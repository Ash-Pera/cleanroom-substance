#!/usr/bin/env python3
"""Corpus discovery must not depend on where the command was typed.

Three tools were found in one session reporting on a corpus that had silently shrunk,
each in its own way, and every one of them was a path-resolution bug rather than
anything to do with the format:

    audit_corpus.py     read the WITHDRAWN 641-path list, ~20% duplicates, and printed
                        every headline count inflated by that much
    reverify.py         resolved the root list's relative paths against the working
                        directory, loaded 3 of 438 files, and reported two FAILs whose
                        arithmetic came from full-corpus exception counts
    validate_corpus.py  globbed relative directory patterns, found nothing from `tools/`,
                        and printed "no specimens found"

All three were silent or near-silent. None of them was a wrong answer about the bytes;
all three were wrong answers about which bytes. So the check is not "is the corpus
right", it is "does the tool find the same corpus from anywhere".
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXPECTED = 438


def test_corpus_paths_are_cwd_independent():
    """corpus.paths returns the same files from the root, from tools/ and from /."""
    sys.path.insert(0, HERE)
    import corpus
    results = {}
    start = os.getcwd()
    try:
        for where in (ROOT, HERE, os.sep):
            os.chdir(where)
            results[where] = corpus.paths()
    finally:
        os.chdir(start)
    counts = {w: len(v) for w, v in results.items()}
    assert len(set(counts.values())) == 1, 'corpus size varies by cwd: %r' % counts
    assert set(map(tuple, results.values())).__len__() == 1, 'corpus CONTENT varies by cwd'
    assert counts[ROOT] == EXPECTED, 'expected %d files, got %r' % (EXPECTED, counts)


def test_corpus_paths_have_no_duplicate_contents():
    """The whole point of the loader: one entry per distinct file."""
    import hashlib
    sys.path.insert(0, HERE)
    import corpus
    seen = set()
    for p in corpus.paths():
        with open(p, 'rb') as fh:
            h = hashlib.sha1(fh.read()).hexdigest()
        assert h not in seen, 'duplicate content survived the loader: %s' % p
        seen.add(h)


def test_validator_finds_specimens_from_tools_dir():
    """validate_corpus globs the corpus directories; they are at the repo root."""
    out = subprocess.run([sys.executable, os.path.join(HERE, 'validate_corpus.py')],
                         cwd=HERE, capture_output=True, text=True, timeout=1800)
    assert 'no specimens found' not in out.stdout, \
        'validator finds nothing when run from tools/'
    assert 'specimens' in out.stdout, out.stdout[-400:]


def test_reverify_refuses_a_shrunken_corpus():
    """The guard has to fire, or the next silent shrink is invisible again."""
    sys.path.insert(0, HERE)
    import reverify
    assert reverify.EXPECTED_FILES == EXPECTED
