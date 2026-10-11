# cleanroom-substance

Notes and tools from a clean-room reverse engineering of Adobe Substance's compiled
material format — the `.sbsasm` assembly inside a `.sbsar` archive.

The goal is interoperability: enough of the format documented that Blender and other free
tools could read Substance materials without the proprietary engine.

## What is here

    SPEC.md                the specification: the container, records, parameters, FX-Maps,
                           the instruction set, and how to evaluate a graph — start here
    OPCODES.md             the bytecode instruction reference
    FORMAT-NOTES.md        the findings — ~64,000 lines, written as a lab notebook

`SPEC.md` and `OPCODES.md` are the distilled references: everything a reader needs to
locate and walk every region of the file by pointer arithmetic, with no fitted tables, and
what each filter computes. They state rules; each rule's evidence is a pointer to the
`FORMAT-NOTES.md` section that settled it. `FORMAT-NOTES.md` is the lab notebook behind
them — every measurement, failure and correction that produced those references.

    tools/                 the maintained tools — see tools/README.md
      sbsasm.py            the file model: records, layouts, edges, parameters, programs
      walk.py              the one structural primitive: the record/node mask-walk
      decompose.py         the structural walk of a record header — edges, size slot
      record_layout.py     the layout rule as one function — SPEC §7.3's width legend
      disasm.py            bytecode disassembler
      transpile.py         compiles a program's bytecode to Python source
      sbsruntime.py        runtime for transpiled programs, vectorised over numpy
      render2/             the renderer of record — every structural read comes from the walk;
                           render2/fxjit.py compiles its two hot loops with numba when numba
                           is installed, and the numpy paths run without it
      fxrender.py          FX-Map tree evaluation
      standalone_parse.py  header, interface block and value table
      sourcematch.py       a compiled field named by the value its own .sbs states

`tools/README.md` covers these in full, along with `corpus.py`, `manifest.py`,
`node_census.py`, `assume.py`, `distance.py` and `isa.py`.

    archive/               everything outside render2's import closure — see archive/README.md
      tools/provenance.py        the provenance exclusion predicate, as a re-runnable check
      tools/reverify.py          re-runs the notes' headline claims against the CURRENT corpus
      tools/audit_corpus.py      runs the model over a corpus and reports every gap
      tools/bit_census.py        every header bit per filter: set, placed, named, left
      tools/validate_corpus.py   structural checks against the .sbsar manifests
      tools/render.py            the earlier renderer, superseded by render2/
      tools/fxdisasm.py          walks an FX-Map tree and disassembles each node's program
      tools/extract_bitmaps.py   embedded images, and graph inputs by manifest uid
      tools/extract_shapes.py    filter 5's embedded vector artwork, as PNG or SVG
      tools/expand_instances.py  expands sub-graph instances using only in-file graphs
      tools/derive_legend.py     derives tools/legend.json — one KIND per header cell, which
                                 record_layout and decompose read on every run
      tools/derive_costs.py      the earlier FITTED cost model, kept as the independent one
      tools/test_*.py            the test suite; `./t` is the fast lane, `./pt` the parallel one
      tools/nativeguard.py       every reference pack rendered at its export size and scored
      tools/refsheet.py          our render beside the export, as a picture, per output
      tools/grooves.py           Bricks' mortar-joint and wheel-spoke widths against the export
      tools/conestash.py         keeps every record of one output's cone, to bisect a picture

The archive is a cut along `render2`'s transitive import closure, not a judgement about
what is useful: `derive_legend.py` and the test suite are both live dependencies that
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
  `<author v="Allegorithmic"` was dropped entire. **42 of the 142 paired sources** were
  excluded this way, counting sources distinct by content — the population
  `provenance.py`'s `paired_sources()` calls the rule's own. Before de-duplication the same
  rule drops **47 of 208**. The pairing is verified rather than assumed: each extracted
  `.sbsasm` is checked byte-for-byte against what the `.sbsar` beside it actually holds. The
  rule is deliberately over-broad — dropping whole files rather than individual graphs gave
  up 12 graphs that were the material author's own work.

  Both populations are legitimate and this README used to quote one while FORMAT-NOTES.md
  quoted the other, neither saying which. See FORMAT-NOTES.md, "The provenance counts were
  two populations and a coincidence" — the short version is that 140 was this file's
  *permitted* count and that file's *total*, which made three self-consistent triples look
  like a contradiction.

That exclusion has a measured cost, and the notes record it rather than hiding it. The 100
permitted paired sources declare exactly 24 filter names and all 24 are already assigned, so
the two remaining ids cannot be named from anything this project may read — filter 9 not at
all, and filter 5 only descriptively, from what its payload draws. **Four** occasions where the
boundary was brushed are disclosed as well: aggregate counts read from two excluded files before
it was noticed, eight archives extracted and scanned before the predicate was applied rather
than after, the declared filter names of three excluded sources printed alongside their
own provenance flag, and — 2026-09-03 — a probe that opened all 142 paired `.sbs` files,
the 42 excluded ones included, under a regex spelled `author="..."` which does not match the
rule's `<author v="Allegorithmic"`, so the intended filter was a silent no-op. It read only
whether a node kind was present; nothing was extracted, and its result was discarded in
favour of the established count. That one is the most instructive of the four, because the
exclusion did not fail — it was never applied, and it reported success either way. It is why
`archive/tools/provenance.py` exists as the predicate rather than as a regex retyped per
script, and re-typing it is the mistake to design out. No such observation is used, and all
are recorded in FORMAT-NOTES.md.

**A limit of the predicate, distinct from those four because nothing excluded was read.** The
rule classifies the file it is handed, and a `.sbs` declares dependencies: `sbs://…` names a
shipped-library graph, which is excluded, and whose nodes are nevertheless compiled into the
package beside it. `Simulator__Grid.sbs` is permitted, declares two such dependencies, and
holds 3 `fxmaps` nodes against its compiled sibling's 6 — so half the compiled records have
no declaration this project may read. A declared-vs-decoded comparison across that pair
cannot separate "we decoded it wrong" from "that node came from a dependency", and one such
finding was withdrawn on that ground rather than published. The permitted/excluded counts
above are unaffected; what is affected is what a *pairing* can prove. Pair only against a
source whose dependency closure is permitted, or compare per node rather than as multisets.

The **Provenance statement** at the top of `FORMAT-NOTES.md` is the auditable version of
all of this in one place. The exclusion predicate is a single string match and can be
re-run against any corpus: `archive/tools/provenance.py` is that check as code rather than a
description of one, and it is meant to run before a new corpus is measured, not after.

## Where the format stands

A dated summary, 2026-09-29. `SPEC.md` states the rules; the most recent `## STATUS` and
promotion sections of `FORMAT-NOTES.md` are the live record, and this section falls behind
them. Every figure below comes from a script and can be re-run.

### Decoding

`archive/tools/audit_corpus.py` over the corpus (437 distinct files, 903,616 records, 4.09 GB;
3.6 minutes):

    files parsed                       437 of 437
    filter identified                100.0%    23 filter ids; 21 named from the format's own
                                               permitted sources, filter 5 descriptively
                                               (`vectorshape`), filter 9 unnamed (5 records)
    record layout by mask-walk       100.00%   all but the 5 filter-9 records
    edge slots resolved              100.00%   1,302,710 slots
    size expression or first
      parameter read                  95.7%    the 4.33% missing are records with no parameter
                                               slot (correct, not misses); 34 genuinely unread
    record bytes interpreted         96.548%   program bodies included
      + every payload reader         99.535%   ramps, curves, vector strips, FX cells, pixels
      + the 2-byte alignment pad     99.990%   27,456 bytes left, 21,910 of them in `fxmaps`

**The format is one recursive mask-walk.** A structured object is `[mask][fields]`: the set
bits of a mask enumerate the fields present in a fixed order, and each field's width is a
constant of its kind — nothing stores an offset. The same primitive runs at three scales
(record header, FX-Map node, baked value), `SPEC.md` §6 states it, and it is the live decode
path: `tools/decompose.py` returns each record's edges, size slot and parameter slots from the
width legend (§7.3) alone. No fitted number is on the live path.

Decoded: the container and the 16-byte footer, the record directory, the tag's filter and
resolution fields, the edge map, the parameter words and the name legend (§13.4), the
instruction set (41 operations, `OPCODES.md`), embedded images, vector artwork, strings and
fonts, graph inputs by uid, the output-to-record table, and FX-Map trees — node kinds, entry
tables and program positions, all stated by the tags.

Not decoded: filter 9's name (the provenance rule blocks it, not the analysis); what the
inline FX programs' parameters are called (no permitted source sets the tag bits that would
say); `colorblending`'s slot; and 20,866 `fxmaps` bytes in FX cells the walk does not reach. The
per-row accounting behind every figure above is in `FORMAT-NOTES.md`.

### Rendering

`tools/render2/` renders all five reference packs end to end at the size their exports were
made at (Auras 512, Bricks 1024, the others 2048), and every channel is scored against the
engine's own export. How a reading is judged, in order: **look** at our render beside the
export (`refsheet.py`); then seed-free measurements (octave band power, levels, structural
censuses), because every `rand` placement differs from the engine's and puts a floor under
pixel correlation; then the per-row ratchet (`test_render2_reference_agreement_does_not_regress`,
52 entries × 3 grids, a frozen health census). Readings the file does not settle are
`assume.QUESTIONS` arms; their defaults, and why, are `SPEC.md` §13.9.

Current scores, every pack at its export size (`nativeguard.py`, mean over rows; 2026-10-10):

    pack             size   rows    corr     band    |dc|
    Chesterfield     2048    10    +0.945    0.808   0.017
    Auras             512     3    +0.877    0.991   0.004
    Bricks           1024    48    +0.636    1.052   0.033
    RoofTiles        2048     9    +0.570    0.779   0.036
    SandyStonePath   2048    20    +0.140    1.402   0.034

What lands: every pack's tile layout, mortar geometry, heights and normals sit on the export;
Chesterfield is above +0.89 on every row (its `metallic` to MAE 0.0004) and its height and AO
levels on the export (dc +0.001 / 0.000); Auras' ring is the export's purple with its level and
band on it (|dc| 0.004, band 0.99 -- `hsl.hue`, the lattice noise, 2026-10-10); Bricks 004's
emission is exact and its six-spoke wheels are the export's thin spokes (`fx.halfbell =
gaussian`, 2026-09-28).

What is visibly wrong, each with its section in `FORMAT-NOTES.md`:

  - **Bricks roughness on 002 / 004 / 005 is far too dark** (dc −0.31 to −0.40). The tree
    walk (`fx.subdivide = quadrant`) fixes the level and removes a faint canvas-sized ring from
    graphs 003–005, but costs colour elsewhere (Chesterfield's blue), so it is not the default.
  - **Bricks' round-tile mortar joints** were 0.75 of the export's width and half its depth;
    under `dirmotionblur.extent = floor` (a blur reaches at least one tag texel, default since
    2026-10-10) they sit on it, f/f 0.299 / 0.296 against 0.278 / 0.293, width 8 / 8. The
    reading is a candidate mechanism, not one read from a source, and it costs 003's normal z
    and RoofTiles' normal some top octaves.
  - **Tile faces carry round pits where the export has an irregular mottle**: which FX entries
    sum rather than take the max is not decided by any field read so far.
  - **SandyStonePath draws cog-shaped rosettes on every tile**: an edge detector amplifying
    the pixel-stepped flanks of our distance field. The fix is a more accurate distance
    transform, not an arm.
  - **RoofTiles lacks its fine wood grain**, which the export's height carries at small
    amplitude; its source in our graph is not yet found.

Speed (2026-10-09, numba): a native Bricks render is 145 s and the ratchet 156 s, its packs
rendered in parallel (`RATCHET_WORKERS=1` for serial). The numpy paths without numba were
about 1.8× slower when last measured (Bricks 287 s, 2026-09-28).

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
