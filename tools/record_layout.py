#!/usr/bin/env python3
"""The record layout rule, as one function.

A record is a struct with two presence masks and no stored offsets:

    word 0   tag   filter id, plus `cls` -- a bitmask over the INHERITED parameters
                   ($outputsize, $randomseed, output format, pixel size, ...)
    word 1   w1    a grid of two-bit codes over the FILTER's OWN parameters
                   00 absent   01 baked   10 a program   11 an image input
                   -- present only for filters that have such parameters
    then     the image inputs, contiguous
    then     one slot per set cls bit, in canonical order
    then     one slot group per nonzero w1 field, in field order
    tail     payload filters end with a pointer to their table

Every position is implied by the bits set before it, so a reader walks the masks and a
writer emits in the same order. Nothing stores a slot number, which is why no bitfield of
the tag was ever found that computed one.

`header_words` is the whole rule in arithmetic form, and it is now SPEC 7.3's WIDTH LEGEND
rather than a fit:

    header = n_hdr + n_base + n_fixed
           + SUM over set class bits of        width(kind)
           + SUM over w1 FIELDS -- a two-bit code AT ITS OWN BIT OFFSET -- of
                 00 absent  -> 0        01 baked   -> width(kind)
                 10 program -> 1        11 edge    -> 1
           + arity                (the two filters whose w1 holds an input count)
           + one conjunction      (bitmap 24+27)
           + one integer field    (transformation's w1 bits 0-4: one reserved value of a
                                   5-bit INTEGER emits a program pointer)

    width:  0 -> 0   1 -> 1   2 -> 2   4 -> 4   C -> 1 grey / 4 colour
    n_hdr = 1 + (this record carries a w1 word)

`n_hdr` is a count of mask words, `n_base` the filter's fixed image-input arity
(SPEC 6.3) and `n_fixed` its fixed prefix -- the ramp pair, the FX tree root, the bitmap
pixel word, `text`'s zero+string+font, `pixelprocessor`'s own program. Every term is a
structural count or a width from the format's own type legend (SPEC 7.2). There is no
intercept, no float, no negative coefficient, no per-state cell, no base/cross vector, no
interaction mode, no grid shift, no straddle table and no fitted variant.

THE TABLE THIS READS IS `tools/legend.json`, derived by `archive/tools/derive_legend.py`:
one KIND per header cell, drawn from the five-symbol alphabet `0 1 2 4 C`. 106 kinds over
107 cells, 32 of them a bit offset. It replaced `costs.json`'s 688 fitted numeric cells
across five spec shapes (`plain`, `colour`, `colour_states`, `arity`, `variants`) plus
`pairs`, `flags`, `constant_bits`, `has_absent`, `arity_sm`, `nullity`, `unident`, a
`w1_shift`, a `conj` list and a `STRADDLED` relabelling table in `decompose`.

WHAT WENT WITH THE FIT, and why each mattered:

  * THE FREE INTERCEPT. `derive_costs` solved `header = const + sum of set-bit costs` and
    nothing in that equation says `const` is the size of anything, so the solver was at
    liberty to shave words off it and charge them to a bit set in every record of a
    filter. The total came out right and the DECOMPOSITION was wrong, which a check that
    only compares lengths cannot see -- and `decompose` walks the same table forwards from
    a base it computes structurally, so it spent the difference as slots past the header
    end. Four entries had to be re-solved by hand against the base and a re-run reverted
    two of them every time. The base is now pinned by construction and there is nothing to
    revert: `derive_legend` LEARNS the legend, so re-running it is idempotent.
  * THE HALVES. `sharpen` still priced the record's CANVAS as of 5fcf06b --
    `cls[10] = cls[11] = +0.5`, `cls[14] = cls[15] = -0.5` on word0's two log2-size
    nibbles -- and its header length therefore depended on the record's aspect ratio for a
    header whose contents do not. It was latent rather than live: on the twelve
    resolutions the corpus holds the four halves and the rounding tie cancel. Under the
    legend those four bits have no cell at all and bit 26 is exactly 2.
  * NEGATIVE COEFFICIENTS. `shuffle` expressed its two record shapes with `cls[0] = -1.0`
    and `w1_present = -1.0`; a forward walk cannot subtract a slot, so its cursor came out
    two words long on 1,623 records. The shapes are a `has_w1` rule now.
  * PER-STATE CELLS. A field cost one number for `01`, another for `10`, a third for `11`.
    Read as the legend they are one width and two ones: a pointer is a pointer and an edge
    slot is a slot, in every filter.
  * `W1_GRID_SHIFT` AND THE STRADDLE TABLE, which were the same artefact twice. A field
    begins at its own bit; there is no grid to shift and nothing to un-straddle.
    `directionalwarp`'s fields are at bits 1, 3 and 7, `emboss`'s at 1, 3, 5 and 7,
    `blend`'s relocated opacity at 9 and `transformation`'s offset at 25, and saying so
    needs no per-filter shift constant and no pair of phantom half-fields.

WHAT THE LEGEND IS NOT. It is a WIDTH legend and not a NAME legend: it says how many words
a cell occupies, never what the value means. SPEC 7.3 states the gap it leaves -- the
per-field type CODE -- and it is unchanged by any of this.

WHAT THE CORPUS DOES NOT SEPARATE, marked in the table rather than smoothed away. A kind is
a pair of widths, `(grey, colour)`, and only two of the five share a width: `Float1` is
`(1, 1)` and per-channel is `(1, 4)`. So a cell exercised in ONE colour only is a reading in
that colour and the legend's PREDICTION in the other, and 36 of the 214 (cell, colour) pairs
are in that state -- 19 because the filter has no record of the other colour at all (`text`
is grey on all 59, `normal` and `hsl` colour on every one), 17 because it has records and
none set the cell (`blur` / `sharpen` / `distance` / `curve` / `dyngradient` class bit 23 in
colour, `emboss` w1 bit 5 in grey, `fxmaps` class bit 22 in colour). `legend.json`'s
`evidence` map names the source of every one, per colour, so an absence can never be read as
a measured zero -- which is exactly what the fitted table stored, and indistinguishably.
"""
import functools
import json
import os

_LEGEND = None


def legend():
    """The width legend, loaded once.

    `header_words` is memoised on (filter, word0, w1, version) and is therefore only sound
    while this table is fixed. It is loaded once per process and never reloaded, so that
    holds; a caller that ever swaps the table must call `header_words.cache_clear()`.
    """
    global _LEGEND
    if _LEGEND is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'legend.json')
        try:
            with open(p) as fh:
                _LEGEND = json.load(fh)
        except OSError:
            _LEGEND = {}
    return _LEGEND


def width(kind, colour):
    """A kind's width in words. `C` is per-channel: 1 grayscale, 4 colour (SPEC 6.4).

    `None` is a cell the corpus never bakes in either colour, so the legend has no reading
    for it -- distinct from a cell measured at zero, and the caller must refuse rather
    than assume. One cell is in that state (`fxmaps` at w1 bit 8).
    """
    if kind is None:
        return None
    if kind == 'C':
        return 4 if colour else 1
    return int(kind)


def arity_field(filter_id):
    """(shift, mask) for a filter's w1 arity count, or None if it declares none.

    THE PLACE THE ARITY ENCODING IS WRITTEN DOWN. It was three: this table, `decompose`'s
    `mask = max(mask, 0x3F)` workaround, and `walk.SPECS[4]`'s hardcoded `(w1 >> 10) & 0xF`.
    The three did not agree -- walk's stale nibble truncated every count above 15 and so
    disagreed with decompose on 10 records (`ie_curve` #35 declares 34 inputs; a nibble
    reads back 2). Callers ask here rather than restating the shift.

    THE WIDENING IS GONE FROM `decompose` TOO, and the legend is why. `pixelprocessor`'s
    field is FIVE bits and the fit read four, so `decompose` carried
    `mask | (mask + 1)` to widen 0xf to 0x1f -- and the missing bit reappeared in the fit
    as a phantom "w1 field 2 bakes 16 words" cell. Read as (shift 0, mask 31) the cell
    disappears and there is nothing left to widen.
    """
    sp = legend().get(str(filter_id))
    if sp is None:
        return None
    ar = sp.get('arity')
    return tuple(ar) if ar else None


W1_REFUSE = object()        # "the shape is undecidable from what you passed"


def has_w1(filter_id, word0, version):
    """Does a record of this filter, tag `word0`, assembly `version` carry a w1 word?

    True, False, or None for "undecidable from what you passed". THE ONE PLACE THIS RULE
    LIVES. `header_words`' own comment used to say the gate belongs here "not in the
    callers", because a caller that forgets it charges a mask word to a record that has
    none and comes out one word long, silently -- a session probe that missed it measured
    warp's model as wrong in 25,085 of 26,795 records and published that. But
    `decompose._has_w1_word` was a second copy of the same rule, so the gate lived in two
    places and only one of them said so. Both delegate here now.

        never        the filter has no w1 word at all; slot 1 is an image edge or a value
        always       every record of the filter carries one
        tagbit0      shuffle (3). TAG BIT 0 selects the shape, and it is not a per-record
                     accident: bit 0 is the output colour flag, filter 3's parameter is PER
                     OUTPUT CHANNEL, and the shape follows the channel count -- one channel
                     wants weights over the inputs and carries no selector word, four want
                     a packed per-channel selector and do. 7,682 records, no exceptions.
        v9           warp (7). The w1 word is a VERSION fact: absent before 0x90000,
                     present from it. Undecidable without a version, so refuse.
    """
    sp = legend().get(str(filter_id))
    rule = sp.get('has_w1') if sp else None
    if rule == 'always':
        return True
    if rule == 'never':
        return False
    if rule == 'tagbit0':
        return bool(word0 & 1)
    if rule == 'v9':
        return None if version is None else version >= 0x90000
    return None


def two_shape_w1(filter_id, word0, w1, version):
    """The effective w1 for a record of this shape, or `W1_REFUSE`.

    `has_w1` states the rule; this applies it to a word, which is the form the older
    callers want. None means "this record has no w1 word", never "the word is zero".
    """
    h = has_w1(filter_id, word0, version)
    if h is None:
        return W1_REFUSE
    return w1 if h else None


@functools.lru_cache(maxsize=1 << 16)
def header_words(filter_id, word0, w1, version=None):
    """Header length in words from the masks alone, or None if the legend cannot say.

    None means "this filter's cells were not established", never "zero" -- callers must
    fall back rather than treat a missing rule as an answer. There are three ways to get
    it: a filter with no legend entry (`vectorshape`, filter 9), a record below the
    version gate a filter's modern layout sits behind (`emboss`), and a w1 field in the
    BAKED state whose kind the corpus never exercised.

    `word0` is the record's ENTIRE first word, not the cls field alone. The tag's low
    bits carry layout too -- `shuffle`'s shape and every per-channel width are selected by
    tag bit 0 -- and the first version of this function took cls and silently could not
    see them. Note what the low half is NOT: a presence mask. Two of its nibbles are the
    record's own log2 size (SPEC 6.2), and a fitted table that offered every bit of word0
    as a feature charged header words to them -- `normal`, `dyngradient` and `sharpen` all
    priced the canvas at one time or another. The legend has no cell on any of those bits,
    because a width comes from a type and not from a regression.

    `w1` is passed unconditionally: this function decides whether the record's shape has
    the word, and ignores the argument when it does not.
    """
    sp = legend().get(str(filter_id))
    if sp is None:
        return None
    mv = sp.get('min_version')
    if mv is not None and (version is None or version < mv):
        return None                      # this filter's modern layout only
    has = has_w1(filter_id, word0, version)
    if has is None:
        return None                      # the shape is undecidable: refuse
    c0 = word0 & 1
    n_hdr = 1 + (1 if has else 0)
    base = sp['base']
    total = n_hdr + (n_hdr if base is None else base) + sp['fixed']
    for b, k in sp['cls'].items():
        if (word0 >> int(b)) & 1:
            total += width(k, c0)
    sh4 = sp.get('shape4')
    if sh4 is not None and not has and (word0 >> sh4[0]) & 1:
        # SPEC 6.4's two-shape filter, from the far side: `shuffle` bakes its
        # `channelsweights` at class bit 24 in the shape that carries NO w1 word, and
        # packs a per-channel selector into w1 in the shape that does. One cell, gated on
        # the shape rather than split into two fitted variants.
        total += width(sh4[1], c0)
    for bx, by, cv in sp.get('conj', ()):
        # SPEC 6.4's paired conjunction: word0's high byte is a small field for `bitmap`,
        # not eight independent flags, and bits 24 and 27 set TOGETHER mean the record
        # carries the second offset word that locates its pixels. An additive model can
        # only reach that through two halves and a rounding tie, which is what it did.
        if (word0 >> bx & 1) and (word0 >> by & 1):
            total += width(cv, c0)
    if has and w1 is not None:
        ar = sp.get('arity')
        if ar:
            total += (w1 >> ar[0]) & ar[1]
        for b in sp.get('edge_bits', ()):
            # A w1 bit that declares an image INPUT from its LOW BIT alone rather than
            # from a two-bit code (SPEC 6.3). One field in one filter: `distance`'s
            # optional mask input, whose cost tracks bit 0 and not baked-versus-program.
            total += (w1 >> b) & 1
        iv = sp.get('w1_int')
        if iv:
            # THE ONE w1 REGION THAT IS AN INTEGER AND NOT TWO-BIT FIELDS (SPEC 7.4).
            # `transformation`'s bits 0-4 hold a 5-bit value; 0..13 are literal and cost
            # nothing, 31 is the ordinary value on 230,639 of 234,859 records, and 30 is
            # the one value that emits a program pointer. No partition of those bits into
            # two-bit fields can express that -- cost is additive over a partition, and
            # `0x3f`/`0x3e` and `0x23`/`0x22` differ in bit 0 alone and disagree about
            # what it costs.
            if (w1 >> iv[0]) & iv[1] == iv[2]:
                total += 1
        for sh, k in sp['w1'].items():
            st = (w1 >> int(sh)) & 3
            if st == 1:
                n = width(k, c0)
                if n is None:
                    return None          # a baked cell with no reading: refuse
                total += n
            elif st:
                total += 1               # a program pointer, or an edge slot
    return total if total > 0 else None


def covered():
    """The filter ids the rule can decide."""
    return {int(k) for k in legend()}
