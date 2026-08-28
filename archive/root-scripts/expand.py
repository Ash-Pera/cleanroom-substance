#!/usr/bin/env python3
"""Expand pkg:/// sub-graph instances inside a .sbs, mirroring the compiler's inlining.

A compInstance names a graph by pkg:/// path. When that graph lives in the same .sbs the
reference can be resolved and its nodes counted in place, which is what the compiler does.
Files whose instances all resolve locally become usable ground truth even though they are
not instance-free.
"""
import re, collections

GRAPH = re.compile(r'<graph>(.*?)</graph>', re.S)
IDENT = re.compile(r'<identifier v="([^"]+)"/>')
NODE  = re.compile(r'<compNode>(.*?)</compNode>', re.S)
FILT  = re.compile(r'<filter v="([^"]+)"/>')
CT    = re.compile(r'<comptype v="(\d+)"/>')
INST  = re.compile(r'<compInstance><path v="pkg:///([^"?]+)')

def graphs(text):
    out={}
    for g in GRAPH.findall(text):
        m=IDENT.search(g)
        if m: out[m.group(1)]=g
    return out

def local_counts(body):
    """(filter, comptype) counts and the list of instance targets in one graph body."""
    fc=collections.Counter()
    for n in NODE.findall(body):
        m=FILT.search(n)
        if not m: continue
        ct=CT.search(n)
        fc[(m.group(1), ct.group(1) if ct else '?')]+=1
    return fc, INST.findall(body)

def expand(text, root=None, depth=8):
    """Fully expanded (filter, comptype) counts; returns (counts, unresolved_count)."""
    G=graphs(text)
    memo={}; unresolved=[0]
    def walk(name, d):
        if d<=0 or name not in G: 
            unresolved[0]+=1
            return collections.Counter()
        if (name,d) in memo: return memo[(name,d)]
        fc, insts = local_counts(G[name])
        tot=collections.Counter(fc)
        for t in insts:
            tot += walk(t, d-1)
        memo[(name,d)]=tot
        return tot
    if root is None:
        tot=collections.Counter()
        for name in G: tot += walk(name, depth)
        return tot, unresolved[0]
    return walk(root, depth), unresolved[0]
