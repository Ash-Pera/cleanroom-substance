# cleanroom-substance

Notes and tools from a clean-room reverse engineering of Adobe Substance's compiled
material format — the `.sbsasm` assembly inside a `.sbsar` archive.

The goal is interoperability: enough of the format documented that Blender and other free
tools could read Substance materials without the proprietary engine.

## What is here

    FORMAT-NOTES.md        the findings — 15,000 lines, written as a lab notebook
    OPCODES.md             the bytecode instruction catalogue

    sbsasm.py              segmenter: parses a .sbsasm into records, edges and programs
    disasm.py              disassembler for the bytecode
    standalone_parse.py    header, interface block and value table
    extract_bitmaps.py     locates and extracts embedded images
    expand_instances.py    expands sub-graph instances using only in-file graphs
    audit_corpus.py        runs the model over a corpus and reports what it cannot explain
    validate_corpus.py     structural checks against the .sbsar manifests
    isa.py                 instruction lengths

Plus assorted analysis scripts used along the way.

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
  `<author v="Allegorithmic"` was dropped entire. 38 of 140 paired sources were excluded
  this way. The rule is deliberately over-broad — dropping whole files rather than
  individual graphs gave up 12 graphs that were the material author's own work.

That exclusion has a measured cost, and the notes record it rather than hiding it: filter
id 11 (1.7% of all records) and filter id 5 cannot be named, because every specimen that
would identify them is excluded. One occasion where the boundary was brushed — aggregate
counts read from two excluded files before it was noticed — is disclosed too, along with
the fact that the observation was not used.

The **Provenance statement** at the top of `FORMAT-NOTES.md` is the auditable version of
all of this in one place. The exclusion predicate is a single string match and can be
re-run against any corpus.

## Where the format stands

Measured over 435 specimens, 895,674 records, 4.09 GB:

    filter identified              97.9%
    main parameter resolved        94.7%
    edge slots resolved           99.96%
    unexplained bytes                  0

Decoded: the container, the record directory as a sorted extent map, the tag's filter and
resolution fields, 17 of 21 filter ids, the edge map, the parameter word for `blend`
(including `blendingmode`), the instruction set at 41 operations, the embedded bitmap format,
graph inputs by uid, and the system variables.

Not decoded: FX-Map tree internals, four filter ids, the version-2 prologue, and the
association between a graph's outputs and the records that produce them — which five
independent approaches failed to find, because the binary does not store it.

## On the notebook style

`FORMAT-NOTES.md` records failures, retractions and corrections alongside results, with the
measurement that settled each one. Several sections exist only to record that a plausible
finding was wrong and how it was caught. That is deliberate: in a format with no
documentation, the tests that discriminate are worth more than the conclusions, and a
conclusion without its test is not reusable.
