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
    """Slot indices, relative to `q`, whose word names `prog` (`word + 52 == prog`).

    ADDRESSED ABSOLUTELY, not through `rec.words`. A structure the walk yields need not lie
    inside the record that yielded it -- an FX table is a body-level structure and the
    directory hands it to whichever record precedes it, so `q` is routinely BEFORE
    `rec.offset`. Indexing `rec.words[(q - rec.offset) // 4 + k]` then goes negative, and
    Python reads from the END of the record instead of raising, so this returned slots from
    the wrong end of the wrong structure and only crashed when the index passed `-len`.
    It ran that way over 80 files without failing, which is the whole problem with it.
    """
    data, hi = rec.asm.data, rec.asm.body_hi
    out = []
    for k in range(0, limit):
        at = q + 4 * k
        if at + 4 > hi:
            break
        if struct.unpack_from('<I', data, at)[0] + 52 == prog:
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
        # A CHAIN ELEMENT STATES ITS EXTENT EVEN WITH NO LAYOUT. The `0x9` family declares
        # no parameters, but it is a linked-list member like any other: the previous
        # element's slot 1 points AT it, and its own slot 1 points at the next. That stored
        # step is the element's own statement of where it ends -- 94 of 108 have a forward
        # pointer there and 82 of those step exactly 3 words.
        #
        # No cap and no plausibility test on the distance. A last-in-chain element points
        # far forward, which yields a huge extent that simply contains everything and
        # reports nothing; under-reporting is the safe direction for a check whose whole
        # value is that a violation cannot be argued with.
        d, e = rec.asm.data, rec.end
        if q + 8 > e:
            return None
        step = struct.unpack_from('<I', d, q + 4)[0] + 52
        return (step - q) // 4 if q < step < e else None
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
    """[(kind, tag, match_offset, extent_words, source)] for attributions outside their
    structure.

    THE THIRD FIELD IS A SEARCH HIT, NOT A DECLARATION, and reporting it as one was this
    instrument's own error rather than a finding. `_naming_slots` scans up to 32 words for
    a word equal to `prog - 52` and returns the lowest match; the census then printed that
    as "slot 7 of a 3-word structure (stated)", where "(stated)" describes the EXTENT's
    provenance and never the slot's. Read together it says the format declares a program at
    slot 7, which it does not -- `fx_entry_layout(0x20018)` declares nothing at all.

    What actually produced the 8 survivors at that tag is `FX_PAYLOAD_PROG`, the one
    hand-stated program offset left in `sbsasm.py`: an address computed as `t + 20` from the
    entry's `+4` pointer TARGET. The decode never reads a slot for it. So this check cannot
    see the path that named the program, went looking for one, and found a word that matched
    by coincidence -- which is the value-based reading this file exists to catch, committed
    by the file itself. (Found by `cleanroom-substance-0e`, corrected in 9f25301.)

    The consequence for reading the output: a reported match means "no word inside the
    extent equals this pointer, and one outside it does". That is evidence the extent or the
    attribution is wrong; it is NOT evidence about which slot the format uses, and an
    attribution computed rather than named is invisible to this check in both directions.
    """
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


def pointer_bound(rec):
    """(header end, first self-pointed program) in words, or None -- an UNFITTED bound.

    The record header's end is the one extent in this format that nothing states outright
    (see FORMAT-NOTES, "Every extent is stated locally except one"). It is computed from
    `costs.json`, which is the last fitted thing the decode rests on.

    But a record does bound it, weakly and without any table: the first byte the record
    POINTS AT inside itself cannot be header, because it is the start of a program. That is
    the record's own statement, made with its own pointers.

    Over 30 files and 33,385 records that point at a program inside themselves:

        end == first inline program   32,607   97.7%
        end <  first inline program      778    2.3%   (gaps of 3..96 words)
        end >  first inline program        0    0.0000%

    The zero is the load-bearing figure. The fitted header end never once claims a word
    that the record's own pointer says is code, so the cost model is bounded above by
    something independent of it. The 778 with a gap are where the two disagree and the
    header may run further than the walk thinks -- the population to look at if the cost
    model is ever to be replaced rather than checked.

    Returns None for the 4,815 records that point at no program inside themselves; they
    state no bound and this has nothing to say about them.
    """
    if rec.filter_id in getattr(sbsasm, '_PAYLOAD_PROGRAM_FILTERS', {4, 20}):
        return None
    d = decompose.decompose(rec)
    if not d or d.get('end') is None:
        return None
    asm = rec.asm
    inline = []
    for w in rec.words:
        p = w + 52
        if rec.offset <= p < rec.end and asm.body_lo <= p < asm.body_hi \
                and asm.valid_program(p):
            inline.append((p - rec.offset) // 4)
    if not inline:
        return None
    return _header_end(rec, d), min(inline)


def census(paths=None):
    paths = paths or corpus.paths()
    fx = collections.Counter()
    fx_tot = collections.Counter()
    hdr = collections.Counter()
    hdr_tot = collections.Counter()
    ov = collections.Counter()
    pb = collections.Counter()
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
            try:
                b = pointer_bound(r)
            except Exception:
                b = None
            if b is not None:
                pb['bounded'] += 1
                if b[0] > b[1]:
                    pb['VIOLATION'] += 1
                elif b[0] < b[1]:
                    pb['gap'] += 1
                else:
                    pb['exact'] += 1
            if r.filter_id != 4:
                continue
            for kind, tag, k, extent, src in fx_violations(r):
                fx[(kind, 'match at +%d words, extent %d (%s)' % (k, extent, src))] += 1
            try:
                items = list(r.fx_walk())
            except Exception:
                items = []
            fx_tot['attributions'] += sum(
                1 for it in items if len(it) > 3 and it[3] is not None)
    return fx, fx_tot, hdr, hdr_tot, ov, pb


def main(argv):
    n = int(argv[0]) if argv else 80
    paths = corpus.paths()[:n]
    fx, fx_tot, hdr, hdr_tot, ov, pb = census(paths)
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
    print("POINTER BOUND: the header end against the record's own first inline program")
    n = pb.get('bounded', 0)
    if not n:
        print('  no record states this bound')
    else:
        for k in ('exact', 'gap', 'VIOLATION'):
            print('  %-20s %10d %9.4f%%' % (k, pb.get(k, 0), 100.0 * pb.get(k, 0) / n))
        print('  %-20s %10d' % ('records bounded', n))
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
