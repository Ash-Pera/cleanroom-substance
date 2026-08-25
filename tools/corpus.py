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

This module is that place, and the root list is canonical because that is the one the
correction moved to.

The two lists do NOT quite agree, and the earlier version of this docstring claimed they
did. By content: the root list holds 437 distinct files, `tools/DISTINCT.txt` holds 438,
and they share 436 -- two files are in the legacy list only, one in the root list only.
Nothing reads the legacy list while the root list exists, so no figure is affected; the
claim of agreement was simply never checked after it was written. Which is the same
failure this module was created to fix, one level up: a statement about the data, made
once and not re-measured.
"""
import hashlib
import json
import os

# Two caches, because the sha1 of four gigabytes is not free and every tool and test
# calls paths() at least once (the full test suite called it about thirty times).
#   _MEMO           per-process: same listing file, same mtime -> same answer
#   .hashcache.json persistent: (size, mtime) -> sha1 per path, so a cold process
#                   hashes only files that changed since the last run
_MEMO = {}
_HASHCACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.hashcache.json')

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
    try:
        memo_key = (src, os.stat(src).st_mtime_ns)
    except OSError:
        memo_key = None
    if memo_key in _MEMO:
        return list(_MEMO[memo_key])
    try:
        hc = json.load(open(_HASHCACHE))
    except Exception:
        hc = {}
    hc_dirty = False
    out, seen, dropped = [], set(), 0
    for line in open(src):
        p = line.strip()
        if not p:
            continue
        if not os.path.isabs(p):
            p = os.path.join(ROOT, p)
        try:
            st = os.stat(p)
            sig = '%d:%d' % (st.st_size, st.st_mtime_ns)
            ent = hc.get(p)
            if ent and ent[0] == sig:
                h = ent[1]
            else:
                with open(p, 'rb') as fh:
                    h = hashlib.sha1(fh.read()).hexdigest()
                hc[p] = [sig, h]
                hc_dirty = True
        except OSError:
            continue                      # a path that no longer resolves is not a file
        if h in seen:
            dropped += 1
            continue
        seen.add(h)
        out.append(p)
    if hc_dirty:
        try:
            tmp = _HASHCACHE + '.tmp'
            json.dump(hc, open(tmp, 'w'))
            os.replace(tmp, _HASHCACHE)
        except OSError:
            pass
    if memo_key is not None:
        _MEMO[memo_key] = list(out)
    if verbose:
        print('corpus: %d files from %s%s'
              % (len(out), os.path.relpath(src, ROOT),
                 (' (%d duplicate-content paths dropped)' % dropped) if dropped else ''))
    return out


if __name__ == '__main__':
    print('%d distinct files' % len(paths(verbose=True)))
