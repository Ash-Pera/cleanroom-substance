# The `.sbsar` / `.sbsasm` format — specification

A concise, self-contained description of Adobe Substance's compiled material format, as
reconstructed by clean-room analysis. It is written to be *sufficient to build a reader*:
every structure below can be located by pointer arithmetic from the file itself, with no
fitted tables and no per-file heuristics. Numbers quoted as agreement rates are corpus
measurements over 383 distinct specimens.

Conventions: little-endian throughout; all sizes in bytes unless stated in *words*
(1 word = 4 bytes); a **pointer** in this format is stored as `target − 52` (the "+52
skew"), so every pointer is dereferenced as `stored_value + 52`.

---

## 1. Layers

A `.sbsar` is a 7-zip archive. The material lives in two parallel files per graph:

```
assemblies/content/0000/<name>.xml       manifest — inputs, outputs, GUI, presets (has a DTD)
assemblies/content/0000/<name>.sbsasm    compiled graph — the binary this spec describes
assemblies/content/0000/thumbnail.png    icon
```

The **manifest** is plain XML (`formatversion="2.1"`) and is the layer existing tools read;
it carries parameter declarations but *no graph topology*. The **`.sbsasm`** carries the
compiled graph: a directory of records (filter nodes), a stream of bytecode programs
(computed parameters), a value table (baked parameters), and an interface block (the
package's inputs and outputs). This spec is about the `.sbsasm`.

---

## 2. `.sbsasm` header (0x00–0x38)

Fixed 0x38-byte header, identical field layout in every specimen.

| offset | size | field |
|---|---|---|
| 0x00 | 4 | magic `"SBAM"` |
| 0x04 | 4 | **assembly (cooker) version** — see note |
| 0x08 | 8 | per-file uid |
| 0x10 | 4 | total file size (exact) |
| 0x14 | 4 | `0x1C` (const) |
| 0x18 | 4 | `0` (const) |
| 0x1C | 4 | pointer to trailer = `filesize − 28` |
| 0x20 | 4 | `0x00010002` (const) |
| 0x24 | 4 | `0` (const) |
| 0x28 | 4 | `1` (const) |
| 0x2C | 4 | value-table end, as a pointer (`table_end − 52`) |
| 0x30 | 4 | `2` (const) |
| 0x34 | 4 | `0` (const) |
| 0x38 | — | body begins |

**Version (0x04)** takes the values `0x0002_0000 … 0x0009_0000` and identifies *which
cooker published the file*, not a release date. It matters because it changes one encoding
rule (image-input slot width, §7.2). It is independent of the manifest's `formatversion`.

---

## 3. Overall body layout

```
0x00            file header (0x38)
0x38            embedded resource segment   ]  length == base   (image, string and font payloads; §9)
base + 0x38     record directory            ]
                records (code region)       ]
                value table                 ]
                interface block             ]
filesize − 28   trailer (root pointers)
```

`base` is the size of the resource segment. **`base == 0`** for packages that embed no
images (the directory then starts at 0x38); otherwise the segment displaces the directory.
A reader must not assume the directory is at 0x38 — it is located from the trailer.

---

## 4. Trailer — the root pointer block (last 28 bytes)

Seven words at `filesize − 28`. A reader needs only the magic from the header; everything
else is reachable from here.

| word | meaning | agreement |
|---|---|---|
| 0 | per-file identifier | — |
| 1 | small enum (0–5, 8) | unexplained |
| 2 | per-file identifier | — |
| 3 | pointer (into directory or body) | 99% valid `+52` |
| 4 | **record-directory start**, as pointer | 100% |
| 5 | **record-directory end**, as pointer | 100% |
| 6 | **value-table start**, as pointer | 100% |

So `dir_at = word4 + 52`, `count = (word5 − word4) / 4`, `table_start = word6 + 52`, and
`base = word4 + 52 − 0x38`.

---

## 5. Record directory

A contiguous array of `count` u32 **absolute file offsets**, strictly increasing, each
pointing at one record. Validated over the full length in every specimen. Sizes range
2 – 39,627 entries (median 1225). A record's extent is `[offset[i], offset[i+1])`; the
last runs to the value table. **Record length is not stored** — it is framed only by the
directory, which is why a correct reader must always walk records from the directory and
never scan the body linearly.

---

## 6. Records — the mask-walk

A record is one filter node. Its layout is not tabulated anywhere; it is **walked** from
two bitmask words at its head. This is the single structural primitive of the format, and
it recurs at three scales (record header, FX-Map node §8, baked value width).

### 6.1 The primitive

A structured object is `[mask][fields…]`. The set bits of the mask, read in ascending
order, enumerate which fields are present; **each field's width is a constant of its
kind**. Nothing stores an offset — a reader advances position by the width of each present
field; a writer emits in the same order.

**Ascending order has two known exceptions, and both are stated here rather than only at
§13.4, because a reader who takes ascending order as universal places fields wrongly and gets
plausible numbers rather than a failure.**

1. **Filter 17 `text`'s `w1` parameter block** is laid `matrix22`, `position`, `fontsize`
   (§13.4) — bits 10, 6, 8. This applies to the parameter block alone.
2. **The class block emits bit 16 LAST within the low class group (bits 16–23), in EVERY
   filter; the filter's own bits 24–31 follow in ascending order.** Class bit 16 gates
   `$outputsize` and bit 23 gates `$randomseed` (§13.4), and when both are set the
   `$randomseed` pointer takes the first class slot and the size expression the second.

   **This was stated here as the pair "23 before 16", and a pair is wrong on 3 records.**
   Scored on the 214,298 corpus records where the candidate orders place bit 16's slot
   differently at all, by whether that slot resolves a program returning a **two-component
   integer** — which a size expression is and a seed is not:

   | order | valid program | two-component |
   |---|---|---|
   | bit 16 last in the low group | 214,298 / 214,298 | **214,298** |
   | swap 23 before 16 | 214,295 / 214,298 | 214,295 |
   | plain ascending | 214,295 / 214,298 | 112,122 |
   | bit 16 last overall / descending | 169,944 / 214,298 | 100,440 |

   The three the pair misses are `Texture_Randomizer` records 0, 2 and 5 — the only corpus
   records that set class bit **22**, which costs a word and is the only costing class bit
   strictly between 16 and 23. They set 16 and 22 and **not** 23, so a pairwise swap never
   fires. Under the sort rule their bit-16 slot resolves a two-component program whose first
   `inputref` names the uid the manifest declares `identifier="$outputsize" type="8"` on 3
   of 3, and their bit-22 slot holds the constant `0x203`; walked ascending the two are
   exchanged.

   **What this corpus cannot separate.** "Bit 16 last in the low group" and "the system
   variables are emitted first, then the filter's own bits" predict the identical order on
   every record here: bits 17–21 cost no word in any filter, so 22 and 23 are the only other
   observable members of the low group. The specimen that would separate them is a record
   setting a **costing** class bit in 17–21 together with bit 16, and there is none. The rule
   above is the one stated because it predicts; a list of pairs only records.
   Measured over **all 102,173 corpus records that set both**, across 19 filters, and taken
   by slot POSITION rather than by any reader's labels: the first class slot's program
   returns **one** component in 102,173 of 102,173 — a size never can — and the second
   returns **two** in 102,173 of 102,173. An independent arbiter agrees without evaluating
   anything: the manifest identifier of the graph input each slot's program reads with its
   first `inputref` is `$randomseed` in the first slot on **102,173 of 102,173** and
   `$outputsize` in the second on 98,113, the remainder either not opening with a bare
   `inputref` (3,902) or naming the material author's own size input (158 records over seven
   identifiers — `resolution` 136, `scale` 12, `cloud_size` 4 — which is the same fact in
   that author's vocabulary).
   Over the 46,118 of those records outside `pixelprocessor`, where it was first measured,
   the second slot's two components equal the record's own tag size in 46,023 of the 46,075
   that evaluate (99.89%).

   The control is records with bit 16 set and bit 23 clear, where nothing can swap and the
   single class slot must be the size: it resolves a two-component program in **639,944 of
   640,074** corpus-wide, a one-component program in **0**, and `$randomseed` in **0**. The
   130 that do not are `vectorshape` (127, no cost model and no placed slot) and three
   `fxmaps` records in `Texture_Randomizer`. `levels` alone is 74,262 of 74,262.

   **`pixelprocessor` was listed here as the exception and is not one.** Its header is
   `[w0][w1 arity][image inputs][bit 23][bit 16][the filter's own pixel program]`, and the
   same manifest arbiter names the first class slot `$randomseed` on 57,731 of 57,731
   records that set bit 23 and the second `$outputsize` on 56,141 of 56,142 that set bit 16,
   with the block ending exactly one slot before the fitted header length on 57,965 of
   57,965. What made it look exceptional is that `decompose`'s arity arm allocated the pixel
   program's slot in FRONT of the class block, so both class labels sat one word late. **That
   is fixed and there is no exception left**: the arity arm walks the class block from
   `2 + n_in` in the same emission order every other filter uses, and puts the filter's own
   program after it. The A/B over 903,616 records moved `prog` on 57,011 `pixelprocessor`
   records and `size_slot` on 87, and moved `end`, `inputs`, `hdr` and `param_slots` on
   **none** — a relabel, not a misplacement. The arbiter, taken by slot POSITION rather than
   by the walk's labels: the last header slot reads `$pos` (sysvar 8) on 55,678 records and
   calls `samplelum`/`samplecol` on 55,179, against 105 and 115 for the slot the walk used to
   call the pixel program — which instead opens with a bare `inputref` on 57,818 and is 0–9
   instructions long on 57,833. See FORMAT-NOTES.md, "Every filter, bit by bit", and the A/B
   appended after it.
   The claim that `pixelprocessor` is "the only filter that sets class bit 22" was a bit
   number read one place low: it sets bit 22 on 0 records and bit 23 on 99.60% of them, and
   the only records in the corpus setting class bit 22 are three `fxmaps` records in
   `Texture_Randomizer`.

A reader that walks the class block in plain ascending order still gets the header LENGTH
right — both bits cost one word — so nothing runs past the end and no parameter moves. What it
gets wrong is which of the two slots is the size, and the error is silent: the misread slot
holds a one-component program, and a reader that requires two components to call something a
size discards it as unevaluable rather than reporting a disagreement.

That silence is measured rather than argued. This project's own decoder walked the block
ascending in one of its four code paths for two commits after stating the rule here, and the
A/B that fixed it moved `size_slot` on 4,280 records while moving the header end, the edge
list, the mask-word count and every parameter slot on **none**. Nothing about the record's
shape reports the error; only the name on one word changes.

### 6.2 The two header words

```
word0:  low16  = bit 0     colour flag (0 grayscale, 1 colour)
                 bits 1-7  filter id, as (low16 & 0xFF) >> 1
                 bits 8-11 log2 WIDTH        the record's own canvas (§13.2)
                 bits 12-15 log2 HEIGHT
        high16 = CLASS WORD — presence mask over INHERITED parameters
word1:          two-bit code per field — the filter's OWN parameters
```

The low half is worth spelling out because it is **not** a presence mask and a reader must
not treat it as one: two of its nibbles are a size. A fitted cost table that offers every bit
of word0 as a feature will happily charge header words to them, and §13.4 records what that
cost. §7.3's width legend has no cell on any bit below 16, because a width comes from a type
and not from a regression.

- **Class word (word0 high half):** the set bits are read in ascending bit order, and each
  one that gates a stored value adds a field. Widths come from the manifest type of the
  parameter that bit gates (§7.2): bit 10 is `$outputsize` (integer2 → 2 words); the other
  common inherited parameters are 1 word each. **A set bit can cost nothing**, and a reader
  that gives every set bit a slot runs its block past the end of the header — see §13.4,
  where a fitted table charged four bits that store no value.
- **Word1 two-bit codes:** each of the filter's own parameters is a 2-bit field:

  | code | meaning | cost |
  |---|---|---|
  | `00` | absent | 0 words |
  | `01` | baked (value stored inline / in the value table) | width of the field's kind |
  | `10` | program (a bytecode pointer) | 1 word |
  | `11` | image input (an **edge**) | 1 slot |

**Field kinds and widths** (words): scalar `Float1` = 1; `Float2` = 2; `Float4` = 4;
*per-channel* fields are `Float1` when grayscale and `Float4` when colour, selected by
word0 bit 0. These are the only widths in use — "4 is the widest scalar the format has".

### 6.3 Edges (graph connectivity)

An **edge slot** holds a **backward record index** (the index of the record that feeds
this input), or the sentinel `0xFFFFFFFF` / `0` for absent. Edges come from three places,
in this order: a filter's fixed *base* image inputs (contiguous from slot 2), any word1
field with code `11`, and — for a few filters — an *arity integer* (§6.4). Because edges
are backward indices, a walk can be checked loudly: any slot the walk calls an edge must
hold a value `< own index`, or the walk is wrong.

**One `w1` field declares an edge on its LOW BIT, not on the full code `11`.** `distance`'s
field 0 is the case: it charges a word in states `01` and `11` and nothing in `10`, which is
a cost tracking bit 0 alone rather than baked-versus-program, and no parameter costs that way.
Over the corpus's five `distance` `w1` values, bit 0 set (5, 7, 9) gives two edges and clear
(6, 10) gives one, **2,277 of 2,277**. Such a field is *not* part of the end-anchored
parameter block (§13.4) and must not be charged a word in it — doing so begins the block one
slot late and silently renames every parameter after it.

**The same loud check applies to programs.** A slot the walk calls a program must hold a
decodable program at `value + 52`, exactly as an edge slot must hold a backward index. This
is worth asserting rather than assuming: reading a baked `5.120025` as the address
`0x40a3d70a + 52` is what the mis-charged field above produced, and it is invisible without
the check — a wrong radius renders, a wrong address does not, and only one of them announces
itself. On one specimen the unchecked read blocked 1,581 further records.

### 6.4 The layout alphabets

The file states each filter's layout in one of three self-describing ways; a reader
handles all three with the one primitive and needs no fitted table:

1. **Two-bit presence codes** — word1 as above (blend, levels, transformation, warps).
   A field begins at **its own bit** (§7.3); there is no grid and no per-filter shift.
2. **Arity integer** — the header states an input *count* as a small integer in word1 and
   the walk reads that many edge slots (pixelprocessor, five bits at 0; fxmaps, six bits
   at 10, after its tree-root pointer).
3. **Paired conjunction** — two class-word bits that, set *together*, name one field
   (bitmap's bits 24+27 = the pixel-offset word).

**There was a fourth, and it was a count standing in for a per-bit fact.** It read: the
number of *leading* block slots that are programs is `popcount(class_word & mask)`, the
rest baked, filled positionally from the front of the block (blur, warp). What the corpus
says instead is that **each class bit is a pointer or a value and always the same one.**
Scored against what the slot holds — `valid_program(word + 52)`, never against any reader's
labels — every class bit of both filters is all-or-nothing:

| filter | pointer bits | value bits |
|---|---|---|
| warp | 16 (26,559/26,559), 23 (269/269), 27 (19,388/19,388), 30 (1,109/1,109) | 26 (0/860), 29 (0/24,815) |
| blur | 16 (9,981/9,981), 23 (51/51), 27 (8,675/8,675), 29 (303/303) | 26 (0/10,318), 28 (0/14,931) |

The popcount mask is that pointer set **minus warp's bit 30**, and warp emits a value bit
(29) *before* that pointer bit, which no positional count can express. On the same slots and
the same ground truth, per-bit is exact on **26,791 of 26,791** warp records against the
count's 25,682 (73,000 slots against 71,891) and identical on blur's **15,371 of 15,371**.
Nothing that agreed stops agreeing.

Role is not a layout alphabet at all, and that is why it leaves this list: both readings
cost one word, so the header is the same length either way, and what changes is what the
word *means*. That is a name-legend fact (§13.4), and it lives beside the other names —
`sbsasm.CLS_PROGRAM_BITS`. The extent consequence the old rule carried is unaffected and
still holds: when no pointer bit is set the size is two baked words `(w, h)` rather than one
program pointer, so a blur header is five words with a baked size and four with a computed
one.

A walk mechanism reproduces record layout for **99.97%** of the manifest-bearing corpus.
Two-shape filters state which shape a record takes with a single stated term — e.g.
`shuffle` uses tag bit 0 (the colour flag) to split its two authoring nodes,
`grayscaleconversion` (one input + a `channelsweights` vector, no w1 word) and Channel
Shuffle (two inputs + a packed channel selector in w1). The only residue is `vectorshape`,
whose layout the file does not state in any readable term and which is additionally behind
the provenance wall (§12).

---

## 7. Parameters

A filter's parameters are either **computed** (a bytecode program) or **baked** (a
constant). Computed parameters are pointers into the instruction stream (§10). Baked
parameters are stored **inline in the record header, one word per component** (§6.4) — not
in the value table, which holds the graph input defaults only (§7.1).

### 7.1 Value table

A single array named by trailer word 6 and bracketed by header 0x2C. It holds the **graph
input defaults and nothing else** — 98% of its entries are byte-exact against manifest
defaults, the rest within float-rounding, none unexplained. Values are addressed
positionally by the widths of §7.2.

An earlier version of this section said it "holds every baked scalar/vector value". That is
false, and the error is large: measured over 437 specimens, the graph-input descriptors of
§7.2 consume the table's **entire stated extent** — `table_start = trailer word 6 + 52` to
`table_end = header 0x2C + 52` — in 437 of 437 files, with no room left over. Meanwhile the
records carry **544,189 baked parameter slots** against the corpus's **8,500** descriptors,
a ratio of 1 : 64.

Those two populations are disjoint. **A record's baked parameters are stored inline in the
record header, one word per component** (§6), and are never in the value table. A reader
built on the old sentence would look for half a million values in an array that does not
contain them.

The 437/437 closure is stated deliberately in terms of the two header/trailer pointers.
`standalone_parse` reports its own `table_ok` at 437/437 as well, and **that number is not
evidence**: the parser selects the interface-block candidate that satisfies
`tstart + span == hdr`, so its closure is a property of the chooser rather than of the
format. The pointers above are ones the chooser never reads.

### 7.2 Graph-input default table

The pointer at 0x2C also frames a table of **graph input defaults** — the graph's
`<inputs>` plus the package `<global><inputs>`, **sorted by manifest `uid` ascending**.
Element width follows the manifest `type` code — this is the *width legend* the whole
mask-walk reads rather than fits:

| type | meaning | width |
|---|---|---|
| 0–3 | float1..float4 | 4N |
| 4, 8, 9, 10 | int1, int2..int4 | 4N |
| 5 | image input | **16 bytes from v8 on, 0 before** |
| 6, 7 | string, font | 0 (stored elsewhere) |

The image-input width is the one version-dependent rule in the format: from assembly
version v8 (`0x0008_0000`) an image input occupies a 16-byte `f32×4` slot at its uid
position; in v2–v6 it occupies none. Getting it wrong shifts the whole table by
`16 × (image count)`.

### 7.3 The width legend, and the key it is missing

§7.2's `type -> 4N` table is the format's own width legend, stated in the file and read
rather than fitted. **It is now the whole of the record-header model as well**, and the
header length is one sum over it:

```
header = n_hdr + n_base + n_fixed
       + SUM over set class bits of        width(kind)
       + SUM over w1 FIELDS -- a two-bit code AT ITS OWN BIT OFFSET -- of
             00 absent  -> 0        01 baked   -> width(kind)
             10 program -> 1        11 edge    -> 1
       + arity                (the two filters whose w1 holds an input count, §6.4)
       + one conjunction      (bitmap 24+27, §6.4)

width:  0 -> 0   1 -> 1   2 -> 2   4 -> 4   C -> 1 grey / 4 colour
n_hdr = 1 + (this record carries a w1 word)
```

`n_hdr` counts mask words, `n_base` is the filter's fixed image-input arity (§6.3) and
`n_fixed` its fixed prefix — the ramp pair, the FX tree root, the bitmap pixel word,
`text`'s zero + string + font, `pixelprocessor`'s own program. Every term is a structural
count or a width from the type legend above. **There is no intercept, no float, no negative
coefficient, no per-state cell and no grid shift**, and the whole table is 106 kinds over
107 cells — 32 of them the bit a `w1` field begins at. A model with 688 fitted numeric cells
across five spec shapes stood here before it, and the two answer the identical header length
on 903,301 of 903,301 corpus records with the same 315 refusals.

**A kind is a pair of widths and the corpus does not always give both.** Only two of the
five share a width — `Float1` is `(1, 1)` and per-channel is `(1, 4)` — so a cell exercised
in one colour only is a reading in that colour and a *prediction* in the other. **36 of the
214 (cell, colour) pairs are in that state**: 19 because the filter has no record of the
other colour at all (`text` is grey on all 59, `normal` and `hsl` colour on every one), 17
because it has records and none set the cell (`blur` / `sharpen` / `distance` / `curve` /
`dyngradient` class bit 23 in colour, `emboss` w1 bit 5 in grey, `fxmaps` class bit 22 in
colour). An implementation must mark those, not store them as zeros — the fitted table
stored them as zeros and they were indistinguishable from measured ones.

The legend reaches the parameter slots as well: over 437 specimens every one of the
**544,189** baked parameter slots the walk reads has a width of 1, 2 or 4 words —
`float1`, `float2`, `float4` — and **none falls outside the legend's 1..4**. (Width 3,
`float3`, is legal by the legend and does not occur.) Per filter:

| filter | 1 word | 2 words | 4 words |
|---|---|---|---|
| 1 `blend` | 138,608 | 26 | — |
| 2 `transformation` | 36 | 29,331 | 66,512 |
| 11 `dirmotionblur` | 25,654 | — | — |
| 12 `directionalwarp` | 115,122 | — | — |
| 15 `levels` | 163,992 | — | 1,735 |
| 17 `text` | 43 | 39 | 14 |
| 18 `normal` | 988 | — | — |
| 21 `distance` | 2,089 | — | — |

So the legend is not the gap. **What the file does not state is the per-field type CODE**,
and that is the whole of what the table derives — a *kind assignment* per (filter, cell),
not a width. Two searches for a per-node type declaration came back empty and are
recorded so they are not repeated: the interface block declares 8,500 typed descriptors
against half a million slots and is framed to the graph-input table alone (§7.1), and the record
directory holds bare offsets. The filter id *is* the declaration, and the parameter list it
names lives in the engine.

**A width does not decide a ROLE, and the two must not be conflated.** `blur`'s class bits
27 and 29 are both one word and both are program pointers; its bits 26 and 28 are two words
and one word and both are baked values — but `warp`'s bit 29 is one word and a value while
its bit 30 is one word and a pointer. So a `1` in this table means "one word", never "a
pointer". Which one-word cells hold pointers is a name-legend fact and is stated with the
names (§6.4, §13.4).

**Three rows moved when the cost model's attribution was corrected**, and the movement is
the correction rather than new data: `distance`'s width-2 column was the phantom left by
charging its mask input twice — the real field is one word wide and there is no width-2
`distance` parameter at all — and `normal` gained 17 slots that the walk used to allocate
past the end of their own records and then discard. `blend`'s row had gone stale earlier,
when its relocated opacity arm was named. The claim the table supports is unaffected: no
width outside 1, 2, 4 has ever appeared, and the corrected `distance` row removes the only
row where a width came from a rounded 1.5 rather than from a type. Under the legend no
width comes from a rounding at all: every cell is solved as an integer against a pinned
base, and the two remaining halves the fit still carried — `emboss`'s w1 bit 1 at "0.5 grey
/ 1.0 colour" and `sharpen`'s four canvas bits at ±0.5 — have no cell.

One kind is already stated rather than assigned, which is the existence proof that the
distinction is real: a `channel` field's component count is the **tag's colour bit** — 4
words when colour, 1 when grayscale — so `walk._field_width` derives it and does not fit
it. The open problem is the rest of the assignment, and its legitimate route is the
permitted `.sbs` sources, which declare parameter names and types per filter.

### 7.4 The field primitive — how `w1` gates and places a parameter

One rule places every parameter this project reads, and it is the §6.1 mask-walk applied to
the second header word.

**`w1` is a set of two-bit FIELDS, and a field begins at ITS OWN BIT.** There is no grid.
A filter declares an offset per field and the field occupies bits `(b, b + 1)` —
`directionalwarp`'s are at 1, 3 and 7, `emboss`'s at 1, 3, 5 and 7, `blend`'s at 4, 6 and 9,
`transformation`'s at 6, 25 and 28, `levels`' and `fxmaps`' at 0, 2, 4, 6 and 8, `text`'s at
6, 8 and 10.

**This section used to state an even grid `(2j, 2j + 1)` plus a per-filter SHIFT `s`, and
both halves were the reader's, not the format's.** The shift existed because
`directionalwarp` and `emboss` begin at bit 1, and a straddle table in `decompose` existed
because `blend`'s relocated opacity begins at 9 and `transformation`'s offset at 25 — odd
bits, which no shift of an even grid can reach, so each appeared as two phantom half-fields,
"one that always looks like a value and one that always looks like a pointer". Reading each
field at its own bit removes the shift, the straddle table and the phantoms together; the A/B
that landed it moved **no** slot position or width anywhere in the corpus, on any of
`inputs`, `cls_slots`, `param_slots`, `cls_params`, `end`, `hdr`, `prog` or `size_slot` over
903,440 records.

`emboss` is the case that first forced an odd offset, and its arbiter was not the fit.
Read at bit 0 it was the only filter in the corpus that failed §6.3's program check, and it
failed it completely — 450 slots whose state says `program` and not one of which decodes.
Read at bits 1, 3, 5, 7, the header length is reproduced on **375 of its 375** covered
records and the two words in question are the plain floats they look like (1.0 and 0.25 on
`sci_fi_elements_02` record 3807). §6.3's program check reads **198,224 of 198,224**
corpus-wide, where it read 198,581 of 199,031 — the whole residual was this one filter's
offsets. The measurement is in FORMAT-NOTES.md, "Every filter, bit by bit", and the A/B
appended after it. The two bits are a STATE, not a count:

    00  absent          the parameter is not present; it costs no slot
    01  baked           a constant, inline in the header, one word per component (§7.3)
    10  program         a pointer into the instruction stream (§10)
    11  image input     an edge — a backward record index, not a parameter at all

**The state legend has one exception, and it is a field that is not a parameter.**
`distance`'s field 0 declares that filter's optional mask INPUT from its LOW BIT alone, so
`01` adds an edge where the legend above would read a baked value — see §6.3. Such a field
takes no place in the parameter block, and the tell is its cost: one word in `01` and `11`
and none in `10` tracks a single bit, where a parameter costs a word for its value and a
word for a pointer.

**Placement is a cursor, not an index.** The walk visits fields in ascending bit order, and
each present field advances the cursor by its own width. Nothing stores a slot number (§6.1),
so a parameter's position is the sum of the widths of the fields before it and cannot be
computed from its offset alone.

**A parameter's presence mask is exactly `3 << b`.** This is what makes the rule one
rule rather than a per-filter table: over the five filters that declare parameters, all
fourteen masks resolve to exactly one field, by a single shift-and-compare —

    blend            opacitymult 0x0030 -> bit 4    opacitymult 0x0600 -> bit 9
    dirmotionblur    intensity   0x0003 -> bit 0    mblurangle  0x000c -> bit 2
    directionalwarp  intensity   0x0006 -> bit 1    warpangle   0x0018 -> bit 3
    levels           levelinlow  0x0003 -> bit 0 ... levelouthigh 0x0300 -> bit 8
    fxmaps           fx_param0   0x0003 -> bit 0 ... fx_param3   0x0300 -> bit 8

**THE OFFSETS ARE DERIVED, NOT STATED, and a reader should know which half of this section
is measured.** The fields, the state codes and the cursor are all read from the file. Where
each field BEGINS is not: it is 32 numbers derived from the corpus by
`archive/tools/derive_legend.py`. What supports them is not one argument:

* **Structural, and independent of any solve.** `w1` bit 0 is set in **0 of 62,898**
  `directionalwarp` records, against a control of 247,561 of 431,890 across `blend`,
  `dirmotionblur` and `levels`. A zero that large with a live control is the file saying bit
  0 carries nothing for this filter. Note precisely what it settles: its first field
  **cannot begin at bit 0**. It does not establish that it begins at bit 1.
* **The values, on both arms.** `blend`'s relocated opacity at bit 9 is settled by what the
  slots hold, over the whole corpus and with 0 exceptions: code `01` gives 963 records
  holding a plain float in `[0, 1]`, none of which resolves a program, and code `10` gives
  170 records of which not one is a plain float and every one resolves a program. Read on an
  even grid the same two words are a pointer seen as the denormal 1.9e-39.
  `transformation`'s offset at bit 25 is the same shape: read at bits (25, 26) it is the
  ordinary alphabet — absent 144,245, baked 29,404, program 69,282, and `11` **never** —
  while bits 24 and 27 are set in no record at all.
* **`emboss`'s program check**, above: 450 non-resolving program slots at bit 0, 0 at bit 1.
* **Independent of the width model.** The field rule and the retired positional rule produce
  identical name lists on 78,783 of 78,783 records. The positional rule never decomposes
  `w1` into fields at all, so this agreement does not rest on the legend.
* **Parsimony, and it should be discounted.** An exact reproduction of the header length is
  not evidence about the decomposition — a misaligned decomposition can sum correctly, which
  is why nothing caught the even grid for as long as it stood.

So the honest statement is that the file forecloses some starting positions and the rest are
inferred from what the slots hold. Read alongside §7.3: the format states the width legend,
and what it does not state is the KEY — which field carries which type, and where each field
begins. Two halves of one missing declaration.

`directionalwarp` is the reason an offset must be read rather than assumed. Its `intensity`
is bits 1 and 2, which STRADDLE the fields of an even grid; a matcher that assumes bit 0
finds no field for it, names neither of its parameters, and returns nothing on 62,146
records — silently, because an empty parameter list is indistinguishable from a filter that
declares none.

**The rule subsumes the positional fallback it was thought to need.** Because of that
straddle, `directionalwarp` was placed by a separate positional rule — "the present
parameters occupy the last `n` slots of the header". Read at its own offsets, the field rule
and the positional rule produce identical name lists on **78,783 of 78,783** records across
both filters that use it. The positional rule is not a second mechanism; it is this one seen
from the far end of the header.

**Where it is vacuous, and that is not a gap.** `fxmaps` has no parameter fields at all — the
walk reports zero on all 41,901 records — and its parameters live in the FX entry table (§8)
rather than the record header. The masks above are still well-formed, they are simply never
matched. A memo that attributed header parameters to it named **0 of 95,426** slots inside the
header it claimed them from, against `levels` at 160,106 of 169,219 (94.61%): the two are not
one rule at two severities but a working rule and a baseless attribution.
---

## 8. FX-Map trees

`fxmaps` records (filter id 4) contain a tree of pattern-generator nodes, reached from a
forward pointer at slot 2 (`node_ptr + 52`). A tree holds two distinct structures,
discriminated by the tag word's **low nibble**:

- **nibble 9 or 0xB → a node header.** A node is the mask-walk one scale down:
  `[tag][fields]`, where the low byte's high nibble (bits 4-7) is a presence mask over the
  fields and the successor pointer follows them. The successor word offset is derivable, not
  tabled: `successor_word = base + popcount(header & 0xF0)`, `base` = 1 (nibble B) or 2
  (nibble 9) — verified 30/30 over every header seen 10+ times. Each set bit inserts one
  field: bit 4 a branch (two children, e.g. `0x1B`), bit 5 a `randomseed` program, bit 6 a
  baked `randomseed`, bit 7 the base program+successor structure. So `0x0b` is a leaf
  (successor at word 1), `0x18b` puts its successor at word 2, `0x1ab`/`0x1cb`/`0x89` at
  word 3, `0x99`/`0x1db` at word 4.

  **Bit 4 makes a branch on a NODE too, not only on a leaf, and the successor rule does not
  see the second child.** `0x1db` (bits 4, 6, 7) is the case, and all 23 in the corpus are
  one structure byte for byte: `[0x1db][2][program][child][child][0x09000013]`. The
  computed successor — word 4 — is the *second* child; word 3, which the mask spends on
  bit 6's baked `randomseed`, is the first. It is a child and not a value that happens to
  dereference: **the program at word 2 ends exactly where word 3's target begins, 23 of 23**,
  so the child abuts its own node's program, the same contiguity `0x1B`'s sentinel form uses.
  Following it reaches an entry table in 20 of 23 against 0 of 23 for the neighbouring word
  as a control, and the same test over every other family stays at the noise floor (`0x89`
  w2 1 of 47, `0x1cb` w2 2 of 30, `0x99` w3 0 of 44). Both children are `0x1a3` and open
  identical chains. The node's program is not a selector: one distinct source across all 23,
  reading nothing, writing constants to slots 1–6 and returning a literal `1` — a state
  initialiser, which is the role `0x1B`'s program also plays. So `0x1db` is the `0x1B`
  BRANCH shape wearing bit 7, and a reader that dispatches on bit 7 first will never see it.

  **A reader following only the computed successor draws half of such a record.** 23 records
  across 12 files walk one table entry and drop one, and the two carry different parameter
  masks (`0x55300158` dropped against `0x05300758` walked, constant across every file — they
  cook from one template). Whether the engine draws both children or selects one is **not
  established**: no specimen with a `0x1db` ships an export.
- **nibble 8 → a paramset table entry**, *not* a node. The entries are a **linked list**:
  each entry stores a pointer to the next one — the header slot reaching furthest forward,
  past the entry's own inline program. The entry ends at its inline program, whose length the
  program states itself (a `u16` instruction count in its first word), so the entry extent is
  the program's structural length, not a tabled stride. (An earlier `FX_ENTRY` stride table
  was a per-tag *fit* of this pointer's distance, and lossy because the distance is the inline
  program's length, which the tag does not encode; following the stored pointer reaches ~78k
  entries the strided walk stopped short of, with zero phantoms.)
- **high half `0x0002` → a chain** — the commonest entry, `0x00020008`, whose slot-1 pointer
  is the next-pointer 100% of the time. These are structural linked-list cells, not
  independent pattern draws, and are excluded from both node sizing and emission.

Nodes carry the FX-Map parameters (pattern type, size, colour, etc.). The pattern
*footprint* (`patternsize`) — how large each emitted pattern is on the canvas — is the one
FX-Map field not yet decoded, and is the principal blocker to correct rendering. How many
patterns a record emits, and where each lands, is §13.7.

---

## 9. Embedded resources (resource table)

When `base != 0`, the resource segment `[0x38, base+0x38)` holds raw image payloads, and a
**resource table** sits immediately before the interface block: one 8-byte record per
image.

```
u32 format_tag
u32 offset            byte offset of the image within the segment (+4)
```

`format_tag` decodes as four bytes: `[3]` format (`01`=L, `02`=RGB, `03`=RGBA, `05`=L16,
`07`=RGBA16), `[2]` depth (`08`=8-bit, `18`=16-bit), `[1]` = `log2(h)<<4 | log2(w)`
(`0xAA` = 1024×1024), `[0]` colour flag (`20`=grayscale, `21`=colour). The three fields are
mutually consistent (bytes-per-pixel = channels × depth). Records sit 8 or 32 bytes apart
depending on the file, so the table is found by *scanning for valid tags*, not walked at a
fixed stride. Consecutive offsets give each image's size; the sizes sum to the segment
length exactly (a strong integrity check). Dimensions resolve for 190/200 images, almost
all 1024×1024.

### 9.1 The segment is not images only — filter 17 stores a string and a font in it

A `text` record's base region is five words, `[w0][w1][zero][string ptr][font ptr]`, and both
pointers carry the format's universal `+52` skew, so they are ordinary offsets into this
segment rather than a private encoding.

**`words[3] + 52` — the string.** `[u32 count][u32 codepoint × count]`, one codepoint per
word. When `w1` **bit 1** is set the same word is instead the `uid` of a **type-6 (string)
graph input**, and the manifest's `default=` for that uid carries the text. The discriminator
is the bit and never the value, because both arms hold an ordinary 32-bit word. Over the
corpus all 59 text records resolve: 38 through the segment, 21 through a graph input.

**`words[4] + 52` — a complete font.** `[u32 hash][u32 length][sfnt]`, where the payload is a
whole TrueType file (`00 01 00 00` on 13 of 14 distinct payloads, `ttcf` on the 14th). The
length field is structural rather than inferred: `off + length` lands exactly on an offset
another record of the same file names as *its* string, on 8 of 14, with no record naming an
offset one word to either side. It is **per record, not per file** — one package carries two
faces and its signature record points at the second, which is the one place on it whose
glyphs are a script face.

The compiled record therefore names **no font family anywhere a reader can see**: the family
exists only inside the payload and in the `.sbs`. Nothing inside the payload has been read
here beyond those four magic bytes and the stated length. That restraint is a licence
question about the type foundry, and is deliberately *not* the Adobe provenance rule of §12 —
the two are separable and are kept separate.

---

## 10. Instruction stream (the ISA)

Computed parameters are **bytecode programs** reached from record slots. A program is a
sequence of instructions in a `u16` token stream (little-endian **`(u16 arg, u16 opcode)`**
words, opcode in the high half).

### 10.1 Encoding

Each instruction is one opcode token followed by its operand tokens (three-address code,
one result per instruction, contiguous SSA value numbering).

| bits | field |
|---|---|
| 15–10 | operand-token count — **instruction length = this + 1 tokens** |
| 9–8 | type: 0 bool, 1 float, 2 int (3 unused) |
| 7–6 | component count − 1 |
| 5–0 | operation id |

The length rule `length = (opcode >> 10) + 1` holds for **every** opcode in
`0x0400–0x7FFF`, so any program can be fully tokenised with no semantic table — unknown
operations are skipped exactly, not guessed past. (Records, `0x8000`+, are exempt: they
are 4-aligned and separately framed by the directory.)

### 10.2 Operands and immediates

Most operands are value numbers naming an earlier result in the same program. Some are
immediates: the swizzle mask, variable-slot indices, the index read by `0x03`/`0x06`, and
the 4-byte immediate of a constant (`0x00`) or an **input reference** (`0x02`). Constants with a 4-byte immediate
come in two forms differing by `0x0400` (a 2-byte alignment pad).

**Inputs are referenced by uid**: a reference opcode is followed by a `u32` input uid, and
bits 6–7 of the opcode encode component count − 1 (`0x0902/0x0942/0x0982/0x09C2` =
float1..4; `0x0A02/0x0A42` = int1..2) — a clean 100% mapping over 326,768 references.
**Outputs are positional**, identified only by index in the interface block's output array;
they never appear in code.

### 10.3 Operation set

**41 operations in 63 type-specific forms, all named** (see `OPCODES.md` for the full
table), covering 96.5% of decoded instructions by operation-id on distinct specimens; the
residue is component/length variants plus decode noise. Seven further operations — `0x03`,
`0x0B`, `0x0F`, `0x1E`, `0x2A`, `0x35`, `0x36` — fall below that catalogue's ≥20-specimen
threshold and are established structurally rather than by frequency; they sit in the same
table, marked `*`.

The catalogue is grouped by family, by operation id within a family:

| ids | family |
|---|---|
| `00`–`02` | values and references — constant, system variable, input reference |
| `03`, `04`, `07` | variable slots — get, set |
| `09`, `0B`, `0C` | control flow and structure — select/ifelse, `while`, sequence |
| `0D`, `0F`, `10` | vector construction and access — construct, `vec4`, swizzle |
| `11` | type conversion — tofloat / toint |
| `12`–`18` | arithmetic — add, sub, mul, div, mod, neg, dot |
| `1D`–`22` | comparison — eq, neq, gt, gteq, lr (less than), lteq |
| `1A`–`1C` | boolean logic — and, or, not |
| `23`–`25` | sign and rounding — abs, floor, ceil |
| `26`–`2B`, `2D`, `35`, `36` | transcendental — cos, sin, sqrt, ln, exp, exp2, atan2, log2, pow |
| `2E`, `2F` | geometry and interpolation — cartesian (polar → xy), lerp |
| `30`–`32` | range and noise — min, max, seeded rand |
| `33`, `34` | sampling — luminance, colour |

Family order follows operation id, with two departures the catalogue also makes: comparison
comes before boolean logic so the relational operators read as one block, and `0x35`/`0x36`
group with the transcendentals rather than sitting after the samplers their ids follow. `0x0D` construct
always takes exactly two operands and concatenates; it and `0x0F` carry a declared `ncomp`
that is authoritative over their operands' runtime widths. `0x0B` **`while`** is a loop —
operands `(init, cond, body, …)`, no immediate — and its operands name expression trees
re-evaluated per iteration, so it is the one instruction a straight-line translation gets
wrong. The compiler performs common-subexpression elimination and inlines sub-graph
instances, so instruction counts can be far below authored node counts.

### 10.4 System variables

`0x01` reads a system variable by immediate: 0 `$time`, 1 `$size`, 3 `$sizelog2`,
8 `$pos`, 10 `$number` (FX-Map only).

`$pos` means **two different things** depending on which program reads it — the sampling
coordinate in a `pixelprocessor`, the node's own base position in an FX-Map. Supplying the
first where the second is meant renders nothing. See §13.5.

---

## 11. Interface block

One per package, a footer immediately after the value table:

```
[value table][u16 n_out][u16 n_in][output uid array][input descriptor array][16-byte footer]
```

It aggregates every graph in a multi-graph package. `validate_corpus.py` confirms
`(n_out, n_in)`, both uid arrays, the footer, and the record directory on 383/383 specimens.

---

## 12. Provenance and scope

This specification was produced clean-room: no Adobe Substance engine binary was run,
disassembled, or inspected, and any source file bearing `<author v="Allegorithmic">` was
excluded from analysis. That exclusion is now a predicate rather than a habit —
`corpus.sources()` returns only permitted `.sbs` paths and `corpus.source_excluded()` checks
one, and every tool that reads a source goes through them. It was enforced by nothing until
a reading of FX-Map `$pos` was taken from an excluded file and had to be withdrawn; **131 of
the 491 sources here bear the tag**, and for FX-Maps specifically they are the whole of the
interesting population, so a negative measured over the permitted sources means "absent from
what may be examined" and never "absent from the format". The format's *structure* is fully recovered — a reader can locate
and walk every region above from the file alone. What remains open is *semantics*: the
meaning of some filter parameters, the FX-Map pattern footprint (§8), and a handful of
provenance-walled specifics (e.g. `vectorshape` layout, inline FX parameter names).

Rendering is no longer wholly open. §13 states a renderer completely enough to rebuild
one, and on the corpus specimen whose two graph inputs are `$outputsize` and `$randomseed`
— so that a colour mismatch cannot be an author's tweak before export — it reproduces all
six declared outputs against the package's own exported maps at r = +0.98 / +0.95 / +0.91
(basecolor), +0.96 (roughness), +0.97 (ambient occlusion) and a height mean of 0.7859
against 0.78628. What is not solved is generality: §13.6 names three filters that run at
defaults for want of a name-legend row, §13.7 names the footprint, and §13.8 names three
values the file does not contain at all.

---

## 13. Evaluating a graph — the renderer

Sections 1–12 are enough to *read* a file. This section is what a reader needs to *run*
one: `tools/render2/` is written from it and nothing else. Where a value is not in the
file it says so (§13.8); everything else is derived from the sections above.

### 13.1 Filter ids

```
0 gradient   1 blend    2 transformation  3 shuffle    4 fxmaps    5 vectorshape
6 uniform    7 warp     8 emboss          9 (unnamed) 10 blur     11 dirmotionblur
12 directionalwarp      13 sharpen       14 hsl       15 levels    16 bitmap
17 text     18 normal   19 dyngradient   20 pixelprocessor        21 distance  22 curve
```

Ids 5, 9 and 17 are not evaluated: 5 and 9 are provenance-walled (§12), 17 is a glyph
source. The other twenty are §13.6.

### 13.2 The pass

**What a record is drawn at.** Its own tag, two nibbles: `width = 1 << ((tag >> 8) & 0xF)`,
`height = 1 << ((tag >> 12) & 0xF)`. One exception, and it is stated by a class bit rather
than guessed: on `bitmap` records class bit 13 (`word0 & 0x20000000`) is a 4×-**area** flag
the height nibble omits — 11 records across the corpus set it and all 11 store an image
exactly four times their declared area, against 0 false positives on ~570 bitmaps with the
bit clear, so `height` gains a factor of 4. Without it a decoder reads the top quarter of
each.

**Which records are outputs.** An 8-byte entry per declared output sits between the record
directory (§5) and the first record — one entry per output on 591 of 591 layout-A
specimens. Word 1 is the **record index** (a valid one in 3,249 of 3,249); word 0's low
half `>> 4` is the manifest's `format` attribute, and bit 2 of that is a grayscale flag
(98.5% grayscale when set against 4.2% when clear, over outputs whose identifier names
them). An entry whose high half is 2 — 48 of 3,249 — is a numeric **value** output rather
than an image, and all 48 name a `pixelprocessor`. This is the attribution earlier notes
called structurally absent; it is not absent, it is in a region nothing had read.

Every edge is a **backward** record index (§6.3), so one forward pass in index order
suffices — no topological sort. Each record produces an `(H, W, C)` image, `C` = 1 when
word0 bit 0 is clear and 4 when set. A record whose input has no output yet fails as a
*cascade* (a consequence); everything else is a *root* failure, and the distinction is
what makes a blocker census meaningful.

Conform each result to the record's own channel count, and refuse rather than invent:
3 channels on a colour record is RGB and gains an opaque alpha; a greyscale record whose
channels are identical is narrowed; anything else means the wrong program ran. Clamp only
**declared outputs** to [0, 1] — an intermediate above 1 is headroom a later multiply may
legitimately consume.

### 13.3 Reading a record's parameters

Three questions, three answers, and only the third needs the header length:

| question | answer | from |
|---|---|---|
| which parameters are present, baked or program? | the `w1` two-bit state | §7.4, the file |
| how wide is each baked one? | Float1/2/4, per-channel by the colour bit | §7.3, the file |
| where does the block start? | `header_end − Σ widths`, laid **forwards in ascending mask order** (except filter 17 `text` — §6.1, §13.4) | the width legend's header length only |

**Anchor at the end, not at the walk's forward cursor.** The cursor inherits any slot a
model mis-charges *before* the parameters; the end anchor is wrong only if the header
*length* is wrong, and the length is the one quantity a fit to observed boundaries
reproduces exactly whatever it does to the attribution. `normal` is the case that separates
them: a five-word header whose intensity is word 4, where the cursor said 6. Under §7.3's
width legend the two agree by construction — the base is `n_hdr + n_base + n_fixed`, three
counts the record states, and the forward cursor lands on the stated length in 903,301 of
903,301 corpus records — so the distinction is a check rather than a repair. Keep it: the
day it fires is the day a width is wrong.

**Check it.** Two slots can never hold a parameter, and neither answer comes from the
fitted per-field charge: an **input edge** (§6.3) and the two mask words. A block reaching
either means the name legend below is missing a field that sits after a listed one — the
whole block has shifted onto words that read as plausible floats. Refuse loudly. Silent on
84,700 records carrying named parameters: 0 reach either.

**The size slot is the one the class walk PLACES**, not the first slot of the class block.
Bit 16 is the lowest class bit but not always the first placed: a flag bit below it takes a
word first. Over 120 files the two answers differ on 7,590 records — `pixelprocessor` by one
slot 6,905 times, `dyngradient` by one 399, `normal` by two 246.

**And the class walk itself must not be run in plain ascending order (§6.1).** When class bits
16 and 23 are both set the size expression is the SECOND class slot; the first holds
`$randomseed`. 102,173 corpus records across 19 filters are affected — `pixelprocessor`
56,055, `fxmaps` 36,028, `transformation` 5,324, `blend` 2,445, `levels` 401, and fourteen
more down to `hsl` 3. The tell that a reader has this wrong is that its size slot resolves a
program returning one component, which no size expression does.

The walk reports it as `size_slot`, so a reader never reconstructs it. Two filters still
have no placement to report, for different reasons, and one has nothing to place.

**`emboss` was a VERSION story, and it is fixed.** `derive_costs` admits a class bit only
when it varies among the headers it can observe, and its population for filter 8 starts at v5
(`MIN_VERSION`). Bit 16 is set on every emboss record in v5, v6 and v9 (256, 87 and 32 of
each) and clear only in v2 (6 records) and v4 (4) — exactly the versions the cut excludes. So
the bit was constant by the gate, not by the format, and its word sat folded into a fitted
intercept of `4.5`.

The repair is the general rule: **identify a feature where it varies, apply it where it does
not.** The derivation now fits the excluded population too — not to ship its spec, whose
exactness is below the bar, but to read coefficients off it — and transfers a constant bit's
cost into the modern spec when, and only when, **every filter that can see that bit agrees on
it**. Bit 16 is charged 1.0 by all 20 such filters, so it transfers; bit 27 is charged 1.0 by
eight and 0.0 by two, so it is a per-filter fact and may not be borrowed. Without that second
test both moved, and the walk's cursor went from one word short of the fitted length to one
word long.

**Bit 27 is now MEASURED here rather than borrowed**, by pinning the intercept instead of
leaving it free. With `const` fixed at the record's own base region — 2 mask words + 2 image
inputs, plus the one word bit 16's transfer accounts for — a constant class bit can be given a
column of its own, where under a free intercept that column *is* the constant. `emboss` bit 27
comes out at 1.0, which is what eight other filters charge it and what its slot holds: the
`sysvar…exp2` `$pixelsize` program, at slot 5 of `sci_fi_elements_02` record 3807. `const`
comes out at the structural 4, where the free fit gave the half 3.5 — a half being the model
conceding it cannot express the rule.

**Under §7.3's width legend the same three bits come out the same way, by a route worth
stating because it needs no separate mechanism.** With the base pinned for every filter, bits
16, 19 and 27 are set on all 375 records the gate admits, so the solve sees only their SUM,
2. Bit 16 is 1 by the same format-wide agreement (every population whose records vary in it
charges 1, 35 of them) and bit 19 is charged by nobody anywhere — it is set on 903,608 of
903,616 corpus records and varies in no filter's population at all — so **the residual
determines bit 27 at 1**, and the closure is the check. Resolving one blind column at a time
and re-testing identifiability after each is what makes that work: pinning all three from
outside instead, which a first attempt did, leaves a word for the free columns to absorb and
`emboss` comes back at 0.008 exact with class bit 23 charged two words.

The transfer is prediction-preserving by construction — the bit is set on every record of the
population, so a word leaving the intercept and arriving on the bit cancels — and measured:
`header_words` is identical on all 546 emboss records. What changes is that the walk now
PLACES the word: `size_slot` comes from the class walk on all 375 walkable records, the last
caller-side guess is deleted, and the walk's own cursor matches the fitted header length on
**375 of 375**, where before the pin it matched 366 and before the transfer none. A further
171 records the walk still declines on the `min_version` gate. Corpus-wide the cursor now
equals the fitted length on every covered record of every filter, with no exceptions.

A second, independent thing had to be right for that to work. The fitted intercept was
answering two questions at once — how many words the masks and edges take, and where the
class block starts — and they are the same number only by arithmetic accident. Taking a word
out of the intercept deleted an EDGE from every emboss record until the base region was
derived from masks-plus-arity instead: `2 + arity` (`1 + arity` where the filter has no `w1`
word) agrees with the intercept on 321,054 of 321,054 interaction records, so separating them
changed nothing and made the transfer safe.

**`fxmaps`** used to be in the same position and is not: walking the class block from the
first slot after the inputs puts bit 16 there in 36,057 of 36,057 records — the walk's own
answer, formerly not emitted. Its fixed prefix (the FX tree root, §8) sits BEFORE the arity
run rather than after it, which is one of the two positions the legend has to state per
filter; the other is `pixelprocessor`'s own program, which comes after the class block. Its
`end` is the header length like every other filter's, and its `prog` is the
first-after-inputs slot — two numbers, not one, which is what it used to return.

**`vectorshape`** has no legend entry at all — the walk returns a stub with no size slot
and no class parameters. Nothing to place, and nothing to fall back to.

**The inherited size slot.** Class bit 0 (word0 bit 16) set ⇒ the first slot after the
base region is the record's output-size expression, not a parameter. Clear ⇒ there is no
size slot and that position is the first parameter. Reading it unconditionally is how a
`blur` whose 3-word header is `[tag][edge][intensity]` reports its intensity as its size.

### 13.4 The name legend

The one table the file does not state (§7.3). `(mask, shift)` is §7.4's presence mask;
`kind` is the baked width. A `program` arm is one pointer whatever its kind.

**Own parameters (`w1`)**

| filter | parameter | mask | shift | kind |
|---|---|---|---|---|
| 1 blend | opacitymult | `0x0030` | 4 | scalar |
| 1 blend | *(unnamed)* | `0x00C0` | 6 | 2 words |
| 1 blend | opacitymult, relocated | `0x0600` | 9 | scalar |
| 2 transformation | matrix22 | `0x000000C0` | 6 | Float4 |
| 2 transformation | offset | `0x06000000` | 25 | Float2 |
| 2 transformation | backgroundcolour | `0x10000000` | 28 | per-channel |
| 11 dirmotionblur | intensity / mblurangle | `0x0003` / `0x000C` | 0 / 2 | scalar |
| 12 directionalwarp | intensity / warpangle | `0x0006` / `0x0018` | 1 / 3 | scalar |
| 15 levels | levelinlow, levelinhigh, levelinmid, leveloutlow, levelouthigh | `0x0003`, `0x000C`, `0x0030`, `0x00C0`, `0x0300` | 0,2,4,6,8 | per-channel |
| 15 levels | *(unnamed)* | `0x0C00` | 10 | flag, 0 words in every state |
| 18 normal | intensity | `0x0003` | 0 | scalar |
| 21 distance | *(the mask input's declaration — not a parameter)* | `0x0003` | 0 | — |
| 21 distance | distance | `0x000C` | 2 | scalar |
| 18 normal | inversedy | `0x000C` | 2 | flag |
| 18 normal | input2alpha | `0x0030` | 4 | flag |
| 17 text | matrix22 | `0x0C00` | 10 | Float4 |
| 17 text | position | `0x00C0` | 6 | Float2 |
| 17 text | fontsize | `0x0300` | 8 | scalar |
| 17 text | align_flag | `0x3000` | 12 | flag, 0 words in every state |

**Filter 17's rows are written in block order, and that order is not ascending** — the one
exception to §6.1. `matrix22` (bit 10) comes first, then `position` (bit 6), then `fontsize`
(bit 8). The discriminator is not a preference: ascending order puts `fontsize` on the
matrix's `c` component and is **unrenderable on 14 of 14** records, while this order yields
diagonal matrices in five files, an exact rotation matrix in `Speed Limit`, and a layout that
reads — SPEED at y −0.22 above LIMIT at −0.03. The off-diagonals are *not* uniformly zero: a
first reading claimed they were and the test written to assert it failed at 3 of 14 (0.0033,
0.0033, −0.627).

`align_flag` is charged zero words in **every** state, so its mask state is its whole value
and declaring it shifts nothing. Its program arm (bit 13) is charged zero words too and is
unobserved across 437 files; a reader that charges it one word would shift the whole block,
so a file setting bit 13 is a thing to examine rather than to trust.

Two of these begin at an **odd** bit — `transformation`'s offset at (25, 26) and `blend`'s
relocated opacity at (9, 10). Under a reader that imposes an even grid `j → (2j, 2j+1)` they
STRADDLE it, their two states swap meaning between adjacent fields, and each appears as two
phantom half-fields, one that can only ever read `10` and one that can only ever read `01`.
That is the reader's frame and not the format's: a field begins at its own bit (§7.4), so
both match `3 << b` like every other, and `param_slots` reports them under bits 25 and 9
carrying the ordinary states. The `STRADDLED` relabelling table that used to put the halves
back together is gone with the grid that split them. A reader working from raw `w1` should
still match the **mask** rather than any index it has invented.

**`blend` states its opacity at one of two masks.** Connect the node's `opacity` input and
the field at (4, 5) goes to state 11 — the image-input code, §7.3 — and the slider moves to
(9, 10). Both are the same parameter: in `ChesterfieldSofa.sbs` exactly three blend nodes
have both a connected `opacity` port and a stated `opacitymult` (0.73, 0.40, 0.20), and
exactly three compiled records set (9, 10), holding those three floats; `SandyStonePath.sbs`
agrees five for five, program arm included. The two arms are exclusive by construction —
one two-bit code cannot read both 01 and 10 — so a reader may give them one name.

What (4, 5) reads under a set (9, 10) depends on which arm it is, and an earlier revision of
this paragraph had it as state 11 in all 1,133 cases. Corpus-wide it splits: **963 baked-arm
records read 11 at (4, 5) and the 170 program-arm records read 01.** The arms are told apart
by their VALUES with no exceptions in 437 files — every one of the 963 holds a plain float in
[0, 1] and resolves no program; not one of the 170 is a plain float and all 170 resolve a
program. That value split is also what pins the offset: read on an even grid the 170
pointers are denormals, 1.9e-39, which is an opacity of zero and a blend that composites
nothing.

**The class block ends exactly where the header ends, and a reader whose block runs past it
has mis-attributed a width, not found a longer header.** This was got wrong here, and the
shape of the error is worth stating because any reader fitting slot costs to observed header
LENGTHS can reproduce it. A header is `base + the cost of each set bit`, where the base is
the record's own structure — one or two mask words plus the filter's base image inputs. Fit
that equation with the base left FREE and the total still comes out right while the split
between base and bits does not: the fit is at liberty to shave words off the base and charge
them to a bit that happens to be set in every record. Nothing that compares lengths can see
it. A reader walking the same table FORWARDS from the real base then places the class block
too far right and runs past the end — on 7,119 records here (`shuffle` 3,514, `dyngradient`
2,214, `normal` 1,391), with the size expression landing two slots late on `normal` and one
on `dyngradient`, and on ~1,000 `normal` records landing on the slot the end-anchored
parameter block owns. `distance` ran its own parameter past the end on 2,360 more, for a
second reason on top of this one: its optional mask input was charged twice, once as the
edge it is and once as a `w1` field.

Pinning the base to what the record states and re-solving for the bit costs is exact on
every record of all three filters, needs no negative or half-word coefficient, and leaves
every header length unchanged. **That is now the whole model rather than a repair of four
entries** (§7.3): the base is pinned for every filter, every cell is one kind from
`0 1 2 4 C`, and 688 fitted numeric cells became 106 kinds over 107 cells with no intercept
to shave. The two answer the identical header length on 903,301 of 903,301 records with the
same 315 refusals, and the walks they drive agree slot for slot on 903,440 of 903,440.
Three things confirm the new placement rather than merely being consistent with it: the size-expression slot resolves as a valid program in 3,640 of
the 3,640 records where it moved, against 281 at the old position; `ChesterfieldSofa.sbs`'s
declared `intensity` 10.0 lands on the `w1` field the legend names, where it used to land on
the slot the walk called class bit 16; and the two independent placements — the forward
class walk and the end-anchored parameter block — now agree instead of colliding.

**What the corrected attribution says about the format.** `distance`'s `w1` field 0 is the
mask input's declaration and its field 1 is the radius, set out with its evidence in the
`distance` paragraph further down this section. **`normal`'s and `dyngradient`'s
over-charged bits were the record's own SIZE**: word0 bits 8–11 and 12–15 are the log2 width
and height (§6.2), and the fit — which offers every bit of word0 as a feature — charged a
word to bits 10, 11, 14 and 15, which are bits 2 and 3 of those two nibbles. It stayed
invisible because within log2 4…11 exactly one of bits 2, 3 is set in each nibble, so the
over-charge was a constant +2, and no `normal` or `dyngradient` record in the corpus is
outside that range. It is not invisible outside it: under the old table the same `normal`
record reads a **10-word header at 4096×4096 and a 6-word one at 8×8**, where its parameters
have not moved at all. Under the corrected table it reads 8 at every size, which is what a
header whose contents do not depend on the canvas must do. And `shuffle` has two
cost tables, one per record shape (§6.4): the one-channel shape bakes four `channelsweights`
words at bit 24 and carries no `w1`, the four-channel shape packs its per-channel selector
into `w1` and bakes nothing, so bit 24 costs 4 words in the first and 0 in the second. One
additive table cannot hold both without a negative coefficient, which is exactly what the
free-intercept fit produced.

**A reader should say what it declines to read.** An unnamed field is not an error — the
walk places it, so the layout is right — but it is invisible in a way an error is not: the
name resolves to a default, the default is the neutral value, and the record renders. `hsl`
was an identity in 747 corpus records and `sharpen` in 1,156 on exactly that mechanism.
Report per record the fields the walk placed and the legend does not name, as its own count
rather than folded into the assumed-value one: the two mean opposite things, and 57,731
`pixelprocessor` records carrying an unnamed class pointer would drown the other. Those
57,731 are not unnamed any more — the pointer is `$randomseed`, and the pixel program is the
LAST header word rather than the first slot after the inputs (§6.1) — but the accounting
point stands.

**A `flag` is zero words baked and one word as a program**, and both arms have to be
declared or the placement shifts. `normal`'s fields 1 and 2 cost nothing when baked — the
mask state IS the value — so omitting them looks free, but their program arm is a pointer:
38 corpus records put a program in field 1 while `intensity` is also a program, and an
end-anchored reader charging one width instead of two reads field 1's pointer as
`intensity`. Those 38 records ran the wrong program, and it evaluates to 0 on every one of
them — a flat normal where the file says 5, 10, 15, 20.

All three of `normal`'s fields are named, and what names them is **the program arm's
operand**, not a frequency asymmetry. A program arm here opens with `inputref` on a graph
input, and the `.sbsar` manifest names graph inputs. Over the corpus, resolving every one:
field 0's 275 programs return float1 in 275 of 275 and read inputs named `normal_intensity`
(205), `Normal` (18), `normal_strength` (13), `intensity` (6) …; field 1's 38 return a
BOOLEAN in 38 of 38, all of the shape `<input> == 1`, reading `normal_format` (34),
`generated_normal_format`, `NormalFormat`, `Format` and `normal_inverseDirection`; field 2's
one program returns a boolean read straight off an input named `Alpha_Channel_Content`. So
field 0 is `intensity`, field 1 is `inversedy` and field 2 is `input2alpha`. The return types
say the same thing without the names — float1 against boolean — and are why the two boolean
fields cost zero words baked: the mask state IS the value. A second witness, source-side:
`SBRustyTreadPlate.sbs` writes four normal nodes at intensity 6 / 15 / 3 / 10 and states
`inversedy 1` on exactly the intensity-15 one; its compiled twin's five records hold 15.0,
12.8, 3.0, 6.0 and 10.0, and the one carrying a field-1 flag is the 15.0 one. Reading any of
these as a single BIT rather than a two-bit code sees the baked arm and calls the program arm
absent.

The `levels` order is `(low, high, mid)`, not the UI's `(low, mid, high)`: over a corpus
sample `in_low <= in_high` holds 3,684 of 3,703 under this order and 641 of 751 under the
other.

**`levels` has a SIXTH field and it is left unnamed deliberately.** Field 5, mask `0x0C00`,
costs zero words in every state, so its mask state is its whole value — the same shape as
`text`'s `align_flag` and `normal`'s two booleans. It is set on 455 of 85,820 corpus records
and always in state 1, never 2, so it never takes the program form. It is listed here because
a reader that does not know it exists cannot report it, not because anything here can say what
it means: no permitted source declares a sixth `levels` parameter. What the file does say about
its population is structural and has a control. Among records baking exactly one named
parameter, that parameter being `leveloutlow` or `levelouthigh` at 0.5, a record with field 5
set has a partner in the same file reading the same input edge and baking the complementary
out-parameter at 0.5 in **436 of 440**; a record of that identical shape with field 5 clear has
one in **0 of 4,916**. The partner sets field 5 in 436 of 436. So within this corpus the field
marks membership of a complementary midpoint split pair — a signal cut into its upper and lower
halves — and marks nothing else. Its records are also fed by `pixelprocessor` in 45.7% of cases
against 0.16% for that matched control, the one filter whose output has no reason to lie in
[0, 1]. Naming it would change 0 of 85,820 readings, because it consumes no word.

**Inherited parameters (class word).** These class bits are shared rather than per-filter,
and a reader handles them once. Only bits 16 and 23 are universal — the high half is a
per-filter parameter list from bit 24 up, and four filters — `uniform`, `hsl`, `shuffle` and
`dyngradient` — put their own parameters at 24–27 (below).

| word0 bit | gates | cost | notes |
|---|---|---|---|
| 16 | `$outputsize` | 1 word | the size expression (§13.3). **Emitted after bit 23**, not before — §6.1 |
| 19 | *(unnamed)* | 0 words | set on 903,608 of 903,616 corpus records. Clear **iff the class word is exactly `0x0080`**, an exact partition; the 8 exceptions are `pixelprocessor` value nodes — 1×1, read by nothing, whose one class slot writes a scalar to the program cache. Not the OR of the other bits: a class word of `0x0008` (bit 19 alone) occurs on 114 records |
| 20 | the output's **format bit 4** | 0 words | over the 2,455 records a graph output names, format bit 4 is set on 94.67% when bit 20 is set and 0.60% when it is clear; within the 156 files whose own outputs disagree on bit 20 the two agree on 1,185 of 1,222 (97.0%). Format bit 4 separates two encodings of the same content — a depth flag by inference, since no manifest attribute states an output's bit depth |
| 21 | the output's **format bit 6** | 0 words | 98.46% when set (n=65) against 0.00% when clear (n=2,390). Format bit 6 is carried by formats 64 and 76 |
| 23 | `$randomseed` | 1 word | a program pointer returning a 1-component integer. **Emitted first** |
| 24, 25 | the filter's **sampling class** | 0 words | 0 for the pixel-local filters, 3 for the ones that read a neighbourhood; redundant with the filter id on 96.8% of records. `uniform`, `hsl`, `shuffle` and `dyngradient` put their own parameters at these bits instead, and are the only filters that charge a word for them |
| 26, 27 | `$pixelsize` | 2 words baked / 1 word program | an adjacent pair, lower baked and upper a pointer, **mutually exclusive on 124,388 of 124,388** records across `warp`, `blur`, `dirmotionblur`, `directionalwarp`, `distance`, `normal` and `sharpen`. The program arm reads a graph input the manifest identifies literally as `$pixelsize` (type 1, float2) on 7,000+ records and is otherwise a six-instruction `sysvar…exp2` computing a size ratio; the baked arm is a float2 — `blur` bakes an equal pair at a power of two on 5,150 of 5,159. `hsl` and `dyngradient` use the same two bits for their own parameters |

Bits 19, 20, 21, 24 and 25 have no cell in any filter's width legend, so they gate no stored
value and a reader that ignores them places nothing wrongly. Bits 20, 21, 24 and 25 describe
what the record PRODUCES rather than how its header is laid out, which is why probes against
the record's own geometry came back negative. Bit 19 is still unnamed.

**Bits 16 and 23 are named by the manifest, not inferred.** Both slots hold a program whose
first instruction is an `inputref` on a graph input uid, and the `.sbsar` manifest declares each
uid's `identifier` and `type`. Across every record setting both bits the bit-16 slot resolves a
**type 4** (int1) input on 46,124 records and the bit-23 slot a **type 8** (int2) on 45,632 —
`$randomseed` and `$outputsize` respectively, read off the manifest by uid. `fur_var_001`
declares `uid="4057753226" identifier="$randomseed" type="4"` and
`uid="2796450008" identifier="$outputsize" type="8" default="8,8"`, and its `levels` record 20
puts the first in the earlier class slot and the second in the later one.

The per-filter bits are an adjacent bit pair, lower = baked, upper = program:

| filter | parameter | word0 bits | width |
|---|---|---|---|
| 3 shuffle | channelsweights | 24 | 4 (one-channel shape) / 0 (four-channel) |
| 6 uniform | outputcolor | 24 baked, 25 program | 4 (colour) / 1 |
| 7 warp | intensity | 29 baked, 30 program | 1 |
| 10 blur | intensity | 28 baked, 29 program | 1 |
| 13 sharpen | intensity | 28 baked, 29 program | 1 |
| 14 hsl | hue | 24 baked, 25 program | 1 |
| 14 hsl | saturation | 26 baked, 27 program | 1 |
| 14 hsl | luminosity | 28 baked, 29 program | 1 |

`uniform`'s bit 25 is named the same way bits 16 and 23 are: on all 653 records that set it
the slot's program opens with an `inputref` on a graph input the manifest names `color`,
`metallic`, `rough`, `metallic_strength` or `roughness_strength`. `render2.model.CLS_NAMES`
carries bit 24 only, so the renderer finds this program with a value probe rather than by
name. `dyngradient` carries an unnamed pair of the same shape at 25 baked / 26 program — the
baked arm is 0.5 on 86 of 95 records and the program arm reads inputs named for a gradient
position — described but not named, `assume.QUESTIONS['dyngradient.gradpos']`.

`distance`'s radius is the source's own: `SandyStonePath.sbs` states 56.2999992 and
64.2200012 on its two distance nodes and records 3 and 180 of the compiled twin hold exactly
those. **That witness pins a SLOT, not a field**, and the difference cost this specification
a wrong reading for a while: on those two records the two candidate fields sit on the same
word, because the reader was charging `distance`'s optional mask input twice — once as the
edge it is, once as `w1` field 0 — and so began the parameter block one slot late.

**Field 0 is not a parameter. Its low bit declares the optional mask INPUT**, and that is
what its costs say: one word in states `01` and `11`, none in `10`. A cost that tracks bit 0
alone rather than baked-versus-program is not a parameter's; a parameter costs a word for its
value and a word for a pointer. Across the five `w1` codes the corpus holds, bit 0 set (5, 7,
9) gives two edges and clear (6, 10) gives one, 2,277 of 2,277. **The radius is field 1**,
whose two states are the ordinary pair.

The file arbitrates the difference outright. Over 2,411 corpus `distance` records, naming
field 1 yields 1,720 plausible baked radii, 509 baked zeros and 188 programs — and **all 188
decode as programs**. Naming field 0 yielded 638 "programs" whose slot does not decode (a
baked `12.8` read as an address), 105 "radii" that are denormals (a pointer read as a float),
3 records whose parameter block could not be placed at all, and 87 with no parameter found.

`sharpen` sits at the same pair as `blur`, on weaker evidence: no shipped source states a
sharpen parameter at all (all 28 nodes are at defaults), so this rests on the pair shape —
bit 28 holds an ordinary float on 1,148 corpus records (median 0.25) and bit 29 holds
integers on 8 — and on the position being the one the other one-scalar filter uses. Of the
1,148 stated values, **1.0 never appears**, which is consistent with 1 being the node
default this table assumes when the field is absent; that is an argument from an absence and
`blur`, whose modal baked intensity IS 1.0 at 10,200 records, is the standing reminder that
such an argument can be wrong.

`hsl`'s three come from the shipped sources: `ChesterfieldSofa.sbs` states `saturation`
0.65 with `luminosity` 0.60 on one node and `saturation` 0.58 on another, and the compiled
records set bit 26 to 0.65 / 0.58 and bit 28 to 0.60; `SandyStonePath.sbs` states
`saturation` 0.525 and its record sets bit 26 to 0.525. A node with all three dynamic
compiles to bits 25, 27, 29 in that order, which is what names the unpaired lower bit
`hue`. Corpus-wide the even bits hold floats in [0,1] clustered on the neutral 0.5 (bit 24
n=93 median 0.49, bit 26 n=203 median 0.43, bit 28 n=297 median 0.475) and the odd bits
hold integers, which is what a program pointer looks like read as a float.

**`$outputsize` is a graph INPUT, and a record's size is the default baked through it.**
The size in a record's tag (§6) is what the graph resolves to at the manifest's declared
`$outputsize` default — `Rokviz` declares `8,8`, so its output records read 256×256 — and an
exporter that sets `12,12` renders the same graph at 4096×4096. A reader that takes the tag
as the only size therefore renders one parameterization and cannot render the other, and a
cap like `max_dim` only lowers it. Scale-free channels are unaffected (`Rokviz`'s basecolor
correlates +0.98 against a 4096 export) but anything measured in pixels is not: the same
graph's normal map is flat at 256 and has slopes of std 0.211 at 4096, and its mean Z —
which is invariant under downsampling, so no resampling can reconcile it — is 1.0 against
the export's 0.899.

Resolution bounds that comparison but does not explain that particular render. Rokviz's
height is a near-Nyquist weave at 4096: its exported per-pixel gradient sd is 0.0457 there
and 0.00093 box-averaged to 256, a factor of 49 rather than the 16 a scale-free field would
give, so no 256-px render can carry its relief. What actually flattens ours is one filter
earlier — our `height` for this specimen correlates **−0.01** with the export at native 256
(against **+0.95** for Chesterfield, same measurement, same code path) while its amplitude
and mean are close. A normal map is a derivative; a derivative of the right statistics with
the wrong pixels averages to nothing. Score a derivative channel at its own resolution or
not at all: resampled to 64 the same pair reads `+0.94` and carries a `DEGENERATE` flag.

### 13.5 Running a program

`$size` is the **record's declared size**, always — it is a property of the file and a
caller's preview resolution must not reach it. `$pos` is the grid actually being drawn on.
Reset both on every call: a program evaluated with neither supplied must not inherit the
last record's, which is an order-dependent cross-record leak.

Of 6,793 program-valued parameters across a corpus sample, 5,338 read `$sizelog2`, 69 read
`$size` and **none** reads `$pos` — they are per-record constants. A `pixelprocessor`'s own
image program is the other population: it does read `$pos`, and for it `$size` and `$pos`
must describe the same grid or a neighbour tap goes sub-pixel and the filter silently
becomes an identity.

**`$pos` MEANS TWO DIFFERENT THINGS, and "the grid being drawn on" is only the first.** The
census above counts filter PARAMETERS and says nothing about FX-Map NODE programs, which
are a third population and a large one: 26,758 of 41,164 fxmaps records (65.0%) carry a
program that reads `$pos`. It is read at two components in 26,907 of 26,907 reads and
immediately ADDED in 99.5% of them. The split against the sampler is clean — of the programs
reading `$pos`, 54,661 of 55,462 `pixelprocessor` ones feed `samplelum`/`samplecol` (98.6%)
against **17 of 26,803** fxmaps ones (0.06%). Inside an FX-Map `$pos` is not a sampling
coordinate.

Its consumer is the GATE. Of 26,741 fxmaps records whose chain reads `$pos`, 26,591 read it
in an `0x89` gate's program and 150 in the stepper's, while only 34 read it in a named entry
parameter at all. The idiom is `$pos + <an offset the program itself scans>` tested against a
float4 rectangle the record bakes — a cull, not a placement. So `$pos` is the **absolute base
of a relative walk**: the scan the program keeps in its own slots is the relative part, and
`$pos` is what it is measured from.

**The value is the origin, and the record's own bounding rectangle says so.** Its bounds are
whole or half integers and the walk steps by whole units, so only `$pos` = 0 puts the scan on
the lattice the bounds are aligned to — a mechanism, not a fit. Emissions against the integer
cells each rectangle encloses: on the reference specimen, records 1/3 bound `[-13, 14]` in
both axes = 27², and emit 729 at the origin against 676 from a corner-based frame; another
specimen's record bounds `[-4, 5]` = 9², and emits 81 against 64. A corner frame misses on
three records and wins on none. It is also a per-node CONSTANT: every per-pattern candidate
breaks the same count (a `$number` cell grid gives 416 and 1,792 where the rectangles hold
729 and 10,000; any per-pattern jitter at all gives 716 for 729). And nothing argues it must
be non-zero — across 26,803 `$pos`-reading FX programs not one divides by a `$pos`-derived
value.

Two further things refuse the per-pixel reading outright: a walk consumes one verdict per
pattern, so a per-pixel `$pos` returns N verdicts of which all but the first are silently
dropped; and supplying the render grid takes the reference specimen from 70 rendered records
to 41 and removes `height` entirely. The remaining open case is a SUBDIVIDED FX-Map (§13.7) —
the chain walk is flat, so there is one node position and it is the root's. See
`assume.QUESTIONS['fx.pos']`.

**How an image reaches a program.** `samplelum`/`samplecol` take a **sampler index**, and
it is the *first* immediate in both their 2- and 3-operand encodings — established by the
arity bound: the first immediate is in range on 5,711 of 5,714 three-operand samples, while
the second is out of range 501 times and is the constant `1` in 5,696 of them. Bind sampler
`k` to the record's `k`-th edge (§6.3). A record with no edges that is itself a declared
output can still sample: bind then in the manifest's image-input declaration order, which is
the one thing the assembly cannot supply. Expect this to resolve few images and fail
honestly for the rest — of 120 graphs with image inputs, 107 have no manifest default on any
of them and ship no image either.

The `0x03`/`0x06` value cache is cross-record common-subexpression elimination: the writer
is one record and the reader another, so it needs one dict threaded through a whole file in
record order — which the §13.2 pass is. Its indices name no file, so it must not outlive
the render.

### 13.6 Filter semantics

`ref` = the record's own declared width (a pixel-valued intensity is relative to it, not to
a fixed 256). Sampling is bilinear and **wrap-tiled** throughout; `pos` is pixel-centred,
`(col + 0.5) / W`.

| filter | output |
|---|---|
| bitmap | the resource payload (§9), `u8`/`u16` → `[0,1]`; or a graph input's manifest default as a uniform |
| uniform | `outputcolor`; else a program at a walk-named slot; else the engine default |
| blend | `dst·(1−op) + f(dst, src)·op`, clamped; `op` = `opacitymult` (absent ⇒ 1, and read from EITHER mask — §13.4) × the mask edge if a third edge is present; `switch` selects on `op ≥ ½` instead |
| transformation | `in = m·(pos − ½) + ½ + offset`; area-prefilter when minifying |
| shuffle | colour bit clear ⇒ `Σ channelsweights·src` (grayscale conversion); set ⇒ four selector bytes in `w1`, `s` picks channel `s mod 4` of input `s div 4`. The width legend declares NO w1 field for filter 3 at all — the fitted table it replaced offered seven (0, 4, 5, 8, 9, 12, 13), every one charging zero words in every state, which was an artefact of a fit admitting any column that varies rather than a statement about layout. Either way it makes no claim the byte reading could contradict; nor can it confirm it. No shipped source contains a colour-arm shuffle node (44 are `grayscaleconversion`), so this one is read from the values alone: every byte holds 0–7, and a reader should refuse the record rather than guess when one does not |
| levels | `t = clip((src − lo)/(hi − lo))`; zero span ⇒ step at `lo`; `t ← t^(ln½/ln mid)`; `out = lo′ + t(hi′ − lo′)`, clamped. **Per channel**: on a colour record every field is a Float4 and its components genuinely differ — applying component 0 to all four remaps ALPHA by the red curve, which on one corpus record turns an opaque output almost transparent |
| curve | a cubic-Bezier transfer curve, sampled to a lookup |
| gradient / dyngradient | a ramp indexed by the input's channel 0; `dyngradient`'s ramp is a second input's long axis |
| hsl | RGB → HSL, then `hue += h − ½` (mod 1), `sat ← clip(sat·2s)`, `lum ← clip(lum + lu − ½)`, back to RGB; each of the three defaults to ½, which is the neutral value — so an unnamed parameter here is silently an identity |
| blur | separable box, radius `clip(\|I\|,0,256)/ref · max(W,H)` px; sub-pixel ⇒ identity |
| sharpen | `src + amount·(src − box₁)`; `amount` = `intensity`, absent ⇒ 1. Read the baked arm only and a stated 0 (6 corpus records) is indistinguishable from an absent one |
| dirmotionblur | 17 taps over ±L/2 along `2π·mblurangle`, `L = clip(\|I\|,0,256)/ref · 10` |
| directionalwarp | displace input 0 by `(2·h − 1)·I/ref` along `2π·warpangle`, `h` = input 1 |
| warp | displace input 0 by the **gradient** of input 1, scaled `·W/ref·I` |
| normal | `n = normalise(−gx·I·W/256, −gy·I·W/256, 1)`, `out = ½ + ½n`; `inversedy` negates `gy`. The reference is a **constant 256**, not the record's size: the engine's own exports give slope/gradient = 160.005 on a 2048-px Chesterfield export at `I` 10 and 9.397 on a 4096-px Rokviz export at `I` 0.25, against 160.000 and 9.405 predicted by a fixed 256 and 20.000 / 0.588 predicted by the record's width. Scale it by the record's own size instead and strength tracks the output resolution: at `$outputsize` 11 that takes Chesterfield's normal Z from 0.961 to 0.999 against the export's 0.966 |
| emboss | `base + k·(g₁(pos) − g₁(pos + (δ, −δ)))`, `δ = 0.005859375` |
| distance | a distance field grown from the mask input; the radius is `w1` field 1 (§13.4), baked or a program, and a fallback locator remains for the records that name neither — mark every record it answers for |
| pixelprocessor | the program at the **last header slot**, evaluated per pixel; earlier slots are inherited parameters and setup |
| fxmaps | §13.7 |

Blend modes: `0 copy, 1 add, 2 subtract, 3 multiply, 4 addsub, 5 max, 6 min, 7 switch,
8 divide, 9 overlay, 10 screen, 11 softlight`. Modes 2, 5 and 6 are corroborated
structurally: two records taking the same pair in opposite order under mode 2, combined by
mode 5, is `max(a−b, b−a)` — an absolute difference, which only parses if 2 is subtract and
5 is max.

### 13.7 FX-Map evaluation

Walk the chain of §8 nodes; the table entries at its end are the draws.

| node | role |
|---|---|
| `0x18B` `0x1AB` `0x1CB` `0x20B` | **iterate** — run the subtree `numberadded` times, `$number` = 0…n−1 |
| `0x89` | **gate** — its program returns a predicate; walk on while true |
| `0x99` `0x??9B` | **stepper** — a per-iteration state update (a raster/spiral position); run it, then continue |
| `0x??1B` `0x1DB` | **branch** — a state-initialiser program and TWO children (§8). `0x??1B` walks both; for `0x1DB` whether the engine draws both or selects one is unestablished, and a reader following only the computed successor draws half the record |
| `0x??0B` | leaf — the entry table draws |

**The emission count**, in this order:

1. If a placement program lays a `$number` **grid** — `floor($number / N)` — the bound is
   that grid's cell count `N²`, not `numberadded`, which for those records is an amount.
2. Otherwise, if `numberadded` is 1 *and* a placement program scales `$number` **linearly**
   by exactly one constant `1/N`, the bound is `N`. This is the file contradicting itself —
   a record computing N positions and visiting one — and it fires on 86 of 41,906 records.
   Read the constant off the **bytecode**, not off decompiled source: integer constants are
   spelled bare, and `const.i1 27` reinterpreted as float32 is 3.78e-44.
3. Otherwise `numberadded`.

Under 1 or 2 the chain's stepper and gate run **once**, not per emission: the placement
already carries each pattern's position and re-driving the spiral adds a second one.

**Drawing.** Each entry emits a pattern at `branchoffset + frameoffset`, of size
`patternsize`, rotated `patternrotation` turns, tiled at unit spacing; overlaps combine by
`max`. The shape is the entry tag's `patterntype` nibble (§8): `3 disc, 4 paraboloid,
5 bell, 6 gaussian, 7 thorn, 8 pyramid, 9 brick, 10 gradation, 11 waves, 12 half bell,
13 ridged bell, 14 crescent, 15 capsule, 16 cone`; nibble 0 is a catch-all that includes
Square. `imageindex`, when present, makes the pattern an input image sampled over its own
footprint.

**Still open** (§8): `patternsize`'s coordinate space. A median footprint of 2.82 unit
squares over-covers the canvas by orders of magnitude on most records, and no frame model
tested reconciles it. This is the principal remaining blocker to rendering FX-Maps
generally, and it is independent of the emission count above.

**Subdivision — not found.** A node whose children cover different parts of their parent's
region would give each child a different `$pos` (§13.5). None is in evidence. Of 155 distinct
node headers reached across the compiled corpus, `0x1db` is the ONLY one whose word 1 equals
its number of trailing node pointers, and it is two-way at every instance — no three- or
four-way variant exists. The shipped sources agree as far as they can be read: over 266
FX-Map graphs in the 34 third-party sources that contain one, **no node has more than one
child**, every node being an `addnode` with one successor, a one-child `markov2`, or a leaf
`paramset`. A two-way branch's arms cover the same region and share a position, so nothing
here subdivides.

This is a NEGATIVE BOUNDED BY THE CLEAN-ROOM RULE (§12), not a claim about the format. The
`.sbs` sources that do branch are Allegorithmic-authored and therefore excluded from
analysis, so the honest statement is that subdivision is absent from what may be examined —
not that Substance lacks it. Until a compiled subdividing node is found, an FX-Map has one
node position and it is the root's.

### 13.8 What the file does not state

Three values the compiler omits when the source left the node at its default, so they are
in neither the assembly nor the manifest. Any renderer needs them; every use should be
marked, because they are the only numbers in it that come from outside the file.

| value | used by | evidence |
|---|---|---|
| `channelsweights` | grayscale conversion | of 5,457 baked vectors corpus-wide the even weight `(⅓,⅓,⅓,0)` never appears, while its neighbours do — an argument from an absence |
| `uniform` fill | uniform with class bit 24 clear | black; one specimen's `metallic` output is such a record and its export is exactly 0.0 at every pixel |
| `levels` ranges | absent level fields | in `(0, ½, 1)`, out `(0, 1)` |

`normal` and `blur` intensities are also omitted on some records. There the honest answer
is to **refuse**: unlike the three above, nothing constrains them, and a rendered guess is
indistinguishable from a read.

Three filters have no located parameters at all and run at defaults everywhere — `sharpen`
(41 records sampled, 0 located), `hsl` (25, 0) and `text`. Naming their fields is the
obvious next increment and needs only §13.4 rows, not new machinery.
