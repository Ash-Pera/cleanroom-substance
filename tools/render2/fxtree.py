#!/usr/bin/env python3
"""FX-Map quadrant subdivision: the entry tree read by its own pointers, drawn as grids.

THE RUN OF ENTRY CELLS IS A NESTING, NOT A LIST. Every entry cell is a Quadrant -- a
`paramset` in the source -- which draws its own pattern in its region and hands each of
its four outputs a quarter of that region. `fxrender.entries` reads the chain-family cells
(`0x0002xxxx`) as structural links and `fx._walk` emits each table entry once at full
canvas, so a record whose leaf sits under five bare cells draws ONE pattern where the
file states 4^4. See FORMAT-NOTES.md, "The level fault upstream of 10055 is a white-noise
FX-Map emitting ONE pattern, and the cons chain is quadrant subdivision", and the two
entries after it, for the source that corroborates the reading
(`SubstanceDesigner__Clouds_3_Animated`: six `paramset` nodes whose `output0..3` all name
the same child), the pointer census that says it without the source, and the arbitration
of the draw model by seed-free instruments. This module is the probe
`archive/tools/fx_subdiv_probe.py` ported into the renderer behind
`assume.QUESTIONS['fx.subdivide']`, with its per-pattern draw loop replaced by one that
draws a subdivided cell as a grid.

WHAT IS ESTABLISHED, and implemented here without an arm:

  * The cell layout and its pointers -- `cells_of` states it and cites the measurement.
  * THE ROOT DOES NOT SUBDIVIDE: the first cell's region is the canvas and so is its
    children's; a cell at depth d >= 1 has region size 2^-(d-1). Two independent
    instruments: 879 of 1,146 sizeless leaves sit at depth log2(record size) + 1, and
    Bricks record 9924 -- `rand(1.0)` opacity under five Quadrants on a 16-px canvas --
    reads mean 0.513 / sd 0.292 / lag-1 -0.012 under this convention (uniform white noise
    is 0.500 / 0.289 / 0) against 0.80 / 0.16 under "the root subdivides". `ROOT=0` in
    the probe.
  * `patternsize` and `frameoffset` are in REGION units; a sizeless, non-marker cell
    fills its region.
  * Each cell's programs are evaluated once PER REGION with a fresh `rand` draw. The draw
    is salted through `sbsruntime.CONTEXT['salt']`, a per-region column the runner here
    sets and clears; `$number` stays the emission index, because placement programs
    read it.

WHAT IS OPEN, and has an arm:

  * `fx.tree.branchoffset` -- `branchoffset` offsets the cell's own pattern AND its
    children. Its unit is not settled. The author of Bricks record 9804 halves it by hand
    per level (`cartesian(rand(r), rand(2*pi))`, r = 0.25, 0.125, ...), which argues for
    CANVAS units; graph 003 cannot tell the two apart (every instrument moves less than
    the renderer's own seed floor). Default `canvas`.
  * `fx.tree.order` -- which output is which quadrant. Default `rowmajor`
    (output0 top-left, output1 top-right, output2 bottom-left, output3 bottom-right);
    `clockwise` and `colmajor` are the other two readings. 003 cannot tell these apart
    either, AND NEITHER CAN ANY SCORED PACK -- the arm is only observable on a cell whose
    four output pointers resolve to more than one distinct child, and a census over 437
    files finds 244 of 23,462 subdividing records (1.04%) with such a cell and NONE in a
    scored pack. RoofTiles was the obvious nomination and is refuted: 0 of its 160
    subdividing records. The one specimen file that has them ships no reference maps.
    Measured under `quadrant`, `clockwise`/`colmajor` move max |dcorr| 0.0024-0.0060,
    against `CORR_MARGIN` 0.02. This needs a specimen pack with an export, not a better
    instrument. See FORMAT-NOTES.md, "`fx.subdivide` re-measured whole".
  * `$pos` per region is NOT modelled: `fxrender.make_runner` sets it from `fx.pos`
    once per record, as it did before, and a subdivided tree does not thread a
    per-region position through it. Left as it is.

HOW IT SCALES. Deep leaves are 4^8 and 4^9 regions per emission (Bricks record 430:
87,382 cells under the root convention above), so a Python loop per pattern is the wrong
shape for this. Each cell's programs are evaluated ONCE over all of its regions and all
of the chain's emissions as one (m, 1) `$number` column beside an (m, 1) salt column --
the runner already accepts a column, see `fx._batch_emit` -- and a program that does not
call `rand` is evaluated once per emission and broadcast over the regions. The result is
a `Batch`: one tag, m centres, m sizes, drawn by `draw` as one vectorised pass per chunk
of regions -- pixel blocks gathered by fancy indexing, coverage evaluated on the (m, ky,
kx) block, scattered with `np.maximum.at` (or `np.add.at`). The hard budget is
`MAX_ROWS` rows per cell evaluation and it REFUSES (`Unsupported`) rather than truncates.
"""

import math
import re
import struct

import numpy as np

import assume
import fxrender
import sbsruntime
from sbsasm import fx_patterntype

from ops import Unsupported, sampler

#: Patterns per cell evaluation -- (chain emissions) x (regions of that cell). 4^10.
MAX_ROWS = 1 << 20

#: Nesting depth past which the tree is refused: 4^12 regions cannot fit `MAX_ROWS`.
MAX_DEPTH = 12

#: Elements of one (n, ky, kx) raster block; bounds the memory of a draw chunk.
BLOCK = 1 << 22

#: Pixels in a pattern copy's block at or above which it is drawn by slice, as the loop
#: draws it, rather than gathered into a batch. See `draw`.
SLICE_AREA = 4096

#: The universal header-to-body skew every FX pointer carries. See `sbsasm.fx_root`.
SKEW = 52

_RAND_CALL = re.compile(r"\brand\(")

#: Output index -> quadrant sign, (x, y), under each `fx.tree.order` arm.
QUADRANTS = {
    "rowmajor": ((-1, -1), (1, -1), (-1, 1), (1, 1)),
    "clockwise": ((-1, -1), (1, -1), (1, 1), (-1, 1)),
    "colmajor": ((-1, -1), (-1, 1), (1, -1), (1, 1)),
}


class Cell(object):
    """One entry cell: its tag, its table parameters, and its four output links."""

    __slots__ = ("off", "tag", "params", "kids")

    def __init__(self, off, tag, params, kids):
        self.off, self.tag, self.params, self.kids = off, tag, params, kids


def _tag_base(data, off, tag):
    """The address of the cell's TAG WORD, or None if the tag is not where the walk says.

    A walk item may land one word SHORT of its target's tag -- `fxrender.entries`: "the
    run begins one word later" -- so an entry whose stated offset holds another word is
    read from the word after it if THAT holds the tag. Anything else is a layout this
    reader does not know (the older format keeps the parameter block out of line, and its
    entry offsets address that block: `concrete_049`, `roofing_007` in the corpus).
    """
    if off + 4 <= len(data) and struct.unpack_from("<I", data, off)[0] == tag:
        return off
    if off + 8 <= len(data) and struct.unpack_from("<I", data, off + 4)[0] == tag:
        return off + 4
    return None


def pointer_slot(tag):
    """Which word of the cell holds its first child pointer.

    THE CELL LAYOUT, measured over the six reference packs and the 437-file corpus (the
    numbers are in FORMAT-NOTES.md, "Quadrant subdivision lands in render2"):

        [tag] [params ptr] [bit-7 word]? [child ptrs] [bit-4 word]? [params ...]

    `params ptr` (word 1) is the address of the cell's first parameter word -- for every
    bit-7-clear cell with parameters or a bit-4 word, 136,089 of 136,089, it equals
    `base + 4 * (2 + n)` with n the number of child-pointer words. The child pointers are
    therefore at word 2, one word (bit 17: the same child on all four outputs) or four
    (bit 16: one per output, 0 = unconnected). A BARE cell -- no parameter bits, no bit-4
    word, e.g. `0x20008` -- has no params ptr and is `[tag][next]`: its one pointer is at
    word 1 (52,178 cells). Bit 7's word sits BEFORE the pointers: 5,100 of 5,100 bit-7
    cells with a bit-17 pointer resolve at word 3 and none at word 2.

    THIS IS NOT THE ORDER `sbsasm.fx_entry_walk` STATES. That walk lays the structural bits
    out in ascending order -- 4, 7, 16, 17 -- which puts the bit-4 word before the
    pointers; the file puts it after. Both words are one slot wide, so every PROGRAM slot
    position the walk computes is unaffected, which is why nothing rendered differently;
    only the pointer word moves. 27,519 corpus cells carry bit 4 with a bit-17 pointer:
    27,500 resolve at word 2, 0 at word 3, 19 nowhere (old-format files whose entry
    offsets address an out-of-line block), and in all 27,500 word 3 holds an integer
    below 256 (42, 16, 11, 3, 80 -- Clouds_3's declared `randomseed` values among them).
    So the slot is stated here, with that measurement, and NOT taken from the walk.
    """
    bare = not (tag >> 19) and not (tag >> 4) & 1
    if bare:
        return 1
    return 2 + ((tag >> 7) & 1)


def pointer_count(tag):
    """How many child-pointer words the cell carries: 4 under bit 16, 1 under bit 17."""
    if (tag >> 16) & 1:
        return 4
    if (tag >> 17) & 1:
        return 1
    return 0


def cells_of(rec, table, run=None, slots=None):
    """The record's entry cells as a tree: ({offset: Cell}, walk order, roots).

    With `run` and `slots`, a child pointer that lands on a `0x89` gate is decided by the
    gate's own predicate over the seeded frame -- see `gated` -- and the gates so
    consumed are listed by `gated_nodes` for the chain walk to leave alone.

    Every `entry` item the walk yields is a cell; its parameters are the table's for that
    offset (the chain family is in the table too, once it carries a program -- `0x420008`
    with its `branchoffset` -- and a bare cell has none). Children are read from the
    cell's own pointer words (see `pointer_slot`), skewed by +52, and resolved to the cell
    at that address or, one word short, at the next.

    Roots are the cells nothing points at, in walk order: 191 of 191 Bricks records and
    the other five packs put the first walked entry among them. Refuses a cell whose tag
    word cannot be located while it carries pointers, and a pointer that resolves to
    nothing -- neither is a reading this module can draw from silently.
    """
    data = rec.asm.data
    by_off = {off: params for off, _tag, params in table}
    cells, order, nodes, headers = {}, [], set(), {}
    switched = assume.assumed("fx.pointercell", "switch") == "switch"
    for item in rec.fx_walk():
        if item[0] != "entry":
            nodes.add(item[1])
            headers[item[1]] = item[2]
            # A BARE QUADRANT MET IN A POINTER-CELL LIST is a cell of the tree: the walk
            # yields the list's `0x20008` links as nodes, and under `switch` each is the
            # nesting the switch before it passed into.
            if not (switched and item[2] > 0xFFFF and (item[2] & 0xF) == 8
                    and pointer_count(item[2]) and pointer_slot(item[2]) == 1):
                continue
        _k, off, tag, _p = item
        if off in cells:
            continue
        base = _tag_base(data, off, tag)
        n = pointer_count(tag)
        raw = [None] * 4
        if n:
            if base is None:
                raise Unsupported(
                    "fxmaps: entry cell %#x at %d carries child pointers but its tag "
                    "word is not at its offset" % (tag, off)
                )
            first = pointer_slot(tag)
            words = [
                struct.unpack_from("<I", data, base + 4 * (first + q))[0]
                for q in range(n)
            ]
            raw = [words[0]] * 4 if n == 1 else words
        cells[off] = Cell(off, tag, by_off.get(off, {}), raw)
        order.append(off)
    def resolve(target):
        if target in cells:
            return target
        if target + 4 in cells:
            return target + 4
        return None

    consumed = set()
    _GATED[rec.index] = consumed

    def through(target, depth=0):
        """The cell a POINTER CELL selects, under `fx.pointercell = switch`.

        `[0x9 | 0x49][next][payload]`, both pointers +52: bit 6 takes the payload, clear
        takes `next`; a `0x?4B` continues at its payload. See `assume.QUESTIONS`.
        """
        while switched and target in headers and pointer_cell_kind(headers[target]):
            if depth > MAX_DEPTH:
                return None
            hdr = headers[target]
            nxt = struct.unpack_from("<I", data, target + 4)[0]
            pay = struct.unpack_from("<I", data, target + 8)[0]
            pick = pay if (pointer_cell_kind(hdr) == "payload" or hdr & 0x40) else nxt
            if not pick:
                return None
            target = pick + SKEW
            depth += 1
        return target

    for c in cells.values():
        kids = []
        for w in c.kids:
            if not w:
                kids.append(None)
                continue
            target = through(w + SKEW)
            if target is None:
                kids.append(None)
                continue
            if run is not None and target in nodes:
                # A CHILD BEHIND A GATE THE FRAME CAN DECIDE. StylizedCobblestoneStreet
                # 607 (the library Tile Sampler): the eighth nested cell's pointer lands
                # on a `0x89` whose predicate is `min($size) >= 12`, and the next on
                # `>= 13` -- subdivide twice more only above 4096 px. `fxrender.chain`
                # lines those gates up after the spiral's and the list walk runs them per
                # emission, so at any smaller size the SECOND closes every pattern. Read
                # as the cell's own child gate: its predicate over the seeded frame picks
                # the true child (the gate's successor) or the false one (its spare),
                # and a gate with no child on the side it picks ends the nesting there.
                #
                # `fx.tree.gate = twoway` CONSUMES ONLY A GATE THAT HAS BOTH CHILDREN.
                # Consuming one removes it from the chain walk (`emissions` drops
                # `gated_nodes`), so a gate that was the chain's own terminator loses the
                # power to close the record: ChesterfieldSofa 321 emits 0 patterns under
                # the flat walk and 21,848 under this one, entirely because its two
                # `$sizelog2` gates are consumed here. A gate with no `spare` is not a
                # selector -- there is no false side for a predicate to pick -- and the
                # corpus agrees that this is the normal shape: of 27,333 `0x89`/`0x99`
                # nodes, 27,037 (98.92%) carry a TRUE child only and 289 (1.06%, in 27
                # files) carry both. Under `twoway` those 98.92% stay in the chain walk
                # and keep terminating it, and the 1.06% that really are two-way still
                # read as child gates. Default `consume` is the reading as it was.
                if assume.assumed("fx.tree.gate", "consume") == "consume" or _two_way(rec, target):
                    target = gated(rec, target, run, slots, consumed)
                if target is None:
                    kids.append(None)
                    continue
            k = resolve(target)
            if k is None and target in nodes:
                # AN OUTPUT WIRED THROUGH A CHAIN NODE. ChesterfieldSofa record 321 (and
                # StylizedCobblestoneStreet 607): a Quadrant's pointer lands on a `0x89`
                # gate whose run hands off to the next entry cells -- the "handoff goes
                # both ways" of `fx_walk`. The gate is driven by the chain walk as it
                # already is, once per emission; the tree reads THROUGH it to the first
                # entry its run names, which is the child that output draws.
                _items, starts = rec._fx_chain_run(target)
                for st in starts:
                    k = resolve(st)
                    if k is not None:
                        break
            if k is None:
                raise Unsupported(
                    "fxmaps: entry cell %#x at %d points at %d, which is not a cell"
                    % (c.tag, c.off, target)
                )
            kids.append(k)
        c.kids = kids
    pointed = {k for c in cells.values() for k in c.kids if k is not None}
    roots = [o for o in order if o not in pointed]
    if switched and rec.fx_root in headers and pointer_cell_kind(headers[rec.fx_root]):
        # THE ROOT IS A POINTER-CELL LIST: the tree starts at the cell the list selects,
        # and the cells the untaken branches name are not roots -- they are what the
        # baked switches passed over.
        top = through(rec.fx_root)
        top = resolve(top) if top is not None else None
        roots = [top] if top is not None else []
    return cells, order, roots


def _two_way(rec, target):
    """Does the `0x89` / `0x99` switch at `target` carry BOTH children?

    A gate with no `spare` has no false side for a predicate to pick, so it is a loop
    guard rather than a selector. See the census in `cells_of` and FORMAT-NOTES.md.
    """
    import fxchain

    n = fxchain.read_node(rec.asm, target)
    return n is not None and n.kind == "switch" and bool(n.loop) and bool(n.spare)


def gated(rec, target, run, slots, consumed, depth=0):
    """The offset a `0x89` gate at `target` hands its region to, or None.

    Follows the gate's TRUE child (its successor) when its predicate holds over `slots`
    and its FALSE child (its spare word) when it does not; either may be another gate.
    Anything that is not a gate is returned as it is for the caller to resolve.
    """
    import fxchain

    while depth <= MAX_DEPTH:
        n = fxchain.read_node(rec.asm, target)
        if n is None or n.kind != "switch" or not n.progs:
            return target
        consumed.add(target)
        try:
            ok = bool(np.asarray(run(n.progs[0], slots, 0)).ravel()[0])
        except Exception:
            return None
        child = n.loop if ok else n.spare
        if not child:
            return None
        target = child + SKEW
        depth += 1
    return None


#: {record index: gate offsets} `cells_of` consumed as child gates on its last call.
_GATED = {}


def gated_nodes(rec):
    """The gate offsets `cells_of` consumed as child gates on its last call."""
    return set(_GATED.get(rec.index, ()))


def pointer_cell_kind(hdr):
    """'switch' for the chain cell (`0x9`/`0x49`), 'payload' for `0x?4B`, else None."""
    if hdr > 0xFFFF or hdr & 0x80:
        return None
    nib = hdr & 0xF
    if nib == 9:
        return "switch"
    if nib == 0xB and hdr & 0x40:
        return "payload"
    return None


def topological(cells, roots):
    """Cells in an order that puts every parent before its children, from the roots.

    A cell can be named by two outputs of one parent, or by two parents -- 9804's leaf
    holds `[->leaf2, 0, ->leaf2, 0]` -- so this is a DAG walk, not a tree walk, and a
    cycle is refused: a region that nests inside itself has no size.
    """
    state, out = {}, []

    def visit(off, depth):
        s = state.get(off)
        if s == 2:
            return
        if s == 1:
            raise Unsupported("fxmaps: entry cell %d is its own descendant" % off)
        if depth > MAX_DEPTH:
            raise Unsupported(
                "fxmaps: entry tree nests deeper than %d levels" % MAX_DEPTH
            )
        state[off] = 1
        for k in cells[off].kids:
            if k is not None:
                visit(k, depth + 1)
        state[off] = 2
        out.append(off)

    for r in roots:
        visit(r, 0)
    out.reverse()
    return out


def depth_census(rec, table=None):
    """{cell offset: depth} under the root convention, for census tools. None if unreadable."""
    try:
        cells, _order, roots = cells_of(rec, table if table is not None else fxrender.entries(rec))
    except Unsupported:
        return None
    depth = {}
    todo = [(r, 0, True) for r in roots]
    while todo:
        off, d, is_root = todo.pop()
        if off in depth and depth[off] <= d:
            continue
        depth[off] = d
        for k in cells[off].kids:
            if k is not None:
                todo.append((k, d if is_root else d + 1, False))
    return depth


# ---------------------------------------------------------------------------
# Emission: the tree evaluated over regions x emissions
# ---------------------------------------------------------------------------


class Batch(object):
    """m patterns of ONE tag, as arrays: what a subdivided cell emits.

    `centre` is (m, 2) in canvas units and already includes the cell's `branchoffset`;
    `size`, `frameoffset` are (m, 2) in canvas units (region-scaled); `rotation` (m,),
    `opacity` (m, c) and `imageindex` (m,) are None where the cell states none. `depth`
    is the region depth per pattern, kept for the census and the notebook, not the draw.
    """

    __slots__ = (
        "tag",
        "patterntype",
        "count",
        "centre",
        "size",
        "frameoffset",
        "rotation",
        "opacity",
        "imageindex",
        "depth",
        "drawdepth0",
    )

    def __init__(self, tag, count, centre, size, frameoffset, rotation, opacity, imageindex, depth):
        self.tag = tag
        self.patterntype = fx_patterntype(tag)
        self.count = count
        self.centre = centre
        self.size = size
        self.frameoffset = frameoffset
        self.rotation = rotation
        self.opacity = opacity
        self.imageindex = imageindex
        self.depth = depth
        #: The record's shallowest DRAWING depth, filled in by `_emit` once every cell's
        #: batch exists. Read only by `_gain` under `fx.hurst.depth = firstdraw`.
        self.drawdepth0 = 0

    def as_dicts(self):
        """The same m patterns as `fx.splat`'s per-pattern dicts, for the arbiter draw."""
        out = []
        for j in range(self.count):
            p = {"patterntype": self.patterntype, "_tag": self.tag}
            p["branchoffset"] = self.centre[j].astype(np.float32)
            if self.size is not None:
                p["patternsize"] = self.size[j].astype(np.float32)
            if self.frameoffset is not None:
                p["frameoffset"] = self.frameoffset[j].astype(np.float32)
            if self.rotation is not None:
                p["patternrotation"] = np.asarray([self.rotation[j]], np.float32)
            if self.opacity is not None:
                p["opacity"] = self.opacity[j].astype(np.float32)
            if self.imageindex is not None:
                p["imageindex"] = np.asarray([self.imageindex[j]], np.float32)
            out.append(p)
        return out

    def __repr__(self):
        return "<Batch %#x x%d depth %s>" % (
            self.tag,
            self.count,
            sorted(set(int(d) for d in self.depth)) if self.depth is not None else None,
        )


def _calls_rand(asm, ptr):
    """Does the program at `ptr` call `rand`? Unknown source counts as yes."""
    import fx

    src = fx._prog_source(asm, ptr)
    return src is None or bool(_RAND_CALL.search(src))


def _rows(a, E, R, m, what):
    """A runner result as (rows, k) with rows in {1, E, m}, or refuse."""
    a = np.asarray(a)
    if a.ndim == 0:
        return a.reshape(1, 1)
    if a.ndim == 1:
        if m > 1 and a.shape[0] == m:
            return a.reshape(m, 1)
        if E > 1 and a.shape[0] == E:
            return a.reshape(E, 1)
        return a.reshape(1, -1)
    if a.ndim == 2 and a.shape[0] in (1, E, m):
        return a
    raise Unsupported(
        "fxmaps: %s returned %s for %d emissions x %d regions" % (what, a.shape, E, R)
    )


def _broadcast(a, E, R):
    """(rows, k) with rows in {1, E, E*R} -> (E*R, k)."""
    rows, k = a.shape
    m = E * R
    if rows == m:
        return a
    if rows == 1:
        return np.broadcast_to(a, (m, k))
    return np.repeat(a, R, axis=0)


def _evaluate(asm, run, params, frame, numbers, salt, E, R):
    """{name: (rows, k)} for one cell over E emissions x R regions.

    A cell whose programs call `rand` is evaluated WIDE: every one of its parameters runs
    once over all m = E * R rows -- `$number` repeated per region, the salt tiled per
    emission, every (E, C) slot of the stacked frame repeated per region. A cell that
    never calls `rand` runs over the E emissions alone, because nothing in it can differ
    between the regions of one emission, and is broadcast later. A baked parameter is
    one row either way.

    ONE FRAME PER CELL, SHARED BY ITS PARAMETERS IN EVALUATION ORDER. Bricks record 553's
    `opacity` writes slots 26, 27, 29, 30, 31 and its `branchoffset` reads 27 -- the
    dependence `in_eval_order` exists for -- so a fresh copy per parameter (which is what
    `fx._batch_emit` takes, having refused writers) refuses the record. The copy is per
    cell; writes do not reach the next cell nor the chain, see `emissions`.
    """
    m = E * R
    progs = [(n, v) for n, (k, v) in fxrender.in_eval_order(params) if k != "baked" and v]
    wide = any(_calls_rand(asm, v) for _n, v in progs)
    got = {}
    if wide:
        numbers_c = np.repeat(numbers, R)
        sbsruntime.CONTEXT["salt"] = np.tile(salt, E).reshape(-1, 1)
        frame_c = {
            k: (
                np.repeat(v, R, axis=0)
                if E > 1 and isinstance(v, np.ndarray) and v.ndim == 2 and v.shape[0] == E
                else v
            )
            for k, v in frame.items()
        }
    else:
        numbers_c = numbers
        sbsruntime.CONTEXT["salt"] = 0.0
        frame_c = dict(frame)
    for name, (kind, value) in fxrender.in_eval_order(params):
        if value is None:
            continue
        if kind == "baked":
            got[name] = np.asarray(value, np.float32).reshape(1, -1)
            continue
        a = run(value, frame_c, numbers_c, flatten=False)
        got[name] = _rows(a, E, R, m, name)
    return got


def _emit(rec, run, cells, order, roots, frame, numbers, cache):
    """Every cell's Batch for E = len(numbers) emissions sharing one stacked frame."""
    E = len(numbers)
    bo_region = assume.assumed("fx.tree.branchoffset", "canvas") == "region"
    quads = QUADRANTS[assume.assumed("fx.tree.order", "rowmajor")]
    root_set = set(roots)
    # Regions per cell: blocks of (cx (E, r), cy (E, r), depth (r,), salt (r,)), one block
    # per parent link, concatenated along the region axis so rows stay emission-major.
    regions = {off: [] for off in cells}
    # THE ROOT'S SALT IS ZERO, so a record whose tree is one cell -- depth 0, the
    # majority -- draws exactly what the flat arm draws: the same `rand` hash with the
    # same inputs. Chesterfield's `metallic`, the MAE 0.0004 arbiter, is such a record.
    # The probe salted the root by `$number` and so reseeded every depth-0 record it
    # touched; that difference is the probe's, not the model's.
    for i, r in enumerate(roots):
        z = np.zeros((E, 1))
        regions[r].append((z, z, np.zeros(1, np.int64), np.full(1, float(i))))
    out = []
    for off in order:
        blocks = regions[off]
        if not blocks:
            continue
        cx = np.concatenate([b[0] for b in blocks], axis=1)
        cy = np.concatenate([b[1] for b in blocks], axis=1)
        depth = np.concatenate([b[2] for b in blocks])
        salt = np.concatenate([b[3] for b in blocks])
        R = cx.shape[1]
        m = E * R
        if m > MAX_ROWS:
            raise Unsupported(
                "fxmaps: entry cell %#x has %d regions x %d emissions = %d patterns, "
                "over the budget of %d" % (cells[off].tag, R, E, m, MAX_ROWS)
            )
        cell = cells[off]
        s = np.exp2(-depth.astype(np.float64))  # region size, (R,)
        got = _evaluate(rec.asm, run, cell.params, frame, numbers, salt, E, R)
        # Region-unit scaling is a per-REGION factor, so every array below is taken to
        # (m, k) first and scaled by the region column tiled per emission.
        s_m = np.tile(s, E)[:, None]
        bo = got.get("branchoffset")
        if bo is None:
            bo_m = np.zeros((m, 2))
        else:
            bo_m = _broadcast(bo, E, R).astype(np.float64)
            if bo_m.shape[1] < 2:
                bo_m = np.repeat(bo_m[:, :1], 2, axis=1)
            bo_m = bo_m[:, :2] * (s_m if bo_region else 1.0)
        cxo = cx.reshape(m) + bo_m[:, 0]
        cyo = cy.reshape(m) + bo_m[:, 1]
        # `fx.tree.gridcell = cell`: A DEPTH-0 CELL WHOSE EMISSIONS WALK A LATTICE IS DRAWN IN
        # LATTICE-CELL UNITS. Bricks 3030 emits 841 = 29 x 29 patterns at branchoffsets
        # (0,0), (0,1), (-1,1) ... -- integers -- with patternsize 2.82; read in canvas units
        # every integer offset wraps to the SAME point of the toroidal canvas, so 841 stamps
        # of a 2.82-canvas blob pile on one spot: a constant under `max`, saturated under
        # add. Read in cells of 1/29 it is a 29 x 29 grid of bumps 2.82 cells wide. The test
        # is `fx._cell`'s, applied to the batch's own offsets: every value an integer, span
        # >= 1, one distinct value per cell. `fx._cell` declines tree batches; this is the
        # same rule on the path that now draws these records. Default `canvas`, as it was.
        grid = None
        if (
            assume.assumed("fx.tree.gridcell", "canvas") == "cell"
            and bo is not None
            and not np.any(depth)
        ):
            d = []
            for k in range(2):
                col = bo_m[:, k]
                sp = float(col.max() - col.min())
                ok = (
                    sp >= 1
                    and abs(sp - round(sp)) < 1e-4
                    and bool(np.all(np.abs(col - np.round(col)) < 1e-4))
                    and len({round(float(t), 6) for t in col}) == round(sp) + 1
                )
                d.append(1.0 / (round(sp) + 1.0) if ok else 1.0)
            if any(x != 1.0 for x in d):
                grid = np.asarray(d, np.float64)[None, :]
                cxo = cx.reshape(m) + bo_m[:, 0] * grid[0, 0]
                cyo = cy.reshape(m) + bo_m[:, 1] * grid[0, 1]
                assume.note(rec.index)
        centre = np.stack([cxo, cyo], axis=1)
        marker = (cell.tag & 0xFF) == 0x08
        size = got.get("patternsize")
        # `fx.bare = skip`: a cell with nothing to draw with places regions only (the flat
        # draw's twin is in `fx.splat`).
        bare = (
            size is None
            and got.get("opacity") is None
            and got.get("imageindex") is None
            and fx_patterntype(cell.tag) is None
            and assume.assumed("fx.bare", "skip") == "skip"
        )
        if bare:
            assume.note(rec.index)
        if size is None:
            size_m = None if (marker or bare) else np.repeat(s_m, 2, axis=1)
        else:
            size_m = _broadcast(size, E, R).astype(np.float64)
            if size_m.shape[1] < 2:
                size_m = np.repeat(size_m[:, :1], 2, axis=1)
            size_m = size_m[:, :2] * s_m
            if grid is not None:
                size_m = size_m * grid
        fo = got.get("frameoffset")
        if fo is not None:
            fo = _broadcast(fo, E, R).astype(np.float64)
            if fo.shape[1] < 2:
                fo = np.repeat(fo[:, :1], 2, axis=1)
            fo = fo[:, :2] * s_m
            if grid is not None:
                fo = fo * grid
        rot = got.get("patternrotation")
        rot = None if rot is None else _broadcast(rot, E, R)[:, 0].astype(np.float64)
        opa = got.get("opacity")
        opa = None if opa is None else _broadcast(opa, E, R).astype(np.float32)
        img = got.get("imageindex")
        img = None if img is None else _broadcast(img, E, R)[:, 0].astype(np.float64)
        out.append(
            Batch(cell.tag, m, centre, size_m, fo, rot, opa, img, np.tile(depth, E))
        )
        if not any(k is not None for k in cell.kids):
            continue
        cxo2, cyo2 = cxo.reshape(E, R), cyo.reshape(E, R)
        if off in root_set:
            # THE ROOT DOES NOT SUBDIVIDE: its children's region is its own. A root with
            # four distinct children (bit 16; one record in RustyMetal) gets each of them
            # at the full region, which is what "the same region" says and is otherwise
            # unarbitrated.
            for k in dict.fromkeys(k for k in cell.kids if k is not None):
                regions[k].append((cxo2, cyo2, depth, salt * 4.0 + 1.0))
            continue
        q = (s / 4.0)[None, :]
        for qi, (qx, qy) in enumerate(quads):
            k = cell.kids[qi]
            if k is None:
                continue
            regions[k].append(
                (cxo2 + qx * q, cyo2 + qy * q, depth + 1, salt * 4.0 + (qi + 1.0))
            )
    # THE SHALLOWEST LEVEL THAT PUTS INK ON THE CANVAS, for `fx.hurst.depth = firstdraw`.
    # A cell DRAWS exactly when it got a size: a marker (`tag & 0xFF == 0x08`) that states
    # no `patternsize` only places regions for its children, so it cannot be where a
    # per-depth gain starts counting. Taken from the batches rather than from the tags
    # because that is the same predicate `draw` uses to decide whether to draw at all.
    drawn = [
        int(b.depth.min())
        for b in out
        if b.size is not None and b.depth is not None and len(b.depth)
    ]
    d0 = min(drawn) if drawn else 0
    for b in out:
        b.drawdepth0 = d0
    return out


def _collapse_cache(cache, before):
    """Leave the LAST row at every cache index a batched write filled, as `fx` does."""
    for k, v in list(cache.items()):
        if before.get(k) is v:
            continue
        a = np.asarray(v)
        if a.ndim == 2 and a.shape[0] > 1:
            cache[k] = a[-1:]


def emissions(rec, run, slots, nodes, table, reads, cache=None):
    """[Batch] for every cell of the entry tree, over every emission of the chain.

    `reads` is `fx.batch_reads`' answer: the slots the entry parameters read, or None
    where the table cannot be batched. With a slot set, the chain is walked once
    recording frames (`fx._walk`), the frames are stacked (`fx._stack`), and the whole
    tree is evaluated over every emission at once. Without one -- or where the frames do
    not stack -- the chain is walked recording the WHOLE frame per emission (`collect`
    is the live key view, so each record is a copy of the frame as the emission saw it)
    and the tree is evaluated per emission over that snapshot. Under both, an entry
    parameter's slot writes stay in the snapshot and do not reach the chain's later
    emissions -- the property the batched flat path already has, and the one place the
    scalar walk's interleaving is not reproduced.
    """
    import fx

    cells, order, roots = cells_of(rec, table, run, slots)
    topo = topological(cells, roots)
    if any(k is not None for c in cells.values() for k in c.kids):
        assume.note(rec.index)
    skip = gated_nodes(rec)
    if skip:
        nodes = [n for n in nodes if n[0] not in skip]
    before = dict(cache) if cache is not None else {}
    try:
        if reads is not None:
            seed = dict(slots)
            frames, closed = fx._walk(rec, run, slots, nodes, table, reads)
            if not frames:
                if not closed:
                    raise Unsupported("fxmaps: emitted no patterns and no gate closed")
                return []
            stacked = fx._stack([f for _n, f in frames], sorted(reads), len(frames))
            if stacked is not None:
                numbers = np.array([n for n, _f in frames], dtype=np.float64)
                return _emit(rec, run, cells, topo, roots, stacked, numbers, cache)
            slots.clear()
            slots.update(seed)
        frames, closed = fx._walk(rec, run, slots, nodes, table, slots.keys())
        if not frames and not closed:
            raise Unsupported("fxmaps: emitted no patterns and no gate closed")
        out = []
        for number, frame in frames:
            out.extend(
                _emit(rec, run, cells, topo, roots, frame, np.array([number]), cache)
            )
        return out
    finally:
        sbsruntime.CONTEXT["salt"] = 0.0
        if cache is not None:
            _collapse_cache(cache, before)


# ---------------------------------------------------------------------------
# Drawing: one vectorised pass per chunk of regions
# ---------------------------------------------------------------------------


def _opacity(b, nchan, neg):
    if b.opacity is None:
        col = np.ones((b.count, nchan), np.float32)
    else:
        col = b.opacity
        if col.shape[1] < nchan:
            col = np.repeat(col[:, :1], nchan, axis=1)
        col = col[:, :nchan]
    if neg == "signed":
        return np.clip(col, -1.0, 1.0).astype(np.float32)
    if neg == "abs":
        return np.clip(np.abs(col), 0.0, 1.0).astype(np.float32)
    return np.clip(col, 0.0, 1.0).astype(np.float32)


def _sources(b, images):
    """[(pattern mask or None, image or None)]: which image each pattern stamps.

    The rule is `fx._image_for`'s: no `imageindex` on a one-image record is that image;
    no index otherwise is a generated profile; a stated index is looked up per pattern.
    """
    if not images:
        return [(None, None)]
    if b.imageindex is None:
        if len(images) == 1:
            return [(None, next(iter(images.values())))]
        return [(None, None)]
    idx = np.round(b.imageindex).astype(np.int64)
    out = []
    for v in np.unique(idx):
        out.append((idx == v, images.get(int(v))))
    return out


def _gain(b, header):
    """(m, 1) multiplier on the batch's opacity from the record header, or None.

    `opacitymult` (field 2) scales every pattern; `hurst` (field 1) scales by depth under
    `fx.hurst`: `exp` is 2^(-hurst * depth), `exp2` is 2^(-2 * hurst * depth), `pow` is
    hurst^depth, `off` is 1. A record
    that bakes no `hurst` takes `fx.hurst.absent` -- 0 or 1 -- because the source omits
    the default and the file does not state it. Depth is the region depth the tree gave
    each pattern (root 0, its children 0, one more per quadrant level), so the flat arm,
    whose patterns are all depth 0, is scaled by `opacitymult` alone -- or, under
    `fx.hurst.depth = firstdraw`, that depth measured from the record's shallowest
    DRAWING level (`Batch.drawdepth0`). `root` is the default and is what this did.
    """
    if header is None:
        return None
    g = None
    opmul = header.get("opacitymult")
    if opmul is not None:
        g = np.full((b.count, 1), float(opmul), np.float32)
    how = assume.assumed("fx.hurst", "exp")
    if how != "off" and b.depth is not None:
        h = header.get("hurst")
        if h is None:
            h = 1.0 if assume.assumed("fx.hurst.absent", "zero") == "one" else 0.0
        d = np.asarray(b.depth, np.float64).reshape(-1, 1)
        # WHERE THE EXPONENT STARTS, behind `fx.hurst.depth`. `root` leaves `d` as the
        # region depth; `firstdraw` measures it from the record's shallowest drawing
        # level, so the top of a record's own ladder is unattenuated whatever depth the
        # subdivision had to reach to get there. Clamped at 0: a batch shallower than
        # `drawdepth0` is a marker and puts no ink down, so its gain is never read.
        if assume.assumed("fx.hurst.depth", "root") == "firstdraw":
            d = np.maximum(d - float(b.drawdepth0), 0.0)
        if how == "exp":
            f = np.exp2(-float(h) * d)
        elif how == "exp2":
            # 2^(-2 * hurst * depth): the exponent per AREA halving. This branch was
            # missing -- `exp2` fell through to `pow` and was a duplicate of it, so the
            # reading `assume.py` describes had never been run. `exp` is untouched.
            f = np.exp2(-2.0 * float(h) * d)
        else:
            f = np.power(float(h), d)
        f = f.astype(np.float32)
        g = f if g is None else g * f
    return g


def draw(canvas, b, W, H, images=None, header=None):
    """Draw a Batch onto `canvas` (H, W, nchan), under `fx.splat`'s own arms.

    `header` is `fx.header_fields`' reading of the record's w1 fields; see `_gain`.

    Per pattern this is `fx.splat`'s arithmetic -- the same footprint, the same tile
    wrap, the same coverage -- written over arrays: every copy of every pattern gets a
    (ky, kx) pixel block sized to the largest in its chunk, local coordinates are
    computed on the (n, ky, kx) block, and the covered samples are scattered into the
    canvas with `np.maximum.at`, which is `_combine`'s `max` exactly because a maximum is
    order-free. `add` is `np.add.at`. The `over` arm is order-dependent and is not drawn
    here: `fx.splat` expands the batch to per-pattern dicts for it.
    """
    import fx

    nchan = canvas.shape[2]
    if assume.assumed("fx.markers", "skip") == "skip" and (b.tag & 0xFF) == 0x08:
        return
    if b.size is None:
        return
    mode = fx.combine_mode(header)
    if mode == "bit18":
        mode = fx._mode_for(b.tag, mode)
    if mode not in ("max", "add"):
        raise Unsupported("fxmaps: fx.combine=%s is not drawn as a grid" % mode)
    forced = assume.assumed("fx.profile")
    neg = assume.assumed("fx.negopacity", "signed")
    prof = forced if forced is not None else fx._profile_for({"patterntype": b.patterntype})
    m = b.count
    # THE LOOP'S OWN ROUNDING, so that a depth-0 record draws bit for bit what the flat
    # arm draws: `splat` reads every parameter as float32, adds `branchoffset` and
    # `frameoffset` in float32, and lifts the results to Python floats. The same casts in
    # the same order here; the test holds the two equal.
    size = b.size.astype(np.float32)
    centre = b.centre.astype(np.float32)
    if b.frameoffset is not None:
        centre = centre + b.frameoffset.astype(np.float32)
    sx = size[:, 0].astype(np.float64)
    sy = size[:, 1].astype(np.float64)
    cx = centre[:, 0].astype(np.float64)
    cy = centre[:, 1].astype(np.float64)
    if assume.assumed("fx.centre", "reach") == "wrap":
        # The canvas is a torus; see `fx.splat` and `assume.QUESTIONS['fx.centre']`.
        cx = (cx + 0.5) % 1.0 - 0.5
        cy = (cy + 0.5) % 1.0 - 0.5
    ok = np.isfinite(sx) & np.isfinite(sy) & np.isfinite(cx) & np.isfinite(cy)
    ok &= (sx > 0) & (sy > 0)
    ok &= np.maximum(sx, sy) <= 64.0
    ok &= np.minimum(sx, sy) >= fx.MIN_SIZE
    if not ok.any():
        return
    col = _opacity(b, nchan, neg)
    gain = _gain(b, header)
    if gain is not None:
        col = (col * gain).astype(np.float32)
    rot = np.zeros(m) if b.rotation is None else b.rotation.astype(np.float32).astype(np.float64)
    rot = np.where(np.isfinite(rot), rot, 0.0)  # the texture rule, as in `fx.splat`
    th = 2.0 * np.pi * rot
    if assume.assumed("fx.rotation", "ccw") == "cw":
        th = -th  # see assume.QUESTIONS['fx.rotation']
    ct, st = np.cos(th), np.sin(th)
    hx = 0.5 * (sx * np.abs(ct) + sy * np.abs(st))
    hy = 0.5 * (sx * np.abs(st) + sy * np.abs(ct))
    reach = np.minimum(3, np.ceil(np.maximum(sx, sy))).astype(np.int64)
    txlo = np.maximum(-reach, np.ceil(-0.5 - cx - hx)).astype(np.int64)
    txhi = np.minimum(reach, np.floor(0.5 - cx + hx)).astype(np.int64)
    tylo = np.maximum(-reach, np.ceil(-0.5 - cy - hy)).astype(np.int64)
    tyhi = np.minimum(reach, np.floor(0.5 - cy + hy)).astype(np.int64)
    # THE TILE WRAP AS COPIES. `splat` loops tx, ty per pattern; here every (pattern,
    # tx, ty) that the pattern's own range admits becomes one row of the raster.
    pi, tx, ty = [], [], []
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            sel = ok & (txlo <= dx) & (dx <= txhi) & (tylo <= dy) & (dy <= tyhi)
            if sel.any():
                w = np.flatnonzero(sel)
                pi.append(w)
                tx.append(np.full(w.size, dx))
                ty.append(np.full(w.size, dy))
    if not pi:
        return
    pi = np.concatenate(pi)
    ux = cx[pi] + np.concatenate(tx)
    uy = cy[pi] + np.concatenate(ty)
    hxp, hyp = hx[pi], hy[pi]
    c0 = np.maximum(np.floor((ux - hxp + 0.5) * W - 0.5), 0).astype(np.int64)
    c1 = np.minimum(np.ceil((ux + hxp + 0.5) * W - 0.5), W - 1).astype(np.int64)
    r0 = np.maximum(np.floor((uy - hyp + 0.5) * H - 0.5), 0).astype(np.int64)
    r1 = np.minimum(np.ceil((uy + hyp + 0.5) * H - 0.5), H - 1).astype(np.int64)
    keep = (c0 <= c1) & (r0 <= r1)
    if not keep.any():
        return
    pi, ux, uy, c0, c1, r0, r1 = (a[keep] for a in (pi, ux, uy, c0, c1, r0, r1))
    kx, ky = c1 - c0 + 1, r1 - r0 + 1
    # Same float32 grid as `splat`'s, and the same float32 arithmetic below it.
    pxg = (np.arange(W, dtype=np.float32) + 0.5) / W - 0.5
    pyg = (np.arange(H, dtype=np.float32) + 0.5) / H - 0.5
    ux32, uy32 = ux.astype(np.float32), uy.astype(np.float32)
    ct32, st32 = ct[pi].astype(np.float32), st[pi].astype(np.float32)
    sx32, sy32 = sx[pi].astype(np.float32), sy[pi].astype(np.float32)
    flat_canvas = canvas.reshape(H * W, nchan)
    srcs = _sources(b, images)
    rect = prof in ("rect", "square")
    area = kx * ky
    # A LARGE FOOTPRINT IS DRAWN AS THE LOOP DRAWS IT. Gathering a (ky, kx) block by
    # fancy index and scattering it back costs about three passes over the block that a
    # slice does not, and for a pattern covering the canvas -- Bricks record 711: 1,024
    # patterns of size (5, 5), each wrapping 36 times over 256 x 256 -- that is the whole
    # cost: 3.0 s against the loop's 0.6 s. So copies whose block is at least `SLICE_AREA`
    # pixels take the slice path below, which is `splat`'s tile arithmetic on the same
    # per-copy values, and only the small ones -- the grid -- are batched.
    big = np.flatnonzero(area >= SLICE_AREA)
    for j in big:
        cc0, cc1, rr0, rr1 = int(c0[j]), int(c1[j]), int(r0[j]), int(r1[j])
        dx = (pxg[cc0 : cc1 + 1] - ux32[j])[None, :]
        dy = (pyg[rr0 : rr1 + 1] - uy32[j])[:, None]
        lx = (dx * ct32[j] + dy * st32[j]) / sx32[j]
        ly = (-dx * st32[j] + dy * ct32[j]) / sy32[j]
        if rect:
            hit = (np.abs(lx) <= 0.5) & (np.abs(ly) <= 0.5)
            cov = None
        else:
            cov = fx._coverage(lx, ly, prof)
            hit = cov > 0
        if not hit.any():
            continue
        tile = canvas[rr0 : rr1 + 1, cc0 : cc1 + 1]
        colj = col[pi[j]]
        for mask, src in srcs:
            if mask is not None and not mask[pi[j]]:
                continue
            if src is None:
                if cov is None and hit.all():
                    tile[...] = fx._combine(tile, colj, mode)
                elif fx.BLEND_IN_PLACE:
                    fx._blend(
                        tile, colj if cov is None else colj * cov[:, :, None], mode, hit[:, :, None]
                    )
                else:
                    tile[hit] = fx._combine(
                        tile[hit], colj if cov is None else colj * cov[hit, None], mode
                    )
                continue
            uv = np.stack([lx[hit] + 0.5, ly[hit] + 0.5], axis=-1)
            got = np.asarray(sampler(src)(uv), np.float32)
            if got.ndim == 1:
                got = got[:, None]
            if got.shape[-1] < nchan:
                got = np.repeat(got[:, :1], nchan, axis=-1)
            tile[hit] = fx._combine(
                tile[hit],
                got[:, :nchan] * colj if cov is None else got[:, :nchan] * colj * cov[hit, None],
                mode,
            )
    # CHUNKS OF SIMILAR FOOTPRINT. Sorted by block area so a chunk's (ky, kx) block is not
    # sized by one large pattern for thousands of small ones.
    ordr = np.argsort(area, kind="stable")
    ordr = ordr[area[ordr] < SLICE_AREA]
    n = ordr.size
    i = 0
    while i < n:
        seg = ordr[i:]
        cnt = np.arange(1, seg.size + 1)
        kxm = np.maximum.accumulate(kx[seg])
        kym = np.maximum.accumulate(ky[seg])
        over = np.flatnonzero(cnt * kxm * kym > BLOCK)
        j = i + (int(over[0]) if over.size else seg.size)
        if j == i:
            j = i + 1
        idx = ordr[i:j]
        i = j
        KX, KY = int(kx[idx].max()), int(ky[idx].max())
        cols = c0[idx][:, None] + np.arange(KX)[None, :]
        rows = r0[idx][:, None] + np.arange(KY)[None, :]
        vc = cols <= c1[idx][:, None]
        vr = rows <= r1[idx][:, None]
        dx = pxg[np.minimum(cols, W - 1)] - ux32[idx][:, None]
        dy = pyg[np.minimum(rows, H - 1)] - uy32[idx][:, None]
        c_ = ct32[idx][:, None, None]
        s_ = st32[idx][:, None, None]
        lx = (dx[:, None, :] * c_ + dy[:, :, None] * s_) / sx32[idx][:, None, None]
        ly = (-dx[:, None, :] * s_ + dy[:, :, None] * c_) / sy32[idx][:, None, None]
        if rect:
            hit = (np.abs(lx) <= 0.5) & (np.abs(ly) <= 0.5)
            cov = None
        else:
            cov = fx._coverage(lx, ly, prof)
            hit = cov > 0
        hit &= vr[:, :, None] & vc[:, None, :]
        for mask, src in srcs:
            h = hit if mask is None else (hit & mask[pi[idx]][:, None, None])
            ni, ri, ci = np.nonzero(h)
            if ni.size == 0:
                continue
            flat = rows[ni, ri] * W + cols[ni, ci]
            vals = col[pi[idx][ni]]
            if src is not None:
                uv = np.stack([lx[ni, ri, ci] + 0.5, ly[ni, ri, ci] + 0.5], axis=-1)
                got = np.asarray(sampler(src)(uv), np.float32)
                if got.ndim == 1:
                    got = got[:, None]
                if got.shape[-1] < nchan:
                    got = np.repeat(got[:, :1], nchan, axis=-1)
                vals = got[:, :nchan] * vals
            if cov is not None:
                # `(image * opacity) * coverage`, the loop's own association.
                vals = vals * cov[ni, ri, ci][:, None]
            if mode == "add":
                np.add.at(flat_canvas, flat, vals.astype(np.float32))
            else:
                np.maximum.at(flat_canvas, flat, vals.astype(np.float32))
