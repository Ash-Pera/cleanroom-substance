#!/usr/bin/env python3
"""Explicit assumptions, for arbitrating a guess against the reference renders.

WHY THIS IS A SEPARATE MODULE. `render()`'s contract is that it never emits an image it
cannot defend -- which is why `blur`'s baked fallback was withdrawn and `distance`'s
parameter slot is deliberately unlocated. That contract is right and nothing here changes
it. But it produced a bind, recorded in FORMAT-NOTES: the reference renders cannot arbitrate
our guesses, because our refusals to guess are what block the reference renders. 96 declared
outputs in the eight reference specimens, 10 produced, 0 spatially varying, and the top
blockers are `blur`'s withdrawn fallback (70 records), `dyngradient` (24), `distance` (11).
Every one is something somebody correctly declined to assume.

The bind dissolves because SCORING DOES NOT NEED A CORRECT RENDER, IT NEEDS A COMPARABLE
ONE. Rendering candidate A and candidate B and asking which matches the engine's own exported
map is how a guess gets arbitrated; refusing to render either is what makes it
unarbitratable.

So: a caller who wants to arbitrate passes an explicit assumption, gets an image, and scores
it. A caller who wants coverage passes nothing and gets today's behaviour exactly.

THE RULES, which are what keep this from becoming a way to make the numbers look better:

  * Assumptions are OPT-IN and empty by default. `assumed(key)` returns None unless a caller
    has opened a scope, so no sweep can pick one up by accident.
  * Every record rendered under one is recorded in `USED`. A coverage count that does not
    subtract `USED` is wrong, the same way one that does not subtract `LOW_CONFIDENCE` is.
  * A key names a QUESTION, not a filter, so an A/B is a one-key change and the thing being
    arbitrated is legible from the call site.

This module deliberately holds no defaults and decides nothing. It is a channel.
"""
import contextlib

# question -> the candidate values it is worth arbitrating. Documentation, not enforcement;
# a caller may pass anything, and an unknown key is that caller's business.
QUESTIONS = {
    'blur.intensity':     ('program', 'slot3'),
    # 'wide' names a reading rather than a location: take component 0 of a 2-COMPONENT
    # program result. The 31 `distance` records that locate nothing have only 2-component
    # programs -- 24 of them a single `exp2(min(swizzle($sizelog2) - $sizelog2, 0))`, an
    # aspect term that is 1.0 on a square image. Whether its first component IS the
    # distance is a guess with an arbiter available, which is what this channel is for.
    'distance.param':     ('program', 'block1', 'slot5', 'wide'),
    'distance.invert':    (False, True),
    'distance.mask_edge': (0, 1),
    # The footprint is no longer a four-way guess: `patterntype` is declared in the entry
    # tag and the manifest NAMES its values, so `fxrender.PATTERN_SHAPES` selects the shape
    # from shipped data and this question only exists to FORCE one for an experiment.
    # Every honourable name must be listed -- an omitted one is rejected here, which is the
    # same failure as accepting a value that cannot be delivered, in the other direction.
    'fx.profile':         ('rect', 'square', 'disc', 'paraboloid', 'bell', 'gaussian',
                           'thorn', 'pyramid', 'brick', 'gradation', 'waves', 'halfbell',
                           'ridgedbell', 'crescent', 'capsule', 'cone'),
    # What a record whose arithmetic went non-finite should emit. The recurring case is
    # an AUTO-LEVELS remap, (L - min) / (max - min), over a source that is constant: max
    # equals min, the range is zero-wide, and 0/0 is degenerate for any renderer including
    # the engine. There is no arithmetic to fix, only a decision about what to write, and
    # three specimens now block on it -- Chesterfield rec330, WoodSubstance005 rec139/245,
    # Bricks_and_tiles rec10330, the last of which gates four channels of the only
    # reference-scored package that has them.
    # What an entry that states NEITHER a patterntype NOR a patternsize should draw.
    # Today it is a full-cell rect, which paints the whole canvas white, and three
    # specimens turn white for exactly that reason -- Chesterfield rec43, WoodSubstance005
    # rec85, Bricks rec5228. The entry is read correctly; what is unknown is what the
    # engine draws when the file states no extent.
    'fx.sizeless':        ('fill', 'skip', 'half', 'quarter'),
    'nonfinite.fill':     (0.0, 0.5, 1.0),
    'uniform.fill':       (),      # a value, not an enumeration
    # The channel weights a single-input `shuffle` record applies. TWO SOURCE NODE TYPES
    # COMPILE TO THE SAME FILTER ID -- the paired sources declare `grayscaleconversion`
    # (100 nodes, parameter `channelsweights`, a float4) and `shuffle` (43 nodes,
    # parameters `channelalpha`/`channelgreen`/`channelblue`, integer selectors) -- which
    # is why one filter has two layouts, a weight vector and a selector word. Class-word
    # bit 8 says whether the weights are stored at all; where it is clear the compiler
    # emitted nothing and the engine uses the node's own default, which is not in the
    # file. A 4-tuple, so continuous rather than enumerated.
    'grayscale.weights':  (),
    # WHAT UNIT A branchoffset IS IN. splat adds branchoffset to frameoffset and treats the
    # sum as canvas coordinates, but the two are not in the same unit: over 966 square-grid
    # fxmaps records the median of branchoffset's span / (G - 1) is exactly 1.0000, i.e. it
    # spans G-1 CELLS, while frameoffset points at canvas in both records that can answer.
    # Rendering agrees independently -- Chainmail record 0 puts one cell on screen read as
    # canvas, and a full 257 x 257 lattice read as cells.
    #
    # It is a QUESTION rather than a fix because the tail is uncharacterised: G is only
    # defined for a square emission count, and 30% of those 966 fall outside 10% of the
    # cell ratio. A reference render can settle what a span statistic cannot, which is
    # exactly what this channel is for.
    'fx.branchoffset':    ('canvas', 'cell'),
    # WHAT UNIT A patternsize IS IN, the other half of the same question. Canvas is refused
    # two independent ways: the 83 distinct baked values all sit in roughly [0.67, 8] --
    # 5.0, 1.5, 3.0, 1.0, 8.0, 2.0 -- which as canvas fractions are patterns from
    # two-thirds of the image to eight times it; and over 299 baked square-grid records
    # with G from 2 to 128 the correlation of size with 1/G is -0.074, where a canvas
    # fraction tiling a G-grid would have to correlate near 1.
    #
    # It is a separate key from fx.branchoffset because the two are COUPLED and scoring
    # them apart is what shows it. Correcting offsets alone puts the lattice in the right
    # place while each cell is still painted G times too large, so a half correction can
    # score worse than none -- which is what cleanroom-substance-0b measured on
    # Chesterfield (normal 0.0854 -> 0.0869) for two records whose span/(G-1) is exactly
    # 1.0000 on both axes, i.e. squarely on the law rather than in its tail.
    'fx.patternsize':     ('canvas', 'cell'),
    # WHAT AN ENTRY WITH NO patterntype DRAWS. `profile_for` falls back to 'rect', a hard
    # fill of the whole cell, and its own docstring says that is "what the code has always
    # done, not because it is established". It is a DIFFERENT knob from 'fx.profile', which
    # overrides every entry including the ones that state a type; this one moves only the
    # entries that state none.
    #
    # It matters more than a catch-all usually would. Over 45 fxmaps-bearing files, giving
    # typeless entries a falloff instead of a hard fill adds spatial structure to 300
    # record outputs across 20 files and removes it from 13 across 3 -- because abutting
    # cells filled solid are flat, and the same cells with a falloff are a pattern.
    #
    # Scored against the one ground truth in the corpus, Chesterfield, no member wins
    # outright:
    #
    #     typeless     basecolor      normal   roughness(std)  metallic  height     AO
    #     rect         not rendered   0.1056   0.0718 (0.0036)   0.0454  0.2480  0.6832
    #     disc         0.1259         0.1045   0.0719 (0.0265)   0.0481  0.2478  0.6888
    #     cone         0.1334         0.0953   0.0719 (0.0000)   0.0481  0.2490  0.6937
    #     paraboloid   0.1320         0.0986   0.0719 (0.0000)   0.0481  0.2472  0.7003
    #     bell         0.1341         0.0940   0.0719 (0.0000)   0.0481  0.2498  0.7075
    #     gaussian     0.1357         0.0905   0.0719 (0.0000)   0.0481  0.2530  0.7070
    #
    # Every falloff RENDERS basecolor, which 'rect' does not produce at all. gaussian takes
    # normal from 0.1056 to 0.0905. But 'rect' keeps metallic and AO, and only 'disc' holds
    # roughness's spatial variation -- std 0.0265 against the reference's 0.0262, where
    # every other falloff collapses it to 0.0000 and 'rect' undershoots at 0.0036.
    #
    # So the default does not move. A choice that improves two maps and flattens two others
    # is the half-correction this file already records being caught by twice.
    'fx.typeless_profile': ('rect', 'disc', 'cone', 'paraboloid', 'bell', 'gaussian'),
}

_ACTIVE = {}

#: record indices rendered under an assumption, cleared per `scope()`. Mirrors
#: render.LOW_CONFIDENCE: an image that depends on a guess must be countable separately.
USED = set()


def assumed(key, default=None):
    """The value a caller chose for `key`, or `default` when nobody opened a scope."""
    return _ACTIVE.get(key, default)


def note(record_index):
    """Record that this record's output depends on an assumption."""
    USED.add(record_index)


@contextlib.contextmanager
def scope(**choices):
    """Render under explicit assumptions. Nested scopes override outer ones.

        with assume.scope(**{'fx.profile': 'bell'}):
            img, _f, _s = render(asm, max_dim=None)
        # assume.USED names every record that depended on it
    """
    for k, v in choices.items():
        allowed = QUESTIONS.get(k)
        # An unhonourable value must fail HERE, loudly, rather than being silently aliased
        # by a consumer -- a channel that accepts what it cannot deliver produces a score
        # for a candidate that was never rendered. Only enumerated questions are checked;
        # `()` marks one whose values are continuous.
        if allowed and v not in allowed:
            raise ValueError('assume: %r is not a candidate for %r; try one of %r'
                             % (v, k, allowed))
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
    """The assumptions currently in force, for reporting alongside a score."""
    return dict(_ACTIVE)
