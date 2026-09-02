#!/usr/bin/env python3
"""Candidate assumptions used by rendering and sweep tools.

The registry is deliberately opt-in: without a scope, callers keep their existing
defaults. ``scope()`` validates registered enumerated choices, tracks records rendered
under a choice in ``USED``, and restores the previous state when it exits.
"""
import contextlib


# Empty tuples identify free-form values; other entries list the candidates a scope may use.
QUESTIONS = {
    'blur.intensity':     ('program', 'slot3'),
    'warp.reference_px':  ('record', 256.0, 64.0, 128.0, 320.0, 384.0, 448.0, 512.0,
                           640.0, 768.0, 1024.0, 2048.0),
    'dirwarp.edges':      ('declared', 'swapped'),
    # NORMAL'S INTENSITY WHEN THE SOURCE OMITTED IT. Not a placement question -- the
    # placement is settled (`header_words - 1`, 8 of 8 containment pairings). This is the
    # 389 corpus records whose last header slot holds a PROGRAM POINTER rather than a
    # parameter, because the source declared no intensity and the header ends one word
    # earlier. See render.py's normal branch for the census and the twin that proves it.
    #
    # THE VALUE IS IN NEITHER FILE, so no decoding recovers it, and the packs cannot
    # arbitrate it either: on UHL3D-Stylized_Sand_with_Rocks_01 every arm from 0.5 to 16.0
    # produces byte-identical record and failure counts (2,349 / 968), because what the arm
    # unblocks is still blocked further downstream. Kept 'refuse' by default.
    #
    # DO NOT ARGUE THE DEFAULT FROM A HOLE IN THE DISTRIBUTION. The same tempting argument
    # is available here as for warp -- 1.0 is absent from the baked values -- and it is
    # refuted the same way: in `blur`, 1.0 is the MODAL baked value at 10,200 of 14,931, so
    # this compiler plainly does not omit parameters merely because they equal a default.
    'normal.default_intensity': ('refuse', 0.5, 1.0, 2.0, 4.0, 8.0, 16.0),
    'blur.kernel':        ('box', 'gaussian'),
    'emboss.probe':       ('passthrough',),
    # 'word1bit2' is the archived renderer's reading -- bit 2 as a BOOLEAN, which sees
    # a baked flag and misses the 38 corpus records whose field 1 holds a program.
    # 'field1' reads the two-bit code the walk declares, both arms.
    'normal.inversedy':   ('ignore', 'word1bit2', 'field1'),
    # THE GRID `normal`'s INTENSITY IS EXPRESSED AGAINST. Default 256.0 -- a constant, not
    # the record's size. Measured against the engine's own exports, with no render of ours
    # in the loop: regressing the exported normal map's slope on the exported height map's
    # per-pixel gradient gives 160.005 on Chesterfield (2048 px, intensity 10) and 9.397 on
    # Rokviz (4096 px, intensity 0.25), against 160.000 and 9.405 predicted by a fixed 256
    # and 20.000 and 0.588 predicted by the record's own width. 'record' restores the older
    # reading, which is what `_reference_px` still returns for blur/warp/dirmotionblur.
    'normal.reference_px': (256.0, 'record', 64.0, 128.0, 512.0, 1024.0, 2048.0, 4096.0),
    'distance.param':     ('program', 'block1', 'slot5', 'wide', 'layout'),
    'distance.invert':    (False, True),
    'distance.mask_edge': (0, 1),
    'distance.propagate': ('field', 'nearest'),
    'fx.profile':         ('rect', 'square', 'disc', 'paraboloid', 'bell', 'gaussian',
                           'thorn', 'pyramid', 'brick', 'gradation', 'waves', 'halfbell',
                           'ridgedbell', 'crescent', 'capsule', 'cone'),
    'fx.sizeless':        ('fill', 'skip', 'half', 'quarter'),
    'fx.rootentry':       ('draw', 'skip'),
    'emboss.intensity':   ('program', 'reference'),
    'fx.gridcount':       ('numberadded', 'divisor'),
    # WHAT `$pos` IS INSIDE AN FX-MAP. It is NOT the sampling coordinate it is in a
    # `pixelprocessor`, and the split is clean: of the programs that read `$pos`, 54,661 of
    # 55,462 pixelprocessor ones feed `samplelum`/`samplecol` (98.6%) against 17 of 26,803
    # fxmaps ones (0.06%). That is the residue in `sbsruntime.SYSVARS`' own note -- $pos
    # feeds a sampler in 34,180 of 86,627 uses -- resolved: the sampling half is
    # pixelprocessor's and the rest is FX-Map gates.
    #
    # ITS CONSUMER IS THE GATE. Of 26,741 fxmaps records whose chain reads $pos, 26,591 read
    # it in the program of an 0x89 gate and 150 in the stepper's; only 34 records read it in
    # a NAMED ENTRY PARAMETER at all (patternrotation 41, opacity 4, frameoffset 2). It is a
    # predicate input, not a placement one, read two-component in 26,907 of 26,907 reads and
    # immediately ADDED in 99.5% of them -- a base the node's own scanned offset is measured
    # from. The idiom is `$pos + <offset the program advances itself>` tested against a
    # float4 rectangle the record bakes: a cull, not a placement.
    #
    # THE RECORD'S OWN RECTANGLE ARBITRATES THE VALUE, and it is a mechanism rather than a
    # fit: the bounds are whole or half integers and the walk steps by whole units, so only
    # `$pos` = 0 puts the scan on the lattice the bounds are aligned to. Emissions against
    # the integer cells the rectangle encloses:
    #
    #     Rokviz 1/3     [-13, 14, -13, 14]         27x27 =    729    origin 729    corner 676
    #     Rokviz 10/12   [-49.5, 50.5, ...]        100x100 = 10,000   origin ok     corner ok
    #     EvilOrb 2      [-4, 5, -4, 5]               9x9 =     81    origin  81    corner  64
    #     EvilOrb 65/67  [-31.5, 32.5, ...]         64x64 =  4,096    origin ok     corner ok
    #
    # 'corner' misses on three and never wins. (EvilOrb 11/12 match neither -- rectangle
    # 7x7 = 49 against 441 and 324 -- and are an outer multiplier, not evidence either way.)
    #
    # 'pixel' IS REFUSED, not merely unchosen. The walk takes
    # `bool(run(prog, slots, number)[0])` -- ONE verdict per pattern -- so a per-pixel $pos
    # returns N verdicts and the walk silently keeps pixel 0's; that is precisely the
    # corruption the pre-fix `$pos` leak produced. And the reference specimen says so
    # outright: at $pos = (128, 128) Rokviz falls from 70 rendered records to 41 and stops
    # producing `height`.
    #
    # IT IS A PER-NODE CONSTANT, not a per-pattern value. Every per-pattern arm breaks the
    # rectangle count on Rokviz: a $number cell grid gives 416 and 1,792 where the rectangles
    # hold 729 and 10,000, a normalised $number gives 8,415, and ANY per-pattern jitter at
    # all gives 716 for 729.
    #
    # NOTHING IS SINGULAR AT ZERO, so no program argues it must be non-zero: across 26,803
    # $pos-reading fx programs, not one divides by a $pos-derived value. One record
    # (NetSubstance001 rec 50) takes a polar conversion of it, which is defined at the
    # origin.
    #
    # EVERY FIGURE ABOVE IS FROM THE COMPILED CORPUS. An earlier version of this comment
    # argued the same conclusion from named function graphs in the shipped `.sbs` sources.
    # Those sources are `<author v="Allegorithmic"/>` and SPEC 12 excludes them from
    # analysis, so that leg has been removed -- along with the parameter names it supplied.
    # The conclusion did not rest on it: it was corroboration, and the arbitration was
    # always the record's own rectangle. What may be read says nothing either way -- across
    # the 34 third-party sources containing an FX-Map, `$pos` appears inside one exactly
    # once, in `patternrotation`/`frameoffset`/`patternsize`, never in a gate.
    #
    # WHAT WOULD MOVE THIS: a SUBDIVIDED FX-Map -- a node whose children cover different
    # parts of their parent's region and so inherit different positions. `chain` is a FLAT
    # walk, so today there is one node position and it is the root's, and the place to
    # thread a per-node one is `make_runner`'s `run`. Searched for and not found: of 155
    # distinct node headers reached, `0x1db` is the only one whose word 1 equals its number
    # of trailing node pointers, and it is two-way at every instance -- arms that cover the
    # same region and share a `$pos`. Across the 266 FX-Map graphs in third-party sources, no
    # node has more than one child at all. That negative is BOUNDED BY THE CLEAN-ROOM RULE:
    # the sources that do branch are Allegorithmic and may not be read, so the claim is
    # "absent from what may be examined", not "absent from the format".
    'fx.pos':             ('origin', 'corner'),
    'fx.scanner':         ('once', 'loop'),
    'fx.gatescan':        ('once', 'loop', 'filter'),
    'fx.combine':         ('max', 'add', 'over'),
    'fx.negopacity':      ('clip', 'signed', 'abs'),
    # THREE BITS THE BIT CENSUS PLACED AND DID NOT NAME. All three cost zero header words,
    # so nothing is misplaced by leaving them here; what is open is what they MEAN, and each
    # candidate below is a guess that would need something outside the file to settle.
    # See FORMAT-NOTES.md, "Every filter, bit by bit", and `archive/tools/bit_census.py`.
    #
    #   blend.w1bit8          w1 bit 8, set on 232,581 of 310,697 blend records and charged
    #                         nothing. It tracks the BLEND MODE: 98.5-100% set for every mode
    #                         that combines the two images arithmetically, 46.7% for `switch`
    #                         and 50.8% for `copy`, the two that select rather than combine.
    #                         Both edges are present either way, so it is not "a background
    #                         is connected".
    #   transformation.w1low  w1 bits 0-5, six bits charged nothing in any state, two values
    #                         covering 98.2% of the filter (0b111111 on 175,110 records,
    #                         0b011111 on 55,529) and a tail of 47 more. A packed enum whose
    #                         value is its bits; naming it from a frequency is the inference
    #                         `normal`'s field 1 had to retract.
    #   dyngradient.gradpos   class bits 25 (baked, 0.5 on 86 of 95) and 26 (a program), an
    #                         ordinary baked/program pair. The program arm's inputs are named
    #                         `Stone_colour_Gradient_Input_Position`, `Stone_Colour_Grad` and
    #                         `Lichen_Colour_Variation` -- the material author's names for a
    #                         position into a gradient, not the parameter's own.
    'blend.w1bit8':       ('ignore', 'alphablend', 'background_used'),
    'transformation.w1low': ('ignore', 'tiling', 'filtering', 'mipmap'),
    'dyngradient.gradpos': ('ignore', 'position', 'variation'),
    'levels.zerospan':    ('step', 'identity'),
    'levels.inversion':   ('flat', 'complete'),
    'levels.interclamp':  ('clamp', 'noclamp'),
    'nonfinite.fill':     (0.0, 0.5, 1.0),
    'uniform.fill':       (),
    'grayscale.weights':  (),
    'fx.branchoffset':    ('canvas', 'cell'),
    'fx.patternsize':     ('canvas', 'cell'),
    'fx.frameoffset':     ('canvas', 'cell'),
    'fx.markers':         ('draw', 'skip'),
    'fx.typeless_profile': ('rect', 'disc', 'cone', 'paraboloid', 'bell', 'gaussian'),
}

_ACTIVE = {}

# Record indices rendered under an assumption; cleared for each scope.
USED = set()


def assumed(key, default=None):
    """Return the active choice for ``key``, or ``default`` outside a scope."""
    return _ACTIVE.get(key, default)


def note(record_index):
    """Record that a rendered record depended on an assumption."""
    USED.add(record_index)


@contextlib.contextmanager
def scope(**choices):
    """Temporarily apply choices and yield records marked within the scope."""
    for key, value in choices.items():
        allowed = QUESTIONS.get(key)
        if allowed and value not in allowed:
            raise ValueError('assume: %r is not a candidate for %r; try one of %r'
                             % (value, key, allowed))
    saved = dict(_ACTIVE)
    saved_used = set(USED)
    _ACTIVE.update(choices)
    USED.clear()
    try:
        yield USED
    finally:
        _ACTIVE.clear()
        _ACTIVE.update(saved)
        USED.clear()
        USED.update(saved_used)


def active():
    """Return the assumptions currently in force."""
    return dict(_ACTIVE)
