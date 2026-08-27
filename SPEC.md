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
0x38            embedded resource segment   ]  length == base   (image payloads; §9)
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

### 6.2 The two header words

```
word0:  low16  = flags (bit 0 = colour: 0 grayscale, 1 colour)  +  filter id
        high16 = CLASS WORD — presence mask over INHERITED parameters
word1:          two-bit code per field — the filter's OWN parameters
```

- **Class word (word0 high half):** each set bit adds one inherited-parameter field, in
  ascending bit order. Widths come from the manifest type of the parameter that bit gates
  (§7.2): bit 10 is `$outputsize` (integer2 → 2 words); the other common inherited
  parameters are 1 word each.
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

### 6.4 The four layout alphabets

The file states each filter's layout in one of four self-describing ways; a reader
handles all four with the one primitive and needs no fitted table:

1. **Two-bit presence codes** — word1 as above (blend, levels, transformation, warps).
2. **Arity integer** — the header states an input *count* as a small integer in word1 and
   the walk reads that many edge slots (pixelprocessor; fxmaps, after its tree-root
   pointer).
3. **Paired conjunction** — two class-word bits that, set *together*, name one field
   (bitmap's bits 24+27 = the pixel-offset word).
4. **Class-word popcount** — the number of leading block slots that are *programs* is
   `popcount(class_word & mask)`; the rest are baked (blur, warp). This decides slot
   *role*, and through role, extent (e.g. `nprog == 0` ⇒ a baked `(w,h)` size pair
   instead of one program pointer).

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
records carry **544,873 baked parameter slots** against the corpus's **8,500** descriptors,
a ratio of 1 : 64.

Those two populations are disjoint. **A record's baked parameters are stored inline in the
record header, one word per component** (§6), and are never in the value table. A reader
built on the old sentence would look for 544,873 values in an array that does not contain
them.

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
rather than fitted. It reaches the record side too: over 437 specimens every one of the
**544,873** baked parameter slots the walk reads has a width of 1, 2 or 4 words —
`float1`, `float2`, `float4` — and **none falls outside the legend's 1..4**. (Width 3,
`float3`, is legal by the legend and does not occur.) Per filter:

| filter | 1 word | 2 words | 4 words |
|---|---|---|---|
| 1 `blend` | 137,808 | 26 | — |
| 2 `transformation` | 36 | 29,331 | 66,512 |
| 11 `dirmotionblur` | 25,654 | — | — |
| 12 `directionalwarp` | 115,122 | — | — |
| 15 `levels` | 163,992 | — | 1,735 |
| 17 `text` | 43 | 39 | 14 |
| 18 `normal` | 971 | — | — |
| 21 `distance` | 1,552 | 2,038 | — |

So the legend is not the gap. **What the file does not state is the per-field type CODE**,
and that is the object `costs.json` actually fits — a *kind assignment* per (filter,
field), not a width. Two searches for a per-node type declaration came back empty and are
recorded so they are not repeated: the interface block declares 8,500 typed descriptors
against 544,873 slots and is framed to the graph-input table alone (§7.1), and the record
directory holds bare offsets. The filter id *is* the declaration, and the parameter list it
names lives in the engine.

One kind is already stated rather than assigned, which is the existence proof that the
distinction is real: a `channel` field's component count is the **tag's colour bit** — 4
words when colour, 1 when grayscale — so `walk._field_width` derives it and does not fit
it. The open problem is the rest of the assignment, and its legitimate route is the
permitted `.sbs` sources, which declare parameter names and types per filter.

### 7.4 The field primitive — how `w1` gates and places a parameter

One rule places every parameter this project reads, and it is the §6.1 mask-walk applied to
the second header word.

**`w1` is a grid of two-bit FIELDS.** Field `j` occupies bits `(2j + s, 2j + 1 + s)`, where
`s` is the filter's **grid shift** — `0` for every filter measured, except `directionalwarp`,
where it is `1`. The two bits are a STATE, not a count:

    00  absent          the parameter is not present; it costs no slot
    01  baked           a constant, inline in the header, one word per component (§7.3)
    10  program         a pointer into the instruction stream (§10)
    11  image input     an edge — a backward record index, not a parameter at all

**Placement is a cursor, not an index.** The walk visits fields in ascending `j`, and each
present field advances the cursor by its own width. Nothing stores a slot number (§6.1), so a
parameter's position is the sum of the widths of the fields before it and cannot be computed
from `j` alone.

**A parameter's presence mask is exactly `3 << (2j + s)`.** This is what makes the rule one
rule rather than a per-filter table: over the five filters that declare parameters, all
fourteen masks resolve to exactly one field —

    blend            s=0    opacitymult 0x0030 -> field 2
    dirmotionblur    s=0    intensity 0x0003 -> 0     mblurangle 0x000c -> 1
    directionalwarp  s=1    intensity 0x0006 -> 0     warpangle  0x0018 -> 1
    levels           s=0    levelinlow 0x0003 -> 0 ... levelouthigh 0x0300 -> 4
    fxmaps           s=0    fx_param0 0x0003 -> 0 ... fx_param3 0x0300 -> 4

`directionalwarp` is the reason the shift exists and the reason it must be read rather than
assumed. Its `intensity` is bits 1 and 2, which STRADDLE the fields of an unshifted grid; a
matcher that assumes `s = 0` finds no field for it, names neither of its parameters, and
returns nothing on 62,146 records — silently, because an empty parameter list is
indistinguishable from a filter that declares none.

**The rule subsumes the positional fallback it was thought to need.** Because of that
straddle, `directionalwarp` was placed by a separate positional rule — "the present
parameters occupy the last `n` slots of the header". With the shift applied, the field rule
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
  word 3, `0x99` at word 4.
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
FX-Map field not yet decoded, and is the principal blocker to correct rendering.

---

## 9. Embedded images (resource table)

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
excluded from analysis. The format's *structure* is fully recovered — a reader can locate
and walk every region above from the file alone. What remains open is *semantics*: the
meaning of some filter parameters, the FX-Map pattern footprint (§8), and a handful of
provenance-walled specifics (e.g. `vectorshape` layout, inline FX parameter names). Reading
the file and reconstructing its graph is solved; rendering it pixel-for-pixel is not.
