#!/usr/bin/env python3
"""The record as the renderer sees it: every structural read from the walk.

`render.py` asks a different question in every filter branch -- `rec.named_parameters`
here, `rec.matrix` there, `cls_pair_slot(rec, 28)` in a third, a by-width probe over
`rec.filter_programs` in a fourth -- and each of those routes through its own table or
value test. This module asks ONCE, structurally, and every filter reads the answer by
NAME.

The one thing a walk cannot supply is what a field MEANS, so that is the only table here:
`W1_PARAMS` and `CLS_NAMES`, (filter, mask) -> name and baked width. Everything positional
is derived -- WHICH parameters are present and whether each is baked or a program from the
w1 mask, HOW WIDE each is from the manifest's type legend, and WHERE the group ends from
`decompose`'s header length. A name legend and a slot legend are different kinds of thing:
a slot legend goes stale when a neighbouring field appears or disappears, and a name legend
cannot, because it never mentions a position.

WHAT THIS FIXES, measured on `Rokviz japanese fabric 8` -- the specimen with no exposed
colour parameters, so a mismatch cannot be an author's tweak:

    record 34   levels, 7 words, no inherited size slot
                LAYOUTS memo            no key -- reads as an identity levels
                decompose.named_params  levelinlow = 4.6e-44, its own `start` rule
                                        counting back from `prog` onto the INPUT EDGE
                this module             levelinlow 0.1375, levelinhigh 0.1375,
                                        leveloutlow 1.0, levelouthigh 0.0

    That record is an INVERTED HARD THRESHOLD -- in_low == in_high with the output range
    reversed -- and it is the mask that decides which of the two palette branches is the
    ground and which the motifs. Read as an identity it exchanges them, which is the
    "red/teal exchange" FORMAT-NOTES records as an open question with two candidate causes
    eliminated. Reading the w1 mask straight takes basecolor from -0.926 / +0.331 / +0.861
    against the package's own export to +0.976 / +0.949 / +0.907, roughness from -0.475 to
    +0.958 and ambient occlusion from -0.331 to +0.970.

    Record 68 (roughness) is the same shape: four parameters the memo has no key for. And
    `Do Not Enter` record 4 is the third shape: a four-word `normal` whose w1 declares a
    baked intensity that the COST MODEL charges zero words, so the cost model's own
    parameter list is empty and the value -- 13.6533, the last word -- is invisible to it.

So this is not a tidier spelling of the old reads. It is a different answer, and the
reference arbitrates it.
"""
import functools

import numpy as np

import decompose


#: Per filter, the parameters its `w1` word declares: (mask, shift, name, kind).
#:
#: `code = (w1 & mask) >> shift` is SPEC.md 7.4's two-bit state -- 00 absent, 01 baked,
#: 10 program, 11 image input -- and `kind` is the BAKED width from the manifest's own
#: type legend: 'scalar' is Float1, 'channel' is Float1 grayscale / Float4 colour, and an
#: integer is a fixed component count. A program is one pointer whatever its type.
#:
#: THE MASK, NOT A FIELD INDEX, and the difference is not cosmetic. Two of these pairs
#: STRADDLE the two-bit tiling -- `transformation`'s offset sits at bits (25, 26) and
#: `blend`'s second scalar at (9, 10) -- so under a plain `j -> bits (2j, 2j+1)` reading a
#: baked offset appears as field 13 state 01 and a program offset as field 12 state 10, and
#: the two states swap meaning between the two fields. The mask is what the format states.
#:
#: THIS REPLACES `decompose`'s `param_slots` FOR NAMED PARAMETERS, deliberately. That list
#: is built from the cost model's per-(field, state) WORD COUNT, which is the fitted half of
#: costs.json (the ledger's L2), and it is wrong in at least one place that matters: for
#: `normal` it charges the intensity zero words and charges a class slot instead, so a
#: four-word record whose w1 says "field 0, baked" reports no parameter at all. Read the
#: presence from the w1 word and the width from the type legend, and the cost model is
#: needed only for the header LENGTH -- which is the part `derive_costs` fits to observed
#: boundaries and reproduces exactly.
W1_PARAMS = {
    # `blend` STATES ITS OPACITY IN TWO PLACES, and which one it uses is the port's doing:
    # connect the node's `opacity` input and the slider moves to bits (9, 10) while the
    # field at (4, 5) goes to state 11, the image-input code. Both are `opacitymult` -- the
    # same parameter -- and the shipped sources say so outright. In `ChesterfieldSofa.sbs`
    # exactly three blend nodes carry BOTH a connected `opacity` port AND a stated
    # `opacitymult` (0.73, 0.40, 0.20); exactly three compiled records set bits (9, 10), and
    # they hold those three floats. `SandyStonePath.sbs` matches five for five, the program
    # arm included. Calling this field anything else leaves 1,133 corpus records
    # compositing at full strength against a mask the source only wanted at 0.2.
    #
    # FIELD 3 IS TWO WORDS AND SITS BETWEEN THEM. Unnamed, and the cost model charges its
    # baked arm 2 words -- so a reader that places only `opacitymult` lands two slots late:
    # RoofingTilesSubstance003 record 26 reads -0.0 where the record holds 0.86. Only 26
    # corpus records set it, always baked; the other two states are charged nothing and are
    # unobserved, so nothing here claims to know what they would cost. What the field IS is
    # also unknown -- the shipped sources write six blend parameters (blendingmode,
    # colorblending, opacitymult, outputsize, format, tiling) and the two words look like
    # packed 16-bit halves -- so it is declared for its width and left unnamed.
    1:  [(0x30, 4, 'opacitymult', 'scalar'),          # blend
         (0xC0, 6, None, 2),
         (0x600, 9, 'opacitymult', 'scalar')],
    2:  [(0xC0, 6, 'matrix22', 4),                    # transformation
         (0x06000000, 25, 'offset', 2),
         (0x10000000, 28, 'backgroundcolour', 'channel')],
    11: [(0x3, 0, 'intensity', 'scalar'),             # dirmotionblur
         (0xc, 2, 'mblurangle', 'scalar')],
    12: [(0x6, 1, 'intensity', 'scalar'),             # directionalwarp
         (0x18, 3, 'warpangle', 'scalar')],
    15: [(0x003, 0, 'levelinlow', 'channel'),         # levels
         (0x00c, 2, 'levelinhigh', 'channel'),
         (0x030, 4, 'levelinmid', 'channel'),
         (0x0c0, 6, 'leveloutlow', 'channel'),
         (0x300, 8, 'levelouthigh', 'channel')],
    # `normal` DECLARES THREE FIELDS AND THIS TABLE NAMED ONE. Fields 1 and 2 are flags
    # whose baked arm costs nothing, so leaving them out looked free -- but their PROGRAM
    # arm is a word, and 38 corpus records put a program in field 1 while `intensity` is
    # also a program. Anchored at the end and charging one width, `intensity` was reading
    # field 1's pointer and running the wrong program.
    #
    # ALL THREE FIELDS ARE NAMED NOW, AND WHAT NAMED THEM IS THE PROGRAM ARM'S OPERAND.
    # Field 1 used to be `inversedy` "on evidence that is suggestive, not conclusive" -- the
    # frequency asymmetry, 38 programs against 67 flags where field 2 was 322 flags against
    # 1 -- and field 2 was left unnamed on that asymmetry alone. The asymmetry was the wrong
    # arbiter and the record says it plainly: every program arm in these fields opens with
    # `inputref` on a GRAPH INPUT, and the manifest names graph inputs.
    #
    #   field 0  275 programs, all returning float1; inputs named `normal_intensity` x205,
    #            `Normal` x18, `normal_strength` x13, `intensity` x6 ... -> intensity
    #   field 1   38 programs, all returning BOOL, all of the shape `<input> == 1`; inputs
    #            named `normal_format` x34, `generated_normal_format`, `NormalFormat`,
    #            `Format`, `normal_inverseDirection`             -> inversedy
    #   field 2    1 program, returning BOOL, `inputref.b2` direct; input named
    #            `Alpha_Channel_Content`                          -> input2alpha
    #
    # The types corroborate the split independently of the names: field 0 is float1 in 275
    # of 275 and fields 1 and 2 are boolean in 39 of 39, which is exactly the source-side
    # shape (`intensity` Float1, `inversedy` and `input2alpha` Bool) and is why the two
    # boolean fields cost zero words baked -- the mask state IS the value.
    #
    # A second, independent witness for field 1, from a permitted paired source:
    # `SBRustyTreadPlate.sbs` writes four normal nodes, intensity 6 / 15 / 3 / 10, and
    # states `inversedy 1` on exactly one of them, the intensity-15 node. Its compiled twin
    # holds five normal records with baked intensities 15.0, 12.8, 3.0, 6.0 and 10.0, and
    # the ONE record carrying a field-1 flag is the 15.0 one.
    #
    # `input2alpha` is NAMED here, not read: `f_normal` writes a constant alpha, and what
    # the parameter does to the alpha channel is not established by any of the above.
    # `distance`'s radius, from SandyStonePath.sbs: it states 56.2999992 and 64.2200012 on
    # its two distance nodes, and records 3 and 180 of the compiled twin hold exactly those
    # at field 0. Field 1 is declared for its width only -- the source's other parameter is
    # `combinedistance` and both nodes state it 0, which names nothing. Where field 1 holds
    # a PROGRAM the placement is unverified and demonstrably wrong: on those 188 records
    # every candidate slot holds a pointer, so `f_distance` keeps its own locator there.
    # `distance`: FIELD 1 IS THE RADIUS, and field 0 is not a parameter at all -- its low
    # bit declares the optional mask input, which the walk places as an EDGE at the front of
    # the header. Listing field 0 here named the wrong field and, worse, would charge this
    # end-anchored block a word for an input that is not in it. The two arms of field 1 are
    # the ordinary pair, and both are now read: 01 bakes the radius, 10 points at a program
    # this filter evaluates. See `decompose`'s note in the w1 loop for the evidence.
    21: [(0xc, 2, 'distance', 'scalar')],             # distance
    18: [(0x3, 0, 'intensity', 'scalar'),             # normal
         (0xc, 2, 'inversedy', 'flag'),
         (0x30, 4, 'input2alpha', 'flag')],
}


@functools.lru_cache(maxsize=None)
def _covered_bits(fid):
    """(w1 bits, class bits) this legend can name for one filter.

    MEMOISED, and a caller that MUTATES either legend -- the checks that prove they can
    still detect a missing name do exactly that -- must call `_covered_bits.cache_clear()`,
    or the mutation is invisible here and the check passes by not looking.

    Bits, not field indices: `blend`'s relocated opacity straddles the two-bit grid, and an
    index-based reading calls both halves unnamed.
    """
    w1 = 0
    for (mask, _shift, name, _kind) in W1_PARAMS.get(fid, ()):
        if name is not None:
            w1 |= mask
    cls = {_SIZE_BIT} | set(CLS_NAMES.get(fid, {}))
    return w1, cls


def _baked_width(kind, colour):
    """A baked field's width in words, from the manifest's type legend.

    `flag` is ZERO WORDS: the mask state IS the value, and the cost model agrees -- for
    filter 18 it charges fields 1 and 2 one word in state `program` and nothing in state
    `baked`. A field whose baked arm costs nothing still has to be DECLARED, because its
    program arm costs one word and the placement is anchored at the header end: an
    undeclared program sitting after `intensity` moves intensity's slot by one.
    """
    if kind == 'flag':
        return 0
    if kind == 'channel':
        return 4 if colour else 1
    return kind if isinstance(kind, int) else 1


#: (filter, w0 bit) -> (name, kind), for the parameters the CLASS word carries. A class
#: parameter is an adjacent bit PAIR -- the lower bit means the value is baked in place and
#: costs its own width, the upper that it is a program and costs one pointer -- so the two
#: bits of one parameter share a name and differ only in kind.
CLS_NAMES = {
    3:  {24: ('channelsweights', 'baked')},   # shuffle / grayscaleconversion, four words
    6:  {24: ('outputcolor', 'baked')},       # uniform's fill
    7:  {29: ('intensity', 'baked'), 30: ('intensity', 'program')},    # warp
    10: {28: ('intensity', 'baked'), 29: ('intensity', 'program')},    # blur
    # `sharpen` AT THE SAME PAIR AS `blur`, and on the same kind of evidence the pair law
    # is built from -- but WITHOUT a source to check it against, which `hsl` had and this
    # does not: all 28 sharpen nodes in the shipped sources state no parameters at all.
    # What is here: bit 28 holds an ordinary float on 1,148 corpus records (median 0.25,
    # 99% inside [1e-6, 1e4]) and bit 29 holds integers-as-denormals on 8, which is the
    # baked/program pair shape; the position is the one `blur` -- the other one-scalar
    # filter -- uses for the same parameter name. Until this table named it, `f_sharpen`
    # asked for `intensity`, no legend supplied it, and every record ran at the default.
    13: {28: ('intensity', 'baked'), 29: ('intensity', 'program')},    # sharpen
    # `hsl`, THREE PARAMETERS AND SIX BITS, from the shipped sources. ChesterfieldSofa.sbs
    # states `saturation` 0.65 with `luminosity` 0.60 on one node and `saturation` 0.58 on
    # another; the compiled records set bit 26 to 0.65 / 0.58 and bit 28 to 0.60.
    # SandyStonePath.sbs states `saturation` 0.525 and its record sets bit 26 to 0.525.
    # A source node with all three DYNAMIC compiles to bits 25, 27 and 29 -- the program
    # arms, in the same ascending order -- which is what names bit 24/25 `hue`: it is the
    # parameter the other two leave room for. Corpus-wide the three even bits hold ordinary
    # floats (bit 24 n=93 median 0.49, bit 26 n=203 median 0.43, bit 28 n=297 median 0.475,
    # all in [0,1] and all clustered on the neutral 0.5) and the three odd bits hold
    # integers-as-denormals, which is what a program pointer looks like read as a float.
    # Unnamed until this table said otherwise, all 747 corpus `hsl` records rendered as an
    # identity: `_scalar` returns the 0.5 default for a parameter nothing names.
    14: {24: ('hue', 'baked'), 25: ('hue', 'program'),                 # hsl
         26: ('saturation', 'baked'), 27: ('saturation', 'program'),
         28: ('luminosity', 'baked'), 29: ('luminosity', 'program')},
}

#: Class bit 0 -- w0 bit 16 -- is the inherited `$outputsize`, and it is the ONE class
#: parameter every filter shares. It is not in `CLS_NAMES` because it is not read by name:
#: it IS the size-expression slot, which `decompose` reports as `prog`.
_SIZE_BIT = 16


class Shifted(ValueError):
    """The end-anchored parameter block landed somewhere a parameter cannot be.

    The name legend cannot go STALE -- it never mentions a position -- but it can be
    INCOMPLETE, and that is the failure this catches: one unlisted `w1` field sitting
    after a listed one pushes the whole block late, and the words it lands on read as
    perfectly plausible floats. Nothing about the values says so; only the structure does.

    Two slots can never hold a parameter, and neither answer comes from the fitted
    per-field charge, so this is independent of the part of the cost model that is known
    wrong here: an INPUT EDGE (the walk names it from the base-input count and the
    state-3 fields, and it holds a backward record index), and the two mask words the
    format fixes at the head of every record. A block reaching either is the exact shape
    of the LAYOUTS memo's failure on Chesterfield 129/146/226, where `levelinhigh` was the
    input edge read as a denormal 0.0.

    Silent on the corpus: over 84,700 records carrying named parameters, 0 reach an edge,
    0 reach a mask word and 0 run past the record. It costs nothing until it is right.
    """


class Param(object):
    """One parameter the walk located. `kind` is 'baked' or 'program'."""
    __slots__ = ('name', 'kind', 'slot', 'width', 'value')

    def __init__(self, name, kind, slot, width, value):
        self.name, self.kind, self.slot = name, kind, slot
        self.width, self.value = width, value

    def __repr__(self):
        return 'Param(%r, %r, slot=%d, w=%d, %r)' % (
            self.name, self.kind, self.slot, self.width, self.value)


def _floats(words, slot, width):
    return np.array(words[slot:slot + width], dtype=np.uint32).view(np.float32)


class View(object):
    """A record decomposed once, by the walk, for the renderer to read by name.

        inputs     source record indices, in edge-slot order
        params     {name: Param}
        size_slot  the inherited size-expression slot, or None when class bit 0 is clear
        header_end the first word past the header, from the cost model
        walked     False when the cost model does not cover the record; every filter
                   treats that as a refusal rather than reading raw slots.

    WHERE THE W1 PARAMETERS SIT: anchored at `header_end` and laid out BACKWARDS, in field
    order, each field taking its own width. Not at the walk's forward cursor, and the
    difference was not cosmetic -- `normal` record 19 is a 5-word header whose intensity is
    slot 4, and the forward cursor put it at 6, because the cost model charged class slots
    for w0 bits 11 and 15 that this filter does not spend (the defect commit 28d4b6b names).
    Anchoring at the end is immune to a mis-charged slot BEFORE the parameters and wrong
    only if the header length itself is wrong -- and the header length is the one number
    `derive_costs` fits to observed boundaries and reproduces exactly.

    THE TWO NOW AGREE, WHICH IS NOT A REASON TO STOP ANCHORING AT THE END. Those two bits
    were the free intercept's shadow -- they declare no slot, and cost nothing once
    `costs.json` was re-attributed against the record's own base region (see
    `record_layout`) -- so the forward cursor lands on slot 4 as well. The anchor earned its
    keep by being right while the cursor was wrong, and it is still the placement that
    cannot be moved by a mis-attributed class width: the failure that has just been
    corrected once is not thereby guaranteed against twice.

    The class-word parameters keep the forward cursor, because they sit before the w1
    fields and an end anchor cannot reach them. Both are the walk; neither is a memo.
    """
    __slots__ = ('rec', 'asm', 'index', 'filter', 'filter_id', 'colour', 'width',
                 'height', 'words', 'inputs', 'params', 'size_slot', 'walked',
                 'header_end', 'unnamed', 'prog_slot', 'cls_slots', 'ignored')

    def __init__(self, asm, rec, size=None):
        self.rec, self.asm, self.index = rec, asm, rec.index
        self.filter, self.filter_id = rec.filter_name, rec.filter_id
        self.colour = bool(rec.colour)
        # THE TAG'S SIZE IS THE SIZE AT ONE `$outputsize`, not the record's only size.
        # Every size expression in a dynamic-size graph is a function of the graph input
        # `$outputsize`, and the tag caches its value at the manifest's DEFAULT. `size`
        # is that function re-evaluated at some other output size -- see
        # `engine.record_sizes`, which is the only thing that computes one. None keeps
        # the tag, so nothing changes unless a caller asks for a different output size.
        self.width, self.height = (rec.width, rec.height) if size is None else size
        self.words = rec.words
        self.params, self.unnamed, self.inputs = {}, [], []
        #: (kind, field-or-bit, slot, words) the walk placed and no name covers. See
        #: `_covered_bits`; the render reads none of these.
        self.ignored = []
        self.cls_slots = []
        self.size_slot = self.header_end = self.prog_slot = None
        self.walked = False

        try:
            d = decompose.decompose(rec)
        except Exception:
            d = None
        if d is None:
            return
        self.walked = True
        self.header_end = d.get('end')

        # EDGES ARE THE WALK'S `inputs`, RESOLVED THROUGH THE SLOT. An edge slot holds a
        # backward record index; the walk says which slots are edges and the word says
        # which record. Nothing scans for plausible indices.
        for slot in d.get('inputs', ()):
            v = rec.words[slot] if 0 <= slot < len(rec.words) else None
            self.inputs.append(v if (v is not None and 0 <= v < rec.index) else None)

        # THE SIZE SLOT IS A FIELD THE WALK RETURNS. It used to be reconstructed here --
        # `prog` gated on a re-test of word0 bit 16 -- and `prog` is where the class block
        # STARTS, which is the same word only when no costing class bit precedes bit 16.
        # Over 120 files those differ on 7,590 records. `decompose` now places it and says
        # so, so there is nothing left to reconcile.
        self.prog_slot = d.get('prog')
        self.size_slot = d.get('size_slot')

        # THE BRANCH THAT USED TO SIT HERE IS GONE. `emboss` was the last filter whose size
        # expression this file had to guess at -- `prog`, on the strength of the word there
        # resolving as a program in 375 of 375 records. It guessed right, and the walk now
        # says so for itself: `derive_costs` takes class bit 16's cost from the records BELOW
        # emboss's version gate, the only ones where that bit varies, and transfers it into
        # the modern spec, where it had been folded invisibly into a fitted 4.5. The transfer
        # is allowed only because every filter that can see bit 16 charges it exactly one
        # word -- a fact about the FORMAT, not about emboss. `record_layout.header_words` is
        # unchanged on all 546 records, and the walk's own cursor now matches that length on
        # 366 of 375 where it used to match none.

        # EVERY class slot, named or not. An inherited parameter this legend has no name
        # for can still hold a PROGRAM, and a filter that needs to run its record's setup
        # programs (pixelprocessor) has to be able to find them. Two Chesterfield
        # pixelprocessors failed on "slot 0 read but never set" -- and took 759 records
        # down with them -- because their setup program sits in an unnamed class slot.
        self.cls_slots = [s for s in d.get('cls_slots', ()) if 0 <= s < len(rec.words)]
        cls_names = CLS_NAMES.get(rec.filter_id, {})
        cov_w1, cov_cls = _covered_bits(rec.filter_id)
        for (bit, slot, width) in d.get('cls_params', ()):
            entry = cls_names.get(bit)
            if entry is not None:
                self._add(entry[0], entry[1], slot, width)
            elif bit not in cov_cls:
                # THE RECORD STATES A FIELD THIS LEGEND DOES NOT READ. Not an error -- the
                # walk placed it, so the layout is right and the render goes on -- but it is
                # the thing that has to be visible: `hsl` was an identity in 747 records and
                # `sharpen` in 1,156, and both looked like ordinary output.
                self.ignored.append(('cls', bit, slot, width))

        # The filter's OWN parameters, from the w1 word, anchored at the header end and
        # laid out in ascending mask order, each taking its own width.
        w1 = rec.words[1] if len(rec.words) > 1 else 0
        n_masks = 2 if len(rec.words) > 1 else 1
        present = []
        for (mask, shift, name, kind) in W1_PARAMS.get(rec.filter_id, ()):
            code = (w1 & mask) >> shift
            if code == 1:
                present.append((name, 'baked', _baked_width(kind, self.colour), shift // 2))
            elif code == 2:
                present.append((name, 'program', 1, shift // 2))
        # ONE ARM AT A TIME. Two entries can share a name (`blend`'s opacity is at (4, 5)
        # or at (9, 10), never both), and a name added twice would keep the second silently
        # while charging both widths to the layout. It has never happened in 437 files; say
        # so out loud rather than render the wrong slot.
        names = [t[0] for t in present if t[0] is not None]
        if len(set(names)) != len(names):
            raise Shifted('filter %d: two w1 fields are present under one name (%s) -- '
                          'they are relocation arms and only one is ever set'
                          % (rec.filter_id,
                             ', '.join(sorted({n for n in names if names.count(n) > 1}))))
        end = self.header_end
        if present and end is not None:
            pos = end - sum(t[2] for t in present)
            in_slots = [s for s in d.get('inputs', ()) if isinstance(s, int)]
            if pos < n_masks or (in_slots and pos <= max(in_slots)) \
                    or end > len(rec.words):
                raise Shifted(
                    'filter %d: the named parameters would start at slot %d, which is %s '
                    '-- a `w1` field this legend does not name is taking the space'
                    % (rec.filter_id, pos,
                       'inside the record\'s masks' if pos < n_masks else
                       'an input edge' if in_slots and pos <= max(in_slots) else
                       'past the record\'s %d words' % len(rec.words)))
            for (name, kind, width, field) in present:
                self._add(name, kind, pos, width, field)
                pos += width
        # THE TWO PLACEMENTS MUST NOT OVERLAP, and on 1,012 `normal` records they did: the
        # class walk put bit 16 -- the size expression -- on the very slot the end-anchored
        # parameter block owns, and bit 27 one further, past the header end. The SOURCE
        # settled which was right: ChesterfieldSofa states `intensity` 10 on its one normal
        # node and that slot holds 10.0, so the parameter was where it belongs and the class
        # placement was over-long.
        #
        # THAT WAS THE SYMPTOM, AND ITS CAUSE IS FIXED. `normal`'s costs charged four class
        # bits that declare no slot, paid for out of an intercept two words below the base
        # region every record of that filter has; with `costs.json` re-attributed against
        # that base (see `record_layout`) the class block ends exactly at the header end and
        # nothing overlaps -- 0 clashes over 447 files, where the same sweep counted 1,012.
        #
        # THE GUARD STAYS. What it does is right whatever the cause: keep the parameter, drop
        # the size slot rather than hand `walk_programs` a float as a program address, and
        # say so through `ignored`. It costs one set membership per record, and
        # `test_the_size_slot_is_the_walks_placement_not_the_blocks_start` now asserts it is
        # SILENT rather than asserting it fires -- so a placement that goes wrong again is
        # caught there instead of being absorbed here.
        taken = {p.slot for p in self.params.values() if p.slot is not None}
        if self.size_slot is not None and self.size_slot in taken:
            self.ignored.append(('clash', _SIZE_BIT, self.size_slot, 1))
            self.size_slot = None

        # Slots the cost model calls parameters keep their place in the PROGRAM candidate
        # list even where this legend has no name for them.
        for (_j, state, slot, _w) in d.get('param_slots', ()):
            if _w >= 1 and not ((3 << (2 * _j)) & cov_w1):
                self.ignored.append(('w1', _j, slot, _w))
            if state == 2 and 0 <= slot < len(rec.words):
                self.unnamed.append((_j, Param(None, 'program', slot, 1,
                                               rec.words[slot] + 52)))

    def _add(self, name, kind, slot, width, field=None):
        if slot < 0 or slot + width > len(self.words):
            return
        if kind == 'program':
            value = self.words[slot] + 52
        elif width == 0:
            value = 1.0                 # a flag: the mask state IS the value
        elif width == 1:
            value = float(_floats(self.words, slot, 1)[0])
        else:
            value = tuple(float(x) for x in _floats(self.words, slot, width))
        p = Param(name, kind, slot, width, value)
        if name is None:
            self.unnamed.append((field, p))
        else:
            # A name can be reached from two fields (`transformation`'s offset straddles
            # the tiling boundary, so its baked arm is field 13 and its program arm field
            # 12). Only one of the two is ever present.
            self.params[name] = p

    # -- reading -----------------------------------------------------------------

    def baked(self, name, default=None):
        """The parameter's constant, or `default` when it is absent or a program."""
        p = self.params.get(name)
        return default if p is None or p.kind != 'baked' else p.value

    def program(self, name):
        """The program address the parameter names, or None."""
        p = self.params.get(name)
        return None if p is None or p.kind != 'program' else p.value

    def has(self, name):
        return name in self.params

    def edge(self, k):
        return self.inputs[k] if k < len(self.inputs) else None

    def size(self, cap=None):
        """(W, H) for evaluation, capped for sweeps."""
        w, h = self.width, self.height
        return (min(w, cap), min(h, cap)) if cap else (w, h)

    def __repr__(self):
        return '<View %d %s inputs=%s params=%s>' % (
            self.index, self.filter, self.inputs, sorted(self.params))


def views(asm):
    """Every record of `asm`, decomposed once."""
    return [View(asm, r) for r in asm.records]
