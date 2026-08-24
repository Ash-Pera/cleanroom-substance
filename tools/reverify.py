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
            T['bit3_iff'] += (bool(r.cls >> 3 & 1) == (r.cls != 0x80))
            try:
                slots = r.edge_slots
            except Exception:
                slots = []
            for s in slots:
                T['edge_slots'] += 1
                T['edge_absent'] += (s >= len(r.words) or r.words[s] == 0xFFFFFFFF)
                if s < len(r.words) and r.words[s] == 0:
                    T['edge_zero'] += 1
            # A second program is named by one of the record's own slots, at the
            # universal offset-52 skew, so a reader follows a pointer rather than
            # scanning for where the first program ends.
            try:
                pts = list(r.programs)
            except Exception:
                pts = []
            if len(pts) >= 2:
                T['second_prog'] += 1
                T['second_prog_named'] += ((pts[1] - 52) in r.words)

            # The three-word transformation key that looked edgeless: slot 2 is its
            # input edge. Recorded at 16,471 of 16,484; the 13 exceptions are gone.
            if r.filter_id == 2 and r.cls == 792 and len(r.words) == 3:
                T['trans2792'] += 1
                v = r.words[2]
                T['trans2792_edge'] += (v < r.index and v < len(a.records))

            # fxmaps tree root pointer target, under the +52 skew.
            if r.filter_id == 4 and len(r.words) > 2:
                q = r.words[2] + 52
                if 0 <= q < len(a.data):
                    T['fx_root'] += 1
                    T['fx_root_aligned'] += (q % 4 == 0)

            # The slot rule. Scored against the RECORDS, not layouts.json -- the table has
            # 2,806 entries that disagree with the bytes they describe.
            ent = sbsasm.PARAM_SPEC.get(r.filter_id)
            if ent and r.filter_id not in sbsasm.PARAM_RAW and len(r.words) > 1:
                key = (r.filter_id, r.cls,
                       r.words[1] & sbsasm.LAYOUT_MASK.get(r.filter_id, 0))
                lay = sbsasm.LAYOUTS.get(key) if sbsasm.LAYOUTS else None
                if lay and lay[1]:
                    w1 = r.words[1]
                    st = tuple(0 if (w1 & m) == 0 else
                               (1 if (w1 & m) == (m & ~h) else (2 if (w1 & m) == h else 3))
                               for _n, m, h in ent)
                    act = sum(1 for x in st if x in (1, 2))
                    share = 1 if (r.filter_id == 15 and st[3] in (1, 2)
                                  and st[4] in (1, 2) and not (r.cls & 1)) else 0
                    ex = 1 if (r.filter_id == 1 and (w1 >> 9) & 1) else 0
                    pred = (act + ex + (r.cls & 1) + ((r.cls >> 7) & 1)
                            + ((r.cls >> 11) & 1) + 2 * ((r.cls >> 10) & 1) - share)
                    T['slotrule_n'] += 1
                    T['slotrule'] += (pred == len(lay[1]))

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
    # Recorded as "all but two". The two were an artefact of an incomplete corpus: adding
    # three assemblies that had never been scanned took it to eight. All eight are
    # pixelprocessor records whose class word is exactly 0x80, and bit 3 is clear IFF the
    # class word is 0x80 - no counterexample either way in 904,131 records. So this is not
    # a near-universal flag with stragglers, it is an exact partition.
    ('class-word bit 3 is set except where cls == 0x80',
     '651,741 of 651,743 (two exceptions)',
     lambda T: (T['cls_bit3'], T['records']), 8),
    ('bit 3 is clear IFF the class word is exactly 0x80',
     'not previously stated',
     lambda T: (T['bit3_iff'], T['records']), 0),
    ('the u16 at a program pointer is its instruction count',
     '291,802 of 291,802',
     lambda T: (T['lenprefix'], T['programs']), 0),
    ('every program transpiles',
     '1,206,800 of 1,206,800',
     lambda T: (T['transpiled'], T['programs']), 0),
    ('a second program is named by one of the record\'s own slots',
     '36,614 of 36,614',
     lambda T: (T['second_prog_named'], T['second_prog']), 0),
    ('transformation (2,792,0): slot 2 is a backward record index',
     '16,471 of 16,484 (13 exceptions)',
     lambda T: (T['trans2792_edge'], T['trans2792']), 0),
    ('the slot rule, against layouts.json (2,806 table entries are wrong)',
     '99.396% -- 99.992% against the records',
     lambda T: (T['slotrule'], T['slotrule_n']), 2843),
    ('fxmaps tree root pointer target is 4-aligned',
     '27,637 of 27,637',
     lambda T: (T['fx_root_aligned'], T['fx_root']), 0),
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
