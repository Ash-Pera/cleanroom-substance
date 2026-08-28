#!/usr/bin/env python3
"""Checks for the walk-only renderer.

    python3 tools/render2/test_render2.py

Two kinds, and the first is the one that survives a missing corpus: the STRUCTURAL checks
read a record's own words and assert what the walk names, with no render and no reference.
The RENDER checks need the `Rokviz japanese fabric 8` specimen and its exported maps and
skip loudly when they are not present -- the corpus is not redistributed here.

WHY THE FLOORS ARE HERE AT ALL. `test_filters.REFERENCE_FLOOR` exists because a commit once
took the best agreement in this repository to a constant and nothing automated noticed for
four commits. The same exposure applies to a second renderer, and more so: nothing else in
the suite runs it.
"""
import glob
import os
import re
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # see __init__.py: this package goes LAST

import sbsasm                                                        # noqa: E402
import manifest                                                      # noqa: E402
import filters as filters_mod                                        # noqa: E402
import model                                                         # noqa: E402
import ops                                                           # noqa: E402
import sbsruntime                                                    # noqa: E402
from engine import Context, render                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Set a little under the measured value, per channel, so float noise passes and a
#: collapse does not. The MEAN is asserted for `height` instead of a correlation, because
#: that is the channel arbitrating the FX emission count.
#:
#: `metallic` is absent because it is 0 on both sides. `normal` is absent for a REASON THIS
#: COMMENT USED TO STATE WRONGLY -- it said normal was degenerate "on this specimen at every
#: resolution", which is true of what we render and false of what the engine exported. The
#: export at its native 4096 has std 0.211 in X and Y: full relief. Ours is 0.5000 +- 0.0009,
#: flat. Two separate things hid that: every score here resamples to 64, and averaging a
#: normal map cancels its slopes (the export box-averaged to 256 falls to std 0.0017).
#:
#: The part resolution does NOT explain: mean Z. Averaging preserves a mean, and the export's
#: is 0.8987 against our 1.0000 -- 0.101 apart, which is the difference between a surface with
#: slopes and a flat one. The cause is that the two images are different renders: the manifest
#: declares `$outputsize` default 8,8 (256) and the maps were exported at 12,12 (4096), while
#: a record's size is baked in its tag, so `max_dim` can only cap and never raise. Until this
#: renderer can be told an `$outputsize`, every scale-dependent channel is being compared
#: across two parameterizations, and a floor here would assert the wrong thing.
REFERENCE_FLOOR = {
    ('basecolor', 0): 0.95,          # measured +0.9758
    ('basecolor', 1): 0.92,          # measured +0.9494
    ('basecolor', 2): 0.87,          # measured +0.9066
    ('roughness', 0): 0.93,          # measured +0.9582
    ('ambientocclusion', 0): 0.94,   # measured +0.9701
}

#: (record, parameter) -> value the walk must read. Every one of these is a record where
#: the LAYOUTS memo reads something else or nothing at all; see FORMAT-NOTES.
WALKED_PARAMETERS = {
    (34, 'levelinlow'): 0.1375, (34, 'levelinhigh'): 0.1375,
    (34, 'leveloutlow'): 1.0, (34, 'levelouthigh'): 0.0,
    (68, 'levelinlow'): 0.2821, (68, 'levelinhigh'): 0.7023,
    (68, 'levelinmid'): 0.8617, (68, 'leveloutlow'): 0.3521,
    (19, 'intensity'): 0.25,
    (23, 'intensity'): 0.38,
    (9, 'intensity'): 3.59,
}


def _skip(reason):
    """A skip a RUNNER can see.

    `print('SKIP ...'); return` is a PASS under pytest, which is the silent-green mode
    this file's own docstring is written against -- the corpus is not redistributed, so
    every render check here is one missing directory away from reporting nothing wrong.
    Under pytest this raises the framework's skip; run as a script it prints and the
    caller returns.
    """
    pytest = sys.modules.get('pytest')
    if pytest is not None:
        pytest.skip(reason)
    print('SKIP ' + reason)


def specimen():
    hits = glob.glob(os.path.join(ROOT, '**', 'Rokviz japanese fabric 8.sbsasm'),
                     recursive=True)
    return hits[0] if hits else None


def references():
    out = {}
    for p in glob.glob(os.path.join(ROOT, '**', 'Rokviz_japanese_fabric_8_*.png'),
                       recursive=True):
        out[re.sub(r'[^a-z]', '', os.path.basename(p).rsplit('_', 1)[-1][:-4].lower())] = p
    return out


#: (filter id) -> the w1 fields, and the class bits, that the format DECLARES and charges
#: words for and that §13.4's legend does not cover. Frozen so a NEW one fails here instead
#: of waiting for a review: `hsl` was a silent identity in 747 records and `sharpen` in
#: 1,156, and neither showed up in any count, because a name nothing supplies reads as its
#: default and a default renders.
#:
#: To retire an entry, name the field (and delete the entry). To add one, say in a comment
#: what is known about it. Bits, not field indices: `blend`'s relocated opacity straddles
#: fields 4 and 5, and an index-based reading would call both unnamed.
UNNAMED_BUT_DECLARED = {
    'w1': {
        # DECLARED FOR THEIR WIDTH, still unread: `W1_PARAMS` carries these with no name, so
        # the placement is right and the value is not read. Being here is the difference
        # between "we know it is there" and "it silently moves a named parameter".
        1:  (3,),        # blend -- two words, put `opacitymult` two slots late until 1241661
        18: (2,),        # normal -- a flag beside `inversedy`
        # NOT DECLARED AT ALL. A program arm here moves whatever this legend does name.
        12: (3,),        # directionalwarp
        20: (2,),        # pixelprocessor -- one field, 16 words, 1 corpus record
        21: (1,),        # distance -- field 0 is named now; field 1 is the source's
                         # `combinedistance` on nothing better than elimination, and both
                         # nodes state it 0, so it stays unnamed
    },
    'cls': {
        # Bit 23 is a PROGRAM POINTER wherever it appears -- it decodes to 10 ops on the
        # simple filters, 14-82 on pixelprocessor -- and `walk_programs` already offers
        # every class slot to the program machinery, so these are run; what is unknown is
        # which parameter each computes.
        0: (23,), 1: (23,), 14: (23,), 20: (23,), 22: (23,),
        # (26, 27) is a per-filter parameter pair, baked then program: blur holds
        # (16.0, 16.0), warp (0.9801, 0.9801), directionalwarp (0.99, 1.0). NOT `$outputsize`
        # -- those are floats, not log2 integers.
        3: (23, 26), 7: (23, 26, 27), 10: (23, 26, 27), 11: (23, 26, 27),
        12: (23, 26, 27), 13: (23, 26, 27), 21: (23, 26, 27),
        18: (10, 11, 14, 15, 23, 26, 27),
        19: (11, 23, 25, 26),
    },
}


def _filter_ids():
    return {n: i for i, n in sbsasm.FILTERS.items()}


def _asks_without_a_legend(count=False):
    """(filter, id, name) for every parameter name a filter asks for and no legend supplies.

    Read out of `filters.py`'s own syntax tree rather than a list kept beside it, so adding
    a filter that asks for a name is enough to be checked.
    """
    import ast
    tree = ast.parse(open(os.path.join(_HERE, 'filters.py'), encoding='utf-8').read())
    ids = _filter_ids()
    askers = {'_scalar': 2, '_vector': 2, '_channelwise': 2}     # index of the name argument
    bad, checked = [], 0
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        declared = [d.args[0].value for d in node.decorator_list
                    if isinstance(d, ast.Call) and getattr(d.func, 'id', '') == 'filt']
        if not declared:
            continue
        asked = set()
        for n in ast.walk(node):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            f = n.func
            if isinstance(f, ast.Name) and f.id in askers and len(n.args) > askers[f.id]:
                a = n.args[askers[f.id]]
            elif isinstance(f, ast.Attribute) and (
                    f.attr in ('baked', 'program', 'has')
                    or (f.attr == 'get' and isinstance(f.value, ast.Attribute)
                        and f.value.attr == 'params')):
                a = n.args[0]
            else:
                continue
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                asked.add(a.value)
        fid = ids.get(declared[0])
        supply = set()
        if fid is not None:
            supply |= {t[2] for t in model.W1_PARAMS.get(fid, ()) if t[2]}
            supply |= {e[0] for e in model.CLS_NAMES.get(fid, {}).values()}
        checked += 1
        bad.extend((declared[0], fid, name) for name in sorted(asked - supply))
    return (bad, checked) if count else bad


def test_every_parameter_a_filter_asks_for_can_be_supplied():
    """A NAME NOTHING SUPPLIES IS A SILENT IDENTITY, not an error.

    `_scalar` and its neighbours return the stated default when `View.params` has no entry,
    and every one of those defaults is the neutral value -- so a filter asking for a name no
    legend produces renders, produces plausible output, and does nothing. That is what `hsl`
    did in all 747 corpus records (hue, saturation and luminosity all defaulted to 1/2) and
    `sharpen` in 1,156 (intensity defaulted to 1).

    Read out of `filters.py`'s own syntax tree rather than a list kept beside it, so adding
    a filter that asks for a name is enough to be checked.
    """
    bad, checked = _asks_without_a_legend(count=True)
    assert checked > 15, 'the filter table was not read: %d functions' % checked
    assert not bad, ('these filters ask for a parameter no legend can supply, so every '
                     'record renders at the default: %r' % (bad,))
    # AND IT CAN FIRE. This check passes by finding nothing, which is the same output a
    # broken scan produces -- so take a legend away and watch it come back. `sharpen` is
    # the one that was actually in this state until the legend named bit 28.
    saved = model.CLS_NAMES.pop(13)
    try:
        again = _asks_without_a_legend()
        assert ('sharpen', 13, 'intensity') in again, \
            'with filter 13 unnamed the scan still reports %r -- it is not looking' % (again,)
    finally:
        model.CLS_NAMES[13] = saved
    print('ok  test_every_parameter_a_filter_asks_for_can_be_supplied (%d filters)' % checked)


def _declared_without_a_name():
    """{'w1'|'cls': {filter id: fields}} the format declares, charges words for, and no
    name covers. From `costs.json` and the legends alone -- no corpus: it states what this
    renderer declines to read, not how often that happens."""
    import json
    costs = json.load(open(os.path.join(ROOT, 'tools', 'costs.json'), encoding='utf-8'))
    ids = _filter_ids()
    got = {'w1': {}, 'cls': {}}
    for name in filters_mod.FILTERS:
        fid = ids.get(name)
        if fid is None:
            continue
        entry = costs.get(str(fid), {})
        cov_w1, cov_cls = model._covered_bits(fid)
        # `int(round(...))` is `decompose`'s own rule for turning a fitted cost into words.
        rows = tuple(int(j) for j, states in sorted(entry.get('w1', {}).items(),
                                                    key=lambda kv: int(kv[0]))
                     if not ((3 << (2 * int(j))) & cov_w1)
                     and max(int(round(v)) for v in states.values()) >= 1)
        if rows:
            got['w1'][fid] = rows
        rows = tuple(int(b) for b, c in sorted(entry.get('cls', {}).items(),
                                               key=lambda kv: int(kv[0]))
                     if int(b) not in cov_cls and int(round(c)) >= 1)
        if rows:
            got['cls'][fid] = rows
    return got


def test_the_declared_fields_the_legend_ignores_are_the_known_ones():
    """The other half: a field the FORMAT declares, charged words, that no name covers.

    This is the `normal` shape -- fields 1 and 2 were declared, cost a word as a program,
    and their absence from the legend moved `intensity` -- and the `blend` field 3 shape,
    where two unnamed words put the opacity two slots late. `UNNAMED_BUT_DECLARED` is what
    is known to be uncovered; this fails when the set moves in either direction.
    """
    got = _declared_without_a_name()
    for half in ('w1', 'cls'):
        new_ = {k: v for k, v in got[half].items() if UNNAMED_BUT_DECLARED[half].get(k) != v}
        gone = {k: v for k, v in UNNAMED_BUT_DECLARED[half].items() if got[half].get(k) != v}
        assert not new_ and not gone, (
            '%s: the declared-but-unnamed set moved. Now uncovered and not in the '
            'inventory: %r. In the inventory and no longer uncovered -- name it in SPEC '
            'and delete the entry: %r' % (half, new_, gone))
    # AND IT CAN FIRE: take `hsl`'s six names away and its class bits must reappear.
    saved = model.CLS_NAMES.pop(14)
    model._covered_bits.cache_clear()          # or the mutation is invisible; see model.py
    try:
        again = _declared_without_a_name()
        assert set(again['cls'].get(14, ())) >= {24, 26, 28}, \
            'with filter 14 unnamed the scan reports %r for hsl -- it is not looking' \
            % (again['cls'].get(14),)
    finally:
        model.CLS_NAMES[14] = saved
        model._covered_bits.cache_clear()
    print('ok  test_the_declared_fields_the_legend_ignores_are_the_known_ones '
          '(%d w1, %d class)' % (len(got['w1']), len(got['cls'])))


def test_walk_reads_the_parameters_the_memo_cannot():
    """The structural half: what the walk names, from the record's own words."""
    path = specimen()
    if not path:
        return _skip('test_walk_reads_the_parameters_the_memo_cannot: no specimen')
    asm = sbsasm.Assembly(path)
    bad = []
    for (index, name), want in sorted(WALKED_PARAMETERS.items()):
        v = model.View(asm, asm.records[index])
        got = v.baked(name)
        if got is None or abs(float(np.asarray(got).ravel()[0]) - want) > 5e-4:
            bad.append((index, name, got, want))
    assert not bad, 'the walk no longer names these: %r' % (bad,)
    # Record 34 is only a threshold because its input span is zero AND its output range is
    # reversed. Both halves, asserted, because either one alone is a different filter.
    v = model.View(asm, asm.records[34])
    assert abs(v.baked('levelinlow') - v.baked('levelinhigh')) < 1e-6
    assert v.baked('leveloutlow') > v.baked('levelouthigh')
    print('ok  test_walk_reads_the_parameters_the_memo_cannot (%d parameters)'
          % len(WALKED_PARAMETERS))


def test_blend_reads_the_relocated_opacity():
    """`blend`'s opacity sits at ONE OF TWO masks, and the specimen here cannot see it.

    Connect a blend node's `opacity` input and the compiler moves the slider from bits
    (4, 5) to bits (9, 10), leaving (4, 5) reading state 11 -- the image-input code. Rokviz
    has nine such records and states no slider on any of them, so the render checks above
    pass whether this field is read or dropped. `ChesterfieldSofa` has three, and its
    shipped `.sbs` states what they are, which is why the assertion is written against that
    file and skips when the corpus is absent.

    Dropping the field composites at full strength: 1,133 corpus records, 963 of them a
    stated constant as low as 0.05.
    """
    hits = glob.glob(os.path.join(ROOT, '**', 'ChesterfieldSofa.sbsasm'), recursive=True)
    if not hits:
        return _skip('test_blend_reads_the_relocated_opacity: no ChesterfieldSofa')
    asm = sbsasm.Assembly(hits[0])
    #: index -> the `opacitymult` its source node states, from `ChesterfieldSofa.sbs`.
    want = {356: 0.73, 859: 0.40, 871: 0.20}
    got = {}
    for rec in asm.records:
        if rec.filter_name != 'blend' or len(rec.words) < 2:
            continue
        w1 = rec.words[1]
        if (w1 >> 9) & 3:
            assert (w1 >> 4) & 3 == 3, \
                'record %d relocates its opacity while (4, 5) is not the image-input ' \
                'code -- the two arms are not exclusive after all' % rec.index
            v = model.View(asm, rec)
            got[rec.index] = v.baked('opacitymult')
    assert set(got) == set(want), \
        'the relocated-opacity records moved: %r, expected %r' % (sorted(got), sorted(want))
    bad = [(i, got[i], want[i]) for i in want
           if got[i] is None or abs(got[i] - want[i]) > 5e-4]
    assert not bad, 'the walk no longer reads the source\'s own opacity: %r' % (bad,)
    # AND THE GUARD FIRES. `model` refuses a record that sets both arms, on the strength
    # of "it never happens" -- 1,133 of 1,133. A refusal nothing has ever seen refuse is
    # indistinguishable from no refusal at all, so set both arms on a record that passes
    # and watch it. The unmodified record goes through the same shim as the control: a
    # broken shim would raise here too, and prove nothing about the guard.
    class _Reworded(object):
        def __init__(self, r, words):
            object.__setattr__(self, '_r', r)
            object.__setattr__(self, 'words', words)

        def __getattr__(self, k):
            return getattr(object.__getattribute__(self, '_r'), k)

    rec = asm.records[356]
    assert model.View(asm, _Reworded(rec, list(rec.words))).has('opacitymult')
    both_arms = list(rec.words)
    both_arms[1] = (both_arms[1] & ~0x30) | 0x10        # (4, 5) baked, (9, 10) still baked
    try:
        model.View(asm, _Reworded(rec, both_arms))
    except model.Shifted:
        pass
    else:
        raise AssertionError('a record setting both opacity arms was accepted')
    print('ok  test_blend_reads_the_relocated_opacity (%d records)' % len(got))


def test_hsl_names_its_three_parameters():
    """`hsl` states hue, saturation and luminosity in the CLASS word, and each defaults to
    the neutral 1/2 -- so a parameter this legend fails to name is not a missing value, it
    is a silent identity. All 747 corpus records were exactly that until the legend grew
    filter 14.

    The values are the shipped source's, not a fit: `ChesterfieldSofa.sbs` states
    `saturation` 0.65 with `luminosity` 0.60 on one node and `saturation` 0.58 on another,
    and a third node leaves all three dynamic -- which is the record that has to come back
    as three PROGRAMS, or the bit pairing is wrong in a way constants cannot show.
    """
    hits = glob.glob(os.path.join(ROOT, '**', 'ChesterfieldSofa.sbsasm'), recursive=True)
    if not hits:
        return _skip('test_hsl_names_its_three_parameters: no ChesterfieldSofa')
    asm = sbsasm.Assembly(hits[0])
    baked = {351: {'saturation': 0.58},
             866: {'saturation': 0.65, 'luminosity': 0.60}}
    for index, want in sorted(baked.items()):
        v = model.View(asm, asm.records[index])
        for name, value in want.items():
            got = v.baked(name)
            assert got is not None and abs(got - value) < 5e-4, \
                'record %d %s reads %r, the source states %r' % (index, name, got, value)
        assert set(v.params) == set(want), \
            'record %d names %r, the source states %r' % (index, sorted(v.params),
                                                         sorted(want))
    # The all-dynamic node: three PROGRAM arms, which is what pairs the odd bits with the
    # even ones. A legend that only got the baked bits right would name nothing here.
    v = model.View(asm, asm.records[864])
    assert {k: p.kind for k, p in v.params.items()} == \
        {'hue': 'program', 'saturation': 'program', 'luminosity': 'program'}, \
        'the all-dynamic hsl record names %r' % ({k: p.kind for k, p in v.params.items()},)
    print('ok  test_hsl_names_its_three_parameters (3 records)')


def test_normal_declares_the_field_that_shifts_its_intensity():
    """A field with a zero-word baked arm still has a one-word PROGRAM arm.

    `normal` declares three w1 fields and this legend named one. Fields 1 and 2 cost
    nothing baked -- the mask state is the value -- so leaving them out of the legend looked
    free. It is not: with `intensity` also a program, the end-anchored placement charges one
    width where the record spent two, and `intensity` reads field 1's pointer. 38 corpus
    records are in that state and the program they were running returns 0.0 on every one --
    a flat normal map where the file says 5.

    Asserted on the VALUES the two programs return, not on the slots alone: a placement that
    is off by one still yields a float, and a slot number does not say which program ran.
    """
    hits = glob.glob(os.path.join(ROOT, '**', 'stone_stylized_adaptive.sbsasm'),
                     recursive=True)
    if not hits:
        return _skip('test_normal_declares_the_field_that_shifts_its_intensity: no specimen')
    asm = sbsasm.Assembly(hits[0])
    v = model.View(asm, asm.records[18])
    assert v.rec.filter_name == 'normal', 'record 18 is %r' % (v.rec.filter_name,)
    kinds = {k: p.kind for k, p in v.params.items()}
    assert kinds == {'intensity': 'program', 'inversedy': 'program'}, \
        'record 18 names %r' % (kinds,)
    assert v.params['intensity'].slot < v.params['inversedy'].slot, \
        'the fields are placed in descending mask order'
    ctx = Context(asm)
    got = {n: float(np.asarray(ctx.run(v, v.params[n].value, 1)).ravel()[0])
           for n in ('intensity', 'inversedy')}
    assert abs(got['intensity'] - 5.0) < 1e-6 and abs(got['inversedy']) < 1e-6, \
        'the two programs return %r; intensity 5.0 is the file\'s, 0.0 is inversedy\'s' \
        % (got,)
    print('ok  test_normal_declares_the_field_that_shifts_its_intensity')


def test_distance_reads_the_radius_its_source_states():
    """`distance`'s radius, and the one case the source cannot reach.

    SandyStonePath states 56.2999992 and 64.2200012 on its two distance nodes; records 3
    and 180 of the compiled twin hold exactly those at w1 field 0. Where field 1 holds a
    PROGRAM there is no such witness, and the walk's placement is demonstrably wrong there
    -- every candidate slot on those records holds a pointer, which reads as 0.0 -- so
    `f_distance` keeps its own locator for them. Both halves are asserted, because the
    naming without the exception would render a radius of zero on 188 corpus records.
    """
    hits = glob.glob(os.path.join(ROOT, '**', 'StylizedCobblestoneStreet.sbsasm'),
                     recursive=True)
    if not hits:
        return _skip('test_distance_reads_the_radius_its_source_states: no specimen')
    asm = sbsasm.Assembly(hits[0])
    for index, want in ((3, 56.3), (180, 64.22)):
        v = model.View(asm, asm.records[index])
        got = v.baked('distance')
        assert got is not None and abs(got - want) < 5e-3, \
            'record %d reads %r, the source states %r' % (index, got, want)
    # THE EXCEPTION NEEDS ITS OWN SPECIMEN: this pack has no distance record whose field 1
    # holds a program, so asserting it here would assert nothing. PavingStones does -- and
    # what the walk names on those records is a pointer, which reads as 0.0.
    other = glob.glob(os.path.join(ROOT, '**', 'PavingStonesSubstance003_COMPILED.sbsasm'),
                      recursive=True)
    checked = 0
    if other:
        asm2 = sbsasm.Assembly(other[0])
        for rec in asm2.records:
            if (rec.filter_name != 'distance' or len(rec.words) < 2
                    or (rec.words[1] >> 2) & 3 != 2):
                continue
            got = model.View(asm2, rec).baked('distance')
            checked += 1
            assert got is None or abs(got) < 1e-30, \
                'record %d: field 1 holds a program and field 0 reads %r, a plausible ' \
                'radius -- f_distance\'s exception may no longer be needed' % (rec.index, got)
        assert checked, 'PavingStones no longer has a program-arm distance record'
    print('ok  test_distance_reads_the_radius_its_source_states (2 values from the source, '
          '%d program-arm records)' % checked)


def test_the_size_slot_is_the_walks_placement_not_the_blocks_start():
    """`size_slot` is where the class walk PUT bit 16, and nothing reconstructs it.

    The retired rule took `prog` -- where the class BLOCK starts -- which is the same word
    only when no costing class bit precedes bit 16. It differs on 7,590 records over 120
    files, and it survived because `walk_programs` unions the size slot with every class
    slot: the right word was in the candidate list either way, so a wrong `size_slot` never
    had to be right. That is why this asserts the FIELD rather than a render.

    ChesterfieldSofa is the specimen because Rokviz cannot see it: 0 of its 70 records have
    a class bit costing a word before bit 16, while Chesterfield has 28 that do.
    """
    hits = glob.glob(os.path.join(ROOT, '**', 'ChesterfieldSofa.sbsasm'), recursive=True)
    if not hits:
        return _skip('test_the_size_slot_is_the_walks_placement: no ChesterfieldSofa')
    import decompose
    asm = sbsasm.Assembly(hits[0])
    disagree, checked, clashes = 0, 0, 0
    for rec in asm.records:
        d = decompose.decompose(rec)
        if not d:
            continue
        v = model.View(asm, rec)
        placed = dict((b, sl) for (b, sl, _n) in d.get('cls_params', ())).get(16)
        if placed is not None:
            checked += 1
            # ONE EXCEPTION, AND IT IS EVIDENCE, NOT SLACK. On this specimen's `normal`
            # records the class walk puts bit 16 on the slot the end-anchored parameter
            # block owns -- and the SOURCE says the parameter is right: ChesterfieldSofa
            # states `intensity` 10 on its one normal node and that slot holds 10.0. The
            # size slot is dropped there rather than handing `walk_programs` a float as a
            # program address, and the clash is reported through `View.ignored`.
            clash = any(e[0] == 'clash' for e in v.ignored)
            if clash:
                clashes += 1
                assert v.size_slot is None and placed in {
                    p.slot for p in v.params.values() if p.slot is not None}, \
                    'record %d: a clash was reported and bit 16 at %r is not on a named ' \
                    'parameter' % (rec.index, placed)
            else:
                assert v.size_slot == placed, \
                    'record %d: size_slot %r, the walk placed bit 16 at %r' \
                    % (rec.index, v.size_slot, placed)
            if d.get('prog') is not None and placed != d['prog']:
                disagree += 1
        if v.size_slot is not None:
            assert 0 <= v.size_slot < len(rec.words), \
                'record %d: size_slot %d is outside its %d words' \
                % (rec.index, v.size_slot, len(rec.words))
    assert checked > 0, 'no record on this specimen places a size expression'
    assert disagree >= 28, \
        'only %d records here distinguish the walk from the block start -- this specimen ' \
        'can no longer catch the regression it was chosen for' % (disagree,)
    assert clashes, \
        'no record here reports a placement clash, and this specimen has one -- the guard ' \
        'that drops a size slot landing on a named parameter is not running'
    print('ok  test_the_size_slot_is_the_walks_placement_not_the_blocks_start '
          '(%d placed, %d where the retired rule differs, %d clash with a parameter)'
          % (checked, disagree, clashes))


#: (form) -> (a two-stop table in that layout, what a ramp indexed at 0, 0.5 and 1 must
#: give). Written out per form because the four are what `sbsasm.RAMP_FORMS` states and the
#: two rare ones -- 2 greyscale-float records in 651 files, and 33 colour-float -- are not
#: reliably in reach of any file sweep. The u16 rows carry the trailing midpoint word, so
#: they also assert that a reader ignoring it reads the rest correctly.
RAMP_CASES = {
    'grey-u16':   ([(0, 0, 32768), (65535, 65535, 32768)],
                   [[0.0], [0.5], [1.0]]),
    'grey-float': ([(0.0, 0.25, -1.0), (1.0, 0.75, -1.0)],
                   [[0.25], [0.5], [0.75]]),
    # Real entries, from `stone_stylized_adaptive` record 337: lo | hi<<16 is RGBA bytes,
    # so 0xFF000000 is opaque black and 0xFFFFFFFF opaque white.
    'rgba-u16':   ([(0, 0, 65280, 32768), (65535, 65535, 65535, 32768)],
                   [[0.0, 0.0, 0.0, 1.0], [0.5, 0.5, 0.5, 1.0], [1.0, 1.0, 1.0, 1.0]]),
    # Six components and five: both are this form, and the reader slices 1:5 from each.
    'rgba-float': ([(0.0, 1.0, 0.0, 0.0, 1.0, -1.0), (1.0, 0.0, 0.0, 1.0, 1.0)],
                   [[1.0, 0.0, 0.0, 1.0], [0.5, 0.0, 0.5, 1.0], [0.0, 0.0, 1.0, 1.0]]),
}


class _RampView:
    """The least `f_gradient` needs: a record that states its ramp, and a size."""

    def __init__(self, got, w=3, h=1):
        self.rec = type('_RampRec', (), {'read_ramp': lambda _self, g=got: g})()
        self._wh = (w, h)

    def size(self, cap):
        return self._wh


class _RampCtx:
    """An input whose channel 0 sweeps 0 -> 1 across the row, so the ramp is read at its
    two ends and its middle."""

    cap = 64

    def sample(self, v, k, pos):
        W, H = v.size(self.cap)
        return np.linspace(0.0, 1.0, W * H, dtype=np.float32)[:, None]


def test_the_gradient_reads_the_layout_the_record_states():
    """`f_gradient` used to ask `isinstance(table[0][0], float)` -- a Python type standing
    in for a decode `Record.read_ramp` had already made from the colour flag and the span.

    It was not wrong. Over 41,092 corpus gradient records the type agreed with the record
    every time, which is why it sat there: a reading that cannot fail reports nothing. What
    it could not do is survive a fifth layout, and it was already blind to a distinction it
    happened not to need -- a greyscale float entry and a greyscale u16 entry carrying a
    midpoint are both three components, so length does not separate them and only the
    decode's own statement does.

    Three assertions. The reader covers exactly the forms the decoder can state, so a new
    layout fails HERE and not at whichever record first reaches it. Each of the four decodes
    to the right colours -- which the old branch never checked, and the two rare forms (4
    greyscale-float records in 651 files) no sweep would reach. And a form or an entry the
    reader cannot read refuses out loud rather than slicing a short entry into silence.
    """
    assert set(filters_mod._RAMP_WIDTH) == set(sbsasm.RAMP_FORMS), (
        'the gradient reader covers %r and the decode states %r -- a layout with no reader '
        'raises at render time, on whichever record happens to carry it'
        % (sorted(filters_mod._RAMP_WIDTH), sorted(sbsasm.RAMP_FORMS)))

    ctx = _RampCtx()
    for form, (table, want) in sorted(RAMP_CASES.items()):
        img = filters_mod.f_gradient(ctx, _RampView((form, table)))
        got = np.asarray(img, np.float32).reshape(3, -1)
        assert got.shape == np.asarray(want).shape, \
            '%s: read %r components, expected %r' % (form, got.shape, np.shape(want))
        assert np.allclose(got, np.asarray(want, np.float32), atol=2e-3), \
            '%s: the ramp reads %r, not %r' % (form, got.tolist(), want)

    # AND IT CAN FIRE, on both halves of the guard.
    for why, bogus in (('an unknown form', ('rgba-u32', [(0, 1, 2, 3)])),
                       ('an entry too short for its form', ('rgba-u16', [(0, 1), (1, 2)]))):
        try:
            filters_mod.f_gradient(ctx, _RampView(bogus))
        except filters_mod.Unsupported:
            pass
        else:
            assert False, '%s rendered instead of refusing: %r' % (why, bogus)

    # The corpus half: this is what licenses deleting the type test -- the form the record
    # states and the values it yields never disagree.
    files = sorted(glob.glob(os.path.join(ROOT, '**', '*.sbsasm'), recursive=True))[:120]
    if not files:
        print('ok  test_the_gradient_reads_the_layout_the_record_states '
              '(%d forms, no .sbsasm files to sweep)' % len(RAMP_CASES))
        return
    seen, bad, n = {}, [], 0
    for path in files:
        for r in sbsasm.Assembly.cached(path).records:
            if r.filter_id != 0:
                continue
            got = r.read_ramp()
            if not got:
                continue
            form, table = got
            seen[form] = seen.get(form, 0) + 1
            n += 1
            if form not in sbsasm.RAMP_FORMS:
                bad.append((os.path.basename(path), r.index, form, 'not a stated form'))
            elif any(isinstance(e[0], float) != form.endswith('float') for e in table):
                bad.append((os.path.basename(path), r.index, form, 'entries are not that'))
            elif len(table[0]) < filters_mod._RAMP_WIDTH[form]:
                bad.append((os.path.basename(path), r.index, form, len(table[0])))
    assert not bad, 'records whose ramp entries are not what the form says: %r' % (bad[:8],)
    print('ok  test_the_gradient_reads_the_layout_the_record_states (%d forms read, '
          '%d records swept: %r)' % (len(RAMP_CASES), n, sorted(seen.items())))


def test_the_legend_agrees_with_the_shipped_sources():
    """The legend, checked against the packages' own `.sbs` -- continuously, not once.

    `tools/sourcematch.py` is the arbiter that named `blend`'s relocated opacity, `hsl`'s
    three, `normal`'s intensity and `distance`'s radius: a source states `saturation 0.65`
    and one slot of the compiled twin holds 0.65. Two things are asserted here.

    First that the tool still re-derives all nine of those namings -- a matcher whose output
    is "here is what matched" reports nothing when it is broken, which looks exactly like a
    clean run.

    Second that where a confirmed match lands on a location this legend NAMES, the two agree
    on the name. That is the check that would have caught a legend drifting away from the
    format, and it is independent evidence: the values come from the source XML, not from
    anything `model` computed.
    """
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import sourcematch
    if not sourcematch.pairs(os.path.join(ROOT, 'archive', 'specimens')):
        return _skip('test_the_legend_agrees_with_the_shipped_sources: no source pairs')
    lost = sourcematch.verify(ROOT)
    assert not lost, 'sourcematch no longer re-derives what it was built from: %r' % (lost,)

    ids = _filter_ids()
    disagree, checked = [], 0
    for sbs, asm in sourcematch.pairs(os.path.join(ROOT, 'archive', 'specimens')):
        for filter_name, param, loc, row in sourcematch.match(sbs, asm):
            if row['verdict'] != 'CONFIRMED':
                continue
            fid = ids.get(filter_name)
            kind, which = loc
            if kind not in ('cls', 'w1'):
                continue                      # an end-relative window names no field
            # A W1 FIELD CAN CARRY TWO NAMES, and taking the first is how this check
            # first reported `directionalwarp` disagreeing with itself. Its `intensity` is
            # mask 0x6 and its `warpangle` 0x18, so field 1 -- bits (2, 3) -- holds one bit
            # of each: the straddle SPEC 13.4 warns about, arriving as a false positive in
            # the check written to catch drift. Every name whose mask touches the field is
            # a candidate, and agreement means the source's name is among them.
            if kind == 'cls':
                entry = model.CLS_NAMES.get(fid, {}).get(which)
                names = {entry[0]} if entry else set()
            else:
                names = {nm for (mask, _sh, nm, _k) in model.W1_PARAMS.get(fid, ())
                         if nm and mask & (3 << (2 * which))}
            if not names:
                continue                      # unnamed here: the inventory's business
            checked += 1
            if param not in names:
                disagree.append((filter_name, loc, 'legend says %r' % sorted(names),
                                 'the source says %r' % param))
    assert checked >= 5, 'only %d legend entries were checked against a source' % checked
    assert not disagree, 'the legend and the sources disagree: %r' % (disagree,)
    print('ok  test_the_legend_agrees_with_the_shipped_sources (%d namings re-derived, '
          '%d legend entries confirmed)' % (len(sourcematch.EXPECTED), checked))


def test_every_record_renders():
    path = specimen()
    if not path:
        return _skip('test_every_record_renders: no specimen')
    asm = sbsasm.Assembly(path)
    outs, fails, info = render(asm, max_dim=128)
    assert not fails, 'records failed with no assumption scope: %r' % (fails,)
    assert len(outs) == len(asm.records)
    # THE RENDER REPORTS WHAT IT DECLINED TO READ. Not an error and not low-confidence --
    # the walk placed these fields, so the layout is right -- but a count that exists is the
    # difference between `hsl` being an identity in 747 records and nobody noticing.
    ignored = info['ignored']
    assert ignored, ('nothing reported as ignored on a specimen that has 7 such records -- '
                     'the channel is not wired, which is exactly the silence it exists to '
                     'break')
    for i, entries in ignored.items():
        w0 = asm.records[i].words[0]
        w1 = asm.records[i].words[1] if len(asm.records[i].words) > 1 else 0
        for (half, which, _slot, _w) in entries:
            stated = (w0 >> which) & 1 if half == 'cls' else (w1 >> (2 * which)) & 3
            assert stated, ('record %d is reported as ignoring %s %s and its own word does '
                            'not state it' % (i, half, which))
    print('ok  test_every_record_renders (%d records, %d low-confidence, %d stating a '
          'field no name covers)' % (len(outs), len(info['low_confidence']), len(ignored)))


def test_the_render_threads_its_own_value_cache():
    """0x03/0x06 answered from the Context's dict, with NOTHING installed in the module.

    The two opcodes are cross-record common-subexpression elimination and their indices
    are bare integers with nothing in them naming a file, so a dict every caller can reach
    at once cannot say whose index 3 it is holding. The whole render therefore runs with
    the module global REMOVED -- under an installed one this asserts nothing, because the
    programs would reach it and pass either way.

    The binding is then checked on the mechanism rather than on a record that happens to
    exercise it: `Rokviz` uses no 0x03/0x06 at all (8 of 60 corpus files do), and a test
    that can only fail on a file this repository does not redistribute is a test that
    reports nothing wrong.
    """
    path = specimen()
    if not path:
        return _skip('test_the_render_threads_its_own_value_cache: no specimen')
    asm = sbsasm.Assembly(path)
    prev = sbsruntime.use_shared_cache(None)
    try:
        assert sbsruntime.use_shared_cache(None) is None, \
            'use_shared_cache(None) must REMOVE, or a render cannot be run without one'
        _outs, fails, _info = render(asm, max_dim=64)
        assert not fails, 'records failed with no cache installed: %r' % (fails,)
        assert sbsruntime.use_shared_cache(None) is None, \
            'the render installed a module-global cache'

        # TWO CONTEXTS OVER ONE ASSEMBLY ARE TWO CACHES. Asserted through the compiled
        # program's own namespace, which is where `ops.bind`'s substitution has to land:
        # `prog.__globals__` is the scope the transpiled source imported into.
        a, b = Context(asm), Context(asm)
        ptr = None
        for rec in asm.records:
            v = model.View(asm, rec)
            got = a.walk_programs(v, include_prog_slot=True) if v.walked else []
            if got:
                ptr = got[0]
                break
        assert ptr is not None, 'the specimen names no program to bind'
        fa = ops.bind(asm, ptr, a.cache, a._funcs)
        fb = ops.bind(asm, ptr, b.cache, b._funcs)
        assert fa is not fb, 'two Contexts were handed one compiled program'
        fa.__globals__['cache_write'](np.float32(0.5), 3)
        assert list(a.cache) == [3], 'the write missed its own Context: %r' % (a.cache,)
        assert not b.cache, "the write reached the other Context: %r" % (b.cache,)
        try:
            fb.__globals__['cache_read'](3)
        except sbsruntime.NoSharedCache:
            pass
        else:
            raise AssertionError("one Context read another's cached value")
        print('ok  test_the_render_threads_its_own_value_cache')
    finally:
        sbsruntime.use_shared_cache(prev)


def test_the_fast_sampler_is_the_shared_one():
    """`ops._fast_sampler`'s two specialisations are equalities, DTYPE INCLUDED.

    The dtype assertion is the point of this test, not decoration. The four-corner lerp
    multiplies by `u - u0` with `u0` an int64, so it returns float64 even over a float32
    image, while the exact-texel gather carries the image's dtype unless it is corrected.
    That single difference moved 567 of 3,047 records on PlasticSubstance003 -- and the
    ad-hoc check written alongside the optimisation passed anyway, because it used ONE
    dtype for both the image and the positions. So both are varied here independently.
    """
    rng = np.random.default_rng(20260827)
    shapes = [(256, 256, 1), (16, 16, 4), (128, 128, 3), (100, 60, 2)]   # last is not pow2
    checked = 0
    for H, W, C in shapes:
        img = rng.random((H, W, C))
        gx = np.tile((np.arange(W) + 0.5) / W, H)
        gy = np.repeat((np.arange(H) + 0.5) / H, W)
        cases = {
            # the 62% case: an image sampled at its own pixel centres
            'identity': np.stack([gx, gy], axis=-1),
            # texel centres reached from outside [0, 1], so the wrap is exercised too
            'wrapped': np.stack([gx + 2.0, gy - 3.0], axis=-1),
            'random': np.concatenate([rng.uniform(-3.0, 4.0, (2000, 2)),
                                      np.array([[0.0, 0.0], [1.0, 1.0],
                                                [-1e-9, 1.0 + 1e-9]])]),
        }
        for name, pos in cases.items():
            for idt in (np.float32, np.float64):
                for pdt in (np.float32, np.float64):
                    im, ps = img.astype(idt), pos.astype(pdt)
                    want = sbsruntime.image_sampler(im)(ps)
                    got = ops._fast_sampler(im)(ps)
                    where = '%dx%dx%d %s img=%s pos=%s' % (
                        H, W, C, name, np.dtype(idt).name, np.dtype(pdt).name)
                    assert got.dtype == want.dtype, \
                        '%s: dtype %s, shared gives %s' % (where, got.dtype, want.dtype)
                    assert got.shape == want.shape, \
                        '%s: shape %s, shared gives %s' % (where, got.shape, want.shape)
                    assert np.array_equal(got, want, equal_nan=True), \
                        '%s: max|d| %r' % (where, float(np.nanmax(np.abs(got - want))))
                    checked += 1
    # The identity-grid branch: `pos_grid` for the IMAGE's own dimensions is answered
    # without any index arithmetic, and must agree with the shared sampler to the bit and
    # the dtype -- while a grid for OTHER dimensions must not take that branch at all.
    for H, W, C in [(64, 64, 1), (32, 16, 3)]:
        img = rng.random((H, W, C))
        for idt in (np.float32, np.float64):
            im = img.astype(idt)
            grid = ops.pos_grid(W, H)
            assert not grid.flags.writeable, 'pos_grid must hand back a read-only array'
            assert grid is ops.pos_grid(W, H), 'pos_grid must memoise, or `is` cannot work'
            want = sbsruntime.image_sampler(im)(grid)
            got = ops._fast_sampler(im)(grid)
            assert got.dtype == want.dtype and np.array_equal(got, want), \
                'identity grid %dx%dx%d img=%s' % (H, W, C, np.dtype(idt).name)
            assert got.base is None and not np.shares_memory(got, im), \
                'the identity branch must copy, not alias the record it sampled'
            # a grid of the WRONG size is an ordinary resample, not the identity
            other = ops.pos_grid(W * 2, H * 2)
            assert np.array_equal(ops._fast_sampler(im)(other),
                                  sbsruntime.image_sampler(im)(other)), \
                'a foreign grid took the identity branch'
            checked += 3
    # And the toggle really reaches the shared implementation, so an A/B measures something.
    saved = ops.FAST_SAMPLER
    try:
        ops.FAST_SAMPLER = False
        assert ops.sampler(np.zeros((8, 8, 1))).__qualname__.startswith('image_sampler')
    finally:
        ops.FAST_SAMPLER = saved
    print('ok  test_the_fast_sampler_is_the_shared_one (%d dtype/position combinations)'
          % checked)


def test_reference_agreement_does_not_regress():
    path, refs = specimen(), references()
    if not path or not refs:
        return _skip('test_reference_agreement_does_not_regress: no specimen or maps')
    from PIL import Image
    asm = sbsasm.Assembly(path)
    outs, _fails, _info = render(asm, max_dim=256)
    names = manifest.output_names(asm)

    def load(p):
        im = Image.open(p)
        a = np.asarray(im).astype(np.float64)
        a = a / (65535.0 if (im.mode == 'I;16' or a.max() > 255) else 255.0)
        return a[:, :, :3] if a.ndim == 3 else a[:, :, None]

    def rs(x, n=64):
        return np.stack(
            [np.asarray(Image.fromarray((np.clip(x[:, :, c], 0, 1) * 65535)
                                        .astype(np.uint16)).resize((n, n), Image.BILINEAR),
                        dtype=np.float64) / 65535.0 for c in range(x.shape[2])], axis=-1)

    seen, flat, worse = [], [], []
    height_mean = None
    for uid, _fmt, _grey, ri in asm.outputs():
        nm = (names.get(uid) or '').lower()
        key = re.sub(r'[^a-z]', '', nm)
        if key not in refs or ri not in outs:
            continue
        o = np.asarray(outs[ri], dtype=np.float64)
        if o.ndim == 2:
            o = o[:, :, None]
        if nm == 'height':
            height_mean = float(o.mean())
        a, b = rs(o), rs(load(refs[key]))
        for c in range(min(a.shape[2], b.shape[2])):
            if (nm, c) not in REFERENCE_FLOOR:
                continue
            x, y = a[:, :, c].ravel(), b[:, :, c].ravel()
            seen.append((nm, c))
            if x.std() == 0.0:
                flat.append((nm, c))
                continue
            corr = float(np.corrcoef(x, y)[0, 1])
            if corr < REFERENCE_FLOOR[(nm, c)]:
                worse.append(((nm, c), round(corr, 4), REFERENCE_FLOOR[(nm, c)]))
    assert not flat, 'channels collapsed to a constant: %r' % (flat,)
    assert not worse, 'channels below their floor: %r' % (worse,)
    missing = sorted(set(REFERENCE_FLOOR) - set(seen))
    assert not missing, 'channels no longer produced: %r' % (missing,)
    # The FX emission count arbiter: `height` back-solves to a mask of mean 0.5 through two
    # `levels`, and the engine's own export means 0.78628. A wrong count moves this first.
    assert height_mean is not None and abs(height_mean - 0.7863) < 0.004, \
        'height mean %r is not the engine\'s 0.78628 -- the FX emission count moved' \
        % (height_mean,)
    print('ok  test_reference_agreement_does_not_regress (%d channels, height mean %.5f)'
          % (len(seen), height_mean))



if __name__ == '__main__':
    for fn in (test_every_parameter_a_filter_asks_for_can_be_supplied,
               test_the_declared_fields_the_legend_ignores_are_the_known_ones,
               test_walk_reads_the_parameters_the_memo_cannot,
               test_blend_reads_the_relocated_opacity,
               test_hsl_names_its_three_parameters,
               test_normal_declares_the_field_that_shifts_its_intensity,
               test_distance_reads_the_radius_its_source_states,
               test_the_size_slot_is_the_walks_placement_not_the_blocks_start,
               test_the_gradient_reads_the_layout_the_record_states,
               test_the_legend_agrees_with_the_shipped_sources,
               test_every_record_renders,
               test_the_render_threads_its_own_value_cache,
               test_the_fast_sampler_is_the_shared_one,
               test_reference_agreement_does_not_regress):
        fn()
