"""The repository root, found rather than counted -- and the live tools/ on sys.path.

Every script in this directory used to resolve the root the same way:

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

which is "up two from this file", and was correct while these scripts lived in tools/.
The archive cut moved them to archive/tools/, one level deeper, and that expression did
not start failing -- it started returning archive/, a directory that exists and contains
no specimen. Six tools then globbed an empty corpus and reported nothing wrong: the
validator printed "no specimens found" and exited, and reverify checked 3 files of 438.

The same cut separated these scripts from the modules they import. Each one inserted its
OWN directory to find `sbsasm` and friends, which worked when that directory was tools/.
Now `tools/` is elsewhere and the insert finds nothing, so the fix has two halves.

A directory count cannot notice it moved. A marker can, so this walks up for one the root
actually has and raises if it runs out of parents -- the failure the count should have been.
"""
import os
import sys

MARKER = 'SPEC.md'


def find_root(start=None):
    """The nearest ancestor directory holding MARKER. Raises if there is none."""
    d = os.path.dirname(os.path.abspath(start or __file__))
    while True:
        if os.path.exists(os.path.join(d, MARKER)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise RuntimeError(
                'repository root not found above %s: no ancestor holds %s'
                % (start or __file__, MARKER))
        d = parent


ROOT = find_root()
TOOLS = os.path.join(ROOT, 'tools')

# The cut split the specimen directories in two. The canonical corpus -- pairs*, corpus/,
# tiny*, acg2 -- stayed at the root; the packs outside the canonical list (new_sbs,
# new_opengameart, new_acg, extracted*) moved under archive/specimens/. A tool that globs
# by directory NAME therefore has two places to look, and which one holds a given name is
# not something the name says. Search both and let the name miss in one of them.
SPECIMENS = os.path.join(ROOT, 'archive', 'specimens')
BASES = (ROOT, SPECIMENS)


def add_tools_to_path():
    """Put the maintained tools/ on sys.path. Idempotent; safe to call from any script."""
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    return TOOLS
