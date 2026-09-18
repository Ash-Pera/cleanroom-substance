#!/usr/bin/env python3
"""Checks for the FX-Map subdivision arm, `render2.fxtree`.

    python3 tools/render2/test_fxtree.py
    python3 -m pytest tools/render2/test_fxtree.py -q

Three kinds. The STRUCTURAL checks read the cells' own words on the Bricks specimen and
assert the layout `fxtree.pointer_slot` states. The EQUALITY checks hold the grid drawer
to `fx.splat`'s per-pattern loop and the tree arm to the flat arm where the two must
agree -- a depth-0 record -- with no reference. The INSTRUMENT check is the notebook's
own arbiter for the root convention: a `rand(1.0)` leaf at one cell per pixel reads as
white noise. Render checks skip loudly without the specimen.
"""

import glob
import os
import struct
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.append(_HERE)  # see __init__.py: this package goes LAST

import assume  # noqa: E402
import fxrender  # noqa: E402
import fxtree  # noqa: E402
import fx  # noqa: E402
import model  # noqa: E402
import sbsasm  # noqa: E402
import sbsruntime  # noqa: E402
from engine import Context  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRICKS = os.path.join(
    ROOT,
    "archive",
    "specimens",
    "new_opengameart",
    "Kutejnikov__Bricks_and_tiles",
    "x_Bricks_Textures_1",
    "assemblies",
    "content",
    "0000",
)


def _skip(reason):
    pytest = sys.modules.get("pytest")
    if pytest is not None:
        pytest.skip(reason)
    print("SKIP " + reason)


def _bricks():
    got = glob.glob(os.path.join(BRICKS, "*.sbsasm"))
    return sbsasm.Assembly(got[0]) if got else None


def _render(asm, ri, cap=256, **choices):
    rec = asm.records[ri]
    v = model.View(asm, rec)
    W, H = v.size(cap)
    ctx = Context(asm, cap=cap)
    run = fxrender.make_runner(asm, rec, programs=ctx.fx_funcs, cache_funcs=ctx.cache_funcs)
    with assume.scope(**choices):
        pats = fx.emissions(rec, run, fxrender.seed_slots(rec, run), cache=ctx.cache)
        img = fx.splat(rec, pats, W, H, header=fx.header_fields(ctx, v))
    return img, sum(getattr(p, "count", 1) for p in pats)


# ---------------------------------------------------------------------------
# structural
# ---------------------------------------------------------------------------


def test_the_child_pointer_sits_before_the_bit4_word_and_after_the_bit7_word():
    """`pointer_slot`'s layout, read back from Bricks' own cells.

    Every bit-4 cell with a bit-17 pointer resolves at word 2 and holds a small integer
    at word 3; every bit-7 cell resolves at word 3. `sbsasm.fx_entry_walk`'s ascending
    order would put the bit-4 word first, and this is the measurement that says the
    file does not.
    """
    asm = _bricks()
    if asm is None:
        return _skip("no Bricks specimen")
    data = asm.data
    bit4 = bit7 = 0
    for rec in asm.records:
        if rec.filter_name != "fxmaps":
            continue
        table = fxrender.entries(rec)
        if not table:
            continue
        cells, _order, _roots = fxtree.cells_of(rec, table)
        for c in cells.values():
            if not (c.tag >> 17) & 1 or (c.tag >> 16) & 1:
                continue
            base = fxtree._tag_base(data, c.off, c.tag)
            w = [struct.unpack_from("<I", data, base + 4 * k)[0] for k in range(4)]
            if (c.tag >> 4) & 1:
                bit4 += 1
                assert w[2] + fxtree.SKEW in cells or w[2] + fxtree.SKEW + 4 in cells
                assert w[3] < 256, "the bit-4 word is a small integer, %#x" % w[3]
            if (c.tag >> 7) & 1:
                bit7 += 1
                assert w[3] + fxtree.SKEW in cells or w[3] + fxtree.SKEW + 4 in cells
                assert w[2] + fxtree.SKEW not in cells
    assert bit4 >= 30 and bit7 >= 10, (bit4, bit7)
    print("ok  pointer slot: %d bit-4 cells at word 2, %d bit-7 cells at word 3" % (bit4, bit7))


def test_every_bricks_tree_reads_and_the_first_walked_entry_is_a_root():
    asm = _bricks()
    if asm is None:
        return _skip("no Bricks specimen")
    n = deep = 0
    for rec in asm.records:
        if rec.filter_name != "fxmaps":
            continue
        table = fxrender.entries(rec)
        if not table:
            continue
        cells, order, roots = fxtree.cells_of(rec, table)
        n += 1
        assert order[0] in roots, rec.index
        fxtree.topological(cells, roots)
        d = fxtree.depth_census(rec, table)
        if max(d.values()) > 0:
            deep += 1
    assert n == 191 and deep == 95, (n, deep)
    print("ok  191 Bricks trees read, 95 subdivide, every first entry a root")


# ---------------------------------------------------------------------------
# equalities
# ---------------------------------------------------------------------------


def test_rand_with_zero_salt_is_bit_identical_to_the_unsalted_hash():
    saved = dict(sbsruntime.CONTEXT)
    try:
        for num in (0.0, 3.0, np.arange(5.0)):
            sbsruntime.set_context(number=num)
            sbsruntime.CONTEXT["salt"] = 0.0
            x = np.array([1.0, 2.0, 6.28, 0.0625, 360.0])
            n = num.reshape(-1, 1) if isinstance(num, np.ndarray) else num
            ref = x * (np.modf(np.sin(x * 12.9898 + n * 78.233) * 43758.5453)[0] % 1.0)
            got = sbsruntime.rand(x)
            assert np.array_equal(got, ref)
            sbsruntime.CONTEXT["salt"] = np.zeros((5, 1)) if isinstance(num, np.ndarray) else 0.0
            assert np.array_equal(sbsruntime.rand(x), ref)
            sbsruntime.CONTEXT["salt"] = 1.0
            assert not np.array_equal(sbsruntime.rand(x), ref)
    finally:
        sbsruntime.CONTEXT.clear()
        sbsruntime.CONTEXT.update(saved)
    print("ok  rand: zero salt is the old hash bit for bit")


def _synthetic_batches(rng, W, H, nchan, with_image):
    """A few batches of random patterns, as `Batch` and as the same dicts."""
    batches = []
    for tag, prof_type in ((0x15400348, 5), (0x4540048, None), (0x12400648, 3), (0x84520088, 8)):
        m = int(rng.integers(20, 60))
        centre = rng.uniform(-0.6, 0.6, (m, 2))
        size = rng.uniform(0.01, 0.4, (m, 2))
        size[: m // 4, :] = rng.uniform(0.8, 2.5, (m // 4, 2))  # a few that wrap
        fo = rng.uniform(-0.05, 0.05, (m, 2))
        rot = rng.uniform(0, 1, m)
        opa = rng.uniform(0, 1, (m, nchan)).astype(np.float32)
        img = np.full(m, 0.0) if with_image else None
        b = fxtree.Batch(tag, m, centre, size, fo, rot, opa, img, np.zeros(m, np.int64))
        b.patterntype = prof_type
        batches.append(b)
    return batches


def test_the_grid_drawer_is_the_per_pattern_loop():
    """`fxtree.draw` against `fx.splat`'s loop over the same patterns, max and add."""
    rng = np.random.default_rng(7)

    class Rec(object):
        colour = False

    for nchan, with_image, mode in ((1, False, "max"), (4, False, "max"), (1, True, "max"), (1, False, "add")):
        W, H = 96, 64
        rec = Rec()
        rec.colour = nchan == 4
        batches = _synthetic_batches(rng, W, H, nchan, with_image)
        images = {0: rng.uniform(0, 1, (32, 32, 4)).astype(np.float32)} if with_image else None
        dicts = [q for b in batches for q in b.as_dicts()]
        with assume.scope(**{"fx.combine": mode}):
            a = fx.splat(rec, batches, W, H, images=images)
            b = fx.splat(rec, dicts, W, H, images=images)
        assert a.shape == b.shape == (H, W, nchan)
        assert a.max() > 0.5
        err = float(np.abs(a - b).max())
        # `max` is order-free and the casts are the loop's own, so it is an EQUALITY;
        # `add` sums in a different order and is held to float32 noise.
        tol = 0.0 if mode == "max" else 1e-4
        assert err <= tol, (nchan, with_image, mode, err)
    print("ok  the grid drawer equals the per-pattern loop on %d synthetic batches" % (4 * 4))


def test_a_depth_zero_record_draws_the_same_under_both_arms():
    """Where nothing subdivides the tree arm IS the flat arm: same draws, same pixels."""
    asm = _bricks()
    if asm is None:
        return _skip("no Bricks specimen")
    checked = 0
    for rec in asm.records:
        if rec.filter_name != "fxmaps":
            continue
        d = fxtree.depth_census(rec)
        if not d or max(d.values()) != 0:
            continue
        try:
            flat, nf = _render(asm, rec.index, cap=128)
        except Exception:
            continue
        tree, nt = _render(asm, rec.index, cap=128, **{"fx.subdivide": "tree"})
        assert nf == nt, (rec.index, nf, nt)
        assert np.array_equal(flat, tree), (rec.index, float(np.abs(flat - tree).max()))
        checked += 1
        if checked >= 12:
            break
    assert checked >= 6, checked
    print("ok  %d depth-0 records identical under flat and tree" % checked)


# ---------------------------------------------------------------------------
# instruments
# ---------------------------------------------------------------------------


def test_a_rand_leaf_under_five_quadrants_is_white_noise():
    """Record 9924: `rand(1.0)` opacity, 16 x 16, one cell per pixel under the root
    convention. Uniform white noise is mean 0.500, sd 0.289, lag-1 0; the notebook
    measured 0.513 / 0.292 / -0.012 and the root-subdivides reading 0.80 / 0.16."""
    asm = _bricks()
    if asm is None:
        return _skip("no Bricks specimen")
    img, n = _render(asm, 9924, **{"fx.subdivide": "tree"})
    x = img[..., 0].astype(np.float64)
    assert x.shape == (16, 16) and n == 342, (x.shape, n)
    y = x - x.mean()
    lag = 0.5 * (
        (y[:, 1:] * y[:, :-1]).mean() / y.var() + (y[1:, :] * y[:-1, :]).mean() / y.var()
    )
    assert abs(x.mean() - 0.5) < 0.05 and abs(x.std() - 0.289) < 0.04 and abs(lag) < 0.15, (
        x.mean(),
        x.std(),
        lag,
    )
    flat, _n = _render(asm, 9924)
    assert flat.std() < 1e-6, "the flat arm draws one pattern: a constant"
    print("ok  9924 under the tree arm: mean %.3f sd %.3f lag-1 %+.3f" % (x.mean(), x.std(), lag))


def test_the_header_names_background_hurst_and_opacitymult_and_the_default_reads_them():
    """Records 9806 / 9804: the `opacity = -1` record bakes `background` 1.0 beside
    `hurst` 0.66 and `opacitymult` 0.44; its 256-px sibling bakes the same two and no
    background. The names are `model.W1_PARAMS`' (Clouds_3's 0.42 / 10.7 at fields 1 / 2,
    ie_particles' (0,0,0,1) at field 0). Under the defaults the draw does not read them --
    9806 is the zero the notebook recorded -- and under `fx.header=read` with a signed add
    the record is the white canvas minus its strokes, at a mean the thresholds downstream
    can cut. See FORMAT-NOTES.md, "Graph 001's first annihilation point is a white canvas
    the file states"."""
    asm = _bricks()
    if asm is None:
        return _skip("no Bricks specimen")
    v6 = model.View(asm, asm.records[9806])
    v4 = model.View(asm, asm.records[9804])
    assert abs(v6.baked("background") - 1.0) < 1e-6, v6.params
    assert abs(v6.baked("hurst") - 0.66) < 1e-6 and abs(v6.baked("opacitymult") - 0.44) < 1e-6
    assert v4.baked("background") is None and abs(v4.baked("hurst") - 0.66) < 1e-6
    # `fx.header=read` is the default since the leaf-count session; the old reading is
    # the `ignore` arm, scoped by name.
    with assume.scope(**{"fx.header": "ignore"}):
        assert fx.header_fields(Context(asm, cap=64), v6) is None, "`ignore` reads nothing"
    assert fx.header_fields(Context(asm, cap=64), v6) is not None, "the default reads them"
    dead, _n = _render(asm, 9806, **{"fx.subdivide": "tree", "fx.header": "ignore", "fx.negopacity": "clip"})
    assert float(dead.max()) == 0.0, "under `ignore` + `clip` the -1 patterns clip to nothing"
    live, n = _render(
        asm,
        9806,
        **{
            "fx.subdivide": "tree",
            "fx.negopacity": "signed",
            "fx.combine": "bit18",
            "fx.header": "read",
            "fx.hurst": "exp",
        }
    )
    x = live[..., 0].astype(np.float64)
    assert n == 86 and x.shape == (64, 64), (n, x.shape)
    assert 0.35 < x.mean() < 0.65 and x.std() > 0.1 and x.max() < 1.0, (x.mean(), x.std(), x.max())
    print("ok  9806 under fx.header=read: mean %.3f sd %.3f (defaults: %.3f)" % (x.mean(), x.std(), dead.mean()))


def test_the_budget_refuses_rather_than_truncates():
    asm = _bricks()
    if asm is None:
        return _skip("no Bricks specimen")
    saved = fxtree.MAX_ROWS
    fxtree.MAX_ROWS = 64
    try:
        try:
            _render(asm, 9924, **{"fx.subdivide": "tree"})
        except fxtree.Unsupported as e:
            assert "budget" in str(e), e
        else:
            raise AssertionError("no refusal at MAX_ROWS = 64 for a 256-region leaf")
    finally:
        fxtree.MAX_ROWS = saved
    print("ok  the tree arm refuses over budget")


if __name__ == "__main__":
    for fn in (
        test_the_child_pointer_sits_before_the_bit4_word_and_after_the_bit7_word,
        test_every_bricks_tree_reads_and_the_first_walked_entry_is_a_root,
        test_rand_with_zero_salt_is_bit_identical_to_the_unsalted_hash,
        test_the_grid_drawer_is_the_per_pattern_loop,
        test_a_depth_zero_record_draws_the_same_under_both_arms,
        test_a_rand_leaf_under_five_quadrants_is_white_noise,
        test_the_budget_refuses_rather_than_truncates,
    ):
        fn()
