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
import collections
import contextlib
import glob
import io
import os
import re
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import decompose                                                     # noqa: E402
import manifest                                                      # noqa: E402
import provenance                                                    # noqa: E402
import render as R                                                   # noqa: E402
import sbsasm                                                        # noqa: E402
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
_SEEDED = {}


def _seeded(name, limit, predicate=None):
    """Memoized front for _seeded_uncached.

    Every filter here is probed by two tests with identical arguments -- curve by
    endpoints and by bisection, dirmotionblur by range and by directionality, gradient
    by bounds and by lookup -- and each call re-rendered the same records from scratch.
    Only predicate-free calls are shared, because a predicate is a closure this cannot
    key on.
    """
    if predicate is not None:
        for item in _seeded_uncached(name, limit, predicate):
            yield item
        return
    key = (name, limit)
    if key not in _SEEDED:
        rows, seen_before = [], SEEN.get(name)
        for item in _seeded_uncached(name, limit):
            rows.append(item)
        _SEEDED[key] = (rows, SEEN.get(name))
    rows, seen = _SEEDED[key]
    SEEN[name] = seen           # restore the candidate count the callers check
    for item in rows:
        yield item


def _seeded_uncached(name, limit, predicate=None):
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
                                       verbose=False, max_dim=64,
                                       stop_after=rec.index)
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
        # NOT a bare skip. `_seeded` records SEEN['curve'] = candidates FOUND, separately from
        # how many rendered, precisely so this case can be told apart: candidates present
        # and none rendered is what a BROKEN FILTER looks like from here, and it must fail.
        # Three of the eight checks in this file already did this; five, including this
        # one, printed SKIP instead and would have reported green through a total breakage.
        if SEEN.get('curve'):
            raise AssertionError('%d curve records found and none rendered' % SEEN['curve'])
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
        # NOT a bare skip. `_seeded` records SEEN['curve'] = candidates FOUND, separately from
        # how many rendered, precisely so this case can be told apart: candidates present
        # and none rendered is what a BROKEN FILTER looks like from here, and it must fail.
        # Three of the eight checks in this file already did this; five, including this
        # one, printed SKIP instead and would have reported green through a total breakage.
        if SEEN.get('curve'):
            raise AssertionError('%d strict-identity curve records found and none rendered' % SEEN['curve'])
        print('SKIP test_curve_identity_is_exact: no corpus, or no strict-identity record')
    return


def test_dirmotionblur_is_an_average():
    """A blur averages its input, so it cannot leave the input's range."""
    n = 0
    for _rec, row in _seeded('dirmotionblur', 200):
        assert float(row.min()) >= -1e-4, row.min()
        assert float(row.max()) <= 1.0 + 1e-4, row.max()
        n += 1
    if not n:
        # NOT a bare skip. `_seeded` records SEEN['dirmotionblur'] = candidates FOUND, separately from
        # how many rendered, precisely so this case can be told apart: candidates present
        # and none rendered is what a BROKEN FILTER looks like from here, and it must fail.
        # Three of the eight checks in this file already did this; five, including this
        # one, printed SKIP instead and would have reported green through a total breakage.
        if SEEN.get('dirmotionblur'):
            raise AssertionError('%d dirmotionblur records found and none rendered' % SEEN['dirmotionblur'])
        print('SKIP test_dirmotionblur_is_an_average: no corpus')
    return


def test_dyngradient_is_a_ramp_lookup():
    """The source's value must INDEX the ramp, not merely pass through it.

    `dyngradient` has no numeric parameters -- which is why containment found zero
    declaring sources and the two-path control found zero programs -- so the only thing to
    verify is the semantics, and it is verifiable exactly because both inputs can be
    driven. Three checks, of which the second is the one with teeth:

        identity ramp, x-ramp source  ->  output reproduces the source
        REVERSED ramp                 ->  output = 1 - source
        step ramp                     ->  exactly two distinct values

    A renderer that ignored the ramp and returned its first input would pass the first
    check and FAIL the second. One that blended rather than looked up would pass both and
    fail the third. The residual tolerance is quantisation: a 256-wide strip indexed by W
    source samples steps by 1/256, so half a step is the floor.
    """
    n = cands = 0
    for path in corpus.paths()[:MAX_FILES]:
        try:
            asm = Assembly(path)
        except Exception:
            continue
        for rec in asm.records:
            if FILTERS.get(rec.filter_id) != 'dyngradient':
                continue
            if len(rec.edges or ()) < 2 or any(e is None for e in rec.edges[:2]):
                continue
            cands += 1
            h = w = 64
            src = np.tile(np.linspace(0.0, 1.0, w, dtype=np.float32),
                          (h, 1)).reshape(h, w, 1)
            ramp = np.zeros((16, 256, 1), dtype=np.float32)
            ramp[:, :, 0] = np.linspace(0.0, 1.0, 256, dtype=np.float32)[None, :]
            for strip, want, label in (
                    (ramp, src[:, :, 0], 'identity'),
                    (ramp[:, ::-1, :].copy(), 1.0 - src[:, :, 0], 'reversed')):
                try:
                    out, _f, _s = R.render(asm, precomputed={rec.edges[0]: src,
                                                             rec.edges[1]: strip},
                                           verbose=False, max_dim=64)
                except Exception:
                    out = {}
                got = out.get(rec.index)
                if got is None:
                    continue
                a = np.asarray(got, dtype=np.float32).reshape(h, w, -1)[:, :, 0]
                assert float(np.abs(a - want).max()) < 0.01, (label, rec.index)
                n += 1
            step = np.zeros((16, 256, 1), dtype=np.float32)
            step[:, 128:, 0] = 1.0
            try:
                out, _f, _s = R.render(asm, precomputed={rec.edges[0]: src,
                                                         rec.edges[1]: step},
                                       verbose=False, max_dim=64)
            except Exception:
                out = {}
            got = out.get(rec.index)
            if got is not None:
                a = np.asarray(got, dtype=np.float32).reshape(-1)
                assert len(np.unique(np.round(a, 4))) <= 2, ('step', rec.index)
            if n >= 6:
                break
        if n >= 6:
            break
    if not n:
        # This check builds its own specimens rather than using `_seeded`, so it counts its
        # own candidates. Without that it had the same hole as four others in this file:
        # `except Exception: out = {}` followed by `if got is None: continue` means a
        # render that RAISES skips the assertions silently, and `if not n` then printed
        # SKIP -- so a totally broken dyngradient reported green rather than failing.
        if cands:
            raise AssertionError('%d dyngradient records found and none rendered' % cands)
        print('SKIP test_dyngradient_is_a_ramp_lookup: no corpus')
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
        # NOT a bare skip. `_seeded` records SEEN['gradient'] = candidates FOUND, separately from
        # how many rendered, precisely so this case can be told apart: candidates present
        # and none rendered is what a BROKEN FILTER looks like from here, and it must fail.
        # Three of the eight checks in this file already did this; five, including this
        # one, printed SKIP instead and would have reported green through a total breakage.
        if SEEN.get('gradient'):
            raise AssertionError('%d gradient records found and none rendered' % SEEN['gradient'])
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


MANIFEST_MISSING_PATHS = 513          # ratchet; see the test below


def _edge_closure(asm, i):
    seen, st = set(), [i]
    while st:
        j = st.pop()
        if j in seen or j >= len(asm.records):
            continue
        seen.add(j)
        for e in (asm.records[j].edges or ()):
            if e is not None:
                st.append(e)
    return seen


BLUR_NODE = re.compile(r'<compFilter>.*?</compFilter>', re.S)
BLUR_INTENSITY = re.compile(
    r'<name v="intensity"/>.*?<constantValueFloat1\s*(?:v="([^"]+)"\s*/>|>\s*<value v="([^"]+)")',
    re.S)


def _blur_slot(nprog):
    """Where `blur` keeps its intensity: after the size block.

    The size is either BAKED as a (w, h) pair in slots 2 and 3, or held by `nprog`
    POINTER slots starting at 2. Either way the intensity is the slot after it.
    """
    return 4 if nprog == 0 else 2 + nprog


def test_blur_intensity_slot_recovers_the_declared_values():
    """The slot rule must find intensities the permitted sources actually declare.

    Reads `.sbs` SOURCES, so the provenance exclusion runs BY CONSTRUCTION: the file list
    is `provenance.audit()`'s permitted set, and excluded sources never enter.

    The CONTROL is the same slot rule applied to records of every OTHER filter in the same
    files. Without it this measures how common small floats are, not where blur keeps a
    parameter -- and blur intensities are values like 1.0, 0.25 and 1.25, which is exactly
    the population `containment.py` has to discard as indistinctive.

    Measured when written: 39 of 54 declared values recovered (72.2%) against 6 (11.1%).
    Four of the fifteen misses are files that compile no blur record at all. Several files
    recover their declared set EXACTLY -- flowingLava 8 of 8, rural_rock_wall 5 of 5 --
    which is the part that is hard to get by luck.
    """
    try:
        import provenance
        import containment
    except Exception:                                       # pragma: no cover
        print('SKIP test_blur_intensity_slot_recovers_the_declared_values: no tools')
        return
    _exc, _flag, permitted = provenance.audit()
    permitted = sorted({q if os.path.isabs(q) else os.path.join(provenance.ROOT, q)
                        for q in permitted})
    declared_n = found_n = control_n = 0
    for q in permitted:
        if not os.path.exists(q):
            continue
        try:
            txt = open(q, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        decl = set()
        for body in BLUR_NODE.findall(txt):
            if '<filter v="blur"/>' not in body:
                continue
            for a, b in BLUR_INTENSITY.findall(body):
                decl.add(round(float(a or b), 4))
        asmf = containment.sbsasm_for(q)
        if not decl or not asmf:
            continue
        try:
            asm = Assembly(asmf)
        except Exception:
            continue
        pool, ctrl = set(), set()
        for rec in asm.records:
            slot = _blur_slot(bin(rec.cls & 0x2881).count('1'))
            if slot >= len(rec.words):
                continue
            v = round(float(np.frombuffer(np.uint32(rec.words[slot]).tobytes(),
                                          dtype=np.float32)[0]), 4)
            (pool if rec.filter_name == 'blur' else ctrl).add(v)
        declared_n += len(decl)
        found_n += len(decl & pool)
        control_n += len(decl & ctrl)
    if not declared_n:
        print('SKIP test_blur_intensity_slot_recovers_the_declared_values: no sources')
        return
    print('blur intensity slot: recovered %d of %d declared (%.1f%%), control %d (%.1f%%)'
          % (found_n, declared_n, 100 * found_n / declared_n,
             control_n, 100 * control_n / declared_n))
    # Both halves. A high recovery rate means nothing if the control matches it, and the
    # floor catches the parse silently finding no declarations at all.
    assert declared_n >= 30, 'only %d declared values found; the source parse has moved' % declared_n
    assert found_n >= 0.55 * declared_n, 'recovery fell to %d of %d' % (found_n, declared_n)
    assert control_n < 0.5 * found_n, \
        'control %d is too close to the signal %d -- the slot is not discriminating' % (
            control_n, found_n)


def test_closure_never_claims_a_dependency_the_manifest_denies():
    """The manifest's `alteroutputs` as an independent check on the edge walk.

    Everything else in this project that reasons about which records feed an output is
    derived from `Record.edges`, so nothing derived from edges can check it. The manifest
    states the dependency separately, which makes it the only oracle available.

    TWO DIFFERENT ASSERTIONS, because the two directions are not equally established:

      * HARD INVARIANT -- our closure must never claim a dependency the manifest denies.
        Measured over the full corpus, type-5 image inputs, 10,837 (output, input) pairs:
        ZERO violations. Over-claiming would mean the edge walk invents reachability, and
        every closure-derived figure would be inflated.

      * RATCHET -- the manifest claims 513 dependencies our closure does NOT find, and
        that is a real gap, not noise: 622 agree, 513 are missed, and 0 go the other way.
        Perfect one-sidedness says our walk is a strict SUBSET rather than merely
        different. Asserting 0 here would fail today, so this asserts the count cannot get
        WORSE -- an improvement to the walk lowers the number and should lower the
        constant with it.

    The likely missing mechanism: FX-Map and pixelprocessor programs reach images through
    sampler indices, not through edges, and an edge walk cannot follow those.

    Restricted to type-5 image inputs ON PURPOSE. A numeric input reaches an output via
    `inputref` inside a program, which the edge graph does not model, so running this on
    type 0 or 4 would report huge disagreement that measures only that absence.

    Costs no rendering -- edges, bitmap kinds and the .xml are all static -- so unlike the
    filter checks this one can afford the whole corpus.
    """
    agree = missed = over = 0
    checked = files = 0
    offenders = []
    for path in corpus.paths():
        try:
            asm = Assembly(path)
            table = asm.outputs()
        except Exception:
            continue
        if not table or not manifest.path_for(asm):
            continue
        files += 1
        uid2idx = {u: i for u, _f, _c, i in table}
        gi = {}
        for r in asm.records:
            if r.filter_name == 'bitmap' and (r.bitmap or {}).get('kind') == 'graph_input':
                gi.setdefault(r.bitmap['uid'], []).append(r.index)
        if not gi:
            continue
        cl = {u: _edge_closure(asm, i) for u, i in uid2idx.items()}
        for uid, (typ, ident, claimed) in manifest.alter_outputs(asm).items():
            if typ != 5 or uid not in gi:
                continue
            recs = set(gi[uid])
            for ouid in uid2idx:
                ours = bool(cl[ouid] & recs)
                man = ouid in claimed
                checked += 1
                if ours and man:
                    agree += 1
                elif man:
                    missed += 1
                elif ours:
                    over += 1
                    if len(offenders) < 5:
                        offenders.append((os.path.basename(path), ident, ouid))
    if not files:
        print('SKIP test_closure_never_claims_a_dependency_the_manifest_denies: no corpus')
        return
    assert checked, ('manifests and outputs present but no type-5 pair was compared', files)
    assert not over, ('edge closure claims %d dependencies the manifest denies; '
                      'the walk invents reachability. first: %s' % (over, offenders))
    assert missed <= MANIFEST_MISSING_PATHS, (
        'closure now misses %d manifest dependencies, worse than the recorded %d'
        % (missed, MANIFEST_MISSING_PATHS))
    return


# Pairings this test found when it was written. A floor, not a target: the check is
# worthless if the pairing procedure quietly stops matching anything, and a suite that
# silently measures nothing looks exactly like a passing one.
#
# It was 12 while the test paired each source against whatever `.sbsasm` a recursive glob
# returned first -- an unrelated package's binary, so those 12 were coincidental float
# matches ACROSS packages. Pairing each source with its own binary takes it to 61.
BLENDMODE_PAIRINGS = 55

_SBS_NODE = re.compile(r'<compNode>((?:(?!</compNode>).)*?)</compNode>', re.S)


def _distinctive(text):
    """A float literal specific enough to identify one node. containment.py's rule.

    Round numbers -- 0, 0.5, 0.25, 1.0 -- occur in every filter of every file and pair
    nothing with anything; five significant decimals do.
    """
    m = re.match(r'^-?\d+\.(\d+)$', text)
    return bool(m) and len(m.group(1).rstrip('0')) >= 5


def _source_blends(path):
    """[(opacitymult, blendingmode or None)] for every blend node the .sbs declares."""
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return []
    out = []
    for body in _SBS_NODE.findall(text):
        if '<filter v="blend"/>' not in body:
            continue
        mode = re.search(r'<name v="blendingmode"/>.*?<constantValueInt32 v="(-?\d+)"/>',
                         body, re.S)
        opac = re.search(r'<name v="opacitymult"/>.*?<constantValueFloat1 v="([-\d.e]+)"/>',
                         body, re.S)
        if not opac or not _distinctive(opac.group(1)):
            continue
        out.append((float(opac.group(1)), int(mode.group(1)) if mode else None))
    return out


def test_blendingmode_matches_the_source_that_declares_it():
    """The low nibble of blend slot 1 IS `blendingmode`, node by node.

    What was already established is a POSITIONAL claim: FORMAT-NOTES.md's corpus-wide
    falsification test says no other bit field of slot 1 can be the mode, over 382
    specimens. That rules out the alternatives; it does not check a single record against
    a source that names the answer. This does, and it is the same containment argument
    `containment.py` makes for filter identity, applied to a parameter.

    THE PAIRING IS THE WHOLE TEST. A blend node in the `.sbs` carries an `opacitymult`
    float; the compiled record carries the same float in one of its words. Where that
    float has five significant decimals, occurs ONCE in the source, and lands in compiled
    blend records that all agree on their mode, the two are the same node and the modes
    must match. Everything ambiguous is dropped rather than guessed -- an ambiguous
    pairing is not weak evidence, it is none.

    WHY NOT COUNT-MATCHING, which would be simpler: every paired source in the corpus is
    instanced -- 0 of 71 have zero `compInstance`, and 0 of 71 have as many blend nodes as
    their binary has blend records -- so a multiset comparison is comparing a top-level
    graph against itself plus every subgraph it instantiates. The per-node pairing is
    what survives instancing.

    WHAT IT FOUND, over 13 sources paired with their own binaries: 61 unambiguous
    pairings, 55 where the source declares a mode and the decode agrees with it, 0
    disagreements, and 6 where the source declares NO blendingmode at all and the decode
    reads 0 -- independent evidence that `copy` is the parameter's default, a fact the
    renderer relies on and had no direct support for.

    THOSE NUMBERS WERE 10 / 0 / 2 UNTIL THE PAIRING WAS FIXED, and the old ones were not
    just fewer, they were meaningless: the sources sit flat in `pairs2/` while the binaries
    sit in sibling `x_NAME/` directories, so a recursive glob from the source's directory
    returned all 95 assemblies in the collection and `[0]` took whichever sorted first.
    Every match was a coincidence between two unrelated packages. The conclusion survived
    the correction, which is luck rather than method -- see `provenance.own_assembly`.

    IT DOES NOT COVER EVERY MODE. Modes 0, 2, 3 and 9 are pinned here; 1, 4, 5, 6, 7, 8,
    10 and 11 are not, because no source in this corpus declares them on a node with a
    distinctive opacity. That gap is the point of reporting the modes covered rather than
    a bare pass.
    """
    agree = differ = default_zero = 0
    offenders = []
    sources = 0
    for path in provenance.paired_sources():
        if provenance.matches(path, provenance.EXCLUDED_AUTHORS):
            continue
        declared = _source_blends(path)
        if not declared:
            continue
        seen = collections.Counter(v for v, _m in declared)
        declared = [(v, m) for v, m in declared if seen[v] == 1]
        if not declared:
            continue
        # ITS OWN BINARY, not whatever the glob returned first. The sources sit flat and
        # the binaries sit in sibling `x_NAME/` directories, so a recursive glob from the
        # source's directory returns EVERY assembly in the collection -- 95 of them for
        # `pairs2/` -- and `[0]` is whichever package sorts first. This test used to do
        # that, so its pairings were coincidental float matches ACROSS packages.
        own = provenance.own_assembly(path)
        if not own:
            continue
        try:
            asm = Assembly(own)
        except Exception:
            continue
        sources += 1
        by_value = collections.defaultdict(list)
        for rec in asm.records:
            if rec.filter_name != 'blend' or not rec.slot1_flags:
                continue
            mode = rec.slot1_flags.get('blendingmode')
            for word in rec.words:
                f = struct.unpack('<f', struct.pack('<I', int(word) & 0xFFFFFFFF))[0]
                if np.isfinite(f) and 0.0 < f < 1.0:
                    by_value[round(f, 6)].append(mode)
        for value, mode in declared:
            hits = by_value.get(round(value, 6))
            if not hits or len(set(hits)) != 1:
                continue
            if mode is None:
                default_zero += 1 if hits[0] == 0 else 0
                if hits[0] != 0:
                    offenders.append((os.path.basename(path), value, 'default', hits[0]))
                    differ += 1
            elif mode == hits[0]:
                agree += 1
            else:
                differ += 1
                offenders.append((os.path.basename(path), value, mode, hits[0]))
    if not sources:
        print('SKIP test_blendingmode_matches_the_source_that_declares_it: no paired sources')
        return
    assert not differ, ('blend slot 1 decodes a mode the source contradicts, %d times; '
                        'first: %s' % (differ, offenders[:5]))
    assert agree + default_zero >= BLENDMODE_PAIRINGS, (
        'only %d pairings (%d declared, %d default) -- fewer than the recorded %d, so the '
        'pairing procedure has stopped finding evidence rather than passing'
        % (agree + default_zero, agree, default_zero, BLENDMODE_PAIRINGS))
    return


# Parameter pairings the all-filter containment finds today. A floor, as above.
ALL_PARAM_PAIRINGS = 140

_SBS_PARAM_BLOCK = re.compile(r'<parameter>((?:(?!</parameter>).)*?)</parameter>', re.S)
_SBS_PARAM_NAME = re.compile(r'<name v="([a-z0-9]+)"/>')
_SBS_PARAM_VALUE = re.compile(r'<constantValue(?:Float1|Float4) v="([-\d.e ]+)"/>')
_SBS_FILTER = re.compile(r'<filter v="([a-z0-9]+)"/>')


def test_no_filter_parameter_is_named_differently_from_its_source():
    """Across EVERY filter, not just the one being worked on.

    `Record.named_parameters` is what the render branches read their constants from, and a
    wrong name there is a different picture rather than an error. The levels check above
    covers five parameters of one filter; this covers whatever the corpus declares.

    Over the permitted paired sources, each with its OWN binary, taking any Float1 or Float4
    parameter declared with five or more significant decimals and unique in its source, and
    landing in exactly one record of that filter:

        named the same as the source   147
        MIS-NAMED                        0
        not named by us at all         103

    The 103 are not failures. Most are parameters other code paths read -- `uniform`'s
    outputcolor comes from the slot after the size expression, `transformation`'s matrix22
    from `Record.matrix`, `warp`'s intensity from the program-or-slot logic -- so
    `named_parameters` not surfacing them says nothing about whether they are read
    correctly. What this asserts is the sharp half: where we DO name a value, we have never
    named it something the source calls something else.

    ONE PARAMETER BLOCK AT A TIME. A first version matched `<name v="...">` and the next
    `<constantValue...>` with a non-greedy span, which crosses `</parameter>` boundaries and
    pairs a name with the FOLLOWING parameter's value. It reported `blendingmode` as
    mis-named 10 times -- blendingmode's own value is an Int32, so the match ran on to the
    neighbouring `opacitymult` float. Every one of those was the regex, not the decode. It
    is the same trap `manifest.output_channels` records for `<channel names=...>`, and it
    produces confident wrong readings in exactly the direction that looks like a finding.
    """
    try:
        own_assembly = provenance.own_assembly
    except AttributeError:
        print('SKIP test_no_filter_parameter_is_named_differently_from_its_source: no pairing')
        return
    by_name = {v: k for k, v in FILTERS.items()}
    by_name['grayscaleconversion'] = 3
    agreed = 0
    wrong = []
    for path in provenance.paired_sources():
        if provenance.matches(path, provenance.EXCLUDED_AUTHORS):
            continue
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        declared = []
        for body in _SBS_NODE.findall(text):
            f = _SBS_FILTER.search(body)
            if not f or f.group(1) not in by_name:
                continue
            for block in _SBS_PARAM_BLOCK.findall(body):
                n = _SBS_PARAM_NAME.search(block)
                v = _SBS_PARAM_VALUE.search(block)
                if not n or not v:
                    continue
                first = v.group(1).split()[0]
                if _distinctive(first):
                    declared.append((by_name[f.group(1)], n.group(1), float(first)))
        if not declared:
            continue
        own = own_assembly(path)
        if not own:
            continue
        try:
            asm = Assembly(own)
        except Exception:
            continue
        once = collections.Counter(v for _f, _p, v in declared)
        by_id = collections.defaultdict(list)
        for rec in asm.records:
            by_id[rec.filter_id].append(rec)
        for fid, param, value in declared:
            if once[value] != 1:
                continue
            holders = [r for r in by_id.get(fid, []) for w in r.words
                       if abs(struct.unpack('<f', struct.pack('<I', int(w) & 0xFFFFFFFF))[0]
                              - value) < 1e-6]
            if len(holders) != 1:
                continue
            baked = {n: v for n, kind, v in holders[0].named_parameters if kind == 'baked'}
            ours = [n for n, v in baked.items() if abs(float(v) - value) < 1e-6]
            if ours == [param]:
                agreed += 1
            elif ours:
                wrong.append((os.path.basename(path), fid, param, value, ours))
    if not agreed and not wrong:
        print('SKIP test_no_filter_parameter_is_named_differently_from_its_source: no pairings')
        return
    assert not wrong, ('a parameter is named differently from the source that declares it: '
                       '%s' % (wrong[:5],))
    assert agreed >= ALL_PARAM_PAIRINGS, (
        'only %d parameters located, fewer than the recorded %d' % (agreed, ALL_PARAM_PAIRINGS))
    return


# Levels parameter pairings this containment finds today. A floor, as above.
LEVELS_PAIRINGS = 80

_LEVEL_PARAMS = ('levelinlow', 'levelinmid', 'levelinhigh', 'leveloutlow', 'levelouthigh')


def test_levels_parameters_are_named_the_way_the_sources_name_them():
    """`levels` has five parameters and this is the first check that we call them right.

    They decide what every levels record does to its input, and a mis-named one is not a
    crash -- it is a different picture. The mapping had never been put to a source.

    Over the permitted paired sources, each paired with its OWN binary: a parameter counts
    when the source declares it with five or more significant decimals and declares that
    value exactly once, and when exactly one filter-15 record in that binary contains it.
    Then `Record.named_parameters` is asked what it calls the value:

        levelinlow    18 named correctly, 1 unnamed
        levelinmid    16 named correctly, 2 unnamed
        levelinhigh   18 named correctly, 1 unnamed
        leveloutlow   15 named correctly, 0 unnamed
        levelouthigh  19 named correctly, 0 unnamed

    86 agreements and ZERO mis-namings. The four residual cases are records where
    `named_parameters` returns nothing at all -- a coverage gap, not a wrong name, and the
    distinction is why this asserts on mis-namings rather than on the total.

    THE VALUES ARE DECLARED AS Float4, not Float1 -- 177 `levelinhigh` declarations against
    19 -- with the same number repeated across RGB and an alpha of 0 or 1. A first attempt
    read only the Float1 form and found a single pairing, which is the shape of a search
    looking in the wrong place rather than of a decode that does not hold.
    """
    try:
        own_assembly = provenance.own_assembly
    except AttributeError:
        print('SKIP test_levels_parameters_are_named_the_way_the_sources_name_them: no pairing')
        return
    named = collections.Counter()
    wrong = []
    for path in provenance.paired_sources():
        if provenance.matches(path, provenance.EXCLUDED_AUTHORS):
            continue
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        declared = []
        for body in _SBS_NODE.findall(text):
            if '<filter v="levels"/>' not in body:
                continue
            for name in _LEVEL_PARAMS:
                m = re.search(r'<name v="%s"/>.*?<constantValueFloat4 v="([-\d.e ]+)"/>' % name,
                              body, re.S)
                if not m:
                    continue
                first = m.group(1).split()[0]
                if _distinctive(first):
                    declared.append((name, float(first)))
        if not declared:
            continue
        own = own_assembly(path)
        if not own:
            continue
        try:
            asm = Assembly(own)
        except Exception:
            continue
        recs = [r for r in asm.records if r.filter_id == 15]
        if not recs:
            continue
        once = collections.Counter(v for _n, v in declared)
        for name, value in declared:
            if once[value] != 1:
                continue
            holders = [r for r in recs for w in r.words
                       if abs(struct.unpack('<f', struct.pack('<I', int(w) & 0xFFFFFFFF))[0]
                              - value) < 1e-6]
            if len(holders) != 1:
                continue
            baked = {n: v for n, kind, v in holders[0].named_parameters if kind == 'baked'}
            ours = [n for n, v in baked.items() if abs(float(v) - value) < 1e-6]
            if ours == [name]:
                named[name] += 1
            elif ours:
                wrong.append((os.path.basename(path), name, value, ours))
    total = sum(named.values())
    if not total:
        print('SKIP test_levels_parameters_are_named_the_way_the_sources_name_them: no pairings')
        return
    assert not wrong, ('a levels parameter is named differently from the source that '
                       'declares it: %s' % (wrong[:5],))
    assert total >= LEVELS_PAIRINGS, (
        'only %d parameters located, fewer than the recorded %d -- the containment has '
        'stopped finding evidence rather than passing' % (total, LEVELS_PAIRINGS))
    return


#: `levels` nodes the walk's placement recovers whole, across every permitted paired
#: source. A floor. The memo recovered 69 of the same 93 when it was retired.
LEVELS_NODES_RECOVERED = 82


def _levels_declared(path):
    """[{name: ('const', v) | ('dynamic', None)}] for each `levels` node in a source.

    The first component of a FloatN, because `levels` writes every parameter as
    `constantValueFloat4` -- the scalar repeated across RGB with an alpha. Reading only
    the Float1 form is what made this filter look unpairable for so long.
    """
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return []
    out = []
    for body in _SBS_NODE.findall(text):
        if '<filter v="levels"/>' not in body:
            continue
        got = {}
        for name in _LEVEL_PARAMS:
            m = re.search(r'<name v="%s"/><relativeTo v="\d+"/><paramValue>'
                          r'(?:<constantValueFloat\d v="([-\d.e ]+)"/>|(<dynamicValue>))'
                          % name, body)
            if not m:
                continue
            got[name] = (('const', float(m.group(1).split()[0])) if m.group(1)
                         else ('dynamic', None))
        if got:
            out.append(got)
    return out


def _max_matching(edges, n_left):
    """Kuhn's algorithm. A declared node may claim at most ONE record, and vice versa."""
    match = {}

    def aug(u, seen):
        for v in edges.get(u, ()):
            if v in seen:
                continue
            seen.add(v)
            if v not in match or aug(match[v], seen):
                match[v] = u
                return True
        return False

    return sum(1 for u in range(n_left) if aug(u, set()))


def test_levels_placement_is_the_one_the_sources_confirm():
    """The arbiter that retired the `LAYOUTS` memo for `levels`, as a standing check.

    `test_levels_parameters_are_named_the_way_the_sources_name_them` above asks whether a
    located value is called the right thing. This asks the harder question the routing
    turned on: given a declared node, does the reading reproduce that node's WHOLE
    parameter set at the values it states? A placement that is one slot out still names
    things correctly on the records where nothing shifted, and fails here.

    A declared node matches a record when the SET of level parameters agrees exactly and
    every stated constant is within 2e-4 of the value read at its slot (a stated
    `dynamicValue` must read as a program). The pairing is a maximum bipartite matching so
    one node cannot claim two records and inflate the count.

    When this was measured, over 21 permitted paired sources and 93 declared nodes:

        the walk (`WALKED_PARAMS`)          82
        the LAYOUTS memo (`_parameters_paired`)   69, ahead on 0 of the 21 files

    The memo's misses are not near-misses. `ChesterfieldSofa` record 348 is a colour
    `levels` whose source states `levelinhigh` 0.593045; the walk reads it at slot 8, four
    words after `levelinlow`, and the memo reads 0.264098 at slot 5 -- a duplicate of
    `levelinlow`, because it charges a colour parameter one word instead of four.

    THIS IS NOT CIRCULAR and that is the point of it: the values come from the packages'
    own `.sbs`, which no part of the decode reads.
    """
    from sbsasm import PARAM_SPEC, WALKED_PARAMS
    if 15 not in WALKED_PARAMS:
        # Not a skip: the routing having been reverted is exactly what this catches.
        assert False, ('`levels` is back on the LAYOUTS memo. It recovered 69 of 93 '
                       'source-declared nodes there against the walk\'s 82 -- see '
                       'FORMAT-NOTES "`levels` goes on the walk"')
    spec = PARAM_SPEC[15]
    seen = collections.Counter()
    behind = []
    for path in provenance.paired_sources():
        if provenance.matches(path, provenance.EXCLUDED_AUTHORS):
            continue
        nodes = _levels_declared(path)
        own = provenance.own_assembly(path) if nodes else None
        if not own:
            continue
        try:
            recs = [r for r in Assembly(own).records if r.filter_id == 15]
        except Exception:
            continue
        if not recs:
            continue
        got = {}
        for which in ('walk', 'memo'):
            reads = []
            for r in recs:
                try:
                    read = (r.named_parameters if which == 'walk'
                            else r._parameters_paired(spec))
                except Exception:
                    read = []
                reads.append({n: (k, v) for n, k, v in read})
            edges = {}
            for i, decl in enumerate(nodes):
                edges[i] = [j for j, rd in enumerate(reads)
                            if set(rd) == set(decl)
                            and all((rd[n][0] == 'program') if kind == 'dynamic'
                                    else (rd[n][0] == 'baked'
                                          and abs(float(rd[n][1]) - v) <= 2e-4)
                                    for n, (kind, v) in decl.items())]
            got[which] = _max_matching(edges, len(nodes))
        seen['nodes'] += len(nodes)
        seen['walk'] += got['walk']
        seen['memo'] += got['memo']
        if got['memo'] > got['walk']:
            behind.append((os.path.basename(path), got['walk'], got['memo']))
    if not seen['nodes']:
        print('SKIP test_levels_placement_is_the_one_the_sources_confirm: no pairings')
        return
    assert not behind, ('the memo recovers MORE source-declared levels nodes than the walk '
                        'on %s -- that was true on 0 of 21 files when levels was routed' %
                        (behind,))
    assert seen['walk'] >= LEVELS_NODES_RECOVERED, (
        'the walk recovers %d of %d declared levels nodes, below the recorded %d'
        % (seen['walk'], seen['nodes'], LEVELS_NODES_RECOVERED))
    print('ok  test_levels_placement_is_the_one_the_sources_confirm '
          '(%d of %d nodes, memo %d)' % (seen['walk'], seen['nodes'], seen['memo']))
    return


# Colour pairings this containment finds today. A floor, for the same reason
# BLENDMODE_PAIRINGS has one.
UNIFORM_COLOUR_PAIRINGS = 150

_OUTPUTCOLOR = re.compile(
    r'<name v="outputcolor"/>.*?<constantValueFloat4 v="([-\d.e ]+)"/>', re.S)


def test_uniform_colour_sits_where_the_source_says_it_does():
    """`uniform`'s fill colour, against the sources that declare it.

    render.py reads the fill from the words after the size-expression slot, and cited as
    evidence "exact containment against a real paired source, DLG-Tools__US_Flag.sbs -- four
    DISTINCT declared outputcolor values". That check was run with the broken pairing (see
    `provenance.own_assembly`), so it compared US_Flag's declarations against a different
    package's binary and its four matches were coincidences.

    Re-run with each source paired to its own binary, the reading holds far more broadly
    than the claim it was resting on:

        distinctive declared colours          200
          found in the source's own binary    182
            at slot 2                         181
            at slot 7                           1
          not found                            18

    A colour is counted only if it is DISTINCTIVE -- every component 0 or 1 discriminates
    nothing, since black, white and opaque alpha occur in every file -- and only if the
    source declares it once, so it can identify a single record.

    The 18 misses are not counter-examples to the slot; they are colours the binary does not
    contain at all, which a node feeding an instanced subgraph would produce. What would
    falsify the reading is a colour found at some OTHER slot, and there is one, at 7.
    """
    try:
        own_assembly = provenance.own_assembly
    except AttributeError:
        print('SKIP test_uniform_colour_sits_where_the_source_says_it_does: no pairing helper')
        return
    found = collections.Counter()
    slots = collections.Counter()
    sources = 0
    for path in provenance.paired_sources():
        if provenance.matches(path, provenance.EXCLUDED_AUTHORS):
            continue
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        declared = []
        for body in _SBS_NODE.findall(text):
            if '<filter v="uniform"/>' not in body:
                continue
            m = _OUTPUTCOLOR.search(body)
            if m:
                declared.append(tuple(float(x) for x in m.group(1).split()))
        if not declared:
            continue
        own = own_assembly(path)
        if not own:
            continue
        try:
            asm = Assembly(own)
        except Exception:
            continue
        recs = [r for r in asm.records if r.filter_id == 6]
        if not recs:
            continue
        sources += 1
        once = collections.Counter(declared)
        for colour in declared:
            if once[colour] != 1 or len(colour) != 4:
                continue
            if all(abs(x) < 1e-9 or abs(x - 1.0) < 1e-9 for x in colour):
                continue                      # round values discriminate nothing
            at = None
            for rec in recs:
                for k in range(len(rec.words) - 3):
                    w = np.frombuffer(np.array(rec.words[k:k + 4], dtype=np.uint32).tobytes(),
                                      dtype='<f4')
                    if all(abs(float(w[j]) - colour[j]) < 1e-5 for j in range(4)):
                        at = k
                        break
                if at is not None:
                    break
            if at is None:
                found['missing'] += 1
            else:
                found['found'] += 1
                slots[at] += 1
    if not sources:
        print('SKIP test_uniform_colour_sits_where_the_source_says_it_does: no paired sources')
        return
    assert found['found'] >= UNIFORM_COLOUR_PAIRINGS, (
        'only %d colours located, fewer than the recorded %d -- the containment has stopped '
        'finding evidence rather than passing' % (found['found'], UNIFORM_COLOUR_PAIRINGS))
    top = slots.most_common(1)[0]
    assert top[0] == 2 and top[1] >= 0.9 * found['found'], (
        'the fill colour no longer sits predominantly at slot 2: %s' % (slots.most_common(4),))
    return


# The agreement each reference-scored channel reaches today, as a FLOOR. Not a target:
# these are correlations against the engine's own exported maps, and the point is that a
# change cannot quietly take one away. Set a little under the measured value so ordinary
# float noise does not trip it; a real collapse is orders of magnitude, not percent.
#: RATCHETED UP after `fx.gridcount` became the default -- see FORMAT-NOTES, "the tufting
#: lattice". The old floors are kept in the comment beside each so the size of that move
#: stays legible, and so nobody re-derives them downward by accident.
REFERENCE_FLOOR = {
    ('Kutejnikov__Auras', 'basecolor', 0): 0.90,            # unchanged, now 0.937
    ('Kutejnikov__Auras', 'basecolor', 1): 0.82,            # unchanged, now 0.865
    ('Kutejnikov__Auras', 'basecolor', 2): 0.91,            # unchanged, now 0.945
    ('Kutejnikov__Bricks_and_tiles', 'emission', 0): 0.88,  # was 0.40, now 0.916-0.940
    ('Kutejnikov__Bricks_and_tiles', 'emission', 1): 0.95,  # was 0.42, now 0.978-0.986
    ('Kutejnikov__Bricks_and_tiles', 'emission', 2): 0.95,  # was 0.42, now 0.981-0.985
    ('minime453__Chesterfield_PBR_Material', 'roughness', 0): 0.90,   # was 0.26 / 0.80, now 0.930
    ('minime453__Chesterfield_PBR_Material', 'metallic', 0): 0.90,    # was 0.29, now 0.952
    # NEW ENTRIES. These channels only became worth ratcheting once the lattice appeared --
    # before it they sat at or below 0.17 and two of them were NEGATIVE.
    ('minime453__Chesterfield_PBR_Material', 'height', 0): 0.90,      # was -0.002, now 0.949
    ('minime453__Chesterfield_PBR_Material', 'normal', 0): 0.86,      # was -0.007, now 0.916
    ('minime453__Chesterfield_PBR_Material', 'normal', 1): 0.86,      # was +0.002, now 0.916
    ('minime453__Chesterfield_PBR_Material', 'AO', 0): 0.82,          # was -0.038, now 0.875
    # CHESTERFIELD BASECOLOR: LOWERED, WHICH IS THE ONE MOVE THIS TABLE IS NOT SUPPOSED TO
    # MAKE, so the reason is here rather than in a commit message. Routing `levels` through
    # the structural walk (`sbsasm.WALKED_PARAMS`) takes these three channels from
    # +0.6281 / +0.9636 / +0.8224 to +0.5985 / +0.6544 / -0.7216.
    #
    # The old numbers were not an agreement. Walking everything but forcing records 129,
    # 146 and 226 to a CONSTANT 1.0 image reproduces them to four decimals -- and those
    # three records only emit a constant under the memo because it reads their INPUT EDGE
    # as a `levelinhigh` of 0.0. Four legitimate readings of the same records (invert,
    # identity, 1-x, constant 0.5) agree with each other to 0.002 on every channel and all
    # four give the numbers below, so the record's own parameters cannot produce the old
    # score under any placement. At `max_dim` 256 the memo's reading takes record 330's
    # pixelprocessor 100% non-finite and this output does not render at all, while the walk
    # renders it at +0.7149 / +0.8536 / -0.8500. See `sbsasm.Record._parameters_walked`.
    #
    # ch2 IS NEW AND IS NEGATIVE, listed for the first assertion. It is the one thing the
    # routing genuinely costs on the pixels, and leaving it unwatched is the exposure the
    # Bricks entries below were added for.
    #
    # RATCHETED UP AGAIN by the FX handoff -- see FORMAT-NOTES, "The FX handoff runs both
    # ways". A table run that ends on a node header now hands back to the chain instead of
    # stopping the walk, which changes ONE `fxmaps` record in this package (and two in
    # `StylizedCobblestoneStreet`, which carries no floor). Measured same-moment against a
    # pinned copy of the previous `sbsasm.py`, everything else in the tree held:
    #
    #     basecolor 0   +0.5985 -> +0.7497        roughness 0   +0.8956 -> +0.9299
    #     basecolor 1   +0.6544 -> +0.7662        every other listed channel identical
    #     basecolor 2   -0.7216 -> -0.6773
    #
    # ch2 is still anti-correlated and its floor still reads as a lower bound on a negative
    # number: -0.70 says "do not get MORE inverted than this". The fault is the nine mode-7
    # switch blends in its colour chain, which this does not touch; it is less wrong, not
    # right.
    ('minime453__Chesterfield_PBR_Material', 'basecolor', 0): 0.72,   # was 0.60 / 0.55, now 0.7497
    ('minime453__Chesterfield_PBR_Material', 'basecolor', 1): 0.74,   # was 0.72 / 0.60, now 0.7662
    ('minime453__Chesterfield_PBR_Material', 'basecolor', 2): -0.70,  # was -0.78, now -0.6773
    # BRICKS BASECOLOR IS ANTI-CORRELATED AND LISTED ANYWAY. These three sit at -0.70,
    # -0.69 and -0.65: the render is not merely poor, it is inverted against the engine's
    # own export. They are here for the FIRST assertion, not the second. Nothing was
    # watching this output -- only Bricks' `emission` was listed -- and it is the output
    # that moves most when `levels` routing changes (walking `levels` takes ch0 from -0.70
    # to +0.40 and ch1 from -0.69 to +0.50, a sign flip on two of three channels that no
    # floor would have reported either way). An unwatched channel that swings by 1.1 is
    # exactly the b2f1d97 exposure this test exists for.
    #
    # READ THE CORRELATION FLOOR AS A COLLAPSE GUARD AND NOTHING MORE. `compare_pack`
    # yields Bricks basecolor SIX times -- the package ships two .sbsar and several graphs,
    # and `_package_refs`/`graph_dir` do not narrow basecolor to one reference the way they
    # do for `emission` (yielded twice, +0.9951 and +0.9805, a 0.015 spread). The SAME
    # render, identified by its sd of 0.06615, scores -0.0195 against one reference and
    # -0.7014 against another: a 0.68 spread on identical pixels. The dict keeps the last
    # row, which is deterministic at a given commit (sorted assemblies, fixed output
    # order), so these floors do not flake -- but the NUMBER is a property of the pairing,
    # not of the render, and ratcheting it upward later would be reading noise. What earns
    # its place is that a constant basecolor now fails, and a basecolor that stops
    # rendering now fails.
    # THESE THREE ARE NOW POSITIVE and the floors are deliberately NOT ratcheted to match.
    # With `levels` on the walk they read +0.4270 / +0.5475 / +0.5148 against the -0.0398 /
    # +0.1615 / +0.0324 recorded here, which is the sign flip the note above predicted --
    # but the pairing ambiguity described above is unchanged, so raising these would be
    # ratcheting a property of which reference won rather than of the render.
    ('Kutejnikov__Bricks_and_tiles', 'basecolor', 0): -0.72,   # was -0.7014, now +0.4270
    ('Kutejnikov__Bricks_and_tiles', 'basecolor', 1): -0.71,   # was -0.6901, now +0.5475
    ('Kutejnikov__Bricks_and_tiles', 'basecolor', 2): -0.67,   # was -0.6462, now +0.5148
}


def test_reference_agreement_does_not_regress():
    """The exported maps as a RATCHET, because a sweep cannot see this.

    WHY THIS EXISTS. `b2f1d97` took Auras' graph-004 basecolor -- the best agreement in this
    repository, r = 0.92 / 0.85 / 0.94 against the package's own export -- to a CONSTANT, and
    nothing automated noticed. The corpus sweep could not: 228 of that file's records moved
    and exactly one of its outputs is scoreable. The blocker census could not: the output
    still rendered. It was caught by a human re-running the scorer, four commits later.

    Four sessions commit into this tree. A number that only one of them checks by hand is
    not a check.

    TWO ASSERTIONS, and the first is the sharp one:

      * NOT CONSTANT. Every channel listed below currently has structure, so a per-channel
        std of zero means the render collapsed. That is what the regression did, and it is
        unambiguous -- no threshold to argue about.

      * NOT MUCH WORSE. The recorded floors sit a little under today's values, so float
        noise passes and a collapse does not.

    PER-CHANNEL std, NOT the array's. A 4-channel constant colour has an overall std of
    0.433, which is inter-channel spread -- the same trap refcompare's docstring records for
    normal maps, and the one that made me call the flattened record "varying" while
    diagnosing this.
    """
    try:
        import refcompare
    except Exception:
        print('SKIP test_reference_agreement_does_not_regress: refcompare unavailable')
        return
    packs = refcompare.reference_packs()
    if not packs:
        print('SKIP test_reference_agreement_does_not_regress: no reference packages')
        return
    seen, flat, worse = {}, [], []
    for pack, refs in sorted(packs.items()):
        want = {k for k in REFERENCE_FLOOR if k[0] == pack}
        if not want:
            continue
        for name, chan, ours, ref in refcompare.compare_pack(pack, refs):
            if chan is None or (pack, name, chan) not in REFERENCE_FLOOR:
                continue
            key = (pack, name, chan)
            o, r = ours.ravel(), ref.ravel()
            sd = float(o.std())
            corr = 0.0
            if sd > 1e-9 and r.std() > 1e-9:
                corr = float(np.corrcoef(o, r)[0, 1])
            seen[key] = (sd, corr)
            if sd <= 1e-9:
                flat.append(key)
            elif corr < REFERENCE_FLOOR[key]:
                worse.append((key, round(corr, 4), REFERENCE_FLOOR[key]))
    missing = sorted(set(REFERENCE_FLOOR) - set(seen))
    if not seen:
        print('SKIP test_reference_agreement_does_not_regress: no listed channel scored')
        return
    assert not flat, ('a reference-scored channel renders CONSTANT: %s -- this is the '
                      'shape of the b2f1d97 regression' % (flat,))
    assert not worse, ('reference agreement fell below its recorded floor: %s' % (worse,))
    assert not missing, ('a channel that used to score no longer does: %s. Either an output '
                         'stopped rendering or its pairing broke' % (missing,))
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
               test_gradient_runs_and_stays_bounded,
               test_dyngradient_is_a_ramp_lookup,
               test_closure_never_claims_a_dependency_the_manifest_denies,
               test_blendingmode_matches_the_source_that_declares_it,
               test_reference_agreement_does_not_regress,
               test_uniform_colour_sits_where_the_source_says_it_does,
               test_levels_parameters_are_named_the_way_the_sources_name_them,
               test_levels_placement_is_the_one_the_sources_confirm,
               test_no_filter_parameter_is_named_differently_from_its_source):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        out = buf.getvalue()
        sys.stdout.write(out)
        print('%-46s %s' % (fn.__name__, 'skipped' if 'SKIP' in out else 'ok'))


class _CurveStub(object):
    """The three attributes `Record.curve_chain` reads, so a control can shift one of them."""

    CURVE_MAX_POINTS = 4096

    def __init__(self, filter_id, words, asm):
        self.filter_id, self.words, self.asm = filter_id, words, asm


def test_curve_chain_totals_the_count_the_record_states():
    """A `curve` record's slot 2 is the TOTAL over a chain of tables, not one table's size.

    `curve_points` reads the first table; `Record.curve_chain` walks the chain and stops
    when the counts it has read total the count the RECORD states. The stop is the file's
    word, so the walk cannot run long, and the total is a test it can fail.

    THE POPULATION IS ASSERTED FIRST, and so is the multi-table half of it, because "every
    chain totals slot 2" is vacuously true of an empty corpus and nearly vacuous on one
    where every chain has one table. Corpus-wide: 1,272 records, 1,261 with one table, 10
    with two, 1 with three, and 23 zero filler words between tables in the whole corpus.

    Two controls, both from `curve_points`' own docstring and both re-run here rather than
    quoted: the same walk one word EARLIER resolves on 0 of 1,272 records, and one word
    later on 5. And where `curve_points` answers at all, its knots are this walk's first
    sub-table -- 1,255 of 1,255 -- so the two readers cannot drift apart.
    """
    recs = multi = tables = agree = 0
    early = late = 0
    first_is_curve_points = cp_total = 0
    for p in corpus.paths():
        try:
            a = Assembly(p)
        except Exception:
            continue
        if not any(r.filter_id == 22 for r in a.records):
            continue
        for r in a.records:
            if r.filter_id != 22 or len(r.words) < 4 or r.words[2] <= 0:
                continue
            recs += 1
            ch = r.curve_chain
            if not ch:
                continue
            agree += 1
            tables += len(ch)
            multi += 1 if len(ch) > 1 else 0
            cp = r.curve_points
            if cp is not None:
                cp_total += 1
                if ch[0][0] == r.words[3] + 52 and ch[0][1] == len(cp):
                    first_is_curve_points += 1
            # CONTROLS: the SAME code, given a slot 3 shifted one word. A stand-in with
            # the three attributes `curve_chain` reads, so the control cannot drift from
            # the rule by being a second implementation of it.
            for delta, box in ((-1, 'early'), (1, 'late')):
                w = list(r.words)
                w[3] = w[3] + 4 * delta
                stub = _CurveStub(r.filter_id, w, r.asm)
                if type(r).curve_chain.fget(stub):
                    if box == 'early':
                        early += 1
                    else:
                        late += 1
    assert recs >= 1000, (
        'only %d curve records declaring a count -- the assertions below say nothing '
        'about a population this small; the corpus has 1,272' % recs)
    assert multi >= 5, (
        'only %d multi-table chains -- with one table each, "the chain totals slot 2" is '
        'the same statement `curve_points` already makes; the corpus has 11' % multi)
    assert agree == recs, (
        '%d of %d curve records have no chain totalling the count they state' % (recs - agree, recs))
    assert first_is_curve_points == cp_total, (
        "`curve_points` and the chain's first sub-table disagree on %d of %d records"
        % (cp_total - first_is_curve_points, cp_total))
    assert early == 0 and late <= recs // 100, (
        'the control walk resolves too often: %d one word early, %d one word late, of %d'
        % (early, late, recs))
    print('curve chains: %d records, %d sub-tables, %d multi-table; controls %d early, '
          '%d late; %d of %d agree with curve_points'
          % (recs, tables, multi, early, late, first_is_curve_points, cp_total))
    return


class _VectorStub(object):
    """What `Record._vector_walk` reads, so a control can shift the payload pointer."""

    VECTOR_KINDS = sbsasm.Record.VECTOR_KINDS

    def __init__(self, filter_id, words, asm):
        self.filter_id, self.words, self.asm = filter_id, words, asm


def test_the_vector_payload_states_its_own_end_and_lands_on_slot_2():
    """Filter 5's payload is a self-delimiting chain, and slot 2 is the control for it.

    `Record.vector_parts` walks `[kind][len][len >> 3 vertices]` parts to a zero terminator
    word. Nothing shows it slot 2, so where it stops is a test it can fail: over the records
    where slot 2 is a usable bound -- inside the record, and a pointer rather than the float
    `0x3F800000` -- the terminator must land exactly on it.

    THE POPULATION IS ASSERTED FIRST, in three parts, because each assertion below is
    vacuous without one of them. Corpus-wide: 139 filter-5 records, 57 where slot 2 is a
    usable bound, and 35 whose walk end differs from the embedded length word's end -- the
    only ones on which the walk and the reading it replaced can disagree at all. Without
    that third count "the walk lands on slot 2" is a restatement of `(w + 23) / 2`.

    THE DISCRIMINATING CONTROL is that same 35: the walk's end is a boundary the file states
    on 34 of them and the embedded length word's end on 0. The 35th ends where a `bitmap`
    record names its image, which this test does not reach for and so allows for.

    TWO MUTATIONS, run through a stand-in carrying the attributes the walk reads, so the
    control cannot drift from the rule by being a second implementation of it: start two
    words late and the walk terminates on none, start one word early and it terminates on
    about half and lands on a stated boundary on none.
    """
    recs = bounded = on_slot2 = multi = 0
    walk_stated = emb_stated = 0
    late_term = early_term = early_stated = 0
    for p in corpus.paths():
        try:
            a = Assembly(p)
        except Exception:
            continue
        if not any(r.filter_id == 5 for r in a.records):
            continue
        starts = set()
        for r in a.records:
            if r.filter_id == 5 and r.vector_extent:
                starts.add(r.vector_extent[0])
        for r in a.records:
            if r.filter_id != 5:
                continue
            got = r.vector_extent
            assert got is not None, 'no extent for a filter-5 record in %s' % p
            recs += 1
            off, n = got
            end = off + n
            emb = off + (struct.unpack_from('<2I', a.data, off)[1] + 23) // 2
            e2 = r.words[2] + 52 if len(r.words) > 2 else None

            def stated(x):
                return (e2 is not None and x == e2) or x == r.end or x in starts - {off}

            # `4d2fd5c`'s own population: slot 2 can only bound a payload that lies in
            # the same record it does. 70 records point their payload OUTSIDE their extent
            # while slot 2 stays inside, and slot 2 is not a bound on those.
            if (e2 is not None and r.offset < e2 <= r.end
                    and r.offset <= off < r.end):
                bounded += 1
                on_slot2 += 1 if end == e2 else 0
            if end != emb:
                multi += 1
                walk_stated += 1 if stated(end) else 0
                emb_stated += 1 if stated(emb) else 0
            for delta, box in ((2, 'late'), (-1, 'early')):
                w = list(r.words)
                w[1] = w[1] + 4 * delta
                stub = _VectorStub(r.filter_id, w, r.asm)
                mut = type(r)._vector_walk.fget(stub)
                if mut is None:
                    continue
                if box == 'late':
                    late_term += 1
                else:
                    early_term += 1
                    early_stated += 1 if stated(mut[0]) else 0
    assert recs >= 100, (
        'only %d filter-5 records -- the assertions below say nothing about a population '
        'this small; the corpus has 139' % recs)
    assert bounded >= 40, (
        'only %d records where slot 2 is a usable bound -- "the walk lands on slot 2" is '
        'vacuous without them; the corpus has 57' % bounded)
    assert multi >= 20, (
        'only %d records whose walk end differs from the embedded length word -- on the '
        'rest the walk and the reading it replaced CANNOT disagree, so agreement is not '
        'evidence; the corpus has 35' % multi)
    assert on_slot2 == bounded, (
        'the terminator misses slot 2 on %d of %d records where slot 2 bounds the payload'
        % (bounded - on_slot2, bounded))
    assert walk_stated >= multi - 1, (
        "%d of %d multi-part walk ends land on no boundary the file states" % (multi - walk_stated, multi))
    assert emb_stated == 0, (
        'the embedded length word already landed on a stated boundary %d times of %d, so '
        'the walk is not what is being tested' % (emb_stated, multi))
    assert late_term == 0, (
        'the walk started two words late still terminates on %d records -- terminating is '
        'not evidence' % late_term)
    assert early_stated == 0, (
        'the walk started one word early lands on a stated boundary %d times' % early_stated)
    print('vector payloads: %d records, %d slot-2-bounded and %d land on it, %d multi-part '
          '(%d walk ends stated, %d embedded-length ends stated); mutations %d late-terminate, '
          '%d early-terminate and %d of those land stated'
          % (recs, bounded, on_slot2, multi, walk_stated, emb_stated,
             late_term, early_term, early_stated))
    return


def test_emboss_below_the_version_gate_is_laid_out_and_its_slots_hold():
    """`emboss`'s pre-v5 records used to have NO layout, and the gate was the fit's.

    `derive_costs` keeps them out because a free intercept cannot separate a class bit set
    on every key from the constant, and the legend inherited the exclusion as
    `min_version`. With the intercept pinned they are not contradictory -- no key below
    the gate carries two different observed sizes -- and they are the only records that
    exercise `emboss`' class bits 19/24/25/26/27 and its `w1` bit 5 in grey.

    THE POPULATION IS ASSERTED FIRST -- both that the old gate's records exist and that
    they are the ones that vary -- because "every record lays out" is vacuous if none is
    below the gate. Then the two SPEC 6.3 loud checks, on those records alone: an edge
    slot must hold a BACKWARD record index and a `w1` state-2 slot must resolve a program.
    Neither was used to derive the layout; both are free to fail.
    """
    GATE = 0x50000
    below = laid = edges = edges_ok = state2 = state2_ok = 0
    cls26 = w1_5_grey = 0
    for p in corpus.paths():
        try:
            a = Assembly(p)
        except Exception:
            continue
        if not any(r.filter_id == 8 for r in a.records):
            continue
        ver = a.header.get('version') if isinstance(a.header, dict) else 0
        if ver is None or ver >= GATE:
            continue
        for r in a.records:
            if r.filter_id != 8:
                continue
            below += 1
            d = decompose.decompose(r)
            if d is None or d.get('end') is None:
                continue
            laid += 1
            assert d['end'] <= len(r.words), (
                '%s record %d: header %d words, record only %d'
                % (os.path.basename(p), r.index, d['end'], len(r.words)))
            if (r.words[0] >> 26) & 1:
                cls26 += 1
            w1 = r.words[1] if len(r.words) > 1 else 0
            if not (r.words[0] & 1) and ((w1 >> 5) & 3) == 1:
                w1_5_grey += 1
            for s in d.get('inputs') or ():
                if s < len(r.words):
                    edges += 1
                    edges_ok += 1 if r.words[s] < r.index else 0
            for sh in (1, 3, 5, 7):
                if ((w1 >> sh) & 3) != 2:
                    continue
                pos = None
                for t in (d.get('param_slots') or ()):
                    if t[0] == sh:
                        pos = t[2]
                if pos is None or pos >= len(r.words):
                    continue
                state2 += 1
                q = r.words[pos] + 52
                state2_ok += 1 if (a.body_lo <= q < a.body_hi and a.valid_program(q)) else 0
    assert below >= 100, (
        'only %d emboss records below v5 -- the corpus had 171 when the gate came off' % below)
    assert laid == below, '%d of %d have no layout' % (below - laid, below)
    assert cls26 >= 2 and w1_5_grey >= 1, (
        'the below-gate records no longer exercise the cells the gate was hiding: class '
        'bit 26 on %d records, grey w1 bit 5 baked on %d -- 2 and 13 when this landed'
        % (cls26, w1_5_grey))
    assert edges_ok == edges, (
        '%d of %d edge slots do not hold a backward record index' % (edges - edges_ok, edges))
    assert state2_ok == state2, (
        '%d of %d state-2 slots do not resolve a program' % (state2 - state2_ok, state2))
    print('emboss below v5: %d records, all laid out; %d edges and %d state-2 slots, all '
          'holding; class bit 26 on %d, grey w1 bit 5 baked on %d'
          % (below, edges, state2, cls26, w1_5_grey))
    return
