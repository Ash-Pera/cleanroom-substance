#!/usr/bin/env python3
"""Walk an fxmaps record's tree and disassemble every node's program.

This is a thin front end over `sbsasm`. It used to carry its own copy of the tree walk,
its own node table (which knew two of the four node shapes) and its own program
validator (which predated the operand-possibility check). Every one of those had drifted
from the module they were copied from, which is the same defect that let `program_span`
and `valid_program` disagree. There is now one implementation of each.
"""
import sys

import disasm
from sbsasm import Assembly, FX_NODES


def tree(asm, r):
    """(offset within record, header, program offset or None) per node, in chain order.

    `Record.fx_tree` already yields the offset relative to the record, so nothing is
    subtracted here -- doing so once printed node positions as large negative numbers.
    """
    return r.fx_tree()


def main(path, idx):
    a = Assembly(path)
    r = a.records[idx]
    print('record %d  filter %s  %dx%d  %d bytes  %d programs'
          % (idx, r.filter_name, r.width, r.height, r.end - r.offset, len(r.programs)))
    if r.filter_id != 4:
        print('  not an fxmaps record'); return
    n = 0
    for off, tag, prog in r.fx_table():
        n += 1
        print('\n=== table entry 0x%X at +%d%s' %
              (tag, off, '  program @+%d' % (prog - r.offset) if prog else
               '  [tag shape not known]'))
        if prog:
            print(disasm.text(a.data, prog, r.end))
    for off, hdr, prog in tree(a, r):
        n += 1
        known = FX_NODES.get(hdr)
        print('\n=== node 0x%X at +%d%s%s'
              % (hdr, off,
                 '  program @+%d' % (prog - r.offset) if prog else '  (no program)',
                 '' if known else '   [shape not known]'))
        if prog:
            print(disasm.text(a.data, prog, r.end))
    if not n:
        print('  slot 2 addresses neither a known node chain nor a parameter table')
        print('  (5.1%% of fxmaps records; see FORMAT-NOTES.md)')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('usage: fxdisasm.py <file.sbsasm> <record index>')
    main(sys.argv[1], int(sys.argv[2]))
