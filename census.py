#!/usr/bin/env python3
"""Rank undecoded opcodes by how much decoding they block.

Backward DP over each code span: R[off] = bytes of clean decode starting at off.
A run ends at the first token that is not a known opcode; that token is the
"blocker". Weighting blockers by the run length that reaches them ranks opcodes by
how much of the stream they gate, which is what matters -- not raw frequency.
"""
import collections, glob, os, struct, sys

from isa import LEN   # structural rule: length = (opcode>>10)+1

def spans_of(path):
    import code_region
    return code_region.code_spans(path)

def census(paths):
    blockers = collections.Counter()   # weighted by reaching-run length
    freq     = collections.Counter()   # raw token frequency at run-reachable offsets
    cov = tot = 0
    for p in paths:
        try:
            d, spans, r = spans_of(p)
        except Exception:
            continue
        for lo, hi in spans:
            n = hi - lo
            if n <= 0: continue
            tot += n
            R = [0]*(n//2 + 2)
            B = [None]*(n//2 + 2)
            for i in range(n//2 - 1, -1, -1):
                off = lo + 2*i
                if off + 2 > len(d): continue
                op = struct.unpack_from('<H', d, off)[0]
                L = LEN.get(op)
                if L is None:
                    R[i], B[i] = 0, op
                else:
                    j = i + L
                    if j <= n//2:
                        R[i] = 2*L + R[j]; B[i] = B[j]
                    else:
                        R[i], B[i] = 0, op
            # walk maximal runs greedily from the span start
            i = 0
            while i < n//2:
                if R[i] > 0:
                    blockers[B[i]] += R[i]
                    freq[B[i]] += 1
                    cov += R[i]
                    i += R[i]//2
                else:
                    i += 1
    return blockers, freq, cov, tot

if __name__ == '__main__':
    paths=[]
    for pat in ('tiny/x_*','tiny2/x_*','pairs/x_*','pairs2/x_*','pairs3/x_*','corpus/x_*','x_*'):
        for xd in glob.glob(pat):
            a=glob.glob(os.path.join(xd,'**','*.sbsasm'),recursive=True)
            if a: paths.append((xd,a[0]))
    seen=set(); u=[]
    for xd,p in paths:
        k=os.path.basename(xd)          # the x_<name> dir, NOT the nested 0000/
        if k not in seen: seen.add(k); u.append(p)
    b,f,cov,tot = census(u)
    print(f'specimens scanned      : {len(u)}')
    print(f'code bytes             : {tot}')
    print(f'covered by known table : {cov} ({100.0*cov/max(tot,1):.1f}%)\n')
    print('top blockers (bytes of clean decode gated / times hit):')
    for op, w in b.most_common(25):
        print(f'   0x{op:04X}   {w:>9} bytes   {f[op]:>6} runs')
