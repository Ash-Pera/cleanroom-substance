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
#
# OWNERSHIP: this file, `derive_costs.py` and the `costs.json` they produce are maintained by
# ONE session at a time. Several Claude sessions share this working tree and one git HEAD, and
# a change here routinely pairs with a change in `decompose.py`; when the two halves landed in
# two sessions' commits, HEAD raised `AttributeError` on every warp and shuffle record while
# each commit was individually fine (5faf524 / 35fe822). Send the change to the owner rather
# than editing alongside them. Verify against a pristine `git show HEAD:` copy, never against
# the working tree, which holds everyone's uncommitted work at once.
#
import functools
import json
import os

_COSTS = None


def costs():
    """The fitted slot costs, loaded once.

    `header_words` is memoised on (filter, word0, w1, version) and is therefore only sound
    while this table is fixed. It is loaded once per process and never reloaded, so that
    holds; a caller that ever swaps the table must call `header_words.cache_clear()`.
    """
    global _COSTS
    if _COSTS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'costs.json')
        try:
            with open(p) as fh:
                _COSTS = json.load(fh)
        except OSError:
            _COSTS = {}
    return _COSTS


W1_REFUSE = object()        # "the shape is undecidable from what you passed"


def two_shape_w1(filter_id, word0, w1, version):
    """The effective w1 for the filters with two record shapes, or `W1_REFUSE`.

    THE ONE PLACE THIS RULE LIVES. `header_words`' own comment says the gate belongs here
    "not in the callers", because a caller that forgets it charges `w1_present` on a record
    that has no w1 word and comes out one word long, silently -- a session probe that missed
    it measured warp's model as wrong in 25,085 of 26,795 records and published that. But
    `decompose._has_w1_word` was a second copy of the same rule, so the gate lived in two
    places and only one of them said so. It now delegates here.

        warp (7)     w1 only from version 0x90000; undecidable without a version, so refuse
        shuffle (3)  TAG BIT 0 selects the shape, and it is not a per-record accident: bit 0
                     is the output colour flag, filter 3's parameter is PER OUTPUT CHANNEL,
                     and the shape follows the channel count -- one channel wants weights
                     over the inputs and carries no selector word, four want a packed
                     per-channel selector and do. Same width legend as SPEC 6.4 everywhere
                     else. 7,682 records, no exceptions; `derive_costs` reaches the same bit
                     from the other side, where it beat an edge-run heuristic on all 51 of
                     their disagreements.
    """
    if filter_id == 7:
        if version is None:
            return W1_REFUSE
        return w1 if version >= 0x90000 else None
    if filter_id == 3:
        return w1 if (word0 & 1) else None
    return w1


@functools.lru_cache(maxsize=1 << 16)
def header_words(filter_id, word0, w1, version=None):
    """Header length in words from the masks alone, or None if not derived.

    None means "this filter's costs were not established", never "zero" -- callers must
    fall back rather than treat a missing rule as an answer.

    `word0` is the record's ENTIRE first word, not the cls field alone. The tag's low
    bits carry layout too -- uniform's colour flag is tag bit 0 and costs +3 words --
    and the first version of this function took cls and silently could not see them.

    `w1` follows the filter's mode, recorded in the spec by derive_costs:

        codes       words[1], a vector of two-bit fields
        arity       words[1]; an integer sub-field adds one slot per unit
        absent      the filter has no w1 word; the argument is ignored
        per_record  the record either has a w1 word or does not, and the TAG says which:
                    `two_shape_w1` gates it on word 0 bit 0. The name predates that and
                    describes a caller contract that no longer exists -- pass words[1]
                    unconditionally and the gate below decides

    The first version of this function silently ignored the arity and presence terms:
    it predicted from const+cls+codes whatever the spec held, so a pixelprocessor
    answer would have been wrong by the input count with no sign anything was missing.
    Terms and spec are now the same shape by construction -- everything the fit can
    emit, this applies.
    """
    spec = costs().get(str(filter_id))
    if spec is None:
        return None
    # THE TWO-SHAPE GATE LIVES HERE, not in the callers. `warp` and `shuffle` each have a
    # record shape that carries a w1 word and one that does not, and `w1_present` is charged
    # whenever the `w1` argument is not None -- so a caller that passes `words[1]`
    # unconditionally gets a header one word too long, silently, for every no-w1 record.
    # Both call sites in sbsasm.py implemented this gate themselves, one of them without a
    # version; a session probe that did not implement it measured warp's model as wrong in
    # 25,085 of 26,795 records and published the conclusion. Gated here, the same comparison
    # is 26,795 of 26,795 exact. A rule the caller can forget is a rule in the wrong place.
    w1 = two_shape_w1(filter_id, word0, w1, version)
    if w1 is W1_REFUSE:
        return None                          # the shape is undecidable: refuse
    # Variant selection before anything else: a split filter stores one spec per
    # sampling class, each behind its own guard. Pick the matching one; a record
    # whose class no variant covers gets None, not a guess.
    for v in spec.get('variants', ()):
        g = v.get('guard')
        if g is None or (word0 >> g['shift']) & g['mask'] == g['value']:
            spec = v
            break
    else:
        if 'variants' in spec:
            return None
    # Guards FIRST, whatever the spec's shape. The interaction dispatch used to sit
    # above the min_version check, so emboss's colour-states spec answered for the
    # v2-v4 records its guard exists to refuse -- and 27 of them surfaced as
    # "observed short of rule", which is what a guess about a population that
    # contradicts its own keys looks like from the outside.
    mv = spec.get('min_version')
    if mv is not None and (version is None or version < mv):
        return None                      # fitted on modern versions only
    g = spec.get('guard')
    if g is not None and (word0 >> g['shift']) & g['mask'] != g['value']:
        return None                      # fitted for a different sampling class
    # The interaction dispatch comes LAST. It sat above the min_version check once and
    # above the guard check twice, and each time the spec answered for a population it
    # was fitted to refuse -- 27 old emboss records the first time, 86 class-0 fxmaps
    # records the second. Every gate runs before any evaluation path forks.
    if spec.get('interaction') in ('colour', 'colour_states'):
        return _interaction(spec, word0, w1)
    if spec.get('mode') == 'absent':
        w1 = None
    total = spec['const']
    for b, c in spec['cls'].items():
        if word0 >> int(b) & 1:
            total += c
    # Conjunctions: word 0's high byte is a small field for some filters, not eight
    # independent flags. bitmap tests bits 24 and 27 TOGETHER -- the pair means the
    # record carries a second offset word, the one that actually locates its pixels --
    # and an additive model can only reach that through two halves and a rounding tie.
    for bx, by, cv in spec.get('conj', ()):
        if (word0 >> bx & 1) and (word0 >> by & 1):
            total += cv
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


def _interaction(spec, word0, w1):
    """Colour-interaction spec: header = base(features) + tagbit0 * cross(features)."""
    if spec.get('mode') == 'absent':
        w1 = None
    v = [1.0] + [float(word0 >> b & 1) for b in spec['clsbits']]
    if spec.get('has_absent'):
        v.append(float(w1 is not None))
    ar = spec.get('arity_sm')
    if ar is not None:
        v.append(float((w1 >> ar[0]) & ar[1]) if w1 is not None else 0.0)
    for j in spec['pairs']:
        st = ((w1 >> (2 * j)) & 3) if w1 is not None else 0
        v += [float(st == 1), float(st == 2), float(st == 3)]
    c0 = float(word0 & 1)
    total = sum(b * x for b, x in zip(spec['base'], v))
    if spec['interaction'] == 'colour_states':
        vs = v[len(v) - len(spec['cross']):]      # the state features alone
        total += c0 * sum(b * x for b, x in zip(spec['cross'], vs))
    else:
        total += c0 * sum(b * x for b, x in zip(spec['cross'], v))
    n = int(round(total))
    return n if n > 0 else None


def covered():
    """The filter ids the rule can decide."""
    return {int(k) for k in costs()}
