#!/usr/bin/env python3
"""Run the structural graph matcher over every .sbs/.sbsar pair for a list of targets."""
import collections, glob, os, sys
import sbsgraph, code_region, match_graph

TARGETS=['min','max','neg','abs','lerp','mod','ceil','floor','cartesian','sin','cos',
         'passthrough','iswizzle1','toint1','toint2','tofloat','tofloat2','rand',
         'exp','log2','pow2','samplelum','mulscalar','dot','sqrt','instance']

def pairs(dirs):
    out=[]
    for dn in dirs:
        for f in sorted(glob.glob(f'{dn}/*.sbs')):
            base=os.path.basename(f)[:-4]
            asm=None
            for c in glob.glob(os.path.join(dn,'x_'+base+'*')):
                a=glob.glob(os.path.join(c,'**','*.sbsasm'),recursive=True)
                if a: asm=a[0]; break
            if asm: out.append((f,asm))
    return out

def run(P, targets=TARGETS, maxn=16):
    hits=collections.defaultdict(collections.Counter)
    files=collections.defaultdict(set)
    for f,a in P:
        try: d,spans,r=code_region.code_spans(a)
        except Exception: continue
        for g in sbsgraph.graphs(f):
            h=sbsgraph.live_hist(g); n=sum(h.values())
            if not (3<=n<=maxn): continue
            for t in targets:
                if t not in h: continue
                for op in match_graph.scan(g,d,spans,t):
                    hits[t][op]+=1; files[t].add(os.path.basename(f))
    return hits, files
