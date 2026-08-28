#!/usr/bin/env python3
"""Parse a .sbs into its individual function graphs.

Each <dynamicValue> is one function graph: a set of <paramNode>s plus a <rootnode>
naming the output. Graphs are the right unit for alignment - a large package may still
contain a small graph that isolates one unknown node type.
"""
import re, collections

NODE_RE = re.compile(r'<paramNode>(.*?)</paramNode>', re.S)
# The .sbs format has TWO serialisations for element values: a direct attribute
# (<x v="1"/>) and a nested value element (<x><value v="1"/></x>). `rootnode` uses the
# nested form 27% of the time and `connRef` 5.6%, so patterns must accept both or
# live-node analysis silently degrades to "every node is live".
UID_RE  = re.compile(r'<uid(?: v="(\d+)"/>|><value v="(\d+)"/></uid>)')
FN_RE   = re.compile(r'<function v="([^"]+)"/>')
CONN_RE = re.compile(r'<connRef(?: v="(\d+)"/>|><value v="(\d+)"/></connRef>)')
ROOT_RE = re.compile(r'<rootnode(?: v="(\d+)"/>|><value v="(\d+)"/></rootnode>)')

def graphs(path):
    s=open(path, errors='ignore').read()
    out=[]
    for m in re.finditer(r'<dynamicValue>(.*?)</dynamicValue>', s, re.S):
        blk=m.group(1)
        nodes={}
        for nm in NODE_RE.finditer(blk):
            body=nm.group(1)
            u=UID_RE.search(body); f=FN_RE.search(body)
            if not u: continue
            uid=u.group(1) or u.group(2)
            conns=[(a or b) for a,b in CONN_RE.findall(body)]
            nodes[uid]=(f.group(1) if f else '?', [('in', v) for v in conns])
        if not nodes: continue
        r=ROOT_RE.search(blk)
        out.append({'nodes':nodes, 'root':(r.group(1) or r.group(2)) if r else None,
                    'hist':collections.Counter(f for f,_ in nodes.values())})
    return out

def live(g):
    """Nodes reachable from the root - the compiler drops the rest."""
    if not g['root'] or g['root'] not in g['nodes']: return set(g['nodes'])
    seen=set(); stack=[g['root']]
    while stack:
        u=stack.pop()
        if u in seen or u not in g['nodes']: continue
        seen.add(u)
        for _,v in g['nodes'][u][1]: stack.append(v)
    return seen

def live_hist(g):
    L=live(g)
    return collections.Counter(g['nodes'][u][0] for u in L)
