#!/usr/bin/env python3
"""The width legend, derived from the corpus: one KIND per header cell, no fitted floats.

    python3 archive/tools/derive_legend.py            # derive, report, write tools/legend.json
    python3 archive/tools/derive_legend.py --dry-run  # derive and report, write nothing

WHAT THIS REPLACES. `derive_costs.py` fits `header = const + sum of per-bit costs` with a
FREE intercept and a real-valued coefficient per (bit) and per (field, state) -- 688 numeric
cells across five spec shapes (`plain`, `colour`, `colour_states`, `arity`, `variants`) plus
`pairs`, `flags`, `constant_bits`, `has_absent`, `arity_sm`, `nullity`, `unident`, a
`w1_shift`, a `conj` list and a `STRADDLED` relabelling table in `decompose`. Read as
EFFECTIVE costs rather than as stored cells, the whole of that collapses onto SPEC 7.2/7.3's
width legend:

    header = n_hdr + n_base + n_fixed
           + SUM over set class bits of        width(kind)
           + SUM over w1 FIELDS -- a two-bit code AT ITS OWN BIT OFFSET -- of
                 00 absent  -> 0        01 baked   -> width(kind)
                 10 program -> 1        11 edge    -> 1
           + arity                (the two filters whose w1 holds an input count)
           + one conjunction      (bitmap 24+27)

    width:  0 -> 0   1 -> 1   2 -> 2   4 -> 4   C -> 1 grey / 4 colour
    n_hdr = 1 + (this record carries a w1 word)

There is no intercept, no float, no negative coefficient, no per-state cell, no base/cross
vector, no interaction mode, no grid shift, no straddle table and no fitted variant.

WHAT IS STATED HERE AND WHAT IS DERIVED, because the difference is the whole claim.

  STATED -- structural facts, each with an arbiter that is not this solve:
    `HAS_W1`        which record shapes carry a w1 word (`record_layout.two_shape_w1`)
    `BASE_INPUTS`   the filter's fixed image-input arity (`decompose.BASE_INPUTS`)
    `FIXED`         the filter's fixed prefix -- gradient/curve's ramp pair, fxmaps' tree
                    root, bitmap's pixel word, text's zero+string+font, pixelprocessor's
                    own program. Every one of them is a slot some reader resolves.
    `W1_OFFSETS`    which BITS of w1 begin a two-bit field. 32 numbers, and the one part of
                    the legend this script takes rather than finds; see the note on the
                    table for what pins each one.
    `EDGE_BITS`     the w1 bits that declare an image INPUT from their low bit alone
                    (SPEC 6.3: `distance`'s field 0)
    `ARITY`         the two filters whose w1 holds an input COUNT, with its (shift, mask)
    `CONJ`          the one paired conjunction (SPEC 6.4: bitmap 24+27)
    `MIN_VERSION`   the version gate `emboss`'s modern layout is behind
    `W1_ORDER`      the one filter whose parameter block is not in ascending bit order
                    (SPEC 6.1: `text`)

  DERIVED -- solved here against the OBSERVED header boundaries, never against
  `costs.json` or `record_layout.header_words`:
    every cell's KIND -- 106 of them, one symbol each from a five-symbol alphabet
    which cells the corpus exercises, per colour, and in which colour each was measured
    the residual that identifies the cost of a class bit set on EVERY record of a filter

THE OBSERVATION TABLE IS `derive_costs.observed()`, unchanged -- the earliest in-record
target of any payload pointer or inline program, or the record's own end where it is nothing
but header. That is the same evidence the fit used, so the two are comparable, and it is
independent of both models.

WHAT THE SOLVE IS. Per filter, ONE COLUMN PER (cell, colour) rather than one column per cell
with a colour interaction, the intercept PINNED to `n_hdr + n_base + n_fixed`, and states 10
and 11 FORCED to one word rather than fitted -- a pointer is a pointer and an edge slot is a
slot, in every filter, and letting a fit discover that is what produced the per-state cells
the legend does not need. What is solved for is therefore exactly one number per (cell,
colour): the width of the BAKED value.

WHY PER-COLOUR COLUMNS AND NOT AN INTERACTION. The obvious parameterisation is
`width = a + 3*b*c0` with `(a, b)` constrained to the alphabet, which is what a first
attempt used. It fails on the filters whose records are all one colour -- `hsl`, `normal`
and `text` -- because there `a` and `b` are perfectly collinear, least squares returns the
minimum-norm split, and rounding each half sends both to zero: `hsl` came back with every
cell at 0 and 0.268% exact. Solving per colour makes each column exercised exactly where it
is exercised, and the merge into a kind then happens on two MEASURED numbers or is declared
absent.

THE MERGE, AND THE THING THAT MUST NOT BE HIDDEN. Of the 112 (cell, colour) pairs the legend
needs, 36 are exercised in ONE COLOUR ONLY. A table that stores those as 0 cannot be told
from one that measured 0, so this writes them as a kind PLUS a mark: `cls_predicted` /
`w1_predicted` name the colour whose width is a prediction of the legend rather than a
reading of the corpus. Where only grey is exercised at width 1, `Float1` and `per-channel`
predict the same word and this corpus cannot separate them; where only colour is exercised
at width 4 the same ambiguity runs the other way. The mark is what says so.

CONSTANT-SET CLASS BITS. A bit set on every key of a filter has an all-ones column, and with
a FREE intercept it is the intercept -- which is what `derive_costs.constant_bits` records.
With the intercept pinned it is determined, but several such bits are determined only as a
SUM. `emboss` is the case: bits 16, 19 and 27 are set on all 375 records the version gate
admits, so the solve sees one number, 2. It is attributed the way `derive_costs.
_format_wide_cost` attributes it -- to the cost every OTHER filter that can see the bit
agrees on, and only when they agree: bit 16 is charged 1 word by all 20 filters whose
population can see it, bit 27 by the eight that can, and bit 19 is set on 903,608 of 903,616
corpus records and varies in no filter's population at all, so nothing anywhere measures it.
1 + 1 + 0 = 2 closes the residual exactly, and the closure is the check.
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _repo_root                                            # noqa: F401  (puts tools/ on the path)
import derive_costs

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'tools', 'legend.json')

NAMES = {0: 'gradient', 1: 'blend', 2: 'transformation', 3: 'shuffle', 4: 'fxmaps',
         6: 'uniform', 7: 'warp', 8: 'emboss', 10: 'blur', 11: 'dirmotionblur',
         12: 'directionalwarp', 13: 'sharpen', 14: 'hsl', 15: 'levels', 16: 'bitmap',
         17: 'text', 18: 'normal', 19: 'dyngradient', 20: 'pixelprocessor',
         21: 'distance', 22: 'curve'}

#: How the record's shape decides whether it carries a w1 word. `tagbit0` and `v9` are
#: `record_layout.two_shape_w1`'s two rules, restated as data rather than as a branch.
HAS_W1 = {0: 'never', 1: 'always', 2: 'always', 3: 'tagbit0', 4: 'always', 6: 'never',
          7: 'v9', 8: 'always', 10: 'never', 11: 'always', 12: 'always', 13: 'never',
          14: 'never', 15: 'always', 16: 'never', 17: 'always', 18: 'always',
          19: 'never', 20: 'always', 21: 'always', 22: 'never'}

#: The filter's fixed image-input arity -- `decompose.BASE_INPUTS`, a format fact and not a
#: fitted memo entry. `shuffle` is `n_hdr`: its no-w1 shape takes one image at slot 1 and
#: its w1 shape two at slots 2-3, so its base arity IS the number of mask words.
BASE = {0: 1, 1: 2, 2: 1, 3: None, 4: 0, 6: 0, 7: 2, 8: 2, 10: 1, 11: 1, 12: 2, 13: 1,
        14: 1, 15: 1, 16: 0, 17: 0, 18: 1, 19: 2, 20: 0, 21: 1, 22: 1}

#: The filter's FIXED PREFIX: slots every record of the filter carries whatever its masks
#: say. Each is a slot some reader already resolves, which is what makes it structural
#: rather than an intercept by another name --
#:     0, 22  the ramp / control-point pair          (`Record.ramp`, `Record.curve_table`)
#:     4      the FX tree root pointer               (`Record.fx_root`, `decompose.FX_ROOT_SLOT`)
#:     16     the pixel/offset word                  (`extract_bitmaps`)
#:     17     the zero word, the string and the font (SPEC 9.1)
#:     20     the filter's own pixel program         (`decompose`'s arity arm)
FIXED = {0: 2, 4: 1, 16: 1, 17: 3, 20: 1, 22: 2}

#: Where the fixed prefix sits relative to the image inputs. Three positions, one filter
#: each away from the default: fxmaps' root pointer comes BEFORE its inputs (slot 2, with
#: the arity run contiguous from slot 3), and pixelprocessor's own program comes after the
#: CLASS BLOCK rather than before it (SPEC 6.1).
FIXED_AT = {4: 'before_inputs', 20: 'after_class'}

#: WHICH BITS OF `w1` BEGIN A TWO-BIT FIELD. 32 numbers, and the part of the legend this
#: script states rather than finds -- the search that produced them is in FORMAT-NOTES.md.
#: What pins them, per filter, is not one argument:
#:
#:   blend 4, 6, 9      bit 9 is the relocated `opacitymult`: over the whole corpus every
#:                      blend record whose code at bit 9 is nonzero reads 01 -> a plain
#:                      float in [0, 1] on 963 records and none resolving a program, 10 ->
#:                      not one a plain float and every one resolving a program, 0
#:                      exceptions. Read on the even grid the two halves are a pointer
#:                      seen as the denormal 1.9e-39.
#:   transformation 25  the offset's code. Read at bits (25, 26) it is the ordinary
#:                      alphabet -- absent 144,245, baked 29,404, program 69,282, and 11
#:                      NEVER -- while bits 24 and 27 are set in no record at all.
#:   directionalwarp 1, 3, 7 and emboss 1, 3, 5, 7
#:                      `PARAM_SPEC` puts dirwarp's `intensity` at bits (1,2) and
#:                      `warpangle` at (3,4); w1 bit 0 is set in 0 of 62,898 dirwarp records
#:                      against a control of 247,561 of 431,890 elsewhere. Read at bit 0
#:                      `emboss` is the only filter in the corpus that fails SPEC 6.3's
#:                      program check, and it fails it completely: 450 slots whose state
#:                      says `program` and not one of which decodes.
#:   everything else    the even grid, which is the same statement with an offset of 0.
#:
#: There is no `w1_shift` and no straddle table here because there is no grid to shift and
#: no field to un-straddle: a field begins at its own bit.
W1_OFFSETS = {
    0: [], 1: [4, 6, 9], 2: [6, 25, 28], 3: [], 4: [0, 2, 4, 6, 8], 6: [], 7: [],
    8: [1, 3, 5, 7], 10: [], 11: [0, 2], 12: [1, 3, 7], 13: [], 14: [],
    15: [0, 2, 4, 6, 8], 16: [], 17: [6, 8, 10], 18: [0, 2, 4], 19: [], 20: [],
    21: [2], 22: [],
}

#: The one filter whose parameter block is not emitted in ascending bit order (SPEC 6.1):
#: `text` lays `matrix22`, `position`, `fontsize` -- bits 10, 6, 8. Over the 14 records that
#: bake all three, the FIRST four words are a 2x2 matrix on 13 of 14 and the last four on 0
#: of 14. It is not a rule any other filter obeys and it is not derived here.
W1_ORDER = {17: [10, 6, 8]}

#: w1 bits that declare an image INPUT from their LOW BIT alone rather than from a two-bit
#: code (SPEC 6.3). One field in one filter: `distance`'s mask input, whose cost tracks bit
#: 0 and not baked-versus-program -- bit 0 set gives two edges and clear one, 2,277 of 2,277.
EDGE_BITS = {21: [0]}

#: The filters whose w1 holds an input COUNT rather than a code grid, with its (shift, mask).
#: `pixelprocessor` reads (0, 31) -- five bits, not four: a nibble reads arity 16 as 0, and
#: the fifth bit read through a two-bit frame is what the fit called "w1 field 2 bakes 16
#: words". `fxmaps` reads (10, 63); a nibble truncates `ie_curve` record 35's 34 inputs to 2.
ARITY = {4: (10, 63), 20: (0, 31)}

#: SPEC 6.4's paired conjunction: two class bits that, set together, name one field.
CONJ = {16: [(24, 27)]}

MIN_VERSION = {8: 0x50000}

#: `shuffle`'s class bit 24 is the one cell in the legend that is not a width: the weights
#: are baked at bit 24 in the shape with NO w1 word and the selector lives in w1 in the shape
#: that has one. Both arms are measured -- bit 24 is set on 3,332 grey records and on all
#: 3,748 colour ones -- and SPEC 6.4 already states the two shapes.
SHAPE4 = {3: 24}

WIDTHS = (0, 1, 2, 4)
GREY, COLOUR = 0, 1
_CNAME = {GREY: 'grey', COLOUR: 'colour'}


def has_w1(f, w0, ver):
    """Does a record of this filter, tag `w0`, version `ver` carry a w1 word?"""
    rule = HAS_W1.get(f)
    if rule == 'always':
        return True
    if rule == 'never':
        return False
    if rule == 'tagbit0':
        return bool(w0 & 1)
    if rule == 'v9':
        return None if ver is None else ver >= 0x90000
    return None




def _keys(table, f):
    """[(word0, w1, header words, record count)] for one filter, modal header per key."""
    out = []
    for (w0, w1), c in table.get(f, {}).items():
        h = max(c.items(), key=lambda t: (t[1], -t[0]))[0]
        out.append((w0, w1, h, sum(c.values())))
    return out


def _row(f, w0, w1, clsbits):
    """(class cells on, baked cells on, conjunctions on, forced words) for one key.

    The forced remainder is everything the legend does NOT solve for: the pinned base, the
    one word a program or an edge state costs, the arity run, and the low-bit edge
    declarations. Subtracting it is what leaves one unknown per baked cell.
    """
    has = w1 is not None
    n_hdr = 1 + (1 if has else 0)
    n_base = n_hdr if f == 3 else BASE[f]
    forced = n_hdr + n_base + FIXED.get(f, 0)
    cls_on, w1_on = [], []
    shape4 = SHAPE4.get(f)
    for b in clsbits:
        if (w0 >> b) & 1:
            if b == shape4:
                if not has:
                    w1_on.append(('shape4', b))    # the no-w1 shape bakes the weights
            else:
                cls_on.append(b)
    conj_on = 0
    for bx, by in CONJ.get(f, ()):
        if (w0 >> bx & 1) and (w0 >> by & 1):
            conj_on += 1
    if has:
        ar = ARITY.get(f)
        if ar:
            forced += (w1 >> ar[0]) & ar[1]
        for b in EDGE_BITS.get(f, ()):
            forced += (w1 >> b) & 1
        for sh in W1_OFFSETS.get(f, ()):
            st = (w1 >> sh) & 3
            if st == 1:
                w1_on.append(('w1', sh))
            elif st in (2, 3):
                forced += 1                        # a pointer, or an edge slot
    return cls_on, w1_on, conj_on, forced


def _system(f, keys, clsbits, c0):
    """`(cols, X, y, wt)` for one colour of one filter, or None if it has no records.

    One column per CELL -- not one per (cell, state) and not one per (cell, colour). What
    a column carries is the width of the cell's BAKED value, which is the only thing the
    legend does not already know.
    """
    rows = [k for k in keys if (k[0] & 1) == c0]
    if not rows:
        return None
    cols, idx = [], {}

    def col(c):
        if c not in idx:
            idx[c] = len(cols)
            cols.append(c)
        return idx[c]

    triples, y, wt = [], [], []
    for w0, w1, h, n in rows:
        cls_on, w1_on, conj_on, forced = _row(f, w0, w1, clsbits)
        v = collections.Counter()
        for b in cls_on:
            v[col(('cls', b))] += 1
        for c in w1_on:
            v[col(c)] += 1
        if conj_on:
            for bx, by in CONJ.get(f, ()):
                v[col(('conj', bx, by))] += 1
        triples.append(v)
        y.append(h - forced)
        wt.append(n)
    # Every declared w1 offset gets a column even where no key of this colour bakes it, so
    # the report can say "unexercised" rather than leaving the cell out and letting a
    # reader assume it was measured at zero.
    for sh in W1_OFFSETS.get(f, ()):
        col(('w1', sh))
    X = np.zeros((len(triples), len(cols)))
    for i, v in enumerate(triples):
        for j, m in v.items():
            X[i, j] = m
    return cols, X, np.array(y, float), np.array(wt, float)


def _identified(X, free):
    """Which of the columns in `free` every exact solution gives the SAME value.

    A column lying on a direction the design matrix cannot see is not a measurement,
    whatever least squares returns for it. Two things make columns blind here and both are
    real. A class bit set on EVERY key of a filter shares an all-ones column with every
    other such bit -- `emboss`'s 16, 19 and 27 hold two words between them and the data
    says only that. And a bit can be CONFOUNDED with a field: over the 15 grey `emboss`
    keys, class bit 20 is set exactly when the w1 field at bit 7 is absent, so their costs
    trade one for one and both a `(c20 1, w7 2)` and a `(c20 0, w7 1)` solution reproduce
    all 246 records. Only the second is the width legend, and the corpus that settles it is
    the COLOUR one, where the confound does not hold.

    Taken over the FREE columns alone, because a column pinned to a known value is a known
    constant on the right-hand side and cannot blind anything.
    """
    out = np.zeros(len(free), dtype=bool)
    if not len(free):
        return out
    L = X[:, free]
    live = np.any(L != 0, axis=0)
    if not live.any():
        return out
    M = L[:, live]
    _u, sv, vt = np.linalg.svd(M)
    tol = max(M.shape) * (sv[0] if len(sv) else 0.0) * np.finfo(float).eps
    padded = np.concatenate([sv, np.zeros(vt.shape[0] - len(sv))])
    nb = vt[padded <= tol]
    blind = (np.linalg.norm(nb, axis=0) > 1e-9) if nb.size \
        else np.zeros(int(live.sum()), dtype=bool)
    out[np.flatnonzero(live)] = ~blind
    return out


def _solve(cols, X, y, wt, pinned):
    """Solve the free columns with `pinned` subtracted out. `(widths, exact, ok mask)`."""
    free = [j for j, c in enumerate(cols) if c not in pinned]
    rhs = y.copy()
    for j, c in enumerate(cols):
        if c in pinned:
            rhs = rhs - X[:, j] * pinned[c]
    widths = dict(pinned)
    if free:
        F = X[:, free]
        sw = np.sqrt(wt)
        sol = np.rint(np.linalg.lstsq(F * sw[:, None], rhs * sw, rcond=None)[0])
        for k, j in enumerate(free):
            widths[cols[j]] = int(sol[k])
    pred = (sum(X[:, j] * widths[cols[j]] for j in range(len(cols)))
            if len(cols) else np.zeros(len(y)))
    ok = np.abs(pred - y) < 1e-9
    return widths, (float(wt[ok].sum() / wt.sum()) if wt.sum() else 0.0), ok


def _borrowable(c0, other_width):
    """The other colour's width, when reading it as THIS colour's is not a guess.

    A kind is a pair of widths, `(grey, colour)`, and only two of the five kinds share a
    width: `Float1` is `(1, 1)` and per-channel is `(1, 4)`. So a width of 4 measured in
    COLOUR is either `Float4` or per-channel and says nothing about grey, and a width of 1
    measured in GREY is either `Float1` or per-channel and says nothing about colour. Every
    other reading is the same in both colours and carries across exactly.
    """
    if other_width is None:
        return None
    if c0 == GREY and other_width == 4:
        return None
    if c0 == COLOUR and other_width == 1:
        return None
    return other_width


def _format_wide(measured, cell, minimum=5):
    """The width every population that MEASURES `cell` agrees on, or None.

    A cell this population cannot see may be borrowed only when it is a property of the
    FORMAT rather than of one filter. Class bit 16 is charged one word by all 35
    populations whose records vary in it; bit 26 is charged 2 by ten and 1 by four, and bit
    27 is charged 1 by fourteen and 0 by three, so both are per-filter facts and neither is
    borrowed. What is left after this declines is either determined by the residual or
    reported as unmeasured.
    """
    vals = collections.Counter()
    for wd in measured.values():
        if cell in wd:
            vals[wd[cell]] += 1
    if len(vals) != 1:
        return None
    (v, n), = vals.items()
    return v if n >= minimum else None


def derive(obs=None):
    """`{filter: {...}}` -- the legend, with every cell's provenance per colour."""
    if obs is None:
        obs, _below = derive_costs.observed()
    sysd, measured = {}, {}
    for f in sorted(HAS_W1):
        keys = _keys(obs, f)
        if not keys:
            continue
        clsbits = sorted({b for b in range(16, 32) if any((k[0] >> b) & 1 for k in keys)})
        for c0 in (GREY, COLOUR):
            r = _system(f, keys, clsbits, c0)
            if r is None:
                continue
            cols, X, y, wt = r
            ident = _identified(X, list(range(len(cols))))
            w, _e, _ok = _solve(cols, X, y, wt, {})
            sysd[(f, c0)] = dict(cols=cols, X=X, y=y, wt=wt, ident=ident, clsbits=clsbits)
            measured[(f, c0)] = {c: w[c] for j, c in enumerate(cols) if ident[j]}

    result = {}
    for (f, c0), d in sorted(sysd.items()):
        cols, X, y, wt = d['cols'], d['X'], d['y'], d['wt']
        why = {c: 'measured' for j, c in enumerate(cols) if d['ident'][j]}
        pinned = {}
        # RESOLVE ONE BLIND COLUMN AT A TIME, BEST SOURCE FIRST, and re-test identifiability
        # after each: pinning one column of a blind direction can make the rest of that
        # direction measurable, and the residual is then a reading rather than a borrow.
        # `emboss` is the whole argument for the loop. Its bits 16, 19 and 27 are set on all
        # 375 records the version gate admits, so the data states only their SUM, 2; bit 16
        # is 1 by the format-wide rule and bit 19 is charged by nobody anywhere, and with
        # those two pinned the residual DETERMINES bit 27 at 1. Pinning all three from the
        # outside instead -- which is what the first version of this script did -- gives
        # 1 + 0 + 0 and leaves a word for the free columns to absorb, and emboss came out at
        # 0.008 exact with `cls 23` charged 2 words.
        while True:
            free = [j for j, c in enumerate(cols) if c not in pinned]
            idf = _identified(X, free)
            blind = [free[i] for i in range(len(free))
                     if not idf[i] and X[:, free[i]].any()]
            if not blind:
                break
            pick = None
            for j in blind:
                v = _borrowable(c0, measured.get((f, 1 - c0), {}).get(cols[j]))
                if v is not None:
                    pick = (j, v, 'other-colour')
                    break
            if pick is None:
                for j in blind:
                    v = _format_wide(measured, cols[j])
                    if v is not None:
                        pick = (j, v, 'format-wide')
                        break
            if pick is None:
                pick = (blind[0], 0, 'unmeasured')
            j, v, src = pick
            pinned[cols[j]] = v
            why[cols[j]] = src
        widths, exact, ok = _solve(cols, X, y, wt, pinned)
        for c in cols:
            why.setdefault(c, 'residual')
        exercise = {c: float(wt[X[:, j] > 0].sum()) for j, c in enumerate(cols)}
        for c, n in exercise.items():
            if not n:
                why[c] = 'unexercised'
        result.setdefault(f, {})[c0] = dict(
            widths=widths, exact=exact, why=why, exercise=exercise, cols=cols,
            records=float(wt.sum()), keys=len(y), missed=float(wt[~ok].sum()))
    return result


def _kind(f, cell, colours):
    """One cell's KIND from its two colours' widths, plus the evidence for each.

    `(kind, {colour name: source})`. A kind is a pair of widths and only per-channel has
    two different ones, so a cell measured in both colours is decided outright; a cell
    exercised in one colour only is written as that colour's own reading and the OTHER
    colour is marked `unexercised`, which is what stops a prediction being stored as a
    measurement. Where only grey is exercised at width 1 the corpus cannot separate
    `Float1` from per-channel, and where only colour is exercised at width 4 it cannot
    separate `Float4` from per-channel; the mark is what says so.
    """
    ev, seen = {}, {}
    for c0 in (GREY, COLOUR):
        d = colours.get(c0)
        if d is None:
            # The filter has no record of this colour AT ALL -- `text` is grey on all 59,
            # `normal` and `hsl` colour on every one. Distinct from a cell this colour's
            # records simply never set, and the two are marked differently.
            ev[_CNAME[c0]] = 'no-records'
            continue
        src = d['why'].get(cell, 'unexercised')
        ev[_CNAME[c0]] = src
        if src not in ('unexercised', 'unmeasured'):
            seen[c0] = d['widths'][cell]
    if not seen:
        return None, ev
    if len(seen) == 2:
        g, k = seen[GREY], seen[COLOUR]
        if g == k:
            return (g if g in WIDTHS else [g, k]), ev
        if (g, k) == (1, 4):
            return 'C', ev
        return [g, k], ev
    (_c0, w), = seen.items()
    return (w if w in WIDTHS else [w]), ev


def _spec(f, colours):
    """One filter's entry in `legend.json`."""
    cells = sorted({c for d in colours.values() for c in d['cols']},
                   key=lambda c: (c[0], c[1]))
    cls, w1, conj, shape4, free = {}, {}, [], None, []
    evidence = {}
    for c in cells:
        kind, ev = _kind(f, c, colours)
        if c[0] == 'cls':
            evidence['cls.%d' % c[1]] = ev
            if kind:
                cls[str(c[1])] = kind
            else:
                free.append(c[1])
        elif c[0] == 'w1':
            evidence['w1.%d' % c[1]] = ev
            w1[str(c[1])] = kind          # None = declared, never baked here: kind unknown
        elif c[0] == 'shape4':
            evidence['shape4.%d' % c[1]] = ev
            shape4 = [c[1], kind]
        elif c[0] == 'conj':
            evidence['conj.%d.%d' % (c[1], c[2])] = ev
            conj.append([c[1], c[2], kind])
    spec = {'name': NAMES.get(f, str(f)), 'has_w1': HAS_W1[f],
            'base': BASE[f], 'fixed': FIXED.get(f, 0),
            'cls': cls, 'w1': w1}
    if free:
        # A class bit the population SAW and measured at zero. It gates no stored value, so
        # the walk allocates nothing for it -- but "measured at zero" and "this legend has
        # never heard of the bit" are different findings, and `bit_census` reports them in
        # different columns.
        spec['cls_free'] = sorted(free)
    if f in FIXED_AT:
        spec['fixed_at'] = FIXED_AT[f]
    if f in W1_ORDER:
        spec['w1_order'] = W1_ORDER[f]
    if f in EDGE_BITS:
        spec['edge_bits'] = EDGE_BITS[f]
    if f in ARITY:
        spec['arity'] = list(ARITY[f])
    if conj:
        spec['conj'] = sorted(conj)
    if shape4 is not None:
        spec['shape4'] = shape4
    if f in MIN_VERSION:
        spec['min_version'] = MIN_VERSION[f]
    spec['evidence'] = evidence
    spec['exact'] = {_CNAME[c0]: round(d['exact'], 6) for c0, d in sorted(colours.items())}
    spec['records'] = {_CNAME[c0]: int(d['records']) for c0, d in sorted(colours.items())}
    return spec


def _fmt(kind):
    return 'C' if kind == 'C' else ('?' if kind is None else str(kind))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dry-run', action='store_true',
                    help='derive and report, write nothing')
    args = ap.parse_args(argv)
    model = derive()

    print('%-4s %-16s %8s %8s %9s %9s  %s'
          % ('f', 'filter', 'grey', 'colour', 'exact g', 'exact c', 'legend'))
    doc = {}
    kinds = pred = unknown = 0
    lawless, missed = [], []
    srcs = collections.Counter()
    kinded = collections.Counter()
    for f, colours in sorted(model.items()):
        sp = _spec(f, colours)
        doc[str(f)] = sp
        show = ['%d:%s' % (int(k), _fmt(v)) for k, v in sorted(sp['cls'].items(),
                                                              key=lambda t: int(t[0]))]
        if 'shape4' in sp:
            show.append('%d:%s-if-no-w1' % tuple(sp['shape4']))
        if 'conj' in sp:
            show += ['conj(%d,%d):%s' % (a, b, _fmt(v)) for a, b, v in sp['conj']]
        w1s = ['%d:%s' % (int(k), _fmt(v)) for k, v in sorted(sp['w1'].items(),
                                                             key=lambda t: int(t[0]))]
        if 'arity' in sp:
            w1s.append('arity(%d,%d)' % tuple(sp['arity']))
        if 'edge_bits' in sp:
            w1s += ['edge bit %d' % b for b in sp['edge_bits']]
        free_labs = {'cls.%d' % b for b in sp.get('cls_free', ())}
        for lab, ev in sp['evidence'].items():
            for cn, src in ev.items():
                srcs[src] += 1
                if lab not in free_labs:
                    kinded[src] += 1
                    if src in ('unexercised', 'no-records'):
                        pred += 1
        for k in list(sp['cls'].values()) + [v for _a, _b, v in sp.get('conj', ())] \
                + ([sp['shape4'][1]] if 'shape4' in sp else []) + list(sp['w1'].values()):
            if k is None:
                unknown += 1
            elif isinstance(k, list):
                lawless.append((f, k))
            else:
                kinds += 1
        for c0, d in sorted(colours.items()):
            if d['missed']:
                missed.append((f, _CNAME[c0], int(d['missed']), int(d['records'])))
        print('%-4d %-16s %8s %8s %9s %9s  %s   |   %s'
              % (f, sp['name'], sp['records'].get('grey', '-'),
                 sp['records'].get('colour', '-'),
                 '%.5f' % sp['exact']['grey'] if 'grey' in sp['exact'] else '-',
                 '%.5f' % sp['exact']['colour'] if 'colour' in sp['exact'] else '-',
                 ' '.join(show), ' '.join(w1s) or '--'))
    off = sum(len(sp['w1']) for sp in doc.values())
    print()
    print('%d kinds over %d cells, %d of them a bit offset; %d cells the corpus never bakes '
          'in either colour' % (kinds, kinds + unknown, off, unknown))
    print('%d (cell, colour) pairs carry a kind; %d of them are the legend PREDICTING a '
          'colour the corpus never exercises -- %d where the filter has no record of that '
          'colour at all, %d where it has records and none set the cell.  Every one is '
          'marked in `evidence`, never written as a measured zero.'
          % (sum(kinded.values()), pred, kinded['no-records'], kinded['unexercised']))
    print('kind-bearing (cell, colour) evidence: %s' % dict(kinded.most_common()))
    print('all (cell, colour) evidence, zero-cost class bits included: %s'
          % dict(srcs.most_common()))
    if lawless:
        print('CELLS OUTSIDE THE LEGEND ALPHABET %r:' % (WIDTHS + ('C',),))
        for f, k in lawless:
            print('   filter %-3d %s' % (f, k))
    if missed:
        print('KEYS THE LEGEND DOES NOT REPRODUCE:')
        for f, cn, m, n in missed:
            print('   filter %-3d %-6s %d of %d records' % (f, cn, m, n))
    if not args.dry_run:
        with open(OUT, 'w') as fh:
            json.dump(doc, fh, indent=0, sort_keys=True)
            fh.write('\n')
        print()
        print('wrote %s: %d filters' % (OUT, len(doc)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
