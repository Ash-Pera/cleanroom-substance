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

import assume

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
    if not widths and assume.assumed('distance.param') == 'wide':
        # See assume.QUESTIONS['distance.param']. Component 0 of a 2-component program,
        # for the records whose only programs are 2-component. A candidate under an open
        # scope, never a default.
        for p in (rec.filter_programs or ()):
            try:
                v = np.asarray(eval_program(p)).ravel()
            except Exception:
                continue
            if v.size == 2 and np.isfinite(v[0]) and 1e-3 < abs(float(v[0])) <= REFERENCE_PX:
                return float(v[0]), 'program component 0 (ASSUMED)'
    if len(widths) > 1:
        # Two width-1 results and no way to say which is `distance`. `transformation`
        # refuses in exactly this case rather than taking the first.
        raise Unlocated('%d width-1 program results; cannot single out `distance`'
                        % len(widths))
    # THE FALLBACK, and the reason its hit rate cannot be read as an accuracy.
    #
    # Containment over the block looks poor -- in the population where this fallback
    # actually fires (no width-1 program), the file's declared value is found somewhere in
    # the block in 19 of 88 records, 21.6%, against a 0.0% control. It is tempting to read
    # that as "wrong four times in five". It is not: the rate is CEILINGED by
    # (distinctive values the source declares) / (records the file compiles to), and
    # instancing makes a source with three `distance` nodes compile to thirty records. Most
    # records cannot match any declared value because no declaration corresponds to them.
    #
    # So the 0.0% control is the load-bearing number here and the 21.6% is close to
    # meaningless. Neither this nor a parallel session's 14.6%-vs-2.9% on `blur` means what
    # its denominator suggests.
    #
    # What the fallback returns is therefore marked LOW CONFIDENCE rather than trusted or
    # refused. render.py already has this pattern: `synth_missing_bitmaps` tags outputs
    # built on invented data into a `synthetic` set so a sweep can count them separately
    # instead of reporting them as ordinary successes. A parameter taken from a slot rather
    # than a program is the same kind of claim and deserves the same treatment -- it turns a
    # plausible-wrong into a visible-uncertain, which is the one lesson this decode keeps
    # relearning.
    # THE SLOT IS DERIVABLE, so try the rule before scanning for a plausible-looking
    # number. Containment against permitted sources puts a filter's float parameter at
    # `layout start + 1 + class bit 7 + class bit 11` in 38 of 38 located pairings across
    # six filters, `distance` among them with 9 -- see tools/param_slots.py.
    #
    # It matters here because the scan below bounds the value at REFERENCE_PX, and
    # sci_fi_elements_02 records 3733 and 3734 hold 512.0 at the derived slot: a full-width
    # distance on a 512-wide map, refused as implausible only because the bound is a fixed
    # 256. A structural rule does not have to guess what a plausible number looks like,
    # which is the failure mode the comment above is about.
    #
    # Still LOW CONFIDENCE. The rule is verified on records that DECLARE a value in a
    # paired source; these records are not among them, so the slot is derived and the value
    # in it is read, not confirmed.
    try:
        _e, _start = rec.layout
        _at = _start + 1 + ((rec.cls >> 7) & 1) + ((rec.cls >> 11) & 1)
    except Exception:
        _at = None
    if _at is not None and _at < len(rec.words):
        f = struct.unpack('<f', struct.pack('<I', rec.words[_at]))[0]
        if np.isfinite(f) and 1e-3 < abs(f) <= 4.0 * REFERENCE_PX:
            return float(f), 'slot %d by the layout rule (LOW CONFIDENCE)' % _at
    edges = set(rec.layout[0] or ())
    for si in range(2, min(len(rec.words), 9)):
        if si in edges:
            continue
        f = struct.unpack('<f', struct.pack('<I', rec.words[si]))[0]
        # Denormals are program pointers read as float32. Accepting them is what put a
        # parallel session's `normal` intensity in the wrong slot.
        if 1e-3 < abs(f) <= REFERENCE_PX:
            return float(f), 'baked slot %d (LOW CONFIDENCE)' % si
    raise Unlocated('no program and no plausible baked float in the block')


def is_low_confidence(how):
    """Did `distance_param` fall back to a slot rather than read a program?

    A caller that renders on a low-confidence parameter should record the output the way
    render.py records a synthesised bitmap -- produced, but not on the file's own evidence.
    """
    return 'LOW CONFIDENCE' in how


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


def propagate(mask, radius_px, source):
    """`source`'s value at the nearest ON pixel of `mask`, as an (H, W, C) array.

    The companion to `distance_field`: that answers HOW FAR the nearest lit pixel is, this
    answers WHAT WAS THERE. Both come out of one `distance_transform_edt` call --
    `return_indices` hands back the coordinates the distance was measured to, so this costs
    an index rather than a second transform.

    WHY A SECOND EDGE IS READ AT ALL. A distance transform's field is scalar by
    construction, so a `distance` record whose header says COLOUR cannot be emitting one.
    Over 444 files (the 437-file corpus plus the 7 reference-shipping packages) the 1,693
    two-edge `distance` records fall into exactly two header shapes and no others:

        record greyscale, edge0 greyscale, edge1 greyscale   1,571
        record COLOUR,    edge0 greyscale, edge1 COLOUR        122

    Edge 0 is greyscale in 1,693 of 1,693 -- it is never the thing being carried -- and the
    record's own colour bit equals EDGE 1's in 1,693 of 1,693. The output's width follows
    edge 1, which is read from three header bits and involves no rendering and no fitting.
    That is what says edge 1 is the source; WHAT IS DONE WITH IT is the modelled part and
    is arbitrated through `assume.QUESTIONS['distance.propagate']`.
    """
    if ndimage is None:
        raise Unlocated('scipy is not available')
    m = np.asarray(mask, dtype=np.float32)
    if m.ndim == 3:
        m = m[:, :, 0]
    src = np.asarray(source, dtype=np.float32)
    if src.ndim == 2:
        src = src[:, :, None]
    on = m > 0.5
    if not on.any():
        return np.zeros(m.shape + (src.shape[2],), dtype=np.float32)
    _d, idx = ndimage.distance_transform_edt(~on, return_indices=True)
    return src[idx[0], idx[1], :]


def scale_radius(value, width):
    """`distance` is pixels at REFERENCE_PX; scale it to the grid actually being rendered.

    This is the max_dim trap a parallel session hit on `blur`: a radius of 0.84 px at 256
    rounds to zero at 64, the filter looks like a no-op, and the conclusion looks like a
    broken decode rather than a downsampled grid.
    """
    return float(value) * (float(width) / REFERENCE_PX)
