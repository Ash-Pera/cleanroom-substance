#!/usr/bin/env python3
"""Iteratively close the opcode-length table.

Each round: census the blockers, infer a length for each, admit only those passing a
strict test on BOTH a training and a held-out split, then repeat.  Admitting opcodes
expands the known set, which un-biases the continuation test for their neighbours --
that is why 0x0517 scored zero everywhere until 0x094D was known.
"""
import glob, os, struct, sys, collections
import code_region, runs, census
from census import LEN
import infer_len

def specimens(limit=300000):
    out=[]
    for pat in ('tiny/x_*','tiny2/x_*','pairs/x_*','pairs2/x_*','pairs3/x_*','corpus/x_*'):
        for xd in glob.glob(pat):
            a=glob.glob(os.path.join(xd,'**','*.sbsasm'),recursive=True)
            if a and os.path.getsize(a[0])<limit: out.append(a[0])
    return sorted(out)

def blockers(paths, topn=40):
    c=collections.Counter()
    for p in paths:
        try: d,spans,r=code_region.code_spans(p)
        except Exception: continue
        for lo,hi in spans:
            for st,cnt,blk in runs.runs(d,lo,hi):
                if blk is not None: c[blk]+=cnt
    return [op for op,_ in c.most_common(topn) if op not in LEN]

def round_(train, hold, verbose=True):
    T=blockers(train)
    if not T: return []
    strain=infer_len.sites_for(train,set(T))
    shold =infer_len.sites_for(hold,set(T))
    added=[]
    for op in T:
        s=strain.get(op,[]); h=shold.get(op,[])
        if len(s)<25: continue
        r=infer_len.infer(s)
        if len(h)>=10:
            rh=infer_len.infer(h)
            if rh[0][1]!=r[0][1]: continue
            if rh[0][0]<0.70: continue
        elif len(h)>0:
            continue
        if r[0][0]>=0.75 and (r[0][0]-r[1][0])>=0.15:
            LEN[op]=r[0][1]; added.append((op,r[0][1],r[0][0],len(s)))
    return added
