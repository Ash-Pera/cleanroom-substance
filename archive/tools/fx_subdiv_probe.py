#!/usr/bin/env python3
"""PROBE: FX-Map quadrant subdivision -- every entry cell is a Quadrant whose four outputs
name a child, and the chain of cells is a nesting, not a list.

Monkeypatches `render2.fx.emissions`; touches nothing in the repository's own model. See
FORMAT-NOTES.md, "The level fault upstream of 10055 is a white-noise FX-Map emitting ONE
pattern, and the cons chain is quadrant subdivision". Knobs are environment variables:

    SUBDIV=0|1      off = the repository's emissions (baseline)      default 1
    ROOT=0|1        does the tree's root cell itself subdivide      default 1
    BO=region|canvas   branchoffset units                            default region
    SZ=region|canvas   patternsize / frameoffset units               default region
    QORDER=rowmajor|clockwise|colmajor   which output is which quadrant
    SALT=0|1        fresh `rand` draw per region                     default 1
    ASSUME=k=v,...  assume.scope choices, e.g. fx.negopacity=abs
    DIM, SAVE       render cap; npz of the declared outputs

Renders Kutejnikov__Bricks_and_tiles / Textures_1 at `$outputsize` 10 and scores every
declared output against its own graph's export by identity (128-px grid, per channel).
"""
import sys, os, glob, math, time, collections
import numpy as np, xml.etree.ElementTree as ET
R=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,R+'/archive/tools'); sys.path.insert(0,R+'/tools'); sys.path.insert(0,R+'/tools/render2')
import sbsasm, assume, fxrender, sbsruntime, manifest
from render2 import engine, model, fx
from sbsasm import fx_patterntype

# ---- variant knobs ----
ROOT_SUBDIVIDES = os.environ.get('ROOT','1')=='1'   # leaf depth = index (1) or index-1 (0)
BO_UNITS = os.environ.get('BO','region')            # branchoffset scale: region | canvas
SIZE_UNITS = os.environ.get('SZ','region')          # patternsize/frameoffset: region | canvas
SALT = os.environ.get('SALT','1')=='1'              # fresh rand per region

_rand0 = sbsruntime.rand
def rand_salted(limit):
    x = np.asarray(limit, dtype=np.float64)
    num = sbsruntime.CONTEXT["number"]
    n = num.astype(np.float64, copy=False).reshape(-1, 1) if isinstance(num, np.ndarray) and num.ndim else float(num)
    s = float(sbsruntime.CONTEXT.get("salt", 0.0)) if SALT else 0.0
    h = np.modf(np.sin(x * 12.9898 + n * 78.233 + s * 37.719) * 43758.5453)[0] % 1.0
    return x * h
sbsruntime.rand = rand_salted

QUAD = ((-1,-1),(1,-1),(-1,1),(1,1))

def cells_of(rec, table):
    """{offset: (tag, params, children)} -- children is a 4-list of child offsets (None = no
    child), read from the entry's own structural slots: bit 17 = ONE pointer shared by all
    four outputs, bit 16 = FOUR pointers, one per output (0 = unconnected)."""
    import struct
    by_off = {off:(tag,params) for off,tag,params in table}
    d = rec.asm.data
    cells={}; order=[]
    for k,o,t,p in rec.fx_walk():
        if k!='entry' or o in cells: continue
        if not ((t>>16)==0x0002 or o in by_off): continue
        kids=[None]*4
        # LAYOUT: [tag][params ptr][child ptrs][bit-4 word][params...]; a BARE cell is
        # [tag][next]. Bit 17 = one child for all four outputs, bit 16 = four, 0 = none.
        first = 2 if (t >> 19) else 1
        if (t >> 17) & 1:
            w=struct.unpack_from('<I',d,o+4*first)[0]
            if w: kids=[w+52]*4
        elif (t >> 16) & 1:
            for q in range(4):
                w=struct.unpack_from('<I',d,o+4*(first+q))[0]
                kids[q]=(w+52) if w else None
        cells[o]=(t, by_off.get(o,(t,{}))[1], kids)
        order.append(o)
    # A LINK MAY LAND ONE WORD SHORT OF ITS TARGET'S TAG (the entry's leading header word,
    # see fxrender.entries: "the run begins one word later"). Resolve to the cell there.
    for o,(t,p,kids) in list(cells.items()):
        cells[o]=(t,p,[(c if (c is None or c in cells) else (c+4 if (c+4) in cells else c)) for c in kids])
    return cells, order

QORDER = {'rowmajor': ((-1,-1),(1,-1),(-1,1),(1,1)), 'clockwise': ((-1,-1),(1,-1),(1,1),(-1,1)),
          'colmajor': ((-1,-1),(-1,1),(1,-1),(1,1))}[os.environ.get('QORDER','rowmajor')]

def emissions_subdiv(rec, run, slots, cache=None):
    nodes = fxrender.chain(rec)
    table = fxrender.entries(rec)
    if not table:
        raise fx.Unsupported("fxmaps: no emittable entries -- %s" % fxrender.why_no_entries(rec))
    for _off, hdr, _p in nodes:
        if not fx._known_node(hdr):
            raise fx.Unsupported("fxmaps: node header %#x is not modelled" % hdr)
    fx_progs = {p for _o, _h, ps in nodes for p in ps.values() if p}
    for _o, _t, params in table:
        for _k, (kind, value) in params.items():
            if kind != "baked" and value: fx_progs.add(value)
    for prog in sorted(set(rec.programs) - fx_progs):
        try: run(prog, slots, 0)
        except Exception: pass
    cells, order = cells_of(rec, table)
    pointed = {c for t,p,kids in cells.values() for c in kids if c}
    roots = [o for o in order if o not in pointed]
    out=[]; closed=[False]; ran_once=set()
    budget=[0]

    def evaluate(params, number):
        got={}
        for name,(kind,value) in fxrender.in_eval_order(params):
            if value is None: continue
            if kind!='baked': got[name]=run(value, slots, number)
            elif isinstance(value,np.ndarray): got[name]=value
            else: got[name]=np.asarray(value,dtype=np.float32).ravel()
        return got

    def draw(off, cx, cy, depth, salt, number, seen):
        if off not in cells or off in seen or depth>9: return
        tag, params, kids = cells[off]
        s = 2.0**(-depth)
        sbsruntime.CONTEXT['salt'] = salt
        got = evaluate(params, number)
        p = {'patterntype': fx_patterntype(tag), '_tag': tag}
        p.update(got)
        sp = s if SIZE_UNITS=='region' else 1.0
        size = got.get('patternsize')
        if size is None and (tag & 0xFF)!=0x08:
            size = np.ones(2,np.float32)
        if size is not None:
            p['patternsize'] = np.asarray(size,np.float32).ravel()*sp
        if 'frameoffset' in got:
            p['frameoffset'] = np.asarray(got['frameoffset'],np.float32).ravel()*sp
        bo = np.asarray(got.get('branchoffset', (0.0,0.0)),np.float64).ravel()
        if bo.size<2: bo=np.repeat(bo[:1],2)
        bo = bo*(s if BO_UNITS=='region' else 1.0)
        p['branchoffset'] = np.array([cx+bo[0],cy+bo[1]],np.float32)
        out.append(p)
        budget[0]+=1
        if budget[0] > 600000: raise fx.Unsupported("subdiv: pattern budget")
        if not any(kids): return
        subdiv = ROOT_SUBDIVIDES or depth>0 or off!=roots[0]
        if not subdiv:
            k=[c for c in kids if c][0]
            draw(k, cx+bo[0], cy+bo[1], depth, salt*4+1, number, seen|{off}); return
        q = s/4.0
        for qi,(qx,qy) in enumerate(QORDER):
            c=kids[qi]
            if c: draw(c, cx+bo[0]+qx*q, cy+bo[1]+qy*q, depth+1, salt*4+qi+1, number, seen|{off})

    def emit(number):
        for r in roots:
            draw(r, 0.0, 0.0, 0, float(number)*7919.0+1.0, number, frozenset())

    def walk(i, number, mode):
        if i == len(nodes):
            emit(number); return
        _off, hdr, progs = nodes[i]
        role = fx.fxnodes.role(hdr)
        if role == "count":
            prog = progs.get("numberadded")
            if prog is None: raise fx.Unsupported("fxmaps: addnode with no numberadded program")
            if "randomseed" in progs and progs["randomseed"] is not None:
                run(progs["randomseed"], slots, number)
            raw = int(round(float(np.asarray(run(prog, slots, number)).ravel()[0])))
            if not 0 <= raw <= fx.MAX_PATTERNS: raise fx.Unsupported("fxmaps: numberadded = %d" % raw)
            n, mode = fx.emission_count(rec, raw)
            for k in range(n): walk(i + 1, k, mode)
            return
        if role == "gate":
            prog = progs.get("switch")
            if prog is None: raise fx.Unsupported("fxmaps: markov2 with no switch program")
            if mode == "placement":
                if i not in ran_once:
                    ran_once.add(i); run(prog, slots, number)
                walk(i + 1, number, mode); return
            if bool(np.asarray(run(prog, slots, number)).ravel()[0]): walk(i + 1, number, mode)
            else: closed[0] = True
            return
        if role == "state":
            prog = progs.get(None)
            if prog is not None and (mode == "chain" or i not in ran_once):
                ran_once.add(i); run(prog, slots, number)
            walk(i + 1, number, mode); return
        if role in ("branch", "leaf", "link"):
            walk(i + 1, number, mode); return
        raise fx.Unsupported("fxmaps: node header %#x is not modelled" % hdr)
    walk(0, 0, "chain")
    sbsruntime.CONTEXT['salt']=0.0
    if not out and not closed[0]:
        raise fx.Unsupported("fxmaps: emitted no patterns and no gate closed")
    return out

if os.environ.get('SUBDIV','1')=='1':
    # `render2.fx` and `fx` are TWO module objects here (filters.py does `import fx` off
    # the render2 path), so both get the patch.
    import importlib
    fx.emissions = emissions_subdiv
    importlib.import_module('fx').emissions = emissions_subdiv

# ---- render + score ----
BASE=R+'/archive/specimens/new_opengameart/Kutejnikov__Bricks_and_tiles'
ap=glob.glob(BASE+'/x_Bricks_Textures_1/assemblies/content/0000/*.sbsasm')[0]
REF=BASE+'/reference_renders/Textures_1/'
asm=sbsasm.Assembly(ap)
root=ET.parse(sorted(glob.glob(os.path.dirname(ap)+'/*.xml'))[0]).getroot()
uid2={}
for g in root.iter('graph'):
    gn=(g.get('pkgurl') or '').split('/')[-1]
    for o in g.iter('output'): uid2[int(o.get('uid'))]=gn
names=manifest.output_names(asm)
DIM=int(os.environ.get('DIM','256'))
t=time.time()
extra={k.split('=')[0]:k.split('=')[1] for k in os.environ.get('ASSUME','').split(',') if '='in k}
with assume.scope(**extra):
    outs,fails,info=engine.render(asm,max_dim=DIM,outputsize=(10,10))
print('render %.0fs  outputs %d  failures %d'%(time.time()-t,len(outs),len(fails)))
from PIL import Image
def load(p):
    im=Image.open(p); a=np.asarray(im).astype(np.float64)
    a=a/(65535.0 if (im.mode=='I;16' or a.max()>255) else 255.0)
    return a[:,:,:3] if a.ndim==3 else a[:,:,None]
def rs(x,n=128):
    return np.stack([np.asarray(Image.fromarray((np.clip(x[:,:,c],0,1)*65535).astype(np.uint16)).resize((n,n),Image.BILINEAR),dtype=np.float64)/65535 for c in range(x.shape[2])],-1)
rows=[]
for uid,fmt,grey,ri in asm.outputs():
    g=uid2.get(uid); nm=names.get(uid,'?')
    p=REF+'%s_%s.png'%(g,nm)
    if not os.path.exists(p) or ri not in outs: continue
    a=rs(np.asarray(outs[ri],np.float64)); b=rs(load(p))
    for c in range(min(a.shape[2],b.shape[2])):
        x,y=a[:,:,c].ravel(),b[:,:,c].ravel()
        corr=float(np.corrcoef(x,y)[0,1]) if x.std()>1e-9 and y.std()>1e-9 else 0.0
        rows.append((g,nm,c,corr,x.mean(),y.mean(),x.std(),y.std()))
print('%-4s %-17s ch  corr    mean ours/ref   sd ours/ref'%('g','output'))
for r in rows: print('%-4s %-17s %d  %+.3f   %.3f/%.3f   %.3f/%.3f'%r)
byg=collections.defaultdict(list)
for r in rows: byg[r[0]].append(r[3])
print('VARIANT',{k:os.environ.get(k) for k in ('SUBDIV','ROOT','BO','SZ','QORDER','ASSUME')})
print('MEAN CORR by graph:', {g:round(float(np.mean(v)),3) for g,v in sorted(byg.items())}, 'all %.3f'%np.mean([r[3] for r in rows]))
if os.environ.get('SAVE'):
    np.savez_compressed(os.environ['SAVE'], **{str(ri):np.asarray(outs[ri]) for uid,fmt,grey,ri in asm.outputs() if ri in outs})
