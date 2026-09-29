#!/usr/bin/env python3
"""Two feature instruments on Kutejnikov__Bricks_and_tiles' HEIGHT, ours against the export,
at native 1024 through `render2-lean`: the mortar JOINTS and the 004 WHEEL SPOKES.

    python3 archive/tools/grooves.py                                   # current defaults
    python3 archive/tools/grooves.py warp.reference_px=tag,dirmotionblur.extent=x8render

WHY THESE AND NOT A GUARD ROW. Both faults were found by looking (Ash, on the sheets: "the
line width on bricks, height and normal", "the radial line on 004 normal"), and neither is
a function any corr/band/dc column is sensitive to in a way that can arbitrate. They decided
`dirmotionblur.extent` and `fx.halfbell`. See FORMAT-NOTES.md, "The round-tile groove" and
"The six-spoke wheel". They were first written as throwaways in a session scratchpad that a
container restart then wiped, while the notes still cited them -- so they live here now.

JOINTS. Every straight joint found ON THE EXPORT by its own minimum: a 60-px band-mean
profile, a local minimum over +/-6 px, depth > 0.25 below the band median, and floor/face
< 0.5 so shallow features are not joints. At the same place in ours, floor/face (how deep
the groove sits against the tile face) and the half-depth width. Reports the medians. THE
WHOLE-IMAGE OTSU THIS REPLACES MISREAD 004 AS FINE (1.08) BECAUSE IT AVERAGES JOINTS WITH
EVERY OTHER DARK FEATURE; per joint 004 and 005 are equally wrong under the default.

SPOKES. Graph 004's four wheels (tile centres at 256 / 768), the angular profile at r = 80 /
95 / 110 px, dark where it is below the ring's own mid-range; the mean dark run converted to
px. DO NOT READ A ROTATION off a six-fold profile's harmonic phase: it flips by 30 degrees
whenever the dark duty crosses a half, which is how a phantom -25..-30 degree "rotation"
was once reported.

Recorded values to reproduce (the 2026-09-24 default / every arm):
    joints  004 floor/face 0.043 / ~0.30, width ratio 0.75 / 1.00;  005 the same
    spokes  (256,256) 35.6 34.0 33.0 px / ~13.4 11.8 9.9;  export 11.3 9.6 8.3
The spokes' second column is today's default (`fx.halfbell = gaussian`, promoted 2026-09-28);
`fx.halfbell=paraboloid` gives the first.
"""
import os, sys, time
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "render2"), _HERE):
    sys.path.insert(0, _p)
import glob  # noqa: E402
import assume, refcompare as rc, sbsasm, structstats as ss  # noqa: E402

N = 1024


def arms(text):
    out = dict(kv.split("=", 1) for kv in (text or "").split(",") if kv)
    for k, v in list(out.items()):
        if k not in assume.QUESTIONS:
            raise SystemExit("grooves: %r is not an assume question" % k)
        for c in assume.QUESTIONS[k]:
            if str(c) == v:
                out[k] = c
                break
        else:
            raise SystemExit("grooves: %r is not a candidate for %r" % (v, k))
    return out


def _joints(a):
    out = []
    for axis in (0, 1):
        for band in ((40, 120), (430, 510), (560, 640), (900, 980)):
            s = a[band[0]:band[1], :].mean(0) if axis == 0 else a[:, band[0]:band[1]].mean(1)
            face = np.median(s)
            for c in range(20, N - 20):
                if s[c] == s[c - 6:c + 7].min() and face - s[c] > 0.25:
                    out.append((axis, band, c))
    return out


def _profile(a, j):
    axis, band, c = j
    s = a[band[0]:band[1], :].mean(0) if axis == 0 else a[:, band[0]:band[1]].mean(1)
    return s.take(range(c - 30, c + 31), mode="wrap")


def _shape(p):
    face = np.median(np.r_[p[:8], p[-8:]])
    lo = p[25:36].min()
    if face - lo < 0.05 or face <= 0:
        return None
    n = (p - lo) / (face - lo)
    c = 25 + int(np.argmin(p[25:36]))
    L = c
    while L > 0 and n[L] < 0.5:
        L -= 1
    R = c
    while R < len(n) - 1 and n[R] < 0.5:
        R += 1
    return lo / face, R - L


def joints(ours, ref):
    fo, fe, wo, we = [], [], [], []
    for j in _joints(ref):
        e, o = _shape(_profile(ref, j)), _shape(_profile(ours, j))
        if e is None or o is None or e[0] > 0.5:
            continue
        fe.append(e[0]); fo.append(o[0]); we.append(e[1]); wo.append(o[1])
    if not fe:
        return None
    return len(fe), np.median(fo), np.median(fe), np.median(wo), np.median(we)


def spokes(a, cx, cy, r):
    th = np.linspace(0, 2 * np.pi, 1440, endpoint=False)
    p = a[np.clip(np.round(cy - r * np.sin(th)).astype(int), 0, N - 1),
          np.clip(np.round(cx + r * np.cos(th)).astype(int), 0, N - 1)]
    return (p < (p.max() + p.min()) / 2).mean() * 360 / 6 * np.pi / 180 * r


def main(argv):
    choices = arms(argv[1] if len(argv) > 1 else "")
    ap = glob.glob(ss.BRICKS + "/x_Bricks_Textures_1/assemblies/content/0000/*.sbsasm")[0]
    asm = sbsasm.Assembly(ap)
    hts = {g: ri for g, nm, ri in ss._bricks_outputs() if nm == "height"}
    t0 = time.time()
    with assume.scope(**choices):
        outs = rc._renderer("render2-lean")(asm, 1 << 10, None, (10, 10))
    print("arms %s   render %.0fs" % (choices or "{} (defaults)", time.time() - t0), flush=True)
    H = {}
    for g in ("002", "004", "005"):
        a = np.asarray(outs[hts[g]], np.float64)
        H[g] = a[:, :, 0] if a.ndim == 3 else a
        ref = rc.load_reference(ss.BRICKS + "/reference_renders/Textures_1/%s_height.png" % g)[:, :, 0]
        if g == "004":
            ref004 = ref
        r = joints(H[g], ref)
        if r is None:
            print("   joints %s: none found" % g)
            continue
        n, fo, fe, wo, we = r
        print("   joints %s  n=%2d   floor/face ours %.3f export %.3f   half-depth width ours %.1f export %.1f  ratio %.2f"
              % (g, n, fo, fe, wo, we, wo / we), flush=True)
    for c in ((256, 256), (768, 256), (256, 768), (768, 768)):
        print("   spokes 004 wheel %-10s r=80/95/110   ours %s   export %s" % (
            c, " / ".join("%5.1f" % spokes(H["004"], c[0], c[1], r) for r in (80, 95, 110)),
            " / ".join("%5.1f" % spokes(ref004, c[0], c[1], r) for r in (80, 95, 110))), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
