#!/usr/bin/env python3
"""The sampler specialisations in `ops` are equalities, and this is what says so.

    python3 tools/render2/test_sampler.py

`ops._fast_sampler` answers three cases without the four-corner lerp -- a power-of-two
wrap, a position that lands exactly on a texel, and the render grid for the image's own
dimensions. Each is an ALGEBRAIC identity rather than a cheaper approximation, so the
check here is `array_equal` and an equal dtype against `sbsruntime.image_sampler`, not a
tolerance. `sbsruntime` is deliberately the reference: the shared implementation is not
the thing that changed.

Kept out of `test_render2.py` because it needs no corpus, no specimen and no render -- it
is arithmetic against arithmetic, and it runs in a tenth of a second.
"""
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # see __init__.py: this package goes LAST

import ops                                                          # noqa: E402
import sbsruntime                                                   # noqa: E402


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


if __name__ == '__main__':
    test_the_fast_sampler_is_the_shared_one()
