#!/usr/bin/env python3
"""The optimised standalone parser must agree with the reference it replaced.

FORMAT-NOTES.md records a 59x rewrite of `standalone_parse.py` and says equivalence "was
checked, not assumed" -- 435 identical, 0 different, 0 differing exceptions -- and that
"the original is kept as `standalone_parse_ref.py` so the check can be repeated".

Nothing repeated it. The reference sat in the directory for the length of that claim with
no code comparing the two, so the sentence described an intention rather than a check, and
an optimisation that drifted would have been caught by nobody. This is that check.

Both halves matter. Comparing only the successful parses would let the fast path start
raising on a file the reference reads, so the EXCEPTION is compared too -- a file both
refuse for the same reason agrees; a file one refuses and the other reads does not.

SKIPS rather than fails when the corpus is absent -- the corpus is not in this repository.

    SBS_PARSE_FILES=0 python3 -m pytest test_standalone_parse.py   # 0 means all of it
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import standalone_parse                                              # noqa: E402
import standalone_parse_ref                                          # noqa: E402

LIMIT = int(os.environ.get('SBS_PARSE_FILES', '120'))


def _outcome(mod, path):
    """(result, exception name) -- an exception is an answer, not a reason to skip."""
    try:
        return mod.parse(path), None
    except Exception as exc:                                  # noqa: BLE001
        return None, type(exc).__name__


def test_optimised_parser_matches_the_reference():
    """Every corpus file must parse identically under both, exceptions included."""
    paths = corpus.paths()
    if LIMIT:
        paths = paths[:LIMIT]
    if not paths:
        print('SKIP test_optimised_parser_matches_the_reference: no corpus')
        return
    same, differ, raised = 0, [], 0
    for p in paths:
        fast = _outcome(standalone_parse, p)
        slow = _outcome(standalone_parse_ref, p)
        raised += fast[1] is not None
        if fast == slow:
            same += 1
        else:
            differ.append((os.path.basename(p), fast[1], slow[1]))
    print('standalone parsers agree on %d of %d files (%d refused by both)'
          % (same, len(paths), raised))
    # NOT just `not differ`: a comparison that silently skipped files would pass. The
    # invariant is that EVERY path offered got compared, which holds at any corpus size --
    # an arbitrary floor here (it was 20) false-fails on a small corpus, which is a test
    # reporting on its own invocation rather than on the parsers.
    assert same + len(differ) == len(paths), \
        'compared %d of %d paths' % (same + len(differ), len(paths))
    assert not differ, 'parsers disagree on %d files, first: %r' % (len(differ), differ[:3])


if __name__ == '__main__':
    test_optimised_parser_matches_the_reference()
