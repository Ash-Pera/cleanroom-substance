#!/usr/bin/env python3
"""The corpus file list, deduplicated by CONTENT.

`DISTINCT.txt` is distinct by path, and for a long time that was quietly not the same
thing. Extraction wrote the same `.sbsasm` into `tiny/`, `pairs/` and the main corpus
directory, so 641 paths held 438 distinct files -- 138 hashes appearing between two and
five times, 120 redundant copies from `tiny/` and 78 from `pairs/` alone.

Nothing failed. Every ratio stayed about right, because a duplicate file is a fair
sample of itself; what broke was every COUNT, uniformly inflated by about 20%, and the
weighting, which quietly tripled the influence of whichever files happened to be
extracted more than once. A corpus figure of "1,086,833 records" was really 904,165.

So this is not a convenience wrapper. Reading the list through here is what makes a
count mean what it says.
"""
import hashlib
import os

LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DISTINCT.txt')


def paths(listing=None, verbose=False):
    """Corpus paths, at most one per distinct file content, in first-seen order."""
    src = listing or LIST
    out, seen, dropped = [], {}, 0
    for line in open(src):
        p = line.strip()
        if not p:
            continue
        try:
            with open(p, 'rb') as fh:
                h = hashlib.sha1(fh.read()).hexdigest()
        except OSError:
            continue                      # a path that no longer resolves is not a file
        if h in seen:
            dropped += 1
            continue
        seen[h] = p
        out.append(p)
    if verbose and dropped:
        print('corpus: dropped %d duplicate-content paths, %d files remain'
              % (dropped, len(out)))
    return out


if __name__ == '__main__':
    ps = paths(verbose=True)
    print('%d distinct files' % len(ps))
