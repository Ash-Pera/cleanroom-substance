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
    record bytes interpreted       99.53%  was 92.5%, which was honest when taken: on its
                                           own definition today's tree gives 96.55%, and
                                           99.53% crediting every payload reader - see below.
                                           It read 99.32% until the vectorshape extent and
                                           the bitmap pointer skew were settled, and 99.42%
                                           until the out-of-line entry block was read.
                                           99.98% once the two-byte alignment pad is
                                           labelled, which is a fourth tier and not a decode.
                                           99.534% and 99.989% now, on 31,748 uninterpreted
                                           bytes - and the payload row FELL 0.004 points
                                           when a compressed image stopped being credited
                                           its uncompressed size, which is the one movement
                                           here that is a correction rather than a decode
    record layout by mask-walk    100.00%  (5 records of 903,616 - filter 9, and it is the
                                           provenance rule that blocks its NAME, not its
                                           shape. It was 99.97%; `vectorshape` and
                                           `emboss`'s pre-v5 records are in the legend now)

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
once. This replaced a memorised layout table: a walk reproduces record layout for all but
**5** of the corpus's 903,616 records — it was 99.97%, and `vectorshape` and `emboss`'s
pre-v5 records have since joined the legend — with no per-record lookup and no fitted
floats, and fails loudly rather than guessing when a spec is wrong. `SPEC.md` §6 states it.

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
`w1` field read at its own bit, and every cell one KIND from `0 1 2 4 C`. **109 kinds over
110 cells** replace the 688 floats, and nothing in the live path reads a fitted number: there
is no intercept, no float, no negative coefficient, no per-state cell, no interaction mode
and no fitted variant. The two models answer the identical header length on **903,276 of
903,301** corpus records — the population the FIT can answer, since it declines 315 and the
legend now declines 5 — and the walks they drive agree slot for
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

What is left is 2,123,232 bytes, 0.746%, and 68.5% of that is the two-byte alignment pad —
730,360 runs of `00 00` inside a record extent, every one with a decoded structure on each
side. **The pad is now labelled rather than counted as uninterpreted, and it is a FOURTH
tier rather than a widening of the third**, because crediting it moves no byte from
undecoded to decoded: `+ every payload reader` read 99.317% when that tier landed and the
new line read **99.831%**, leaving 480,950 bytes, 0.169%. They now read **99.534%** and
**99.989%**, leaving **31,748**, 0.011% — see below. The audit prints that split, per
filter, with a classification of what remains.

The residual after the pad was **480,950 bytes** and is now **31,748**. Two thirds of the
first drop was the model asking a question two different ways; the rest was one kind of
table entry the walk met, refused and stopped at.

**The last 14,868 were four small things and none of them was FX.** `emboss`'s 6,268 bytes
were its 171 pre-v5 records, which had no layout because the width legend inherited a
version gate from the fitted model — a gate that exists because a free intercept cannot be
told from a class bit set on every key, and which with the intercept pinned is not needed:
those records are exact, and they are the only ones that exercise four of `emboss`'s cells.
`curve`'s 5,832 were a chain: slot 2 is the TOTAL point count over several
`[count][24n]` sub-tables, not one table's size, and the chain totals it on 1,272 of 1,272
records against 0 of 1,272 for the same walk started one word early. `vectorshape`'s 584
were its class block — filter 5 is in the legend now, and its bit-16 slot resolves the
record's own `$outputsize` on 127 of 127, so the "record layout by mask-walk" row above is
100.00%. And 3,504 were the word after an out-of-line FX cell's slot 1, which the previous
pass left out because "nothing in the tag separates" a next-pointer from a program's first
word: `tag & 0x30000` does, 876 of 876 against 316 of 316. One correction went the other
way and is not a closure at all — see the bitmap paragraph below.

**`abuts an fx cell` was an entry whose parameter block sits out of line.** 126,206 bytes,
71% of the residual, in records whose own filter has no payload — and not, as the class's
name suggests, a tree lying beside a cell by accident of the directory partition. The cell
is `[fields][tag][slot 1 → the fields][slot 2]`: its parameter block is stored at the
address slot 1 names and ends exactly on its own tag word, so `entry_layout_holds`, which
reads the tag's program slots *forward*, refuses it and the table run stops dead. Slot 1
means the same thing in the ordinary form, where the block is inline — it holds
`off + 4 × first parameter slot` in 85.75% of the 137,552 entries the walk already reached.
Where the pointer and the tag's own mask agree on where the block is, **1,749 of 1,749
declared program slots resolve as programs**, against 9 of 602 at the nibble-8 words in the
same byte runs where they do not. A second, older defect went with it: `fx_walk` skipped on
an entry's OFFSET, so an entry naming three programs arrived as three items and left as
one — 189,206 programs on 78,402 entries, invisible until a cell's programs lay *behind*
it. The residual goes 178,122 → 46,616, the class 126,206 → 10,628, and `walk_partition`
holds at 32 violations while attributions rise 76,013 → 148,903. `other` moves, which the
two previous passes could say it did not, and every byte of the 3,538 is accounted for in
the notes. SPEC §8's recorded-but-unapplied `stated_extent` correction is settled with it:
it is load-bearing in the new reading — 101 of 595 cells stop matching without it — and
applying it to the checker moves 2 bytes, so the objection that it would credit bytes by
moving the ruler is measured and withdrawn. See FORMAT-NOTES.md, "`abuts an fx cell` was an
entry whose parameter block sits out of line".

**`vectorshape` had two definitions of where its payload stops, and one of them was a copy
in the audit.** `audit_corpus.py`'s byte canvas re-derived the extent from the embedded
length word instead of calling `Record.vector_shape`, so the slot-2 payload-end override
`68377e1` added could report recovering 146,440 bytes while the audit's `vectorshape`
residual did not move — the 90 bytes it did move were its `align pad` column, the same row
taken with and without a tier that landed in the same pass. Both figures were right about
their own instrument. There is one definition now, `Record.vector_extent`, and the audit
asks for it. The slot-2 rule also turned out not to be fitted to the 13 records that
motivated it: of the 57 records where both its containment bounds hold, **44 are a control
in which slot 2 and the embedded length word agree to the byte.** And the "chain of
`[kind][length]` sub-payloads" that commit recorded as refuted is real — it looked at
`off + n` and the next header is at `off + n − 4`, because the length counts one trailing
word that is not a vertex. `vectorshape` goes from the worst filter in the table,
81.24% interpreted, to **99.93%**.

**And the payload states its own end, so the 141,088 bytes were never a convention.** That
same pass recorded what its bound cost: 141,088 of the 146,388 bytes the slot-2 override
credits were "bounded and stated by nothing". They are not. A filter-5 payload is a chain of
`[len][len >> 3 vertices]` parts closed by a **zero terminator word** — the old
`(w + 23) / 2` is that formula seen through the first part only, `12 + 4 * (len >> 3)`, one
part plus the *next* part's length word. The walk terminates in **139 of 139** records and
lands exactly on slot 2 in **57 of 57** where slot 2 is a usable bound, including all 13 the
override had to be asserted for; corpus-wide all 139 ends land on a boundary the file states
elsewhere. The discriminating control is the 35 records where the two readings can disagree:
the walk's end is stated by slot 2, the record end or the next payload's start in 34 of 35
against **0 of 35** for the embedded length word's end, and the 35th is named by a `bitmap`
record's image pointer — the only word in a 5.4 MB file that names it. **Nothing closed and
the residual did not move**: `audit_corpus.py`'s output is byte-for-byte identical, because
what changed is what a credit rests on and not which bytes are credited. `len & 7` turned out
to be a primitive selector, which settles the caveat that pass left open — the tail read
62.24% on the strip test because 38 of its 54 parts are **closed contours** (0.38% adjacent
repeats against 16.71%, first vertex equals last in 37 of 38) and not strips. See
FORMAT-NOTES.md, "The payload states its own end".

**`Grid.sbsasm`'s two "constant-fill blobs" are images that say `2m` and `4m`.** Three
65,536-byte 256×256 grayscale label images, each named at `words[1] + 52` by a *neighbouring*
two-word `bitmap` record and each lying in the previous record's extent — §5's partition
again. Reaching them needed two corrections in `Record.bitmap`: it decided a record's form
from its **directory extent** rather than its own header length, and its pointer skew was
`+4` where the format's universal skew is `+52`. The `+4` put every image in the corpus 48
bytes early, reading 48 bytes of the file header as the first image's pixels; the check that
sees it is the segment's far end, `max(offset + size) == resource_end` in **111 of 111**
against 111 of 111 at −48. Three of the four checks in `test_bitmap.py` were blind to it —
52 ≡ 4 (mod 8), and packing is invariant to a uniform shift — and there is now a fourth that
is not. See FORMAT-NOTES.md, "`vectorshape`'s 172,344 bytes were a second definition".

**And the audit was crediting a compressed image's UNCOMPRESSED size, which is 53,782 bytes
it had no business holding.** `Record.bitmap` says in as many words that `size` "stays the
UNCOMPRESSED size, because that is what it is" for a JPEG record, and the byte canvas
marked `[offset, offset + size)` anyway: `PavingStonesSubstance006` record 125 declares
0x400000 bytes at 0x1324ac in a 2.6 MB file, so the span ran past `body_lo` and over
1,360,900 bytes of the record body, painting every one that no earlier reader had claimed.
The file states the compressed length — a u32 at `offset`, ahead of the SOI at
`data_offset` — and `data_offset + n` lands exactly on the stream's `FF D9` in **54 of
54**. Corrected, the residual does not move by one byte and 53,782 re-attribute to the
readers that state them: `ramp` +14,754, `fx entry` +23,946, `fx node` +2,452,
`curve` +180 and the alignment pad +12,450. It is a reclassification and not a closure, and
it costs the `+ every payload reader` row 0.004 points because a twelfth of it lands in the
fourth tier.

**135,440 bytes of that came off the FX row — 40.7% of the whole FX gap — and the repair the
notes proposed for it is withdrawn as stated.** SPEC §8 proposed widening `fx_table`'s
next-pointer search to the cell's stated width. Measured, that makes the residual worse
(18,856 → 31,030 unreached bytes over 60 files), because `0x00020008` is a two-word cell
whose slot 2 is the *next* cell's tag word rather than a pointer; and fixing the off-by-one
in the width reverses the direction but still costs 35 real entries, because moving the
choice resolves `0x00020018` and `0x00010008` in opposite directions. What works is the same
observation with no choice moved: **a cell that names two forward structures gets both
followed.** Two more things were wrong beside it — the handoff between the node chain and the
paramset table only ran one way, so a table run landing on a node header stopped the whole
walk; and the chain's two-word links were traversed without ever being reported.

The result is an extension and not a wider net. Over the corpus 39,839 of 41,164 `fxmaps`
records walk identically, 1,322 gain items with the old list an exact ordered subsequence
every time, and 3 are altered — three bit-7-clear leaves losing a program attribution that
`walk_partition` reports as reading a neighbour's constant. `fx cell not reached` goes
183,804 → 70,940; `walk_partition` holds at 32 FX violations on 73,964 → 75,557 attributions;
and on the only ground-truth check in the repository, `Chesterfield`'s basecolor rises
+0.60/+0.65/−0.72 → +0.75/+0.77/−0.68 and its roughness +0.90 → +0.93, with four
`REFERENCE_FLOOR` entries ratcheted up. See FORMAT-NOTES.md, "A cell with two forward
pointers loses one, so follow both".

**And another 30,086 came off it, because the words the parameter layout DROPS are pointers
too.** `fx_table` steps by the furthest-forward of "the slots the tag's *parameter* layout
declares", and `fx_entry_layout` drops every structural bit — 4, 7, 16 and 17, the words
`FX_STRUCTURAL_BITS` already records as pointer-shaped. Enqueuing each of those words as a
further table start, gated on the record's own frozen entry-tag vocabulary, and reading a
pointer cell's payload when the cell is met inside a table run rather than only through the
chain, closes 122 of the 316 remaining cells over the 60-file sample and takes `fx cell not
reached` 70,940 → 41,034. The gate is what makes it precise: ungated the same sweep admits
91 cells that land on bytes another reader had already been credited, all of them bit 7.
Corpus-wide 40,892 of 41,164 records are identical, 272 gain items with the old list an
exact ordered **prefix** every time, and **0 are altered**. What the rule proposes is
checkable where nothing is at stake: 10,895 of the 10,931 targets it offers — 99.67% — are
cells the same record's walk already reaches by another path, against 1 of 34,258 for the
same gate on the tag's own program slots. Two further groups were measured and refused, one
of them after being fully implemented: a node's spare field slot closes another 102 cells
with a 27-against-0-against-0 control, but it quadruples what the records it touches draw
and the render is bit-identical either way, so it is the `0x1db` refusal covering three more
families. See FORMAT-NOTES.md, "The words the parameter layout drops are pointers too".

**The 8-byte FX entry stub was already fixed, and this is what it was worth.** `bytes-audit`
found FX entries credited a fixed 8 bytes rather than their stated extent and fixed it in the
same commit; re-measured at HEAD both ways, the stub gives `fxmaps` a residual of 2,787,352
and the stated extent 802,940 — 1.98 MB, already credited. A proposal to credit it again
would have moved nothing.

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
"`transformation`'s 342,244 uninterpreted record bytes". **That fx-adjacent third has since
been read** — it is the out-of-line entry block above, and `transformation`'s share of it is
46,216 → 4,804 bytes.

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
