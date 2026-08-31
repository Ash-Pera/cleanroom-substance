# cleanroom-substance

Notes and tools from a clean-room reverse engineering of Adobe Substance's compiled
material format — the `.sbsasm` assembly inside a `.sbsar` archive.

The goal is interoperability: enough of the format documented that Blender and other free
tools could read Substance materials without the proprietary engine.

## What is here

    SPEC.md                a clean ~4-page specification of the whole format — start here
    OPCODES.md             the bytecode instruction reference
    FORMAT-NOTES.md        the findings — ~43,000 lines, written as a lab notebook

`SPEC.md` and `OPCODES.md` are the distilled references: everything a reader needs to
locate and walk every region of the file by pointer arithmetic, with no fitted tables.
`FORMAT-NOTES.md` is the lab notebook behind them — every measurement, failure and
correction that produced those references.

    tools/                 the maintained tools — see tools/README.md
      sbsasm.py            the file model: records, layouts, edges, parameters, programs
      walk.py              the one structural primitive: the record/node mask-walk
      decompose.py         the structural walk of a record header — edges, size slot
      record_layout.py     the layout rule as one function; decompose reads its cost model
      disasm.py            bytecode disassembler
      transpile.py         compiles a program's bytecode to Python source
      sbsruntime.py        runtime for transpiled programs, vectorised over numpy
      render2/             the renderer of record — every structural read comes from the walk
      fxrender.py          FX-Map tree evaluation
      standalone_parse.py  header, interface block and value table
      sourcematch.py       a compiled field named by the value its own .sbs states

`tools/README.md` covers these in full, along with `corpus.py`, `manifest.py`,
`node_census.py`, `assume.py`, `distance.py` and `isa.py`.

    archive/               everything outside render2's import closure — see archive/README.md
      tools/provenance.py        the provenance exclusion predicate, as a re-runnable check
      tools/reverify.py          re-runs the notes' headline claims against the CURRENT corpus
      tools/audit_corpus.py      runs the model over a corpus and reports every gap
      tools/validate_corpus.py   structural checks against the .sbsar manifests
      tools/render.py            the earlier renderer, superseded by render2/
      tools/fxdisasm.py          walks an FX-Map tree and disassembles each node's program
      tools/extract_bitmaps.py   embedded images, and graph inputs by manifest uid
      tools/extract_shapes.py    filter 5's embedded vector artwork, as PNG or SVG
      tools/expand_instances.py  expands sub-graph instances using only in-file graphs
      tools/derive_costs.py      regenerates tools/costs.json, which render2 reads on every run
      tools/test_*.py            the test suite; `./t` is the fast lane, `./pt` the parallel one

The archive is a cut along `render2`'s transitive import closure, not a judgement about
what is useful: `derive_costs.py` and the test suite are both live dependencies that
happen to sit outside it. The pre-`tools/` exploratory scripts are in `archive/root-scripts/`.
They are one-off analyses rather than maintained interfaces, and several encode assumptions
the notes later correct.

## What is not here

**The corpus.** The analysis used freely distributed files — CC0 materials from
[ambientCG](https://ambientcg.com) and `.sbs` sources published by their authors on GitHub
under MIT, CC0 and MPL licences. Those belong to their authors and are not republished here.
Point the tools at your own collection.

## Provenance discipline

Analysing freely distributed `.sbsar` files for interoperability is the legitimate activity
this project is built on. Two things were excluded throughout:

* **Adobe's Substance engine, in any form** — no binary was run, disassembled or inspected.
* **Adobe's bundled library `.sbs` sources.** Several material packs redistribute them.
  Enforced mechanically, before any measurement: a source file containing
  `<author v="Allegorithmic"` was dropped entire. 47 of 187 paired sources were excluded
  this way, over a pair set whose pairing is verified rather than assumed: each extracted
  `.sbsasm` is checked byte-for-byte against what the `.sbsar` beside it actually holds. The rule is deliberately over-broad — dropping whole files rather than
  individual graphs gave up 12 graphs that were the material author's own work.

That exclusion has a measured cost, and the notes record it rather than hiding it. The 140
permitted paired sources declare exactly 24 filter names and all 24 are already assigned, so
the two remaining ids cannot be named from anything this project may read — filter 9 not at
all, and filter 5 only descriptively, from what its payload draws. Three occasions where the
boundary was brushed are disclosed as well: aggregate counts read from two excluded files before
it was noticed, eight archives extracted and scanned before the predicate was applied rather
than after, and the declared filter names of three excluded sources printed alongside their
own provenance flag. No such observation is used, and all are recorded in FORMAT-NOTES.md.

The **Provenance statement** at the top of `FORMAT-NOTES.md` is the auditable version of
all of this in one place. The exclusion predicate is a single string match and can be
re-run against any corpus: `archive/tools/provenance.py` is that check as code rather than a
description of one, and it is meant to run before a new corpus is measured, not after.

## Where the format stands

Measured over 435 specimens, 895,674 records, 4.09 GB. These are the last **full** audit and
are a dated snapshot, not a live figure: the corpus has since settled at 437 (438 before one
withdrawal), and the attribution fixes of 2026-08-28 — the pinned base region, `distance`'s
double-charged mask input — landed after this table was taken. Re-run `audit_corpus.py` to
refresh it; the ranking in FORMAT-NOTES.md's most recent status section is the current one.

    filter identified              99.9%
    size expression or first
      parameter read               95.6%
    edge slots resolved          100.00%
    record bytes interpreted       92.5%
    record layout by mask-walk     99.97%  (only vectorshape, provenance-walled, left)

**The format is one recursive mask-walk.** A structured object is `[mask][fields]`: the set
bits of a mask enumerate which fields are present in canonical order, and each field's width
is a constant of its kind — nothing stores an offset. The same primitive runs at three
scales (record header, FX-Map tree node, baked value width), and `walk.py` implements it
once. This replaced a memorised layout table: a walk reproduces record layout for 99.97% of
the corpus with no per-record lookup and no fitted floats, and fails loudly rather than
guessing when a spec is wrong. `SPEC.md` §6 states it.

That walk is now the **live decode path**, not just a check that could reproduce the table.
`Record.layout` and `edge_slots` route through one structural pass (`tools/decompose.py`),
which returns each record's edges and its size-or-program slot from the cost model alone; the
five hand-tuned layout branches it replaced run only as the fallback for the 5 unnamed
filter-9 records. It is proven 0-diff against the independent table-based model (925,706
records, 925,701 agree, 0 disagree, 5 uncovered) and render-verified at 0 pixel difference.
The one decision still on a fitted table is **what baked parameters one filter carries**.
`named_parameters` routes `blend`, `fxmaps`, `dirmotionblur` and `directionalwarp` through the
walk; `levels` alone still reads the `LAYOUTS` memo, and that is 9.3% of records. The walk's
placement for it is the better-evidenced one — source containment recovers 91 of 91 declared
values at the slots the walk names, and the memo reads a parameter out of an input-edge slot
1,844 times where the walk never does — but the render holds it back, and honestly so: routing
it costs one package's basecolor on two independent measures, correlation and amount of
structure. That veto is narrow rather than general. Across all five reference packs the switch
moves 9 channels of 27, and on a different package it is the memo that comes out
anti-correlated. The memo also cannot see a sixth `levels` field that the cost model declares,
because its key was fitted to the five parameters known when it was fitted. Edges, size
expression and program positions are off the tables; one filter's parameter *values* are the
honest remaining exception.

The last line of the audit table is the one to read. Earlier versions of this table reported "unexplained
bytes 0", which was circular: `coverage()` marks a whole record extent as accounted for
the moment the record is enumerated, and the directory is a sorted partition of the body,
so every body byte is inside some record by construction. That measured the directory's
completeness, not the segmenter's. 92.5% counts only bytes the model can put a meaning to.

Decoded: the container, the record directory as a sorted extent map, the tag's filter and
resolution fields, 22 of 23 filter ids — 21 named from the format's own sources and
confirmed by one uniform presence test with controls, and filter 5 identified by decoding
and rendering its payload but labelled descriptively, because no permitted source names
it — the edge map, the parameter word for `blend`
(including `blendingmode`), the instruction set at 41 operations, the embedded bitmap format,
graph inputs by uid, the system variables, and the output-to-record attribution — a table
between the directory and the first record that five earlier approaches had all missed,
naming each output's record in 3,249 of 3,249 with a colour-mode check it could have failed
and did not (`Assembly.outputs()`).

Not decoded: one filter id — filter 9, 5 records, where it is the provenance rule and not
the analysis that blocks the name — and what most filter parameters mean once their
record and program are known, which is the gap that actually blocks a renderer. The
version-2 prologue is no longer on this list: it is a constant 72-byte preamble of
programs, one of which binds the graph's random seed. Neither
are FX-Map records as a whole. Entry boundaries, entry lengths and program positions are
all stated by the tag; four node headers are bound to source node kinds on 8 of the 8
permitted files containing an FX-Map, with no off-diagonal cell of that confusion matrix
reaching 7; and FX programs run the same instruction set as the rest of the format, minus
loops and cache writes. What stays open is naming the inline programs' parameters — 98% of
them open with `inputref`, and no permitted source sets the tag bits that would say which
parameter each one is. That is the provenance rule again rather than the analysis.

See FORMAT-NOTES.md's most recent status section for the
current ranking; this paragraph is a summary and falls behind it.

## On the notebook style

`FORMAT-NOTES.md` records failures, retractions and corrections alongside results, with the
measurement that settled each one. Several sections exist only to record that a plausible
finding was wrong and how it was caught. That is deliberate: in a format with no
documentation, the tests that discriminate are worth more than the conclusions, and a
conclusion without its test is not reusable.

## Licence

Split deliberately, because the code and the documentation are trying to do different things.

    tools/, archive/       MPL-2.0        see LICENSE
    SPEC.md, OPCODES.md,
      FORMAT-NOTES.md      CC-BY-4.0      see LICENSE-DOCS

The documentation is permissive on purpose. The goal of this project is independent
reimplementations in other people's tools, and a copyleft specification works against
that — an implementer should never have to wonder whether reading `SPEC.md` makes their
decoder a derivative work. Attribution is the only condition.

The code is MPL-2.0, which is copyleft per FILE rather than per program. Improvements to
these files stay open, but the files can be linked into projects under other licences —
including both GPL projects like Blender and permissively licensed ones like Godot, which
a whole-program copyleft would have shut out. Given that interoperability with exactly
those tools is the point, that is the trade this project wants.

`archive/specimens/sbsarx/` carries its own MIT licence and is unaffected.

Nothing here licenses the corpus: those files belong to their authors, are not
redistributed in this repository, and arrive under their own terms.
