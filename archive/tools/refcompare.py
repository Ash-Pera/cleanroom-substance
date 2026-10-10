#!/usr/bin/env python3
"""Compare rendered outputs against the engine's OWN exported maps.

Every other check in this repository is a distribution match or a source containment: a
decode is believed because its numbers line up with something independently known. This
is the one place a render can be scored against ground truth, because several packages in
the corpus ship the texture maps the engine exported alongside the .sbsar that produces
them.

    python3 archive/tools/refcompare.py            # every pack that ships reference maps
    python3 archive/tools/refcompare.py Chesterfield   # substring-matched to one pack
    python3 archive/tools/refcompare.py Chesterfield --renderer render2 \
            --outputsize implied --dim 512
    python3 archive/tools/refcompare.py Chesterfield --renderer render2 \
            --outputsize implied --dim 2048 --bands       # full-res structure + spectrum

THE BARE INVOCATION IS A GUARD'S CONFIGURATION AND NOT THE RECOMMENDED READING. With no
options this renders `archive/tools/render.py` at the `$outputsize` the FILE declares and
`max_dim` 128, which is what `test_filters.REFERENCE_FLOOR` is scored from and must keep
being scored from. It is not what a reader should use to see where the renderer stands:
every reference pack here ships maps exported at an `$outputsize` its own file does not
declare (512, 1024, 2048, 2048, 2048, 4096 against a declared 256), and the renderer of
record is `render2`. Pass all three options for that. See FORMAT-NOTES.md, "The output size
the reference was exported at is a property of the SCORE, not of the render".

WHY IT WAS UNUSABLE UNTIL NOW, and what changed. `tools/assume.py` records the bind: the
reference renders could not arbitrate our guesses because our refusals to guess were what
blocked the reference renders -- 96 declared outputs across the reference specimens, 10
produced, 0 spatially varying, with `blur`'s withdrawn intensity fallback the top blocker
at 70 records. Locating blur's intensity (01dedd5) moved that to 96 declared / 17 produced,
and the comparison below runs end to end.

PAIRING IS AN EXACT LOOKUP, NOT A FILENAME GUESS. `manifest.output_names` gives each
declared output's usage -- basecolor, normal, roughness, height, metallic,
ambientocclusion -- and that is the same vocabulary the exported files are named in. Where
a package names its outputs generically (`output`, `output_1`, ... -- see
`minime453__Stylized_Sandy_Stone_Path`) nothing pairs and this reports so rather than
matching by position, which would be a guess dressed as a measurement.

NOT A FRAME MISMATCH EITHER, and for `Kutejnikov__Auras` that is the obvious first guess:
it ships 120 base-colour exports, 60 frames of an animation in two encodings, and this
compares against whichever the glob returns first. If our render corresponded to a different
frame, the shape would match and the colours would not -- which is exactly the symptom its
`basecolor` shows, correlation 0.94 with a per-channel gain of 0.536 / 0.321 / 0.802.

Scoring our render against all 120:

    best MAE     0.0802 at frame 0034, mean correlation +0.9008
    worst MAE    0.0921 at frame 0008, mean correlation +0.9257
    frame 0000, the one used   0.0879, +0.9366

The whole range is 0.080 to 0.092 and every frame correlates between 0.90 and 0.93, so the
frames barely differ and the choice does not matter. The gain error is a property of our
render, not of which export it is held against. (Note the best MAE and the best correlation
are at different frames, which is the same structure-versus-gain split the fit column
reports.)

Also checked and rejected: it is not a transfer function. The best pure gamma fits at
residual 0.031 against the linear fit's 0.032, treating our output as sRGB makes it worse
(0.145), and linearising it improves the raw number but not past the linear fit.

NOT AN ORIENTATION PROBLEM, checked rather than assumed. A systematic flip or transpose
would depress every correlation in this table while the decode underneath was correct, so
it is cheap to ask and expensive to miss. Scoring all 14 channels under identity, flip-x,
flip-y, flip-both, transpose, rot90 and rot270:

    Auras basecolor    0.9206 / 0.8499 / 0.9385   -- identical to four decimals under all seven
    Bricks emission    0.4454 / 0.4669 / 0.4629   -- identical under all seven
    Chesterfield normal, height, AO               -- every variant within 0.1 of zero

Nothing improves. The high scores are dominated by structure too coarse for orientation to
matter, and the low ones are not a misoriented right answer.

TWO TRAPS, both of which produced confident wrong readings before they were caught:

  16-BIT MAPS. AO, height, metallic and roughness export as `mode="I;16"`. `convert('L')`
  saturates them, and the first run of this comparison reported AO and height as constant
  1.0 -- i.e. it described the engine's own exports as blank placeholders. They are not:
  the Chesterfield AO map has 20,551 distinct values and its height map 31,997. Scale by
  65535, not 255, and decide by the image mode rather than by eye.

  CHANNEL AVERAGING. A normal map is mostly (0.5, 0.5, 1.0), which is nearly constant
  under a mean over channels -- so averaging destroys exactly the spatial variation being
  measured. It made a render whose per-channel std is 0.0179 look like 0.0082. Compare per
  channel. For the same reason the std of a whole 3-channel normal array (0.25 for that
  record) is inter-channel spread and not detail at all.

WHAT IT SAYS TODAY, on the one package where outputs both render and pair:

    normal ch0   ours 0.5000 / 0.0179    ref 0.5002 / 0.0968    MAE 0.0783
    normal ch1   ours 0.5000 / 0.0179    ref 0.4999 / 0.0967    MAE 0.0781
    normal ch2   ours 0.9990 / 0.0193    ref 0.9659 / 0.0233    MAE 0.0349
    metallic     ours 0.0027 / 0.0322    ref 0.0481 / 0.1733    MAE 0.0454
    height       ours 0.2503 / 0.0107    ref 0.5154 / 0.0970    MAE 0.2652
    AO           ours 0.1487 / 0.0268    ref 0.8871 / 0.0645    MAE 0.7387

The means agree to four decimal places on `normal`: the map is correctly formed and
centred on a flat normal. The spatial std is 5.4x too small, and metallic is short by the
same ratio. Tracing the 121-record cone behind that output puts the loss at the `fxmaps`
generators feeding it, which emit patterns at full brightness covering 0.4% to 11.8% of
the canvas -- the right colour and far too small. `blend`, `levels` and `dirmotionblur` in
that chain are not losing anything; the two `blendingmode=3` records downstream are
multiplying already-sparse maps together, which is what multiply does.

THAT TABLE IS THE BARE INVOCATION'S, AND IT IS NOT WHERE THE RENDERER STANDS -- it is
`render.py` at the declared `$outputsize` and `max_dim` 128, kept because
`test_filters.REFERENCE_FLOOR` is scored from exactly that. Through the renderer of record
at the corrected size, which is what `REFERENCE_FLOOR_RENDER2` guards
(`--renderer render2 --outputsize implied --dim 256`), the same package reads

    normal ch0   0.5002 / 0.1207   ref 0.5002 / 0.0968   MAE 0.0332   corr +0.9524
    normal ch1   0.5001 / 0.1204   ref 0.4999 / 0.0967   MAE 0.0333   corr +0.9496
    normal ch2   0.9607 / 0.0215   ref 0.9659 / 0.0233   MAE 0.0131   corr +0.7499
    metallic     0.0486 / 0.1727   ref 0.0481 / 0.1733   MAE 0.0010   corr +0.9999
    height       0.5815 / 0.1217   ref 0.5154 / 0.0970   MAE 0.0684   corr +0.9562
    AO           0.9839 / 0.0139   ref 0.8871 / 0.0645   MAE 0.0968   corr +0.8715
    roughness    0.1713 / 0.0207   ref 0.2352 / 0.0262   MAE 0.0639   corr +0.9358

`normal`'s std is now 25% HIGH rather than 5.4x low, `metallic` reproduces the export at
MAE 0.0010, and "the single number to move is the footprint" -- which this paragraph used
to end on -- is withdrawn: see the position/gain paragraph below and `fxrender.py`'s
negative results 5 and 6.

AND `roughness`'s 0.0639 IS ONE CONSTANT, WHICH NO COLUMN OF THIS TABLE COULD SEE UNTIL
THE `DC=` COLUMN WAS ADDED. Its MAE is 0.0639 and its DC offset -- `ours.mean() -
ref.mean()` -- is -0.0639: the two agree to four decimals (100.00% at this grid, and the
MAE that survives removing the constant is 0.0079), so essentially the whole of that
channel's error is a level shift and almost none of it is shape. Every other column
here is mean-removed by construction (`corr`, `band_power`, `structure`, and `resid`,
whose affine fit absorbs any constant), which is how a channel correlating at +0.93
against a 0.91 CORRELATION floor stayed the worst-offset channel in the table without
anyone reading it that way. The cause is located and it is upstream of the output's own
`levels`, whose four stated values this package's permitted `.sbs` reproduces bit for bit
as float32:
two `blend` records in the cone multiply by a source that renders an exactly constant 0
where the file states a noise generator, so the chain reaches the output scaled by
0.35 x 0.53 = 0.186. Substituting a mid-grey for those two sources takes the DC from
-0.0639 to -0.0016 and the fit slope from 1.183 to 1.032 TOGETHER -- the offset and the
gain are one defect and cannot be separated. See FORMAT-NOTES.md, "`roughness` is one
level shift, and it is two multiply-blends whose noise source renders constant".

THE POSITION-SIGNATURE LEAD IS WITHDRAWN -- 2026-09-04, and the numbers it rested on are
two renderers and one output size old. What it said: "after the blend-opacity fix `normal`
reads std 0.1018 against the reference's 0.0968 while its MAE ROSE, 0.0783 -> 0.1039. Right
variance and a worse error is a POSITION signature, not a size one", with
`branchoffset + frameoffset` as the candidate on their combined x-extent having median 0.835
and p90 7.8.

Through the renderer of record at the configuration `test_filters.REFERENCE_FLOOR_RENDER2`
is taken at -- render2, `$outputsize` implied, `max_dim` 256 -- the same channel reads

    normal ch0   ours 0.5002 / 0.1207   ref 0.5002 / 0.0968   MAE 0.0332   corr +0.9524
                 fit y = 0.764x + 0.118, resid 0.0229

MAE 0.0332, not 0.1039, and a correlation of +0.9524. Patterns correlating at 0.95 are not
landing in the wrong places. What is left is a GAIN error and the fit states it: our std is
1/0.764 = 1.31x the reference's, an amplitude 31% high with the structure right.

THAT GAIN IS `height`'s, NOT `normal`'s, and this paragraph used to leave the subject
unstated -- which is the shape of defect the pass one commit earlier was written to catch.
Scored in the same run, same configuration, the two channels' fits are the same fit:

    max_dim   normal ch0                    height ch0
     128      corr +0.9561  MAE 0.0352  y=0.741x    corr +0.9566  MAE 0.0610  y=0.718x
     256      corr +0.9524  MAE 0.0332  y=0.764x    corr +0.9562  MAE 0.0684  y=0.762x
     512      corr +0.9510  MAE 0.0312  y=0.786x    corr +0.9561  MAE 0.0737  y=0.794x
    1024      corr +0.9506  MAE 0.0305  y=0.796x    corr +0.9560  MAE 0.0756  y=0.804x
    2048      corr +0.9504  MAE 0.0297  y=0.807x    corr +0.9560  MAE 0.0774  y=0.814x

Five rungs, agreeing to 3.2% / 0.3% / 1.0% / 1.0% / 0.9%. 2048 is the last one there is --
it is both the record's own size at `$outputsize` 11 and the export's -- and the slope gets
to 0.807, not to 1.0, at 92 seconds for the run. `ChesterfieldSofa`'s `normal` (record 121)
and its `height` (record 120) both read record 119, and record 120 is a `levels` with a baked
out-range of [0.25, 0.75] -- one linear gain of exactly 0.5 -- so a shared amplitude error in
119 arrives at both outputs at the same size. On `Kutejnikov__Bricks_and_tiles` the SIGN
flips and they still track: normal y=1.361x against height y=1.292x at max_dim 256. A fixed
31% error in `f_normal` cannot be 31% high on one package and 29% low on another.

The 0.764 is also not an artifact of scoring on a 64px grid, which was the obvious first
guess given the export is 2048. `resample` puts BOTH sides on `SIZE`, so the comparison is
symmetric; and crossing `max_dim` against `SIZE` shows `height`'s slope is INVARIANT to the
scoring grid -- 0.758 at every grid from 128 to 2048 at max_dim 256 -- while `normal`'s moves
the wrong way for that hypothesis, 0.764 at grid 64 down to 0.724 at grid 2048. Averaging the
reference down was making our overshoot look smaller, not larger. See FORMAT-NOTES.md,
"`normal`'s 31% gain error is `height`'s".

The p90 statistic itself reproduces -- 7.964 over 39,513 records at HEAD against the 7.8
recorded -- but conditioning it on what the record draws reverses its sign:

                 n        x-extent median   p90    records placing a centre outside the cell
    flat     21,731            0.0444      0.573                15.0%
    picture  17,774            0.4055     19.249                54.4%

A wild offset is the signature of a record that DOES produce a picture, which is what a
scatter generator's offsets have to look like; under unit-spacing tiling an offset of 8
wraps. The records that render flat are the ones whose patterns barely move. So the two
signals are a second thing rather than the same thing seen downstream, and the second thing
is not the one this paragraph named. See FORMAT-NOTES.md, "`patternsize`'s setup chain was
never out of order".

PROVENANCE. The exported maps are distribution data published by the material's own
author, on the same footing as the .sbsar beside them -- the standing exclusion is of
Adobe's engine and of Adobe's bundled .sbs sources, neither of which is involved in
reading a PNG somebody published with their material.
"""

import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _repo_root  # noqa: E402

_repo_root.add_tools_to_path()
import manifest  # noqa: E402
import render  # noqa: E402
import sbsasm  # noqa: E402

ROOT = _repo_root.ROOT
PACKS = os.path.join(_repo_root.SPECIMENS, "new_opengameart")
#: The score grid. `refguard.SCORE_GRID` is the same constant under the guard's own name and
#: the two are asserted equal below, because `resample`'s default moved with the function
#: and a reader changing one of them would silently leave the other behind.
SIZE = 64

# THE GRID WE RENDER ON IS NOT THE GRID WE COMPARE ON, and conflating them was costing more
# than any decode question settled this week. `SIZE` is the resolution both arrays are
# resampled to before scoring; `RENDER_DIM` is the `max_dim` the renderer actually evaluates
# at. They were one constant, so every score this project has reported was measured on a
# 64x64 render.
#
# WHY THAT IS NOT NEUTRAL. `distance.scale_radius`'s own docstring warns about it for `blur`:
# a parameter in PIXELS at a 256 reference shrinks with the grid, and below a pixel the
# filter is a no-op that reads as a dead parameter. On Bricks Textures_1's 126 `distance`
# records the radii run 0.69 to 256 px with a median of 3.25, and the fraction that survive:
#
#     max_dim  64    median scaled radius 0.81 px    >=1px on  43/126    >=2px on  16/126
#     max_dim 128    median               1.63 px    >=1px on 108/126    >=2px on  43/126
#     max_dim 256    median               3.25 px    >=1px on 121/126    >=2px on 108/126
#
# So at 64 the filter is off on most records, and every arbitration that touches it has been
# decided with it off.
#
# MEASURED, AND THE TWO EFFECTS SEPARATE CLEANLY. Bricks, `distance.param` crossed with the
# render grid -- 'wide' resolves 126 records to 2 distinct radii, 'layout' to 22, so the
# 'wide' row is the control in which the filter stays inert:
#
#                 max_dim 64     max_dim 128     resolution gain
#     wide          0.1385         0.1275           -0.0110
#     layout        0.1370         0.1223           -0.0147
#     layout's edge  0.0015         0.0052
#
# Both effects are real and they are different sizes. There is a general gain of about 0.011
# present even with the filter inert -- a finer render antialiases better under the common
# downsample -- and on top of it the candidate's own advantage more than TRIPLES once its
# radii are resolvable. A 64px harness does not merely add noise: it systematically
# understates any candidate that moves a pixel-scale parameter.
#
# IT SATURATES AT 128, which is what says this is resolution and not a coincidence: Bricks
# scores 0.1223 at 128 and 0.1226 at 256. Once the render is finer than the 64px comparison
# grid by a factor of two there is nothing further to resolve, so 128 is the whole gain at a
# quarter of 256's cost.
#
# ACROSS EVERY REFERENCE PACKAGE, same scope, same 112 channels, same 16 unrendered:
#
#     max_dim  64    0.1270          71 channels better at 128
#     max_dim 128    0.1121          21 worse, 20 unchanged
#
# The gains concentrate where a mechanism predicts them. `normal` is a height GRADIENT, and
# a gradient sampled at 64 on a map authored for 1024 is badly undersampled -- its channels
# move -0.05 each, and `basecolor` ch2 by up to -0.10. The 21 regressions are mostly small;
# the real ones are four `roughness` channels at +0.068, +0.067, +0.020, +0.020, and they are
# recorded here rather than averaged away.
#
# THE COST IS WHY THIS IS A CONSTANT AND NOT A FIXED CHOICE. This module's docstring calls
# max_dim "the difference between minutes and seconds per file", and that is still true --
# 128 is roughly four times 64's work. A caller sweeping many candidates can pass a smaller
# `max_dim` to `compare_pack`; it should then not read small margins as arbitrations.
RENDER_DIM = 128


def load_reference(path):
    """A reference map as float in [0, 1], (H, W, C) -- by IMAGE MODE, not by guess."""
    from PIL import Image

    im = Image.open(path)
    a = np.asarray(im).astype(np.float64)
    a = a / (65535.0 if (im.mode == "I;16" or a.max() > 255) else 255.0)
    return a[:, :, :3] if a.ndim == 3 else a[:, :, None]


# THE MEASUREMENT SCALES MOVED TO `refguard.py` AND ARE IMPORTED BACK, so that there is
# exactly one implementation of each and every existing caller keeps the name it used.
# `resample`, `structure`, `band_power`, `_structure_grid`, `LOW_GRID` and `BANDS` were
# defined here and are now defined there, verbatim and with their docstrings. The reason is
# `tools/render2/test_render2.py`: the reference guard is shared by three tables in two
# files, one of which is inside `tools/render2/` and must not import a renderer to score
# itself. `refguard` imports numpy and PIL and nothing else in this tree.
#
# `corpus.py`'s argument, one level up: a correction written into one implementation does
# not propagate to a second, and this module and that guard were about to have two copies
# of the same spectrum.
from refguard import (
    BANDS,
    LOW_GRID,
    band_power,  # noqa: F401  (re-exported)
    resample,
    structure,
)
from refguard import structure_grid as _structure_grid  # noqa: F401
import refguard  # noqa: E402

assert refguard.SCORE_GRID == SIZE, (
    "the score grid has two names and they have parted: refcompare.SIZE=%r, "
    "refguard.SCORE_GRID=%r -- `resample`'s default follows the second"
    % (SIZE, refguard.SCORE_GRID)
)


#: A declared channel and the token an exporter abbreviates it to in a filename.
CHANNEL_ABBREVIATIONS = {"ambientocclusion": "ao"}


def _key(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def reference_packs(match=None):
    """Packages that ship exported maps, as {name: [png paths]}."""
    out = {}
    for png in glob.glob(
        os.path.join(PACKS, "*", "reference_renders", "**", "*.png"), recursive=True
    ):
        pack = os.path.relpath(png, PACKS).split(os.sep)[0]
        out.setdefault(pack, []).append(png)
    if match:
        # Match the PACK NAME or any of its file names. A package directory is named for
        # its author (`Kutejnikov__Stylized_Wooden_Roof_Tiles`) while the material is
        # called RoofTiles everywhere else, so filtering on the directory alone silently
        # returns nothing for the name a caller actually has in hand.
        m = match.lower()
        out = {
            k: v
            for k, v in out.items()
            if m in k.lower() or any(m in os.path.basename(p).lower() for p in v)
        }
    return out


def graph_dir(asm, uid):
    """The directory a graph's exports live in, from its manifest `pkgurl`.

    ONE .sbsar CAN HOLD SEVERAL GRAPHS, AND THEIR EXPORTS DO NOT SHARE A NAMESPACE.
    `Kutejnikov__Auras` declares four -- `pkg://001` to `pkg://004`, one output each -- and
    ships `reference_renders/001/` ... `004/` to match. Pairing on the output NAME alone
    cannot tell them apart: all four outputs are called `basecolor`, so all four scored
    against whichever map the glob happened to return first, and three of the four scores
    were a comparison against another graph's picture.

    The manifest names the graph that declares each output, and the exporter named the
    directories after the same graphs, so this is a lookup on both sides.
    """
    for g in manifest.graphs(asm):
        if uid in g["outputs"] and g.get("pkgurl"):
            return g["pkgurl"].rstrip("/").rsplit("/", 1)[-1] or None
    return None


def implied_outputsize(refs):
    """The `$outputsize` a set of exported maps implies -- `render2.engine`'s, not a copy.

    ONE IMPLEMENTATION, and it lives next to `declared_outputsize` and `record_sizes`
    because it is the same question asked of the other side of the pair. The rule started
    life THREE times over -- inline in `render2/__main__._outputsize_warning`, again here,
    and a third time in a probe -- and two of the three read only `size[0]` and took the
    max on disagreement. `corpus.py`'s argument applies verbatim: a correction written
    into one implementation does not propagate to a second.
    """
    import render2  # noqa: F401
    from engine import implied_outputsize as _impl

    return _impl(refs)


def _sizes_at(asm, outputsize):
    """`{record: (W, H)}` at `outputsize`, or None -- `render2.engine.record_sizes`.

    IMPORTED HERE AND NOT AT MODULE SCOPE so that the default path of this module imports
    nothing it did not import before. `outputsize=None` is the whole of the old behaviour
    and must stay measurably identical to it, which an import at the top would leave true
    but no longer obvious.

    NO SIZE MODEL IS DUPLICATED INTO THIS DIRECTORY. `render.py`'s independence from
    `render2` is an independence of FILTER implementations -- which is what this module
    scores -- and `record_sizes` is a decode: a slot the walk names, a program at it, and
    the check that the program reproduces the tag at the declared size. Writing a second
    one here would give two answers to a question the file has one answer to.
    """
    if outputsize is None:
        return None
    import render2  # noqa: F401
    from engine import record_sizes

    return record_sizes(asm, outputsize)


def _renderer(which):
    """`render.py`'s pass or `render2`'s, as one callable `(asm, max_dim, sizes) -> dict`.

    ONE PAIRING, TWO RENDERERS. Everything in this module apart from the single
    `render.render` call is PAIRING -- `graph_dir`, `_package_refs`, the identifier-then-
    channel fallback, the 16-bit load, the per-channel resample. All of it was written
    against faults that cost sessions (a graph scored against its sibling's picture, a
    package scored against another package's material, `convert('L')` saturating a 16-bit
    map), and `render2`'s own `--score` reimplements NONE of it: it globs `*.png`, keys on
    the last underscore-separated token, and keeps the first hit per key. On a
    single-graph pack the two agree; on `Kutejnikov__Bricks_and_tiles`, which declares
    five graphs and flattens their exports into one directory, `--score` reports 48 rows
    against the 12 distinct channels this narrowing leaves, and its `basecolor` rows run
    from -0.06 to +0.05 because glob order decides which graph's map each output meets.

    So a `render2` floor cannot be taken from `--score` and must come through here. The
    argument is the same one `corpus.py` makes about corpus lists: a correction written
    into one implementation does not propagate to a second.
    """
    if which == "render2":
        # THROUGH THE PACKAGE, NOT BY PATH. A first attempt inserted `tools/render2` on
        # `sys.path`, imported `engine`, and popped the path again to avoid shadowing
        # `model`/`ops`/`filters` for everyone else. It imported fine and then rendered 60
        # of ChesterfieldSofa's 881 records instead of 881, silently: the modules that
        # `engine` imports lazily could no longer be found, and every record that reached
        # one failed as an ordinary unsupported record. `render2/__init__.py` already does
        # this properly -- it puts `tools` FIRST and its own directory LAST, and then
        # asserts that each name resolved inside the package -- so importing the package
        # is both the supported entry point and the one that fails loudly.
        import render2 as _r2

        # `render2` takes an `$outputsize` and derives the sizes itself, so handing it a
        # `sizes` dict as well would run `record_sizes` twice and let the two answers
        # drift. It takes the OUTPUT SIZE; `render.py` takes the sizes.
        def go(asm, max_dim, sizes, _os=None, inputs=None):
            outs, _f, _i = _r2.render(
                asm, verbose=False, max_dim=max_dim, outputsize=_os, inputs=inputs
            )
            return outs

        go.wants_outputsize = True
        go.takes_inputs = True
        return go

    if which == "render2-lean":
        return _lean_renderer()
    if isinstance(which, tuple) and which and which[0] == "render2-lean":
        # ("render2-lean", extra_keep): a caller that needs an INTERMEDIATE alive -- the
        # companion instrument reads a tone-mask record that is not a declared output and
        # would otherwise be freed under it. Naming them is the caller's job for the same
        # reason the liveness list is: this module cannot know which intermediates a
        # measurement wants.
        return _lean_renderer(which[1])

    def go(asm, max_dim, sizes, _os=None, inputs=None):
        produced, _failures, _synth = render.render(
            asm, verbose=False, max_dim=max_dim, sizes=sizes
        )
        return produced

    go.wants_outputsize = False
    go.takes_inputs = False
    return go


def _lean_renderer(extra_keep=()):
    """`render2`, one whole-file pass, with dead intermediates FREED as it goes.

    WHY NOT A PER-OUTPUT CONE, which is the obvious way to make a native-size render fit.
    It is unsound, and the file says so: the 0x03/0x06 value cache is cross-record common
    -subexpression elimination, so a record inside an output's edge closure can read a
    cache index that a record OUTSIDE it wrote. Skipping the writers costs Auras' graph
    004 its whole basecolor cone -- `NoSharedCache: cache index 5 read before anything
    wrote it` at record 408, cascading to the output -- while Bricks 005's roughness cone
    happens to contain its own writers and comes out identical. A cone is therefore an
    optimisation that is correct on the specimens where it is tested and wrong elsewhere,
    which is the worst shape a measurement tool can have.

    So every record is evaluated, in order, exactly as `engine.render` always did, and the
    only thing that changes is that an array nothing further reads is dropped. Bricks at
    `$outputsize` 1024 holds 112 GB of record arrays if none ever is; the peak LIVE set is
    3.5 GB. Chesterfield at 2048 is 58 GB against a 13.1 GB peak.

    WHAT IS NEVER FREED, and both are structural rather than cautious: the declared
    OUTPUTS, which are the answer, and every `bitmap` record, because `sampler_bindings`
    reaches a graph image input that no edge points at and `filters.py:396` and
    `fx.py:1229` then index `ctx.outputs` with it. Liveness over `View.inputs` alone would
    free those and the failure would be silent. The VALUE cache is `ctx.cache`, a separate
    dict this does not touch.

    A record whose `View` raises is treated as reading nothing, which is not an
    approximation: `engine.render` builds the View inside its `try`, so such a record is
    refused before it samples anything.

    WHY IT EXISTS. `GUARD_GRIDS` used to be `max_dim` values, and `max_dim` CLAMPS each
    record independently (`model.View.size`) while a record's `$size` programs read its
    declared size -- so a 1024-canvas graph drawn into a 256 buffer computes its pixel
    parameters 4x over-scale and renders a DIFFERENT PICTURE, not a coarser one. The
    honest reading renders at the size the exports were made at and resamples down to
    score. See FORMAT-NOTES.md, "the `pergraph` blocker was an artefact of `max_dim`".
    `test_filters.test_render2_lean_renderer_matches_the_whole_file_render` is the A/B that
    holds this to being a memory policy and nothing else: every declared output of a
    single-graph pack and a package, bit-identical against the ordinary whole-file render.
    Verified beyond the test on `Kutejnikov__Bricks_and_tiles` as well -- 31 outputs, 12,585
    records reduced to 31 held -- which is kept out of the suite only for its runtime.
    """
    from render2 import engine as _engine, model as _model

    def go(asm, max_dim, sizes, _os=None, inputs=None):
        _sizes = _engine.record_sizes(asm, _os) or {}
        views = {}
        for r in asm.records:
            try:
                views[r.index] = _model.View(asm, r, size=_sizes.get(r.index))
            except Exception:
                views[r.index] = None
        keep = set(ri for _u, _f, _g, ri in asm.outputs())
        keep |= set(r.index for r in asm.records if r.filter_name == "bitmap")
        keep |= set(extra_keep or ())
        last = {}
        for i in sorted(views):
            v = views[i]
            for j in (v.inputs if v is not None else ()) or ():
                if isinstance(j, int) and j in views and j not in keep:
                    last[j] = max(last.get(j, -1), i)
        drop = {}
        for j, k in last.items():
            drop.setdefault(k, []).append(j)
        outs, _f, _i = _engine.render(
            asm,
            verbose=False,
            max_dim=max_dim,
            outputsize=_os,
            inputs=inputs,
            drop_after=drop,
            sizes=_sizes,
        )
        return outs

    go.wants_outputsize = True
    go.takes_inputs = True
    return go


def compare_pack(
    pack, refs, max_dim=RENDER_DIM, outputsize=None, renderer="render", grid=SIZE, qualify_graph=False
):
    """Yield (output name, channel, ours, reference) arrays for every paired output.

    `outputsize` is `(log2 w, log2 h)`, or the string `'implied'` for whatever this
    pack's own exported maps were produced at. None -- the default -- renders every record
    at its tag, which is the graph at the `$outputsize` the manifest declares.

    `renderer` is `'render'` (the default, `archive/tools/render.py`) or `'render2'`.

    `grid` is the square both sides are resampled to before they are yielded; `None`
    yields them NATIVE, which is what a full-resolution question needs. The default is
    `SIZE` = 64 and is the guard's, so passing nothing changes nothing. A caller asking
    for native arrays owns the comparison grid and must put both sides on ONE of them --
    `_structure_grid` -- because half the quantities worth measuring at full resolution
    are per-pixel and a 512-px render against a 2048-px export compares two rulers.
    THE DEFAULTS OF THIS FUNCTION ARE A GUARD'S CONFIGURATION AND NOT A RECOMMENDATION:
    they are what `test_filters.REFERENCE_FLOOR` was taken at and must keep being taken
    at. What a reader scoring a render today should pass is `renderer='render2'`,
    `outputsize='implied'` and the largest `max_dim` they can afford -- see
    `REFERENCE_FLOOR_RENDER2` and FORMAT-NOTES.md, "The output size the reference was
    exported at is a property of the SCORE".
    """
    asms = glob.glob(os.path.join(PACKS, pack, "**", "*.sbsasm"), recursive=True)
    if not asms:
        return
    for _asm_path in sorted(asms):
        if _excluded_export(pack, _asm_path):
            continue
        for _prefix, _inputs in EXPORT_SETS.get(pack, ((None, None),)):
            _refs = refs
            if _prefix is not None:
                _refs = [r for r in refs if os.path.basename(r).startswith(_prefix + "_")]
                if not _refs:
                    continue
            for _row in _compare_one(_asm_path, _refs, max_dim, outputsize, renderer,
                                     grid, qualify_graph, _inputs, _prefix):
                yield _row


#: Export sets a package ships from ONE .sbsar under DIFFERENT GRAPH INPUTS, keyed by the
#: filename prefix the exporter gave each set, with the inputs that set was made with.
#:
#: `minime453__Stylized_Sandy_Stone_Path` ships `SandyStoneRoad01_*` and `SandyStoneRoad02_*`
#: from a single graph, `StylizedCobblestoneStreet`. The graph's height, colour and roughness
#: all pass through record 55, a `switch` whose selector is `select(inputs[89582107], 1, 0)`
#: -- `Use_Random_Tiles`, a toggle the manifest declares 0 -- between 27, a 5 x 5 square-tile
#: grid, and 54, the outlines of a jittered Voronoi scatter. `SandyStoneRoad02_BaseColor`
#: is a 5 x 5 square grid under a sand overlay; `SandyStoneRoad01_BaseColor` is the Voronoi.
#: So 02 is the graph at its declared inputs and 01 is the graph with the toggle on: the
#: correspondence is read from the switch's two branches and the two pictures, the way the
#: Bricks numbering is read from the manifest, and not chosen by which our render resembles.
#:
#: WHAT THIS REPLACES. Both sets share every channel name, so `paired[0]` was glob order:
#: roughness, AO and metallic met 02's maps and height, normal and basecolor met 01's --
#: one render scored against two settings of one input, and the three rows against 01
#: measure a scatter jittered on a `$randomseed` the pack does not record (corr within
#: +/-0.17 at 128 under the toggle, both ways). With the sets separated, the declared
#: render against 02 reads +0.36 / +0.32 / +0.27 basecolor, +0.45 / +0.47 / +0.38 normal,
#: +0.36 roughness and +0.20 height at 128 -- the first rows of this pack that measure the
#: renderer rather than the seed.
#:
#: A set's inputs are applied by `_compare_one` through the renderer (render2 only; the old
#: `render.py` takes no graph inputs and keeps scoring the declared render against every
#: set it can pair). Rows are qualified `<prefix>/<name>` so the two sets cannot collide in
#: a guard table. A package absent from this table pairs as before.
EXPORT_SETS = {
    "minime453__Stylized_Sandy_Stone_Path": (
        ("SandyStoneRoad02", {}),
        ("SandyStoneRoad01", {89582107: (1,)}),
    ),
}


#: Export sets that CANNOT be scored, and why -- checked, not assumed. An entry here is a
#: directory whose maps were produced from inputs the package does not record, so no correct
#: renderer can reproduce them and agreement with them is not evidence about a renderer.
#:
#: `Kutejnikov__Bricks_and_tiles` ships x_Bricks_Textures_1 and x_Bricks_Textures_2. Their
#: .sbsasm, their .xml manifest and all five icons are BYTE-IDENTICAL -- compared by hash,
#: every file in both packages matches -- and the manifest declares `$randomseed` type="4"
#: default="0" on all five graphs. The exports differ anyway, and per channel Textures_1
#: against Textures_2 correlates +0.02..+0.14 on the three randomised graphs while reaching
#: +0.79..+0.97 on the two deterministic ones, which is the signature of a seed chosen at
#: export time and written down nowhere. Scoring our render against it measures the seed.
#:
#: THIS IS A SCORING EXCLUSION AND NOT A PROVENANCE ONE. The maps are legitimate and stay in
#: the corpus; `reference_packs` still returns them and a reader may still look at them.
UNSCORED_EXPORTS = frozenset({
    ("Kutejnikov__Bricks_and_tiles", "Textures_2"),
})


def _excluded_export(pack, asm_path):
    """True where `asm_path`'s own export set is in `UNSCORED_EXPORTS`.

    Matched on the assembly's `x_<package>_<name>` directory, the same correspondence
    `_package_refs` reads, so the two cannot disagree about which set an assembly belongs to.
    """
    parts = os.path.normpath(asm_path).split(os.sep)
    own = next((c for c in parts if c.startswith("x_")), None)
    if not own:
        return False
    return any(p == pack and own.lower().endswith(n.lower())
               for p, n in UNSCORED_EXPORTS)


def _package_refs(asm_path, refs):
    """The subset of `refs` exported from the SAME .sbsar as `asm_path`.

    ONE PACKAGE DIRECTORY CAN HOLD SEVERAL .sbsar, AND THEY ARE DIFFERENT MATERIALS.
    `Kutejnikov__Bricks_and_tiles` ships x_Bricks_Textures_1 and x_Bricks_Textures_2 and
    exports `reference_renders/Textures_1/` and `Textures_2/` to match. Pooling every PNG
    in the package and taking the first name match scored Textures_1's render against
    Textures_2's map -- a different material, not a different preset. Their roughness
    exports differ by 0.12 in mean, which is two orders of magnitude larger than the
    margins the fx arms are decided on.

    The correspondence is read from the layout, not guessed: the extracted directory is
    `x_<package>_<name>` and the export directory is `<name>`, so a reference directory
    whose name is a SUFFIX of the assembly's own `x_` directory belongs to that assembly.
    Applied only where such a directory exists, for the same reason `graph_dir` is: most
    packages ship one .sbsar and put its maps straight in `reference_renders/`, and
    narrowing there would discard all of them.
    """
    parts = os.path.normpath(asm_path).split(os.sep)
    own = next((c for c in parts if c.startswith("x_")), None)
    if not own:
        return refs
    scoped = [
        r
        for r in refs
        if any(
            c and not c.startswith("x_") and own.lower().endswith(c.lower())
            for c in os.path.normpath(r).split(os.sep)[:-1]
        )
    ]
    return scoped if scoped else refs


def _compare_one(
    asm_path, refs, max_dim, outputsize=None, renderer="render", grid=SIZE,
    qualify_graph=False, inputs=None, set_prefix=None
):
    asm = sbsasm.Assembly(asm_path)
    refs = _package_refs(asm_path, refs)
    names = manifest.output_names(asm)
    want = implied_outputsize(refs) if outputsize == "implied" else outputsize
    run = _renderer(renderer)
    if inputs and not run.takes_inputs:
        # `render.py` cannot render this set's inputs; scoring its declared render against
        # the set would be the glob-order mixture `EXPORT_SETS` exists to end.
        return
    produced = run(
        asm,
        max_dim,
        None if run.wants_outputsize else _sizes_at(asm, want),
        want if run.wants_outputsize else None,
        **({"inputs": inputs} if run.takes_inputs else {}),
    )
    for uid, _fmt, _gray, rec in asm.outputs():
        name = names.get(uid) or "?"
        pool = refs
        gdir = graph_dir(asm, uid)
        # A GRAPH'S EXPORTS CAN BE MARKED BY A FILENAME PREFIX INSTEAD OF A DIRECTORY, and
        # missing that was costing more than the sibling-package bug it sits next to.
        # `Kutejnikov__Auras` sorts four graphs into `reference_renders/001/` ... `004/`;
        # `Kutejnikov__Bricks_and_tiles` declares FIVE graphs and flattens their exports
        # into one directory as `001_roughness.png` ... `005_roughness.png`. Same numbering,
        # same meaning, and only the nested form was recognised -- so all five of Bricks'
        # graphs pooled together and glob order decided which graph's map each output was
        # graded against. Its `normal` output is graph 004 and was being scored against
        # 001's or 002's picture.
        #
        # The prefix is the graph's own pkgurl tail, the same string the directory form
        # uses, so this recognises a second spelling of one convention rather than
        # introducing a rule.
        #
        # THE NUMBERING WAS ASSERTED STRUCTURALLY AND THEN TESTED, because "both numberings
        # come from the manifest graph order" is an assumption and it could be off by one,
        # reversed, or unrelated. Correlating each rendered output against ALL FIVE numbered
        # references is a falsification test rather than a fit: the pairing is derived from
        # the manifest, and correlation only asks whether the derived partner wins.
        #
        #     graph 002   normal +0.630  roughness +0.898  height +0.626  AO +0.892
        #                 runner-up (003) at +0.448 / +0.642 / +0.535 / +0.611
        #     graph 004   normal, roughness, AO, emission all pick 004
        #     graph 005   normal, roughness, AO all pick 005
        #
        # Graph 002 decides it: all four outputs pick their own number, with a 0.25-0.28
        # margin over the nearest rival. That could have come out otherwise and did not.
        # 11 outputs confirm, 6 contradict.
        #
        # ALL SIX CONTRADICTIONS ARE IN THE REGIME WHERE THE TEST CANNOT SPEAK. Four are
        # graph 003, whose every correlation against every reference is inside +/-0.06 --
        # our render of that graph is uncorrelated with all five, so its argmax is noise,
        # not a competing alignment. The other two are `height`, our worst channel, picking
        # 001 at +0.115 over its own at -0.049. Where our render carries real signal the
        # numbering agrees; where it does not, the test returns noise, which is the expected
        # shape of a passing test on a partly-broken renderer rather than a failing one.
        #
        # GRAPH 003 IS A LOCATED FAULT AND GRAPH 002 IS ITS CONTROL. The test found it by
        # accident and no MAE would have: a wrong-but-plausible picture scores as mediocre,
        # not as broken. Rendered under identical scopes, in one pass, from one file:
        #
        #     002   normal +0.571  roughness +0.891  height +0.587  AO +0.895
        #     003   normal -0.019  roughness +0.016  height -0.101  AO -0.004
        #
        # 003 is not randomly wrong, it is FLAT -- height std 0.0037 at mean 0.875, and
        # normal at mean exactly 0.7500 / std 0.2500, a perfectly flat tangent normal with
        # an opaque alpha. Its height cone is 67% constant records against 002's 51%, with
        # the same root census in both (flat fxmaps leaves, blends flattening a live input).
        # Same failure family as the missing-lattice chain in render.py's warp note.
        #
        # THE SCOPES ARE NOT THE CAUSE, which had to be checked because these outputs are
        # only reachable with blur.intensity='program' AND distance.param='wide' both open:
        # with neither, or either alone, nothing here renders but a flat metallic, so there
        # is no unscoped baseline to compare against. The control is internal instead -- 002
        # and 003 render in ONE pass under ONE scope, and a scope held constant across both
        # cannot explain a difference between them.
        if gdir:
            _pre = [r for r in refs if os.path.basename(r).startswith(gdir + "_")]
            if _pre and any(
                os.path.basename(r).startswith((graph_dir(asm, u) or "\0") + "_")
                for u, _f, _g, _rc in asm.outputs()
                for r in refs
            ):
                pool = _pre
        if (
            gdir
            and pool is refs
            and any(
                ("%s%s%s" % (os.sep, graph_dir(asm, u) or "\0", os.sep)) in r
                for u, _f, _g, _rc in asm.outputs()
                for r in refs
            )
        ):
            # ONLY WHERE THE PACKAGE SORTS ITS EXPORTS BY GRAPH. Most ship one graph and
            # put its maps straight in `reference_renders/`, and narrowing there would
            # discard every one of them. Where the directories DO exist, an empty result is
            # the answer: that graph exported nothing, and borrowing a sibling's map would
            # manufacture a score rather than find one.
            own = [r for r in refs if ("%s%s%s" % (os.sep, gdir, os.sep)) in r]
            pool = own
        paired = [
            r for r in pool if _key(name) and _key(name) in _key(os.path.basename(r))
        ]
        if not paired:
            # THE IDENTIFIER FIRST, THEN THE DECLARED CHANNEL. An output's identifier is its
            # own name and is usually what its exported map is called too, which is why
            # matching on it alone worked everywhere it was tried. It is not required to be
            # either. StylizedCobblestoneStreet names its six outputs `output`, `output_1`
            # ... `output_5`, and the same manifest declares them as baseColor, normal,
            # roughness, ambientOcclusion, height and metallic. On identifiers that package
            # pairs 0 of its 12 exported maps; on channels it pairs all six outputs, so a
            # whole package sat unscoreable for want of this fallback.
            #
            # THE IDENTIFIER KEEPS PRIORITY and this only runs when it matched nothing, so
            # no pairing that already works can change. It is also read from the manifest
            # rather than chosen by fit: picking whichever reference our own render happens
            # to resemble would guarantee a good score and measure nothing.
            _ch = manifest.output_channels(asm).get(uid)
            if _ch:
                paired = [
                    r
                    for r in pool
                    if _key(_ch) and _key(_ch) in _key(os.path.basename(r))
                ]
                if not paired and _key(_ch) in CHANNEL_ABBREVIATIONS:
                    # THE EXPORTER'S ABBREVIATION, as a whole token only: `_AO.png` is
                    # `ambientocclusion` (SandyStoneRoad01_AO), and a substring test on
                    # two letters would pair it with anything.
                    _ab = CHANNEL_ABBREVIATIONS[_key(_ch)]
                    paired = [
                        r
                        for r in pool
                        if os.path.splitext(os.path.basename(r))[0].lower()
                        .split("_")[-1] == _ab
                    ]
                if paired:
                    name = _ch
        # ONE KEY PER GRAPH, when the caller asks. A multi-graph pack yields the same
        # (name, channel) once per graph, and a caller keyed on that alone keeps whichever
        # arrives last -- which for Bricks was graph 005 of one package, so five graphs were
        # guarded by one. Qualified, each graph is its own row and none can hide another.
        if qualify_graph and gdir:
            name = "%s/%s" % (gdir, name)
        if set_prefix:
            name = "%s/%s" % (set_prefix, name)
        if rec not in produced or not paired:
            yield (
                name,
                None,
                None,
                ("not rendered" if rec not in produced else "no matching reference"),
            )
            continue
        ours = np.asarray(produced[rec], dtype=np.float64)
        ref = load_reference(paired[0])
        if grid:
            ours, ref = resample(ours, grid), resample(ref, grid)
        elif ours.ndim == 2:
            ours = ours[:, :, None]
        for c in range(min(ours.shape[2], ref.shape[2])):
            yield name, c, ours[:, :, c], ref[:, :, c]


def main(argv):
    """CLI.

        python3 archive/tools/refcompare.py [pack] [--outputsize implied|declared|N]
                                            [--renderer render|render2] [--dim N]
                                            [--structure [--bands] [--grid N]]

    `--structure` adds the two-sided STRUCTURE RATIO -- see `structure()` -- computed at
    full resolution on the smaller of the two native grids, beside the same scalar columns
    the bare table prints. The scalars are unaffected by it: they are still taken at
    `SIZE` = 64. Use it for a question a scalar cannot answer, the pattern profile being
    the one it was written for.

    THE BARE INVOCATION IS THE GUARD'S CONFIGURATION, not the recommended one, so that
    `refcompare.py` with no arguments keeps printing the table `test_filters
    .REFERENCE_FLOOR` is scored from. For a reading of where the renderer actually stands,
    pass `--renderer render2 --outputsize implied --dim 512` or larger.
    """
    args = [a for a in argv[1:] if not a.startswith("--")]
    opts = dict(
        a[2:].split("=", 1) if "=" in a else (a[2:], "")
        for a in argv[1:]
        if a.startswith("--")
    )
    # Also accept the space-separated spelling, which is what anyone types first.
    rest = list(argv[1:])
    while rest:
        a = rest.pop(0)
        if (
            a.startswith("--")
            and "=" not in a
            and rest
            and not rest[0].startswith("--")
        ):
            opts[a[2:]] = rest.pop(0)
            if opts[a[2:]] in args:
                args.remove(opts[a[2:]])
    match = args[0] if args else None
    osz = opts.get("outputsize") or None
    if osz not in (None, "implied", "declared"):
        osz = (int(osz), int(osz))
    elif osz == "declared":
        osz = None
    renderer = opts.get("renderer") or "render"
    dim = int(opts.get("dim") or RENDER_DIM)
    want_bands = "bands" in opts
    want_structure = "structure" in opts or want_bands
    sgrid = int(opts["grid"]) if opts.get("grid") else None
    packs = reference_packs(match)
    if not packs:
        print("no packages with reference maps found under %s" % PACKS)
        return 0
    for pack, refs in sorted(packs.items()):
        print(
            "\n=== %s   (%d exported maps)   renderer %s, $outputsize %s, max_dim %d"
            % (
                pack,
                len(refs),
                renderer,
                (implied_outputsize(refs) if osz == "implied" else osz) or "declared",
                dim,
            )
        )
        print(
            "   %-12s %-3s %-21s %-21s %-7s %s"
            % (
                "output",
                "ch",
                "ours mean/std",
                "reference mean/std",
                "MAE",
                "DC = ours mean - ref mean",
            )
        )
        for name, chan, ours, ref in compare_pack(
            pack,
            refs,
            max_dim=dim,
            outputsize=osz,
            renderer=renderer,
            grid=None if want_structure else SIZE,
        ):
            if chan is None:
                print("   %-12s %s" % (name, ref))
                continue
            struct = ""
            if want_structure:
                # THE STRUCTURE RATIO AND THE SCALAR SCORES, ON ONE LINE, BECAUSE EITHER
                # ALONE MISLEADS. A profile that fills the panel while wrecking the
                # correlation is not a win, and neither is the reverse; this table is the
                # only place both are visible at once. The scalars stay exactly what they
                # were -- `resample` to SIZE, the same call the default path makes -- so a
                # row here is comparable to a row of the table above and to the floors.
                n, o_n, r_n = _structure_grid(ours, ref, sgrid)
                (lo_o, ed_o), (lo_r, ed_r) = structure(o_n), structure(r_n)
                struct = "  |  n=%-5d low %.5f/%.5f=%5.2f  edge %.5f/%.5f=%5.2f" % (
                    n,
                    lo_o,
                    lo_r,
                    lo_o / max(lo_r, 1e-12),
                    ed_o,
                    ed_r,
                    ed_o / max(ed_r, 1e-12),
                )
                if want_bands:
                    (bo, to), (br, tr) = band_power(o_n), band_power(r_n)
                    struct += "\n   %-16s bands %s  total %.3f" % (
                        "",
                        " ".join(
                            "%d-%d %.2f" % (lo, hi, b / max(c, 1e-18))
                            for lo, hi, b, c in zip(BANDS[:-1], BANDS[1:], bo, br)
                        ),
                        to / max(tr, 1e-18),
                    )
                ours, ref = resample(ours, SIZE)[:, :, 0], resample(ref, SIZE)[:, :, 0]
            # STRUCTURE AND GAIN ARE DIFFERENT FAILURES and MAE does not separate them.
            # The best affine fit of ours onto the reference, and the error that REMAINS
            # after it, says which one you have: a small residual under a slope far from 1
            # is a render with the right picture at the wrong contrast, and no amount of
            # decoding the wrong filter will fix it.
            #
            # What it says today. Auras `basecolor` correlates at 0.94 and its MAE is 0.088,
            # but the fit is y = 0.536x with a residual of 0.032 -- the structure is right
            # and the contrast is roughly double. Chesterfield `roughness` is the opposite
            # end: correlation 0.29, MAE 0.019, fit y = 3.389x, so the picture is faintly
            # right at a NINTH of the reference's contrast. And Chesterfield `height` fits
            # y = -0.001x + 0.516, a slope of zero -- ours carries no information about the
            # reference at all, and its MAE of 0.248 is just the 0.23 offset between two
            # means.
            fit = (
                np.polyfit(ours.ravel(), ref.ravel(), 1)
                if ours.std() > 1e-9
                else (0.0, 0.0)
            )
            resid = float(np.abs(np.polyval(fit, ours.ravel()) - ref.ravel()).mean())
            # THE CORRELATION IS PRINTED, and it did not used to be. This column was labelled
            # `r=` and carried `resid` -- the residual AFTER the affine fit -- while the
            # comments above it, and this file's own header, use `r` for the correlation and
            # quote values like "r = 0.295" in that sense. Two meanings, one label, one
            # column. A reader who knows `r` as Pearson's sees Chesterfield `normal` at
            # 0.0235 and concludes the channel is uncorrelated noise; it correlates at
            # 0.9490, and 0.0235 is a small residual, which is the opposite verdict. That
            # misreading cost a session: it was reported twice as an unexplained collapse
            # and chased through a git bisect that found nothing, because nothing had
            # regressed.
            #
            # `test_reference_agreement_does_not_regress` scores the true correlation
            # against `REFERENCE_FLOOR`, so it was always the arbiter -- this table just
            # did not show the number the arbiter uses. Now it does, first, where a number
            # called `corr` is expected to be, and the residual keeps its own name.
            corr = 0.0
            if ours.std() > 1e-9 and ref.std() > 1e-9:
                corr = float(np.corrcoef(ours.ravel(), ref.ravel())[0, 1])
            # HOW MANY DISTINCT VALUES OUR RENDER ACTUALLY HAS, because a correlation
            # computed against a near-constant image is not evidence and this table was
            # being read as though it were. Chesterfield `roughness` renders as THREE
            # distinct values with std 0.0023 against the reference's 0.0262, and its
            # correlation 0.295 -- the strongest-looking structural agreement then --
            # is three plateaus landing near the reference's levels, not a picture that
            # matches. That number decided three separate fx arbitrations before anyone
            # looked at how many values were behind it.
            #
            # Rule of thumb, applied by eye rather than enforced here: a channel can
            # arbitrate only if `uniq` is comfortably above ~20 AND our std is at least
            # about a tenth of the reference's. Of the 15 channels this table scores
            # today, 7 clear that bar.
            uniq = int(len(np.unique(np.round(ours.ravel(), 4))))
            # THE DC OFFSET, `ours.mean() - ref.mean()`, AND NOTHING ELSE IN THIS MODULE
            # COULD SEE IT. Every other column here removes the mean by construction:
            # `corr` is a correlation, `band_power` subtracts the mean before the
            # transform and its bands are variance ratios, `structure` returns two
            # standard deviations, and `resid` is what is left after an affine fit that
            # is free to absorb any constant. The two mean columns were printed side by
            # side and a reader had to subtract them by eye, so a channel whose whole
            # error is a level shift read as a channel in good health.
            #
            # WHAT IT SAYS TODAY, and it is why the column exists. Chesterfield
            # `roughness` scores corr +0.9358 and MAE 0.0639 at render2 / implied / 256 --
            # and its DC offset is -0.0639. The two agree to four decimals, so 99.9% of
            # that channel's entire error is one constant, on a channel whose correlation
            # has read above +0.93 for the whole investigation and whose floor (0.91) is a
            # CORRELATION floor and cannot see it. The located cause is upstream: two
            # `blend` records in its cone multiply by a source that renders as an exactly
            # constant 0 instead of a mid-grey noise, so the chain arrives scaled by
            # 0.35 x 0.53. See FORMAT-NOTES.md, "roughness is one level shift, and it is
            # two multiply-blends whose noise source renders constant".
            #
            # It is signed and it is ours-minus-reference, the same order as the two mean
            # columns it is derived from, so a negative DC means our render is DARKER.
            dc = float(ours.mean() - ref.mean())
            print(
                "   %-12s %-3d %.4f / %-13.4f %.4f / %-13.4f %.4f  DC=%+.4f  corr=%+.4f"
                " y=%.3fx%+.3f resid=%.4f uniq=%d%s%s"
                % (
                    name if chan == 0 else "",
                    chan,
                    ours.mean(),
                    ours.std(),
                    ref.mean(),
                    ref.std(),
                    np.abs(ours - ref).mean(),
                    dc,
                    corr,
                    fit[0],
                    fit[1],
                    resid,
                    uniq,
                    "  DEGENERATE"
                    if (uniq < 20 or ours.std() < 0.1 * ref.std())
                    else "",
                    struct,
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
