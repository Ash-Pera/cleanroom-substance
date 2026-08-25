#!/usr/bin/env python3
"""Pass/fail checks for the filter implementations in `render.py`.

`test_transpile.py` is the model: a claim is worth testing when something independent can
contradict it. Most of this project's claims are distribution matches, which cannot be
asserted. These can.

Like `test_transpile.py` this SKIPS rather than fails when the corpus is absent, since the
corpus is not in this repository. Point `SBS_CORPUS` at an unpacked collection.

Each filter is exercised by SEEDING its input through `render(precomputed=...)` rather
than by waiting for a graph to reach it. That matters: `gradient` computes zero times in a
straight corpus sweep, because every one of its 1,230 records sits behind an unimplemented
upstream filter. A filter that never runs cannot be tested by running the renderer at it.

The curve checks are the ones with teeth, and getting there took one retraction. The first
version tested "records whose spline is the identity", detected as every KNOT lying on the
diagonal, and 39 of 40 failed. The predicate was the problem: it says nothing about the
HANDLES, and a knot-on-diagonal spline with curved handles is not the identity at all.
Only 1 record in the corpus has knots and handles both on the diagonal -- the other 214
are genuinely curved and were right to disagree. That is this project's signature failure
mode, found in its own test rather than in the format.

WHAT THESE CATCH, by mutating render.py one edit at a time:

    mutation                                 caught by
    curve: swap the in/out handles           bisection cross-check
    curve: drop the spline, return input     bisection, endpoints
    curve: reverse the knot loop             NOTHING -- and it is a no-op, not a defect:
                                             the sample table is argsorted by x before use,
                                             so loop order is unobservable (verified: the
                                             two outputs differ by exactly 0.0)
    gradient: index the ramp with 1 - t      independent lookup
    gradient: stop positions used as values  bounds, independent lookup
    dirmotionblur: TAPS = 1, no blur at all  smooths-along-its-angle
    dirmotionblur: kernel 10x too long       NOTHING -- see below

The first version of this file caught three of seven, for two reasons that are both
mistakes this project has made before:

  * `gradient` and `dirmotionblur` had only BOUNDS checks -- output inside the ramp's
    range, output inside [0, 1]. Reversing a lookup and lengthening a kernel both keep
    those bounds. Bounds are cheap and nearly powerless.
  * A broken filter renders NOTHING, and the tests reported "no specimen" and SKIPPED.
    `TAPS = 1` divides by zero, every render raises, and the suite passed. Candidate
    records are now counted separately from successful ones, and finding candidates while
    rendering none is an assertion failure rather than a skip.

The 10x-kernel mutation is not caught and cannot honestly be caught here. It changes the
blur's absolute LENGTH, which is precisely what this implementation does not know: the
256-pixel reference is inherited from `directionalwarp` and is recorded in `render.py` as
possibly wrong by a constant factor. A test asserting the length would be asserting the
unestablished thing. The blind spot lines up exactly with the documented gap, which is the
honest place for it.
"""
import contextlib
import io
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import render as R                                                   # noqa: E402
from sbsasm import Assembly, FILTERS                                  # noqa: E402

MAX_FILES = 400


def _ramp(h, w):
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)
    return np.repeat(x[None, :, None], h, axis=0)


def _bezier_y(knots, x_want):
    """y at a given x, by bisecting t -- deliberately not how render.py does it."""
    for k in range(len(knots) - 1):
        p0 = (knots[k][0], knots[k][1])
        p1 = (knots[k][4], knots[k][5])
        p2 = (knots[k + 1][2], knots[k + 1][3])
        p3 = (knots[k + 1][0], knots[k + 1][1])
        if not (p0[0] - 1e-6 <= x_want <= p3[0] + 1e-6):
            continue
        lo, hi = 0.0, 1.0
        for _ in range(60):
            t = (lo + hi) / 2
            x = ((1 - t) ** 3 * p0[0] + 3 * t * (1 - t) ** 2 * p1[0]
                 + 3 * t * t * (1 - t) * p2[0] + t ** 3 * p3[0])
            lo, hi = (t, hi) if x < x_want else (lo, t)
        t = (lo + hi) / 2
        return ((1 - t) ** 3 * p0[1] + 3 * t * (1 - t) ** 2 * p1[1]
                + 3 * t * t * (1 - t) * p2[1] + t ** 3 * p3[1])
    return None


SEEN = {}


def _seeded(name, limit, predicate=None):
    """Yield (record, row) where `row` is the filter's response to a 0..1 linear ramp.

    Records `SEEN[name]` = how many CANDIDATE records were found, separately from how many
    produced a row. A caller must distinguish "no corpus" from "the filter is broken and
    rendered nothing", because the second must fail and not skip.
    """
    got = 0
    SEEN[name] = 0
    for path in corpus.paths()[:MAX_FILES]:
        try:
            asm = Assembly(path)
        except Exception:
            continue
        hits = [r for r in asm.records
                if FILTERS.get(r.filter_id) == name and r.edges and r.edges[0] is not None
                and (predicate is None or predicate(r))]
        for rec in hits[:2]:
            w, h = min(rec.width, 64), min(rec.height, 64)
            if w < 16 or h < 8:
                continue
            SEEN[name] += 1
            try:
                out, _f, _s = R.render(asm, precomputed={rec.edges[0]: _ramp(h, w)},
                                       verbose=False, max_dim=64)
            except Exception:
                continue
            arr = out.get(rec.index)
            if arr is None:
                continue
            a = np.asarray(arr, dtype=np.float32)
            yield rec, a.reshape(a.shape[0], a.shape[1], -1)[:, :, 0][0]
            got += 1
            if got >= limit:
                return


def test_curve_endpoints():
    """Whatever a spline does between its knots, it starts and ends on them."""
    n = 0
    for rec, row in _seeded('curve', 60):
        k = rec.curve_points
        assert abs(float(row[0]) - k[0][1]) < 1e-2, (rec.index, row[0], k[0][1])
        assert abs(float(row[-1]) - k[-1][1]) < 1e-2, (rec.index, row[-1], k[-1][1])
        n += 1
    if not n:
        print('SKIP test_curve_endpoints: no corpus')
    return


def test_curve_matches_independent_bisection():
    """render.py tabulates the Bezier; this solves x(t)=X directly. They must agree."""
    n = 0
    worst = 0.0
    for rec, row in _seeded('curve', 60):
        xs = np.linspace(0.0, 1.0, len(row), dtype=np.float32)
        for x, got in zip(xs, row):
            ref = _bezier_y(rec.curve_points, float(x))
            if ref is None:
                continue
            worst = max(worst, abs(float(got) - ref))
        n += 1
    if not n:
        if SEEN.get('curve'):
            raise AssertionError('%d curve records found and none rendered'
                                 % SEEN['curve'])
        print('SKIP test_curve_matches_independent_bisection: no corpus')
        return
    assert worst < 1e-3, worst
    return


def test_curve_identity_is_exact():
    """The one record whose knots AND handles are on the diagonal must be a no-op.

    Not "knots on the diagonal" -- see this module's docstring. 215 records pass that
    and 214 of them are genuinely curved.
    """
    def strict(r):
        k = r.curve_points
        return bool(k) and len(k) >= 2 and all(
            abs(p[0] - p[1]) < 1e-6 and abs(p[2] - p[3]) < 1e-6 and abs(p[4] - p[5]) < 1e-6
            for p in k)

    n = 0
    for rec, row in _seeded('curve', 4, predicate=strict):
        xs = np.linspace(0.0, 1.0, len(row), dtype=np.float32)
        assert float(np.abs(row - xs).max()) < 1e-3, rec.index
        n += 1
    if not n:
        print('SKIP test_curve_identity_is_exact: no corpus (or no strict-identity record)')
    return


def test_dirmotionblur_is_an_average():
    """A blur averages its input, so it cannot leave the input's range."""
    n = 0
    for _rec, row in _seeded('dirmotionblur', 200):
        assert float(row.min()) >= -1e-4, row.min()
        assert float(row.max()) <= 1.0 + 1e-4, row.max()
        n += 1
    if not n:
        print('SKIP test_dirmotionblur_is_an_average: no corpus')
    return


def test_gradient_runs_and_stays_bounded():
    """A ramp lookup returns values from the ramp, so it is bounded by the table."""
    n = 0
    for rec, row in _seeded('gradient', 20):
        table = rec.ramp
        if not table or isinstance(table[0][0], float):
            continue
        if rec.colour:
            # See the packed-RGBA note in the lookup test below: channel 0 of a colour
            # ramp is the low byte of `v1 | (v2 << 16)`, so the bound is over those bytes.
            if len(table[0]) < 3:
                continue
            packed = [(int(e[1]) | (int(e[2]) << 16)) & 0xFFFFFFFF for e in table]
            vals = np.array([u & 0xFF for u in packed], dtype=np.float32) / 255.0
        else:
            vals = np.array([e[1] for e in table], dtype=np.float32) / 65535.0
        assert float(row.min()) >= float(vals.min()) - 1e-3, rec.index
        assert float(row.max()) <= float(vals.max()) + 1e-3, rec.index
        n += 1
    if not n:
        print('SKIP test_gradient_runs_and_stays_bounded: no corpus')
    return


def test_gradient_matches_an_independent_lookup():
    """Recompute the ramp lookup here and compare, rather than only bounding it.

    The bound check below passes when the ramp is indexed with `1 - t` instead of `t`,
    because reversing a lookup keeps every value inside the table. Only recomputing
    catches that.
    """
    n = 0
    worst = 0.0
    for rec, row in _seeded('gradient', 20):
        table = rec.ramp
        if not table or isinstance(table[0][0], float):
            continue
        stops = np.array([e[0] for e in table], dtype=np.float32) / 65535.0
        if rec.colour:
            # A COLOUR ramp's two value words are one packed RGBA8888, so the reference
            # for channel 0 is the low byte of `v1 | (v2 << 16)` over 255 -- not the
            # greyscale reading, which would be v1 over 65535.
            #
            # These records reached this test for the first time when render.py stopped
            # refusing them: previously they raised, `out.get` returned None and _seeded
            # skipped them, so the greyscale reference was never applied to a colour
            # table. It is applied here deliberately rather than skipped, because
            # recomputing the packed reading independently is what makes this test cover
            # the new decode instead of merely tolerating it.
            if len(table[0]) < 3:
                continue
            packed = [(int(e[1]) | (int(e[2]) << 16)) & 0xFFFFFFFF for e in table]
            vals = np.array([u & 0xFF for u in packed], dtype=np.float32) / 255.0
        else:
            vals = np.array([e[1] for e in table], dtype=np.float32) / 65535.0
        xs = np.linspace(0.0, 1.0, len(row), dtype=np.float32)
        ref = np.interp(xs, stops, vals)
        worst = max(worst, float(np.abs(row - ref).max()))
        n += 1
    if not n:
        if SEEN.get('gradient'):
            raise AssertionError('%d gradient records found and none rendered'
                                 % SEEN['gradient'])
        print('SKIP test_gradient_matches_an_independent_lookup: no corpus')
        return
    assert worst < 1e-3, worst
    return


def _stripes(h, w, along):
    """A high-frequency pattern varying along one axis only."""
    x = (np.arange(w if along == 'x' else h, dtype=np.float32) % 4 < 2).astype(np.float32)
    if along == 'x':
        return np.repeat(x[None, :, None], h, axis=0)
    return np.repeat(x[:, None, None], w, axis=1)


def _blur_once(rec, asm, src, max_dim=64):
    out, _f, _s = R.render(asm, precomputed={rec.edges[0]: src}, verbose=False,
                           max_dim=max_dim)
    got = out.get(rec.index)
    return None if got is None else np.asarray(got, dtype=np.float32)


def test_dirmotionblur_actually_smooths_and_only_along_its_angle():
    """A blur must reduce variance ACROSS its direction and leave the other axis alone.

    The range check elsewhere in this file passes for TAPS=1 -- no blur at all -- and for a
    kernel ten times too long, because averaging keeps everything inside [0, 1] either way.
    This is the check that fails for both.

    Specimen selection is forced by the data, not chosen for convenience. Baked `intensity`
    has a median of 1.45, which in normalised units displaces by well under a pixel and
    would smooth nothing, so the test needs |intensity| >= 16. Of those, the axis-aligned
    angles are 139 at +0.25 and 1 at -0.25 -- both of which blur along Y, since
    `dy = length * sin(2*pi*angle)`. So stripes running across Y must smear and stripes
    running across X must not.
    """
    tested = ok = candidates = 0
    for path in corpus.paths()[:MAX_FILES]:
        try:
            asm = Assembly(path)
        except Exception:
            continue
        for rec in asm.records:
            if FILTERS.get(rec.filter_id) != 'dirmotionblur':
                continue
            if not rec.edges or rec.edges[0] is None:
                continue
            baked = {k: float(v) for k, kind, v in (rec.named_parameters or [])
                     if kind == 'baked'}
            it, an = baked.get('intensity'), baked.get('mblurangle')
            if it is None or an is None or abs(it) < 16.0:
                continue
            if abs((an * 4) % 1) > 1e-3:
                continue
            w, h = min(rec.width, 64), min(rec.height, 64)
            if w < 32 or h < 32:
                continue
            candidates += 1
            vary_y = _stripes(h, w, 'y')       # varies along Y -- the blur axis
            vary_x = _stripes(h, w, 'x')       # varies along X -- across it
            by = _blur_once(rec, asm, vary_y)
            bx = _blur_once(rec, asm, vary_x)
            if by is None or bx is None:
                continue
            tested += 1
            if float(by.std()) < 0.7 * float(vary_y.std()) and \
               float(bx.std()) > 0.7 * float(vary_x.std()):
                ok += 1
            if tested >= 12:
                break
        if tested >= 12:
            break
    if not candidates:
        print('SKIP test_dirmotionblur_actually_smooths_and_only_along_its_angle: no corpus')
        return
    # NOT a skip. Specimens exist and none of them rendered, which is what a broken filter
    # looks like from here -- setting TAPS=1 divides by zero, every render raises, and the
    # first version of this check reported "no specimen" and passed.
    assert tested, ('specimens found but none rendered', candidates)
    assert ok / tested > 0.75, (ok, tested)
    return


# The standalone runner reads SKIP from what a check PRINTS, not from what it returns.
# These functions used to return a count and the runner reported "skipped" when it was
# falsy -- but a pytest test function that returns non-None is a warning today and an
# error in a future pytest, so the returns are gone. Reading the printed SKIP keeps the
# distinction that matters: a suite that silently skips everything looks identical to a
# passing one, which is the failure this directory has already recorded once.
if __name__ == '__main__':
    for fn in (test_curve_endpoints,
               test_gradient_matches_an_independent_lookup,
               test_dirmotionblur_actually_smooths_and_only_along_its_angle, test_curve_matches_independent_bisection,
               test_curve_identity_is_exact, test_dirmotionblur_is_an_average,
               test_gradient_runs_and_stays_bounded):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        out = buf.getvalue()
        sys.stdout.write(out)
        print('%-46s %s' % (fn.__name__, 'skipped' if 'SKIP' in out else 'ok'))
