#!/usr/bin/env python3
"""The native row of the reference guard: every pack rendered at its implied `$outputsize`
with NO grid cap, scored per row (corr, band, dc) through `refguard.measure`.

WHY A NATIVE ROW. `refcompare`'s grids (128 / 256 / 512 under the implied size) cap the
pixel grid below the size every texel-dependent construct was written for -- flood fills,
jump floods, height-to-normal taps, `256 / min($size)` blurs -- and there is no one `$size`
reading that is right under a cap: the declared size is the faithful downsample, the grid
is the only reading under which a texel-stepping machine runs at all. At native there is
no such choice. FORMAT-NOTES.md, "The capped grid is a lie every texel-dependent construct
hears differently". Bricks takes ~2 min, RoofTiles ~11 min at 2048.

    python3 archive/tools/nativeguard.py                       # current defaults
    python3 archive/tools/nativeguard.py distance.propagate=spread
    ONLY=Bricks python3 archive/tools/nativeguard.py           # one pack

Graph-input overrides the exports used and the file does not record (RoofTiles' tile
counts) are applied per pack, as `refcompare`'s pairing corrections are: a score against
an export made with other inputs is not a score. SandyStonePath's `Use_Random_Tiles` is
`refcompare.EXPORT_SETS`'s now -- its two export sets are two settings of that toggle and
each is scored under its own -- so the override here merges UNDER whatever the pairing
passes rather than replacing it.
"""
import os, sys, time
_HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(os.path.dirname(_HERE))
for p in (os.path.join(ROOT,'tools'), os.path.join(ROOT,'tools','render2'), _HERE):
    sys.path.insert(0,p)
import numpy as np, assume, refcompare, refguard, render2
EXTRA=dict(kv.split('=') for kv in (sys.argv[1] if len(sys.argv)>1 else '').split(',') if kv)
for k,v in list(EXTRA.items()):
    for c in assume.QUESTIONS.get(k,()):
        if str(c)==v: EXTRA[k]=c
packs=refcompare.reference_packs()
OV={'Kutejnikov__Stylized_Wooden_Roof_Tiles':{2367149106:(14,9),2366871910:(14,),2366870030:(9,)}}
orig=render2.render
with assume.scope(**EXTRA):
    for pack in sorted(packs):
        if os.environ.get('ONLY') and os.environ['ONLY'] not in pack: continue
        os_=refcompare.implied_outputsize(packs[pack]); dim=2**max(os_) if os_ else 256
        ov=OV.get(pack,{})
        render2.render=lambda *a,ov=ov,**k: orig(*a, **dict(k, inputs=dict(ov, **(k.get('inputs') or {}))))
        t=time.time()
        try:
            rows=[(n,c,refguard.measure(o,r)) for n,c,o,r in refcompare.compare_pack(pack, packs[pack], max_dim=dim, outputsize="implied", renderer="render2", grid=None, qualify_graph=True) if c is not None]
        except Exception as e:
            print("%s ERROR %s" % (pack,e), flush=True); continue
        seen=set(); rows=[x for x in rows if not ((x[0],x[1]) in seen or seen.add((x[0],x[1])))]
        live=[m for _,_,m in rows if not m.flat]
        print("%-40s dim %4d %4.0fs rows %2d corr %+.3f band %.3f |dc| %.3f" % (pack[:40],dim,time.time()-t,len(rows),np.mean([m.corr for m in live]) if live else float('nan'),np.mean([m.band for m in live]) if live else float('nan'),np.mean([abs(m.dc) for m in live]) if live else float('nan')), flush=True)
        for n,c,m in rows: print("     %-28s ch%d corr %+.3f band %.3f dc %+.3f%s" % (n,c,m.corr,m.band,m.dc,' FLAT' if m.flat else ''), flush=True)
