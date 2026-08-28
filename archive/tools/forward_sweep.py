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

WHAT THE 46% ACTUALLY IS, chased from there. Not the chainless encoding 5e05c2f banks --
that is real (RoofTiles rec1398 yields chain=0 and entries=0, its words a flat interleave
of program pointers and constants) but it is a different, rarer population. Over the
reference packs no record has unreadable entries at all, and chainlessness barely shifts
the odds:

    has a node chain    228 varying   173 CONSTANT
    chainless           155 varying   142 CONSTANT

The discriminator is whether `patternsize` is readable across an entry table, and it is
absolute where it bites:

    patternsize on ALL entries      294 varying    31 CONSTANT
    patternsize on SOME entries       0 varying   240 CONSTANT
    patternsize on NO entries        60 varying    53 CONSTANT

240 of 240, no counterexample. That is the full-cell fallback `fxrender.entries` documents:
an entry whose patternsize cannot be read paints the WHOLE canvas, so one unreadable entry
in an otherwise-good table obliterates every real pattern in the record. The record does
not degrade, it goes uniformly white.

SKIPPING THOSE ENTRIES IS NOT THE FIX, and the reference says so rather than intuition.
Dropping unsized entries in mixed tables recovers 186 records (CONSTANT 324 -> 138), and
against the exported maps that buys nothing: 27 channels, 2 better, 11 worse, every delta
in the fourth decimal (worst -0.0012, best +0.0014). Nominally negative, practically a
wash. Note the metric is gameable in the direction tested -- dropping entries can only
remove white paint, so it can only push records toward `varying` whether or not that is
closer to the engine -- which is why the exported maps and not the constant count decide.

So the flat-white cost is largely INVISIBLE to the reference set. WHY it is invisible is
attenuation, NOT topology, and the first version of this note had that wrong: it said the
recovered records are "mostly not on scored paths". cleanroom-substance-01 measured
reachability over the eight packages and every record is on a scored path -- 34,675 of
34,675 in the ancestor cone of some declared output, verified per file rather than by
aggregate, with fxmaps reaching 83 of 96 outputs. These are cooked packages; dead records
were eliminated before the corpus ever saw them.

So the fxmaps records are maximally on-path and the channels still moved by at most 0.0014.
Influence dies through the blends, levels and clamps between a record and the output it
feeds, which is a much harder thing to work around than a reachability gap would have been.

And that 0.0014 is UNCALIBRATED. Nobody has measured this renderer's reproducibility, so
"the arms moved the scored channels by at most 0.0014" is only a conclusion if the
instrument's own floor is known to be below it. 01 is measuring the floor. Until that
number exists the honest form of every figure in this file is "against an instrument whose
floor is unmeasured".

That leaves the fallback policy unarbitrated here, and points at reading `patternsize`
properly (a328c8c) rather than at choosing a better thing to do when it cannot be read.

LEVELS' SECOND FAULT, FOUND BY DIFFERENCING TWO CONES. Routing `levels` onto the walk
wrecks Chesterfield basecolor while IMPROVING roughness (+0.8834 -> +0.8956 at 128,
+0.8689 -> +0.9234 at 256). A wrong decode degrades broadly; a correct decode meeting one
broken consumer degrades sharply in one place and improves elsewhere. Both outputs take the
same corrected value from record 129, so the fault is in what basecolor reaches and
roughness does not: 25 records, of which 12 amplify.

Those 25 contain a REDUCTION PYRAMID and it is resolution-dependent:

    322 blend 256x256 -> 323 pp 64x64 -> 324 pp 16x16 -> 325 pp 4x4 -> 326 pp 1x1
    ... -> 329 pp 1x1 -> 330 pp 256x256, inputs [322, 329]

That is the auto-normalise idiom -- reduce an image to a global scalar, then normalise the
image by it. Records 326 and 329 are declared 1x1, so their values are scalars and CANNOT
legitimately depend on the render grid. They do:

    max_dim      326 (1x1)   329 (1x1)   330        871 basecolor
    64             0.61516     0.61516   0.96910    0.51545
    128            0.54476     0.54476   0.99177    0.51997
    256            0.50000     0.50000   FAIL       FAIL

So the normalising scalar is a function of how coarsely we chose to render, which is not a
property of the file. basecolor is normalised by it through 330 and roughness is not, which
is exactly why one output gets worse and the other gets better from the same correction.

WHY THE MEMO LOOKED RIGHT. With `levels` on the memo, record 129 feeds a constant white
into this pyramid and the scalar's error lands somewhere that happens to match the export.
Correct 129 and the error is exposed rather than introduced. That is the "two faults
cancelling" account with the second fault named: not a parameter misread, an evaluator that
does not honour a declared 1x1 extent.

Independently found from the other side by the rendering session, which traced
basecolor's 256 failure to rec 330 non-finite <- rec 329 <- rec 322 constant at 256. Same
records, two directions, no shared assumption.

RETRACTED, THE SAME DAY, BY cleanroom-substance-07's TEST. The resolution dependence above
is an artifact of THIS HARNESS, not a property of the file. Rendering uncapped:

    max_dim      326 (1x1)   329 (1x1)
    64             0.61516     0.61516
    128            0.54476     0.54476
    256            0.50000     0.50000
    None           0.50000     0.50000      <- converged and stopped

A 1x1 record's own grid cannot move -- min(1, 64) is 1 -- so the dependence was never
coming from the 1x1 record. It arrived through its INPUT, which is the failure `render.py`
documents at its own lines 41-48: capping each pixelprocessor's width and height
INDEPENDENTLY does not preserve two different records' size ratio to each other, and a
reduction pyramid is the worst possible shape for that. The docstring ends "rendering a
single file for real output should leave `max_dim` unset", and I had not.

07 predicted the result from the shape of the numbers before running anything: three
readings converging on a round value is an artifact vanishing as the cap stops binding, not
a decode fault. That is the third time this repository has lost time to a
resolution-dependent symptom reading as a misplaced parameter -- previously on `blur` and
on `distance` -- so it is recorded here as a pattern rather than as a third separate
mistake.

WHAT SURVIVES, AND IT IS WORSE FOR THE LEVELS QUESTION THAN WHAT I CLAIMED. Uncapped,
record 330 still fails non-finite and basecolor still does not render at all -- 874 records
produced, 7 failed, 871 among them. So basecolor is SCOREABLE ONLY AT 128, which is
precisely the regime where per-record capping distorts a reduction pyramid inside its own
cone. Every levels arbitration anyone has run, mine included, has been run there.

That does not say the memo is right or that the walk is. It says the instrument that has
been vetoing `levels` all along has never been read in a regime where it can be trusted for
this output, and the veto should carry that caveat until basecolor renders at full
resolution.

The cone-differencing that produced the 25 records is unaffected -- it is a graph
computation with no render in it -- and the roughness/basecolor divergence is still real at
both 128 and 256. What is withdrawn is the mechanism I attached to it.
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
