#!/usr/bin/env python3
"""Segment and disassemble a .sbsasm.

One place for the file model, so analyses stop re-deriving it. Every table here was
measured over the 383-specimen corpus; see FORMAT-NOTES.md for the evidence behind each.

The guiding rule is **strict by default**. Where the layout of a record is known, this
module reads it; where it is not, it says so rather than guessing. Guessing is what
produced the phantom opcodes, the phantom `bool 0x1E`, and several false filter
identifications - every one of them came from a permissive walk that treated arbitrary
data as structure. `Assembly.coverage()` reports the bytes it could not explain, so a
wrong assumption shows up as a number instead of as a plausible-looking result.

    from sbsasm import Assembly
    a = Assembly(path)
    print(a.summary())
    for rec in a.records:
        print(rec.describe())
        for p in rec.programs:
            print(a.disassemble(p))
"""
import math
import struct
import standalone_parse as S
import isa
import disasm

# ---------------------------------------------------------------- filter table

FILTERS = {
    0: 'gradient', 1: 'blend', 2: 'transformation', 3: 'shuffle', 4: 'fxmaps',
    6: 'uniform', 7: 'warp', 10: 'blur', 12: 'directionalwarp', 13: 'sharpen',
    11: 'dirmotionblur', 22: 'curve',
    8: 'emboss',
    14: 'hsl', 15: 'levels', 16: 'bitmap', 17: 'text', 18: 'normal',
    20: 'pixelprocessor', 21: 'distance',
    19: 'dyngradient',
    5: 'vectorshape',
}
# `vectorshape` is a PROJECT LABEL, not a name recovered from a source file. Every other
# entry above is a name this format's own `.sbs` sources use; filter 5's is not, and
# cannot be, because the permitted vocabulary is exhausted - see PROJECT_LABELS.
PROJECT_LABELS = {5}
# Filter 11 is `dirmotionblur`, named from the permitted sources alone. It declares exactly
# two Float1 parameters and nothing else, which is filter 11's shape:
#
#     mblurangle   -0.25, 0.25, 0.75        an angle in turns, symmetric about zero
#     intensity    12.0, 13.67, 34.82       one-sided magnitudes
#
# and containment settles it: all three declared `intensity` values appear at filter 11's
# first parameter slot and at NO other filter or slot in the corpus. The three `mblurangle`
# values appear at its second slot too, alongside a few coincidental hits elsewhere - 0.25
# and 0.75 are common numbers, which is exactly why the `intensity` column is the one that
# carries the identification.
#
# This also confirms a reading left open earlier. Filter 11's second parameter was recorded
# as "angle-SHAPED but unconfirmed - none of its 25 programs divides by 2*pi, so nothing
# confirms it". It is `mblurangle`, and it is an angle.
#
# Filter 22 is `curve`, named the same way but only after separating two questions the first
# measurement ran together. Of 271 distinct declared `curve` values, just 90 appear anywhere
# in the paired compiled file - two thirds do not survive compilation, which put the apparent
# hit rate at 14% against the 98-100% the method's controls reach.
#
# Conditional on surviving, the landing is decisive:
#
#     88 of 90 surviving values land at filter 22          97.8%
#     2 at pixelprocessor, 1 each at directionalwarp, levels, blend
#
# against `transformation`'s `offset` at 94 of 96 and `matrix22` at 101 of 101. The structure
# agrees: filter 22 has one edge in 1,173 of 1,267 records and a parameter in 1,264, and
# `curve` takes one input and declares `position`, `left` and `right` as `Float2` - which is
# what its slots 6 to 11 hold, three pairs.
#
# The 14% was never evidence against the identification. It measured "does this value survive
# the cooker" and "does it land at the right filter" as one number.
# Unnamed ids, with what is known. Never rendered as a name.
UNNAMED = {9: 'legacy, version 0x20000 only'}
# Filter 5 was here as "generator, greyscale (svg?)" and is now `vectorshape` in FILTERS.
# What it does is settled: it is a generator that rasterises an embedded triangle strip,
# and `Record.vector_shape` decodes all 140 of its records. What is NOT settled is what
# the format calls it. The 140 permitted paired sources declare exactly 24 filter names,
# and all 24 are already accounted for by the 21 named ids (with `grayscaleconversion`
# and `valueprocessor` as aliases of `shuffle` and `pixelprocessor`, and `passthrough`
# culled). Filter 5 appears in 0 of those 140 files. So no permitted source can name it,
# and the label above is descriptive - chosen here, and marked as such.
# Filter 8 was here as "two inputs, greyscale control (emboss?)" and is now `emboss`,
# named by containment against the one permitted source that declares an emboss node.
#
# `Hard-Science-Old__CrustyLava` declares exactly one, with intensity = 1.91999996 and
# lightangle = 0.560000002, and its binary holds exactly one filter-8 record, whose two
# parameter slots - 5 and 6, immediately after the program slot the layout names - hold
# those two values in that order.
#
#     records in the corpus carrying BOTH values          1 of 904,131
#     ...and they are adjacent, at slots 5 and 6          the same record
#
# One observation, so the control is what carries it: no other record anywhere holds the
# pair. `lightangle` alone is worthless here (0.56 lands 270 times corpus-wide); it is the
# co-occurrence that discriminates.
#
# Corroborated three ways. By ELIMINATION: of the source filter names never mapped to a
# filter id, `grayscaleconversion` is `shuffle` with luminance weights, `valueprocessor`
# compiles to `pixelprocessor`, and `passthrough` is culled - leaving `emboss` as the only
# unmapped name. By COUNT: emboss = 1 and filter 8 = 1 in that specimen. By ARITY: filter 8
# takes two image inputs, and they are asymmetric in the way an emboss is - slot 2 carries
# the record's own channel mode in 546 of 546, slot 3's target is grayscale in 546 of 546.
# It preserves resolution (1,090 of 1,092) and feeds `blend` in 482 of 521 uses.
# 19 was here and is now `dyngradient` in FILTERS. An id in both tables is read as known
# by `Record.known` and as unknown by `describe()`, so the stale entry was a live
# contradiction rather than a harmless leftover.

# Data edges: slots whose targets are used once each (refs/target ~= 1).
# Derived by measuring, per filter, the rate at which a slot holds a valid backward
# record index - EXCLUDING slot 1 wherever slot 1 is a parameter word, because a small
# packed integer passes the "valid backward index" test trivially. That conflation is
# what produced the shared-reference error; see FORMAT-NOTES.md.
EDGES = {0: [1], 1: [2, 3], 2: [2], 3: [2, 3], 7: [1, 2], 8: [2, 3], 9: [2, 3], 10: [1],
         11: [2], 12: [2, 3], 13: [1], 14: [1], 15: [2], 18: [2], 19: [1],
         21: [2], 22: [1]}
# Filter 9 had no entry, so `Record.edges` returned [] for it while slots 2 and 3 plainly
# held backward record indices -- its inputs were simply unread, not absent. It is the
# corpus's rarest filter (5 records in 4 files, all version 0x20000) so the n >= 200
# correlation control cannot be run on it; what CAN be shown at n=5 is reported instead:
#
#   slots holding a valid backward index in all 5 records      1, 2, 3
#   slot 1 refuted as an edge: it holds the constant 1 or 5, and does not track the
#     record's index -- the exact small-integer artifact the edge control exists to catch
#   slots 2 and 3 track the record's own index                 corr 0.998 and 1.000
#   distance from own index                                    1-21 records back, and one
#                                                              of the two is index-1 or -2
#                                                              in every record
#
# [2, 3] is also the layout blend, shuffle, emboss and directionalwarp already use, so this
# claims no new shape. The correlations are reported rather than relied on: n=5 against a
# published threshold of 200. What the entry rests on is 5-of-5 agreement plus slot 1
# failing the same test in the same records.

# Filters whose input list is still not fully resolved, with the residue measured over the
# corpus. **Read by no code**: this is a hand-kept register of known gaps, which means it
# goes stale silently and has to be re-measured when the edge rules change. It just did.
#
#     filter     records   edge slots   unresolved
#     fid 8          546        1,637            7
#     distance     2,277        3,838            1
#
# Two entries were removed because the gaps they named are closed, both now resolving every
# slot they claim:
#
#     shuffle    7,687 records, 11,385 slots, 0 unresolved
#         Said "takes up to 4 inputs; only slot 3 resolves reliably". Slot 1 is
#         self-discriminating and `_compute_layout` reads it directly; arity is 1 or 2, with
#         33 records having no input slot at all.
#
#     fxmaps    41,212 records, 24,423 slots, 0 unresolved
#         Said "inputs resolve only in the bit-12 layout (8.3% of its records)". The input
#         count is a 4-bit field in word 1 and bit 12 was the single case k == 6; arities 1
#         to 14 all occur. 36,047 records carry k == 0 and genuinely have no input.
#
# `bitmap` was listed here too and is not a gap: 1,345 records, 0 edge slots, no image input
# at all. That is a fact about the filter, and listing it under "not fully resolved" invited
# the opposite reading.
PARTIAL_EDGES = {21: 'distance slot 3 is a shared control map, not a data edge'}
# `emboss` was listed here on the reading that it takes three image inputs in slots 1-3.
# It takes two, in slots 2 and 3, and `_real_edges` already drops slot 1: that slot takes
# **22 distinct values across the entire corpus**, at most 7 in any one file, which is a
# packed parameter word and not a reference. 1,092 edge slots, 0 unresolved.

# Shared references: slots pointing at one record used by many (refs/target >> 1).
#
# Audited with the discriminator from "Slot 1 is two different things", which separates a
# packed parameter word (small global vocabulary, bits 6 and 7 structurally dead) from a
# real reference (many values, high bits set about half the time):
#
#     filter slot  records  distinct  max/file    bit6     bit7
#       19    2      2,225      362        28    49.26%   48.67%   reference - KEPT
#       11    1     15,109        7         6     0.00%    0.00%   bitfield  - REMOVED
#       22    2      1,273       12         6     0.00%    0.00%   bitfield  - REMOVED
#        8    1        546       22         7     0.37%   45.42%   an EDGE    - REMOVED
#
# 11 and 22 are the packed-parameter-word shape, and 11 was additionally in PARAM_WORD, so
# the same slot was claimed as both a reference and a bitfield in one file. Those two are
# what the "shared reference is a hierarchy" reading left behind after it was refuted.
#
# Filter 8 read as ambiguous on this test alone - a 22-value vocabulary says bitfield, bit 7
# at 45% says reference - and the tie is broken elsewhere in this same file: the rule in
# `_compute_layout` reads slot 1 as one of filter 8's three IMAGE INPUTS, valid backward
# indices in 538 of 546. Its high bits are set half the time because record indices in a
# large file are, which is what made it look reference-like here. `Record.edges` and
# `Record.shared_refs` were returning the same slot under two readings.
#
# That leaves one entry, consumed by nothing. It is kept rather than deleted only because
# slot 2 of `dyngradient` is a real shared reference and there is nowhere else to record it.
SHARED = {19: [2]}

# The slot holding the record's OUTPUT SIZE expression -- not a filter parameter.
#
# This slot was called "the main parameter" throughout the earlier notes. It is not one.
# 81.9% of the programs it points at read a graph input of type 8 whose declared value is
# (8, 8) -- log2 256, the output size -- and 81.3% return an int2. Evaluating them and
# comparing with the log2 dimensions the record's TAG independently carries: **434,167 of
# 435,013 agree, 99.81%**.
#
# So a record's parameters are the slots AFTER this one, and `blend`'s `opacitymult` sits
# at the first of them, which is why it kept landing at "block position 0".
#
# Measured: the slot holding a valid program pointer in the largest share of records.
PROG_SLOT = {0: 4, 1: 4, 2: 3, 4: 3, 6: 1, 7: 3, 10: 2, 11: 3, 12: 4, 13: 2, 14: 2,
             15: 3, 18: 3, 19: 3, 21: 4, 22: 4}

# Some filters emit more than one record layout, distinguished by input count.
# Candidates are tried in order and the first whose program slot validates is used;
# because the pointer/float union is unambiguous, a wrong guess cannot validate.
# Each entry is (edge slots, program slot).
ALT_LAYOUTS = {
    3: [([2, 3], 4), ([1], 2)],          # shuffle: two inputs, or one
}

# Filters whose slot 1 is a packed parameter word rather than a reference.
PARAM_WORD = {1, 2, 4, 8, 11, 12, 15, 18, 20, 21, 22}

CHANNELS = {1: 1, 2: 3, 3: 4}          # bitmap class -> channel count

# Slot 1 holds both parameter values and layout bits. These masks keep the layout bits
# and drop the rest, found by dropping any bit whose removal does not cost determinism.
# For `blend` the search independently rejected bits 0-3 - the `blendingmode` nibble -
# and kept 4, 5 and 9, which is what the layout actually varies on.
LAYOUT_MASK = {0: 0x3FFF, 1: 0x230, 2: 0x060000C0, 3: 0x06001FE0, 4: 0xE55,
               6: 0x0036FFE0, 7: 0x2FF8, 10: 0x0, 11: 0x04, 12: 0x1E, 15: 0x3FD,
               19: 0x0, 20: 0x0B, 21: 0x01}


def _load_layouts():
    """(filter, class, masked slot 1) -> (edge slots, program slots), or {} if absent.

    The same key also states the record's HEADER SIZE, in `HEADER_WORDS`. That the header
    boundary is stated rather than discovered was the missing piece behind two failed
    attempts at the parameter table: a hard cap of 11 slots hid real ones, and widening it
    claimed bytecode as parameters. For records carrying an inline program the boundary is
    directly observable, and over 928,922 of them the descriptor predicts it at 98.44% --
    98.75% among keys with 100+ records.
    """
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'layouts.json')
    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}, {}           # no table shipped: every reader falls back to probing
    except (json.JSONDecodeError, OSError):
        raise                   # a table that exists and will not load is a defect, not
                                # a reason to silently run without one. Returning {} here
                                # disables every layout lookup in the module and every
                                # count downstream drops without saying why.
    lay, hdr = {}, {}
    for k, v in raw.items():
        key = tuple(int(x) for x in k.split(','))
        lay[key] = (tuple(v[0]), tuple(v[1]))
        if len(v) > 3 and v[3]:
            hdr[key] = v[3]
    return lay, hdr


LAYOUTS, HEADER_WORDS = _load_layouts()

# Every slot any layout key registers as an EDGE slot, per filter. Used to recognise a
# record whose input count the key does not encode, where the key's program slot has been
# pushed along by extra edges.
EDGE_SLOTS = {}
for _k, _v in LAYOUTS.items():
    EDGE_SLOTS.setdefault(_k[0], set()).update(_v[0])

# FX-Map tree node shapes: header -> (offset of the next pointer, program slots).
# The tree is a singly linked list entered from record slot 2, and each node carries a
# program. 0x18B is `addnode` (exact count against source over 110 records) and its
# program returns i1 in 12,023 of 12,023; 0x89 is a conditional and its program returns
# b2 in 10,048 of 10,048. 0x1AB carries two programs. Others exist and are unidentified.
# Shapes were probed by reaching a node only as a known node's chain successor, so the
# position is validated before the shape is read. Return type is the last instruction's
# type, and it separates the roles: 0x89 alone yields a boolean, in 11,197 of 11,197
# programs; the other three yield i1, each at 100%. Physical shape does not determine
# role - 0x1CB has 0x89's layout and 0x18B's return type.
FX_NODES = {
    0x18B: (8,  (4,)),        # [header][program][next]          addnode,     -> i1
    0x89:  (12, (4,)),        # [header][program][0][next]       markov2,     -> b2
    0x1AB: (12, (4, 8)),      # [header][program][program][next]              -> i1
    0x1CB: (12, (4,)),        # [header][program][0][next]                    -> i1
}

# The FX-Map source language, mapped onto this ISA.
#
# A node's program IS its parameter's function graph -- `addnode` declares one parameter,
# `numberadded`; `markov2` declares one, `switch`. That gives IDENTIFIED pairs: an addnode
# program can only be a `numberadded` graph. Comparing multisets within a node type yields
# seven equations, from 3 elements up to 37.
#
# Pairing by SIZE instead of by type is not good enough and was tried first: it produced
# `sub -> cache_read` and `get_float2 -> const`, because two unrelated graphs of the same
# length get matched. Same permissiveness problem as everywhere else in this document.
#
# Solved from three independent axes, none of which is name similarity:
#
#   MULTISET    cancel bound pairs; when one term remains on each side they are equal.
#               Nested equations subtract: the size-5 graph minus the size-4 one is
#               `not = not`, which is the only way that binding was obtained.
#   ARITY       the source declares each node's <connection> count; the ISA gives each
#               opcode its operand count. `ifelse` has 3 and only `select` has 3.
#   RESULT TYPE the source's <type v="N"/> against the ISA type field. This is what fixes
#               `div`, whose modal type is f1 where the rest of its group is f2.
#
# Four bindings are NOT determined by any of the three: {add, sequence, set, vector2} and
# {add, seq, set, vec} tie on all of count, arity and modal type. They are assigned by the
# obvious name correspondence, and that is the one place here where a name is doing the
# work. Flagged rather than hidden.
#
# Verification: pushing every source graph through this map reproduces the compiled opcode
# multiset EXACTLY in 7 of 7 equations, including the 37-element one.
#
# `get_float1` is the interesting row. It maps to `sysvar`, not to `get` -- reading a
# named float compiles to a system-variable fetch when the name is a system variable, and
# `get_float2` maps to `get`. So the lowering depends on the ARGUMENT, not only the
# function, which is why one source name can reach two opcodes.
FX_LOWERING = {
    'const_float1': 'const',  'const_int1': 'const',   'const_float2': 'const',
    'get_float3':   'inputref', 'get_integer1': 'inputref',
    'get_bool':     'get',    'get_float2': 'get',     'get_float1': 'sysvar',
    'swizzle1':     'swizzle', 'toint1': 'cvt',        'tofloat': 'cvt',
    'ifelse':       'select', 'lr': 'lt',              'not': 'not',
    'mul':          'mul',    'div': 'div',            'mod': 'mod',
    'samplecol':    'samplecol',
    # name-fixed, see above
    'add': 'add', 'sequence': 'seq', 'set': 'set', 'vector2': 'vec',
}


# WHICH PARAMETER EACH NODE PROGRAM IS, by file-level co-occurrence against the permitted
# paired sources -- the node-chain counterpart to `FX_PARAM_BITS`.
#
# An FX-Map source names each node's TYPE (`addnode`, `markov2`, `paramset`) and a node type
# declares a fixed parameter list, so binding the header to the type binds the name. The
# comment above already asserted `0x18B` is `addnode` on an exact count over 110 records;
# this is the same claim re-derived on permitted evidence with the off-diagonal reported,
# which is what turns a count into a confusion matrix:
#
#     compiled header  vs  source node kind      files agreeing on presence/absence
#     0x18B   addnode                            8/8   (2 files also match exactly)
#     0x1AB   addnode declaring `randomseed`     8/8   (2 exact)
#     0x89    markov2                            8/8
#     0x20B   addnode with a BAKED numberadded   8/8   (1 exact)
#     every off-diagonal cell of that table      3/8 to 6/8
#
# Only 8 permitted sources contain an FX-Map, so 8/8 is a small number of files; what makes
# it evidence is that no off-diagonal cell reaches 7.
#
# `0x1AB`'s two programs are ordered by containment, not by guessing: over the four
# `ie_curve` nodes that declare both, word 1 holds every literal the source's `randomseed`
# graph declares and none of `numberadded`'s, and word 2 holds all seven of
# `numberadded`'s. 4 of 4, and the reverse assignment fails on all four.
#
# `0x20B` is the interesting row and is NOT tabulated below, because it has no program to
# name: `triDraw` is the one permitted file declaring `numberadded` as a literal rather
# than a graph, and it is the one file with a `0x20B`. So the low-nibble-B node family
# carries the same program/baked distinction in its header that the entry tags carry in
# theirs -- `0x1AB` is `0x18B | 0x20`, and that bit is `randomseed`.
#
# NOT IDENTIFIED, and left blank rather than guessed: `0x1CB` (1,858 programs, i1 100%,
# `0x18B`'s return type on `0x89`'s layout) and `0x99` (150, b2). No permitted source in
# the corpus contains either, so nothing here can name them.
#
# header -> {byte offset of the program: parameter name or None}
FX_NODE_PARAMS = {
    0x18B: {4: 'numberadded'},
    0x1AB: {4: 'randomseed', 8: 'numberadded'},
    0x89:  {4: 'switch'},
    0x1CB: {4: None},                    # unidentified -- see above
}


# A SECOND family, keyed by the header's low BYTE rather than the whole word. The two
# families are cleanly separated by how much their headers vary: each of the four above
# occurs as exactly ONE word (0x18B is 14,705 sightings and 1 distinct value), while
# these occur as many - 0x0B has 83 distinct words, 0x48 has 78 - so their upper bits
# carry per-node parameters and only the low byte names the type.
#
# The low NIBBLE says which family a chain stop belongs to, and this reframes "the
# vocabulary is open" into something much smaller. Over every chain stop in the corpus:
#
#     nibble 8   38,944   94.5%   the table handoff `fx_walk` already models
#     nibble 9/B  2,261    5.5%   genuine node types, of which these are two
#     other           5    0.0%
#
# So the open part of the FX node vocabulary is 5.5% of chain ends, not all of them.
#
# Shapes were probed the way the table above was: every word offset is a candidate, and
# every OTHER offset is its control. The target test is "does `word + 52` land on a
# header whose low nibble is 9 or B", which is the family test rather than membership of
# the four exact words - requiring the latter is what made 0x1B look like a dead end.
#
#     0x1B   372 nodes   k=2: 92%   k=5: 97%   every other offset <= 2%
#            and the two targets are DIFFERENT nodes in 343 of 343, so it BRANCHES
#            program at k=4 (92%, next best 3%)
#     0x99   150 nodes   k=4: 100%  next best 11%
#            program at k=2 (100%, every other offset 0%)
#
# NOT added, and recorded so the next attempt starts here rather than at the beginning:
# 0x0B is the largest unhandled type at 1,538 nodes and its best offset is k=4 at 31%
# against a 2% control. That is a real signal and not a shape - a 31% rule would be
# guessing for the other 69%.
#
# A CORRECTION to the probe that produced this table, which changed one of its rows.
# "Is the target a node header" was tested as "low nibble 9 or B", and a PROGRAM's first
# word has those bits often enough to fire it. Classifying each target as program-only /
# node-only / both shows where that mattered:
#
#     0x1B  k=2   node only 92%   both  0%      unaffected
#     0x1B  k=5   node only 94%   both  4%      unaffected
#     0x0B  k=4   program only 53%  both 30%    the whole signal
#
# 0x0B's "31% successor at k=4" was 30 points of bytecode. Under the disjoint predicate
# it has no successor at k=4. What it does carry is programs, and those were being lost.
#
# WITHDRAWN, the conclusion drawn from that: "it is a LEAF, and the walk ending there is
# correct rather than a gap". 0x0B has a successor and it is at word 1. The probe could
# not see it because its target test was "low nibble 9 or B", and 85.7% of 0x0B successors
# are TABLE ENTRIES, whose tag ends in nibble 8 -- the same handoff `fx_walk`'s docstring
# describes for every other chain. Over 161 0x??0B nodes reached at a validated successor
# position, word 1's target is:
#
#     entry tag   85.7%   (and all 138 have their low 16 bits in FX_TAG_LOW16)
#     node header 14.3%
#     a program    0.0%       neither  0.0%
#
# 100%, split between the two things a chain can continue into. The control is every other
# slot of the same nodes: +2 resolves to anything at all 1.2% of the time, +3 is 69.6%
# "neither", and +5 is 85.7% program-only.
#
# The code below still says `()`. Following the pointer was implemented and measured, and
# it moves NO number: entries, entry programs, node programs and records-reaching-a-table
# are identical either way, because `fx_walk` already reaches those tables through the
# record's own slot-2 path. So the claim is corrected here and the walk is left alone --
# what was wrong was the reasoning, not the output.
#
# 0x0B's program slots are not fixed and no header field predicts them (best field 68%
# against a 46.9% control), so they are SCANNED rather than tabulated - `progs=None`
# below. That is a permissive read, and it is bounded two ways: offsets 1-3 never hold
# one, and the claimed starts are pairwise DISJOINT program spans in 1,589 of 1,589
# nodes, so they are distinct programs rather than one program seen from several
# offsets, which is what a run like (5,6,7,8,9,10) would otherwise be.
FX_NODES2 = {
    0x1B: ((8, 20), (16,)),   # two children, at words 2 and 5; program at word 4
    0x99: ((16,),   (8,)),    # one successor at word 4; program at word 2
    0x0B: ((),      None),    # a leaf; programs scanned, see above
}


# Named parameter blocks: slot 1 carries one presence bit per parameter, and the
# parameters that are present are packed into consecutive slots after the header.
#
# For `levels` the presence bits are the even bits of the layout word, which is exactly
# five bits for exactly five parameters. The mapping was established by containment:
# for a record holding a value the source declares, the parameter's position in the
# block is (slot - start), and the bit naming it is the (slot - start)-th set bit. Over
# the permitted paired sources that names 107 of 111 checked reads correctly (96.4%),
# with each individual bit agreeing 92-100%.
#
# Note the order is in-low, in-high, in-mid, out-low, out-high - not the order the
# parameters are declared in a `.sbs`, and not the order they are applied in.
# For `directionalwarp` the same slot-1 field carries TWO bits per parameter, and the
# second bit is what the parameter is stored as:
#
#     bit 1  intensity, baked constant      bit 2  intensity, program
#     bit 3  warpangle, baked constant      bit 4  warpangle, program
#
# The two bits of a pair are mutually exclusive in 136,470 of 136,470 records, and only
# seven of the sixteen mask values occur (0, 2, 4, 8, 10, 12, 20); the never-seen
# combination is 18, a baked intensity beside a warpangle program.
#
# Predicting from the bits BOTH which parameters are present and whether each is a
# program or a constant is correct in 136,366 of 136,470 slot reads (99.92%). The 104
# misses all predict a program where `valid_program` declines.
#
# These occupy the LAST k slots of the block, not the first k -- which is the opposite
# of what this table's `levels` derivation assumed. For `directionalwarp` the tail
# placement is what the 99.92% above measures. For `levels` and `blend` the question is
# genuinely open: front and back differ on 20.9% of `blend` records, and the only
# parameter with enough distinctive source values to test (`opacitymult`, n=41) splits
# 32 front / 33 back, which decides nothing. They are left on front placement.
#
# `warpangle` is in TURNS, and that is not an inference from the value distribution --
# the programs that compute it end in `atan2(v) / 6.28319`, dividing by a full turn in
# 3,336 of 3,336 angle-shaped programs.

# The general form of the same field: one parameter per BIT PAIR, where the low bit says
# the parameter is a baked constant and the high bit says it is a program. A parameter is
# present when either bit is set.
#
# The two forms of a pair are mutually exclusive for `directionalwarp` (0 of 136,470
# records set both) but not for `blend`, where 10,536 records set both and the program bit
# wins. So presence is `low | high` and the kind is `high`, which covers both.
#
# For `blend` this is exact. Over every record whose last block slot is readable:
#
#     bit 4 set, bit 5 clear   140,329 slots   100.0% a baked constant in [0,1]
#     bit 5 set                 77,386 slots   100.0% a program
#
# with no exceptions in 217,715 slots. `opacitymult` really can be a function: the clean
# paired sources declare it as a `dynamicValue` 176 times against 851 constants, and for
# the self-contained graphs the counts compile through exactly - `multi_blender` 7 dynamic
# to 7 bit-5 records, `hblend` 3 to 3, `ie_curve` 14 dynamic + 1 constant to 15 + 1.
# Source-dynamic implies a bit-5 record in 25 of 25 paired files with no counterexample;
# the converse fails 24 times, which is what instancing and library dependencies predict.
#
# These parameters sit at the END of the block. Where head and tail placement disagree
# (bits fewer than slots), tail puts all 1,035 `blend` slots on floats, 100% inside [0,1],
# and head puts all 1,035 on programs.
#
# `levels` is NOT in this table. Its odd bits are not program markers: modelling them as
# pairs moves the fit between bit count and slot count from 81.40% to 82.49%, against
# 63.78% to 83.32% for `blend`. It keeps the single-bit model and head placement above,
# and the front-versus-back question stays open for it.
#
# `levels` DOES belong here, contrary to what an earlier measurement concluded. That
# measurement asked whether the number of set bits equals the number of block slots, which
# cannot separate the two models: `LAYOUT_MASK[15]` is 0x3fd, so the layout key already
# folds in the odd bits, and a block holds slots that are not parameters at all. Asking the
# right question - does the odd bit predict that the slot holds a program? - gives
# **174,329 of 174,396 (99.96%)**, and finds 2,642 `levels` programs where the single-bit
# model found 540.
#
# filter -> [(name, presence mask, program mask)]
PARAM_SPEC = {
    1:  [('opacitymult', 0x30, 0x20)],
    12: [('intensity', 0x06, 0x04), ('warpangle', 0x18, 0x10)],
    15: [('levelinlow',   0x003, 0x002), ('levelinhigh', 0x00c, 0x008),
         ('levelinmid',   0x030, 0x020), ('leveloutlow', 0x0c0, 0x080),
         ('levelouthigh', 0x300, 0x200)],
    # `dirmotionblur`, named from the permitted sources - see the FILTERS table. Its bit
    # pairs were derived mechanically before the filter had a name: 32,204 of 32,204 slot
    # kinds correct. The distributions that were recorded as suggestive and not claimed
    #   intensity   one-sided, p50 1.45, p99 36.3, max 500
    #   mblurangle  symmetric, 28.0% negative, p1 -0.125, values in multiples of 1/16
    # are what the source names say they are.
    11: [('intensity', 0x003, 0x002), ('mblurangle', 0x00c, 0x008)],
    # `fxmaps` has four, derived the same way. Two of the pairs are exact and two are near
    # it, over 92,815 slot reads:
    #
    #     bit 6 pair   27,984 / 27,984   100.00%      bit 0 pair    9,774 / 10,054  97.22%
    #     bit 8 pair   27,467 / 27,467   100.00%      bit 4 pair   26,507 / 27,310  97.06%
    #
    # The pairs at 6 and 8 are all but always the PROGRAM form - bit 8 alone is never set
    # in 39,942 records, only bit 9 - and the clean sources agree: `fxmaps`' `opacity` is
    # declared as a `dynamicValue` 232 times out of 232, never as a constant, and
    # `numberadded` (296 against 2), `patternsize` (230 against 6) and `frameoffset` (230
    # against 1) are nearly so. A filter whose parameters are almost all functions is the
    # filter whose kind bits sit on "program".
    #
    # The source also declares `patterntype` and `blendingmode` (Int32) and `colorswitch`
    # (Bool). Those are NOT floats, which is why this filter is in PARAM_RAW below.
    4:  [('fx_param0', 0x003, 0x002), ('fx_param1', 0x030, 0x020),
         ('fx_param2', 0x0c0, 0x080), ('fx_param3', 0x300, 0x200)],
}

# Filters whose baked parameter values are reported as the raw u32 rather than as a float.
# `fxmaps`' declared parameters include Int32 and Bool types, so decoding every constant as
# a float32 would invent numbers like 1.5e-33 out of small integers. Where a filter's
# parameter types are not established, the raw word is the honest value.
PARAM_RAW = frozenset({4})


# The OTHER kind mechanism: a population count in the CLASS word.
#
# `blur` (10) and `warp` (7) keep no kind bits in slot 1 - the best correlation any of its
# sixteen bits reaches is 0.225. They keep them in the class word, and they do not spend one
# bit per parameter. `popcount(cls & mask)` is the NUMBER of leading block slots that hold
# programs; the rest hold constants. Order is positional, filled from the front of the block.
#
#     blur      bits 0, 7, 11, 13    100.000%   over 43,883 slot reads, every position exact
#     warp      bits 0, 7, 11          99.889%   over 42,473
#
# The masks are nested, which is worth more than the earlier note allowed: `warp` uses three
# bits and `blur` those same three plus one.
#
# Both must be read against the LAYOUT TABLE's block, not against fixed slot numbers. An
# earlier measurement hardcoded `warp` to slots 3-5 and got 95.69%, because its block starts
# at slot 3 in 13,623 records and slot 4 in 1,561. Using the block gives 99.889%.
PARAM_POPCOUNT = {10: 0x2881, 7: 0x0881}


# FX-Map parameter table: the OTHER thing an fxmaps record's slot 2 can address.
#
# 9,111 records (34% of fxmaps) have a slot-2 target that is not a node header. They point
# instead at a run of 1 to 9 consecutive 8-byte entries, each `[tag][pointer + 52]`. The
# tag is a shape code: it fixes where a program sits inside the structure the pointer
# addresses. Derived over the whole corpus, keeping only tags with 100+ entries in 10+
# specimens and a >=98%-consistent offset - all 15 came out at 100.0%.
#
# The programs are unmistakably FX-Map content: `const.f1 6.28 ; rand.f1 ; cos.f1` is a
# random angle, 6.28 being 2*pi, which is what a pattern generator computes per instance.
# `const.f1 1 ; rand.f1` is the same two-instruction form the version-2 prologue emits.
#
# The first derivation searched offsets 4, 8, 12 and 16 only, and found 15 tags. Widening
# the search to 40 shows +20 and +24 are common, and finds 22 - the earlier window was a
# search range mistaken for a property of the data, the same error as scanning programs on
# 4-byte alignment. No bitfield of the tag computes the offset: the best contiguous field
# predicts it 47.3% of the time, so this is a lookup and not a rule.
#
# tag -> byte offset of the program within the pointed-at structure
# WARNING, measured: this table is 25 exact tag words, and the entry population it is
# meant to describe cannot currently be enumerated safely.
#
# `fx_table` finds entries by stepping 8 bytes and testing `(tag & 0xF) == 8`. That test
# is weak on this data. Program pointers here are 4-ALIGNED, so a pointer VALUE ends in
# 0, 4, 8 or C, and 11.8% of pointer-valued words inside `fxmaps` records end in 8. A
# table entry holds several pointers, so roughly half of them contain at least one word
# that reads as a tag. Stepping by 8 from a known entry start reaches the next
# low-nibble-8 word at 8 bytes only 27% of the time, and at 4, 12 or 24 bytes the rest.
#
# So the entry stride is not established, and any census built on it is not either. A
# scan of that kind produced "67,363 entries, 9,215 distinct tags, 98% of their program
# offsets forming a consecutive run" and none of it is reported, because the denominator
# is unsafe. What a real entry-boundary rule has to beat is that 11.8%.
#
# What DOES survive is the handoff itself: of the chain stops whose word has low nibble 8,
# 86.4% do not resolve as pointer values, so they are packed tag words rather than
# pointers that happen to end in 8. The chain ending in a table is not in doubt; where one
# entry stops and the next begins is.
FX_TABLE = {
    # program at +4
    0x100048: 4, 0x410008: 4, 0x420008: 4, 0x4000148: 4, 0x8000248: 4, 0x8000848: 4,
    # +8
    0x2000048: 8, 0x2000248: 8, 0x2000448: 8,
    # +12
    0x1520248: 12, 0x22000D48: 12,
    # +16
    0x2520448: 16, 0x12400448: 16, 0x12440248: 16, 0x14520248: 16,
    # +20
    0x20018: 20, 0xA800048: 20, 0x124A0648: 20, 0x12540A48: 20, 0x34520A48: 20,
    0x54540088: 20,
    # +24
    0x13120658: 24,
}


# FX-Map table entry LENGTH, stated by the whole tag word. `'T'` means the entry is the
# last in its table.
#
# The 8-byte stride this replaces was not a stride. Measured from a chain handoff -- the
# one entry position established by pointer-following rather than by guessing -- the
# distance to the next entry is 8 bytes in 16% of records and 24 in 40%, with a long tail.
#
# Two things had to be fixed before the length was visible.
#
# 1. The TAG TEST. `(w & 0xF) == 8` fires on 11.8% of pointer-valued words, because
#    program pointers are 4-aligned and so end in 0, 4, 8 or C. The vocabulary below was
#    learned at handoff positions ONLY, where the position is not in doubt, and it is
#    small in a way a noise population is not:
#
#        at validated positions   39,320 sightings   146 distinct words   20 distinct low-16
#        by stepping 8 bytes      28,879 sightings 9,097 distinct words 3,677 distinct low-16
#
#    Testing the low 16 bits against the 17 values seen 20+ times drops the false-positive
#    rate on pointer-valued words from 11.8% to 2.42%.
#
# 2. The GRANULARITY. The low 16 bits alone do not state the length (63.0% pure against a
#    40.0% control). The WHOLE tag word does: 88.4% over 146 tags.
#
# Learned from FIRST entries only and then tested by walking to the second, third and
# beyond -- an extrapolation to positions it was not fitted on:
#
#        step landed on a vocabulary tag            68,521    85.7%
#        step landed elsewhere                      11,399
#        CONTROL: a stride the table did not state             24.6%
# Where a table entry keeps its programs, by tag, as WORD offsets from the entry start.
#
# `FX_TABLE` above is the earlier attempt at this: 25 tags, one offset each, derived when
# entries were enumerated by stepping 8 bytes. That population was unsafe and the result
# was withdrawn. With entries walked by the tag-stated length instead, the same question
# has a much sharper answer -- the tag does not merely suggest an offset, it DETERMINES
# the set:
#
#     tags with 20+ entries                                            100
#     ...whose every offset is either 95+ percent or under 5 -- no
#        middling slot                                                  83
#     entries those tags cover                            111,109 of 112,012
#     tags carrying at least one program                                66
#
# "No middling slot" is the claim worth checking. A slot holding a program in 60 percent
# of a tag's entries would mean the tag does not decide; 83 of 100 tags have no such slot,
# each offset either always holding one or never. That is what a fixed record layout looks
# like from outside, and it is the check that separates this from the withdrawn version.
FX_ENTRY_PROGS = {
    0x00000008: [2, 3, 4, 5, 6], 0x0000019B: [2], 0x0000100B: [5], 0x0000190B: [4],
    0x0000770B: [4, 5, 8], 0x0001900B: [4, 5, 8], 0x00024D0B: [4, 5, 6, 7, 8], 0x0006910B:
    [4], 0x000E100B: [4, 5, 8], 0x00100048: [2], 0x00410008: [6], 0x0041010B: [4],
    0x00420008: [3], 0x00420018: [4], 0x00500248: [2, 3], 0x00500E48: [2, 3], 0x00520158:
    [4, 5], 0x01520248: [3, 4, 5], 0x02400448: [2], 0x02440248: [2], 0x02520448: [3, 4],
    0x03520248: [3, 4, 5], 0x04000048: [2], 0x04000148: [2], 0x04000E48: [2], 0x04440048:
    [2, 3], 0x04540048: [2, 3, 4], 0x05140048: [2, 3, 4], 0x05400348: [2, 3, 4], 0x08520158:
    [4, 5], 0x0C520958: [4, 5, 6], 0x124A0648: [4, 7], 0x12520448: [3, 4, 7], 0x13120658:
    [4, 5, 8], 0x13520248: [3, 4, 5, 8], 0x13520658: [4, 5, 6, 9], 0x13520948: [3, 4, 5, 8],
    0x13520958: [4, 5, 6, 9], 0x14120648: [3, 4, 5], 0x14420248: [3, 4, 5], 0x14420448: [3,
    4, 5], 0x14520248: [3, 4, 5, 6], 0x14540E48: [2, 3, 4, 5], 0x15000448: [2, 3, 4],
    0x150A0248: [4, 5, 6], 0x15140848: [3, 4, 5], 0x15400348: [2, 3, 4, 5], 0x34520A48: [3,
    4, 5, 6], 0x34520A58: [4, 5, 6, 7], 0x35520A48: [3, 4, 5, 6, 7], 0x54500048: [2, 3, 4,
    5, 6], 0x54500148: [2, 3, 4, 5, 6], 0x54500248: [2, 3, 4, 5, 6], 0x54500448: [2, 3, 4,
    5, 6], 0x54500748: [2, 3, 4, 5, 6], 0x54500848: [2, 3, 4, 5, 6], 0x54500C48: [2, 3, 4,
    5, 6], 0x54540248: [2, 3, 4, 5, 6], 0x54540748: [2, 3, 4, 5, 6], 0x54540848: [2, 3, 4,
    5, 6], 0x54540E48: [2, 3, 4, 5, 6], 0x55140048: [2, 3, 4, 5, 6], 0x95140088: [3, 4, 5,
    6, 7], 0xD4500088: [3, 4, 5, 6, 7, 8], 0xD4540088: [3, 4, 5, 6, 7, 8], 0xD5140088: [3,
    4, 5, 6, 7, 8],
}


FX_TAG_LOW16 = frozenset({
    0x0008, 0x0018, 0x0048, 0x0088, 0x0148, 0x0248, 0x0288, 0x0348, 0x0448,
    0x0548, 0x0648, 0x0748, 0x0848, 0x0B48, 0x0C48, 0x0D48, 0x0E48,
})
FX_ENTRY = {
    0x00000048: 64, 0x00000448: 64, 0x00000E48: 64, 0x00020008: 8,
    0x00020018: 16, 0x00420008: 24, 0x02000048: 76, 0x02510448: 80,
    0x05140048: 56, 0x54500148: 80, 0x54500248: 80, 0x54500448: 80,
    0x54500848: 80, 0x54500C48: 80, 0x54540248: 80, 0x54540748: 80,
    0x54540848: 80, 0x54540E48: 80, 0x95540288: 4,  0xD4540088: 88,
    # terminal - the last entry of its table
    0x02520448: 'T', 0x04440048: 'T', 0x04540048: 'T', 0x05400348: 'T',
    0x08000248: 'T', 0x08000848: 'T', 0x0A800048: 'T', 0x15140848: 'T',
    0x15400348: 'T', 0x22000248: 'T', 0x22000D48: 'T', 0x55140048: 'T',
}


# THE TAG IS A PARAMETER LAYOUT, and every table entry decodes without a lookup table.
#
# `FX_ENTRY_PROGS` above is a census: 100 tags observed often enough to state where their
# programs sit. It covers 45.2% of the corpus's 112,012 entries and says nothing about the
# other 55%, nothing about which slot means what, and nothing about a tag it has not seen.
# The tag does not merely CORRELATE with the program offsets - it spells the entry out.
#
# Bits 20..31, read in ASCENDING order, are the entry's parameter sequence: a set bit means
# that parameter is present and takes the next slot(s), a clear bit means it is absent and
# takes none. Seven of them hold a program pointer; the rest hold a value baked in place,
# and bit 25's baked value is TWO words wide because the parameter is a float2.
#
# NAMES, by containment against the permitted paired sources (tools/provenance.py).
# An FX-Map's source declares each `paramset` node's parameters, each either a literal or a
# `<dynamicValue>` function graph, and a graph's `const_*` nodes carry literals that survive
# into the compiled program as immediates. So for a source node and a compiled entry with
# the same number of programs, ask which BIJECTIONS of names onto program slots put every
# declared literal inside the program that slot names. Where exactly one bijection survives,
# it is the binding - no name similarity, no ordering assumption, no guess.
#
#     source paramset nodes x candidate entries          2,203
#       exactly one valid bijection                        943   <- the evidence
#       several                                            543   (reported, not used)
#       none                                               697
#     (tag, slot) pairs bound                               13
#     pairs where two nodes disagreed about the name         0
#
# Zero disagreements across 943 independent bijections over three tags, and the three tags
# agree with each other on every bit they share.
#
# WHY THIS IS THE NESTED-SERIALISATION TRAP AGAIN: 3 of the 8 permitted FX sources write
# every literal as `<constantValueFloat1><value v="0.75"/></constantValueFloat1>` and the
# other 5 as `<constantValueFloat1 v="0.75"/>`. Matching one form reports the other three
# files as declaring no constants at all, which is how this looked unbindable at first. It
# is the third time that fact has cost this project a measurement.
#
# THE LAYOUT, fitted with the names held out. Roles were fitted to the base-free SHAPE of
# each tag's program-slot list (the gaps, not the positions), so the fit cannot absorb an
# error in where the entry's header ends:
#
#     predicted shape == the census's, over the 57 real entry tags     55/57   96.5%
#     CONTROL, random role per bit                                              8.0%
#     leading slots  base = 2 + widths of set bits {4, 7, 16, 17, 19}  55/55  100.0%
#     CONTROL, random widths                                                    4.7%
#     the two together: predicted program-slot LIST == the census's    55/57   96.5%
#
# BIT 16 IS FOUR WORDS WIDE, and it is the only leading bit that is not one. Fitting the
# base with widths capped at 2 leaves exactly one tag unexplained -- `0x00410008`, predicted
# 2 and observed 6 -- and allowing 4 closes it at 55/55. That is not curve-fitting on one
# row: bit 16 is set in two residue tags and its width predicts BOTH of their positions
# directly, `0x00410008`'s program at +6 in 98% of 445 entries and `0x02510448`'s at +6 and
# +7 in 91% of 44. Corpus-wide it moves the layout from 93.87% to 94.33%.
#
# Four words is a baked float4, and the FX-Map quadrant's float4 parameter is its colour --
# which would sit beside the bit-8 finding below, where a set bit 8 is what makes `opacity`
# return f4. That reading is NOT claimed here; the width is measured, the name is not.
#
# The nine `FX_ENTRY_PROGS` keys whose low nibble is 9 or 0xB are excluded from that count:
# a nibble of 8 is what makes a word a table entry, and 9/0xB are NODE headers, which is a
# different structure with a different shape. They were never entries.
#
# GAPS ARE ALWAYS TWO WORDS, which is what says bit 25 is a float2 baked in place rather
# than one word plus an unknown. Over the ten census tags whose program slots are not
# consecutive, every gap is exactly 2 - against a control that draws the same number of
# slots at random from the same span and produces a 1-wide gap 76.3% of the time.
#
# APPLIED TO THE WHOLE CORPUS, not just to the tags it was fitted on:
#
#     slots this layout calls a program                    108,257
#       hold a program `program_span` accepts              101,617   93.9%
#     CONTROL, the same test at an out-of-layout slot                  0.7%
#
# 101,617 named programs, against 934 the direct source binding reaches on its own.
#
# THE INDEPENDENT CHECK, which is the one that matters. None of the above looks at what a
# program COMPUTES. A source declares each parameter's result type, and the ISA's last
# instruction states the program's. They agree, corpus-wide, on evidence that fed nothing
# above:
#
#     opacity          f1 97.9%   (f4 1.9%: colour opacity, and those entries set bit 8)
#     branchoffset     f2 100.0%  over 45,504
#     frameoffset      f2 99.8%
#     patternsize      f2 99.8%
#     patternrotation  f1 99.9%
#     patternsuppl     f1 100.0%
#     imageindex       i1 98.5%
#
# WHAT IS AND IS NOT SETTLED. `opacity`, `patternsize` and `patternrotation` are bound by
# all three tags independently and confirmed by type. `branchoffset` (bit 22) is bound by
# ONE specimen -- and it is the commonest bit in the corpus, 45,504 programs, so it is
# simultaneously the least-evidenced name and the most load-bearing one. Type agreement
# confirms it carries a two-component parameter but cannot separate it from `frameoffset`,
# which is also f2. Treat the pair as "one of the two offsets, probably this one".
# Bits 21 and 23 are set in NO observed tag, so their roles are unfitted and their names
# unknown; bits 27 and 29 are set in 2 and 3 tags, enough to say "baked" and not enough to
# say how wide. They are `None` below rather than guesses.
#
# A SEPARATE TEST of the same map, from the other direction: take a source node's declared
# parameter set, predict the tag's high twelve bits from the names alone, and ask whether
# that value occurs among the file's compiled entry tags. 60 of 62 nodes, against 4.2% for
# a shuffled name-to-bit map. The two misses are one file whose entries the walk does not
# reach at all.
#
# bit -> (parameter name or None, slots the baked form occupies)
FX_PARAM_BITS = (
    (4,  None,              1),   # leading baked words; which parameters they are is
    (7,  None,              1),   # not established -- only that each takes one slot,
    (16, None,              4),   # except this one, which takes FOUR: see below
    (17, None,              1),   # which is what fixes where the program run starts
    (19, None,              1),
    (20, 'opacity',         1),
    (21, None,              1),   # never set in any observed tag
    (22, 'branchoffset',    1),
    (23, None,              1),   # never set in any observed tag
    (24, 'frameoffset',     1),
    (25, None,              2),   # baked float2; the only two-word gap the census shows
    (26, 'patternsize',     1),
    (27, None,              1),   # baked, width not established (2 tags)
    (28, 'patternrotation', 1),
    (29, None,              1),   # baked, width not established (3 tags)
    (30, 'patternsuppl',    1),
    (31, 'imageindex',      1),
)

# The bits whose parameter is stored as a POINTER to a program rather than baked in place.
FX_PROGRAM_BITS = frozenset({20, 22, 24, 26, 28, 30, 31})


# Bits whose presence means an INLINE program sits after the parameter slots -- one the
# entry stores in its own bytes instead of pointing at. See `fx_entry_layout`.
FX_INLINE_BITS = frozenset({25, 27, 29})


def fx_entry_layout(tag):
    """[(slot, name or None, 'program'|'baked'|'inline')] for one FX table entry tag.

    Slot 0 is the tag and slot 1 is the entry's own word; parameters start at slot 2 and
    are laid out in ascending bit order. Returns [] for a tag with no parameter bits set,
    which is a real answer -- `0x00020008` is an entry whose every parameter is baked
    ahead of the run.

    'program' means the SLOT HOLDS A POINTER to a program. 'inline' means the slot IS the
    program -- its first word is the instruction count. Callers must not confuse the two:
    reading an inline slot as a pointer lands 52 bytes past a random instruction.
    """
    out, sl = [], 1
    for bit, name, width in FX_PARAM_BITS:
        if not (tag >> bit) & 1:
            continue
        if bit in FX_PROGRAM_BITS:
            sl += 1
            out.append((sl, name, 'program'))
        else:
            out.append((sl + 1, name, 'baked'))
            sl += width
    # THE INLINE PROGRAM. `FX_TABLE` above records, for 25 tags, "the byte offset of the
    # program within the structure the entry's +4 word addresses", and withdrew itself
    # because the entry population it described could not be enumerated safely. With the
    # population clean, both halves of that sentence resolve: the "structure" is the ENTRY
    # -- the +4 word is a self-pointer, landing at off+8 in 2,737 of 2,870 cases -- and
    # every one of its six commonest offsets equals 4 x (the first slot this layout does
    # not use). So there is no second structure and no lookup table; the program simply
    # sits after the parameters.
    #
    #     no program bits, and bit 25, 27 or 29 set:
    #       a program is there              2,796      precision 94.6%
    #       none is                           161
    #     rule silent, a program is there     165      (so recall is 94.4%)
    #     CONTROL, the same test two slots further on             3.9%
    #
    # Only when the tag names no program slots. An entry that has them already has a
    # program at this slot in 99.0% of cases -- it is the first one its own pointers
    # address, sitting adjacent -- and reporting it again would double-count it.
    #
    # NOT NAMED. 98% of these open with `inputref`, so they are image references rather
    # than numeric parameters, and `inputref const add` / `inputref cvt swizzle` are the
    # two commonest shapes. No permitted source sets bits 25, 27 or 29 on any entry, so
    # nothing available can say which parameter this is.
    if not any(k == 'program' for _s, _n, k in out) and (
            tag & sum(1 << b for b in FX_INLINE_BITS)):
        out.append((sl + 1, None, 'inline'))
    return out


# Base image inputs for the filters whose parameter fields are catalogued.
_RULED_PARAMS = {1: 2, 12: 2, 15: 1, 11: 1}


class Record:
    """One compiled filter node: a tag, a class word, and a run of 32-bit slots.

    Three properties used to share a name up to pluralization -- `params`,
    `parameter`, `parameters` -- for three unrelated things, which cost real
    debugging time more than once (render.py read `size_or_baked`'s program as
    a filter's opacity; it is the record's OUTPUT SIZE expression in 91.3% of
    records and only incidentally a real parameter in the rest). Renamed so a
    plain read of the name says which:

        slot1_flags       decoded bits of the slot-1 class/parameter word
                          (blend mode, "computes own size", etc.)
        size_or_baked     the first slot after the record's inputs -- a
                          size-expression PROGRAM in 91.3% of records, a
                          baked FLOAT parameter in the rest; the tag says
                          which, a caller must still check it
        named_parameters  real per-filter parameters with names, e.g.
                          directionalwarp's `intensity`/`angle`; empty
                          unless the filter is in PARAM_SPEC

    Two more properties are easy to reach for wrong in the same way:

        programs          every program this record's slots name, including
                          the size expression -- wants counting bytes
        filter_programs   `programs` with the size expression (if identified
                          as `size_or_baked`'s target) removed -- wants
                          knowing what the filter actually computes

    And `matrix`/`translation` (filter 2 only) both return None for three
    different reasons alike -- not this filter, slot out of range, or the
    value is computed by a program rather than baked -- which their own
    docstrings cover but a caller cannot recover from the None alone.
    """
    __slots__ = ('index', 'offset', 'end', 'tag', 'cls', 'asm', '_words', '_layout')

    def __init__(self, asm, index, offset, end):
        self.asm, self.index, self.offset, self.end = asm, index, offset, end
        w0 = struct.unpack_from('<I', asm.data, offset)[0]
        self.tag, self.cls = w0 & 0xFFFF, w0 >> 16
        self._words = None
        self._layout = None

    @property
    def words(self):
        """Unpacked lazily: an fxmaps record runs to 331 slots and most callers
        touch only the first handful."""
        w = self._words
        if w is None:
            n = (self.end - self.offset) // 4
            w = struct.unpack_from('<%dI' % n, self.asm.data, self.offset) if n else ()
            self._words = w
        return w

    # ---- tag fields
    @property
    def filter_id(self):
        return (self.tag & 0xFF) >> 1

    @property
    def colour(self):
        return bool(self.tag & 1)

    @property
    def width(self):
        return 1 << ((self.tag >> 8) & 0xF)

    @property
    def height(self):
        return 1 << ((self.tag >> 12) & 0xF)

    @property
    def filter_name(self):
        return FILTERS.get(self.filter_id)

    @property
    def known(self):
        return self.filter_id in FILTERS

    # ---- structure
    @property
    def arity(self):
        """Number of image inputs, or None when the layout is not known."""
        if self.filter_id == 20:                       # variable-length input list
            n = self.words[1] if len(self.words) > 1 else -1
            return n if 0 <= n <= 16 else None
        e = EDGES.get(self.filter_id)
        return len(e) if e is not None else None

    @property
    def layout(self):
        """(edge slots, program slot) for this record, probing alternates if needed.

        Cached: `edges`, `parameter` and `programs` all need it, and the probe walks
        bytecode, so recomputing it three times per record dominated the corpus audit.
        """
        if self._layout is not None:
            return self._layout
        edges, prog = self._compute_layout()
        self._layout = r = (self._real_edges(edges), prog)
        return r

    def _real_edges(self, slots):
        """Drop slots the layout names as edges that measurably are not edges.

        A genuine edge holds a NEARBY record index, so its value has to rise with the
        record's own index. Over the 40 (filter, slot) pairs the layout names as edges
        with 200+ observations, the correlation between the slot's value and the
        record's index is 0.936 or better for 37 of them and 0.99+ for 34. Three fail:

            transformation slot 1   corr -0.319   n   287
            fid 8          slot 1   corr  0.067   n   758
            warp           slot 3   corr -0.005   n 1,867

        This is a control that can fail, and it is the only thing that found these. The
        100%-resolution figure could not: a two-bit type-code vector is a small integer,
        so it passes "is this a backward record index" trivially. That is the same
        conflation that produced the shared-reference error recorded against EDGES.

        Slot 1 of `transformation` and of filter 8 is words[1], the type-code vector.
        263 of transformation's 287 hold 0x3f, which is the modal words[1] across all
        284,131 transformation records (119,919 of them); filter 8's 758 take 22 distinct
        small values whose histogram is its words[1] histogram. Nothing real is dropped:
        all 287 transformation records keep their one other edge slot, all 758 filter-8
        records keep their two, and every one of those resolves.

        Warp is not a defective entry but two record shapes, and words[1] separates them
        exactly:

            words[1] == 0    1,801 records   slot 3 is a backward index   1,801  100.0%
            words[1] != 0       66 records   slot 3 is a program pointer     65   98.5%
                                             slot 1 is a backward index      66  100.0%  corr 0.998

        So when words[1] is nonzero the whole record is shifted one slot earlier: the two
        edges are at slots 1 and 2 and slot 3 holds the pointer. The tracking is within
        file, not an artefact of pooling - in BricksSubstance005 records 4099, 4101 and
        4103 carry 4097, 4099 and 4101, always index minus two.

        `levels` and `distance` are the same defect as transformation and filter 8 at a
        smaller scale - 68 and 21 records, correlating 0.108 and -0.431 - and both keep
        their slot-2 edge, which resolves in every one.

        The last two are not type codes but COUNTS, and the layout table read a count as
        an edge because a small number passes for a small record index:

            gradient slot 2   166 records   the ramp's stop count. `ramp` already says so
                                            - "resolution agreement 35.5%, which is
                                            chance" - but nothing enforced it. Dropping it
                                            alone would leave those records with no input
                                            at all; their real edge is slot 1, which the
                                            table never named and which holds a backward
                                            index in all 166.

            curve slot 2      119 records   the count of spline control points, repeated
                                            again in the record's last slot. Curve's three
                                            shapes are (1,2,4), (1,2,5) and (1,2,6), and
                                            in every one slot 1 is the edge, slot 2 the
                                            count, the middle slots are table pointers and
                                            the final slot repeats the count. So curve has
                                            exactly one input, which is what EDGES says.

        What that does NOT settle is the words[1] == 0 population, where slot 1 holds 0.
        Zero is both "no type codes" and "an edge to record 0", and the value cannot
        distinguish them. Warp takes two image inputs and slots 2 and 3 already supply
        them, so this reads it as the type-code vector; that is an inference from arity,
        not a measurement.
        """
        f = self.filter_id
        # Filter 8 is NOT here any more: `_compute_layout` states emboss's edges as
        # (2, 3) directly, so stripping slot 1 here as well would write one rule twice.
        # Kept for 2, 15 and 21, whose slot 1 arrives from the layout TABLE rather than
        # from a rule and so cannot be corrected at the source.
        if f in (2, 15, 21):
            return [s for s in slots if s != 1]
        if f == 7 and len(self.words) > 1 and self.words[1] != 0 and 3 in slots:
            return sorted({1} | {s for s in slots if s != 3})
        if f == 0 and 2 in slots:
            return sorted({1} | {s for s in slots if s != 2})
        if f == 22 and 2 in slots:
            return [1]
        return slots

    def _compute_layout(self):
        f = self.filter_id

        # ---- rules that replace memorised table entries
        #
        # These run BEFORE the table because layouts.json is demonstrably wrong for them,
        # in ways a (filter, cls, word1) key cannot express. Each is measured in
        # FORMAT-NOTES.md against the records rather than against the table.

        # fxmaps states its input count in a 4-bit field. The table cannot hold it:
        # LAYOUT_MASK[4] is 0xe55, which keeps bits 10 and 11 of the field and discards
        # 12 and 13, so a four-bit number arrives cut in half.
        #
        #     (word1 >> 10) & 0xF == the leading run of backward record indices
        #         41,198 / 41,212  99.97%   all records
        #          5,152 /  5,165  99.75%   records whose field is NONZERO, where a
        #                                   constant predictor scores nothing
        #
        # The previous reading - bit 12 set means slots 3-8 are edges - is the single
        # case k == 6 of this field, and missed every other arity.
        if f == 4 and len(self.words) > 1:
            k = (self.words[1] >> 10) & 0xF
            if k and 3 + k < len(self.words):
                return (list(range(3, 3 + k)), 3 + k)
            if not k:
                return ([], 3)

        # shuffle puts an input in SLOT 1 - where the parameter word would be - and the
        # table keyed on it, memorising 38 record indices as if they were configurations.
        # The slot is self-discriminating, as bitmap's is.
        #
        #     the table calls slot 1 an edge, and it IS a backward index   883 / 883
        #     the table gives 175 records no input at all, impossible for a channel
        #       shuffle: 143 have the index in slot 1, 32 in slots 2 and 3
        #     control: slots the table calls PARAMETERS pass the same test 1.46% of the
        #       time, so this is 56x the false-positive rate
        #
        #     finds an input for 4,605 / 4,605 records, against the table's 4,430
        if f == 3 and len(self.words) > 3:
            n = len(self.asm.records)

            def _backward(v):
                return v == 0 or (v < self.index and v < n)

            if _backward(self.words[1]):
                return ([1], 2)
            if _backward(self.words[2]) and _backward(self.words[3]):
                return ([2, 3], 4)

        # filter 8 always takes THREE image inputs, in slots 1, 2 and 3. The table gives
        # it three only 60.3% of the time, splitting the rest into a spurious two-input
        # form - but in the records the table calls two-input, slot 1 holds a valid
        # backward record index in 217 of 217.
        #
        #     slots 1, 2 and 3 all valid backward indices   538 / 546   98.5%
        #     the table gives three edges                   329 / 546   60.3%
        #     slots 4, 5 and 6 valid                          0 / 546    0.0%
        #
        # The 8 exceptions carry a FORWARD index in slot 1 and are left to the table.
        if f == 8 and len(self.words) > 4:
            n = len(self.asm.records)

            def _bw8(v):
                return v == 0 or (v < self.index and v < n)

            # Emboss takes TWO inputs, at slots 2 and 3. Slot 1 is words[1], the packed
            # type-code word. It was proposed here as a third edge and `_real_edges` then
            # removed it again, in all 546 records - the rule stated twice, the two
            # statements disagreeing. The index-correlation control settles it:
            #
            #     corr(slot 1, record index)   +0.109      22 distinct small values
            #     corr(slot 2, record index)   +0.999
            #     corr(slot 3, record index)   +0.985
            #
            # The guard asked whether slot 1 held a backward index. A small packed word
            # passes that trivially, and did in all 546, so the guard was vacuous - the
            # same conflation already recorded against EDGES and the layout table. Slots
            # 2 and 3 are backward on their own in 546 of 546.
            if all(_bw8(self.words[s]) for s in (2, 3)):
                return ([2, 3], 4)

        # The parameter slots of the four filters whose two-bit fields are catalogued,
        # computed from the FULL word1 rather than looked up.
        #
        # The table cannot hold this rule for two of them. Its key masks word1, and the
        # mask drops field bits the rule needs:
        #
        #     blend            LAYOUT_MASK 0x230   fields 0x230   loses nothing
        #     directionalwarp              0x1e           0x1e    loses nothing
        #     dirmotionblur                0x4            0xf     loses 0xb
        #     levels                       0x3fd          0x3ff   loses bit 1
        #
        # so for dirmotionblur and levels two records with different parameter states
        # collide on one key and must share one answer. That is the same defect as
        # fxmaps' halved arity field, and it cannot be repaired by rewriting entries.
        #
        # The allocation order puts the class-word parameters immediately after the base
        # image inputs, so the first of them - the slot a reader wants - is at 2 + arity.
        # The rule and the table are UNIONED rather than one replacing the other.
        #
        # A value test cannot decide between them: "slot 1 holds a valid backward record
        # index" is true for 94% of these records, because a word1 bitfield is a small
        # number and record indices are large - 291,188 false positives on blend alone.
        # Guarding on it excluded almost every record and reduced the rule to +5 edges.
        #
        # Dropping the guard instead loses 167 real edges to gain 307. The union keeps
        # both: every slot the table names, plus every slot the rule finds. The added
        # slots were valid backward record indices in 307 of 307, so the union does not
        # admit junk.
        _ruled = f in _RULED_PARAMS and len(self.words) > 1
        if _ruled:
            base = _RULED_PARAMS[f]
            w1 = self.words[1]
            edges = list(range(2, 2 + base))
            # The class-word parameters sit between the base inputs and the fields, so a
            # state-11 field's edge lands after them. Omitting this placed the mask input
            # of 8,188 blend records too early, and 99.99% of the slots that dropped out
            # of the edge list were valid backward record indices - real edges, lost.
            g = ((self.cls & 1) + ((self.cls >> 7) & 1) + ((self.cls >> 11) & 1)
                 + ((self.cls >> 13) & 1) + 2 * ((self.cls >> 10) & 1))
            s = 2 + base + g
            for _nm, mask, hi in PARAM_SPEC[f]:
                x = w1 & mask
                if not x:
                    continue
                if x == mask:                      # state 11: an image input
                    edges.append(s)
                s += 1
            prog = 2 + base
            if prog < len(self.words):
                hit = (LAYOUTS or {}).get(
                    (f, self.cls, self.words[1] & LAYOUT_MASK.get(f, 0)))
                if hit:
                    edges = sorted(set(edges) | set(hit[0] or []))
                return (edges, prog)

        if LAYOUTS and len(self.words) > 1:
            hit = LAYOUTS.get((f, self.cls, self.words[1] & LAYOUT_MASK.get(f, 0)))
            if hit:
                edges, progs = hit
                sl = progs[0] if progs else None
                # `pixelprocessor` states its INPUT COUNT in the low nibble of slot 1, and
                # its parameter follows the inputs. The layout key does not encode the
                # count, so a record with more inputs than the key's edge list covers has
                # its parameter slot pushed along and the key's index lands on an edge.
                #
                #     the nibble IS the edge count      56,934 / 57,118 = 99.68%
                #     min(edge slots) + nibble is a program  54,180 / 54,180 = 100.00%
                #     the key's slot is a program            54,001 / 54,180 =  99.67%
                #
                # The two agree in 54,001 and differ exactly where the key is wrong. This
                # is the same field `fxmaps` uses for the same purpose.
                if f == 20 and edges:
                    k = min(edges) + (self.words[1] & 0xF)
                    if k < len(self.words):
                        sl = k
                return (list(edges), sl)
        if f == 4:
            # Superseded by the arity field above; reachable only for a record too short
            # to hold the inputs its field claims.
            return ([], 3)
        if f == 20:
            n = self.arity
            return (list(range(2, 2 + n)), 2 + n) if n is not None else ([], None)
        alts = ALT_LAYOUTS.get(f)
        if alts:
            for edges, prog in alts:
                if prog < len(self.words):
                    q = self.words[prog] + 52
                    if self.asm.body_lo <= q < self.asm.body_hi and self.asm.valid_program(q):
                        return (edges, prog)
            return alts[0]                       # nothing validated; report the default
        return (EDGES.get(f, []), PROG_SLOT.get(f))

    @property
    def output_size(self):
        """(log2 width, log2 height) as the record's own size expression computes it.

        Returns None when the expression uses an operation this reader does not evaluate.
        Where it does evaluate, it agrees with the tag in 99.81% of records -- so this is a
        cross-check on the tag, not a substitute for it.
        """
        par = self.size_or_baked
        if not par or par[0] != 'program':
            return None
        decl = {u: v for t, u, v in (self.asm.header.get('inputs') or [])}
        vals = []
        for k, addr, op, toks in disasm.decode(self.asm.data, par[1], self.end):
            _ntok, _ty, n, oid = disasm.fields(op)
            if oid == 0x02:
                v = decl.get(disasm.uid(addr, toks))
                if v is None or len(v) < n:
                    return None
                vals.append(tuple(int(x) for x in v[:n]))
            elif oid == 0x00:
                raw = disasm.immediate(addr, toks)
                if len(raw) < 4 * n:
                    return None
                vals.append(tuple(struct.unpack_from('<i', raw, 4 * i)[0] for i in range(n)))
            elif oid in (0x12, 0x13):
                if len(toks) < 2:
                    return None
                try:
                    x, y = vals[toks[0]], vals[toks[1]]
                except IndexError:
                    return None
                if len(x) != len(y):
                    return None
                vals.append(tuple(p + q if oid == 0x12 else p - q for p, q in zip(x, y)))
            else:
                return None
        return vals[-1] if vals and len(vals[-1]) == 2 else None

    @property
    def header_words(self):
        """Length of this record's header in words, or None if the key is unknown.

        Everything from here to the end of the record is code, not slots.
        """
        if len(self.words) < 2:
            return None
        # The RULE first, the memo second. `record_layout.header_words` computes this
        # from the two presence masks -- a constant plus the cost of each set bit -- and
        # returns None for filters whose costs have not been derived. HEADER_WORDS is a
        # memo of the same quantity, keyed by (filter, cls, w1 & LAYOUT_MASK), and that
        # key is lossy: it masks w1, so it cannot even represent the arity fields. Where
        # the rule answers it is exact by construction; see tools/derive_costs.py.
        import record_layout
        w1 = self.words[1]
        # Two-shape filters. Warp's w1 word is a VERSION fact -- absent before 0x90000,
        # present from it -- and the old edge-start detector could not tell w1 == 0 from
        # "an edge to record 0", misreading 180 v9 records. Shuffle's shapes coexist
        # within versions, so it stays per-record: slot 1 is self-describing.
        if self.filter_id == 7:
            ver = self.asm.header.get('version') if isinstance(self.asm.header, dict) else 0
            if ver < 0x90000:
                w1 = None
        elif self.filter_id == 3:
            try:
                es = [s for s in self.edge_slots if s < len(self.words)]
            except Exception:
                es = []
            if es and min(es) == 1:
                w1 = None
        ver = self.asm.header.get('version') if isinstance(self.asm.header, dict) else 0
        n = record_layout.header_words(self.filter_id, self.words[0], w1, version=ver)
        if n is not None:
            return n
        return HEADER_WORDS.get((self.filter_id, self.cls,
                                 self.words[1] & LAYOUT_MASK.get(self.filter_id, 0)))

    @property
    def edge_slots(self):
        """Slots holding this record's input edges.

        `pixelprocessor` states its own arity instead of relying on the layout table: the
        low nibble of slot 1 is the input count and the inputs occupy slots 2 onward. The
        nibble IS the count, not a code for it - it equals the resolved edge count in
        56,934 of 57,118 records (99.68%). Over the corpus,
        records with a count of 1 to 8 have every one of those slots holding a valid
        backward record index in 41,350 of 41,453 - 99.8%. The derived table saw only the
        slots that were populated often enough to pass a threshold and missed the rest,
        which stranded 6,875 pixelprocessor records from any output.
        """
        if self.filter_id == 20 and len(self.words) > 1:
            n = self.words[1]
            if 1 <= n <= 8 and len(self.words) >= 2 + n:
                return list(range(2, 2 + n))
            if n == 0:
                return []                  # a generator: no image input at all
            # The count is the low NIBBLE, not the whole word. Reading the whole word works
            # only while no other bit of slot 1 is set, and 437 records have one. In every
            # one of those 437, slots 2..2+nibble hold a backward record index - so the
            # nibble is right where the whole word is unusable, and 32 of them get more
            # edges than the layout table offers.
            #
            # Applied only when the whole-word rule does not fire, so this cannot change
            # any record that was already being read.
            #
            # The cap is 16, the width of the field, not 8. Capping it at 8 stranded 81
            # records with a declared arity of 9, 12 or 13 - and in all 81, every one of
            # slots 2..2+k-1 holds a backward record index, so the declared count is
            # right there too. Those records were falling through to the layout table,
            # which named slots 11, 12 and 13 as edges when they hold the pointer.
            k = n & 0xF
            if 1 <= k <= 16 and len(self.words) >= 2 + k \
                    and all(0 <= self.words[2 + j] < self.index for j in range(k)):
                return list(range(2, 2 + k))
        return self.layout[0]

    @property
    def edges(self):
        """Input record indices. None entries are unresolved.

        Edge values are 0-BASED, so 0 is a reference to record 0, not an absent input.
        Those were conflated: the corpus settled 0-based indexing (87.17% resolution
        agreement against 79.97% for 1-based) while the same value was also read as 'no
        input', and the two cannot both hold. `0xFFFFFFFF` is the actual absent-input
        marker, and it is a separate value.

        Only 0.10% of edge slots hold 0, so little turns on it in aggregate -- but it is
        everything for a small graph, where record 0 is the generator every other record
        descends from. Crediting it lifts the per-file median of records reachable from
        the output table from 97.6% to 99.8%.

        A slot beyond the end of this record is not an unresolved edge - it is a slot
        this record does not have, so no edge is claimed for it at all. Reporting those
        as unresolved conflated "the value here is not a record index" with "the layout
        table named a slot that is not present", which are different failures.
        """
        out = []
        for sl in self.edge_slots:
            if sl >= len(self.words):
                continue
            v = self.words[sl]
            if v == 0xFFFFFFFF:
                continue                  # -1: this record has no input in this slot
            if v == 0 or (v < self.index and v < len(self.asm.records)):
                out.append(v)
                continue
            # The layout descriptor does not fully determine a few keys: a slot that is
            # an edge in most of a key's records holds a program or a baked float in the
            # rest. Those readings are disjoint from a backward record index, so this is
            # a positive identification rather than a fallback - the slot is not an edge
            # in THIS record, so no edge is claimed.
            #
            # Deliberately narrow. A forward index, or one past the end of the record
            # table, is left as None: those are genuinely unexplained and must stay
            # visible rather than be absorbed into a catch-all.
            q = v + 52
            if self.asm.body_lo <= q < self.asm.body_hi and self.asm.valid_program(q):
                continue
            f = struct.unpack('<f', struct.pack('<I', v))[0]
            if v and math.isfinite(f) and 1e-6 <= abs(f) <= 1e6:
                continue
            out.append(None)
        return out

    @property
    def shared_refs(self):
        return [self.words[s] for s in SHARED.get(self.filter_id, [])
                if s < len(self.words)]

    @property
    def slot1_flags(self):
        """The slot-1 parameter word, decoded as far as it is understood.

        Was `params` -- renamed to stop it colliding by name, not just by
        near-miss reading, with `size_or_baked` and `named_parameters`, three
        unrelated things a plain grep for "param" could not tell apart. See
        the class docstring for what each one actually holds.
        """
        if self.filter_id not in PARAM_WORD or len(self.words) < 2:
            return None
        v = self.words[1]
        d = {'raw': v}
        if self.filter_id == 1:                        # blend
            d['blendingmode'] = v & 0xF                # confirmed
            d['computes_own_size'] = bool(v >> 5 & 1)  # confirmed
            d['unknown_bits'] = v & ~0x2F
        return d

    @property
    def size_or_baked(self):
        """The first slot after the record's inputs. It is one of two different things.

        Was `parameter` -- renamed because that name reads as "the meaningful
        setting", and it usually is not. **Not "the main parameter"**, which is
        what these notes called it for a long time before that too. In 91.3%
        of records it holds the record's OUTPUT SIZE expression - see
        `output_size`, and `filter_programs`, which exists specifically to
        strip this program back out of `programs` for callers that want what
        the filter actually computes - and in the rest a baked float that is
        a genuine filter parameter. The two are not variants of one idea;
        they are different fields, which is exactly what the tagged return
        forces a caller to handle rather than guess at.

        Which one it is, is **stated by the layout descriptor**: over 1,031,041 records
        and 20,970 keys the key predicts it in 100.00%, with a single mixed key of 278
        records. So a reader never has to guess.

        The readings are also disjoint in the data - a decodable program pointer is never
        a plausible float - so the discrimination here is exact rather than heuristic.

        Returns ('program', offset) | ('float', value) | ('zero', 0) | None.
        """
        sl = self.layout[1]
        if sl is None or sl >= len(self.words):
            return None
        v = self.words[sl]
        p = v + 52
        if self.asm.body_lo <= p < self.asm.body_hi and self.asm.valid_program(p):
            return ('program', p)
        if v == 0:
            return ('zero', 0)
        f = struct.unpack('<f', struct.pack('<I', v))[0]
        if math.isfinite(f) and (f == 0 or 1e-6 <= abs(f) <= 1e6):
            return ('float', f)
        # The program can be INLINE at the slot rather than pointed at by it. The slot
        # then holds a program header -- 0x09000022 is [34 instructions][const.f1] -- which
        # reads as a denormal float and was being discarded.
        #
        # Safe to try only because the two readings are disjoint: of 1,037,401 slots that
        # resolve as a pointer, 2 also start a program, 0.00%. Almost all of these are
        # `gradient` (351 of 353).
        addr = self.offset + 4 * sl
        if self.asm.program_span(addr, self.end):
            return ('program', addr)
        # The layout key does not encode how many INPUTS a record has. A record with more
        # inputs than its key's edge list covers has its program slot pushed along, and the
        # slot the key names holds another edge - a backward record index.
        #
        # Recognised by three things together, none of which is enough alone: the word is a
        # backward record index, the slot is one this filter uses as an edge slot under
        # other keys, and stepping past the run of such words lands on a valid program.
        # That last is the one that pays: it holds in 327 of 327 records, no exceptions.
        #
        # These records are `pixelprocessor` with a median of 5 edges against 1 for the
        # rest, and 350 words against 28. Multi-input records, in other words.
        if not (0 <= v < self.index and sl in EDGE_SLOTS.get(self.filter_id, ())):
            return None
        k = sl
        while k < len(self.words) and 0 <= self.words[k] < self.index:
            k += 1
        if k >= len(self.words):
            return None
        q = self.words[k] + 52
        if self.asm.body_lo <= q < self.asm.body_hi and self.asm.valid_program(q):
            return ('program', q)
        return None

    @property
    def named_parameters(self):
        """Named parameters this record carries, as [(name, kind, value), ...].

        Was `parameters` -- renamed alongside `size_or_baked` (was `parameter`)
        and `slot1_flags` (was `params`) so the three no longer share a name up
        to pluralization. This is the only one of the three actually NAMED --
        real per-filter parameters like directionalwarp's `intensity`/`angle`.

        `kind` is 'baked' for a constant, whose value is the float in the slot, or
        'program', whose value is the program's offset.

        Only for filters in PARAM_SPEC; [] otherwise, and [] is not a claim that the
        record has no parameters - only that this filter's bit layout is not derived yet.
        """
        f = self.filter_id
        if f in PARAM_SPEC:
            return self._parameters_paired(PARAM_SPEC[f])
        return []

    @property
    def program_slots(self):
        """Which block slots hold programs, for the filters that encode it as a count.

        Returns a list of (slot, is_program) for filters in PARAM_POPCOUNT, or [] otherwise.
        This is the class-word mechanism, not the slot-1 bit pairs of PARAM_SPEC - a filter
        uses one or the other, never both.
        """
        m = PARAM_POPCOUNT.get(self.filter_id)
        if m is None or len(self.words) < 2:
            return []
        hit = LAYOUTS.get((self.filter_id, self.cls,
                           self.words[1] & LAYOUT_MASK.get(self.filter_id, 0)))
        if not hit:
            return []
        n = bin(self.cls & m).count('1')
        return [(s, j < n) for j, s in enumerate(hit[1]) if s < len(self.words)]

    def _read_slot(self, name, slot):
        """One parameter slot as (name, kind, value)."""
        raw = self.words[slot]
        ptr = raw + 52
        if (self.asm.body_lo <= ptr < self.asm.body_hi
                and self.asm.valid_program(ptr)):
            return (name, 'program', ptr)
        if self.filter_id in PARAM_RAW:
            return (name, 'baked', raw)
        return (name, 'baked', struct.unpack('<f', struct.pack('<I', raw))[0])

    def _parameters_paired(self, spec):
        """Parameters for filters whose bits come in (baked, program) pairs.

        The present parameters occupy the LAST k slots of the block, in spec order. A
        record whose bits imply more parameters than the block has slots is not readable
        either way, so it reports what fits instead of guessing an alignment.
        """
        if len(self.words) < 3:
            return []
        f = self.filter_id
        hit = LAYOUTS.get((f, self.cls, self.words[1] & LAYOUT_MASK.get(f, 0)))
        if not hit or len(hit[1]) < 2:
            return []
        slots = list(hit[1])[1:]
        w = self.words[1]
        present = [nm for nm, pres, _prog in spec if w & pres]
        if not present:
            return []
        out = []
        for nm, slot in zip(present, self._param_slots(hit[1], len(present))):
            if slot < 2 or slot >= len(self.words):
                continue
            # `kind` comes from the slot itself, not from the bit. The bits predict it in
            # 99.966% of reads across the four filters in PARAM_SPEC, so the two almost
            # always agree - and where they do not, what is actually in the slot is the
            # honest answer.
            out.append(self._read_slot(nm, slot))
        return out

    def _param_slots(self, block, count):
        """Which slots `count` parameters occupy, given the layout table's whole block.

        The block is a VARIABLE-LENGTH window anchored on the parameters, not a fixed list.
        `block` is the layout entry entire - its first element is the size-expression slot,
        and whether IT is adjacent to the rest is what says which way the window grows.

        Measured over the 13,417 records where the bits need more slots than the block has:

            block is gapped             grow BACKWARD, into the gap      47 of 50
            block is contiguous
              and the record has room   grow FORWARD             12,953 of 12,954
              and it does not           grow BACKWARD            27,882 of 27,882

        40,882 of 40,886 correct (99.990%), against 40,838 of 40,886 for a rule that asks
        only whether the record has room.

        Reading contiguity off the STRIPPED block instead of the whole one silently
        disables the first case: the only gapped layout in the corpus is `(3, 8)`, whose
        stripped form is the single slot `[8]`, and one slot is contiguous by default. That
        mistake costs 47 of the 48 errors the rule exists to fix, while still looking like
        a working rule.

        Growing forward there puts a parameter in slot 9, which holds values like 9.3e-33
        and 9.2e+12 - not parameters at all. Backward puts it in slot 7, inside the gap the
        layout left, beside the 0, 0, 0.5, 0 that are plainly levels values.

        The 4 remaining errors are 2 distinct records (the corpus holds one of them twice).
        Both are 10 words where the conforming records are 11, and their whole block sits
        two slots earlier - one layout key covering two real layouts, told apart by record
        length. Two records is not enough to derive a rule from, so none is fitted.
        """
        slots = list(block)[1:]
        need = count - len(slots)
        if need <= 0:
            return slots[len(slots) - count:]
        backward = [slots[0] - need + i for i in range(need)] + slots
        if any(block[i + 1] != block[i] + 1 for i in range(len(block) - 1)):
            return backward
        if slots[-1] + need < len(self.words):
            return slots + [slots[-1] + i + 1 for i in range(need)]
        return backward

    @property
    def programs(self):
        """Offsets of every parameter program this record names, in slot order.

        A record can carry more than one. The two-scalar filters put a second program in
        the record's tail - `directionalwarp` has an intensity and an angle, and `warp`,
        `blur`, `distance`, `sharpen`, `normal` and filter 11 do the same. Returning only
        the main slot's program missed 36,614 of them.

        They are read from the slots the layout table names, never by scanning past the
        first program's end: every second program's start appears in a record slot as
        `offset - 52`, in 36,614 of 36,614, so there is nothing to guess. Each program is
        independently self-delimiting through its instruction count, but that is a
        decoder's business, not a way to find the next one.

        Where the layout table has no key, `classified_programs` supplies the slots
        instead. That path used to return whatever the hand-written fallback named, which
        is one slot by construction - see `classified_programs` for what it cost.
        """
        asm = self.asm
        hit = LAYOUTS.get((self.filter_id, self.cls,
                           self.words[1] & LAYOUT_MASK.get(self.filter_id, 0))
                          if len(self.words) > 1 else None)
        slots = list(hit[1]) if hit else []
        sl = self.layout[1]
        if sl is not None and sl not in slots:
            slots.insert(0, sl)
        out = []
        for s in slots:
            if s is None or s >= len(self.words):
                continue
            p = self.words[s] + 52
            if asm.body_lo <= p < asm.body_hi and p not in out and asm.valid_program(p):
                out.append(p)
        if hit is None:
            for p in self.classified_programs():
                if p not in out:
                    out.append(p)

        # Then every OTHER slot that names a program.
        #
        # The slots above come from layouts.json, and this file has since established that
        # the table is both incomplete - 2.85% of records in unseen files have no key at
        # all - and lossy, since its key masks word1 and the mask discards field bits for
        # five filters. A record whose parameter slot the table never learned therefore had
        # its program dropped, and nothing above would notice.
        #
        # What a record names does not depend on the table: a program's start appears in a
        # slot as `offset - 52`, the universal skew, and that is checkable directly.
        #
        #     records with a slot-named program the table path misses   8.50%
        #     programs recovered                                       38,543 of 92,907
        #                                                              records examined
        #     by filter   fxmaps 33,768, blend 1,170, transformation 1,048,
        #                 pixelprocessor 788, directionalwarp 556, levels 460
        #
        # Not coincidence. Slots the layout calls EDGES hold record indices, and they pass
        # `valid_program` 63 times in 95,891 - 0.066%, about one in fifteen hundred.
        #
        # It matters because the missing programs WRITE. Every one of the 25 execution
        # failures left after the width work read a cache index that nothing appeared to
        # write, and in each case the writer was a slot-named program this method did not
        # return. Enumerating them takes those failures to zero.
        seen = set(out)
        for word in self.words:
            p = word + 52
            if p in seen:
                continue
            if asm.body_lo <= p < asm.body_hi and asm.valid_program(p):
                out.append(p)
                seen.add(p)
        # Finally, the record's TAIL. 6,181 records carry a valid size program that NO
        # slot names - most are two words, [count=1][ref.i2][uid], the expression that
        # reads $outputsize - and 93% end flush with the record (0-2 pad bytes). They
        # were found by their first instruction showing up as a u32 "species" in a
        # surplus census, then dissolving under a full-record read. The engine needs no
        # pointer for a program that always abuts the record end; neither does this.
        #
        # The probe is deliberately narrow: only the region AFTER everything already
        # claimed, 4-aligned starts, and only a program whose own length lands within
        # 4 bytes of the record end. Corpus-wide it fires on 6,981 records (0.78%),
        # 95% of them records that had no program at all - the scale the unnamed-pair
        # census predicted, not an explosion.
        hi = self.end
        lo = self.offset + 8
        for q in out:
            if self.offset < q < hi:
                try:
                    lo = max(lo, asm.program_end(q))
                except Exception:
                    pass
        q = (lo + 3) & ~3
        while q + 4 <= hi:
            if q not in seen and asm.valid_program(q):
                try:
                    e = asm.program_end(q)
                except Exception:
                    e = None
                if e is not None and 0 <= hi - e < 4:
                    out.append(q)
                    seen.add(q)
                    break
            q += 4
        # And the HEADER END, the other positional convention. The v2 cooker emits some
        # programs immediately after the header, unnamed by any slot - the mirror of the
        # modern tail placement. Walking valid programs from the rule's header end gains
        # 1,928 programs over 1,549 records, and every one is in a version-0x20000 file:
        # the probe is version-selective by construction, because in later versions the
        # header end already coincides with a slot-named program.
        try:
            import record_layout
            w1 = self.words[1] if len(self.words) > 1 else None
            if self.filter_id == 7:
                ver = asm.header.get('version') if isinstance(asm.header, dict) else 0
                if ver < 0x90000:
                    w1 = None
            elif self.filter_id == 3:
                es = [s for s in self.edge_slots if s < len(self.words)]
                if es and min(es) == 1:
                    w1 = None
            rl = (record_layout.header_words(self.filter_id, self.words[0], w1)
                  if w1 is not None or self.filter_id in (7, 3) else
                  record_layout.header_words(self.filter_id, self.words[0], self.words[1]))
        except Exception:
            rl = None
        if rl is not None:
            q = self.offset + 4 * rl
            while q + 4 <= hi and q not in seen and asm.valid_program(q):
                out.append(q)
                seen.add(q)
                try:
                    q = (asm.program_end(q) + 3) & ~3
                except Exception:
                    break
        # Third and most general: TILING. Unnamed programs are the earliest 4-aligned
        # run of valid programs that tiles - through any slot-named spans - to the
        # record end. This needs no cost spec, which matters because the two probes
        # above fed a circle: normal's spec was REJECTED because 18 records carried
        # unnamed v2 programs, and those records could not be fixed because the
        # header-end probe needs the spec. (The notes' claim that valid_program
        # rejected those programs was wrong - they validate cleanly; the walk simply
        # never started.) The scan is bounded to the first 512 words so a stored-pixel
        # record does not turn this into a quadratic sweep.
        known = sorted(x for x in seen if self.offset < x < hi)
        kend = {}
        for x in known:
            try:
                kend[x] = asm.program_end(x)
            except Exception:
                pass
        first_known = known[0] if known else hi
        q0 = self.offset + 8
        limit = min(first_known, self.offset + 2048)
        while q0 < limit:
            pos = q0
            found = []
            while pos < hi - 3:
                pa = (pos + 3) & ~3
                if pa in kend:
                    pos = kend[pa]
                    continue
                sl = 1 if self.filter_id == 20 else 0
                if asm.valid_program(pa, slack=sl):
                    # A single-instruction candidate must be an input REFERENCE
                    # (oid 0x02) to be claimed. Every real one-instruction tail
                    # program in the corpus is [count=1][ref.*][uid]; the false
                    # positives are baked floats whose u16 phase happens to decode --
                    # 0.25 stored as 0x3e800001 reads as [count=1][op 0x3e80], a
                    # one-instruction const, and 24 directionalwarp records had their
                    # boundary pulled into the header exactly that way, surfacing as
                    # "observed short of rule".
                    cnt = struct.unpack_from('<H', asm.data, pa)[0]
                    if cnt == 1:
                        op1 = struct.unpack_from('<H', asm.data, pa + 2)[0]
                        if op1 & 0x3F != 0x02:
                            break
                    try:
                        e = asm.program_end(pa)
                    except Exception:
                        break
                    found.append(pa)
                    pos = e
                    continue
                break
            if pos >= hi - 3 and found:
                for x in found:
                    if x not in seen:
                        out.append(x)
                        seen.add(x)
                break
            q0 += 4
        return out

    def classified_programs(self):
        """Program offsets read from the record itself, for records with no layout key.

        `MIN = 20` in `derive_layouts.py` drops rare keys from the table, and
        `_compute_layout` then falls through to a hand-written default - one `PROG_SLOT`
        entry, or one slot from `ALT_LAYOUTS`. Every one of those names a SINGLE program
        slot, so a record on that path could not report a second program whatever its
        slots held. `Normalize_RG`'s `pixelprocessor` names its output-size expression at
        slot 3 and the 19-instruction normalisation at slot 4, and only slot 3 came back.

        41,244 records (4.62%) take that path. Probing just the slot after the fallback's
        program slot finds a valid program in 19.54% of them, against 0.02% on known-key
        records with one program slot - so these are real, not the small-integer artifact.

        The predicate is the one already validated: `words[s] + 52` passing
        `valid_program`, whose operand-possibility check is violated by 0.00% of
        instructions in programs a record's slots name and 65% of scan candidates. The
        bound is stated by the record - the header ends where its own bytecode begins,
        observable as the smallest inline program start.

        Measured against the 851,549 records whose key IS in the table, so the answer is
        known: slot set exactly right 99.02%, recall 100.00% (two misses corpus-wide),
        precision 98.51% - and that precision is a floor, since it counts as wrong every
        slot the table does not name, which is the thing this method exists to find.

        `fxmaps` is excluded. Its records run to 331 slots and beyond, which is the
        condition under which any small value is a plausible pointer, and it contributes
        76% of every false positive this predicate makes (13,280 of 17,552) at 90.9%
        precision. Outside `fxmaps` and `pixelprocessor` the predicate runs at 99.8% or
        better. That carve-out costs 586 of the 10,400 programs this recovers; the way to
        get them back is the `fxmaps` header size, not a wider scan.

        Additive only. As a REPLACEMENT for the fallback it is a wash - it gains 10,400
        and loses 10,298, because the header bound cuts off slots the fallback happens to
        reach. Used as a union it gains 10,400 and loses none.
        """
        if self.filter_id == 4:
            return []
        asm, o, e = self.asm, self.offset, self.end
        cand = []
        for s in range(2, len(self.words)):
            p = self.words[s] + 52
            if asm.body_lo <= p < asm.body_hi and asm.valid_program(p):
                cand.append((s, p))
        # The header ends at the first program the record points at INSIDE itself.
        inline = [(p - o) // 4 for _s, p in cand if o <= p < e]
        stop = min(inline) if inline else len(self.words)
        return [p for s, p in cand if s < stop]

    @property
    def filter_programs(self):
        """The programs that compute this filter's behaviour, without the size expression.

        `programs` returns every program the record's slots name, and its FIRST entry is
        usually the record's OUTPUT SIZE expression rather than anything to do with the
        filter. Any analysis of what a filter computes wants this instead; anything
        accounting for bytes wants `programs`.
        """
        out = list(self.programs)
        par = self.size_or_baked
        if out and par and par[0] == 'program' and out[0] == par[1]:
            out = out[1:]
        return out

    def fx_walk(self):
        """The whole FX-Map structure: the node chain, then the table it hands off to.

        Yields ('node', offset, header, program) then ('entry', offset, tag, program),
        with every offset ABSOLUTE - a file position, not relative to anything.

        The two halves used to disagree: `fx_tree` subtracted the record's start and
        `fx_table` subtracted `body_lo`, so one interface returned two coordinate systems.
        Over 2,776 records yielding both kinds, every node offset landed inside the record
        and 2,753 of the entry offsets did not - a 792-byte record reporting a node at +32
        beside entries at +2444, +14116 and +36020. Any caller treating them alike was
        wrong, and `fxdisasm` printed both under the same `+%d`.

        These were treated as two unrelated things, and as two failures: the chain
        "stopped at an unrecognised header" and a third of records "had no readable
        content". They are one structure. A chain does not end with a null next-pointer -
        only 2 of 31,378 do - it ends by pointing at the first table entry, and
        **97.2% of chains end on a word whose low nibble is 8**, which is what a table
        entry is.
        """
        last = None
        for off, hdr, prog in self.fx_tree():
            last = off
            yield ('node', off, hdr, prog)
        start = None
        if last is not None:
            q = last                      # fx_tree yields absolute offsets
            h = struct.unpack_from('<I', self.asm.data, q)[0]
            sh = FX_NODES.get(h)
            if sh:
                nxt = struct.unpack_from('<I', self.asm.data, q + sh[0])[0] + 52
                if self.offset <= nxt < self.end - 7:
                    start = nxt
        for off, tag, prog in self.fx_table(start):
            yield ('entry', off, tag, prog)

    def fx_named_params(self):
        """Yield (entry offset, tag, slot, name, kind, value) for every table parameter.

        `kind` is 'program' or 'baked'; `value` is the program's absolute offset for the
        former and the raw slot word for the latter. `name` is None where the bit's
        parameter is not established -- see FX_PARAM_BITS, which says which those are and
        why they are left blank rather than guessed.

        This is `fx_walk`'s entry half read through the layout instead of through the
        `FX_ENTRY_PROGS` census: the census knows 100 tags and this decodes any tag, which
        is the difference between naming 934 of the corpus's entry programs and 101,617.
        """
        d, lo, hi = self.asm.data, self.asm.body_lo, self.asm.body_hi
        seen = set()
        for kind, off, tag, _prog in self.fx_walk():
            if kind != 'entry' or off in seen:
                continue
            seen.add(off)
            for sl, name, how in fx_entry_layout(tag):
                if off + 4 * sl + 4 > hi:
                    break
                w = struct.unpack_from('<I', d, off + 4 * sl)[0]
                if how == 'baked':
                    yield off, tag, sl, name, how, w
                    continue
                if how == 'inline':
                    # The slot IS the program; its address is not read from the word.
                    at = off + 4 * sl
                    yield off, tag, sl, name, how, (at if self.asm.program_span(at, hi)
                                                    else None)
                    continue
                pv = w + 52
                # A slot the layout calls a program whose word is not one is reported as
                # such rather than skipped: 6.1% of them corpus-wide, and hiding them
                # would turn a known miss rate into an invisible one.
                ok = lo < pv < hi and self.asm.program_span(pv, hi)
                yield off, tag, sl, name, how, (pv if ok else None)

    def fx_node_params(self):
        """Yield (node offset, header, name or None, program offset) for the node chain.

        The counterpart to `fx_named_params`, which does the table half. Names come from
        `FX_NODE_PARAMS`; a header that table does not carry yields `None` for the name
        rather than being skipped, so a caller counting coverage sees the gap.

        Covers 59,892 of the corpus's 66,657 node programs (89.9%). The 6,765 it cannot
        name are `0x1CB` (1,858), `0x99` (150) and the low-byte 0x0B/0x1B families -- none
        of which any permitted source contains.
        """
        for kind, off, hdr, prog in self.fx_walk():
            if kind != 'node' or not prog:
                continue
            names = FX_NODE_PARAMS.get(hdr) or {}
            # `fx_walk` yields the program's ADDRESS, not the slot that named it, so the
            # slot is recovered by reading each candidate back. Subtracting `off` from the
            # address instead silently names nothing, since a program does not sit in the
            # node.
            name = None
            for sl, nm in names.items():
                if off + sl + 4 > self.asm.body_hi:
                    continue
                if struct.unpack_from('<I', self.asm.data, off + sl)[0] + 52 == prog:
                    name = nm
                    break
            yield off, hdr, name, prog

    def fx_table(self, start=None):
        """For filter 4: yield (entry offset, tag, program offset or None) per entry.

        The counterpart to `fx_tree`. A record's slot 2 addresses either a linked node
        chain - walk it with `fx_tree` - or this: a run of consecutive 8-byte entries.
        The two are told apart by whether the first word is a node header.

        Stepping is by eight bytes. Following the entry's own pointer as though it were
        the next entry walks out of the record 77.4% of the time, because that pointer is
        the entry's payload, not its successor.

        A tag not in FX_TABLE yields a program offset of None rather than a guess.
        """
        if self.filter_id != 4 or len(self.words) < 3:
            return
        d = self.asm.data
        q = self.words[2] + 52 if start is None else start
        # Bounded by the BODY, not by this record. A record's extent is a directory
        # partition, not an allocation: 805 fxmaps records address a table that lies
        # outside them, and in 757 of 757 resolvable cases it sits inside an earlier
        # record -- usually a blend or transformation, which cannot own an FX table. The
        # table is a body-level structure and the partition simply attributes it to
        # whichever record precedes it.
        o, e = self.asm.body_lo, self.asm.body_hi
        if not (o <= q < e - 7):
            return
        if start is None and struct.unpack_from('<I', d, q)[0] in FX_NODES:
            return
        limit = 64                       # runaway guard: the longest real walk is 17
        nth = 0
        while q + 8 <= e and limit > 0:
            limit -= 1
            tag = struct.unpack_from('<I', d, q)[0]
            if tag in FX_NODES:
                break
            # THE LAYOUT IS A STOPPING RULE, and it is the only one that catches this walk
            # running into bytecode. The vocabulary test cannot: `0x09130008` is 2,322
            # "entries" whose low 16 bits are in FX_TAG_LOW16 and which are, every one of
            # them, a u32 straddling two instructions -- word +2 is `const.f1`, word +3 is
            # its 1.0 immediate. So ask a question bytecode cannot pass: the tag states
            # where its programs are, so if it names some and NONE of them resolve, the
            # word is not a tag.
            #
            #     layout verdict            entries    lie INSIDE a program's byte span
            #     all predicted resolve      49,528                              0.0%
            #     NONE resolve                3,192                             82.1%
            #     no program predicted       58,848                              0.7%
            #
            # Zero of 49,528 against 2,622 of 3,192, and program spans come from record
            # pointers, so that test knows nothing about the layout. By POSITION the same
            # split appears: 1.1% of FIRST entries fail it against 11.5% of the ones the
            # stride guessed.
            #
            # Applied from the SECOND entry only. The first is at a position established by
            # pointer-following, and stopping there too costs 310 records their table
            # entirely while removing nothing this rule is for.
            #
            # It drops 2,882 entries and 258 entry programs. Note what it does NOT do:
            # vocabulary purity moves 96.64% -> 96.55%, i.e. slightly DOWN, because the
            # junk it removes has in-vocabulary tags. This is the opposite of the failure
            # mode tools/test_fx.py documents, where a walk that gives up early scores
            # better on purity; here the justification is the span test, not a rate.
            if nth and not self.asm.entry_layout_holds(q, tag):
                break
            nth += 1
            # Stop on what is not an entry, not on an entry whose payload is unusable.
            # A table entry's tag ends in nibble 8 -- that is what separates entries from
            # node headers, which end in 9 or 0xB. Stopping when the +4 pointer failed to
            # land in-record instead discarded 1,974 records whose FIRST entry has an
            # unusable pointer, reporting them as having no readable content at all.
            t = struct.unpack_from('<I', d, q + 4)[0] + 52
            # An entry is recognised by EITHER signal: a tag whose low nibble is 8 -- what
            # separates entries from node headers, which end in 9 or 0xB -- or a payload
            # pointer that lands in the record. Requiring the pointer alone discarded 1,974
            # records whose first entry has an unusable one; requiring the nibble alone cut
            # 32,854 entries and 1,026 programs, so words with other nibbles are part of
            # the run too. Neither signal subsumes the other.
            if (tag & 0xF) != 8 and not (o <= t < e - 3):
                break
            slots = FX_ENTRY_PROGS.get(tag)
            if slots:
                # One yield PER PROGRAM SLOT, the way `fx_tree` does it. An entry with six
                # programs was previously reported as carrying at most one.
                any_ = False
                for sl in slots:
                    if q + 4 * sl + 4 > e:
                        break
                    pv = struct.unpack_from('<I', d, q + 4 * sl)[0] + 52
                    if o < pv < e and self.asm.program_span(pv, e):
                        yield q, tag, pv
                        any_ = True
                if not any_:
                    yield q, tag, None
            else:
                off = FX_TABLE.get(tag)
                prog = None
                if off is not None and o <= t < e - 3 and t + off + 4 <= e \
                        and self.asm.program_span(t + off, e):
                    prog = t + off
                yield q, tag, prog
            # The tag states the entry's length; 8 was a guess that happened to be the
            # second commonest. Falls back to 8 for a tag the table does not carry, so a
            # record with an unlisted tag degrades to the old behaviour rather than
            # stopping - but a TERMINAL tag ends the table, which is what it means.
            # An unknown tag STOPS the walk rather than falling back to 8. Falling back
            # keeps 17% more entries and ruins them: the yielded tags then number 9,719
            # distinct values with 81.0% in the vocabulary, against 228 and 96.5% when it
            # stops. A small vocabulary is what a real entry population looks like, so the
            # policy that shrinks it by a factor of 40 is the one telling the truth.
            step = FX_ENTRY.get(tag)
            if step is None or step == 'T':
                return
            q += step

    def fx_tree(self):
        """For filter 4: yield (offset, header, program offset) once PER PROGRAM SLOT.

        NOT once per node, which this said for a long time: a node with two program slots
        (`0x1AB`) is yielded twice at the same offset, so any census built on this
        over-counts multi-program nodes. Count distinct offsets.

        Nodes whose header is not in FX_NODES stop the walk - the vocabulary is open,
        and guessing a node's size to continue past one is how earlier walks wandered
        into bytecode and produced phantom node types.
        """
        if self.filter_id != 4 or len(self.words) < 3:
            return
        d, o, e = self.asm.data, self.offset, self.end
        q, seen = self.words[2] + 52, set()
        pending = []
        while o <= q < e - 7 and q not in seen:
            seen.add(q)
            h = struct.unpack_from('<I', d, q)[0]
            shape = FX_NODES.get(h)
            if shape is None:
                # The second family, keyed by low byte. A 0x1B branches, so the walk stops
                # being a straight line here; `pending` carries the far child and the near
                # one continues inline. Order is not claimed to be the engine's.
                shape2 = FX_NODES2.get(h & 0xFF)
                if shape2 is None:
                    return
                nxts, prog_slots = shape2
                if prog_slots is None:
                    # Scanned, not tabulated. Only for a type whose slots are not fixed
                    # and whose claimed starts are disjoint spans -- see FX_NODES2.
                    for k in range(4, 14):
                        if q + 4 * k + 4 > e:
                            break
                        pv = struct.unpack_from('<I', d, q + 4 * k)[0] + 52
                        if (o < pv < e and self.asm.program_span(pv, e)
                                and (struct.unpack_from('<I', d, pv)[0] & 0xF) not in (9, 0xB)):
                            yield q, h, pv
                    else:
                        pass
                    if not nxts:
                        yield q, h, None
                else:
                    for sl in prog_slots:
                        if q + sl + 4 > e:
                            return
                        p = struct.unpack_from('<I', d, q + sl)[0] + 52
                        yield q, h, (p if (o < p < e and self.asm.program_span(p, e)) else None)
                targets = []
                for n_off in nxts:
                    if q + n_off + 4 > e:
                        return
                    targets.append(struct.unpack_from('<I', d, q + n_off)[0] + 52)
                if not targets:
                    if not pending:
                        return
                    q = pending.pop()
                    continue
                pending.extend(targets[1:])
                q = targets[0]
                continue
            nxt_off, prog_slots = shape
            for sl in prog_slots:
                if q + sl + 4 > e:
                    return
                p = struct.unpack_from('<I', d, q + sl)[0] + 52
                yield q, h, (p if (o < p < e and self.asm.program_span(p, e)) else None)
            if q + nxt_off + 4 > e:
                return
            q = struct.unpack_from('<I', d, q + nxt_off)[0] + 52
            if not (o <= q < e - 7) or q in seen:
                while pending and (not (o <= q < e - 7) or q in seen):
                    q = pending.pop()

    @property
    def matrix(self):
        """For filter 2: the `matrix22` transform, as four float32, or None.

        The matrix occupies four slots starting at `3 + class bit 0 + class bit 7`. Source matrices appear verbatim here in 66 of 72 cases across 23 permitted
        files, the misses being nodes the cooker eliminated.
        The values read as transforms should - `2 0 0 2`, `-1 0 0 -1`, `1.4014 0 0 1.4014`
        - and the off-diagonals are zero in 94% and 76% of records, since most transforms
        scale or flip without shear.
        """
        if self.filter_id != 2:
            return None
        # The matrix starts after the header, and the header grows one slot for EACH of two
        # class bits - bit 0, the static/dynamic flag, and bit 7. The rule is additive, not
        # a choice between two bases. Over the 66,211 records whose slot-1 bit 6 says the
        # matrix is baked:
        #
        #     slot 4 always                        59.2%
        #     slot 4 if class bit 0 else slot 3    83.2%
        #     slot 4 if bit 0 OR bit 7 else slot 3 97.3%
        #     slot 3 + bit 0 + bit 7              100.0%   (66,210 of 66,211)
        #
        # The disjunction and the sum agree except when BOTH bits are set, where the sum
        # says slot 5 and the disjunction says slot 4. 1,795 records read `[pointer, 2, 0,
        # 0]` at slot 4 under the disjunction - a program where the matrix should be - and
        # come out as ordinary transforms at slot 5.
        #
        # `w1` bit 26 scores 100% on the bit-0-clear subset where bit 7 was found, and 53.8%
        # corpus-wide: a coincidence inside a restricted population, tested and dropped.
        base = 4 * (3 + (self.cls & 1) + (self.cls >> 7 & 1))
        if base // 4 + 3 >= len(self.words):
            return None
        m = struct.unpack_from('<4f', self.asm.data, self.offset + base)
        if not all(-1e4 < x < 1e4 and x == x for x in m):
            return None
        # A transform cannot be singular: a zero determinant collapses the image to a
        # line. Records whose slots 4-7 are not the matrix land here and are rejected.
        if abs(m[0] * m[3] - m[1] * m[2]) < 1e-9:
            return None
        return m

    @property
    def translation(self):
        """For filter 2: the `offset` parameter, as two float32, or None.

        Named `translation` because `offset` is already this record's byte offset.

        `transformation` is the one filter whose parameters are MULTI-WORD - `matrix22` is a
        Float4 and `offset` a Float2 - which is why a one-slot-per-parameter model never fitted
        it. `offset` packs immediately after the matrix, four slots along.

        Its bits follow the ordinary pair convention, at 25 and 26 of slot 1:

            bit 25   offset, baked        MCC +0.974 for "this is a parameter slot", 98.7%
            bit 26   offset, a program    MCC +0.994, 99.8%

        They are mutually exclusive - 26,700 baked against 10,692 program, never both. The
        presence bit was found by asking which slots lie inside bytecode the record itself
        names, and confirmed independently by containment: of 96 distinct declared `offset`
        values in the permitted sources, **54 appear in bit-25 records and 0 in bit-25-clear
        ones**.

        Returns None when the matrix is absent: those records have no parameter block to pack
        against, and the slot lands in bytecode 97.4% of the time.
        """
        if self.filter_id != 2 or len(self.words) < 2:
            return None
        w = self.words[1]
        if not (w >> 6 & 1 or w >> 7 & 1):      # no matrix: nothing to pack after
            return None
        if not (w >> 25 & 1):                   # not baked (bit 26 means it is a program)
            return None
        s = 3 + (self.cls & 1) + (self.cls >> 7 & 1) + 4
        if s + 1 >= len(self.words):
            return None
        o = struct.unpack_from('<2f', self.asm.data, self.offset + 4 * s)
        return o if all(x == x and abs(x) < 1e4 for x in o) else None

    @property
    def ramp(self):
        """For filter 0: the gradient's colour ramp, or None.

        A gradient record embeds its ramp as a table of u16 entries:

            slot 2   number of stops
            slot 3   table start - which may lie in a NEIGHBOURING record
            slot 4   an upper bound on the table, usually where the record's program begins

        The entry width follows the channel count - `4 + 2*colour + 2*(class bit 8)` -
        giving 4, 6 or 8 bytes: a stop position followed by one, two or three values.
        The formula holds for 94.4% of the 17,151 records carrying a ramp pointer; the
        rest are recovered by treating slot 4 as an upper bound rather than the exact end.

        Slot 2 is *not* an input edge. It reads as one - a small backward value - but
        its resolution agreement with the record is 35.5%, which is chance, where a real
        edge agrees at ~100%.
        """
        if self.filter_id != 0 or len(self.words) < 5:
            return None
        count = self.words[2]
        start = self.words[3] + 52
        end = self.words[4] + 52
        if not count or not (self.asm.body_lo <= start < self.asm.body_hi):
            return None
        # The table need not lie inside this record. The record directory is a sorted
        # PARTITION, not an allocation - a fact this file establishes elsewhere and this
        # reader used to contradict, by requiring `self.offset < start < self.end`. That
        # rejected 654 records, and every one of them points exactly ONE record back:
        #
        #     one record back    654 / 654        the table fits    654 / 654
        #     positions ascend   654 / 654
        #
        # unanimous on all three. Their stop positions read like `[0, 32768, 33044, 65535]`,
        # a full-range ramp, and the record they point into is usually not a gradient at all
        # (64 of 654) - so this is a table sitting in a neighbour's span, not a shared ramp.
        if not (start < end <= self.asm.body_hi):
            end = self.end if self.offset < start < self.end else self.asm.body_hi
        width = 4 + 2 * (1 if self.colour else 0) + 2 * ((self.cls >> 8) & 1)
        # There is a SECOND ramp encoding, in float32. Its entries are a position followed
        # by the channels and a trailing -1.0 - six floats for colour, three for greyscale:
        #
        #     (0.0,    0.2891, 0.3231, 0.3265, 1.0, -1.0)
        #     (0.0051, 0.2852, 0.3158, 0.3225, 1.0, -1.0)
        #
        # 21 records use it, every one of them class 825, and the split is total: those 21
        # match the float width exactly and never the u16 width, while all 12,879 other
        # gradient records match the u16 width and never the float one.
        #
        # The format is chosen by which width the span matches, not by the class value - 21
        # records is far too thin to name a bit from, and the span says it outright.
        #
        # This also repairs a regression. Relaxing the guard to containment let 11 of these
        # through as u16 tables, since a float table always FITS a u16 reading; they were
        # being reported as ramps and read as nonsense. Exact match has to be tried first.
        fwidth = 4 * (6 if self.colour else 3)
        if (end - start) != count * width and (end - start) == count * fwidth:
            out = [struct.unpack_from('<%df' % (fwidth // 4), self.asm.data,
                                      start + i * fwidth) for i in range(count)]
            if any(out[i][0] > out[i + 1][0] for i in range(len(out) - 1)):
                return None
            return out
        # Slot 4 is not always the table's end. Requiring `end - start == count * width`
        # rejected 968 records; in every one of them the span is LARGER than the table
        # needs, never smaller, and the table fits inside it at the formula width. So the
        # guard is containment, not equality - plus the check that only a ramp can pass:
        # stop positions must ascend. 958 of the 968 do, and those are recovered.
        if start + count * width > end:
            return None
        n = width // 2
        out = [struct.unpack_from('<%dH' % n, self.asm.data, start + i * width)
               for i in range(count)]
        if any(out[i][0] > out[i + 1][0] for i in range(len(out) - 1)):
            return None                     # not a ramp: positions do not ascend
        return out

    # ---- curve specialisation
    @property
    def curve_points(self):
        """For filter 22: the spline's control points, or None.

        A curve record carries its curve inline, the way a gradient carries its ramp:

            slot 1   the image input, and curve's only one
            slot 2   the number of control points
            slot 3   the table, at the universal +52 skew
            ...      one or two more pointers, filter-specific
            last     the point count again

        The table is a u32 count followed by that many 24-byte entries, each six floats.
        The first curve read out is the identity: point 0 at (0, 0) with both tangents
        zero, point 1 at (1, 1) with handles (0.303, 1) and (1, 1) - a position pair
        followed by an incoming and an outgoing tangent, which is a cubic Bezier knot.

        Measured over the 1,519 curve records that declare a count:

            u32 at slot3+52 equals slot 2        1,499   98.68%
            all 6n floats finite and |v| <= 1e3  1,519  100.00%
            x coordinates non-decreasing         1,507   99.21%
            CONTROL: same u32 one word earlier       0    0.00%

        The control is the point. A count-shaped small integer turns up all over these
        records, so "there is a plausible count here" is worth nothing on its own; the
        same probe four bytes earlier had to be able to succeed, and it never does.

        Slot 4 is an upper bound rather than the exact end, exactly as it is for `ramp`:
        span == 24n + 4 holds for 88.55%, and the misses are records where slot 4 is a
        second pointer or where the table simply has room after it. Reading the count
        from the table itself avoids depending on that.
        """
        if self.filter_id != 22 or len(self.words) < 4:
            return None
        n = self.words[2]
        if not (1 <= n <= 16):
            return None
        off = self.words[3] + 52
        if not (self.asm.body_lo <= off and off + 4 + 24 * n <= self.asm.body_hi):
            return None
        if struct.unpack_from('<I', self.asm.data, off)[0] != n:
            return None                     # the table does not confirm the count
        v = struct.unpack_from('<%df' % (6 * n), self.asm.data, off + 4)
        return [tuple(v[i * 6:i * 6 + 6]) for i in range(n)]

    # ---- vector-shape specialisation

    @property
    def vector_shape(self):
        """For filter 5: the vector artwork it generates, as a triangle strip.

        Filter 5 is a generator - 0 resolved edge slots in all 140 of its records - and
        its record begins with a pointer to a payload that nothing else in the format
        points at:

            slot 0   tag
            slot 1   payload start, at the universal +52 skew
            slot 2   payload end, OR a float parameter, depending on the class word
            ...      the payload, where it lies inside the record

        The payload is `[word0][length word][4-byte vertices...]`, and `word0` takes one
        of three values partitioned by the class word: 0x07FFFFFB (cls 9, 25, 1545),
        0x00000003 (cls 9, 537) and 0x04040403 (cls 536). An earlier reading called
        0x07FFFFFB a magic marker and counted the other 22 records as failures. It is not
        a marker, it is a variant field, and all 140 records decode.

        `L = (w + 23) / 2` is the payload's own byte count, as it is for `ramp` and
        `curve_points`; the end pointer, where the class word provides one, bounds it
        rather than stating it. Over the corpus:

            header decodes, length sane, payload a multiple of 4    140 of 140

        Each 4-byte vertex is two u16s, x in the low half and y in the high half, in a
        normalised 0..65535 coordinate space. A trailing all-zero vertex terminates the
        list in 97 of 118 payloads and appears nowhere else in any of them.

        The vertices are a TRIANGLE STRIP, not a path: consecutive triples are faces,
        and strip joins are made with repeated vertices, which is what produces the
        run-length spike this data shows against a shuffle of its own values

            run of 2 identical vertices   10,826 observed     1,624 shuffled
            run of 3                       1,888                379
            run of 5                       2,073                 33

        and which is why x is far more locally coherent than y (median step 432 against
        8,395 out of 65,536): the strip zig-zags across a stroke.

        The evidence that this is artwork is not statistical. Rasterising the triples
        renders the road markings, filigree corner ornaments, snowflakes and hand-drawn
        lettering the materials are named for. See `tools/extract_shapes.py`.

        STRIP is not a guess and not merely the first convention tried. Two independent
        signatures confirm it, and an earlier caveat here is withdrawn.

        **Overlap, by area.** A tessellation's faces partition the shape, so the sum of
        face areas equals the area of their union; overlap makes the sum exceed it.

            convention                 sum of face areas / union area
            strip                          0.983   (range 0.917 - 0.998)
            list (every third triple)      0.505
            fan                          138.313   (range 11.6 - 372.7)

        A previous version of this docstring reported 73.3% of pixels "covered exactly
        once" and called the missing 27% an open residue. That number was measuring the
        rasteriser, not the geometry: adjacent faces in a strip share an edge, and a
        polygon fill paints boundary pixels for both, so every shared edge double-counts.
        Shared edges have zero AREA, which is why this test is the right one. There is no
        residue - `strip` is a clean tessellation and `fan` is refuted 140-fold.

        **Winding.** In a strip, consecutive faces reuse two vertices in swapped order, so
        if the faces are consistently wound their RAW signed areas alternate in sign.
        Nothing else makes that happen.

            consecutive faces with opposite signed area   99.52%  (69,942 pairs)
            CONTROL: the same vertices, shuffled          31.38%

        **Structure.** The payload is a sequence of triangle SUB-STRIPS - 13,512 of them
        across the 140 records, a median of 20 per record - separated by joins made of
        repeated vertices. The join lengths are a parity mechanism, not padding:

            length 2   19,377      preserves the strip's parity
            length 3    3,240      flips it
            length 5    2,651      flips it
            length 4       97      would be redundant with 2, and is duly absent
            length 6      101      likewise

        Even joins longer than 2 are 0.4% of all joins. That is the signature of an
        encoder choosing between "carry on" and "flip", with no reason to emit anything
        else.

        What does NOT hold is parity across the whole payload: correcting each face by
        (-1)^i over the full vertex list agrees with the payload's majority orientation in
        only 81.5% of faces (against 53.8% uncorrected), and just 38 of 140 payloads reach
        100%. So each sub-strip is internally consistent and carries its own winding, and
        a reader must fill per sub-strip or take the union - it cannot rely on a global
        winding rule. Whether that is the encoder's intent or an imperfect reconstruction
        of where its joins actually fall is not settled; it does not affect what renders,
        because a union is orientation-blind.

        **Word 0 is not a format selector.** All three of its values decode with this same
        reader and show the same signatures - alternation 99.17%, 97.29% and 99.95%, and
        the same 2/3/5 join profile. What it does track is the tag's colour bit: the 12
        `0x04040403` records are greyscale in 12 of 12 and never carry the terminator,
        against 0-1% greyscale for the other two values. Twelve records from two files is
        not enough to call that a colour flag, and it is recorded as an observation.

        Returns `(word0, [(x, y), ...])` with coordinates in 0..1, or None.
        """
        if self.filter_id != 5 or len(self.words) < 2:
            return None
        off = self.words[1] + 52
        d = self.asm.data
        if not (0 <= off <= len(d) - 8):
            return None
        kind, w = struct.unpack_from('<2I', d, off)
        n = (w + 23) // 2
        # The payload need not lie inside this record: the record directory is a sorted
        # PARTITION, not an allocation, and 76 of 140 of these point outside their own
        # extent -- 6 of them below the first record entirely. Same as `ramp`.
        if n < 12 or (n - 8) % 4 or off + n > len(d):
            return None
        v = struct.unpack_from('<%dI' % ((n - 8) // 4), d, off + 8)
        # Drop the TERMINATOR only, not every zero. `if x` looks equivalent -- a zero
        # vertex is the terminator in 105 of 140 payloads and interior zeros are rare --
        # but two payloads have a vertex at exactly (0, 0), which is a legal corner, and
        # discarding one shifts the strip's parity for every face after it.
        if v and v[-1] == 0:
            v = v[:-1]
        return kind, [((x & 0xFFFF) / 65535.0, (x >> 16) / 65535.0) for x in v]

    @property
    def vector_faces(self):
        """`vector_shape`'s strip as explicit triangles, with the joins dropped.

        A strip join repeats a vertex, so the triple spanning it is degenerate and
        covers no area. Dropping those is what separates the shape from the stray
        slivers that a naive read of every consecutive triple draws across the joins.
        """
        got = self.vector_shape
        if got is None:
            return None
        _, p = got
        out = []
        for i in range(len(p) - 2):
            a, b, c = p[i], p[i + 1], p[i + 2]
            if a == b or b == c or a == c:
                continue
            out.append((a, b, c))
        return out

    # ---- bitmap specialisation
    @property
    def bitmap(self):
        """For filter 16: either stored pixels or a named graph input.

        Record LENGTH does not decide this. The 8-byte form was read as pixels outright,
        on the reading that the long form names an input and the short form addresses
        raw data - but a third of short records name a declared graph input too, and
        they were being lost: `CHANNELS` has no entry for their channel code, so the
        method returned None for 170 records rather than the input uid.

        What decides it is whether slot 1 CAN be a file offset. A resource offset is an
        offset into this file; a graph-input uid is a 32-bit identifier the cooker
        assigns, and lands far outside it. Over 463 short-form records in 484 paired
        specimens, checked against the uids their own manifest declares:

            slot 1 >= file size  ->  graph input     157 of 157, no false positives
            slot 1 <  file size  ->  pixels          306 of 306

        100% both ways, so the length reading was not merely incomplete, it was the
        wrong discriminator. The 13 records with a channel code `CHANNELS` cannot decode
        (`cls` 0x808, all 2048x2048) sit on the pixels side of that rule and stay there;
        they report `channels: None` rather than vanishing, since where the pixels are
        is known even when their layout is not.
        """
        if self.filter_id != 16 or len(self.words) < 2:
            return None
        asm, v = self.asm, self.words[1]

        def pixels(off):
            hi = (self.cls >> 8) & 0xFF
            ch = CHANNELS.get(hi & 3)
            bpc = 2 if hi & 4 else 1
            return {'kind': 'pixels', 'offset': off,
                    'size': self.width * self.height * ch * bpc if ch else None,
                    'channels': ch, 'depth': bpc * 8 if ch else None}

        # Class-word bit 8 says the record carries its own image rather than naming one.
        # It never names a graph input: 0 of 241 bit-8 records hold a uid their manifest
        # declares, against 1,060 of 1,132 without it. The long-form ones were the last
        # 7 records reported as `graph_input` with a uid no manifest knew.
        if (self.cls >> 8) & 1 and self.end - self.offset != 8:
            body = self.offset + 8
            if asm.program_span(body, self.end) is not None:
                # The image is computed. Grid record 6 is
                #   select(inputref(uid) > 0, 0.0, 1.0)  -- a parameter-driven toggle.
                return {'kind': 'computed', 'program': body}
            for s in range(2, min(len(self.words), 4)):
                if 0 < self.words[s] < len(asm.data):
                    return pixels(self.words[s])       # 3-word form: slot 2 is the offset
            return {'kind': 'inline_pixels', 'offset': body,
                    'size': self.end - body}           # data stored in the record itself

        if self.end - self.offset == 8 and v < len(asm.data):
            return pixels(v)
        return {'kind': 'graph_input', 'uid': v}

    def describe(self):
        name = self.filter_name or ('fid %d (%s)' % (self.filter_id,
                                                     UNNAMED.get(self.filter_id, 'unknown')))
        s = '[%4d] @%-9d %-30s %5dx%-5d %s' % (
            self.index, self.offset, name, self.width, self.height,
            'colour' if self.colour else 'grey')
        e = self.edges
        if e:
            s += '  inputs=' + ','.join('-' if v == 0 else ('?' if v is None else str(v))
                                        for v in e)
        p = self.slot1_flags
        if p and 'blendingmode' in p:
            s += '  mode=%d' % p['blendingmode']
        if self.programs:
            s += '  prog@%d' % self.programs[0]
        p2 = self.size_or_baked
        if p2 and p2[0] == 'float':
            s += '  param=%g' % p2[1]
        mx = self.matrix
        if mx:
            s += '  matrix=[%g %g %g %g]' % mx
        rp = self.ramp
        if rp:
            s += '  ramp=%d stops x%d' % (len(rp), len(rp[0]))
        b = self.bitmap
        if b:
            s += ('  pixels@%d %dB %dch %d-bit' % (b['offset'], b['size'],
                                                   b['channels'], b['depth'])
                  if b['kind'] == 'pixels' else '  input uid=%d' % b['uid'])
        return s


class Assembly:
    def __init__(self, path):
        self.path = path
        self.data = d = open(path, 'rb').read()
        self.header = S.parse(path)
        c, dir_at = self.header['dir_count'], self.header['dir_at']
        if c < 1 or dir_at + 4 * c > len(d):
            raise ValueError('directory out of range')
        ents = struct.unpack_from('<%dI' % c, d, dir_at)
        # Layout B (version 2): body precedes the directory.
        self.layout = 'B' if sum(1 for e in ents if e + 52 < dir_at) > len(ents) // 2 else 'A'
        self.body_lo = 0x38 if self.layout == 'B' else dir_at + 4 * c
        # In layout B the body PRECEDES the directory, so the record body ends where the
        # directory begins. Ending it at table_start instead let the last record's extent
        # swallow the directory and the output table behind it -- which coverage() then
        # reported as 'records', i.e. explained.
        self.body_hi = dir_at if self.layout == 'B' else self.header['table_start']
        offs = sorted(e + 52 for e in ents)
        self.records = []
        for i, o in enumerate(offs):
            nxt = offs[i + 1] if i + 1 < len(offs) else self.body_hi
            if o + 4 > len(d):
                continue
            self.records.append(Record(self, i, o, min(nxt, len(d))))
        # The resource segment ends where the record DIRECTORY begins, not where the
        # first record does. Taking the first record swallows the directory and the
        # output table between them - which is precisely how the output table stayed
        # unread: coverage() relabelled it 'resource segment' and never contradicted
        # itself, because a file with no resources still had bytes there to claim.
        self.resource_end = dir_at if self.layout == 'A' else None
        # The output table: one 8-byte entry per graph output, immediately after the
        # directory in BOTH layouts. Layout A puts the body after the directory so it
        # lands before the first record; layout B puts the body first so it lands before
        # the value table. One rule, two apparent positions.
        self.output_table = (dir_at + 4 * c,
                             min(offs) if self.layout == 'A' and offs
                             else self.header['table_start'])

    # ---- outputs
    # ---- programs
    # ---- outputs
    def outputs(self):
        """The graph outputs, as [(uid, format, grayscale, record index), ...].

        Layout A puts an 8-byte entry per output between the record directory and the
        first record - the region coverage() was calling 'resources', though many files
        with one embed no images at all. One entry per output in 591 of 591 layout-A
        specimens, and the second word is a valid record index in 3,249 of 3,249.

        The first word carries the manifest's `format` attribute as bits 4 and up:
        format == (w0 & 0xFFFF) >> 4, exact on every distinct value in the corpus. Bit 2
        of that format is the grayscale flag - VERIFIED independently: over outputs whose
        identifier names them (roughness, height, metallic vs basecolor, diffuse, normal),
        bit 2 set is 98.5% grayscale against 4.2% when clear. It was recorded as matching
        the colour bit of
        the record the entry names in 3,249 of 3,249 - but that count comes from the
        withdrawn 641-file corpus (tools/DISTINCT.txt, a third duplicates); the 435-file
        corpus yields 2,442 entries, and no bit of words 0-2 of the named record agrees
        better than 59.71%, which is chance for a flag this skewed. UNVERIFIED: the
        grayscale flag is read from the output table alone, and the record-side bit it was
        said to agree with has not been located.

        This is the output-to-record attribution recorded elsewhere in FORMAT-NOTES.md as
        structurally absent. It is not absent; it was in a region nothing had read.

        Entries whose high half is 2 - 48 of 3,249 - are numeric VALUE outputs rather
        than images, and are returned with format `('value', type)`. The manifest declares
        each with a `type` attribute, `typegui="float"` and no format/width/height; the
        entry's low half equals that type in 48 of 48. All 48 name a pixelprocessor.
        """
        if not self.records:
            return []
        lo, hi = self.output_table
        if hi <= lo:
            return []
        uids = self.header.get('output_uids') or []
        out = []
        for j, off in enumerate(range(lo, hi, 8)):
            if off + 8 > len(self.data):
                break
            w0, idx = struct.unpack_from('<II', self.data, off)
            uid = uids[j] if j < len(uids) else None
            if (w0 >> 16) == 2:
                # A numeric VALUE output, not an image: the manifest declares it with a
                # `type` and `typegui="float"` and no format, width or height. The entry's
                # low half is that type code, in 48 of 48 across the corpus, and all 48
                # name a pixelprocessor record - the only filter that computes a number
                # rather than an image.
                out.append((uid, ('value', w0 & 0xFFFF), None, idx))
            else:
                fmt = (w0 & 0xFFFF) >> 4
                out.append((uid, fmt, bool(fmt & 4), idx))
        return out

    # ---- programs
    def valid_program(self, p, slack=0):
        """A program is valid only if it decodes exactly AND its operands are possible.

        Three checks, each of which a run of arbitrary bytes fails:

        1. the declared instruction count decodes to exactly that many instructions;
        2. every opcode is well-formed and its id is one the format actually uses
           (`isa.plausible`) - the raw length rule accepts 47% of all u16 values, which
           is why a scan for programs finds so many that are not programs;
        3. every operand that is a value reference names an EARLIER value. This is
           three-address code, results are numbered contiguously, so an operand at or
           beyond its own instruction's number is impossible.

        Check 3 is the one with teeth. Over programs a record's slots name it is violated
        by 0.00% of instructions; over scan-discovered candidates, by 65%. Without it a
        validator cannot tell a program from bytes that merely decode.
        """
        d, hi = self.data, self.body_hi
        if p + 4 > hi:
            return False
        # 4. the address is even. Instructions are u16 tokens, so a program cannot begin
        # on an odd byte - and the count that check 1 reads is itself a u16. This is the
        # cheapest check and it was missing, which let 142 impossible programs into every
        # figure. They are not evenly spread: over the corpus, 1,915,402 of the 1,915,613
        # programs that transpile start 4-aligned, while misaligned starts are 12% of the
        # 125 that fail - an enrichment of about 1,800x.
        #
        # The requirement is 4, not 2. A pointer is a slot value plus the universal skew
        # of 52, and 52 is 0 mod 4, so a program that begins at a record word boundary
        # arrives 4-aligned. Of the 226 starts that were not, 218 (96.5%) are positively
        # accounted for as not being programs at all:
        #
        #     odd, impossible for a u16 stream                142
        #     even, but the span overlaps a 4-aligned program  74
        #     even, standalone, and malformed - these two are   2
        #       the ONLY remaining truncated-immediate failures
        #                                                    ---
        #                                                     218   of 226
        #
        # Eight are unexplained and are lost by this check. That is the trade taken:
        # 0.0004% of programs against 218 that are demonstrably not programs, one of
        # which was inflating the transpiler's failure list. See FORMAT-NOTES.md.
        if p & 3:
            return False
        # `slack` admits operands up to k + slack - 1: a program whose numbering starts
        # at S = slack, referencing that many values defined BEFORE it. Pixelprocessor's
        # per-pixel function is the case that needs it: value 0 is the implicit POSITION
        # input, so its operands run one ahead of the local count. Measured over the 264
        # big-surplus pixelprocessor records: 0 validate at S=0, 151 at exactly S=1
        # regardless of arity, and the control -- the same S=1 probe at a random aligned
        # offset inside the same regions -- passes 0 of 264. Callers other than the
        # tiling probe leave slack at 0; loosening the default would re-admit exactly
        # the garbage the strict check exists to reject.
        n = struct.unpack_from('<H', d, p)[0]
        if not (1 <= n <= 20000):
            return False
        q, k = p + 2, 0
        while k < n and q + 2 <= hi:
            op = struct.unpack_from('<H', d, q)[0]
            if not isa.plausible(op):
                return False
            L = isa.LEN.get(op)
            oid = op & 0x3F
            imm = disasm.IMM.get(oid)
            if imm != 'all' and L > 1:
                pos = imm or ()
                for i in range(L - 1):
                    if i in pos:
                        continue
                    if oid == 0x0B and i >= 3:
                        # A VALIDATION exemption for the while opcode's trailing
                        # operands, and deliberately not a semantic claim - this
                        # document has adopted and withdrawn readings of those tokens
                        # twice. The fact that forces it: a 185-instruction library
                        # function, byte-identical across five files, carries token 4
                        # = 4096 at instruction 180, which no ordering check can
                        # accept and no honest reading calls a value reference. The
                        # control: exempting tokens 3+ newly admits 0 of 2,622 random
                        # body offsets, and recovers 68 real per-pixel functions.
                        continue
                    v = struct.unpack_from('<H', d, q + 2 + 2 * i)[0]
                    # 0xFFFF is the absent marker, not a value number - the u16 form of the
                    # 0xFFFFFFFF an absent edge uses. Rejecting it as an impossible forward
                    # reference threw away 10 `pixelprocessor` programs in `US_Flag`,
                    # consecutive records at a 356-byte stride, each pointing at a
                    # 56-instruction program inside its own record.
                    #
                    # This does not weaken check 3. Over 622,587 slot targets that land in
                    # the body, 126,700 are valid strictly and allowing 0xFFFF admits
                    # exactly ONE more - the exemption reaches the sentinel and nothing else.
                    if v >= k + slack and v != 0xFFFF:
                        return False
            q += 2 * L
            k += 1
        return k == n

    def entry_layout_holds(self, off, tag):
        """Does the entry at `off` have a program where its tag says it should?

        True when the tag names no program slots -- the layout has nothing to say about
        those, and 58,848 real entries are of that kind. False only when it names some and
        not one of them resolves, which is what bytecode read as a tag looks like. See the
        stopping rule in `Record.fx_table` for the measurement and its control.
        """
        pred = [sl for sl, _n, k in fx_entry_layout(tag) if k == 'program']
        if not pred:
            return True
        lo, hi = self.body_lo, self.body_hi
        for sl in pred:
            if off + 4 * sl + 4 > hi:
                continue
            pv = struct.unpack_from('<I', self.data, off + 4 * sl)[0] + 52
            if lo < pv < hi and self.program_span(pv, hi):
                return True
        return False

    def program_span(self, p, hi=None):
        """End offset of the program at p, or None. Bounded by `hi` when given.

        This is the single definition of "is a program"; `valid_program` is this
        returning non-None. They used to be two implementations of the same idea and
        drifted apart -- this one checked only instruction lengths, so a tightening
        applied to the other silently did not reach the scan that finds most programs.

        That drift had a second instance this docstring did not yet cover: `valid_program`
        exempts the 0xFFFF absent-edge sentinel from the backward-reference check (see its
        own comment -- 10 `pixelprocessor` programs in `US_Flag` point at a slot carrying
        it, not an impossible forward reference), but this function rejected it like any
        other out-of-range operand. `valid_program(p)` could return True while
        `program_span(p)` returned None for the exact same program, which broke the
        "returning non-None" equivalence the two are supposed to have.
        """
        hi = self.body_hi if hi is None else hi
        d = self.data
        if p + 4 > hi:
            return None
        n = struct.unpack_from('<H', d, p)[0]
        if not (1 <= n <= 20000):
            return None
        q = p + 2
        for k in range(n):
            if q + 2 > hi:
                return None
            op = struct.unpack_from('<H', d, q)[0]
            if not isa.plausible(op):
                return None
            L = isa.LEN.get(op)
            oid = op & 0x3F
            imm = disasm.IMM.get(oid)
            if imm != 'all' and L > 1:
                pos = imm or ()
                if q + 2 * L > hi:
                    return None
                for i in range(L - 1):
                    if i in pos:
                        continue
                    v = struct.unpack_from('<H', d, q + 2 + 2 * i)[0]
                    if v >= k and v != 0xFFFF:
                        return None
            q += 2 * L
        return q

    def referenced_programs(self):
        """Every program some 4-aligned word in the file points at, as {start: end}.

        The layout-based `Record.size_or_baked` finds a record's *own* parameter program
        and is the strict reading. It is not the whole story: FX-Map records reach programs
        through their tree, the version-2 prologue holds programs no record slot names,
        and both looked like undecoded regions until this was measured.

        Accepting a program on a reference is permissive, so it was checked two ways:
        recomputing with references from inside program bodies excluded changes the count
        by 66 in 144,273, and only 40 of 88,671 spans start inside another - a clean
        tiling, which chance does not produce.
        """
        d, out = self.data, {}
        # Scan the u32 view rather than unpacking per word: this walks the whole file,
        # and an unpack_from per candidate made the corpus audit four times slower.
        a = memoryview(d)[: len(d) & ~3].cast('I')
        lo, hi = self.body_lo - 52, self.body_hi - 52
        seen = set()
        for v in a:
            if not (lo <= v < hi) or v in seen:
                continue
            seen.add(v)
            q = v + 52
            end = self.program_span(q)
            if end and end > q:
                out[q] = end
        return out

    def strings(self, limit=4096):
        """Text the package embeds, as [u32 count][u32 per character] at 0x38.

        The `text` filter's strings live at the head of the resource segment, ahead of
        the images. Nine specimens carry them and all nine contain filter-17 records.
        """
        d, q = self.data, 0x38
        while q + 4 <= len(d):
            n = struct.unpack_from('<I', d, q)[0]
            if not (1 <= n <= limit) or q + 4 + 4 * n > len(d):
                return
            chars = struct.unpack_from('<%dI' % n, d, q + 4)
            if not all(9 <= c < 0x110000 for c in chars):
                return
            yield ''.join(chr(c) for c in chars)
            q += 4 + 4 * n

    def program_end(self, p):
        d = self.data
        n = struct.unpack_from('<H', d, p)[0]
        q = p + 2
        for _ in range(n):
            q += 2 * isa.LEN[struct.unpack_from('<H', d, q)[0]]
        return q

    def disassemble(self, p):
        return disasm.text(self.data, p, self.body_hi)

    # ---- accounting
    def coverage(self, unreached=True):
        """Classify every byte. Anything unexplained is reported, not hidden.

        **The `unexplained` count is a weak measure and reads far stronger than it is.**
        Record extents are marked accounted for on enumeration, and the record directory is
        a sorted partition of the body, so every body byte is inside some record by
        construction. Reporting 0 unexplained therefore measures the directory's
        completeness, not the segmenter's understanding. The figure to quote is 92.5% of
        record bytes interpreted; see FORMAT-NOTES.md, "0 unexplained bytes was measuring
        the directory".

        `unreached` also credits programs that no record slot points at - FX-Map tree
        programs and the layout-B prologue. It costs a scan of the file; pass False for
        the strict layout-only accounting.
        """
        n = len(self.data)
        seen = bytearray(n)

        def mark(a, b, v):
            a, b = max(0, a), min(n, b)
            if b > a:
                seen[a:b] = bytes((v,)) * (b - a)   # slice assignment, not a Python loop

        mark(0, 0x38, 1)                                   # header
        c, dir_at = self.header['dir_count'], self.header['dir_at']
        mark(dir_at, dir_at + 4 * c, 2)                    # directory
        mark(self.header['table_start'], n, 3)             # value table + footer
        if self.resource_end:
            mark(0x38, self.resource_end, 4)               # resource segment
        mark(self.output_table[0], self.output_table[1], 8)   # output table
        nprog = 0
        for r in self.records:
            mark(r.offset, r.end, 5)                       # record
            for p in r.programs:
                mark(p, self.program_end(p), 6)
                nprog += 1
        # Programs no record slot names: reached through an FX-Map tree, or emitted into
        # the layout-B prologue. Both looked like undecoded regions until measured.
        if unreached:
            for p, end in self.referenced_programs().items():
                if not seen[p]:
                    mark(p, end, 6)
        # Layout B emits a prologue before the first record. It is mostly programs that
        # no record slot names -- one of them binds the graph's random-seed input, and
        # every version-2 package emits the same 72-byte preamble to do it.
        #
        # Scanned on TWO-byte alignment, not four. Programs are not 4-aligned: the
        # alignment pad exists precisely because instructions legitimately sit at 2 mod 4,
        # and a 4-byte scan cannot see half the possible starts. On one specimen that
        # difference was 2% of the prologue understood versus 91%; corpus-wide, 42.7%
        # versus 84.8%.
        if self.layout == 'B' and self.records:
            first = min(r.offset for r in self.records)
            q = max(0, self.body_lo)
            while q + 4 <= first:
                if seen[q]:
                    q += 2
                    continue
                end = self.program_span(q, first)
                if end and end > q:
                    mark(q, end, 6)
                    nprog += 1
                    q = end
                else:
                    q += 2
            # Whatever is still unclaimed is the prologue's index table: (tag, offset)
            # pairs pointing inside it. Named rather than left in 'unexplained', because
            # it is a known structure that is simply not decoded.
            for i in range(max(0, self.body_lo), min(n, first)):
                if not seen[i]:
                    seen[i] = 7
        # bytearray.count is C-speed; counting byte-by-byte in Python made this
        # function 97% of the corpus audit's runtime.
        counts = {v: seen.count(v) for v in range(9)}
        return {'total': n, 'unexplained': counts.get(0, 0),
                'header': counts.get(1, 0), 'directory': counts.get(2, 0),
                'value_table': counts.get(3, 0), 'resources': counts.get(4, 0),
                'records': counts.get(5, 0) + counts.get(6, 0),
                'layout_b_prologue': counts.get(7, 0),
                'output_table': counts.get(8, 0),
                'programs_found': nprog}

    def summary(self):
        cov = self.coverage()
        known = sum(1 for r in self.records if r.known)
        unresolved = sum(1 for r in self.records for e in r.edges if e is None)
        return ('%s\n  version %s  layout %s  %d records  %d inputs  %d outputs\n'
                '  filters known %d/%d (%.1f%%)   programs located %d\n'
                '  unresolved edge slots %d\n'
                '  bytes: %d total, %d unexplained (%.2f%%)%s'
                % (self.path, hex(self.header['version']), self.layout,
                   len(self.records), self.header['n_in'], self.header['n_out'],
                   known, len(self.records), 100 * known / max(1, len(self.records)),
                   cov['programs_found'], unresolved,
                   cov['total'], cov['unexplained'],
                   100 * cov['unexplained'] / max(1, cov['total']),
                   '' if not cov['layout_b_prologue']
                   else ', %d in the layout-B prologue (known gap)' % cov['layout_b_prologue']))


if __name__ == '__main__':
    import sys
    a = Assembly(sys.argv[1])
    print(a.summary())
    print()
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    for r in a.records[:limit]:
        print(r.describe())
