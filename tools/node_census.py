#!/usr/bin/env python3
"""Harvest fx-tree node cells and derive the node schema's size law.

A node cell is what fills the gaps between a record's header and its inline programs.
Cells are 4-aligned (programs are u16 streams, so up to 2 padding bytes follow each);
a cell's first word is its TAG.

What this measures, in order:

  1. node size is a function of the tag: 92% of cells take their tag's modal size, and
     the residue is multi-node gaps and misparses, not counter-evidence;
  2. the tag's LOW BYTE is a KIND (0x48, 0x58, 0x08, 0x88, 0x89, 0x8b, ...);
  3. within a kind, size is ADDITIVE over the remaining tag bits, with every cost a
     field width -- the two kinds with enough tag variety to test are EXACT:

         kind 0x48   102 tags   60,652 cells   100.00%   const 8
                     bit 16 = +16   bits 17,19,20,22,24 = +4   bit 23 = +8
         kind 0x58    29 tags    9,367 cells   100.00%   const 12
                     bits 17,20,22,26 = +4     bits 21,25 = +8

So the node tag is a PRESENCE MASK and node size follows the width law -- the same
design as the record header, at the third scale it has appeared (record cls+w1, the
colour multiplier, and now tree nodes). The single-tag kinds (0x89, 0x8b, 0x18, ...)
have no variation to fit but also no ambiguity: one tag, one size.

Pointer layout comes for free: probing each 4-byte offset of a cell for "value + 52 is
a valid program" gives per-tag pointer maps with rates of 100% or ~0%, nothing between:

    0x00000089   size 16   pointer at +4
    0x0000018b   size 12   pointer at +4
    0x00420008   size 16   pointer at +12
    0x14520248   size 28   pointers at +12 +16 +20 +24
"""
import collections
import struct
import sys
import os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
from sbsasm import Assembly                                           # noqa: E402

CHAIN = 0x20008          # the levels-appendix chain tag; variable payload, not a cell


def harvest():
    sizes = collections.defaultdict(collections.Counter)
    ptr = collections.defaultdict(collections.Counter)
    seen = collections.Counter()
    for p in corpus.paths():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4 or len(r.words) < 4:
                continue
            root = r.words[2] + 52
            if not (r.offset < root < r.end):
                continue
            spans = []
            for q in r.programs:
                if root <= q < r.end:
                    try:
                        spans.append((q, a.program_end(q)))
                    except Exception:
                        pass
            spans.sort()
            pos = root
            for s, e in spans + [(r.end, r.end)]:
                pos = (pos + 3) & ~3
                if pos + 8 <= s:
                    tag = struct.unpack_from('<I', a.data, pos)[0]
                    sizes[tag][s - pos] += 1
                    if seen[tag] < 4000:
                        seen[tag] += 1
                        for off in range(4, min(s - pos, 64), 4):
                            v = struct.unpack_from('<I', a.data, pos + off)[0]
                            q2 = v + 52
                            if a.body_lo <= q2 < a.body_hi and a.valid_program(q2):
                                ptr[tag][off] += 1
                pos = max(pos, e)
    return sizes, ptr, seen


def main():
    sizes, ptr, seen = harvest()
    tot = sum(sum(c.values()) for c in sizes.values())
    det = sum(c.most_common(1)[0][1] for c in sizes.values())
    print('node cells %d   tags %d   size deterministic %.3f%%'
          % (tot, len(sizes), 100 * det / tot))
    keys = [(t, c.most_common(1)[0][0], sum(c.values())) for t, c in sizes.items()
            if t != CHAIN and sum(c.values()) >= 10
            and c.most_common(1)[0][1] / sum(c.values()) >= 0.9]
    byk = collections.defaultdict(list)
    for k in keys:
        byk[k[0] & 0xFF].append(k)
    for kind, ks in sorted(byk.items(), key=lambda kv: -sum(x[2] for x in kv[1])):
        bits = [b for b in range(8, 32) if len({t >> b & 1 for t, _, _ in ks}) > 1]
        n = sum(x[2] for x in ks)
        if len(ks) <= len(bits) + 1:
            only = ks[0] if len(ks) == 1 else None
            print('   kind %#04x %4d tags %8d cells   %s'
                  % (kind, len(ks), n,
                     ('single tag, size %d' % only[1]) if only else 'underdetermined'))
            continue
        X = np.array([[1.0] + [float(t >> b & 1) for b in bits] for t, _, _ in ks])
        y = np.array([h for _, h, _ in ks], float)
        wt = np.array([x[2] for x in ks], float)
        sw = np.sqrt(wt)
        co = np.rint(np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0])
        ok = X @ co == y
        nz = [(b, int(c)) for b, c in zip(bits, co[1:]) if c]
        print('   kind %#04x %4d tags %8d cells   exact %6.2f%%  const=%d  %s'
              % (kind, len(ks), n, 100 * wt[ok].sum() / wt.sum(), int(co[0]), nz))
    print()
    print('pointer maps, top tags:')
    for t, c in sorted(sizes.items(), key=lambda kv: -sum(kv[1].values()))[:10]:
        if t == CHAIN or not seen[t]:
            continue
        m = ['+%d' % o for o, h in sorted(ptr[t].items()) if h / seen[t] > 0.9]
        print('   %#012x size %-4d pointers %s' % (t, c.most_common(1)[0][0],
                                                   ' '.join(m) or '-'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
