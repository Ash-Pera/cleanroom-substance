#!/usr/bin/env python3
"""Full opcode census using the structural length rule.

length = (opcode >> 10) + 1 tokens, for 0x0400 <= opcode < 0x8000.
0x8000+ are 4-aligned records and are exempt.
"""
import glob, os, struct, sys, collections
import code_region, runs, census


def main():
    paths=[]
    for pat in ('tiny/x_*','tiny2/x_*','pairs/x_*','pairs2/x_*','pairs3/x_*','corpus/x_*','x_*'):
        for xd in glob.glob(pat):
            a=glob.glob(os.path.join(xd,'**','*.sbsasm'),recursive=True)
            if a: paths.append((os.path.basename(xd),a[0]))
    u=[p for _,p in sorted(dict(paths).items())]
    freq=collections.Counter(); byfiles=collections.defaultdict(set)
    for p in u:
        try: d,spans,r=code_region.code_spans(p)
        except Exception: continue
        k=os.path.basename(os.path.dirname(os.path.dirname(p)))
        for lo,hi in spans:
            for st,cnt,blk in runs.runs(d,lo,hi):
                if cnt < 4: continue          # ignore short, likely-spurious runs
                ins,_=runs.instrs(d,st,cnt)
                for off,op,L,args in ins:
                    freq[op]+=1; byfiles[op].add(k)
    return freq, byfiles, len(u)

if __name__=='__main__':
    freq,byfiles,n = main()
    tot=sum(freq.values())
    print(f'specimens {n}   instructions decoded {tot}   distinct opcodes {len(freq)}\n')
    print(f'{"opcode":>7} {"len":>4} {"cmp":>4} {"id":>5} {"count":>10} {"%":>6} {"files":>6}')
    for op,c in freq.most_common(45):
        print(f' 0x{op:04X} {(op>>10)+1:>4} {((op>>6)&3)+1:>4} 0x{op&0x3F:02X} '
              f'{c:>10} {100.0*c/tot:>6.2f} {len(byfiles[op]):>6}')
