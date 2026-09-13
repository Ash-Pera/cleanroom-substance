#!/usr/bin/env python3
"""Checks for the chain-tree arm (`render2.fxchain`), the lazy `select` arm of the
transpiler, and the two pixel-processor arms that graph 001's flood fill needs.

    python3 -m pytest tools/render2/test_fxchain.py -q

The STRUCTURAL checks read Bricks record 10081 -- the random-size stone tiling -- and
assert the tree the words state: 25 nodes, 8 leaves, a 0x1CB with both children, six
0x89 / 0x99 switches with a false child. The SEMANTIC checks hold the tiling to its own
consistency: under `program.select=lazy` the first row's cell widths sum to the canvas
and the row height survives the row; under `eager` the same gate program clobbers it.
The DEFAULT checks hold every default arm to what it drew before: the list walk on a
record the tree arm applies to, and the tree arm equal to the list walk on one it does
not. Render checks skip loudly without the specimen.
"""

import glob
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.append(_HERE)  # see __init__.py: this package goes LAST

import assume  # noqa: E402
import fxchain  # noqa: E402
import fxrender  # noqa: E402
import fx  # noqa: E402
import model  # noqa: E402
import ops  # noqa: E402
import sbsasm  # noqa: E402
import sbsruntime  # noqa: E402
import transpile  # noqa: E402
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
TILING = 10081
NOISE = 10080
ROW_GATE = 3891180  # the per-cell gate of 10081's statistics pass


def _skip(reason):
    pytest = sys.modules.get("pytest")
    if pytest is not None:
        pytest.skip(reason)
    print("SKIP " + reason)


def _bricks():
    got = glob.glob(os.path.join(BRICKS, "*.sbsasm"))
    return sbsasm.Assembly(got[0]) if got else None


def _emit(asm, index, **arms):
    rec = asm.records[index]
    ctx = Context(asm, cap=256)
    with assume.scope(**arms):
        run = fxrender.make_runner(
            asm, rec, programs=ctx.fx_funcs, cache_funcs=ctx.cache_funcs
        )
        seeded = (
            fxchain.seed(rec, run) if fxchain.active(rec) else fxrender.seed_slots(rec, run)
        )
        return fx.emissions(rec, run, seeded, cache=ctx.cache)


def test_tiling_tree_structure():
    asm = _bricks()
    if asm is None:
        return _skip("Bricks specimen not present")
    rec = asm.records[TILING]
    nodes, leaves, why = fxchain.survey(rec)
    assert why is None
    assert len(nodes) == 25 and len(leaves) == 8
    kinds = sorted(hex(n.hdr) for n in nodes.values())
    assert kinds.count("0x1cb") == 1 and kinds.count("0x19b") == 4
    both = [n for n in nodes.values() if n.hdr == 0x1CB and n.spare]
    assert len(both) == 1
    switches = [n for n in nodes.values() if n.kind == "switch" and n.spare]
    assert len(switches) == 6  # two passes x (wide/tall, per-column, per-row)
    assert fxchain.needed(rec)
    # the two passes end on leaves of two tag families, none with Quadrant pointers
    tags = sorted({hex(t) for t, _p in leaves.values()})
    assert tags == ["0x25300758", "0x5300758", "0x55300758"]


def test_lazy_select_keeps_the_row_height():
    """The gate writes the row's height into slot 44 inside the row-start branch."""
    asm = _bricks()
    if asm is None:
        return _skip("Bricks specimen not present")
    end = asm.program_span(ROW_GATE)
    inputs = {
        966468536: np.array([[5]], np.float32),
        966474941: np.array([[6]], np.float32),
    }

    def run(arm):
        with assume.scope(**{"program.select": arm}):
            src = transpile.transpile(asm.data, ROW_GATE, end, "python", "prog")
        scope = {}
        exec(compile(src, "<t>", "exec"), scope)
        slots = {k: np.zeros(1) for k in (33, 37, 38, 39, 40, 41, 42, 43, 44)}
        widths, heights = [], []
        for n in range(5):
            sbsruntime.set_context(number=float(n))
            scope["prog"](inputs=inputs, slots=slots)
            widths.append(float(np.ravel(slots[42])[0]))
            heights.append(float(np.ravel(slots[44])[0]))
        return widths, heights

    widths, heights = run("lazy")
    assert abs(sum(widths) - 1.0) < 1e-5
    assert all(w > 0 for w in widths)
    assert len({round(h, 6) for h in heights}) == 1 and heights[0] > 0.1
    _w, eager = run("eager")
    assert len({round(h, 6) for h in eager}) > 1  # clobbered on every non-row-start cell


def test_select_guards_on_the_gate():
    asm = _bricks()
    if asm is None:
        return _skip("Bricks specimen not present")
    import disasm

    ins = list(disasm.decode(asm.data, ROW_GATE, asm.program_span(ROW_GATE)))
    guards = transpile.select_guards(ins, ins[-1][0])
    sets = {}
    for k, _a, op, toks in ins:
        if disasm.fields(op)[3] == 0x07:
            sets[toks[1]] = guards[k]
    assert sets[40] == frozenset() and sets[42] == frozenset()
    assert sets[44] and sets[38] and sets[43]
    assert all(branch for _j, branch in sets[44])


def test_tiling_emits_two_passes():
    asm = _bricks()
    if asm is None:
        return _skip("Bricks specimen not present")
    pats = _emit(asm, TILING, **{"fx.chain": "tree", "program.select": "lazy"})
    assert len(pats) == 96
    lum = [float(np.ravel(p["opacity"])[0]) for p in pats]
    assert all(v == 0.0 for v in lum[:48]) and all(v == 1.0 for v in lum[48:])
    # the draw pass sizes every stone below its cell: the statistics pass ran first
    stats = [np.ravel(p["patternsize"]) for p in pats[:48]]
    draw = [np.ravel(p["patternsize"]) for p in pats[48:]]
    assert all((d < s).all() for s, d in zip(stats, draw))
    # the list walk draws the statistics pass alone
    listed = _emit(asm, TILING)
    assert len(listed) < 20 and all(float(np.ravel(p["opacity"])[0]) == 0.0 for p in listed)


def test_default_arms_unchanged():
    asm = _bricks()
    if asm is None:
        return _skip("Bricks specimen not present")
    # a record the tree arm applies to draws what it drew under the default
    v = model.View(asm, asm.records[TILING])
    a = np.asarray(fx.render_fxmaps(Context(asm, cap=256), v))
    assert a.max() == 0.0
    # and one it does not apply to is identical under the arm
    other = next(
        r for r in asm.records if r.filter_name == "fxmaps" and not fxchain.needed(r)
        and r.index > TILING
    )
    v2 = model.View(asm, other)
    b0 = np.asarray(fx.render_fxmaps(Context(asm, cap=256), v2))
    with assume.scope(**{"fx.chain": "tree", "program.select": "lazy"}):
        b1 = np.asarray(fx.render_fxmaps(Context(asm, cap=256), v2))
    assert np.array_equal(b0, b1)


def test_pixel_rand_is_white_noise():
    asm = _bricks()
    if asm is None:
        return _skip("Bricks specimen not present")
    import filters

    v = model.View(asm, asm.records[NOISE])
    flat = np.asarray(filters.f_pixelprocessor(Context(asm, cap=256), v))
    assert flat.std() < 1e-9 and abs(flat.mean() - 0.2115) < 1e-3
    with assume.scope(**{"pixelprocessor.rand": "pixel"}):
        noise = np.asarray(filters.f_pixelprocessor(Context(asm, cap=256), v))
    assert abs(noise.mean() - 0.5) < 0.02 and abs(noise.std() - 0.289) < 0.02
    assert noise.min() >= 0.001 and noise.max() <= 1.0


def test_nearest_sampler():
    im = np.arange(16, dtype=np.float32).reshape(4, 4, 1)
    s = ops.nearest_sampler(im)
    grid = ops.pos_grid(4, 4)
    assert np.array_equal(s(grid)[:, 0], np.arange(16))
    # a quarter texel off the centre still returns that texel; a wrap goes round
    pos = np.array([[(1 + 0.75) / 4.0, (2 + 0.25) / 4.0], [-0.1, 0.1]])
    assert s(pos)[0, 0] == 9 and s(pos)[1, 0] == 3


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
