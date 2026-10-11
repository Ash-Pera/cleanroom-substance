"""Compiled kernels for render2's hottest loops, OPTIONAL: numba if importable.

WHY THIS EXISTS. A native Bricks render (12,585 records at 1024) spent half its time in
`fx.splat`'s per-pattern loop -- 39,662 patterns drawn as 62,055 footprint tiles, each ~15
small numpy passes issued from Python -- and 40% (before the shift paths) in the general
bilinear sampler, ~20 separate million-element passes a call. Both are memory-bound numpy
issued one pass at a time; a compiled loop does each in one pass. FORMAT-NOTES.md, "the
renderer, profiled" and "numba".

OPTIONAL BY CONSTRUCTION. `AVAILABLE` is False when numba does not import, and every caller
keeps its numpy path, so the renderer runs (slower) without it. `ENABLED` switches the
kernels off in-process for an A/B against the numpy paths.

NOT BIT-IDENTICAL to the numpy paths (owner's rule, 2026-09-28: speed does not need
bit-equality). The raster computes a footprint's local coordinates in float64 where numpy
stayed in float32; the sampler is the numpy arithmetic in the same dtypes and matched it
bit for bit on every case tested, but nothing here promises that. The nearest-texel gather
(the pixel processor's sampler, 2026-10-09) does numpy's steps in numpy's dtypes, with the
integers numpy gives a NaN / out-of-range cast probed from numpy at import.
"""
import math

import numpy as np

try:
    from numba import njit, prange

    AVAILABLE = True
except Exception:  # pragma: no cover - the numpy paths are the fallback
    AVAILABLE = False

#: In-process switch, for A/B against the numpy paths.
ENABLED = True

#: `fxrender.profile_value`'s shapes as integer codes for the raster. The ARMS are resolved
#: by the caller (`profile_code`) so the kernel reads no `assume` state.
P_RECT, P_DISC, P_CONE, P_PARABOLOID, P_GAUSSIAN, P_PYRAMID, P_GRADATION = range(7)
P_BELL_T2, P_HALFBELL_GAUSS, P_HALFBELL_PARAB, P_RIDGEDBELL, P_THORN = range(7, 12)
P_BRICK_INSET, P_WAVES, P_CRESCENT, P_CAPSULE = range(12, 16)
P_HALFBELL_GAUSS_X, P_HALFBELL_PARAB_X, P_HALFBELL_GAUSS_NX, P_HALFBELL_PARAB_NX = range(16, 20)

M_MAX, M_ADD, M_OVER = 0, 1, 2
MODES = {"max": M_MAX, "add": M_ADD, "over": M_OVER}


def active():
    return AVAILABLE and ENABLED


def profile_code(prof, assumed):
    """The kernel's code for profile name `prof`, or None for one it does not draw.

    `assumed` is `assume.assumed`. Every modelled shape's arm is read HERE, with the same
    default `fxrender.profile_value` uses, so a changed default there must change here."""
    if prof in ("rect", "square"):
        return P_RECT
    if prof == "bell":
        return P_GAUSSIAN if assumed("fx.bell", "t2") == "gaussian" else P_BELL_T2
    if prof == "halfbell":
        g = assumed("fx.halfbell", "gaussian") == "gaussian"
        cut = assumed("fx.halfbell.cut", "y")
        if cut == "x":
            return P_HALFBELL_GAUSS_X if g else P_HALFBELL_PARAB_X
        if cut == "-x":
            return P_HALFBELL_GAUSS_NX if g else P_HALFBELL_PARAB_NX
        return P_HALFBELL_GAUSS if g else P_HALFBELL_PARAB
    if prof == "brick":
        return P_RECT if assumed("fx.brick", "fill") == "fill" else P_BRICK_INSET
    return {
        "disc": P_DISC,
        "cone": P_CONE,
        "paraboloid": P_PARABOLOID,
        "gaussian": P_GAUSSIAN,
        "pyramid": P_PYRAMID,
        "gradation": P_GRADATION,
        "ridgedbell": P_RIDGEDBELL,
        "thorn": P_THORN,
        "waves": P_WAVES,
        "crescent": P_CRESCENT,
        "capsule": P_CAPSULE,
    }.get(prof)


if AVAILABLE:

    @njit(cache=True, inline="always")
    def _cov(lx, ly, code):
        """`fxrender.profile_value` at one point; 0 outside the |lx|, |ly| <= 0.5 box."""
        if abs(lx) > 0.5 or abs(ly) > 0.5:
            return 0.0
        if code == P_RECT:
            return 1.0
        r2 = (2.0 * lx) ** 2 + (2.0 * ly) ** 2
        r = math.sqrt(r2)
        if code == P_DISC:
            return 1.0 if r <= 1.0 else 0.0
        if code == P_CONE:
            return max(0.0, 1.0 - r)
        if code == P_PARABOLOID:
            return min(1.0, max(0.0, 1.0 - r * r))
        if code == P_GAUSSIAN:
            return math.exp(-4.0 * r * r)
        if code == P_PYRAMID:
            c = max(abs(2.0 * lx), abs(2.0 * ly))
            return max(0.0, 1.0 - c)
        if code == P_GRADATION:
            return min(1.0, max(0.0, 0.5 + lx))
        if code == P_BELL_T2:
            t = min(1.0, max(0.0, 1.0 - r * r))
            return t * t
        if code == P_HALFBELL_GAUSS:
            return math.exp(-4.0 * r * r) if ly >= 0.0 else 0.0
        if code == P_HALFBELL_PARAB:
            return min(1.0, max(0.0, 1.0 - r * r)) if ly >= 0.0 else 0.0
        if code == P_HALFBELL_GAUSS_X:
            return math.exp(-4.0 * r * r) if lx >= 0.0 else 0.0
        if code == P_HALFBELL_PARAB_X:
            return min(1.0, max(0.0, 1.0 - r * r)) if lx >= 0.0 else 0.0
        if code == P_HALFBELL_GAUSS_NX:
            return math.exp(-4.0 * r * r) if lx <= 0.0 else 0.0
        if code == P_HALFBELL_PARAB_NX:
            return min(1.0, max(0.0, 1.0 - r * r)) if lx <= 0.0 else 0.0
        if code == P_RIDGEDBELL:
            return max(0.0, 1.0 - r) * abs(math.cos(3.0 * math.pi * r))
        if code == P_THORN:
            t = max(0.0, 1.0 - r)
            return t * t * t
        if code == P_BRICK_INSET:
            c = max(abs(2.0 * lx), abs(2.0 * ly))
            return 1.0 if c <= 0.85 else 0.0
        if code == P_WAVES:
            return min(1.0, max(0.0, 0.5 + 0.5 * math.cos(2.0 * math.pi * lx * 2.0)))
        if code == P_CRESCENT:
            outer = max(0.0, 1.0 - r)
            inner = math.sqrt((2.0 * (lx - 0.15)) ** 2 + (2.0 * ly) ** 2)
            return outer if inner > 0.75 else 0.0
        if code == P_CAPSULE:
            d = abs(2.0 * ly)
            e = max(0.0, abs(2.0 * lx) - 0.5)
            return min(1.0, max(0.0, 1.0 - max(d, e)))
        return 0.0

    @njit(parallel=True, cache=True)
    def _raster(canvas, pxg, pyg, geo, box, cols):
        """Draw tiles into `canvas` IN ORDER at every pixel; parallel over rows.

        geo  (D, 6) float64   ux, uy, cos, sin, sx, sy
        box  (D, 6) int64     c0, c1, r0, r1, profile code, combine mode
        cols (D, C) float64   the pattern's per-channel opacity, clipped and scaled

        A pixel's draws are applied in queue order, as `splat` applied them, so `over` and
        `add` keep their order; distinct rows are independent, which is what makes the rows
        safe to split."""
        H = canvas.shape[0]
        C = canvas.shape[2]
        D = geo.shape[0]
        for y in prange(H):
            yc = np.float64(pyg[y])
            for d in range(D):
                if y < box[d, 2] or y > box[d, 3]:
                    continue
                ux = geo[d, 0]
                ct = geo[d, 2]
                st = geo[d, 3]
                sx = geo[d, 4]
                sy = geo[d, 5]
                code = box[d, 4]
                mode = box[d, 5]
                dy = yc - geo[d, 1]
                for x in range(box[d, 0], box[d, 1] + 1):
                    dx = np.float64(pxg[x]) - ux
                    lx = (dx * ct + dy * st) / sx
                    ly = (-dx * st + dy * ct) / sy
                    cov = _cov(lx, ly, code)
                    if not cov > 0.0:
                        continue
                    for c in range(C):
                        s = cols[d, c] * cov
                        dst = np.float64(canvas[y, x, c])
                        if mode == M_ADD:
                            canvas[y, x, c] = dst + s
                        elif mode == M_OVER:
                            a = min(abs(s), 1.0)
                            canvas[y, x, c] = dst * (1.0 - a) + s
                        else:
                            canvas[y, x, c] = max(dst, s)

    @njit(parallel=True, cache=True)
    def _bilinear(base, u, v, W, H):
        """`ops._fast_sampler`'s four-corner lerp in one pass: the same dtype steps (the
        difference in the image dtype, the lerps in float64), wrap-tiled."""
        N = u.shape[0]
        C = base.shape[1]
        out = np.empty((N, C), np.float64)
        for i in prange(N):
            fu0 = np.floor(u[i])
            fv0 = np.floor(v[i])
            u0 = np.int64(fu0)
            v0 = np.int64(fv0)
            fu = np.float64(u[i]) - np.float64(u0)
            fv = np.float64(v[i]) - np.float64(v0)
            u0m = u0 % W
            v0m = v0 % H
            u1m = (u0 + 1) % W
            v1m = (v0 + 1) % H
            r0 = v0m * W
            r1 = v1m * W
            for c in range(C):
                a0 = base[r0 + u0m, c]
                b0 = base[r0 + u1m, c]
                a1 = base[r1 + u0m, c]
                b1 = base[r1 + u1m, c]
                top = np.float64(b0 - a0) * fu + np.float64(a0)
                bot = np.float64(b1 - a1) * fu + np.float64(a1)
                out[i, c] = (bot - top) * fv + top
        return out

    @njit(cache=True)
    def _as_int64(f, inv_nan, inv_hi, inv_lo):
        # numpy's `astype(np.int64)` where the float has no int64: probed, not assumed.
        if f != f:
            return inv_nan
        if f >= 9.223372036854775807e18:
            return inv_hi
        if f < -9.223372036854775808e18:
            return inv_lo
        return np.int64(f)

    @njit(parallel=True, cache=True)
    def _nearest_kernel(base, pos, W, H, Wf, Hf, inv, out):
        pow2 = (W & (W - 1)) == 0 and (H & (H - 1)) == 0
        for i in prange(pos.shape[0]):
            u = _as_int64(np.floor(pos[i, 0] * Wf), inv[0], inv[1], inv[2])
            v = _as_int64(np.floor(pos[i, 1] * Hf), inv[0], inv[1], inv[2])
            if pow2:
                u &= W - 1
                v &= H - 1
            else:
                u %= W
                v %= H
            r = v * W + u
            for c in range(base.shape[1]):
                out[i, c] = base[r, c]


with np.errstate(invalid="ignore"):
    _INVALID_INT64 = np.array([np.nan, np.inf, -np.inf]).astype(np.int64)


def _nearest(base, pos, W, H, out_dtype):
    """`ops.nearest_sampler`'s texel gather in one pass: `floor(pos * W)` in pos's dtype,
    wrapped, gathered, written in `out_dtype`."""
    out = np.empty((pos.shape[0], base.shape[1]), out_dtype)
    t = pos.dtype.type
    _nearest_kernel(base, pos, W, H, t(W), t(H), _INVALID_INT64, out)
    return out


class TileQueue:
    """Tiles `splat` would have drawn, held until a draw the kernel cannot do (an image
    pattern, a tree batch, an unknown profile) or the end forces them out, in order."""

    def __init__(self, canvas, pxg, pyg):
        self.canvas, self.pxg, self.pyg = canvas, pxg, pyg
        self.geo, self.box, self.cols = [], [], []

    def add(self, ux, uy, ct, st, sx, sy, c0, c1, r0, r1, code, mode, col):
        self.geo.append((ux, uy, ct, st, sx, sy))
        self.box.append((c0, c1, r0, r1, code, mode))
        self.cols.append(col)

    def flush(self):
        if not self.geo:
            return
        C = self.canvas.shape[2]
        cols = np.zeros((len(self.cols), C), np.float64)
        for k, c in enumerate(self.cols):
            c = np.asarray(c, np.float64).ravel()
            cols[k, :] = c[:C] if c.size >= C else c[0]
        _raster(
            self.canvas,
            self.pxg,
            self.pyg,
            np.asarray(self.geo, np.float64),
            np.asarray(self.box, np.int64),
            cols,
        )
        self.geo, self.box, self.cols = [], [], []
