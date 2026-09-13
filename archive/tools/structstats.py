#!/usr/bin/env python3
"""Seed-free structural instruments: numbers a picture states about the nodes that made it.

Pixel correlation against a differently-seeded export measures the seed (FORMAT-NOTES.md,
"Arbitrating the subdivision draw model without corr"). What survives a reseed is the
STRUCTURE each node adds -- a row pitch, a mortar width, a per-brick tone, a grain -- so
these instruments each extract one such quantity from a single-channel image and report it
in pixels of the analysis grid or in image units. Every instrument is defined here in a
sentence, is measured on the Textures_1 / Textures_2 pair to state its own seed floor
(`--floor`), and is then a discriminator only for moves larger than that floor.

    level        mean, p5, p50, p95 of the channel
    pitch_x/y    period of the strongest repeat along each axis, from the autocorrelation
                 of the zero-mean channel (first local maximum past lag 2); `pitch_peak`
                 is the autocorrelation at that lag, 1.0 for a perfect repeat
    line_width   width of the thin dark structure: dark = below Otsu's threshold; the 25th
                 percentile of the lengths of dark runs along rows and columns. A thin line
                 crossed by a run gives its width; a blob gives its diameter, so this is the
                 LOWER quartile on purpose
    line_jitter  straightness of the horizontal dark lines: at every row-line the dark
                 fraction profile finds, the per-column centroid of darkness within a band
                 of +/- pitch_y/4; the standard deviation of that centroid, in px
    blob_d       median equivalent diameter of the bright connected components (above
                 Otsu, area >= 4 px), and `blob_n` their count per 256^2 px
    tone_between standard deviation of the per-blob mean level -- per-brick tone
    tone_within  mean of the per-blob standard deviation -- texture inside a brick
    grain        fraction of spectral power above half Nyquist (zero-mean channel)
    noise_lag1   lag-1 autocorrelation, x and y averaged -- 0 for white noise

    python3 archive/tools/structstats.py --floor            # T1 vs T2 per instrument
    python3 archive/tools/structstats.py --render a.npz [b.npz ...] --graph 003
    python3 archive/tools/structstats.py --records 9924,343 --assume fx.subdivide=tree
"""
import argparse
import glob
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
for p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "render2"), _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

GRID = 256


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def otsu(x):
    """Otsu's threshold on a [0, 1] channel, 256 bins."""
    h, edges = np.histogram(np.clip(x, 0, 1), bins=256, range=(0.0, 1.0))
    h = h.astype(np.float64)
    c = edges[:-1] + 0.5 / 256
    w0 = np.cumsum(h)
    w1 = w0[-1] - w0
    m0 = np.cumsum(h * c) / np.maximum(w0, 1e-9)
    m1 = (np.cumsum((h * c)[::-1])[::-1] - h * c) / np.maximum(w1, 1e-9)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(c[int(np.argmax(between))])


def autocorr_1d(x, axis):
    """Mean autocorrelation along `axis` of the zero-mean channel, lags 0..n/2."""
    y = x - x.mean()
    n = y.shape[axis]
    f = np.fft.rfft(y, n=2 * n, axis=axis)
    ac = np.fft.irfft(f * np.conj(f), n=2 * n, axis=axis)
    ac = np.take(ac, np.arange(n // 2), axis=axis)
    ac = ac.mean(axis=1 - axis)
    return ac / max(ac[0], 1e-12)


def first_peak(ac, lo=3):
    """(lag, height) of the first local maximum at lag >= lo, or (None, 0)."""
    for k in range(lo, len(ac) - 1):
        if ac[k] > ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] > 0:
            return k, float(ac[k])
    return None, 0.0


def runs(mask, axis):
    """Lengths of every True run along `axis`."""
    m = np.moveaxis(mask, axis, -1)
    pad = np.zeros(m.shape[:-1] + (1,), bool)
    d = np.diff(np.concatenate([pad, m, pad], axis=-1).astype(np.int8), axis=-1)
    starts = np.argwhere(d == 1)
    ends = np.argwhere(d == -1)
    return (ends[:, -1] - starts[:, -1]).astype(np.int64)


def label(mask):
    """Connected components, 4-connected. Returns (labels, count) without scipy."""
    try:
        from scipy import ndimage

        lab, n = ndimage.label(mask)
        return lab, n
    except ImportError:
        pass
    H, W = mask.shape
    lab = np.zeros((H, W), np.int32)
    n = 0
    for r in range(H):
        for c in range(W):
            if mask[r, c] and lab[r, c] == 0:
                n += 1
                stack = [(r, c)]
                lab[r, c] = n
                while stack:
                    y, x = stack.pop()
                    for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and lab[yy, xx] == 0:
                            lab[yy, xx] = n
                            stack.append((yy, xx))
    return lab, n


# ---------------------------------------------------------------------------
# instruments
# ---------------------------------------------------------------------------


def instruments(x):
    """Every instrument on one channel `x`, an (H, W) float array in [0, 1]."""
    x = np.asarray(x, np.float64)
    H, W = x.shape
    out = {}
    p = np.percentile(x, [5, 50, 95])
    out.update(mean=x.mean(), p5=p[0], p50=p[1], p95=p[2], sd=x.std())
    flat = x.std() < 1e-6
    if flat:
        return out

    acx, acy = autocorr_1d(x, 1), autocorr_1d(x, 0)
    kx, hx = first_peak(acx)
    ky, hy = first_peak(acy)
    out.update(pitch_x=kx, pitch_y=ky, pitch_peak=max(hx, hy))
    out["noise_lag1"] = 0.5 * (acx[1] + acy[1])

    t = otsu(x)
    dark = x < t
    bright = ~dark
    rl = np.concatenate([runs(dark, 0), runs(dark, 1)])
    out["line_width"] = float(np.percentile(rl, 25)) if rl.size else 0.0

    # horizontal line jitter: rows whose dark fraction is a local peak above the mean
    frac = dark.mean(axis=1)
    band = max(2, int((ky or 16) // 4))
    rows = [
        r
        for r in range(band, H - band)
        if frac[r] > frac.mean() and frac[r] >= frac[r - band : r + band + 1].max()
    ]
    jit = []
    for r in rows:
        sl = dark[r - band : r + band + 1].astype(np.float64)
        wsum = sl.sum(axis=0)
        ok = wsum > 0
        if ok.sum() < W // 4:
            continue
        cen = (sl * np.arange(-band, band + 1)[:, None]).sum(axis=0)[ok] / wsum[ok]
        jit.append(cen.std())
    out["line_jitter"] = float(np.mean(jit)) if jit else 0.0

    lab, n = label(bright)
    if n:
        areas = np.bincount(lab.ravel())[1:]
        keep = np.nonzero(areas >= 4)[0] + 1
        if keep.size:
            sums = np.bincount(lab.ravel(), weights=x.ravel())[1:]
            sq = np.bincount(lab.ravel(), weights=(x.ravel() ** 2))[1:]
            a = areas[keep - 1].astype(np.float64)
            m = sums[keep - 1] / a
            v = np.maximum(sq[keep - 1] / a - m * m, 0.0)
            out["blob_d"] = float(np.median(2.0 * np.sqrt(a / np.pi)))
            out["blob_n"] = float(keep.size) * (256.0 * 256.0) / (H * W)
            out["tone_between"] = float(m.std())
            out["tone_within"] = float(np.sqrt(v).mean())

    f = np.abs(np.fft.fftshift(np.fft.fft2(x - x.mean()))) ** 2
    yy, xx = np.mgrid[:H, :W]
    r = np.hypot(yy - H / 2, xx - W / 2)
    nyq = min(H, W) / 2.0
    tot = f[r >= 1].sum()
    out["grain"] = float(f[r >= nyq / 2].sum() / tot) if tot > 0 else 0.0
    return out


KEYS = [
    "mean", "p5", "p50", "p95", "sd", "pitch_x", "pitch_y", "pitch_peak",
    "line_width", "line_jitter", "blob_d", "blob_n", "tone_between", "tone_within",
    "grain", "noise_lag1",
]


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------


def load_png(path, n=GRID):
    from PIL import Image

    im = Image.open(path)
    a = np.asarray(im).astype(np.float64)
    a = a / (65535.0 if (im.mode == "I;16" or a.max() > 255) else 255.0)
    a = a[:, :, :3] if a.ndim == 3 else a[:, :, None]
    return resample(a, n)


def resample(a, n=GRID):
    from PIL import Image

    return np.stack(
        [
            np.asarray(
                Image.fromarray((np.clip(a[:, :, c], 0, 1) * 65535).astype(np.uint16)).resize(
                    (n, n), Image.BILINEAR
                ),
                dtype=np.float64,
            )
            / 65535.0
            for c in range(a.shape[2])
        ],
        -1,
    )


BRICKS = os.path.join(
    ROOT, "archive", "specimens", "new_opengameart", "Kutejnikov__Bricks_and_tiles"
)


def _bricks_outputs():
    import xml.etree.ElementTree as ET

    import manifest
    import sbsasm

    ap = glob.glob(BRICKS + "/x_Bricks_Textures_1/assemblies/content/0000/*.sbsasm")[0]
    asm = sbsasm.Assembly(ap)
    names = manifest.output_names(asm)
    root = ET.parse(sorted(glob.glob(os.path.dirname(ap) + "/*.xml"))[0]).getroot()
    uid2 = {
        int(o.get("uid")): (g.get("pkgurl") or "").split("/")[-1]
        for g in root.iter("graph")
        for o in g.iter("output")
    }
    return [(uid2.get(uid), names.get(uid), ri) for uid, _f, _g, ri in asm.outputs()]


def fmt(v):
    if v is None:
        return "     --"
    return "%7.3f" % v if abs(v) < 100 else "%7.1f" % v


def floor_report(graphs=("001", "002", "003"), grid=GRID):
    """Each instrument on Textures_1 and Textures_2, and the seed floor it implies."""
    print("seed floor: Textures_1 against Textures_2, channel 0, %d-px grid" % grid)
    print("%-22s" % "output" + "".join("%8s" % k[:7] for k in KEYS))
    rel = {k: [] for k in KEYS}
    for p1 in sorted(glob.glob(BRICKS + "/reference_renders/Textures_1/*_*.png")):
        nm = os.path.basename(p1)[:-4]
        if nm[:3] not in graphs:
            continue
        p2 = p1.replace("Textures_1", "Textures_2")
        if not os.path.exists(p2):
            continue
        a, b = instruments(load_png(p1, grid)[:, :, 0]), instruments(load_png(p2, grid)[:, :, 0])
        print("%-22s" % nm + "".join("%8s" % fmt(a.get(k)) for k in KEYS))
        print("%-22s" % "  T2" + "".join("%8s" % fmt(b.get(k)) for k in KEYS))
        for k in KEYS:
            if a.get(k) is not None and b.get(k) is not None:
                rel[k].append(abs(a[k] - b[k]) / (abs(a[k]) + abs(b[k]) + 1e-9) * 2)
    print()
    print("%-14s %8s %8s   (relative |T1-T2| over the randomised graphs)" % ("instrument", "median", "max"))
    for k in KEYS:
        if rel[k]:
            print("%-14s %8.3f %8.3f" % (k, np.median(rel[k]), max(rel[k])))


def render_report(npzs, graph, outputs=None, grid=GRID):
    """Each instrument on the reference and on every saved render, per output channel 0."""
    outs = [(g, nm, ri) for g, nm, ri in _bricks_outputs() if g == graph]
    zs = [np.load(f) for f in npzs]
    labels = ["T1"] + [os.path.basename(f)[:-4] for f in npzs]
    print("graph %s, channel 0, %d-px grid" % (graph, grid))
    for g, nm, ri in outs:
        if outputs and nm not in outputs:
            continue
        ref = BRICKS + "/reference_renders/Textures_1/%s_%s.png" % (g, nm)
        if not os.path.exists(ref):
            continue
        rows = [instruments(load_png(ref, grid)[:, :, 0])]
        for z in zs:
            if str(ri) not in z.files:
                rows.append({})
                continue
            a = np.asarray(z[str(ri)], np.float64)
            a = a if a.ndim == 3 else a[:, :, None]
            rows.append(instruments(resample(a, grid)[:, :, 0]))
        print("%-22s" % nm + "".join("%8s" % k[:7] for k in KEYS))
        for lab, r in zip(labels, rows):
            print("%-22s" % ("  " + lab[:20]) + "".join("%8s" % fmt(r.get(k)) for k in KEYS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", action="store_true")
    ap.add_argument("--render", nargs="*", default=None)
    ap.add_argument("--graph", default="003")
    ap.add_argument("--outputs", default=None)
    ap.add_argument("--grid", type=int, default=GRID)
    ap.add_argument("--records", default=None, help="fxmaps record indices, comma-separated")
    ap.add_argument(
        "--assume",
        default="",
        help="assume.scope choices for --records, e.g. fx.subdivide=tree,fx.tree.order=clockwise",
    )
    a = ap.parse_args()
    if a.records:
        record_report([int(x) for x in a.records.split(",")], choices=a.assume)
    if a.floor:
        floor_report(grid=a.grid)
    if a.render:
        render_report(a.render, a.graph, a.outputs.split(",") if a.outputs else None, a.grid)



# ---------------------------------------------------------------------------
# per-record self-consistency: a generator's own statistics, no reference needed
# ---------------------------------------------------------------------------


def record_report(indices, asm_path=None, choices=""):
    """Render each fxmaps record under `assume.scope(**choices)` and print its instruments
    at native size. A `rand(1.0)` leaf at one cell per pixel must read mean 0.50, sd 0.29,
    noise_lag1 ~0; anything else is the combine rule or the depth.

    `choices` is `k=v,...` -- `fx.subdivide=tree` is the renderer's own subdivision arm
    (`render2.fxtree`), which replaced the probe import this used to make; the probe's
    knobs map onto `fx.tree.branchoffset` and `fx.tree.order`. `pats` counts PATTERNS:
    a `fxtree.Batch` is one cell's m patterns and counts m.
    """
    import fxrender
    import sbsasm
    from render2 import engine, fx, model
    import assume

    asm = sbsasm.Assembly(
        asm_path or glob.glob(BRICKS + "/x_Bricks_Textures_1/assemblies/content/0000/*.sbsasm")[0]
    )
    ctx = engine.Context(asm, cap=256)
    extra = {k.split("=")[0]: k.split("=")[1] for k in (choices or os.environ.get("ASSUME", "")).split(",") if "=" in k}
    print("assume:", extra or "(defaults)")
    print("%-8s %-9s %6s" % ("record", "size", "pats") + "".join("%8s" % k[:7] for k in ("mean", "sd", "p5", "p95", "noise_lag1", "pitch_x", "blob_d", "line_width")))
    with assume.scope(**extra):
        for ri in indices:
            rec = asm.records[ri]
            v = model.View(asm, rec)
            run = fxrender.make_runner(asm, rec, programs=ctx.fx_funcs, cache_funcs=ctx.cache_funcs)
            try:
                pats = fx.emissions(rec, run, fxrender.seed_slots(rec, run), cache=ctx.cache)
                img = fx.splat(rec, pats, v.width, v.height)[..., 0]
            except Exception as e:
                print("%-8d %-9s REFUSED: %s" % (ri, "%dx%d" % (v.width, v.height), e))
                continue
            n = sum(getattr(p, "count", 1) for p in pats)
            r = instruments(img)
            print("%-8d %-9s %6d" % (ri, "%dx%d" % (v.width, v.height), n) + "".join("%8s" % fmt(r.get(k)) for k in ("mean", "sd", "p5", "p95", "noise_lag1", "pitch_x", "blob_d", "line_width")))


if __name__ == "__main__":
    main()
