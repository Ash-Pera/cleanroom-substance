# tools

The finished tools. Each runs from the repository root, where the corpus lives:

    python3 tools/sbsasm.py <file.sbsasm> [record limit]
    python3 tools/fxdisasm.py <file.sbsasm> <record index>
    python3 tools/extract_bitmaps.py <file.sbsasm>
    python3 tools/audit_corpus.py
    python3 tools/validate_corpus.py

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

* `Record.parameter` is the **strict** one - a record's own parameter program or baked float,
  found through its layout. `Record.programs` returns *every* program the record's slots name;
  a record can carry up to five, and the two-scalar filters routinely carry two. This is what a
  reader should bind to.
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
invented node types. It reaches 95.7% of the node headers present; the gap is that 34% of fxmaps
records carry no node of a known shape at all.

`Assembly.strings()` reads the `text` filter's embedded strings from the head of the resource
segment.

## Extraction

    extract_bitmaps.py    embedded images, and graph inputs by manifest uid
    fxdisasm.py           walks an FX-Map tree and disassembles each node's program
    expand_instances.py   expands sub-graph instances using only in-file graphs

## Checking

    audit_corpus.py       runs the model over a corpus and reports every gap
    validate_corpus.py    structural checks against the .sbsar manifests
    attribute_outputs.py  cross-checks the output table against the manifest's alteroutputs
                          relation: 98.20% agreement over 39,855 (input, output) pairs
    standalone_parse_ref.py
                          the pre-optimisation parser, kept so the 59x rewrite can be
                          re-verified as output-identical on demand

## Not here

The exploratory scripts that produced individual findings are left in the repository root.
They are one-off analyses, not maintained interfaces, and several encode assumptions that later
sections of FORMAT-NOTES.md correct.
