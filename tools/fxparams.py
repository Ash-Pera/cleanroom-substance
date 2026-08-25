#!/usr/bin/env python3
"""Re-derive the FX-Map table-entry parameter names, from sources, with the controls.

`sbsasm.FX_PARAM_BITS` says which parameter each bit of an FX table entry's tag names.
That table is not a reading of the format specification -- there isn't one -- it is the
output of the procedure in this file, run against the permitted paired sources. Anything
stated as a percentage in `FX_PARAM_BITS`' comment is printed by `main()` below, so the
claim and the check cannot drift apart the way the provenance rule's "38 excluded" did
before tools/provenance.py existed.

THE PROCEDURE, in one paragraph. A `.sbs` FX-Map declares its `paramset` nodes' parameters
by name, each holding either a literal or a `<dynamicValue>` function graph. The graph's
`const_*` nodes carry literals that survive compilation as program immediates. So take a
source node with k dynamic parameters and a compiled entry with k program slots, and ask
which BIJECTIONS of names onto slots put every declared literal inside the program that
slot addresses. Where exactly one bijection survives, the binding is forced -- by the
literals, not by name similarity or by assuming the compiler preserves declaration order,
which it does not (`Bruno_Caustics_Generator` declares patternsize before opacity and
compiles opacity first).

WHAT MAKES IT EVIDENCE. Three things, and the file reports all three:

  * bijections that are NOT unique are counted and discarded, not resolved by preference;
  * every (tag, slot) is checked for two source nodes disagreeing about its name;
  * `predict_tags()` runs the resulting map BACKWARDS -- source parameter set to expected
    tag bits -- against a shuffled-map control, which is a test the derivation cannot pass
    by construction.

WHAT IT CANNOT SETTLE, stated here because the numbers look better than the evidence is.
Only 8 permitted sources in the corpus contain an FX-Map at all, and between them they
exercise three tags. `branchoffset` rests on ONE of those files. See `FX_PARAM_BITS`.
"""
import collections
import itertools
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import disasm                                                        # noqa: E402
import provenance                                                    # noqa: E402
from containment import sbsasm_for                                   # noqa: E402
from sbsasm import Assembly, FX_PARAM_BITS, fx_entry_layout          # noqa: E402

# `.sbs` serialises every value two ways -- `<x v="1"/>` and `<x><value v="1"/></x>` --
# and 3 of the 8 permitted FX sources use the nested form for ALL of theirs. Reading only
# the direct form reports those three as declaring no constants, which is what made this
# look underdetermined on the first pass. tools/pixelgraph.py's docstring has recorded the
# two forms all along; this is the third module to be caught by it.
_ALT = r'<%s(?: v="([^"]*)"/>|><value v="([^"]*)"/></%s>)'
GD = re.compile(r'<paramsGraphData>(.*?)</paramsGraphData>', re.S)
TY = re.compile(_ALT % ('type', 'type'))
PA = re.compile(r'<parameter><name(?: v="([^"]*)"/>|><value v="([^"]*)"/></name>)'
                r'(.*?)</parameter>', re.S)
_CVT = 'Float1|Float2|Float3|Float4|Int32|Int1|Bool'
CV = re.compile(r'<constantValue(?:%s)(?: v="([^"]*)"/>'
                r'|><value v="([^"]*)"/></constantValue(?:%s)>)' % (_CVT, _CVT))


def _num(v):
    """A literal's canonical string, rounded through float32 as the binary stores it."""
    return '%.6g' % struct.unpack('<f', struct.pack('<f', v))[0]


def declared_literals(param_body):
    out = set()
    for a, b in CV.findall(param_body):
        for tok in (a or b).split():
            try:
                out.add(_num(float(tok)))
            except ValueError:
                pass
    return out


def paramset_nodes(text):
    """[{name: literals or None}] per `paramset` node; None means the value is a graph."""
    out = []
    for body in GD.findall(text):
        m = TY.search(body)
        if not m or (m.group(1) or m.group(2)) != 'paramset':
            continue
        node = {}
        for n1, n2, pv in PA.findall(body):
            node[n1 or n2] = (declared_literals(pv) if '<dynamicValue>' in pv else None)
        out.append(node)
    return out


def program_literals(data, ptr, hi):
    """Every immediate the compiled program's constant instructions carry."""
    out = set()
    for _k, addr, op, toks in disasm.decode(data, ptr, hi):
        _n, ty, _c, oid = disasm.fields(op)
        if oid != 0x00:
            continue
        raw = disasm.immediate(addr, toks)
        for i in range(0, len(raw) - 3, 4):
            out.add(_num(struct.unpack_from('<f', raw, i)[0]) if ty == 1
                    else '%d' % struct.unpack_from('<i', raw, i)[0])
    return out


def compiled_entries(asmf):
    """{(tag, offset): {slot: literals}} over every FX table entry with programs."""
    a = Assembly(asmf)
    d, lo, hi = a.data, a.body_lo, a.body_hi
    out = collections.defaultdict(dict)
    for r in a.records:
        if r.filter_id != 4:
            continue
        seen = set()
        for kind, off, tag, _p in r.fx_walk():
            if kind != 'entry' or off in seen:
                continue
            seen.add(off)
            for sl, _nm, how in fx_entry_layout(tag):
                if how != 'program' or off + 4 * sl + 4 > hi:
                    continue
                pv = struct.unpack_from('<I', d, off + 4 * sl)[0] + 52
                if lo < pv < hi and a.program_span(pv, hi):
                    out[(tag, off)][sl] = program_literals(d, pv, hi)
    return dict(out)


def fx_sources():
    """(relpath, source text, assembly path) for every PERMITTED paired source with an FX-Map."""
    for rel in provenance.audit()[2]:
        full = os.path.join(provenance.ROOT, rel)
        text = open(full, encoding='utf-8', errors='replace').read()
        if 'paramsGraphData' not in text:
            continue
        asmf = sbsasm_for(full)
        if asmf:
            yield rel, text, asmf


def bind():
    """{(tag, slot): Counter(name)} from UNIQUE bijections only, plus the tallies."""
    votes = collections.defaultdict(collections.Counter)
    stats = collections.Counter()
    for _rel, text, asmf in fx_sources():
        ents = compiled_entries(asmf)
        for node in paramset_nodes(text):
            decl = {n: v for n, v in node.items() if v is not None}
            if not decl:
                continue
            names = sorted(decl)
            for (tag, _off), comp in ents.items():
                if len(comp) != len(names):
                    continue
                slots = sorted(comp)
                good = [p for p in itertools.permutations(slots)
                        if all(decl[n] <= comp[s] for n, s in zip(names, p))]
                if not good:
                    stats['no valid bijection'] += 1
                elif len(good) == 1:
                    stats['exactly one valid bijection'] += 1
                    for n, s in zip(names, good[0]):
                        votes[(tag, s)][n] += 1
                else:
                    stats['several valid bijections'] += 1
    return votes, stats


def predict_tags(bitmap):
    """Run the map backwards: source parameter set -> expected tag bits. (hits, total)."""
    hit = tot = 0
    for _rel, text, asmf in fx_sources():
        a = Assembly(asmf)
        highs = {tag >> 20 for r in a.records if r.filter_id == 4
                 for kind, _o, tag, _p in r.fx_walk()
                 if kind == 'entry' and (tag & 0xF) == 8}
        for node in paramset_nodes(text):
            dyn = {n for n, v in node.items() if v is not None}
            if not dyn:
                continue
            tot += 1
            want = 0
            for n in dyn:
                if n in bitmap:
                    want |= 1 << (bitmap[n] - 20)
            hit += want in highs
    return hit, tot


def main():
    names = {n: b for b, n, _w in FX_PARAM_BITS if n}
    votes, stats = bind()
    print('CONTAINMENT BINDING, over the permitted paired sources')
    for k, v in stats.most_common():
        print('   %-32s %6d' % (k, v))
    print()
    print('   (tag, slot) -> name        [published bit]')
    conflicts = 0
    for (tag, sl) in sorted(votes):
        c = votes[(tag, sl)]
        if len(c) > 1:
            conflicts += 1
        top, n = c.most_common(1)[0]
        want = dict((s, nm) for s, nm, _k in fx_entry_layout(tag))
        agree = 'ok' if want.get(sl) == top else 'DISAGREES WITH FX_PARAM_BITS (%s)' % want.get(sl)
        print('   0x%08X slot %-2d  %-18s n=%-5d %s'
              % (tag, sl, top, n, agree if len(c) == 1 else 'CONFLICT %s' % c.most_common()))
    print()
    print('   (tag, slot) pairs bound:   %d' % len(votes))
    print('   pairs two nodes disagree about: %d' % conflicts)

    print()
    print('BACKWARDS TEST -- predict the tag from the source parameter set')
    hit, tot = predict_tags(names)
    print('   published map                          %d/%d  (%.1f%%)'
          % (hit, tot, 100.0 * hit / max(tot, 1)))
    import random
    random.seed(5)
    ns, bs = list(names), list(names.values())
    acc = 0
    trials = 200
    for _ in range(trials):
        random.shuffle(bs)
        acc += predict_tags(dict(zip(ns, bs)))[0]
    print('   CONTROL, shuffled name->bit map        %.1f%%'
          % (100.0 * acc / max(trials * tot, 1)))


if __name__ == '__main__':
    main()
