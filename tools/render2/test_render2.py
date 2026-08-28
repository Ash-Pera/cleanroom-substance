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
#: collapse does not. `normal` and `metallic` are absent on purpose: both are degenerate on
#: this specimen at every resolution this renderer reaches, and a correlation against a
#: near-constant is not evidence. The MEAN is asserted for `height` instead, which is the
#: channel that arbitrates the FX emission count.
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
               test_every_record_renders,
               test_the_render_threads_its_own_value_cache,
               test_reference_agreement_does_not_regress):
        fn()
