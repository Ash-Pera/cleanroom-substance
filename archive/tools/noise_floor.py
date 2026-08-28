#!/usr/bin/env python3
"""Measure the render instrument's NOISE FLOOR: how much it moves when nothing does.

    python3 tools/noise_floor.py [--dim N] [--packs N]

WHY THIS EXISTS. "The scored channels moved by at most 0.0014" is a conclusion only if the
instrument's own reproducibility is known to be below 0.0014, and it never has been. Three
independent ways to get a wrong number out of `refcompare` were found in one day -- module-level
`sbsruntime.SAMPLERS` carrying state between files in a process, `warp.reference_px`, and a
load artifact where two byte-identical runs disagreed with a stale baseline. None of them is
a bug in a decode; all of them move rendered pixels. Until the floor is measured, every "no
movement" verdict in this project is uncalibrated, including `235b831`'s refcompare-identical
claim and the fxmaps arm sweep's 0.0014.

THE NULL IS EXACT, NOT ARGUED. Every arm below renders THE SAME FILE with THE SAME CODE, so
the true delta is zero by construction. That is deliberately stronger than "a change that
cannot affect this file": that form needs an argument about the change's reach, and an
argument is what a floor measurement must not depend on. Anything this reports is instrument
noise with no interpretation step in between.

THE ARMS, each varying only something that must not matter:

    same-process, no clear      render X, render X again in one process
                                -> this is the SAMPLERS leak, measured
    same-process, with clear    the same, with sbsruntime.SAMPLERS cleared between
                                -> does clearing actually fix it?
    after-other, no clear       render Y, then X -- versus X alone
                                -> cross-FILE contamination, the shape refcompare hits
    after-other, with clear     the same, cleared between
    separate-process            X alone, twice, in two processes
                                -> the determinism baseline; must be exactly 0

REPORTED AS TWO SEPARATE QUANTITIES, because they answer different questions. A pixel delta
says how far a value moved; a RECORD-SET delta says the run rendered a different set of
records entirely, which is the 2,229-vs-2,288 signature and is not a small-number effect at
all. A floor quoted only in pixels would hide it.

Raw per-arm results go to JSON so they stay re-analysable rather than a summary to trust.

THE ANSWER, first run, against a pinned `git archive HEAD` export (9f25301), 3 packs,
max_dim 64 -- every arm ZERO:

    same-process / no clear         record-set 0   max |pixel delta| 0
    same-process / with clear       record-set 0   max |pixel delta| 0
    after-other  / no clear         record-set 0   max |pixel delta| 0
    after-other  / with clear       record-set 0   max |pixel delta| 0
    separate process                record-set 0

Cross-process was also checked at max_dim 160 on Auras_FX: 427 records, 0 differing. The
renderer is bit-reproducible.

`cleanroom-substance-ca` reached the same result independently and by a different route --
refcompare scoring rather than `render()` outputs -- with two identical passes differing on
0 of 10 channels at 1e-12, and five packs rendered before Chesterfield without clearing
giving 0 of 881 records differing.

WHAT THAT RETIRES. Three reasons were on record to expect a large floor and none survives:

  * the SAMPLERS leak is UNOBSERVED. `SAMPLERS` is module-level and `render()` does not
    clear it at entry, but the fxmaps branch saves and restores per record and the
    pixelprocessor branch tests bindings against `own_slots` rather than SAMPLERS
    membership -- defensive code that already neutralises it on the paths that matter. A
    latent maintenance hazard, not a measurement contaminant. The "2,229 records and then
    2,288 depending on what rendered before it" figure that was quoted for it belongs to a
    different experiment (bounding `Record.programs`' word scan) and was attached to the
    wrong cause.
  * the "load artifact" was a MOVED BASELINE. Two runs of `refcompare` came back
    byte-identical to each other and disagreed with a baseline captured hours earlier while
    peers were committing. With a zero floor, the two agreeing is exactly what is predicted;
    the disagreement was a real code difference. Diagnosed as load, and that was wrong.
  * `warp.reference_px` is not covered here.

SO THE USEFUL STATEMENT IS NARROW AND SOLID: an in-process A/B is not contaminated by prior
renders, and the arms that were split into separate processes to dodge the leak did not
need to be. What this does NOT license is quoting "the floor is zero" generally -- it is
measured on 3 packs, at 64 (and one file at 160), with no concurrent load, and a difference
that exists only at full render dimension would not appear here.

AND IT DOES NOT MAKE SMALL DELTAS MEANINGFUL. A zero floor means a 0.0014 movement is real
rather than noise; it says nothing about whether 0.0014 is enough to DISCRIMINATE between
two decodes. That is the sensitivity question and it needs its own instrument.
"""
import argparse
import collections
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R                                                   # noqa: E402
import sbsruntime                                                    # noqa: E402
from sbsasm import Assembly                                          # noqa: E402

REF_GLOB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'new_opengameart', '**', '*.sbsasm')


def reference_files():
    """The scored packs, by ABSOLUTE path.

    Deliberately not a cwd-relative glob. `nonwalked.py`'s `REF_GLOB` is relative, so run
    from `tools/` it reports 0 reference packs and from the repo root it reports 8 -- and
    prints the same confident "-> DISJOINT" either way, with its "overlap 0" vacuously true
    in the first case. The tool that measured the blind spot had one.
    """
    return sorted(glob.glob(REF_GLOB, recursive=True))


def _render(path, dim, clear):
    if clear:
        sbsruntime.SAMPLERS.clear()
    out, _reasons, _synth = R.render(Assembly(path), verbose=False, max_dim=dim)
    return {i: np.asarray(v, dtype=np.float64) for i, v in out.items()}


def _delta(a, b):
    """(record-set difference, max |pixel delta| over common records, n records moved)."""
    only = (set(a) ^ set(b))
    worst, moved = 0.0, 0
    for i in set(a) & set(b):
        x, y = a[i], b[i]
        if x.shape != y.shape:
            only.add(i)
            continue
        d = np.abs(x - y)
        d = d[np.isfinite(d)]
        if d.size and d.max() > 0:
            moved += 1
            worst = max(worst, float(d.max()))
    return len(only), worst, moved


def _hash_only(path, dim, out):
    """Render once and write {record: sha256 of its array}. The separate-process arm's child."""
    import hashlib
    o = _render(path, dim, clear=True)
    json.dump({str(i): hashlib.sha256(v.tobytes()).hexdigest() for i, v in o.items()},
              open(out, 'w'))


def main(argv=None):
    if argv is None and len(sys.argv) > 1 and sys.argv[1] == '--hash-only':
        _hash_only(sys.argv[2], int(sys.argv[3]), sys.argv[4])
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument('--dim', type=int, default=64, help='render grid cap (default 64)')
    ap.add_argument('--packs', type=int, default=3, help='how many packs to test')
    ap.add_argument('--json', default='/tmp/noise_floor.json')
    a = ap.parse_args(argv)

    files = reference_files()[:a.packs]
    if len(files) < 2:
        print('need at least 2 reference packs, found %d' % len(files))
        return 2
    other = files[-1]
    rows = []
    print('noise floor -- same file, same code, %d packs, max_dim=%d\n' % (len(files), a.dim))
    print('  %-26s %-8s %10s %9s %s' % ('file', 'arm', 'recset d', 'max |d|', 'recs moved'))
    for path in files:
        name = os.path.basename(path)[:26]
        base = _render(path, a.dim, clear=True)

        # 1. same process, back to back, NO clear -- the leak
        s, w, m = _delta(base, _render(path, a.dim, clear=False))
        rows.append(dict(file=name, arm='same-proc/noclear', recset=s, worst=w, moved=m))
        print('  %-26s %-8s %10d %9.6g %d' % (name, 'noclear', s, w, m))

        # 2. same process, back to back, WITH clear
        s, w, m = _delta(base, _render(path, a.dim, clear=True))
        rows.append(dict(file=name, arm='same-proc/clear', recset=s, worst=w, moved=m))
        print('  %-26s %-8s %10d %9.6g %d' % (name, 'clear', s, w, m))

        # 3. after a DIFFERENT file, no clear -- cross-file contamination
        if other != path:
            sbsruntime.SAMPLERS.clear()
            _render(other, a.dim, clear=False)
            s, w, m = _delta(base, _render(path, a.dim, clear=False))
            rows.append(dict(file=name, arm='after-other/noclear', recset=s, worst=w, moved=m))
            print('  %-26s %-8s %10d %9.6g %d' % (name, 'afterY', s, w, m))

            # 4. after a different file, WITH clear
            sbsruntime.SAMPLERS.clear()
            _render(other, a.dim, clear=False)
            s, w, m = _delta(base, _render(path, a.dim, clear=True))
            rows.append(dict(file=name, arm='after-other/clear', recset=s, worst=w, moved=m))
            print('  %-26s %-8s %10d %9.6g %d' % (name, 'afterY+c', s, w, m))

    # 5. separate processes. Run as a child so nothing of this process's state can carry,
    # which is the only arm the in-process ones cannot cover by construction.
    import subprocess, hashlib, tempfile
    for path in files[:1]:
        name = os.path.basename(path)[:26]
        hs = []
        for _ in range(2):
            fd, tmp = tempfile.mkstemp(suffix='.json'); os.close(fd)
            subprocess.run([sys.executable, os.path.abspath(__file__),
                            '--hash-only', path, str(a.dim), tmp], check=True,
                           stdout=subprocess.DEVNULL)
            hs.append(json.load(open(tmp))); os.unlink(tmp)
        diff = sum(1 for k in set(hs[0]) | set(hs[1]) if hs[0].get(k) != hs[1].get(k))
        rows.append(dict(file=name, arm='separate-process', recset=diff, worst=0.0, moved=diff))
        print('  %-26s %-8s %10d %9s %d' % (name, 'xproc', diff, '-', diff))

    with open(a.json, 'w') as fh:
        json.dump(rows, fh, indent=1)

    print()
    byarm = collections.defaultdict(lambda: [0, 0.0, 0])
    for r in rows:
        v = byarm[r['arm']]
        v[0] += r['recset']; v[1] = max(v[1], r['worst']); v[2] += r['moved']
    print('  THE FLOOR, per arm (all should be zero; anything else is the instrument):')
    for arm, (s, w, m) in sorted(byarm.items()):
        print('    %-22s record-set delta %4d   max |pixel delta| %-12.6g records moved %d'
              % (arm, s, w, m))
    floor = max((v[1] for v in byarm.values()), default=0.0)
    print('\n  worst non-zero movement under a provably null change: %.6g' % floor)
    print('  raw: %s' % a.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
