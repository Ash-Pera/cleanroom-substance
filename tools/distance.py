#!/usr/bin/env python3
"""The `distance` filter (id 21): a distance transform, and where its parameter lives.

Kept out of render.py so the branch there is a call rather than a block -- render.py is
shared and this decode is not finished.

WHAT THE SOURCES DECLARE. 17 permitted files carry a `distance` compNode. Its parameters:

    distance          256 x11, and 5.45 / 56.12 / 56.30 / 64.22 / 105.53 / 0.14, plus 4
                      declared as function graphs
    combinedistance   0 in all 19 sightings -- no contrast, unlocatable from this corpus
    colorswitch / outputsize / tiling   one or two sightings each

UNITS ARE PIXELS AT A 256 REFERENCE, which the values say on their own: every declared
constant lies in [0, 256], 11 of 19 are exactly 256 -- propagate across the whole image,
the natural default -- and corpus-wide the slot that carries 256 most often has a median of
exactly 256 over 913 float-valued reads. A normalised [0, 1] parameter cannot be 256.

THE SLOT IS NOT FIXED, and finding that out took two passes. The first scan put slot 5 at
72.0% own-file containment against a 0.0% control and slot 6 at noise (14.3% against 15.9%).
That was an artifact: `distance` = 256 in more than half the declarations, and a value every
file shares discriminates nothing -- the reason containment.py demands >= 5 decimals. Redone
on values only one file declares:

    slot 4   44.4% own, 0.0% control (n=9)
    slot 5   52.9% own, 0.0% control (n=17)
    slot 6   13.3% own, 0.0% control (n=45)

Three slots, every control zero. That is what a parameter whose position MOVES looks like,
not three candidates. Read against the record's own layout block instead, the best position
is block index 1 at 60.0% against 0.0% (n=15).

WHY NO SLOT IS HARDCODED HERE. 60% on fifteen records is weaker than the 33.7%-against-6.5%
that a parallel session used to place `normal`'s intensity, and that placement was WRONG --
the population was mixed and program pointers read as floats are denormals that pass a
plausibility test. So `distance_param` uses `transformation`'s discriminator instead: take
the record's own filter programs, and if exactly one returns a width-1 value, that is the
parameter; otherwise fall back to a baked float in the block, denormals excluded; otherwise
refuse. A refusal is a correct answer here and a guessed slot is not.

THE KERNEL IS VERIFIED, by a controlled input rather than a distribution. A single lit pixel
at the centre of a 256x256 field, R = 16 and R = 40:

    nonzero radius   15.81 and 39.96   against R = 16 and 40
    value at r = R/2  0.500 exactly, for both
    spread of the value around a fixed radius   0.0155 and 0.0056  (radially symmetric)

Linear, symmetric, and reaching zero at exactly R. What that does NOT establish is the
SIGN convention or whether the mask is the first or second input, both of which need an
output to compare against -- see FORMAT-NOTES on the reference renders.
"""
import struct

import numpy as np

try:
    from scipy import ndimage
except ImportError:                                    # pragma: no cover
    ndimage = None

REFERENCE_PX = 256.0        # the resolution `distance` is expressed against


class Unlocated(Exception):
    """The record's `distance` parameter could not be identified without guessing."""


def distance_param(rec, eval_program, inputs):
    """(value, how) for a record's `distance`, or raise `Unlocated`.

    `eval_program(ptr)` must return the program's value; the caller supplies it so this
    module does not depend on render.py.
    """
    widths = []
    for p in (rec.filter_programs or ()):
        try:
            v = np.asarray(eval_program(p)).ravel()
        except Exception:
            continue
        if v.size == 1 and np.isfinite(v[0]):
            widths.append(float(v[0]))
    if len(widths) == 1:
        return widths[0], 'program'
    if len(widths) > 1:
        # Two width-1 results and no way to say which is `distance`. `transformation`
        # refuses in exactly this case rather than taking the first.
        raise Unlocated('%d width-1 program results; cannot single out `distance`'
                        % len(widths))
    edges = set(rec.layout[0] or ())
    for si in range(2, min(len(rec.words), 9)):
        if si in edges:
            continue
        f = struct.unpack('<f', struct.pack('<I', rec.words[si]))[0]
        # Denormals are program pointers read as float32. Accepting them is what put a
        # parallel session's `normal` intensity in the wrong slot.
        if 1e-3 < abs(f) <= REFERENCE_PX:
            return float(f), 'baked slot %d' % si
    raise Unlocated('no program and no plausible baked float in the block')


def distance_field(mask, radius_px):
    """Distance transform of `mask`, normalised so it reaches 0 at `radius_px`.

    1 on the mask, falling linearly with euclidean distance. Verified against a single-pixel
    input: radially symmetric, exactly 0.5 at half the radius, zero at the radius.
    """
    if ndimage is None:
        raise Unlocated('scipy is not available')
    m = np.asarray(mask, dtype=np.float32)
    if m.ndim == 3:
        m = m[:, :, 0]
    on = m > 0.5
    if not on.any():
        return np.zeros(m.shape, dtype=np.float32)
    d = ndimage.distance_transform_edt(~on)
    return np.clip(1.0 - d / max(float(radius_px), 1e-6), 0.0, 1.0).astype(np.float32)


def scale_radius(value, width):
    """`distance` is pixels at REFERENCE_PX; scale it to the grid actually being rendered.

    This is the max_dim trap a parallel session hit on `blur`: a radius of 0.84 px at 256
    rounds to zero at 64, the filter looks like a no-op, and the conclusion looks like a
    broken decode rather than a downsampled grid.
    """
    return float(value) * (float(width) / REFERENCE_PX)
