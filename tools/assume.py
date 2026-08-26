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
    # THE ABSOLUTE PIXEL SCALE, which render.py flags as unverified in four places -- blur,
    # sharpen, directionalwarp and dirmotionblur all divide `intensity` by a hardcoded 256
    # and none of them has evidence for that number. A constant-factor error here makes
    # every blurred or warped edge too soft or too hard by the same ratio, which is exactly
    # the kind of defect a correlation cannot see and a picture can.
    'warp.reference_px':  (256.0, 64.0, 128.0, 320.0, 384.0, 448.0, 512.0, 640.0,
                           768.0, 1024.0, 2048.0),
    # WHICH INPUT IS WARPED AND WHICH SUPPLIES THE MAP. render.py calls this "the declared,
    # unverified-at-the-bytecode-level convention": one paired source names the connections
    # `input1` then `inputintensity`, matching edges[0]/[1] in that order, with no
    # independent proof. Getting it backwards produces "a plausible-looking but misdirected
    # warp, not a crash", which is precisely the failure this project treats as worst.
    'dirwarp.edges':      ('declared', 'swapped'),
    # THE KERNEL SHAPE, likewise flagged: "A separable box blur is used, which is what the
    # parameter means before any kernel shape is assumed; a Gaussian would differ in the
    # tails and nothing here distinguishes them."
    'blur.kernel':        ('box', 'gaussian'),
    # NOT A FORMULA -- A PROBE. `emboss` is unimplemented and heads the reference packages'
    # blocker table at 18 outputs, but a heading is what a gap TOUCHES, not what fixing it
    # would release (see FORMAT-NOTES on the census). 'passthrough' renders the filter as
    # its first input so the true unlock can be COUNTED before any formula is guessed at.
    # It is not a candidate reading of emboss and must never be scored as one.
    'emboss.probe':       ('passthrough',),
    # THE GREEN CHANNEL'S HANDEDNESS. The permitted sources declare `inversedy` on this
    # filter and render.py's normal branch says outright that not decoding it leaves "a
    # specimen using the other handedness rendering with its green channel inverted".
    # 'word1bit2' reads it from bit 2 of the record's word 1.
    #
    # THE ARBITER IS INDEPENDENT OF OUR RENDERER. Take a package's exported HEIGHT map,
    # run our own height-to-normal formula on it, and correlate against that package's
    # exported NORMAL map. Nothing of ours upstream is involved, so it measures the
    # formula and the convention alone:
    #
    #     package                     ch0      ch1      verdict
    #     Chesterfield              +0.991   +0.990    no flip
    #     Stylized_Sandy            +0.872   +0.859    no flip
    #     Stylized_Wooden           +0.704   +0.875    no flip
    #     Bricks_and_tiles          +0.891   -0.892    FLIPPED
    #
    # That also VERIFIES THE FORMULA, which render.py records as unverified: central
    # difference, scale, unit Z reproduces three packages' own normal maps at 0.87 to 0.99
    # on both gradient channels. Bricks is not structurally wrong, it is green-inverted.
    #
    # And the bit predicts it, 4 of 4, on the record that actually FEEDS each exported
    # normal: Bricks rec 12180 word1=5 (bit set), Chesterfield rec 121, Sandy rec 1452 and
    # Wooden rec 1414 all word1=1 (clear). Corpus-wide the bit is rare -- 2 of 53 normal
    # records -- which is what a non-default option looks like, and it is the ONLY
    # boolean-shaped difference among the 6 words that differ between Bricks rec 12180 and
    # Chesterfield rec 121, two records otherwise identical in all 123 words and class.
    #
    # SCORED, and it is surgical: of 16 usable channels exactly ONE moves. Bricks
    # `normal` ch1 goes from -0.158 to +0.158 -- an anti-correlated channel becoming a
    # correlated one -- and the other 15 come back byte-identical. It fires where predicted
    # and nowhere else.
    #
    # NOTE THE STATISTIC THIS ESCAPES. The mean |corr| used to decide the fx questions is
    # UNCHANGED at 0.2464 either way, because |-0.158| = |+0.158|. Absolute correlation
    # cannot see a sign error, which is exactly what this question is about; the signed
    # value is what has to be read here.
    #
    # THE EVIDENCE IS NOW SIX SPECIMENS, NOT ONE, and the earlier "one positive specimen"
    # was an artifact of a broken harness -- see FORMAT-NOTES on the collapsed scoring key.
    # Scored per ASSEMBLY rather than per package, the reference set has 55 channels, not
    # 15, and SIX of them are `normal` ch1 with the bit set. Every one is anti-correlated
    # and every one is corrected:
    #
    #     bit set, green anti-correlated   6      -0.585 -0.158 -0.126 -0.119 -0.093 -0.024
    #     bit clear, green correlated      1      +0.002
    #     bit set, green correlated        0
    #     bit clear, green anti-correlated 0
    #
    # On the full 42-channel usable basis it lifts mean SIGNED correlation from +0.1102 to
    # +0.1628, the largest move any candidate in this file produces, and the strongest
    # single channel it fixes reads -0.585 -> +0.585.
    #
    # THE WEAKNESS THAT REMAINS: the six positives are three assemblies of ONE package,
    # Kutejnikov__Bricks_and_tiles, each scored against two reference directories. So the
    # confusion matrix is clean but the positive side is one author's convention, and a
    # second package that sets the bit is what would settle it.
    #
    # SUPERSEDED, kept because the reasoning was right on what it saw: there is exactly ONE
    # positive specimen. Any field set in Bricks and clear in the other three would fit this
    # evidence, and rarity plus boolean shape is what distinguishes this one from the five
    # other differing words -- not a second package that sets it. Kept OPT-IN for that
    # reason; a second package that sets the bit and needs the flip would settle it.
    #
    # ADOPTED AS THE DEFAULT (see render.py's normal branch for the full note). The
    # reservation two paragraphs up -- one positive specimen, one moving channel -- was
    # written before the reference-pairing fixes and the patterning work. Bricks now renders
    # 12,585 of 12,585 records and FIVE of its graphs produce a normal with real signal, in
    # each of TWO assemblies, fed by TEN DIFFERENT `normal` records, every one carrying
    # word1 = 5.
    #
    # On all five signal-carrying graphs the correlation flips sign with its magnitude
    # intact to three decimals -- -0.585/-0.475/-0.594/-0.504/-0.683 becoming +0.585/+0.475/
    # +0.594/+0.504/+0.683 -- which is the signature of a handedness error and not of a gain
    # or a geometry error. Across every reference package exactly 7 of 112 scored channels
    # move, all `normal` ch1, all improving; the other 105 are byte-identical. Overall MAE
    # 0.1332 -> 0.1318.
    #
    # The bit is also not as rare as recorded above: 118 of 1,447 normal records set it,
    # across 40 of 444 files, against the "2 of 53" measured on a much smaller population.
    #
    # THE ORIGINAL RESERVATION STILL STANDS AND IS NOT DISCHARGED. Only one package with an
    # exported normal map sets the bit on the record that feeds it, so any field set in
    # Bricks and clear elsewhere fits this evidence just as well. `minime453__Stylized_
    # Sandy_Stone_Path` sets the bit on rec 175 -- which feeds basecolor, AO and height --
    # while its exported normal comes from rec 1452 with the bit CLEAR, and the
    # renderer-free arbiter says that package needs no flip. Consistent, so nothing is
    # refuted; not a second confirmation either. 'ignore' restores the old behaviour exactly
    # (0.1332), and a package that sets the bit ON its normal output and does NOT need the
    # flip would settle it the other way.
    'normal.inversedy':   ('ignore', 'word1bit2'),
    # PUT TO THE REFERENCE MAPS. `slot3` moves nothing at all -- 24 rendered outputs before
    # and after -- so the live candidate is `program`, and on the five reference packages it
    # is the single biggest lever there is: 24 -> 48 declared outputs rendered, 18 -> 24
    # scoreable channels. Scored, though, it is NEUTRAL rather than confirmed:
    #
    #   * all 18 channels that already scored come back BYTE-IDENTICAL. So it costs
    #     nothing, which is worth having on its own -- it is not a trade.
    #   * the 6 it adds carry no structure to speak of: correlations +0.140, +0.031,
    #     +0.159, -0.158, +0.109, +0.040, with fitted slopes 0.02-0.37.
    #
    # RE-SCORED with the harness fixed (keyed by assembly and by reference content, not by
    # package), and the answer is sharper than "neutral". Against `nonfinite.fill` alone:
    #
    #     scored channels            19  ->  73
    #     usable channels in common  10, byte-IDENTICAL 10, moved 0, lost 0
    #     newly scoreable            54, of which NOT degenerate  50
    #     mean correlation of those 50 new channels          +0.0002
    #
    # So it costs literally nothing, and it produces fifty genuinely varying images that
    # have ZERO relationship to the reference maps. That is not weak agreement, it is none.
    # Fifty channels averaging +0.0002 is, if anything, evidence AGAINST the reading rather
    # than for it -- a roughly-right intensity applied to a roughly-right input should leave
    # some positive correlation even with other errors present.
    #
    # It stays available as an arbitration BASIS -- more comparable channels is what
    # assume.py exists to buy -- but a candidate that moves those channels off zero would be
    # telling us something, and the baseline they sit at is nothing.
    #
    # So the references neither refute it nor confirm it, and it is NOT adopted as a
    # default on the strength of the count. The confound is worth naming precisely because
    # it is the reason the arm cannot decide: all 6 new channels are Bricks_and_tiles, and
    # Bricks is full of FX-Maps that render at exactly 1.0 (see FORMAT-NOTES on the white
    # FX-Maps). A washed-out generator upstream would produce exactly this signature --
    # rendered, low variance, near-zero correlation -- whether the intensity is right or
    # wrong. Nothing here separates a bad intensity from a good intensity applied to a bad
    # input, and the way to separate them is to fix the white FX-Maps and re-run, not to
    # pick a candidate.
    # 'wide' names a reading rather than a location: take component 0 of a 2-COMPONENT
    # program result. The 31 `distance` records that locate nothing have only 2-component
    # programs -- 24 of them a single `exp2(min(swizzle($sizelog2) - $sizelog2, 0))`, an
    # aspect term that is 1.0 on a square image. Whether its first component IS the
    # distance is a guess with an arbiter available, which is what this channel is for.
    # 'layout' IS 'wide' WITH ITS PRECEDENCE FIXED, and the fix is worth more than the
    # candidate. Under 'wide' the 2-component reading is tried BEFORE the structural slot
    # rule -- `layout start + 1 + cls bit 7 + cls bit 11`, verified 38 of 38 across six
    # filters in tools/param_slots.py -- and returns, so the derived rule is never
    # consulted. An ASSUMED reading pre-empting a DERIVED one.
    #
    # WHAT IT COSTS, on Bricks Textures_1's 126 distance records: 'wide' resolves all 126 to
    # just TWO distinct values, 1.0 on 121 of them and 2.0 on the other 5. The component it
    # reads is the aspect term `exp2(min(sizelog2.x - sizelog2.y, 0))`, which is exactly 1.0
    # on a square image, and every image here is square.
    #
    # (An earlier version of this note said 1.0 for EVERY one. That is wrong and it was
    # caught by a parallel session instrumenting the same call. The corrected claim is the
    # stronger one to carry: "all 126" is refutable by a single record, "two values across
    # 126" is not, and 2.0 changes nothing anyway -- at a 256 reference it is 0.5px on a 64
    # grid, still sub-pixel, so the transform is inert either way and its output is just the
    # thresholded mask. Six records masking six different colour layers came out
    # byte-identical.)
    #
    # Against 'layout', which resolves the same 126 to 22 distinct values -- 84 via slot 6,
    # 40 via slot 5, and exactly 2 falling through to the 2-component reading.
    #
    # The slot rule gives them author-shaped numbers instead, and distinct ones:
    #
    #     rec 62 1.50   rec 143 1.28   rec 145 7.68   rec 159 3.00   rec 5043 3.84
    #     rec 5048 1.28   rec 7327 2.44   rec 7332 3.25   rec 7338 3.25   rec 7340 2.44
    #
    # 7327/7340 at 2.44 and 7332/7338 at 3.25 is TWO distinct fields where 'wide' produced
    # one, which is the difference between four colour layers stacking in the same place and
    # two of them landing somewhere else.
    #
    # AND 'wide' IS BARELY NEEDED. With it closed entirely, only TWO of the 126 fail to
    # locate anything (recs 158 and 10170, whose slot holds 0.0 and fails the 1e-3 floor).
    # So it was pre-empting the good rule on 124 records to rescue 2. 'layout' defers to the
    # rule and keeps the 2-component reading for exactly those.
    'distance.param':     ('program', 'block1', 'slot5', 'wide', 'layout'),
    # ARBITRATED, AND 'wide' IS REFUTED -- by the widest margin of anything in this file, and
    # it is the candidate that looks best on a coverage count. `distance` heads the reference
    # packages' blocker table once blur.intensity and nonfinite.fill are open, and 'wide'
    # takes them from 54 of 90 rendered to 74. 'program', 'block1' and 'slot5' unlock nothing
    # at all (54 either way), so it is the only live one.
    #
    # Scored, keyed by assembly AND by reference content so the comparison cannot drift:
    #
    #     usable channels common to both       60
    #       byte-identical                     57
    #       MOVED                               3   Auras basecolor ch0/1/2
    #         +0.937 -> +0.804
    #         +0.865 -> +0.631
    #         +0.945 -> +0.801
    #     newly scoreable                      18
    #       of those, NOT degenerate            0
    #
    # Every one of the 20 outputs it unlocks comes back carrying no picture -- all 18
    # scoreable ones fail the variation test -- and the price is the three best-correlated
    # channels this project has. That is the coverage-versus-correctness trade at its
    # starkest: +20 outputs, -0.13 average correlation on the only channels that were
    # working.
    #
    # `distance` therefore stays unimplemented, and its 25-output heading stays as a
    # heading.
    'distance.invert':    (False, True),
    'distance.mask_edge': (0, 1),
    # WHAT THE SECOND EDGE IS FOR, and the header answers half of it without rendering
    # anything. A distance transform's field is scalar by construction, so a `distance`
    # record whose header says COLOUR is not emitting one -- and the colour has to come
    # from somewhere. Over 444 files (the 437-file corpus plus the 7 reference-shipping
    # packages) the 1,693 two-edge `distance` records take exactly two header shapes:
    #
    #     record greyscale, edge0 greyscale, edge1 greyscale   1,571
    #     record COLOUR,    edge0 greyscale, edge1 COLOUR        122
    #
    # No other combination occurs. Edge 0 is greyscale 1,693 of 1,693 -- it is the mask and
    # never the payload -- and the record's own colour bit equals EDGE 1's 1,693 of 1,693.
    # So the output's width follows edge 1. That much is read from three header bits.
    #
    # WHAT IS DONE WITH IT IS NOT READ FROM ANYTHING, which is why this is a question and
    # not a decode. 'field' is the incumbent: emit the scalar field and ignore edge 1
    # entirely, which is what every `distance` record renders as today and which the 122
    # colour records cannot honour -- they produce one channel against a header asking for
    # four, and refuse. 'nearest' carries edge 1's value at the nearest lit mask pixel
    # (`distance.propagate`) and gates it by the field, so the payload fades out at the
    # radius exactly where 'field' does.
    #
    # THE CENSUS IS EVIDENCE FOR THE WIDTH, NOT FOR THE OPERATION. A candidate that gets
    # the width right can still be the wrong arithmetic, and 'nearest' is one reading of a
    # propagation rather than the only one.
    'distance.propagate': ('field', 'nearest'),
    # RE-ARBITRATED AND THE ORIGINAL REFUSAL STANDS -- but my instrument said the opposite
    # first, and how it was fooled is the part worth keeping. Scored on the wide basis with
    # the degeneracy filter and SIGNED correlation over usable channels only:
    #
    #     field     mean corr +0.2951   MAE 0.1575
    #     nearest   mean corr +0.3089   MAE 0.1570
    #
    # Better on both, driven by Bricks basecolor channels moving -0.237 -> +0.090,
    # -0.347 -> +0.051, -0.199 -> +0.094. On that table 'nearest' wins.
    #
    # THE PICTURES SAY NO, UNAMBIGUOUSLY. Under 'field' Bricks renders crisp geometry --
    # circles, grid lines, embossed rings in basecolor, AO and normal. Under 'nearest' all
    # three are a smeared grey mush with the structure gone. The correlation gain is
    # strongly ANTI-correlated channels drifting toward zero, and a channel at -0.35 going
    # to +0.05 has not become right, it has become featureless.
    #
    # SO THE METRIC HAS A HOLE: mean signed correlation treats |negative| -> 0 as an
    # improvement. The degeneracy filter does not catch it either, because a smeared image
    # keeps enough std and enough distinct values to pass. An anti-correlated channel is
    # evidence of a WRONG picture, not of a missing one, and the way to fix it is to make
    # it correlate positively, not to flatten it.
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
    #
    # BUT IT IS STILL LOAD-BEARING SOMEWHERE ELSE, AND ONLY IN COMBINATION. Bricks
    # Textures_1 record 12193 is a blend with `blendingmode` 2 -- SUBTRACT -- fed by two
    # fxmaps generators, and it heads a 70-record warp accumulator (12193 -> 12194 -> ...
    # -> 12262) that is black end to end. It is black because both operands are solid
    # white and white minus white is nothing.
    #
    # Why they are white: rec 12190 emits THREE patterns, one typeless and two pyramids
    # carrying opacity -1.0. `fx.sizeless` = 'fill' paints the typeless one as a full-cell
    # 1.0; `fx.negopacity` = 'clip' paints the two pyramids as nothing; max-combine lets
    # the fill win outright. rec 12192 the same with five. Two independent defaults, and
    # each one alone is enough to produce the white:
    #
    #     incumbent            12190 1.0000/0.000000  12192 1.0000/0.000000  12193 0.0000/0.000000
    #     sizeless='skip'      12190 0.0000/0.000000  12192 0.7243/0.106242  12193 0.0000/0.000000
    #     skip + negopac='abs' 12190 0.7008/0.106793  12192 0.7243/0.106242  12193 0.0239/0.041758
    #
    # 'skip' alone still leaves 12190 empty, because once the fill is gone its only other
    # patterns are the two the clip discards. So neither key can be arbitrated on this
    # specimen by itself -- the record needs both open before its subtract has two
    # different operands, and a sweep varying one at a time reports both as inert.
    #
    # WHAT THE ACCUMULATOR IS WORTH, measured causally rather than fitted. Seeding record
    # 12262 with a constant and re-rendering graph 004's roughness, whose reference is
    # mean 0.5569 std 0.1101:
    #
    #     12262 = 0.00   ours 0.3105/0.2638   MAE 0.2690   y=0.294x+0.466   r +0.704
    #     12262 = 0.50   ours 0.4721/0.2230   MAE 0.1606   y=0.365x+0.384   r +0.740
    #     12262 = 1.00   ours 0.6138/0.1657   MAE 0.0893   y=0.521x+0.237   r +0.785
    #
    # The MAE improves threefold, our std falls toward the reference's, and the fitted
    # slope walks toward 1. The CORRELATION rising is what makes this causal rather than
    # cosmetic: a constant substitution that only moved brightness and contrast would leave
    # r untouched, so the black operand was destroying structure and not merely level. The
    # values are arbitrary and the trend runs to the boundary, so this locates NO value --
    # it establishes only that black is wrong and which way is right.
    #
    # AND NONE OF IT MOVES A SCORE YET. Bricks overall MAE is 0.1401 incumbent, 0.1401
    # under 'skip', 0.1401 under skip+'abs', 0.1401 under patternsize/branchoffset 'cell',
    # 0.1402 under all four. The revival reaches 12193 and dies again before 12262, which
    # is still 0.0000 under every combination tried. Recorded because the mechanism is
    # established and the remedy is not, and because a later sweep will otherwise re-derive
    # 'both keys are inert on Bricks' from the same one-at-a-time evidence.
    'fx.sizeless':        ('fill', 'skip', 'half', 'quarter'),
    # THE ROOT NODE, asked separately from `fx.sizeless` because it has its own signature
    # and that question is decided the other way. An FX-Map's tree has a root covering the
    # whole canvas, and a Quadrant that subdivides without drawing is `patterntype` 0 --
    # which nibble 2 cannot distinguish, since 0, 1 and 2 all land on the catch-all.
    #
    # The signature is sharp. Over 30 corpus files, 1,177 records emit a pattern that states
    # no patterntype and no patternsize at branchoffset EXACTLY (0, 0):
    #
    #     the corner is (0,0)          1,177 of 1,177
    #     it is the FIRST emission     1,160 of 1,177
    #     exactly one per record       1,098 of 1,177
    #     the record renders flat      1,174 of 1,177   (3 varied)
    #
    # Drawn, it is a full-canvas stamp at the default opacity of 1.0, which is precisely what
    # paints a record white. 'draw' is today's behaviour.
    #
    # PUT TO THE REFERENCE MAPS, AND THEY CANNOT DECIDE IT. The arm is not vacuous -- 125 of
    # 694 fxmaps records in those packages change, and the white count drops from 271 to
    # 146. But on the 7 channels that vary enough to arbitrate, 'skip' is byte-identical to
    # 'draw': mean MAE 0.1090 and mean |corr| 0.4136 either way. Every channel it moves is
    # one whose default render is near-constant.
    #
    # What it adds is Chesterfield `basecolor`, which renders only under 'skip' and is NOT
    # degenerate there -- 331, 216 and 223 distinct values at 16%, 26% and 37% of the
    # reference's std -- correlating at 0.101, 0.156 and 0.145. So this costs nothing
    # measurable and produces more actual picture at weak agreement. Neutral, like
    # `blur.intensity`, and for the same reason: the arbiter runs out before the question
    # does.
    'fx.rootentry':       ('draw', 'skip'),
    # AN 'inherit' CANDIDATE WAS ADDED HERE AND REMOVED, for the reason the retired
    # 'oversize' arm in fxrender gives: a candidate that cannot differ from another is not
    # an arbitration option. The idea was that a pattern stating no size inherits the last
    # one stated in the same table, motivated by the white population's shape -- 1,206 of
    # the 1,369 records that render at exactly 1.0 carry a patternsize on SOME patterns and
    # not others, against 34 of 997 varied records.
    #
    # It renders BYTE-IDENTICALLY: 0 of 694 fxmaps records in the reference packages change,
    # and 0 of 793 over twelve corpus files, despite 2,330 places where a sizeless pattern
    # follows a sized one. The reason is visible in any specimen -- PavingStones rec 161
    # alternates typeless patterns with typed ones whose patternsize is 5.0. Inheriting 5.0
    # instead of defaulting to 1.0 changes nothing, because both already cover the canvas.
    #
    # So the mixed-table signal is real but it is NOT the mechanism: those records are white
    # because the sizes they DO state are oversized, not because of the ones they omit.
    # ARBITRATED AGAINST THE REFERENCE MAPS, AND `fill` HOLDS. This question now looks
    # obviously wrong from the census side -- 1,369 fxmaps records render at exactly 1.0,
    # and a full-cell fill on a typeless entry is what paints them -- so the temptation is
    # to take any of the other three. The references say do not. Scored on the 15 channels
    # ALL FOUR candidates produce (not on each candidate's own denominator, which is the
    # error this file exists to avoid):
    #
    #     candidate   mean MAE   mean |corr|
    #     fill          0.0613      0.3827
    #     skip          0.0617      0.3635
    #     half          0.0617      0.3635
    #     quarter       0.0617      0.3636
    #
    # What the alternatives buy is Chesterfield `basecolor`, 3 channels that render only
    # without `fill` -- and they correlate at 0.103, 0.156 and 0.151, which is a picture
    # carrying almost no structure. What they cost is `roughness`, the one channel in the
    # set with real signal, whose correlation falls from 0.295 to 0.066 while its MAE rises
    # from 0.0193 to 0.0279. Every other channel moves by ~0.001, at noise level.
    #
    # THAT VERDICT WAS WRONG, AND THE TABLE ABOVE IS WHY -- see the correction below.
    #
    # CORRECTION: `fill` DOES NOT WIN; the comparison was carried by degenerate channels.
    # The 15-channel means above include channels whose OWN render is near-constant, and a
    # correlation computed on such a channel is not evidence. Chesterfield `roughness`
    # renders as THREE distinct values with std 0.0023 against the reference's 0.0262, and
    # its r = 0.295 under `fill` -- the largest single term in that 0.3827 -- is three
    # plateaus landing near the reference's levels. Under `skip` the same channel becomes a
    # genuinely varying image, 284 distinct values at std 0.0077, and its correlation falls
    # to 0.066. The number got worse because the picture got real.
    #
    # Restricted to the 7 channels that vary enough to compare under EVERY candidate
    # (uniq >= 20 and our std >= 10% of the reference's):
    #
    #     candidate         mean MAE   mean |corr|
    #     fill               0.1090      0.4136
    #     skip               0.1087      0.4099
    #
    # A tie, not a win. `fill` remains the DEFAULT because it is what the code has always
    # done and nothing here displaces it -- but the reference set cannot presently decide
    # this question, which is a different statement from the one this note used to make.
    #
    # AND THIS IS THE SECOND QUESTION TO FAIL ON THE SAME CHANNEL. `nonfinite.fill`'s note
    # below reports Chesterfield `basecolor` unblocking under every one of ITS candidates
    # and correlating at 0.04-0.10 regardless -- a different question, the same three
    # channels, the same verdict. Two independent arms now say those channels come back
    # carrying no structure, so "Chesterfield basecolor renders" should be treated as a
    # property of that output rather than as evidence for whatever produced it.
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
    # A 9x9 READING OF THE REFERENCE IS A FENCEPOST, and it is worth recording because the
    # arithmetic behind it looks convincing. Counting lit column BANDS in the exported
    # metallic gives 9 -- but the spacing is 256px on 2048, which is 8 cells. The ninth band
    # is the wrapped edge dot appearing clipped at both x=0 and x=2048. So the lattice is
    # 8x8 = 64 dot positions, not 9x9 = 81, and a count derived from the 81 would be five
    # times the coverage the reference carries.
    #
    # THE COMPANION ARITHMETIC IS ALSO WRONG in a way measurement settles. It reasons that
    # 16 stamps of side 0.25 light 16 * 0.0625 = 1.0000 of the canvas against a reference of
    # 0.055, i.e. eighteen times too bright. That assumes each stamp is FULLY lit. They are
    # not: a stamp samples rec29, which is itself lit over 0.403 of its own area. Measured
    # rather than estimated, 16 stamps with the scanner held give metallic lit 0.0469
    # against the reference's 0.0483 -- a 3% difference, not 18x.
    #
    # And the two counts reconcile rather than compete: 16 stamps each carrying rec29's 2x2
    # blob positions is 64 dots, which is the 8x8 the spacing shows. The account closes.
    #
    # A PICTURE TEST FOR THE patternsize ARMS CANNOT REACH THEM ON THIS PACK, and the reason
    # is structural rather than a coverage gap. Measuring the drawn dot -- the blob's size
    # WITHIN rec29 times the stamp's footprint, against the reference dot -- gives on rec34:
    #
    #     reading              s      predicted dot   vs reference (0.0468)
    #     canvas (stored)   0.2500    0.0537..0.0287    1.15x .. 0.61x
    #     cell, 8 axis      0.0312    0.0067..0.0036    0.14x .. 0.08x
    #
    # which reads as decisive for canvas. It is not, because rec34 is not a record the arms
    # touch. `_cell_divisor` fires on Chesterfield recs 92 and 93 ONLY, and those two are in
    # the cones of basecolor, normal, roughness, height and AO -- but NOT metallic. rec34 is
    # in metallic's cone alone.
    #
    # So the dot lattice the picture test can read belongs to the one channel the arms never
    # touch, and the five channels the arms move carry no dot lattice to measure. The two
    # instruments address DISJOINT record sets by construction. They cannot be in conflict
    # here, and neither can corroborate the other: a picture test that arbitrates these arms
    # needs a record that is both in the fired set and feeds a reference with identifiable
    # dots, and Chesterfield has none.
    #
    # BRICKS HAS ONE, AND IT REFUTES CANVAS ON THE FIRED SET. Bricks' normal references ARE
    # lattices -- 111 blobs at 0.0120 of the width with a size cv of 0.281, and 72 at
    # 0.0167 -- and its fired records are in normal's cone. Verified here: all 38 fired
    # records carry patternsize 2.82, and `_cell_divisor` returns exactly sqrt(N) on every
    # one of them (0 of 38 differ), so a per-axis cell count is well defined.
    #
    #     rec     N      psize   divisor   canvas dot   cell dot
    #     619     16     2.82        4       2.82        0.705
    #     328     64     2.82        8       2.82        0.353
    #     612    841     2.82       29       2.82        0.097
    #     334   1024     2.82       32       2.82        0.088
    #     reference normal dots: 0.0120 .. 0.0200 of the width
    #
    # CANVAS IS REFUTED BY THE VALUE, not by a margin: 2.82 as a canvas fraction is a stamp
    # nearly three times the canvas, 141x to 235x the reference dot, and no falloff recovers
    # two orders of magnitude. The cell reading reaches 0.088 on the dense grids -- still 5
    # to 7x large, which is within reach of a profile's lit core being a fraction of its
    # footprint, and that is not modelled by treating the footprint as the dot.
    #
    # THIS DOES NOT CONTRADICT THE rec34 RESULT. rec34's patternsize is 0.25 and these are
    # 2.82: opposite sides of 1.0, where a value below 1 is consistent with a canvas
    # fraction and a value above it cannot be one at all. The fired set is entirely on the
    # impossible-as-canvas side, which is the only way the two measurements could agree.
    #
    # A LEVERAGE CHECK ACROSS THE REMAINING PACKS, run before wiring anything: the sole root
    # of every blocked output in the scored set is one of two arbitrations, and the recovered
    # fxmaps entry table is not among them.
    #
    #     Sandy Stone  output, _1, _2, _3, _4     nonfinite   ONLY
    #     Auras        basecolor                  blur.intensity ONLY
    #     Chesterfield  -- nothing blocked --
    #
    # So `nonfinite.fill` is the last root on five outputs at once and `blur.intensity` on
    # one. A fix for the chainless fxmaps entry table -- recoverable via fx_walk on 3,224 of
    # 3,227 empty-chain records, a genuine decode-integration gap with a known one-place fix
    # -- has ZERO leverage on any scored pack: it is not the last root anywhere. Worth
    # wiring on its own merits eventually; not worth wiring to move a score.
    #
    # AND IT EXPLAINS WHY 'oversize' COULD NOT DIFFER FROM 'cell'. That candidate scaled
    # records whose median patternsize exceeds 1.0, and it was retired as byte-identical.
    # The identity is not luck: the fired set IS the oversize set, because an oversized
    # nominal patternsize is what a record with a full integer lattice has. The symptom
    # threshold was selecting the right population by another route.
    #
    # It stops short of the predicted ~0.40, and the residue is specific: the emitted
    # frameoffsets run -0.375, -0.125, -0.875, -0.625, -1.375, -1.125. They sit on the
    # correct 0.25 lattice, so the pitch is confirmed, but they range outside the unit
    # square, so several stamps land off-canvas -- the `mod 1` the decoded formula specifies
    # is not taking effect here.
    #
    # AND THE `mod 1` WAS NOT MISSING -- the residue was an artifact of how the count was
    # forced. frameoffset is literally slots[26] + slots[12]: the $number grid PLUS the
    # scanner's position. Forcing numberadded to 16 makes the addnode loop sixteen times,
    # and each iteration re-runs the 0x99 body on the shared frame, so slot 12 accumulated
    # sixteen steps and every grid position rode away on top of it. Holding the scanner to a
    # single run while $number varies separates them:
    #
    #                          emissions   rec34 lit   metallic lit
    #     baseline                     1      0.0254         0.0039
    #     n = 16                      16      0.2285         0.0288
    #     n = 16, scanner held once   16      0.4062         0.0469
    #
    # The sixteen offsets become exactly {-0.375, -0.125, 0.125, 0.375} on both axes -- the
    # centred 4x4 grid, every one inside +-0.5 and on canvas. rec34's lit fraction reaches
    # 0.4062 against its own input's 0.403, and metallic reaches 0.0469 against the engine
    # export's 0.0483. The cone is explained: nothing was wrong with the size, the index,
    # the mod, the scanner or the units, and everything was the emission count.
    #
    # SO rec34 HAS TWO POSITION SOURCES and the walk conflates them. The $number grid and
    # the scanner are alternative tilings summed by frameoffset; a $number-grid record needs
    # the scanner run once for its slot initialisation and NOT re-entered per emission.
    #
    # NOTHING IS WIRED FROM THIS. numberadded genuinely evaluates to 1, and the decoded
    # formula ((g-1 mod 2) + g)^2 yields only odd squares, so 16 is unreachable through it
    # and the correct count must still arrive by a path neither side has pinned.
    #
    # THOUGH IT MAY NOT BE MISSING FROM THE FILE, only from the addnode. The structural side
    # searched the 0x18B node, its single program and the record-level FX params and
    # reported the 16 absent by every path -- correct, and it stops one program short. The
    # grid dimension is a HARDWIRED CONSTANT in the placement program, the same one that was
    # decoded as placing at (0.125 + 0.25*($number mod 4), ...), and its constants differ
    # per record:
    #
    #     rec34 prog 530756   0.125  0.25  ...  2.0  3.0  4.0  5.0
    #     rec53 prog 537064   0.125  0.25  ...  2.0  3.0  4.0  5.0
    #     rec86 prog 551884   0.125  0.25  ...  2.0  3.0  4.0  5.0
    #     rec65 prog 542248   0.125  0.25  ...  1.67  2.0        <- no 4.0
    #
    # Three records carry the 4 whose square is the 16 the measurement demands; the fourth
    # does not, and rec65 is exactly the record whose deficit is 5.8 rather than 16. So the
    # count varies per record in the way its coverage does, and it is present as a decoded
    # constant rather than absent from the format.
    #
    # THAT INFERENCE IS WRONG, AND SO IS THE RULE BUILT ON IT. Sweeping rec65's count with
    # its scanner held shows the layout it actually produces:
    #
    #     n     rec65 lit    first offsets
    #     1        0.1377    (-0.377, -0.376)
    #     4        0.3764    -0.377, -0.127, 0.123, 0.373  on x
    #     9        0.7231
    #    16        1.0000
    #
    # Those x offsets are spaced 0.25 -- rec65 lays a 4x4 grid on the SAME pitch as rec34,
    # despite its patternsize being 0.4146 rather than 0.25 and despite its placement
    # program carrying no 4.0 among its constants. So the grid dimension does NOT track the
    # constant list, which kills the per-record reading above, and it does not equal
    # 1/patternsize either, which kills the proposed rule count = (1/patternsize)^2: that
    # would want 2.41 cells for rec65 and the file lays 4.
    #
    # AND THE 1/size^2 AGREEMENT WAS NEVER INDEPENDENT EVIDENCE. Coverage of one stamp is
    # size^2 times the input's own lit fraction, so IF the engine tiles fully then the
    # deficit is 1/size^2 identically, for any mechanism whatever. The number appearing
    # three times was one measurement restated, not three confirmations -- and building a
    # count rule on it reproduces the assumption it came from. rec34 matching its input's
    # lit fraction at n=16 is real, but it works because size 0.25 tiles a 4-grid exactly;
    # rec65 at n=16 saturates to 1.0000 because 0.4146 stamps on a 0.25 pitch overlap.
    #
    # AND THE "rec65 LACKS THE 4.0" WAS A DISPLAY BUG IN MY OWN PROBE. It does not lack it.
    # Both placement programs are 347 lines and both contain `v10 = 4.0` at line 19, with a
    # 0.25 pitch at lines 24/30/36. The constant scan that reported otherwise truncated its
    # output to twelve values, and rec65 has twelve constants below 4.0 where rec34 has ten,
    # so the 4.0 fell off the end of a list, not out of the file. A slice in a debug print
    # became a finding, and it was handed onward as one.
    #
    # SO THE COUNT IS LOCATED, by two methods that are genuinely independent of each other
    # and of the 1/size^2 identity. The structural side diffed the two programs: the grid
    # computation is byte-identical, `floor($number / 4)` for the rows and a 0.25-step
    # column wrapping at 1.0, and the ONLY differences between the records are three
    # constants feeding patternsize. Separately, sweeping rec65's count here put its stamps
    # on a measured 0.25 pitch. A read of the bytes and a render measurement agree that the
    # grid is 4x4 = 16 in both records and that it is size-independent.
    #
    # What remains is only the path: by which route the engine turns that hardwired divisor
    # into the emission loop bound, given this walk uses numberadded and numberadded is the
    # aspect-amount for these records. The VALUE and its SOURCE are pinned; the derivation
    # is not.
    #
    # Both arms above remain measurements, not fixes -- they say what the answer looks like,
    # not what produces it.
    # WHERE A $number-GRID RECORD'S EMISSION COUNT COMES FROM. The walk takes its loop
    # bound from `numberadded`, and for these records that is an amount rather than a bound
    # -- Chesterfield's reads only the aspect slot and degenerates to 1 on a square canvas,
    # and its decoded form yields only odd squares so it can never produce the 16 the layout
    # needs. The grid is hardwired in the placement program instead, as the N in
    # `floor($number / N)`, and 'divisor' reads it from there and emits N^2 patterns with
    # the scanner held to one run.
    #
    # Two limits it is worth being explicit about. N^2 assumes rows equal columns, which is
    # true of every specimen either side can see but is not established; a record whose
    # column wrap differs from its row divisor would need width x height. And the divisor is
    # matched semantically on `$number / N` rather than at the instruction offset where it
    # was located, because that offset is verified on four records sharing one program
    # almost byte-for-byte.
    # SCORED ON CHESTERFIELD, and it is the largest correction this pack has had since the
    # levels gamma. Overall MAE 0.0856 -> 0.0557, and `basecolor` goes from not rendering at
    # all to a scored output:
    #
    #     output      numberadded        divisor        reference std
    #     AO         0.0633/0.0160   0.0279/0.0824         0.0645
    #     basecolor    not scored    0.0553/0.0536         0.0662
    #     height     0.2480/0.1064   0.0623/0.1316         0.0970
    #     metallic   0.0464/0.0199   0.0203/0.1181         0.1733
    #     normal     0.0742/0.0613   0.0881/0.1512         0.0722
    #     roughness  0.0193/0.0025   0.0160/0.0147         0.0262
    #
    # Five of six improve and height improves fourfold, from the worst channel in the pack
    # to among the best. The contrast moves with it: metallic 0.0199 -> 0.1181 against a
    # reference 0.1733, AO 0.0160 -> 0.0824 against 0.0645, where before every one of them
    # was flat by comparison.
    #
    # `normal` GETS WORSE, 0.0742 -> 0.0881, and it is the one to watch rather than to
    # explain away: its std goes 0.0613 -> 0.1512 against a reference of 0.0722, so it is
    # now over-textured by as much as it was under-textured before. AO overshoots slightly
    # too. Sixteen stamps where there was one is a large change and some channels have
    # clearly gone past the mark, which is what a real correction with a remaining error
    # looks like rather than a tuned one.
    #
    # CORPUS-CHECKED SINCE, on both of its stated limits. The square assumption is confirmed
    # POSITIVELY rather than by absence of a counterexample: over every record where both
    # the row divisor and the column pitch can be extracted, rows equal columns exactly --
    # 49 of 49, across N of 1, 2, 3, 5, 6, 8, 10, 11, 12, 16, 18 and 32. And N varies
    # genuinely per record: over 80 files the divisors run 2, 3, 4, 5, 6, 7, 8, 10, 11, 12,
    # 13, 14, 16, 18, 20, 24, 25, 30, 31, 32, 35, 39, 42, 50, 64. So `grid_width` reads a
    # real parameter and N^2 is node semantics, not the 4 Chesterfield happens to carry.
    #
    # The extraction resolves on 49 of 72 scanner-and-grid records; the other 23 use a
    # placement structure the reader does not catch, which is unparsed rather than
    # contradicted. And the reader's upper bound turns out to fall in a gap the corpus
    # leaves -- see `grid_width`, where the two populations are separated by a factor of two
    # of empty space.
    #
    # `normal`'s REGRESSION IS NOT A DOUBLE-COUNT, and the graph supplies the control that
    # shows it: rec121 (normal) and rec120 (height) share their source, rec119. Height
    # improved fourfold under this candidate, so rec119's level and coverage are right with
    # sixteen stamps -- if any path here assumed a single stamp or double-counted a blend,
    # height would have overshot by the same factor and it did the opposite. Normal is the
    # SLOPE of that same field, and a derivative amplifies high frequency: height sits at
    # 1.36x the reference contrast and normal at 2.09x, which is that excess passed through
    # a derivative.
    #
    # SO IT IS STAMP-EDGE HARDNESS, PARTLY -- tested rather than assumed, by sweeping the
    # profile these typeless stamps are drawn with:
    #
    #     profile      overall   normal MAE/std   height MAE/std
    #     rect          0.0557   0.0881/0.1512    0.0623/0.1316
    #     disc          0.0591   0.0772/0.1435    0.0908/0.1179
    #     cone          0.0544   0.0814/0.1328    0.0677/0.1141
    #     paraboloid    0.0530   0.0859/0.1405    0.0316/0.1222
    #     bell          0.0567   0.0925/0.1457    0.0546/0.1301
    #     gaussian      0.0605   0.0903/0.1468    0.0990/0.1293
    #     reference std                   0.0722           0.0970
    #
    # Softening does pull normal's contrast down, 0.1512 to 0.1328 at its best, which is the
    # predicted direction. It does NOT close the gap: the best profile still leaves normal
    # at 1.84x the reference, so edge hardness is a contributor and not the whole residual.
    # And no profile is free -- `disc` gives the best normal MAE and costs height half its
    # gain.
    #
    # RE-RUN ON TWO PACKS, AND THE TIE DOES NOT BREAK. The argument for re-running was that
    # a verdict of "no member wins outright" was reached on one specimen, and Bricks is now
    # a confirmed second scoring pack with 18 grid records. Scored on both, all five outputs
    # present in each:
    #
    #     profile      Chesterfield   Bricks
    #     rect               0.0646   0.1065   <- best on Bricks
    #     disc               0.0678   0.1076
    #     paraboloid         0.0639   0.1155   <- best on Chesterfield
    #
    # The packs disagree. Chesterfield prefers paraboloid, Bricks prefers rect, and neither
    # margin is large. So a second specimen does not resolve it: the recorded verdict stands
    # and is now better evidenced rather than overturned.
    #
    # AND THE SOFT PROFILES BREAK THE RENDER, which is why they are absent from that table
    # and why a naive reading of the sweep would have inverted the answer. On Bricks,
    # `cone`, `bell` and `gaussian` each score 0.0292 -- apparently far the best -- while
    # scoring ONE output instead of five, with 50 records failing to render outright. The
    # number improves because four outputs vanish. Any sweep over this key has to report the
    # AND THE FAILURE IS FIVE RECORDS, NOT FIFTY -- fifty is the OUTPUT-level cascade count,
    # which is not the same thing and was first reported as though it were. The root
    # failures under `cone` at max_dim 96 are five records: 326, 2744, 5211, 7643 and 10330,
    # all `pixelprocessor`, all class 0x0099, all producing non-finite values on 100% of
    # samples. They cascade into 8,518 lost records and the 50 lost outputs.
    #
    # It is resolution-dependent, which is how a first check missed it: at max_dim 64
    # nothing fails and both profiles render an identical record set. So softening does not
    # break a structural class -- it pushes five pixelprocessors over an edge that exists
    # only at some resolutions, which has the shape of a divide by a coverage that has
    # reached zero. Same 0/0 family as QUESTIONS['nonfinite.fill'], reached from the profile
    # side rather than from an empty upstream.
    #
    # CONFIRMED BY EXPERIMENT, and it makes the soft arms comparable for the first time.
    # The structural side reads those five as a per-pixel AUTO-LEVELS -- (L - lo)/(hi - lo)
    # with lo and hi taken from an input's own channel bounds -- so a flattened field gives
    # hi == lo, the range is zero, and every sample is 0/0. That predicts nonfinite.fill
    # should resolve them independently of the profile, and it does:
    #
    #     profile   nonfinite.fill    scored outputs   overall
    #     rect      (none)                         5    0.1065
    #     rect      0.5                            5    0.1065
    #     cone      (none)                         1    0.0292
    #     cone      0.5                            5    0.1213
    #
    # `rect` is untouched by the fill, `cone` goes from one output to five, and the fill is
    # doing exactly what the mechanism says. So softness is NOT blocked by these records --
    # their 0/0 is a pre-existing degeneracy the profile merely reaches.
    #
    # And compared fairly, cone still LOSES: 0.1213 against rect's 0.1065. Its 0.0292 was
    # entirely the four missing outputs, which is now demonstrated rather than inferred.
    #
    # scored-output COUNT beside the mean, or a profile that destroys the render reads as a
    # profile that fixes it.
    #
    # WORTH NOTING SEPARATELY: this question used to be undecidable. Scored before the count
    # was fixed, no member of fx.typeless_profile won outright. With sixteen stamps instead
    # of one, `paraboloid` now beats `rect` overall (0.0530 against 0.0557) and takes height
    # to 0.0316 from 0.0623. An arbitration can be unanswerable because an upstream value is
    # wrong, and answerable once it is fixed -- which is an argument for re-running old
    # inconclusive sweeps after any correction of this size, not only the ones it obviously
    # touches.
    # A SECOND PACK CONFIRMS IT, AND IT IS NOT THE ONE THAT WAS EXPECTED. The structural
    # side offered Sandy Stone rec27 (N = 5) as the discriminating specimen and named
    # Bricks, RoofTiles and Auras as negative controls with no scanner fxmaps at all. The
    # controls are half right and Bricks is not one of them:
    #
    #     Bricks         18 records with a readable grid, widths {2: 11, 4: 2, 25: 5}
    #     Chesterfield    4 records, all width 4
    #     Sandy Stone     1 record,  width 5
    #     RoofTiles       none        Auras  none
    #
    # So Bricks scores it, at three different N and eighteen records:
    #
    #     arm            overall      AO   height   normal  roughness  emission
    #     numberadded     0.1239  0.1190   0.3503   0.0344     0.2370    0.0140
    #     divisor         0.1065  0.1040   0.2154   0.0502     0.2152    0.0292
    #
    # Overall improves, height improves by a third, AO and roughness improve, and `normal`
    # regresses -- the same signature as Chesterfield, at different grid widths, in a
    # different package by a different author. That the regression REPRODUCES is what makes
    # the derivative-amplification account credible rather than a Chesterfield story.
    #
    # Sandy Stone turns out not to score it: rec27 feeds five outputs and none of them
    # renders yet, so its only scored channel is a metallic the record does not touch. It
    # remains a valid extraction check -- grid_width returns 5 there, a third distinct value
    # -- and not a scoring one. RoofTiles and Auras are byte-identical under both arms,
    # which is the control working.
    #
    # THE BRICKS COUNT IS DISPUTED AND VERIFIED HERE, so a later reader knows which number
    # this rests on. The structural side reports the committed `grid_width` returning 2
    # records for Bricks (rec84 width 5, rec263 width 2) and only 8 programs referencing
    # sysvar(10). Re-run against the committed function: 18 records in EACH of the pack's
    # two assemblies, 191 fxmaps each, widths {2: 11, 4: 2, 25: 5}, at records 553, 2465,
    # 2470, 2476, 2485, 2491, 2971, 4917 and on -- and 18 DISTINCT programs supplying them,
    # one apiece, so it is not one program counted many times either. No record 84 or 263
    # appears, and no width 5 exists anywhere in this pack.
    #
    # The two readings do not overlap at all, which means they are not the same file rather
    # than the same file counted differently.
    #
    # RESOLVED, AND IT WAS THE FILE: there are THREE Bricks.sbsasm in the tree. The disputed
    # reading came from `tiny/x_textures__BricksSubstance/.../Bricks.sbsasm` -- 75 fxmaps,
    # 2 grids at widths 2 and 5 -- which is a different author's brick material entirely.
    # Running the committed `grid_width` on the reference pack's path reproduces 18 on both
    # of its assemblies. So the detector agrees with itself and the disagreement was a glob
    # picking the wrong specimen, which is the same hazard that cost this project a day on
    # graph 003's authorship. Worth keeping the record of it: a count that cannot be
    # reconciled by any reading of the same file usually means it is not the same file.
    # HOW emboss's INTENSITY ENTERS. The filter is a directional relief: sample the gradient
    # input at `pos` and at `pos + offset`, and add the difference to the base image. Two of
    # its three terms are decoded and fixed. The OFFSET is resolution-independent -- the
    # record's first program writes a texel COUNT into slot 2, 0.005859375 * (W, H) * (1,-1),
    # and the texel SIZE (1/W, 1/H) into slot 0 which nothing else reads, so their product is
    # a constant 0.005859375 in UV at a 45-degree (+x, -y) light. The EDGES are [base,
    # gradient]: the second is a shuffle or a blur, a single-channel relief source, the first
    # is the image the relief lands on.
    #
    # What is not decoded is the third term. The second program returns 0.1 * 2048 / size --
    # 0.1 calibrated to a 2048 reference and then scaled by resolution -- and the scaling
    # lives in the built-in rather than in any program, so nothing in the bytes says whether
    # it multiplies the relief or compensates the sampling. Those differ by 8x at the
    # resolutions this renderer scores at, which is large enough to make a wrong choice look
    # like a mediocre channel rather than a broken one.
    #
    #   'program'   use the program's own value, 0.1 * 2048 / size
    #   'reference' use the 2048-calibrated 0.1 unscaled, i.e. treat the scaling as
    #               compensating the sampling rather than amplifying the relief
    # AND NOTHING SCORES IT YET, which is why both arms are still here. Implementing emboss
    # removes it from RoofTiles' root list -- 5 emboss roots gone, one record now rendering
    # and the other four cascade-blocked from above -- but the pack still scores ONE output,
    # because the roots that actually gate it are elsewhere:
    #
    #     shuffle stores no weight vector      15
    #     blur intensity: slot not plausible    8
    #     fxmaps: no readable table entries     5
    #
    # So emboss was 5 roots and 0 leverage: removing it unblocks no output because the
    # shuffle roots sit in the same cones. The arms are indistinguishable at present and
    # both are recorded rather than one being picked -- the 8x between them is exactly the
    # kind of thing that would score as a mediocre channel rather than a wrong one, and
    # there is no channel to score it on.
    #
    # The one record that does render comes out at mean 0.9998, std 0.0011 -- nearly flat --
    # which is not evidence the implementation is right or wrong, only that its inputs are
    # degenerate too.
    #
    # GREEN INVERSION DOES NOT EXPLAIN THE normal REGRESSION -- checked, because another
    # session found Bricks' normal green-inverted and that is the pack the regression was
    # measured on. Crossing the two keys:
    #
    #     pack          gridcount      inversedy    overall   normal
    #     Bricks        numberadded    ignore        0.1559   0.0344
    #     Bricks        numberadded    word1bit2     0.1554   0.0330
    #     Bricks        divisor        ignore        0.1291   0.0502
    #     Bricks        divisor        word1bit2     0.1275   0.0450
    #     Chesterfield  numberadded    either        0.0871   0.0790
    #     Chesterfield  divisor        either        0.0646   0.1170
    #
    # Inversion helps Bricks a little and leaves Chesterfield untouched -- consistent with
    # its being one author's convention on three assemblies of one package. But the
    # regression SURVIVES it on both: 0.0330 -> 0.0450 with the inversion corrected, and
    # 0.0790 -> 0.1170 where the inversion does not apply at all. So the two effects are
    # additive and independent, and the blocker is real rather than an artifact of a
    # mis-signed channel.
    #
    # Note also that Chesterfield's normal reads 0.1170 here at max_dim 96 against 0.0881 at
    # 128. A derivative channel is resolution-sensitive, which is what the edge-hardness
    # account predicts, and it means any figure for this channel has to carry its resolution.
    #
    # THE LESSON GENERALISES, AND CHECKING IT FIRST IS CHEAP. A root only has leverage if it
    # is the LAST one in its cone; counting roots ranks by how often a cause appears, not by
    # what removing it would free. Listing every distinct root kind per failing RoofTiles
    # output:
    #
    #     height      shuffle 2, blur 1, fxmaps-empty 1
    #     AO          shuffle 2
    #     roughness   shuffle 4, blur 3, fxmaps-empty 1
    #     normal      shuffle 2, blur 1, fxmaps-empty 1
    #     basecolor   shuffle 5, blur 4, fxmaps-empty 2
    #
    # Every output is blocked by `shuffle`, and `fxmaps-empty` never appears without it. So
    # implementing the second, chainless fxmaps encoding would unblock ZERO outputs here --
    # the same trap emboss fell into, caught before the work rather than after. AO is blocked
    # by shuffle ALONE, so that one key unblocks a channel by itself; shuffle plus blur would
    # take height and normal as well.
    #
    # Which puts this whole pack behind the grayscale-default shuffle, and that is the
    # principled refusal -- unavailable on all three avenues, record, sources and manifest.
    # RoofTiles may simply not be scoreable, and the ordering says no amount of fxmaps or
    # emboss work changes that.
    'emboss.intensity':   ('program', 'reference'),
    'fx.gridcount':       ('numberadded', 'divisor'),
    'fx.scanner':         ('once', 'loop'),
    # THE SAME QUESTION FOR THE GATE. `fx.scanner` covers the 0x99 STEPPER; the 0x89 gate is
    # handled as a one-shot conditional -- run `switch`, walk on if true. But a gate's
    # program is not always a pure predicate. ChesterfieldSofa records 331 and 333 carry one
    # that ADVANCES a position and THEN tests it: instructions 29-32 read slot 14, add a
    # step and write it back, and 41-58 compare the result against a rectangle
    # (`x >= s0.x and x <= s0.y - 0.5 and y >= s0.z and y <= s0.w - 0.5`). Run once that
    # emits a single stamp; run until the predicate fails it lays a row.
    #
    # Both records render flat WHITE today, and their difference -- record 334 is
    # `subtract(332, 333)` -- is therefore flat BLACK, which is the input all eight of that
    # file's directionalwarps take. The seams missing from its basecolor are drawn by that
    # dead chain.
    'fx.gatescan':        ('once', 'loop', 'filter'),
    # HOW OVERLAPPING PATTERNS COMBINE. fxrender's docstring lists this among "assumptions,
    # none of them from the format": overlaps combine with `max`. That choice makes a
    # NEGATIVE opacity inert -- max(canvas, negative) is the canvas -- and negative opacities
    # are not noise: ChesterfieldSofa record 331's only two drawn patterns both carry
    # opacity -1.0, and the record renders solid white because its typeless fills win the
    # max and nothing can carve them back. 'add' lets a negative subtract; 'over' composites
    # by coverage.
    'fx.combine':         ('max', 'add', 'over'),
    # WHAT A NEGATIVE OPACITY MEANS. `splat` clips opacity to [0, 1], so a pattern carrying
    # -1.0 draws NOTHING -- and fxrender's own census found 1,195 such patterns in 20 files,
    # 0.6% of them, which it read as too few to be a systemic misread. On ChesterfieldSofa
    # record 331 they are not a corner: BOTH of its drawn patterns carry -1.0, so under the
    # clip the record has nothing but its typeless full-cell fills and renders solid white.
    # 'signed' passes the value through so a negative can subtract (which needs
    # `fx.combine` to be something max cannot be); 'abs' takes the magnitude.
    'fx.negopacity':      ('clip', 'signed', 'abs'),
    # WHAT A GENUINELY ZERO-WIDTH levels DOES. Where levelinlow equals levelinhigh the
    # transfer has no width, and the branch currently reads it as a STEP: everything at or
    # above the point maps to out_high, everything below to out_low. That is the arithmetic
    # limit of a ramp as its width goes to zero, and it was the right correction to make
    # against substituting a span of 1.0.
    #
    # THE ENGINE APPEARS NOT TO DO IT. Bricks graph 004's `emission` is the clean specimen,
    # because it is four isolated dots on black and nothing else. rec12578 is a levels with
    # both ends stated at 0.051, fed by rec7369, a uniform holding the red (0.500, 0.111,
    # 0.111). Every one of those channels is above 0.051, so the step sends all of them to
    # 1.0 and the dots come out WHITE. The engine's exported emission is red -- R 0.6255,
    # G 0.1674, B 0.1555 where lit -- which is rec7369's colour, not a saturation of it.
    #
    #   'step'      today's reading: a hard threshold at the degenerate point
    #   'identity'  pass the input through unchanged when the range is zero-width
    #
    # A step cannot preserve a hue and the reference plainly does, so identity is the
    # candidate the picture suggests. It is a candidate rather than a fix because the step
    # is a defensible limit and because 116 records corpus-wide state both ends equal -- a
    # population wide enough that one specimen should not decide it.
    # WHAT LOOKING AT THE WHOLE PACK SHOWED, recorded because the numbers do not say it and
    # the next reader should not have to re-render to find out. Bricks Textures_1 has five
    # graphs; under current defaults, side by side with the engine's exports:
    #
    #     004, 005   geometry essentially right -- medallions, rings, grid and layout all
    #                land on the engine's; what is wrong is colour
    #     002        a lattice IS drawn, but ours is a square grid where the engine's is an
    #                offset/hex packing, and the engine's is denser
    #     003        sparse: a few rectangles and stray marks where the engine has a full
    #                running-bond brick wall
    #     001        FLAT. Solid brown basecolor, featureless normal, uniform roughness and
    #                height, near-white AO, against a fully detailed stone-block reference.
    #                The same total-collapse shape graph 003 had before, on a different graph
    #
    # AND A SYSTEMATIC WARM CAST ON basecolor IN ALL FIVE. Channel means, ours against the
    # engine's:
    #
    #     graph   ours R/B   engine R/B
    #     001         2.58         0.85
    #     002         1.86         0.93
    #     003         3.22         1.52
    #     004         2.28         1.18
    #     005         2.78         1.15
    #
    # Ours runs roughly twice as warm on every graph. It is NOT a channel swap -- that would
    # put our R/B below 1, and it is above 1 everywhere -- so it is a consistent
    # multiplicative bias in the red-to-blue balance, shared across five graphs that
    # otherwise differ completely. Five independent graphs failing the same way is one
    # mechanism, not five, and it is the largest thing visible that no MAE column names.
    'levels.zerospan':    ('step', 'identity'),
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
    #
    # THOUGH THE 63 MISFIRES ARE NOT THE SHIPPED GUARD'S. That table was built with a
    # hand-written span classifier, and `_cell_divisor` does not select the same set -- it
    # additionally requires every pattern to carry a branchoffset and the span to be an
    # exact integer of at least 1. Measured against the guard itself over 50 files: it
    # scales 219 records, and NONE of them calls rand, NONE is a $number-grid. The static
    # exclusions the structural side proposed -- never scale a rand-scatter, never scale a
    # grid -- were implemented and removed zero records, so they are redundant against the
    # shipped code and were reverted rather than kept as cost without effect.
    #
    # The lesson is narrower than the numbers: a proxy for a guard is not the guard, and a
    # misfire rate measured on the proxy says nothing about the code. The unresolved half
    # stands -- scaling is still unvalidated on the residual population -- but the specific
    # 63-scatter defect recorded above never existed in what actually runs.
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
    # THE THIRD COORDINATE, and the one the other two arms leave behind. `splat` scales
    # branchoffset under `fx.branchoffset` and patternsize under `fx.patternsize`, and
    # NOTHING scales frameoffset -- so "everything is in cell units" has never actually been
    # testable, only two thirds of it.
    #
    # It matters because frameoffset is what carries a DISPLACED PAIR. ChesterfieldSofa
    # records 92 and 93 are the same 25-pattern 5x5 lattice with frameoffset exactly negated
    # ([0.1102, -0.0591] against [-0.1102, 0.0591], and so on for all 25); record 94 is
    # `levels(92)` with leveloutlow 0.5, giving 0.5 + A/2, and record 95 subtracts 93 at
    # opacity 0.5, giving 0.5 + A/2 - B/2. That is a relief filter: it produces the sofa's
    # tufting from the difference between two displaced copies, and it produces NOTHING if
    # the two copies are the same.
    #
    # Ours are nearly the same, because patternsize is 2.82 -- almost three canvases -- and
    # displacing a blob that large by 0.11 changes it hardly at all:
    #
    #     scaling                     |A - B| max    record 95 std
    #     as-is                          0.0066         0.000572
    #     all three by 1/5               0.2518         0.055014
    #
    # `_cell_divisor` already returns exactly [0.2, 0.2] here -- the branchoffset span is
    # -2..+2, five cells per axis -- so the divisor is not in doubt, only which quantities
    # it applies to.
    'fx.frameoffset':     ('canvas', 'cell'),
    # ARBITRATED ON THE REFERENCE PACKAGES, AND REFUTED ON STRUCTURE. `fxrender`'s note says
    # this arm left two specimen records byte-identical because `_cell_divisor` declined
    # them; over the reference packages as a whole it is NOT vacuous -- 97 of 694 rendered
    # fxmaps records change -- so it can be scored, and it was:
    #
    #     candidate   mean MAE   mean |corr|
    #     canvas       0.0613      0.3827
    #     cell         0.0595      0.3533
    #
    # MAE PREFERS `cell` AND CORRELATION REFUSES IT, which is the exact split refcompare's
    # affine column was added to make visible. The MAE gain is almost entirely Auras
    # basecolor ch0 (-0.0120) and ch1 (-0.0231), and those same two channels lose structure:
    # correlation 0.937 -> 0.820 and 0.865 -> 0.635. Correlation is scale-invariant, so a
    # fall in it is structural damage, while MAE is not -- and Auras basecolor is the known
    # gain case (fit y = 0.536x). Shrinking every pattern dims the render, which flatters a
    # too-bright image on MAE while making the picture itself worse.
    #
    # Adopting on MAE alone would have taken it. It stays `canvas`.
    #
    # AND THIS VERDICT SURVIVES THE DEGENERATE-CHANNEL CORRECTION that overturned
    # `fx.sizeless`'s -- it is in fact stronger under it. On the 7 channels that vary
    # enough to arbitrate, 'canvas' scores mean |corr| 0.4136 against 'cell' at 0.3578,
    # a wider gap than the 0.3827/0.3533 measured over all 15. The structural loss is on
    # Auras basecolor, which is one of the few channels in the set that is not degenerate,
    # so removing the near-constant channels does not soften it.
    #
    # AND IT IS NOT THE WHITE RECORDS' CAUSE: 271 fxmaps records render at exactly 1.0 in
    # these packages under BOTH candidates. Whatever the 97 records it moves are, the white
    # population is not among them, so this question and the white one are separate.

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
    # THE 0x08 ENTRY FAMILY: A POSITION WITH NO SHAPE. Splitting entry tags by low byte
    # (see FORMAT-NOTES) isolates 430 entries that occur at nibble 0 and nowhere else and
    # never state a patterntype. Their layout carries ONE program -- `branchoffset` -- and
    # nothing that says what to draw or how big. An entry that states only where it is
    # looks like a marker rather than a draw, and drawing it is what covers a canvas with
    # full cells.
    #
    # This is narrower than `fx.sizeless`, which skips ANY typeless sizeless pattern
    # regardless of family. That question was refused on ChesterfieldSofa partly because
    # skipping the fills let oversized STRIPS through, which smeared its roughness -- a
    # side effect of the fills' removal rather than of the fills themselves.
    #
    # SCORED AND REFUSED, and it fails the same way the broader question did. Over the
    # reference packages, 12 usable channels: mean +0.7997 -> +0.7910, nothing gained or
    # lost, and the movement is
    #
    #     roughness ch0     +0.854 -> +0.743
    #     basecolor ch0     +0.667 -> +0.669
    #     basecolor ch2     +0.446 -> +0.449
    #
    # Two thousandths of basecolor against a tenth of roughness. So the marker reading may
    # well be right about WHAT these entries are and it is still not an improvement,
    # because what the fills are covering is worse than the fills.
    #
    # AND THE OBVIOUS PAIRING DOES NOT RESCUE IT. If the fills merely hide oversized
    # strips, skipping them plus shrinking the strips should fix both. Shrinking
    # patternsize globally by 2, 4, 7, 10 and 20 takes the mean to 0.379, 0.236, 0.197,
    # 0.203 and 0.174 -- it destroys the tufting lattice `fx.gridcount` established, whose
    # sizes were already right. That experiment scales correct sizes along with the
    # oversized ones and so cannot test the hypothesis; a narrower one would have to.
    'fx.markers':         ('draw', 'skip'),
    # NIBBLE 0 IS NOT ONE POPULATION -- and a candidate for it was added here and REMOVED,
    # because it renders byte-identically: 0 of 1,296 fxmaps records change. The structural
    # finding is kept in FORMAT-NOTES; the lever is not, per the same rule that retired
    # fxrender's 'oversize' arm.
    'fx.typeless_profile': ('rect', 'disc', 'cone', 'paraboloid', 'bell', 'gaussian'),

    # HOW FAR `normal`'s intensity fallback MAY SCAN. 'scan' is the incumbent: eight words
    # from the layout start, take the first that reads as a plausible float. 'derived'
    # stops it at the slot `param_slots` derives, `start + 1 + bit7 + bit11`.
    #
    # THE AGREEMENT BETWEEN THEM IS NOT THE EVIDENCE, and an earlier note in this project
    # treated it as though it were. Over 1,379 corpus `normal` records:
    #
    #     rule slot holds a plausible value       968     scan picks that exact slot  968
    #     rule slot holds a denormal or zero      390     of which the scan reaches
    #                                                     further and finds something  68
    #                                                     and finds nothing           322
    #
    # 968 of 968 is agreement between the CHALLENGER and the INCUMBENT. It measures how
    # little would change, not whether either is right -- two readings that are wrong
    # together agree perfectly. What it does establish is that the window never fires
    # early: slots between the start and the derived slot hold nothing plausible, so the
    # two arms can differ ONLY on the 68.
    #
    # THE 68 ARE WHERE THE EVIDENCE IS, scored by the instrument this file already uses
    # for `blur` -- two readings of one parameter must have two agreeing distributions,
    # against source declarations as the third, independent instrument. `normal` declares
    # intensity p50 4.5, range -0.05..100, commonest 10, 20, 0.25, 5, 3, 0.5, 16.
    #
    #     population                       n     p50    in range   IS a declared value
    #     backed by the derived slot     968    12.0      93.2%          76.8%
    #     derived slot says NON-value     68     8.5      72.1%          35.3%
    #
    # Same scan, same filter, split only by whether the derived slot corroborated it. The
    # backed population is 76.8% EXACT declared values; the overriding population is a
    # third of that, and its members include -237.816, -77.22, -32.06, 96.0772, 105.469,
    # 305.965 and 300.0 exactly ten times. Long mantissas are not author-typed numbers.
    # Where the derived slot says no baked value is stored, the scan reaches six more
    # words and finds a different quantity -- which is what `param_slots` already reports
    # for `blur`: "where bit 12 says none is stored the same rule lands on something that
    # is not one. That is what an absent value looks like."
    #
    # WHY THIS IS NOT SIMPLY ADOPTED. 35.3% of the 68 ARE declared values, so closing the
    # window drops perhaps two dozen good readings to suppress rather more bad ones, and
    # that is a coverage-versus-correctness call this file exists to hold open rather than
    # settle by preference. `normal` also pairs only ONCE under `param_slots` containment
    # (SubstanceDesignerPractice rec 362, 2.01 at slot 4, cls 0x0319, which the rule
    # predicts) -- one specimen is corroboration, not verification, and the 38-of-38 was
    # measured on six OTHER filters. The distributional split is the case for 'derived';
    # the single pairing is not.
    # AND THE REFERENCE CORPUS CANNOT SETTLE IT, which is stated here with its cause rather
    # than left as a bare null. Scored under {'blur.intensity':'program',
    # 'distance.param':'layout', 'nonfinite.fill':0.5} over every package shipping exported
    # maps, both arms give mean MAE 0.0904 across 27 paired channels and ZERO channels move.
    #
    # That is not the two arms agreeing. Of the 72 records where they differ, 68 are in
    # corpus files no reference package contains, and the remaining 4 sit inside a
    # reference package but feed no paired output's cone. The instrument is silent because
    # nothing it scores depends on the choice -- so the distributional split above is the
    # only evidence there is, and the default does not move on it alone.
    'normal.intensity': ('scan', 'derived'),
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
