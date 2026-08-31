"""Session-wide Assembly cache for the test suite.

A dozen tests sweep the corpus, and each used to re-parse all 437 files and re-run
every per-record probe from scratch -- the suite crossed ten minutes on repeated work
whose inputs cannot change mid-run. Assemblies are read-only in practice and their
data is mmapped (the OS page cache holds the bytes once), so sharing parsed instances
across tests changes nothing but the clock.

This swaps each test module's `Assembly` name for `Assembly.cached` after collection.
Tests that never sweep are unaffected; tests that construct via keyword or subclass
would bypass the cache and still be correct, just slower.
"""
import os
import sys

# The archive cut moved these tests out of the directory holding the modules they test:
# `sbsasm` and its neighbours stayed in tools/, the suite came here, and nothing put the
# two back in touch. Every module below errored at collection until this line existed.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))

import sbsasm


# Modules that measure COUNTERFACTUALS -- patch a table, re-read, compare -- must not
# get cached instances: a memoized Record answers from before the patch, and every
# table looks dead. test_tables exists precisely to catch dead tables, and the cache
# made it report three false ones within an hour of landing.
NO_CACHE = {'test_tables'}


def pytest_collection_finish(session):
    for name, mod in list(sys.modules.items()):
        if name in NO_CACHE:
            continue
        if name.startswith('test_') and getattr(mod, 'Assembly', None) is sbsasm.Assembly:
            mod.Assembly = sbsasm.Assembly.cached
