#!/usr/bin/env python3
"""Derive the record layout table that `sbsasm.py` reads.

The engine does not probe: a record's layout is stated by its tag, its class word and
the layout bits of its parameter word. This derives the (filter, class, masked slot 1)
-> (edge slots, program slots) map from a corpus, so the segmenter can look it up
instead of guessing.

    python3 tools/derive_layouts.py > tools/layouts.json

A slot is called an edge when its target is a backward record sharing the record's
resolution. The parameter slot is the one holding *either* a decodable program or a
plausible float32 - the tagged union documented in FORMAT-NOTES.md - since a record
whose parameter is a baked constant has no program there at all. Requiring a program
alone loses every constant-valued record, which cost 70,000 of them on the first try.

Zero counts as a float. It is the default of `levelinlow`, of every offset and of the
matrix off-diagonals, so a slot whose value is legitimately 0.0 in a fifth of records
fails a 90% float test and vanishes from the table - which is how `levels`'s
`levelouthigh` stayed hidden in 36,818 records. Because padding also reads zero, a slot
is claimed only when zero is the minority reading.

Keys seen fewer than `MIN` times are dropped rather than guessed at.
"""
import collections
import json
import math
import struct
import sys

from sbsasm import Assembly, LAYOUT_MASK

MIN = 20


def derive(paths):
    role = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    targets = collections.defaultdict(lambda: collections.defaultdict(set))
    seen = collections.Counter()
    for p in paths:
        try:
            a = Assembly(p)
        except Exception:
            continue
        tags = {r.index: r.tag for r in a.records}
        for r in a.records:
            if len(r.words) < 2:
                continue
            k = (r.filter_id, r.cls, r.words[1] & LAYOUT_MASK.get(r.filter_id, 0))
            seen[k] += 1
            for sl in range(1, 12):
                if sl >= len(r.words):
                    # The slot does not exist in this record. That is evidence about the
                    # layout, not a record to skip: counting only the records long enough
                    # to have a slot let a slot present in 1 of 37 records be claimed as
                    # an edge for all 37, and every such claim became an unresolved edge.
                    role[k][sl]['X'] += 1
                    continue
                v = r.words[sl]
                q = v + 52
                if a.body_lo <= q < a.body_hi and a.program_span(q) is not None:
                    role[k][sl]['P'] += 1
                elif 0 < v < r.index and v in tags and (r.tag >> 8) == (tags[v] >> 8):
                    role[k][sl]['E'] += 1
                    targets[k][sl].add(v)
                elif 0 < v < r.index and v in tags:
                    # A backward reference whose target has a DIFFERENT resolution.
                    # Resolution agreement is what separates real edges from small
                    # integers, and it was right to adopt -- but it assumes an edge
                    # preserves resolution, which is false for the filters that resize.
                    # transformation agrees on resolution in only 39.5% of its backward
                    # references, so this test rejected its input edge in 16,484 records.
                    role[k][sl]['B'] += 1
                    targets[k][sl].add(v)
                elif v == 0:
                    role[k][sl]['Z'] += 1
                else:
                    f32 = struct.unpack('<f', struct.pack('<I', v))[0]
                    if math.isfinite(f32) and 1e-6 <= abs(f32) <= 1e6:
                        role[k][sl]['F'] += 1
                    else:
                        role[k][sl]['.'] += 1
    out = {}
    for k, slots in role.items():
        if seen[k] < MIN:
            continue
        edges, progs = [], []
        for sl, c in slots.items():
            t = sum(c.values())
            if c['X'] / t > 0.05:
                continue                  # not present often enough to be part of the layout
            if c['E'] / t > 0.9:
                edges.append(sl)
            elif (c['E'] + c['B']) / t > 0.9 and len(targets[k][sl]) > 0.05 * t:
                # A resizing filter's edge: almost always a backward reference, but not
                # to a same-resolution record. Value diversity is what keeps this from
                # being the small-integer trap that has caught this project seven times --
                # a packed field or a count repeats a handful of values, an edge names a
                # different record nearly every time. The 0.05 threshold is calibrated,
                # not guessed: over slots that are almost always backward references, the
                # slot-1 packed parameter words reach at most 0.025 diversity while slots
                # the table already calls edges have a 5th percentile of 0.109. 0.05 sits
                # in that gap, keeping 96.1% of known edges and admitting 0% of packed
                # words. Confirmed independently by reachability from the output table.
                edges.append(sl)
            elif c['P'] / t > 0.5:
                # A slot that is a program in the majority of a key's records is a
                # program slot even when the rest of them hold an edge instead. Requiring
                # one bucket to reach 90% classified such a slot as neither and emitted an
                # empty layout: pixelprocessor (20,137,0) is 87% program and 13% edge
                # across slots 2, 3 and 4, and lost all three.
                progs.append(sl)
            elif (c['P'] + c['F'] + c['Z']) / t > 0.9 and (c['P'] + c['F']) / t > 0.5:
                # The parameter union: a program, a float, or zero. Zero is a real
                # parameter value - it is the default of `levelinlow`, of every offset
                # and of the matrix off-diagonals - so excluding it drops genuine
                # parameter slots. It is also what padding looks like, so a slot is
                # only claimed when zero is the minority reading.
                progs.append(sl)
        edges.sort()
        progs.sort()
        # The parameter slot is the one immediately after the inputs. Requiring it to
        # hold a program at least once drops every key whose records are all constants,
        # which cost 70,000 records; the positional rule does not.
        if edges and progs:
            after = max(edges) + 1
            if after in progs:
                progs = [after] + [x for x in progs if x != after]
        out['%d,%d,%d' % k] = [edges, progs, seen[k]]
    return out


if __name__ == '__main__':
    paths = [l.strip() for l in open(sys.argv[1] if len(sys.argv) > 1 else 'DISTINCT.txt')
             if l.strip()]
    json.dump(derive(paths), sys.stdout, indent=0, sort_keys=True)
