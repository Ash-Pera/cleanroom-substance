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


def flat_origin(asm, rec, produced, flat):
    """The record that INTRODUCES an output's flatness, walking back through flat inputs.

    A FLAT OUTPUT IS NOT AUTOMATICALLY A DEFECT, and reporting the count without saying
    what made it flat reads as ten broken renders when most are the engine's own answer.
    Over 30 files, the 10 flat declared outputs split:

        a `uniform` record that IS the output      6    metallic 0.0 on a non-metal,
                                                        roughness 0.25, and so on -- the
                                                        material is constant there
        a `pixelprocessor`                         4    all four are fur_var_001 record 17,
                                                        and its value is 1.31, outside
                                                        [0, 1], so that one is broken

    Six of the ten are correct. The four that are not are one record in one file, and they
    are the `filter_programs[-1]` selection gap the render's channel guard already names.
    """
    cur, guard = rec, 0
    while guard < 200:
        guard += 1
        nxt = [e for e in asm.records[cur].edges if e in produced and flat.get(e)]
        if not nxt:
            break
        cur = nxt[0]
    return asm.records[cur].filter_name


def roots_blocking(asm, rec, failures, cascaded=()):
    """The failures in `rec`'s cone that are not caused by another failure.

    CASCADE IS A FLAG, NOT A PREFIX, and reading it off the prose is the mistake
    `render.cascade` was written to stop. Its docstring says so outright: fourteen raise
    sites say "has no output yet" and a fifteenth says "no sampler for input 0", meaning
    exactly the same thing, and matching on the string missed it -- which named an fxmaps
    record as a specimen's blocker when it sat three levels downstream of the real one.

    This function was making that same mistake with `msg.startswith('edge')`. Over 30 files
    it reported 5 declared outputs under `fxmaps: no sampler installed for input 0`; every
    one is an FX-Map whose first edge failed with `produced non-finite values`, and
    render.py already raises those through `cascade()` and collects them in `CASCADED`.
    The table was crediting a consequence as a cause, in the exact way the helper exists to
    prevent -- and this table is what the work gets chosen from.
    """
    seen, stack, found = set(), [rec], []
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        msg = failures.get(n)
        if msg and n not in cascaded:
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
            # Snapshot immediately: `CASCADED` is module state that the next render clears.
            cascaded = set(render.CASCADED)
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
                if arr.min() == arr.max():
                    tally['rendered flat'] += 1
                    flat = {}
                    for j, a in produced.items():
                        v = np.asarray(a, dtype=np.float64)
                        flat[j] = bool(v.min() == v.max())
                    tally['flat from ' + flat_origin(asm, rec, produced, flat)] += 1
                continue
            for msg in roots_blocking(asm, rec, failures, cascaded):
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
    for key in sorted(k for k in tally if k.startswith('flat from ')):
        print('    %-34s %d   %s' % (key, tally[key],
                                     '(a constant channel is a real answer)'
                                     if key == 'flat from uniform' else ''))
    print('\nroot causes, counted once per blocked output:')
    for msg, n in roots.most_common(20):
        print('   %4d  %s' % (n, msg))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
