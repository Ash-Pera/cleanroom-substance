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


def main(argv=None):
    ap = argparse.ArgumentParser(prog='render2')
    ap.add_argument('path')
    ap.add_argument('--dim', type=int, default=256)
    ap.add_argument('--out')
    ap.add_argument('--score')
    a = ap.parse_args(argv)

    asm = sbsasm.Assembly(a.path)
    outs, fails, info = render(asm, max_dim=a.dim)
    print('%d/%d records, %d failures, %d low-confidence'
          % (len(outs), len(asm.records), len(fails), len(info['low_confidence'])))
    roots = sorted(set(fails) - info['cascaded'])
    for i in roots[:20]:
        print('   rec %-5d %-16s %s' % (i, asm.records[i].filter_name, fails[i]))
    if len(fails) > len(roots):
        print('   (+%d cascaded)' % (len(fails) - len(roots)))

    names = manifest.output_names(asm)
    refs = references(a.score) if a.score else {}
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
