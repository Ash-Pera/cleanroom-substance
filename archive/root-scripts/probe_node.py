#!/usr/bin/env python3
"""Find the compiled run for graphs isolating one unknown node type, with tolerance.

Looser than solve.py: allows the run to be a few instructions off the live-node count
(dead code, compiler temporaries) and reports the distribution of unexplained op-ids
rather than demanding a single perfect residual.
"""
import collections, glob, os, sys
import code_region, runs, sbsgraph
from solve import NAME2OP, GETNAMES, GET, KNOWN

def probe(target, pairs, slack=2, maxn=22):
    votes=collections.Counter(); opv=collections.Counter(); seen=0
    for f,a in pairs:
        gs=[g for g in sbsgraph.graphs(f)]
        if not any(target in sbsgraph.live_hist(g) for g in gs): continue
        try: d,spans,r=code_region.code_spans(a)
        except Exception: continue
        R=[]
        for lo,hi in spans:
            for st,cnt,blk in runs.runs(d,lo,hi):
                if 2<=cnt<=maxn+slack:
                    ins,_=runs.instrs(d,st,cnt)
                    R.append((cnt,collections.Counter(op&0x3F for _,op,_,_ in ins),ins))
        for g in gs:
            h=sbsgraph.live_hist(g); n=sum(h.values())
            if not (2<=n<=maxn) or target not in h: continue
            unk=[k for k in h if k not in KNOWN]
            if unk!=[target]: continue
            seen+=1
            pred=collections.Counter(); ngets=0
            for name,c in h.items():
                if name==target: continue
                if name in GETNAMES: ngets+=c
                else: pred[NAME2OP[name]]+=c
            for cnt,oc,ins in R:
                if abs(cnt-n)>slack: continue
                if abs(sum(oc[k] for k in GET)-ngets)>slack: continue
                resid=collections.Counter()
                for k,c in oc.items():
                    if k in GET: continue
                    dd=c-pred.get(k,0)
                    if dd>0: resid[k]+=dd
                if len(resid)==1:
                    k=list(resid)[0]
                    votes[k]+=1
                    for _,op,_,_ in ins:
                        if (op&0x3F)==k: opv[op]+=1
    return seen, votes, opv
