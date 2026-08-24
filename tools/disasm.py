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
#   0x03            reads something by index; its single operand is the index
#   0x06            position 1 = an index; position 0 is an ordinary value reference
#
# 0x03 and 0x06 were rendering as value references and are not -- but they are not the
# same shape, and treating both as 'all' was wrong about 0x06. Testing each operand
# position separately for "operand >= its own value number", which no reference can be
# since three-address code numbers results contiguously:
#
#                   position 0            position 1
#     0x06            0.0% (n=497)          88.1%
#     0x07 set        0.0% (n=897,276)       0.2%
#     0x10 swizzle    0.0% (n=659,778)      36.0%
#
# So 0x06 has the shape of `set` and `swizzle`: a value in position 0 and an index in
# position 1. The test only ever undercounts -- `set`'s slot index reads 0.2% because a
# small index is usually below the instruction's own number anyway -- which makes
# position 0 at exactly 0.0% strong evidence that it really is a reference.
#
# 0x03 carries one token and is the whole immediate: its operand is >= its own value
# number in 75.7% of instances, and it is the program's FIRST instruction 59.0% of the
# time, where there is nothing to refer to. What either indexes is not established, so
# they stay unnamed.
#
# The controls are `add` (0.0%, n=976,997) and `eq` (0.0%, n=5,263). `sysvar` and `get`
# are NOT controls and measure 84.2% and 66.9%: they carry immediates too, which is why
# they are in this table.
#
# Measured on programs a record's slots name, never on the permissive whole-file scan:
# on that scan even `add` reads 38.5% impossible and `lteq` 86.5%, because the scan
# accepts positions that are not programs at all.
IMM = {0x00:'all', 0x02:'all', 0x01:'all', 0x04:'all', 0x03:'all',
       0x10:(1,), 0x07:(1,), 0x0B:(0,), 0x33:(1,), 0x34:(1,), 0x06:(1,)}

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

def pad_bytes(toks):
    """Bytes of alignment padding ahead of an instruction's immediate.

    Immediate-carrying opcodes come in two forms differing by 0x0400 -- one extra token.
    The longer form emits a 2-byte pad when the instruction lands at 0 mod 4, so that the
    immediate itself stays 4-aligned. Reading from the first operand byte regardless
    misreads every constant in the padded form: it takes the low half of one float32 and
    the high half of the previous word, which destroys the exponent. For the 9-token form,
    reading from byte 0 yields values like 7.5e-28 and -3.0e-13; skipping the pad yields
    1, 0.001 and 0.333333.

                     plausible magnitude, from byte 0  /  from byte 2
        3 tokens, addr%4=0          90.8%                   99.8%
        5 tokens, addr%4=0          98.0%                  100.0%
        9 tokens, addr%4=0          92.0%                  100.0%
        4 tokens, addr%4=2         100.0%                   45.6%

    **The pad is read from the token count, not from the address.** A 4-byte immediate
    needs an even number of u16 tokens, so an odd count above one IS the pad. Deriving it
    from `addr % 4` instead is right for the constants and input references that carry a
    4-byte immediate -- their token counts correlate with alignment exactly -- but wrong
    for every operation whose immediate is a single u16, because those have no padded
    form and land at both alignments:

        sysvar      1 token @0: 15,422    @2: 87,591
        get         1 token @0:  5,693    @2: 22,632
        0x03        1 token @0:    700    @2:  3,832
        const 0440  1 token @0: 21,889             every 1-token constant is bool

    Padding those strips the only operand there is. Token parity cannot misfire that way,
    and agrees with alignment everywhere a padded form actually exists.
    """
    return 2 if len(toks) > 1 and len(toks) % 2 else 0


def _imm(f, toks, addr=None):
    """Render the immediate carried by a constant/inputref instruction.

    See `pad_bytes` for the alignment pad. `addr` is accepted for backward compatibility
    and is no longer needed: the pad follows from the token count alone.
    """
    pad = pad_bytes(toks)
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

def immediate(addr, toks):
    """The immediate bytes an instruction carries, with the alignment pad removed.

    Any tool reading an immediate must go through this. `addr` is accepted so existing
    callers keep working and is no longer used -- see `pad_bytes` for why the pad is read
    from the token count instead.
    """
    return b''.join(struct.pack('<H', t) for t in toks)[pad_bytes(toks):]


def uid(addr, toks):
    """The u32 uid carried by an inputref (op id 0x02), or None."""
    raw = immediate(addr, toks)
    return struct.unpack_from('<I', raw)[0] if len(raw) >= 4 else None


def floats(addr, toks, n=None):
    """The float32 immediates a const.f instruction carries."""
    raw = immediate(addr, toks)
    out = [struct.unpack_from('<f', raw, i)[0] for i in range(0, len(raw) - 3, 4)]
    return out[:n] if n else out
