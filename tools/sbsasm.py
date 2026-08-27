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
import os
import struct
import standalone_parse as S
import isa
import disasm

# ---------------------------------------------------------------- filter table

FILTERS = {
    0: 'gradient', 1: 'blend', 2: 'transformation', 3: 'shuffle', 4: 'fxmaps',
    6: 'uniform', 7: 'warp', 10: 'blur', 12: 'directionalwarp', 13: 'sharpen',
    11: 'dirmotionblur', 22: 'curve',
    # COUNT-EXACT ON ONE PERMITTED SPECIMEN, and the earlier note here was wrong. It said
    # filter 8 "cannot be" verified from this corpus, on a measurement that paired every
    # source with an unrelated package's binary -- see `provenance.own_assembly` for how
    # that happened. Paired correctly, 24 of the 26 sources declaring an `emboss` node have
    # filter-8 records in THEIR OWN binary.
    #
    # 23 of those 24 are Allegorithmic-authored and therefore source-excluded, which is the
    # same wall FORMAT-NOTES already records for blur, warp, gradient and fxmaps. The one
    # that is permitted is `Hard-Science-Old__CrustyLava.sbs`, and it is count-exact:
    #
    #     emboss nodes in the source        1
    #     filter-8 records in its binary    1
    #
    # One specimen at 1:1 is thinner than the containment `dirmotionblur` has, and it is not
    # nothing. What is still missing is the PARAMETERS: CrustyLava's emboss node declares
    # none -- every value left at its default -- so there is no declared number to locate in
    # the record, and its two floats (1.92 and 0.56 at words 5 and 6) have nothing to be
    # matched against.
    #
    # A SLOT IS PREDICTED EVEN SO, AND THE PREDICTION IS OUT OF SCOPE. This cited
    # `param_slots.predicted_slot` -- layout start + 1 + bit 7 + bit 11 -- as "verified 38 of
    # 38 on six OTHER filters", and used it to put emboss's float at slot 6 in
    # stone_stylized_adaptive records 6 and 10, both holding 10.0.
    #
    # That verification does not cover these records. `param_slots` now states its own scope
    # in capitals -- THE RULE IS VERIFIED ONLY WHERE cls BIT 0 IS SET, all 34 containment
    # pairings have `cls & 1`, and there are ZERO pairings with bit 0 clear -- and BOTH cited
    # records have `cls = 0x0b198810`, bit 0 CLEAR. So the number quoted here was the one
    # population the rule says nothing about. Corpus-wide the same split runs through this
    # filter: 316 of 546 emboss records are bit-0-clear, so the majority are outside it.
    #
    # How wrong the rule can be off-scope is measured, on `distance`: with bit 0 SET its slot
    # is what the walk enumerates as a parameter in 2,451 of 2,451, and with bit 0 CLEAR it
    # lands on a walk parameter in 11 of 89, on a cls slot in 11, and on a word the walk
    # accounts to no field at all in 67. Prediction on a bit-0-clear record is therefore
    # roughly a one-in-eight shot, not a near-certainty.
    #
    # The 10.0 is left recorded because it is a real number at a real slot and someone will
    # find it again -- but it is NOT evidence, and it was being read as some. It was already
    # a PREDICTION rather than a pairing (no permitted source declares an emboss value, so
    # nothing confirms `intensity` over `lightangle`, and the FORMULA is not established);
    # what is corrected here is that it was also quoting a verification that excludes it.
    # Implementing emboss still needs a permitted source that both pairs and states a value.
        8: 'emboss',
    14: 'hsl', 15: 'levels', 16: 'bitmap', 17: 'text', 18: 'normal',
    20: 'pixelprocessor', 21: 'distance',
    19: 'dyngradient',
    5: 'vectorshape',
    9: 'filter9',
}
# `vectorshape` and `filter9` are PROJECT LABELS, not names recovered from a source file.
# Every other entry above is a name this format's own `.sbs` sources use; these two are not,
# and cannot be, because the permitted vocabulary is exhausted - see PROJECT_LABELS.
PROJECT_LABELS = {5, 9}

# Filters whose PAYLOAD legitimately holds program pointers, so `Record.programs` may not
# bound its slot scan at the header walk's `end` for them: `fxmaps` (4) reaches programs
# through its node/entry tree and `pixelprocessor` (20) through the pixel program's own
# block. For every other filter a word past `end` is bytecode, and reading one as a program
# pointer manufactures phantoms -- see the scan in `Record.programs`.
_PAYLOAD_PROGRAM_FILTERS = {4, 20}

# pixelprocessor records whose arity field names slots that do NOT hold backward record
# indices. The count is believed regardless -- see `_pp_edges` -- and this is the record of
# where that belief was not corroborated. Empty on the 437-file corpus.
_pp_unvalidated = []
# FILTER 9 IS THE ONLY GAP IN 0..22, and it is narrowed to two candidates -- but the name
# below is neither of them. `filter9` names it after its id BECAUSE the id cannot be settled
# from this corpus, and calling it `motionblur` or `svg` on the evidence here would be
# stating a coin toss as a fact. See the provenance paragraph at the end of this note.
#
# THE CENSUS, over all 444 assemblies (the 437-file corpus plus the 7 reference packages),
# 925,706 records. An earlier version of this note said "One record in 30 corpus files
# carries it -- wood_cedar_white record 357"; that was the population then, and it is not
# the population now:
#
#     concrete_085             rec 216   21 words   cls 0x0319   edges [203, 215]
#     granite_001              rec 144   17 words   cls 0x0319   edges [123, 142]
#     granite_001              rec 389    8 words   cls 0x0319   edges [373, 388]
#     wood_cedar_white         rec 357   14 words   cls 0x0309   edges [356, 353]
#     SD_FlickDom_SoftMaple    rec 381   14 words   cls 0x0309   edges [380, 377]
#
# 5 records, 4 files, two class words, every assembly at version 0x20000 -- which confirms
# what UNNAMED used to record as "legacy, version 0x20000 only" and is why that entry is
# retired rather than deleted as wrong. The EDGES note further down states the same 5-in-4
# count; the two disagreed, and this is the one that was stale.
#
# The source vocabulary has five node names this table does not map: `grayscaleconversion`
# (which is filter 3, established), `valueprocessor`, `passthrough`, `motionblur` and `svg`.
# Pairing each permitted source with its OWN binary rules two of them out outright:
#
#     valueprocessor   8 permitted sources declare it (up to 8 nodes)   0 filter-9 records
#     passthrough     25 permitted sources declare it (up to 32 nodes)  0 filter-9 records
#
# A source with 32 `passthrough` nodes whose binary contains no filter-9 record at all is a
# refutation, not a miss. What remains is `motionblur` (3 sources) and `svg` (1), and every
# one of those four is Allegorithmic-authored and source-excluded -- which FORMAT-NOTES
# already records for motionblur in as many words: "Every file in the corpus that uses
# `motionblur` is excluded by the provenance rule". So the id cannot be settled from this
# corpus, and it is two candidates rather than an open field.
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
#
# EMPTY NOW THAT FILTER 9 IS NAMED, and empty rather than deleted because `describe()` and
# `audit_corpus` both still read it and an id can become unnamed again. Its only entry was
# `9: 'legacy, version 0x20000 only'`, whose version claim was checked before retiring it --
# all four filter-9 assemblies report version 131072 -- and now lives in the FILTERS note.
#
# LEAVING IT WOULD HAVE BEEN A LIVE CONTRADICTION, not a leftover: the comment above EDGES
# records exactly that failure for id 19, "an id in both tables is read as known by
# `Record.known` and as unknown by `describe()`". This is the same trap one entry later.
UNNAMED = {}
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
         11: [2], 12: [2, 3], 13: [1], 14: [1], 15: [2], 18: [2], 19: [1, 2],
         21: [2], 22: [1]}
# dyngradient (19) takes TWO inputs -- its unique greyscale input at slot 1 and its shared
# control map at slot 2 -- and slot 2 holds a valid backward record index in 2,225 of 2,225
# records. The default was [1], which made `arity` report one input and left the fallback a
# slot short; the computed edge_slots already read [1,2] through the walk, so this only
# aligns the static default and the arity helper with what the records and the rule agree on.
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


# `HEADER_WORDS` IS STILL BUILT AND NO LONGER READ. Its 666 entries memoised the record's
# header length, which `record_layout.header_words` and the walk's own `end` now compute:
# emptied over the full corpus, 903,616 records with `header_words` non-None on 900,715,
# it changes 0 readings. Kept as the loader's second return so the on-disk layouts.json
# shape is unchanged and the census stays inspectable; nothing consults it.
LAYOUTS, HEADER_WORDS = _load_layouts()

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
# DRAINED, kept as a census. `node_shape` computes every one of these from the header's
# mask -- successor at base + popcount(header & 0xF0) words, programs at word 1 (+word 2 for
# bit 5) -- and the walk now calls it instead of looking here. See `node_shape`. The rows
# stay because their comments record which source node each header is (addnode, markov2) and
# the return type, evidence `node_shape` does not carry.
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
# `0x1CB` RESOLVED, by comparing its program's VALUES against the two conventions it could
# be following. It is `0x18B | 0x40` just as `0x1AB` is `0x18B | 0x20`, so the flag could
# have inserted a `randomseed` before the count the way bit 5 does -- which would put the
# COUNT in the zero at +8 and make the node emit nothing. Opposite conclusions from the
# same bytes, so the values decide:
#
#     0x18B  +4   n=4,936   1.0 x3,431 (69.5%), then 25, 9, 49, 81, 169   <- numberadded
#     0x1AB  +4   n=6       0.0 x6                                        <- randomseed
#     0x1CB  +4   n=183     1.0 x180, 0.0 x3
#
# `0x1CB`'s value distribution is `0x18B`'s, not `0x1AB`'s: 1.0 dominant where randomseed is
# uniformly 0.0. So +4 is `numberadded` and the node iterates once. Its +8 word is zero in
# 179 of 183, which under the pair design is `randomseed` present as a BAKED value of 0 --
# bit 5 the seed as a program, bit 6 the seed baked.
#
# A parallel session reached the same conclusion from return type and pointer layout and
# flagged it as unfalsifiable, since a count of 1 makes iterate-once and pass-through
# identical. The value comparison is what makes it falsifiable: had +4 matched `0x1AB`'s
# seed distribution the reading would have inverted, and it does not.
FX_NODE_PARAMS = {
    0x18B: {4: 'numberadded'},
    0x1AB: {4: 'randomseed', 8: 'numberadded'},
    0x89:  {4: 'switch'},
    0x1CB: {4: 'numberadded'},           # + a baked randomseed of 0 at +8; see above
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
# 0x0B CARRIES ITS SUCCESSOR IN ITS SECOND WORD, and 0x9B is what that word reaches when
# it is not an entry. Over the five reference packages: of 338 0x0B leaves, 328 point at an
# entry (low nibble 8) and 10 point at a 0x19B -- and those 10 records are exactly the ones
# fx_named_params returns nothing for, i.e. every "no readable table entries" failure in
# that set. 0x9B's own slots, measured over all 10 cells:
#
#     +8   in-record, and a program   10 of 10
#     +12  in-record, and an ENTRY     10 of 10
#
# hence ((12,), (8,)) -- successor at word 3, program at word 2, exactly 0x99's shape.
# NOT +4: that word is 0x00003039 in every cell seen, the same literal in two different
# files, and +52 puts it outside the record both times. An earlier read of this scored it
# "resolves to an ENTRY 8 of 10" because the search was body-wide, so a constant landed on
# an unrelated nibble-8 word elsewhere in the file. The record's own extent is the bound
# that matters here, and fx_tree already uses it. walk.py's
# NODE_LEGEND sizes 0x9B at 4 words from an independent measurement, which is a tag plus
# exactly these three slots.
# The LEAF and BRANCH families, keyed by low byte, that `node_shape` does not derive because
# they have no base program+successor structure (low-byte bit 7 clear). Everything else is a
# mask-walk; see `node_shape`. 0x99 and 0x9B were here too and are gone -- they are linear
# nodes the walk now computes.
# 0x0B is gone too: the LEAF's successor is the mask rule's own answer and `leaf_successor`
# computes it, 73 of 73 leaf nodes over 20 files. What is left here is the BRANCH alone --
# two children and a program that no bit of the mask expresses, on two headers, which is not
# a population to derive a rule from.
#
# THE LEAF'S PROGRAMS ARE STILL SCANNED (`prog_slots` None, in `fx_tree`), and that scan is
# a probe of the kind this project otherwise removes: words 4..13, anything whose `+ 52`
# passes `program_span`. Measured over 20 files it yields 266 candidates across those 73
# leaves, 2 to 5 each -- and ALL 266 are named by another node or entry of the same record,
# so it contributes no program the walk does not already reach. Checked non-circularly, by
# excluding the leaf's own yields from the comparison set (including them makes every
# candidate "confirmed" by construction, which is how this first read as 266/266 for the
# wrong reason). Removing it is therefore safe for program COVERAGE but changes which
# programs the leaf EVALUATES as its own, which is a render question and not settled here.
# CORRECTED. The row used to read `((8, 20), (16,))` -- successors at bytes 8 and 20 and a
# program at byte 16, i.e. words 2, 5 and 4 -- and `fxrender` has carried a standing flag that
# this contradicts what it derives. It does, and the flag was right: bytes 16 and 20 are the
# NEIGHBOUR's fields, not this node's. Measured over all 355 0x1B nodes in the corpus plus the
# reference packs:
#
#     (word 2 + 52) - node offset == 12                         355 of 355
#
# So word 2 is this node's one pointer and it addresses word 3 -- the structure immediately
# after a THREE-WORD cell. What sits there is stated by word 1:
#
#     word 1 == 0x3039 (12345)   343 nodes   word 3 is a 0x18B node header, 343 of 343
#     word 1 == 0                 12 nodes   word 3 is a paramset ENTRY tag (low nibble 8)
#
# And for the 343, words 4 and 5 are exactly the neighbouring 0x18B's own program and
# successor -- `FX_NODES[0x18B] = (8, (4,))` measured from the neighbour at +12:
#
#     word 4 holds a valid program                              343 of 343
#     word 5's successor lands inside the record                343 of 343
#
# which is why the old byte 20 always resolved to something in range: it was reading the next
# node's successor. Byte 8 was the only part of the row that was this node's.
#
# The correction changes no reading -- `((8,), ())` and the empty table both differ from the
# old row on 0 of 355 records, because `fx_table` reaches the same entries either way. It is
# made because the row is a STATEMENT about a node's shape and the statement was wrong.
#
# `walk.NODE_LEGEND` reaches the same width independently: 0x1b is 3 words there, derived by
# the landing test over the whole corpus rather than from these bytes.
FX_NODES2 = {
    0x1B: ((8,), ()),   # one pointer, at word 2, addressing the next structure at word 3
}


#: Which low nibbles are FX node headers, and each one's `base` -- the word the successor
#: is counted from before the mask's fields are added. ONE TABLE, SO THERE IS NO CATCH-ALL
#: ARM: this was `nib not in (9, 0xB, 3)` guarding `base = 2 if nib == 9 else 1`, and that
#: `else` would have handed base 1 to any nibble a later reading admitted, silently and
#: without a measurement. A nibble now has to STATE its base to exist here at all.
#:
#: Prompted by a neighbouring session's report on `fx_patterntype`, whose nibble 0 is a
#: catch-all covering two declared source types and 34% of entries, and which failed as a
#: clean zero on one side of a join rather than as an error. The node vocabulary has no such
#: member -- over every header the walk reaches, the low nibbles are exactly 3 (46), 9
#: (27,521) and B (37,196), with no nibble 0 -- so this is the shape of that hazard removed,
#: not an instance of it fixed.
#:
#: WHAT `base` MEANS IS OPEN. Bit 1 of the nibble happens to split these three correctly;
#: that is a three-point fit on a two-valued output and is not written down as a rule, for
#: the reason `leaf_successor` gives about the branch.
NODE_BASE = {9: 2, 0xB: 1, 3: 1}


def node_shape(header):
    """(successor byte offset, (program byte offsets,)) for one FX-Map node header, or None.

    The FX node is the same `[tag/mask][fields]` walk as the record header and the FX entry,
    one scale between them. The low byte's HIGH nibble (bits 4-7) is a presence mask; each set
    bit inserts one field ahead of the successor, so the successor sits at

        base + popcount(header & 0xF0)   words,  base = 1 (low nibble B) or 2 (nibble 9)

    verified 30/30 over every node header seen 10+ times. The bits' fields:

        bit 4  a word ahead of the program (for nibble 9/linear B); on a LEAF it makes a branch
        bit 5  `randomseed` as a program, one word after the base program
        bit 6  `randomseed` baked -- a value word, not a program
        bit 7  the base program+successor structure itself

    Returns None when bit 7 is clear: those are the open-vocabulary LEAF (0x0B) and BRANCH
    (0x1B) families, whose two-child / scanned-program shapes `FX_NODES2` still states by hand.
    Reproduces the retired `FX_NODES` (four whole-word headers) and the linear `FX_NODES2` rows
    (0x99, 0x9B) exactly, and extends to headers neither table listed.
    """
    nib = header & 0xF
    base = NODE_BASE.get(nib)
    if base is None or not (header & 0x80):
        return None
    # NIBBLE 3 IS A NODE, and it was declined by this guard rather than on its merits. Its
    # 23 words in the corpus were being reported as unusable TABLE ENTRIES -- a bucket named
    # for the last test applied, not for what happened -- and the mask rule already predicts
    # every field of them. The specimens are identical across three unrelated files:
    #
    #     slot 0  0x000001a3   header, bit 7 set, mask 0xa0
    #     slot 1  -> +16       addresses its OWN slot 4, an inline program
    #     slot 2  -> +24       addresses its OWN slot 6, an inline program
    #     slot 3  -> 0x89      a GATE node: the successor
    #
    # popcount(0xa0) is 2, so with base 1 the successor is slot 3; bit 4 clear puts the
    # first program at slot 1 and bit 5 adds the second at slot 2. Measured on the words the
    # WALK REACHES, against every other slot as a control:
    #
    #     successor  slot 3   23 of 23   100.0%      every other slot   0.0%
    #     program    slot 1   24 of 24   100.0%      every other slot   0.0%
    #     program    slot 2   23 of 23   100.0%
    #
    # `base` IS STATED PER NIBBLE, NOT DERIVED, and that is deliberate. It is 1 for B, 2 for
    # 9, and must be 1 here. Bit 1 of the nibble splits all three correctly -- and that is a
    # three-point fit on a two-valued output, which is the exact inference `leaf_successor`
    # declines to make for the branch ("two headers is not a population to fit a rule to").
    # What base means stays open; this claims only what the corpus states.
    #
    # UNEXPLAINED AND LEFT OUT: `0x081`, one specimen, bit 7 set and nibble 1. Its predicted
    # successor (slot 2) scores 0 of 1. One word is not a population either way, so it is
    # not swept in with the 23 and it is not claimed against them.
    succ = 4 * (base + bin(header & 0xF0).count('1'))
    # (the bit-7-clear arm of this same rule is `leaf_successor` below)
    pbase = 1 + (1 if header & 0x10 else 0)          # bit 4 shifts the program one word on
    progs = [4 * pbase]
    if header & 0x20:                                # bit 5: randomseed program follows
        progs.append(4 * (pbase + 1))
    return (succ, tuple(progs))


#: A pointer cell is three words -- `[header][next][payload]`. The corpus states it rather
#: than this choosing it: of the cells the walk reaches, 362 carry a forward next-pointer and
#: every one of them steps exactly 3 words, with 0 stepping anything else. The 62 that carry
#: none are last in their list, and take the width the other 362 establish.
POINTER_CELL_WORDS = 3


def pointer_cell_successor(header):
    """Where a POINTER CELL says the structure continues -- byte offset, or None.

    Two bit-7-clear families are neither nodes nor entries. They carry no program and draw
    nothing; each one holds a pointer and the structure goes on at the other end of it:

        nibble 9, bit 7 clear    the CHAIN cell (`0x09`, `0x49`) -- 05d472e's "0x9 IS a
                                 structure". Slot 1 is its next in the list; slot 2 is the
                                 pointer to the list's shared payload.
        nibble B, bit 6 set,     the `0x?4B` cell that slot 2 lands on, which in turn
        bit 7 clear              addresses the table entry.

    Both continue at SLOT 2, and both were being reached by hand: `fxrender`'s
    `_chain_embedded_entries` allowlisted `(0x09, 0x49)`, read `off + 8` as a constant,
    and stepped over the `0x?4B` by a hardcoded 12; `fx_walk` computed `q + 12` for the
    `0x1B` handoff and used the cell's own pointer only to confirm it. Following the
    pointer retires all of that.

    THE SLOT IS NOT THE MASK RULE, and that matters because `node_shape` derives every
    other successor here from the mask. Measured on cells the walk ARRIVES at:

        0x09   mask -> slot 2   59 of 59   100.0%
        0x49   mask -> slot 3    0 of 6      0.0%      (slot 2: 6 of 6)

    Bit 6 inserts a field for the bit-7-set family and does not for these, so a mask
    popcount would be a regression on `0x49`. Slot 2 is the slot after the header and the
    next-pointer -- the 3-word extent `chain_extent` reads, 3 words in 60 of 60 records
    whose root is one of these cells.

    That the pointer, not an offset, is the thing to follow is what separates this from the
    constant it replaces. Over the 53 `0x?4B` cells the structure reaches (43 through a
    chain cell's slot 2, 10 as a record root), following each slot and asking whether the
    target passes `entry_layout_holds`:

        slot 1   45 of 53   84.9%        slot 3    0 of 53    0.0%
        slot 2   52 of 53   98.1%        slot 4   17 of 53   32.1%
                                         slot 5    1 of 53    1.9%

    and slot 2 addresses the cell + 12 in only 7 of those 53. The `12` was one sub-case's
    layout, not the rule; the other 46 point elsewhere entirely and would be missed.

    UNEXPLAINED, and left visible: one of the 53 (a `0x14b`) fails `entry_layout_holds` at
    slot 2 and no reading is offered for it. Nor is it established what the chain LIST is
    for -- every cell's slot 2 addresses the same shared `0x?4B`, so the list's length
    feeds nothing read here.
    """
    if header & 0x80:
        return None
    nib = header & 0xF
    if nib == 9 or (nib == 0xB and header & 0x40):
        return 4 * (POINTER_CELL_WORDS - 1)
    return None


def pointer_cell_payload(asm, off):
    """A pointer cell's payload slot, as a byte offset -- ASKED OF THE CELL.

    `pointer_cell_successor` answers from the family width. This answers from the cell,
    which is the same discipline `chain_extent`'s own comment states: the element stores
    its next at slot 1, so `next - self` IS its width, and its payload is its LAST slot.

    Over every list the walk reaches, the two readings never disagree:

        pointer cells stating a width      362    all of them 3 words, none anything else
          last slot == slot 2              362 of 362
          last slot's target holds         362 of 362
        stating no width                    62    last in their list (slot 1 null or
                                                  backward), so they take the family width

    So `4 * (POINTER_CELL_WORDS - 1)` is not a fitted 8: it is the last slot of a cell whose
    width the corpus states 362 times and contradicts none. Reading the width per-cell
    matters anyway -- a cell that ever states 4 words should have its payload read at slot 3,
    because the cell is the authority and the family width is only what every cell has said
    so far. Widths outside a cell's plausible range fall back rather than being followed: a
    far-forward next-pointer is a statement about LIST POSITION, not width, which is exactly
    why `chain_extent` returns the raw distance and leaves the decision here.
    """
    step = chain_extent(asm, off)
    if step is None or step % 4 or not (8 < step <= 4 * (POINTER_CELL_WORDS + 1)):
        step = 4 * POINTER_CELL_WORDS
    return step - 4


def chain_extent(asm, off):
    """The byte extent of a chain element that states its own next at slot 1, or None.

    The FX chain's elements are a linked list: each stores the next element's address, in
    the format's usual `- 52` skew, at slot 1. That step IS the element's extent, so an
    element states its own width without a table and without a stride.

    Measured over 80 files on the `0x9`/`0x49` family and the `0x?4B` family they hand off
    to: 94 of 108 have a forward pointer there, and where they do the step is 3 words in 82
    of 94 (and 60 of 66 for `0x?4B`). The rest are last in chain and point far forward,
    which is why this returns the raw distance and leaves the caller to decide -- a huge
    extent is a real statement about a real pointer, not a value to clamp.

    Returns None when slot 1 does not point forward inside the body, which is the honest
    answer for an element that states nothing rather than a guessed default.
    """
    lo, hi = asm.body_lo, asm.body_hi
    if not (lo <= off < hi - 8):
        return None
    nxt = struct.unpack_from('<I', asm.data, off + 4)[0] + 52
    return (nxt - off) if off < nxt < hi else None


def leaf_successor(header):
    """The bit-7-clear LEAF's successor byte offset, or None -- `node_shape`'s other arm.

    `node_shape` declines when bit 7 is clear, because bit 7 is what declares the base
    program+successor structure it walks. For the LEAF (nibble B, bits 4-7 all clear) the
    successor is still exactly what the mask says it is:

        4 * (base + popcount(header & 0xF0))   with base = 1 for nibble B

    which is 4 -- word 1 -- because the mask bits are clear by the guard. That is the same
    number `FX_NODES2[0x0B]` stated by hand, now arrived at by the rule rather than
    written down, and it holds on all 73 leaf nodes over 20 files.

    THE HIGH BITS ARE NOT PART OF THIS. Corpus leaves carry wildly different upper words --
    0xC0B, 0x510B, 0x1B90B, 0x3C10B, 0xE100B and eleven more, 18 distinct headers over 77
    nodes -- and every one has bits 4-7 clear, so the rule reads the same shape from all of
    them. What those upper bits mean is not decided here; this claims only the successor.

    The BRANCH (0x1B, bit 4 set) is deliberately NOT derived. Its shape is two children and
    a program -- `FX_NODES2` states (8, 20) and (16,) -- and while the mask rule does give
    its FIRST child correctly (popcount 1 -> 8), nothing in the mask expresses the second
    child at word 5 or the program at word 4. Two headers is not a population to fit a rule
    to, so it stays hand-stated and visible rather than derived from two points.
    """
    if (header & 0xF) != 0xB or (header & 0xF0):
        return None
    return 4 * (1 + bin(header & 0xF0).count('1'))


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
# Filters whose parameters are placed by the structural walk rather than by the LAYOUTS
# memo: `blend` (1), `dirmotionblur` (11) and `directionalwarp` (12).
#
# (This comment said blend was NOT here, while the set below contained it. Corrected by
# reading the set rather than the prose -- a stale comment about which arm is live is the
# same failure mode as a stale figure, and this file has been bitten by that before.)
#
# `fxmaps` (4) is the one still on the memo, and its blocker is not width-zero fields: its
# cost-model entry has `const: None` and NO w1 dictionary at all, so `decompose` routes it
# through `_fxmaps_walk`, which returns `param_slots: []`. There is nothing for the walk to
# place its four parameters WITH. Migrating it means deriving those positions first.
#
# `levels` (15) IS NOT HERE AND WAS: it wins every structural comparison and REGRESSES THE
# RENDER. See `Record._parameters_walked`, which is kept precisely so the next attempt
# starts from the evidence rather than from the idea.
# `blend` (1) is here on the evidence in the commit that added it, which supersedes both
# 77a01d1's "not chosen" note and my own revert of it. The disagreement was about what the
# memo's `opacitymult` slot IS on records whose w1 field reads state 3:
#
#     the field's slot holds a backward record index   8,486 of 8,486   -> it is an EDGE
#     the memo's opacitymult slot is the LAST class slot    373 of 373
#     the memo's opacitymult kind on those records          always 'program', never baked
#
# So the memo is counting back one slot from its block end -- its documented rule -- and
# landing on an inherited-parameter slot when the field declares an image input and there
# is no own-parameter to find. Nothing is lost by declining it: `programs()` still returns
# that program, and render reads `opacitymult` only when its kind is 'baked'.
# `fxmaps` (4) is here on a structural arbiter and a knockout, not on a render score. The
# memo attributes header parameters to it; over 150 files not ONE of those slots lies inside
# the header it is attributed to:
#
#     past the walk's end, in payload   40,054      the prog/size slot   9,618
#     past the record entirely               8      an input edge            6
#     inside the walked header               0
#
# That is `walk_partition`'s invariant failing outright -- the memo is claiming payload words,
# which belong to the FX tree and entry table, as though they were slots in the record header.
# `_fxmaps_walk` reports no header parameters at all, and it is right to.
#
# Nothing reads them either: emptying fxmaps' named_parameters changes 0 of 12,632 rendered
# records, because render's fxmaps branch takes its parameters from `fxrender`'s entry table
# and never touches this. So routing fxmaps here drops 40,054 misattributions and costs
# nothing.
WALKED_PARAMS = frozenset({1, 4, 11, 12})

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

# Filters whose PARAM_SPEC program bit is VERIFIED EXACT against what the slot holds, so
# `_read_slot` can read the kind from the header instead of probing the word. Full corpus:
# blend 179,524 reads, levels 168,077, directionalwarp 117,657 -- 465,258 reads, ZERO
# disagreements. `fxmaps` (1.516%, and its own entry admits two of its four pairs are ~97%)
# and `dirmotionblur` (one record, and that one is a LAYOUTS slot error rather than a bit
# error -- see `_read_slot`) are deliberately absent and keep reading the slot.
BIT_EXACT_KINDS = frozenset({1, 12, 15})

# Records where the program bit and the slot contents disagree on a BIT_EXACT_KINDS filter.
# Empty on the 437-file corpus; an entry on a new one is a finding to investigate, not a
# slot to guess at.
_kind_conflicts = []


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


# The two FX-Map entry tags whose inline program is NOT where the entry layout says.
#
# `fx_entry_layout` states where an inline program sits -- it follows the parameters, at
# `4 x (the first slot the layout does not use)`, measured from the ENTRY. Over the whole
# corpus that rule and the withdrawn `FX_TABLE` never once disagree (2,620 agreements, 0
# disagreements), so for twenty of that table's twenty-two tags the lookup was restating
# what the layout already said. Those are gone. These two are what is left:
#
#     tag           entries  files   program at   why the layout rule misses it
#     0x00020018        136     37   entry +32    its +4 word points to entry+12, not
#                                                 entry+8, in 98% of entries -- the base
#                                                 the rule assumes is wrong here
#     0x0A800048        123     45   entry +28    base is entry+8 as usual, but the
#                                                 program sits one slot PAST the inline
#                                                 slot the rule predicts (7, not 6)
#
# Both were re-derived over all 437 corpus files by sweeping word offsets 0..15, not
# inherited: 97.8% and 94.3% of their entries put the program at that one offset, against
# runners-up of 2.2% and 11.4%, and neither lands inside another program's byte span in
# any entry. 44.5% of entries decode at two or more swept offsets, so "a position that
# decodes" is worth nothing on its own -- what carries these is that the winner is the
# same position for every entry of a tag, and that the containment control is 0 of 2,900
# where the walk's own stopping rule measures 82.1% for the population it rejects.
#
# `0x0A800048` is a live discrepancy, not a special case: the layout rule is off by one
# slot for it and the reason is not known. It is tabled here so the walk stays right while
# that stands.
# `0x0A800048` IS GONE FROM HERE, verified dead rather than argued away. Knocking each row
# out separately over the whole corpus, comparing every `fx_walk` output on all 41,164
# fxmaps records:
#
#     drop 0x0A800048    41,164 identical,   0 differ     <- carries nothing
#     drop 0x00020018    41,031 identical, 133 differ     <- load-bearing
#
# It was tabled for a discrepancy that no longer exists. Its note said "the program sits one
# slot PAST the inline slot the rule predicts (7, not 6)", and `fx_entry_layout` now returns
# `(7, None, 'inline')` for that tag -- the layout rule caught up at some point and the row
# was left behind. A row kept for a fixed problem reads exactly like a row kept for a real
# one, which is why they have to be knocked out rather than re-read.
#
# `0x00020018` STAYS, and what it is standing in for is now measured. Of its 796 entries,
# 133 put a program at the tabled offset, and on all 133 A WORD OF THE ENTRY POINTS AT THAT
# SAME ADDRESS -- word 7, unanimously, 0 reachable only by the constant. So the byte offset
# is standing in for a pointer the entry stores.
#
# That does NOT make swapping the constant for "word 7" an improvement: the entry's layout
# is empty for this tag, so word 7 is not derived from anything either. It is one fitted
# constant for another, and the readings are identical on all 133. Left alone until the tag
# says where its program is.
#
# The over-reach here does NOT repeat the `0x1B` story, and the check that would have made
# it look as though it did is the one worth recording. On 9 of the 133, word 7 lies PAST the
# next entry's start -- the same shape as a node reading its neighbour's fields. But every
# one of those 9 programs is UNIQUE to this entry: 0 of 9 are also yielded by the structure
# they appear to belong to. Bounding the read would delete 9 programs nothing else finds,
# not deduplicate 9 misattributions. Uniqueness cuts both ways -- 9 real programs no other
# structure names, or 9 phantoms no other structure confirms -- and this does not separate
# them, so the bound is not applied.
# THE ONE HAND-STATED PROGRAM OFFSET LEFT, and the entry appears to state it itself.
# `fx_table` reaches this only when the tag declares no program slot, and 0x00020018 is
# the only tag in it -- the comment at `fx_table` calling it "the two tags whose
# self-pointer base the inline rule reads wrong" is stale by one.
#
# Every attribution it makes is also stored by the entry: over 80 files it fires 8 times,
# and in 8 of 8 the address it computes (`t + 20`) equals the word at the entry's slot 7
# read as a pointer. So the constant reproduces a pointer already present in the data, and
# deriving it would drain the last hand-stated row here.
#
# NOT DERIVED YET, because it turns on an unsettled question. `walk_partition` reports
# these 8 as the whole of its remaining FX violations, against a 3-word extent taken from
# the entry's slot-1 step -- and a slot 7 cannot be inside a 3-word entry. Either the
# extent is wrong for this tag, or slot 7 belongs to a later chain element and the equality
# is telling us something about the neighbour instead. `fx_entry_layout(0x00020018)`
# declares NOTHING at all, so it is not the source of a slot-7 reading either way; a
# higher-bit variant `0x00420018` occurs in the same records and DOES declare a program, at
# slot 4.
#
# Recorded rather than acted on: which tag the contradiction is against has to be settled
# before the 8 mean anything.
FX_PAYLOAD_PROG = {
    0x00020018: 20,                       # BYTE offset from the entry's +4 pointer
}


# FX-Map table entry LENGTH, stated by the whole tag word. `'T'` means the entry is the
# last in its table.
#
# DRAINED, kept only as a census. `fx_table` no longer steps this stride: the entries are a
# LINKED LIST, each storing a pointer to the next -- the header slot reaching furthest forward,
# past the entry's own inline program -- and the walk follows it. The entry ends at its inline
# program, whose length the program states in its own first word (`_program_span_scan` reading
# the `u16` instruction count), so the extent is structural and not a per-tag constant. This
# table was a FIT of that pointer's distance, lossy because the distance is the inline
# program's length, which the tag does not encode; following the stored pointer reaches 77,637
# real entries the strided walk stopped short of, with zero phantoms. See `fx_table` and the
# FORMAT-NOTES section "The FX entry table is a linked list".
#
# The 8-byte stride this once replaced was not a stride. Measured from a chain handoff -- the
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
# `FX_TABLE` was the earlier attempt at this: 22 tags, one offset each, derived when
# entries were enumerated by stepping 8 bytes. That population was unsafe and the result
# was withdrawn; re-derived on a clean population, all but two of its tags turned out to
# restate the entry layout, and those two are now `FX_PAYLOAD_PROG` above. With entries
# walked by the tag-stated length instead, the same question has a much sharper answer --
# the tag does not merely suggest an offset, it DETERMINES the set:
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
#
# DRAINED, and kept only as evidence. `fx_table` no longer consults this census: a nibble-8
# tag's program slots come from `fx_entry_layout` (the bit-walk), which reproduces every one
# of the 24 census tags the corpus actually reaches and extends to the tags the census never
# saw; a nibble-9/B "tag" is a 0x0B-family node, read by the disjoint-span scan `fx_tree`
# runs, which is +3,480 programs over the census because a node's slots vary per instance
# (0x0000190B is (4,7) in 129 nodes and (5,6,7,8) in 124 -- one fixed slot list cannot be
# right for both). What is left below is a table of MEASURED slot positions, still checked
# against the layout by `test_entry_layout_agrees_with_the_census`; it drives no reading.
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


# SIX VALUES ADDED, and they were already stated elsewhere in this file. `FX_ENTRY_PROGS`
# is keyed by whole tags and its keys imply 27 distinct low-16 values against this set's 17;
# eight of the difference end in nibble B and are NODE headers rather than entry tags, but
# six are entry-shaped and were simply missing here: 0x0158, 0x0658, 0x0948, 0x0958, 0x0A48,
# 0x0A58. Two tables in one file disagreeing about the same vocabulary.
#
# What the omission cost, over all 367,077 entries `fx_walk` yields corpus-wide:
#
#     low 16 in this set, as it was      329,942    89.88%
#     covered by the six additions        35,225     9.60%
#     still unaccounted                    1,910     0.52%
#
# The structure argues for them rather than just the count. `fx_patterntype` reads NIBBLE 2
# of this word, and the note by FX_PATTERNTYPE_SHIFT observes that "FX_TAG_LOW16's nibble 2
# takes 0-8 and B-E, thirteen values, which is what a pattern-shape enum looks like from
# outside". The six supply exactly the two values that were missing from that range -- 9 and
# A -- so nibble 2 becomes 0 through E CONTIGUOUS, fifteen values with no holes. An enum
# with two gaps in the middle is a sign of unobserved cases, not of an enum with two gaps.
# (The additions also introduce nibble 1 = 5, where this set had only 4 and 8.)
#
# Safe to widen: this set is NOT the entry walk's stopping rule -- the layout is, and
# `fx_table` breaks on `node_shape` and on a tag whose predicted programs do not resolve.
# It is read by the vocabulary test and by the two `0x1B` handoff guards, both of which were
# REJECTING valid tags while it was short.
FX_TAG_LOW16 = frozenset({
    0x0008, 0x0018, 0x0048, 0x0088, 0x0148, 0x0158, 0x0248, 0x0288, 0x0348,
    0x0448, 0x0548, 0x0648, 0x0658, 0x0748, 0x0848, 0x0948, 0x0958, 0x0A48,
    0x0A58, 0x0B48, 0x0C48, 0x0D48, 0x0E48,
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
# BITS 19..30 ARE SIX (baked, program) PAIRS, one per parameter -- the same design
# `PARAM_SPEC` documents for filter records and `directionalwarp`'s slot-1 field, at a third
# scale. The even bit of a pair means "this parameter is a pointer to a program"; the odd
# bit below it means "this parameter is a value baked in place", and its width is the
# parameter's own type.
#
# The roles alternate perfectly. Reading each bit's assigned slot and asking whether it
# holds a program pointer or a plain value, over every entry in the corpus:
#
#     bit 19    2,633    0.5% program        bit 20   13,746   99.6% program
#     bit 21        8   12.5%                bit 22   46,050   99.9%
#     bit 23      153    0.0%                bit 24    9,200   99.9%
#     bit 25    8,694    0.0%                bit 26   12,939   99.8%
#     bit 27    1,814    0.0%                bit 28   15,834   99.9%
#     bit 29    1,240    0.2%                bit 30      -     (program, see above)
#
# CORRECTED: bits 21 and 23 were published here as programs, on the grounds that they were
# "never set in any observed tag". They are set -- 8 and 153 entries -- just never in the 57
# census tags the layout was fitted on, so the fit had nothing to say and the default stood.
# Measured at their own slots they hold values, not pointers, 0.0% of the time for bit 23
# against 99.9% at both its neighbours.
#
# THE WIDTHS ARE THE PARAMETERS' OWN TYPES, which is what identifies the pairing rather
# than merely permitting it. Each width below was fitted from slot positions alone, before
# any of this was hypothesised, and each matches the declared type of the parameter the
# even bit names:
#
#     bit 19 -> 1 word    opacity          Float1
#     bit 21 -> 2         branchoffset     Float2     (width not pinned; see below)
#     bit 23 -> 2         frameoffset      Float2
#     bit 25 -> 2         patternsize      Float2
#     bit 27 -> 1         patternrotation  Float1
#     bit 29 -> 1         patternsuppl     Float1
#
# Bit 23's width is pinned directly: over the entries that set it and carry a program bit
# above it, width 2 puts every one of those programs where a program is, in 23 of 26 -- and
# width 1 in 0 of 26. Bit 21 is set in 8 entries and never with a program above it, so its
# width is inferred from its partner's type and not measured; it is the one row here that
# is a guess, and it is flagged as such.
#
# The value distributions agree independently: bit 27 is quarter-turn multiples beside
# `patternrotation`, bit 25 is never negative with p50 3.0 beside `patternsize`, bit 23 sits
# at 0.5 beside `frameoffset`, bit 29 lies in [0, 1] beside `patternsuppl`. A parallel
# session reached the same pairing from mutual exclusivity -- 100.00% for all six pairs
# against a 78-99% control on the other phase -- with no names and no source containment.
#
# BIT 19 IS THE WEAK ROW. Its values run to +-1e13 with a median of -1, which is not what an
# `opacity` looks like, so either its slot is misassigned for some tags or the pairing does
# not extend to it. Named with that stated rather than left blank, because the width, the
# alternation and the exclusivity all point the same way.
FX_PARAM_BITS = (
    (4,  None,              1),   # leading baked words; which parameters they are is
    (7,  None,              1),   # not established -- only that each takes one slot,
    (16, None,              4),   # except this one, which takes FOUR: see below
    (17, None,              1),   # which is what fixes where the program run starts
    (19, 'opacity',         1),   # baked forms. See the pairing note above; bit 19 is the
    (20, 'opacity',         1),   # weakest row and bit 21's width is inferred, not measured
    (21, 'branchoffset',    2),
    (22, 'branchoffset',    1),
    (23, 'frameoffset',     2),
    (24, 'frameoffset',     1),
    (25, 'patternsize',     2),
    (26, 'patternsize',     1),
    (27, 'patternrotation', 1),
    (28, 'patternrotation', 1),
    (29, 'patternsuppl',    1),
    (30, 'patternsuppl',    1),
    (31, 'imageindex',      1),
)

# The bits whose parameter is stored as a POINTER to a program rather than baked in place.
# The odd bit of each pair carries the same parameter as a value; see FX_PARAM_BITS.
FX_PROGRAM_BITS = frozenset({20, 22, 24, 26, 28, 30, 31})

# STRUCTURAL bits: they consume a slot but that slot is NOT a parameter.
#
# `FX_PARAM_BITS` listed bits 4, 7, 16, 17 and 19 together as "leading baked words", and
# `fx_entry_layout` emitted a `(slot, None, 'baked')` row for each. Reading what those slots
# actually hold, over 120 files, splits them cleanly in two:
#
#     bit  4     613   denormal (pointer-shaped) 85.6%   a plausible float 12.9%
#     bit  7     304   denormal 95.7%                    points at a program 4.3%
#     bit 16     170   denormal 85.3%
#     bit 17  16,179   denormal 99.5%
#     bit 19     477   A PLAUSIBLE FLOAT 53.7%   zero 42.6%   denormal only 3.8%
#
# A denormal is what a POINTER looks like read as float32 -- the trap this document records
# three times. So 4, 7, 16 and 17 are header or pointer words: they occupy space, which is
# why their widths are needed to place the program slots that follow, but calling them
# baked parameters was wrong. Bit 19 is the exception and stays a parameter, which is
# consistent with it being `opacity`'s baked form in the pair table above.
#
# The concrete damage this did: `0x00020008` is the corpus's commonest tag, its only
# parameter bit is 17, and the emitted row landed at slot 2 of an entry that is eight bytes
# long -- `[tag][self-pointer]`, with nowhere to put a parameter. A parallel session counted
# 3,983 entries whose stated length is too short for the bits the layout claims, and 3,960
# of them are that tag. The `FX_ENTRY` clip added earlier hid the symptom; this removes the
# cause. Program-slot positions are unaffected, because those depend only on the widths.
FX_STRUCTURAL_BITS = frozenset({4, 7, 16, 17})

# PARAMETERS A TABLE ENTRY NEVER STORES, however the source declares them.
#
# `patterntype` decides the pattern's SHAPE and `blendingmode` decides how it combines, so
# a renderer needs both, and the natural assumption is that an entry carries them. It does
# not -- not as a baked field, and not as a program even when the source declares one.
#
# The test is set subtraction with the counts as its own check. Predict an entry's stored
# parameter set as "the source paramset's declared DYNAMICS minus this set", and compare
# against the name-sets `fx_entry_layout` reads out of the compiled entries:
#
#     ie_pcloud   3 dyn -> 3 stored   {frameoffset, opacity, patternsize}          108 entries
#                 6 dyn -> 4 stored   + patternrotation                              1
#                 7 dyn -> 5 stored   + imageindex                                   1
#     ie_curve    5 dyn -> 5,  7 dyn -> 5,  4 dyn -> 4        all present, exact
#     ie_particles 5 dyn -> 4,  4 dyn -> 4                    all present, exact
#
# Every row lands on a name-set the compiled file actually has, and the two six- and
# seven-dynamic paramsets are short by exactly two -- `blendingmode` and `patterntype`,
# both declared as function graphs and neither given a slot.
#
#     dropping this set                              11 of 13 source signatures reproduced
#     dropping {blendingmode, patterntype} alone     10
#     CONTROL: the best of the other 44 name pairs    8
#     CONTROL: median over all 45 pairs               2
#     dropping nothing -- the naive reading           7
#
# This closes a route that looked live: `ie_pcloud` declares `patterntype` as a PROGRAM in
# two paramsets, which would have named it by elimination if the compiled entry had a sixth
# slot to put it in. It has four and five. So `patterntype` and `blendingmode` are not in
# the FX table at all, and looking for them there -- in a baked field, in the tag's nibbles,
# in a program slot -- is looking in the wrong structure.
FX_UNSTORED_PARAMS = frozenset({
    'patterntype', 'blendingmode', 'imagefiltering', 'imagepremul', 'randomseed',
    'colorswitch',
})

# ...BUT `patterntype` IS IN THE FILE. It is nibble 2 of the tag, offset by two.
#
# "Not in the parameter block" is not "not in the file" -- the engine has to know which
# shape to draw. It is in the tag itself, at bits 11:8, as `patterntype - 2`.
#
#     file                    declared    nibble 2    pt - 2
#     Bruno_Caustics             9            7          7     <-- the one that carries it
#     triDraw                    3            1          1     <--
#     ie_curve                   1            0         (0)
#     ie_particles               2            0          0
#     ie_pcloud                  2            0          0
#     Simulator__Grid            2            0          0
#
# Seven of seven usable files, and the weight is entirely on the first two rows, because
# nibble 2 is not uniformly distributed. Over 20,929 parameter-carrying entries:
#
#     nibble 0   62.4%      nibble 1    1.0%      nibble 7    0.4%
#
# So `triDraw` landing on a 1.0% value and `Bruno_Caustics` on a 0.4% value, both exactly
# at `pt - 2`, is the evidence; the four files at nibble 0 are consistent but prove little
# on their own. Chance for those two together is about 4e-5.
#
# WHY THIS WAS MISSED TWICE. A parallel session tested `nibble 2 == patterntype` and
# falsified it correctly -- `ie_particles` declares 2 and its nibble is 0 -- and I recorded
# that falsification as closing the question. Both of us tested the un-offset form. `pt - 2`
# is 0 for that specimen, so the counter-example was never one.
#
# THE SOFT SPOT, stated because nibble 0 is the catch-all: `patterntype` 1 and 2 BOTH map
# to 0, and so does a `patterntype` the source declares as a function graph (`ie_particles`
# has one of each and both entries read 0). So the offset is not established below 3, and
# nibble 0 cannot be read back as a specific pattern. What is established is that the field
# is here, and that it separates 3 and 9 from the default.
#
# The vocabulary agrees with an enum of this size: FX_TAG_LOW16's nibble 2 takes 0-8 and
# B-E, thirteen values, which is what a pattern-shape enum looks like from outside.
FX_PATTERNTYPE_SHIFT = 8
FX_PATTERNTYPE_BIAS = 2


def fx_patterntype(tag):
    """The entry's `patterntype`, or None where the encoding does not determine it.

    Returns None for nibble 0, which is the catch-all: `patterntype` 1, `patterntype` 2 and
    a source-declared function graph all land there. See FX_PATTERNTYPE_BIAS.
    """
    n = (tag >> FX_PATTERNTYPE_SHIFT) & 0xF
    return None if n == 0 else n + FX_PATTERNTYPE_BIAS


# Bits whose presence means an INLINE program sits after the parameter slots -- one the
# entry stores in its own bytes instead of pointing at. See `fx_entry_layout`.
FX_INLINE_BITS = frozenset({25, 27, 29})


def fx_entry_walk(tag):
    """[(bit, slot, name, kind, width)] for one FX table entry tag -- the single walk.

    `fx_entry_layout` and `fxrender.baked_slots` were two implementations of this, and the
    second's docstring claimed it "mirrors sbsasm.fx_entry_layout's walk exactly -- same
    table, same order". It did not. `fx_entry_layout` gives `FX_STRUCTURAL_BITS` their own
    branch -- advance the cursor, emit nothing, "occupies space, is not a parameter" -- and
    `baked_slots` had no such branch, so it emitted structural bits as baked parameters.
    Over 20 files and 82 distinct entry tags the two disagree on 37, every disagreement a
    structural bit (4, 16 or 17) that one reports and the other does not.

    NOTHING RENDERED DIFFERENTLY, and that is why it survived: `baked_slots`' only caller
    looks each bit up in `PARTNER`, a structural bit has none, and the extra rows were
    dropped one line later. Both walks also advanced the cursor identically, so the SLOT
    POSITIONS never diverged -- only the membership of the list. That is the benign case of
    a duplicated walk and not one to rely on: the same duplication in the baked-parameter
    READ cost 928 entries their second component (see the width-2 note), and that one had to
    be found by containment rather than by the two implementations disagreeing loudly.

    `kind` is 'program', 'baked' or 'structural'. The inline-program row `fx_entry_layout`
    appends is not here -- it is a property of the whole tag, not of any one bit.
    """
    out, sl = [], 1
    for bit, name, width in FX_PARAM_BITS:
        if not (tag >> bit) & 1:
            continue
        if bit in FX_PROGRAM_BITS:
            sl += 1
            out.append((bit, sl, name, 'program', 1))
        elif bit in FX_STRUCTURAL_BITS:
            out.append((bit, sl + 1, name, 'structural', width))
            sl += width
        else:
            out.append((bit, sl + 1, name, 'baked', width))
            sl += width
    return out


def fx_entry_walk_end(tag):
    """First slot the walk does not use -- what the inline-program rule measures from."""
    sl = 1
    for bit, _name, width in FX_PARAM_BITS:
        if (tag >> bit) & 1:
            sl += 1 if bit in FX_PROGRAM_BITS else width
    return sl


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
    out = [(sl, name, kind) for _b, sl, name, kind, _w in fx_entry_walk(tag)
           if kind != 'structural']
    sl = fx_entry_walk_end(tag)
    # THE INLINE PROGRAM. `FX_TABLE` recorded, for 22 tags, "the byte offset of the
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
    # WITHDRAWN: a clip against `FX_ENTRY`'s stated length used to sit here.
    #
    # It was added because `0x00020008` -- the commonest tag, 50,965 entries -- put a baked
    # row at slot 2 of an entry that is eight bytes long, and that word is the NEXT entry's
    # tag 96.5% of the time. The clip suppressed it. `FX_STRUCTURAL_BITS` then removed the
    # cause: bit 17 is a pointer word, not a parameter, so that tag now yields [] on its own
    # merits and the clip has nothing to do there.
    #
    # Measured afterwards, its only remaining effect was harm. Over 120 files it changed
    # exactly one tag, `0x95540288`, and:
    #
    #     clipped     16,353 predicted program slots resolve, 73 do not
    #     unclipped   16,613 resolve, 125 do not
    #
    # It was discarding 260 programs that resolve in order to suppress 52 that do not,
    # because `FX_ENTRY` states that tag is FOUR bytes -- a tag and nothing else -- while
    # its observed cell is 32 bytes in 36 of 36 sightings and five of its six predicted
    # slots hold real programs. A length claim standing alone against a structure claim
    # corroborated 1,715 times is the one that is wrong.
    #
    # The 52 that did not resolve are `0x95540288`'s slot 8, bit 31 (`imageindex`). An
    # earlier reading called these the entry's TRAILING program written inline and had
    # `fx_named_params` recover them by reading the slot as bytecode when its pointer failed.
    # That was WRONG, and value-driven: it decided the field's structure from whether
    # `word` happened to decode. Measured against the entry boundary, all 1,910 such
    # "inline programs" that have a following entry begin PAST the next entry's tag -- they
    # are bytecode from a later structure, not a field here. So bit 31 in a short entry is an
    # OVER-PREDICTION: the tag names a slot the entry is not long enough to hold, and its
    # pointer duly fails to resolve. `fx_named_params` reports that as a miss (None), it does
    # not manufacture a program. This function still emits the `'program'` row; the caller's
    # pointer read is what correctly comes up empty.
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
    __slots__ = ('index', 'offset', 'end', 'tag', 'cls', 'asm', '_words', '_layout', '_programs')

    def __init__(self, asm, index, offset, end):
        self.asm, self.index, self.offset, self.end = asm, index, offset, end
        w0 = struct.unpack_from('<I', asm.data, offset)[0]
        self.tag, self.cls = w0 & 0xFFFF, w0 >> 16
        self._words = None
        self._layout = None
        self._programs = None

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
        n = (self.tag >> 12) & 0xF
        # `cls & 0x2000` is a 4x-AREA flag the tag height nibble omits: 11 bitmaps across the
        # corpus (PlanksSubstance003, BricksSubstance004, NightSkyHDRI, pbr_render) set it and
        # ALL 11 store an image exactly 4x their tag-declared area -- 0 false positives against
        # ~570 normal bitmaps (cls 0x108-0x718, bit clear). The extra factor is height x4: for
        # PlanksSubstance003 rec50 the 4 MB slot is one contiguous 2048x512 image (no stacking
        # discontinuity at the declared 128-row boundary), and the row-continuity test favours
        # height x4 across all measured specimens. Without this the decoder reads the top
        # quarter of each. Gated on filter 16 so only bitmaps are touched.
        if self.filter_id == 16 and (self.cls & 0x2000):
            n += 2
        return 1 << n

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
        # The unified structural walk is the primary layout computation now: it returns the same
        # (edges, prog) as the five special cases below, proven 0-diff on every consumer -- edges
        # 926,882/926,882, and size_or_baked and programs() both 0 changes corpus-wide -- and its
        # prog already carries the edge-XOR-program rule (prog is None when its slot is an input).
        # `_compute_layout` stays only for the records decompose does not cover (the unnamed
        # filter 9). See tools/decompose.py and FORMAT-NOTES.md "Unified walk".
        import decompose as _decompose
        _d = _decompose.decompose(self)
        if _d is not None:
            self._layout = r = (list(_d['inputs']), _d['prog'])
            return r
        edges, prog = self._compute_layout()
        edges = self._real_edges(edges)
        # A slot is an edge XOR a program, never both. The _ruled branch fixes the program
        # at `2 + base`, which is right until a state-11 field puts a mask edge there: 300
        # blend records (5 words, [tag][w1][in][in][mask]) then have no program at all, yet
        # `prog` still named the mask slot. The mask slot holds a backward RECORD INDEX, and
        # that is the test -- not `valid_program`, which false-positives on two of them whose
        # index (12, 32) happens to point +52 into the header where the bytes decode as a
        # short program (`programs` then reported 0x40 and 0x54, offsets that sit BEFORE the
        # record). A real program pointer is a large body offset, never a small backward
        # index: pixelprocessor's over-read edge list names slot 11 an edge too, but slot 11
        # holds 9812, no record index, so its genuine program survives. Where the named
        # program slot holds a valid backward record index, it is an edge and there is no
        # program: drop it.
        if (prog is not None and prog in set(edges) and prog < len(self.words)
                and self.words[prog] < self.index
                and self.words[prog] < len(self.asm.records)):
            prog = None
        self._layout = r = (edges, prog)
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
        if f == 7 and len(self.words) > 3 and self.words[1] != 0 and 3 in slots:
            # The shift's premise is that slot 3 stops being an edge and becomes the
            # PROGRAM pointer (with slot 1 the real edge). Gate it on that premise rather
            # than on w1 != 0 alone: a v9 warp can carry a genuine nonzero w1 parameter and
            # still have the ordinary [2,3] layout with its programs at slots 4-5 -- there
            # slot 3 is a backward input index, not a program, and shifting drops a real
            # edge (OnyxSubstance001 rec955: slot 3 = record 954, slots 4-5 the programs;
            # the walk read [2,3] and this shift wrongly made it [1,2]). Fire only when slot
            # 3 actually resolves as a program.
            q3 = self.words[3] + 52
            if self.asm.body_lo <= q3 < self.asm.body_hi and self.asm.valid_program(q3):
                return sorted({1} | {s for s in slots if s != 3})
        if f == 0 and 2 in slots:
            return sorted({1} | {s for s in slots if s != 2})
        if f == 22 and 2 in slots:
            return [1]
        return slots

    # Filters whose size-expression slot sits two words past the inputs, a colour ramp
    # (gradient) or stop table (curve) occupying the gap.
    _RAMP_FILTERS = frozenset({0, 22})

    def _walk_layout(self):
        """(edges, prog) computed by the mask-walk for the class-word-driven filters, or
        None to fall through to the table.

        Covers the filters `layouts.json` used to decide by lookup. Edges are the fixed
        base shape from `walk.TIER_A_EDGES` (a stated bit discriminates warp and distance);
        the size-expression slot follows the inputs. Returns None -- deferring to the table
        -- for `text`, whose slot layout is not yet catalogued, and for any record whose
        edges fail the backward-index invariant, so a wrong shape never displaces the table.
        """
        import walk as _walk
        f = self.filter_id
        if f == 17 or f not in _walk.TIER_A_EDGES or len(self.words) < 2:
            return None
        ver = self.asm.header.get('version') if isinstance(self.asm.header, dict) else 0
        edges = _walk._tier_a_edges(f, self.words[0], self.words[1], ver)
        n = len(self.asm.records)
        for s in edges:
            if s >= len(self.words):
                return None
            v = self.words[s]
            if not (v == 0xFFFFFFFF or v == 0 or (v < self.index and v < n)):
                return None
        if f == 6:                                   # uniform: no input, size expr at slot 1
            prog = 1
        else:
            prog = (max(edges) + 1) if edges else 2
            if f in self._RAMP_FILTERS:
                prog += 2
        if prog >= len(self.words):
            prog = None
        return (list(edges), prog)

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
        #
        # The shape is STATED by the tag, not probed: tag bit 0 is clear for the single-input
        # shape (slot 1 is that input) and set for the shape whose slot 1 is the four-byte
        # channel-selector word, with the two inputs at slots 2 and 3. This is the same bit
        # `header_words` reads for shuffle's w1 presence, so the two paths now agree. Over 437
        # files it matches the old value probe on 7,631 records and CORRECTS 18: `Cliff` and
        # `Bitmap2Material_3` records whose selector word is 0x400 (a `channelgreen: 4`
        # selector), a small integer the probe misread as a slot-1 edge -- in all 18 the
        # tag-stated slots 2 and 3 hold valid backward record indices.
        if f == 3 and len(self.words) > 3:
            if not (self.words[0] & 1):
                return ([1], 2)
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
                # No LAYOUTS union here any more: measured over every _RULED record, the
                # memo's edge list adds exactly ZERO real slots beyond what the w1-field
                # walk above already found (the union's only past contribution was the 10
                # spurious dirmotionblur slot-1 edges, since removed). The walk states the
                # edges in full, so the table is redundant for these four filters and is
                # dropped -- one of the LAYOUTS memo's uses drained.
                return (list(edges), prog)

        # The class-word-driven filters: their edges are a fixed base shape (a stated bit
        # discriminates the two-shape ones) and their size-expression slot follows the
        # inputs, so `walk` computes what `layouts.json` used to memorise. Guarded by the
        # backward-index invariant: where the computed edges do not all hold a valid
        # backward record index the walk yields, and this falls through to the table.
        wl = self._walk_layout()
        if wl is not None:
            return wl

        # pixelprocessor states its input count in the low nibble of slot 1, so its edges
        # and program slot come from that nibble, not the memo. `_pp_edges` is the same
        # computation `edge_slots` uses, shared so `layout[0]` and `edge_slots` agree
        # (they disagreed on 370 records while the table served one and the nibble the
        # other). Only the records whose nibble does not validate fall through to the
        # table below -- draining the memo for the ~58k clean ones.
        if f == 20:
            e = self._pp_edges()
            if e is not None:
                return (e, 2 + len(e))

        # transformation (2) and bitmap (16): both are in walk.SPECS but were never wired
        # into _compute_layout, so they fell straight to the memo. The walk reproduces the
        # model's edge_slots on every record (0 disagreements over 240k transformation and
        # 1,346 bitmap), and each has one program slot right after its inputs -- slot 3 for
        # transformation (the matrix), slot 2 for bitmap -- present as a program iff that
        # slot resolves as one. So the memo is redundant for both.
        _spec_prog = {2: 3, 16: 2}.get(f)
        if _spec_prog is not None and len(self.words) > 1:
            import walk as _walk
            try:
                w = _walk.walk(_walk.SPECS[f], self.words[0], self.words[1],
                               len(self.words))
            except _walk.Overrun:
                w = None
            if w is not None:
                sl = _spec_prog
                if sl >= len(self.words):
                    sl = None
                elif f == 16:
                    q = self.words[sl] + 52
                    if not (self.asm.body_lo <= q < self.asm.body_hi
                            and self.asm.valid_program(q)):
                        sl = None
                return (list(w.edge_slots), sl)

        # The LAYOUTS memo lookup used to sit here, keyed by (filter, cls, w1 & mask). It is
        # gone: pixelprocessor is handled by `_pp_edges` above, transformation and bitmap by
        # the walk above, and blend/levels/dirmotionblur/directionalwarp by `_ruled`. What
        # reached this lookup otherwise -- vectorshape, text, and the odd short record --
        # gets the identical answer from the fixed-shape fallbacks below, verified by
        # emptying the whole memo and finding 0 edge and 0 program changes corpus-wide.
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
            # word 0 bit 0: the low tag byte is 0x07 for the shape carrying a w1 word
            # and 0x06 for the shape without one. The edge-run detector this replaces
            # was wrong on 51 of 7,682 records.
            if not (self.words[0] & 1):
                w1 = None
        ver = self.asm.header.get('version') if isinstance(self.asm.header, dict) else 0
        n = record_layout.header_words(self.filter_id, self.words[0], w1, version=ver)
        if n is not None:
            return n
        # THEN THE WALK, AND THE MEMO IS DEAD BEHIND IT. `decompose` states the same
        # quantity structurally -- its `end` is where the slots stop and the code begins,
        # which is this property's own definition -- so it belongs ahead of a lookup.
        #
        # Measured over corpus.paths() PLUS the reference packs, which are DISJOINT
        # populations (437 files against 8, zero overlap) and had to be counted together
        # because most censuses in this repo see only the first and every render score
        # comes from the second:
        #
        #     the rule answers          900,544 of 900,859 corpus   33,426 of 33,436 packs
        #     rule silent                   315                          10
        #       ..memo answers                0                           0
        #       ..walk answers              171                          10
        #
        # The memo answers NONE of the 325 records that reach it. Its key is
        # (filter, cls, w1 & LAYOUT_MASK) and it is documented above as lossy; what this
        # adds is that on the population it exists to serve it is not merely lossy but
        # empty. It is kept below rather than deleted because deleting a table is a
        # separate change with its own knockout, and `test_every_table_is_load_bearing`
        # does not currently cover it.
        #
        # The 181 the walk recovers are all `emboss`, and the answer is admissible on every
        # one: 2 <= end <= len(words) in 181 of 181, inputs [2, 3] matching emboss's base
        # arity of two, ends of 4 to 7 words inside records of 13 to 83. `vectorshape` (139)
        # and `filter9` (5) stay unanswered -- the walk is silent there too, which is an
        # absence rather than a guess.
        try:
            import decompose as _decompose
            _d = _decompose.decompose(self)
            if _d is not None and _d.get('end') is not None:
                return _d['end']
        except Exception:
            pass
        # THE `HEADER_WORDS` MEMO USED TO BE THE FALLBACK HERE, AND IS DRAINED. It held 666
        # keyed entries of the same quantity the walk computes, and over the FULL corpus --
        # 903,616 records, `header_words` non-None on 900,715 of them -- emptying it changes
        # 0 readings. The walk answers everything it answered.
        #
        # Measured through the accessor it serves, not through a general sweep: a sweep of
        # six other readings also scored `SHARED` at 0 in the same pass, and `SHARED` is LIVE
        # on 277 readings once `shared_refs` is actually called. A knockout is evidence only
        # for the readings it exercises.
        return None

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
        # The unified structural walk (decompose) is the single mechanism for input edges; it
        # reproduces this computation exactly across every covered filter and returns None only
        # for filters it does not cover, which fall through to the existing path. See
        # tools/decompose.py and FORMAT-NOTES.md "Unified walk".
        #
        # FXMAPS IS NOW COVERED TOO, so the fx path runs on the same walk as everything else.
        # It used to be declined outright -- "payload/table filter, not a header walk" -- and
        # the two facts that close it are exact over 25 files and 1,535 records: the input
        # COUNT is the cost model's own `arity_sm` field read from w1 (shift 10, mask 15),
        # matching the edge count 1,535 of 1,535, and the inputs are contiguous from slot 3
        # with slot 2 holding the FX table pointer. Over the same corpus the walk now agrees
        # with this computation on 27,663 of 27,663 records across every filter present, the
        # single exception being one record of the unnamed filter 9.
        import decompose as _decompose
        d = _decompose.decompose(self)
        if d is not None:
            return d['inputs']
        e = self._pp_edges()
        if e is not None:
            return e
        return self.layout[0]

    def _pp_edges(self):
        """pixelprocessor edges from the arity nibble of slot 1, or None to fall to the
        table. The count is the low nibble; inputs occupy slots 2 onward. Shared by
        `edge_slots` and `_compute_layout` so the two agree -- the table used to serve
        `layout[0]` while the nibble served `edge_slots`, and they disagreed on 370
        records. Returns None for any filter but 20, or when the nibble does not validate.

        The count is the low NIBBLE, not the whole word: reading the whole word works only
        while no other bit of slot 1 is set (437 records have one, and in all of them slots
        2..2+nibble hold a backward record index). The cap is 16, the width of the field --
        capping at 8 stranded 81 records with a declared arity of 9, 12 or 13, all of whose
        slots 2..2+k-1 hold a backward record index.
        """
        if self.filter_id != 20 or len(self.words) < 2:
            return None
        n = self.words[1]
        if 1 <= n <= 8 and len(self.words) >= 2 + n:
            return list(range(2, 2 + n))
        if n == 0:
            return []                      # a generator: no image input at all
        # The count field is FIVE bits (0..16), not the low nibble: 16 needs bit 4, and a
        # nibble reads 16 (0x10) as 0. ie_curve record 233 is the one record where this
        # bites -- w1 = 0x10, and its bytecode references 21 input uids over slots 2..17,
        # a clean block of backward record indices, so its true arity is 16, which the
        # memo had recorded as a generator's empty edge list. Reading five bits fixes it
        # and touches no other record (0x1F == 0xF for every count below 16), while the
        # bit-16+ flag words (0x10000, ...) still take & 0x1F == 0 and fall through here.
        k = n & 0x1F
        if 1 <= k <= 16 and len(self.words) >= 2 + k:
            # THE COUNT DECIDES; the slots are only OBSERVED. This arm used to require
            # `all(0 <= words[2 + j] < index)` before believing the count -- a value test on
            # the very slots the count names, and the last one left in this filter's path.
            #
            # Over the full 437-file corpus it fires 521 times and rejects 0. That is the
            # same perfect zero the two probes in `Record.edges` scored before they were
            # removed, and for the same reason: it re-tests a predicate the header has
            # already settled. Arm 1 above -- 54,849 records -- never consulted a value at
            # all, so the two arms disagreed about whether `words[1]` is to be trusted.
            #
            # Not deleted, SURFACED. A record whose named slots do not hold backward indices
            # is a finding about a new corpus, not a slot to fall back on quietly, so it goes
            # in `_pp_unvalidated` the way an unknown (filter, field) goes in
            # `decompose._probe_fallback`. Empty on this corpus; inspect it if it fills.
            if not all(0 <= self.words[2 + j] < self.index for j in range(k)):
                _pp_unvalidated.append((self.filter_id, self.index, n, k))
            return list(range(2, 2 + k))
        return None

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
            # ANYTHING ELSE IS A MISS, REPORTED AS ONE. A forward index, or one past the
            # end of the record table, is genuinely unexplained and stays visible rather
            # than being absorbed into a catch-all.
            #
            # Two VALUE PROBES used to sit here and have been removed: "if `v + 52` passes
            # `valid_program` the slot is a program, not an edge", and "if `v` reads as a
            # float in 1e-6..1e6 it is a baked value, not an edge". Both asked what a word
            # LOOKS like in order to decide what it IS, which is the one thing this parser
            # is not allowed to do -- and both were legacy from the era when the layout
            # came from `layouts.json`, which genuinely did not determine whether a given
            # key's slot was an edge in a given record. `edge_slots` now routes through the
            # structural walk (`decompose`), which answers that question before the value
            # is ever consulted, so the probes were second-guessing an accessor that had
            # already decided.
            #
            # Verified redundant before deleting, per-branch rather than in aggregate --
            # an aggregate zero is what made two probes look dead once before when the
            # accessor was simply raising. Over the FULL 437-file corpus, 1,302,039
            # walk-named edge slots:
            #
            #     backward record index (the edge)       1,301,922
            #     0xFFFFFFFF absent sentinel                   117
            #     "looks like a program" probe                   0
            #     "looks like a float" probe                     0
            #     slot past record end / unexplained             0
            #
            # and `edges` before/after the removal is identical on all 903,616 records.
            #
            # WHY THEY WERE DEAD IS NOT "the format guarantees a backward index" -- that
            # reading would be circular, and stating it here would bank the circularity.
            # `decompose._is_image_input` used to decide an unnamed state-3 field IS an
            # input by testing `0 < words[pos] < own_index`, the very same predicate --
            # so the walk pre-selected slots for holding a backward index and these probes
            # then re-tested the same thing. A tautology, which is exactly why they score
            # 0: they were redundant, not vindicated.
            #
            # That upstream probe is now gone too. Over the full corpus it was asked 1,944
            # of 10,430 state-3 decisions (18.6%; the other 8,486 came from an exact
            # PARAM_SPEC mask) and answered False every time, so it is replaced by the
            # per-(filter, field) law in `decompose.INPUT_FIELDS`, which reads only the
            # header. Edges are unchanged: 903,611 of 903,611 agree with the independent
            # `_compute_layout`/`_real_edges` model. See FORMAT-NOTES "Are slots real?".
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
        # REMOVED HERE: a tail that recognised a program slot "pushed along" by inputs the
        # layout key could not count, by stepping past the run of backward record indices.
        # It was load-bearing until 1332e2f and is not now. Its whole premise was that the
        # input count was unreadable -- `fxmaps` stated 34 inputs in a six-bit field that
        # was read four bits wide, so `layout[1]` landed mid-run and this stepped out of it.
        # Reading the field at its real width puts `layout[1]` on the program directly, and
        # the walk now derives what this recovered empirically: same slots, 37/22/23/20.
        #
        # Knocked out rather than assumed dead -- the REAL property with the union emptied,
        # against the real one, `_layout` cleared between reads so the cache cannot make
        # both sides agree by construction: 903,616 records, 0 readings changed.
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
        if f in WALKED_PARAMS:
            return self._parameters_walked(PARAM_SPEC[f])
        if f in PARAM_SPEC:
            return self._parameters_paired(PARAM_SPEC[f])
        return []

    def _parameters_walked(self, spec):
        """Parameters placed by the structural walk instead of by a memo lookup.

        `_parameters_paired` finds a block in `LAYOUTS` by key and counts from its end.
        `decompose` advances a cursor through the record and reports each parameter's first
        slot and width. For `levels` the walk is strictly better, and the arbiter is not
        plausibility -- both placements read values in [0, 1] on 6,520 of the 6,521 slots
        they disagree about, because the disagreement is a clean off-by-one and a shifted
        window of level positions is still a window of level positions.

        THE ARBITER IS THE EDGE-XOR-PARAMETER RULE this file already asserts, scored on the
        6,521 disagreements. The edge set is `decompose`'s `inputs`, validated 903,611 of
        903,611 against `_compute_layout` + `_real_edges`, so it is independent of where
        either model puts a parameter:

            memo lands ON AN INPUT EDGE       1,844        walk      0
            memo slot past end of record          1        walk      0

        A parameter read out of the input-edge slot is a record index reinterpreted as a
        float, which is why those read 0.0 rather than as anything out of range -- the
        plausibility test cannot see it and this one can.

        Coverage moves the same way. Over every corpus `levels` record: the memo never finds
        a parameter the walk misses, the walk finds parameters on 4,351 records where the
        memo returns nothing at all, and the two agree exactly on 153,230 slots.

        `dirmotionblur` AND `directionalwarp` ROUTE HERE TOO, and both now use the FIELD
        MATCH. `directionalwarp` used to be unable to: a spec mask is matched to a cost-model
        field by `pres == 3 << (2j + w1_shift)`, and with the shift fixed at 0 for every
        filter its `intensity` (0x006, bits 1 and 2) and `warpangle` (0x018) matched no field
        at all, so it fell through to `_parameters_positional`. That was read as a fact about
        dirwarp and was a fact about the GRID -- `costs.json` fitted its w1 fields on an even
        grid that splits both parameters. The grid is corrected (`derive_costs.W1_GRID_SHIFT`
        gives filter 12 a shift of 1), so 0x006 = 3 << 1 is field 0 and 0x018 = 3 << 3 is
        field 1, and the match names both.

        Verified name-for-name against the positional rule it replaces, over the corpus plus
        the reference packs: the same names in the same order on 62,898 of 62,898 records,
        and the parameters it reports track the declaring bits exactly -- intensity baked
        58,959 / program 3,479, warpangle baked 57,581 / program 2,535, against w1 bit counts
        of 58,959 / 3,479 / 57,581 / 2,535.

        WHAT DECIDED IT, corpus-wide, against the memo:

            filter            records   agree   differ   memo silent   walk silent
            directionalwarp    62,146  117,655      2       1,975          205
            dirmotionblur      15,097   25,960     15         337            3

        so the walk places 3,461 more `directionalwarp` parameters and 515 more
        `dirmotionblur` ones, recovering 1,770 and 334 records the memo returns nothing at
        all for, and neither path ever lands on an input edge.

        THE 17 DISAGREEMENTS ARE ARBITRATED STRUCTURALLY, not by plausibility -- every one
        of them reads as an ordinary float under both placements, which is exactly why this
        needed an arbiter that does not look at values:

            memo lands PAST the walk's header end (bytecode read as a parameter)   13
            walk coincides with the size-expression slot                            2
            undecided by structure (both placements inside the header)              2
            memo favoured                                                           0

        The 13 are decisive and one-sided. The 2 collisions are `dirmotionblur` records
        with no class-word slots, where `decompose`'s `prog` (the first slot after the const
        region) and the first parameter slot are the same position, so the walk's own two
        answers overlap rather than the memo being right -- and on one of them, Road.sbsasm
        record 417, the KIND BIT settles it for the walk independently: the bit says
        `intensity` is a program, `words[3] + 52` is a valid program, and the memo's slot 4
        holds 0.25. That record is the one `_read_slot` names as the memo's single kind
        conflict, recorded there as pending "until that filter moves onto the walk". This is
        that move. The 2 undecided are one `directionalwarp` record placed one slot apart
        with both readings inside the header, and nothing here claims to resolve them.

        `kind` still comes from the slot itself via `_read_slot`, not from the bit.

        `levels` IS NOT ROUTED HERE, because the render says no. With 15 in `WALKED_PARAMS`,
        `test_reference_agreement_does_not_regress` fails:

            Chesterfield basecolor ch0   corr 0.5495   floor 0.60
            Chesterfield basecolor ch1   corr 0.0268   floor 0.72

        CORRECTED ATTRIBUTION. This block previously blamed records 137, 210 and 218 -- the
        three that read `leveloutlow` 1.0 / `levelouthigh` 0.0 where the memo returns
        nothing. That was wrong, and the intervention that "confirmed" it was malformed: it
        made the named records return [], which is a THIRD behaviour, not the incumbent.
        Falling back to the memo instead, one group at a time, over the 7 records of the 124
        where the two routes differ:

            memo everywhere (incumbent)      ch0 +0.6658   ch1 +0.8862
            walk everywhere                  ch0 +0.5495   ch1 +0.0268
            memo for 137 / 210 / 218         ch0 +0.5499   ch1 +0.0260   no effect
            memo for 348                     ch0 +0.5495   ch1 +0.0268   no effect
            memo for 129 / 146 / 226         ch0 +0.6658   ch1 +0.8862   FULLY RESTORED
            memo for every levels record     ch0 +0.6658   ch1 +0.8862   control

        So it is 129, 146 and 226, and 137 is innocent -- routing it through the walk costs
        nothing measurable. The inversion it reads may still be wrong, but it is not what
        this test is objecting to.

        WHAT THE THREE CULPRITS LOOK LIKE. Record 129 is six words, class 0x18, w1 0x144, so
        three parameters at three slots and the record has exactly three to spare:

            slot 2  0x80        = record 128, its input EDGE
            slot 3  0x3f7fa377  = 0.99859
            slot 4  0x3f800000  = 1.0
            slot 5  0x0         = 0.0

            memo   levelinhigh @2  leveloutlow @3  levelouthigh @4
            walk   levelinhigh @3  leveloutlow @4  levelouthigh @5

        The memo starts one slot EARLIER and reads the edge as `levelinhigh`, which comes
        back as the denormal 1.79e-43 -- a record index reinterpreted as a float. The walk
        never lands on an edge and uses every word of the record. By the edge-XOR-parameter
        rule the walk is right, and by the reference maps the memo is: the walk's placement
        gives `leveloutlow` 1.0 above `levelouthigh` 0.0, an inversion, and the channel
        collapses. Both readings cannot be right and the two instruments disagree, which is
        the whole of what is unresolved here.

        RECORD 129 IN FULL, since it is the smallest complete statement of the conflict.
        Its input, record 128, is a near-flat mid-grey (mean 0.4998, std 0.0037). Under the
        two routes it renders as:

            memo   mean 1.0000  std 0.0000   a CONSTANT WHITE
            walk   mean 0.4995  std 0.0037   the input, inverted

        and the memo's constant is what the reference maps agree with. The arithmetic is
        not in doubt on either side. The memo's out-pair is (0.99859, 1.0) -- an output
        range one and a half thousandths wide, so every input lands on white whatever the
        input range does. The walk's out-pair is (1.0, 0.0), a genuine inversion, which this
        file separately verifies is a real thing an author asks for (fur_var_001 record 54
        stores exactly (1.0, 0.0) and its output is 1.0 where its input is 0.0).

        What propagates is the MEAN, not the structure: 129 feeds a transformation into a
        blend where it acts as a mask, and white against mid-grey changes that blend
        completely. That is how a record with std 0.0037 swings basecolor ch1 from +0.89 to
        +0.03, and it is why the three sibling records that read the SAME inversion cost
        nothing -- 137, 210 and 218 take inputs that are already 0.5 to within 0.0005, and
        inverting 0.5 returns 0.5.

        SO THE WHOLE CONFLICT IS ONE WORD: does w1 field 1 (`levelinhigh`, bit 2) consume a
        slot in this record? If it does, the out-pair is at slots 4 and 5 and 129 inverts.
        If it does not, the out-pair is at 3 and 4 and 129 is white.

        THAT QUESTION IS NOT ARBITRABLE BY THE REFERENCE MAPS, and the control says so
        rather than an argument. Zeroing the cost model's width for field 1 state 1 gives
        129 the memo's out-pair and scores BETTER than the memo on ch0; zeroing field 0
        instead leaves record 129 byte-identical -- its w1 is 0x144, bit 0 clear, so field 0
        is in state 0 and skipped whatever its width -- and moves the score further still:

            memo (incumbent)                    ch0 +0.6658   ch1 +0.8862
            walk, cost model unchanged          ch0 +0.5495   ch1 +0.0268
            walk, field 1 state 1 costs 0       ch0 +0.7924   ch1 +0.7583
            walk, field 0 state 1 costs 0       ch0 +0.8398   ch1 +0.6378   <- cannot touch 129

        A knob that provably does not reach the record under study moves its channel by
        +0.29. So these are a fitting surface, not evidence about record 129.

        AND CONTAINMENT REFUSES BOTH EDITS. Zeroing field 1 drops `levelinhigh` from record
        25, whose own source declares it as 0.604323 and where it sits at slot 4; zeroing
        field 0 drops `levelinlow` from the same record, declared 0.211466 at slot 3. Both
        cost edits improve the picture and contradict the file's own text, which is the
        exact shape of error this project keeps recording.

        RESOLVED SINCE, AND AGAINST THE WIDTH HYPOTHESIS. `param_slots.declared()` read
        only `constantValueFloat1`, and `levels` stores every parameter as
        `constantValueFloat4` -- the scalar repeated across RGB with alpha 0 or 1 -- so it
        matched ONE node in the whole corpus and the filter looked unpairable. Reading the
        first component of a FloatN gives 91 pairings across 35 sources and 18 distinct w1
        patterns, and against the walk's placement:

            MATCH,  state 1 (baked)      90
            MISMATCH, state 2 (program)   1

        The single mismatch is not one: DLG-Tools__Damaged_Iron_01 record 266 has
        `levelinhigh` in the PROGRAM form, its slot 4 holds a valid program pointer, and the
        declared 0.7 sits inside that program's body as `const.f1 0.7` -- located by the
        search, but not at a parameter slot. So it is 91 of 91 read correctly.

        RECORD 129'S OWN SHAPE IS CONFIRMED TWICE, INDEPENDENTLY. Its w1 is 0x144, and two
        other packages declare a levels node with exactly that pattern:

            DLG-Tools__Damaged_Iron_01 rec 209   levelinhigh 4, leveloutlow 5, levelouthigh 6
            Sho__Fur                   rec 14    levelinhigh 4, leveloutlow 5, levelouthigh 6

        Both place the three parameters at three consecutive slots with `levelinhigh` first,
        which is exactly what the walk does for record 129. So w1 field 1 DOES consume a
        slot, the "field 1 state 1 costs 0 words" edit is refuted by source declarations
        rather than by a score, and record 129's out-pair really is (1.0, 0.0) at slots 4
        and 5.

        THE CONE, TRACED. Record 129's input is not flat by accident and not flat by any
        fault upstream of it. Walking the 39 records above it:

            122  shuffle          256x256  std 0.2187   real contrast
            128  transformation    16x16   std 0.0037   <- the signal dies here
            129  levels            16x16   std 0.0000

        Record 128 is a 4x MINIFICATION -- matrix (4, 0, 0, 4) onto a 16x16 output -- and its
        `uniq` of 16 is the giveaway: 16 output pixels at 4x zoom land on only four distinct
        sample positions per axis. Upstream of that everything is healthy and, more to the
        point, correct: 122 is a shuffle whose weight vector is exactly (1, 0, 0, 0), the RED
        channel of the normal map at 121, and a normal map's X channel IS 0.5 wherever the
        surface is flat. 121's own mean of 0.7220 is what R,G ~ 0.5 with B,A ~ 1.0 averages
        to. So the 0.4998 reaching 129 is the right number, not a collapse to be fixed.

        WHICH MAKES THE TWO READINGS STRUCTURALLY IDENTICAL AND ONLY THE MEAN DIFFERENT --
        inverting 0.5 returns 0.5 -- and pins exactly what the reference is asking for. For a
        levels node to turn an input of 0.5 into the ~1.0 the exported maps want, it needs
        t = 0, which means `levelinlow` >= 0.5. The value sitting at slot 3 is 0.99859 and
        would do precisely that -- if slot 3 were `levelinlow`.

        It is not. w1 bit 2 is `levelinhigh`, and that is the one thing here with independent
        support: record 25 of this same file sets bits 0 and 2 and its source declares
        `levelinlow` 0.211466 and `levelinhigh` 0.604323 at slots 3 and 4. So the reading the
        pixels require is the reading containment forbids, on the same file, for the same bit.

        BOTH DECODE EXPLANATIONS ARE NOW ELIMINATED, and by a source declaration rather
        than by a score.

        An inverted output range is not exotic. Over every paired source, 58 levels nodes
        state an output range and 21 of them have `leveloutlow` above `levelouthigh` -- most
        of those exactly (1.0, 0.0), across seven different packages. The earlier reading of
        "0 of 12 in ChesterfieldSofa" was a twelve-node sample of one file, which is the
        small-population error this docstring already records being made once.

        And record 129's exact shape is declared, with its inversion, in another package.
        DLG-Tools__Damaged_Iron_01 record 209 has the same w1 of 0x144, and its source says:

            declared    leveloutlow 1.0   levelouthigh 0.0   levelinhigh 0.395455
            walk reads  levelinhigh 0.395455, leveloutlow 1.0, levelouthigh 0.0

        Three values, three slots, exact. So w1 bit 2 IS `levelinhigh` in this record shape --
        record 25 generalises after all -- and `render.py` is not mishandling an inverted
        out-range, because the parameters it is handed match a declaration exactly. Record
        129 really is an inverter over a near-full input range, and the walk reads it right.

        WHAT THAT LEAVES IS THE THIRD OPTION. The exported map agrees with the memo for a
        reason that has nothing to do with record 129's parameters: the memo's accidental
        constant -- produced by reading an input edge as a denormal `levelinhigh` -- is
        masking a fault somewhere else in the graph, and routing levels correctly exposes it.
        The reference test's veto on `levels` is therefore a symptom and not a verdict, and
        the record to chase is no longer this one.

        WHICH MOVES THE PROBLEM RATHER THAN CLOSING IT. The levels widths are settled and
        the placement is right; the Chesterfield disagreement is therefore NOT a parameter
        layout question, and the next place to look is record 129's cone or the handling of
        an inverted output range -- not this table.

        So record 129 is explained and not resolved: the walk reads it correctly given the
        cost model, the cost model is the thing in question, and the only instrument that
        could settle a width -- source containment -- speaks for the current widths while
        the pixels speak against them.

        The walk is ahead on every structural measure and behind on pixels:

            walk lands on an input edge          0        memo   1,844
            walk slot past end of record         0        memo       1
            memo finds a parameter walk misses   0        walk finds some on 4,351 records
            source-declared values recovered     8 of 8   (slot AND value, end to end)

        None of that outweighs a reference channel falling from 0.72 to 0.03. Explain record
        137 before routing this.

        THREE FOLLOW-UPS, none of which unblocks it, two of which close off a wrong turn.

        1. The regression is REAL, not a measurement artifact. In-process A/B renders in
           this repository share `sbsruntime.SAMPLERS` between the two passes, and a change
           that provably could not affect a file still moved 9 of 18 of its channels that
           way -- so this one was re-run as two SEPARATE PROCESSES, one per condition:

               memo   basecolor ch0 +0.6658   ch1 +0.8862   ch2 +0.6854
               walk   basecolor ch0 +0.5495   ch1 +0.0268   ch2 -0.3526

           ch2 does not merely fall, it goes NEGATIVE: the output is anti-correlated with
           the engine's, which is what an inversion reaching the output looks like.

        2. "(1.0, 0.0) looks like a sentinel" does not survive a census, so the argument
           from the sources -- zero of 12 declared `levels` nodes put `leveloutlow` above
           `levelouthigh` -- is a small-sample artifact and not evidence against the read.
           Over 200 specimens, 17,119 records carry both:

               (1.0, 0.0)          4,430   the SINGLE most common pair, 25.9%, in 148 files
               inverted in total   4,723
               normal              12,190

           An inverted output range is the format's ordinary way to invert a map. The walk
           is reading a real and common setting, not misreading a sentinel.

        3. "Skip the inverted pairs" is NOT the missing rule. Walking `levels` but dropping
           any pair with `leveloutlow > levelouthigh` is worse than either side above:

               AO ch0        +0.9193  ->  -0.9193   (mae 0.028 -> 0.773, a clean sign flip)
               roughness     +0.8834  ->  +0.4442

           So some inversions are load-bearing -- AO depends on one -- while others wreck
           basecolor. The population is heterogeneous and a blanket rule in either
           direction is wrong.

        What is left to find is therefore a rule about WHICH records apply their levels,
        not about placement (source-confirmed), not about the values (real and common), and
        not about inversion as a category (needed in some places, harmful in others).

        THE BLOCKING RECORDS ARE 129, 146 AND 226 -- NOT 137. Bisected by falling each
        candidate back to the MEMO reading (not to [], which is a different answer again --
        the memo's near-zero in_high makes the record degenerate, while [] gives defaults
        and an identity):

            memo-fallback on 129, 146, 226   basecolor +0.6658 +0.8862 +0.6854  = memo
            memo-fallback on 137, 210, 218   basecolor +0.5499 +0.0260 -0.3524  = unchanged

        So the three byte-identical 16x16 records this note was named for are RENDER-NEUTRAL
        and never were the blocker. Only 7 of the file's 124 levels records read differently
        at all, and the collapse is entirely those three.

        AND ON THOSE THREE THE MEMO IS READING AN INPUT EDGE. Record 129 is six words:

            slot 2   0x80        the input edge -- record 128
            slot 3   0.998588    walk: levelinhigh    memo: leveloutlow
            slot 4   1.0         walk: leveloutlow    memo: levelouthigh
            slot 5   0.0         walk: levelouthigh   memo: (not read)

        The memo reads slots 2, 3, 4, so its `levelinhigh` is the edge word 128 reinterpreted
        as a float -- the 1.79e-43 denormal it reports. That is the exact failure the
        edge-XOR arbiter above scores 1,844 of, and it is what makes the record degenerate
        and therefore harmless. The walk reads 3, 4, 5, which exhausts the record exactly and
        assigns every declared field a slot.

        So the structurally invalid reading is the one that matches the engine, and the
        complete one does not. Both pass the source-naming checks
        (`test_levels_parameters_are_named_the_way_the_sources_name_them`, 86 agreements and
        0 mis-namings) because no source-locatable value lands in these seven records.

        Refuted while here: that the names are rotated against the slots -- out-parameters
        taking the earlier positions, which would make slot 3/4 the out pair and reproduce
        the memo's values honestly. Rotating drives every channel strongly negative
        (basecolor -0.60 / -0.98 / -0.82, AO -0.81), so the naming is not the error either.

        THE WHOLE SAMPLING CLASS IS OUT TOO. Record 128, the 4x minification feeding 129, is
        the obvious next culprit and is not one. It collapses a std-0.1356 input to std
        0.0017 because a 16x16 grid at 4x zoom lands on four distinct fractional coordinates
        per axis (0.125, 0.375, 0.625, 0.875) and samples the same four texels repeatedly.
        That collapse is real -- and MEAN-PRESERVING, and only the mean reaches 129:

            122 full                        mean 0.4999   std 0.1356
            decimated 16x16                 mean 0.4915   std 0.1121
            box-averaged 16x16 (a true mip) mean 0.4999   std 0.0776
            point-sampled at the 4x coords  mean 0.5180   std 0.0001

        Every filtering rule gives ~0.5, so no sampling fix reaches the ~1.0 the exported map
        wants: after 129's inversion they all land at 0.48-0.50.

        The matrix CONVENTION goes the same way. Reading (4, 0, 0, 4) as the sampling
        transform (minify) or as its inverse (magnify at 0.25x) gives 0.5180 and 0.4959
        before the levels, 0.4813 and 0.5034 after it. Neither is white.

        So the thing still unaccounted for is not a filtering rule and not a transform
        convention. Something upstream would have to deliver a value at or above
        `levelinhigh` (0.99859) instead of a mid-grey, and nothing in the traced cone does.
        """
        import decompose as _decompose
        d = _decompose.decompose(self)
        if d is None:
            return []
        names = {}
        # THE GRID THE FIELDS ARE ON COMES FROM THE WALK. A parameter's mask matches field
        # j at bit `2j + w1_shift`, and the shift is 0 for every filter but
        # `directionalwarp`, whose parameters begin at bit 1. Before that offset was fitted
        # into `costs.json`, dirwarp's 0x006 and 0x018 matched no field at all and it had to
        # fall through to `_parameters_positional`; with the grid corrected both match
        # exactly (0x006 = 3 << 1 -> field 0, 0x018 = 3 << 3 -> field 1) and it routes here.
        # Verified name-for-name against the positional rule it replaces: same names in the
        # same order on 62,898 of 62,898 records.
        gsh = int(d.get('w1_shift', 0) or 0)
        aligned = True
        for nm, pres, _prog in spec:
            for j in range(16):
                if pres == (3 << (2 * j + gsh)):
                    names[j] = nm
                    break
            else:
                aligned = False
        if not aligned:
            # UNREACHABLE, AND LOUD RATHER THAN SILENT IF IT EVER IS NOT. Every mask in
            # every PARAM_SPEC entry resolves to exactly one field under the grid shift
            # (SPEC 7.4), so this branch is not taken on any of 445,815 records that reach
            # this method. It used to fall through to `_parameters_positional`, a SECOND
            # placement rule -- and that rule and this one produce identical name lists on
            # 78,783 of 78,783 records, so it was never a different answer, only a second
            # implementation of the same one. Two implementations of one rule is how
            # `walk.SPECS[4]`'s arity drifted from `decompose`'s.
            #
            # Deleting it silently would be worse than keeping it: the reason it was kept
            # is that a future misaligned spec would then return [] with no signal, and an
            # empty parameter list is indistinguishable from a filter that declares none.
            # So the mechanism goes and the alarm stays. If this raises, a PARAM_SPEC mask
            # is not `3 << (2j + shift)` and SPEC 7.4 needs the counter-example, not a
            # workaround.
            raise ValueError(
                'filter %d has a PARAM_SPEC mask off the w1 field grid (shift %d): %r. '
                'See SPEC 7.4 -- a presence mask must be 3 << (2j + shift).'
                % (self.filter_id, gsh,
                   [hex(pres) for _n, pres, _p in spec
                    if not any(pres == (3 << (2 * j + gsh)) for j in range(16))]))
        out = []
        for j, _st, pos, _w in d['param_slots']:
            nm = names.get(j)
            if nm is None or not (0 <= pos < len(self.words)):
                continue
            out.append(self._read_slot(nm, pos))
        return out

    def program_slots(self):
        """Which block slots hold programs, for the filters that encode it as a count.

        Returns a list of (slot, is_program) for filters in PARAM_POPCOUNT, or [] otherwise.
        This is the class-word mechanism, not the slot-1 bit pairs of PARAM_SPEC - a filter
        uses one or the other, never both.

        THE SLOT LIST COMES FROM THE WALK; only the program/baked SPLIT is the class
        word's. This used to take the slots from LAYOUTS and `return []` whenever the
        table had no key for the record -- so a fifth of blur and warp records reported
        no block at all, silently, and `walk.py` consumed that empty answer. Over 120
        specimens, 7,439 blur/warp records:

            LAYOUTS had no key      1,630 (21.9%)  -- the walk names slots for 1,629
            LAYOUTS had a key       5,809          -- walk identical on 5,795

        The 14 that differ are one pattern: `warp` with cls 0x2B19, where the table says
        slots 4, 5, 6 and the walk says 3, 4, 5. The table's list leaves slot 3 belonging
        to nothing and puts its last slot at 6, past the walk's own header end of 6 -- the
        same signature as every other phantom found here, a slot index that addresses
        payload. The walk's list is contiguous with the base region and ends where the
        header ends, so it is taken.

        `test_tables.py` names draining this and `named_parameters` as the remaining step
        before layouts.json can be removed; this is the first of the two. The table stays
        as the fallback for a record the walk cannot resolve.
        """
        m = PARAM_POPCOUNT.get(self.filter_id)
        if m is None or len(self.words) < 2:
            return []
        slots = None
        try:
            import decompose as _decompose
            _d = _decompose.decompose(self)
        except Exception:
            _d = None
        if _d is not None and _d.get('end') is not None:
            slots = sorted(set(_d['cls_slots'])
                           | {t[2] for t in _d.get('param_slots', ()) if len(t) >= 3})
        if slots is None:
            hit = LAYOUTS.get((self.filter_id, self.cls,
                               self.words[1] & LAYOUT_MASK.get(self.filter_id, 0)))
            if not hit:
                return []
            slots = list(hit[1])
        n = bin(self.cls & m).count('1')
        return [(s, j < n) for j, s in enumerate(slots) if s < len(self.words)]

    def _read_slot(self, name, slot):
        """One parameter slot as (name, kind, value).

        `kind` comes from the parameter's PROGRAM BIT where that bit is verified exact, and
        from the slot's contents everywhere else.

        The format STATES whether a parameter is computed or baked: `PARAM_SPEC` carries a
        program mask beside each presence mask (blend's `opacitymult` is presence 0x30,
        program 0x20), and this file established that bit at 100% over 217,715 blend slots.
        This reader used to ignore it and ask `valid_program(word + 52)` instead -- deciding
        what a word IS by what it looks like, which is the probe that manufactured a phantom
        program out of an instruction operand in `Record.programs`.

        Where the two can be compared, full corpus, 585,105 parameter reads:

            blend            179,524 reads        0 disagreements   0.000%
            levels           168,077              0                 0.000%
            directionalwarp  117,657              0                 0.000%
            dirmotionblur     25,975              1                 0.004%
            fxmaps            93,872          1,423                 1.516%

        So for the first three the bit and the slot NEVER disagree, and reading the bit is
        exactly equivalent -- the probe is removed for 465,258 of 585,105 reads with no
        change to any value.

        The other two keep reading the slot, for reasons that are about them and not about
        the bit:

        * `fxmaps` holds 1,423 of the 1,424 disagreements, and its own PARAM_SPEC entry
          already says why -- of its four pairs "two are exact and two are near it", at
          97.22% and 97.06%. Its bit model is unfinished, so preferring it here would be
          adopting a 97% rule over a probe with no arbiter to say which is right.
        * `dirmotionblur`'s single disagreement is not a bit error at all. Road.sbsasm
          record 417 has w1=0x6, so the bit says `intensity` is a program, and the WALK
          agrees -- it puts intensity at field 0, slot 3, state 2, and `words[3] + 52` is a
          valid program. The 0.25 the probe reports is `words[4]`. The LAYOUTS memo, which
          is what routes this filter, named the wrong slot. Trusting the bit while standing
          on the memo's slot would emit `words[4] + 52` as a program pointer -- a right kind
          on a wrong slot, which is garbage rather than a fix. The slot read is the safer
          answer until that filter moves onto the walk.

        Conflicts are RECORDED, not swallowed: `_kind_conflicts` collects any record where
        the bit and the slot disagree on a filter this trusts. It is empty on this corpus,
        and an entry on a new one is a finding -- the same discipline that surfaced the
        missing `(emboss, 1)` pair in `decompose.INPUT_FIELDS` instead of guessing at it.
        """
        raw = self.words[slot]
        ptr = raw + 52
        slot_is_program = (self.asm.body_lo <= ptr < self.asm.body_hi
                           and self.asm.valid_program(ptr))
        if self.filter_id in BIT_EXACT_KINDS:
            w1 = self.words[1] if len(self.words) > 1 else 0
            bit_is_program = False
            for _nm, _pres, _prog in PARAM_SPEC.get(self.filter_id, ()):
                if _nm == name:
                    bit_is_program = bool(w1 & _prog)
                    break
            if bit_is_program != slot_is_program:
                _kind_conflicts.append((self.filter_id, name, self.index))
            slot_is_program = bit_is_program
        if slot_is_program:
            return (name, 'program', ptr)
        if self.filter_id in PARAM_RAW:
            return (name, 'baked', raw)
        return (name, 'baked', struct.unpack('<f', struct.pack('<I', raw))[0])

    def _parameters_paired(self, spec):
        """Parameters for filters whose bits come in (baked, program) pairs.

        The present parameters occupy the LAST k slots of the block, in spec order. A
        record whose bits imply more parameters than the block has slots is not readable
        either way, so it reports what fits instead of guessing an alignment.

        HOW OFTEN "MORE THAN THE BLOCK HAS" HAPPENS, corpus-wide rather than over the file
        subset `_param_slots` quotes 13,417 from:

            filter   records   block < bits   block sizes seen        MAX
            1        310,491        47,705    [-1, 0, 1, 2]             2
            4         40,789           304    [-1, 0 .. 6]              6
            11        14,825           286    [0 .. 4]                  4
            12        60,339           579    [1 .. 4]                  4
            15        85,149        13,686    [-1, 0 .. 4]              4   <- declares 5

        62,560 records in total, and `levels` declares FIVE parameters against a block that
        never exceeds four slots. `_param_slots`' grow rule reaches outside the block and
        places nearly all of them, which is what it is for.

        WHERE IT DOES NOT, THE LOSS IS SILENT, and that is worth naming because nothing
        reports it. The `continue` below drops a parameter whose computed slot falls
        outside the record, so `named_parameters` returns FEWER parameters than the
        record's own presence bits declare -- no exception, no LOW_CONFIDENCE, no marker:

            filter 4    36 records    (23 lose 1 of 2, 13 lose 1 of 1)
            filter 15    1 record
            37 records corpus-wide

        The cause is the lossy memo key. `concrete_049` record 396 is SIX words long and
        the block its key selects names slot 11; record 78 is eight words and gets slot 11
        too. That is the "one layout key covering two real layouts, told apart by record
        length" that `_param_slots` records below -- but these are a different population
        from the 4 errors it counts there, and they fail by disappearing rather than by
        landing wrong.

        A CURSOR CANNOT MAKE THIS MISTAKE. `decompose` advances `pos` through the record
        itself, so it cannot propose slot 11 of a six-word record; only a memo consulted by
        key can. This is the parameter path's version of what `param_slots` found for
        `intensity` -- a slot index is a position in a walk, and reading it in any other
        frame is what makes it look unstable. Retiring this is blocked on the parameter
        WIDTHS, and the obvious structural candidate for those is refuted: baked levels are
        one word whether the record is colour or greyscale (colour records with 2 baked
        parameters have a 2-slot block, 550 of 550 -- not the 8 a float4 would need).
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

        CACHED on first access. The tiling probe walks up to 512 candidate offsets
        through valid_program, and every tool and test that touches a record reads
        .programs at least once -- the full test suite went from seventeen seconds to
        ten minutes on recomputation alone.

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
        if self._programs is not None:
            return self._programs
        asm = self.asm
        # No LAYOUTS hit here any more. The memo used to seed the program slots and gate
        # `classified_programs`, but the universal slot scan below (a program's start is a
        # slot's value + 52) plus `classified_programs` recover every one it named --
        # emptying the whole memo changes 0 program lists corpus-wide. So the slots come
        # from the record's own program slot and the classifier, and the memo is drained
        # from programs() as it was from the layout.
        slots = []
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
        # BOUNDED BY THE WALK, because "slot" is what the paragraph above means and this
        # loop used to read `self.words` -- EVERY word of the record. Past the walk's `end`
        # a record is BYTECODE, so an instruction operand that happens to survive
        # `valid_program` was returned as a program. `UHL3D-Stylized_Sand_with_Rocks_01`
        # record 2618 is 142 words with its structure ending at word 5; word 19 is
        # `0x10008`, mid-bytecode, and yielded "program" 65596 -- byte-identical in 177
        # records of that file because they share an instruction sequence. It evaluates
        # 2-wide, so `render.py`'s transformation branch saw two candidate offsets and
        # refused on 88 records over something that is not a program at all. Same
        # anti-pattern as the `fx_named_params` inline recovery that manufactured 2,717.
        #
        # Nothing this loop was FOR is lost: its own justification above is "a slot-named
        # program this method did not return", and a slot is exactly what `end` bounds.
        #
        # THE TWO CARVE-OUTS ARE STRUCTURAL, NOT A FITTED LIST. `fxmaps` and
        # `pixelprocessor` address a payload region that HOLDS program pointers by design
        # -- the FX node/entry tree, and the pixel program's own block -- so for them the
        # record's words past the header are still slots, just slots of another structure.
        # Measured rather than assumed: bounding every filter takes one file from 2,229
        # rendered records to 172, and 99.8% of fxmaps' programs plus 34.6% of
        # pixelprocessor's are named only past `end`. Bounding the rest drops 1,470
        # candidates over 14 files, 6.4% of their programs.
        seen = set(out)
        end = None
        if self.filter_id not in _PAYLOAD_PROGRAM_FILTERS:
            try:
                import decompose
                _d = decompose.decompose(self)
                end = _d.get('end') if _d else None
            except Exception:
                end = None
        for word in (self.words if end is None else self.words[:end]):
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
                if not (self.words[0] & 1):     # see Record.header_words
                    w1 = None
            # `version` is REQUIRED now: header_words owns the warp/shuffle two-shape
            # gate, and refuses rather than guessing when it cannot see the version. This
            # call omitted it, which made every filter-7 answer here depend on the local
            # gating above rather than on the rule.
            _ver = asm.header.get('version') if isinstance(asm.header, dict) else 0
            rl = (record_layout.header_words(self.filter_id, self.words[0], w1,
                                             version=_ver)
                  if w1 is not None or self.filter_id in (7, 3) else
                  record_layout.header_words(self.filter_id, self.words[0],
                                             self.words[1], version=_ver))
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
                # The filter-20 slack that used to sit here is retired: the "S = 1
                # implicit position" reading was a proxy for sample tokens 2+ being
                # immediates, now stated correctly in disasm.IMM. Strict validation
                # accepts all 178 affected functions.
                if asm.valid_program(pa):
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
        self._programs = out
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
        # BOUNDED BY THE WALK TOO, for the same reason and with the same carve-out as
        # `programs`' slot loop: past `end` a record is BYTECODE, so an instruction operand
        # that happens to survive `valid_program` is not a program. This loop said "the
        # header ends at the first program the record points at INSIDE itself", which is a
        # bound read off the VALUES; `decompose` states where the header ends.
        #
        # The two bounds agree almost everywhere, so this is a correctness fix rather than a
        # coverage change. Corpus-wide, excluding `_PAYLOAD_PROGRAM_FILTERS`:
        #
        #     bounds agree                     678,272 of 679,775 records   99.8%
        #     walk bound drops candidates        1,502 records, 1,688 candidates
        #     walk bound adds candidates             1 record,      1 candidate
        #
        # which is the same scale `programs` measured and accepted for its own loop ("drops
        # 1,470 candidates over 14 files"). The carve-out is structural and not a fitted
        # list: `fxmaps` and filter 20 address a payload region that holds program pointers
        # by design, so for them the words past the header are still slots.
        #
        # The inline bound is KEPT as well, as a further clip rather than a replacement. It
        # is not equivalent -- it can stop earlier than the walk when a record points into
        # its own bytecode early -- and nothing here establishes which is right where they
        # differ, so both apply and the tighter one wins.
        stop = len(self.words)
        if self.filter_id not in _PAYLOAD_PROGRAM_FILTERS:
            try:
                import decompose as _decompose
                _d = _decompose.decompose(self)
                if _d and _d.get('end') is not None:
                    stop = min(stop, _d['end'])
            except Exception:
                pass
        cand = []
        for s in range(2, len(self.words)):
            p = self.words[s] + 52
            if asm.body_lo <= p < asm.body_hi and asm.valid_program(p):
                cand.append((s, p))
        # The header ends at the first program the record points at INSIDE itself.
        inline = [(p - o) // 4 for _s, p in cand if o <= p < e]
        if inline:
            stop = min(stop, min(inline))
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
            # ONLY when that program could actually BE a size expression. A size is an
            # INTEGER -- (log2 width, log2 height) -- so a FLOAT-valued program in this
            # slot is not the record's size under any reading, and stripping it deletes
            # the very parameter a caller asked for.
            #
            # Over 60 corpus files, 84,052 records have a program here and 13,921 of them
            # are not size-shaped. The float ones are the point:
            #
            #     transformation   1,488 return f2   -- the translation OFFSET
            #     transformation      32 return f4   -- the 2x2 MATRIX
            #     uniform             19 f4, 20 f1     warp 7 f2     blend 30 f1
            #
            # `render.py` reads `filter_programs` to find exactly those, so every one of
            # those records refused to render with "offset is a program this cannot single
            # out (0 programs)" -- a message that is self-contradictory, and was true only
            # because this property had removed the program before the caller looked. The
            # first one read, `stone_stylized_adaptive` record 153, computes
            # `vec(-1.0 / $size.x, 0.0)`: a one-pixel horizontal shift.
            #
            # The INTEGER non-size cases are left stripped. `pixelprocessor` and `fxmaps`
            # return a 1-component integer here in 99.7% and 99.3% of records, and
            # `audit_corpus.py` already records that calling that a size is "a label this
            # audit applied, not a fact it measured" -- whatever it is, it is not a filter
            # parameter this changes the reading of, so it stays out of scope.
            if self.asm.program_result(par[1]) is None or \
                    self.asm.program_result(par[1])[0] != 1:
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
        cells = []
        for off, hdr, prog in self.fx_tree():
            last = off
            _s = (pointer_cell_payload(self.asm, off)
                  if hdr is not None and pointer_cell_successor(hdr) is not None else None)
            if _s is not None and off + _s + 4 <= self.asm.body_hi:
                cells.append((off, hdr, _s))
            yield ('node', off, hdr, prog)
        start = None
        if last is not None:
            q = last                      # fx_tree yields absolute offsets
            h = struct.unpack_from('<I', self.asm.data, q)[0]
            sh = node_shape(h)
            # THE 0x??0B FAMILY HANDS OFF TOO, and its next-pointer is at word 1. Only
            # FX_NODES was consulted here, so 643 chains ending on one of those leaves
            # reached no table at all -- and for a record whose slot 2 addresses a CHAIN
            # the chain is the only path there is, because fx_table returns immediately
            # when the first word is a node header.
            #
            # That is why FORMAT-NOTES' earlier "following 0x0B's word 1 moves NO number"
            # held: measured over all records it is true, since every record it looked at
            # already reached its table through slot 2. Restricted to the chains that end
            # on one of these leaves, word 1's target is
            #
            #     entry tag   591     node header  1     neither  51     (of 643)
            #
            # -- 91.9% a table entry, matching the 85.7% the leaf probe already recorded --
            # and 62 records gain a table they otherwise have none of. Those 62 are not
            # marginal: they are the tree-only FX-Maps, and in StylizedCobblestoneStreet
            # two of them gate 1,158 and 1,127 of the file's 1,778 records.
            # THE HANDOFF OFFSET COMES FROM THE TABLES, not from a special case. This
            # read `4 if (h & 0xFF) == 0x0B else None`, which is FX_NODES2[0x0B]'s
            # successor slot written out by hand -- correct while 0x0B was the only
            # non-FX_NODES kind a chain could end on. It no longer is: with 0x9B walkable,
            # a chain can end there instead, and 10 records across the reference packages
            # do (ChesterfieldSofa 79, Auras 43/250/332/370) -- every "no readable table
            # entries" failure in that set. Their table sits at the 0x9B's successor slot,
            # word 3, and the hardcoded 4 could never find it.
            off1 = sh[0] if sh else None
            # A NON-SENTINEL `0x1B` HANDS OFF TO THE TABLE, CONTIGUOUSLY. Both forms of
            # this branch are three words -- `[header][word 1][pointer]` -- and WORD 1 says
            # what follows at byte 12:
            #
            #     word 1 == 0x3039   the next NODE (an 0x18B), walked as a child
            #     word 1 == 0        the first table ENTRY, and the chain ends here
            #
            # The second reading is not inferred from the low nibble alone. On all 12 such
            # nodes in the corpus the word at byte 12 has its low 16 bits IN `FX_TAG_LOW16`,
            # the established entry-tag vocabulary -- 12 of 12 -- and `fx_table(q + 12)`
            # yields 3 to 5 entries on every one of them, where the walk as it stood reached
            # 0 or 1. Word 2's pointer confirms it independently: it addresses q + 12 exactly
            # (12 of 12), so the node names the entry as well as abutting it.
            #
            # This cannot go through `off1`, which POINTER-READS the byte it is given. The
            # table is AT byte 12, not addressed by a word there.
            if start is None and (h & 0xFF) == 0x1B and q + 16 <= self.asm.body_hi:
                _w1 = struct.unpack_from('<I', self.asm.data, q + 4)[0]
                if _w1 != 0x3039:
                    _t = struct.unpack_from('<I', self.asm.data, q + 12)[0]
                    if (_t & 0xFFFF) in FX_TAG_LOW16 and self.offset <= q + 12 < self.end - 7:
                        start = q + 12
                        off1 = None
            if off1 is None and start is None:
                # The LEAF's successor is derived (`leaf_successor`), not looked up; only
                # the BRANCH still comes from the hand-stated table, and for it the handoff
                # is the LAST child.
                off1 = leaf_successor(h)
            if off1 is None and start is None:
                # A pointer cell ends the chain by ADDRESSING the table at slot 2 -- the
                # same derivation `fx_tree` walks by, so the two halves cannot drift.
                off1 = (pointer_cell_payload(self.asm, q)
                        if pointer_cell_successor(h) is not None else None)
            if off1 is None and start is None:
                _s2 = FX_NODES2.get(h & 0xFF)
                if _s2 and _s2[0]:
                    off1 = _s2[0][-1]
            if start is None and off1 is not None and q + off1 + 4 <= self.asm.body_hi:
                nxt = struct.unpack_from('<I', self.asm.data, q + off1)[0] + 52
                # BOUNDED BY THE BODY, as `fx_table` is and for the reason it records:
                # "805 fxmaps records address a table that lies outside them, and in 757
                # of 757 resolvable cases it sits inside an earlier record". The handoff
                # names the FIRST entry of that table, so requiring it to sit inside this
                # record contradicts the bound on the table it points into -- and this
                # method's own docstring, which reports 2,753 entry offsets landing outside
                # their record against 0 node offsets.
                #
                # AND GATED ON THE LAYOUT, NOT ON THE TAG VOCABULARY, which is the half of
                # this that nearly went in wrong. Relaxing the bound alone admits 62 new
                # landings, and the word waiting at 61 of them has its low 16 bits in
                # FX_TAG_LOW16 -- so a vocabulary test passes every one and coverage
                # appears to jump by 53 records. It is bytecode. `fx_table`'s own stopping
                # rule already records this exact trap: "0x09130008 is 2,322 'entries'
                # whose low 16 bits are in FX_TAG_LOW16 and which are, every one of them, a
                # u32 straddling two instructions."
                #
                # `entry_layout_holds` separates them, and it is a UNIFORM rule here rather
                # than a patch aimed at the new cases -- which is the only reason it is
                # trusted. Measured over every handoff landing in the corpus:
                #
                #     in-record (the established path)   28,559 of 28,577 hold   99.94%
                #     outside the record, in the body         1 of      62 holds  1.6%
                #
                # A test the working population passes at 99.94% and the newly-admitted
                # population fails at 98.4% is discriminating between two different kinds
                # of thing, not thresholding one. So the body bound recovers ONE record
                # (Desert_Sand_01 #71, whose tag 0x14b the vocabulary test would itself
                # have rejected -- the two gates disagree in both directions), and the
                # other 61 are refused on the correct grounds instead of by accident of the
                # old bound.
                #
                # THE 18 IN-RECORD LANDINGS THAT FAIL are left admitted, deliberately.
                # Gating them too is a separate change to an established path with its own
                # risk, and 0.06% is as consistent with a layout-test false negative as
                # with junk. Recorded here rather than acted on.
                if self.asm.body_lo <= nxt < self.asm.body_hi - 7 and (
                        self.offset <= nxt < self.end - 7
                        or self.asm.entry_layout_holds(
                            nxt, struct.unpack_from('<I', self.asm.data, nxt)[0])):
                    start = nxt
        # EVERY POINTER CELL STATES A PAYLOAD, not just the last one. A chain list can
        # name more than one entry (see `fx_tree`), and `start` holds one handoff.
        starts = []
        for _o, _h, _s in cells:
            t = struct.unpack_from('<I', self.asm.data, _o + _s)[0] + 52
            if self.asm.body_lo <= t < self.asm.body_hi - 3 and t not in starts:
                starts.append(t)
        if not starts and start is not None:
            starts = [start]
        elif start is not None and start not in starts:
            starts.append(start)
        emitted = set()
        for st in (starts or [None]):
            for off, tag, prog in self.fx_table(st):
                if off in emitted:
                    continue
                emitted.add(off)
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

        THE YIELD ORDER IS LOAD-BEARING and a caller must not reorder it. An entry program
        can write slots as a side effect that a later one reads: on `sci_fi_elements_02`
        record 86 the `opacity` program sets slots 15, 17 and 18 while computing an angle,
        and the `frameoffset`, `patternsize` and `patternrotation` programs are bare `get`s
        of exactly those. 1,335 of 9,736 records with two or more entry programs (13.7%)
        have at least one such dependency.

        Table order then ascending slot -- what this yields -- is a runnable order:
        forward references occur in 0 of those 9,736 records, and reversing the order
        produces them, which is the control. `test_fx.py` asserts both.

        A reordering would not crash; it would produce a plausible wrong picture. That is
        the third instance in this decode of the same failure class, after samplers left
        installed from a previous record and a spread metric measured across channels.
        """
        d, lo, hi = self.asm.data, self.asm.body_lo, self.asm.body_hi
        seen = set()
        for kind, off, tag, _prog in self.fx_walk():
            if kind != 'entry' or off in seen:
                continue
            seen.add(off)
            layout = fx_entry_layout(tag)
            # A BAKED PARAMETER IS AS WIDE AS THE LAYOUT SAYS. This used to yield the single
            # raw slot WORD, so a parameter declared at width 2 lost its second component --
            # 928 entries over 20 files, 921 of them `patternsize`, and the values are not
            # degenerate: ChesterfieldSofa 331/333 store (5.0, 1.0), a 5:1 strip, and it was
            # drawn as a 5x5 square. `fxrender.entries` carried a width-aware override to
            # work around exactly this; the read itself is now correct, so the workaround is
            # a belt to the braces rather than the mechanism.
            #
            # Yielded as a TUPLE OF FLOATS, length = width, decoded here rather than handed
            # back raw: this module has no numpy, and a caller that received a bare word had
            # no way to know how many words the parameter actually occupied.
            widths = {sl: w for _b, sl, _n, k, w in fx_entry_walk(tag) if k == 'baked'}
            for sl, name, how in layout:
                if off + 4 * sl + 4 > hi:
                    break
                w = struct.unpack_from('<I', d, off + 4 * sl)[0]
                if how == 'baked':
                    n = widths.get(sl, 1)
                    if off + 4 * (sl + n) <= hi:
                        raw = d[off + 4 * sl:off + 4 * (sl + n)]
                        yield off, tag, sl, name, how, struct.unpack('<%df' % n, raw)
                    else:
                        yield off, tag, sl, name, how, struct.unpack('<f',
                                                                    struct.pack('<I', w))
                    continue
                if how == 'inline':
                    # The slot IS the program; its address is not read from the word. This
                    # kind is set STRUCTURALLY by `fx_entry_layout` (bits 25/27/29 with no
                    # program bit), not by probing whether the word decodes.
                    at = off + 4 * sl
                    yield off, tag, sl, name, how, (at if self.asm.program_span(at, hi)
                                                    else None)
                    continue
                # A program parameter is a POINTER. Follow it; report a miss as None. The
                # slot's word is NOT inspected to re-decide the structure the tag stated --
                # a previous version, when the last program's pointer failed, read that slot
                # as an inline program instead. Every one of those 2,717 recovered programs
                # lies BEYOND the entry: over the 1,910 with a following entry the recovered
                # start sits past the next entry's tag in 1,910 of 1,910, so it is bytecode
                # from a later structure, not this entry's field. Deciding pointer-vs-inline
                # from whether `word - 52` happens to land on decodable bytes is exactly the
                # value-driven read the format does not require, and it invented a phantom
                # `imageindex` that duplicated an earlier program pointer 2,056 times.
                pv = w + 52
                yield off, tag, sl, name, how, (
                    pv if lo < pv < hi and self.asm.program_span(pv, hi) else None)

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

    @property
    def fx_root(self):
        """For filter 4: the body offset of the FX tree/table root, or None.

        THE SLOT COMES FROM THE WALK. `decompose` reports it as `root`, derived from the
        two facts `walk.SPECS[4]` already states -- two mask words, then `Arity(prefix=1)`,
        one fixed non-edge slot before the image inputs. Nothing here stores a slot number.

        This is the one place the +52 header-to-body skew is applied to that pointer. It
        used to be written out four times -- `fx_tree`, `fx_entry_walk`,
        `node_census.harvest` and `reverify` each did `words[2] + 52` -- which is the
        duplication `fx_entry_walk`'s own note warns about at length: two implementations
        of one walk drift, and the nibble-8 category error survived as long as it did
        because the census and walk.py's validator made the same mistake in parallel and
        so never disagreed.

        Returns None rather than a guess when the record is not filter 4, when the walk
        declines it, or when the slot falls outside the record -- an absence a caller can
        see, not a word from the next record.
        """
        if self.filter_id != 4:
            return None
        import decompose as _decompose
        d = _decompose.decompose(self)
        if d is None:
            return None
        slot = d.get('root')
        if slot is None or slot >= len(self.words):
            return None
        return self.words[slot] + 52

    def fx_table(self, start=None):
        """For filter 4: yield (entry offset, tag, program offset or None) per entry.

        The counterpart to `fx_tree`. A record's slot 2 addresses either a linked node
        chain - walk it with `fx_tree` - or this: a run of entries. The two are told
        apart by whether the first word is a node header.

        STEPPING IS BY THE POINTER THE ENTRY STORES, and this said "by eight bytes" long
        after that stopped being true -- with the paragraph below the loop already saying
        the opposite in capitals. Both claims here were the retired `FX_ENTRY` stride and
        its justification ("following the entry's own pointer walks out of the record
        77.4% of the time"), and the code between them has followed the furthest-forward
        stored pointer for some time. `while q + 8 <= e` is a BOUNDS CHECK, not a stride,
        which is what let the wrong reading survive a look at the loop.

        Recording why this mattered rather than just deleting it: a stale docstring is a
        blocker with no measurement behind it, and this one produced a whole proposal to
        "fix the stride" before anyone read the loop it describes.

        The entry layout says where an inline program sits; `FX_PAYLOAD_PROG` covers
        the two tags it gets wrong. A tag neither names yields None, not a guess.
        """
        if self.filter_id != 4 or len(self.words) < 3:
            return
        d = self.asm.data
        q = self.fx_root if start is None else start
        if q is None:
            return
        # Bounded by the BODY, not by this record. A record's extent is a directory
        # partition, not an allocation: 805 fxmaps records address a table that lies
        # outside them, and in 757 of 757 resolvable cases it sits inside an earlier
        # record -- usually a blend or transformation, which cannot own an FX table. The
        # table is a body-level structure and the partition simply attributes it to
        # whichever record precedes it.
        o, e = self.asm.body_lo, self.asm.body_hi
        if not (o <= q < e - 7):
            return
        if start is None and node_shape(struct.unpack_from('<I', d, q)[0]) is not None:
            return
        limit = 64                       # runaway guard: the longest real walk is 17
        nth = 0
        while q + 8 <= e and limit > 0:
            limit -= 1
            tag = struct.unpack_from('<I', d, q)[0]
            # WITHDRAWN: STOPPING THE RUN ON THE BIT-7-CLEAR FAMILIES. `node_shape` only
            # knows bit-7-SET headers, so leaves and pointer cells appear in this run --
            # 26 and 34 of them across 32 records that yield no usable entry -- and that
            # looked like the run overreading into node territory. It is not. The run
            # follows each word's furthest-forward pointer, and the pointer goes THROUGH
            # the cell to a real entry beyond it:
            #
            #     fabric_002 233      0x00020008 -> 0x0000014b -> 0x0a000a48   holds
            #     Camouflage_02 223   same shape                               holds
            #     CardBoard 491       0x00420008 -> 0x0000014b -> 0x15000448   holds
            #
            # A pointer cell in the run is a WAYPOINT, not a terminator. Breaking on one
            # costs records their table and gains none: at position 0, 80 records lost, 0
            # gained -- `entries()` starts this run at a root that is itself a chain cell,
            # so it refuses the run its own caller asked for. Applied from the second word
            # instead, 3 lost, 0 gained, and those 3 are the shape above, where the entry
            # AFTER the cell is the one `entries()` was keeping. The cells themselves cost
            # nothing: they are not drawable tags and `entries()` filters them already.
            #
            # So the stop stays `node_shape` alone. Recorded rather than left to be
            # re-derived: the census that motivated this counted waypoints as junk, and the
            # only instrument that told the difference was the corpus entry diff.
            if node_shape(tag) is not None:
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
            if (tag & 0xF) in (9, 0xB):
                # A NODE reached inside the entry run. A low nibble of 9 or B is a node
                # header, not an entry tag -- the 0x??0B leaf family, whose successor and
                # programs `fx_tree` reads by scanning. Its program slots are NOT a fixed
                # list: 0x0000190B alone occurs as (4,7) in 129 nodes and as (5,6,7,8) in
                # 124, so a census stating one slot list per tag is wrong per-instance.
                # `FX_ENTRY_PROGS` used to state exactly that and this drains it -- the same
                # disjoint-span scan `fx_tree` runs for a `progs=None` node reads each node
                # on its own bytes, which is +3,480 programs over that census corpus-wide.
                # BOUNDED BY THE ELEMENT'S OWN STATED EXTENT. `range(2, 14)` reads
                # twelve slots out of a structure that says how wide it is: the 0x9/0x49
                # family declares no parameters but is a linked-list member, its slot 1
                # pointing at the next element, and that stored step is its statement of
                # where it ends. Corpus-wide the scan yields 59 programs from these words
                # and NOT ONE lies inside the element it is attributed to:
                #
                #     a LATER element, slot 2 (its handoff pointer)     42
                #     a LATER element, slot 1 (its next pointer)         1
                #     lands in no element of the chain                  16
                #
                # So 43 of 59 name a word whose meaning is already established elsewhere
                # -- slot 2 is the handoff `fxrender` resolves, slot 1 is the step this
                # bound is read from -- and call it a program of the element three or more
                # words back. `program_span` cannot catch that: a handoff pointer addresses
                # real bytecode, so the pointer disassembles and only the OWNERSHIP is
                # wrong. That is also why the slot list looked per-instance (0x0000190B as
                # (4,7) in 129 nodes and (5,6,7,8) in 124) -- those are neighbours, not
                # variants.
                #
                # `walk_partition.stated_extent` implements this same rule and reports the
                # trespass ("slot 5 of a 3-word structure (stated)"). This does NOT call
                # it, deliberately: that module is the independent arbiter for exactly this
                # class of error, and a decode wired into the checker that validates it
                # makes the check true by construction.
                #
                # Where the element states nothing -- no forward step in the body -- the
                # scan is left at its full width rather than guessed at.
                _step = struct.unpack_from('<I', d, q + 4)[0] + 52
                _lim = min(14, (_step - q) // 4) if q < _step < e else 14
                any_ = False
                for sl in range(2, _lim):
                    if q + 4 * sl + 4 > e:
                        break
                    pv = struct.unpack_from('<I', d, q + 4 * sl)[0] + 52
                    if o < pv < e and self.asm.program_span(pv, e) and (
                            struct.unpack_from('<I', d, pv)[0] & 0xF) not in (9, 0xB):
                        yield q, tag, pv
                        any_ = True
                if not any_:
                    yield q, tag, None
            else:
                # THE TAG STATES ITS OWN PROGRAM SLOTS. `fx_entry_layout` walks bits 19..31
                # in ascending order and marks each program pointer's slot; this replaces
                # the `FX_ENTRY_PROGS` census, which it reproduces on every one of its tags
                # and extends to the tags it never saw. Bit 26 alone (`patternsize` as a
                # program) names slot 2 on the whole 0x040002xx.. family the census left
                # blank, and 0.0% of the slots it adds lie inside another program's span.
                slots = [sl for sl, _nm, kind in fx_entry_layout(tag)
                         if kind == 'program']
                if slots:
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
                    # No program bit is set, so the program -- if any -- is inline after the
                    # baked parameters (bit 25/27/29) or at `FX_PAYLOAD_PROG`'s stated offset
                    # for the two tags whose self-pointer base the inline rule reads wrong.
                    prog = None
                    off = FX_PAYLOAD_PROG.get(tag)
                    if off is not None:
                        if o <= t < e - 3 and t + off + 4 <= e \
                                and self.asm.program_span(t + off, e):
                            prog = t + off
                    else:
                        inline = [sl for sl, _nm, kind in fx_entry_layout(tag)
                                  if kind == 'inline']
                        if inline:
                            cand = q + 4 * inline[0]
                            if cand + 4 <= e and self.asm.program_span(cand, e):
                                prog = cand
                    yield q, tag, prog
            # THE NEXT ENTRY IS THE POINTER THE ENTRY STORES, not a tabled stride. One header
            # slot holds a pointer to the following entry -- the one reaching FURTHEST forward,
            # past this entry's own inline program (slot 1 for 0x00020008, slot 2 for
            # 0x00420008). `FX_ENTRY` was a per-tag fit of that pointer's DISTANCE, and lossy
            # because the distance is the inline program's length -- which the entry states,
            # `_program_span_scan` reading its instruction count -- and is not a function of the
            # tag. Following the stored pointer reaches 77,637 real entries the stride stopped
            # short of with zero phantoms, needs no table and tests no value on the target: the
            # header slots come from the mask-walk and `entry_layout_holds` at the top of the
            # loop is the stop. `FX_ENTRY` is drained by this, kept only as a census.
            hdr = fx_entry_layout(tag)
            span = (max(sl for sl, _n, _k in hdr) + 1) if hdr else 1
            nxt = None
            for sl in range(1, span + 1):
                if q + 4 * sl + 4 > e:
                    break
                pv = struct.unpack_from('<I', d, q + 4 * sl)[0] + 52
                if q < pv < e and (nxt is None or pv > nxt):
                    nxt = pv
            if nxt is None:
                return
            q = nxt

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
        # BOUNDED BY THE BODY, NOT BY THIS RECORD -- the same correction `fx_table` already
        # carries, for the same reason it states: "a record's extent is a directory
        # partition, not an allocation", and an fxmaps record can address a structure that
        # lies outside its own span. The tree was bounded by `self.offset .. self.end`, so
        # a root outside the record made `while o <= q < e - 7` false on the FIRST
        # iteration and this yielded nothing at all.
        #
        # Every root-stop record in the corpus is that case: 39 records, root outside the
        # record in 39 of 39, inside the body in 39 of 39, and `node_shape` already knows
        # the header in 27 of them. Those 27 were never rejected by the vocabulary -- the
        # walk never reached the point of asking.
        #
        # `why_no_entries` reports them as "not in the node vocabulary" because it reads
        # the header itself and infers the walk refused it. That inference is wrong for the
        # 27, and it is the same misattribution that function exists to prevent, one level
        # further in.
        d, o, e = self.asm.data, self.asm.body_lo, self.asm.body_hi
        q, seen = self.fx_root, set()
        if q is None:
            return
        pending = []
        while o <= q < e - 7 and q not in seen:
            seen.add(q)
            h = struct.unpack_from('<I', d, q)[0]
            shape = node_shape(h)
            if shape is None:
                # The leaf/branch families node_shape does not derive (low-byte bit 7 clear).
                # A 0x1B branches, so the walk stops being a straight line here; `pending`
                # carries the far child and the near one continues inline. Order is not
                # claimed to be the engine's.
                # THE 0x1B BRANCH STATES ITS OWN SHAPE IN WORD 1, so read it instead of
                # the hand-stated row. Over the whole corpus, all 355 `0x1B` nodes split
                # on that word with no residue:
                #
                #   word 1 == 0x3039   343   [hdr][0x3039][ptr -> a distant 0x18B]
                #                            [contiguous 0x18B]  -- two children, no
                #                            program of its own
                #   word 1 == 0         12   a six-word self-relative form (w2 -> +12,
                #                            w4 -> +20, w5 -> a program), 12 of 12 exact
                #
                # `FX_NODES2[0x1B] = ((8, 20), (16,))` is wrong for the 343: byte 20 and
                # byte 16 are the FOLLOWING `0x18B`'s own successor and program, since that
                # node starts at byte 12 and `node_shape(0x18B)` is `(8, (4,))` -- 12+8 and
                # 12+4. The row was derived by reading the neighbour's fields as this
                # node's, which `fxrender` measured independently on 34 nodes in one file
                # and declined to correct from there.
                #
                # What that costs today: nothing addresses byte 12, so the contiguous
                # `0x18B` is NEVER VISITED AS A NODE -- its program is yielded under the
                # `0x1B`'s offset and its successor followed as if it were the branch's.
                # The traversal still reaches the same descendants; the node census and the
                # program attribution are what is wrong. Reading word 1 fixes both.
                #
                # THE 12 ARE LEFT ON THE OLD ROW DELIBERATELY. Their six-word form is
                # characterised but their successor is not, so there is nothing yet to put
                # in `nxts` for them; changing their behaviour would be a guess where the
                # 343 is a measurement. They are all in one file (`Splatter.sbsasm`).
                _extra = []
                if (h & 0xFF) == 0x1B and q + 8 <= e:
                    _w1 = struct.unpack_from('<I', d, q + 4)[0]
                    if _w1 == 0x3039:
                        # One POINTER child at byte 8; the other child is CONTIGUOUS at
                        # byte 12 and so cannot go in `nxts`, which pointer-reads each
                        # offset. It is appended to the targets directly below.
                        _extra.append(q + 12)
                        shape2 = ((8,), None)
                        nxts, prog_slots = shape2
                        yield q, h, None
                        targets = []
                        for n_off in nxts:
                            if q + n_off + 4 > e:
                                return
                            targets.append(
                                struct.unpack_from('<I', d, q + n_off)[0] + 52)
                        targets.extend(_extra)
                        pending.extend(targets[1:])
                        q = targets[0]
                        continue
                    # NON-SENTINEL: this branch has no node children at all -- it hands
                    # off to the TABLE, which begins contiguously at byte 12 (verified
                    # against `FX_TAG_LOW16` on 12 of 12, and `fx_walk` starts the entry
                    # scan there). So bytes 16 and 20, which `FX_NODES2` calls this node's
                    # program and second successor, are the ENTRY's own fields -- the same
                    # borrow-the-neighbour error as the sentinel form, one structure over.
                    # Yield the node owning nothing and let the chain end here.
                    _t3 = (struct.unpack_from('<I', d, q + 12)[0]
                           if q + 16 <= e else 0)
                    if (_t3 & 0xFFFF) in FX_TAG_LOW16:
                        yield q, h, None
                        if not pending:
                            return
                        q = pending.pop()
                        continue
                if pointer_cell_successor(h) is not None:
                    # A POINTER CELL, and the list it sits in. Both are LINKED-LIST
                    # elements that state their next at slot 1, so the list is walked by
                    # the pointers it stores rather than by a stride:
                    #
                    #   [09|49][next][payload]   3 words -- states a payload at slot 2
                    #   [0x000200.8][next]       2 words -- link only, `entries()` already
                    #                            calls this chain-family structural, not a
                    #                            draw (word[1]+52 == next in 98.5%)
                    #
                    # They strictly alternate. `stylized_rocks_magma` record 9 is why the
                    # list has to be walked and not just entered: its three pointer cells
                    # name TWO DISTINCT payloads (0x13ec, 0x1328), so following the first
                    # cell's slot 2 and stopping loses the second entry outright. That is
                    # the regression this branch was written wrong the first time and
                    # caught by diffing entry counts against HEAD -- 12 records, all
                    # 2 entries -> 1.
                    #
                    # Only the pointer cells are yielded; the links carry nothing. The
                    # payloads are read by `fx_walk`, which follows slot 2 on each cell it
                    # sees here -- one derivation, used by both halves.
                    # `q` is already in `seen` -- the outer loop adds it on arrival, so
                    # this steps rather than re-testing it and stopping on the first cell.
                    while o <= q < e - 7:
                        hh = struct.unpack_from('<I', d, q)[0]
                        if pointer_cell_successor(hh) is not None:
                            yield q, hh, None
                        elif (hh >> 16) != 0x0002:
                            break
                        if q + 8 > e:
                            break
                        nq = struct.unpack_from('<I', d, q + 4)[0] + 52
                        if nq in seen or not (o <= nq < e - 7):
                            break
                        seen.add(nq)
                        q = nq
                    if not pending:
                        return
                    q = pending.pop()
                    continue
                _lf = leaf_successor(h)
                if _lf is not None:
                    # DERIVED, not tabulated: the mask gives the leaf's successor, so
                    # `FX_NODES2` no longer states it. `prog_slots` stays None because the
                    # leaf's programs are still scanned below -- that scan is a separate
                    # question from where the successor is, and it is measured in
                    # FX_NODES2's comment.
                    shape2 = ((_lf,), None)
                else:
                    shape2 = FX_NODES2.get(h & 0xFF)
                if shape2 is None:
                    return
                nxts, prog_slots = shape2
                # AN EMPTY PROGRAM TUPLE IS "NO PROGRAM", NOT "NO NODE". The yield below
                # lives inside `for sl in prog_slots`, so a row stating `()` walked its node
                # and never reported it -- invisible to `fx_walk`'s `last`, to the pointer
                # cells it collects, and to `node_census`. `FX_NODES2[0x1B]` is such a row,
                # and the 12 records whose root is a `0x?1b` were reported as "walk reached
                # NOTHING" for that reason alone rather than because the header was unknown.
                #
                # THIS FIXES NO RECORD'S OUTPUT, and that was measured before making it: for
                # all 12 the successor reaches exactly one entry and it passes
                # `entry_layout_holds` in 0 of 12, so they stay empty either way. It is here
                # because a node that walks and is never yielded is a silent hole in every
                # consumer of this generator, and the next row stating `()` inherits it.
                if not prog_slots:
                    # THE LEAF NAMES NO PROGRAM, and the walk no longer pretends it does.
                    #
                    # This SCANNED words 4..13 and yielded anything whose `+ 52` passed
                    # `program_span` -- a probe, the same act as the phantom programs
                    # `Record.programs` used to manufacture from bytecode. Bit 7 clear says
                    # a leaf has no base program structure, so a program found by sweeping
                    # its words is not one the record named.
                    #
                    # Over 20 files: 28 distinct leaves reached by the walk yield 73 program
                    # items between them (1 to 5 each), and EVERY one of the 73 is also named
                    # by an ENTRY of the same record -- 0 unique to a leaf -- with the leaf
                    # always yielded first. So the scan reached no program the walk does not
                    # already have; it reached them earlier and attributed them to the wrong
                    # node. Checked non-circularly, by excluding the leaf's own yields from
                    # the comparison set -- including them confirms every candidate by
                    # construction, which is how an earlier pass of this read "all confirmed"
                    # for the wrong reason.
                    #
                    # RENDER-CHECKED IN ISOLATION, which is the only way it could be checked
                    # honestly: a pristine HEAD copy with just this block replaced, against
                    # HEAD, over four fxmaps files -- 6,077 rendered records, 0 differing.
                    # Measuring it in the shared working tree instead said 3,968 of 6,077
                    # differed, all of it another session's uncommitted edits and none of it
                    # this change. The harness is deterministic (identical code twice, 0
                    # differences); the tree was not the code under test.
                    #
                    # The path that made this worth checking rather than assuming:
                    # `fxrender.emissions` seeds the slot frame by RUNNING every program of
                    # the record the chain and table do not claim --
                    #
                    #     fx_progs = {p for _o, _h, ps in nodes for p in ps.values() if p}
                    #     for prog in sorted(set(rec.programs) - fx_progs): run(prog, ...)
                    #
                    # -- so a scanned leaf program was being SUBTRACTED from that loop, and
                    # dropping the scan could have started executing it as a seeder. It does
                    # not: the table already claims all 73 through the entries that name them.
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

        THE RECORD'S OWN BIT DECIDES WHETHER THERE IS ONE. w1 bit 6 says a baked `matrix22`
        is present; the walk then names its slot, by FIELD (the w1 pair at bits 6,7). Bit 6
        clear means no baked matrix and this returns None -- it does not go looking for one.

        Source matrices appear verbatim here in 66 of 72 cases across 23 permitted files,
        the misses being nodes the cooker eliminated. The values read as transforms should
        - `2 0 0 2`, `-1 0 0 -1`, `1.4014 0 0 1.4014` - and the off-diagonals are zero in
        94% and 76% of records, since most transforms scale or flip without shear.
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
        #
        # THE WALK NAMES THE SLOT NOW, and the ladder above is what it replaces -- four
        # candidate formulas ranked by which best lands a plausible matrix, the same
        # value-probe method retired from `translation` (the Float2 sibling of this
        # parameter) and from blur, sharpen and warp. `transformation` declares exactly two
        # parameters, a Float4 `matrix22` and a Float2 `offset`, so in `decompose`'s
        # (field, state, position, WIDTH) tuples the width-4 entry IS the matrix, with
        # nothing to choose between.
        #
        # SWAPPED AT ZERO DIFF, which is the point rather than a disappointment: the fitted
        # rule was already at 100.0%, so there is no coverage to win here, only a rule
        # selected by plausibility to remove. Over the corpus, filter 2:
        #
        #     bit 6 says baked   66,508 records   walk agrees 66,506   disagrees 0   silent 2
        #     bit 6 clear       168,351           walk silent 168,349  disagrees 2
        #
        # The walk is consulted only where the record's OWN bit 6 says a baked matrix is
        # there, so the 2 silent ones fall back to the formula and nothing changes. The two
        # bit-6-clear disagreements are left alone deliberately: the walk finds a width-4
        # slot in a record that says it has no baked matrix, and which of those two
        # statements is wrong is not established here. They are recorded, not resolved.
        base = None
        if (self.words[1] >> 6 & 1) if len(self.words) > 1 else False:
            try:
                import decompose as _decompose
                _d = _decompose.decompose(self)
            except Exception:
                _d = None
            if _d:
                # BY FIELD, NOT BY WIDTH. `matrix22` is the w1 pair at bits 6,7 -- field 3
                # under the two-bit tiling `decompose` reports in `param_slots[0]`. Selecting
                # "the sole width-4 entry" instead was ambiguous whenever w1 bit 28 (the
                # background colour) is set on a COLOUR record, because that parameter is a
                # Float4 too: two width-4 entries, no way to choose. Corpus-wide the field
                # rule agrees with the width rule on all 66,506 records where both answer,
                # never disagrees, and resolves the 2 the width rule could not --
                # NightSkyHDRISubstance001 record 1589 (slots 3 and 7) and pbr_render record
                # 44 (slots 3 and 9), both w1 bit 28 set. 66,508 of 66,508.
                _m = [t for t in _d.get('param_slots', ())
                      if len(t) >= 4 and t[3] == 4 and t[0] == 3]
                if len(_m) == 1:
                    base = 4 * _m[0][2]
        if base is None:
            # NO BAKED MATRIX DECLARED, SO THERE IS NO MATRIX TO RETURN. This used to fall
            # back to `4 * (3 + cls bit 0 + cls bit 7)` -- the last rung of the ladder above,
            # kept "for the 2 records where the walk is silent". Instrumenting the method
            # rather than reconstructing its inputs shows what it was really doing: the walk
            # is consulted ONLY when bit 6 is set, so all 168,349 bit-6-CLEAR records skipped
            # it entirely and were answered by the formula. Corpus-wide, filter 2:
            #
            #     bit 6 set, walk answers    66,506      bit 6 set, walk silent        2
            #     bit 6 clear, walk silent  168,349      bit 6 clear, walk answers     2
            #
            # 234,855 of 234,859 -- the walk answers if and only if the record's own bit 6
            # says a baked matrix is there. The formula produced a matrix in 276 of the
            # records it was left to answer, 274 of them with bit 6 CLEAR, and 175 of those
            # read from a slot PAST the walk's header end -- bytecode, or the next structure.
            # All 276 survived only because they passed the finite/non-singular screen below,
            # which is a plausibility window, not a reading.
            #
            # Nothing downstream loses a value: render.py already re-applied the bit at the
            # call site (`m = rec.matrix if (w1 >> 6 & 1) else None`, added when honouring it
            # took ChesterfieldSofa from 659 non-finite records to 0), so those 276 were
            # discarded by the only consumer. The bit now lives in the accessor instead of
            # being re-tested by each caller.
            #
            # The 4 off-diagonal records are recorded, not resolved: 2 where bit 6 is set and
            # the walk finds TWO width-4 slots, and 2 where it names one in a record that says
            # it has no baked matrix. Which statement is wrong is not established here.
            return None
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

        The slot now comes from the WALK rather than from a formula stepping over an assumed
        matrix, so a matrix-less record is read rather than refused: see the comment below.
        Superseded: "Returns None when the matrix is absent -- those records have no parameter
        block to pack against, and the slot lands in bytecode 97.4% of the time." That was true
        of the formula, and it is the formula that has been replaced.
        """
        if self.filter_id != 2 or len(self.words) < 2:
            return None
        w = self.words[1]
        if not (w >> 25 & 1):                   # not baked (bit 26 means it is a program)
            return None
        # THE WALK NAMES THE SLOT; the formula below only ever guessed at it. `decompose`
        # enumerates a record's parameter slots as (field, state, position, WIDTH), and
        # `transformation` has exactly two parameters -- a Float4 `matrix22` and a Float2
        # `offset` -- so the width-2 entry IS the offset, with nothing to choose between.
        #
        # `3 + colour + bit7 + 4` steps over a matrix it ASSUMES is present. Over 14 corpus
        # files 659 records set bit 25 and 621 carry a matrix: walk and formula name the
        # same slot in all 621, and differ in exactly the 38 with NO matrix, where the
        # `+ 4` overshoots -- 26 past the walk's header end into bytecode, 12 past the
        # record entirely. Those 38 are NOT misread today; the matrix guard declines them,
        # which is what this docstring's "lands in bytecode 97.4% of the time" is about.
        # So this RECOVERS 38 offsets that had to be refused -- the walk knows the matrix
        # is absent and the formula cannot -- rather than correcting a wrong value.
        #
        # The widths also settle what the two bits mean, which this docstring left open.
        # Field 12 (bits 24/25) costs 2 words in all 659 -- a Float2 pair, not a pointer --
        # so bit 25 is a BAKED offset; field 13 (bits 26/27) costs 1, a program pointer.
        # The generic `01 = baked, 10 = program` table does not decide these fields; the
        # cost model's WIDTH does, and it agrees with the bits as read here.
        s = None
        try:
            import decompose
            _d = decompose.decompose(self)
        except Exception:
            _d = None
        if _d:
            # BY ITS FIELD, not by "the sole two-word entry". The offset's two-bit code
            # sits at bits 25,26, which the tiling's even-bit grid used to split across
            # fields 12 and 13; `decompose.STRADDLED` reframes it as one field carrying the
            # ordinary alphabet, so state 1 IS the baked Float2 and can be asked for. Over
            # 242,931 filter-2 records the field read names the same slot the width rule
            # named, on every record where that rule answered, and it no longer depends on
            # no other parameter happening to be two words wide.
            _two = [t for t in _d.get('param_slots', ())
                    if len(t) >= 4 and t[0] == 12 and t[1] == 1]
            if len(_two) == 1:
                s = _two[0][2]
        if s is None:
            # UNREACHABLE, AND MEASURED SO RATHER THAN ASSUMED. This was the old path --
            # `3 + cls bit 0 + cls bit 7 + 4`, stepping over a matrix it assumed was there.
            # Instrumenting this method over the corpus: it is called on 234,859 filter-2
            # records, the walk answers 29,331 and is silent 205,528, and the method returns
            # None exactly 205,528 times. Nothing reaches the formula, because the bit-25
            # guard above already rejected every record the walk is silent on:
            #
            #     bit 25 set, walk answers   29,331      bit 25 set, walk silent       0
            #     bit 25 clear, walk silent 205,528      bit 25 clear, walk answers    0
            #
            # 234,859 of 234,859. The walk's coverage IS the format's own declaration, so
            # the formula had nothing left to answer. Returning None keeps that explicit.
            return None
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

        NOT A FITTED CONSTANT, and the record says so itself. A sweep for slot arithmetic
        that bypasses the walk flagged this expression on the strength of that 94.4%,
        reading it as a formula patched by a bound. It is neither. It reads two STATED
        bits -- the tag's colour flag and class bit 8 -- which is the same width legend
        the walk applies everywhere else: a per-channel field's width is a constant of
        its kind, selected by the colour flag (SPEC 6.4). Retracting that flag.

        The record's own stated extent corroborates it independently. Slot 2 gives the
        stop COUNT and the pair gives a span, so where that span is an exact multiple of
        the count the width is a READ rather than a formula. Full corpus, 17,866 records
        with a ramp pointer:

            span exact and 4/6/8      11,707      formula agrees on 11,706   99.99%
            span not an exact extent   6,159      slot 4 is a bound, as above

        The single disagreement reads width 6 by formula and 8 by span, and NEITHER gives
        ascending stop positions, so it is a record this decode does not read rather than
        evidence between the two.

        And the bound holds, which is a check that could have failed. Over 200 specimens,
        7,152 ramp records: 4,594 where the span equals count x width exactly, 551 where
        it is larger, and ZERO where count x width overruns the span the record states.
        A width too wide would have shown up here as a table running past its own bound.

        Slot 2 is *not* an input edge. It reads as one - a small backward value - but
        its resolution agreement with the record is 35.5%, which is chance, where a real
        edge agrees at ~100%.

        VERIFIED AGAINST THE SOURCES THAT DECLARE IT, which had never been done -- every
        justification above is internal to the binary. A `.sbs` gradient node carries
        `gradientrgba` as an array of cells, each with a `position` and a `value`, so a
        stop with enough decimals to be distinctive locates the record by containment and
        its colour can then be read back. Over the permitted paired sources:

            distinctive stops sought              34
              located in exactly one record       25
                and its COLOUR matches            24        to within 0.02 per channel
                but its colour differs             1
              ambiguous (2 or 3 records)           7
              not found                            2

        24 of 25 covers both storage forms -- the packed-u16 entries and the 5-float
        (20-byte) exact-span form -- and it is what licenses the ramp for colour work
        rather than only for structure. The one disagreement is `Wood_Planks` record 68,
        where the position matches to 2e-4 but the source's grey (0.0217 x3) reads back as
        (0.569, 0.020, 0.000): either a form this decode picks wrongly or a coincidental
        position collision with an unrelated record, and one specimen does not separate
        those.

        A FOUR-WORD RECORD STATES ITS COUNT AND START AND NO UPPER BOUND, and the count
        supplies one. This used to require five words, so `concrete_049` records 110 and
        235 -- class 0x0118, words [hdr, uid, 4, ptr] -- returned None and refused with
        "gradient record carries no readable ramp", blocking six declared outputs. Slot 4
        is described above as "an upper bound on the table": it is a BOUND, not the extent,
        and `count x width` is the extent exactly.

        The width formula is the one already established here, and on these two records it
        is the only one that reads back a ramp at all. `colour` is False and class bit 8 is
        set, so width is 4 + 0 + 2 = 6, and stepping by 6 gives positions 0.0, 0.5, 0.5042,
        1.0 -- ascending, which a ramp must be -- with values alternating 0 and 65535.
        Stepping by 4 gives 0.0, 0.5, 1.0, 0.5042 and by 8 gives 0.0, 1.0, 0.5, 0.3984;
        both are out of order, so the width is singled out here rather than merely allowed.
        """
        if self.filter_id != 0 or len(self.words) < 4:
            return None
        count = self.words[2]
        if not count:
            return None
        # THE PAIR IS NOT ALWAYS AT WORD 3. Some records carry an extra float parameter
        # there and put the pointers one word later -- Auras records 312, 424 and 442 hold
        # 0x3F63D70A and 0x3F800000 (0.89 and 1.0) at word 3, which addresses nothing, with
        # a perfectly good (start, end) pair at words 4 and 5.
        #
        # Chosen by which pair ADDRESSES THE BODY, not by a class bit: only 4 records in 40
        # corpus files plus every reference package have the shift, and 4 records is far too
        # thin to name a bit from -- the same reasoning the float-width note below gives for
        # reading the span instead of the class. Word 3 is tried first, so no record that
        # reads today can change.
        start = end = None
        for k in (3, 4):
            if len(self.words) <= k + 1:
                break
            a = self.words[k] + 52
            b = self.words[k + 1] + 52
            if self.asm.body_lo <= a < self.asm.body_hi:
                start, end = a, b
                break
        if start is None and len(self.words) > 3:
            # No successor word to bound the table -- derive the end from the count. See
            # the four-word note in this docstring.
            a = self.words[3] + 52
            if self.asm.body_lo <= a < self.asm.body_hi:
                width = 4 + 2 * bool(self.colour) + 2 * ((self.cls >> 8) & 1)
                start, end = a, a + count * width
        if start is None:
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
        # A FIVE-FLOAT FORM AS WELL: position, R, G, B, A, with no trailing -1.0. Auras
        # records 312, 424 and 442 span exactly count * 20 bytes and decode to a ramp that
        # reads like one -- positions ascending 0.0, 0.0696, 0.2025, 0.3249, 0.6442,
        # 0.9515, 1.0, every component inside [0, 1], and alpha 1.0 at every stop. Under
        # the 6-float reading the same bytes give a position sequence that does not ascend
        # and a component of 5.4e16.
        #
        # Selected the same way the 6-float form is: by which width makes count * width
        # equal the span EXACTLY. A 20-byte table fits a u16 reading and a 24-byte one does
        # not fit these, so exact match is what separates them, and it is tried before the
        # containment path below for the reason that path already records.
        for fwidth in (4 * (6 if self.colour else 3), 20 if self.colour else 0):
            if not fwidth or (end - start) == count * width:
                continue
            if (end - start) != count * fwidth:
                continue
            out = [struct.unpack_from('<%df' % (fwidth // 4), self.asm.data,
                                      start + i * fwidth) for i in range(count)]
            if any(out[i][0] > out[i + 1][0] for i in range(len(out) - 1)):
                continue
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
            # BIT 3 SAYS THE IMAGE IS JPEG, and this decoder used to read the compressed
            # bytes as raw pixels. Only bits 0-2 of this byte were read; bit 3 was found
            # by chasing the one thing in a 437-file self-check that looked like a decode
            # bug rather than a property of the files -- GravelSubstance002's declared
            # image sizes running ~900 KB past the next image's start.
            #
            # It predicts perfectly. Over 706 consecutive image pairs corpus-wide:
            #
            #                     declared size fits   does not fit
            #     bit 3 clear            697                0
            #     bit 3 set                0                9
            #
            # Both off-diagonal cells empty. The payload confirms it independently: all 9
            # have a JPEG SOI at exactly offset + 52 -- the same +52 bias this format uses
            # for record pointers -- and all 9 decode to precisely the width, height and
            # channel count the RECORD declares (1024x1024x1 and 2048x2048x1), which
            # nothing in a JPEG stream could know.
            #
            # THE COMPRESSED LENGTH IS AT BYTE 48, a u32 immediately ahead of the SOI. It
            # equals the stream's actual SOI..EOI extent in 54 of 54, so the payload does
            # not have to be found by scanning for an EOI -- which matters, because
            # `ff d9` can occur inside entropy-coded data. `size` stays the UNCOMPRESSED
            # size, because that is what it is. The other 48 bytes are not identified.
            #
            # This does NOT restore packing: the space between these images is far larger
            # than the JPEG, and GravelSubstance002 holds 17 SOI markers against 7 flagged
            # records, so other images live in the gaps.
            #
            # ONLY TWO CLASS WORDS CARRY THE FLAG, and the second resolves a gap this file
            # has documented for a long time:
            #
            #     cls 0x0908   hi & 3 == 1  ->  1 channel      9 records
            #     cls 0x0808   hi & 3 == 0  ->  CHANNELS has no entry     45 records
            #
            # 0x808 is the "channel code CHANNELS does not cover" that `Record.bitmap`'s
            # docstring reports with channels, depth and size all None. It is a JPEG with
            # no channel bits set, and the channel count is in the JPEG itself -- mode L is
            # 1, RGB is 3. So `channels` stays None here, honestly, and the decoder takes
            # it from the stream. (The old note called these "all 2048x2048"; they are not,
            # 1024x512 occurs too. That came from a smaller sample.)
            #
            # 45 of the 54 carry real content, up to a 3.7 MB stream; only 9 are the blank
            # white "no mask" defaults found first. Untreated, the 9 read entropy-7.7 JPEG
            # bytes as pixels and feed that noise downstream without refusing, and the 45
            # refuse on the undecodable channel code -- so this is both a correctness fix
            # and 45 images the renderer could not previously produce at all.
            if hi & 8:
                return {'kind': 'pixels', 'offset': off + 4, 'compressed': 'jpeg',
                        'data_offset': off + 4 + 52,
                        'size': self.width * self.height * ch * bpc if ch else None,
                        'channels': ch, 'depth': bpc * 8 if ch else None}
            # THE STORED OFFSET IS 4 LOW. The pixel region is at the FRONT of the file,
            # ahead of the assembly body, and the header in front of it is eight bytes,
            # not four:
            #
            #     word@0  0x4d414253 = 'SBAM', the file magic       40 of 40 files
            #     word@4  low 16 bits zero -- a version field       40 of 40 files
            #             (0x20000, 0x50000, 0x60000, 0x90000)
            #
            # yet the first bitmap in every one of those files declares offset 4, which
            # is the version word. So pixels begin at 8 and every declared offset is four
            # bytes short of its data.
            #
            # It went unnoticed because it is INVISIBLE in the commonest layout: four
            # bytes is a whole pixel at depth 8 with 4 channels, so that decode is right
            # either way (it merely starts one pixel late). Everywhere else it rotates
            # the channels by 4/(depth/8) mod ch, and the rotation it predicts -- from
            # the layout alone, before looking at any image -- is the one measured:
            #
            #     depth  8 ch 4   shift 0   measured 0   (pix_alley_oil, already correct)
            #     depth  8 ch 3   shift 1   measured 1   (brown_mud_leaves_01)
            #     depth 16 ch 4   shift 2   measured 2   (hiero_03, pix_concrete_02)
            #
            # Corpus-wide the RGBA case is self-controlling, since an RGBA image's
            # flattest channel is its alpha and belongs at index 3: at the declared
            # offset it lands at index 1 in 13 of 16 depth-16 4-channel bitmaps, and at
            # +4 it lands at index 3 in 13 of 16. The depth-8 4-channel bitmaps are the
            # null control and give the same answer both ways.
            #
            # Note what does NOT show this: the images pack back-to-back exactly (174 of
            # 174 consecutive pairs, offset[k+1] - offset[k] == size[k]), which reads as
            # a corroboration of the offsets but is invariant to a UNIFORM shift and so
            # says nothing either way. It was briefly taken as a refutation.
            return {'kind': 'pixels', 'offset': off + 4,
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
    _CACHE = {}

    @classmethod
    def cached(cls, path):
        """A shared parsed instance. Safe because readers never mutate an Assembly;
        the memo tables only grow. The test suite re-parsed the full corpus once per
        corpus-sweeping test -- a dozen sweeps of 437 files -- and with data mmapped
        the cache holds records and memos, not file bytes."""
        key = (path, os.stat(path).st_mtime_ns)
        hit = cls._CACHE.get(key)
        if hit is None:
            hit = cls._CACHE[key] = cls(path)
        return hit

    def __init__(self, path):
        self.path = path
        # mmap, not read(): the bytes stay in the OS page cache and are SHARED between
        # Assembly instances and processes, so caching parsed Assemblies costs the
        # records and memo tables, not four gigabytes of file data.
        import mmap as _mmap
        fh = open(path, 'rb')
        try:
            self.data = d = _mmap.mmap(fh.fileno(), 0, access=_mmap.ACCESS_READ)
        except (ValueError, OSError):
            self.data = d = fh.read()
        self._vp_cache = {}
        self._pe_cache = {}
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
        # The floor for a program. `body_lo` is the header end (layout B) or directory end
        # (layout A), and in layout B a 16-byte gap sits between the header at 0x38 and the
        # first record: `valid_program` had only an upper bound, so a slot holding a small
        # value (a mask edge, say 12) resolved +52 into that gap and decoded as a phantom
        # program -- 281 of them corpus-wide, all below the first record. Code lives in
        # record bodies, so the first record's offset is the true floor; every real program
        # is at least 8 bytes past it, so this excludes the phantoms and no genuine program.
        self.code_lo = offs[0] if offs else self.body_lo
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
        k = (p, slack)
        hit = self._vp_cache.get(k)
        if hit is not None:
            return hit
        r = self._valid_program(p, slack)
        self._vp_cache[k] = r
        return r

    def _valid_program(self, p, slack=0):
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
        if p + 4 > hi or p < self.code_lo:
            return False                       # past the body, or before the first record
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
        # The bound is the FIELD's range, not a guess about programs. The cap sat at
        # 20,000 as an anti-garbage margin and silently rejected the corpus's largest
        # per-pixel functions -- 45 records whose functions run 21,102 to 41,493
        # instructions, every one decoding cleanly and operand-exact once the cap
        # lifts. Garbage does not survive 20,000 consecutive opcode-and-operand
        # checks; the checks are the filter, the cap never was.
        if not (1 <= n <= 0xFFFF):
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

        Memoised. The scan underneath is a pure function of (p, hi) over `self.data`,
        which is the mapped file and never mutated -- so caching is behaviour-identical,
        not an approximation. It is worth doing because this is not called once per
        program but once per FX-Map node evaluation: a single 3029-record assembly
        renders with 118,539 calls to it, re-decoding the same few hundred byte ranges
        and spending 16.2M `struct.unpack_from` calls to reach answers it already had.

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
        try:
            cache = self._span_cache
        except AttributeError:
            cache = self._span_cache = {}
        key = (p, hi)
        if key in cache:
            return cache[key]
        cache[key] = v = self._program_span_scan(p, hi)
        return v

    def program_result(self, p):
        """(type, components) of the program at `p`, from its LAST instruction, or None.

        Memoised the same way and for the same reason as `program_span`. This is what
        separates an output-size expression from a filter parameter that happens to sit in
        the same slot: a size is a two-component INTEGER, and `audit_corpus.py` has
        measured that at 90-99.5% for every filter but `pixelprocessor` and `fxmaps`.
        """
        try:
            cache = self._result_cache
        except AttributeError:
            cache = self._result_cache = {}
        if p in cache:
            return cache[p]
        last = None
        for _k, _q, op, _t in disasm.decode(self.data, p, self.body_hi):
            last = op
        if last is None:
            cache[p] = None
            return None
        _ntok, ty, ncomp, _oid = disasm.fields(last)
        cache[p] = v = (ty, ncomp)
        return v

    def _program_span_scan(self, p, hi):
        """Uncached scan. See `program_span`, which is the entry point."""
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
        hit = self._pe_cache.get(p)
        if hit is not None:
            return hit
        r = self._program_end(p)
        self._pe_cache[p] = r
        return r

    def _program_end(self, p):
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
