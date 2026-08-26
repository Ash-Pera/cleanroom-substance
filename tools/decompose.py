"""One structural walk of a record header, replacing the five layout special cases.

The format is a single struct (record_layout's model):

    [tag][w1?][image inputs, contiguous][one slot per set cls bit][one slot-group per w1 field][tail]

`decompose(record)` walks it once and returns {inputs, cls_slots, param_slots, end}, from which
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


def _is_image_input(r, j, pos, masks, ri):
    """Is a state-3 (0b11) w1 field at cost-model index `j`, slot `pos`, a real image input?

    Two ways it can be: it is an ALIGNED named field (its 2-bit range exactly equals a PARAM_SPEC
    mask -- e.g. blend's opacitymult, an edge even when its reference is record 0), OR the slot
    holds a valid backward record index (a genuine input reference -- e.g. distance's unnamed
    input). An unnamed field holding a baked value (blend's field-4 zeros) or a misaligned param
    overlap (directionalwarp's intensity/warpangle, whose slots hold programs/floats, not small
    indices) is neither, and is not an edge."""
    if (3 << (2 * j)) in masks:
        return True
    return pos < len(r.words) and 0 < r.words[pos] < ri

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
    for v in spec.get('variants', ()):
        g = v.get('guard')
        if g is None or (w0 >> g['shift']) & g['mask'] == g['value']:
            return v
    return None if 'variants' in spec else spec


def _has_w1_word(f, w0, ver):
    """record_layout's w1-presence rule for the two-shape filters, or None if not two-shape."""
    if f == 7:                       # warp: w1 only from version 0x90000
        return ver >= 0x90000
    if f == 3:                       # shuffle: tag bit 0 selects the shape carrying w1
        return bool(w0 & 1)
    return None


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
    for i, b in enumerate(clsbits):
        if (w0 >> b) & 1:
            for _ in range(cost(1 + i, False)):
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
        for _ in range(cost(idx, True)):
            if st == 3 and _is_image_input(r, pj, pos, masks, ri):
                inputs.append(pos)             # state-11 image input
            elif st in (1, 2):
                param_slots.append((pj, st, pos))
            pos += 1
    prog = None if size_pos in inputs else size_pos
    return {'inputs': inputs, 'cls_slots': cls_slots, 'param_slots': param_slots,
            'end': pos, 'prog': prog}


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
        different start. Slot 2 sits before them and holds the FX table pointer, which
        every reader in the fx path already takes as `words[2] + 52`; the interaction walk
        independently places the first structural slot at 2 in 1,305 of 1,305, which is
        that hardcode corroborated from the cost model rather than assumed.
    """
    w1 = r.words[1] if len(r.words) > 1 else 0
    shift, mask = spec['arity_sm']
    n_in = (w1 >> shift) & mask
    inputs = list(range(3, 3 + n_in))
    # layout[1] for fxmaps is 3 + input count (the first slot after the inputs = end), exact over
    # 41,164 records / 14 distinct input counts -- the same "first slot after the base region" as
    # the main path's size_pos, verified by cleanroom-substance-00.
    return {'inputs': inputs, 'cls_slots': [], 'param_slots': [], 'end': 3 + n_in, 'prog': 3 + n_in}


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
        pos = max(pos, int(round(const)))
        cls_slots = []
        for b in sorted(int(k) for k in spec['cls']):
            if (w0 >> b) & 1:
                for _ in range(int(round(spec['cls'][str(b)]))):
                    cls_slots.append(pos); pos += 1
        return {'inputs': inputs, 'cls_slots': cls_slots, 'param_slots': [],
                'end': pos, 'prog': prog}

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
    for b in sorted(int(k) for k in spec['cls']):
        if (w0 >> b) & 1:
            for _ in range(int(round(spec['cls'][str(b)]))):
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
    if w1 is not None:
        for j in sorted(int(k) for k in spec['w1']):
            st = (w1 >> (2 * j)) & 3
            if st == 0:
                continue
            for _ in range(int(round(spec['w1'][str(j)].get(str(st), 0.0)))):
                if st == 3 and _is_image_input(r, j, pos, masks, ri):
                    inputs.append(pos)         # state-11 image input
                elif st in (1, 2):
                    param_slots.append((j, st, pos))
                pos += 1
    # prog = the size-expression slot (what size_or_baked reads) = the first slot after the base
    # region (the first cls slot when there is one). None only when that slot is itself an image
    # input edge (blend's mask-only records). Not bounds-checked here: layout names the slot even
    # when it is past the record's words, and size_or_baked does the bounds check.
    # text (17) is a source filter -- it emits glyphs at a baked size, with no size-expression slot.
    # bitmap (16) carries a size expression only when tag bit 0 is set; otherwise slot 2 is image
    # data (which can coincidentally parse as a program), and layout reports no size.
    prog = None if (f == 17 or (f == 16 and not (r.cls & 1)) or size_pos in inputs) else size_pos
    return {'inputs': inputs, 'cls_slots': cls_slots, 'param_slots': param_slots,
            'end': pos, 'prog': prog}


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
