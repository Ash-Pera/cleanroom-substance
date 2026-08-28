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


def _walk_params(rec):
    """The record's parameter slots as the WALK enumerates them: [(state, position)].

    Ascending by position, so index 0 is the record's first parameter. `state` is the
    field's two-bit code -- 1 baked, 2 program -- which is what makes reading this slot a
    structural act rather than a guess about its contents.
    """
    try:
        import decompose
        d = decompose.decompose(rec)
    except Exception:
        return []
    if not d:
        return []
    out = []
    for t in d.get('param_slots', ()):
        if len(t) >= 3:
            out.append((t[1], t[2]))
    return sorted(out, key=lambda sp: sp[1])


def _locate_slot(rec, run=None):
    """`distance` from the slot the WALK names, or None.

    THE SLOT COMES FROM THE WALK, NOT FROM ARITHMETIC. This used to compute
    `rec.layout[1] + 1 + class bit 7 + class bit 11` -- `param_slots`' containment-verified
    rule. The walk names the same slot without the arithmetic, and where the two disagree
    the walk is right; both halves of that are measured below.

    "NO BEHAVIOUR CHANGE" WAS MEASURED ON 20 FILES AND IS FALSE ON THE CORPUS. Re-run over
    all 437 corpus files plus the reference packs -- 2,540 `distance` records, both sides
    pinned, only this edit differing -- the two rules part on 80: 69 where the old arm
    refused and this one answers, 0 lost, and 11 where both answer and disagree. A subset
    that showed 112 of 112 identical could not see any of them.

    THE SPLIT IS ENTIRELY cls BIT 0, which the formula has no term for:

        cls bit 0 SET     2,451 records   formula slot == walk parameter, 2,451 of 2,451
        cls bit 0 CLEAR      89 records   formula slot is a walk parameter in 11,
                                          a CLS slot in 11, and a word the walk accounts
                                          to NO field at all in 67

    Where the bit is clear the parameter sits one slot later than the formula predicts.

    AND THE 11 DISAGREEMENTS ARE EXACTLY THE 11 CLS-SLOT CASES -- one to one, nothing else
    lands there. So they are not two readings of one parameter with no way to choose
    between them: the old rule was reading a CLASS-WORD parameter and returning it as
    `distance`. It reads 1.0 in 10 of the 11 (256.0 by the walk), and a constant 1.0 is
    exactly what a misaligned read looks like -- the same 1.0 the 'wide' arm produces from
    the aspect term on a square image, noted in `distance_param` below.

    WHAT CONTAINMENT CAN AND CANNOT SETTLE. `param_slots.locate('distance', 21, 'distance')`
    returns 9 pairings -- the docstring there claiming `distance` pairs zero was calling it
    with the default parameter name `intensity`, which a distance node does not declare.
    On all 9 the containment-verified slot IS a slot the walk enumerates as a parameter, 9
    of 9. But every one of the 9 has cls bit 0 SET, and there are ZERO pairings with it
    clear, so containment confirms the walk on the population where the two rules already
    agree and cannot reach the 89 where they part.

    The 11 therefore rest on structural accounting, not on declared values: the format
    assigns the formula's target to a different field. That is falsifiable -- one permitted
    source declaring a distinctive `distance` on a bit-0-clear record would settle it
    directly -- and no such source exists in what this project may read.

    The remaining 10 of the 69 gains are cls bit 0 SET and come from dropping the
    plausibility window below, not from the slot.

    THE STATE REPLACES THE PLAUSIBILITY WINDOW. The old guard accepted the slot's bytes as
    a float when `1e-3 < abs(f) <= 4.0 * REFERENCE_PX` -- deciding what a word IS from what
    it LOOKS like, and the bound had already been widened once because a fixed 256 refused
    the legitimate 512.0 in `sci_fi_elements_02` records 3733/3734. The walk states the
    field's kind outright: of those 112 records the first parameter is baked in 106 and a
    PROGRAM in 6, and all 6 program-state slots read as denormals when forced through
    float32 -- exactly the "program pointer read as float" that put a parallel session's
    `normal` intensity in the wrong slot. So a program-state slot is declined here and left
    to the program path, on the format's own word rather than on the size of the number.

    A denormal under a BAKED state is a contradiction between the walk and the bytes (4 of
    112), and it is reported as a miss rather than resolved in either direction: the format
    does not bake 1e-40 as a pixel radius, and inventing a reading for it is what this
    module exists not to do. No upper bound is imposed at all now -- 512.0 is a real answer
    on a 512-wide map, and it is the RECORD, not a constant here, that says how wide it is.
    """
    params = _walk_params(rec)
    if not params:
        return None
    state, at = params[0]
    if at >= len(rec.words):
        return None
    if state == 2:
        # THE WALK NAMES WHICH PROGRAM, so "left to the program path" gave away the one
        # thing worth having. That path takes a width-1 result from `rec.filter_programs`
        # and only when there is EXACTLY ONE, so a record with none or several refuses --
        # while the record itself says which slot holds the pointer.
        #
        # HOW OFTEN THIS MATTERS, stated honestly because it is not often. 77 records have
        # state 2 with a valid program at the named slot, but `distance_param`'s first
        # branch already resolves 73 of them: it takes a width-1 result when the record has
        # EXACTLY ONE, and these mostly do. This arm reaches the remaining 4 -- the records
        # with state 2 and NO width-1 program to search at all, so the search has nothing to
        # return and the record still names the pointer. AB_ScrewGeneratorPlus is the whole
        # population; records 123 and 268 go from "no program, and no baked value in a
        # parameter slot the walk names" to rendering, and 17 and 162 stay blocked on an
        # upstream cascade.
        #
        # It is kept for the direction rather than the four: the walk names WHICH program,
        # and the branch above searches for one. A search that happens to find the right
        # answer 73 times is not the same claim as a read.
        #
        # This is the same gap `normal` had at its own walk-named slot: one arm for a baked
        # float, none for a pointer, and a value test that cannot tell them apart because a
        # pointer through float32 is a denormal. `valid_program` decides it structurally.
        if run is None:
            return None                 # caller cannot evaluate; leave it to the program path
        ptr = int(rec.words[at]) + 52
        asm = rec.asm
        if not (asm.body_lo <= ptr < asm.body_hi and asm.valid_program(ptr)):
            return None
        try:
            v = np.asarray(run(ptr)).ravel()
        except Exception:
            return None
        if v.size >= 1 and np.isfinite(v[0]):
            return float(v[0]), 'walk parameter slot %d, PROGRAM (LOW CONFIDENCE)' % at
        return None
    f = struct.unpack('<f', struct.pack('<I', rec.words[at]))[0]
    if not np.isfinite(f) or f == 0.0 or abs(f) < 1e-30:
        return None                     # denormal under a baked state: walk vs bytes
    return float(f), 'walk parameter slot %d (LOW CONFIDENCE)' % at


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
    if not widths and assume.assumed('distance.param') == 'layout':
        # 'layout' IS 'wide' WITH THE PRECEDENCE FIXED. See
        # assume.QUESTIONS['distance.param']: under 'wide' the 2-component reading is tried
        # FIRST and returns before the structural slot rule below is ever consulted -- an
        # ASSUMED reading pre-empting a DERIVED one. On Bricks that costs every distance
        # record its radius, because the component it reads is the aspect term
        # `exp2(min(sizelog2.x - sizelog2.y, 0))`, which is exactly 1.0 on a square image:
        # the file's 126 distance records resolve to just TWO values under 'wide', 1.0 on
        # 121 and 2.0 on 5, and at a 256 reference both are sub-pixel on a 64 grid, so the
        # filter is a no-op either way. Under this arm the same 126 resolve to 22 distinct
        # values.
        #
        # This arm defers to the slot rule and keeps the 2-component reading only for
        # records the rule cannot serve. `_locate_slot` is the same code path the fallback
        # uses; calling it here changes the ORDER and nothing else.
        _slot = _locate_slot(rec, eval_program)
        if _slot is not None:
            return _slot
    if not widths and assume.assumed('distance.param') in ('wide', 'layout'):
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
    _got = _locate_slot(rec, eval_program)
    if _got is not None:
        return _got
    # THE REMAINING PARAMETERS THE WALK NAMES, and only those. This used to be
    # `for si in range(2, min(len(rec.words), 9))` -- a linear sweep over a hardcoded slot
    # window, returning the FIRST word whose float lay in `1e-3 .. REFERENCE_PX`. That is
    # scanning until a number looks right, the same act as the phantom program that
    # `Record.programs` used to manufacture from bytecode: the window decided the answer,
    # and slot 9 was a constant nobody derived. Any word in that range can pass, including
    # an input's record index and a cls slot's unrelated quantity.
    #
    # The walk already enumerates which slots are parameters and which are inputs, so the
    # sweep has nothing left to do: take the record's OWN parameters in order, skip the
    # ones the walk calls programs, and read the baked ones. `distance` records carry one
    # or two parameters (56 and 43 of 112 over 20 files), so this is a second candidate at
    # most, not a scan.
    for state, si in _walk_params(rec)[1:]:
        if si >= len(rec.words) or state == 2:
            continue
        f = struct.unpack('<f', struct.pack('<I', rec.words[si]))[0]
        if not np.isfinite(f) or f == 0.0 or abs(f) < 1e-30:
            continue
        return float(f), 'walk parameter slot %d (LOW CONFIDENCE)' % si
    raise Unlocated('no program, and no baked value in a parameter slot the walk names')


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
