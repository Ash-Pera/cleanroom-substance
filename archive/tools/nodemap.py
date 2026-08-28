#!/usr/bin/env python3
"""Render every record in a file and lay the outputs out as one labelled contact sheet.

WHY THIS EXISTS. Chasing a wrong colour through a record graph one `print` at a time reads
the pipeline as a list of numbers, and a list of numbers hides the thing a picture makes
obvious: WHERE the image stops looking like the material and starts looking like something
else. On `Rokviz japanese fabric 8` the basecolor defect was chased through nine rounds of
per-record statistics -- means, standard deviations, correlations -- before it was clear that
the whole tail of the chain was a two-colour lerp. One sheet of 70 thumbnails would have said
that in a glance.

    python3 tools/nodemap.py <file.sbsasm> [-o out.png] [--dim 128] [--cone REC]
                             [--cell] [--weights r,g,b,a] [--thumb 96]
                             [--renderer render|render2] [--outputs]

`--cone REC` restricts the sheet to the records REC transitively depends on, which is the
usual way to look at one output. `--cell` and `--weights` set the assumption scope so a sheet
can be produced under a candidate reading rather than only the defaults. `--renderer render2`
draws it with the walk-only renderer instead, which is how the two are compared cell by cell.
`--outputs` drops the sheet to the declared outputs alone, which at a large `--thumb` is the
material as the engine would export it.

The graph's DECLARED OUTPUTS are outlined and labelled with their usage name rather than
their filter, because those six cells are what the material is and the rest is how it is
built.

Each cell shows the record index, its filter, and its channel mean. Records that failed to
render are drawn as an empty cell carrying the reason, because a hole in the graph is itself
the most useful thing a sheet can show -- the Rokviz investigation turned on five blends being
no-ops, which is visible here as five cells in a row that look identical to their neighbour.

Greyscale records are shown as grey; colour records as RGB. A record whose output is constant
is drawn flat, which is what it is -- no contrast stretch is applied, deliberately. Stretching
each cell to its own range would make a constant record look like a texture and would hide
exactly the degeneracy this is built to expose.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assume                                                        # noqa: E402
import manifest                                                      # noqa: E402
import render                                                        # noqa: E402
import sbsasm                                                        # noqa: E402


def renderer(name):
    """`(fn, label)` for `--renderer`. Both take (asm, verbose=, max_dim=).

    The two renderers disagree on real records, so a sheet has to say which one drew it --
    that is the whole point of putting them side by side. `render2` returns an `info` dict
    where `render` returns a `synthetic` set; only the first two members are read here.
    """
    if name == 'render2':
        import render2
        return (lambda asm, **kw: render2.render(asm, **kw)), 'render2'
    return render.render, 'render.py'


def cone_of(asm, root):
    """Every record `root` transitively depends on, including itself."""
    seen, stack = set(), [root]
    while stack:
        i = stack.pop()
        if i in seen:
            continue
        seen.add(i)
        for e in asm.records[i].edges:
            if isinstance(e, int) and 0 <= e < len(asm.records):
                stack.append(e)
    return seen


def as_rgb(arr, side):
    """One record's output as a `side`x`side` uint8 RGB thumbnail, NOT contrast-stretched."""
    from PIL import Image
    a = np.clip(np.nan_to_num(np.asarray(arr, dtype=np.float64)), 0.0, 1.0)
    if a.ndim == 2:
        a = a[:, :, None]
    if a.shape[2] == 1:
        a = np.repeat(a, 3, axis=2)
    a = a[:, :, :3]
    im = Image.fromarray((a * 255).astype(np.uint8))
    return np.asarray(im.resize((side, side), Image.NEAREST))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('path')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--dim', type=int, default=128, help='max_dim for the render')
    ap.add_argument('--cone', type=int, default=None, help='limit to this record\'s cone')
    ap.add_argument('--thumb', type=int, default=96)
    ap.add_argument('--cols', type=int, default=0, help='0 = auto')
    ap.add_argument('--cell', action='store_true',
                    help='render under fx.patternsize=cell and fx.branchoffset=cell')
    ap.add_argument('--weights', default=None,
                    help='grayscale.weights as r,g,b,a')
    ap.add_argument('--renderer', choices=('render', 'render2'), default='render',
                    help='which renderer draws the sheet (default: render)')
    ap.add_argument('--outputs', action='store_true',
                    help='only the graph\'s declared outputs -- the material itself')
    args = ap.parse_args(argv)

    from PIL import Image, ImageDraw

    asm = sbsasm.Assembly(args.path)
    scope = {}
    if args.cell:
        scope['fx.patternsize'] = 'cell'
        scope['fx.branchoffset'] = 'cell'
    if args.weights:
        scope['grayscale.weights'] = tuple(float(x) for x in args.weights.split(','))

    draw, engine_label = renderer(args.renderer)
    if scope:
        with assume.scope(**scope):
            produced, failed = draw(asm, verbose=False, max_dim=args.dim)[:2]
    else:
        produced, failed = draw(asm, verbose=False, max_dim=args.dim)[:2]

    # THE DECLARED OUTPUTS ARE WHAT THE MATERIAL IS, and on a 70-cell sheet they are six
    # cells among sixty-four. Naming them in the label is the difference between a sheet
    # you read and a sheet you search.
    try:
        names = manifest.output_names(asm)
        declared = {ri: (names.get(uid) or '?') for uid, _f, _g, ri in asm.outputs()}
    except Exception:
        declared = {}

    if args.outputs:
        want = sorted(declared)
    elif args.cone is not None:
        want = sorted(cone_of(asm, args.cone))
    else:
        want = list(range(len(asm.records)))
    print('%s: %d records, %d produced, %d failed%s'
          % (os.path.basename(args.path), len(asm.records), len(produced), len(failed),
             '' if args.cone is None else '  (cone of %d: %d records)' % (args.cone, len(want))))

    T, PAD, LBL = args.thumb, 6, 26
    cols = args.cols or max(1, int(np.ceil(np.sqrt(len(want) * 1.6))))
    rows = int(np.ceil(len(want) / cols))
    W = cols * (T + PAD) + PAD
    H = rows * (T + LBL + PAD) + PAD + 22
    sheet = Image.new('RGB', (W, H), (16, 16, 20))
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 6), '%s   %d records   %s   max_dim %d%s'
           % (os.path.basename(args.path), len(want), engine_label, args.dim,
              ('   ' + ' '.join('%s=%s' % kv for kv in sorted(scope.items()))) if scope else ''),
           fill=(235, 235, 240))

    for n, i in enumerate(want):
        r = asm.records[i]
        cx = PAD + (n % cols) * (T + PAD)
        cy = 22 + PAD + (n // cols) * (T + LBL + PAD)
        v = produced.get(i)
        if v is None:
            d.rectangle([cx, cy + LBL, cx + T, cy + T + LBL], fill=(40, 26, 26))
            why = str(failed.get(i, 'not produced'))
            d.text((cx + 3, cy + LBL + T // 2 - 6), why[:16], fill=(190, 130, 130))
            tone = (200, 140, 140)
        else:
            sheet.paste(Image.fromarray(as_rgb(v, T)), (cx, cy + LBL))
            a = np.nan_to_num(np.asarray(v, dtype=np.float64))
            flat = a.reshape(-1, a.shape[-1]) if a.ndim == 3 else a.reshape(-1, 1)
            m = flat.mean(axis=0)
            # A record whose output carries no spatial variation is the thing this sheet is
            # for, so it is called out in the label rather than left to the eye.
            const = float(flat.std()) < 1e-6
            d.text((cx + 2, cy + 13), ('%.2f ' % m[0]) + ('CONST' if const else
                   ' '.join('%.2f' % x for x in m[1:3])), fill=(150, 150, 160))
            tone = (225, 225, 232)
        if i in declared:
            # A declared output gets its usage name and a border, so the six cells that
            # ARE the material stand out from the sixty-four that build it.
            d.rectangle([cx - 2, cy + LBL - 2, cx + T + 1, cy + T + LBL + 1],
                        outline=(240, 200, 90))
            d.text((cx + 2, cy + 1), '%d %s' % (i, declared[i][:11]), fill=(240, 200, 90))
        else:
            d.text((cx + 2, cy + 1), '%d %s' % (i, r.filter_name[:11]), fill=tone)

    out = args.out or (os.path.splitext(os.path.basename(args.path))[0] + '-nodemap.png')
    sheet.save(out)
    print('wrote %s  (%dx%d)' % (out, sheet.size[0], sheet.size[1]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
