#!/usr/bin/env python3
"""A BENCH for FX-Map questions: seconds per arm instead of minutes per sweep.

WHY THE SWEEP IS THE WRONG SHAPE. Arbitrating a draw-side FX question by rendering 150
files evaluates ~300,000 records to learn about a few dozen fxmaps ones, and returns a
single scalar that says which arm won without saying what changed. Each cycle costs
minutes and answers one question.

WHAT THIS DOES INSTEAD, and why it is sound rather than merely quicker:

  * A FIXED RECORD SET with KNOWN SIGNATURES, not a corpus. Each entry is a record this
    notebook has already characterised, so a number that moves is interpretable
    immediately.
  * EMISSIONS ARE EXTRACTED ONCE AND REUSED. The expensive half of an FX-Map is the walk
    and its programs; `splat` is pure numpy over a pattern list. Every DRAW-side question
    -- `fx.sizeless`, `fx.combine`, `fx.profile`, `fx.typeless_profile`, `fx.patternsize`,
    `fx.branchoffset`, `fx.frameoffset`, `fx.rootentry`, `fx.markers`, `fx.negopacity` --
    changes only how a fixed pattern list is drawn, so the walk need not be repeated.
  * IT REPORTS A DIAGNOSIS, NOT A SCORE: pattern count, size range, lit fraction, sd, and
    whether the result is constant. "Flat" and "why flat" arrive together.

WHAT IT CANNOT ANSWER. `fx.gridcount`, `fx.gatescan` and `fx.scanner` change the EMISSION
itself, so the cache is invalid for them -- pass `fresh=True` and pay the walk. And a bench
of fifteen records is not a corpus: it tells you what an arm DOES, quickly, so that only the
survivors need a sweep to tell you how often.
"""

import sys, time, collections

sys.path.insert(0, "/Users/pera/Documents/cleanroom-substance/tools")
sys.path.insert(0, "/Users/pera/Documents/cleanroom-substance/tools/render2")
import numpy as np, sbsasm, assume
import fx as FX
from render2 import engine

ROOT = "/Users/pera/Documents/cleanroom-substance/archive/specimens/new_opengameart/"
BENCH = [
    (
        ROOT
        + "minime453__Chesterfield_PBR_Material/x_ChesterfieldSofa/assemblies/content/0000/ChesterfieldSofa.sbsasm",
        331,
        "Chesterfield 331  saturates to 1.0 -- carries patternsize (5.0, 1.0) at opacity -1",
    ),
    (
        ROOT
        + "minime453__Chesterfield_PBR_Material/x_ChesterfieldSofa/assemblies/content/0000/ChesterfieldSofa.sbsasm",
        333,
        "Chesterfield 333  saturates to 1.0, feeds subtract -> 334 = 0",
    ),
    (
        ROOT + "Kutejnikov__Auras/x_Auras_FX/assemblies/content/0000/Auras_FX.sbsasm",
        427,
        "Auras 427  144 bells at 2.82, dome 0.69..1.0",
    ),
    (
        ROOT + "Kutejnikov__Auras/x_Auras_FX/assemblies/content/0000/Auras_FX.sbsasm",
        428,
        "Auras 428  same draw point-reflected; |427-428| = 3e-3",
    ),
    (
        ROOT
        + "minime453__Chesterfield_PBR_Material/x_ChesterfieldSofa/assemblies/content/0000/ChesterfieldSofa.sbsasm",
        92,
        "Chesterfield 92  25 bells at 2.82, pairs with 93",
    ),
    (
        ROOT
        + "minime453__Chesterfield_PBR_Material/x_ChesterfieldSofa/assemblies/content/0000/ChesterfieldSofa.sbsasm",
        93,
        "Chesterfield 93  the 0x18B sibling of 92",
    ),
    (
        ROOT
        + "minime453__Chesterfield_PBR_Material/x_ChesterfieldSofa/assemblies/content/0000/ChesterfieldSofa.sbsasm",
        321,
        "Chesterfield 321  emits 0 -- gate 2 is a $sizelog2>=12 guard, CORRECTLY closed",
    ),
    (
        "/Users/pera/Documents/cleanroom-substance/pairs2/x_Stadsspel__Lines/assemblies/content/0000/Lines.sbsasm",
        0,
        "Lines 0  THE VERIFIED CONTROL -- 10 strips, lit 0.5078",
    ),
]
_asm = {}


def asm_for(p):
    if p not in _asm:
        _asm[p] = sbsasm.Assembly(p)
    return _asm[p]


_pats = {}


def emissions_for(path, idx, cap=128, fresh=False):
    key = (path, idx, cap)
    if key in _pats and not fresh:
        return _pats[key]
    grab = {}
    orig = FX.splat

    def spy(rec, patterns, W, H, images=None):
        p = list(patterns)
        if rec.index == idx:
            grab["p"] = (p, W, H, dict(images or {}))
        return orig(rec, p, W, H, images=images)

    FX.splat = spy
    try:
        engine.render(asm_for(path), max_dim=cap, outputsize=11)
    except Exception:
        pass
    finally:
        FX.splat = orig
    _pats[key] = grab.get("p")
    return _pats[key]


def draw(path, idx, arms=None, cap=128):
    got = emissions_for(path, idx, cap)
    if got is None:
        return None
    pats, W, H, images = got
    rec = asm_for(path).records[idx]
    if arms:
        with assume.scope(**arms):
            a = FX.splat(rec, [dict(q) for q in pats], W, H, images=images)
    else:
        a = FX.splat(rec, [dict(q) for q in pats], W, H, images=images)
    return np.asarray(a, dtype=np.float32), pats


def diagnose(a, pats):
    g = a[:, :, 0] if a.ndim == 3 else a
    sizes = [
        np.asarray(p["patternsize"], dtype=float).ravel()[0]
        for p in pats
        if p.get("patternsize") is not None
    ]
    return dict(
        n=len(pats),
        sized=len(sizes),
        size=(round(min(sizes), 3), round(max(sizes), 3)) if sizes else None,
        mean=round(float(g.mean()), 4),
        sd=round(float(g.std()), 6),
        lit=round(float((g > 1e-3).mean()), 4),
        flat=bool(g.std() < 1e-9),
    )


if __name__ == "__main__":
    arms = [
        None,
        {"fx.sizeless": "skip"},
        {"fx.sizeless": "half"},
        {"fx.combine": "add"},
    ]
    t0 = time.time()
    for path, idx, label in BENCH:
        print("\n%s" % label)
        for arm in arms:
            r = draw(path, idx, arm)
            if r is None:
                print("   %-24s (no emissions)" % (arm or "default"))
                continue
            a, pats = r
            nm = (
                "default"
                if arm is None
                else ",".join("%s=%s" % kv for kv in arm.items())
            )
            print("   %-24s %s" % (nm, diagnose(a, pats)))
    print(
        "\nwall clock: %.1fs for %d records x %d arms"
        % (time.time() - t0, len(BENCH), len(arms))
    )
