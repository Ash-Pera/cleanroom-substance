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
from sbsasm import Assembly, fx_entry_layout


def tree(asm, r):
    """(absolute offset, header, program offset or None) per node, in chain order.

    `Record.fx_tree` yields absolute file offsets, as `fx_table` does. They used to
    disagree - one relative to the record, one to `body_lo` - which this front end printed
    under a single `+%d` as though they matched.
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
    for kind, off, tag, prog in r.fx_walk():
        n += 1
        label = 'node' if kind == 'node' else 'table entry'
        if kind == 'entry':
            # Which parameter each slot carries, from the tag alone -- see FX_PARAM_BITS.
            # A slot whose bit has no established name prints as `?`, not as a guess.
            lay = fx_entry_layout(tag)
            if lay:
                print('\n--- 0x%X: %s' % (tag, '  '.join(
                    '+%d %s%s' % (s, nm or '?', '' if k == 'program' else '=baked')
                    for s, nm, k in lay)))
        where = ('+%d' % (off - r.offset) if r.offset <= off < r.end
                 else '0x%X (outside this record)' % off)
        print('\n=== %s 0x%X at %s%s' %
              (label, tag, where,
               '  program @0x%X' % prog if prog else '  [shape not known]'))
        if prog:
            # bound by the body, not by this record: an entry's program need not be inside
            print(disasm.text(a.data, prog, a.body_hi))
    if not n:
        print('  slot 2 addresses neither a known node chain nor a parameter table')
        print('  (5.1%% of fxmaps records; see FORMAT-NOTES.md)')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('usage: fxdisasm.py <file.sbsasm> <record index>')
    main(sys.argv[1], int(sys.argv[2]))
