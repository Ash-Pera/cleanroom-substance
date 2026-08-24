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

THE COMPILED SIDE IS ALSO CHECKABLE, contrary to what this file said first. The original
claim here was that the author string lives in the `.sbs` only, on the evidence that
grepping 396 `.sbsar`-only specimens for `Allegorithmic` returned nothing. That test was
worthless: a `.sbsar` is a 7z archive, so no string inside it is greppable from the
container. The manifest **does** carry authorship -- `<graph ... author="Igor Elovikov">` --
and `manifest_authors()` reads it from the extracted `.xml` beside each `.sbsasm`. Over
DISTINCT.txt that finds 56 entries authored by Allegorithmic or Adobe where the source-side
check finds 42, the extra 14 being compiled-only specimens with no `.sbs` in the corpus at
all (`Bitmap2Material_3`, an Adobe product, among them).

WHAT COMPILED-SIDE AUTHORSHIP DOES **NOT** MEAN. It is not an exclusion trigger, and the
distinction is the same one that trips up the source rule. Analysing a freely distributed
compiled `.sbsar` is the basis of this project whoever authored it; what the rule refuses is
reading Adobe's `.sbs` graph DEFINITIONS. An Adobe-authored `.sbsar` supplies compiled
bytecode like any other specimen and supplies no definitions, so it stays in the corpus.
`compiled_audit()` therefore reports authorship as a fact about the corpus, not as a
deletion list -- it is the third time in this file's short history that conflating "who
wrote it" with "may we use it" would have produced a wrong answer.

What it is good for: knowing which specimens would become source-excluded if a `.sbs` for
them ever entered the corpus; seeing how much of the corpus leans on Adobe-published
material; and surfacing non-Adobe authors whose terms are not permissive at all, which is
how `GameTextures.com` was found.
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


# --- the compiled side: authorship as recorded in the .sbsar manifest ----------------

# Adobe acquired Allegorithmic; both names appear as authors in compiled manifests and mean
# the same party. Kept separate from EXCLUDED_AUTHORS because that list governs which .sbs
# SOURCES may be read, and this one governs nothing -- see the module docstring.
ADOBE_NAMES = ("Allegorithmic", "Adobe")

AUTHOR_ATTR = re.compile(r'author="([^"]*)"')


def manifest_authors(sbsasm_path):
    """Authors declared in the `.sbsar` manifest(s) sitting beside a compiled specimen.

    The extractor writes `<name>.xml` next to `<name>.sbsasm`; a manifest names an author
    per graph, so a package built from several authors' graphs returns all of them. Returns
    an empty set when no manifest is present or none declares an author -- which is a real
    outcome, not a failure, and is counted separately from "checked and clean".
    """
    out = set()
    for x in glob.glob(os.path.join(os.path.dirname(sbsasm_path), '*.xml')):
        try:
            text = open(x, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        out |= {a for a in AUTHOR_ATTR.findall(text) if a}
    return out


def compiled_audit(listing=None):
    """Authorship of every DISTINCT.txt entry, read from its compiled manifest.

    Returns (rows, no_author) where rows is [(relpath, {authors}), ...] for entries whose
    manifest declares at least one author. NOT an exclusion list: see the module docstring.
    """
    src = listing or os.path.join(ROOT, 'DISTINCT.txt')
    rows, no_author = [], []
    for line in open(src):
        p = line.strip()
        if not p:
            continue
        full = p if os.path.isabs(p) else os.path.join(ROOT, p)
        who = manifest_authors(full)
        if who:
            rows.append((p, who))
        else:
            no_author.append(p)
    return rows, no_author


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

    # --- compiled side ---------------------------------------------------------------
    rows, no_author = compiled_audit()
    if rows or no_author:
        import collections
        adobe = [(p, w) for p, w in rows if w & set(ADOBE_NAMES)]
        flag2 = [(p, w) for p, w in rows if w & set(FLAGGED_AUTHORS)]
        counts = collections.Counter(a for _p, w in rows for a in w)
        print()
        print('COMPILED SIDE -- authorship read from each specimen\'s .sbsar manifest')
        print('  DISTINCT.txt entries:              %d' % (len(rows) + len(no_author)))
        print('    manifest declares an author:     %d' % len(rows))
        print('    no author declared / no manifest: %d' % len(no_author))
        print()
        print('  authored by Adobe/Allegorithmic:   %d' % len(adobe))
        print('  authored by a FLAGGED party:       %d  %s'
              % (len(flag2), sorted({a for _p, w in flag2 for a in w & set(FLAGGED_AUTHORS)})))
        print()
        print('  NOTE: this is NOT an exclusion list. A freely distributed compiled .sbsar')
        print('  is analysable whoever wrote it; the rule refuses Adobe\'s .sbs DEFINITIONS.')
        print('  Source-side excluded: %d. Compiled-side Adobe-authored: %d. The %d extra are'
              % (len(excluded), len(adobe), max(0, len(adobe) - len(excluded))))
        print('  compiled-only specimens with no .sbs in the corpus to exclude.')
        print()
        print('  top authors by specimen count:')
        for name, n in counts.most_common(8):
            mark = '  <-- Adobe' if name in ADOBE_NAMES else (
                   '  <-- flagged' if name in FLAGGED_AUTHORS else '')
            print('      %-34s %4d%s' % (name[:34], n, mark))
