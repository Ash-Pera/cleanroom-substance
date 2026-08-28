#!/usr/bin/env python3
"""Parse the .sbs PIXEL graph (compNodes) into a DAG.

Both .sbs serialisations are handled: a value may appear as a direct attribute
(<x v="1"/>) or nested (<x><value v="1"/></x>). rootnode, connRef, comptype and path all
use the nested form for a substantial share of the corpus.
"""
import re

GRAPH = re.compile(r'<graph>(.*?)</graph>', re.S)
NODE  = re.compile(r'<compNode>(.*?)</compNode>', re.S)
UID   = re.compile(r'<uid(?: v="(\d+)"/>|><value v="(\d+)"/></uid>)')
FILT  = re.compile(r'<filter v="([^"]+)"/>')
CREF  = re.compile(r'<connRef(?: v="(\d+)"/>|><value v="(\d+)"/></connRef>)')
CT    = re.compile(r'<comptype(?: v="(\d+)"/>|><value v="(\d+)"/></comptype>)')
INST  = re.compile(r'<compInstance>')
OBR   = re.compile(r'<compOutputBridge>')


def graphs(text):
    out = []
    for g in GRAPH.findall(text):
        nodes = {}
        for body in NODE.findall(g):
            m = UID.search(body)
            if not m:
                continue
            uid = m.group(1) or m.group(2)
            f = FILT.search(body)
            if f:
                kind = f.group(1)
            elif INST.search(body):
                kind = 'instance'
            elif OBR.search(body):
                kind = 'output'
            else:
                kind = 'other'
            ct = CT.search(body)
            chan = (ct.group(1) or ct.group(2)) if ct else None
            refs = [(a or b) for a, b in CREF.findall(body)]
            nodes[uid] = (kind, chan or '?', refs)
        if nodes:
            out.append(nodes)
    return out


def topo(nodes):
    """uids in dependency order: a node's inputs precede it."""
    seen, order = set(), []

    def visit(u, depth=0):
        if u in seen or u not in nodes or depth > 64:
            return
        seen.add(u)
        for r in nodes[u][2]:
            visit(r, depth + 1)
        order.append(u)

    for u in nodes:
        visit(u)
    return order
