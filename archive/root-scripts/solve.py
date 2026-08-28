#!/usr/bin/env python3
"""Identify unknown opcodes by residual matching against isolating function graphs.

For a graph whose live nodes are all of KNOWN type except one, the compiled run must
contain exactly the predicted op-ids plus N copies of one unknown op-id. Finding runs
that fit and taking the residual votes for the unknown node's opcode. Votes are pooled
across the whole corpus, so no single coincidence decides anything.

`get_*` nodes are a wildcard over {0x01 system, 0x03 parameter, 0x04 local} because the
compiler picks by variable kind, which the .sbs does not record directly.
"""
import collections, glob, os, sys
import code_region, runs, sbsgraph

GET = {0x01, 0x03, 0x04}
NAME2OP = {
 'set':0x07,'sequence':0x0C,'while':0x0B,'ifelse':0x09,
 'vector2':0x0D,'vector3':0x0D,'vector4':0x0D,
 'swizzle1':0x10,'swizzle2':0x10,'swizzle3':0x10,
 'add':0x12,'sub':0x13,'mul':0x14,'div':0x15,'dot':0x18,'sqrt':0x28,
 'samplecol':0x34,'eq':0x1D,'and':0x1A,'or':0x1B,'not':0x1C,
 'gt':0x1F,'gteq':0x20,'lr':0x21,'lreq':0x22,'atan2':0x2D,
 'min':0x30,'max':0x31,'samplelum':0x33,'mulscalar':0x14,'iswizzle1':0x10,
 'tofloat':0x11,'tofloat2':0x11,'toint1':0x11,'toint2':0x11,
 'exp':0x2A,'ceil':0x25,'neg':0x17,'abs':0x23,'mod':0x16,'lerp':0x2F,
 'rand':0x32,'cartesian':0x2E,'min':0x30,
}
for c in ('const_float1','const_float2','const_float3','const_float4','const_int1','const_bool'):
    NAME2OP[c]=0x00
GETNAMES={'get_float1','get_float2','get_float3','get_float4',
          'get_integer1','get_integer2','get_bool'}
KNOWN=set(NAME2OP)|GETNAMES

def runs_of(path):
    out=[]
    try: d,spans,r = code_region.code_spans(path)
    except Exception: return out
    for lo,hi in spans:
        for st,cnt,blk in runs.runs(d,lo,hi):
            if cnt<2: continue
            ins,_=runs.instrs(d,st,cnt)
            oc=collections.Counter(op&0x3F for _,op,_,_ in ins)
            out.append((st,cnt,oc,ins))
    return out

def match_file(sbs, asm, votes, tally, opvotes):
    R=runs_of(asm)
    if not R: return
    for g in sbsgraph.graphs(sbs):
        h=sbsgraph.live_hist(g); n=sum(h.values())
        if not (2<=n<=24): continue
        if 'instance' in h: continue     # inlined - never maps 1:1 to one instruction
        unk=[k for k in h if k not in KNOWN]
        if len(unk)!=1: continue
        uname=unk[0]; ucount=h[uname]
        pred=collections.Counter(); ngets=0
        for name,c in h.items():
            if name==uname: continue
            if name in GETNAMES: ngets+=c
            else: pred[NAME2OP[name]]+=c
        hits=[]
        for st,cnt,oc,ins in R:
            if cnt!=n: continue
            if sum(oc[k] for k in GET)!=ngets: continue
            resid=collections.Counter()
            ok=True
            for k,c in oc.items():
                if k in GET: continue
                d2=c-pred.get(k,0)
                if d2<0: ok=False; break
                if d2: resid[k]+=d2
            if not ok: continue
            if sum(pred.values())!=sum(c for k,c in oc.items() if k not in GET)-sum(resid.values()):
                continue
            if len(resid)==1 and list(resid.values())[0]==ucount:
                hits.append((list(resid)[0], [op for _,op,_,_ in ins if (op&0x3F)==list(resid)[0]]))
        # only an UNAMBIGUOUS match is evidence: one run, one residual op-id
        cand={h[0] for h in hits}
        tally[uname]+=len(hits)
        if len(cand)==1 and len(hits)>=1:
            votes[uname][hits[0][0]]+=1
            for op in hits[0][1]: opvotes[uname][op]+=1
