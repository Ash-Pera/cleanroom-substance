#!/usr/bin/env python3
"""Expand a .sbs graph's `compInstance` nodes using only graphs defined in the same file.

Inlining is why a source node count rarely matches a binary record count. Two thirds of
instance references point outside the file and cannot be followed with permitted material,
but a third resolve internally and cost nothing to expand.

The goal is not to make a file flat - no file in this corpus becomes flat - but to make
individual *filters* count-exact within a non-flat file. The count-exact criterion stays
self-validating either way: if the expanded source count equals the binary record count,
nothing unexpanded contributed that filter.
"""
import collections
import re

RE_GRAPH = re.compile(r'<graph>')
RE_IDENT = re.compile(r'<identifier v="([^"]+)"/>')
RE_FILTER = re.compile(r'<filter v="([a-z0-9_]+)"')
RE_PATH = re.compile(r'<path v="([^"]+)"')
RE_INB = re.compile(r'<compInputBridge>')


def graphs(text):
    """identifier -> (direct filter counts, list of instance target identifiers or None)."""
    out = {}
    for chunk in text.split('<graph>')[1:]:
        body = chunk.split('</graph>')[0]
        m = RE_IDENT.search(body)
        if not m:
            continue
        counts = collections.Counter()
        targets = []
        for node in body.split('<compNode>')[1:]:
            n = node.split('</compNode>')[0]
            mf = RE_FILTER.search(n)
            if mf:
                counts[mf.group(1)] += 1
                continue
            if RE_INB.search(n):
                counts['bitmap'] += 1          # an input bridge compiles to a bitmap record
                continue
            mp = RE_PATH.search(n)
            if mp:
                p = mp.group(1)
                targets.append(p[7:].split('?')[0].split('/')[-1]
                               if p.startswith('pkg:///') else None)
        out[m.group(1)] = (counts, targets)
    return out


def expand(g, ident, seen=None):
    """(expanded filter counts, whether any instance could not be followed)."""
    if seen is None:
        seen = set()
    if ident in seen or ident not in g:            # recursion guard
        return collections.Counter(), True
    seen = seen | {ident}
    direct, targets = g[ident]
    total = collections.Counter(direct)
    complete = True
    for t in targets:
        if t is None or t not in g:
            complete = False                        # external: contents unknown
            continue
        sub, ok = expand(g, t, seen)
        total.update(sub)
        complete &= ok
    return total, complete


def roots(g):
    """Graphs not instantiated by any other graph in the file.

    Expanding every graph double-counts: a sub-graph's nodes appear once standalone and
    again inside each parent that instantiates it. Only roots should be expanded.
    """
    used = {t for _, targets in g.values() for t in targets if t in g}
    return [k for k in g if k not in used]


def whole_file(text):
    """Filter counts for the file's root graphs, with internal instances expanded."""
    g = graphs(text)
    total = collections.Counter()
    complete = True
    for ident in roots(g):
        c, ok = expand(g, ident)
        total.update(c)
        complete &= ok
    return total, complete, g
