#!/usr/bin/env python3
"""FX-Map evaluation: how many patterns a record emits, and where each one lands.

STRUCTURE COMES FROM THE TAG, and this module does not re-derive it -- `fxrender.chain`
and `fxrender.entries` read the node chain and the parameter table out of the tag words,
which is the same mask-walk one scale down, and duplicating that walk is exactly how the
nibble-8 category error survived (two implementations making the same mistake in parallel
never disagree). What is rewritten here is everything downstream: WHEN each program runs,
HOW MANY times, and what the numbers mean once you have them.

WHICH ROLE A NODE HAS is asked of `fxnodes`, so the arms below dispatch on
`count`/`gate`/`state`/`leaf` rather than on header constants. The role itself is
`fxrender`'s census under either arm of `assume.QUESTIONS['fx.nodemodel']` -- nothing in the
mask states what a node's program does, and a rule that read one off the low nibble was
withdrawn as a fit. What the arm chooses is how the node's programs were LOCATED: by the
mask, or by `FX_NODE_PARAMS`' per-header offsets. See `fxnodes`.

THE EMISSION COUNT IS STATED BY THE PLACEMENT PROGRAM, and reading it there rather than
from `numberadded` is the change that renders `Rokviz japanese fabric 8`.

That record's FX-Map (record 6) has an `addnode` whose `numberadded` evaluates to exactly
1 -- `((slot8 - 1) mod 2 + slot8)**2` with slot8 = 1 -- and a gate whose spiral leaves its
1x1 box after one step. One emission. Yet its own two parameter programs both divide by
45:

    frameoffset = vec2(0, 0.5 + $number * (1/45)) + slot12
    patternsize = vec2(1.41774, 0.5/(45 * $size.y) + 1/(90*sqrt2))

A bar sqrt2 long at 0.125 turns -- the unit square's diagonal, at 45 degrees -- stepped by
1/45 in y walks a perpendicular spacing of 1/(45*sqrt2) = 0.015713, and its width
1/(90*sqrt2) = 0.007857 is EXACTLY HALF of that. 45 emissions is a twill at 50% duty; the
90 in the width is 2 x 45.

Three independent measurements agree that 45 is the count:

  * the arithmetic above closes to 0.5028 coverage, and the record's own consumer chain
    ends at the `height` output, whose reference mean 0.78628 back-solves through two
    `levels` to a mask of mean 0.50008;
  * the exported height map's 2-D FFT peaks at (965, 965) cycles over 4096 px, and
    45 x 21.4334 = 964.5, where 21.4334 is the baked matrix of the `transformation` that
    consumes the chain;
  * rendering it at 45 gives the mask mean 0.5029 and takes `height` to r = +0.944 with
    an MAE of 0.0004 against the package's own export.

`fxrender.grid_width` already reads a count out of a placement program -- but only from
the `floor($number / N)` spelling, and only when the program also touches slot 26. The
same statement written as a MULTIPLY by 1/N is the same statement. `number_grid` reads
both, and reads the DIMENSIONALITY too: a program that decomposes $number into a row and
a column walks an N x N grid, one that scales it linearly walks a run of N.
"""

import math
import re
import struct

import numpy as np

import assume
import disasm
import fxchain
import fxnodes
import fxrender
import fxtree
import sbsruntime
from sbsasm import fx_patterntype

from ops import Unsupported, sampler

#: THE PATTERN BUDGET IS A RUNTIME GUARD, NOT A READING, and it sits above the largest
#: count the corpus states. Tile samplers at full density emit 1024^2, 1025^2, 1501^2 and
#: 2049^2 = 4,198,401 patterns (54 files refused at the old 300,000, each after minutes
#: of walking). With the table batched (`batch_reads`, sibling writes included) the
#: emission of 589,824 patterns is 0.3 s and their draw 18 s at 64 px; the draw is the
#: cost, ~30 us a pattern, so the worst corpus record is ~2 min. 2^23 leaves the guard
#: for a count program gone wrong (2^31 - 1 is what an unset count reads as).
MAX_PATTERNS = 1 << 23
#: Patterns per pixel of the grid above which a record is refused as sub-pixel at that
#: grid (see `render_fxmaps`).
MAX_PER_PIXEL = 64

_GRID_CACHE = {}

#: Opcodes that mean `$number` has been decomposed rather than scaled -- a row/column
#: split, which is `grid_width`'s two-axis case and not this one. Read BROADLY on purpose:
#: a false "two-dimensional" only declines the record and falls back to `numberadded`,
#: while a missed one would emit N patterns where the record wants N**2.
_DECOMPOSE = ("mod", "cvt", "floor")

#: The `$number` system variable's id. See sbsruntime.SYSVARS.
_NUMBER = 10


def _const_value(addr, op, toks):
    """A `const` instruction's value, as a float, respecting its TYPE.

    `disasm.floats` reinterprets the immediate as float32, which is right for a float
    constant and garbage for an integer one -- `const.i1 27` reads back as 3.78e-44. The
    opcode's type field says which, and an integer divisor spelled `const.i1 45` is
    exactly the case a reader that only understands floats cannot see.
    """
    _ntok, ty, _comps, _oid = disasm.fields(op)
    imm = disasm.immediate(addr, toks)
    if imm is None or len(imm) < 4:
        return None
    if ty == 2:
        return float(struct.unpack_from("<I", imm, 0)[0])
    got = disasm.floats(addr, toks)
    return float(got[0]) if got else None


def number_grid(rec):
    """(N, dims) the placement programs state for `$number`, or None.

    N is the constant `$number` is scaled by -- `$number / N` or `$number * (1/N)`, the
    same statement in two spellings. `dims` is 2 when the program also DECOMPOSES
    `$number`, which is a two-axis layout and `grid_width`'s case, and 1 when it scales it
    linearly, which is a run of N.

    READ OFF THE BYTECODE, NOT OFF TRANSPILED PYTHON. This walked `transpile`'s output
    with regular expressions, which coupled the emission count -- and through it the one
    number the suite guards, Rokviz's `height` mean -- to that module's exact formatting,
    so a reformat would have changed a render silently. It was also incomplete in a way
    that mattered: the constant pattern required a decimal point, and `transpile` emits
    integer constants bare (`v24 = 1`), so every integer-spelled divisor was invisible.
    Instructions are the format's own statement and have neither problem.

    Registers are implicit: instruction k defines register k and its operand tokens name
    earlier registers, so this is a small SSA walk. Bounded at 4096 because above that
    `$number` is a coordinate normalised by the canvas rather than a stamp index.
    """
    key = (getattr(rec.asm, "path", id(rec.asm)), rec.index)
    if key in _GRID_CACHE:
        return _GRID_CACHE[key]
    asm = rec.asm
    ptrs = set()
    try:
        for item in rec.fx_walk():
            p = item[3] if len(item) > 3 else None
            if p:
                ptrs.add(p)
    except Exception:
        pass
    found, dims = set(), 1
    for ptr in sorted(ptrs):
        end = asm.program_span(ptr)
        if not end:
            continue
        num, const = set(), {}
        try:
            stream = list(disasm.decode(asm.data, ptr, end))
        except Exception:
            continue
        for k, addr, op, toks in stream:
            nm = disasm.name(op)
            if nm == "sysvar":
                if toks and toks[0] == _NUMBER:
                    num.add(k)
                continue
            if nm == "const":
                v = _const_value(addr, op, toks)
                if v is not None:
                    const[k] = v
                continue
            # An operand token is a register only if it names an EARLIER instruction;
            # anything else in the tuple is an immediate.
            regs = [t for t in toks if t < k]
            if nm in ("mul", "div") and len(toks) >= 2:
                a, b = toks[0], toks[1]
                pairs = ((a, b), (b, a)) if nm == "mul" else ((a, b),)
                for x, y in pairs:
                    if x in num and const.get(y):
                        n = (1.0 / const[y]) if nm == "mul" else const[y]
                        if abs(n - round(n)) < 1e-3 and 1 < round(n) <= 4096:
                            found.add(int(round(n)))
                        num.add(k)
            if any(r in num for r in regs):
                if nm in _DECOMPOSE:
                    dims = 2
                num.add(k)
    got = (found.pop(), dims) if len(found) == 1 else None
    _GRID_CACHE[key] = got
    return got


def emission_count(rec, numberadded):
    """How many patterns to emit, and how the chain's own nodes are driven alongside.

    Returns (count, mode). The three modes, in the order they are tried:

    'grid'       `fxrender.grid_width` -- the ESTABLISHED reading, and the default arm of
                 `fx.gridcount`. Where a placement program lays a $number grid as
                 `floor($number / N)`, the loop bound is that grid's cell count N**2 and
                 not `numberadded`, which for these records is an amount. This is what put
                 the tufting lattice on Chesterfield and ratcheted five packs' reference
                 floors; dropping it costs `normal` 0.95 -> -0.01 there. Steppers run once
                 across the batch, gates per emission -- exactly as `fxrender` drives it.

    'placement'  the narrow addition. An iterator that runs ONCE under a placement program
                 whose position is a function of `$number`: such a record computes a
                 per-iteration position and visits one of them, so 44 of the 45 positions
                 its own formula names are never drawn. That contradiction is the trigger,
                 and it fires on 137 of 41,906 fxmaps records. Steppers AND gates run once,
                 for the same reason steppers do under 'grid' -- the placement already
                 carries this pattern's position and re-driving the spiral adds a second.

    'chain'     `numberadded`, believed, and everything driven per emission. The default.

    NOT "read a count out of a program" in general, which is far too loose: scanning every
    FX placement program for a `$number` scale finds a constant on 4,488 records and finds
    FIVE OR SIX candidates on most of them, so picking one would be inventing a number.
    `number_grid` answers only where the record names exactly ONE.
    """
    if assume.assumed("fx.gridcount", "divisor") == "divisor":
        w = _grid_width(rec)
        if w:
            return w * w, "grid"
    if numberadded == 1:
        # THE LEAF'S BAKED COUNT, where the count node degenerates to 1. Tiled roof 383:
        # `numberadded` is `((aspect - 1) mod 2 + aspect)^2` -- the spiral's bound, 1 on a
        # square canvas -- under a leaf `0x160B` that states 22, and its entry's
        # branchoffset walks `$number` down a column. The same contradiction 'placement'
        # fires on, with the count stated by the file instead of read off a constant;
        # the gate that bounds the spiral runs once, as under 'placement'. Where both are
        # readable and the node's count is not 1 the two agree (46 of 46); the 10 that
        # differ are all of this shape. See `leaf_count`; the arm is `fx.leafcount`.
        n = leaf_count(rec) if assume.assumed("fx.leafcount", "header") == "header" else 0
        if n > 1 and n <= MAX_PATTERNS:
            return n, "placement"
        grid = number_grid(rec)
        # ONE-DIMENSIONAL ONLY. The two-axis spelling is `grid_width`'s own case, and where
        # it declines a record that is `grid_width`'s judgement -- overriding it with a
        # looser test is re-extending a rule past its evidence, which is the failure this
        # whole board is written against. What is left is the gap `grid_width` cannot
        # express at all: `$number` scaled LINEARLY by 1/N, a run of N rather than a grid.
        if grid is not None and grid[1] == 1 and grid[0] <= MAX_PATTERNS:
            return grid[0], "placement"
    return numberadded, "chain"


_WIDTH_CACHE = {}


def _grid_width(rec):
    key = (getattr(rec.asm, "path", id(rec.asm)), rec.index)
    if key not in _WIDTH_CACHE:
        try:
            _WIDTH_CACHE[key] = fxrender.grid_width(rec)
        except Exception:
            _WIDTH_CACHE[key] = None
    return _WIDTH_CACHE[key]


#: THERE IS NO SIZE THRESHOLD, and the obvious one is a pessimisation. `fxrender` keeps a
#: `BATCH_MIN` because there the decision is made BEFORE the walk; here the count is only
#: known after it, so declining a small record means walking the chain a SECOND time to
#: emit scalar. On PlasticSubstance003, 148 of 181 records draw fewer than 32 patterns, so
#: a threshold of 32 would double-walk 82% of them to save the stacking of 900 patterns.
#: The only refusal left is a table that cannot be batched at all, which `batch_reads`
#: answers before the walk starts.


_CACHE_READ = re.compile(r"cache_read\((\d+)\)")
_CACHE_WRITE = re.compile(r"cache_write\([^,]+,\s*(\d+)\)")


def _prog_source(asm, ptr):
    """The program's transpiled Python source, from `ops`' own memo, or None."""
    import ops

    try:
        return ops._source(asm, ptr)
    except Exception:
        return None


def batch_reads(asm, run, nodes, table):
    """The slots the entry parameters read, or None if the table cannot be batched.

    WHAT THE CHAIN CARRIES AND WHAT THE TABLE DOES NOT. A gate's `switch` is a scanner: it
    reads slots 18/20/21/22 and writes 16/18/20/21/22/25, so emission k's frame is a
    function of emission k-1's and the chain has to be walked one pattern at a time. The
    ENTRY parameters are the other kind -- they read the frame and write no slot back --
    which makes each of them a pure function of ($number, frame) and lets ONE evaluation
    over m rows answer for m patterns.

    THE 0x03/0x06 CACHE IS THE SECOND STATE CHANNEL and it is not visible to `run.flow`,
    which reports slots only. 164 of 181 records on PlasticSubstance003 have an entry
    parameter that calls `cache_write`, so refusing them all would leave this path
    switched off for 91% of the population. The writes themselves are reproducible --
    the scalar walk leaves the LAST pattern's value at the index and `_collapse_cache`
    puts exactly that there -- so what has to be refused instead is a cache index that is
    both WRITTEN by an entry parameter and READ by anything that runs against a different
    pattern than the write: a chain program (which the batched path now runs entirely
    BEFORE the table rather than interleaved with it) or another entry parameter (which
    under the scalar walk would read pattern k-1's write, a loop-carried dependence the
    batch flattens). Indices are literals in the transpiled call, so they are read off it.

    `None` means "run the scalar walk", never "run something approximate".
    """
    flow = getattr(run, "flow", None)
    if flow is None:
        return None
    reads, written = set(), set()
    writes_idx, reads_idx = set(), set()
    # A SLOT AN ENTRY PARAMETER WRITES FOR ITS SIBLINGS IS NOT STATE. The Tile Sampler
    # template's `opacity` program computes the pattern's shared values once and stores
    # them in slots 26-31 for `frameoffset`, `patternsize` and `patternrotation` -- the
    # same pattern's, evaluated after it in the table's order. 498 of 5,140 records over
    # 80 files carry that shape, and refusing every write sent them all down the scalar
    # walk (FabricSubstance009: ten records of 147,456 patterns at 92 s each, 600 s
    # before its one refusal). The write is loop-carried only if something reads the
    # slot BEFORE the writer in an emission -- a chain program, or an entry parameter at
    # or before the writer's position (its own read-before-write included, which is what
    # `flow` reports as a read) -- and those are refused as before. What the batch then
    # does is what the walk does: one frame through the table in order, the writer's
    # (m, C) column read by the parameters after it.
    for _o, _t, params in table:
        for _n, (kind, value) in fxrender.in_eval_order(params):
            if kind == "baked" or not value:
                continue
            src = _prog_source(asm, value)
            if src is None:
                return None
            try:
                r, w = flow(value)
            except Exception:
                return None
            if w & reads or w & r:
                return None
            if w and assume.assumed("fx.batchwrites", "sibling") != "sibling":
                return None
            reads |= r
            written |= w
            writes_idx |= {int(x) for x in _CACHE_WRITE.findall(src)}
            reads_idx |= {int(x) for x in _CACHE_READ.findall(src)}
    for _o, _h, ps in nodes:
        for value in ps.values():
            if not value:
                continue
            src = _prog_source(asm, value)
            if src is None:
                return None
            reads_idx |= {int(x) for x in _CACHE_READ.findall(src)}
            if written:
                try:
                    r, _w = flow(value)
                except Exception:
                    return None
                if r & written:
                    return None
    if reads_idx & writes_idx:
        return None
    # The frames need only what the chain supplies; a slot the table writes before it
    # reads it is the table's own.
    return reads - written


def _collapse_cache(cache, before, m):
    """Leave the LAST pattern's value at every index the batch wrote, as the walk would.

    A batched `cache_write` stores an (m, C) column where the scalar walk stored one row
    per pattern and left the last. The cache holds one value per index for a LATER RECORD
    to read back, so an m-row array there is not a faster answer, it is a different one.
    """
    if m < 2:
        return
    for k, v in list(cache.items()):
        if before.get(k) is v:
            continue
        a = np.asarray(v)
        if a.ndim == 2 and a.shape[0] == m:
            cache[k] = a[-1:]


def _stack(frames, keys, m):
    """The m recorded frames as one {slot: (m, C)} frame, or None if they do not stack.

    A slot nothing rewrote between emissions is the SAME ARRAY OBJECT in every frame, so
    it is passed through at its own width instead of being tiled to m identical rows --
    which is most of them, and the difference is the whole memory cost of this path.
    """
    out = {}
    for k in keys:
        col = []
        for f in frames:
            v = f.get(k)
            if v is None:
                return None
            col.append(v)
        first = col[0]
        if all(v is first for v in col):
            out[k] = first
            continue
        try:
            rows = [np.asarray(v).reshape(1, -1) for v in col]
            if len({r.shape[1] for r in rows}) != 1:
                return None
            out[k] = np.concatenate(rows, axis=0)
        except Exception:
            return None
    return out


def emissions(rec, run, slots, cache=None):
    """[{parameter: value}] for every pattern the record draws, in emission order.

    THE CHAIN IS WALKED ONCE PER PATTERN AND THE TABLE IS EVALUATED ONCE. Those are two
    different costs and only one of them is sequential. A gate's `switch` carries state --
    it reads the slots it writes, so pattern k's frame is pattern k-1's advanced -- and no
    reordering of the walk is available. The entry parameters carry none: they read the
    frame and write nothing, so one run of the same program over an (m, 1) `$number`
    against the m frames the walk recorded gives the same m answers it gave one at a time.
    See `batch_reads` for how "carries none" is decided and `_batch_emit` for the run.

    The scalar path is unchanged and is still the arbiter: anything the batched one cannot
    stack falls back to it FROM THE FRAME THE WALK STARTED WITH, so a refusal costs a
    re-walk and never an approximation.
    """
    # THE CHAIN AS A TREE, behind `fx.chain`. Decided before the table is asked for,
    # because a record this arm applies to has leaves the list walk's table never
    # reaches, and before the seeding, because those leaves' programs are in
    # `rec.programs` and would otherwise be run as the record's prologue.
    if fxchain.active(rec):
        got = fxchain.emissions(rec, run, slots)
        assume.note(rec.index)
        return got
    nodes = fxrender.chain(rec)
    table = fxrender.entries(rec)
    if not table:
        raise Unsupported(
            "fxmaps: no emittable entries -- %s" % fxrender.why_no_entries(rec)
        )
    for _off, hdr, _p in nodes:
        if not _known_node(hdr):
            raise Unsupported("fxmaps: node header %#x is not modelled" % hdr)

    # THE RECORD'S OWN PROGRAMS SEED THE FRAME. The chain's programs read constants the
    # record's prologue writes, so running only the chain leaves better than half of all
    # records failing on "slot N read but never set".
    fx_progs = {p for _o, _h, ps in nodes for p in ps.values() if p}
    for _o, _t, params in table:
        for _k, (kind, value) in params.items():
            if kind != "baked" and value:
                fx_progs.add(value)
    for prog in sorted(set(rec.programs) - fx_progs):
        try:
            run(prog, slots, 0)
        except Exception:
            pass

    reads = batch_reads(rec.asm, run, nodes, table)
    # QUADRANT SUBDIVISION, behind `fx.subdivide`. The `tree` arm reads the entry cells
    # as a nesting and returns `fxtree.Batch` objects -- one per cell, m patterns each --
    # which `splat` draws as grids. Everything above this line is shared: the same chain,
    # the same table, the same seeding, the same answer about whether the table batches.
    # See `fxtree` for what is established and what the arm leaves open.
    how = assume.assumed("fx.subdivide", "flat")
    if how == "tree" or (how == "noise") == white_noise_record(rec, table) and how in ("noise", "quadrant"):
        return fxtree.emissions(rec, run, slots, nodes, table, reads, cache)
    if reads is not None:
        seed = dict(slots)
        frames, closed = _walk(rec, run, slots, nodes, table, reads)
        got = _batch_emit(run, table, frames, reads, cache)
        if got is not None:
            if not got and not closed:
                raise Unsupported("fxmaps: emitted no patterns and no gate closed")
            return got
        # THE FRAMES WOULD NOT STACK. Restore the frame the walk started from: the chain
        # has been driven and its writes are in `slots`, so re-walking without this would
        # start pattern 0 on pattern N's state.
        slots.clear()
        slots.update(seed)

    out, closed = _walk(rec, run, slots, nodes, table, None)
    if not out and not closed:
        raise Unsupported("fxmaps: emitted no patterns and no gate closed")
    return out


def _batch_emit(run, table, frames, reads, cache=None):
    """Every recorded frame's patterns, one evaluation per entry parameter, or None.

    ZERO FRAMES IS AN ANSWER, NOT A REFUSAL, and the two paths disagreed about it. A gate
    that closes before the first pattern leaves the walk with no frames at all; the scalar
    path returns `[]` for that and `emissions` accepts it, because `closed` is true. The
    batched path reached `_stack` with an empty column list and raised `IndexError` on
    `col[0]` -- not a refusal that falls back, an exception that escaped `emissions`
    entirely and failed the record.

    It is a REGRESSION AND IT IS DATED. `e231131` made `fx_walk` follow both of a cell's
    forward pointers; on `ChesterfieldSofa` record 321 that takes the chain from
    `[0x18b, 0x89]` to `[0x18b, 0x89, 0x89, 0x89]` and the entry table from 9 rows to 11,
    and one of the two new gates closes at pattern 0. Before `e231131`: 881/881 records,
    0 failures. After: 858/881, 23 failures, and `basecolor` and `roughness` stop being
    scored at all -- 4 of the 10 channels `777e597` tabulated. Nothing caught it because
    `test_render2.REFERENCE_FLOOR` covers Rokviz only and `test_filters.REFERENCE_FLOOR`
    is scored through `render.py`, which does not run this code.

    The fix is the one that makes the two paths agree rather than the one that makes the
    symptom go away: the batched path's own docstring says the scalar walk is the arbiter
    and that anything the batch cannot do falls back to it. On m = 0 the arbiter says `[]`.
    """
    m = len(frames)
    if m == 0:
        return []
    numbers = np.array([n for n, _f in frames], dtype=np.float64)
    stacked = _stack([f for _n, f in frames], sorted(reads), m)
    if stacked is None:
        return None
    before = dict(cache) if cache is not None else {}
    cols = []
    # ONE FRAME THROUGH THE TABLE, as the scalar walk's `emit` has: a parameter that
    # writes a slot for the parameters after it (`batch_reads` admits exactly those)
    # leaves an (m, C) column the later ones read. Nothing outside the table sees it.
    frame = dict(stacked)
    for _o, tag, params in table:
        per = {"patterntype": fx_patterntype(tag), "_tag": tag}
        wide = {}
        for name, (kind, value) in fxrender.in_eval_order(params):
            if value is None:
                continue
            if kind != "baked":
                a = np.asarray(run(value, frame, numbers, flatten=False))
                # ROWS ARE PATTERNS ONLY WHEN THERE ARE m OF THEM. A program reading
                # neither `$number` nor a stacked slot returns ONE row however wide, and
                # that row is one value's components, not a per-pattern column.
                if a.ndim == 0:
                    a = a.reshape(1, 1)
                elif a.ndim == 1:
                    a = a[:, None] if a.shape[0] == m else a[None, :]
                if a.shape[0] not in (1, m):
                    return None
                wide[name] = a
            elif isinstance(value, np.ndarray):
                per[name] = value
            else:
                per[name] = np.asarray(value, dtype=np.float32).ravel()
        cols.append((per, wide))
    if cache is not None:
        _collapse_cache(cache, before, m)
    out = []
    for j in range(m):
        for per, wide in cols:
            got = dict(per)
            for name, a in wide.items():
                got[name] = a[j] if a.shape[0] == m else a[0]
            out.append(got)
    return out


def _walk(rec, run, slots, nodes, table, collect):
    """Drive the chain. `collect` is the slot set to record per pattern, or None to emit.

    Returns (patterns or (number, frame) pairs, whether a gate closed a branch).
    """
    out = []
    closed = [False]
    ran_once = set()

    def emit(number):
        if collect is not None:
            out.append((float(number), {k: slots[k] for k in collect if k in slots}))
            return
        for _o, tag, params in table:
            got = {"patterntype": fx_patterntype(tag), "_tag": tag}
            for name, (kind, value) in fxrender.in_eval_order(params):
                if value is None:
                    continue
                if kind != "baked":
                    got[name] = run(value, slots, number)
                elif isinstance(value, np.ndarray):
                    got[name] = value
                else:
                    got[name] = np.asarray(value, dtype=np.float32).ravel()
            out.append(got)

    # THE BUDGET IS COUNTED IN PATTERNS IN BOTH ARMS. `emit` appends one dict per TABLE
    # ENTRY when it is emitting and one per EMISSION when it is recording frames, so
    # `len(out)` is the pattern count only in the first case. Left as `len(out)`, a record
    # with four entries would be refused at the same budget scalar and allowed four times
    # as many patterns batched -- a runtime bound that moved with an optimisation.
    per_emission = 1 if collect is None else max(len(table), 1)

    def walk(i, number, mode):
        if len(out) * per_emission > MAX_PATTERNS:
            raise Unsupported("fxmaps: more than %d patterns" % MAX_PATTERNS)
        if i == len(nodes):
            emit(number)
            return
        _off, hdr, progs = nodes[i]
        # See `fxnodes`: `role` is the header's reading under `fx.nodemodel`, and the arms
        # below are what a role DOES, unchanged from when each tested the header itself.
        role = fxnodes.role(hdr)
        if role == "count":
            prog = progs.get("numberadded")
            if prog is None:
                raise Unsupported("fxmaps: addnode with no numberadded program")
            if "randomseed" in progs and progs["randomseed"] is not None:
                run(progs["randomseed"], slots, number)
            _c = float(np.asarray(run(prog, slots, number)).ravel()[0])
            # A NON-FINITE COUNT IS ZERO PATTERNS: the count program divided 0/0 (a size read
            # as 0 upstream) and the texture rule writes 0 (`nonfinite.fill`); six corpus
            # files raised `cannot convert float NaN to integer` here.
            raw = int(round(_c)) if np.isfinite(_c) else 0
            if not 0 <= raw <= MAX_PATTERNS:
                raise Unsupported("fxmaps: numberadded = %d" % raw)
            n, mode = emission_count(rec, raw)
            if mode != "chain":
                assume.note(rec.index)
            for k in range(n):
                walk(i + 1, k, mode)
            return
        if role == "gate":
            prog = progs.get("switch")
            if prog is None:
                raise Unsupported("fxmaps: markov2 with no switch program")
            if mode == "placement":
                # HELD TO ONE RUN under a stated count, for the same reason the scanner is:
                # the placement program already carries this pattern's position, and the
                # gate's spiral would add a second one -- re-driving it per emission walks
                # every stamp off the canvas (Rokviz record 6: mask mean 0.279 against the
                # 0.503 its own arithmetic predicts). Its predicate is not consulted
                # either: it bounds a spiral, and under a stated count there is no spiral.
                if i not in ran_once:
                    ran_once.add(i)
                    run(prog, slots, number)
                walk(i + 1, number, mode)
                return
            if bool(np.asarray(run(prog, slots, number)).ravel()[0]):
                walk(i + 1, number, mode)
            else:
                closed[0] = True
            return
        if role == "state":
            prog = progs.get(None)
            if prog is not None and (mode == "chain" or i not in ran_once):
                ran_once.add(i)
                run(prog, slots, number)
            walk(i + 1, number, mode)
            return
        if role in ("branch", "leaf", "link"):
            walk(i + 1, number, mode)
            return
        raise Unsupported("fxmaps: node header %#x is not modelled" % hdr)

    # THE LEAF'S UPPER BITS ARE THE BAKED EMISSION COUNT. `leaf_successor` left them open
    # ("0xC0B, 0x510B, 0x1B90B, 0x3C10B, 0xE100B and eleven more"): they are 12, 81, 441,
    # 961, 3600 -- 9^2, 21^2, 31^2, 60^2 -- the Iterate node's Number, written into the
    # header when the source baked it. Corpus-wide 1,635 leaf nodes carry one; every reader
    # that names a count independently agrees where the layout is square (`grid_width` 287
    # of 287, `number_grid` 134 of 134), and where it is not the header holds the product
    # the readers cannot (0x770B = 119 = 7 x 17 rows under a `floor($number / 7)`
    # placement; 589 = 19 x 31; 143 = 13 x 11). The leaf is not in `nodes` -- it names no
    # program -- so the count is read off the walk. 1,371 leaf-only chains emitted ONE
    # pattern of theirs: RoofTiles 2194 drew one row line of 119 and 2201 one tile of 25.
    # A chain with a count node keeps that node's count (264 chains; the leaf's agrees
    # where both can be read). The arm is `fx.leafcount`.
    n = leaf_count(rec) if not any(fxnodes.role(h) == "count" for _o, h, _p in nodes) else 0
    if n > 0 and assume.assumed("fx.leafcount", "header") == "header":
        if n > MAX_PATTERNS:
            raise Unsupported("fxmaps: leaf count = %d" % n)
        assume.note(rec.index)
        for k in range(n):
            walk(0, k, "chain")
    else:
        walk(0, 0, "chain")
    return out, closed[0]


def white_noise_record(rec, table):
    """Is this the library's 16-px White Noise: a root offset cell, bare Quadrants, and one
    leaf whose only parameter is an opacity program?

    THE FLAT ARM DRAWS THIS RECORD AS A CONSTANT -- one pattern, one `rand(1)` -- and
    Bricks 7660 came out 0.922 flat where the tree walk gives white noise (mean 0.49, sd
    0.287; 9924, the same record, calibrated the tree's region convention at 0.513 /
    0.292 / lag-1 -0.012). It is the source of every per-tile tone in graph 002 (the
    gradient ladder 7667-7709 maps it) and the corpus carries ~1,300 of them in 100+
    files, all 16 x 16. `fx.subdivide = noise` sends this class down the tree walk and
    nothing else; `tree` sends every Quadrant record, `flat` none. `noise` is an ARM:
    the tone ladder above it lands the tiles 0.07 darker than the export where the flat
    arm's accidental constant lands them 0.05 brighter, so the ratchet and the companion
    both refuse it (FORMAT-NOTES.md, "The White Noise class").
    """
    if not (rec.width == 16 and rec.height == 16):
        return False
    try:
        cells, order, roots = fxtree.cells_of(rec, table)
    except Exception:
        return False
    if len(order) < 3:
        return False
    leaves = [o for o in order if not any(cells[o].kids)]
    if len(leaves) != 1:
        return False
    for o in order:
        c = cells[o]
        if o == leaves[0]:
            if set(c.params) != {"opacity"} or c.params["opacity"][0] != "program":
                return False
        elif o in roots:
            if set(c.params) - {"branchoffset"}:
                return False
        elif c.params:
            return False
    return True


def leaf_count(rec):
    """`header >> 8` of the record's leaf node (nibble B, mask bits clear), or 0."""
    try:
        for item in rec.fx_walk():
            if item[0] == "node" and (item[2] & 0xFF) == 0x0B:
                return int(item[2]) >> 8
    except Exception:
        return 0
    return 0


def _known_node(hdr):
    return fxnodes.known(hdr)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

_ZERO2 = np.zeros(2, np.float32)
_ONE2 = np.ones(2, np.float32)
_ONE1 = np.ones(1, np.float32)

#: The smallest patternsize component that is a size rather than a misread. The corpus
#: leaves a gap here: nothing between 1e-30 and 1e-06.
MIN_SIZE = 1e-6


def _cell(patterns):
    """1 / (cells per axis), read from the branchoffset span, or None.

    A cell-unit offset walks WHOLE cells, so its values are integers and its span is one
    less than the cell count. That is a property of the emissions alone -- no count, no
    square test -- which is what makes it usable where round(sqrt(N)) was not: a jittered
    scatter can span an integer, but it cannot put every emission on a lattice point.
    """
    if not patterns:
        return None
    # A subdivided cell arrives as an `fxtree.Batch`, whose centres already carry the
    # region's branchoffset; the cell-unit reading is a property of the flat walk's
    # dicts and is not asked of a batch.
    if any(not isinstance(q, dict) for q in patterns):
        return None
    b = [
        np.asarray(q.get("branchoffset"), np.float64).ravel()
        for q in patterns
        if q.get("branchoffset") is not None
    ]
    if len(b) != len(patterns) or not b:
        return None
    w = max(x.size for x in b)
    a = np.array([np.pad(x, (0, w - x.size)) for x in b])
    d = []
    for k in range(min(2, a.shape[1])):
        col = a[:, k]
        sp = float(col.max() - col.min())
        ok = (
            sp >= 1
            and abs(sp - round(sp)) < 1e-4
            and bool(np.all(np.abs(col - np.round(col)) < 1e-4))
            and len({round(float(t), 6) for t in col}) == round(sp) + 1
        )
        d.append(1.0 / (round(sp) + 1.0) if ok else 1.0)
    if not any(x != 1.0 for x in d):
        return None
    while len(d) < 2:
        d.append(1.0)
    return np.asarray(d, np.float32)


def _mode_for(tag, mode):
    """The combine one pattern draws under: `mode`, or per cell under `bit18`.

    `bit18` reads the entry tag: bit 18 set is `max`, clear is signed `add`. Over the
    permitted paired sources that bit is set on exactly the entries whose `paramset`
    declares a `blendingmode` and clear where none is declared -- see `assume.QUESTIONS`
    and FORMAT-NOTES.md, "Graph 001's first annihilation point is a white canvas the file
    states". A pattern with no tag (a synthetic one) is drawn by `max`.
    """
    if mode != "bit18":
        return mode
    if tag is None:
        return "max"
    return "max" if (int(tag) >> 18) & 1 else "add"


def _combine(dst, src, mode=None):
    if mode is None:
        mode = assume.assumed("fx.combine", "max")
    if mode == "add":
        return dst + src
    if mode == "over":
        a = np.clip(np.abs(src), 0.0, 1.0)
        return dst * (1.0 - a) + src
    return np.maximum(dst, src)


def _blend(dst, src, mode, where):
    """`_combine` written INTO `dst`, under a mask, without gathering the tile.

    The line this replaces was `tile[hit] = _combine(tile[hit], src[hit])`, which is three
    fancy-index passes over the tile -- a gather of the destination, a gather of the
    source, and a scatter back -- where a `where=`-guarded ufunc is one. It is the whole
    cost of drawing: 802 million pixel-evaluations go through here on one 256px render of
    PlasticSubstance003, against a canvas of six million, because the patterns overlap
    about 130-fold.

    The values are the same ones `_combine` computes, at the same positions, in the same
    order -- `where` suppresses the write, it does not change the arithmetic -- so this is
    an equality, not an approximation. It is A/B'd against the gathering form by toggling
    `fx.BLEND_IN_PLACE`.
    """
    if mode == "add":
        np.add(dst, src, out=dst, where=where)
        return
    if mode == "over":
        a = np.clip(np.abs(src), 0.0, 1.0)
        np.copyto(dst, dst * (1.0 - a) + src, where=where)
        return
    np.maximum(dst, src, out=dst, where=where)


#: Toggle for the paragraph above, so the two forms can be measured in ONE process against
#: one set of patterns. Off restores the gathering form exactly.
BLEND_IN_PLACE = True

#: Second toggle, for `_coverage` and the 1-D sample grids. Off sends every tile back
#: through `fxrender.profile_value` on 2-D `dx`/`dy`, which is what this replaces.
FAST_RASTER = True


def _coverage(lx, ly, prof):
    """`fxrender.profile_value`, with the redundant `inside` mask dropped where it is one.

    `profile_value` closes every profile with a multiply by `inside`, the |lx|,|ly| <= 0.5
    box. For the profiles below the multiply cannot change a value: each one ends in a
    `clip(..., 0, 1)` whose argument is already <= 0 outside the box, so the sample is zero
    there with or without the mask, and inside the box the mask is 1.

        bell, paraboloid    zero once r >= 1, and 4lx^2 + 4ly^2 < 1 implies |lx|, |ly| < 0.5
        pyramid             zero once max(|2lx|, |2ly|) >= 1, which IS the box

    So this is an equality over every input, not a fast approximation, and it saves the
    two absolutes, the two comparisons, the `and`, the `astype` and the multiply -- seven
    of the seventeen passes `bell` makes over a tile, on the 94% of patterns that ARE bell.
    NOT extended to `gaussian` (its exponential is nonzero everywhere), `gradation` (a ramp
    in x alone, unbounded in y) or `capsule` (bounded in y only), which keep the mask by
    going through `profile_value` unchanged.

    The `sqrt` is deliberately kept even where the result is immediately squared: `r * r`
    is not bit-identical to the sum under it, and this function is held to equality.
    """
    if not FAST_RASTER:
        return fxrender.profile_value(lx, ly, prof)
    if prof == "bell":
        r = np.sqrt((2.0 * lx) ** 2 + (2.0 * ly) ** 2)
        t = np.clip(1.0 - r * r, 0.0, 1.0)
        return (t * t).astype(np.float32)
    if prof == "paraboloid":
        r = np.sqrt((2.0 * lx) ** 2 + (2.0 * ly) ** 2)
        return np.clip(1.0 - r * r, 0.0, 1.0).astype(np.float32)
    if prof == "pyramid":
        c = np.maximum(np.abs(2.0 * lx), np.abs(2.0 * ly))
        return np.clip(1.0 - c, 0.0, 1.0).astype(np.float32)
    return fxrender.profile_value(lx, ly, prof)


def splat(rec, patterns, W, H, images=None, header=None):
    """Draw the emitted patterns onto a W x H canvas.

    `header` is `header_fields`' reading of the record's own w1 fields, or None: under
    `fx.header=read` the canvas starts at its `background` and every pattern's opacity is
    multiplied by its `opacitymult`; `hurst` reaches only the tree arm's grid draw, where
    a pattern has a depth (`fxtree.draw`).
    """
    nchan = 4 if rec.colour else 1
    canvas = np.zeros((H, W, nchan), np.float32)
    if header is not None and header.get("background") is not None:
        bg = np.asarray(header["background"], np.float32).ravel()
        if bg.size < nchan:
            bg = np.repeat(bg[:1], nchan)
        canvas[...] = bg[:nchan]
    opmul = None
    if header is not None and header.get("opacitymult") is not None:
        opmul = np.float32(header["opacitymult"])
    # ONE ROW AND ONE COLUMN, NOT TWO FULL GRIDS. `pxg` never varied down a column nor
    # `pyg` across a row, so the mgrid pair spent H*W building W + H distinct numbers and
    # every tile then subtracted its centre out of a 2-D slice. The broadcast below
    # produces the same float32 values in the same order.
    if FAST_RASTER:
        pxg = (np.arange(W, dtype=np.float32) + 0.5) / W - 0.5
        pyg = (np.arange(H, dtype=np.float32) + 0.5) / H - 0.5
    else:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        pxg = (xx + 0.5) / W - 0.5
        pyg = (yy + 0.5) / H - 0.5

    forced = assume.assumed("fx.profile")
    # ONCE PER RECORD. `_combine` asked `assume` for this on every tile it drew.
    mode = assume.assumed("fx.combine", "max")
    cell = None
    for key in ("fx.branchoffset", "fx.patternsize", "fx.frameoffset"):
        if assume.assumed(key) == "cell":
            cell = _cell(patterns)
            break
    base_scale = cell if assume.assumed("fx.branchoffset") == "cell" else None
    size_scale = cell if assume.assumed("fx.patternsize") == "cell" else None
    frame_scale = cell if assume.assumed("fx.frameoffset") == "cell" else None
    sizeless = assume.assumed("fx.sizeless", "fill")
    skip_root = assume.assumed("fx.rootentry") == "skip"
    skip_markers = assume.assumed("fx.markers", "skip") == "skip"
    neg = assume.assumed("fx.negopacity", "signed")
    wrap_centre = assume.assumed("fx.centre", "reach") == "wrap"
    if wrap_centre:
        assume.note(rec.index)
    rot_cw = assume.assumed("fx.rotation", "ccw") == "cw"
    if rot_cw:
        assume.note(rec.index)

    def val(pat, name, default):
        v = pat.get(name)
        return (
            np.asarray(default, np.float32)
            if v is None
            else np.asarray(v, np.float32).ravel()
        )

    # A SUBDIVIDED CELL ARRIVES AS ONE `fxtree.Batch` OF m PATTERNS and is drawn as one
    # pass. `over` is the one combine that pass cannot express -- it is order-dependent --
    # so under that arm a batch is expanded to the per-pattern dicts the loop below
    # draws, within the flat budget.
    if mode == "over" and any(isinstance(p, fxtree.Batch) for p in patterns):
        expanded = []
        for p in patterns:
            expanded.extend(p.as_dicts() if isinstance(p, fxtree.Batch) else [p])
            if len(expanded) > MAX_PATTERNS:
                raise Unsupported(
                    "fxmaps: fx.combine=over draws per pattern, over %d" % MAX_PATTERNS
                )
        patterns = expanded

    for p in patterns:
        if isinstance(p, fxtree.Batch):
            fxtree.draw(canvas, p, W, H, images=images, header=header)
            continue
        tag = p.get("_tag")
        pmode = _mode_for(tag, mode)
        if skip_markers and tag is not None and (int(tag) & 0xFF) == 0x08:
            continue
        if p.get("patternsize") is None and p.get("patterntype") is None:
            b = np.asarray(p.get("branchoffset", _ZERO2), np.float64).ravel()
            if skip_root and b.size >= 2 and not np.any(np.abs(b[:2]) > 1e-6):
                continue
            if sizeless == "skip":
                continue
            if sizeless in ("half", "quarter"):
                p = dict(p)
                p["patternsize"] = np.full(
                    2, 0.5 if sizeless == "half" else 0.25, np.float32
                )
        src = _image_for(p, images)
        base = val(p, "branchoffset", _ZERO2)
        off = val(p, "frameoffset", _ZERO2)
        size = val(p, "patternsize", _ONE2)
        if base_scale is not None:
            base = base * base_scale[: base.size]
        if frame_scale is not None:
            off = off * frame_scale[: off.size]
        if size_scale is not None:
            size = size * size_scale[: size.size]
        if size.size < 2:
            size = np.repeat(size[:1], 2)
        if base.size < 2:
            base = np.repeat(base[:1], 2)
        if off.size < 2:
            off = np.repeat(off[:1], 2)
        sx, sy = float(size[0]), float(size[1])
        cx, cy = float(base[0] + off[0]), float(base[1] + off[1])
        if not (
            math.isfinite(sx)
            and math.isfinite(sy)
            and math.isfinite(cx)
            and math.isfinite(cy)
        ):
            continue
        if sx <= 0 or sy <= 0 or max(sx, sy) > 64.0 or min(sx, sy) < MIN_SIZE:
            continue
        col = val(p, "opacity", _ONE1)
        if col.size < nchan:
            col = np.repeat(col[:1], nchan)
        if neg == "signed":
            col = np.clip(col[:nchan], -1.0, 1.0)
        elif neg == "abs":
            col = np.clip(np.abs(col[:nchan]), 0.0, 1.0)
        else:
            col = np.clip(col[:nchan], 0.0, 1.0)
        if opmul is not None:
            col = col * opmul

        if wrap_centre:
            # THE CANVAS IS A TORUS. A pattern placed at x = 2.0 is at x = 0: the row
            # stagger of RoofTiles record 7 is `branchoffset` x = 0, 0.5, 1.0, 1.5, 2.0 ...
            # for rows 0, 1, 2, ..., one full-width stripe each, and under the bounded
            # neighbour copies below (`reach`) everything past the second row fell off the
            # canvas. Wrapping the centre first leaves every pattern the copies already
            # reached exactly where it was.
            cx = (cx + 0.5) % 1.0 - 0.5
            cy = (cy + 0.5) % 1.0 - 0.5
        rot = float(val(p, "patternrotation", np.zeros(1, np.float32))[0])
        if not math.isfinite(rot):
            rot = 0.0  # the texture rule: a non-finite rotation program wrote 0
        th = 2.0 * math.pi * rot
        if rot_cw:
            th = -th
        ct, st = math.cos(th), math.sin(th)
        prof = forced if forced is not None else _profile_for(p)
        hx = 0.5 * (sx * abs(ct) + sy * abs(st))
        hy = 0.5 * (sx * abs(st) + sy * abs(ct))
        reach = int(min(3, math.ceil(max(sx, sy))))
        txlo = max(-reach, math.ceil(-0.5 - cx - hx))
        txhi = min(reach, math.floor(0.5 - cx + hx))
        tylo = max(-reach, math.ceil(-0.5 - cy - hy))
        tyhi = min(reach, math.floor(0.5 - cy + hy))
        for ty in range(tylo, tyhi + 1):
            for tx in range(txlo, txhi + 1):
                ux, uy = cx + tx, cy + ty
                c0 = max(math.floor((ux - hx + 0.5) * W - 0.5), 0)
                c1 = min(math.ceil((ux + hx + 0.5) * W - 0.5), W - 1)
                r0 = max(math.floor((uy - hy + 0.5) * H - 0.5), 0)
                r1 = min(math.ceil((uy + hy + 0.5) * H - 0.5), H - 1)
                if c0 > c1 or r0 > r1:
                    continue
                if FAST_RASTER:
                    dx = (pxg[c0 : c1 + 1] - ux)[None, :]
                    dy = (pyg[r0 : r1 + 1] - uy)[:, None]
                else:
                    dx = pxg[r0 : r1 + 1, c0 : c1 + 1] - ux
                    dy = pyg[r0 : r1 + 1, c0 : c1 + 1] - uy
                lx = (dx * ct + dy * st) / sx
                ly = (-dx * st + dy * ct) / sy
                if prof in ("rect", "square"):
                    hit = (np.abs(lx) <= 0.5) & (np.abs(ly) <= 0.5)
                    cov = None
                else:
                    cov = _coverage(lx, ly, prof)
                    hit = cov > 0
                if not hit.any():
                    continue
                tile = canvas[r0 : r1 + 1, c0 : c1 + 1]
                if src is None:
                    if cov is None and hit.all():
                        tile[...] = _combine(tile, col, pmode)
                    elif BLEND_IN_PLACE:
                        _blend(
                            tile,
                            col if cov is None else col * cov[:, :, None],
                            pmode,
                            hit[:, :, None],
                        )
                    else:
                        tile[hit] = _combine(
                            tile[hit], col if cov is None else col * cov[hit, None], pmode
                        )
                    continue
                uv = np.stack([lx[hit] + 0.5, ly[hit] + 0.5], axis=-1)
                got = np.asarray(sampler(src)(uv), np.float32)
                if got.ndim == 1:
                    got = got[:, None]
                if got.shape[-1] < nchan:
                    got = np.repeat(got[:, :1], nchan, axis=-1)
                tile[hit] = _combine(
                    tile[hit],
                    got[:, :nchan] * col
                    if cov is None
                    else got[:, :nchan] * col * cov[hit, None],
                    pmode,
                )
    return np.clip(canvas, 0.0, 1.0)


def header_fields(ctx, v):
    """{background, hurst, opacitymult} from the record's own w1 fields, or None.

    None under `fx.header=ignore`, the default, which draws as before. Under `read` each
    named field is its baked value, or its program evaluated once at the record's declared
    size (`Context.run`), or absent. `background` comes back as a (nchan,) vector, the two
    scalars as floats. A program that does not evaluate leaves its field absent and marks
    the record low-confidence rather than refusing it: the field was ignored outright
    until now, and a draw that falls back to that is not worse than the draw it replaces.
    """
    if assume.assumed("fx.header", "read") != "read":
        return None
    nchan = 4 if v.colour else 1
    out = {}
    for name, width in (("background", nchan), ("hurst", 1), ("opacitymult", 1)):
        p = v.params.get(name)
        if p is None:
            continue
        if p.kind == "baked":
            vals = np.asarray(p.value, np.float32).ravel()
        else:
            try:
                vals = np.asarray(ctx.run(v, p.value, 1), np.float32).ravel()
            except Exception:
                ctx.low_confidence.add(v.index)
                continue
        if vals.size == 0:
            continue
        if width == 1:
            out[name] = float(vals[0])
        else:
            out[name] = vals[:width] if vals.size >= width else np.repeat(vals[:1], width)
    if out:
        assume.note(v.index)
    return out


def _profile_for(p):
    t = p.get("patterntype")
    if t is None:
        return assume.assumed("fx.typeless_profile", "rect")
    return fxrender.PATTERN_SHAPES.get(t, "rect")


def _image_for(p, images):
    """The image a pattern stamps, or None to draw a generated profile instead.

    WHERE THERE IS EXACTLY ONE CANDIDATE, AN ABSENT INDEX IS NOT AN ABSENT IMAGE. `splat`'s
    docstring refuses to fall back to "the first available image" when `imageindex` is
    missing, and that refusal is right for the records it was written about: 133 records
    index 0 while carrying SIX edges and 27 index 1 while carrying THREE, so the index runs
    over some narrower subset of the edges and picking the first would sample the wrong
    input. That is a real ambiguity and it is still declined below.

    It is not an ambiguity when the record supplies ONE image. There is no wrong input to
    choose, and the corpus says the file itself reasons this way: over 437 corpus files plus
    the 8 pack assemblies, 1,409 of 1,409 entries with a STATED `imageindex` sit on a record
    with two or more wired edges, and 0 of 2,652 one-edge entries state one. THE FILE STATES
    THE INDEX EXACTLY WHERE THERE IS A CHOICE. An entry that omits it on a one-edge record
    is not incomplete; it is naming the only input it has.

    This is the other half of the `imageindex` correction, and without it the first half
    changes no pixel. `ce5897e` traced Chesterfield's 10-14 cycle excess to record 43
    resolving `imageindex` to `opacity`'s own address, giving 1.0 -- out of range for a
    one-edge record -- so the pattern fell back to a full-canvas fill and the record rendered
    SOLID WHITE. Suppressing that bogus value in `fxrender._recover_last_inline` leaves
    `imageindex` absent, and an absent index took the SAME fallback: the render came back
    bit-identical on all six channels. The value had to be suppressed AND the one-edge case
    read for the white to go away.
    """
    if not images:
        return None
    v = p.get("imageindex")
    if v is None:
        if len(images) == 1:
            return next(iter(images.values()))
        return None
    try:
        idx = int(round(float(np.asarray(v, dtype=float).ravel()[0])))
    except Exception:
        return None
    return images.get(idx)


def render_fxmaps(ctx, v):
    """One `fxmaps` record: emit its patterns and draw them."""
    W, H = v.size(ctx.cap)
    rec = v.rec
    saved = dict(sbsruntime.SAMPLERS)
    sbsruntime.SAMPLERS.clear()
    # `rand` as a stream, per record: see `sbsruntime.rand` and `assume.QUESTIONS`.
    sbsruntime.CONTEXT["stream"] = assume.assumed("rand.draws", "hash") == "stream"
    sbsruntime.CONTEXT["draw"] = 0
    if sbsruntime.CONTEXT["stream"]:
        assume.note(v.index)
    try:
        # BIND WHAT EXISTS AND LET THE PROGRAM ASK FOR THE REST. An FX-Map's patterns need
        # an image input only if one of its programs samples it, and most do not: refusing
        # the record because SOME edge has no output yet costs 511 records on
        # MetalPlatesSubstance004 alone, all of them downstream of one that would have
        # rendered. A program that does need the missing image raises `MissingSampler`,
        # which `run_program` turns into a cascade at the point of use.
        images = {}
        for k, e in enumerate(v.inputs):
            if e is None or e not in ctx.outputs:
                continue
            sbsruntime.SAMPLERS[k] = sampler(ctx.outputs[e])
            images[k] = ctx.outputs[e]
        for k, srci in ctx.sampler_bindings(v).items():
            if k not in sbsruntime.SAMPLERS:
                sbsruntime.SAMPLERS[k] = sampler(ctx.outputs[srci])
                images[k] = ctx.outputs[srci]
                ctx.low_confidence.add(v.index)
        run = fxrender.make_runner(
            ctx.asm,
            rec,
            programs=ctx.fx_funcs,
            cache_funcs=ctx.cache_funcs,
            inputs=ctx.program_inputs(),
        )
        try:
            seeded = (
                fxchain.seed(rec, run)
                if fxchain.active(rec)
                else fxrender.seed_slots(rec, run)
            )
            pats = emissions(rec, run, seeded, cache=ctx.cache)
        except fxrender.Unmodelled as e:
            raise Unsupported("fxmaps: %s" % e) from e
        # THE DRAW BUDGET IS PER PIXEL OF THE GRID, because both the cost and the meaning
        # of a pattern scale with it. A 2049^2 tile sampler is 4.2M patterns; at 64 px that
        # is 1,025 per pixel, each 0.03 px across, and the pixel-step rasteriser (no
        # anti-aliasing, SPEC 13.7) hits a centre with one in a thousand of them -- noise,
        # drawn at ~30 us a pattern: the fourth sweep spent 15 hours on Fence.sbsasm and
        # 7 on Fabric21 under the flat 2^23 budget. At 256 px the same record is 16 a
        # pixel and draws; at native, one. 64 a pixel puts the 64-px sweep where the old
        # 300,000 cap had it and lets every corpus count through at 256 and above.
        n = sum(int(p.count) if isinstance(p, fxtree.Batch) else 1 for p in pats)
        if n > MAX_PER_PIXEL * W * H:
            raise Unsupported(
                "fxmaps: %d patterns on a %d x %d grid (%.0f a pixel, over %d): sub-pixel "
                "at this grid" % (n, W, H, n / float(W * H), MAX_PER_PIXEL)
            )
        return splat(rec, pats, W, H, images=images, header=header_fields(ctx, v))
    finally:
        sbsruntime.CONTEXT["stream"] = False
        sbsruntime.SAMPLERS.clear()
        sbsruntime.SAMPLERS.update(saved)
