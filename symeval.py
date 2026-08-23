#!/usr/bin/env python3
"""Symbolically evaluate an .sbsasm instruction run and report the expression built.

Three-address code: each instruction writes the next value number.  Operands are
u16 value numbers referring to earlier results.  Seed `env` with symbolic inputs.
"""
import math, struct

# token length (in u16) per opcode, and an evaluator over already-resolved operands
LEN = {0x0900:3, 0x0D00:4, 0x0912:3, 0x0913:3, 0x0914:3, 0x0915:3,
       0x0862:3, 0x0D09:4, 0x0528:2, 0x0529:2, 0x052B:2, 0x0910:3}
SYM = {0x0912:('add',  lambda a,b: (f'({a[0]} + {b[0]})',  lambda x: a[1](x)+b[1](x))),
       0x0913:('sub',  lambda a,b: (f'({a[0]} - {b[0]})',  lambda x: a[1](x)-b[1](x))),
       0x0914:('mul',  lambda a,b: (f'({a[0]} * {b[0]})',  lambda x: a[1](x)*b[1](x))),
       0x0915:('div',  lambda a,b: (f'({a[0]} / {b[0]})',  lambda x: a[1](x)/b[1](x))),
       0x0862:('cmp_le',lambda a,b:(f'({a[0]} <= {b[0]})', lambda x: a[1](x)<=b[1](x))),
       0x0529:('ln',   lambda a:   (f'ln({a[0]})',  lambda x: math.log(a[1](x)) if a[1](x)>0 else float('-inf'))),
       0x052B:('exp2', lambda a:   (f'2^({a[0]})',  lambda x: 2.0**a[1](x))),
       0x0528:('sqrt', lambda a:   (f'sqrt({a[0]})',lambda x: math.sqrt(a[1](x)))),
       0x0D09:('select',lambda c,t,f:(f'({c[0]} ? {t[0]} : {f[0]})',
                                      lambda x: t[1](x) if c[1](x) else f[1](x)))}
NARGS = {0x0912:2,0x0913:2,0x0914:2,0x0915:2,0x0862:2,0x0529:1,0x052B:1,0x0528:1,0x0D09:3}


def run(d, start, end, env, counter, verbose=True):
    off, vn = start, counter
    while off < end:
        op = struct.unpack_from('<H', d, off)[0]
        if op not in LEN:
            if verbose: print(f'  0x{off:06X}  {op:04X}  <unknown opcode - stop>')
            return env, vn, off
        ln = LEN[op]
        if op in (0x0900, 0x0D00):                       # constant load
            fo = off + (2 if op == 0x0900 else 4)
            c = struct.unpack_from('<f', d, fo)[0]
            env[vn] = (f'{c:.9g}', (lambda k: (lambda x: k))(c))
            if verbose: print(f'  0x{off:06X}  {op:04X}  v{vn:<3} = const {c:.9g}')
        elif op == 0x0910:                               # component extract
            src, idx = struct.unpack_from('<HH', d, off+2)
            base = env.get(src, (f'v{src}', lambda x: x))
            env[vn] = (f'{base[0]}.{"xyzw"[idx] if idx<4 else idx}', base[1])
            if verbose: print(f'  0x{off:06X}  {op:04X}  v{vn:<3} = extract v{src}[{idx}]')
        else:
            n = NARGS[op]
            args = struct.unpack_from('<%dH' % n, d, off+2)
            vals = [env.get(a, (f'v{a}', lambda x: float("nan"))) for a in args]
            name, fn = SYM[op]
            env[vn] = fn(*vals)
            if verbose:
                print(f'  0x{off:06X}  {op:04X}  v{vn:<3} = {name}('
                      + ', '.join(f'v{a}' for a in args) + ')')
        vn += 1
        off += 2 * ln
    return env, vn, off
