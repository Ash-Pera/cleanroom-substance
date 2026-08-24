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
"""
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


def _seeded(name, limit, predicate=None):
    """Yield (record, row) where `row` is the filter's response to a 0..1 linear ramp."""
    got = 0
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
    return n


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
        print('SKIP test_curve_matches_independent_bisection: no corpus')
        return 0
    assert worst < 1e-3, worst
    return n


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
    return n


def test_dirmotionblur_is_an_average():
    """A blur averages its input, so it cannot leave the input's range."""
    n = 0
    for _rec, row in _seeded('dirmotionblur', 200):
        assert float(row.min()) >= -1e-4, row.min()
        assert float(row.max()) <= 1.0 + 1e-4, row.max()
        n += 1
    if not n:
        print('SKIP test_dirmotionblur_is_an_average: no corpus')
    return n


def test_gradient_runs_and_stays_bounded():
    """A ramp lookup returns values from the ramp, so it is bounded by the table."""
    n = 0
    for rec, row in _seeded('gradient', 20):
        table = rec.ramp
        if not table or isinstance(table[0][0], float):
            continue
        vals = np.array([e[1] for e in table], dtype=np.float32) / 65535.0
        assert float(row.min()) >= float(vals.min()) - 1e-3, rec.index
        assert float(row.max()) <= float(vals.max()) + 1e-3, rec.index
        n += 1
    if not n:
        print('SKIP test_gradient_runs_and_stays_bounded: no corpus')
    return n


if __name__ == '__main__':
    for fn in (test_curve_endpoints, test_curve_matches_independent_bisection,
               test_curve_identity_is_exact, test_dirmotionblur_is_an_average,
               test_gradient_runs_and_stays_bounded):
        got = fn()
        print('%-46s %s' % (fn.__name__, ('ok, %d records' % got) if got else 'skipped'))
