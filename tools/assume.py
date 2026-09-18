#!/usr/bin/env python3
"""Candidate assumptions used by rendering and sweep tools.

The registry is deliberately opt-in: without a scope, callers keep their existing
defaults. ``scope()`` validates registered enumerated choices, tracks records rendered
under a choice in ``USED``, and restores the previous state when it exits.
"""

import contextlib


# Empty tuples identify free-form values; other entries list the candidates a scope may use.
QUESTIONS = {
    "blur.intensity": ("program", "slot3"),
    "warp.reference_px": (
        "record",
        256.0,
        64.0,
        128.0,
        320.0,
        384.0,
        448.0,
        512.0,
        640.0,
        768.0,
        1024.0,
        2048.0,
    ),
    "dirwarp.edges": ("declared", "swapped"),
    # FLIPPED TO 1.0 by the mechanism that settled warp's ("a value equal to the default is
    # never typed"): over the corpus, `normal` states its intensity on 1,263 of 1,379
    # records and 1.0 is stated ZERO times, with 0.5 (20) and 2.0 (34) both present, while
    # `blur` -- the control -- types 1.0 ten thousand times. No reference channel depends
    # on it; the ratchet passes; it reaches 55 corpus files. `refuse` is the arm.
    # NORMAL'S INTENSITY WHEN THE SOURCE OMITTED IT. Not a placement question -- the
    # placement is settled (`header_words - 1`, 8 of 8 containment pairings). This is the
    # 389 corpus records whose last header slot holds a PROGRAM POINTER rather than a
    # parameter, because the source declared no intensity and the header ends one word
    # earlier. See render.py's normal branch for the census and the twin that proves it.
    #
    # THE VALUE IS IN NEITHER FILE, so no decoding recovers it, and the packs cannot
    # arbitrate it either: on UHL3D-Stylized_Sand_with_Rocks_01 every arm from 0.5 to 16.0
    # produces byte-identical record and failure counts (2,349 / 968), because what the arm
    # unblocks is still blocked further downstream. Kept 'refuse' by default.
    #
    # DO NOT ARGUE THE DEFAULT FROM A HOLE IN THE DISTRIBUTION. The same tempting argument
    # is available here as for warp -- 1.0 is absent from the baked values -- and it is
    # refuted the same way: in `blur`, 1.0 is the MODAL baked value at 10,200 of 14,931, so
    # this compiler plainly does not omit parameters merely because they equal a default.
    # FLIPPED TO 1.0 on the reference set: every reference channel is inert to the value
    # (RoofTiles, the one pack it unblocks, scores identically under 0.0 .. 2.0 at 256),
    # the ratchet passes, and it renders five of RoofTiles' six outputs and ~50,000 corpus
    # records that `refuse` left dark. `refuse` is the arm now. The value itself still
    # rests on the corpus argument below, not on a picture.
    # ARMS TO TEST A CANDIDATE, NOT A CHANGE: the first arm WAS `refuse`, so adding this
    # question changed no render. `warp` refuses when its intensity is absent (880 records,
    # 3.13% of warps, blocking 1,347 downstream) and had no arm at all, so the alternative
    # could not be measured. 1.0 is first among the values because it is the candidate the
    # evidence points at: absent from all 26,108 compiled stated intensities and from all 15
    # stated in permitted sources, while 0.75, 1.5 and 2.0 are present, and `blur` -- the
    # control -- states 1.0 10,357 times, so the test discriminates. See FORMAT-NOTES,
    # "Permitted sources corroborate `warp` default = 1.0".
    "warp.default_intensity": (1.0, "refuse", 0.0, 0.25, 0.5, 2.0),
    # BLUR'S INTENSITY WHEN THE SOURCE OMITTED IT -- the same question as warp's, and it
    # gates RoofTiles' basecolor (record 2190) and Auras' fourth basecolor (342), both
    # with reference maps, so unlike warp's this one is measurable. `refuse` first.
    "blur.default_intensity": ("refuse", 0.5, 1.0, 0.0, 0.25, 2.0, 4.0),
    "normal.default_intensity": (1.0, "refuse", 0.5, 2.0, 4.0, 8.0, 16.0),
    "blur.kernel": ("box", "gaussian"),
    "emboss.probe": ("passthrough",),
    # 'word1bit2' is the archived renderer's reading -- bit 2 as a BOOLEAN, which sees
    # a baked flag and misses the 38 corpus records whose field 1 holds a program.
    # 'field1' reads the two-bit code the walk declares, both arms.
    "normal.inversedy": ("ignore", "word1bit2", "field1"),
    # THE GRID `normal`'s INTENSITY IS EXPRESSED AGAINST. Default 256.0 -- a constant, not
    # the record's size. Measured against the engine's own exports, with no render of ours
    # in the loop: regressing the exported normal map's slope on the exported height map's
    # per-pixel gradient gives 160.005 on Chesterfield (2048 px, intensity 10) and 9.397 on
    # Rokviz (4096 px, intensity 0.25), against 160.000 and 9.405 predicted by a fixed 256
    # and 20.000 and 0.588 predicted by the record's own width. 'record' restores the older
    # reading, which is what `_reference_px` still returns for blur/warp/dirmotionblur.
    #
    # THE 'record' ARM IS NOW SEPARABLE AND IS REFUTED. It returns `v.width`, which is the
    # record's size AT THE `$outputsize` BEING RENDERED, not its tag -- so while scoring ran
    # at the DECLARED size it was 256 on every reference record and indistinguishable from
    # the default. Scoring at the implied `$outputsize` (23a5492) makes ChesterfieldSofa's
    # 256-tag normal record evaluate to 2048, and the arm scores normal ch0 at MAE 0.0650,
    # sd 0.0169, fit y=5.432x -- against 0.0332, 0.1207, y=0.764x for 256.0 -- with mean Z
    # back at the flat 0.9993 against the export's 0.9659. The three readings the caveat
    # above names (hard 256, the tag, `1 << DECLARED $outputsize`) are all file properties
    # and are still tied; only a reference pack with a non-256-tag `normal` record separates
    # them, and none exists. See FORMAT-NOTES.md, "`normal`'s 31% gain error is `height`'s".
    "normal.reference_px": (
        256.0,
        "record",
        64.0,
        128.0,
        512.0,
        1024.0,
        2048.0,
        4096.0,
    ),
    "distance.param": ("program", "block1", "slot5", "wide", "layout"),
    "distance.invert": (False, True),
    "distance.mask_edge": (0, 1),
    # `spread` is `nearest` WITHOUT the falloff multiply: the source's value at the nearest
    # lit mask pixel wherever the field is non-zero, 0 beyond the radius. It is what a
    # `combinedistance` of 0 says, and 0 is what every one of the 19 permitted sightings
    # declares; `nearest` is the combined (=1) reading. Arbitrated on Bricks graph 003,
    # deterministic, same construct as graph 001's 10254. See FORMAT-NOTES.md.
    "distance.propagate": ("field", "nearest", "spread"),
    "fx.profile": (
        "rect",
        "square",
        "disc",
        "paraboloid",
        "bell",
        "gaussian",
        "thorn",
        "pyramid",
        "brick",
        "gradation",
        "waves",
        "halfbell",
        "ridgedbell",
        "crescent",
        "capsule",
        "cone",
    ),
    "fx.sizeless": ("fill", "skip", "half", "quarter"),
    "fx.rootentry": ("draw", "skip"),
    "emboss.intensity": ("program", "reference"),
    "fx.gridcount": ("numberadded", "divisor"),
    # WHERE A CHAIN NODE'S PROGRAMS ARE PLACED. 'table' reads the byte offsets out of
    # `FX_NODE_PARAMS`, per header; 'walk' computes them from the header's mask through
    # `node_shape` and pairs the names onto them in field order. Two statements of one
    # address, which is the discipline the rest of the decode runs on.
    #
    # THE ROLE ITSELF IS NOT PART OF THE ARM, and an earlier version of this comment said
    # it was. Nothing in the mask states what a node's program DOES; the rule that read a
    # `count` against a `gate` off the low nibble was a fit on six headers whose two
    # candidate discriminators -- bits 1 and 8 -- the corpus cannot separate. Both arms take
    # the role from the census; see `fxnodes`, and `python3 tools/fxnodes.py --separability`
    # for the measurement that withdrew the fit.
    #
    # NOT AN ARM TO TEST A CHANGE. Over all 437 corpus files the two place every program
    # identically, so this changes no render. It is a question rather than a replacement
    # because a per-header offset table goes stale silently and a walk does not.
    "fx.nodemodel": ("table", "walk"),
    # WHAT `$pos` IS INSIDE AN FX-MAP. It is NOT the sampling coordinate it is in a
    # `pixelprocessor`, and the split is clean: of the programs that read `$pos`, 54,661 of
    # 55,462 pixelprocessor ones feed `samplelum`/`samplecol` (98.6%) against 17 of 26,803
    # fxmaps ones (0.06%). That is the residue in `sbsruntime.SYSVARS`' own note -- $pos
    # feeds a sampler in 34,180 of 86,627 uses -- resolved: the sampling half is
    # pixelprocessor's and the rest is FX-Map gates.
    #
    # ITS CONSUMER IS THE GATE. Of 26,741 fxmaps records whose chain reads $pos, 26,591 read
    # it in the program of an 0x89 gate and 150 in the stepper's; only 34 records read it in
    # a NAMED ENTRY PARAMETER at all (patternrotation 41, opacity 4, frameoffset 2). It is a
    # predicate input, not a placement one, read two-component in 26,907 of 26,907 reads and
    # immediately ADDED in 99.5% of them -- a base the node's own scanned offset is measured
    # from. The idiom is `$pos + <offset the program advances itself>` tested against a
    # float4 rectangle the record bakes: a cull, not a placement.
    #
    # THE RECORD'S OWN RECTANGLE ARBITRATES THE VALUE, and it is a mechanism rather than a
    # fit: the bounds are whole or half integers and the walk steps by whole units, so only
    # `$pos` = 0 puts the scan on the lattice the bounds are aligned to. Emissions against
    # the integer cells the rectangle encloses:
    #
    #     Rokviz 1/3     [-13, 14, -13, 14]         27x27 =    729    origin 729    corner 676
    #     Rokviz 10/12   [-49.5, 50.5, ...]        100x100 = 10,000   origin ok     corner ok
    #     EvilOrb 2      [-4, 5, -4, 5]               9x9 =     81    origin  81    corner  64
    #     EvilOrb 65/67  [-31.5, 32.5, ...]         64x64 =  4,096    origin ok     corner ok
    #
    # 'corner' misses on three and never wins. (EvilOrb 11/12 match neither -- rectangle
    # 7x7 = 49 against 441 and 324 -- and are an outer multiplier, not evidence either way.)
    #
    # 'pixel' IS REFUSED, not merely unchosen. The walk takes
    # `bool(run(prog, slots, number)[0])` -- ONE verdict per pattern -- so a per-pixel $pos
    # returns N verdicts and the walk silently keeps pixel 0's; that is precisely the
    # corruption the pre-fix `$pos` leak produced. And the reference specimen says so
    # outright: at $pos = (128, 128) Rokviz falls from 70 rendered records to 41 and stops
    # producing `height`.
    #
    # IT IS A PER-NODE CONSTANT, not a per-pattern value. Every per-pattern arm breaks the
    # rectangle count on Rokviz: a $number cell grid gives 416 and 1,792 where the rectangles
    # hold 729 and 10,000, a normalised $number gives 8,415, and ANY per-pattern jitter at
    # all gives 716 for 729.
    #
    # NOTHING IS SINGULAR AT ZERO, so no program argues it must be non-zero: across 26,803
    # $pos-reading fx programs, not one divides by a $pos-derived value. One record
    # (NetSubstance001 rec 50) takes a polar conversion of it, which is defined at the
    # origin.
    #
    # EVERY FIGURE ABOVE IS FROM THE COMPILED CORPUS. An earlier version of this comment
    # argued the same conclusion from named function graphs in the shipped `.sbs` sources.
    # Those sources are `<author v="Allegorithmic"/>` and SPEC 12 excludes them from
    # analysis, so that leg has been removed -- along with the parameter names it supplied.
    # The conclusion did not rest on it: it was corroboration, and the arbitration was
    # always the record's own rectangle. What may be read says nothing either way -- across
    # the 34 third-party sources containing an FX-Map, `$pos` appears inside one exactly
    # once, in `patternrotation`/`frameoffset`/`patternsize`, never in a gate.
    #
    # WHAT WOULD MOVE THIS: a SUBDIVIDED FX-Map -- a node whose children cover different
    # parts of their parent's region and so inherit different positions. `chain` is a FLAT
    # walk, so today there is one node position and it is the root's, and the place to
    # thread a per-node one is `make_runner`'s `run`. Searched for and not found: of 155
    # distinct node headers reached, `0x1db` is the only one whose word 1 equals its number
    # of trailing node pointers, and it is two-way at every instance -- arms that cover the
    # same region and share a `$pos`. Across the 266 FX-Map graphs in third-party sources, no
    # node has more than one child at all. That negative is BOUNDED BY THE CLEAN-ROOM RULE:
    # the sources that do branch are Allegorithmic and may not be read, so the claim is
    # "absent from what may be examined", not "absent from the format".
    "fx.pos": ("origin", "corner"),
    "fx.scanner": ("once", "loop"),
    "fx.gatescan": ("once", "loop", "filter"),
    # `bit18` IS PER CELL: entry-tag bit 18 clear draws by signed `add`, set draws by
    # `max`. Over the permitted paired sources bit 18 is set on exactly the entries whose
    # `paramset` DECLARES a `blendingmode` (ie_curve 43 of 43 own entries, ie_particles
    # 2 of 2, ie_pcloud 110 of 110, Bruno 1) and clear on every entry of the two sources
    # that declare none (Simulator__Grid 19, Clouds_3 4); the compiled tag does not say
    # WHICH declared mode, and a source states no default. `max` was arbitrated on
    # Chesterfield's tufting records, whose entries set bit 18; Bricks' subdivided
    # scatters -- the `opacity = -1` construct among them -- clear it. See FORMAT-NOTES.md,
    # "Graph 001's first annihilation point is a white canvas the file states".
    "fx.combine": ("bit18", "max", "add", "over"),
    "fx.negopacity": ("signed", "clip", "abs"),
    # THE FX-MAP RECORD'S OWN HEADER FIELDS. `read` initialises the canvas to field 0
    # (`background`, 1 word grey / 4 colour) and multiplies every pattern's opacity by
    # field 2 (`opacitymult`, the UI's Global Opacity); `ignore` is the draw as it stood,
    # a zero canvas and no multiplier. The names are `model.W1_PARAMS`' and rest on two
    # paired sources (Clouds_3's 0.42 / 10.7, ie_particles' (0,0,0,1)). Corpus-wide, all
    # 2,071 records carrying a negative baked opacity bake `background = 1.0` and none of
    # the 2,874 with only non-negative ones does.
    "fx.header": ("ignore", "read"),
    # `hurst` (field 1, the UI's Roughness) as a per-depth gain on the pattern's opacity,
    # under the tree arm's depth (root 0, its children 0, one more per quadrant level).
    # `exp` is the fBm reading of the name, 2^(-hurst * depth), under which the baked 0.0
    # the white-noise records state (Bricks 343, 9924: `rand(1)` leaves at depth 4) is
    # "no attenuation"; `pow` is hurst^depth, under which 0.0 kills every subdivided leaf
    # -- kept as the arm the noise records refute. `fx.hurst.absent` is the value a record
    # that bakes no field 1 takes: the source omits a default and the file does not say.
    # `exp2` is 2^(-2 * hurst * depth): the same exponent per AREA halving rather than
    # per side halving, kept because graph 001's own thresholds sit between `exp` and it.
    "fx.hurst": ("exp", "off", "exp2", "pow"),
    "fx.hurst.absent": ("zero", "one"),
    # THREE BITS THE BIT CENSUS PLACED AND DID NOT NAME. All three cost zero header words,
    # so nothing is misplaced by leaving them here; what is open is what they MEAN, and each
    # candidate below is a guess that would need something outside the file to settle.
    # See FORMAT-NOTES.md, "Every filter, bit by bit", and `archive/tools/bit_census.py`.
    #
    #   blend.w1bit8          w1 bit 8, set on 232,581 of 310,697 blend records and charged
    #                         nothing. It tracks the BLEND MODE: 98.5-100% set for every mode
    #                         that combines the two images arithmetically, 46.7% for `switch`
    #                         and 50.8% for `copy`, the two that select rather than combine.
    #                         Both edges are present either way, so it is not "a background
    #                         is connected".
    #   transformation.w1low  w1 bits 0-5. NOT SIX BITS OF ONE THING, AND NOT TWO-BIT
    #                         FIELDS: bits 0-4 are a 5-bit INTEGER and bit 5 is a separate
    #                         one-bit flag. Both are still unnamed, and what changed is that
    #                         the integer is now DESCRIBED rather than uninterpreted --
    #                         SPEC 7.4 and 13.4 carry the measurement.
    #
    #                         WHY NOT FIELDS. Cost is additive over a partition of the bits,
    #                         and four observed codes contradict every split finer than four
    #                         bits, each pair differing in bit 0 alone and all four occurring
    #                         under one class word: 0x21/0x20 say bit 0 is free where
    #                         0x3f/0x3e say it costs a word; 0x23/0x22 say a field at (0,1)
    #                         reads 10 and 11 at the same cost where 0x3f/0x3e do not;
    #                         0x27/0x26 say the same for a field at (0,1,2). The seed
    #                         hypothesis that these were independent FLAGS is refuted by the
    #                         first of those pairs just as the pair framing is by the rest.
    #
    #                         WHAT THE INTEGER IS. A halving count. Over the 4,192 records
    #                         reading 0..13 whose single image input resolves, the record's
    #                         own log2 size is max(input log2 - k, 0) on 84.1% -- 99.47%
    #                         where the input is a `levels` record, 92.72% where the record
    #                         carries a size expression -- against 25.3% for the same law at
    #                         k = 0 and 7.1% for a uniform guess. Value 31 is the ordinary
    #                         one (230,639 records), 30 emits a program pointer (25 records,
    #                         all returning an int1 computed from $sizelog2), 29 occurs 3
    #                         times and costs nothing, and 14..28 never occur.
    #
    #                         WHY IT IS STILL NOT NAMED. The name would have to come from
    #                         knowing what the engine calls a halving count, and no source
    #                         this project may read reaches any value but the default.
    #                         `tiling` IS REFUTED, source-side rather than manifest-side:
    #                         the manifest cannot speak here at all, because a field charged
    #                         zero words in its ordinary states has no pointer slot and so no
    #                         program to read an `inputref` out of, and the one arm that DOES
    #                         have a pointer opens on `sysvar 3` rather than an `inputref`.
    #                         Pinning permitted sources' transformation nodes to compiled
    #                         records by their stated `matrix22`/`offset` constants -- 73
    #                         nodes uniquely matched across 16 packages, where an earlier
    #                         pass reached 36 -- `tiling` 0 (19 nodes, 9 packages), `tiling`
    #                         2 (2 nodes, 1 package) and `tiling` unstated (52 nodes, 9
    #                         packages) ALL give 0b111111. Two different stated values cannot
    #                         compile to the same bits if those bits are the value. Still not
    #                         conclusive in the other direction: EVERY uniquely matched node
    #                         lands on the modal code, so no permitted source reaches any
    #                         other value and nothing source-side can say what the codes are.
    #
    #                         BIT 5 IS THE REMAINING UNNAMED ONE, and it is a bit rather
    #                         than half a field: read as a two-bit field at (4,5), states 10
    #                         and 11 ought to differ and instead behave alike, while 01 is
    #                         the one that parts. On the determinant of the record's own
    #                         baked matrix22, bit 5 set gives det>1 55.8% / det<1 23.7%
    #                         (n=26,459) and bit 5 clear det<1 58.4% / det>1 27.5%
    #                         (n=40,049); bit 4 moves neither. An association with the
    #                         direction of the scale at about 2.5:1, which is not a partition
    #                         and names nothing.
    #   emboss.w1field0       the w1 field at bit 1 -- bits 1 and 2 (SPEC 7.4: a field
    #                         begins at its own bit, and this one is odd, which is why the
    #                         reader that imposed an even grid needed a per-filter shift
    #                         constant here). 9 program slots, every
    #                         one carrying an `inputref` on a `float1` input and returning
    #                         `f1`. The nine identifiers are `bricks_age`,
    #                         `bricks_bricks_age`, `grunge_age`,
    #                         `concrete_damaged_grunge_age`, `concrete_intact_grunge_age`,
    #                         `Grunge_Effect_age`, `degradation`, `dirtiness` -- eight
    #                         distinct strings all naming an amount-of-wear slider, which is
    #                         semantic convergence and not lexical.
    #                         A LEAD, NOT A FINDING: the modal name has 2 packages and all
    #                         nine are ambientCG's or undeclared, so this is one author's
    #                         naming habit rather than independent packages agreeing. Type
    #                         and position are consistent with `emboss`'s `intensity`, and
    #                         that is exactly the plausible name that must not stand in for a
    #                         measurement.
    #                         READ IT ON THE SHIFTED GRID OR NOT AT ALL. Before the shift
    #                         landed, this sweep reported these same 9 programs as field 1
    #                         and reported field 0 as 366 programs of which 358 were the
    #                         `sysvar..exp2` size ratio and 8 read an input the manifest
    #                         identifies literally as `$pixelsize`. On the shifted grid those
    #                         375 sit on class bit 27 where `bit_census.PENDING_CLS[8][27]`
    #                         always said they belonged, and w1 fields 1, 2 and 3 are charged
    #                         zero words in their program state -- no pointer, no program,
    #                         nothing the manifest can be asked. The label moved by one and
    #                         the population moved with it, which is the check that the shift
    #                         was the right one and the reason a name read off the even grid
    #                         would have been wrong.
    #   fxmaps.cls22          class bit 22, costed one word, set on 3 records -- all in
    #                         `Texture_Randomizer`, ONE package, one author. The slot's
    #                         program returns `i2` and opens with an `inputref` on an input
    #                         the manifest declares `$outputsize`, type 8 (int2): the same
    #                         shape and the same type as class bit 16. What it means for one
    #                         filter to carry a second size-expression slot is not something
    #                         three records from one package can say. Listed so a reader can
    #                         see the bit exists and see how thin it is.
    #   dyngradient.gradpos   class bits 25 (baked, 0.5 on 86 of 95) and 26 (a program), an
    #                         ordinary baked/program pair. The program arm's inputs are named
    #                         `Stone_colour_Gradient_Input_Position`, `Stone_Colour_Grad` and
    #                         `Lichen_Colour_Variation` -- the material author's names for a
    #                         position into a gradient, not the parameter's own.
    "blend.w1bit8": ("ignore", "alphablend", "background_used"),
    "transformation.w1low": ("ignore", "tiling", "filtering", "mipmap"),
    # HOW `matrix22`'S FOUR WORDS ARE LAID OUT. `columns` (the default since this was
    # arbitrated on the whole reference set): the words are a column-major 2x2, so the
    # sampled position is `(m0 x + m2 y, m1 x + m3 y)`. `rows` is the reading before it,
    # `(m0 x + m1 y, m2 x + m3 y)`, which turns every rotation the wrong way. Symmetric
    # matrices (scales, flips -- all of Bricks) draw identically under both.
    "transformation.matrix": ("columns", "rows"),
    "dyngradient.gradpos": ("ignore", "position", "variation"),
    "emboss.w1field0": ("ignore", "intensity", "greyscale_amount"),
    "fxmaps.cls22": ("ignore", "outputsize"),
    "levels.zerospan": ("step", "identity"),
    "levels.inversion": ("flat", "complete"),
    "levels.interclamp": ("clamp", "noclamp"),
    # A NON-FINITE SAMPLE IS ZERO IN THE TEXTURE. Every node's output is written to a
    # texture, and IEEE NaN / inf convert to 0 in a UNORM texture (D3D's float-to-unorm
    # rule; GL's is unspecified and does the same in practice) -- so a record whose
    # arithmetic divides 0/0 (an Auto Levels on a constant input: 131 corpus files at 64
    # px, SandyStonePath's 11 before its tiling came alive) is a black image at the next
    # node, not a refusal. 0.0 is the default on that footing, `refuse` the arm; 0.5 and
    # 1.0 remain as the other fills a sweep can ask for. No reference pack exercises it at
    # the guard's grids, so the ratchet is silent; the record is marked low-confidence.
    "nonfinite.fill": (0.0, "refuse", 0.5, 1.0),
    "uniform.fill": (),
    "grayscale.weights": (),
    "fx.branchoffset": ("canvas", "cell"),
    "fx.patternsize": ("canvas", "cell"),
    "fx.frameoffset": ("canvas", "cell"),
    # SKIP FIRST, i.e. the default, and it is a READING rather than a guess. `splat` has
    # always carried `if skip_markers and (tag & 0xFF) == 0x08: continue`; the file tags these
    # patterns and we drew them anyway. Of the sizeless patterns on flat-origin fxmaps records,
    # 628 of 815 (77%) carry tag byte 0x08, and 85% carry ONLY `branchoffset` + `patterntype`
    # -- no opacity, no rotation, nothing about drawing. Drawing them at `fx.sizeless`'s full
    # canvas is what pins 574 of 574 flat-origin records to a constant.
    "fx.markers": ("skip", "draw"),
    # WHERE A PATTERN CENTRE OUTSIDE THE CANVAS GOES. `reach` draws up to three neighbour
    # copies and drops what they do not cover; `wrap` takes the centre modulo the canvas
    # first, which is what a tileable FX-Map does, and is the only way RoofTiles record 7's
    # rows (centres x = 0, 0.5, 1.0, ... 4.5) can all land. Identical for every pattern the
    # copies already reached.
    "fx.centre": ("reach", "wrap"),
    # THE SENSE OF `patternrotation`. `ccw` is what `splat` has always drawn: a rotation of
    # r turns is +2 pi r in the canvas's (x right, y down) frame. `cw` is the other sense.
    # RoofTiles' shingles are 0.75-turn gradient stripes (records 7, 61) and under `ccw`
    # each shingle is bright at the top where the reference is bright at the bottom lip,
    # with the layout otherwise in place (height corr -0.79 at the exported tile counts);
    # inverting `transformation`'s matrix instead fixes RoofTiles and wrecks Chesterfield
    # and Auras, so the sense in question is this one. Arbitrated on every pack.
    "fx.rotation": ("ccw", "cw"),
    "fx.typeless_profile": ("rect", "disc", "cone", "paraboloid", "bell", "gaussian"),
    # QUADRANT SUBDIVISION. `flat` is `fx.emissions` as it stood: every table entry drawn
    # once at full canvas, the chain-family cells read as links. `tree` reads the entry
    # cells as a nesting -- each cell a Quadrant whose four outputs are the quarters of its
    # region, the root's region the canvas AND its children's -- and draws what the tree
    # states: `render2.fxtree`. The structure is established (FORMAT-NOTES.md, "The level
    # fault upstream of 10055 is a white-noise FX-Map emitting ONE pattern, and the cons
    # chain is quadrant subdivision") and so is the root convention (879 of 1,146 sizeless
    # leaves; record 9924 at 0.513 / 0.292 / -0.012). DEFAULT `flat` UNTIL THE ARBITER SAYS
    # OTHERWISE: the reference guards are floored on flat, and a default flips when the
    # seed-free instruments on the deterministic graphs say the tree arm is not worse.
    "fx.subdivide": ("flat", "tree"),
    # The two draw-model questions the tree arm leaves open. `branchoffset` offsets a cell's
    # own pattern and its children; whether its unit is the canvas or the cell's region is
    # not settled (Bricks 9804's author halves it per level by hand, which argues canvas).
    # Which output is which quadrant is not settled either. Graph 003 cannot tell any of
    # these apart -- every instrument moves less than the renderer's own seed floor.
    "fx.tree.branchoffset": ("canvas", "region"),
    "fx.tree.order": ("rowmajor", "clockwise", "colmajor"),
    # HOW A `set` UNDER A `select` BRANCH EXECUTES. `eager` is the transpiler as it stood:
    # straight-line code, every `set` applied whichever branch the condition picks.
    # `lazy` applies a `set` only on the lanes whose `select` demands that branch, and not
    # at all when nothing demands it -- the demand-driven reading `while` already has
    # (its operand trees are re-evaluated per iteration, OPCODES.md). Bricks record 10081
    # is the specimen that separates them: its tile generator writes a row's height into
    # slot 44 inside the row-start branch and, under `eager`, overwrites it on every other
    # cell of the row with the difference of two fresh jitters, so the tiling's own
    # consistency (cell widths summing to the canvas, monotone edges) is the arbiter. See
    # `transpile.select_guards` and FORMAT-NOTES.md, "Record 10253 is not the fault".
    "program.select": ("lazy", "eager"),
    # HOW AN FX-MAP'S CHAIN NODES ARE WALKED. `list` follows one successor per node --
    # `fxrender.chain` -- and reads 0x89's spare word as "0", 0x1CB's as "0", and 0x19B
    # by its low byte as a stepper. `tree` reads the words the file fills: a 0x89 / 0x99
    # is a two-way Switch (the spare word its FALSE child, the successor its TRUE child),
    # a 0x1CB an Iterate whose spare word is a child run once AFTER the loop, and 0x19B
    # an Iterate (0x18B under bit 4; its program returns an int count, 245 of 245 corpus
    # nodes). Corpus census (437 files): 205 of 27,093 0x89 nodes carry a false child,
    # 88 of 238 0x99, 65 of 1,865 0x1CB -- about 150 records. A record whose chain has
    # none of these renders identically under both arms by construction (`fxchain.needed`).
    "fx.chain": ("tree", "list"),
    # `rand` INSIDE A PIXEL PROCESSOR. `image` is one draw per record -- `$number` is 0
    # and nothing else salts the hash -- so a program that is only `rand(1)` renders a
    # constant. `pixel` salts the hash per pixel, so the same program is a white noise.
    # Bricks 10080 (`0.001 + rand(0.999)`, no inputs) feeds a flood-fill-to-random-grey
    # that samples it once per cell at the cell's centre, and the reference height shows
    # one grey per stone; under `image` every cell reads the same 0.2115.
    "pixelprocessor.rand": ("pixel", "image"),
    # A `blur` WHOSE RADIUS IS UNDER A PIXEL ON THE RENDER GRID. `identity` returns the
    # input; `fractional` mixes the one-pixel box in by the radius. Not a question about
    # the format -- the radius is read the same way under both -- but about a render
    # drawn below the record's own size: Bricks 10164 states one pixel at `$size` and
    # gets 0.25 px at `--dim 256`, and its `|blur - x|` edge detector reads zero under
    # `identity`. See `render2.filters.f_blur`.
    "blur.subpixel": ("identity", "fractional"),
    # HOW A PIXEL PROGRAM SAMPLES ITS IMAGE INPUTS. `bilinear` is the shared sampler;
    # `nearest` the texel whose centre is nearest. An image that ENCODES values -- an
    # offset in texels, a cell's size, an id -- survives only the second: interpolating
    # two encoded offsets names no pixel. The file states no filtering mode per input
    # that this reader has found. See `ops.nearest_sampler`.
    "pixelprocessor.sample": ("nearest", "bilinear"),
    # WHAT `$outputsize` SAYS INSIDE A PIXEL PROCESSOR'S PROGRAMS. `grid` (the default,
    # arbitrated on the whole reference set): log2 of the grid the record is drawn on --
    # the rule `Context.run` already applies to `$size` for this one population, extended
    # to the other name a texel is derived from. `render`: the size the graph is evaluated
    # at, what every other program reads, and the reading before this. Under `--dim` below
    # the export size it is the difference between a live flood fill / height-to-normal
    # and a constant: RoofTiles' normal 0.00 -> +0.31/+0.73/+0.39, Chesterfield +0.002,
    # Auras and Bricks 002-005 identical, at 256 px under the implied `$outputsize`.
    "pixelprocessor.outputsize": ("grid", "render"),
    # THE `brick` PATTERN'S FOOTPRINT (patterntype 9, `SHAPE_MODELLED`). `inset` is the
    # hard fill at 85% of the box the profile has always drawn; `fill` is the whole box.
    # See `fxrender.profile_value`.
    "fx.brick": ("fill", "inset"),
}

_ACTIVE = {}

# Record indices rendered under an assumption; cleared for each scope.
USED = set()


def assumed(key, default=None):
    """Return the active choice for ``key``, or ``default`` outside a scope."""
    return _ACTIVE.get(key, default)


def note(record_index):
    """Record that a rendered record depended on an assumption."""
    USED.add(record_index)


@contextlib.contextmanager
def scope(**choices):
    """Temporarily apply choices and yield records marked within the scope."""
    for key, value in choices.items():
        allowed = QUESTIONS.get(key)
        if allowed and value not in allowed:
            raise ValueError(
                "assume: %r is not a candidate for %r; try one of %r"
                % (value, key, allowed)
            )
    saved = dict(_ACTIVE)
    saved_used = set(USED)
    _ACTIVE.update(choices)
    USED.clear()
    try:
        yield USED
    finally:
        _ACTIVE.clear()
        _ACTIVE.update(saved)
        USED.clear()
        USED.update(saved_used)


def active():
    """Return the assumptions currently in force."""
    return dict(_ACTIVE)
