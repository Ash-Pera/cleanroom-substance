#!/usr/bin/env python3
"""How many DECLARED outputs render, against an honest denominator -- and what blocks them.

    python3 tools/output_census.py [files]

THE DENOMINATOR IS THE POINT. "N of the corpus's declared outputs render" was the figure
this project steered by, and it counts outputs that CANNOT render, ever, from the shipped
file alone. A graph whose input is a user-supplied image is a filter, not a material: its
outputs are a function of a bitmap the package does not contain, and no amount of decoding
produces one. Over 30 files:

    declared outputs                      176
      fed by a user-supplied IMAGE input   49    cannot render standalone
      renderable in principle             127
    rendered                               36

So the share is 28% of what is renderable, not 20% of everything, and the 49 are not a
backlog -- they are the wrong question. That distinction is the same failure `corpus.py`
was written to fix one level up: a denominator that was never re-derived after the
population changed.

WHICH OUTPUTS THOSE ARE IS A LOOKUP, NOT AN INFERENCE. A manifest input carries
`alteroutputs`, the set of outputs it affects, so a type-5 (image) input names its
dependents outright. Nothing here walks edges to decide it, which matters because the edge
walk is known to under-report reachability -- see
test_filters.test_closure_never_claims_a_dependency_the_manifest_denies, where the manifest
claims 513 dependencies the closure does not find.

ROOT CAUSES, NOT CASCADES. A blocked output is attributed to the failures in its own cone
that are not themselves caused by an upstream failure, so one real gap is counted once per
output it blocks rather than once per record it takes down. The same output can appear
under two roots when two independent gaps block it, which is why the column sums exceed the
number of blocked outputs.
"""
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import manifest                                                      # noqa: E402
import render                                                        # noqa: E402
from sbsasm import Assembly                                          # noqa: E402


def image_fed_outputs(asm):
    """Output uids that a type-5 (image) input alters, straight from the manifest."""
    fed = set()
    try:
        table = manifest.alter_outputs(asm)
    except Exception:
        return fed
    for _uid, (typ, _ident, claimed) in table.items():
        if typ == 5:
            fed |= set(claimed or ())
    return fed


def roots_blocking(asm, rec, failures):
    """The failures in `rec`'s cone that are not caused by another failure."""
    seen, stack, found = set(), [rec], []
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        msg = failures.get(n)
        # A cascade names the edge it is waiting on; a root says what it could not do.
        if msg and not msg.startswith('edge'):
            found.append(msg)
        for e in asm.records[n].edges:
            if e in failures:
                stack.append(e)
    return set(found)


def census(paths, max_dim=64):
    tally = collections.Counter()
    roots = collections.Counter()
    for path in paths:
        try:
            asm = Assembly(path)
            produced, failures, _synth = render.render(asm, verbose=False, max_dim=max_dim)
        except Exception:
            continue
        tally['files'] += 1
        outs = [(uid, rec) for uid, _f, _g, rec in asm.outputs()]
        if not outs:
            continue
        fed = image_fed_outputs(asm)
        for uid, rec in outs:
            tally['declared'] += 1
            if uid in fed:
                tally['needs an image'] += 1
                continue
            tally['renderable'] += 1
            if rec in produced:
                tally['rendered'] += 1
                arr = np.asarray(produced[rec], dtype=np.float64)
                tally['rendered flat'] += int(arr.min() == arr.max())
                continue
            for msg in roots_blocking(asm, rec, failures):
                roots[msg.split('(')[0].strip()[:64]] += 1
    return tally, roots


def main(argv):
    paths = argv[1:] or corpus.paths()
    tally, roots = census(paths)
    if not tally['files']:
        print('no files rendered')
        return 1
    renderable = max(1, tally['renderable'])
    print('files %d' % tally['files'])
    print('declared outputs                      %d' % tally['declared'])
    print('  fed by a user-supplied IMAGE input  %d   (cannot render standalone)'
          % tally['needs an image'])
    print('  renderable in principle             %d' % tally['renderable'])
    print('rendered                              %d  (%.0f%% of renderable)'
          % (tally['rendered'], 100.0 * tally['rendered'] / renderable))
    print('  of those, FLAT                      %d' % tally['rendered flat'])
    print('\nroot causes, counted once per blocked output:')
    for msg, n in roots.most_common(20):
        print('   %4d  %s' % (n, msg))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
