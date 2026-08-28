#!/usr/bin/env python3
"""Correlate .sbs function-graph node names against .sbsasm opcode counts.

The .sbs XML source names every node of every function graph (`<function v="mul"/>`).
The .sbsar built from it contains the compiled form. Counting both per file and
correlating across the paired corpus maps names to opcodes with no guesswork.
"""
import collections, glob, math, os, re, struct, sys
import code_region, runs

CONSTS = {0x0900,0x0D00,0x1140,0x1540,0x1980,0x1D80,0x21C0,0x25C0,
          0x0A00,0x0E00,0x1240,0x1640}
MIN_RUN = 6

def opcode_counts(path):
    c=collections.Counter()
    try: d,spans,r = code_region.code_spans(path)
    except Exception: return c
    for lo,hi in spans:
        for st,cnt,blk in runs.runs(d,lo,hi):
            if cnt < MIN_RUN: continue
            ins,_ = runs.instrs(d,st,cnt)
            S = runs.base_vn(ins); ok=True
            for i,(off,op,L,args) in enumerate(ins):
                if op in CONSTS: continue
                if any(a >= S+i for a in args): ok=False; break
            if not ok: continue
            for off,op,L,args in ins: c[op]+=1
    return c

def pairs():
    """(name, function-name counter, opcode counter) for each matched .sbs/.sbsar pair."""
    out=[]
    for f in sorted(glob.glob('pairs*/*.sbs')):
        s=open(f, errors='ignore').read()
        fc=collections.Counter(re.findall(r'<function v="([^"]+)"/>', s))
        if not fc: continue
        base=os.path.basename(f)[:-4]; dirn=os.path.dirname(f)
        cands=glob.glob(os.path.join(dirn, 'x_'+base+'*'))
        asm=None
        for c in cands:
            a=glob.glob(os.path.join(c,'**','*.sbsasm'), recursive=True)
            if a: asm=a[0]; break
        if not asm: continue
        oc=opcode_counts(asm)
        if oc: out.append((base, fc, oc))
    return out

def pearson(x, y):
    n=len(x)
    if n<4: return 0.0
    mx=sum(x)/n; my=sum(y)/n
    sx=math.sqrt(sum((v-mx)**2 for v in x)); sy=math.sqrt(sum((v-my)**2 for v in y))
    if sx==0 or sy==0: return 0.0
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/(sx*sy)
