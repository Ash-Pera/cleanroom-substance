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
import decompose                                                     # noqa: E402
import disasm                                                        # noqa: E402
import transpile                                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = os.path.join(ROOT, 'DISTINCT.txt')


def corpus():
    """The canonical corpus, through `corpus.paths`.

    This used to open the root list and hand each line straight to `Assembly`. The lines
    are RELATIVE paths, so they resolved against the working directory - and run from
    `tools/`, which is where every other tool here is run from, all but three of the 438
    failed to open. The `except Exception: continue` below swallowed it, and the header
    printed "corpus: 3 files" in a line nobody read as an error.

    So the tool whose entire purpose is to stop settled claims going stale was checking
    0.7% of the corpus, and reporting FAIL for claims whose expected exception counts are
    full-corpus numbers. Two claims read FAIL for that reason alone.

    `corpus.paths` resolves relative paths against the repository root, so the answer no
    longer depends on where the command was typed.
    """
    import corpus as _corpus
    for p in _corpus.paths():
        try:
            yield sbsasm.Assembly(p)
        except Exception:                        # a parse failure is its own claim, below
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
                # The claim is about programs a SLOT names. `Record.programs` has since
                # grown a tail scan that deliberately finds programs no slot names -- 0.78%
                # of records, added because those programs WRITE cache indices other
                # programs read. Counting them here made this claim fail at 3,854 misses
                # where 0 were expected, and 100% of those misses were tail-scan programs:
                # in-record, named by no word. That is a population change, not a
                # regression, and the fix is to measure the population the claim is about.
                second = pts[1]
                tail_found = (r.offset <= second < r.end
                              and (second - 52) not in r.words)
                if not tail_found:
                    T['second_prog'] += 1
                    T['second_prog_named'] += ((second - 52) in r.words)
                else:
                    T['second_prog_tail'] += 1

            # The three-word transformation key that looked edgeless: slot 2 is its
            # input edge. Recorded at 16,471 of 16,484; the 13 exceptions are gone.
            if r.filter_id == 2 and r.cls == 792 and len(r.words) == 3:
                T['trans2792'] += 1
                v = r.words[2]
                T['trans2792_edge'] += (v < r.index and v < len(a.records))

            # fxmaps tree root pointer target, under the +52 skew. The slot and the skew
            # both come from `Record.fx_root`, which asks the walk; this used to re-derive
            # `words[2] + 52` itself, one of four copies of that read.
            if r.filter_id == 4 and len(r.words) > 2:
                q = r.fx_root
                if q is not None and 0 <= q < len(a.data):
                    T['fx_root'] += 1
                    T['fx_root_aligned'] += (q % 4 == 0)

            # The slot rule, scored against the WALK.
            #
            # This comment used to read "Scored against the RECORDS, not layouts.json",
            # and the code under it did the opposite: it looked the record up in LAYOUTS
            # and scored `pred == len(lay[1])`, the memo's own slot list. It also ran only
            # `if lay and lay[1]`, so every record the table has no key for was skipped
            # without appearing in the denominator -- 510 of 10,618 over 14 files, and the
            # walk resolves 958 of the 959 unkeyed records in that sample. A claim that
            # drops the population the table never learned cannot detect the table going
            # stale, which is this file's entire purpose.
            #
            # The decoder stopped reading that memo for layout, edges and prog some time
            # ago; the measurement layer did not follow. Scoring against `decompose` is
            # what the comment always claimed, and it is measured over every record rather
            # than over the ones the table happens to cover.
            ent = sbsasm.PARAM_SPEC.get(r.filter_id)
            if ent and r.filter_id not in sbsasm.PARAM_RAW and len(r.words) > 1:
                _d = decompose.decompose(r)
                nslots = (len(_d['cls_slots'])
                          + sum(int(t[3]) for t in _d['param_slots'] if len(t) >= 4)
                          if _d is not None and _d.get('end') is not None else None)
                if nslots is not None:
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
                    T['slotrule'] += (pred == nslots)

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
    # Recorded as 100% and no longer true, which is what this tool exists to surface. The
    # 110 misses are one cause, not a frayed edge: the condition-less `while` programs,
    # whose trip count the transpiler REFUSES to guess. That refusal is deliberate and
    # twice-corrected in FORMAT-NOTES.md - a reading giving 100% was adopted and withdrawn
    # two separate times on evidence that turned out to be a handful of program shapes
    # repeated. So the exception count is the honest statement of the claim, and if it
    # ever moves off 110 in either direction that is worth knowing: down means the loops
    # were understood, up means something else broke.
    ('every program transpiles, bar the condition-less loops',
     '1,761,423 of 1,761,533 = 99.9938%, the 110 being condition-less `while`',
     lambda T: (T['transpiled'], T['programs']), 110),
    ('a second program is named by a slot (tail-scan programs excluded)',
     '36,614 of 36,614',
     lambda T: (T['second_prog_named'], T['second_prog']), 0),
    ('transformation (2,792,0): slot 2 is a backward record index',
     '16,471 of 16,484 (13 exceptions)',
     lambda T: (T['trans2792_edge'], T['trans2792']), 0),
    # MECHANISM CHANGED, so the recorded figure is rebased rather than reproduced. This
    # was scored against layouts.json and ran only on records the table had a key for,
    # which dropped 22,701 records (4.8%) from its own denominator without saying so. It
    # is now scored against the walk over every record. The previous figure is kept in the
    # text so the change is visible rather than silently absorbed.
    ('the slot rule, scored against the WALK over every record',
     '98.394% -- 466,152 of 473,760 (previously 99.370% against layouts.json, which '
     'silently skipped 22,701 unkeyed records)',
     lambda T: (T['slotrule'], T['slotrule_n']), 7608),
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


# How many files the corpus list currently offers. A run that loads materially fewer than
# this has not verified the claims below, whatever it prints next to them.
EXPECTED_FILES = 437   # 438 until the provenance exclusion of one specimen (2026-08-24)


def main():
    T = scan()
    print('corpus: %d files, %d records, %d programs\n'
          % (T['files'], T['records'], T['programs']))
    # Refuse to report on a corpus that quietly shrank. Every claim here is a proportion,
    # so a smaller corpus does not look wrong - it looks like slightly different
    # percentages against exception counts that are full-corpus numbers, which is how a
    # 3-file run came to print two confident FAILs. The failure mode is silence, so the
    # check has to be loud and it has to be first.
    if T['files'] < EXPECTED_FILES:
        print('REFUSING TO REPORT: loaded %d files, expected %d.' % (T['files'], EXPECTED_FILES))
        print('Nothing below would be a verification. Check that the corpus paths resolve.')
        return 2
    print('%-52s %-22s %s' % ('claim', 'recorded', 'now'))
    bad = 0
    for name, recorded, fn, expected in CLAIMS:
        hits, total = fn(T)
        pct = hits / total if total else 0.0
        misses = total - hits
        # `misses == expected` reported a claim that got BETTER as a failure: the slot
        # rule improved from 2,843 misses to 2,840 and was printed as FAIL. A check that
        # cannot tell "regressed" from "improved" makes every drift look identical, and
        # the reflex it trains is to edit the expected number until the line goes green.
        if misses <= expected:
            ok = True
            note = 'ok' if misses == expected else \
                'ok, IMPROVED (%d misses, recorded %d -- update the figure)' % (misses, expected)
        else:
            ok = False
            note = 'FAIL (%d misses, expected %d)' % (misses, expected)
        bad += not ok
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
