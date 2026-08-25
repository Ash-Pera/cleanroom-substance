#!/usr/bin/env python3
"""One place for "does this image vary", because the obvious spelling is silently wrong.

`max(x) - min(x) > eps` and `std(x) > eps` both evaluate to **False** on an all-NaN image,
because every comparison with NaN is False. So a NaN output is classified FLAT by the
obvious test, in silence -- it does not raise, it does not warn, and it lands in the wrong
column of every flat/spatial split. Two sessions independently copied that spelling into
their scratchpads.

Measured, over 120 files:

    declared outputs rendered   186    flat 105, spatial 81, NON-FINITE 0
    all records rendered     54,623    flat 50,102, spatial 4,208,
                                       NON-FINITE 298 all + 15 partial  (0.6%)

So the declared-output figures published in FORMAT-NOTES are unaffected -- no NaN among them
-- and record-level flat counts overstate by about 0.5%. Small, real, and it was invisible
until someone printed a diff and got `nan` back.

`classify` returns four states rather than a boolean because 'non-finite' is not a kind of
flat: a record producing NaN is a defect to investigate, and a record producing a constant
is usually correct behaviour.
"""
import numpy as np

DEFAULT_EPS = 0.01


def _chan(x):
    a = np.asarray(x, dtype=float)
    return a[:, :, None] if a.ndim == 2 else a


def classify(x, eps=DEFAULT_EPS):
    """'spatial' | 'flat' | 'non-finite' | 'non-finite-partial'."""
    a = _chan(x)
    finite = np.isfinite(a)
    if not finite.all():
        return 'non-finite' if not finite.any() else 'non-finite-partial'
    return 'spatial' if spread(a, eps=None) > eps else 'flat'


def spread(x, eps=DEFAULT_EPS):
    """Largest PER-CHANNEL standard deviation, or NaN if the image is not finite.

    Per channel because a constant-but-coloured image -- a flat normal map at
    (0.5, 0.5, 1.0) -- has zero spatial variation and a whole-array statistic sees 0.5.
    That error inflated one published figure from 8 to 13 before it was caught.
    """
    a = _chan(x)
    if not np.isfinite(a).all():
        return float('nan')
    v = max(float(a[:, :, c].std()) for c in range(a.shape[2]))
    return v


def varies(x, eps=DEFAULT_EPS):
    """True only for a finite image that actually varies. NaN is never 'varies'."""
    return classify(x, eps) == 'spatial'
