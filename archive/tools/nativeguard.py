#!/usr/bin/env python3
"""The native row of the reference guard: every pack rendered at its implied `$outputsize`
with NO grid cap, scored per row (corr, band, dc) through `refguard.measure`.

WHY A NATIVE ROW. `refcompare`'s grids (128 / 256 / 512 under the implied size) cap the
pixel grid below the size every texel-dependent construct was written for -- flood fills,
jump floods, height-to-normal taps, `256 / min($size)` blurs -- and there is no one `$size`
reading that is right under a cap: the declared size is the faithful downsample, the grid
is the only reading under which a texel-stepping machine runs at all. At native there is
no such choice. FORMAT-NOTES.md, "The capped grid is a lie every texel-dependent construct
hears differently".

    python3 archive/tools/nativeguard.py                       # current defaults
    python3 archive/tools/nativeguard.py distance.propagate=spread
    ONLY=Bricks python3 archive/tools/nativeguard.py           # one pack

IT SCORES THROUGH `render2-lean`, AND THAT IS WHAT MAKES THE NATIVE ROW REACHABLE AT ALL.
This file was written when `graph.outputsize` defaulted to `first`, which pinned Bricks
002-005 and Auras 002-004 at 256 -- so "Bricks takes ~2 min, RoofTiles ~11 min at 2048",
the timing this docstring used to carry, was taken on a render that was mostly NOT at
native. With `pergraph` the default every record is built at the declared size and the
ordinary whole-file pass holds every array: 112 GB on Bricks at 1024, 58 GB on
Chesterfield at 2048, against live peaks of 3.5 and 13.1 GB under the lean pass. The
lean pass is a MEMORY policy and nothing else -- `test_filters
.test_render2_lean_renderer_matches_the_whole_file_render` holds it to bit-identical
outputs, and Auras, the one pack small enough to render both ways, gives all three rows
identical to three decimals. See `refcompare._lean_renderer`.

Graph-input overrides the exports used and the file does not record (RoofTiles' tile
counts) are applied per pack, as `refcompare`'s pairing corrections are: a score against
an export made with other inputs is not a score. SandyStonePath's `Use_Random_Tiles` is
`refcompare.EXPORT_SETS`'s now -- its two export sets are two settings of that toggle and
each is scored under its own -- so the override here merges UNDER whatever the pairing
passes rather than replacing it.

THE OVERRIDE IS INSTALLED ON EVERY BINDING OF `render`, AND COUNTED. `engine.py` is loaded
TWICE in this process -- as top-level `engine`, which is what `render2.render` is bound to,
and as `render2.engine`, which is what `refcompare._lean_renderer` calls -- two module
objects from one file, because `render2/__init__.py` does `from engine import render`
while `refcompare` does `from render2 import engine`. A patch written against
`render2.render` alone is therefore SILENTLY INERT under the lean renderer: RoofTiles
would be scored at its declared 1 x 1 tiling against exports made at 14 x 9, which is not
a score and which no output of this file would say. `_install` patches all three and
`_calls` counts them, so a binding this file does not know about is an assertion rather
than a wrong number.
"""
import os, sys, time
_HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(os.path.dirname(_HERE))
for p in (os.path.join(ROOT,'tools'), os.path.join(ROOT,'tools','render2'), _HERE):
    sys.path.insert(0,p)
import numpy as np, assume, refcompare, refguard, render2
import engine as _engine_top
from render2 import engine as _engine_pkg
EXTRA=dict(kv.split('=') for kv in (sys.argv[1] if len(sys.argv)>1 else '').split(',') if kv)
for k,v in list(EXTRA.items()):
    for c in assume.QUESTIONS.get(k,()):
        if str(c)==v: EXTRA[k]=c
packs=refcompare.reference_packs()
OV={'Kutejnikov__Stylized_Wooden_Roof_Tiles':{2367149106:(14,9),2366871910:(14,),2366870030:(9,)}}
#: Every binding of `render` this process holds, with the function each one started as.
#: See the module docstring: there are three, from two module objects and one file.
_ORIG=[(m,a,getattr(m,a)) for m,a in ((render2,'render'),(_engine_top,'render'),(_engine_pkg,'render'))]
_calls=[0]
def _install(ov):
    """Merge `ov` UNDER whatever the pairing passes, on every binding, counting calls."""
    for m,a,orig in _ORIG:
        def patched(*args,_orig=orig,_ov=ov,**kw):
            _calls[0]+=1
            return _orig(*args, **dict(kw, inputs={**_ov, **(kw.get('inputs') or {})}))
        setattr(m,a,patched)
with assume.scope(**EXTRA):
    for pack in sorted(packs):
        if os.environ.get('ONLY') and os.environ['ONLY'] not in pack: continue
        os_=refcompare.implied_outputsize(packs[pack]); dim=2**max(os_) if os_ else 256
        _install(OV.get(pack,{})); _calls[0]=0
        t=time.time()
        try:
            rows=[(n,c,refguard.measure(o,r)) for n,c,o,r in refcompare.compare_pack(pack, packs[pack], max_dim=dim, outputsize="implied", renderer="render2-lean", grid=None, qualify_graph=True) if c is not None]
        except Exception as e:
            print("%s ERROR %s" % (pack,e), flush=True); continue
        # A pack that produced rows without going through a patched binding was rendered
        # at inputs this file believes it overrode. Loud, because the number would not be.
        assert _calls[0] or not rows, "%s: %d rows and 0 patched render calls" % (pack,len(rows))
        seen=set(); rows=[x for x in rows if not ((x[0],x[1]) in seen or seen.add((x[0],x[1])))]
        live=[m for _,_,m in rows if not m.flat]
        print("%-40s dim %4d %4.0fs rows %2d corr %+.3f band %.3f |dc| %.3f" % (pack[:40],dim,time.time()-t,len(rows),np.mean([m.corr for m in live]) if live else float('nan'),np.mean([m.band for m in live]) if live else float('nan'),np.mean([abs(m.dc) for m in live]) if live else float('nan')), flush=True)
        for n,c,m in rows: print("     %-28s ch%d corr %+.3f band %.3f dc %+.3f%s" % (n,c,m.corr,m.band,m.dc,' FLAT' if m.flat else ''), flush=True)
