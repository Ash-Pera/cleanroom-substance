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
import glob
import hashlib
import json
import os
import re

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


#: SPEC 12's clean-room boundary, as a predicate instead of a habit.
#:
#: "any source file bearing `<author v="Allegorithmic">` was excluded from analysis" was
#: stated in the spec, repeated in `sbsasm`'s comments, and enforced by nothing: `paths()`
#: lists `.sbsasm` only, so every reader of a `.sbs` reached for `glob` and walked straight
#: past the rule. It has been tripped over -- FX-Map `$pos` semantics were derived from
#: `noise_bnw_spots_3.sbs` and written into SPEC and `assume.py` before anyone read the tag.
#:
#: THE EXCLUDED SET IS NOT A FRINGE. Of the 491 sources here 131 bear the tag and 360 do not,
#: and the excluded ones are exactly the interesting ones for FX-Maps: every branching FX-Map
#: graph in the repository (81 of 81) and every four-way node (63 of 63) is theirs. Any
#: negative measured over `sources()` therefore means "absent from what may be examined",
#: never "absent from the format", and a result that turns on the difference has to say so.
#:
#: AN UNTAGGED SOURCE IS NOT EXCLUDED, and the first version of this module got that wrong in
#: a way worth recording. Refusing anything without an author tag looks like the careful
#: reading and is not the stated one -- SPEC 12 excludes a file BEARING the tag. 159 of the
#: 491 sources carry no author tag at all, and they include BOTH of the paired specimens the
#: repository's four hand-derived namings rest on (`ChesterfieldSofa.sbs`,
#: `SandyStonePath.sbs`, neither tagged). Failing closed on them would have silently voided
#: `sourcematch --verify` and `test_the_legend_agrees_with_the_shipped_sources` while looking
#: more conservative than the rule it was enforcing. Only an UNREADABLE file fails closed.
_AUTHOR = re.compile(rb'<author v="([^"]*)"/>')
_EXCLUDED_AUTHOR = b'Allegorithmic'

#: The package author sits in the preamble -- 320 of the 332 tagged sources have it inside
#: the first 8 KB, median offset 524 bytes. These files run to megabytes on ONE line, so the
#: head read is what keeps this a predicate rather than a full corpus scan; the 12 stragglers
#: fall through to a whole-file search rather than being guessed at.
_HEAD = 8192


def source_author(path):
    """The author a `.sbs` states, `None` if it states none, `False` if unreadable."""
    try:
        with open(path, 'rb') as fh:
            head = fh.read(_HEAD)
            m = _AUTHOR.search(head)
            if m is None:
                fh.seek(0)
                m = _AUTHOR.search(fh.read())
    except OSError:
        return False
    return None if m is None else m.group(1).decode('utf-8', 'replace')


def source_excluded(path):
    """Is this `.sbs` excluded by SPEC 12? True iff it BEARS an Allegorithmic author tag.

    An unreadable file is excluded -- a boundary that cannot be checked is not cleared. An
    untagged one is not; see the note above for why that distinction is load-bearing.
    """
    a = source_author(path)
    if a is False:
        return True
    return a is not None and 'Allegorithmic' in a


def sources(root=None):
    """Every `.sbs` in the tree that SPEC 12 permits, sorted.

    The counterpart to `paths()`: that one is the compiled corpus, this one is the sources,
    and a caller wanting sources should call this rather than globbing. `source_excluded` is
    exposed separately for a caller handed a single path on a command line.
    """
    base = root or ROOT
    return [p for p in sorted(glob.glob(os.path.join(base, '**', '*.sbs'), recursive=True))
            if not p.endswith('.sbsar') and not source_excluded(p)]


if __name__ == '__main__':
    print('%d distinct files' % len(paths(verbose=True)))
    allowed = sources()
    every = [p for p in glob.glob(os.path.join(ROOT, '**', '*.sbs'), recursive=True)
             if not p.endswith('.sbsar')]
    untagged = sum(1 for p in allowed if source_author(p) is None)
    print('%d sources, %d readable under SPEC 12 (%d excluded, %d of the readable untagged)'
          % (len(every), len(allowed), len(every) - len(allowed), untagged))
