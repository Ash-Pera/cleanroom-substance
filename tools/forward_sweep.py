#!/usr/bin/env python3
"""Find where a render first loses its signal, walking FORWARDS from the leaves.

    python3 tools/forward_sweep.py [file.sbsasm] [--dim N]
    python3 tools/forward_sweep.py --packs          # every reference package

WHY FORWARDS. The natural move when an output is wrong is to trace back from it, and that
is how the `levels` record-129 investigation ate several sessions: every candidate drags a
39-record cone behind it, and eliminating one costs a full re-render. Chesterfield's
basecolor was traced backwards through the cone, through the parameter widths, through the
placement and through the transform convention -- and the first record where the render
actually stops carrying its input's structure is rec 14, then rec 43, both far upstream of
the record being argued about.

Record indices are TOPOLOGICAL -- edges are backward indices, an invariant this repository
checks separately -- so index order is already forward order and no sort is needed.

WHAT IT REPORTS. For each record, the per-channel std of its output against the largest
per-channel std among its inputs. A record whose inputs carry contrast and whose output
does not is where signal dies. Per-channel, not the array's: a 4-channel constant colour
has an overall std of 0.433, which is inter-channel spread, and reading that as "varying"
is a trap `refcompare` and `test_filters` both record falling into.

A collapse is NOT automatically a fault -- `levels` with `levelouthigh` 0.0385 is supposed
to crush its input to near-black, and does. The report is a worklist ordered by position,
not a defect list.

WHAT IT FOUND FIRST TIME OUT, over the five reference packages, 698 fxmaps records:

    varying          372   53.3%
    CONSTANT 1.00    268   38.4%
    CONSTANT 0.00     38    5.4%
    CONSTANT 0.92     16    2.3%
    not rendered       4    0.6%

So 46% of fxmaps records emit no pattern at all. The dominant shape is the chainless form
-- no node chain, slot 2 addressing the parameter table directly -- which 5e05c2f banks as
a real decode gap, and entry COUNT does not separate constant from varying (both occur at
1, 2, 3 and 4+ entries), so the entries are being found and read and it is the pattern
placement that does not reach the canvas. That rate is the part not previously written
down; the gap itself is known.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np                                                   # noqa: E402
import sbsasm                                                        # noqa: E402
import sbsruntime                                                    # noqa: E402
import render as R                                                   # noqa: E402

IN_FLOOR = 0.02        # an input must carry this much contrast for a collapse to mean anything
OUT_CEIL = 0.005       # below this the output is flat


def chan_std(x):
    """The largest PER-CHANNEL std. See the docstring on why not the array's."""
    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 3:
        return float(max(a[:, :, c].std() for c in range(a.shape[2])))
    return float(a.std())


def sweep(path, max_dim=256):
    """[(record, filter, size, in_std, out_std, out_mean, inputs)], in forward order."""
    sbsruntime.SAMPLERS.clear()          # samplers persist across renders; see refcompare
    asm = sbsasm.Assembly(path)
    produced, failures, _synth = R.render(asm, verbose=False, max_dim=max_dim)
    out = []
    for rec in asm.records:
        i = rec.index
        if i not in produced:
            continue
        ins = []
        for e in rec.edge_slots:
            if e is None or e >= len(rec.words):
                continue
            v = rec.words[e]
            if 0 <= v < len(asm.records) and v in produced:
                ins.append(v)
        if not ins:
            continue
        si = max(chan_std(produced[j]) for j in ins)
        so = chan_std(produced[i])
        if si > IN_FLOOR and so < OUT_CEIL:
            out.append((i, sbsasm.FILTERS.get(rec.filter_id, str(rec.filter_id)),
                        '%dx%d' % (rec.width, rec.height), si, so,
                        float(np.asarray(produced[i], dtype=np.float64).mean()), ins))
    return out, failures


def main(argv):
    max_dim = 256
    if '--dim' in argv:
        k = argv.index('--dim')
        max_dim = int(argv[k + 1]); del argv[k:k + 2]
    if '--packs' in argv:
        import refcompare, glob
        paths = []
        for pack in refcompare.reference_packs():
            paths += glob.glob(os.path.join(refcompare.PACKS, pack, '**', '*.sbsasm'),
                               recursive=True)
    elif len(argv) > 1:
        paths = [argv[1]]
    else:
        import corpus
        paths = corpus.paths()[:1]
    for p in paths:
        try:
            rows, failures = sweep(p, max_dim)
        except Exception as e:
            print('%s: %s' % (os.path.basename(p), e))
            continue
        print('\n== %s ==' % os.path.basename(p))
        print('%-6s %-15s %-10s %8s %8s %8s  %s'
              % ('rec', 'filter', 'size', 'in_std', 'out_std', 'out_mean', 'inputs'))
        for t in rows[:20]:
            print('%-6d %-15s %-10s %8.4f %8.4f %8.4f  %s' % t)
        print('collapses: %d' % len(rows))
        hard = [(i, str(v)[:48]) for i, v in sorted(failures.items())
                if 'has no output yet' not in str(v)]
        if hard:
            print('genuine render failures: %d   first: rec %d  %s' % (len(hard), hard[0][0], hard[0][1]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
