#!/usr/bin/env python3
"""Render one .sbsasm, and score it against the package's own exported maps if it ships any.

    python3 tools/render2 <file.sbsasm> [--dim 256] [--out DIR] [--score DIR]

`--score DIR` pairs each declared output with `<DIR>/*<usage>.png` by the manifest's own
usage name -- basecolor, normal, roughness, height, metallic, ambientocclusion -- which is
the vocabulary the exporter names its files in. Nothing is matched by position.

Both arrays are resampled to 64 before scoring, per channel and at 16-bit precision. Read
the `uniq` column before reading a correlation: a channel with three distinct values
correlates with anything.
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


def _outputsize_warning(asm, refs, used):
    """Say so when the exported maps were not produced at the `$outputsize` being rendered.

    THE FILE DECLARES A DEFAULT AND THE EXPORTER DID NOT HAVE TO USE IT, and on a
    `dynamicsize` graph the two are a different render, not the same render at a different
    resolution: every size expression is a function of `$outputsize`, and a `switch` blend
    whose selector program compares `$sizelog2` against a constant takes the OTHER branch.
    `ChesterfieldSofa` declares 8 (256) and ships 2048 maps, and ten switches in its
    colour chain read `$sizelog2`; scoring the two against each other without saying so is
    how that package's basecolor spent months being read as a filter defect.

    A warning and not a default, because the reference's pixel dimensions are evidence
    about the export and not a statement by the file.
    """
    from engine import declared_outputsize
    decl = declared_outputsize(asm)
    if decl is None:
        return
    now = used or decl
    sizes = set()
    for p in refs.values():
        try:
            from PIL import Image
            sizes.add(Image.open(p).size[0])
        except Exception:
            pass
    implied = sorted({int(round(np.log2(s))) for s in sizes if s and s & (s - 1) == 0})
    if implied and implied != [now[0]]:
        print('   NOTE: rendering at $outputsize %s (file declares %s); the reference '
              'maps are %s px, i.e. $outputsize %s. Pass --outputsize %d to compare like '
              'with like.' % (now[0], decl[0], sorted(sizes), implied,
                              implied[-1]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='render2')
    ap.add_argument('path')
    ap.add_argument('--dim', type=int, default=256)
    ap.add_argument('--out')
    ap.add_argument('--score')
    ap.add_argument('--outputsize', type=int, default=None,
                    help='render the graph at $outputsize = this log2 size (8 = 256, '
                         '11 = 2048). Defaults to what the file declares. NOT --dim: '
                         '--dim caps the pixel grid, this is the size expressions read.')
    a = ap.parse_args(argv)

    asm = sbsasm.Assembly(a.path)
    os_log2 = None if a.outputsize is None else (a.outputsize, a.outputsize)
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

    names = manifest.output_names(asm)
    refs = references(a.score) if a.score else {}
    if refs:
        _outputsize_warning(asm, refs, os_log2)
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
