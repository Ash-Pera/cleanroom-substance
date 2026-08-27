#!/usr/bin/env python3
"""Where the structural walk does NOT answer, counted per filter.

    python3 tools/walk_health.py

THE POINT IS THE FAILURE COLUMNS, the same discipline `audit_corpus` applies to the
segmenter. Three readings this project has now retired -- blur's `2 + nprog`, sharpen's
five-formula ladder, warp's `4 + popcount(cls & {7,10,11})` -- were each replaced by
`decompose`, and each replacement was justified by containment on a handful of pairings.
That is the right arbiter but a thin one, and it says nothing about the records containment
never reaches. This says what the walk does with ALL of them.

`end` is the walk's header boundary and every retired formula was replaced by a position
measured from it, so its health is the health of those readings. Three outcomes:

    bounds     end < len(words): a header, then a bytecode tail. The normal case.
    == len     the walk consumed the whole record. Not wrong by itself -- a header-only
               record is real, and `blur`'s intensity at `end - 1` is verified 15,371 of
               15,371 with 4,961 of those records in this column -- but it is the shape a
               runaway cursor also produces, so it is counted rather than assumed benign.
    PAST       end > len(words). A header longer than the record it is in. This one is not
               a judgement call: it cannot be right, and anything reading `end - 1` on such
               a record is reading past the end or wrapping into nothing.

MEASURED, 437 files, 903,616 records:

    filter              records     bounds      ==len       past  no-walk
    blend                310697     272186      38511          0        0
    transformation       234859     189269      45590          0        0
    levels                85820      74773      11047          0        0
    directionalwarp       62146      61061       1085          0        0
    pixelprocessor        57965      57965          0          0        0
    fxmaps                41164      41164          0          0        0
    warp                  26795      26581        214          0        0
    gradient              17939      17854         85          0        0
    uniform               16763      10418       6345          0        0
    blur                  15371      10410       4961          0        0
    dirmotionblur         15097      14766        331          0        0
    shuffle                7682       5828        231       1623        0
    distance               2277       2185         15         77        0
    dyngradient            2225       2151          0         74        0
    normal                 1379       1233        125         21        0
    bitmap                 1345        461        884          0        0
    sharpen                1323       1291         32          0        0
    curve                  1273       1273          0          0        0
    hsl                     747        691         56          0        0
    emboss                  546        545          1          0        0
    vectorshape             139          0          0          0      139
    text                     59         43         16          0        0
    filter9                   5          0          0          0        5

1,795 RECORDS IN THE `past` COLUMN, and shuffle holds 1,623 of them with one signature:
tag low byte 0x07 -- the shape that carries a w1 word -- seven words long, walk end 9, over
by exactly 2 in every case. `record_layout` already declares shuffle a two-shape filter
whose w1 exists in only one shape, so this is that declared gap showing up as an arithmetic
error rather than as a refusal. `distance` (77), `dyngradient` (74) and `normal` (21) are
the rest.

WHY THIS MATTERS FOR `normal` SPECIFICALLY, which is the one filter where it changed a
decision. render.py locates `normal`'s baked intensity with an eight-word plausibility scan
-- a search, not a reading -- and the obvious repair was the one that worked for blur,
sharpen and warp: take `end - 1`. Containment refuses it. The single permitted pairing,
`SubstanceDesignerPractice` record 362, declares 2.01 and holds it at slot 4; the scan finds
slot 4, the `start + 2 + bit7 + bit11` arm says 5, and the walk says 6 -- and that record's
`end` is 7 in a 7-word record, so `end - 1` is just the last word rather than a bounded
header slot. One pairing is thin evidence, but it is the evidence there is, and it points
the same way as the 21 over-runs: the cost model does not bound `normal`'s header, and
`w1_present` is unestablished (null) in its spec. So the scan STAYS, and it stays because
the walk cannot answer yet -- not because a search is acceptable.

That is the honest shape of "port everything onto the walk": three filters moved on strong
evidence, and this one is blocked on a cost model that has to be finished first.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import decompose                                                     # noqa: E402
import sbsasm                                                        # noqa: E402


def census(paths=None):
    """{filter name: Counter} over the corpus, or the given paths."""
    st = collections.defaultdict(collections.Counter)
    for p in (paths or corpus.paths()):
        try:
            asm = sbsasm.Assembly.cached(p)
        except Exception:
            continue
        for r in asm.records:
            c = st[sbsasm.FILTERS.get(r.filter_id, 'f%s' % r.filter_id)]
            c['records'] += 1
            d = decompose.decompose(r)
            if d is None or d.get('end') is None:
                c['no-walk'] += 1
                continue
            end, n = d['end'], len(r.words)
            c['past' if end > n else '==len' if end == n else 'bounds'] += 1
    return st


def main(argv):
    st = census(argv[1:] or None)
    print('%-18s %8s %10s %10s %10s %8s'
          % ('filter', 'records', 'bounds', '==len', 'past', 'no-walk'))
    tot = collections.Counter()
    for nm in sorted(st, key=lambda k: -st[k]['records']):
        c = st[nm]
        tot.update(c)
        print('%-18s %8d %10d %10d %10d %8d'
              % (nm, c['records'], c['bounds'], c['==len'], c['past'], c['no-walk']))
    print('%-18s %8d %10d %10d %10d %8d'
          % ('TOTAL', tot['records'], tot['bounds'], tot['==len'],
             tot['past'], tot['no-walk']))
    if tot['past']:
        print('\n%d records claim a header longer than the record. A header cannot '
              'exceed its\nrecord, so every one of these is a defect in the walk rather '
              'than a gap in it.' % tot['past'])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
