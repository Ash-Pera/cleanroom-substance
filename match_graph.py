#!/usr/bin/env python3
"""Locate a .sbs function graph inside the compiled instruction stream.

A graph compiles to a contiguous window of instructions in topological order, not to a
whole maximal run, so multiset matching over runs fails. This does structural matching:
find a bijection between graph nodes and window positions that preserves BOTH the op-id
labels (for known node types) and every dataflow edge (an edge u->v requires the
instruction for u to carry an operand equal to the value number of the instruction for v).

The unknown node type is a wildcard; whatever op-id lands on it is the answer.
"""
import collections
import runs
from solve import NAME2OP, GETNAMES, GET, KNOWN

def window_edges(ins, base):
    """value number -> position, for operands that reference inside the window."""
    pos={base+i: i for i in range(len(ins))}
    ops=[]
    for i,(off,op,L,args) in enumerate(ins):
        ops.append([pos[a] for k,a in enumerate(args)
                    if not runs.is_imm(op,k) and a in pos and pos[a]<i])
    return ops

def compatible(nodetype, op):
    oid=op&0x3F
    if nodetype in GETNAMES: return oid in GET
    if nodetype in NAME2OP:  return oid==NAME2OP[nodetype]
    return True                      # unknown node: wildcard

def match(gnodes, gedges, ins, base):
    """gnodes: [type], gedges: [[input positions]] -> mapping node->window index or None."""
    n=len(gnodes); m=len(ins)
    if n!=m: return None
    wedges=window_edges(ins, base)
    assign={}; used=[False]*m
    def bt(k):
        if k==n: return True
        for j in range(m):
            if used[j] or not compatible(gnodes[k], ins[j][1]): continue
            ok=True
            for u in gedges[k]:
                if u in assign and assign[u] not in wedges[j]: ok=False; break
            if ok:
                for a,b in assign.items():
                    if k in gedges[a] and j not in wedges[b]: ok=False; break
            if ok:
                assign[k]=j; used[j]=True
                if bt(k+1): return True
                del assign[k]; used[j]=False
        return False
    order=sorted(range(n), key=lambda k: (gnodes[k] not in KNOWN, -len(gedges[k])))
    gnodes=[gnodes[i] for i in order]
    remap={o:i for i,o in enumerate(order)}
    gedges=[[remap[u] for u in gedges[o]] for o in order]
    if not bt(0): return None
    return {order[k]: v for k,v in assign.items()}

def scan(graph, d, spans, target):
    """Yield the opcode that lands on the `target` node, over all matching windows."""
    import sbsgraph
    L=sbsgraph.live(graph)
    ids=[u for u in graph['nodes'] if u in L]
    idx={u:i for i,u in enumerate(ids)}
    gnodes=[graph['nodes'][u][0] for u in ids]
    gedges=[[idx[v] for _,v in graph['nodes'][u][1] if v in idx] for u in ids]
    n=len(ids)
    tpos=[i for i,t in enumerate(gnodes) if t==target]
    out=[]
    for lo,hi in spans:
        for st,cnt,blk in runs.runs(d,lo,hi):
            if cnt<n: continue
            ins,_=runs.instrs(d,st,cnt)
            base=runs.base_vn(ins)
            for s in range(cnt-n+1):
                w=ins[s:s+n]
                mp=match(gnodes,gedges,w,base+s)
                if mp:
                    for tp in tpos: out.append(w[mp[tp]][1])
    return out
