# .sbsasm opcode catalogue

**41 distinct operations in 63 type-specific forms, all named.**
(Previously "45 in 68, 43 named". The five unnamed forms - `0B19`, `0A48`, `0448`, `0A3D`,
`1EB8` - were shown by direct test to be misread data, not instructions. See "The five
unnamed opcodes are not instructions" below.) (The catalogue table below
has one row per type-operation pair; its 67 rows have previously been quoted as an operation
count, which conflates the two. See "The operation-by-type matrix" in FORMAT-NOTES.) Measured over 382 distinct specimens (the corpus holds 579
`.sbsasm` files, 34% of them duplicate content) and 11,845,287 instructions decoded by
`isa_census.py`, which **scans** code regions run-by-run. An earlier version of this line
claimed the census walked records to their bytecode; it does not, and that mattered - the
scan is what produced the phantom opcodes recorded below.

96.5% of instructions carry an operation id catalogued for their type. No opcode
appearing in 20 or more distinct specimens has an uncatalogued operation id. The residual
is component-count and length variants of named operations, plus decode residue.

Two earlier figures are superseded and should not be quoted: "127 opcodes across 493
specimens, 24,285,805 instructions" counted a duplicated corpus with a flat scan, which
inflates the instruction count roughly 2x with misread record data; and "39 of 67
operations identified" predates the naming work.
## Opcode encoding

| bits | field |
|---|---|
| 15–10 | operand-token count — **instruction length = this + 1 tokens** |
| 9–8 | type: 0 bool, 1 float, 2 int — **value 3 is unused** |
| 7–6 | component count − 1 |
| 5–0 | operation id |

Three-address code: an opcode, then that many operand tokens, each a value number naming
an earlier result. Numbering is contiguous, one result per instruction.

Some operands are **immediates**, not value numbers: the swizzle mask (`0x10`), the
variable slot (`0x07`, `0x04`, `0x01`), and the `while` iteration cap (`0x0B`).

**Padding.** Opcodes carrying a 4-byte immediate — constants and references — come in two
forms differing by `0x0400`, one extra token, a 2-byte pad emitted when the instruction
lands at 0 mod 4 so the immediate stays aligned. The split is 100%/0% in the corpus.

**The compiler performs common-subexpression elimination.** Identical subexpressions are
emitted once, so instruction counts can be far below authored node counts — in
`ie_processing` 289 `dot` nodes collapse to a single instruction. Counting evidence is
unreliable for any node whose inputs repeat.

**Not instructions:** `pow`, `log2`, `length`, `normalize`, `clamp`, and any call. These
are lowered — `pow2` to `exp2(ln x · p)`, `normalize` to `dot`/`sqrt`/`div` — and
sub-graph `instance` calls are **inlined**, which is why a `.sbsar` can hold many times
more instructions than its `.sbs` has nodes.

## Operations

| type | id | 1 | 2 | 3 | 4 | instructions | % | files | meaning |
|---|---|---|---|---|---|---:|---:|---:|---|
| float | `00` | `0900` | `1140` | `1980` | `21C0` | 4,877,193 | 20.08 | 417 | constant (immediate) |
| float | `0D` | · | `094D` | `098D` | `09CD` | 1,831,842 | 7.54 | 418 | construct vector |
| float | `14` | `0914` | `0954` | `0994` | `09D4` | 1,575,012 | 6.49 | 419 | mul |
| float | `07` | `0907` | `0947` | · | `09C7` | 1,451,585 | 5.98 | 319 | set — assign variable slot |
| float | `12` | `0912` | `0952` | `0992` | `09D2` | 1,343,142 | 5.53 | 408 | add |
| float | `10` | `0910` | `0950` | `0990` | `09D0` | 1,276,159 | 5.25 | 408 | swizzle (packed 2-bit mask) |
| float | `0C` | `090C` | `094C` | `098C` | `09CC` | 1,149,426 | 4.73 | 312 | sequence — chain statements |
| float | `13` | `0913` | `0953` | `0993` | · | 1,062,635 | 4.38 | 408 | sub |
| int | `00` | `0A00` | `1240` | · | · | 904,670 | 3.73 | 354 | constant (immediate) |
| float | `2B` | `052B` | `056B` | · | · | 723,550 | 2.98 | 341 | exp2 |
| float | `09` | `0D09` | `0D49` | `0D89` | `0DC9` | 708,596 | 2.92 | 390 | ifelse / select(c,a,b) |
| int | `12` | `0A12` | `0A52` | · | · | 686,458 | 2.83 | 332 | add |
| int | `0C` | `0A0C` | `0A4C` | · | · | 666,922 | 2.75 | 290 | sequence — chain statements |
| float | `17` | `0517` | · | · | · | 582,554 | 2.40 | 323 | neg |
| float | `15` | `0915` | `0955` | · | · | 515,162 | 2.12 | 403 | div |
| float | `11` | `0511` | `0551` | · | · | 501,146 | 2.06 | 370 | type conversion (tofloat/toint) |
| float | `04` | `0504` | `0544` | `0584` | `05C4` | 393,434 | 1.62 | 284 | get — read variable slot |
| float | `23` | `0523` | `0563` | · | · | 388,736 | 1.60 | 360 | abs |
| float | `31` | `0931` | `0971` | `09B1` | `09F1` | 342,759 | 1.41 | 378 | max |
| int | `07` | `0A07` | · | · | · | 334,104 | 1.38 | 293 | set — assign variable slot |
| bool | `1F` | · | `085F` | · | · | 284,788 | 1.17 | 384 | gt |
| int | `11` | `0611` | `0651` | · | · | 276,173 | 1.14 | 340 | type conversion (tofloat/toint) |
| float | `34` | · | · | · | `0DF4` | 249,327 | 1.03 | 78 | samplecol |
| float | `30` | `0930` | `0970` | `09B0` | `09F0` | 243,200 | 1.00 | 378 | min |
| int | `14` | `0A14` | · | · | · | 217,628 | 0.90 | 276 | mul |
| float | `32` | `0532` | · | · | · | 161,480 | 0.66 | 365 | rand (seeded) |
| int | `02` | `0A02` | `0A42` | · | · | 151,747 | 0.62 | 329 | input reference (u32 uid) |
| int | `13` | `0A13` | `0A53` | · | · | 143,611 | 0.59 | 296 | sub |
| bool | `1A` | · | `085A` | · | · | 110,555 | 0.46 | 302 | and |
| int | `04` | `0604` | · | · | · | 96,487 | 0.40 | 288 | get — read variable slot |
| float | `24` | `0524` | `0564` | · | · | 88,333 | 0.36 | 356 | floor |
| float | `33` | `0D33` | · | · | · | 87,974 | 0.36 | 177 | samplelum |
| bool | `21` | · | `0861` | · | · | 79,974 | 0.33 | 327 | lr (less than) |
| bool | `22` | · | `0862` | · | · | 79,546 | 0.33 | 316 | lreq |
| bool | `20` | · | `0860` | · | · | 74,169 | 0.31 | 349 | gteq |
| float | `01` | `0501` | `0541` | · | · | 63,685 | 0.26 | 402 | read system variable ($pos) |
| float | `2E` | · | `096E` | · | · | 58,351 | 0.24 | 281 | cartesian (polar to xy) |
| bool | `07` | · | `0847` | · | · | 55,811 | 0.23 | 232 | set — assign variable slot |
| bool | `1D` | · | `085D` | · | · | 55,451 | 0.23 | 380 | eq |
| bool | `0C` | · | `084C` | · | · | 45,232 | 0.19 | 287 | sequence — chain statements |
| int | `09` | `0E09` | · | · | · | 43,924 | 0.18 | 267 | ifelse / select(c,a,b) |
| float | `2F` | `0D2F` | `0D6F` | · | · | 34,581 | 0.14 | 317 | lerp |
| float | `18` | `0918` | `0958` | · | · | 31,624 | 0.13 | 213 | dot product |
| bool | `00` | · | `0440` | · | · | 28,331 | 0.12 | 281 | constant (immediate) |
| float | `16` | `0916` | `0956` | · | · | 26,476 | 0.11 | 336 | mod |
| int | `16` | `0A16` | · | · | · | 22,192 | 0.09 | 300 | mod |
| float | `28` | `0528` | · | · | · | 21,738 | 0.09 | 279 | sqrt |
| bool | `1C` | · | `045C` | · | · | 18,822 | 0.08 | 125 | not |
| bool | `1B` | · | `085B` | · | · | 16,974 | 0.07 | 285 | or |
| float | `25` | `0525` | · | · | · | 14,948 | 0.06 | 281 | ceil |
| int | `30` | · | `0A70` | · | · | 13,204 | 0.05 | 104 | min |
| bool | `04` | · | `0444` | · | · | 12,755 | 0.05 | 81 | get — read variable slot |
| float | `29` | `0529` | · | · | · | 12,707 | 0.05 | 65 | ln |
| float | `02` | `0902` | `0942` | · | · | 11,066 | 0.05 | 288 | input reference (u32 uid) |
| float | `26` | `0526` | · | · | · | 9,015 | 0.04 | 298 |  cos |
| float | `27` | `0527` | · | · | · | 8,610 | 0.04 | 259 |  sin |
| bool | `09` | · | `0C49` | · | · | 6,303 | 0.03 | 74 | ifelse / select(c,a,b) |
| int | `0D` | · | `0A4D` | · | · | 5,354 | 0.02 | 171 | construct vector |
| float | `2D` | `052D` | · | · | · | 3,509 | 0.01 | 203 | atan2 |
| t3 | `19` | `0B19` | · | · | · | 1,358 | 0.01 | 108 |  |
| int | `08` | · | `0A48` | · | · | 1,215 | 0.01 | 58 |  |
| int | `31` | `0A31` | · | · | · | 981 | 0.00 | 62 | max |
| bool | `08` | · | `0448` | · | · | 835 | 0.00 | 172 |  |
| int | `18` | · | `0658` | · | · | 253 | 0.00 | 75 | dot product |
| int | `10` | `0A10` | · | · | · | 179 | 0.00 | 17 | swizzle (packed 2-bit mask) |
| int | `3D` | `0A3D` | · | · | · | 149 | 0.00 | 65 |  |
| int | `38` | · | · | `1EB8` | · | 95 | 0.00 | 51 |  |

## Confirmed below the catalogue threshold

The ≥50-specimen filter removes decode noise but also removes rare real instructions.
These are established structurally, not by frequency:

| opcode | type | comps | id | instructions | files | meaning |
|---|---|---:|---|---:|---:|---|
| `0A10` | int | 1 | `10` | 181 | 18 | integer swizzle (`iswizzle1`) |
| `052A` | float | 1 | `2A` | 3,733 | 45 | `exp` — 578/578 exact in `ie_processing` |
| `085E` | bool | 1 | `1E` | 2,927 | 21 | **`neq`** — deepest-embedded opcode tested (median containing run 21,102) |
| `0525` | float | 1 | `25` | 17,493 | 287 | `ceil` — 17/17 exact in `ie_processing` |
| `0503` | float | 1 | `03` | 3,603 | 34 | a distinct variable-access kind |


## Decoding correctly: walk records, do not scan

The instruction stream has no independent existence — every block is reachable from a
record's bytecode slot. Decoding by scanning the region linearly and decoding whatever
has a valid length is therefore wrong, and measurably so.

Comparing the two procedures over the same region in 120 specimens:

| | flat scan | record-walk |
|---|---:|---:|
| "instructions" | 19,192,507 | 8,127,795 |
| distinct opcodes | 24,776 | 5,653 |

The four opcodes catalogued as unnamed operations, plus `0B19`, behave exactly as the
structural account predicts — they are record headers and slot values read as code:

| opcode | flat scan | record-walk |
|---|---:|---:|
| `0B19` | 14,230 | **0** |
| `0A3D` | 1,013 | **0** |
| `0A48` | 692 | **0** |
| `0448` | 2,841 | 11 |
| `1EB8` | 409 | 5 |

Three vanish outright; the other two fall by 99.6% and 98.8%. 19,125 opcodes are visible
only to the flat scan, accounting for 1.85% of its instruction count — all of it noise.

## The operation set is complete

Under the correct procedure, over 13,532,669 instructions in 579 specimens:

```
operation id catalogued for its type : 96.926%
operation id catalogued for any type : 98.465%
```

and of the 95 opcodes that appear in 20 or more specimens — the threshold that separates
real operations from decode residue — **93 have a catalogued operation id**. The large
distinct-opcode count is not a set of unknown operations: the encoding is combinatorial,
so one operation appears as many opcodes across type, component count and length.
`0x0532` and `0x0524`, in 228 and 205 specimens, are `rand` and `floor` at component
count 1; `0x0861` and `0x085D` are `lr` and `eq` on 2-component bools.

### All five phantom opcodes traced to their source

Each of `0448`, `0A48`, `0B19`, `0A3D` and `1EB8` is a 16-bit half of a tag in the
self-referential 8-byte array structure documented in FORMAT-NOTES under "The array
entries". Measured across 56,470 array entries: `0448` appears as a tag half 405 times,
`0A48` 72, `0B19` 3, `0A3D` 2, `1EB8` 1.

They are not "decode residue" in the abstract — they are fragments of one specific
structure, which a linear scan of the body cuts across. Walking records to their bytecode
never enters it, which is why the record-walk decoder reports zero for three of them and
near-zero for the other two.

### The two candidates were artifacts — retracted

`0403` and `153F` were recorded here as genuinely new operations on the strength of
appearing in 28 and 25 specimens, above the 20-specimen threshold that separates real
operations from decode residue. Both are artifacts, and the threshold is what failed.

**They do not vary.** `153F` has **exactly one distinct operand tuple** across all 25
instances — `(1033, 768, 5376, 265, 1280)` — always preceded by the same `0403, 0400,
4400` sequence. A real operation names value numbers, which differ per block and per
file; an invariant tuple is a fixed byte pattern being read as code. `0403` has six
distinct tuples across 28 instances, which is barely better.

**The specimens are not independent.** 24 of 28 and 24 of 25 are `serverhouse__*` files,
and those are near-duplicates of one another — `BrickWall_02` and `BrickWall_02__66ca`
are the same material extracted twice. The effective specimen count is around a dozen
files from one source, not 25 independent observations.

The 20-specimen threshold assumes specimens are independent. This corpus contains
duplicate extractions of the same material, so **a file-count threshold must be applied
to deduplicated specimens**, and is worth pairing with an operand-variance check: a real
operation's operands vary, a misread structure's do not.

**With these two withdrawn, the operation set has no known gaps.** Of the 95 opcodes
appearing in 20 or more specimens, 93 carry a catalogued operation id and the other two
are the artifacts above.

### Re-measured on distinct specimens

Deduplicating the corpus by content hash (579 files, 382 distinct) and re-running the
record-walk decode:

```
instructions                         : 11,845,287
operation id catalogued for its type : 96.525%    (96.926% with duplicates)
opcodes in 20+ DISTINCT specimens    : 82         (95 with duplicates)
of those, uncatalogued operation id  : 0
```

**Deduplication alone removes both false candidates.** `0403` and `153F` do not reach 20
distinct specimens, because their apparent breadth came from repeated extractions of the
same `serverhouse__*` materials. No operand-variance check is needed once the input is
deduplicated — the threshold does its job again as soon as its independence assumption
holds.

The coverage rate is essentially unchanged, 96.9% to 96.5%, which is the expected
signature of duplicates: they inflate counts without shifting proportions.

**Current position.** 62 named operations, no opcode appearing in 20 or more distinct
specimens carries an uncatalogued operation id, and the residual 3.5% is component-count
and length variants of named operations plus decode residue.

## The last five

Four unnamed entries — `0448`, `0A48`, `0A3D`, `1EB8` — total 3,652 instructions out of
24,285,805 (0.015%). They are almost certainly not instructions.

A real operand names an earlier result in the same run, so it must not exceed the current
value number. Measured against that:

| opcode | status | operands in range |
|---|---|---:|
| `0900` | known-good | 53% |
| `094D` | known-good | 65% |
| `0914` | known-good | 66% |
| `0912` | known-good | 74% |
| `096E` | known-good | 87% |
| `0A12` | known-good | 90% |
| `0B19` | record class word | 52% |
| `1EB8` | unnamed | **7%** |
| `0448` | unnamed | **5%** |
| `0A3D` | unnamed | **9%** |
| `0A48` | unnamed | **2%** |

(The known-good figures fall short of 100% because the run tracker resets its value
counter on every decode failure, which undercounts. The separation is the point: 53-90%
against 2-9%.)

Their operands read like raw u16 data — `1EB8` takes `[16005, 1, 2626, 23844, 32194,
34818, 25]` — and they appear with no valid preceding instruction, where a real operation
sits in a decoded sequence. `0448` takes operand 1290 in a run whose value numbers are
single digits.

**Caveat on the test.** `0B19` scores 52%, indistinguishable from genuine operations, yet
is known from independent evidence to be a record class word. So this test cannot
establish that something is noise on its own — it is corroboration, not proof. For the
four at 2-9% it agrees with the operand-magnitude and context evidence.

**So the instruction set is, to the resolution the corpus supports, complete**: 62
operations, all named, covering 99.985% of decoded instructions, with the residue
attributable to record data being decoded as code.

## The five unnamed opcodes are not instructions

The section above inferred this from operand plausibility and called it "corroboration, not
proof". It can be proved directly, and now has been.

**Test 1 - do they ever appear in a program reached from a record?** Following every slot of
every record as a candidate program pointer, across all 382 distinct specimens, and accepting
every opcode the length rule admits (including type 3, which is normally rejected):

    opcode   scan census        record-walk census
    0448     835 in 172 files   0 occurrences
    0A3D     149 in  65 files   0
    0A48   1,215 in  58 files   1  (and that one has a forward operand reference)
    0B19   1,358 in 108 files   0
    1EB8      95 in  51 files   0

    control: 0900 const.f1  2,940,814     0914 mul.f1  1,037,185
             0A42 inputref  524,740       085F gt.b2     366,362

This walk is deliberately **over-permissive** - following every slot as a pointer decodes
30,038,253 instructions, 2.5x the catalogue's count, because false pointers get followed too.
Even so it never encounters four of the five. A permissive decoder that cannot find them is
stronger evidence than a strict one that cannot.

**Test 2 - where do the byte patterns actually sit?** Scanning every 2-byte position in 120
specimens and classifying each hit against the set of real instruction boundaries:

    opcode   on a real boundary   inside a program, misaligned   outside every program
    0448              0                     83                          1,452
    0A3D              0                    247                            786
    0A48              0                     65                            321
    0B19              0                     34                          8,897
    1EB8              0                    251                            733
    ----
    total             0                    680                         12,189

**Zero of 12,869 occurrences falls on an instruction boundary.** 680 sit inside a decoded
program at a misaligned offset - almost all of them within the 4-byte immediate of a constant
- and 12,189 sit outside any program at all, in record headers, pointer slots and the value
table. `0B19` is the extreme case and was already known to be a record class word: 8,897 of its
8,931 hits are not even in code.

The mechanism is the one this document already established for linear scanning: a scan that
starts mid-stream and jumps block to block loses alignment, and every 2-byte window it lands on
that happens to satisfy the length rule becomes a phantom instruction. The rule admits any word
in `0x0400`-`0x7FFF`, so roughly half of all random data decodes as a plausible opcode.

**Consequence.** Four operation ids - `0x08`, `0x19`, `0x38`, `0x3D` - come off the catalogue,
and with them the last unnamed entries. The instruction set is **41 operations in 63
type-specific forms, all named**. The prior claim of "three probably sampler-related" unnamed
opcodes is withdrawn; there was nothing there to name.
