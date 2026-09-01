#!/usr/bin/env python3
"""Is each of the model's tables actually carrying the decode?

A table can be elaborately derived, carefully documented, guarded against corpus
duplication -- and dead. Nothing in this project measured that, and the audit cannot:
emptying `layouts.json` entirely moves `audit_corpus.py`'s headline by 0.3 points, which is
noise. A number that barely moves when you delete the thing it is supposed to measure is
not measuring it.

So this knocks each table out and reports what changes. It is a LOAD-BEARING test, the
mirror image of the coverage checks in `test_fx.py`: those catch a model that decodes less
than it should, this catches a table that is not doing the job its derivation claims.

SKIPS when the corpus is absent.
"""
import contextlib
import io
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import sbsasm                                                        # noqa: E402
from sbsasm import Assembly                                          # noqa: E402

FILES = int(os.environ.get('SBS_TABLE_FILES', '120'))


def _snapshot(paths):
    out = {}
    for p in paths:
        try:
            a = Assembly(p)
        except Exception:
            continue
        for r in a.records:
            # The FX walk has to be in the snapshot or the FX tables read as dead: the
            # first version of this probe measured only programs, edges and parameters,
            # none of which touch fx_walk, and duly reported FX_NODES and FX_ENTRY as
            # changing nothing. A knockout test is only as good as what it observes.
            fx = ()
            if r.filter_id == 4:
                try:
                    fx = tuple((k, o, t, pr) for k, o, t, pr in r.fx_walk())
                except Exception:
                    fx = ('error',)
            # program_slots and named_parameters are observed too: LAYOUTS and LAYOUT_MASK
            # are drained from the layout computation (edges/programs) but STILL feed these
            # two -- program_slots keys the blur/warp popcount block, named_parameters reads
            # the blend/levels parameter positions. Without observing them the knockout
            # reports both tables dead, which they are not.
            try:
                psl = tuple(r.program_slots)
            except Exception:
                psl = ('error',)
            try:
                npr = tuple(r.named_parameters)
            except Exception:
                npr = ('error',)
            out[(p, r.index)] = (frozenset(r.programs),
                                 tuple(r.edge_slots),
                                 tuple(r.edges),
                                 None if r.size_or_baked is None else r.size_or_baked[0],
                                 fx, psl, npr)
    return out


def _knockout(table, paths):
    """(records compared, records whose reading changes) with `table` emptied."""
    base = _snapshot(paths)
    saved = dict(table)
    table.clear()
    try:
        mut = _snapshot(paths)
    finally:
        table.clear()
        table.update(saved)
    changed = sum(1 for k, v in base.items() if mut.get(k) != v)
    return len(base), changed


def test_layouts_drained_from_layout():
    """`layouts.json` no longer determines any record's edges, programs, or size.

    This used to assert the table was marginally load-bearing (~0.87% of records). That is
    no longer true for the LAYOUT computation, and by design: `_compute_layout` no longer
    consults LAYOUTS -- pixelprocessor reads its arity from `_pp_edges`, transformation and
    bitmap from walk(SPECS[.]), blend/levels/dirmotionblur/directionalwarp from `_ruled`,
    and the rest from the fixed-shape EDGES/PROG_SLOT/ALT_LAYOUTS fallbacks; and `programs()`
    finds every program from the universal slot scan plus `classified_programs`. The one
    record that still needed the table (ie_curve rec233, a 5-bit arity the low nibble
    misread as a generator) was fixed at the rule instead.

    So emptying LAYOUTS changes 0 EDGE, PROGRAM or SIZE readings -- the drain succeeding.
    It is a SCOPED knockout, not the full snapshot, and it was scoped because LAYOUTS was
    still load-bearing for `program_slots` (the blur/warp popcount block) and
    `named_parameters` (`levels`' parameter positions). Both are drained now --
    `test_layouts_is_fully_drained` is the unscoped version and asserts zero over the whole
    snapshot -- so this one is kept as the narrower statement it always was, not as the
    boundary of what the table no longer does.
    """
    paths = corpus.paths()[:FILES]
    if not paths:
        print('SKIP test_layouts_drained_from_layout: no corpus')
        return
    saved = dict(sbsasm.LAYOUTS)

    def layout_reads():
        out = {}
        for p in paths:
            try:
                a = Assembly(p)
            except Exception:
                continue
            for r in a.records:
                out[(p, r.index)] = (frozenset(r.programs), tuple(r.edge_slots),
                                     None if r.size_or_baked is None
                                     else r.size_or_baked[0])
        return out

    base = layout_reads()
    sbsasm.LAYOUTS.clear()
    try:
        mut = layout_reads()
    finally:
        sbsasm.LAYOUTS.clear()
        sbsasm.LAYOUTS.update(saved)
    if not base:
        print('SKIP test_layouts_drained_from_layout: no records')
        return
    changed = sum(1 for k, v in base.items() if mut.get(k) != v)
    assert changed == 0, ('layouts.json still changes %d edge/program/size readings; the '
                          'layout drain regressed' % changed)
    return


def test_layouts_changes_no_program_discovery():
    """The programs found are identical with and without the layout table.

    `Record.programs` looks the key up, but everything it names is also named by
    `self.layout[1]` and `classified_programs`, so the lookup contributes nothing. Stated
    as a test because it is surprising and would otherwise be re-discovered.
    """
    paths = corpus.paths()[:FILES]
    if not paths:
        print('SKIP test_layouts_changes_no_program_discovery: no corpus')
        return
    base = _snapshot(paths)
    saved = dict(sbsasm.LAYOUTS)
    sbsasm.LAYOUTS.clear()
    try:
        mut = _snapshot(paths)
    finally:
        sbsasm.LAYOUTS.clear()
        sbsasm.LAYOUTS.update(saved)
    if not base:
        print('SKIP test_layouts_changes_no_program_discovery: no records')
        return
    bad = sum(1 for k, v in base.items() if mut.get(k, (None,))[0] != v[0])
    assert bad == 0, ('%d records find different programs without layouts.json' % bad)
    return


def test_every_table_is_load_bearing():
    """Report each table's contribution; fail on any that changes nothing at all.

    A table that changes no reading is either dead or shadowed by another, and either way
    the next person should not have to find that out by experiment.

    FX_ENTRY and FX_NODES are deliberately NOT in the list: both are drained. FX_ENTRY was the
    entry-walk stride, now replaced by the linked-list next-pointer each entry stores; FX_NODES
    was the node sizer, now computed by `node_shape` from the header's mask. Emptying either
    changes no reading BY DESIGN, and both are kept as a census.

    FX_NODES2 IS NOW OUT OF THE LIST TOO, and for a THIRD reason that is worth separating from
    the other two, because the obvious readings are both wrong. It is not derived away like
    FX_NODES -- `node_shape(0x1B)` and `leaf_successor(0x1B)` both return None, so nothing
    derives it -- and it is not shadowed by the 0x1B value probe above it in `fx_walk`, which
    takes only 12 of the corpus's 355 0x1B nodes (the other 343 have word 1 == 0x3039 and the
    probe declines them). The remaining 343 DO reach `FX_NODES2[0x1B]`, and its stated byte 20
    yields an IN-RANGE successor in 343 of 343. The table is consulted and it answers.

    It is REDUNDANT: `fx_table` reaches the same entries whether or not `start` is set from
    that answer. Measured with the accessor this snapshot actually observes, over records
    scanned from the whole corpus for containing a 0x1B node, `fx_walk` is byte-identical with
    and without the table on 40 of 40. So emptying it changes no reading, and the assertion
    below would fail on a table that is doing exactly what it claims.

    That distinction matters for whoever removes it. A derived table can be deleted; a
    redundant one is only redundant against the CURRENT `fx_table`, and the 343 in-range
    successors are a real second statement of where the handoff is. Kept as a census, like
    the other two. Note also `fxrender`'s standing flag that the row's (8, 20) contradicts
    what that file derives -- unresolved, and not resolved here.

    LAYOUTS AND LAYOUT_MASK LEFT THIS LIST for a FOURTH reason: they are drained, on
    purpose, and the drain finished. `layouts.json` was down to one consumer --
    `Record.named_parameters` for `levels`, 9.272% of records -- and routing `levels`
    through the structural walk took that to zero. `test_layouts_is_fully_drained` below
    asserts the emptied-table result this list would now read as a failure, which is the
    right shape: a table that must change nothing needs an assertion that it changes
    nothing, not an assertion that it changes something.
    """
    paths = corpus.paths()[:FILES]
    if not paths:
        print('SKIP test_every_table_is_load_bearing: no corpus')
        return
    dead = []
    for name in ('EDGES',):
        tab = getattr(sbsasm, name, None)
        if not isinstance(tab, dict) or not tab:
            continue
        n, changed = _knockout(tab, paths)
        print('    %-14s %7d of %7d records read differently without it  (%.3f%%)'
              % (name, changed, n, 100 * changed / max(1, n)))
        if changed == 0:
            dead.append(name)
    assert not dead, ('these tables change no reading at all: %s' % dead)
    return


def test_layouts_is_fully_drained():
    """`layouts.json` now changes NO reading this model makes, of any kind.

    `test_layouts_drained_from_layout` above is the SCOPED version -- edges, programs and
    size only -- and it was scoped because the table still placed `levels`' parameters
    through `Record._parameters_paired`. It no longer does: `WALKED_PARAMS` covers every
    filter in `PARAM_SPEC`, so `_parameters_paired` has no caller, and `program_slots`'
    LAYOUTS fallback is reached 0 times in 42,166 corpus blur/warp records because
    `decompose` answers first on every one of them.

    So this runs the FULL snapshot -- programs, edge slots, edges, size, the FX walk,
    `program_slots` and `named_parameters` -- with each table emptied, and asserts zero.
    Before the routing it read 14,897 of 160,672 (9.272%) for both tables, which is exactly
    the `levels` share.

    IT IS A REAL ASSERTION AND NOT A TAUTOLOGY, which is the thing to check about a test
    that expects nothing to happen: `_knockout` on EDGES over the same paths returns 4, so
    the machinery does detect a table that is consulted. Route `levels` back to the memo
    and this fails immediately.
    """
    paths = corpus.paths()[:FILES]
    if not paths:
        print('SKIP test_layouts_is_fully_drained: no corpus')
        return
    for name in ('LAYOUTS', 'LAYOUT_MASK'):
        tab = getattr(sbsasm, name)
        n, changed = _knockout(tab, paths)
        if not n:
            print('SKIP test_layouts_is_fully_drained: no records')
            return
        print('    %-14s %7d of %7d records read differently without it'
              % (name, changed, n))
        assert changed == 0, (
            '%s still decides %d of %d readings -- layouts.json is not drained, and '
            'something has been routed back onto the memo' % (name, changed, n))
    return


# The standalone runner reads SKIP from what a check PRINTS, not from what it returns.
# These functions used to return a count and the runner reported "skipped" when it was
# falsy -- but a pytest test function that returns non-None is a warning today and an
# error in a future pytest, so the returns are gone. Reading the printed SKIP keeps the
# distinction that matters: a suite that silently skips everything looks identical to a
# passing one, which is the failure this directory has already recorded once.
if __name__ == '__main__':
    for fn in (test_layouts_drained_from_layout,
               test_layouts_changes_no_program_discovery,
               test_layouts_is_fully_drained,
               test_every_table_is_load_bearing):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        out = buf.getvalue()
        sys.stdout.write(out)
        print('%-52s %s' % (fn.__name__, 'skipped' if 'SKIP' in out else 'ok'))
