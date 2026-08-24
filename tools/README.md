# tools

The finished tools. Each runs from the repository root, where the corpus lives:

    python3 tools/sbsasm.py <file.sbsasm> [record limit]
    python3 tools/fxdisasm.py <file.sbsasm> <record index>
    python3 tools/extract_bitmaps.py <file.sbsasm>
    python3 tools/audit_corpus.py
    python3 tools/validate_corpus.py
    python3 tools/test_transpile.py

## The model

    isa.py                opcode length rule, and the op ids the format actually uses
    standalone_parse.py   header, footer, interface block and value table
    disasm.py             bytecode disassembler
    sbsasm.py             the file model: records, layouts, edges, parameters, programs

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

## Extraction

    extract_bitmaps.py    embedded images, and graph inputs by manifest uid
    fxdisasm.py           walks an FX-Map tree and disassembles each node's program
    expand_instances.py   expands sub-graph instances using only in-file graphs

## Checking

    test_transpile.py     the only outright pass/fail test here -- see below
    audit_corpus.py       runs the model over a corpus and reports every gap
    validate_corpus.py    structural checks against the .sbsar manifests
    attribute_outputs.py  cross-checks the output table against the manifest's alteroutputs
                          relation: 98.20% agreement over 39,855 (input, output) pairs
    standalone_parse_ref.py
                          the pre-optimisation parser, kept so the 59x rewrite can be
                          re-verified as output-identical on demand

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
