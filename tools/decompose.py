"""One structural walk of a record header, replacing the five layout special cases.

The format is a single struct (record_layout's model):

    [tag][w1?][image inputs, contiguous][one slot per set cls bit][one slot-group per w1 field][tail]

`decompose(record)` walks it once and returns {inputs, cls_slots, param_slots, end}, from which
`param_slots` entries are (w1 field, state, first slot, WIDTH IN WORDS) -- one per parameter,
edges (= inputs), the size slot, named parameters and program slots all follow. It reads the slot
COSTS from record_layout's cost model (costs.json), so it inherits that model's per-filter fit
rather than re-deriving anything. Returns None only for the single unnamed filter-9 record, so
callers fall back there; fxmaps decomposes via _fxmaps_walk.

Validated against `_compute_layout` + `_real_edges` DIRECTLY (the independent model, which reads the
SPECS/_ruled/EDGES tables and never touches costs.json): 925,706 records, 925,701 agree, 0 disagree,
5 uncovered (filter 9). fxmaps prog == _compute_layout prog 41,164/41,164.

VALIDATION MUST GO THROUGH `_compute_layout`, NEVER THROUGH `edge_slots` OR `Record.layout`. Both of
those now call decompose, so `decompose(r)['inputs'] == r.edge_slots` and `decompose(r)['prog'] ==
r.layout[1]` are decompose compared against itself -- they return 100% by construction and prove
nothing. This trap already bit twice (an edges number and an fxmaps-prog number, both circular and
both silently passing). Compare against `_compute_layout()` / `_real_edges()` / `_pp_edges()`, the raw
words, or the render. See FORMAT-NOTES.md "Unified walk".
"""
import record_layout


def _param_field_masks(f):
    """The exact PARAM_SPEC presence masks for this filter. A cost-model w1 field reading 0b11
    is a genuine image input only when its 2-bit range EXACTLY equals one of these masks (an
    aligned named field, e.g. blend's opacitymult). An unnamed field, or a misaligned overlap of
    two params (directionalwarp's intensity/warpangle), is not an edge."""
    import sbsasm
    return {pres for _nm, pres, _prog in sbsasm.PARAM_SPEC.get(f, ())}


# Whether a state-3 w1 field is an image input is a LAW OF (filter, field), not a per-record
# question. Measured by INSTRUMENTING THIS FUNCTION over the full 437-file corpus -- wrapping it
# and recording every (filter, field, answer) it is actually asked -- rather than by re-deriving
# slot positions in a separate script. That distinction is not pedantry: the first version of this
# table WAS built by re-derivation, and it was wrong. That script called `_select_spec` with
# `getattr(asm, 'version', None)`, which is not the `ver` decompose passes internally, so it
# selected a DIFFERENT spec variant with different w1 keys and dutifully measured six
# (filter, field) pairs -- (1,0), (3,0), (3,4), (3,5), (3,12), (7,0) -- that the walk never visits
# at all. It reported blend field 0 as a 130,767-record "mixed" case needing its own rule; the
# walk never asks about blend field 0. Instrument the real call, do not reconstruct it.
#
# Every decision this function is genuinely asked to make, full corpus, 10,430 calls:
#
#     f=1  j=2   8,486   ALWAYS input   -- and it never reaches this table: its 2-bit range
#                                          equals blend's PARAM_SPEC mask 0x30 exactly, so the
#                                          aligned test above answers it structurally first.
#     f=1  j=4     963   never input    f=1  j=5      7   never input
#     f=8  j=1      87   never input    f=12 j=1    838   never input
#     f=12 j=2       2   never input    f=21 j=0     47   never input
#
# So the split is 8,486 aligned (81.4%) against 1,944 that fell to the old value probe (18.6%),
# and the probe returned False for all 1,944 of them -- its entire job was saying "no". An earlier
# draft of this comment claimed 95.6% probe-decided; that came from the broken re-derivation above
# and is retracted.
#
# Note what is NOT needed here: `distance`'s unnamed input, cited by the old docstring as the case
# that made a value probe unavoidable, is f=21 j=0 and is never an input -- distance's optional
# mask is declared structurally by w1 bit 0 in `decompose` and never reaches this function.
INPUT_FIELDS = {
    (1, 2): True,
    (1, 4): False, (1, 5): False,
    (8, 1): False,
    (12, 1): False, (12, 2): False,
    (21, 0): False,
}


def _is_image_input(r, j, pos, masks, ri):
    """Is a state-3 (0b11) w1 field at cost-model index `j`, slot `pos`, a real image input?

    Answered from the HEADER ONLY -- the aligned PARAM_SPEC mask, then the per-(filter, field)
    law in `INPUT_FIELDS`, then blend field 0's bits-4|5 rule. The slot's VALUE is never
    consulted.

    It used to end with `0 < r.words[pos] < ri` -- "the slot holds something that looks like a
    backward record index, so call it an input". That decided 1,944 of 10,430 state-3 fields
    (18.6%), and answered False every single time. It also made the two value probes in
    `Record.edges` score a perfect zero, since they re-tested the very predicate that had selected
    the slots -- a tautology, not a confirmation, which is why removing them changed nothing.

    The residual `_probe_fallback` list records any (filter, field) pair this table has never
    seen. It is empty on this corpus; entries appearing on a new one are a finding to investigate,
    not a slot to guess at. It caught (8, 1) exactly this way -- 87 calls the first table missed,
    surfaced instead of silently probed."""
    if (3 << (2 * j)) in masks:
        return True
    known = INPUT_FIELDS.get((r.filter_id, j))
    if known is not None:
        return known
    _probe_fallback.append((r.filter_id, j))
    return pos < len(r.words) and 0 < r.words[pos] < ri


# Every (filter, field) the table above does not cover, appended as it is hit. Empty on the
# 437-file corpus; inspect it rather than trusting the fallback if it fills on a new one.
_probe_fallback = []

# Per-filter base image-input arity: how many input images the filter consumes before any
# w1-declared inputs. A format fact (like the blend-mode table), not a fitted memo entry.
BASE_INPUTS = {
    0: 1, 1: 2, 2: 1, 3: 1, 7: 2, 8: 2, 10: 1, 11: 1, 12: 2,
    13: 1, 14: 1, 15: 1, 16: 0, 17: 0, 18: 1, 19: 2, 21: 1, 22: 1,
    # 16 bitmap / 17 text are source-side: no image inputs. shuffle (3) is two-shape, handled
    # in decompose; vectorshape (5) has no header cost model (source geometry, no edges).
}


def _select_spec(f, w0, w1, ver):
    spec = record_layout.costs().get(str(f))
    if spec is None:
        return None
    # A SPEC FITTED ON MODERN VERSIONS DOES NOT ANSWER FOR OLDER ONES. `derive_costs` records
    # `min_version` for the filters whose costs it could only establish above some version,
    # and `record_layout.header_words` honours it by returning None -- "this filter's costs
    # were not established", which its docstring says callers must treat as a refusal rather
    # than an answer. This did not honour it, so `emboss`'s v5+ fit was applied to v2 records
    # and produced a header length nothing had validated.
    #
    # It shows up as exactly one violation in 682,887 records of the pointer bound -- the
    # walk's header end running PAST a program the record itself points at -- on
    # BrickWall_02 record 330, a v2 file. That record's additive total is 6.5 words, a
    # literal half charged by `base[0] = 4.5` on the colour flag, and the rounding tie goes
    # to 11 where the record's own pointer says 10. Halves are the model conceding it cannot
    # express the rule; applying one outside its fitted range is where the tie broke wrong.
    mv = spec.get('min_version')
    if mv is not None and (ver is None or ver < mv):
        return None
    for v in spec.get('variants', ()):
        g = v.get('guard')
        if g is None or (w0 >> g['shift']) & g['mask'] == g['value']:
            return v
    return None if 'variants' in spec else spec


def _has_w1_word(f, w0, ver):
    """record_layout's w1-presence rule for the two-shape filters, or None if not two-shape.

    DELEGATED, not reimplemented. This carried its own copy of the warp and shuffle gates,
    which is precisely the duplication `record_layout.header_words` warns about -- "a rule
    the caller can forget is a rule in the wrong place". Two copies is that same failure one
    step later: the gate lived in two files and only one of them said so.
    """
    if f not in (3, 7):
        return None
    eff = record_layout.two_shape_w1(f, w0, 1, ver)
    if eff is record_layout.W1_REFUSE:
        return None                  # undecidable without a version: fall to the spec's mode
    return eff is not None


# A w1 parameter whose two-bit code does NOT sit on the tiling's even-bit grid.
#
# `pairs` are FIELD INDICES and `_interaction_walk` reads each as `(w1 >> (2 * pj)) & 3`, so
# a field can only begin at an EVEN bit. `transformation`'s offset begins at bit 25. Its
# code therefore SPLITS across two tiling fields -- 12 (bits 24,25) takes the code's low bit
# as its HIGH bit, 13 (bits 26,27) takes the code's high bit as its LOW bit -- and each half
# then looks like a different parameter that is always the same thing: field 12 can only
# ever read 0b10 and field 13 can only ever read 0b01. That is the "one phantom field that
# always looks like a value and one that always looks like a pointer" FORMAT-NOTES records,
# and it is an artefact of the FRAME, not something the file says.
#
# MEASURED over 242,931 filter-2 records (corpus + reference packs):
#
#     the code read at bits (25,26)   absent 144,245   01 baked 29,404   10 program 69,282
#                                     11 NEVER
#     bits 24 and 27                  NEVER SET, neither of them, in any record
#     tiling field 12 states           only 0 and 2     tiling field 13 states  only 0 and 1
#
# Bit 24 never being set is exactly why field 12 can never read 01, and bit 27 never being
# set is why field 13 can never read 10. Read at shift 25 the pair is the format's ordinary
# alphabet -- 01 baked, 10 program, mutually exclusive, 11 absent -- which is what
# `Record.translation` and `walk.SPECS[2]`'s `(0x06000000, 25, 2)` have both said all along.
# The two halves are RELABELLED as one field below; their EXTENTS are untouched, because the
# cost model fitted a width to each half separately and both are already right (2 words for
# the baked Float2 under field 12, 1 word for the pointer under field 13).
#
# COMPLETE FOR ONE SIGNATURE, NOT FOR MISALIGNED GRIDS GENERALLY -- and the difference is
# not pedantic, because a second misaligned filter exists and this sweep cannot see it.
#
# What was swept for: an ADJACENT pair -- tiling field j that can only ever read 0b10,
# field j+1 that can only ever read 0b01, outer bits 2j and 2j+3 never set. Over the corpus
# plus the reference packs, across every filter carrying a `pairs` list, that occurs exactly
# ONCE: transformation 12,13. Several fields match one HALF of it (transformation 14,
# fxmaps 1/4/13, emboss 0, levels 5) and none is a straddle -- a field whose only nonzero
# state is 1 is a parameter that is always baked, and one whose only nonzero state is 2 is
# always a program. Calling those framing errors would invent six fields the file does not
# have; only the adjacent pair is evidence.
#
# WHAT THE SWEEP MISSES, concretely. `directionalwarp`'s grid is off by one too (35f1a93):
# its parameters sit at bits (1,2) and (3,4), so the misalignment runs across a SEQUENCE
# rather than sitting in one parameter with dead bits either side. Two independent reasons
# this sweep is blind to it -- dirwarp's cost spec has no `pairs` list at all, so it was
# never tested; and its middle field spans intensity's HIGH bit and warpangle's LOW bit,
# two DIFFERENT parameters, so it takes state 3 and fails the "only ever 0b01" test.
#
# AND IT MUST NOT BE ADDED HERE, which is the substantive point rather than a scoping
# caveat. This relabelling is only sound because each of transformation's two halves has a
# fitted width equal to the WHOLE parameter's: field 12 state 2 costs 2 words (the baked
# Float2) and field 13 state 1 costs 1 word (the pointer), so re-labelling recovers the
# parameter exactly and touches no extent. dirwarp's fitted costs are SUMS ACROSS PARAMETER
# BOUNDARIES -- `costs.json` gives its field 1 a state-3 width of 2.0, which is
# intensity-as-program (1) plus warpangle-baked (1) -- so no relabelling can recover the two
# extents from the one number. That filter needs the cost model re-derived on the right
# grid, and until then counting back from `end` is the only available reading, because the
# model's total is right where its per-field attribution is not.
#
# {filter: [(low tiling field, high tiling field, real shift, field id to report)]}
STRADDLED = {2: [(12, 13, 25, 12)]}


def _restraddle(r, w1, param_slots):
    """Relabel a straddled pair as the one field it is. Positions and widths unchanged."""
    for lo, hi, shift, fid in STRADDLED.get(r.filter_id, ()):
        code = (w1 >> shift) & 3
        if code not in (1, 2):
            continue
        param_slots = [(fid, code, pos, n) if j in (lo, hi) else (j, st, pos, n)
                       for (j, st, pos, n) in param_slots]
    return param_slots


def _interaction_walk(r, s):
    """Colour-interaction spec: per-feature slot count = base[i] + (tag bit 0)*cross[i]."""
    w0 = r.words[0]
    w1 = r.words[1] if len(r.words) > 1 else 0
    c0 = w0 & 1
    base, cross = s['base'], s['cross']
    clsbits, pairs = s['clsbits'], s['pairs']
    states_only = s['interaction'] == 'colour_states'

    def cost(idx, is_state):
        if idx >= len(base):
            return 0
        x = cross[idx] if (idx < len(cross) and (not states_only or is_state)) else 0.0
        return int(round(base[idx] + c0 * x))

    pos = cost(0, False)
    size_pos = pos                           # first slot after the base region = size-expr slot
    inputs = list(range(2, pos))
    cls_slots = []
    cls_params = []
    for i, b in enumerate(clsbits):
        if (w0 >> b) & 1:
            n = cost(1 + i, False)
            if n > 0:
                cls_params.append((b, pos, n))
            for _ in range(n):
                cls_slots.append(pos); pos += 1
    off = 1 + len(clsbits)
    if s.get('has_absent'):
        off += 1
    if s.get('arity_sm') is not None:
        off += 1
    param_slots = []
    masks = _param_field_masks(r.filter_id)
    ri = r.index
    for k, pj in enumerate(pairs):
        st = (w1 >> (2 * pj)) & 3
        if st == 0:
            continue
        idx = off + 3 * k + (st - 1)
        n = cost(idx, True)
        if st in (1, 2):
            # ONE ENTRY PER PARAMETER, CARRYING ITS WIDTH -- not one per word. A colour
            # `levels` bakes each level as a float4, so this loop used to emit
            # (0, 1, 4), (0, 1, 5), (0, 1, 6), (0, 1, 7) for ONE parameter, and a consumer
            # pairing parameter NAMES against these entries misaligned by three from the
            # first colour record it met. The walk placed them correctly throughout; only
            # the report of where they are was wrong. See `levels`' widths in costs.json:
            # state 1 is base 1 + cross 3, so 1 word greyscale and 4 colour, and state 2
            # (a program POINTER) is 1 word either way.
            if n:
                param_slots.append((pj, st, pos, n))
            pos += n
            continue
        for _ in range(n):
            if _is_image_input(r, pj, pos, masks, ri):
                inputs.append(pos)             # state-11 image input
            else:
                # STATE 3 IS NOT ALWAYS AN IMAGE INPUT, and a word that fails the test is
                # still a word this field occupies. This used to advance `pos` and record
                # NOTHING, so the walk knew the slot was taken but not by what, and every
                # consumer reading `param_slots` was silently short.
                #
                # It is what hid emboss BrickWall_02 record 330's four floats -- 0.125 and
                # 0.196 three times under a set colour flag, a per-channel Float4 by
                # SPEC 6.4 -- from the slot-by-slot accounting while the walk still charged
                # their width to `end`.
                #
                # What actually sits there, over 40 files: blend 88 of 88 a baked value;
                # directionalwarp 60 program pointers and 58 baked; emboss 3 and 2. So it is
                # a parameter either way, and recording it as state 3 says exactly that --
                # the field is present and occupied, its kind is what the pointer test just
                # declined to call an edge. Nothing is recovered that was lost: every one of
                # those program pointers is already in `Record.programs`, which scans the
                # header slots. What changes is that the slot is ACCOUNTED.
                param_slots.append((pj, 3, pos, 1))
            pos += 1
    prog = None if size_pos in inputs else size_pos
    param_slots = _restraddle(r, w1, param_slots)
    return _bounded(r, {'inputs': inputs, 'cls_slots': cls_slots,
                        'param_slots': param_slots, 'cls_params': cls_params,
                        'end': _model_end(r, pos), 'prog': prog})


# fxmaps' header opens the way every record does -- w0 (the class word) then w1 -- and
# `walk.SPECS[4]` gives it `Arity(prefix=1)`: exactly ONE fixed non-edge slot between the
# masks and the image inputs, which is the FX tree/table root pointer. The root slot and the
# first input slot are therefore ONE fact, not two, and are derived from those terms here
# rather than both written down. `Record.fx_root` resolves the pointer and is the only place
# the +52 body skew is applied.
_FX_MASK_WORDS = 2                                # w0, w1
_FX_PREFIX = 1                                    # walk.Arity(prefix=1) -- the root pointer
FX_ROOT_SLOT = _FX_MASK_WORDS                     # = 2
_FX_FIRST_INPUT = _FX_MASK_WORDS + _FX_PREFIX     # = 3


def _fxmaps_walk(r, spec):
    """fxmaps: slot 2 is the TABLE POINTER, and w1 carries the image-input count.

    The interaction spec covers this filter's slot COSTS but not its roles: run through
    `_interaction_walk` it reports slot 2 as an image input and finds none of the real ones,
    which is why filter 4 used to be declined outright. Two facts fix it, and both are
    exact over 25 corpus files, 1,535 records:

      * The input COUNT is the cost model's own `arity_sm` field -- shift 10, mask 15 --
        read from w1, not w0:

            edges 0 -> field 0   1,365      edges 3 -> field 3       4
            edges 1 -> field 1      50      edges 6 -> field 6     116

        1,535 of 1,535, no exceptions, and w0's field at the same position is noise
        (edges 0 spread across fields 0,1,2,4,5,8,9,10,13,14).

      * The inputs are CONTIGUOUS FROM SLOT 3. Layout's edge slots for the records that
        have any are exactly [3], [3,4,5] and [3,4,5,6,7,8] -- never a gap, never a
        different start. Slot 2 sits before them and holds the FX table pointer, and the
        interaction walk independently places the first structural slot at 2 in 1,305 of
        1,305 -- the cost model corroborating it rather than the reader assuming it.

        THAT SLOT IS NOW REPORTED, as `root`. It used to be re-derived by every reader in
        the fx path as `words[2] + 52` -- four of them: `Record.fx_tree`,
        `Record.fx_entry_walk`, `node_census.harvest` and `reverify`. A slot number copied
        into four files is the shape of thing this walk exists to delete, and the copies
        cannot disagree with the walk about fxmaps only because nobody has changed one of
        them yet. `Record.fx_root` is the single reader now.
    """
    w1 = r.words[1] if len(r.words) > 1 else 0
    shift, mask = spec['arity_sm']
    # THE COUNT FIELD IS SIX BITS, NOT THE LOW NIBBLE, and the cost model now states it that
    # way -- `arity_sm` is (shift 10, mask 63). It read (10, 15) until 424f507, and a 4-bit
    # mask TRUNCATES the count on records declaring more than 15 inputs, reporting the
    # remainder rather than failing: `ie_curve` record 35 states 34 and read back 2; 57
    # states 19 and read 3; 79 states 20 and read 4. This function carried a local
    # `mask = max(mask, 0x3F)` while the widening lived on `main` and the working branch
    # still had 15; the refs met at dfa2c19 and the line is gone. Removing it is a no-op
    # against the current model, measured rather than assumed: 41,164 fxmaps records
    # identical, 0 differing.
    #
    # Widened on the PROG INVARIANT, which is structural and can fail: layout[1] is 3 + n_in
    # for this filter, and that slot's word + 52 must resolve to a valid program. A truncated
    # count lands `end` inside the edge run, where the word is a small record index and +52 is
    # not a program. Over the full corpus, 41,164 fxmaps records:
    #
    #     4 bits   41,118 hold the invariant       6 bits   41,128
    #     7 and 8 bits gain nothing over 6, so 6 is the width, not merely a wider guess
    #
    #     both widths hold  41,118    6-bit only  10    4-bit only  0    neither  36
    #
    # No record that held at 4 bits fails at 6, so this is a strict gain. The 36 that hold at
    # neither width are a different population and are not addressed here.
    #
    # The docstring's "1,535 of 1,535 over 25 corpus files" is not contradicted: those 25 files
    # contain no fxmaps declaring more than 15 inputs, so the nibble was sufficient there and
    # the sample could not see the truncation.
    n_in = (w1 >> shift) & mask
    inputs = list(range(_FX_FIRST_INPUT, _FX_FIRST_INPUT + n_in))
    # layout[1] for fxmaps is 3 + input count (the first slot after the inputs = end), exact over
    # 41,164 records / 14 distinct input counts -- the same "first slot after the base region" as
    # the main path's size_pos, verified by cleanroom-substance-00.
    end = _FX_FIRST_INPUT + n_in
    return {'inputs': inputs, 'cls_slots': [], 'param_slots': [], 'cls_params': [],
            'end': end, 'prog': end,
            'root': FX_ROOT_SLOT}


def decompose(r):
    """Structural decomposition of record `r`'s header, or None if uncovered."""
    f = r.filter_id
    if len(r.words) < 1:
        return None
    if f == 4:
        spec = _select_spec(f, r.words[0], r.words[1] if len(r.words) > 1 else None, 0)
        if spec is None or not spec.get('arity_sm'):
            return None
        return _fxmaps_walk(r, spec)
    if f == 5:                               # vectorshape: source geometry, no header cost model,
        return {'inputs': [], 'cls_slots': [], 'param_slots': [], 'end': None, 'prog': None}  # no inputs
    ver = r.asm.header.get('version') if isinstance(r.asm.header, dict) else 0
    w0 = r.words[0]
    spec = _select_spec(f, w0, r.words[1] if len(r.words) > 1 else None, ver)
    if spec is None:
        return None
    if spec.get('interaction') in ('colour', 'colour_states'):
        return _interaction_walk(r, spec)
    if 'const' not in spec or 'cls' not in spec or 'w1' not in spec:
        return None
    if spec['const'] is None:
        return None                          # fxmaps payload: no header cost model

    tw = _has_w1_word(f, w0, ver)
    has_w1 = tw if tw is not None else (spec.get('mode') != 'absent')
    const = spec['const']

    if spec.get('mode') == 'arity':          # pixelprocessor: w1 is an input-count integer
        ar = spec.get('arity') or {}
        # The arity FIELD is 5 bits (0..16): a 4-bit mask reads 16 (0x10) as 0. The cost model
        # fits a 4-bit mask (arity 16 is one record), but the input count needs the full field.
        mask = ar.get('mask', 0) | (ar.get('mask', 0) + 1)   # widen 0xf -> 0x1f
        n_in = ((r.words[1] >> ar.get('shift', 0)) & mask) if len(r.words) > 1 else 0
        pos = 2
        inputs = list(range(pos, pos + n_in)); pos += n_in
        # pixelprocessor's program is the slot RIGHT AFTER the inputs (layout: 2 + edge count) --
        # the pixel program, not a size expression pushed past the const region. layout names it
        # only when the arity is clean: _pp_edges reads the 5-bit field and declines a field of 0
        # whose word is nonzero (e.g. 0x10000 -> arity 0 with a stray high bit), leaving prog None;
        # a nonzero field with high bits (0x10001 -> arity 1) is fine.
        valid_arity = n_in >= 1 or (len(r.words) > 1 and r.words[1] == 0)
        prog = pos if (valid_arity and pos < len(r.words)) else None
        # ADVANCE PAST THE PROGRAM SLOT. This line was missing, and `const` hid it for
        # exactly the records where it did not matter: const is 3, so at arity 0 the walk
        # goes pos=2 -> prog=2 -> max(3, 3) = 3 and the class slots start correctly at 3.
        # At any arity >= 1, pos is already 2+arity >= 3, `const` bumps nothing, and the
        # first class slot is allocated ON TOP OF the program slot -- so every later slot,
        # and `end` with them, sits one word too low.
        #
        # Corpus-wide: 55,255 of 57,965 pixelprocessor records (95.3%) had `prog` colliding
        # with a class slot, and in 55,254 of those the slot at the too-low `end` holds a
        # VALID PROGRAM -- the record's real pixel program, excluded from its own header.
        # Confirmed against the cost model's own independent total: `decompose`'s end was
        # -1 against `record_layout.header_words` on 5,259 of 5,490 records, and equal on
        # the 231 (the arity-0 ones) where `const` happened to cover for it.
        #
        # This is what put UHL3D-Stylized_Sand record 2194's pixel program OUTSIDE its
        # header, so `programs()` could only reach it through the word scan -- and left it
        # looking like a record whose program samples an input its arity does not declare.
        if prog is not None:
            pos += 1
        pos = max(pos, int(round(const)))
        cls_slots = []
        cls_params = []
        for b in sorted(int(k) for k in spec['cls']):
            if (w0 >> b) & 1:
                n = int(round(spec['cls'][str(b)]))
                if n > 0:
                    cls_params.append((b, pos, n))
                for _ in range(n):
                    cls_slots.append(pos); pos += 1
        return _bounded(r, {'inputs': inputs, 'cls_slots': cls_slots, 'param_slots': [],
                            'cls_params': cls_params, 'end': _model_end(r, pos),
                            'prog': prog})

    if f not in BASE_INPUTS:
        return None                          # fxmaps payload / uncovered small shapes

    w1 = r.words[1] if (has_w1 and len(r.words) > 1) else None
    n_hdr = 1 + (1 if has_w1 else 0)
    # shuffle's two shapes carry a different input count: the no-w1 shape takes one image at
    # slot 1, the w1 shape takes two at slots 2-3, so its base arity is n_hdr.
    n_base = n_hdr if f == 3 else BASE_INPUTS[f]
    pos = n_hdr
    inputs = list(range(pos, pos + n_base)); pos += n_base
    # distance takes an optional SECOND (mask) base input, declared STRUCTURALLY by w1 bit 0
    # (walk.py:215 states `[2,3] if w1 & 1 else [2]`; verified 2,277/2,277 by 00). This replaces a
    # value probe on the slot -- right on this corpus only because it tracked w1 bit 0, but a probe
    # with a 1-in-4 false-positive rate in isolation. Read the flag, not the value.
    if f == 21 and (r.words[1] & 1) and pos < len(r.words):
        inputs.append(pos); pos += 1
    pos = max(pos, int(round(const)))        # skip ramp/table base structure (gradient/curve)
    size_pos = pos                           # first slot after the base region = size-expr slot
    cls_slots = []
    cls_params = []
    for b in sorted(int(k) for k in spec['cls']):
        if (w0 >> b) & 1:
            n = int(round(spec['cls'][str(b)]))
            if n > 0:
                cls_params.append((b, pos, n))
            for _ in range(n):
                cls_slots.append(pos); pos += 1
    for bx, by, cv in spec.get('conj', ()):
        if (w0 >> bx & 1) and (w0 >> by & 1):
            for _ in range(int(round(cv))):
                cls_slots.append(pos); pos += 1
    # w1 fields after the cls slots, in field order: state-3 = image input (validated by the
    # backward-index invariant), state-01/10 = parameter.
    param_slots = []
    masks = _param_field_masks(f)
    ri = r.index
    # Field j sits at bit 2j + w1_shift -- 0 everywhere but `directionalwarp`, whose
    # parameters begin at bit 1. See `derive_costs.W1_GRID_SHIFT`.
    #
    # READ OUTSIDE THE `w1 is not None` GUARD, because the return reports it unconditionally.
    # Assigning it inside raised `UnboundLocalError` on every record whose slot 1 is an EDGE
    # rather than a w1 mask -- gradient, warp, blur, bitmap, shuffle, dyngradient, sharpen,
    # curve and hsl, 5,017 of 66,699 records over 40 files -- which is a whole class of
    # filter, not an edge case. `w1_shift` is a property of the SPEC and is well defined
    # whether or not the record carries a w1 word.
    gsh = int(spec.get('w1_shift', 0))
    if w1 is not None:
        for j in sorted(int(k) for k in spec['w1']):
            st = (w1 >> (2 * j + gsh)) & 3
            if st == 0:
                continue
            n = int(round(spec['w1'][str(j)].get(str(st), 0.0)))
            if st in (1, 2):
                # One entry per parameter, carrying its width -- see `_interaction_walk`.
                if n:
                    param_slots.append((j, st, pos, n))
                pos += n
                continue
            for _ in range(n):
                if _is_image_input(r, j, pos, masks, ri):
                    inputs.append(pos)         # state-11 image input
                else:
                    param_slots.append((j, 3, pos, 1))   # occupied, just not an edge
                pos += 1
    # prog = the size-expression slot (what size_or_baked reads) = the first slot after the base
    # region (the first cls slot when there is one). None only when that slot is itself an image
    # input edge (blend's mask-only records). Not bounds-checked here: layout names the slot even
    # when it is past the record's words, and size_or_baked does the bounds check.
    # text (17) is a source filter -- it emits glyphs at a baked size, with no size-expression slot.
    # bitmap (16) carries a size expression only when tag bit 0 is set; otherwise slot 2 is image
    # data (which can coincidentally parse as a program), and layout reports no size.
    prog = None if (f == 17 or (f == 16 and not (r.cls & 1)) or size_pos in inputs) else size_pos
    # `w1_shift` is REPORTED rather than left for callers to look up again. A consumer
    # matching a PARAM_SPEC mask to a field has to know which grid the fields are on, and
    # re-deriving it means re-selecting the spec with arguments the caller has to
    # reconstruct -- the failure `INPUT_FIELDS` above documents at length. The walk knows
    # it; the walk says it.
    return _bounded(r, {'inputs': inputs, 'cls_slots': cls_slots,
                        'param_slots': param_slots, 'cls_params': cls_params,
                        'w1_shift': gsh,
                        'end': _model_end(r, pos), 'prog': prog})


def _model_end(r, fallback):
    """The header length from `record_layout.header_words`, or `fallback`.

    THE WALK AND THE MODEL ARE NOT THE SAME ARITHMETIC, and where they differ the model is
    the one that was fitted. `derive_costs` solves `header = const + sum of set-bit costs`
    against boundaries observed in the file, and keeps a filter only if the rounded costs
    reproduce EVERY observed header exactly -- it currently does so for 21 filters at
    100.000%, covering 99.98% of records, `shuffle`, `distance`, `dyngradient`, `normal`,
    `uniform` and `emboss` among them. `header_words` evaluates that sum directly. This walk
    approximates it by appending one slot per unit of cost, which cannot express two things
    the fit uses: a NEGATIVE coefficient (`range(int(round(-1.0)))` yields nothing rather
    than subtracting) and a `const` that already accounts for the base region (the walk adds
    `n_base` input slots on top of it).

    Both show up as disagreement on exactly six filters and nowhere else -- 852,238 records
    agree, and `blur`, `sharpen` and `warp`, whose `end - 1` reads are verified by
    containment on 15,371, 1,323 and 13 records, are all in the agreeing set, so taking the
    model's answer changes nothing there.

    Containment settles the direction independently where it can reach: `normal` record 362
    declares 2.01 at slot 4, and `header_words - 1` is 4 while the walk's `end - 1` is 6.

    EVERY BOUND DISAGREEMENT, ENUMERATED, AND THE CAUSE IS ONE CATEGORY ERROR. Measured by
    spying on this function's own two arguments over corpus.paths() plus the reference packs,
    the walk's accumulated cursor against the model's length:

        15 filters agree on 884,351 records -- bitmap, transformation, uniform, blend,
        levels, gradient, directionalwarp, warp, hsl, blur, dirmotionblur, pixelprocessor,
        curve, sharpen, text.

        filter        cursor - model              records
        normal        +2                            1,502
        dyngradient    0 / +1                  105 / 2,392
        distance      +1 / +2                  761 / 1,779
        shuffle        0 / +4                4,028 / 3,781
        emboss        -1, -3, -4, -6         371 / 3 / 3 / 22

    `const` IS AN INTERCEPT, NOT A POSITION, and this walk uses it as one. The fit solves
    `header = const + sum of set-bit costs`; nothing in that equation says the first slot sits
    at index `const`. The walk's base is a structural fact -- `n_hdr` mask words plus `n_base`
    image inputs -- and `pos = max(pos, const)` silently mixes the two. Predicting the delta
    as `(n_hdr + n_base) - const` accounts for it exactly:

        normal        predicted +2, measured +2      1,502 of 1,502
        dyngradient   predicted +1, measured +1      2,392 of 2,392
        distance      predicted +1, measured +1        761 of 761

    and the two residuals are the representational gaps already named above, each adding to
    that base term rather than replacing it:

        distance +2   the OPTIONAL mask input this walk appends after the base (1,779 records)
        shuffle  +4   the base term (+2) plus two NEGATIVE cost terms it cannot subtract (+2)

    THE ASYMMETRY IS THE BUG. Where `const` EXCEEDS the real base, `max(pos, const)` absorbs
    the difference and the two agree -- which is why bitmap, curve, gradient and text predict
    a non-zero delta and measure zero. Only the other direction leaks, and it leaks as slots
    allocated past a length the model believes is shorter.

    FOR `normal` IT IS NOW SETTLED, AND THE MODEL WINS. That rested on one specimen and now
    rests on eight, found by matching the exact float32 bit pattern within each file instead
    of demanding a corpus-unique three-decimal value -- see `param_slots.declared`. Across
    eight different packages:

        seven records, cls 0x0b19   intensity at slot 5, model end 6
        one record,    cls 0x0319   intensity at slot 4, model end 5

    Intensity is at `end - 1` in 8 of 8, so the model's LENGTH is right and this walk's
    cursor is wrong by exactly the +2 the intercept term predicts. The cursor puts normal's
    parameter at slot 7 (or 6) where the file puts it at 5 (or 4), and its last cls slot
    already sits at or past the model's end. `param_slots.predicted_slot` also lands on 8 of
    8, so the two independent rules agree with each other and with the file.

    That does not license truncating the slot lists against `end` generally: it is one filter,
    and `shuffle`'s +4 still carries two negative cost terms this walk cannot represent at
    all. But the direction is no longer open for normal.

    `emboss` is not this. It is the only filter whose cursor runs SHORT, and it is attributed
    elsewhere -- a v5 fit applied to v2 records.

    The SLOT LISTS are left as the walk built them. They are this function's own
    accumulation and a position in them can now exceed `end`; that is a true statement about
    the walk rather than something to paper over, and every consumer already bounds slots by
    the record.

    THAT LAST CLAUSE WAS AUDITED, and it holds -- but for two accidental reasons rather than
    by construction, so it should not be leaned on. First the size of the thing being
    claimed, over the corpus plus the reference packs, 938,147 records with an `end`:

        a slot at or past its own `end`     9,463    shuffle 3,781, dyngradient 2,400,
                                                     distance 1,779, normal 1,503
        a slot past the RECORD entirely     1,789    shuffle 1,643, the rest 146

    `walk.walk`'s loud `Overrun` fires on none of this and `_bounded` catches none of it
    either: `_bounded` guards `end` and `prog`, and these are the SLOT LISTS, a different
    object. The two guards are not on the same thing.

    Of the four consumers, two bound correctly -- `sbsasm.program_slots` filters
    `s < len(words)`, and safely, because an out-of-record slot sorts LAST and so cannot
    shift the popcount index of a slot before it, and `audit_corpus` filters the same way.
    The other two are the accidents:

      `reverify`'s slotrule COUNTS rather than reads -- `len(_d['cls_slots'])` with no bound
      -- so an inflated list would inflate the count it compares a fitted formula against.
      It is unaffected only because it runs on PARAM_SPEC filters and NONE of the 9,463
      affected records is in PARAM_SPEC. A filter-set disjointness, not a check.

      `distance._locate_slot` bounds by the RECORD but not by `end`, and 93 distance records
      have their first parameter slot outside their own header and inside the record, so the
      read HAPPENS. All 93 read exactly 0.0, and the zero/denormal guard -- written for the
      unrelated walk-vs-bytes contradiction -- refuses every one. A value coincidence, not a
      check. 34 more sit past the record and are refused properly.

    So nothing is currently wrong in the output. What is wrong is that the invariant is
    stated here and enforced nowhere, and the next consumer to read a slot list without
    bounding it against `end` will not be protected by either accident.

    THEY CANNOT BE CORRECTED FROM THIS MODEL, which is worth stating because it is the
    obvious next move and it does not work. The fit gives a header LENGTH, not an
    attribution of that length to particular slots -- `const` is an intercept, not the size
    of the base region. shuffle shows it plainly. Its two negative coefficients (`cls[0]`
    and `w1_present`, both -1.0) are set exactly when the record carries a w1 word, so they
    fold into a per-shape base, and every shuffle header is `base + the positive costs`:

        shape     effective base    header == base + positives
        no-w1           2                   325 of 325
        w1              0                   395 of 395

    A per-shape refit would therefore have no negative coefficients at all -- but the w1
    shape's base would be ZERO, and a header cannot begin at word 0 with `w0` and `w1` free.
    The intercept is absorbing the base region rather than measuring it. So the model
    licenses the total and nothing finer, and correcting slot POSITIONS needs a different
    derivation than a per-bit sum against observed lengths.
    """
    import record_layout
    try:
        hw = record_layout.header_words(
            r.filter_id, r.words[0], r.words[1] if len(r.words) > 1 else None,
            r.asm.header.get('version') if isinstance(r.asm.header, dict) else 0)
    except Exception:
        return fallback
    return fallback if hw is None else hw


def _bounded(r, d):
    """Refuse an `end` that exceeds the record instead of returning it.

    A header cannot be longer than the record containing it, so `end > len(words)` is not a
    gap in the model -- it is the model being WRONG, and every reader that takes a position
    from `end` (blur, sharpen and warp all read `end - 1`) would be reading past the record.
    Those readers already treat a missing `end` as "the walk does not resolve this record"
    and refuse or fall back, so reporting None turns a confidently wrong answer into an
    honest one. `inputs` is kept -- it comes from the record's own shape flags, not from the
    cost arithmetic that overran.

    1,795 of 903,616 records over-run (`tools/walk_health.py` counts them per filter), and
    shuffle holds 1,623 of those with a single cause. Its two shapes are told apart by tag
    bit 0, and the cost model expresses the difference with two NEGATIVE terms:
    `cls[0] = -1.0` and `w1_present = -1.0`. This walk appends one slot per unit of cost, so
    it cannot represent either -- `range(int(round(-1.0)))` yields nothing rather than
    subtracting, and `w1_present` is never applied on this path at all. Both are silently
    dropped and the header comes out exactly 2 too long, on all 1,623.

    THE SPLIT BY SHAPE IS THE PROOF, over all 7,682 shuffle records:

        shape     records    walk end == header_words    walk end > len(words)
        no-w1       3,934          3,934 of 3,934                  0
        w1          3,748              0 of 3,748              1,623

    Perfect agreement on the shape carrying no negative term, none whatsoever on the shape
    carrying two. `record_layout` already lists shuffle among the filters it does not derive
    ("two record shapes, and w1 exists in only one of them"); this is what that undelivered
    fit does when a walk applies it anyway.

    NOT REPAIRED HERE, DELIBERATELY. `header_words` applies the same costs additively and
    never over-runs, so the tempting fix is to take `end` from it. But the two models also
    disagree about the BASE -- this walk adds `n_base` input slots on top of `const`, while
    `header_words` treats `const` as the entire base -- and for shuffle that is a further
    difference of 2, so they do not simply agree once the sign is fixed. Choosing between
    them needs ground truth for shuffle's header and the corpus has none: no permitted
    source declares a distinctive shuffle float, so containment pairs nothing here. Picking
    the model that looks better would be the same mistake as the formulas this walk was
    built to replace. The over-run is refused, and the cause is written down for whoever
    finishes shuffle's cost model.
    """
    n = len(r.words)
    # THE SLOT LISTS ARE BOUNDED TOO, and against the RECORD rather than against `end`.
    #
    # Only `end` and `prog` were checked here, so the lists could name words the record does
    # not contain. Over corpus.paths() plus the reference packs:
    #
    #     inputs        0 records name a word past the record
    #     cls_slots  1,738   (shuffle 1,643, dyngradient 74, normal 21)
    #     param_slots   68   (distance 51, normal 17)
    #
    # `inputs` needs nothing, which is why this cannot move the edge readings the walk is
    # validated on -- 903,611 of 903,611 against `_compute_layout` + `_real_edges`.
    #
    # AGAINST len(words), NOT AGAINST `end`, and the distinction is the whole judgement.
    # A further 7,637 cls_slots and 3,165 param_slots sit at or past `end` and are LEFT
    # ALONE: `end` is a cost-model output, shuffle's is provably two too long (see the split
    # by shape above), and truncating a slot list against a number known to be wrong would
    # bury that overrun instead of leaving it visible. `len(words)` is not a model output --
    # a word past the end of the record does not exist, and naming it is never right under
    # any cost model. That is the same fact this function already applies to `end` itself.
    #
    # WHAT IT WAS COSTING, both benign by accident rather than by design, which is why
    # nothing caught it: `reverify`'s slotrule counts cls_slots unbounded and is saved only
    # because no affected record is in PARAM_SPEC, and `distance._locate_slot` reads 93
    # slots outside their own header, every one of which happens to hold exactly 0.0 and is
    # refused by a zero guard written for something else.
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
    never consults the cost model's 2-bit field decomposition, so it is immune to the PARAM_SPEC/
    cost-model field misalignment that dropped directionalwarp's intensity+warpangle, and it reads
    the level VALUES rather than the baked WIDTHS that precede them.

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
        # levels' values are read FORWARD from a start, with the baked WIDTHS trailing (the cost
        # model's "baked widths not separated" gap). When the tag is ODD the values sit right after
        # the cls-slot region (start = last cls slot + 1; a set cls bit 7 adds a slot and pushes it);
        # when EVEN they sit at/before the size slot (prog, shifted back one when leveloutlow is
        # present, which occupies prog-1). 99.83% vs the memo. The residual 0.17% is per-record: the
        # SAME present set lands at different starts in different records, i.e. the memo's own
        # fitting, not a structural rule -- and render-neutral (all-packs refcompare, 0 worse).
        cls_slots = d['cls_slots']
        if r.cls & 1:
            start = (max(cls_slots) + 1) if cls_slots else prog + 1
        else:
            start = prog - 1 if 'leveloutlow' in present else prog
        slots = range(start, start + len(present))
    else:
        slots = range(end - len(present), end)
    return [r._read_slot(nm, s) for nm, s in zip(present, slots) if 2 <= s < len(r.words)]
