#!/usr/bin/env python3
"""Walk an fxmaps record's tree and disassemble every node's program."""
import struct
import isa, disasm
from sbsasm import Assembly


def program_end(data, q, hi):
    n = struct.unpack_from('<H', data, q)[0]
    if not (1 <= n <= 20000):
        return None
    p = q + 2
    for _ in range(n):
        if p + 2 > hi:
            return None
        L = isa.LEN.get(struct.unpack_from('<H', data, p)[0])
        if not L:
            return None
        p += 2 * L
    return p


def tree(asm, r):
    """Yield (offset, header, program offset or None) for each node, in chain order."""
    o, e = r.offset, r.end
    if len(r.words) < 3:
        return
    q = r.words[2] + 52
    seen = set()
    while o <= q < e - 7 and q not in seen:
        seen.add(q)
        h = struct.unpack_from('<I', asm.data, q)[0]
        if h not in (0x18B, 0x89):
            return
        p = struct.unpack_from('<I', asm.data, q + 4)[0] + 52
        yield q - o, h, (p if (o < p < e and program_end(asm.data, p, e)) else None)
        q = struct.unpack_from('<I', asm.data, q + (8 if h == 0x18B else 12))[0] + 52


if __name__ == '__main__':
    import sys
    a = Assembly(sys.argv[1])
    idx = int(sys.argv[2])
    r = a.records[idx]
    print('record %d  filter %s  %dx%d  len %d'
          % (idx, r.filter_name, r.width, r.height, r.end - r.offset))
    for off, h, p in tree(a, r):
        print('\n=== node 0x%X at +%d%s' % (h, off, '  program @+%d' % (p - r.offset) if p else '  (no program)'))
        if p:
            print(disasm.text(a.data, p, r.end))
