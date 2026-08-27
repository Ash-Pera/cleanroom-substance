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
    'normal.inversedy':   ('ignore', 'word1bit2'),
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
    'fx.scanner':         ('once', 'loop'),
    'fx.gatescan':        ('once', 'loop', 'filter'),
    'fx.combine':         ('max', 'add', 'over'),
    'fx.negopacity':      ('clip', 'signed', 'abs'),
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
