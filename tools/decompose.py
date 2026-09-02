"""One structural walk of a record header, replacing the five layout special cases.

The format is a single struct (record_layout's model):

    [tag][w1?][fixed prefix][image inputs][one slot per set cls bit][one slot-group per w1 field][tail]

`decompose(record)` walks it once and returns {inputs, cls_slots, param_slots, end}, from which
`param_slots` entries are (w1 BIT OFFSET, state, first slot, WIDTH IN WORDS) -- one per parameter,
edges (= inputs), the size slot, named parameters and program slots all follow.

IT READS SPEC 7.3's WIDTH LEGEND (`tools/legend.json`, via `record_layout`), NOT A FIT. One
kind per header cell, drawn from `0 1 2 4 C` -- 106 kinds over 107 cells -- where the model
this replaced held 688 fitted numeric cells across five spec shapes. What that removed from
THIS file, and every one of them was a source of misplacement rather than of length error:

  * `_interaction_walk` and `_feature_cost`, the `base`/`cross` vectors and the
    `colour`/`colour_states` modes. Per-channel is a KIND, `C`, and the walk asks the
    legend for its width the same way it asks for every other.
  * `_select_spec`'s variant loop. `shuffle`'s two shapes are a `has_w1` rule.
  * `_restraddle` and `STRADDLED`. A field begins at its own bit, so there is nothing to
    un-straddle: `blend`'s relocated opacity is the field at bit 9 and `transformation`'s
    offset the field at bit 25, and each is ONE field with one width in both its states.
  * `w1_shift`. There is no grid to shift; `directionalwarp`'s fields are at bits 1, 3, 7
    and `emboss`'s at 1, 3, 5, 7, and the walk reads each at its own offset.
  * the arity-mask widening `mask | (mask + 1)`. The legend states five bits for
    `pixelprocessor` and six for `fxmaps`, which is what they are.
  * `pos = max(pos, const)`. `const` was an INTERCEPT and this used it as a POSITION; the
    base is now `n_hdr + n_base + n_fixed`, three structural counts, and the cursor walks it.

Four walks became one. The class block, the fixed prefix and the w1 block are each emitted
once here, so a rule about any of them lands in one place -- which is the thing that went
wrong repeatedly while there were four (`_class_emission_order`'s note records the last of
them, a class order applied at three of four loops for two commits).

Returns None for `vectorshape`'s shape-only stub aside: the single unnamed filter-9 record,
`emboss` below its version gate, and any record whose legend cell the corpus never
exercised. Callers must treat None as a refusal, never as zero.

VALIDATION MUST NOT GO THROUGH `edge_slots` OR `Record.layout`. Both of those now call
decompose, so `decompose(r)['inputs'] == r.edge_slots` and `decompose(r)['prog'] ==
r.layout[1]` are decompose compared against itself -- they return 100% by construction and
prove nothing. This trap already bit twice (an edges number and an fxmaps-prog number, both
circular and both silently passing). Compare against `_compute_layout()` / `_real_edges()` /
`_pp_edges()`, the raw words, `record_layout.header_words`, the manifest, or the render.
See FORMAT-NOTES.md "Unified walk" and "The cost model is a width legend".
"""
import record_layout


#: word0 bit for the inherited size expression -- class bit 0.
_SIZE_BIT = 16


def _size_slot(cls_params):
    """The slot the class walk PLACED the size expression in, or None.

    THE WALK ANSWERS THIS, NOT THE CALLER. Readers used to reconstruct it by re-testing
    word0 bit 16 and taking `prog`, which is where the class block STARTS -- the same word
    only when no costing class bit precedes bit 16. Over 120 files the two answers differ on
    7,590 records (`pixelprocessor` by one slot 6,905 times, `dyngradient` by one 399,
    `normal` by two 246). Returning it here leaves one answer with one contract: the slot
    holding the inherited size expression, or None when the record has none or this walk
    cannot place it. None is a REFUSAL, never a zero.
    """
    return next((sl for (b, sl, _n) in cls_params if b == _SIZE_BIT), None)


def _param_field_masks(f):
    """The exact PARAM_SPEC presence masks for this filter. A w1 field reading 0b11 is a
    genuine image input only when its 2-bit range EXACTLY equals one of these masks (an
    aligned declared field, e.g. blend's opacitymult). An unnamed field is not an edge.

    Every mask in every PARAM_SPEC entry is `3 << offset` for an offset the legend
    declares -- blend 0x30/0x600 at 4 and 9, dirwarp 0x6/0x18 at 1 and 3, levels' five at
    0, 2, 4, 6, 8, fxmaps' four at 0, 4, 6, 8 -- so the test is a set membership and needs
    no grid.
    """
    import sbsasm
    return {pres for _nm, pres, _prog in sbsasm.PARAM_SPEC.get(f, ())}


# Whether a state-3 w1 field is an image input is a LAW OF (filter, bit offset), not a
# per-record question. Measured by INSTRUMENTING THIS FUNCTION over the full 437-file corpus
# -- wrapping it and recording every (filter, offset, answer) it is actually asked -- rather
# than by re-deriving slot positions in a separate script. That distinction is not pedantry:
# the first version of this table WAS built by re-derivation, and it was wrong. That script
# called `_select_spec` with `getattr(asm, 'version', None)`, which is not the `ver`
# decompose passes internally, so it selected a DIFFERENT spec variant with different w1 keys
# and dutifully measured six (filter, field) pairs the walk never visits at all.
# Instrument the real call, do not reconstruct it.
#
# THE KEYS ARE BIT OFFSETS NOW, NOT COST-MODEL FIELD INDICES. Under the fitted model this
# table read {(1,2), (1,4), (1,5), (8,1), (12,1), (12,2), (21,0)} -- indices into a per-filter
# `pairs` list on an even grid, three of which named fields the format does not have. Every
# decision the legend walk is genuinely asked to make, full corpus:
#
#     f=1  bit 4    8,486   ALWAYS input   -- and it never reaches this table: its 2-bit
#                                             range equals blend's PARAM_SPEC mask 0x30
#                                             exactly, so the aligned test above answers it
#                                             structurally first.
#     f=8  bit 3       87   never input    f=12 bit 3      838   never input
#
# `distance`'s unnamed input, cited by an old docstring as the case that made a value probe
# unavoidable, never reaches this function at all: its mask is declared by w1 BIT 0 alone
# (SPEC 6.3) and the legend states it as an `edge_bits` entry, placed with the base region.
INPUT_FIELDS = {
    (1, 4): True,
    (8, 3): False,
    (12, 3): False,
}


def _is_image_input(r, sh, pos, masks, ri):
    """Is a state-3 (0b11) w1 field at bit offset `sh`, slot `pos`, a real image input?

    Answered from the HEADER ONLY -- the aligned PARAM_SPEC mask, then the per-(filter,
    offset) law in `INPUT_FIELDS`. The slot's VALUE is never consulted.

    It used to end with `0 < r.words[pos] < ri` -- "the slot holds something that looks like a
    backward record index, so call it an input". That decided 1,944 of 10,430 state-3 fields
    (18.6%), and answered False every single time. It also made the two value probes in
    `Record.edges` score a perfect zero, since they re-tested the very predicate that had
    selected the slots -- a tautology, not a confirmation, which is why removing them changed
    nothing.

    The residual `_probe_fallback` list records any (filter, offset) pair this table has never
    seen. It is empty on this corpus; entries appearing on a new one are a finding to
    investigate, not a slot to guess at. It caught (8, 3) exactly this way -- 87 calls the
    first table missed, surfaced instead of silently probed."""
    if (3 << sh) in masks:
        return True
    known = INPUT_FIELDS.get((r.filter_id, sh))
    if known is not None:
        return known
    _probe_fallback.append((r.filter_id, sh))
    return pos < len(r.words) and 0 < r.words[pos] < ri


# Every (filter, offset) the table above does not cover, appended as it is hit. Empty on the
# 437-file corpus; inspect it rather than trusting the fallback if it fills on a new one.
_probe_fallback = []

# Per-filter base image-input arity: how many input images the filter consumes before any
# w1-declared inputs. A format fact (like the blend-mode table), not a fitted memo entry, and
# it lives in `legend.json` as each filter's `base`. Kept here as the accessor callers already
# know, and read from the legend so there is one copy: `None` means "the number of MASK
# WORDS", which is `shuffle`'s rule (its no-w1 shape takes one image at slot 1 and its w1
# shape two at slots 2-3).
#
# 16 bitmap / 17 text are source-side: no image inputs. `vectorshape` (5) has no legend entry
# (source geometry, no edges) and is answered by the stub in `decompose`.
BASE_INPUTS = {int(k): v['base'] for k, v in record_layout.legend().items()
               if v.get('base') is not None}


def _has_w1_word(f, w0, ver):
    """Does this record's shape carry a w1 word? True / False / None for "undecidable".

    DELEGATED, not reimplemented. This carried its own copy of the warp and shuffle gates,
    which is precisely the duplication `record_layout.header_words` warns about -- "a rule
    the caller can forget is a rule in the wrong place". Two copies is that same failure one
    step later: the gate lived in two files and only one of them said so.
    """
    return record_layout.has_w1(f, w0, ver)


#: THE CLASS BLOCK'S EMISSION ORDER, as a format constant rather than a per-filter branch.
#:
#: `clsbits` is ascending and the block is not. THE RULE IS A SORT, NOT A PAIR:
#: **class bit 16 (`$outputsize`) is emitted LAST within the low class group (bits 16-23),
#: and the filter's own bits 24-31 follow in ascending order.**
#:
#: THIS REPLACED A PAIRWISE SWAP `((23, 16),)`, WHICH WAS WRONG ON 3 RECORDS. Bit 23 gates
#: `$randomseed` and bit 16 `$outputsize`, and stating only "23 before 16" misses every
#: record that sets a costing class bit between them without setting 23. Scored on the
#: 214,298 records where the candidate orders place bit 16 in different slots at all -- by
#: whether that slot's word resolves a program returning a TWO-COMPONENT integer, which a
#: size expression is and a seed is not:
#:
#:     order                                      valid program        two-component
#:     16 last in the low group (this rule)    214,298 / 214,298         214,298
#:     swap 23 before 16 (the old rule)        214,295 / 214,298         214,295
#:     plain ascending                         214,295 / 214,298         112,122
#:     bit 16 last overall / descending        169,944 / 214,298         100,440
#:
#: The three records the swap misses are `Texture_Randomizer.sbsasm` records 0, 2 and 5 --
#: the only records in the corpus that set class bit 22, which costs a word and is the only
#: costing class bit strictly between 16 and 23. They set 16 and 22 and NOT 23, so a
#: pairwise `(23, 16)` swap never fires. Walked under this rule their bit-22 slot opens
#: `0x0A42 inputref` on uid 1786583393, which that file's manifest declares
#: `identifier="$outputsize" type="8" default="8,8"`, and the bit-16 slot holds a constant
#: `0x203`; walked ascending the two are exchanged.
#:
#: WHAT THIS CORPUS CANNOT SEPARATE, and it is worth stating rather than leaving implied:
#: "bit 16 last in the low group" and "the SYSTEM variables are emitted first, then the
#: filter's own bits" predict the identical order on every record here, because bits 17-21
#: cost no word in any filter and 22/23 are the only other observable members of the low
#: group. The specimen that would separate them is a record setting a COSTING class bit in
#: 17-21 together with bit 16; the corpus has none. The rule below is the economical one --
#: it predicts, where a growing list of pairs only records.
#:
#: THERE IS NO EXEMPTION. `pixelprocessor` (20) was exempted here, and the exemption was an
#: artefact of THIS module rather than a fact about the format, so the set it lived in is gone
#: rather than left empty. Its header is
#: `[w0][w1 arity][inputs][bit 23][bit 16][the filter's own pixel program]`: the manifest names
#: the first class slot `$randomseed` on 57,731 of 57,731 records that set bit 23 and the second
#: `$outputsize` on 56,141 of 56,142 that set bit 16, and that block ends exactly one slot before
#: the fitted header length on 57,965 of 57,965. The walk used to allocate the pixel program's
#: slot IN FRONT of the class block, which shifted both class labels by one and is what made the
#: filter look like it does not obey the order; the legend states the prefix's position instead
#: (`fixed_at: after_class`) and there is nothing left to exempt.
#:
#: THE LOW GROUP IS `b < 24`, WHICH INCLUDES WORD0's LOW HALF. The legend has no cell on any
#: bit below 16 -- word0's low half is a filter id and two log2 size nibbles (SPEC 6.2), not a
#: presence mask, and a fitted table that offered them as features charged header words to the
#: canvas. They would sort ahead of bit 16 either way, so the key does not have to special-case
#: them, and it must not exclude them: a bit with no cell today and a cell tomorrow belongs in
#: the same group its neighbours are in.
_CLASS_LOW_GROUP_LAST = 16       # the bit that goes last in the low group (bits < 24)


def _class_emission_order(filter_id, clsbits):
    """`(original index, bit)` in EMISSION order.

    The index is the bit's position in `clsbits` and never its emission position. It is kept
    although the legend keys every cell on the BIT: the separation is what stopped a
    reordering of the walk from reordering the lookup while the two were keyed differently,
    and a caller that wants the bit has it in the same tuple.

    `filter_id` is kept in the signature although no filter is exempt: the order is a
    format constant that every filter obeys, and the argument is what a future per-filter
    finding would key on rather than something the caller has to supply for its own sake.
    """
    return sorted(enumerate(clsbits),
                  key=lambda t: (0 if t[1] < 24 else 1,
                                 1 if t[1] == _CLASS_LOW_GROUP_LAST else 0,
                                 t[1]))


def _class_block(r, clsbits, pos, cost):
    """The class block, walked once.

    Returns `(cls_slots, cls_params, pos)`: the slots it allocated, the `(bit, first slot,
    width)` triples for the bits that cost something, and the cursor after the block.

    THIS EXISTS BECAUSE FOUR COPIES OF ONE RULE IS HOW THE RULE GOT MISSED. The block's
    emission order is a format constant (`_class_emission_order`), and it was applied at three
    of the four loops that walked the block: `550de51` routed the interaction and fxmaps
    arms through it, `c70269f` the arity arm, and the additive-spec arm kept iterating
    `sorted(spec['cls'])` for another two commits -- labelling bits 16 and 23 backwards on
    4,280 records across 13 filters, a population partitioned exactly by which branch of this
    module the record reached. There is one arm now and the question cannot recur.
    `walk.py`'s "implemented once" is the repo's claim about the FORMAT, and it has to hold
    of the reader too.
    """
    w0 = r.words[0]
    cls_slots, cls_params = [], []
    for i, b in _class_emission_order(r.filter_id, clsbits):
        if not (w0 >> b) & 1:
            continue
        n = cost(i, b)
        if n > 0:
            cls_params.append((b, pos, n))
        for _ in range(n):
            cls_slots.append(pos)
            pos += 1
    return cls_slots, cls_params, pos


# fxmaps' header opens the way every record does -- w0 (the class word) then w1 -- and its
# fixed prefix is ONE slot sitting BEFORE the image inputs (`fixed_at: before_inputs`): the
# FX tree/table root pointer. The root slot and the first input slot are therefore ONE fact,
# not two, and are derived from those terms rather than both written down. `Record.fx_root`
# resolves the pointer and is the only place the +52 body skew is applied.
FX_ROOT_SLOT = 2


def decompose(r):
    """Structural decomposition of record `r`'s header, or None if uncovered."""
    f = r.filter_id
    if len(r.words) < 1:
        return None
    if f == 5:                               # vectorshape: source geometry, no legend entry,
        # `cls_params` and `size_slot` stated rather than omitted: a caller reading
        # `d.get('cls_params', ())` cannot tell an empty walk from an absent key, and this
        # record has no size slot to place -- not one this walk failed to find.
        return {'inputs': [], 'cls_slots': [], 'param_slots': [], 'cls_params': [],
                'end': None, 'prog': None, 'size_slot': None, 'hdr': 0}
    sp = record_layout.legend().get(str(f))
    if sp is None:
        return None
    ver = r.asm.header.get('version') if isinstance(r.asm.header, dict) else 0
    # A LEGEND ESTABLISHED ON MODERN VERSIONS DOES NOT ANSWER FOR OLDER ONES. `emboss`'s
    # cells were established from 0x50000 up; its 51 older records sit in keys that
    # contradict themselves, and applying the modern reading to them produced a header
    # length nothing had validated. `record_layout.header_words` honours the same gate, and
    # a refusal here is what its docstring says callers must treat as a refusal rather than
    # an answer.
    mv = sp.get('min_version')
    if mv is not None and (ver is None or ver < mv):
        return None
    w0 = r.words[0]
    c0 = w0 & 1
    has = record_layout.has_w1(f, w0, ver)
    if has is None:
        return None                          # the shape is undecidable without a version
    w1 = r.words[1] if (has and len(r.words) > 1) else None
    n_hdr = 1 + (1 if has else 0)
    base = sp['base']
    n_base = n_hdr if base is None else base
    fixed, where = sp['fixed'], sp.get('fixed_at', 'after_inputs')
    width = record_layout.width

    pos = n_hdr
    if where == 'before_inputs':
        pos += fixed                         # fxmaps: the tree root, then the arity run
    # THE IMAGE INPUTS. Either the filter's fixed arity or, for the two filters whose w1
    # holds an input COUNT, that count. Contiguous from the cursor in both cases; fxmaps'
    # edge slots for the records that have any are exactly [3], [3,4,5] and [3..8], never a
    # gap and never a different start.
    ar = sp.get('arity')
    if ar is not None:
        n_in = ((w1 >> ar[0]) & ar[1]) if w1 is not None else 0
    else:
        n_in = n_base
    inputs = list(range(pos, pos + n_in))
    pos += n_in
    # A w1 bit that declares an image INPUT from its LOW BIT alone (SPEC 6.3). One field in
    # one filter: `distance`'s optional mask. It is not part of the end-anchored parameter
    # block and must not be charged a word in it -- doing so begins the block one slot late
    # and silently renames every parameter after it, which is exactly what happened while
    # the fit gave the field its own per-state cell AND the base region placed the edge.
    # The field's costs said so on their own: one word in states 01 and 11 and NOTHING in
    # 10 tracks w1 BIT 0, not baked-versus-program, and no parameter behaves that way. Read
    # across the five w1 codes the corpus holds, bit 0 set (5, 7, 9) gives two edges and
    # clear (6, 10) gives one, 2,277 of 2,277.
    for b in sp.get('edge_bits', ()):
        if w1 is not None and (w1 >> b) & 1 and pos < len(r.words):
            inputs.append(pos)
            pos += 1
    if where == 'after_inputs':
        # The filter's fixed prefix: gradient's and curve's ramp pair, bitmap's pixel word,
        # `text`'s zero + string pointer + font pointer. Every one is a slot some reader
        # already resolves, which is what makes it structural rather than an intercept by
        # another name.
        pos += fixed
    size_pos = pos                           # first slot after the base region

    # THE CLASS BLOCK. One cell per set bit, its width from the legend. `shuffle`'s bit 24
    # joins the block only in the shape that carries no w1 word: the weights are baked there
    # and the selector lives in w1 in the shape that has one (SPEC 6.4).
    cells = {int(b): k for b, k in sp['cls'].items()}
    sh4 = sp.get('shape4')
    if sh4 is not None and not has:
        cells[sh4[0]] = sh4[1]
    cls_slots, cls_params, pos = _class_block(
        r, sorted(cells), pos, lambda _i, b: width(cells[b], c0))
    # SPEC 6.4's paired conjunction: word0's high byte is a small field for `bitmap`, not
    # eight independent flags, and bits 24 and 27 set TOGETHER name the second offset word
    # that locates its pixels. An additive model could only reach that through two halves
    # and a rounding tie.
    for bx, by, cv in sp.get('conj', ()):
        if (w0 >> bx & 1) and (w0 >> by & 1):
            for _ in range(width(cv, c0)):
                cls_slots.append(pos)
                pos += 1
    own_prog = None
    if where == 'after_class':
        # `pixelprocessor`: the filter's own pixel program is the slot right after the class
        # block. The arbiter is the manifest identifier of the graph input each slot's
        # program reads with its first `inputref`, taken by POSITION rather than by the
        # walk's labels: the bit-23 slot names `$randomseed` on 57,731 of 57,731, the bit-16
        # slot `$outputsize` on 56,141 of 56,142, the block ends exactly one slot before the
        # header end on 57,965 of 57,965, and the LAST header slot reads `$pos` (sysvar 8)
        # on 55,595 -- against 105 at the slot the walk used to call the pixel program.
        #
        # The slot is NAMED only when the arity is clean and CHARGED always. Refusing to name
        # it and refusing to charge it are two different things: the 807 records whose arity
        # field this walk declines (a field of 0 under a nonzero w1) still have the word, and
        # the legend still counts it. Guarding the advance left the cursor one short of the
        # header length on exactly those 807.
        valid_arity = n_in >= 1 or (len(r.words) > 1 and r.words[1] == 0)
        own_prog = pos if (valid_arity and pos < len(r.words)) else None
        pos += fixed

    # THE W1 PARAMETER BLOCK, in ascending BIT OFFSET. Each field advances the cursor by
    # its own width; nothing stores a slot number, so a parameter's position is the sum of
    # the widths of the fields before it and cannot be computed from its offset alone.
    #
    # `text`'s BLOCK ORDER IS NOT APPLIED HERE, DELIBERATELY, and the legend records it
    # anyway. SPEC 6.1's second exception is real -- filter 17 lays `matrix22`, `position`,
    # `fontsize`, bits 10, 6, 8, and over the 14 records that bake all three the FIRST four
    # words are a 2x2 matrix on 13 of 14 and the last four on 0 of 14 -- and
    # `render2.model.W1_PARAMS` already implements it, walking its list in the written order
    # rather than sorting it. THIS walk has always emitted ascending, so `param_slots` for
    # those 14 records reads (5, 2w) (7, 1w) (8, 4w) where the exception says (5, 4w)
    # (9, 2w) (11, 1w). Applying it here moves `param_slots` on exactly those 14 records and
    # on nothing else in the corpus -- which is a change to a slot list, not a relabel, and
    # it owes its own A/B and its own render check rather than riding in on a cost-model
    # swap. `legend.json` carries `w1_order` for filter 17 so the fact is stated where the
    # rest of the layout is; the reader that acts on it today is `render2`.
    param_slots = []
    masks = _param_field_masks(f)
    ri = r.index
    if w1 is not None:
        for sh in sorted(int(k) for k in sp['w1']):
            st = (w1 >> sh) & 3
            if st == 0:
                continue
            if st == 1:
                n = width(sp['w1'][str(sh)], c0)
                if n is None:
                    return None              # a baked cell the corpus never exercised
                # ONE ENTRY PER PARAMETER, CARRYING ITS WIDTH -- not one per word. A colour
                # `levels` bakes each level as a Float4, and this loop used to emit four
                # entries for ONE parameter, so a consumer pairing parameter NAMES against
                # these entries misaligned by three from the first colour record it met.
                if n:
                    param_slots.append((sh, st, pos, n))
                pos += n
                continue
            if st == 2:
                # A PROGRAM POINTER IS ONE WORD, IN EVERY FILTER. The fit discovered that
                # per (field, state) and got it wrong where the field was misframed --
                # `emboss` bit 1's program arm came out 0.5 grey / 1.0 colour, which is not
                # a width in any legend.
                param_slots.append((sh, 2, pos, 1))
                pos += 1
                continue
            if _is_image_input(r, sh, pos, masks, ri):
                inputs.append(pos)           # state-11 image input
            else:
                # STATE 3 IS NOT ALWAYS AN IMAGE INPUT, and a word that fails the test is
                # still a word this field occupies. This used to advance `pos` and record
                # NOTHING, so the walk knew the slot was taken but not by what, and every
                # consumer reading `param_slots` was silently short. What actually sits
                # there, over 40 files: blend 88 of 88 a baked value; directionalwarp 60
                # program pointers and 58 baked; emboss 3 and 2. So it is a parameter either
                # way, and recording it as state 3 says exactly that.
                param_slots.append((sh, 3, pos, 1))
            pos += 1

    # `prog` is the slot a reader evaluates for this record's size or first parameter.
    # For every filter but `pixelprocessor` that is the first slot after the base region;
    # for `pixelprocessor` it is the filter's OWN program, which sits after the class block.
    # None only when the record has no such slot: `text` (17) is a source filter and emits
    # glyphs at a baked size; `bitmap` (16) carries a size expression only when tag bit 0 is
    # set, and otherwise slot 2 is image data that can coincidentally parse as a program;
    # and a record whose first post-base slot is itself an image edge (blend's mask-only
    # records) has no size there. Not bounds-checked here: the walk names the slot even when
    # it is past the record's words, and `size_or_baked` does the bounds check.
    if where == 'after_class':
        prog = own_prog
    elif f == 17 or (f == 16 and not (r.cls & 1)) or size_pos in inputs:
        prog = None
    else:
        prog = size_pos
    d = {'inputs': inputs, 'cls_slots': cls_slots, 'param_slots': param_slots,
         'cls_params': cls_params, 'end': _model_end(r, pos), 'prog': prog,
         'size_slot': _size_slot(cls_params), 'hdr': n_hdr}
    if where == 'before_inputs':
        d['root'] = FX_ROOT_SLOT
    return _bounded(r, d)


def _model_end(r, cursor):
    """The header length from `record_layout.header_words`, or the walk's own `cursor`.

    THE TWO ARE NOW THE SAME ARITHMETIC, and that is the change. `header_words` sums the
    legend's widths and this walk lays one slot per word of the same widths, from the same
    base -- so the cursor lands on the model's answer by construction, and the corpus
    confirms it on 903,301 of 903,301 records with a non-None answer.

    IT WAS NOT, AND THE GAP WAS WHERE THE MISPLACEMENTS LIVED. `derive_costs` solved
    `header = const + sum of set-bit costs` with a FREE intercept, and this walk approximated
    that sum by appending one slot per unit of cost -- which cannot express two things the
    fit used: a NEGATIVE coefficient (`range(int(round(-1.0)))` yields nothing rather than
    subtracting) and a `const` that already accounts for the base region (the walk adds
    `n_base` input slots on top of it). Measured by spying on this function's own two
    arguments, before the cost table was re-attributed:

        filter        cursor - model              records
        normal        +2                            1,502
        dyngradient    0 / +1                  105 / 2,392
        distance      +1 / +2                  761 / 1,779
        shuffle        0 / +4                4,028 / 3,781
        emboss        -1, -3, -4, -6         371 / 3 / 3 / 22

    `const` IS AN INTERCEPT, NOT A POSITION, and this walk used it as one -- `pos = max(pos,
    const)` silently mixed "how long is the header" with "where does the block start".
    Predicting the delta as `(n_hdr + n_base) - const` accounted for it exactly on the first
    three; `shuffle`'s residual was its two negative terms and `emboss`'s was a v5 fit
    applied to v2 records. Under the legend there is no intercept to mix up: the base is
    `n_hdr + n_base + n_fixed`, three counts the record itself states.

    THE ASYMMETRY WAS THE BUG. Where `const` EXCEEDED the real base, `max(pos, const)`
    absorbed the difference and the two agreed -- which is why bitmap, curve, gradient and
    text predicted a non-zero delta and measured zero. Only the other direction leaked, and
    it leaked as slots allocated past a length the model believed was shorter: 7,119 records
    placed a CLASS parameter at or past their own header end and `distance` ran a w1
    parameter past it on 2,360 more.

    KEPT AS THE SOURCE OF `end` RATHER THAN TAKING THE CURSOR, because the two being equal
    is a CHECK and not an assumption. `archive/tools/walk_health.py` and `bit_census --check`
    both compare them, and a change that broke the equality would show up there rather than
    being absorbed silently.
    """
    import record_layout
    try:
        hw = record_layout.header_words(
            r.filter_id, r.words[0], r.words[1] if len(r.words) > 1 else None,
            r.asm.header.get('version') if isinstance(r.asm.header, dict) else 0)
    except Exception:
        return cursor
    return cursor if hw is None else hw


def _bounded(r, d):
    """Refuse an `end` that exceeds the record instead of returning it.

    A header cannot be longer than the record containing it, so `end > len(words)` is not a
    gap in the model -- it is the model being WRONG, and every reader that takes a position
    from `end` (blur, sharpen and warp all read `end - 1`) would be reading past the record.
    Those readers already treat a missing `end` as "the walk does not resolve this record"
    and refuse or fall back, so reporting None turns a confidently wrong answer into an
    honest one. `inputs` is kept -- it comes from the record's own shape flags, not from the
    width arithmetic that overran.

    IT NO LONGER FIRES, AND THE RECORD OF WHY IS THE POINT. When this guard was written the
    walk's own accumulated cursor was the `end` it returned, 1,795 of 903,616 records
    over-ran, and shuffle held 1,623 of them with a single cause: its two shapes are told
    apart by tag bit 0, and the cost model expressed the difference with two NEGATIVE terms,
    `cls[0] = -1.0` and `w1_present = -1.0`. This walk appends one slot per unit of cost, so
    it can represent neither, and the header came out exactly 2 too long on all 1,623.

    THE SPLIT BY SHAPE WAS THE PROOF, over all 7,682 shuffle records of the time:

        shape     records    walk end == header_words    walk end > len(words)
        no-w1       3,934          3,934 of 3,934                  0
        w1          3,748              0 of 3,748              1,623

    Perfect agreement on the shape carrying no negative term, none whatsoever on the shape
    carrying two. Under the legend the shape is a `has_w1` rule and neither term exists.

    KEPT ANYWAY, because what it asserts is a fact about the FORMAT and not about any model:
    a header cannot be longer than the record containing it. It costs nothing while it is
    right, and it is the shape of the failure a future legend change would produce.
    """
    n = len(r.words)
    # THE SLOT LISTS ARE BOUNDED TOO, and against the RECORD rather than against `end`.
    #
    # Only `end` and `prog` were checked here, so the lists could name words the record does
    # not contain. Over corpus.paths() plus the reference packs, when this was written:
    #
    #     inputs        0 records name a word past the record
    #     cls_slots  1,738   (shuffle 1,643, dyngradient 74, normal 21)
    #     param_slots   68   (distance 51, normal 17)
    #
    # Re-measured after the four filters' costs were re-attributed, by spying on this
    # function's own argument: cls_slots 0, param_slots 0. The truncation is doing nothing at
    # all any more, because there is nothing left to truncate -- which is what fixing the
    # attribution rather than the symptom looks like from here.
    #
    # AGAINST len(words), NOT AGAINST `end`, and the distinction is the whole judgement.
    # Slots at or past `end` are LEFT ALONE -- there are none today, down from 7,637
    # cls_slots and 3,165 param_slots before the re-attribution, and the rule stays as
    # stated: `end` is a model output, so truncating a slot list against it would bury an
    # overrun instead of leaving it visible. That is exactly how this one stayed hidden.
    # `len(words)` is not a model output -- a word past the end of the record does not
    # exist, and naming it is never right under any width legend.
    #
    # WHAT THIS DOES NOT DO. A slot can also START inside the record and have a WIDTH that
    # runs off the end -- 1,373 `cls_params` and 26 `param_slots`. Those are left, and not
    # for lack of a rule: no consumer reads the width as an extent. All three callers of
    # `render.cls_pair_slot` take `_pair[1]` alone and guard it against `len(rec.words)`
    # themselves, so nothing today would notice whether an over-long width were dropped or
    # clamped. Choosing between those with no consumer to validate against is how a fitted
    # answer gets in, so the number is recorded and the choice is left to whoever adds a
    # reader that needs it.
    if any(s >= n for s in d['cls_slots']) or any(t[2] >= n for t in d['param_slots']):
        d = dict(d,
                 cls_slots=[s for s in d['cls_slots'] if s < n],
                 param_slots=[t for t in d['param_slots'] if t[2] < n],
                 cls_params=[t for t in d.get('cls_params', ()) if t[1] < n])
    if d.get('end') is not None and d['end'] > n:
        return dict(d, end=None, prog=None)
    return d


def named_params(r):
    """Named parameters positionally, replacing the LAYOUTS-memo path of Record.named_parameters.

    The parameters a filter declares (PARAM_SPEC) occupy the LAST n_present slots of the header,
    where n_present is the count of PARAM_SPEC fields the w1 word marks present and NOT as an image
    input (state 11). The boundary is decompose's `end` (= header_words). This is POSITIONAL: it
    never consults the w1 field decomposition, so it is immune to any (filter, field)
    misalignment, and it reads the level VALUES rather than the baked WIDTHS that precede them.

    Returns [(name, kind, value), ...] with kind 'baked'|'program' from the slot itself; [] for
    filters without a PARAM_SPEC, and None where decompose does not cover the record.

    Validated vs the current named_parameters, where the memo has a real answer: directionalwarp
    100.00%, dirmotionblur 99.92%, blend 99.43%, levels 96.26% -- and every disagreement is the
    MEMO being wrong (blend's 1,004 size-expr misattributions, dirwarp's misalignment, levels'
    baked widths), plus ~28k parameters the memo has no key for that this recovers. Better-than-memo,
    so NOT 0-diff; wire only behind a render validation.
    """
    import sbsasm
    if r.filter_id == 4:
        return None                          # fxmaps: parameters come from the table, not the header
    spec = sbsasm.PARAM_SPEC.get(r.filter_id)
    if spec is None:
        return []
    d = decompose(r)
    if d is None or d.get('end') is None:
        return None
    w1 = r.words[1] if len(r.words) > 1 else 0
    present = [nm for _lb, nm in sorted(
        (p & -p, nm) for nm, p, _pg in spec if (w1 & p) and (w1 & p) != p)]
    if not present:
        return []
    end = d['end']
    prog = d['prog']
    if r.filter_id == 15 and prog is not None:
        # levels' values are read FORWARD from a start, with the baked WIDTHS trailing. When
        # the tag is ODD the values sit right after the cls-slot region (start = last cls slot
        # + 1; a set cls bit 7 adds a slot and pushes it); when EVEN they sit at/before the
        # size slot (prog, shifted back one when leveloutlow is present, which occupies
        # prog-1). 99.83% vs the memo. The residual 0.17% is per-record: the SAME present set
        # lands at different starts in different records, i.e. the memo's own fitting, not a
        # structural rule -- and render-neutral (all-packs refcompare, 0 worse).
        cls_slots = d['cls_slots']
        if r.cls & 1:
            start = (max(cls_slots) + 1) if cls_slots else prog + 1
        else:
            start = prog - 1 if 'leveloutlow' in present else prog
        slots = range(start, start + len(present))
    else:
        slots = range(end - len(present), end)
    return [r._read_slot(nm, s) for nm, s in zip(present, slots) if 2 <= s < len(r.words)]
