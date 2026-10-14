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

import math
import struct
import re

import numpy as np

import assume
import manifest
import sbsruntime

# `text` (filter 17) is a module of its own: its string and its font are RESOURCES in the
# file's head segment rather than record words, and its legend entry is not in mask order.
import text  # noqa: E402

from ops import (
    nearest_sampler,
    Unsupported,
    blend,
    footprint_scale,
    pos_grid,
    prefilter,
    sampler,
    to_image,
)

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
    "grayscale.weights": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, 0.0),
    "uniform.fill": 0.0,
    "levels.in": (0.0, 0.5, 1.0),
    "levels.out": (0.0, 1.0),
}

FILTERS = {}


def filt(name):
    def wrap(fn):
        FILTERS[name] = fn
        return fn

    return wrap


FILTERS["text"] = text.f_text


def _scalar(ctx, v, name, default, W, H, pos):
    """A named parameter as a number or an (N, 1) field. Baked, program, or the default."""
    p = v.params.get(name)
    if p is None:
        return np.float32(default)
    if p.kind == "baked":
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
    return to_image(ctx.run(v, p.value, W * H, pos=pos), W * H, H, W).reshape(
        W * H, -1
    )[:, :1]


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
    if p.kind == "baked":
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
    if p.kind == "baked":
        vals = (p.value,) if p.width == 1 else tuple(p.value)
        return vals if len(vals) == width else None
    out = np.asarray(ctx.run(v, p.value, 1)).ravel()
    return tuple(float(x) for x in out) if out.size == width else None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


@filt("bitmap")
def f_bitmap(ctx, v):
    b = v.rec.bitmap
    if b is None:
        raise Unsupported("bitmap record states no payload")
    if b["kind"] == "pixels":
        return _pixels(ctx, v, b)
    if b["kind"] == "graph_input":
        got = _graph_input_default(ctx, v)
        if got is not None:
            ctx.low_confidence.add(v.index)
            return got
        raise Unsupported(
            "bitmap is a graph image input and the package ships no image "
            "and declares no default"
        )
    raise Unsupported("bitmap kind %r has no supplied output" % b["kind"])


def _pixels(ctx, v, b):
    asm = ctx.asm
    off, size, ch, depth = b["offset"], b["size"], b["channels"], b["depth"]
    if b.get("compressed") == "jpeg":
        import io
        import struct
        from PIL import Image

        p = b["data_offset"]
        if asm.data[p : p + 3] != b"\xff\xd8\xff":
            raise Unsupported("bitmap is flagged JPEG but has no JPEG stream at +52")
        n = struct.unpack_from("<I", asm.data, p - 4)[0]
        try:
            im = Image.open(io.BytesIO(asm.data[p : p + n]))
            im.load()
        except Exception as e:
            raise Unsupported("bitmap's JPEG payload will not decode: %s" % e)
        got = {"L": 1, "RGB": 3, "RGBA": 4}.get(im.mode)
        if got is None:
            raise Unsupported("bitmap's JPEG has an unhandled mode %r" % im.mode)
        if (im.size[0], im.size[1]) != (v.width, v.height):
            raise Unsupported(
                "bitmap's JPEG is %dx%d, record declares %dx%d"
                % (im.size[0], im.size[1], v.width, v.height)
            )
        return (np.asarray(im, dtype=np.float32) / 255.0).reshape(
            v.height, v.width, got
        )
    if depth is None:
        raise Unsupported("bitmap has pixels but an undecoded channel code")
    if off + size > len(asm.data):
        raise Unsupported(
            "bitmap wants %d bytes at %d, file holds %d"
            % (size, off, max(0, len(asm.data) - off))
        )
    arr = np.frombuffer(
        asm.data[off : off + size], dtype="<u1" if depth == 8 else "<u2"
    )
    ch = ch if (ch and ch > 1) else 1
    return arr.reshape(v.height, v.width, ch).astype(np.float32) / float(
        (1 << depth) - 1
    )


def _graph_input_default(ctx, v):
    """The manifest's substitute for an unconnected image input, as a uniform, or None."""
    uid = (v.rec.bitmap or {}).get("uid")
    got = manifest.image_input_defaults(ctx.asm).get(uid)
    if got is None:
        return None
    try:
        parts = [float(x) for x in got[0].replace(";", ",").split(",") if x.strip()]
    except ValueError:
        return None
    if not parts:
        return None
    n = 4 if v.colour else 1
    vals = ([parts[0]] * n) if len(parts) == 1 else (parts + [parts[-1]] * n)[:n]
    return np.zeros((v.height, v.width, n), np.float32) + np.asarray(vals, np.float32)


@filt("uniform")
def f_uniform(ctx, v):
    W, H = v.size(ctx.cap)
    n = 4 if v.colour else 1
    col = _vector(ctx, v, "outputcolor", 4)
    if col is None:
        col = _vector(ctx, v, "outputcolor", n)
    if col is None:
        # NO BAKED FILL AND NO PROGRAM AT THE NAMED SLOT. The class word says the source
        # set no colour, so the engine's default applies -- and a `uniform` still carries
        # its SIZE expression, which is a different slot and must not be read as a fill.
        prog = _fill_program(ctx, v)
        if prog is not None:
            col = prog
        else:
            fill = assume.assumed("uniform.fill", DEFAULTS["uniform.fill"])
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
        if (
            out.size >= n
            and np.all(np.isfinite(out[:n]))
            and np.all((out[:n] >= -0.01) & (out[:n] <= 1.01))
        ):
            return tuple(float(x) for x in out[:n])
    return None


@filt("fxmaps")
def f_fxmaps(ctx, v):
    import fx

    return fx.render_fxmaps(ctx, v)


# ---------------------------------------------------------------------------
# Per-pixel programs
# ---------------------------------------------------------------------------



_DEAD_SAMPLER = {}
_DEF_RE = re.compile(r"^\s*%(\d+)\s+[0-9A-F]{4}\s+(\S+?)\s+(.*)$")


def annihilated_samplers(asm, ptr):
    """Sampler indices whose EVERY use in the program at `ptr` is a multiply by a constant
    zero -- reads whose binding cannot change the program's output.

    The proof `archive/tools/render.py::sampler_is_annihilated` reads off the bytecode,
    carried to the renderer of record. A source graph with a trailing UNCONNECTED input
    slot compiles to a sample of index == arity that the program then multiplies away
    (`%20 samplelum %19, #3; %21 const 0; %22 mul %20, %21`); refusing it for want of a
    binding was refusing a record whose output is the same for any image bound there.
    SandyStonePath record 177 is one -- the Flood Fill to Gradient's fourth, unwired
    input -- and 995 of the pack's 1,778 records cascaded from that one refusal, five of
    its six reference maps with them. A LIVE read of an unwired input still refuses: what
    the engine substitutes for it is not known from the file.
    """
    key = (getattr(asm, "path", id(asm)), ptr)
    got = _DEAD_SAMPLER.get(key)
    if got is not None:
        return got
    import disasm

    try:
        hi = asm.program_end(ptr)
        lines = disasm.text(asm.data, ptr, hi).splitlines()
    except Exception:
        _DEAD_SAMPLER[key] = frozenset()
        return _DEAD_SAMPLER[key]
    defs = {}
    for ln in lines:
        m = _DEF_RE.match(ln)
        if m:
            defs[int(m.group(1))] = (m.group(2), m.group(3))
    def _is_zero(ar):
        # A constant the disassembler cannot print shows as `?`; that is not a zero.
        try:
            toks = [t.strip() for t in ar.split(",")]
            return bool(toks) and all(t and float(t) == 0.0 for t in toks)
        except ValueError:
            return False

    zero = {g for g, (op, ar) in defs.items() if op.startswith("const") and _is_zero(ar)}
    by_index = {}
    for g, (op, ar) in defs.items():
        if op.startswith("sample"):
            ims = re.findall(r"#(\d+)", ar)
            if ims:
                by_index.setdefault(int(ims[0]), set()).add(g)
    uses = {}
    for g, (op, ar) in defs.items():
        for u in re.findall(r"%(\d+)", ar):
            uses.setdefault(int(u), []).append((op, ar))
    dead = set()
    for index, targets in by_index.items():
        ok = True
        for t in targets:
            for op, ar in uses.get(t, ()):
                others = [int(x) for x in re.findall(r"%(\d+)", ar) if int(x) != t]
                if not op.startswith("mul") or not any(o in zero for o in others):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            dead.add(index)
    _DEAD_SAMPLER[key] = frozenset(dead)
    return _DEAD_SAMPLER[key]



class _ZeroSlots(dict):
    """A slot frame whose unset entries read as 0.0; see `f_pixelprocessor`."""

    def __missing__(self, key):
        return np.float32(0.0)


@filt("pixelprocessor")
def f_pixelprocessor(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    saved = dict(sbsruntime.SAMPLERS)
    sbsruntime.SAMPLERS.clear()
    # THE SAMPLER A PIXEL PROGRAM READS ITS INPUTS THROUGH, behind `pixelprocessor.sample`.
    # `bilinear` is the shared sampler every filter uses; `nearest` returns the texel
    # whose centre is nearest, which is what a program that stores offsets or cell sizes
    # in its channels and reads them back at `$pos + k texels` needs (the flood fill of
    # Bricks graph 001, records 10175-10252). See `ops.nearest_sampler`.
    make = sampler
    if assume.assumed("pixelprocessor.sample", "nearest") == "nearest":
        make = nearest_sampler
        assume.note(v.index)
    try:
        for k in range(len(v.inputs)):
            # AN UNWIRED EDGE IS NOT BOUND, and is not a refusal here: whether the
            # program reads it decides -- an annihilated read is bound to zeros below, a
            # live one raises `MissingSampler` at the point of use. Refusing every record
            # with a gap in its edge list ("input 0 is not wired", 14 corpus files)
            # refused programs that never sample the gap.
            if v.edge(k) is None:
                continue
            sbsruntime.SAMPLERS[k] = make(ctx.src(v, k))
        for k, src in ctx.sampler_bindings(v).items():
            if k not in sbsruntime.SAMPLERS:
                sbsruntime.SAMPLERS[k] = make(ctx.outputs[src])
                ctx.low_confidence.add(v.index)
        # THE PIXEL PROGRAM IS THE LAST HEADER SLOT, which is the record layout model read
        # straight: [tag][arity][inputs][one slot per set class bit][the filter's own].
        # `decompose` used to place it BEFORE the class slots for this filter, and the two
        # orderings give the same header length so no length check separates them -- but
        # the contents do. Rokviz record 24 has a 5-word header whose slot 3 is
        # `inputref($randomseed)`, an INHERITED parameter, and whose slot 4 is the pixel
        # program; taking slot 3 renders the record as a constant and blackens the mask
        # that carries the whole basecolor pattern.
        #
        # THE WALK AGREES NOW, so `v.prog_slot` and `v.header_end - 1` are the same word on
        # every record whose arity the walk accepts, and this local workaround has stopped
        # being one. It is kept as the primary read because it does not depend on the walk
        # being right about which of two adjacent slots is which -- the same reason it was
        # written -- and because `prog_slot` is None on the 807 records whose arity field
        # the walk declines. See FORMAT-NOTES.md, "Every filter, bit by bit".
        progs = ctx.walk_programs(v, include_prog_slot=True)
        main = ctx.prog_at(v, (v.header_end - 1) if v.header_end else None)
        if main is None:
            main = ctx.prog_at(v, v.prog_slot)
        if main is None and progs:
            main = progs[-1]
        if main is None:
            raise Unsupported("pixelprocessor names no program")
        # AN ANNIHILATED READ OF AN UNBOUND SAMPLER IS BOUND TO ZERO, by proof; see
        # `annihilated_samplers`. Nothing that rendered before reaches this line with a
        # different result, because a bound index is never rebound here.
        for k in annihilated_samplers(ctx.asm, main):
            if k not in sbsruntime.SAMPLERS:
                sbsruntime.SAMPLERS[k] = lambda pos: np.zeros((len(pos), 1), np.float32)
        if main not in progs:
            progs = progs + [main]
        # AN UNSET SLOT READS AS ZERO in a pixel program, behind `pixelprocessor.unset`.
        # The record's own programs seed the frame (below), and what a program reads past
        # that is a variable no `set` reached first -- an accumulator's initial value
        # (OnyxSubstance001 record 1470, a 21,643-line program whose first touch of slot
        # 48 is `clamp(slots[48], 3)` inside `select(cond, f(slots[48]), slots[48])`),
        # which the engine reads as 0. `refuse` keeps the diagnostic that found the
        # slot-frame model; it is the arm now, for the FX-Map path is unchanged and
        # still raises, where the frame model is what a refusal is about.
        slots = (
            _ZeroSlots()
            if assume.assumed("pixelprocessor.unset", "zero") == "zero"
            else {}
        )
        # `$outputsize` DESCRIBES THE SAME GRID AS `$size` AND `$pos`, for this record's
        # programs, behind `pixelprocessor.outputsize`. `Context.run` already hands the
        # image program the grid it is drawn on as `$size`, for the reason stated there;
        # a record that derives its texel from `$outputsize` instead -- in its prologue,
        # `0.5 / 2^os` into a slot (Bricks' flood-fill seed 10175; RoofTiles'
        # height-to-normal 2599) -- was still told the export size, and on a 256-px grid
        # under `$outputsize` 11 its neighbour tap is an eighth of a pixel: no edge is
        # ever found, the normal is flat 0.5. `grid` hands these programs log2 of the
        # grid. Every other record's programs still read the render's.
        # ONLY FOR A RECORD THAT IS THE CANVAS. A pixel processor pinned to its own size
        # is not stepping the canvas by texels: ChesterfieldSofa 364, an HBAO gradient LUT
        # at 2048 x 16 at every output size, reads `$outputsize` to turn a per-pixel slope
        # back into a per-canvas one (see `Context.graph_inputs`), and handing it the grid
        # flattened the pack's AO (band 0.0007, dc +0.11 on the ratchet). The record's
        # declared size against the render's `$outputsize` is the test; a canvas-sized
        # record is one whose size IS `2^$outputsize`.
        # `own` (an arm, refused): a non-canvas record's programs read log2 of its OWN
        # size, the engine's per-node `$outputsize`. It flattens Chesterfield's AO (band
        # 0.0007): the HBAO's mip pyramid (64 -> 1 px) and its 2048 x 16 LUT read
        # `$outputsize` to mean the GRAPH's, as `grid` gives them. And it was not what
        # graph 001's flood fill needed (`blur.reference_px` was).
        gi = None
        mode = assume.assumed("pixelprocessor.outputsize", "grid")
        # EVERY `$outputsize` uid, because a package declares one per graph and this
        # record may belong to any of them -- see `engine.outputsize_uids`.
        if mode in ("grid", "own") and ctx._os_uids and ctx.outputsize is not None:
            canvas = (v.width, v.height) == (
                2 ** int(ctx.outputsize[0]),
                2 ** int(ctx.outputsize[1]),
            )
            if canvas:
                gi = {u: (math.log2(W), math.log2(H)) for u in ctx._os_uids}
                assume.note(v.index)
            elif mode == "own" and v.width and v.height:
                gi = {u: (math.log2(v.width), math.log2(v.height)) for u in ctx._os_uids}
                assume.note(v.index)
        for p in progs:
            if p != main:
                try:
                    ctx.run(v, p, 1, slots=slots, inputs=gi)
                except Unsupported:
                    pass
        pos = pos_grid(W, H)
        # `rand` PER PIXEL, behind `pixelprocessor.rand`. The hash in `sbsruntime.rand`
        # takes `$number` (0 here) and `CONTEXT['salt']` (0.0 outside the FX tree
        # runner), so a pixel program's `rand` is one draw for the whole image under the
        # default. `pixel` salts it by the pixel's row-major index plus one, the same
        # third input the FX tree runner uses per region, and clears it after -- so a
        # program that is only `rand(1)` is a white noise at one draw per pixel. Bricks
        # 10080 is the specimen (`0.001 + rand(0.999)`, no inputs), sampled by 10253
        # once per flood-fill cell; see FORMAT-NOTES.md, "Record 10253 is not the fault".
        salted = assume.assumed("pixelprocessor.rand", "pixel") == "pixel"
        if salted:
            sbsruntime.CONTEXT["salt"] = np.arange(1, N + 1, dtype=np.float64).reshape(
                -1, 1
            )
            assume.note(v.index)
        try:
            out = ctx.run(v, main, N, slots=slots, pos=pos, W=W, H=H, inputs=gi)
        finally:
            if salted:
                sbsruntime.CONTEXT["salt"] = 0.0
        return to_image(out, N, H, W)
    finally:
        sbsruntime.SAMPLERS.clear()
        sbsruntime.SAMPLERS.update(saved)


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


@filt("blend")
def f_blend(ctx, v):
    mode = (v.rec.slot1_flags or {}).get("blendingmode")
    if mode is None:
        raise Unsupported("blend record states no readable blendingmode")
    if len(v.inputs) < 2:
        raise Unsupported("blend has fewer than 2 edges")
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    dst = ctx.sample(v, 0, pos)
    src = ctx.sample(v, 1, pos)
    if dst.shape[-1] != src.shape[-1]:
        raise Unsupported(
            "blend inputs disagree on channel count (%d vs %d)"
            % (dst.shape[-1], src.shape[-1])
        )
    # OPACITY IS `opacitymult` OR 1.0, AND NOTHING ELSE. The old reader fell back to the
    # size-expression slot when the parameter was absent, which is where its 1,004
    # size-expression misattributions came from: an absent field means the source left the
    # multiplier at 1, not that the number is somewhere else.
    opacity = _scalar(ctx, v, "opacitymult", 1.0, W, H, pos)
    opacity = (
        np.asarray(opacity, np.float32).reshape(-1, 1)
        if np.ndim(opacity)
        else np.full((N, 1), float(opacity), np.float32)
    )
    if len(v.inputs) > 2 and v.inputs[2] is not None:
        opacity = opacity * ctx.sample(v, 2, pos)[:, :1]
    return to_image(blend(mode, dst, src, opacity), N, H, W)


@filt("transformation")
def f_transformation(ctx, v):
    W, H = v.size(ctx.cap)
    m = _vector(ctx, v, "matrix22", 4)
    if m is None:
        if v.has("matrix22"):
            raise Unsupported("matrix22 is a program that does not evaluate 4-wide")
        m = (1.0, 0.0, 0.0, 1.0)
    off = _vector(ctx, v, "offset", 2)
    if off is None:
        if v.has("offset"):
            raise Unsupported("offset is a program that does not evaluate 2-wide")
        off = (0.0, 0.0)
    # THE FOUR WORDS ARE COLUMN-MAJOR. Read as rows -- `x_in = m0 x + m1 y` -- a 90-degree
    # rotation turns the wrong way: RoofTiles record 62 (`0, -1, 1, 0`) lays its shingle
    # rows in place but with every shingle's gradient upside down, height corr -0.79
    # against the reference at the exported tile counts, +0.81 read as columns. Scales
    # and flips are symmetric, so Bricks is bit-identical either way, Auras and
    # SandyStonePath unchanged, Chesterfield +0.007 (normal ch2 +0.05). `rows` keeps the
    # old reading. See FORMAT-NOTES.md, "RoofTiles: the shingles are upside down".
    if assume.assumed("transformation.matrix", "columns") == "rows":
        m = (m[0], m[2], m[1], m[3])
        assume.note(v.index)
    src = np.asarray(ctx.src(v, 0))
    if (
        SHIFTED_TAPS
        and tuple(float(x) for x in m) == (1.0, 0.0, 0.0, 1.0)
        and src.ndim == 3
        and src.shape[:2] == (H, W)
    ):
        # AN IDENTITY MATRIX IS A SHIFT, and it is 92% of Bricks' 2,639 transformations
        # (842 with no offset at all, 1,592 offset-only, most by a whole pixel). `in_pos` is
        # then `pos + off`, which `_shift_lerp` reads as rolls instead of a gather.
        return _shift_lerp(
            src.astype(np.float32, copy=False), float(off[0]) * W, float(off[1]) * H
        )
    c = pos_grid(W, H) - 0.5
    in_pos = np.stack(
        [
            m[0] * c[:, 0] + m[2] * c[:, 1] + 0.5 + off[0],
            m[1] * c[:, 0] + m[3] * c[:, 1] + 0.5 + off[1],
        ],
        axis=-1,
    )
    scale = footprint_scale(m, W, H, src.shape)
    if scale >= 2.0:
        src = prefilter(src, scale)
    return to_image(sampler(src)(in_pos), W * H, H, W)


@filt("shuffle")
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
        w = _vector(ctx, v, "channelsweights", 4)
        if w is None:
            w = assume.assumed("grayscale.weights", DEFAULTS["grayscale.weights"])
            ctx.low_confidence.add(v.index)
            assume.note(v.index)
        hot = np.asarray(w, np.float32).ravel()
        if hot.size != 4 or not np.all(np.isfinite(hot)):
            raise Unsupported(
                "channelsweights is not four finite numbers (%r)"
                % (np.round(hot, 4).tolist(),)
            )
        src = ctx.sample(v, 0, pos)
        used = [k for k, x in enumerate(hot) if abs(x) > 1e-9]
        if used and max(used) >= src.shape[-1]:
            # A WEIGHT ON A CHANNEL THE INPUT DOES NOT HAVE. Not clamped: the source image
            # is three channels or one, and weighting a fourth means reading padding this
            # renderer invented -- the exact error that made a fitted weight vector look
            # like the best candidate on this file's own arbiter.
            raise Unsupported(
                "channelsweights weights channel %d of an input with only %d"
                % (max(used), src.shape[-1])
            )
        w4 = hot[: src.shape[-1]]
        return to_image((src * w4).sum(axis=-1, keepdims=True), N, H, W)

    w1 = v.words[1] if len(v.words) > 1 else 0
    sels = [(w1 >> (8 * k)) & 0xFF for k in range(4)]
    if not all(s <= 7 for s in sels):
        raise Unsupported("shuffle selector word %#010x is not four selectors" % w1)
    nout = 4 if v.colour else 1
    cols = []
    cache = {}
    for s in sels[:nout]:
        k, c = s // 4, s % 4
        if k >= len(v.inputs) or v.inputs[k] is None:
            raise Unsupported(
                "shuffle wants input %d, which this record does not have" % (k + 1)
            )
        a = cache.setdefault(k, ctx.sample(v, k, pos))
        if c >= a.shape[-1]:
            raise Unsupported(
                "shuffle selects channel %d of an input with only %d" % (c, a.shape[-1])
            )
        cols.append(a[:, c : c + 1])
    return to_image(np.concatenate(cols, axis=-1), N, H, W)


# ---------------------------------------------------------------------------
# Tone
# ---------------------------------------------------------------------------


@filt("levels")
def f_levels(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    src = ctx.sample(v, 0, pos)
    nchan = src.shape[-1]

    def par(name, default):
        return _channelwise(ctx, v, name, default, W, H, pos, nchan)

    lo = par("levelinlow", DEFAULTS["levels.in"][0])
    mid = par("levelinmid", DEFAULTS["levels.in"][1])
    hi = par("levelinhigh", DEFAULTS["levels.in"][2])
    out_lo = par("leveloutlow", DEFAULTS["levels.out"][0])
    out_hi = par("levelouthigh", DEFAULTS["levels.out"][1])

    # A ZERO-WIDE INPUT SPAN IS A THRESHOLD, not a division to guard against, and it is
    # how this format writes a hard binarisation: `levelinlow == levelinhigh` with the
    # OUTPUT range reversed (leveloutlow 1, levelouthigh 0) is "1 below the threshold".
    # Rokviz record 34 is exactly that, and reading it as an identity exchanges the two
    # palette branches of the whole material.
    span = hi - lo
    degenerate = np.abs(span) < 1e-6
    safe = np.where(degenerate, 1.0, span)
    ramp = np.clip((src - lo) / safe, 0.0, 1.0)
    if assume.assumed("levels.zerospan") == "identity":
        step = np.clip(src, 0.0, 1.0)
        if np.any(degenerate):
            assume.note(v.index)
    else:
        step = (src >= lo).astype(np.float32)
    t = np.where(degenerate, step, ramp)

    m = np.clip(mid, 1e-4, 1 - 1e-4)
    linear = np.abs(m - 0.5) < 1e-6
    with np.errstate(all="ignore"):
        expo = np.log(0.5) / np.log(m)
        if np.all(linear):
            # `gamma` would be discarded at every pixel: skip it, keep `where`'s dtype/shape.
            shape = np.broadcast_shapes(np.shape(linear), np.shape(t), np.shape(expo))
            t = np.broadcast_to(t, shape).astype(np.result_type(t, expo))
        else:
            t = np.where(linear, t, np.power(t, expo))
    return to_image(np.clip(out_lo + t * (out_hi - out_lo), 0.0, 1.0), N, H, W)


@filt("normal")
def f_normal(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    p = v.params.get("intensity")
    if p is None:
        d = assume.assumed("normal.default_intensity", 1.0)
        if d == "refuse":
            raise Unsupported(
                "normal stores no intensity (its w1 field is absent), so the "
                "source omitted it and the engine default applies"
            )
        intensity = float(d)
        ctx.low_confidence.add(v.index)
        assume.note(v.index)
    elif p.kind == "baked":
        intensity = float(p.value)
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size < 1 or not np.isfinite(got[0]):
            raise Unsupported("normal intensity program does not evaluate to a scalar")
        intensity = float(got[0])

    height = to_image(ctx.sample(v, 0, pos), N, H, W)[:, :, 0].astype(np.float32)
    # `np.gradient` is per RENDER pixel and the engine's slope is per 256 pixels, FIXED.
    # This used to read `_reference_px(v)`, i.e. the record's own width, on the reasoning
    # that "the engine differences adjacent pixels at the record's own resolution". That is
    # the half of it that is right; what it misses is that the engine then expresses the
    # result against a CONSTANT 256-px grid, so the normal a record produces does not depend
    # on the size the record is evaluated at. The engine's own exports say so directly, and
    # the measurement needs no render of ours:
    #
    #   for each reference pack, take the exported HEIGHT and NORMAL maps at their native
    #   size R, undo the levels between the normal node's input and the height output (a
    #   pure linear gain g), and regress the map's own slope nx/nz on -d(height)/d(pixel):
    #
    #     Chesterfield  R=2048  I=10.0   g=0.5     K measured 160.005 / 159.999  corr 0.982
    #     Rokviz        R=4096  I=0.25   g=0.4253  K measured   9.397 /   9.398  corr 0.725
    #
    #   predicted K = (I/g) * (R/256):  160.000 and 9.405   -- 0.003% and 0.09% out
    #   predicted K = (I/g)          :   20.000 and 0.588   -- out by 8x and 16x, i.e. R/256
    #
    # So the rule is `slope = intensity * dH/du / 256` with u the normalised coordinate,
    # which in render-pixel terms is `gradient * W / 256`. Two packs, two export sizes, two
    # intensities three orders of magnitude apart, and the ratio between the two hypotheses
    # is exactly R/256 in both.
    #
    # CONFIRMED IN THE RENDER, at four sizes, and the ratio form needs neither I nor g. Run
    # the same regression on OUR OWN two outputs -- no reference in the loop -- and K comes
    # out at exactly (I/g)*(W/256) with correlation 1.000: 10.000 / 20.001 / 40.000 / 80.000
    # at max_dim 128 / 256 / 512 / 1024 against 10 / 20 / 40 / 80 predicted. K is
    # proportional to the size the map is drawn at, so `K_ref / K_ours == R_ref / R_ours`
    # with the intensity and the levels gain cancelling, which travels to a pack whose I and
    # g are unknown: Chesterfield 8.000 against 8.000, and Bricks graphs 004 and 005 3.987
    # and 3.984 against 4.000. Three graphs, two packages, 0.4% or better.
    #
    # WHAT THIS DOES NOT SEPARATE, because both reference packs' normal records carry a
    # 256x256 tag: a hard 256, the record's TAG width, and `1 << declared $outputsize` are
    # all 256 there. A hard 256 is taken because it makes the filter resolution-independent,
    # which is the only one of the three an engine could implement without consulting a
    # graph input's DEFAULT; `blur`'s [0,256] clamp and `distance`'s exact-256 radii say the
    # same constant is the format's. 320 of 1,379 corpus `normal` records have a tag that is
    # not 256 and no reference pack covers one; `assume.QUESTIONS['normal.reference_px']`
    # holds 'record' for anyone who wants to put the old reading back.
    #
    # THE TAG AND THE DECLARED SIZE STAY TIED -- both are file properties and neither moves
    # when a caller renders at another `$outputsize`. What DOES move is `v.width`, which is
    # the record's size AT THE SIZE BEING RENDERED, so the 'record' arm is a fourth reading
    # rather than one of those three, and scoring at the implied `$outputsize` separated it:
    # record 121 of ChesterfieldSofa is a 256 tag that evaluates to 2048 at (11, 11). Scored
    # there, `'record'` takes normal ch0 to MAE 0.0650 / sd 0.0169 / fit y=5.432x against
    # 0.0332 / 0.1207 / y=0.764x, and mean Z back to the flat 0.9993 against the export's
    # 0.9659. Its CORRELATION barely moves (+0.9524 -> +0.9488), so the fit slope is what
    # sees this and a correlation floor alone would not.
    ref = _normal_reference_px(v)
    gy, gx = np.gradient(height)
    gx, gy = gx * (W / ref), gy * (H / ref)
    # FIELD 1 IS A TWO-BIT CODE, NOT A BIT. Reading `(w1 >> 2) & 1` sees state 01 and calls
    # state 10 absent, so a program-valued inversedy -- which is how the sources actually
    # write it, `normal_format == <int>` off a graph input -- reads as "not inverted" and
    # its program is never run. That the field IS inversedy remains an assumption; that it
    # has two arms is the walk's own declaration.
    inv = v.params.get("inversedy")
    if assume.assumed("normal.inversedy", "field1") != "ignore" and inv is not None:
        if inv.kind == "baked":
            flip = True
        else:
            got = np.asarray(ctx.run(v, inv.value, 1)).ravel()
            if got.size < 1 or not np.isfinite(got[0]):
                raise Unsupported(
                    "normal inversedy program does not evaluate to a scalar"
                )
            flip = bool(got[0] > 0.5)
        if flip:
            gy = -gy
        ctx.low_confidence.add(v.index)
        assume.note(v.index)
    nx, ny = -gx * intensity, -gy * intensity
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack(
        [0.5 + 0.5 * nx / ln, 0.5 + 0.5 * ny / ln, 0.5 + 0.5 * nz / ln], axis=-1
    ).reshape(N, 3)
    rgb = np.clip(rgb, 0.0, 1.0)
    if v.colour:
        rgb = np.concatenate([rgb, np.ones((N, 1), np.float32)], axis=-1)
    return to_image(rgb, N, H, W)


@filt("hsl")
def f_hsl(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    src = ctx.sample(v, 0, pos)
    h = _scalar(ctx, v, "hue", 0.5, W, H, pos)
    s = _scalar(ctx, v, "saturation", 0.5, W, H, pos)
    lu = _scalar(ctx, v, "luminosity", 0.5, W, H, pos)
    rgb = src[:, :3] if src.shape[-1] >= 3 else np.repeat(src[:, :1], 3, axis=1)
    mx, mn = rgb.max(axis=1, keepdims=True), rgb.min(axis=1, keepdims=True)
    lum = 0.5 * (mx + mn)
    with np.errstate(all="ignore"):
        sat = np.where(
            mx == mn, 0.0, (mx - mn) / np.where(lum < 0.5, mx + mn, 2.0 - mx - mn)
        )
        hue = np.zeros_like(lum)
        d = mx - mn
        r, g, b = rgb[:, :1], rgb[:, 1:2], rgb[:, 2:3]
        hue = np.where(mx == r, (g - b) / np.where(d == 0, 1, d) % 6.0, hue)
        hue = np.where(mx == g, (b - r) / np.where(d == 0, 1, d) + 2.0, hue)
        hue = np.where(mx == b, (r - g) / np.where(d == 0, 1, d) + 4.0, hue)
        hue = np.where(d == 0, 0.0, hue / 6.0)
    # `hsl.hue`: the shift in turns is `h - 0.5` (`half`) or `2 (h - 0.5)` (`twoturn`, the slider
    # spanning two turns, so 0, 0.5 and 1 are all the identity). FORMAT-NOTES.md, "Auras' hue".
    _k = 2.0 if assume.assumed("hsl.hue", "twoturn") == "twoturn" else 1.0
    hue = (hue + _k * (np.asarray(h) - 0.5)) % 1.0
    # `hsl.saturation` / `hsl.luminosity`: `full` reads both as offsets of 2 (x - 0.5), as the
    # hue slider is read. FORMAT-NOTES.md, "the buttons are hsl".
    if assume.assumed("hsl.saturation", "scale") == "full":
        sat = np.clip(sat + 2.0 * (np.asarray(s) - 0.5), 0.0, 1.0)
        assume.note(v.index)
    else:
        sat = np.clip(sat * (2.0 * np.asarray(s)), 0.0, 1.0)
    _kl = 2.0 if assume.assumed("hsl.luminosity", "half") == "full" else 1.0
    if _kl != 1.0:
        assume.note(v.index)
    lum = np.clip(lum + _kl * (np.asarray(lu) - 0.5), 0.0, 1.0)
    q = np.where(lum < 0.5, lum * (1.0 + sat), lum + sat - lum * sat)
    p_ = 2.0 * lum - q

    def chan(tc):
        tc = tc % 1.0
        out = np.where(
            tc < 1 / 6.0,
            p_ + (q - p_) * 6.0 * tc,
            np.where(
                tc < 0.5,
                q,
                np.where(tc < 2 / 3.0, p_ + (q - p_) * (2 / 3.0 - tc) * 6.0, p_),
            ),
        )
        return out

    out = np.concatenate([chan(hue + 1 / 3.0), chan(hue), chan(hue - 1 / 3.0)], axis=1)
    if src.shape[-1] == 4:
        out = np.concatenate([out, src[:, 3:4]], axis=1)
    return to_image(np.clip(out, 0.0, 1.0), N, H, W)


# ---------------------------------------------------------------------------
# Spatial
# ---------------------------------------------------------------------------


def _normal_reference_px(v):
    """The pixel grid `normal`'s intensity is expressed against: a CONSTANT 256.

    Separate from `_reference_px` on purpose. That one answers "how many pixels is this
    record" and is what `blur`, `warp`, `dirmotionblur` and `directionalwarp` read; nothing
    measured here is evidence about those, and they are untouched. `f_normal`'s comment
    carries the two-pack measurement that pins this one.
    """
    forced = assume.assumed("normal.reference_px", 256.0)
    if forced == "record":
        return float(v.width) if v.width else 256.0
    return float(forced)


def _reference_px(v):
    """The pixel scale a pixel-valued intensity is expressed in -- from the RECORD.

    A fixed 256 is right for 98.6% of the corpus by a property of the corpus, not of the
    format, and wrong by 2x or 4x on the rest. An explicit `warp.reference_px` still wins.
    """
    # DEFAULT `tag` since the re-take recorded in FORMAT-NOTES.md, "`tag` promoted": the
    # arbitrated reading restored. `record` (the rendered width) stays as an arm.
    forced = assume.assumed("warp.reference_px", "tag")
    if forced == "tag":
        # THE RECORD'S TAG WIDTH, which is what `record` MEANT when it was arbitrated: every
        # graph then rendered at its tag size, so `v.width` and the tag were one number.
        # `pergraph` split them -- Bricks 005's records are 1024 wide under it and 256 under
        # `first` -- and `record` silently became the RENDERED width, shrinking every
        # pixel-valued intensity in graphs 002-005 by 4x against the canvas. `tag` reads the
        # arbitrated quantity back; for a record tagged 64 or 128 it is not the same as a
        # forced 256.0. See FORMAT-NOTES.md, "`_reference_px` silently changed meaning".
        return float(v.rec.width) if getattr(v, "rec", None) is not None and v.rec.width else 256.0
    if forced is not None and forced != "record":
        return float(forced)
    return float(v.width) if v.width else 256.0


@filt("blur")
def f_blur(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    p = v.params.get("intensity")
    if p is None:
        d = assume.assumed("blur.default_intensity", 10.0)
        if d == "refuse":
            raise Unsupported(
                "blur stores no intensity: neither class bit 12 (baked) nor 13 "
                "(program) is set, so the source omitted it"
            )
        # The engine default the source left in place; see assume.QUESTIONS.
        p = None
        intensity = float(d)
        ctx.low_confidence.add(v.index)
        assume.note(v.index)
    if p is None:
        pass
    elif p.kind == "baked":
        intensity = float(p.value)
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size != 1 or not np.isfinite(got[0]):
            raise Unsupported("blur intensity program does not evaluate to a scalar")
        intensity = float(got[0])
    src = to_image(ctx.sample(v, 0, pos), N, H, W)
    # THE BLUR'S PIXEL SCALE IS A FIXED 256, under `blur.reference_px`. Bricks graph 001's
    # outline is `|x - blur(x)|` with the blur's intensity `256 / min($size)` (10164): an
    # author's idiom for "one pixel whatever the size", which it is only if the intensity
    # is in pixels AT 256 -- under the record's own width it is a quarter-pixel at 1024,
    # the difference is zero, the mask is white, the Flood Fill sees one cell, and graph
    # 001's stones never existed (10253 flat 0.779 at native; sd 0.305 under this). The
    # directional blur keeps the record reading: Chesterfield's Blur HQ (3.3 baked, four
    # passes at 2048) flattens the AO's height under a fixed 256 (band 0.0007).
    if assume.assumed("blur.reference_px", 256.0) == "record":
        ref_px = _reference_px(v)
    else:
        ref_px = float(assume.assumed("blur.reference_px", 256.0))
    radius = float(np.clip(abs(intensity), 0.0, 256.0)) / ref_px
    rfl = radius * max(W, H)
    rpx = int(round(rfl))
    if rpx < 1:
        # A SUB-PIXEL RADIUS, behind `blur.subpixel`. `identity` is the reading as it
        # stood. `fractional` mixes the 1-px box in by the radius, so a blur the record
        # states at a fraction of a pixel still moves the picture by that fraction: a
        # box of half-width r < 1 covers each neighbour by r, which is exactly the lerp.
        # Bricks 10164 is the specimen -- intensity `256 / min($size)`, one pixel at
        # the record's own size, 0.25 px when a 1024 record is drawn on a 256 grid --
        # whose downstream `|blur - x|` is the edge detector graph 001's flood-fill mask
        # is built from, and the identity returns exactly zero to it.
        if assume.assumed("blur.subpixel", "identity") == "fractional" and rfl > 0:
            assume.note(v.index)
            return src + (_box(src, 1) - src) * np.float32(rfl)
        return src  # a blur of sub-pixel radius is the identity
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


@filt("sharpen")
def f_sharpen(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    src = to_image(ctx.sample(v, 0, pos), N, H, W)
    # `v.baked(name, 1.0) or 1.0` read the baked arm ONLY and turned a stated 0.0 into 1.0,
    # which mattered the moment the legend started supplying this parameter at all.
    p = v.params.get("intensity")
    if p is None:
        amount = 1.0  # absent: the node default, and NOT recorded here
    elif p.kind == "baked":
        amount = float(p.value)
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size < 1 or not np.isfinite(got[0]):
            raise Unsupported("sharpen intensity program does not evaluate to a scalar")
        amount = float(got[0])
    return np.clip(src + amount * (src - _box(src, 1)), 0.0, 1.0)


#: Toggle for `_dirmotion_shifted`, so the per-pixel sampler path it replaces can be A/B'd
#: against it in one process.
SHIFTED_TAPS = True


def _constant(a):
    """A parameter that is one number: a scalar, or an (N, 1) field whose rows all agree.
    `_scalar` broadcasts program-valued parameters to a field even though none of them
    read `$pos` (see its note), so size alone would send nearly every record the slow way."""
    a = np.asarray(a)
    return a.size == 1 or bool(a.min() == a.max())


def _shift_lerp(img, dx, dy):
    """`img` read at (x + dx, y + dy) pixels, bilinear and wrap-tiled -- what `sampler`
    returns for `pos_grid + (dx / W, dy / H)` on an image already at the render grid,
    computed as three rolls and two lerps instead of a million-point gather."""
    ix, iy = math.floor(dx), math.floor(dy)
    fx, fy = np.float32(dx - ix), np.float32(dy - iy)
    a = np.roll(img, (-iy, -ix), axis=(0, 1))
    if fx == 0 and fy == 0:
        return a  # a whole-pixel shift (or none): the roll IS the answer, and a copy
    if fy == 0:
        top = np.roll(a, -1, axis=1)
        top -= a
        top *= fx
        top += a
        return top
    top = np.roll(a, -1, axis=1)
    top -= a
    top *= fx
    top += a
    bot = np.roll(top, -1, axis=0)
    bot -= top
    bot *= fy
    bot += top
    return bot


def _dirmotion_shifted(src, length, turn, taps):
    """`f_dirmotionblur` when its length and angle are CONSTANT and its input is at the
    render grid: every tap is then the whole image shifted by one sub-pixel offset.

    NOT BIT-IDENTICAL to the sampler path, by design (owner, 2026-09-28: speed does not need
    bit-equality): float32 throughout where the sampler promoted to float64, and the offset
    is added in pixels rather than to each float32 pixel centre, so the fraction no longer
    carries per-pixel rounding. It was 30% of a native Bricks render -- 264 records, 17
    million-point gathers each (FORMAT-NOTES.md, "the renderer, profiled")."""
    H, W = src.shape[:2]
    L = float(np.asarray(length).ravel()[0])
    t = float(np.asarray(turn).ravel()[0])
    img = src.astype(np.float32, copy=False)
    acc = np.zeros(img.shape, np.float32)
    for k in range(taps):
        f = (k / (taps - 1.0)) - 0.5
        acc += _shift_lerp(img, L * f * math.cos(t) * W, L * f * math.sin(t) * H)
    acc /= np.float32(taps)
    return acc


@filt("dirmotionblur")
def f_dirmotionblur(ctx, v):
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    if v.params.get("intensity") is None:
        # The value never typed (assume.QUESTIONS); 8 corpus records omit it.
        d = assume.assumed("dirmotionblur.default_intensity", 10.0)
        if d == "refuse":
            raise Unsupported("dirmotionblur stores no intensity; the source omitted it")
        ctx.low_confidence.add(v.index)
        assume.note(v.index)
    else:
        d = 0.0
    intensity = np.asarray(_scalar(ctx, v, "intensity", float(d), W, H, pos), np.float32)
    angle = np.asarray(_scalar(ctx, v, "mblurangle", 0.0, W, H, pos), np.float32)
    # LENGTH IS THE INTENSITY IN THE RECORD'S OWN PIXEL SCALE, WITH NO EXTRA FACTOR. This
    # read `* 10.0`, and that multiplier is where graph 004's top two octaves went: four
    # chained `dirmotionblur` records take band-5 power from 1.288e-03 to 4.114e-06 -- 313x
    # -- in the last four steps before the height output, while the thirty `warp` records
    # feeding them pass it through unchanged. Replacing the filter with a pass-through
    # restores the top band from 0.005 to 1.302 on height and RAISES every correlation.
    #
    # THE LOSS IS HERE AND THE GENERATOR IS ELSEWHERE, and those are different questions.
    # `pixelprocessor` remains the only filter that GENERATES top-octave content -- that
    # knockout still takes the top octave to exactly zero -- and an earlier note struck this
    # filter off the list of suspects by observing that correcting it "does not add
    # top-octave content", which is true and does not answer where the octaves are LOST.
    # See FORMAT-NOTES.md, "Where graph 004 loses the top two octaves".
    #
    # WHY 1 AND NOT A FIT TO `corr`: at this value the top two BANDS return to 0.880 / 1.004
    # on height and 0.807 / 1.265 on normal -- the spectrum agreeing, rather than a scalar
    # improving. `f_directionalwarp` below computes the same quantity as
    # `intensity / _reference_px(v)` with no factor at all, and this now matches it.
    #
    # `roughness` DOES NOT FOLLOW and must not be corrected with this knob: its top band
    # overshoots to 7.976 here and its coarse bands are already 2.7-5x high at every value.
    # That is the field-level fault measured separately -- 0.161 against 0.513 -- and it is
    # a different fault in the same graph.
    length = np.clip(np.abs(intensity), 0.0, 256.0) / _reference_px(v)
    # `dirmotionblur.extent`: WHETHER THE INTENSITY IS THE BLUR'S TOTAL EXTENT OR ITS REACH
    # EACH SIDE. `total` spreads the 17 taps over [-length/2, +length/2] (`floor`, the
    # default, is `total` with at least one tag texel);
    # `radius` over [-length, +length]. The export states which, and it states it on a
    # construct this filter can be tested on in isolation: Bricks 004 and 005 each end in
    # the SAME eight-direction stack (two chains of four at 1/16-turn steps, averaged 50/50,
    # intensity 0.5016), fed a hard slot (floor/face 0.000). Emulated on the saved stack
    # input the stack reproduces the rendered output to max |diff| 0.0000, and swept against
    # each graph's OWN export joint by joint it wants 8x today's length -- 005 best at x8 on
    # 12 of 16 joints, 004 on 11 of 16, median x8.0 on both. x8 is x4 (reading the
    # intensity in the TAG's pixels, `warp.reference_px`) times x2 (this). Neither alone.
    # See FORMAT-NOTES.md, "the round-tile groove".
    _ext = assume.assumed("dirmotionblur.extent", "floor")
    if _ext == "radius":
        length = length * 2.0
    elif _ext == "x8render":
        # EIGHT TIMES THE INTENSITY IN THE RENDERED IMAGE'S PIXELS, independent of
        # `warp.reference_px`. The two export fits agree on this and not on tag x radius:
        # Bricks 004/005's 0.5016 stack at 1024 wants 8 x intensity rendered px (joints), and
        # Auras 003's 3.861 chain at 512 wants 8 x intensity rendered px (glow halo), where
        # tag x radius gives x8 on Bricks only because its rendered/tag ratio is 4 and x4 on
        # Auras. See FORMAT-NOTES.md, "The large-blur fit".
        length = np.clip(np.abs(intensity), 0.0, 256.0) * 8.0 / float(W)
    elif _ext == "floor":
        # AT LEAST ONE TAG TEXEL for a positive intensity; 0 stays a pass-through. FORMAT-NOTES.md,
        # "the round-tile joint, re-measured".
        a = np.clip(np.abs(intensity), 0.0, 256.0)
        length = np.where(a > 0.0, np.maximum(a, np.float32(1.0)), a) / _reference_px(v)
    turn = 2.0 * np.pi * angle
    TAPS = 17
    src = np.asarray(ctx.src(v, 0))
    if (
        SHIFTED_TAPS
        and src.ndim == 3
        and src.shape[:2] == (H, W)
        and _constant(length)
        and _constant(turn)
    ):
        return _dirmotion_shifted(src, length, turn, TAPS)
    smp = sampler(src)
    acc = None
    for k in range(TAPS):
        f = (k / (TAPS - 1.0)) - 0.5
        off = np.concatenate(
            [
                (length * f) * np.cos(turn) * np.ones((N, 1), np.float32),
                (length * f) * np.sin(turn) * np.ones((N, 1), np.float32),
            ],
            axis=-1,
        )
        val = smp(pos + off)
        acc = val if acc is None else acc + val
    return to_image(acc / float(TAPS), N, H, W)


@filt("directionalwarp")
def f_directionalwarp(ctx, v):
    if len(v.inputs) < 2:
        raise Unsupported("directionalwarp has fewer than 2 edges")
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    a, b = (1, 0) if assume.assumed("dirwarp.edges") == "swapped" else (0, 1)
    if a:
        assume.note(v.index)
    intensity = np.asarray(_scalar(ctx, v, "intensity", 0.0, W, H, pos), np.float32)
    angle = np.asarray(_scalar(ctx, v, "warpangle", 0.0, W, H, pos), np.float32)
    height = ctx.sample(v, b, pos)[:, :1]
    disp = (2.0 * height - 1.0) * intensity / _reference_px(v)
    turn = 2.0 * np.pi * angle
    in_pos = pos + np.concatenate(
        [
            disp * np.cos(turn) * np.ones((N, 1), np.float32),
            disp * np.sin(turn) * np.ones((N, 1), np.float32),
        ],
        axis=-1,
    )
    return to_image(sampler(ctx.src(v, a))(in_pos), N, H, W)


# ---------------------------------------------------------------------------
# Table-driven tone, and the two-input spatial filters
# ---------------------------------------------------------------------------

#: How many components of a `read_ramp` entry `f_gradient` actually slices, per form. The
#: keys are asserted against `sbsasm.RAMP_FORMS` by the suite, so a new layout in the decode
#: fails there rather than at whichever record happens to reach it first. Entries may be one
#: component WIDER than this -- the trailing midpoint word, which nothing here reads.
_RAMP_WIDTH = {"grey-u16": 2, "rgba-u16": 3, "grey-float": 2, "rgba-float": 5}


@filt("gradient")
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
        raise Unsupported("gradient record carries no readable ramp")
    form, table = got
    if form not in _RAMP_WIDTH:
        raise Unsupported("gradient ramp form %r has no reader here" % (form,))
    if len(table[0]) < _RAMP_WIDTH[form]:
        raise Unsupported(
            "%s ramp entry is %d components, needs %d"
            % (form, len(table[0]), _RAMP_WIDTH[form])
        )
    W, H = v.size(ctx.cap)
    N = W * H
    if form == "rgba-float":
        stops = np.array([e[0] for e in table], np.float32)
        vals = np.array([list(e[1:5]) for e in table], np.float32)
    elif form == "grey-float":
        stops = np.array([e[0] for e in table], np.float32)
        vals = np.array([e[1] for e in table], np.float32)
    elif form == "rgba-u16":
        stops = np.array([e[0] for e in table], np.float32) / 65535.0
        packed = [(int(e[1]) | (int(e[2]) << 16)) & 0xFFFFFFFF for e in table]
        vals = (
            np.array(
                [[(u >> (8 * k)) & 0xFF for k in range(4)] for u in packed], np.float32
            )
            / 255.0
        )
    else:
        stops = np.array([e[0] for e in table], np.float32) / 65535.0
        vals = np.array([e[1] for e in table], np.float32) / 65535.0
    t = np.clip(ctx.sample(v, 0, pos_grid(W, H))[:, :1], 0.0, 1.0).ravel()
    if vals.ndim == 2:
        out = np.stack(
            [
                np.interp(t, stops, vals[:, c]).astype(np.float32)
                for c in range(vals.shape[1])
            ],
            axis=-1,
        )
    else:
        out = np.interp(t, stops, vals).astype(np.float32).reshape(N, 1)
    return to_image(out, N, H, W)


@filt("curve")
def f_curve(ctx, v):
    """A cubic Bezier transfer curve, sampled to a lookup and applied per channel."""
    knots = v.rec.curve_points
    if not knots or len(knots) < 2:
        raise Unsupported("curve record carries no readable spline")
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
        b2, b3 = 3 * u * u * (1 - u), u**3
        xs.append(b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0])
        ys.append(b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1])
    cx, cy = np.concatenate(xs), np.concatenate(ys)
    order = np.argsort(cx)
    out = np.interp(src.ravel(), cx[order], cy[order]).astype(np.float32)
    return to_image(out.reshape(src.shape), N, H, W)


@filt("warp")
def f_warp(ctx, v):
    """Displace input 0 by the GRADIENT of input 1, scaled by `intensity`."""
    if len(v.inputs) < 2:
        raise Unsupported("warp has fewer than 2 edges")
    p = v.params.get("intensity")
    if p is None:
        d = assume.assumed("warp.default_intensity", 1.0)
        # THE BITS ARE 29 AND 30, NOT 13 AND 14. `CLS_NAMES[7]` maps bit 29 to
        # `('intensity', 'baked')` and bit 30 to `('intensity', 'program')`, and that is the
        # mapping `View._add` actually uses. The old message named 13/14, which sent a reader
        # censusing the wrong bits for most of an investigation before the legend was checked.
        #
        # THE OMISSION IS GENUINE AND IT IS SMALL. Over 437 corpus files plus the 8 pack
        # assemblies there are 28,100 `warp` records: 26,108 (92.91%) state a baked intensity,
        # 1,112 (3.96%) a program, and 880 (3.13%) state NEITHER, spread across 161 files.
        # That 880 is exactly the `warp stores no intensity` failure count in the corpus-wide
        # completion sweep, from an independent measurement -- so these records really do omit
        # the field and are not being misread.
        #
        # Refusing follows `f_normal`, which raises rather than substituting a default on the
        # same reasoning: an invented intensity renders something WRONG instead of nothing.
        # Whether `warp` should gain a `warp.default_intensity` arm the way `normal` has
        # `normal.default_intensity` is a policy question and the owner's to decide.
        if d == "refuse":
            raise Unsupported(
                "warp stores no intensity: neither class bit 29 (baked) nor 30 "
                "(program) is set, so the source omitted it"
            )
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    if p is None:
        # SUBSTITUTED, AND MARKED AS SUCH. `f_normal` does the same: a render leaning on a
        # value the file does not state is low-confidence, so it stays distinguishable from
        # one that read the field.
        intensity = float(d)
        ctx.low_confidence.add(v.index)
        assume.note(v.index)
    elif p.kind == "baked":
        intensity = float(p.value)
        if not (intensity == intensity and -1e3 < intensity < 1e3):
            raise Unsupported(
                "warp intensity is not a plausible float (%r)" % intensity
            )
    else:
        got = np.asarray(ctx.run(v, p.value, 1)).ravel()
        if got.size != 1 or not np.isfinite(got[0]):
            raise Unsupported("warp intensity program does not evaluate to a scalar")
        intensity = float(got[0])
    gmap = to_image(ctx.sample(v, 1, pos), N, H, W)[:, :, 0].astype(np.float32)
    gy, gx = np.gradient(gmap)
    ref = _reference_px(v)
    in_pos = pos + np.concatenate(
        [
            (gx * W / ref * intensity).reshape(N, 1),
            (gy * H / ref * intensity).reshape(N, 1),
        ],
        axis=-1,
    )
    return to_image(sampler(ctx.src(v, 0))(in_pos), N, H, W)


@filt("emboss")
def f_emboss(ctx, v):
    """Input 0 plus a directional difference of input 1 -- a lit relief."""
    if len(v.inputs) < 2:
        raise Unsupported("emboss has fewer than 2 edges")
    W, H = v.size(ctx.cap)
    N = W * H
    pos = pos_grid(W, H)
    base = to_image(ctx.sample(v, 0, pos), N, H, W)
    smp = sampler(ctx.src(v, 1))
    OFF = 0.005859375
    g0 = to_image(smp(pos), N, H, W)[:, :, :1]
    if assume.assumed("emboss.intensity", "fields") == "fields":
        # `fields`: the record's own w1 fields -- field 1 an intensity, field 3 a light angle in
        # turns (0 when absent) -- times slot 5's `0.1 * 2048 / $size`; the sample offset is
        # slot 4's 0.00586 UV, along the angle. FORMAT-NOTES.md, "RoofTiles' basecolor".
        f = {fld: struct.unpack("<f", struct.pack("<I", int(v.words[s]) & 0xFFFFFFFF))[0]
             for kind, fld, s, _w in v.ignored if kind == "w1"}
        th = 2.0 * math.pi * float(f.get(3, 0.0))
        off = np.array([OFF * math.cos(th), -OFF * math.sin(th)], np.float32)
        g1 = to_image(smp(pos + off), N, H, W)[:, :, :1]
        k = float(f.get(1, 1.0)) * 0.1 * 2048.0 / float(v.width or 2048)
        assume.note(v.index)
        return np.clip(base + k * (g0 - g1), 0.0, 1.0)
    g1 = to_image(smp(pos + np.array([OFF, -OFF], np.float32)), N, H, W)[:, :, :1]
    k = 0.1
    if assume.assumed("emboss.intensity", "fields") == "program":
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


@filt("distance")
def f_distance(ctx, v):
    """A distance field grown from the mask input, out to a radius the record states.

    The radius LOCATION is `distance.distance_param`, which is the one read in this
    renderer still carrying a fallback of its own -- see FORMAT-NOTES' L6. Every record it
    answers for is marked low-confidence, so the fallback is visible in the output rather
    than folded into it.
    """
    import distance as dist

    # THE RADIUS IS FIELD 1, AND BOTH OF ITS ARMS ARE READ HERE. It was named at field 0,
    # which is not a parameter at all: field 0's low bit declares the optional mask INPUT,
    # and the walk was charging that input twice -- once as the edge it is, once as this
    # field -- so the parameter block started one slot late and the wrong field carried the
    # name. On the records a source can witness the two coincide, which is why the naming
    # held up: SandyStonePath states 56.3 and 64.22 and records 3 and 180 hold exactly
    # those. Everywhere else they part, and the file says which is right -- see below.
    #
    # THE SLOT MUST ACTUALLY HOLD A PROGRAM, and that check is what found this. Under the
    # field-0 naming, the named slot resolved to a valid program in 0 of 595 records while
    # the slot one earlier did in 569; 579 of the 595 held a float-shaped word, Brick02
    # record 61 being the shape of all of them -- `5.120025` read as an address
    # (`0x40a3d70a + 52`). Reading the state bits differently would have been a third guess
    # about a placement two rules already disagreed on, so this asked the file, which is the
    # loud check §6.3 applies to edges; declining gained 1,215 records (+6.3%) and 7 declared
    # outputs over the 30 files carrying the configuration, with the reference specimen
    # byte-identical.
    #
    # WITH THE NAME ON FIELD 1 THE DECLINE IS NEVER NEEDED: over 2,411 corpus `distance`
    # records the legend now reads 1,720 plausible baked radii, 509 baked zeros and 188
    # programs, and ALL 188 decode. Under the old naming the same sweep produced 638
    # undecodable "programs", 105 denormal "radii" (pointers read as floats), 3 records that
    # raised `Shifted` and 87 with no parameter at all. The guard stays because what it
    # asserts is right whatever the naming, and it is now silent.
    p = v.params.get("distance")
    if p is not None and p.kind == "program":
        _raw = (
            v.words[p.slot]
            if (p.slot is not None and 0 <= p.slot < len(v.words))
            else None
        )
        if _raw is None or not ctx.asm.valid_program(_raw + 52):
            p = None
    val = how = None
    # `f1_program` USED TO GUARD THIS LINE -- "field 1 holds a program, so the walk's
    # placement is unverified" -- and it was a symptom of the name being on field 0. Field 1
    # holding a program now means the radius IS a program and the record names it. Against
    # the locator it replaces, on the five program-arm records of PavingStonesSubstance003:
    # identical, 5 of 5 (0.0, 1.0, 1.0, 3.2, -3.2).
    if p is not None:
        if p.kind == "baked":
            val, how = float(p.value), "walked"
        else:
            got = np.asarray(ctx.run(v, p.value, 1)).ravel()
            if got.size and np.isfinite(got[0]):
                val, how = float(got[0]), "walked"
    if val is None:
        try:
            val, how = dist.distance_param(v.rec, lambda p_: ctx.run(v, p_, 1), {})
        except dist.Unlocated as e:
            raise Unsupported("distance: %s" % e) from e
        if dist.is_low_confidence(how):
            ctx.low_confidence.add(v.index)
    W, H = v.size(ctx.cap)
    pos = pos_grid(W, H)
    mask_edge = assume.assumed("distance.mask_edge", 0)
    if mask_edge >= len(v.inputs) or v.edge(mask_edge) not in ctx.outputs:
        mask_edge = 0
    if assume.assumed("distance.mask_edge") is not None:
        assume.note(v.index)
    mask = ctx.sample(v, mask_edge, pos).reshape(H, W, -1)[:, :, 0]
    field = dist.distance_field(mask, dist.scale_radius(val, W))
    if assume.assumed("distance.invert", False):
        field = 1.0 - field
        assume.note(v.index)
    payload = next(
        (e for k, e in enumerate(v.inputs) if k != mask_edge and e in ctx.outputs), None
    )
    prop = assume.assumed("distance.propagate", "spread")
    if prop == "flag":
        # WORD 1 BIT 1 AS `combinedistance`. Over 2,277 corpus distance records word 1 is
        # 5 / 9 / 21 (two edges, bit 1 clear) on 1,552, 6 / 10 (one edge, bit 1 set) on
        # 678, and 7 (two edges, bit 1 SET) on 47; bit 2 / bit 3 are the baked / program
        # distance, bit 0 the second edge. A one-edge record has nothing to combine and
        # carries the default (1); the 19 permitted two-edge sightings declare 0 and
        # their records clear it. Set: `nearest`; clear: `spread`, source and all.
        prop = "nearest" if (v.rec.words[1] >> 1) & 1 else "spread"
        same_ok = True
    else:
        same_ok = False
    # A SOURCE THAT IS THE MASK ITSELF IS NO SOURCE. Bricks wires the same record to both
    # edges on 46 of its 86 two-edge `distance` records ([158, 158]); read as a source it
    # turns the field into a hard dilation of the mask, and graph 005's bevels and grid
    # lines go with it. Under `spread` such a record draws the field.
    if prop == "spread" and payload is not None and payload == v.edge(mask_edge) and not same_ok:
        payload = None
    if prop in ("nearest", "spread") and payload is not None:
        src = sampler(ctx.outputs[payload])(pos).reshape(H, W, -1)
        vals = dist.propagate(mask, dist.scale_radius(val, W), src)
        assume.note(v.index)
        # `nearest` combines the propagated value with the falloff; `spread` keeps the
        # value flat out to the radius (`combinedistance` = 0, see assume.QUESTIONS).
        gain = field if prop == "nearest" else (field > 0).astype(np.float32)
        return to_image((vals * gain[:, :, None]).reshape(H * W, -1), W * H, H, W)
    return to_image(field.reshape(-1, 1), W * H, H, W)


@filt("vectorshape")
def f_vectorshape(ctx, v):
    """Filter 5: the record's embedded triangle strip, rasterised as a mask.

    `Record.vector_faces` is the strip as explicit triangles in [0, 1] canvas units, joins
    and part boundaries dropped (§13 of SPEC.md, "vectorshape"). Each triangle covers the
    pixels whose centres lie inside it (three edge functions, one sign), and the shape is
    the union; the fill is 1.0 where the strip covers and 0.0 elsewhere -- the record
    names no parameter, and the class-bit-25 float where present is 1.0 on every corpus
    record that was checked. No anti-aliasing: an edge is a pixel step. 139 corpus
    records, 7 files blocked on "no implementation" before this.
    """
    faces = v.rec.vector_faces
    if not faces:
        raise Unsupported("vectorshape: no faces decode from the payload")
    W, H = v.size(ctx.cap)
    out = np.zeros((H, W), np.float32)
    px = (np.arange(W, dtype=np.float64) + 0.5) / W
    py = (np.arange(H, dtype=np.float64) + 0.5) / H
    for tri in faces:
        (x0, y0), (x1, y1), (x2, y2) = tri
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-12:
            continue
        c0 = max(int(np.floor(min(x0, x1, x2) * W)) - 1, 0)
        c1 = min(int(np.ceil(max(x0, x1, x2) * W)) + 1, W)
        r0 = max(int(np.floor(min(y0, y1, y2) * H)) - 1, 0)
        r1 = min(int(np.ceil(max(y0, y1, y2) * H)) + 1, H)
        if c0 >= c1 or r0 >= r1:
            continue
        X = px[c0:c1][None, :]
        Y = py[r0:r1][:, None]
        e0 = (x1 - x0) * (Y - y0) - (y1 - y0) * (X - x0)
        e1 = (x2 - x1) * (Y - y1) - (y2 - y1) * (X - x1)
        e2 = (x0 - x2) * (Y - y2) - (y0 - y2) * (X - x2)
        if area > 0:
            hit = (e0 >= 0) & (e1 >= 0) & (e2 >= 0)
        else:
            hit = (e0 <= 0) & (e1 <= 0) & (e2 <= 0)
        out[r0:r1, c0:c1][hit] = 1.0
    return out[:, :, None]


@filt("dyngradient")
def f_dyngradient(ctx, v):
    """Input 0 indexes into input 1, which is a one-row (or one-column) ramp image."""
    if len(v.inputs) < 2:
        raise Unsupported("dyngradient has fewer than 2 edges")
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
