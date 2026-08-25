#!/usr/bin/env python3
"""Pass/fail checks for the FX-Map decode.

Every claim here was established in FORMAT-NOTES.md with a control, and every check below
can fail if the model regresses. Thresholds sit clearly below the measured value so that
normal corpus drift does not trip them, but a broken walk does.

SKIPS rather than fails when the corpus is absent -- the corpus is not in this repository.

The checks that matter are the ones with a CONTROL in the same function. A number like
"96% of entry tags are in the vocabulary" means nothing on its own; it means something
against the 56.7% the same walk produced before the entry length was known.

WHAT THESE CATCH, measured by mutating the model one table at a time:

    mutation                                caught by
    FX_ENTRY: every stride -> 8             coverage
    FX_ENTRY: drop the table entirely       coverage
    FX_ENTRY: terminal tags become 24       coverage
    FX_ENTRY_PROGS: shift every slot by +1  coverage, entries_read_the_slots
    FX_NODES2: 0x1B child at word 4 not 5   0x1B_branches

The first version of this file caught NONE of them, and the reason is worth keeping. Every
check it had measured purity -- what fraction of yielded tags are in the vocabulary, whether
slot roles are consistent -- and purity IMPROVES when the walk gives up early. Emptying
`FX_ENTRY` makes the walk stop after each record's first entry, which is the one position
established by pointer-following, so every purity number went UP. A test suite that cannot
distinguish "decoding correctly" from "decoding almost nothing" is decoration.

Two fixes made it real: a coverage check (entries and entry programs per record), and
reading the offsets under test FROM the table rather than restating them, since the
hardcoded version validated the constants it had been written with.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import disasm                                                        # noqa: E402
from sbsasm import (Assembly, FX_NODES, FX_NODES2, FX_TAG_LOW16,     # noqa: E402
                    FX_ENTRY, FX_ENTRY_PROGS, FX_NODE_PARAMS, fx_entry_layout)

LIMIT = int(os.environ.get('SBS_FX_FILES', '250'))


def _files():
    return corpus.paths()[:LIMIT]


def _walk(a, r):
    """(nodes, entries) as lists of (offset, tag, program)."""
    nodes, entries = [], []
    for kind, off, tag, prog in r.fx_walk():
        (nodes if kind == 'node' else entries).append((off, tag, prog))
    return nodes, entries


def test_coverage_does_not_regress():
    """How MUCH the walk finds, not just how clean it is.

    The first version of this file had no such check and was worthless: every other test
    here measures purity, and purity IMPROVES when the walk gives up early. Emptying
    `FX_ENTRY` makes the walk stop after the first entry of every record -- which is the
    one position established by pointer-following, so the tag vocabulary goes to ~100% and
    every purity check passes more comfortably than before. Four mutations were applied to
    the model and all four were missed.

    These two numbers are what the mutations actually move.
    """
    entries = progs = recs = 0
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4:
                continue
            recs += 1
            _n, ents = _walk(a, r)
            entries += len({o for o, _t, _p in ents})
            progs += len({pv for _o, _t, pv in ents if pv is not None})
    if not recs:
        print('SKIP test_coverage_does_not_regress: no corpus')
        return 0
    assert entries / recs > 1.8, (entries, recs)      # measured 2.72
    assert progs / recs > 1.6, (progs, recs)          # measured 2.53
    return entries


def test_records_yield_structure():
    """Almost every fxmaps record yields a node or an entry. 0.17% did not when measured."""
    n = empty = 0
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4:
                continue
            n += 1
            nodes, entries = _walk(a, r)
            if not nodes and not entries:
                empty += 1
    if not n:
        print('SKIP test_records_yield_structure: no corpus')
        return 0
    assert empty / n < 0.02, (empty, n)
    return n


def test_entry_tags_are_in_the_vocabulary():
    """A real entry population has a small tag vocabulary.

    CONTROL is historical and stated rather than recomputed: walking with a fixed 8-byte
    stride yielded 56.7% in-vocabulary and 20,184 distinct tags. The tag-stated length with
    a stop on unknown gives 96.5% and 228. This asserts the good side of that gap.
    """
    good = bad = 0
    tags = set()
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4:
                continue
            for _off, tag, _prog in _walk(a, r)[1]:
                tags.add(tag)
                if (tag & 0xFFFF) in FX_TAG_LOW16:
                    good += 1
                else:
                    bad += 1
    if not (good + bad):
        print('SKIP test_entry_tags_are_in_the_vocabulary: no corpus')
        return 0
    rate = good / (good + bad)
    assert rate > 0.90, rate
    assert len(tags) < 2000, len(tags)
    return good + bad


def test_0x1B_branches_to_two_distinct_children():
    """0x1B's successors are at words 2 and 5, differ, and land on NODE headers.

    "They differ" alone is not enough and was the first version of this check: pointing the
    second child at word 4 -- which is the program slot -- still gives two different words,
    and the mutation went unnoticed. What distinguishes a child from a program is the
    disjoint predicate that established the shape: a node header whose target is not itself
    a decodable program. Word 4 fails that in 92% of these nodes and words 2 and 5 pass it.
    """
    same = diff = 0
    landed = probed = 0
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        d = a.data
        for r in a.records:
            if r.filter_id != 4:
                continue
            for off, hdr, _prog in r.fx_tree():
                if (hdr & 0xFF) != 0x1B:
                    continue
                # Read the offsets from the TABLE, not from a copy of it here. The
                # first version hardcoded +8 and +20, so it validated the constants it
                # had itself been written with and could not see a change to FX_NODES2.
                nxts = FX_NODES2[0x1B][0]
                if len(nxts) != 2 or off + max(nxts) + 4 > r.end:
                    continue
                c1 = struct.unpack_from('<I', d, off + nxts[0])[0]
                c2 = struct.unpack_from('<I', d, off + nxts[1])[0]
                if c1 == c2:
                    same += 1
                else:
                    diff += 1
                for c in (c1, c2):
                    t = c + 52
                    if not (a.body_lo <= t < a.body_hi - 4):
                        continue
                    probed += 1
                    w = struct.unpack_from('<I', d, t)[0]
                    if (w & 0xF) in (9, 0xB) and not a.program_span(t, r.end):
                        landed += 1
    if not (same + diff):
        print('SKIP test_0x1B_branches_to_two_distinct_children: none in this corpus')
        return 0
    assert same == 0, (same, diff)
    assert probed and landed / probed > 0.80, (landed, probed)
    return diff


def test_entry_slot_roles_are_fixed():
    """Per (tag, slot) the program's result type is one value, not a mixture.

    This is what makes an entry a RECORD rather than a bag. A tag whose slot 3 were f2 in
    half its entries and f1 in the other half would mean the tag does not state the layout.
    """
    seen = collections.defaultdict(collections.Counter)
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        d = a.data
        for r in a.records:
            if r.filter_id != 4:
                continue
            for off, tag, prog in _walk(a, r)[1]:
                if prog is None:
                    continue
                slots = FX_ENTRY_PROGS.get(tag)
                if not slots:
                    continue
                for k in slots:
                    if off + 4 * k + 4 > r.end:
                        break
                    if struct.unpack_from('<I', d, off + 4 * k)[0] + 52 != prog:
                        continue
                    end = a.program_span(prog, r.end)
                    if end is None:
                        break
                    ins = list(disasm.decode(d, prog, end))
                    _n, ty, comps, _o = disasm.fields(ins[-1][2])
                    seen[(tag, k)]['%s%d' % (disasm.TYPE[ty], comps)] += 1
                    break
    big = [(k, c) for k, c in seen.items() if sum(c.values()) >= 100]
    if not big:
        print('SKIP test_entry_slot_roles_are_fixed: no corpus')
        return 0
    pure = sum(1 for _k, c in big if c.most_common(1)[0][1] / sum(c.values()) > 0.95)
    assert pure / len(big) > 0.90, (pure, len(big))
    return len(big)


def test_fx_programs_use_no_opcode_a_filter_does_not():
    """One ISA. An FX-only opcode would mean the FX side is a different language."""
    fx, filt = set(), set()
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id == 4:
                for _o, _h, prog in r.fx_tree():
                    if prog is None:
                        continue
                    e = a.program_span(prog, r.end)
                    if e:
                        fx |= {disasm.name(i[2]) for i in disasm.decode(a.data, prog, e)}
            else:
                for prog in r.programs:
                    e = a.program_span(prog, r.end)
                    if e:
                        filt |= {disasm.name(i[2]) for i in disasm.decode(a.data, prog, e)}
    if not fx:
        print('SKIP test_fx_programs_use_no_opcode_a_filter_does_not: no corpus')
        return 0
    assert not (fx - filt), sorted(fx - filt)
    return len(fx)


def test_fx_node_programs_never_loop():
    """An FX node program is a parameter expression, not a kernel. 0 in 2.7M instructions."""
    n = loops = 0
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4:
                continue
            for _o, _h, prog in r.fx_tree():
                if prog is None:
                    continue
                e = a.program_span(prog, r.end)
                if e is None:
                    continue
                for i in disasm.decode(a.data, prog, e):
                    n += 1
                    if disasm.name(i[2]) == 'while':
                        loops += 1
    if not n:
        print('SKIP test_fx_node_programs_never_loop: no corpus')
        return 0
    assert loops == 0, loops
    return n


def test_entries_read_the_slots_nodes_write():
    """The chain computes into a shared frame; the table reads it.

    Only high slot indices carry the test -- small ones collide by chance, which is why the
    same comparison over all slots shows 74.7% against a 52.2% control and means nothing.
    """
    def slots(a, prog, end, want):
        out = set()
        for i in disasm.decode(a.data, prog, end):
            if disasm.name(i[2]) == want and i[3]:
                out.add(i[3][-1])
        return out

    per = []
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        W, R = set(), set()
        for r in a.records:
            if r.filter_id != 4:
                continue
            for kind, _off, _tag, prog in r.fx_walk():
                if prog is None:
                    continue
                e = a.program_span(prog, r.end)
                if e is None:
                    continue
                if kind == 'node':
                    W |= slots(a, prog, e, 'set')
                else:
                    R |= slots(a, prog, e, 'get')
        if W or R:
            per.append((W, R))
    hi = lambda s: {x for x in s if x >= 64}                          # noqa: E731
    own = ownd = ctl = 0
    for i, (W, R) in enumerate(per):
        r_ = hi(R)
        own += len(r_ & hi(W))
        ownd += len(r_)
        ctl += len(r_ & hi(per[(i + len(per) // 2) % len(per)][0]))
    # NOT a skip. Too few high slots is how a broken walk looks from here -- shifting
    # every program slot by one word made this test skip rather than fail, which is the
    # same worthlessness as measuring purity alone.
    assert ownd >= 20, ('too few high slots to test: the walk is finding less than it should',
                        ownd)
    assert own / ownd > 0.70, (own, ownd)
    assert ctl / ownd < 0.20, (ctl, ownd)                             # the control
    return ownd


def test_entry_layout_names_the_program_slots():
    """`fx_entry_layout` predicts where an entry's programs are, against a real control.

    The control is what makes this a test rather than a tautology: the same
    "does this word address a program" question, asked at a slot the layout does NOT
    call a program. If the layout were merely finding pointer-shaped words -- which is
    the failure mode that made `(tag & 0xF) == 8` weak -- the control would score too.

    Measured: 93.9% against 0.7%. Thresholds sit well clear of both.
    """
    hit = tot = ctl = ctln = 0
    for f in corpus.paths():
        try:
            a = Assembly(f)
        except Exception:
            continue
        d, lo, hi = a.data, a.body_lo, a.body_hi
        for r in a.records:
            if r.filter_id != 4:
                continue
            seen = set()
            for kind, off, tag, _p in r.fx_walk():
                if kind != 'entry' or off in seen:
                    continue
                seen.add(off)
                lay = fx_entry_layout(tag)
                for sl, _nm, how in lay:
                    if how != 'program' or off + 4 * sl + 4 > hi:
                        continue
                    tot += 1
                    pv = struct.unpack_from('<I', d, off + 4 * sl)[0] + 52
                    if lo < pv < hi and a.program_span(pv, hi):
                        hit += 1
                    s2 = sl + len(lay) + 3                 # off the end of the layout
                    if off + 4 * s2 + 4 <= hi:
                        ctln += 1
                        qv = struct.unpack_from('<I', d, off + 4 * s2)[0] + 52
                        if lo < qv < hi and a.program_span(qv, hi):
                            ctl += 1
    if not tot:
        print('SKIP test_entry_layout_names_the_program_slots: no corpus')
        return 0
    assert hit / tot > 0.85, (hit, tot)
    assert ctl / max(ctln, 1) < 0.10, (ctl, ctln)                     # the control
    return tot


def test_entry_layout_agrees_with_the_census():
    """The layout reproduces `FX_ENTRY_PROGS`, which was derived a different way.

    `FX_ENTRY_PROGS` counted where programs were seen, tag by tag; the layout computes it
    from the tag's bits. They are independent derivations of the same fact, so agreement
    is worth asserting and disagreement is a regression in one of them.

    Node-header keys (low nibble 9 or 0xB) are excluded: those are not table entries and
    the layout does not claim to describe them.
    """
    rows = [(t, sorted(s)) for t, s in FX_ENTRY_PROGS.items() if (t & 0xF) == 8 and t]
    ok = sum(1 for t, s in rows
             if [x for x, _n, k in fx_entry_layout(t) if k == 'program'] == s)
    assert ok / len(rows) > 0.90, (ok, len(rows))
    return len(rows)


def test_node_programs_are_named_and_typed():
    """Every named node program returns the type its parameter's declared type implies.

    `numberadded` is an Integer1 and `switch` a Bool in the source, and the ISA states a
    program's type in its last instruction. This is a check on the NAMES, not on the walk:
    if `FX_NODE_PARAMS` had `0x18B` and `0x89` the wrong way round, the two columns would
    swap and both assertions below would fail.

    Measured: numberadded i1 100.0%, switch b2 100.0%, coverage 89.9% of node programs.
    """
    seen = collections.Counter()
    types = collections.defaultdict(collections.Counter)
    for f in corpus.paths():
        try:
            a = Assembly(f)
        except Exception:
            continue
        for r in a.records:
            if r.filter_id != 4:
                continue
            for _off, _hdr, name, prog in r.fx_node_params():
                seen[name is not None] += 1
                if name is None:
                    continue
                last = None
                for _k, _ad, op, _t in disasm.decode(a.data, prog, a.body_hi):
                    last = op
                if last is None:
                    continue
                _n, ty, comps, _o = disasm.fields(last)
                types[name]['%s%d' % (disasm.TYPE[ty], comps)] += 1
    if not seen:
        print('SKIP test_node_programs_are_named_and_typed: no corpus')
        return 0
    total = seen[True] + seen[False]
    assert seen[True] / total > 0.80, (seen[True], total)
    for name, want in (('numberadded', 'i1'), ('switch', 'b2')):
        c = types[name]
        n = sum(c.values())
        assert n > 100, (name, n)
        assert c[want] / n > 0.95, (name, c.most_common(3))
    return seen[True]


if __name__ == '__main__':
    for fn in (test_coverage_does_not_regress,
               test_records_yield_structure,
               test_entry_tags_are_in_the_vocabulary,
               test_0x1B_branches_to_two_distinct_children,
               test_entry_slot_roles_are_fixed,
               test_fx_programs_use_no_opcode_a_filter_does_not,
               test_fx_node_programs_never_loop,
               test_entries_read_the_slots_nodes_write,
               test_entry_layout_names_the_program_slots,
               test_entry_layout_agrees_with_the_census,
               test_node_programs_are_named_and_typed):
        got = fn()
        print('%-52s %s' % (fn.__name__, ('ok, n=%d' % got) if got else 'skipped'))
