# The `.sbsar` / `.sbsasm` format — specification

A concise, self-contained description of Adobe Substance's compiled material format, as
reconstructed by clean-room analysis. It is written to be *sufficient to build a reader*:
every structure below can be located by pointer arithmetic from the file itself, with no
fitted tables and no per-file heuristics. Counts quoted as support are measurements over the
437-file content-deduplicated corpus (`tools/corpus.py`) unless a narrower population is
named; the measurements themselves are in FORMAT-NOTES.md under the headings cited.

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
(computed parameters), a value table (graph-input defaults), and an interface block (the
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
| 0x1C | 4 | `filesize − 28`, a plain absolute offset (**not** `+52`-skewed): the last input descriptor's tail plus the footer (§4) |
| 0x20 | 4 | `0x00010002` (const) |
| 0x24 | 4 | `0` (const) |
| 0x28 | 4 | `1` (const) |
| 0x2C | 4 | value-table end, as a pointer (`table_end − 52`) |
| 0x30 | 4 | `2` (const) |
| 0x34 | 4 | `0` (const) |
| 0x38 | — | body begins |

**Version (0x04)** takes the values `0x0002_0000 … 0x0009_0000` and identifies *which
cooker published the file*, not a release date. It changes two encoding rules: the
image-input slot width in the graph-input table (from v8, §7.2) and whether a `warp` record
carries a `w1` word (from v9, §6.2). It is independent of the manifest's `formatversion`.

---

## 3. Overall body layout

```
0x00            file header (0x38)
0x38            embedded resource segment   ]  length == base   (image, string and font payloads; §9)
base + 0x38     record directory            ]
                records (code region)       ]
                value table                 ]
                interface block             ]   (ends with the input descriptors, §11)
filesize − 16   footer (root pointers, §4)
```

`base` is the size of the resource segment. **`base == 0`** for packages that embed no
images (the directory then starts at 0x38); otherwise the segment displaces the directory.
A reader must not assume the directory is at 0x38 — it is located from the footer.

---

## 4. Footer — the root pointers (last 16 bytes)

Four words at `filesize − 16`. A reader needs only the magic from the header; everything
else is reachable from here.

| word | meaning |
|---|---|
| 0 | **record count** `= (word2 − word1) / 4` |
| 1 | **record-directory start**, as pointer |
| 2 | **record-directory end**, as pointer |
| 3 | **value-table start**, as pointer |

So `dir_at = word1 + 52`, `count = word0`, `table_start = word3 + 52`, and
`base = word1 + 52 − 0x38`; the relation holds exactly on 437 of 437 corpus files. The 12
bytes before the footer are **not** footer fields: they are the tail of the interface block's
input-descriptor array (§11) — the last input's `(type, uid)` and, when there are two or more
inputs, the previous input's uid (437 of 437 and 411 of 411). A reader that treats the last
28 bytes as a seven-word trailer finds two "identifiers" and an "unexplained small enum",
which are those uids and that type (FORMAT-NOTES.md, "The 16-byte trailer, fully decoded").

---

## 5. Record directory

A contiguous array of `count` u32 **absolute file offsets**, strictly increasing, each
pointing at one record. Validated over the full length in every specimen. Sizes range
1 – 39,627 entries (median 1,016). A record's extent is `[offset[i], offset[i+1])`; the
last runs to the value table. **Record length is not stored** — it is framed only by the
directory, which is why a correct reader must always walk records from the directory and
never scan the body linearly.

---

## 6. Records — the mask-walk

A record is one filter node. Its layout is not tabulated anywhere; it is **walked** from
two bitmask words at its head. This is the single structural primitive of the format, and
it recurs at three scales (record header, FX-Map node §8, baked value width).

### 6.1 The primitive

A structured object is `[mask][fields…]`. The set bits of the mask, read in a fixed order,
enumerate which fields are present; **each field's width is a constant of its kind**.
Nothing stores an offset — a reader advances position by the width of each present field;
a writer emits in the same order.

**Record header order.** Each part is present only as the masks and the width legend
(§7.3) say:

1. `w0` (tag + class word, §6.2), then `w1` if the filter's shape carries one (§6.2).
2. `fxmaps` only: its FX tree/table root pointer (slot 2, §8).
3. The image inputs, contiguous: the filter's base arity, or for the two arity filters the
   count stated in `w1` (§6.4); then `distance`'s optional mask edge (§6.3).
4. The filter's other fixed prefix: `gradient`'s and `curve`'s ramp pair, `bitmap`'s pixel
   word, `text`'s zero + string + font, `vectorshape`'s payload pointer.
5. The class block, in the emission order below; then `bitmap`'s conjunction word (§6.4).
6. `pixelprocessor` only: its own pixel program.
7. `transformation` only: the pointer that integer code 30 emits (§7.4).
8. The `w1` parameter fields, in ascending bit offset (§7.4) — except `text`, below.

**Ascending order has two exceptions.** A reader that takes ascending order as universal
places fields wrongly and gets plausible numbers rather than a failure.

1. **Filter 17 `text`'s `w1` parameter block** is laid `matrix22`, `position`, `fontsize` —
   bits 10, 6, 8 (§13.4). This applies to the parameter block alone (FORMAT-NOTES.md, "The
   parameters, and the one place the walk's general rule does not hold").
2. **The class block emits bit 16 LAST within the low class group (bits below 24), in EVERY
   filter; the filter's own bits 24–31 follow in ascending order.** Class bit 16 gates
   `$outputsize` and bit 23 gates `$randomseed` (§6.2, §13.4), so when both are set the
   `$randomseed` pointer takes the first class slot and the size expression the second.
   Class bit 22 — one word, set only on `Texture_Randomizer` records 0, 2 and 5 (`fxmaps`) —
   also precedes bit 16, so a pairwise "23 before 16" swap is wrong on exactly those three.
   Only this rule puts a two-component (size) program at bit 16's slot on all 214,298 records
   where candidate orders differ (FORMAT-NOTES.md, "H3 survives in a STRONGER form"; "Three
   arbiters, none of them the walk").

   No filter is exempt: `pixelprocessor`'s header is
   `[w0][w1 arity][image inputs][bit 23][bit 16][its own pixel program]` (FORMAT-NOTES.md,
   "Fix 1 — `pixelprocessor`'s class block"), and `vectorshape`'s bit-16 slot is slot 2, after
   its payload pointer, where it resolves the record's own size on 127 of 127
   (FORMAT-NOTES.md, "4. `vectorshape`").

   *Open:* "bit 16 last in the low group" and "system variables first, then the filter's own
   bits" predict the identical order on every corpus record, because bits 17–21 cost no word
   in any filter; a record setting a costing class bit in 17–21 with bit 16 would separate
   them, and the corpus has none.

A reader that walks the class block in plain ascending order still gets the header LENGTH
right — both bits cost one word — so nothing overruns and no parameter moves. What it
gets wrong is which slot is the size, and silently: the misread slot holds a one-component program,
which a reader requiring two components discards instead of reporting (FORMAT-NOTES.md, "The
fourth class-block walk, and one loop instead of four").

### 6.2 The two header words

```
word0:  low16  = bit 0     colour flag (0 grayscale, 1 colour)
                 bits 1-7  filter id, as (low16 & 0xFF) >> 1
                 bits 8-11 log2 WIDTH        the record's own canvas (§13.2)
                 bits 12-15 log2 HEIGHT
        high16 = CLASS WORD — presence mask over INHERITED parameters
word1:          two-bit code per field — the filter's OWN parameters
```

The low half is **not** a presence mask and a reader must not treat it as one: two of its
nibbles are a size. The width legend (§7.3) has no cell on any bit below 16; a fitted cost
table that offers word0's low bits as features charges header words to the canvas (§13.4).

- **Class word (word0 high half).** Class bits are numbered by their **word0** bit position,
  16–31 ("class bit 16" is the class word's lowest bit). Each set bit that gates a stored
  value adds a field whose width is that (filter, bit)'s legend cell (§7.3), walked in the
  §6.1 emission order. Two bits are universal: **16 = `$outputsize`**, one word, a pointer to
  the size-expression program (which returns an int2); **23 = `$randomseed`**, one word, a
  pointer. Bits 24–31 are a per-filter parameter list keyed on (filter, bit), usually as an
  adjacent baked/program pair — e.g. bits 26/27 are `$pixelsize` in `warp`, `blur`,
  `dirmotionblur`, `directionalwarp`, `distance`, `normal` and `sharpen`: 26 a baked float2
  (2 words), 27 a program pointer (1 word), never both set (§13.4; FORMAT-NOTES.md, "Class bits
  26 and 27 are `$pixelsize`"). **A set bit can cost nothing** (bits 19–21 never cost a word),
  and a reader that gives every set bit a slot runs its block past the end of the header
  (§13.4).
- **Whether a record has `w1`** is a per-filter rule (`legend.json` `has_w1`):
  *always* — `blend`, `transformation`, `fxmaps`, `emboss`, `dirmotionblur`,
  `directionalwarp`, `levels`, `text`, `normal`, `pixelprocessor`, `distance`;
  *never* — `gradient`, `vectorshape`, `uniform`, `blur`, `sharpen`, `hsl`, `bitmap`,
  `dyngradient`, `curve`; `shuffle` — iff tag bit 0 is set; `warp` — iff the assembly version
  is ≥ `0x0009_0000` (without the version, refuse). A reader that charges a mask word to a
  record that has none comes out one word long, silently (FORMAT-NOTES.md, "Draining the memo:
  the rest of `layouts.json`").
- **Word1 two-bit codes:** each of the filter's own parameters is a 2-bit field:

  | code | meaning | cost |
  |---|---|---|
  | `00` | absent | 0 words |
  | `01` | baked (value stored inline in the record header) | width of the field's kind |
  | `10` | program (a bytecode pointer) | 1 word |
  | `11` | image input (an **edge**) — for a field declared as an input | 1 slot |

  Whether a `11` field is an edge is a fact of (filter, bit offset), decided from the header
  and never from the slot's value: `blend`'s bit-4 field is an input; `emboss`'s and
  `directionalwarp`'s bit-3 fields in state `11` hold a one-word parameter, not an edge
  (`decompose.INPUT_FIELDS`; FORMAT-NOTES.md, "The walk is fixed: image inputs are now read
  from the header alone").

**Field kinds and widths** (words): `0` = 0; scalar `Float1` = 1; `Float2` = 2;
`Float4` = 4; *per-channel* `C` fields are 1 when grayscale and 4 when colour, selected by
word0 bit 0. No other width occurs — "4 is the widest scalar the format has".

### 6.3 Edges (graph connectivity)

An **edge slot** holds a **backward record index**, 0-based (the index of the record that
feeds this input; `0` is record 0), or the sentinel `0xFFFFFFFF` for an absent input
(FORMAT-NOTES.md, "Edge value 0 is record 0, not 'no input'"). Edges come from: the filter's
base image inputs or its `w1` arity count (contiguous from slot `n_hdr`, after `fxmaps`' root
pointer — §6.1), `distance`'s low-bit mask edge (below), and `w1` fields in state `11` that
are declared inputs (§6.2), at their place in the parameter block. Because edges are backward
indices, a walk can be checked loudly: any slot the walk calls an edge must hold a value
`< own index` or the sentinel, or the walk is wrong.

**One `w1` field declares an edge on its LOW BIT, not on the full code `11`.** `distance`'s
field 0 charges a word in states `01` and `11` and nothing in `10` — a cost tracking bit 0
alone, which no parameter does: bit 0 set gives two edges and clear gives one, 2,277 of 2,277.
It is placed with the image inputs, is *not* part of the end-anchored parameter block
(§13.4), and must not be charged a word in it — doing so begins the block one slot late and
silently renames every parameter after it (FORMAT-NOTES.md, "The other half of `distance`").

**The same loud check applies to programs.** A slot the walk calls a program must hold a
decodable program at `value + 52`, exactly as an edge slot must hold a backward index.
Assert it rather than assume it: a mis-charged field reads a baked `5.120025` as the address
`0x40a3d70a + 52`, a wrong value renders while a wrong address does not, and only the check
makes the error announce itself (FORMAT-NOTES.md, "A baked radius read as an address";
"The two loud checks, and the arbiter that is not the walk").

### 6.4 The layout alphabets

The file states each filter's layout in one of three self-describing ways; a reader
handles all three with the one primitive and needs no fitted table:

1. **Two-bit presence codes** — word1 as above (blend, levels, transformation, warps).
   A field begins at **its own bit** (§7.4); there is no grid and no per-filter shift.
2. **Arity integer** — the header states an input *count* as a small integer in word1 and
   the walk reads that many edge slots (`pixelprocessor`, five bits at 0; `fxmaps`, six bits
   at 10, after its tree-root pointer).
3. **Paired conjunction** — two class-word bits that, set *together*, name one field
   (`bitmap`'s bits 24+27 = the pixel-offset word).

**Each class bit is always a pointer or always a value**, per (filter, bit); it is not a
positional count of "leading program slots". `blur`'s pointer bits are {16, 23, 27, 29} and
its value bits {26, 28}; `warp`'s are {16, 23, 27, 30} and {26, 29}. `warp` emits value bit
29 before pointer bit 30, which no count can express (`sbsasm.CLS_PROGRAM_BITS`;
FORMAT-NOTES.md, "SPEC 6.4's fourth alphabet: it is not a count"). Role is a name-legend
fact (§13.4), not a layout one: the header length comes from the widths alone (§7.3). So a
`blur` header with a baked `$pixelsize` (bit 26, two words) is one word longer than with a
computed one (bit 27, one pointer).

**Two-shape filters** state their shape with a single term: `shuffle` by tag bit 0 (the
colour flag) — `grayscaleconversion` (one input + a `channelsweights` vector, no `w1` word)
versus Channel Shuffle (two inputs + a packed channel selector in `w1`); `warp` by version
(§6.2); `distance` by `w1` bit 0 (§6.3) (FORMAT-NOTES.md, "The shuffle header reads 100%").

The walk reproduces record layout for **all but 5** of the corpus's 903,616 records. The 5
are filter 9, which no permitted source names and which has no legend entry; a reader refuses
them. (The fitted model the legend replaced also declined `vectorshape`'s 139 records and
`emboss`'s 171 pre-v5 records, 315 in all; both are ordinary legend entries — FORMAT-NOTES.md,
"1. `emboss`: the version gate was the FIT's"; "4. `vectorshape`".) What is behind the
provenance wall (§12) is filter 5's NAME, not its shape.

### 6.5 Which bits the corpus can actually separate

A per-bit claim is normally argued by scoring a model with the bit against one without it.
That argument is void when another bit is set on exactly the same masks: the two are one
column, every score is identical, and the tie reads as a confirmation. Two relations matter:

- **identical** — set on exactly the same masks. Fatal; no measurement over that population
  can name one rather than the other.
- **implies** — this bit's masks are a strict subset of the partner's. A real confound, but
  *arguable*: the partner's extra masks are the control.

`archive/tools/separability.py` reports both, and **no `identical` pair exists anywhere in
the corpus**, so every bit named in this document is in principle arguable. The subset
confounds (FORMAT-NOTES.md, 'The audit, and what "not separable" means'):

| population | not separable | separable |
|---|---|---|
| FX entry tags (158 masks) | bit 31 implies 7, 24 | the other 16 |
| class word, bits 16–31 (1,923 masks) | 16, 20, 21, 24–29 imply 19; 22 (n=3); 30 | only 19, 23 |
| w1, filter 1 (285,398 records) | 6, 11, 12 imply 8; 9, 10 imply 4, 5, 8 | 0–5, 8 |
| w1, filter 2 (215,444 records) | 4 (n=211,786) implies 2, 3; 28 (n=33) | 0–3, 5–7, 25, 26 |
| w1, filter 15 (76,879 records) | — | all of 0–10 |

**The population is part of the claim.** Bits 7 and 31 of the FX entry tag are co-extensive
over `FX_ENTRY_PROGS`' 57-tag key set but not over the corpus, where bit 31 is a strict subset
of bit 7 and 474 entries across 11 tags separate them. Enumerate from the corpus, and say so
when narrowing (FORMAT-NOTES.md, "First, a correction: the co-extensivity that started this
was a SUBSET ARTIFACT").

---

## 7. Parameters

A filter's parameters are either **computed** (a bytecode program) or **baked** (a
constant). Computed parameters are pointers into the instruction stream (§10). Baked
parameters are stored **inline in the record header, one word per component** (§7.3, §7.4) —
not in the value table, which holds the graph input defaults only (§7.1).

### 7.1 Value table

A single array from `table_start = footer word 3 + 52` to `table_end = header 0x2C + 52`.
It holds the **graph input defaults and nothing else**: the graph-input descriptors of §7.2
consume its entire stated extent in 437 of 437 files. 98% of its entries are byte-exact
against manifest defaults, the rest within float rounding, none unexplained. Values are
addressed positionally by the widths of §7.2.

A record's baked parameters are never here — the records carry 544,189 baked slots against
the corpus's 8,500 descriptors (FORMAT-NOTES.md, "The value table holds graph-input defaults
and nothing else"; "The interface block cannot be the legend: 1 : 64").

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

From assembly version v8 (`0x0008_0000`) an image input occupies a 16-byte `f32×4` slot at
its uid position (its scalar default in component 0, zeros elsewhere); before v8 it occupies
none. Getting it wrong shifts the whole table by `16 × (image count)`. Take the width from the
version, not by trial: on 2–4-entry tables both widths can appear to validate
(FORMAT-NOTES.md, "Graph-input default table — confirmed").

### 7.3 The width legend, and the key it is missing

§7.2's `type → 4N` table is the format's own width legend, and it is the whole of the
record-header model as well. The header length is one sum over it (`record_layout.header_words`):

```
header = n_hdr + n_base + n_fixed
       + SUM over set class bits of        width(kind)
       + SUM over w1 FIELDS -- a two-bit code AT ITS OWN BIT OFFSET -- of
             00 absent  -> 0        01 baked   -> width(kind)
             10 program -> 1        11 edge    -> 1
       + arity                (the two filters whose w1 holds an input count, §6.4)
       + distance's mask edge (w1 bit 0, §6.3)
       + one conjunction      (bitmap 24+27, §6.4)
       + one integer field    (`transformation`'s w1 bits 0-4, §7.4: a 5-bit value, one of
                               whose codes emits a program pointer, and whose unobserved
                               range 14-28 is REFUSED)

width:  0 -> 0   1 -> 1   2 -> 2   4 -> 4   C -> 1 grey / 4 colour
n_hdr = 1 + (this record carries a w1 word, §6.2)
```

`n_hdr` counts mask words; `n_base` is the filter's fixed image-input arity (§6.3), which for
`shuffle` equals `n_hdr`; `n_fixed` is its fixed prefix — the ramp pair, the FX tree root, the
bitmap pixel word, `text`'s zero + string + font, `vectorshape`'s payload pointer,
`pixelprocessor`'s own program. Every term is a structural count or a width from the type
legend. **There is no intercept, no float, no negative coefficient, no per-state cell and no
grid shift.** The table (`tools/legend.json`) is 109 kinds over 110 cells: 76 class-bit cells,
32 `w1` field offsets, `bitmap`'s conjunction and `shuffle`'s shape cell (FORMAT-NOTES.md,
"The legend, in full"; "H4 survives").

**Refusals.** `header_words` answers `None` — never zero — for a filter with no legend entry
(filter 9, 5 records), for a `w1` field in the baked state whose kind the corpus never
exercised (`fxmaps` `w1` bit 8), and for `transformation`'s integer codes 14–28 (§7.4). A
width nobody measured is not zero; a caller must refuse rather than lay slots against it.

**A kind is a pair of widths and the corpus does not always give both.** `Float1` is
`(1, 1)` and per-channel is `(1, 4)`, so a cell exercised in one colour only is a reading in
that colour and a *prediction* in the other. **37 of the 220 (cell, colour) pairs are in that
state**: 19 because the filter has no record of the other colour at all (`text` is grey on
all 59, `normal` and `hsl` colour on every one), 18 because none of its records sets the cell
(e.g. class bit 23 in colour for six filters). `legend.json`'s `evidence` map is the full list.
An implementation must mark those as predictions, not store them as measured values.

**Every baked parameter slot is 1, 2 or 4 words.** Over 437 specimens, none of the 544,189
baked slots the walk reads falls outside the legend's 1..4, and width 3 (`float3`), though
legal, does not occur (FORMAT-NOTES.md, "The legend is not the gap -- the KEY is"). Per filter:

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

`emboss` has no row: its baked `w1` fields 1, 3, 5, 7 (widths 1, 1, `C`, `C`) were not in the
population this table was taken over. Re-take the table with one instrument before quoting it.

**A width does not decide a ROLE.** `blur`'s class bits 27 and 29 are one word each and both
are pointers; `warp`'s bit 29 is one word and a value while its bit 30 is one word and a
pointer. A `1` in the legend means "one word", never "a pointer"; which one-word cells hold
pointers is a name-legend fact (§6.4, §13.4).

**What the file does not state is the per-field type CODE** — the *kind assignment* per
(filter, cell) that the legend table supplies. No per-node type declaration exists: the
interface block's typed descriptors cover the graph-input table only (§7.1) and the directory
holds bare offsets. The filter id *is* the declaration; its parameter list lives in the
engine. One kind is stated rather than assigned: a `channel` field's component count is the
tag's colour bit — 4 words colour, 1 grayscale (`walk._field_width`). *Open:* the rest of
the assignment; its legitimate route is the permitted `.sbs` sources, which declare parameter
names and types per filter.

### 7.4 The field primitive — how `w1` gates and places a parameter

One rule places every parameter this project reads: the §6.1 mask-walk applied to the second
header word.

**`w1` is a set of two-bit FIELDS, and a field begins at ITS OWN BIT.** There is no grid.
A filter declares an offset per field and the field occupies bits `(b, b + 1)` —
`directionalwarp`'s are at 1, 3 and 7, `emboss`'s at 1, 3, 5 and 7, `blend`'s at 4, 6 and 9,
`transformation`'s at 6, 25 and 28, `levels`' and `fxmaps`' at 0, 2, 4, 6 and 8, `text`'s at
6, 8 and 10, `dirmotionblur`'s at 0 and 2, `normal`'s at 0, 2 and 4, `distance`'s at 2. The
two bits are a STATE, not a count:

    00  absent          the parameter is not present; it costs no slot
    01  baked           a constant, inline in the header, one word per component (§7.3)
    10  program         a pointer into the instruction stream (§10)
    11  image input     an edge — a backward record index, not a parameter (§6.2's caveat)

**The state legend has one exception, a field that is not a parameter:** `distance`'s field
0 declares that filter's optional mask INPUT from its LOW BIT alone, so `01` adds an edge
where the legend would read a baked value (§6.3). It takes no place in the parameter block.

**Placement is a cursor, not an index.** The walk visits fields in ascending bit order
(`text` excepted, §6.1), and each present field advances the cursor by its own width.
Nothing stores a slot number, so a parameter's position is the sum of the widths of the fields
before it and cannot be computed from its offset alone.

**A parameter's presence mask is exactly `3 << b`.** Over the five filters with named `w1`
parameters, all fifteen masks (fourteen parameters; `blend`'s `opacitymult` has two) resolve
to exactly one field by a single shift-and-compare (`sbsasm.PARAM_SPEC`) —

    blend            opacitymult 0x0030 -> bit 4    opacitymult 0x0600 -> bit 9
    dirmotionblur    intensity   0x0003 -> bit 0    mblurangle  0x000c -> bit 2
    directionalwarp  intensity   0x0006 -> bit 1    warpangle   0x0018 -> bit 3
    levels           levelinlow  0x0003 -> bit 0 ... levelouthigh 0x0300 -> bit 8
    fxmaps           fx_param0   0x0003 -> bit 0 ... fx_param3   0x0300 -> bit 8

**The offsets are derived, not stated.** The fields, the state codes and the cursor are read
from the file; where each field BEGINS is 32 numbers derived from the corpus by
`archive/tools/derive_legend.py`. Their support:

* **Structural:** `w1` bit 0 is set in 0 of 62,898 `directionalwarp` records (control: 247,561
  of 431,890 across `blend`, `dirmotionblur`, `levels`) — its first field cannot begin at bit 0,
  which does not by itself put it at bit 1.
* **Slot values:** at `blend`'s bit 9, code `01` holds a plain float in `[0, 1]` on 963 of 963
  records and code `10` a resolving program on 170 of 170 (FORMAT-NOTES.md, "`blend`'s opacity
  moves when its mask port is connected"); `transformation` read at (25, 26) is the ordinary
  alphabet with `11` never, and bits 24 and 27 are never set (FORMAT-NOTES.md, "Corrections to
  my own not-walked map").
* **The program check (§6.3):** `emboss` read at bit 0 has 450 program slots that do not
  decode; at bits 1, 3, 5, 7 none fails and the header length is exact on 375 of 375
  (FORMAT-NOTES.md, "`emboss`: the state legend is wrong"; "Fix 2 — `emboss`'s grid").
* **Independent of the width model:** the field rule and the positional rule ("the present
  parameters occupy the last `n` header slots", which never decomposes `w1`) give identical
  name lists on 78,783 of 78,783 records.
* An exact header length is **not** evidence about the decomposition: a misaligned one can sum
  correctly.

So the file forecloses some starting positions and the rest are inferred from what the slots
hold. With §7.3: the format states the width legend; what it does not state is the KEY —
which field carries which type, and where each field begins.

**An offset must be read, not assumed.** `directionalwarp`'s `intensity` is bits 1 and 2; a
matcher that assumes fields begin at even bits finds no field for it, names neither of its
parameters, and returns nothing on 62,146 records — silently, because an empty parameter list
is indistinguishable from a filter that declares none.

**`fxmaps`' node parameters are in its five `w1` fields** (its PATTERNS' parameters are in
the FX entry table, §8). Field 0 is `background` (`channel` width — one word grey, four
colour), field 1 `hurst`, field 2 `opacitymult`, each named by a paired source; field 3's baked
arm is four words and its program arm returns a 4-vector from the FX-Map's slot 0, field 4's
from slot 4; fields 3 and 4 are unnamed (FORMAT-NOTES.md, "Graph 001's first annihilation
point is a white canvas the file states").

**`transformation`'s `w1` bits 0–4 are a 5-bit INTEGER `k`, not fields.** No partition of
them into two-bit fields or single-bit flags can hold the corpus: cost is additive over a
partition, and observed codes differing in bit 0 alone under one class word
(`0x3f`/`0x3e`, `0x23`/`0x22`, `0x21`/`0x20`, `0x27`/`0x26`) disagree about what that bit
costs (FORMAT-NOTES.md, "Why no field grid can hold it"). Its codes:

    0 .. 13    literal, and costs no header word           4,192 records
    14 .. 28   never observed -- a reader REFUSES
    29         costs no word, and is not a size rule           3 records
    30         ONE PROGRAM POINTER, after the class block     25 records
    31         the ordinary value, costs no word          230,639 records

* **0..13: `k` is how many times the record halves its input:** `own log2 size =
  max(input log2 size − k, 0)`, on 84.1% of the 4,192 against 25.3% at `k = 0` (92.9% where the
  record carries an `$outputsize` expression, 42.3% where it does not). `k` is **not** bounded
  by the input's size; `max(·, 0)` absorbs the overhang (FORMAT-NOTES.md, "What the integer is
  — a halving count").
* **30** emits one program pointer, placed before the other `w1` fields. A program resolves
  there on 25 of 25 records reading 30 and on 0 of 234,834 reading anything else; all 25 return
  an int1 computed from `$sizelog2` — `|log2 w − log2 h| ≥ 2 ? int(|log2 w − log2 h| − 1) : 0` —
  a halving count, like the literal arm (FORMAT-NOTES.md, "The 25 records are real").
  *Not shown by the corpus:* its place relative to fields at 6, 25 and 28 — no record sets 30
  together with any of them.
* **14..28 refuses.** The range is unobserved, not unreachable (`k` = 14 needs only a log2-8
  input and an excess of 6, the observed maximum), and the two exotic codes observed split on
  cost (29 none, 30 one word). Charging zero and meeting a pointer code shifts every later slot
  silently; a refusal is reported (FORMAT-NOTES.md, "The two loose ends of `transformation`'s
  integer field"). With `w0 = 0x03197704`, `w1 = 0x20 | k`, `header_words` answers

      k = 0..13   4      k = 14..28   None      k = 29   4      k = 30   5      k = 31   4

* **29** costs no word (each record's directory extent equals the stated header) and is not a
  second pointer arm. It is not the halving law at any single `k` and not a synonym for 31; 29
  and 30 have never been seen under a common class word. The records are `US_Flag` 45,
  `Embroidery_Legacy` 2 (byte-identical headers, plausibly one library sub-graph) and
  `TatamiSubstance001_COMPILED` 906. *Open:* what 29 MEANS — all three lack `$outputsize`,
  where the size law is weakest, and offer no program slot to arbitrate; a file with several
  records at 29 whose inputs differ in size would settle it (FORMAT-NOTES.md, "What the 29
  records did settle, about the law rather than about 29").

**Bit 5 is separate and is not part of the integer** — see §13.4.

---

## 8. FX-Map trees

An `fxmaps` record (filter id 4) names its FX structure at slot 2 (the walk's `root` slot,
`words[2] + 52`). The region holds two kinds of structure: a **chain** of control nodes
(iterate, switch, branch) and a **table** of entry cells (the patterns drawn, each a source
`paramset`). The root is either. A chain ends by pointing at the first table entry (97.2%
of chains end on a nibble-8 word; FORMAT-NOTES.md, "The node chain and the parameter table
are one structure"); a table run may end by pointing back at a node. Every
pointer carries the `+52` skew, and every offset is absolute. As everywhere in §5, the
structure need not lie inside the naming record: 805 records address a table outside
themselves, in every resolvable case inside an earlier record. Bound reads by the body, not
the record.

**Classifying a word.**

| word | structure |
|---|---|
| low byte bit 7 set, low nibble 9, B or 3 | **node** (mask-walk below). Node headers are ≤ `0xFFFF` |
| low nibble B, bits 4–7 clear (`0x??0B`) | **leaf** |
| low byte `0x1B` | **branch** |
| low nibble 9, bit 7 clear (`0x09`, `0x49`) | **pointer cell** `[hdr][next][payload]` |
| low nibble B, bit 6 set, bit 7 clear (`0x?4B`) | **payload cell**: continues at slot 2, which addresses a table entry |
| > `0xFFFF`, low nibble 8 | **entry cell** (a Quadrant). Nibble-0 `patterntype` is still an entry |
| high half `0x0002` **and** low nibble 8 | **chain link**: an entry cell met in the chain (`0x00020008` is the bare cell below) |

Test the low nibble before the high half: `0x0002711B` is a branch, and reading it as a link
loses `Splatter.sbsasm` record 242 its only entry (FORMAT-NOTES.md, "And one cell was
traversed all along and never reported"). `0x081` (one specimen, nibble 1) is
unexplained and not modelled.

**Nodes: the mask-walk one scale down.** A node is `[header][fields]`. Bits 4–7 of the low
byte are a presence mask; each set bit inserts one field ahead of the successor:

    successor word = base + popcount(header & 0xF0)      base: nibble B = 1, 9 = 2, 3 = 1
    program word   = 1 + bit 4;  bit 5 adds a second program in the next word

- bit 4: one word ahead of the program (on a bit-7-clear header it makes the `0x1B` branch
  instead);
- bit 5: a `randomseed` program after the base program;
- bit 6: one word (on `0x1CB`/`0x1DB`, the after-child pointer; §13.7);
- bit 7: the base program + successor structure. `node_shape` returns nothing without it.

`base` is stated per nibble; what it means is open (bit 1 of the nibble splits the three,
which is a three-point fit and not a rule). Nibble 9's extra base word is the FALSE child of
a switch. Verified 30/30 over every header seen 10+ times (FORMAT-NOTES.md, "The FX-Map node
successor is a popcount"; `sbsasm.node_shape`).

| header | words | role (§13.7) |
|---|---|---|
| `0x18B` | `[hdr][numberadded][succ]` | iterate (`addnode`) |
| `0x19B` | `[hdr][bit-4 word][count program][succ = loop]` | iterate |
| `0x1AB`, `0x1A3` | `[hdr][randomseed][numberadded][succ]` | iterate |
| `0x1CB` | `[hdr][program][after child][succ = loop child]` | iterate with after-child |
| `0x1DB` | `[hdr][bit-4 word = 2][program][after child][succ = loop child]` | `0x1CB` in a variant compile |
| `0x89` | `[hdr][switch program][FALSE child][succ = TRUE child]` | switch (`markov2`) |
| `0x99` | `[hdr][bit-4 word][program][FALSE child][succ = TRUE child]` | switch / stepper |

A spare child word is 0 when unconnected. It is wired on 205 of 27,093 `0x89`, 88 of 238
`0x99` and 65 of 1,865 `0x1CB` corpus-wide, and on all 23 `0x1DB` (12 files, both children
`0x1A3`, the program `0x1CB`'s line for line: zero the statistics slots, return 1). A reader
that follows only the successor draws half of each such record; `fx.chain` = `tree`
(default) reads both (§13.7). No export covers a `0x1DB` record, so its reading is
structural only (FORMAT-NOTES.md, "`0x1DB` and `0x1A3` are the Bricks tiling compiled with
bit 3 clear and bit 4 set").

**Leaf** (`0x??0B`, bit 7 clear): `[hdr][successor]`, successor at word 1 by the same mask
rule (`leaf_successor`). `header >> 8` is the leaf's baked emission count (§13.7). A leaf
states no program slots; a reader that scans its words for programs must cap the scan at its
stated width, because a one-word `0x0000000B` leaf's slot 1 is the next cell's tag.

**Branch** (`0x??1B`): no program of its own; word 1 states the shape (FORMAT-NOTES.md, "The
`0x1B` family has TWO shapes, and word 1 states which").

- word 1 = `0x3039` (343 of 355): `[hdr][0x3039][→ child A][child B …]`, three words, two
  children — one addressed by word 2, one contiguous at word 3. Words 4–5 belong to child B.
- word 1 = 0 (12, all in `Splatter.sbsasm`): the table begins contiguously at word 3; the
  node owns nothing.

**Entry cells are Quadrants.** Every entry cell is a `paramset`: it draws its own pattern in
its region and hands each of its four outputs a quarter of that region. A run of entry cells
is therefore a nesting, not a list (§13.7; FORMAT-NOTES.md, "The level fault upstream of
10055 is a white-noise FX-Map emitting ONE pattern"). The tag is a presence mask over the
entry's fields:

| tag bits | field | slots |
|---|---|---|
| 4 | structural word; in a Quadrant a small integer (declared `randomseed` values among them) | 1 |
| 7 | structural word; **no slot unless bit 31 is also set** | 0 / 1 |
| 8–11 | `patterntype − 2`; 0 is a catch-all (`patterntype` 1, 2, or a function graph) | — |
| 16 | four child pointers, one per output, 0 = unconnected | 4 |
| 17 | one child pointer shared by all four outputs | 1 |
| 18 | a `blendingmode` is declared (§13.7) | — |
| 19 / 20 | `opacity`, baked / program | 1 / 1 |
| 21 / 22 | `branchoffset`, baked / program | 2 / 1 |
| 23 / 24 | `frameoffset`, baked / program | 2 / 1 |
| 25 / 26 | `patternsize`, baked / program | 2 / 1 |
| 27 / 28 | `patternrotation`, baked / program | 1 / 1 |
| 29 / 30 | `patternsuppl`, baked / program | 1 / 1 |
| 31 | `imageindex`, program | 1 |

Slot 0 is the tag; slot 1 points at the parameter block (usually inline, so it reads
`off + 4 · first parameter slot`, 85.75%); parameters follow from slot 2 in ascending bit
order. A program bit's slot holds a program pointer; a baked bit's slots hold the value.
Bit 19 is the weakest row (values to ±1e13) and bit 21's width is inferred. `patterntype`,
`blendingmode`, `imagefiltering`, `imagepremul`, `randomseed` and `colorswitch` have no
parameter slot (`FX_UNSTORED_PARAMS`).

- **Bit 7.** Crediting it a slot puts every program of the `0x??5?0088` family one slot late
  (140 of 140 named programs resolve with the declared arity without it; FORMAT-NOTES.md,
  "The blur value cannot be seen because the picture behind it was blank"). On bit-31
  entries slot 1 is a small integer (the image index as a value), and bit 7's slot stands.
- **Bit 31** is open. Its trailing slot is a real program pointer on `0xD5140088` (54 of 54)
  and the body of the entry's own inline program on `0x83000088` and `0x91100088`
  (FORMAT-NOTES.md, "The walk: bit 31's trailing program is real for one tag and program
  BODY for two"); the self-delimited width below stops before it.
- **Inline program.** A tag that names no program slot but sets bit 25, 27 or 29 carries one
  program inline at the first slot after its fields (unnamed; 98% open with `inputref`). The
  one tag this misreads, `0x00020018`, has its program at slot 1's target + 20
  (`FX_PAYLOAD_PROG`).

**Quadrant child pointers.** The cell is

    [tag][params ptr][bit-7 word]?[child ptrs][bit-4 word]?[params …]

The params pointer addresses the first parameter word, `base + 4·(2 + n)` for n pointer
words (136,089 of 136,089 bit-7-clear cells), so the pointers start at word 2, or word 3
under bit 7 (5,100 of 5,100; on a 120-file sample every such cell also sets bit 31, consistent with
the bit-7 rule above). The bit-4 word follows the pointers (27,500 of 27,519), not
precedes them as ascending order would place it; both are one word, so no program slot
moves. A **bare** cell (no bit ≥ 19, no bit 4) has no params pointer and is `[tag][child]`,
two words. `k` bare cells in a row are `k` nestings of four; permitted
`SubstanceDesigner__Clouds_3_Animated` agrees node for node (`render2/fxtree.py`
`pointer_slot`; FORMAT-NOTES.md, "Quadrant subdivision lands in render2").

**The pointer-cell list.** A list may alternate pointer cells with bare cells,
`[0x9][next][payload] [0x00020008][next] [0x9][next][payload] …`, every payload naming one
shared `0x?4B`. It is the library Splatter's chain of Switches with `Grid_Number` folded by
the compiler: each `0x9` is a switch whose selector is baked into bit 6 — `0x49` takes the
payload (the draw), clear takes `next` (a bare Quadrant, one more nesting). A `0x49` at index
`k` after `k` bare cells draws its payload in `4^k` regions. 59 of 60 such lists carry exactly
one `0x49`. `fx.pointercell` = `switch` (default) | `list` (FORMAT-NOTES.md, "The
`0x9`/`0x49` pointer-cell list is the library Splatter's `Grid_Number`, compiled").

**Entry extent.** The mask width is `max(slot + width − 1) + 1`: the last field's full width
counts (a trailing `patternsize` is two words, and `max(slot) + 1` stops on its second
component). It is exact for 98.94% of entries and one word long for 93 (`0x83000088`,
`0x91100088`), and no bit separates those (bit 31 is necessary, not sufficient). The
**self-delimited width** (`Assembly.fx_entry_width`, inline fields only) is the rule:
resolve program slots in order and stop at the first slot whose own address lies inside a
program already named (99.23% exact, 0 long). An entry's inline program states its own length (§10), so
the entry's byte extent ends where that program ends; no stride table is needed
(FORMAT-NOTES.md, "The FX entry table is a linked list").

**Out-of-line entries.** An entry's parameter block may sit before its tag, at the address
slot 1 names:

    [ … the tag's own field words … ][tag][slot 1 → the block][slot 2]

It is recognised by two statements of one address agreeing: slot 1 names the block, and the
mask width puts the block's end on the tag word (`block + 4·(width − slot) = tag offset`,
for the slot the block starts at). Where they agree, 1,749 of 1,749 declared program slots
resolve; elsewhere 9 of 602. Fields are read at `base + 4·sl`, `base = tag offset − 4·width`
(mask width, not self-delimited). The cell is yielded at its block. Its step is bounded to
slots 1 and 2 — past the tag lie the next cell's programs. Its extent runs to `tag + 12`
when the tag sets bit 16 or 17 (the word at `tag + 8` is then a pointer to a cell, 876 of
876) and to `tag + 8` otherwise (that word is a record's program, 316 of 316)
(`Assembly.fx_out_of_line`, `fx_out_of_line_span`; FORMAT-NOTES.md, "`abuts an fx cell` was
an entry whose parameter block sits out of line" and "3. The word at an out-of-line cell's
`tag + 8`").

**Walking the region** (`Record.fx_walk`):

1. **Chain run** from the root, node by node (`fx_tree`); a branch queues its second child,
   and a chain link or pointer cell is yielded and stepped through by its slot 1. The run
   ends on the first table entry.
2. **Table run.** Entries form a linked list: the next entry is the furthest-forward pointer
   among slots `1 … span`, `span` = last layout slot + 1 (1 for an empty layout, 2 for an
   out-of-line cell). Stop when the next word is a node header (report it), or — from the
   second entry on — when the tag names program slots and none resolves
   (`entry_layout_holds`) and the out-of-line identity fails — the test that catches
   bytecode read as a tag, which a tag-vocabulary test does not (`0x09130008`). Pointer
   cells met in a run are waypoints, not terminators.
   Nibble-9/B words met in a run have their programs scanned, capped at the element's stated
   width (slot-1 step, or `leaf_successor` / `pointer_cell_successor`).
3. **Both forward pointers.** For a tag with an empty layout, also enqueue as table starts
   the other forward targets in slots `1 … walk_end − 1` that pass nibble 8 and
   `entry_layout_holds` (`0x00020018` is `[tag][→ leaf][→ next cell]`, and the step takes
   the dead-end leaf). Do not widen or move the step instead: that derails `0x00020008` and
   `0x00010008`, and no tag bit separates them from `0x00020018`.
4. **Table → chain.** Follow a reported stop header only if its word is a header this
   record's own chain run already yields (vocabulary frozen before any continuation).
   Floats such as `0x3E999999` end in `0x99` and would otherwise pass as nodes.
5. **Once both queues drain**, enqueue: the forward targets of an entry's structural words
   (bits 4, 7, 16, 17, which the parameter layout drops) and of an out-of-line cell's
   `tag + 8` word when bit 16 or 17 is set, both gated on the record's frozen entry-tag
   vocabulary; and, ungated, the payload of a pointer cell met inside a table run
   (`pointer_cell_payload`, the cell's last slot). Each target must be a nibble-8 word that
   passes `entry_layout_holds` or the out-of-line identity.
6. Yield an entry once **per resolving program slot**, as a node is.

Evidence: FORMAT-NOTES.md, "A cell with two forward pointers loses one, so follow both" and
"The words the parameter layout drops are pointers too".

**Known limits.**

- `fx_walk` does not follow node spare words (27 of 3,019 over 60 files point at further
  cells). The tree reading of §13.7 reads them per record.
- `0x00420008` cells holding their declared program inline at slot 3 are not accepted: the
  cells that arm admits do not state where they end.
- About 25 KB of FX bytes corpus-wide stay unlabelled (`fx cell not reached` 20,890,
  `abuts an fx cell` 4,204; FORMAT-NOTES.md, "The sweep asked a predicate that cannot see an
  out-of-line cell").

**`patternsize`** is decoded: named by source containment, placed by the entry mask, and in
the units of the cell's region — the canvas at depth 0 (§13.7). It resolves
deterministically: no unset slot, no unset graph input and no evaluation-order dependence,
over all 41,153 `fxmaps` records that yield a drawable entry table (FORMAT-NOTES.md,
"`patternsize`'s setup chain was never out of order"). What is open is the drawing model
around it, and how many patterns a record emits and where: §13.7.

---

## 9. Embedded resources (resource table)

When `base != 0`, the resource segment `[0x38, base + 0x38)` holds raw image payloads, and a
**resource table** sits immediately before the interface block: one record per image.

```
u32 format_tag
u32 offset            the image's file position − 52 (segment position + 4)
```

`format_tag` is four bytes: `[3]` format (`01` L, `02` RGB, `03` RGBA, `05` L16, `07` RGBA16),
`[2]` depth (`08` 8-bit, `18` 16-bit), `[1]` `log2(h) << 4 | log2(w)` (`0xAA` = 1024×1024),
`[0]` colour flag (`20` grayscale, `21` colour). The fields are mutually consistent
(bytes-per-pixel = channels × depth). Records sit 8 or 32 bytes apart depending on the file,
so find the table by scanning for valid tags, not at a fixed stride (FORMAT-NOTES.md, "The
embedded images decode — confirmed"). Consecutive offsets give each image's size; the sizes
sum to the segment length exactly.

**A two-word `bitmap` record names its image at `words[1] + 52`**, the universal skew; when
`words[1]` is not below the file size it is a graph-input uid instead (§13.6). The longer
forms (a computed program, a three-word form whose slot 2 is the offset, pixels inline in the
record) are `Record.bitmap`'s. The image runs `width × height × channels × depth/8` bytes;
when bit 3 of class byte 1 (`cls >> 8`) is set it is JPEG, `[u32 compressed length][SOI …]`
at that offset. Check: `max(offset + size)` equals the segment end in 111 of 111 files whose images tile it
(FORMAT-NOTES.md, "`Grid.sbsasm`'s two 65 KB blobs are images, and the naming record is next
door").

**The image need not lie in the resource segment or in the naming record.** With
`base == 0` there is no segment and images sit in the record body; §5's directory is a sorted
partition, so an image falls inside whichever record's extent it lands in (`Grid.sbsasm`
records 5, 6 and 8 name three 256×256 images each lying inside the previous record). Decide a
record's form from its own header length (§6.1), never from `offset[i+1] − offset[i]`.

### 9.1 Filter 17 stores a string and a font in the segment

A `text` record's base region is `[w0][w1][zero][string ptr][font ptr]`; both pointers carry
the `+52` skew and address this segment.

**`words[3] + 52`: the string**, `[u32 count][u32 codepoint × count]`. When `w1` **bit 1** is
set, `words[3]` is instead the uid of a **type-6 (string) graph input**, and the manifest's
`default=` for that uid is the text. Decide by the bit, never the value: both arms hold an
ordinary 32-bit word. All 59 corpus text records resolve (38 segment, 21 graph input).

**`words[4] + 52`: a font**, `[u32 hash][u32 length][sfnt]`, a complete TrueType file
(`00 01 00 00` on 13 of 14 distinct payloads, `ttcf` on the 14th). The length is structural:
`off + length` lands exactly on another record's string offset on 8 of 14. The font is per
record, not per file (FORMAT-NOTES.md, "Where the font is").

The compiled record names no font family anywhere outside the payload. Nothing inside the
payload is read beyond its four magic bytes and stated length. That restraint is a licence
question about the type foundry, separate from the provenance rule of §12.

### 9.2 Filter 5 stores vector artwork, and the payload states its own end

A filter-5 record names its payload at `words[1] + 52`. The payload is a self-delimiting
chain of primitives:

```
u32 kind              0x07FFFFFB, 0x00000003 or 0x04040403 (partitioned by class word)
u32 len               vertex count in `len >> 3`, primitive flag in `len & 7`
u32 vertex × len>>3   x in the low half, y in the high half, 0..65535 normalised
...                   further parts, each `[len][vertices]`; a kind word may restart
                      the two-word form, and is then skipped
u32 0                 terminator, one word
```

The extent is a walk to the terminator (139 of 139 records; `Record.vector_parts`,
`vector_extent`). Nothing else states the end: slot 2 is the record's `$outputsize`
expression, which the payload merely abuts, and `(len + 23) / 2 = 12 + 4·(len >> 3)` covers
only the first part plus one trailing word. Every end lands on a boundary the file states
elsewhere (slot 2 in 57 of 57 where it is a usable pointer; FORMAT-NOTES.md, "The payload
states its own end, and the 141,088 bytes were never a convention").

`len & 7` is **1** for a triangle strip (joins repeat a vertex) or **2** for a **closed
contour** (first vertex equals last in 37 of 38). A part is never flag 2 first. The payload
need not lie in the naming record: 76 of 139 point outside it.

---

## 10. Instruction stream (the ISA)

Computed parameters are **bytecode programs** reached from record slots. A program is
`[u16 instruction count][instructions …]` in a little-endian `u16` token stream
(**`(u16 arg, u16 opcode)`** words, opcode in the high half). Reach programs only through
record slots; a linear scan of the body decodes junk (`OPCODES.md`, "Decode correctly").

### 10.1 Encoding

Each instruction is one opcode token followed by its operand tokens (three-address code, one
result per instruction, contiguous SSA value numbering).

| bits | field |
|---|---|
| 15–10 | operand-token count — **instruction length = this + 1 tokens** |
| 9–8 | type: 0 bool, 1 float, 2 int (3 unused) |
| 7–6 | component count − 1 |
| 5–0 | operation id |

`length = (opcode >> 10) + 1` holds for **every** opcode in `0x0400–0x7FFF`, so any program
tokenises with no semantic table; unknown operations are skipped exactly (`isa.py`). Records
(`0x8000`+) are exempt: 4-aligned and framed by the directory.

### 10.2 Operands and immediates

Operands are value numbers naming an earlier result in the same program, except these
immediates (`disasm.IMM`): every operand token of a constant (`0x00`), system variable
(`0x01`), input reference (`0x02`), cache read (`0x03`) and variable get (`0x04`); position 1
of `set` (`0x07`, slot), swizzle (`0x10`, packed 2-bit mask) and cache write (`0x06`, index);
positions 1–6 of the samplers `0x33`/`0x34` (1 = sampler index, 2+ = flags, unread).
Instructions with a 4-byte immediate come in two forms differing by `0x0400`: the longer
carries a 2-byte pad, emitted when the instruction lands at 0 mod 4, so the immediate stays
aligned.

**Inputs are referenced by uid**: the reference opcode is followed by a `u32` input uid, and
bits 6–7 encode component count − 1 (`0x0902/0x0942/0x0982/0x09C2` = float1..4;
`0x0A02/0x0A42` = int1..2), 100% over 326,768 references. **Outputs are positional**,
identified only by index in the interface block's output array; they never appear in code.

### 10.3 Operation set

**41 operations in 63 type-specific forms, all named** (`OPCODES.md`), covering 96.5% of
decoded instructions on distinct specimens. Seven further operations — `0x03`, `0x0B`,
`0x0F`, `0x1E`, `0x2A`, `0x35`, `0x36` — fall below the catalogue's ≥20-specimen threshold,
are established structurally, and sit in the same table marked `*`. `0x06`, the write half of
`0x03`'s cache, also occurs (1,063 writes) and is not tabulated.

| ids | family |
|---|---|
| `00`–`02` | values and references — constant, system variable, input reference |
| `03`, `04`, `06`, `07` | variable slots and the cross-record cache — cache read, get, cache write, set |
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

Families follow operation id, except that comparison precedes boolean logic and `0x35`/`0x36`
group with the transcendentals.

- `0x0D` construct always takes exactly two operands and concatenates. It and `0x0F` carry a
  declared `ncomp` that is authoritative over their operands' runtime widths.
- `0x0B` **`while`** is a loop, operands `(init, cond, body, …)`, no immediate. Its operands
  name expression trees re-evaluated per iteration, so it is the one instruction a
  straight-line translation gets wrong. In the 5-operand form operand 1 may be `0xFFFF`, the
  absent-operand sentinel (164 instances): what bounds such a loop is not established, and
  `transpile.py` refuses it.
- `0x03`/`0x06` are cross-record common-subexpression elimination: a never-sampled
  `pixelprocessor` record writes a value at an index, and later records read it (FORMAT-NOTES.md,
  "`0x03`/`0x06` are cross-record common-subexpression elimination").
- The compiler performs common-subexpression elimination and inlines sub-graph instances, so
  instruction counts can be far below authored node counts.

### 10.4 System variables

`0x01` reads a system variable by immediate: 0 `$time`, 1 `$size`, 3 `$sizelog2`,
8 `$pos`, 10 `$number` (FX-Map only).

`$pos` means **two different things** depending on the reading program: the sampling
coordinate in a `pixelprocessor`, the node's own base position in an FX-Map. Supplying the
first where the second is meant renders nothing. See §13.5.

---

## 11. Interface block

One per package, immediately after the value table, ending at the end of the file:

```
[value table][u16 n_out][u16 n_in][output uid array][input descriptor array][16-byte footer]
```

Output uids are `u32`; each input descriptor is 8 bytes, `u32 type, u32 uid`. The footer is
the file's last 16 bytes, `(count, dir_start − 52, dir_end − 52, table_start − 52)` (§4), immediately after the
input descriptor array. The value table, walked with the widths its descriptor types imply, ends
exactly on the `n_out`/`n_in` word (`tools/standalone_parse.py`). The block aggregates every graph in a multi-graph package.
`archive/tools/validate_corpus.py` confirms `(n_out, n_in)`, both uid arrays, the footer and
the record directory on 383/383 specimens (FORMAT-NOTES.md, "Byte coverage, and the curve
tables").

---

## 12. Provenance and scope

This specification is clean-room: no Adobe Substance engine binary was run, disassembled or
inspected, and any source file bearing `<author v="Allegorithmic">` is excluded from analysis.
The exclusion is a predicate: `corpus.sources()` returns only permitted `.sbs` paths,
`corpus.source_excluded()` checks one, and every tool that reads a source goes through them.
131 of the 491 sources bear the tag, and for FX-Maps they are the whole of the interesting
population, so a negative measured over the permitted sources means "absent from what may be
examined", never "absent from the format".

**A permitted source is ground truth only if its dependency closure is also permitted.** The
predicate classifies the file it is handed; `sbs://…` dependencies name shipped library
graphs, which are excluded but compiled into the package. `Simulator__Grid.sbs` is permitted,
declares two `sbs://` dependencies, and holds 3 `fxmaps` nodes against its compiled
sibling's 6. Pair only against a source whose dependencies are all permitted, or compare per
node rather than as multisets (FORMAT-NOTES.md, "SPEC: where the format is read as individual
bits", "WITHDRAWN: the Grid declared-vs-decoded comparison").

The format's *structure* is recovered: a reader can locate and walk every region above from
the file alone (residuals: §8 known limits). What remains open is *semantics*: the meaning of
some filter parameters, the FX-Map drawing model (§13.7), and provenance-walled specifics —
filter 5's name (its layout is in the legend and its payload decodes), filter 9, and inline FX
parameter names.

§13 specifies a renderer. On the corpus specimen whose only graph inputs are `$outputsize`
and `$randomseed` (so a colour mismatch cannot be an author's tweak before export) it
reproduced all six declared outputs against the package's own exports at r = +0.98 / +0.95 /
+0.91 (basecolor), +0.96 (roughness), +0.97 (ambient occlusion), and a height mean of 0.7859
against 0.78628 (FORMAT-NOTES.md, "A renderer where every structural read comes from the
walk, and Rokviz renders"). Generality is open: §13.8 lists the node defaults the file does not
contain, and §13.7 the FX-Map drawing readings that are still arms.

---

## 13. Evaluating a graph — the renderer

Sections 1–12 are enough to *read* a file; this section is what a reader needs to *run* one.
The renderer of record is `tools/render2/`: `engine.py` (the pass, record sizes,
`$outputsize`), `model.py` (the name legend and the per-record `View`), `filters.py` and
`text.py` (filters), `ops.py` (program runner, samplers, blend modes), `fx.py`, `fxtree.py`
and `fxchain.py` (FX-Maps). Values the file does not state are §13.8.

Readings the file does not settle are arms of `assume.QUESTIONS` (`tools/assume.py`). The
**effective** reading is the default at the call site, `assume.assumed("key", default)`;
where this section names an arm it names that default, and other arms exist for comparison.

### 13.1 Filter ids

```
0 gradient   1 blend    2 transformation  3 shuffle    4 fxmaps    5 vectorshape
6 uniform    7 warp     8 emboss          9 (unnamed) 10 blur     11 dirmotionblur
12 directionalwarp      13 sharpen       14 hsl       15 levels    16 bitmap
17 text     18 normal   19 dyngradient   20 pixelprocessor        21 distance  22 curve
```

Every id but 9 is evaluated. §13.6 gives the semantics of all of them except 17 (`fxmaps`
through §13.7). `text` (17) is `render2/text.py`: the string and the embedded font sit in the
resource segment (§9.1), and every `text` record is marked low-confidence, because the ink
colour, the size of a record that states none, and the glyph face (a substitute) are not in
the file. Id 9 has no implementation.

### 13.2 The pass

**What a record is drawn at.** Its own tag, two nibbles: `width = 1 << ((tag >> 8) & 0xF)`,
`height = 1 << ((tag >> 12) & 0xF)`. One exception, which a class bit states: on `bitmap`
records, `word0 & 0x20000000` (class bit 13) is a 4×-**area** flag that the height nibble
omits, so `height` gains a factor of 4. All 11 corpus records that set it store exactly
four times their declared area, and none of ~570 with the bit clear does. Without the flag a
decoder reads only the top quarter of each image (FORMAT-NOTES.md, "A confirmed bitmap
under-declaration: 11 images decoded at 1/4 height").

**The tag is the size at the declared `$outputsize`.** `$outputsize` is a graph input (the
manifest identifier `$outputsize`, type 8, `(log2 w, log2 h)`). A record's real size is
the program at its size slot (§13.3), evaluated at the `$outputsize` the graph is being run
at, and the tag caches that value at the manifest's default. At the default the tag is the
answer. At any other `$outputsize` (`engine.record_sizes`):

- Evaluate the size program with every `$outputsize` uid set to the requested value. Trust
  it only where, evaluated at the declared default, it reproduces the tag with every log2 in
  0–16. Otherwise the slot is misidentified, and its answer at other sizes is worthless.
- A record with no trusted size program takes its parent's size **relatively**: it scales
  its tag by the factor its input moved (the largest over its inputs), and does not copy
  the parent's new size. A record with neither a program nor an input (`bitmap`, `uniform`)
  keeps its tag.
- **Never scale the tags uniformly.** Size expressions do not move together. In
  `ChesterfieldSofa`, 674 of 746 add the whole shift, 45 ignore `$outputsize` (fixed-size
  pyramid stages), 5 add a third of the shift, 5 two thirds, and 1 shifts width only
  (FORMAT-NOTES.md, "Why "just multiply the tag by 8" is wrong").
- If the graph declares no `$outputsize`, or no default for it, every record keeps its tag
  and no program's `$outputsize` is overridden.

The tag also sets the unit of the pixel-valued intensities of `warp`, `dirmotionblur` and
`directionalwarp`: they are in the pixels of the tag width, whatever size the record renders
at (`warp.reference_px = tag`; see §13.6).

**A package declares one `$outputsize` per graph.** A multi-graph package declares one input
with identifier `$outputsize` per graph, all with the same default. Their uids are
per-graph-slot identifiers, not per-file ones: `Kutejnikov__Bricks_and_tiles` declares five
and `Kutejnikov__Auras` four, and the first four are the same uids in the same order. A
record's size expression reads the uid of its own graph, so a reader must set every one.
`engine.outputsize_uids` returns all of them in manifest order, and the renderer sets each to
the requested size (`graph.outputsize = pergraph`). The `first` arm sets only the first uid,
which pins every other graph at its declared size. On single-graph files the two arms are
identical (FORMAT-NOTES.md, "ROOT CAUSE: a multi-graph package has ONE `$outputsize` INPUT
PER GRAPH").

**`$outputsize` changes the graph, not only its resolution.** Record sizes feed `$size` and
`$sizelog2`, which ordinary programs read. In `ChesterfieldSofa`, 98 of 102 `switch` blends
take their selector from a program that compares `$sizelog2` against a constant: a mip
pyramid whose octave k switches in once the output is large enough. A render at one
`$outputsize` compared with an export at another compares two different graphs. Every
reference pack in this corpus ships maps at a size its own file does not declare, so score
at the size the export implies. `engine.implied_outputsize` reads it from power-of-two map
dimensions and returns `None` when a pack's maps disagree (FORMAT-NOTES.md, "Every
reference pack in this corpus was exported at an `$outputsize` its own file does not
declare").

Score a derivative channel (`normal`, and the `height` it derives from) at its own
resolution or not at all. Resampled down, a map with no spatial agreement can still score
high on a handful of unique values, which the scorer flags `DEGENERATE` (FORMAT-NOTES.md, "`normal` in full: three named fields, a per-256-pixel slope,
and two causes for four threads").

**A pixel cap is not a scaled-down render.** The caller's cap (`max_dim`, `View.size(cap)`)
clamps each record's grid independently, while its programs still read the record's
declared size. Every `$size`-derived pixel parameter is therefore computed for the full
canvas and applied in the small buffer, and the result is a different picture, not a
coarser one. Render at the canvas size and resample down (FORMAT-NOTES.md, "The blocker
dissolves").

**Which records are outputs.** Between the record directory (§5) and the first record there
is one 8-byte entry per declared output. Word 1 is the output's **record index**. If word
0's high half is 2, the entry is a numeric **value** output rather than an image: its low
half is the manifest type, and the record it names is a `pixelprocessor`. Otherwise
`format = (word0 & 0xFFFF) >> 4`, which is the manifest's `format` attribute, and bit 2 of
`format` is the grayscale flag. That flag is read from the output table alone
(FORMAT-NOTES.md, "Correction: the output table exists, and it was never hidden"; "The last
output-table entries are numeric value outputs").

**Order.** Every edge is a **backward** record index (§6.3), so one forward pass in index
order suffices; no topological sort is needed. Each record produces an `(H, W, C)` image,
with `C` = 1 when word0 bit 0 is clear and 4 when it is set. A record the walk does not
cover, or whose filter has no implementation, is refused. It is never read from raw slots.

**Failures.** A failure is a *cascade* when it is only a consequence: an input edge whose
record has no output, or a program read through a sampler nothing binds (an unwired image
input). Every other failure is a *root*. Root causes are `failures − cascaded`, and that
distinction is what makes a blocker census meaningful.

**Conform each result to the record's channel count, and refuse rather than invent**
(`ops.conform`):

- A colour record returning 3 channels is RGB and gains an opaque alpha. One returning 1
  channel has that channel replicated to four.
- A greyscale record returning several identical channels is narrowed. If the channels
  differ, it takes the first component (`greyscale.wide = first`, whose `refuse` arm treats
  it as the wrong program). These records are cache writers, and their picture is a
  by-product of the side effect.
- Anything else is refused: a channel count that disagrees with the record's colour flag
  means the wrong program ran.

Non-finite samples become 0, and the record is marked low-confidence
(`nonfinite.fill = 0.0`). Results pass between records as float32
(`engine.bitdepth = float`); the per-output depth flag, word0 bit 20 (§13.4), is not
applied. After the pass, clamp **declared image outputs** to [0, 1] and nothing else: an
intermediate above 1 is headroom that a later multiply may legitimately consume.

### 13.3 Reading a record's parameters

Three questions, three answers, and only the third needs the header length:

| question | answer | from |
|---|---|---|
| which parameters are present, baked or program? | the `w1` two-bit state | §7.4, the file |
| how wide is each baked one? | Float1/2/4, per-channel by the colour bit | §7.3, the file |
| where does the block start? | `header_end − Σ widths`, laid **forwards in legend order**: ascending mask order everywhere except filter 17 `text` (§6.1, §13.4) | the width legend's header length only |

**Anchor at the end, not at the walk's forward cursor.** The cursor inherits any slot that
was mis-charged *before* the parameters. The end anchor is wrong only if the header
*length* is wrong. Under §7.3's width legend the two coincide: the base is
`n_hdr + n_base + n_fixed`, and the cursor lands on the stated length in 903,301 of 903,301
corpus records. The end anchor stays as the check that fires when a width is wrong.

**Check it** (`model.Shifted`). Refuse the record when:

- the block would start on a mask word, or on or before an input-edge slot (§6.3); or
- the header end runs past the record's words; or
- two present `w1` fields share one name. These are relocation arms (see `blend`, §13.4),
  and only one is ever set.

Any of these means the name legend is missing a field that sits after a listed one, and the
whole block has shifted onto words that read as plausible floats. The check is silent on
84,700 records that carry named parameters.

**The base region is structural.** It is the mask words plus the base image inputs:
`2 + arity` words, or `1 + arity` for a filter with no `w1` word. It is never a fitted
intercept, and it agrees with the fitted intercept on 321,054 of 321,054 interaction records.

**The size slot is the slot the class walk places for bit 16**, which `decompose` reports as
`size_slot`. It is not the first slot of the class block (`prog`). The class block emits
bits below 24 in ascending order with bit 16 **last**, then bits 24–31 in ascending order
(§6.1). So when bit 23 (`$randomseed`) is also set, the seed takes the first class slot and
the size expression the second. That applies to 102,173 corpus records across 19 filters
(`pixelprocessor` 56,055 and `fxmaps` 36,028 the largest); over 120 files `prog` and
`size_slot` differ on 7,590 records (FORMAT-NOTES.md, "The fourth class-block walk, and one
loop instead of four"). A size slot that resolves a one-component program is the tell of an
ascending-order walk: no size expression returns one component.

**Class bit 16 clear ⇒ no size slot.** Do not read one. Reading it unconditionally is how a
`blur` whose 3-word header is `[tag][edge][intensity]` reports its intensity as its size.
If the size slot coincides with a slot the `w1` parameter block owns, keep the parameter,
drop the size slot and report it under `ignored` (§13.4). This does not fire on the corpus.

**Per-filter placement** (all reported by the walk; no caller reconstructs a slot):

- `emboss`: class bit 16 costs 1 word, bit 27 1 word and bit 19 none, over a base of 2 mask
  words and 2 image inputs. The 171 records below the legend's `min_version` gate (v5) are
  declined. Where a class bit is constant within a filter's population, it
  takes the cost that every population varying in it agrees on (bit 16: 1 word in all). A
  bit on which populations disagree (bit 27) is measured per filter with the base pinned
  (FORMAT-NOTES.md, "1. `emboss`: the version gate was the FIT's, and the records it hid are
  the evidence").
- `fxmaps`: its fixed prefix, the FX tree root (§8), is slot 2, *before* the inputs. The
  class block starts at the first slot after the inputs, and `prog` is that slot. `end` is
  the header length, as for every filter.
- `pixelprocessor`: its own image program is the **last** header word, after the class
  block (§6.1, §13.6).
- `vectorshape`: legend `base 0`, `fixed 1`, `cls {16: 1, 25: 1}`. On 127 of its 139 records
  class bit 16 is set, and in 127 of 127 the slot at position 2 holds the `$outputsize`
  expression (FORMAT-NOTES.md, "4. `vectorshape`: it was never a layout the file does not
  state").

### 13.4 The name legend

This is the one table the file does not state (§7.3). It is `render2.model.W1_PARAMS` and
`CLS_NAMES`. `(mask, shift)` is §7.4's presence mask, and `kind` is the baked width. A
`program` arm is one pointer, whatever its kind. A field begins at its own bit, so match
`3 << shift`, never an index on an even `(2j, 2j+1)` grid. `transformation`'s offset (bits
25–26) and `blend`'s relocated opacity (bits 9–10) begin at odd bits. An even grid splits
each of them into two phantom half-fields whose states swap meaning.

**Own parameters (`w1`)**

| filter | parameter | mask | shift | kind |
|---|---|---|---|---|
| 1 blend | opacitymult | `0x0030` | 4 | scalar |
| 1 blend | *(unnamed)* | `0x00C0` | 6 | 2 words |
| 1 blend | opacitymult, relocated | `0x0600` | 9 | scalar |
| 2 transformation | matrix22 | `0x000000C0` | 6 | Float4 |
| 2 transformation | offset | `0x06000000` | 25 | Float2 |
| 2 transformation | backgroundcolour | `0x10000000` | 28 | per-channel |
| 2 transformation | *(a halving count — an INTEGER, not a two-bit field)* | `0x0000001F` | 0 | 0 words at 0-13, 29 and 31, one pointer at 30, REFUSED at 14-28 (§7.4) |
| 2 transformation | *(unnamed)* | `0x00000020` | 5 | flag, 0 words in every state |
| 4 fxmaps | background | `0x003` | 0 | per-channel |
| 4 fxmaps | hurst | `0x00C` | 2 | scalar |
| 4 fxmaps | opacitymult | `0x030` | 4 | scalar |
| 4 fxmaps | *(unnamed)* | `0x0C0` | 6 | Float4 |
| 4 fxmaps | *(unnamed)* | `0x300` | 8 | never baked in the corpus; charged 1 |
| 11 dirmotionblur | intensity / mblurangle | `0x0003` / `0x000C` | 0 / 2 | scalar |
| 12 directionalwarp | intensity / warpangle | `0x0006` / `0x0018` | 1 / 3 | scalar |
| 15 levels | levelinlow, levelinhigh, levelinmid, leveloutlow, levelouthigh | `0x0003`, `0x000C`, `0x0030`, `0x00C0`, `0x0300` | 0,2,4,6,8 | per-channel |
| 15 levels | *(unnamed)* | `0x0C00` | 10 | flag, 0 words in every state |
| 17 text | matrix22 | `0x0C00` | 10 | Float4 |
| 17 text | position | `0x00C0` | 6 | Float2 |
| 17 text | fontsize | `0x0300` | 8 | scalar |
| 17 text | align_flag | `0x3000` | 12 | flag, 0 words in every state |
| 18 normal | intensity | `0x0003` | 0 | scalar |
| 18 normal | inversedy | `0x000C` | 2 | flag |
| 18 normal | input2alpha | `0x0030` | 4 | flag |
| 21 distance | *(the mask input's declaration — not a parameter)* | `0x0003` | 0 | — |
| 21 distance | distance | `0x000C` | 2 | scalar |

A `flag` is **zero words baked and one word as a program**, because the mask state is the
value. Declare both arms, or the end-anchored placement shifts.

**Filter 17's rows are in block order, which is not ascending**, the one exception to §6.1
in a `w1` block. `matrix22` (bit 10) comes first, then `position` (bit 6), then `fontsize`
(bit 8), and the reader walks the list in this order rather than sorting it. Ascending order
puts `fontsize` on the matrix's `c` component and cannot be rendered on any of the 14
records that bake all three. This order yields diagonal matrices in five files, an exact
rotation in `Speed Limit`, and a layout that reads. The off-diagonals are not uniformly zero
(FORMAT-NOTES.md, "The parameters, and the one place the walk's general rule does not
hold"). `align_flag` costs zero words in **every** state, its program arm (bit 13)
included. That arm is unobserved in 437 files, so treat a file that sets bit 13 as
something to examine, not to trust.

**`blend` states its opacity at one of two masks.** Connecting the node's `opacity` input
sets the field at bits (4, 5) to state 11 (the image-input code, §7.3) and moves the slider
to bits (9, 10). Both are `opacitymult`, and the two are exclusive, so a reader gives them
one name. `ChesterfieldSofa.sbs` (3 of 3) and `SandyStonePath.sbs` (5 of 5, program arm
included) place their stated values at (9, 10). Over the corpus, the (9, 10) field reads
`01` on 963 records, every one a plain float in [0, 1], and `10` on 170, every one a
program (FORMAT-NOTES.md, "`blend`'s opacity moves when its mask port is connected, and the
walk now states it").

**`normal`'s three fields are named by the program arm's operand.** A program arm opens
with `inputref` on a graph input, and the manifest names graph inputs. Field 0's 275
programs return float1 from inputs such as `normal_intensity` (`intensity`). Field 1's 38
return a boolean `<input> == 1` from inputs such as `normal_format` (`inversedy`). Field 2's
one program returns a boolean from `Alpha_Channel_Content` (`input2alpha`). The renderer
reads `inversedy` (`normal.inversedy = field1`). A reader that charges field 1's program arm
no word reads its pointer as `intensity` (FORMAT-NOTES.md, "`normal` in full: three named
fields, a per-256-pixel slope, and two causes for four threads").

**`levels` order is `(low, high, mid)`**, not the UI's `(low, mid, high)`. Over a corpus
sample, `in_low <= in_high` holds on 3,684 of 3,703 records under this order and on 641 of
751 under the other (FORMAT-NOTES.md, "render2 becomes the renderer of record, and how it
was built").

**`levels` field 5** (`0x0C00`) costs zero words in every state and is left unnamed. It is
set on 455 of 85,820 records, always in state 1, and within the corpus it marks one half of
a complementary midpoint split pair (436 of 440, against 0 of 4,916 in a matched control).
No permitted source declares a sixth `levels` parameter (FORMAT-NOTES.md, "`levels` has a
SIXTH w1 field, and it marks a midpoint SPLIT PAIR").

**`transformation`'s low `w1` bits are one integer and one flag, and neither is named.**
Bits 0–4 hold a halving count (§7.4), unnamed (`transformation.w1low = ignore`). The
halving law holds on 3,408 of 3,667 records (92.9%) that carry a `$outputsize` expression,
but only on 222 of 525 (42.3%) that do not. Codes 12, 13 and 29 occur only on records with
class bit 16 clear (77 records), and 12 and 13 state a constant canvas (32×32 and 16×16)
whatever their input. Neither
source nor manifest names it: 73 permitted source nodes pinned to their compiled records
all compile to `w1 & 0x3f = 0b111111`, whatever `tiling` they state, which refutes `tiling`.
The manifest has no pointer to read in the field's ordinary states, and the pointer arm at
value 30 opens on `sysvar 3`, not on an `inputref` (FORMAT-NOTES.md, "The source arbiter is
silent here, and its silence is now measured").

Bit 5 is a separate one-bit flag, associated at about 2.5:1 with the direction of the
scale in the record's own `matrix22` (det > 1 against det < 1). That is an association, not a
partition, and bit 4 moves neither (FORMAT-NOTES.md, "Bit 5 is separate, and bit 4 is what
says so").

**`distance`'s field 0 declares the optional mask INPUT, and field 1 is the radius.** Field
0 costs a word in states `01` and `11` and none in `10`, a cost that tracks bit 0 alone. Bit
0 set gives two edges and clear gives one, on 2,277 of 2,277 records (§6.3). Field 0 is an
edge, so it is not charged in the end-anchored block. Charging it begins the block one slot
late. Field 1's two arms are the ordinary pair, and all 188 of its program arms decode.
`SandyStonePath.sbs` states radii 56.2999992 and 64.2200012, and compiled records 3 and 180
hold exactly those (FORMAT-NOTES.md, "The other half of `distance`: the cost model was
paying for its mask input twice"; "A baked radius read as an address, and the 1,581 records
behind it").

**The class block ends exactly where the header ends.** A block that runs past the end has
mis-attributed a width. It has not found a longer header. Word0 bits 8–15 are the log2 size
nibbles (§6.2) and gate no word. A table that charges them gives one `normal` record a
10-word header at 4096×4096 and a 6-word header at 8×8. A header whose contents do not depend
on the canvas must have the same length at every size. `shuffle` needs two cost tables, one
per record shape (§6.4): bit 24 costs 4 words in the one-channel shape and 0 in the
four-channel shape (FORMAT-NOTES.md, "A fitted header LENGTH does not give you a header
LAYOUT, and the intercept was eating the base region"; "H4 survives, and it is the largest
result: the five cost-model modes are ONE mechanism").

**A reader should say what it declines to read.** An unnamed field is not an error, because
the walk places it and the layout is right. But its name resolves to a default, the default
is the neutral value, and the record renders, so the omission is invisible. `engine.render`
reports per record, under `info["ignored"]`:

- class parameters with no `CLS_NAMES` entry, except bit 16;
- `w1` fields of one word or more with no name;
- size-slot clashes (§13.3).

`low_confidence` means the opposite, "a value the file does not record was assumed", so
keep the two counts apart. `$randomseed` (bit 23) and `$pixelsize` (bits 26/27) have names
but no reader, so they appear under `ignored` on every record that sets them
(FORMAT-NOTES.md, "`ignored`: every warp states a bit-27 field we do not name, and
$randomseed is bit 23"). Other unnamed fields, each read as `ignore`, are `blend` `w1` bit 8
(a zero-cost flag, `blend.w1bit8`) and `emboss`'s `w1` field at bit 1 (`emboss.w1field0`).

**Inherited parameters (class word).** These class bits are shared rather than per-filter,
and a reader handles them once. Only bits 16 and 23 are universal. The high half, from bit
24 up, is a per-filter parameter list, and four filters (`uniform`, `hsl`, `shuffle` and
`dyngradient`) put their own parameters at bits 24–27 (see the next table).

| word0 bit | gates | cost | notes |
|---|---|---|---|
| 16 | `$outputsize` | 1 word | the size expression (§13.3), a program returning a 2-component integer. **Emitted after bit 23** (§6.1) |
| 19 | *(unnamed)* | 0 words | set on 903,608 of 903,616 corpus records. The 8 records with it clear are exactly those whose class word is `0x0080`: `pixelprocessor` value nodes (1×1, read by nothing, whose one class slot writes a scalar to the program cache). It is not the OR of the other bits: class word `0x0008` (bit 19 alone) occurs on 114 records |
| 20 | the output's **format bit 4**, a 16-bit depth flag | 0 words | over the 2,455 records a graph output names, format bit 4 is set on 94.67% when bit 20 is set and on 0.60% when it is clear. On all 42 greyscale outputs with a paired export, bit 20 set ↔ the export is 16-bit (FORMAT-NOTES.md, "Class bits 19, 20 and 21: two of the three were answered eight thousand lines ago"; "CORRECTION to `d3bad15`") |
| 21 | the output's **format bit 6** | 0 words | set on 98.46% of outputs when bit 21 is set (n=65) and on 0.00% when clear (n=2,390). Format bit 6 is carried by formats 64 and 76 |
| 23 | `$randomseed` | 1 word | a program pointer returning a 1-component integer. **Emitted first** |
| 24, 25 | the filter's **sampling class** | 0 words | 0 for the pixel-local filters, 3 for those that read a neighbourhood; redundant with the filter id on 96.8% of records (FORMAT-NOTES.md, "cls bits 8 and 9 encode the filter's sampling class"). `uniform`, `hsl`, `shuffle` and `dyngradient` put their own parameters at these bits instead, and are the only filters that charge a word for them |
| 26, 27 | `$pixelsize` | 2 words baked / 1 word program | an adjacent pair, lower baked and upper a pointer, **mutually exclusive on 124,388 of 124,388** records across `warp`, `blur`, `dirmotionblur`, `directionalwarp`, `distance`, `normal` and `sharpen`. The program arm reads the graph input the manifest names `$pixelsize` (type 1, float2), or is a six-instruction `sysvar…exp2` size ratio. The baked arm is a float2 (FORMAT-NOTES.md, "Class bits 26 and 27 are `$pixelsize`, and they are a baked/program pair"). `hsl` and `dyngradient` use these two bits for their own parameters |

Bits 19, 20, 21, 24 and 25 have no cell in any filter's width legend, so they gate no stored
value, and a reader that ignores them places nothing wrongly.

**Bits 16 and 23 are named by the manifest.** Both slots hold a program whose first
instruction is an `inputref` on a graph-input uid, and the manifest declares each uid's
`identifier` and `type`. The first class slot (bit 23) reads a **type 4** (int1) input named
`$randomseed`. The second (bit 16) reads a **type 8** (int2) input named `$outputsize`. For
example, `fur_var_001` declares `uid="4057753226" identifier="$randomseed" type="4"` and
`uid="2796450008" identifier="$outputsize" type="8" default="8,8"`, and its `levels` record 20
reads them in that slot order (FORMAT-NOTES.md, "Class bit 23 is `$randomseed`, and the class
block is NOT in ascending bit order").

The per-filter bits form an adjacent pair, the lower bit baked and the upper a program:

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

- **`uniform` bit 25** is named the way bits 16 and 23 are: on all 653 records that set it,
  the program opens with an `inputref` on an input named `color`, `metallic`, `rough`,
  `metallic_strength` or `roughness_strength`. `CLS_NAMES` carries bit 24 only, so the
  renderer finds this program with a value probe over the walk-named program slots.
- **`dyngradient` bits 25/26** are an unnamed pair of the same shape. The baked arm is 0.5
  on 86 of 95 records, and the program arm reads inputs named for a gradient position
  (`dyngradient.gradpos = ignore`).
- **`sharpen`** rests on the pair shape alone, because no shipped source states a sharpen
  parameter (all 28 nodes are at defaults). Bit 28 holds an ordinary float on 1,148 corpus
  records (median 0.25), and bit 29 holds integers on 8. The position is the one `blur`, the
  other one-scalar filter, uses. 1.0 never appears among the 1,148 values, which fits 1 as
  the default for an absent field. That is an argument from absence (§13.8).
- **`hsl`** comes from shipped sources. `ChesterfieldSofa.sbs` states `saturation` 0.65 with
  `luminosity` 0.60 on one node and `saturation` 0.58 on another; its compiled records set
  bit 26 to 0.65 and 0.58 and bit 28 to 0.60. `SandyStonePath.sbs` states `saturation`
  0.525, which is at bit 26. A node with all three parameters dynamic compiles to bits 25,
  27 and 29 in that order, which makes the unpaired lower bit `hue`. Corpus-wide, the even
  bits hold floats in [0, 1] clustered on the neutral 0.5, and the odd bits hold pointers.

### 13.5 Running a program

**`$size` is the record's own size, always**: the size its size expression (§13.2) gives at
the `$outputsize` the graph is being evaluated at, which is the tag at the default. A
caller's preview cap never reaches it. **`$pos` is the grid being drawn on.** Set `$size`,
`$pos` and `$number` (= 0) on every call (`ops.run_program`). A program evaluated with none
supplied must not inherit the previous record's values, which would be an order-dependent
cross-record leak. An unset `$pos` reads as 0. The one population whose `$size` is the drawn
grid rather than the record's size is a `pixelprocessor`'s own image program (see below).

**`$outputsize` is not a system variable, and it must be overridden wherever it is read.**
It is a graph INPUT, reached by `inputref` on its manifest uid (§13.2), so it arrives
through the interface block's value table and not through `sysvar`. Hand every program the
evaluated `$outputsize`: filter parameters (`Context.graph_inputs`) and FX-Map programs
(`Context.program_inputs`) alike, under the same condition as the size expressions. A
renderer that overrides it only for size expressions evaluates one graph at two output
sizes, silently. A census of direct readers cannot rule this out: `ChesterfieldSofa`'s HBAO
LUT reaches `$outputsize` through a slot its own size expression writes (`exp2($outputsize)`
into slot 0), and with the default it comes out short by exactly the ratio of the two sizes
(FORMAT-NOTES.md, "The discriminator is not in `$size` at all"). A canvas-sized
`pixelprocessor` is the exception (§13.6, `pixelprocessor.outputsize = grid`). Other graph
inputs keep their declared defaults unless the caller sets them (`render(inputs=…)`), since
an export may have been made with non-default inputs.

**A size expression and a parameter program read different variables.** Over the eight
reference assemblies, 30,792 records resolve a size program, and not one executes a `sysvar`
of any id. A size expression is a function of the `$outputsize` input and of constants,
never of `$size` or `$sizelog2`, so the question of what `$size` means inside a size
expression does not arise. `$size` in a `transformation`'s `offset` is the record's evaluated
size, not its tag. The `switch` gates that admit a mip rung once the render reaches
`2^(k+1)` pixels read the same quantity, which is what keeps the pyramid consistent across
output sizes. A `c / $size` offset is a pixel count, so its form does not tell a horizon tap
from a half-texel nudge.

**Filter parameters are per-record constants.** Of 6,793 program-valued parameters in a
corpus sample, 5,338 read `$sizelog2`, 69 read `$size` and **none** reads `$pos`, so evaluate
each once. A `pixelprocessor`'s image program does read `$pos`, and for it `$size` and `$pos`
must describe the same grid, the one it is drawn on. Otherwise a neighbour tap goes
sub-pixel and the filter silently becomes an identity.

**Inside an FX-Map, `$pos` is the node's base position, and its value is the origin**
(`fx.pos = origin`; the `corner` arm exists, and a per-pixel `$pos` is refused). FX-Map
node programs read `$pos` on 26,758 of 41,164 `fxmaps` records, almost always in an `0x89`
gate as `$pos + <an offset the program scans>` tested against a float4 rectangle the record
bakes: a cull, not a placement. So `$pos` is the absolute base of a relative walk. Only the
origin puts the scan on the lattice that the rectangle's bounds align to. It is a per-node
constant, and a per-pixel `$pos` would return N verdicts where the walk consumes one
(FORMAT-NOTES.md, "`fx.pos` = `origin` confirmed: `corner` KILLS EMISSION ON 86 RECORDS").
The open case is a subdivided FX-Map (§13.7). The chain walk is flat, so there is one node
position, and it is the root's.

**How an image reaches a program.** `samplelum`/`samplecol` take a **sampler index**, which
is the *first* immediate in both their 2- and 3-operand encodings. It is in range on 5,711
of 5,714 three-operand samples (FORMAT-NOTES.md, "Chasing the three LIVE samplers: an ISA
correction, a provable fix, and one open question").

- Bind sampler `k` to the record's `k`-th edge (§6.3). An unwired edge is left unbound.
- On a record that is itself a declared output, sampler indices that no edge binds are
  bound to the graph's image inputs in manifest declaration order (`Context.sampler_bindings`).
  This is the one thing the assembly cannot supply, and the record is marked low-confidence.
  Expect it to resolve few images: of 120 graphs with image inputs, 107 have no manifest
  default on any of them and ship no image.
- A live read of an unbound sampler is a cascade failure (§13.2). A read whose every use is
  multiplied by a constant 0 is bound to zeros (§13.6).

**Three program semantics, each behind an arm.** Each was arbitrated on one construct:
`Bricks_and_tiles` records 10175–10253, a Flood Fill compiled to pixel processors, with
jump-flood passes that store texel offsets in their channels and double them each pass
(FORMAT-NOTES.md, "Record 10253 is not the fault").

- **`select` is demand-driven** (`program.select = lazy`; `eager` is the arm). A `set` under
  a `select` branch executes only on the lanes that demand that branch. A tiling FX-Map's
  gate writes its row height and edge into slots inside the branch that starts a row, and
  evaluating both arms clobbers them on every emission.
- **`rand` in a pixel program draws per pixel** (`pixelprocessor.rand = pixel`; `image` is
  the arm). The hash is salted by the pixel's row-major index plus one. Inside an FX-Map the
  draw is per emission and per region (§13.7). The hash itself is arbitrary, so an export
  can be matched only in its statistics (§13.9).
- **An encoded field is sampled nearest** (`pixelprocessor.sample = nearest`, the texel
  `floor(pos · W)`; `bilinear` is the arm). A texel offset or a cell id in a float channel
  does not survive interpolation across a cell edge.

**The `0x03`/`0x06` value cache is cross-record common-subexpression elimination.** The
writer is one record and the reader another, so a render needs one dict threaded through
the whole file in record order, which the §13.2 pass is. Writers precede readers on 7,074
of 7,074 matched pairs. Its indices name no file, so the cache must not outlive the render,
and a program compiled against one cache must never run against another (`ops.bind`)
(FORMAT-NOTES.md, "`0x03`/`0x06` are cross-record common-subexpression elimination").

### 13.6 Filter semantics

`pos` is pixel-centred, `(col + 0.5) / W`. Sampling is bilinear and **wrap-tiled** unless a
row says otherwise. `I` is the record's `intensity`. `ref` is the pixel scale of a
pixel-valued intensity: the record's **tag** width (`warp.reference_px = tag`; the rendered
width `record` and fixed widths are arms); `blur`, `normal` and `distance` use a fixed 256
instead. `gx`, `gy` are per-pixel central differences of a map's channel 0. Omitted values
are §13.8's.

| filter | output |
|---|---|
| bitmap | the resource payload (§9), `u8`/`u16` → `[0,1]`; or a graph input's manifest default as a uniform |
| uniform | `outputcolor`, clipped to `[0,1]`; else a program at a walk-named slot; else the engine default (§13.8) |
| blend | `clip(dst·(1−op) + f(dst, src)·op)`, `f` per mode below, `dst` = input 0, `src` = input 1; `op` = `opacitymult` (at either of its `w1` positions, §13.4; absent ⇒ 1) × channel 0 of input 2 when a third edge is present. `switch` selects `src` where `op ≥ ½`, else `dst` (`blend.switch = threshold`; `lerp` is an arm). Unequal channel counts, or a mode outside 0–11, refuse |
| transformation | `in = m·(pos − ½) + ½ + offset`, `matrix22`'s words **column-major**: `x_in = m0·x + m2·y`, `y_in = m1·x + m3·y` (`transformation.matrix = columns`); absent matrix ⇒ identity, absent offset ⇒ 0. Symmetric matrices read the same either way; row-major turns RoofTiles record 62's quarter turn the wrong way (FORMAT-NOTES.md, "RoofTiles: the shingles were upside down"). Box-halve the source while one output pixel covers ≥ 2 source texels |
| shuffle | tag bit 0 (colour) decides. Clear (`grayscaleconversion`): `Σ channelsweights·src`; a non-zero weight on a channel the input lacks refuses. Set (Channel Shuffle): byte k of `w1` is output channel k's selector `s`, taking channel `s mod 4` of input `s div 4`; every byte is 0–7, else refuse the record rather than guess. Unspecified channels compile to input-dependent bytes (`[0, 4, 0, 0]` with two grey inputs, `[0, 1, 4, 3]` with a four-channel input 1), never a fixed pass-through (FORMAT-NOTES.md, "`shuffle`'s channel selectors are four bytes in slot 1"; source support in "`Add Sub` is `d + 2s - 1`") |
| levels | **per channel**, each field at its declared width: `t = clip((src − lo)/(hi − lo))`; zero span ⇒ `t = [src ≥ lo]` (`levels.zerospan = step`); `t ← t^(ln½/ln mid)`, `mid` held in `[10⁻⁴, 1 − 10⁻⁴]`; `out = clip(lo′ + t(hi′ − lo′))`. A colour record's fields are Float4s whose components differ; applying component 0 to all four remaps alpha by the red curve (FORMAT-NOTES.md, "`levels`: the renderer is right") |
| curve | a cubic-Bézier transfer curve, sampled to a lookup, applied per channel to the clipped input |
| gradient | a ramp indexed by the input's channel 0 (clipped), linear between stops |
| dyngradient | as `gradient`, the ramp being input 1's middle row or column along its longer axis, nearest entry |
| hsl | RGB → HSL, then `hue += h − ½` (mod 1), `sat ← clip(sat·2s)`, `lum ← clip(lum + lu − ½)`, back to RGB; alpha passes. Each defaults to ½, the neutral value, so an unnamed parameter is silently an identity |
| blur | separable box of half-width `r = round(clip(\|I\|,0,256)/256 · max(W,H))` px, clipped; `r < 1` ⇒ identity (`blur.subpixel = identity`; `fractional` is an arm). `I` is in **pixels at 256 whatever the record's size** (`blur.reference_px = 256`): the `256/min($size)` idiom means one pixel only under it. On a capped grid that idiom falls sub-pixel and an edge detector `\|x − blur(x)\|` reads 0; score at native (§13.9) (FORMAT-NOTES.md, "Graph 001's stones never existed") |
| sharpen | `clip(src + amount·(src − box₁(src)))`, `box₁` the 3 × 3 box; `amount` = `intensity`, baked or a program, absent ⇒ 1. A stated 0 is a value, not an absence |
| dirmotionblur | the mean of 17 taps at `pos + (k/16 − ½)·L·(cos θ, sin θ)`, `k` = 0…16, `θ = 2π·mblurangle`, `L = max(clip(\|I\|,0,256), 1)/ref` in canvas units for `I ≠ 0` (0 is a pass-through) — `I` pixels at `ref` in total, never less than one tag texel, no further factor (`dirmotionblur.extent = floor`; `total` (no floor), `radius` (2L) and `x8render` (`L = 8·clip(\|I\|,0,256)/W`) are arms) (FORMAT-NOTES.md, "Where graph 004 loses the top two octaves"; "The round-tile groove"; "`floor` promoted") |
| directionalwarp | input 0 sampled at `pos + ((2h − 1)·I/ref)·(cos θ, sin θ)`, `θ = 2π·warpangle`, `h` = input 1's channel 0; absent intensity or angle ⇒ 0 |
| warp | input 0 sampled at `pos + (gx·W, gy·H)·I/ref`, `gx`, `gy` of input 1 — the **gradient** of input 1 (FORMAT-NOTES.md, "`tag` promoted, COMMITTED") |
| normal | `n = normalise(−gx·I·W/256, −gy·I·H/256, 1)`, `out = clip(½ + ½n)`, alpha 1 on a colour record; `inversedy` (`w1` field 1: baked ⇒ set, program ⇒ value > ½) negates `gy`. The reference is a **constant 256** (`normal.reference_px = 256`), not the record's size: the engine's own exports fit `slope = (I/g)·(R/256)` at R = 2048 and 4096. A residual on this channel is its height input's (FORMAT-NOTES.md, "`f_normal` reproduces the engine's own normal-from-height relation"; "The second pack settles it") |
| emboss | `clip(base + k·(g(pos) − g(pos + (δ, −δ))))`, `base` = input 0, `g` = input 1's channel 0, `δ = 0.005859375` (1.5/256), `k = 0.1` (`emboss.intensity = reference`; `program`, an arm, reads a record program instead and costs Bricks 002 basecolor) |
| distance | `clip(1 − d/R)`, `d` the Euclidean distance to the nearest lit (> ½) pixel of the mask input (edge 0), 0 when none is lit; `R` = `w1` field 1 (§13.4), baked or a program, in **pixels at 256** (scaled by `W/256`); unit and linear falloff arbitrated (FORMAT-NOTES.md, "`distance`'s radius unit and falloff shape"). A fallback locator answers records that name neither arm; mark each. A second edge that is a DIFFERENT record is a **source** (edge 1 is colour exactly when the record is, 1,693 of 1,693): the output is the source's value at the nearest lit mask pixel, flat out to the radius, 0 beyond — **`spread`** (`distance.propagate = spread`, i.e. `combinedistance = 0`, which every permitted sighting declares; `field` (source ignored), `nearest` (source × falloff), `flag` are arms). A source that is the mask record itself is no source (FORMAT-NOTES.md, "`distance.propagate = spread` is the default") |
| vectorshape | filter 5, a generator: the embedded triangle strip (§9, `vector_shape` / `vector_faces` — joins and part boundaries dropped) rasterised as a mask, 1.0 where a triangle covers a pixel centre, 0.0 elsewhere; no parameter is read (the class-bit-25 float is 1.0 on every record checked) |
| pixelprocessor | the program at the **last header slot**, per pixel; earlier slots (inherited parameters, setup) run first to seed the slot frame. Inputs are read **nearest-texel** (`pixelprocessor.sample = nearest`); `rand` is salted per pixel (`pixelprocessor.rand = pixel`). In a **canvas-sized** record (declared size = `2^$outputsize`) `$size`, `$pos` and `$outputsize` all describe the grid it is drawn on (`pixelprocessor.outputsize = grid`), so a texel derived as `0.5 / 2^os` is a pixel; a record pinned to its own size (Chesterfield's 2048 × 16 HBAO LUT) reads the render's `$outputsize`. An unset slot reads 0 (`pixelprocessor.unset = zero`; an accumulator's initial value, Onyx 1470). A `sample` past the wired arity whose every use is multiplied by a constant 0 is bound to zeros; a LIVE read of an unwired input refuses (FORMAT-NOTES.md, "A pixel processor's `$outputsize` is the grid it is drawn on"; "SandyStonePath renders end to end") |
| fxmaps | §13.7 |

**Blend modes.** The `blendingmode` nibble's values and `f(d, s)`:

| mode | `f(d, s)` | arithmetic fixed by |
|---|---|---|
| 0 copy | `s` | name |
| 1 add | `d + s` | name |
| 2 subtract | `d − s` | name |
| 3 multiply | `d·s` | name |
| 4 addsub | `d + 2s − 1` | a permitted source's implementation |
| 5 max | `max(d, s)` | name |
| 6 min | `min(d, s)` | name |
| 7 switch | selects on `op` (above) | name; threshold ½ is convention |
| 8 divide | `d/s`, `\|s\| < 10⁻⁶` read as 10⁻⁶ | name; operand order is convention |
| 9 overlay | `2ds` for `d < ½`, else `1 − 2(1−d)(1−s)` | name; gate on `d` is convention |
| 10 screen | `1 − (1−d)(1−s)` | name |
| 11 softlight | `2ds + d²(1−2s)` for `s < ½`, else `2d(1−s) + √d(2s−1)` | name; member is convention |

The names are **declared, not conventional**: where a permitted source exposes
`blendingmode` as a graph input, its `dropdownlist` labels 0–11 exactly so and the node's
parameter is a literal `get_integer1` pass-through. An option string reads
`default;value;label;…`, the leading token the widget's default (all 375 dropdowns in the
permitted sources have an odd token count; the leading token equals `<defaultValue>` in 357).
The support is one collection, two files, no declared author, raised by a tool-generated
`<description>` block — an inference, stated as one (FORMAT-NOTES.md, "`blendingmode`'s twelve
names are declared by a permitted source"). The enumeration is **closed at 11**: over 310,697
corpus blend records the nibble never takes 12–15. Modes 2 and 5 also stand structurally:
mode 2 in both orders combined by mode 5 is `max(a−b, b−a)`. `addsub` is fixed by a permitted
`.sbs` that reimplements five modes as pixel processors (`hadd` … `hmax`, each
`lerp(bg, lerp(bg, f(bg, fg), opacity), mask)`), which run agree with the table to 1.1e-16
(FORMAT-NOTES.md, "`Add Sub` is `d + 2s - 1`"). `softlight`'s member is **undecidable here**
(the W3C formula differs from it by at most 0.000455 over the reference packs' 17.4 M mode-11
pixels); `overlay`'s gate is decidable in principle (read on `s` it is `hardlight`) and the
reference packs do not decide it.

**Operand order is settled by the source**: input 0 is `dst` = `destination`, input 1 is `src`
= `source`. The 28 paired records identified by a unique `opacitymult` all place the declared
`destination` at slot 0 (control: 2 of 30), modes 9 and 11 included; the source states a
blend node has exactly the connectors `destination`, `source`, `opacity`.

A second enumerated `blend` parameter, `colorblending` (`0 Use Source Alpha, 1 Ignore Alpha,
2 Straight Alpha Blending, 3 Premultiplied Alpha Blending`), is named by the same mechanism
and its slot is **not located**; it is in FORMAT-NOTES.md, not §13.4's legend, because a name
legend states where a field is and this one cannot.

### 13.7 FX-Map evaluation

Walk the chain of §8 nodes; the table entries at its end are the draws — and the entries
are themselves a tree of Quadrants, each drawing in its own region (**Subdivision** below).

| node | role |
|---|---|
| `0x18B` `0x1AB` `0x19B` | **iterate** — run the loop child (the successor) `numberadded` times, `$number` = 0…n−1; `0x1AB` (`0x18B` \| `0x20`) runs its `randomseed` program first; `0x19B` is `0x18B` under bit 4 (its program returns an integer count, 245 of 245) |
| `0x1CB` | **iterate with an after-child** — the loop child is the successor (word 3); the spare word (2) names a child run ONCE after the loop, where the record puts the draw pass that reads the loop's accumulated slots |
| `0x89` | **switch** — its program returns a predicate; the successor is the TRUE child, the spare word (2) the FALSE child, 0 for none. "Walk on while true" is the false-child = 0 case |
| `0x99`, other `0x??9B` | **stepper / switch** — a per-iteration state update (a raster/spiral position); `0x99`'s spare word (3) is a FALSE child when wired |
| `0x1DB` `0x1A3` | `0x1CB` / `0x1AB` **in a variant compile** (bit 3 clear; bit 4 set on the two-pass node). `0x1DB` is `[hdr][baked word][program][after][loop]`, its program `0x1CB`'s (zero the statistics slots, return 1); `0x1A3` has `0x1AB`'s shape (FORMAT-NOTES.md, "`0x1DB` and `0x1A3` are the Bricks tiling") |
| `0x??1B` | **branch** — bit 7 clear, no program of its own. Word 1 `0x3039`: two children, a pointer at word 2 and a node contiguous at word 3, both walked; word 1 `0` (12 nodes, one file): the entry table follows at word 3 (FORMAT-NOTES.md, "The last hand-stated node entry, `FX_NODES2[0x1B]`") |
| `0x??0B` | **leaf** — the entry table draws. **`header >> 8` is the baked emission count**: `0x190B` 25, `0x510B` 81 = 9², `0xE100B` 3600, and products the placement readers cannot express (`0x770B` = 119 = 7 × 17). `0x20B` is an addnode baking `numberadded` = 2 in this form; plain `0x0B` states none (`fx.leafcount = header`; `one` is an arm) (FORMAT-NOTES.md, "The blur value cannot be seen because the picture behind it was blank") |

**The spare words are children.** `fx.chain = tree` (`render2/fxchain.py`) walks `0x89` /
`0x99` false children, `0x1CB` after-children, `0x19B` loops and the `0x1DB` / `0x1A3`
iterates; a record holding none of them takes the one-successor list walk (`fx.chain = list`
keeps that walk for every record, reading spare words as nothing and running `0x19B` once as
a stepper). Which word is which is read off Bricks 10081: its Switch program writes a column
count into slot 45 when false and a row count into slot 46 when true, and the false word
addresses the `0x19B` whose program returns slot 45. The false child is wired on 205 of
27,093 corpus `0x89` and 88 of 238 `0x99`, the after-child on 65 of 1,865 `0x1CB`
(FORMAT-NOTES.md, "Record 10253 is not the fault").

**The emission count**, first rule that applies; a leaf-only chain instead emits its leaf's
count (`$number` = 0…n−1; once for a plain `0x0B`).

1. A placement program lays a `$number` **grid**, `floor($number / N)`: `N²`, not
   `numberadded`, which for those records is an amount (`fx.gridcount = divisor`; on the
   five reference packs `numberadded` now reaches the same draws through rules 2 and the
   chain walk, FORMAT-NOTES.md, "The call-site defaults, checked").
2. `numberadded` is 1 and the leaf states a count > 1: the leaf's count (Tiled roof 383's
   count is a spiral bound, 1 on a square canvas, under a leaf stating 22). A count other
   than 1 stands, and agrees with the leaf's.
3. `numberadded` is 1 and a placement program scales `$number` **linearly** by exactly one
   constant `1/N`: `N` — the record computes N positions and visits one. Read the constant
   off the **bytecode**: integer constants are spelled bare, and `const.i1 27` read as
   float32 is 3.78e-44.
4. Otherwise `numberadded`.

Under rule 1 steppers run once and gates per emission; under rules 2 and 3 both run **once**
and the gate's predicate is not consulted: the placement already carries each position, and
re-driving the spiral adds a second one.

**Drawing.** Canvas coordinates have 0 at the canvas centre. Each entry emits a pattern
centred at `branchoffset + frameoffset`, of size `patternsize`, rotated `2π·patternrotation`
counter-clockwise in the x-right, y-down frame (`fx.rotation = ccw`; non-finite ⇒ 0). It is
drawn at its centre and at whole-canvas offsets up to `min(3, ⌈max size⌉)` per axis where
those copies overlap the canvas (`fx.centre = reach`); `fx.centre = wrap`, an arm, first takes
the centre modulo the canvas, the only reading under which all of RoofTiles record 7's rows
(`branchoffset` x = 0, 0.5, … 4.5) land. Skip a pattern whose size or centre is non-finite,
whose size is `≤ 0`, `> 64` or `< 10⁻⁶` (the corpus has nothing between 1e-30 and 1e-06), or
that is a marker (tag low byte `0x08`, `fx.markers = skip`). No `patternsize` ⇒ the whole
canvas (`fx.sizeless = fill`; `skip`, `half`, `quarter` are arms). A cell that **states nothing to draw with** — pattern
nibble 0 (and not a marker) with no `patternsize`, `opacity` or `imageindex` — draws nothing: it
only places regions (`fx.bare = skip`, on both draw paths). `fill`, an arm, draws it like any
sizeless pattern at opacity 1, and under `max` that square hides every pattern after it: all
587 corpus FX-Maps holding such a cell then render as a constant, and none do under `skip`
(FORMAT-NOTES.md, "`fx.bare`"). The value is
`clip(opacity, −1, 1) · gain · profile` (absent opacity ⇒ 1, `fx.negopacity = signed`), times
the named input image sampled over the footprint when `imageindex` is present (absent on a
record with exactly one image input, it names that input). Patterns combine by **`max`**, for
every entry (`fx.combine = max`); the canvas is clipped to `[0,1]`.

**The record's header states the canvas and a global gain** (§7.4's fields, named by two
permitted pairings): field 0 `background` (one word grey, four colour) is the canvas's
initial value (absent ⇒ 0); `gain = opacitymult · 2^(−hurst·k)` from field 2 `opacitymult`
(Global Opacity) and field 1 `hurst` (Roughness), `k` the region depth (**Subdivision**)
counted from the root, 0 for a flat draw (`fx.header = read`, `fx.hurst = exp`,
`fx.hurst.depth = root`; absent `hurst` ⇒ 0; `off`, `exp2` = `2^(−2·hurst·k)` and
`pow` = `hurst^k` are arms). The fields are not vacuous: all 2,071 records whose entries bake
a negative `opacity` bake `background = 1.0`, and none of the 2,874 with only non-negative
ones does. A baked `opacity = −1` is one library construct, a (5,1) stroke subtracted from a
white canvas; under `max` it does nothing, so its draw is the gain's question, not the
combine's (FORMAT-NOTES.md, "Graph 001's first annihilation point is a white canvas"). Entry
tag **bit 18 says a `blendingmode` is declared** on the source's `paramset` (ie_curve 43 of
43, ie_pcloud 110 of 110, Simulator__Grid 0 of 19); the combine is `max` either way, and
`bit18` (clear ⇒ signed add), `background`, `add` and `over` are arms (FORMAT-NOTES.md, "The
dirt overlay's coverage is the combine").

**The profile** is set by `patterntype` (§8) over the footprint `|lx|, |ly| ≤ ½` (0 outside),
`r = 2·√(lx² + ly²)`, clipped to `[0,1]`: `3 disc` `[r ≤ 1]`; `4 paraboloid` `1 − r²`;
`5 bell` `(1 − r²)²` (`fx.bell = t2`; `gaussian` an arm); `6 gaussian` `exp(−4r²)`;
`7 thorn` `(1 − r)³`; `8 pyramid` `1 − max(|2lx|, |2ly|)`; `9 brick` the whole footprint
(`fx.brick = fill`; `inset`, an 85% hard inset, an arm); `10 gradation` `½ + lx`; `11 waves`
`½ + ½cos(4π·lx)`; `12 half bell` `exp(−4r²)` where `ly ≥ 0` (`fx.halfbell = gaussian`;
`paraboloid` an arm); `13 ridged bell` `(1 − r)·|cos 3πr|`; `14 crescent` `1 − r` outside
`2·√((lx − 0.15)² + ly²) ≤ 0.75`; `15 capsule` `1 − max(|2ly|, max(|2lx| − ½, 0))`; `16 cone`
`1 − r`. Nibble 0 is a catch-all (patterntype 1, 2 — Square — and function graphs) drawn as the
whole footprint (`fx.typeless_profile = rect`); 17 is unassigned. A name fixes the family; the
curves of bell, thorn, brick, waves, half bell, ridged bell, crescent and capsule are
modelled.

**`patternsize`** is in canvas units under the flat draw, region units under the tree, and
**not bounded by 1** — `(5.0, 1.0)`, `(8.0, 1.25)` are routine baked values. An entry
parameter is `baked` (the entry's own slots, §8) or a **program** evaluated per emission.
Baked sizes are always sane (3,732 of 3,732 over 60 permitted specimens); bad sizes come
from program evaluation only, and the skip rule removes them — 0.09% of patterns, not an
amplitude cause (FORMAT-NOTES.md, "SPEC: where the format is read as individual bits"). A
record's setup programs are already a fixed point, no entry reads another entry's write, so
table order cannot matter, and no FX program reads an undeclared graph input; the reciprocal
reading of a baked size is refuted (FORMAT-NOTES.md, "`patternsize`'s setup chain was never
out of order"). Sizeless patterns are 1.9% corpus-wide, 18.3% on Auras. Open: the modelled
curves, the tile lattice, and under the flat draw a cell rather than canvas unit for the
offsets and size (`fx.patternsize`, `fx.branchoffset`, `fx.frameoffset`, default `canvas`).
The `(5.0, 1.0)` two-entry family in five of the six reference packs is the −1 construct.
The one sharp arbiter agrees: ChesterfieldSofa's `metallic` reproduces its export at MAE
0.0004.

**Subdivision is in the entry table, not the nodes.** A `paramset`'s four outputs are the
quadrants of its region; in the permitted `SubstanceDesigner__Clouds_3_Animated` each chained
`paramset` names the same child on `output0`–`output3`, and compiled record 50 walks four bare
`0x20008` cells and then the two draws. So the entry run of §8 is a nesting: each cell is a
Quadrant, its bit-17 pointer its child on all four outputs, its bit-16 pointers one child per
output. Half of Bricks' 191 FX-Maps nest (depths 3–9); Chesterfield's `metallic` is depth 0.
The draw model (`render2/fxtree.py`; FORMAT-NOTES.md, the three entries beginning "The level
fault upstream of 10055", and "Quadrant subdivision lands in render2"):

- **The root does not subdivide.** The first cell's region is the canvas and so is its
  children's. Region depth `k` is 0 for the root and its children, +1 per quadrant level;
  region size is `2^−k` (nesting depth `d ≥ 1` ⇒ `k = d − 1`). Seed-free support: 879 of
  1,146 sizeless leaves sit one level deeper than their record's size, and Bricks 9924
  (`rand(1.0)` under five Quadrants, 16 px) reads mean 0.513 / sd 0.292 / lag-1 −0.012,
  uniform white noise, against 0.80 / 0.16 if the root subdivides.
- Output `j`'s child region is centred at the parent's centre `+ (±s/4, ±s/4)`, `s` the
  parent's region size; `fx.tree.order = rowmajor`: 0 top-left, 1 top-right, 2 bottom-left,
  3 bottom-right (`clockwise`, `colmajor` arms).
- `patternsize` and `frameoffset` are in REGION units; a sizeless, non-marker cell fills its
  region, except a cell that states nothing to draw with, which draws nothing (`fx.bare = skip`, **Drawing**). A cell's programs run once PER REGION with a fresh `rand`
  draw; `$number` stays the emission index.
- **Open:** `branchoffset`'s unit (`fx.tree.branchoffset = canvas`; it offsets the cell's
  pattern and children, and Bricks 9804's author halves it by hand per level), the quadrant
  order, and `$pos` per region (§13.5; not threaded through). The order shows only where a
  cell's outputs name distinct children — 244 of 23,462 subdividing records, none in a
  scored pack — so it needs a specimen pack with an export.

`fx.subdivide` chooses who draws the tree: `flat` (default: every entry once at full canvas,
cells read as links), `noise` (the 16-px `rand(1)` White Noise class), `quadrant` (every other
subdividing record) and `tree` (both; `noise` and `quadrant` partition it). A chain opening a
`0x9`/`0x49` pointer-cell list is drawn by the tree under `fx.pointercell = switch` regardless.
`noise` and `tree` are refused; `quadrant` waits on the gain at depth (FORMAT-NOTES.md,
"`fx.subdivide` re-measured whole").

### 13.8 What the file does not state

The compiler omits a parameter the source left at its node default, so the default is in
neither the assembly nor the manifest. Any renderer needs these values; every use should be
marked, because they are the only numbers in it that come from outside the file.

| value | used by | reads as | evidence |
|---|---|---|---|
| `channelsweights` | grayscale conversion | `(⅓, ⅓, ⅓, 0)` | of 5,457 baked vectors the even weight never appears while its neighbours do — an argument from an absence |
| `uniform` fill | a uniform with no `outputcolor` and no fill program | black | one specimen's `metallic` output is such a record; its export is 0.0 at every pixel |
| `levels` ranges | absent level fields | in `(0, ½, 1)`, out `(0, 1)` | — |
| `warp` intensity | 3.1% of warps | 1.0 | 0 of 26,108 compiled and 0 of 15 permitted-source intensities are 1.0; 0.5 and 2.0 occur |
| `normal` intensity | 116 of 1,379 | 1.0 | 0 of 1,263 stated intensities are 1.0 |
| `blur` intensity | 137 records, 81 files | 10.0 | stated once in 14,931; 8.0 at 21, 16.0 at 31 |
| `dirmotionblur` intensity | 8 records | 10.0 | weaker: 10.0 and 5.0 both stated 0 times in 14,278; 10.0 is `blur`'s |
| `sharpen` intensity | absent field | 1.0 | 0 of 1,148 stated; 0.5 at 59 |
| `hsl` fields | absent fields | ½ each | the neutral value (§13.6) |

The intensity rows rest on one mechanism: an author who wants the default leaves the
parameter alone, so the default is the round value **stated zero times** beside stated
neighbours — `blur`, the control, states 1.0 over ten thousand times (FORMAT-NOTES.md,
"Permitted sources corroborate `warp` default = 1.0"; "`blur`'s omitted intensity is 10.0").
Every reference channel is inert to the `warp` and `normal` values (§13.9); none can
arbitrate `blur`'s.

A record whose arithmetic produces a non-finite sample (an Auto Levels dividing 0/0 on a
constant input) writes **0** there: every node's output is a texture, and IEEE NaN converts
to 0 in a UNORM texture. Mark the record.

**The seed.** `$randomseed` is a graph input with a manifest default, and an export may be
taken at any other value, written down nowhere: `Kutejnikov__Bricks_and_tiles` ships two
export sets from byte-identical packages whose randomised graphs correlate +0.02..+0.10. And
the compiled `rand` is a sequence the engine draws; this document's hash of `$number` and a
per-region salt reproduces its statistics, never its values. So for any record downstream of
a `rand` — every subdivided FX-Map in Bricks calls one — pixel agreement with an export
measures the seed, not the reader. §13.9 is the consequence.

### 13.9 Arbitrating without the seed

What survives a reseed is the STRUCTURE each node adds, so the arbiter for a rand-driven
graph is a set of seed-free instruments (`archive/tools/structstats.py`), each one number per
channel with its own measured floor:

| instrument | extracts | renderer-side reseed floor (Bricks 003 height, 256 px) |
|---|---|---|
| `mean`, `p5`, `p50`, `p95`, `sd` | level | mean ±0.02 |
| `pitch_x/y`, `pitch_peak` | first autocorrelation peak — row/brick period and its regularity | — |
| `line_width` | 25th-percentile dark-run length (dark = below Otsu) along rows and columns — a mortar width | ±1 px |
| `line_jitter` | sd of the per-column centroid of darkness around each horizontal dark line — how far a brick edge wanders | ±0.02 px |
| `blob_d`, `blob_n` | median diameter and count of bright components (Otsu, ≥ 4 px) — a stone or brick | ±0.4 px |
| `tone_between` / `tone_within` | sd of per-blob means / mean per-blob sd — the tone per brick and the texture inside one | ±0.004 |
| `grain`, `noise_lag1` | power above half Nyquist; lag-1 autocorrelation (0 for white noise) | — |

The renderer-side floor is measured by reseeding every draw. Uses, in the order they decide
things (FORMAT-NOTES.md, "Structural instruments: what a picture states about its nodes"):

1. **The file against itself, no export.** A `rand(1.0)` leaf at one cell per pixel must read
   mean 0.50 / sd 0.29 / lag-1 0; a record's own canvas states the cell size its author
   expected (§13.7's 879 of 1,146).
2. **Level and structure against an export, the floor as resolution.** An export at a second
   seed moves Bricks' mean by 1.0% (median), p50 1.3%, p95 0.3%, sd 4.9%, and octave band
   shares by 18–58%, so spectral shape discriminates only moves larger than an octave. Bricks'
   second export set is not a pure reseed (row pitch 32 px in one, 42–43 in the other), so it
   bounds the reference-side floor from above.
3. **Pixel correlation only where structure survives a reseed** (Bricks 004 and 005, +0.80
   to +0.99 between the export sets), and only as a regression guard: a variant may not cost
   more than 0.03 there. Their subdivided records supply detail, not layout, so they cannot
   arbitrate offset units or quadrant order.
4. **Per tile** (`structstats.py --tiles`): the graph's own tile mask segments the picture;
   per tile a plane is fitted to the height, its change across the tile (`|grad| × √area`)
   reported with the tile and mortar means. It reads what a draw model puts INSIDE a cell
   through a per-cell random direction correlation cannot (FORMAT-NOTES.md, "The corr guard's
   objection to `spread` is the rand hole").
5. **The native row** (`archive/tools/nativeguard.py`): every pack at its implied
   `$outputsize`, no grid cap. Every texel-dependent construct hears a capped grid differently
   — a flood fill's seed pass finds no edge, a `256/min($size)` blur is the identity at one
   grid and a pixel at the next — and no one `$size` reading is right under a cap. It scores
   through `render2-lean`, its graph-input overrides installed on every binding of the
   renderer (FORMAT-NOTES.md, "`nativeguard.py` was scoring through the NON-lean renderer").

**The score** is taken from ONE render at the pack's implied `$outputsize`, resampled to 128 /
256 / 512 — not three renders at three `max_dim`s. The companion instrument takes its tile
labels from the EXPORT's own normal map (the height is unimodal and cannot), so its reference
side does not move with the renderer (FORMAT-NOTES.md, "The companion instrument rebuilt on
EXPORT-derived labels").

**The rule for a default.** A reading becomes the default when it passes the ratchet —
`test_render2_reference_agreement_does_not_regress`, per row on corr, band and dc at 128 /
256 / 512, against bounds taken when the row was first scored — and the old reading is kept
as a named arm. Per-pack mean correlation is not the ratchet: it hid the loss of a whole AO
channel (Chesterfield's, band 0.0007) behind +0.887. **A correlation floor may be re-taken
lower under a companion instrument** (`refguard.Entry.companion`) — a seed-free measurement
of the same channel that a per-cell random draw cannot move (Bricks' per-tile tilt and level,
the pillow profile, the band power in the octaves the reading acts on), guarded by its own
test (`COMPANION_INSTRUMENTS`), the replaced bound kept; correlation is then ratcheted from
the re-taken value. The effective default is the CALL SITE's: `assume.assumed(key, default)`
returns `default`, so promoting an arm means changing its call sites, not only
`assume.QUESTIONS`.

The defaults, by the section that states them (each arbitrated in FORMAT-NOTES.md):

| section | defaults |
|---|---|
| §13.2 | `graph.outputsize = pergraph` (every floor it touched re-taken; FORMAT-NOTES.md, "STATUS: the re-take is done") |
| §13.6 | `transformation.matrix = columns`; `pixelprocessor.outputsize = grid`, `.rand = pixel`, `.sample = nearest`; `blur.reference_px = 256`; `warp.reference_px = tag`; `dirmotionblur.extent = floor`; `distance.propagate = spread` (33 Bricks correlation floors re-taken under it) |
| §13.7 | `fx.leafcount = header`; `fx.chain = tree` with `program.select = lazy` (without `lazy` it turns 10081's row-start count into 2³¹ − 1); `fx.header = read`; `fx.combine = max`; `fx.negopacity = signed`; `fx.hurst = exp`; `fx.hurst.depth = root`; `fx.brick = fill`; `fx.halfbell = gaussian`; `fx.bare = skip` (on structure alone: no scored output holds such a cell) |
| §13.8 | `warp.default_intensity = 1.0`, `normal.default_intensity = 1.0`, `blur.default_intensity = 10.0`, `dirmotionblur.default_intensity = 10.0`, `nonfinite.fill = 0.0` |
| §8 | `fx.pointercell = switch`, on the structure alone as `fx.leafcount`: the ratchet packs carry no such record (FORMAT-NOTES.md, "The `0x9`/`0x49` pointer-cell list") |

Refused and kept as arms: `distance.propagate = field` (tiles a third of the way to white, no
per-tile tone), `fx.subdivide = tree` and `noise` (§13.7), `blur.subpixel = fractional`
(within 0.004 of the defaults at native, worse at 256), `fx.gridnamed = branchoffset` (inert:
leaf-only chains that spell a grid in `branchoffset` take the leaf's count) and
`fx.hurst.depth = firstdraw` (it prints the subdivision lattice into the image; FORMAT-NOTES.md,
"`fx.hurst`'s depth origin decided by LOOKING").
