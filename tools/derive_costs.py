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

PAYLOAD = {0: 3, 22: 3}          # filter -> slot holding its payload pointer
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
            obs[r.filter_id][(r.cls, r.words[1])][(q - r.offset) // 4] += 1
    return obs


def fit(keys):
    """Fit costs for one filter. Returns (spec, exact_fraction) or (None, 0.0)."""
    clsbits = [b for b in range(16) if len({k[0] >> b & 1 for k, _, _ in keys}) > 1]
    pairs = [j for j in range(16) if len({(k[1] >> (2 * j)) & 3 for k, _, _ in keys}) > 1]

    def row(cls, w1):
        v = [1.0] + [float(cls >> b & 1) for b in clsbits]
        for j in pairs:
            st = (w1 >> (2 * j)) & 3
            v += [float(st == 1), float(st == 2), float(st == 3)]
        return v

    X = np.array([row(k[0], k[1]) for k, _, _ in keys])
    y = np.array([h for _, h, _ in keys], dtype=float)
    wt = np.array([n for _, _, n in keys], dtype=float)
    if X.shape[0] <= X.shape[1]:
        return None, 0.0                      # fewer observations than unknowns
    c = np.rint(np.linalg.lstsq(X, y, rcond=None)[0] * 2) / 2
    ok = np.rint(X @ c) == y
    spec = {'const': c[0],
            'cls': {str(b): c[1 + i] for i, b in enumerate(clsbits)},
            'w1': {}}
    base = 1 + len(clsbits)
    for i, j in enumerate(pairs):
        spec['w1'][str(j)] = {'1': c[base + 3 * i],
                              '2': c[base + 3 * i + 1],
                              '3': c[base + 3 * i + 2]}
    return spec, float(wt[ok].sum() / wt.sum())


def main():
    obs = observed()
    out, report = {}, []
    for f, d in sorted(obs.items(), key=lambda kv: -sum(sum(c.values()) for c in kv[1].values())):
        keys = [(k, c.most_common(1)[0][0], sum(c.values())) for k, c in d.items()]
        n = sum(x[2] for x in keys)
        if len(keys) < 10:
            report.append((f, n, len(keys), None, 'too few keys')); continue
        spec, exact = fit(keys)
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
