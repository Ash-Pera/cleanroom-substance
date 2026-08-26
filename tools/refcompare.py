#!/usr/bin/env python3
"""Compare rendered outputs against the engine's OWN exported maps.

Every other check in this repository is a distribution match or a source containment: a
decode is believed because its numbers line up with something independently known. This
is the one place a render can be scored against ground truth, because several packages in
the corpus ship the texture maps the engine exported alongside the .sbsar that produces
them.

    python3 tools/refcompare.py            # every package that ships reference maps
    python3 tools/refcompare.py Chesterfield   # substring-matched to one package

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
the canvas -- the right colour and far too small. That is the pattern FOOTPRINT, which
`tools/fxrender.py` names as its largest open question. `blend`, `levels` and
`dirmotionblur` in that chain are not losing anything; the two `blendingmode=3` records
downstream are multiplying already-sparse maps together, which is what multiply does.

So the honest reading of this table is a baseline, not a validation: nothing matches yet,
and the single number to move is the footprint.

WHERE THE RESIDUAL PROBABLY IS NOT. After the blend-opacity fix `normal` reads std 0.1018
against the reference's 0.0968 while its MAE ROSE, 0.0783 -> 0.1039. Right variance and a
worse error is a POSITION signature, not a size one: patterns of roughly the right extent
landing in the wrong places score worse than no patterns at all, because a flat image whose
mean is right is cheap on MAE. So an experiment that perturbs `patternsize` and rescores is
likely to move nothing -- the size path is separately settled, resolving to values from 0.25
to 2.92 including a non-square, none of them unset.

The candidate is the position path, `branchoffset` + `frameoffset`. Measured by the session
that decoded the FX structure: their combined x-extent has a median of 0.835 -- about one
cell, which is what tiling wants -- but a p90 of 7.8, so some records place patterns well
outside the unit square. That is a hypothesis with a number attached and not a finding; it
is recorded here because it is the second arm of the same experiment and would otherwise be
spent on the lane it has already been ruled out of.

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
import manifest                                                      # noqa: E402
import render                                                        # noqa: E402
import sbsasm                                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = os.path.join(ROOT, 'new_opengameart')
SIZE = 64


def load_reference(path):
    """A reference map as float in [0, 1], (H, W, C) -- by IMAGE MODE, not by guess."""
    from PIL import Image
    im = Image.open(path)
    a = np.asarray(im).astype(np.float64)
    a = a / (65535.0 if (im.mode == 'I;16' or a.max() > 255) else 255.0)
    return a[:, :, :3] if a.ndim == 3 else a[:, :, None]


def resample(x, n=SIZE):
    """Per channel, at 16-bit precision -- an 8-bit round trip here would quantise the
    very differences being measured."""
    from PIL import Image
    x = np.clip(x, 0.0, 1.0)
    if x.ndim == 2:
        x = x[:, :, None]
    chans = [np.asarray(Image.fromarray((x[:, :, c] * 65535).astype(np.uint16))
                        .resize((n, n), Image.BILINEAR), dtype=np.float64) / 65535.0
             for c in range(x.shape[2])]
    return np.stack(chans, axis=-1)


def _key(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())


def reference_packs(match=None):
    """Packages that ship exported maps, as {name: [png paths]}."""
    out = {}
    for png in glob.glob(os.path.join(PACKS, '*', 'reference_renders', '**', '*.png'),
                         recursive=True):
        pack = os.path.relpath(png, PACKS).split(os.sep)[0]
        out.setdefault(pack, []).append(png)
    if match:
        # Match the PACK NAME or any of its file names. A package directory is named for
        # its author (`Kutejnikov__Stylized_Wooden_Roof_Tiles`) while the material is
        # called RoofTiles everywhere else, so filtering on the directory alone silently
        # returns nothing for the name a caller actually has in hand.
        m = match.lower()
        out = {k: v for k, v in out.items()
               if m in k.lower() or any(m in os.path.basename(p).lower() for p in v)}
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
        if uid in g['outputs'] and g.get('pkgurl'):
            return g['pkgurl'].rstrip('/').rsplit('/', 1)[-1] or None
    return None


def compare_pack(pack, refs, max_dim=SIZE):
    """Yield (output name, channel, ours, reference) arrays for every paired output."""
    asms = glob.glob(os.path.join(PACKS, pack, '**', '*.sbsasm'), recursive=True)
    if not asms:
        return
    for _asm_path in sorted(asms):
        for _row in _compare_one(_asm_path, refs, max_dim):
            yield _row


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
    own = next((c for c in parts if c.startswith('x_')), None)
    if not own:
        return refs
    scoped = [r for r in refs
              if any(c and not c.startswith('x_') and own.lower().endswith(c.lower())
                     for c in os.path.normpath(r).split(os.sep)[:-1])]
    return scoped if scoped else refs


def _compare_one(asm_path, refs, max_dim):
    asm = sbsasm.Assembly(asm_path)
    refs = _package_refs(asm_path, refs)
    names = manifest.output_names(asm)
    produced, _failures, _synth = render.render(asm, verbose=False, max_dim=max_dim)
    for uid, _fmt, _gray, rec in asm.outputs():
        name = names.get(uid) or '?'
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
            _pre = [r for r in refs if os.path.basename(r).startswith(gdir + '_')]
            if _pre and any(os.path.basename(r).startswith((graph_dir(asm, u) or '\0') + '_')
                            for u, _f, _g, _rc in asm.outputs() for r in refs):
                pool = _pre
        if gdir and pool is refs and any(
                ('%s%s%s' % (os.sep, graph_dir(asm, u) or '\0', os.sep)) in r
                for u, _f, _g, _rc in asm.outputs() for r in refs):
            # ONLY WHERE THE PACKAGE SORTS ITS EXPORTS BY GRAPH. Most ship one graph and
            # put its maps straight in `reference_renders/`, and narrowing there would
            # discard every one of them. Where the directories DO exist, an empty result is
            # the answer: that graph exported nothing, and borrowing a sibling's map would
            # manufacture a score rather than find one.
            own = [r for r in refs if ('%s%s%s' % (os.sep, gdir, os.sep)) in r]
            pool = own
        paired = [r for r in pool if _key(name) and _key(name) in _key(os.path.basename(r))]
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
                paired = [r for r in pool
                          if _key(_ch) and _key(_ch) in _key(os.path.basename(r))]
                if paired:
                    name = _ch
        if rec not in produced or not paired:
            yield name, None, None, ('not rendered' if rec not in produced
                                     else 'no matching reference')
            continue
        ours = resample(np.asarray(produced[rec], dtype=np.float64))
        ref = resample(load_reference(paired[0]))
        for c in range(min(ours.shape[2], ref.shape[2])):
            yield name, c, ours[:, :, c], ref[:, :, c]


def main(argv):
    match = argv[1] if len(argv) > 1 else None
    packs = reference_packs(match)
    if not packs:
        print('no packages with reference maps found under %s' % PACKS)
        return 0
    for pack, refs in sorted(packs.items()):
        print('\n=== %s   (%d exported maps)' % (pack, len(refs)))
        print('   %-12s %-3s %-21s %-21s %s'
              % ('output', 'ch', 'ours mean/std', 'reference mean/std', 'MAE'))
        for name, chan, ours, ref in compare_pack(pack, refs):
            if chan is None:
                print('   %-12s %s' % (name, ref))
                continue
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
            fit = np.polyfit(ours.ravel(), ref.ravel(), 1) if ours.std() > 1e-9 else (0.0, 0.0)
            resid = float(np.abs(np.polyval(fit, ours.ravel()) - ref.ravel()).mean())
            print('   %-12s %-3d %.4f / %-13.4f %.4f / %-13.4f %.4f  y=%.3fx%+.3f r=%.4f'
                  % (name if chan == 0 else '', chan, ours.mean(), ours.std(),
                     ref.mean(), ref.std(), np.abs(ours - ref).mean(),
                     fit[0], fit[1], resid))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
