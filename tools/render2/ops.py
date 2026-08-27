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

def pos_grid(W, H):
    """(N, 2) pixel-centre positions in [0, 1], x then y, row-major."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.stack([(xx.ravel() + 0.5) / W, (yy.ravel() + 0.5) / H], axis=-1)


def sampler(image):
    """`pos -> value`, bilinear and wrap-tiled. See sbsruntime.image_sampler."""
    return sbsruntime.image_sampler(np.asarray(image))


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
    mode is a no-op -- the structure the one independently verified mode (0) was checked
    under. `switch` takes opacity as a selector instead.
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


_COMPILED = {}


def run_program(asm, start, inputs, slots, N, pos=None, W=None, H=None):
    """Evaluate the program at `start` over N samples. Returns its raw array."""
    key = (getattr(asm, 'path', id(asm)), start)
    fn = _COMPILED.get(key)
    if fn is None:
        scope = {}
        exec(compile(_source(asm, start), '<prog>', 'exec'), scope)
        fn = _COMPILED[key] = scope['prog']
    sbsruntime.set_context(number=0.0)
    if pos is not None or W is not None or H is not None:
        sbsruntime.set_context(width=W, height=H, pos=pos)
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
