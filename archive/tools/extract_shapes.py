#!/usr/bin/env python3
"""Rasterise filter 5's embedded vector artwork.

    python3 tools/extract_shapes.py <file.sbsasm> [outdir] [--size 512] [--svg]

Filter 5 is a generator whose payload is a triangle strip in a 16-bit normalised
coordinate space; see `Record.vector_shape`. This writes one image per record, and with
`--svg` one `<polygon>` soup per record as well, which is lossless with respect to what
the file actually stores.

The shapes are the reason the identification does not rest on statistics. Point it at an
ambientCG road material and it writes out the pedestrian, bicycle, lorry and turn-arrow
markings; at a Christmas-ornament material and it writes snowflakes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sbsasm import Assembly


def to_svg(faces, size):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">' % (size, size)]
    for a, b, c in faces:
        out.append('<polygon points="%s" fill="#000"/>' % ' '.join(
            '%.2f,%.2f' % (p[0] * size, p[1] * size) for p in (a, b, c)))
    out.append('</svg>')
    return '\n'.join(out)


def main(path, outdir, size, want_svg):
    a = Assembly(path)
    stem = os.path.basename(path).rsplit('.', 1)[0]
    os.makedirs(outdir, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        Image = None
    n = 0
    for r in a.records:
        faces = r.vector_faces
        if not faces:
            continue
        kind = r.vector_shape[0]
        base = os.path.join(outdir, '%s_r%d_k%08x' % (stem, r.index, kind))
        if want_svg:
            open(base + '.svg', 'w').write(to_svg(faces, size))
        if Image is not None:
            im = Image.new('L', (size, size), 0)
            d = ImageDraw.Draw(im)
            for tri in faces:
                d.polygon([(p[0] * size, p[1] * size) for p in tri], fill=255)
            im.save(base + '.png')
        n += 1
    print('%s: %d shapes -> %s' % (os.path.basename(path), n, outdir))
    return n


if __name__ == '__main__':
    args = [x for x in sys.argv[1:] if not x.startswith('--')]
    size = 512
    if '--size' in sys.argv:
        size = int(sys.argv[sys.argv.index('--size') + 1])
        args = [x for x in args if x != str(size)]
    main(args[0], args[1] if len(args) > 1 else 'shapes', size, '--svg' in sys.argv)
