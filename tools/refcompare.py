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


def compare_pack(pack, refs, max_dim=SIZE):
    """Yield (output name, channel, ours, reference) arrays for every paired output."""
    asms = glob.glob(os.path.join(PACKS, pack, '**', '*.sbsasm'), recursive=True)
    if not asms:
        return
    asm = sbsasm.Assembly(asms[0])
    names = manifest.output_names(asm)
    produced, _failures, _synth = render.render(asm, verbose=False, max_dim=max_dim)
    for uid, _fmt, _gray, rec in asm.outputs():
        name = names.get(uid) or '?'
        paired = [r for r in refs if _key(name) and _key(name) in _key(os.path.basename(r))]
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
            print('   %-12s %-3d %.4f / %-13.4f %.4f / %-13.4f %.4f'
                  % (name if chan == 0 else '', chan, ours.mean(), ours.std(),
                     ref.mean(), ref.std(), np.abs(ours - ref).mean()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
