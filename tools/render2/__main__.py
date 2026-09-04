#!/usr/bin/env python3
"""Render one .sbsasm, and score it against the package's own exported maps if it ships any.

    python3 tools/render2 <file.sbsasm> [--dim 256] [--out DIR] [--score DIR]
                          [--outputsize N|declared]

`--score DIR` pairs each declared output with `<DIR>/*<usage>.png` by the manifest's own
usage name -- basecolor, normal, roughness, height, metallic, ambientocclusion -- which is
the vocabulary the exporter names its files in. Nothing is matched by position.

Both arrays are resampled to 64 before scoring, per channel and at 16-bit precision. Read
the `uniq` column before reading a correlation: a channel with three distinct values
correlates with anything.

**`--score` RENDERS AT THE SIZE THE REFERENCES WERE EXPORTED AT, and plain rendering does
not.** Every reference pack in this corpus ships maps at an `$outputsize` its own file does
not declare, and a record's size slot is a PROGRAM of `$outputsize`, so the two are
different graphs and not one graph at two resolutions. The default is therefore per-tool:
the file's declared size when rendering (that is all a consumer of the file has), the
implied size when scoring (that is what the other side of the comparison is). Both are
printed. `--outputsize declared` forces the file's own. See `_score_outputsize`.

**THIS SCORER'S PAIRING IS THE CRUDE ONE.** It globs `*.png`, keys on the last
underscore-separated token and keeps the first hit per key. On a single-graph pack that
agrees with `archive/tools/refcompare.py`; on a pack that declares several graphs and
flattens their exports into one directory it does not, and `Kutejnikov__Bricks_and_tiles`
reports 48 rows here -- five graphs' outputs each scored against whichever map the glob
returned first -- against the 12 distinct channels that survive `refcompare`'s graph
narrowing. Use `refcompare` for anything that arbitrates.
"""
import argparse
import glob
import os
import re
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # see __init__.py: this package goes LAST

import manifest                                                      # noqa: E402
import sbsasm                                                        # noqa: E402
from engine import render                                            # noqa: E402

SIZE = 64


def load_reference(path):
    from PIL import Image
    im = Image.open(path)
    a = np.asarray(im).astype(np.float64)
    a = a / (65535.0 if (im.mode == 'I;16' or a.max() > 255) else 255.0)
    return a[:, :, :3] if a.ndim == 3 else a[:, :, None]


def resample(x, n=SIZE):
    from PIL import Image
    return np.stack(
        [np.asarray(Image.fromarray((np.clip(x[:, :, c], 0, 1) * 65535).astype(np.uint16))
                    .resize((n, n), Image.BILINEAR), dtype=np.float64) / 65535.0
         for c in range(x.shape[2])], axis=-1)


def references(directory):
    out = {}
    for p in glob.glob(os.path.join(directory, '**', '*.png'), recursive=True):
        key = re.sub(r'[^a-z]', '', os.path.basename(p).rsplit('_', 1)[-1][:-4].lower())
        out.setdefault(key, p)
    return out


def _score_outputsize(asm, refs, asked, dim):
    """The `$outputsize` to SCORE at, and the reason, printed.

    THE FILE DECLARES A DEFAULT AND THE EXPORTER DID NOT HAVE TO USE IT, and on a
    `dynamicsize` graph the two are a different render, not the same render at a different
    resolution: every size expression is a function of `$outputsize`, and a `switch` blend
    whose selector program compares `$sizelog2` against a constant takes the OTHER branch.
    `ChesterfieldSofa` declares 8 (256) and ships 2048 maps, and ten switches in its
    colour chain read `$sizelog2`; scoring the two against each other without saying so is
    how that package's basecolor spent months being read as a filter defect.

    THIS USED TO BE A WARNING AND IS NOW THE DEFAULT, and the argument for the change is
    that the two are different questions:

      * RENDERING has no reference in it. The only thing a consumer of a `.sbsar` holds is
        the file, and the file states one `$outputsize`; a renderer that quietly picked
        some other number would be inventing a parameter. So `render()` and `--out` keep
        the declared size, and `render(asm)` with no `outputsize` is unchanged.
      * SCORING is a comparison, and a comparison between a render of G at 8 and an export
        of G at 11 measures neither. Here the reference's pixel dimensions are not a
        statement by the file, they are the one piece of evidence available about what the
        other side of the comparison IS -- and refusing to read it does not make the score
        neutral, it makes it wrong in a fixed direction.

    So the default is per-tool and not global: declared for the render, implied for the
    score. `--outputsize` overrides either way, and `--outputsize declared` is the spelling
    that gets the old behaviour back without the caller having to know the number.

    IT IS NOT FREE AT A SMALL `--dim`, and that is printed too rather than left for
    someone to rediscover. `$outputsize` and `--dim` are not independent: at
    `$outputsize` 11 ChesterfieldSofa has 15 distinct record sizes of which a 128-px cap
    leaves 7, against 9 at the declared size, so the cap flattens the size hierarchy
    MORE at the corrected size than at the wrong one. Measured on that pack, declared ->
    implied: 7 of 10 channels improve at `--dim` 128, 7 at 256, 8 at 512 and 10 of 10 at
    1024. The corrected size wants a grid that can carry it.
    """
    from engine import declared_outputsize, implied_outputsize
    decl = declared_outputsize(asm)
    if asked == 'declared' or decl is None:
        return None
    implied = implied_outputsize(refs.values())
    if asked is not None:
        want = (asked, asked)
    elif implied is None:
        print('   NOTE: the reference maps do not agree on one power-of-two size, so '
              'nothing is implied; scoring at the declared $outputsize %s.' % (decl[0],))
        return None
    else:
        want = implied
    if want == decl:
        return None
    print('   scoring at $outputsize %s, not the %s this file declares%s. Pass '
          '--outputsize declared for the file\'s own size.'
          % (want[0] if want[0] == want[1] else want,
             decl[0] if decl[0] == decl[1] else decl,
             '' if asked is not None else
             ' -- the reference maps are %d px' % (1 << implied[0])))
    if dim and dim < (1 << want[0]) // 4:
        print('   NOTE: --dim %d is far below the %d px this graph is now being evaluated '
              'at, and the cap flattens the size hierarchy the $outputsize creates. '
              'Read small margins here as understated, not as arbitrations.'
              % (dim, 1 << want[0]))
    return want


def main(argv=None):
    ap = argparse.ArgumentParser(prog='render2')
    ap.add_argument('path')
    ap.add_argument('--dim', type=int, default=256)
    ap.add_argument('--out')
    ap.add_argument('--score')
    ap.add_argument('--outputsize', default=None,
                    help="render the graph at $outputsize = this log2 size (8 = 256, "
                         "11 = 2048), or 'declared' for the file's own. Without --score "
                         "the default IS the declared size; WITH --score it is the size "
                         "the reference maps were exported at, because a score is a "
                         "comparison. NOT --dim: --dim caps the pixel grid, this is what "
                         "the size expressions read.")
    a = ap.parse_args(argv)
    asked = a.outputsize
    if asked not in (None, 'declared'):
        asked = int(asked)

    asm = sbsasm.Assembly(a.path)
    names = manifest.output_names(asm)
    refs = references(a.score) if a.score else {}
    # THE REFERENCES ARE READ BEFORE THE RENDER, because with `--score` they decide what
    # is rendered. Without them nothing here can imply a size and the declared one stands.
    if refs:
        os_log2 = _score_outputsize(asm, refs, asked, a.dim)
    else:
        os_log2 = None if asked in (None, 'declared') else (asked, asked)
    outs, fails, info = render(asm, max_dim=a.dim, outputsize=os_log2)
    print('%d/%d records, %d failures, %d low-confidence'
          % (len(outs), len(asm.records), len(fails), len(info['low_confidence'])))
    ign = info.get('ignored') or {}
    if ign:
        by_filter = {}
        for i, entries in ign.items():
            for (half, which, _slot, _w) in entries:
                by_filter.setdefault((asm.records[i].filter_name, half, which), 0)
                by_filter[(asm.records[i].filter_name, half, which)] += 1
        top = sorted(by_filter.items(), key=lambda kv: -kv[1])[:6]
        print('   %d records state a field no name covers: %s'
              % (len(ign), ', '.join('%s %s %s x%d' % (f, h, w, n)
                                     for (f, h, w), n in top)))
    roots = sorted(set(fails) - info['cascaded'])
    for i in roots[:20]:
        print('   rec %-5d %-16s %s' % (i, asm.records[i].filter_name, fails[i]))
    if len(fails) > len(roots):
        print('   (+%d cascaded)' % (len(fails) - len(roots)))

    scores = []
    for uid, fmt, _grey, ri in asm.outputs():
        nm = (names.get(uid) or '').lower()
        if a.out and ri in outs:
            _save(outs[ri], os.path.join(a.out, '%s_%d.png' % (nm or 'output', ri)))
        key = re.sub(r'[^a-z]', '', nm)
        if key not in refs:
            print('   %-18s rec %-5s %s' % (nm, ri, 'rendered' if ri in outs else
                                            'NOT RENDERED: %s' % fails.get(ri, '?')))
            continue
        if ri not in outs:
            print('   %-18s rec %-5s NOT RENDERED: %s' % (nm, ri, fails.get(ri, '?')))
            continue
        ours = np.asarray(outs[ri], dtype=np.float64)
        if ours.ndim == 2:
            ours = ours[:, :, None]
        o, r = resample(ours), resample(load_reference(refs[key]))
        for c in range(min(o.shape[2], r.shape[2])):
            x, y = o[:, :, c].ravel(), r[:, :, c].ravel()
            corr = float(np.corrcoef(x, y)[0, 1]) if x.std() > 1e-9 and y.std() > 1e-9 \
                else 0.0
            uniq = int(len(np.unique(np.round(x, 4))))
            scores.append(corr)
            print('   %-18s ch%d  corr %+.4f  MAE %.4f  ours %.4f/%.4f  ref %.4f/%.4f'
                  '  uniq %d%s'
                  % (nm if c == 0 else '', c, corr, np.abs(x - y).mean(),
                     x.mean(), x.std(), y.mean(), y.std(), uniq,
                     '  DEGENERATE' if (uniq < 20 or x.std() < 0.1 * y.std()) else ''))
    if scores:
        print('   mean corr over %d channels %+.4f' % (len(scores), np.mean(scores)))
    return 0


def _save(arr, path):
    from PIL import Image
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    a = np.clip(np.nan_to_num(np.asarray(arr, dtype=np.float64)), 0, 1)
    if a.ndim == 2:
        a = a[:, :, None]
    if a.shape[2] == 1:
        Image.fromarray((a[:, :, 0] * 255).astype(np.uint8), 'L').save(path)
    else:
        Image.fromarray((a[:, :, :3] * 255).astype(np.uint8), 'RGB').save(path)


if __name__ == '__main__':
    sys.exit(main())
