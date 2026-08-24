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


def header_sizes(paths):
    """(filter, cls, masked slot 1) -> header length in words.

    The header size is not something a reader has to discover: the layout descriptor
    states it, the same key that states the slot roles. For any record carrying an inline
    program the header end is directly observable -- it is where that program starts --
    and over 928,922 such records the descriptor predicts it at **98.44%**, holding at
    98.75% among keys with 100+ records, so it is not a small-sample effect.

    That matters because the alternative was a hard cap of 11 slots, which hid real
    parameter slots (a program at slot 17), while widening it claimed bytecode as
    parameters (96.5% of what it added). Neither was necessary: the boundary was stated
    all along.
    """
    obs = collections.defaultdict(collections.Counter)
    files = collections.defaultdict(set)
    for i, p in enumerate(paths):
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if len(r.words) < 2:
                continue
            # NOT `r.programs`: that reads layouts.json, which is the file this script
            # writes, so the derivation was seeded by its own previous output and the
            # table was a fixed point of its own history rather than a function of the
            # corpus. Blinding the model to it moved 29 of 842 keys and 94 header sizes.
            # A record's inline programs are observable without any table: a slot whose
            # +52 target is a decodable program lying inside this same record.
            inline = [r.words[s] + 52 for s in range(1, len(r.words))
                      if r.offset <= r.words[s] + 52 < r.end
                      and a.program_span(r.words[s] + 52, r.end)]
            if not inline:
                continue
            k = (r.filter_id, r.cls, r.words[1] & LAYOUT_MASK.get(r.filter_id, 0))
            obs[k][(min(inline) - r.offset) // 4] += 1
            files[k].add(i)
    out = {}
    for k, c in obs.items():
        n = sum(c.values())
        h, m = c.most_common(1)[0]
        if n >= MIN and len(files[k]) >= 3 and m / n >= 0.95:
            out[k] = h
    return out


def derive(paths, headers=None):
    headers = headers or {}
    role = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    targets = collections.defaultdict(lambda: collections.defaultdict(set))
    seen = collections.Counter()
    files = collections.defaultdict(set)
    for fi, p in enumerate(paths):
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
            files[k].add(fi)
            # Bounded by the header, which the descriptor states. Falls back to the
            # old cap of 11 only for keys with no observable header size -- that cap is
            # arbitrary and both hides real slots and, if widened blindly, claims bytecode.
            # Capped at 32 slots even when a larger header is observed. Two keys have a
            # record whose inline program genuinely starts thousands of words in --
            # pixelprocessor (20,185,8) has ~11,634-word records with the program at word
            # 11,434 -- but what lies between is a data blob, not 11,432 layout slots. The
            # derive duly invented 1,200 parameter slots for it. A header that large is
            # not a layout, whatever the program's position says.
            hi = min(headers.get(k, 12), 32)
            for sl in range(1, max(hi, 2)):
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
                # NOT counted here: a program starting AT the slot. `Record.size_or_baked`
                # does try that reading, and it is right there -- one named slot, tried
                # only after the pointer and float readings fail, with 2 slots in
                # 1,037,401 satisfying both. Applied to EVERY slot here it is a different
                # test entirely: slots past the header lie inside the record's bytecode,
                # where positions that decode are everywhere, and it claimed 955,857
                # parameter readings including slot 6 of blend across 129,610 records.
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
        # Both guards, not just the record count. `header_sizes` has required three
        # distinct specimens all along; `derive` did not, so a key resting entirely on
        # near-duplicate files could reach MIN=20 on what is really one observation.
        # That is the standing rule from "Corpus integrity", applied to this table:
        # 49 shipped keys rest on fewer than 3 specimens, 19 of them on exactly one.
        if seen[k] < MIN or len(files[k]) < 3:
            continue
        edges, progs = [], []
        for sl, c in slots.items():
            t = sum(c.values())
            if c['X'] / t > 0.05:
                continue                  # not present often enough to be part of the layout
            if c['E'] / t > 0.9 and (len(targets[k][sl]) > 0.05 * t
                                     or len(targets[k][sl]) >= 5):
                # The diversity guard applies HERE too, not only to the resizing-filter
                # branch below. A slot holding a constant small integer that happens to
                # name a same-resolution record passes the resolution test at 100% with
                # zero diversity: directionalwarp key (12,1032,10) has slot 1 = 10 in all
                # 480 of its records, and record 10 is a directionalwarp, so every one
                # scored as a valid edge -- including record 10 pointing at itself.
                #
                # The absolute alternative matters: a SHARED input has low diversity as a
                # ratio but many distinct targets. Key (12,2073,10) has slot 1 with 1
                # distinct target (a constant) and slot 3 with 138 over 4,855 records
                # (diversity 0.028) -- the ratio alone would discard both, and slot 3 is a
                # real edge to a shared control map.
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
        out['%d,%d,%d' % k] = [edges, progs, seen[k], headers.get(k, 0)]
    return out


if __name__ == '__main__':
    paths = [l.strip() for l in open(sys.argv[1] if len(sys.argv) > 1 else 'DISTINCT.txt')
             if l.strip()]
    json.dump(derive(paths, header_sizes(paths)), sys.stdout, indent=0, sort_keys=True)
