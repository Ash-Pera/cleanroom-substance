#!/usr/bin/env python3
"""Image primitives and the program runner. No format knowledge lives here.

Everything in this module is arithmetic on arrays plus the bytecode VM, which is
`sbsruntime` -- the one part of the old renderer that is not a decode decision and so is
reused rather than rewritten. What was rewritten is everything that decides WHICH program
to run and WHAT its number means; that is `filters.py`, reading `model.View`.
"""
import math

import numpy as np

import sbsruntime
import transpile


class Unsupported(Exception):
    """This renderer will not produce an output for this record, and says why.

    `cascade` is True when the failure is only the shadow of an upstream one -- a record
    whose input was never produced -- so a root-cause list is `failures - cascaded`.
    """
    cascade = False


def cascade(message):
    e = Unsupported(message)
    e.cascade = True
    return e


# ---------------------------------------------------------------------------
# Grids and images
# ---------------------------------------------------------------------------

#: The render grid per (W, H). MEMOISED SO THE IDENTITY CASE IS RECOGNISABLE BY IDENTITY:
#: `_fast_sampler` cannot tell "this is my own pixel centres" from an arbitrary position
#: array without arithmetic, but it can compare the object. 62.4% of all sampling on
#: PlasticSubstance003 is a filter resampling an input that is already at the render grid,
#: and 122 M of those samples come through `Context.sample` with exactly this array.
_GRIDS = {}


def pos_grid(W, H):
    """(N, 2) pixel-centre positions in [0, 1], x then y, row-major.

    The returned array is SHARED and READ-ONLY. Shared because the identity check above is
    an `is`, and read-only because a shared mutable grid is a leak between every filter
    that asks for one -- the flag turns a write that used to corrupt the next record into
    an exception at the line that did it.
    """
    got = _GRIDS.get((W, H))
    if got is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        got = np.stack([(xx.ravel() + 0.5) / W, (yy.ravel() + 0.5) / H], axis=-1)
        got.setflags(write=False)
        _GRIDS[(W, H)] = got
    return got


#: Toggle for `_fast_sampler`, so it and `sbsruntime.image_sampler` can be measured and
#: compared in ONE process against one file. Off restores the shared implementation for
#: every caller.
FAST_SAMPLER = True

#: Toggle for the identity-grid branch alone, so it can be measured against the
#: exact-texel branch that would otherwise catch the same calls more slowly.
IDENTITY_GRID = True


def _grid_result_type(image_dtype):
    """What the four-corner lerp returns for a `pos_grid` position array.

    `pos_grid` is float32 and `fu` is `u - u0` against an int64, so the fraction is
    float64 and so is the lerp -- whatever the image's own width. Written out rather than
    inlined because getting it wrong is invisible: a bare gather carries the image's dtype
    and that alone moved 567 of 3,047 records.
    """
    return np.result_type(image_dtype, np.result_type(np.float32, np.int64))


def sampler(image):
    """`pos -> value`, bilinear and wrap-tiled. See sbsruntime.image_sampler.

    EVERY SAMPLER THIS RENDERER BUILDS COMES THROUGH HERE -- eleven call sites, including
    the two that install into `sbsruntime.SAMPLERS` for a transpiled program's
    `sample_lum`/`sample_col` -- which is why the specialisation below lives in render2
    and not in `sbsruntime`. The shared implementation stays the reference the fast one is
    held equal to, rather than becoming the thing that changed.
    """
    im = np.asarray(image)
    if not FAST_SAMPLER or im.ndim != 3:
        # A 2-D image takes the shared path unspecialised. It does not occur here --
        # `conform` gives every record output a channel axis -- and the shared code's
        # 1-D `base` would broadcast (N,) against an (N, 1) fraction into an (N, N)
        # outer product, so there is no behaviour worth reproducing.
        return sbsruntime.image_sampler(im)
    return _fast_sampler(im)


def _fast_sampler(image):
    """`sbsruntime.image_sampler` with two specialisations, both equalities.

    WRAPPING IS A MASK. `x & (W - 1)` equals `x % W` for every two's-complement integer
    when W is a power of two, negatives included, and numpy's `%` follows Python's sign
    convention exactly as the mask does. All 7,723 sampler calls on PlasticSubstance003
    are power-of-two, and the four modulos were 0.319 ms of a 0.9 ms call -- integer
    division against one cycle.

    AN EXACT TEXEL HIT IS A GATHER. When every sample's fractional part is zero on both
    axes the interpolation is `a + (b - a) * 0` twice over, which IS `a` in floating
    point, so one gather returns the same bits four gathers and two lerps do. 62.4% of all
    sampling on that file takes this path (186 M samples of 298 M) -- most of it filters
    resampling an input that is ALREADY at the render grid, which the sampler was paying
    for as a full bilinear tap. A further 0.2% is within 1e-6 of a texel and deliberately
    NOT short-circuited: those samples would move, and this function is held to equality,
    not to being more nearly right.

    THE GRID ITSELF IS THE COMMONEST CASE, and it is recognised by object identity rather
    than by testing the numbers -- see `pos_grid`. It returns the image, copied, with no
    index arithmetic and no gather at all.

    THE DTYPE IS PART OF THE ANSWER, and it is the trap. `fu` is `u - u0` with `u0` an
    int64, so a float32 position promotes to float64 there and the four-corner result is
    float64 EVEN OVER A FLOAT32 IMAGE. A bare `base[idx]` carries the image's dtype
    instead, and that one difference moved 567 of 3,047 records while an elementwise test
    of the two samplers passed -- the test used the same dtype for image and position, so
    the promotion never showed. The result type is reproduced below rather than assumed.
    """
    H, W = image.shape[:2]
    base = image.reshape(-1, image.shape[2])
    wm, hm = W - 1, H - 1
    pow2 = (W & wm) == 0 and (H & hm) == 0
    # The grid for THIS IMAGE's dimensions, not the caller's. A 128px source sampled on a
    # 256px render grid is not the identity case and must not take that branch.
    grid = _GRIDS.get((W, H)) if IDENTITY_GRID else None

    def sampler(pos):
        pos = np.asarray(pos)
        u = pos[:, 0] * W - 0.5
        v = pos[:, 1] * H - 0.5
        fu0 = np.floor(u)
        fv0 = np.floor(v)
        u0 = fu0.astype(np.int64)
        v0 = fv0.astype(np.int64)
        if pow2:
            u0m = u0 & wm
            v0m = v0 & hm
        else:
            u0m = u0 % W
            v0m = v0 % H
        if pos is grid:
            # THE IMAGE'S OWN PIXEL CENTRES, IN ORDER. The gather below would read
            # `base[0], base[1], ... base[N-1]` -- the array itself, row-major -- so this
            # returns it directly and skips the scale, the two floors, the two casts, the
            # masks and the gather. `astype` COPIES (it is not `copy=False`): every other
            # path here hands back a fresh array, and returning a view into a record's
            # stored output instead would alias two records' pixels together the moment
            # any caller wrote through it.
            return base.astype(_grid_result_type(base.dtype), copy=True)
        if np.all(u == fu0) and np.all(v == fv0):
            fdt = np.result_type(u.dtype, np.int64)     # what `u - u0` would have been
            return base[v0m * W + u0m].astype(np.result_type(base.dtype, fdt),
                                              copy=False)
        if pow2:
            u1m = (u0 + 1) & wm
            v1m = (v0 + 1) & hm
        else:
            u1m = (u0 + 1) % W
            v1m = (v0 + 1) % H
        fu = (u - u0)[:, None]
        fv = (v - v0)[:, None]
        r0, r1 = v0m * W, v1m * W
        a0 = base[r0 + u0m]; b0 = base[r0 + u1m]
        a1 = base[r1 + u0m]; b1 = base[r1 + u1m]
        top = a0 + (b0 - a0) * fu
        bot = a1 + (b1 - a1) * fu
        return top + (bot - top) * fv

    return sampler


def to_image(out, N, H, W):
    """A program's return value as an (H, W, k) image, broadcasting a constant row.

    An N-sample evaluation does not guarantee an N-row result: a program whose final value
    never touches `$pos` or a sampler stays one row wide, correctly, and has to be spread.
    """
    a = np.asarray(out)
    if a.ndim == 0:
        a = a.reshape(1, 1)
    elif a.ndim == 1:
        a = a[:, None]
    if a.shape[0] == 1 and N > 1:
        a = np.repeat(a, N, axis=0)
    return a.reshape(H, W, a.shape[-1])


def resample(image, W, H):
    """`image` sampled onto a W x H grid, area-filtered when it is being reduced."""
    src = np.asarray(image)
    if src.shape[0] == H and src.shape[1] == W:
        return src
    scale = max(src.shape[1] / float(W), src.shape[0] / float(H))
    return to_image(sampler(prefilter(src, scale))(pos_grid(W, H)), W * H, H, W)


def prefilter(src, scale):
    """Box-halve `src` until one texel covers the sampling footprint.

    A single bilinear tap answers "what is the source AT this point"; a minifying transform
    needs "what is it AVERAGED over the area this pixel covers", and on a sparse source the
    two differ by everything -- a 4x reduction of a field that is 0.5 in 99.8% of its pixels
    lands on the flat part at every phase and comes back exactly constant.

    Halving because a power-of-two chain is exact and needs no resampling; it stops on an
    odd dimension rather than padding.
    """
    img = np.asarray(src, dtype=np.float64)
    while scale >= 2.0 and img.shape[0] >= 2 and img.shape[1] >= 2 \
            and img.shape[0] % 2 == 0 and img.shape[1] % 2 == 0:
        img = 0.25 * (img[0::2, 0::2] + img[1::2, 0::2]
                      + img[0::2, 1::2] + img[1::2, 1::2])
        scale /= 2.0
    return img


def footprint_scale(m, W_out, H_out, src_shape):
    """Source texels covered by one output pixel under matrix `m`, for `prefilter`."""
    Hs, Ws = src_shape[0], src_shape[1]
    dx = math.hypot(m[0] * Ws / max(W_out, 1), m[2] * Hs / max(W_out, 1))
    dy = math.hypot(m[1] * Ws / max(H_out, 1), m[3] * Hs / max(H_out, 1))
    return float(max(dx, dy))


def conform(arr, want):
    """An (H, W, c) array as (H, W, want), or None when that would invent information.

    Grey wants one channel and colour four. Three channels for a colour record is RGB with
    no alpha and gets an opaque one; a greyscale record holding several IDENTICAL channels
    is the same picture written wide and is narrowed. Anything else is refused, because a
    channel count that disagrees with the record's own colour flag means the wrong program
    was evaluated, and a plausible picture is worse than a refusal.
    """
    a = np.asarray(arr)
    if a.ndim == 2:
        a = a[:, :, None]
    if a.shape[-1] == want:
        return a
    if want == 1:
        spread = float(np.max(np.abs(a - a[..., :1]))) if a.size else 0.0
        return a[..., :1] if spread <= 1e-9 else None
    if a.shape[-1] == 3:
        return np.concatenate([a, np.ones(a.shape[:2] + (1,), dtype=a.dtype)], axis=-1)
    if a.shape[-1] == 1:
        return np.repeat(a, want, axis=-1)
    return None


# ---------------------------------------------------------------------------
# Blending
# ---------------------------------------------------------------------------

#: mode -> (name, f(dst, src)). `switch` is a selection rather than a mix and is applied
#: by `blend` directly.
#:
#: THE NAMES ARE DECLARED, NOT CONVENTIONAL, AND THE ARITHMETIC IS NOT. A `.sbs` states
#: `blendingmode` on a node as a bare integer, so a source's parameter VALUES can pin the
#: field and can never name it. Where an author EXPOSES the parameter as a graph input the
#: file also carries its widget, and for an enumeration that is a `dropdownlist` whose
#: option string is `default;value;label;value;label;...`. Two permitted sources do, over
#: eight widgets, all carrying
#:
#:   0;Copy 1;Add (Linear Dodge) 2;Subtract 3;Multiply 4;Add Sub 5;Max (Lighten)
#:   6;Min (Darken) 7;Switch 8;Divide 9;Overlay 10;Screen 11;Soft Light
#:
#: and in each the node's own parameter is a one-node `get_integer1("<that input>")` -- a
#: literal pass-through, so the labelled integer IS `blendingmode`. The enumeration is
#: closed at 11: over 903,616 corpus records the nibble takes 0-11 and never 12-15, on
#: 310,697 blend records with no unreadable mode.
#:
#: A NAME IS NOT AN ARITHMETIC, and five of these rows are still this file's convention:
#: `addsub`'s `d + 2s - 1`, `switch`'s threshold, `divide`'s operand order, and the
#: particular `overlay` and `softlight` formulae, each of which has several published
#: forms. What IS measured is that they are in the right family -- swapping subtract's
#: operands flips six reference channels negative and kills twelve, reading 3 as screen
#: flips eight, reading 10 as multiply flips two, and `hardlight` in place of 11 kills a
#: channel -- while the three published softlight formulae agree to 0.0026 on every
#: channel and cannot be told apart at all. See FORMAT-NOTES.md, "`blendingmode`'s twelve
#: names are declared by a permitted source".
BLEND_MODES = {
    0:  ('copy',       lambda d, s: s),
    1:  ('add',        lambda d, s: d + s),
    2:  ('subtract',   lambda d, s: d - s),
    3:  ('multiply',   lambda d, s: d * s),
    4:  ('addsub',     lambda d, s: d + 2.0 * s - 1.0),
    5:  ('max',        lambda d, s: np.maximum(d, s)),
    6:  ('min',        lambda d, s: np.minimum(d, s)),
    7:  ('switch',     None),
    8:  ('divide',     lambda d, s: d / np.where(np.abs(s) < 1e-6, 1e-6, s)),
    9:  ('overlay',    lambda d, s: np.where(d < 0.5, 2.0 * d * s,
                                             1.0 - 2.0 * (1.0 - d) * (1.0 - s))),
    10: ('screen',     lambda d, s: 1.0 - (1.0 - d) * (1.0 - s)),
    11: ('softlight',  lambda d, s: np.where(
        s < 0.5, 2.0 * d * s + d * d * (1.0 - 2.0 * s),
        2.0 * d * (1.0 - s) + np.sqrt(np.clip(d, 0, None)) * (2.0 * s - 1.0))),
}


def blend(mode, dst, src, opacity):
    """Composite `src` over `dst` under `mode` at `opacity`, clamped to [0, 1].

    Opacity mixes the blended result back toward the destination, so at opacity 0 every
    mode is a no-op. `switch` takes opacity as a selector instead.

    `dst` IS INPUT 0 AND `src` IS INPUT 1, which matters for the three asymmetric modes and
    is measured rather than assumed: exchanging them for every mode at once kills 17 of the
    27 reference channels and takes `Bricks_and_tiles` emission ch0 from +0.9885 to +0.1413.
    The source states that a blend node's connectors are exactly `destination`, `source` and
    `opacity` -- the shape this signature reads -- but not which compiled edge slot each
    takes, so the render is the arbiter for the ORDER and the source for the names.

    `switch`'s threshold is the convention and not the file's: reading it as `> 0` or as an
    ordinary lerp moves nine `Bricks_and_tiles` channels by at most +0.0143 and leaves
    `Chesterfield` identical to four decimals, which is below the bar to overturn a declared
    name. Selecting `dst` instead of `src` is refused loudly -- it takes Chesterfield
    `basecolor` ch1 from +0.9694 to -0.7575 and `metallic`, the sharpest number in this
    repository, to unrenderable. See `BLEND_MODES` above for what the twelve names rest on.
    """
    entry = BLEND_MODES.get(mode)
    if entry is None:
        raise Unsupported('blend mode %r is outside the verified 0-11 range' % (mode,))
    name, fn = entry
    if name == 'switch':
        return np.where(opacity >= 0.5, src, dst)
    with np.errstate(all='ignore'):
        return np.clip(dst * (1.0 - opacity) + fn(dst, src) * opacity, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------

#: Transpiled source and compiled function, keyed by (assembly PATH, address).
#:
#: NOT by `id(asm)`. CPython reuses an id after the object is collected, so a sweep that
#: loads one Assembly per file can hand a second file the first file's compiled program at
#: the same address -- silently, and only sometimes. The path is stable and unique.
_SRC = {}


def _source(asm, start):
    key = (getattr(asm, 'path', id(asm)), start)
    got = _SRC.get(key)
    if got is None:
        end = asm.program_span(start)
        if end is None:
            raise Unsupported('program at %d does not resolve a span' % start)
        got = _SRC[key] = transpile.transpile(asm.data, start, end, 'python', 'prog')
    return got


_CODE = {}


def _code(asm, start):
    """The program's compiled code object. Pure in (path, address), so it is shared."""
    key = (getattr(asm, 'path', id(asm)), start)
    got = _CODE.get(key)
    if got is None:
        got = _CODE[key] = compile(_source(asm, start), '<prog>', 'exec')
    return got


def bind(asm, start, cache, memo):
    """The program at `start`, with its 0x03/0x06 halves bound to `cache`.

    THE COMPILED FUNCTION IS NOT SHARED, AND THE CODE OBJECT IS. Transpiling and compiling
    depend on nothing but the bytes at `start`, so `_SRC` and `_CODE` are keyed by (path,
    address) and every caller reuses them. What differs per caller is the NAMESPACE the
    function runs in: the transpiled source imports `cache_read` and `cache_write` from
    `sbsruntime` at its own module level, and rebinding those two names in the scope after
    the exec points them at this caller's dict instead of the module global. `prog`'s
    `__globals__` IS that scope, so the substitution reaches every call.

    `memo` is the caller's dict, not a module global, and that is the whole point: a
    function compiled against one cache must never be handed to a caller holding another.
    Keeping the memo beside the cache makes that unrepresentable rather than merely
    unlikely -- the pair is created together and collected together.
    """
    key = (getattr(asm, 'path', id(asm)), start)
    fn = memo.get(key)
    if fn is None:
        scope = {}
        exec(_code(asm, start), scope)
        scope['cache_read'], scope['cache_write'] = sbsruntime.cache_functions(cache)
        fn = memo[key] = scope['prog']
    return fn


def run_program(fn, inputs, slots, N, pos=None, W=None, H=None):
    """Evaluate `bind`'s function over N samples. Returns its raw array."""
    # EVERY FIELD, EVERY CALL. `set_context` ignores a None by design -- which is right
    # for its own callers and wrong here, because "no position supplied" has to MEAN no
    # position and not "keep the last record's". `pos` is therefore assigned directly;
    # there is no other way to clear it.
    sbsruntime.set_context(number=0.0, width=W, height=H)
    sbsruntime.CONTEXT['pos'] = pos
    with np.errstate(all='ignore'):
        try:
            return np.asarray(fn(inputs=inputs, slots=slots))
        except sbsruntime.MissingSampler as e:
            raise cascade('sampler %s is not bound -- an unwired image input' % e) from e
        except KeyError as e:
            raise Unsupported('slot %s read but never set' % e) from e


def graph_inputs(asm, N):
    """The graph's declared input defaults, broadcast to N rows, for `inputref`."""
    out = {}
    for _t, uid, v in asm.header.get('inputs') or []:
        if v:
            out[uid] = np.repeat(np.array(v, dtype=np.float32).reshape(1, -1), N, axis=0)
    return out
