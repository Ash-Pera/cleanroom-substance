# cleanroom-substance

Notes and tools from a clean-room reverse engineering of Adobe Substance's compiled
material format — the `.sbsasm` assembly inside a `.sbsar` archive.

The goal is interoperability: enough of the format documented that Blender and other free
tools could read Substance materials without the proprietary engine.

## What is here

    FORMAT-NOTES.md        the findings — 15,000 lines, written as a lab notebook
    OPCODES.md             the bytecode instruction catalogue

    tools/                 the finished tools — see tools/README.md
      sbsasm.py            the file model: records, layouts, edges, parameters, programs
      disasm.py            bytecode disassembler
      fxdisasm.py          walks an FX-Map tree and disassembles each node's program
      standalone_parse.py  header, interface block and value table
      extract_bitmaps.py   embedded images, and graph inputs by manifest uid
      expand_instances.py  expands sub-graph instances using only in-file graphs
      audit_corpus.py      runs the model over a corpus and reports every gap
      validate_corpus.py   structural checks against the .sbsar manifests

Exploratory scripts that produced individual findings are left in the root. They are one-off
analyses rather than maintained interfaces, and several encode assumptions the notes later
correct.

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
graph inputs by uid, the system variables, and the output-to-record attribution — a table
between the directory and the first record that five earlier approaches had all missed,
naming each output's record in 3,249 of 3,249 with a colour-mode check it could have failed
and did not (`Assembly.outputs()`).

Not decoded: FX-Map tree internals, four filter ids, the version-2 prologue, and what most
filter parameters mean once their record and program are known — the gap that actually
blocks a renderer. See FORMAT-NOTES.md's most recent status section for the current ranking;
this paragraph is a summary and falls behind it.

## On the notebook style

`FORMAT-NOTES.md` records failures, retractions and corrections alongside results, with the
measurement that settled each one. Several sections exist only to record that a plausible
finding was wrong and how it was caught. That is deliberate: in a format with no
documentation, the tests that discriminate are worth more than the conclusions, and a
conclusion without its test is not reusable.
