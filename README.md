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
      record_layout.py     the layout rule as one function — SPEC §7.3's width legend
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
Two rows have been re-measured against the current 437 files and 903,616 records since —
the size-expression row, which did not move on re-measurement and then moved 0.003 points
when the `valid_program` floor was retired, and the byte row, which moved 6.75 points.

    filter identified              99.9%
    size expression or first
      parameter read               95.64%  see below - 4.35 of the missing 4.36 points are
                                           records that HAVE no parameter slot. 95.6426%
                                           since the floor went; it was 95.6393%
    edge slots resolved          100.00%
    record bytes interpreted       99.25%  was 92.5%, which was honest when taken: on its
                                           own definition today's tree gives 96.50%, and
                                           99.25% crediting every payload reader - see below
    record layout by mask-walk     99.97%  (only vectorshape, provenance-walled, left)

**The size-expression row does not mean what it looks like, and re-running it does not move
it.** Measured again over the current 437 files and 903,616 records it is 95.64%, identical
to four decimal places at the commit before the 2026-08-28 attribution fixes and after them.
The number is stable because its denominator is wrong, not because the decode is stuck: it
is `1 - (records where size_or_baked returns None) / records`, and a record whose header
ends before a parameter slot could exist returns `None` correctly. `audit_corpus.py` prints
that split on the next four lines and this table dropped it. The split:

    record has no parameter slot   39,303   4.350%   correct, not a miss
    slot is an edge or a ramp bound     38   0.004%   read, not a parameter
    genuinely unread                    63   0.007%

63 records, in two pockets, neither of them a placement failure, **and one of the two has
since closed.** 30 held a real program pointer that `valid_program` refused only because
its floor was the FIRST RECORD's offset - all 30 in v2 files whose code region precedes the
records. That floor is gone and those 30 read, so the split is now 39,303 / 38 / 33 and the
headline is 95.6426%, which is the size of the pocket and not a change of method. The
remaining 33 hold a small integer (`curve`'s point count, 26 of them), and
`size_or_baked`'s program/zero/float trichotomy has no arm for an integer.

**What the floor was really doing was slot-role work in address disguise, and there is now
one predicate instead of two.** An input edge's word is a record index and a record's offset
is `index + 52` - the same universal skew a program pointer uses - so `edge_word + 52` is
by construction the offset of the record the edge names, and asking the program predicate
about it is a category error. In layout A `body_lo` sits past the directory and a small
index lands nowhere; in layout B the body starts at 0x38, so every small word aliases the
version-2 prologue, and a floor over that prologue suppressed the aliases along with 11,440
bytes of real code. `valid_program` and `program_span` - which its own docstring already
called "the single definition of is a program" - disagreed on **8,310 addresses** on four
separate axes, of which the floor was one; they are now one function, and the rule that
replaced the floor is the walk's: only a slot can name a program, and the walk states which
words are slots. Over the window the floor used to cover, 8,463 record words land there and
3.5% decode as a program - but **30 of 30** of the ones the walk names as a size or program
slot do, against 1.9% for input edges and 3.2% for the record's own header words.

The non-circular arbiter says the placement itself was never the problem, and it improved:
over the 742,120 records where the class walk NAMES a size slot, the word there resolves as
a valid program in 742,117 - **99.9996%**, against 23.1% one slot away and 1.2% at a random
other slot in the same records. It was 99.577% before the 2026-08-28 attribution fixes and
99.9981% after them; retiring the floor closed 11 of the remaining 14. The last 3 are
`Texture_Randomizer` records whose slot word is odd, and no floor or predicate makes an odd
address a pointer.

**The format is one recursive mask-walk.** A structured object is `[mask][fields]`: the set
bits of a mask enumerate which fields are present in canonical order, and each field's width
is a constant of its kind — nothing stores an offset. The same primitive runs at three
scales (record header, FX-Map tree node, baked value width), and `walk.py` implements it
once. This replaced a memorised layout table: a walk reproduces record layout for 99.97% of
the corpus with no per-record lookup and no fitted floats, and fails loudly rather than
guessing when a spec is wrong. `SPEC.md` §6 states it.

That walk is now the **live decode path**, not just a check that could reproduce the table.
`Record.layout` and `edge_slots` route through one structural pass (`tools/decompose.py`),
which returns each record's edges and its size-or-program slot from the width legend alone;
the five hand-tuned layout branches it replaced run only as the fallback for the 5 unnamed
filter-9 records. It is proven 0-diff against the independent table-based model (925,706
records, 925,701 agree, 0 disagree, 5 uncovered) and render-verified at 0 pixel difference.

**And the last fitted table is off the live path.** The header model was
`header = const + Σ per-bit costs`, fitted per filter with a free intercept and real-valued
coefficients — 688 numeric cells over five spec shapes, plus a per-filter `w1` grid shift and
a straddle table to put back together the two fields no even grid could hold. It is now
SPEC §7.3's **width legend**: `header = n_hdr + n_base + n_fixed + Σ width(kind)`, with each
`w1` field read at its own bit, and every cell one KIND from `0 1 2 4 C`. **106 kinds over
107 cells** replace the 688 floats, and nothing in the live path reads a fitted number: there
is no intercept, no float, no negative coefficient, no per-state cell, no interaction mode
and no fitted variant. The two models answer the identical header length on **903,276 of
903,301** corpus records with the same 315 refusals, and the walks they drive agree slot for
slot on **903,440 of 903,440** — `inputs`, `cls_slots`, `cls_params`, `hdr`, `prog`,
`size_slot` and `root`, no exceptions. `end` and `param_slots` part on **25** records, and
that is the one place the legend deliberately went past the fit rather than a drift:
`transformation`'s `w1` bits 0-4 are a 5-bit INTEGER and not two-bit fields, and one of its
values emits a program pointer both models used to leave unplaced (SPEC §7.4). The fitted model is kept in
`archive/tools/` as the independent second one, the role `render.py` plays for `render2`.
Its two remaining halves went with it: `sharpen` was still pricing the record's CANVAS, at
±0.5 on word0's log2-size nibbles, latent only because the twelve resolutions in the corpus
make the halves cancel. What the legend cannot separate it MARKS: 36 of its 214
(cell, colour) pairs are exercised in one colour only, so their other colour is a prediction,
and the fitted table stored those absences as zeros indistinguishable from measured ones.

**Baked parameter values are now off the tables too, and `layouts.json` is drained.**
`named_parameters` used to route four filters through the walk and leave `levels` — 9.3% of
records — on the fitted `LAYOUTS` memo. It no longer does, and the arbiter is source
containment rather than the renderer: over every permitted paired source that declares a
`levels` node, matching declared nodes to records on the parameter set and the values to
2e-4, the walk recovers 82 of 93 against the memo's 69, ahead on 10 files and behind on none.
Structurally the memo reads a parameter out of an input-edge slot 1,844 times and past the
walked header end 133 times, where the walk does neither, ever. The render veto that held
this back for months was re-run and withdrawn: the one package it protected, Chesterfield,
scores better under the memo only because three `levels` records emit a constant white — a
value no correct placement can produce, reproduced to four decimals by simply forcing those
records to 1.0, and gone at `max_dim` 256, where the memo's reading takes a pixelprocessor
100% non-finite and the channel does not render at all. Across all five reference packs the
switch moves 9 channels of 27, mean MAE 0.0883 → 0.0669, and flips one package's basecolor
from anti-correlated to positive on all three channels. With `levels` on the walk nothing
reads `layouts.json`: emptying it changes 0 of 160,672 readings, against 9.272% before.
What that switch does *not* fix is stated with it: Chesterfield's basecolor channel 2 is
anti-correlated under the walk at both resolutions, −0.72 and −0.85, and it now has a floor
watching it. The fault is in the nine mode-7 switch blends its colour chain runs through,
not in the placement. Edges, size expressions, program positions and parameter values are
all structural now. What is *not* decided by a walk is what a field MEANS — that is a name
legend, and it never mentions a position.

**The byte row was never code, and that is why it went stale.** Earlier versions of this
table reported "unexplained bytes 0", which was circular: `coverage()` marks a whole record
extent as accounted for the moment the record is enumerated, and the directory is a sorted
partition of the body, so every body byte is inside some record by construction. That
measured the directory's completeness, not the segmenter's. The replacement counts only
bytes the model can put a meaning to — but `git log -S` finds no script that ever computed
it. It entered the notes and this README in prose, and `coverage()`'s docstring points *at*
the figure instead of producing one. So the row nobody could re-run was the row that looked
worst, which is `corpus.py`'s lesson one level up. `audit_corpus.py` now computes it, over a
FILE-WIDE canvas because the directory is a partition and not an allocation: ramps, FX entry
runs and vectorshape strips routinely lie inside a *neighbouring* record's extent, and a
per-record canvas charges them to a record that does not own them.

Re-measured, and the old number checks out as a measurement of its own moment. The same
script against `git archive 8f973fa` — the commit that pinned 92.5% into `coverage()`'s
docstring — over today's 437 files and 903,616 records gives **92.296%**. Against HEAD it
gives 96.50% on that identical definition, and 99.25% once the payload readers this
repository already has are credited at their stated extents.

Re-run again after `66b559a` retired `valid_program`'s address floor, since a change to which
words may name a program is exactly the kind that could move a byte count: **96.499% and
99.254%**, unmoved at the precision quoted. The uninterpreted residual goes 2,123,304 bytes to
2,123,332 — 28 bytes in 284.5 MB, and the row stands. That check took two minutes because the
figure is now something a script produces; the whole reason it was wrong for eight days is
that it was not.

The 7.5% was real in August. Half of
it has since been genuinely decoded — mostly by `Record.ramp` (`gradient` 43.3% → 99.75%)
and by the walk migration reaching programs the layout table could not name — and most of
the rest was never undecoded, only unmarked.

What is left is 2,123,304 bytes, 0.746%, and 68.5% of that is the two-byte alignment pad —
727,527 of 727,527 of them `00 00`, with a decoded structure on each side. The genuine
residual is **624,822 bytes, 0.220% of record bytes**: `vectorshape` 171,836 (one real
payload-extent bug, 13 records, fix written up as a patch and not applied), `fxmaps`
169,086 of entry-table parameter words,
224,466 in `transformation` and `blend` of which 131,068 are two constant-fill image blobs
in a single specimen, and 64,898 everywhere else. See FORMAT-NOTES.md, "The 7.5% of
uninterpreted record bytes".

**`transformation`'s share of that is now classified, and none of it is a decode gap.** Its
342,244 uninterpreted record bytes are an exact three-way partition with no remainder:
225,530 (65.9%) is the two-byte alignment pad, in 112,765 runs of exactly 2 zero bytes each
with a decoded structure on both sides; 65,532 (19.2%) is one specimen's constant-fill blob,
`Grid.sbsasm` record 4; and the remaining 51,182 (14.9%, 119 runs) each abut a byte the
FX-Map reader has already labelled, belonging to a *neighbouring* `fxmaps` record whose tree
lies inside a `transformation` extent because the record directory is a partition rather
than an allocation. `blend` splits the same way — 318,110 as 210,358 pad, 65,536 blob and
42,216 fx-adjacent, also exact — so the pair's 224,466 non-pad bytes are 131,068 of blob and
93,398 of another filter's payload charged to these extents. See FORMAT-NOTES.md,
"`transformation`'s 342,244 uninterpreted record bytes".

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
record and program are known, which is the gap that actually blocks a renderer. `text`
(filter 17) has come off that list: its three `w1` fields are placed and three of its six
parameters are named by a permitted source, and its two base-region pointers turned out to
name a string and a **complete embedded TrueType font**, one per record. The font's presence
is established from its magic bytes and its stated length; nothing inside it has been read,
and whether it may be is a licence question about the type foundry rather than a provenance
question about Adobe — see FORMAT-NOTES.md, "Filter 17, `text`". The
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
