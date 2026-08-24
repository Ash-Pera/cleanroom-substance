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
PARAM_BITS = {
    15: {0: 'levelinlow', 2: 'levelinhigh', 4: 'levelinmid',
         6: 'leveloutlow', 8: 'levelouthigh'},
    1: {4: 'opacitymult'},
}
PARAM_BIT_MASK = {15: 0x155, 1: 0x10}


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
                return (list(edges), progs[0] if progs else None)
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
        return None

    @property
    def parameters(self):
        """Named parameters this record carries, as [(name, value), ...].

        Only for filters in PARAM_BITS; [] otherwise, and [] is not a claim that the
        record has no parameters. The block starts after the header: slot 3 when the
        class word's bit 0 is clear, slot 4 when it is set - that bit is what says
        whether slot 3 holds the parameter program or the first parameter.
        """
        f = self.filter_id
        bits = PARAM_BITS.get(f)
        if not bits or len(self.words) < 3:
            return []
        # Slot positions come from the layout table, not from a per-filter formula.
        # The table's first parameter entry is the program slot; the baked constants
        # follow it, and that is where the block sits. Falling back to a formula would
        # be a guess exactly where the table already knows the answer.
        hit = LAYOUTS.get((f, self.cls, self.words[1] & LAYOUT_MASK.get(f, 0)))
        if not hit or len(hit[1]) < 2:
            return []
        slots = list(hit[1])[1:]
        w = self.words[1] & PARAM_BIT_MASK[f]
        out = []
        for j, b in enumerate(i for i in range(16) if w >> i & 1):
            if j >= len(slots) or slots[j] >= len(self.words):
                break                      # more bits than slots: report the readable
            v = self.words[slots[j]]
            out.append((bits[b], struct.unpack('<f', struct.pack('<I', v))[0]))
        return out

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
        return out

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

        Yields ('node', offset, header, program) then ('entry', offset, tag, program).

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
            q = self.offset + last
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
            yield q - o, tag, prog
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
                yield q - o, h, (p if (o < p < e and self.asm.program_span(p, e)) else None)
            if q + nxt_off + 4 > e:
                return
            q = struct.unpack_from('<I', d, q + nxt_off)[0] + 52

    @property
    def matrix(self):
        """For filter 2: the `matrix22` transform, as four float32, or None.

        Slots 4 to 7 hold the 2x2 matrix. Source matrices appear verbatim here in 66 of
        72 cases across 23 permitted files, the misses being nodes the cooker eliminated.
        The values read as transforms should - `2 0 0 2`, `-1 0 0 -1`, `1.4014 0 0 1.4014`
        - and the off-diagonals are zero in 94% and 76% of records, since most transforms
        scale or flip without shear.
        """
        if self.filter_id != 2 or len(self.words) < 8:
            return None
        m = struct.unpack_from('<4f', self.asm.data, self.offset + 16)
        if not all(-1e4 < x < 1e4 and x == x for x in m):
            return None
        # A transform cannot be singular: a zero determinant collapses the image to a
        # line. Records whose slots 4-7 are not the matrix land here and are rejected.
        if abs(m[0] * m[3] - m[1] * m[2]) < 1e-9:
            return None
        return m

    @property
    def ramp(self):
        """For filter 0: the gradient's colour ramp, or None.

        A gradient record embeds its ramp as a table of u16 entries:

            slot 2   number of stops
            slot 3   table start
            slot 4   table end, which is also where the record's program begins

        The entry width follows the channel count - `4 + 2*colour + 2*(class bit 8)` -
        giving 4, 6 or 8 bytes: a stop position followed by one, two or three values.
        The formula holds for 94.4% of the 17,151 records carrying a ramp pointer.

        Slot 2 is *not* an input edge. It reads as one - a small backward value - but
        its resolution agreement with the record is 35.5%, which is chance, where a real
        edge agrees at ~100%.
        """
        if self.filter_id != 0 or len(self.words) < 5:
            return None
        count = self.words[2]
        start = self.words[3] + 52
        end = self.words[4] + 52
        if not count or not (self.offset < start < self.end):
            return None
        if not (self.offset < end <= self.end):
            end = self.end
        width = 4 + 2 * (1 if self.colour else 0) + 2 * ((self.cls >> 8) & 1)
        if (end - start) != count * width:
            return None                     # the 5.6% the formula does not cover
        n = width // 2
        return [struct.unpack_from('<%dH' % n, self.asm.data, start + i * width)
                for i in range(count)]

    # ---- bitmap specialisation
    @property
    def bitmap(self):
        """For filter 16: either stored pixels or a named graph input."""
        if self.filter_id != 16:
            return None
        if self.end - self.offset == 8:
            hi = (self.cls >> 8) & 0xFF
            ch = CHANNELS.get(hi & 3)
            if ch is None:
                return None
            bpc = 2 if hi & 4 else 1
            size = self.width * self.height * ch * bpc
            return {'kind': 'pixels', 'offset': self.words[1], 'size': size,
                    'channels': ch, 'depth': bpc * 8}
        if len(self.words) > 1:
            return {'kind': 'graph_input', 'uid': self.words[1]}
        return None

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
