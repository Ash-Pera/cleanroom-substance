#!/usr/bin/env python3
"""Constrain which record produces each graph output, without evaluating pixels.

The binary stores no output->record association (see FORMAT-NOTES.md). But the manifest
publishes, for every input, the set of outputs it alters; and the bytecode says which
records read which input uid. That gives two constraints per (parameter, output) pair:

    p alters o        =>  o's record is downstream of some record reading p
    p does not alter o=>  o's record is downstream of NO record reading p

The second is the useful one: it eliminates candidates rather than merely admitting them.
"""
import collections
import struct
import xml.etree.ElementTree as ET

import disasm
from sbsasm import Assembly


def readers(asm):
    """input uid -> set of record indices whose programs reference it."""
    out = collections.defaultdict(set)
    for r in asm.records:
        par = r.parameter
        if not par or par[0] != 'program':
            continue
        for _, _, op, toks in disasm.decode(asm.data, par[1], asm.body_hi):
            if (op & 0x3F) == 0x02 and len(toks) >= 2:
                out[toks[0] | (toks[1] << 16)].add(r.index)
    return out


def forward(asm):
    """record index -> records that consume it, directly."""
    fwd = collections.defaultdict(set)
    for r in asm.records:
        for e in r.edges:
            if e:
                fwd[e].add(r.index)
    return fwd


def closure(fwd, seeds):
    seen = set(seeds)
    st = list(seeds)
    while st:
        for v in fwd.get(st.pop(), ()):
            if v not in seen:
                seen.add(v)
                st.append(v)
    return seen


def candidates(asm, xml_path):
    """output uid -> set of record indices that could produce it."""
    root = ET.parse(xml_path).getroot()
    rd, fwd = readers(asm), forward(asm)
    allrec = {r.index for r in asm.records}
    result = {}
    for g in root.findall('graphs/graph'):
        outs = [o.get('uid') for o in g.findall('outputs/output')]
        alt = {}
        for inp in g.findall('inputs/input'):
            uid = int(inp.get('uid'))
            s = {x for x in (inp.get('alteroutputs') or '').split(',') if x}
            if s and uid in rd:
                alt[uid] = s
        cl = {uid: closure(fwd, rd[uid]) for uid in alt}
        for o in outs:
            keep = set(allrec)
            for uid, s in alt.items():
                keep &= cl[uid] if o in s else (allrec - cl[uid])
            result[o] = keep
    return result
