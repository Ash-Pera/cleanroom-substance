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


# Op ids that no record-named program in the corpus ever uses.
#
# The length rule above accepts any word in [0x0400, 0x8000) -- 47% of all u16 values --
# which is why a scan for programs finds so many that are not programs. Requiring every
# op id to be one the format actually uses is a cheap, evidence-based tightening.
#
# Derived over strictly-named programs only (the programs a record's slots point at)
# across all 641 specimens. Every id below is absent from every one of them; the 49 that
# do occur are each present in at least 5 distinct specimens, so this is not a
# thin-evidence cut. Note 0x35 (41 files) and 0x36 (11 files) ARE real and are not here:
# a 150-specimen sample had missed them.
ABSENT_IDS = frozenset({0x05, 0x08, 0x0A, 0x0E, 0x19, 0x2C,
                        0x37, 0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F})


def plausible(op):
    """True if `op` is a well-formed opcode whose id the format actually uses."""
    return LO <= op < HI and ((op >> 8) & 3) != 3 and (op & 0x3F) not in ABSENT_IDS
