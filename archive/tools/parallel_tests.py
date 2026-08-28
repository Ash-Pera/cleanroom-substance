#!/usr/bin/env python3
"""Run each test in its own process, N at a time, with a per-test wall cap.

WHY PROCESSES AND NOT pytest-xdist: no new dependency, and the isolation is wanted
here for its own sake -- `conftest` swaps in a session-wide Assembly cache, and
`test_tables` is excluded from it because it measures counterfactuals. One process per
test makes that exclusion unnecessary in principle and keeps a runaway test from
taking the report down with it.

WHAT IT BUYS, measured on this corpus: the slow lane's 27 tests are 5,940 seconds of
work serially, of which four render tests are over 900 seconds each. With eight
workers the wall clock is the slowest single test, and the other 23 report in about
150 seconds instead of never.

A capped test is reported as TIMEOUT and does not stop the run -- the point is to see
the 23 results that a serial run hides behind the 4.
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

TOOLS = os.path.dirname(os.path.abspath(__file__))
DEFAULT = ['test_filters.py', 'test_fx.py', 'test_tables.py',
           'test_transpile.py', 'test_standalone_parse.py', 'test_corpus_discovery.py']
CAP = float(os.environ.get('CAP', '900'))
WORKERS = int(os.environ.get('W', '8'))


def collect(mods):
    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--collect-only',
                        '--no-header', '-p', 'no:cacheprovider'] + mods,
                       cwd=TOOLS, capture_output=True, text=True)
    return [l.strip() for l in r.stdout.splitlines() if '::' in l]


def run_one(nid):
    t = time.time()
    try:
        r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--no-header',
                            '-p', 'no:cacheprovider', nid],
                           cwd=TOOLS, capture_output=True, text=True, timeout=CAP)
        return nid, time.time() - t, ('pass' if r.returncode == 0 else 'FAIL'), r.stdout
    except subprocess.TimeoutExpired:
        return nid, time.time() - t, 'TIMEOUT', ''


def main():
    mods = [a for a in sys.argv[1:] if not a.startswith('-')] or DEFAULT
    mods = [m for m in mods if os.path.exists(os.path.join(TOOLS, m))]
    ids = collect(mods)
    if not ids:
        print('no tests collected from %s' % mods)
        return 1
    print('%d tests, %d workers, %.0fs cap' % (len(ids), WORKERS, CAP), flush=True)
    t0, res = time.time(), []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(run_one, n) for n in ids]
        for f in as_completed(futs):
            nid, dt, status, out = f.result()
            res.append((dt, nid, status, out))
            print('%7.1fs  %-7s %s' % (dt, status, nid), flush=True)
    wall = time.time() - t0
    bad = [(n, s, o) for _, n, s, o in res if s != 'pass']
    print('\n%d passed, %d failed, %d timed out   wall %.0fs, work %.0fs (%.1fx)'
          % (sum(1 for r in res if r[2] == 'pass'),
             sum(1 for r in res if r[2] == 'FAIL'),
             sum(1 for r in res if r[2] == 'TIMEOUT'),
             wall, sum(r[0] for r in res), sum(r[0] for r in res) / max(wall, 1e-9)))
    for nid, status, out in bad:
        if status == 'FAIL':
            print('\n===== %s =====\n%s' % (nid, out[-3000:]))
    return 1 if any(s == 'FAIL' for _, _, s, _ in res) else 0


if __name__ == '__main__':
    sys.exit(main())
