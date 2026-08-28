#!/usr/bin/env python3
"""Draw a record graph as a layered DAG, each node showing its own rendered output.

`nodemap.py` shows WHAT every record produces; this shows HOW they connect, which is the
other half of reading a chain. The two answer different questions and the second one is
harder to get from text: a record's edge list is easy to print and almost impossible to hold
in your head twenty records deep, and the thing that usually matters -- which input is the
DESTINATION, which is the SOURCE, and which is the MASK -- is positional and therefore
invisible in a flat list.

    python3 tools/nodegraph.py <file.sbsasm> [-o out.png] [--cone REC] [--dim 128]
                               [--cell] [--weights r,g,b,a] [--thumb 64] [--dot out.dot]

EDGE ROLES ARE COLOURED, because that is the point. For a `blend` the edges are
(destination, source, mask) in that order, and a mask that is near zero makes the blend a
no-op no matter what the source is -- a failure that looks like nothing at all in a printout
and is obvious here as a pale edge into a node identical to its parent.

    white   edge 0   destination / primary input
    cyan    edge 1   source
    orange  edge 2   mask (opacity)
    grey    edge 3+  further inputs

LAYERING IS AS-LATE-AS-POSSIBLE by default: each node sits just above its earliest consumer,
not as high as its inputs allow. On this project's files that is worth far more than any
within-row reordering -- on Rokviz's basecolor cone it takes the drawn crossings from 80 to
19 -- because the alternative strands seventeen palette constants in the top row, each
dragging one long diagonal down the whole diagram. `--asap` restores the older layering.

Within a row, a barycentre sweep is TRIED and kept only if it actually reduces crossings; it
often does not once the edges are already short. Both counts are printed. Records that failed
to render are drawn as an empty red box: a hole in the graph is worth as much as a picture.

`--dot` additionally writes Graphviz source, for when a file is too wide to read as an image.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assume                                                        # noqa: E402
import render                                                        # noqa: E402
import sbsasm                                                        # noqa: E402

ROLE = [(235, 235, 240), (90, 210, 230), (240, 165, 70), (130, 130, 140)]
ROLE_NAME = ['dst', 'src', 'mask', 'in']


def edges_of(asm, i):
    return [e for e in asm.records[i].edges if isinstance(e, int) and 0 <= e < len(asm.records)]


def cone_of(asm, root):
    seen, stack = set(), [root]
    while stack:
        i = stack.pop()
        if i in seen:
            continue
        seen.add(i)
        stack.extend(edges_of(asm, i))
    return seen


def depths(asm, want):
    """Longest-path depth, so a node is always below every record it consumes."""
    d = {}

    def go(i, guard=0):
        if i in d:
            return d[i]
        if guard > 512:                      # cycles are not expected; do not hang on one
            return 0
        ins = [e for e in edges_of(asm, i) if e in want]
        d[i] = 0 if not ins else 1 + max(go(e, guard + 1) for e in ins)
        return d[i]

    for i in want:
        go(i)
    return d


def as_late_as_possible(asm, depth, want):
    """Push every node down to just above its EARLIEST consumer.

    Longest-path-from-the-sources puts all 17 palette uniforms in the top row, and several
    of them are consumed eight layers below -- so each drags one long diagonal across the
    whole diagram and no amount of within-row reordering can help, because the edge is long
    whatever order the row is in.

    Placing a node at `min(layer of its consumers) - 1` instead makes every edge as short as
    the graph allows, which is both fewer crossings and a truer picture: a constant colour
    used once, deep in the chain, BELONGS deep in the chain, and drawing it at the top
    implies a role in the early structure that it does not have.

    Sinks keep the deepest layer. Consumers always have a strictly greater longest-path
    depth than their inputs, so visiting nodes in decreasing depth order guarantees every
    consumer is resolved before the node that feeds it.
    """
    consumers = {i: [] for i in want}
    for i in want:
        for e in edges_of(asm, i):
            if e in want:
                consumers[e].append(i)
    maxd = max(depth.values()) if depth else 0
    out = {}
    for i in sorted(want, key=lambda k: -depth[k]):
        cs = [out[c] for c in consumers[i] if c in out]
        out[i] = maxd if not cs else min(cs) - 1
    # A node can land above 0 only if the graph disagrees with itself; clamp rather than
    # produce a negative row.
    lo = min(out.values()) if out else 0
    if lo < 0:
        out = {k: v - lo for k, v in out.items()}
    return out


def order_layers(asm, layers, want, rounds=12):
    """Reorder each layer by the BARYCENTRE of its neighbours, to reduce edge crossings.

    Records arrive in index order, which is the order they sit in the file and has nothing
    to do with who consumes them -- so a source feeding a node far to its right drags a long
    diagonal across everything between. The standard fix is Sugiyama's: repeatedly place each
    node at the average position of its neighbours and re-sort, sweeping down then up until
    it settles.

    Positions are measured as an offset from the ROW CENTRE rather than as a raw slot index,
    because the rows are centre-aligned and have different widths; comparing raw indices
    across a 3-wide row and a 17-wide row would pull every short row to the left.

    Neighbours are taken in BOTH directions. A node's placement should answer to what it
    feeds as well as what it consumes -- one-directional sweeps leave the leaves unplaced,
    and the leaves here are the palette uniforms, which are exactly the nodes whose edges
    were crossing the whole diagram.
    """
    nbr = {i: set() for i in want}
    for i in want:
        for e in edges_of(asm, i):
            if e in want:
                nbr[i].add(e)
                nbr[e].add(i)

    def centres():
        out = {}
        for ly, row in layers.items():
            half = (len(row) - 1) / 2.0
            for k, i in enumerate(row):
                out[i] = k - half
        return out

    for r in range(rounds):
        c = centres()
        for ly in (sorted(layers) if r % 2 == 0 else sorted(layers, reverse=True)):
            def bary(i):
                ns = [c[j] for j in nbr[i] if j in c]
                return sum(ns) / len(ns) if ns else c[i]
            layers[ly] = sorted(layers[ly], key=lambda i: (bary(i), i))
    return layers


def _seg_cross(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2 = side(a, b, c), side(a, b, d)
    d3, d4 = side(c, d, a), side(c, d, b)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def count_crossings(segments):
    """Exact geometric crossings among the drawn edge segments.

    Reported rather than assumed: a layout heuristic that makes a picture subjectively
    tidier while adding crossings is worth knowing about, and this is cheap at these sizes.
    """
    n = 0
    for x in range(len(segments)):
        for y in range(x + 1, len(segments)):
            if _seg_cross(*segments[x], *segments[y]):
                n += 1
    return n


def thumb(arr, side):
    from PIL import Image
    a = np.clip(np.nan_to_num(np.asarray(arr, dtype=np.float64)), 0.0, 1.0)
    if a.ndim == 2:
        a = a[:, :, None]
    if a.shape[2] == 1:
        a = np.repeat(a, 3, axis=2)
    im = Image.fromarray((a[:, :, :3] * 255).astype(np.uint8))
    return np.asarray(im.resize((side, side), Image.NEAREST))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('path')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--cone', type=int, default=None)
    ap.add_argument('--dim', type=int, default=128)
    ap.add_argument('--thumb', type=int, default=64)
    ap.add_argument('--cell', action='store_true')
    ap.add_argument('--weights', default=None)
    ap.add_argument('--dot', default=None)
    ap.add_argument('--asap', action='store_true',
                    help='layer by longest path from the sources instead of '
                         'pushing nodes down to their earliest consumer')
    args = ap.parse_args(argv)

    from PIL import Image, ImageDraw

    asm = sbsasm.Assembly(args.path)
    scope = {}
    if args.cell:
        scope['fx.patternsize'] = 'cell'
        scope['fx.branchoffset'] = 'cell'
    if args.weights:
        scope['grayscale.weights'] = tuple(float(x) for x in args.weights.split(','))
    if scope:
        with assume.scope(**scope):
            produced, failed, _s = render.render(asm, verbose=False, max_dim=args.dim)
    else:
        produced, failed, _s = render.render(asm, verbose=False, max_dim=args.dim)

    want = cone_of(asm, args.cone) if args.cone is not None else set(range(len(asm.records)))
    d = depths(asm, want)
    if not args.asap:
        d = as_late_as_possible(asm, d, want)
    layers = {}
    for i in sorted(want):
        layers.setdefault(d[i], []).append(i)

    T, GAPX, GAPY, LBL = args.thumb, 26, 74, 22
    width = max(len(v) for v in layers.values())
    W = width * (T + GAPX) + GAPX
    H = (max(layers) + 1) * (T + GAPY) + GAPY + 24
    img = Image.new('RGB', (W, H), (14, 14, 18))
    dr = ImageDraw.Draw(img)
    dr.text((10, 6), '%s   %d records   flow top->bottom   '
                     'white=dst  cyan=src  orange=mask'
            % (os.path.basename(args.path), len(want)), fill=(235, 235, 240))

    def place(lay):
        p = {}
        for ly in sorted(lay):
            row = lay[ly]
            x0 = (W - len(row) * (T + GAPX)) // 2 + GAPX // 2
            for k, i in enumerate(row):
                p[i] = (x0 + k * (T + GAPX), 24 + GAPY // 2 + ly * (T + GAPY))
        return p

    def segments(p):
        segs = []
        for i in sorted(want):
            if i not in p:
                continue
            for e in edges_of(asm, i):
                if e in p:
                    segs.append(((p[e][0] + T // 2, p[e][1] + T),
                                 (p[i][0] + T // 2, p[i][1] - LBL)))
        return segs

    # KEEP WHICHEVER ORDERING ACTUALLY WINS, because the heuristic does not always. Under
    # as-late-as-possible layering the edges are already short and barycentre sweeping made
    # this file WORSE -- 19 crossings by file order against 40 after sweeping -- while under
    # as-soon-as-possible layering the same sweep helped (80 -> 71). A tidier-looking rule
    # that is not measured is just a preference, so both are counted and the better is used.
    plain = {k: list(v) for k, v in layers.items()}
    pos_plain = place(plain)
    n_plain = count_crossings(segments(pos_plain))
    swept = order_layers(asm, {k: list(v) for k, v in layers.items()}, want)
    pos_swept = place(swept)
    n_swept = count_crossings(segments(pos_swept))
    if n_swept < n_plain:
        layers, pos, kept = swept, pos_swept, 'barycentre'
    else:
        layers, pos, kept = plain, pos_plain, 'file order'
    print('edge crossings: file order %d, barycentre %d -> using %s (%d)'
          % (n_plain, n_swept, kept, min(n_plain, n_swept)))

    # edges first, so nodes draw over them
    for i in sorted(want):
        if i not in pos:
            continue
        xi, yi = pos[i]
        for slot, e in enumerate(edges_of(asm, i)):
            if e not in pos:
                continue
            xe, ye = pos[e]
            dr.line([xe + T // 2, ye + T, xi + T // 2, yi - LBL],
                    fill=ROLE[min(slot, 3)], width=2 if slot < 3 else 1)

    for i in sorted(want):
        if i not in pos:
            continue
        x, y = pos[i]
        r = asm.records[i]
        v = produced.get(i)
        if v is None:
            dr.rectangle([x, y, x + T, y + T], outline=(190, 90, 90), fill=(46, 24, 24))
            dr.text((x + 3, y + T // 2 - 5), 'FAILED', fill=(210, 130, 130))
        else:
            img.paste(Image.fromarray(thumb(v, T)), (x, y))
            a = np.nan_to_num(np.asarray(v, dtype=np.float64))
            flat = a.reshape(-1, a.shape[-1]) if a.ndim == 3 else a.reshape(-1, 1)
            if float(flat.std()) < 1e-6:
                dr.rectangle([x, y, x + T, y + T], outline=(120, 120, 60))
        mode = ''
        if r.filter_name == 'blend':
            m = (r.slot1_flags or {}).get('blendingmode')
            if m is not None:
                mode = ' m%d' % m
        dr.text((x, y - LBL + 2), '%d %s%s' % (i, r.filter_name[:9], mode), fill=(225, 225, 232))

    out = args.out or (os.path.splitext(os.path.basename(args.path))[0] + '-graph.png')
    img.save(out)
    print('%s: %d records in view, %d produced, %d failed'
          % (os.path.basename(args.path), len(want), len(produced), len(failed)))
    print('wrote %s  (%dx%d)' % (out, img.size[0], img.size[1]))

    if args.dot:
        with open(args.dot, 'w') as fh:
            fh.write('digraph records {\n  rankdir=TB;\n  node [shape=box,fontsize=9];\n')
            for i in sorted(want):
                r = asm.records[i]
                fh.write('  r%d [label="%d %s"%s];\n'
                         % (i, i, r.filter_name,
                            ',color=red' if i not in produced else ''))
            for i in sorted(want):
                for slot, e in enumerate(edges_of(asm, i)):
                    if e in want:
                        fh.write('  r%d -> r%d [label="%s"];\n'
                                 % (e, i, ROLE_NAME[min(slot, 3)]))
            fh.write('}\n')
        print('wrote %s' % args.dot)
    return 0


if __name__ == '__main__':
    sys.exit(main())
