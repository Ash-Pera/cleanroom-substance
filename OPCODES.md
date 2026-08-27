# `.sbsasm` opcode catalogue

**41 operations in 63 type-specific forms, all named.** Measured over 382 distinct
specimens (the corpus holds 579 `.sbsasm` files, ~34% duplicate content) and 11,845,287
instructions decoded by walking records to their bytecode. On distinct specimens, 96.5% of
instructions carry an operation id catalogued for their type, and **of the 82 opcodes that
appear in 20 or more distinct specimens, none has an uncatalogued operation id**. The
residual is component-count and length variants of named operations plus decode residue.

Seven further operations — `0x03`, `0x0B`, `0x0F`, `0x1E`, `0x2A`, `0x35`, `0x36` — fall
below that threshold and are established structurally rather than by frequency. They are in
the table below, marked `*`, which is why it carries 48 operation ids rather than 41.

The large raw opcode count is not a set of unknown operations: the encoding is
combinatorial, so one operation appears as many opcodes across type, component count, and
length (e.g. `0x0532`/`0x0524` are `rand`/`floor` at 1 component; `0x0861`/`0x085D` are
`lr`/`eq` on 2-component bools).

This file is organised as a reference, not as a derivation: encoding first, then how to
reach the instruction stream correctly, then the operations grouped by what they do and
ordered by operation id. The instruction/file counts are measurements, kept per row.

---

## Encoding

Instructions are a little-endian `u16` token stream, `(u16 arg, u16 opcode)` with the
opcode in the high half. Each instruction is one opcode token followed by its operand
tokens.

| bits | field |
|---|---|
| 15–10 | operand-token count — **instruction length = this + 1 tokens** |
| 9–8 | type: 0 bool, 1 float, 2 int (3 unused) |
| 7–6 | component count − 1 |
| 5–0 | operation id |

The length rule `length = (opcode >> 10) + 1` holds for every opcode in `0x0400–0x7FFF`, so
any program is fully tokenisable without a semantic table — unknown operations are skipped
exactly rather than guessed past. Records (`0x8000`+) are exempt; they are 4-aligned and
framed by the record directory, not part of the instruction stream.

**Three-address code.** One result per instruction, contiguous SSA value numbering; each
operand names an earlier result in the same program. Some operands are immediates: the
swizzle mask (`0x10`), variable-slot indices (`0x07`/`0x04`/`0x01`), the index read by
`0x03`/`0x06`, and the 4-byte immediate of a constant (`0x00`) or input reference (`0x02`).

**Padding.** Opcodes carrying a 4-byte immediate come in two forms differing by `0x0400`,
one extra token — a 2-byte pad emitted when the instruction lands at 0 mod 4 so the
immediate stays aligned.

**Component count and reference opcodes.** Bits 6–7 hold component count − 1, cleanly for
the reference and construct families:

```
float input reference   0x0902 + 0x40*(n-1)   ->  0902 0942 0982 09C2   n = 1..4
int   input reference   0x0A02 + 0x40*(n-1)   ->  0A02 0A42             n = 1,2
```

100% pure over 326,768 references. Bits 6–7 are inert for booleans (`0x0842` is a *bool*
reference, not int1 — the manifest lumps bool and int1 under type 4). Float constants
instead encode component count in the *length* field, which is why they walk up the pages:
`0900` (1), `1140` (2), `1980` (3), `21C0` (4).

**Compiler behaviour.** Common-subexpression elimination emits identical subexpressions
once, and sub-graph `instance` calls are inlined, so instruction counts can be far below
authored node counts. `length`, `normalize`, and `clamp` are not opcodes — they are lowered
(e.g. `normalize` → `dot`/`sqrt`/`div`).

---

## Decode correctly: walk records, do not scan

The instruction stream has no independent existence — every program is reached from a
record's bytecode slot. Scanning the body linearly and decoding whatever satisfies the
length rule is wrong: the rule admits any word in `0x0400–0x7FFF`, so roughly half of all
random data decodes as a plausible opcode. Over the same region, a flat scan reports
19.2M "instructions" and 24,776 distinct opcodes against a record-walk's 8.1M and 5,653.

Five opcodes once catalogued as unnamed operations — `0448`, `0A48`, `0A3D`, `1EB8`,
`0B19` — are **not instructions**. They are 16-bit halves of tags in the 8-byte array
structure, which a linear scan cuts across. Under a record-walk decode none of them ever
appears on an instruction boundary (0 of 12,869 occurrences); `0B19` is a record class
word (8,897 of its 8,931 hits are not in code at all). They are removed from the
catalogue: operation ids `0x08`, `0x19`, `0x38`, `0x3D` are not real operations.

---

## Operations

Grouped by family, by operation id within a family, and by type (float, int, bool) within
an id. Columns 1–4 give the opcode hex at component counts 1–4 (`·` = that width does not
occur). An opcode marked `*` falls below the catalogue threshold and is established
structurally — see the note under the table.

**Values and references**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `00` | `0900` | `1140` | `1980` | `21C0` | 4,877,193 | 20.08 | 417 | constant (immediate) |
| int | `00` | `0A00` | `1240` | · | · | 904,670 | 3.73 | 354 | constant (immediate) |
| bool | `00` | · | `0440` | · | · | 28,331 | 0.12 | 281 | constant (immediate) |
| float | `01` | `0501` | `0541` | · | · | 63,685 | 0.26 | 402 | read system variable (see below) |
| float | `02` | `0902` | `0942` | · | · | 11,066 | 0.05 | 288 | input reference (u32 uid) |
| int | `02` | `0A02` | `0A42` | · | · | 151,747 | 0.62 | 329 | input reference (u32 uid) |

**Variable slots**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `03` | `0503`\* | · | · | · | 3,603 | — | 34 | reads the cross-record CSE cache written by `0x06` |
| float | `04` | `0504` | `0544` | `0584` | `05C4` | 393,434 | 1.62 | 284 | get — read variable slot |
| int | `04` | `0604` | · | · | · | 96,487 | 0.40 | 288 | get — read variable slot |
| bool | `04` | · | `0444` | · | · | 12,755 | 0.05 | 81 | get — read variable slot |
| float | `07` | `0907` | `0947` | · | `09C7` | 1,451,585 | 5.98 | 319 | set — assign variable slot |
| int | `07` | `0A07` | · | · | · | 334,104 | 1.38 | 293 | set — assign variable slot |
| bool | `07` | · | `0847` | · | · | 55,811 | 0.23 | 232 | set — assign variable slot |

**Control flow and structure**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `09` | `0D09` | `0D49` | `0D89` | `0DC9` | 708,596 | 2.92 | 390 | select / ifelse — `select(c,a,b)` |
| int | `09` | `0E09` | · | · | · | 43,924 | 0.18 | 267 | select / ifelse |
| bool | `09` | · | `0C49` | · | · | 6,303 | 0.03 | 74 | select / ifelse |
| float | `0B` | `150B`\* | · | · | · | 542 | — | 20 | `while` — a loop, no immediate (see below) |
| float | `0C` | `090C` | `094C` | `098C` | `09CC` | 1,149,426 | 4.73 | 312 | sequence — chain statements |
| int | `0C` | `0A0C` | `0A4C` | · | · | 666,922 | 2.75 | 290 | sequence — chain statements |
| bool | `0C` | · | `084C` | · | · | 45,232 | 0.19 | 287 | sequence — chain statements |

**Vector construction and access**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `0D` | · | `094D` | `098D` | `09CD` | 1,831,842 | 7.54 | 418 | construct vector (concatenate; always 2 operands) |
| int | `0D` | · | `0A4D` | · | · | 5,354 | 0.02 | 171 | construct vector |
| float | `0F` | · | · | · | `11CF`\* | 28 | — | 6 | probably `vec4` — build a 4-vector from four scalars |
| float | `10` | `0910` | `0950` | `0990` | `09D0` | 1,276,159 | 5.25 | 408 | swizzle (packed 2-bit mask) |
| int | `10` | `0A10`\* | · | · | · | 179 | 0.00 | 17 | swizzle (packed 2-bit mask) |

**Type conversion**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `11` | `0511` | `0551` | · | · | 501,146 | 2.06 | 370 | type conversion (tofloat / toint) |
| int | `11` | `0611` | `0651` | · | · | 276,173 | 1.14 | 340 | type conversion (tofloat / toint) |

**Arithmetic**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `12` | `0912` | `0952` | `0992` | `09D2` | 1,343,142 | 5.53 | 408 | add |
| int | `12` | `0A12` | `0A52` | · | · | 686,458 | 2.83 | 332 | add |
| float | `13` | `0913` | `0953` | `0993` | · | 1,062,635 | 4.38 | 408 | sub |
| int | `13` | `0A13` | `0A53` | · | · | 143,611 | 0.59 | 296 | sub |
| float | `14` | `0914` | `0954` | `0994` | `09D4` | 1,575,012 | 6.49 | 419 | mul |
| int | `14` | `0A14` | · | · | · | 217,628 | 0.90 | 276 | mul |
| float | `15` | `0915` | `0955` | · | · | 515,162 | 2.12 | 403 | div |
| float | `16` | `0916` | `0956` | · | · | 26,476 | 0.11 | 336 | mod |
| int | `16` | `0A16` | · | · | · | 22,192 | 0.09 | 300 | mod |
| float | `17` | `0517` | · | · | · | 582,554 | 2.40 | 323 | neg |
| float | `18` | `0918` | `0958` | · | · | 31,624 | 0.13 | 213 | dot product |
| int | `18` | · | `0658` | · | · | 253 | 0.00 | 75 | dot product |

**Comparison**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| bool | `1D` | · | `085D` | · | · | 55,451 | 0.23 | 380 | eq |
| bool | `1E` | · | `085E`\* | · | · | 2,927 | — | 21 | `neq` |
| bool | `1F` | · | `085F` | · | · | 284,788 | 1.17 | 384 | gt |
| bool | `20` | · | `0860` | · | · | 74,169 | 0.31 | 349 | gteq |
| bool | `21` | · | `0861` | · | · | 79,974 | 0.33 | 327 | lr (less than) |
| bool | `22` | · | `0862` | · | · | 79,546 | 0.33 | 316 | lteq |

**Boolean logic**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| bool | `1A` | · | `085A` | · | · | 110,555 | 0.46 | 302 | and |
| bool | `1B` | · | `085B` | · | · | 16,974 | 0.07 | 285 | or |
| bool | `1C` | · | `045C` | · | · | 18,822 | 0.08 | 125 | not |

**Sign and rounding**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `23` | `0523` | `0563` | · | · | 388,736 | 1.60 | 360 | abs |
| float | `24` | `0524` | `0564` | · | · | 88,333 | 0.36 | 356 | floor |
| float | `25` | `0525` | · | · | · | 14,948 | 0.06 | 281 | ceil |

**Transcendental**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `26` | `0526` | · | · | · | 9,015 | 0.04 | 298 | cos |
| float | `27` | `0527` | · | · | · | 8,610 | 0.04 | 259 | sin |
| float | `28` | `0528` | · | · | · | 21,738 | 0.09 | 279 | sqrt |
| float | `29` | `0529` | · | · | · | 12,707 | 0.05 | 65 | ln |
| float | `2A` | `052A`\* | · | · | · | 3,733 | — | 45 | `exp` — 578/578 exact in `ie_processing` |
| float | `2B` | `052B` | `056B` | · | · | 723,550 | 2.98 | 341 | exp2 |
| float | `2D` | `052D` | · | · | · | 3,509 | 0.01 | 203 | atan2 |
| float | `35` | `0535`\* | · | · | · | 3,903 | — | 37 | `log2` — source-confirmed via `ie_pcloud` |
| float | `36` | `0936`\* | · | · | · | 53 | — | 8 | `pow(x, y)` — proved via sRGB closed form (see below) |

**Geometry and interpolation**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `2E` | · | `096E` | · | · | 58,351 | 0.24 | 281 | cartesian (polar → xy) |
| float | `2F` | `0D2F` | `0D6F` | · | · | 34,581 | 0.14 | 317 | lerp |

**Range and noise**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `30` | `0930` | `0970` | `09B0` | `09F0` | 243,200 | 1.00 | 378 | min |
| int | `30` | · | `0A70` | · | · | 13,204 | 0.05 | 104 | min |
| float | `31` | `0931` | `0971` | `09B1` | `09F1` | 342,759 | 1.41 | 378 | max |
| int | `31` | `0A31` | · | · | · | 981 | 0.00 | 62 | max |
| float | `32` | `0532` | · | · | · | 161,480 | 0.66 | 365 | rand (seeded) |

**Sampling**

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `33` | `0D33` | · | · | · | 87,974 | 0.36 | 177 | samplelum |
| float | `34` | · | · | · | `0DF4` | 249,327 | 1.03 | 78 | samplecol |

---

## Below the catalogue threshold (`*`)

The ≥20-specimen filter removes decode noise but also removes rare real instructions. The
eight opcodes marked `*` are established structurally, not by frequency, and their counts
come from a filter-free re-check rather than the catalogue pass. The `%` column is a share
of the catalogued total, which is measured without them, so it is left as `—` on those rows;
`0A10`, which the catalogue does carry, is counted at 181 instructions in 18 specimens by
that re-check against the 179/17 in its row.

`085E` sits in the width-2 column with the other bool comparisons, which is what its bits
6–7 declare; those bits are inert for booleans, so the width carries no meaning there.

---

## Notable operations

**System variables (`0x01`).** Read by immediate: 0 `$time`, 1 `$size`, 3 `$sizelog2`,
8 `$pos`, 10 `$number` (FX-Map only).

**`0x0B` = `while`.** A loop, carrying no immediate. Operands are `(init, cond, body, …)`:
position 1 is bool in 616/616 (the condition) and position 2 self-references in 56.5% of
instances (the accumulating body) against 0.4% for position 0 (the initialiser). Its
operands name *expression trees* re-evaluated per iteration, so a decoder emitting
instructions in linear order is wrong here — the one place straight-line translation fails.
The runtime batches all samples, so a correct implementation carries a per-lane `active`
mask and freezes a lane's writes and result (`select(active, new, old)`) once its condition
holds. Six forms: `194B`, `150B`, `190B`, `184B` (returns bool2), `15CB`, and `1A0B`
(returns int1 — one instance, in `TatamiSubstance001`, identified structurally rather than
by frequency: its operands are `seq` init, a **bool** `lt` condition, and a `set` body, the
exact signature the five commoner forms share).

**`0x0F` — probable `vec4`.** The only operation taking four operands and returning four
components; terminal in 28/28 instances, all in `levels` records, always the shape
`(x,x,x,1)` — a scalar broadcast to RGB with opaque alpha. Distinct from `0x0D` `vec`,
which always takes exactly two operands and would need three nested instructions to build a
4-vector. Marked probable: enough to fix the shape, not to rule out a `levels`-specific
reading.

**`0x0D` / `0x0F` width.** Both carry a declared `ncomp` that is authoritative over the
runtime widths of their operands. A transpiler must pass `ncomp` through to `vec` and
truncate, or a value that has drifted from its declared width can concatenate into
something wider than declared and silently break a downstream `add`.

**`0x36` = `pow` and `0x35` = `log2`.** Both proved against the inverse sRGB transfer
function `((s+0.055)/1.055)^2.4`, the same closed form used to confirm the `ln`/`exp2`
lowering. Transpiling `op36(x,y) = x**y` matches the closed form to max deviation
1.19e-07 (float32 rounding). A generic `exp2(ln(x)/ln2 · p)` lowering still exists and is
still emitted; which path a call compiles to is not established.
