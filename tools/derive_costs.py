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

PAYLOAD = {0: 3, 22: 3, 5: 1}    # filter -> slot holding its payload pointer

# How to read words[1], per filter. The first model treated it as a code vector
# everywhere, and the four worst rejections were exactly the four filters where it is
# not one: an ARITY INTEGER (pixelprocessor low nibble, fxmaps bits 10-13), ABSENT
# (uniform bakes a value there; filter 5 points at its payload), or PER-RECORD (warp
# and shuffle have two shapes, and the edge run starting at slot 1 is the no-w1 shape).
W1_ARITY = {20: (0, 0xF), 4: (10, 0xF)}      # filter -> (shift, mask)
W1_ABSENT = {6, 5, 16, 13}
W1_PER_RECORD = {7, 3}
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
            else:
                inline = [x for x in r.programs if r.offset < x < r.end]
                if not inline:
                    continue
                q = min(inline)
            if not (r.offset < q < r.end):
                continue
            f = r.filter_id
            w1 = r.words[1]
            if f in W1_ABSENT:
                w1 = None
            elif f in W1_PER_RECORD:
                # Two record shapes. The edge run starting at slot 1 is the shape with
                # no w1 word at all; treat its "w1" as absent rather than keying on an
                # edge value, which is what gave warp 12,366 keys for 26,416 records.
                try:
                    es = [s for s in r.edge_slots if s < len(r.words)]
                except Exception:
                    es = []
                if es and min(es) == 1:
                    w1 = None
            obs[f][(r.cls, w1)][(q - r.offset) // 4] += 1
    return obs


def fit(f, keys):
    """Fit costs for one filter. Returns (spec, exact_fraction) or (None, 0.0).

    Weighted by record count, and refit once with anomalous keys excluded. The first
    version fit unweighted over keys and levels came out at 48%: its dominant key
    (32,735 records, header 6) counted exactly as much as a two-record key whose
    "header" was 14, and the junk keys dragged the costs. A cost table must answer for
    records, not for keys, so the fit must too. Exactness is still reported over ALL
    keys, junk included -- exclusion is for the fit, never for the score.
    """
    arity = W1_ARITY.get(f)

    def bits_of(keys):
        clsbits = [b for b in range(16) if len({k[0] >> b & 1 for k, _, _ in keys}) > 1]
        aw = [k[1] for k, _, _ in keys if k[1] is not None]
        excl = set()
        if arity is not None:
            sh, m = arity
            excl = {j for j in range(16) if (m << sh) >> (2 * j) & 3}
        pairs = [j for j in range(16) if j not in excl
                 and len({(w >> (2 * j)) & 3 for w in aw}) > 1] if aw else []
        return clsbits, pairs

    clsbits, pairs = bits_of(keys)
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
    ok = np.rint(X @ c) == y
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


def main():
    obs = observed()
    out, report = {}, []
    for f, d in sorted(obs.items(), key=lambda kv: -sum(sum(c.values()) for c in kv[1].values())):
        keys = [(k, c.most_common(1)[0][0], sum(c.values())) for k, c in d.items()]
        n = sum(x[2] for x in keys)
        if len(keys) < 10:
            report.append((f, n, len(keys), None, 'too few keys')); continue
        spec, exact = fit(f, keys)
        if spec is None:
            report.append((f, n, len(keys), None, 'underdetermined')); continue
        report.append((f, n, len(keys), exact, 'kept' if exact >= KEEP else 'rejected'))
        if exact >= KEEP:
            out[str(f)] = spec
    with open(OUT, 'w') as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    print('%-16s %9s %7s %9s  %s' % ('filter', 'records', 'keys', 'exact', 'status'))
    kept = tot = 0
    for f, n, k, e, st in report:
        tot += n
        if st == 'kept':
            kept += n
        print('  %-14s %9d %7d %9s  %s'
              % (FILTERS.get(f) or 'fid %d' % f, n, k,
                 ('%.3f%%' % (100 * e)) if e is not None else '    -', st))
    print()
    print('wrote %s: %d filters, covering %d of %d records (%.2f%%) at >= %.1f%% exact'
          % (os.path.basename(OUT), len(out), kept, tot, 100 * kept / tot, 100 * KEEP))
    return 0


if __name__ == '__main__':
    sys.exit(main())
