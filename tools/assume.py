#!/usr/bin/env python3
"""Explicit assumptions, for arbitrating a guess against the reference renders.

WHY THIS IS A SEPARATE MODULE. `render()`'s contract is that it never emits an image it
cannot defend -- which is why `blur`'s baked fallback was withdrawn and `distance`'s
parameter slot is deliberately unlocated. That contract is right and nothing here changes
it. But it produced a bind, recorded in FORMAT-NOTES: the reference renders cannot arbitrate
our guesses, because our refusals to guess are what block the reference renders. 96 declared
outputs in the eight reference specimens, 10 produced, 0 spatially varying, and the top
blockers are `blur`'s withdrawn fallback (70 records), `dyngradient` (24), `distance` (11).
Every one is something somebody correctly declined to assume.

The bind dissolves because SCORING DOES NOT NEED A CORRECT RENDER, IT NEEDS A COMPARABLE
ONE. Rendering candidate A and candidate B and asking which matches the engine's own exported
map is how a guess gets arbitrated; refusing to render either is what makes it
unarbitratable.

So: a caller who wants to arbitrate passes an explicit assumption, gets an image, and scores
it. A caller who wants coverage passes nothing and gets today's behaviour exactly.

THE RULES, which are what keep this from becoming a way to make the numbers look better:

  * Assumptions are OPT-IN and empty by default. `assumed(key)` returns None unless a caller
    has opened a scope, so no sweep can pick one up by accident.
  * Every record rendered under one is recorded in `USED`. A coverage count that does not
    subtract `USED` is wrong, the same way one that does not subtract `LOW_CONFIDENCE` is.
  * A key names a QUESTION, not a filter, so an A/B is a one-key change and the thing being
    arbitrated is legible from the call site.

This module deliberately holds no defaults and decides nothing. It is a channel.
"""
import contextlib

# question -> the candidate values it is worth arbitrating. Documentation, not enforcement;
# a caller may pass anything, and an unknown key is that caller's business.
QUESTIONS = {
    'blur.intensity':     ('program', 'slot3'),
    # 'wide' names a reading rather than a location: take component 0 of a 2-COMPONENT
    # program result. The 31 `distance` records that locate nothing have only 2-component
    # programs -- 24 of them a single `exp2(min(swizzle($sizelog2) - $sizelog2, 0))`, an
    # aspect term that is 1.0 on a square image. Whether its first component IS the
    # distance is a guess with an arbiter available, which is what this channel is for.
    'distance.param':     ('program', 'block1', 'slot5', 'wide'),
    'distance.invert':    (False, True),
    'distance.mask_edge': (0, 1),
    # The footprint is no longer a four-way guess: `patterntype` is declared in the entry
    # tag and the manifest NAMES its values, so `fxrender.PATTERN_SHAPES` selects the shape
    # from shipped data and this question only exists to FORCE one for an experiment.
    # Every honourable name must be listed -- an omitted one is rejected here, which is the
    # same failure as accepting a value that cannot be delivered, in the other direction.
    'fx.profile':         ('rect', 'square', 'disc', 'paraboloid', 'bell', 'gaussian',
                           'thorn', 'pyramid', 'brick', 'gradation', 'waves', 'halfbell',
                           'ridgedbell', 'crescent', 'capsule', 'cone'),
    # What a record whose arithmetic went non-finite should emit. The recurring case is
    # an AUTO-LEVELS remap, (L - min) / (max - min), over a source that is constant: max
    # equals min, the range is zero-wide, and 0/0 is degenerate for any renderer including
    # the engine. There is no arithmetic to fix, only a decision about what to write, and
    # three specimens now block on it -- Chesterfield rec330, WoodSubstance005 rec139/245,
    # Bricks_and_tiles rec10330, the last of which gates four channels of the only
    # reference-scored package that has them.
    # What an entry that states NEITHER a patterntype NOR a patternsize should draw.
    # Today it is a full-cell rect, which paints the whole canvas white, and three
    # specimens turn white for exactly that reason -- Chesterfield rec43, WoodSubstance005
    # rec85, Bricks rec5228. The entry is read correctly; what is unknown is what the
    # engine draws when the file states no extent.
    #
    # ITS SCOPE COLLAPSED IN THE FX MASK-WALK RESTRUCTURE, and any earlier reasoning that
    # leaned on this key has to be re-read in that light. On Bricks a sizeless entry is now
    # 265 of 39,549 emissions -- 0.7% -- across 95 records. The three fxmaps leaves that
    # feed the missing-lattice cone (5513, 5515, 5518) were the motivating specimens for
    # this question and they are NO LONGER SIZELESS: they state patternsize 5.0 and their
    # branchoffset programs use the rand opcode, so they are random-scatter records that
    # this key does not touch at all.
    #
    # That is a simplification, not a loss. Those leaves used to paint white because a
    # typeless entry fell back to a full-cell 'fill'; they now paint white because 5.0 in
    # canvas units covers the image. Same picture, and now the SAME cause as rec5596 --
    # one defect where the earlier reading had two. The oversized-patternsize question
    # below now explains the whole cone on its own.
    'fx.sizeless':        ('fill', 'skip', 'half', 'quarter'),
    # PUT TO THE REFERENCE MAPS AND NOT SETTLED, which is worth recording so it is not
    # tried a third time. Under any scope Chesterfield's `basecolor` renders and the
    # scoreable table goes 14 channels -> 17. But of those 17 only 3 move between
    # candidates, 0.5 and 1.0 give BYTE-IDENTICAL results, and the three that move
    # separate by less than 0.001 MAE:
    #
    #     basecolor.0   0.0 -> (0.1299, r 0.090)   0.5 and 1.0 -> (0.1298, r 0.102)
    #     basecolor.1   0.0 -> (0.2142, r 0.051)   0.5 and 1.0 -> (0.2142, r 0.056)
    #     basecolor.2   0.0 -> (0.0958, r 0.043)   0.5 and 1.0 -> (0.0959, r 0.052)
    #
    # Two candidates being indistinguishable says the filled value barely propagates --
    # something downstream saturates it -- so this is not an arbiter narrowly missing, it
    # is an arbiter that cannot see the parameter. And the unblocked output correlates at
    # 0.04-0.10 whichever value is chosen: rendering `basecolor` does not make it right.
    # WHAT THE ABSENT SIDE OF AN INVERSION PAIR DEFAULTS TO. Substance inverts a levels by
    # setting in_low ABOVE in_high -- 1.0 and 0.0. 185 records corpus-wide state exactly one
    # of that pair and nothing else: 176 state levelinhigh = 0.0, 9 state levelinlow = 1.0.
    # The structural side verified there is no second value to find -- the parameter block
    # is one header slot plus one parameter slot, the other side's presence bits are clear,
    # so the file really does state one end only.
    #
    # Under the standard defaults (absent high -> 1.0, absent low -> 0.0) those become
    # [1.0, 1.0] and [0.0, 0.0], both zero-width, and the record renders a constant. The
    # candidate is that an author setting one end of an inversion expects the other to be
    # its opposite extreme, giving [1.0, 0.0] -- an inversion rather than a flat.
    #
    # IT IS A QUESTION AND NOT A FIX because the two readings are not separable structurally
    # -- both are consistent with the bytes -- and because being wrong here manufactures 185
    # plausible pictures. Only a reference render decides it, and Bricks graph 003 is the
    # specimen: it currently correlates r ~ 0 against its own graph's exports, so a real
    # correction has to move that and a merely-plausible one cannot.
    #
    # SCORED, AND 'complete' IS REFUTED. Against graph 003's own exports, and graph 002 in
    # the same pass as the control:
    #
    #     candidate    003 normal  roughness   height    AO  |  002 normal  roughness
    #     flat            -0.019     +0.016    -0.101  -0.004 |    +0.571     +0.891
    #     complete        -0.122     +0.029    -0.031  +0.032 |    +0.571     +0.891
    #
    # 003 stays inside the noise band on every channel; normal moves the wrong way. The
    # candidate DOES change the picture -- the numbers all move -- it simply does not make
    # it agree with the engine, which is precisely the "renders is not right" outcome this
    # question was built to detect. 002 is byte-identical under both, confirming the arm
    # never fires there, so 003 was the only test available and it says no.
    #
    # AND THE SOURCES AGREE, from a direction the render cannot reach. Scanning the levels
    # nodes of the permitted paired .sbs sources -- 389 nodes across 96 packages -- for how
    # an inversion is actually written:
    #
    #     inversions with BOTH endpoints named    21   (leveloutlow > levelouthigh)
    #     one-sided at an inversion extreme        1   (levelinlow 1.0, high absent)
    #
    # Every inversion in the permitted sources names both ends. So the format has no
    # implicit inversion: an author who wanted one wrote both numbers, and a compiled record
    # stating one side is not a dropped pair -- the absent side is a genuine default. The
    # structural session reports the same law over a wider source set (66 inversions, all
    # two-sided), and the one-sided cases it found it characterises as authored intent
    # rather than as inversions.
    #
    # That is the second independent refutation of 'complete', reached from the sources
    # rather than from a score, and the two agree. Kept as a scored negative rather than
    # deleted: the inversion reading is a reasonable thing for the next reader to arrive at,
    # and this is the evidence that it was tried twice, two ways, and failed both.
    #
    # WHAT REMAINS GENUINELY OPEN is narrower than it was: rec9 and rec39 are a faithful
    # decode of an authored [1.0, default] range, so the flat is what the file asks for --
    # and graph 003 still disagrees with the engine's export. Either the engine treats a
    # zero-width range differently from this step reading, or the flatness enters somewhere
    # neither side has reached. No second scoreable specimen exists to separate those: the
    # corpus has exactly one flat-at-r~0 output, and the packages carrying comparable
    # one-sided levels ship no reference renders.
    # WHETHER A 0x99 SCANNER NODE RUNS ONCE OR SCANS. The walk runs this node's program a
    # single time and then emits one pattern. The structural side reads the program as a
    # SERPENTINE RASTER SCANNER: nested row/column counters in slots 16/17, a step-direction
    # accumulator in slot 18 flipped at row ends, a position in slot 14 advanced by that
    # step and copied to slot 12 -- which is what frameoffset reads -- and a tail that
    # compares the position against slot 0 with +-0.5 offsets, i.e. an in-bounds predicate
    # shaped like a while-body continue test.
    #
    # If that reading is right the node is a loop body and running it once lays a single
    # stamp of the (1/step)^2 it would tile. Three unfitted measurements agree that this is
    # what happens: the step constant equals the pattern size (0.25 on Chesterfield rec34),
    # the coverage deficit is exactly 1/size^2 on both content-bearing records (16.0 and
    # 5.8), and the engine's exported metallic is a dot grid at 1/8 pitch, which is a 4x4
    # tiling of a cell carrying 2x2 blobs.
    #
    # SCOPE, censused by the structural side over 130 packages: 36 of 11,940 fxmaps records
    # carry a 0x99 at all -- 0.3%, extrapolating to roughly 180 corpus-wide. Within that
    # population it is uniform: 31 of 36 have the exact ADDNODE -> 0x99 -> LEAF chain and 34
    # of 36 end their program in comparison or boolean ops. So this is a narrow population
    # with a consistent shape, not a per-record special case -- which is the argument for it
    # eventually being node semantics rather than a candidate.
    # RUN, AND THE LOOP ALONE CHANGES NOTHING -- reported here because it was promised
    # either way. Under 'loop', Chesterfield rec34 and rec65 still emit exactly ONE pattern
    # each, coverage still 0.0254 and 0.1377, every output byte-identical to 'once'.
    #
    # The reason is a second gap, and it is not a guess: evaluating the scanner's program
    # against a plain slot dict raises `slot 18 read but never set`. In the render path the
    # frame is a Perm, which fills a missing slot rather than refusing, so the read succeeds
    # with a default and the step comes out ZERO. `seed_slots` seeds this scanner's state
    # deliberately and its own docstring lists what -- "position in 14, counters in 16 and
    # 17" -- with no 18. Slot 18 is the step-DIRECTION the position is advanced by, so with
    # it defaulted the scan cannot move whether or not the body repeats.
    #
    # THAT WAS WRONG, AND TRACING THE REAL LOOP CORRECTS IT. The `slot 18 read but never
    # set` came from a probe that ran the scanner program directly, without the addnode
    # above it; in the walk the addnode's `numberadded` runs FIRST into the same frame, and
    # it is also the scan's initializer -- it writes slots 12, 14, 16, 17, 18 and 20. So
    # slot 18 is seeded from the file, and the step is not zero. Instrumenting the loop:
    #
    #     iter 0   slot18 (step) = [-0.0, 1.0]   slot14 (pos) = [0.0, 1.0]   predicate = 0.0
    #
    # The step is a unit vector, the position advances by it, and the loop stops after one
    # iteration because THE PREDICATE IS FALSE, not because nothing moved.
    #
    # AND THAT IS A UNITS MISMATCH, which the structural side predicted as the next thing to
    # check before the trace existed. The step is one CELL; the predicate bounds the
    # position against +-0.5, which is the CANVAS half-extent. A cell step of 1.0 leaves a
    # +-0.5 canvas bound on the very first move, so the scan reports itself out of bounds
    # immediately. With the cell size 0.25 between them, steps land at 0, 0.25, 0.5 -- four
    # per axis, sixteen cells, which is the deficit exactly.
    #
    # AND IT IS NOT A UNITS EDIT EITHER -- reading the frame settles it. The bound and the
    # cell size are both IN the slot frame and can simply be looked at:
    #
    #     slot 0  (bound)      [0.0, 1.0, 0.0, 1.0]      a one-cell box
    #     slot 10 (cell size)  [1.0, 1.0]                one cell spans the whole canvas
    #     slot 14 (position)   [0.0, 1.0]   after one step -- at the box edge
    #
    # The structural side predicted slot 10 = vec(1.0, 1/gridsize), so [1.0, 1.0] means
    # gridsize = 1. The scanner is laying exactly one stamp because the geometry it was
    # handed describes a 1x1 grid, and its predicate is correctly telling it that one step
    # leaves the box. Nothing about the loop, the step, the units or the predicate is wrong:
    # every one of them is behaving correctly for a grid of one cell.
    #
    # SO THE FAULT MOVES UPSTREAM AGAIN, to whatever computes the grid. Program 532980 is a
    # record program (so seed_slots does run it), it writes slots 0 and 10, and the only
    # graph input it reads is uid 3139271155 -- type 8, value (8, 8) -- which it passes
    # through exp2. That is the $outputsize convention, log2 of 256. Why a 256-pixel canvas
    # yields a one-cell grid where the reference shows four cells per axis is the open
    # question, and it is a question about that program's arithmetic rather than about the
    # scanner that consumes its result.
    #
    # AND IT IS SYSTEMATIC, not one record's data. Seeding every scanner-bearing fxmaps
    # record in a 40-file sample and reading slot 10 straight out of the frame:
    #
    #     slot 10 = (1.0, 1.0)     4 of 4 records, 3 files
    #
    # Every scanner this renderer evaluates is handed a 1x1 grid. So the geometry programs
    # are collapsing to one cell everywhere they are run, which makes this an evaluation
    # fault with a single cause rather than a per-record decode question -- and it also
    # disposes of the obvious repair. The structural side proposes multiplying the step by
    # slot 10, on the reasoning that slot 10 is a computed cell size that nothing reads.
    # That is sound as far as it goes, but slot 10 IS 1.0 in every record observable here,
    # so the multiplication is the identity and cannot move any picture until the program
    # that computes it produces something other than one.
    #
    # AND (1.0, 1.0) IS CORRECT -- the census was the renderer being right. Program 532980
    # is ASPECT COMPENSATION, not subdivision: exp2(log2 W - log2 H), which is W/H, and 1
    # for any square canvas. There is no grid there to get wrong, so "why does it yield one
    # cell" was a malformed question. rec34's 4x4 lives in program 530756, keyed on $number,
    # placing at (0.125 + 0.25*($number mod 4), 0.125 + 0.25*floor($number/4)) -- which also
    # makes the scanner loop irrelevant to THIS record, whose scanner geometry is a
    # legitimate 1x1 and whose tiling is $number-keyed.
    #
    # THE DEFICIT IS THE EMISSION COUNT, shown by experiment. Forcing numberadded to 16 so
    # $number runs 0..15 and letting 530756 place them:
    #
    #                      emissions   rec34 lit   metallic lit
    #     baseline                 1      0.0254         0.0039
    #     forced n = 16           16      0.2285         0.0288
    #
    # A 9x rise in coverage from the count alone, pattern size untouched at 0.25.
    #
    # It stops short of the predicted ~0.40, and the residue is specific: the emitted
    # frameoffsets run -0.375, -0.125, -0.875, -0.625, -1.375, -1.125. They sit on the
    # correct 0.25 lattice, so the pitch is confirmed, but they range outside the unit
    # square, so several stamps land off-canvas -- the `mod 1` the decoded formula specifies
    # is not taking effect here.
    #
    # NOTHING IS WIRED FROM THIS. numberadded genuinely evaluates to 1, and the decoded
    # formula ((g-1 mod 2) + g)^2 yields only odd squares, so 16 is unreachable through it
    # and the correct count must arrive by a path neither side has pinned. Forcing it was a
    # measurement, not a fix.
    'fx.scanner':         ('once', 'loop'),
    'levels.inversion':   ('flat', 'complete'),
    'nonfinite.fill':     (0.0, 0.5, 1.0),
    'uniform.fill':       (),      # a value, not an enumeration
    # The channel weights a single-input `shuffle` record applies. TWO SOURCE NODE TYPES
    # COMPILE TO THE SAME FILTER ID -- the paired sources declare `grayscaleconversion`
    # (100 nodes, parameter `channelsweights`, a float4) and `shuffle` (43 nodes,
    # parameters `channelalpha`/`channelgreen`/`channelblue`, integer selectors) -- which
    # is why one filter has two layouts, a weight vector and a selector word. Class-word
    # bit 8 says whether the weights are stored at all; where it is clear the compiler
    # emitted nothing and the engine uses the node's own default, which is not in the
    # file. A 4-tuple, so continuous rather than enumerated.
    #
    # TWO ROUTES TRIED, BOTH CLOSED. The reference maps cannot separate the candidates --
    # five of them, (1,0,0,0), the luminance weights, (.25 x4), (0,0,0,1), (0,1,0,0),
    # move 0 of 14 scoreable channels, because not one of these records reaches an output
    # the engine exported. And the question is not degenerate either: of the 26 bit-8-clear
    # records across 27 files, the 11 whose input renders all receive a FOUR-channel image
    # whose channels differ, so the candidates really do produce different pictures. It is
    # a live choice with no arbiter, holding 36 declared outputs.
    'grayscale.weights':  (),
    # WHAT UNIT A branchoffset IS IN. splat adds branchoffset to frameoffset and treats the
    # sum as canvas coordinates, but the two are not in the same unit: over 966 square-grid
    # fxmaps records the median of branchoffset's span / (G - 1) is exactly 1.0000, i.e. it
    # spans G-1 CELLS, while frameoffset points at canvas in both records that can answer.
    # Rendering agrees independently -- Chainmail record 0 puts one cell on screen read as
    # canvas, and a full 257 x 257 lattice read as cells.
    #
    # It is a QUESTION rather than a fix because the tail is uncharacterised: G is only
    # defined for a square emission count, and 30% of those 966 fall outside 10% of the
    # cell ratio. A reference render can settle what a span statistic cannot, which is
    # exactly what this channel is for.
    # THE THREE-WAY SPAN SPLIT, CHECKED AGAINST THE PROGRAMS. cleanroom-substance-00 reads
    # the span alone and sorts records into integer-span (scale these), rational span k/d
    # with d dividing the count (real grids, stored already normalised, correct today), and
    # no rational d (a rand scatter has no cell size, so no d exists). The span cannot see
    # what a record's position program actually does, so the two readings were crossed --
    # 60 files, classifying each record's branchoffset program as reading an integer2 input
    # (a grid), using the rand opcode (a scatter), or neither:
    #
    #     span group                       n      grid   scatter   neither
    #     integer span (SCALED)          326         0        63       263
    #     rational k/d, d | N            108        20         0        88
    #     no rational d <= 256         2,113         6     1,881       226
    #
    # TWO OF THE THREE HOLD, and hold well. Every one of the 20 program-identifiable grids
    # lands in the rational-span group, with zero scatters there -- so "these are grids
    # stored normalised" is confirmed from a direction the span statistic cannot reach. And
    # the no-rational-d group is 89% rand, confirming that a scatter leaves no cell size
    # behind.
    #
    # THE GROUP THE GUARD ACTUALLY SCALES IS THE ONE THAT IS NOT CONFIRMED. The integer-span
    # group contains NO record whose program reads a grid input, and 63 whose program calls
    # rand. Those 63 are a positive misfire: by the rule's own reasoning a scatter has no
    # cells, so dividing it by a cell count is the same category of error the sqrt(N) guard
    # made, at a fifth the rate. The remaining 263 are unclassifiable from the entry alone
    # and may well be grids -- a record whose $number decomposition happens one node up
    # reads as "neither" to a per-entry transpile -- but "may well be" is not the evidence
    # the other two groups have.
    #
    # So the guard is a large improvement and still not established on the population it
    # acts on. It has been shown to DECLINE the right records; it has not been shown to
    # SCALE the right ones.
    'fx.branchoffset':    ('canvas', 'cell'),
    # WHAT UNIT A patternsize IS IN, the other half of the same question. Canvas is refused
    # two independent ways: the 83 distinct baked values all sit in roughly [0.67, 8] --
    # 5.0, 1.5, 3.0, 1.0, 8.0, 2.0 -- which as canvas fractions are patterns from
    # two-thirds of the image to eight times it; and over 299 baked square-grid records
    # with G from 2 to 128 the correlation of size with 1/G is -0.074, where a canvas
    # fraction tiling a G-grid would have to correlate near 1.
    #
    # It is a separate key from fx.branchoffset because the two are COUPLED and scoring
    # them apart is what shows it. Correcting offsets alone puts the lattice in the right
    # place while each cell is still painted G times too large, so a half correction can
    # score worse than none -- which is what cleanroom-substance-0b measured on
    # Chesterfield (normal 0.0854 -> 0.0869) for two records whose span/(G-1) is exactly
    # 1.0000 on both axes, i.e. squarely on the law rather than in its tail.
    #
    # SCORED ON BRICKS, AND 'cell' LOSES -- the first time either member has been put
    # against a spatially-varying reference set rather than a span statistic. Both keys
    # swept together over Kutejnikov__Bricks_and_tiles, five paired outputs at 128:
    #
    #     psize   boff     overall    AO      height  normal  roughness
    #     canvas  canvas    0.1951  0.5758    0.3185  0.0394     0.2691
    #     canvas  cell      0.1973  0.5879    0.3185  0.0394     0.2718
    #     cell    canvas    0.2077  0.6149    0.3736  0.0311     0.2832
    #     cell    cell      0.2063  0.6076    0.3741  0.0312     0.2802
    #
    # AND THE ONE OUTPUT 'cell' APPEARS TO WIN IS THE ONE THAT SHOWS WHY MAE CANNOT BE
    # READ ALONE HERE. `normal` improves 0.0394 -> 0.0311, which looks like the fix
    # landing; it is not. On this pack MAE is dominated by a constant offset -- the
    # our-vs-reference MEAN gap is 0.56 on AO, 0.23 on height and roughness -- so it
    # scores agreement of level, not of structure. Comparing STD against the reference's
    # own std separates them, and every output moves the wrong way under 'cell':
    #
    #     output      ours(canvas)  ours(cell)   REFERENCE
    #     AO              0.1871      0.1362      0.1719
    #     height          0.1544      0.1139      0.1565
    #     normal          0.0306      0.0181      0.0401
    #     roughness       0.1219      0.0875      0.1429
    #
    # Under 'canvas' our contrast already sits close to the reference on all four; 'cell'
    # shrinks it 25-40% below. `normal`'s MAE fell because the image got FLATTER while the
    # reference is more textured than either, and a flatter image is nearer a constant --
    # not nearer this reference. So 'cell' loses wherever it applies, and 'canvas' stays
    # the default on evidence rather than on inertia.
    #
    # BUT READ THAT REFUTATION AT ITS ACTUAL SCOPE, WHICH IS NARROWER THAN IT LOOKS. The
    # 'cell' branch is guarded on a PERFECT-SQUARE emission count, because G is undefined
    # otherwise. On Bricks that guard fires on 68 of 175 fxmaps records; the other 107
    # (61%) have non-square counts and the sweep above did not move them AT ALL. So the
    # table refutes the policy AS IMPLEMENTED -- divide by round(sqrt(N)) -- on the 39% it
    # can reach. It does not refute "patternsize is in cell units" in general, and it must
    # not be cited as if it did.
    #
    # AND THE DEGENERACY IT LEAVES BEHIND IS NOT SMALL. Of 39,104 emitted patternsize
    # values in this one file, 35,739 -- 91.4% -- are GREATER THAN 1.0, i.e. read as
    # canvas units they are patterns larger than the whole image. The three modes are
    # 2.82, 5.0 and 3.0. A format in which nine of ten patterns overflow the canvas is not
    # a format being read correctly, whatever the score says, and the visible consequence
    # is documented at render.py's `warp` branch: rec5596 emits a clean 32x32 lattice of
    # 1,024 patterns at size 5.0 and is painted uniformly white.
    #
    # So the open question is not canvas-or-cell, it is WHAT THE DIVISOR IS. sqrt(N) is
    # one guess at it and scores badly; the emission's lattice dimension taken from the
    # addnode chain that generated it is a different number for every non-square record,
    # and is the one thing that would let the other 61% be tested at all.
    # 'oversize' IS THE CONDITIONAL FORM, AND IT EXISTS BECAUSE THE UNCONDITIONAL ONE
    # DAMAGES THE RECORDS THAT WERE ALREADY RIGHT. Splitting Bricks' fxmaps records by
    # their median emitted patternsize separates two populations, and BOTH contain perfect
    # squares, so 'cell' fires on both:
    #
    #     size <= 1  (27 records)   N = 9, 32, 625 ...   sizes 0.012, 0.25, 0.052
    #     size >  1  (133 records)  N = 16, 64, 841, 1024, 1521   sizes 1.92, 2.82, 3.0, 5.0
    #
    # A record emitting 625 patterns at size 0.052 is already coherent as canvas units;
    # dividing it by sqrt(625) = 25 makes it 0.002 and erases it. That is what the
    # unconditional sweep was doing to a fifth of the records while it fixed the rest, and
    # it is the most likely reason 'cell' scored worse overall than doing nothing.
    #
    # So 'oversize' applies the same 1/G ONLY where the canvas reading is self-evidently
    # impossible -- a median patternsize above 1.0, i.e. a pattern larger than the whole
    # image -- and leaves the coherent records alone.
    #
    # RECHECKED AFTER THE FX MASK-WALK RESTRUCTURE (FX_NODES/FX_NODES2/FX_ENTRY drained
    # onto the walk, entry table read as a linked list). Every number above was re-measured
    # against the new emission stream. The populations grew -- 22/83 records became 27/133,
    # and Bricks now walks 191 fxmaps records rather than 175 -- but the shape of the split
    # is unchanged, both halves still contain perfect squares, the 91.4% figure reproduced
    # exactly, and canvas/cell/oversize score IDENTICALLY to four decimals on all five
    # outputs. The scores not moving is itself explained: 80 of the 133 oversized records
    # paint uniform white under canvas, which is also what a sizeless entry painted under
    # the old 'fill' default, so the records that changed category did not change picture.
    #
    # AND THE PERFECT-SQUARE GUARD IS NOW THE DOMINANT LIMIT, worse than when 'oversize'
    # was added. Of those 80 uniform-white oversized records, only 15 have a perfect-square
    # emission count, so 65 -- 81% of the visibly broken records -- cannot be reached by
    # ANY current candidate, whatever divisor it uses. The blocker is the guard, not the
    # policy: G has to come from somewhere other than round(sqrt(N)) before the majority of
    # this file is even testable.
    #
    # THE GUARD IS NOT MERELY INCOMPLETE, IT IS INVERTED -- it selects against the records
    # it exists to serve. Classifying every Bricks fxmaps record by what its branchoffset
    # program actually consumes, and crossing that with which records each arm touches:
    #
    #     arm        touches   grid-by-input   scatter(rand)   neither
    #     cell            88               0              40        48
    #     oversize        68               0              25        43
    #
    # 88 of 88 and 68 of 68. Not one grid record is touched by either arm, and every record
    # they do touch is a random scatter or has no $number decomposition at all. The five
    # records in this file that ARE grids -- 5, 11, 20, 27, 33, all reading integer2 input
    # 3616786801 = (4, 8) -- emit 32 and 8 patterns, neither a perfect square, so the guard
    # excludes exactly the population a cell divisor is for.
    #
    # That is the whole explanation for both arms' scores. They apply a grid divisor
    # exclusively to non-grids, so 'cell' damaging coherent records and 'oversize' scoring
    # neutral are consequences of the guard, not evidence about cell units. A square
    # emission count is not a grid: cleanroom-substance-00 reports the same from the span
    # side -- a one-addnode chain emits in ONE dimension, where sqrt(n) is a spurious root
    # -- and separates the populations by CHAIN SIGNATURE instead, 163 of 163 within 10% of
    # the cell ratio for one shape against 239 of 1,321 for another. The signature is
    # visible here too: all five grids sit under 0x8b,0x89,0x8b.
    #
    # So the next divisor to score is not another function of N. It is read per record from
    # the integer2 input the position program consumes, gated on chain signature rather than
    # on N being square, and neither existing arm is evidence for or against it.
    #
    # A SECOND SCOREABLE SPECIMEN EXISTS AFTER ALL, and it agrees. The structural session
    # checked whether any reference-shipping pack contained records affected by the selector
    # change and found none, concluding the tightening was unscoreable. That is true of the
    # SELECTOR change; it is not true of the arms themselves. Chesterfield is sensitive to
    # them, and it is a single-graph, correctly-paired pack:
    #
    #     psize   boff     height MAE/std   normal MAE/std    metallic MAE
    #     canvas  canvas   0.2479 / 0.1064  0.0790 / 0.0747   0.0465
    #     canvas  cell     0.2479 / 0.1062  0.0790 / 0.0746   0.0465
    #     cell    canvas   0.2477 / 0.1051  0.0789 / 0.0742   0.0465
    #     cell    cell     0.2463 / 0.0998  0.0781 / 0.0719   0.0465
    #     reference std             0.0970           0.0722
    #
    # cell/cell wins on MAE and on std for both channels, and its std lands nearly on the
    # reference: normal 0.0719 against 0.0722, height 0.0998 against 0.0970, where canvas is
    # 0.0747 and 0.1064. Same direction as Bricks, on a different pack, a different author
    # and a single graph -- so the two specimens agree, which neither could establish alone.
    #
    # The margins are still small (0.0016 of MAE on height) and two packs is not a corpus,
    # so this does not move the default by itself. It does retire "there is no second
    # specimen", which was the stated reason the question could not progress.
    #
    # AND METALLIC IS COMPLETELY INSENSITIVE -- 0.0465 to four decimals under all four arms,
    # against a reference std of 0.1733 where ours is 0.0185. Whatever makes Chesterfield's
    # metallic flat, it is not the divisor, and that gap needs its own explanation.
    #
    # RE-SCORED AFTER THE levelinmid GAMMA FIX (b2f1d97), because every table above was
    # measured through a bug that put a constant offset on this pack -- the same offset
    # these notes kept warning about and working around by reading std instead of MAE. With
    # MAE meaningful again, no arm flips:
    #
    #     arm        overall     AO MAE/std    height         normal         roughness
    #     canvas      0.1253   0.1443/0.0621  0.3190/0.1541  0.0393/0.0305  0.2392/0.0887
    #     cell        0.1338   0.1329/0.0340  0.3742/0.1133  0.0310/0.0180  0.2765/0.0348
    #     oversize    0.1253   0.1444/0.0646  0.3187/0.1554  0.0393/0.0305  0.2393/0.0892
    #                          (ref std 0.1719)      (0.1565)       (0.0401)       (0.1429)
    #
    # canvas and oversize tie on MAE to four decimals, oversize stays marginally ahead on
    # summed std error (0.1717 against 0.1760) and cell stays worst on both. The ordering
    # is what it was, now measured through a renderer that is not lying about level.
    #
    # ONE THING THE FIX MADE WORSE, and it should not be buried: our AO std fell from
    # 0.1871 to 0.0621 against a reference of 0.1719. Before the gamma fix AO was slightly
    # OVER-textured and badly wrong in level; it is now right in level and badly
    # UNDER-textured. That is a real residual the offset was masking, and it is not a
    # patternsize question -- no arm here moves it.
    #
    # RE-SCORED UNDER THE SPAN GUARD (ccc896a extended to this key), which is the first
    # measurement of this question on a population the divisor is actually for. Six arms
    # over Bricks, patternsize x branchoffset:
    #
    #     psize      boff      overall MAE   summed std error
    #     canvas     canvas         0.1302             0.2442
    #     canvas     cell           0.1302             0.2426
    #     cell       canvas         0.1298             0.2357
    #     cell       cell           0.1298             0.2284
    #
    # 'cell' now beats 'canvas' on BOTH metrics at once -- the first time it has done so.
    # The margin is small and one pack cannot carry a default on 0.0004 of MAE, so canvas
    # stays the default; but every previous table had cell losing, and those were all
    # measured through the inverted guard.
    #
    # 'oversize' IS RETIRED. It was a threshold on the symptom of the bad selector, and the
    # span reading declines the coherent records structurally instead, so the extra
    # condition never fires: cell and oversize render byte-identically on all 175 Bricks
    # fxmaps records, 0 differing. A candidate that cannot differ from another is not an
    # option.
    'fx.patternsize':     ('canvas', 'cell'),
    # WHAT AN ENTRY WITH NO patterntype DRAWS. `profile_for` falls back to 'rect', a hard
    # fill of the whole cell, and its own docstring says that is "what the code has always
    # done, not because it is established". It is a DIFFERENT knob from 'fx.profile', which
    # overrides every entry including the ones that state a type; this one moves only the
    # entries that state none.
    #
    # It matters more than a catch-all usually would. Over 45 fxmaps-bearing files, giving
    # typeless entries a falloff instead of a hard fill adds spatial structure to 242
    # record outputs across 20 files and removes it from 14 across 3 -- because abutting
    # cells filled solid are flat, and the same cells with a falloff are a pattern.
    #
    # Scored against the one ground truth in the corpus, Chesterfield, no member wins
    # outright:
    #
    #     typeless     basecolor      normal   roughness(std)  metallic  height     AO
    #     rect         not rendered   0.1056   0.0718 (0.0036)   0.0454  0.2480  0.6832
    #     disc         0.1314         0.1045   0.0719 (0.0000)   0.0481  0.2478  0.6888
    #     cone         0.1334         0.0953   0.0719 (0.0000)   0.0481  0.2490  0.6937
    #     paraboloid   0.1324         0.0986   0.0719 (0.0000)   0.0481  0.2472  0.7003
    #     bell         0.1343         0.0940   0.0719 (0.0000)   0.0481  0.2498  0.7075
    #     gaussian     0.1357         0.0905   0.0719 (0.0000)   0.0481  0.2530  0.7070
    #
    # RE-MEASURED after the FX node/entry walks were drained onto the mask-walk. Everything
    # here held except two numbers, and one of them was carrying an argument. The basecolor
    # column moved in its last digits (disc 0.1259 -> 0.1314, paraboloid 0.1320 -> 0.1324,
    # bell 0.1341 -> 0.1343); every other figure is identical.
    #
    # WITHDRAWN: this block used to say "only 'disc' holds roughness's spatial variation --
    # std 0.0265 against the reference's 0.0262". Under the corrected walk disc collapses
    # roughness to 0.0000 like every other falloff. That statistic was the entire reason
    # disc was singled out, and it was an artifact of the old enumeration.
    #
    # What survives: every falloff RENDERS basecolor, which 'rect' does not produce at all,
    # and gaussian takes normal from 0.1056 to 0.0905. 'rect' still keeps metallic and AO,
    # and now keeps the only non-zero roughness variation as well -- though at 0.0036 it
    # undershoots the reference's 0.0262 by an order of magnitude, so no member of this set
    # gets roughness right.
    #
    # So the default does not move. A choice that improves two maps and flattens two others
    # is the half-correction this file already records being caught by twice.
    'fx.typeless_profile': ('rect', 'disc', 'cone', 'paraboloid', 'bell', 'gaussian'),
}

_ACTIVE = {}

#: record indices rendered under an assumption, cleared per `scope()`. Mirrors
#: render.LOW_CONFIDENCE: an image that depends on a guess must be countable separately.
USED = set()


def assumed(key, default=None):
    """The value a caller chose for `key`, or `default` when nobody opened a scope."""
    return _ACTIVE.get(key, default)


def note(record_index):
    """Record that this record's output depends on an assumption."""
    USED.add(record_index)


@contextlib.contextmanager
def scope(**choices):
    """Render under explicit assumptions. Nested scopes override outer ones.

        with assume.scope(**{'fx.profile': 'bell'}):
            img, _f, _s = render(asm, max_dim=None)
        # assume.USED names every record that depended on it
    """
    for k, v in choices.items():
        allowed = QUESTIONS.get(k)
        # An unhonourable value must fail HERE, loudly, rather than being silently aliased
        # by a consumer -- a channel that accepts what it cannot deliver produces a score
        # for a candidate that was never rendered. Only enumerated questions are checked;
        # `()` marks one whose values are continuous.
        if allowed and v not in allowed:
            raise ValueError('assume: %r is not a candidate for %r; try one of %r'
                             % (v, k, allowed))
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
    """The assumptions currently in force, for reporting alongside a score."""
    return dict(_ACTIVE)
