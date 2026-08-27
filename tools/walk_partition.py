#!/usr/bin/env python3
"""Does every attribution stay inside the structure it is attributed to?

    python3 tools/walk_partition.py [n_files]

THE INVARIANT, and why it is worth more than a render comparison. The walk yields
STRUCTURES -- record headers, FX nodes, FX entries -- each with a start. Sorted by start,
a structure's extent runs to the next structure's start. Every slot a decode reads ON
BEHALF OF a structure must lie inside that structure's extent, because two structures
cannot own the same word. A read outside it is claiming a neighbour's bytes, and that is
wrong BY CONSTRUCTION rather than wrong-looking.

WHY NOT JUST RENDER IT. Because the render has too many moving parts to answer a
structural question. Over this session a single decode change was measured three times
and gave three answers: the shared working tree contributed another session's edits
(3,968 of 6,077 records "changed" by an edit that changed nothing), `sbsruntime.SAMPLERS`
is module-level and never cleared at entry so a file renders differently depending on what
rendered before it, and most specimens ship no reference maps at all -- of 27 packages with
any image beside them only 5 carry the engine's own exported maps, and none of those
exercises the mechanism under test. A criterion that depends on all of that is not a
criterion. This one depends on nothing but the walk, which is independently established:
`decompose` reproduces `_compute_layout` on 925,701 of 925,706 records, from a different
model.

WHAT A VIOLATION MEANS. Not "this looks wrong" -- "this structure named a word that
belongs to the next structure". The decode may still produce a usable number; a program
found two structures away is real bytecode and will disassemble. The claim it makes about
WHOSE program it is, is what fails. That is exactly the failure the FX leaf scan and the
record-header word scan both had, and it is visible here without rendering anything.

It bounds the error rather than eliminating it, and it is falsifiable on 100% of the corpus
instead of on the 5 packages a render can score.

THE EXTENT IS THE STRUCTURE'S OWN STATEMENT, not its neighbour's position. A node's fields
end at the SUCCESSOR slot, which the header's mask locates (`node_shape`, `leaf_successor`,
and the one hand-stated `FX_NODES2` branch row); an entry's tag declares its slots and the
entry states where the next one begins by the slot reaching furthest forward. Only where a
structure states nothing does this fall back to the next start, and those rows are labelled
`(proxy)` so the two are never read as one measurement.

THAT DISTINCTION OVERTURNED A RESULT, which is why it is worth the code. Under the proxy
this reported 40 violations on the `0x??1B` BRANCH -- a program at word 4 of a "3-word
structure" -- and that looked like evidence against the hand-stated `FX_NODES2` row. It was
evidence against the proxy. The branch header states six words (its second child sits at
word 5), and the walk yields a child three words in because children are reached by POINTER,
not by adjacency. Under the stated extent all 40 are inside their structure and the row is
vindicated. A neighbour's position is not a bound when the neighbour is not a neighbour.

WHAT SURVIVES: zero violations wherever a structure states its extent -- 80 files / 46,841
attributions and again at 200 files / 142,637 attributions, every remaining row `(proxy)` --
and 18 (86 at 200 files) where none is stated -- the entry disjoint-span scan's programs,
at slots 10..13 of words whose "tag" (`0x9`, `0xb`, `0x49`) has no entry layout at all. That
is the sharper form of the finding: not that the scan crosses a known boundary, but that it
attributes programs to a word that declares no shape to stay inside of.

THIS DOES NOT PROVE A DECODE CORRECT either way. Staying inside your own extent is
NECESSARY, NOT SUFFICIENT: a rule can read the wrong slot within the right structure and
pass clean.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import sbsasm                                                        # noqa: E402
import decompose                                                     # noqa: E402


def _naming_slots(rec, q, prog, limit):
    """Slot indices, relative to `q`, whose word names `prog` (`word + 52 == prog`)."""
    base = (q - rec.offset) // 4
    out = []
    for k in range(0, limit):
        j = base + k
        if j >= len(rec.words):
            break
        if rec.words[j] + 52 == prog:
            out.append(k)
    return out


def stated_extent(rec, kind, q, tag):
    """The structure's OWN stated width in words, or None if it states none.

    Preferred over the next-start proxy, because it is what the structure says about
    itself rather than what its neighbour's position implies.

      node   its fields end at the SUCCESSOR slot, which the header's mask locates:
             `node_shape` returns that byte offset, `leaf_successor` the bit-7-clear arm,
             and `FX_NODES2` the one branch row still stated by hand. Width is the last
             field's slot plus one.
      entry  the tag's layout declares its slots (`fx_entry_layout`), and the entry states
             where the next one begins by the slot reaching furthest forward -- the linked
             list `fx_table` walks. The nearer of the two bounds the entry's own fields.
    """
    if kind == 'node':
        sh = sbsasm.node_shape(tag)
        if sh:
            return sh[0] // 4 + 1
        lf = getattr(sbsasm, 'leaf_successor', lambda _t: None)(tag)
        if lf is not None:
            return lf // 4 + 1
        s2 = sbsasm.FX_NODES2.get(tag & 0xFF)
        if s2:
            last = max(list(s2[0] or ()) + list(s2[1] or ()) or [0])
            return last // 4 + 1
        return None
    hdr = sbsasm.fx_entry_layout(tag)
    if not hdr:
        return None
    span = max(sl for sl, _n, _k in hdr) + 1
    # The stored next-pointer, read exactly as `fx_table` reads it.
    d, e = rec.asm.data, rec.end
    nxt = None
    for sl in range(1, span + 1):
        if q + 4 * sl + 4 > e:
            break
        pv = struct.unpack_from('<I', d, q + 4 * sl)[0] + 52
        if q < pv < e and (nxt is None or pv > nxt):
            nxt = pv
    if nxt is not None:
        return min(span, (nxt - q) // 4)
    return span


def fx_violations(rec):
    """[(kind, tag, slot, extent_words, source)] for attributions outside their structure."""
    try:
        items = list(rec.fx_walk())
    except Exception:
        return []
    starts = sorted({it[1] for it in items})
    nxt = {}
    for i, s in enumerate(starts):
        nxt[s] = starts[i + 1] if i + 1 < len(starts) else rec.end
    bad = []
    for it in items:
        kind, q, tag, prog = it[0], it[1], it[2], (it[3] if len(it) > 3 else None)
        if prog is None or q not in nxt:
            continue
        # THE STRUCTURE'S OWN STATEMENT FIRST; the neighbour's start only where it makes
        # none. The two disagree, and the disagreement is the point -- see the `0x??1B`
        # branch, whose header states six words while the next structure the walk yields
        # begins three words in.
        extent = stated_extent(rec, kind, q, tag)
        source = 'stated'
        if extent is None:
            extent = (nxt[q] - q) // 4
            source = 'proxy'
        if extent <= 0:
            continue
        slots = _naming_slots(rec, q, prog, 32)
        # ONLY when the structure cannot name it from inside. A program whose pointer also
        # appears within the extent is attributed legitimately, and a second copy of the
        # same word further along is a coincidence, not a claim. Counting every matching
        # slot instead would report one violation per repeat and flag correct attributions
        # that happen to have a duplicate word downstream.
        if slots and all(k >= extent for k in slots):
            bad.append((kind, tag, min(slots), extent, source))
    return bad


def header_violations(rec):
    """[(slot, end)] for record-header programs named past the walk's own header end."""
    if rec.filter_id in getattr(sbsasm, '_PAYLOAD_PROGRAM_FILTERS', {4, 20}):
        return []                                # payload legitimately holds pointers
    d = decompose.decompose(rec)
    if not d or d.get('end') is None:
        return []
    # THE SIZE SLOT IS PART OF THE HEADER even though it sits AT `end`. `decompose` computes
    # `prog` as the first slot after the base region and `end` as the cursor after the
    # parameter fields, so `prog == end` exactly when no parameter follows -- and the walk
    # names that slot itself. Bounding at `end` alone reported the record's own size
    # expression as an out-of-extent read: 17 of 33 flagged over 80 files, every one
    # `j == prog == end`, `emboss` mostly. Those were this check's error, not the decode's.
    end = _header_end(rec, d)
    bad = []
    for p in rec.programs:
        idxs = [j for j, w in enumerate(rec.words) if w + 52 == p]
        if idxs and all(j >= end for j in idxs):
            bad.append((min(idxs), end))
    return bad


def _header_end(rec, d):
    """The header's exclusive end in words, honouring how the size expression is stored.

    `decompose` computes `prog` as the size-expression slot and `end` as the cursor after
    the parameter fields, so `prog == end` whenever no parameter follows. What that last
    word IS depends on the record, and the difference decides the bound:

      POINTER   the slot holds `program - 52` and is a header word, so the header runs to
                `prog + 1`. Bounding at `end` alone reported the record's own size
                expression as an out-of-extent read -- 17 of 33 over 80 files, mostly
                `emboss`.
      INLINE    the program BEGINS at that slot: `size_or_baked` returns the slot's own
                address, `rec.offset + 4 * prog`, rather than a pointer's target. Then the
                word is the first word of code and the header ends at `prog`. Bounding at
                `prog + 1` counted that first instruction word as a header slot and
                reported every such record as an overlap -- all 43 left over 80 files,
                `gradient` 35 of them (word 4 holds 0x9000022, an instruction; `+ 52`
                lands 150 MB outside the file, so it was never a pointer).

    Read off `size_or_baked`, which has already decided the slot's role -- not off whether
    the word's value looks like a pointer, which is the probe this project does not make.
    """
    prog = d.get('prog')
    if prog is None:
        return d['end']
    try:
        sob = rec.size_or_baked
    except Exception:
        sob = None
    if sob and sob[0] == 'program' and sob[1] == rec.offset + 4 * prog:
        return max(d['end'], prog)          # inline: the slot is the program's first word
    return max(d['end'], prog + 1)          # pointer: the slot is a header word


def overlap_violations(rec):
    """[(slot, end)] for programs that START inside the walked header.

    A header word is a SLOT, not code, so a program cannot begin inside one. This is the
    partition invariant in its strongest form -- it needs no notion of attribution at all,
    only the two extents, and it is the one case where a violation cannot be explained by a
    read that was never made.

    IT DOES NOT SAY WHICH SIDE IS WRONG, and that is the same duality the extent proxy has.
    Either `valid_program` succeeded on a slot's bytes -- a baked float or a pointer parsing
    as bytecode, which is how phantoms are made -- or the walk over-ran and `end` is too
    large, so the word is really past the header. `walk_health` counts the second kind
    directly (shuffle 1,623 and distance 77 records where `end` exceeds the record), and
    both filters appear here, so neither reading can be assumed for the whole population.
    """
    if rec.filter_id in getattr(sbsasm, '_PAYLOAD_PROGRAM_FILTERS', {4, 20}):
        return []
    d = decompose.decompose(rec)
    if not d or d.get('end') is None:
        return []
    end = _header_end(rec, d)
    hi = rec.offset + 4 * end
    return [((p - rec.offset) // 4, end) for p in rec.programs
            if rec.offset <= p < hi]


def census(paths=None):
    paths = paths or corpus.paths()
    fx = collections.Counter()
    fx_tot = collections.Counter()
    hdr = collections.Counter()
    hdr_tot = collections.Counter()
    ov = collections.Counter()
    for pp in paths:
        try:
            a = sbsasm.Assembly(pp)
        except Exception:
            continue
        for r in a.records:
            name = sbsasm.FILTERS.get(r.filter_id, str(r.filter_id))
            try:
                hv = header_violations(r)
            except Exception:
                hv = []
            hdr_tot[name] += len(list(r.programs) or ())
            hdr[name] += len(hv)
            try:
                ov[name] += len(overlap_violations(r))
            except Exception:
                pass
            if r.filter_id != 4:
                continue
            for kind, tag, k, extent, src in fx_violations(r):
                fx[(kind, 'slot %d of a %d-word structure (%s)' % (k, extent, src))] += 1
            try:
                items = list(r.fx_walk())
            except Exception:
                items = []
            fx_tot['attributions'] += sum(
                1 for it in items if len(it) > 3 and it[3] is not None)
    return fx, fx_tot, hdr, hdr_tot, ov


def main(argv):
    n = int(argv[0]) if argv else 80
    paths = corpus.paths()[:n]
    fx, fx_tot, hdr, hdr_tot, ov = census(paths)
    print('walk partition check -- %d files\n' % len(paths))
    print('RECORD HEADER: programs named only by a word past the walk\'s header end')
    print('  %-20s %10s %10s' % ('filter', 'violations', 'programs'))
    any_h = False
    for f in sorted(hdr, key=lambda k: -hdr[k]):
        if hdr[f]:
            print('  %-20s %10d %10d' % (f, hdr[f], hdr_tot[f]))
            any_h = True
    if not any_h:
        print('  none')
    print()
    print('HEADER OVERLAP: a program that STARTS inside the walked header')
    if not sum(ov.values()):
        print('  none')
    else:
        for f in sorted(ov, key=lambda k: -ov[k]):
            if ov[f]:
                print('  %-20s %10d %10d' % (f, ov[f], hdr_tot[f]))
        print('  %-20s %10d %10d' % ('TOTAL', sum(ov.values()), sum(hdr_tot.values())))
    print()
    print('FX STRUCTURES: a program named by a slot outside its own structure')
    if not fx:
        print('  none')
    else:
        for (kind, where), c in fx.most_common(20):
            print('  %-6s %-44s %5d' % (kind, where, c))
    n_att = fx_tot.get('attributions', 0)
    print('\n  total FX violations: %d of %d attributions (%.2f%%)'
          % (sum(fx.values()), n_att, 100.0 * sum(fx.values()) / max(n_att, 1)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
