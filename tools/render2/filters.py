#!/usr/bin/env python3
"""One function per filter. Every parameter is read from `model.View` BY NAME.

The rule this file is written to: a filter may ask what a parameter IS and whether it is
baked or a program; it may not ask where it sits, how wide it is, or what a slot's value
looks like. Slot arithmetic and value probes live nowhere -- the walk answered both before
this module runs.

PARAMETERS THE FORMAT OMITS. A class-word or w1 field that is absent means the source left
the parameter at its node default, and that default is in NEITHER file -- not the assembly,
which stores only what was set, and not the manifest, whose vocabulary is the exposed
interface. `DEFAULTS` is that table, and it is the only place in this renderer where a
number comes from outside the file. Every use marks the record LOW_CONFIDENCE and an
explicit `assume` scope overrides it, so a sweep can still ask what a different default
would do.
"""
import numpy as np

import assume
import manifest
import sbsruntime

from ops import (Unsupported, blend, footprint_scale, pos_grid, prefilter, sampler,
                 to_image)

#: Parameter defaults for values the format does not record. See the module docstring.
#:
#: `grayscale.weights` -- `grayscaleconversion`'s `channelsweights`. Over the whole corpus
#: 5,457 records BAKE this vector and the even weight `(1/3, 1/3, 1/3, 0)` is not among
#: them at any multiplicity, while the two neighbouring candidates are ((0.3, 0.59, 0.11,
#: 0) x26 and its exact twin x14, (0.25, 0.25, 0.25, 0) x44). A compiler that omits a
#: parameter exactly when it equals the node default leaves the default as the value that
#: is never written, and the even weight is the only round candidate with a zero count.
#: That is an argument from an absence and it is marked accordingly.
#: `uniform.fill` -- the node default for a `uniform` whose class bit 8 is clear. Black,
#: and this specimen is one of the few places the claim has ground truth: `Rokviz japanese
#: fabric 8` record 0 is such a uniform, it IS the graph's `metallic` output, and the
#: engine's own 4096x4096 export of that output is exactly 0.0 at every pixel -- min, max
#: and mean, one distinct value. One specimen is one specimen; it is still a check the
#: default could have failed.
DEFAULTS = {
    'grayscale.weights': (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, 0.0),
    'uniform.fill': 0.0,
    'levels.in': (0.0, 0.5, 1.0),
    'levels.out': (0.0, 1.0),
}

FILTERS = {}


def filt(name):
    def wrap(fn):
        FILTERS[name] = fn
        return fn
    return wrap


def _scalar(ctx, v, name, default, W, H, pos):
    """A named parameter as a number or an (N, 1) field. Baked, program, or the default."""
    p = v.params.get(name)
    if p is None:
        return np.float32(default)
    if p.kind == 'baked':
        return np.float32(p.value if p.width == 1 else p.value[0])
    # NO W/H: `Context.run` supplies the record's declared size. Passing the capped grid
    # here made every program-valued `opacitymult`, all five `levels` parameters and
    # `dirmotionblur`/`directionalwarp`'s intensity and angle read `$size` as
    # min(declared, --dim) -- a parameter VALUE that moves when the caller previews smaller.
    #
    # THE CHOICE IS NOT A TASTE, and the population settles it. Over a corpus sample,
    # 6,793 program-valued parameters of these filters: 5,338 read `$sizelog2`, 69 read
    # `$size`, and NOT ONE reads `$pos`. They are per-record CONSTANTS that `_scalar` then
    # broadcasts, so there is no grid-relative neighbour tap to preserve and the declared
    # size is the only defensible answer. (A `pixelprocessor`'s own image program is the
    # other population -- it does read `$pos` -- and keeps the render grid.) `pos` is still
    # passed here in case a parameter program ever reads it.
    return to_image(ctx.run(v, p.value, W * H, pos=pos),
                    W * H, H, W).reshape(W * H, -1)[:, :1]


def _channelwise(ctx, v, name, default, W, H, pos, nchan):
    """A per-channel parameter, kept at its real WIDTH instead of collapsed to one value.

    `levels`' five fields are per-channel (SPEC 13.4): Float1 on a greyscale record and
    Float4 on a colour one, and on a colour record the four components are genuinely
    different -- Chesterfield record 348 holds `levelinlow` = (0.264, 0.264, 0.264, 0.0)
    and `levelinhigh` = (0.593, 0.593, 0.593, 1.0), an RGB remap with alpha left alone.
    Reading component 0 and applying it to all four is a known wrong read: it remaps alpha
    by the red curve.

    Returned as a `(nchan,)` vector so it broadcasts against the `(N, C)` source, which is
    all the surrounding arithmetic needs -- every step of it is already elementwise.
    """
    p = v.params.get(name)
    if p is None:
        return np.float32(default)
    if p.kind == 'baked':
        if p.width == 1:
            return np.float32(p.value)
        vals = np.asarray(p.value, dtype=np.float32).ravel()
        return vals[:nchan] if vals.size >= nchan else np.float32(vals[0])
    got = to_image(ctx.run(v, p.value, W * H, pos=pos), W * H, H, W).reshape(W * H, -1)
    return got[:, :nchan] if got.shape[-1] >= nchan else got[:, :1]


def _vector(ctx, v, name, width):
    """A named parameter as a `width`-long tuple, evaluating a program if that is its arm.

    At the record's declared size, which is `Context.run`'s rule and stated there.
    """
    p = v.params.get(name)
    if p is None:
        return None
    if p.kind == 'baked':
        vals = (p.value,) if p.width == 1 else tuple(p.value)
        return vals if len(vals) == width else None
    out = np.asarray(ctx.run(v, p.value, 1)).ravel()
    return tuple(float(x) for x in out) if out.size == width else None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

@filt('bitmap')
def f_bitmap(ctx, v):
    b = v.rec.bitmap
    if b is None:
        raise Unsupported('bitmap record states no payload')
    if b['kind'] == 'pixels':
        return _pixels(ctx, v, b)
    if b['kind'] == 'graph_input':
        got = _graph_input_default(ctx, v)
        if got is not None:
            ctx.low_confidence.add(v.index)
            return got
        raise Unsupported('bitmap is a graph image input and the package ships no image '
                          'and declares no default')
    raise Unsupported('bitmap kind %r has no supplied output' % b['kind'])


def _pixels(ctx, v, b):
    asm = ctx.asm
    off, size, ch, depth = b['offset'], b['size'], b['channels'], b['depth']
    if b.get('compressed') == 'jpeg':
        import io
        import struct
        from PIL import Image
        p = b['data_offset']
        if asm.data[p:p + 3] != b'\xff\xd8\xff':
            raise Unsupported('bitmap is flagged JPEG but has no JPEG stream at +52')
        n = struct.unpack_from('<I', asm.data, p - 4)[0]
        try:
            im = Image.open(io.BytesIO(asm.data[p:p + n]))
            im.load()
        except Exception as e:
            raise Unsupported("bitmap's JPEG payload will not decode: %s" % e)
        got = {'L': 1, 'RGB': 3, 'RGBA': 4}.get(im.mode)
        if got is None:
            raise Unsupported("bitmap's JPEG has an unhandled mode %r" % im.mode)
        if (im.size[0], im.size[1]) != (v.width, v.height):
            raise Unsupported("bitmap's JPEG is %dx%d, record declares %dx%d"
                              % (im.size[0], im.size[1], v.width, v.height))
        return (np.asarray(im, dtype=np.float32) / 255.0).reshape(v.height, v.width, got)
    if depth is None:
        raise Unsupported('bitmap has pixels but an undecoded channel code')
    if off + size > len(asm.data):
        raise Unsupported('bitmap wants %d bytes at %d, file holds %d'
                          % (size, off, max(0, len(asm.data) - off)))
    arr = np.frombuffer(asm.data[off:off + size], dtype='<u1' if depth == 8 else '<u2')
    ch = ch if (ch and ch > 1) else 1
    return arr.reshape(v.height, v.width, ch).astype(np.float32) / float((1 << depth) - 1)


def _graph_input_default(ctx, v):
    """The manifest's substitute for an unconnected image input, as a uniform, or None."""
    uid = (v.rec.bitmap or {}).get('uid')
    got = manifest.image_input_defaults(ctx.asm).get(uid)
    if got is None:
        return None
    try:
        parts = [float(x) for x in got[0].replace(';', ',').split(',') if x.strip()]
    except ValueError:
        return None
    if not parts:
        return None
    n = 4 if v.colour else 1
    vals = ([parts[0]] * n) if len(parts) == 1 else (parts + [parts[-1]] * n)[:n]
    return np.zeros((v.height, v.width, n), np.float32) + np.asarray(vals, np.float32)


@filt('uniform')
def f_uniform(ctx, v):
    W, H = v.size(ctx.cap)
    n = 4 if v.colour else 1
    col = _vector(ctx, v, 'outputcolor', 4)
    if col is None:
        col = _vector(ctx, v, 'outputcolor', n)
    if col is None:
        # NO BAKED FILL AND NO PROGRAM AT THE NAMED SLOT. The class word says the source
        # set no colour, so the engine's default applies -- and a `uniform` still carries
        # its SIZE expression, which is a different slot and must not be read as a fill.
        prog = _fill_program(ctx, v)
        if prog is not None:
            col = prog
        else:
            fill = assume.assumed('uniform.fill', DEFAULTS['uniform.fill'])
            arr = np.asarray(fill, dtype=np.float32).ravel()
            col = tuple(np.repeat(arr, n)) if arr.size == 1 else tuple(arr[:n])
            ctx.low_confidence.add(v.index)
            assume.note(v.index)
    c = np.clip(np.asarray(col[:n] if len(col) >= n else col, np.float32), 0.0, 1.0)
    if c.size == 1 and n > 1:
        c = np.repeat(c, n)
    return np.tile(c, (H * W, 1)).reshape(H, W, n)


def _fill_program(ctx, v):
    """A `uniform`'s fill when it is computed, taken from a slot the walk names.

    The record's own program slots minus the size expression. A `uniform` with class bit 8
    clear and a second program is a fill the graph computes -- twelve records in one
    reference pack rendered black until this was read.
    """
    n = 4 if v.colour else 1
    for p in ctx.walk_programs(v):
        try:
            out = np.asarray(ctx.run(v, p, 1)).ravel()
        except Exception:
            continue
        if out.size == 1 and n > 1:
            out = np.repeat(out, n)
        if out.size >= n and np.all(np.isfinite(out[:n])) \
                and np.all((out[:n] >= -0.01) & (out[:n] <= 1.01)):
            return tuple(float(x) for x in out[:n])
    return None


@filt('fxmaps')
def f_fxmaps(ctx, v):
    import fx
    return fx.render_fxmaps(ctx, v)


# ---------------------------------------------------------------------------
# Per-pixel programs
# ---------------------------------------------------------------------------

@filt('pixelprocessor')
def f_pixelprocessor(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    saved = dict(sbsruntime.SAMPLERS)
    sbsruntime.SAMPLERS.clear()
    try:
        for k in range(len(v.inputs)):
            sbsruntime.SAMPLERS[k] = sampler(ctx.src(v, k))
        for k, src in ctx.sampler_bindings(v).items():
            if k not in sbsruntime.SAMPLERS:
                sbsruntime.SAMPLERS[k] = sampler(ctx.outputs[src])
                ctx.low_confidence.add(v.index)
        # THE PIXEL PROGRAM IS THE LAST HEADER SLOT, which is the record layout model read
        # straight: [tag][arity][inputs][one slot per set class bit][the filter's own].
        # `decompose` places it BEFORE the class slots for this filter, and the two
        # orderings give the same header length so no length check separates them -- but
        # the contents do. Rokviz record 24 has a 5-word header whose slot 3 is
        # `inputref($randomseed)`, an INHERITED parameter, and whose slot 4 is the pixel
        # program; taking slot 3 renders the record as a constant and blackens the mask
        # that carries the whole basecolor pattern.
        progs = ctx.walk_programs(v, include_prog_slot=True)
        main = ctx.prog_at(v, (v.header_end - 1) if v.header_end else None)
        if main is None:
            main = ctx.prog_at(v, v.prog_slot)
        if main is None and progs:
            main = progs[-1]
        if main is None:
            raise Unsupported('pixelprocessor names no program')
        if main not in progs:
            progs = progs + [main]
        slots = {}
        for p in progs:
            if p != main:
                try:
                    ctx.run(v, p, 1, slots=slots)
                except Unsupported:
                    pass
        pos = pos_grid(W, H)
        out = ctx.run(v, main, N, slots=slots, pos=pos, W=W, H=H)
        return to_image(out, N, H, W)
    finally:
        sbsruntime.SAMPLERS.clear()
        sbsruntime.SAMPLERS.update(saved)


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------

@filt('blend')
def f_blend(ctx, v):
    mode = (v.rec.slot1_flags or {}).get('blendingmode')
    if mode is None:
        raise Unsupported('blend record states no readable blendingmode')
    if len(v.inputs) < 2:
        raise Unsupported('blend has fewer than 2 edges')
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    dst = ctx.sample(v, 0, pos)
    src = ctx.sample(v, 1, pos)
    if dst.shape[-1] != src.shape[-1]:
        raise Unsupported('blend inputs disagree on channel count (%d vs %d)'
                          % (dst.shape[-1], src.shape[-1]))
    # OPACITY IS `opacitymult` OR 1.0, AND NOTHING ELSE. The old reader fell back to the
    # size-expression slot when the parameter was absent, which is where its 1,004
    # size-expression misattributions came from: an absent field means the source left the
    # multiplier at 1, not that the number is somewhere else.
    opacity = _scalar(ctx, v, 'opacitymult', 1.0, W, H, pos)
    opacity = np.asarray(opacity, np.float32).reshape(-1, 1) if np.ndim(opacity) \
        else np.full((N, 1), float(opacity), np.float32)
    if len(v.inputs) > 2 and v.inputs[2] is not None:
        opacity = opacity * ctx.sample(v, 2, pos)[:, :1]
    return to_image(blend(mode, dst, src, opacity), N, H, W)


@filt('transformation')
def f_transformation(ctx, v):
    W, H = v.size(ctx.cap)
    m = _vector(ctx, v, 'matrix22', 4)
    if m is None:
        if v.has('matrix22'):
            raise Unsupported('matrix22 is a program that does not evaluate 4-wide')
        m = (1.0, 0.0, 0.0, 1.0)
    off = _vector(ctx, v, 'offset', 2)
    if off is None:
        if v.has('offset'):
            raise Unsupported('offset is a program that does not evaluate 2-wide')
        off = (0.0, 0.0)
    pos = pos_grid(W, H)
    c = pos - 0.5
    in_pos = np.stack([m[0] * c[:, 0] + m[1] * c[:, 1] + 0.5 + off[0],
                       m[2] * c[:, 0] + m[3] * c[:, 1] + 0.5 + off[1]], axis=-1)
    src = np.asarray(ctx.src(v, 0))
    scale = footprint_scale(m, W, H, src.shape)
    if scale >= 2.0:
        src = prefilter(src, scale)
    return to_image(sampler(src)(in_pos), W * H, H, W)


@filt('shuffle')
def f_shuffle(ctx, v):
    """Two authoring nodes, one filter id, separated by TAG BIT 0 -- the colour flag.

    Clear: `grayscaleconversion`, one image at slot 1 and a `channelsweights` float4.
    Set:   Channel Shuffle, two images and a packed four-byte selector in w1.

    Read from the flag, not from what the slots look like: over 307 single-input records
    the bit and a plausible-looking float4 agree 302 times, and four of the five that
    disagree have the bit CLEAR while the bytecode at that offset decodes to floats a value
    test accepts.
    """
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    if not v.colour:
        w = _vector(ctx, v, 'channelsweights', 4)
        if w is None:
            w = assume.assumed('grayscale.weights', DEFAULTS['grayscale.weights'])
            ctx.low_confidence.add(v.index)
            assume.note(v.index)
        hot = np.asarray(w, np.float32).ravel()
        if hot.size != 4 or not np.all(np.isfinite(hot)):
            raise Unsupported('channelsweights is not four finite numbers (%r)'
                              % (np.round(hot, 4).tolist(),))
        src = ctx.sample(v, 0, pos)
        used = [k for k, x in enumerate(hot) if abs(x) > 1e-9]
        if used and max(used) >= src.shape[-1]:
            # A WEIGHT ON A CHANNEL THE INPUT DOES NOT HAVE. Not clamped: the source image
            # is three channels or one, and weighting a fourth means reading padding this
            # renderer invented -- the exact error that made a fitted weight vector look
            # like the best candidate on this file's own arbiter.
            raise Unsupported('channelsweights weights channel %d of an input with only %d'
                              % (max(used), src.shape[-1]))
        w4 = hot[:src.shape[-1]]
        return to_image((src * w4).sum(axis=-1, keepdims=True), N, H, W)

    w1 = v.words[1] if len(v.words) > 1 else 0
    sels = [(w1 >> (8 * k)) & 0xFF for k in range(4)]
    if not all(s <= 7 for s in sels):
        raise Unsupported('shuffle selector word %#010x is not four selectors' % w1)
    nout = 4 if v.colour else 1
    cols = []
    cache = {}
    for s in sels[:nout]:
        k, c = s // 4, s % 4
        if k >= len(v.inputs) or v.inputs[k] is None:
            raise Unsupported('shuffle wants input %d, which this record does not have'
                              % (k + 1))
        a = cache.setdefault(k, ctx.sample(v, k, pos))
        if c >= a.shape[-1]:
            raise Unsupported('shuffle selects channel %d of an input with only %d'
                              % (c, a.shape[-1]))
        cols.append(a[:, c:c + 1])
    return to_image(np.concatenate(cols, axis=-1), N, H, W)


# ---------------------------------------------------------------------------
# Tone
# ---------------------------------------------------------------------------

@filt('levels')
def f_levels(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    src = ctx.sample(v, 0, pos)
    nchan = src.shape[-1]

    def par(name, default):
        return _channelwise(ctx, v, name, default, W, H, pos, nchan)

    lo = par('levelinlow', DEFAULTS['levels.in'][0])
    mid = par('levelinmid', DEFAULTS['levels.in'][1])
    hi = par('levelinhigh', DEFAULTS['levels.in'][2])
    out_lo = par('leveloutlow', DEFAULTS['levels.out'][0])
    out_hi = par('levelouthigh', DEFAULTS['levels.out'][1])

    # A ZERO-WIDE INPUT SPAN IS A THRESHOLD, not a division to guard against, and it is
    # how this format writes a hard binarisation: `levelinlow == levelinhigh` with the
    # OUTPUT range reversed (leveloutlow 1, levelouthigh 0) is "1 below the threshold".
    # Rokviz record 34 is exactly that, and reading it as an identity exchanges the two
    # palette branches of the whole material.
    span = hi - lo
    degenerate = np.abs(span) < 1e-6
    safe = np.where(degenerate, 1.0, span)
    ramp = np.clip((src - lo) / safe, 0.0, 1.0)
    if assume.assumed('levels.zerospan') == 'identity':
        step = np.clip(src, 0.0, 1.0)
        if np.any(degenerate):
            assume.note(v.index)
    else:
        step = (src >= lo).astype(np.float32)
    t = np.where(degenerate, step, ramp)

    m = np.clip(mid, 1e-4, 1 - 1e-4)
    with np.errstate(all='ignore'):
        gamma = np.power(t, np.log(0.5) / np.log(m))
    t = np.where(np.abs(m - 0.5) < 1e-6, t, gamma)
    return to_image(np.clip(out_lo + t * (out_hi - out_lo), 0.0, 1.0), N, H, W)


@filt('normal')
def f_normal(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    p = v.params.get('intensity')
    if p is None:
        d = assume.assumed('normal.default_intensity', 'refuse')
        if d == 'refuse':
            raise Unsupported('normal stores no intensity (its w1 field is absent), so the '
                              'source omitted it and the engine default applies')
        intensity = float(d)
        ctx.low_confidence.add(v.index)
        assume.note(v.index)
    elif p.kind == 'baked':
        intensity = float(p.value)
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size < 1 or not np.isfinite(got[0]):
            raise Unsupported('normal intensity program does not evaluate to a scalar')
        intensity = float(got[0])

    height = to_image(ctx.sample(v, 0, pos), N, H, W)[:, :, 0].astype(np.float32)
    # `np.gradient` is per RENDER pixel, so an uncorrected normal halves in strength every
    # time the grid doubles -- the engine differences adjacent pixels at the record's own
    # resolution. Put it back on that scale, the same correction `warp` already makes.
    # At full resolution the factor is exactly 1, so no uncapped render moves.
    ref = _reference_px(v)
    gy, gx = np.gradient(height)
    gx, gy = gx * (W / ref), gy * (H / ref)
    # FIELD 1 IS A TWO-BIT CODE, NOT A BIT. Reading `(w1 >> 2) & 1` sees state 01 and calls
    # state 10 absent, so a program-valued inversedy -- which is how the sources actually
    # write it, `normal_format == <int>` off a graph input -- reads as "not inverted" and
    # its program is never run. That the field IS inversedy remains an assumption; that it
    # has two arms is the walk's own declaration.
    inv = v.params.get('inversedy')
    if assume.assumed('normal.inversedy', 'field1') != 'ignore' and inv is not None:
        if inv.kind == 'baked':
            flip = True
        else:
            got = np.asarray(ctx.run(v, inv.value, 1)).ravel()
            if got.size < 1 or not np.isfinite(got[0]):
                raise Unsupported('normal inversedy program does not evaluate to a scalar')
            flip = bool(got[0] > 0.5)
        if flip:
            gy = -gy
        ctx.low_confidence.add(v.index)
        assume.note(v.index)
    nx, ny = -gx * intensity, -gy * intensity
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack([0.5 + 0.5 * nx / ln, 0.5 + 0.5 * ny / ln,
                    0.5 + 0.5 * nz / ln], axis=-1).reshape(N, 3)
    rgb = np.clip(rgb, 0.0, 1.0)
    if v.colour:
        rgb = np.concatenate([rgb, np.ones((N, 1), np.float32)], axis=-1)
    return to_image(rgb, N, H, W)


@filt('hsl')
def f_hsl(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    src = ctx.sample(v, 0, pos)
    h = _scalar(ctx, v, 'hue', 0.5, W, H, pos)
    s = _scalar(ctx, v, 'saturation', 0.5, W, H, pos)
    lu = _scalar(ctx, v, 'luminosity', 0.5, W, H, pos)
    rgb = src[:, :3] if src.shape[-1] >= 3 else np.repeat(src[:, :1], 3, axis=1)
    mx, mn = rgb.max(axis=1, keepdims=True), rgb.min(axis=1, keepdims=True)
    lum = 0.5 * (mx + mn)
    with np.errstate(all='ignore'):
        sat = np.where(mx == mn, 0.0,
                       (mx - mn) / np.where(lum < 0.5, mx + mn, 2.0 - mx - mn))
        hue = np.zeros_like(lum)
        d = mx - mn
        r, g, b = rgb[:, :1], rgb[:, 1:2], rgb[:, 2:3]
        hue = np.where(mx == r, (g - b) / np.where(d == 0, 1, d) % 6.0, hue)
        hue = np.where(mx == g, (b - r) / np.where(d == 0, 1, d) + 2.0, hue)
        hue = np.where(mx == b, (r - g) / np.where(d == 0, 1, d) + 4.0, hue)
        hue = np.where(d == 0, 0.0, hue / 6.0)
    hue = (hue + (np.asarray(h) - 0.5)) % 1.0
    sat = np.clip(sat * (2.0 * np.asarray(s)), 0.0, 1.0)
    lum = np.clip(lum + (np.asarray(lu) - 0.5), 0.0, 1.0)
    q = np.where(lum < 0.5, lum * (1.0 + sat), lum + sat - lum * sat)
    p_ = 2.0 * lum - q

    def chan(tc):
        tc = tc % 1.0
        out = np.where(tc < 1 / 6.0, p_ + (q - p_) * 6.0 * tc,
                       np.where(tc < 0.5, q,
                                np.where(tc < 2 / 3.0,
                                         p_ + (q - p_) * (2 / 3.0 - tc) * 6.0, p_)))
        return out
    out = np.concatenate([chan(hue + 1 / 3.0), chan(hue), chan(hue - 1 / 3.0)], axis=1)
    if src.shape[-1] == 4:
        out = np.concatenate([out, src[:, 3:4]], axis=1)
    return to_image(np.clip(out, 0.0, 1.0), N, H, W)


# ---------------------------------------------------------------------------
# Spatial
# ---------------------------------------------------------------------------

def _reference_px(v):
    """The pixel scale a pixel-valued intensity is expressed in -- from the RECORD.

    A fixed 256 is right for 98.6% of the corpus by a property of the corpus, not of the
    format, and wrong by 2x or 4x on the rest. An explicit `warp.reference_px` still wins.
    """
    forced = assume.assumed('warp.reference_px')
    if forced is not None and forced != 'record':
        return float(forced)
    return float(v.width) if v.width else 256.0


@filt('blur')
def f_blur(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    p = v.params.get('intensity')
    if p is None:
        raise Unsupported('blur stores no intensity: neither class bit 12 (baked) nor 13 '
                          '(program) is set, so the source omitted it')
    if p.kind == 'baked':
        intensity = float(p.value)
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size != 1 or not np.isfinite(got[0]):
            raise Unsupported('blur intensity program does not evaluate to a scalar')
        intensity = float(got[0])
    src = to_image(ctx.sample(v, 0, pos), N, H, W)
    radius = float(np.clip(abs(intensity), 0.0, 256.0)) / _reference_px(v)
    rpx = int(round(radius * max(W, H)))
    if rpx < 1:
        return src                       # a blur of sub-pixel radius is the identity
    return _box(src, rpx)


def _box(src, rpx):
    k = 2 * rpx + 1
    acc = np.zeros_like(src)
    for d in range(-rpx, rpx + 1):
        acc += np.roll(src, d, axis=1)
    acc /= k
    out = np.zeros_like(acc)
    for d in range(-rpx, rpx + 1):
        out += np.roll(acc, d, axis=0)
    return np.clip(out / k, 0.0, 1.0)


@filt('sharpen')
def f_sharpen(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    src = to_image(ctx.sample(v, 0, pos), N, H, W)
    # `v.baked(name, 1.0) or 1.0` read the baked arm ONLY and turned a stated 0.0 into 1.0,
    # which mattered the moment the legend started supplying this parameter at all.
    p = v.params.get('intensity')
    if p is None:
        amount = 1.0                      # absent: the node default, and NOT recorded here
    elif p.kind == 'baked':
        amount = float(p.value)
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size < 1 or not np.isfinite(got[0]):
            raise Unsupported('sharpen intensity program does not evaluate to a scalar')
        amount = float(got[0])
    return np.clip(src + amount * (src - _box(src, 1)), 0.0, 1.0)


@filt('dirmotionblur')
def f_dirmotionblur(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    intensity = np.asarray(_scalar(ctx, v, 'intensity', 0.0, W, H, pos), np.float32)
    angle = np.asarray(_scalar(ctx, v, 'mblurangle', 0.0, W, H, pos), np.float32)
    length = np.clip(np.abs(intensity), 0.0, 256.0) / _reference_px(v) * 10.0
    turn = 2.0 * np.pi * angle
    smp = sampler(ctx.src(v, 0))
    TAPS = 17
    acc = None
    for k in range(TAPS):
        f = (k / (TAPS - 1.0)) - 0.5
        off = np.concatenate([(length * f) * np.cos(turn) * np.ones((N, 1), np.float32),
                              (length * f) * np.sin(turn) * np.ones((N, 1), np.float32)],
                             axis=-1)
        val = smp(pos + off)
        acc = val if acc is None else acc + val
    return to_image(acc / float(TAPS), N, H, W)


@filt('directionalwarp')
def f_directionalwarp(ctx, v):
    if len(v.inputs) < 2:
        raise Unsupported('directionalwarp has fewer than 2 edges')
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    a, b = (1, 0) if assume.assumed('dirwarp.edges') == 'swapped' else (0, 1)
    if a:
        assume.note(v.index)
    intensity = np.asarray(_scalar(ctx, v, 'intensity', 0.0, W, H, pos), np.float32)
    angle = np.asarray(_scalar(ctx, v, 'warpangle', 0.0, W, H, pos), np.float32)
    height = ctx.sample(v, b, pos)[:, :1]
    disp = (2.0 * height - 1.0) * intensity / _reference_px(v)
    turn = 2.0 * np.pi * angle
    in_pos = pos + np.concatenate(
        [disp * np.cos(turn) * np.ones((N, 1), np.float32),
         disp * np.sin(turn) * np.ones((N, 1), np.float32)], axis=-1)
    return to_image(sampler(ctx.src(v, a))(in_pos), N, H, W)


# ---------------------------------------------------------------------------
# Table-driven tone, and the two-input spatial filters
# ---------------------------------------------------------------------------

#: How many components of a `read_ramp` entry `f_gradient` actually slices, per form. The
#: keys are asserted against `sbsasm.RAMP_FORMS` by the suite, so a new layout in the decode
#: fails there rather than at whichever record happens to reach it first. Entries may be one
#: component WIDER than this -- the trailing midpoint word, which nothing here reads.
_RAMP_WIDTH = {'grey-u16': 2, 'rgba-u16': 3, 'grey-float': 2, 'rgba-float': 5}


@filt('gradient')
def f_gradient(ctx, v):
    """A colour or greyscale ramp indexed by the input's first channel.

    The ramp table itself is `Record.read_ramp`, whose stop/value packing is a decode this
    module does not restate. Its ONE fitted piece is documented there and is not touched
    here: a one-word-late read patched onto three records of a single reference pack.

    THE LAYOUT IS READ FROM THE RECORD, NOT FROM THE VALUES. This used to branch on
    `isinstance(table[0][0], float)` and on the entry's length -- asking what a Python
    object was, where the decode that built it had already chosen the layout from the
    colour flag and the span. It agreed with the record on all 23,153 gradient records in
    the 651 `.sbsasm` files here, which is how a reading like this survives a review: it is
    not wrong, it is unfalsifiable. Two of the four layouts are three components wide, so the day a fifth
    arrives the type is no longer enough and nothing would say so. `read_ramp` states the
    layout; `_RAMP_WIDTH` is what this reader needs from each, and a form it cannot read
    refuses out loud instead of slicing a short entry into a wrong-width array.
    """
    got = v.rec.read_ramp()
    if not got:
        raise Unsupported('gradient record carries no readable ramp')
    form, table = got
    if form not in _RAMP_WIDTH:
        raise Unsupported('gradient ramp form %r has no reader here' % (form,))
    if len(table[0]) < _RAMP_WIDTH[form]:
        raise Unsupported('%s ramp entry is %d components, needs %d'
                          % (form, len(table[0]), _RAMP_WIDTH[form]))
    W, H = v.size(ctx.cap)
    N = W * H
    if form == 'rgba-float':
        stops = np.array([e[0] for e in table], np.float32)
        vals = np.array([list(e[1:5]) for e in table], np.float32)
    elif form == 'grey-float':
        stops = np.array([e[0] for e in table], np.float32)
        vals = np.array([e[1] for e in table], np.float32)
    elif form == 'rgba-u16':
        stops = np.array([e[0] for e in table], np.float32) / 65535.0
        packed = [(int(e[1]) | (int(e[2]) << 16)) & 0xFFFFFFFF for e in table]
        vals = np.array([[(u >> (8 * k)) & 0xFF for k in range(4)] for u in packed],
                        np.float32) / 255.0
    else:
        stops = np.array([e[0] for e in table], np.float32) / 65535.0
        vals = np.array([e[1] for e in table], np.float32) / 65535.0
    t = np.clip(ctx.sample(v, 0, pos_grid(W, H))[:, :1], 0.0, 1.0).ravel()
    if vals.ndim == 2:
        out = np.stack([np.interp(t, stops, vals[:, c]).astype(np.float32)
                        for c in range(vals.shape[1])], axis=-1)
    else:
        out = np.interp(t, stops, vals).astype(np.float32).reshape(N, 1)
    return to_image(out, N, H, W)


@filt('curve')
def f_curve(ctx, v):
    """A cubic Bezier transfer curve, sampled to a lookup and applied per channel."""
    knots = v.rec.curve_points
    if not knots or len(knots) < 2:
        raise Unsupported('curve record carries no readable spline')
    W, H = v.size(ctx.cap)
    N = W * H
    src = np.clip(ctx.sample(v, 0, pos_grid(W, H)), 0.0, 1.0)
    TAPS = 1024
    xs, ys = [], []
    for k in range(len(knots) - 1):
        p0, p1 = (knots[k][0], knots[k][1]), (knots[k][4], knots[k][5])
        p2, p3 = (knots[k + 1][2], knots[k + 1][3]), (knots[k + 1][0], knots[k + 1][1])
        u = np.linspace(0.0, 1.0, TAPS // max(1, len(knots) - 1), dtype=np.float32)
        b0, b1 = (1 - u) ** 3, 3 * u * (1 - u) ** 2
        b2, b3 = 3 * u * u * (1 - u), u ** 3
        xs.append(b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0])
        ys.append(b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1])
    cx, cy = np.concatenate(xs), np.concatenate(ys)
    order = np.argsort(cx)
    out = np.interp(src.ravel(), cx[order], cy[order]).astype(np.float32)
    return to_image(out.reshape(src.shape), N, H, W)


@filt('warp')
def f_warp(ctx, v):
    """Displace input 0 by the GRADIENT of input 1, scaled by `intensity`."""
    if len(v.inputs) < 2:
        raise Unsupported('warp has fewer than 2 edges')
    p = v.params.get('intensity')
    if p is None:
        raise Unsupported('warp stores no intensity: neither class bit 13 (baked) nor 14 '
                          '(program) is set, so the source omitted it')
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    if p.kind == 'baked':
        intensity = float(p.value)
        if not (intensity == intensity and -1e3 < intensity < 1e3):
            raise Unsupported('warp intensity is not a plausible float (%r)' % intensity)
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size != 1 or not np.isfinite(got[0]):
            raise Unsupported('warp intensity program does not evaluate to a scalar')
        intensity = float(got[0])
    gmap = to_image(ctx.sample(v, 1, pos), N, H, W)[:, :, 0].astype(np.float32)
    gy, gx = np.gradient(gmap)
    ref = _reference_px(v)
    in_pos = pos + np.concatenate([(gx * W / ref * intensity).reshape(N, 1),
                                   (gy * H / ref * intensity).reshape(N, 1)], axis=-1)
    return to_image(sampler(ctx.src(v, 0))(in_pos), N, H, W)


@filt('emboss')
def f_emboss(ctx, v):
    """Input 0 plus a directional difference of input 1 -- a lit relief."""
    if len(v.inputs) < 2:
        raise Unsupported('emboss has fewer than 2 edges')
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    base = to_image(ctx.sample(v, 0, pos), N, H, W)
    smp = sampler(ctx.src(v, 1))
    OFF = 0.005859375
    g0 = to_image(smp(pos), N, H, W)[:, :, :1]
    g1 = to_image(smp(pos + np.array([OFF, -OFF], np.float32)), N, H, W)[:, :, :1]
    k = 0.1
    if assume.assumed('emboss.intensity') == 'program':
        for q in ctx.walk_programs(v):
            try:
                got = np.asarray(ctx.run(v, q, 1)).ravel()
            except Exception:
                continue
            if got.size and np.isfinite(got[0]):
                k = float(got[0])
                break
        assume.note(v.index)
    return np.clip(base + k * (g0 - g1), 0.0, 1.0)


@filt('distance')
def f_distance(ctx, v):
    """A distance field grown from the mask input, out to a radius the record states.

    The radius LOCATION is `distance.distance_param`, which is the one read in this
    renderer still carrying a fallback of its own -- see FORMAT-NOTES' L6. Every record it
    answers for is marked low-confidence, so the fallback is visible in the output rather
    than folded into it.
    """
    import distance as dist
    # THE RADIUS IS A NAMED FIELD NOW, where the source could see it: SandyStonePath states
    # 56.3 and 64.22 and records 3 and 180 hold exactly those at w1 field 0. The locator
    # below stays for the one case the source cannot reach -- field 1 holding a PROGRAM,
    # where the walk's placement is unverified and reads a pointer as 0.0 while the locator
    # evaluates the program and returns 1.0 or 0.29. That case is 188 corpus records and it
    # is chosen on the record's own state bits, not on how the value looks.
    p = v.params.get('distance')
    f1_program = ((v.words[1] >> 2) & 3) == 2 if len(v.words) > 1 else False
    val = how = None
    if p is not None and not f1_program:
        if p.kind == 'baked':
            val, how = float(p.value), 'walked'
        else:
            got = np.asarray(ctx.run(v, p.value, 1)).ravel()
            if got.size and np.isfinite(got[0]):
                val, how = float(got[0]), 'walked'
    if val is None:
        try:
            val, how = dist.distance_param(
                v.rec, lambda p_: ctx.run(v, p_, 1), {})
        except dist.Unlocated as e:
            raise Unsupported('distance: %s' % e) from e
        if dist.is_low_confidence(how):
            ctx.low_confidence.add(v.index)
    W, H = v.size(ctx.cap)
    pos = pos_grid(W, H)
    mask_edge = assume.assumed('distance.mask_edge', 0)
    if mask_edge >= len(v.inputs) or v.edge(mask_edge) not in ctx.outputs:
        mask_edge = 0
    if assume.assumed('distance.mask_edge') is not None:
        assume.note(v.index)
    mask = ctx.sample(v, mask_edge, pos).reshape(H, W, -1)[:, :, 0]
    field = dist.distance_field(mask, dist.scale_radius(val, W))
    if assume.assumed('distance.invert', False):
        field = 1.0 - field
        assume.note(v.index)
    payload = next((e for k, e in enumerate(v.inputs)
                    if k != mask_edge and e in ctx.outputs), None)
    if assume.assumed('distance.propagate', 'field') == 'nearest' and payload is not None:
        src = sampler(ctx.outputs[payload])(pos).reshape(H, W, -1)
        vals = dist.propagate(mask, dist.scale_radius(val, W), src)
        assume.note(v.index)
        return to_image((vals * field[:, :, None]).reshape(H * W, -1), W * H, H, W)
    return to_image(field.reshape(-1, 1), W * H, H, W)


@filt('dyngradient')
def f_dyngradient(ctx, v):
    """Input 0 indexes into input 1, which is a one-row (or one-column) ramp image."""
    if len(v.inputs) < 2:
        raise Unsupported('dyngradient has fewer than 2 edges')
    W, H = v.size(ctx.cap)
    idx = ctx.sample(v, 0, pos_grid(W, H)).reshape(H, W, -1)[:, :, 0]
    strip = np.asarray(ctx.src(v, 1), np.float32)
    if strip.ndim == 2:
        strip = strip[:, :, None]
    sh, sw = strip.shape[0], strip.shape[1]
    along_x = sw >= sh
    n = sw if along_x else sh
    k = np.clip((np.clip(idx, 0.0, 1.0) * (n - 1)).round().astype(int), 0, n - 1)
    mid = (sh // 2) if along_x else (sw // 2)
    ramp = strip[mid, :, :] if along_x else strip[:, mid, :]
    return to_image(ramp[k.ravel()], W * H, H, W)
