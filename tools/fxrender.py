#!/usr/bin/env python3
"""Render an fxmaps record, built on sbsasm's own FX naming tables.

Structure and NAMES come from the repository: `Record.fx_node_params()` names the chain's
programs (`numberadded`, `switch`, `randomseed`) and `Record.fx_named_params()` names the
table's (`opacity`, `branchoffset`, `frameoffset`, `patternsize`, `patternrotation`,
`patternsuppl`, `imageindex`), both derived by source containment with controls.

What is added here is only what those tables do not cover: WHEN each program runs, and
what to do with the numbers once you have them.

    addnode   n = numberadded; walk the rest of the chain n times, $number = 0..n-1
    markov2   walk on only if `switch` is true
    table     each entry emits one pattern at the current $number

A node's program is evaluated once per VISIT, not once per record -- that is what lets a
slot the table reads carry a per-iteration value.

Assumptions, none of them from the format: pattern shape is a filled RECTANGLE
(`patterntype` is declared and unlocated); overlaps combine with `max`; patterns tile into
neighbouring cells; the gate passes on true.

WHAT THIS PRODUCES, and where it stops. `Stadsspel__Lines` record 0 renders correctly end
to end: one `0x18B` node over one entry, whose three programs evaluate to a per-iteration
y step, a size of (1.414, 0.036) -- 1.414 being the unit square's diagonal -- and 0.125
turns. Ten bars, 45 degrees, spaced 1/10: the file is named `Lines` and nothing in the
decode used its name. Three numbers that all have to be right at once.

Corpus-wide it does not. Over 1,521 records that emit patterns at all, 96% render FLAT,
and the cause is measurable rather than mysterious:

    patternsize, median   2.82  in records that render flat
                          0.50  in records that render a picture

A pattern 2.8 unit squares wide paints everything one colour. So the coordinate space
`patternsize` is expressed in is the open question, and it is upstream of everything else
here.

TWO NEGATIVE RESULTS, recorded so they are not re-run.

1. IT IS NOT THE SHAPE ASSUMPTION. Swapping the filled rectangle for a falloff profile
   takes "renders a picture" from 4.1% to 97.3% -- and means nothing, because a profile
   with falloff cannot produce a flat image by construction, so the metric is defeated
   rather than passed. Looked at, those renders are one soft blob per tile. A better
   shape does not rescue a size that is too large; it only stops the failure from being
   visible in the flatness number. This is why the flatness metric alone must not be used
   to score a pattern-shape hypothesis.

2. THE FRAME IS NOT 1/sqrt(n). If n patterns tiled a grid, `patternsize / sqrt(n)` would
   concentrate near 1. It does not: the fraction landing in [0.2, 2] moves 55.0% -> 60.4%
   while the spread widens at both ends (p10 0.374 -> 0.060). Whatever sets the scale, it
   is not the pattern count.

3. THE FRAME IS NOT A PER-LEVEL POWER OF TWO ON NODE DEPTH. `walk` treats the node graph
   as a linear chain, so an obvious candidate was a missing per-level halving. Evaluating
   `patternsize` for real over 1,034 pattern-emitting records (it is a PROGRAM in most
   entries and invisible to a static read), the best-scoring divisor is `2^chain length`:
   median 0.480 against the 0.50 that characterises records rendering a picture, and
   79.6% landing in [0.2, 2] against 51.2% raw. It is also WRONG. `Stadsspel__Lines`
   record 0 has chain length 1 and a patternsize of 1.414 -- the unit square's diagonal,
   verified end to end -- so any divisor above 1 destroys the one record known to be
   correct. The variants that preserve it, `2^(chain-1)` and the numerically identical
   `2^(addnode levels)`, reach only median 0.961 at 63.8%: better than raw, nowhere near
   0.50. Note the shape of that failure -- it is negative result 1 again from a different
   direction, a metric improving while the model gets worse, and only the known-good
   record caught it.

4. THE TILE LATTICE DOES NOT STEP BY patternsize. `splat` tiles with dx = px - (cx + tx)
   for integer tx, i.e. spacing 1.0, so a pattern of size 0.15 gets reach 1 and only its
   centre copy lands on the canvas -- one blob. ChesterfieldSofa's metallic map shows the
   engine drawing about a 6x6 lattice from such a record and 1/0.15 = 6.7, which makes
   size-spacing the obvious candidate. It is wrong in both directions at once: Lines record
   0 goes from a lit fraction of 0.510 (ten bars) to 0.936, because its y-size of 0.036
   would place about 28 overlapping rows where the file explicitly steps frameoffset by
   0.1 ten times; and ChesterfieldSofa drops from 4 declared outputs to 1, with metallic's
   correlation against the engine's own map falling from +0.2294 to 0.0000.

   THE TEST IS THE POINT, more than the result. Every earlier entry in this list needed a
   bespoke measurement to refute, and two readings had to be PARKED because nothing
   available could contradict them. This one died in a single run against a two-sided test:

       a ground-truth record that must keep rendering correctly   (Lines record 0)
       a reference correlation that must not get worse            (ChesterfieldSofa)

   Neither half is new, but the second only became usable when the matrix fix took
   ChesterfieldSofa from 659 non-finite records to 0 and from 1 spatially-varying declared
   output to 4. Before that the reference set had no scoreable output and the only
   available metric was flatness, which negative result 1 correctly refuses to trust
   because a falloff cannot be flat by construction. A correlation has no such defect: a
   falloff that is wrong scores no better than a rectangle that is wrong.

   Anything proposed for the frame question should be run against both halves before it is
   argued about.

5. THE RECIPROCAL READING OF A BAKED patternsize IS UNDECIDABLE ON THIS CORPUS -- which is
   a stronger statement than "unproven", and is recorded so nobody re-derives it.

   The reading: a BAKED patternsize is stored as 1/size. It is not idle. The words decode
   as clean float32 clustering on 5.0, 3.0, 1.5, 8.0, 2.0, 1.0 and 4.0; read as canvas
   fractions they paint everything, read as reciprocals they are 1/5, 1/3, 2/3, 1/8, 1/2,
   1 and 1/4. Per record it lands median exactly 0.500 -- the value that characterises a
   record which renders a picture -- with 88.7% in [0.02, 1.5] against 41.8% as-is. It
   also explains the asymmetry no frame model did: 62% of oversized records have a baked
   patternsize against 27% of correctly-sized ones.

   WHY IT IS NOT IMPLEMENTED. Both records with independent ground truth -- Stadsspel__Lines
   record 0 and sci_fi_elements_02 record 86 -- take patternsize from a PROGRAM, so a rule
   touching only baked values cannot break either. The property that makes it safe is the
   property that makes it unfalsifiable, and two hypotheses died here today on exactly that
   ground: a plausibility gain that no available record could contradict.

   WHAT WOULD DECIDE IT, stated as a search rather than left open. A record whose geometry
   is OVERDETERMINED -- more constraints than degrees of freedom -- so the footprint is
   forced rather than chosen, AND whose patternsize is baked. Record 86 is the precedent
   in the other currency: six patterns at radius 0.433, rotations stepping exactly 1/6
   turn, size 0.866 = 2 x radius, so every hard footprint passes through the centre and
   coverage is forced. An evenly-stepped ring is NOT sufficient on its own; a ring whose
   size is unrelated to its radius is still free and decides nothing. Two shapes qualify:

       a ring where size and radius stand in a forced ratio, baked size
       a 0x99 lattice chain with a baked size -- the lattice already forces coverage
       (a parallel session's nine specimens run 2304 = 48 x 48, 450 = 9 x 50, 256 = 16 x 16,
       overdetermined in exactly this sense, but their sizes come from programs)

   Searched: 0 candidates over 60 files, baked patternsize with 3-24 patterns and either
   evenly-stepped rotations or a constant-radius ring. One such record decides the question
   in a single render; nothing else in this corpus will.

WHY THIS MATTERS MORE THAN THE FILTER WORK. Perturbation over 140 files: of 112 declared
outputs that render flat, the flat SOURCE records in their closure were replaced with
varying patterns and the output re-rendered. 89 then varied, 4 stayed flat, and 19 had no
flat source to perturb. So 89 of the 93 testable -- 95.7% -- are flat because their
sources are constant, NOT because the filter chain destroys variation; it transmits fine.
The constant sources are `fxmaps` (367) and `uniform` (300), and nothing else. This is why
three filters landing in one session moved `produced` and left the picture count alone:
they were never the constraint. `patternsize` is.

The positions say the same thing from the other side: the x-extent of
`branchoffset + frameoffset` across one record's patterns has median 0.835 -- about a unit
square, as expected -- but a p90 of 7.8. Some records place patterns far outside the unit
square, which a frame model would explain and this renderer does not have.
"""
import argparse
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assume, sbsruntime, transpile                                  # noqa: E402
from sbsasm import Assembly, FX_NODES, fx_patterntype                                 # noqa: E402

# 0x1CB joins these on the value evidence in sbsasm's FX_NODE_PARAMS: its +4 program is
# 1.0 in 180 of 183, matching 0x18B's `numberadded` (1.0 in 69.5%) and not 0x1AB's
# `randomseed` (0.0 in 6 of 6). It iterates once and passes through.
ADDNODE = frozenset({0x18B, 0x1AB, 0x20B, 0x1CB})
GATE = 0x89

#: One successor, one unnamed program, and the program is a per-iteration STATE UPDATE
#: rather than a count or a predicate. In StylizedCobblestoneStreet record 27 it reads
#: slots 14/16/17/18 and writes 12/14/16/17/18: a counter in 17 wrapping against 16, a
#: direction vector in 18 rotated a quarter turn (`mul.f2` by (-1, 1) on a swizzle) when
#: it wraps, and a position in 14 advanced by that direction. The 0x18B node above it
#: initialises those same five slots.
#:
#: IT IS A RASTER SCAN, not the serpentine this comment first called it. Plotting the
#: emitted offsets in emission order shows each row laid left to right and then a jump
#: back to begin the row above -- a serpentine would reverse along alternate rows and
#: need no return. Over the nine records in 260 files that exercise it with more than one
#: pattern, EVERY emission lands at a distinct offset (2304 of 2304, 450 of 450, 256 of
#: 256) against 15% of records without a 0x99, and in all nine the count divides exactly
#: by the number of distinct rows:
#:
#:     Brick02  r12   81 = 9 x 9      Brick03  r12  108 = 9 x 12
#:     Brick02  r17  315 = 9 x 35     Brick03  r17  225 = 9 x 25
#:     Brick02  r23  432 = 9 x 48     Brick03  r23  450 = 9 x 50
#:     Chipboard r1633  256 = 16 x 16     Flagstone r219  256 = 16 x 16
#:     PavingStones r44   2304 = 48 x 48
#:
#: Nine courses in every brick record. Where the distinct x count EXCEEDS the row length
#: (Brick02 r12 has 10 for 9, r23 has 64 for 48) the extra x values are the running-bond
#: offset -- always more than the row length, never fewer, which is what an alternating
#: course offset does and what a broken stepper could not do.
#:
#: It is the pattern's position, not incidental state: the table entry's `frameoffset`
#: and `opacity` programs both read slot 12, which the stepper writes as *this*
#: iteration's position (`slot 12 = slot 14` before slot 14 advances). So the node runs
#: its program and continues to its single successor -- run first, then emit, which is
#: the order slot 12 is written in.
STEPPER = 0x99

#: The 0x??0B family is where a chain ENDS. Its "programs" are not its own: in record 27
#: the leaf's five programs are byte-identical to the five parameter programs of the
#: table entry it hands off to (opacity, frameoffset, patternsize, patternrotation,
#: patternsuppl at the same five addresses). The leaf IS the entry seen from the node
#: side, so the walk passes straight through it and the table does the emitting.
def _is_leaf(hdr):
    return (hdr & 0xFF) == 0x0B
MAX_PATTERNS = 40000


class Unmodelled(Exception):
    pass


class Perm(dict):
    def __missing__(self, key):
        return 0.5


def make_runner(asm, rec):
    cache = {}

    def run(ptr, slots, number):
        end = asm.program_span(ptr, asm.body_hi)
        if end is None:
            raise Unmodelled("program at %d has no span" % ptr)
        key = (ptr, end)
        if key not in cache:
            src = transpile.transpile(asm.data, ptr, end, "python", "prog")
            scope = {}
            exec(compile(src, "<fx>", "exec"), scope)
            cache[key] = scope["prog"]
        sbsruntime.set_context(width=rec.width, height=rec.height, number=float(number))
        inputs = Perm()
        for _t, uid, val in asm.header.get('inputs') or []:
            if val:
                inputs[uid] = np.array(val, dtype=np.float32).reshape(1, -1)
        with np.errstate(all="ignore"):
            try:
                out = scope_call(cache[key], inputs, slots)
            except sbsruntime.MissingSampler as e:
                # MUST precede the bare KeyError: MissingSampler subclasses it, so without
                # this an unwired image input is reported as a missing SLOT. render.py had
                # exactly this bug, it was fixed there, and this file -- committed one turn
                # later -- reintroduced it. It is why an A/B over the sampling records
                # showed "no sampler 0" in every arm while 18 records failed with a message
                # about slots: the category was real and the label was wrong.
                raise Unmodelled("no sampler for input %s (an unwired edge, NOT a "
                                 "missing slot)" % e) from e
            except KeyError as e:
                raise Unmodelled("slot %s read but never set" % e) from e
        return np.asarray(out).ravel()

    return run


def scope_call(fn, inputs, slots):
    return fn(inputs=inputs, slots=slots)


def chain(rec):
    """[(offset, header, {name: program})] in chain order."""
    nodes, order = {}, []
    for off, hdr, name, prog in rec.fx_node_params():
        if off not in nodes:
            nodes[off] = (hdr, {})
            order.append(off)
        nodes[off][1][name] = prog
    return [(off, nodes[off][0], nodes[off][1]) for off in order]


def entries(rec, baked_pairs=True):
    """[(offset, tag, {name: (kind, value)})] in table order.

    `baked_pairs` additionally reads each UNNAMED baked (odd) bit as the baked form of
    the parameter the next even bit names -- the reading argued for in
    FX-RENDER-HANDOFF.md section 3, and NOT what sbsasm's FX_PARAM_BITS says (it leaves
    those bits None). It is a flag precisely so the two readings can be compared: with it
    off, an entry that bakes its patternsize falls back to a full-cell default and paints
    the whole canvas.
    """
    # THE TABLE IS THE ENTRY LIST, NOT THE PARAMETER LIST. This used to derive `order`
    # from fx_named_params(), so an entry whose tag sets no parameter bits was invisible
    # and the record reported "no readable table entries" -- 9,385 entries across 220
    # files, and 950 records that thereby had no table at all. They are not nothing: the
    # patterntype still rides in the tag's nibble 2, so a paramless entry is a pattern of
    # a stated shape at default transform, which is the full-cell fallback below.
    #
    # That they are real entries and not a walk running into bytecode is the program-span
    # containment control, with both of its controls present in the same measurement:
    #
    #     group           entries   inside a program span
    #     parameterised      5621        1        0.0%     (known good)
    #     paramless8         9385        0        0.0%
    #     other-nibble        808      112       13.9%     (known bad: node headers)
    #
    # Restricted to nibble 8 for exactly that reason -- the nibble-b words in the same
    # walk ARE node headers and score 13.9%, so they stay out. Note the payload-pointer
    # test cannot be used here: a paramless entry has no program, so its +4 word points
    # nowhere by construction (0.3% against 97.9%), which measures the absence of
    # parameters rather than the absence of an entry.
    tbl, order = {}, []
    for off, tag, _p in rec.fx_table():
        if off in tbl or (tag & 0xF) != 8:
            continue
        tbl[off] = (tag, {})
        order.append(off)
    for off, tag, _sl, name, kind, value in rec.fx_named_params():
        if off not in tbl:
            tbl[off] = (tag, {})
            order.append(off)
        if name:
            tbl[off][1][name] = (kind, value)
    if baked_pairs:
        for off in order:
            tag = tbl[off][0]
            for bit, sl, width in baked_slots(tag):
                partner = PARTNER.get(bit)
                if partner is None or partner in tbl[off][1]:
                    continue
                raw = rec.asm.data[off + 4 * sl:off + 4 * sl + 4 * width]
                if len(raw) == 4 * width:
                    tbl[off][1][partner] = ('baked', np.frombuffer(raw, dtype='<f4'))
    return [(off, tbl[off][0], tbl[off][1]) for off in order]


def baked_slots(tag):
    """[(bit, slot, width)] for the tag's BAKED parameter bits.

    Mirrors sbsasm.fx_entry_layout's walk exactly -- same table, same order -- but keeps
    the bit index, which that function does not return.
    """
    from sbsasm import FX_PARAM_BITS, FX_PROGRAM_BITS
    out, sl = [], 1
    for bit, _name, width in FX_PARAM_BITS:
        if not (tag >> bit) & 1:
            continue
        if bit in FX_PROGRAM_BITS:
            sl += 1
        else:
            out.append((bit, sl + 1, width))
            sl += width
    return out


def _partners():
    from sbsasm import FX_PARAM_BITS, FX_PROGRAM_BITS
    names = {b: n for b, n, _w in FX_PARAM_BITS}
    return {b: names.get(b + 1) for b, _n, _w in FX_PARAM_BITS
            if b not in FX_PROGRAM_BITS and (b + 1) in FX_PROGRAM_BITS}


PARTNER = _partners()


def seed_slots(rec, run):
    """Run the record's OWN non-FX programs once, so the table can read what they set.

    The FX table reads slots the chain never writes -- 58.9% of fxmaps records died on
    `slot N read but never set` when only the chain was run. The writers are the record's
    other programs, which is what FORMAT-NOTES' "the slot frame is per-RECORD" (99.892%
    against an 11.8% control) says: the frame's unit is the record, so every program the
    record names shares it, not just the chain's.

    Evaluated once at N=1 into the dict the walk then uses. Takes rendering from 27.9% to
    85.2% of fxmaps records -- the single largest lever in this file.
    """
    slots = {}
    fx = {p for _o, _h, _n, p in rec.fx_node_params()}
    fx |= {v for _o, _t, _s, _n, k, v in rec.fx_named_params() if k != 'baked' and v}
    for p in (rec.programs or ()):
        if p in fx:
            continue
        try:
            run(p, slots, 0)
        except Exception:
            # A record's own program may itself read a slot nothing writes. Seeding is
            # best-effort by design: what it fails to set, the walk reports as missing.
            pass
    return slots


def emissions(rec, run, gate_polarity=True, baked_pairs=True, slots=None):
    slots = {} if slots is None else slots
    nodes = chain(rec)
    table = entries(rec, baked_pairs)
    if not table:
        raise Unmodelled("no readable table entries")
    for _off, hdr, _p in nodes:
        if hdr not in ADDNODE and hdr != GATE and hdr != STEPPER and not _is_leaf(hdr):
            raise Unmodelled("node header %#x is not modelled" % hdr)

    out = []

    # THE RECORD'S OWN PROGRAMS SEED THE FRAME. This session's "slot frame is per-RECORD"
    # finding counts as writers the node chain AND the record's own programs -- 99.892%
    # of entry slot reads resolve against an 11.8% control. Running only the chain left
    # 58.9% of records failing on `slot N read but never set`, because the record's own
    # programs are where the constants live. Evaluated once, N=1, in address order, into
    # the same dict -- exactly what render.py already does for a pixelprocessor's
    # non-final programs.
    fx_progs = {p for _o, _h, ps in nodes for p in ps.values() if p}
    for _o, _t, params in table:
        for _k, (kind, value) in params.items():
            if kind != 'baked' and value:
                fx_progs.add(value)
    for prog in sorted(set(rec.programs) - fx_progs):
        try:
            run(prog, slots, 0)
        except Exception:
            pass          # a record program that cannot run is not fatal to the walk

    def walk(i, number):
        if len(out) > MAX_PATTERNS:
            raise Unmodelled("more than %d patterns" % MAX_PATTERNS)
        if i == len(nodes):
            for _o, _t, params in table:
                # THE TAG TRAVELS WITH THE PATTERN. The shape is selected per entry from
                # `patterntype`, and by the time `splat` runs the tag is gone -- so it is
                # attached here rather than re-derived, which would mean re-walking the
                # table and guessing which entry produced which emission.
                got = {'patterntype': fx_patterntype(_t)}
                for name, (kind, value) in params.items():
                    if value is None:
                        continue
                    if kind != 'baked':
                        got[name] = run(value, slots, number)
                    elif isinstance(value, np.ndarray):
                        got[name] = value          # already decoded by `baked_slots`
                    else:
                        # fx_named_params hands a baked parameter back as its RAW SLOT
                        # WORD, not as a number -- see its docstring.
                        got[name] = np.frombuffer(struct.pack('<I', int(value)),
                                                  dtype='<f4')
                out.append(got)
            return
        _off, hdr, progs = nodes[i]
        if hdr in ADDNODE:
            prog = progs.get('numberadded')
            if prog is None:
                raise Unmodelled("addnode with no numberadded program")
            if 'randomseed' in progs and progs['randomseed'] is not None:
                run(progs['randomseed'], slots, number)
            n = int(round(float(run(prog, slots, number)[0])))
            if not 0 <= n <= MAX_PATTERNS:
                raise Unmodelled("numberadded = %d" % n)
            for k in range(n):
                walk(i + 1, k)
        elif hdr == STEPPER:
            # Run the state update, then continue to the single successor. The return
            # value is discarded: this program is a chain of `seq`-joined `set`s, and
            # what it produces is the slot frame the entry then reads, not a number.
            prog = progs.get(None)
            if prog is not None:
                run(prog, slots, number)
            walk(i + 1, number)
        elif _is_leaf(hdr):
            walk(i + 1, number)             # the leaf is the entry; the table emits
        else:
            prog = progs.get('switch')
            if prog is None:
                raise Unmodelled("markov2 with no switch program")
            if bool(run(prog, slots, number)[0]) == gate_polarity:
                walk(i + 1, number)

    walk(0, 0)
    return out


# patterntype -> shape name, READ OFF THE MANIFEST rather than guessed. Every .xml in the
# corpus is scanned for <guicomboboxitem value= text=>, and the shape-named items form one
# contiguous, self-consistent sequence: 2 Square, 3 Disc, 4 Paraboloid, 5 Bell, 6 Gaussian,
# 7 Thorn, 8 Pyramid, 9 Brick, 10 Gradation, 11 Waves, 12 Half bell, 13 Ridged Bell,
# 14 Crescent, 15 Capsule, 16 Cone. `fx_patterntype` already supplies the value from the
# tag nibble plus FX_PATTERNTYPE_BIAS, so the selector and the enumeration meet.
#
# IT PREDICTS THE TWO RECORDS WE HAVE GROUND TRUTH FOR, which is what makes it more than a
# plausible table. Stadsspel__Lines record 0 is nibble 0 -- the documented catch-all, i.e.
# Square -- and renders correctly as a hard bar today. sci_fi_elements_02 record 86 is
# nibble 8 -> 10 -> Gradation, and its six patterns at radius 0.433 with size 0.866 are
# geometrically FORCED to cover the canvas under any hard footprint (diameter = 2 x radius,
# so each passes through the centre); only a falloff resolves it, which is what a gradation
# is. Both were established before this table existed.
#
# Most value->name pairs appear in only two files. The evidence is not their count -- it is
# that 5..16 are contiguous and consistent, and that the table independently gets both
# ground-truth records right, a test it could have failed.
PATTERN_SHAPES = {
    2: 'square', 3: 'disc', 4: 'paraboloid', 5: 'bell', 6: 'gaussian', 7: 'thorn',
    8: 'pyramid', 9: 'brick', 10: 'gradation', 11: 'waves', 12: 'halfbell',
    13: 'ridgedbell', 14: 'crescent', 15: 'capsule', 16: 'cone',
}

# Which shapes are DETERMINED by their name and which are MODELLED. A name fixes the
# family -- gaussian is radial and falls off, square does not -- but not always the exact
# analytic form, and pretending otherwise would repeat the mistake this file already
# records: a shape that cannot be flat by construction passes a flatness check without
# being right. Callers can subtract the modelled ones from a coverage figure.
SHAPE_MODELLED = frozenset({'bell', 'thorn', 'brick', 'waves', 'halfbell',
                            'ridgedbell', 'crescent', 'capsule'})


def profile_value(lx, ly, profile):
    """Pattern coverage at local coordinates, |lx|,|ly| <= 0.5 inside the footprint.

    The shape is no longer unknown. `patterntype` is declared in the entry tag and the
    manifest names its values (see PATTERN_SHAPES), so the footprint is selected from
    shipped data instead of assumed. What remains a modelling choice is the exact profile
    for the eight names in SHAPE_MODELLED, whose family is fixed by the name but whose
    curve is not.

    WHY A GLOBAL PROFILE COULD NEVER HAVE WORKED, and why the earlier attempt to score one
    was uninformative: 1,218 records are the Square catch-all and need a hard fill, while
    roughly 670 are Paraboloid, Gradation, Gaussian or Bell and need falloff. Any single
    answer breaks one group or the other, so a corpus-wide flatness score was measuring
    the metric rather than the format.

    The two legacy names stay: 'rect' is an alias for square, and 'cone' was already here.
    An unknown name still raises rather than silently reaching a default -- a channel that
    accepts a value it cannot honour is the failure this project keeps being caught by.
    """
    inside = (np.abs(lx) <= 0.5) & (np.abs(ly) <= 0.5)
    if profile in ('rect', 'square'):
        return inside.astype(np.float32)
    r = np.sqrt((2.0 * lx) ** 2 + (2.0 * ly) ** 2)      # 0 at centre, 1 at the box edge
    ins = inside.astype(np.float32)
    if profile == 'disc':
        return ((r <= 1.0) & inside).astype(np.float32)      # hard circle, no falloff
    if profile == 'cone':
        return (np.clip(1.0 - r, 0.0, 1.0) * ins).astype(np.float32)           # linear
    if profile == 'paraboloid':
        return (np.clip(1.0 - r * r, 0.0, 1.0) * ins).astype(np.float32)       # quadratic
    if profile == 'gaussian':
        return (np.exp(-4.0 * r * r) * ins).astype(np.float32)
    if profile == 'pyramid':
        c = np.maximum(np.abs(2.0 * lx), np.abs(2.0 * ly))   # Chebyshev, not Euclidean
        return (np.clip(1.0 - c, 0.0, 1.0) * ins).astype(np.float32)
    if profile == 'gradation':
        return (np.clip(0.5 + lx, 0.0, 1.0) * ins).astype(np.float32)   # ramp along x
    # --- SHAPE_MODELLED below: the family is named, the curve is chosen. ---
    if profile == 'bell':
        t = np.clip(1.0 - r * r, 0.0, 1.0)
        return (t * t * ins).astype(np.float32)              # smoother than paraboloid
    if profile == 'halfbell':
        t = np.clip(1.0 - r * r, 0.0, 1.0)
        return (t * (ly >= 0.0) * ins).astype(np.float32)
    if profile == 'ridgedbell':
        t = np.clip(1.0 - r, 0.0, 1.0)
        return (t * np.abs(np.cos(3.0 * np.pi * r)) * ins).astype(np.float32)
    if profile == 'thorn':
        t = np.clip(1.0 - r, 0.0, 1.0)
        return (t ** 3 * ins).astype(np.float32)             # sharper than cone
    if profile == 'brick':
        c = np.maximum(np.abs(2.0 * lx), np.abs(2.0 * ly))
        return ((c <= 0.85).astype(np.float32) * ins).astype(np.float32)
    if profile == 'waves':
        return (np.clip(0.5 + 0.5 * np.cos(2.0 * np.pi * lx * 2.0), 0.0, 1.0)
                * ins).astype(np.float32)
    if profile == 'crescent':
        outer = np.clip(1.0 - r, 0.0, 1.0)
        inner = np.sqrt((2.0 * (lx - 0.15)) ** 2 + (2.0 * ly) ** 2)
        return (outer * (inner > 0.75) * ins).astype(np.float32)
    if profile == 'capsule':
        d = np.abs(2.0 * ly) / np.maximum(1e-6, 1.0)         # a bar with rounded ends
        cap = np.clip(1.0 - np.maximum(d, np.clip(np.abs(2.0 * lx) - 0.5, 0.0, None)),
                      0.0, 1.0)
        return (cap * ins).astype(np.float32)
    raise ValueError('unknown pattern profile %r' % (profile,))


def splat(rec, patterns, W=None, H=None, profile=None, images=None):
    """Draw the emitted patterns. `images` maps EDGE SLOT -> (H, W, C) array.

    When `images` is supplied and a pattern carries `imageindex`, the pattern IS that image
    sampled over its own footprint rather than a generated profile. For those records the
    shape question does not arise -- there is no footprint to guess.

    HOW OFTEN IT APPLIES, and what it must not be over-read as. Over 80 files, 176 fxmaps
    records carry `imageindex` on their entries:

        every pattern indexes 0     133 records   -- and these have SIX edges
        at least one indexes 1       27 records   -- and these have THREE
        values seen                  0.0 x54,518 and 1.0 x27; no other value exists

    If `imageindex` were a direct index into the edge list, six-edge records would be
    expected to use more than index 0. They do not, so it indexes something narrower -- a
    subset of edges that are pattern images -- and that mapping is NOT established. So
    `image_for` takes the index literally and returns None when the caller did not supply
    it, which draws the generated profile instead. Silently falling back to the first
    available image would sample the wrong input on the 27 and produce a plausible picture
    from it, which is the failure mode this decode keeps being caught by.
    """
    W = W or rec.width
    H = H or rec.height
    # The footprint is the largest open question here and the one the reference renders
    # could settle, so it is arbitrable: `assume.scope(**{'fx.profile': 'bell'})` renders a
    # candidate. Absent a scope this is 'rect', today's behaviour, unchanged.
    # An explicit scope still wins, so a candidate can be forced for an experiment. With
    # none, the shape comes from the entry's own patterntype -- data, not an assumption.
    forced = profile if profile is not None else assume.assumed('fx.profile', None)

    def profile_for(p):
        if forced is not None:
            return forced
        t = p.get('patterntype')
        # nibble 0 is the documented catch-all -- patterntype 1, 2 and a source-declared
        # function graph all land there -- and Square is the member of it that Lines
        # record 0 confirms, so an unresolved type keeps today's hard fill.
        return PATTERN_SHAPES.get(t, 'rect') if t is not None else 'rect'

    def image_for(p):
        if not images:
            return None
        v = p.get('imageindex')
        if v is None:
            return None
        try:
            idx = int(round(float(np.asarray(v, dtype=float).ravel()[0])))
        except Exception:
            return None
        return images.get(idx)
    nchan = 4 if rec.colour else 1
    canvas = np.zeros((H * W, nchan), dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    px = (xx.ravel() + 0.5) / W - 0.5
    py = (yy.ravel() + 0.5) / H - 0.5

    for p in patterns:
        src = image_for(p)
        def val(name, default):
            v = p.get(name)
            return np.asarray(default, dtype=np.float32) if v is None \
                else np.asarray(v, dtype=np.float32).ravel()
        base = val('branchoffset', [0.0, 0.0])
        off = val('frameoffset', [0.0, 0.0])
        size = val('patternsize', [1.0, 1.0])
        rot = float(val('patternrotation', [0.0])[0])
        col = val('opacity', [1.0])
        if size.size < 2:
            size = np.repeat(size[:1], 2)
        if base.size < 2:
            base = np.repeat(base[:1], 2)
        if off.size < 2:
            off = np.repeat(off[:1], 2)
        sx, sy = float(size[0]), float(size[1])
        cx, cy = float(base[0] + off[0]), float(base[1] + off[1])
        if not all(np.isfinite([sx, sy, cx, cy])) or sx <= 0 or sy <= 0:
            continue
        if max(sx, sy) > 64.0:
            continue          # a pattern 64 cells across is a misread, not a pattern
        if col.size < nchan:
            col = np.repeat(col[:1], nchan)
        col = np.clip(col[:nchan], 0.0, 1.0)

        th = 2.0 * np.pi * rot
        ct, st = np.cos(th), np.sin(th)
        reach = int(min(3, np.ceil(max(sx, sy))))
        for ty in range(-reach, reach + 1):
            for tx in range(-reach, reach + 1):
                dx = px - (cx + tx)
                dy = py - (cy + ty)
                lx = (dx * ct + dy * st) / sx
                ly = (-dx * st + dy * ct) / sy
                cov = profile_value(lx, ly, profile_for(p))
                hit = cov > 0
                if not hit.any():
                    continue
                if src is None:
                    canvas[hit] = np.maximum(canvas[hit], col * cov[hit, None])
                    continue
                # The pattern IS the input image: local coordinates, which run
                # -0.5..0.5 across the footprint, map straight onto its UV.
                uv = np.stack([lx[hit] + 0.5, ly[hit] + 0.5], axis=-1)
                sampled = sbsruntime.image_sampler(src)(uv)
                sampled = np.asarray(sampled, dtype=np.float32)
                if sampled.ndim == 1:
                    sampled = sampled[:, None]
                if sampled.shape[-1] < nchan:
                    sampled = np.repeat(sampled[:, :1], nchan, axis=-1)
                canvas[hit] = np.maximum(canvas[hit],
                                         sampled[:, :nchan] * col * cov[hit, None])
    return np.clip(canvas, 0, 1).reshape(H, W, nchan)


def render_record(path, idx, size=256):
    asm = Assembly(path)
    rec = asm.records[idx]
    if rec.filter_id != 4:
        raise Unmodelled("record %d is %s, not fxmaps" % (idx, rec.filter_name))
    pats = emissions(rec, make_runner(asm, rec))
    if not pats:
        raise Unmodelled("emitted no patterns")
    return splat(rec, pats, size, size), pats


def save(img, out):
    from PIL import Image
    a = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    if a.shape[2] == 1:
        Image.fromarray(a[:, :, 0], 'L').save(out)
    else:
        Image.fromarray(a[:, :, :3], 'RGB').save(out)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('record', type=int)
    ap.add_argument('-o', '--out', default='/tmp/fx.png')
    ap.add_argument('-s', '--size', type=int, default=256)
    a = ap.parse_args()
    img, pats = render_record(a.path, a.record, a.size)
    print('%d patterns   min %.3f max %.3f mean %.3f'
          % (len(pats), img.min(), img.max(), img.mean()))
    save(img, a.out)
    print('wrote', a.out)
