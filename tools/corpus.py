#!/usr/bin/env python3
"""The corpus file list: one canonical source, deduplicated by CONTENT.

There were two lists, and the difference between them was recorded and then not applied.

`tools/DISTINCT.txt` held 641 paths that were 438 distinct files - extraction had written
the same `.sbsasm` into `tiny/` (120 redundant copies), `pairs/` (78), the main corpus
directory (4) and `acg2/` (1), with single files appearing up to five times. That was
found, and `tools/reverify.py` has said so in its own docstring ever since:

    "Their denominators came from tools/DISTINCT.txt - the withdrawn 641-file list, about
     a third duplicates - and survived the correction to the 435-file root list because a
     settled number invites no re-reading."

`reverify.py` moved to the root list. `audit_corpus.py` did not, and audit_corpus.py is
what prints the headline figures. So the corpus was corrected in one place, documented in
a second, and left wrong in the third - and the third was the one anybody read. Every
audit figure was inflated by about 20% for as long as that lasted, and the ratios all
stayed right, which is why it did.

The lesson is not "check the corpus". It is that a correction recorded in prose does not
propagate to code, and the fix has to be a single place both tools call.

This module is that place. Both lists are now deduplicated and agree at 438 files; the
root list is canonical because that is the one the correction moved to.
"""
import hashlib
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = os.path.join(ROOT, 'DISTINCT.txt')
LEGACY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DISTINCT.txt')


def paths(listing=None, verbose=False):
    """Corpus paths, at most one per distinct file content, in first-seen order.

    Deduplicates even though both lists are currently clean. The duplication took hold
    silently the first time; a loader that only works on already-correct input would let
    it happen again.
    """
    src = listing or (LIST if os.path.exists(LIST) else LEGACY)
    out, seen, dropped = [], set(), 0
    for line in open(src):
        p = line.strip()
        if not p:
            continue
        if not os.path.isabs(p):
            p = os.path.join(ROOT, p)
        try:
            with open(p, 'rb') as fh:
                h = hashlib.sha1(fh.read()).hexdigest()
        except OSError:
            continue                      # a path that no longer resolves is not a file
        if h in seen:
            dropped += 1
            continue
        seen.add(h)
        out.append(p)
    if verbose:
        print('corpus: %d files from %s%s'
              % (len(out), os.path.relpath(src, ROOT),
                 (' (%d duplicate-content paths dropped)' % dropped) if dropped else ''))
    return out


if __name__ == '__main__':
    print('%d distinct files' % len(paths(verbose=True)))
