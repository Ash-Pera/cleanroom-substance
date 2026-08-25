# tools

The finished tools. Each runs from the repository root, where the corpus lives:

    python3 tools/sbsasm.py <file.sbsasm> [record limit]
    python3 tools/fxdisasm.py <file.sbsasm> <record index>
    python3 tools/extract_bitmaps.py <file.sbsasm>
    python3 tools/extract_shapes.py <file.sbsasm> [outdir] [--size 512] [--svg]
    python3 tools/audit_corpus.py
    python3 tools/validate_corpus.py
    python3 tools/test_transpile.py
    python3 tools/test_filters.py
    python3 tools/test_fx.py
    python3 tools/test_tables.py
    python3 tools/reverify.py
    python3 tools/provenance.py

## The model

    isa.py                opcode length rule, and the op ids the format actually uses
    standalone_parse.py   header, footer, interface block and value table
    disasm.py             bytecode disassembler
    sbsasm.py             the file model: records, layouts, edges, parameters, programs
    record_layout.py      the record layout rule, as one function
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

Two readings sit side by side, deliberately:

* `Record.parameter` is the **strict** one - the first slot after the record's inputs,
  found through its layout. It holds the record's **output size expression** in 91.3% of
  records (`Record.output_size` evaluates it, agreeing with the tag in 99.81%) and a baked
  filter parameter in the rest; the layout key states which, at 100.00%. It is not "the
  main parameter", which is what earlier notes called it. `Record.programs` returns every
  program the record's slots name; a record can carry up to five, and the two-scalar filters
  routinely carry two. This is what a reader should bind to.

  That claim used to be false for the 4.6% of records whose layout key `derive_layouts.py`
  dropped: those fall through to a hand-written default naming a single slot, so a second
  program could not come back however plainly its slot named one. `Record.classified_programs`
  now reads those records directly — `words[s] + 52` passing `valid_program`, bounded by the
  header end the record states — recovering 9,825 programs at 20.77% of dropped-key records
  against a 0.25% control on records the table does know. `fxmaps` is excluded; see the
  method's docstring for why.
* `Assembly.referenced_programs()` is **permissive** - every program some word in the file points
  at. It exists because FX-Map records reach programs through their tree and the version-2
  prologue holds programs no record names, and both looked like undecoded regions until this was
  measured. It is for coverage accounting, **never for ISA statistics**: any opcode census or
  operand analysis must run over strictly-named programs. See FORMAT-NOTES.md for what happens
  when it does not.

`Assembly.outputs()` returns `(uid, format, grayscale, record index)` for each graph output. The
output table is one 8-byte entry per output, immediately after the record directory in both file
layouts. Earlier sections of the notes record this attribution as structurally absent; it is not.

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

`render.py` implements ten filters: `bitmap`, `pixelprocessor`, `blend`, `transformation`,
`levels`, `uniform`, `directionalwarp`, `gradient`, `curve` and `dirmotionblur`. That is
not enough to render a real material, and FORMAT-NOTES.md measures how far short it falls
and which filter gates the rest.

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
                          the 0x1B branch, one-ISA, no loops, and the node/table dataflow
    audit_corpus.py       runs the model over a corpus and reports every gap
    validate_corpus.py    structural checks against the .sbsar manifests
    attribute_outputs.py  cross-checks the output table against the manifest's alteroutputs
                          relation: 98.20% agreement over 39,855 (input, output) pairs
    test_tables.py        knocks out each table in turn -- a table that changes no
                          reading when emptied is not carrying the decode it documents
    test_corpus_discovery.py
                          corpus discovery must not depend on where the command was typed
    reverify.py           re-runs FORMAT-NOTES.md's headline claims against the CURRENT
                          corpus, so a settled figure cannot quietly go stale
    provenance.py         the provenance exclusion predicate, as a re-runnable check
                          rather than a description of one
    standalone_parse_ref.py
                          the pre-optimisation parser, kept so the 59x rewrite can be
                          re-verified as output-identical on demand

`provenance.py` is the one to run against a new corpus before measuring anything with it.
The exclusion rule in README.md is a single string match, and this applies it and reports
what it drops; the discipline is that it runs BEFORE any measurement, not after.

## The FX-Map decode

`Record.fx_walk()` returns an FX-Map as two connected halves. The chain of nodes --
`addnode` (0x18B), `markov2` (0x89) and five more headers -- computes into a shared slot
frame; the `paramset` table then reads that frame and computes each pattern's size, offset,
rotation and emit condition. The connection is measured: slots at index 64 and above are
read-and-written within one file 88.1% of the time against a 0.0% cross-file control.

Entry boundaries come from the tag, which states both the entry's LENGTH (`FX_ENTRY`) and
which of its words hold programs (`FX_ENTRY_PROGS`). Do not step 8 bytes -- that was the
old rule and it is wrong.

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
meet there. Two specimens is thin evidence for a 41-operation ISA, and the coverage figure --
99.958% of 644,282 programs -- measures the table's completeness, not whether the output computes
the right thing.

## Not here

The exploratory scripts that produced individual findings are left in the repository root.
They are one-off analyses, not maintained interfaces, and several encode assumptions that later
sections of FORMAT-NOTES.md correct.
