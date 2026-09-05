#!/usr/bin/env python3
"""The reference guard: three quantities, several grids, and a register of causes.

WHAT THIS REPLACES AND WHY. Every reference guard in this repository was ONE CORRELATION
FLOOR PER CHANNEL AT ONE GRID, and it failed in four distinct ways while missing three real
regressions. The four, each with the commit that measured it:

  1. CORRELATION IS BLIND TO COLLAPSE. `ad493f2` put Chesterfield's `AO` at 2.6% of the
     export's structure -- band total 0.026 -- while it correlated +0.9110 against a 0.84
     floor. A picture at a fortieth of the right amplitude, in the right places, passes a
     correlation floor with room to spare. Only a band ratio saw it.

  2. CORRELATION IS BLIND TO LEVEL. `ba3a1f6` measured Chesterfield's `roughness` at
     +0.9345 against a 0.91 floor with MAE 0.0639 and DC -0.0638 -- 99.9% of its whole
     error is one constant. Every column `refcompare` printed was mean-removed BY
     CONSTRUCTION (`corr`, `band_power`, `structure`, and `resid`, whose affine fit absorbs
     any constant), so no instrument in the tree could see it until the `DC=` column landed.

  3. A SINGLE GRID HIDES SIGN-REVERSING REGRESSIONS. `ce5897e` measured `Chesterfield
     normal 2` moving -0.1061 / -0.0457 / +0.0411 / +0.0437 at `--dim` 128 / 256 / 512 /
     1024 under one correction, with MAE improving at EVERY one of the four. The floor was
     scored at 256, so it read a real improvement as a break.

  4. "NO REFERENCE CHANNEL MAY GET WORSE" IS UNSATISFIABLE. Proven twice. The `imageindex`
     recovery loses 0.0010 on `roughness` and 0.0015 on `AO` at `--dim` 512 while improving
     both elsewhere (`ce5897e`); the roughness-level fix breaks `basecolor` ch2 while taking
     `roughness`'s MAE from 0.0639 to 0.0071 (`ba3a1f6`). A renderer wrong in several places
     cannot be fixed one channel at a time without some channel moving adversely.

And it MISSED A LIVE REGRESSION FOR SIX COMMITS: `e231131` cut ChesterfieldSofa from 881
records to 858 and stopped producing `basecolor` and `roughness` entirely, and no floor
existed on those packs at the time (`23a5492`).

THE THREE QUANTITIES, one per defect class, all of them already instruments this repository
owns and none of them new arithmetic:

    corr    Pearson correlation on the 64-px score grid -- is the structure in the RIGHT
            PLACES.  This is the old guard, kept whole.
    band    `band_power`'s total, ours over reference, a VARIANCE ratio -- is there the
            RIGHT AMOUNT of structure.  1.0 is the target; 0.026 is `ad493f2`'s AO.
    dc      `ours.mean() - ref.mean()` -- is the LEVEL right.  0.0 is the target; -0.0639
            is `ba3a1f6`'s roughness.

MAE is recorded beside them as context and is not a bound: it is the sum of the three and
cannot say which one moved, which is the whole reason this file exists.

TWO KINDS OF BOUND, and keeping them apart is what makes the guard readable.

  * HEALTH BARS are absolute and say what a correct channel looks like: `|dc| <= 0.02` and
    `band` within a factor of 4 of 1.0. They are evaluated at EVERY scored grid and a
    violation at any one is a failure. They are how a channel that is BROKEN TODAY fails
    today -- which is the point, not a bug.

  * THE RATCHET is relative and says a channel may not get worse than the value recorded
    for it. Every bound is derived from a MEASURED value plus a stated margin; nothing here
    is aspirational and nothing may be set by hand.

A channel that fails a health bar must carry a DECLARED CAUSE naming the record or the
mechanism responsible (see `Cause`). A declaration is not an amnesty: it PINS the quantity
two-sided at the value recorded with it, so the suite is green on HEAD and any MOVEMENT --
better or worse -- is what breaks it and forces the entry to be re-taken deliberately. A
bypass with no cause, or with a cause that names nothing, fails.

GRID SENSITIVITY IS HANDLED BY SCORING AT SEVERAL, NOT BY PICKING A BETTER ONE. Failure 3
is a property of scoring at one grid and no single grid fixes it -- 256 read a real
improvement as a break, and 512 would have read `ad493f2`'s AO collapse the same way 256
did. Each table states its own grid set; each grid carries its own recorded triple and its
own bounds; and the RATCHET fails only where a movement is adverse AT EVERY SCORED GRID, or
adverse by more than a hard margin at any one of them. The hard margins are set above the
largest grid-reversing movement this repository has measured (0.1061 of correlation, on
`Chesterfield normal 2` under `ce5897e`) and are stated as constants below, so a reader can
see the number that set them.

WHAT IS NOT HERE. There is no absolute CORRELATION bar. Correlation health is exactly what
the old floors measured, the recorded per-grid value is the bound, and adding an absolute
bar on top would recategorise a dozen channels this repository lists deliberately as weak
(`Bricks basecolor` at +0.04, `Chesterfield basecolor 2` at -0.46) as declared failures
without any new evidence about them. Their bounds are re-taken and they stay ratchets.

THE SCALES ARE NOT REIMPLEMENTED HERE. `structure`, `band_power`, `BANDS`, `LOW_GRID` and
`resample` MOVED to this module from `archive/tools/refcompare.py` -- with their docstrings
-- and `refcompare` imports them back, so there is exactly one implementation and every
existing caller keeps its name. This module imports numpy and PIL and nothing else in the
tree, which is what lets `tools/render2/test_render2.py` use it without dragging a renderer
into its process.
"""
import math

import numpy as np


#: The grid `corr`, `dc` and `mae` are taken on. `refcompare.SIZE`, kept identical: every
#: floor this repository has ever recorded is a correlation of two 64-px resamples, and a
#: guard that changed this would not be comparable to a single recorded number.
SCORE_GRID = 64


#: The low-pass grid `structure` reduces to. FIXED, so that "low frequency" means the same
#: band whatever grid the pair is compared on: a fixed 8x8 block would be 1/64 of the canvas
#: at 512 and 1/256 of it at 2048, and the number would then move with the grid rather than
#: with the render.
LOW_GRID = 64


#: Radial band edges in CYCLES PER IMAGE -- canvas-relative, so a band means the same
#: feature size whatever grid the pair is compared on.
BANDS = (1, 7, 10, 14, 20, 32, 128)


def resample(x, n=SCORE_GRID):
    """Per channel, at 16-bit precision -- an 8-bit round trip here would quantise the
    very differences being measured."""
    from PIL import Image
    x = np.clip(x, 0.0, 1.0)
    if x.ndim == 2:
        x = x[:, :, None]
    chans = [np.asarray(Image.fromarray((x[:, :, c] * 65535).astype(np.uint16))
                        .resize((n, n), Image.BILINEAR), dtype=np.float64) / 65535.0
             for c in range(x.shape[2])]
    return np.stack(chans, axis=-1)


def structure(a, low_grid=LOW_GRID):
    """(low-frequency field sd, high-frequency edge sd) of ONE channel, at ITS OWN grid.

    THE TWO QUANTITIES OPPOSE, WHICH IS THE WHOLE POINT. Every score in this module is a
    scalar taken after both sides are resampled to `SIZE` = 64, and a scalar cannot score a
    pattern PROFILE: `fxrender.py`'s negative result 1 records that any falloff at all takes
    "renders a picture" from 4.1% to 97.3% and means nothing, because a profile with falloff
    cannot be flat by construction. A pair of quantities that must move in OPPOSITE
    directions is not defeatable that way -- a falloff too soft fills the panel and loses the
    seam, one too hard keeps the seam and never fills the panel, and only the right one moves
    both toward 1 at once.

      low   the sd of the image reduced to `low_grid` by block averaging -- panel-scale
            variation, the "field" half. Ours too flat reads low < ref.
      edge  the sd of `d/dy + d/dx` per pixel -- the seam/grain half. Ours too hard reads
            edge > ref.

    BOTH ARE GRID-DEPENDENT AND ONLY THEIR RATIO IS NOT, which is not a nicety: `edge` is a
    PER-PIXEL difference, so a smooth image sampled twice as finely has half the gradient,
    and comparing a 512-px render against a 2048-px export understates the export's edge
    energy by about a factor of two. That is a property of the two rulers and not of either
    picture. Callers must put both sides on ONE grid first -- `structure_grid` does -- and
    read the RATIO ours/ref, whose target is 1.0 on both halves.
    """
    a = np.asarray(a, dtype=np.float64)
    h, w = a.shape[:2]
    k = max(1, min(h, w) // low_grid)
    lo = a[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    d = np.diff(a, axis=0)[:, :-1] + np.diff(a, axis=1)[:-1, :]
    return float(lo.std()), float(d.std())


def band_power(a, edges=BANDS):
    """Power per radial band, in VARIANCE units, so two images are directly comparable.

    WHY A SPECTRUM AND NOT THE TWO SUMMARY NUMBERS ABOVE. `structure` returns one
    low-frequency and one high-frequency scalar, and a pair of scalars cannot tell a SHAPE
    error from an AMPLITUDE one. They have different signatures and the bands show it:

      a wrong pattern profile REDISTRIBUTES energy between bands -- a hard edge pushes it
        up, a soft one pulls it down -- so the ratio ours/ref is TILTED across the octaves
      a wrong gain scales every band together, so the ratio is FLAT and equal to the gain

    Read the ratios across bands before concluding anything from either summary scalar.

    Hanning-windowed, because the maps tile and a rectangular window puts the wrap
    discontinuity into every band. Parseval-scaled by `1 / (h*w)**2`, so the bands sum to
    the variance of the windowed, mean-removed image and a band ratio is a variance ratio.
    """
    a = np.asarray(a, dtype=np.float64)
    h, w = a.shape[:2]
    x = (a - a.mean()) * (np.hanning(h)[:, None] * np.hanning(w)[None, :])
    f = np.fft.rfft2(x)
    p = (f.real ** 2 + f.imag ** 2) / float(h * w) ** 2
    # `rfft2` keeps half the plane; every column but DC and Nyquist stands for two.
    p[:, 1:w // 2 if w % 2 == 0 else None] *= 2.0
    r = np.hypot((np.fft.fftfreq(h) * h)[:, None], (np.fft.rfftfreq(w) * w)[None, :])
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        out.append(float(p[(r >= lo) & (r < hi)].sum()))
    return out, float(p[r >= 1].sum())


def structure_grid(ours, ref, grid=None):
    """Both channels on one square grid -- the smaller native one unless told otherwise.

    NATIVE IS LEFT NATIVE. `resample` is a uint16 round trip through PIL, and asking it for
    the size an array already has is not free of it; a side that needs no resizing is passed
    through so that "compared at 2048" means the export's own pixels.
    """
    n = grid or min(ours.shape[0], ours.shape[1], ref.shape[0], ref.shape[1])
    out = []
    for a in (ours, ref):
        a = np.clip(np.asarray(a, dtype=np.float64), 0.0, 1.0)
        out.append(a if a.shape[0] == n and a.shape[1] == n
                   else resample(a[:, :, None], n)[:, :, 0])
    return n, out[0], out[1]


# --------------------------------------------------------------------------------------
# The reading


class Reading(object):
    """What one channel measures against its reference at one render grid.

    `corr`, `dc` and `mae` are taken on the 64-px score grid, which is where every floor
    this repository has recorded was taken. `band` is taken at the pair's own smaller
    NATIVE grid through `structure_grid`, which is where every band number the notes quote
    was taken -- a band ratio on a 64-px resample would have no octaves above 32 cycles to
    put energy in. The two are deliberately different grids and saying so is the point of
    this docstring.
    """
    __slots__ = ('corr', 'band', 'dc', 'mae', 'sd', 'ref_sd', 'uniq', 'band_n', 'bands')

    def __init__(self, corr, band, dc, mae, sd, ref_sd, uniq, band_n, bands):
        self.corr, self.band, self.dc, self.mae = corr, band, dc, mae
        self.sd, self.ref_sd, self.uniq = sd, ref_sd, uniq
        self.band_n, self.bands = band_n, bands

    @property
    def flat(self):
        return self.sd <= 1e-9

    def triple(self):
        return (round(self.corr, 4), round(self.band, 4), round(self.dc, 4))

    def __repr__(self):
        return ('Reading(corr=%+.4f band=%.4f dc=%+.4f mae=%.4f sd=%.5f ref_sd=%.5f '
                'uniq=%d n=%d)' % (self.corr, self.band, self.dc, self.mae, self.sd,
                                   self.ref_sd, self.uniq, self.band_n))


def measure(ours, ref, score_grid=SCORE_GRID, band_grid=None):
    """The three quantities for one channel pair, from two NATIVE 2-D arrays.

    Callers must pass native arrays -- `refcompare.compare_pack(..., grid=None)` -- because
    this function owns both grids and a caller that has already resampled to 64 has thrown
    away every octave the band ratio is about.
    """
    ours = np.asarray(ours, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    if ours.ndim == 3:
        ours = ours[:, :, 0]
    if ref.ndim == 3:
        ref = ref[:, :, 0]
    o = resample(ours[:, :, None], score_grid)[:, :, 0]
    r = resample(ref[:, :, None], score_grid)[:, :, 0]
    sd, ref_sd = float(o.std()), float(r.std())
    corr = 0.0
    if sd > 1e-9 and ref_sd > 1e-9:
        corr = float(np.corrcoef(o.ravel(), r.ravel())[0, 1])
    dc = float(o.mean() - r.mean())
    mae = float(np.abs(o - r).mean())
    uniq = int(len(np.unique(np.round(o.ravel(), 4))))
    n, o_n, r_n = structure_grid(ours, ref, band_grid)
    (bo, to), (br, tr) = band_power(o_n), band_power(r_n)
    band = float(to / tr) if tr > 1e-18 else float('inf') if to > 1e-18 else 1.0
    bands = tuple(float(b / c) if c > 1e-18 else float('inf') for b, c in zip(bo, br))
    return Reading(corr, band, dc, mae, sd, ref_sd, uniq, n, bands)


# --------------------------------------------------------------------------------------
# The bounds


#: How far under its recorded value a correlation may fall before the movement counts as
#: adverse at that grid. The floors this replaces sat 0.02 to 0.03 under their measured
#: values by the same reasoning: "float noise passes and a collapse does not".
CORR_MARGIN = 0.02

#: How much FURTHER FROM 1.0, in natural-log units, the band total may go. 0.10 is 10.5%
#: of amplitude. `ad493f2`'s AO collapse is |log 0.026| = 3.65, two orders of magnitude
#: past it; the imageindex correction's AO movement is 0.16, one and a half times it.
BAND_MARGIN = 0.10

#: How much FURTHER FROM 0.0 the level may go. `ba3a1f6` measured this channel's DC as
#: constant to 0.0002 across an 8x range of render grid, so the tolerance is about float
#: noise and resample jitter and nothing else.
DC_MARGIN = 0.005

#: THE HARD MARGINS: a movement this far past the bound at ANY ONE grid fails on its own,
#: without needing to be adverse at all of them. They exist so that scoring at several
#: grids is not weaker than scoring at one -- the cross-grid rule below forgives a movement
#: that reverses sign with the grid, and these keep it from forgiving a large one.
#:
#: THE CORRELATION NUMBER IS SET FROM A MEASUREMENT, not chosen. The largest grid-reversing
#: correlation movement this repository has measured is `Chesterfield normal 2` under
#: `ce5897e`: -0.1061 at 128, -0.0457 at 256, +0.0411 at 512, +0.0437 at 1024, with MAE
#: improving at all four. 0.13 past a bound that already sits 0.02 under the recorded value
#: puts the hard bar at 0.15 of movement, above that 0.1061 and deliberately so.
CORR_HARD = 0.13
BAND_HARD = 0.50
DC_HARD = 0.02


#: HEALTH BARS. Absolute, and they say what a channel in good health looks like rather than
#: what this renderer happens to produce. A channel outside them is BROKEN, and the guard
#: says so unless the entry declares a cause.
#:
#: `DC_BAR` at 0.02 is 2% of the [0, 1] range. `ba3a1f6`'s roughness is at 0.0639, three
#: times it, and `metallic` -- the control, MAE 0.0004 -- is at 0.0003.
#:
#: `BAND_BAR` at 4.0 is a factor of four either way, which is loose on purpose: this file's
#: predecessor says "a real collapse is orders of magnitude, not percent", and `ad493f2`'s
#: AO is a factor of 38. A tighter bar would catch more and would also declare half the
#: table broken on evidence nobody has gathered yet.
DC_BAR = 0.02
BAND_BAR = 4.0


class Cause(object):
    """Why a channel is allowed to sit outside a health bar, naming what is responsible.

    THIS IS THE MECHANISM THAT REPLACES "NO REFERENCE CHANNEL MAY GET WORSE". That bar was
    proven unsatisfiable twice -- see this module's header -- and the replacement is not a
    looser bar but a different question: not "did anything get worse" but "is every
    adverse movement ACCOUNTED FOR". A cause must name a record index or a mechanism; a
    declaration with neither is rejected by `check`, so a bypass cannot be written by
    leaving the reason out.

    `at` is the measured value the declaration was taken with, per grid, and it PINS the
    quantity two-sided: the entry is green while it reproduces and fails the moment it
    moves in either direction. An improvement failing the suite is intended -- it means the
    recorded cause is no longer the whole story and the entry is owed a re-take.
    """
    __slots__ = ('ident', 'mechanism', 'records', 'note', 'source')

    def __init__(self, ident, mechanism='', records=(), note='', source=''):
        self.ident = ident
        self.mechanism = mechanism
        self.records = tuple(records)
        self.note = note
        self.source = source

    def names_something(self):
        """A cause must name a RECORD or a MECHANISM. Empty strings name nothing."""
        return bool(self.records) or len(self.mechanism.strip()) >= 8

    def __repr__(self):
        return 'Cause(%s, records=%s)' % (self.ident, list(self.records))


class Entry(object):
    """One (pack, output, channel) as MEASURED, per grid, with what it used to be.

    `at` is `{grid: (corr, band, dc)}` -- the value read today, at each grid the table
    scores. Nothing in this structure is a bound: `check` derives every bound from these
    numbers and the margins above, which is what "re-take every entry at its current
    measured value" means operationally. A bound cannot be typed in by hand, so it cannot
    be typed in low.

    `was` is `(old floor, the grid it was taken at)` from the correlation-floor table this
    replaces, or None for an entry that never had one. It is not decoration: `check`
    refuses to let the derived correlation bound fall below it, so re-taking can RAISE a
    floor and can never lower one, and `test_the_new_guard_does_not_weaken_the_old_floors`
    reads it directly.

    `declared` is `{quantity: cause id}` for quantities outside a health bar today.
    `mae` is recorded per grid as context and is not bounded.
    """
    __slots__ = ('at', 'was', 'declared', 'mae', 'note')

    def __init__(self, at, was=None, declared=None, mae=None, note=''):
        self.at = dict(at)
        self.was = was
        self.declared = dict(declared or {})
        self.mae = dict(mae or {})
        self.note = note

    def grids(self):
        return sorted(self.at)

    def bound(self, quantity, grid):
        """The bound this entry's recorded value implies for one quantity at one grid.

        corr  a LOWER bound: the recorded value less `CORR_MARGIN`, never below the old
              floor if this entry had one at this grid.
        band  an upper bound on |log(band)|: no further from 1.0 than recorded, plus
              `BAND_MARGIN`.
        dc    an upper bound on |dc|: no further from 0.0 than recorded, plus `DC_MARGIN`.
        """
        corr, band, dc = self.at[grid]
        if quantity == 'corr':
            lo = corr - CORR_MARGIN
            if self.was is not None and self.was[1] == grid:
                lo = max(lo, self.was[0])
            return lo
        if quantity == 'band':
            return abs(math.log(max(band, 1e-9))) + BAND_MARGIN
        if quantity == 'dc':
            return abs(dc) + DC_MARGIN
        raise KeyError(quantity)


def _adverse(quantity, value, bound):
    """How far past the bound a value sits, in that quantity's own units. <= 0 is fine."""
    if quantity == 'corr':
        return bound - value
    if quantity == 'band':
        return abs(math.log(max(value, 1e-9))) - bound
    if quantity == 'dc':
        return abs(value) - bound
    raise KeyError(quantity)


def _hard(quantity):
    return {'corr': CORR_HARD, 'band': BAND_HARD, 'dc': DC_HARD}[quantity]


def _value(reading, quantity):
    return {'corr': reading.corr, 'band': reading.band, 'dc': reading.dc}[quantity]


def _health(quantity, value):
    """Is this value inside its absolute health bar? `corr` has none -- see the header."""
    if quantity == 'dc':
        return abs(value) <= DC_BAR
    if quantity == 'band':
        return (1.0 / BAND_BAR) <= value <= BAND_BAR
    return True


def _fmt_key(key):
    """A table key rendered for a message. Keys are TUPLES -- (pack, output, channel) --
    and `_fmt_key(key)` on a bare string silently yields one entry per CHARACTER rather than
    failing, which is how a misuse would reach a reader as `['a', 'o']` instead of `ao`.
    A guard whose own reporting degrades quietly is the thing this module exists to stop.
    """
    if isinstance(key, (str, bytes)):
        return key if isinstance(key, str) else key.decode('utf-8', 'replace')
    return ' '.join(str(p) for p in key)


QUANTITIES = ('corr', 'band', 'dc')


def check(table, readings, causes, label=''):
    """Score a whole table. Returns a list of failure strings, empty when the table holds.

    `readings` is `{key: {grid: Reading}}`; a key or a grid that is absent is a MISSING
    channel, which is `e231131`'s shape and is the first thing this reports.

    THE ORDER OF THE CHECKS IS THE ORDER OF THE EVIDENCE. Missing first, because a channel
    that stopped rendering is not a channel that got worse. Flat second, for the same
    reason. Then the declarations, because a declaration that no longer reproduces makes
    every bound under it meaningless. Then the health bars, then the ratchet.
    """
    fails = []
    pre = ('%s: ' % label) if label else ''
    for key in sorted(table):
        e = table[key]
        got = readings.get(key) or {}
        want = e.grids()
        absent = [g for g in want if g not in got]
        if absent:
            fails.append('%s%s is no longer produced or paired at grid(s) %s -- this is '
                         'the e231131 shape: an output stopped rendering and nothing '
                         'failed' % (pre, _fmt_key(key), absent))
            continue
        flat = [g for g in want if got[g].flat]
        if flat:
            fails.append('%s%s renders CONSTANT at grid(s) %s -- this is the b2f1d97 shape'
                         % (pre, _fmt_key(key), flat))
            continue
        for q in QUANTITIES:
            cid = e.declared.get(q)
            vals = {g: _value(got[g], q) for g in want}
            if cid is not None:
                cause = causes.get(cid)
                if cause is None:
                    fails.append('%s%s declares %s under cause %r, which is not in the '
                                 'cause register -- a bypass needs a cause'
                                 % (pre, _fmt_key(key), q, cid))
                    continue
                if not cause.names_something():
                    fails.append('%s%s declares %s under cause %r, which names neither a '
                                 'record nor a mechanism -- a bypass with no cause must '
                                 'fail' % (pre, _fmt_key(key), q, cid))
                    continue
                # A DECLARATION IS A PIN, NOT AN AMNESTY. Two-sided, at every grid.
                moved = []
                for g in want:
                    rec = e.at[g][QUANTITIES.index(q)]
                    tol = {'corr': CORR_MARGIN, 'band': BAND_MARGIN, 'dc': DC_MARGIN}[q]
                    if q == 'band':
                        off = abs(math.log(max(vals[g], 1e-9)) - math.log(max(rec, 1e-9)))
                    else:
                        off = abs(vals[g] - rec)
                    if off > tol:
                        moved.append((g, round(rec, 4), round(vals[g], 4)))
                if moved:
                    fails.append(
                        '%s%s %s is DECLARED broken under %r and has MOVED: (grid, '
                        'recorded, now) %s. A declared quantity is pinned two-sided -- if '
                        'this improved, re-take the entry and say why; if it got worse, '
                        'the recorded cause is no longer the whole story'
                        % (pre, _fmt_key(key), q, cid, moved))
                continue
            sick = [(g, round(vals[g], 4)) for g in want if not _health(q, vals[g])]
            if sick:
                fails.append(
                    '%s%s %s is outside its health bar at (grid, value) %s and declares no '
                    'cause. Either the channel regressed, or it is broken today and the '
                    'entry owes a Cause naming the record or mechanism responsible'
                    % (pre, _fmt_key(key), q, sick))
                # AND FALL THROUGH TO THE RATCHET. This used to `continue`, so a quantity
                # that was BOTH outside its health bar and adverse against its recorded
                # value reported only the first and the regression went unlisted. That is
                # not hypothetical: on the `imageindex` correction, `Chesterfield basecolor`
                # dc was adverse at ALL THREE grids (-0.0493 -> -0.0999) and `check`
                # returned five failures with that one absent, because the same quantity was
                # already failing its health bar. A guard that truncates its own findings is
                # the disease this module was written to cure. The two are different claims
                # -- "this channel is broken today" and "this change made it worse" -- and a
                # reader needs both, so both are appended.
            over = {g: _adverse(q, vals[g], e.bound(q, g)) for g in want}
            worst = max(over, key=lambda g: over[g])
            if over[worst] > _hard(q):
                fails.append(
                    '%s%s %s fell %.4f past its bound at grid %d (recorded %.4f, now '
                    '%.4f) -- past the hard margin, so one grid is enough'
                    % (pre, _fmt_key(key), q, over[worst], worst,
                       e.at[worst][QUANTITIES.index(q)], vals[worst]))
                continue
            if all(over[g] > 0 for g in want):
                fails.append(
                    '%s%s %s is adverse at EVERY scored grid %s: recorded %s, now %s'
                    % (pre, _fmt_key(key), q, want,
                       [round(e.at[g][QUANTITIES.index(q)], 4) for g in want],
                       [round(vals[g], 4) for g in want]))
    return fails


def report(table, readings, quantity=None):
    """One line per entry per grid: recorded, measured, and whether it moved adversely.

    For a human re-taking the table, and for the printed tail of a passing test -- a guard
    that only speaks when it fails cannot be checked for having measured anything.
    """
    out = []
    for key in sorted(table):
        e = table[key]
        for g in e.grids():
            r = (readings.get(key) or {}).get(g)
            if r is None:
                out.append('%-70s %5d  MISSING' % ('/'.join(str(k) for k in key), g))
                continue
            rec = e.at[g]
            marks = []
            for q in QUANTITIES:
                if quantity and q != quantity:
                    continue
                over = _adverse(q, _value(r, q), e.bound(q, g))
                marks.append('%s%s' % (q, '!' if over > 0 else ''))
            out.append('%-70s %5d  corr %+.4f (%+.4f)  band %.4f (%.4f)  dc %+.4f (%+.4f)'
                       '  mae %.4f  %s'
                       % ('/'.join(str(k) for k in key), g, r.corr, rec[0], r.band, rec[1],
                          r.dc, rec[2], r.mae, ' '.join(marks)))
    return out
