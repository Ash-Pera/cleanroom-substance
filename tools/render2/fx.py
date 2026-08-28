#!/usr/bin/env python3
"""FX-Map evaluation: how many patterns a record emits, and where each one lands.

STRUCTURE COMES FROM THE TAG, and this module does not re-derive it -- `fxrender.chain`
and `fxrender.entries` read the node chain and the parameter table out of the tag words,
which is the same mask-walk one scale down, and duplicating that walk is exactly how the
nibble-8 category error survived (two implementations making the same mistake in parallel
never disagree). What is rewritten here is everything downstream: WHEN each program runs,
HOW MANY times, and what the numbers mean once you have them.

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
import struct

import numpy as np

import assume
import disasm
import fxrender
import sbsruntime
from sbsasm import fx_patterntype

from ops import Unsupported, sampler

MAX_PATTERNS = 300000

_GRID_CACHE = {}

#: Opcodes that mean `$number` has been decomposed rather than scaled -- a row/column
#: split, which is `grid_width`'s two-axis case and not this one. Read BROADLY on purpose:
#: a false "two-dimensional" only declines the record and falls back to `numberadded`,
#: while a missed one would emit N patterns where the record wants N**2.
_DECOMPOSE = ('mod', 'cvt', 'floor')

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
        return float(struct.unpack_from('<I', imm, 0)[0])
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
    key = (getattr(rec.asm, 'path', id(rec.asm)), rec.index)
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
            if nm == 'sysvar':
                if toks and toks[0] == _NUMBER:
                    num.add(k)
                continue
            if nm == 'const':
                v = _const_value(addr, op, toks)
                if v is not None:
                    const[k] = v
                continue
            # An operand token is a register only if it names an EARLIER instruction;
            # anything else in the tuple is an immediate.
            regs = [t for t in toks if t < k]
            if nm in ('mul', 'div') and len(toks) >= 2:
                a, b = toks[0], toks[1]
                pairs = ((a, b), (b, a)) if nm == 'mul' else ((a, b),)
                for x, y in pairs:
                    if x in num and const.get(y):
                        n = (1.0 / const[y]) if nm == 'mul' else const[y]
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
    if assume.assumed('fx.gridcount', 'divisor') == 'divisor':
        w = _grid_width(rec)
        if w:
            return w * w, 'grid'
    if numberadded == 1:
        grid = number_grid(rec)
        # ONE-DIMENSIONAL ONLY. The two-axis spelling is `grid_width`'s own case, and where
        # it declines a record that is `grid_width`'s judgement -- overriding it with a
        # looser test is re-extending a rule past its evidence, which is the failure this
        # whole board is written against. What is left is the gap `grid_width` cannot
        # express at all: `$number` scaled LINEARLY by 1/N, a run of N rather than a grid.
        if grid is not None and grid[1] == 1 and grid[0] <= MAX_PATTERNS:
            return grid[0], 'placement'
    return numberadded, 'chain'


_WIDTH_CACHE = {}


def _grid_width(rec):
    key = (getattr(rec.asm, 'path', id(rec.asm)), rec.index)
    if key not in _WIDTH_CACHE:
        try:
            _WIDTH_CACHE[key] = fxrender.grid_width(rec)
        except Exception:
            _WIDTH_CACHE[key] = None
    return _WIDTH_CACHE[key]


def emissions(rec, run, slots):
    """[{parameter: value}] for every pattern the record draws, in emission order."""
    nodes = fxrender.chain(rec)
    table = fxrender.entries(rec)
    if not table:
        raise Unsupported('fxmaps: no emittable entries -- %s'
                          % fxrender.why_no_entries(rec))
    for _off, hdr, _p in nodes:
        if not _known_node(hdr):
            raise Unsupported('fxmaps: node header %#x is not modelled' % hdr)

    # THE RECORD'S OWN PROGRAMS SEED THE FRAME. The chain's programs read constants the
    # record's prologue writes, so running only the chain leaves better than half of all
    # records failing on "slot N read but never set".
    fx_progs = {p for _o, _h, ps in nodes for p in ps.values() if p}
    for _o, _t, params in table:
        for _k, (kind, value) in params.items():
            if kind != 'baked' and value:
                fx_progs.add(value)
    for prog in sorted(set(rec.programs) - fx_progs):
        try:
            run(prog, slots, 0)
        except Exception:
            pass

    out = []
    closed = [False]
    ran_once = set()

    def emit(number):
        for _o, tag, params in table:
            got = {'patterntype': fx_patterntype(tag), '_tag': tag}
            for name, (kind, value) in fxrender.in_eval_order(params):
                if value is None:
                    continue
                if kind != 'baked':
                    got[name] = run(value, slots, number)
                elif isinstance(value, np.ndarray):
                    got[name] = value
                else:
                    got[name] = np.asarray(value, dtype=np.float32).ravel()
            out.append(got)

    def walk(i, number, mode):
        if len(out) > MAX_PATTERNS:
            raise Unsupported('fxmaps: more than %d patterns' % MAX_PATTERNS)
        if i == len(nodes):
            emit(number)
            return
        _off, hdr, progs = nodes[i]
        if hdr in fxrender.ADDNODE:
            prog = progs.get('numberadded')
            if prog is None:
                raise Unsupported('fxmaps: addnode with no numberadded program')
            if 'randomseed' in progs and progs['randomseed'] is not None:
                run(progs['randomseed'], slots, number)
            raw = int(round(float(np.asarray(run(prog, slots, number)).ravel()[0])))
            if not 0 <= raw <= MAX_PATTERNS:
                raise Unsupported('fxmaps: numberadded = %d' % raw)
            n, mode = emission_count(rec, raw)
            if mode != 'chain':
                assume.note(rec.index)
            for k in range(n):
                walk(i + 1, k, mode)
            return
        if hdr == fxrender.GATE:
            prog = progs.get('switch')
            if prog is None:
                raise Unsupported('fxmaps: markov2 with no switch program')
            if mode == 'placement':
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
        if hdr == fxrender.STEPPER or (hdr & 0xFF) in (fxrender.STEPPER2,
                                                       fxrender.BRANCH):
            prog = progs.get(None)
            if prog is not None and (mode == 'chain' or i not in ran_once):
                ran_once.add(i)
                run(prog, slots, number)
            walk(i + 1, number, mode)
            return
        if (hdr & 0xFF) == fxrender.PASSTHROUGH or fxrender._is_leaf(hdr):
            walk(i + 1, number, mode)
            return
        raise Unsupported('fxmaps: node header %#x is not modelled' % hdr)

    walk(0, 0, 'chain')
    if not out and not closed[0]:
        raise Unsupported('fxmaps: emitted no patterns and no gate closed')
    return out


def _known_node(hdr):
    return (hdr in fxrender.ADDNODE or hdr == fxrender.GATE or hdr == fxrender.STEPPER
            or (hdr & 0xFF) in (fxrender.STEPPER2, fxrender.PASSTHROUGH, fxrender.BRANCH)
            or fxrender._is_leaf(hdr))


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
    b = [np.asarray(q.get('branchoffset'), np.float64).ravel()
         for q in patterns if q.get('branchoffset') is not None]
    if len(b) != len(patterns) or not b:
        return None
    w = max(x.size for x in b)
    a = np.array([np.pad(x, (0, w - x.size)) for x in b])
    d = []
    for k in range(min(2, a.shape[1])):
        col = a[:, k]
        sp = float(col.max() - col.min())
        ok = (sp >= 1 and abs(sp - round(sp)) < 1e-4
              and bool(np.all(np.abs(col - np.round(col)) < 1e-4))
              and len({round(float(t), 6) for t in col}) == round(sp) + 1)
        d.append(1.0 / (round(sp) + 1.0) if ok else 1.0)
    if not any(x != 1.0 for x in d):
        return None
    while len(d) < 2:
        d.append(1.0)
    return np.asarray(d, np.float32)


def _combine(dst, src):
    mode = assume.assumed('fx.combine', 'max')
    if mode == 'add':
        return dst + src
    if mode == 'over':
        a = np.clip(np.abs(src), 0.0, 1.0)
        return dst * (1.0 - a) + src
    return np.maximum(dst, src)


def splat(rec, patterns, W, H, images=None):
    """Draw the emitted patterns onto a W x H canvas."""
    nchan = 4 if rec.colour else 1
    canvas = np.zeros((H, W, nchan), np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    pxg = (xx + 0.5) / W - 0.5
    pyg = (yy + 0.5) / H - 0.5

    forced = assume.assumed('fx.profile')
    cell = None
    for key in ('fx.branchoffset', 'fx.patternsize', 'fx.frameoffset'):
        if assume.assumed(key) == 'cell':
            cell = _cell(patterns)
            break
    base_scale = cell if assume.assumed('fx.branchoffset') == 'cell' else None
    size_scale = cell if assume.assumed('fx.patternsize') == 'cell' else None
    frame_scale = cell if assume.assumed('fx.frameoffset') == 'cell' else None
    sizeless = assume.assumed('fx.sizeless', 'fill')
    skip_root = assume.assumed('fx.rootentry') == 'skip'
    skip_markers = assume.assumed('fx.markers') == 'skip'
    neg = assume.assumed('fx.negopacity', 'clip')

    def val(pat, name, default):
        v = pat.get(name)
        return np.asarray(default, np.float32) if v is None \
            else np.asarray(v, np.float32).ravel()

    for p in patterns:
        tag = p.get('_tag')
        if skip_markers and tag is not None and (int(tag) & 0xFF) == 0x08:
            continue
        if p.get('patternsize') is None and p.get('patterntype') is None:
            b = np.asarray(p.get('branchoffset', _ZERO2), np.float64).ravel()
            if skip_root and b.size >= 2 and not np.any(np.abs(b[:2]) > 1e-6):
                continue
            if sizeless == 'skip':
                continue
            if sizeless in ('half', 'quarter'):
                p = dict(p)
                p['patternsize'] = np.full(2, 0.5 if sizeless == 'half' else 0.25,
                                           np.float32)
        src = _image_for(p, images)
        base = val(p, 'branchoffset', _ZERO2)
        off = val(p, 'frameoffset', _ZERO2)
        size = val(p, 'patternsize', _ONE2)
        if base_scale is not None:
            base = base * base_scale[:base.size]
        if frame_scale is not None:
            off = off * frame_scale[:off.size]
        if size_scale is not None:
            size = size * size_scale[:size.size]
        if size.size < 2:
            size = np.repeat(size[:1], 2)
        if base.size < 2:
            base = np.repeat(base[:1], 2)
        if off.size < 2:
            off = np.repeat(off[:1], 2)
        sx, sy = float(size[0]), float(size[1])
        cx, cy = float(base[0] + off[0]), float(base[1] + off[1])
        if not (math.isfinite(sx) and math.isfinite(sy)
                and math.isfinite(cx) and math.isfinite(cy)):
            continue
        if sx <= 0 or sy <= 0 or max(sx, sy) > 64.0 or min(sx, sy) < MIN_SIZE:
            continue
        col = val(p, 'opacity', _ONE1)
        if col.size < nchan:
            col = np.repeat(col[:1], nchan)
        if neg == 'signed':
            col = np.clip(col[:nchan], -1.0, 1.0)
        elif neg == 'abs':
            col = np.clip(np.abs(col[:nchan]), 0.0, 1.0)
        else:
            col = np.clip(col[:nchan], 0.0, 1.0)

        rot = float(val(p, 'patternrotation', np.zeros(1, np.float32))[0])
        th = 2.0 * math.pi * rot
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
                dx = pxg[r0:r1 + 1, c0:c1 + 1] - ux
                dy = pyg[r0:r1 + 1, c0:c1 + 1] - uy
                lx = (dx * ct + dy * st) / sx
                ly = (-dx * st + dy * ct) / sy
                if prof in ('rect', 'square'):
                    hit = (np.abs(lx) <= 0.5) & (np.abs(ly) <= 0.5)
                    cov = None
                else:
                    cov = fxrender.profile_value(lx, ly, prof)
                    hit = cov > 0
                if not hit.any():
                    continue
                tile = canvas[r0:r1 + 1, c0:c1 + 1]
                if src is None:
                    if cov is None and hit.all():
                        tile[...] = _combine(tile, col)
                    else:
                        tile[hit] = _combine(tile[hit],
                                             col if cov is None else col * cov[hit, None])
                    continue
                uv = np.stack([lx[hit] + 0.5, ly[hit] + 0.5], axis=-1)
                got = np.asarray(sampler(src)(uv), np.float32)
                if got.ndim == 1:
                    got = got[:, None]
                if got.shape[-1] < nchan:
                    got = np.repeat(got[:, :1], nchan, axis=-1)
                tile[hit] = _combine(tile[hit],
                                     got[:, :nchan] * col if cov is None else
                                     got[:, :nchan] * col * cov[hit, None])
    return np.clip(canvas, 0.0, 1.0)


def _profile_for(p):
    t = p.get('patterntype')
    if t is None:
        return assume.assumed('fx.typeless_profile', 'rect')
    return fxrender.PATTERN_SHAPES.get(t, 'rect')


def _image_for(p, images):
    if not images:
        return None
    v = p.get('imageindex')
    if v is None:
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
        run = fxrender.make_runner(ctx.asm, rec, programs=ctx.fx_funcs,
                                   cache_funcs=ctx.cache_funcs)
        try:
            pats = emissions(rec, run, fxrender.seed_slots(rec, run))
        except fxrender.Unmodelled as e:
            raise Unsupported('fxmaps: %s' % e) from e
        return splat(rec, pats, W, H, images=images)
    finally:
        sbsruntime.SAMPLERS.clear()
        sbsruntime.SAMPLERS.update(saved)
