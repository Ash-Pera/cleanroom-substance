#!/usr/bin/env python3
"""Why layouts.json cannot be regenerated from the slot rule, and where it is lossy.

The obvious move, once the slot rule was exact against the records, was to rewrite
layouts.json from it. That is not possible, and this reports why.

The table's key is `(filter_id, cls, word1 & LAYOUT_MASK[filter])`. The rule needs the
FULL word1 - every two-bit parameter field. Where the mask drops a field bit, two records
with different parameters collide on one key and must share one answer, so no rewriting of
entries can express the rule:

    python3 tools/gen_layouts.py

The regeneration therefore happens in `Record._compute_layout`, which sees the whole word,
and the table remains only as the fallback for filters whose fields are not catalogued.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbsasm                                                        # noqa: E402


def main():
    print('%-18s %12s %12s %14s  %s'
          % ('filter', 'LAYOUT_MASK', 'field bits', 'lost by key', 'verdict'))
    lossy = 0
    for f in sorted(sbsasm.PARAM_SPEC):
        if f in sbsasm.PARAM_RAW:
            continue
        lm = sbsasm.LAYOUT_MASK.get(f, 0)
        cov = 0
        for _n, m, _h in sbsasm.PARAM_SPEC[f]:
            cov |= m
        if f == 1:
            cov |= 0x200                      # blend's bit-9 flag
        lost = cov & ~lm
        lossy += bool(lost)
        print('%-18s %12s %12s %14s  %s'
              % (sbsasm.FILTERS.get(f, 'fid %d' % f), hex(lm), hex(cov), hex(lost),
                 'LOSSY' if lost else 'complete'))
    print('\n%d of %d catalogued filters have a key that cannot carry their own rule.'
          % (lossy, len([f for f in sbsasm.PARAM_SPEC if f not in sbsasm.PARAM_RAW])))
    print('fxmaps is a fifth: LAYOUT_MASK 0xe55 keeps bits 10 and 11 of its 4-bit arity')
    print('field at bits 10-13 and discards 12 and 13.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
