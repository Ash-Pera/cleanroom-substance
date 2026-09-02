# tools

The finished tools. Each runs from the repository root, where the corpus lives:

    python3 tools/sbsasm.py <file.sbsasm> [record limit]
    python3 tools/sourcematch.py [--verify] [--pairs]

The archive cut — a boundary along `render2`'s transitive import closure, stated in
`archive/README.md` — moved everything else in this list to `archive/tools/`. They still run
from the repository root, and being archived is not a judgement about whether they are
useful: `derive_costs.py` regenerates a table `render2` reads on every run, and the test
suite is the test suite.

    python3 archive/tools/fxdisasm.py <file.sbsasm> <record index>
    python3 archive/tools/extract_bitmaps.py <file.sbsasm>
    python3 archive/tools/extract_shapes.py <file.sbsasm> [outdir] [--size 512] [--svg]
    python3 archive/tools/audit_corpus.py
    python3 archive/tools/validate_corpus.py
    python3 archive/tools/reverify.py
    python3 archive/tools/provenance.py

The test modules are pytest modules rather than scripts, and `conftest.py` is what puts
`tools/` on their path — running one directly as `python3 test_filters.py` does not import.
Use the lanes:

    cd archive/tools && ./t                            # fast lane, ~30s
    cd archive/tools && ./pt                           # parallel lane, one process per test
    cd archive/tools && python3 -m pytest -q test_filters.py

Below, any module not present in `tools/` is in `archive/tools/`. As of this writing that is
`attribute_outputs`, `audit_corpus`, `containment`, `derive_costs`, `derive_layouts`,
`expand_instances`, `extract_bitmaps`, `extract_shapes`, `fxdisasm`, `fxparams`,
`gen_layouts`, `provenance`, `refcompare`, `render`, `reverify`, `run_file`, `slot_rules`,
`standalone_parse_ref`, `validate_corpus` and every `test_*`.

## The model

    isa.py                opcode length rule, and the op ids the format actually uses
    standalone_parse.py   header, footer, interface block and value table
    disasm.py             bytecode disassembler
    sbsasm.py             the file model: records, layouts, edges, parameters, programs
    decompose.py          the one structural walk of a record header — edges, size slot,
                          program slots — that replaced the five layout special cases
    record_layout.py      the record layout rule, as one function; decompose reads its cost model
    slot_rules.py         every rule that decides a record's slot layout, each verified
    corpus.py             the canonical corpus list, deduplicated by CONTENT

`corpus.py` is the only place a corpus list is read. That is not tidiness: the list was
once corrected in one tool, documented in a second and left wrong in a third, and the
third was the one printing the headline figures. A correction written in prose does not
propagate to code, so both tools now call the same loader.

`sbsasm.py` is the one to read first. It is strict by default: where a record's layout is
known it reads it, and where it is not it returns `None` and counts it. `coverage()` classifies
every byte and reports what it cannot explain, so a wrong assumption surfaces as a number rather
than as a plausible-looking result.

**`Record.layout` and `edge_slots` now route through `decompose.py`, not a table.** One
structural pass — `[tag][w1?][image inputs][one slot per set class bit][one slot-group per w1
field][tail]`, reading only `record_layout`'s cost model — returns `(edges, size-or-program
slot)` for every record, and `_compute_layout` runs only as the fallback for the 5 unnamed
filter-9 records. This retired the five hand-tuned branches that used to decide layout
(`_walk_layout`, `_ruled`, `_pp_edges`, the SPECS-walk, and the fixed-shape/`ALT_LAYOUTS`
fallbacks). It is proven 0-diff against the independent `_compute_layout`+`_real_edges` model —
925,706 records, 925,701 agree, 0 disagree, 5 uncovered — and every consumer (`size_or_baked`,
`programs()`) is unchanged corpus-wide; 0b render-verified it at 0 pixel difference across all
affected filters. One caveat, stated in `decompose.py`'s docstring: because `edge_slots` and
`Record.layout` now *call* decompose, validating decompose against them is circular — check it
against `_compute_layout`/`_real_edges`, the raw words, or the render. **Parameters are on the
walk too now, and `layouts.json` is drained.** `WALKED_PARAMS` covers every filter in
`PARAM_SPEC`, `levels` included, so `_parameters_paired` has no caller and emptying `LAYOUTS`
or `LAYOUT_MASK` changes 0 of 160,672 readings — against 9.272% before, which was exactly the
`levels` share. `_parameters_paired` stays as the independent second model, the role
`_compute_layout` plays for `decompose`. What decided `levels` was source containment, not the
render: 82 of 93 declared nodes recovered against the memo's 69 over 21 permitted paired
sources. See FORMAT-NOTES.md "Unified walk" / "Better decoder" and
"`levels` goes on the walk".

Two readings sit side by side, deliberately:

* `Record.parameter` is the **strict** one - the first slot after the record's inputs,
  found through its layout. It holds the record's **output size expression** in 91.3% of
  records (`Record.output_size` evaluates it, agreeing with the tag in 99.81%) and a baked
  filter parameter in the rest; the layout key states which, at 100.00%. It is not "the
  main parameter", which is what earlier notes called it. `Record.programs` returns every
  program the record's slots name; a record can carry up to five, and the two-scalar filters
  routinely carry two. This is what a reader should bind to.

  That claim used to be false for the 5.6% of records whose layout key `derive_layouts.py`
  dropped: those fall through to a hand-written default naming a single slot, so a second
  program could not come back however plainly its slot named one. `Record.classified_programs`
  now reads those records directly — `words[s] + 52` passing `valid_program`, bounded by the
  header end the record states — recovering 11,557 programs at 19.5% of dropped-key records
  against a 0.12% control on records the table does know. `fxmaps` is excluded; see the
  method's docstring for why. **Re-taken after the slot rule; it read 4.6% / 9,825 / 20.77%
  / 0.25% before.** The 4.6% moved on corpus drift alone — `layouts.json` has not been
  regenerated since 2026-08-24 and the corpus has grown by 7,942 records since. The control
  is NOT attributed to the slot rule: running the pre-slot-rule loop on today's tree gives
  0.13%, so almost all of the fall from 0.25% happened earlier, under changes this note
  cannot separate. What did NOT survive re-measurement is the framing: those
  programs now come back either way, because `programs()`’ own slot scan got the same skip
  and is a superset of this method. Stub `classified_programs` to `[]` and 0 program sets
  change over 903,616 records (4 orderings do). It is the measured statement of the
  predicate, not the thing that supplies the programs.

  **Only a slot can name a program, and the walk states which words are slots.** Both scans
  — `programs`' and `classified_programs`' — skip the record's own header words (`hdr` from
  `decompose`: w0, plus w1 where the shape carries one, so 1 for `uniform` and not a
  hardcoded 2) and its input-edge slots. An edge's word is a record index and a record's
  offset is `index + 52`, the same universal skew a program pointer uses, so `edge_word + 52`
  is the offset of the record the edge names and a program predicate has nothing to say about
  it. This rule replaced `Assembly.code_lo` as a floor inside `valid_program`, which was
  doing the same job by address and getting the version-2 prologue wrong; it drops 423
  program attributions corpus-wide, 401 of them addresses another record in the same file
  still names properly and the remaining 22 addresses that lie physically inside a *different*
  record than the one claiming them.
* `Assembly.referenced_programs()` is **permissive** - every program some word in the file points
  at. It exists because FX-Map records reach programs through their tree and the version-2
  prologue holds programs no record names, and both looked like undecoded regions until this was
  measured. It is for coverage accounting, **never for ISA statistics**: any opcode census or
  operand analysis must run over strictly-named programs. See FORMAT-NOTES.md for what happens
  when it does not.

`Assembly.outputs()` returns `(uid, format, grayscale, record index)` for each graph output. The
output table is one 8-byte entry per output, immediately after the record directory in both file
layouts. Earlier sections of the notes record this attribution as structurally absent; it is not.

`Assembly.program_span(p, hi, slack)` is **the single definition of "is a program"**, and
`valid_program` is one call to it. They were two implementations for a long time and drifted
apart on four axes — 4-byte alignment, the instruction-count cap, the `while` opcode's
trailing operands, and the `code_lo` floor — disagreeing on 8,310 addresses corpus-wide.
Do not add a check to one of them.

**Reading an immediate goes through `disasm.immediate`, `disasm.uid` or `disasm.floats`.**
Immediate-carrying opcodes have two forms differing by `0x0400`, the longer emitting a 2-byte pad
when the instruction lands at 0 mod 4 so the immediate stays 4-aligned. Splicing the operand
tokens directly joins halves of two different words.

`Record.fx_tree()` walks an FX-Map's linked node chain. It stops at an unknown node header rather
than guessing the node's size, because guessing is how earlier walks wandered into bytecode and
invented node types.

It returns nothing for 34.2% of `fxmaps` records, and that is **not** a gap. Slot 2 is a
discriminated union: it addresses a node chain in 65.8% of records and the parameter table
directly in the other 34.2%, and the two figures partition exactly. Those records have no node
because their FX-Map has no `addnode` — `paramset`, which is 69 of 155 nodes across the
ground-truth sources, compiles to no tree node at all. Use `fx_walk()`, which follows whichever
structure the root addresses; `fx_tree()` alone sees only the chain half.

Counting nodes from either one wants **distinct offsets**: both yield once per program slot, so a
`0x1AB` node (two programs) is yielded twice at the same offset.

`Assembly.strings()` reads the `text` filter's embedded strings from the head of the resource
segment.

`Record.vector_shape()` decodes filter 5's payload: a triangle strip of 16-bit normalised
(x, y) vertices, 140 of 140 records. `Record.vector_faces` drops the degenerate triples that
join one sub-strip to the next. This is what identifies the filter - rasterising the faces
draws the road markings, filigree ornaments, snowflakes and lettering the materials carrying
it are named for. The id is labelled `vectorshape` in `PROJECT_LABELS`, not `FILTERS`'
usual sense of a name: the permitted sources' 24 filter names are all assigned already, so
no source this project may read names filter 5.

## Extraction

    extract_bitmaps.py    embedded images, and graph inputs by manifest uid
    extract_shapes.py     filter 5's embedded vector artwork, as PNG or SVG
    fxdisasm.py           walks an FX-Map tree and disassembles each node's program
    expand_instances.py   expands sub-graph instances using only in-file graphs

## Rendering

    transpile.py          compiles a program's bytecode to Python source
    sbsruntime.py         runtime for transpiled programs, vectorised over numpy
    run_file.py           evaluates every program in a file through one shared cache
    render.py             walks a record graph in index order and evaluates what it can
    render2/              the same, rebuilt so every structural read comes from the walk

`render.py` implements ten filters: `bitmap`, `pixelprocessor`, `blend`, `transformation`,
`levels`, `uniform`, `directionalwarp`, `gradient`, `curve` and `dirmotionblur`. That is
not enough to render a real material, and FORMAT-NOTES.md measures how far short it falls
and which filter gates the rest.

`render2/` is **the renderer of record**, and the difference from `render.py` is not tidiness. `render.py` asks a different
question in every filter branch -- the fitted `LAYOUTS` memo here, a value probe over
`Record.programs` there, a hand-stated slot offset in a third -- and `render2` asks
`decompose` ONCE per record, in `model.View`, and every filter reads the answer by name.
The only table left is a NAME legend, (filter, field) -> name, which cannot go stale when a
neighbouring field appears or disappears because it never mentions a position.

    python3 tools/render2 <file.sbsasm> [--dim 256] [--out DIR] [--score DIR]

`--score DIR` pairs each declared output against the package's own exported maps by the
manifest's usage name. On `Rokviz japanese fabric 8` -- the specimen with no exposed colour
parameter, so a colour mismatch cannot be an author's tweak -- it renders all 70 records
and scores basecolor +0.976 / +0.949 / +0.907, roughness +0.958, ambient occlusion +0.970
and height at an MAE of 0.0004, against -0.926 / +0.331 / +0.861, -0.475, -0.331 and
+0.047 for `render.py`. Two readings account for it, both the walk answering where
something else used to: `levels` parameters taken from the field enumeration rather than
the memo, and an FX-Map emission count taken from the placement program on the 0.21% of
records whose iterator contradicts it. FORMAT-NOTES.md has the measurements, the census
behind the narrow trigger, and the one channel of one package where the memo still wins.

`render.py` stays, as the independent model to check `render2` against -- the role
`_compute_layout` plays for `decompose`. On `Chesterfield` at `max_dim` 256 the two agree
to four decimals on `normal`, `height`, `metallic` and `AO`; `roughness` improves by 0.055
and `basecolor` is produced where it was not. Two implementations of one thing drift; two
that are known to differ, with the difference measured, do not.

`run_file.py` exists because `cache_read` raises unless a caller threads one cache through
a whole file. Programs are not independent: a record's program can read what an earlier
record's program wrote.

## Deriving the tables

    derive_layouts.py     derives layouts.json: (filter, class, layout bits) -> slot roles
    derive_costs.py       derives costs.json: each filter's slot costs from the corpus
    gen_layouts.py        why layouts.json CANNOT be regenerated from the slot rule
    node_census.py        harvests fx-tree node cells and derives the node size law
    fxparams.py           re-derives the FX-Map entry parameter names from sources
    containment.py        identifies a filter id by containment, with its control

Each of these writes or justifies a table the model reads. `gen_layouts.py` is the odd one:
it exists to record a negative result, that the mask in `layouts.json`'s key drops the
parameter bits the slot rule needs, so no rewriting of entries can express the rule.

## Checking

    test_transpile.py     the sRGB round-trip -- see below
    test_filters.py       gradient, curve and dirmotionblur, with an independent check
    test_fx.py            the FX-Map decode: coverage, tag vocabulary, slot roles,
                          the 0x1B branch, one-ISA, no loops, the node/table dataflow,
                          and the source-side check on `FX_LOWERING` -- see below
    audit_corpus.py       runs the model over a corpus and reports every gap
    validate_corpus.py    structural checks against the .sbsar manifests
    attribute_outputs.py  cross-checks the output table against the manifest's alteroutputs
                          relation: 98.20% agreement over 39,855 (input, output) pairs
    refcompare.py         rendered outputs against the engine's OWN exported maps --
                          the only ground-truth check in the repository
    test_tables.py        knocks out each table in turn -- a table that changes no
                          reading when emptied is not carrying the decode it documents
    test_corpus_discovery.py
                          corpus discovery must not depend on where the command was typed
    reverify.py           re-runs FORMAT-NOTES.md's headline claims against the CURRENT
                          corpus, so a settled figure cannot quietly go stale
    provenance.py         the provenance exclusion predicate, as a re-runnable check
    sourcematch.py        a compiled field named by the value its own .sbs states
                          rather than a description of one
    test_standalone_parse.py
                          the 59x parser rewrite against the reference it replaced, full
                          result dict AND exception compared, over the whole corpus
    standalone_parse_ref.py
                          the pre-optimisation parser, kept so that check has something
                          to compare against

`standalone_parse_ref.py` used to be kept "so the check can be repeated", and nothing
repeated it -- the reference sat here for the length of that claim with no code comparing
the two, so the sentence described an intention rather than a check. `test_standalone_parse.py`
is the check. It compares the exception as well as the result, since a fast path that
starts raising on a file the reference reads would otherwise pass unnoticed.

`refcompare.py` is the only check here that scores a render against ground truth rather
than against a distribution. Several corpus packages ship the texture maps the engine
exported beside the `.sbsar` that produces them, and `manifest.output_names` pairs each
declared output to its map by USAGE (basecolor, normal, roughness ...), which is an exact
lookup rather than a filename guess. `assume.py` records why this was unusable for so
long: our refusals to guess were what blocked the reference renders, with `blur`'s
withdrawn intensity fallback the top blocker at 70 records.

Read its docstring before using it. Two traps in there produced confident wrong readings:
the AO/height/metallic/roughness maps are 16-bit, so `convert('L')` saturates them and
makes the engine's own exports look like blank white placeholders; and averaging a normal
map's channels flattens it by construction, since (0.5, 0.5, 1.0) is nearly constant under
a channel mean. Today it reports a baseline, not a validation -- means agreeing to four
decimals with spatial variation 5.4x too small.

`provenance.py` is the one to run against a new corpus before measuring anything with it.

`sourcematch.py` is the arbiter for a naming question: it reads a package's `.sbs`, reads the
compiled twin beside it, and reports every location a stated value lands in. Four of the
legend's names were derived this way by hand before the tool existed, and `--verify` re-derives
all nine of those rows -- which is the only way to tell a clean run from a broken parser, since
both report nothing. Its binding limit is stock: 74 sources ship here and TWO have a compiled
twin, so it can say nothing at all about `blur`, `warp`, `dirmotionblur`, `pixelprocessor`,
`sharpen`, `shuffle` or `dyngradient`.
The exclusion rule in README.md is a single string match, and this applies it and reports
what it drops; the discipline is that it runs BEFORE any measurement, not after.

## The FX-Map decode

`Record.fx_walk()` returns an FX-Map as two connected halves. The chain of nodes --
`addnode` (0x18B), `markov2` (0x89) and five more headers -- computes into a shared slot
frame; the `paramset` table then reads that frame and computes each pattern's size, offset,
rotation and emit condition. The connection is measured: slots at index 64 and above are
read-and-written within one file 88.1% of the time against a 0.0% cross-file control.

The entries are a LINKED LIST. Each entry stores a pointer to the next one -- the header slot
reaching furthest forward, past the entry's own inline program -- and the walk follows it
rather than stepping a tabled stride. The entry ends at its inline program, whose length the
program states in its own first word (a `u16` instruction count), so the extent is structural,
not a per-tag constant. `FX_ENTRY` was a fit of that pointer's distance and is drained: which
of an entry's words hold programs comes from `fx_entry_layout`'s bit-walk (nibble 8) or the
disjoint-span scan (nibble 9/B nodes), and `FX_ENTRY_PROGS` is likewise drained to a census.
Do not step 8 bytes and do not read the length from a table -- both were wrong.

Where a tag names no program slots the program is stored INLINE, and its position is a
layout fact rather than a table lookup: `fx_entry_layout` puts it after the parameters, at
`4 x (the first slot the layout does not use)`. That rule replaced `FX_TABLE`, a 22-entry
lookup recording the same offsets. Over the whole corpus the two never once name a
different address -- 2,620 agreements, 0 disagreements -- and asking the layout instead
finds 176 programs on tags no table covered, none of which lies inside another program's
byte span. `FX_PAYLOAD_PROG` is what remains of the table: the two tags the rule gets
wrong, one because its payload word points at entry+12 rather than entry+8, one because
its program sits a slot past the predicted position for a reason not yet known.

`test_fx.py` is the regression guard, and its docstring records which mutations each check
catches. The first version of it caught none of them.

`FX_LOWERING` maps the FX-Map source language onto this ISA, and it is the one table
checked against `.sbs` SOURCES rather than against compiled files alone. A node's program
is its parameter's function graph -- `addnode` declares `numberadded` -- so the pair is
identified and the multisets compare directly: 19 equations over the 8 permitted sources
that contain an FX-Map, all 19 reproducing. The provenance exclusion runs by construction
there, the file list coming from `provenance.audit()` before anything is measured.

The matching rule is one-to-one consumption, not membership, and that distinction is the
whole test. `ie_pcloud` alone offers 217 `addnode` programs; against a pool that size,
re-pointing `lr` at `and` still leaves 18 of 19 equations "reproducing". Under consumption
all ten bindings probed are caught.

## The one thing that is actually tested

Nearly every claim in this project is a distribution match: a decode is believed because the
numbers it produces line up with something independently known. `transpile.py` is the exception.
A program's bytecode *is* its semantics, so a program whose algorithm is known can be transpiled,
run, and compared against the closed form.

`test_transpile.py` does that for the sRGB transfer function in both directions -- the encode in
`LGMLtools__sRGB_colorchart` and the decode in `DLG-Tools__Embroidery_Legacy`, the second a
specimen the instruction table was not built from. Maximum deviation 5.22e-08 and 1.19e-07,
which is float32 rounding. It also covers the immediate decoding, where two bugs have been found.

It runs under `pytest` or on its own, and **skips rather than fails** when a specimen is absent,
since the corpus is not in this repository. Point `SBS_CORPUS` at an unpacked collection.

The file records what the tests catch and what they cannot, measured by mutating the operation
table one entry at a time. `lteq -> lt`, `sub -> add`, `div -> mul`, `ln -> exp` and `exp2 -> exp`
are all caught; `gt -> gteq` is not, because sRGB is continuous at its threshold and both branches
meet there. Every entry in that table can now be mutated meaningfully: `0x2C: "not"` named
an opcode that does not exist -- zero occurrences in 30,932,107 instructions, no row in
OPCODES.md -- and has been removed. The real `not` is `0x1C`, which has its own branch.

Two specimens is thin evidence for a 41-operation ISA, and the coverage figure --
99.958% of 644,282 programs -- measures the table's completeness, not whether the output computes
the right thing.

## Not here

The exploratory scripts that produced individual findings are left in the repository root.
They are one-off analyses, not maintained interfaces, and several encode assumptions that later
sections of FORMAT-NOTES.md correct.
