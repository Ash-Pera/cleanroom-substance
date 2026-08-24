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
    14: 'hsl', 15: 'levels', 16: 'bitmap', 17: 'text', 18: 'normal',
    20: 'pixelprocessor', 21: 'distance',
}
# Unnamed ids, with what is known. Never rendered as a name.
UNNAMED = {5: 'generator, greyscale (svg?)', 8: 'two inputs, greyscale control (emboss?)',
           9: 'legacy, version 0x20000 only', 11: 'one input, channel-preserving',
           19: 'one input from blend + shared pixelprocessor map', 22: 'one input'}

# Data edges: slots whose targets are used once each (refs/target ~= 1).
# Derived by measuring, per filter, the rate at which a slot holds a valid backward
# record index - EXCLUDING slot 1 wherever slot 1 is a parameter word, because a small
# packed integer passes the "valid backward index" test trivially. That conflation is
# what produced the shared-reference error; see FORMAT-NOTES.md.
EDGES = {0: [1], 1: [2, 3], 2: [2], 3: [2, 3], 7: [1, 2], 8: [2, 3], 10: [1],
         11: [2], 12: [2, 3], 13: [1], 14: [1], 15: [2], 18: [2], 19: [1],
         21: [2], 22: [1]}

# Filters whose input list is not fully resolved. Listing them beats guessing.
PARTIAL_EDGES = {3: 'shuffle takes up to 4 inputs; only slot 3 resolves reliably',
                 4: 'fxmaps inputs resolve only in the bit-12 layout (8.3% of its records)',
                 21: 'distance slot 3 is a shared control input, not a tree edge',
                 16: 'bitmap has no image input'}

# Shared references: slots pointing at one record used by many (refs/target >> 1).
SHARED = {8: [1], 11: [1], 19: [2], 22: [2]}

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
PARAM_WORD = {1, 2, 4, 11, 12, 15, 18, 20, 21, 22}

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
    except Exception:
        return {}, {}
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
    0x89:  (12, (4,)),        # [header][program][0][next]       conditional, -> b2
    0x1AB: (12, (4, 8)),      # [header][program][program][next]              -> i1
    0x1CB: (12, (4,)),        # [header][program][0][next]                    -> i1
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
    # Filter 11 is one of the filters this work will not name - doing so needs sources
    # excluded on provenance - so its two parameters carry positional names. The bit pairs
    # were derived mechanically, not fitted: 32,204 of 32,204 slot kinds correct.
    #
    # Their value distributions are suggestive and are NOT claims:
    #   param0  one-sided, p50 1.45, p99 36.3, max 500, values in multiples of 0.66
    #   param1  symmetric, 28.0% negative, p1 -0.125, values in multiples of 1/16
    # param1 has the signature of an angle in turns, but unlike `directionalwarp` none of
    # its 25 programs divides by 2*pi, so nothing confirms it. A value distribution alone
    # already produced one withdrawn reading in this file; it does not get to produce
    # another.
    11: [('fid11_param0', 0x003, 0x002), ('fid11_param1', 0x00c, 0x008)],
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


class Record:
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
        self._layout = r = self._compute_layout()
        return r

    def _compute_layout(self):
        f = self.filter_id
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
            # fxmaps has two record layouts, selected by bit 12 of the parameter word.
            # With it set, slots 3-8 are input edges (100% valid or zero, 94-99.8%
            # resolution agreement) and the program sits at slot 9. With it clear, no
            # slot resolves as an edge and the program is at slot 3.
            if len(self.words) > 1 and (self.words[1] >> 12) & 1:
                return ([3, 4, 5, 6, 7, 8], 9)
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
        par = self.parameter
        if not par or par[0] != 'program':
            return None
        decl = {u: v for t, u, v in (self.asm.header.get('inputs') or [])}
        vals = []
        for k, addr, op, toks in disasm.decode(self.asm.data, par[1], self.end):
            f = disasm.fields(op)
            oid, n = f['id'], f['comps']
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
        return HEADER_WORDS.get((self.filter_id, self.cls,
                                 self.words[1] & LAYOUT_MASK.get(self.filter_id, 0)))

    @property
    def edge_slots(self):
        """Slots holding this record's input edges.

        `pixelprocessor` states its own arity instead of relying on the layout table:
        slot 1 is the input count and the inputs occupy slots 2 onward. Over the corpus,
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
    def params(self):
        """The slot-1 parameter word, decoded as far as it is understood."""
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
    def parameter(self):
        """The first slot after the record's inputs. It is one of two different things.

        **Not "the main parameter"**, which is what these notes called it for a long time.
        In 91.3% of records it holds the record's OUTPUT SIZE expression - see
        `output_size` - and in the rest a baked float that is a genuine filter parameter.
        The two are not variants of one idea; they are different fields.

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
    def parameters(self):
        """Named parameters this record carries, as [(name, kind, value), ...].

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
        par = self.parameter
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
        while q + 8 <= e and limit > 0:
            limit -= 1
            tag = struct.unpack_from('<I', d, q)[0]
            if tag in FX_NODES:
                break
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
            off = FX_TABLE.get(tag)
            prog = None
            if off is not None and o <= t < e - 3 and t + off + 4 <= e \
                    and self.asm.program_span(t + off, e):
                prog = t + off
            yield q, tag, prog
            q += 8

    def fx_tree(self):
        """For filter 4: yield (offset, header, program offset or None) per tree node.

        Nodes whose header is not in FX_NODES stop the walk - the vocabulary is open,
        and guessing a node's size to continue past one is how earlier walks wandered
        into bytecode and produced phantom node types.
        """
        if self.filter_id != 4 or len(self.words) < 3:
            return
        d, o, e = self.asm.data, self.offset, self.end
        q, seen = self.words[2] + 52, set()
        while o <= q < e - 7 and q not in seen:
            seen.add(q)
            h = struct.unpack_from('<I', d, q)[0]
            shape = FX_NODES.get(h)
            if shape is None:
                return
            nxt_off, prog_slots = shape
            for sl in prog_slots:
                if q + sl + 4 > e:
                    return
                p = struct.unpack_from('<I', d, q + sl)[0] + 52
                yield q, h, (p if (o < p < e and self.asm.program_span(p, e)) else None)
            if q + nxt_off + 4 > e:
                return
            q = struct.unpack_from('<I', d, q + nxt_off)[0] + 52

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
        p = self.params
        if p and 'blendingmode' in p:
            s += '  mode=%d' % p['blendingmode']
        if self.programs:
            s += '  prog@%d' % self.programs[0]
        p2 = self.parameter
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
    def outputs(self):
        """The graph outputs, as [(uid, format, grayscale, record index), ...].

        Layout A puts an 8-byte entry per output between the record directory and the
        first record - the region coverage() was calling 'resources', though many files
        with one embed no images at all. One entry per output in 591 of 591 layout-A
        specimens, and the second word is a valid record index in 3,249 of 3,249.

        The first word carries the manifest's `format` attribute as bits 4 and up:
        format == (w0 & 0xFFFF) >> 4, exact on every distinct value in the corpus. Bit 2
        of that format is the grayscale flag, and it matches the colour bit of the record
        the entry names in 3,249 of 3,249 - a consequence test the table could have
        failed and did not.

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
    def valid_program(self, p):
        """True if a program starts at p. See `program_span` for what that requires.

        Three checks, each of which a run of arbitrary bytes fails: the declared
        instruction count decodes to exactly that many instructions; every opcode is
        well-formed and its id is one the format actually uses (the raw length rule
        accepts 47% of all u16 values); and every operand that is a value reference names
        an EARLIER value, since this is three-address code with contiguously numbered
        results.

        The last check is the one with teeth -- violated by 0.00% of instructions in
        programs a record's slots name, and by 65% in scan-discovered candidates.
        """
        return self.program_span(p) is not None

    # ---- outputs
    def outputs(self):
        """The graph outputs, as [(uid, format, grayscale, record index), ...].

        Layout A puts an 8-byte entry per output between the record directory and the
        first record - the region coverage() was calling 'resources', though many files
        with one embed no images at all. One entry per output in 591 of 591 layout-A
        specimens, and the second word is a valid record index in 3,249 of 3,249.

        The first word carries the manifest's `format` attribute as bits 4 and up:
        format == (w0 & 0xFFFF) >> 4, exact on every distinct value in the corpus. Bit 2
        of that format is the grayscale flag, and it matches the colour bit of the record
        the entry names in 3,249 of 3,249 - a consequence test the table could have
        failed and did not.

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
    def valid_program(self, p):
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
                    if struct.unpack_from('<H', d, q + 2 + 2 * i)[0] >= k:
                        return False
            q += 2 * L
            k += 1
        return k == n

    def program_span(self, p, hi=None):
        """End offset of the program at p, or None. Bounded by `hi` when given.

        This is the single definition of "is a program"; `valid_program` is this
        returning non-None. They used to be two implementations of the same idea and
        drifted apart -- this one checked only instruction lengths, so a tightening
        applied to the other silently did not reach the scan that finds most programs.
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
                    if i not in pos and struct.unpack_from('<H', d, q + 2 + 2 * i)[0] >= k:
                        return None
            q += 2 * L
        return q

    def referenced_programs(self):
        """Every program some 4-aligned word in the file points at, as {start: end}.

        The layout-based `Record.parameter` finds a record's *own* parameter program and
        is the strict reading. It is not the whole story: FX-Map records reach programs
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
