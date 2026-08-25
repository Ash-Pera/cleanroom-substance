#!/usr/bin/env python3
"""Derive each filter's SLOT COSTS from the corpus, and emit costs.json.

A record is a struct with two presence masks, and its header size is therefore a sum:

    header = const + SUM over set cls bits of that parameter's cost
                   + SUM over w1 fields of that field's cost in its state

Nothing here is hand-written. The costs are fitted from (cls, w1) -> observed header
size and then rounded, and a filter is only kept if the rounded costs reproduce every
header exactly. That is the whole test: a model that has to predict an integer number of
slots for thousands of distinct mask combinations cannot be fitted by accident.

What comes out is the parameter table the format implies. Two coefficients are worth
reading directly, because both were established elsewhere by completely different means
and this recovers them cold:

    cls bit 10 costs +2      recorded in FORMAT-NOTES as "a baked 2-component value,
                             never a program"
    transformation field 3   costs +4 baked and +1 as a program -- matrix22 is a Float4,
                             and "baked costs its width, a program costs one slot" is
                             the rule that made the earlier fitted weights stop looking
                             arbitrary

The header boundary is observed as the start of the record's first inline program. For
the two payload filters (gradient's ramp, curve's control points) the payload sits
between header and code, so their boundary is the payload pointer instead.
"""
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
from sbsasm import Assembly, FILTERS                                  # noqa: E402

PAYLOAD = {0: 3, 22: 3, 5: 1, 4: 2, 16: 1}  # filter -> slot holding its payload pointer
# bitmap (16) stores PIXELS: slot 1 is the pixel offset when it is small enough to be a
# file offset (Record.bitmap's own discrimination). A stored-pixel record's "record end"
# boundary swallowed the pixel payload -- one Grid.sbsasm record measured a 16,386-word
# "header" that was 64KB of image. For graph-input records slot 1 is a uid and the +52
# probe lands outside the record, so those simply contribute no observation.
# fxmaps (4) belongs here even though its "payload" is the fx TREE: slot 2 is the tree
# root pointer, and the root sits immediately after the header -- the earliest in-record
# pointer is slot 2's in 40,802 of 40,802 records. The first-INLINE-PROGRAM probe was
# measuring into the tree (a position set by node sizes, not the header), which is why
# fxmaps sat rejected at 49% while every observable that respects its structure is
# 99.9% deterministic.

# How to read words[1], per filter. The first model treated it as a code vector
# everywhere, and the four worst rejections were exactly the four filters where it is
# not one: an ARITY INTEGER (pixelprocessor low nibble, fxmaps bits 10-13), ABSENT
# (uniform bakes a value there; filter 5 points at its payload), or PER-RECORD (warp
# and shuffle have two shapes, and the edge run starting at slot 1 is the no-w1 shape).
W1_ARITY = {20: (0, 0xF), 4: (10, 0xF)}      # filter -> (shift, mask)
W1_ABSENT = {6, 5, 16, 13, 10, 14, 19}
# blur (10), hsl (14) and dyngradient (19) joined when the all-baked records entered
# the fit: they are start-1 filters -- words[1] is their first EDGE -- and keying on an
# edge value gave blur 12,006 keys for 15,371 records, the one-key-per-record signature
# this file already names twice.
W1_PER_RECORD = {3}      # warp (7) moved to the version rule above

# Filters whose costs are fitted on modern versions only. Emboss is EXACT (375 of 375)
# from 0x50000 up under the colour-x-baked-states law, and its 51 older records sit in
# keys that contradict themselves -- the same within-key contradictions that first put
# it beyond any function of (word0, w1). The spec carries min_version and answers None
# below it, falling to the memo rather than guessing at a population that has already
# demonstrated it is not a function of these masks.
MIN_VERSION = {8: 0x50000}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'costs.json')
KEEP = 0.995                     # a filter is kept only at this exactness or better


def observed():
    """(filter, cls, w1) -> Counter of header sizes in words."""
    obs = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for p in corpus.paths():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if len(r.words) < 2:
                continue
            sl = PAYLOAD.get(r.filter_id)
            if sl is not None:
                if len(r.words) <= sl:
                    continue
                q = r.words[sl] + 52
                if not (r.offset < q <= r.end):
                    # The payload lives OUTSIDE the record (bitmap keeps most pixel
                    # data in the pre-body region; only oversized images are inline).
                    # The record is then nothing but header, or header plus inline
                    # programs -- the ordinary boundary logic applies.
                    inline = [x for x in r.programs if r.offset < x < r.end]
                    q = min(inline) if inline else r.end
            else:
                inline = [x for x in r.programs if r.offset < x < r.end]
                if not inline:
                    # An all-baked record is NOTHING BUT header, so its own end is the
                    # boundary. These are 12.7% of the corpus and the fit never saw
                    # them: this probe needed an inline program, so every all-baked
                    # shape was invisible, and levels' cls-0x18 population -- 11,843
                    # records of [tag][w1][edge][baked][baked] -- was represented by
                    # the 13 program-carrying stragglers alone, which starved the fit
                    # into overcharging it by 2. A record with a trailing node region
                    # violates the assumption and lands as a junk key, which the
                    # robust trim already handles.
                    q = r.end
                else:
                    q = min(inline)
            # `<=` and not `<`: an all-baked record's boundary IS its end. The first
            # version of this check silently re-dropped every record the all-baked
            # branch had just admitted, and the derivation came back byte-identical --
            # the only sign was that the numbers did not move.
            if not (r.offset < q <= r.end):
                continue
            f = r.filter_id
            if f in MIN_VERSION:
                ver = a.header.get('version') if isinstance(a.header, dict) else 0
                if ver < MIN_VERSION[f]:
                    continue
            w1 = r.words[1]
            if f in W1_ABSENT:
                w1 = None
            elif f == 7:
                # warp's w1 word is a VERSION fact: absent before 0x90000, present (so
                # far always zero) from it. The edge-start detector used here before
                # could not tell w1 == 0 from "an edge to record 0" -- the ambiguity
                # its own docstring predicted -- and misread 180 v9 records, holding
                # warp at 99.31%. With version as the rule it fits at 99.993%.
                ver = a.header.get('version') if isinstance(a.header, dict) else 0
                if ver < 0x90000:
                    w1 = None
            elif f in W1_PER_RECORD:
                # shuffle's two shapes coexist WITHIN versions, so its discrimination
                # stays per-record: slot 1 is self-describing (a backward index or a
                # big field word), and the edge run starting at slot 1 marks no-w1.
                try:
                    es = [s for s in r.edge_slots if s < len(r.words)]
                except Exception:
                    es = []
                if es and min(es) == 1:
                    w1 = None
            # The whole of word 0, not just cls. The tag's low bits carry layout too:
            # uniform's colour flag (tag bit 0) is +3 words -- a colour value bakes four
            # floats where a grayscale bakes one -- and keying on cls alone left 3,209
            # records as within-key minorities that no fit could reach. Bits that do not
            # vary within a filter never become features, so widening the mask is free.
            obs[f][(r.words[0], w1)][(q - r.offset) // 4] += 1
    return obs


def fit(f, keys, bitrange=range(32), colour='off'):
    """Fit costs for one filter. Returns (spec, exact_fraction) or (None, 0.0).

    Weighted by record count, and refit once with anomalous keys excluded. The first
    version fit unweighted over keys and levels came out at 48%: its dominant key
    (32,735 records, header 6) counted exactly as much as a two-record key whose
    "header" was 14, and the junk keys dragged the costs. A cost table must answer for
    records, not for keys, so the fit must too. Exactness is still reported over ALL
    keys, junk included -- exclusion is for the fit, never for the score.
    """
    arity = W1_ARITY.get(f)

    # Which bits of word 0 may become features. 'wide' offers all 32 -- the tag's low
    # half carries layout (uniform's colour flag is tag bit 0, +3 words) -- but those
    # bits INTERACT for some filters (the colour cost differs by sampling class), and
    # an additive model over interacting bits is worse than one that cannot see them.
    # So both widths are fitted and the caller keeps whichever is exact. Bits that do
    # not vary never become features, so 'wide' is free where the tag is constant.
    def bits_of(keys, bitrange):
        clsbits = [b for b in bitrange if len({k[0] >> b & 1 for k, _, _ in keys}) > 1]
        aw = [k[1] for k, _, _ in keys if k[1] is not None]
        excl = set()
        if arity is not None:
            sh, m = arity
            excl = {j for j in range(16) if (m << sh) >> (2 * j) & 3}
        pairs = [j for j in range(16) if j not in excl
                 and len({(w >> (2 * j)) & 3 for w in aw}) > 1] if aw else []
        return clsbits, pairs

    clsbits, pairs = bits_of(keys, bitrange)
    has_absent = any(k[1] is None for k, _, _ in keys)

    def row(cls, w1):
        v = [1.0] + [float(cls >> b & 1) for b in clsbits]
        if has_absent:
            v.append(float(w1 is not None))    # the w1 word itself occupies a slot
        if arity is not None:
            sh, m = arity
            v.append(float((w1 >> sh) & m) if w1 is not None else 0.0)
        for j in pairs:
            st = ((w1 >> (2 * j)) & 3) if w1 is not None else 0
            v += [float(st == 1), float(st == 2), float(st == 3)]
        if colour == 'full':
            # The colour flag is tag bit 0, and its cost is not additive: a colour
            # value bakes more floats than a grayscale one, so the flag multiplies
            # WIDTHS rather than adding a constant. Crossing it with every feature
            # lets the fit discover which slots widen -- uniform's +3 lands on the
            # value slot only when cls bit 8 is set, which a main effect cannot say.
            c0 = float(cls & 1)
            v = v + [c0 * x for x in v]
        elif colour == 'states':
            # The lean variant, and the width law's own shape: colour multiplies BAKED
            # widths and nothing else, so cross the flag with the state features alone.
            # Half the columns of 'full', which is what lets a 30-key filter fit at
            # all -- emboss was underdetermined under 'full' and is EXACT under this.
            c0 = float(cls & 1)
            nstate = 3 * len(pairs)
            v = v + [c0 * x for x in v[len(v) - nstate:]]
        return v

    def solve(sub):
        X = np.array([row(k[0], k[1]) for k, _, _ in sub])
        y = np.array([h for _, h, _ in sub], dtype=float)
        wt = np.array([n for _, _, n in sub], dtype=float)
        if X.shape[0] <= X.shape[1]:
            return None
        sw = np.sqrt(wt)
        c = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
        return np.rint(c * 2) / 2

    # Fit on plausible headers only; SCORE on everything. A header is a struct's slot
    # count, a handful of words -- pixelprocessor's real headers are 5 + arity. But its
    # observation table also held keys claiming headers of 33,687 words: records where
    # the first-program probe missed and measured to some later program. Squared error
    # made those few keys the entire objective (10 records x 30,000^2 outweighs 23,000
    # records x 1^2), and the fit came back with const = -110.5 and an arity cost of 63.
    # The robust trim could not recover, because "within 2 of an insane model" keeps the
    # junk that built it. So the cap comes first: no observed header above 64 words
    # informs the fit. It still counts against the score -- exclusion is for the fit,
    # never for the reported exactness.
    fit_pop = [k for k in keys if k[1] <= 64]
    c = solve(fit_pop if len(fit_pop) >= 10 else keys)
    if c is None:
        return None, 0.0
    X = np.array([row(k[0], k[1]) for k, _, _ in keys])
    y = np.array([h for _, h, _ in keys], dtype=float)
    wt = np.array([n for _, _, n in keys], dtype=float)
    # robust pass: refit without keys the first fit missed by 2+ words
    err = np.abs(np.rint(X @ c) - y)
    keep = [k for k, e in zip(fit_pop, np.abs(np.rint(
        np.array([row(k[0], k[1]) for k, _, _ in fit_pop]) @ c)
        - np.array([h for _, h, _ in fit_pop]))) if e < 2] if fit_pop else []
    if len(keep) >= 10 and len(keep) < len(fit_pop):
        c2 = solve(keep)
        if c2 is not None:
            c = c2
    # Integer refinement. Weighted least squares minimises squared error, and under
    # collinearity the minimiser can round to a vector that loses whole keys by exactly
    # one word while a neighbouring integer vector loses none -- v2 transformation sat
    # at 69.9% with every miss equal to -1 for exactly this reason. So: coordinate
    # descent from the rounded solution, scoring by the thing that matters (weighted
    # exact hits), in half-word steps, until a sweep improves nothing.
    def _score(cv):
        return float(wt[np.rint(X @ cv) == y].sum())
    wt = np.array([n for _, _, n in keys], dtype=float)
    X = np.array([row(k[0], k[1]) for k, _, _ in keys])
    y = np.array([h for _, h, _ in keys], dtype=float)
    best = _score(c)
    for _sweep in range(6):
        moved = False
        for i in range(len(c)):
            for d in (-1.0, -0.5, 0.5, 1.0):
                c2 = c.copy(); c2[i] += d
                s2 = _score(c2)
                if s2 > best:
                    c, best, moved = c2, s2, True
        if not moved:
            break
    ok = np.rint(X @ c) == y
    if colour == 'states':
        nstate = 3 * len(pairs)
        base_c, cross_c = c[:len(c) - nstate], c[len(c) - nstate:]
        spec = {'interaction': 'colour_states', 'clsbits': clsbits, 'pairs': pairs,
                'has_absent': bool(has_absent),
                'arity_sm': list(arity) if arity is not None else None,
                'base': [float(x) for x in base_c],
                'cross': [float(x) for x in cross_c],
                'mode': ('absent' if f in W1_ABSENT else
                         'per_record' if f in W1_PER_RECORD else
                         'arity' if f in W1_ARITY else 'codes')}
        wt_ = np.array([n for _, _, n in keys], dtype=float)
        return spec, float(wt_[ok].sum() / wt_.sum())
    if colour == 'full':
        # Interaction spec: store the two half-vectors; predict as base + bit0*cross.
        half = len(c) // 2
        base_c, cross_c = c[:half], c[half:]
        spec = {'interaction': 'colour', 'clsbits': clsbits, 'pairs': pairs,
                'has_absent': bool(has_absent),
                'arity_sm': list(arity) if arity is not None else None,
                'base': [float(x) for x in base_c],
                'cross': [float(x) for x in cross_c],
                'mode': ('absent' if f in W1_ABSENT else
                         'per_record' if f in W1_PER_RECORD else
                         'arity' if f in W1_ARITY else 'codes')}
        wt_ = np.array([n for _, _, n in keys], dtype=float)
        return spec, float(wt_[ok].sum() / wt_.sum())
    names = ['const'] + ['cls%s' % b for b in clsbits]
    mode = ('absent' if f in W1_ABSENT else
            'per_record' if f in W1_PER_RECORD else
            'arity' if f in W1_ARITY else 'codes')
    spec = {'const': c[0], 'cls': {str(b): c[1 + i] for i, b in enumerate(clsbits)},
            'w1': {}, 'mode': mode}
    i = 1 + len(clsbits)
    if has_absent:
        spec['w1_present'] = c[i]; i += 1
    if arity is not None:
        spec['arity'] = {'shift': arity[0], 'mask': arity[1], 'cost': c[i]}; i += 1
    for n_, j in enumerate(pairs):
        spec['w1'][str(j)] = {'1': c[i + 3 * n_], '2': c[i + 3 * n_ + 1],
                              '3': c[i + 3 * n_ + 2]}
    return spec, float(wt[ok].sum() / wt.sum())


# Filters whose field costs INTERACT with the sampling class (cls bits 8-9): the same
# w1 field in state 10 costs 1 slot in class 3 and 3 slots in class 0 for fxmaps. An
# additive model cannot hold both, so these filters are fitted per class, and the spec
# carries a guard: it answers only for the class it was fitted on and returns None for
# the rest, which fall through to the memo. Class 0 is 20 keys and 1,418 records and
# does not clear the bar on its own -- kept out rather than guessed at.
SPLIT_SAMPLING = {4}


def main():
    obs = observed()
    out, report = {}, []
    for f, d in sorted(obs.items(), key=lambda kv: -sum(sum(c.values()) for c in kv[1].values())):
        keys = [(k, c.most_common(1)[0][0], sum(c.values())) for k, c in d.items()]
        n = sum(x[2] for x in keys)
        if len(keys) < 10:
            report.append((f, n, len(keys), None, 'too few keys')); continue
        if f in SPLIT_SAMPLING:
            best = None
            for sc in (0, 3):
                sub = [x for x in keys if (x[0][0] >> 24) & 3 == sc]
                if len(sub) < 10:
                    continue
                spec, exact = fit(f, sub, range(32))
                spec2, exact2 = fit(f, sub, range(16, 32))
                if spec2 is not None and exact2 > exact:
                    spec, exact = spec2, exact2
                if spec is None or exact < KEEP:
                    continue
                spec['guard'] = {'shift': 24, 'mask': 3, 'value': sc}   # cls bits 8-9, in word0
                cov = sum(x[2] for x in sub)
                if best is None or cov > best[2]:
                    best = (spec, exact, cov)
            if best is None:
                report.append((f, n, len(keys), 0.0, 'rejected')); continue
            spec, exact, cov = best
            report.append((f, cov, len(keys), exact, 'kept (guarded to its class)'))
            out[str(f)] = spec
            continue
        spec, exact = fit(f, keys, range(32))
        spec2, exact2 = fit(f, keys, range(16, 32))
        if exact2 > exact:                        # narrow (cls-only) model wins
            spec, exact = spec2, exact2
        # The FORMAT byte (word0 bits 8-15) carries layout for some filters -- bitmap's
        # 0xaa/0xbb formats cost one extra word -- but bits 0-7 are junk features that
        # hurt the integer refinement, so the mask that sees the format byte without
        # them is its own candidate. bitmap: 99.33% under both other masks, 100.00%
        # under this one.
        spec2b, exact2b = fit(f, keys, range(8, 32))
        if spec2b is not None and exact2b > exact:
            spec, exact = spec2b, exact2b
        spec3, exact3 = fit(f, keys, range(32), colour='full')
        if spec3 is not None and exact3 > exact:  # colour-interaction model wins
            spec, exact = spec3, exact3
        spec4, exact4 = fit(f, keys, range(16, 32), colour='states')
        if spec4 is not None and exact4 > exact:  # lean colour-x-baked variant wins
            spec, exact = spec4, exact4
        if spec is None:
            report.append((f, n, len(keys), None, 'underdetermined')); continue
        report.append((f, n, len(keys), exact, 'kept' if exact >= KEEP else 'rejected'))
        if exact >= KEEP:
            if f in MIN_VERSION:
                spec['min_version'] = MIN_VERSION[f]
            out[str(f)] = spec
    with open(OUT, 'w') as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    print('%-16s %9s %7s %9s  %s' % ('filter', 'records', 'keys', 'exact', 'status'))
    kept = tot = 0
    for f, n, k, e, st in report:
        tot += n
        if st.startswith('kept'):
            kept += n
        print('  %-14s %9d %7d %9s  %s'
              % (FILTERS.get(f) or 'fid %d' % f, n, k,
                 ('%.3f%%' % (100 * e)) if e is not None else '    -', st))
    print()
    print('wrote %s: %d filters, covering %d of %d records (%.2f%%) at >= %.1f%% exact'
          % (os.path.basename(OUT), len(out), kept, tot, 100 * kept / tot, 100 * KEEP))
    # ---- the width law
    # A cost is not a free parameter. The record is a serialized parameter list, so
    # every coefficient must be a TYPE WIDTH: baked = the parameter's component count
    # (1, 2, 3 or 4), program = 1 pointer, image = 1 edge, and the inherited
    # parameters have the same width in every filter. The fit exists only to RECOVER
    # that table where the type declarations are unknown -- so any coefficient that is
    # not a small non-negative integer is not a finding, it is a flag: either two
    # populations averaged (distance's 1.5s -- really a Float2's 2 and a fit
    # degeneracy), or an inline node region absorbed as a constant (fxmaps' 10/16/32),
    # or a mishandled shape (shuffle's negatives).
    lawless = []
    for fs, spec in out.items():
        def each(label, v):
            if v and (float(v) != int(float(v)) or v < 0 or v > 4):
                lawless.append((fs, label, float(v)))
        if 'base' in spec:
            for i, v in enumerate(spec['base']):
                each('base[%d]' % i, v)
            continue
        each('const', spec['const'])
        for b, v in spec['cls'].items():
            each('cls%s' % b, v)
        if spec.get('arity'):
            each('arity', spec['arity']['cost'])
        for j, states in spec['w1'].items():
            for st, v in states.items():
                each('f%s.%s' % (j, st), v)
    if lawless:
        print()
        print('coefficients violating the width law (each is a flag, not a finding):')
        for fs, label, v in lawless:
            print('   filter %-4s %-12s %g' % (fs, label, v))
    return 0


if __name__ == '__main__':
    sys.exit(main())
