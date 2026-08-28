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
import sbsruntime                                                    # noqa: E402
from engine import render                                            # noqa: E402

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
        print('SKIP test_walk_reads_the_parameters_the_memo_cannot: no specimen')
        return
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
        print('SKIP test_every_record_renders: no specimen')
        return
    asm = sbsasm.Assembly(path)
    outs, fails, info = render(asm, max_dim=128)
    assert not fails, 'records failed with no assumption scope: %r' % (fails,)
    assert len(outs) == len(asm.records)
    print('ok  test_every_record_renders (%d records, %d low-confidence)'
          % (len(outs), len(info['low_confidence'])))


def test_the_shared_cache_does_not_outlive_the_render():
    """A cache left installed leaks ANSWERS, not memory, so this asserts both halves.

    The 0x03/0x06 indices are bare integers with nothing in them naming a file. A render
    that leaves its dict in `sbsruntime`'s module global therefore hands the NEXT caller
    this file's value for index 3 where it was owed a `NoSharedCache` saying it needs a
    whole-file run -- and `NoSharedCache` is the guard that exists because "a silently
    wrong cached value is exactly the failure mode this project's own tests exist to
    catch". Restoring is only possible if `None` removes, so that is asserted first; it
    used to install a fresh `{}` and a restore could not reach the default state.

    The first half needs no specimen.
    """
    outer = {}
    prev = sbsruntime.use_shared_cache(outer)
    try:
        sbsruntime.cache_write(np.float32(0.25), 7)
        assert sbsruntime.use_shared_cache(None) is outer, \
            'use_shared_cache must hand back the cache it replaced, or nothing can restore'
        try:
            sbsruntime.cache_read(7)
        except sbsruntime.NoSharedCache:
            pass
        else:
            raise AssertionError('None left a cache installed, so a restore cannot reach '
                                 'the default state a single-program transpile needs')
        path = specimen()
        if not path:
            print('ok  test_the_shared_cache_does_not_outlive_the_render (no specimen: '
                  'removal only)')
            return
        sbsruntime.use_shared_cache(outer)
        render(sbsasm.Assembly(path), max_dim=32, stop_after=0)
        assert sbsruntime.use_shared_cache(outer) is outer, \
            'render did not put back the cache it found'
        assert list(outer) == [7], \
            'render wrote into the caller\'s cache instead of its own: %r' % (list(outer),)
        print('ok  test_the_shared_cache_does_not_outlive_the_render')
    finally:
        sbsruntime.use_shared_cache(prev)


def test_reference_agreement_does_not_regress():
    path, refs = specimen(), references()
    if not path or not refs:
        print('SKIP test_reference_agreement_does_not_regress: no specimen or maps')
        return
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
               test_the_shared_cache_does_not_outlive_the_render,
               test_reference_agreement_does_not_regress):
        fn()
