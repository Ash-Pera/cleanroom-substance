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
    disagree, checked = 0, 0
    for rec in asm.records:
        d = decompose.decompose(rec)
        if not d:
            continue
        v = model.View(asm, rec)
        placed = dict((b, sl) for (b, sl, _n) in d.get('cls_params', ())).get(16)
        if placed is not None:
            checked += 1
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
    print('ok  test_the_size_slot_is_the_walks_placement_not_the_blocks_start '
          '(%d placed, %d where the retired rule differs)' % (checked, disagree))


def test_every_record_renders():
    path = specimen()
    if not path:
        return _skip('test_every_record_renders: no specimen')
    asm = sbsasm.Assembly(path)
    outs, fails, info = render(asm, max_dim=128)
    assert not fails, 'records failed with no assumption scope: %r' % (fails,)
    assert len(outs) == len(asm.records)
    print('ok  test_every_record_renders (%d records, %d low-confidence)'
          % (len(outs), len(info['low_confidence'])))


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
    for fn in (test_walk_reads_the_parameters_the_memo_cannot,
               test_blend_reads_the_relocated_opacity,
               test_hsl_names_its_three_parameters,
               test_normal_declares_the_field_that_shifts_its_intensity,
               test_the_size_slot_is_the_walks_placement_not_the_blocks_start,
               test_every_record_renders,
               test_the_render_threads_its_own_value_cache,
               test_reference_agreement_does_not_regress):
        fn()
