#!/usr/bin/env python3
"""Check the output table against the manifest's input-alters-output relation.

This tool used to open by saying the binary stores no output-to-record association, and
tried to *constrain* which record produced each output by elimination. That premise was
wrong: the output table names the record outright, one 8-byte entry per output,
immediately after the record directory. See FORMAT-NOTES.md.

So the job is no longer inference, it is verification, and the manifest supplies an
independent check. A manifest input carries `alteroutputs`, the set of outputs it
affects. If the table is right then, for every input p and output o:

    p alters o        =>  o's record is reachable from some record that reads p
    p does not alter o=>  o's record is NOT reachable from any record reading p

The second is the sharp one - it can fail, and a wrong table would fail it often.

    python3 attribute_outputs.py <file.sbsasm> <manifest.xml>
    python3 attribute_outputs.py --corpus <list-file>
"""
import struct
import collections
import sys
import xml.etree.ElementTree as ET

import disasm
from sbsasm import Assembly


def readers(asm):
    """graph input uid -> set of record indices whose programs reference it.

    Reads EVERY program a record names, not just the main parameter program -- a record
    can carry up to five, and the two-scalar filters routinely carry two. It also decodes
    the uid through `disasm.uid`, which removes the alignment pad; splicing the operand
    tokens directly yields a uid built from two different words.
    """
    out = collections.defaultdict(set)
    for r in asm.records:
        for q in r.programs:
            for _, addr, op, toks in disasm.decode(asm.data, q, asm.body_hi):
                if (op & 0x3F) == 0x02:
                    u = disasm.uid(addr, toks)
                    if u is not None:
                        out[u].add(r.index)
    return out


def forward(asm):
    """record index -> records that consume it directly.

    Image edges are not the only dependency. `0x06` writes a value into the per-package
    cache and `0x03` reads it back by index, from a different record - so a reader depends
    on the writer with no edge between them, and a walk over edges alone cannot see it.

    Adding those, over the corpus:

        edges only            28,470 / 28,896   98.53%   142 unreachable, 6 spurious
        + cache write->read   28,554 / 28,896   98.82%   131 unreachable, 6 spurious

    6,888 cache edges. The improvement is in the loose direction and the SHARP test - an
    output reachable from an input the manifest says does not alter it - does not move,
    which is what distinguishes this from adding the fx node programs as readers: that
    also fixed 11, and took the sharp violations from 426 to 512.
    """
    fwd = collections.defaultdict(set)
    for r in asm.records:
        for e in r.edges:
            if e is not None:
                fwd[e].add(r.index)
    writer, reader = {}, collections.defaultdict(set)
    for r in asm.records:
        for q in r.programs:
            try:
                ins = list(disasm.decode(asm.data, q, asm.body_hi))
            except Exception:
                continue
            for _, _addr, op, toks in ins:
                oid = op & 0x3F
                if oid == 0x06 and len(toks) > 1:
                    writer.setdefault(toks[1], r.index)
                elif oid == 0x03 and toks:
                    reader[toks[0]].add(r.index)
    for idx, who in reader.items():
        w = writer.get(idx)
        if w is not None:
            fwd[w] |= who
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


def check(asm, xml_path):
    """(agreements, violations, untested) for one specimen."""
    root = ET.parse(xml_path).getroot()
    rd, fwd = readers(asm), forward(asm)
    table = {uid: idx for uid, _, _, idx in asm.outputs() if uid is not None}
    ok = bad = skip = 0
    vac_ok = vac_bad = 0
    detail = []
    # An input of type 8 is the graph's output size. Its rows are near-vacuous: it is read
    # by a median 73% of a file's records, so its forward closure is most of the graph, and
    # the manifest says it alters 96.1% of outputs. Both sides say "everything", so those
    # rows agree almost by construction and cannot fail the way the others can. Counted
    # separately rather than folded into the headline.
    intype = {u: t for t, u, v in (asm.header.get('inputs') or [])}
    for g in root.iter('graph'):
        for inp in g.iter('input'):
            uid = inp.get('uid')
            if uid is None:
                continue
            uid = int(uid)
            alters = {x for x in (inp.get('alteroutputs') or '').split(',') if x}
            if uid not in rd:
                skip += 1
                continue
            cl = closure(fwd, rd[uid])
            for o in g.iter('output'):
                ouid = o.get('uid')
                if ouid is None or int(ouid) not in table:
                    continue
                rec = table[int(ouid)]
                reach = rec in cl
                if intype.get(uid) == 8:
                    if (ouid in alters) == reach: vac_ok += 1
                    else: vac_bad += 1
                    continue
                if (ouid in alters) == reach:
                    ok += 1
                else:
                    bad += 1
                    if len(detail) < 5:
                        detail.append((uid, ouid, 'alters but unreachable'
                                       if ouid in alters else 'reachable but does not alter'))
    return ok, bad, skip, detail, vac_ok, vac_bad


def main(argv):
    if len(argv) >= 2 and argv[0] == '--corpus':
        import glob, os
        paths = [l.strip() for l in open(argv[1]) if l.strip()]
        tot = collections.Counter(); files = 0
        unreadable = []
        for p in paths:
            xs = glob.glob(os.path.join(os.path.dirname(p), '*.xml'))
            if not xs:
                continue
            try:
                a = Assembly(p)
                ok, bad, skip, _, v1, v2 = check(a, xs[0])
            except (OSError, ET.ParseError, struct.error) as e:
                # Only what a malformed specimen raises. A bare `except` here swallows a
                # bug in `check` as a smaller file count -- measured, it currently drops
                # exactly 2 files, both the manifests the audit already reports as
                # unparseable, and it would hide anything else just as quietly.
                unreadable.append((p, e))
                continue
            files += 1
            tot['ok'] += ok; tot['bad'] += bad; tot['skip'] += skip
            tot['vac_ok'] += v1; tot['vac_bad'] += v2
        n = tot['ok'] + tot['bad']
        print('specimens checked        : %d' % files)
        if unreadable:
            print('unreadable specimens     : %d' % len(unreadable))
            for _p, _e in unreadable[:4]:
                print('   %-44s %s' % (_p.split('/')[-1][:44], type(_e).__name__))
        print('(input, output) pairs    : %d' % n)
        print('   agree with the table  : %d  (%.2f%%)' % (tot['ok'], 100*tot['ok']/max(n, 1)))
        print('   violations            : %d' % tot['bad'])
        print('   inputs no program reads: %d' % tot['skip'])
        v = tot['vac_ok'] + tot['vac_bad']
        print('output-size rows, counted apart : %d  (%d agree) -- near-vacuous, see check()'
              % (v, tot['vac_ok']))
        return
    a = Assembly(argv[0])
    ok, bad, skip, detail, v1, v2 = check(a, argv[1])
    print('output table:')
    for uid, fmt, gray, idx in a.outputs():
        r = a.records[idx] if 0 <= idx < len(a.records) else None
        print('   uid=%-12s format=%-5s grayscale=%-6s record %-6d %s'
              % (uid, fmt, gray, idx, r.filter_name if r else '?'))
    print('\nmanifest cross-check: %d agree, %d violations, %d inputs unread' % (ok, bad, skip))
    for d in detail:
        print('   input %s vs output %s: %s' % d)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1:])
