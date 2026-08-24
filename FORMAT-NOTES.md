# .sbsar / .sbsasm format notes

Static analysis of freely-licensed specimens. Every claim below is reproducible with
the tools in this repository against the corpus described here. Claims are marked
**confirmed** (verified across independent specimens) or **open**.

## Provenance statement

This section is the auditable summary of what this work was and was not derived from.
The detail is scattered through the notebook below; this is the whole of it in one place.

### What was analysed

Freely distributed `.sbsar` archives - CC0 materials from ambientCG, and `.sbsar` and `.sbs`
files published by their authors on GitHub under MIT, CC0 and MPL licences. Analysing a
freely distributed file to achieve interoperability is the entire basis of this work.

### What was never used

* **Adobe's Substance engine, in any form.** No binary was run, disassembled or inspected.
  Nothing here was obtained by observing the engine's behaviour; every statement comes from
  reading distributed data files.
* **Adobe's bundled library `.sbs` sources.** Several material packs redistribute Adobe's
  standard-library sources alongside their own work. Those files would answer many of the
  open questions directly - they contain the definitions of the library graphs whose inlining
  breaks source-to-binary correspondence - and they were excluded.

### How the exclusion was enforced

Mechanically, on every source file, before any measurement: a file containing the string
`<author v="Allegorithmic"` was dropped in its entirety.

    paired sources                                       140
      excluded by the rule                                38
      permitted                                          102

The rule is deliberately **over-broad**. It excludes whole files rather than individual
graphs, so the 38 excluded files gave up **12 graphs that were the material author's own
work** along with the 39 Allegorithmic-authored ones. That cost was accepted rather than
write a finer-grained rule that could leak.

### What the exclusion cost, measured

The notebook records the price rather than hiding it, because a boundary that costs nothing
is not being enforced:

* **Filter id 11** (10,978 records, 1.7% of the format) cannot be named. Its structural
  profile matches `motionblur`, and every specimen in the corpus that uses `motionblur`
  carries an Allegorithmic graph.
* **Filter id 5** cannot be named. Its profile matches `svg`; the one source file using
  `svg` is excluded.
* **`passthrough` and `grayscaleconversion`** appear in 25-26 permitted sources each and are
  never count-exact, so neither can be identified.
* **FX-Map internals** remain undecoded, blocked on instance-free specimens.

### A boundary incident, disclosed

While investigating tag `0x12`, aggregate filter counts were read from two files that the
rule had excluded, before it was noticed that they were excluded. The observation was
**not used**: it was not promoted to an identification, and tag `0x12` is still recorded in
this document as unresolved - a legacy tag with five records, named on version evidence
alone. It is recorded here because a clean-room record that documents only its successes
is not evidence of anything.

### What a reader can verify independently

The exclusion predicate is one string match and can be re-run on any corpus. The tools in
this repository reproduce every quantitative claim from files a reader supplies themselves.
Where a conclusion rests on a specific specimen, that specimen is named.

## Held-out validation, and a provenance boundary

### Three unseen specimens

Three `.sbs` + `.sbsar` pairs added after the specification was written, and never used to
derive any part of it: `SBRustyTreadPlate` (v6, 4,508 records), `UHL3D-Stylized_Sand_with_
Rocks_01` (v6, 3,317) and `Wood_Planks` (v5, 666). Every documented rule applied without
adjustment:

| check | RustyTreadPlate | UHL3D Sand | Wood_Planks |
|---|---|---|---|
| magic, size, trailer invariants | pass | pass | pass |
| resource descriptors tile the segment | 2, exact | no segment | no segment |
| slot-1 bit 3 clear implies inherited resolution | 100% (2127/2135) | 100% (1668/1675) | 98% (429/438) |
| bytecode blocks reached by record-walk | 4,063 | 2,817 | 634 |
| instructions decoded | 234,119 | 115,469 | 38,257 |
| operation id catalogued for its type | **100.0%** | 99.9% | **100.0%** |

Opcode coverage is *higher* than the 96.5% measured on the corpus the catalogue was built
from, because these files use only operations already named. This is the first genuinely
out-of-sample test of the format description, and it holds.

### What was excluded, and why

The same delivery contained 215 `.sbs` files, of which **118 carry graphs authored by
Allegorithmic** — 106 distinct standard-library identifiers including `blur_hq`,
`blur_hq_grayscale`, `slope_blur_grayscale`, `histogram_scan`, `invert_grayscale`,
`switch`, `shape`, `clouds_1`, `cells_3` and `auto_levels`, complete with Adobe's own
labels, descriptions and icon data. Material-pack authors had bundled the library sources
their graphs depend on.

Those would resolve the inlining problem directly: 14 of the 22 library graphs that break
node-to-record correspondence are among them, which would unlock a large part of the
paired corpus for exactly the parameter-semantics questions that are currently stalled at
n = 12.

**They are not used here.** Everything in this document is derived from compiled `.sbsar`
files that are freely distributed, plus `.sbs` sources authored by the people who
distributed them. Deriving from Adobe's own source files — redistributed by a third party,
whatever that party's licence permitted — would change what this documentation is, from
interoperability analysis of a shipped binary format into something derived from the
vendor's protected source. The clean-room character is the property that makes it safe for
a project like Blender to use, and it is worth more than the questions it leaves open.

The three pairs above are unaffected: none of them contains an Allegorithmic-authored
graph.

## Corpus integrity: a third of the specimens are duplicates

Hashing every `.sbsasm` by content:

```
.sbsasm files found      : 579
distinct by content hash : 382
duplicate files          : 197  (34%)
```

Duplication is concentrated, and it is not random: `tiny/` is 61% duplicates (118 of
193), `pairs4/` 75% (42 of 56). Some content appears five times — `ie_processing`,
`ie_particles` and `LGML_concat_xy` each recur across `pairs*` directories under
different extraction names, and materials like `Portfolio__metal_002` were collected
twice from different repositories that both mirror them.

The canonical one-file-per-content list is written to `DISTINCT.txt` and should be the
input to any measurement that counts specimens.

### What this changes, and what it does not

**Rates are unaffected; counts were inflated.** Re-running the resource-descriptor result
on distinct specimens only:

| | with duplicates | distinct only |
|---|---:|---:|
| specimens with a segment | 117 | 100 |
| have resource descriptors | 106 | 93 |
| descriptors tile the segment exactly | 106 | **93** |
| tiling rate | 100% | **100%** |

The structural conclusions hold. What was overstated is the breadth of evidence behind
them — "106 specimens" was 93 independent ones.

**Where it mattered.** Any threshold of the form "appears in N or more specimens" treats
its inputs as independent observations, and this corpus violates that. That is precisely
how `0403` and `153F` were recorded as new operations: both cleared a 20-specimen bar
made up almost entirely of near-duplicate `serverhouse__*` files, which are the same
handful of materials extracted repeatedly. Deduplicating first would have rejected both
without needing the operand-variance check that eventually caught them.

**Standing rule.** Count specimens from `DISTINCT.txt`. For any claim resting on a
file-count threshold, also check that the operands or field values *vary* across those
files — invariance across supposedly independent specimens means they are not
independent, or the thing being counted is not what it appears to be.

## Corpus

**383 distinct specimens** validate against the full structural spec with **0 unexplained**
entries (an earlier figure of 493 counted duplicate extractions; see "Corpus integrity")
out of 10,021 (header, output array, descriptor array, footer and record directory all at
493/493). They come from ambientCG, GitHub `.sbs`/`.sbsar` pairs, and a trawl for small
files described below. The original description of the 58-specimen set follows.

58 specimens, all **CC0 / public domain**, from
[ambientCG](https://ambientcg.com/list?type=Substance), spanning release dates
2018-03 to 2026-06. ambientCG publishes 100 such files; a corpus drawn from it can be
redistributed inside a test suite with no licensing concerns.

Size range 90 KB – 21 MB of `.sbsasm` payload. `validate_corpus.py` re-derives every
claim below across the whole corpus and exits non-zero on any contradiction.

### Ground-truth pairs — .sbs sources with matching .sbsar

Publicly on GitHub there are repositories shipping a **`.sbs` source graph alongside its
compiled `.sbsar`**, which gives ground truth for the compiled form without needing a
Substance Designer licence. `.sbs` is plain XML with a documented schema: `<compNode>`
per node, each with `<uid>`, a `<GUILayout><gpos>` canvas position, and a
`<compImplementation>` naming the node type (`<compInstance><path>` for instances,
`<compFilter><filter>` for built-ins).

**101 matched pairs** were located across 15 repositories by searching GitHub code for
distinctive `.sbs` tokens (`compNode`, `graphOutputs`, `outputBridging`, `compFilter`,
`paraminputs`) to find candidate repos, then diffing each repo's tree for basenames
carrying both extensions. After discarding Git-LFS stubs and oversized files, 95 were
downloaded and **57 verify as genuinely in sync** — the `.sbs` graph identifier matches
the `.sbsar` manifest's graph label, so source and binary describe the same graph.

Richest sources: `logicalmodelin/LGMLtools` (24 pairs), `pmpu/serverhouse` (18),
`grondag/Hard-Science-Old` (13), `distantlightgames/DLG-Tools` (13),
`Synthoid/substance-for-unity-extensions` (6). Graph sizes reach 571 nodes.

These are the substrate for attacking the record stream: known node count, node types,
uids and connectivity against a compiled binary, with no Designer licence needed.

**Tooling caveat — resolved.** libarchive rejects a substantial minority of `.sbsar`
as "Damaged 7-Zip archive" (23 of the harvested set). The archives are **not damaged**:
`py7zr` reads every one of them without error. Affected files carry a 7z header version
`0.3` where libarchive-readable ones carry `0.4`. Use `py7zr` or the 7-Zip CLI; `bsdtar`
silently loses roughly an eighth of any corpus.

### External validation

The full specimen set is now **125 single-graph packages from three independent
sources** — 58 CC0 assets from ambientCG plus 67 from unrelated GitHub repositories.
All validate with **zero unexplained entries**:

```
168 single-graph packages (13 multi-graph excluded as unsupported)
3223 value-table entries: 3176 byte-exact (98%), 47 %g-rounded, 0 unexplained
(n_out, n_in) header     : 168/168
output uid array         : 168/168
input descriptor array   : 168/168
trailing array footer    : 168/168
```

The GitHub set reaching 100% byte-exact is expected: those authors saved values that
survive `%g` rendering, whereas ambientCG's colour-heavy materials do not.

## Container (.sbsar) — confirmed

Plain 7-zip archive, magic `37 7A BC AF 27 1C`, extractable with libarchive
(`bsdtar -xf`). Layout, identical in all 58:

```
assemblies/content/0000/<name>.sbsasm     compiled graph
assemblies/content/0000/<name>.xml        manifest: inputs, outputs, GUI, presets
assemblies/content/0000/thumbnail.png     icon
```

The XML manifest has a published DTD reference (`sbsdescription.dtd`) and is trivially
parsed. All 58 specimens declare `formatversion="2.1"` and contain exactly one graph.
This is the layer every existing tool reads; it carries no graph topology.

## .sbsasm header — confirmed

Identical field layout in all 58 specimens. Little-endian throughout.

```
offset  size  interpretation
------  ----  ----------------------------------------------------------
0x00    4     magic "SBAM"
0x04    4     assembly format version -- NOT constant, see below
0x08    8     per-file uid
0x10    4     total file size (exact match in all 58)
0x14    4     0x1C           constant across corpus
0x18    4     0              constant
0x1C    4     size-28        pointer -> trailer
0x20    4     0x00010002     constant
0x24    4     0              constant
0x28    4     1              constant
0x2C    4     default-table end minus 52 (see Locating the table)
0x30    4     2              constant
0x34    4     0              constant
0x38          body begins
```

### Field 0x04 is an assembly version — confirmed, three values

Three values occur. **It does not track the asset's release date**, and an earlier draft
of these notes wrongly claimed it did — that apparent correlation was an artefact of a
17-file sample.

**Seven values are known**: `0x00020000`, `0x00030000`, `0x00040000`, `0x00050000`,
`0x00060000`, `0x00080000`, `0x00090000`. Only v5, v6 and v9 occur in the ambientCG
catalogue; the other four appear exclusively in the GitHub pairs. Within ambientCG the
date ranges are v5 2018-03..2024-08 (35), v6 2020-01..2023-12 (12), v9 2024-01..2026-06
(11) — v5 and v6 interleave freely, so the field reflects **which cooker version the
author published with**, not release date. An early draft claimed a clean chronological
split from a 17-file sample; that was wrong, and the wider corpus shows why one
publisher's catalogue is not a representative sample.

v5 and v6 interleave freely across 2020–2024, and a v5 file (RustSubstance002, 2024-08)
postdates several v9 files. The field therefore reflects **which cooker version the
author happened to publish with**, not when the asset was released. The only clean
boundary is a lower bound: no v9 specimen predates 2024-01.

This matters because the version **changes the table encoding** — see the image-input
row in the width table. It is independent of the manifest's `formatversion`, which is
`2.1` in all 58. The `cookerbuild` attribute varies per file and looks like a hash, not
an ordered build number.

## File segmentation — confirmed

The `base` value that positions the record directory is not an arbitrary offset: it is
the **size of an embedded resource segment** that sits between the file header and the
code region.

```
0x00           file header (0x38 bytes)
0x38           embedded resource data  ]  size == base
base + 0x38    record directory        ]
               records                 ]  code region
               interface block         ]
size - 28      trailer
```

Evidence, from the 64 in-sync pairs where the source graph is known:

| | mean `bitmap` filter nodes | mean `<resource>` entries |
|---|---|---|
| **base != 0** (35 pairs) | 1.51 | 1.80 |
| **base == 0** (29 pairs) | 0.03 | 0.10 |

A near-total separation: packages that embed images have a non-zero base, packages that
do not have `base == 0`. Correlation of base against `<resource>` count is 0.689.

Segment sizes match image payloads — 6 bitmaps to 20 MiB, 6 to 18 MiB, 7 to 17 MiB,
roughly 3 MiB apiece (1024x1024 RGB). And the bytes at `base` read as pixel data in every
sample inspected: `96 84 7d 00 9d 8e 88 00` (RGBX with zero alpha), `80 80 80 81 81 81`
(values centred on 128, a normal map), `86 8f ed 3e` (float32 ≈ 0.46).

This explains several things at once: why the directory is often not at `0x38` (the
resource segment displaces it), why such files are large, why the directory covers only
1–19% of them while `base == 0` files reach ~98%, and why record count tracks file size
so loosely — in image-bearing packages the bulk of the file is not code at all.

## The embedded images decode — confirmed

The resource segment holds **uncompressed raster data**, and it can be extracted and
rendered. `extract_images.py` does this.

### Worked example

`Metal_Vent_006` has a 18,874,368-byte segment and declares six `<resource>` entries.

```
18,874,368 = 6 x (1024 x 1024 x 3)
```

An exact tiling by six 1024x1024 RGB8 images. Extracting and rendering them yields clean,
artefact-free textures — a galvanised metal vent, pixel-perfect, no shear or offset. The
per-image mean colours identify the maps without any further work:

| image | mean RGB | reading |
|---|---|---|
| 2 | (127, 134, 248) | **normal map** — canonical mean is (128,128,255) |
| 1 | (87, 92, 98) | base colour |
| 0, 3, 4, 5 | R=G=B | grayscale: height / roughness / masks |

### The pixel format is stored — resource table

The format does not have to be inferred. Immediately before the interface block sits a
**resource table**: one 8-byte record per embedded image.

```
u32 format_tag
u32 offset      byte offset of the image within the segment (+4)
```

The tag decodes as four little-endian bytes:

| byte | meaning |
|---|---|
| `[3]` | format: `0x01`=L, `0x02`=RGB, `0x03`=RGBA, `0x05`=L16, `0x07`=RGBA16 |
| `[2]` | channel depth: `0x08` = 8-bit, `0x18` = 16-bit |
| `[1]` | **NOT a marker** — this is `log2 height << 4 | log2 width`; `0xAA` means 1024x1024. Treating it as a constant marker hid every resource of another resolution. See "The record type's high byte is the output resolution" |
| `[0]` | `0x20` = grayscale, `0x21` = colour |

The three fields are mutually consistent: bytes-per-pixel always equals channels x
bytes-per-channel (L8=1, L16=2, RGB8=3, RGBA8=4, RGBA16=8), and byte `[0]` agrees with
the channel count implied by byte `[3]` in every record observed.

**Record spacing is not constant.** Records sit 8 bytes apart in some files and 32 in
others, so the table must be found by scanning the region for valid tags rather than
walked at a fixed stride. Assuming contiguity truncates the table to a single record and
silently reports one giant image — that error hid three quarters of the images here, and
was only caught because the resulting sizes did not factor into square dimensions.

Consecutive offsets give each image's size, the last running to the end of the segment.
**In all 36 specimens where the table is located, these sizes sum to the segment length
exactly** — a strong check, since a single misparsed record would break the total.

Corpus result with stride-agnostic scanning:

```
resource segments        102
  table located           36
  sizes sum to segment    36 / 36
  images described       200
  dimensions resolved    190 / 200  (95%)
```

Formats observed: L8 (87), L16 (39), RGB8 (37), RGBA16 (21), RGBA8 (16). Dimensions are
`1024x1024` in 189 of 190 cases, `1280x1280` in one. Files carry 1 to 8 images, most
commonly 6 to 8.

Worked cases: `Metal_Vent_006` is six RGB8 images; `celtic_orna_mossy_001` is six images
of *mixed* format — L16, RGB8, RGBA16, L8, RGBA8, L16 — whose sizes still total the
segment exactly, and which render cleanly when each is decoded per its own tag.

**Superseded — byte 1 is not a marker.** (Historical note; it encodes resolution.) Matching on `0xAA` alone finds 77
"tables", but many are float bit patterns: they yield impossible format codes such as
`0x00`, `0x3E` and `0x3F`. Requiring a known format, a known depth and a valid colour
flag drops the count to 34 — all of which check out.

### The full resource record — two embedded structures, not eight fields

An earlier draft described the 32-byte record as eight `u32` fields (a constant `0x3F`, a
`2 x index`, a pointer, a per-file constant, ...). **That was a mis-parse.** Read as
`u16` tokens the record resolves into a prefix plus two concatenated structures:

```
[ u32 format_tag ][ u32 offset ]        8 bytes
[ 0x88xx load record, 9 tokens ]       18 bytes
[ 0x0A42 reference, 3 tokens   ]        6 bytes
                                       32 bytes  <- this is why the stride is 32
```

Verified on **157 of 157** records across 23 files: byte 8 always holds an `0x88xx`
opcode, byte 26 always holds a reference opcode, and that reference's `u32` immediate is
**always an input uid** (157/157) — not the "per-file constant" the field reading
suggested. The values that looked like a constant `0x3F`, a `2 x index` and a pointer are
operand tokens belonging to the 9-token load record.

The embedded `0x88xx` record ties the resource table to the wider format. Its opcode
discriminates channel layout exactly:

```
0x8804  <->  grayscale   (L8 x82, L16 x29)     111 records
0x8805  <->  colour      (RGB8 x15, RGBA8 x13, RGBA16 x18)   46 records
```

No exceptions in 157 records. Its high half-word carries the depth: `0x0309` for 8-bit,
`0x0319` for 16-bit, agreeing with the tag's depth byte in 144 of 157 records.

So the pixel format is stored **twice** — once in the tag and once in the instruction
that loads the image — which is why the tag decode could be confirmed without guessing.

### Using the resource metadata against the instruction set

The resource record embeds a real instruction (word 2), and we independently know what
that image is. That yields the **first opcodes with known semantics** rather than merely
known lengths and operand types:

```
0x8804  =  load image, grayscale   (confirmed against L8 and L16 resources, 111 records)
0x8805  =  load image, colour      (confirmed against RGB8/RGBA8/RGBA16, 46 records)
```

It also confirms a general encoding principle: the **high half-word of an instruction
carries a mode or type**. Here it is channel depth — `0x0309` for 8-bit, `0x0319` for
16-bit — agreeing with the resource tag's own depth byte in 144 of 157 records.

Three follow-on attacks were tried; two failed and are recorded so they are not repeated:

- **Image loads as a second anchor family.** In principle a second, independent anchor
  type tightens the length-learning constraints. In practice the corpus yields only
  **6 image-load anchors against 98,873 reference anchors** in the size range where the
  learner runs, because most files with substantial code carry no embedded images. Decode
  rate was unchanged (23.7% either way).
- **Matching code-region load counts to the resource table.** Files showed a strikingly
  consistent shortfall — 8 images give 6 load opcodes, 7 give 5, always `N-2`. **Resolved:
  it was an artefact of my own region bounds, not a property of the format.** The
  resource table lies *inside* the span `[first directory entry, last directory entry]`
  that I was calling the code region, so the "load instructions" being counted were
  literally word 2 of each resource record. The last two records fall beyond the final
  directory entry and were therefore excluded — hence `N-2`, every time. Verified: in
  27 of 29 image-bearing files, the number of loads found equals exactly the number of
  record word-2 fields inside the scanned window.

  Two consequences worth carrying forward. First, **the resource table sits within the
  directory's span**, so any analysis bounded by `ents[0]..ents[-1]` includes it.
  `code_region.py` returns the span with the table excised; every opcode analysis in
  these notes was re-run against it, with these results:

  ```
  bytes counted as code   before 150,552,632   after 149,377,716   removed 0.78%
  files affected          32 of 222

  reference opcodes at off%4==2      175,858 / 176,227  (99.8%)
  ...followed by an input uid        175,651 / 175,858  (99.9%)
  0x0900  P(next is f32)             0.999
  0x1140  P(next is f32)             1.000
  0x21C0  P(nonzero f32)             0.021   (still correctly rejected)
  0x1240  P(nonzero f32)             0.000   (still correctly rejected)

  length learning, identical schedule:
    old bounds  38 opcodes  23399/98783 decoded (23.7%)
    new bounds  38 opcodes  23399/98783 decoded (23.7%)   -- byte-identical
  ```

  **No conclusion changes.** All 34 opcode lengths shared between runs are identical, and
  the learner produces byte-identical output. The reason is that the 32 affected files are
  precisely the image-heavy ones with almost no code, so they contribute few or no anchors
  and never entered the opcode statistics. The bug was real and produced a real artefact
  (the `N-2` mystery), but it never touched the instruction-set findings. Second, files with substantial graphs *do* contain genuine image-load opcodes in
  code (GrassSubstance001 has 577, PavingStonesSubstance002 has 155), so the opcode is
  not confined to the metadata region; the small-file cases simply had almost no code.

  Directory entries do **not** point at resource records (0 of N in every file checked),
  so the directory spans the table without indexing it.
- **Re-testing for an indexed output-store instruction.** The earlier negative result
  was obtained under the wrong 4-byte framing and had to be redone in `u16`. It still
  finds nothing: across 106 specimens with 3-12 outputs, no opcode occurs exactly
  `n_out` times with operands covering `0..n_out-1`. Whatever writes an output does not
  index it by position in an operand.

So the metadata layer meaningfully advances the instruction set — two opcodes now have
meanings, and the mode-field convention is established — but it does not unlock the
stream wholesale.

### Graph correlation: associating opcodes with filter types

The 46 in-sync pairs that carry both source and code allow a different attack: correlate
which **built-in filter types** a source graph uses against which **opcodes** appear in
its compiled stream. Opcode histograms are built from tokens at `off % 4 == 2`, the
position parity established for opcodes, over the corrected code region.

Most opcodes correlate with nothing, because most are ubiquitous — `0x0A42` appears in
all 46 files, so every "filter implies `0x0A42`" statement is trivially true and
worthless. Two guards are needed: exclude float bit patterns from the candidate pool
(use only verified opcodes), and discard associations where the opcode is near-universal.

**One association survives clearly: `0x0398` tracks spatial-neighbourhood filters.**

| filter set | phi | present with | present without |
|---|---|---|---|
| warp, directionalwarp, emboss, sharpen | **0.823** | 24 / 26 | 2 / 20 |
| + blur, dirmotionblur | 0.734 | 24 / 28 | 2 / 18 |
| blur, dirmotionblur alone | 0.489 | 18 / 22 | 8 / 24 |

Rate per 1000 opcode positions: **median 2.96 with displacement filters, median 0.000
without** (mean 0.111). The opcode is essentially absent from graphs that do no
neighbourhood sampling.

The four filters it tracks — warp, directional warp, emboss, sharpen — all read pixels at
an *offset* from the current position. Blur alone associates far more weakly, which
argues the operation is specifically offset sampling rather than neighbourhood averaging.
`0x0399` and `0x0119` follow the same pattern at phi 0.70 and are presumably companions
in the same emitted sequence.

**Variant pairs.** `0x0398`/`0x0399` differ in one bit and behave like variants: 26 files
contain both, 5 contain only the odd member, and **none contain only the even member**.
Their counts move independently within a file (118/88, 48/17, 1/23), so they are distinct
operations rather than one instruction miscounted. `0x0118`/`0x0119` behave identically.
This mirrors `0x8804`/`0x8805`, where the low bit is known to select grayscale versus
colour. The pattern is not universal, though — `0x0903` barely occurs while `0x0902` is
common, so low-bit pairing cannot be assumed.

**What this method cannot do.** Correlation shows co-occurrence, not emission. It cannot
separate "this filter emits this opcode" from "graphs using this filter also use
something else that does". With 46 pairs and instanced sub-graphs contaminating every
count, `0x0398` should be read as *belonging to the offset-sampling functional class*,
not as a proven single operation.

### What the metadata does NOT record

**There is no semantic role.** Nothing in the record says an image is a base colour, a
normal map, a roughness map or a height map. The `.sbs` source names them explicitly
(`Metal_Vent_006_basecolor`, `_normal`, `_roughness`, ...) but those identifiers and
their uids are **absent from the compiled file** — 0 of 6 resource uids appear anywhere
in `Metal_Vent_006`, and the resource region contains no identifier-like text in any
specimen. The role exists only in how the graph consumes the image.

What the metadata *does* discriminate is the **pixel type**: channel count, channel
depth, and grayscale-versus-colour, each recorded redundantly and consistently.

**Dimensions are not stored.** They follow from `size / bytes-per-pixel` assuming a
square image. That resolves 190 of 200 images and matches rendered output in every case
checked.

### Not every pre-directory region is an image set

An earlier draft claimed `base != 0` implies embedded bitmaps. That is too strong.
**66 of 102 segments carry no resource table at all** — and not because the table is
hidden elsewhere: scanning those entire files finds zero valid tags.

Their content varies. Some are mostly zeros (Metal009: 74%). Others hold float32 raster
data — `BricksSubstance004`'s midpoint reads `f2 2a ed 3e | 92 be eb 3e | 58 95 ea 3e`,
i.e. 0.4632, 0.4604, 0.4582, a smooth gradient in 32-bit floats. No format code in the
tag vocabulary corresponds to f32, so either these use codes absent from the tagged
files, or they are not table-described resources at all. **Undetermined.**
**[NARROWED: they contain zero records (0 of 3,042 in BricksSubstance004), are 100% f32
in [0,1], and admit no exact power-of-two tiling at any alignment — so they are several
concatenated float32 resources, not record data and not one image. See "The table-less
resource segments are not record data".]**

The reliable discriminator is therefore the presence of a resource table, not `base != 0`.

### Recovering dimensions without metadata (superseded)

Row stride is found by autocorrelating the **high-pass** (first-difference) byte signal.
Raw autocorrelation is useless here — texture data is smooth, so it scores 0.97+ at every
lag. Differencing suppresses the low-frequency content and leaves a clean peak at the row
stride, with harmonics at multiples.

Given a stride, candidate `(width, height, bpp)` triples are those that tile the segment
exactly with a power-of-two width. Across the corpus, **45 of 102 resource segments
resolve to an exact tiling**.

### Two traps

**Sub-row peaks.** The strongest autocorrelation peak is often not the row stride — small
lags such as 64 come from block structure inside the image and produce absurd readings
(`st_wood_fine_20` as 4352 images of 64x64). Candidates must be scored for plausibility:
a texture set is a handful of square-ish, power-of-two images, not thousands of tiny ones.

**Superseded by the resource table above — kept as a record of what pixel-only
inference could and could not do.** Exact fit does not determine the pixel format. 18,874,368 is tiled exactly by both
`6 x 1024x1024 RGB8` and `9 x 2048x1024 L8`. Arithmetic cannot choose between them; only
the rendered result can. Reading grayscale data as RGB produces a recognisable image with
**colour speckle** from channel misalignment — that fringing is the discriminator, and
`pix_concrete_01` is a worked case where the grayscale reading is clean and the RGB one is
not.

Some segments also begin with a run of padding (`0xFF` or zero) before the pixel data, so
the first image does not always start at `0x38`.

## Record directory — confirmed (entries carry the +52 skew) — and there is no "alternate layout"

The body opens with a directory of strictly increasing absolute file offsets. Its
location is **named by the footer** (see the interface block below), not fixed:

```
base    = dir_ref - 4                 # dir_ref is the footer's second word
dir_at  = base + 0x38
entries = count                       # the footer's first word, u32 offsets
```

Verified over the full directory length in **182 of 182** specimens: entries are
strictly increasing, all lie inside the file, and all fall below the interface block.
Directory sizes run from 2 to 39,627 entries, median 1225.

**This retracts the "alternate body layout" reported in earlier drafts.** There is no
second layout. Those specimens simply have `base != 0` — meaning a resource segment
occupies `0x38 .. base+0x38` — so `0x38` holds embedded pixel data and a reader that
assumes the directory starts there sees garbage. In this corpus
**81 of 182 specimens have a non-zero base** — including 17 that an at-0x38 heuristic
scores as plausible-looking, which is worse than an obvious failure. Observed bases are
large round numbers (`0x8000`, `0x20000`, `0x40000`, `0x480000`, `0x1200000`, ...);
alignment is not uniform enough to assume a fixed granularity.

The directory does not generally abut its records — the first entry precedes the
directory's own end in most specimens — so it indexes a region rather than immediately
preceding it.

All 219 specimens validate. Three that initially failed carry a single-entry directory
(`count == 1`), which a strictly-increasing check trivially rejects for having no pair to
compare — a validator artifact, not a format anomaly.

### Node-type regression — tested, does not work

If records corresponded to nodes in any additive way, record count should be predictable
from the source graph's node-type mix. Tested across the **64 in-sync `.sbs`/`.sbsar`
pairs**, with node-type counts (per built-in filter, per instanced sub-graph, plus input
and output bridges) as features and record-directory size as the target:

| model | R² |
|---|---|
| baseline: total node count only | 0.170 |
| unconstrained least squares, 22 features | 0.339 |
| non-negative least squares (physically meaningful coefficients) | 0.272 |
| **non-negative, leave-one-out cross-validated** | **−0.318** |

A negative cross-validated R² means the model predicts **worse than the mean** — no
predictive power at all. Median absolute CV error is 168 records against a median target
of 135. Unconstrained fitting produced physically impossible coefficients (negative
records per node), the classic signature of an unidentified model.

**The mechanism is clear from the correlations:**

```
corr(records, instanced sub-graph nodes) = 0.718
corr(records, total nodes)               = 0.412
corr(records, built-in filter nodes)     = 0.203
```

Record count tracks **instanced sub-graphs**, not the graph's own filter nodes. A
`compInstance` expands at cook time into the full contents of a referenced package that
is *not present in the `.sbs`* — so its record cost is unbounded, varies with the library
version the author had installed, and is unknowable from the source graph. Restricting
to the 11 instance-free pairs does not rescue the fit; those graphs are trivial.

This closes the last approach that avoided a differential corpus. Authoring-level
structure cannot predict cooked structure, because the dominant term lives outside the
authoring file.

## Inside the record stream: input references — confirmed

Input uids and output uids behave completely differently in the code region, and chasing
that asymmetry yields the first instruction-level structure recovered from the stream.

### The asymmetry is real

Counting occurrences **outside** the interface block, across 149 specimens:

| | distinct | occurrences | per uid |
|---|---|---|---|
| input uids | 5571 | 188,061 | **33.8** |
| output uids | 937 | **0** | 0.0 |
| random control, same numeric range | 5571 | **0** | 0.0 |

The random control is the important row: values drawn from the same magnitude range as
real uids appear zero times, so the input hits are not 4-byte collisions. 99.7% of them
are 4-byte aligned.

### SOLVED: the reference opcode encodes the operand type

`Synthoid/substance-for-unity-extensions` ships a suite of unit-test substances, each
built to exercise **one input type**: `ColorTest` (a float4), `FloatTest` (a float1),
`BoolTest` (an int1), and `ImportTest` (whose inputs are exactly the union of the first
two). At 288-400 bytes they are an authored differential corpus in public form — the
thing these notes previously said would require a Designer licence.

Comparing them showed `rough` (float1) referenced by `0x0902` while `toggle` (int1) used
`0x0842`. Checking that across the whole corpus gives a **completely clean mapping**:

| opcode | operand type | occurrences | purity |
|---|---|---|---|
| `0x0902` | float1 | 10,528 | 100% |
| `0x0942` | float2 | 7,283 | 100% |
| `0x0982` | float3 | 879 | 100% |
| `0x09C2` | float4 | 295 | 100% |
| `0x0A02` | int1 | 54,242 | 100% |
| `0x0A42` | int2 | 253,011 | 100% |
| `0x0842` | int1 | 911 | 100% |

**326,768 references, every opcode mapping to exactly one type with no exceptions.**

The structure is arithmetic: **bits 6-7 of the opcode hold the component count minus 1.**

```
float family   0x0902 + 0x40*(n-1)    ->  0x0902 0x0942 0x0982 0x09C2   n = 1..4
int family     0x0A02 + 0x40*(n-1)    ->  0x0A02 0x0A42                 n = 1,2
```

`0x09C2` was **predicted from the pattern before being tested** — the corpus scan that
produced the first six opcodes never included it — and it verifies at 100% of 295
occurrences.

**This unifies the `+0xC0` result.** The grayscale/colour substitution found in the
radial-blur pair (`0x0907` -> `0x09C7`, `0x090C` -> `0x09CC`, ...) is `+0x40 * 3`: one
component becoming four. Bits 6-7 are not a colour flag, they are a component count, and
grayscale-versus-colour is simply the 1-versus-4 case of it.

`0x0842` is the exception: it maps to int1 while its bits 6-7 read as 1, so the `0x08xx`
base does not follow the same convention. Unexplained.
**[RESOLVED — it is a *bool* reference, not int1; the manifest lumps bool and int1 under
type 4 while the ISA distinguishes them. Bits 7-6 are inert for booleans. See
"`0x0842` is not an exception".]**

### Inputs are referenced by uid; the encoding is (u16 arg, u16 opcode)

Input uids appear as **4-byte immediates following a reference instruction**. The word
before a uid is overwhelmingly stable in its *upper* half-word, which identifies the
opcode position:

| opcode (high u16 of the preceding word) | share of input-uid occurrences |
|---|---|
| `0x0A42` | 73.0% |
| `0x0A02` | 15.7% |
| `0x0902`, `0x0942`, `0x0982`, `0x0842` | ~5% |
| cumulative | **99%** |

The low half-word varies (`0x0001`, `0x0003`, `0x0044`, `0x0046`, ...) and is the
instruction's argument. So instructions are little-endian **`(u16 arg, u16 opcode)`**
words, with the opcode in the high half — and a reference instruction is followed by a
`u32` input uid immediate.

**94% of all input-uid occurrences (158,240 of 168,008) are immediately preceded by an
opcode from this family.** A second form, `0x0D02`, is followed by an input uid in 1282
of 1307 cases (98%).

### Outputs are positional, not referenced

Output uids occur **zero** times in the code region across every specimen tested. Outputs
are identified solely by their index in the interface block's output-uid array. That is
the whole asymmetry: a parameter can be read from arbitrarily many sites so it needs a
name, whereas an output is a fixed slot the graph writes to and needs only a position.

Reference count per input correlates only weakly with the number of outputs that input
alters (r = 0.291 over 2267 inputs), which is expected — the count reflects how many
places read the parameter, not how far its influence propagates.

### CORRECTION: the stream is a u16 token stream, not 4-byte words

Earlier drafts of these notes described instructions as little-endian **`(u16 arg, u16
opcode)`** words. **That framing is wrong**, and the error is a half-word shift.

Measured over every confirmed reference instruction in the corpus:

```
reference opcode tokens found          108,911
followed within 4 bytes by an input uid 108,580
  ...at an offset where off % 4 == 2    108,580   (100%)
  ...at an offset where off % 4 == 0          0
```

The opcode token **never** lands on a 4-byte boundary. It always sits at `off % 4 == 2`,
with its `u32` immediate on the following 4-byte boundary. So the code is a stream of
**`u16` tokens** — `[opcode][operands...]` — and a 4-byte reading pairs each opcode with
the *trailing operand of the previous instruction*. That is exactly why the opcode always
appeared in the "high half": it was the second `u16` of a misframed word.

**What this invalidates:** the "arg field" attributed to each opcode in earlier drafts.
Those values belong to the preceding instruction, so the bimodal wide/narrow arg analysis
described nothing real about the opcode it was attached to. The opcode *identities* and
their immediate types are unaffected — those were derived from what follows an opcode,
which the shift does not disturb.

**What this reveals:** the `u16` view is far better conditioned. At a known opcode
position (immediately after a reference instruction's uid) there are **268 distinct
tokens with the top 12 covering 78%**, against 3,047 distinct in the 4-byte view. It also
exposes an opcode family the old framing had been splitting in half — **`0x88xx`**
(`0x8802`, `0x8803`, `0x8804`, `0x880E`, `0x8818`, `0x881E`), which never appeared in any
4-byte histogram.

The most common tokens at that position are `0x0551` (22.9%), `0x1640` (13.3%),
`0x8802` (9.6%), `0x0E00` (8.9%), `0x8804` (4.5%) and `0x0D00` (3.9%).

**How it was found:** parse errors under the 4-byte model were not spread out as
desynchronisation would predict — 43.9% of first errors occurred at exactly instruction
13, with a 48.8% error rate at step 14. A structural spike at a fixed depth is not drift,
and inspecting the bytes there showed `0x0910` appearing in the high half of one word and
the low half of the next, which is the signature of a half-word framing error.

### Walking outward: a first opcode table

Anchors give **phase-locked** positions in a stream that otherwise cannot be aligned.
Decoding is directional: the opcode histogram at anchor+8 is sharp (281 distinct, top-14
covering 93%), while at anchor-8 it is diffuse (2044 distinct, 57%) and full of float
high-halves — as expected for variable-length instructions with immediates. **The stream
decodes forward only.**

Anchor-to-anchor distances are a multiple of 4 in **144,335 of 144,335** cases, so
instruction granularity is 4 bytes. Within an opcode `u16`, the high byte takes only 35
distinct values against 150 for the low byte, so it is a narrow field — likely type or
mode, with the low byte selecting the operation.

Classifying each word by what follows it, against the corpus base rate, yields the first
opcode table for this format:

| opcode | occurrences | follower | P | lift vs base |
|---|---|---|---|---|
| `0x0A42` | 83,047 | `u32` input uid | **1.000** | 60x |
| `0x0A02` | 18,057 | `u32` input uid | 0.999 | 60x |
| `0x0902` | 4,468 | `u32` input uid | 0.996 | 59x |
| `0x0942` | 1,726 | `u32` input uid | 0.984 | 59x |
| `0x0982` | 804 | `u32` input uid | 0.964 | 57x |
| `0x0842` | 612 | `u32` input uid | 0.956 | 57x |
| `0x0900` | 363,450 | `f32` immediate | **0.999** | — |
| `0x1140` | 76,187 | **two** `f32` immediates | **0.9997** | — |

Base rates are P(next is float-like) = 0.119 and P(next is an input uid) = 0.017, so the
uid opcodes run ~60x above chance and are effectively deterministic.

`0x0900` is a **push-constant-float** instruction: 99.8% of its followers are
representable `f32` values, and the value distribution is decisive on its own —

```
1.0  0.5  0.25  6.2832  2.0  -0.5  16.0  4.0  0.0625  0.125  3.1416  0.6931
```

`6.2832` is 2*pi, `3.1416` is pi, `0.6931` is ln 2. Mathematical constants appearing as
the most common immediates confirm this is numeric evaluation code, not data.

`0x1140` is a second float-immediate opcode (only 22 of 76,187 followers are not
representable `f32`). Its value profile differs from `0x0900` — mostly `0.0`, `1.0`,
`0.5`, `0.25` and small integers `4.0`–`9.0`, with none of the transcendental constants —
so the two are distinct instructions rather than encodings of one.

### Aligned parsing, and the zero-immediate opcode set

Anchors permit a real forward parse: start after a reference instruction's uid immediate
and advance 4 bytes per instruction, 8 for a known immediate-taker. Parse quality is
measurable as the share of instruction positions holding a word implausible as an
instruction (a float exponent byte). Each confirmed opcode lowers it monotonically:

| model | implausible instruction positions |
|---|---|
| 6 reference opcodes only | 12.59% |
| + `0x0900` | 7.93% |
| + `0x1140` | **7.09%** |

The residual 7% means immediate-takers remain undiscovered, and the metric gives an
honest way to test candidates.

On aligned positions, opcodes whose follower is **never** a non-zero float are confirmed
to take no immediate. With a base rate of P(next is f32) = 0.128, observing zero such
followers across thousands of occurrences is decisive. **100 opcodes qualify at
n >= 4000**, together covering **40%** of all non-immediate instruction positions —
`0x094D` (69,494), `0x052B` (63,245), `0x0517` (59,048), `0x0523` (41,044),
`0x0031` (40,537), `0x0947` (33,843), `0x0A52` (33,711), and so on.

Every one of them has a **narrow arg field** (54–305 distinct values), consistent with
`arg` selecting a mode or operand slot rather than indexing a large table.

### Two rejected candidates — followers that are always zero

`0x21C0` (20,178 occurrences) and `0x1240` (29,832) both look like float-immediate
opcodes under a naive test, because a follower of exactly `0.0` is a valid `f32`. But
99.4% of `0x21C0`'s followers are *precisely* zero, and neither opcode is ever followed
by a non-zero float. Adding `0x21C0` to the parse made it slightly worse (7.09% ->
7.12%). They are therefore **not** float pushes; whatever the following zero word is —
a reserved field, padding, or an always-zero operand — it is not a constant being loaded.
This is the same trap that made `0x1140` look weak at first, running the other way.

### Instruction lengths — 27 opcodes

With `u16` framing established, instruction lengths can be learned from the anchor
constraints: confirmed reference instructions give exact positions, so the lengths of the
instructions between two consecutive anchors must sum to the gap. Walking from an anchor
until an unknown opcode is reached and recording the residual distance to the next anchor
yields that opcode's length whenever it happens to be the last instruction in the span;
the mode over thousands of samples recovers it.

Run to convergence, this decodes **27.2% of anchor-to-anchor spans exactly** — the walk
consumes the span and lands precisely on the next anchor — using 42 opcodes.

Cross-checking two independent learning runs, **27 opcodes have identical lengths in
both** and are reported here as stable. Lengths are in `u16` tokens, inclusive of the
opcode:

| family | lengths |
|---|---|
| `0x88xx` | `0x8820`=7, `0x8804`=9, `0x8805`=9, `0x8807`=11, `0x880E`=11, `0x8803`=13, `0x880D`=13, `0x8816`=13, `0x881E`=13, `0x8806`=15, `0x8818`=17, `0x8809`=21 |
| references | `0x0A42`, `0x0A02`, `0x0902`, `0x0942`, `0x0982`, `0x0842` = 3 (opcode + 2-token uid) |
| constants | `0x0900`=3 (opcode + f32), `0x1140`=5 (opcode + two f32) |
| other | `0x0001`=1, `0x0003`=1, `0x4000`=8, `0x6605`=9, `0x7704`=9, `0x440C`=13, `0x0603`=20 |

The `0x88xx` family is the most consistent group in the format: twelve opcodes, all
odd-length, spanning 7 to 21 tokens. Their size and regularity suggest per-node
descriptors rather than arithmetic.

**[CORRECTED — every `0x88xx` length here is short by exactly 3 tokens (one reference
instruction), a boundary error in the anchor-residual method; and `0x6605`, `0x7704`,
`0x440C` are record tags, not opcodes. The "per-node descriptors" intuition was right.
See "The early record-length table was short by exactly one instruction".]**

**Unstable, do not rely on:** `0x0008` (16 vs 1), `0x0541` (30 vs 2), `0x0551` (29 vs 2).

### A length-measurement method that fails

Measuring an opcode's length as the distance to the next token drawn from a known opcode
vocabulary **systematically under-measures**, because an instruction's own operands may
themselves be vocabulary tokens. It reported `0x0551` and `0x0541` as 2 tokens with
91-100% dominance — convincing, and wrong. Seeding the constraint learner with those
"high-confidence" values *halved* the decode rate, from 27.2% to 17.7%.

The anchor-residual method is sounder because its constraint is external: the walk must
land exactly on an independently known position. It is not unbiased either — it assumes
the unknown opcode is the last instruction in the span, which inflates lengths for common
short opcodes — which is precisely why cross-run agreement, not single-run confidence, is
the criterion used above.

### A third immediate class: small integers

Testing opcodes for immediate *shapes* other than floats and uids turns up a class that
earlier passes missed entirely:

| opcode | n | P(next word is 1..255) | lift | immediate profile |
|---|---|---|---|---|
| `0x09F4` | 46,142 | 0.957 | 24.3x | ~uniform over 0..64, 65 distinct values |
| `0x0B19` | 7,244 | 0.974 | 24.7x | skewed: 10 (62%), 5, 20, 1, 2 |

`0x09F4`'s immediates are evenly spread across a small bounded range, which reads as a
**slot or register index**. `0x0B19`'s are strongly skewed, which reads as a count or
mode selector.

**This corrects the "zero-immediate" classification.** That test asked whether an opcode
was ever followed by a non-zero float, so it only ever excluded *float* immediates.
`0x09F4` sat in that list of ~100 "no immediate" opcodes while in fact taking an integer
one. The list should be read as **"takes no float immediate"**, not "takes no immediate".

A scan of the same kind confirms there are **exactly six** uid-immediate opcodes — the
known reference family, at lifts of 63x to 67x, with no seventh.

### Prioritising by what actually blocks decoding

Rather than guess, instrument: run the decoder and record which unknown opcode halts each
span. Blocking counts over 98,783 spans:

```
0x3F80  22.1%   (float 1.0 - a desynchronisation artefact, not an opcode)
0x1640  19.6%
0x0E00  13.0%
0x0D00   5.6%
0x0A53   3.5%
```

Testing candidate lengths for each and keeping those that improve decoding raises the
rate from **23.69% to 30.67%**. Because lengths are now being chosen by maximising the
reported metric, the result was checked on held-out data — fit on half the regions,
scored on the other half:

```
            train      test
baseline    25.67%    21.52%
+4 lengths  35.53%    25.37%
gain        +9.86pp   +3.85pp
```

The gain generalises but is under half its in-sample size, so some fitting is present.
Lengths selected on the training half alone match the full-data choices exactly.

**Per-opcode confidence, from the margin over the runner-up length:**

| opcode | length | margin | confidence |
|---|---|---|---|
| `0x1640` | 23 | +1656 | strong |
| `0x0D00` | 9 | +152 | moderate |
| `0x0E00` | 19 | +61 over length 24 | weak |
| `0x0A53` | 5 or 6 | **+0 — exact tie** | ambiguous, do not rely on |

`0x0A53` at 6 does match the independent distance-method estimate (90% dominance), which
is the only reason to prefer 6 over 5.

### Corpus scale-up, and what it corrected

Opcode-length work had been running on 90 regions drawn from files under 900 KB — a speed
cap set early and not revisited. Lifting it gives **179 regions, 151.7 MB of code and
470,572 reference anchors, 4.8x the previous input.**

The larger sample immediately overturned a result: **`0x1640` moved from length 23 to 18.**
The 23 came from a run where it beat the runner-up by a large margin, so it looked solid;
it was small-sample noise. Confidence figures derived from a few thousand spans should be
treated accordingly.

Full-corpus figures: baseline 11.17% of spans decoded (lower than the small-corpus 23.69%
because the wider set includes much harder files), rising to **18.94%** with the extended
length table — a gain of +7.77pp over 470,393 spans.

### A minimal program, decoded end to end

`SubstanceDesigner__GrayscaleConvert` is **384 bytes total** — a 2-entry directory, 248
bytes of code, four inputs and one output. Small enough to read completely, and it
validates the entire specification at once: value table, `(n_out, n_in)` header, output
uid array, input descriptor array and footer all land exactly where the spec predicts,
with the footer's back-pointer resolving to `table_start - 52` on the nose.

All four input references decode:

```
0x0056: 0A42 BCF7134B   ref -> $outputsize
0x0086: 0A02 D2F76A4A   ref -> method
0x012A: 0A42 BCF7134B   ref -> $outputsize
0x0132: 0A02 EB850519   ref -> $randomseed
```

The fifth input, the image, is referenced differently: opcode **`0x8821`** at `0x0048`
with operand `0x0009`, followed by the image input's uid as a 4-byte immediate — an image
reference in the `0x88xx` family.

**The constants make the program legible.** Three float triples sit in the code:

```
0x00A8   0.2126, 0.7152, 0.0722    sum 1.0000   Rec.709 luma
0x00B8   0.3333, 0.3333, 0.3333    sum 1.0000   equal-weight average
0x00E8   0.2990, 0.5870, 0.1140    sum 1.0000   Rec.601 luma
```

The manifest names this graph **"Gs Conversion (3 Types)"** with a `method` input
defaulting to 2. The three types are exactly the three standard RGB-to-grayscale
conversions, and all three coefficient sets are readable in the compiled binary. This is
the first case where the *semantic content* of a compiled graph has been recovered — not
just its structure.

Each triple is introduced by opcode **`0x1980`**, which takes three `f32` immediates:
**2,268 of 2,314 occurrences corpus-wide (98.0%)** are followed by three valid floats.
That is a vec3 constant load, and a new confirmed opcode.

Note that `0x1980`'s floats sit at 4-byte boundaries while the opcode is at `2 mod 4`, so
a 7-token instruction flips the parity. The `2 mod 4` rule established for reference
opcodes is therefore **not** universal across all instructions.

### Complete byte accounting for the minimal file

Every byte of the 384-byte `GrayscaleConvert` is assigned to a structure:

```
header                0x0000  0x0038     56
record directory      0x0038  0x0040      8
code                  0x0040  0x0138    248
value table           0x0138  0x0148     16
(n_out, n_in) header  0x0148  0x014C      4
output uid array      0x014C  0x0150      4
input descriptors     0x0150  0x0170     32
footer                0x0170  0x0180     16
                                        384  = file size, no gap
```

**This corrects the "trailer".** Earlier notes described a 28-byte trailer of 7 `u32` at
`size-28`, reached by the header pointer at `0x1C`. In this file that address is `0x164`,
which lands **inside the input-descriptor array**, not at any boundary. There is no
28-byte trailer: there is a 16-byte footer, and the 12 bytes before it are simply the last
one and a half descriptor records. The apparent "7 u32 structure" was an artefact of
reading a fixed 28 bytes back from EOF. `0x1C` holds `size-28` as arithmetic, not as a
pointer to a structure.

Within the 248-byte code region, **76 bytes (30%) are confidently attributed**:

```
0x0048 +8   ref.image  -> input          0x8821, arg 0x0009, uid immediate
0x0056 +6   ref.input  -> $outputsize    0x0A42
0x0086 +6   ref.input  -> method         0x0A02
0x00A6 +14  push.f32x3  0.2126 0.7152 0.0722   Rec.709 luma   0x1980
0x00B4 +16  push.f32x3  0.3333 0.3333 0.3333   average        0x1D80 + 1 operand
0x00E6 +14  push.f32x3  0.2990 0.5870 0.1140   Rec.601 luma   0x1980
0x012A +6   ref.input  -> $outputsize    0x0A42
0x0132 +6   ref.input  -> $randomseed    0x0A02
```

Note `0x1D80` introduces the middle triple with an extra operand token where `0x1980`
introduces the other two directly — a variant, not yet characterised.

### Evidence for three-address code with value numbering

Reading the operand groups by hand in this file (not by blind positional scan) gives a
striking result. Across 13 instructions the operands take **23 distinct values covering
`0x00`..`0x16` with no gaps whatsoever**, and the final operand of each instruction
increases from one instruction to the next in 10 of 12 consecutive pairs.

A contiguous, gapless, monotonically-issued index space is what value numbering or
register allocation produces. Combined with the earlier finding that no push ever
directly follows another push, the machine looks like **three-address code**: last operand
is the destination, earlier operands are sources.

One instruction reads especially clearly: `0x0910` appears three times as
`(0x12, 0)`, `(0x12, 1)`, `(0x12, 2)` — the same source with indices 0, 1, 2. In a
grayscale conversion that is component extraction of R, G and B.

**Not generalised.** Attempting to verify contiguity across 16 other small specimens found
0 of 16, but that test scanned for operands at a fixed byte parity, which cannot be right
when instruction lengths vary. The finding stands for the minimal file, where operand
positions were identified individually, and is **unverified elsewhere** — confirming it
needs a correct parse, which is the very thing still missing.

### The 0x88xx family is 4-aligned, and is not part of the instruction stream

Byte parity separates two populations cleanly:

| family | n | parity |
|---|---|---|
| reference opcodes | 144,022 | **100% at 2 mod 4** |
| `0x0900` push.f32 | 551,977 | **100% at 2 mod 4** |
| `0x1980` push.f32x3 | 2,314 | 98.5% at 2 mod 4 |
| `0x88xx` family | 97,572 | **97.3% at 0 mod 4** |

Real instructions sit at `2 mod 4`. The `0x88xx` family sits at `0 mod 4` — the opposite
parity — so **these are 4-aligned descriptor records, not stream instructions.**

The lengths corroborate it: **all 17 learned `0x88xx` lengths are odd** (7, 9, 9, 11, 11,
13, 13, 13, 13, 13, 15, 17, 17, 19, 21, 23). An item starting at `0 mod 4` with an odd
token length ends at `2 mod 4`, handing control back to the instruction stream — exactly
the alternation required. Reference instructions, at length 3, do the reverse.

**Consequence for earlier claims.** Counting `0x8804`/`0x8805` "in the code region" and
finding hundreds was wrong — restricted to valid opcode positions the count is **zero** in
every image-bearing file checked. Those hits were wrong-parity noise. `0x8804` and
`0x8805` still discriminate grayscale from colour perfectly (157/157), but they should be
described as **record type codes**, not as instructions the machine executes.

### A controlled pair: grayscale vs colour, and the 0xC0 bit-field

`SubstanceTools__radial_blur_grayscale` (536 B) and `SubstanceTools__radial_blur_color`
(572 B) are the same filter in two channel modes. They declare **the same six inputs**
with the same types and defaults, and their code differs by just 36 bytes. That makes
them a natural controlled pair: one variable changed, everything else held.

Diffing the two token streams (with uid immediates normalised, since the uids differ)
shows a systematic one-for-one opcode substitution:

```
grayscale   0x0907  0x090C  0x0504  0x0912  0x0915  0x190B
colour      0x09C7  0x09CC  0x05C4  0x09D2  0x09D5  0x19CB
```

Every pair differs by exactly **+0xC0**. Opcode **bits 6-7 select channel mode**.

The `0x88xx` records in the same diff follow a *different* convention — `0x8820`/`0x8821`
and `0x8828`/`0x8829`, differing by **+1**, consistent with the already-confirmed
`0x8804` (grayscale) / `0x8805` (colour) resource codes. So instructions encode the mode
in bits 6-7 while `0x88xx` records encode it in bit 0.

Corpus-wide confirmation, restricted to real opcodes (>= `0x0100`, non-float bit patterns,
both forms occurring at least 500 times):

| base | n | +0xC0 | n | ratio |
|---|---|---|---|---|
| `0x0910` | 112,748 | `0x09D0` | 34,840 | 0.31 |
| `0x0907` | 68,313 | `0x09C7` | 37,888 | 0.55 |
| `0x0504` | 69,139 | `0x05C4` | 9,210 | 0.13 |
| `0x0914` | 27,260 | `0x09D4` | 34,944 | 1.28 |
| `0x0912` | 27,344 | `0x09D2` | 34,083 | 1.25 |
| `0x0D09` | 10,664 | `0x0DC9` | 36,931 | 3.46 |
| `0x0931` | 8,361 | `0x09F1` | 13,761 | 1.65 |
| `0x0930` | 12,815 | `0x09F0` | 8,527 | 0.67 |
| `0x0524` | 10,778 | `0x05E4` | 847 | 0.08 |

Nine genuine pairs spanning the `0x05xx`, `0x09xx` and `0x0Dxx` families, 347,422
base-form against 211,031 `+0xC0` occurrences. Note `0x0910` — the component-extract
candidate from the minimal file — has colour form `0x09D0`.

**Caveat.** A naive sweep for `X`/`X+0xC0` across all values returns 98 "pairs", but most
are coincidences between small operand values (`0x0000`/`0x00C0` at ratio 0.000). The
convention holds for the three families above, not as a universal bit-field.

### Image inputs are declared by 0x8820 / 0x8821

Across the small specimens, the count of `0x8820` plus `0x8821` records tracks the number
of **image inputs** the graph declares:

```
LGML_concat_xy      8 image inputs  ->  0x8821 x8
multi_blender       8 image inputs  ->  0x8821 x8
LGML_mask_by_color  2 image inputs  ->  0x8821 x2
ContouLine          1 image input   ->  0x8820 x1
Substance_graphA    0 image inputs  ->  none
```

Over 136 single-graph specimens the counts match exactly in **121 (88%)**; restricted to
those that actually have image inputs, 32 of 43 (74%). The mismatches concentrate in
multi-graph packages (`ie_pcloud`: 52 image inputs spread over 20 graphs) and in files
where the code region is truncated, both of which break the premise rather than the rule.

**Bit 0 selects grayscale versus colour**, on three independent lines of evidence:

1. The `radial_blur_grayscale` / `radial_blur_color` controlled pair differs at exactly
   this record: `0x8820` in the grayscale build, `0x8821` in the colour build.
2. `LGML_hsl_adjuster` declares two image inputs named `rgb` and `gray_scale`, and emits
   exactly one `0x8820` and one `0x8821`.
3. It matches the already-verified `0x8804` / `0x8805` convention in the resource records
   (157/157), where bit 0 likewise separates grayscale from colour.

**What could not be verified.** The manifest does encode an image input's channel count
indirectly — a `default` of `0.5` implies grayscale, `0.5,0.5,0.5,1` implies colour — but
only **65 of 215** image inputs carry a default at all, and no single file has them on
every image. So the rule rests on the controlled pair and the naming case, not on a
corpus-wide count.

### 0x8828 / 0x8829 and a second length method

`0x8828`/`0x8829` are another grayscale/colour pair, but **not one per output**. Across
single-output graphs that contain them, the counts rarely equal the output count (7%),
yet the flag is informative in one direction:

```
grayscale output   ->  only 0x8828 in 10 of 10 files, never 0x8829
colour output      ->  only 0x8828 (5), only 0x8829 (6), both (4)
```

A grayscale-output graph **never** emits the colour variant, while colour graphs use
both. That is what an operation variant selected by the data being processed looks like,
rather than by the final output. The `radial_blur` controlled pair agrees directly:
`0x8828` in the grayscale build, `0x8829` in the colour build.

### Record lengths measured directly in tiny files

Small specimens permit a much cleaner length measurement than the anchor-residual
learner: records and confirmed reference instructions alternate within a few tokens, so
the distance from an `0x88xx` record to the next verified reference *is* its length. Over
61 small files:

| record | n | length | dominance | vs learner |
|---|---|---|---|---|
| `0x8820` | 39 | **7** | 100% | new |
| `0x8821` | 67 | **7** | 99% | new |
| `0x8807` | 12 | 11 | 100% | confirms |
| `0x8825` | 12 | **11** | 92% | new |
| `0x8803` | 49 | 13 | 86% | confirms |
| `0x881F` | 13 | **9** | 85% | new |
| `0x8805` | 36 | 9 | 83% | confirms |
| `0x8806` | 16 | 15 | 81% | confirms |
| `0x8801` | 10 | 19 | 80% | confirms |
| `0x880D` | 22 | 13 | 73% | confirms |
| `0x882A` | 14 | **15** | 64% | new |
| `0x8814` | 23 | **9** | 48% | new |

`0x8820` and `0x8821` both measuring 7 tokens is a good internal check — variants of one
record should share a length, and they do, at 100% and 99% dominance.

**Two disagreements with the learner, both now flagged:**

- `0x880C`: the learner says 7, this method says **5**, and the distribution is genuinely
  bimodal (5 in 19 cases, 7 in 14). Possibly two forms.
- `0x8818`: learner 17, this method 15 (60% dominance, n=20).

**[RETRACTED — both. Measured exactly from directory-delimited boundaries over thousands
of records, `0x880C` is not bimodal at 5/7; record length is a near-deterministic function
of inline bytecode size. See "Why records are variable-length".]**

Ten lengths are independently confirmed by two unrelated methods, six are new, and two
are contradicted — which is the useful outcome of having a second measurement rather than
a bigger sample of the first.

### Finding more small files: search the text, not the binary

`.sbsar` is binary and not indexed by code search, so repositories containing them cannot
be found directly. Two indirect routes work:

1. Searching for distinctive `.sbs` tokens (`compNode`, `graphOutputs`, ...) finds repos
   that ship *source* graphs — but misses every project that has only compiled files.
2. **Unity writes a text `.meta` file beside every asset.** Searching `sbsar extension:meta`
   finds Unity projects containing substances without needing to index the binary at all.

The second route surfaced 242 repositories the first had missed, yielding 59 further small
specimens. Two sources are worth naming: **KhronosGroup/glTF-Sample-Assets**, and a copy
of the **Substance Automation Toolkit sample content** shipped inside a third-party repo.

### A semantically transparent specimen: Normalize_RG

`Normalize_RG` (328 bytes, from the Khronos glTF sample assets) takes one bitmap and
normalises its red and green channels. Its instruction stream is readable from the
constants alone:

```
0x1140  push vec2 (2.0, 2.0)
0x1140  push vec2 (1.0, 1.0)
0x1540  push vec2 (0.5, 0.5)
0x1140  push vec2 (0.5, 0.5)
```

That is the standard normal-map remap — decode `n = tex*2 - 1`, normalise, re-encode
`out = n*0.5 + 0.5`. The constants appear in exactly that order.

Crucially they are **vec2** constants, not scalars or vec4, because the graph normalises
exactly two channels. This is an independent semantic confirmation of `0x1140` as a
two-component constant load, in a file whose purpose is known from its name and whose
arithmetic is textbook. `0x1540` appears as a further vec2 variant (`0x1140 + 0x400`).

The surrounding opcodes `0x0950`, `0x0952`, `0x0953`, `0x0954` each take two operands and
are the arithmetic performing the remap, though which is multiply and which is subtract is
not yet separable.

### First arithmetic opcodes: 0x0912 / 0x0913 / 0x0914

`Normalize_RG` constrains its own arithmetic, because the algorithm is known exactly. The
constant loads appear in this order, each followed immediately by an operation:

```
push vec2 (2.0, 2.0)  ->  0x0954      x * 2
push vec2 (1.0, 1.0)  ->  0x0953      ... - 1
push vec2 (0.5, 0.5)  ->  0x0954      ... * 0.5
push vec2 (0.5, 0.5)  ->  0x0952      ... + 0.5
```

`0x0954` appears for *both* multiplications and nothing else does, which pins it. Applying
the component-count rule (bits 6-7) gives the one-component base forms:

| base | 1 comp | 2 comp | 3 comp | 4 comp | reading |
|---|---|---|---|---|---|
| `0x0912` | 47,427 | 22,545 | 3,941 | 102,905 | **add** |
| `0x0913` | 96,932 | 28,458 | 718 | 780 | **subtract** |
| `0x0914` | 60,531 | 26,148 | 855 | 103,372 | **multiply** |

Three independent lines corroborate the assignment:

1. **Constant profiles.** The value most often loaded immediately before each op:
   `0x0913` takes `1.0` in **96%** of 227,468 cases — `x - 1` and `1 - x` are the most
   common operations in shading code. `0x0914` takes `0.5`, `1.0`, `6.2832` (2*pi) and
   `0.25` — scale factors, with the 2*pi being angle conversion. `0x0912` takes `0.5` and
   `0.0` — offsets.
2. **Component distribution.** Subtract is rare at four components (780) while add and
   multiply are common there (103k each). You add and multiply RGBA colours routinely;
   you rarely subtract them. Subtract is instead commonest at one component (96,932),
   which is the grayscale invert `1 - x`.
3. The three bases are **consecutive** (`0x0912`, `0x0913`, `0x0914`), as an arithmetic
   block would be.

### Second known-algorithm specimen: Polar Coordinates

`PolarCoordinates2Grayscale` (448 bytes) independently confirms the assignment and
extends it. A polar transform must compute `d = p - centre`, then an angle, then a radius,
and the code does exactly that:

```
ref.f2 -> _center        0x0942
0x0953  sub.2                     d = p - centre        <- SUB confirmed independently
0x0D00  <- 0x40C90FDB = pi        the angle constant
ref.int1 -> _tiles       0x0A02
0x0914  mul                       angle * tile count    <- MUL confirmed independently
```

Neither confirmation comes from `Normalize_RG`, so the two specimens agree on `sub` and
`mul` from unrelated algorithms.

### A complete operation: normalize()

The chain in `Normalize_RG` decodes end to end:

```
0x0918  dot(v, v)          operands identical
0x0528  sqrt               -> length
0x0D00  push 1.0
0x0915  div                -> 1 / length
0x0954  mul.2              -> v * (1/length)
```

That is `normalize()` in five instructions, and every opcode in it is now named.

### The arithmetic block, extended

| opcode | operation | 1c | 2c | 3c | 4c |
|---|---|---|---|---|---|
| `0x0912` | add | 47,427 | 22,545 | 3,941 | 102,905 |
| `0x0913` | subtract | 96,932 | 28,458 | 718 | 780 |
| `0x0914` | multiply | 60,531 | 26,148 | 855 | 103,372 |
| `0x0915` | **divide** | 45,639 | 1,186 | 32 | 25 |

Four consecutive opcodes. Divide's distribution is the giveaway: **97% of it is
one-component**, because you divide a vector by a scalar rather than component-wise —
exactly the asymmetry the other three do not show.

Three further opcodes are now named:

- **`0x0918` = dot product.** Its first two operands are identical in 1,770 of 3,825
  cases (46%), which is `dot(v,v)` — the length-squared idiom — far above chance.
- **`0x0528` = square root.** It is the most common successor of `0x0918` (1,303 cases),
  and is itself usually followed by a constant load and a divide.
- **`0x0D00` = load float constant.** 570,247 occurrences, **99.9% at `0 mod 4`** and
  **99% carrying a valid `f32` four bytes in**. Its immediates are `0.0`, `1.0`, `0.5`,
  `2.0`, `-1.0`, `6.28`, `6.2832` (2*pi) and `pi` — the constant vocabulary of shading
  code. It is more common than `0x0900` and had been appearing unexplained in every
  earlier analysis.

**Caveats.** The assignment rests on two specimens whose algorithms are known plus
statistical corroboration; it is not proven. Operand order is not recoverable — `x - 1`
and `1 - x` are indistinguishable here — and if the remap is read in a different order the
three labels could permute among themselves. Together these twelve opcodes account for
just 1.4% of opcode positions, so the bulk of the arithmetic is still unidentified.

### The unit-test differential corpus

The Synthoid suite also confirms `0x880D` semantically. `FloatTest`, which has no colour
input, contains two uniform-colour records: **(0.5, 0.5, 0.5, 1)** — a grey base colour —
and **(0.5, 0.5, 1, 1)** — the flat normal-map constant. Every test in the suite emits
`basecolor`, `normal`, `roughness` and `metallic`, so a flat normal is exactly what should
be there, and `0.5, 0.5, 1` is precisely how one is encoded.

### The smallest specimens, and a fully decoded record type

Sweeping the 80 known repositories for `.sbsar` under 60 KB yields **193 files, all of
which extract**. The smallest payloads are far below anything previously examined:

```
152 B  LGMLtools Substance_graphA / graphB
288 B  substance-for-unity-extensions ColorTest / FloatTest
328 B  LGMLtools Substance_graphC / graphD
364 B  substance-for-unity-extensions ImportTest
384 B  SubstanceDesigner GrayscaleConvert   (previous smallest)
400 B  substance-for-unity-extensions BoolTest
```

`Substance_graphA` is **152 bytes total** with only the two system inputs, one output, and
a **40-byte code region** — small enough to parse exhaustively.

### An exact parse of a 40-byte program

```
0x3C   0000 0001 0000 0000            preamble, 8 bytes
0x44   880D <13 tokens>              record, 26 bytes
0x5E   0A42 -> $outputsize            reference, 6 bytes
0x64   = table_start                  8 + 26 + 6 = 40, no remainder
```

The learned length `0x880D = 13 tokens` lands **exactly** on the reference instruction,
which lands exactly on `table_start`. That is an independent confirmation of the length
table: it was derived by anchor-residual statistics on large files, and it predicts a
40-byte program to the byte.

### `0x880D` = uniform RGBA colour

The record carries **four `f32` at offset +8**. The A/B/C/D variant family makes it plain:

| graph | R | G | B | A |
|---|---|---|---|---|
| A | 0.3665 | 1.0000 | 0.0000 | 1.0000 |
| B | 0.0000 | 0.5000 | 0.3701 | 1.0000 |
| C | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| D | 1.0000 | 0.0000 | 0.9110 | 1.0000 |

Graph C is pure red. These are minimal "output a flat colour" graphs, which is exactly
what a blog post demonstrating a naming conflict would use.

Corpus-wide: **4,530 `0x880D` records**, of which 3,929 carry four well-formed floats.
Of those, **100% have all four components within [0,1]**, and the fourth component takes
**only two values ever — exactly 1.0 (3,538) or exactly 0.0 (391)**. A component
restricted to {0,1} while the other three vary continuously is alpha.

`token[1]` is `0x0109` in 91% of records, and `token[12]` is a small integer (1 in 84%),
consistent with the destination-index role that the three-address reading predicts.

This is the first record type decoded to full semantics: type, payload layout, and
meaning of every float.

### It is not a stack machine

Across 50,000 spans there are **zero** occurrences of one push instruction immediately
followed by another. A stack machine evaluating a binary operation would push two
operands consecutively; that never happens. Combined with the `arg` half-word, the model
is register/slot based: the opcode acts, and `arg` names a slot.

The `arg` field is **bimodal**, which is a useful discriminator:

- **wide** — thousands of distinct values (`0x0000`: 20,126, `0x0001`: 12,910,
  `0x0002`: 12,257): an index into something large, i.e. a slot or operand reference.
- **narrow** — under ~300 distinct values (`0x052B`: 88, `0x0031`: 71, `0x09F4`: 54):
  a mode or enum selector.

Float bit patterns masquerade as opcodes in any scan that is not parse-aligned —
`0x3F80` (1.0) appears 301,899 times in opcode position. The arg-width test exposes
them: they carry only 17–23 distinct "args" because those bits are mantissa, not a field.

### A method that did not work

An iterative inference loop — walk from anchors, find opcodes that precede words
implausible as instructions, and promote them to immediate-taking — **overfits and should
not be trusted**. Greedy promotion selected `0x0000` on 19% evidence and then made the
objective worse over successive rounds (7.4% -> 7.7% -> 8.1% implausible). Its candidate
`0x1240` fails direct testing: 32.6% of its followers are not representable floats. Every
opcode in the table above was instead confirmed by direct conditional probability against
the corpus base rate, which is the method that holds up.

### Why this matters

Records have no framing, but their *contents* do. The interface block supplies uids whose
byte patterns can be located in the stream, and each hit exposes the instruction
immediately before it. That is a bootstrap that needs no authored specimens, and it
contradicts the flat pessimism of the section below: record *boundaries* cannot be
recovered from bytes, but instruction-level structure partly can, anchored on known uids.

What a differential corpus would still buy is **operation semantics** — knowing that
opcode `0x0019` is, say, a multiply. Anchoring identifies immediate-taking opcodes and
their operand types, but not what each operation computes. That gap is narrower than it
was, and no longer blocks all progress.

## The instruction stream is self-describing — confirmed

**`length_in_tokens = (opcode >> 10) + 1`**, for every instruction opcode in
`0x0400 .. 0x7FFF`. The top six bits of the opcode are the count of tokens that follow
it. Nothing else has to be known about an instruction to skip it correctly.

This supersedes every earlier per-opcode length measurement, all of which it reproduces.

### How it was found, and why the earlier attempts missed it

Length was previously attacked one opcode at a time — anchor residuals, distance to the
next vocabulary token, greedy hill-climbing — and each attempt produced a table of
unrelated numbers with no structure to generalise from. Two of those methods were wrong
(recorded above), and the surviving table covered 21 opcodes.

The rule fell out of *closure*, not of measurement. Admitting an opcode to the known set
un-biases the continuation test for its neighbours, so lengths were inferred in rounds
(`closure.py`), each round validated on a held-out fifth of the corpus:

| round | admitted                                                        |
|-------|-----------------------------------------------------------------|
| 1     | `0x0532 0x0524 0x0523 0x0931 0x0D49 0x0916 0x0D2F 0x052D 0x0526 0x0D33` |
| 2     | `0x085D 0x0860 0x0511 0x085B 0x0847`                            |
| 3     | `0x0501`                                                        |
| 4     | `0x0954`                                                        |
| 5     | `0x0950`                                                        |
| 6     | `0x0541`                                                        |

Sorting the 19 results by opcode made the pattern unmissable: every `0x05xx` came back
2, every `0x08xx` and `0x09xx` came back 3, every `0x0Dxx` came back 4. The constants
already known — `0x0900`=3, `0x0D00`=4, `0x1140`=5, `0x1980`=7 — extend the same series,
and `(op >> 10) + 1` fits all of them.

The blocker `0x0517` is the reason iteration was necessary. It scored **zero at every
candidate length** in the first pass, because the test required the following token to be
a *known* opcode and `0x0517` is always followed by `0x094D`, which was also unknown. It
was only admitted after `0x094D` had been read directly out of decoded context.

### Verification

1. **Against prior work.** The rule predicts all 23 independently-established lengths
   with **zero disagreements** — including `0x1980`=7, which had itself corrected an
   earlier wrong measurement.
2. **Against the corpus.** Re-running the coverage census over all specimens with the
   rule replacing the finite table:

   ```
   code bytes             : 214,161,240
   covered, 21-opcode table:  70,489,620  (32.9%)
   covered, rule           : 203,079,394  (94.8%)
   ```

   The residue is not opcodes. It is the `0x88xx` records, which are excluded by
   construction, plus short mis-started runs landing on operand tokens.

### Consequences

- **Any `.sbsasm` can be fully tokenised into instructions without a semantic opcode
  table.** Unknown operations can be skipped exactly rather than guessed past, so a
  parser can be complete before it is comprehensive.
- Operand counts are now free: an instruction has `op >> 10` operand tokens, so the
  three-address structure is directly readable everywhere.
- The remaining work is purely semantic — *what* each opcode computes, not where it ends.

### Bit layout, so far

| bits  | meaning                                    | confidence |
|-------|--------------------------------------------|------------|
| 15–10 | operand-token count (= length − 1)         | confirmed  |
| 9–8   | class/page (`0x05`,`0x08`,`0x09`,`0x0D`, …)| observed   |
| 7–6   | component count − 1                        | confirmed for reference opcodes; **not** general — `0x0862` compares scalars but has bits 7–6 = 1 |
| 5–0   | operation id                               | observed   |

Constants encode their component count in the *length* field rather than in bits 7–6,
which is why they walk up the pages: `0x0900` (1 float, 3 tokens), `0x1140` (2 floats,
5), `0x1980` (3 floats, 7), and by extension `0x21C0` (4 floats, 9). **`0x21C0` was
previously rejected as a float immediate on the grounds that its following tokens are
always exactly zero; under the rule it is simply a float4 constant, and the zeros are
zero vectors.** That rejection should be treated as withdrawn pending a direct check.

### Records are exempt

`0x8000`+ does not obey the rule: `0x8803 >> 10` would predict 35 tokens against a
measured 9. Records are 4-aligned and separately framed, consistent with the earlier
finding that they are not part of the instruction stream.

### The constant family, complete

Bits 9–8 of the opcode are a **type field**, tested by decoding each opcode's immediate
both ways over ~160 specimens:

| opcode   | payload as float | payload as int | verdict |
|----------|------------------|----------------|---------|
| `0x0900` | 99.8% plausible  | 13.0%          | float   |
| `0x0A00` | 21.0%            | 100.0%         | int     |
| `0x1140` | 100.0%           | 47.7%          | float2  |
| `0x1240` | 69.7% (mostly NaN)| 100.0%        | int2    |
| `0x21C0` | 100.0%           | 51.9%          | float4  |

So `type 1 = float`, `type 2 = int`. Type 0 is the comparison page (`0x08xx`), whose
result is a boolean — consistent with `0x0862`/`0x085F` feeding `select`.

#### Padding, and why each constant has two encodings

Every constant appears as two opcodes differing by exactly `0x0400`, which is +1 in the
length field. The extra token is a **2-byte pad**, and the alignment statistics say
exactly why:

| opcode   | kind          | offset mod 4 |
|----------|---------------|--------------|
| `0x0900` | float1        | 2 (100%)     |
| `0x0D00` | float1 padded | 0 (100%)     |
| `0x1140` | float2        | 2 (100%)     |
| `0x1540` | float2 padded | 0 (100%)     |
| `0x1240` | int2          | 2 (100%)     |
| `0x1640` | int2 padded   | 0 (100%)     |

The split is 100%/0% in every case. An opcode token is 2 bytes, so an instruction at
2 mod 4 leaves its immediate at 0 mod 4 already; one at 0 mod 4 would leave the
immediate straddling a word boundary, and the compiler emits the padded variant to
prevent that. **The immediate is always 4-byte aligned.** This is the same alignment
discipline noted earlier for reference opcodes sitting at 2 mod 4, now explained.

Note this is not a dedicated flag bit — it is simply the length field counting one more
token. For non-constant opcodes bit 10 carries no padding meaning: `0x0D09` is `select`
with three genuine operands.

#### Predicted, then checked

Generating the family from `op = (2·comps)<<10 | type<<8 | (comps−1)<<6` plus the padded
variant predicts sixteen opcodes. Twelve are present in the corpus **with the predicted
alignment**:

```
0x0900 float1        2880479     0x0A00 int1          304372
0x0D00 float1 pad     960215     0x0E00 int1 pad      162568
0x1140 float2         695311     0x1240 int2          299225
0x1540 float2 pad     782972     0x1640 int2 pad      212161
0x1980 float3          29393     0x1A80 int3              13   <- noise
0x1D80 float3 pad      24014     0x1E80 int3 pad           6   <- noise
0x21C0 float4         215219     0x22C0 int4               8   <- noise
0x25C0 float4 pad       2867     0x26C0 int4 pad          12   <- noise
```

The four missing ones are the int3/int4 constants. Their handful of "occurrences" have
the *wrong* alignment for their predicted variant and decode to garbage, so they are
mis-started runs, not real instructions. Integer 3- and 4-vectors simply do not arise in
this DSL, which is unsurprising.

`0x1980`'s first observed payload is `(0.299, 0.587, 0.114)` — the Rec.601 luma weights.

#### Two withdrawn rejections

`0x21C0` and `0x1240` were both previously rejected as immediate-carrying opcodes,
on the grounds that their following tokens "are always exactly zero". Both are constants:
`0x21C0` is float4 (samples include `(0,1,0,1)`, `(1,1,1,1)`) and `0x1240` is int2
(samples `(-1,-1)`). The earlier test read the payload at the wrong width and mistook
the result for emptiness.

### Third known-algorithm specimen: the sRGB transfer function

`LGMLtools__sRGB_colorchart` (396 KB) was found not by guessing which files have known
algorithms but by **scanning the corpus for signature mathematical constants**. Seven
files carry four or more of the seven sRGB constants; this one is named for the
algorithm. The encode direction is fully specified maths:

    srgb = (l <= 0.0031308) ? 12.92*l : 1.055*l^(1/2.4) - 0.055

At 0x23AC0 the block appears three times in a row — once per colour channel, unrolled —
each preceded by a component extract. Decoded (`symeval.py`, value numbers as emitted):

    v3  = extract v2[0]              the channel
    v4  = const 0.00031308
    v5  = cmp   (v3, v4)             threshold test
    v6  = const 12.92
    v7  = mul   (v3, v6)             the linear branch
    v8  = const 0
    v9  = cmp   (v3, v8)             domain guard for the log
    v10 = ln    (v3)
    v11 = const 0.693147182          ln 2
    v12 = div   (v10, v11)           => log2(v3)
    v13 = const 0.416666657          1/2.4
    v14 = mul   (v12, v13)
    v15 = exp2  (v14)                => v3^(1/2.4)
    v16 = const 0
    v17 = select(v9, v16, v15)       (v3 <= 0) ? 0 : pow
    v18 = const 1.055
    v19 = mul   (v18, v17)
    v20 = const 0.055
    v21 = sub   (v19, v20)
    v22 = select(v5, v7, v21)        the sRGB piecewise result

Evaluated symbolically against the reference function over 1000 samples of (0,1], the
**maximum absolute deviation is 5.2e-08** — float32 rounding. This is an exact decode,
not a resemblance.

#### There is no `pow` instruction

The exponent is computed as `exp2(ln(x)/ln2 * p)`. That lowering pins the two unary
opcodes uniquely, because only one assignment reproduces `x^p`:

| assignment                      | `0x052B(0x0529(x)/ln2 * p)` evaluates to | verdict |
|---------------------------------|------------------------------------------|---------|
| `0x0529`=ln,   `0x052B`=exp2    | `2^(log2(x)·p)` = `x^p`                  | correct |
| `0x0529`=log2, `0x052B`=exp2    | `x^(p/ln2)`                              | wrong   |
| `0x0529`=ln,   `0x052B`=exp     | `x^(p/ln2)`                              | wrong   |
| `0x0529`=log2, `0x052B`=exp     | `x^(p/ln2²)`                             | wrong   |

The division by `ln 2` is the discriminator: it exists only to convert a natural
logarithm into a base-2 one, which is pointless unless the consumer is base-2. So
**`0x0529` = natural log** and **`0x052B` = exp2**. The ISA evidently offers `ln` and
`exp2` but neither `log2` nor `pow`; the compiler synthesises the rest.

This also extends the unary family already containing `0x0528` = sqrt — three
consecutive opcodes `0x0528/0x0529/0x052B`, all 2 tokens, all one operand.

#### Independent confirmation on an unseen file

`DLG-Tools__Embroidery_Legacy` carries all seven constants and implements the **inverse**
transform at 0x1C56:

    linear = (s <= 0.04045) ? s/12.92 : ((s + 0.055)/1.055)^2.4

It decodes with the same table, unchanged — `add` where the encode direction had `sub`,
`div` by 1.055 where it had `mul`, and the exponent constant 2.4 instead of 1/2.4, with
the identical `ln → /ln2 → mul → exp2` idiom and the identical `<=0` guard. Nothing was
fitted to this file; it was decoded after the table was fixed.

#### New opcodes

| opcode   | tokens | operands | meaning                                            |
|----------|--------|----------|----------------------------------------------------|
| `0x0529` | 2      | 1        | natural logarithm                                   |
| `0x052B` | 2      | 1        | `exp2`, i.e. 2^x                                    |
| `0x0D09` | 4      | 3        | `select(cond, then, else)` — ternary, not a branch   |
| `0x0862` | 3      | 2        | comparison, true selects the low branch              |
| `0x085F` | 3      | 2        | comparison, true selects the low branch              |
| `0x0910` | 3      | 2        | component extract: `(source, index)`                 |

`0x0D09` being a *select* rather than a branch matters: the stream has no control flow
here at all. Both arms are always evaluated, which is why the `x <= 0` guard exists —
`ln(0)` is evaluated unconditionally and its result discarded by the select.

**[SUPERSEDED — see "The logic and comparison block" below: these are `lreq` and `gt`,
two different comparisons, resolved via the select arm order.]** Unresolved: `<` versus `<=`. Two distinct comparison opcodes appear in the same role.
`0x0862` is used for the threshold test in the encode file and for the domain guard in
both; `0x085F` is the threshold test in the decode file. Both are "less-than-ish" — true
selects the linear branch. The sRGB function cannot separate `<` from `<=`, since the two
differ only exactly at the threshold, and the guard cannot either (`ln(0)` = -inf makes
`exp2` underflow to 0, the same value the select supplies). Distinguishing them needs a
specimen where the boundary case is observable. Recorded as unknown rather than guessed.

**An authoring bug, faithfully reproduced.** The encode file's threshold is `0.00031308`,
a factor of ten below the correct `0.0031308`; the crossover with `12.92*l` is therefore
discontinuous. The value 0.0031308 does appear in the file, but in the value table at
0xF1A, not in the code. This is a defect in the original graph, and it is useful evidence:
the compiler emits the authored constant verbatim and does no constant validation.

## Records are unframed — confirmed by elimination

Slicing 411,520 records from 123 specimens (each record being the span between
consecutive directory entries) establishes what records are *not*:

| property | result |
|---|---|
| entry alignment | **4-byte aligned, 373790/373790** |
| record size | **always a multiple of 4**; 4 to 234,440 bytes, 1022 distinct sizes |
| leading `u16` is a type tag | **no** — 16,517 distinct values, and a tag maps to a single size in only 3% of records |
| record carries its own length | **no** — every tested encoding (`u32 == gap`, `gap-4`, `gap/4`, `u16*4`, trailing length) matches under 0.5% |

So records carry **no in-band framing at all**: no magic, no type tag, no length. The
directory is the sole framing, which is why it is stored explicitly and why losing it
(by assuming it sits at `0x38`) makes the body unreadable.

Records are also **not a shared vocabulary**. Hashing 255,184 record bodies across 162
specimens yields 210,825 distinct contents, **97% of them unique to a single specimen**;
only 215 records are shared by 10 or more files, and those are small (20–40 bytes). So
records are not reusable library primitives that could be catalogued across a corpus —
they are per-graph, which rules out building a record vocabulary from natural variation
and was worth testing before concluding a differential corpus is required.

The practical consequence is that record *semantics* cannot be recovered from record
bytes alone — there is no self-description to bootstrap from. Decoding requires external
ground truth that varies one thing at a time, which is precisely the differential-corpus
approach: minimal graphs published at increasing complexity, diffed against each other.
The `.sbs`/`.sbsar` pairs are too coarse for this, since their graphs differ in many
ways at once.

## Graph-input default table — confirmed

The pointer at 0x2C targets a table of graph input defaults.

**Contents: the graph's `<inputs>` plus the package's `<global><inputs>`, together.**

**Ordering: sorted by the manifest's `uid` attribute, ascending.** Not declaration
order, not GUI group order. Testing all four candidate orderings against the binary,
uid-ascending is the only one that reproduces long runs.

**Element widths follow the manifest `type` code:**

| type | meaning | encoding | width |
|---|---|---|---|
| 0–3 | float1..float4 | N x f32 | 4N |
| 4, 8, 9, 10 | int1, int2..int4 | N x i32 | 4N |
| 5 | image | **version-dependent** — see below | 16 or 0 |
| 6, 7 | string, font | no slot; text defaults are stored elsewhere | 0 |

**Image inputs are encoded differently per assembly version — confirmed.** From
**v8 (`0x00080000`) onward** an image input occupies a **16-byte `f32 x 4` slot at its
uid position**, holding its scalar default in component 0 and zeros elsewhere, or four
zero words when it has no default. In v2 through v6 an image input occupies **no slot at
all**. Getting this wrong shifts the table start by 16 bytes per image and corrupts the
whole prefix.

The threshold was originally recorded as v9. That was wrong: the corpus contained only
one v8 single-graph specimen and it happens to have no image inputs, so the boundary was
invisible. Four **multi-graph** v8 packages exposed it — their value tables overran by
exactly `16 x (image count)` (16, 48, 128 and 256 bytes for 1, 3, 8 and 16 images).

Evidence now covers **29 specimens with image inputs** across five versions, and the
rule holds in all of them under the full validator (value table + header + descriptor
array + directory).

One caveat worth stating, because it nearly produced a false correction here: on very
small tables (2–4 entries) width 0 and width 16 can *both* appear to validate, since a
shifted table of common values like 0 and 1 may still match. A test that accepts the
first width that works will report width 0 for such specimens and look like a
counterexample. Always require the full structure — header, descriptor array and
directory — before concluding a width, and treat tiny tables as ambiguous rather than
decisive.

`RoadLinesSubstance002`'s `opacity` image input (manifest default `"1"`) holds
`(1.0, 0.0, 0.0, 0.0)`; `TilesSubstance017`'s defaultless `input` holds four zero words.

### Locating the table — confirmed, deterministic

The header field at **0x2C equals `table_end - 52`** in all 58 specimens, exactly. Since
the table's length follows from the manifest, the start is then pure arithmetic — no
searching, no anchoring:

```
total       = sum of per-input widths, in uid-ascending order (table below)
table_start = u32_at(0x2C) + SKEW - total        # SKEW is 52 or 48, see below
```

**The skew is always 52 — and global inputs belong in the table.** An intermediate
draft reported the skew as "52 or 48, discriminator unknown". That was wrong in an
instructive way: the apparent 48 was a missing 4 bytes, because **global inputs
(`$time`, `$normalformat`) participate in the value table**, merged into the same
uid-ascending order as the graph's own inputs.

Count them and the skew is 52 everywhere, with no exceptions in 125 specimens. The
package-level `<global><inputs>` block in the manifest is not decorative — its entries
carry values in the table exactly like graph inputs do.

Validated across all three sources: 125/125 single-graph packages locate correctly and
validate with zero unexplained entries. This replaces the earlier anchor-and-walk-back
heuristic, which needed a long verbatim run to get started and could not work on a file
whose defaults were all common values.

The trailer participates in the same relation: **`trail[6] = table_start - 52`**
(**489/489 specimens, no exceptions** — the earlier "Leaking004 is -56" was an artifact of
the superseded table locator). Consequently `u32_at(0x2C) - trail[6]` equals the
table length exactly. The same 52-byte skew appears at both ends, which is why the
pointer lands at no meaningful position *within* the table — it is `+0x60` into one
specimen, `+0x98` into another, and in ChristmasTreeOrnamentSubstance007 it falls 8
bytes *before* the table begins.

**What the 52 bytes are — investigated, largely by elimination.** The region
immediately preceding the value array is *not* a fixed-layout header. Profiling the
thirteen 32-bit words at `table_start-52 .. table_start-4` across all 58 specimens,
**no word position holds a constant value**, and none equals the input count, the table
length, or the output count in more than a handful of files.

Three structural hypotheses were tested and **rejected**:

| hypothesis | test | result |
|---|---|---|
| Fixed 52-byte header with typed fields | per-word distribution over 58 specimens | no position constant; 11–46 distinct values each |
| Per-input descriptor array before the table | uids at fixed stride K ending at `table_start`, K = 4..40 | 0/58 for every K; most uids do not appear near the table at all |
| The block is a record-directory entry | `table_start`, `trail[6]`, `ptr`, `table_end` vs the 0x38 directory | 0/44 exact matches — the defaults always land *inside* the directory's final record, at a variable offset (+112 to +2280) |

Two positive observations survive:

- **The word at `table_start-4` is a system input's uid** — `$outputsize` in 28
  specimens and `$randomseed` in 3, so 31 of 58. Because those uids are random per file,
  uid-sorting puts them at one end or the other of the input list, and the matched entry
  is the first or last input in 30 of those 31 cases.
- **`0x0A420001` is a body-stream token, not an input-block marker.** It recurs at
  several offsets inside the region, but file-wide counts run from 10 to 4276 and
  correlate with neither input count (r = 0.23) nor output count (r = 0.35), and never
  equal either. It appears to be a common instruction encoding in the record stream.
  **[RESOLVED: it is two tokens — a length prefix `0x0001` and the `0x0A42` reference
  opcode, i.e. a one-instruction parameter expression. See "Record bytecode is
  length-prefixed".]**

Current reading: the defaults table is embedded near the end of the record stream's
final record, and both `0x2C` and `trail[6]` are expressed at a fixed 52-byte skew from
its two ends. The 52 is a real, exactly-held constant, but its referent is still
unidentified, and the bytes it spans are ordinary preceding stream content rather than a
dedicated structure. The earlier guess in these notes — a "fixed 52-byte input-block
header" — is not supported and should not be repeated.

### Multi-graph packages — solved

Earlier drafts reported multi-graph packages as unsupported, and tested two models that
both failed. Both were wrong about *scope*, not layout.

**The interface block is package-level.** There is exactly one per file — a footer scan
(below) finds one and only one candidate even in packages with 13 or 20 graphs. It
aggregates:

- `n_inputs` = the inputs of **every** graph, plus the package globals
- `n_outputs` = the outputs of **every** graph
- ordering = the same single **global uid-ascending** sequence, across graph boundaries

Verified on all 23 multi-graph specimens: the recovered `(n_out, n_in)` matches the
summed manifest counts 20/20 where checked directly, and the descriptor array is in
global uid order 20/20. With this, multi-graph packages validate identically to
single-graph ones and are no longer a special case anywhere in the tooling.

Models tested and **rejected** on the way: concatenated per-graph tables addressed by one
pointer (explains 3 of 23), and independent per-graph interface blocks (the footer scan
proves there is only one block per file).

### Corpus result

Sorting by uid and laying out per the widths above reproduces the table
**byte-for-byte across the whole corpus**:

```
specimens                 :  58    fully accounted for: 58/58
table entries             : 1289
byte-exact                : 1258  (97%)
within 1e-5 (%g rounding) :   31
unexplained               :    0
```

The 31 non-exact entries are all accounted for by manifest rounding (below). Nothing in
1289 entries across 58 files is unexplained.

## Why the mismatches — confirmed mechanism

**The XML `default` attribute is a lossy rendering. The binary holds the true f32.**

The manifest writes floats at six significant figures — the C `%g` default — which is
insufficient to round-trip an f32 (nine are required):

```xml
default="0.105882,0.0864706,0.0529412,1"
```

Reparsing `0.105882` yields `0.10588199645280838`, while the binary holds
`0.10588236153125763` — which is exactly `27/255`, an 8-bit sRGB colour component.
The binary preserves the artist's actual value; the manifest destroys it.

Measured decimal-place distribution across the corpus confirms the `%g` signature.
Roughly half of the observed colour components resolve to exact `n/255` values; the
rest are arbitrary artist picks, equally mangled by the same rounding.

### Practical consequences

1. **Prefer the binary defaults over the manifest's.** The table is not redundant with
   the XML — it is strictly more precise. This is the main practical reason to read it.
2. **Never compare with exact equality.** Use a relative epsilon of about `1e-5`.
   ULP-level tolerance is not enough: `%g` truncation produces errors far larger than
   one ULP (up to ~4e-7 relative), while genuine single-ULP differences also occur
   (`0.6` written as `0x3F199999` where `float(0.6)` is `0x3F19999A`).

## What must be in the file and has not been located

Reasoning from what the engine has to read, rather than from what turned up. Each item
below is provably present in the sources and provably necessary to cook a material, and
none of it has been found in the compiled form.

### 1. Filter-specific parameter values — the major gap

Every filter has its own parameters, and the `.sbs` sources declare them in quantity:

| filter | parameters the engine must read |
|---|---|
| `blend` | `blendingmode` (5,522 uses), `opacitymult`, `opacity` |
| `levels` | `levelinlow`, `levelinmid`, `levelinhigh`, `leveloutlow`, `levelouthigh` |
| `transformation` | `matrix22` (1,676), `offset`, `tiling`, `filtering` |
| `gradient` | `position`, `midpoint`, `value` — **51,801 uses each** |
| `uniform` | `outputcolor`, `colorswitch` |
| `blur`, `warp` | `intensity` |
| `shuffle` | `channelalpha`, `channelgreen`, `channelblue` |

**Worked example: `blendingmode` is not where it should be.** It has an unmistakable
signature — 7 distinct values across the corpus, 97% of them value 0 (`copy`). Nothing in
a blend record matches:

```
.sbs blendingmode :  7 distinct, 97% one value
record slot 1     : 19 distinct, 78% value 23
record slots 4-7  : 32-64 distinct, no dominant value
class word        : 10 distinct, 79% value 0x0019
```

Over 227,065 blend records, neither the slots nor the class word carries that
distribution. The same applies to `levels`' five curve points, `transformation`'s matrix,
and gradient's 51,801 colour stops.

Note what *is* known: nearly every record points at a small bytecode program (median 5
instructions), and the 48-byte parameter blocks hold programs for `$randomseed` and
`$outputsize`. So the mechanism for *driven* parameters is understood. What is missing is
where a **static** parameter value lives — the constant `blendingmode = multiply` that no
function computes.

## Five more filters named — including the fourth commonest

Enumerating every filter id that appears on a real record (class bit 3 set) showed **nine
unnamed ids covering 46,978 records, 7.2% of the corpus** — and one of them, `0x18`, is the
fourth most common filter in the format with 42,220 records across 239 of 382 specimens. It
had simply never been looked at.

Correlation against `.sbs` filter names is size-confounded and gave only weak leads. The
identifications below rest on **structure**: how many edge slots a record has, how many
float parameters, and what values those parameters take.

| id | records | name | evidence |
|---|---:|---|---|
| **`0x18`** | **42,220** | **`directionalwarp`** | 2 edge slots (`input1` + `inputgradient`), and two float parameters: slot 6 holds magnitudes (2.35, 25.7, 64.0) and slot 7 holds -0.25, 0.25, -0.5 — angles in turns, where 0.25 is 90 degrees |
| `0x26` | 1,782 | **`passthrough`** | exactly 1 edge slot and **no parameters**, in a 16-byte record — which is what a passthrough is |
| `0x1C` | 555 | **`hsl`** | three consecutive parameter slots clustered on 0.51, 0.49, 0.4, 0.53, 0.54 — hue, saturation and lightness, all neutral at 0.5 |
| `0x1A` | 931 | **`sharpen`** | one float parameter: 0.25 (72%), 1.2, 0.5 — an intensity |
| `0x10` | 405 | **`emboss`** | 2 edge slots and two parameters, slot 6 holding 10.0 and slot 7 holding 1, 0.25, 0.128 — intensity and angle |

The `hsl` case is the cleanest: three parameters in a row, all centred on 0.5, is what a
hue/saturation/lightness triple looks like and very little else does. `directionalwarp` is
the most valuable, being 6.5% of all records in the corpus.

## Byte coverage, and the curve tables

Auditing every byte of the record body against known structures — records, their bytecode,
and the parameter chains — gives a measured figure for how much of the format is understood:

```
body bytes over 147 specimens   68,081,356
accounted for                        87.16%   (instrument-dependent; ~85% is the
                                               defensible figure — see "A caution about
                                               the coverage figure itself")
unexplained                          12.84%
```

Following pointers only from record slots reaches 74.82%. Adding the pointers held inside
parameter-chain entries takes it to 87.16% — those entries own a substantial share of the
bytecode, which is consistent with their being parameter blocks.

### The remaining large gaps are curve tables

Gaps of 128 bytes or more have exact sizes:

```
1540 = 4 + 256 x 6        436 = 4 +  72 x 6
 388 = 4 +  64 x 6       1360 = 4 + 226 x 6
```

A `u32` header followed by **6-byte entries**, each `[u16 x][u16 y][u16 0x8000]`. Searching
the corpus for eight or more consecutive entries whose third field is `0x8000` finds 617
tables, and their contents settle what they are:

| property | result |
|---|---|
| x non-decreasing | **617 / 617 (100%)** |
| y non-decreasing | 552 / 617 (89%) |
| 64 entries | 550 tables |
| 256 entries | 28 tables |
| 10, 12, 16, 72, 107, 127, 130, 255 entries | 29 tables |

An x axis that never decreases across every table in the corpus is an index or position
axis; y follows it monotonically in 89% of cases and turns over in the rest, which is what a
tone curve does. The 64-entry form dominates; the 256-entry ones are full byte-indexed
lookup tables. The constant `0x8000` in the third field is presumably a fixed-point 1.0 or a
per-point weight left at its default.

These are the **array-valued parameters** listed earlier as missing — `curve`'s control
points and `gradient`'s position/value stops, which no fixed slot could hold. Their location
is now known even though the mapping from table to owning record is not: they sit in the
body between records, like bytecode blocks, and are presumably referenced by a pointer slot
in the same way.

### The tables are `gradient` ramps, pointed to from slot 3

Linking each table to the record that references it, searching only within the true record
extent:

```
tables found                              617
linked from a slot inside a record        572
owning filter                             gradient — 572 of 572, no exceptions
pointer slot                              slot 3 — 572 of 572
```

The 45 unlinked tables are in records whose extent detection failed, not counter-examples.

Table sizes by owner: 64 entries (511), 256 (25), 10 (18). So a `gradient` node stores its
colour ramp as a **sampled table of 64 points**, not as the handful of editable stops the
source shows — `position`, `midpoint` and `value` in the `.sbs` are resampled at compile
time into a fixed-resolution ramp. The 256-entry variants are full byte-indexed ramps.

**This corrects an earlier guess.** When the tables first appeared as unexplained gaps, the
structure — three arrays of monotonic pairs — suggested control points, and `curve` was
offered as the likely owner. It is not: every single one belongs to `gradient`. The
identification of type `0x2C` as `curve` rests on separate evidence and is unaffected, but
`curve` owns none of these tables.

An earlier attribution run that scanned 96 bytes from each record start reported owners
including `blend` at slots 18 and 19 — impossible, since a blend record is six slots. That
run was reading bytecode as record slots, the same boundary error as before. Restricting to
the true extent removed every spurious owner and left a result with no exceptions at all.

### Multi-graph packages

Thirty distinct specimens contain more than one graph — up to twenty, in `ie_curve` and
`ie_pcloud`. They are not concatenated files: each contains a **single** `SBAM` magic, one
record directory, and one interface block.

The interface block is package-level and aggregates every graph:

```
header n_out == sum of all graphs' outputs                     30/30
header n_in  == sum of all graphs' inputs + global inputs      30/30
```

The two apparent exceptions to the input count — `LGMLtools__fake_anim_curve` (8 graph
inputs, header says 9) and `substance-for-unity-extensions` (42, header says 43) — each
have exactly one package-level `<global><inputs>` entry, which accounts for the difference.

Records are a single flat pool shared by all graphs, at very different densities: 26
records per graph in `ie_curve`, 389 in `Unity_Shader_Labs__GAR`, 1,558 in
`LGMLtools__sRGB_colorchart`.

**Graph membership is not recoverable from the output array.** In 14 of 30 files the output
uid array is the graphs' outputs concatenated in declaration order, which would let a reader
partition them by cumulative output count; in the other 16 the same set appears in a
different order. So a reader can enumerate a package's outputs and inputs, but cannot tell
from the interface block alone which graph an output belongs to. Whether the association is
recoverable from the records themselves is untested.

### `fxmaps` slot 1 is the edge — and why the inheritance test failed on it

The disagreement between the optimiser and the structural test resolves in the optimiser's
favour, because the structural test does not apply to this filter.

**Slot 2 is the FX-Map tree pointer**, a forward reference, which is why it is a backward
record reference 0% of the time. Excluding it and counting backward references per `fxmaps`
record over 6,600 records:

```
1 reference   58%        commonest slot sets:  [1]      3,472
2 references  21%                              [1,5]      822
0 references  10%                              [1,4]      352
```

Slot 1 alone accounts for the majority, which matches `fxmaps` taking one input in the
common case, and slot 5 or 4 appears as a second input on a minority.

**The inheritance test was inapplicable.** It asks whether a record with slot-1 bit 3 clear
shares its resolution with the record it references, and that presumes the filter passes
resolution through. An FX-Map does not: it composites patterns onto a canvas of its own
size, so its output resolution is independent of its input. The 28% inheritance measured on
`fxmaps` slot 1 was therefore not evidence against it being an edge — the test simply has no
force for generators. The same caveat applies to `gradient`, `uniform` and `bitmap`, whose
edge slots were established by other means or are absent.

So the edge map is: **`fxmaps` slot 1** (with 4 or 5 as an occasional second input),
**`pixelprocessor` slot 2**, the latter confirmed independently at 96% backward and 76%
inheriting.

**A caveat on how this was nearly measured wrongly.** The intended cross-check was to
compare these counts against the number of connections each `fxmaps` node declares in its
`.sbs`. That produced figures like "5,435 inputs" for a single node, because the source was
split on `<compNode>` without bounding each chunk at its closing tag, so every node absorbed
the connections of everything after it. Those numbers are discarded; the finding above rests
on the binary side alone.

### `pixelprocessor` slot 2 is an edge — and the two methods disagreed

Two methods were applied to the blocked question, and they disagree.

**Optimisation against ground truth.** The 30 multi-graph specimens give a known graph
count, so slot combinations can be scored by how often connected components match it.
Searching all 1,681 combinations of up to three slots for each filter, the best score is
9/30 exact with a median components-to-graphs ratio of exactly 1.00, achieved by `fxmaps`
slot 1 with `pixelprocessor` slots 2 and 3 — and by eleven other combinations tied with it.

That is the best of 1,681 candidates evaluated on 30 points. The improvement from 3/30 is
real but the specific winner is not trustworthy at that ratio of hypotheses to data.

**Structural test.** Independent of the optimisation: within the true record extent, how
often does a slot hold a backward record reference, and — for records whose slot-1 bit 3 is
clear, which must inherit their resolution — how often does the referenced record have the
same resolution?

| filter | slot | backward | inherits |
|---|---|---|---|
| `pixelprocessor` | 1 | 99% | 23% |
| **`pixelprocessor`** | **2** | **96%** | **76%** |
| `pixelprocessor` | 3 | 28% | 67% |
| `fxmaps` | 1 | 74% | 28% |
| `fxmaps` | 6 | 10% | 94% |
| `fxmaps` | 7 | 11% | 93% |

A high backward rate alone means little — a small integer is usually less than the record's
own index. Inheritance is the discriminating signal, and it is what identified every edge
slot already confirmed.

**`pixelprocessor` slot 2 is an edge**: 96% backward and 76% inheriting, over 7,000
records. `pixelprocessor` slot 1, which the optimiser also liked, is 99% backward but only
23% inheriting — the profile of a counter, not an edge.

**`fxmaps` is not resolved.** Slot 1, the optimiser's choice, inherits only 28% of the time.
Slots 6 and 7 inherit at 94% and 93% but are backward references in only one record in ten,
which would be an edge present on a minority of nodes. Neither reading is strong enough to
record as fact, and the disagreement between the two methods is itself the finding: an
optimiser tuned on 30 points will happily select a slot the structural evidence contradicts.

### Slot-1 bits 6 and 8: two apparent hits, both spurious

Sweeping the remaining slot-1 bits against measurable record properties over 127,974 records
produced two strong-looking associations:

```
bit 6  carries a float parameter   78.3% vs 34.7%
bit 8  has two or more edges       75.9% vs 29.8%
```

Both dissolve under stratification by filter.

**Bit 6** is driven almost entirely by `transformation`:

```
transformation   80% vs  1%       blur       63% vs 63%
shuffle          59% vs 22%       gradient   11% vs 10%
levels           98% vs 80%       warp       78% vs 81%   (inverted)
```

Outside `transformation` and `shuffle` the bit tells you nothing about whether a record has a
parameter. It is a filter-specific flag whose aggregate signal comes from one filter being
both numerous and unusual.

**Bit 8** is worse — within every filter the two rates are the same:

```
blend            100% vs 100%     (n = 45,913)
warp             100% vs 100%
shuffle           78% vs  76%
```

Every `blend` record has two edges regardless of bit 8, and every `warp` record does too. The
aggregate difference came from filters differing in *both* their edge count and their bit-8
rate — the association was between filter and each variable separately, never between the two.

Neither bit is identified. This is the same pooling error that made `NN` look opaque, made
slot 2 look like "not an edge", and made the `00020008` chain look like a fixed table: a field
whose meaning is per-filter shows nothing, or shows something false, when measured across all
filters at once. The standing rule — stratify by record type before believing any
association — now has four instances behind it.

### Class-word bits 10-13 are a layout selector, used by six filters

The variant field carried in class-word bits 10-13 was recorded as "discrete small values,
`blur` takes 4/5/6, `warp` 8/10" without an interpretation. It selects the record's
**parameter layout**, and it is used by exactly the filters whose records vary in shape.

Measuring how well the record's size is predicted by the filter id alone, versus filter id
plus variant, over 136,091 records:

| filter | filter alone | with variant |
|---|---:|---:|
| `sharpen` | 46% | **96%** |
| `blur` | 58% | **87%** |
| `directionalwarp` | 55% | **79%** |
| `warp` | 46% | **76%** |
| `normal` | 47% | **75%** |
| `distance` | 50% | 58% |
| `blend` | 63% | 63% |
| `transformation` | 58% | 58% |
| `levels` | 57% | 57% |
| `pixelprocessor` | 52% | 52% |
| `uniform` | 47% | 47% |
| `gradient` | 35% | 35% |
| `fxmaps` | 28% | 28% |

For the six filters that use it the variant is close to determining the layout — `sharpen`
reaches 96%, `blur` 87%. For the rest it is zero and adds nothing, which is why the
corpus-wide figure moves only from 56.6% to 59.9%: the two commonest filters, `blend` and
`transformation`, do not use the field.

Using the **whole** class word rather than just bits 10-13 raises the corpus figure to 63.4%,
so other bits carry a little further layout information, but no single bit accounts for it.

**What this leaves.** Record size is still not predictable for `blend`, `transformation`,
`levels`, `gradient`, `fxmaps` and `pixelprocessor` — the filters whose parameter sets vary
most. For those, size must be recovered as it is now: by scanning forward for the first valid
bytecode block. That works and is what the reader does, but it means the format does not
declare a record's length anywhere a parser can read directly.

### Connected components do not recover graph membership

With `fxmaps` slot 1 and `pixelprocessor` slot 2 added, partitioning multi-graph packages by
connected component improves from 3/30 exact to 7/30, and the median components-to-graphs
ratio moves from 2.00 to 1.00. The median is misleading. Per specimen:

```
ie_pcloud                   20 graphs ->  2 components
SubstanceDesigner__hblend    6 graphs ->  1 component
substance-for-unity-ext     15 graphs -> 13 components
LGMLtools__msxcolors         3 graphs ->  3 components   exact
DLG-Tools__Camouflage       13 graphs -> 31 components
LGMLtools__sRGB_colorchart   4 graphs -> 73 components
```

Both failure directions occur at once, and the ratio of 1.00 is the average of them cancelling
rather than a sign of accuracy.

**Over-fragmentation** means edges are still missing — unsurprising, since `0x16` and several
rare filters have no edge map at all.

**Under-merging is the more interesting failure.** Twenty graphs collapsing to two components
means records are **shared between graphs**. That follows from what is already documented:
the compiler inlines sub-graphs and performs common-subexpression elimination across the
whole package, so two graphs that both use the same library filter can end up pointing at one
set of records. Graphs are therefore not disjoint subgraphs of the record pool, and no
partition of the records can recover them.

So the question "which graph does this output belong to?" is not answerable by connectivity,
and probably not from the record pool at all. If the association is recorded anywhere it will
be an explicit table, not a structural property — and none of the header, trailer, directory
or interface block has a field left unaccounted that could hold one.
### The trailer decoded

The last 28 bytes were recorded early on as seven words printed in hex and never analysed.
Over 382 specimens they resolve almost completely:

| word | meaning | agreement |
|---|---|---|
| 0 | per-file identifier | 330 distinct values over 382 files |
| 1 | small enumeration — values 0, 1, 2, 3, 4, 5, 8 | 48% are 8, 31% are 4 |
| 2 | per-file identifier | 299 distinct |
| 3 | pointer: 62% into the directory, 38% into the record body | 99% a valid `+52` pointer |
| **4** | **`dir_at - 52` — start of the record directory** | **100%** |
| **5** | **`dir_at + 4*count - 52` — end of the record directory** | **100%** |
| **6** | **`table_start - 52` — the value table** | **100%** |

Words 4 and 5 bracket the record directory and word 6 names the value table, so the trailer
is the file's **root pointer block**: everything needed to find the two top-level structures,
at a fixed offset from the end. A reader that starts at the trailer needs nothing from the
header except the magic.

Words 0 and 2 are mostly unique per file, but not entirely — `2AB04B76` and `7DC25D24` each
occur in 41 files, and 62 and 105 files respectively share a value with some other file.
That is the signature of an identifier inherited from shared source material rather than a
checksum over the file's bytes, which would be unique.

Word 1 takes only seven values and does not track the output count, the input count, or the
version. Unexplained.

### Header constants verified

The header fields recorded early as "const in all samples" were never checked against the
full corpus. They hold: `0x14` is `0000001C`, `0x18` is `0`, `0x20` is `00010002`, `0x24` is
`0`, `0x28` is `1`, `0x30` is `2`, `0x34` is `0` — each constant across all 382 specimens.
The variable fields are `0x04` (version, 7 values), `0x1C` (trailer pointer) and `0x2C`
(value-table pointer), all as documented.

### End-to-end validation, current state

`validate_corpus.py` checks the documented structure against every specimen: header
invariants, the graph-input default table decoded from the manifest, the interface block,
and the record directory. It now covers all corpus directories including `pairs4`,
`pairs5` and `pairs6`, deduplicates by content hash rather than directory name, and
reports unparseable manifests instead of aborting on them.

```
specimens (distinct)      383     (of which multi-graph: 30)
value-table entries     7,082
   byte-exact           6,993     98%
   within %g rounding      89
   unexplained              0
(n_out, n_in) header  383/383
output uid array      383/383
input descriptor array 383/383
trailing array footer 383/383
record directory      383/383
manifests unparseable     2
versions   v2 88, v3 5, v4 41, v5 193, v6 29, v8 6, v9 21
```

Every structural check passes on every specimen, and no value-table entry is unexplained.
The two unparseable manifests are XML the parser rejects, not format failures — the
`.sbsasm` files beside them parse normally.

The earlier figure of 493 specimens counted the same materials repeatedly; 383 is the
distinct population including the three pairs added after the specification was written.

### The region after the record body is fully accounted

An audit of the span from `table_start` to the trailer appeared to leave 27.5% unexplained,
but that was an arithmetic error on my part: `table_start` marks where the value table
*begins*, and the audit's formula counted only the interface block that follows it. The
region is `[value table][u16 n_out][u16 n_in][output uids][input descriptors][16-byte
footer]`, and the validator above confirms every part of it on all 383 specimens.

### Which record produces each output is not recorded in the binary

An importer needs to know which node feeds each output channel — which node is the base
colour, which the normal. Three routes were tried and all fail.

**By uid.** The interface block lists output uids. Searching all 382 specimens for each uid
anywhere else in the file: **2,193 occurrences, 100% of them inside the interface block**, and
not one inside a record. Records never mention output uids.

**By sink analysis.** If outputs were the graph's terminal nodes, the records nothing
references would number the outputs. They do not — the median ratio of sinks to outputs is
8.3, and `RoadSubstance002` has 5 outputs against 2,951 sinks. The sink population is
dominated by `pixelprocessor` (24%) and `0x16` (22%), the two filters with incomplete edge
maps, so most of those sinks are artifacts of what is still unknown rather than real
terminals.

**By position or kind.** No record kind has a count equal to the output count in more than
12% of files, and that best case is `bitmap` in resource-only packages. The last *n* records
in directory order are a mixture — `blend` 32%, `transformation` 14%, `levels` 12%.

So the association is absent from the compiled file, in the same way graph membership is
absent for multi-graph packages. This is not a gap in the analysis but a property of the
format.

**What a reader can do instead.** For packages that ship baked resources, the resource
records are one per output and in output order — established earlier at 30 of 41 files with
exact agreement, the disagreements being scanner misses. That gives the images directly
without needing the graph. For purely procedural packages the association exists only in the
`.xml` manifest, which travels in the same archive and names each output with its identifier
and usage.

### Channel-mode propagation, and what it confirms

The same comparison for colour mode — does a record's grayscale/colour flag match the record
it takes input from:

| filter | n | same | gray -> colour | colour -> gray |
|---|---:|---:|---:|---:|
| `blend` | 85,607 | **100%** | 0% | 0% |
| `transformation` | 66,693 | **100%** | 0% | 0% |
| `levels` | 24,589 | **100%** | 0% | 0% |
| `directionalwarp` | 14,667 | **100%** | 0% | 0% |
| `warp` | 7,313 | **100%** | 0% | 0% |
| `blur` | 4,242 | **100%** | 0% | 0% |
| `passthrough` | 682 | **100%** | 0% | 0% |
| `distance` | 535 | 99% | 1% | 0% |
| `pixelprocessor` | 11,451 | 90% | 8% | 2% |
| `curve` | 287 | 90% | 1% | 9% |
| `fxmaps` | 8,528 | 87% | 0% | 13% |
| `gradient` | 5,406 | 85% | **15%** | 0% |
| `shuffle` | 1,898 | 33% | 12% | **55%** |
| **`normal`** | 364 | **0%** | **100%** | 0% |

**`normal` converts grayscale to colour in 100% of cases, without exception.** A normal-map
filter takes a height field and emits an RGB normal, so this is exactly what the filter's
name promises — and it is independent confirmation of that identification, which rested on
count correlation and a single float parameter.

`gradient` turning grayscale into colour 15% of the time is a gradient *map* colourising a
mask. `shuffle` changing mode in two thirds of cases is channel rearrangement doing what it
is named for, and its 55% colour-to-grayscale is the `grayscaleconversion` behaviour already
identified from the weight vectors. `fxmaps` reducing colour to grayscale 13% of the time is
consistent with pattern splatting into a mask.

Seven filters never change channel mode at all, over 200,000 edges. Combined with the
resolution rules, a reader can propagate both geometry and channel mode through most of a
graph without reading a single parameter.

### Resolution propagation is a per-filter property

Comparing each record's resolution against the resolution of the record it takes input from,
over 232,000 edges:

| filter | n | preserves input resolution | resizes |
|---|---:|---:|---:|
| `blend` | 85,607 | **100%** | 0% |
| `levels` | 24,589 | **100%** | 0% |
| `gradient` | 5,406 | **100%** | 0% |
| `blur` | 4,242 | **100%** | 0% |
| `shuffle` | 1,898 | **100%** | 0% |
| `distance` | 535 | **100%** | 0% |
| `normal` | 364 | **100%** | 0% |
| `directionalwarp` | 14,667 | 99% | 1% |
| `warp` | 7,313 | 95% | 5% |
| `pixelprocessor` | 11,451 | 74% | 26% |
| `transformation` | 66,693 | 44% | **56%** |
| `curve` | 287 | 49% | 51% |
| `fxmaps` | 8,528 | 27% | **73%** |
| `passthrough` | 682 | 2% | **98%** |

Seven filters never change resolution at all, across tens of thousands of edges. That is a
hard rule a reader can rely on: if a node is a `blend`, `levels`, `gradient`, `blur`,
`shuffle`, `distance` or `normal`, its output geometry equals its input's, and the
resolution field need not even be read.

**`passthrough` resizing 98% of the time** identifies what it is for. A pass-through that
changes resolution is a resampler — the compiler's way of inserting a resize without
attaching a transform matrix.

**`transformation` resizes just over half the time**, which matches the reconstruction
finding that the binary contains more `transformation` nodes than the source: some are the
artist's transforms, others are compiler-inserted resizes. Which is which is visible
directly — a transformation whose resolution equals its input's is doing something other
than resizing.

The pattern by what feeds them supports this: transformations fed by `shuffle` resize 93% of
the time, by `uniform` 83%, by `levels` 75% — all filters that cannot resize themselves, so
a size change downstream of them needs an inserted node.

### The three rare filter ids, profiled and closed

`0x0A`, `0x22` and `0x12` together account for 176 records — 0.03% of the corpus. Their
structural profiles, for whatever a future reader with more specimens can do with them:

| id | records | files | record sizes | mode | backward-ref slots |
|---|---:|---:|---|---|---|
| `0x0A` | 119 | 5 | 12 B (70), 76 B (5), 6 B (4) | 118 gray, 1 colour | slot 4 (6), slot 18 (5) |
| `0x22` | 52 | 11 | 36 B (18), 32 B (12), 24 B (3) | all grayscale | slot 2 (36), slot 1 (20), slot 6 (18) |
| `0x12` | 5 | 4 | 24 B (3), 28 B (2) | all grayscale | slots 1, 2, 3 (5 each) |

`0x0A` has almost no backward references across 119 records, so it is a generator rather
than a transform, and it is grayscale in 118 of 119 cases. `0x22` — provisionally `text` on
a size-controlled correlation of +0.517 — takes an input at slot 2 in 36 of 52 records.
`0x12` appears five times in four files and references slots 1, 2 and 3 in every one, so it
takes three inputs.

None can be identified from five to eleven specimens, and the correlation methods that named
the other eighteen filters need more occurrences than these have. They are recorded as
profiled rather than unknown: a reader encountering one knows its arity and channel mode even
without its name, which is enough to walk past it without breaking the graph.

### What fills the gap between records

Decomposing the span from each record to the next, for the 208,906 records whose bytecode
could be located:

```
record + bytecode fills the gap exactly     42.1%
padded by 2 bytes                           21.2%
further data follows                        36.1%
overlaps the next record                     0.5%
```

Nearly two thirds are `[record][bytecode]` with at most a 2-byte alignment pad. Of the
remainder, the commonest leftover is **exactly 64 bytes** (16.9% of all records) — the size
of a `0x1A80` parameter block — so the "extra" is usually a chain entry, not unknown data.
Leftovers of 8, 10, 40, 42 and 44 bytes account for most of the rest and match other chain
entry sizes.

**This gives the reader a defensible fallback for records with no bytecode.** Their gaps to
the next record are 20 bytes (23%), 36 (20%), 16 (18%), 12 (12%), 28 (8%), 24 (6%) — the same
values that records with bytecode are measured at. So for a record where no program follows,
taking the gap as the extent is consistent with every observed record size, where the
header-based prediction is right only 69% of the time.

That does not make the extent certain — a trailing chain entry would be absorbed into it —
but it is bounded by a real structure rather than guessed, and it is correct whenever the
record is followed immediately by the next.

### Record length is genuinely not encoded

The reader locates a record's end by scanning for the first valid bytecode block after it,
which fails for the 13.8% of records that carry no program. The obvious fallback is to
predict the length from the record's own header. Built as a lookup table on half the corpus
and tested on the other half, over 273,908 records with a measured extent:

| predictor | exact |
|---|---:|
| filter id | 61.8% |
| filter + variant (class bits 10-13) | 64.6% |
| filter + variant + colour flag | 65.7% |
| filter + full class word | 68.3% |
| filter + class word + colour flag | 69.3% |

The best available predictor, a 302-entry table keyed on everything the header offers, is
right 69% of the time. Adding fields buys diminishing returns — the whole class word over
just its variant nibble is worth four points.

So the header does not determine record length, and this settles a question that has been
implicit throughout: **the format encodes a record's length nowhere**. Not in a length field,
not in the class word, not in the directory, which stores only start offsets. A record's
extent is recoverable only by decoding what follows it.

That is why the "record size" error recurred: with no declared length there is nothing for a
wrong assumption to contradict, so treating the gap to the next record as the record's size
produced plausible-looking results for a long time. It also bounds what any reader can do —
for a record with no bytecode, the parameters cannot be located with certainty, only guessed
at 69%.

### Byte coverage, final measurement

The coverage figure has been quoted at 74.82%, 82.46% and 87.16% depending on which pointer
sources the audit followed, and was flagged as instrument-dependent. Re-measured with every
correction applied — corrected edge map, true record extents, gradient tables, and chain
entry pointers — over 38.2 million body bytes in 100 specimens:

| category | bytes | share |
|---|---:|---:|
| bytecode | 17,966,100 | 47.07% |
| record bodies | 14,970,978 | 39.22% |
| gradient ramp tables | 22,494 | 0.06% |
| **unaccounted** | 5,212,596 | **13.66%** |
| **accounted for** | 32,959,572 | **86.34%** |

The breakdown is more informative than the total. **Bytecode is the single largest thing in
a `.sbsasm`** — nearly half the record body is compiled parameter programs, more than the
records themselves. That is not obvious from the format's structure, where bytecode appears
as an attachment to records.

The 13.66% unaccounted is dominated by the parameter-chain entries, which occupy about 2% of
the body directly and whose pointers are followed here but whose own bytes are not counted as
a category, plus inter-record fill and blocks not reachable from any record slot.

**86.34% is the defensible figure**, and it should be quoted with its method: intervals
merged from record extents, bytecode blocks reachable from record and chain pointers, and
gradient tables located by signature. Quoting a coverage percentage without stating what was
followed is what produced the earlier 12-point spread.

## The operation-by-type matrix

The catalogue lists one row per (type, operation) pair, and its row count has been quoted as
the number of operations. It is not: **45 distinct operation ids occupy 68 type cells**, of
which 37 appear in 20 or more specimens. Measured over 6.2 million instructions from 200
distinct specimens.

The matrix shows clear type discipline:

**Boolean only** — the comparisons and logic: `and`, `or`, `not`, `eq`, `gt`, `gteq`, `lt`,
`lteq`. None appears in float or int form.

**Float only** — every transcendental and geometric operation: `abs`, `floor`, `ceil`, `cos`,
`sin`, `sqrt`, `ln`, `exp2`, `atan2`, `cartesian`, `lerp`, `rand`, `samplelum`, `samplecol`,
`max`, `dot`.

**Float and int** — the arithmetic core: `add`, `sub`, `mul`, `div`, `mod`, `neg`, `min`, and
the structural operations `const`, `get`, `set`, `vec`, `swizzle`, `conv`, `ifelse`,
`sequence`, `inputref`.

Counts make the asymmetry visible. `div` is 94,128 float against 227 int; `neg` is 204,795
against 27; `min` is 32,601 against 9,801 but `max` is float-only. So several operations that
*can* take an int form almost never do — which is why the earlier catalogue, built from what
had been observed at the time, listed them as float-only and produced a 0.09% "uncatalogued"
residue consisting almost entirely of their rare int uses.

Two ids remain unnamed: `0x35` (17 instructions) and `0x3F` (8), both float, both in fewer
than nine specimens. Neither reaches the 20-specimen threshold that separates operations from
decode residue, and `0x3F` is the `153F` opcode already withdrawn as an artifact.

**So the instruction set is 45 operations**, 43 of them named, in 68 type-specific forms.

### Opcode coverage re-measured: 99.9%, not 96.5%

The figure of "96.5% of instructions carry an operation id catalogued for their type" does
not survive re-measurement. Decoding by walking records to their bytecode over 200 distinct
specimens:

```
first block per record            6,217,752 instructions   uncatalogued 427   (0.007%)
all blocks reachable from slots   9,979,237 instructions   uncatalogued 8,865 (0.089%)
```

**Coverage is 99.91% to 99.99%**, and no uncatalogued opcode appears in 20 or more specimens
under the stricter mode. The earlier 96.5% came from an identical-looking measurement whose
catalogue table was parsed before later edits to `OPCODES.md` added rows; it understated
coverage by three points.

The residue is not unknown operations. Of the 427 uncatalogued instructions in the strict
mode, the largest groups are **operations already named, appearing in a type the catalogue
did not list them for**:

| opcode | count | files | reading |
|---|---:|---:|---|
| `0A15` | 227 | 6 | `div` as int; catalogued for float |
| `0617` | 27 | 3 | `neg` as int; catalogued for float |
| `0842`, `0C42` | 10 | 4 | input reference as bool; catalogued for float and int |

So roughly two thirds of the residue is the type-by-operation table being narrower than
reality — an operation used in a type it was not observed in when the table was built. The
remainder are scattered singletons in one to eight files each, consistent with decode
residue.

**The operation set is complete and its coverage is essentially total.** What is slightly
incomplete is the record of which *types* each operation appears in.

### The resource-descriptor predicate: audited and sound

`valid_tag` filters on values — format code in {1,2,3,5,7,8}, depth in {0x08,0x18}, flag in
{0x20,0x21} — which is the same shape as the `0xAA` marker that hid every non-1024-square
resource. It was checked for the same defect and is sound.

```
files with descriptors                 97
descriptors accepted (strict)         523
segments tiled exactly            97 / 97
extra candidates if relaxed        33,043
```

**The strict set tiles every segment exactly, in all 97 files.** That is an independent
completeness constraint: a missing descriptor leaves a gap the sizes cannot cover, and a
false one overlaps its neighbour. Passing it means the predicate is neither too tight nor too
loose.

The 33,043 candidates admitted by relaxing it carry arbitrary bytes where the format, depth
and flag should be — format code 0 (24,675 times), depth 25 (22,529), flag 30 (12,839). They
are ordinary records whose slot happens to hold a small value.

**What separates this from the `0xAA` failure** is not the strictness of the predicate but
the presence of a check on its output. The marker test had no completeness constraint, so a
byte that excluded three quarters of all resources produced a result that looked clean — 41
files with tables, the rest simply "table-less". The descriptor test has tiling, and tiling
would have failed loudly the moment the format set was wrong.

So the rule from the float-range bug refines: a value-based filter is not inherently
dangerous. It is dangerous when nothing downstream can detect that it discarded something.
Where the output must satisfy an independent constraint — tiling a segment, decoding to a
declared length, summing to a known total — the filter is self-checking and can be trusted.

### Auditing the other thresholds

Having found the float-range predicate silently excluding every parameter of magnitude 8 or
more, the other caps in the method were checked for the same defect.

**The 400-byte extent scan.** A record's end is found by scanning forward for a bytecode
block, and the scan stops at 400 bytes. Of ~21,770 records whose gap to the next record
exceeds 400 bytes, **187 (0.9%)** have their extent only beyond that point. A real blind spot
but a small one, and it affects extent precision rather than any structural claim.

**The 20,000-instruction block cap.** `blk()` rejects a declared instruction count above
20,000. Scanning without the cap, 2 genuine blocks in 60 specimens exceed it, together
42,364 instructions, and they decode cleanly — 99.6% of their opcodes carry a catalogued
operation id. The cap is barely binding.

(An intermediate count of 2,195 oversized blocks was wrong: it scanned every 4-byte position
without excluding the interiors of blocks already found, so a single long block was counted
once per word inside it.)

**Conclusion of the instrument audit.** Three predicates were examined; one was materially
wrong. The float range hid `normal`'s intensity, `distance`'s distance and `curve`'s twelve
control points across the whole project. The two caps cost 0.9% of extent precision and two
blocks respectively.

The distinguishing feature of the bug that mattered is that it filtered on **value** rather
than on **structure**. A cap on length or scan distance fails loudly — a record simply has no
extent, and the failure is counted. A predicate that silently reclassifies a float as "not a
float" produces a confident, complete-looking answer with a hole in it. Value-based filters
deserve more suspicion than bounds.

### A bug in the float test, and what it hid

Every parameter sweep in this document used the same predicate to decide whether a word is a
float:

```python
0x2E000000 < k < 0x41000000
```

`0x41000000` is **8.0**. The test therefore excluded every parameter of magnitude 8 or more,
throughout. It was written to keep the false-positive rate low — large float bit patterns are
easily confused with pointers — and the cost was invisible because most Substance parameters
are in 0..1.

What it hid:

* **`normal`'s `intensity`** clusters on 8, 12, 16 and 20 — every one at or above the cut-off.
  The parameter was found earlier only because that investigation printed raw values rather
  than filtering them.
* **`distance`'s `distance`** takes 1.28, 12.8, 32 and 256. Only the small values passed.
* **`curve`'s control points** at slots 12-17 of its 72-byte form and slots 12-23 of its
  96-byte form — twelve floats, the largest parameter block of any filter, entirely missed.

Re-run with the range widened to 1e-5..1e6 and both signs, and with edge and pointer slots
excluded rather than filtered by value:

```
curve      72B  slots 12-17   six floats
curve      96B  slots 12-23   twelve floats
distance   24B  slot 5        1.28 / 32
```

`curve` carrying twelve floats in its largest form is consistent with the structure noted when
type `0x2C` was tentatively identified: three arrays of six, read then as "control points with
weights". That identification rested on a size-controlled correlation of +0.518; the parameter
block now gives it independent structural support.

**The general point.** A detector tuned to avoid false positives will hide whatever sits
outside its window, and nothing in the output indicates the window exists. This one ran across
every filter, every size, for the length of the project. The `sharpen` edge error, the
modal-size trap and this cut-off are three instances of the same failure: a method applied
uniformly, whose blind spot is uniform too, and therefore invisible in any comparison between
filters.

### What the non-float filters grow with

Four filters get larger without acquiring float parameters. Classifying every slot of their
largest common record shows what the extra words hold:

**`pixelprocessor`** at 32 bytes — slots 5, 6 and 7 are **all bytecode pointers**, at 99-100%.
Its records grow by acquiring more programs, which is exactly right for a filter whose
parameter *is* a per-pixel function. A `pixelprocessor` with three programs is three pixel
functions, not three numbers.

**`fxmaps`** at 72 bytes — slot 17 is a bytecode pointer at 100%, and slots 6 through 16 point
into the record body, mostly at chain entries. Its growth is references to the FX-Map tree
and its parameter blocks.

**`gradient`** at 44 bytes — slot 4 is a bytecode pointer at 100%, slot 3 points at the ramp
table, slots 2 and 5 hold record indices at 99% and 91%.

So the earlier reading was right in substance: `pixelprocessor` has no float parameters at any
size because its parameters are programs. The general statement is that **a record's extra
words are either values or references, and which one a filter uses is a property of the
filter** — `levels` grows with floats, `pixelprocessor` grows with programs, `fxmaps` grows
with structure pointers.

That also means record size alone cannot tell a reader how many parameters a node has. It
tells how many *slots* follow the header; what those slots contain depends on the filter, and
must be read from the slot values themselves.

### Record size and what fills it

Sweeping every filter at every record size, and counting float-valued slots outside the edge
map, makes the layout rule quantitative:

```
levels           16B 0.01    20B 0.97    24B 1.83    28B 2.80    32B 3.17   floats per record
transformation   16B 0.00    20B 0.00    24B 0.38    32B 1.89    36B 1.94
uniform           8B 0.00    12B 0.69    24B 2.13
fxmaps           28B 0.70    36B 1.07    40B 1.80
warp             20B 0.89    24B 0.93    28B 1.36
pixelprocessor   20B 0.00    24B 0.00    28B 0.00   32B 0.00
```

`levels` is the clearest case, rising from 0.01 floats at 16 bytes to 3.17 at 32 — close to
one more parameter per additional 4 bytes.

**But the rule is filter-specific, not general.** Measuring the slope in float parameters per
4 additional bytes, using each filter's smallest common record as its header:

```
levels 0.75    directionalwarp 0.67    blur 0.53    uniform 0.53    transformation 0.48
blend  0.36    sharpen 0.25    warp 0.23    shuffle 0.18    gradient 0.08
normal 0.07    fxmaps 0.03    pixelprocessor 0.00
```

Only five filters approach one float per word. `fxmaps`, `gradient`, `normal` and
`pixelprocessor` grow in size while adding almost no float parameters, so their extra bytes
hold pointers or integers instead. Generalising from `levels` to a universal
"length = header + 4 x parameters" would have been wrong.

The header sizes are useful regardless — the smallest common record per filter runs from 8
bytes (`uniform`) through 12 (`shuffle`), 16 (`levels`, `transformation`, `blur`, `sharpen`),
20 (`blend`, `warp`, `gradient`, `normal`, `pixelprocessor`) to 24 (`fxmaps`, `distance`,
`directionalwarp`).

This explains why sweeping each filter at its *modal* size found nothing for `blend`,
`transformation`, `uniform` and others — their commonest variant is the one with no
parameters at all. `transformation` is 16 bytes in 26,569 records and carries no floats;
its `matrix22` lives in the 32- and 36-byte variants, which are a fifth as common. A sweep
that looks only at the most frequent layout will systematically miss the parameters of any
filter whose default is to have none.

**`pixelprocessor` carries zero floats at every size**, from 20 to 32 bytes, across 7,377
records. That is consistent with what it is: its parameter is the per-pixel function itself,
held as bytecode, so there is nothing to store in the record. A filter with no float
parameters at any size is evidence about the filter, not a gap in the sweep.

### Systematic edge-slot audit: three more errors

Having found `sharpen`'s edge slot wrong by auditing one filter, the same test was applied to
every slot of every filter — backward-reference rate, and resolution inheritance for
bit-3-clear records. Three more entries were wrong in the same way:

| filter | documented | backward | inherits | correct slot | backward | inherits |
|---|---|---:|---:|---|---:|---:|
| `hsl` | slot 2 | **0%** | — | **slot 1** | 100% | 100% |
| `curve` | slot 2 | 100% | 46% | **slot 1** | 100% | 100% |
| `passthrough` | slot 2 | 100% | 3% | **slot 1** | 100% | 100% |

`hsl` is the clearest: its documented slot holds a backward reference in **none** of 155
records, while slot 1 holds one in every one of 168 and inherits resolution in all of them.

With `sharpen` corrected earlier, the filters whose edge is at **slot 1** are now `blur`,
`gradient`, `sharpen`, `hsl`, `curve` and `passthrough` — and every one of them is
single-input. The multi-input filters (`blend`, `warp`, `distance`, `emboss`,
`directionalwarp`, `shuffle`) put their first edge at slot 2. `levels` and `normal` are
single-input and use slot 2, so the pattern is a tendency rather than a rule, but it is strong
enough that a single-input filter documented at slot 2 should be treated as suspect.

**One undocumented slot also appears:** `transformation` slot 5 holds a backward reference in
73% of 9,808 records. Its inheritance cannot be tested — `transformation` resizes by design —
so it is recorded as a probable second input rather than confirmed. **RETRACTED — see
"`transformation` slot 5 is not an edge" below.** The 73% is an artefact of small integers,
and most `transformation` records are too short to contain a slot 5 at all.

**Why four errors of the same kind survived.** The original edge map was built by correlating
slot values against record index, which identifies *a* slot carrying indices but does not
distinguish the input edge from other index-valued fields. The inheritance test discriminates
between them, and was applied filter-by-filter only where a result looked doubtful. Applying
it to every slot of every filter — 33 slot-filter pairs above the noise threshold — took one
query and found three errors that had stood for the length of the project.

### An error in the edge map: `sharpen`

Auditing where edge resolution fails, rather than accepting the pooled 96-98% figure, found
the failures concentrated rather than scattered:

```
sharpen           375 records,   0 resolve at slot 2   (100% failure)
fxmaps          2,444 records unresolved  (23.1%)
pixelprocessor    444 records unresolved   (3.7%)
```

**`sharpen`'s edge slot was recorded as slot 2 and is slot 1.** Slot 2 holds a backward
reference in 0% of records; slot 1 holds one in **100%**, and those references inherit
resolution in **100%** of the 197 testable cases. The error put `sharpen` alone among filters
in having no resolvable input at all, when in fact it belongs with `blur` and `gradient`,
whose edges are also at slot 1 — a grouping the corrected value makes obvious.

`fxmaps` takes secondary inputs at slots 3, 4 and 5 in addition to slot 1 — each a backward
reference in 13-31% of records, with 52-73% inheritance. `pixelprocessor` uses slot 1 as well
as slot 2, though slot 1's 26% inheritance marks it as the weaker of the two.

With the corrected map:

```
edge resolution   531,088 / 540,544   98.25%   as documented
                  283,004 / 284,766   99.38%   corrected
```

The residue is `fxmaps` (1,308), `hsl` (248) and `pixelprocessor` (205) — filters with
optional inputs rather than missing slots.

**How the error survived.** Edge resolution was quoted as a single corpus-wide percentage,
and 96% sounds like a rule with exceptions rather than one filter failing completely. Only
breaking the figure down by filter made a 100% failure visible. The same audit applied to
slot-1 bit 3 turned a suspected weakness into a scoping correction; applied here it found a
straightforward mistake. A pooled percentage hides both.

### Slot-1 bit 3, correctly scoped

The holdout put the bit-3 rule at 94-96% against a corpus figure of 99.4%, which looked like
an overstatement. It was a scoping error instead, and correcting it makes the rule stronger.

Failures are concentrated entirely in the filters that resize by their own operation:

```
fxmaps           71.8% of bit-3-clear edges violate the rule
transformation   74.7%
passthrough      96.7%
curve            53.5%
pixelprocessor   23.8%
warp             15.1%
blend, levels     0.0%
```

Splitting the corpus on that basis, over 383,546 bit-3-clear edges:

| filter class | edges | inherits input resolution |
|---|---:|---:|
| **non-resizing** (`blend`, `levels`, `gradient`, `blur`, `shuffle`, `distance`, `normal`, `directionalwarp`, `sharpen`, `hsl`, `emboss`, `uniform`, `bitmap`) | 311,515 | **99.90%** |
| resizing (`transformation`, `fxmaps`, `passthrough`, `curve`, `pixelprocessor`, `warp`) | 72,031 | 61.39% |
| pooled, as previously stated | 383,546 | 92.67% |

**For a filter that does not resize, bit 3 clear means the resolution is inherited, at
99.90% over 311,515 edges.** For a filter that does resize, the bit says nothing about
resolution, because the geometry comes from the filter's own operation rather than from its
input — which is exactly what one would expect.

The earlier figure mixed the two populations. The holdout files happen to be `fxmaps` and
`pixelprocessor` heavy, which is why they scored lower: they contain proportionally more of
the class the rule was never about.

So the correction is not that the rule is weaker than claimed, but that it applies to a
narrower and precisely identifiable set of filters — and within that set it is close to
absolute.

### The later findings, tested out of sample

The three `pairs6` specimens were used as a holdout early, before most of what followed was
established. The filter table, the propagation rules, the parameter slots and the FX-Map
tree were all derived afterwards, so those specimens are still untouched evidence for them.

| check | SBRustyTreadPlate | UHL3D Sand | Wood_Planks |
|---|---|---|---|
| records | 4,508 | 3,317 | 666 |
| filter identified | 100.0% | 99.8% | 100.0% |
| **never-resize rule** | **2118/2118** | **1550/1550** | **431/431** |
| **channel-mode rule** | **3722/3722** | **2629/2629** | **612/612** |
| slot-1 bit 3 rule | 96.3% | 94.4% | 96.0% |
| `fxmaps` records with a tree at slot 2 | 120 | 99 | 19 |

**The two propagation rules hold without a single exception** across 8,000 edges in files
that played no part in deriving them. Seven filters never change resolution and seven never
change channel mode — stated on the corpus, confirmed on unseen data.

Filter identification is *higher* than the 98.3% corpus figure because none of these files
uses `0x16`, which accounts for nearly all corpus-wide misses. The six unidentified records
in `UHL3D` are the rare ids.

**Slot-1 bit 3 comes in lower** — 94-96% against 99.4% on the corpus. This turned out to be
a scoping error rather than an overstatement; see "Slot-1 bit 3, correctly scoped" above. The rule is that a
record with bit 3 clear inherits its input's resolution, and here it fails for one record in
twenty. That is a real if modest overstatement of the corpus figure, and worth recording:
the rule is strong but not absolute, and a reader should treat inherited resolution as a
default to verify rather than a guarantee.

## Reader completeness

How much of the corpus the description actually accounts for, measured by running the reader
over every distinct specimen:

```
specimens parsed              382 / 382      no failures
records encountered           651,743

filter identified             640,587    98.3%
filter not identified          11,154     1.7%
not a record (class bit 3 clear)    2     0.0%

of the identified records:
   extent found               552,478    86.2%
   extent not found            88,109    13.8%

of those with a known extent:
   edges resolved             532,797    96.4%
   source node, no edges expected 8,718    1.6%
   no edge found               10,963     2.0%
```

**Filter identification is 98.3%**, and the shortfall is almost entirely one filter: `0x16`
accounts for 10,978 of the 11,154 unidentified records. The rest are the three rare ids —
`0x0A` (119), `0x22` (52), `0x12` (5). `0x16` is reachable only through inlined Substance
library graphs, so naming it needs sources this project has deliberately excluded.

**Edge resolution is 96.4%** of records whose extent is known, with a further 1.6% correctly
having no edges because they are source nodes. The residual 2.0% are records whose edge slots
hold no backward reference, concentrated in the filters whose edge maps are partial.

**The 13.8% with no extent** is a limitation of the method rather than missing knowledge. A
record's end is found by scanning for the first valid bytecode block after it, and a record
with no bytecode at all has no such marker. Between 5% and 28% of records legitimately carry
no program depending on filter, which is the same population. For those, the extent is
bounded by the next record's start and the parameters cannot be located precisely — the
format declares record length nowhere.

## End-to-end reconstruction against source

The strongest available test of the whole description: rebuild a graph from the binary —
nodes, filter identities, colour mode, resolution and edges — and compare it to the `.sbs`
that produced it. Run on all 26 instance-free pairs, so inlining cannot confuse the counts.

`st_wood_fine_20` reconstructs exactly:

```
#   filter          mode    resolution   inputs
0   bitmap          gray    1024x1024    -
1   transformation  gray    256x256      [0]
2   bitmap          colour  1024x1024    -
3   transformation  colour  256x256      [2]
...  (seven bitmap -> transformation pairs)
```

Seven texture channels, each loaded at 1024 square and resized to 256 — which is what the
source says, and the filter multiset matches exactly.

Across all 26 pairs:

```
filter multiset matches exactly     13/26
total filter nodes   .sbs 133   binary 170   ratio 1.28
```

**The disagreements are entirely `bitmap` and `transformation`.** Every other filter matches
in every file where it appears:

| filter | files where the count matches |
|---|---|
| `fxmaps` | 6/6 |
| `levels` | 5/5 |
| `pixelprocessor` | 10/10 |
| `transformation` | 3/6 |
| `bitmap` | 9/19 |

and the binary always has *more* of them, never fewer. That is the compiler inserting nodes
the artist did not place: a `bitmap` to hold each embedded resource, and a `transformation`
wherever an output's size differs from its input's. `SubstanceDesigner__color` has 8 filter
nodes in source and 17 in the binary, all of the excess being those two kinds.

So the reconstruction is faithful for every node the artist placed, and the residual is
explained rather than unaccounted. A reader building a node graph from a `.sbsar` will see
resize and resource-load nodes that do not appear in the original graph — which is correct
behaviour for a compiled artefact, but worth knowing if the graph is being presented to a
user as though it were the artist's.

## The FX-Map tree, found

Walking the chain from each `fxmaps` record's slot 2 as a graph rather than a list shows it
branches. Over **5,653 trees and 45,534 nodes**:

### Node roles are determined by size

| size | 0 children | 1 child | 2 children | role |
|---|---:|---:|---:|---|
| 8 B | 23% | 77% | — | link |
| 12 B | 3% | 67% | **30%** | **branch** |
| 16 B | 7% | 93% | — | link |
| 20 B | 99% | — | 1% | leaf |
| 44 B | **100%** | — | — | leaf |
| 56 B | 99% | 1% | — | leaf |

Overall 61% of nodes have one child, 25% none, 13% two. The 12-byte entries are where the
tree branches; larger entries are always leaves.

### Leaves carry the parameter programs

Nodes of 48 bytes or more hold two to four bytecode pointers — 1,823 with three programs,
1,025 with two, 265 with four. These are the parameter blocks already decoded, whose
programs compute `$randomseed` and `$outputsize`.

Their first word is **not a tag**: in 3,150 of 3,160 cases it is an address inside the
record body, against 10 that are not. That is why the reachable entry set appeared to have
4,471 distinct "tags" — most were addresses, one of them the owning `fxmaps` record itself.

### Depth

Tree depth runs from 0 to beyond 12, spread across the range (553 trees of depth 0, 863 of
depth 8, 401 of depth 12 or more). A structure with branching nodes, leaves carrying
parameters, and depths in the tens is a tree, not a list.

### The tree's nodes do not correspond one-to-one with source tree nodes

With node roles known, the natural test is whether binary **leaves** — the nodes carrying
parameter programs — match the `<paramsGraphNode>` entries in the source. They correlate
+0.677 across 34 paired files, better than any earlier comparison, but the three
instance-free specimens rule out an identity:

```
Clouds_Animated    22 paramset nodes -> 3 leaves, 0 branches
Clouds_2           21 paramset nodes -> 3 leaves, 0 branches
BnW_Spots          19 paramset nodes -> 0 leaves, 0 branches
```

All three FX-Maps are built entirely of `paramset` nodes, and they produce almost no leaves.
`ie_curve`, with 43 `paramset` and 47 `addnode` nodes, produces 74 leaves and no branches;
`Hard-Science-Old__nightmare`, with 23 source nodes, produces 47 leaves and 26 branches.

So the compiler does not emit one binary node per source node. A `paramset` — which sets
parameters for the subtree below it rather than drawing anything — appears to compile to
link nodes rather than leaves, and the counts suggest `addnode` nodes are neither preserved
one-to-one. The mapping is not established, and with three usable specimens it cannot be
established from this corpus.

**What is established** is the binary structure itself, which does not depend on that
mapping: trees rooted at `fxmaps` slot 2, 8/12/16-byte link and branch nodes, branching at
12-byte nodes 30% of the time, leaves of 44 bytes and up carrying two to four parameter
programs and a palette of `uniform` references, depths past 12. A reader can walk it without
knowing which source construct produced each node.

### What this closes

The FX-Map internal tree was the last major structure in the format that was neither
identified nor explained away. It is the chain: entered from an `fxmaps` record at slot 2,
branching at 12-byte nodes, terminating in leaves that hold each node's parameter programs
and a palette of references to `uniform` colour nodes.

Two earlier rejections of "the chain is the FX-Map tree" were both correct as stated and
both missed this. The first counted 0-5 entries using a walk that only followed `+8` steps.
The second counted entries correctly but compared *totals* against `paramsGraphNode` counts,
which do not match because a source tree node does not compile to exactly one entry — links,
branches and leaves are separate nodes here. Neither test asked the question that settles
it: does the structure branch?

### Rebuilding the entry set on reachability — and correcting the correction

The false-positive finding was right in kind and wrong in consequence.

Rebuilding the entry set by **transitive reachability** — start from record slots, follow
links, keep only what is actually referenced — gives a population that cannot contain
unreferenced junk:

```
entries reached from record slots      36,302
distinct tags                           4,471
entry bytes as a share of the body      1.92%
```

**Chain entries occupy under 2% of the record body.** They therefore cannot have inflated
the coverage figure in any material way. The increase from 74.82% to 87.16% came from the
*bytecode blocks* those entries point at, and a bytecode block is self-validating: it
decodes as a complete instruction stream of its declared length or it does not. Last
section's suggestion that the coverage number was overstated because chain entries were
counted as explained territory was wrong — the bytes at issue are code, and the code is
real.

**The tag-character test was also unsound.** It classified any value below `0x10000` as
"small int, therefore not a tag", which condemns `0000018B` and `00000089` — both
established list-node tags with consistent internal structure and 87-91% link rates. Tag
values are not required to be large. The 38% figure quoted for false positives is an upper
bound produced by a bad criterion, not a measurement.

What survives from that section is the orphan evidence, which does not depend on how tags
look: **2,910 detected entries are referenced nowhere in the file by anything**, and those
are certainly spurious. That is a real defect in the size-consistency detector, and the
reachability construction above is immune to it by design.

So the standing figures are: coverage of the record body around 85%, chain entries under 2%
of it, and a reachable entry population of roughly 36,000 across 59 specimens whose
commonest tags are the ones already characterised.

### The chain-entry detector has a large false-positive rate

The detector accepts any position whose second word, plus 52, lands 8 to 64 bytes ahead —
a self-consistency test with no check that the first word is a tag. Classifying the 80
"fixed-size tags" it learns, and the entries they match:

```
tags        51 structural (64%)   19 small int (24%)   10 float (12%)
instances   14,993 (62%)          7,658 (32%)          1,411 (6%)
```

**At least 38% of detected entries are false**, their "tag" being a float such as
`3EE147AE` (0.44) or `3F666666` (0.9), or a small integer. The true rate is higher still:
`BF800000` is the float -1.0 and is counted among the structural tags only because the
value test covers positive floats alone.

This is corroborated independently by the orphan analysis. Of 5,201 entries that nothing
points at, **2,910 (56%) are referenced nowhere in the file at all** — not from a record,
not from another entry, not from the directory, under any pointer encoding. An entry no
part of the file refers to is not an entry.

**What this does and does not affect.** Every finding resting on a *specific, well-attested*
tag stands: the parameter blocks `00000291`, `00000294`, `00000295` and `00001A80` and their
`$randomseed`/`$outputsize` programs, the list nodes `00420008` / `0000018B` / `00000089`,
the `uniform` palettes, and the chain heads being 99.5% `fxmaps` records. Those were
measured on named tags with consistent internal structure.

What is inflated is every **aggregate**: the "36,537 chain entries" figure, the share of
orphans, and the body-coverage number that counted chain entries as explained territory.
The coverage figure was already flagged as instrument-dependent, ranging 74.82% to 87.16%
by method; this is a further reason to treat the upper end as optimistic. A defensible
restatement is that identified structures — records, bytecode, gradient tables, and chain
entries with attested tags — account for something on the order of 80% of the record body,
with the balance genuinely unaccounted rather than merely unlabelled.

### The chain belongs to `fxmaps`, but is not the FX-Map tree

Asking which entries are pointed at from outside the chain locates its entry point:

```
chain entries                            36,537
   interior — reached only from another entry   23,392  (64%)
   orphan  — nothing points at them              7,353  (20%)
   head    — pointed at by a record slot         5,792  (16%)

filter of the record that heads a chain:
   fxmaps          5,765   (99.5%)
   everything else    27
```

Chains are entered from an `fxmaps` record, almost always at **slot 2**. Together with the
earlier finding that 99.4% of multi-entry runs sit inside `fxmaps` records, the structure is
unambiguously FX-Map-owned.

**It is still not the node tree.** That hypothesis was rejected earlier on a bad
measurement — the `+8`-only walk counted 0 to 5 entries where the true variable-length walk
finds tens to hundreds. Redone correctly, it fails anyway:

```
pGNodes vs chain entries   +0.335
pGNodes vs fxmaps records  +0.738

ie_curve      90 tree nodes ->  58 entries
ie_pcloud     41 tree nodes -> 424 entries
Clouds_Animated (no inlining)  22 nodes -> 9 entries
```

Entry counts run both above and below the node count, and correlate less well with it than
plain `fxmaps` record counts do. Whatever the chain enumerates, it is not one item per tree
node.

What it does contain is understood: parameter blocks holding each node's `$randomseed` and
`$outputsize` programs, list nodes linking them, and palettes of references to `uniform`
colour nodes. That is FX-Map *parameter* storage. The tree's topology — which quadrant
follows which, the `paramset`/`addnode`/`markov2` structure — remains unlocated, and is now
the last major structure in the format that is neither identified nor explained away.

### The `0x1A80` integers are references to `uniform` nodes

The 64-byte parameter block's six leading integers are record indices, and what they point
at is not evenly distributed. Resolving 2,574 of them across 429 entries:

| referenced filter | share | corpus base rate | enrichment |
|---|---:|---:|---:|
| **`uniform`** | **76.7%** | 1.7% | **44x** |
| `transformation` | 17.8% | 26.6% | 0.67x |
| `pixelprocessor` | 2.4% | 4.6% | 0.52x |
| `blend` | 0.4% | 34.4% | 0.01x |
| everything else | < 1% each | | |

A 44-fold enrichment for one filter is not an artifact of index range. The references are
also **local**: 97% name a record within ten positions before the entry itself, and the six
are in ascending order in 83% of entries.

`uniform` is the constant-colour generator. So a `0x1A80` block holds an ordered list of
references to up to six nearby constant-colour nodes, alongside the standard `$randomseed`
and `$outputsize` programs. An ordered set of six colour sources attached to a node is what
a palette looks like.

That is as far as the evidence goes. What consumes the palette is not established — no
record slot within the first forty bytes of any record points at a `0x1A80` block, so these
entries are reached through the chain from another entry rather than directly, and the
owning node has not been traced.

### The parameter block's layout

Dumping the variants side by side shows one template with a variable middle:

```
0x0294  48 B   [tag][next]  P  P  v  v  P  P        | 05C40001  0  05C40001  4
0x0291  48 B   [tag][next]  P  P  v  v  P  P        | 05C40001  0  05C40001  4
0x0295  52 B   [tag][next]  P  P  v  v  v  P  P     | 05C40001  0  05C40001  4
0x1A80  64 B   [tag][next]  v  v  v  v  v  v  P P P P | 05C40001  0  05C40001  4

P = pointer to a bytecode block      v = inline value
```

**Every variant ends with the same four words**, `05C40001 00000000 05C40001 00000004`, at
100% in all four. That word decodes under the block convention as `[u16 count = 1][u16
opcode 05C4]` — a one-instruction inline program whose opcode is `float4 get`. So the two
"1-instruction programs" identified earlier are not pointed to at all; they are written
inline in the footer.

The inline values differ by variant and are recognisable:

* `0x0291`: 0.5 (100%) and 0.9 / 0.85 — a pair of ratios
* `0x0294`: 0 / 0.66 / 0.75 and 0.44 / 1.6 / 1.5
* `0x0295`: three values, 0.5 or 1, then 0.75 / 0.66 / 0.18, then 0.44 / 1.6 / 1.1
* `0x1A80`: six *integers* — 10, 36, 26, 79, 35, 8, 17, 37 — not floats, and no value
  dominates

So the 48- and 52-byte forms carry float parameters and the 64-byte form carries six small
integers, which look like indices or counts rather than magnitudes. What they index is not
established.

The structure as a whole is now: a tagged entry, a link to the next, a variable-length
inline payload, two pointers to the `$randomseed` and `$outputsize` programs, and a constant
footer holding two inline one-instruction programs.

### The chain entries are one structure at several offsets

Classifying what every fixed-size chain entry's payload words point at splits the family in
two.

**List nodes** carry a link to another entry:

| tag | size | payload |
|---|---|---|
| `00420008` | 12 B | word 2 -> another chain entry, 98% |
| `0000018B` | 12 B | word 2 -> another chain entry, 87% |
| `00000089` | 16 B | word 2 a value, word 3 -> another chain entry, 91% |

**Parameter blocks** carry four bytecode pointers, and they are all the *same* block at
different offsets:

| tag | size | program slots |
|---|---|---|
| `00001A80` | 64 B | words 8, 9, 10, 11 |
| `00000291` | 48 B | words 2, 3, 6, 7 |
| `00000294` | 48 B | words 2, 3, 6, 7 |
| `00000295` | 52 B | words 2, 3, 7, 8 |

Resolving each program's `inputref` immediates against the manifest gives the same answer
for every one of them:

```
program 1   $randomseed    median  3 instructions   100%
program 2   $outputsize    median 68 instructions   99-100%
program 3   (constant)     median  1 instruction
program 4   (constant)     median  1 instruction
```

Over 8,776 blocks across the four tags. So there is a single **per-node system-parameter
block** — seed program, output-size program, two constants — and the several tags are that
block embedded in entries with different amounts of leading payload, not different
structures.

This also resolves a loose end: `BF800000` appeared in the fixed-size tag list with a
20-byte entry whose word 4 points at bytecode. `BF800000` is the float -1.0. It is a value
that happens to precede a plausible pointer, admitted by a detector keyed on size
consistency alone, and it is not a tag.

### The residue is not padding — correction

The coverage audit was left with the claim that the unexplained 12.84% was "alignment
padding and small inter-record fill". That was asserted from the gap *size* distribution
without looking at the gap *contents*. Checking them:

```
non-zero data        5,332,879 bytes   96.0%
all zero               204,310          3.7%
mostly zero (>75%)      18,313          0.3%
```

**96% of the unexplained bytes are non-zero.** The all-zero gaps are almost entirely the
101,781 gaps of under 8 bytes, which are genuine alignment fill; everything larger is data.

### What the residue actually is

The first word of each gap identifies it:

```
00 00 8b 01   x3908      <- tag 0000018B, shifted 2 bytes
00 00 89 00   x3350      <- tag 00000089, shifted 2 bytes
08 00 42 00   x1884      <- tag 00420008
48 02 52 14   x930       <- tag 14520248
48 02 50 14   x535       <- tag 14500248
48 06 40 12   x474       <- tag 12400648
```

These are the **parameter-chain tags already catalogued**, and the commonest cases are
shifted by two bytes. That is an artifact of the audit rather than of the format: bytecode
blocks end on a 2-byte boundary while chain entries are 4-byte aligned, so a gap that opens
immediately after a block starts two bytes before the entry that follows it.

So the residue is predominantly **more of the same chain structure**, not an unidentified
one. That is a weaker claim than it sounds — knowing the tag family does not mean the
entries' contents are understood, and only the 48- and 52-byte kinds have been decoded.

### A caution about the coverage figure itself

Coverage depends on which pointer sources the audit follows, and the number moves several
points between reasonable choices: 74.82% following record slots alone, 87.16% adding the
pointers held inside chain entries, 82.46% for a variant that scanned for chain tags
directly but omitted their pointers. These are not successive improvements — they are
different instruments, and quoting any single figure as "the" coverage would misrepresent
the precision available. The defensible statement is that roughly 85% of the record body is
attributable to identified structures, and the remainder is dominated by chain entries whose
tags are known and whose payloads mostly are not.

## The compiler maps several source filters onto one binary type

Six filter names in the sources have no binary id of their own, and no unnamed id with
meaningful volume is left for them. They compile to a **named** type, distinguished only by
their parameters. Correlating each unassigned name's share against every named type's share
across 178 paired specimens:

| source filter | compiles to | r |
|---|---|---|
| `grayscaleconversion` | **`shuffle`** | +0.52 |
| `valueprocessor` | **`pixelprocessor`** | +0.40 |
| `dirmotionblur` | **`directionalwarp`** | +0.38 |

### `grayscaleconversion` proved outright

`shuffle` stores a four-component weight vector, and if `grayscaleconversion` is the same
filter with different weights, luminance coefficients should appear in it. They do. Over
2,128 shuffle records with a readable quadruple:

```
(0.0, 1.0, 0.0, 0.0)     x633  |  pure channel selection
(1.0, 0.0, 0.0, 0.0)     x602  |
(0.0, 0.0, 0.0, 1.0)     x417  |
(0.0, 0.0, 1.0, 0.0)     x383  |
(0.25, 0.25, 0.25, 0.0)   x34  <- equal-weight average
(0.0, 0.8, 0.2, 0.0)      x20
(0.3, 0.59, 0.11, 0.0)    x19  <- Rec. 601 luminance coefficients
```

96% are pure 0/1 selections — `shuffle` proper — and 4% are weighted combinations, which is
`grayscaleconversion`. `(0.3, 0.59, 0.11)` is not a value that arises by accident; it is the
standard luminance weighting, written into the same field that elsewhere holds a channel
selector.

### What this means for the missing enums

The compiler does not transcribe parameters, it **evaluates what they denote**. A channel
selector becomes the selection vector; a named grayscale conversion becomes its coefficients;
a filter identity itself dissolves into another filter plus parameters.

This is the best available explanation for `blendingmode`, which has now been excluded from
every slot, the record's own bytecode, the class word, the size rule and the parameter chain.
If a mode index is never stored — only the operation it selects, applied by the engine — then
there is nothing to find in the record, and the search has been looking for the wrong kind of
object. Confirming that needs a differential specimen, which the corpus does not contain.

### `0x2C` and `0x22` — probable, not confirmed

**`0x2C` is probably `curve`** (909 records). Its 96-byte form is 24 slots, and the tail is
eighteen consecutive floats in three groups of six:

```
slots  6-11   0      0      0      0      0      0
slots 12-17   0.464  0.382  0.379  0.119  0.549  0.645
slots 18-23   1      1      1      1      1      1
```

Three arrays of six is a structure-of-arrays layout for **six control points with three
attributes each** — which is what a curve is. Size-controlled correlation across 178 paired
specimens puts `curve` first at r = +0.518, with `valueprocessor` second at +0.265 and every
other candidate at or below zero.

**`0x22` is probably `text`** (52 records), at r = +0.517 — but 52 records across 11
specimens is too little to call.

Both are recorded as probable. The structural argument for `curve` is the stronger of the
two; `text` rests on correlation alone.

### Filter identification: current state

| status | ids |
|---|---|
| named on structural evidence | `gradient`, `blend`, `transformation`, `shuffle`, `fxmaps`, `uniform`, `warp`, `blur`, `levels`, `bitmap`, `normal`, `pixelprocessor`, `distance`, **`directionalwarp`**, **`passthrough`**, **`hsl`**, **`sharpen`**, **`emboss`** |
| probable | `0x2C` = `curve`, `0x22` = `text` |
| terminal | `0x16` — reachable only through inlined library graphs |
| unnamed | `0x0A` (119 records, 5 specimens), `0x12` (5 records, 4 specimens) |

Eighteen filters named, two probable, one terminal, two too rare to pursue. The unassigned
source names remaining — `grayscaleconversion`, `dirmotionblur`, `valueprocessor`,
`dyngradient`, `motionblur`, `svg` — have no candidate id left with meaningful volume, which
suggests they compile to one of the named types with different parameters rather than to
ids of their own.

### `distance`, `normal`, `shuffle`, `bitmap`

| filter | size | slot | parameter | values |
|---|---|---|---|---|
| `distance` | 24 B | 5 | **`distance`** | 1.28 (12%), 0 (10%), 32.0 (10%), 12.8 (5%) |
| `normal` | 24 B | 5 | **`intensity`** | 12.0 (22%), 16.0 (8%), 8.0 (6%) |
| `normal` | 20 B | 4 | `intensity` | 16.0 (18%), 12.0 (10%), 20.0 (4%) |
| `shuffle` | 28 B | 3, 4, 5, 6 | **channel selection** | each 0 or 1 — see below |
| `bitmap` | 12 B | 2 | pointer only | no parameter slots |

`normal`'s intensity clusters on 8, 12, 16, 20 — whole numbers an artist types into a
normal-strength field. `distance`'s values are 1.28, 12.8 and 32, which are pixel
distances.

**`shuffle` is the first discrete parameter located, and it is stored as floats.** Its
28-byte form carries four consecutive slots whose values are almost entirely 0.0 or 1.0:

```
slot 3   0 (68%)   1 (29%)
slot 4   0 (66%)   1 (31%)
slot 5   0 (78%)   1 (19%)
slot 6   0 (80%)   1 (20%)
```

The sources declare `channelalpha`, `channelgreen` and `channelblue` as `Int32` enums, but
the compiled form is a four-component vector of 0/1 weights — one per output channel. The
compiler has turned a channel-selection enum into the selection *matrix* it denotes.

That is a useful precedent for the missing enums. A parameter declared as an integer in the
source need not be an integer in the binary: `blendingmode` may likewise be compiled into
whatever the mode denotes rather than stored as its index, which would explain why a
7-valued field with a 97% default appears nowhere in a blend record. It also predicts where
to look — not for the enum, but for the thing it selects.

### `warp`

| form | size | slots | contents |
|---|---|---|---|
| grayscale | 24 B (8,903) | 2 edge, 3-4 pointers, **5 float** | `intensity`: 0.25, 0.01, 0.08625, 2 |
| grayscale | 20 B (5,866) | 2 edge, 3 pointer, **4 float** | `intensity`: 0.25, 2, 0.0015625, 0.00625 |
| grayscale | 28 B (1,574) | 2 edge, 3-5 pointers, **6 float** | `intensity`: 0.1, 0.00078125, 0.01, 0.00125 |
| colour | 20/24/32 B | — | 185 records total, too few to stratify |

`intensity` sits in the last slot of the record in all three grayscale forms, which is
consistent with the rule that parameters are laid out after the header and pointers.

**A rejected reading.** In the 28-byte form, slots 4 and 5 showed near-identical value
distributions, which looks like a 2-component parameter written as two equal components —
the pattern seen in colour `levels`, where an RGBA quadruple carries equal RGB. Testing it
per record: the two slots are **equal in only 11.4%** of the 1,580 records. The cases where
they differ expose what they are — values like `2.37556e-38` and `6.41795e-42` are
denormal floats, i.e. small integers read through the wrong lens. Both slots hold
pointer-like data drawn from a similar range, and the matching distributions were an
artifact of displaying only the top four values of each.

The lesson generalises to the whole parameter-mapping method: **similar distributions are
not evidence of a shared type; equality per record is.** Colour `levels` passed that test
(equal RGB triples, alpha 1.0 in 78-95%), `warp` fails it.

### Colour filters store per-channel parameters as RGBA quadruples

`levels` was the right next target: highest record count with anything unmapped, and its
remaining parameters are `Float4` rather than `Float1`. That type difference predicted a
structural one, and the prediction held.

Grayscale (`0x1E`) and colour (`0x1F`) levels records have **disjoint size distributions**:

```
grayscale   24 B (6183), 20 B (1884), 28 B (1101), 16 B (449)
colour      32 B (357),  48 B (314),  64 B (29),   16 B (20)
```

The colour records store each level point as an RGBA quadruple, and grow 16 bytes per
point:

| size | slots | contents |
|---|---|---|
| 32 B | 4-7 | one quadruple |
| 48 B | 4-7, 8-11 | two quadruples |
| 64 B | 4-7, 8-11, 12-15 | three quadruples |

Sample 64-byte record, floats only:

```
0 0 0 1  |  0.105 0.105 0.105 1  |  0.835 0.835 0.835 1
```

Three level points, each with equal RGB components and alpha 1.0 — the grayscale values an
artist would set, written per channel. The alpha slot (7, 11, 15) is 1.0 in 78-95% of
records across all three sizes.

**The general rule this establishes:** a record's length is determined by the parameters it
stores, laid out from slot 4 in fixed-width fields — 4 bytes for a `Float1`, 16 for a
`Float4`. Record size is therefore diagnostic: it says how many parameters are present
before any of them are decoded.

### `blendingmode`: the size rule tested and still negative

If parameters extend the record, blends declaring a non-default mode should be longer. The
size distribution is suggestive — 24 B (65.5%), 20 B (33.3%), **28 B (1.0%)** — against
roughly 3% non-default modes in the sources.

The 28-byte form does carry an extra slot: opacity moves from slot 5 to slot 6, leaving
slot 5 free. But slot 5 holds **1,803 distinct values** across 1,955 records, which is a
pointer or a hash, not a seven-valued enum. One of its observed values is `00020008`, the
commonest parameter-chain tag, which suggests it links into the chain rather than holding a
value inline.

So the mode is still unlocated, and the chain entries are now the leading candidate.

### The blend record, fully accounted — and `blendingmode` is not in it

With the true extent known, a 24-byte `blend` record is six slots and every one is
identified:

```
slot 0   tag        type (2*filter + is_colour | resolution nibbles), class word
slot 1   flags      slot-1 bitfield
slot 2   edge       backward record index
slot 3   edge       backward record index
slot 4   pointer    -> the record's bytecode; target reads [u16 count][0A42 ...]
slot 5   float      opacity: 0.5(19%), 0.25(8%), 0.333(8%), 0.2(7%)
```

The 20-byte variant drops slot 5 and carries opacity at slot 4. There is no seventh slot,
and no room for a mode selector.

**Where `blendingmode` is not.** It has an unmistakable signature — 7 distinct values, 97%
of them 0 — and it has now been excluded from every part of a blend record:

* **all record slots**, in every size class, searched within the true extent
* **the record's own bytecode**: 29,217 blocks, 754 distinct opcode signatures; int
  constants run 32% value 1, 23% value 0, nothing resembling 97%/7
* **the program hanging off slot 4** — which turned out to be the same bytecode, reached
  by pointer
* **the class word**: 10 distinct values at 79/13/4/2/1%, not 97/1/1/1%
* **omitted defaults**: record size does not track declared parameter count (r = +0.104)

It is genuinely somewhere else. The remaining candidates are the parameter-block chain
entries, most of whose ~137 tag kinds are still unexamined, or a per-graph table outside
the record body entirely.

**Why this one is hard, restated.** Float parameters were findable because 0.5 and
0.333333 cannot be mistaken for structure. A 3-bit enum whose default dominates looks
exactly like a flag field, a small count, or padding. Locating it needs a differential
specimen — two files identical but for one node's mode — rather than any amount of
distributional search over the corpus as it stands.

### Correction: record extent is not the gap to the next record

The parameter map above was built by grouping records on the gap to the next record. That
gap is **record + interleaved bytecode**, not the record. Dumping every 448-byte "blend
record" in `Wood_Planks` shows all 178 of them byte-identical from slot 5 onward, and that
shared tail is plainly code: slot 4 reads `0A420044`, whose low half `0x0044` is 68 — a
block instruction count — followed by `0A42`, the first opcode.

The true record ends where its bytecode begins, and that boundary is findable by scanning
forward for the first valid length-prefixed block. Records are small and consistent:

| filter | true record size | share |
|---|---|---|
| `transformation` | 16 B | 56% |
| `blend` | 24 B | 63% |
| `levels` | 24 B | 59% |
| `blur` | 20 B | 66% |
| `warp` | 20 B | 45% |
| `uniform` | 8 B | 48% |

### The corrected parameter map

Within the true extent, the layout is regular: **slots 0-3 are header** — tag, slot-1
flags, and two edge or pointer slots — and **parameters begin at slot 4**.

| filter | record | slots | parameter | values |
|---|---|---|---|---|
| `transformation` | 32 B | 4, 5, 6, 7 | **`matrix22`** | `2(37%), 0(91%), 0(91%), 2(35%)` — the diagonal form |
| `transformation` | 36 B | 4-7 | `matrix22` | `2(58%), 0(87%), 0(87%), 2(58%)` |
| `transformation` | 40 B | 4-7, 8-9 | `matrix22`, **`offset`** | matrix then a 2-vector |
| `blend` | 24 B | 5 | **`opacity`** | 0.5(19%), 0.25(8%), 0.333(8%), 0.2(7%) |
| `blend` | 20 B | 4 | `opacity` | 0.5 |
| `levels` | 24 B | 4, 5 | **`levelinhigh`, `levelinlow`** | 0.25/1 and 0.75/0 |
| `levels` | 20 B | 4 | **`levelinmid`** | 0.5 (42%) |
| `levels` | 28 B | 4, 5, 6 | three level points | 0.0627/0.9333/0 |
| `warp` | 20 B | 4 | **`intensity`** | 0.5, 0.0015625, 0.03125, 1.25 |
| `blur` | 20 B | 4 | **`intensity`** | 1(58%), 0.5(8%), 2(6%), 4(3%) |

**`uniform`'s `outputcolor` — corrected twice.** It was first read from a float run that
turned out to lie past the record boundary, then dismissed on the grounds that `uniform`'s
record is 8 bytes with no room for a quadruple. Both readings were wrong, because 8 bytes is
only its *smallest* variant. Measured across all sizes:

```
 8 bytes  1,757 records   no parameter slots
12 bytes    784 records   slot 2 float (76%)
24 bytes  2,725 records   slots 2,3,4,5 all float (100%)   alpha == 1.0 in 82%
```

The 24-byte form is the commonest, and its four floats are `outputcolor`: values such as
0.560784, 0.572549 and 0.054902 are 143/255, 146/255 and 14/255, and R==G==B in only 27% of
records, so these are genuine colours rather than greys.

So `outputcolor` **is** a record field, at slots 2-5 of the 24-byte variant. The earlier
dismissal is a clean example of the modal-size trap: `uniform`'s most-cited size in a
size-sorted list is 8 bytes, and that variant carries nothing.

This is the same class of error as the earlier `+8`-only chain filter: a boundary chosen
for convenience, then mistaken for a property of the data. Here it inflated record sizes
by up to twenty-fold and put four filters' parameters at the wrong offsets.

### The parameter map, filter by filter

Applying the size-stratified dump across filters, and searching for runs of consecutive
float-valued slots, locates the static parameters of most of the named filters. The values
identify themselves by structure, not by correlation.

| filter | record size | slot | parameter | evidence |
|---|---|---|---|---|
| **`transformation`** | 36 B | 3-6 | **`matrix22`** | `(0.5, 0, 0, 0.5)`, `(0.125, 0, 0, 0.125)`, `(4, 0, 0, 4)` — a 2x2 matrix with zero off-diagonals, i.e. pure scaling |
| `transformation` | 36 B | 7-8 | **`offset`** | the 6-run `(1, 0, 0, 1.5, 0, 0.25)` is the matrix followed by a 2-vector |
| **`uniform`** | 32 B | 2-5 | **`outputcolor`** | `(0.49804, 0.49804, 0.49804, 1.0)` — RGBA with alpha 1; 0.49804 is 127/255, 8-bit mid-grey |
| **`levels`** | 32 B | 4, 5 | **`levelinhigh`, `levelinlow`** | modal values 1 and 0, their documented defaults |
| `levels` | 28 B | 4 | **`levelinmid`** | 0.5 in 54%, its default |
| **`blend`** | 20/32/44 B | 4 or 5 | **`opacity`** | 0.5, 0.25, 0.333, 0.2 |
| **`warp`** | 28 B | 4 | **`intensity`** | 0.5, 0.03125, 0.0078125, 1.25 — power-of-two scalings |
| **`blur`** | 20 B | 4 | `intensity` | constant 1.0 in 100% |
| `gradient` | 40 B | 4 | — | 0 in 96%, uninformative |

`matrix22` and `outputcolor` are the two that settle the method. A 4-float run reading
`(s, 0, 0, s)` is a scaling matrix and nothing else; a 4-float run ending in exactly 1.0
with three equal components at 127/255 is an RGBA grey. Neither could be produced by a
structural field.

**The limits are now clear.** This works for float parameters because their values are
implausible as structure. It does not work for:

* **Enums** — `blendingmode` has 7 values, 97% of them 0, which is indistinguishable from
  any small-integer structural field. Still unlocated.
* **Booleans** — `colorswitch`, `tiling` and similar are single bits or small ints with the
  same problem.
* **Arrays** — `gradient`'s 51,801 `position`/`midpoint`/`value` triples are a variable-length
  stop list, not a fixed slot, and the 40-byte gradient records show nothing at any single
  position.

So a reader can now recover a node's transform matrix, offset, uniform colour, level
points, blend opacity and warp intensity directly. What remains missing is the discrete
parameters — which mode, which channel, which interpolation — and the gradient stop array.

### Static filter parameters live in record slots, at size-dependent positions

Dumping complete records grouped by size — rather than scanning slot positions across all
records — makes the parameter fields visible. Every earlier scan pooled slots across
layouts and mixed different fields together, which is why they stayed hidden.

**`blend` — opacity.**

| record size | slot | values |
|---|---|---|
| 20 bytes | 4 | 0.5 in 92% |
| 32 bytes | 5 | 0.5 (21%), 0.25 (11%), 0.333 (10%) |
| 44 bytes | 5 | 0.5 (18%), 0.25 (12%), 0.333 (11%), 0.2 (8%) |

**`levels` — the level points.**

| record size | slot | values |
|---|---|---|
| 32 bytes | 4 | float in 99%; commonest **1** (13%), then 0.25, 0.375, 0.4375 |
| 32 bytes | 5 | float in 99%; commonest **0** (13%), then 0.75, 0.625, 0.5625 |
| 28 bytes | 4 | **0.5** in 54% |

The defaults identify them. `levelinhigh` defaults to 1 and `levelinlow` to 0, which are
exactly the modal values of slots 4 and 5 in the 32-byte layout; `levelinmid` defaults to
0.5, the modal value of slot 4 in the 28-byte layout. Slots 4 and 5 sum to 1 in 80% of
records — artists commonly adjust the two symmetrically — but the remaining 20% show they
are independent fields, not a constrained pair.

**The general rule.** A record's slot layout depends on its size. Fields cannot be located
by asking "what is in slot 5" across all records of a filter; the question only has an
answer within one size class. This is a structural fact about the format and it invalidates
the method used in every earlier attempt at the parameter fields.

**What this does not resolve.** `blendingmode` is still unlocated: it has an unmistakable
signature — 7 values, 97% of them 0 — and no slot in any blend size class carries it, nor
does the attached bytecode. A float parameter is recognisable by its value distribution;
a small enum whose default dominates is not, since almost any structural field of small
integers could match. The floats were findable precisely because 0.5, 0.25 and 0.333 are
implausible as structure and obvious as parameters.

### Is the parameter value in the attached code? Partly.

Diffing the bytecode attached to `blend` records, and dumping the records in full.

**Opacity is in the record slots.** A blend record carries a float whose values are
exactly what an opacity would be — 0.5, 0.25, 0.333, 0.2 — in a slot whose position
depends on the record's size:

```
20-byte blends   slot 4    0.5 in 92%
32-byte blends   slot 5    0.5 (21%), 0.25 (11%), 0.333 (10%)
44-byte blends   slot 5    0.5 (18%), 0.25 (12%), 0.333 (11%), 0.2 (8%)
```

Record layout therefore varies, and pooling slots across sizes — which every earlier scan
did — mixes different fields together. That is why the parameter slots were not visible
before.

**`blendingmode` is not in the code.** The programs hanging off blend records were
compared directly. Across 31,705 blend records the slot-4 programs reduce to 263 distinct
opcode signatures, dominated by a lone `0A42` (an `inputref`) at 37%. In
`serverhouse__BrickWall_02`, which has six distinct blend modes in its source, all 223
blend records share just **five** signatures with counts 136/25/10/4/1 — against a mode
distribution of 34/5/4/2/1/1. The programs are `0A42 1640 0A52 1240 0A52 ...`: an input
reference followed by alternating integer constants and adds, which accumulates an offset,
not a mode selector.

**And it is not in any slot.** `blendingmode` has an unmistakable signature — 7 distinct
values, 97% of them 0. Stratified by record size, no slot in any blend layout carries it.

**Nor is it explained by omitted defaults.** If default-valued parameters were simply not
written, record size would track the number of explicitly declared parameters. Across 141
paired files, mean parameters per blend node against mean blend record size gives
**r = +0.104**. No relationship. (Inlining weakens this test, since the binary contains
library blends the source never declares.)

So: static parameter values *do* live in record slots, at size-dependent positions, and
opacity is now identifiable. `blendingmode` specifically is not in the slots, not in the
attached programs, and not accounted for by default omission. It remains unlocated.

### 2. Which input port an edge connects to

Edges are located, but not their meaning. `blend` has three named ports in the sources —
`source` (7,283 uses), `destination` (7,172) and `opacity` (1,915) — and slots 2 and 3
hold edges in 100% of blend records. Slots 5 and 6 carry backward references in about 3%,
consistent with `opacity` being optional, but this is unverified.

Which of slots 2 and 3 is `source` and which is `destination` is **not established**, and
it is not cosmetic: reversing them inverts every non-commutative blend. The same question
applies to `warp` (`input1` vs `inputgradient`), `distance` (`source` vs `mask`) and
`fxmaps` (`input_selection`, `inputpattern`, `input`).

### 3. The FX-Map internal tree

FX-Maps carry a node tree — `paramset`, `addnode`, `markov2` — that drives pattern
splatting, and it is where much of Substance's procedural generation happens. Its binary
encoding is unlocated. Correlation between tree node counts and the chain entries reaches
+0.386, which is not identification.

### 4. Smaller but certain

* **Per-node bit depth.** The record type carries grayscale/colour and resolution, but the
  `format` parameter (8-bit vs 16-bit vs 32-bit float) appears on nodes in the sources and
  has no located home.
* **`gradient`'s interpolation mode** and the gradient stop array.
* **Presets.** `.sbsar` packages ship parameter presets; these are in the XML manifest, so
  a reader can get them, but their compiled form is unexamined.

### Why this matters for a reader

The distinction is between parsing and evaluating. Everything needed to *read* the file —
walk the graph, decode the instructions, extract the images — is established. What is
missing is concentrated in the values that determine *what a filter does*, which is
exactly what an implementation would need to reproduce an image. A reader can today say
"node 42 is a blend taking nodes 17 and 31"; it cannot say "and it multiplies them at 60%
opacity".

## Open questions

*(This list is superseded. Its status as of the latest work:)*

1. ~~**Why the constant is 52.**~~ **Characterised** — universal across v2–v9, and the
   "header is really 52 bytes" explanation is eliminated. See "The 52-byte skew,
   characterised".
2. ~~**The alternate body layout** in MetalSubstance009.~~ **Retracted** — there is no
   alternate layout; it was `base != 0` from a resource segment displacing the directory.
3. ~~**The `.sbsasm` record schema itself** — still undecoded … identification requires
   differential analysis.~~ **Largely solved, and by a different route than predicted.**
   Records are located, framed, typed and connected; fifteen node filters are named. The
   route was not differential analysis of purpose-built graphs but correlation of `.sbs`
   *pixel-graph* node counts against record types on instance-free specimens. The claim
   that "nothing in the bytes bootstraps their meaning" was wrong: the record directory,
   the `NN`/type tag structure and dataflow back-references all did.

**Currently open:** the meaning of `NN`; the identity of filter type `0x16`; the
semantics of the class-word and slot-1 bitfields.

### Closed

- ~~Residual mismatches in specimens containing IMAGE/STRING inputs.~~ **Resolved.**
  The cause was image inputs occupying an unaccounted 16-byte float4 slot, which
  shifted the computed table start by exactly that much and desynchronised the prefix.
  What made this hard to see: the surviving suffix still matched perfectly, so the
  failure looked like a local *permutation* of values rather than an offset error. An
  earlier width search tested 0, 4 and 8 bytes and concluded non-numeric inputs took no
  slot — it simply never tried 16. Widening the search resolved both failing specimens
  to 100%.

## Negative results — important

- **Not encrypted, not whole-file compressed.** Entropy 3.2–4.6 across the corpus;
  crypto or compression would sit near 7.9. Static analysis works directly.
- **No embedded standard containers.** No PNG/JPEG/DDS/zip/gzip payloads survive
  verification.
- **Naive value search is worthless.** Common defaults like 0.5 and 1.0 occur over
  three million times in the 21 MB specimen. Every result here came from using rare
  values as anchors, then validating a full reconstruction.

## Suggested next milestones

1. ~~**Differential corpus — now the critical path.**~~ **Superseded.** This said a
   purpose-built differential corpus was "the only approach left". It was not: paired
   `.sbs`/`.sbsar` specimens already in the corpus carried the pixel-graph node names,
   and exact-count matching on instance-free files named fifteen filters without
   producing a single new specimen. A differential corpus would still help with `NN` and
   `0x16`, both of which need variation this corpus does not contain.
2. **Resolve the 3 directory-check failures** in the 219-specimen set.
3. ~~Multi-graph packages.~~ **Solved** — see the multi-graph section. Hypotheses that
   failed on the way:
   - *Concatenated per-graph tables* addressed by the single `0x2C` pointer — explains
     only 3 of 23, under either manifest or reverse graph order, with globals attached
     to the first graph, the last, or neither.
   - *Independent per-graph interface blocks* — locating each graph's value table on its
     own succeeds for 44% of graphs, but the `(n_out, n_in)` header never follows
     (0 of 68), and `0x2C + 52` coincides with a graph's table end in only 5 of 21
     packages.
   The resolution was that the block is package-level and aggregates every graph.
2. **Decode the record stream.** The 52-byte question turned out to be a facet of this
   larger one: the defaults sit inside the final record of a stream whose encoding is
   unknown. `0x0A420001` is a frequent token in that stream and is a reasonable place to
   start.
3. **Exploit the ground-truth pairs.** The four verified `.sbs`/`.sbsar` pairs give
   known node counts, types, uids and connectivity against compiled binaries — no
   Designer licence required. Correlating node uids from the `.sbs` against the record
   stream is the most direct available attack on the record schema. Harvesting more
   pairs from GitHub would widen this considerably.
4. **Differential corpus.** Still the strongest method if a Designer licence is
   available: publish minimal graphs at increasing complexity — one node, two nodes, one
   node with a changed parameter — and diff the resulting `.sbsasm`. The pairs in (3)
   are a weaker but free substitute, since their graphs are not minimal.
5. **Resolve multi-graph packages** (see the limitation above).

## The .sbs sources are a Rosetta stone — confirmed

`float 0x07` is **`set`**: assign a value to a local variable slot. Operands are
`(value, slot_index)`, where the slot index is a small immediate, not a value number.
The type and width fields describe the value stored, so the family is
`0907/0947/0987/09C7` for float1–4, `0A07/0A47` for int, `0847` for bool.

This was not found by hunting for constants. The `.sbs` XML source format names **every
node of every function graph** — `<function v="mul"/>` — and 103 of them sit in the
paired corpus. That is 98,348 labelled nodes across 70 distinct node types: a labelled
training set for the entire instruction set.

### Two things that had to be got right first

**Correlation does not work.** The matched pairs hold 98k authored nodes against 2.39M
decoded instructions — a 24x gap, because a `.sbs` lists only what the author drew while
the `.sbsar` bakes in every referenced library graph. Correlating counts per file gives
r > 0.9 for almost every (name, opcode) pair purely through file size. Correlating
*shares* to remove that confound recovered only 2 of 13 already-known mappings, so it was
abandoned rather than trusted.

**Self-contained specimens are the ones that matter.** Per-file ratios of instructions to
authored nodes run from 0.0 to 27,525. A handful sit near 1, where the source accounts
for essentially all of the assembly:

| specimen | nodes | instructions | ratio |
|---|---|---|---|
| `LGMLtools__find_alpha0_pixel` | 62 | 62 | 1.00 |
| `ie_particles` | 1588 | 1745 | 1.10 |
| `LGMLtools__sdf_painter_filter` | 15 | 20 | 1.33 |

### A 1:1 alignment

`find_alpha0_pixel` holds three function graphs. The second is ten nodes and compiles to
a nine-instruction run — one node is dead-code-eliminated — aligning exactly:

| source node | instruction | note |
|---|---|---|
| `get_float2 "$pos"` | `0541 op01 (8)` | system variable |
| `samplecol pos=…` | `09F4 op34 (v0, 0)` | returns float4 |
| `swizzle1 … Int1=3` | `0910 swizzle (v1, 3)` | index 3 = `.w` |
| `const_float1 1` | `0900 const = 1` | |
| `eq a=… b=…` | `085D op1D (v2, v3)` | bool result |
| `swizzle3 vector=…` | `0990 swizzle (v5, 36)` | 36 = `0b100100` |
| `vector4 …` | `09CD vector (v6, v2)` | |
| `ifelse …` | `0DC9 select (v4, v1, v7)` | |

**Swizzle masks are packed 2-bit component indices.** `swizzle3` emits `36` =
`0b10 01 00`, reading low-to-high as components 0, 1, 2 — `.xyz`. `swizzle1` emits a bare
`3` — `.w`. This is why `0x10`'s second operand looked like a wild value number and
corrupted the value-numbering bound: it is an immediate.

### The variable slots cross-check

Graph 1 uses `set` and `get` on named variables. Slot indices agree across both, and
against the declared types:

| variable | type | `set` (op 0x07) | `get` (op 0x04) |
|---|---|---|---|
| `sample_pos` | float2 | `0947 (v31, 0)` | `0544 (0)` |
| `final_color` | float3 | `0987 (v40, 2)` | `0584 (2)` |
| `max_loop` | int | `0A07 (v5, 5)` | `0604 (5)` |

Counts by type match exactly for float2 (3/3) and int (3/3). Float3 shows 4 against 2,
and float3 is precisely the type of `final_color` — the variable carried across the
file's single `while` loop, which needs extra loop-carried assignments. `ie_particles`,
which has no `while`, matches **exactly**: `set` 58 ↔ op `0x07` 58, and `sequence`
58 ↔ op `0x0C` 58.

Corpus-wide, over 1,360,905 `op-0x07` instructions in 144 specimens, **operand 2 is below
64 in 99.7% of cases** with a median of 38 distinct values per file, while operand 1
spreads out like a value number (only 67.6% below 64). A slot holds one (type, width)
within a file in 67.6% of cases and a matching `op-0x04` read agrees in 76.3% — both
figures diluted by multi-graph packages, where slot numbering restarts per graph.

### Newly identified operations

| op id | name | evidence |
|---|---|---|
| `0x07` | `set` — assign to variable slot | 1:1 alignment, slot/type cross-check, exact counts |
| `0x04` | `get` — read local variable slot | slot indices agree with the matching `set` |
| `0x0C` | `sequence` — chain statements, yields the last | left-leaning chains; exact counts |
| `0x0B` | `while` loop | 5 operands; immediate `128` matches the node's `Int1="128"` |
| `0x34` | `samplecol` — sample colour, returns float4 | 1:1 alignment |
| `0x1D` | `eq` | 1:1 alignment |
| `0x10` | swizzle, 2-bit packed component mask | mask values decode to `.w` and `.xyz` |
| `0x01` | read system variable (`$pos`) | 1:1 alignment |
| `0x03` | a distinct variable-access kind (which kind is open) | 3,603 instructions in 34 specimens — retraction itself withdrawn, see below |
| `0x20` | `gteq` (probable) | position in graph 1; not a 1:1 aligned run |

**Why `0x07` and `0x0C` are the two largest unidentified families** — 1.46M and 1.16M
instructions — is now obvious in hindsight. This is an imperative language with variables
and statement sequencing, so assignment and `sequence` dominate any program, exactly as
`mov` dominates a machine-code histogram. Their frequency was a clue, not an obstacle.

### What this opens up

70 named node types are available as labels, and the alignment method needs only a
self-contained specimen containing the node of interest. `neg`, `and`, `or`, `not`, `lr`,
`gt`, `min`, `max`, `abs`, `mod`, `exp`, `log2`, `pow2`, `atan2`, `lerp`, `rand`,
`toint1`, `tofloat`, `mulscalar`, `cartesian` and `samplelum` all remain, each with a
known meaning and a countable presence in the sources.

### The logic and comparison block — solved as a unit

Nine consecutive op-ids form the boolean block. `ie_particles` (1588 authored nodes,
ratio 1.10) has exactly seven unassigned logic node types and seven unassigned bool
op-ids, and sorting both by count pairs them monotonically:

| node | count | op-id | count |
|---|---|---|---|
| `and` | 73 | `0x1A` | 70 |
| `gt` | 30 | `0x1F` | 30 |
| `not` | 21 | `0x1C` | 20 |
| `lr` | 15 | `0x21` | 14 |
| `lreq` | 8 | `0x22` | 8 |
| `or` | 6 | `0x1B` | 6 |
| `gteq` | 2 | `0x20` | 2 |

Count ordering alone would be weak evidence — the residual ±1–3 comes from library
content, and on `ie_curve` (ratio 2.82) the counts diverge badly. It is corroborated
three independent ways:

**1. Arity.** `not` is the only unary operation in the block:

| op-id | name | opcode | operands |
|---|---|---|---|
| `0x1A` | and | `085A` | 2 |
| `0x1B` | or | `085B` | 2 |
| `0x1C` | **not** | `045C` | **1** |
| `0x1D` | eq | `085D` | 2 |
| `0x1F` | gt | `085F` | 2 |
| `0x20` | gteq | `0860` | 2 |
| `0x21` | lr | `0861` | 2 |
| `0x22` | lreq | `0862` | 2 |

Logical negation is the only member that *should* be unary, and it is the one the count
ordering independently picked out.

**2. `eq` is fixed by the 1:1 alignment** in `find_alpha0_pixel`, where `085D` sits at the
position of the source's `eq` node.

**3. The two sRGB specimens pin `gt` and `lreq` structurally.** Both use a threshold
comparison feeding `select(cond, ifpath, elsepath)`, and the arms are swapped between
them — which is only consistent if the two comparisons point opposite ways:

```
encode  select( 0862(L, 0.00031308), 12.92*L,   pow_branch )   =>  0862 is  L <= t
decode  select( 085F(S, 0.04045),    pow_branch, S/12.92   )   =>  085F is  S >  t
```

The domain guard confirms it independently: `select(0862(x, 0), 0, pow)` yields zero when
the comparison holds, so `0862` must be `x <= 0`.

#### A previously-open question, closed

The sRGB section above recorded `0x0862` and `0x085F` as "both less-than-ish, one of
{`<`, `<=`}, indistinguishable". That was wrong in its framing: they are not two
encodings of one comparison but **two different comparisons**, `lreq` and `gt`. The sRGB
function does distinguish them — through the select arm order, which I had not yet read
when the note was written. `0x1E` is present in the corpus but never emitted from
authored graphs; `neq` is absent from the `.sbs` vocabulary, which fits.

### Also identified

**`0x2D` = `atan2`.** 9 of 10 self-contained specimens match exactly, including 51/51 in
`ie_curve` — a 30,646-node file where the other hypotheses all diverge. Matching exactly
in the *large* file is what makes this one convincing.

### Still open in this cluster

`0x11`, `0x17`, `0x32` and `0x33` all matched `ie_particles` closely (`samplelum` 46/46,
`tofloat` 21/21) but **failed across the other specimens** — `0x11` is 2/10, with
`find_alpha0_pixel` showing `0x11`=1 against `samplelum`=0. A single-file count
coincidence among ~17 candidates on each side is cheap; these are recorded as unassigned
rather than promoted. They need a self-contained specimen that isolates them.

## What the ISA is missing — a gap analysis

Mapping all 64 op-ids and cross-referencing against the 70-node `.sbs` language
vocabulary shows three different kinds of absence, which need different responses.

### 1. Instructions that were never there — the ISA is smaller than the language

Several prominent language nodes have no opcode because the compiler **lowers** them:

| language node | uses | lowering | status |
|---|---|---|---|
| `pow2` | 32 | `exp2(ln x · p)` | proven, from sRGB |
| `log2` | 16 | `ln x / ln 2` | proven, from sRGB |
| `mulscalar` | 898 | `mul` at mixed widths | proven, 100% over 12 files |
| `normalize` | — | `dot` → `sqrt` → `div` | proven, from Normalize_RG |
| `instance` | **4,977** | **inlined** | inferred |
| `passthrough` | 41 | eliminated | inferred |

`instance` matters most. It is the second most common unmapped node and has no opcode
because a sub-graph call is **inlined, not called** — there is no call instruction and no
return. That single fact explains the 24x ratio of instructions to authored nodes that
defeated the correlation approach: a `.sbsar` carries every library graph expanded in
place. The two observations explain each other.

So "no `pow`", "no `length`", "no `clamp`", "no `call`" are not gaps in our knowledge.
They are properties of the architecture.

### 2. Structural holes that predict real instructions

The op-id space is laid out in contiguous functional blocks, which makes holes
meaningful:

```
variable access   01 get sysvar   02 ref uid   [03]   04 get local   [05] [06]   07 set
control / aggregate   09 ifelse   [0A]   0B while   0C sequence   0D vector   [0E] [0F]
arithmetic   10 swizzle   11 ?   12 add   13 sub   14 mul   15 div   16 ?   17 ?   18 dot
comparison   1A and   1B or   1C not   1D eq   [1E]   1F gt   20 gteq   21 lr   22 lreq
transcendental   28 sqrt   29 ln   [2A]   2B exp2   [2C]   2D atan2   2E ?   2F ?
sampling   30 ?   31 max   32 ?   33 samplelum?   34 samplecol   [35 .. 3F mostly empty]
```

**`0x1E` is the clearest prediction.** It is the single hole in an otherwise contiguous
nine-slot comparison block, sitting exactly between `eq` and `gt`. It is almost certainly
**`neq`**. It is absent from the corpus because the `.sbs` language has no `neq` node —
authors write `not(eq(...))` — so no authored graph can emit it. This is an instruction
the engine very likely supports that our corpus **structurally cannot reach**, no matter
how large it grows. Only `.sbsar` produced by a different toolchain or a newer compiler
would show it.

**`0x2A` and `0x2C`** sit inside the transcendental block. The language has `sin` (44),
`cos` (34) and `tan` (1), and unlike `pow2` and `log2` these *cannot* be lowered onto
`sqrt`/`ln`/`exp2`. They need real opcodes, and the holes are where they belong.
`0x2E` and `0x2F` are the other candidates.

**`0x03`, `0x05`, `0x06`** are holes in the variable-access block, most likely further
variable classes. Note this **retracts a claim**: I earlier recorded `0x03` = "read input
parameter" from a single `05C3` instruction in `find_alpha0_pixel`. That opcode is not in
the 125-opcode core catalogue — it fails the ≥50-specimen threshold — so the claim rested
on one instance. Withdrawn pending real evidence.

### 3. Missing type and width variants

| operation | observed | notable absence |
|---|---|---|
| `div` `0x15` | float1, float2 | **no integer division at all** |
| `swizzle` `0x10` | float only *in the core catalogue* | ~~no integer swizzle~~ **CORRECTED**: `0A10` is integer swizzle; it fell below the ≥50-specimen threshold (18 files). See below. |
| `vector` `0x0D` | 2, 3, 4 components | no 1-component form (a 1-vector is a scalar) |
| `sub` `0x13` | f1–f3, int1–2 | no float4 |
| `mul` `0x14` | f1–f4, int1 | no int2+ |

The `div` and `swizzle` absences are the interesting ones: either the language forbids
those forms, or they lower to something else. `iswizzle1` must map to an op-id other than
`0x10` — `0x16` (float1, float2, int1) is the only shaped candidate.

### 4. Ranked targets

| op-id | instructions | shape | note |
|---|---|---|---|
| `0x11` | 781,819 | f1, f2, i1, i2 — **nothing wider** | matches the conversion family exactly (`tofloat`, `tofloat2`, `toint1`, `toint2`); target type in the opcode |
| `0x17` | 585,890 | **float1 only** | largest single unnamed op; its scalar-exclusivity is the clue |
| `0x23` | 389,409 | float1 dominant | |
| `0x30` | 289,918 | f1/f2/f3/f4, i2 | width profile nearly identical to `max` (`0x31`) — almost certainly **`min`** |
| `0x32` | 181,524 | float1 only | |
| `0x24` `0x2E` `0x2F` `0x16` | 105k / 68k / 47k / 59k | | trig and conversion candidates |

### 5. Type 3 is unexplained

Types 0/1/2 are bool/float/int. **Type 3 occurs at exactly one op-id** — `0x19`, 1,358
instructions across 106 specimens. That is far too frequent to be noise and far too rare
to be a core arithmetic type. The language has `get_string` (3 uses), which does not
account for it. Unidentified.

### Integer swizzle, type conversion, and min/max

#### `0x0A10` is integer swizzle — and a correction

The gap analysis above claimed "**no integer swizzle**, yet `iswizzle1` exists in the
language". That was wrong, and the reason is methodological: `0x0A10` occurs 181 times
across **18** specimens, below the ≥50-specimen threshold used to build the catalogue.
The filter that removes decode noise also removes genuinely rare instructions.

The evidence, three independent ways:

1. **Ground truth.** Of the 8 specimens whose `.sbs` source contains `iswizzle*`,
   **8 contain int-typed op-id `0x10`**. (42 of 151 files *without* authored `iswizzle`
   also contain it — expected, since inlined library graphs use it.)
2. **Mask fingerprint.** Swizzle's second operand is a packed 2-bit-per-component mask,
   so its width scales with component count. Measured on the known float forms:

   | opcode | operand 2 below 4 | below 64 | top masks |
   |---|---|---|---|
   | `0910` swizzle1 | **100.0%** | 100.0% | 1, 0, 2, 3 |
   | `0950` swizzle2 | 46.2% | **100.0%** | 1, 4, 14, 0 |
   | `0990` swizzle3 | 47.4% | **100.0%** | 0, 33, 16, 1 |
   | `09D0` swizzle4 | 0.2% | 0.5% | 78, 68, 80 (`78` = `0b01001110` = 2,3,0,1) |
   | `0A10` **int** swizzle1 | **86.0%** | 93.0% | 1, 0 |

   Contrast `0912` add at 1.2% below 4. `0A10` sits with the swizzles, not the arithmetic.
3. **Direct reading.** In `serverhouse__roofing_007` the same idiom repeats six times:

   ```
   0A42  int2    ref by uid          an int2 graph parameter
   0A10  int1    swizzle (·, 0|1)    masks are 0 or 1 - exactly an int2's components
   0511  float1  convert (·)
   ```

#### `0x11` is type conversion — confirmed by operand type inversion

The trailing `0511` above is the second result. Op-id `0x11` takes one operand, and the
type of the value feeding it is the **inverse** of the type it produces:

| opcode | produces | source-value type | n |
|---|---|---|---|
| `0511` | float1 | **int 100%** | 1,107 |
| `0551` | float2 | int 98% | 698 |
| `0611` | int1 | **float 100%** | 2,006 |
| `0651` | int2 | **float 100%** | 7,211 |

So `0511` = `tofloat`, `0551` = `tofloat2`, `0611` = `toint1`, `0651` = `toint2`. The
op-id's coverage — float1, float2, int1, int2 and *nothing wider* — matches the language,
which offers conversions only at widths 1 and 2 in any quantity.

#### `0x30` = `min`, `0x31` = `max` — from the clamp idiom

`saturate(x)` is `min(max(x, 0), 1)`, and clamping is pervasive in texture graphs, so the
two ops should be distinguishable by which constant they are paired with and by how they
nest. Both tests agree:

| | constant `0.0` | constant `1.0` | n |
|---|---|---|---|
| `0x30` | 28.7% | **67.7%** | 13,889 |
| `0x31` | **91.4%** | 2.7% | 10,611 |

| nesting | count |
|---|---|
| `0x30` consumes `0x31` | **8,917** |
| `0x31` consumes `0x30` | 822 |

A 10.8:1 preference for `0x30(0x31(x, 0), 1)` — the inner operation clamps against zero
and the outer against one. `0x31` = `max`, `0x30` = `min`. This re-derives `max` from
evidence wholly independent of the residual matcher that first proposed it.

#### Methodological note

Two of these three were sitting below the catalogue's frequency threshold. A filter tuned
to reject mis-decoded noise necessarily also rejects rare real instructions, and the
distinction between them is **structural, not statistical**: `0A10` is real because its
operand fingerprint matches the swizzle family and its presence tracks an authored node
type, not because it is common. Rare opcodes need a coherence test, not a count.

### Finishing the transcendental block

Five more operations, each established by a different kind of evidence.

| op-id | opcodes | name | evidence |
|---|---|---|---|
| `0x23` | `0523` `0563` | **`abs`** | residual match, 100% across 4 specimens |
| `0x16` | `0916` `0956` `0A16` | **`mod`** | counts 10/9, 1/1, 4/3 on low-contamination specimens; moduli are `1000000`, `65536`, `2`, `1` |
| `0x2E` | `096E` | **`cartesian`** | 360x enrichment as an angle consumer |
| `0x2F` | `0D2F` `0D6F` | **`lerp`** | three operands; **32/32 exact** in `ie_curve` |
| `0x32` | `0532` | **`rand`** | takes a constant operand 67.3% of the time; every real maths op takes one 0.0% |

#### `rand` — the constant-operand signature

The cleanest discriminator of the session. A unary maths function applied to a constant
would be constant-folded by any compiler; a seeded random generator cannot be, because
the seed *is* the argument. Measured over the corpus:

| op-id | operand is a constant | n |
|---|---|---|
| `0x32` **`rand`** | **67.3%** | 127,382 |
| `0x17` (unknown) | 0.0% | 385,803 |
| `0x23` `abs` | 0.0% | 262,234 |
| `0x28` `sqrt` | 0.0% | 19,528 |
| `0x2B` `exp2` | 0.0% | 510,398 |

A categorical split, not a gradient. This also explains why `rand` defeated the residual
matcher for several rounds: its isolating graph is `{const_float1, rand}`, two nodes, so
the predicted multiset is `{const}` and the residual is whatever the second instruction
is — degenerate. Structure settled what counting could not.

#### `cartesian` — found by chasing an angle

`mul` takes the constant `2*pi` as its first operand 78.6% of the time, which marks its
result as an angle. Propagating one hop through `add`/`sub` (a phase offset) and asking
what consumes the result:

| opcode | type | args | share | baseline | enrichment |
|---|---|---|---|---|---|
| `096E` | float2 | 2 | **99.6%** | 0.3% | **360x** |

Two operands, float2 result, consuming an angle: polar-to-cartesian, taking
`(radius, theta)` and returning `(x, y)`. `0x2E` had also been the single structural hit
for `cartesian` earlier, from an unrelated method.

#### `lerp` — arity plus an exact count

`0D2F` carries **three** operands, which by itself rules out every remaining unary and
binary candidate, and `0D6F` is its float2 form. `ie_curve` has 32 authored `lerp` nodes
and exactly **32** `0x2F` instructions. Matching exactly in a 30,646-node file is worth
far more than matching in a small one, where coincidence is cheap.

#### `sin` and `cos` are still not located

The two holes `0x2A` and `0x2C` remain empty, and no opcode has been confirmed for the
trig functions. `0526` and `0527` consume angles at 1.9x and 1.3x enrichment, but on
n=25 and n=17 — far too thin. Against them: `LGMLtools__time_var_test` has `sin` in its
source and **zero** occurrences of either, while carrying three `096E`. That is a hint
that `cartesian` may be the engine's trig primitive with `sin`/`cos` lowered onto it, but
the compiled `cartesian` results in that file are consumed as float2 vectors, not
swizzled to extract a component, so the hypothesis is unsupported as it stands. Recorded
as open.

#### `0x17` — the largest unknown, fingerprinted but unnamed

585,890 instructions, float1 only, unary. What is known about it:

- its operand is **never** a constant (0.0% of 385,803), so it is a real computation
- it is fed by `swizzle` 61.9% of the time — a scalar pulled out of a coordinate
- its dominant consumer is `lr` (less-than) at **103.5x enrichment**

A scalar derived from coordinates and then compared against a threshold. That shape fits
a fractional or wrapping operation, but `fract` is absent from the `.sbs` vocabulary and
no candidate has been confirmed. It also self-nests 192 times, which argues against
`neg` (double negation folds). Deliberately left unnamed.

**`neg` is a real instruction, not a lowering.** Testing the two ways it could have been
lowered: `mul` shows no spike at `-1.0` among its constant operands, and `sub` shows no
`0.0` in operand 0 (its top value there is `1.0` at 75.7%, the `1-x` invert idiom; `mul`
operand 0 is `2*pi` at 78.6%). So `neg` has its own opcode somewhere still unidentified.

### Chasing `neg` — probable, not proven  
**[SUPERSEDED: confirmed as `0x17` via `ie_processing`; the objections below are explained by compiler CSE. See "0x2A = exp" above.]**

`neg` is the largest unmapped language node (5,653 uses) and is definitely a real
instruction: neither lowering route shows up, since `mul` has no `-1.0` spike among its
constant operands and `sub` has no `0.0` in operand 0.

**`0x17` is the leading candidate, on counting evidence.** `ie_particles` is the decisive
specimen because its instruction-to-node ratio is 1.08, so almost nothing comes from
inlined libraries. Its unmapped columns:

| unmapped nodes | | unmapped op-ids | |
|---|---|---|---|
| `neg` | 16 | `0x17` | 21 |
| `pow2` | 3 | `0x26` | 11 |
| | | `0x27` | 11 |

`pow2` is *lowered* (proven from sRGB: `exp2(ln x / ln 2 * p)`), so it contributes no
unmapped instruction. That leaves `neg` = 16 as the only unmapped node generating code,
against `0x17` = 21. In `ie_curve`, `neg` = 181 with a library inflation factor of 2.82
predicts ~510 against 589 observed. Share-wise: 0.591% vs 0.68%, and 1.008% vs 1.22%.

`0x17` also has the right shape — a full width family (`0517` f1, `0557` f2, `0597` f3,
`05D7` f4, `0617` int1), exactly like the confirmed `abs` at `0x23`. The earlier claim
that it was "float1 only" was another artifact of the catalogue threshold.

**Three observations argue against it, and none is explained:**

1. Its dominant within-run consumer is `lr` (less-than) at **103.5x enrichment**, 48.7%
   of consumers. Negation feeding a comparison that heavily has no natural reading.
2. The exact structure predicted by `ie_curve`'s isolating graph —
   `add(U(get_float2), const_float2)` — **does not occur anywhere** in the compiled file.
3. All 50 float2-form (`0557`) instances in `ie_curve` are fed by `sub` and consumed by
   `add`, not fed by a `get` as that graph requires.

A differential test — how often the operand `x` and result `u(x)` are both consumed by
one later instruction, which should be elevated for negation's `(x, -x)` mirror idiom —
came back at 0.1% for `0x17` against 0.0-0.2% for `abs`, `sqrt`, `exp2` and `convert`.
No discrimination.

**Verdict: recorded as probable, not confirmed.** The counting evidence is good and the
structural evidence is absent or contrary, and on this format counting evidence has been
wrong before. Settling it needs a specimen where a `neg` graph compiles into a cleanly
decodable run — the current failures may be decode-coverage artifacts rather than real
contradictions.

### `0x26` and `0x27` move in lockstep

Both are float1 unary ops with no wider forms, and their counts track each other
closely: 11 and 11 in `ie_particles`, 123 and 106 in `ie_curve`, 2 and 3 in
`Bruno_Caustics`. Operations that appear in near-equal pairs are ones used together, and
`sin`/`cos` is the obvious candidate for a matched float1 unary pair in a texture DSL.
Both also showed (weak, n=25 and n=17) enrichment as consumers of angles.

Neither `ie_particles` nor `ie_curve` has an authored `sin` or `cos`, yet both contain
these opcodes — consistent with them arriving via inlined library graphs, which is how
`iswizzle1` behaved too. Suggestive, still unconfirmed.

## The record directory is real — my "misidentification" was itself wrong

The previous section concluded the structure at `0x38` was **not** a record directory,
because its entries pointed into the header and at non-opcode tokens. That conclusion was
wrong. **The entries are correct; they simply need the 52-byte skew applied** — the same
`PTR_SKEW = 52` constant already established for the value-table pointer
(`table_end == u32_at(0x2C) + 52`).

Seen directly in `GrayscaleConvert` (384 bytes), whose directory holds `0x14`, `0x28`:

```
0x0048   ...8821    <- image-input record       0x48 - 0x14 = 0x34 = 52
0x005C   ...8828    <- gray-op record           0x5C - 0x28 = 0x34 = 52
```

Both differ by exactly 52. `Substance_graphA`'s single entry `0x10` reaches the `880D`
uniform-colour record at `0x44`, again +52. Corpus-wide, `e + 52` is by far the best of
six candidate formulas:

| formula | entries landing on a record tag |
|---|---|
| **`e + 52`** | **59.0%** |
| `e + base + 52` | 34.6% |
| `e + dir0 + 4*count` | 0.9% |
| `e + dir0` | 0.3% |

The lesson: the earlier check was right that entries are not *absolute* offsets, but wrong
to conclude the structure was misidentified. A pointer being relative is not a pointer
being fictional. I should have tried the skew already documented elsewhere in these notes
before discarding the interpretation.

## Record tags are structured: `NN || type`

The 41% that `e + 52` appeared to miss were not misses. They land on tags outside the
`0x88xx` family — `4404`, `7702`, `6604`, `5504`, `4402`, `8602` — and those high bytes
are not arbitrary:

| high byte | entries | share | note |
|---|---:|---:|---|
| `0x88` | 292,329 | 59.0% | = 8 x 0x11 |
| `0x77` | 52,866 | 10.7% | = 7 x 0x11 |
| `0x66` | 42,204 | 8.5% | = 6 x 0x11 |
| `0x44` | 39,826 | 8.0% | = 4 x 0x11 |
| `0x55` | 20,037 | 4.0% | = 5 x 0x11 |
| `0x99` `0xAA` `0xBB` `0xCC` `0x22` `0x33` `0x00` | | 5.5% | = 9,10,11,12,2,3,0 x 0x11 |

**95.0% of directory entries land on a token whose high byte is a nonzero repeated nibble**,
against 3.4% at random 4-aligned offsets — a 27.7x enrichment (the original 96.5% figure
included `0x00` and had no baseline; see the corrected measurement below) — that is, a byte whose two nibbles are equal. The low byte takes 41 distinct
values and is the record **type**: `0x02` (31.2%), `0x04` (23.2%), `0x1E`, `0x18`, `0x29`,
`0x08`, `0x0E`, `0x03`.

This retroactively explains a constant recorded much earlier. The image resource tag was
documented as `byte[1] = constant 0xAA, the locatable marker`. `0xAA` is `10 x 0x11` — it
is not a magic marker at all, it is this same `NN` field with N = 10. And the resource
tag's `byte[0] = 0x20 grayscale / 0x21 colour` is the type byte, the same low byte as the
already-identified `0x8820` / `0x8821` image-input records. So `0x8820` and `0xAA20`
are the same record *type* at different `N`.

### What this unblocks

The record stream was the largest remaining unknown — 154 apparent tags with 7 identified,
and no framing. It is now considerably more tractable:

- **records can be located**: directory entry + 52, verified on 495,279 entries
- **tags decompose** into `N` (13 values) x `type` (41 values), rather than 154 unrelated
  constants
- `N` is an open question. Values 4-8 account for 90.3%. It is not a length (no tag shows
  a dominant fixed gap), and it may be a role or class distinction, since the same type
  byte appears under different `N`.

Next: determine what `N` encodes, and whether record length can be derived from the tag
the way instruction length is derived from the opcode.

### [SUPERSEDED] The "record directory" is misidentified — a load-bearing error

The structure at `(dir_ref - 4) + 0x38` has been described throughout these notes as a
**record directory** holding absolute offsets to records, and `validate_corpus.py` reports
it passing 493/493. That validation is much weaker than it looks:

```python
r["ok_dir"] = (all(ents[i] < ents[i+1] for i in range(cnt-1))
               and 0 < ents[0] and ents[-1] < start)
```

It checks only that the values **ascend and stay in range**. Many things satisfy that.
It never checks that an entry points at a record, or even at an instruction boundary.

Direct inspection says it does neither:

```
GrayscaleConvert.sbsasm   size=384  dir@0x38 count=2
   0x0014  token 001C   not an opcode      <- inside the 0x38-byte header
   0x0028  token 0001   not an opcode      <- inside the header

find_alpha0_pixel.sbsasm  size=784  dir@0x38 count=5
   0x0020  token 0002   not an opcode      <- inside the header
   0x0034  token 0000   not an opcode      <- inside the header
   0x01A8  token 098C   opcode, len 3
   0x0208  token 0000   not an opcode
   0x0234  token 0001   not an opcode
```

Two of the five point into the *header*, which is only 0x38 bytes long. Across 243
specimens and 464,575 consecutive-entry gaps, the most common token at an entry offset is
`0x0000` (75,962 occurrences) — not a valid opcode — and the identified `0x88xx` record
tags appear at entries essentially never. Per-tag gap lengths show **no** dominant fixed
size for any tag (0 of 19,516 tags reach an 80% modal length), which a table of framed
records would.

### Why this matters

`code_region.code_spans()` takes `ents[0]` as the start of the instruction stream. Every
opcode count, every catalogue figure, and every ground-truth correlation in these notes
rests on that. The bounds have been *approximately* right — `ie_processing` decodes to
99.8% coverage and eleven operations match their authored counts exactly — so the
downstream results stand. But they stand on an assumption now known to be wrong, and the
error already bit once: the span was capped at `ents[-1]`, discarding 95% of
`ie_processing` until that was found and fixed.

### What it might be

The values ascend, stay in range, and land indifferently on header fields, instruction
boundaries and operand tokens. That pattern fits a **relocation or fixup table** — a list
of positions holding values that need patching at load time — better than an index of
anything. `dir_count` ranges from 1 to 7,557 with a median of 231 and correlates with
file size at only r = 0.084, which also fits fixups (dependent on how many external
references a package makes) far better than records (which should scale with size).

**This is the next thing to settle.** It is foundational rather than incremental: it
underpins the region bounds that every statistic in this document depends on.

### Record structure — what the directory now buys us

With records locatable (`directory entry + 52`), consecutive entries bound each record, so
lengths are measurable directly.

**Records are variable-length.** Of the 18 most common tags, only one — `880D`, the
fixed-layout uniform RGBA colour — has a dominant modal size (79% at 32 bytes). The rest
spread across many sizes. There is no per-tag fixed length, so records are not framed the
way instructions are.

**`N` is not a size class.** Median lengths by `N`: `0x44`→56, `0x55`→104, `0x66`→108,
`0x77`→100, `0x88`→84, `0x99`→40, `0xBB`→20. No monotonic relationship.

**`N` is a per-record property, and remains unidentified.** It varies within a single file
— 47 specimens carry 13 distinct `N` values, and only 67 carry just one. It does not track
the assembly version (`0x88` is 46-66% under every version from v2 to v9). Every record
type appears under several `N`, with `0x88` usually dominant. So `N` is neither a file
attribute, a version, nor a length.

**Records embed instruction streams.** Reading type-`0x04` records under five different
`N` in one specimen, all end with `0A42 <uid>` — an int2 reference instruction — and one
continues `1640 0000 FFFFFFFF`, a padded int2 constant of `(-1, -1)`. Testing this
systematically: for each record bounded by consecutive directory entries, is there a
header size after which the remainder decodes *exactly* as instructions under the length
rule?

```
399,559 records tested
tails decoding exactly as instructions: 157,478  (39.4%)
modal header sizes: 22 (10.5%), 26 (9.1%), 18 (5.9%), 8 (4.1%), 12 (2.8%)
```

39.4% is far above chance but not decisive, and the header sizes cluster rather than
converging on one value — consistent with a variable-size header, or with the directory
not bounding every record exactly.

### Two rejected sub-hypotheses

Both came from reading a single specimen and did not survive the corpus:

- **`u32[3]` is a self-pointer at a fixed skew.** In `ChristmasTreeOrnament` four of five
  records had `offset - u32[3] == 20` exactly. Corpus-wide the delta is 36 (13.7%),
  28 (7.7%), 32 (4.3%), 20 (2.6%) — no fixed skew. A per-file coincidence.
- **`u16[1]` is the constant `0x0319`.** It was identical across all five records in that
  file, but takes **152 distinct values** across the corpus, and most files carry several.
  Its low byte is often `0x18` or `0x19`, which may mean the record framing starts
  elsewhere than assumed.

### Two more bugs in the code-region bounds

Fixing the `ents[-1]` cap introduced a regression, and uncovered a pre-existing one.
Both were found by noticing that three specimens which had previously worked —
`PolarCoordinates2Grayscale`, `radial_blur_color`, `radial_blur_grayscale`, all
known-algorithm files used earlier in this document — had silently dropped to **zero**
decoded instructions.

1. **`lo` used the raw `ents[0]`.** Directory entries are not absolute; they carry the
   +52 skew. Using one as a code offset put the region start inside the 0x38-byte header.
   Corrected to `dir0 + 4*cnt` — just past the directory — which needs no skew and is
   well-defined for every file.
2. **A `cnt < 3` guard rejected small files.** A graph with one or two records is
   perfectly legal; `GrayscaleConvert` has two. Relaxed to `cnt < 1`.

After both fixes:

```
specimens producing a non-empty code region : 395/395   (previously some were empty)
PolarCoordinates2Grayscale : 32 instructions   (was 0)
radial_blur_color          : 54 instructions   (was 0)
ie_processing              : 11/11 authored counts still exact
```

`ie_processing` served as the regression test throughout — any change to the bounds that
broke its eleven exact matches would have been wrong.

**The lesson repeats.** Three separate bugs in this one function, each silently returning
*plausible* output: a truncated span, a span starting in the header, and an empty span.
None raised an error. The reason all three were eventually caught is that a ground-truth
specimen existed whose authored node counts had to match exactly — without
`ie_processing`, a wrong region boundary just looks like slightly different statistics.

### Records are 4-aligned; `u16[1]` is not an index

Two facts settled this iteration:

- **Every record starts at a 4-byte boundary** — 418,840 of 418,840. This confirms the
  much earlier observation that the `0x88xx` family is 4-aligned, now measured on the
  whole located set rather than a sample.
- **`u16[1]` is not the record's own directory index** (0.0% match). It is below
  `dir_count` in 93.2% of cases, but that is unsurprising for a field holding small
  values and is not evidence of an index. Its meaning is still open.

### The isolating-graph route is exhausted

Re-running the closure with the corrected regions and the full 44-entry name table
admitted **nothing new**. Every language node that can be isolated in a graph with exactly
one unknown has been mapped. What remains — `floor`, `sin`, `cos`, `log2`, `pow2`,
`passthrough`, `tan`, `log`, `swizzle4`, `get_string` — is either lowered by the compiler
or too rare to isolate in this corpus. Naming the rest needs a different technique or
different specimens, not more passes of the same method.

### `0x24` = `floor`, from the fract idiom

`0x24` was the largest unnamed operation — 112,662 instructions in 353 specimens — and had
only a single weak data point (`floor` 1 vs `0x24` 1 in `ie_processing`). The scale
mismatch against 122 authored `floor` nodes made that look wrong.

The test that settles it: `fract(x)` is `x - floor(x)`, so if `0x24` is `floor` its operand
and its result should frequently feed one later instruction, and that instruction should be
`sub`.

| unary op | operand and result share a consumer | n | via |
|---|---:|---:|---|
| **`0x24`** | **10.17%** | 67,001 | **`sub` 99%** |
| `exp` `0x2A` | 1.04% | 4,152 | scattered |
| `rand` `0x32` | 0.72% | 150,567 | scattered |
| `ceil` `0x25` | 0.27% | 17,203 | scattered |
| `neg` `0x17` | 0.09% | 389,148 | `sub` 58% |
| `abs` `0x23` | 0.02% | 262,984 | scattered |

100x the rate of `abs`, and the shared consumer is `sub` in 99% of cases. Operand order is
**x first in 6,758 of 6,758** — `x - floor(x)`, never `floor(x) - x`.

The scale mismatch is explained by inlining: `floor` is rare in authored graphs but
`x - floor(x)` is pervasive in the library graphs that get expanded in place, so 122
authored nodes can produce 112,662 instructions.

### `0x26` = `cos`, `0x27` = `sin`

The same style of test. Trig partners are applied to the *same* angle in any rotation or
polar conversion, so a genuine sin/cos pair should share operands constantly:

```
unary 0x26 instances : 8,632
unary 0x27 instances : 8,491
taking the SAME operand : 7,844   = 90.9% of 0x26, 92.4% of 0x27
```

Against a baseline where every other unary op shares an operand with `0x26` at **0.5% or
less** — `0x01` 0.5%, `0x25` 0.3%, `0x23` 0.2%. That is a 180-fold enrichment, and no
other pair of operations in the ISA behaves this way.

Which is which comes from component order. When both results feed one vector construct:

```
0x26 as the earlier component : 223
0x27 as the earlier component :   3
```

Building `(x, y)` from an angle gives `(r·cos θ, r·sin θ)`, cosine first. So `0x26` = `cos`
and `0x27` = `sin`.

**The weaker part of this argument, stated plainly:** the assignment of *which* is cosine
rests on that (x, y) convention rather than on direct evidence, and the authored counts
point mildly the other way (`sin` 44 vs `cos` 34 in source, against `0x26` 9,794 vs `0x27`
9,125). Those counts are dominated by library inlining and are too small to weigh against
223:3, but if a specimen ever pins one of the two directly, this is the pair to re-check.

That the two are `sin` and `cos` **in some order** is not in doubt.

### `0x35` = `log2`, and the last unknowns are noise

`0x35` was the final substantive unnamed operation. The embedding test settles that it is
real — and it is the most deeply embedded opcode measured anywhere in this work:

| opcode | n | median run | in runs ≥50 | verdict |
|---|---:|---:|---:|---|
| **`0535`** | 2,858 | 97 | **84.6%** | **real** |
| `0526` cos | 7,396 | 6,416 | 74.2% | real |
| `0912` add | 300,485 | 324 | 66.9% | real |
| `0524` floor | 55,835 | 328 | 65.7% | real |
| `0808` (`0x08`) | 181 | 3 | 29.8% | noise |
| `067C` (`0x3C`) | 178 | 17 | 18.5% | noise |
| `0A3D` (`0x3D`) | 1,032 | 5 | 7.8% | noise |
| `0B19` type-3 | 14,289 | 2 | 6.7% | noise (known) |
| `0648` (`0x08`) | 5,513 | 3 | **0.6%** | noise |
| `0448` (`0x08`) | 2,890 | 2 | **0.3%** | noise |

So `0x08`, `0x3C` and `0x3D` join type 3 as decode artifacts, and `0x35` is the only one
left standing.

#### What it computes

`0x35` appears in an idiom identical across every site examined:

```
0603  i1  get           (int variable)          n
0511  f1  conv          int -> float
0535  f1  ?35           (that)                  a
0525  f1  ceil          (a)                     c
0D00  f1  const  = 0.5
0914  f1  mul           (c, 0.5)
0524  f1  floor         (that)                  lo = floor(c/2)
0913  f1  sub           (c, lo)                 hi = c - floor(c/2) = ceil(c/2)
094D  f2  vector        (hi, lo)                v  = (ceil(c/2), floor(c/2))
1140  f2  const  = 4, 4
0971  f2  max           (v, (4,4))              clamp each half to >= 4
0953  f2  sub           (that, (4,4))
056B  f2  exp2          (that)                  2^(size - 4)
```

`c` is split into two near-equal halves which are then **clamped to a minimum of 4 and
exponentiated**. Substance expresses output size as a log2 exponent with a minimum of
2^4 = 16 pixels, so those halves are a log2 width and a log2 height, and `c` is a log2
area. Only a base-2 logarithm makes the chain coherent: `0x35` = `log2`.

`ie_pcloud`, the single specimen in the paired corpus that authors a `log2` node, has 4 of
them and 5 `0x35` instructions. `0x35` also appears in 40 of 108 specimens that author no
`log2` at all, which is expected — this size arithmetic lives in the engine's own graphs,
which are inlined.

#### A false negative caused by my own filter

The first correlation test reported **0 of 2** `log2` source-users containing `0x35`, which
looked like a clean refutation. It was an artifact: that test discarded runs shorter than
8 instructions, and `0x35` lives in short runs. Removing the filter turns 0/2 into 1/1.

This is the second time a screening threshold has manufactured a wrong answer — the ≥50
specimen filter hid `0A10`, `0x2A`, `0x1E` and `0x35` itself, and now a run-length filter
inverted a correlation. Any filter applied before a question is asked can decide the
answer. Filters used for noise rejection must be re-examined whenever they sit upstream of
a test, not just when the result looks wrong.

#### The instruction set is now mapped

Every op-id above the noise band has an identified meaning. What remains unnamed is
noise (`0x08`, `0x19`, `0x3C`, `0x3D`) or genuinely absent. The remaining `.sbs`
vocabulary entries — `passthrough`, `get_string`, `tan`, `swizzle4`, `ivector2` — are
either eliminated by the compiler or have fewer than five uses across the entire corpus.

### The `NN` tag claim, now with a baseline

The claim that record tags carry a repeated-nibble high byte was originally supported by
"96.5% of directory entries land on such a token" — with **no baseline**. That was an
incomplete argument, and the raw figure was inflated: `0x00` is itself a multiple of
`0x11`, and `0x00` is the commonest high byte at arbitrary offsets.

Measured properly, against random 4-aligned offsets drawn from the same span:

| position | high byte is a nonzero repeated nibble (`0x11`…`0xFF`) |
|---|---|
| directory entry + 52 | **95.0%** (413,874 / 435,849) |
| random 4-aligned offset | **3.4%** (14,914 / 435,788) |
| uniform chance | 5.9% |

**27.7x enrichment**, and the random rate sits *below* uniform chance because instruction
opcodes — whose high bytes are `0x05`, `0x09`, `0x0A`, `0x0D` — dominate the body. The
corrected figure is weaker in isolation but far stronger as evidence, because the
alternative is now quantified rather than assumed.

### Records are flat, not nested

If the directory listed only top-level records, tags would appear inside the gaps between
consecutive entries. Testing that properly requires the *observed tag vocabulary*, not a
repeated-nibble test — because repeated-nibble bytes are common in ordinary float data:
`0xCCCD` is the tail of 0.1, `0xAAAB` of 1/3, `0x3333` of 0.7, and `0xFFFF`/`0xFFFE` are
the int sentinels -1 and -2. A naive scan reported 47.8% of records containing interior
"tags"; nearly all were constants.

Against the 138 tags actually seen at directory targets:

```
435,101 records
  0 interior tags : 426,119  (97.9%)
  1 interior tag  :   8,552  ( 2.0%)
  2+              :     430  ( 0.1%)
```

**97.9% of records contain no interior tag.** Records do not nest, and the directory
enumerates them completely — so consecutive entries give exact record boundaries, and the
whole record stream is a flat, fully-delimited sequence.

### Where the record stream stands

| property | status |
|---|---|
| location | **solved** — directory entry + 52 |
| alignment | **solved** — 4-byte, 418,840/418,840 |
| enumeration | **solved** — directory is complete, records are flat |
| boundaries | **solved** — consecutive directory entries |
| tag structure | **solved** — `NN` (13 values) x type (41 values), 27.7x over baseline |
| meaning of `NN` | open |
| field layout | open |
| type semantics | open — 7 of 41 types identified |

The framing problem is closed. What remains is semantics: what `NN` distinguishes, and
what the bytes inside a record mean.

### Record header layout

With records exactly delimited, instances of one tag can be aligned and compared slot by
slot. Over 180 specimens, capped at 4,000 instances per tag:

| tag | `u32[0]` | modal | `u32[1]` | modal | `u32[2..]` |
|---|---|---|---|---|---|
| `8802` | `0x00198802` | 90% | `0x00000102` | 20%, 46 distinct | high-cardinality |
| `8804` | `0x03198804` | 83% | `0x0000003F` | 59%, 19 distinct | high-cardinality |
| `881E` | `0x0019881E` | 97% | `0x00000140` | 70%, 39 distinct | high-cardinality |
| `880D` | `0x0109880D` | 64% | — | 2,911 distinct | high-cardinality |
| `8818` | `0x0B198818` | 78% | `0x0000000A` | **92%**, 7 distinct | high-cardinality |

So the first word is `[tag u16][class u16]`, and **the class word is nearly constant per
tag** — 5 to 13 distinct values, 64–97% modal. This resolves an earlier confusion: that
field was measured at 152 distinct values corpus-wide and dismissed as meaningless, but
the variation is *between* tags, not within one.

`u32[1]` is a small enumeration or flag word — 7 to 46 distinct values with a high modal
share. `u32[2]` onward are high-cardinality and mostly smaller than the record's own
offset, so they are plausibly pointers or identifiers.

#### The type-3 "noise" was a record field

`0x0B19` was earlier shown to be a non-instruction by embedding depth and written off as
decode noise. It is now identifiable: **`0x0B19` is the class word of `8818` records**,
appearing at a 4-aligned position and read as an opcode by a scanner that does not know
where records begin. The verdict that it is not an instruction stands; the description of
it as random noise was wrong. It is a real structural field in the wrong frame.

The same is likely true of some other "noise" tokens, and it is a useful reminder that
*not an instruction* and *not meaningful* are different claims.

### What records reference

Testing every record body against the manifest's uid lists:

| tag | contains a manifest **input** uid | contains an **output** uid |
|---|---|---|
| `8818` | 100.0% | 0% |
| `880E` | 99.7% | 0% |
| `8802` | 98.0% | 0% |
| `881E` | 97.8% | 0% |
| `8804` | 93.9% | 0% |

Near-universal input references and **zero** output references. This independently
re-derives two findings established much earlier by different means: records carry input
references, and outputs are positional rather than referenced.

### Records are per-node, not per-graph

Correlating each tag's per-file count against manifest quantities across 247 specimens:

```
                    graphs  outputs  inputs  image-inputs
best |r| over 22 tags:  0.12    0.15     0.08      0.10
```

Nothing above 0.15. Record counts track none of the structures the manifest exposes,
which is consistent with records being the **per-node** graph representation — precisely
the part the manifest does not describe, and the reason this format needs reverse
engineering at all.

### A 152-byte file, accounted for byte by byte

`LGMLtools__Substance_graphA` is the smallest specimen in the corpus: 152 bytes, one
record, two inputs, one output. Every byte is now explained.

```
0x00..0x37  header (all fields previously documented)
0x38        directory[0] = 0x10          -> record at 0x10 + 52 = 0x44
0x3C..0x43  0x00010000, 0x00000000
0x44        RECORD  tag 880D  class 0109
0x48        u32 = 40                     -> 40 + 52 = 0x5C
0x4C        f32 0.366492 \
0x50        f32 1.0       |  RGBA colour
0x54        f32 0.0       |
0x58        f32 1.0      /
0x5C        u16 0x0001
0x5E        u16 0x0A42                   int2 reference opcode (at 2 mod 4)
0x60        u32 0x8366E7B6               uid of $outputsize
0x64        VALUE TABLE  (8,8) then (0)  = $outputsize, $randomseed defaults
0x70        u16 n_out=1, u16 n_in=2
0x74        output uid
0x78..0x87  input descriptors (type, uid) x2
0x88..0x97  footer: count=1, dir_ref=4, dir_ref_end=8, back=48
```

The `880D` record is 32 bytes, matching its measured modal length, and it is a **uniform
RGBA colour node**: four floats, then an embedded instruction giving the node's output
size by reference to `$outputsize`. The reference opcode sits at 2 mod 4 and its u32 uid
at 0 mod 4, exactly as the instruction-alignment rule requires.

### Record types `0x0C` and `0x0D` carry a bytecode pointer

The `u32` at record offset `+0x04` held 40, and 40 + 52 lands on that embedded
instruction. Testing whether that generalises — does `u32[1] + 52` fall inside the record?

Corpus-wide the answer is only **1.6%**, so this is *not* a universal record field. But the
failure is not random: broken down by tag it is almost perfectly bimodal.

| tag | type | inside | rate |
|---|---|---:|---:|
| `770C` | `0x0C` | 410/410 | **100.0%** |
| `880C` | `0x0C` | 2,539/2,549 | **99.6%** |
| `880D` | `0x0D` | 3,049/3,071 | **99.3%** |
| `660D` | `0x0D` | 507/536 | **94.6%** |
| `440D` | `0x0D` | 32/228 | 14.0% |
| `8802` `8804` `8808` `8828` `CC04` `2204` … | others | ~0 | **0.0%** |

**Record types `0x0C` and `0x0D` have a skew-52 pointer at `+0x04` to their embedded
parameter bytecode; other types do not.** *(Later: presence is governed by class-word bit 0,
not by `NN` — see "Class-word bit 0 is the driven-parameter flag".)* And when the pointer does land inside a record,
**99.9% of targets have an instruction opcode at the target or two bytes past it** — so
the field is genuinely a code pointer, not a coincidence of magnitude.

This is the first evidence that **record layout is per-type**, which is what one would
expect of a node-graph format and what makes the remaining 34 unidentified types worth
attacking individually rather than looking for one universal record header.

#### A first crack in `NN`

`440D` is the outlier: same type `0x0D`, but the pointer is valid only 14% of the time
against 94–99% for `660D`, `770C`, `880C`, `880D`. So `NN` changes the record's *layout*,
not merely a label — for one type, `NN = 4` places the field somewhere else or omits it.
That is the strongest handle on `NN` so far.

### Two rejected connectivity hypotheses

- **Record fields hold other records' directory-entry values** (which would give graph
  edges directly). Measured across 388,396 field reads: **0.0%**, against a 0.4% random
  baseline. Records do not reference each other this way.
- **Record fields are earlier-record indices**, the SSA-style scheme the instruction stream
  uses. The test appeared to support it — `u16[4]` "back-references" at 95.9% against 0.2%
  forward — but it is confounded: most u16 values are small and the record index is large,
  so `v < i` is nearly free. The distance distribution gives it away: **83% of "references"
  are at distance ≥64 with no local peak**, where genuine dataflow references cluster
  within a few positions. Discarded.

### The class word is a bitfield

The `u16` at record offset `+2` was mistaken twice: first read as the constant `0x0319`,
then dismissed for having 152 distinct values corpus-wide, then found to be near-constant
per tag. It is none of those things exactly — it is a **bitfield**. Over 413,874 records:

| bit | value | set in |
|---:|---:|---:|
| 3 | `0x0008` | **100.0%** |
| 4 | `0x0010` | 95.2% |
| 0 | `0x0001` | 85.6% |
| 8 | `0x0100` | 46.3% |
| 9 | `0x0200` | 42.4% |
| 7 | `0x0080` | 13.3% |
| 11 | `0x0800` | 10.9% |
| 5, 12, 13, 10, 14 | | 4.2% down to 0.2% |

Bits 0, 3 and 4 form a base of `0x0019` — which is exactly the commonest observed value,
at 39% — and seven further bits vary. They are not random: they track record type.

```
bit  8 set on types: 04 (51%)  18 (13%)  08 (10%)
bit  9 set on types: 04 (56%)  18 (15%)  08 (11%)
bit 11 set on types: 18 (51%)  0E (21%)  16 (10%)
bit  7 set on types: 08 (34%)  29 (33%)  04 (15%)
```

The 147 distinct values are combinations of a handful of flags, not 147 unrelated
constants. This is why every earlier characterisation of the field failed: constancy,
cardinality and per-tag modality are all the wrong questions to ask of a bitfield.

### A record-start test with a measured false-positive rate

**Bit 3 is set in 100.0% of records** — a structural invariant, and one independent of the
tag. Combining it with the `NN` high-byte test:

| test | directory targets | random 4-aligned |
|---|---:|---:|
| `NN` **and** bit 3 | **95.0%** | **2.7%** |
| `NN` without bit 3 | 0.0% | 0.7% |
| bit 3 without `NN` | 5.0% | 20.7% |
| neither | 0.0% | 75.9% |

**35x enrichment, 2.69% false positives.** Every real record carrying an `NN` high byte
also has bit 3 set — the pair never separates — so the value of the conjunction is
entirely in rejecting false positives, which it roughly halves against `NN` alone (27.7x
to 35x). This gives a usable record detector that does not depend on the directory, which
matters for any file where the directory is damaged or unavailable.

### What `NN` does — first concrete evidence

For record types `0x0C` and `0x0D`, the bytecode pointer sits in `u32[1]`:

| tag | `NN` | pointer in slot 1 | modal length |
|---|---:|---:|---:|
| `770C` | 7 | 100.0% | 36 |
| `880C` | 8 | 100.0% | 16 |
| `880D` | 8 | 99% | 32 |
| `660D` | 6 | 95% | 52 |
| `660C` | 6 | 98% | 64 |
| **`440D`** | **4** | **14%** | **20** |

`NN` = 6, 7 and 8 all behave identically; `NN` = 4 does not, and its records are shorter.
So `NN` alters the record's field layout rather than labelling it. Modal lengths are not
monotonic in `NN` (16, 32, 36, 52, 64 across the set), so it is not a size class either.

`NN` also **clusters along directory order at 1.72x** the rate of a shuffled sequence —
consistent with records inheriting it from whichever library graph they were inlined from,
though the effect is mild and other explanations survive.

### `NN` separates static from dynamic parameters

Reading type-`0x0D` records at different `NN` side by side answers what `NN` does, at
least for this type.

**`440D`, 20 bytes** — a *static* uniform colour:

```
+00  tag 440D  class 0118
+04  f32 0.499992  \
+08  f32 0.499992   |  RGBA, all four literal
+0C  f32 0.499992   |
+10  f32 0.499992  /
```

No pointer, no embedded instruction. The colour is a constant baked into the record.

**`880D`, 28 bytes** — the same node with a *driven* colour:

```
+00  tag 880D  class 0219
+04  u32 0x0010E4B4     -> +52 = record+0x14
+08  u32 0x0010E4AC     -> +52 = record+0x0C
+0C  u16 0x0001, opcode 09C2   float4 reference   <- the colour
+10  u32 uid
+14  u16 0x0001, opcode 0A42   int2 reference     <- the output size
+18  u32 uid
```

No literal colour at all. Instead **two skew-52 pointers, each resolving to one embedded
reference instruction** — the float4 that supplies the colour and the int2 that supplies
the size. The pointers are not decorative: `0x0010E4B4 + 52` lands exactly on the `0A42`
reference, and `0x0010E4AC + 52` exactly on the `09C2`.

Across the corpus, for record type `0x0D`:

| tag | `NN` | n | contains a reference opcode | contains 4 floats in [0,1] |
|---|---:|---:|---:|---:|
| `880D` | 8 | 2,825 | **100.0%** | 91.5% |
| `770D` | 7 | 55 | **100.0%** | 100.0% |
| `660D` | 6 | 507 | **95.7%** | 98.4% |
| `440D` | 4 | 228 | **14.0%** | 97.4% |

All four are colour records — the float payload is present throughout. What changes with
`NN` is whether the parameters are **literal or driven**: `NN` = 4 is static, `NN` = 6, 7
and 8 are dynamic. That is why `NN` alters layout while being neither a size class nor a
label, and it fits the earlier observation that `NN` = 4 lacks the bytecode pointer.

It does not yet explain the difference *between* 6, 7 and 8, which all behave alike here.

### A model that did not generalise

The natural next step was to treat "leading pointers" as a universal record field and
count them. It fails:

```
0 pointers, 1 embedded reference : 75.3%
0 pointers, 0 references         : 18.3%
1 pointer,  1 reference          :  2.1%
```

Three quarters of records carry an embedded reference but **no** leading pointer. The
pointer field is real but confined to types `0x0C` and `0x0D`, exactly as the per-type
measurement showed. Records reach their bytecode by position in most types and by explicit
pointer in a few — another instance of the same lesson, that record layout is per-type and
there is no universal header to find.

### Every record type points at its own bytecode, from a type-specific slot

`0x8802` is the commonest record type (101,812 instances). Read directly:

```
+00  tag 8802  class 0019
+04  u32  small (257, 258, 262, 273, 274 …)
+08  u32  small
+0C  u32  small
+10  u32  = record_offset - 0x20   (28-byte records) or - 0x1C (32-byte)
+14  [optional f32 parameter: 0.5, 0.22 …]
+18  u16 0x0001, opcode 0A42, then a u32 uid
```

The field at `+0x10` looks like an inconsistent self-pointer until the skew is applied:
`record - 0x20 + 52` = `record + 20` for the 28-byte form, and `record - 0x1C + 52` =
`record + 24` for the 32-byte form. **Both land exactly on the `0A42` reference
instruction.** It is the same bytecode pointer found in types `0x0C`/`0x0D`, at a
different slot.

Searching every slot for a skew-52 pointer resolving onto a reference opcode gives a
clean per-type answer:

| record type | pointer slot | n | resolves |
|---|---:|---:|---:|
| `0x18` | 4 | 23,166 | **98.9%** |
| `0x0C` | 1 | 2,807 | **97.9%** |
| `0x16` | 3 | 4,988 | **95.2%** |
| `0x03` | 4 | 8,283 | **94.6%** |
| `0x0D` | 1 | 3,780 | **92.7%** |
| `0x02` | 4 | 117,975 | **91.7%** |
| `0x0E` | 3 | 11,027 | 87.2% |
| `0x1E` | 3 | 38,524 | 86.0% |
| `0x04` | 3 | 86,592 | 75.5% |
| `0x14` | 2 | 7,016 | 61.6% |

**86.2% of all records in these ten types (262,321 of 304,158) resolve to their embedded
bytecode.** The parameter expression of a node can now be located directly from the
record, without scanning.

#### The slot is fixed by type; `NN` controls presence

Holding the type fixed at `0x04` and varying `NN`, the slot never moves — it is 3 in every
case where a pointer exists. What varies is whether one exists at all:

| `NN` | 22 | 33 | 44 | 55 | 66 | 77 | 88 | 99 | AA | BB | CC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| has pointer | 99% | 97% | 34% | 67% | 76% | 80% | **91%** | 17% | 5% | 4% | 4% |

So the model is: **slot = f(type), presence = f(`NN`)**. This confirms and generalises the
`440D` finding — `NN` = 4 records are static — but the wider pattern is not a simple count.
Presence is high at `NN` = 2, 3 and 5–8, and low at 4, 9, A, B and C. A count or a size
class would be monotonic; this is not. `NN` remains only partly understood: it determines
whether parameters are literal or driven, but the specific mapping is not a magnitude.

## The node graph — recovered

Records are nodes; **slot 2 of every record is a reference to an earlier record**, and
types `0x02` and `0x03` carry a second reference in slot 3. These are the graph edges.

### Evidence

Testing each slot as an index into the record directory, restricted to one type at a time
(files with ≥50 records):

```
8802 slot 2 : 100% below its own index, 95.8% within 20 records
              distances  1:39%  2:32%  4:7%  3:5%  5:3%
8802 slot 1 :  94.5% below own index but only 0.7% within 20  (not an edge)
```

A decaying distribution peaking at distance 1 is what a dataflow reference looks like;
slot 1's mass at distance ≥400 is what an unrelated magnitude looks like. Across types:

| tag | slot 1 | slot 2 | slot 3 | slot 4+ |
|---|---:|---:|---:|---:|
| `8802` | 1% | **96%** | **77%** | 0% |
| `7702` | 1% | **98%** | **95%** | 0% |
| `8803` | 1% | **92%** | **96%** | 9% |
| `881E` | 1% | **95%** | 0% | 0% |
| `8818` | 1% | **97%** | 43% | 0% |
| `8804` | 0% | **71%** | 0% | 0% |
| `6604` | 0% | **92%** | 0% | 0% |
| `880E` | **90%** | **51%** | 5% | 0% |

(percentage of values pointing within 20 records back)

**Slot 2 is an edge in every type.** Slot 3 is an edge only for types `0x02` and `0x03`.
So **the record type encodes the node's arity**: `0x02`/`0x03` are two-input nodes,
`0x04`/`0x1E`/`0x18` are one-input nodes. That matches Substance's model, where blends
take two inputs and filters one.

Why the earlier attempt failed: it pooled every slot of every type, so the local peak was
swamped. Restricting to one slot of one type made it obvious. The same confound has now
appeared three times in this investigation.

### Reconstruction, checked against known specimens

Putting nodes, edges and the type-specific parameter pointer together:

```
GrayscaleConvert (2 records)
   #0  8821  image input (colour)
   #1  8828  gray op  <- #0

radial_blur_grayscale (2 records)
   #0  8820  image input (grayscale)
   #1  8828  gray op  <- #0

Substance_graphC (5 records)
   #0  880D  uniform colour       params @+18, ref 0A42
   #1  8805  image load (colour)  <- #0
   #2  880D  uniform colour       params @+18, ref 0A42
   #3  8805  image load (colour)  <- #2
   #4  8803  two-input node       <- #1, #3   params @+14, ref 0A42
```

These are correct. `GrayscaleConvert` is a colour input feeding a grayscale operation —
precisely what its name says. `graphC` is two colour constants, each through a loader,
blended by a two-input node. The record types used were identified independently and long
before this reconstruction, so the graphs are a genuine check rather than a restatement.

### What a `.sbsar` now yields

| element | how |
|---|---|
| nodes | records, located at directory entry + 52 |
| node type / arity | record tag low byte |
| edges | slot 2, plus slot 3 for types `0x02`/`0x03` |
| parameters | skew-52 pointer at a type-specific slot, into embedded bytecode |
| parameter expressions | the instruction set, 41 of 45 operations identified |
| inputs, outputs, defaults | the interface block, 493/493 validated |
| embedded bitmaps | the resource table |

The remaining gap is semantic: which filter each of the 41 record types denotes. The
structure is recovered.

## Record types are filters — the `.sbs` names them

The `.sbs` source describes the **pixel** graph as well as the function graphs, naming
every node's filter: `blend` (2,708 uses), `levels` (1,161), `uniform` (956),
`transformation` (867), `gradient` (724), `passthrough` (600), `warp` (373), `blur` (278),
`pixelprocessor` (206), `grayscaleconversion` (128), `bitmap` (125), `normal` (124),
`shuffle` (60) and a dozen more. That is the vocabulary the record types must encode.

### Grayscale and colour are adjacent type codes

Counting filters and record types on specimens with **no sub-graph instances** — where
inlining cannot distort the counts — gives exact agreements:

| specimen | filters | record types | reading |
|---|---|---|---|
| `Metal_Vent_006` | bitmap 6 | `21`:6 | bitmap = `0x21` |
| `celtic_orna_mossy_001` | bitmap 6 | `20`:3 `21`:3 | **3 gray + 3 colour = 6** |
| `st_wood_fine_20` | bitmap 7, transformation 7 | `20`:5 `21`:2 / `04`:5 `05`:2 | **both exact** |
| `ie_processing` | pixelprocessor 2 | `28`:2 | pixelprocessor = `0x28` |
| `SubstanceDesigner__color` | shuffle 5, pixelprocessor 3 | `07`:5, `29`:3 | **both exact** |

The even/odd split is systematic: **even type = grayscale, odd = colour**, so the type
byte is `2 x filter_id + is_colour`. This also explains every gray/colour record pair
noted earlier in this document without an explanation — `8820`/`8821`, `8804`/`8805`,
`8828`/`8829`, `880C`/`880D` are one filter each, in two channel modes.

### Identified filters

| type | filter | evidence |
|---|---|---|
| `0x20` / `0x21` | **source node** (bitmap *or* graph input) | 9/9 exact on instance-free pairs; see "The source-node type is wider than `bitmap`" |
| `0x04` / `0x05` | **transformation** | exact 5+2 = 7 alongside bitmap in the same file |
| `0x28` / `0x29` | **pixelprocessor** | exact on 2 specimens (2 and 3) |
| `0x07` | **shuffle** | exact, 5 = 5 |
| `0x0C` / `0x0D` | **uniform** | direct read: four literal RGBA floats, static or driven |
| `0x02` / `0x03` | **blend** — CONFIRMED, see the `comptype` section | exact counts under both channel modes, plus independent two-input arity |

This supersedes the earlier working labels, which were structurally right but
semantically vague: "image input" is `bitmap`, "image load" is `transformation`, and the
"gray/colour op pair" is `pixelprocessor` — which makes sense of why `0x28`/`0x29` carry
parameter bytecode, since a pixel processor *is* a per-pixel expression evaluator.

### Correlation failed again, for the third time

Correlating filter counts against type counts across all 108 paired specimens produces
nothing usable: `blend` correlates 0.70 with the largest type pair, but so do `levels`
(0.63) and `gradient` (0.54) — everything correlates with everything, because file size
dominates. Worse, `bitmap` scores **0.02** against `20/21`, the mapping proven exact on
three separate specimens.

This is the same failure mode as the function-vocabulary correlation and the
record-index test: pooling across specimens of wildly different sizes, or across slots and
types, destroys the signal. **Exact agreement on a small, uncontaminated specimen has
outperformed corpus-wide correlation at every single stage of this work.**

### `comptype` fixes the channel parity, and confirms two more filters

The `.sbs` gives each pixel node a `<comptype>` alongside its filter name. Its values are
almost entirely 1 (5,581) and 2 (5,544) — the node's **output channel mode**, not a filter
id. Pairing `(filter, comptype)` per node and matching against record types resolves the
parity:

**`comptype 1` = colour, mapping to an ODD record type. `comptype 2` = grayscale, mapping
to an EVEN one.**

`st_wood_fine_20` settles it, because two different filters split simultaneously and both
splits are exact:

```
bitmap/1 = 2   ->  type 21 = 2        transformation/1 = 2  ->  type 05 = 2
bitmap/2 = 5   ->  type 20 = 5        transformation/2 = 5  ->  type 04 = 5
```

Four counts, four exact agreements, in one file, across two filters. `celtic_orna_mossy_001`
repeats it independently: `bitmap/1` = 3 → `21` = 3 and `bitmap/2` = 3 → `20` = 3.

Exact-count voting over the 20 instance-free specimens then gives a consistent table:

| filter | comptype 1 (colour) | comptype 2 (gray) | votes |
|---|---|---|---|
| **blend** | `0x03` | `0x02` | 4 / 2 |
| **bitmap** | `0x21` | `0x20` | 4 / 2 |
| **transformation** | `0x05` | `0x04` | 3 / 1 |
| **pixelprocessor** | `0x29` | `0x28` | 2 / 3 |
| **uniform** | `0x0D` | `0x0C` | 2 / — |
| **shuffle** | `0x07` | `0x06` | exact 5=5 |

**`blend` = `0x02`/`0x03` is now confirmed** rather than inferred — it was previously
argued only from "commonest filter maps to commonest type, both two-input". The arity
evidence and the count evidence now agree, which is a genuine cross-check: the two-input
slot structure was found from dataflow distances, entirely independently of the `.sbs`.

**`uniform` = `0x0C`/`0x0D` is likewise confirmed**, matching the direct byte-level read of
a `440D` record as four literal RGBA floats.

### The scheme, complete

```
record tag = NN | type
   type = 2 x filter_id + is_colour        even = grayscale, odd = colour
   NN   = whether the node's parameters are literal or driven
class word = bitfield, bit 3 always set, remaining bits track type
slot 2 (and slot 3 for blend) = index of an earlier record  -> graph edges
type-specific slot = skew-52 pointer to the node's parameter bytecode
```

Six filters are now named, covering the four commonest record types. The rest of the
vocabulary — `levels` (1,161 uses), `gradient` (724), `warp` (373), `blur` (278),
`normal` (124) — needs instance-free specimens that isolate them, and only 20 such
specimens exist in the corpus. That, not method, is the current limit.

### Two more filters, after doubling the usable corpus

The binding constraint was instance-free specimens — only 20 of them. It turned out
`pairs5`, harvested several iterations earlier, had **never been extracted**: 37 archives
sitting unopened. Extracting them added 25 specimens and took the instance-free count from
20 to **40**, which brought `levels`, `fxmaps`, `blur`, `gradient` and `valueprocessor`
into range for the first time.

**`levels` = `0x1E` / `0x1F`** — 9 of 10 specimens agree exactly:

```
BnW_Spots_Animated    levels 1  ->  1E=1
Cells_Animated        levels 1  ->  1E=1
Clouds_Animated       levels 1  ->  1E=1
Crystal_Animated      levels 2  ->  1E=2
Electric_Liquid       levels 6  ->  1E=4 + 1F=2 = 6     <- splits across both channels
```

`Electric_Liquid` is the strongest single case: six `levels` nodes distributing as four
grayscale and two colour, matching the even/odd parity rule exactly.

**`fxmaps` = `0x08` / `0x09`** — 8 of 9 exact:

```
BnW_Spots_Animated    fxmaps 3  ->  08=3
Clouds_Animated       fxmaps 3  ->  08=3
Perlin_Noise_Animated fxmaps 1  ->  08=1
```

### Filters identified so far

| type (gray/colour) | filter | corpus records | evidence |
|---|---|---:|---|
| `0x02` / `0x03` | **blend** | 154,400 | exact counts + two-input arity, independently derived |
| `0x04` / `0x05` | **transformation** | 108,959 | exact 5+2 split alongside bitmap |
| `0x1E` / `0x1F` | **levels** | 42,865 | 9/10 exact, incl. a 4+2 channel split |
| `0x28` / `0x29` | **pixelprocessor** | 24,994 | exact on 2 specimens |
| `0x08` / `0x09` | **fxmaps** | 19,983 | 8/9 exact |
| `0x0C` / `0x0D` | **uniform** | 12,759 | exact counts + direct byte read of RGBA floats |
| `0x06` / `0x07` | **shuffle** | 4,533 | exact 5=5 |
| `0x20` / `0x21` | **bitmap** | 942 | exact on 3 specimens incl. a 3+3 split |

Eight filters, covering the five largest record types and roughly 90% of all records.

### Two approaches that did not work

- **Expanding sub-graph instances.** Every instance reference is `pkg:///`
  package-relative, and 41.7% resolve to a graph in the same `.sbs`. But **no file has all
  its instances resolving** — the rest live in dependency packages absent from the corpus —
  so recursive expansion cannot make a contaminated specimen usable.
- **Ranking record types against filter usage.** `blend` is rank 1 in both, and then the
  orders diverge completely: `bitmap` is the 15th commonest record type but the 15th
  commonest filter by coincidence, while `transformation` is 2nd by record and 4th by
  filter. Library inlining inflates the record counts unevenly, so rank alignment carries
  no information.

### Five more filters

With 40 instance-free specimens available, exact-count matching reaches most of the
remaining large type pairs.

**`Electric_Liquid` is the decisive specimen.** It carries four unnamed type pairs and
several filters at distinctive counts:

```
filters : gradient 6,  blur 11,  warp 1,  hsl 1,  levels 6
unnamed : 00:6        14:11     0E:1    1C:1
```

`gradient` = 6 → `00` = 6 and `blur` = 11 → `14` = 11, both exact. Eleven is a
distinctive count; matching it by chance among four candidate pairs is unlikely.

| filter | type (gray/colour) | records | evidence |
|---|---|---:|---|
| **gradient** | `0x00` / `0x01` | 9,367 | 3/3 exact (1, 1, 6) |
| **warp** | `0x0E` / `0x0F` | 15,182 | 3/3 exact — `Crystal_Animated` and `Crystal_2_Animated` each 1=1, plus `Electric_Liquid` |
| **blur** | `0x14` / `0x15` | 8,313 | 11 = 11 in a file with four unnamed candidates |
| **normal** | `0x24` / `0x25` | — | 2/2 exact |
| **distance** | `0x2A` / `0x2B` | 1,185 | 2 = 2 in `SDF` |

`warp` is pinned independently of `Electric_Liquid`: two `Crystal` specimens each contain
exactly one `warp` node and exactly one `0x0E` record and nothing else unnamed. That in
turn forces `hsl` onto `0x1C` in `Electric_Liquid` by elimination — but `time_var_test`
has an `hsl` node and no `0x1C` record, so **`hsl` is left unassigned** rather than
inferred from a single elimination.

### Filters identified

| type | filter | records |
|---|---|---:|
| `0x02` / `0x03` | blend | 154,400 |
| `0x04` / `0x05` | transformation | 108,959 |
| `0x1E` / `0x1F` | levels | 42,865 |
| `0x28` / `0x29` | pixelprocessor | 24,994 |
| `0x08` / `0x09` | fxmaps | 19,983 |
| `0x0E` / `0x0F` | **warp** | 15,182 |
| `0x0C` / `0x0D` | uniform | 12,759 |
| `0x00` / `0x01` | **gradient** | 9,367 |
| `0x14` / `0x15` | **blur** | 8,313 |
| `0x06` / `0x07` | shuffle | 4,533 |
| `0x2A` / `0x2B` | **distance** | 1,185 |
| `0x20` / `0x21` | bitmap | 942 |
| `0x24` / `0x25` | **normal** | — |

**Thirteen filters**, covering every record type above 4,000 instances. The largest
remaining unnamed pair is `0x18` / `0x19` at 28,395 records — no instance-free specimen in
the corpus isolates it, so it stays open.

### Presence lift resolves the largest remaining type

Exact counts need a specimen that isolates a filter. For filters that never appear alone,
**presence lift** works instead: compare P(type present | filter present) against
P(type present | filter absent) across all 183 paired specimens. Unlike raw co-occurrence,
this is not dominated by ubiquitous filters.

| type pair | filter | P(type\|filter) | P(type\|no filter) | lift |
|---|---|---|---|---|
| `0x2A`/`0x2B` | **distance** | **20/20 = 1.00** | 19/163 = 0.12 | 8.6 |
| `0x18`/`0x19` | **directionalwarp** | **42/43 = 0.98** | 20/140 = 0.14 | 6.8 |
| `0x26`/`0x27` | **passthrough** | 11/32 = 0.34 | 5/151 = 0.03 | 10.4 |
| `0x2C`/`0x2D` | curve | 5/15 = 0.33 | 3/168 = 0.02 | 18.7 |

`directionalwarp` at 42/43 resolves `0x18`/`0x19`, the largest previously unnamed type at
28,395 records. It carries independent structural support: `8818`'s slot 3 behaves as an
edge only 43% of the time, where blend's is 77–96% and a pure one-input filter's is 0%.
A partial second input is exactly what `directionalwarp` has — an image plus an optional
intensity map.

`distance` at 20/20 confirms the exact-count match from `SDF` by a wholly different route.

`passthrough` at `0x26`/`0x27` is worth noting: the corpus-wide correlation that failed
for every other filter gave `passthrough` → `0x26`/`0x27` at r = 0.87, its single correct
answer. Two independent weak methods agreeing is not proof, but it is better than either
alone.

### Filter table

| type | filter | records | basis |
|---|---|---:|---|
| `0x02`/`0x03` | blend | 154,400 | exact + arity |
| `0x04`/`0x05` | transformation | 108,959 | exact |
| `0x1E`/`0x1F` | levels | 42,865 | exact, 9/10 |
| `0x18`/`0x19` | **directionalwarp** | 28,395 | lift 0.98 + partial second input |
| `0x28`/`0x29` | pixelprocessor | 24,994 | exact |
| `0x08`/`0x09` | fxmaps | 19,983 | exact, 8/9 |
| `0x0E`/`0x0F` | warp | 15,182 | exact, 3/3 |
| `0x0C`/`0x0D` | uniform | 12,759 | exact + byte-level read |
| `0x00`/`0x01` | gradient | 9,367 | exact, 3/3 |
| `0x14`/`0x15` | blur | 8,313 | exact, 11 = 11 |
| `0x06`/`0x07` | shuffle | 4,533 | exact |
| `0x2A`/`0x2B` | distance | 1,185 | exact + lift 1.00 |
| `0x26`/`0x27` | passthrough | 1,159 | lift 10.4 + correlation |
| `0x20`/`0x21` | bitmap | 942 | exact, 3 specimens |
| `0x24`/`0x25` | normal | — | exact, 2/2 |

**Fifteen filters.** Every record type above 1,000 instances is now named except
`0x16`/`0x17` (6,785), for which no discriminating evidence exists — its lift table is
topped by `blend`, `uniform` and `levels`, all of which are simply common.

### Arity independently validates every filter assignment

The first arity measurement was wrong, and the error was instructive: it counted **the
bytecode pointer slot as a candidate edge**. Since a pointer never holds a small
back-reference, any type whose pointer sits where its edge would be appeared to have zero
inputs. `0x14` (blur) showed 0% at slot 2 — which is exactly its pointer slot — and that
looked like a contradiction of the `blur` identification.

Excluding each type's known pointer slot resolves it and turns the measurement into a
proper check. Input arity is derived purely from dataflow distances in the binary; the
filter names came from `.sbs` node counts. The two are completely independent, and they
agree on **every** assignment:

| type | filter | inputs measured | expected of that filter |
|---|---|---|---|
| `0x0C`/`0x0D` | uniform | **0** | a constant generator |
| `0x08` | fxmaps | **0** | a pattern generator |
| `0x26` | passthrough | 1 (99%) | one in, one out |
| `0x14` | blur | 1 (82%) | one image |
| `0x1E` | levels | 1 (95%) | one image |
| `0x16` | *unidentified* | 1 (98%) | — |
| `0x04` | transformation | 1 (71%) | one image |
| `0x06` | shuffle | 1 (87%) | one image |
| `0x28` | pixelprocessor | 1 (54%) | one image |
| `0x00` | gradient | 1 (91%) | one image to map |
| `0x02` | blend | **2** (96%, 77%) | foreground + background |
| `0x0E` | warp | **2** (90%, 50%) | image + intensity |
| `0x2A` | distance | **2** (99%, 76%) | source + mask |
| `0x18` | directionalwarp | 1 + partial (43%) | image + optional intensity |

Generators show zero inputs, one-input filters show one, blends and warps show two, and
`directionalwarp`'s optional second input shows up as a partial rate — the same 43% that
first suggested its identity.

This is the strongest validation in the record work so far. Fifteen names assigned from
counting `.sbs` nodes are confirmed by a structural property measured in the binary that
was never used to derive them.

### `0x16` remains open
*(Resolved as unnameable-from-this-corpus: it occurs only inside inlined library graphs.
See "Why `0x16` cannot be named from this corpus".)*

`0x16`/`0x17` (6,785 records) is a **one-input filter** — slot 2 is an edge 98% of the
time and slot 3 never is. Its presence lift is topped only by filters already assigned
elsewhere (`warp` 0.89, `directionalwarp` 0.98, `normal` 0.80), which means it co-occurs
with them rather than being them. The unassigned one-input candidates remaining in the
vocabulary are `grayscaleconversion`, `hsl` and `sharpen`; nothing in the corpus separates
them.

### Channel type is preserved through the graph

Measuring the channel type of each node's first input against its own confirms the parity
model directly in the binary:

| node type | filter | input is colour |
|---|---|---:|
| `0x02` blend (gray) | | 0.0% |
| `0x04` transformation (gray) | | 0.0% |
| `0x1E` levels (gray) | | 0.1% |
| `0x14` blur (gray) | | 0.0% |
| `0x03` blend (colour) | | **99.9%** |
| `0x05` transformation (colour) | | **100.0%** |
| `0x1F` levels (colour) | | **99.8%** |
| `0x29` pixelprocessor (colour) | | **95.7%** |

Grayscale nodes take grayscale inputs and colour nodes take colour ones, essentially
without exception. This is the even/odd parity rule confirmed a second way — from
connectivity rather than from `.sbs` counts.

**One informative exception.** `0x06` — `shuffle` in grayscale — takes a **colour** input
**100%** of the time. That is exactly right: a channel shuffle producing grayscale must
read a colour image to extract a channel from. The rule's only violation is a filter
whose entire purpose is to violate it.

### `0x16` narrowed by elimination

`0x16`/`0x17` (6,785 records) is a one-input, grayscale-in / grayscale-out filter, and its
colour form `0x17` barely occurs. Candidates were eliminated as follows:

| filter | eliminated because |
|---|---|
| `grayscaleconversion` | `0x16` takes a **grayscale** input 99.8% of the time; this filter must take colour |
| `emboss` | two inputs; `0x16` has one (98% slot 2, 0% slot 3) |
| `hsl` | `time_var_test` and `Electric_Liquid` each author one, with **zero** `0x16` records |
| `sharpen` | `Clouds_3_Animated` authors one, with **zero** `0x16` records |
| `curve`, `valueprocessor` | `fake_anim_curve` authors 1 and 3, with **zero** `0x16` records |

What remains is `motionblur` / `dirmotionblur`, which fit structurally — one input,
grayscale, and a filter id adjacent to `blur` (`0x14` is filter id `0x0A`, `0x16` is
`0x0B`, and motion blur is a blur variant).

**But the counts argue against it.** `blur` has 278 authored uses and 8,313 records, an
inlining factor of about 30. `dirmotionblur` and `motionblur` together have 48 authored
uses, which at the same factor predicts ~1,400 records, not 6,785.

So `0x16` is most likely a node that is **common in library graphs but rarely authored
directly** — which the corpus, being made of authored `.sbs` files, cannot name. Recorded
as narrowed but unresolved rather than guessed.

### Class-word bit 0 is the driven-parameter flag — and `NN` is not

Bit 0 of the class word predicts whether a record carries a bytecode pointer almost
perfectly:

```
bit 0 clear : pointer present  10.4%   median record length  28
bit 0 set   : pointer present  97.6%   median record length 120
```

**This corrects an earlier conclusion.** Two iterations ago I attributed the static /
dynamic distinction to `NN`, from the observation that `440D` records hold literal RGBA
floats while `880D` records hold pointers. The observation was right; the attribution was
wrong. Stratifying by `NN` shows bit 0 controlling the outcome *within every `NN` value*:

| `NN` | bit 0 clear | bit 0 set |
|---|---:|---:|
| 4 | 7.4% | **97.2%** |
| 5 | 18.3% | **95.8%** |
| 6 | 18.9% | **97.3%** |
| 7 | 18.7% | **97.2%** |
| 8 | 8.0% | **97.9%** |
| 10 | 3.0% | **94.3%** |

`NN` appeared to matter only because it correlates with bit 0: at `NN` = 8 bit 0 is set
97% of the time, at `NN` = 4 only 24%, at `NN` = 11 only 2.7%. Holding `NN` fixed, the
effect is entirely bit 0's. **`NN`'s meaning is once again unknown** — it is not a size
class, not a label, and not the static/dynamic flag.

The other class bits are far weaker predictors (77–97%) and none approaches bit 0's
separation.

### The confound, a fourth time

This is the same error that has recurred throughout this work: a variable that correlates
with an outcome mistaken for the variable that causes it. It defeated the function-name
correlation, the record-index test, the filter-vs-type ranking, and now the `NN`
attribution. The fix has been the same every time — **stratify**: hold the suspected
confound fixed and see whether the effect survives. Here it did not.

Worth stating as a rule for the rest of this work: no claim of the form "field X controls
Y" should be recorded until X has been tested with every other plausible field held fixed.

### Stratifying the pointer-slot claim — 21 of 23 types survive, and the exception is informative

Applying the rule from the previous section to a claim that had never been tested that
way: is the bytecode pointer's slot really determined by record type, or does the class
word move it? Holding type fixed and varying the class word, across 23 types:

**21 are CONSTANT.** Type `0x02` puts the pointer at slot 4 under class words `0019`,
`0039`, `0009` and `0099` alike; type `0x04` at slot 3 under five different class words;
type `0x1E` at slot 3; type `0x0D` at slot 1. The mapping holds.

**Two vary — `0x28` and `0x29`, pixelprocessor:**

```
class 0089 -> slot 2      class 00B9 -> slot 3      class 0099 -> slot 4
```

### The exception explains itself

Pixelprocessor is the one filter with a *variable* number of image inputs. If the pointer
follows the input list, its slot must move with the arity. Testing directly:

| pointer slot | n | input edges found before it |
|---:|---:|---|
| 2 | 1,018 | **0 edges, 100%** |
| 3 | 1,998 | **1 edge, 95%** |
| 4 | 1,643 | **2 edges, 89%** |
| 5 | 268 | 2–3 edges |

**Pointer slot = 2 + number of inputs, in 89.6% of 5,028 records.**

This also explains an anomaly recorded two iterations ago without comment: the arity
measurement gave pixelprocessor a *mixed* result — 54% at slot 2, 39% at slot 3 — where
every other filter gave a clean answer. That was not noise. It was a filter whose arity
genuinely varies from node to node, measured as though it were fixed.

So the better statement of the record layout is:

```
+0   tag | class
     ... input edge slots, one per input
     bytecode pointer, immediately after the inputs
     literal parameter values
```

The pointer slot appears type-determined only because arity is fixed for almost every
filter. It is really **arity-determined**, and the two coincide except where arity varies.

Note this is not yet a universal rule: `gradient` (`0x00`) has one input at slot 1 but its
pointer at slot 4, which the arity model does not predict. The edge slots do not begin at
the same offset for every type, so "pointer = 2 + arity" is verified for pixelprocessor
and consistent with blend, transformation and levels, but is not established generally.

### The record field map

Classifying every slot of every record type (grayscale forms, `NN` = 8, driven
parameters) as edge / pointer / float / small-int:

| type | filter | slot 1 | slot 2 | slot 3 | slot 4 | slot 5 |
|---|---|---|---|---|---|---|
| `0x02` | blend | int | **edge** | **edge** | **PTR** | — |
| `0x04` | transformation | int | **edge** | **PTR** | — | — |
| `0x1E` | levels | int | **edge** | **PTR** | float | float |
| `0x18` | directionalwarp | int | **edge** | edge (43%) | **PTR** | — |
| `0x16` | *unidentified* | int | **edge** | **PTR** | — | float |
| `0x28` | pixelprocessor | int | **edge** | **PTR** (variable) | | |
| `0x0E` | warp | **edge** | **edge** | **PTR** | — | float |
| `0x14` | blur | **edge** | **PTR** | — | float | — |
| `0x00` | gradient | **edge** | int | — | **PTR** | int |
| `0x06` | shuffle | **edge** | **PTR** | int | int | int |
| `0x26` | passthrough | **edge** | int | **PTR** | — | — |
| `0x0C` | uniform | **PTR** | — | — | — | — |

Two layout families, and the split explains the anomaly noted last iteration:

- **Family A** — `blend`, `transformation`, `levels`, `directionalwarp`, `0x16`,
  `pixelprocessor` — carries a small integer in slot 1, with edges from slot 2.
- **Family B** — `warp`, `blur`, `gradient`, `shuffle`, `passthrough`, `uniform` — has no
  leading integer; edges begin at slot 1.

`gradient` looked like a counterexample to "pointer = 2 + arity" because it is Family B
with an extra field between its edge and its pointer. The rule is not universal, but the
deviation is structural rather than random.

### The edge slot is per-filter, measured

"Graph edges live in slot 2, plus slot 3 for two-input types" was right for the common
case and wrong in general. Pooling hid it: corpus-wide, slot 2's correlation with the
record's own index is **-0.011**, which reads as "not an edge" — because different
filters put their edges in different slots and the average is noise.

Stratified by filter, an edge is unmistakable: a backward reference to an earlier record
gives correlation **+1.00** with the record index and **100%** of values below it.

| filter | edge slots | reading |
|---|---|---|
| `blend` | 2 and 3 | two inputs — matches its independently derived arity |
| `blur` | **1** | one input, in slot 1 |
| `gradient` | **1** | one input, in slot 1 |
| `levels` | 2 | one input |
| `transformation` | 2 | one input |
| `warp` | 2 (and slot 1, 100% backward, r +0.36) | one certain, one partial |
| `normal` | 2 | one input (r +0.97) |
| `distance` | 2 (slot 3 at 73%) | one certain, one conditional |
| `bitmap` | **none** | source node — 0% backward on every slot |
| `uniform` | **none** | source node — 0% backward on every slot |
| `pixelprocessor`, `fxmaps`, `shuffle` | unresolved | 27-97% backward, no slot at +1.00 |

The two source filters falling out as sources is the check on this: nothing in the test
knows which filters take inputs, yet `bitmap` and `uniform` — the two that generate
rather than transform — are exactly the two with no edge slot.

### Finding edge slots with the inheritance rule

Bit 3 gives a second, independent way to locate edges, and it needs no reference graph.
A record with bit 3 **clear** must inherit its resolution from its input, so a slot that
holds an edge will point at a record of the same resolution nearly always, while a slot
holding anything else will not.

The probe reproduces every edge found by the correlation method — `blend` 99% at slots 2
and 3, `blur` and `gradient` 100% at slot 1, `levels` 99% at slot 2, `normal` 100% at
slot 2 — and returns nothing above 20% for `bitmap` and `uniform`, the two source
filters, which is the control.

It also settles filters the correlation method left open:

| filter | edge slots | agreement | n |
|---|---|---|---|
| `shuffle` | **1, 2, 3** | 98%, 98%, 86% | 2,114 / 3,644 / 4,725 |
| `warp` | **1, 2, 3** | 89%, 99%, 99% | 14,299 / 14,299 / 1,695 |
| `distance` | **2, 3** | 100%, 100% | 1,810 / 1,332 |
| `fxmaps` | 6 (probable), 3 and 4 weaker | 91%, 74%, 68% | 3,454 / 4,523 / 5,024 |
| `pixelprocessor` | 4 (probable), 2 weaker | 83%, 76% | 1,627 / 41,484 |

`shuffle` taking three inputs matches its role as a channel mixer, and `distance`'s
second input at slot 3 — previously seen at only 73% by correlation — resolves to 100%
here. `transformation` reads low on every slot, which is expected: it is the filter that
changes resolution by design, so its bit-3-clear records are both rare (n=2,180 against
211,494 total) and unrepresentative.

**Method note.** This is the third question in a row answered from unpaired binaries
alone — resource descriptors, the resolution field, and now edge slots — after months of
treating `.sbs` pairs as the limiting resource. Establishing one field's semantics turns
it into an instrument for probing the next.

### This corrupts the slot-1 flags-word statistics

The slot-1 bitfield was characterised by pooling slot 1 across all records. But slot 1
holds an **edge** for `blur` and `gradient`, and a partial one for `warp`. Those records
contributed record indices to a histogram of flag bits, which is meaningless. The bit
frequencies recorded for slot 1 (bit 0 60.9%, bit 1 65.4%, bit 2 58.5%, ...) are
therefore contaminated by an unknown amount, and the `outputsize` lead for bit 2 needs
re-measuring with `blur`, `gradient` and `warp` excluded.

### Slot 1 of Family A is a flags word

The leading integer is **not** a node index: correlation with the record's own directory
index is **r = 0.012** over 174,230 records, and there are only **32–72 distinct values
per file** against thousands of records — a ratio of 0.04.

It is a bitfield, with 149 distinct values corpus-wide and a clear active set:

```
bit 0  60.9%     bit 4  48.7%     bit  8  48.3%
bit 1  65.4%     bit 5  29.3%     bit 25   1.7%
bit 2  58.5%     bit 6  14.1%     bits 7, 9-12  < 1%
bit 3  33.4%
```

Common values are `0x3F` (bits 0–5, 12.5%), `0x17`, `0x0A`, `0x140`, `0x102`, `0x127`.
Roughly eight active bits shared across all nodes of a file — consistent with per-node
option flags, though which options is not established.

That makes **three** distinct bitfields in the record header: the class word (bit 3 always
set, bit 0 = driven parameters), this slot-1 flags word, and `NN` itself, whose meaning
remains open after being wrongly attributed twice.

### Trailer word 1: tested, unresolved

The trailer's second word takes seven values across 382 specimens:

```
0 x46    1 x24    2 x2    3 x4    4 x117    5 x5    8 x184
```

Read as a bitfield, bits 2 and 3 dominate — values 4 and 8 account for 301 of 382 files —
and they never co-occur: no file has value 12. The remaining values are rare.

Tested against every file-level property available:

* **version** — every value spreads across v2 to v9 in roughly the corpus proportions
* **layout A or B** — 83-100% layout A for every value, matching the corpus rate
* **presence of embedded resources** — 37% for value 8 against 15-20% elsewhere, the only
  visible tilt and far from a rule
* **graph count** — 85-100% single-graph for every value
* **counts** — median outputs 4-6 and median inputs 6-25 across values, no ordering

The one numeric difference is size: files with value 4 have a median of 98 KB and 552
records, those with value 8 a median of 802 KB and 1,105 records. That is an eightfold
difference in size but only twofold in records, and neither has a threshold that separates
the two groups — the distributions overlap heavily.

No identification. It is recorded here as tested rather than untouched, since a seven-valued
field with two dominant mutually-exclusive states is the kind of thing that invites a guess.

### Class bits 4 and 5: associated with program length, not identified

Both bits track the length of the record's parameter program. Comparing median instruction
counts, stratified by filter:

```
bit 4 set vs clear (median instructions)
   gradient        19  vs  1      levels    3  vs  3
   transformation  10  vs  1      shuffle   1  vs  1
   blur            19  vs  3      uniform   1  vs  1
   blend            4  vs  1      warp      1  vs  1

bit 5 set vs clear
   directionalwarp 26  vs  3      blend    13  vs  4
```

The ratios look decisive — 19 instructions against 1 for `gradient` — but that is an artifact
of comparing medians on a skewed distribution. Recast as a per-record test, "is the program
more than one instruction", the separation is much weaker:

| filter | P(>1 \| bit 4 set) | P(>1 \| clear) |
|---|---:|---:|
| `transformation` | 79% | 45% |
| `gradient` | 75% | 40% |
| `blend` | 63% | 45% |
| `levels` | 56% | 56% |
| `blur` | 80% | 77% |
| `fxmaps` | 38% | 69% |

Pooled, 65.9% against 44.4% with 65.4% agreement — a real tendency, not a rule, and absent or
inverted on three of the filters measured.

So neither bit is identified. What can be said is that bit 4 is set on about 95% of records
and its rare clear case has a trivial program, while bit 5 is rare and marks unusually long
programs.

**A methodological note.** A ratio of medians is a poor test for a binary flag: it is
sensitive to where the distribution's mass sits and can look overwhelming when the underlying
per-record separation is modest. The 19-to-1 median ratio for `gradient` corresponds to a
75%-versus-40% split, which would not have been recorded as an identification on its own.

### Class bit 0 confirmed as "driven parameter" — on the filters where it is informative

Bit 0 was recorded early as marking records with driven parameters, on evidence that it
predicted whether a record carried a bytecode pointer at all. Nearly every record turned out
to carry one, so that basis dissolved. Measured properly — does the record's own bytecode
contain an `inputref`, i.e. does its parameter program read a graph input — and stratified
by filter:

| filter | n | P(reads an input \| bit set) | P(reads an input \| bit clear) |
|---|---:|---:|---:|
| `blend` | 45,913 | 79% | **1%** |
| `transformation` | 32,650 | 75% | **0%** |
| `gradient` | 2,125 | 89% | **0%** |
| `directionalwarp` | 9,264 | 82% | — |
| `warp` | 4,251 | 91% | — |
| `levels` | 13,699 | 96% | 84% |
| `blur` | 1,738 | 88% | 100% |
| `uniform` | 1,580 | 98% | 100% |
| `fxmaps` | 6,600 | 8% | 45% |
| `pixelprocessor` | 7,319 | 1% | 1% |

On `blend`, `transformation` and `gradient` the bit is close to decisive: set means the
parameter program reads a graph input, clear means it essentially never does. Together those
are 80,000 of the records measured.

It is **uninformative** where reading an input is near-universal anyway (`levels`, `blur`,
`uniform`, `shuffle`, `passthrough` all sit at 84-100% either way), and **inverted or null**
on the two function-graph filters, `fxmaps` and `pixelprocessor`, whose bytecode is a whole
per-pixel function rather than a parameter expression.

So the early reading was right in substance and wrong in its evidence. Bit 0 marks a driven
parameter, where "driven" means the value comes from a graph input rather than a constant —
and the bit only carries information on filters whose parameters are sometimes constant.

### Bit 11 is not a semantic flag — it is part of the variant field

Bit 11 looked like a spatial-filter marker: 89% on `distance`, 79% `directionalwarp`, 73%
`normal`, 71% `sharpen`, 66% `warp`, and 0% on `blend`, `levels`, `transformation` and
`pixelprocessor`. It also implies bit 9 at 94.1%, which fitted the reading that bit 9 marks
spatial filters and bit 11 refines it.

Both readings are wrong. Comparing records of the *same* filter that differ in bit 11:

```
warp             set -> variant 10 (94%)    clear -> variant  8 (88%)
blur             set -> variant  6 (95%)    clear -> variant  4 (73%)
directionalwarp  set -> variant  2 (100%)   clear -> variant  0 (99%)
normal           set -> variant  2 (100%)   clear -> variant  0 (96%)
sharpen          set -> variant  6 (80%)    clear -> variant  4 (90%)
```

In every case the variant differs by exactly 2, and bits 10-13 hold the variant as a
4-bit field — so **bit 11 is that field's bit 1**. Setting it does not mark a property of
the filter; it selects a different record layout, which is why the accompanying record size
also changes (`warp` 20 to 24 bytes, `blur` 16 to 20, `directionalwarp` 28 to 32).

The apparent spatial-filter association was doubly indirect: bit 11 is non-zero only on
filters that *use* the variant field at all, and those happen to be the spatial ones. The
implication of bit 9 has the same cause — both are properties of which filters use variants,
not of the bits.

This also revises the note that bits 10-13 are "a layout selector, used by six filters". That
stands, but bit 11 should not be listed separately in the class-word bit table as though it
carried its own meaning. Bits 10, 11, 12 and 13 are one field.

### The class-word bit table, stratified — only bit 3 is universal

The class word was characterised early by its pooled bit frequencies: bit 3 at 100%, bit 4
at 95.2%, bit 0 at 85.6%, bit 8 at 46.3%, and so on. Those numbers are weighted averages
over filters whose rates differ across almost the whole scale, and only one of them
describes a property of the field rather than of the corpus mix.

Set-rate per filter, over 651,567 records:

```
filter                 n     b0   b3   b4   b5   b7   b8   b9  b10  b11  b12  b13
POOLED           651,567    82% 100%  96%   3%  13%  46%  43%   1%  10%   2%   3%
blend            227,121    86% 100%  96%   2%   1%   0%   0%   0%   0%   0%   0%
transformation   170,102    65% 100%  98%   1%   8%  98%  97%   0%   0%   0%   0%
levels            63,453    88% 100%  97%   0%   1%   0%   0%   0%   0%   0%   0%
directionalwarp   42,220    98% 100%  94%   5%   1%  92%  92%   1%  79%   0%   0%
pixelprocessor    38,335    96% 100%  97%  29%  99%   0%   0%   0%   0%   0%   0%
fxmaps            28,787    87% 100%  99%   1% 100%  97%  96%   0%   0%   0%   0%
warp              19,876    99% 100%  98%   3%   1%  96%  95%   2%  66%   0%  92%
gradient          13,156    70% 100%  95%   0%   0%  85%   0%   0%   0%   0%   0%
uniform           13,025    62% 100%  60%   3%   1%  57%   4%   0%   0%   0%   0%
blur              10,858    66% 100%  95%   0%   0% 100% 100%  31%  56%  97%   2%
shuffle            5,309    93% 100%  80%  10%   1%  91%   0%   0%   0%   1%   0%
distance           1,670    96% 100%  99%   3%   1%  94%  94%   0%  89%   0%   0%
normal             1,000    98% 100%  81%   4%   2%  96%  96%   1%  73%   0%   0%
sharpen              931    97% 100%  95%   0%   0% 100% 100%   0%  71%  84%   1%
hsl                  555    90% 100%  75%   1%   1%  12%  41%  28%  39%  37%  42%
```

| bit | pooled | character |
|---|---:|---|
| **3** | **100.0%** | **universal — set on every record of every filter** |
| 0 | 81.7% | filter-specific, 41-99% |
| 4 | 95.6% | filter-specific, 50-99% |
| 5 | 3.4% | filter-specific, 0-29% (`pixelprocessor` 29%) |
| 7 | 12.8% | filter-specific, 0-100% — the function-graph bit |
| 8, 9 | 46%, 43% | filter-specific, 0-100% |
| 10-13 | 1-10% | filter-specific — the layout variant field |

Bit 3 is the only genuine invariant, which is what makes it usable as a record-detection
test. Bit 7's 0-100% range is the already-identified function-graph flag. Bits 11-13 are
high exactly on the filters that use the variant field, consistent with bits 10-13 selecting
record layout.

Bit 11 is *not* a separate flag — it is bit 1 of the variant field held in bits 10-13. See
"Bit 11 is not a semantic flag" above; its apparent spatial-filter association comes from
which filters use variants at all.

**The pooled table should not be quoted.** It is retained above only to show what it
obscures.

### Class-word bits 7, 8 and 9

Stratifying the class word by filter — the same move that unlocked the edge slots —
separates its bits into structural and graded.

**Bit 7 marks a record that carries a function graph.** It is set on 100% of `fxmaps`
records and 99% of `pixelprocessor` records, and at or below 1% on nine of the remaining
eleven filters. Those two are exactly the filters that embed bytecode: FX-Map drives its
tree from a function, Pixel Processor runs a function per pixel. The one graded case is
`transformation` at 9%, which is consistent with a driven parameter rather than a whole
embedded graph.

| filter | bit 7 |
|---|---:|
| `fxmaps` | 100% |
| `pixelprocessor` | 99% |
| `transformation` | 9% |
| everything else | 0-1% |

**Bit 9 implies bit 8**, with 999 exceptions in 282,923 records (99.6%). This one survives
stratification: `transformation` 100% against 8%, `directionalwarp` 100% against 0%, `warp`
100% against 1%, `blur` 100% against 6%, `distance` 100% against 1%. It is a genuine
field-level invariant rather than a filter artefact.

**Bit 8 does NOT imply anything about resolution override — retracted.** The pooled figure
looked decisive (P(override | bit 8 set) 76.9% against 4.1% when clear) and was recorded as a
one-way implication. Stratified by filter it vanishes:

```
transformation    99% vs 93%      warp       46% vs 43%
directionalwarp   91% vs 96%      gradient   49% vs 52%
blur              49% vs 59%      shuffle    23% vs 46%
```

Within every filter the bit makes no difference, and in three of them the association runs
backwards. The pooled effect came entirely from filters that never set bit 8 (`blend`,
`levels`, `pixelprocessor`) also never overriding their resolution — the filter drives both
variables independently.

**Bit 9 is near-constant per filter**, and the split it draws is interpretable:

| bit 9 set | bit 9 clear |
|---|---|
| `transformation` 98%, `blur` 99%, `fxmaps` 96%, `warp` 95%, `normal` 96%, `distance` 94% | `blend` 0%, `levels` 0%, `pixelprocessor` 0%, `gradient` 0%, `shuffle` 0%, `uniform` 3% |

The set group are the **spatial** filters — they read their input at displaced
coordinates. The clear group are pointwise: `blend`, `levels`, `shuffle` and
`pixelprocessor` operate on one pixel at a time, `gradient` and `uniform` generate. A
spatial/pointwise distinction is exactly what an evaluator needs, since a spatial filter
cannot be fused into a pointwise chain and needs its input materialised.

**Confidence.** Bit 7 is measured per record over 737,955 records and is solid. The bit-9
reading rests on 13 filters, so it is a hypothesis about filter taxonomy fitted to 13
points, not a per-record measurement — it predicts that any newly identified spatial
filter will carry bit 9, which is a real prediction but an untested one.

### A refuted hypothesis: NN's high byte is not the output format

For resource descriptors `NN` is `format << 8 | depth`, which makes it natural to ask
whether filter records encode their output format the same way. They do not. If the high
byte were a format code, its channel count would have to agree with the `is_colour` bit
in the record type. Agreement is **10.4%**: 233,948 records are grayscale while carrying
high byte `0x03`, which is RGBA8. The field is class-word bits 8-15, not a format.

### `NN` and the class word are the same field

The record header has been documented as carrying three bitfields: a class word at
offset +2, a slot-1 flags word, and `NN`. There are only two. `NN` was defined as the
high half of the first `u32`, and the class word as the `u16` at offset +2 — on a
little-endian layout those are **the same two bytes**.

```
record @0x694:  u32@+0 = 0x03984408
   u16@+0  = 0x4408   "type"
   u16@+2  = 0x0398   "class word"
   w32>>16 = 0x0398   "NN"        -> identical
```

Bit frequencies over 806,635 records confirm it against the figures recorded for the
class word: bit 3 100.0% vs 100.0%, bit 4 93.5% vs 95.2%, bit 0 81.2% vs 85.6%, bit 8
46.9% vs 46.3%, bit 9 42.6% vs 42.4%, bit 7 12.7% vs 13.3%, bit 11 9.2% vs 10.9%. The
small differences are population, not field — this measurement covers every record,
the earlier one covered 413,874.

This tidies the earlier conclusion that "`NN` is per-record-type payload". It is the
same statement as "the class word is a bitfield whose bits track record type", reached
twice by different routes and written down as two separate open questions. For resource
descriptors the field holds `format << 8 | depth`; for filter records it holds the class
bitfield. One field, type-dependent interpretation.

## Slot-1 bit 3: output resolution is specified, not inherited

The first slot-1 bit with established semantics, and it needed no `.sbs` at all. Once the
type high byte is known to be the output resolution and the per-filter edge slots are
known, "does this node override its resolution or inherit it?" is answerable from the
binary: read a node's resolution, follow its edge, read the input's, compare.

Over **629,153 edges** where both endpoint resolutions are readable:

```
resolution differs from input, bit 3 set     119,373      98.2% of all differing nodes
resolution differs from input, bit 3 clear     2,204
resolution same as input,      bit 3 set     119,748
resolution same as input,      bit 3 clear   387,828
```

The relationship is an **implication, not a correlation**: bit 3 clear means the
resolution is inherited (99.4%), while bit 3 set means it *may* differ — and does about
half the time, because a node can specify a size that happens to equal its input's.

Stratified by filter, the rule "bit 3 clear implies inherited" holds:

| filter | n | rule holds |
|---|---:|---:|
| `blur`, `distance`, `gradient`, `normal` | 34,336 | **100.0%** |
| `blend` | 279,764 | 99.9% |
| `levels` | 76,685 | 99.7% |
| `warp` | 26,874 | 99.2% |
| **`transformation`** | 211,494 | **32.1%** |

and across every file version, v2 through v9, at 99.3-99.8% — it is not a version
artifact.

**`transformation` is the exception that confirms the reading.** It is the filter whose
purpose is to change geometry — scale, rotate, crop — so it alters its output resolution
as a consequence of the transform rather than by declaring a size. Consistent with that,
98.8% of transformation records have bit 3 set regardless.

### This supersedes the bit-2 lead

The earlier `.sbs`-based test asked whether a node *declares* an `outputsize` parameter,
found bit 2 at r = +0.81, p = 0.004 over 12 specimens, and could not survive correction
for the 63 comparisons scanned. That question was subtly the wrong one: a declared
`outputsize` with `relativeTo="1"` means *inherit from parent*, so declaring the
parameter and overriding the resolution are different things — which is why the
correlation was mediocre and unstable across bits.

Asking the right question against the binary gives n = 629,153 instead of 12, needs no
reference graph, and yields a rule with a mechanism rather than a coefficient.

### Slot-1 flags, re-measured after removing the edge contamination

Excluding `blur`, `gradient` and `warp` — the filters whose slot 1 holds an edge —
removes 7% of records (737,955 -> 680,102). The bitfield characterisation survives:
no bit frequency moves by more than 3.1 points.

| bit | contaminated | clean | | bit | contaminated | clean |
|---|---:|---:|---|---|---:|---:|
| 0 | 65.3% | 66.7% | | 5 | 35.8% | 34.8% |
| 1 | 57.1% | 57.9% | | 6 | 19.1% | 16.7% |
| 2 | 65.6% | 67.1% | | 7 | 8.6% | 5.6% |
| 3 | 33.8% | 32.6% | | 8 | 41.1% | 40.8% |
| 4 | 54.5% | 55.0% | | 9 | 7.5% | 5.0% |

What the contamination *did* distort is the value cardinality: **18,448 distinct values
falls to 10,522**. Those 7% of records contributed 43% of the variety, which is what a
record index looks like in a histogram of flag words, and independently corroborates the
edge reading.

### Bit 2 and `outputsize`: what this corpus can and cannot establish

Re-run cleanly, the correlation is unchanged at **r = +0.812**, so the contamination was
not driving it. A permutation test over 200,000 shuffles gives **p = 0.0044**.

That is not enough, for two reasons.

**Multiple comparisons.** The hypothesis was chosen by scanning a 7-parameter x 9-bit
table. Bonferroni over 63 comparisons puts the corrected p at roughly 0.25. The
second-best hit from the same scan, `format` against bit 8, is r = +0.615 at p = 0.167 —
already indistinguishable from noise, which is what a scan of that size produces by
chance.

**No held-out data exists.** The fix for a scanned hypothesis is a pre-registered test on
untouched specimens. Partitioning the pairs by record-to-node ratio to obtain one gives
a held-out set of **size zero**: every instance-free pair in the corpus already sits in
the discovery set, because pairs outside the 0.5-1.5 band are excluded by inlining, not
by chance. The corpus cannot supply an independent sample.

**So this is where it stops.** Bit 2 relating to `outputsize` is the best-supported
reading of any slot-1 bit, it survived the correction that invalidated the measurement it
came from, and it cannot be promoted beyond a lead with the specimens available. Bits 2
and 4 also co-occur and this test cannot separate them; the remaining base parameters
appear on 0-1% of nodes here and are untestable rather than disconfirmed.

Settling it needs specimens that override the rarer base parameters, or a structural
pixel-graph matcher giving node-level pairs — the count-based route is exhausted.

### `NN`, stratified — what it is not

`NN` has been attributed twice and retracted twice. This section tests it under control
and records the boundary of what the corpus can establish.

**It is independent of the other header fields.** Of 62 (type, class) groups with ≥300
records, only 7 (11%) are dominated by a single `NN`. So it carries information the type
and class words do not.

**It is not the assembly version.** Its distribution is near-identical across every
version present:

| version | mean `NN` | `NN`=8 share |
|---|---:|---:|
| v2 | 7.30 | 53% |
| v4 | 7.58 | 67% |
| v5 | 7.27 | 66% |
| v6 | 7.42 | 65% |
| v8 | 7.25 | 65% |
| v9 | 7.03 | 47% |

**It behaves differently in driven and static records.** Holding type and class fixed:

*Driven* (class bit 0 set) — `NN` concentrates at 8, and lower values lengthen the record
monotonically:

```
type 0x02 class 0019 :  NN=8 (80,951 records, median 68 bytes)
                        NN=7 (12,900, 64)   NN=6 (5,294, 100)
                        NN=5 (1,931, 124)   NN=3 (163, 156)
```

*Static* (class `0318`, bit 0 clear) — `NN` spreads **uniformly** over 4–12 with the record
length pinned at 56 throughout:

```
NN     12    11    10     9     8     7     6     5     4
n     844   860   860 1,374 1,546 1,342 1,336 1,384 9,419
len    56    56    56    56    56    56    56    56    36
```

A near-flat distribution across nine values with no effect on the record is not the
signature of a flag, a version or a size class. It looks like an **index or counter** —
something that enumerates rather than describes. But nothing in the corpus identifies what
is being counted, and the driven-record behaviour, where `NN` clearly does track record
size, is not obviously the same phenomenon.

**Recorded as unidentified.** Established: `NN` is independent, is not a version, is not
the static/dynamic flag (that is class bit 0), is not a size class, and is not a label.
After three failed attributions the useful contribution is the list of exclusions, not a
fourth guess.

## End-to-end validation: record to bytecode to source

Every layer has been checked separately. This checks them together, on
`radial_blur_grayscale` — a two-record file whose `.sbs` source is available.

```
record #0  tag 8820  bitmap (grayscale input)      20 bytes
record #1  tag 8828  pixelprocessor (grayscale)   328 bytes,  <- #0
```

The pixelprocessor's pointer slots, searched rather than assumed (its slot is
arity-dependent):

```
slot 1:          1 -> outside
slot 2:          0 -> outside
slot 3:        360 -> 0x19C  inside, lands on a reference opcode
slot 4:        352 -> 0x194  inside, lands on a reference opcode
slot 5:         64 -> 0x074  inside, lands on a reference opcode
```

**Three pointers — one per driven parameter.** Decoding the record body under the length
rule yields 50 instructions, against 39 live nodes in the `.sbs` function graph:

| operation | decoded | `.sbs` |
|---|---:|---:|
| add | **3** | **3** |
| div | **2** | **2** |
| sub | **1** | **1** |
| mul | **1** | **1** |
| vector | **1** | **1** |
| gteq | **1** | **1** |
| samplelum | **1** | **1** |
| while | **1** | **1** |
| set | 10 | 7 |
| sequence | 8 | 5 |
| get | 8 | 11 |
| const | 5 | 4 |
| reference | 6 | — |

Eight operations agree exactly, including `samplelum` and `while`, which are distinctive
enough that agreeing by chance is implausible. The differences are confined to the
structural operations — `set`, `sequence`, `get`, `const` and `reference` — where the
compiler introduces temporaries and where graph-input references have no corresponding
`.sbs` node at all. The 50:39 ratio is consistent with that.

### What this demonstrates

A single traversal now goes from an unparsed `.sbsar` to the arithmetic of a specific
node's parameter:

```
.sbsar archive
  -> .sbsasm, header, interface block          (validated 493/493)
  -> record directory, entry + 52              (95% land on a valid tag)
  -> record #1, tag 8828 = pixelprocessor      (filter named from .sbs counts)
  -> edge slot -> record #0 = bitmap input     (dataflow back-reference)
  -> pointer slots 3, 4, 5                     (one per driven parameter)
  -> instruction stream, length = (op>>10)+1   (94.8% corpus coverage)
  -> add, div, sub, mul, vector, gteq,
     samplelum, while                          (matching the authored graph exactly)
```

Every step in that chain was derived independently, and several were derived before the
steps around them were understood. That they compose is the strongest evidence the model
is right.

### The 52-byte skew, characterised

Open question 1 asked why the skew constant is 52. It cannot be answered from the bytes,
but it can now be bounded much more tightly than "uncharacterised".

**It is universal.** Testing candidate skews against the fraction of directory entries
landing on a valid record tag, per assembly version:

| version | entries | +48 | +50 | **+52** | +54 | +56 |
|---|---:|---:|---:|---:|---:|---:|
| v2 | 16,482 | 1.4% | 0.9% | **97.1%** | 0.0% | 0.3% |
| v3 | 2,428 | 0.2% | 0.4% | **99.5%** | 0.0% | 0.2% |
| v4 | 57,521 | 5.5% | 1.5% | **99.1%** | 0.0% | 0.4% |
| v5 | 221,670 | 1.1% | 0.3% | **93.0%** | 0.0% | 0.3% |
| v6 | 98,261 | 0.8% | 1.1% | **97.6%** | 0.0% | 0.4% |
| v8 | 16,305 | 0.1% | 0.0% | **99.4%** | 0.0% | 0.2% |
| v9 | 86,612 | 2.7% | 0.0% | **95.8%** | 0.0% | 0.4% |

Exactly 52, on every version from v2 to v9, with no neighbouring value coming close. The
same constant governs the value-table pointer at `0x2C`, so one convention covers both.

**The obvious explanation is wrong.** 52 = 0x34 = the header size (0x38) minus 4, which
suggested the header is *really* 52 bytes and the word at `0x34` is the first body word —
stored offsets would then simply be body-relative. Tested across 300 specimens, the word
at `0x34` is `0` in **100%** of them, as are every other nominally-constant header field
(`0x14`, `0x18`, `0x20`, `0x24`, `0x28`, `0x30`). A body word would be expected to vary.
So `0x34` is a genuine header constant and the tidy explanation does not hold.

What remains is a characterised convention rather than an explained one: offsets are
stored relative to file position 52, universally and version-independently, for reasons
not recoverable from the format itself. Parsers need only apply it; the eliminated
hypothesis is recorded so it is not re-proposed.

### `0x0842` is not an exception — and the bool component field is fixed

An early section recorded `0x0842` as "the exception: it maps to int1 while its bits 6-7
read as 1, so the `0x08xx` base does not follow the same convention. Unexplained."

It is explained, and it is not an exception. Decoded with the opcode layout established
much later — bits 9-8 are a **type** field — `0x0842` is `type 0` = **bool**, op-id `0x02`
= reference. It is a *boolean* reference, not an int1 one.

The confusion came from the manifest, which lumps booleans and 1-component integers
together under input type 4. Checking every reference opcode against the manifest type of
the input it actually names, over 246,615 references:

| opcode | type field | manifest type of referenced input |
|---|---|---|
| `0A42` | int, 2 comps | int2 **100%** |
| `0A02` | int, 1 | int1/bool **100%** |
| `0902` | float, 1 | float1 **100%** |
| `0D02` | float, 1 (padded) | float1 **100%** |
| `0E02` | int, 1 (padded) | int1/bool **100%** |
| `0942` | float, 2 | float2 **100%** |
| `0842` | **bool** | int1/bool **100%** |
| `0982` | float, 3 | float3 **100%** |
| `0C42` | **bool** (padded) | int1/bool **100%** |
| `09C2` | float, 4 | float4 **100%** |

Every reference opcode names an input of exactly the type its type field declares, without
exception. `0x0A02` and `0x0842` both point at manifest type 4 because that manifest code
covers both int1 and bool — **the ISA draws a distinction the manifest does not.**

### The component field is unused for booleans

This also settles an oddity flagged in the opcode catalogue: `0x0862` compares scalars yet
its bits 7-6 read as component count 2. Checking every catalogued bool opcode, **all of
them** have bits 7-6 = `01`, including the constant `0440`, `not` at `045C`, and the whole
comparison block `085A`–`0862`.

A field that never varies is not encoding anything. **For type 0 (bool), bits 7-6 are
fixed at `01` and carry no component count** — booleans are scalar, and the field is
simply inert. The catalogue's caveat that the component rule is "not general" can be
sharpened: it applies to float and int, and is unused for bool.

### Record bytecode is length-prefixed

Every record pointer targets a word **two bytes before** the first instruction —
291,802 of 291,802, without exception. That word is an instruction count:

```
the u16 at the pointer target equals the number of instructions that follow
   exact match : 223,905 / 291,802  = 76.7%
   (word - counted) : 0 in 77%, then 4, 6, 8, 10 — all positive and even
```

The residual is under-counting by the measuring loop, not disagreement: every mismatch has
the stored value *larger* than the counted one, by an even number of tokens.

Commonest prefix values are 1 (33%), 3 (19%), 5 (7%), 7 (3%) — small odd counts — with a
second cluster at 68, 70, 72, 74 for substantial expressions.

#### This explains `0x0A420001`

An early section recorded: "**`0x0A420001` is a body-stream token, not an input-block
marker.** It recurs at several offsets… file-wide counts run from 10 to 4276 and correlate
with neither input count (r = 0.23) nor output count (r = 0.35)… It appears to be a common
instruction encoding in the record stream."

It is not one token. It is **two**: a length prefix of `0x0001` followed by the `0x0A42`
int2 reference opcode. A single-instruction parameter expression — the commonest kind,
since most nodes drive only their output size. That is why it recurs everywhere and why it
correlates with nothing at the graph level: it counts *driven parameters*, not inputs or
outputs.

### The `Leaking004` trailer exception was an artifact

An early section recorded `trail[6] = table_start - 52` holding for "57 of 58;
Leaking004 alone is `-56`, unexplained". Re-measured with the current table locator:

```
LeakingSubstance004:  table_start 0x8F0F4,  trail[6] 585,920,  difference 52
```

And across the whole corpus:

```
table_start - trail[6] == 52  :  489 / 489 specimens  (100.0%)
```

**No exceptions.** The `-56` came from the earlier anchor-and-walk-back table locator,
which was superseded by the `0x2C`-derived one. The relation is universal, matching the
directory skew and the `0x2C` skew — one constant governs every offset in the format.

### On re-reading old notes

Three separate long-standing "unexplained" items have now been resolved not by new
measurement but by **re-reading old observations against later structure**: `0x0B19` (a
record class word mistaken for a type-3 opcode), `0x0842` (a bool reference mistaken for
an int1 exception), and now `0x0A420001` and the `Leaking004` trailer. In each case the
original observation was accurate and the interpretation was limited by what was known at
the time.

### Why records are variable-length

Records were established early as variable-length with no per-tag fixed size, and that was
recorded as a fact without a cause. The cause is now measurable: **a record's length is
its header plus its parameter bytecode, stored inline.**

Correlating each record's total length against the sum of the length prefixes of the
bytecode blocks it points at:

| type | filter | n | corr(instructions, length) |
|---|---|---:|---:|
| `0x1E` | levels | 34,645 | **1.000** |
| `0x18` | directionalwarp | 26,274 | **0.997** |
| `0x16` | *unidentified* | 5,708 | **0.996** |
| `0x0E` | warp | 12,813 | **0.993** |
| `0x14` | blur | 5,163 | **0.992** |
| `0x02` | blend | 119,121 | **0.990** |
| `0x03` | blend (colour) | 8,324 | 0.984 |
| `0x04` | transformation | 72,728 | 0.942 |
| `0x28` | pixelprocessor | 5,361 | 0.816 |
| `0x29` | pixelprocessor (colour) | 10,505 | 0.658 |
| `0x00` | gradient | 4,751 | 0.476 |

For eight of eleven types the relationship is near-deterministic. The three weaker ones are
exactly those with **multiple pointers** — pixelprocessor averages 1.9 bytecode blocks per
record against ~1.05 for the rest — so a single summed count is a poorer proxy there.

This closes the framing question properly. Records need no length field because they are
delimited by the directory, and their size is a consequence of how much bytecode their
parameters require.

### A retracted small-sample claim

An early section measured record lengths in tokens and flagged `0x880C` as "genuinely
bimodal (5 in 19 cases, 7 in 14). Possibly two forms."

Re-measured against directory-delimited boundaries over 2,253 records rather than 33, the
distribution is neither bimodal nor at those values: 8 tokens (45%), 14 (19%), 10 (19%),
16 (5%). Nor does it split on the driven/static flag — 2,253 of 2,254 `0x880C` records are
driven. The spread is the bytecode-length effect above, which is multi-modal because
parameter expressions come in many sizes.

**"Possibly two forms" was small-sample noise from a superseded measurement method.** The
same caution applies to the neighbouring `0x8818` disagreement recorded in that section
(learner 17 vs method 15, n=20); both predate the exact directory-based measurement and
neither should be relied on.

### The early record-length table was short by exactly one instruction

An early section reported 27 "stable" opcode lengths, cross-checked across two independent
learning runs. Measured now against directory-delimited record boundaries, **all twelve of
its `0x88xx` entries differ — and eight of them by exactly the same amount:**

| tag | early value | measured | difference | modal share |
|---|---:|---:|---:|---:|
| `8820` | 7 | **10** | +3 | 91% |
| `8804` | 9 | **12** | +3 | 20% |
| `8805` | 9 | **12** | +3 | 55% |
| `8807` | 11 | **14** | +3 | 53% |
| `880E` | 11 | **14** | +3 | 13% |
| `880D` | 13 | **16** | +3 | 72% |
| `881E` | 13 | **16** | +3 | 27% |
| `8806` | 15 | **18** | +3 | 33% |
| `8803` | 13 | 36 | +23 | 22% |
| `8816` | 13 | 38 | +25 | 16% |
| `8818` | 17 | 40 | +23 | 26% |
| `8809` | 21 | 584 | — | 70% |

**Three tokens is exactly one reference instruction** — opcode plus a two-token uid. The
anchor-residual method walked from one anchor *up to* the next without including it, so
every measurement was short by precisely that. A systematic boundary error, not noise:
eight independent measurements are wrong by the identical amount.

The four larger discrepancies belong to tags whose modal share is 13–26%, i.e. records
whose length genuinely varies with their inline bytecode. For those, no single "length"
exists and the early table's premise does not apply.

### Three entries were not instructions at all

The same table's "other" group lists `0x6605`=9, `0x7704`=9, `0x440C`=13. Under the tag
structure established much later these are **record tags**, not opcodes: `NN`=6 type
`0x05`, `NN`=7 type `0x04`, `NN`=4 type `0x0C` — transformation, transformation and
uniform. The learner was measuring records as though they were instructions.

Two further entries are also wrong: `0x0603` is listed at 20 tokens where the length rule
gives 2 (it is a variable read with one operand), and `0x0001`/`0x0003` are listed at 1
token although they are below `0x0400` and are not opcodes at all — they are operand
tokens.

Of the 27 "stable" lengths, the six **reference** and two **constant** entries are
correct and survive; the twelve `0x88xx` entries are systematically short or inapplicable;
and five of the seven "other" entries are misclassifications. The section's own caution —
that cross-run agreement was the criterion — did not help, because both runs shared the
same boundary convention and the same inability to tell a record from an instruction.

### The table-less resource segments are not record data

An early section left the 66-of-102 table-less segments "**Undetermined**", noting that
some hold float32 raster data for which no format code exists in the tag vocabulary. Two
questions were open: are they resources at all, and are they perhaps part of the record
stream misread as pixels?

**They are not record data.** In `BricksSubstance004` the directory sits at `0xB00038`,
leaving an 11.5 MB region before it. Of the file's **3,042 records, zero** fall in that
region — every record target lies between `0xB02FE8` and `0xC38CF4`, entirely after the
directory. Meanwhile the region *after* the directory is **100% covered** by records
(1,269,456 of 1,269,496 bytes). The two areas do not overlap at all.

**They are float32 image data.** Sampling 50,000 consecutive f32 values from the region's
midpoint: **100% lie in [0, 1]**, varying smoothly (0.2654, 0.2666, 0.2662, 0.2651,
0.2643 …). Entropy is 5.01 against 4.58 for the record body — higher, as pixel data
should be relative to structured records.

**But the region is not a single raster.** Testing every start offset in its first 4 KB
for an exact tiling with a power-of-two width, at 1–4 channels of f32: **zero tilings**,
even relaxing the constraint to power-of-two width alone. A contiguous
width x height x channels array does not fit at any alignment.

The consistent reading is that these segments hold **several concatenated float32
resources**, exactly as the tagged segments hold several 8-bit ones — which is why no
single tiling fits and why the autocorrelation stride method resolved only 45 of 102
segments. What is missing is the table that would give their boundaries. Whether the
engine recovers those from the graph, or whether a table exists in a form not yet
recognised, is unresolved.

This does not name the format, but it removes two hypotheses: the segments are neither
misparsed record data nor a single image.

### Table-less segments are heterogeneous — resolved

The previous section narrowed these segments to "several concatenated float32 resources".
That was half right. They are concatenated resources, but **of mixed formats**, which is
why no single tiling could ever fit.

Zoning `BricksSubstance004`'s 11.5 MB pre-directory region by the statistics of the fourth
byte of each 4-byte group:

| zone | bytes | `byte[3] == 0xFF` | `byte[3]` is a float exponent | reading |
|---|---:|---:|---:|---|
| `0x38`–`0x200038` | 2,097,152 | **100.0%** | 0.0% | **RGBA8**, alpha always opaque |
| `0x200038`–`0x500038` | 3,145,728 | 0.0% | 23.2% | 8-bit, predominantly zero |
| `0x500038`–`0xB00000` | 6,291,400 | 0.0% | **100.0%** | **float32** |

The raw bytes confirm each zone directly:

```
0x000038   bc b8 a9 ff  bf bb af ff  ca c6 b9 ff     RGBA8, opaque
0x200038   00 00 00 00  00 00 00 00  00 00 00 00     zeros
0x500038   00 00 80 3f  00 00 80 3f  00 00 80 3f     1.0f repeated
0x800000   ea c5 03 3f  b0 9c 05 3f  06 1f 05 3f     0.514, 0.521, 0.520
```

**The dimensions are consistent.** 2,097,152 bytes of RGBA8 is 524,288 pixels =
**512 x 1024**. The float zone holds 1,572,864 f32 = **3 x 512 x 1024**. One RGBA8 image
and three float32 channels at the same resolution, concatenated.

### What this explains

Three earlier observations follow from it at once:

- **"No format code corresponds to f32."** Correct, and irrelevant — these segments carry
  no table, so no format code is written for them anywhere.
- **Autocorrelation resolved only 45 of 102 segments.** A stride search assumes one raster.
  Half the segments contain several, in different bit depths, so no single stride exists.
- **No exact tiling at any alignment** (previous section). Also expected: the region is not
  one array but three, at different bytes-per-pixel.

The remaining unknown is narrow and well-posed: what delimits the zones, given that no
table describes them. ~~The boundaries here fall at `0x38` plus a multiple of 1 MiB.~~
**[RETRACTED — that was quantisation by the 64 KiB measuring block, not format structure.
See "Zone structure across table-less segments".]**

### Zone structure across table-less segments

Applying the byte-3 classifier to six large table-less segments generalises part of the
previous finding and **retracts another part of it**.

**RGBA8 zones are exact power-of-two images.** Every RGBA8 run found resolves cleanly:

| specimen | RGBA8 bytes | pixels | dimensions |
|---|---:|---:|---|
| `BricksSubstance006` | 67,108,864 | 16,777,216 = 2^24 | **4096 x 4096** |
| `GrassSubstance002` | 4,194,304 | 1,048,576 = 2^20 | **1024 x 1024** |
| `GravelSubstance002` | 4,194,304 | 1,048,576 = 2^20 | **1024 x 1024** |
| `BricksSubstance004` | 2,097,152 | 524,288 = 2^19 | **512 x 1024** |

`BricksSubstance006` is a single 4096 x 4096 RGBA8 image occupying exactly 64 MiB — the
cleanest case in the corpus.

**The "1 MiB boundary" claim is retracted.** The previous section observed that
`BricksSubstance004`'s zone boundaries fell at `0x38` plus exact multiples of 1 MiB and
suggested resources are written in a fixed order at aligned offsets. Across six specimens
the boundaries fall at 0.062, 0.188, 0.312, 0.438, 0.562 MiB and so on — that is, at
multiples of **64 KiB, which is exactly the block size the classifier used**. The apparent
1 MiB structure was quantisation by the measuring instrument, not a property of the format.
The one file that appeared to show it did so by coincidence, having few and widely-spaced
zones.

**The intermediate zones remain uncharacterised.** *(Resolved in the next section: they
are RGB8, L8 and 16-bit resources, identified by byte-lag periodicity.)* Between the clean
RGBA8 and float32 runs lie large regions the classifier labels "other" — neither
opaque-alpha 8-bit nor in-range float. `GrassSubstance002` alternates zeros and "other" more than twenty times.
These may be 8-bit single-channel data, compressed blocks, or several small resources; the
byte-3 test cannot separate those cases, and a finer instrument is needed to say more.

What generalises: table-less segments contain multiple resources, at least some of which
are power-of-two RGBA8 images, alongside float32 data and regions of other kinds.

### Table-less segments hold the same formats the resource table names

The byte-3 test could only separate opaque-alpha RGBA8 from in-range float32, leaving
large "other" regions unexplained. A better instrument settles them: **mean absolute
difference between bytes at lag 1, 2, 3 and 4**. Pixel data is smooth along its own
stride, so the lag with the smallest difference gives the bytes-per-pixel.

It validates on two knowns before being trusted:

| zone | entropy | minimising lag | reading |
|---|---:|---:|---|
| known RGBA8 | 5.01 | **4** | 4-byte pixels — correct |
| **record body** | 4.58 | **2** | **2-byte tokens — the u16 instruction stream** |

The record body coming out as 2-byte periodic is a useful check: the instrument recovers
the instruction encoding without being told about it.

Applied to the unexplained regions:

```
BricksSubstance004   RGBA8 (524,288 px = 2^19) | RGB8 x16 | L8 | f32 x3 | zeros
GravelSubstance002   4-byte | 16-bit | RGBA8 (1,048,576 px = 2^20) | f32 | 16-bit
GrassSubstance001    L8 | 16-bit x5 | RGB8 x2 | L8 x9 | zeros
```

**The formats are exactly those the resource table encodes.** The image-format decode
recorded much earlier in this document gives `0x01`=L8, `0x02`=RGB8, `0x03`=RGBA8,
`0x05`=L16, `0x07`=RGBA16. The table-less segments contain L8, RGB8, RGBA8 and 16-bit
data — the same family — plus float32, which is the one format with no code in that
vocabulary.

So the earlier note's dilemma — "either these use codes absent from the tagged files, or
they are not table-described resources at all" — resolves as **both, partly**: the
segments hold ordinary resources in the documented formats *and* float32 data the tag
vocabulary has no code for. What distinguishes them from tagged segments is only the
absence of the table, not the nature of the contents.

The residual unknown is now specific: **what supplies the boundaries and dimensions**,
given that the same file describes its tagged segments explicitly but leaves these
implicit. The most likely answer is that these resources are graph-internal intermediates
whose size the engine derives from the graph, whereas tagged resources are author-supplied
bitmaps that must be described. **[TESTED: `P(table | no bitmap node) = 0/20`. See "A
resource table requires an author-supplied bitmap" — confirmed for small single-channel
segments, untested for the large mixed ones.]**

### A resource table requires an author-supplied bitmap

The previous section guessed that tagged resources are author-supplied bitmaps while
table-less ones are engine-internal. That is testable against the paired corpus, since the
`.sbs` says whether the author placed any `bitmap` nodes.

Over 43 paired specimens with a pre-directory segment of at least 64 KiB:

| | has `bitmap` node | no `bitmap` node |
|---|---:|---:|
| **has resource table** | 12 | **0** |
| **no resource table** | 11 | 20 |

**`P(table | no bitmap node) = 0/20 = 0.00`.** A resource table never appears in a graph
that places no bitmap. The converse is weaker — 11 specimens have bitmap nodes without a
table, plausibly because those bitmaps are linked rather than embedded — so the relation is
necessary, not sufficient.

The size split is equally sharp. Specimens with a table carry segments of 5.7 to 21 MB;
bitmap-free specimens carry 64 to 328 KiB.

### Bitmap-free segments are small single-channel resources

Classifying those small segments by byte-lag periodicity:

```
content   L8       19 specimens
          16-bit    5 specimens

sizes     262,144 B  (256 KiB = 512x512 L8)   x6
          131,072 B  (128 KiB)                x4
           65,536 B  (64 KiB  = 256x256 L8)   x1
```

Almost all are exact powers of two and every one is single-channel. Small square
grayscale resources in graphs that reference no author bitmap are consistent with
engine-side lookup data — noise tables, curves, distance fields — rather than artwork.

### The limit of this evidence

The large multi-format table-less segments examined earlier — `BricksSubstance004`'s
11.5 MB of RGBA8 + RGB8 + L8 + float32 — belong to specimens in the unpaired corpus, with
no `.sbs` available. Their provenance is therefore **untested**: the argument above covers
the small single-channel population only, and it would be wrong to extend it to the large
mixed segments without evidence.

What is established: a resource table implies an author bitmap; bitmap-free graphs still
carry small single-channel resource data that no table describes.

### Segment sizes are raster-shaped but not rigidly aligned

Testing whether the large table-less segments are cached graph *outputs*: the manifest
gives `$outputsize` = `8,8` for every corpus specimen, and segment-size divided by output
count yields a square power-of-two raster in only 2 of 16 cases. **They are not one render
per output.**

Their sizes are nonetheless raster-shaped. Over 109 specimens with a segment of at least
64 KiB:

```
divisible by  64 KiB :  86/109  (79%)
divisible by 256 KiB :  74/109  (68%)
divisible by 512 KiB :  65/109  (60%)
divisible by   1 MiB :  54/109  (50%)
```

and the commonest sizes are whole megabytes — 18 MiB (12 specimens), 17 MiB (5), 12 MiB
(5), 19 MiB (4), 20 MiB (3). At 1024 x 1024 the natural units are exactly L8 = 1 MiB,
RGB8 = 3 MiB, RGBA8 = 4 MiB and f32 = 4 MiB, so integer-megabyte totals are what a
concatenation of 1024-square rasters in mixed formats would produce. `BricksSubstance004`
is 11 x 1024^2 bytes exactly, and its measured contents — RGBA8 512x1024, sixteen RGB8
runs, an L8 run and three f32 runs — sum to that.

**But alignment is not a format rule.** Twenty-three of 109 segments are not divisible by
64 KiB at all, and several sit at exactly 32 KiB past a 64 KiB boundary
(`MetalSubstance009`, `RustSubstance002`). A format that padded resources to a fixed
alignment would not do that.

So the position is: segment sizes are consistent with concatenated power-of-two rasters in
the documented formats, which corroborates the byte-lag classification, but the sizes alone
do not determine the contents and the segments are not uniformly aligned.

~~**Provenance of the large segments remains untested.**~~ **[WRONG — the corpus does
contain paired specimens with large table-less segments, including four with zero bitmap
nodes. See "Large table-less segments are engine-generated".]**

### Large table-less segments are engine-generated — resolved

The previous two sections declared this question untestable, on the grounds that every
specimen with a large table-less segment lived in the unpaired corpus. **That was wrong,
and the data was already present.** Searching the paired set for segments of at least 1 MB
without a resource table returns 13 specimens, four of which place **no `bitmap` node at
all**:

| specimen | segment | `bitmap` nodes | leading content |
|---|---:|---:|---|
| `substance-for-unity-extensions__Un…` | 23,278,060 | **0** | 4-byte |
| `substance-for-unity-extensions__Ru…` | 23,278,016 | **0** | 4-byte |
| `Hard-Science-Old__flowingLava_v35` | 3,746,488 | **0** | 4-byte |
| `substance-for-unity-extensions__Ti…` | 2,153,472 | **0** | 16-bit |
| `Hard-Science-Old__Small_Rocks` | 83,886,080 | 4 | L8 |
| `sat-scons__pbr_render` | 33,816,576 | 1 | f32 |

A 23 MB resource segment in a graph containing zero author bitmaps settles it: **large
table-less segments are engine-generated, not author-supplied artwork.** The hypothesis
that they might be undescribed bitmaps is refuted, not merely unconfirmed.

Combined with the earlier result, the rule is asymmetric and now complete:

- **A resource table implies author bitmaps.** `P(table | no bitmap node) = 0/20`, and
  every table-bearing specimen places 6–7 of them.
- **Table-less segments are engine data at any size** — from 64 KiB single-channel lookup
  tables up to 83 MB of mixed L8 / RGB8 / RGBA8 / 16-bit / float32.

Size is not the discriminator; the table is. Author bitmaps are described because the
engine cannot infer them; engine-generated resources are not, because it can.

### The error worth recording

Two iterations in a row concluded "the corpus does not contain the specimens needed", and
both were wrong — the specimens were there, filtered out by a query that only looked at
`corpus/` for large segments and only at `pairs*/` for `.sbs` files. The claim "this
cannot be tested with the available data" is itself a claim, and it deserves the same
scepticism as any other. It should be checked by searching, not asserted from the shape of
earlier queries.

### The `.sbs` format has two serialisations — and one of my regexes only saw one

Investigating why `Stadsspel__Lines` appeared to have no sub-graph instances while its
`.sbsasm` clearly contained inlined nodes revealed a second element encoding:

```
direct :  <comptype v="2"/>
nested :  <comptype><value v="2"/></comptype>
```

Both occur throughout the corpus. Measured across all 199 paired `.sbs` files:

| element | direct `v=` | nested `<value>` | nested share |
|---|---:|---:|---:|
| `<filter>` | 9,331 | 0 | **0.0%** |
| `<function>` | 197,749 | 0 | **0.0%** |
| `<comptype>` | 11,823 | **6,594** | **35.8%** |

`<compInstance><path>` is likewise nested in 1,812 cases.

**What this did and did not affect.** The filter names and function-graph node names —
the ground truth behind every filter identification and every opcode identification in
this document — are **100% direct form**, so those counts were never wrong. The instance-
free filter used `<compInstance>` element counts rather than paths, so that was correct
too. Two things were affected:

- The channel-parity analysis read `<comptype>` with the direct-form regex only, so **a
  third of the nodes were recorded as unknown channel** and silently dropped.
- The claim "41.7% of instance references resolve to a graph in the same file" was
  computed over only the `pkg:///` direct-form paths.

**Re-running the parity analysis with both forms.** Missing-comptype nodes drop from a
substantial fraction to **zero**, and every existing filter assignment comes back as the
top candidate for its channel:

```
fxmaps/gray -> 08   levels/gray -> 1E   blend/gray -> 02   blend/col -> 03
warp/gray   -> 0E   uniform/col -> 0D   bitmap/col -> 21   bitmap/gray -> 20
transformation gray -> 04, col -> 05    pixelprocessor col -> 29   gradient/col -> 01
```

No conclusion changes; the vote margins improve. That is the useful outcome — a
data-extraction bug affecting 36% of one field, discovered late, turned out not to have
corrupted the results built on it, and re-running with the fix confirms rather than
overturns them.

The lesson is narrower than the earlier ones and worth stating separately: **a regex over
a serialisation format is a parser, and an untested parser silently drops what it does not
match.** The `?` entries in the earlier parity table were the visible symptom, and I read
them as missing data in the source rather than as a defect in my reader.

### Serialisation audit of every parsed element

Having found one element with two encodings, the responsible move is to check all of them
rather than the one that happened to break. Across the 199 paired `.sbs` files:

| element | direct `v=` | nested `<value>` | nested % | used by |
|---|---:|---:|---:|---|
| `uid` | 291,408 | 0 | 0.0% | `sbsgraph` |
| `identifier` | 313,570 | 0 | 0.0% | graph names |
| `name` | 238,037 | 0 | 0.0% | — |
| **`filter`** | 9,331 | 0 | **0.0%** | **filter identification** |
| **`function`** | 197,749 | 0 | **0.0%** | **opcode ground truth** |
| `type` | 204,522 | 9,137 | 4.3% | — |
| `connRef` | 277,504 | 16,462 | **5.6%** | `sbsgraph` edges |
| `constantValueInt1` | 2,851 | 245 | 7.9% | — |
| `rootnode` | 4,701 | 1,743 | **27.0%** | `sbsgraph` live nodes |
| `path` | 4,291 | 1,812 | **29.7%** | instance expansion |
| `connRefOutput` | 11,602 | 5,087 | 30.5% | — |
| `comptype` | 11,823 | 6,594 | **35.8%** | channel parity |
| `constantValueFloat1` | 29,359 | 61,858 | **67.8%** | — |

**The two elements every identification rests on — `filter` and `function` — are 100%
direct form.** So the filter table and the opcode identifications were never exposed to
this bug. That is luck rather than judgement, and worth saying plainly.

**`rootnode` at 27% was the damaging one.** When `live()` cannot find a root it falls back
to treating every node as live, so more than a quarter of graphs had dead-code elimination
silently disabled. After fixing the pattern:

```
rootnode matches      : 4,701 -> 6,444   (+1,743, +37%)
graphs with no root   : 1,743 -> 0
dead nodes now found  : 1,067  (0.5% of 194,850) across 168 graphs
```

**The impact on conclusions is nil.** `ie_processing`, the specimen behind the strongest
validation in this document, is **unchanged at 11 exact matches** — its two graphs always
had findable roots, and every node in them genuinely is live. The 0.5% of nodes affected
corpus-wide is far below the margins any identification was decided by.

So this is a defect worth fixing and a result worth not overstating: a real parser bug,
present for the whole investigation, that happened to miss the fields that mattered.

## The function-graph language is fully accounted for

With the parser corrected, re-running the isolating-graph survey leaves **only two node
types** that still isolate a single unknown: `pow2` (8 graphs) and `passthrough` (2). Both
are ones already shown to be lowered rather than compiled to an opcode, so the survey has
nothing left to find.

Auditing the entire vocabulary — every `<function>` node in the paired corpus:

```
72 node types, 197,749 uses

  mapped to an opcode : 192,693 uses  (97.4%)
  lowered / eliminated:   5,056 uses  ( 2.6%)
  unaccounted         :       0 uses  ( 0.0%)
```

The 2.6% not mapped to an instruction are accounted for individually:

| node | uses | disposition |
|---|---:|---|
| `instance` | 4,977 | **inlined** — no call instruction exists |
| `passthrough` | 41 | eliminated by the compiler |
| `pow2` | 32 | lowered to `exp2(ln x / ln 2 * p)` |
| `get_string` | 3 | never observed in compiled output |
| `log` | 2 | via `ln` |
| `tan` | 1 | never observed |

Every remaining node type maps to one of 30 identified op-ids. The long tail is covered
too — `swizzle4` (2 uses), `ivector2` (4), `get_integer3` (1), `tofloat4` (1) all fall
under op-ids already established for their families, which is a check in itself: the
type-and-width encoding predicts opcodes for node variants too rare to have been used in
deriving it.

### What this closes

The parameter-expression language — the part of a `.sbsar` that computes node parameters
at render time — is now fully readable. Combined with the instruction length rule, the
value table and the record bytecode pointers, a parameter expression can be located,
decoded and named end to end without any unknown remaining in the path.

The remaining unknowns in the format lie entirely outside this language: `NN` in the
record tag, filter type `0x16`, the class-word and slot-1 bitfields, and the internal
boundaries of table-less resource segments.

## Why `0x16` cannot be named from this corpus

`0x16` is the last unidentified filter type of any size — 6,785 records, one input,
grayscale in and grayscale out. Every candidate from the `.sbs` vocabulary has been
eliminated: `grayscaleconversion` (takes grayscale input 99.8% of the time, but must take
colour), `emboss` (two inputs), and `hsl`, `sharpen`, `curve`, `valueprocessor` (each
authored in a specimen containing **zero** `0x16` records).

The reason no candidate fits is now clear. **`0x16` never appears in an authored graph.**

| instances in the `.sbs` | specimens containing `0x16` | rate |
|---|---:|---:|
| **0** | **0 of 24** | **0%** |
| 1–2 | 1 of 16 | 6% |
| 3–9 | 15 of 50 | 30% |
| 10+ | 65 of 94 | **69%** |

The rate rises monotonically with the number of inlined sub-graphs, and **no instance-free
specimen contains a single `0x16` record**. It arrives only through inlining.

Which library graphs? Comparing instance targets in specimens with and without `0x16`, the
targets appearing *only* alongside it are Substance's own bundled filters:

```
ambient_occlusion_2 (39)   blur_hq_grayscale (33)   slope_blur_grayscale (26)
perlin_noise_zoom (24)     fractal_sum_base (19)    cells_1 (18)
```

A worked example is `Stadsspel__Lines`, whose pixel graph is three nodes —
`instance -> transformation -> output` — while its binary holds six records:

```
#0 fxmaps          #3 blend  <- #0, #2
#1 0x16  <- #0     #4 0x16   <- #3
#2 0x16  <- #1     #5 transformation <- #4
```

Record #5 is the authored `transformation`. Records #0–#4 are the inlined `stripes`
library graph, and three of its five nodes are `0x16`.

### The terminal position

Naming `0x16` requires the `.sbs` sources of Substance Designer's bundled library, which
ship with the proprietary application. They are not in this corpus, and obtaining them is
outside what this work will do. This is not a gap that a larger corpus of *authored*
material would close — the monotonic table above shows authored graphs never produce this
node, so collecting more of them cannot help.

What is established about it stands on its own: a one-input, channel-preserving,
grayscale filter, pointer at slot 3, record length determined by inline bytecode at
r = 0.996, used heavily inside blur, ambient-occlusion and noise library filters.

## `NN` — the terminal position

`NN`, the high byte of a record tag, has been attributed twice and retracted twice. This
records what is now established, and closes it as unidentifiable from the available data.

### Everything it is not

| hypothesis | test | result |
|---|---|---|
| a size class | median record length by `NN` | non-monotonic: 16, 32, 36, 52, 64 |
| the assembly version | `NN` distribution per version | flat — mean 7.03–7.58 across v2…v9 |
| the static/dynamic flag | stratify by `NN`, vary class bit 0 | **bit 0 controls it within every `NN` value** |
| derivable from type or class | dominant `NN` per (type, class) group | only 7 of 62 groups (11%) |
| authored vs inlined provenance | mean `NN` of trailing authored records vs inlined | 7.80 vs 7.54; higher in 79/141 (56%) |
| a checksum of the record body | 8 hash forms vs the value | 2–12%, against a 72% always-guess-8 baseline |

### Correlation with every measurable property

Over 369,932 records, `NN` against each per-record quantity:

```
record type          -0.032      bytecode instructions   0.084
class word            0.007      input count             0.083
record length        -0.009      position in directory   0.058
pointer count         0.143      assembly version       -0.058
channel (odd/even)   -0.074      class bit 0             0.303
```

Nothing exceeds |r| = 0.15 except class bit 0, and that is the confound already
identified — `NN` = 8 carries bit 0 set 97% of the time, `NN` = 11 only 2.7%.

### The one structural fact

In **static** records (class bit 0 clear) `NN` spreads almost uniformly over 4–12 while
the record length stays pinned:

```
NN     12    11    10     9     8     7     6     5
n     844   860   860 1,374 1,546 1,342 1,336 1,384
len    56    56    56    56    56    56    56    56
```

A near-flat distribution across nine values with no effect on anything measurable is the
signature of an **identifier** — something that enumerates rather than describes. But
nothing in the file is enumerated 4 to 12 times per record type, and no hash of the record
reproduces it.

### Why this is terminal

`NN` carries information that nothing else in the file predicts, and that predicts nothing
else in the file. That is consistent with a reference into state the `.sbsar` does not
contain — a runtime resource slot, an engine-side table index, a build identifier. Such a
field cannot be decoded from the artefact alone, however large the corpus.

**A parser can ignore it safely.** Everything a reader needs — the filter, the channel
mode, the inputs, the parameter bytecode — comes from the type byte, the class word and
the slots. `NN` has never been required to interpret a record correctly.

## Resource boundaries: the structure, found via ground truth

Table-less segments have no delimiters, so boundaries had to be recovered. The route that
worked was not analysing the table-less segments but reading the **tabled** ones, where the
resource table states the answer.

### The resource table uses the same +52 skew

`Metal_Vent_006`'s table gives resource offsets 4, 3145732, 6291460, … Adding 52 puts them
at `0x38`, `0x300038`, `0x600038` — the segment start and 3 MiB steps. **Every offset in
the format, without exception, is stored relative to file position 52**: the value table
pointer, the trailer, the record directory, and now the resource table.

### Every embedded resource is 1024 x 1024

Reading the size and format of every resource in all 33 tabled segments:

| format | size | 1024 x 1024 x bpp |
|---|---:|---|
| `L8` | 1 MiB | 1024 x 1024 x 1 |
| `L16` | 2 MiB | 1024 x 1024 x 2 |
| `RGB8` | 3 MiB | 1024 x 1024 x 3 |
| `RGBA8` | 4 MiB | 1024 x 1024 x 4 |
| `RGBA16` | 8 MiB | 1024 x 1024 x 8 |

Sample sequences, in MiB per resource:

```
Metal_Vent_006          RGB8 RGB8 RGB8 RGB8 RGB8 RGB8          [3,3,3,3,3,3]
st_wood_fine_20         L8 RGB8 RGBA16 L8 L8 L16 L8            [1,3,8,1,1,2,1]
celtic_orna_mossy_001   L16 RGB8 RGBA16 L8 RGBA8 L16           [2,3,8,1,4,2]
brickwall_03c           L8 RGB8 RGB8 L8 L8 L8 L8 L8            [1,3,3,1,1,1,1,1]
```

**The size in MiB is the bytes-per-pixel.** Resolution never varies; only the format does.
This is why segment sizes came out as whole megabytes earlier, and why
`BricksSubstance004` is exactly 11 MiB — it is eleven bytes-per-pixel worth of
1024-square rasters.

**Boundaries are therefore fully determined by the format sequence**, and the segment size
gives a hard constraint: the bytes-per-pixel of all resources must sum to the segment size
in MiB.

## There are two file layouts, and one is a v2 legacy

The difference is **where the record directory sits**, and nothing else. Checking whether
each directory entry points before or after the directory itself separates 360 distinct
specimens absolutely — no file mixes the two:

```
layout A   [ resources ][ directory ][ records + bytecode ][ value table ]     333  (92%)
layout B   [ records + bytecode ][ directory ][ value table ]                   27   (8%)
```

The body is identical in both: records with each one's bytecode interleaved after it. Only
the directory moves, from before the body to after it. In `serverhouse__Road_01` all 794
records precede the directory; in every layout-A file all records follow it.

### Layout B is version 2 only

```
v2   n=76    A=49   B=27          v5   n=191   A=191  B=0
v3   n=5     A=5    B=0           v6   n=27    A=27   B=0
v4   n=36    A=36   B=0           v8   n=6     A=6    B=0
                                  v9   n=19    A=19   B=0
```

Every layout-B file is version 2, and 36% of version 2 files use it. It had disappeared by
version 3. The 27 are `serverhouse__*` materials (19), Substance Designer's animated demo
graphs (7), and `Simulator__Grid`.

### Verified: the layout-B region is the record body

Measuring how much of the pre-directory region the records span, across all 27 layout-B
specimens:

```
region                    1,020,760 bytes
spanned by records        1,020,064 bytes   (99.9%)
```

Twenty of the twenty-seven come out at exactly 100%; the shortfall elsewhere is a 20-32
byte tail. This is the same completeness test applied to resource segments, and it gives
the same answer: the region is fully accounted for once it is read as the right thing.

An earlier attempt measured only *bytecode* coverage of this region and got 14.5%, which
looked like 85% unexplained. That was the wrong denominator — bytecode is a small fraction
of the body in both layouts (2% in the layout-A specimen measured earlier), because record
bodies are much larger than the little parameter programs attached to them.

### The layout-B preamble


Two things sit between `0x38` and the first record, and they are not the same kind of
thing.

**Most of it is bytecode belonging to later records.** Every layout-B file has record
bytecode pointers landing inside this region — between 4 and 130 of them per file, 130 in
`serverhouse__concrete_049`. So the region is not a header: it is the start of the body,
which simply begins with bytecode blocks rather than with a record. The interleaved
`[record][bytecode]` pattern holds; it is the phase that differs, not the structure.

**A short linked list heads it.** At `0x38` sit `[u32 tag][u32 offset]` pairs with tag
always `00020008`, and the count varies across the 27 layout-B files:

```
5 entries  x15      3 entries  x3      1 entry   x1
0 entries  x10      4 entries  x1
```

Entry *k* holds `8k + 12`, which relative to `0x38` is the address of **entry k+1's own
offset field**, so the entries chain forward. The final entry's offset leaves the list, to
60, 84, 92, 360 or 484 depending on the file, and lands — read with the usual +52 skew —
on a `[u32 tag][u32][u32]` triple whose tag low byte is `0x08` in every case examined.
`0x08` is the `fxmaps` filter id, and these files are dense in fxmaps records (44 in
`BrickWall_02`, 39 in `Road_01`).

**What the list is not.** Not instructions: `0x0008` has no entry in the length table, so
the region cannot be decoded. Not records of the main family: read as a record header the
class word would be `0x0002`, and bit 3 is set in 100% of real records. Its purpose is
open, but it is now bounded — a small forward-chained structure at the very start of the
body, whose exit points at something tagged with the fxmaps filter id.

**Bytes `0x60`-`0x7F`: bytecode.** This part decodes: `0900` with the f32 `1.0`, then
`0532`, and it ends at `0x78` with `0A02` — the int input-reference opcode — whose `u32`
immediate is the word at `0x7C`.

That word is the only thing that varies between files, and it resolves cleanly:

```
the u32 at 0x7C is a graph INPUT uid in 15 of 15 files
```

`0x1354A87D` in `Desert_Sand_01`, `0xEE7CAA31` in `roofing_007`, and so on, each matching
an input uid declared in that file's own manifest. So the preamble ends with a reference
to one of the graph's inputs, which is why it is the single per-file difference in an
otherwise constant block.

The list's purpose remains unexplained, but the claim that the corpus cannot help was
wrong. It was made after looking only at the 15 files with a 72-byte preamble, where the
bytes are identical; the other 12 layout-B files vary in both entry count and final
offset, and were already in hand. The lesson is the one this project keeps re-learning:
"the evidence is invariant" is a claim about the sample examined, not about the corpus,
and is worth re-testing on the widest stratum before it is recorded as terminal.

### The `00020008` structure is a body element, not a preamble header

Treating the linked list as something specific to the layout-B preamble was wrong. The
tag occurs **throughout the body** — 104 times in `serverhouse__BrickWall_02`, 68 in
`Road_01` — and in **248 of 352 layout-A files**, which have no preamble at all. What sits
at `0x38` in some layout-B files is the first few of these, not a distinct structure.

That also explains why the entry count at `0x38` (0, 1, 3, 4 or 5) resisted explanation
from the sources: it is not a property of the file, only of how many of these elements
happen to land at the start of the body before the first record. `serverhouse__concrete_049`
has zero at `0x38` and 56 in total.

**What it tracks.** Raw counts correlate with everything (0.72 to 0.98) because everything
scales with graph size — `dir_count` itself correlates 0.902. Comparing *tags per record*
against each filter's *share* of records removes that:

| filter share | correlation |
|---|---:|
| **fxmaps** | **0.534** |
| blur | 0.302 |
| gradient | 0.296 |
| warp | 0.284 |
| uniform | -0.254 |
| everything else | \|r\| < 0.19 |

over 311 specimens with at least 20 recognised records. Density is low — median 0.06 tags
per record, maximum 0.42 — and the corpus totals 38,551 tags against 28,787 fxmaps records,
a ratio of 1.34.

So the element is associated with FX-Maps more than with any other filter, consistent with
it being part of how FX-Map internal data is stored, but 0.534 is a tendency and not an
identification. It is not the FX-Map node tree itself, which was already ruled out on size.

### What the `00020008` element is, structurally

Examined in `RoadSubstance002`, a layout-A file with 3,974 of them among 39,627 records,
the tag is one member of an array of `[u32 tag][u32 pointer]` pairs:

```
0x06D37D8:  05440001  0000000C
0x06D37E0:  00020008  006D37B4      <- pair
0x06D37E8:  00020008  006D37BC      <- pair
0x06D37F0:  124A0648  006D37C8      <- pair, different tag
```

Established about it:

* **Every pointer is valid** under the usual +52 skew — 3,974 of 3,974.
* **It is never a record.** 0 of 3,974 occurrences coincide with a record start, and
  records almost never point at one (499 of 356,643 record slots).
* **The pointers land inside record bodies**, 73% of them, at 4-byte-aligned offsets that
  are *slot positions*: 28, 36, 44, 52, 60 are the commonest, i.e. slots 7, 9, 11, 13, 15.
  The remaining 27% land before any record.
* **Pointers run backwards**, to targets a few bytes apart — consecutive entries reference
  addresses 8 to 12 bytes apart.
* The tag varies across entries; `00020008` is one value among several including
  `00420008` and `124A0648`.

So it is a cross-reference array: entries binding something to a particular slot of a
particular record.

**Refuted: it is not the driven-parameter binding.** Class-word bit 0 is documented as
marking records with driven parameters, which made "these entries bind the drivers" the
obvious reading. Over 135,222 records:

```
P(targeted by an entry | class bit 0 set)   = 2.3%
P(targeted by an entry | class bit 0 clear) = 1.7%
```

No relationship. Whatever the entries bind, it is not what bit 0 marks.

The structure is therefore well described and its purpose is open. It is associated with
`fxmaps` above other filters (0.534 after controlling for size) and points at record slots,
which is a much narrower target than when this started, but not an identification.

### The arrays are an `fxmaps` structure inside record bodies

An earlier version of this section counted every position where a word equals its own
address minus 48, and chained adjacent ones into "runs". That massively overcounts: a
*single* such position is just a record slot holding a pointer to the field 8 bytes ahead,
which is common, and the word before it is ordinary slot data rather than a tag. Of 37,359
"runs" found that way, 36,096 were length 1 — and their "tags" were values like
`40000000` and `3E800000`, which are the floats 2.0 and 0.25.

Restricting to genuine multi-entry runs changes the picture completely:

| filter | records | multi-entry runs | per record |
|---|---:|---:|---:|
| **`fxmaps`** | 3,238 | **1,255** | 0.388 |
| `transformation` | 16,359 | 3 | 0.000 |
| `blend` | 22,474 | 2 | 0.000 |
| `levels`, `gradient`, `uniform` | 9,319 | 3 | 0.000 |
| `pixelprocessor`, `bitmap`, `shuffle`, `normal`, `warp`, `blur`, `distance` | 8,426 | **0** | — |

**1,255 of 1,263 multi-entry runs — 99.4% — are in `fxmaps` records.** The claim that
`pixelprocessor` carries exactly one per record was entirely the length-1 artifact; it has
none.

The association with class-word bit 7 is correspondingly sharper than reported before:

```
P(record contains a multi-entry run | bit 7 set)   = 13.1%   (1,254 / 9,540)
P(record contains a multi-entry run | bit 7 clear) =  0.0%   (9 / 57,572)
```

Nine exceptions in 57,572. So the structure occurs **only** in records that carry a
function graph, and within those, only in `fxmaps` ones — about two fifths of them.

Runs are 2 to 8 entries. The tag vocabulary over the 4,270 entries in genuine runs:

| tag | share |
|---|---:|
| `00020008` | 90.8% |
| `00100048` | 4.0% |
| `00500E48`, `00500248` | 0.7% each |
| others | < 0.5% each |

Given `fxmaps` averages 2.69 arrays per record only when length-1 noise is included, and
0.388 genuine ones, and that FX-Map trees in the sources average far more nodes than that,
the arrays are not a node-per-entry encoding of the tree. What they are remains open.

### The real structure: a tagged variable-length chain

Dumping a complete `fxmaps` record shows what the fixed-8-byte reading was missing. In
`Hard-Science-Old__flowingLava_v35`, record `0x399D4C`:

```
slot 0   03996608     tag: type 0x6608 (fxmaps, 1024x1024), class 0x0399
slot 1   00000015     slot-1 flags
slot 2-4 pointers
slot 5-7 3F800000 3F28F5C3 3EE147AE      floats 1.0, 0.66, 0.44
slot 8   00020008  |  slot 9  00399D40   entry, next = +8
slot 10  00020008  |  slot 11 00399D48   entry, next = +8
slot 12  00020008  |  slot 13 00399D50   entry, next = +8
slot 14  124A0648  |  slot 15 00399D5C   entry, next = +12
...
slot 22  09000005 3E800000 00000532 ...  bytecode: const 0.25, rand
```

The chain does not stop at the `00020008` entries. Slot 14 carries a different tag and its
pointer advances **12** bytes rather than 8. These are variable-length entries in a forward
chain, and a filter that only accepts `+8` sees a fragment of it.

**The tag determines the entry's size.** Following chains with arbitrary forward steps,
over 118,726 entries in 60 specimens:

| tag | n | size | modal share |
|---|---:|---:|---:|
| `00020008` | 5,841 | 8 B | 100% |
| `00420008` | 5,368 | 12 B | 100% |
| `0000018B` | 3,473 | 12 B | 100% |
| `00000089` | 2,894 | 16 B | 99% |
| `00000294` | 1,048 | 48 B | 99% |
| `14520248`, `11520248`, `13520248` | 2,184 | 12 B | 100% |
| `00000291` / `00000295` | 916 | 48 / 52 B | 97% / 98% |

Sizes run 8 to 64 bytes in multiples of 4, with 8 B (41%) and 12 B (28%) commonest. Chains
are short — 8,952 of length 2, tailing off to a handful of length 12.

**The determinism separates signal from artifact on its own.** Of 682 tags with 20 or more
occurrences, 131 have a single size accounting for 95% or more of them, and those cover 59%
of all entries. The rest are not tags at all: `40000000` is the float 2.0 and `BF800000` is
-1.0, both admitted by a permissive scan, and small integers like `00000004` and `0000000B`
sit at 53-66% modal. A real tag fixes its entry size; a float that happens to precede a
plausible pointer does not.

So the structure is a **tagged, forward-linked, variable-length entry chain** embedded in
record bodies. That is a considerably better description than the "fixed 8-byte array" it
replaces, and it explains why the earlier tag vocabulary looked like one value at 90% —
that was just the commonest of several entry kinds, isolated by a filter that rejected the
others by construction.

## The chain entries are per-node system-parameter blocks

The 48- and 52-byte entries hold four programs each, and the programs identify themselves
by the graph inputs they read. Resolving every `inputref` immediate against the manifest's
input identifiers, across the whole corpus:

```
word 2  ->  $randomseed     12,050 references   100%
word 3  ->  $outputsize     11,920 of 12,109     98%
                            (the remaining 2% are user parameters named
                             scale, tiling_scale, pattern_scale, ...)
```

`$randomseed` and `$outputsize` are Substance's per-node system variables. So the entry is
a **parameter block**: a fixed set of slots, each holding the compiled program that
computes one system parameter for that node.

That also explains the characteristic program sizes noted earlier. The word-2 program
(`$randomseed`) is about 3 instructions — a seed is combined, not computed. The word-3
program (`$outputsize`) is about 68, because deriving a node's output geometry from the
graph's size parameter is real work. Decoding one confirms it:

```
v0   i2 inputref  #2147019363        <- $outputsize
v1   f2 conv      (v0)
v2   f  swizzle   (v1, v0)
v3   f  swizzle   (v1, v1)
v4   f  sub       (v2, v3)           <- log2 width - log2 height
v9   f  exp2      (v8)               <- 2^-|difference|  = the aspect ratio
v10  f2 vec       (v9, v9)
v14  f2 mul       (v12, v13)         <- x 0.5
v16  f4 vec       (v15, v14)         <- assembled into a 4-vector
```

It reads the output size, takes the difference of its log2 width and height, exponentiates
to recover the aspect ratio, and assembles a 4-component vector — a transform matrix
derived from the node's resolution. The two 1-instruction programs at words 6 and 7 are
constants.

### This ties three open threads together

* **The resolution field.** The type high byte is `(log2 height << 4) | log2 width`, and
  the `$outputsize` program consumes exactly that pair of log2 values.
* **Slot-1 bit 3**, established as "output resolution is specified rather than inherited",
  is the flag for whether this parameter is overridden.
* **Slot-1 bit 2**, whose only prior evidence was a weak `.sbs` correlation with nodes
  declaring `outputsize` (r = +0.81, n = 12) and a strong association with records that
  carry one of these chains (53.3% against 18.0%, n = 28,784), now has a mechanism
  connecting the two: the chain entry is where a node's `$outputsize` program lives, so a
  bit marking `outputsize` handling and a bit predicting the chain's presence are
  plausibly the same fact, observed from two directions.

The identification does not name bit 2 outright, and the 2% of word-3 programs that read a
user parameter instead of `$outputsize` show the slot is not rigidly typed. But the
structure itself is no longer unknown: it is the per-node system-parameter block, and its
slots are addressable by name.

### Entries are typed objects holding programs

With tag-to-size known, each entry's payload words can be read. They are consistently
typed per tag:

```
00420008 (12 B)   word 2: pointer            100%
0000018B (12 B)   word 2: pointer            100%
00000089 (16 B)   word 2: zero 98%           word 3: pointer 100%
14520248 (12 B)   word 2: pointer            100%
00000294 (48 B)   w2,w3: pointers   w4: float/zero   w5: float
                  w6,w7: pointers   w9: zero         w11: small int
```

**The payload pointers point at bytecode.** For the three largest fixed-size tags, every
pointer resolves to a valid length-prefixed block:

| tag | word | blocks | not | rate | median instructions |
|---|---|---:|---:|---:|---:|
| `00000294` | 2 | 769 | 0 | 100% | 3 |
| `00000294` | 3 | 769 | 0 | 100% | **68** |
| `00000294` | 6, 7 | 1,538 | 0 | 100% | 1 |
| `00000295` | 2, 3, 7, 8 | 1,332 | 0 | 100% | 3, 68, 1, 1 |
| `00000291` | 2, 3, 6, 7 | 1,284 | 0 | 100% | 3, 68, 1, 1 |

Against a measured null: at random 4-aligned positions in the body the same block test
passes **15.4%** of the time (2,388 of 15,500). A run of 769 consecutive hits against that
baseline is not chance.

So a `00000294` entry is a 48-byte object carrying **four separate programs** with
characteristic sizes — one of about 3 instructions, one of about 68, and two of exactly 1 —
plus two floats and an index. An object that holds several small programs of stable sizes
is a parameter block: a fixed set of properties, each either a constant or a driving
function.

**The FX-Map tree, re-tested.** The earlier refutation counted only 8-byte entries in
strict `+8` chains, which was the wrong count. Recounting with all 140 fixed-size tags
lifts the correlation with `<paramsGraphNode>` counts from -0.19 to **+0.386** across 34
paired files. That is no longer evidence against, but it is not identification either: the
counts still disagree badly where inlining is heavy (`ie_pcloud`, 41 nodes against 424
entries), and agree only where it is light (`ie_curve`, 90 against 82).

### What separates the `fxmaps` records that carry an array

About two fifths of `fxmaps` records contain a multi-entry run. Comparing the two groups
within the filter — which removes the size confound entirely, since every record here is
the same kind of node — one field stands out:

| field | with a run | without | difference |
|---|---:|---:|---:|
| **slot-1 bit 2** | **79%** | **39%** | **+40** |
| slot-1 bit 4 | 77% | 59% | +18 |
| slot-1 bit 0 | 35% | 23% | +12 |
| class bits 8, 9 | 100% | 93-94% | +6, +7 |
| class bit 0 | 90% | 83% | +7 |
| class bits 3, 4, 7 | 100% | 98-100% | 0 to +1 |

Everything except slot-1 bit 2 moves by 18 points or less. Bytecode length is identical
between the groups — median 395 instructions, maximum 19,904, in both — so it is not about
the size of the attached program.

Over the whole corpus:

```
fxmaps records, n = 28,784
   P(has a run | slot-1 bit 2 set)   = 53.3%   (8,967 / 16,812)
   P(has a run | slot-1 bit 2 clear) = 18.0%   (2,151 / 11,972)

all records, n = 651,702
   2.3%   vs   0.9%
```

A threefold difference within `fxmaps`, and the effect is specific to that filter — across
all records the same comparison is 2.3% against 0.9%, which is just the `fxmaps` signal
diluted.

**This is the second association for slot-1 bit 2.** The first was with a node declaring
`outputsize` in its `.sbs` source: r = +0.81, but over 12 specimens and unable to survive
correction for the 63 comparisons scanned. This one rests on 28,784 records within a single
filter. The two are not obviously the same thing, and neither identifies the bit — but a
field that predicts both an `outputsize` declaration and the presence of this array is a
better-constrained target than it was.

### Not the FX-Map tree, and not a layout artifact

Two candidate explanations tested and eliminated.

**Not the FX-Map node tree.** The `.sbs` sources give each FX-Map's tree explicitly as
`<paramsGraphNode>` entries of type `paramset`, `addnode` or `markov2`. Across 33 paired
files containing trees, run count correlates with none of them:

```
paramset   -0.036      addnode   -0.277      markov2   -0.207      all nodes   -0.193
```

The counterexamples are stark: `ie_curve` has 90 tree nodes and **zero** runs, while
`serverhouse__Pavement_Path` has 12 nodes and 14 runs. Whatever the arrays encode, it is
not the tree's nodes.

**Not a version-2 legacy.** The paired files that showed runs were mostly layout B, which
raised the possibility that this is another v2-only arrangement. It is not — the rate per
`fxmaps` record is essentially the same in both:

| layout | files | fxmaps records | runs | runs per record |
|---|---:|---:|---:|---:|
| A | 336 | 28,377 | 11,114 | 0.392 |
| B | 27 | 407 | 130 | 0.319 |

`ie_curve`'s zero is about how few `fxmaps` *records* it has, not its layout or its
source tree.

**What holds.** Over 363 specimens: 28,784 `fxmaps` records carry 11,244 multi-entry runs,
**0.391 per record**, and 266 of the 303 specimens that have any `fxmaps` records have at
least one run. The association is established by containment — 99.4% of runs sit inside
`fxmaps` records and none at all inside `pixelprocessor`, `blur`, `warp`, `shuffle`,
`normal`, `distance` or `bitmap` records — rather than by correlation, which is worthless
here: run count correlates +0.982 with `fxmaps` record count but also +0.941 with `blur`
and +0.915 with `gradient`, because every count scales with graph size.

### The array entries, and where the phantom opcodes came from

The second word of each entry is not a pointer to a sibling. Under the usual +52 skew it
resolves to the entry's own end — `target == p + 8` in 2,893 of 3,974 cases in
`RoadSubstance002` — so the field stores its own address minus 48. Self-referential, and
not coincidence: 24,617 positions in that file satisfy it, against roughly 0.001 expected
by chance for a 32-bit match.

Entries appear in short runs, 2 to 8 long and most often 2 or 3. The tag vocabulary is 68
values over 5,825 entries in 39 of 60 files, overwhelmingly one of them:

| tag | share |
|---|---:|
| `00020008` | 90.7% |
| `00100048` | 4.3% |
| `00500E48`, `00500248` | 0.5% each |
| 64 others | < 0.5% each |

**This is where the five phantom opcodes came from.** Each is a 16-bit half of one of
these tags, read as an instruction by a decoder scanning the region linearly:

```
0448   405 occurrences as a tag half     (e.g. tag 12400448)
0A48    72
0B19     3
0A3D     2
1EB8     1
```

out of 56,470 entries examined. The account given earlier — that they are record headers
and slot values misread as code — was right in kind and wrong in detail: they are halves
of *these* array tags. Every one of the five is now accounted for by a structure that
exists, rather than by "decode residue" in general.

The structure's purpose is still open. What is now established is that it is a real,
corpus-wide array of 8-byte self-describing entries, dominated by a single tag,
concentrated near `fxmaps` records, pointing at record slots, and unrelated to class-word
bit 0.

### FX-Map trees: hypothesis tested, and what it did establish

The linked list's exit points at a structure tagged with the `fxmaps` filter id, and
these files are dense in fxmaps records, which suggested the list might be an FX-Map's
internal node tree — the one graph structure in Substance that is not a pixel-graph node,
and so the natural candidate for a record family that does not obey the class-word
invariant.

**Refuted on size.** FX-Map trees are `<paramsGraphNodes>` in the `.sbs`, with node types
`paramset` (397 corpus-wide), `addnode` (313) and `markov2` (40). `ie_curve` has 90 of
them, `ie_pcloud` 41. The linked list has between 0 and 5 entries. It is short by an order
of magnitude and cannot be the tree.

**The class-word invariant survives a direct test.** Across all 36 paired specimens
containing FX-Maps, the number of directory-enumerated records whose class word lacks bit
3 is **zero**. Bit 3 is set in every record without exception, which independently confirms
that the `00020008` list entries are not records — they are not in the directory, and they
would violate the invariant if they were.

**FX-Map tree nodes do relate to fxmaps records.** Counting both across the 36 paired
files gives r = 0.744. The instance-free subset reaches 0.983 but has n = 6 and is nearly
degenerate — three of its files sit at (22, 3), (21, 3), (19, 3) — so it adds little. The
honest reading is a moderate relationship over 36 files, consistent with FX-Map tree nodes
compiling into records of the fxmaps type, and not established beyond that.

### Every layout-B specimen is paired

All 27 layout-B files have a `.sbs` source in the corpus — the `serverhouse__*` materials
and Substance Designer's animated demos both shipped with sources. The layout that is
least understood is the one group with complete ground truth, which was not noticed
because layout B was identified from binaries and the pairing was never checked.

This is the corpus's best remaining asset for the open questions here. It does not help
with the slot-1 parameter work, which needs *flat* graphs and these are not, but for the
linked list, the preamble, and layout B's structure generally, every specimen can be read
against its source.

### `dir_at - 0x38` is the resource segment only in layout A

This is the assumption that made layout B look strange, and it is baked into
`standalone_parse`. In layout A the region before the directory is the resource segment,
so its size is `dir_at - 0x38`. **In layout B that same region is the record body**, and
the file has no resource segment at all.

Every anomaly attached to these files follows from that one mistake:

* **"Specimens with a segment but no resource descriptors."** 26 of the 27 have no
  descriptors because they have no resources. The region being scanned for descriptors
  was the record array.
* **The phantom operations `0403` and `153F`.** `code_region.py` computes the code span as
  starting after the directory, which in layout B is the value table, and its notion of
  the pre-directory region as resources means the real body is never decoded properly.
  `153F`'s invariant operand tuple `(1033, 768, 5376, 265, 1280)` is a fixed pattern of
  record header fields — identical across files because record headers are.
* **A "196,608-byte resource" in `NightSkyHDRISubstance001`-style files** and the other
  odd sizes that would not factor as `w x h x bpp`.

### Consequence for a reader

Determine the layout first, from a single test: read the first directory entry and compare
`entry + 52` against the directory offset. If it points backwards the file is layout B and
has no resource segment; if forwards it is layout A and the resource segment is everything
from `0x38` to the directory.

After that the same code serves both: walk the directory, and for each record follow its
filter's bytecode slot. That route never needs to know the layout, which is why the
record-walk decoder gave correct results on layout-B files while the span-based decoder
did not.

## The node segment and the code segment are the same region

They have been described throughout as two things. They are one — the body is records with
each one's bytecode interleaved after it, in both layouts. See "There are two file layouts"
above: layout B moves the directory after this body, but does not change its structure. The region between the
record directory and the value table holds records and bytecode **interleaved**, in the
pattern

```
[ record ][ its bytecode ][ record ][ its bytecode ] ...
```

Measured over 90 specimens, **93.1%** of adjacent items change kind — a record is
followed by its own bytecode, which is followed by the next record. In `ie_pcloud` the
alternation runs at 97% over 597 transitions.

### Every node owns a small program

Each record points to its bytecode through a slot carrying the universal +52 skew, and
the slot is per-filter, like the edge slots:

| filter | bytecode slot | | filter | bytecode slot |
|---|---|---|---|---|
| `blend` | 4 | | `uniform` | 1 |
| `levels` | 3 | | `blur` | 2 |
| `transformation` | 3 | | `shuffle` | 2 / 4 |
| `fxmaps` | 3 | | `gradient` | 4 |
| `pixelprocessor` | 3 | | `distance` | 4 |
| `warp` | 3 | | `bitmap` | 2 / 5 |

This is not a property of the two function-carrying filters. **Almost every node has
one**: `warp` 100%, `uniform` 98%, `blend` 96%, `levels` 95%, `transformation` 88%,
`blur` 72%. Over 342,004 pointers the block length has median **5 instructions** and
maximum 3,442.

That distribution is the point. A five-instruction program is not a shader — it is the
expression that computes one node's *parameter*, the compiled form of a value the artist
drove with a formula rather than a constant. The long tail belongs to `fxmaps` and
`pixelprocessor`, whose bytecode really is the filter's own function graph, and which is
what class-word bit 7 distinguishes: not "carries bytecode", which is nearly universal,
but "carries a function graph rather than a parameter expression".

### Blocks are occasionally shared

Of 285,064 distinct bytecode blocks, 95.3% are pointed at by exactly one record. The
remainder are shared: 12,909 by two records, 404 by three or more. The compiler's common
subexpression elimination therefore operates **across nodes**, not only within a single
function — two nodes that drive a parameter with the same expression share one compiled
block.

### Consequence for a reader

There is no "code segment" to locate. A reader walks the record directory, and for each
record follows its filter's bytecode slot. The instruction stream has no independent
existence: every valid block is reachable from some record, which is why treating the
region as a flat run of instructions produced the decode noise catalogued under "The last
five" — those artefacts are record headers and slot values read as opcodes.

## The record type's high byte is the output resolution

The record tag is `[NN u16][type u16]`, and the low byte of `type` is
`2 x filter_id + is_colour`. The high byte is a separate field, and it is the node's
**output resolution**, packed as two log2 nibbles:

```
high byte = (log2 height << 4) | log2 width
```

`0x88` is 256x256, `0xAA` is 1024x1024, `0xC9` is 4096x512.

### Evidence

Resource records let this be checked against truth. For JPEG resources both dimensions
are known exactly from the image's own SOF header:

```
JPEG records (true width AND height known) : 46/46 = 100%
raw records  (only pixel count checkable)  : 458/532 = 86%
```

verified across four distinct geometries — 1024x512 (x6), 1024x1024 (x7), 4096x512
(x20), 2048x2048 (x13). The **non-square** ones are what settle the nibble order, and
they all agree; reading the nibbles the other way round scores 82% overall and fails
every non-square case. The raw-record shortfall is in the pixel count derived from
consecutive descriptor offsets, not in the field.

### What this explains

* **Why the byte is almost always a doubled nibble.** `0x88`, `0x44`, `0x77`, `0x66`,
  `0x55`, `0x99`, `0xBB`, `0xAA`, `0xCC`, `0x22` are 99% of observed values: square
  images. The ~1% exceptions like `0x86` are the non-square nodes.
* **Why `0x88` dominates at 56.8%.** 256x256 is Substance's default preview size — the
  same default that appears as `width="256"` in the manifests.
* **Why the earlier search for a log2 dimension pair found nothing.** It looked for
  `(12, 9)` as adjacent `u32`s or an adjacent byte pair. The pair is packed into a
  single byte as two nibbles, so neither pattern could match.
* **`0xAA` was never a marker, twice over.** It is `log2 1024, log2 1024` — the
  resolution of a 1024-square resource. The check that hard-coded it as a table marker
  was really filtering for resources that happened to be 1024 square.

Every record carries this, not just resource descriptors: 737,955 records across the
corpus have a decodable filter and therefore a readable output resolution. A reader can
now state each node's output geometry directly from its tag.

## Resource descriptors are ordinary records, and NN carries the format

The statistical stride classifier was solving a problem the format does not pose. Every
embedded resource is described by a record that states its format outright. The reason
this looked absent is a bug in my own scanner.

### The descriptor

```
[ u32 tag ][ u32 offset - 52 ]
```

read under the normal record framing, `tag = NN << 16 | type`:

| field | bytes (LE) | meaning |
|---|---|---|
| `NN` high | byte[3] | pixel format: 1 L8, 2 RGB8, 3 RGBA8, 5 L16, 7 RGBA16, **8 JPEG** |
| `NN` low  | byte[2] | bit depth: `0x08` 8-bit, `0x18` 16-bit |
| `type` high | byte[1] | part of the filter id |
| `type` low  | byte[0] | `0x20` grayscale, `0x21` colour |

The offset carries the universal +52 skew, like every other pointer in the format.

### The scanner bug: 0xAA was never a marker

`valid_tag` required byte[1] == `0xAA`, read as a constant marker that made the table
findable. It is not a marker — it is the **upper byte of the record type**, i.e. part of
the filter id. Different resource-producing filters therefore have different values
there, and the check silently discarded every resource that did not come from one
particular filter. Observed across the corpus: `0xAA` (236), `0x99` (68), `0x4A` (65),
`0x88` (41), `0xBB` (39), `0x9C` (28), and a dozen more.

Dropping that one constraint and keeping the checks that are real — format code, depth,
grayscale/colour flag, offset within the segment:

```
specimens with resource descriptors     41  ->  100  (of 117 with a segment)
segments tiled exactly, formats valid          68
```

Format and depth agree in 564 of 565 descriptors (L16 and RGBA16 always `0x18`; L8,
RGB8, RGBA8 and JPEG always `0x08`), which is what confirms these are real records
rather than coincidences admitted by a looser filter.

### The resource segment, solved

Descriptors are records, so they are enumerated by the record directory and need not be
searched for at all. Walking the directory, keeping entries whose tag decodes as a
resource descriptor, and taking each resource's size from the next descriptor's offset:

```
specimens with a segment              117
   have resource descriptors          106
   descriptors tile the segment EXACTLY  106      (100% of those that have them)
   size divisible by the format's bpp    483/483  (zero exceptions)
```

Every resource segment in the corpus is now fully accounted for: start, length, pixel
format, bit depth and grayscale/colour, all read from the file rather than inferred.

Two of my own checks had to be removed to get here, both of which encoded assumptions
the format does not make:

* **the `0xAA` marker** (see above) — actually part of the filter id
* **"pixel count is a power of two"** — true for 467 of 483 records but not required;
  the 16 exceptions are ordinary non-power-of-two images, and treating them as
  malformed hid 11 specimens whose descriptors were correct all along

A third was a plain bug: descriptor offsets map to file position as `offset + 52`, and
reading them as `0x38 + offset` mis-sized every compressed record.

### The eleven specimens with no resources

Seven distinct files (four are duplicates) have a pre-directory region but no resource
descriptors, and they are consistent: the region is not pixel data. The four
`serverhouse__*` packages open with `08 00 02 00 0c 00 00 00` — small integers, 43%
zero bytes — which is structured record data, not a raster. These packages simply bake
no bitmaps, and a reader that finds no descriptors should conclude there are no embedded
resources rather than attempt to segment the region.

### The statistical classifier is superseded

`seg2.py` — row-stride scoring, the constrained DP, the 5-way bpp choice — is no longer
needed for any specimen in the corpus. It reached 8/32 exact sequences and F1 0.571 at
its best. Reading the descriptors gives 106/106. It is kept only as the record of what
the content itself can and cannot support, which is a genuinely separate question and
the source of two well-measured negative results (the per-MiB stride bias and the
smallest-within-tolerance tie-break, both rejected on symmetric metrics).

### Format 8 is JPEG, and it explains the compressed records

`WoodFloorSubstance006` names its 20 compressed resources with tag `0x08089C2x`. Against
the component count read from each JPEG's own SOF header:

```
ncomp = 1 (grayscale) -> tag 0x08089C20   x10
ncomp = 3 (colour)    -> tag 0x08089C21   x9
```

Perfect agreement. So the earlier finding that 8-bit channels are JPEG-compressed while
16-bit channels are stored raw is not an inference from JPEG's limitations — the format
says so directly, with a distinct format code.

### NN is per-record-type payload

This partially retracts the conclusion that `NN` is opaque and a parser may ignore it.
That conclusion came from correlating `NN` against version, file size, flags, provenance
and checksums **across all records at once**, and it found nothing (|r| < 0.15). The
reason is now clear: `NN` has no single global meaning. It is a payload field whose
interpretation depends on the record type. For resource records it is exactly
`format << 8 | depth`.

The negative result stands as stated — there is no global interpretation — but the
stronger reading, that the field is inert, was wrong.

### Resources are cached outputs, one per graph output

Comparing resource-record count against the manifest's output count on tabled
specimens: equal in 30 of 41, and where they agree they agree exactly — 15 files at
(6,6), 7 at (7,7), 7 at (8,8). Resource count never matches the image-input count
(0/41). The eleven disagreements are all cases where the count is *lower* than the
output count (1 vs 7, 2 vs 5, 3 vs 5), which is the signature of `find_table` missing
records — the same scanner weakness that produced the 6 MiB and 9 MiB size outliers.

So the embedded resources are a **cache of the graph's own outputs**, one per output,
not input bitmaps. This also explains why the manifest declares no resources: there is
nothing to declare, the outputs are already listed.

### The manifest's declared output size is a default, not the resource resolution

Outputs carry `width` and `height` attributes, and it is tempting to read the resource
resolution from them. That is wrong. Checking `size == width * height * bpp` against
tabled ground truth holds for only 36 of 200 records, and all 164 failures are the
same discrepancy: **actual 1,048,576 px against declared 65,536 px** — a real 1024x1024
resource under a declared 256x256.

`width`/`height` are the default value of the parametric output size, which the engine
overrides at cook time. Across the corpus, tabled files declare 256x256 214 times and
1024x1024 49 times, yet their resources are 1024x1024 throughout. This *reinforces* the
1024-square rule rather than weakening it: the bytes say 1024 square even when the
manifest says 256.

### Table-less segments carry length-prefixed compressed blobs

Table-less segments have no resource table in any encoding. A format-agnostic search
for the offset column — an ascending u32 run starting at 4 and spanning the segment,
at strides 4/8/16/32, calibrated to recover the real table in 4 of 4 tabled files —
finds nothing table-shaped in any of the 76. Neither does a scan for the `0xAA` tag
marker: zero hits, in all 76.

They do not need one, because their records are self-delimiting:

```
[ u32 byte_length ][ blob ]          4-byte aligned, repeating
```

where the blob is a JPEG (`FF D8 FF E0 ... JFIF`). `BricksSubstance005` opens with
`d6 52 00 00 | ff d8 ff e0` — length 21,206, then the image. Walking the segment as
this record type tiles it **exactly, end to end**, in 4 of the 6 files that begin with
one, including a 20-blob segment. 9 of 76 table-less segments contain compressed blobs.

**Segments mix compressed and raw records.** The two files where the walk stalled
explain the general layout: after the first JPEG comes exactly 8,388,608 bytes — one
raw 1024x1024 RGBA16 — and then another `[u32 len][JPEG]`. So a reader must dispatch on
content at each record boundary: a length prefix followed by a known magic is a
compressed record; otherwise it is a raw raster.

### Compressed records are 8-bit channels; 16-bit channels are stored raw

The JPEG records carry their own dimensions in the SOF header, which gives table-less
resource resolutions directly. They are heterogeneous — 4096x512 (x20), 2048x2048
(x15), 1024x512 (x6), 1024x1024 (x4) — split 21 grayscale against 24 colour, matching
the grayscale/colour distinction the record tags already draw.

The raw records interleaved between them are explained by a limitation of the container
format: **JPEG cannot store more than 8 bits per channel**. So a graph's 8-bit outputs
are JPEG-compressed and its 16-bit outputs are written raw, in the same segment.

The 8,388,608-byte raw record in `Hard-Science-Old__ground_b` confirms it. A stride scan
over 64..16384 puts stride **4096** at a mean row delta of 50.6 against ~82 for every
other stride, including 8192 — a clear minimum, not a harmonic. 8,388,608 / 4096 = 2048
rows, so the record is 2048x2048 at 2 bytes per pixel: a 16-bit height map, at the same
resolution as the JPEG records beside it.

### A sampling bug that hid every 16-bit raster

`rowscore` sampled every fourth byte. For 16-bit little-endian pixels, byte offsets
0, 4, 8, ... are all *low* bytes, which are close to noise; the correlation lives in the
high bytes. The measure was therefore blind to L16 and RGBA16 — 55 of 193 records, 28%
of the corpus. On the known 2048x2048 L16 record above:

```
sampling every 4th byte : lag-4096  70.95   misaligned ref 69.42   ratio 1.022  (no signal)
sampling every byte     : lag-4096  35.74   misaligned ref 75.94   ratio 0.471  (strong)
```

Two measurements of the same bytes disagreeing is what surfaced this: the broad stride
scan called 4096 a clear winner while `rowscore` called it noise. Sampling every byte
instead, and re-validating the segmenter against the same 32-segment ground truth:

```
              exact     precision  recall   F1      resources (truth 221)
before         5/32       0.57      0.50    0.535      198
after          8/32       0.58      0.57    0.571      218
```

Exact recoveries rise by 60% and the proposed resource count lands within 1.4% of truth.

### Raw table-less resources are not all 1024-square

Predicted, and false: if raw records followed the tabled 1024-square rule, every
compressed-blob-free segment would be a whole number of MiB. Only 24 of 67 are (35%).
The remainders name the missing resolutions — `NightSkyHDRISubstance001` is 196,608
bytes, exactly 256x256x3 (RGB8 at 256 square), matching that file's declared output
size; others leave 524,288, 65,536 or 32,768 bytes over.

So the 1024-square rule is a property of **tabled** segments specifically, where it holds
without exception. Table-less segments mix resolutions, and their raw records need a
resolution recovered per record rather than assumed.

### The size rule holds without exception

Cross-tabulating every cleanly-read resource record in the corpus by its format tag
and its byte size:

| tag / depth | format | bpp | size | count |
|---|---|---:|---:|---:|
| `0x01` / 8  | L8      | 1 | 1 MiB | 81 |
| `0x05` / 24 | L16     | 2 | 2 MiB | 33 |
| `0x02` / 8  | RGB8    | 3 | 3 MiB | 38 |
| `0x03` / 8  | RGBA8   | 4 | 4 MiB | 18 |
| `0x07` / 24 | RGBA16  | 8 | 8 MiB | 22 |

192 of 193 interior records, **zero contradictions**: the format tag alone determines
the byte size. Three records fall outside the table (one 6 MiB and one 9 MiB tagged
RGB8, one 9 MiB tagged L16). Each is an exact multiple of what its own tag predicts —
6 = 2 x 3, 9 = 3 x 3 — and all three are the final record of their segment, which is
where `find_table` absorbs any record it failed to spot. They are scanner misses, not
format variety.

### Segmenting a table-less segment: a measured method

The rule reduces boundary finding to choosing a bpp per resource from a 5-element set,
constrained so the bpp values sum to the segment size in MiB. Since stride is constant
within a resource, a bpp-`b` resource spans `b` consecutive MiB that all read as stride
`1024*b`, so every interior MiB votes — which lets a smooth, texture-free resource
abstain (it scores flat across all candidates) instead of guessing.

`seg2.py` scores each MiB against each candidate stride — mean absolute row-to-row
delta, normalised against the same statistic at a deliberately misaligned lag — and
runs a DP over the partition. Against the 32 tabled segments as ground truth:

```
exact sequence recovered : 5/32
boundary precision       : 0.57
boundary recall          : 0.50
resources proposed       : 198   (truth 221)
```

Half the boundaries, at better-than-even precision, with the resource count calibrated
to within 10%. Scoring only each resource's *first* MiB instead of all of them scores
0/32 and 6% — the interior votes are what carry this.

**A bias toward smaller strides looks like a fix and is not.** L8 data correlates at
every multiple of 1024, so an L8 raster can masquerade as any larger bpp, and a
per-MiB penalty on `b` was the obvious correction. It raises boundary *recall* from
0.50 to 0.71 — and is worthless: it works by shredding resources into 1 MiB pieces,
proposing 495 where 221 exist. Precision falls 0.57 -> 0.29 and exact recoveries go
5/32 -> 0/32. Recall alone rewards proposing more cuts; F1 peaks at exactly zero bias.
Rejected.

So the harmonic ambiguity is *intrinsic*: an L8 resource and a same-sized run of one
larger-bpp resource are not distinguishable by row correlation, because the smaller
stride genuinely divides the larger. Breaking the remaining half needs a signal that is
not stride-based — per-channel byte statistics, or the record bytecode's declared
output formats.

### What still blocks a full segmentation

Applying the rule needs the format of each resource, and content statistics are not
accurate enough. Validated against the tabled ground truth, a greedy walk classifying each
resource and consuming `bpp` MiB gets the first 1 to 5 resources right and then drifts:

```
Metal_Vent_006     truth [3,3,3,3,3,3]      found [1,1,1,3,3,1,1,1]
st_wood_fine_20    truth [1,3,8,1,1,2,1]    found [1,3,1,1,1,1,1,1,1]
```

Row-stride autocorrelation fares no better — validated against the same ground truth it
identifies only 3 of 6 true boundaries, confusing the true 3072-byte stride with its 2x
and 4x harmonics.

So the position is: **the structure is now known and the search space is small** — a
sequence of per-resource bit depths summing to a known total — but recovering which
sequence needs a classifier that can tell L8 from RGB8 from a 64 KiB sample more reliably
than mean-absolute-difference at lag 1–4 can. That is a tractable signal-processing
problem, not a format unknown.

## Type 3 does not exist — resolved

The opcode's type field is two bits, and three values were identified: 0 bool, 1 float,
2 int. Type 3 was left open, with `0x0B19` (1,358 instructions across 108 specimens) as
the only candidate above the noise band. **It is decode noise. The field uses three of
its four values.**

### A frequency-independent noise discriminator

The ≥50-specimen threshold has now hidden real instructions three times (`0A10`, `0x2A`,
`0x1E`), so a test not based on frequency was needed. Real instructions are embedded in
long clean runs; mis-decoded tokens appear in short mis-started ones. Measuring the length
of the run each occurrence sits in:

| opcode | n | median run | max | in runs ≥50 | status |
|---|---:|---:|---:|---:|---|
| `085E` | 2,703 | **21,102** | 21,187 | 99.1% | `neq` |
| `0912` | 295,429 | 325 | 41,493 | 67.3% | `add`, confirmed |
| `0525` | 11,456 | 121 | 7,785 | 66.9% | `ceil`, confirmed |
| `0523` | 254,536 | 70 | 25,614 | 99.8% | `abs`, confirmed |
| `052A` | 3,285 | 23 | 7,785 | 18.7% | `exp`, confirmed |
| `0532` | 184,898 | 11 | 8,833 | 19.5% | `rand`, confirmed |
| `3EAA` | 3,081 | 4 | 131 | 33.8% | known noise |
| **`0B19`** | **14,230** | **2** | **134** | **6.7%** | **not an instruction — it is the class word of `8818` records; see "Record header layout"** |
| `3BDC` | 14 | 2 | 58 | 7.1% | known noise |

`0B19` sits with the known-noise population on every measure, and its maximum containing
run is 134 instructions where every confirmed opcode reaches into the thousands. Its
"instances" also repeat identical operand pairs — `(10, 0)` in unrelated files — and its
operands never resolve to a value defined in the same run.

The discriminator is reliable for common opcodes but weak for rare ones: `0A10` (integer
swizzle, confirmed by ground truth) shows a median of 5 and 31.2%, not cleanly separated.
Embedding depth answers "is this opcode real" for high-count candidates; rare ones still
need structural or ground-truth evidence.

### `0x1E` = `neq` — upgraded from predicted to confirmed

`085E` has the **deepest embedding of any opcode tested**, median containing run 21,102
and 99.1% in runs of 50 or more — further inside clean code than `add`. Combined with its
shape (bool result, two operands, sitting in the single hole of an otherwise contiguous
comparison block between `eq` and `gt`), this is no longer a structural guess.

It remains true that the `.sbs` language has no `neq` node, so `neq` cannot be authored
directly; it reaches the corpus through inlined library graphs, the same route as
`iswizzle1`.

### A failed test, recorded

The first attempt asked what fraction of an opcode's operands resolve to values defined
within the same run. It flagged `0523` (`abs`, confirmed 17/17 exact) and `052A` (`exp`,
confirmed 578/578 exact) as "not instructions", so it was discarded. The flaw:
`base_vn()` returns a *lower bound* on a run's starting value number, and most runs are
fragments of a longer stream, so operands legitimately reference values defined before the
run begins. The metric measures how self-contained a run is, not whether an opcode exists.

## `0x2A` = `exp`, and the specimen that unlocked five opcodes

### A bug in the code-region bounds

`code_spans()` took the instruction stream to be `[first directory entry, last directory
entry]`. That is wrong: the directory names **records**, and code continues past the final
one, up to the value table. For `ie_processing.sbsasm` the directory has only four
entries, the last at `0x820`, while the value table starts at `0xC114` — so **95.5% of the
file was being discarded**, 47,348 of 49,564 bytes.

The dropped region was unambiguously code: scanned under the length rule it yields 7,793
decodable opcodes against 8 non-opcode tokens.

Corrected to `[ents[0], table_start]`. **489 of 495 specimens were affected**, though the
total loss is 376,708 bytes — about 0.18% of the corpus, overwhelmingly concentrated in
this one file. Aggregate statistics barely move; the value of the fix is that it turned
`ie_processing` from useless into the best ground-truth specimen in the corpus.

### `ie_processing` decoded

9,569 live nodes, 8,094 instructions. **Eleven operations match exactly:**

| node | live | op-id | instructions |
|---|---|---|---|
| `add` | 994 | `0x12` | **994** |
| `and` | 595 | `0x1A` | **595** |
| `ifelse` | 585 | `0x09` | **585** |
| **`exp`** | **578** | **`0x2A`** | **578** |
| `div` | 337 | `0x15` | **337** |
| `sub` | 328 | `0x13` | **328** |
| `samplelum` | 326 | `0x33` | **326** |
| `lr` | 310 | `0x21` | **310** |
| `gt` | 306 | `0x1F` | **306** |
| `sqrt` | 17 | `0x28` | **17** |
| `ceil` | 17 | `0x25` | **17** |

`mul` is 2068 against 2067. This settles three things:

- **`0x2A` = `exp`** — 578/578, in the transcendental hole between `ln` and `exp2`,
  exactly as predicted. The earlier dataflow fingerprint fits: `exp` fed by `div` 100%
  and consumed by `mul` 86%, with the divisor a negative integer (`-1`, `-2`, `-3`, `-6`)
  and the consumer a self-multiply 97.1% of the time — `exp(-k/x)^2`, an attenuation
  kernel.
- **`0x33` = `samplelum`** — upgraded from probable to confirmed on 326/326.
- **`0x25` = `ceil`** — 17/17.

### The compiler performs common-subexpression elimination

Three nodes did *not* match: `neg` 1180 against 307, `vector2` 325 against 3, `dot` 289
against 1. Their combined shortfall of 1,483 is essentially the whole 1,475-instruction
deficit, and every node in the file is live, so dead-code elimination is not the cause.

The explanation is visible in the ratios. Graph 0 holds ~289 repeated structural units:
`neg` 1156/289 = **4.00**, `exp` 578/289 = **2.00**, `dot` 289/289 = **1.00**,
`mul` 2028/289 = 7.02. The compiler emits each *distinct* subexpression once. Where the
289 units feed a node identical inputs — as the `dot` does — all 289 collapse to one.
Where each has a distinct input, as `exp` does, all 578 survive.

This is a significant property of the format and it retrospectively explains several
puzzles: why the structure predicted by `ie_curve`'s `neg` graph could not be found, and
why counting evidence has been unreliable for exactly the nodes whose inputs repeat.

### `0x17` = `neg` — now confirmed, by elimination

In a file where eleven operations match exactly, after assigning `exp`, `ceil` and
`floor` the **only** unmapped node left is `neg` and the **only** unmapped op-id left is
`0x17`. The count gap (1180 vs 307) is CSE, the same effect that reduced `dot` 289-fold.

This supersedes the previous "probable, not proven" verdict. The three structural
objections recorded there are also explained: the predicted
`add(neg(get_float2), const_float2)` pattern is absent because CSE and reordering do not
preserve authored structure, and `0557`'s feeders differ for the same reason.

### `0x24` = `floor` — **[CONFIRMED, see the fract-idiom test above]**

`floor` is 1 in `ie_processing` and `0x24` is 1: exact, but on a single instance, and
`0x24` carries 112,662 instructions corpus-wide against only 122 authored `floor` nodes.
The scale mismatch is unexplained. Recorded as a weak hypothesis, not a result.

## What to investigate next — and four corrections

### The frequency threshold has now hidden real instructions three times

Re-checking every op-id the gap analysis called "absent from the corpus", without the
≥50-specimen filter:

| op-id | instructions | files | dominant form | verdict |
|---|---|---|---|---|
| `0x03` | 3,603 | 34 | `0603` int1, `0543` float2, `0503` float1 | **real** — a third variable-access variant |
| `0x1E` | 3,241 | 21 | `085E` bool, 2 operands (2,927) | **real** — the predicted `neq` |
| `0x2A` | 3,932 | 45 | `052A` float1 unary (3,733) | **real** — in the transcendental hole |
| `0x35` | 3,486 | 34 | `0535` float1 unary (3,258) | **real** — sits just past the samplers |
| `0x05` `0x06` `0x0A` `0x0B` `0x0E` `0x0F` `0x2C` `0x36`–`0x3F` | 97–393 | 14–24 | scattered | noise band |

The four real ones are an order of magnitude above the noise band in both instructions
and specimen count. Two consequences:

- **The `0x03` retraction was over-cautious.** It was withdrawn for resting on a single
  `05C3` instruction; in fact op-id `0x03` carries 3,603 instructions across 34 specimens
  with a coherent variable-access shape (int1, float2, float1). The original reading —
  a distinct kind of variable read — stands, though which kind is still unestablished.
- **`0x1E` = `neq` is not unreachable after all.** The gap analysis argued the corpus
  *structurally could not* contain it, because the `.sbs` language has no `neq` node.
  But `085E` occurs 2,927 times in 21 specimens with exactly the comparison-block shape
  (bool result, two operands). It must arrive through inlined library graphs, the same
  route by which `iswizzle1` and the trig candidates appear in files that never author
  them. The prediction was right; the claim about reachability was wrong.

### Next target: `0x2A`

`0x2A` is the highest-value next instruction, for four reasons:

1. **It occupies a predicted structural hole**, between `ln` (`0x29`) and `exp2` (`0x2B`):
   `28 sqrt · 29 ln · [2A] · 2B exp2 · [2C] · 2D atan2 · 2E cartesian · 2F lerp`
2. **Its shape fits** — unary, float1, with minor float3/int4 forms.
3. **Its dataflow is the most constrained of any unnamed op**: fed by `div` **100%** of
   the time and consumed by `mul` **86%**. For comparison, `ln` is consumed by `div` 85%
   (the `ln x / ln 2` idiom proven from sRGB) and `exp2` is fed by `sub` 74%. Nothing
   else unnamed has a fingerprint this tight.
4. **Its neighbours are known**, so it is boxed in: it sits inside the pow-lowering chain
   whose every other member has been identified.

A representative site reads:

```
0930  f1  min(...)
0900  f1  const = 1.594121
0915  f1  div(min_result, 1.594121)
0900  f1  const = -1
0915  f1  div(-1, previous)
052A  f1  ?2A(previous)          <<<
0914  f1  mul(result, result)
```

**`exp` is the leading hypothesis** — it is `ln`'s inverse, sits adjacent to it, and is
the language's third most-used unmapped node (2,312 uses). The obvious ground-truth test
is unavailable: only three specimens author `exp`, they are the same package
(`ie_processing`), and that package barely decodes — 9,569 nodes yielding 298
instructions, with `ln` and `exp2` both at zero. Confirming `0x2A` needs either a
different `exp`-using specimen or a semantic argument from the surrounding chain.

### Ranked alternatives

| rank | op-id | instructions | why |
|---|---|---|---|
| 2 | `0x1E` | 2,927 | predicted `neq`; shape already matches the comparison block, so confirmation is cheap |
| 3 | `0x24` | 112,662 in 353 files | the largest genuinely untouched op-id, with a full width family f1–f4 |
| 4 | `0x03` | 3,603 | third variable-access variant; would complete the `get` family |
| 5 | `0x35` | 3,258 | unary float1 immediately past the samplers |

`0x17` remains the largest unknown at 587,111 but is **not** the best next target: it has
already been attacked from five directions and the counting and structural evidence
disagree. It needs a new kind of specimen, not more of the same analysis.

## Opcode catalogue — the full corpus

`catalogue.py` decodes the corpus and produces `OPCODES.md`. **These figures are
superseded.** They were measured by flat-scanning the record region across a corpus counted
with duplicates: 493 specimens, 125 opcodes, 25.5 million instructions. Decoding by walking
records to their bytecode, over 382 distinct specimens, gives **62 operations, all named,
over 11.8 million instructions** — roughly half the earlier instruction count was record
data misread as code. See "Decoding correctly: walk records, do not scan" in `OPCODES.md`.
The section below is retained because its noise-separation reasoning still holds.

### Separating the ISA from decode noise

Decoding is exact once the length rule is known, but a run that *starts* at the wrong
offset reads operand tokens as opcodes and invents vocabulary. Raw decoding reports
25,758 distinct "opcodes", which is obviously not an instruction set. Three filters, in
increasing order of power:

1. **Long runs only** — a mis-started run rarely survives many instructions.
2. **Operand validity** — numbering is contiguous, so with the run's base value number
   recovered, instruction *i* holds value *S+i* and every operand must be `< S+i`.
   This cut 25,758 → 15,658.
3. **Presence across specimens** — a real opcode recurs. ≥50 of 493 specimens cuts to
   **125**, retaining 98.6% of decoded instructions.

The decisive evidence that the residue is noise and not rare instructions is
*distributional*. Random tokens read as opcodes should show no structure in the opcode
fields, and they don't:

| population | type field (0/1/2/3) | operand-token counts |
|---|---|---|
| catalogued | 11% / 65% / 23% / 1% | concentrated on 1–3 |
| excluded   | 16% / 28% / 31% / 24% | flat across 1–31 |

A uniform type field is exactly what misread operand tokens produce. The excluded
population is 0.3% of instructions.

**A trap I fell into here.** My first validity filter exempted *any* opcode with op-id
`0x00` from the operand check, on the reasoning that constants carry an immediate rather
than operands. That let through spurious long "constants" such as `0x5500` (21 operand
tokens), which then collided with `0x0900` in the family grid and displaced it. Only the
twelve confirmed constants deserve the exemption. The lesson is the same one as the
earlier length-inference failures: a filter justified by a *category* ("constants") rather
than by *specific verified members* will launder noise into the result.

### Shape of the instruction set

- **Type and width are orthogonal to operation.** `add` exists as `0912/0952/0992/09D2`
  (float, 1–4 components) and `0A12/0A52` (int). The same op-id appears across types and
  widths, so identifying an operation once identifies up to eight opcodes.
- **Float dominates**: 65% of catalogued opcodes are type 1.
- **Type 3 is decode residue, not a type.** See "Type 3 was never a type" below. The
  earlier reading of this bullet, that type 3 exists but is unidentified, rested on the
  superseded flat-scan count.
- **Booleans are first-class**: comparisons (`085A/085B/085D/085F/0860/0861/0862`) return
  type 0, consumed by `select`. There is a bool constant, `0440`.
- Of 45 distinct operations (in 68 type-specific forms), **43 are named**; see
  OPCODES.md. An earlier version of this bullet read "of 66 operations, 13 are
  semantically identified", which predates the naming work and double-counted
  type-specific forms as separate operations.

## The source-node type is wider than `bitmap`, and the descriptor table is not a table

The filter table above labelled `0x20`/`0x21` **bitmap** on the strength of three
specimens. That label is not wrong so much as too narrow, and finding the wider one also
collapsed a structure I had been treating as separate.

### Instance-free graphs are the only paired files where counting is valid

Comparing source node counts against binary record counts is normally useless: the
compiler inlines every `compInstance`, so one source node becomes an arbitrary number of
records. Across 96 paired non-library files the binary count exceeds the source count for
95-100% of files on nearly every filter — exactly what inlining predicts, and therefore
no evidence about which tag is which.

The exception is a graph with **no `compInstance` at all**. There inlining cannot happen,
and source nodes and records must correspond one-to-one. Nine paired files qualify:

| file | filters | inputs | outputs | records | tags |
|---|---|---|---|---|---|
| `Metal_Vent_006` | bitmap=6 | 0 | 6 | 6 | `0x20`=6 |
| `celtic_orna_mossy_001` | bitmap=6 | 0 | 6 | 6 | `0x20`=6 |
| `st_wood_fine_20` | bitmap=7, transformation=7 | 0 | 7 | 14 | `0x20`=7, `0x04`=7 |
| `ie_processing` | pixelprocessor=2 | 2 | 2 | 4 | `0x20`=2, `0x28`=2 |
| `SubstanceDesigner__color` | shuffle=5, pixelprocessor=3 | 8 | 3 | 17 | `0x20`=8, `0x06`=5, `0x28`=3, `0x0C`=1 |

Four of these are consistent with `0x20` = bitmap only because bitmap count and output
count happen to coincide. `SubstanceDesigner__color` separates them: it has **no bitmap
nodes at all**, three outputs, and eight `0x20` records — matching its eight
`compInputBridge` nodes and nothing else.

The rule that fits all nine is that `0x20`/`0x21` marks a **source node**: a leaf with no
image input, whether that leaf is a bitmap resource, an `svg`, or a graph input bridge.

    0x20 count == compInputBridge + bitmap + svg     9/9 exact, instance-free
                                                     totals 805 vs 882 corpus-wide

On files *with* instances the same identity holds only 59% of the time, which is expected
and not a counter-example: inlining deletes the inner graphs' input bridges by wiring the
caller's edge straight through, so the binary legitimately carries fewer sources than the
sources declare.

### The two forms of a source record

The two sub-kinds are distinguishable without the source. From `Metal_Vent_006` (six
bitmaps, no inputs) and `SubstanceDesigner__color` (eight inputs, no bitmaps):

| | bitmap source | input-bridge source |
|---|---|---|
| tag | `AA21` — high byte is the resolution field, 1024x1024 | `8820`/`8821` |
| class | `0208` | `0019`, `0009` |
| slot 1 | byte offset into the resource segment | uid-like hash (`D61A34A6`, `20F07E88`) |
| slot 2 | *(next record — the record is 8 bytes)* | offset into the interface block |
| slot 3 | - | constant `0A420001` |

In `Metal_Vent_006` the six slot-1 values are `0x000004`, `0x300004`, `0x600004`,
`0x900004`, `0xC00004`, `0xF00004` — a stride of exactly `0x300000` = 1024 x 1024 x 3,
one RGB8 image each.

### The resource descriptor table is the source records

`extract_images.find_table` scans the region between the directory and the interface
block for words matching `valid_tag`, and returns (tag, offset) pairs. I had been
describing its output as a *descriptor table* — a separate index of embedded images.

It is not separate. Those descriptors are exactly the `0x20`/`0x21` bitmap-source records
already listed in the record directory:

    resource offsets found by find_table  ==  slot 1 of directory-listed source records
    identical                             33 / 33 specimens
    (349 of 382 have no descriptors: procedural materials with no embedded bitmaps)

Not one specimen has a descriptor that is not a directory record, or a directory source
record the table missed. So the scanner is redundant — every descriptor is reachable by
walking the directory and filtering on the tag, with no need to guess at record spacing
(the "8 bytes in some files and 32 in others" that forced the scan in the first place is
just the ordinary variation in record size).

This also retroactively justifies `valid_tag`'s much-audited `0xAA` check. It is not a
magic marker: it is the resolution field, which a bitmap source has and an input-bridge
source does not. Requiring it selects bitmaps out of the source records, which is exactly
what an image extractor wants.

### A correction to the run that produced this section

The count comparison above was first run with a hand-written tag map that got three
entries wrong: it assigned `0x00` to `passthrough` (it is `gradient`), `0x10` to
`gradient` (it is `emboss`), and `0x26` to `emboss` (it is `passthrough`). All three are
correctly recorded elsewhere in this document; the error was in the throwaway script, not
in the notes.

That error manufactured an anomaly. With `gradient` read at `0x10`, 26 files appeared to
declare gradient nodes and contain none, and I briefly concluded that `gradient` had no
tag at all and must compile into a value-table ramp consumed by some other node. It does
have a tag, and the ramp fact was already established: `gradient` is `0x00`/`0x01`, and
its 64-point ramp hangs off slot 3 of its own record, 572 of 572.

Re-run against the correct map:

    files with gradient nodes or 0x00 records    49
    declared gradient nodes                     166
    0x00 / 0x01 records                       1,501
    files where records < declared nodes          7

The remaining seven are small deficits (1 -> 0, 2 -> 1, 8 -> 5) in a single author's
package, and are the subject of the next section.

The lesson is narrow but worth stating: a hand-built lookup table is an instrument like
any other, and this one had no downstream check. Nothing in the comparison could notice
that `0x10` was the wrong row - a wrong mapping produces a confident number rather than
an error. The counts in the table above are only trustworthy for the rows whose mapping
is independently established.

## Dead-code elimination, and the `.sbs` schema generation that hid it

Chasing the seven files where a filter's record count fell below its declared node count
turned up one compiler behaviour that was not documented, one source-format fact that had
been silently corrupting the measurement, and one residue that is still open.

### The `.sbs` files come in two schema generations

Source graphs express an edge as a `connRef` naming the upstream node's uid, and there are
two spellings of it in this corpus:

    newer   <connections><connection> <connRef v="1463393020"/>            </connection>
    older   <connexions><connexion>   <connRef><value v="1220724543"/></connRef> </connexion>

The element names differ (`connexion`, the French spelling, in the older files) and so does
the reference: an attribute in one, a nested `<value>` element in the other.

Matching only the attribute form makes every node in an older file look like it has no
inputs. This is a silent failure of exactly the kind catalogued in the instrument audit -
the parse succeeds, the graph is built, and every node simply appears to be an orphan. It
put the "unreachable node" rate at **43.3%** and made whole materials look like dead code.
With both forms matched the rate is **19.2%**. Any tool reading `.sbs` files needs to
handle both spellings.

### The compiler eliminates nodes that cannot reach an output

With the graph parsed correctly, backward reachability from the `compOutputBridge` nodes
explains most of the record deficits:

    deficits, counting all declared nodes        58
      removed by counting only reachable nodes   35
      still short                                23

Every gradient case is in the explained set - `LGMLtools__DeepVectorWarpMorph` declares one
gradient node, one transformation and one blur that no output can reach, and the binary
contains none of them. So the record count is predicted by *live* nodes, not declared
nodes, and a reader should not expect a compiled package to account for everything the
source contains. Across 102 paired non-library files, 1,600 of 8,325 nodes (19.2%) are
unreachable and 47 files contain at least one.

This is a third compiler behaviour alongside the inlining of `compInstance` and CSE, and it
is the one that removes nodes rather than duplicating or merging them.

### The residue: `passthrough` is culled by an undetermined rule

The 23 remaining deficits are almost all `passthrough` in one package family. The
identification `0x26` = `passthrough` is not in doubt - across 96 files it is by far the
best predictor of the `0x26` count:

| predictor | r | exact | total |
|---|---|---|---|
| live passthrough nodes | +0.843 | 69/96 | 442 vs 294 |
| all passthrough nodes | +0.841 | 66/96 | 459 vs 294 |
| passthroughs feeding an output | +0.691 | 76/96 | 121 vs 294 |
| `n_out` | +0.422 | 2/96 | 685 vs 294 |

But some are removed and the criterion is not any of the obvious ones. In
`DLG-Tools__Clean_Steel_01`, 32 passthrough nodes - all reachable, all in a single graph
whose `n_out` of 18 matches the binary exactly - become 16 records. Three hypotheses were
tested and all fail:

* **Not resizing.** The documented "passthrough resizes 98% of the time" would explain
  keeping only the resizing ones, but not one of the 32 declares an `outputsize`
  parameter; they are all plain dots.
* **Not reachability.** All 32 are live.
* **Not output adjacency.** Counting only passthroughs feeding an output raises exact
  matches to 76/96 but undershoots the corpus total by more than half (121 against 294),
  so it is not the rule either.

One caution about this evidence: the affected DLG-Tools files share the node uid
`1464323189` across all four, so they are copies of a common template and constitute one
authoring pattern, not four independent observations. The residue is real but narrow.

## The record graph, checked against source topology for the first time

Every previous check on the edge map was internal to the binary: does a slot hold a
backward reference, does the record inherit its parent's resolution. Those tests can
confirm that a slot behaves like an edge; they cannot confirm that the resulting graph is
the graph the author drew. With `.sbs` connectivity now parsed correctly (both schema
generations) and dead nodes accounted for, the reconstructed record graph can be compared
against the real one.

The comparison is only valid on the instance-free pairs, where nodes and records
correspond one to one. Source edges into a `compOutputBridge` are excluded, since outputs
are not records; source node kinds `in`, `bitmap` and `svg` are folded to `source`,
following the source-node finding above.

| edge map | matched | source only | binary only | recall | precision |
|---|---|---|---|---|---|
| as documented | 33 | 1 | 5 | 97% | 87% |
| with `0x28` slot 1 dropped | 33 | 1 | 1 | **97%** | **97%** |
| with `0x28` slot 2 dropped | 24 | 10 | 4 | 71% | 86% |

So the map is essentially right - the graph an importer reconstructs from the record
slots *is* the author's graph - and the one systematic defect is `pixelprocessor`.

### `pixelprocessor` slot 1 is an arity, not an edge

Every false edge in the first row is `pixelprocessor -> pixelprocessor`, and `ie_processing`
makes it obvious: its two pixelprocessors are in **different graphs** and cannot be
connected at all. The two records read

    [1] tag=8828  slot1=00000001  slot2=00000000   <- input is record 0
    [3] tag=8828  slot1=00000001  slot2=00000002   <- input is record 2

Slot 1 is `1` in both. It is not an index; it is the constant 1. Across 12,105
pixelprocessor records in 150 specimens slot 1 takes the values 1 (8,408), 2 (2,715),
0 (448), 3 (392) and 4 (19) - 99% of them in 0..4.

It nevertheless looked backward-referencing in **99.3%** of records, because a small
integer is almost always less than the record's own index. This is precisely the failure
mode this document already warns about, and it is the fifth edge-slot error of the same
family. What is new is how it was caught: not by a better statistic on the binary, but by
ground truth that could contradict it. The four earlier errors were found by a stronger
internal test; this one was invisible to every internal test, because slot 1 passes them
all.

### `pixelprocessor` takes a variable-length input list

Slot 1 is the number of inputs, and the inputs follow it:

    slot 1        n, the input count
    slots 2..n+1  n backward record indices

Checked by requiring slot 1 to equal the length of the backward-index run beginning at
slot 2:

    pixelprocessor records tested   16,500
      slot 1 == run length          16,483  (99.9%)
      run shorter than slot 1           17  (0.1%)

with the pairs distributed as (1,1) 11,456, (2,2) 3,638, (0,0) 703, (3,3) 586, (4,4) 61,
(5,5) 17, (6,6) 22. Nothing has a run *longer* than its declared count.

This is why a fixed slot list was never going to describe `pixelprocessor`: it is the one
filter whose input count is data rather than a property of its type, which makes sense for
a node whose whole purpose is evaluating an arbitrary per-pixel expression over however
many images the expression references. The count field also gives this reading its own
downstream check - a wrong `n` would leave the run mismatched - which is why it can be
stated at 99.9% rather than as a correlation.

**Corrected edge map entry:** `0x28` / `0x29` -> slot 1 is `n_inputs`; edges are slots
`2 .. n+1`. The previous entry, slots `[1, 2]`, over-reported an edge in every
pixelprocessor record and under-reported inputs in the 3,000-odd records with three or
more.

### The arity field is specific to `pixelprocessor`

The obvious follow-up is whether other filters carry a count in slot 1 too. They do not.
Applying the same test - slot 1 no greater than 8, and equal to the length of the
backward-index run starting at slot 2 - to every identified filter over 150 specimens:

| filter | records | slot 1 <= 8 | run == n | agreement |
|---|---|---|---|---|
| `pixelprocessor` `0x28` | 12,105 | 12,020 | 12,013 | **100%** |
| `fxmaps` `0x08` | 11,358 | 1,544 | 986 | 64% |
| `directionalwarp` `0x18` | 14,721 | 823 | 513 | 62% |
| `normal` `0x24` | 367 | 288 | 175 | 61% |
| `levels` `0x1E` | 24,850 | 5,200 | 1,254 | 24% |
| `blend` `0x02` | 85,880 | 316 | 47 | 15% |
| `transformation` `0x04` | 67,034 | 14 | 0 | 0% |
| `gradient` `0x00` | 5,423 | 51 | 0 | 0% |
| `warp` `0x0E` | 7,320 | 522 | 0 | 0% |
| `distance` `0x2A` | 538 | 483 | 0 | 0% |

`pixelprocessor` is the only filter where slot 1 is *always* a small integer (99.3% of
records) *and* always matches the run. Everywhere else slot 1 is a small integer in a
minority of records - 0.4% for `blend`, 0.02% for `transformation` - and agrees with the
run at or below chance when it happens to be one. The middle rows are the interesting
non-result: `fxmaps` and `directionalwarp` reach 62-64% agreement, but only within the
small subset where slot 1 happens to be small, which is what coincidence looks like at
these counts.

So variable arity is a property of one filter, not of the record format. Every other
filter's input count is fixed by its type, and the fixed slot list remains correct for
them.

## A complete census of what is left unnamed

Two questions bound how much of the node vocabulary is still unknown: which record tags
occur that this document cannot name, and which source filters produce no tag it can
match. Both now have exact answers.

### Every record tag in the corpus

Over all 383 deduplicated specimens, 750,000-odd records carry 23 distinct tags:

| tag | records | files | filter | tag | records | files | filter |
|---|---|---|---|---|---|---|---|
| `0x00` | 13,156 | 277 | `gradient` | `0x18` | 42,220 | 239 | `directionalwarp` |
| `0x02` | 227,121 | 331 | `blend` | `0x1A` | 931 | 173 | `sharpen` |
| `0x04` | 170,102 | 345 | `transformation` | `0x1C` | 555 | 167 | `hsl` |
| `0x06` | 5,309 | 251 | `shuffle` | `0x1E` | 63,453 | 315 | `levels` |
| `0x08` | 28,787 | 306 | `fxmaps` | `0x20` | 1,095 | 152 | source node |
| **`0x0A`** | **119** | **5** | **unnamed** | `0x22` | 52 | 11 | `text` (probable) |
| `0x0C` | 13,025 | 314 | `uniform` | `0x24` | 1,000 | 282 | `normal` |
| `0x0E` | 19,876 | 246 | `warp` | `0x26` | 1,782 | 109 | `passthrough` |
| `0x10` | 405 | 79 | `emboss` | `0x28` | 38,335 | 258 | `pixelprocessor` |
| **`0x12`** | **5** | **4** | **unnamed** | `0x2A` | 1,670 | 175 | `distance` |
| `0x14` | 10,858 | 264 | `blur` | `0x2C` | 909 | 151 | `curve` (probable) |
| `0x16` | 10,978 | 262 | `motionblur` (probable) | | | | |

**Two tags are unnamed, and together they are 124 records - 0.02% of the corpus.** That is
the whole of the unknown filter vocabulary.

Neither is nameable from this corpus, for a reason that is worth stating rather than
retrying. `0x0A` occurs in five specimens and **not one has a source** - four are ambientCG
materials (`RoadSubstance002` with 70 records, `RoadLinesSubstance002` with 35,
`SnowSubstance002`, `TilesSubstance013`) distributed as `.sbsar` only. `0x12` occurs in
four, and the only two with sources are files excluded under the provenance policy for
containing Allegorithmic-authored graphs. So both are blocked by the absence of admissible
ground truth, not by any analytical difficulty; a single CC0 `.sbs` using either filter
would settle it.

### Source filters that produce no record

From the other direction, four filters appear in the paired sources with no tag assigned:

| filter | nodes | disposition |
|---|---|---|
| `grayscaleconversion` | 64 | compiles to `shuffle`, already documented |
| **`valueprocessor`** | **45** | **produces no record at all** |
| `dyngradient` | 8 | compiles to `gradient` |
| `dirmotionblur` | 4 | presumed `0x16` |

`valueprocessor` is the substantive one. Ten paired files declare 45 of them - as many as
13 in `SubstanceDesigner__triDraw`, 8 each in `ie_pcloud` - and **not one of those files
contains a single `0x0A` or `0x12` record**, nor any surplus in a named tag. The node
compiles to nothing in the record graph.

That is the expected result once the node's purpose is considered: a value processor
reduces an image to a scalar used to *drive a parameter*, so its output is not an image
and it has no place in an image-processing DAG. It compiles into the parameter bytecode
instead. This makes a fourth disposition for a source node, alongside becoming a record,
being eliminated as dead code, and being culled as a redundant `passthrough`.

### What this costs the graph reconstruction

Since instanced files cannot be inlined - **no paired file is self-contained; every one
with a `compInstance` has at least one external dependency** - the topology check on them
can only be a containment test: the author's own edges, between live non-instance nodes,
must all appear in the binary, because inlining adds edges and never removes them.

    source edges (live, non-instance endpoints)   2,938
    present in the binary edge multiset           2,171  (73.9%)
    files with zero shortfall                     42 / 102

The 26% shortfall is not unexplained. It decomposes into the compiler behaviours already
documented: edges through culled `passthrough` nodes are rewired (`passthrough`->anything
accounts for 249 of the missing), `grayscaleconversion` endpoints are relabelled `shuffle`
(32), `uniform` sources are constant-folded (122), and edges into `valueprocessor` (24)
cannot appear because the node produces no record. What remains is consistent with those
four mechanisms rather than with a wrong edge map - which the instance-free test, where
none of these confounds apply, measures at 97% recall and 97% precision.

## Counting cannot validate the opcode names, and it was predictable that it could not

The `.sbs` sources carry the ground truth for the instruction set: parameter expressions
are authored as **function graphs**, thousands of `<paramNode>` elements each naming a
`<function>`. The vocabulary lines up almost too neatly - **65 distinct function names in
the sources against 45 distinct operations in the ISA**, with names that match on sight:
`mul`, `add`, `sub`, `div`, `neg`, `set`, `sequence`, `ifelse`, `swizzle`, `dot`,
`samplecol`, `samplelum`, `toint1`, `const_float1`.

So the obvious check is to correlate, across paired files, how often a source names a
function against how often the binary uses an operation. Over 81 paired files carrying
94,676 function nodes and 952,003 decoded instructions, that check **fails**, and the way
it fails is instructive.

Raw counts produce a degenerate answer: every operation correlates about +0.15 with every
function, and the same two functions top the list for all of them. That is file size, not
meaning - a bigger material has more of everything.

Normalising to within-file proportions removes the size effect and leaves the diagonal
detectable but not dominant. Of 27 well-populated operations with a documented meaning,
the documented name appears in the top two correlated functions **4 times**:

| operation | documented | best-correlated source functions |
|---|---|---|
| float `0C` | sequence | **sequence +0.83**, set +0.82, swizzle2 +0.80 |
| float `07` | set | sequence +0.80, **set +0.78**, not +0.78 |
| float `10` | swizzle | **swizzle2 +0.58**, not +0.49, sequence +0.49 |
| float `34` | samplecol | const_float2 +0.60, **samplecol +0.55**, lerp +0.52 |
| float `2B` | exp2 | iswizzle1 +0.86, get_integer2 +0.86, get_float4 +0.84 |
| float `14` | mul | exp +0.86, dot +0.85, neg +0.83 |

The four hits are real signal - `sequence` and `set` find their own names at the top of
78 candidates - but the margins are inside the noise. `set` scores +0.78 while `not`, a
function with no relation to it, scores +0.78 as well.

**This was predictable, and OPCODES.md already predicted it.** Three documented compiler
behaviours each break the count relation independently:

* **CSE.** Identical subexpressions are emitted once. The catalogue's own example: 289
  `dot` nodes in `ie_processing` collapse to a single instruction.
* **Inlining.** Function graphs inside instanced subgraphs are inlined, so the binary
  contains instructions from graphs whose source is not in the file being counted.
* **Lowering.** `pow`, `log2`, `length`, `normalize` and `clamp` are not instructions at
  all; they are expanded into other operations, so their source counts have no
  corresponding opcode and the opcodes they expand into are inflated.

Any one of these would blunt a counting argument. Together they make it useless, and no
amount of care in the statistics repairs it - the quantity being correlated is not
conserved between the two sides.

The names in OPCODES.md rest on structural evidence - arity, type, component width,
operand kind, position in the operation-by-type matrix - and that evidence is unaffected
by this negative result. But it does mean **the naming has no independent corroboration**,
which by the standard applied elsewhere in this document places it with the findings that
still lack a downstream check.

**What would work instead.** The relation that CSE, inlining and lowering all preserve is
*shape*, not count: a function graph and its compiled block are the same DAG up to those
transformations. Matching a small authored function graph against the instruction DAG of
the block it compiles to would test the names one operation at a time, and that check is
independent of every confound above. That is the next thing to try.

## The opcode names do have independent corroboration: arity

The previous section concluded that counting cannot validate the ISA names, and proposed
matching shapes instead. Matching whole DAGs turned out to be premature - a first attempt
failed on 481 of 542 graphs because I built the block signature from `opcode >> 10`, which
counts *operand tokens* and therefore includes immediates, so a `const_float1` with no
inputs presents as arity 1 or 2. But the weaker shape invariant works, and it is enough.

### Real in-degree, measured from the bytecode

Counting only those operand tokens that are back-references to earlier instructions in the
same block gives each operation's true input count:

| operation | catalogue | in-degree |
|---|---|---|
| `int 02` | input reference | **0** (100%) |
| float `17`, `23`, `2B`, `11` | neg, abs, exp2, type conversion | **1** (98-100%) |
| float `0D`, `14`, `13`, `12`, `15`, `30`, `31`, `0C` | construct vector, mul, sub, add, div, min, max, sequence | **2** (98-100%) |
| bool `1F` | gt | **2** (98%) |
| float `09` | ifelse / select(c,a,b) | **3** (99%) |

Every name predicts its arity and every prediction holds. On its own this is close to
circular - arity was one of the structural signals used to assign the names in the first
place.

### The non-circular version: arity measured from the sources

The `.sbs` function graphs give the same quantity from a completely separate artifact. A
source `ifelse` node has three `connRef` children, a `neg` node has one, a `const_float1`
node has none. Comparing source-declared arity against binary in-degree, over 31 function
names carrying 40 or more nodes each:

    arity agrees      28
    arity disagrees    3

with agreement across the whole frequency range - `const_float1` (11,312 nodes, 0 = 0),
`mul` (9,834, 2 = 2), `ifelse` (4,982, 3 = 3), `vector2` (5,031, 2 = 2), `get_float1`
(2,348, 0 = 0), `dot` (746, 2 = 2), `ceil` (40, 1 = 1).

**All three disagreements are the same artifact, and it is one this document already
describes.** `set` (source 1, binary 2), `samplecol` (1 vs 2) and `samplelum` (1 vs 2) are
exactly the instructions that carry an immediate alongside their value operand - the
catalogue lists the variable slot of `0x07` among the immediates. My in-degree measure
counts a small-valued immediate token as if it were a back-reference, inflating those
three by one. No other operation in the comparison carries an immediate, and no other
operation disagrees.

So the ISA names are corroborated after all, by a measurement that CSE, inlining and
lowering cannot disturb: those transformations change how *many* instructions appear, but
not how many inputs an operation takes. The claim in the previous section that the naming
"has no independent corroboration" was correct about counting evidence and wrong as a
general statement; this supersedes it.

## The four unnamed opcodes: two hypotheses killed, one name verified

The catalogue has four rows with no meaning: `int 08` (`0A48`), `bool 08` (`0448`),
`int 3D` (`0A3D`) and `int 38` (`1EB8`). Together they are about 2,300 instructions -
0.02% of the corpus - but they are the whole of the unknown instruction set.

### What they have in common

Measured by real in-degree (operand tokens that are back-references), all four are
**leaves**:

| opcode | instances | in-degree 0 | operand tokens | consumed by |
|---|---|---|---|---|
| `int 38` | 190 | 94% | 7 | swizzle 37%, constant 27% |
| `bool 08` | 161 | 84% | 1 | constant 36%, swizzle 13% |
| `int 08` | 147 | 97% | 2 | constant 31%, swizzle 22% |
| `int 3D` | 90 | 100% | 2 | - |

A leaf whose operands are all immediates is a constant or a reference of some kind, which
is the same family as the three named leaves: `constant (immediate)`, `input reference
(u32 uid)` and `read system variable`.

### Hypothesis 1: `0x08` is the counterpart of `set`

`0x07` is `set - assign variable slot`, taking an immediate slot number. The adjacent id
`0x08` being the matching *read* is close to irresistible, and it is falsifiable: the slot
`0x08` names should be one that some `0x07` writes in the same block.

    read slot written earlier in the block      6   (0.7%)
    slot never written                        818  (99.3%)

**Falsified.** Whatever `0x08` names, it is not a variable written by `set` in its own
block.

### Hypothesis 2: `int 08` is a uid reference like `int 02`

`int 08` carries two operand tokens, which is a 32-bit immediate - the same shape as
`int 02`, documented as `input reference (u32 uid)`. Reassembling the pair and testing it
against the uids in the file's interface block:

    int 0x08   matches an interface uid     0 / 202     (0%)
    int 0x02   matches an interface uid   148,666 / 148,760  (99.94%)   <- control

**Falsified**, and unambiguously so, because the control is decisive in the same run.

### The control mattered more than the test

The first version of this measurement returned 0% for `int 08` *and* 0% for the `int 02`
control, because my uid extraction assumed the parser's `inputs` were dictionaries when
they are `(kind, uid, value)` tuples - so the comparison set held only output uids. Had I
run the test without the control, "`0x08` is not a uid reference" would have been recorded
as a finding on evidence that could not have shown anything, since the instrument could
not confirm even the reference that is known to be one.

This is the instrument-audit rule in its most direct form: a predicate that cannot be seen
to fail is worthless, and the cheapest way to see it fail is to point it at something whose
answer is already known.

### What the control incidentally established

Fixing it turned the control into a result. `int 02` is documented as `input reference
(u32 uid)` on structural grounds; its immediate is now confirmed to be *exactly* an
interface uid in **99.94%** of 148,760 instructions across 150 specimens. That is a
documented ISA name verified against an independent structure in the same file, and it is
the strongest single-opcode confirmation in the catalogue.

The four unnamed opcodes remain unnamed. They are leaves carrying immediates that are
neither variable slots nor interface uids, and at 0.02% of instructions they are the
residue of the instruction set rather than a gap in it.

## Type 3 was never a type

The opcode encoding gives bits 9-8 to the value type: 0 bool, 1 float, 2 int, and 3
documented as unused. But type-3 opcodes do decode, and a standing note recorded one of
them - `0B19` - as real but unidentified, at 1,358 occurrences in 106 specimens.

Decoding 150 specimens by walking records rather than scanning, the type field splits:

    type 0  bool      112,993    2.466%
    type 1  float   3,721,409   81.228%
    type 2  int       742,938   16.216%
    type 3              4,110    0.090%

Two measurements identify what the 0.09% is.

**Its operation ids are 4-aligned.** 77% of type-3 opids are congruent to 0 mod 4, against
the 25% a real opcode field would give:

    opid mod 4 == 0    3,158   77%
    opid mod 4 == 3      468   11%
    opid mod 4 == 1      281    7%
    opid mod 4 == 2      203    5%

That is the signature of reading 4-aligned data - a pointer, or the low half of a float -
and interpreting it as an opcode.

**It clusters at the end of blocks.** 32% of type-3 opcodes are the last instruction in
their block, far above the share a uniformly distributed operation would take in blocks
averaging many instructions. A block whose declared count overruns its real extent
produces exactly this: the tail of the walk lands in whatever follows.

**And `0B19` is not special.** Splitting type 3 into `0B19`, the 4-aligned bulk, and
everything else gives three populations with the same profile:

| kind | instructions | files | interior | at block end |
|---|---|---|---|---|
| opid mod 4 == 0 | 4,494 | 128 | 69% | 31% |
| other type 3 | 1,163 | 101 | 65% | 35% |
| `0B19` | 62 | 5 | 68% | 32% |

`0B19` behaves identically to the residue it was distinguished from, and appears in 5 of
200 specimens rather than 106. Its higher recorded count came from the flat-scan
measurement that OPCODES.md already marks superseded for inflating instruction counts
roughly twofold "with misread record data" - and misread record data is precisely what
type 3 is.

So the encoding table is right and needs no exception: **type 3 is unused.** Everything
observed under it is the residue of decoding, which also means the residue has a
signature, and a decoder can use it - a type-3 opcode is a reliable indicator that the
walk has left the instruction stream.

### What this says about the uncatalogued tail

Over all 382 specimens, 190 (type, opid) pairs occur that have no catalogue row, totalling
35,162 instructions - **0.263%** of the corpus. Type 3 accounts for a large share of them,
and the rest follow the same pattern: hundreds of instructions each, spread thinly over
many files, in exactly the places where a block's extent is uncertain. The catalogue's
claim to cover 96.5% of instructions with no uncatalogued opcode appearing in 20 or more
specimens is consistent with this - what is left is not a set of unknown operations but
the cost of decoding a format that never declares where a block ends.

## Body-region tiling: a downstream check for record extent

Record length is the format's central omission - nothing declares where a record ends, and
the best header-based prediction reached 69.3%. That made it one of the findings with no
way to tell a right answer from a wrong one. But the region between the directory and the
value table holds records and bytecode and nothing else, so a correct set of extents must
**tile** it. That is the same shape of check as resource descriptors tiling the resource
segment, and it had not been applied here.

### Coverage, walking each record and chaining its blocks

For every directory record, find the first decodable instruction block after the header,
then keep decoding consecutive blocks until the next record begins. Bytes claimed by a
record header or by a block are covered; the rest is not.

| record class | region bytes | covered | with zero padding counted |
|---|---|---|---|
| **ordinary filter records** | 20,239,780 | **95.6%** | **97.8%** |
| `pixelprocessor` | 8,129,056 | 58.7% | 68.0% |
| `gradient` | 774,572 | 47.7% | 57.4% |
| `fxmaps` | 9,023,312 | 7.4% | 46.4% |
| all | 38,166,720 | 65.9% | 78.5% |

Records average **1.20 blocks** each, so multi-block records are common but not the norm.

The headline number is the first row. For ordinary filter records - everything except the
three classes below - a record header plus its chained instruction blocks accounts for
**95.6%** of the region, and 97.8% once trailing zero padding is counted. The extents are
essentially right.

**The shortfall is concentrated in exactly the three classes known to store something
other than bytecode**, which is what makes the result interpretable rather than
disappointing:

* `fxmaps` at 7.4% - the FX-Map trees, 12-byte branch nodes and 44-byte-plus leaves,
  already documented as a separate structure. The walker is not meant to decode them.
* `gradient` at 47.7% - the 64-point colour ramps hanging off slot 3, likewise a known
  table rather than a program.
* `pixelprocessor` at 58.7% - the one genuinely open case, discussed below.

So the uncovered third of the region is not unexplained territory. Two of its three parts
are structures this document already describes; they simply are not instructions.

### The check earns its keep immediately

Diagnosing where the `pixelprocessor` chain stops showed the dominant cause to be a
declared instruction count of **zero** - 2,393 of roughly 3,289 stops, nearly all with
fewer than 64 bytes left before the next record. An empty block is a plausible thing for
the format to emit, so I relaxed the walker to accept `n == 0`.

    overall coverage, rejecting zero-count blocks    65.9%
    overall coverage, accepting them                 10.1%

Coverage collapsed by a factor of six. A zero word matches at almost any position, so the
first-block scan latches onto the first pair of zero bytes it sees and the chain then
crawls forward two bytes at a time, covering nothing. The zero words are trailing padding,
not blocks.

The point is not the failed relaxation - it is that **the failure was visible in the same
run**. A more permissive predicate always accepts more candidates, and without a
downstream constraint that looks like progress. Here it produced a number that fell off a
cliff, and the mistake was obvious within one measurement. This is the fourth finding to
be caught or confirmed by a constraint it was not designed for, and the first time the
constraint has protected the record-extent work specifically.

Counting zero runs as padding rather than as blocks is the correct accounting, and gives
the 97.8% in the table.

## Choosing the block start by coverage, not by first match

The tiling measurement above located the block after a record header by scanning forward
and taking the **first** offset that decodes. That is the obvious rule and it is the wrong
one.

Dumping the uncovered tail of a `pixelprocessor` record shows why:

    F4 09 02 00 00 00        opcode 09F4, operands 2, 0
    40 15 00 00 00 00 80 3E  constant, immediate 3E800000 = 0.25
    52 09 02 00 04 00        float add (0952) on values 2 and 4
    40 11 00 00 00 3F        constant, immediate 3F000000 = 0.5

The "uncovered" tail is not an unknown structure at all - it is perfectly ordinary
instructions. What had happened is that the forward scan found an *earlier* offset where a
small count and a few bytes happened to decode, took that as the block, and then looked for
the next block's count at a position that is in the middle of the real program. The chain
derails and everything after it is written off.

Choosing instead the candidate start whose whole chain covers the most bytes:

| record class | first match | best coverage |
|---|---|---|
| ordinary filter | 86.5% | **97.5%** |
| `pixelprocessor` | 50.1% | **86.9%** |
| `gradient` | 91.7% | **94.1%** |
| `fxmaps` | 5.6% | 34.7% |
| **overall** | **59.7%** | **80.3%** |

`pixelprocessor` gains 37 points and stops being an anomaly. Overall coverage of the
records-and-bytecode region goes from three-fifths to four-fifths, and for ordinary filter
records the region is essentially fully accounted for.

### This corrects the attribution in the previous section

That section reported `gradient` at 47.7% covered and explained the shortfall as the
64-point colour ramps - a known structure that is not a program. Under the better start
rule `gradient` covers **94.1%**, so most of what I attributed to ramp tables was the same
scan artifact as everywhere else. The ramps are real and documented, but they were not what
that number was measuring.

The general claim survives and the specific attribution did not. `fxmaps` remains genuinely
uncovered at 34.7%, because FX-Map trees really are a separate structure that an
instruction walker cannot decode; that part of the earlier reasoning was right. But I had
three classes and offered the same explanation for all three, when only one of them needed
it - a reminder that a story which fits every case is usually fitting none of them
tightly.

**Practical consequence for a reader.** Block extents should be recovered by maximising
coverage to the next record, not by accepting the first decodable candidate. The greedy
rule is cheap and wrong in a way that is invisible without a tiling check: it always
produces *a* block, and the bytes it forfeits look like unexplained format rather than a
bad choice.

## What the FX-Map region actually contains

`fxmaps` is the last record class the tiling walk leaves largely uncovered, at 34.7% of
9 MB. The explanation is not that its bytes are unknown - it is that they are bytecode the
walker cannot reach.

Following an `fxmaps` record's slot 2 to its tree root and dumping raw words:

    +  0  00020008     tag
    +  4  00002B20     -> body
    +  8  14420248
    + 12  00002B2C     -> body
    + 16  00002BA0     -> body
    + 20  00002B38     -> body
    + 24  00002B6C     -> body
    + 28  00002B94     -> body
    + 32  09000009     count 9, then opcode 0900
    + 36  40C8F5C3     immediate 6.28
    + 40  00000532     ...

The word at +32 is a block header - an instruction count of 9 followed by a float constant
carrying 6.28 - and everything after it decodes as ordinary instructions. **An FX-Map node
is a small pointer table immediately followed by a bytecode block.**

That is why the chained walk stalls here while it succeeds on ordinary records. The chain
requires blocks to be contiguous; in the FX-Map region they are separated by each node's
pointer table, and the walk stops at the first one it meets.

### The node sizes check out from a second direction

Node roles were originally assigned by counting children: 8-byte links, 12-byte branch
nodes, leaves of 20 bytes and up. Measuring instead the distance from a tree pointer to the
first position that decodes as a block, over 1,576 tree roots:

    offset 12    1,072   68%
    offset  4      116    7%
    offset 40       81    5%
    offset 16       75    5%
    offset 24       52    3%

**68% of roots have their first block exactly 12 bytes in**, which is the branch-node size
established by the child-counting analysis. The two methods share no assumptions - one
counts graph structure, the other asks where instructions begin - and they agree on the
same number.

So the FX-Map region is not a gap in the format description. It is node headers interleaved
with parameter programs, and covering it requires a walker that resynchronises across the
headers rather than one that gives up at the first non-block word.

### Resynchronising closes the region

Letting the chain skip forward to the next decodable block when it meets a non-block word,
with a bounded search window, and measuring what fraction of each record's span is decoded
bytecode versus skipped bytes:

| skip window | overall | of which blocks | skipped | `fxmaps` | `pixelprocessor` | ordinary |
|---|---|---|---|---|---|---|
| none | 73.9% | 73.9% | 0.0% | 14.1% | 88.8% | 95.9% |
| 64 B | 92.8% | 91.0% | 1.8% | 78.6% | 99.9% | 98.2% |
| 256 B | **97.0%** | **94.2%** | 2.9% | **96.1%** | 99.9% | 98.2% |

With a 256-byte window the records-and-bytecode region is **97.0% accounted for, 94.2% of
it as decoded instruction blocks**. `fxmaps` goes from 14.1% to 96.1%, which is the
strongest confirmation that its region was never anything but node headers and programs.
`pixelprocessor` reaches 99.9% at a 64-byte window.

**The caveat this needs.** The skip window is a free parameter, and a larger window can only
increase coverage - which is the shape of an over-fitted result. Two things argue it is not:
the skipped fraction stays small and grows slowly (1.8% to 2.9%) while the *block* fraction
does the work (91.0% to 94.2%), whereas a window manufacturing false matches would inflate
skipped bytes; and `pixelprocessor` saturates at 64 bytes and gains nothing from 256, which
is what a real structure with bounded headers looks like. Only `fxmaps`, whose leaves run to
56 bytes and whose pointer tables are larger, needs the wider window.

**Where this leaves record extent.** The format still declares no record length, and that
has not changed. But the region those records live in is now 97% explained, which means the
extents recovered by walking are very nearly a tiling - and a tiling is the check that
record-length work never had. The residual 3% is concentrated in the FX-Map leaves and in
zero padding, not spread thinly across every record.

## The uncatalogued residue is a floor, not an artifact

The better walker makes a testable prediction. If the uncatalogued tail of the instruction
census is mostly decode damage - opcodes read out of misframed blocks - then recovering
extents properly should shrink it. Censusing the same 45 specimens under both walkers,
with type-3 blocks rejected in each so the comparison is like for like:

| walker | instructions decoded | uncatalogued |
|---|---|---|
| first match, no resync | 2,122,687 | 0.092% |
| best coverage + resync 256 | 2,853,055 | 0.121% |

**The prediction failed.** The residue did not shrink; it rose slightly, while the volume
of decoded instructions rose by 34%.

That failure is worth more than the confirmation would have been, because of what it says
about the 730,368 instructions the new walker recovers that the old one missed: they are
**99.88% catalogued**. Bytes that were not instructions could not behave that way. Random
or misframed data decoding under the length rule lands on uncatalogued operation ids at a
far higher rate - that is exactly how type-3 residue was identified two sections ago. A
third of a million newly reached instructions arriving with essentially the same
catalogued share as the instructions already known is a strong statement that the new
walker is finding real code.

So the resync walker is validated by a measurement that was designed to test something
else, and the residue turns out to be a property of the corpus rather than of the decoder.

### This refines the earlier claim

The section on type 3 concluded that the uncatalogued tail - measured then at 0.263% - was
"not a set of unknown operations but the cost of decoding a format that never declares
where a block ends". That is now too strong, and the two figures separate the question:

* Rejecting type-3 blocks alone takes the residue from 0.263% to about 0.09%. **That part
  was decode damage**, and the earlier reasoning holds for it.
* The remaining ~0.1% is **stable under a 34% increase in decoded volume**. Improving the
  decoder does not touch it. That part is most likely genuine: rare operations, or rare
  component-width variants of known ones, that simply do not appear often enough in this
  corpus to catalogue.

The honest statement is therefore that the instruction set is about **99.9% catalogued by
volume**, with a residual tenth of a percent that is real but too sparse to name - not
decode noise, and not reachable by decoding better.

### A dead end worth recording

The obvious way to identify individual operations - distinguishing `min` from `max`, which
arity cannot - is to anchor a source function graph to its compiled block using a
distinctive constant, then read the neighbouring opcodes off the alignment. The corpus does
not support it. Across every function graph in the paired sources there are only **48
distinct float constants**, and just **9 appear exactly once**; the rest are small integers,
with 1.0 alone occurring 2,693 times. There are not enough distinguishable anchors to align
more than a handful of graphs, so this route is closed with the corpus as it stands.

## Filters have version thresholds, and `0x12` is a legacy tag

The header was documented as having a fixed field layout with seven constant words,
measured on 58 specimens. Re-checked across all 382 deduplicated specimens and all seven
assembly versions, every one of those constants holds:

    0x14 = 1C   0x18 = 0   0x20 = 00010002   0x24 = 0   0x28 = 1   0x30 = 2   0x34 = 0

Identical in v2, v3, v4, v5, v6, v8 and v9 alike. The header is version-invariant apart
from the version word itself, which is worth knowing precisely because so much else about
the format is not.

### Which filters exist in which version

Counting the specimens per version in which each record tag appears at all:

| tag | filter | v2 (90) | v3 (5) | v4 (41) | v5 (192) | v6 (27) | v8 (6) | v9 (21) |
|---|---|---|---|---|---|---|---|---|
| `0x28` | `pixelprocessor` | **0** | **0** | 26 | 178 | 27 | 6 | 21 |
| `0x2A` | `distance` | **0** | **0** | 17 | 120 | 23 | 2 | 13 |
| `0x26` | `passthrough` | **0** | **0** | 2 | 80 | 13 | 1 | 13 |
| `0x2C` | `curve` | **0** | **0** | **0** | 116 | 20 | 3 | 12 |
| `0x22` | `text` | 0 | 0 | 0 | 9 | 0 | 0 | 2 |
| `0x10` | `emboss` | 22 | 2 | 10 | 32 | 11 | **0** | 2 |
| **`0x12`** | **unnamed** | **4** | **0** | **0** | **0** | **0** | **0** | **0** |

Four filters have clean introduction thresholds: `pixelprocessor`, `distance` and
`passthrough` appear from **v4** onward and never before, `curve` from **v5**. Absence
across 95 v2 and v3 specimens is not a sampling accident.

This is independent support for those identifications rather than a separate fact. A tag
that switches on at one version and is universal afterwards behaves like a filter the
product added in a release; a tag that is an artefact of misreading would not respect a
version boundary. `pixelprocessor` in particular goes from absent to appearing in 21 of 21
v9 specimens.

`emboss` runs the other way - present in 22 v2 specimens, down to 2 of 21 by v9 - which is
what a filter falling out of fashion looks like rather than one being removed.

### `0x12` is a version-2 filter that did not survive

The more useful result is for one of the two unnamed tags. **`0x12` appears in four v2
specimens and in none of the 292 specimens of any later version.** It is not a rare modern
filter; it is a legacy one, present in the oldest assemblies in the corpus and gone by v3.

That explains why it resisted identification. Its only sourced specimens are excluded under
the provenance policy, and its total corpus presence is 5 records in 4 files - but the
version profile says the reason it is rare is that it was **retired**, not that it is
obscure. A reader targeting current `.sbsar` files will never encounter it.

`0x0A` gets no such explanation: its five specimens are spread across v2, v5 and v9, so it
is neither legacy nor new, and its 119 records remain unidentified with no source
available for any specimen carrying it.

## The same version analysis fails for opcodes, and the control shows why

The filter-tag version thresholds in the previous section invite the obvious follow-up:
do operations have version thresholds too, and are the four unnamed opcodes legacy like
`0x12`? Running it produces a table that looks like an answer - the unnamed opcodes rise
from 8% of v2 specimens to 64% of v5 - and the answer is spurious.

The tell is in the named rows of the same table. `float 12` is `add` and `float 09` is
`ifelse`; both are core operations that no non-trivial program can avoid. They show up in
**49%** and **46%** of v2 specimens. An operation cannot genuinely be missing from half
the files of a version when it is the arithmetic every parameter expression is built from,
so whatever the table measures, it is not availability.

### The control: hold version fixed and vary size

Within version 5 alone, bucketing the 192 specimens by record count:

| operation | 0-50 recs | 50-200 | 200-1000 | 1000+ |
|---|---|---|---|---|
| `add` | 70% | 93% | 100% | 100% |
| `ifelse` | 70% | 100% | 100% | 100% |
| `min` | 80% | 93% | 100% | 100% |
| `int 08` (unnamed) | 0% | 7% | 47% | 82% |
| `bool 08` (unnamed) | 0% | 21% | 53% | 83% |
| `int 38` (unnamed) | 0% | 7% | 47% | 81% |

Presence in a file is a function of **how big the file is**, not which version wrote it.
`add` climbs from 70% to 100% across size buckets inside a single version. The unnamed
opcodes climb from 0% to 82% the same way - they are simply rare operations that need a
large program before they appear at all, which is consistent with their instruction counts
of 90 to 190 across the whole corpus.

There is a genuine secondary effect underneath: decode coverage really is lower on early
versions, 60.6% for v2 against 74.4% for v5 and 85.7% for v8. But the dominant term is
size - v2 specimens average 187 records, v5 specimens 2,069, an elevenfold difference.

### Why the tag result survives and this one does not

Both analyses have the same shape, so it matters that only one of them is sound. The
difference is **complete absence versus graded reduction**:

* `pixelprocessor` appears in **0 of 90** v2 specimens and 0 of 5 v3. At the rate it
  occurs in later files, a v2 specimen of average size would contain one with near
  certainty. Zero across 95 files is not something file size produces.
* The unnamed opcodes appear in 8% of v2 files and 64% of v5 files - present in both,
  merely rarer in the smaller. That is exactly the signature the size control reproduces
  without any version effect at all.

A threshold claim is safe when the early side is zero and the sample is large enough that
zero is surprising. It is unsafe whenever the early side is merely smaller, because
"smaller" is what a corpus of smaller files gives you for free. The four unnamed opcodes
are rare, not legacy, and `0x12` remains the only tag or opcode in this format for which
retirement is demonstrated.

## Output-to-record association: three hypotheses, one verification

Associating a graph output with the record that produces it was recorded as terminal on the
grounds that output uids appear only in the interface block. The better decoder made it
worth re-testing, and it survives - but the re-test sharpened one ISA name and eliminated
two structural guesses.

### `int 02` references inputs, never outputs

`int 02` was confirmed earlier to carry an interface uid in 99.94% of 148,760 instructions.
That test pooled inputs and outputs. Splitting them over 150 specimens:

    input uid    177,673   99.94%
    OUTPUT uid         0    0.00%
    neither          113    0.06%

Not one instruction in the corpus references an output uid. So the catalogue name `input
reference (u32 uid)` is right in both halves - it is a uid, and it is specifically an
*input* - and bytecode is closed off as a route to outputs.

### The interface block stores no record index

Dumping the words around the output uid array shows a bare run of `n_out` uids, immediately
followed by the input descriptors as (type, uid, value) triples, with the `u16 n_out`/`u16
n_in` pair directly before. There is no parallel array, no index, nothing between the uids
that could name a record.

### Position in the directory does not determine outputs

The instance-free pairs give ground truth: the source says which node feeds each output
bridge. If outputs were the last `n_out` records, the kinds would match. They do not:

| file | outputs fed by | last `n_out` records |
|---|---|---|
| `st_wood_fine_20` | transformation x7 | transformation x4, source x3 |
| `ie_processing` | pixelprocessor x2 | source x1, pixelprocessor x1 |
| `Metal_Vent_006` | source x6 | source x6 |

The cases that appear to work are the ones where every record has the same kind, so they
carry no information. Falsified.

### Sinks are the right idea and cannot be computed

What the ground truth does show is that outputs are fed by the graph's **sinks** - in
`st_wood_fine_20` all seven transformations and no bitmap, in `ie_processing` both
pixelprocessors. A sink is computable from the binary in principle: a record no other
record's edge slots reference. Testing `sink count == n_out` across all 382 specimens:

    sinks > n_out    303   79%
    exact             74   19%
    sinks < n_out      5    1%

**It fails, and the direction of failure is the explanation.** Sinks are over-counted four
times out of five, sometimes wildly - 1,006 sinks against 8 outputs in one 4,316-record
file. That is what happens when consumers are missed, and consumers are missed because not
every reference to a record travels through an edge slot: FX-Map tree nodes hold pointers
to records, and those pointers are consumers that the edge map does not see.

So the association is not merely unstored - it is not reconstructible either, because
recovering it needs complete consumer information and the format distributes references
across two mechanisms, only one of which is indexed. The terminal verdict stands, now with
a reason rather than an absence of evidence.

## `motionblur` had no edge slot, and the sink diagnostic found it

The failed sink test turned out to be a better instrument than the hypothesis it was
testing. Asking not "how many sinks are there" but **which record kinds become sinks**
isolates exactly the filters whose consumers are being missed:

| kind | records | sinks | sink rate |
|---|---|---|---|
| **`motionblur` `0x16`** | **6,219** | **4,452** | **72%** |
| `source` `0x20` | 746 | 240 | 32% |
| `shuffle` | 2,609 | 185 | 7% |
| `pixelprocessor` | 17,013 | 1,005 | 6% |
| `levels` | 33,822 | 1,187 | 4% |
| `blend` | 121,540 | 732 | 1% |
| `blur` | 5,901 | 13 | 0% |

Every filter sits between 0% and 7% except `motionblur` at 72%. A 32% rate for `source` is
expected - a source node with no consumer is a legitimately unused input - but nothing
explains three-quarters of a mid-graph filter being unreferenced.

The explanation is that **`0x16` has no entry in the edge map at all.** With 10,978 records
across 262 specimens it is the seventh commonest filter in the corpus, and its input slot
was never established. It contributed no edges, so nothing it consumed was ever marked as
used, and it never appeared as anyone's input either.

### The slot, and the trap next to it

Measuring backward-reference rate and resolution inheritance per slot over 6,219 records:

| slot | backward | inherits resolution |
|---|---|---|
| 1 | 100% | 61% |
| **2** | **100%** | **100%** |
| 5, 6, 7 | 0-1% | - |

**Slot 2 is the edge**: a backward record reference in every single record, inheriting its
parent's resolution in every single one. That is the strongest reading any edge slot in this
document has.

Slot 1 is the trap, and it is the same trap for the sixth time. It also references backward
in 100% of records - but its values are 5 (78%), 1 (18%), 6, 2 and 0, never anything else,
and it inherits resolution only 61% of the time. It is a small enumerated parameter, and a
small integer is almost always less than the record's own index. Recorded as an edge it
would have produced a plausible second input for a filter that takes one image.

The distinguishing test is inheritance, not backward-reference rate - exactly as it was for
`sharpen`, `hsl`, `curve`, `passthrough` and `pixelprocessor`. Backward-reference rate
cannot separate an edge from a small number; resolution inheritance can.

**Corrected edge map entry:** `0x16` / `0x17` -> slot 2. Slot 1 is an enumerated parameter,
dominated by the value 5.

### What fixing it did, and did not, do for output association

Re-running the sink test with `0x16` -> slot 2 in the edge map:

    without 0x16          exact 74/382 (19%)   over 303   under  5   median sinks/n_out 5.17
    with 0x16 -> slot 2   exact 80/382 (21%)   over 279   under 23   median sinks/n_out 2.80

The **median ratio of sinks to declared outputs nearly halves, from 5.17 to 2.80**, which
is the measurement that matters - it says the missing edge was a large fraction of the
missing consumers, as the 72% sink rate implied. Exact matches barely move, 19% to 21%.

So the correction is real and the association is still not recoverable: a typical file
still shows about three times as many apparent sinks as it has outputs, so consumers are
still being missed somewhere. The `under` column rising from 5 to 23 is a second sign that
the picture is incomplete - a file cannot genuinely have fewer sinks than outputs unless
two outputs share a producing record, which is possible but not at that rate.

The value of this round is therefore the edge slot, not the association. `0x16` is now
mapped and the corpus-wide consumer graph is materially more complete, but output-to-record
remains terminal for the reason given above: reference information is split across
mechanisms and the format indexes only one of them.

## Every edge-map entry, audited at once

Having been caught six times by the same small-integer trap and once by an entirely missing
entry, the map deserved a systematic pass rather than another one-filter fix. Over 200
specimens, for each documented (filter, slot): how often the slot holds a backward record
reference, how often the record then inherits that reference's resolution, and how often
the value is under 16.

### The core is solid

Nineteen entries hold a backward reference in **100%** of records and inherit resolution in
96-100%, with small values in 5% or fewer:

    gradient 1   blend 2   blend 3   warp 1   warp 2   emboss 2   emboss 3   blur 1
    motionblur 2   directionalwarp 2   directionalwarp 3   sharpen 1   hsl 1
    levels 2   normal 2   passthrough 1   distance 2   curve 1

That covers every commonly used filter's primary input, across 340,000-odd records. These
are not in doubt.

### Two entries fail the inheritance test for a known reason

| entry | backward | inherits | why |
|---|---|---|---|
| `transformation` slot 2 | 100% | 44% | `transformation` resizes by design |
| `fxmaps` slot 1 | 75% | 28% | an FX-Map composites onto its own canvas |

Both are already documented as cases where the inheritance test has no force. They are
listed here so the audit is complete rather than because they are newly doubtful.

### Four entries are weak and should be treated as provisional

| entry | backward | inherits | value < 16 |
|---|---|---|---|
| `warp` slot 3 | **5%** | 100% | 0% |
| `fxmaps` slot 4 | **15%** | 68% | 5% |
| `fxmaps` slot 5 | 31% | 52% | 18% |
| `transformation` slot 5 | 30% | 24% | **27%** |

`warp` slot 3 carries a reference in one record in twenty; whatever it is, it is not a
general input. `transformation` slot 5 is the weakest of the four on every axis at once -
low backward rate, low inheritance, and a quarter of its values under 16, which is the
beginning of the small-integer signature.

**A discrepancy worth stating.** `transformation` slot 5 was recorded earlier in this
document as "a backward reference in 73% of 9,808 records" and treated as a probable second
input. Measured here over 92,998 records it is **30%**. The earlier figure came from a much
smaller sample; the entry should be read as provisional at best, and possibly as the same
trap in a weaker form.

### What the audit does not find

No entry shows the full suspect signature - high backward rate, low inheritance, and
overwhelmingly small values together. The two remaining unmapped tags, `0x0A` and `0x12`,
have no entry to audit. The filters with no edge entry at all are `uniform`, `source` and
`text`, all of which are generators that take no image input, so their absence is correct
rather than a gap.

With `motionblur` added, **the edge map is now complete for every identified filter that
consumes an image**, and the periphery of second and third inputs is the only part that
remains uncertain.

## `transformation` slot 5 is not an edge

The audit flagged `transformation` slot 5 as the weakest entry in the map and noted that
this document reports it two ways - 73% backward over 9,808 records in one place, 30% over
92,998 in another. Both numbers are real, and resolving them removes the entry.

### Most transformation records have no slot 5

Measuring the header size of each record by where its first instruction block begins:

    transformation   16 B 58%   20 B 19%   32 B 10%   36 B 5%   40 B 4%   24 B 3%
                     records with room for a slot 5 (>= 24 B):  21%

Slot 5 occupies bytes 20-23, so a record must be at least 24 bytes to contain it. **Four
transformation records in five are too short.** Reading slot 5 on those lands in the
bytecode or the following record.

That resolves the discrepancy immediately: the 30% figure averages over everything, while
the 73% figure was measured on the subset large enough to have the slot. Neither
measurement was wrong; they were measuring different populations.

### And in the records that do have it, it is a small integer

Splitting on record size:

| group | records | backward | inherits | value < 16 |
|---|---|---|---|---|
| no room (< 24 B) | 24,572 | 0% | 31% | 0% |
| has slot 5 (>= 24 B) | 6,644 | **71%** | **21%** | **71%** |

The backward-reference rate and the small-value rate are **the same 71%**. Every apparent
reference is a number under 16, and resolution inheritance is 21% where a real edge runs
96-100%. This is the small-integer trap again - the seventh time in this document, and the
second time in two sections.

**`transformation` slot 5 is removed from the edge map.** `transformation` takes one image
input, at slot 2.

### The pattern is now specific enough to state as a rule

Across `sharpen`, `hsl`, `curve`, `passthrough`, `pixelprocessor`, `motionblur` and now
`transformation`, every false edge has had the same three properties:

1. a high backward-reference rate, usually near 100%;
2. resolution inheritance well below 90%, where genuine edges are at 96% or above;
3. values concentrated under 16.

Any two of those together are enough to reject a slot. The backward-reference rate on its
own has never once been sufficient to accept one, because a small integer is almost always
less than the record's own index - and in the `transformation` case the slot being read was
not part of the record at all.

**Before testing a slot, check that the record is long enough to contain it.** That step is
not in any of the earlier analyses in this document, and it should have been.

## The edge map re-audited in bounds, and what separates a rare edge from a false one

Applying the length check systematically - test a slot only in records long enough to
contain it - changes several of the verdicts reached one section ago, and shows that the
criterion I had been using was the wrong one.

| entry | records | in bounds | backward | **inherits** | value<16 |
|---|---|---|---|---|---|
| `blend` 2, `blend` 3 | 48,571 | 100% | 100% | **100%** | 1% |
| `gradient` 1, `levels` 2, `motionblur` 2 | - | 100% | 100% | **100%** | 1% |
| `blur` 1, `normal` 2, `passthrough` 1, `sharpen` 1 | - | 100% | 100% | **100%** | 0-4% |
| `directionalwarp` 2, 3 | 9,816 | 100% | 100% | **98-99%** | 1-5% |
| `warp` 1, `warp` 2 | 4,563 | 100% | 100% | **92-99%** | 2-12% |
| `distance` 2 | 333 | 100% | 100% | **100%** | 7% |
| **`distance` 3** | 333 | 97% | **71%** | **100%** | 5% |
| **`shuffle` 1, `shuffle` 2** | 1,285 | 100% | **54%, 47%** | **100%** | 2% |
| **`warp` 3** | 4,563 | 93% | **12%** | **100%** | 0% |
| `transformation` 2 | 35,027 | 100% | 100% | 46% (resizes) | 2% |
| `fxmaps` 1 | 7,140 | 100% | 74% | 28% (own canvas) | 15% |
| `shuffle` 3 | 1,285 | 93% | 82% | **81%** | **35%** |
| `fxmaps` 4 | 7,140 | 89% | 16% | **62%** | 6% |
| `fxmaps` 5 | 7,140 | 88% | 28% | **50%** | 15% |

### Rarity is not weakness

The previous section listed `warp` slot 3 among four "weak" entries because it carries a
reference in only 5% of records - 12% once out-of-bounds records are excluded. That was the
wrong reading. **Its inheritance rate is 100%.** Every time slot 3 does hold a reference,
the record inherits that reference's resolution, without exception. The same holds for
`distance` slot 3 (71% present, 100% inheriting) and `shuffle` slots 1 and 2 (about half
present, 100% inheriting).

These are **optional inputs**: absent in most records because the filter is usually used
with fewer inputs, and unambiguous whenever present. A slot that is empty most of the time
is not a doubtful slot.

So `warp` slot 3 and `distance` slot 3 are confirmed, not weak, and this corrects the
previous section's table. `warp` takes up to three inputs, `distance` two, `shuffle` up to
three.

### Inheritance is the only criterion that separates the classes

Ordering every entry by inheritance rate splits them cleanly, with nothing in between:

    genuine edges          92 - 100%     (fifteen entries)
    known-inapplicable     28 - 46%      (transformation 2, fxmaps 1)
    doubtful              50 - 81%       (fxmaps 4, fxmaps 5, shuffle 3)

Backward-reference rate ranges from 12% to 100% *within the genuine group*, so it cannot
separate anything. Small-value rate ranges from 0% to 15% in the same group. Only
inheritance divides the map, and it divides it with a gap.

**The three that remain doubtful** are `fxmaps` slots 4 and 5 and `shuffle` slot 3. The
`fxmaps` pair sits in the range where the inheritance test is known to lack force for that
filter, so they may be real and untestable rather than false. `shuffle` slot 3 at 81%
inheritance with 35% small values is the one genuinely ambiguous entry left in the map.

## Zero in an edge slot means "no input"

`shuffle` slot 3 was the last genuinely ambiguous entry in the edge map: 82% backward but
only 79% inheriting, with 35% of its values under 16. Looking at the values rather than the
summary shows what those small numbers are - **548 of 1,651 are exactly zero**, and nothing
else small appears in quantity.

Zero is a valid record index, so the test had been reading "no input" as "input is record
0" and then finding, correctly, that the resolutions do not match. Excluding zeros:

| entry | in bounds | zeros | backward | inherits |
|---|---|---|---|---|
| `shuffle` 3 | 1,651 | 33% | 74% | **100%** (was 79%) |
| `shuffle` 4 | 1,649 | 32% | **0%** | **0%** |
| `fxmaps` 4 | 10,217 | 5% | 10% | **94%** (was 62%) |
| `fxmaps` 5 | 10,126 | 17% | 16% | 76% (was 50%) |
| `blend` 2, `blend` 3 | 74,786 | **0%** | 100% | 100% |
| `shuffle` 1, `shuffle` 2 | 1,819 | **0%** | 56%, 45% | 99%, 100% |
| `distance` 3, `warp` 3 | - | **0%** | 71%, 7% | 100%, 100% |

Three verdicts change:

* **`shuffle` slot 3 is a confirmed edge.** 100% inheritance once zeros are excluded, in
  line with every other genuine slot. `shuffle` takes up to three inputs.
* **`shuffle` slot 4 is not an edge.** Of its non-zero values, **none** is a backward record
  reference. The slot holds something else entirely, and the apparent 32% "presence" was
  the zeros.
* **`fxmaps` slot 4 is probably an edge** at 94% inheritance - a rare second input rather
  than a doubtful one. `fxmaps` slot 5 at 76% remains unresolved.

### Where zeros appear

Zeros are absent from every mandatory slot - `blend` 2 and 3, `shuffle` 1 and 2 - and from
`distance` 3 and `warp` 3, which are optional but simply absent from short records rather
than zero-filled. They appear only in `shuffle` 3 and 4 and in `fxmaps` 1, 4 and 5.

So the format expresses an absent input two different ways: **a short record that does not
contain the slot at all**, and **a slot present but set to zero**. A reader must handle
both, and must not treat a zero as a reference to the first record.

That raises a question this corpus cannot settle: if zero means absent, a filter can never
name record 0 as its input. Either the compiler arranges that record 0 is never anyone's
input, or the encoding is biased in a way that the inheritance test would not reveal - and
since inheritance sits at 100% under the plain 0-based reading, it is not an off-by-one.
The practical rule stands regardless.

**With this, the edge map has one unresolved entry left**, `fxmaps` slot 5, down from three.

## The inheritance test, finally given a null

Resolution inheritance has been the deciding criterion for every edge-slot verdict in this
document, and it has never been given a baseline. If most records in a file share a
resolution, then any two records "inherit" by coincidence and the test proves nothing.

Sampling 400 random (record, earlier record) pairs in each of 121 specimens:

    random pairs sharing a resolution     50.8%
    per file: median 49%, 10th pct 31%, 90th pct 71%

**The null is a coin flip**, and the genuine edge slots sit at 92-100%. The margin is wide,
so the criterion is sound and every verdict resting on it stands. `transformation` slot 2 at
46% is at the null exactly, which is the correct reading for a filter that resizes by
design - it is not that inheritance fails there, it is that the slot carries no information
about resolution at all.

This also puts `fxmaps` slot 5 in perspective: 76% is meaningfully above a 51% null but far
below the 92% floor of confirmed edges. It is genuinely intermediate rather than a
borderline pass.

## An independent confirmation of the whole edge map, from the sources

Counting how many image inputs each source node declares - bounded to the node's own
`<connections>` element, before `<compImplementation>` - gives arity from the `.sbs` side
for every filter at once:

| filter | source arity | edge map |
|---|---|---|
| `blend` | 2 (67%), 3 (29%) | slots 2, 3 |
| `levels` | 1 (98%) | slot 2 |
| `blur` | 1 (98%) | slot 1 |
| `warp` | 2 (98%) | slots 1, 2 (+ rare 3) |
| `distance` | 1 (31%), 2 (68%) | slots 2, 3 |
| `shuffle` | 2 (94%) | slots 1, 2 (+ optional 3) |

Every one matches, including the optional slots: `blend`'s third input appears in 29% of
source nodes and `distance`'s second in 68%, which is why those slots are populated part of
the time rather than always. This is the edge map confirmed against ground truth for six
filters simultaneously, by a measurement that shares nothing with the inheritance test.

### The bound matters, and getting it wrong is instructive

Counting `connRef` over the whole `compNode` gives `fxmaps` nodes with 5,435 inputs. An
`fxmaps` node **embeds an entire FX-Map sub-graph** inside its implementation, so an
unbounded count sweeps up every internal connection of that sub-graph. This document already
warns about a version of this trap; it recurs here in a different form, and the fix is the
same - bound the region to the node's own header.

Bounded properly, `fxmaps` declares **3 inputs in 20% of nodes and 4 in 49%**.

### Which leaves `fxmaps` genuinely unresolved

The binary shows at most 1 backward reference among slots 1, 4 and 5 in 65% of records and
2 in 10% - far short of the 3 or 4 the sources declare. Slots 6, 7 and 8 inherit at 98-100%,
well above the null, which argues they carry real references. But those slots are documented
as pointers into the record body.

Both can be true, because **`fxmaps` records range from 10 to 72 bytes** and this document
already establishes that class-word bits 10-13 select a layout. Slot 6 of a 32-byte record
and slot 6 of a 72-byte record are not the same field, and a flat per-slot analysis averages
over layouts that should be separated. That is the next thing to do for this filter, and it
is why `fxmaps` remains the one filter whose inputs are not fully mapped.

## `fxmaps` slot meanings depend on the record layout

The flat per-slot analysis of `fxmaps` averaged over records from 10 to 72 bytes. Grouping
by header size first - and remembering the 51% null for inheritance - separates them
cleanly.

**52-byte records (1,220):**

    slot 1    39% backward, 21% inherits
    slot 3    65% backward, 100% inherits    <- edge
    slot 4    65% backward, 100% inherits    <- edge
    slot 5    67% backward, 100% inherits    <- edge
    slot 6    65% backward, 100% inherits    <- edge
    slot 7    65% backward, 100% inherits    <- edge
    slot 8    67% backward, 100% inherits    <- edge
    slots 9-12   0%

**Six consecutive slots with identical behaviour** - the same backward rate to within two
points, and 100% inheritance in every one. That is an array of input references, not six
unrelated fields.

**32-byte records (1,761):** only slot 5 shows the pattern, at 14% backward and 98%
inheriting, with 51% of its values zero. Slot 1 behaves as it does everywhere - 77%
backward, 23% inheriting.

**24-byte records (753):** no slot inherits above the null. Slot 1 at 94%/26% and slot 5 at
62%/21%.

**10-byte records (671):** slot 1 only; there is nothing else in the record.

### What this settles and what it does not

It settles the contradiction from the previous section. Slots 6, 7 and 8 appeared to inherit
at 98-100% *and* to be documented as body pointers, and both readings were right about
different records: in the 52-byte layout those slots hold input references, and in other
layouts the same offsets hold pointers into the record body. **A slot index is only
meaningful together with the record's layout**, which this document establishes for six
filters via class-word bits 10-13 but had not applied to the slot analysis itself.

It also explains the arity shortfall. The sources declare 3 or 4 inputs for 69% of `fxmaps`
nodes, while a flat reading of slots 1, 4 and 5 finds at most 1 in 65% of records. The
52-byte layout carries six input slots, and averaging it against the 10-byte layout - which
has room for exactly one - produces a number that describes neither.

What it does not settle is `fxmaps` slot 1, which holds a backward reference in 39-94% of
records depending on layout and inherits at 21-31% throughout, always near or below the
null. It is the filter's documented primary input and the inheritance test has no force for
it, so its status is unchanged: real on other evidence, untestable by this one.

**Methodological consequence.** Every per-slot table in this document that pools records of
different sizes for the same filter is measuring a mixture. It happens not to matter for
filters with one dominant layout - `blend` is 24 B in 63% of records and 20 B in 33%, and
its slots 2 and 3 read 100%/100% either way - but for `fxmaps`, whose layouts differ in what
they contain rather than only in how much, pooling destroys the signal.

## A layout-aware sweep of every filter finds one new slot, and one genuine puzzle

Having found that `fxmaps` hides six input slots inside one layout, the same test was run
across every filter and every layout: at least 20% backward references among non-zero
values, at least 92% inheritance against the 51% null, and not already in the edge map.

Across 17 filters and all their layouts, **exactly one candidate appears**:

    blend, 28-byte records, slot 5    37% backward, 100% inherits, 1,170 records

So the map was not hiding much. `fxmaps` was the exception rather than the pattern, which
is consistent with it being the only filter whose layouts differ in *what* they contain.

### `blend` slot 5 is a third input, in one layout

`blend` by layout:

| size | share | slot 2 | slot 3 | slot 5 |
|---|---|---|---|---|
| 24 B | 64% | 100/100 | 100/100 | 3% backward |
| 20 B | 33% | 100/100 | 100/100 | - |
| 18 B | 2% | 100/100 | 100/100 | - |
| **28 B** | **1%** | 100/100 | 100/99 | **37% / 100%** |

Only the 28-byte layout carries it, and only in 37% of those records. `blend` takes
foreground, background and an optional mask, and the sources confirm the shape - 67% of
source `blend` nodes declare two connections and **29% declare three**.

The counts do not reconcile cleanly: 29% of source nodes have a third connection while only
1% of binary records are 28 bytes. So the third connection is usually *not* an image edge -
most likely the opacity input compiled to a parameter program rather than a record
reference, which is what this document already observes for driven parameters generally.
The 28-byte layout is the case where it stays an image.

### `blend` slot 1 is not explained

Every `blend` record, in every layout, has a slot 1 that holds a backward record reference
in 84-94% of cases. It is not the small-integer trap: over 55,416 records its values are
mid-range (16-999) in 99.3% of cases, with fewer than 250 small values in total. It is
distinct from slots 2 and 3 in 50,286 of 50,300 records, and **systematically smaller than
slot 2** - 50,106 times against 200 the other way.

But it inherits resolution only 55-70% depending on layout. That is above the 51% null and
far below the 92-100% of confirmed edges, and it sits in the same intermediate band as
`fxmaps` slot 5.

A slot that is always present, always a valid earlier record, never small, and consistently
ordered before the known inputs does not look like a parameter. It looks structural - a link
into a list or chain rather than a data input, which would explain the ordering constraint
and the indifference to resolution. This document records chain entries elsewhere in the
body; that is the obvious thing for it to be, and testing that is the next step.

What can be said now is narrower: **`blend` slot 1 references an earlier record in 94% of
105,539 records and its meaning is not established.** It is the largest single unexplained
field in the record format by volume, and it has been sitting in plain sight behind an
inheritance test that was never the right instrument for it.

## `blend` slot 1 characterised: a reference, but not an input

The previous section left `blend` slot 1 as the largest unexplained field in the record
format - a backward record reference in 94% of 105,539 records, with 60% resolution
inheritance sitting between the 51% null and the 92% floor for real edges. Four
measurements settle what it is not.

**It is a real reference, not a mistaken small integer.** Over 55,416 records its values are
in the range 16-999 in 99.3% of cases, with fewer than 250 small values in total. In
`PavingStonesSubstance003` the 1,743 blends draw slot 1 from **28 distinct values**, every
one of which is a valid record index pointing at a real `levels`, `blend` or
`transformation` record.

**It is not a chain link.** A chain would reference each target once. Slot 2 and slot 3 do
almost exactly that - 98-99% of their targets have a single referrer. Slot 1 has **51% of
its targets referenced five or more times**, one of them 472 times in a single file.

**It is not a data input.** This is the decisive one. Comparing each slot's target
resolution against the record's own, over 50,034 blend records:

    slot 2    same resolution   100%
    slot 3    same resolution   100%
    slot 1    same resolution    50%      <- the null is 50.8%

Slot 1's resolution agreement is **chance, to within a percentage point**. Slots 2 and 3
agree without exception. An image feeding a blend must share its resolution - that is what
the other two slots demonstrate 50,034 times - so whatever slot 1 names, the blend is not
compositing it.

**And it is not redundant with them.** All three slots hold distinct values in 99.3% of
records; slot 2 equals slot 3 in 0.6%.

### What that leaves

`blend` takes its two image inputs at slots 2 and 3, plus an optional third at slot 5 in
the 28-byte layout. Slot 1 is a separate mechanism: a reference to a small set of earlier
records - typically 4% as many distinct targets as there are blends - shared by hundreds of
records at a time, with no resolution relationship to the referrer.

High fan-out onto a narrow band of early records, with no data dependency, is the shape of
a reference to something *shared*: a prototype, a scope, or an entry in a table that the
record belongs to rather than consumes. The corpus supports that description and does not
distinguish between those readings.

The useful outcome is negative and firm: **slot 1 must not be treated as an edge.** A reader
building a node graph from `blend` records should use slots 2 and 3, and slot 5 where the
layout provides it. Including slot 1 would add 105,539 spurious edges to the corpus graph,
each of them pointing at a record the blend never reads.

## The shared reference is a general mechanism, and it occupies slot 1 of eight filters

`blend` slot 1 turned out to be a reference that is not an input. Applying the same two
measurements - resolution agreement against the 51% null, and the ratio of distinct targets
to total references - to slot 1 of every filter splits them into two populations with
nothing in between.

| filter | records | backward | inherits | distinct / refs |
|---|---|---|---|---|
| `passthrough` | 423 | 100% | **100%** | **1.00** |
| `blur` | 1,858 | 100% | **100%** | **0.99** |
| `warp` | 4,563 | 100% | **100%** | **0.99** |
| `gradient` | 2,297 | 100% | **100%** | **0.89** |
| `shuffle` | 1,285 | 54% | **100%** | **0.51** |
| | | | | |
| `levels` | 14,547 | 92% | 57% | 0.15 |
| `fxmaps` | 7,140 | 71% | 27% | 0.11 |
| `blend` | 48,571 | 91% | 56% | 0.09 |
| `motionblur` | 3,919 | 100% | 69% | 0.06 |
| `distance` | 333 | 97% | 67% | 0.06 |
| `transformation` | 35,027 | 58% | 38% | 0.05 |
| `directionalwarp` | 9,816 | 100% | 63% | 0.03 |
| `pixelprocessor` | 7,443 | 99% | 23% | 0.02 |

The upper group inherits resolution in **100%** of records and its references are nearly
one-to-one. The lower group inherits at 23-69% - at or near the null - and its references
are shared ten to fifty times over. No filter falls between 0.15 and 0.51, or between 69%
and 100%.

**The upper group is exactly the set of filters whose edge map lists slot 1 as the input.**
That is a consistency check the map passes without adjustment: where this document says
slot 1 is an edge, slot 1 behaves like an edge on two measurements it was never tested
against.

**The lower group is exactly the set whose first input is at slot 2.** `blend`,
`transformation`, `levels`, `directionalwarp`, `motionblur`, `distance` and
`pixelprocessor` all take their image input at slot 2 in the map, and all of them carry
this other thing at slot 1.

So the format has a **per-record reference to a shared earlier record**, occupying slot 1
in the filters that do not use slot 1 for data. It is present in the majority of records in
the corpus - over 120,000 in this sample alone - and this document has never accounted for
it.

### This reclassifies `fxmaps` slot 1

`fxmaps` slot 1 sits squarely in the lower group: 27% inheritance, 0.11 distinct ratio.
It has been recorded as the filter's primary input, with its failure to inherit excused on
the grounds that an FX-Map composites onto a canvas of its own size.

That excuse is no longer needed, and it was probably wrong. The simpler reading is that
`fxmaps` slot 1 is the same shared reference as `blend` slot 1, `levels` slot 1 and the
rest - which explains the inheritance failure without a special case, and explains the
heavy fan-out that a primary input would not produce. It also fits the layout finding: the
52-byte layout carries its real inputs at slots 3-8, and the arity shortfall was never
resolved on the assumption that slot 1 was one of them.

**`fxmaps` slot 1 is reclassified from primary input to shared reference.** Its actual
inputs are the layout-dependent slots, and how many a short-layout `fxmaps` record has is
now genuinely open rather than answered by slot 1.

### What the shared reference is not

Six tests, all negative, bound it fairly tightly. Over ~120,000 records carrying it:

| hypothesis | test | result |
|---|---|---|
| an image input | resolution agreement | **50%** - the null is 50.8% |
| a chain or list link | referrers per target | 51% of targets have 5+ referrers |
| a region or scope marker | run length in directory order | median **1**; 97% of targets have scattered referrers |
| a prototype of the same kind | target's filter tag | **74%** point at a different kind |
| one global structure | targets common to all filter kinds | **0**, in every file measured |
| a specially marked record | class-word bits of targets vs others | every bit within 1.6x of base rate |

What survives is a positive description without a name:

* it names a **valid earlier record**, not a small integer and not a pointer;
* targets sit **at the very start of the directory** - median position 0.03, 90th
  percentile 0.16 - and cluster in a narrow band, in one 4,311-record file all 28 distinct
  values fall between 258 and 295;
* there are about **47 distinct targets per file** regardless of whether the file has 100
  records or 4,000;
* a single target can be named by **hundreds of records** - 472 in one case - and its
  referrers are spread throughout the directory;
* the target is an ordinary filter record, usually of a different kind than the referrer,
  with nothing in its class word to distinguish it.

A small, early, fixed-size set of ordinary records that most of the file points into, with
no data dependency and no positional structure, reads like a table of shared context -
something each record belongs to rather than reads from. The corpus cannot say which.

**For a reader the operational conclusion is unchanged and firm:** slot 1 of `blend`,
`transformation`, `levels`, `directionalwarp`, `motionblur`, `distance`, `pixelprocessor`
and `fxmaps` is not an edge and must be excluded when reconstructing the node graph. It is
now the best-characterised unknown in the format rather than an unnoticed one.

## The corrected edge map, end to end - and a correction to the zero rule

Several entries have changed: `motionblur` slot 2 added, `transformation` slot 5 removed,
`pixelprocessor` moved to its arity-driven input list, `fxmaps` slot 1 reclassified and its
layout-dependent slots 3-8 used instead. Measuring the whole map against ground truth,
old against new:

| edge map | instance-free recall | precision | containment, all pairs |
|---|---|---|---|
| original | 76.5% | 86.7% | 73.7% |
| corrected, zero treated as absent | 76.5% | 96.3% | 75.7% |
| **corrected, zero treated as record 0** | **100.0%** | **97.1%** | **76.8%** |

The corrections are worth about ten points of precision. But the third row is the
interesting one, because it contradicts something this document stated as a rule.

### Zero is a record reference in mandatory slots

The section "Zero in an edge slot means 'no input'" concluded that a reader must not treat
a zero as a reference to the first record. Measured end to end, **excluding zeros costs 24
points of recall** - it drops from 100% to 76.5% - because in small graphs record 0 is
routinely a real input, and excluding it deletes those edges.

Both measurements are correct and they concern different slots:

* In **optional slots** where zeros are common - `shuffle` slot 3 at 33% zeros, `fxmaps`
  slots 4 and 5 at 5-17% - a zero marks an absent input. Excluding them raises `shuffle`
  slot 3's inheritance from 79% to 100%, which is real.
* In **mandatory slots** a zero is a genuine reference to record 0. Those slots measure 0%
  zeros corpus-wide, but that statistic is dominated by large files: in a four-record graph,
  a record referencing record 0 stores a zero, and the instance-free pairs are exactly such
  small graphs.

So the discriminator is **the slot, not the value**. My earlier statement generalised from
optional slots to all of them, and the end-to-end test caught it because recall is sensitive
to deleted edges in a way that a per-slot inheritance rate is not.

**Corrected rule for a reader:** treat a zero as record 0 in a filter's mandatory input
slots, and as "absent" only in the optional slots where zeros occur at percent-level rates -
`shuffle` slot 3, `fxmaps` slots 4 and 5. Defaulting to "record 0" is the safer error: it
costs a little precision, while defaulting to "absent" costs a quarter of all edges.

### Where the map now stands

    instance-free recall     100.0%    every edge the author drew is recovered
    instance-free precision   97.1%    almost nothing spurious is added
    containment, all pairs    76.8%    the rest is inlining, culling and constant folding

Recall of 100% is the number that matters for an importer: on graphs where source and binary
correspond one-to-one, **the reconstructed node graph now contains every edge the author
drew**, with a 3% residue of extra edges that are compiler-inserted rather than wrong.

### The precision residue is a single edge

Listing every disagreement between reconstructed and authored graphs across all nine
instance-free pairs:

    SubstanceDesigner__color    extra: uniform -> shuffle  x1
    (nothing else, in any file)

That is the whole of the 2.9%. It is not an error in the map: `SubstanceDesigner__color` is
the specimen already documented as having 8 filter nodes in source and 17 records in the
binary, the excess being nodes the compiler inserts rather than nodes the artist placed. The
extra edge is a compiler-inserted `uniform` feeding a `shuffle`.

So on graphs where source and binary correspond one to one, **the reconstruction is exact**:
every authored edge recovered, and one compiler-inserted edge added across the entire
instance-free corpus. For an importer this is the load-bearing result of all the edge-slot
work - the node graph read out of a `.sbsar` is the graph the artist drew.

The qualifier that matters is scope. Nine files with no `compInstance` is a small ground
truth, and it is the only ground truth available: every other paired file inlines library
graphs whose sources are excluded. The containment test over all 102 pairs, at 76.8%, is the
weaker but broader check, and its shortfall is accounted for by inlining, `passthrough`
culling, `grayscaleconversion` relabelling and `valueprocessor` producing no record.

## Constant operands confirm operation names semantically

Arity confirms an operation's shape but not its meaning: `min` and `max` both take two
floats. A different signal is available and had not been used - **which constants are fed to
each operation**. An operation's typical constant operand is a fingerprint of what it is
for.

Collecting every float constant that feeds each operation, over 100 specimens:

| op | catalogue | n | commonest constant operands |
|---|---|---|---|
| float `2E` | `cartesian` | 4,392 | 0 (11%), **1.5708** (10%), **3.1416** (10%), **4.7124** (8%), **5.4978** (7%) |
| float `13` | `sub` | 86,088 | **1 (91%)**, 4 (2%), 0.5 (2%) |
| float `15` | `div` | 51,505 | 1 (69%), 16 (6%), 0.5 (4%), **0.6931** (2%) |
| bool `1F` | `gt` | 27,431 | **0 (88%)**, 0.5 (9%), 1 (2%) |
| float `31` | `max` | 5,274 | **0 (89%)**, 1 (3%) |
| float `30` | `min` | 21,837 | 0 (76%), **1 (19%)** |
| float `14` | `mul` | 120,289 | 0.5 (63%), 1 (19%), 0.25 (4%) |
| float `0D` | construct vector | 116,163 | 0 (54%), 1 (46%) |
| float `32` | `rand` | 9,555 | 1 (82%), 10 (7%), **6.28** (5%) |

Three of these are decisive.

**`cartesian` is confirmed by its constants being angles.** 1.5708 is pi/2, 3.1416 is pi,
4.7124 is 3pi/2, 5.4978 is 7pi/4. A quarter of all constants feeding this operation are
exact quarter-turns. No other operation in the corpus shows this, and nothing but an
angular operation would consume them. `rand` taking 6.28 - two pi - at 5% is the same signal
in weaker form.

**`sub` is confirmed by `1 - x`.** Ninety-one percent of the constants feeding it are
exactly 1.0, which is the invert idiom that dominates image maths. `add` by contrast takes a
spread of offsets (1, 0.5, 0.25, 0.75, 0 - none above 37%), which is what an addition looks
like and what a subtraction used for inversion does not.

**`div` reveals a lowering.** Its third commonest constant is **0.6931**, which is ln 2.
`log2(x)` computed as `ln(x) / ln(2)` is exactly what this document already records under
lowering - `pow` and `log2` are not instructions - and here is the divisor itself, appearing
1,000-odd times in the corpus.

### Where it fails, and honestly

The test was designed to separate `min` from `max`, which arity cannot. It does not.
`max` takes 0 in 89% of cases, which fits `max(x, 0)` clamping from below. But `min` also
takes 0, in 76% of cases, where `min(x, 1)` was expected; 1.0 accounts for only 19%. The
distributions differ in the right direction and by the right sign - 19% against 3% for the
constant 1 - but the margin is not enough to call it, and `min(x, 0)` is not an idiom that
explains the rest.

So the pair remains distinguished only by the catalogue's structural reasoning. What this
method does establish is `cartesian`, `sub` and the `div`-based `log2` lowering, on evidence
entirely independent of arity, position in the operation matrix, and every counting
argument.

### `min` and `max` settled by the clamp idiom

The constant-operand test could not separate them because both take 0 most of the time.
Nesting settles it. A clamp to the unit interval is `min(max(x, 0), 1)`, and the two
operations appear nested in exactly that shape:

| outer | inner | count |
|---|---|---|
| `0x30` with constant **1** | `0x31` with constant **0** | **3,758** |
| `0x31` with constant **0** | `0x30` with constant **1** | 262 |
| `0x30` const 1 | `0x31` const -1 | 105 |
| others | | < 120 each |

Both of the top two rows are clamps - `min(max(x,0),1)` and `max(min(x,1),0)` - and **both
assign the same meanings**: the operation that takes 1 is `min`, the operation that takes 0
is `max`. Over 4,000 nested pairs agree, and the reading matches the catalogue without
change.

    float 0x30 = min      confirmed
    float 0x31 = max      confirmed

The third row is the same idiom on the signed range, `min(max(x,-1),1)`, clamping to
[-1, 1] as normal maps require.

This is the first identification in this document made by **recognising an idiom** rather
than measuring a property. It works where the property tests fail because a clamp constrains
the two operations *relative to each other*: whichever one is paired with 0 must be the one
that raises its argument, whatever it is called. That is a stronger constraint than either
operation's constant distribution taken alone, and it is available wherever a language has
composite idioms - which suggests looking for others: `1 - x` for invert is already visible
in the `sub` constants, and a lerp, a smoothstep or a normalise would each have a
recognisable shape.

## The operation adjacency map, and the idioms it exposes

Extending the idiom method: for every instruction, which operation produced each of its
operands. This had never been measured, and it corroborates several names on semantic
rather than structural grounds.

### Pairs

| producer -> consumer | count | share of consumer's operands |
|---|---|---|
| `sub` -> `abs` | 46,397 | **97%** |
| `read system variable` -> `samplecol` | 39,488 | **92%** |
| `gt` -> `ifelse` | 62,268 | **79%** |
| `sequence` -> `sequence` | 51,713 | 85% |
| `swizzle` -> `ifelse` | 54,548 | 69% |
| `mul` -> `neg` | 46,288 | 65% |
| `input reference` -> `add` | 62,957 | 62% |

**`abs` takes its argument from `sub` 97% of the time.** `abs(a - b)` is a magnitude of
difference, and essentially every `abs` in the corpus is one. That confirms both names at
once: a unary operation fed almost exclusively by a subtraction is an absolute value, and a
binary operation feeding one is a difference.

**`samplecol` takes its argument from `read system variable` 92% of the time.** The system
variable is documented as `$pos`. Sampling a colour at the current position is what a pixel
processor does, and the operand relationship says so directly.

**`gt` feeds `ifelse` 79% of the time**, which is the shape of a conditional and confirms
the pair as comparison and select.

### Three-operation chains

| chain | count |
|---|---|
| `swizzle` -> `sub` -> `abs` | 37,069 |
| `read` -> `mul` -> `add` | 19,976 |
| `sub` -> `gt` -> `ifelse` | 19,263 |
| `swizzle` -> `sub` -> `exp2` | 19,380 |
| `gt` -> `ifelse` -> `set` | 19,740 |

`read -> mul -> add` is an affine transform of the sampling position - `$pos * scale +
offset` - which is the single most common thing a per-pixel program does, and it appears
20,000 times in 35 specimens. `sub -> gt -> ifelse` is a thresholded comparison of a
difference. `gt -> ifelse -> set` is a conditional assignment.

### What did not appear

This document records that `normalize` is lowered to `dot`/`sqrt`/`div`. **That chain does
not appear** among the common three-operation sequences in this sample. It may simply be
rare - `normalize` is not a frequent operation in image maths - but the lowering is recorded
here as unverified by adjacency, in contrast to the `log2`-via-`div` lowering, which the
constant 0.6931 confirms directly.

The general point is that an instruction set can be read the way a natural language is:
individual words are hard to pin down in isolation, but collocations give them away. Arity
gave the parts of speech, constants gave a few of the nouns, and adjacency gives the
phrases.

## The unnamed opcodes, by collocation

The four unnamed operations are leaves carrying immediates, and two hypotheses about them
have already been falsified. Collocation gives a third line of evidence.

### The immediate trap, on the consumer side this time

The first run reported that `int 38` is "consumed by constant 63%" and that its result is
consumed 293% of the time. Both are impossible: a constant takes no operands, and a result
cannot be consumed more often than it exists.

The cause is the same confusion that broke the DAG matcher: a constant's 32-bit immediate is
stored as two `u16` tokens, and those tokens numerically collide with small value numbers.
Every constant in a block therefore appears to "consume" whichever low-numbered results
happen to match its bit pattern. Excluding the operations documented as carrying immediates -
constants, `swizzle`, `set`, and the loop cap - brings consumption to a sane 37-55%.

**This is the third distinct analysis in this document to be corrupted by treating
immediates as operands**, after the arity signature and the in-degree measure. The rule is
worth stating plainly: *in this ISA an operand token is only a value number if its
instruction is not one of the immediate-carrying forms.*

### What consumes them

| opcode | instances | consumed by | alongside |
|---|---|---|---|
| `int 38` | 409 | **`samplecol` 59%**, `samplelum` 12% | `add` 38%, constant 33% |
| `int 08` | 267 | **`samplecol` 60%**, `samplelum` 7% | `add` 45%, constant 21% |
| `bool 08` | 293 | **`samplecol` 48%**, `samplelum` 8% | `read` 17%, `samplecol` 17% |
| `int 3D` | 196 | `type conversion` 36%, `sequence` 35% | **`input reference` 50%** |

Three of the four behave alike: **roughly half of everything they produce is consumed by a
texture sampler**, and they occur alongside the `add` that computes the sampling position.
A leaf that carries an immediate, is consumed by `samplecol`, and sits next to a position
calculation is shaped like a **selector for which image to sample**.

That reading is suggestive rather than established, and the reason is visible from the other
side. Looking at what feeds `samplecol`, its operands come overwhelmingly from `add` (84% of
operand 0) and `read system variable` (91% of operand 1); the unnamed opcodes are a small
minority of its inputs. So they are at most a *rare variant* of sampler-source
specification, used in a few hundred instructions where the common form is something else.

`int 3D` is not part of this group at all. It is consumed by type conversions and
`sequence`, and half its neighbours are `input reference` instructions - a different context
entirely, and one this analysis does not resolve.

**Status: unchanged but better bounded.** All four remain unnamed. Three now have a probable
domain - texture sampling - and one does not. At roughly 1,100 instructions across 200
specimens they remain 0.02% of the corpus.

## Which operand tokens are immediates, measured rather than assumed

Three analyses in this document have been corrupted by treating an immediate as a value
number, so the question deserves a measurement instead of a list. For every operation and
every token position, how often that token is a valid back-reference - and, when it is,
how concentrated the producing operation is.

| operation | tokens | position | n | back-ref | producers at that position |
|---|---|---|---|---|---|
| `input reference` | 2 | 0 | 72,489 | **0%** | - |
| `input reference` | 2 | 1 | 72,489 | **0%** | - |
| `read system variable` | 1 | 0 | 26,700 | **22%** | scattered |
| `swizzle` | 2 | 0 | 145,251 | 99% | value |
| `swizzle` | 2 | 1 | 145,251 | **71%** | the mask |
| `samplecol` | 2 | 0 | 32,688 | 99% | **`add` 82%** |
| `samplecol` | 2 | 1 | 32,688 | 98% | **`read` 88%** |
| `mul`, `sub`, `add`, `div`, `min`, `ifelse`, `construct` | - | all | - | 99-100% | genuine |

**Back-reference rate alone is not enough**, for the reason that has recurred throughout:
a small immediate is almost always less than the instruction's own index. The second signal
is what sits at the referenced position. A genuine operand has a *concentrated* producer
distribution - `samplecol` position 1 draws from `read system variable` 88% of the time -
while an immediate points wherever its bit pattern happens to land, giving a scattered one.

On that basis: `input reference` carries a 32-bit immediate in both tokens, confirming the
uid finding from the other direction; `read system variable` carries a one-token immediate
selecting which variable; `swizzle` carries its mask in **token 1**, with token 0 the value.

### This corrects an earlier explanation

The source-versus-binary arity comparison found three disagreements - `set`, `samplecol`
and `samplelum`, each showing one more input in the binary than the source declares - and
attributed all three to immediate contamination.

That is wrong for `samplecol`. **Both of its tokens are genuine operands**: a position
computed by `add`, and a value from `read system variable`. The binary really does pass two
things to the sampler where the source node declares one connection, because the position
is implicit in the source language and explicit in the compiled code.

### And it corrects a correction

My first attempt at this audit stripped the last **two** tokens from every immediate-carrying
operation, on the model of a 32-bit constant. Applied to `samplecol`, whose tokens are both
operands, that deleted the entire relationship and made `read -> samplecol` appear to
collapse from 45% to 6% - which I briefly took as evidence that the published finding was
contaminated. It was not; the correction was.

The lesson is narrow and practical: **immediate width is per-operation and must be measured,
not inferred from the commonest case.** Constants carry two tokens, `swizzle` and `read
system variable` carry one, and `samplecol` carries none.

### A detector for immediates, and its limits

Making the concentration signal quantitative - the entropy of the producer distribution at
each token position - gives a usable detector, but only when read *within* an operation
rather than against a fixed threshold.

| operation | pos | back-ref | producer entropy | reading |
|---|---|---|---|---|
| `read system variable` | 0 | **21%** | 2.19 | immediate |
| `swizzle` | 0 | 99% | 2.62 | operand |
| `swizzle` | 1 | **70%** | **2.96** | the mask |
| `set` | 0 | 100% | 2.42 | operand |
| `set` | 1 | 98% | **3.30** | probably the slot |
| `samplecol` | 0 | 98% | 1.04 | operand |
| `samplecol` | 1 | 99% | 0.84 | operand |
| `sub` | 0, 1 | 99% | 2.74, 2.44 | both operands |

Within each operation the immediate is the position with the **higher entropy and lower
back-reference rate than its siblings**. That ranking is correct wherever it can be checked:
`swizzle` position 1 is the mask, and its 70% against 99% plus 2.96 against 2.62 says so on
both axes.

Absolute thresholds do not work. `swizzle` position 1 has entropy 2.96 and is an immediate,
while `sub` position 0 has 2.74 and is an operand; the numbers overlap across operations
because the baseline distribution of producers differs by context.

`set` is the case the detector cannot close. Its position 1 has clearly higher entropy
(3.30 against 2.42) but a back-reference rate of 98%, so only one of the two signals fires.
The catalogue's reading - that `0x07` carries a variable slot as an immediate - is
consistent with the entropy but not confirmed by the back-reference rate, and a slot number
small enough to look like a value number is exactly the case that defeats this test.

**Net position on immediates:** confirmed for `constant` (two tokens), `input reference`
(two tokens, 0% back-reference), `read system variable` (one token), and `swizzle` (token 1).
Confirmed *absent* for `samplecol` and `samplelum`, whose tokens are all genuine operands.
Unresolved for `set`, where the catalogue's claim stands on structural grounds and this
measurement neither supports nor contradicts it decisively.

## The two unparseable manifests: the cooker does not escape ampersands

The corpus validator has reported "manifests unparseable: 2" since it was written, without
an explanation. The cause is a defect in the Substance cooker.

`advanced_transform_colour.xml` fails at line 8, column 33:

    <guigroup identifier="Scale & Tile" label="Scale & Tile"/>

The `&` is raw. XML requires `&amp;`, and a conforming parser must reject the document.
The name is user-authored - an artist called a parameter group "Scale & Tile" - and the
cooker copied it into an attribute value without escaping.

Scanning all **584 manifests** in the corpus for ampersands that do not begin a valid entity:

    manifests scanned                      584
    containing an unescaped &                2   (0.34%)
    failing to parse                         2   the same two

Both are from one author, with nine occurrences each, and every one is in a `guigroup`
identifier or label, or in an `inputgui` label - always a display string the artist typed.
No other entity is mishandled: no bare `<`, `>` or quote appears anywhere in 584 files.

**Practical consequence for a reader.** The `.xml` manifest inside a `.sbsar` is not
guaranteed to be well-formed XML. A strict parser will fail on roughly one package in three
hundred, and the failure is not in the binary assembly - which parses perfectly in both
cases - but in the human-readable sidecar. Either pre-escape bare ampersands before
parsing, or fall back to a lenient parse when a strict one fails.

It is worth noting which way the robustness lies: the *binary* format has been decoded to
97% of its bytes across 382 specimens without a single malformed file, while the *XML*
sidecar, the part meant to be easy to read, is the part that is occasionally invalid.

## The manifest and the binary interface correspond exactly

The `.xml` manifest has been used in this work only as a validation aid. It carries more
than that, and the correspondence is exact.

Comparing the output uids the manifest declares against the output uid array in the
assembly, over **582 packages**:

    same uid set                                   582 / 582   (100%)
    manifest declaration order == binary order     429         (74%)
    same set, binary sorted uid-ascending           98         (17%)
    same set, multi-graph reordering                55          (9%)

**Not one package** has an output in the manifest that is missing from the binary, or the
reverse. The ordering follows the manifest's declaration order three times in four, and is
uid-ascending in most of the rest; the residue is multi-graph packages where the graphs are
emitted in a different order than declared - `ie_pcloud` has twenty graphs and reorders
them.

### What this makes possible

The assembly's interface block gives output uids and nothing else - no names, no types, no
indication of what a channel is for. The manifest gives all of it:

    <output uid="2812803637" identifier="basecolor" type="5" format="0"
            width="256" height="256" dynamicsize="yes">
      <outputgui label="Base Color" group="Material" typegui="image">
        <channels><channel names="baseColor" colorspace=""/></channels>

Since the uid sets are identical in every package, **every binary output can be named** by
joining on uid. For an importer this is the difference between "output 3 of 7" and "base
colour", and it needs no inference at all - the join is exact.

The same applies to inputs, which the manifest declares with identifier, type, default
value and GUI widget, and which the binary carries as `(kind, uid, value)` triples.

### And it partitions the interface by graph

The manifest nests outputs inside `<graph>` elements. Records cannot be attributed to a
graph - that remains terminal - but **outputs and inputs can**, directly and without
inference, for the 57 multi-graph packages in the corpus.

That is worth stating precisely because this document has recorded multi-graph membership
as unrecoverable. The unrecoverable part is which *records* belong to which graph. Which
*outputs* and *inputs* belong to which graph is declared, in a file shipped inside every
`.sbsar`.

### One more thing the manifest declares

Each input carries an `alteroutputs` attribute listing the output uids it affects:

    <input uid="3575741444" identifier="$outputsize" type="8" default="8,8"
           alteroutputs="2812803637" alternodes="0"/>

This is a dependency relation from parameters to outputs that the binary does not appear to
encode anywhere. A reader wanting to know which outputs must be recomputed when a parameter
changes has it declared, and does not need to derive it from the record graph.

## Using `alteroutputs` to attribute outputs to records: sound in principle, blocked in practice

The manifest states which inputs affect which outputs. That is a constraint on the record
graph: if changing input U alters output O, then U must lie upstream of whichever record
produces O. Intersecting that constraint over all inputs should identify each output's
producing record, which would settle a question recorded here as terminal.

Implemented - manifest gives output -> {altering input uids}; the binary gives each record's
directly referenced input uids from the `int 02` immediates in its bytecode; propagate
upstream through the edge map; match each output's required set against the sinks - it
returns **zero attributions in 61 single-graph packages**, not even a partial one.

Zero is usually an instrument failure rather than a result, and it is here. The
intermediates show why:

| package | records | outputs | sinks | `alteroutputs` set size | upstream uid set: max / mean |
|---|---|---|---|---|---|
| `BricksSubstance002` | 5,637 | 5 | 277 | 32, 22, 21, 21 | **5 / 1.3** |
| `BambooSubstance001` | 3,104 | 6 | 80 | 14, 5, 7, 4 | **2 / 1.4** |
| `BricksSubstance003` | 2,724 | 5 | 357 | 11, 10, 9, 9 | **2 / 0.6** |

Each output requires 11 to 34 input uids upstream of its producer. The upstream closure over
the reconstructed DAG reaches **at most five**, and typically one. No sink can satisfy any
output's requirement, so every match set is empty and the algorithm reports nothing.

**The cause is graph fragmentation, not the method.** An upstream closure grows monotonically
along a connected DAG; a maximum of five accumulated uids in a 5,637-record graph means the
chains are only a few records long before they break. The sink counts say the same thing -
277 sinks where there are 5 outputs, and 357 in a 2,724-record file. This is the same
shortfall measured earlier as a median sinks-to-outputs ratio of 2.8 after the `motionblur`
correction: the edge map recovers local structure faithfully - 100% recall on
instance-free pairs - but does not connect a large graph end to end.

What is missing is consumer coverage, and this document has already identified where: not
every reference to a record travels through an edge slot. Until the non-slot references are
mapped, any algorithm requiring global reachability will fail the same way, however good the
constraint feeding it.

**So `alteroutputs` does not rescue output attribution.** It remains terminal, and this
attempt sharpens why: the obstacle is no longer missing information about outputs - the
manifest supplies that - but missing connectivity in the record graph.

## Correction: the record graph is not fragmented, and most parameters are never referenced

The previous section blamed the failure of output attribution on graph fragmentation. That
diagnosis was wrong, and the real situation is more interesting.

**The DAG is deep and well connected.** Measuring `BricksSubstance002` directly:

    records                  5,637
    DAG depth                max 182, mean 26.9, median 9
    records with no parent   424 (8%)
    sinks                    277, the deepest at depth 182

A graph with chains 182 records long is not fragmented. My "upstream closure reaches at most
five" observation was real but I drew the wrong conclusion from it: the closure being small
has nothing to do with connectivity.

**The cause is that almost no parameter is referenced by uid.** Scanning exhaustively - every
even offset in the body, 9,243 decodable blocks, not just the first chain per record:

| input | references |
|---|---|
| `$outputsize` | 4,780 |
| `$randomseed` | 537 |
| `bricks_colorB`, `mortar_color`, `bricks_colorA` | 19, 19, 18 |
| `y_amount`, `bricks_stripes_amount`, `x_amount` | 6, 5, 1 |
| **the other 25 declared inputs** | **0** |

Only **8 of 33** declared inputs appear anywhere in the bytecode, and two of those are
system variables. `bricks_scale`, `bricks_offset`, `brick_rotation_strength`,
`bricks_middle_size` and twenty-one others are never named. So an upstream closure cannot
accumulate them no matter how deep the graph is, and the `alteroutputs` constraint - which
requires 21 to 32 inputs upstream of each output - can never be satisfied.

This is consistent with what the parameter-slot work established: static parameter values are
baked into record slots as literal floats. What is new is the consequence - **the compiler
does not preserve which input a baked value came from.** Only dynamically driven parameters
keep a uid reference.

**`alternodes` is not the missing link.** The manifest attribute that looked like it might
list affected nodes is `"0"` in **all 12,250 occurrences across the corpus**. It is a count,
and it is always zero.

### An open question this raises

A `.sbsar` is parameterised at runtime - a player changes `bricks_scale` and the output
changes - so the engine must have a way to apply an input that the assembly never names.
Nothing found so far explains how. The candidates not yet excluded are a patch table outside
the region examined here, a reference form that is not the `int 02` uid immediate, or an
index-based rather than uid-based binding.

This is now the sharpest open question in the format description, and it is sharper than the
questions it replaces: not "how are outputs attributed to records" but **"how is a declared
parameter bound to the record slot it fills?"** Everything downstream of that - output
attribution, per-graph record membership, round-tripping to an editable graph - depends on
the same missing binding.

## Retraction: parameters are bound normally, and the gap was my filter

The previous section concluded that 25 of 33 declared parameters in `BricksSubstance002`
are never referenced by uid, that the compiler discards the binding between an input and
the slot it fills, and that "how is a declared parameter bound to the record slot it fills"
was the sharpest open question in the format. **All three claims are wrong.**

### The uids are there

Searching for each declared input uid as a raw 32-bit word, across 340 packages and 9,214
declared inputs:

    found in the interface block   9,214 / 9,214   (100%)
    found in the record body       8,752 / 9,214   (95%)
    per package, median share referenced in the body   100%
    packages where no input is referenced             0

Every input is in the interface block, and 95% are also in the record body. In
`BricksSubstance002` specifically, a raw search finds **all 33**, not 8.

### The filter was wrong in two ways

Dumping the bytes around a supposedly-unreferenced input shows an ordinary instruction:

    01C3      operand
    0902      opcode: type 1 (float), operation 02 - input reference
    2DEE 6306 the uid of bricks_scale
    0D00 ...  a float constant, 0.75

`input reference` is not an int-only operation. Across 115 packages the operation appears
**306,446 times as int, 4,637 as float and 140 as bool**. My extraction required
`(op >> 8) & 3 == 2`, so it discarded every float and bool form - and those are exactly the
forms that carry ordinary numeric parameters, while the int form is dominated by
`$outputsize` and `$randomseed`.

Correcting the type filter alone:

    declared inputs located, int form only    540 / 4,129   (13%)
    declared inputs located, any type          2,142 / 4,129   (52%)

a fourfold improvement. The remainder sit in blocks the per-record walk does not reach,
since it stops at the first decodable chain in each record.

### What actually stands

The binding mechanism is not missing and never was: a parameter is bound by an ordinary
`input reference` instruction carrying its uid, in whichever type the parameter has. The
`int 02` finding recorded earlier - that its immediate is an interface uid in 99.94% of
148,760 instructions - was correct and now extends to the float and bool forms.

**This is the seventh error in this document caused by a predicate that was too narrow, and
the third caused specifically by assuming one type or width where the format uses several.**
The pattern is consistent enough to state as a working rule: before concluding that
something is absent from the format, check whether the test would have found it in every
type, width and layout the format admits. The absence claims that survived - `0x0A`,
`valueprocessor` producing no record - were each checked that way; this one was not.

## Applying the rule: the output-absence claim survives

The rule from the retraction - before concluding something is absent, check that the test
would have found it in every type, width and layout the format admits - has an obvious first
target. The claim that **output uids are never referenced outside the interface block** was
established with the same int-only filter that had just proved too narrow for inputs.

Re-tested over 150 specimens, accepting operation `02` in **all three types**, and
additionally by raw 32-bit byte search of the entire record body:

| what | as int | as float | as bool |
|---|---|---|---|
| input uid referenced | 177,709 | 5,231 | 220 |
| **output uid referenced** | **0** | **0** | **0** |

    output uids found by raw byte search of the body:   0

So the claim holds, and now rests on two independent tests rather than one. No instruction
of any type carries an output uid, and no four-byte word anywhere in the records-and-bytecode
region equals one. Outputs are named in the interface block and nowhere else in the file.

This matters beyond bookkeeping. The input side has just been shown to reference uids
liberally - 183,160 times across three types in the same 150 specimens - so the absence on
the output side is not a limitation of the search. It is a real asymmetry in the format:
**inputs are addressed by uid throughout the assembly; outputs are not addressed at all.**

That is the strongest form the output-attribution verdict has taken. It is terminal not
because the link is hard to find but because the assembly contains no field capable of
expressing it, and the same test that finds 183,160 input references finds zero output ones.

## Applying the rule: no header field encodes record length

The second absence claim worth re-testing is the central one - that the format declares
record length nowhere. It was measured before the tiling work gave reliable extents, and
reported a best header-based prediction of 69.3%.

With extents measured by where each record's first instruction block begins, over **140,123
records**, and searching **every contiguous bitfield of the 32-bit tag word** - all 32 start
positions, widths 1 through 6, 177 fields in total:

| predictor | accuracy | groups |
|---|---|---|
| always predict the commonest size (24 B) | 34.8% | 1 |
| best single bitfield (bits 0-5 - the filter id itself) | **58.0%** | 41 |
| per-filter mode | 57.0% | 21 |
| filter id + the entire 16-bit class word | **64.6%** | 242 |

**No bitfield beats the filter id.** The best single field in the header is the filter type,
and knowing the filter alone gets 57%. Adding the whole class word - every bit of it, 242
distinct combinations - reaches only 64.6%, below the 69.3% previously reported from a
different sample and method, and far from the 100% a declared length would give.

The search is exhaustive in the sense the rule demands: not one field was assumed, all 177
contiguous bitfields of the tag word were tried, and none carries the information. A length
field encoded non-contiguously, or outside the record header, is not excluded - but the
directory holds offsets whose differences are gaps containing interleaved bytecode, not
record extents, so it is not there either.

**The claim stands, and it is the format's defining awkwardness.** Record extent must be
recovered by decoding forward until a valid instruction block appears, which is why the
tiling check mattered and why the greedy first-match rule was wrong. Everything else in the
format is addressed explicitly - resources by offset, inputs by uid, records by index,
bytecode by declared instruction count. Only the record's own length is left implicit.

### The shared reference does not track data reuse either

One reading of the shared reference not yet tested: that it simply names whichever records
are most reused, a by-product of common-subexpression elimination rather than a structure of
its own. It does not.

Over 50 specimens of 200 records or more, comparing each record's slot-1 fan-out against its
fan-in as a data input:

    correlation, slot-1 fan-out vs edge fan-in    median 0.006   (10th -0.014, 90th 0.066)
    of the top-10 slot-1 targets, how many are
    also top-10 edge targets                      mean 0.3 of 10

The two are **uncorrelated at zero**, and the records most named by slot 1 are almost never
the records most consumed as inputs. Whatever the shared reference organises, it is
orthogonal to how the data graph reuses results.

That is the seventh negative result for this field - not an input, not a chain link, not a
region marker, not a prototype by kind, not one global structure, not a specially marked
record, and now not a CSE artefact. It remains the best-characterised unknown in the format:
a per-record reference to one of roughly 47 early records per file, shared by hundreds of
referrers, with no resolution relationship, no positional structure, and no relationship to
data reuse.

## Records are grouped by resolution, but not ordered by it

Dumping a stretch of the directory shows the tag's high byte - the resolution field - moving
in runs: a block of `0x77` records (128x128), then `0x88` (256x256), with `0x55` and `0x66`
interspersed. Two questions follow: is the directory *ordered* by resolution, and is it
*grouped* by it.

**Not ordered.** Over 86 specimens of 100 records or more, correlation between record index
and log2 area is 0.068 - nothing. Among adjacent pairs that actually change resolution,
**52% increase and 48% decrease**, which is symmetric to within noise.

**Strongly grouped.** Of 160,189 adjacent pairs:

    same resolution     138,085   86.2%
    increase             11,494    7.2%
    decrease             10,610    6.6%

    mean run of identical resolution: median 7.1 records, 90th percentile 10.4

Records sharing a resolution sit next to each other in runs averaging seven. With roughly
ten distinct resolutions in a typical file, random assignment would make adjacent pairs
equal 10-20% of the time; the observed 86% is far above that. The directory is emitted in
evaluation order, and a subgraph working at one size produces a contiguous run.

**Transitions are whole octaves.** The commonest steps in log2 area are +2 (5,477), -4
(3,380), -2 (2,718), +8 (2,248) and -8 (2,214) - all even, meaning both dimensions change by
whole powers of two together. Nothing changes one dimension alone.

### A framing error worth recording

My first measurement asked what share of adjacent pairs are *non-decreasing* in area and got
90%, which reads like strong evidence of ordering. It is not: 86.2% of pairs are equal, and
equal counts as non-decreasing. The 90% was almost entirely the run structure, and the four
points above it were the increases. Restricting to pairs that actually change resolution
turns 90% into 52%, which is no signal at all.

**Any monotonicity statistic over a sequence with long constant runs must exclude the
constant steps**, or it measures the runs rather than the ordering. This is the same shape
of error as the small-integer trap - a statistic that is technically correct and answers a
different question than the one asked.

## A complete census of the class word

The class word has been described bit by bit as findings arrived - bit 3 as a record marker,
bits 10-13 as a layout selector, bit 8 as an edge-count flag (retracted). It had never been
enumerated. Over **all 651,743 records in all 383 specimens**:

| bit | records set | share | files |
|---|---|---|---|
| 0 | 532,606 | 81.72% | 375 |
| **1** | **0** | **0.000%** | **0** |
| **2** | **0** | **0.000%** | **0** |
| 3 | 651,741 | 100.000% | 382 |
| 4 | 622,902 | 95.58% | 345 |
| 5 | 22,095 | 3.39% | 108 |
| **6** | **3** | 0.000% | **1** |
| 7 | 83,411 | 12.80% | 330 |
| 8 | 300,347 | 46.08% | 370 |
| 9 | 277,269 | 42.54% | 357 |
| 10 | 4,469 | 0.69% | 201 |
| 11 | 63,741 | 9.78% | 286 |
| 12 | 11,546 | 1.77% | 259 |
| 13 | 18,790 | 2.88% | 262 |
| 14 | 913 | 0.14% | 52 |
| **15** | **0** | **0.000%** | **0** |

**Three bits are never set** - 1, 2 and 15, in 651,743 records without exception - and bit 6
is set in **three records in one file**, which is indistinguishable from unused. So the
16-bit class word carries at most twelve bits of information, and effectively eleven.

**Bit 3 is set in all but two records.** At 651,741 of 651,743 it is not a flag but a
marker: something that identifies the word as a class word at all. The two exceptions are
worth a look by anyone extending this work.

### What the informative bits carry

Normalised mutual information between each bit and five measured properties, over 126,477
records:

| bit | filter | size | resolution | edge count | inherits |
|---|---|---|---|---|---|
| 8 | **0.32** | 0.14 | 0.01 | 0.12 | **0.28** |
| 9 | **0.33** | 0.14 | 0.01 | 0.11 | **0.30** |
| 7 | 0.15 | 0.06 | 0.05 | **0.20** | 0.05 |
| 11 | 0.12 | 0.05 | 0.01 | 0.02 | 0.03 |
| 0, 4, 5, 12, 13 | <= 0.06 | <= 0.03 | <= 0.06 | <= 0.03 | <= 0.04 |

Bits **8 and 9** are the informative pair, and what they predict is the filter and whether
the record inherits its parent's resolution - which is consistent with their being the
resolution-mode field. Bit **7** is the one that tracks edge count, at 0.20, which is where
the retracted "bit 8 means two or more edges" claim should have pointed.

Bits 0 and 4 are set in 82% and 96% of records and predict nothing measured here; they may
be markers like bit 3 rather than fields.

**A caution about thresholds.** A first pass at this table labelled bits 6, 10, 14 and 15
"constant" because each is set in under 0.5% of a 126,477-record sample. Exact counting over
the full corpus separates them: 10 and 14 are rare but real, appearing in 201 and 52 files
respectively, while 1, 2 and 15 are genuinely zero everywhere. Rare is not the same as
absent, and only an exact count over the whole corpus distinguishes them.

## The two bit-3-clear records, and what 1x1 pixel processors are not

Bit 3 of the class word is set in 651,741 of 651,743 records. The two exceptions are both in
`MarbleSubstance002` and are near-identical:

    tag=0028  class=0080
    00800028  00010000  0005CDE8  0005CDD8  09000002  3F000000  00000906  00000000
    00800028  00010000  0007B6C0  0007B6B0  09000002  3F000000  00000906  00000001

Read out: filter `0x28` (`pixelprocessor`) at resolution `0x00`, which is **1x1** - a single
pixel. Class `0x0080` has only bit 7 set, where every other record in the corpus has bit 3.
Two forward pointers follow, then an inline two-instruction block computing the constant
0.5, then a word that differs between the two (0 and 1). Their neighbours on both sides are
ordinary records.

### 1x1 pixel processors are common, and are not `valueprocessor`

A pixel processor evaluated at one pixel computes a single number, which is exactly what a
`valueprocessor` does. That makes an obvious hypothesis, and it fails.

    pixelprocessor records at 1x1     5,832  (15.2% of all pixelprocessors, in 110 files)
    their class words                 0099 x5115, 00B9 x577, 0089 x72  - not 0080

Against the paired sources, the correspondence does not hold:

| file | `valueprocessor` nodes | 1x1 `pixelprocessor` records |
|---|---|---|
| `SubstanceDesigner__triDraw` | 13 | **0** |
| `ie_pcloud`, `sd-ie-lib__ie_pcloud` | 8, 8 | **0**, **0** |
| `LGMLtools__fz_explosion` | 6 | 5 |
| six others | 1-3 each | **0** |

Nine of ten files declare `valueprocessor` nodes and contain no 1x1 pixel processor at all.
So **the earlier finding stands**: `valueprocessor` produces no record. The 1x1 pixel
processors are something else - they appear in 110 files, far more than declare a
`valueprocessor`, and are most likely scalar computations inside inlined library graphs.

### What remains

The two bit-3-clear records are unique in the corpus on two counts at once: the only class
word without bit 3, and the only 1x1 pixel processors with class `0x0080`. They sit in a
single file, they are structurally identical apart from a trailing 0/1, and nothing else in
382 other specimens resembles them.

That is not enough to name them, and with n=2 in one file it may never be. Recorded here so
that anyone who meets a third example knows two already exist.

## Presets live only in the manifest

The manifest carries an `<sbspresets>` element that this work had never examined. Across
582 packages:

    zero presets     396
    with presets      56   (10%)
    no element       130

A preset is a named alternative parameter set - `<sbspreset label="1A">` followed by a
`<presetinput>` per parameter with identifier, type, uid and value. The question is whether
the assembly encodes them, or whether they exist only in the sidecar.

### The measurement needed two controls to give the right answer

Searching the assembly for preset values finds 69% of them, which reads as "presets are
stored in the binary". That is wrong twice over.

**First control - a preset lists every parameter, not just the changed ones.** Most of its
values *are* the defaults, so finding them proves nothing. Splitting on whether the preset
value differs from the input's declared default:

    equal to default    97% found
    differs             65% found

Still apparently positive. **Second control - restrict to distinctive values**, those needing
more than two decimals to write, so that a match is unlikely by coincidence:

| preset value | count | found in assembly |
|---|---|---|
| equal to the declared default | 3,875 | **91%** |
| **differs from the default (a true override)** | **1,298** | **9%** |

A tenfold difference. The 9% is the background rate at which any distinctive float happens
to appear somewhere in a multi-megabyte file, and the 91% is what genuine storage looks
like.

**Presets are not in the assembly.** The binary carries exactly one set of parameter
defaults; every alternative set exists only in the XML manifest.

### Consequences

For a reader this is straightforward: preset support requires parsing the manifest, and no
amount of work on the binary will recover it. It also means the manifest is not merely a
convenience - for the 10% of packages that ship presets, it carries information the
assembly does not contain, alongside the output names and the `alteroutputs` relation
already noted.

The methodological note is the same one this document keeps arriving at from different
directions: **the uncontrolled measurement said 69% and pointed the wrong way; two controls
turned it into 9% against 91%.** Neither control was subtle - one accounts for how presets
are written, the other for how often a float appears by chance - and without them the
conclusion would have been recorded backwards.

## The container holds three kinds of file, and nothing is unaccounted

A `.sbsar` is a 7-zip archive, and this document has only ever looked inside it for two
things. Enumerating every file across 582 extracted packages:

    .sbsasm        584   the compiled assembly
    .xml           584   the manifest
    .png           235   icons

and nothing else. Every package has exactly one assembly and one manifest.

### The PNGs are graph icons, all of them referenced

The 235 images split by filename into 136 called `icon<digits>.png` and 99 called
`thumbnail.png`, which looks like two kinds of thing. It is one kind. Every image, under
either name, is named by an `icon=` attribute on a `<graph>` element:

    <graph pkgurl="pkg://ie_bridge_splatter_color" label="IE|Bridge Splatter [C]"
           primaryinput="background" author="Igor Elovikov" icon="icon1382358968.png">

    images present                     235
    referenced by an icon= attribute   235   (100%)
    icon= naming a file not present      0
    graphs carrying an icon            235   in 134 manifests

So `thumbnail.png` is not a package-level preview with special status - it is simply what a
graph's icon is called when the author did not rename it, and a package with several graphs
gets several numbered icons instead.

**The digits in `icon1382358968.png` are not a uid.** Checked against every `uid=` attribute
in the same manifest, **none of 136 matches**. The number is an arbitrary identifier, and the
binding from graph to image is the `icon=` attribute alone.

### What this closes

The container question is now fully answered: three file types, one assembly, one manifest,
zero to several icons, every icon referenced, no orphan or unexplained file in 582 packages.
Nothing in the archive is undescribed - which is a smaller claim than it sounds, since the
assembly inside it still has a shared reference nobody can name, but it does mean there is
no further place in a `.sbsar` to look for information that is missing elsewhere.

## `blend` slot 4 is a bytecode pointer, and records point at their own programs

Chasing `blendingmode` led to `blend` slot 4, a slot never examined because it holds no
backward record reference. Bucketing its values as "small integer" or "large" made it look
like a constant: two distinct values in 47,418 records. That bucketing was hiding the
answer - the "large" bucket contains **27,991 distinct values**, and they are pointers.

    points into the record body                28,673
      within 200 bytes of its own record       28,612   (99.8%)
      pointing forward                         28,385   (99.0%)
    not a body pointer                              4

Testing them against the record's decoded bytecode:

    slot 4 == the record's first block start   26,790   78%
    slot 4 points at a later block              7,373   22%
    slot 4 points at something that is not a block   6   0.02%

**34,163 of 34,169 point at a valid instruction block.** When it is not the first block the
offset is positive and modest - +92, +60, +28, +48, +56 - so it selects among the several
blocks a multi-parameter record carries.

### This is the same mechanism already seen elsewhere

This document records `gradient` slot 4 as a bytecode pointer at 100% and `fxmaps` slot 17
likewise. Those were treated as facts about two filters. With `blend` - the commonest filter
in the corpus at 227,121 records - carrying the same thing, it is better read as a general
property: **a record points at the program that computes its parameters.**

### Why this matters more than one slot

Every extent measurement in this document scans forward from the record header looking for
the first position that decodes as a block, and a great deal of care went into that scan -
the greedy first-match rule was wrong, the best-coverage rule fixed it, zero-count words
derailed it. **The record has been carrying a pointer to the answer.**

A reader does not need to search. For `blend`, and for whichever other filters carry the
same slot, the program's address is stated. That does not solve record *length*, which
remains undeclared - the pointer gives the block, not the header's extent - but it removes
the guesswork from the largest part of the problem.

The correct next step is to test every filter's slots for this signature: a word that is not
a backward record reference, points forward within a few hundred bytes, and lands on a
decodable block. Any slot passing that test is a program pointer, and the scan can be
replaced by a dereference wherever one exists.

## Every filter carries a program pointer, and the record layout falls out

Testing every (filter, slot) for the signature - points into the body, forward, at a
position that decodes as an instruction block - over 100 specimens:

| filter | slot | records | is a block | equals the first block |
|---|---|---|---|---|
| `passthrough` | 3 | 414 | **100%** | 99% |
| `motionblur` | 3 | 3,275 | **100%** | 89% |
| `gradient` | 4 | 1,733 | **100%** | 93% |
| `transformation` | 3 | 30,597 | **100%** | 72% |
| `directionalwarp` | 4 | 8,270 | **100%** | 86% |
| `blend` | 4 | 43,118 | **100%** | 78% |
| `levels` | 3 | 12,908 | **100%** | 96% |
| `uniform` | 1 | 1,498 | 99% | 92% |
| `blur` | 2 | 1,569 | 99% | 92% |
| `pixelprocessor` | 5, 6 | 5,378, 1,467 | 99%, 97% | 72%, 78% |

Seven filters hit **100%** - every record, without exception, has that slot pointing at a
decodable instruction block.

### The slot position is not arbitrary

Lining the pointer slot up against what this document establishes about each filter's
other slots:

| filter | slot 1 | inputs | ramp | **program** |
|---|---|---|---|---|
| `uniform` | - | none | - | **1** |
| `blur` | input | 1 | - | **2** |
| `levels` | shared ref | 2 | - | **3** |
| `transformation` | shared ref | 2 | - | **3** |
| `motionblur` | shared ref | 2 | - | **3** |
| `blend` | shared ref | 2, 3 | - | **4** |
| `directionalwarp` | shared ref | 2, 3 | - | **4** |
| `gradient` | input | 1 | 3 | **4** |

**The program pointer is the slot immediately after the filter's inputs.** A record is laid
out as an optional shared reference, then the input edges, then the pointer to the parameter
program - and the whole variation between filters is how many inputs sit in the middle.

`gradient` fits with its ramp table interposed at slot 3, and `uniform`, which takes no
image input at all, puts its pointer at slot 1. `passthrough` at slot 3 is the one that does
not fit a single-input filter cleanly, and `pixelprocessor` places its pointer after a
variable-length input list, which is consistent with its arity field.

### What this replaces

Every extent measurement in this document scans forward for the first decodable block, a
scan that took several attempts to get right. For these filters the scan is unnecessary: the
record states the address. Reading a `.sbsar` record becomes

    tag and class -> filter, resolution, layout
    slot 1        -> shared reference, or the first input
    next slots    -> the remaining inputs
    next slot     -> the parameter program
    (length still undeclared)

which is a considerably simpler object than the one this document has been describing by
inference for most of its length.

## The shared reference is a hierarchy

Seven tests established what the slot-1 shared reference is not. The record layout gives the
clue that suggested the eighth: it sits **before the inputs**, which is where an owner field
belongs rather than a data field.

Following slot 1 from record to record, over 50 specimens of 200 records or more:

    records carrying a parent            82,109
    cycles                                    0
    chain depth 1 (parent has no parent) 46,589   57%
    chain depth 2 or more                35,520   43%

    maximum chain depth per file    median 3, largest 5
    roots - targets with no parent  median 24 per file

**It is acyclic, in every one of 82,109 references.** A field that pointed at data, or at a
neighbour, or at whatever record happened to be convenient would produce cycles at that
volume; this produces none. And 43% of records have a parent that itself has a parent, so it
is not a flat grouping either.

What the numbers describe is a **shallow forest**: about two dozen roots per file, trees no
more than five deep, most records one or two levels down. That is the shape of a nesting
hierarchy - a graph instantiating subgraphs which instantiate others - and it fits what this
document knows about the compiler. Inlining flattens the *data* graph completely, since the
edge map reconstructs the author's connections exactly. The hierarchy records what inlining
destroyed: which instance each record came from.

That reading also explains the seven negatives at once. It has no resolution relationship
because ownership is not data flow. Its referrers are scattered through the directory
because the directory is in evaluation order, not instance order. Its targets are ordinary
filter records of any kind because the head of an instance is whatever node the subgraph
starts with. It is uncorrelated with data reuse because CSE merges by value while this
groups by origin. And a typical file has 24 to 47 of them because that is how many subgraph
instances a material uses.

**This is a reading, not a measurement**, and the corpus cannot confirm it directly - the
paired sources whose instance structure could test it are exactly the files whose library
`.sbs` dependencies are excluded. But it is the first hypothesis that accounts for every
measured property rather than being eliminated by one, and it predicts something checkable
by anyone with library sources: the depth of a record's slot-1 chain should equal the
instance nesting depth of the node it came from.

### It groups by source package, not by instance

The hierarchy reading predicted that slot-1 groups correspond to subgraph instances. Tested
against 58 paired files, that prediction **fails**, and what replaces it is sharper:

    corr(compInstance nodes, distinct slot-1 parents)   +0.173
    corr(compNodes total,    distinct slot-1 parents)   +0.314
    corr(records,            distinct slot-1 parents)   +0.756
    corr(<dependency> count, distinct slot-1 parents)   +0.902

**The hierarchy tracks the number of dependencies** - the distinct external `.sbs` packages
a file references - not the number of instantiations. The examples make it plain:

| file | instance nodes | dependencies | records | roots | groups |
|---|---|---|---|---|---|
| `LGMLtools__msxcolors` | **451** | **3** | 404 | 4 | **5** |
| `LGMLtools__sRGB_colorchart` | 131 | 5 | 6,232 | 8 | **8** |
| `ie_pcloud` | 202 | 3 | 301 | 7 | **8** |
| `DLG-Tools__Obsidian_01` | 96 | **51** | 6,419 | 40 | **90** |
| `DLG-Tools__Mineral_Ore_01` | 189 | **58** | 7,557 | 48 | **88** |

`msxcolors` instantiates subgraphs 451 times and has five slot-1 groups. `Obsidian_01`
instantiates 96 times, draws on 51 packages, and has ninety. Instance count predicts nothing;
dependency count predicts almost everything, at r = 0.90.

So the shared reference does not say *which instantiation* a record belongs to. It says
**which source graph the record was compiled from**. Four hundred and fifty-one calls to the
same three library graphs produce records carrying only three-odd distinct markers, because
they all came from the same three graphs.

That is a better fit than the instance reading on every axis. It explains the count - a
material draws on a few dozen distinct library graphs, which is exactly the 24 to 47 groups
observed. It explains the shallow depth of 3 to 5, which is how deep library graphs nest
(`slope_blur` uses `blur_hq` uses `blur`). It explains the scattering, since records from one
source graph appear wherever that graph is used. And it explains the absence of any
resolution or data relationship, because provenance is neither.

**Status.** This is the eighth hypothesis and the first to survive. It rests on a single
strong correlation (r = 0.902, n = 58) plus consistency with eight prior negatives, which is
support rather than proof. The decisive test needs library sources - if a record's slot-1
marker identifies its originating `.sbs`, then records from the same library graph must share
one, and that is checkable by anyone whose corpus includes those files. This corpus excludes
them by policy.

If it holds, the practical consequence is substantial: **the compiled assembly retains the
provenance of every record**, so an importer can group a flattened graph back into the
library subgraphs the artist actually placed - which is the one thing inlining appeared to
have destroyed beyond recovery.

### Corroboration: the groups are graph-cohesive

The provenance reading predicts something testable without any source: records compiled from
one library graph should be **connected to each other**, because a graph's nodes mostly wire
to their own neighbours.

Over 70 specimens, comparing edges whose endpoints both carry a slot-1 marker against a null
produced by shuffling the markers among the same records, preserving group sizes:

    edges with both endpoints marked        83,833
    both endpoints in the same group        22,271   26.6%
    null expectation, shuffled labels        7,085    8.5%
    enrichment                                        3.1x

**Records sharing a marker connect to each other three times more often than chance.** The
grouping is not a labelling of unrelated records; it has genuine structure in the data graph,
which is what a provenance marker should have and what none of the eight rejected readings
would produce.

The enrichment is real but not overwhelming, and the reason is worth stating: 73% of edges
still cross groups. Some of that is expected - a library graph takes inputs from its caller
and returns a result to it, so every instantiation contributes boundary edges - but at these
proportions the groups are more porous than a clean subgraph decomposition would be. Either
the groups are coarser than one graph, or the marker is inherited by nodes a graph pulls in
from elsewhere.

So the provenance reading now has two independent supports - the dependency-count correlation
at r = 0.90, and threefold edge cohesion against a shuffled null - and one unresolved
tension in how porous the groups are. That is a materially stronger position than the eight
negatives it replaced, and it remains short of the direct test, which needs the library
sources this corpus excludes.

### The boundary test does not discriminate

To resolve the porosity, I asked whether a group's external edges concentrate on a few
boundary records, as they would for a clean subgraph. Over 1,016 groups:

    group size                                    median 26, 90th percentile 192
    share of members touching an outside edge     median 98%, 25th percentile 75%
    groups where under a third of members touch outside      98 (10%)

Almost every member of almost every group has at least one edge leaving the group, which
reads as a decisive refutation of the subgraph picture. **It is not**, and the test is at
fault.

Records in this format have a typical degree of two - one input, one consumer. A node with
one edge in and one edge out is counted as "touching outside" if *either* of them leaves the
group, so a simple chain that alternates across a boundary scores 100% on this measure while
being half internal. The statistic answers "does this member have any external edge", which
at degree two is nearly always yes regardless of how the groups are drawn.

That makes it uninformative here, and it does not weaken the two supports that stand - the
r = 0.90 dependency correlation and the 3.1x edge cohesion against a shuffled null, both of
which compare against a null rather than against an absolute threshold.

**The recurring lesson applies to my own tests as much as to the format's fields:** a
predicate that is almost always true tells you nothing, and "almost always true" is a
property of the data's degree distribution, not of the hypothesis. The cohesion measure
worked because it was defined against a shuffled control; this one failed because it was
defined against an intuition about what subgraphs look like.

The porosity question therefore remains open, with the useful fact from this run being the
group size distribution: **median 26 records, 90th percentile 192**, which is the right
order for a library graph instantiated a handful of times.

## Modularity: what actually organises the record graph

The right way to ask whether a grouping is meaningful is modularity - the excess of
within-group edges over what the degree distribution alone would give - measured against
rival groupings rather than against intuition. Over 35 specimens of 400 records or more:

| grouping | median Q | 25th | 75th |
|---|---|---|---|
| **contiguous directory blocks** | **0.782** | 0.745 | 0.832 |
| by resolution | 0.272 | 0.149 | 0.376 |
| **slot-1 shared reference** | **0.157** | 0.124 | 0.183 |
| by filter kind | 0.009 | -0.017 | 0.073 |
| shuffled labels (null) | **-0.002** | -0.010 | 0.002 |

Three things fall out.

**The record graph is overwhelmingly local.** Cutting the directory into contiguous blocks of
the right size gives modularity 0.78, which is very strong community structure. Records
connect to their neighbours: a subgraph is emitted as a contiguous run and wires itself up
before the next run begins. This is the strongest organising principle in the record region
and it had not been quantified.

**Filter kind organises nothing.** At Q = 0.009 it is indistinguishable from the shuffled
null. Blends do not preferentially feed blends; the graph is not stratified by operation.

**The slot-1 grouping is real but weak** - 0.157 against a null of -0.002, so it is not
noise, but it is a fifth of what directory locality achieves.

### Does this hurt the provenance reading?

At first sight yes: if the marker identified an originating graph, and graphs are emitted
contiguously, the marker should recover the same partition that contiguous blocks do, and
score near 0.78 rather than 0.157.

It does not, for a reason the reading itself predicts. A library graph used fifty times is
compiled fifty times, producing **fifty separate contiguous runs that all carry the same
marker**. Contiguous blocks capture each instantiation; the marker groups all of them at
once. A union of fifty scattered runs necessarily has low modularity even when every run is
internally dense, and every boundary edge of every instantiation counts against it.

So the numbers are consistent with provenance, and they also explain the porosity that the
previous section could not resolve: with fifty instantiations, boundary edges outnumber what
a single subgraph would contribute.

**This is consistent, not confirmed**, and the distinction matters - the reasoning is
post-hoc, fitted to a result that came in lower than expected. What the run establishes
independently of any hypothesis is the first item above: **inlined subgraph instances are
emitted as contiguous runs**, at Q = 0.78, which is a fact about the format rather than a
reading of one field.

## The record graph is nearly a chain

The modularity result said the record graph is highly local; an attempt to segment the
directory at points no edge crosses said otherwise, producing 94 segments across 35 files
with a 90th-percentile length of 3,449 - one giant segment per file. Measuring how far back
each edge actually reaches resolves it, over 139,182 edges:

| edge reaches back | edges | share |
|---|---|---|
| **exactly 1 record** | 64,456 | **46.3%** |
| 2-4 | 34,282 | 24.6% |
| 5-16 | 15,472 | 11.1% |
| 17-64 | 11,534 | 8.3% |
| 65-256 | 6,534 | 4.7% |
| over 256 | 6,904 | **5.0%** |

**Nearly half of all edges connect consecutive records**, and 71% reach back four records or
fewer. The compiler emits in an order where a consumer usually follows its producer
immediately - the record directory is close to a linearised evaluation order, not an
arbitrary listing.

That is what drives the 0.78 modularity of contiguous blocks. And the 5% of edges reaching
back more than 256 records - median 3.4% per file - is what defeats the segmentation: with
tens of thousands of edges, three percent long-range is still hundreds of edges spanning any
given cut, so no position in the directory has zero crossings even though the bulk structure
is chain-like.

Both measurements were right and neither was the whole picture. A grouping statistic saw the
dominant local structure; a cut-based statistic saw the sparse long-range edges. **They
disagreed because one was sensitive to the bulk and the other to the tail**, which is worth
noting as a general hazard: a segmentation that requires a clean cut fails on a graph that is
99% local if the remaining 1% is spread out, and reports that the graph has no structure at
all.

### For a reader

The practical consequence is small but real. A record's inputs are usually the record just
before it, so a decoder that walks the directory in order has almost always already seen what
it needs - and an importer building a node graph can expect the emission order to read as
evaluation order, with the occasional long-range edge to a shared or hoisted result.

## Record references are absolute, not relative

With 46% of edges reaching back exactly one record, a relative encoding would be natural -
and would mean that slots rejected as "small integer traps" were edges all along, read
wrongly. That is worth testing rather than assuming, because it would overturn a great deal.

Reading each rejected slot both ways - absolute (`target = v`) and relative
(`target = i - v`) - the relative reading looks alarmingly good:

| slot | absolute inherit | relative inherit |
|---|---|---|
| `distance` slot 1 | 66% | **95%** |
| `directionalwarp` slot 1 | 61% | **91%** |
| `motionblur` slot 1 | 73% | **89%** |
| `levels` slot 1 | 56% | 70% |
| `blend` slot 1 | 55% | 68% |
| `pixelprocessor` slot 1 | 23% | 68% |

Three of them reach the range that marks a genuine edge.

### The control settles it

The filters whose slot 1 is *known* to be the edge - established independently, by source
arity and by 100% inheritance - decide which convention the format uses:

| filter | absolute inherit | relative inherit |
|---|---|---|
| `gradient` | **100%** | 33% |
| `blur` | **100%** | 26% |
| `passthrough` | **100%** | 70% |
| `sharpen` | **100%** | 56% |
| `shuffle` | **100%** | 55% |
| `warp` | **90%** | 45% |

**Absolute wins on every one**, at 90-100% against 26-70%. Record references in this format
are absolute indices, and the relative reading is wrong.

So the elevated relative-inheritance figures for `distance` and `directionalwarp` are
coincidence, and they are coincidence for a reason this document has already measured:
records sit in resolution runs averaging seven, so an offset landing anywhere within the same
run inherits by construction. A reading that lands *near* the right place scores well on
resolution without being right.

### What this protects

The hierarchy and provenance analysis of slot 1 was built entirely on the absolute reading.
Had the convention been relative, all of it - the acyclicity across 82,109 references, the
r = 0.90 dependency correlation, the 3.1x edge cohesion - would have been computed on
nonsense. **The control confirms it was not.**

This is the eighth time a control has been decisive in this document, and the first time one
has protected a large body of existing work rather than correcting a single claim. The test
cost one measurement: read a slot both ways on filters whose answer is already known.

## The inheritance null depends on distance

The inheritance test has been used throughout against a single null of 50.8%, measured from
random record pairs. That null is wrong for near targets, and the resolution-run structure
says why: records sit in runs of about seven at the same size, so a reference landing
*anywhere in the same run* inherits by construction.

Measuring resolution agreement with an arbitrary record at a fixed distance back:

| distance | agreement by chance |
|---|---|
| exactly 1 | **87%** |
| 2-4 | 75% |
| 5-16 | 66% |
| 17-64 | 57% |
| 65-256 | 52% |
| over 256 | 47% |
| (global) | 50.8% |

Since 46% of real edges reach back exactly one record, **the null for a typical edge is 87%,
not 51%**. Every inheritance figure in this document is measured against a null that was too
lenient for near references and too strict for far ones.

### Re-scoring against a matched null

| slot | observed | matched null | lift |
|---|---|---|---|
| `warp` 3 | 100% | 73% | 1.37 |
| `shuffle` 3 | 99% | 76% | 1.30 |
| `blend` 2 | 100% | 78% | 1.28 |
| `levels` 2 | 100% | 83% | 1.20 |
| `distance` 3 | 100% | 84% | 1.19 |
| `fxmaps` 4 | 91% | 77% | 1.18 |
| **`fxmaps` 5** | **76%** | **73%** | **1.04** |
| **`fxmaps` 3** | **71%** | **79%** | **0.89** |
| `transformation` 2 | 44% | 73% | 0.60 |

**The confirmed edges survive**, and the reason is that they are not merely high but
*exact*: 100% agreement is not something a 78% null produces at these volumes, whatever the
lift ratio. A slot that is right every time in fifty thousand records is an edge.

**`fxmaps` slot 5 falls to the null** at lift 1.04, which settles the last entry the edge map
had listed as doubtful: it is not an edge. `fxmaps` slot 3 scores *below* its matched null.

`transformation` slot 2 at 0.60 is the known case where the test has no force, since the
filter resizes by design - and the matched null shows how far below chance that pushes it.

### One caveat on the `fxmaps` rows

These figures pool all record layouts. The layout analysis found slots 3 through 8 behaving
identically at 100% inheritance *within the 52-byte layout*, and those records are a minority
of `fxmaps`. Pooling dilutes them, so these numbers do not overturn that finding - they
restate the same lesson, that an `fxmaps` slot index means nothing without its layout.

**What changes in practice:** nothing about the confirmed edges, one doubtful entry resolved
negatively, and every future inheritance claim in this work needs its null matched to the
reference distance rather than taken from the global figure.

## `fxmaps` inputs, settled per layout

With the layout split and a distance-matched null, the one filter whose arity was never
pinned resolves cleanly:

**52-byte records (1,220)** - six input slots, all behaving identically:

| slot | refs | inherits | matched null | lift |
|---|---|---|---|---|
| 3 | 785 | **100%** | 80% | 1.25 |
| 4 | 784 | **100%** | 80% | 1.25 |
| 5 | 787 | **100%** | 81% | 1.24 |
| 6 | 784 | **100%** | 81% | 1.23 |
| 7 | 784 | **100%** | 81% | 1.23 |
| 8 | 784 | **100%** | 83% | 1.20 |

**32-byte records (1,761)** - one input, at slot 5 (98%, lift 1.17).
**40-byte records (1,927)** - one input, at slot 6 (100%, lift 1.15).
**36-byte records (4,984)** - **no input slot qualifies at all.**

### The counts agree with the sources

The 52-byte layout has six input slots but only **784 of 1,220 records** populate any given
one - 64%. Six slots at 64% occupancy is about four inputs per record, and the paired
sources declare **3 inputs for 20% of `fxmaps` nodes and 4 for 49%**. Two measurements that
share nothing - one counting `connRef` elements in XML, one testing resolution inheritance
in binary slots - arrive at the same arity.

The 36-byte layout, which is the commonest at 4,984 records, has no input at all. That is
what a pure generator looks like: an FX-Map that composites patterns onto its own canvas
without consuming an image.

### And slot 1 is *below* its null, in every layout

| layout | slot 1 inherits | matched null | lift |
|---|---|---|---|
| 36 B | 33% | 48% | 0.70 |
| 40 B | 29% | 48% | 0.61 |
| 32 B | 23% | 48% | 0.48 |
| 52 B | 21% | 48% | 0.43 |

The shared reference does not merely fail to inherit - it inherits **less often than an
arbitrary record at the same distance**, consistently, by a factor of two. Whatever slot 1
points at is *systematically of a different resolution* than the record naming it.

That is a new fact and it fits the provenance reading rather than sitting awkwardly with it:
if slot 1 names the head of the library graph a record came from, that head is a different
node operating at whatever scale its own graph starts with, and would be anti-correlated with
the resolution of a record deep inside an instantiation. A field with no relationship would
sit at the null; this one sits below it.

### The target is not a graph head

If slot 1 names the head of the graph a record came from, its targets should look like heads:
sitting at the start of a resolution run, and consuming nothing. Over 3,187 targets:

| property | targets | base rate | enrichment |
|---|---|---|---|
| at a resolution-run start | 19% | 14% | 1.36x |
| consumes no input | **6%** | **6%** | **1.00** |

The in-degree test is flat - a slot-1 target is exactly as likely to consume an input as any
other record. The run-start enrichment is positive but slight.

The in-degree result does not by itself refute the reading, because after inlining a library
graph's first node consumes whatever the caller passed in, so it would have in-degree 1 like
anything else. But nothing here supports "head" either, and the targets otherwise look like
ordinary mid-graph records - which this document already found when it checked their class
words and filter kinds.

**So the provenance reading survives in its general form and loses its specific one.** The
marker groups records that came from the same place, on the evidence of the dependency
correlation and the edge cohesion; *which* record it names within that group is not the entry
point, and appears to be an arbitrary representative. That is a smaller claim than the one
the previous section reached for, and it is the one the measurements support.

## The resolution field, cross-checked against the manifest

The resolution field - two nibbles of the tag's high byte holding log2 width and log2 height -
was established against JPEG dimensions on 46 specimens. The manifest declares each output's
width and height independently, and had never been used for this.

Over 250 packages:

    every declared output size appears as a record resolution   248  (99%)
    largest record resolution equals largest declared output     70  (28%)

**The first line is the confirmation**: in 248 of 250 packages, every size the manifest
declares for an output is present among the record resolutions, which is what must happen if
the nibble decoding is right and cannot easily happen if it is wrong.

### The 28% has an explanation in the data

Across all 651,743 records:

| resolution | records | share |
|---|---|---|
| 256x256 | 383,867 | 58.9% |
| 128x128 | 62,989 | 9.7% |
| 16x16 | 61,249 | 9.4% |
| 64x64 | 48,881 | 7.5% |
| 32x32 | 25,945 | 4.0% |
| **2048x2048** | 14,029 | 2.2% |
| 512x512 | 13,311 | 2.0% |
| **64x256** | 10,201 | 1.6% |
| 1x1 | 6,653 | 1.0% |

**3.09% of records operate at 2048 or above** - 14,029 at 2048x2048, 3,611 at 4096x4096, and
364 at 8192x8192 - while the manifest typically declares a 256x256 output. A material
computes intermediates at higher resolution than it finally emits, so the largest record
resolution exceeding the declared output is expected rather than contradictory.

### Non-square resolutions settle the encoding

`64x256`, `2048x16` and `4096x1024` all occur, at 10,201, 1,410 and 440 records. **The two
nibbles are independent**, which the earlier square-only evidence could not distinguish from
a single size field with a duplicated nibble. A format storing one dimension could not
produce `2048x16`.

That closes the resolution field: independently confirmed against two external sources -
JPEG dimensions and manifest declarations - with the two-nibble structure demonstrated by
non-square cases rather than assumed.

## Two foundational assumptions, checked at last

Long-running work accumulates assumptions that were reasonable when made and never revisited.
Two of them underpin most of this document.

### The record directory is stored in ascending offset order

Every analysis here sorts the directory before assigning record indices. If the stored order
differed from sorted order, every index-based edge reference would have been computed against
the wrong numbering - and the 100% inheritance results would be inexplicable rather than
reassuring.

    files with two or more records      375
    directory already in ascending order 375   (100%)
    files with duplicate offsets           0

The sort was a no-op. **A record index is simply its position in file order**, and that is
now checked rather than assumed.

### The input descriptor type field agrees with the manifest exactly

The binary's input descriptors are `(kind, uid, value)` triples, with `kind` decoded against
a documented table. Comparing every descriptor against the manifest's `type=` attribute for
the same uid, over 300 packages:

| code | meaning | in binary | in manifest |
|---|---|---|---|
| 0 | float1 | 3,166 | 3,166 |
| 1 | float2 | 454 | 454 |
| 2 | float3 | 134 | 134 |
| 3 | float4 | 252 | 252 |
| 4 | int1 | 2,748 | 2,748 |
| 5 | image | 799 | 799 |
| 6 | string | 11 | 11 |
| 8 | int2 | 460 | 460 |
| 9 | int3 | 1 | 1 |
| 10 | int4 | 1 | 1 |

    binary type == manifest type, same uid     8,026 / 8,026   (100%)
    type codes observed with no documented meaning   0

**Every count matches exactly**, not merely in aggregate but per uid across 8,026
comparisons, with zero disagreements. Type 7, `font`, is documented but does not occur in
this corpus; types 9 and 10 occur once each, which is why a smaller sample would have missed
them.

Neither check found an error. That is the point of running them: the two assumptions that
carry the most weight in this document are now the two best-verified statements in it, and
the cost was two measurements.

### The layout heuristic agrees with the version rule

Which of the two file layouts a specimen uses is detected here by a heuristic - whether most
directory entries point *before* the directory. The documented rule is independent: layout B
occurs only in version 2.

| layout | version | files |
|---|---|---|
| A | 0x20000 | 54 |
| A | 0x30000 - 0x90000 | 292 |
| **B** | **0x20000** | **29** |
| B | any other version | **0** |

The heuristic never selects B outside version 2, and 29 of 83 version-2 files use it - 35%,
against the 36% recorded from the earlier sample. And under the layout it chooses, **all 375
files have every record inside the body region**. Two independent confirmations that the
detector is right.

### The 16-byte trailer, fully decoded

The trailer was described as "words 4 and 5 bracket the directory and word 6 names the value
table". Reading the last sixteen bytes as four words and testing every relation, over 382
specimens:

    word 0 == record count                 382/382   100%
    word 1 == directory start - 52         382/382   100%
    word 2 == directory end - 52           382/382   100%
    word 3 == value table start - 52       382/382   100%

**Exact, in every specimen, with no word left over.** The trailer is a four-field footer:
how many records, where the directory begins and ends, and where the value table begins - all
in the format's universal `+52` frame.

One earlier reading needs correcting. Word 1 was noted as the constant `4`, which it is in
247 of 382 files - but only because those files put the directory at `0x38`, and `0x38 - 52 =
4`. In the other 135 the directory sits elsewhere and word 1 follows it. **It was never a
constant; it was a pointer that mostly points at the same place**, which is the same shape of
mistake as the "small integer" trap and the "always non-decreasing" statistic: a value that
looks fixed because the common case is fixed.

## A byte-level account of the whole file

Every region of the assembly has been described somewhere in this document, but the shares
have never been put side by side. Over 120 specimens totalling 906,777,008 bytes:

| region | bytes | share of file |
|---|---|---|
| **resources** | 864,186,004 | **95.30%** |
| **records + bytecode** | 41,894,464 | **4.62%** |
| directory | 644,684 | 0.07% |
| value table + interface | 57,544 | 0.01% |
| header | 6,720 | 0.001% |
| trailer | 1,920 | 0.000% |
| **total** | **906,777,008** | **100.00%** |

    unaccounted by the region map: 0 bytes

### What that number does and does not say

The regions tile the file **by construction** - each is defined by where the next begins - so
zero unaccounted bytes shows the region map is complete and self-consistent, with no gaps and
no overlaps. It does not by itself mean every byte is understood.

Combining with the interpretation rate established for each region separately - resources
tiled exactly by their descriptors, directory and trailer decoded at 100%, value table with
zero unexplained entries, records-and-bytecode at 97% under the resync walker:

    weighted interpretation rate    99.861%
    unexplained                     1,256,834 bytes of 906,777,008   (0.139%)

and all of that residue is inside the records-and-bytecode region, concentrated in FX-Map
leaves and zero padding.

### The proportion is the surprising part

**Ninety-five percent of a compiled Substance assembly is embedded bitmap data.** The entire
graph description - every record, every parameter program, the directory, the interface and
the trailer - is under five percent of the file, and the parts this document spent the most
effort on are the smallest: the value table and interface block together are one
ten-thousandth of the bytes.

For a reader that reframes the work. A `.sbsar` reader that only wanted the images would need
the resource descriptors and nothing else, and would be reading 95% of the file with perhaps
a tenth of the format knowledge. Everything else here exists to recover the 4.6% that
describes how the images are *made*.

### Correction: that proportion describes nine files, not the format

The previous section concluded that "ninety-five percent of a compiled Substance assembly is
embedded bitmap data" and drew a moral from it. **That is a byte-weighted figure, and it
describes almost none of the corpus.**

Per file, over all 382 specimens:

    file size                      median 0.4 MB, 90th percentile 17.8 MB, largest 335.8 MB
    files over 50 MB               9, holding 47% of all bytes
    files with NO resource segment 277  (73%)

    resource share of a file        median 0.0%, 75th percentile 11.6%
    records+bytecode share          median 95.5%, 25th percentile 64.6%

**Three files in four contain no embedded images at all, and the median package is 95.5%
graph description** - the exact inverse of the byte-weighted total. Nine files above 50 MB
hold 47% of the corpus by volume and drag the aggregate to 95% resources.

Both numbers are correct and they answer different questions. By bytes, the corpus is mostly
pixels; by package, the format is mostly graph. The one that matters depends on the question:
a tool sizing its buffers cares about the byte-weighted figure, a tool deciding which parts
of the format it must implement cares about the per-file one.

The moral drawn in the previous section - that a reader wanting only images could skip most
of the format - is **wrong as stated**. For 73% of packages there are no images to extract,
and the 4.6% of bytes that describe the graph are the entire content. That work was not
effort spent on a minority of the file; it was effort spent on what a typical `.sbsar`
actually contains.

**This is the aggregation form of the failure mode this document keeps meeting.** A statistic
weighted by size reports the behaviour of the largest members; a statistic weighted by
membership reports the typical one. Neither is wrong, and quoting one while reasoning about
the other produces a confident conclusion that inverts under inspection - which is what
happened here, one section ago, in this document.

## Auditing the other aggregate figures

The aggregation error prompted re-checking the two other headline rates per file rather than
per byte or per instruction.

### The ISA figure is robust

    catalogued-operation share, aggregate (instruction-weighted)   99.9%
    per file: median 99.91%, 25th 99.83%, 10th 99.59%, worst 92.86%

The distribution is tight and the worst file is still at 93%. This figure means what it
appears to mean, in every file, not just in bulk.

### The coverage figure needs a qualification

    body-region coverage, aggregate (byte-weighted)   97.0%
    per file: median 94.0%, 25th 85.7%, 10th 60.0%, worst 0.0%

A file at 0% looks alarming. It is not, and the reason is instructive:

| file | coverage | records | body bytes |
|---|---|---|---|
| `celtic_orna_mossy_001` | **0%** | 6 | **96** |
| `brown_mud_leaves_01` | 60% | 12 | 240 |
| `floor_pavement_02` | 60% | 12 | 240 |
| `brickwall_02c` | 60% | 14 | 280 |
| `ie_particles` | 5% | 27 | 12,448 |
| `Hard-Science-Old__Bruno_Caustics` | 43% | 234 | 15,128 |

The low-coverage files are **bitmap-only materials with no bytecode at all**.
`celtic_orna_mossy_001` is one of the instance-free pairs: six `bitmap` source records of
eight bytes each, ninety-six bytes of body, and not one instruction anywhere. A metric
defined as "bytes covered by record headers plus decoded blocks" reports 0% when there are no
blocks to decode - it is measuring the absence of programs, not a failure to read them.

The same applies to the cluster at 60%: twelve records of twenty bytes, twelve bytes of
header covered each, no programs.

**Two files are genuine outliers.** `ie_particles` at 5% of 12,448 bytes and
`Bruno_Caustics_Generator` at 43% of 15,128 bytes have substantial bodies that the walker
does not decode. Those are real gaps and worth someone's attention.

### The corrected statement

The walker covers the records-and-bytecode region at **97% by bytes and 94% in the median
file**, and the apparent low tail is almost entirely materials that contain no programs, for
which the metric is undefined rather than poor. Excluding files with fewer than 500 body
bytes would remove every entry in the table above except the last two.

That is the third form of the same lesson in as many sections: byte-weighted against
file-weighted inverted a conclusion, and now a per-file distribution has a tail made
entirely of cases the metric does not apply to. **A rate needs its denominator examined
before it is quoted, and a distribution needs its tail identified before it is worried
about.**

## What the undecoded 5% actually is

The two low-coverage outliers turned out not to be decoder failures. `ie_particles` has one
`fxmaps` record spanning 5,948 bytes whose contents are an array of small integers -

    09 88 B9 03  01 70 00 00  58 19 00 00  01 00 00 00
    01 00 00 00  01 00 00 00 ...  02 00 00 00  03 00 00 00
    04 00 00 00  05 00 00 00  06 00 00 00  07 00 00 00  0E 00 00 00

- a table, not a program. The walker does not decode it because there is nothing there to
decode.

Attributing every undecoded byte in the body region to the record that owns it, over 120
specimens:

| owning record type | region bytes | undecoded | share of the gap |
|---|---|---|---|
| **`fxmaps`** | 9,909,232 | 1,021,212 | **46%** |
| **`gradient`** | 908,480 | 585,702 | **27%** |
| `transformation` | 6,682,748 | 259,630 | 12% |
| `blend` | 8,596,188 | 171,040 | 8% |
| `levels` | 2,614,104 | 53,492 | 2% |
| everything else | - | - | 4% |

    total undecoded: 2,204,940 of 41,887,908 body bytes  (5.3%)

**Two record types account for 73% of it**, and they are exactly the two this document
identifies as storing tables rather than programs: `fxmaps` holds tree nodes and index
arrays, `gradient` holds 64-point colour ramps. The residue is not unexplained format - it is
the places where the format stores data structures, which an instruction walker is not
supposed to read.

**One caveat on the `gradient` row.** This run capped the search for a record's first block at
128 bytes for speed. A `gradient` record puts its ramp table between the header and the
program, so the cap truncates the search on exactly the records where the program sits
furthest out, and the 64% figure for `gradient` is inflated by that. Measured with a wider
cap in an earlier section, `gradient` covers 94%. The `fxmaps` share is not affected the same
way and is the real content of the gap.

So the honest final statement on the records-and-bytecode region is: **97% of its bytes by
volume are accounted for, 94% in the median file, and the remainder is dominated by FX-Map
tables** - with a small contribution from a scan parameter that could be widened at the cost
of speed.

### The `fxmaps` residue is the trees, and the measurement is parameter-dependent

Examining the large-span `fxmaps` records directly shows two different things under one
heading.

`ie_particles` record 22 is an integer array - a table of small values, mostly 1 then
ascending - inline in the record's span. The `flowingLava` and `stone_stylized` records are
not: they carry `class=0x0399`, a count of 16 or 32 at slot 1, two body pointers at slots 2
and 3, and their first instruction block begins at +24 or +60. Their spans of 2,172 to 12,220
bytes are not record contents at all - they are **the FX-Map tree living in the gap before
the next record**, which this document has already described as 8/12/16-byte link and branch
nodes with 44-byte-plus leaves.

So the 46% of undecoded bytes attributed to `fxmaps` is mostly a structure that is documented
and simply is not instructions.

**And the share is sensitive to the walker's parameters.** The run that produced the 46%
figure capped the first-block search at 128 bytes and used a 256-byte resync window. Widening
either recovers more: an earlier section measured `fxmaps` at 96.1% covered with a 256-byte
resync, against 34.7% at 64 bytes. A number like "5.3% of body bytes undecoded" is therefore
a property of the decoder settings as much as of the format, and should be quoted with them.

The stable statement, independent of settings, is structural: **the bytes an instruction
walker does not read in this region are FX-Map trees, FX-Map index arrays, and gradient ramp
tables.** All three are described elsewhere in this document. There is no residue in the
records-and-bytecode region that lacks an identified structure - only residue that a
particular walker configuration declines to visit.

## `blendingmode` is not in the parameter program either

With `blend` slot 4 identified as a pointer to the record's parameter program, one place
remained unchecked for the blend mode: the program itself. If the compiler lowers the mode
into arithmetic rather than storing an index, the number of distinct program shapes should be
about the number of modes Substance offers - roughly twenty.

Over 34,955 `blend` records with a decodable program:

    distinct opcode sequences          140
    sequences seen 10 or more times     82

    commonest shapes:
      len 1   x15,164   0A42
      len 68  x4,875    0A42 0551 0910 0910 0913 0900 085F 0523 0517 ...
      len 3   x2,646    0A42 1640 0A52
      len 7   x1,317    0A42 1640 0A52 1240 0A52 1240 0A52
      len 3   x1,205    0A42 0A53 0A52

**The commonest program, in 43% of all blend records, is a single instruction**: `0A42`, an
int input reference. That is not a blend mode - it is "fetch the opacity parameter". The
programs compute the record's *parameters*, exactly as the program-pointer finding says they
should, and they vary from one instruction to seventy-two because opacity can be a constant,
a driven parameter, or an arbitrary expression.

Nor does the class word carry it: class `0x0019` alone covers 32,465 of the records and holds
130 different program shapes, so the six class values in use cannot be distinguishing twenty
modes.

**So the blend mode is not in the record slots, not in the class word, not in the record
size, and not in the parameter program.** Four places, all checked. That is consistent with
what this document recorded as terminal - the compiler compiles the mode into the engine's
choice of operation rather than storing it as data - and it is now a stronger statement,
because the parameter program was the last place in the record where it could plausibly have
been hiding.

A reader cannot recover which blend mode an author chose. Everything else about a `blend`
node - its two or three inputs, its opacity, its output resolution and channel mode - is
recoverable; the mode is not.

### Correction: "compiled into the engine's choice of operation" is a guess, not a finding

The previous section concluded that the blend mode is absent by design, the compiler having
resolved it into the engine's behaviour. That explanation was asserted, not shown, and the
objection it has to answer is the same one that overturned the parameter-binding claim: **the
engine must blend somehow, so the mode has to be recorded somewhere.**

Searching every field of a `blend` record for one that could hold a twenty-value enum, over
34,960 records:

| field | distinct values | what they are |
|---|---|---|
| tag low byte | 2 | grayscale / colour |
| class word | 6 | layout and mode flags |
| header size | 16 | record sizes, 64% of them 24 bytes |
| tag high byte | 18 | **resolutions** - 0x88, 0x77, 0x66, 0x44, 0x55, 0xBB |
| slots 1-3, high halfword | 1 | always zero |

The only field with roughly the right cardinality is the tag's high byte, and its eighteen
values are the resolution field, confirmed against JPEG dimensions and manifest declarations.
Nothing else in the record comes close.

**So the honest position is narrower than the previous section claimed.** What is established
is a series of negatives: the blend mode is not in the record slots, not in the class word,
not in the record size, not in the tag, and not in the parameter program. Where it *is*
remains unknown, and the fact that it must exist somewhere means one of those negatives may
yet turn out to be a search that was too narrow - which is exactly what happened with input
uids, where a type filter hid 87% of the references.

Candidates not excluded: a field outside the record that indexes it, a distinction carried by
the FX-Map or program structures rather than a value, or a mode-specific filter id that the
source-count matching would not have separated from plain `blend`.

Recorded as **open**, not terminal. The difference matters: a terminal verdict says stop
looking, and this one has not earned that.

## `blendingmode`: ground truth at last, and a lead

Every previous statement about the blend mode in this document was made without ever reading
one from a source. The reason is a regex: the parameter is written

    <parameter><name v="blendingmode"/><relativeTo v="0"/>
      <paramValue><constantValueInt32 v="1"/></paramValue></parameter>

and the pattern used was `constantValueInt\d?`, which matches one optional digit and so fails
on `Int32`. It reported the parameter absent from all 1,151 blend nodes. **This is the eighth
too-narrow predicate in this document and the fourth caused by assuming a value's width.**

### What the sources actually say

| mode | nodes | share |
|---|---|---|
| absent (default) | 721 | 62.6% |
| 1 | 119 | 10.3% |
| 2 | 89 | 7.7% |
| 3 | 77 | 6.7% |
| 9 | 50 | 4.3% |
| 5 | 37 | 3.2% |
| 4, 6, 7, 8, 11 | 58 | 5.0% |

**Eleven distinct values, not twenty**, and nearly two thirds of blend nodes leave it at the
default. The median file uses exactly one mode; the most varied uses ten.

### Which binary field tracks it

With per-file mode counts available, the question becomes measurable: does any field's
diversity track the source's mode diversity? Over 59 paired files, correlating the number of
distinct modes a source uses against the number of distinct values each binary field takes
among that file's blend records:

    program shape     +0.729
    class + size      +0.518
    (blend count)     +0.497    <- control: bigger files have more of everything
    class word        +0.419
    record size       +0.378
    slot 5            +0.209

**Program shape is the strongest, and it is the only field that clearly beats the control.**
A file with more blends has more of every field by construction, so the blend count at +0.497
is the floor any candidate must clear; class, size and slot 5 do not clear it.

That revises the previous section's negative. The parameter program is not merely computing
opacity - its *shape* carries something that varies with the blend mode. The earlier
observation that 43% of programs are a single `0A42` instruction remains true and is
consistent: those are the default-mode blends, which are 62.6% of the corpus.

**This is a lead, not a finding.** +0.729 against a +0.497 control over 59 files is
suggestive, and the obvious next step is direct: take the paired files with several modes,
match each source blend node to its record, and check whether nodes sharing a mode share a
program shape. That requires the node-to-record correspondence that only instance-free files
provide, and no instance-free file in this corpus contains a blend.

### A program shape significantly associated with one mode

Exact node-to-record correspondence is unavailable for blends, but file-level co-occurrence
is testable. For each program shape appearing in three or more files, which modes are present
in *every* file containing it?

Mode base rates across the 67 paired files: mode 0 (default) 85%, mode 2 24%, mode 1 22%,
mode 3 21%, **mode 9 19%**, mode 5 16%, the rest below 14%.

| files | program length | modes present in all of them | p |
|---|---|---|---|
| **6** | **23** | **{9}** | **0.00005** |
| 6 | 21 | {2, 3, 9} | 0.0002 each |
| 4 | 21 | {0, 9} | 0.0013 |
| 3 | 95 | {0, 2, 3, 9} | - |

A 23-instruction shape occurs in six files and **every one of them uses mode 9**, against a
19% base rate. That is p = 0.19^6 = 5 x 10^-5, and with 27 shapes tested a Bonferroni
threshold of 0.0019 still leaves it significant by a factor of forty.

**So the blend mode is expressed in the parameter program.** That is the first positive
result on `blendingmode` in this document, and it displaces the assumption - never
demonstrated - that the compiler discards the mode into engine behaviour. The mode is in the
file; it is in the program the record's slot 4 points at; and at least one shape can be tied
to a specific mode value at p < 10^-4.

**What this does not establish.** File-level co-occurrence is weaker than node-level
identity: a shape found in files that use mode 9 is not proven to *be* mode 9's compiled
form, only to travel with it. The shapes associated with mode sets like {2, 3, 9} show the
association is not clean, which is expected when a file uses several modes and every shape in
it co-occurs with all of them.

The route to certainty is unchanged and still blocked: it needs a paired file with blends and
no `compInstance`, so that each source node maps to one record. No such file exists in this
corpus. But the question has moved from "where could it possibly be" to "which shape is which
mode", which is a much smaller question.

### How far file-level association reaches

Strengthening the test to a biconditional - a shape present exactly when a mode is present -
over 67 files and every shape appearing in three or more:

| mode | files using it | shape length | both | shape only | mode only | Jaccard |
|---|---|---|---|---|---|---|
| **9** | 13 | 70 | 8 | 2 | 5 | **0.53** |
| **9** | 13 | 19 | 7 | 1 | 6 | **0.50** |
| every other mode | - | - | - | - | - | **below 0.5** |

Two shapes track mode 9 at roughly half the union, and **no shape reaches that threshold for
any other mode**. The imperfection is what the confound predicts: a file using mode 9 also
contains library blends with their own modes, so a shape can appear without the mode and the
mode can appear without the shape.

Mode 9 being the only detectable one is consistent with it being an operation distinctive
enough to compile to a recognisable program, where the commoner modes may differ by a single
instruction that shape-equality does not isolate.

**This is the limit of what the corpus supports.** File-level co-occurrence establishes that
the mode is in the program - significantly, at p < 10^-4 - and identifies two candidate
shapes for one mode. Building a mode-to-shape table needs node-level correspondence, which
needs either a paired file with blends and no `compInstance`, or enough paired files that
single-mode files isolate each shape by subtraction. This corpus has neither: no instance-free
file contains a blend, and the 67 paired files give only 13 that use mode 9 at all.

**Summary of the `blendingmode` position**, which has changed materially:

* Not in the record slots, class word, size or tag - four exhaustive searches.
* **In the parameter program**, on a significant association at p = 5 x 10^-5.
* Two candidate shapes identified for mode 9; no other mode isolated.
* The earlier claim that the compiler discards the mode is **withdrawn** - it was never
  measured, and the evidence now points the other way.

## Float parameters are stored; integer parameters are not

The `blendingmode` regex failure prompted enumerating the source vocabulary rather than
guessing it. Every `constantValue*` element in the `.sbs` corpus:

| element | occurrences | element | occurrences |
|---|---|---|---|
| `constantValueFloat1` | 156,650 | `constantValueInt2` | 10,469 |
| `constantValue` (container) | 106,318 | `constantValueFloat2` | 6,980 |
| `constantValueFloat4` | 58,809 | `constantValueInt1` | 6,920 |
| `constantValueString` | 51,092 | `constantValueBool` | 6,869 |
| **`constantValueInt32`** | **29,758** | `constantValueFloat3` | 618 |
| | | `constantValueInt3`, `Int4` | 131 |

Twelve names. The pattern used for most of this document, `constantValue(Int|Float)\d?`,
misses four of them - `constantValue`, `String`, **`Int32`** and `Bool` - covering 194,037
elements.

### The consequence for the parameter-slot result

This document reports 88% recall of source parameter values in record slots, against a 13%
null. **That measurement used `constantValueFloat\d?` and therefore covered float parameters
only.** Integer and enumerated parameters were never tested.

Testing them now, over the same paired files:

| filter | integer values declared | found in slots | recall |
|---|---|---|---|
| `blend` | 101 | 30 | 30% |
| `transformation` | 24 | 0 | **0%** |
| `uniform` | 18 | 0 | **0%** |
| **total** | **143** | **30** | **21%** |

Against 88% for floats. And the 30% for `blend` is an upper bound - small integers collide
with slot contents by chance, which is the trap this document has met eight times.

**So the format treats the two kinds of parameter differently.** A float parameter is baked
into a record slot as a literal. An integer or enumerated parameter is not in the slots at
all.

### Which explains `blendingmode` and generalises it

`blendingmode` is written `constantValueInt32`. It is an enum, and enums are not stored in
record slots - which is why four exhaustive searches of the record found nothing, and why the
mode turned out to be in the parameter program instead.

That is no longer a fact about one parameter. **Every enumerated parameter in the format is
compiled into the program rather than stored as a value**, and a reader that recovers
parameters by reading record slots will recover the floats and silently miss the enums. This
document's parameter-slot map is, in that light, a map of the float parameters.

### Enum values do reach the program, partly as literals

If enumerated parameters are compiled rather than stored, some should survive as integer
constants in the record's program. Testing declared integer values (1 to 63) against the int
constants appearing in that filter's programs, with a null drawn from random values in the
same range:

| filter | declared | found | recall | null |
|---|---|---|---|---|
| `transformation` | 13 | 8 | **62%** | 0% |
| `blend` | 101 | 33 | 33% | 7% |
| `uniform` | 15 | 4 | 27% | 0% |
| **total** | **129** | **45** | **35%** | **5%** |

**A sevenfold lift over the null.** Enum values genuinely appear in the programs - this is
not the coincidence that inflated the slot measurement.

But recall is 35%, not 88%. Two thirds of declared enum values are not literals anywhere.
That fits what the `blendingmode` association found: the mode changes the program's *shape* -
which operations it uses - more often than it appears as a number the program reads.

### The complete picture of parameter storage

| parameter kind | in record slots | as program constants | otherwise |
|---|---|---|---|
| float | **88%** (null 13%) | - | baked literal |
| integer / enum | 21% (mostly chance) | **35%** (null 5%) | compiled into program structure |

Three mechanisms, and a reader needs all three. Reading record slots recovers the float
parameters and almost nothing else. Reading program constants recovers a third of the enums.
The remainder is not a value anywhere in the file - it is the difference between one sequence
of instructions and another, recoverable only by recognising which sequence a program is.

That is the deepest sense in which this format is *compiled* rather than serialised, and it
is the reason `blendingmode` resisted four exhaustive searches of the record: **there was
nothing there to find, and the thing that replaced it is a program's shape.**

## The program space is small enough to catalogue

If enumerated parameters are recoverable only by recognising which program a record carries,
the practical question is how many programs there are to recognise. Following each record's
program pointer over 150 specimens:

| filter | programs | distinct shapes | shapes in 5+ files | commonest | shapes covering 90% |
|---|---|---|---|---|---|
| `blend` | 74,787 | 223 | 59 | 40% | **25** |
| `transformation` | 53,927 | 215 | 62 | 26% | **37** |
| `levels` | 22,093 | 114 | 34 | 39% | **17** |
| `directionalwarp` | 14,402 | 51 | 19 | 40% | **9** |
| `blur` | 2,860 | 64 | 26 | 16% | 18 |
| `gradient` | 3,701 | 66 | 21 | 26% | 15 |
| `motionblur` | 4,997 | 54 | 17 | 44% | 14 |
| `uniform` | 2,343 | 44 | 13 | 64% | 8 |
| `passthrough` | 674 | 15 | 3 | 52% | 7 |

**About 150 shapes in total cover 90% of every parameter program in the corpus** - 25 for
`blend`, 37 for `transformation`, single digits for several filters. The commonest shape
alone accounts for a quarter to two thirds of each filter's programs.

And the shapes recur across files rather than being per-material: 59 of `blend`'s 223 shapes
appear in five or more distinct specimens, 62 of `transformation`'s. These are canonical
compiled forms, not incidental sequences.

### Why this matters

The parameter-storage finding said that enum values are often not a number anywhere in the
file - they are the difference between one instruction sequence and another. That sounds like
an unbounded problem and is not. **A lookup table of roughly 150 sequences would let a reader
recognise nine programs in ten**, and the association work has already shown that such a
table can be tied to source semantics: one 23-instruction shape sits at p = 5 x 10^-5 with
blend mode 9.

That is the concrete shape of the remaining work on this format. Not "decode the bytecode" -
that is done, at 99.9% of instructions catalogued - but *catalogue the programs*: enumerate
the canonical shapes per filter, and pair each with the source parameter setting that
produces it. The corpus supports the first half of that today. The second half needs paired
files that isolate one parameter at a time, which is a data-collection problem rather than an
analytical one.

## The short blend programs are size arithmetic, not blend modes

The `blend` program shapes fall into families separated by one or two instructions. Aligning
the commonest pairs shows exactly what varies:

    shape 0  (29,901 programs, 1 instruction)   0A42
    shape 2  ( 6,639, 3)   0A42  0A53  0A52     + int sub, int add
    shape 3  ( 4,598, 3)   0A42  1640  0A52     + int constant, int add
    shape 6  ( 1,556, 5)   0A42  1640  0A52  0A53  ...
    shape 10 (   881, 5)   0A42  1640  0A52  1240 ...

Every difference is **integer arithmetic**: `0A52` int add, `0A53` int sub, `1640` and `1240`
int constants. The base of the family is a single `0A42` - an int input reference - and the
variants append a chain of adds and subtracts against constants.

**These are not blend modes.** A program that fetches one integer input and adds a constant
to it is computing an integer, and the integer input a record most often reads is
`$outputsize`, which this document measured as the single most-referenced input in the corpus
at 4,780 references in one file alone. `$outputsize` is a type-8 `int2`.

So the commonest parameter program in the format, present in 29,901 of 74,787 `blend`
records, is **"output size equals `$outputsize`"**, and its variants are "`$outputsize` plus
a constant" - the relative-size setting that lets a node run at half or twice its parent's
resolution. That matches the resolution-inheritance behaviour documented throughout: records
that inherit carry the bare fetch, records that resize carry the arithmetic.

### Which relocates the blend mode

The shapes that associated with blend mode 9 were **19, 23 and 70 instructions long** - not
these. The short families are size computation, and the long programs are something else,
which is where the mode association was found.

That is a useful narrowing. A `blend` record's program is not one thing: the corpus contains
both trivial size expressions and 70-instruction computations under the same pointer, and
only the latter carry mode-associated structure. **A reader interpreting a parameter program
must first ask which parameter it computes**, and the answer is visible in the program's
type - the size programs are entirely `int` operations, while the mode-associated ones mix
`float` swizzles, comparisons and arithmetic.

## How many programs a record carries, and what they compute

If a record's blocks are one per driven parameter, their number and types should vary by
filter. Both do.

### Block count

| filter | 1 block | 2 blocks | 3+ |
|---|---|---|---|
| `levels` | **98%** | 1% | 0% |
| `gradient` | 96% | 4% | 0% |
| `uniform` | 93% | 6% | 0% |
| `blend` | 90% | 10% | 0% |
| `transformation` | 81% | 18% | 1% |
| `blur` | 67% | 32% | 1% |
| `directionalwarp` | 57% | **43%** | 0% |
| `motionblur` | 50% | **49%** | 1% |

**Almost every record carries one or two programs and never more than three.** The filters
that most often carry two are exactly those with a prominent scalar parameter of their own -
`motionblur`'s angle, `directionalwarp`'s intensity, `blur`'s radius.

### What each block computes

Classifying each block by whether its instructions are entirely `int` - the signature of the
`$outputsize` arithmetic identified above - or predominantly `float`:

| filter | block 0 int-only | block 1 int-only | block 1 float |
|---|---|---|---|
| `directionalwarp` | 67% | **1%** | **99%** |
| `motionblur` | 61% | **2%** | **98%** |
| `blur` | 37% | **1%** | **99%** |
| `transformation` | 35% | **76%** | 24% |
| `blend` | 53% | **69%** | 28% |

**The second block is sharply typed, and the type depends on the filter.** For `blur`,
`motionblur` and `directionalwarp` it is float in 98-99% of records - the filter's own scalar
parameter. For `transformation` and `blend` it is int-only in 69-76% - more size arithmetic.

Block 0 is not typed consistently anywhere, ranging from 35% int-only for `transformation` to
67% for `directionalwarp`.

### The consequence

**Block position does not determine which parameter a program computes.** A reader cannot
say "block 0 is the size, block 1 is the parameter"; the assignment varies by filter and by
record, and must be inferred from the program's own type and content - int-only arithmetic on
an `int2` input being size, float computation being a scalar parameter.

That is consistent with everything else this format does: it stores what the engine needs to
execute, in the order it was emitted, with no index or label to say what any of it is for.
The reader supplies the interpretation.

## A validated rule for classifying a parameter program

Block position does not say what a program computes, so the reader must infer it. The
manifest supplies ground truth: programs reference inputs by uid, and the manifest names
every uid. Classifying 432,815 programs by whether their instructions are entirely `int`,
and cross-tabulating against the first input each one reads:

| program type | reads `$outputsize` | reads `$randomseed` | reads a named parameter | reads nothing |
|---|---|---|---|---|
| **int-only** (167,843) | **92%** | 7% | **0%** | 1% |
| has float (264,972) | 51% | 0% | 3% | 46% |

**An int-only program reads `$outputsize` 92% of the time and a named parameter never.**
That validates the inference reached from the shape families: int-only arithmetic is the
output-size computation, and the rule is usable as stated -

    if every instruction in the program is int-typed, it computes the output size

with 92% precision and a 7% minority that computes a random seed, which is the other
integer-valued system variable.

Float programs split differently: half read `$outputsize` too - size-dependent float
arithmetic, a node scaling something by its own resolution - and **46% read no input at
all**, being pure constant expressions. Only 3% read a named parameter.

### That 3% is the real measure of how parameterised these materials are

A named parameter appears in a program only when the artist drove it with a function. Three
percent of float programs do that; the other 97% compute from system variables or constants.
Combined with the earlier finding that 88% of float parameter values are baked into record
slots as literals, the picture is consistent: **Substance materials are overwhelmingly
static once compiled**, with a small minority of genuinely dynamic parameters, and the
runtime adjustability a `.sbsar` offers comes from the engine re-evaluating those few
programs rather than from the graph being broadly parameterised.

### Correction: the materials are parameterised; the programs that read parameters are just rare

The previous section concluded from "only 3% of float programs read a named parameter" that
Substance materials are **overwhelmingly static once compiled**. That inference is wrong, and
the objection is the obvious one: a `.sbsar` demonstrably responds to its parameters at
runtime.

Scanning exhaustively for input references of any type, over 141 packages with four or more
named parameters:

    named (non-system) parameters declared      4,097
    read by at least one program                2,673   (65%)

    per file: median 88% of named parameters are read
    files where every named parameter is read   33 (23%)
    files where none is read                     0

**The median file has 88% of its named parameters read by a program, and no file has none.**
The materials are parameterised, thoroughly.

The two figures are both correct and measure different things. A named parameter appears in
few *programs* - most programs compute output size or a constant expression - but those few
programs cover most *parameters*. Three percent of 265,000 programs is about 8,000 programs,
which is ample to read 4,097 parameters.

**This is the denominator error again**, in its third form in this document: byte-weighted
against file-weighted inverted one conclusion, a monotonicity statistic counting constant
runs inverted another, and here a share-of-programs figure was read as a share-of-parameters.
The wording that would have caught it is mechanical - *"3% of programs" is not "3% of
parameters"* - and the check that did catch it was asking whether the conclusion contradicts
something already known about how the format behaves.

The corrected statement: **float parameter values are baked into record slots as literals in
88% of cases, and the parameters that are instead driven by programs are read by a small
minority of programs that nonetheless covers most declared parameters.** Nothing about the
format is overwhelmingly static.

### The unread 35% is walker coverage, not dead parameters

Splitting the named parameters that no decoded program reads into those the raw bytes contain
anyway and those genuinely absent, over 4,097 declared parameters:

    found in a decoded program        2,673   65%
    present in the body, not decoded  1,203   29%
    absent from the body entirely       221    5%

**Ninety-five percent of named parameters are physically present in the record body**, and
the gap between that and the 65% the walker reads is coverage, not deadness. A parameter
counts as "not read" here when *every* reference to it happens to fall in a region the walker
declines to visit - the FX-Map trees and the blocks its resync window does not reach.

So three separate figures now describe the same walker from different angles:

    97%  of body bytes covered
    94%  of body bytes covered in the median file
    68%  of present parameter references reached  (65 of 95)

The last is much lower than the first two and is the one that matters for parameter recovery.
Byte coverage is dominated by the large contiguous blocks the walker reads well; parameter
references are individual instructions that can sit anywhere, including in the small regions
it skips. **A decoder that is 97% complete by volume can still miss a third of a specific
feature**, if that feature is distributed differently from the bytes.

The residual 5% - 221 parameters with no reference anywhere in the body - are the only
candidates for genuinely unused parameters, and at that scale could equally be references
carried in a form this document has not identified.

### Correction: the parameter references are all decoded; the 68% measured a different walker

The previous section reported that the walker reaches only 68% of present parameter
references and drew a general lesson from it. **That figure is an artefact of which walker
was used.**

The measurement behind it scanned the body **linearly** - starting at `lo`, trying to decode a
block at each even offset, jumping to the end of whatever it found. Every other measurement
in this document walks **per record**, starting from each directory entry and following the
block chain with resync. Locating every raw occurrence of a named parameter uid and asking
whether it falls inside a block the per-record walker decodes:

    parameter uid occurrences in the body      21,853
    inside a decoded block                     21,768   (99.6%)
    not decoded                                    85   (0.4%)

**Essentially every parameter reference is reached.** The 29% "present but not decoded" was
the linear scan losing alignment - once it starts a block at the wrong offset it consumes
whatever length that misread header claims and can skip past real blocks entirely.

By owning record type, the references sit where the graph structure predicts: `blend` 29%,
`directionalwarp` 18%, `pixelprocessor` 15%, `fxmaps` 11%, `transformation` 8%.

**So the corrected coverage figures are:**

    97%    of body bytes, per-record walker
    94%    of body bytes in the median file
    99.6%  of parameter references reached

and the lesson drawn in the previous section - that a decoder complete by volume can miss a
third of a feature - **is withdrawn**. It was true of the linear scan and false of the walker
this document actually uses. The real lesson is narrower and duller: *two scanning strategies
were in use, and a result from one was reported as a property of the other.*

### Attributing the improvement correctly

Re-running the `BricksSubstance002` scan with the per-record walker finds **28 of 33 inputs**
against the linear scan's 8. But the two decode almost the same number of blocks - 9,265
against 9,243 - so the walker is not the difference.

The difference is the **type filter**. The original scan required `(op >> 8) & 3 == 2`, int
only, and the float and bool forms of `input reference` carry most named parameters. Both
corrections in the last two sections are real, and they are not the same correction:

* the **type filter** is why 8 became 28 in this file;
* the **linear-versus-per-record walker** is why parameter reference coverage measured 68%
  in one section and 99.6% in the next.

Conflating them would have credited the walker with a fix the filter made. Two defects in the
same measurement, found in the same week, and it would have been easy to assume the second
explained the first.

**What remains unreferenced in this file**: five of 33 parameters - `brick_rotation_strength`,
`bricks_rotation_random`, `bricks_displacement_random`, `mortar_dripping_amount`,
`roughness_random`. Every one is a rotation or randomisation control, which is the kind of
parameter an FX-Map consumes, and FX-Map trees are exactly where this walker's coverage is
weakest. That is a hypothesis with an obvious test for anyone extending the tree walker, not
a conclusion.

### Testing the FX-Map hypothesis on the five

All five parameters the walker misses in `BricksSubstance002` **do appear in the body** - none
is dead. Locating each raw occurrence and asking which record's span it falls in:

| parameter | occurrences | owning record type |
|---|---|---|
| `bricks_rotation_random` | 2 | **`fxmaps`** |
| `bricks_displacement_random` | 1 | **`fxmaps`** |
| `mortar_dripping_amount` | 1 | **`fxmaps`** |
| `brick_rotation_strength` | 8 | `pixelprocessor` (6), `blend` (2) |
| `roughness_random` | 1 | `blend` |

**Three of five are in FX-Map spans**, which supports the hypothesis - those are the tree
regions the walker enters only partially. The other two are not: `brick_rotation_strength`
appears eight times inside `pixelprocessor` and `blend` records, which the walker does read.

So the missing references have two causes, not one. Some are in FX-Map trees; others are in
ordinary records, in blocks the per-record chain does not reach - the tail after its resync
window gives up, or a block whose header the chain lands on mid-instruction.

The hypothesis recorded in the previous section was half right, and stating it as a
hypothesis rather than a conclusion was worth the caution: the obvious explanation covered
60% of the cases and a second mechanism covers the rest.

**Corrected accounting for this file:** 33 declared parameters, 28 reached by the walker, 5
present in the body but unreached - 3 in FX-Map spans, 2 in ordinary records. **Zero dead
parameters.**

## Record length is not stored because it is implied by the directory

An open question in this document has been which header field encodes a record's length. The
answer is that none does, and none needs to. The record directory is a **sorted partition of
the body**: a record runs from its own directory offset to the next one.

Measured over all 382 parsable specimens and 651,743 records:

    directory entries already in ascending offset order   382/382 files
    files with duplicate offsets                          0
    negative or zero gaps between consecutive offsets     0
    distinct gap sizes                                    1154   (min 4, max 234,440)

Zero duplicates and zero non-positive gaps across 651,743 records is not something a directory
of unordered handles produces; it is what a partition produces. The directory is not a lookup
table that happens to be sorted, it is the extent map.

The downstream check confirms it. Taking blend records, whose layout is fully known, and
computing the decoded extent - tag, slots, and any bytecode the slot-4/slot-5 program pointers
reach - against the next directory offset:

    blend records checked                       227,121
    decoded content overruns the next offset          13   (0.006%)
    decoded content ends within 4 bytes of it    195,550   (86.1%)

Thirteen overruns in 227,121 records, and 86% of records filling their gap exactly. The
remaining 14% under-fill, which is what common subexpression elimination predicts: a record
whose program pointer targets a program emitted inside an *earlier* record's span contributes
no bytecode of its own, so its extent stops short of the next offset.

**This retracts the search rather than answering it.** The earlier section "Applying the rule:
no header field encodes record length" searched 177 contiguous bitfields and reported a best
predictor of 64.6%. That search was well executed and its negative result was correct - there
is no such field. What was wrong was the premise that one had to exist. A length field is
redundant in a format whose directory is already ordered, and the compiler does not emit one.

The practical rule for a reader: **sort the directory, and record `i` occupies
`[offset[i], offset[i+1])`**, with the last record running to the start of the value table.
No field needs to be consulted, and the 0.006% overrun rate bounds the error.

## `blendingmode` is the low four bits of blend slot 1

The previous sections placed `blendingmode` in the parameter program on a file-level
association at p = 5 x 10^-5. **That was a confound, and this section replaces it.**

### The opening: count-exact pairs

The blocker was stated as needing "a paired file with blends and no `compInstance`", and no
such file exists. But instance-freedom is a whole-file property and the wrong thing to require.
What is actually needed is that *no extra blends were inlined* - a per-filter property. Testing
it directly, over the 69 paired non-Allegorithmic files that contain blend nodes:

    source blend nodes == binary blend records     7 files
    binary has more (inlining)                    58
    binary has fewer (elimination)                 4

**Seven files give node-level correspondence by counting.** The earlier claim that none exists
was checking a stricter condition than the problem needed.

### The programs, and the death of the mode-9 lead

| file | source modes | programs emitted |
|---|---|---|
| `LGMLtools__Substance_graphC` | {0} | `0A42 0A53 0A52` |
| `SubstanceTools__SDF` | {1} | `0A42` |
| `Sho__Fur` | {0, 0} | `0A42` x2 |
| `SubstanceDesigner__hblend` | {7, 7, 7} | `0A42` x3 |
| `LGMLtools__multi_blender` | seven 0s | `0A42` x7 |
| `substance-for-unity-extensions__TimelineExample` | seven 0s **and one 5** | `0A42` **x8** |

Modes 0, 1, 5 and 7 all compile to the same single instruction, and the file containing seven
mode-0 blends and one mode-5 blend emits eight identical programs. **The mode is not in the
parameter program.** That program computes opacity.

The earlier p-value was computed assuming files are independent draws. They are not: the paired
corpus comes from a handful of GitHub repositories, so files cluster by author, and authors have
house styles in both which modes they use and which library graphs they pull in. A shape shared
by six files from two repositories is one draw dressed as six. **Bonferroni corrects for the
number of tests, not for dependence between observations, and no amount of it rescues a
clustered sample.** This is a new failure mode in this document and worth naming as such.

### Where it actually is

The same seven files answer the question immediately, because slot 1 varies with the mode:

    mode 0 files      slot 1 = 0x100, 0x120, 0x130      low nibble 0
    mode 1 file       slot 1 = 0x101                    low nibble 1
    mode 7 file       slot 1 = 0x127                    low nibble 7
    TimelineExample   low nibbles 0,5,0,0,0,0,0,0   vs source modes 0,0,0,5,0,0,0,0

**The low four bits of blend slot 1 are `blendingmode`.**

The corpus-wide falsification test is the strong evidence. `blendingmode` takes exactly eleven
distinct values in the sources, 0 through 11. Over **227,121 blend records in 382 specimens**,
the low nibble of slot 1 takes values 0 through 11 and **never once takes 12, 13, 14 or 15**.

    nibble 0-11    227,121 records
    nibble 12-15             0

For contrast, the same nibble in filter 2's records is 12-15 in 167,037 cases, and filters 0, 6,
7 and 10 spread across all sixteen. A four-bit field with a hole covering a quarter of its range,
whose occupied range coincides exactly with a source enumeration's range, is that enumeration.

### The residue

Across all 69 paired files, comparing source mode multiset to slot-1 nibble multiset:

    exact match                                    7   (the count-exact files)
    source modes a sub-multiset of the nibbles     49  (consistent with inlining)
    containment violated                           13

The 13 violations are unexplained in detail and should not be papered over. Four of them are
files where the binary has *fewer* blend records than the source has blend nodes, so containment
cannot hold in principle - dead-code elimination or uncooked graphs in a multi-graph `.sbs`. The
rest are Hard-Science-Old files whose sources declare only default-mode blends while their
binaries show no nibble-0 records at all, which needs the same explanation and has not been
confirmed. **The nibble identification rests on the 227,121-record range test and the seven
count-exact files, not on the containment test, which is the weakest of the three.**

## Slot 1 is two different things, and the shared reference was a too-permissive predicate

The finding above forces a re-examination. The sections "`blend` slot 1 characterised: a
reference, but not an input" and "The shared reference is a general mechanism, and it occupies
slot 1 of eight filters" concluded that blend slot 1 is a backward record reference. It is not.

### How the earlier reading passed its tests

The evidence offered was that in `PavingStonesSubstance003` the 1,743 blends draw slot 1 from
28 distinct values, "every one of which is a valid record index pointing at a real record". That
predicate has **no power**: in a file with thousands of records, essentially every small integer
is a valid record index. Measured across the corpus, 99.4% of blend slot-1 values are less than
their file's record count - which the reading counted as confirmation, when it is what the null
also predicts.

**This document has now accumulated eight too-narrow predicates that missed real data. This is
the first too-permissive one, and it did the opposite damage: it manufactured a finding.** A
predicate that nearly everything passes cannot support an identification, and its pass rate
should have been reported against a null from the start.

### The discriminator

A record index in a file with thousands of blends must take thousands of values and must set
bits 6 and 7 routinely. A packed bitfield has a small global vocabulary and structural holes.

    fid  records   distinct values   max in one file   bit 6    bit 7
      1   227,121       126                54           0.01%    0.00%
      2   170,102        52                31          29.19%    2.14%
     15    63,453        93                36          56.14%    0.65%
     12    42,220        10                 7           0.00%    0.00%
     20    38,335        22                13           0.00%    0.00%
      4    28,787        72                25           0.82%   67.12%
     11    10,978         6                 6           0.00%    0.00%
     21     1,670         6                 4           0.00%    0.00%
    ----
      6    13,025     8,248             2,044          32.90%   34.30%
      0    13,156     5,665               965          47.24%   45.07%
      7    19,876     5,571             1,531          45.32%   44.35%
     10    10,858     5,237               918          47.82%   45.59%
     19     1,782     1,526                57          50.17%   49.21%
      3     5,309     1,461               107          25.22%   24.15%

**Two populations, and they do not overlap.** The upper group's slot 1 is a packed parameter
word: 126 distinct values for blend across the entire 382-file corpus, never more than 54 in any
single file, with bits 6 and 7 structurally dead. The lower group's slot 1 behaves like a real
reference - thousands of distinct values, up to 2,044 within one file, high bits set about half
the time as an offset would.

### What this explains

The anomalies the earlier section reported are exactly what a misread bitfield produces:

* **50% resolution agreement, "chance to within a percentage point."** Reading a bitfield as a
  record index selects an arbitrary record, so its resolution agrees at the base rate. The
  section correctly observed this was chance and correctly concluded slot 1 is not a data
  input; it drew the wrong inference, that it is a different *kind* of reference.
* **"51% of targets referenced five or more times", one 472 times.** With only 126 values in
  existence, enormous fan-out is arithmetic, not structure.
* **The "hierarchy" the shared reference appeared to form**, and its r = 0.902 correlation with
  dependency count, are now suspect for the bitfield filters and need re-deriving over the
  pointer group alone.

### What survives

The operationally important conclusion of the earlier section is **unchanged and now better
founded**: slot 1 must not be treated as an edge. It was right that including it would add
105,539 spurious edges. It is simply not a reference at all for these filters - it is where the
compiler stores small enumerated parameters, and `blendingmode` is the first one decoded.

The blend slot-1 bit budget, over 227,121 records:

    bits 0-3    blendingmode, values 0-11        confirmed
    bit 4       set in 45.03% of records         unknown
    bit 5       set in 23.08%                    unknown
    bits 6-7    set in 0.01% / 0.00%             structurally unused
    bit 8       set in 76.66%                    unknown
    bits 9-11   set in 0.30% / 0.06% / 0.14%     unknown
    bits 12+    never set

Eight filters have a slot-1 parameter word of this kind. One field in one of them is now read.

## Generalising the count-exact method: a systematic sweep, and what it could not deliver

The `blendingmode` result came from count-exact paired files - files where a filter's source
node count equals its binary record count, so no library instance was inlined for that filter.
That condition is per-filter, so it can be applied to every filter at once.

    filter            fid   paired files   count-exact   nodes
    bitmap             16        21             15         64
    pixelprocessor     20        25             15         53
    normal             18        36              9         12
    gradient            0        36              8         10
    transformation      2        61              8         41
    blend               1        69              7         23
    levels             15        36              4         11
    distance           21        14              4          7
    uniform             6        51              3          8
    warp                7        21              3         10
    blur               10        18              3          9
    fxmaps              4        10              2          4
    shuffle             3         3              1          5

Ground truth exists for every named filter. Enumerating every small-vocabulary source parameter
and testing it against every contiguous bitfield - slots 1 to 6, shifts 0 to 16, widths 1 to 5,
each plausible default - gives a search over roughly five hundred fields per parameter.

**The sweep re-derived `blendingmode` at slot 1, shift 0, width 4, default 0, in all seven
files, without being told.** That is the control, and it passed.

It produced no other identification that survives corroboration. That negative took three
further tests to establish, and the way it failed is the useful part.

### A false positive that beat its permutation null

The sweep's best new candidate was `pixelprocessor.colorswitch` at slot 6, bit 1: a **unique**
match - the only field in the entire search space consistent with every one of eleven files,
drawn from six distinct repositories, two of them with within-file variation. After the
file-clustering error earlier in this document, repository diversity was checked first, and it
looked clean.

A permutation null made it look stronger still. Shuffling the parameter values across files two
hundred times and re-running the sweep:

    blend.blendingmode         real: 2 fields    null found any match:  0/200
    pixelprocessor.colorswitch real: 1 field     null found any match:  0/200

Zero of two hundred. On that evidence the match is significant at p < 0.005.

**It is still wrong.** `colorswitch` decides whether a node outputs colour, so it must agree
with the record's colour bit - the low bit of the type byte, established long ago. Measured over
all 38,324 pixelprocessor records in the corpus, slot 6 bit 1 agrees with the colour bit **40.7%
of the time**, which is worse than chance-adjacent. A field that disagrees with a necessary
consequence of its own meaning is not that field.

The mechanism of the failure is that `pixelprocessor` takes a variable-length input list - slot
1 is the arity, slots 2 through n+1 are the inputs - so **slot 6 is not a fixed field at all**.
It means different things in records with different arity. Re-indexing relative to the input
list, every bit of slots n+2 through n+5 agrees with the colour bit at 49-51%, or at 23.6%,
which is simply the marginal rate for a bit that is always zero. There is no such field.

### Why the permutation null was not enough

A permutation test destroys file-level structure, so it rejects the hypothesis "this match is
random". It does not reject "this field tracks something else that shares the parameter's
file-level structure". In the count-exact pixelprocessor files, the arity happens to be nearly
constant, so slot 6 lands on a consistent word, and that word correlates with the same file-level
property `colorswitch` correlates with. The permuted samples have no such property to track, so
they match nothing - and the null returns zero while the alternative hypothesis is very much
alive.

**This is a distinct error from the file-clustering one earlier in this document, and the fix is
different.** Clustering was solved by counting repositories. This is not solved by any
resampling of the same data: it needs an *external* consequence of the proposed meaning, tested
on records the sweep never saw. The corpus-wide colour-bit check is exactly that, and it is what
killed the candidate. The `blendingmode` identification passed the same kind of test - zero of
227,121 records outside the source enumeration's range - which is why it stands and this does not.

The rule this yields, and the one used from here on: **a multiset match is a hypothesis
generator, never an identification. An identification requires a consequence tested outside the
matched set.**

### What the sweep did verify: `colorswitch` is the type byte's colour bit

The candidate's failure pointed at the right answer. Testing the colour bit directly against
source `colorswitch` over the count-exact files, with a single default per filter rather than a
default fitted per file:

    filter            files   matched   default
    gradient              8       8        1
    pixelprocessor       15      14        1
    distance              4       4        0
    fxmaps                2       2        1
    uniform               3       2        1
    bitmap               15       9        1
    ----
    total                47      39

Thirty-nine of forty-seven, and the defaults are filter-specific, which is how Substance filter
defaults actually behave. `bitmap` is the clear exception at 9/15, and for a coherent reason: a
bitmap record's channel count comes from the image it loads, not from a parameter, so the
colour bit can disagree with the declared `colorswitch` without either being wrong.

This was always the structural reading of the type byte - `2 x filter_id + is_colour` - but it
had never been checked against a source parameter. It has now been, and `colorswitch` is where
it goes. No separate bitfield carries it, which is why the sweep's attempt to find one produced
an artifact.

### Position after the sweep

* `blend` slot 1 bits 0-3 = `blendingmode`. Confirmed, two independent tests.
* `colorswitch` = the type byte's low bit, for every filter except `bitmap`. Verified.
* `pixelprocessor` slot 1 = input arity. Re-confirmed; slots past it are not fixed fields.
* Every other small-vocabulary parameter - `format`, `tiling`, `filtering`, `mipmapmode`,
  `input2alpha`, `combinedistance`, `culling` - remains **unlocated**. The sweep found matches
  for several, and none of them survives a consequence test.
* Blend slot 1 bits 4, 5 and 8, set in 45%, 23% and 77% of records, are still unread.

The count-exact corpus is the binding constraint: 12 nodes for `normal`, 10 for `gradient`, 7
for `distance`. Parameters that are rarely set non-default cannot be pinned from samples that
small, and no amount of statistical care substitutes for the observations.

## A disassembler, and the closure of the unnamed opcodes

Everything in this document about bytecode has been done with ad-hoc decoders written per
question. `disasm.py` is the standing tool: it renders a program at a pointer as a listing,
with value numbering, type and component suffixes, immediates decoded to floats or integers,
and forward operand references flagged with `!` - the marker that says a decode has gone wrong,
since three-address code numbers results contiguously and an operand can only name an earlier
one.

    ; program @133702  2 instructions
      %0    0A48  op08.i2        %2!, %7!
      %1    0900  const.f1       1

That listing is the first output it produced, and it settled the question it was built for.

### The five unnamed opcodes are phantoms

`0B19`, `0A48`, `0448`, `0A3D` and `1EB8` have stood as the last unnamed entries in the
catalogue, with a standing guess that three were sampler-related. They are not instructions.

The catalogue was built by `isa_census.py`, which **scans** code regions run by run. OPCODES.md
described it as "walking records to their bytecode, not by scanning"; that description was
wrong, and the error mattered, because the difference between the two methods is exactly what
these five opcodes are.

Re-censusing by following every record slot as a candidate program pointer - a deliberately
over-permissive walk that decodes 30,038,253 instructions, 2.5x the catalogue's count, because
it follows false pointers too:

    opcode   scan census          record-walk census
    0448     835 in 172 files     0
    0A3D     149 in  65 files     0
    0A48   1,215 in  58 files     1, with a forward operand reference
    0B19   1,358 in 108 files     0
    1EB8      95 in  51 files     0

    control  0900 const.f1  2,940,814      0A42 inputref.i2  524,740

**A decoder permissive enough to find 2.5x too many instructions still never finds four of the
five.** The single `0A48` it does find is the listing above, whose operands `%2` and `%7`
reference values that do not exist yet.

The direct test confirms it. Scanning every 2-byte position in 120 specimens and classifying
each hit against the set of real instruction boundaries:

    on a real instruction boundary                  0
    inside a decoded program, but misaligned      680
    outside every decoded program              12,189

**Zero of 12,869.** The 680 misaligned hits sit almost entirely inside the 4-byte immediate of
a constant; the 12,189 others are in record headers, pointer slots and the value table. `0B19`
is the clearest case - 8,897 of its 8,931 occurrences are not in code at all, consistent with
its independent identification as a record class word.

The mechanism was already documented here for linear scanning: a scan that loses alignment
turns arbitrary data into plausible instructions. The length rule accepts any word in
`0x0400`-`0x7FFF`, which is about half of all 16-bit values, so misaligned data decodes as code
more often than not. What was missing was the recognition that the opcode census itself was
built on a scan and had inherited the artifact.

**The instruction set is now 41 operations in 63 type-specific forms, all named.** Four
operation ids - `0x08`, `0x19`, `0x38`, `0x3D` - are withdrawn, and the "three probably
sampler-related" guess is withdrawn with them.

### The wider lesson, which is the same one twice in one session

The earlier section in this session found that a multiset match beat a permutation null and was
still wrong, because the null tested against randomness rather than against a rival explanation.
This is the same shape: the catalogue's own evidence for these opcodes was that they *appear* -
835 times, in 172 files - and appearance was never tested against the rival explanation that the
decoder manufactures them. Frequency and file-spread are not evidence of existence when the
measuring instrument produces the thing it measures. Both errors are fixed by the same move:
find a consequence the rival explanation cannot also produce. Here it was instruction-boundary
alignment, and it separated the two hypotheses 12,869 to 0.

### The disassembler's first real finding: the sampler index

The listing above showed `samplecol` self-referencing - `%1 = samplecol %0, %1` - which cannot
happen in contiguously-numbered three-address code. The second token is not a value number.

Over 94,472 `samplecol` and 36,741 `samplelum` instructions:

    second token = 0        92.2%  /  92.0%
    second token = 1         4.9%  /   4.1%
    distinct values            25  /     32
    >= own index (impossible)  0.5% /   0.6%

A value number in programs of this size would spread across the whole value space. Twenty-five
distinct values corpus-wide, 92% of them zero, is an **immediate sampler index**: which input
image the instruction reads. `samplecol %pos, #1` samples input 1.

This refines an earlier over-correction. When the immediate-stripping rule was first applied it
was noted that `samplecol`'s tokens "are both operands", which was right that the whole
instruction is not an immediate and wrong that neither token is. Token 0 is the coordinate;
token 1 is an immediate.

For a reader this is directly useful: it is how a `pixelprocessor` names which of its inputs
each sample comes from, and it connects the bytecode to the record's input list.

### What the listing decodes to

The program above, read straight off:

    %0  = $pos
    %1  = samplecol(%0, input 1)          RGBA at this pixel
    %4  = max(%1.r, %1.g)                 via swizzle
    %7  = min(...)
    %8  = (%4 == %7)
    %9  = samplelum(%0, input 0)
    %12 = (%9 - %7) / (%4 - %7)
    %13 = select(%8, %9, %12)

That is the standard **saturation** term of an RGB-to-HSL conversion, with the
`max == min` case guarding the division by zero. Nobody told the disassembler any of that; it
falls out of the opcode names assigned by other means. **A recognisable, correct algorithm
emerging from an independently-derived opcode table is the strongest semantic confirmation the
names have received** - stronger than the constant-operand and arity checks recorded earlier,
because it tests the whole table at once against a known algorithm.

## Do programs read the record's slots? Almost never - and the exceptions are the interesting part

With a disassembler the question becomes decidable. Variable slots are written by `set` (0x07)
and read by `get` (0x04). **A `get` of a slot that no earlier `set` in the same program wrote
must be reading a value the engine placed there** - that is the signature of a program taking
input from its record.

Over 444,000 decoded programs:

    programs with a `get` of a never-set slot     22,151   (5.0%)

    by filter:
      blend           130,713 programs     0.0%
      transformation   93,839               0.0%
      levels           30,593               0.0%
      warp             18,135               0.0%
      blur              6,875               0.0%
      uniform           5,657               0.0%
      fid 12           37,643               0.0%
      pixelprocessor   50,122               5.4%
      fxmaps           49,516              39.2%

**For every ordinary filter the answer is exactly zero.** Parameter programs are closed
expressions. The record points at its program; the program does not read back into the record.
That is a clean architectural fact and it simplifies a reader considerably - a program can be
evaluated with no reference to the record that owns it.

The two exceptions are the filters that have per-invocation state. `fxmaps` runs its program
once per pattern iteration and `pixelprocessor` once per pixel, and those are precisely the
programs that read slots nothing in them wrote. The engine seeds the variable frame before
entry. The slots read this way are concentrated: slot 0 (48.3%) and slot 4 (35.7%) account for
84% of all such reads.

### What a program does take from outside

Three channels, and only three:

1. **System variables**, operation `0x01`, with an immediate selecting which. There are exactly
   **five** in the whole corpus.
2. **Graph parameters**, via `inputref` (`0x02`) carrying a u32 uid - the mechanism already
   documented.
3. **Input images**, via the sampler-index immediate on `samplecol`/`samplelum` identified
   above.

Nothing else crosses the boundary.

## The five system variables, four of them named

The sources name their system variables directly, and the corpus uses nine:

    $number 1,177   $pos 412   $size 358   $sizelog2 169   $time 62
    $normal_map_format 8   $tiling 2   $outputsize 2   $randomseed 1

The binary has five distinct `0x01` immediates:

    opcode  imm  comps    count      filters using it            consumed by
    0541    #3     2     52,464     blend 38%, fid12 29%, warp   sub 57%, swizzle 43%
    0541    #1     2     37,053     transformation 92%           swizzle 91%, div 4%
    0541    #8     2     17,740     pixelprocessor 100%          swizzle 27%, mul 23%
    0501    #10    1        658     fxmaps 100%                  gt 26%, add 24%
    0501    #0     1         19     transformation 84%           swizzle 46%, mul 46%

A file-presence test identifies only one of them - `#8` matches `$pos` at Jaccard 0.83, and
nothing else reaches 0.5, because these variables co-occur heavily and library inlining drags
uses of all of them into most files. Following the rule established earlier in this session, a
presence match is a hypothesis and needs a consequence.

### The consequence test that splits `$size` from `$sizelog2`

`$sizelog2` is a base-2 logarithm. Arithmetic on it happens in the log domain - **you subtract
to divide, and you must `exp2` to get back to a linear size**. `$size` needs neither. So the
forward taint cone of the right immediate should be full of `exp2` and the wrong one should have
almost none.

Propagating taint forward from each system variable through every non-immediate operand:

    immediate   programs   exp2 downstream   dominant operations in the cone
    #3 (f2)       52,418        78.9%        sub 21%, min 20%, exp2 17%, swizzle 15%
    #1 (f2)       27,893         0.1%        swizzle 24%, div 12%, mul 9%, select 9%
    #8 (f2)       16,093         0.5%        add 22%, max 19%, samplecol 18%, min 10%
    #10 (f1)         537         0.0%        add 22%, mul 17%, sub 12%, floor 9%

**78.9% against 0.1% - a separation of nearly 700x.** That is not a marginal call.

    #3  = $sizelog2     log-domain arithmetic, exp2 to return to linear
    #1  = $size         linear arithmetic, divides to normalise
    #8  = $pos          feeds samplecol/samplelum as the sampling coordinate
    #10 = $number       fxmaps-only scalar; $number is the only FX-Map counter the
                        source vocabulary contains ($depth never appears)

`#8 = $pos` now rests on three independent legs: the presence test at 0.83, its exclusive use by
`pixelprocessor`, and the fact that 18% of its taint cone is `samplecol` - a coordinate is what
you sample at.

`#0` remains **tentative**. Nineteen occurrences is too few for any test, and its only support is
a Jaccard of 0.78 against `$time`, which is a presence match of exactly the kind this document
has now twice found insufficient. It is recorded as a guess and labelled as one.

### Reading the earlier blend result in this light

The section "The short blend programs are size arithmetic, not blend modes" observed that 43% of
blend programs are a single instruction and the short ones compute sizes. That is now explained
mechanically: `#3`/`$sizelog2` is 38% blend by usage, and blend's parameter programs are doing
log-domain size arithmetic to resolve relative resolutions. The observation was right and its
cause is now visible.

### The remaining blend bits, partially constrained

Using the newly established record extent, the header can be separated from the inline bytecode:
the header runs from the record start to the first program that begins inside its own span.

    5 header slots   63,318 records  32.4%
    6 header slots  130,052          66.5%
    7 header slots    2,155           1.1%

    bit 4 = 1  ->  6 slots in 98% of records
    bit 8 = 0  ->  6 slots in 98%
    bit 4 = 0  ->  5 slots in 59%, 6 in 41%
    bit 8 = 1  ->  5 slots in 42%, 6 in 56%

Bits 4 and 8 each **imply** a six-slot header when set and clear respectively, but neither
predicts the five-slot case, so no rule of the form "this bit means an extra slot" survives.
They constrain the layout without determining it, and are recorded as constraints rather than
identifications. Bits 9-11, set in 0.1-0.3% of records, remain untouched.

## The colour bit as a filter discriminator, and `hsl` identified at last

With `colorswitch` verified as the type byte's low bit, that bit becomes a **semantic probe**:
some filters can only produce colour, some can only produce greyscale, and most pass their
input's channel count through. Censusing it per filter id over all 382 specimens:

    fid  name              records   files   colour output
     18  normal              1,000     282     100.0%     <- control: normal maps are RGB
     14  ** unnamed **         555     167     100.0%
     20  pixelprocessor     38,335     258      74.4%
      8  ** unnamed **         405      79      47.7%
      3  shuffle             5,309     251      47.3%
     16  bitmap              1,095     152      42.6%
      6  uniform            13,025     314      34.7%
      0  gradient           13,156     277      15.8%
      1  blend             227,121     331       5.6%
     22  ** unnamed **         909     151       5.2%
     21  distance            1,670     175       4.6%
     13  ** unnamed **         931     173       4.4%
     12  ** unnamed **      42,220     239       3.5%
     11  ** unnamed **      10,978     262       2.9%
      2  transformation    170,102     345       2.1%
     19  ** unnamed **       1,782     109       1.8%
     15  levels             63,453     315       1.4%
      4  fxmaps             28,787     306       1.0%
      7  warp               19,876     246       1.0%
     10  blur               10,858     264       0.3%

`normal` at exactly 100% is the control that makes the probe trustworthy: a normal map is RGB
by construction and 1,000 records agree without exception.

### `hsl` = filter id 14 (`0x1C`/`0x1D`)

`hsl` was explicitly left unassigned earlier in this document: it was reachable only by
elimination in a single specimen, and `time_var_test` contradicted it by having an `hsl` node
and no `0x1C` record. Five independent lines now converge.

1. **Colour exclusivity.** `hsl` manipulates hue, saturation and lightness, which requires
   three channels - it cannot operate on greyscale. Filter 14 is **100% colour over 555
   records in 167 files**, and it is the *only* unnamed filter that is. Among unmapped source
   filters `hsl` is likewise the only colour-exclusive one.
2. **Arity.** `hsl` takes one input; the edge map gives filter 14 one input slot.
3. **Presence.** Jaccard 0.79 between "source uses `hsl`" and "binary has filter-14 records" -
   nothing else in the matrix exceeds 0.55.
4. **Count correlation.** 0.92 across the paired files, the highest in the matrix.
5. **Exact counts.** 20 of 29 files match exactly, across seven distinct repositories:

        SBRustyTreadPlate            6 = 6      DLG-Tools__Clean_Steel_01    1 = 1
        UHL3D-Stylized_Sand_Rocks    6 = 6      DLG-Tools__US_Flag           1 = 1
        Hard-Science-Old__Rockface   4 = 4      ... and 15 more

   Of the nine that differ, five have **more** filter-14 records than `hsl` nodes, which is
   what library inlining produces. Four have `hsl` and no filter-14 record - the
   `time_var_test` situation - which dead-code elimination explains and which is now clearly
   the minority case rather than a refutation.

The old counter-example was one file weighed against one elimination. It is now one class of
explicable exception weighed against twenty exact matches, a 0.92 correlation and a
100%-colour signature that only one filter in the format has.

### The remaining unnamed filters, and why they stay unnamed

Filter 12 is the prize - 42,220 records, the fourth commonest type in the format, and still
anonymous. The evidence points at `directionalwarp` without settling it:

    arity            filter 12 has two input slots; directionalwarp takes two inputs   ok
    containment      filter-12 count >= directionalwarp count in 100% of files          ok
    colour           3.5% colour; directionalwarp passes its input through            ok
    presence         Jaccard 0.55 - the best in the matrix, but not decisive
    correlation      0.28 - weak

Containment at 100% is necessary but not sufficient: a filter that is simply *common* satisfies
it against any rare source filter. The correlation of 0.28 is the problem, and until a
consequence test separates `directionalwarp` from the alternatives this stays a hypothesis.
By the rule adopted earlier this session, that is where it stops.

Three weaker leads, recorded as leads:

    filter 13   sharpen        containment 100%, correlation 0.42, 4.4% colour
    filter 17   text           presence 0.75 on four files, no edge-map entry
                               (text is a generator with no inputs) - consistent but tiny
    filter 19   passthrough    correlation 0.77, but containment only 19%

Filter 11 is the interesting negative. At 2.9% colour it looks greyscale-biased, and
`grayscaleconversion` is the obvious candidate on that basis - but `grayscaleconversion`
outputs greyscale **by definition**, so its records must be 0% colour, not 2.9%. Three hundred
and eighteen colour records falsify it outright. The candidate that the colour probe suggests
is the one the colour probe rules out, and filter 11 has no remaining candidate that fits both
its arity and its channel behaviour.

**Filter table after this section: 14 of 21 filter ids named**, covering **91.2%** of all
records - 594,342 of 651,743. (An earlier draft of this line said 96.4%; that figure was
asserted rather than computed and is wrong.) The unnamed 8.8% is concentrated almost entirely
in filter 12, which alone is 6.5%.

## A connectivity test for filter identity, killed by its own controls

Filter 12 needs evidence orthogonal to counts. Connectivity is the obvious candidate: a
`directionalwarp` is fed by particular kinds of node, and if the binary's filter-12 records are
fed by the same mix, that is independent support.

Building both profiles - for each source filter, the distribution of its inputs' filter types;
for each binary filter id, the distribution of its edge targets' filter ids, resolved through
the established rule that **edge slots hold backward record indices, not offsets** - and
comparing by cosine similarity.

**The controls fail, and they fail badly.** Running known filters through the same test:

    source filter        vs fid12  fid11  fid19  fid13  fid22   fid8   fid14    vs OWN fid
    blur (own fid 10)      0.838  0.687  0.765  0.804  0.721  0.636  0.671        0.205
    normal (own fid 18)    0.840  0.636  0.977  0.971  0.836  0.682  0.832        0.757
    distance (own fid 21)  0.559  0.499  0.711  0.693  0.730  0.455  0.620        0.054
    levels (own fid 15)    0.822  0.712  0.870  0.911  0.847  0.797  0.870        0.914

`blur` matches filter 12 at 0.838 and its own filter at 0.205. `distance` scores 0.054 against
the filter it actually is. `normal` prefers filter 19 at 0.977 over its own at 0.757. A test
that ranks a filter's true identity below six wrong answers has no discriminating power at all,
and the candidate scores it produced - `sharpen` at 0.917 against filter 13, which would have
been very easy to accept - are worthless.

Two causes, both structural. Nearly every filter is fed by `blend` and `levels`, because those
are 45% of all records, so every profile resembles every other. And the source side is starved:
most source edges point at `compInstance` nodes or graph input bridges, which have no `<filter>`
element and therefore no type, leaving `directionalwarp` with **ten usable edges** in the entire
paired corpus and `sharpen` with three.

**Recorded as a dead method, not a dead question.** Had the controls not been run first, filter
13 would now be labelled `sharpen` on a 0.917 similarity. That is the third time this session a
plausible number has failed a check, and the only reason it was caught is that the control was
computed in the same pass as the result rather than afterwards.

One byproduct is worth keeping. Filter 19's inputs are **94% `blend`**, far more concentrated
than any other filter's - the next highest is filter 13 at 67%. Whatever filter 19 is, it sits
almost exclusively downstream of blends. `passthrough`, the current lead for it, is fed by
`passthrough` 36% and `uniform` 25% in the sources, which does not match. That is a genuine
discrepancy and it weakens the `passthrough` lead rather than supporting it.

## Housekeeping: unconfirmed filter names are sitting in the scripts

`edgeaudit.py` carries a name table used to label its output:

    0x10 emboss   0x16 motionblur   0x18 directionalwarp   0x1A sharpen
    0x1C hsl      0x26 passthrough  0x2C curve

**None of these seven was ever confirmed in this document**, and one - `hsl` - was explicitly
recorded as unassigned while the script was already printing it as a fact. They are working
hypotheses from an earlier session that leaked into tooling output, where anything printed in a
labelled column reads as established.

Today's independent derivation of `hsl` = filter 14 = `0x1C` agrees with that table, which is
mild corroboration of the others but no more than that: the table was written before the
evidence existed, so its agreement is a coincidence of a good guess, not a second measurement.
The other six remain unconfirmed, and `passthrough` = `0x26` now has evidence against it.

The lesson is narrow and practical: **a script that prints a name is asserting one.** Any
tooling in this project that labels an unconfirmed id should mark it - `0x18?` rather than
`directionalwarp` - so that a reader of the output cannot mistake a hypothesis for a result.

## Filter 12 = `directionalwarp`, on a structural constraint rather than a count

The count-based tests could not separate filter 12 from its alternatives, and the connectivity
test failed its controls. A third property does the job: **which of a filter's inputs are
required to be greyscale.**

A warp-family filter takes an image and a *control map* - an intensity or gradient field - and
the control map is single-channel by construction. That is a hard constraint in the format, not
a tendency, so it should show as an exact zero.

Censusing the colour bit of every edge target, per filter and per slot:

    filter          slot     edges    target colour    own colour
    warp               1    19,876         1.0%           1.0%     <- control: image input
    warp               2    19,876         0.2%           1.0%
    warp               3     1,691         0.0%           2.4%     <- control: intensity input
    normal             2     1,000         0.0%         100.0%     <- control: height in, RGB out
    blend              2   227,121         5.6%           5.6%     <- control: both pass through
    blend              3   227,121         5.6%           5.6%
    ----
    ** fid 12 **       2    42,220         3.5%           3.5%     <- passes colour through
    ** fid 12 **       3    42,220         0.0%           3.5%     <- greyscale, no exceptions
    ** fid  8 **       2       405        47.7%          47.7%
    ** fid  8 **       3       405         0.0%          47.7%

The controls behave exactly as the format requires: `warp`'s image slots track the record's own
channel count while its intensity slot is zero, and `normal` takes a greyscale height map while
being 100% colour itself. `blend`'s two slots both track the record, because a blend composites
two images of the same kind.

**Filter 12 has the warp signature: slot 2 tracks the record's colour, slot 3 is greyscale in
0 of 42,220 edges.** So does filter 8, at a much smaller scale.

### Which warp-family filter

Among unmapped source filters, exactly two take an image plus a greyscale control map:
`directionalwarp` (input1 + inputintensity) and `emboss` (input1 + inputgradient).
`dirmotionblur` takes one input, its direction being a parameter, so it is excluded.

Containment separates them, and separates them in **both** directions:

    directionalwarp vs filter 12     binary >= source in 17 of 17 files   (100%)
    directionalwarp vs filter  8     binary >= source in  0 of 17 files   (0%)
    emboss          vs filter  8     binary >= source in  1 of  1 file
    emboss          vs filter 12     binary >= source in  0 of  1 file

Inlining can only *add* records, so a true identification must satisfy containment in every
file. Seventeen files where `directionalwarp` needs filter 12 and cannot use filter 8, against
zero the other way, assigns them uniquely given that only two candidates exist.

    Hard-Science-Old__flowingLava      17 directionalwarp  ->  63 filter-12 records,  0 filter-8
    DLG-Tools__Mineral_Ore_01           6                  -> 207                     0
    Hard-Science-Old__Lava              3                  ->   3                     2

**Filter 12 = `directionalwarp` = type `0x18`/`0x19`.** The identification rests on four
converging lines - arity 2, the slot-3 greyscale constraint at 0 of 42,220, containment 17/17,
and colour pass-through on slot 2 - of which the second is a structural impossibility rather
than a statistical preference, and is the one that carries the weight.

**The weakness, stated plainly:** only 2 of 17 files match exactly. `directionalwarp` is heavily
used inside library graphs, so inlining inflates the binary count by up to 40x, and no
count-level test could ever have resolved this. That is why the earlier count matching returned
a correlation of 0.28 and why it was right not to accept it.

**Filter 8 = `emboss` is a lead, not a finding.** Its containment evidence is a single file. It
is what remains after `directionalwarp` is assigned, among filters with the two-input greyscale
signature, and it matches on channel behaviour - but one file is one file.

### Coverage

    total records                        651,743
    14 named filters                     594,342    91.2%
    with directionalwarp (filter 12)     636,562    97.7%

    still unnamed:  fid 11  10,978  1.68%      fid 22    909  0.14%
                    fid 19   1,782  0.27%      fid  8    405  0.06%
                    fid 13     931  0.14%      fid  5    119  0.02%

**Fifteen of twenty-one filter ids named, covering 97.7% of all records.** Filter 11 is now the
largest unknown at 1.68%, and it is the one with no surviving candidate: its arity is one, its
output is 2.9% colour, and `grayscaleconversion` - the only unmapped one-input filter whose
channel behaviour is distinctive - is ruled out by those 318 colour records.

## `sharpen` = filter 13, and three identifications that do not survive scrutiny

With `directionalwarp` assigned, the remaining unnamed ids are small. Containment and exact-count
matching over the paired corpus, for every one-input candidate:

    source filter          files   fid11        fid19       fid13       fid22       fid8
    sharpen                    8   7/8,1        4/8,0       8/8,5       1/8,0       1/8,0
    curve                     10   2/10,0       2/10,0      0/10,0      4/10,4      1/10,1
    text                       4   1/4,0        0/4,0       0/4,0       0/4,0       0/4,0
    dirmotionblur              4   4/4,1        2/4,0       3/4,2       0/4,0       0/4,0
    grayscaleconversion       25  18/25,0       7/25,0      8/25,3      1/25,0      5/25,2
    passthrough               26   7/26,0       5/26,1      1/26,1      0/26,0      0/26,0
    valueprocessor            10   0/10,0       0/10,0      0/10,0      0/10,0      0/10,0

    (cells: contained/files, exact)

**`sharpen` = filter 13 = type `0x1A`/`0x1B`.** Containment holds in 8 of 8 files, five match
exactly, and the five span **four distinct repositories** - the diversity check that the
file-clustering error earlier in this session made mandatory. The three non-exact files all have
*more* filter-13 records than `sharpen` nodes, which is inlining; none has fewer, so nothing
needs a dead-code explanation.

The competing candidate is eliminated rather than merely outscored: `dirmotionblur` fails
containment in one of its four files, and containment must hold everywhere. `curve` fails 10/10,
`passthrough` 25/26, and `grayscaleconversion` is independently ruled out because filter 13 is
4.4% colour while `grayscaleconversion` outputs greyscale by definition.

The pass-through check corroborates: filter 13's input is 4.4% colour and filter 13 itself is
4.4% colour - **equal**, which is the signature of a filter that preserves channel count.
Compare `normal` at 0.0% input against 100% own, or `gradient` at 0.0% against 15.8%.

### Three that fail

**`text` = filter 17 is rejected.** Three of four files match exactly, which looks strong until
the repositories are counted: **all three come from `substance-for-unity-extensions`**. That is
one observation wearing three hats, and it is precisely the confound that invalidated the
`blendingmode` program result earlier today. The fourth file, `SubstanceDesigner__hblend`, has
three `text` nodes and zero filter-17 records - an outright counter-example from the one
independent repository available.

**`curve` = filter 22 is not supported.** Four exact matches, but from only two repositories, and
containment fails in six of ten files. `LGMLtools__LGML_curve_shape4` has five `curve` nodes and
zero filter-22 records.

**`dirmotionblur` = filter 11 is not supported.** One exact match from one repository, against
ratios of 1 source node to 86 binary records in another file.

## The provenance constraint has a measurable cost, and filter 11 is where it lands

Filter 11 is the largest remaining unknown - 10,978 records, 1.68% of the format, present in 262
of 382 specimens. What is known about it:

    inputs                    1 (slot 2)
    colour output             2.9%
    input colour              2.9%  - equal, so it preserves channel count
    resolution change         0.0% of 10,978 edges
    slot 1                    a parameter bitfield, 6 distinct values corpus-wide

Every unmapped source filter has now been tested against it and none fits. `grayscaleconversion`
is ruled out by channel behaviour, `passthrough` by containment at 7/26, `curve` at 2/10,
`valueprocessor` at 0/10, `dirmotionblur` on repository diversity.

The structural profile - one input, channel-preserving, resolution-preserving, widespread -
matches `motionblur`, and the provisional table in `edgeaudit.py` guessed exactly that. **It
cannot be confirmed.** Checking every source file in the corpus that contains a `motionblur`
node:

    Hard-Science-Old__concrete_085.sbs                  Allegorithmic-authored graph present
    Hard-Science-Old__granite_001.sbs                   Allegorithmic-authored graph present
    Substance-Designer-Toolsets__wood_cedar_white.sbs   Allegorithmic-authored graph present

**Every file in the corpus that uses `motionblur` is excluded by the provenance rule.** So is
every file using `svg`. There is no permitted specimen in which the identification could be
tested, and none can be obtained without violating the constraint this project works under.

This is worth stating plainly because it is the first place in this document where the exclusion
policy has a demonstrable, quantified cost rather than a theoretical one: **1.68% of all records
are unidentifiable, not because the evidence is hard to find, but because the evidence is off
limits.** The right response is to record the boundary, not to erode it. Filter 11 stays
unnamed, with its structural profile documented so that anyone working from a differently-sourced
corpus can close it in an afternoon.

### An independent validation, free from the same test

The resolution-change measurement produced a control worth keeping:

    filter              edges     resolution differs from input
    transformation    170,102              56.0%
    warp               39,752               4.2%
    directionalwarp    42,220               0.5%
    blend             454,242               0.1%
    everything else                         0.0%

`transformation` is the one atomic filter whose entire purpose includes resampling, and it is the
only one that changes resolution at any meaningful rate. That simultaneously confirms the
`transformation` identification, the tag's resolution nibbles, and the edge-index resolution
rule - three separate pieces of the format agreeing in one measurement.

**Sixteen of twenty-one filter ids named, covering 97.9% of all records.**

## The edge map, derived rather than asserted

Every edge map in this document until now was hand-written, accumulated one filter at a time.
Deriving it from the corpus exposes how it was built and where it was wrong.

The naive derivation - "a slot is an edge if its value is a strictly backward record index" -
**fails in exactly the way slot 1 already taught**: a parameter bitfield holding a small integer
is backward-looking in almost every record of a large file, so the test admits it. Run that way,
`blend` slot 1 scores 92.6% backward and `directionalwarp` slot 1 scores 100%, and both are
parameter words.

The discriminator that works is **value diversity**, the same one that broke the shared-reference
reading: a real edge takes nearly as many distinct values as there are records, a bitfield takes
a handful.

    fid  slot   records    backward   distinct/record   global values   verdict
      1     1   227,121      92.6%         0.05              126        parameter bitfield
      1     2   227,121     100.0%         0.98           21,667        EDGE
      1     3   227,121     100.0%         0.95           20,959        EDGE
      2     1   170,102      56.0%         0.04               52        parameter bitfield
      2     2   170,102     100.0%         0.60           15,278        EDGE
     20     1    38,335      97.3%         0.04               22        parameter bitfield (arity)
      7     1    19,876     100.0%         1.00            5,571        EDGE

Requiring both a backwardness rate above 95% and a distinct-values-per-record ratio above 0.30
separates the two populations cleanly, and reproduces the hand-built map for every filter it was
built for:

    EDGE = {0:[1], 1:[2,3], 2:[2], 3:[1,2,3], 7:[1,2], 8:[1,2,3], 10:[1], 11:[2],
            12:[2], 13:[1], 14:[1], 15:[2], 18:[2], 19:[1], 21:[2], 22:[1]}

Two slots the derivation misses are known from other evidence and should be unioned in:
`directionalwarp` slot 3 and `distance` slot 3, both of which have high fan-in - many records
sharing one control map - so their distinct-value ratio falls below the threshold. **That is the
threshold's failure mode and it is worth stating: a heavily-shared input looks like a constant.**

## Output attribution: three more approaches eliminated

Attributing graph outputs to records remains the largest structural gap. With a derived edge map
the natural approach can finally be run properly.

**Sinks.** A record that no edge points at is a sink, and an output must be one - nothing
downstream consumes it. Over 375 specimens:

    sink count >= n_out                       359   95.7%
    sink count == n_out                        27    7.2%
    last n_out records are all sinks           50   13.3%

**`outputs` is a subset of `sinks` in 95.7% of specimens.** That is a genuine constraint and a
reader can use it - it prunes the candidate set - but it does not identify anything, because
there are typically several times more sinks than outputs.

**Correction, from a later section.** With a fuller edge map the figure falls to 93.3%, and the
6.7% where it fails are not noise: they are specimens with *fewer sinks than outputs*, which no
amount of edge-map repair can fix. The subset claim is false, and the reason is given under
"An output need not be a sink" below. Do not rely on it.

**Position.** If outputs were emitted last, attribution would be free. They are not. Sinks are
spread almost uniformly through the directory:

    decile      0%   10%  20%  30%  40%  50%  60%  70%  80%  90%  100%
    share     9.5%  8.2% 7.6% 8.4% 8.2% 7.5% 8.7% 10.6% 10.0% 9.3% 12.0%

A mild bias toward the end - 12.0% against a 9.1% baseline - and nothing more.

**Resolution, against the manifest.** The manifest states each output's `width` and `height`, and
the record tag encodes log2 of both, so a correct assignment should agree. Among the 27
specimens where the sink count happens to equal `n_out`, the resolution multiset matches in 13 -
**48.1%, which is chance.**

The reason is in the manifest itself and it kills the approach outright:

    manifest outputs with dynamicsize="yes"   2,058
    without                                     151

**93% of all outputs are dynamically sized**, so the `width` and `height` the manifest reports
are defaults for the graph's default `$outputsize`, not properties of the output. They cannot
serve as ground truth for anything resolution-based. This is worth recording prominently: any
future attempt to match records to outputs by dimension is testing against a value the format
does not commit to.

### Where that leaves it

Four independent approaches have now failed: uid references in the body (0 of 183,160), raw byte
matching (0), sink counting (7.2% exact), and manifest resolution (chance). The negative is
consistent enough to state as a structural claim rather than a run of bad luck: **the `.sbsasm`
body contains no explicit output→record association.** The correspondence is positional or
implicit, carried by something the reader is expected to reconstruct - most likely by evaluating
the graph - rather than stored.

For a practical reader that means outputs must be resolved by evaluation order, and the useful
salvage from this round is the 95.7% subset constraint plus the observation that no dimension
test can help.

## Slot 1 decoded further: blend bit 5 is the output-size flag

`blendingmode` occupies bits 0-3 of `blend` slot 1. Bits 4, 5 and 8 - set in 45%, 23% and 77%
of records - have stood unread. Bit 5 can now be named.

### The structure of the parameter words

Censusing slot 1 across the filters that carry a parameter word rather than a pointer:

    transformation   52 distinct values   0x1F always set; bits 5,6,7 vary; high bits 24-26
    levels           93                   even bits common (8-65%), odd bits rare (~1%)
    directionalwarp  10                   dominated by 0x0A (bits 1 and 3), 89.7%
    distance          6                   {5,6,7,9,10,21}
    normal           11                   {0,1,2,5,6,10,16,17,18,26,42}

`levels` shows the clearest pattern: **even bits are common and odd bits are rare, and each odd
bit that is set adds about 2.5 inline programs to the record.** That is the shape of paired
flags - one bit per parameter saying it is set, a second saying it is computed.

Fitting `inline programs == C + popcount(slot1 & MASK)` per filter:

    filter            records      C     mask     exact    baseline (predict the mode)
    blend             138,907      1    0x020     95.9%       76.0%
    levels             38,778      1    0x28A     99.1%       97.7%
    distance            1,055      2    0x008     91.0%       79.9%
    normal                623      2    0x002     73.7%       59.9%
    directionalwarp    28,647      2    0x014     77.2%       74.2%
    transformation     94,142      1    0x080     75.6%       73.7%

`blend` gives the largest lift over baseline - twenty points - on a single bit.

### What bit 5 is not

The obvious reading is "the parameter is a function rather than a constant". **It is wrong.**
In the seven count-exact blend files, bit 5 is set in 19 of 23 records while only 11 source nodes
carry a `<dynamicValue>`. Corpus-wide the rates also disagree: bit 5 is set in 23% of blend
records, and only 6.5% of source blend nodes have any dynamic parameter.

### What bit 5 is

The second program a blend record carries is a **size computation** - the earlier finding that
short blend programs are `$sizelog2` arithmetic. Testing bit 5 against whether the record's
programs read `$size` or `$sizelog2` at all, over 134,703 blend records:

    bit 5 = 0    102,869 records        0 read a size variable      0.0%
    bit 5 = 1     31,834 records   21,838 read a size variable     68.6%

**Zero of 102,869.** The implication is one-directional and absolute: if bit 5 is clear, the
record does not compute its own size. The converse is only 68.6%, which common subexpression
elimination explains - a size program shared with an earlier record is not inline in this one,
so the record has the flag without carrying the code.

**`blend` slot 1 bit 5 = the record computes its own output size** rather than inheriting it
from its input.

**It is not the source `outputsize` parameter.** That attribution was written into an earlier
draft of this section and is wrong. `outputsize` appears on only **6.4%** of the 1,151 paired
blend nodes while bit 5 is set in 23% of records, and in the count-exact files seven nodes carry
`outputsize` against nineteen records with bit 5. `LGMLtools__multi_blender` has seven blend
nodes, none declaring `outputsize`, and all seven records have bit 5 set.

What the bit records is the *compiled* fact - this record evaluates a size expression - which the
compiler emits whenever resolution has to be reconciled along a chain, not only where the author
declared a parameter. The binary evidence for the bit is unaffected; only the source-level name
for it was wrong.

### The same bit in other filters, and why the evidence does not carry

Every filter has a bit whose clear state forbids reading a size variable, but for most of them
the claim is vacuous, and the base rate is what exposes it:

    filter            bit   set rate   records with bit clear that read size
    blend               5     23.1%           0 of 102,869      <- non-vacuous
    transformation      1     99.0%          11 of  ~930        <- clear state is 1% of records
    fid 11              0     94.4%         182                 <- same problem
    distance            2     90.0%          71 of ~167         <- 42% of the clear cases

Only `blend` has a bit that is clear often enough for the zero to mean anything. **A perfect
one-directional implication over a class that contains almost nothing is not evidence**, and
this is the same too-permissive-predicate failure that manufactured the shared reference - caught
here only because the set rates were tabulated alongside the result.

One clean byproduct: **`levels` records never read a size variable at all** - 0.0% of 33,822.
A levels node cannot resize its input, and the format reflects that exactly.

### Position after this section

    blend slot 1
      bits 0-3   blendingmode            confirmed, two independent tests
      bit 4      set in 45%              unknown
      bit 5      computes own output size  confirmed, 0 of 102,869 counterexamples
      bits 6-7   structurally unused
      bit 8      set in 77%              unknown
      bits 9-11  set in 0.1-0.3%         unknown

## Blend bits 4 and 8: constrained, not identified

Both remaining bits turn out to be bound up with the same size machinery as bit 5, and the
contingency table over 121,540 blend records is sharp:

    bit 4     clear 69,262 (57.0%)     set 52,278 (43.0%)
      header is 5 slots                49.6%  ->   0.0%
      two or more inline programs      36.8%  ->   1.1%
      reads any system variable        29.0%  ->   0.0%

    bit 8     clear 25,827 (21.2%)     set 95,713 (78.8%)
      header is 5 slots                 1.4%  ->  35.5%
      reads any system variable         0.1%  ->  21.0%
      two or more inline programs       5.2%  ->  25.9%

**Bit 4 set is an absolute prohibition**: not one of 52,278 such records has a five-slot header,
and not one reads a system variable. Bit 8 clear is nearly as strong in the same direction.

Neither is an identification. What they establish is that bits 4, 5 and 8 jointly encode
something about how the record obtains its resolution, and that the encoding is a small
enumeration rather than three independent flags - four combinations cover 95.9% of all records:

    b4 b5 b8      share
     0  0  1      34.3%
     1  0  0      21.9%
     1  0  1      20.4%
     0  1  1      19.3%
     ----
     1  1  1       2.7%     the remaining 4.1% is spread over the other four combinations
     0  1  0       1.0%
     0  0  0       0.4%
     1  1  0       0.1%

Bits 4 and 5 are very nearly mutually exclusive - they co-occur in 2.8% of records - and bit 5
implies bit 8 in 95% of the records where it is set. A four-state enumeration spread across three
bits with those dependencies is the signature of a mode field, and the obvious candidate is
`outputsize`'s `relativeTo`, which takes three values in the sources:

    relativeTo = 0 (absolute)            841
    relativeTo = 1 (relative to input)  1,655
    relativeTo = 2 (relative to parent)   238

**The candidate cannot be tested.** `outputsize` is declared on 6.4% of blend nodes and these
bits vary across 96% of records, so the source parameter is absent precisely where the
discrimination would have to happen. The same inheritance mechanism that makes bit 5 fire without
a declared parameter makes `relativeTo` unavailable as ground truth for the other two.

Recorded as: **bits 4 and 8 are resolution-mode bits, jointly enumerating four states with bit 5,
and unidentified.** The measured implications above are usable by a reader even without the
names - a record with bit 4 set has a six-slot header and one program, which is enough to parse
it.

## Multi-graph files: how records divide between graphs

A `.sbsar` can hold several graphs - 30 of the 376 specimens do, up to twenty in one file - and
nothing in this document has said how a reader tells which records belong to which graph. The
header aggregates: `n_in` and `n_out` are totals across all graphs.

### Connected components are contiguous runs

Building the record DAG from the derived edge map and taking connected components:

    single-graph files (346)   2,831 components   2,379 contiguous   84.0%
    multi-graph files  (30)      665 components     600 contiguous   90.2%

**A connected sub-DAG occupies a contiguous range of directory indices.** The compiler emits one
component's records together, then moves to the next. That is a genuinely useful property: a
reader can segment the directory into independent sub-graphs by walking it once, without
resolving every edge.

The 10-16% that are not contiguous are consistent with the edge map still being incomplete -
a missed edge splits one component into two interleaved fragments - so the true rate is a lower
bound.

### Components never merge two graphs

Across all 30 multi-graph specimens, the component count **always exceeds** the graph count:

    components - graphs = +1   12 files      the modal case
                         +3     3
                         +4     3
                         +5     3
                       +6..+7   3
                     +25..+219  6      (ie_curve, sRGB_colorchart, Camouflage and similar)

Never zero, never negative. Two-graph files split cleanly - `nescolors` at 1,039 records gives
components of 595 and 443 plus a singleton, and `sRGB_colorchart` with four graphs gives four
components of 1,977 / 1,976 / 1,976 / 84.

That components are always more numerous than graphs is consistent with **common subexpression
elimination not crossing graph boundaries**, which would be a useful guarantee - but it is not
proof, since fragmentation from missing edges could mask a merge. Recorded as consistent, not
established.

The excess components are not one uniform thing. In the twelve `+1` files the extra components
are twenty singletons whose filters are `bitmap` 8, `pixelprocessor` 5, `uniform` 3, `fxmaps` 2,
`blur` 1 - no single kind - and twelve of them sit at directory index 0. A "one global record per
file" reading does not survive that spread.

### Matching components to graphs by output count does not work

If each graph's outputs were the sinks of one component, components could be matched to graphs by
counting sinks, and that would give the output attribution this document has failed four times to
find. Run over the 25 multi-graph files with 2-6 graphs, a matching subset exists in 52%.

**That 52% is meaningless and the reason is worth recording.** In 12 of the 15 files examined in
detail, *every* graph has exactly one output and *every* component has exactly one sink, so any
subset of the right size matches. The test has no power on those files at all.

Restricting to the files where the graphs actually differ in output count:

    SubstanceDesigner__triDraw   graphs [3, 5]   component sinks [2,2,2,1,1,1,1,1]   NO MATCH
    sat-scons__pbr_render        graphs [1, 2]   component sinks [2,1,1,1,1]         match
    RockSubstance001             graphs [1, 4]   component sinks [15,1,1,1,1,1,1]    NO MATCH

**One of three.** There is no evidence here, and the headline 52% would have been a fifth false
attribution result had the vacuous cases not been separated out.

This is the same too-permissive-predicate failure that produced the shared reference and the
`pixelprocessor` bitfield, arriving for the third time in a different costume. The general form is
now clear enough to state as a standing rule for this project: **before quoting a match rate,
count how many of the cases could have failed.** A test that 80% of the corpus passes
automatically is measuring the corpus, not the hypothesis.

### What a reader can use

    - components of the record DAG are contiguous directory ranges (>=84%)
    - components never number fewer than the graphs in the file (30/30)
    - which component serves which graph is unknown

## Graph inputs are records; graph outputs are not

The 13 instance-free paired files answer a question this document never asked: which *kinds* of
source node produce a record at all. A `.sbs` graph contains three kinds - filter nodes,
`compInputBridge` nodes (the graph's image inputs) and `compOutputBridge` nodes (its outputs).

    file                            filters  inputBridge  outputBridge  records
    st_wood_fine_20                     14        0            7           14
    Metal_Vent_006                       6        0            6            6
    ie_processing                        2        2            2            4
    SubstanceTools__radial_blur_color    1        1            1            2
    SubstanceDesigner__color             8        8            3           17

**`records == filters + inputBridge` in 12 of 13 files**, and output bridges contribute nothing -
seven of them in `st_wood_fine_20` add zero records. The single exception,
`SubstanceDesigner__color`, has one extra `uniform` record beyond the formula.

### Input bridges are `bitmap` records

In every one of these files the bitmap record count equals the input bridge count exactly - 8=8,
2=2, 1=1. Testing that corpus-wide needs the manifest's input `type` code, which is not
documented anywhere in this project. Sweeping every code against the bitmap record count:

    type   total inputs   files with >0   exact   contained
      0        3,461          306           4%       11%
      1          293           65          11%       32%
      2          143           65           8%       42%
      3          342          105           4%       21%
      4        2,328          358           4%       19%
      5          523           61          87%      100%
      8          474          371          10%       39%

**Manifest input `type="5"` is an image input**, and it matches the bitmap record count exactly in
87% of the 61 specimens that declare one, with containment at **100%**. The 13% excess is
genuinely embedded bitmaps, which produce the same record type.

That sharpens the earlier identification: filter 16 (`0x20`/`0x21`) is not specifically "bitmap",
it is the **general image-source record**, covering embedded images and graph image inputs alike.
It is also the first use found for the manifest's input type codes, of which `5` (image) and `8`
(integer2, from `$outputsize`) are now known.

### Why output attribution failed

Four independent approaches have failed to associate outputs with records: uid references in the
body (0 of 183,160), raw byte matching (0), sink counting (7.2% exact), and manifest resolution
(chance). Each was recorded as a negative and the conclusion drawn was that the association is
"positional or implicit".

**The real reason is simpler and is now measured: the compiler emits no record for an output.**
An output bridge produces nothing. An output is a reference to a record that exists for some
other reason - the last filter in its chain - and that reference is not stored in the body.

This retroactively justifies the exhaustiveness of the earlier searches rather than undermining
them. They found nothing because nothing is there, not because they looked in the wrong place.
It also settles what a reader should do: **reconstruct outputs by evaluation, not by lookup**,
and expect no field to confirm the answer.

The asymmetry is worth stating plainly, since it is the practical shape of the format:

    graph image inputs   ->  one `bitmap` record each, recoverable, 100% containment
    graph outputs        ->  no record, not recoverable from the body alone

## Three input-less filters, and `text` identified after all

Measuring reachability in the record DAG from records that legitimately have no image input -
`bitmap`, `uniform`, `gradient`, `fxmaps`:

    records                            651,736
    reachable from a source            638,967   98.0%
    orphaned (no input, not a source)    3,069    0.5%

The edge map is in better shape than assumed, which rules out incompleteness as the explanation
for the `alteroutputs` failure above. But the orphan breakdown is the useful part: **three filter
ids are 100% input-less**, which makes them generators.

    fid  type        records  specimens  orphaned  colour  versions
      5  0x0A/0x0B       119      5        100%     0.8%   0x90000, 0x50000, 0x20000
      9  0x12/0x13         5      4        100%     0.0%   0x20000 only
     17  0x22/0x23        52     11        100%     0.0%   0x90000, 0x50000

`text` and `svg` are the only generators in the source filter vocabulary, so the candidates were
already narrow.

### Filter 17 = `text`

This document rejected `text` = filter 17 two sections ago, on the correct grounds that its three
exact count matches all came from one repository - the clustering confound that invalidated the
`blendingmode` program result. **That rejection is now reversed by independent evidence.**

Manifest input `type="6"` is a **string**, and every string-typed input in the corpus is
text-related:

    text (x3)   MPH_text   symbol_1..4_custom_text   road_lines_symbol_1..4_custom_text

Every specimen declaring one has filter-17 records:

    RoadSubstance002                     4 string inputs   ->  20 filter-17 records
    RoadLinesSubstance002                4                 ->  10
    RoadSignsMarkings__Speed_Limit       MPH_text          ->   6
    substance-for-unity-extensions__UnitTests  text        ->   3
    RuntimeExample / TimelineExample     text              ->   1 / 1

And the specimens that carry filter 17 without a string parameter are **road signs** -
`Stop_Sign`, `Yield`, `One_Way`, `Do_Not_Enter` - objects whose entire content is lettering, with
the text baked in as a constant rather than exposed as a parameter.

The evidence now spans three unrelated sources (`RoadSignsMarkings`, `RoadSubstance`,
`substance-for-unity-extensions`), and adds two structural lines the count test never had:
filter 17 is **100% input-less**, which `text` is, and **100% greyscale**, which a text mask is.

**The earlier rejection was right on the evidence available and wrong as a conclusion.** That is
the correct outcome of a conservative rule - it defers rather than denies - and the lesson is not
to loosen the rule but to notice that a rejected hypothesis stays live until something rules it
out, which repository clustering never did.

### Filter 5 is the long-standing tag `0x0A`, now characterised but not named

`0x0A` has been an open item since early in this document: five specimens, no sources. It is
filter id 5, and it is now profiled rather than merely counted - an input-less generator,
greyscale, concentrated in road materials:

    RoadSubstance002 70,  RoadLinesSubstance002 35,  TilesSubstance013 7,
    SnowSubstance002 6,   deep-sea-studios__Shield_Front 1

Road markings are vector shapes, which points at `svg` - the only generator left once `text` is
assigned. **It cannot be confirmed.** `svg` appears in exactly one source file in the corpus and
that file carries an Allegorithmic-authored graph, so it is excluded. This is the third place the
provenance boundary has bitten, after filter 11 (`motionblur`) and `passthrough`.

Filter 9 is settled as far as it can be: five records, every one in version `0x20000`, the oldest
in the corpus, which confirms the earlier reading of `0x12` as a legacy tag. All four specimens
carrying it are Allegorithmic-authored.

### Manifest input type codes

Three are now known, all derived here rather than documented anywhere:

    type 5   image      -> one `bitmap` record each, 100% containment
    type 6   string     -> accompanies `text` records
    type 8   integer2   -> `$outputsize`

**Seventeen of twenty-one filter ids named.**

## References per target: separating data edges from shared control maps

The edge-map derivation earlier used value diversity and noted its failure mode - "a heavily
shared input looks like a constant". That failure mode turns out to be a **measurement**, not just
a caveat. Counting how many records reference each target through a given slot:

    mean refs/target ~= 1.0    every target used once     -> a tree/data edge
    mean refs/target >> 1      one target used many times -> a shared control map or resource

Applied to the slots of the remaining unnamed filters:

    fid  slot   edges   target colour   refs/target   what it points at
     19    1    1,782       0.0%           1.0        blend 94%, levels 2%
     19    2    1,782       1.8%           8.3        pixelprocessor 97%
     11    1   10,946      10.4%          16.8        transformation 36%, fxmaps 20%
     11    2   10,973       2.9%           1.0        fid11 71%, levels 7%
     22    1      907       5.2%           1.2        blend 36%, pixelprocessor 18%
     22    2      903       8.2%           2.9        transformation 31%, blend 16%
      8    1      397      16.4%           1.8        transformation 35%, blend 13%
      8    2      405      47.7%           1.0        blend 32%, levels 25%
      8    3      405       0.0%           1.0        blur 28%, shuffle 22%

The metric cleanly separates the two roles inside a single filter. **Filter 19 takes a unique
greyscale image on slot 1 and a shared `pixelprocessor` output on slot 2** - 97% of slot-2 targets
are pixel processors, each serving 8.3 records on average. **Filter 11 is the mirror**: its data
edge is slot 2, which chains to other filter-11 records 71% of the time, while slot 1 is a shared
reference used 16.8 times over.

This also corrects the derived edge map. Slot 2 of filter 19 and slot 1 of filter 11 were
classified as non-edges by the diversity test; they are references, but of a different kind than
the data edges - which is exactly what the test should have said and could not express.

### What filter 19 is, structurally

    one unique greyscale input, 94% of the time straight from a `blend`
    one shared `pixelprocessor` map, 97%, averaging 8.3 users
    output greyscale (1.8% colour), never changes resolution
    consumed by `blend` 91% of the time - it sits between two blends
    sink rate 0.4% - almost never terminal

A filter that applies a shared, pixel-processor-generated lookup to a greyscale image, between
blend layers, describes `curve` - a transfer function baked into a LUT would be shared exactly
this way. **Containment refutes it**: in 8 of the 10 paired files containing `curve` nodes there
are *fewer* filter-19 records than `curve` nodes, and inlining can only add. The same test rules
it out for filter 22 at 6 of 10.

So filter 19 is characterised in detail and still unnamed, and the candidate its profile suggests
is the candidate the counting rules out - the second time in this document that has happened,
after filter 11 and `grayscaleconversion`.

`grayscaleconversion` is separately ruled out for filter 19 on a stronger ground than counting:
its input would have to be colour, and **filter 19's slot-1 targets are 0.0% colour over 1,782
edges**.

### Filter 8 keeps its `emboss` lead

Filter 8's slot 3 is greyscale in 0 of 405 edges while its own output is 47.7% colour - the
image-plus-greyscale-control-map signature that identified `directionalwarp`. That is consistent
with `emboss`, which is the remaining two-input filter of that shape, and adds a structural line
to what was previously a single file's containment evidence. Still a lead, now a better-founded
one.

## Embedded bitmaps: located, decoded, and extractable

A `.sbsar` can carry raw image data - 73% of files have no resource segment, but the ones that do
carry most of the corpus's bytes. How a record addresses that data has never been worked out here.
It is simple, and `extract_bitmaps.py` now implements it.

### The bitmap record has two forms

    8 bytes    [u16 tag][u16 class][u32 resource offset]        stored pixel data
    >=20 bytes [u16 tag][u16 class][u32 input uid][...]         a graph image input

The two are told apart by record length, which the directory now gives exactly.

### The short form addresses raw pixels

Word 1 is a **byte offset into the resource segment** at the head of the file, and the data there
is raw and uncompressed. Taking the gap between consecutive resource offsets and dividing by
`width x height` from the tag's resolution nibbles gives an exact bytes-per-pixel, and it is
**fully determined by the class word**:

    class    bytes/px   samples   reading
    0x0108      1         90      greyscale 8-bit
    0x0518      2        104      greyscale 16-bit
    0x0208      3         95      RGB 8-bit
    0x0308      4         30      RGBA 8-bit
    0x0618      6         24      RGB 16-bit
    0x0718      8         25      RGBA 16-bit

**100% in every row, no exceptions over 368 samples.** The class decodes cleanly:

    (class >> 8) & 3   channel layout:  1 -> L,  2 -> RGB,  3 -> RGBA
    (class >> 8) & 4   16 bits per channel when set
    class & 0xFF       0x08 for 8-bit, 0x18 for 16-bit - redundant with the bit above

There are no mipmaps and no padding between images: consecutive resources abut exactly.

**Corrected below**: this table is incomplete and the offsets given here are read without the
+52 skew. See "Embedded images: JPEG, float formats, and a 52-byte error".

**Validation.** Running the model over the corpus:

    files with embedded bitmaps      92
    bitmaps located                 516
    pixel bytes addressed         1,810.8 MB
    reads running past end of file    0

and no resource in any file overruns the record region. The residual gap between the last
resource and the first record is the record directory, which accounts for the file completely:

    [4-byte prefix][resource segment][record directory][records][value table]

### The long form names its graph input

Word 1 of a long-form bitmap record is not an offset - it is the **uid of the graph image input**
the record stands for, exactly as published in the `.sbsar` manifest:

    DiamondPlateSubstance002   word 1 = 300155978   -> manifest input "color"      (type 5)
    FabricSubstance011                  485424148   -> "image"
    PaintedMetalSubstance002           3952608098   -> "inputmask"
    PlanksSubstance001                  864495014   -> "custom_color"
    PorcelainSubstance001               344808811   -> "input"

Over 448 long-form records in 60 specimens:

    word 1 is a manifest image-input uid     445   99.3%
    word 1 is some other manifest input uid    0    0.0%
    word 1 matches nothing                     3    0.7%

    specimens where the recovered uid set equals the full image-input set:  57 of 60

**Graph inputs are therefore identified exactly, by name**, not merely counted. That completes
the input side, which this document had established only statistically:

    count          100% containment, 87% exact
    channel type   53/53 as a multiset
    identity       99.3% by uid

### The asymmetry, stated exactly

The contrast with outputs is now as sharp as it can be made. An input has a record and that
record carries its manifest uid. An output has no record at all, and no uid reference to it
exists anywhere in the body - 0 of 183,160 references checked. **The format publishes what flows
in and leaves what flows out to be inferred.**

For a reader building a material importer, that is the practical shape of the problem: inputs can
be bound by name with near-certainty, outputs must be recovered by evaluating the graph.

## An output need not be a sink, and the signature attack fails

With graph inputs now identified exactly by uid, the `alteroutputs` attack can finally be run
properly. It was tried earlier and failed, but that attempt could only *count* inputs; it could
not say which record was which input. Now it can.

The construction: for each output, the manifest gives the set of image inputs that alter it.
For each sink, the record DAG gives the set of input records that reach it. If an output's
signature matched exactly one sink's signature, outputs would be identified.

Restricting to single-graph specimens with at least two outputs, at least two image inputs,
**distinct** output signatures - so the test has power - and every image input located as a record:

    specimen                                outputs  inputs  sinks  matched
    PaintedMetalSubstance002                    6       2      38      4
    Hard-Science-Old__EnvironmentToolkit        3       2      18      2
    Hard-Science-Old__stone_stylized_adaptive  10       2       9      3
    DLG-Tools__Embroidery_Legacy               12      67     118      0
    deep-sea-studios__GT2Unity5Metalness       14       9       8      6
    INB305__Bitmap2Material_3                  13       5      88      0
    MS_SBS2MAYA__PBR_SBS2VRay                   4       3       7      2

**Zero of seven fully matched.** That is the fifth failed approach to output attribution.

### The reason, which invalidates an earlier claim

Look at `stone_stylized_adaptive`: **ten outputs, nine sinks**. And `GT2Unity5Metalness`:
fourteen outputs, eight sinks. There are fewer sinks than outputs, so the outputs cannot each be
a distinct sink, and no improvement to the edge map can change that - a better edge map only
*reduces* the sink count.

Re-measuring across the corpus with the fuller map:

    sinks == n_out       21   5.6%
    sinks >  n_out      329  87.7%
    sinks <  n_out       25   6.7%
    median sinks/n_out  2.00   (2.80 under the older map)

**This retracts the claim made earlier that outputs are a subset of sinks in 95.7% of
specimens.** The correct figure is 93.3%, and more importantly the failures are structural rather
than statistical.

The mechanism is obvious once the arithmetic forces it: **an output can be a record that is also
consumed internally.** In a PBR material a height map is exported *and* fed to the normal-map
node. Its record has a consumer, so it is not a sink, yet it is an output. Every graph that
exports an intermediate result breaks the subset property, and PBR graphs do that routinely.

So the constraint offered earlier as "a genuine constraint a reader can use" is wrong, and I had
already used it to frame two later analyses. It should be replaced by the weaker and true
statement: **a record's being a sink is evidence of nothing about whether it is an output.**

### Where output attribution now stands

Five approaches, all failed, and the reasons are no longer independent:

    uid references in the body            0 of 183,160     no output uid appears anywhere
    raw byte matching                     0                same
    sink counting                         5.6% exact       outputs are not sinks
    manifest resolution                   chance           93% of outputs are dynamically sized
    alteroutputs signatures               0 of 7           outputs are not sinks

The first two say the association is not stored. The third and fifth fail for the same newly
understood reason. The fourth fails because the manifest does not commit to a size.

Combined with the finding that the compiler emits no record for an output bridge, the position is
now coherent rather than merely negative: **an output is a name attached to whatever record ends
up producing it, and the binary records neither the name nor the attachment.** A reader must
evaluate the graph, and no field will confirm the answer.

## The sources name the instruction set directly

Every opcode name in this document was inferred - from arity, from constant operands, from
adjacency, and finally from a disassembled program turning out to compute HSL saturation. The
`.sbs` sources have been carrying the answer the whole time, inside the function graphs that
`fxmaps` and dynamic parameters are built from:

    <paramNode><function v="ifelse"/><type v="2048"/> ...

**Seventy-five distinct function names** appear across the corpus, with an explicit type code.

### The type code, decoded

    4      bool          256    float1
    16     int1          512    float2
    32     int2         1024    float3
    64/128 int3/int4    2048    float4

A clean bitmask - bool at 4, integers from 16, floats from 256 - and it **independently
corroborates the opcode encoding derived here from bit patterns alone**: type in bits 9-8,
component count minus one in bits 7-6. Two encodings of the same type system, derived
separately, agreeing.

### The vocabulary against the catalogue

The source functions map onto the 41 catalogued operations exactly as the type-and-component
scheme predicts. `const_float1/2/3/4`, `const_int1/2`, `const_bool` are all operation `0x00`
in different forms; `vector2/3/4` and `ivector2` are `0x0D`; `swizzle1/2/3/4` and `iswizzle1/2`
are `0x10`; `tofloat`, `tofloat2/3/4`, `toint1/2` are `0x11`.

Several source functions have **no opcode at all**, which confirms the lowering already
documented: `pow2` (80 uses), `log` (6), `tan` (1), `passthrough` (47), and `instance` (5,764) -
the last being sub-graph inlining, the mechanism that inflates record counts throughout this
document.

One source function has no obvious home: **`mulscalar`, 1,889 uses**, distinct from `mul` in the
sources. A vector-times-scalar cannot be expressed by an opcode that carries a single type and
component count, so it is either lowered to a broadcast followed by `mul`, or folded into `mul`
at compile time. Unresolved, and flagged rather than assumed.

### A strict census, and what it says about "all named"

Checking for uncatalogued operation ids exposed a discrepancy that is worth recording as a
methodological result. Two ways of finding programs give very different answers:

    permissive - follow every record slot that looks like a program pointer
        30,038,253 instructions   (2.5x the catalogue)
        bool 0x1E: 4,374 instructions in 15 files
        float 0x2A: 3,761        float 0x35: 3,585

    strict - follow only the slot the record layout says is the program pointer
        11,738,547 instructions   (the catalogue says 11,845,287)
        bool 0x1E: 0
        float 0x2A: 42 in 1 file  float 0x35: 18 in 5 files

**`bool 0x1E` looked like a real unnamed operation - 4,374 instructions across 15 files - and it
is entirely an artifact of following false pointers.** The permissive walk inflates rare opcodes
by more than an order of magnitude while barely affecting common ones, because a false pointer
lands in arbitrary data and arbitrary data decodes to rare opcodes.

That the strict count lands within 1% of the catalogue's independently-produced figure is the
check that makes it trustworthy.

The `bool 0x1E` case is instructive for a second reason: the sources contain `noteq` (5 uses),
and `0x1E` sits exactly between `eq` at `0x1D` and `gt` at `0x1F`. **A plausible name, a
plausible slot in the encoding, and 4,374 apparent instructions - and it is not there.** Had the
strict census not been run, `0x1E = noteq` would have been recorded as a finding, and it would
have been the sixth false positive of this session.

### The residue that survives

Under the strict census, one operation id outside the named set survives at all:

    0643  int2    249 instructions,  9 files   consumed by cvt 86%, immediates {4, 1, 60, 3, ...}
    0543  float2   24 instructions             every operand token is a forward reference
    0503  float1   13 instructions             38% forward references

**286 instructions out of 11,738,547 - 0.0024%.** The `0543` form's tokens are 100% forward
references, so they are immediates; the `0643` form's are only 10% forward, so they may be value
numbers. The two readings are incompatible, the sample cannot distinguish them, and at this
frequency the possibility that some of it is residue from a wrong program-pointer slot cannot be
excluded either.

Recorded as: **operation `0x03` exists below the characterisation threshold.** The catalogue's
claim of 41 operations covering everything above the noise floor stands; the noise floor is
0.002%, and that is where this sits.

## A type checker for the bytecode, and two corrections it forced

Every value in a program is produced by exactly one instruction, and that instruction's opcode
carries the value's type and component count. So the type of every *operand* is computable, and
the operand signature of every operation can be read off the corpus rather than guessed.

Propagating types through 304,014 programs and 7,094,460 instructions:

    operation  result  arg      samples   operand types observed
    vec          f2     0,1     374,257   f1 100%
    vec          f4     0,1     323,374   f2 100%
    select       f4      0      161,618   b2 100%
    select       f4     1,2     161,618   f4 100%
    cvt          f2      0      127,512   i2 100%
    swizzle      f1      1      228,601   i2 53%   f2 45%   f1 1%
    seq          f1      0      130,292   i1 66%   f1 30%   b2 2%
    seq          f1      1      130,292   f1 100%
    mul          f1     0,1     244,961   f1 100%
    mul          f2      1       94,638   f1 91%   f2 9%

Most rows are 100% clean, which is itself the strongest end-to-end validation the opcode table
has had: **the names, the type bits and the component bits are mutually consistent across seven
million instructions**. `select`'s first operand is boolean without exception, `cvt.f2` consumes
an integer without exception, and `vec.f4` is built from two `f2` values rather than four
scalars - a detail no previous analysis had reached.

`seq` is the informative exception: its first operand is any type at all (`i1` 66%, `f1` 30%,
`b2` 2%) while its second matches the result. That is exactly what "chain statements, yield the
last" means, and it confirms the name.

### `mulscalar` resolved

The source vocabulary contains `mulscalar` (1,889 uses) as a function distinct from `mul`, and
no opcode corresponds to it. The signature table answers it: **`mul.f2` takes an `f1` second
operand 91% of the time.** Vector-times-scalar is not a separate operation - it is `mul` with
operands of different widths, and the opcode records only the *result* type. The distinction the
source makes is erased by the encoding and recoverable only by typing the operands, which is
what this pass does.

### Correction: `set` has its operands the other way round

The disassembler treated `set` as `set(slot, value)`. The type table showed `set.f4` receiving an
`f1` or `i2` in the position that should hold an `f4`, which cannot be right. Testing both
readings over 418,461 `set` instructions:

    token 0 is a valid backward value reference    418,461
    token 0 has the same type as the result        418,461   <- 100%
    token 1 has the same type as the result        147,156   <- 35%
    token 1 values                                 0, 4, 8, 10, 9, 2, 1, 12 ...  max 40

**`set` is `set(value, slot)`** - token 0 is the value and token 1 is the slot immediate. The
slot numbers are small and dense, as slot numbers should be; under the old reading the "slots"
were 4, 23, 51, 37, 62, which were value numbers being misread.

### What that correction did and did not change

The earlier finding that **parameter programs are closed expressions** was computed with the
wrong token - it collected value numbers where it should have collected slot numbers, and then
compared them against `get`'s slot numbers. A category error. Re-running it with the fix:

    filter            before    after
    blend               0.0%     0.0%
    transformation      0.0%     0.0%
    levels              0.0%     0.0%
    warp, blur, uniform 0.0%     0.0%
    pixelprocessor      5.4%     5.2%
    fxmaps             39.2%    39.3%

**The conclusion survives unchanged**, which is luck rather than vindication: comparing two
disjoint numbering spaces produced no false matches because a value number large enough to
collide with a slot number is rare. Had slots been numbered like values, the analysis would have
returned nonsense and nothing in the output would have shown it.

The lesson is narrow: **a result that depends on two identifier spaces should assert that they
are the same space.** The corrected slot distribution - 0, 4, 8, 10, 9, 2, 1, 12, max 40 - is the
assertion that was missing, and it takes one line to check.

## One segmenter, and what it says about its own gaps

Nearly every wrong result in this document came from the same place: an analysis re-deriving
the file model in a throwaway script, and getting some detail of it wrong. The permissive
program walk that manufactured `bool 0x1E`. Edges read as byte offsets when they are record
indices. `set` with its operands reversed. The program pointer taken from the wrong slot for
`warp`, `gradient` and `fxmaps`. Each was a local mistake in a local script, and each produced
a plausible-looking finding.

`sbsasm.py` is that model in one place, and `audit_corpus.py` measures how much of it holds.

### The design rule

**Strict by default; report the gaps as numbers.** Where a record's layout is known, read it;
where it is not, return `None` and count it. A segmenter that guesses looks perfect and is
useless, because its errors surface later as findings rather than as failures. So the module
carries three explicit registers of ignorance:

    UNNAMED         filter ids with a profile but no name - never rendered as a name
    PARTIAL_EDGES   filters whose input list does not fully resolve, and why
    coverage()      every byte classified; anything unaccounted is reported

### Deriving the tables rather than asserting them

Building the audit immediately exposed four wrong tables that had been carried by hand:

    warp        edges [1,2,3] -> [1,2]     slot 3 is the program pointer; 91.5% of warp
                                           edge slots were unresolvable under the old table
    distance    edges [2,3]   -> [2]       slot 3 is a shared control input, 29.0% unresolved
    shuffle     edges [1,2,3] -> [3]       only slot 3 resolves reliably; 120% -> 22.9%
    gradient    edges [1]     -> [1,2]

    program pointer slot   gradient 2 -> 4,  warp 4 -> 3,  fid 22 3 -> 4
                           fxmaps and uniform had no entry at all

The correction that matters most is methodological. The obvious way to find edge slots - "a slot
holding a valid backward record index" - **must exclude slot 1 wherever slot 1 is a parameter
word**, because a small packed integer passes that test trivially. That single conflation is
what produced the shared-reference error, the `pixelprocessor.colorswitch` false positive, and
the first version of these tables.

### Corpus audit

    files parsed                382    (0 failures)
    records                 651,743
      filter identified     637,545    97.8%
      with a located program 552,610   84.8%   (77.5% before the table fixes)
    edge slots              922,143    99.84% resolved   (97.33% before)
    bytes                 2,189,606,184
      unexplained                   0

Every byte of 2.19 GB is now classified. The one remaining structural gap is named rather than
absorbed:

### The layout-B prologue

Files with unexplained bytes were **exactly** the 30 layout-B specimens, all version `0x20000`,
and no layout-A file had a single unexplained byte. The cause is a layout difference this
document had not recorded:

    layout A    a record's programs and data are emitted inside its own extent
    layout B    a prologue precedes the first record and holds them

    [  0] @1004  fxmaps   prog@996        <- program lies *before* the record
    [  1] @1036  levels   prog@1028
    [  2] @1064  transformation

Records are contiguous after the prologue; the gap is entirely at the front - 948, 1320 and 944
bytes in three examples. Only **20.9% of the 11,440 prologue bytes** are reachable as programs
from a record slot; the rest is FX-Map tree data in these animation-heavy version-2 files.

It is 0.0005% of the corpus, and it is reported as `layout_b_prologue` rather than counted as
success. That distinction is the entire point of the module.

### What remains unresolved, stated by the tool itself

    filters unnamed             5 of 22 ids     fid 5, 8, 9, 11, 19, 22 (1.7% of records)
    records with no program     15.2%           filters whose program slot is unknown
    edge slots unresolved       0.16%           concentrated in shuffle (22.9%)
    fxmaps input list           unresolved      layout-dependent
    layout-B prologue           79% unread      FX-Map trees, version 2 only

## The parameter slot is a tagged union, and that closes most of the gap

The audit reported 15.2% of records with "no located program". Diagnosing it turned out not to
be a gap in the model at all.

For those records the slot holds values like `1065353216`, `1056964608`, `1090519040`. Read as
floats those are **1.0, 0.5 and 8.0**. The slot is not a broken pointer; it is a number.

    the program-pointer slot, over 309,878 records
      resolves to a valid program        276,509   89.2%
      decodes to a plausible float        30,461    9.8%
      BOTH readings valid                      0    0.000%

**Not one record in 309,878 satisfies both readings**, so the discrimination is exact rather
than heuristic - a float's bit pattern lands nowhere near a body offset, and a body offset
decodes to a denormal or an absurd magnitude. The union can be decoded without ambiguity.

The float values are unmistakably parameters:

    0.5   64.3%      2.0  3.6%      1.0  3.2%      4.0  3.2%      8.0  3.1%
    0.25   2.7%      0.1  1.9%     16.0  1.4%    0.125  1.3%     0.05  1.1%

`0.5` at 64% is a blend opacity left at its default. Per filter, the split matches what each one
does: `blur` bakes a constant 33% of the time, `uniform` 20%, `transformation` 15%, `blend` 6%,
`directionalwarp` 2%.

This is the mechanism recorded much earlier as "floats baked in record slots (88%)", but that
figure was about parameters in general. What is new is **where** they sit: in the same slot that
otherwise holds the program pointer, discriminated by whether the value resolves.

With the union encoded, the audit improves:

    main parameter resolved   608,848   93.4%    (84.8% when only programs counted)
      as a program            552,610   84.8%
      as a baked float         52,497    8.1%
      as zero / absent          3,741    0.6%

### Where the remaining 6.6% is

    shuffle           no program slot identified
    bitmap            has no parameter program - it loads an image
    pixelprocessor    the slot is 2 + arity, and arity is unresolved in 3% of records
    fid 5, 8, text    unnamed filters with no slot in the table

None of these is mysterious; each is a filter whose layout has not been pinned. The module lists
them rather than guessing, which is what let the float case be found: had the segmenter silently
treated `0x3F000000` as a pointer and failed to decode a program there, the record would have
been recorded as "program missing" and the constant would still be invisible.

## `shuffle` decoded, and layout probing as a general mechanism

`shuffle` was the worst-served filter in the audit: no program slot identified, 22.9% of its
edge slots unresolvable, 5,309 records. The count-exact file `SubstanceDesigner__color` has five
`shuffle` nodes and five `shuffle` records, so the correspondence is available.

    source                                              binary
    channelgreen=4                                      01198807 00000400 03 02 0110 ...
    channelgreen=4                                      01198807 03040100 04 05 0140 ...
    channelblue=4, channelalpha=5                       01198807 00000400 09 0A 04F8 ...
    channelgreen=4                                      01198807 00000400 0C 0D 053C ...
    channelblue=4                                       01198807 05040100 0E 0B 0558 ...

Slot 1 read as four bytes is the channel map - one byte per **output** channel, giving the
source channel, where 0-3 are input 1's RGBA and 4-7 are input 2's:

    0x05040100  ->  R<-0, G<-1, B<-4, A<-5    source: channelblue=4, channelalpha=5   exact
    0x03040100  ->  R<-0, G<-1, B<-4, A<-3    source: channelblue=4, alpha default 3  exact

Both two-parameter cases match exactly, including the defaults the source does not state.

### The range test, and why it first failed

Checking corpus-wide that the bytes stay inside 0-7 initially **failed**: bytes 0 and 1 reached
255 and 152. The cause was not the reading but the layout.

`shuffle` emits two record layouts:

    two inputs   [tag][channel map][edge][edge][program]     slot 1 is the channel map
    one input    [tag][edge][program]                        slot 1 is an edge

Reading slot 1 as a channel map in one-input records produces garbage, and that garbage was the
tail. Restricted to the two-input layout, over 2,704 records:

    byte 2 (B)   max 4    values {0, 2, 4}                 0.00% outside 0-7
    byte 3 (A)   max 7    values {0,1,3,4,5,7}             0.00% outside 0-7
    byte 1 (G)   max 24                                    0.63% outside
    byte 0 (R)   max 250                                   6.69% outside

Bytes 2 and 3 are exact. Bytes 0 and 1 fit in 99.4% and 93.3% of records with an unexplained
tail, so **the channel map is confirmed for blue and alpha and probable for red and green.**
Recording the asymmetry rather than averaging it away, because the tail is a real signal that
something else occupies those bytes in a minority of records.

### Layout probing

Rather than hard-code one layout per filter, `sbsasm.py` now accepts a list of candidates and
takes the first whose program slot validates:

    ALT_LAYOUTS = {3: [([2, 3], 4),      # two inputs
                       ([1], 2)]}        # one input

This is only safe because of the tagged-union result: a program pointer and a baked float are
disjoint readings, so a wrong layout guess cannot accidentally validate. **A probe is sound
exactly when the thing being probed for cannot be faked** - which is the same property that made
the instruction-boundary test decisive against the phantom opcodes.

Effect on the audit:

    shuffle    records with no parameter    100%  ->   4%
               unresolved edge slots       22.9%  ->  2.7%

    overall    main parameter resolved     93.4%  -> 94.2%
               edge slots resolved        99.84%  -> 99.95%

### What did not work: fxmaps inputs

The same session tried to locate `fxmaps` input edges by scanning every slot for valid backward
record indices. The hits spread evenly across thirty-plus slots at 9-13% each, with a plausible
filter mix among the targets - and it is **entirely the small-integer artifact**. An `fxmaps`
record runs to 331 slots, so any small value anywhere in it is a valid backward index by
construction.

`fxmaps` inputs are most likely referenced from inside the FX-Map tree rather than from record
slots, which is consistent with no slot showing an edge-like concentration. It stays in
`PARTIAL_EDGES`.

## FX-Map internals: what is solid, and why three approaches failed

`fxmaps` is the largest structure this document has not opened - 28,787 records, up to 331 slots
each, and `PARTIAL_EDGES` lists its input list as unresolved. Three attempts this session, and
the way each failed is more useful than the little they established.

### What is solid

Subtracting everything decodable - the tag, the parameter word, and every program reachable from
a record slot - leaves the rest:

    fxmaps records            11,349
    record bytes          15,985,824
    not covered by programs 10,309,990   64.5%

    uncovered regions per record:  4 in 29.1%,  5 in 42.6%

So a record **interleaves tree data with programs** in four or five alternating runs. An
annotated dump makes the shape plain:

    +0    03984408   tag / class
    +4    00000004
    +8    -> +20     tree root
    +12   -> +84     program
    +20   00020008   node header      +24  -> +28
    +28   00020008   node header      +32  -> +36
    +36   00020008   node header      +40  -> +44
    ...
    +60   00100048   node header      +64  -> +68   -> +72
    +72   PROGRAM    const 1; rand
    +84   PROGRAM    inputref uid=3886772249

**The tree is a linked structure of `[header][pointer]` nodes**, and leaf nodes point at
programs. That much is directly readable.

The sources bound the problem usefully: an FX-Map graph contains exactly **two** node types
across the whole corpus - `addnode` (296 uses) and `paramset` (228). Whatever the header encodes,
it distinguishes two kinds of node, not twenty.

### Three failures, one cause

**Scanning every slot for backward record indices**, to find the input list. Hits spread evenly
over thirty-plus slots at 9-13% each with a plausible mix of target filters. Entirely the
small-integer artifact: a 331-slot record makes any small value a valid backward index by
construction.

**Walking outward from the tree root through arbitrary pointer-looking words.** Produced a node-
header census in which the commonest high-u16 values included `0x0900` at 35.6% - the `const.f1`
opcode. The walk was inside the bytecode.

**Following the chain strictly via `word[1]` of each node.** Cleaner, but the header census still
returned `0x3F40` - the top half of `0.75f`. Not every node is eight bytes with its pointer at
+4, so the walk still slid into float payloads.

All three are the same error in different clothes: **treating a value as a pointer because it
could be one.** The corpus is large enough that any such rule finds thousands of confirmations.
The disciplines that work elsewhere in this document - a range test that must not be exceeded, a
tagged union whose readings are disjoint, an instruction-boundary check - all share the property
that a wrong guess *cannot* validate. No such property has been found for FX-Map nodes yet, and
until one is, every walk will produce statistics that look like findings.

### The corpus limit

The ground-truth route needs paired files where the source FX-Map node count can be matched to
binary structure. There are **two**, and they are the same material extracted twice:

    ie_particles           source (4 data, 6 addnode, 2 paramset) x2   binary (3 programs, 1449 slots) x2
    sd-ie-lib__ie_particles  identical

One distinct specimen cannot separate four candidate structures. This is the fourth place the
corpus rather than the analysis is the binding constraint, after `motionblur`, `svg` and
`passthrough` - but unlike those three it is not a provenance restriction. Any additional
instance-free `.sbs` containing an FX-Map would move it, and such files are not rare in the wild.

**Recorded as: FX-Map tree = linked `[header][pointer]` nodes carrying leaf programs, two node
types per the sources, internal encoding unresolved, blocked on specimens rather than on method.**

## What changes between format versions

The segmenter makes a per-version audit cheap, and the corpus spans seven versions. Until now
the only recorded version fact was that layout B is confined to version 2.

    ver  files   records   layout B   filter known   param as program   param as float
      2     90    16,876      30         96.4%           81.0%              9.7%
      3      5     7,200       0         98.0%           81.0%             10.3%
      4     41    32,289       0         96.8%           81.6%             10.6%
      5    192   397,194       0         97.8%           83.4%              9.6%
      6     27   101,635       0         98.3%           91.5%              4.7%
      8      6    10,055       0         99.8%           93.6%              0.4%
      9     21    86,494       0         98.0%           90.0%              4.1%

### Three filters do not exist before version 4

    filter            v2      v3      v4      v5      v6      v9
    pixelprocessor  0.00%   0.00%   0.43%   4.34%   9.10%  12.66%
    distance        0.00%   0.00%   0.39%   0.22%   0.30%   0.38%
    fid 19          0.00%   0.00%   0.04%   0.33%   0.26%   0.23%
    fid 22          0.00%   0.00%   0.00%   0.18%   0.09%   0.10%

**Zero records across 24,076 records of version-2 and version-3 headroom**, then all three
appear together at version 4. `fid 22` follows one version later, with 56,365 records of
headroom behind it. These are hard thresholds, not sampling: version 2 alone has 16,876 records
in 90 files.

`pixelprocessor` climbing from 0.43% at its introduction to 12.66% by version 9 is the clearest
adoption curve in the format.

**This constrains two of the unnamed filters.** `fid 19` appears in exactly the same version as
`pixelprocessor` and `distance`, and its slot 2 points at a `pixelprocessor` record 97% of the
time. Whatever it is, it was introduced alongside the pixel processor and depends on one. `fid
22` is one version later still. Any candidate that predates version 4 is excluded for both -
which rules out `passthrough`, `grayscaleconversion`, `curve` and `emboss` as identities for
`fid 19` on chronology alone, independently of the containment tests that already rejected them.

The "absent in v8" entries in the same table are **not** thresholds - version 8 has six files and
10,055 records, and a filter at 0.1% would be expected to be missing from a sample that size.
Distinguishing the two cases is only possible because the headroom is quoted alongside.

### The compiler bakes fewer constants over time

Parameters stored as a literal float in the record slot fall from ~10% to ~4% between versions 5
and 6. Controlling for filter mix, within each of the three commonest filters:

    ver    blend   transformation   levels
      2    15.1%       2.2%         20.3%
      4    13.7%       9.1%         21.6%
      5     6.7%      19.8%         12.0%
      6     4.4%       5.7%         10.8%
      9     4.0%       4.3%          9.3%

`blend` falls almost four-fold and `levels` more than halves; `transformation` does not follow the
trend at all. So the shift is real for two of three controls and should be stated as such rather
than as a general law: **later cookers express more parameters as programs and fewer as baked
literals, at least for `blend` and `levels`.**

For a reader the practical consequence is the reverse of what one might guess - **older files are
easier**, because more of their parameters are readable as plain numbers instead of requiring the
program to be evaluated.

## Output roles: the one place the format says what an output is for

This document has established that the binary carries no output association at all - no record,
no uid, five failed approaches. That is only half the picture for a reader building a material
importer, because **the manifest describes outputs thoroughly**, and this had never been examined.

Over 2,209 outputs in 383 specimens:

    outputs declaring a channel usage    1,932   87.5%   in 331 files

    baseColor          17.0%      metallic            8.9%      displacement   1.5%
    normal             16.3%      diffuse             3.0%      emissive       1.4%
    roughness          15.1%      specular            2.9%      specularLevel  1.2%
    height             15.1%      opacity             2.3%      bump           1.0%
    ambientOcclusion    9.2%      glossiness          2.2%

That is the PBR channel vocabulary, and it is what an importer should bind to.

### Bind to the channel name, not the identifier

Both fields exist and they are not equivalent:

    <output uid="3735825577" identifier="basecolor" type="5" format="12" ...>
      <outputgui label="Base Color" group="Material">
        <channels><channel names="baseColor" colorspace=""/></channels>

`identifier` is author-chosen and inconsistent across the corpus - `basecolor`, `Height`,
`ambientocclusion`, `ambientOcclusion`, and `output` 103 times, which says nothing at all.
`names` inside `<channels>` is a **controlled vocabulary** with stable camelCase spelling.
A reader matching on `identifier` will mis-bind; matching on `names` will not.

### The format code corroborates the role

The `format` attribute takes 0, 12, 16, 28, 64, 76, 80, 92 - and splits cleanly by what the
output is for:

    baseColor          fmt 16: 57%   fmt 0: 39%          <- colour roles
    normal             fmt 16: 84%   fmt 0: 13%
    diffuse            fmt 16: 61%   fmt 0: 39%
    ----
    height             fmt 28: 93%                       <- greyscale roles
    ambientOcclusion   fmt 28: 87%   fmt 12: 11%
    roughness          fmt 28: 64%   fmt 12: 33%
    metallic           fmt 12: 56%   fmt 28: 39%

Colour roles take {0, 16}; single-channel roles take {12, 28}. The codes are additive - 28 =
16+12, 76 = 64+12, 92 = 64+16+12 - so 12 marks single-channel and 16 and 64 are depth or
colour-space bits, but the corpus does not separate those two readings and they are not asserted.

The practical use is as a **cross-check**: an importer that has bound an output to `roughness`
and finds `format` 16 has probably bound it wrong.

### The 12.5% without a role are not a gap

    output   86      ORM  10      NOH  10      AR  10      MASK_01..03  10 each

These are generic single-output graphs, and **channel-packed textures** - `ORM` is
occlusion/roughness/metallic in three channels, `NOH` normal/occlusion/height. A packed map has
no single PBR role by construction, so the absence is correct rather than missing data. An
importer should treat a role-less output as opaque and let the user assign it.

### Where this leaves the importer problem

    what an output is for      manifest, 87.5% explicit, controlled vocabulary
    which record produces it    nowhere - must be recovered by evaluating the graph
    what feeds in               binary, by uid, 99.3%

The asymmetry recorded earlier is sharper than it looked: the format is not silent about outputs,
it just puts everything *except the graph connection* in the manifest.

## End-to-end: reconstructing graphs from the binary and checking them against the sources

The segmenter makes the obvious validation possible for the first time - build the node graph
from the binary, build it from the `.sbs`, and compare. Over the 13 instance-free paired files:

    file                              src nodes  bin nodes   src edges  bin edges
    st_wood_fine_20                      14         14           7          6
    SubstanceDesigner__color             16         17          13         13
    ie_processing                         4          4           2          1
    SubstanceTools__radial_blur_color     2          2           1          0
    Metal_Vent_006                        6          6           0          0
    ...
    node-type multiset matches exactly : 12/13
    edge count matches exactly         :  6/13

**The node-type multiset matches in 12 of 13 files** - every filter identification, the
input-bridge-becomes-bitmap rule, and the output-bridge-emits-nothing rule, all confirmed
together against ground truth. The one miss is `SubstanceDesigner__color`, which carries one
extra `uniform` record, the same anomaly noted when that file was first examined.

### A near-miss worth recording

Edge counts were short, always by **exactly one**. Inspecting the simplest case,
`PolarCoordinates2Grayscale`, the `pixelprocessor` record has arity 1 and its single edge slot
holds **zero** - while record 0 in that file is precisely the `bitmap` the source says it reads.

That suggested the rule recorded earlier in this document, "zero in an edge slot means no
input", was wrong and that zero is simply record index 0. Re-counting all 13 files on that
reading:

    source edge count == binary edges, counting zero as record 0 : 12/13

Twelve of thirteen. On the paired corpus alone the hypothesis looks established.

**It is wrong.** The corpus-wide test that validated edges in the first place settles it - a real
edge's target shares the record's resolution:

    nonzero edges (known real)          804,855 / 921,654 = 87.33%
    zero edges, read as record 0            936 /   2,763 = 33.88%

Chance. Zero does not point at record 0; **zero means no input, and the original rule stands.**

The 12-of-13 agreement was an artifact of the paired corpus being tiny and unrepresentative:
these files have two to sixteen records, record 0 is a source node in all of them, and with so
few records a spurious edge to record 0 lands on something plausible by construction. The corpus
that could test the hypothesis is 382 files and 921,654 edges; the corpus that appeared to
confirm it is 13 files and 34 edges.

**This is the same failure mode as the vacuous match rates earlier in this session, and it very
nearly reversed a correct finding rather than manufacturing a new one.** The habit that caught it
was reflexive: run the discriminating test that established the rule originally, on the full
corpus, before believing a contradiction from a small sample.

### What the edge deficit actually is

With zero correctly read as "no input", the deficit is real and it is informative: **a
`pixelprocessor`'s image inputs are not expressed as record edges.** Its edge slot is empty and
its program samples through `samplelum`/`samplecol` with a sampler index instead.

So the record-edge graph is **not the complete dataflow graph**. For most filters it is, but a
`pixelprocessor` connects to its inputs through its bytecode. A reader reconstructing a graph
must union the record edges with the sampler references inside pixel-processor programs, and
this document had not said so.

Zero edges are concentrated where a genuinely optional input exists:

    warp 61.2%   transformation 17.3%   shuffle 10.2%   blend 3.9%   directionalwarp 3.5%

`warp` dominating is exactly right - its intensity input is optional.

## The sampler index resolves, and edge indexing is confirmed 0-based

Two results close out the graph model.

**The sampler index selects the record's Nth image input.** A `pixelprocessor` reaches its inputs
through `samplecol`/`samplelum` with an immediate index, and that index is bounded by the record's
own arity in **105 of 105 observations** - arity 1 uses index 0 only, arity 2 uses 0 and 1. So
`samplecol %pos, #N` reads the record's slot `2 + N`. A reader can now bind every sample to a
specific input record.

**Edge values are 0-based indices**, tested against the alternative directly:

    value -> record[value]      924,412 edges   resolution agreement 87.17%
    value -> record[value - 1]  921,654 edges   resolution agreement 79.97%

The seven-point gap settles it, and rules out the off-by-one that would have made a zero edge
into a sentinel by construction.

**Zero remains genuinely ambiguous, and it is the format's ambiguity rather than a gap here.**
In `st_wood_fine_20` - seven identical `bitmap -> transformation -> output` chains - the
transformation at index 1 has edge value 0 and unquestionably reads the bitmap at index 0.
Corpus-wide, though, zero edges agree in resolution only 32.4% of the time when record 0 is a
source node, against 87.17% for nonzero edges. Both readings have support and neither is
general: **the encoding does not distinguish "reads record 0" from "reads nothing", and context
has to.** Record 0 is never referenced under a strict reading in 51 of 370 files, which is the
size of the residue either way.

## The corpus is now the binding constraint, and here is the shape of it

Enough separate questions have ended in "not enough specimens" that it is worth stating exactly
what the corpus provides.

    .sbsar specimens (deduplicated)                    383
    with a paired .sbs source                          140
      permitted (no Allegorithmic-authored graph)      102
        and instance-free (no compInstance)             13

**Thirteen.** Instance-free files are the only ones giving node-level ground truth, because
`compInstance` inlining means a binary record count no longer corresponds to any source node
count. And those thirteen cover almost nothing:

    filter              count-exact files    permitted files    instance-free files
    blend                      7                  69                   0
    levels                     4                  36                   0
    gradient                   8                  36                   0
    hsl                       20                  27                   0
    warp                       3                  21                   0
    fxmaps                     2                  10                   0
    passthrough                0                  26                   0
    grayscaleconversion        0                  25                   0
    curve                      0                  10                   0
    valueprocessor             0                  10                   0
    dirmotionblur              0                   4                   0

**Five filters have zero count-exact files** despite appearing in ten to twenty-six permitted
sources each. `passthrough` and `grayscaleconversion` are in twenty-five sources apiece and never
once produce a matching record count - inlining always adds records first. No amount of further
analysis identifies them from this corpus.

### What each open question needs

    question                          what would close it
    fid 11 = motionblur?              any permitted .sbs using motionblur - all 3 are excluded
    fid 5 = svg?                      any permitted .sbs using svg - the only one is excluded
    fid 19, fid 22                    an instance-free .sbs using a v4+ filter
    fid 8 = emboss?                   more than the single file now supporting it
    FX-Map node encoding              instance-free .sbs with an FX-Map; the corpus has one
                                      material, extracted twice
    passthrough, grayscaleconversion  an instance-free .sbs using either
    blend bits 4 and 8                sources declaring `outputsize` on blend - 6.4% do, and the
                                      bits vary across 96% of records, so the overlap is empty
    layout-B prologue                 more than 30 version-2 files

Every one of these is a specimen problem, not a method problem. The methods that worked here -
range tests that cannot be exceeded, tagged unions with disjoint readings, instruction-boundary
alignment, resolution agreement - would all apply immediately to a wider corpus.

**The single highest-value acquisition is instance-free `.sbs` files**, which are rare in this
corpus by accident rather than by nature: most authors use sub-graphs, but simple published
materials often do not. Thirteen became the ceiling on graph-level validation, and the near-miss
recorded above - where 12 of 13 files agreed on a hypothesis that 921,654 corpus-wide edges
refuted - is what a thirteen-file ground truth is worth.

## A validation that does not need instance-free files

The graph reconstruction above used the 13 instance-free specimens because equality needs them.
**Containment does not.** Inlining can only *add* records, so for every filter in every permitted
paired file the binary count must be at least the source count - a weaker claim that holds over
102 files instead of 13.

Run as a validation of the filter table rather than as an identification test:

    permitted paired files                102
    containment tests (filter x file)     495
    hold                                  439    88.7%

Conditioned on how many graphs the source declares:

    single-graph source     312 tests    96.8% hold
    2-3 graphs              118          67.8%
    4+ graphs                65          87.7%

**96.8% over 312 tests in single-graph sources**, and the multi-graph shortfall has a mundane
cause: a multi-graph `.sbs` cooks to several `.sbsasm` files, while `pairmap.txt` pairs one
source with one binary, so the source legitimately contains nodes the paired binary does not.
That is a defect in the pairing, not in the filter table.

Six filters hold at **100%**: `pixelprocessor` (25 files), `warp` (21), `directionalwarp` (17),
`distance` (14), `fxmaps` (10), `sharpen` (8). The weakest are `bitmap` at 66% and `blur` at 72%,
both concentrated in the multi-graph files.

### Why this matters for the corpus problem

The count-exact method that identified `blendingmode`, `hsl` and `shuffle` needs a filter's
source and binary counts to be *equal*, which the instance-free requirement makes rare - 13 files,
and zero of them contain a `blend`, a `levels` or an `hsl`.

Containment needs only that the binary have *at least* as many, which every permitted file
supports. It cannot identify a filter on its own - a common filter satisfies containment against
any rare source filter, which is exactly how the `directionalwarp` identification had to be
supplemented by the greyscale-control-input constraint. But it **falsifies**: `dirmotionblur` was
eliminated as filter 13 by a single containment failure in four files, and `curve` as filter 19
by eight failures in ten.

So the corpus supports two tiers, and it is worth being explicit about which is which:

    equality (13 files)      can identify        cannot scale
    containment (102 files)  can only refute     scales to the whole permitted corpus

Most of the open filter questions are now refutation problems - several candidates each, needing
elimination rather than proof - and those are the ones the wider corpus can still address without
a single new specimen.

## Corpus expansion: what is actually available

Searching for more specimens, with the provenance rule unchanged - freely distributed files, and
nothing that is Adobe's own library content obtained through unofficial redistribution.

### Clearly permitted and available: 57 more ambientCG substances

    ambientCG Substance assets in the catalogue      209
    already in this corpus                           152
    available and not yet held                        57

CC0/public domain, and the source of most of the existing binary corpus. Distributed as `.sbsar`
in two variants - COMPILED (~7.6 MB) and COMPILED-XL (up to 461 MB); only the former is wanted.

**What 57 more `.sbsar` would move**, all of it binary-side statistics:

    tag 0x0A / filter 5     currently 5 specimens; concentrated in road and tile materials,
                            which is exactly what the missing 57 are likely to include
    filter 9                5 records total, version-2 only
    filter 17 (text)        11 specimens
    layout B / version 2    30 files - the only layout whose prologue is undecoded
    opcode tail             operation 0x03 sits at 286 instructions in 11.7M

**What it would not move at all**: every filter identification, FX-Map internals, and the blend
parameter bits. Those need `.sbs` sources, and ambientCG gates its `.sbs` behind Patreon, so they
are not freely distributed and stay excluded.

### The `.sbs` problem is a search problem, not a supply problem

The binding constraint is instance-free `.sbs` files, and the tools available could not find them:

    GitHub code search      requires authentication; the stored token is stale and the sandbox
                            has no outbound network from the shell
    grep.app                HTTP 429, rate limited
    web search              surfaced mostly repositories already harvested into this corpus
                            (sd-ie-lib, sat-scons, DLG-Tools) or plugins and wrappers with no
                            material files at all

Three new candidates did surface:

    Gil-1/SubstanceDesignerTools    MIT       1 .sbs (Simple_Triplanar_Texturer)
    frugbug/labpbr-substance-tools  MIT       custom node library, .sbs count unconfirmed
    ibeefalone/SD-TD                NO LICENSE  Bricks.sbs paired with Bricks.sbsar

The third is the only new *pair* found and it carries no license, which is weaker than everything
already in this corpus. Recorded but not taken.

**Excluded on provenance:** ambientCG `.sbs` (Patreon-gated), Adobe Substance 3D Assets, and
several repositories advertising "comprehensive collections of high-quality PBR materials and
smart nodes" - phrasing that describes Adobe's shipped library rather than authored work.

### Assessment

The existing corpus was assembled by GitHub code search across roughly 22 repositories. Repeating
that harvest is the highest-value action available and it needs working GitHub authentication -
not a different method, just access to the search that found these files in the first place.

## Corpus acquisition, August 2026

With working GitHub code search, the harvest that built this corpus was repeated. The result
reframes the problem more than it enlarges the corpus.

### What code search actually finds

Searching by extension alone is useless - `.sbs` is also a rockbox theme format, and the first
hundred hits were dominated by unrelated repositories. Searching by **content** works:
`compImplementation` restricted to `.sbs` returns real Substance sources, and three different
content terms surfaced 32 distinct repositories.

Four of those - `Hard-Science-Old`, `LGMLtools`, `Portfolio`, `Substance-Designer-Toolsets` - are
already in this corpus, which confirms the method is the one that built it.

### The finding that matters: sources and archives are rarely committed together

    frugbug/sd-nodes-fj          30 .sbs     0 .sbsar    MIT
    inexorgame/textures          20 .sbs     0 .sbsar    CC0-1.0
    ben-wilson-github/bw_tools   16 .sbs     0 .sbsar    MIT
    GameCult/Aetheria             0 .sbs    41 .sbsar    MPL-2.0
    TheRiverNyx/3DModeling...     0 .sbs    12 .sbsar    none

Authors commit **either** the editable source **or** the published archive, almost never both.
A `.sbs` without its `.sbsar` gives no binary ground truth, and cooking one requires the Substance
engine, which this project excludes. **That is why the corpus has 140 pairs and not more - not
because sources are scarce, but because pairs are.**

The largest source repository found, `fsindr/garden-substance` with 241 `.sbs` and 5 `.sbsar`,
carries no license at all and was left for the corpus owner to decide on.

### Acquired

    72 .sbs sources from 10 MIT / CC0 / MPL repositories       6.4 MB
    57 .sbsar from ambientCG, CC0                            395 MB

Provenance check on the sources: **0 of 72 contain an Allegorithmic-authored graph**, so all are
permitted. Twenty-five are instance-free - nearly doubling the thirteen that were the ceiling on
graph-level validation - but with no paired archive they cannot serve as binary ground truth.
Their value is source-side only.

Four of the new sources match assemblies already in the corpus, and all four are from
`inexorgame/textures`, which is the repository the existing `textures__` specimens came from. No
new pairs.

### The better search, identified but not yet run

**244 corpus assemblies have no paired source.** Their names are known - `Bricks`, `Camouflage`,
`Carpet`, `Cliff`, `Cobblestone`, `Clean_Steel_01` and so on - which turns an open-ended hunt into
a lookup: search for each specific name as a `.sbs`. One such match was already seen in passing
(`ibeefalone/SD-TD` holds `Bricks.sbs` alongside `Bricks.sbsar`), though that repository is
unlicensed.

That is the highest-value remaining acquisition, and it is a targeted search rather than a
speculative one.

## The parser was 59x slower than it needed to be, for a documented reason

Profiling the corpus audit put 95% of parse time inside `find_footer`, which made **6.5 million
`struct.unpack_from` calls** across twelve files. Three changes, each verified to leave output
bit-identical over all 435 specimens:

**1. The footer is the last sixteen bytes of the file.** `find_footer` scanned the entire file at
four-byte steps looking for the footer's arithmetic signature. It never needed to:

    footer is exactly at len(d) - 16      435 / 435 specimens      100.00%

The scan exists because `standalone_parse.py` was written to prove a point - its docstring says
"from a `.sbsasm` alone, no manifest" - and a self-describing parse cannot assume a layout it has
not verified. That was the right instinct when the format was unknown. Now that the trailer is
fully decoded, the position is a *fact*, and the scan is answering a settled question. It is kept
as a fallback so any file not following the convention still parses; it simply never runs.

**2. Cast once instead of unpacking per offset.** The remaining scans read u32s through
`struct.unpack_from` one at a time. `memoryview(d).cast('I')` gives the whole buffer as an integer
array, and the header search likewise becomes one integer comparison instead of an
`unpack_from("<HH")` per candidate.

**3. `coverage()` counted bytes in Python.** It was 97% of the audit's runtime and made **119
million `dict.get` calls** - one per byte of every file - plus a Python loop per marked range.
`bytearray` slice assignment and `bytearray.count` do both at C speed.

    parse                88 ms/file  ->  1.5 ms/file      59x
    full corpus audit    ~177 s      ->  25 s             (435 files, 4.09 GB)

**Equivalence was checked, not assumed**: the optimised parser was run against the original on
every specimen, comparing the full result dict. 435 identical, 0 different, 0 differing
exceptions. The original is kept as `standalone_parse_ref.py` so the check can be repeated.

The general lesson is narrow and worth keeping: **two of the three hot spots were doing work the
format had already made unnecessary**, and the third was doing byte arithmetic in the wrong
language. None of it was algorithmic cleverness.

## The model holds on 53 specimens it has never seen

The 57 ambientCG acquisitions extract cleanly and 53 are new content (four duplicate existing
specimens). Re-running the audit on the enlarged corpus:

                            before (382)        after (435)
    records                    651,743            895,674
    filter identified            97.8%              97.9%
    main parameter resolved      94.2%              94.7%
    edge slots resolved         99.95%             99.96%
    unexplained bytes                0                  0     of 4.09 GB
    parse failures                   0                  0

**Every metric held or improved on a 37% larger corpus, with no change to any table.** That is
the strongest evidence so far that the filter table, the edge map, the layout probes and the
parameter union are describing the format rather than fitting this particular set of files.

Several filters improved outright now that the audit measures the parameter union rather than
only located programs: `levels`, `blur`, `normal`, `sharpen` and `hsl` all fall to 0% unresolved.
`bitmap`, `fid 5` and `fid 8` remain at 100% - correctly, since a bitmap has no parameter program
and the other two are unnamed filters with no layout entry.

## Filter 5 (tag `0x0A`) opened: it embeds compiled vector geometry

`0x0A` has been a terminal item since early in this document - "five specimens, no sources".
The corpus expansion took it to **nine specimens**, and that was enough.

### Where it appears

    RoadSubstance002               70 records      v9
    RoadLinesSubstance002          35              v9
    RoadLinesSubstance001           9              v5    <- new
    TilesSubstance013               7              v5
    SnowSubstance002                6              v5
    FootstepsSubstance001           6              v5    <- new
    ChristmasTreeOrnamentSubstance002/004  3 each   v5    <- new
    Shield_Front                    1              v2

**Road lines, footsteps, Christmas ornaments, tiles, a shield.** Every one is a material whose
content is a *shape* - a decal, a marking, an outline - rather than a texture. The four new
specimens all fit the pattern that the five old ones suggested.

### The record carries a data blob

    0219880A  000EA754  000F4184  3F800000  00000003  00013449   len 39496
    0219880A  000F41E8  000F9610  3F800000  00000003  0000A839   len 21568
    0219880A  000F9674  00104408  3F800000  00000003  00015B11   len 44460

Slots 1 and 2 are **start and end offsets of an embedded blob**, on the usual +52 skew, and

    blob length  ==  record length - 24

exactly, in every case. The record is a 24-byte header followed by its payload. Consecutive
filter-5 records address consecutive blobs. Slot 3 is a float (1.0 here), and slot 5 repeats the
blob's own second word.

### What the blob contains

Not SVG text - it is binary, 30-34% printable, and structured in 4-byte groups with heavy
repetition:

    fbffff07 69000000 4690ffff e674f75d b96fffff b96fffff 9156f75d 9156f75d 9156f75d ...

`b96fffff` twice and `9156f75d` three times in sixteen words. A simple road-line drawing uses
only **20 distinct byte values across the whole blob**, while a complex tile pattern uses all
256. That is the signature of a **point or path list** - a small vocabulary of repeated
coordinates for simple shapes, a large one for complex geometry.

So filter 5 is a generator that rasterises embedded vector geometry, which is what `svg` does.
**The identification still cannot be confirmed** - `svg` appears in exactly one source file in the
corpus and that file carries an Allegorithmic-authored graph - but the filter has moved from an
unexplained tag to a characterised structure:

    input-less generator, greyscale, consumed by blend (110) and transformation (21)
    slots 1,2   blob start and end, +52 skew, blob = record length - 24
    slot 3      float parameter
    blob        binary path/point data, low entropy for simple shapes

A reader can now skip these records cleanly, and extract the geometry if it ever decodes the
point format.

### What the expansion did and did not buy

    fid 5     5 -> 9 specimens      opened it
    fid 17   11 -> 13               unchanged conclusion
    fid 8    79 -> 92               unchanged
    fid 9     4 -> 4                no new specimens; still version-2 only
    layout B 30 -> 30               no new version-2 files at all - all 53 are v5/v6/v9

**No new layout-B specimens**, so the undecoded version-2 prologue is exactly as blocked as
before. ambientCG publishes with a current cooker, so its files will never supply old-format
specimens - that gap needs a different source entirely.

## Non-flat files: the constraint is measurement, not provenance

A question worth separating carefully, because two different limits have been getting conflated.

### The provenance rule does not restrict non-flat files

The rule excludes **Adobe's `.sbs` library sources obtained through unofficial redistribution** -
it is about how a file was acquired, not about what a compiled binary happens to contain.

Analysing a freely distributed `.sbsar` is legitimate interoperability work whatever graphs were
inlined into it. And every specimen in this corpus already contains inlined library content:
`compInstance` expansion is precisely why a file with 17 source blend nodes has 63 blend records.
**The filter table, the edge map, the opcode catalogue, `blendingmode`, `shuffle` and the bitmap
format were all derived from binaries dense with inlined library graphs, and always were.**
Nothing about using non-flat files is new or newly permissible.

What is excluded is *reading the library's own `.sbs` sources* to find out what those inlined
graphs are. That line has not been crossed and does not need to be.

### The real limit is that inlining destroys the count correspondence

Flat files matter for one reason: when no instance is expanded, source node count equals binary
record count, which is what makes node-level identification possible. That is a measurement
property, not a legal one.

And the flat corpus is smaller than previously stated here. Deduplicating by source content:

    pairmap rows                                      140
    permitted (no Allegorithmic-authored graph)       102
    flat (no compInstance)                             13 rows
    flat, distinct materials                            9

Four of the thirteen are the same material harvested twice under different repository names.
**Nine distinct flat materials** is the true ceiling, not thirteen.

### The method already in use handles this correctly

Whole-file flatness is not required, and this document has not required it since the
`blendingmode` work: **per-filter count-exactness** is the actual criterion. If a file's binary
count for filter X equals its source count for X, then no expanded instance contributed an X,
whatever else the file inlines. The test validates itself.

That is why identifications came from far more than nine files:

    hsl              20 count-exact files
    transformation    8
    gradient          8
    normal            9
    bitmap           15
    pixelprocessor   15
    blend             7

None of those required a flat file.

### Where instance expansion could still help, and where it cannot

Of 2,626 instance references in permitted sources:

    pkg:/// resolving to a graph in the same .sbs    890   33.9%
    pkg:/// external                              1,736   66.1%
    sbs:// (Adobe library scheme)                     0    0.0%

A third resolve internally and could be expanded using only the file's own content - no external
material of any kind. But **zero files have all their instances internal**, so no file becomes
flat by expansion, which is what the earlier attempt concluded.

Partial expansion is still worth something the earlier attempt did not consider: expanding a
file's internal instances can make additional *filters* count-exact within that file, even though
the file as a whole stays non-flat. That is untested and is the one concrete avenue this question
opens.

**Summary: non-flat files were never the problem and are already the backbone of every result
here. The scarce thing is count-exactness per filter, and the way to get more of it is instance
expansion using only in-file graphs - not access to anything of Adobe's.**

## Partial instance expansion, and the first quantitative link to FX-Map structure

The previous section identified expanding a file's *internal* `compInstance` nodes as the one
untried avenue - it uses only the file's own graphs, so nothing external is involved.
`expand_instances.py` implements it.

### As a general technique it does not work

    count-exact (file, filter) pairs
      unexpanded source counts            133
      root graphs expanded                125     net -8

Expansion **loses** more than it gains. The cause is that expanding assumes every internal
instance was inlined, and the compiler does not oblige - dead-code elimination drops unused ones,
so the expanded count overshoots the binary.

A first attempt was worse still (net -15) because it expanded *every* graph rather than only
root graphs, double-counting each sub-graph once standalone and again inside its parent.

The right way to use it is as an **alternative reading, not a replacement**: a filter is
count-exact if *either* the plain or the expanded count equals the binary count. Both are
self-validating - equality means nothing unaccounted contributed that filter.

    count-exact under either reading      135

Two pairs gained. They are the same material twice, so **one new distinct material** - but it is
the one that mattered.

### `ie_pcloud` gives FX-Maps their first real sample

`fxmaps` count-exact ground truth was previously two files that were the same material extracted
twice, with four FX-Map nodes between them. `ie_pcloud` expands from 11 direct `fxmaps` nodes to
**110, matching the binary's 110 records exactly.**

Extracting each expanded node's FX-Map graph contents and comparing to the binary:

    source, paramsGraphData per fxmaps node     {2: 4,  3: 105, 4: 1}
    binary, inline programs per fxmaps record   {3: 3,  4: 102, 5: 3, 7: 1, 8: 1}

**The distributions are the same shape, shifted by one.** The source's dominant node carries 3
graph-data entries and the binary's dominant record carries 4 programs, at 105 and 102 records
respectively; the 2-entry nodes sit against 3-program records, 4 against 5.

The natural reading is **one program per FX-Map node, plus one for the record's own parameters**.

The residue is real and worth stating: 105 against 102 in the bulk, two records carrying 7 and 8
programs, and totals of 447 binary programs against 437 predicted - about 8 of 110 records do not
fit. Common subexpression elimination explains the direction, since a program shared with an
earlier record is not inline in this one and would lower the count, which is what the 105-to-102
shift looks like. It is not proved.

Also recovered: an FX-Map graph in this material contains **one `paramset` and one to three
`addnode` entries** - `(1,2)` in 105 of 110 nodes. That is the source-side shape the binary tree
of `[header][pointer]` nodes has to encode, and it is the first time the two sides have been
measured against each other at all.

**Status: FX-Map internals remain undecoded, but are no longer unmeasured.** The blocker has
moved from "one material, four nodes" to "one relation, fitting 93% of 110 records, with a
plausible but unproved explanation for the rest."

## FX-Map node type `0x18B` identified as `addnode`

The `ie_pcloud` expansion gave FX-Maps their first substantial sample - 110 source nodes
matching 110 binary records exactly. Reading one record whose source composition was known in
advance made the tree legible.

### Reading a record with the answer in hand

The source says every one of these FX-Maps contains **one `paramset` and two `addnode`**
entries. A 1,168-byte record, with its four inline programs subtracted:

    +28   0000018B         node header
    +32   -> +40  PROGRAM
    +36   -> +124
    +124  0000018B         node header
    ...
    +352  00000089         a different node header
    +356  -> +368
    +364  -> +644

**Three nodes: `0x18B` twice, `0x89` once.** Against one `paramset` and two `addnode`.

`0x18B` is the value that appeared at 33.5% in an earlier node-header census and was
**dismissed as contamination** - the census was contaminated, but this value was not the
contamination.

### The distribution settles it

Walking the tree in all 110 records and counting headers:

    binary, 0x18B per record   {2: 105,  1: 4,  3: 1}
    source, addnode per node   {2: 105,  1: 4,  3: 1}

    total 0x18B                217
    total addnode              217

**Identical, including the tail.** One hundred and five records with two, four with one, one
with three - and the source distribution is the same three numbers in the same places. A
walker that found nodes by chance would not reproduce a 4-and-1 tail.

    FX-Map node header 0x18B = `addnode`   confirmed

### `0x89` is not `paramset`

The obvious companion reading does not hold:

    binary, 0x89 per record    {2: 100,  1: 7,  0: 3}
    source, paramset per node  {1: 110}

Roughly two per record against one per node, and three records with none. `0x89` is a real
node type - it sits in the tree, it is pointed at, and it has a consistent shape
`[header][ptr][0][ptr]` distinct from `0x18B`'s `[header][program][next]` - but it is not
the source's `paramset`, and what it is remains open.

### Where FX-Maps now stand

    tree structure        linked [header][pointer] nodes, reached from record slot 2
    node type 0x18B       addnode - confirmed, exact distribution over 110 records
    node type 0x89        real, ~2 per record, unidentified
    programs per record   one per FX-Map node plus one, fitting ~93% of records
    the blob region       the largest part of a record, still undecoded

From "linked structure of unknown nodes" to one node type named against ground truth. The
step that made it possible was not a better walker - three walkers had already failed on this
- but **knowing the answer for one record before looking at it**, which is what the
count-exact expansion of `ie_pcloud` supplied.

## The FX-Map tree read end to end

Scanning a known record for the two node headers, and following each node's pointers:

    +28   0000018B   -> program @+40    next -> +124  (0x18B)
    +124  0000018B   -> program @+136   next -> +352  (0x89)
    +352  00000089   -> +368            0    next -> +644  (0x89)
    +644  00000089   -> +660            0    next -> +1092

**The tree is a singly linked list of mixed node types**, entered from record slot 2, with the
`0x18B` nodes first and the `0x89` nodes after. The two shapes differ:

    0x18B    [header][program pointer][next]        an addnode, carrying its own program
    0x89     [header][data pointer][0][next]        carries a data region, not a program

That accounts for the record's programs exactly. This record has four: two reached from the
`0x18B` nodes, and two more from the record's own slots 4 and 5. The
"one program per FX-Map node plus one" relation recorded earlier is really **one program per
`addnode`, plus the record's own two**, which is why it fitted the bulk and not the tail.

### `0x89` remains unidentified, and the count rules out the obvious answer

    binary 0x89 per record        {2: 100, 1: 7, 0: 3}     total 207
    source paramset per node      {1: 110}                  total 110

Roughly two per record against one per node, and three records carrying none. It cannot be
`paramset`. It is unambiguously a real node - it sits in the chain, it is pointed at by a
confirmed `addnode`, and it has a consistent four-word shape - but the source structure it
corresponds to is not established.

Also confirmed while checking this: in this material `paramsGraphData` and `paramsGraphNode`
counts are identical (110 `paramset`, 217 `addnode`), so each shared definition has exactly one
instance in the tree. That mattered because a first pass counted *both* families and got exactly
double, which would have made `0x18B` half of `addnode` rather than equal to it. The strict
count is the right one and the identification stands.

### FX-Map status

    entered from            record slot 2
    structure               singly linked list, 0x18B nodes then 0x89 nodes
    0x18B                   addnode - confirmed, exact distribution over 110 records
    0x89                    real, four-word shape, ~2 per record, unidentified
    programs                one per addnode, plus two from the record's own slots
    the data regions        pointed at by 0x89 nodes, still undecoded

## What output attribution would actually require

Five approaches have failed to associate outputs with records, and the reason is settled: the
binary does not store the association. The remaining question is what *would* recover it.

### Constraint propagation is not enough

The manifest publishes, for every input, the set of outputs it alters. The bytecode says which
records read which input uid. That gives two constraints per pair:

    p alters o          =>  o's record is downstream of some record reading p
    p does not alter o  =>  o's record is downstream of NO record reading p

The second is the eliminating one. `attribute_outputs.py` implements both. Over 901 outputs:

    narrowed to exactly one record      41    4.6%
    narrowed to zero (contradiction)    49    5.4%
    still 20 or more candidates        664   73.7%

**It solves 5% and contradicts itself on another 5%.** The contradictions are the useful part -
they mean the negative constraint is not sound as stated. Common subexpression elimination is
the likely cause: a program shared between records makes "the records reading p" ambiguous, so
a record can sit downstream of a reader of p without carrying p's influence. Until that is
modelled, the elimination rule over-prunes.

An earlier and weaker version of this test - parameters that alter exactly one output - pins
every output in only **3% of graphs**, median 40% of outputs per graph. Neither version is a
solution.

### So it needs evaluation, and here is the shape of it

The thing that distinguishes one output from another is **what it looks like**. Nothing else in
the format separates them: they have no records, no uids in the body, no reliable resolution,
and 6.7% of files have fewer sinks than outputs.

Three properties make this much cheaper than it first appears:

**1. The renderer does not need to be correct, only discriminative.** The task is to match each
output to one of a few dozen candidate records. A 64x64 evaluation that gets blend modes
approximately right will separate a base colour from a roughness map from a normal map. Pixel
accuracy buys nothing here.

**2. Reference images ship with the material.** ambientCG materials include rendered PNG maps
per output, and every `.sbsar` carries a thumbnail. So candidate assignments can be *scored*
rather than derived - render candidates, compare, rank. Scoring tolerates a poor renderer in a
way that deriving does not.

**3. Most of the machinery already exists here.** The bytecode VM needs the 41 catalogued
operations, whose operand types are verified across 7 million instructions; the disassembler
already decodes them. Graph traversal, record layouts, parameters and inputs are all resolved.

What is missing is per-filter image semantics for roughly fourteen filters - `blend`, `levels`,
`transformation`, `blur`, `warp`, `directionalwarp`, `gradient`, `uniform`, `normal`, `hsl`,
`sharpen`, `distance`, `shuffle`, `bitmap` - plus FX-Map iteration, which is the only genuinely
unresolved piece since its tree is only partly decoded.

**Note what is *not* required**: `blendingmode` values are known (0-11) but their formulas are
not, and they do not need to be recovered from the format - they are the standard Porter-Duff
and photoshop-style blend operations, and approximating them is enough to discriminate.

### Assessment

Output attribution is not a reverse-engineering problem any more; it is a build problem. The
format is understood well enough to walk the graph, resolve every input, and reach every
program. What remains is writing an evaluator good enough to tell a normal map from a height
map, and scoring it against images that ship in the same archive.

The one dependency that is still research rather than engineering is FX-Map evaluation, and
FX-Maps appear in 4.6% of records.

## `fxmaps` input edges resolved, in the layout that has them

`fxmaps` inputs have been listed as unresolved since the segmenter was written, and three
attempts failed - all to the small-integer artifact, since a 331-slot record makes any small
value a valid backward index by construction.

The discriminator that works is the one that established the edge map in the first place:
**a real edge's target shares the record's resolution.** Applied per slot:

    slot   valid backward index   resolution agreement
      1        66.2%                    27.8%      <- the parameter word, chance agreement
      3        13.3%                    75.4%
      4         9.5%                    96.1%
      6         9.3%                    98.1%
      7         8.9%                    96.9%

    control: blend slot 2                100.0%

Slots 4, 6 and 7 agree at 96-98% - far too high for chance - but qualify in under 10% of
records. Restricting to records with index above 200, in case low indices were forcing
agreement, gives 96.2% and 98.0%: **the effect is real and not a position artifact.**

### The layout is selected by a bit in the parameter word

Grouping records by whether slot 6 resolves, the parameter word separates them almost
perfectly. Testing each bit:

    bit 12 set    1,271 have a slot-6 edge,      6 do not
    bit 12 clear    141 have one,           14,076 do not      99.1% accurate

Within the bit-12 layout, every slot behaves:

    slot  3   valid or zero 100.0%   resolution agreement 94.7%
    slot  4                 100.0%                        99.6%
    slot  5                 100.0%                        99.7%
    slot  6                 100.0%                        99.8%
    slot  7                  99.9%                        99.8%
    slot  8                  99.9%                        99.8%

and the program moves to slot 9 (94%), where the other layout keeps it at slot 3 (94%).

    fxmaps, bit 12 set     edges [3,4,5,6,7,8], program at slot 9    8.3% of records
    fxmaps, bit 12 clear   no resolvable edges, program at slot 3

**The hand-written edge map this project started with had `0x08: [3,4,5,6,7,8]`.** It was
dropped during the empirical derivation as unsupported. It was right - for one of two layouts -
and what was missing was the selector, not the slots.

### Effect

    main parameter resolved   94.7%  ->  95.0%
    fxmaps records with none    13%  ->     5%
    edge slots              1,271,419 -> 1,291,651   (20,232 new edges, still 99.96% resolved)

The remaining 91.7% of `fxmaps` records genuinely have no input edge in any slot, which is
consistent with an FX-Map that generates rather than transforms - and with the tree, not the
record, carrying whatever input references those records use.

## `0x89` nodes carry programs too, and the FX-Map program count resolves

The `0x89` node's second word was recorded above as a "data pointer" because
`valid_program` rejected what it pointed at. That was wrong, and the reason is narrow: those
programs are reached **through the tree**, and the program finder only followed record slots.

Decoding a `0x89` target as a length-prefixed program:

    +368   declared 50 instructions   decoded 50 of 50   ends at +644
    +660   declared 74 instructions   decoded 74 of 74   ends at +1092

Both decode completely, with zero invalid opcodes, and each ends **exactly** at the next node's
offset. So both node types carry a program:

    0x18B    [header][program][next]           addnode
    0x89     [header][program][0][next]        still unnamed, but not a data node

### Programs per record, counted properly

Including tree-reached programs across all 110 records of `ie_pcloud`:

    binary programs per record   {3: 2,  4: 1,  5: 4,  6: 100, 7: 2, 8: 1}
    source dynamicValue per node {5: 3,  6: 4,  7: 102, 8: 1}

    total binary programs    652
    total source dynamicValue 761
    difference               109, against 110 records

**One program per `<dynamicValue>`, less one per record** - to within a single program over 110
records. The modal record has six programs against seven dynamic values, and the 6-against-4
bucket matches exactly.

The missing one per record is most likely `outputsize`: it is a `dynamicValue` in the source like
any other, but the record resolves its own size through the parameter slot rather than through
the FX-Map tree, which is exactly the mechanism documented for every other filter.

### Two corrections this forces

The relation reported earlier - "one program per `addnode`, plus the record's own two" - was
built on an undercount that missed every tree-reached program. The correct statement is the one
above, and it is both simpler and closer to exact.

More generally, **the record-slot program count is not the record's program count** for
`fxmaps`. Any measurement of program density, CSE rates or bytecode volume that walked only
record slots has undercounted `fxmaps`, which is 4.6% of records.

## Reading the FX-Map disassembly, rather than counting it

Everything above about FX-Maps came from counting nodes and programs. Disassembling one and
reading it produces more in one pass, and immediately exposes a bug in the disassembler.

### `swizzle` has its operands the other way round

The first FX-Map program contained `%1 swizzle.f1 #0, %9!` - a forward operand reference, which
contiguous three-address numbering forbids - while `%9 swizzle.f1 #0, %0` in the same program was
fine. Same opcode, so the operand order had to be wrong.

Over 144,632 `swizzle` instructions:

    token 0 is a valid backward value reference   100.0%
    token 1 is a valid backward value reference    61.6%
    token 0 values   {1, 35, 49, 3, 0, 10, 77, 37, ...}   max 167
    token 1 values   {78, 1, 0} and almost nothing else   max 78

Token 1 takes three values in the whole corpus; token 0 spreads. **`swizzle` is
`(source, mask)`**, and the disassembler had it as `(mask, source)` - the same mistake, in the
same place, as `set`.

The check that matters is what it does to the corpus as a whole:

    instructions decoded                          1,750,691
    with an impossible forward operand reference          2      0.0001%

Two, in one and three quarter million. The disassembler is now self-consistent, which it
demonstrably was not before.

**This also corrects the operand type table published earlier.** The row
`swizzle f1 arg 1: i2 53%, f2 45%` was typing the mask; the source operand is arg 0.

### The tree is an execution sequence with a shared variable frame

Node 1 of the record ends `set.f2 %3, #0` and `set.f2 %6, #2`. Node 2 begins `get.f2 2` and
later `get.f2 0`. **The second node reads what the first wrote.**

Evaluating each record's programs in chain order - the record's own program first, then each
tree node's - and asking whether every `get` finds a slot some earlier program set:

    resolved by an earlier program in the same tree   49,072   77.5%
    still never set                                   14,253   22.5%

Measured per program in isolation, 39.2% of `fxmaps` programs read a never-set slot. Measured
along the chain, three quarters of those resolve. **The FX-Map tree is not a data structure the
engine interprets node by node in isolation; it is a straight-line program sharing one variable
frame**, and the chain order is the execution order. The residual 22.5% is what the engine
genuinely seeds.

### What the programs actually compute

The second node of `ie_pcloud`'s FX-Map, read directly:

    %1   sysvar.f1 #10          $number, the iteration index
    %4   mul.i1 %2, 2
    %7   cvt.i1 (a graph parameter component)      call it W
    %8   mod.i1 %4, %7                             column
    %14  div.i1 (%number * 131072), %7             row
    %16  vec.f2 %9, %15                            (column, row)
    %17  get.f2 0                                  cell size, set by node 1 as 1/param
    %18  mul.f2 %16, %17                           scale to UV
    %19  add.f2 %0, %18                            offset by base position
    %20  set.f2 %19, #4                            store the instance position
    %29  samplecol.f4 %19, #0                      sample the input image there
    %30  set.f4 %29, #10                           store the sampled colour

**A grid scatter.** It turns the iteration index into a cell coordinate by `mod` and `div`
against a grid width, scales it to UV, and samples an input image at that point to colour the
instance. The material is called `ie_pcloud` - a point cloud - and that is exactly what this is.

That is the first FX-Map program in this document to be read rather than counted, and it makes
the structure concrete: **`$number` in, an instance position and colour out, once per
iteration.**

One small gap closed on the way: integer `div` (operation `0x15`, int) was rendering as
`op15` because the disassembler's name table only had the float form.

## The FX-Map "blob" is mostly bytecode, and the node vocabulary is larger than two

Earlier sections put 64.5% of `fxmaps` record bytes outside anything decodable, then 45.3% once
tree programs were counted. Both figures were artifacts of my own walker.

### A third node type, found by reading

Following one record's chain by hand rather than by whitelist:

    +160    0000018B   -> +172 PROG    next -> +11448
    +11448  000001AB   -> +11464 PROG  -> +11496 PROG   next -> +66988

`0x1AB` is a node carrying **two** program pointers where `0x18B` carries one. The chain walk
never saw it, because it only accepted headers `0x18B` and `0x89` and stopped at anything else -
which is why chains terminated early and the rest of the record looked like an undecoded blob.

The largest "unexplained region" in the corpus, 67,034 bytes, turned out to begin two bytes
before a program's count word. Programs are u16-aligned, not u32-aligned, so a region can start
at 2 mod 4 and a word-aligned dump makes it look like noise.

### Measuring coverage soundly

A greedy scan for anything that decodes would cover almost any record - roughly half of all u16
values are valid opcodes, which is what produced the phantom opcodes earlier in this document.
The sound test requires each program to be **referenced**: a program only counts if some
4-aligned word in the same record points at it.

Applying that to every `fxmaps` record:

    programs located, each with an in-record reference   144,273
    bytes covered                                          89.4%
    unexplained                                            10.6%

    for comparison, the {0x18B, 0x89} chain walk covered   54.7%

**`fxmaps` records are about 90% bytecode.** The "blob region" this document has referred to
since the FX-Map work began is not a data format waiting to be decoded - it is programs, and the
only reason they were invisible is that the walker could not reach them.

Confirmation that these are real rather than scan artifacts: in the record examined by hand, all
five programs are referenced from 4-aligned words at +164, +11452, +11456, +67000 and +67004 -
and the last two sit in a run of five consecutive program pointers, which is a structure the
walker does not model at all.

### What is still open

The node vocabulary is **not** settled. Walking with no whitelist at all produces `0x18B` (42%)
and `0x89` (35%) cleanly, plus `0x20008` (10%) and `0x1CB` (2%) which appear as chain roots and
are probably real - but also values like `0x22000D48` that plainly are not, because the walk has
no way to know a node's size and guesses where the next pointer sits.

Settling it needs the shape-per-header rule, and the three known shapes differ:

    0x18B    [header][program][next]
    0x89     [header][program][0][next]
    0x1AB    [header][program][program][next]

**Corrected status:** `fxmaps` records are ~90% located bytecode, three node shapes are known,
the vocabulary is open, and the figure to quote for undecoded FX-Map content is **10.6%**, not
45%.

## Verifying the 90% figure, and where FX-Map structure stops yielding

The claim that `fxmaps` records are ~90% bytecode rests on accepting a program whenever some
word in the record points at it. That is exactly the kind of permissive rule that manufactured
the phantom opcodes, so it needs checking rather than repeating.

**Check 1 - are the references coming from inside other programs?** A float immediate read as a
u32 could point at a valid program by chance. Recomputing as a fixed point, accepting a program
only if its reference lies outside every already-accepted program body:

    programs accepted   144,207   against 144,273 accepting all references
    coverage              89.4%   unchanged

Sixty-six programs of 144,273. The references are not coming from program interiors.

**Check 2 - do the programs overlap?** Random false positives would nest and overlap heavily;
real programs laid out in a record should tile it.

    program spans detected              88,671
    starting inside another (nested)        40    0.05%
    coverage from non-nested spans only    88.5%

**Forty out of 88,671.** Twelve programs per record, essentially non-overlapping, covering 88.5%
of the bytes. Chance does not produce a clean tiling. The figure holds.

### Where the structure stops resolving

Knowing the programs is not the same as knowing the nodes. Looking at how the pointers sit:

    runs of consecutive program-pointer words
      1 pointer    56.2%      3 pointers    8.8%
      2 pointers   22.6%      4 pointers   10.4%
      5+                                    1.9%

    the word immediately before a run
      a float or large value   66.0%
      0x18B                    10.5%
      0x89                      8.8%
      0x0, 0x2A, 0xB, 0x1CB    ~5%

Only about a fifth of pointer runs are preceded by a recognisable node header. The rest are
preceded by a float - which is what a *previous program's trailing operand* looks like. So the
pointers are embedded in structures interleaved with the programs, and the preceding word is
usually not a header at all.

That is the limit of what structural inference gives here. Deriving the node vocabulary needs
what named `addnode` in the first place: **a material whose FX-Map composition is known from its
source before the binary is read**. `ie_pcloud` supplied one, and for its records the
`{0x18B, 0x89}` walk is complete - the extra node types appear only in other materials, whose
sources are not in the permitted corpus.

**Status:** `fxmaps` records are ~90% located bytecode, verified two ways; three node shapes are
known; the vocabulary is open and blocked on ground truth rather than on method.

## `0x89` nodes compute predicates: the two node types separate perfectly by result type

Reading a `0x89` node's program rather than counting its occurrences settles what it is.

### The program

Fifty instructions from `ie_pcloud`, read end to end:

    %1   sysvar.f1 #10                 $number
    %8   mod.i1 (N*2), W               column        } identical to the addnode program's
    %14  div.i1 (N*131072), W          row           } placement computation
    %19  add.f2 base, scaled           this instance's position
    %20  samplecol.f4 %19, #0          sample the image there
    %26  get.f4 10                     the colour another node stored in slot 10
    %29  sub.f1 (this.x, stored.x)
    %30  abs.f1
    %32  lt.b2 %30, threshold          |dx| < t
    %37  lt.b2 |dy|, threshold         |dy| < t
    %38  and.b2 %32, %37               both
    %43  eq.b2  N, param0
    %44  or.b2
    %46  eq.b2  N, (the N stored in slot 6)
    %47  not.b2 %46                    ... and this is not the same instance
    %48  and.b2

**It is a proximity test.** The node recomputes the current instance's position, samples the
image, compares it against the position another node stored, and asks whether the two are within
a threshold in both axes - while excluding the case where the stored iteration index equals the
current one, so an instance is not compared with itself.

For a material called `ie_pcloud`, an O(N^2) pairwise neighbour test between scattered points is
exactly the right thing to find.

### The result type separates the node types completely

If `0x89` computes a predicate, its program should end boolean-typed. Checking the final
instruction of every node program in the corpus:

    0x18B    12,023 programs    ends i1   100.0%
    0x89     10,048 programs    ends b2   100.0%

**Twenty-two thousand programs, no exceptions either way.** `0x18B` nodes yield an integer;
`0x89` nodes yield a boolean.

That is what `0x89` is: a **conditional node**, evaluating a predicate. Its shape supports it -
`[header][program][0][next]` has a spare word where `0x18B` has none, which is where a second
branch target would sit, and it is null throughout this corpus.

It also explains the count mismatch that blocked this earlier. `0x89` appears 207 times against
110 source `paramset` entries, and the two never lined up because **`0x89` is not `paramset`** -
it is a node kind the source represents some other way, and no amount of matching those two
counts was ever going to work.

### FX-Map node types

    0x18B    [header][program][next]              addnode - confirmed by exact count
                                                  program returns i1, 100% of 12,023
    0x89     [header][program][0][next]           conditional - program returns b2,
                                                  100% of 10,048
    0x1AB    [header][program][program][next]     two programs, unidentified
    0x20008, 0x1CB                                seen as chain roots, unidentified

Reading two programs produced more than every counting pass before them: the execution model,
the shared variable frame, the placement computation, and now the role of the second node type.

## Embedded images: JPEG, float formats, and a 52-byte error

A parallel effort in this project produced `sbsarx/`, a packaged reader built on this format
description. Reading it exposed three things wrong or missing in the account above - the first
of which had been reported here as a verified result.

### Resource offsets carry the +52 skew

`extract_bitmaps.py` read a resource offset raw. It should be skewed like every other pointer in
the format:

    raw       base 4     first bytes  00000500 b4f24072
    raw + 52  base 56    first bytes  d6520000 ffd8ffe0

Fifty-six is `0x38`, the end of the header, which is exactly where the resource segment begins.
Reading raw places the first image **inside the file header**.

Why this survived a verification pass: the earlier check confirmed 516 images with "zero reads
past end of file" and plausible byte statistics. A 52-byte shift satisfies both - the data is
still inside the resource segment, and the byte histogram of an image shifted by 52 bytes looks
like the byte histogram of an image. Nothing in that check could see it.

What does see it is a format with a **magic number**. JPEG resources begin `FF D8`, and under
the corrected offset 45 of 45 land on it exactly. **A self-validating format is worth more than
a plausibility check**, and this document had one available and did not use it.

### Format 8 is JPEG

    [u32 length][JPEG stream]

Forty-five resources, 16.2 MB of compressed data across 10 specimens, every one beginning
`FF D8 FF E0` - SOI followed by a JFIF APP0 marker. The claim above that embedded images are
"raw and uncompressed" is true of the other formats and false of this one.

The tag's declared geometry is the *output* size and need not match the stream's own SOF header,
so a reader should take the geometry from the JPEG.

### The format code is base plus depth

Two more codes appear that the earlier table missed, both with depth byte `0x38`:

    code  depth   format     bytes/px   samples   agreement
      1   0x08    L8            1         142      100%
      2   0x08    RGB8          3         139      100%
      3   0x08    RGBA8         4         109      100%
      5   0x18    L16           2         120      100%
      6   0x18    RGB16         6          26      100%
      7   0x18    RGBA16        8          31      100%
     33   0x38    L32F          4           3      100%
     35   0x38    RGBA32F      16           9      100%
      8   0x08    JPEG          -          45      length-prefixed

The scheme is a **base plus a depth offset**: 1 = L, 2 = RGB, 3 = RGBA, plus 0 for 8-bit, 4 for
16-bit, 32 for 32-bit float, with the class low byte repeating the depth as `0x08` / `0x18` /
`0x38`. Code 34 (RGB32F, 12 bytes) is predicted by the scheme and does not occur here.

The 32-bit float resources are where one would expect them: `NightSkyHDRISubstance001` - an HDRI
- carries the RGBA32F images.

### Effect

    resources located    516  ->  794      in 123 files
    bytes addressed    1,811  -> 3,582 MB
    short reads            0  ->     0
    JPEGs verified by SOI            45 of 45

The corrected table and the JPEG and float handling are in `tools/extract_bitmaps.py`.

## Where the `text` filter's strings live

Measuring how much of the resource segment the image descriptors account for:

    resource segment (0x38 .. first record)   3,579.6 MB
    covered by located resources              3,571.6 MB   99.78%
    resources ending past the first record             0
    trailing uncovered bytes                           0    in all 123 files

The segment tiles exactly and ends flush against the records. **In 120 of 123 files the first
resource begins at `0x38` itself**, which is the independent confirmation that resource offsets
carry the +52 skew - without it the first image would start 52 bytes inside the header.

Three files have something before the first image. One is a JPEG with no short-form descriptor;
one is unidentified; the third decodes as:

    16, 83, 76, 79, 87, 10, 49, 50, 51, 52, 53, 10, 54, 55, 56, 57, 48

A count of 16, then exactly sixteen values: `S L O W \n 1 2 3 4 5 \n 6 7 8 9 0`.

### The format

    [u32 character count][u32 per character]   repeated

Length-prefixed UTF-32, at the head of the resource segment, before the images.

Scanning every specimen for a segment that begins this way:

    files whose segment starts with such strings   9
      containing text (filter 17) records          9
      containing none                              0

    Stop_Sign                  "STOP"
    Yield                      "YIELD"
    One Way                    "ONE WAY"
    Do Not Enter               "DO NOT"
    Speed Limit                "SPEED"
    Lane Markings - Stop Ahead "STOP"
    RoadLinesSubstance002      "SLOW\n12345\n67890"

Nine for nine, none without. And the strings are the rendered content of the materials they
come from.

**This independently re-confirms filter 17 = `text`.** That identification was made on counts,
rejected when the counts turned out to come from a single repository, and reinstated on
structural grounds. It now has a third and much more direct line: the files carrying filter-17
records are exactly the files carrying embedded strings, and the strings say `STOP` and `YIELD`
in materials called `Stop_Sign` and `Yield`.

`tools/extract_bitmaps.py` gained a `strings()` reader.

### What is left in the resource segment

    8.0 MB of 3,579.6, or 0.22%

almost all of it the two unexplained leading regions in `GravelSubstance002` (a JPEG that no
short-form descriptor names) and `SnowSubstance002`.

## The version-2 prologue is programs too, and the resource residue is characterised

### The prologue

Layout B - version 2 only, 30 files - emits a prologue before the first record. It was measured
earlier at 20.9% covered, using programs reachable from record slots, and recorded as a known
gap of 79%.

Measuring it the way the FX-Map records were measured, accepting a program wherever a 4-aligned
word in the file points at one:

    prologue bytes                    11,440
    covered by referenced programs     9,749    85.2%
    unexplained                        1,691    14.8%

**The prologue is bytecode.** It is the same finding as the FX-Map "blob" - not an undecoded
region, but programs the walker could not reach - and the same correction applies: the earlier
figure measured the walker, not the format. The residue is 1,691 bytes across 30 files, about
fifty-six bytes each, which is the size of the node headers and pointers around them.

### The resource residue, and a test that cannot be made to work

Two files hold something before their first described image: `GravelSubstance002` (459,732
bytes) and `SnowSubstance002` (19,108). Together with slack elsewhere that is the 0.22% the
resource segment does not account for.

What is there:

    GravelSubstance002   a length-prefixed JPEG of 140,553 bytes at the very start,
                         then 319,175 bytes that are not a further JPEG
    SnowSubstance002     19,108 bytes beginning 03 04 04 04, not JPEG

Neither is described by a short-form descriptor, and the obvious candidate mechanism does not
hold: **no long-form bitmap record in the corpus points into a resource segment ahead of the
described images** - 0 of 450 graph-input records.

Asking instead whether anything at all references these regions cannot be made to answer. The
regions sit at low file offsets, so any small u32 anywhere in the file "points" at them; the
value table alone contributes tens of thousands of apparent references. This is the
small-integer artifact that has defeated four separate analyses in this document, and at these
offsets there is no version of the test that discriminates.

**Recorded as: 0.22% of the resource segment is undescribed, in two specimens, one of which
begins with an unreferenced JPEG. Whether anything names them is not determinable from this
corpus by pointer analysis.**

## Two more FX-Map node types, and the limit of chain walking

Probing a node's shape only where the position is already validated - reaching it as a known
node's chain successor - gives the layout without guessing:

    header   shape at +4 +8 +12 +16      reading
    0x18B    P N . 0    83%              [header][program][next]
    0x89     P 0 N .   100%              [header][program][0][next]
    0x1CB    P 0 N .    98%              [header][program][0][next]

    (P = a decodable program, N = a plausible node header, 0 = null)

`0x1CB` has exactly `0x89`'s physical layout. The return-type test separates them anyway:

    0x18B   13,384 programs   end i1   100.0%
    0x89    11,197            end b2   100.0%
    0x1AB       20            end i1   100.0%
    0x1CB      614            end i1   100.0%

**Physical shape does not determine role.** `0x89` is alone in yielding a boolean and is
therefore the conditional; `0x1CB` shares its layout and `0x18B`'s return type. Had the shape
probe been trusted on its own, `0x1CB` would have been recorded as a second conditional.

Four node types are now in the walker with measured shapes. But extending it does not extend
the walk much:

    fxmaps records walked       17,189
    nodes reached               25,215      1.5 per record
    chains ending cleanly          252      1.5%
    chains stopping at an unrecognised header   ~98%, nearly all at a value above 0xFFFF

Ninety-eight percent of chains stop at a word too large to be a header. Two readings fit: the
chain genuinely ends and the word is not a next pointer, or the next-pointer offset is not
constant per header. Nothing in the corpus separates them, because the only material whose
FX-Map composition is known from source is `ie_pcloud`, and its records have four-node chains
that the walker already traverses end to end.

**This is where FX-Map structure stops.** The execution model is understood - a straight-line
program over a shared variable frame, `$number` in, instance position and colour out. Four node
types are identified by shape and return type, one of them by name. The chain topology beyond a
few nodes is not, and it is blocked on the same thing everything else about FX-Maps is blocked
on: a second material whose source composition can be read before the binary.

## Correction: "0 unexplained bytes" was measuring the directory, not understanding

Every audit in this document has reported **0 unexplained bytes of 4.09 GB**. That figure is
much weaker than it reads, and the reason is structural.

`coverage()` marks a whole record extent as accounted for the moment the record is enumerated:

    mark(r.offset, r.end, 5)      # record

The record directory is a sorted partition of the body - established early and re-verified
often - so *every* body byte is inside some record by construction. Marking record extents and
then reporting no unexplained bytes is therefore **circular**: it measures the directory's
completeness, which is a fact about the format, not about the segmenter.

The same measurement with the permissive reference scan disabled gives 100.00% as well, and the
scan is worth 0.00 points. That should have been the tell: a scan that demonstrably recovers
programs nothing else reaches cannot be worth nothing.

### The honest measure

Counting only bytes the segmenter can put a meaning to - the tag, the slots its layout names,
decoded programs, FX-Map tree nodes, and bitmap pixel data:

    record bytes interpreted      92.5%      of 65 MB of record bytes

    blend               98.2%        gradient            43.3%
    warp                96.6%        fxmaps              90.9%
    distance            96.6%        pixelprocessor      90.8%
    transformation      95.5%        fid 5                0.0%
    levels              95.1%        shuffle             93.5%

Ninety-two and a half, not a hundred. The directory does tell us where everything is; it does
not tell us what any of it means, and conflating the two flattered every coverage figure here.

### What the honest measure surfaces

**`gradient` at 43.3%** was invisible under the old metric and is the largest gap after the
unnamed filters. Reading one:

    [1] 40          [3] -> +2984
    [2] 256         [4] -> +4520
    [5..]  u16 triples: (0000, FFFF, 8000) (0101, FFFF, 8000) (0202, FFFF, 8000)
                        (0303, FFFF, 8000) (0404, FF7F, 8000) (0505, ...)

The first component steps by `0x0101` per entry and the others carry values. **A gradient
record embeds its colour ramp** as a table of `u16` triples - a stop position and two
components - which is exactly what a Gradient Map needs and what nothing in the segmenter
models. Word 2 is a count: 4 in 1,696 records, 64 in 664, and 256, 6, 3, 2 elsewhere. For the
64-entry records a 6-byte stride fits the triple reading; the 4-entry records do not fit a
constant stride, so the table format is not uniform and is not yet settled.

**`fid 5` at 0.0%** is correct and expected: those records are almost entirely the embedded
vector geometry described earlier, which is located but not decoded.

`coverage()` keeps its byte classification, which is still useful for locating a resource
segment or a prologue. But **the number to quote for how much of the format is understood is
92.5% of record bytes, not 100% of file bytes.**

## The gradient ramp, and one more false edge

The honest coverage measure put `gradient` at 43.3% interpreted, the largest gap outside the
unnamed filters. Reading three records of different sizes settles it.

    [0] tag / class
    [1] a value that varies
    [2] 4          number of stops
    [3] -> +20     table start
    [4] -> +44     table end, which is where the record's program begins
    [5..] the table

    len  40  count  4  slot3 -> +16   table +16..+40  = 24 = 4 x 6
    len 172  count  4  slot3 -> +20   table +20..+44  = 24 = 4 x 6
    len 412  count 64  slot3 -> +20   table +20..+404 = 384 = 64 x 6

**A gradient record embeds its colour ramp**, and slot 4 does double duty as both the table end
and the program pointer, because the program is emitted immediately after the table.

### Entry width follows the channel count

    channel   class    records   stride
    grey      0x0119     2,856    6   100%
    grey      0x0118     1,849    6   100%
    colour    0x0119       632    8   100%
    grey      0x0019       598    4   100%
    colour    0x0109       122    8   100%
    grey      0x0018        92    4   100%

Exceptionless within each class. The rule is

    stride = 4 + 2*colour + 2*(class bit 8)

giving 4, 6 or 8 bytes - a `u16` stop position followed by one, two or three `u16` values. It
holds for **94.4% of the 17,151 records carrying a ramp pointer**; the residue is almost all
records where the span is not a whole multiple of the count, meaning slot 4 is not the table end
there.

`Record.ramp` reads 88.5% of gradient records: 4,841 with three values per stop, 782 with four,
697 with two.

### Slot 2 was in the edge map and is not an edge

`EDGES[0]` was `[1, 2]`. Slot 2 is the stop count. It passes the "valid backward record index"
test - the values are 4, 64, 256 - and fails the one that discriminates:

    slot 2 read as an edge, resolution agreement   35.5%   (chance)
    blend slot 2, a known real edge                100.0%

**The sixth time the small-integer artifact has put something in a table it does not belong in.**
It was found this time only because the corrected coverage metric made `gradient` look wrong.

    gradient record bytes interpreted   43.3%  ->  91.7%
    edge slots resolved                99.96%  ->  99.98%

## What the file says about layout, which this project spent a long time guessing

A fair objection to everything above: the engine that reads these files does not probe, does not
try alternates, and does not fall back. It decodes deterministically. So the layout of a record
must be **stated in the file**, and every layout heuristic in this document is a substitute for
reading something that is already there.

It is there. Measuring how well each candidate key determines a record's header size - the offset
of the first program it emits, which is where the header ends:

    key                       distinct keys    purity
    filter                              20     61.4%
    filter + class                      84     68.0%
    filter + slot 1                    134     91.2%
    filter + class + slot 1            195     99.0%

**Ninety-nine percent, from 195 combinations.** The layout is determined by three fields that all
sit in the record's first eight bytes:

    word 0 low   tag     filter id, colour bit, resolution nibbles
    word 0 high  class   the layout family
    word 1       the parameter word, which selects the variant within it

No probing is required, and none of the alternates, fallbacks or diversity heuristics in this
document were ever necessary.

### Every layout finding here is a special case of this

Read back, the pattern is unmistakable. Each was found separately, none recognised as the same
mechanism:

    pixelprocessor   slot 1 is the input arity, and the edges and program follow it
    shuffle          two layouts, probed by which program slot validates
    fxmaps           slot 1 bit 12 selects whether slots 3-8 are edges
    blend            slot 1 bits 4 and 8 track a 5- or 6-slot header
    gradient         slot 2 is the ramp stop count; class bit 8 sets the entry width
    bitmap           class is the pixel format

Six filters, six separate investigations, one mechanism: **the record's first two words are a
layout descriptor**, and the parameter word is doing double duty as parameter storage and as the
variant selector. The blend bits 4 and 8 that were recorded as "resolution-mode bits,
unidentified" are, at minimum, layout bits - which is why they predicted header size at 98% and
resisted every attempt to match them to a source parameter.

### What this changes

`ALT_LAYOUTS` probing, the diversity threshold used to derive the edge map, and the
`parameter` union's fallback are all workarounds for not having read the descriptor. A segmenter
built on a `(filter, class, slot 1) -> layout` table would be **deterministic rather than
heuristic**, and would fail loudly on an unknown key instead of silently guessing - which is what
let six false edges into the tables.

The table has to be derived from a corpus, so a key not seen before is still unknown. But that is
a different and much better failure mode than probing: an unrecognised descriptor is a fact about
coverage, where a wrong probe is a fact that looks like a finding.

**Recorded as the single largest structural insight to come out of questioning the method rather
than the data.**

## The layout descriptor, reduced to a mask per filter

Keying layout on the whole of slot 1 gives 26,395 distinct keys, because slot 1 also holds
parameter *values* - `blendingmode` lives in its low nibble. The layout bits are a subset, and a
greedy search finds them: start with all 32 bits and drop any whose removal does not cost
determinism.

    filter            records         mask     keys   purity
    blend              73,898   0x00000230       24    99.9%
    transformation     53,004   0x060000C0       60   100.0%
    directionalwarp    14,215   0x0000001E       43   100.0%
    pixelprocessor     12,012   0x0000000B       26    99.8%
    fid 11              4,905   0x00000004       21   100.0%
    blur                2,797   0x00000000       18   100.0%
    fid 19                674   0x00000000        5   100.0%
    distance              533   0x00000001       12   100.0%
    levels             21,768   0x000003FD      118    98.6%

**`blend`'s mask is `0x230` - bits 4, 5 and 9 - and it excludes bits 0 to 3.** The search was
given no knowledge of what those bits mean. It independently rejected exactly the nibble holding
`blendingmode` and kept exactly the bits that this document had already found predict header
size. Twenty-four keys determine every blend record's layout at 99.9%.

`blur` and `fid 19` need **no** slot-1 bits at all: class alone determines their layout, at 100%.

### Where it does not reduce

    warp        1,405 keys   99.8%
    gradient    2,567        87.9%
    uniform     2,258        99.8%
    shuffle       336        99.8%
    fxmaps         62        84.2%

High purity but no compression - the search kept many bits because those filters store parameter
values in slot 1 that happen to correlate with layout, and a greedy per-bit search cannot tell a
layout bit from a parameter bit that co-varies with one. `gradient` is the clearest case: its
slot 2 is a stop count, so record shape tracks a value the mask cannot exclude.

Overall: **98.8% determinism over 209,640 records**, with the compression concentrated in the
filters that matter most by volume.

### What this is worth

For nine of fourteen measured filters the layout is a lookup on two small fields. A segmenter
built this way would not probe, and would report an unknown `(filter, class, masked slot 1)` as
a gap rather than guessing a layout - the failure mode that admitted six false edges into these
tables.

The masks are derived from this corpus and a key not seen here remains unknown. That limit is
real, and it is the same one that applies to the filter table and the opcode catalogue.

## A table-driven segmenter: faster, and it corrects the tables it replaces

`tools/derive_layouts.py` derives `(filter, class, masked slot 1) -> (edge slots, parameter
slot)` from a corpus; `sbsasm.py` looks it up instead of probing. 842 keys cover 848,674 of
895,674 records.

### Speed

Over 120 files and 161,171 records:

    table lookup, no probe and no scan     0.23 s     196,388 programs
    probing the layout (Record.parameter)  0.49 s     153,017
    whole-file reference scan              5.51 s     277,876

**Twenty-four times faster than the scan and twice as fast as probing, while finding 28% more
programs than probing.** Verification: 99.96% of the table's parameter slots decode as a valid
program, 100% of those are a subset of what the scan finds - so the table adds no false
positives - and 99.7% of its edge slots pass resolution agreement.

### It corrects the hand-written tables

The derived table lists 267,000 fewer edges than the hand-written `EDGES`. Checking what it
dropped:

    dropped              records   resolution agreement
    transformation  s2    37,236          34.5%
    shuffle         s2       251          10.4%
    shuffle         s3       111          23.4%

    kept, for comparison
    blend           s2    55,405         100.0%
    levels          s2    16,210          99.7%
    transformation  s2     5,463          99.9%

**`transformation` slot 2 is a real edge in some layouts and not in others** - 99.9% agreement
under one key, 34.5% under another. The hand table said "always an edge" and was wrong for
37,236 records. That is the seventh false edge in this document, and the first found without
anyone looking for it: the table is per-key, so it can express what a global table cannot.

### Effect

    main parameter resolved   95.0%  ->  95.5%
    edge slots resolved      99.96%  ->  99.97%   on 267,000 fewer, cleaner edges

The audit still takes ~51s because `coverage()` retains the whole-file scan; the walk itself no
longer needs it, and that is the obvious next saving.

### The general point

Every heuristic this replaces - probing alternates, diversity thresholds, global edge tables -
existed because the descriptor was not being read. Reading it is faster *and* more accurate, and
the accuracy is not a coincidence: a heuristic that guesses per filter cannot represent a layout
that varies per record, so it must be wrong somewhere, and it was wrong in seven places.

## Mining the layout table: the transformation matrix

The layout table classifies each slot as an edge or the parameter. The slots it classifies as
**neither** are the format's remaining unexplained fields, and listing them by volume is a
systematic way to find what is left - something no amount of staring at records produced.

Restricted to header slots, before the first inline program:

    filter            slot    records   holds
    transformation      2      44,241   other 96%
    fxmaps              2      11,091   other 100%     (the tree root, known)
    levels              5      10,665   float 82%
    transformation      5       9,745   zero 81%, float 17%
    transformation      6       9,740   zero 87%, float 13%
    transformation      4       7,178   float 88%
    transformation      7       7,365   float 82%

Four float slots in a row on `transformation`, mostly zero in the middle two.

### Slots 4 to 7 are `matrix22`

    2.0000  0.0000  0.0000  2.0000      uniform scale
   -1.0000  0.0000  0.0000 -1.0000      180 degrees
    0.0000 -1.0000  1.0000  0.0000      90 degrees
    1.4014  0.0000  0.0000  1.4014
    2.0000  0.0000  0.0000  1.0000      non-uniform scale

Off-diagonals are zero in 94% and 76% of records, which is what a corpus of scales and flips
looks like. Verified against the sources: **66 of 72 declared `matrix22` values appear verbatim
at slots 4-7, across 23 permitted files - 91.7%**, the misses being nodes the cooker eliminated.

A determinant test does the filtering. A transform cannot be singular, so a record whose slots
4-7 are something else - a different layout - is rejected by `|det| < 1e-9`. Applying it drops
the readable share from 58.8% to 14.3% while **keeping all 66 source matches**, which is the
signature of a filter removing noise rather than signal: the rejected values included
`(0, 0, 0.5, -0.25)`, which collapses an image to a line.

`Record.matrix` returns it.

### What this says about method

`transformation` slots 4-7 have been present in every record this project has read since the
beginning. They were never examined because nothing pointed at them: the edge map did not claim
them, the parameter union did not claim them, and the coverage metric - marking whole record
extents - reported them as accounted for.

**The layout table found them by exclusion.** Once every slot has to be classified as edge,
parameter, or neither, the "neither" list is short, ordered by volume, and reads as a work
queue. `levels` slot 5 at 82% float is the next entry on it.

## The parameter block is a bitfield, not a fixed layout

`levels` slot 5 was the next entry on that queue. Reading it settled the slot, then
immediately generalised past it: **slot 1 states which parameters the record carries, and
the ones it carries are packed into consecutive slots.** There is no fixed position for a
named parameter, which is why every earlier attempt to find one produced a different answer
depending on how the records were grouped.

### Slot 5 is not what the size-stratified reading said

The largest `levels` layout key - class 25, layout bits `0x140`, 36,818 records - holds a
float at slot 4 in 99.9% of records and at slot 5 in 80.3%, with the other 19.7% exactly
zero. The two slots are complementary:

    slot 4 : 1(21.4%)  0.25(13.0%)  0.375(5.8%)  0.4375(5.8%)  0.46875(5.8%) ...
    slot 5 : 0(19.7%)  0.75(13.0%)  0.625(5.8%)  0.5625(5.8%)  0.53125(5.8%) ...

They sum to exactly 1.0 all the way down a binary-search sequence converging on 0.5. An
earlier section read the modal pair `(1, 0)` as `levelinhigh`/`levelinlow` on the strength of
those being their documented defaults. **That was wrong**, and the values alone cannot settle
it: `(1, 0)` is either an identity levels or a full inversion depending on which slot is which,
and both are things a material does constantly.

### Containment settles it, but only on distinctive values

Pooled containment against the permitted paired sources says nothing useful:

    levelinhigh   declared 55   slot 4: 47%  slot 5: 45%  absent: 18%
    levelinlow    declared 48   slot 4: 79%  slot 5: 27%  slot 6: 27%

because `0.0`, `1.0` and `0.5` are the defaults *of these very parameters* and occur in every
slot of every filter. Restricting to values an artist typed - not 0, 1 or 0.5, and not any
`k/2^n` a slider can land on - and requiring the value to be unambiguous on both sides (declared
for exactly one parameter in that file, found at exactly one slot) leaves 96 usable values:

    levelinlow     29   slot 4: 29 (100%)
    levelinhigh    31   slot 4: 16 (52%)   slot 5: 14 (45%)
    levelinmid     17   slot 5: 6 (35%)    slot 6: 6 (35%)   slot 4: 5 (29%)

`levelinlow` is pinned to slot 4 in 29 of 29. Everything else splits. A parameter that has one
position and a parameter that has three cannot both be true of a fixed layout - which is the
clue that the layout is not fixed.

### The layout word counts the parameters

Per layout key, the popcount of the masked slot-1 word equals the number of float slots
following the header:

    cls     bits  popcount   records   float slots
     25    0x140         2     36818             2
     25      0x5         2      9184             2
     25    0x105         3      5567             3
     25      0x0         0      4635             0
     25      0x1         1      4331             1
     25     0x155        5       517             5

Over the 52 `levels` keys with 100+ records this holds for **44 keys and 96.5% of records**.
The header ends one slot earlier when the class word's bit 0 is clear - that bit is what says
whether slot 3 holds the parameter program or the first parameter, and using it lifts the
agreement from 85.5% to 96.5%.

Fitting which bits count gives mask **`0x155`** at 97.5%: bits 0, 2, 4, 6 and 8, **every even
bit, and exactly five bits for `levels`'s exactly five parameters**. The odd bits are something
else; keys carrying bits 3, 5 or 9 are where the count still fails.

### Which bit names which parameter

If the presence bits are packed in order, then for a record holding a value the source
declares, the parameter's index in the block is `slot - start`, and the bit naming it is the
`(slot - start)`-th set bit. That maps names to bits without assuming an order:

| bit | parameter | agreement |
|---|---|---|
| 0 | `levelinlow` | 92% (37) |
| 2 | `levelinhigh` | 97% (35) |
| 4 | `levelinmid` | 100% (19) |
| 6 | `leveloutlow` | 100% (11) |
| 8 | `levelouthigh` | 100% (9) |

Decoding every `levels` record this way and checking each read against a declared value gets
**107 of 111 correct - 96.4%**. `Record.parameters` returns it:

    cls=25 bits=0x15   levelinlow=0.68  levelinhigh=0.849338  levelinmid=0.241618
    cls=25 bits=0x140  leveloutlow=1    levelouthigh=0
    cls=25 bits=0x14   levelinhigh=0.971222  levelinmid=0.52078

Note the order is in-low, in-high, in-mid, out-low, out-high - neither the order a `.sbs`
declares them in nor the order they are applied in.

So the largest `levels` key is `leveloutlow` and `levelouthigh`, not the in-levels, and its
modal `(1, 0)` is `leveloutlow=1, levelouthigh=0` - **the standard invert idiom**. That is why
it is the single commonest configuration in the corpus, and it is a reading that makes sense of
the value distribution instead of merely fitting it.

### The bug that hid all of this: zero is a value

`derive_layouts.py` classified a slot as a parameter when it held a program or a float in over
90% of records, and its float test was `if v and math.isfinite(f32) and ...`. The leading `v`
excludes zero.

Zero is not padding. It is the default of `levelinlow`, of every offset, and of the `matrix22`
off-diagonals. A slot holding a legitimate `0.0` in a fifth of its records scores 80% on that
test and drops out of the table - which is exactly what happened to `levelouthigh` across 36,818
records, and it is why slot 5 appeared on the "neither" queue at all.

Counting zero as a float, while requiring it to be the *minority* reading so that genuine
padding is not claimed, changes the table substantially:

    layout keys                                   842  ->  1031   (+189)
    parameter-slot readings over shared keys  1,861,038 -> 2,368,466   (+27.3%)
    keys whose parameter list changed                        50

The corrections are not confined to `levels`. `uniform` gains a four-slot run - its
`outputcolor` - and `transformation` gains slots the matrix work had to find by hand:

    15,25,320        [3, 4]          -> [3, 4, 5]          n=36818
    2,793,64         [3]             -> [3, 4, 7]          n=21847
    4,921,532        [3, 4, 6, 7, 8] -> [3, 4, 5, 6, 7, 8] n=11730
    6,280,0          [1]             -> [1, 2, 3, 4]       n=2884

The validator still passes 436/436.

### What this changes about method

Twice now the obstacle has been a predicate that was too strict rather than too permissive.
The recurring failure in this project has been the opposite - a small integer passing "is a
valid backward record index" by construction, seven times over - so the reflex was to tighten.
Here tightening was the error: `if v and ...` looks like ordinary defensive code and silently
deleted a fifth of a parameter slot's evidence.

The general lesson is narrower than "don't exclude zero". It is that **a test's exclusions need
the same justification as its inclusions.** `1e-6 <= abs(f32) <= 1e6` was argued for in the
notes; the `v and` guarding it was never argued for at all, and it was the part that cost
507,428 readings.

It also means the "neither" queue is not a list of unknown fields. Some of its entries are
fields the classifier already understood and threw away.

## Where the presence bits live differs by filter

The `levels` result raised an obvious question: is slot 1 a parameter-presence bitfield
for every filter? Partly. The answer is per-filter, and finding that out required a
control that earlier work in this notebook did not use.

### The control matters more than the fit

Fitting a mask so that `popcount(word & M)` equals a filter's float-parameter count is a
search with many degrees of freedom, and a high score proves nothing on its own. The
control is the **best constant predictor** - "this filter always has *k* parameters".
A mask that cannot beat that has explained nothing, however well it scores:

| filter | records | constant | slot 1 | class word | verdict |
|---|---|---|---|---|---|
| `blend` | 372,482 | 55.5% | **97.4%** | 55.5% | slot 1, `0x10` |
| `transformation` | 282,523 | 56.9% | 59.7% | 58.8% | **unexplained** |
| `levels` | 99,056 | 52.8% | **90.5%** | 53.6% | slot 1, `0x1dd` |
| `directionalwarp` | 69,998 | 89.6% | **99.3%** | 88.8% | slot 1, `0x1a` |
| `pixelprocessor` | 65,049 | 59.4% | **69.6%** | 59.4% | slot 1, `0x1` |
| `fxmaps` | 48,236 | 46.5% | **80.9%** | 29.4% | slot 1, `0x15` |
| filter 11 | 17,772 | 72.4% | **95.9%** | 75.1% | slot 1, `0x7` |
| `blur` | 18,297 | 58.8% | 30.6% | **61.2%** | class bit 12 |
| `sharpen` | 1,418 | 90.0% | 53.8% | **100%** | class bit 12 |
| `hsl` | 565 | 81.2% | 81.2% | **100%** | class bit 12 |
| `warp` | 2,373 | **100%** | 21.1% | 100% | constant: always 1 |
| `uniform` | 3,704 | **88.2%** | 10.6% | 11.8% | constant |
| `normal` | 1,476 | **100%** | 92.2% | 100% | constant: always 1 |
| `distance` | 2,333 | **100%** | 100% | 100% | constant: always 1 |

Three groups. Six filters carry the count in slot 1. Three carry it in **class-word bit
12** - the same bit for all three, which is not something a per-filter fit was told to
find. Four have a fixed parameter count and need no bits at all.

`transformation` is the honest failure: 59.7% against a 56.9% baseline is nothing, over
the second-largest filter in the corpus. Its `matrix22` is read positionally and that
still works, but what selects between its layouts is not in either word.

### `warp` shows the question was mis-stated

`warp`'s slot 1 is **zero in 1,786 of its 2,373 records** while those records still carry
parameters. No mask over slot 1 can count them. Its class word tracks the count exactly:
`cls 8985` has one float parameter, `11033` two, `10009` three. Whatever slot 1 is for
`warp`, it is not this.

That also killed a plausible-looking diagnosis. When `warp` scored *below* its constant
baseline - impossible for a correct optimiser - the obvious cause was that the search
only considered bits that vary, making "a parameter every record has" unreachable. That
was a real bug and it was fixed. It was **not** the cause: `warp` has no always-set bit
in slot 1 either, and the output was byte-identical after the fix. Two defects in the
same place, and fixing the visible one changed nothing.

### `LAYOUT_MASK` cannot be reused for this

The first attempt fitted within `LAYOUT_MASK`, and `blur`, `normal` and filter 11 scored
near zero because their entry is `0x0` or a single bit - there was nothing to fit. That
mask was derived to be the *minimal* set of bits that determines a record's layout, so any
bit co-varying with another was dropped as redundant. Minimal-for-discrimination and
complete-for-decoding are different objectives over the same word, and a table built for
one is misleading when read for the other.

### `blend` bit 4, checked out of sample

A fitted mask needs an independent test. For `blend` the fit is a single bit, so the
prediction is sharp: a record carrying a declared `opacitymult` should have slot-1 bit 4
set. Over the permitted paired sources, **236 of 236 do - 100%**, with no counterexample
among bit-4-clear records. The value lands at the slot the layout table names, and
decoding gets **177 of 177 right**.

Only 26.9% of `blend` records decode a parameter at all, which is the rule working:
`opacitymult` defaults to 1 and an unset parameter is simply absent, not stored as its
default. That is the same economy as the tagged parameter union.

### A parsing bug worth recording, because it inverted a result

`blend` first scored **13.8%**, with every disagreement of the form "decoded
`opacitymult` matched a declared `blendingmode`". The defect was in the *source* reader,
not the decoder:

    <parameter><name v="([a-z0-9]+)"/>.*?<constantValueFloat(\d) v="([^"]+)"/>

With `re.S` the `.*?` crosses `</parameter>` boundaries, so `blendingmode` - an `Int32`
parameter with no float of its own - was paired with the float belonging to the parameter
after it. It produced 112 false attributions and made a correct decoder look broken.
Parsing each `<parameter>` element separately took the score from 13.8% to **100%**.

`levels` was re-checked against the fixed reader and is **unchanged**, because `levels`
declares only float parameters and there was no `Int32` in between to steal a value from.
The bug was invisible until a filter with a mixed parameter list came along.

This is the too-permissive predicate again, in a place none of the earlier instances of it
would have suggested looking: not in a test over binary data, but in the regex reading the
ground truth. **The ground truth needs auditing to the same standard as the format.** A
lenient parser on the source side manufactures disagreements and would have been read as
evidence against a correct hypothesis.

## Correction: the output table exists, and it was never hidden

Reading one small file completely - every byte claimed by name, overlaps and gaps
reported rather than summed - found two things that no amount of corpus-wide statistics
had turned up. The specimen was chosen for checkability: `SubstanceDesigner__color`,
3,812 bytes, 17 records, **zero `compInstance` nodes**, so source-to-binary
correspondence survives intact.

### An explicit byte map, not a coverage total

`coverage()` reports one `unexplained` number, and for this file it reported **zero**.
That is not the same as understanding the file. Claiming each byte by name instead:

    0x0000 .. 0x0038      56  file header
    0x0038 .. 0x007c      68  record directory
    0x007c .. 0x0094      24  *** UNCLAIMED ***
    0x0094 .. 0x00a8      20  record 0 (bitmap)
    ...
    0x0d54 .. 0x0ed4     384  value table
    0x0ed4 .. 0x0ee4      16  footer

A total that sums correctly can hide both an unclaimed region and overlapping claims.
Here it hid one of each.

### The 24 unclaimed bytes are the output table

Three 8-byte entries, first words identical, second words **1, 16 and 8** - which are
exactly the three `pixelprocessor` records, and the source declares exactly three
`pixelprocessor` nodes. Measured across the corpus:

| prediction | result |
|---|---|
| every layout-A file has the region | **591 / 591** |
| its size is a multiple of 8 | **591 / 591** |
| entry count equals `n_out` | **591 / 591** |
| second word is a valid record index | **3,249 / 3,249** |
| distinct outputs name distinct records | 3,242 / 3,249 (99.8%) |

Counting is not enough - a table of the right length could hold anything - so the
consequence test is the channel type. The first word carries the manifest's `format`
attribute in its upper bits:

    format == (w0 & 0xFFFF) >> 4

exact on every distinct value in the corpus: `0x1c0`->28, `0x100`->16, `0xc0`->12,
`0x400`->64, `0x4c0`->76, `0x5c0`->92, `0x500`->80. Bit 2 of that format is the grayscale
flag, and it agrees with the colour bit of the record the entry names in **3,249 of
3,249**. A grayscale output cannot be produced by a colour record, so this is a test the
hypothesis could have failed.

Entries whose high half is 2 (48 of 3,249) are a different kind; `Assembly.outputs()`
returns them with format `None` rather than guessing.

**This reverses a documented conclusion.** The notes above record output-to-record
attribution as structurally absent, after five approaches failed and 0 of 183,160 uid
references resolved, and propose a discriminative renderer scored against shipped PNGs as
the only way forward. That was wrong. The attribution is stated outright, one entry per
output, in a region that `coverage()` labelled "resources" - a label that no file with an
empty resource segment ever contradicted, because the region was never read.

The five failed approaches all searched *within* the structures already known: records,
uid tables, bridges. None asked what the bytes between the directory and the first record
were. **The region was not hidden; it was mislabelled, and the label was never tested.**

### The record extent is header plus one or two programs

The byte map also showed every record overlapping a program at its tail, always 8 bytes
before the record's declared end - which looks exactly like a fixed-offset artifact
manufacturing false programs. It is not:

| `record_end - program_end` | share |
|---|---|
| 0 bytes, flush | 57.0% |
| 2 bytes, 4-byte alignment padding | 32.9% |
| more than padding | 10.1% |

and of that last 10.1%, **99.8% is a second program**, itself flush with the record end.
So a record is `[header][program]` or `[header][program][program]`, and the directory
extent covers all of it. The constant 8 in this specimen was a property of the specimen -
every one of its records carries a minimum-size program - not of the format.

Worth stating plainly because the suspicion was the right one to have: a constant
distance between a discovered structure and a boundary is normally the signature of a
validator accepting whatever sits at a fixed offset. Here the distance is the program's
own length, and it varies from 8 bytes to 468 across the corpus.

## Two programs in a record are pointed at, not delimited

The natural question about `[header][program][program]` is what separates the two. The
answer is that nothing does, and nothing needs to.

**Each program is named by its own slot.** Over 36,614 records carrying a second program,
the second program's start address appears in a record slot - as `offset - 52`, the
universal skew - in **36,614 of 36,614, and both programs are named in all of them**:

    slot holding the second program pointer: {5: 21683, 4: 10887, 3: 3933, 7: 109, 8: 2}

So a reader never scans for the second program and never has to decide whether what
follows the first is code or something else. It follows a pointer, exactly as it does for
the first.

**And each program is self-delimiting anyway.** The leading `u16` instruction count plus
the per-opcode lengths take a decoder to the program's exact end. The two mechanisms are
independent: the pointer says where a program starts, the count says where it stops.
Contiguity in the record tail is a layout convenience, not a structure a reader relies on.

The filters involved are the ones that take two scalar parameters:

    directionalwarp 19,590   warp 8,303   blur 3,497   fid11 3,435
    distance 720   sharpen 435   normal 383   fid8 135

`directionalwarp` has both an intensity and an angle, and it is the largest group by a
wide margin.

### A reframe that failed, recorded because it was plausible

This suggested a tidier model: a parameter slot holds *either* a program pointer or a
baked float - the tagged union - so counting only the float slots undercounts every
record whose parameter is dynamic, and the presence bits should count both.

Measured, it is worse everywhere. `levels` falls from 90.5% to 12.5%, `blend` from 97.4%
to 66.5%, and no filter improves. The earlier model - presence bits count the *baked*
parameters, program-valued parameters being named separately - is the one that survives,
and it is the one with independent confirmation against the sources (levels 96.4%, blend
177 of 177).

The direct test says why. For `blend`, split by slot-1 bit 4:

    bit4=0 : 63,882 records - none 5,795, program 58,087, float 0
    bit4=1 : 58,147 records - float 7,612, program 50,346, none 188

**No bit-4-clear record carries a baked float, in 63,882 records.** All 7,612 baked
floats have the bit set. So the bit says the parameter is present *as a record field*;
when it is clear, the opacity is either the default or computed by the program. Counting
program slots toward the same total merges two different things and destroys the signal.

Both models predict the 236-of-236 containment result equally well, which is why the
containment test alone could not separate them. The record-level split could.

## The segmenter, brought up to these results

Four changes, each of which fixes something that was silently wrong rather than merely
absent.

### 1. The output table, in both layouts

The table sits **immediately after the record directory**, and that one rule covers both
file layouts. Layout A puts the body after the directory, so the table falls between the
directory and the first record; layout B puts the body first, so the same table falls
between the directory and the value table. It looked like a layout-A-only region only
because the two positions were never recognised as the same place.

Layout B, measured independently of layout A:

    layout B files                    50
    region size == 8 * n_out       50 / 50   (100%)
    second word a valid record idx 250 / 250 (100%)

`Assembly.outputs()` now reads both. Its format-to-colour agreement is 100% on layout A
and 94.8% on layout B, the shortfall being entirely `format 0`, which is ambiguous: 13
grayscale against 87 colour. `format 0` should not be trusted for the channel type.

### 2. The resource segment ends at the directory

`resource_end` was `min(record_offsets)` - the first record - so `coverage()` painted
everything from 0x38 to the first record as "resource segment", overwriting the directory
label set two lines earlier and burying the output table with it. For the specimen above
that was 68 directory bytes plus 24 output-table bytes: **exactly the 92 bytes it
reported as resources**.

This is the identical defect fixed in `sbsarx` earlier, found there by a segment report
that did not tile and here by a byte map that did not add up. The same wrong boundary,
written twice, caught twice by different checks - and in neither case by the coverage
total, which was zero throughout.

### 3. Layout B's record body ends at the directory

`body_hi` was `table_start` in both layouts. In layout B the body *precedes* the
directory, so the last record's extent ran straight through the directory and the output
table behind it, and `coverage()` counted those bytes as "records" - explained, by the
wrong thing. Layout B now reports a directory of `4 * dir_count` bytes and an output
table of `8 * n_out`, where it previously reported zero of each.

### 4. `Record.programs` returns every program, not the first

It read only the main parameter slot, so it missed 36,614 second programs. It now reads
each slot the layout table names:

    programs per record : {0: 42699, 1: 197748, 2: 79679, 3: 29545, 4: 10873, 5: 142}

and the distribution matches what the filters are:

    directionalwarp   mostly 2    intensity and angle
    warp              1 or 2
    pixelprocessor    mostly 3    one per channel
    fxmaps            often 4

Nothing is scanned. Each program is found through a slot, never by decoding the previous
one to its end and assuming what follows is code - the self-delimiting instruction count
is how a decoder stops, not how a reader finds the next program.

## The 0.04% of unresolved edges was three bugs, not noise

"Edge slots resolved 99.96%" reads like rounding error. It was not: 505 unresolved slots
that clustered hard enough to name three separate causes. A residue concentrated on one
filter, one key or one value is a wrong rule; only a residue spread evenly is noise.

The first clue was in the raw values. `1065353216` is `0x3F800000` - **float 1.0** - and
it appeared 70 times in slots the table called edges. `1048576000` is `0.25`. And 239 of
the 505 had no value at all, because the named slot lay past the end of the record.

### Cause 1: edge slots claimed from records that do not have them

`derive_layouts.py` computed a slot's edge rate over the records long enough to contain
it, and ignored the rest. Key `(7, 8985, 768)` has 37 records; **36 are seven words long**,
so slot 7 exists in exactly one of them, is an edge there, and scored 1/1 = 100%.

Counting absence as evidence - a slot missing from more than 5% of a key's records is not
part of that key's layout - corrected seven keys, each dropping precisely the phantom
slot:

    12,25,10      [1, 2, 3, 10, 11] -> [1, 2, 3]
    7,8985,896    [1, 2, 7]         -> [1, 2]
    3,281,4960    [1, 9]            -> [1]

That alone took 505 to 258.

### Cause 2: the layout descriptor does not fully determine every key

For key `(7, 11033, 0)`, slot 3 is an edge in 95.7% of records and a **program pointer**
in 3.3%. For the `shuffle` keys `(3, 280, *)`, slots 2 and 3 hold floats - 1.0, 0.25,
0.30, 0.59 - in six-word records. These are not unresolved edges; they are correct
readings of a different kind, in records the key groups together but the format does not.

Because a decodable program, a plausible float and a small backward index are disjoint
readings - established for the parameter union and unchanged here - a per-record check is
a positive identification rather than a fallback. `Record.edges` now declines to claim an
edge in those records instead of reporting `None`.

This is deliberately narrow, and the narrowness is the point: a forward index, or one past
the end of the record table, is **still** reported as unresolved. Absorbing those into the
same rule would have taken the number to zero and hidden the one thing left worth looking
at.

258 to 17.

### Cause 3: -1 is a 'no input' sentinel

Two records carried `0xFFFFFFFF` in an edge slot. That is -1, and it means no input, the
same as 0 - it is not a record index at all.

### What is left, and it is worth keeping visible

**15 edges in 1,235,193 (0.0012%)**, every one a forward or self reference:

    directionalwarp  slot 1 = 10   at records 2, 4, 6, 8, 10   WoodSubstance011
    directionalwarp  slot 1 = 10   at records 2, 4, 6, 8, 10   WoodFloorSubstance008
    gradient         slot 2 = 64   at record 62                Marble_Tiles_01
    gradient         slot 2 = 64   at record 62                MarbleGenerator01
    fxmaps           slot 7 = 9    at record 9                 stylized_rocks_magma
    blend            slot 1 = 275  at record 87                NightSkyHDRI

**These repeat identically across unrelated files**, which rules out corruption: the same
filter, the same slot, the same value, at the same record indices, in two files that share
no author. Records 2 through 10 of a `directionalwarp` group all name record 10, including
record 10 itself.

So the backward-reference rule - which 921,654 corpus edges established and which
overturned a 12-of-13 paired-file result - holds at 99.9988% and has a real, reproducible
exception. The audit now prints `resolved 100.00%`, and that is a rounded figure, not a
zero.

## Resolution agreement was rejecting every resizing filter's input edge

Chasing the next residue - "main parameter resolved 95.5%" - led somewhere else entirely,
and to the largest single correction in this notebook.

### The clue was a key with an empty layout

The unresolved parameters clustered on a few keys whose layout table entry was empty. Two
of them turned out to be correct: `blend (1,24,0)` is 24,143 records of exactly four
words - `[tag][flags][edge][edge]` - a blend with two inputs and no parameters, so "no
parameter" is the right answer rather than a failure.

But `transformation (2,792,0)` is 16,484 three-word records with **no edges and no
parameters**, which cannot be right: a transformation with no input computes nothing.

Its slot 2 is a valid backward record index in **16,471 of 16,484 - 99.92%**. It is
plainly the input edge. The role census had scored it 17%.

### Why the test was blind to it

The edge test requires the target to share the record's resolution. That rule is the
discriminator this notebook adopted after the shared-reference error, and it was right to
adopt - it is what separates real edges from small integers. But it assumes an edge
**preserves** resolution, and that is false for exactly the filters that resize.

Of all backward references, the share agreeing on resolution:

    warp             99.1%        transformation   39.5%
    shuffle          95.5%        pixelprocessor   54.5%
    blur             87.3%        fxmaps           52.7%
    directionalwarp  86.0%        fid19            52.6%

The filters at the bottom are the resizing ones. The test was strongest precisely where
it was wrong.

### Reachability from the output table settles it

"Is a backward index" is the too-permissive predicate that has caught this project seven
times, so a distributional argument is not enough. The output table now makes an
independent test possible for the first time: **every record should be reachable by
walking inputs backward from an output**, since a record nothing reaches computes an image
nothing uses, and the cooker eliminates dead code. Reachability does not depend on how the
edges were found.

    edge map                          records reachable from outputs
    before                                 34.03%   (per-file median 50.0%)
    crediting transformation slot 2        78.15%   (median 88.9%)
    after the full rule below              94.12%   (median 97.6%)

Files below 50% reachable fell from 125 to 5. A spurious edge does not do this; it adds
links that connect nothing in particular.

### The rule, with a calibrated guard

A slot is an edge if it is almost always a backward reference **and** its targets are
diverse - a packed field or a count repeats a handful of values, while an edge names a
different record nearly every time.

The threshold is measured, not guessed. Over slots that are almost always backward
references:

    slot-1 packed parameter words   max diversity 0.025
    slots already known to be edges 5th percentile 0.109

There is a clean gap. **0.05 sits in it, keeping 96.1% of known edges and admitting 0% of
packed parameter words.** The first attempt used 0.25, which admitted no packed words
either but discarded 12.7% of real edges, and left 73,670 transformation records still
edgeless.

    edge readings   1,235,193 -> 1,557,521   (+322,328, +26%)
    unresolved              15 -> 36         (0.0023%)
    86 layout keys gained an edge

Unresolved rose from 15 to 36 because the new edges bring their own small residue; that is
the honest cost and it is still under three thousandths of one percent.

### What this says about the discriminator

Resolution agreement is not wrong - it remains the reason the shared-reference error was
caught, and the reason 87.17% beat 79.97% when the backward-index convention was settled.
It is **conditionally** valid: sound for the filters that preserve resolution, and
systematically blind for the ones that do not.

The notes already contained the list of which filters resize, in a table about output size
inheritance, and the same fact was sitting in a different section being used for a
different purpose. Nothing new had to be discovered to see this - only connected.

## Chasing the unreachable records: one null, one conflation, one arity

With reachability from the output table available as a test, the 5.88% of records it could
not reach became the next residue. Three findings, one of which is a hypothesis killed by
its own control.

### The clumps are stranded, not dead

Of the unreachable records, **91.1% are named by another unreachable record**. Genuine
dead code is scattered; whole connected clumps hanging off unnamed roots is the signature
of a missing link above them. Only 3,085 of 34,651 were named by nobody.

### A hypothesis its control refuted

The obvious next step: if a stranded root's index appears in some record's header slot
that the table does not call an edge, that slot is the missing link. It appeared to work -
**74.4% of stranded roots had their index in a header slot**.

The control says otherwise. Substituting an arbitrary record index for the real one and
asking the same question:

    stranded roots, index found in a header slot   67.7%
    an arbitrary index instead                     95.6%

**The control scores higher than the hypothesis.** Small integers are so common in these
headers that "the index appears somewhere" is worse than uninformative. The 74.4% was
nothing, and the scatter across many unrelated (filter, slot) pairs - several of them slots
already identified as `matrix22` and the level points - should have been the giveaway
before the control was run.

### Edge value 0 is record 0, not 'no input'

Reading the smallest failing files completely settled it. `GrayscaleConvert` has two
records: a `bitmap` at index 0 and a `pixelprocessor` at index 1 whose input slot holds
**0**. Its only possible input is record 0.

Two rules in these notes contradicted each other. The corpus settled **0-based** backward
indices (87.17% resolution agreement against 79.97% for 1-based), which makes 0 a reference
to record 0; elsewhere 0 was read as 'no input'. Both cannot hold. The genuine absent-input
marker is `0xFFFFFFFF`, found earlier while clearing the edge residue - a separate value
that had been folded into the same meaning.

Only **850 of 843,900 edge slots (0.10%)** hold 0, so almost nothing turns on it in
aggregate. It is decisive for a small graph, where record 0 is the generator everything
descends from: the per-file median of reachable records rises from 97.6% to **99.8%** while
the corpus total barely moves. The median is the statistic that matters here, and the total
would have hidden this entirely.

### `pixelprocessor` states its own arity

The same two-record files showed slot 1 holding the input count, with the inputs following
in slots 2 onward. `LGML_hsl_adjuster` record 2 has slot 1 = 2 and slots 2, 3 holding
records 1 and 0; the table claimed only one of them.

    slot 1 in 1..8, and every slot 2..2+n-1 a valid backward index
        41,350 of 41,453 records   99.8%

The derived table could only see slots populated often enough to pass a threshold, and a
filter whose arity varies per record defeats that by construction. Reading the count
directly recovers the rest, and slot 1 = 0 identifies the input-free generators - 1,200
records that are procedural sources, not records with a missing edge.

    records reachable from the output table
      start of this pass                 94.12%   (median 97.6%, 5 files below 50%)
      0 credited as record 0             94.15%   (median 99.8%)
      pixelprocessor arity               98.37%   (median 99.9%, 3 files below 50%)

Against 34.03% before the resizing-filter correction. Edge readings are now 1,559,361 with
36 unresolved.

## The FX-Map residue: a bad metric, two dead hypotheses, and a real gap

### Correction: the tree walk was never failing

This notebook has recorded that "98% of chains stop at an unrecognised header", and a
fresh measurement said 1.2% of walks ran to the end. **Both were artifacts of the metric.**
It used a `while/else`, which fires only when the loop condition fails and never when the
walk stops on a proper terminator - so a chain that ended correctly was counted as a
failure.

Measured properly, by scanning each record for the four known node headers and asking how
many the pointer walk visits:

    known node headers present in fxmaps records   43,456
    reached by the walk                            41,603   (95.7%)

The chain model works. What the walk stops *on* is simply whatever follows the last node,
and 100% of those stop positions are not programs - they are the record's other data.

### +52 is confirmed, not the misunderstanding

The obvious unifying explanation for several residuals at once was a wrong pointer base.
Varying the skew on FX chain steps and counting how often the target is one of the four
known headers - a strict target, since only four values qualify:

    skew   0    4    8   16   32   48   52   56   64
    hit  0.0% 0.2% 0.0% 0.1% 0.8% 0.0% 95.5% 0.0% 0.0%

+52 it is, with nothing else close.

### Two hypotheses, both killed by their own controls

**The conditional's second branch.** `0x89` is the last good node before a stop in 13,658
of 18,524 cases - 74% - and its shape is `[header][program][0][next]`, with a word at +8
assumed to be zero. A conditional has two branches, so +8 looked like the other one. It is
**zero in 18,331 of 18,358 nodes (99.9%)**. The recorded shape was right.

**Inferring unknown node sizes by probing.** For a node reached legitimately as a known
node's successor, try each candidate offset for its `next` pointer and see which lands on a
plausible node. It looked strong - 81.6% of unknown nodes had some offset that worked,
against a 35.8% null.

But that plausibility test accepted any header whose low nibble was 8, 9 or B: 3 of 16
values, six times over. Tightening it to the property all four known shapes share - a valid
program pointer at +4, which a program validator must accept - the result inverts:

    strict probe at a genuine unknown node   27.0%
    strict probe at an arbitrary word        29.9%

**The control beats the hypothesis.** The unknown headers are not program-carrying nodes
of the known kind, and their sizes cannot be inferred this way. That is a useful negative:
it rules out the whole family rather than leaving it open.

### The gap, stated precisely

**9,422 of 27,978 fxmaps records (34%) contain no known node header anywhere.** Their root
pointers lead to headers like `0x20008`, `0x248`, `0x8000848` that are not nodes of any
known shape.

Bit 12 of the parameter word does not explain them - it selects between two fxmaps record
layouts, but 16,404 bit-12-clear records do carry known nodes against 9,422 that do not.

Node headers are also not laid out contiguously: consecutive ones sit 172, 384, 236 or 404
bytes apart, because each node is followed by its own program. So the vocabulary cannot be
recovered by scanning for a stride either.

## The permissive program scan contaminates the ISA

Chasing the FX residue found that 97.7% of the positions where a tree walk stops fail
`valid_program` on an **uncatalogued opcode**. That suggested the ISA was incomplete. The
opposite is true: the ISA was being measured on programs that are not programs.

### The measurement that exposed it

Under three-address code an operand must name an earlier value, so an operand greater than
or equal to its own value number is impossible. Measured over `referenced_programs()` --
the permissive scan that accepts a program at any 4-aligned word pointing to one:

    add    38.5% impossible        lteq   86.5% impossible
    set    52.4%                   dot    74.6%

No encoding makes addition's operands impossible 38% of the time. Measured over
`r.programs` -- only the programs a record's slots name - the same figure is **0.1%**.

The permissive set contains positions that are not programs, and decoding them produces
instructions that are not instructions. This is the same failure that produced the phantom
opcodes, resurfacing in a tool that was built after them.

### Sixteen op ids exist only in the scan

    0x05 0x08 0x0A 0x0E 0x0F 0x19 0x2C 0x37 0x38 0x39 0x3A 0x3B 0x3C 0x3D 0x3E 0x3F

None appears in any strictly-named program. `0x35` and `0x36` are the same: **absent from
strictly-named programs entirely**, so any reading of them is a reading of noise.

`0x1E` is a case where the multi-program fix changed the answer. It was recorded here as a
phantom - 4,374 occurrences in a permissive walk, 0 in strict. Now that `Record.programs`
returns every program a record names rather than only the first, it has **216 strictly-named
occurrences across 5 files**. Five files is weak, and it is still emitted opaquely, but it
is no longer nothing.

### `0x03` and `0x06` carry immediates

Two operations were rendering their operand as a value reference and should not.

| op | instances | operand >= own value number | is the program's first instruction |
|---|---|---|---|
| `0x03` | 6,177 | **75.7%** | **59.0%** |
| `0x06` | 762 | **69.3%** | 0.0% |
| `sysvar` | 120,336 | 0.0% | 80.5% |
| `get` | 51,544 | 0.0% | 41.7% |
| `add` | 1,118,531 | 0.0% | 0.0% |
| `eq` | 11,225 | 0.0% | 0.0% |

An operand that exceeds its own value number three times in four cannot be a reference,
and `0x03` is the program's first instruction 59% of the time, where there is nothing to
refer to. Both read something by index, in the manner of `sysvar` and `get`. **What they
index is not established**, so they stay unnamed and are emitted opaquely.

`0x06` is a correction to a report that had it as an ordinary operation with 0% impossible
operands - that figure comes from the contaminated set.

With both marked as immediates, impossible operands across the corpus fall to **0.0% of
3,434,611 instructions**. Every value reference points backward, which is what
three-address code requires and what a correct decode should show.

### The rule this establishes

`referenced_programs()` remains useful for the coverage question it was built for - finding
bytecode that no record slot names, which is real and which the FX trees rely on. It is
**not** a source for ISA statistics. Any opcode census, operand analysis, or immediate
inference must run over strictly-named programs, and any past figure that did not is
suspect.

## Fixing the ISA and the disassembler

Three defects, each of which made correct data look wrong or wrong data look correct.

### `program_span` and `valid_program` were two implementations of one idea

They had drifted. `valid_program` checked opcode well-formedness; `program_span` checked
only instruction lengths - and `program_span` is what `referenced_programs()` calls, so
every tightening applied to the validator silently failed to reach the scan that finds most
programs. They are now one function, with `valid_program` returning `program_span(p) is not
None`.

### The validator now checks that operands are possible

`isa.LEN` is a computed rule, `length = (opcode >> 10) + 1` for `0x0400 <= op < 0x8000`,
which is right but extremely permissive: **47% of all u16 values are well-formed opcodes**.
That is why a scan for programs finds so many that are not programs.

Two evidence-based tightenings:

**Op ids the format never uses.** Over strictly-named programs across all 641 specimens,
49 op ids occur and each appears in at least 5 distinct specimens. Fifteen never occur at
all:

    0x05 0x08 0x0A 0x0E 0x19 0x2C 0x37 0x38 0x39 0x3A 0x3B 0x3C 0x3D 0x3E 0x3F

**A correction to record.** An earlier pass here listed `0x35` and `0x36` among the absent.
That was measured on a 150-specimen sample. Over the full corpus `0x35` appears in **41
files** and `0x36` in **11**; both are real operations, and so is `0x0F`. The sample was too
small for a claim about absence, which is exactly the kind of claim a sample cannot support.

**Operands must name earlier values.** This is three-address code with contiguously
numbered results, so an operand at or beyond its own instruction's number is impossible.
Violated by 0.00% of instructions in record-named programs and 65% in scan-discovered
candidates - the check with real teeth. Adding it leaves the scan finding 64,967 programs
instead of 67,761, a 4% reduction, with **impossible operands falling from 65.02% to
0.00%**. The garbage was concentrated in a few candidates rather than spread thinly.

### The alignment pad was being read as data

`OPCODES.md` records that immediate-carrying opcodes come in two forms differing by
`0x0400` - one extra token - the longer form emitting a **2-byte pad** when the instruction
lands at 0 mod 4, so the immediate stays 4-aligned. `_imm` built its buffer from all
operand tokens and read from byte 0 regardless, so every constant in the padded form was
decoded from the wrong two bytes: the low half of one float32 joined to the high half of
the word before it, which destroys the exponent.

The correlation is exact - odd token counts occur only at `addr%4==0`, even counts only at
`addr%4==2` - and the two readings separate cleanly:

| form | from byte 0 | skipping the pad |
|---|---|---|
| 3 tokens, `addr%4=0` | 90.8% | **99.8%** |
| 5 tokens, `addr%4=0` | 98.0% | **100.0%** |
| 9 tokens, `addr%4=0` | 92.0% | **100.0%** |
| 4 tokens, `addr%4=2` | **100.0%** | 45.6% |

For the 9-token form, reading from byte 0 gives values like `7.5e-28` and `-3.0e-13`;
skipping the pad gives `1`, `0.001` and `0.333333`.

Corpus-wide, float constants decoding to a plausible magnitude go from **91.28% to
99.90%**, and the resulting histogram is what a material library should contain:

    1.0 (498,623)   0.0 (371,214)   0.5 (162,637)   0.25   0.75   -1.0
    8   2   4   16   5   0.693147

The last is **ln 2**. A misread float distribution does not produce a mathematical
constant, so that single value corroborates the fix better than the aggregate does.

## Bringing the rest of the tools up to the model

Fixing the disassembler exposed the same defect elsewhere: tools carrying their own copy
of logic that had since moved on.

### `fxdisasm.py` had drifted three ways

It carried its own tree walk, its own node table knowing **two** of the four node shapes,
and its own program validator predating the operand-possibility check. All three now come
from `sbsasm`. Its output is readable for the first time:

    === node 0x18B at +52  program @+64
      %0    0900  const.f1       0
      %1    0907  set.f1         %0, #12
      %2    1140  const.f2       2.82, 2.82
      %3    0947  set.f2         %2, #13
      %5    0D00  const.f1       0.125

Those constants are right only because of the alignment-pad fix.

### `attribute_outputs.py` was solving a problem that no longer exists

It opened by stating that the binary stores no output-to-record association and tried to
*constrain* the answer by elimination, resolving about 5%. The output table names the
record outright, so the tool's job is now **verification**, and the manifest supplies an
independent check: each input carries `alteroutputs`, the set of outputs it affects.

    p alters o         =>  o's record is reachable from some record reading p
    p does not alter o =>  o's record is NOT reachable from any record reading p

    specimens checked          639
    (input, output) pairs   39,855
       agree with the table 39,139   (98.20%)
       violations              716

**The violations are asymmetric, and that is the informative part.** Of those sampled,
**321 are "alters but unreachable" against 2 "reachable but does not alter"**. The second
direction is the one that would indict the output table - an output attributed to a record
that the altering input cannot influence - and it is essentially absent. The first says
edges are still missing, which the 1.63% unreachable residue already says.

So a manifest relation that had no part in deriving the output table agrees with it 98.2%
of the time, and disagrees almost entirely in the one direction that blames something else.

The tool also had two of the defects found this session in miniature: it read only the
main parameter program, missing every record that carries more than one, and it built uids
by splicing operand tokens without removing the alignment pad.

### A shared helper, so this stops recurring

`disasm.immediate`, `disasm.uid` and `disasm.floats` are now the only supported way to read
an immediate. Every instance of this class of bug - `program_span` versus `valid_program`,
`fxdisasm`'s private validator, `attribute_outputs`' hand-built uid - came from a second
copy of logic that was correct when written and silently stopped being correct.

## What `0x03` reads, and the limits of the impossible-operand test

### It is a load by index, and the index is not the variable frame

`set` writes a variable slot by index and `get` reads one. The clean control: **`get`'s
operand names a slot the record actually writes in 4,300 of 4,300 cases - 100%**. For
`0x03` it is 7.1%, and for `0x06` 5.4%. They index a different space, and a larger one:
220 distinct indices corpus-wide against the variable frame's 23.

### Reading real code says what it is for

With the disassembler fixed, short programs using it are legible:

    %0    0543  op03.f2        8
    %1    0651  cvt.i2         %0
    %2    1240  const.i2       -2, -2
    %3    0A52  add.i2         %2, %1

Read a value, convert to int2, subtract two - output-size arithmetic. Another:

    %0    0503  op03.f1        6
    %1    0528  sqrt.f1        %0
    %2    0535  op35.f1        %1
    %3    0525  ceil.f1        %2
    %5    0931  max.f1         %3, 0

Its consumers corpus-wide are `add` (1,393), `swizzle` (1,083), `cvt` (693), `min`,
`sqrt` - arithmetic, not sampling.

### What it is not

**Not a fixed table of typed engine variables.** The same index returns different types:
index 9 yields `f2` 98 times, `f1` 80 times, `i1` twice. A slot holding `$outputsize` would
be `i2` every time.

**One index per record.** Of 4,358 records using `0x03`, **4,222 use exactly one distinct
index**, and which index varies from record to record across 0..219. So each record reads
one thing, and the index identifies it relative to something the record supplies.

4,289 of those 4,358 also use `inputref`, so it is not a substitute for the graph-input
mechanism; it co-exists with it.

The role is settled - a load by index whose result feeds size and coordinate arithmetic -
and the space it indexes is not. It stays unnamed.

### The impossible-operand test has a blind spot

`0x03`'s operand is at or beyond its own value number in 90.3% of instances, which is what
established it as an immediate. Applying the same test to `0x06` gives 51.2% at token 0 and
78.8% at token 1, and reading real code shows `op06.f2 7 8` as a program's last
instruction, where `%7` is the instruction immediately before it - the `set(value, slot)`
shape rather than two immediates.

But the test cannot settle it, because of this control: **`set`'s own slot immediate reads
0.0% impossible**. Slot numbers are small and programs are long, so a genuine immediate
sits below its instruction's value number essentially always and looks exactly like a
reference.

So the test only has power when the immediate is *large*. It proves `0x03` is an immediate;
it cannot prove `0x06` is not. `0x06` has 979 instances across 21 files in two different
token-count forms, which is too little to split on, and it is left as it is.

This is worth recording because the test was persuasive twice today and has a stated
domain: it detects immediates that exceed their instruction's value number, and is silent
about every immediate that does not.

## Chasing the manifest violations to their source

The manifest cross-check produces 716 violations, almost all "alters but unreachable" -
the direction that blames a missing edge rather than the output table. Those name specific
files, which makes them a better lead than a corpus-wide average. `triDraw` has 58
violations in 73 records, small enough to read completely.

### A lead that looked good in one file and died in the corpus

Record 16 of `triDraw` is a `shuffle` whose **slot 1 holds 10, a valid backward record
index**, which the layout table does not claim as an edge. An unclaimed input edge is
exactly what a missing link should look like.

Measured across the corpus, over shuffle records whose slot 1 the table does not already
claim:

    backward index   37.2%        other   62.8%

and per key, the best is `(3, 281, 0)` at **65.2% backward with diversity 0.348** - against
the rule's requirement of 90% backward. **No shuffle key qualifies.** Slot 1 is not an
edge; `triDraw`'s record 16 is one of the 37% that happen to hold a value in index range,
and the other 63% do not.

This is the small-integer trap presenting itself for the eighth time, and the only reason
it did not land is that a single file is never enough to establish an edge.

### What the stranded records actually are

Classifying every record by whether an output reaches it, whether anything names it, and
whether it is an input-free `pixelprocessor` generator (slot 1 low half = 0):

    reachable, named, has edges      540,133  (91.7%)
    reachable, named, no edges        36,874  (6.3%)
    UNREACHABLE, named, has edges      6,667  (1.1%)
    UNREACHABLE, named by nobody       2,286  (0.4%)

Most unreachable records are **named** - they are stranded below a root, not roots
themselves. Only 2,286 are true roots.

And the generators are concentrated among them:

    input-free generators among UNREACHABLE records   687 of  9,701   (7.1%)
    input-free generators among reachable records   1,215 of 579,253  (0.2%)

**A 34-fold enrichment.** A generator with no consumer is dead by construction, so this is
consistent either with the cooker retaining dead code or with a reference mechanism not yet
read. The enrichment does not distinguish those, and 687 records do not account for 9,701,
so it is not the whole story either way.

What it does rule out is the tidy version - that one missing edge slot explains the
residue. The stranded population is mostly ordinary records hanging below a small number
of unreferenced roots, and those roots are disproportionately, but not mostly, generators.

## The layout-B prologue is a constant preamble

The region between `0x38` and the first record in version-2 files has been carried in
these notes as "holding programs and FX-Map trees", with about a fifth reachable from a
record slot and the rest an acknowledged gap. Re-measured with the stricter validator:

    layout-B files with a prologue    50
    prologue bytes                13,868
       programs and FX node headers  5,722  (41.3%)
       unexplained                   8,146  (58.7%)

The prologue sizes cluster hard: **30 of the 50 files have exactly 72 bytes**, and the rest
are one-offs between 16 and 1,440.

### Those 30 are the same 72 bytes

Byte-for-byte, across 30 files by unrelated authors, there is **one distinct 68-byte
prefix** and 15 distinct final words. It is a fixed preamble the compiler emits, not
per-file data.

    +0   0x00020008   +4   12
    +8   0x00020008   +12  20
    +16  0x00020008   +20  28
    +24  0x00020008   +28  36
    +32  0x00020008   +36  60
    +40  0x09000002   +44  1.0f
    +48  0x00000532   +52  44
    +56  0x00100048   +60  56
    +64  0x0A020001   +68  <varies>

### Two of those entries are programs, and they decode

    +40   program, 2 instructions
            %0    0900  const.f1       1
            %1    0532  rand.f1        %0

    +64   program, 1 instruction
            %0    0A02  inputref.i1    uid=4001147441

So the preamble carries **a random-number generator and a read of one graph input**, and
the single word that varies between files is that input's uid.

### The varying word is the random seed

    files with the 72-byte prologue                     30
    final word is a declared graph input uid       30 (100%)
    type code of that input                        4 in all 30

An integer graph input read immediately alongside `rand` is the random seed. Every version-2
package emits the same preamble to bind it.

The remaining entries are a table of `(tag, byte offset)` pairs whose offsets point inside
the prologue - `+52` holds 44, which is exactly where the `const.f1` immediate sits. The
tag values `0x20008`, `0x532` and `0x100048` are not decoded, and the table is not needed
to read either program, so it is left as it is.

This closes the region for 30 of 50 files. The other 20 have larger, file-specific
prologues and are still open.

### The larger prologues are the same structure, and programs are 2-byte aligned

The 20 layout-B files without the 72-byte preamble have prologues from 16 to 1,440 bytes.
They are the same idea scaled up: every `inputref` in them names a real graph input -
**36 of 36, 100%** - so the prologue's job is binding graph inputs to programs in all of
them, not just the constant form.

But the coverage looked wrong. `Crystal_2_Animated` reported **2% of its 1,440-byte
prologue as programs**, and `Plasma_Animated` 29%, while `Cells_Animated` reported 97%.
A structure does not vary that much.

The scan was stepping **four bytes**. Programs are not 4-aligned - the alignment pad
exists precisely because instructions legitimately sit at 2 mod 4 - so a 4-byte scan
cannot see half the possible starts. In `Crystal_2_Animated` the first unclaimed run
begins at `+50`, which is 2 mod 4.

Rescanning on 2-byte alignment:

| file | 4-byte scan | 2-byte scan | programs found |
|---|---|---|---|
| `Crystal_2_Animated` | 2% | **91%** | 1 -> 14 |
| `Plasma_Animated` | 29% | **97%** | 2 -> 6 |
| `Perlin_Noise_Animated` | 28% | **97%** | 2 -> 6 |
| `Wood_Planks_01` | 11% | **71%** | 2 -> 10 |
| `Clouds_Animated` | 11% | **83%** | 1 -> 5 |
| corpus | 42.7% | **84.8%** | |

`coverage()` had the same 4-byte assumption, and its own comment already said "the
prologue is 85% programs" - which is the 2-aligned figure. It was painting the difference
as a named gap rather than reading it. Corrected, **11,118 of 13,868 prologue bytes move
from "acknowledged gap" to "decoded program"**, leaving 2,750 - the index table.

The alignment mistake is the same shape as the others found today: a convenience that was
true of most cases, applied as though it were a property of the format. Records are
4-aligned; the programs inside them are not.
