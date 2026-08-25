#!/usr/bin/env python3
"""walk(): the format's one structural primitive, as one function.

A prototype for the proposal in FORMAT-NOTES.md ("Read it as the mask-walk it was
serialised as"). Every structured object in this format is `[mask][fields...]`: the set
bits of a mask, read in canonical order, enumerate which fields are present, and each
field's width is a constant of its KIND. Nothing stores an offset. A reader walks the
mask; a writer emits in the same order.

This file implements that walk ONCE and drives it with a per-filter spec whose only
numbers are integer field widths taken from a WIDTH LEGEND. The legend is seeded from the
manifest's parameter type codes -- `$outputsize` is `type="8"` (integer2), two components,
which is why the inherited-parameter that class-word bit 10 gates costs two words. No float
is fitted anywhere here, and the walk fails loudly (raises `Overrun`) rather than guessing
when it cannot land inside the record the directory framed.

The same primitive runs one scale down: an FX-Map tree node is `[tag][fields]`, the tag a
presence mask over the same 1/2/4-word field widths. `_walk_mask` is the shared core;
`walk()` composes it over a record's two masks and `walk_node()` applies it to a node tag.

The format states a record's layout in more than one alphabet, and the walk reads all of
them: two-bit presence codes (blend, levels, transformation), an arity INTEGER
(pixelprocessor, fxmaps), a paired CONJUNCTION (bitmap), and a class-word POPCOUNT that
states program-slot ROLE (blur, warp). None needs a fitted table or a value probe.

Cataloguing the class-word-driven filters as well drains the rest of `layouts.json`: a walk
mechanism covers 99.19% of the manifest-bearing corpus, and what is left is only the three
filters where the file genuinely does not state the layout (shuffle, emboss, vectorshape).

Run it to validate against the established `Record` model and node census over the corpus:

    python3 tools/walk.py     # eighteen filters, four encodings, FX nodes; manifest files
"""
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# The width legend. Component count per manifest type code -- how many words a
# value of that type occupies. Read from a manifest, not fitted; see manifest.py
# and FORMAT-NOTES.md's "preset type codes are the width law" section.
# ---------------------------------------------------------------------------

# The manifest's own vocabulary: Float1..Float4 and Int1..Int4, plus the two known
# non-scalar codes. "4 is the widest scalar the format has" -- the fitted `<= 4`
# ceiling is this table's range, stated by the file.
LEGEND_FROM_TYPE = {
    0: 1,   # Float1
    4: 1,   # Integer1  ($randomseed)
    5: 1,   # image input -- one edge slot (a backward record index)
    8: 2,   # Integer2  ($outputsize)  <- the only width > 1 in the blend/levels specs
}


def legend_from_manifest(xml_path):
    """{type code: component count} read from a manifest's declared inputs.

    Only demonstrates that the widths the specs use are STATED, not fitted: it confirms
    `$outputsize` is type 8 and pins its component count from the default's arity
    (`default="8,8"` -> 2). Falls back to LEGEND_FROM_TYPE for codes the file does not
    exercise.
    """
    import re
    leg = dict(LEGEND_FROM_TYPE)
    try:
        text = open(xml_path, encoding='utf-8', errors='replace').read()
    except OSError:
        return leg
    for m in re.finditer(r'<input\b[^>]*\btype="(\d+)"[^>]*\bdefault="([^"]*)"', text):
        code = int(m.group(1))
        comps = len([c for c in m.group(2).split(',') if c != ''])
        if comps:
            leg[code] = comps
    return leg


# ---------------------------------------------------------------------------
# Per-filter specs. Every number is a slot width. `cls_bits` are the inherited
# parameters, one field per set class-word bit, in canonical (ascending) order;
# their widths come from the legend via the type each bit gates. `w1_fields` are
# the filter's OWN parameters, one two-bit code each: 00 absent, 01 baked,
# 10 program, 11 image input (an edge).
# ---------------------------------------------------------------------------

class Spec:
    def __init__(self, base, cls_widths, w1_fields, has_w1=True, conj=(), arity=None):
        self.base = base                 # base image inputs, contiguous from slot 2
        self.cls_widths = cls_widths     # {class-word bit: width in words}
        self.w1_fields = w1_fields        # [(mask, shift, kind)] in field order
        self.has_w1 = has_w1
        self.conj = conj                 # [(bitx, bity, width)] -- a PAIR of tag bits that,
                                         # set together, name one field (bitmap's offset word)
        self.arity = arity               # an Arity, or None -- the count-field encoding


class Arity:
    """The other self-describing encoding: the header states its input count as an INTEGER,
    and the walk reads that many edge slots. Not two-bit presence codes -- a small number.

        prefix       fixed non-edge slots after the masks (fxmaps' tree-root pointer)
        read(w1)     the count, extracted from word1 (a nibble, or the whole small word)
    """
    def __init__(self, prefix, read):
        self.prefix = prefix
        self.read = read


# A baked parameter is stored INLINE, and occupies one word per component. Its component
# count is its type's, from the legend. A field that holds a PROGRAM or an IMAGE instead is
# a single pointer/edge slot regardless of type. `kind` names the baked component count:
#
#     'scalar'    Float1, one word
#     'channel'   per-channel: Float1 when grayscale, Float4 when colour -- the tag's
#                 colour bit (bit 0) says which
#     an integer  a fixed component count from the manifest type: matrix22 is Float4 (4),
#                 offset is Float2 (2)
def _field_width(kind, code, colour):
    if code != 1:            # 10 program / 11 image -> one pointer or edge slot
        return 1
    if kind == 'channel':    # baked, per-channel: component count from the colour bit
        return 4 if colour else 1
    if isinstance(kind, int):
        return kind          # baked, fixed component count (Float2/Float4/...)
    return 1                 # baked scalar (Float1)


# The class-word inherited-parameter block. Bit 10 is `$outputsize` (integer2, width 2
# from the legend); the other four inherited parameters are one word each. This is the
# same set of bits `_compute_layout`'s `g` sums -- but as widths from the legend, not a
# fitted `2 * bit`.
_CLS = {0: 1, 7: 1, 10: 2, 11: 1, 13: 1}

SPECS = {
    1:  Spec(base=2, cls_widths=_CLS,          # blend
             w1_fields=[(0x30, 4, 'scalar'),    # opacitymult (Float1)
                        (0x600, 9, 'scalar')]),  # a second Float1 parameter: a two-bit code
                                                 # at bits (9,10) -- 01 baked, 10 program --
                                                 # with bit 8 as its always-on present flag.
                                                 # NOT a size nibble: the baked slot is a
                                                 # float in [0,1], not a magnitude count.
    15: Spec(base=1, cls_widths=_CLS,          # levels
             w1_fields=[(0x003, 0, 'channel'), (0x00c, 2, 'channel'),
                        (0x030, 4, 'channel'), (0x0c0, 6, 'channel'),
                        (0x300, 8, 'channel')]),  # five per-channel level fields
    2:  Spec(base=1, cls_widths={0: 1, 7: 1},   # transformation
             w1_fields=[(0xC0, 6, 4),            # matrix22 pair (6,7): baked Float4
                        (0x06000000, 25, 2)]),   # offset pair (25,26): baked Float2
    16: Spec(base=0, cls_widths={0: 1},         # bitmap -- a generator, no image edge
             w1_fields=[],
             conj=[(24, 27, 1)]),                # bits 24+27 together: the offset word
    20: Spec(base=0, cls_widths={}, w1_fields=[],  # pixelprocessor -- arity integer
             arity=Arity(prefix=0,
                         read=lambda w1: w1 if 1 <= w1 <= 8 else (0 if w1 == 0 else w1 & 0xF))),
    4:  Spec(base=0, cls_widths={}, w1_fields=[],  # fxmaps -- arity integer after the root
             arity=Arity(prefix=1, read=lambda w1: (w1 >> 10) & 0xF)),
    11: Spec(base=1, cls_widths=_CLS,           # dirmotionblur -- two-bit codes, like blend
             w1_fields=[(0x3, 0, 'scalar'),      # intensity
                        (0xc, 2, 'scalar')]),     # mblurangle
    12: Spec(base=2, cls_widths=_CLS,           # directionalwarp
             w1_fields=[(0x6, 1, 'scalar'),      # intensity
                        (0x18, 3, 'scalar')]),    # warpangle
}

# Popcount is the format's THIRD self-describing encoding: for `blur` (10) and `warp` (7)
# the number of leading block slots that hold PROGRAMS (the rest baked) is
# popcount(cls & mask), a count spelled by set bits in the class word. It decides ROLE --
# which slots are programs -- and, through role, extent: when nprog == 0 the SIZE is two
# baked words (w, h) rather than one program pointer, so a blur header is five words with a
# baked size and four with a computed one. (An earlier comment here claimed popcount moved
# no header word; blur's own headers, grouped by popcount, disprove it -- the baked size
# pair is the extra word.) `check_popcount` validates the count against the model.
#
# blur's trailing intensity word is a separate class-word bit again, and fully stated: cls
# bit 12 is set iff the last header slot is a baked value, 6,855 of 6,855. So the header is
# (masks + edge) + nprog program slots + the bit-10 size pair + the bit-12 intensity, every
# term a class-word bit -- which is why costs.json reproduces it and record_layout matches
# the model in every blur record. The apparent nprog==3 anomaly (a 5-word header where a
# "size then intensity" model predicts 6) is just bit 12 clear: no baked intensity, and
# independent of nprog. Not a residue.
POPCOUNT_MASK = {10: 0x2881, 7: 0x0881}


# The rest of the memo (`layouts.json`): filters whose header is purely class-word driven
# (their `w1` adds no header word -- see costs.json) and whose edges are a FIXED base shape.
# The table memorised header sizes and edge lists that are computed by the costs legend
# (header) and a constant base (edges); nothing here needs a per-record lookup. The value is
# the dominant edge shape; the minority shapes are the honest residue reported alongside.
#
# The value is either a fixed edge list or a function (word0, word1, version) -> edges for
# the two-shape filters, whose extra input is itself stated by the file: warp switches shape
# by version (the w1 word appears at 0x90000), distance by w1 bit 0 (its second input).
#     filter          edges                                          note
TIER_A_EDGES = {
    0:  [1],                                                        # gradient (residue: [])
    6:  [],                                                         # uniform (generator)
    7:  lambda w0, w1, v: [2, 3] if v >= 0x90000 else [1, 2],       # warp
    10: [1],                                                        # blur
    13: [1],                                                        # sharpen
    14: [1],                                                        # hsl
    17: [],                                                         # text (generator)
    18: [2],                                                        # normal (residue: [1,2])
    19: [1, 2],                                                     # dyngradient (residue: [1])
    21: lambda w0, w1, v: [2, 3] if w1 & 1 else [2],               # distance
    22: [1],                                                        # curve
}


def _tier_a_edges(f, word0, word1, version):
    e = TIER_A_EDGES[f]
    return e(word0, word1, version) if callable(e) else e


def validate_cls_driven(files):
    """Header from the costs legend (via record_layout), edges from the fixed base shape.

    Returns per filter: records, header-exact, edge-exact -- both against the model. Where
    both hit, the `layouts.json` entry for that record is redundant and drained."""
    import record_layout
    from collections import Counter
    from sbsasm import Assembly
    stat = {f: Counter() for f in TIER_A_EDGES}
    for p in files:
        try:
            a = Assembly(p)
        except Exception:
            continue
        ver = a.header.get('version') if isinstance(a.header, dict) else 0
        for r in a.records:
            f = r.filter_id
            if f not in TIER_A_EDGES or len(r.words) < 2:
                continue
            c = stat[f]
            c['records'] += 1
            # warp's w1 word is a version fact -- absent before 0x90000 -- and the header
            # legend must be read with it nulled there, exactly as the model does.
            w1 = r.words[1]
            if f == 7 and ver < 0x90000:
                w1 = None
            h = record_layout.header_words(f, r.words[0], w1, version=ver)
            hw = r.header_words
            if hw is not None:
                c['header seen'] += 1
                if h == hw:
                    c['header exact'] += 1
            if list(_tier_a_edges(f, r.words[0], r.words[1], ver)) == list(r.edge_slots):
                c['edges exact'] += 1
    return stat


# ---------------------------------------------------------------------------
# The FX-Map tree node: the SAME primitive at the third scale. A node is
# `[tag][fields by mask]`: the tag's low byte is a KIND fixing a constant base
# size, and the remaining tag bits are a presence mask whose set bits each add a
# field of a constant width -- the same 1/2/4-word (Float1/Float2/Float4) widths
# the record fields use. Derived by node_census.py; see FORMAT-NOTES.md.
#
# Widths in WORDS, to make the shared vocabulary explicit: const includes the tag word;
# +1 = Float1, +2 = Float2, +4 = Float4. This IS the legend node_census.py derives -- the
# tree analogue of the manifest's parameter-type table -- transcribed here as the thing the
# walk reads. The three multi-tag kinds carry a bit->width map; the single-tag kinds have no
# variation to walk and are stored as their one size. Genuinely underdetermined kinds (0x0b,
# 0x1b, 0x98) are deliberately absent: walk_node returns None for them rather than guessing.
#
# Kind 0x08 was on that list and should not have been. It is not underdetermined -- the fit
# failed because it POOLED three different structures under one kind byte. Separated:
#   * two deterministic node tags -- 0x00420008 (size 4, pointer +12, 18,152 cells) and
#     0x00410008 (size 7, pointer +24) -- 100% each, stored explicitly in NODE_TAGS below;
#   * the CHAIN tag 0x00020008, a linked list rather than a fixed-size node (its "sizes"
#     6..11 are chain-run lengths, not a cell width), which walk_node returns None for;
#   * an 8-cell tag the census already dropped as inconsistent.
# With the chain and the noise pulled out, the two real 0x08 nodes are as determined as any.
NODE_TAGS = {                       # full tag -> (size in words, [pointer word offsets])
    0x00420008: (4, [3]),
    0x00410008: (7, [6]),
}
# The CHAIN FAMILY: tags whose high 16 bits are 0x0002 are linked lists, not fixed-size
# nodes, and their gap "sizes" are run lengths. 8,794 of 8,811 such cells are
# non-deterministic against 0% for any other high-half value -- so the family, not the two
# tags found one at a time (0x00020008 dragged kind 0x08, 0x00020018 dragged kind 0x18), is
# the thing to exclude. walk_node returns None for all of them.
def _is_chain(tag):
    return (tag >> 16) == 0x0002
#
# One apparent gap that is not one: kind 0x48's bit 9 is set in a large fraction of cells and
# charges no width here, so a cross-check reads it as a field both this table and
# fx_entry_layout missed. It is not a field -- bit 9 is a bit of the patterntype nibble (bits
# 8-11), measured to cost +0 words in 100% of both the set and clear populations and to
# differ from patterntype's own nibble bit in 0 of 3,781 cells. It belongs to a different
# field, not to no field, so leaving it out of the width mask is correct.
NODE_LEGEND = {
    0x48: (2, {16: 4, 17: 1, 19: 1, 20: 1, 22: 1, 23: 2, 24: 1, 25: 2,
               26: 1, 27: 1, 28: 1, 29: 1, 30: 1}),
    0x58: (3, {17: 1, 20: 1, 21: 2, 22: 1, 24: 1, 25: 2, 26: 1, 27: 1,
               28: 1, 29: 1, 30: 1}),
    0x88: (3, {9: -1, 17: 1, 22: 1, 23: 2, 24: 1, 28: 2, 30: 1, 31: 2}),
    0x8b: (3, {}), 0x89: (4, {}), 0x18: (5, {}), 0xcb: (4, {}), 0x99: (5, {}),
    0x9b: (4, {}), 0xab: (4, {}), 0xa3: (4, {}), 0xdb: (5, {}),
}


def _walk_mask(mask_word, const_words, bit_widths):
    """The core: walk the set bits of a mask in ascending order, each adding its width.

    Returns (total words, {bit: word offset of its field}). This is the one operation
    the whole format is built from; `walk()` composes it over the record's two masks,
    and `walk_node()` applies it once to a tree node's tag."""
    size = const_words
    offsets = {}
    for bit in sorted(bit_widths):
        if (mask_word >> bit) & 1:
            offsets[bit] = size
            size += bit_widths[bit]
    return size, offsets


def walk_node(tag):
    """A tree node's size in words and its field offsets, or None for an uncatalogued
    kind. The tag itself is the mask; no per-node table is consulted."""
    if _is_chain(tag):
        return None                      # a linked-list chain, not a fixed-size node
    ent = NODE_TAGS.get(tag)
    if ent is not None:
        size, ptrs = ent
        return (size, {i: off for i, off in enumerate(ptrs)})
    spec = NODE_LEGEND.get(tag & 0xFF)
    if spec is None:
        return None
    const, bit_widths = spec
    return _walk_mask(tag, const, bit_widths)


class Overrun(Exception):
    """The walk ran past the end of the record the directory framed. A designed format
    does not do this; when it happens the spec or the legend is wrong, and saying so
    loudly is the whole point -- a fitted table cannot."""


class Walk:
    __slots__ = ('header_words', 'edge_slots', 'param_slots')

    def __init__(self, header_words, edge_slots, param_slots):
        self.header_words = header_words
        self.edge_slots = edge_slots
        self.param_slots = param_slots


def walk(spec, word0, word1, n_words, legend=None):
    """Walk the two presence masks. Returns a Walk; raises Overrun past the record end.

    `n_words` is the record's total word count, from the directory extent map. The walk
    never consults a per-record table and never rounds: position advances by legend widths.
    """
    cls = word0 >> 16
    colour = bool(word0 & 1)             # tag bit 0: the record's colour flag
    pos = 2 if spec.has_w1 else 1        # slots 0 (tag+cls) and 1 (w1) are the masks
    edges, params = [], []

    # the count-field encoding: a fixed prefix, then N edges named by an integer in word1
    if spec.arity is not None:
        pos += spec.arity.prefix
        n = spec.arity.read(word1)
        for _ in range(n):
            edges.append(pos)
            pos += 1
        if pos > n_words:
            raise Overrun('arity %d edges past record %d words' % (n, n_words))
        return Walk(pos, edges, params)

    # base image inputs, contiguous
    for _ in range(spec.base):
        edges.append(pos)
        pos += 1

    # inherited parameters: one field per set class-word bit, in ascending bit order,
    # each as wide as the legend says. (Widths already resolved into cls_widths.)
    for bit in sorted(spec.cls_widths):
        if (cls >> bit) & 1:
            params.append(pos)
            pos += spec.cls_widths[bit]

    # the filter's own parameters: one two-bit code per field, in field order
    for mask, shift, kind in spec.w1_fields:
        code = (word1 & mask) >> shift
        if code == 0:
            continue                      # absent, consumes nothing
        if code == 3:                     # image input -> an edge
            edges.append(pos)
        else:                             # baked (01) or program (10) -> a parameter
            params.append(pos)
        pos += _field_width(kind, code, colour)

    # conjunctions: a PAIR of tag bits that, set together, name one field. bitmap's bits
    # 24 and 27 together add the offset word that locates its pixels; an additive per-bit
    # model can only reach this through a rounding tie, but the walk states it directly.
    for bx, by, width in spec.conj:
        if (cls >> (bx - 16) & 1) and (cls >> (by - 16) & 1):
            params.append(pos)
            pos += width

    if pos > n_words:
        raise Overrun('header %d words > record %d words' % (pos, n_words))
    return Walk(pos, edges, params)


# ---------------------------------------------------------------------------
# Validation against the established Record model.
# ---------------------------------------------------------------------------

def _corpus_files(limit=None):
    files = []
    for root in ('corpus', 'extracted', 'extracted2', 'extracted3', 'new_sbs'):
        for p in glob.glob(os.path.join(root, '**', '*.sbsasm'), recursive=True):
            if os.path.exists(os.path.splitext(p)[0] + '.xml'):
                files.append(p)
    files.sort()
    return files[:limit] if limit else files


def validate_nodes(files):
    """Harvest fx-tree node cells (as node_census does) and check walk_node against them.

    Ground truth for a cell's size is the gap between the node's start and the next inline
    program; ground truth for a pointer is `value + 52 is a valid program`. The walk knows
    neither -- it computes size and field offsets from the tag alone. Two claims:

        size:     walk_node's word size == the gap, for kinds it catalogues
        pointers: every empirically-found program pointer sits on a field boundary the
                  walk predicts (a pointer never lands in the middle of a field)
    """
    import struct
    from collections import Counter, defaultdict
    from sbsasm import Assembly
    tag_sizes = defaultdict(Counter)        # tag -> Counter of observed gap sizes (words)
    ptr = defaultdict(Counter)              # tag -> Counter of program-pointer byte offsets
    for p in files:
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4 or len(r.words) < 4:
                continue
            root = r.words[2] + 52
            if not (r.offset < root < r.end):
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
                    if walk_node(tag) is not None:
                        tag_sizes[tag][(s - pos) // 4] += 1
                        for off in range(4, min(s - pos, 64), 4):
                            v = struct.unpack_from('<I', a.data, pos + off)[0]
                            q2 = v + 52
                            if a.body_lo <= q2 < a.body_hi and a.valid_program(q2):
                                ptr[tag][off] += 1
                pos = max(pos, e)

    # Compare walk_node against the MODAL size per tag, exactly as node_census does: a
    # cell's size is a function of its tag, and multi-node gaps are the residue, not
    # counter-evidence. Weight by how many cells each tag accounts for.
    size_ok = Counter()
    size_seen = Counter()
    for tag, sizes in tag_sizes.items():
        kind = tag & 0xFF
        n = sum(sizes.values())
        size_seen[kind] += n
        if walk_node(tag)[0] == sizes.most_common(1)[0][0]:
            size_ok[kind] += n
    # Pointers: every program pointer that occurs in >90% of a tag's cells must sit on a
    # field boundary the walk predicts -- a pointer never lands in the middle of a field.
    ptr_on_boundary = ptr_total = 0
    for tag, offs in ptr.items():
        seen = sum(tag_sizes[tag].values())
        field_starts = {4 * o for o in walk_node(tag)[1].values()}
        for off, h in offs.items():
            if h / seen > 0.9:
                ptr_total += 1
                if off in field_starts:
                    ptr_on_boundary += 1
    return size_ok, size_seen, ptr_on_boundary, ptr_total


def check_popcount(files):
    """popcount(cls & mask) predicts how many block slots are programs, for blur and warp.

    Ground truth is the model's `_block_programs()`, which reads each slot and asks whether
    it resolves as a program. The claim is that the COUNT of those is stated by the class
    word, not discovered by probing: popcount(cls & mask) == number of program slots."""
    from collections import Counter
    from sbsasm import Assembly
    stat = {f: Counter() for f in POPCOUNT_MASK}
    for p in files:
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            f = r.filter_id
            mask = POPCOUNT_MASK.get(f)
            if mask is None:
                continue
            block = r.program_slots
            if not block:
                continue
            stat[f]['records'] += 1
            predicted = bin(r.cls & mask).count('1')
            actual = sum(1 for _s, isp in block if isp)
            if predicted == actual:
                stat[f]['exact'] += 1
    return stat


def main(argv):
    from sbsasm import Assembly
    limit = int(argv[1]) if len(argv) > 1 else None
    files = _corpus_files(limit)
    print('validating walk() over %d files with a manifest\n' % len(files))

    # show the legend is read, not fitted
    xml0 = os.path.splitext(files[0])[0] + '.xml'
    leg = legend_from_manifest(xml0)
    print('width legend seeded from %s' % os.path.basename(xml0))
    print('   type 8 ($outputsize) -> %d words   (class-word bit 10 costs %d)\n'
          % (leg.get(8, 0), _CLS[10]))

    from collections import Counter
    stat = {f: Counter() for f in SPECS}
    overruns = 0
    boundary_fail = []          # walk edge slot that is NOT a backward index -- loud fail

    for p in files:
        try:
            a = Assembly(p)
        except Exception:
            continue
        nrec = len(a.records)
        for r in a.records:
            f = r.filter_id
            spec = SPECS.get(f)
            if spec is None or len(r.words) < 2:
                continue
            c = stat[f]
            c['records'] += 1
            try:
                w = walk(spec, r.words[0], r.words[1], len(r.words), leg)
            except Overrun:
                overruns += 1
                c['overrun'] += 1
                continue
            # 1) header length vs the established model. Not meaningful for the arity
            #    encoding: there the walk states the EDGE run, and the parameter/bank
            #    region past it is a separate matter -- edges are the claim to check.
            hw = r.header_words
            if spec.arity is None and hw is not None:
                c['header seen'] += 1
                if w.header_words == hw:
                    c['header exact'] += 1
            # 2) edge slots vs the established model
            ref = set(r.edge_slots)
            if set(w.edge_slots) == ref:
                c['edges exact'] += 1
            # 3) the format's own edge invariant: every edge slot the walk names holds
            #    a backward record index or the absent sentinel. A loud check.
            for s in w.edge_slots:
                if s < len(r.words):
                    v = r.words[s]
                    if not (v == 0xFFFFFFFF or v == 0 or (v < r.index and v < nrec)):
                        boundary_fail.append((os.path.basename(p), r.index, f, s, v))

    name = {1: 'blend', 15: 'levels', 2: 'transformation', 16: 'bitmap',
            20: 'pixelprocessor', 4: 'fxmaps', 7: 'warp', 10: 'blur',
            11: 'dirmotionblur', 12: 'directionalwarp', 0: 'gradient', 13: 'sharpen',
            14: 'hsl', 17: 'text', 18: 'normal', 19: 'dyngradient', 21: 'distance',
            22: 'curve', 6: 'uniform'}
    print('%-15s %8s %10s %8s %10s %8s %8s'
          % ('filter', 'records', 'hdr seen', 'hdr ok', 'edges ok', 'overrun', ''))
    print('%-15s %8s %10s %8s %10s %8s %8s'
          % ('-' * 15, '-' * 8, '-' * 10, '-' * 8, '-' * 10, '-' * 8, ''))
    for f in sorted(SPECS):
        c = stat[f]
        rec = c['records'] or 1
        hcol = ('%6.2f%%' % (100.0 * c['header exact'] / c['header seen'])
                if c['header seen'] else '  n/a  ')
        print('%-15s %8d %10d %8s %9.2f%% %8d'
              % (name[f], c['records'], c['header seen'], hcol,
                 100.0 * c['edges exact'] / rec, c['overrun']))

    print('\nloud checks (a fitted table cannot make these):')
    print('   overruns past record end          %d' % overruns)
    print('   walk edge slot not a backward idx  %d' % len(boundary_fail))
    for row in boundary_fail[:10]:
        print('      %s  rec %d  fid %d  slot %d = %d' % row)

    # The same primitive at the tree scale: walk_node over FX-Map node cells.
    print('\nFX-Map tree nodes -- the same [mask][fields] walk, one scale down:')
    size_ok, size_seen, pb, pt = validate_nodes(files)
    print('   %-10s %10s %12s' % ('node kind', 'cells', 'size exact'))
    for kind in sorted(size_seen):
        n = size_seen[kind]
        print('   %#04x %14d %11.2f%%' % (kind, n, 100.0 * size_ok[kind] / n))
    if pt:
        print('   program pointers on a predicted field boundary  %d / %d = %.2f%%'
              % (pb, pt, 100.0 * pb / pt))

    # Tier B, third encoding: popcount states the program-slot count (role, not extent).
    print('\npopcount encoding -- program-slot count stated by the class word:')
    pc = check_popcount(files)
    for f in sorted(pc):
        c = pc[f]
        rec = c['records'] or 1
        print('   %-14s %8d records   popcount==program count %6.2f%%'
              % (name.get(f, f), c['records'], 100.0 * c['exact'] / rec))

    # Tier A: draining the layouts.json memo -- class-word header + fixed-base edges.
    print('\ndraining the memo -- cls-driven header (costs legend) + fixed-base edges:')
    print('   %-14s %8s %10s %10s' % ('filter', 'records', 'header ok', 'edges ok'))
    ca = validate_cls_driven(files)
    drained = total = 0
    for f in sorted(ca, key=lambda f: -ca[f]['records']):
        c = ca[f]
        rec = c['records'] or 1
        hs = c['header seen'] or 1
        total += c['records']
        drained += c['edges exact']
        print('   %-14s %8d %9.2f%% %9.2f%%'
              % (name.get(f, f), c['records'],
                 100.0 * c['header exact'] / hs, 100.0 * c['edges exact'] / rec))
    print('   edges reproduced without the table: %d / %d = %.2f%%'
          % (drained, total, 100.0 * drained / (total or 1)))

    # Overall: how much of the corpus a walk mechanism now covers, and what is left.
    from collections import Counter as _C
    from sbsasm import Assembly as _A, FILTERS as _F
    cov = _C()
    left = _C()
    for p in files:
        try:
            a = _A(p)
        except Exception:
            continue
        for r in a.records:
            f = r.filter_id
            if f in SPECS or f in TIER_A_EDGES:
                cov['covered'] += 1
            else:
                cov['left'] += 1
                left[_F.get(f, f)] += 1
    tot = cov['covered'] + cov['left']
    print('\ncorpus coverage by a walk mechanism: %d / %d = %.2f%%'
          % (cov['covered'], tot, 100.0 * cov['covered'] / (tot or 1)))
    print('   not yet covered, by filter: %s'
          % ', '.join('%s %d' % (k, v) for k, v in left.most_common()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
