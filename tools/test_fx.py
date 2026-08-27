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
    FX_NODES2: 0x1B row -> ((8,12),())      NOTHING -- see 0x1B_owns_its_fields
    fx_tree: 0x1B sentinel branch removed   0x1B_owns_its_fields (143 of 143)
    FX_LOWERING: any one binding re-pointed  fx_lowering (10 of 10 probed, see there)

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
import contextlib
import io
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xml.etree.ElementTree as ET                                   # noqa: E402

import containment                                                   # noqa: E402
import corpus                                                        # noqa: E402
import disasm                                                        # noqa: E402
import provenance                                                    # noqa: E402
from sbsasm import (Assembly, FX_NODES, FX_NODES2, FX_TAG_LOW16,     # noqa: E402
                    FX_ENTRY, FX_ENTRY_PROGS, FX_NODE_PARAMS, FX_LOWERING,
                    fx_entry_layout, node_shape)

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
        return
    assert entries / recs > 1.8, (entries, recs)      # measured 2.72
    assert progs / recs > 1.6, (progs, recs)          # measured 2.53
    return


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
        return
    assert empty / n < 0.02, (empty, n)
    return


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
        return
    rate = good / (good + bad)
    assert rate > 0.90, rate
    assert len(tags) < 2000, len(tags)
    return


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
        return
    assert same == 0, (same, diff)
    assert probed and landed / probed > 0.80, (landed, probed)
    return


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
        return
    pure = sum(1 for _k, c in big if c.most_common(1)[0][1] / sum(c.values()) > 0.95)
    assert pure / len(big) > 0.90, (pure, len(big))
    return


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
        return
    assert not (fx - filt), sorted(fx - filt)
    return


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
        return
    assert loops == 0, loops
    return


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
    return


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
        return
    assert hit / tot > 0.95, (hit, tot)
    assert ctl / max(ctln, 1) < 0.10, (ctl, ctln)                     # the control
    return


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
    return


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
        return
    total = seen[True] + seen[False]
    assert seen[True] / total > 0.80, (seen[True], total)
    for name, want in (('numberadded', 'i1'), ('switch', 'b2')):
        c = types[name]
        n = sum(c.values())
        assert n > 100, (name, n)
        assert c[want] / n > 0.95, (name, c.most_common(3))
    return


def test_the_layout_rejects_bytecode_read_as_an_entry():
    """A walked entry never lies inside a program's byte span.

    The stopping rule in `Record.fx_table` exists because `0x09130008` and friends are
    bytecode: a u32 straddling two instructions whose low 16 bits happen to be in
    FX_TAG_LOW16, so the vocabulary test passes them. Program spans come from record
    pointers and know nothing about the entry layout, which is what makes this a check on
    the rule rather than a restatement of it.

    Fails if the stopping rule is removed: 2,622 entries reappear inside program spans.
    """
    import bisect
    bad = tot = 0
    for f in corpus.paths():
        try:
            a = Assembly(f)
        except Exception:
            continue
        spans = []
        for r in a.records:
            for p in r.programs or ():
                e = a.program_span(p, a.body_hi)
                if e:
                    spans.append((p, e))
        spans.sort()
        starts = [s for s, _e in spans]
        for r in a.records:
            if r.filter_id != 4:
                continue
            seen = set()
            for kind, off, _tag, _p in r.fx_walk():
                if kind != 'entry' or off in seen:
                    continue
                seen.add(off)
                tot += 1
                i = bisect.bisect_right(starts, off) - 1
                if i >= 0 and spans[i][0] < off < spans[i][1]:
                    bad += 1
    if not tot:
        print('SKIP test_the_layout_rejects_bytecode_read_as_an_entry: no corpus')
        return
    assert bad / tot < 0.02, (bad, tot)
    return


def test_inline_programs_are_where_the_layout_says():
    """The 'inline' rows of `fx_entry_layout` hold a program, against a shifted control."""
    hit = tot = ctl = ctln = 0
    for f in corpus.paths():
        try:
            a = Assembly(f)
        except Exception:
            continue
        hi = a.body_hi
        for r in a.records:
            if r.filter_id != 4:
                continue
            seen = set()
            for kind, off, tag, _p in r.fx_walk():
                if kind != 'entry' or off in seen:
                    continue
                seen.add(off)
                for sl, _nm, how in fx_entry_layout(tag):
                    if how != 'inline' or off + 4 * sl + 2 > hi:
                        continue
                    tot += 1
                    hit += bool(a.program_span(off + 4 * sl, hi))
                    if off + 4 * (sl + 2) + 2 <= hi:
                        ctln += 1
                        ctl += bool(a.program_span(off + 4 * (sl + 2), hi))
    if not tot:
        print('SKIP test_inline_programs_are_where_the_layout_says: no corpus')
        return
    assert hit / tot > 0.85, (hit, tot)
    assert ctl / max(ctln, 1) < 0.15, (ctl, ctln)                     # the control
    return



# --- the source-side check ------------------------------------------------------------
#
# `addnode` declares `numberadded`; `markov2` declares `switch`. A node's compiled program
# IS that parameter's function graph, so the pair is IDENTIFIED and the multisets can be
# compared without guessing an alignment.
_NODE_HDR = {'addnode': {0x18B, 0x1AB, 0x20B}, 'markov2': {0x89}}


def _v(el, tag):
    """A .sbs field, in either serialisation -- `<tag v="x"/>` or `<tag><value v="x"/>`."""
    c = el.find(tag)
    if c is None:
        return None
    if c.get('v') is not None:
        return c.get('v')
    return c.find('value').get('v') if c.find('value') is not None else None


def _source_graphs(path):
    """(node type, parameter name, multiset of source function names) per declared graph."""
    out = []
    for g in ET.parse(path).getroot().iter('paramsGraphData'):
        ntype = _v(g, 'type')
        for par in g.iter('parameter'):
            fns = [n.get('v') for n in par.iter('function') if n.get('v')]
            if fns:
                out.append((ntype, _v(par, 'name'), collections.Counter(fns)))
    return out


def _compiled_multisets(path):
    """header -> list of opcode-name multisets, one per FX node program in the file."""
    a = Assembly(path)
    out = collections.defaultdict(list)
    for r in a.records:
        if r.filter_id != 4:
            continue
        for _off, hdr, prog in r.fx_tree():
            if prog is None:
                continue
            out[hdr].append(collections.Counter(
                disasm.name(op) for _k, _q, op, _t in disasm.decode(a.data, prog, a.body_hi)))
    return out


def _lower(counter, table):
    """The source multiset under `table`, or None if any function is unbound."""
    m = collections.Counter()
    for k, v in counter.items():
        if k not in table:
            return None
        m[table[k]] += v
    return m


def _fx_sources():
    """Permitted paired sources that declare an FX-Map and have a compiled sibling."""
    _excluded, _flagged, permitted = provenance.audit()
    out, seen = [], set()
    for q in permitted:
        q = q if os.path.isabs(q) else os.path.join(provenance.ROOT, q)
        if q in seen or not os.path.exists(q):
            continue
        seen.add(q)
        try:
            if 'paramsGraphData' not in open(q, encoding='utf-8', errors='replace').read():
                continue
        except OSError:
            continue
        if containment.sbsasm_for(q):
            out.append(q)
    return out


def _equations(table):
    """(matched, unmatched) over every fully-bound source graph of a bound node type."""
    matched = unmatched = 0
    for q in _fx_sources():
        comp = _compiled_multisets(containment.sbsasm_for(q))
        for ntype in _NODE_HDR:
            have = collections.Counter()
            for h in _NODE_HDR[ntype]:
                for m in comp.get(h, ()):
                    have[tuple(sorted(m.items()))] += 1
            want = collections.Counter()
            for nt, _pname, c in _source_graphs(q):
                if nt != ntype:
                    continue
                low = _lower(c, table)
                if low is not None:
                    want[tuple(sorted(low.items()))] += 1
            short = sum(max(0, v - have[k]) for k, v in want.items())
            matched += sum(want.values()) - short
            unmatched += short
    return matched, unmatched


def test_fx_lowering_reproduces_the_compiled_multisets():
    """Mapping a source graph through `FX_LOWERING` must reproduce the compiled multiset.

    This is the only check in this file that reads `.sbs` SOURCES, so the provenance
    exclusion runs first and BY CONSTRUCTION: the file list comes from `provenance.audit()`,
    which drops every source carrying an excluded author tag before anything is measured.
    The rule is not applied to the results afterwards; the excluded files never enter.

    Matched by ONE-TO-ONE CONSUMPTION, not membership. A file's fully-bound source graphs
    must be a sub-multiset of its compiled programs, each consuming a distinct one.

    Membership alone is far too weak, and that is measured rather than assumed: `ie_pcloud`
    offers 217 `addnode` programs, and against a pool that size re-pointing `lr` at `and`
    still leaves 18 of 19 equations "reproducing". Under consumption the same mutation is
    caught. Every binding probed is caught this way:

        binding re-pointed        matched  unmatched        binding      matched  unmatched
        mul -> add                   15         4           ifelse->vec     15        4
        add -> mul                    8        11           get_integer1     16       3
        const_float1 -> get          12         7           vector2->set     16       3
        toint1 -> const               4        15           swizzle1->cvt     6      13
        lr -> and                    18         1           get_bool->const  16       3

    `lr` is the thin one at a single unmatched equation, and it has independent support:
    composing this table with `transpile.py`'s -- derived from the sRGB round-trip, not
    from these graphs -- gives `lr -> lt -> 0x21 -> "<"`, and all five bindings the two
    tables share agree.

    CONTROL: the same equations matched against a DIFFERENT file's pool succeed 2 of 133
    (1.5%), so a match is a fact about the pairing rather than about FX programs looking
    alike.
    """
    files = _fx_sources()
    if not files:
        print('SKIP test_fx_lowering_reproduces_the_compiled_multisets: no permitted sources')
        return
    matched, unmatched = _equations(FX_LOWERING)
    print('FX_LOWERING: %d equations matched, %d unmatched, over %d permitted sources'
          % (matched, unmatched, len(files)))
    # NOT just `unmatched == 0`. Nothing found is also zero unmatched, and a test that
    # passes when the parser silently returns no graphs is the failure this file's
    # docstring already records once.
    assert matched >= 12, 'only %d equations found; the source parse has regressed' % matched
    assert unmatched == 0, '%d source graphs do not reproduce their compiled program' % unmatched


# The standalone runner reads SKIP from what a check PRINTS, not from what it returns.
# These functions used to return a count and the runner reported "skipped" when it was
# falsy -- but a pytest test function that returns non-None is a warning today and an
# error in a future pytest, so the returns are gone. Reading the printed SKIP keeps the
# distinction that matters: a suite that silently skips everything looks identical to a
# passing one, which is the failure this directory has already recorded once.
def test_entry_programs_are_yielded_in_a_runnable_order():
    """`fx_named_params` must yield entry programs in an order that can be RUN.

    An entry program can write slots as a side effect and a later one read them: on
    `sci_fi_elements_02` record 86 the `opacity` program sets slots 15, 17 and 18 while
    computing an angle, and the `frameoffset`, `patternsize` and `patternrotation`
    programs are bare `get`s of exactly those. 13.7% of records with two or more entry
    programs have at least one such dependency.

    So the yield order is load-bearing, and it is load-bearing in the worst way: a
    reordering does not crash, it produces a plausible wrong picture. Neither coverage nor
    flatness can see that -- the third instance this session of the same failure class,
    after stale samplers and a whole-array spread metric.

    The check is that no program reads a slot only a LATER program writes, i.e. the order
    contains no forward reference. Measured at 0 of 9,736 records, and a reversed order is
    the control: it must fail.
    """
    def setget(d, p, hi):
        sets, gets = set(), set()
        for _k, _a, op, toks in disasm.decode(d, p, hi):
            _n, _ty, _c, oid = disasm.fields(op)
            if oid == 0x04 and toks:
                gets.add(toks[0])
            elif oid == 0x07 and len(toks) > 1:
                sets.add(toks[1])
        return sets, gets

    def forward_refs(d, hi, seq):
        """How many programs read a slot only something after them writes."""
        bad = 0
        for i, p in enumerate(seq):
            _s, g = setget(d, p, hi)
            before = set()
            for q in seq[:i]:
                before |= setget(d, q, hi)[0]
            later = set()
            for q in seq[i + 1:]:
                later |= setget(d, q, hi)[0]
            if (g - before) & later:
                bad += 1
        return bad

    fwd = rev = n = 0
    for f in corpus.paths():
        try:
            a = Assembly(f)
        except Exception:
            continue
        d, hi = a.data, a.body_hi
        for r in a.records:
            if r.filter_id != 4:
                continue
            seq = [v for _o, _t, _s, _n, k, v in r.fx_named_params() if k != 'baked' and v]
            if len(seq) < 2:
                continue
            n += 1
            fwd += bool(forward_refs(d, hi, seq))
            rev += bool(forward_refs(d, hi, list(reversed(seq))))   # the control
    if not n:
        print('SKIP test_entry_programs_are_yielded_in_a_runnable_order: no corpus')
        return 0
    assert fwd == 0, ('a yielded entry program reads a slot only a later one writes', fwd, n)
    assert rev > 0, ('the control did not fail: reversing the order broke nothing, so this '
                     'test proves nothing about the order', rev, n)
    return n


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
               test_node_programs_are_named_and_typed,
               test_the_layout_rejects_bytecode_read_as_an_entry,
               test_inline_programs_are_where_the_layout_says,
               test_fx_lowering_reproduces_the_compiled_multisets,
               test_entry_programs_are_yielded_in_a_runnable_order):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        out = buf.getvalue()
        sys.stdout.write(out)
        print('%-52s %s' % (fn.__name__, 'skipped' if 'SKIP' in out else 'ok'))


def test_0x1B_owns_its_fields_and_does_not_borrow_its_neighbours():
    """A sentinel `0x1B` must yield NO program and its contiguous child must be VISITED.

    The ownership check, and it exists because the validity check next door cannot fail on
    the error that actually happened. `test_0x1B_branches_to_two_distinct_children` asks
    whether the claimed child offsets LAND ON NODE HEADERS, and a row that borrows its
    neighbour's fields satisfies that -- the neighbour's fields point at real nodes too.
    Mutation-tested directly: with `FX_NODES2[0x1B]` set to the shipped `((8, 20), (16,))`
    and to the measured `((8, 12), ())`, that check passes BOTH ways. It does catch a child
    moved to word 4, both children made identical, and nonsense offsets -- three of four --
    so it is a real check with one blind spot, and this covers the blind spot.

    WHAT OWNERSHIP MEANS HERE, stated as arithmetic rather than as plausibility. For a
    `0x1B` whose word 1 is the `0x3039` sentinel the next node begins CONTIGUOUSLY at byte
    12, and `node_shape` gives that node's own successor and program offsets relative to
    ITS OWN start. So the bytes it owns are `12 + those`. For the `0x18B` that always
    follows, `node_shape` is `(8, (4,))`, which makes 12+8 = 20 and 12+4 = 16 ITS fields --
    exactly the two bytes `FX_NODES2[0x1B]` claimed. The claim was the neighbour's
    successor and program read as this node's.

    The consequence in the walk, which is what this asserts, is that nothing addressed byte
    12, so the contiguous `0x18B` was never visited as a node at all: its program was
    yielded under the `0x1B`'s offset and its successor followed as though the branch owned
    it. Both assertions below fail on that behaviour and pass on the two-shape walk.

    Scoped to the sentinel form deliberately. The 12 non-sentinel `0x1B` nodes in the
    corpus (all in one file, word 1 = 0) have a six-word self-relative shape whose
    successor is not established, so there is nothing here to assert about them yet.
    """
    checked = no_prog = child_visited = 0
    borrowed = []
    for p in _files():
        try:
            a = Assembly(p)
        except Exception:
            continue
        d = a.data
        for r in a.records:
            if r.filter_id != 4:
                continue
            try:
                items = [(off, hdr, prog) for kind, off, hdr, prog in r.fx_walk()
                         if kind == 'node']
            except Exception:
                continue
            offs = {off for off, _h, _p in items}
            for off, hdr, prog in items:
                if (hdr & 0xFF) != 0x1B or off + 16 > r.end:
                    continue
                if struct.unpack_from('<I', d, off + 4)[0] != 0x3039:
                    continue          # the six-word form, not established
                checked += 1
                if prog is None:
                    no_prog += 1
                if (off + 12) in offs:
                    child_visited += 1
                # The neighbour's OWN fields, by its own shape -- this is the arithmetic
                # that makes the claim checkable rather than a matter of taste.
                child_hdr = struct.unpack_from('<I', d, off + 12)[0]
                sh = node_shape(child_hdr)
                if sh is None:
                    continue
                owned = {12 + sh[0]} | {12 + s for s in (sh[1] or ())}
                claimed = set(FX_NODES2.get(0x1B, ((), ()))[0] or ())
                claimed |= set(FX_NODES2.get(0x1B, ((), ()))[1] or ())
                if claimed & owned:
                    borrowed.append((os.path.basename(p), off,
                                     sorted(claimed & owned)))
    if not checked:
        print('SKIP test_0x1B_owns_its_fields: no sentinel 0x1B in this corpus')
        return
    assert no_prog == checked, (
        'a sentinel 0x1B yielded a program of its own on %d of %d nodes; byte 16 is the '
        'contiguous neighbour\'s program (12 + 4), not this node\'s'
        % (checked - no_prog, checked))
    assert child_visited == checked, (
        'the contiguous child at byte 12 was not visited on %d of %d sentinel 0x1B nodes '
        '-- nothing addresses it unless the walk continues there'
        % (checked - child_visited, checked))
    print('0x1B ownership: %d sentinel nodes, %d yield no program, %d contiguous children '
          'visited; %d borrow-claims against the neighbour'
          % (checked, no_prog, child_visited, len(borrowed)))
    return
