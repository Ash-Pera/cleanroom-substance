#!/usr/bin/env python3
"""Catalogue every opcode in the corpus.

Decoding is exact (length = (op>>10)+1), but a run that STARTS at the wrong offset
decodes operand tokens as opcodes and invents vocabulary. Two filters remove that:

  * long runs only - a mis-started run rarely survives many instructions
  * operand validity - value numbering is contiguous, so with the run's base number S
    recovered from the operand bound, instruction i holds value S+i and every operand
    must be < S+i. Mis-started runs violate this almost immediately.

Field decode:  bits 15-10 operand-token count | 9-8 type | 7-6 components-1 | 5-0 op id
"""
import collections, glob, os, struct, sys
import code_region, runs

MIN_RUN = 10
# only the twelve CONFIRMED constants carry an immediate instead of operands; every
# other opcode - including any other op-id 0x00 - must pass the operand-validity test
CONSTS = {0x0900,0x0D00,0x1140,0x1540,0x1980,0x1D80,0x21C0,0x25C0,
          0x0A00,0x0E00,0x1240,0x1640}
TYPE = {0:'bool', 1:'float', 2:'int', 3:'t3'}

NAMES = {  # semantics established elsewhere in FORMAT-NOTES.md
 (1,0x00):'const', (2,0x00):'const', (1,0x02):'ref', (2,0x02):'ref',
 (1,0x12):'add', (1,0x13):'sub', (1,0x14):'mul', (1,0x15):'div', (1,0x18):'dot',
 (2,0x12):'add', (2,0x13):'sub', (2,0x14):'mul', (2,0x15):'div',
 (1,0x10):'extract', (2,0x10):'extract', (1,0x0D):'construct', (2,0x0D):'construct',
 (1,0x28):'sqrt', (1,0x29):'ln', (1,0x2B):'exp2', (1,0x09):'select', (2,0x09):'select',
}

def valid_run(d, st, cnt):
    ins,_ = runs.instrs(d, st, cnt)
    S = runs.base_vn(ins)
    for i,(off,op,L,args) in enumerate(ins):
        if op in CONSTS:
            continue                      # immediate payload, not operands
        for a in args:
            if a >= S+i: return None
    return ins

def scan(paths):
    freq=collections.Counter(); files=collections.defaultdict(set)
    raw=collections.Counter(); nrun=0; nkept=0
    for p in paths:
        key=os.path.basename(os.path.dirname(p.split('/x_')[0]+'/x_'+p.split('/x_')[1].split('/')[0])) \
            if '/x_' in p else p
        key = 'x_'+p.split('/x_')[1].split('/')[0] if '/x_' in p else p
        try: d,spans,r = code_region.code_spans(p)
        except Exception: continue
        for lo,hi in spans:
            for st,cnt,blk in runs.runs(d,lo,hi):
                nrun+=1
                for _,op,_,_ in runs.instrs(d,st,cnt)[0]: raw[op]+=1
                if cnt < MIN_RUN: continue
                ins = valid_run(d,st,cnt)
                if ins is None: continue
                nkept+=1
                for off,op,L,args in ins:
                    freq[op]+=1; files[op].add(key)
    return freq, files, raw, nrun, nkept

if __name__=='__main__':
    paths=[]
    for pat in ('tiny/x_*','tiny2/x_*','pairs/x_*','pairs2/x_*','pairs3/x_*','corpus/x_*','x_*'):
        for xd in glob.glob(pat):
            a=glob.glob(os.path.join(xd,'**','*.sbsasm'),recursive=True)
            if a: paths.append((os.path.basename(xd),a[0]))
    u=[p for _,p in sorted(dict(paths).items())]
    freq,files,raw,nrun,nkept = scan(u)
    tot=sum(freq.values())
    keep={op:c for op,c in freq.items() if len(files[op])>=3}
    print(f'specimens                 : {len(u)}')
    print(f'runs seen / kept          : {nrun} / {nkept}')
    print(f'instructions in kept runs : {tot}')
    print(f'distinct opcodes, raw     : {len(raw)}')
    print(f'distinct, validity-filtered: {len(freq)}')
    print(f'distinct, in >=3 specimens : {len(keep)}\n')
    import json; json.dump({hex(k):[v,len(files[k])] for k,v in sorted(keep.items())},
                           open('catalogue.json','w'), indent=0)
    print(f'{"opcode":>7} {"tok":>4} {"type":>6} {"c":>2} {"id":>5} {"count":>10} {"%":>6} {"files":>6}  name')
    for op,c in sorted(keep.items(), key=lambda z:-z[1]):
        t=(op>>8)&3; cm=((op>>6)&3)+1; i=op&0x3F
        print(f' 0x{op:04X} {(op>>10)+1:>4} {TYPE[t]:>6} {cm:>2} 0x{i:02X} {c:>10} '
              f'{100.0*c/tot:>6.2f} {len(files[op]):>6}  {NAMES.get((t,i),"")}')
