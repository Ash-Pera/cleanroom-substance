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
EDGES = {0: [1, 2], 1: [2, 3], 2: [2], 3: [2, 3], 7: [1, 2], 8: [2, 3], 10: [1],
         11: [2], 12: [2, 3], 13: [1], 14: [1], 15: [2], 18: [2], 19: [1],
         21: [2], 22: [1]}

# Filters whose input list is not fully resolved. Listing them beats guessing.
PARTIAL_EDGES = {3: 'shuffle takes up to 4 inputs; only slot 3 resolves reliably',
                 4: 'fxmaps inputs resolve only in the bit-12 layout (8.3% of its records)',
                 21: 'distance slot 3 is a shared control input, not a tree edge',
                 16: 'bitmap has no image input'}

# Shared references: slots pointing at one record used by many (refs/target >> 1).
SHARED = {8: [1], 11: [1], 19: [2], 22: [2]}

# The slot holding the pointer to the record's parameter program.
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
    def edge_slots(self):
        return self.layout[0]

    @property
    def edges(self):
        """Input record indices. 0 means 'no input'. None entries are unresolved."""
        out = []
        for sl in self.edge_slots:
            if sl >= len(self.words):
                out.append(None); continue
            v = self.words[sl]
            out.append(v if (v == 0 or (v < self.index and v < len(self.asm.records)))
                       else None)
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
        """The record's main parameter slot, which is a tagged union.

        Either a pointer to a parameter program, or the parameter baked in as a
        float32. The two readings are disjoint: over 309,878 records not one value
        satisfies both, so the discrimination is exact rather than heuristic.

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
        return None

    @property
    def programs(self):
        """Offsets of parameter programs, located strictly via the known slot."""
        sl = self.layout[1]
        if sl is None or sl >= len(self.words):
            return []
        p = self.words[sl] + 52
        if not (self.asm.body_lo <= p < self.asm.body_hi):
            return []
        return [p] if self.asm.valid_program(p) else []

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
        self.body_hi = self.header['table_start']
        offs = sorted(e + 52 for e in ents)
        self.records = []
        for i, o in enumerate(offs):
            nxt = offs[i + 1] if i + 1 < len(offs) else self.body_hi
            if o + 4 > len(d):
                continue
            self.records.append(Record(self, i, o, min(nxt, len(d))))
        self.resource_end = min(offs) if self.layout == 'A' and offs else None

    # ---- programs
    def valid_program(self, p):
        """A program is valid only if its declared instruction count decodes exactly."""
        d, hi = self.data, self.body_hi
        if p + 4 > hi:
            return False
        n = struct.unpack_from('<H', d, p)[0]
        if not (1 <= n <= 20000):
            return False
        q, k = p + 2, 0
        while k < n and q + 2 <= hi:
            op = struct.unpack_from('<H', d, q)[0]
            L = isa.LEN.get(op)
            if not L or ((op >> 8) & 3) == 3:
                return False
            q += 2 * L
            k += 1
        return k == n

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
    def coverage(self):
        """Classify every byte. Anything unexplained is reported, not hidden."""
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
        nprog = 0
        for r in self.records:
            mark(r.offset, r.end, 5)                       # record
            for p in r.programs:
                mark(p, self.program_end(p), 6)
                nprog += 1
        # Layout B emits a prologue before the first record holding programs and
        # FX-Map trees. Only ~21% of it is reachable from a record slot; the rest is
        # a known gap, named here rather than left in 'unexplained'.
        prologue = 0
        if self.layout == 'B' and self.records:
            first = min(r.offset for r in self.records)
            prologue = max(0, first - self.body_lo)
            mark(self.body_lo, first, 7)
        # bytearray.count is C-speed; counting byte-by-byte in Python made this
        # function 97% of the corpus audit's runtime.
        counts = {v: seen.count(v) for v in range(8)}
        return {'total': n, 'unexplained': counts.get(0, 0),
                'header': counts.get(1, 0), 'directory': counts.get(2, 0),
                'value_table': counts.get(3, 0), 'resources': counts.get(4, 0),
                'records': counts.get(5, 0) + counts.get(6, 0),
                'layout_b_prologue': counts.get(7, 0),
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
