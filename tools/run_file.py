#!/usr/bin/env python3
"""Evaluate every program in a file, in record order, through one shared cache.

`cache_read` raises unless a caller threads a cache through the whole file - its own
docstring says so, and says what such a caller must do. Nothing did. The consequence was
that no program containing a cross-record cache read could be executed at all, and any
measurement of "does this program run" scored those as failures regardless of what was
being tested. That made the control group for the condition-less loop question fail 518
of 518, so the question could not be asked.

This supplies what the runtime needs:

    a shared cache      one dict for the file, threaded in record order, so 0x06 writes
                        land before the 0x03 reads that want them
    samplers            a constant frame per index, since the point is whether a program
                        EVALUATES, not what picture it makes
    inputs              a permissive mapping, so a missing uid yields a value instead of
                        a KeyError

    python3 tools/run_file.py <file.sbsasm>
    python3 tools/run_file.py --corpus <list-file> [limit]
"""
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbsasm                                                        # noqa: E402
import sbsruntime                                                    # noqa: E402
import transpile                                                     # noqa: E402


class Permissive(dict):
    """Any uid resolves; an absent one is 0.5, a plausible mid-range parameter."""

    def __missing__(self, key):
        return 0.5


def _namespace():
    ns = {'np': np}
    ns.update({k: getattr(sbsruntime, k)
               for k in dir(sbsruntime) if not k.startswith('_')})
    return ns


class _Samplers(dict):
    """Any sampler index resolves to a constant frame.

    Indices are not small: the corpus references up to 8,688, so pre-installing a fixed
    count leaves holes that surface as KeyError and look like program failures. They are
    not - the point of this harness is whether a program EVALUATES, and every index it
    reaches must therefore answer.
    """

    def __init__(self, size=8):
        super().__init__()
        self._frame = np.full((size, size, 4), 0.5, dtype=float)

    def __missing__(self, index):
        fn = sbsruntime.image_sampler(self._frame)
        self[index] = fn
        return fn


def install_samplers(count=None, size=8):
    """Install a mapping that answers for every sampler index."""
    sbsruntime.SAMPLERS = _Samplers(size)


def programs_of(asm, rec):
    pts = []
    try:
        pts = list(rec.programs)
    except Exception:
        pass
    if rec.filter_id == 4:
        try:
            pts += [pr for _k, _o, _t, pr in rec.fx_walk() if pr]
        except Exception:
            pass
    return pts


def run_file(path, stats):
    asm = sbsasm.Assembly(path)
    install_samplers()
    cache = {}
    prev = sbsruntime.use_shared_cache(cache)
    try:
        for rec in asm.records:                 # record order: writers precede readers
            try:
                sbsruntime.set_context(width=rec.width, height=rec.height)
            except Exception:
                pass
            for q in programs_of(asm, rec):
                stats['programs'] += 1
                try:
                    src = transpile.transpile(asm.data, q, asm.body_hi)
                except Exception as exc:
                    stats['not transpiled: ' + type(exc).__name__] += 1
                    continue
                ns = _namespace()
                try:
                    exec(src, ns)
                    val = ns['program'](inputs=Permissive(), slots=Permissive())
                except Exception as exc:
                    stats['failed: ' + type(exc).__name__] += 1
                    continue
                stats['ran'] += 1
                try:
                    arr = np.asarray(val, dtype=float)
                    stats['finite'] += bool(np.all(np.isfinite(arr)))
                except Exception:
                    stats['unmeasurable value'] += 1
    finally:
        sbsruntime.use_shared_cache(prev)
    return stats


def main():
    args = sys.argv[1:]
    stats = collections.Counter()
    if args and args[0] == '--corpus':
        paths = [l.strip() for l in open(args[1]) if l.strip()]
        if len(args) > 2:
            paths = paths[:int(args[2])]
    else:
        paths = args
    files = 0
    for p in paths:
        try:
            run_file(p, stats)
            files += 1
        except Exception as exc:
            stats['file unreadable: ' + type(exc).__name__] += 1
    n = stats['programs']
    print('files                 : %d' % files)
    print('programs              : %d' % n)
    if n:
        print('  ran to a value      : %d  (%.2f%%)' % (stats['ran'], 100 * stats['ran'] / n))
        print('  all values finite   : %d  (%.2f%%)'
              % (stats['finite'], 100 * stats['finite'] / n))
    for k, v in stats.most_common():
        if k.startswith(('failed', 'not transpiled', 'file unreadable')):
            print('  %-34s%d' % (k, v))
    return 0


if __name__ == '__main__':
    sys.exit(main())
