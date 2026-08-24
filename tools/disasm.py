"""Disassembler for .sbsasm bytecode programs.

Three-address code: each instruction produces one value, numbered contiguously from 0.
Operand tokens are u16 value numbers, except where the operation carries an immediate.

Usage:
    import disasm
    print(disasm.text(data, prog_ptr, hi))          # listing for one program
    for op,args,imm in disasm.decode(data, ptr, hi) # structured
"""
import struct, isa

NAMES = {
 (1,0x00):'const',   (2,0x00):'const',   (0,0x00):'const',
 (1,0x01):'sysvar',  (1,0x02):'inputref',(2,0x02):'inputref',
 (1,0x04):'get',     (2,0x04):'get',     (0,0x04):'get',
 (1,0x07):'set',     (2,0x07):'set',     (0,0x07):'set',
 (1,0x09):'select',  (2,0x09):'select',  (0,0x09):'select',
 (1,0x0C):'seq',     (2,0x0C):'seq',     (0,0x0C):'seq',
 (1,0x0D):'vec',     (2,0x0D):'vec',
 (1,0x10):'swizzle', (2,0x10):'swizzle',
 (1,0x11):'cvt',     (2,0x11):'cvt',
 (1,0x12):'add',     (2,0x12):'add',
 (1,0x13):'sub',     (2,0x13):'sub',
 (1,0x14):'mul',     (2,0x14):'mul',
 (1,0x15):'div',     (2,0x15):'div',
 (1,0x16):'mod',     (2,0x16):'mod',
 (1,0x17):'neg',
 (1,0x18):'dot',     (2,0x18):'dot',
 (1,0x23):'abs',     (1,0x24):'floor',   (1,0x25):'ceil',
 (1,0x26):'cos',     (1,0x27):'sin',     (1,0x28):'sqrt',
 (1,0x29):'ln',      (1,0x2B):'exp2',    (1,0x2D):'atan2',
 (1,0x2E):'cartesian',(1,0x2F):'lerp',
 (1,0x30):'min',     (2,0x30):'min',
 (1,0x31):'max',     (2,0x31):'max',
 (1,0x32):'rand',
 (1,0x33):'samplelum',(1,0x34):'samplecol',
 (0,0x1A):'and',     (0,0x1B):'or',      (0,0x1C):'not',
 (0,0x1D):'eq',      (0,0x1F):'gt',      (0,0x20):'gteq',
 (0,0x21):'lt',      (0,0x22):'lteq',
}
TYPE = {0:'b', 1:'f', 2:'i', 3:'?'}

# Operations whose operand tokens are immediates rather than value numbers.
# 'all' = every token is part of one immediate; otherwise a tuple of token positions.
#   0x10 swizzle    position 1 = packed 2-bit component mask (position 0 is the source)
#   0x07 set        position 1 = variable slot (position 0 is the value)
#   0x0B while      position 0 = iteration cap
#   0x33 samplelum  position 1 = sampler index (which input image to read)
#   0x34 samplecol  position 1 = sampler index
#   0x03, 0x06      read something by index; the operand is the index, not a value
#
# 0x03 and 0x06 were rendering as value references and are not. Over strictly-named
# programs, 0x03's operand is >= its own value number in 75.7% of 6,177 instances and
# 0x06's in 69.3% of 762 -- impossible for a reference, since three-address code numbers
# results contiguously and an operand must name an earlier value. 0x03 is also the
# program's FIRST instruction 59.0% of the time, where there is nothing to refer to.
# By comparison sysvar, get, add and eq measure 0.0% impossible on the same set.
# What they index is not established, so they stay unnamed.
#
# Measured on programs a record's slots name, never on the permissive whole-file scan:
# on that scan even `add` reads 38.5% impossible and `lteq` 86.5%, because the scan
# accepts positions that are not programs at all.
IMM = {0x00:'all', 0x02:'all', 0x01:'all', 0x04:'all', 0x03:'all', 0x06:'all',
       0x10:(1,), 0x07:(1,), 0x0B:(0,), 0x33:(1,), 0x34:(1,)}

def fields(op):
    return dict(ntok=(op >> 10) + 1, ty=(op >> 8) & 3, comps=((op >> 6) & 3) + 1, id=op & 0x3F)

def name(op):
    f = fields(op)
    return NAMES.get((f['ty'], f['id']), 'op%02X' % f['id'])

def decode(d, ptr, hi):
    """Yield (index, addr, opcode, [operand tokens]) for one program."""
    n = struct.unpack_from('<H', d, ptr)[0]
    q = ptr + 2
    for k in range(n):
        if q + 2 > hi: return
        op = struct.unpack_from('<H', d, q)[0]
        L = isa.LEN.get(op)
        if not L: return
        toks = list(struct.unpack_from('<%dH' % (L - 1), d, q + 2)) if L > 1 else []
        yield k, q, op, toks
        q += 2 * L

def _imm(f, toks, addr=None):
    """Render the immediate carried by a constant/inputref instruction.

    Immediate-carrying opcodes come in two forms differing by 0x0400 -- one extra token.
    The longer form emits a 2-byte pad when the instruction lands at 0 mod 4, so that the
    immediate itself stays 4-aligned. Reading from the first operand byte regardless
    misreads every constant in the padded form: it takes the low half of one float32 and
    the high half of the previous word, which destroys the exponent.

    The correlation is exact in the corpus -- odd token counts occur only at addr%4==0 and
    even counts only at addr%4==2 -- and the readings separate accordingly. For the
    9-token form, reading from byte 0 yields values like 7.5e-28 and -3.0e-13; skipping
    the pad yields 1, 0.001 and 0.333333.

                     plausible magnitude, from byte 0  /  from byte 2
        3 tokens, addr%4=0          90.8%                   99.8%
        5 tokens, addr%4=0          98.0%                  100.0%
        9 tokens, addr%4=0          92.0%                  100.0%
        4 tokens, addr%4=2         100.0%                   45.6%

    `addr` is the opcode's own offset. It is optional only so old callers keep working;
    without it the pad cannot be detected and padded constants are misread.
    """
    pad = 2 if (addr is not None and addr % 4 == 0) else 0
    raw = b''.join(struct.pack('<H', t) for t in toks)[pad:]
    if f['id'] == 0x02:
        return 'uid=%d' % struct.unpack_from('<I', raw)[0] if len(raw) >= 4 else '?'
    if f['id'] != 0x00:
        return ' '.join('%d' % t for t in toks[pad // 2:])
    out = []
    for i in range(0, len(raw) - 3, 4):
        if f['ty'] == 1: out.append('%g' % struct.unpack_from('<f', raw, i)[0])
        else:            out.append('%d' % struct.unpack_from('<i', raw, i)[0])
    return ', '.join(out) if out else '?'

def text(d, ptr, hi, mark=()):
    """Human-readable listing. `mark` is a set of opcodes to flag with '<<<'."""
    n = struct.unpack_from('<H', d, ptr)[0]
    lines = ['; program @%d  %d instructions' % (ptr, n)]
    for k, addr, op, toks in decode(d, ptr, hi):
        f = fields(op)
        nm = '%s.%s%d' % (name(op), TYPE[f['ty']], f['comps'])
        rule = IMM.get(f['id'])
        if rule == 'all':
            args = _imm(f, toks, addr)
        else:
            pos = rule or ()
            args = ', '.join('#%d' % t if i in pos
                             else ('%%%d' % t if t < k else '%%%d!' % t)
                             for i, t in enumerate(toks))
        lines.append('  %%%-4d %04X  %-14s %-34s%s' % (k, op, nm, args,
                     '   <<<' if op in mark else ''))
    return '\n'.join(lines)
