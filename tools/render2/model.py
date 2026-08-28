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
    1:  [(0x30, 4, 'opacitymult', 'scalar'),          # blend
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
    18: [(0x3, 0, 'intensity', 'scalar')],            # normal
}


def _baked_width(kind, colour):
    """A baked field's width in words, from the manifest's type legend."""
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
    difference is not cosmetic -- `normal` record 19 is a 5-word header whose intensity is
    slot 4, and the forward cursor puts it at 6, because the cost model charges class slots
    for w0 bits 11 and 15 that this filter does not spend (the defect commit 28d4b6b names).
    Anchoring at the end is immune to a mis-charged slot BEFORE the parameters and wrong
    only if the header length itself is wrong -- and the header length is the one number
    `derive_costs` fits to observed boundaries and reproduces exactly.

    The class-word parameters keep the forward cursor, because they sit before the w1
    fields and an end anchor cannot reach them. Both are the walk; neither is a memo.
    """
    __slots__ = ('rec', 'asm', 'index', 'filter', 'filter_id', 'colour', 'width',
                 'height', 'words', 'inputs', 'params', 'size_slot', 'walked',
                 'header_end', 'unnamed', 'prog_slot', 'cls_slots')

    def __init__(self, asm, rec):
        self.rec, self.asm, self.index = rec, asm, rec.index
        self.filter, self.filter_id = rec.filter_name, rec.filter_id
        self.colour = bool(rec.colour)
        self.width, self.height = rec.width, rec.height
        self.words = rec.words
        self.params, self.unnamed, self.inputs = {}, [], []
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

        # THE SIZE SLOT IS PRESENT IFF CLASS BIT 0 IS. `decompose` reports `prog` for every
        # record, set or clear, so a `blur` whose 3-word header is [tag][edge][intensity]
        # has `prog = 2` pointing at its intensity -- which is what makes `size_or_baked`
        # answer ('float', 0.38) on a record that carries no size expression at all. The
        # class word says whether the inherited parameter is there; ask it.
        self.prog_slot = d.get('prog')
        if (rec.words[0] >> _SIZE_BIT) & 1:
            self.size_slot = self.prog_slot

        # EVERY class slot, named or not. An inherited parameter this legend has no name
        # for can still hold a PROGRAM, and a filter that needs to run its record's setup
        # programs (pixelprocessor) has to be able to find them. Two Chesterfield
        # pixelprocessors failed on "slot 0 read but never set" -- and took 759 records
        # down with them -- because their setup program sits in an unnamed class slot.
        self.cls_slots = [s for s in d.get('cls_slots', ()) if 0 <= s < len(rec.words)]
        cls_names = CLS_NAMES.get(rec.filter_id, {})
        for (bit, slot, width) in d.get('cls_params', ()):
            entry = cls_names.get(bit)
            if entry is not None:
                self._add(entry[0], entry[1], slot, width)

        # The filter's OWN parameters, from the w1 word, anchored at the header end and
        # laid out in ascending mask order, each taking its own width.
        w1 = rec.words[1] if len(rec.words) > 1 else 0
        n_masks = 2 if len(rec.words) > 1 else 1
        present = []
        for (mask, shift, name, kind) in W1_PARAMS.get(rec.filter_id, ()):
            code = (w1 & mask) >> shift
            if code == 1:
                present.append((name, 'baked', _baked_width(kind, self.colour)))
            elif code == 2:
                present.append((name, 'program', 1))
        # ONE ARM AT A TIME. Two entries can share a name (`blend`'s opacity is at (4, 5)
        # or at (9, 10), never both), and a name added twice would keep the second silently
        # while charging both widths to the layout. It has never happened in 437 files; say
        # so out loud rather than render the wrong slot.
        names = [t[0] for t in present]
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
            for (name, kind, width) in present:
                self._add(name, kind, pos, width)
                pos += width
        # Slots the cost model calls parameters keep their place in the PROGRAM candidate
        # list even where this legend has no name for them.
        for (_j, state, slot, _w) in d.get('param_slots', ()):
            if state == 2 and 0 <= slot < len(rec.words):
                self.unnamed.append((_j, Param(None, 'program', slot, 1,
                                               rec.words[slot] + 52)))

    def _add(self, name, kind, slot, width, field=None):
        if slot < 0 or slot + width > len(self.words):
            return
        if kind == 'program':
            value = self.words[slot] + 52
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
