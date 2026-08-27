#!/usr/bin/env python3
"""What is NOT read by the walk -- measured, not listed.

The walk is the format's one structural primitive (see walk.py), and where it applies it
answers with no free parameters. This tool enumerates what is left: every read that still
comes from a fitted formula, a memo lookup, a value probe, or an outright guess. Each is a
place a render can be wrong in a way no reference score attributes correctly, because the
error arrives as a plausible number rather than as a failure.

It is a MEASUREMENT and not a list, for the reason corpus.py exists: a correction recorded
in prose does not propagate to code, so an inventory that cannot go stale has to be run.

    python3 tools/nonwalked.py

WHAT IT REPORTS, and the one finding that reframes the rest:

  1. ROUTING, per filter -- are edges walked, and are parameters walked, memo'd, or
     neither. Edge coverage is essentially total; parameter coverage is not.

  2. THE EDGE-XOR-PARAMETER RULE on every memo-routed filter. A parameter must never be
     read out of an input-edge slot: that is a record index reinterpreted as a float, it
     reads 0.0, and no plausibility test can see it. This is the arbiter sbsasm.py already
     uses to prefer the walk for `levels`.

  3. THE CENSUS BLIND SPOT. `corpus.paths()` and the reference packs are DISJOINT. Thirteen
     tools measure the corpus; three touch the packs. So every "corpus-wide" figure in this
     project excludes the only eight files with ground-truth renders, and every figure
     computed against the packs is outside what the corpus tools have ever seen.

     This is not hypothetical. `Record.ramp` carries a patch for gradient records whose
     pointer pair sits one word late; the three records it is fitted to are Auras 312, 424
     and 442, they are the ONLY such records anywhere, and Auras is a reference pack. The
     patch is fitted to the scoring set and no corpus census can see the population it
     describes. (The class word does mark them -- cls bits 9 AND 10, together, 3 of 3,
     against 26 records with one bit or the other and no shift -- so there is a structural
     signal here. Three records cannot establish a rule; what they establish is that the
     value probe is standing in for something the file states.)

  4. THE OPEN QUESTIONS in `assume`, with their arm counts. These are the live guesses.
     They are not annotations -- they move pixels: on Bricks, `fx.combine=add` moves the
     overall reference correlation from +0.209 to +0.271 while making basecolor WORSE
     (-0.250 to -0.337). Any residual analysis is conditional on where these are set.
"""
import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assume                                                        # noqa: E402
import corpus                                                        # noqa: E402
import sbsasm                                                        # noqa: E402
import walk                                                          # noqa: E402
from sbsasm import Assembly                                          # noqa: E402

REF_GLOB = 'new_opengameart/**/*.sbsasm'


def reference_files():
    return sorted(glob.glob(REF_GLOB, recursive=True))


def routing():
    """(records by filter, and how each filter's edges and parameters are read)."""
    n = collections.Counter()
    for p in corpus.paths():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            n[r.filter_id] += 1
    rows = []
    for f, c in n.most_common():
        edges = ('walk/spec' if f in walk.SPECS else
                 'walk/tierA' if f in walk.TIER_A_EDGES else 'NOT WALKED')
        params = ('walk' if f in sbsasm.WALKED_PARAMS else
                  'memo' if f in sbsasm.PARAM_SPEC else 'no spec')
        rows.append((sbsasm.FILTERS.get(f, f), c, edges, params))
    return rows, sum(n.values())


def edge_xor(paths):
    """Parameter slots that land ON an input edge, per memo-routed filter.

    `decompose`'s `inputs` is the edge set, validated 903,611 of 903,611 against
    `_compute_layout` + `_real_edges`, so it is independent of where either parameter
    model puts a parameter.
    """
    import decompose
    stat = collections.defaultdict(collections.Counter)
    for p in paths:
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            f = r.filter_id
            if f not in sbsasm.PARAM_SPEC or f in sbsasm.WALKED_PARAMS:
                continue
            if len(r.words) < 3:
                continue
            hit = sbsasm.LAYOUTS.get(
                (f, r.cls, r.words[1] & sbsasm.LAYOUT_MASK.get(f, 0)))
            if not hit or len(hit[1]) < 2:
                continue
            present = [nm for nm, pres, _p in sbsasm.PARAM_SPEC[f] if r.words[1] & pres]
            if not present:
                continue
            try:
                edges = set(decompose.decompose(r)['inputs'])
            except Exception:
                continue
            for _nm, sl in zip(present, r._param_slots(hit[1], len(present))):
                c = stat[f]
                c['slots'] += 1
                if sl < 2 or sl >= len(r.words):
                    c['outside record'] += 1
                elif sl in edges:
                    c['ON AN INPUT EDGE'] += 1
                else:
                    c['clean'] += 1
    return stat


def blind_spot():
    """The corpus list and the ground-truth packs, and how many tools see each."""
    cp = set(corpus.paths())
    rf = set(os.path.abspath(p) for p in reference_files())
    here = os.path.dirname(os.path.abspath(__file__))
    uses_corpus = uses_refs = 0
    for py in sorted(glob.glob(os.path.join(here, '*.py'))):
        text = open(py, encoding='utf-8', errors='replace').read()
        uses_corpus += 'corpus.paths()' in text
        uses_refs += 'new_opengameart' in text
    return len(cp), len(rf), len(cp & rf), uses_corpus, uses_refs


# HOW THE "no spec" FILTERS ARE ACTUALLY READ. This column is the most misread thing in
# this report, and it cost a full pass down a false trail: "no PARAM_SPEC" is NOT "not
# walked", and it is not "not read". Every one of these has a reader; most are the walk.
#
#   warp          `decompose(rec)['end'] - 1`, the last header slot -- the same rule blur
#                 and sharpen use. CONFIRMED INDEPENDENTLY by containment here: over the
#                 permitted paired sources, a declared constant `intensity` lands on the
#                 LAST class slot in 15 of 15, across two record shapes (slot 5 where the
#                 header ends at 6, slot 4 where it ends at 5).
#   transformation `Record.matrix` / `Record.translation`, both walk-placed.
#   distance      `distance._locate_slot`, the walk's parameter slot.
#   blur, sharpen `end - 1`, 15,371 of 15,371 and 1,323 of 1,323.
#   uniform       a FITTED formula, and it survives -- see below.
#   gradient      `Record.ramp`; slot 2 states the count and the pointer pair the span.
#
# UNIFORM IS THE ONE GENUINELY FITTED PLACEMENT LEFT, and three walk-derived replacements
# were tried and all three lost. `outputcolor` is a Float4 (Float1 greyscale) and render.py
# places it at `(2 if has_prog else 1) + (1 if cls bit 7 else 0)`. Against containment on
# the permitted sources -- 1,976 records where a declared colour is found in the bytes:
#
#     the fitted formula                    1,975 / 1,976
#     end - (4 if colour else 1)            1,975 / 1,976     coverage 33.8%
#     prog + 1                              1,975 / 1,976
#     first class slot after prog           1,975 / 1,976     coverage 33.8%
#     the fitted formula, coverage                            coverage 81.1%
#
# All four tie on truth, all four miss the same record, and the ground truth cannot
# separate them -- the `blur.slot` situation exactly. But the walk forms are not merely
# unarbitrated, they are WORSE: 62.4% of uniform records have no class slot after `prog`
# at all, so a prog-relative read has nothing to name. The fitted formula stays, and this
# is recorded so the next sweep for slot arithmetic does not re-propose the same swap.
#
# A TRAP FOR ANYONE ADDING PARAM_SPEC ENTRIES. `decompose.named_params` reads `r.words[1]`
# as the w1 presence mask, and for several filters SLOT 1 IS AN EDGE, not a mask -- warp,
# gradient, blur, sharpen, curve, hsl and dyngradient have no w1 word at all. A PARAM_SPEC
# entry for one of those would read a backward record index as a presence mask. Measured
# over corpus + packs, records whose slot 1 is an edge: gradient 5,803 of 5,803, blur 4,524
# of 4,524, sharpen 415 of 415, curve 291, hsl 258, dyngradient 962.
#
# Two filters look mixed and only one is. `shuffle` really has two shapes and the COLOUR
# FLAG states which, with no exceptions -- 4,032 greyscale records with no w1, 3,781 colour
# records with one -- which is walk.py's grayscaleconversion / Channel Shuffle reading,
# confirmed here. `warp` is NOT mixed: it always has exactly two inputs, at slots [1,2] in
# 26,390 records and at [2,3] in 1,710, one extra word ahead of the edges under the SAME
# class word (0x2b19 occurs in both). The walk already resolves both -- it reports
# cls_slots [4,5,6] and end 7 for the shifted shape against [3,4,5] and 6 -- so `end - 1`
# still lands on the intensity. Nothing to fix; recorded because "same class word, two
# layouts" is worth knowing before someone keys a memo on the class word.
READ_PATHS = """  "no spec" is NOT "not read" and NOT "not walked" -- see the note above this
  function. warp/blur/sharpen read `end-1`, transformation uses matrix/translation,
  distance uses the walk's parameter slot, gradient uses ramp. Of the unspeced
  filters only `uniform` still places a parameter by a fitted formula, and three
  walk-derived replacements were measured and all three were worse."""


def main():
    rows, tot = routing()
    print('ROUTING -- %d records over %d corpus files\n' % (tot, len(corpus.paths())))
    print('  %-16s %8s %7s  %-12s %s' % ('filter', 'records', 'share', 'edges', 'parameters'))
    share = collections.Counter()
    for name, c, edges, params in rows:
        share[params] += c
        print('  %-16s %8d %6.2f%%  %-12s %s' % (name, c, 100.0 * c / tot, edges, params))
    print('\n  parameters by routing:')
    for k in ('walk', 'memo', 'no spec'):
        print('     %-10s %8d %6.2f%%' % (k, share[k], 100.0 * share[k] / tot))
    print(READ_PATHS)

    print('\nEDGE-XOR-PARAMETER, memo-routed filters (corpus + reference packs):')
    stat = edge_xor(list(corpus.paths()) + reference_files())
    print('  %-16s %9s %9s %14s %9s' % ('filter', 'slots', 'clean', 'ON EDGE', 'outside'))
    tt = collections.Counter()
    for f in sorted(stat):
        c = stat[f]
        for k in c:
            tt[k] += c[k]
        print('  %-16s %9d %9d %14d %9d'
              % (sbsasm.FILTERS.get(f, f), c['slots'], c['clean'],
                 c['ON AN INPUT EDGE'], c['outside record']))
    print('  %-16s %9d %9d %14d %9d'
          % ('TOTAL', tt['slots'], tt['clean'], tt['ON AN INPUT EDGE'], tt['outside record']))
    if tt['slots']:
        print('  corrupt reads: %d of %d = %.2f%%'
              % (tt['ON AN INPUT EDGE'] + tt['outside record'], tt['slots'],
                 100.0 * (tt['ON AN INPUT EDGE'] + tt['outside record']) / tt['slots']))

    nc, nr, ov, uc, ur = blind_spot()
    print('\nCENSUS BLIND SPOT:')
    print('  corpus.paths()          %4d files' % nc)
    print('  reference packs         %4d files   (the only ground-truth renders)' % nr)
    print('  overlap                 %4d files' % ov)
    print('  tools measuring corpus  %4d' % uc)
    print('  tools touching packs    %4d' % ur)
    if ov == 0:
        print('  -> DISJOINT. No corpus-wide figure in this project describes the files it'
              '\n     is scored on, and nothing scored is covered by a corpus census.')

    print('\nOPEN QUESTIONS -- the live guesses, %d of them:' % len(assume.QUESTIONS))
    bymod = collections.defaultdict(list)
    for k, v in sorted(assume.QUESTIONS.items()):
        bymod[k.split('.')[0]].append((k, len(v)))
    for mod in sorted(bymod, key=lambda m: -sum(n for _k, n in bymod[m])):
        ks = bymod[mod]
        print('  %-12s %2d question(s), %3d arms total'
              % (mod, len(ks), sum(n for _k, n in ks)))
        for k, n in ks:
            print('       %-26s %d arm%s%s'
                  % (k, n, '' if n == 1 else 's', '   <- unresolved, no arms' if not n else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
