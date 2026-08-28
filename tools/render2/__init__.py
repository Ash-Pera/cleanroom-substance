#!/usr/bin/env python3
"""A renderer whose every structural read comes from the walk.

    python3 tools/render2 <file.sbsasm> [--dim 256] [--out DIR]

`render.py` is the renderer this replaces. The difference is not a rewrite for tidiness:
that one asks a different question in every filter branch -- a fitted `LAYOUTS` memo here,
a value probe over `Record.programs` there, a hand-stated slot offset in a third -- and
this one asks `decompose` once, per record, and reads the answer by NAME.

    model.py     the record as the walk states it: edges, parameters, header extent
    ops.py       image primitives and the bytecode runner
    filters.py   one function per filter, reading parameters by name
    fx.py        FX-Map emission and drawing
    engine.py    the forward pass

See `model.View` and `fx.number_grid` for the two readings this changes, and
`tools/render2/__main__.py` for the scorer it was verified with.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
# `tools` FIRST, this package LAST. The modules here have short names -- `model`, `ops`,
# `fx`, `filters`, `engine` -- and putting them at the front of `sys.path` would shadow a
# same-named module anywhere else in a process that imports this one. Appending means a
# collision breaks THIS package loudly (the check below) instead of breaking someone else
# quietly.
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
if _HERE not in sys.path:
    sys.path.append(_HERE)

from engine import render, Context          # noqa: E402,F401
from ops import Unsupported                 # noqa: E402,F401
from model import View, views               # noqa: E402,F401

for _m in (render, Context, Unsupported, View):
    if os.path.dirname(os.path.abspath(sys.modules[_m.__module__].__file__)) != _HERE:
        raise ImportError('render2: %r resolved outside the package -- a module of the '
                          'same name shadows it on sys.path' % _m.__module__)

__all__ = ['render', 'Context', 'Unsupported', 'View', 'views']
