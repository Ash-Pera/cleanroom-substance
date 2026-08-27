#!/usr/bin/env python3
"""Derive the fx-tree node size legend, by the WALK's landing test.

A node cell is `[tag][fields]` -- the same `[mask][fields...]` primitive as a record
header, at the tree scale (see walk.py). This census derives the per-kind size legend
that `walk.NODE_LEGEND` states and `walk.walk_node()` reads.

MIGRATED FROM THE GAP INSTRUMENT. This census used to size a cell by the distance to the
next inline program, then fit a size law by least squares over the tag bits. Both halves
are retired, and the reason is the same one twice: the gap does not measure a cell.

    The gap runs from a cell to the next PROGRAM, so a cell followed immediately by
    another cell reads as the sum of the run.

Every "underdetermined" kind was that artefact, and reading the bytes shows it plainly:

    0000401b 00003039 0000825c | 0000018b 0000825c 000084f4     gap says 6, is 3 + 3
    00000009 003ad76c 003ad7e4 | 00020008 003ad774                   "     5, is 3 + 2

The first is a 0x1b node followed by a 0x8b node -- the commonest node in the corpus,
sitting in the same run. The second is a 0x09 node followed by a chain cell. The gap was
not noisy about these, it was CONFIDENTLY WRONG: 100% modal at 6 and 68% modal at 42.
A high modal agreement measures how regularly cells are packed, not where one ends.

The least-squares bit fit inherited that. It was fed gap sizes, and its two headline
"exact 100.00%" kinds (0x48, 0x58) were not node kinds at all -- they are paramset TABLE
ENTRIES, whose lengths belong to `fx_entry_layout`. That category error is described in
walk.py; this file no longer fits anything, so it cannot re-introduce it.

THE INSTRUMENT NOW: a cell of size `s` is admissible when the word at `+s` BEGINS A
STRUCTURE in >=99% of that kind's cells -- the next tag (low nibble 8, 9 or 0xB), a chain,
or the run ends there (a program starts, or the record does). It consults no legend, so
using it to check `walk.NODE_LEGEND` is not circular.

One clause had to come OUT of that test to make it sound. The landing test in
`walk.validate_nodes` also accepted "the word is a valid program pointer (value + 52
resolves)", and that is precisely what a node's own POINTER FIELDS look like -- so every
pointer-bearing kind landed spuriously wherever it happened to carry a pointer:

    kind      admissible with the pointer clause      without it     legend
    0x8b                  1, 3                             3            3
    0x89                  1, 4                             4            4
    0x99                  2, 5                             5            5
    0x9b                  2, 4                             4            4
    0xab               1, 2, 4                             4            4
    0xdb               2, 5, 10                          5, 10          5

The clause is redundant as well as harmful: a cell followed by a program already lands via
`off == s`. Dropping it makes the reading unique for eleven of twelve kinds.

RESULT. The strict test reproduces all nine legend entries exactly, with no disagreement,
and determines four kinds the gap left underdetermined:

    0x1b = 3    0x09 = 3    0x4b = 3    0x49 = 3

Sizes above the chosen one that also land are runs of contiguous cells (0xdb admits 10 =
two 5-word cells). Size 1 is the one residual false positive, and it has a named cause
rather than a statistical one: `0x401b`'s second word is 0x00003039 -- decimal 12345, a
constant -- which passes the nibble test by coincidence. It is excluded because the
pointer maps below show every node kind carries at least one field after its tag, so a
one-word node is contradicted by that kind's own evidence.

Pointer layout still comes for free, and is unchanged: probing each 4-byte offset of a
cell for "value + 52 is a valid program" gives per-tag pointer maps with rates of 100% or
~0%, nothing between:

    0x00000089   size 4w   pointer at +4
    0x0000018b   size 3w   pointer at +4
    0x0011520248 size 7w   pointers at +12 +16 +20 +24

Run it to derive the legend and check it against the one walk.py states:

    python3 tools/node_census.py
"""
import collections
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import walk                                                          # noqa: E402
from sbsasm import Assembly                                          # noqa: E402

# Candidate sizes to score, in words. Nothing observed approaches this; it bounds the
# scan, it does not bound a node.
MAX_WORDS = 16

# A kind needs this many cells before a size derived for it is reported as determined.
# 0x49 sits at 11 and is reported as thin rather than silently promoted.
MIN_CELLS = 20

# The share of a kind's cells whose landing must agree. The readings are bimodal -- 100%
# or near zero, nothing between -- so this threshold is a formality, not a tuned cut.
AGREE = 0.99


# The CHAIN family: tags whose high 16 bits are 0x0002 are linked lists, not fixed-size
# nodes, so their harvested "sizes" are run lengths and must be kept out of the legend.
# 0x00020008 (the levels appendix) was the first found; 0x00020018 is another, and measured
# as a family the split is clean -- 8,794 of 8,811 cells with hi16==0x0002 are
# non-deterministic against 0% for any other high-half value.
#
# The SAME tag word is not a chain everywhere: reached as a paramset TABLE entry (via
# FX_ENTRY) 0x00020018 is a deterministic stride-16 entry in 72 of 72. The role is the
# context -- harvested here by inter-program gaps it is a chain cell; addressed as a table
# entry it is a fixed entry. This exclusion is for the NODE harvest only and must not be
# carried into the entry tables, where it would discard a 72/72 reading.
is_chain = walk._is_chain


# The node nibbles. fx_table's discriminator is the tag's low nibble: 8 is a paramset TABLE
# ENTRY, whose length is `fx_entry_layout`'s to state, and a node is 9 or 0xB -- or 3.
#
# THE 3 WAS MISSING, and this census found it by disagreeing with itself. `walk.NODE_LEGEND`
# has always carried a row for kind 0xa3, whose nibble is 3; the "9 or 0xB" rule stated in
# walk.py and applied here could not see it, so the derived legend came back 8 of 9 with the
# 0xa3 row unreachable rather than refuted. It is a real node: 46 cells, all of tag 0x1a3,
# all shaped `[tag][ptr][ptr][ptr]`, landing at 4 words in 100% and at no smaller size --
# which is exactly what NODE_LEGEND already said. The legend was right and the rule was
# short one case, so the rule is what changed.
#
# Nibble 1 also occurs, in 8 cells. Eight is not enough to call it anything, and it is
# recorded here as unresolved rather than swept into the node set to make a total look
# complete.
NODE_NIBBLES = frozenset({3, 9, 0xB})


def is_node_tag(tag):
    """Nodes only -- see NODE_NIBBLES. Entries (nibble 8) and chains are not nodes."""
    return (tag & 0xF) in NODE_NIBBLES and not is_chain(tag)


def lands(a, off, span_end, rec_end):
    """Does a cell ending at `off` end on a real structure boundary?

    The next word must BEGIN something: a tag (an entry's nibble 8, or a node's -- see
    NODE_NIBBLES), a chain cell, or the cell run ends here because a program starts
    (`off == span_end`) or the record does.

    Deliberately NOT accepted: "the word is a valid program pointer". That clause is what
    a node's own pointer fields look like from outside, and it made every pointer-bearing
    kind admit a spurious short size (see the module docstring). It is redundant too --
    a cell followed by a program lands on `off == span_end` already.

    The `> 0xFF` guard rejects small integers posing as tags. It applies looking FORWARD
    only: 0x89 and 0x99 are genuine node tags whose whole word is under 0xFF, and applying
    this guard to a cell's own tag would discard 28,097 real cells.
    """
    if off == span_end or off == rec_end:
        return True
    if off + 4 > rec_end:
        return False
    w = struct.unpack_from('<I', a.data, off)[0]
    if is_chain(w):
        return True
    return w > 0xFF and (w & 0xF) in (8, 3, 9, 0xB)


def harvest(files=None):
    """Walk each fx record's tree region and yield one row per cell start.

    Yields `(assembly, tag, pos, span_end, rec_end)`. The region is scanned from the tree
    root, stepping over inline programs; the gap to the next program bounds the scan but
    -- since the migration -- no longer supplies a size. This is the SINGLE harvest:
    `walk.validate_nodes` calls it rather than keeping a second copy, because two
    implementations of one walk is how the nibble-8 category error survived as long as it
    did (see `sbsasm.fx_entry_walk`'s note on the same hazard).
    """
    for p in (corpus.paths() if files is None else files):
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4 or len(r.words) < 4:
                continue
            root = r.fx_root                     # the walk's slot, not a hardcoded 2
            if root is None or not (r.offset < root < r.end):
                continue
            spans = []
            for q in r.programs:
                if root <= q < r.end:
                    try:
                        spans.append((q, a.program_end(q)))
                    except Exception:
                        pass
            spans.sort()
            pos = root
            for s, e in spans + [(r.end, r.end)]:
                pos = (pos + 3) & ~3
                if pos + 8 <= s:
                    tag = struct.unpack_from('<I', a.data, pos)[0]
                    yield a, tag, pos, s, r.end
                pos = max(pos, e)


def measure(files=None, ptr_cap=4000):
    """Score every candidate size for every tag, and map each tag's program pointers.

    Returns `(admit, seen, ptr)`: `admit[tag][words]` = cells that land at that size,
    `seen[tag]` = cells, `ptr[tag][byte offset]` = cells whose word there is a program
    pointer. Pointer probing is capped per tag; the size scan is not.
    """
    admit = collections.defaultdict(collections.Counter)
    seen = collections.Counter()
    ptr = collections.defaultdict(collections.Counter)
    probed = collections.Counter()
    for a, tag, pos, s, end in harvest(files):
        seen[tag] += 1
        for w in range(1, MAX_WORDS + 1):
            if lands(a, pos + 4 * w, s, end):
                admit[tag][w] += 1
        if probed[tag] < ptr_cap:
            probed[tag] += 1
            for off in range(4, min(s - pos, 64), 4):
                v = struct.unpack_from('<I', a.data, pos + off)[0]
                q = v + 52
                if a.body_lo <= q < a.body_hi and a.valid_program(q):
                    ptr[tag][off] += 1
    return admit, seen, ptr


def derive(admit, seen):
    """{kind: (size in words, admissible sizes, tags, cells)} -- the legend, derived.

    A size is admissible when it lands in >=AGREE of the kind's cells. The chosen size is
    the smallest admissible one of at least two words: the gap direction always
    OVERSTATES (a run of contiguous cells reads as one), so among sizes that all land
    cleanly the shortest is the cell and the rest are runs. One word is excluded because
    every kind's pointer map shows at least one field after the tag.
    """
    bykind = collections.defaultdict(list)
    for tag in seen:
        if is_node_tag(tag):
            bykind[tag & 0xFF].append(tag)
    out = {}
    for kind, tags in bykind.items():
        n = sum(seen[t] for t in tags)
        ok = [w for w in range(1, MAX_WORDS + 1)
              if sum(admit[t].get(w, 0) for t in tags) / n >= AGREE]
        pick = next((w for w in ok if w >= 2), None)
        out[kind] = (pick, ok, len(tags), n)
    return out


def main():
    admit, seen, ptr = measure()
    node_cells = sum(n for t, n in seen.items() if is_node_tag(t))
    node_tags = sum(1 for t in seen if is_node_tag(t))
    print('fx cells harvested %d   node cells %d   node tags %d\n'
          % (sum(seen.values()), node_cells, node_tags))

    legend = derive(admit, seen)
    print('derived size legend, by the landing test (legend-free instrument):')
    print('   kind  tags   cells  size  admissible        walk.NODE_LEGEND')
    agree = disagree = selfsame = 0
    for kind, (pick, ok, ntags, n) in sorted(legend.items(), key=lambda kv: -kv[1][3]):
        stated = walk.NODE_LEGEND.get(kind)
        stated = stated[0] if stated else None
        if pick is None:
            verdict = 'no size lands'
        elif stated is None:
            verdict = 'NEW' + ('  (thin)' if n < MIN_CELLS else '')
        elif stated == pick:
            # A row this instrument SUPPLIED cannot also corroborate it. Counting those as
            # agreements would turn a tautology into a headline; they are named instead.
            if kind in walk.NODE_LEGEND_FROM_LANDING:
                verdict = 'agrees (this instrument supplied it -- not a check)'
                selfsame += 1
            else:
                verdict = 'agrees'
                agree += 1
        else:
            verdict = 'DISAGREES, states %d' % stated
            disagree += 1
        print('  %#04x %5d %7d %5s  %-17s %s'
              % (kind, ntags, n, pick, ','.join(str(w) for w in ok) or '-', verdict))
    print('\n  %d kinds reproduced independently (the gap derived them, the landing test'
          ' agrees), %d disagreements' % (agree, disagree))
    print('  %d further kinds stated on this instrument alone -- no second reading'
          % selfsame)

    print('\npointer maps, top tags:')
    for t, n in sorted(seen.items(), key=lambda kv: -kv[1])[:10]:
        if is_chain(t) or not n:
            continue
        m = ['+%d' % o for o, h in sorted(ptr[t].items()) if h / min(n, 4000) > 0.9]
        size = legend.get(t & 0xFF, (None,))[0] if is_node_tag(t) else None
        print('   %#012x %-9s pointers %s'
              % (t, ('size %dw' % size) if size else 'entry', ' '.join(m) or '-'))
    return 1 if disagree else 0


if __name__ == '__main__':
    sys.exit(main())
