import sys, os, collections
sys.path.insert(0, 'tools')
import corpus, render, sbsruntime, output_census
from sbsasm import Assembly
rows = []; files = 0
for p in corpus.paths():
    if os.path.getsize(p) > 8_000_000: continue
    try:
        asm = Assembly.cached(p)
        decl = list(asm.outputs())
        if not decl: continue
        sbsruntime.SAMPLERS.clear()
        got, fails, _s = render.render(asm, verbose=False, max_dim=48)
        casc = set(render.CASCADED)
    except Exception: continue
    files += 1
    fed = output_census.image_fed_outputs(asm)
    rend = [r for u,_f,_g,r in decl if u not in fed and r in got]
    want = [(u, r) for u,_f,_g,r in decl if u not in fed]
    if want and not rend:
        roots = collections.Counter()
        for u, r in want:
            for x in output_census.roots_blocking(asm, r, fails, casc):
                roots[str(x)[:58]] += 1
        rows.append((os.path.basename(p)[:34], len(want), roots.most_common(2)))
    if files >= 55: break
print('files scanned=%d   files rendering ZERO of their renderable outputs: %d' % (files, len(rows)))
agg = collections.Counter()
for nm, n, rs in rows:
    for k, v in rs: agg[k] += 1
print('\nmost common root in a zero-output file:')
for k, v in agg.most_common(10): print('  %2d files  %s' % (v, k), flush=True)
print()
for nm, n, rs in rows[:12]: print('  %-36s %d outputs  %s' % (nm, n, rs[0][0] if rs else '?'), flush=True)
