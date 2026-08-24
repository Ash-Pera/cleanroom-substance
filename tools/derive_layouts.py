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
            for sl in range(1, min(len(r.words), 12)):
                v = r.words[sl]
                q = v + 52
                if a.body_lo <= q < a.body_hi and a.program_span(q) is not None:
                    role[k][sl]['P'] += 1
                elif 0 < v < r.index and v in tags and (r.tag >> 8) == (tags[v] >> 8):
                    role[k][sl]['E'] += 1
                else:
                    f32 = struct.unpack('<f', struct.pack('<I', v))[0]
                    if v and math.isfinite(f32) and 1e-6 <= abs(f32) <= 1e6:
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
            if c['E'] / t > 0.9:
                edges.append(sl)
            elif (c['P'] + c['F']) / t > 0.9:
                progs.append(sl)          # the parameter union: a program or a float
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
