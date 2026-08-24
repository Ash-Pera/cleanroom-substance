#!/usr/bin/env python3
"""The record layout rule, as one function.

A record is a struct with two presence masks and no stored offsets:

    word 0   tag   filter id, plus `cls` -- a bitmask over the INHERITED parameters
                   ($outputsize, $randomseed, output format, pixel size, ...)
    word 1   w1    a vector of two-bit codes over the FILTER's OWN parameters
                   00 absent   01 baked   10 a program   11 an image input
                   -- present only for filters that have such parameters
    then     the image inputs, contiguous
    then     one slot per set cls bit, in canonical order
    then     one slot group per nonzero w1 field, in field order
    tail     payload filters end with a pointer to their table

Every position is implied by the bits set before it, so a reader walks the masks and a
writer emits in the same order. Nothing stores a slot number, which is why no bitfield of
the tag was ever found that computed one.

`header_words` is the whole rule in arithmetic form: a header is a constant plus the cost
of each set bit. The costs are in costs.json, fitted from the corpus by derive_costs.py
and kept only where the rounded costs reproduce EVERY observed header exactly -- currently
12 filters and 72.25% of records with an observable boundary.

This does not yet replace layouts.json. It replaces the part of it that can be computed,
and reports the rest honestly rather than memorising it. The filters still missing are
missing for stated reasons:

    pixelprocessor, fxmaps   their w1 carries an ARITY INTEGER, not two-bit codes, so a
                             per-field cost model cannot express it (0.0% and 10.4%)
    warp, shuffle            two record shapes, and w1 exists in only one of them
    uniform                  no w1 word at all; slot 1 is an edge
    levels                   five fields, and its baked widths are not yet separated
"""
import json
import os

_COSTS = None


def costs():
    global _COSTS
    if _COSTS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'costs.json')
        try:
            with open(p) as fh:
                _COSTS = json.load(fh)
        except OSError:
            _COSTS = {}
    return _COSTS


def header_words(filter_id, cls, w1):
    """Header length in words from the masks alone, or None if not derived.

    None means "this filter's costs were not established", never "zero" -- callers must
    fall back rather than treat a missing rule as an answer.

    `w1` follows the filter's mode, recorded in the spec by derive_costs:

        codes       words[1], a vector of two-bit fields
        arity       words[1]; an integer sub-field adds one slot per unit
        absent      the filter has no w1 word; the argument is ignored
        per_record  the record either has a w1 word or does not, and only the CALLER
                    can tell (the edge run starting at slot 1 is the no-w1 shape) --
                    pass words[1], or None for the no-w1 shape

    The first version of this function silently ignored the arity and presence terms:
    it predicted from const+cls+codes whatever the spec held, so a pixelprocessor
    answer would have been wrong by the input count with no sign anything was missing.
    Terms and spec are now the same shape by construction -- everything the fit can
    emit, this applies.
    """
    spec = costs().get(str(filter_id))
    if spec is None:
        return None
    if spec.get('mode') == 'absent':
        w1 = None
    total = spec['const']
    for b, c in spec['cls'].items():
        if cls >> int(b) & 1:
            total += c
    if w1 is not None:
        total += spec.get('w1_present', 0.0)
        ar = spec.get('arity')
        if ar:
            total += ar['cost'] * ((w1 >> ar['shift']) & ar['mask'])
        for j, states in spec['w1'].items():
            st = (w1 >> (2 * int(j))) & 3
            if st:
                total += states.get(str(st), 0.0)
    n = int(round(total))
    return n if n > 0 else None


def covered():
    """The filter ids the rule can decide."""
    return {int(k) for k in costs()}
