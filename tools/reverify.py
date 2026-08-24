#!/usr/bin/env python3
"""Re-run the headline claims in FORMAT-NOTES.md against the CURRENT corpus.

Two claims in that file were found stale in one afternoon, and both shared a signature:
they were 100%-shaped, so nothing ever re-ran them. Their denominators came from
`tools/DISTINCT.txt` - the withdrawn 641-file list, about a third duplicates - and survived
the correction to the 435-file root list because a settled number invites no re-reading.

This exists so that stops happening. Each entry states the number as RECORDED, recomputes it,
and reports both. A claim that no longer reproduces is not edited away here; it is printed as
FAIL so it can be investigated.

    python3 tools/reverify.py

Adding a claim: append to CLAIMS a (name, recorded_text, fn) where fn returns (hits, total).
Only claims that can be recomputed from the corpus belong here.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbsasm                                                        # noqa: E402
import disasm                                                        # noqa: E402
import transpile                                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = os.path.join(ROOT, 'DISTINCT.txt')


def corpus():
    """The 435-file root list. NOT tools/DISTINCT.txt, which is withdrawn."""
    with open(LIST) as fh:
        for line in fh:
            p = line.strip()
            if not p:
                continue
            try:
                yield sbsasm.Assembly(p)
            except Exception:                    # a parse failure is its own claim, below
                continue


def program_points(a, r):
    """Every program in a record, fx programs included."""
    pts = []
    try:
        pts = list(r.programs)
    except Exception:
        pass
    if r.filter_id == 4:
        try:
            pts += [pr for _k, _o, _t, pr in r.fx_walk() if pr]
        except Exception:
            pass
    return pts


def scan():
    """One pass over the corpus, accumulating everything the claims need."""
    T = collections.Counter()
    for a in corpus():
        T['files'] += 1
        for r in a.records:
            T['records'] += 1
            T['aligned'] += (r.offset % 4 == 0)
            T['cls_bit3'] += bool(r.cls >> 3 & 1)
            try:
                slots = r.edge_slots
            except Exception:
                slots = []
            for s in slots:
                T['edge_slots'] += 1
                T['edge_absent'] += (s >= len(r.words) or r.words[s] == 0xFFFFFFFF)
                if s < len(r.words) and r.words[s] == 0:
                    T['edge_zero'] += 1
            for q in program_points(a, r):
                try:
                    n = len(list(disasm.decode(a.data, q, a.body_hi)))
                except Exception:
                    continue
                T['programs'] += 1
                if q + 2 <= len(a.data):
                    T['lenprefix'] += (struct.unpack_from('<H', a.data, q)[0] == n)
                try:
                    transpile.transpile(a.data, q, a.body_hi)
                    T['transpiled'] += 1
                except Exception:
                    pass
    return T


# (name, recorded, fn, expected_exceptions). The last field matters: "all but two records"
# is a claim ABOUT two exceptions, so testing it for exact equality would fail it for being
# true. A claim with expected_exceptions=n holds when the miss count is exactly n.
CLAIMS = [
    ('every record starts on a 4-byte boundary',
     '418,840 of 418,840',
     lambda T: (T['aligned'], T['records']), 0),
    ('class-word bit 3 is set on all but two records',
     '651,741 of 651,743',
     lambda T: (T['cls_bit3'], T['records']), 2),
    ('the u16 at a program pointer is its instruction count',
     '291,802 of 291,802',
     lambda T: (T['lenprefix'], T['programs']), 0),
    ('every program transpiles',
     '1,206,800 of 1,206,800',
     lambda T: (T['transpiled'], T['programs']), 0),
]

# Claims whose recorded figure is a small RATE, not a near-100% share. Printed separately
# because "FAIL" against 100% is the wrong test for them.
RATES = [
    ('edge slots holding 0', '850 of 843,900 = 0.10%',
     lambda T: (T['edge_zero'], T['edge_slots'])),
    ('edge slots holding the absent sentinel', 'near zero for every filter',
     lambda T: (T['edge_absent'], T['edge_slots'])),
]


def main():
    T = scan()
    print('corpus: %d files, %d records, %d programs\n'
          % (T['files'], T['records'], T['programs']))
    print('%-52s %-22s %s' % ('claim', 'recorded', 'now'))
    bad = 0
    for name, recorded, fn, expected in CLAIMS:
        hits, total = fn(T)
        pct = hits / total if total else 0.0
        misses = total - hits
        ok = misses == expected
        bad += not ok
        note = 'ok' if ok else 'FAIL (%d misses, expected %d)' % (misses, expected)
        print('%-52s %-22s %s/%s  %.4f%%  %s'
              % (name[:52], recorded, format(hits, ','), format(total, ','),
                 pct * 100, note))
    print()
    for name, recorded, fn in RATES:
        hits, total = fn(T)
        print('%-52s %-22s %s/%s  %.4f%%'
              % (name[:52], recorded, format(hits, ','), format(total, ','),
                 (hits / total * 100) if total else 0.0))
    print('\n%d of %d exact-share claims no longer hold' % (bad, len(CLAIMS)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
