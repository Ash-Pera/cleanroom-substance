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
    'distance.param':     ('program', 'block1', 'slot5'),
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
    'uniform.fill':       (),      # a value, not an enumeration
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
