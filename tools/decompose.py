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


def _feature_cost(spec, idx, c0, is_state):
    """One interaction feature's slot count: `base[idx] + colour * cross[idx]`, rounded.

    Shared by `_interaction_walk` and `_fxmaps_walk` because it is one rule. The fxmaps arm
    declines the interaction spec's ROLES -- it calls slot 2 an image input and misses the
    real ones -- but not its COSTS, and a second copy of this arithmetic is the duplication
    `fx_entry_walk`'s note is about.
    """
    base, cross = spec['base'], spec['cross']
    if idx >= len(base):
        return 0
    if spec.get('interaction') == 'colour_states':
        # CROSS HOLDS ONLY THE STATE COLUMNS, so it is indexed by the STATE ORDINAL and not
        # by the full column index. `record_layout._interaction` takes the same slice from
        # the other end -- `vs = v[len(v) - len(cross):]` -- and this took `cross[idx]`,
        # which for the one `colour_states` spec in the file (emboss, len(base) 17 against
        # len(cross) 12) is off by five: it charged one state's colour coefficient to
        # another and dropped the last five entirely. Two implementations of one rule, and
        # the header LENGTH never showed it because `end` comes from `_model_end`, i.e.
        # from `record_layout` -- only the slot POSITIONS this walk hands out were wrong.
        j = idx - (len(base) - len(cross))
        x = cross[j] if (is_state and 0 <= j < len(cross)) else 0.0
    else:
        x = cross[idx] if idx < len(cross) else 0.0
    return int(round(base[idx] + c0 * x))


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
    0: 1, 1: 2, 2: 1, 3: 1, 6: 0, 7: 2, 8: 2, 10: 1, 11: 1, 12: 2,
    13: 1, 14: 1, 15: 1, 16: 0, 17: 0, 18: 1, 19: 2, 21: 1, 22: 1,
    # 16 bitmap / 17 text are source-side: no image inputs. shuffle (3) is two-shape, handled
    # in decompose; vectorshape (5) has no header cost model (source geometry, no edges).
    # 6 uniform is a generator and takes none; it reaches only `_interaction_walk`, which
    # needs the arity to place the base region without asking the fitted constant for it.
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
# A SECOND STRADDLE THE SWEEP COULD NOT SEE: `blend`'s opacity, fields 4 and 5 at shift 9.
# It fails two of the three criteria above, and for one reason -- the low half's OTHER bit
# belongs to something else. Bit 8 is set on 22,459 of 29,961 blend records over 40 files
# whether or not an opacity is present, so field 4 reads 0b01 and 0b11 rather than "only
# ever 0b10", and "outer bit 2j never set" is false by the same bit. Only bit 9 is the
# parameter's.
#
# READ AT SHIFT 9 IT IS THE ORDINARY ALPHABET, and the VALUES say so on both arms rather
# than the state bits saying it about themselves. Over the whole 437-file corpus, every
# blend record whose straddled code is nonzero, against what sits in the word the walk
# charges -- 0 exceptions:
#
#     code 01   963 records   every one a plain float in [0, 1]   none resolves a program
#     code 10   170 records   not one a plain float               every one resolves a program
#
# Unrelabelled the walk calls the first arm "field 4, image input" and the second "field 5,
# baked" -- a pointer read as a denormal, 1.9e-39, which is an opacity of zero and a blend
# that composites nothing. Two shipped sources say the same thing from the other side:
# `ChesterfieldSofa.sbs` pairs 11 of 11 declared `opacitymult` values onto the slot the walk
# charges and `SandyStonePath.sbs` 7 of 7, three of them at this field in each.
#
# SOUND BY THE SAME WIDTH TEST as transformation, which is the condition this table's own
# caveat sets: field 4 state 3 costs 1 word and field 5 state 1 costs 1 word, and the whole
# parameter is 1 word in both arms -- a baked scalar and a pointer. So the relabelling
# recovers the parameter and touches no extent. `directionalwarp` still must not be added,
# for the reason above: its halves are sums across two parameters, not one parameter twice.
#
# {filter: [(low tiling field, high tiling field, real shift, field id to report)]}
STRADDLED = {1: [(4, 5, 9, 4)], 2: [(12, 13, 25, 12)]}


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
    clsbits, pairs = s['clsbits'], s['pairs']
    spec_mode = s.get('mode')

    def cost(idx, is_state):
        return _feature_cost(s, idx, c0, is_state)

    # THE BASE REGION IS STRUCTURAL, NOT FITTED. This asked `cost(0)` -- the model's
    # intercept -- for two different things at once: how many words the masks and edges take
    # (which is what `inputs` is read off) and where the class block starts. They are the
    # same number today, on 321,054 of 321,054 records across the four interaction filters
    # (emboss 4, levels 3, transformation 3, uniform 1) -- but only by arithmetic accident,
    # because the intercept is a fitted LENGTH that also absorbs any class word every record
    # of the population carries. Take a word out of that intercept, as `derive_costs` now
    # does for a constant bit identified in another population, and an intercept-derived
    # base region loses an EDGE. Masks plus arity says what the region is; the fit says what
    # the header costs. Two questions, two answers.
    n_masks = 1 if spec_mode == 'absent' else 2
    pos = n_masks + BASE_INPUTS[r.filter_id] if r.filter_id in BASE_INPUTS else cost(0, False)
    size_pos = pos                           # first slot after the base region = size-expr slot
    inputs = list(range(n_masks, pos))
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
                        'end': _model_end(r, pos), 'prog': prog,
                        'size_slot': _size_slot(cls_params)})


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
    # count lands `prog` inside the edge run, where the word is a small record index and +52 is
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
    # layout[1] for fxmaps is 3 + input count, exact over 41,164 records / 14 distinct input
    # counts -- the same "first slot after the base region" as the main path's size_pos,
    # verified by cleanroom-substance-00. That slot is `prog`, and it is ONLY `prog`; `end`
    # is a different quantity and is taken from the cost model below, as in every other arm.
    prog = _FX_FIRST_INPUT + n_in
    # THE CLASS BLOCK IS WALKABLE HERE TOO, and it used to be left empty -- which pushed
    # every caller that needed the size slot into re-deriving it from `prog`. Filter 4
    # carries `base`/`clsbits` rather than a `cls` dictionary, and this arm declines the
    # interaction spec's ROLES (it calls slot 2 an image input and misses the real ones),
    # not its COSTS. Walked from the first slot after the inputs, bit 16 lands on `prog` in
    # 36,057 of 36,057 corpus records at width 1, so what the callers were synthesising was
    # this walk's own answer; 36,031 of them also carry bit 22 or 23, one further costing
    # class slot that nothing has ever looked at.
    #
    # `end` IS THE FITTED HEADER LENGTH HERE TOO. This arm used to return ONE number in both
    # fields -- `end` == `prog` == the first slot after the inputs -- so fxmaps' `end` carried
    # the role the general walk calls `size_pos` and no other filter's `end` carries, and it
    # sat below the walk's OWN class slots: the class cursor exceeded it by +2 on 36,031
    # corpus records, +1 on 5,129, and 0 on 4.
    #
    # THE REASON RECORDED FOR THAT WAS WRONG, AND THE RECORD'S OWN ROOT POINTER SAYS SO. The
    # claim was that `record_layout.header_words` cannot be the header length because the fit
    # "also charges parameters that live in the PAYLOAD" -- inferred from the direction of the
    # disagreement, never tested against anything outside the fit. fxmaps has an independent
    # boundary to test it with: where `fx_root` lands inside the record, no header word can sit
    # at or past it. Over the 40,754 corpus records whose root does:
    #
    #     header_words <= the root slot   40,744    exactly ON it 12,389, four short 27,956
    #     header_words >  the root slot       10    all ie_curve / ie_particles, the same
    #                                               high-arity records the arity note above
    #                                               names, and no others
    #
    # The four-short population is not header the fit missed either: the four words before the
    # root node are a fixed prologue -- 05c40001 00000000 05c40001 00000004 -- in every record
    # sampled. So the fitted length stops AT the payload rather than reaching into it, which is
    # the opposite of what it was declined for.
    #
    # WHAT SAT BETWEEN THE CLASS CURSOR AND `end` WAS HEADER CONTENT THIS WALK DID NOT PLACE:
    # 120,380 slots over 37,318 records, reading as parameters and not as payload --
    #
    #     valid program pointer   56,366   46.8%        zero          11,613    9.6%
    #     plausible float         51,650   42.9%        other          1,751    1.5%
    #
    # -- which was a gap in the WALK, and the parameter block below closes it. Shortening
    # `end` to sit in front of those slots would have been the one repair that cannot be
    # right: it makes the walk's own cursor overrun the length it reports, and it hides the
    # gap in the field a reader would use to find it. `end` is never past the record (0 of
    # 41,164), and `prog` keeps the first-after-inputs slot the invariant above validates.
    pos = prog
    cls_slots, cls_params = [], []
    for i, b in enumerate(spec.get('clsbits', ())):
        if not (r.words[0] >> b) & 1:
            continue
        n = _feature_cost(spec, 1 + i, r.words[0] & 1, False)
        if n > 0:
            cls_params.append((b, pos, n))
        for _ in range(n):
            cls_slots.append(pos)
            pos += 1
    # THE SIX W1 PAIRS ARE THIS FILTER'S OWN PARAMETERS, and this arm used to return
    # `param_slots: []` while the cost model charged every one of them. `costs.json`'s
    # filter-4 spec is a `colour` interaction carrying `pairs: [0, 1, 2, 3, 4, 13]` -- w1
    # two-bit fields at bits 0-1, 2-3, 4-5, 6-7, 8-9 and 26-27, clear of the arity field at
    # 10-15 -- and walking them from the class cursor with the SAME `_feature_cost` the
    # class block uses lands this cursor on `record_layout.header_words` in 41,164 of 41,164
    # corpus records. The arithmetic closes exactly; nothing is left over.
    #
    # A TOTAL THAT CLOSES DOES NOT PROVE THE ORDER, so every placed slot was checked against
    # what its own state declares it to be -- state 1 a baked value, state 2 a program
    # pointer -- by the record's own bytes:
    #
    #     pair 0 st1   9,699 slots   9,699 baked      pair 3 st1     341     341 baked
    #     pair 1 st1  24,265        24,265 baked      pair 3 st2  28,246  28,246 pointers
    #     pair 2 st1  27,407        27,407 baked      pair 4 st2  27,980  27,980 pointers
    #     pair 2 st2     130           130 pointers
    #
    # 118,068 of 118,068 placed value slots agree with their declared state. A misordered
    # walk cannot do that: a baked float read one slot early is a pointer and fails the test.
    #
    # STATE 3 IS AN IMAGE INPUT HERE TOO, and by the walk's existing header-only rule rather
    # than a new one: `PARAM_SPEC[4]`'s `fx_param0` presence mask IS 3, so
    # `_is_image_input` answers True for field 0 without consulting the slot. All 596 hold a
    # backward record index, which corroborates the rule and is not it. They matter because
    # they are inputs the ARITY COUNT DOES NOT COVER -- this filter's edge list is the
    # contiguous arity run PLUS any state-3 field, and the run alone missed one input on 596
    # records. The docstring's "inputs are contiguous from slot 3" is unharmed: these sit
    # past the class block, and no record has a gap inside its arity run.
    #
    # A zero-width field is recorded as ABSENT rather than as a slot, as in `_interaction_
    # walk`: `pairs` 4 state 1 and 13 state 1 both cost 0, and 13 state 1 occurs on 23
    # records that place nothing.
    off = 1 + len(spec.get('clsbits', ()))
    if spec.get('has_absent'):
        off += 1
    if spec.get('arity_sm') is not None:
        off += 1
    masks = _param_field_masks(r.filter_id)
    param_slots = []
    for k, pj in enumerate(spec.get('pairs', ())):
        st = (w1 >> (2 * pj)) & 3
        if st == 0:
            continue
        n = _feature_cost(spec, off + 3 * k + (st - 1), r.words[0] & 1, True)
        if st in (1, 2):
            if n:
                param_slots.append((pj, st, pos, n))
            pos += n
            continue
        for _ in range(n):
            if _is_image_input(r, pj, pos, masks, r.index):
                inputs.append(pos)
            else:
                param_slots.append((pj, 3, pos, 1))
            pos += 1
    return _bounded(r, {'inputs': inputs, 'cls_slots': cls_slots,
                        'param_slots': param_slots,
                        'cls_params': cls_params, 'end': _model_end(r, pos), 'prog': prog,
                        'size_slot': _size_slot(cls_params), 'root': FX_ROOT_SLOT})


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
        # `cls_params` and `size_slot` stated rather than omitted: a caller reading
        # `d.get('cls_params', ())` cannot tell an empty walk from an absent key, and this
        # record has no size slot to place -- not one this walk failed to find.
        return {'inputs': [], 'cls_slots': [], 'param_slots': [], 'cls_params': [],
                'end': None, 'prog': None, 'size_slot': None}
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
                            'prog': prog, 'size_slot': _size_slot(cls_params)})

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
    # RELABEL HERE TOO. `_restraddle` was called only from `_interaction_walk`, so a
    # `STRADDLED` entry for a filter that takes THIS walk was inert -- and `blend`, the
    # filter the table's new entry is about, has no `interaction` key and takes this one.
    # A straddle is a property of the filter's grid, not of which walk reads it.
    if w1 is not None:
        param_slots = _restraddle(r, w1, param_slots)
    # `w1_shift` is REPORTED rather than left for callers to look up again. A consumer
    # matching a PARAM_SPEC mask to a field has to know which grid the fields are on, and
    # re-deriving it means re-selecting the spec with arguments the caller has to
    # reconstruct -- the failure `INPUT_FIELDS` above documents at length. The walk knows
    # it; the walk says it.
    return _bounded(r, {'inputs': inputs, 'cls_slots': cls_slots,
                        'param_slots': param_slots, 'cls_params': cls_params,
                        'w1_shift': gsh, 'size_slot': _size_slot(cls_params),
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
    the walk's accumulated cursor against the model's length -- as it stood BEFORE the cost
    table was re-attributed, which is the state the rest of this docstring explains and the
    three lines below no longer reproduce:

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

    THREE OF THE FIVE ARE FIXED, AND THE FIX WAS IN THE TABLE, NOT HERE. `costs.json`'s
    entries for `normal`, `dyngradient` and `shuffle` have been re-solved with the intercept
    PINNED to the base region this walk computes structurally -- see `record_layout`'s module
    docstring for the derivation and the arbiters. The re-solve is exact on every record,
    every coefficient a non-negative integer, and `header_words` answers the identical length
    on all 926,957 records; what changes is the ATTRIBUTION, and with it where this walk puts
    the class block. The cursor now ends exactly at the model's length on all 11,648 records
    of the three, where 7,158 used to run past it, and no class parameter is placed at or
    past a header end anywhere in the corpus except in `distance`.

    `normal`'s direction was settled by containment before that, and the re-attribution
    agrees with it -- which is the point. Across eight packages, found by matching the exact
    float32 bit pattern within each file:

        seven records, cls 0x0b19   intensity at slot 5, model end 6
        one record,    cls 0x0319   intensity at slot 4, model end 5

    Intensity is at `end - 1` in 8 of 8, so the model's LENGTH was right and the cursor was
    wrong by exactly the +2 the intercept term predicts. It now lands there by walking
    forwards as well.

    WHAT IS LEFT. `distance` (+1 / +2) has the same defect and one of its own: this walk adds
    its optional mask input structurally AND the fit charges the same word to w1 field 0, so
    the two must be reconciled together. A pinned re-solve for it is exact, but its parameter
    slots feed `distance._locate_slot`, so moving them changes a rendered value on 2,280
    records and wants its own containment run first; it is deliberately not in this change.
    `emboss` is not this at all -- it is the only filter whose cursor runs SHORT, and it is a
    v5 fit applied to v2 records.

    THE SLOT LISTS ARE THE WALK'S OWN ACCUMULATION, and a position in them can still exceed
    `end` -- for `distance`, on 1,645 records. Every consumer bounds slots by the record, and
    two of the four do so only by accident, which is worth keeping in view now that only one
    filter is left to trip over it:

      `reverify`'s slotrule COUNTS rather than reads -- `len(_d['cls_slots'])` with no bound
      -- so an inflated list would inflate the count it compares a fitted formula against.
      It is unaffected only because it runs on PARAM_SPEC filters and no affected record is
      in PARAM_SPEC. A filter-set disjointness, not a check.

      `distance._locate_slot` bounds by the RECORD but not by `end`, and 93 distance records
      have their first parameter slot outside their own header and inside the record, so the
      read HAPPENS. All 93 read exactly 0.0, and the zero/denormal guard -- written for the
      unrelated walk-vs-bytes contradiction -- refuses every one. A value coincidence, not a
      check. 34 more sit past the record and are refused properly.

    The other two bound correctly: `sbsasm.program_slots` filters `s < len(words)`, safely,
    because an out-of-record slot sorts LAST and so cannot shift the popcount index of a slot
    before it, and `audit_corpus` filters the same way.

    AN EARLIER REVISION OF THIS DOCSTRING SAID THIS COULD NOT BE DONE, and the argument is
    worth keeping because it was nearly right. It ran: the fit gives a header LENGTH, not an
    attribution of that length to particular slots; shuffle's own negative coefficients fold
    into a per-shape base, and a per-shape refit would give the w1 shape a base of ZERO,
    which is impossible when `w0` and `w1` occupy the first two words. Every step of that is
    true of a fit whose intercept is FREE. What it missed is that the base is not something
    the fit has to discover: it is `n_hdr` mask words plus `n_base` image inputs, a
    structural fact this walk already computes, and pinning it turns the underdetermined
    half of the model into a solved one. shuffle's "impossible" zero base was the tell --
    an intercept absorbing a base region it was never measuring.
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

    IT NO LONGER FIRES, AND THE RECORD OF WHY IS THE POINT. When this guard was written the
    walk's own accumulated cursor was the `end` it returned, 1,795 of 903,616 records
    over-ran, and shuffle held 1,623 of them with a single cause: its two shapes are told
    apart by tag bit 0, and the cost model expressed the difference with two NEGATIVE terms,
    `cls[0] = -1.0` and `w1_present = -1.0`. This walk appends one slot per unit of cost, so
    it can represent neither -- `range(int(round(-1.0)))` yields nothing rather than
    subtracting, and `w1_present` is never applied on this path at all -- and the header came
    out exactly 2 too long on all 1,623.

    THE SPLIT BY SHAPE WAS THE PROOF, over all 7,682 shuffle records of the time:

        shape     records    walk end == header_words    walk end > len(words)
        no-w1       3,934          3,934 of 3,934                  0
        w1          3,748              0 of 3,748              1,623

    Perfect agreement on the shape carrying no negative term, none whatsoever on the shape
    carrying two.

    BOTH HALVES OF THAT ARE NOW GONE. `_model_end` takes the length from `header_words`
    rather than from the cursor, so an over-long cursor stopped reaching this guard; and
    shuffle's costs have since been re-solved as two variants, one per shape, with the
    intercept pinned to the base region -- no negative term survives, and the walk's cursor
    ends exactly at the model's length on all 7,804 of its records. Over 447 files and
    926,957 records nothing reaches this branch at all.

    KEPT ANYWAY, because what it asserts is a fact about the FORMAT and not about any fit: a
    header cannot be longer than the record containing it. It costs nothing while it is
    right, and it is the shape of the failure a future cost change would produce.
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
    # Re-measured over 447 files after the three filters' costs were re-attributed, by
    # spying on this function's own argument: cls_slots 0, param_slots 51 -- all distance.
    # The truncation is doing nothing for shuffle, dyngradient and normal because there is
    # nothing left to truncate, which is what fixing the attribution rather than the symptom
    # looks like from here.
    #
    # `inputs` needs nothing, which is why this cannot move the edge readings the walk is
    # validated on -- 903,611 of 903,611 against `_compute_layout` + `_real_edges`.
    #
    # AGAINST len(words), NOT AGAINST `end`, and the distinction is the whole judgement.
    # Slots at or past `end` are LEFT ALONE -- 1,696 param_slot positions, every one of them
    # `distance`'s, down from 7,637 cls_slots and 3,165 param_slots before the
    # re-attribution. `end` is a cost-model output and distance's attribution is still known
    # wrong, so truncating a slot list against it would bury the remaining overrun instead of
    # leaving it visible. `len(words)` is not a model output -- a word past the end of the
    # record does not exist, and naming it is never right under any cost model. That is the
    # same fact this function already applies to `end` itself.
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
