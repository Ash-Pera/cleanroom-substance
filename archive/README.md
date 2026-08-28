# archive/

Everything not reachable from `tools/render2`.

The cut line is `render2`'s transitive import closure, computed rather than guessed:
nothing inside that closure imports anything outside it, so the boundary is exact.

## What stayed

    tools/render2/          engine, filters, fx, model, ops + test_render2.py
    tools/                  assume corpus decompose disasm distance fxrender isa
                            manifest node_census record_layout sbsasm sbsruntime
                            standalone_parse transpile walk
    tools/                  costs.json  layouts.json  DISTINCT.txt  .hashcache.json
    DISTINCT.txt            the canonical 437-file corpus list
    corpus/ acg2/ tiny/ tiny2/ pairs/ pairs2/ pairs3/ pairs4/ pairs5/ pairs6/
                            every specimen directory the canonical list names
    *.md                    FORMAT-NOTES, SPEC, OPCODES, README, UNIFY-BOARD

Verified after the cut: `python3 tools/render2/test_render2.py` passes all three checks,
including `test_reference_agreement_does_not_regress` (5 channels, height mean 0.78587),
which needs the `Rokviz japanese fabric 8` specimen and its exported maps.

## What moved here

    root-scripts/   the pre-tools/ exploration phase (Aug 22). 25 scripts + lentable.json.
                    Imported by nothing, anywhere.
    root-data/      their derived intermediates: *.pkl, catalogue*, isa_census.txt,
                    structmatch.txt, harvest2.txt, *.bak, and the root __pycache__.
    tools/          41 modules outside the closure, plus `t`, `pt`, node_sizes.json
                    and the withdrawn 641-file DISTINCT list.
    specimens/      extracted{,2,3}/ x_Leaking004/ x_Metal009/ new_acg/ new_sbs/
                    new_opengameart/ sbsarx/ and the two loose .sbsar archives.
                    None appear in the canonical corpus list.

## Three things to know before you delete any of this

`derive_costs.py`, `derive_layouts.py` and `gen_layouts.py` are the only things that
regenerate `tools/costs.json` and `tools/layouts.json`, which render2 reads on every run.
The tables survive here as files; their *generators* are in this folder. Deleting the
archive makes those two tables permanent black boxes.

`render.py` is the renderer render2 replaces, and `test_filters.py` / `refcompare.py` /
`test_fx.py` are its harness — they import `render`, not `render2`. render2 is verified
solely by its own `test_render2.py`. That is a smaller net than the old renderer had, and
it is the whole net; `test_render2.py`'s own docstring says why the floors are there.

`walk.py:_corpus_files()` globs `extracted/`, `extracted2/`, `extracted3/` and `new_sbs/`
by relative path. Those directories are now under `archive/specimens/`, so that helper
returns fewer files than it used to — silently, because a missing glob root is not an
error. It feeds `validate_nodes()`, a self-check inside `walk.py` that nothing in
render2's path calls. Repoint it or delete it; do not trust a number it prints today.
