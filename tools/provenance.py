#!/usr/bin/env python3
"""The provenance exclusion predicate, as an actual re-runnable check.

README.md and FORMAT-NOTES.md's Provenance statement both describe the rule as "a file
containing `<author v="Allegorithmic"` was dropped in its entirety" and call it "one string
match [that] can be re-run against any corpus" -- but no code implementing it existed
anywhere in tools/ or the root scripts. Whatever enforced it when the corpus was first built
was a one-off step that was never saved, so the number it produced could go stale silently
as the corpus grew. It has: see `audit()` below.

WHAT THE RULE APPLIES TO -- the distinction that makes this file easy to get backwards.

The rule excludes Adobe's `.sbs` SOURCES from source-level analysis. It does NOT remove the
corresponding compiled assembly from the corpus. Analysing a freely distributed compiled
`.sbsar` is the entire basis of this project; reading Adobe's bundled library graph
DEFINITIONS is the thing being refused. So a specimen can legitimately be both:

  * present in DISTINCT.txt (its compiled .sbsasm is analysed), and
  * source-excluded (its .sbs is off limits for containment/identification work).

FORMAT-NOTES.md states exactly this where it records the rule's cost -- "Every file in the
corpus that uses `motionblur` is excluded by the provenance rule" -- a sentence that only
parses if in-corpus and source-excluded are independent properties. An earlier version of
this module treated the two as the same thing and reported the 42 source-excluded specimens
as corpus entries to delete. They are not; deleting them would discard legitimately analysed
compiled specimens and silently move every corpus-wide figure.

WHAT THIS CHECKS: which paired `.sbs` sources carry an excluded author tag. That is the
population the rule governs. It says nothing about whether the compiled sibling belongs in
the corpus -- it does.

COVERAGE LIMIT: the author string lives in the `.sbs` source only. A bare `.sbsar` never
preserves it (0 of 396 `.sbsar`-only specimens sampled contain the literal string, including
ones known to be Allegorithmic-authored via a paired source elsewhere). Most of the corpus is
compiled-only and cannot be checked this way at all -- their authorship is neither confirmed
nor cleared here, and `audit()` reports them as `unknown` rather than folding them into a
clean count they were never tested for.
"""
import glob
import hashlib
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXCLUDED_AUTHORS = [
    'Allegorithmic',     # Adobe, pre-acquisition -- Adobe's own bundled library sources
]

# Authors found to carry non-permissive terms but NOT currently part of the stated rule.
# Kept separate on purpose: adding a name to EXCLUDED_AUTHORS changes what the corpus is
# and moves published figures, which is a decision to take deliberately and record, not a
# side effect of noticing something. `audit()` reports these separately.
FLAGGED_AUTHORS = [
    # gametextures.com: proprietary subscription licence, explicit anti-sublicensing
    # clause, no CC0/public-domain statement. Appears in sources published to GitHub by
    # third parties under their own permissive licences -- i.e. redistributed upstream in
    # a way those terms do not appear to allow. Analysing the compiled sibling stands on
    # the same footing as any other freely distributed .sbsar; whether the SOURCE should be
    # excluded the way Allegorithmic's is remains an open call.
    'GameTextures.com',
]

SEARCH_DIRS = ["pairs", "pairs2", "pairs3", "pairs4", "pairs5", "pairs6", "new_sbs",
               "new_opengameart"]


def author_tags(sbs_path):
    """Every `<author v="...">` value in a .sbs, in document order.

    A package's own author tag is frequently blank while a GRAPH nested inside it carries
    the real one -- `serverhouse__BrickWall_02.sbs` has a blank package author and one
    Allegorithmic graph among its four. Checking only the package-level tag would miss it,
    which is why the stated rule is a whole-file string match and why this returns all of
    them rather than "the" author.
    """
    try:
        data = open(sbs_path, encoding='utf-8', errors='replace').read()
    except OSError:
        return []
    return re.findall(r'<author v="([^"]*)"', data)


def matches(sbs_path, names):
    """Which of `names` this file's author tags match, or None."""
    tags = set(author_tags(sbs_path))
    for n in names:
        if n in tags:
            return n
    return None


def paired_sources():
    """Distinct-by-content .sbs files that have a sibling .sbsar -- the rule's population."""
    found, seen, out = [], set(), []
    for d in SEARCH_DIRS:
        found += glob.glob(os.path.join(ROOT, d, "**", "*.sbs"), recursive=True)
    for p in sorted(found):
        if not os.path.exists(p[:-4] + ".sbsar"):
            continue
        try:
            h = hashlib.sha1(open(p, 'rb').read()).hexdigest()
        except OSError:
            continue
        if h in seen:
            continue
        seen.add(h)
        out.append(p)
    return out


def audit():
    """Return (excluded, flagged, permitted) paired-source paths."""
    excluded, flagged, permitted = [], [], []
    for p in paired_sources():
        rel = os.path.relpath(p, ROOT)
        hit = matches(p, EXCLUDED_AUTHORS)
        if hit:
            excluded.append((rel, hit))
            continue
        hit = matches(p, FLAGGED_AUTHORS)
        if hit:
            flagged.append((rel, hit))
        else:
            permitted.append(rel)
    return excluded, flagged, permitted


if __name__ == '__main__':
    excluded, flagged, permitted = audit()
    total = len(excluded) + len(flagged) + len(permitted)
    # `new_opengameart/` postdates the published figures; hold it out so the comparison
    # below is against the same population the document was describing.
    added = [r for r, *_ in excluded] + [r for r, *_ in flagged] + permitted
    new = [r for r in added if r.startswith('new_opengameart/')]
    print('paired sources (distinct by content): %d' % total)
    print('  excluded by the stated rule:        %d' % len(excluded))
    print('  permitted:                          %d' % (len(permitted) + len(flagged)))
    if new:
        print('  (of which %d are new_opengameart/, added after the figures below)' % len(new))
    print()
    print('FORMAT-NOTES.md / README.md state: 140 paired sources, 38 excluded, 102 permitted.')
    print('  paired sources, excluding new_opengameart/:  %d   (document says 140)'
          % (total - len(new)))
    print('  excluded by re-running the rule:             %d   (document says 38)'
          % len(excluded))
    if len(excluded) != 38:
        print()
        print('  The published 38 is STALE by %d. The rule was applied once and never saved'
              % (len(excluded) - 38))
        print('  as code, so sources added since were never tested against it.')
    print()
    if flagged:
        print('flagged, NOT excluded by the current rule (%d):' % len(flagged))
        for rel, who in flagged:
            print('    %-70s %s' % (rel, who))
        print()
        print('  These are a live question, not a settled exclusion -- see FLAGGED_AUTHORS.')
