#!/usr/bin/env python3
"""The .sbsasm instruction length rule.

    length_in_tokens = (opcode >> 10) + 1        for 0x0400 <= opcode < 0x8000

Verified against 23 independently-established lengths (zero disagreements) and by
corpus coverage: 94.8% of 214 MB of instruction bytes decode linearly under this rule
alone, versus 32.9% using a hand-built 21-opcode table.

0x8000+ are 4-aligned records, separately framed, and exempt.
Below 0x0400 is not a valid opcode (those tokens are operands).
"""
LO, HI = 0x0400, 0x8000

class LengthTable(dict):
    """Behaves like the old dict-of-lengths, but computes rather than looks up."""
    def __contains__(self, op):   return LO <= op < HI
    def get(self, op, default=None):
        return (op >> 10) + 1 if LO <= op < HI else default
    def __getitem__(self, op):
        if LO <= op < HI: return (op >> 10) + 1
        raise KeyError(op)
    def __missing__(self, op):    raise KeyError(op)

LEN = LengthTable()

def length(op):   return (op >> 10) + 1 if LO <= op < HI else None
def nargs(op):    return (op >> 10)     if LO <= op < HI else None
def comps(op):    return ((op >> 6) & 3) + 1
def opid(op):     return op & 0x3F
def page(op):     return (op >> 8) & 0x3F
