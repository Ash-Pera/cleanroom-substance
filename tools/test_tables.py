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
            out[(p, r.index)] = (frozenset(r.programs),
                                 tuple(r.edge_slots),
                                 tuple(r.edges),
                                 None if r.size_or_baked is None else r.size_or_baked[0],
                                 fx)
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


def test_layouts_is_fully_drained():
    """`layouts.json` changes NOTHING a record reads -- the memo is drained.

    This used to assert the table was still marginally load-bearing (~0.87% of records).
    That is no longer true, and by design: `_compute_layout` no longer consults LAYOUTS at
    all -- pixelprocessor reads its arity from `_pp_edges`, transformation and bitmap from
    walk(SPECS[.]), blend/levels/dirmotionblur/directionalwarp from `_ruled`, and the rest
    from the fixed-shape EDGES/PROG_SLOT/ALT_LAYOUTS fallbacks; and `programs()` finds every
    program from the universal slot scan plus `classified_programs` rather than the memo's
    hint. The one record that still needed the table (ie_curve rec233, a 5-bit arity the low
    nibble misread as a generator) was fixed at the rule instead.

    So emptying LAYOUTS now changes 0 of the snapshotted readings -- programs, edges, edge
    resolution, size_or_baked and the whole FX walk. The assertion is inverted from its old
    `changed > 0`: the table IS dead for these readings, which is the drain succeeding.

    Not yet asserted, and the reason the loading is not simply deleted: `program_slots`
    (the blur/warp popcount block) and `named_parameters` still read LAYOUTS-derived data,
    and this snapshot does not observe them. Draining those is the remaining step before
    `layouts.json` can be removed outright.
    """
    paths = corpus.paths()[:FILES]
    if not paths:
        print('SKIP test_layouts_is_fully_drained: no corpus')
        return
    n, changed = _knockout(sbsasm.LAYOUTS, paths)
    if not n:
        print('SKIP test_layouts_is_fully_drained: no records')
        return
    assert changed == 0, ('layouts.json still changes %d of %d readings; the drain is '
                          'incomplete or a rule regressed' % (changed, n))
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
    """
    paths = corpus.paths()[:FILES]
    if not paths:
        print('SKIP test_every_table_is_load_bearing: no corpus')
        return
    dead = []
    for name in ('LAYOUTS', 'EDGES', 'LAYOUT_MASK', 'FX_NODES', 'FX_ENTRY'):
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


# The standalone runner reads SKIP from what a check PRINTS, not from what it returns.
# These functions used to return a count and the runner reported "skipped" when it was
# falsy -- but a pytest test function that returns non-None is a warning today and an
# error in a future pytest, so the returns are gone. Reading the printed SKIP keeps the
# distinction that matters: a suite that silently skips everything looks identical to a
# passing one, which is the failure this directory has already recorded once.
if __name__ == '__main__':
    for fn in (test_layouts_is_load_bearing_but_barely,
               test_layouts_changes_no_program_discovery,
               test_every_table_is_load_bearing):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        out = buf.getvalue()
        sys.stdout.write(out)
        print('%-52s %s' % (fn.__name__, 'skipped' if 'SKIP' in out else 'ok'))
