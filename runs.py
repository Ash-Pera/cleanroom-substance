#!/usr/bin/env python3
"""Find maximal clean-decode runs and recover their absolute value numbering.

Every instruction writes exactly one value and numbering is contiguous, so if a run
starts at absolute value number S, instruction i holds value S+i and each operand a
must satisfy a < S+i.  Hence S >= max(a - i) + 1 over the run; that bound is tight
whenever any instruction references the value defined immediately before it, which is
the common case.  This recovers absolute numbering for a run found in isolation.
"""
import struct
from isa import LEN

NAME={0x0900:'const',0x0D00:'const',0x1140:'const2',0x1980:'const3',
      0x0912:'add',0x0913:'sub',0x0914:'mul',0x0915:'div',0x0918:'dot',
      0x0528:'sqrt',0x0529:'ln',0x052B:'exp2',0x0862:'cmp',0x085F:'cmp',
      0x0D09:'select',0x0910:'extract',
      0x0902:'ref.f1',0x0942:'ref.f2',0x0982:'ref.f3',0x09C2:'ref.f4',
      0x0A02:'ref.i1',0x0A42:'ref.i2',0x0842:'ref.i1b'}

def runs(d, lo, hi):
    """Yield (start, instrs, blocker) for maximal clean runs, longest first."""
    n=(hi-lo)//2
    R=[0]*(n+2); B=[None]*(n+2)
    for i in range(n-1,-1,-1):
        off=lo+2*i
        if off+2>len(d): continue
        op=struct.unpack_from('<H',d,off)[0]
        L=LEN.get(op)
        if L is None: R[i],B[i]=0,op
        else:
            j=i+L
            if j<=n: R[i]=1+R[j]; B[i]=B[j]
            else: R[i],B[i]=0,op
    out=[]; i=0
    while i<n:
        if R[i]>0:
            out.append((lo+2*i, R[i], B[i]))
            k=i; c=R[i]
            while c>0:
                op=struct.unpack_from('<H',d,lo+2*k)[0]; k+=LEN[op]; c-=1
            i=k
        else: i+=1
    return out

def instrs(d, start, count):
    off=start; out=[]
    for _ in range(count):
        op=struct.unpack_from('<H',d,off)[0]; L=LEN[op]
        args=struct.unpack_from('<%dH'%(L-1), d, off+2)
        out.append((off,op,L,args)); off+=2*L
    return out, off

# operands that are IMMEDIATES, not value numbers: (op-id) -> set of operand indices.
# Established by ground-truth alignment against .sbs sources.
IMMEDIATE = {
    0x10: {1},          # swizzle: packed 2-bit component mask
    0x07: {1},          # set: variable slot index
    0x01: {0}, 0x03: {0}, 0x04: {0},   # get: variable slot index
}

def is_imm(op, k):
    return k in IMMEDIATE.get(op & 0x3F, ())


def base_vn(ins):
    """Lower bound on the run's starting absolute value number."""
    b=0
    for i,(off,op,L,args) in enumerate(ins):
        if op in (0x0900,0x0D00,0x1140,0x1980): continue   # constants take no operands
        for k,a in enumerate(args):
            if is_imm(op, k): continue          # slot indices and masks are not values
            b=max(b, a-i+1)
    return b

def show(d, start, count, S=None, label=''):
    ins,end = instrs(d,start,count)
    if S is None: S=base_vn(ins)
    print(f'  {label}run 0x{start:X}..0x{end:X}, {count} instructions, base value number v{S}')
    for i,(off,op,L,args) in enumerate(ins):
        if op in (0x0900,0x0D00):
            fo=off+(2 if op==0x0900 else 4)
            txt=f'= {struct.unpack_from("<f",d,fo)[0]:.9g}'
        elif op in (0x1140,0x1980):
            k=2 if op==0x1140 else 3
            txt='= '+', '.join(f'{v:.6g}' for v in struct.unpack_from('<%df'%k,d,off+2))
        else:
            txt='('+', '.join(f'v{a}' for a in args)+')'
        print(f'    0x{off:06X}  {op:04X}  v{S+i:<5} {NAME.get(op,"?"):<8} {txt}')
    return end
