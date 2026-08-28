#!/usr/bin/env python3
"""Every rule that decides a record's slot layout, in one place, each one verified.

The rules had accumulated across eight code paths in `sbsasm.py` -- `EDGES`, `LAYOUTS`,
`ALT_LAYOUTS`, `_RULED_PARAMS`, the arity fields, `_compute_layout`'s special cases,
`edge_slots`' override and `_real_edges`' corrections -- and no single place said what
they were. Two of them contradicted each other for a whole day without either being
wrong-looking: filter 8's edges were named (1,2,3) by one and (2,3) by the other, and
because the second ran last, the first was simply dead.

This reports, per rule: how many records it decides, and whether what it decides holds.

The test is not "did it return something". Two independent checks:

  EDGES     every slot it names as an edge holds a backward record index, or the absent
            sentinel 0xFFFFFFFF. This is necessary but WEAK -- a small packed word passes
            it trivially, which is the conflation that produced the shared-reference
            error, the layout table's false edges, and filter 8's phantom third input.

  CONTROL   the correlation between a slot's value and the record's own index, over every
            record the rule decides. A real edge points at a NEARBY record, so the two
            rise together; a packed field does not. This is the check that can fail, and
            the only one that has ever caught anything here.

A rule whose edge check is 100% and whose correlation is near zero is not a rule that
works. It is a rule that has not been tested.
"""
import collections
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
from sbsasm import (Assembly, FILTERS, LAYOUTS, LAYOUT_MASK, EDGES,   # noqa: E402
                    ALT_LAYOUTS, _RULED_PARAMS)


def which_rule(r):
    """Which code path decided this record's layout. Mirrors `_compute_layout`."""
    f = r.filter_id
    w = r.words
    if f == 4 and len(w) > 1:
        k = (w[1] >> 10) & 0xF
        if k and 3 + k < len(w):
            return 'fxmaps arity field (w1>>10)&0xF'
        if not k:
            return 'fxmaps arity field (w1>>10)&0xF'
    if f == 3 and len(w) > 3:
        n = len(r.asm.records)
        bw = lambda v: v == 0 or (v < r.index and v < n)
        if bw(w[1]) or (bw(w[2]) and bw(w[3])):
            return 'shuffle slot-1 discrimination'
    if f == 8 and len(w) > 4:
        n = len(r.asm.records)
        bw = lambda v: v == 0 or (v < r.index and v < n)
        if all(bw(w[s]) for s in (2, 3)):
            return 'emboss fixed (2,3)'
    if f in _RULED_PARAMS and len(w) > 1 and 2 + _RULED_PARAMS[f] < len(w):
        return 'generative walk over PARAM_SPEC'
    if f == 20:
        return 'pixelprocessor arity nibble'
    if LAYOUTS and len(w) > 1:
        if LAYOUTS.get((f, r.cls, w[1] & LAYOUT_MASK.get(f, 0))):
            return 'layouts.json table'
    if ALT_LAYOUTS.get(f):
        return 'ALT_LAYOUTS probe'
    return 'EDGES fallback'


def corr(pairs):
    n = len(pairs)
    if n < 30:
        return None
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def main():
    paths = corpus.paths(verbose=True)
    per = collections.defaultdict(lambda: collections.Counter())
    vals = collections.defaultdict(list)
    slotvals = collections.defaultdict(list)
    for p in paths:
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            rule = which_rule(r)
            c = per[rule]
            c['records'] += 1
            try:
                slots = r.edge_slots
                edges = r.edges
            except Exception:
                c['raised'] += 1
                continue
            present = [s for s in slots if s < len(r.words)]
            c['edge slots named'] += len(present)
            c['unresolved'] += sum(1 for e in edges if e is None)
            for s in present:
                v = r.words[s]
                if v != 0xFFFFFFFF:
                    vals[rule].append((v, r.index))
                    slotvals[(r.filter_id, s)].append((v, r.index))
            c['no edge at all'] += (not present)

    print()
    print('%-36s %9s %9s %7s %8s' % ('rule', 'records', 'edges', 'unres', 'corr'))
    print('%-36s %9s %9s %7s %8s' % ('-' * 36, '-' * 9, '-' * 9, '-' * 7, '-' * 8))
    tot = collections.Counter()
    for rule, c in sorted(per.items(), key=lambda kv: -kv[1]['records']):
        cc = corr(vals[rule])
        tot.update(c)
        print('%-36s %9d %9d %7d %8s'
              % (rule, c['records'], c['edge slots named'], c['unresolved'],
                 ('%+.3f' % cc) if cc is not None else '     -'))
    print('%-36s %9d %9d %7d' % ('TOTAL', tot['records'], tot['edge slots named'],
                                 tot['unresolved']))

    print()
    print('per-slot control, worst 8 of those with 200+ observations:')
    rows = []
    for (f, s), v in slotvals.items():
        cc = corr(v)
        if cc is not None and len(v) >= 200:
            rows.append((cc, FILTERS.get(f) or 'fid %d' % f, s, len(v)))
    rows.sort()
    for cc, name, s, n in rows[:8]:
        print('   %-18s slot %-2d  n=%-7d corr %+.3f%s'
              % (name, s, n, cc, '   <-- NOT AN EDGE' if cc < 0.9 else ''))
    print('   (%d slot populations checked; %d correlate above 0.9)'
          % (len(rows), sum(1 for r in rows if r[0] > 0.9)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
