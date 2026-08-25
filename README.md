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
      extract_shapes.py    filter 5's embedded vector artwork, as PNG or SVG
      expand_instances.py  expands sub-graph instances using only in-file graphs
      transpile.py         compiles a program's bytecode to Python source
      render.py            walks a record graph and evaluates the filters it implements
      audit_corpus.py      runs the model over a corpus and reports every gap
      validate_corpus.py   structural checks against the .sbsar manifests
      reverify.py          re-runs the notes' headline claims against the CURRENT corpus
      provenance.py        the provenance exclusion predicate, as a re-runnable check

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
  `<author v="Allegorithmic"` was dropped entire. 47 of 187 paired sources were excluded
  this way, over a pair set whose pairing is verified rather than assumed: each extracted
  `.sbsasm` is checked byte-for-byte against what the `.sbsar` beside it actually holds. The rule is deliberately over-broad — dropping whole files rather than
  individual graphs gave up 12 graphs that were the material author's own work.

That exclusion has a measured cost, and the notes record it rather than hiding it. The 140
permitted paired sources declare exactly 24 filter names and all 24 are already assigned, so
the two remaining ids cannot be named from anything this project may read — filter 9 not at
all, and filter 5 only descriptively, from what its payload draws. Filter 11 was in that
sentence for a long time and no longer belongs there: it is `dirmotionblur`, named from the
permitted sources alone once containment was applied to its two declared `Float1`
parameters. Three occasions where the boundary was brushed are disclosed as well: aggregate
counts read from two excluded files before it was noticed, eight archives extracted and
scanned before the predicate was applied rather than after, and the declared filter names of
three excluded sources printed alongside their own provenance flag. No such observation is
used, and all are recorded in FORMAT-NOTES.md.

The **Provenance statement** at the top of `FORMAT-NOTES.md` is the auditable version of
all of this in one place. The exclusion predicate is a single string match and can be
re-run against any corpus: `tools/provenance.py` is that check as code rather than a
description of one, and it is meant to run before a new corpus is measured, not after.

## Where the format stands

Measured over 435 specimens, 895,674 records, 4.09 GB (the corpus has since grown to 438, then to 437 after one withdrawal;
the figures below are the last full audit):

    filter identified              97.9%   (99.9% with filter 5, now decoded)
    size expression or first
      parameter read               95.6%
    edge slots resolved          100.00%
    record bytes interpreted       92.5%

The last line is the one to read. Earlier versions of this table reported "unexplained
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
