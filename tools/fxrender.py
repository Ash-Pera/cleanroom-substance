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

A POSITIVE RESULT, source-confirmed: patternsize is a plain [0,1] canvas fraction, and the
open question is a VARIABLE-RESOLUTION problem, not a coordinate-space scale. Reading the
permitted FX-Map sources settles what `patternsize` is expressed in. These graphs have no
Quadrant node -- their whole node vocabulary is addnode (596), paramset (480), markov2 (80),
so there is no spatial subdivision to scale a size against, and the linear-chain model is
topologically right. And in 220 of 230 patternsize programs the value is simply READ from a
cross-node variable (`get_float2("size_out")`, 96; a gated `get_float1`, 124), set in a setup
node, not computed at the draw site. `ie_pcloud`'s own author comment states the chain:

    cloud_img_size = pow2(tofloat2(cloud_size))     # 2 ** cloud_size, an integer2 input
    size_out       = (1, 1) / cloud_img_size        # the reciprocal
    ... paramset patternsize = get_float2("size_out")

With the default `cloud_size = (7, 7)`, `size_out = 1/128 = 0.0078` -- a point in a point
cloud, correct. `ie_curve` reaches a small size the other way (`p_size` input default 0.01,
read directly). Either way the drawn size is SMALL and lives behind a variable. So the median
2.82 is not a size in a mysterious space; it is what `size_out` reads when its setup chain
(input -> `pow2` -> reciprocal -> the variable slot) has not been resolved to its small value
by the time the paramset reads it. This confirms negative-result 5's reciprocal reading as the
format's real convention -- size is written as `1/pow2(N)` in the source, for PROGRAM sizes
which are the majority, not just as a baked-byte trick -- and it explains the asymmetry (the
oversized records are the ones whose size variable defaulted).

WHAT TO CHECK NEXT (needs a working render, which this author's env cannot run -- numpy is
broken here). For a cloud record, assert the walk holds `size_out ~= 1 / 2**cloud_size`
(~0.008 at the default) in `slots` at the moment a paramset reads it. If it does not, the
setup `set` program that computes it is either not run before the read or writes a different
slot number than the read -- a `seed_slots`/ordering bug -- and that, not a frame scale, is
what paints the corpus flat. The two-sided test from negative-result 4 still applies: Lines
record 0 (baked-free, must stay a picture) and ChesterfieldSofa's reference correlation.
"""
import argparse
import os
import math
import re
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assume, sbsruntime, transpile                                  # noqa: E402
from sbsasm import (Assembly, FX_NODES, fx_patterntype,                              # noqa: E402
                    fx_entry_layout)

# 0x1CB joins these on the value evidence in sbsasm's FX_NODE_PARAMS: its +4 program is
# 1.0 in 180 of 183, matching 0x18B's `numberadded` (1.0 in 69.5%) and not 0x1AB's
# `randomseed` (0.0 in 6 of 6). It iterates once and passes through.
#: Upper bound on scanner iterations -- a runaway predicate must not hang a render.
SCAN_LIMIT = 4096

#: Debug hook: set to a list to capture the first scanner iterations.
_SCAN_TRACE = None

# A CLAIM MADE HERE AND WITHDRAWN. 921c775 said collapsing these four costs Chesterfield's
# `height` and `normal`: records 92 and 93 are subtracted at record 95, their renders agree
# to within 0.0063 so the subtract cancels, and 92's third chain node is `0x1CB` where 93's
# is `0x18B`. The inference was that the walker fails to distinguish two maps the format
# distinguishes.
#
# IT DOES DISTINGUISH THEM. Emitting both and comparing pattern by pattern: 25 patterns
# each, and ALL 25 DIFFER -- the frameoffsets are mirrored, (0.110, -0.059) against
# (-0.110, +0.059). The walk is not collapsing anything.
#
# What washes the difference out is downstream: every pattern has `patternsize` (2.82, 2.82),
# nearly three cells across, so each one covers the canvas several times over and 25 of them
# overlapping give a near-uniform field whichever way the offsets point. Move the stamps and
# the picture barely moves. That is the oversized-patternsize question another session is
# working, not a node-vocabulary gap.
#
# The measurement that misled me is worth keeping: salting `rand` per record moves every
# near-zero Chesterfield channel slightly the right way -- normal ch0 -0.0069 -> +0.0297,
# height -0.0015 -> +0.0207 -- which I read as support for the collapse. It is equally
# consistent with jittering an over-covered field. A change that improves four channels by
# 0.03 does not tell you WHY, and I treated it as though it did.
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

#: 0x9B has the SAME SHAPE as the stepper -- one unnamed program and one successor -- and
#: is walked the same way. sbsasm's FX_NODES2 gives it ((12,), (8,)): program at word 2,
#: successor at word 3, where 0x99 has ((16,), (8,)). It became reachable only once 0x0B's
#: successor slot was wired, and the ten records that end their chain on one are exactly
#: the "no readable table entries" failures in the reference set (ChesterfieldSofa 79,
#: Auras 43/250/332/370 among them).
#:
#: TREATED AS A PASS-THROUGH ON ITS SHAPE, not on a decoded meaning. What the program
#: computes is not established -- 0x99 was shown to be a raster scan by reading its slot
#: traffic, and no equivalent reading has been done here -- so this runs it for its slot
#: side effects and continues, which is what a one-program one-successor node can do
#: without inventing semantics. If it turns out to gate or to iterate, this is where that
#: would go, and the records above are the specimens.
STEPPER2 = 0x9B

#: The 0x??1B family: ONE child at word 2, a program at word 4, and a CONTINUATION at
#: word 5 -- not two children, which is what test_fx's name for it still says.
#:
#: Both readings satisfy that test (the two words differ and both land on node headers),
#: and the file separates them. If word 5 is the continuation, following word 2's subtree
#: along its own next-pointers must ARRIVE at word 5's target; if it is an independent
#: second branch, it must not. Over every 0x??1B node in 150 files:
#:
#:     word 5 target reachable from word 2's subtree     81 of 81
#:     control -- another node in the same record         0 of 81
#:
#: So the subtree already flows into the continuation and a linear walk visits everything
#: a tree walk would. That is why this needs no tree machinery, only a run-and-continue,
#: and it is why the estimate that it required a tree walk was wrong.
#:
#: Two further facts make the flat index walk exactly right, both 81 of 81: the child at
#: word 2 is always the NEXT node in the address-ordered chain, and `progs[None]` -- the
#: only name chain() gives these nodes -- is always word 4's program.
#:
#: The program is not a selector. It is around 104 instructions of `rand` and `cartesian`
#: writing slots 25/27/29/30: a state initialiser, the role STEPPER's program also plays,
#: which is why it shares STEPPER's handling rather than getting its own.
BRANCH = 0x1B

#: A THREE-WORD CELL THE CHAIN SIMPLY CONTINUES PAST. Measured over 34 `0x1B` nodes in 40
#: files, with no counter-example in any of the three:
#:
#:     word 1 is the constant 12345 (0x3039)          34 of 34
#:     word 2 is a pointer BACKWARDS into the body    34 of 34
#:     word 3 is a `0x18B` node header                34 of 34
#:
#: Word 3 being a header in every case is what fixes the width at three, independently of
#: how the walk arrived: the next node is contiguous, not addressed by a pointer.
#:
#: THIS CONTRADICTS `sbsasm.FX_NODES2['0x1b'] = ((8, 20), (16,))`, which places successors
#: at bytes 8 and 20 and a program at byte 16 -- words 2, 5 and 4 of a cell that is only
#: three words long. Words 4 and 5 are the FOLLOWING `0x18B` node's own program and
#: successor (`FX_NODES['0x18b'] = (8, (4,))` reads exactly those two), so that entry was
#: derived by reading the next node's fields as this one's. Not corrected there from here:
#: the table drives the walk for every record, and this is the shape of one node kind
#: measured in one place.
#:
#: 0x3039 is the same sentinel that withdrew an earlier `0x9B` derivation in this file --
#: a constant, present in both files examined, that looked like an entry pointer under a
#: body-wide search.
PASSTHROUGH = 0x1B

#: The 0x??0B family is where a chain ENDS. Its "programs" are not its own: in record 27
#: the leaf's five programs are byte-identical to the five parameter programs of the
#: table entry it hands off to (opacity, frameoffset, patternsize, patternrotation,
#: patternsuppl at the same five addresses). The leaf IS the entry seen from the node
#: side, so the walk passes straight through it and the table does the emitting.
def _is_leaf(hdr):
    return (hdr & 0xFF) == 0x0B
#: The per-record emission budget. A runtime bound, not a format fact -- a record asking for
#: more is refused rather than rendered slowly.
#:
#: RAISING IT IS NOT THE LEVER IT LOOKS LIKE, measured after batched emission made a
#: million patterns arithmetically cheap. Over the same 30 corpus files, at max_dim 64:
#:
#:     cap     40,000     44 of 127 declared outputs rendered       74 s
#:     cap    300,000     44 of 127                               117 s
#:     cap  3,000,000     44 of 127                               878 s
#:
#: ZERO more outputs for twelve times the wall clock. It was two when this note was first
#: written, before `distance` learned to read its parameter from the derived slot (57da8db)
#: -- those two outputs were reachable another way, and the budget was never what held them.
#: Re-measured rather than carried forward, because a stale comparison is how a number turns
#: into folklore. The cost is also concentrated: at 3,000,000 three files take 114 s, 353 s
#: and 364 s on their own. The counts that appear in the blocker
#: table -- 1,050,625 (1025^2), 2,253,001, 921,600, 102,400 (320^2), 66,049 (257^2) -- are
#: legitimate values, squares of a grid dimension, so this budget is refusing correct work.
#: But the records behind them mostly hit another root as soon as they emit, which is why
#: lifting the budget moves the output count by two.
#:
#: Splat is what costs now, not emission: emission runs at about 3 us per pattern batched,
#: and drawing one is 50-80 us. Making a million-pattern record affordable is a splat
#: problem, and until it is solved raising this number buys almost nothing.
MAX_PATTERNS = 40000

_SLOT_WRITE = re.compile(r'slots\[(\d+)\]\s*=')
_SLOT_ANY = re.compile(r'slots\[(\d+)\]')

#: Below this many patterns the scalar path is used unchanged. Batching costs a snapshot
#: of the slot frame and an extra dict per pattern, which is not worth it for a handful,
#: and it keeps the common small record on exactly the code path it has always taken.
BATCH_MIN = 32

# Defaults for the emitted pattern parameters, as arrays built once. `val` used to take
# Python lists and convert them per pattern.
_ZERO1 = np.zeros(1, dtype=np.float32)
_ZERO2 = np.zeros(2, dtype=np.float32)
_ONE1 = np.ones(1, dtype=np.float32)
_ONE2 = np.ones(2, dtype=np.float32)


class Unmodelled(Exception):
    pass


class Perm(dict):
    def __missing__(self, key):
        return 0.5


def make_runner(asm, rec):
    cache = {}

    # BUILT ONCE PER RECORD, NOT ONCE PER EMISSION. The graph's declared input values do
    # not change while a record renders -- they are read straight off `asm.header` -- but
    # this dict used to be rebuilt inside `run`, which an FX-Map calls several times for
    # every pattern it emits. CarpetSubstance001 record 365 emits 262,144 patterns, so
    # the 22 `np.array(...).reshape(1, -1)` calls below were being made about six million
    # times to produce six million copies of the same 22 numbers.
    #
    # Safe to share: `Perm` is only ever READ by transpiled code (`inputs[uid]`), and its
    # `__missing__` returns a default without storing it, so no program can mutate what
    # the next one sees.
    shared_inputs = Perm()
    for _t, uid, val in asm.header.get('inputs') or []:
        if val:
            shared_inputs[uid] = np.array(val, dtype=np.float32).reshape(1, -1)

    # `program_span` is memoized inside the assembly, but reaching that memo is still a
    # method call and a tuple hash per emission. Keyed by ptr alone here because
    # `asm.body_hi` is fixed for the life of the assembly.
    spans = {}

    flows = {}

    def flow(ptr):
        """(slots read before this program writes them, slots it writes).

        The batched emission below needs to know whether a slot a program writes is
        SCRATCH -- written before it is ever read, so the value it arrived with cannot
        matter -- or STATE carried from the previous pattern. The distinction is visible
        in the transpiled source, which assigns and reads slots by literal index, so it is
        read off there rather than guessed from the values.

        Reported for the program alone. A slot that is scratch here can still be state for
        the record if ANOTHER program reads it without writing it first, which is why the
        caller unions `read_first` across every program that can run.
        """
        got = flows.get(ptr)
        if got is not None:
            return got
        end = spans.get(ptr, 0) or asm.program_span(ptr, asm.body_hi)
        reads, writes = set(), set()
        if end is not None:
            try:
                src = transpile.transpile(asm.data, ptr, end, "python", "prog")
            except Exception:
                src = ''
            for line in src.splitlines():
                line = line.strip()
                lhs = _SLOT_WRITE.match(line)
                for m in _SLOT_ANY.finditer(line if lhs is None else line[lhs.end():]):
                    k = int(m.group(1))
                    if k not in writes:
                        reads.add(k)
                if lhs is not None:
                    writes.add(int(lhs.group(1)))
        got = flows[ptr] = (reads, writes)
        return got

    run_flow = flow

    def run(ptr, slots, number, flatten=True):
        end = spans.get(ptr, 0)
        if end == 0:
            end = spans[ptr] = asm.program_span(ptr, asm.body_hi)
        if end is None:
            raise Unmodelled("program at %d has no span" % ptr)
        fn = cache.get(ptr)
        if fn is None:
            src = transpile.transpile(asm.data, ptr, end, "python", "prog")
            scope = {}
            exec(compile(src, "<fx>", "exec"), scope)
            fn = cache[ptr] = scope["prog"]
        sbsruntime.set_context(width=rec.width, height=rec.height,
                               number=number if isinstance(number, np.ndarray)
                               else float(number))
        inputs = shared_inputs
        with np.errstate(all="ignore"):
            try:
                out = scope_call(fn, inputs, slots)
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
        out = np.asarray(out)
        # `flatten` is off for a BATCHED evaluation, where the rows are patterns and
        # flattening them together would interleave every pattern's components into one
        # unusable strip. Every other caller wants the old 1-D value.
        return out.ravel() if flatten else out

    run.flow = run_flow
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


_SLOT_SET = re.compile(r'slots\[(\d+)\]\s*=')
_SLOT_GET = re.compile(r'slots\[(\d+)\](?!\s*=)')


def _slot_flow(asm, ptr):
    """(slots written, slots read before being written) for the program at `ptr`."""
    end = asm.program_span(ptr, asm.body_hi)
    if end is None:
        return None
    try:
        src = transpile.transpile(asm.data, ptr, end, "python", "prog")
    except Exception:
        return None
    sets, reads = set(), set()
    for line in src.splitlines():
        line = line.strip()
        m = _SLOT_SET.match(line)
        for g in _SLOT_GET.finditer(line if m is None else line[m.end():]):
            k = int(g.group(1))
            if k not in sets:
                reads.add(k)
        if m:
            sets.add(int(m.group(1)))
    return sets, reads


def _recover_last_inline(rec, tbl, order):
    """An entry's LAST program slot may hold the program itself, not a pointer to it.

    A NARROWED FORM OF A READING THAT WAS WITHDRAWN, and the withdrawal was right about
    what it measured. `sbsasm.fx_named_params` used to re-read a failed program pointer as
    an inline program, and 9ff1354 removed it: of the 2,717 programs that recovered, the
    1,910 whose entry HAS A SUCCESSOR sit past the next entry's tag in 1,910 of 1,910.
    They are bytecode from a later structure. Deciding pointer-vs-inline from whether
    `word - 52` lands on decodable bytes is a value-driven read, and it invented an
    `imageindex` that duplicated an earlier pointer 2,056 times.

    That measurement leaves 807 unexamined -- the ones with no successor. Over 25 corpus
    files plus every reference package, the split is total:

        recovered program lies INSIDE its own entry   14    all 14 are the LAST entry
        lies beyond the next entry's tag               4    all 4 have a successor

    But "it is the last entry" is a weak test, because for a last entry the bound is just
    the record's end. So the gate here is not containment, it is whether the recovery
    ANSWERS A QUESTION THE RECORD ASKS: does the program write a slot that another
    parameter of the same entry reads before writing, and that no other program in the
    record writes? Of the 14, exactly 7 do, and they are the ones that matter --

        Auras records 45, 49, 252, 256, 334 (slots 13 and 15), Chesterfield 43 (slot 0)

    -- three of the four declared outputs of Auras hang on slot 15 having a writer. The
    other 7 explain nothing and are left as misses.

    A program that decodes is not evidence; a program that resolves a dangling dependency
    in the record that names it is.
    """
    asm = rec.asm
    for idx, off in enumerate(order):
        missing = [n for n, (k, v) in tbl[off][1].items() if k == 'program' and not v]
        if not missing:
            continue
        layout = fx_entry_layout(tbl[off][0])
        slot_of = {n: sl for sl, n, how in layout if how == 'program'}
        prog_slots = [sl for sl, _n, how in layout if how == 'program']
        if not prog_slots:
            continue
        last = max(prog_slots)
        # What the entry's OTHER programs read without writing, and what the record writes
        # anywhere else -- the two halves of "otherwise unwritten".
        need = set()
        for name, (kind, value) in tbl[off][1].items():
            if kind != 'program' or not value:
                continue
            f = _slot_flow(asm, value)
            if f:
                need |= f[1]
        if not need:
            continue
        at = off + 4 * last
        f = _slot_flow(asm, at)
        if not f:
            continue
        elsewhere = set()
        for p in (rec.programs or ()):
            if p == at:
                continue
            g = _slot_flow(asm, p)
            if g:
                elsewhere |= g[0]
        if not ((f[0] & need) - elsewhere):
            continue
        for name in missing:
            if slot_of.get(name) == last:
                tbl[off][1][name] = ('program', at)


def _chain_embedded_entries(rec):
    """Entries reached through the chain-family cells, for records whose table is empty.

    A `0x09` (or `0x49`) cell is five words -- `[kind][ptr][ptr][0x00020008][ptr]` -- and
    the run of them is a linked list, which 1498ae6 established and rightly stopped drawing:
    over 80 files, 6,846 `0x00020008` entries, the second word pointing at the next entry in
    99.5% and no patterntype in 100%. A list node is structure, not a draw.

    WHAT THE LIST POINTS AT WAS LEFT OPEN, and it is the record's actual entry. The cell's
    THIRD word is a shared pointer -- constant across all cells of a record in 7 of 9 --
    and following it at the format's +52 skew lands on a `0x4B` cell, whose own word 3 is a
    table-entry tag. That is the shape the node census predicted for `0x4b` from the bytes
    ("carries an embedded table-entry tag") and listed as uncovered.

    Measured over 25 corpus files plus every reference package:

        chain cells whose B + 52 is a 0x4B cell        42 of 64
          and whose word 3 is an entry tag             36 of 42, all `0x15140088`
        records where the follow finds an entry         6
          and whose entries() is currently EMPTY        6 of 6

    Every record the follow helps is one that had nothing, which is what makes this safe to
    add rather than a competing reading: it cannot displace an entry that already exists.
    `0x15140088` gives opacity, frameoffset, patternsize and patternrotation at slots 3-6,
    the same four `0x15140848` gives at 2-5, and in flowingLava record 911 three of the four
    resolve to programs inside the record.

    Read from the words directly, because `fx_named_params` is driven by the walk and the
    walk is exactly what does not reach here.

    THE OTHER SHAPE UNDER THIS HEADING DOES NOT YIELD, and the obvious move on it has been
    tried. Most records still reporting `no readable table entries` have a table that is
    ENTIRELY `0x00020008` cells with no `0x09` among them -- concrete_049 records 2, 57 and
    58, Desert_Sand_01, MossSubstance001. Those cells chain by word 1 at the +52 skew, each
    landing on the next 8 bytes on, and the LAST one points somewhere else: concrete_049
    record 2's final cell reaches 0x25C holding `0x00100048`, records 57 and 58 reach
    `0x03520248`. Both end in nibble 8 and neither is chain-family, so they look exactly
    like the real entry the chain was leading to.

    They are not. `entry_layout_holds` rejects all three, and it is right to: `0x00100048`
    names a program at slot 2 and that word is `0x0A020001`, which resolves to no program;
    `0x03520248` names three and they are `0x09000007`, `0x40000000`, `0x00000532` --
    bytecode and a float 2.0. A tag whose every predicted program is bytecode is not a tag.

    So the walk stops correctly and this route is closed: whatever those records draw is not
    reached by following their chain to its end.
    """
    data, lo, hi = rec.asm.data, rec.asm.body_lo, rec.asm.body_hi
    out = []
    seen = set()
    try:
        cells = [off for kind, off, hdr, _p in rec.fx_walk()
                 if hdr is not None and (hdr & 0xFF) in (0x09, 0x49)]
    except Exception:
        return out
    for off in cells:
        try:
            shared = struct.unpack_from('<I', data, off + 8)[0] + 52
        except Exception:
            continue
        if not (lo <= shared < hi - 16):
            continue
        try:
            hdr2 = struct.unpack_from('<I', data, shared)[0]
        except Exception:
            continue
        at = shared + 12 if (hdr2 & 0xFFF) in (0x04B, 0x14B) else shared
        if at in seen or not (lo <= at < hi - 4):
            continue
        try:
            tag = struct.unpack_from('<I', data, at)[0]
        except Exception:
            continue
        if (tag & 0xF) != 8 or (tag >> 16) == 0x0002 or not tag:
            continue
        seen.add(at)
        params = {}
        for sl, name, how in fx_entry_layout(tag):
            if not name or at + 4 * sl + 4 > hi:
                continue
            w = struct.unpack_from('<I', data, at + 4 * sl)[0]
            if how == 'baked':
                params[name] = ('baked', w)
            elif how == 'inline':
                a = at + 4 * sl
                params[name] = ('program', a if rec.asm.program_span(a, hi) else None)
            else:
                pv = w + 52
                params[name] = ('program',
                                pv if lo < pv < hi and rec.asm.program_span(pv, hi) else None)
        out.append((at, tag, params))
    return out


def in_eval_order(params):
    """An entry's parameters, in the order the engine evaluates them.

    PROGRAM ADDRESS ORDER, NOT TABLE ORDER, and the two disagree. Entry parameters talk to
    each other through the slot frame -- one writes a slot another reads -- so where they
    do, only one order is defined. Counting every such pair:

        corpus, 25 files      437 dependent pairs   address 437/437   table 437/437
        reference packages    192 dependent pairs   address 192/192   table 182/192

    629 of 629 for address order against 619 of 629 for table order, and the ten
    disagreements all fall the same way. Auras record 49 is the clearest: `opacity` sits
    first in the table and reads slot 15, while `patternrotation` sits second and WRITES
    it -- at the lower address. In table order the read comes first and the record dies on
    `slot 15 read but never set`, which blocks three of the four declared outputs of the
    smallest reference specimen in the corpus.

    Baked parameters are constants and cannot participate, so they go first and their
    relative order does not matter.
    """
    return sorted(params.items(),
                  key=lambda kv: (kv[1][0] != 'baked',
                                  kv[1][1] if isinstance(kv[1][1], int) else 0))


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
    # ...WITH ONE EXCEPTION, AND THE JUSTIFICATION ABOVE IS WHAT EXCLUDES IT. A paramless
    # nibble-8 entry is kept because "the patterntype still rides in the tag's nibble 2".
    # For the CHAIN FAMILY -- high 16 bits 0x0002 -- that sentence is empty: nibble 2 is
    # zero and `fx_patterntype` returns None for every one of them, so there is no stated
    # shape to fall back to. They are structural, not draws:
    #
    #     group                          entries   word[1]+52 == next entry
    #     chain-family, no patterntype      6918          98.5%
    #     other, no patterntype             5439          15.9%
    #
    # 98.5% of them point at the entry that follows, which is a linked list and not a
    # table of independent patterns. Emitting one full-cell fill each is what paints a
    # record white: `WoodSubstance005` record 85 has six entries, five of them this tag.
    #
    # THE OTHER DISCRIMINATOR OFFERED FOR THIS WAS "skip entries whose patterntype is
    # None", and it is NOT equivalent -- the second row above is why. It would also drop
    # 5,439 entries that are not chain-family and mostly do not chain, among them 3,332 of
    # tag 0x00420008, which `FX_ENTRY_PROGS` gives a program slot. Those are real draws
    # and dropping them would trade a white record for a missing one.
    tbl, order, chain_family = {}, [], []
    for off, tag, _p in rec.fx_table():
        if (tag >> 16) == 0x0002:
            # Structural, not a draw -- but its next-pointer is followed below, because the
            # last link of the run leaves it for a real entry.
            chain_family.append(off)
            continue
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
    # THE CHAIN-FAMILY RUN ENDS BY POINTING AT A DRAW ENTRY, and the linear walk does not
    # follow it. `fx_table` steps eight bytes at a time; the chain family is a linked list
    # (97.5% of its entries point at the one that follows) and its LAST link leaves the run
    # entirely. Where it lands is a real draw the table otherwise never reaches.
    #
    # Containment says so rather than plausibility. `SubstanceDesigner__Clouds_3_Animated`
    # is permitted, declares exactly two `paramset` nodes carrying patterntype 8,
    # patternsize "3 2" and randomseeds 42 and 16, and its own binary's record 50 walks four
    # chain-family entries and stops. The fourth one's next-pointer lands on tag
    # 0x13520658 -- patterntype nibble 6, so type 8 -- whose parameter block holds 42 and
    # (3.0, 2.0); the second entry, tag 0x13100658, holds 16 and (3.0, 2.0). Two of two, on
    # three declared values each, and the randomseeds tell the two apart.
    #
    # 20 records across 30 corpus files reach a draw entry this way that the walk misses.
    for _o in chain_family:
        if _o + 8 > len(rec.asm.data):
            continue
        _nxt = struct.unpack_from('<I', rec.asm.data, _o + 4)[0] + 52
        if not (rec.asm.body_lo <= _nxt < rec.asm.body_hi - 7) or _nxt in tbl:
            continue
        _t2 = struct.unpack_from('<I', rec.asm.data, _nxt)[0]
        if (_t2 & 0xF) != 8 or (_t2 >> 16) == 0x0002:
            continue
        for _at, _tag, _p in rec.fx_table(_nxt):
            if _at in tbl or (_tag & 0xF) != 8 or (_tag >> 16) == 0x0002:
                continue
            tbl[_at] = (_tag, {})
            order.append(_at)

    if not order:
        for at, tag, params in _chain_embedded_entries(rec):
            tbl[at] = (tag, params)
            order.append(at)
    _recover_last_inline(rec, tbl, order)
    if baked_pairs:
        for off in order:
            tag = tbl[off][0]
            for bit, sl, width in baked_slots(tag):
                partner = PARTNER.get(bit)
                if partner is None or partner in tbl[off][1]:
                    continue
                # THE SLOT IS INLINE ONLY WHEN THE ENTRY SAYS SO. An entry's +4 word
                # addresses its parameters; usually that is off+8 and the slots follow the
                # tag, which is what this read assumes. Where it points somewhere else the
                # parameters are in a separate block and reading inline returns whatever
                # happens to sit there -- for Clouds_3_Animated record 50 that is (0.0, 0.0)
                # against a source-declared patternsize of (3, 2).
                #
                # The block IS locatable -- both of that file's entries hold their declared
                # randomseed and patternsize at word1+52 -- but two specimens do not
                # establish the slot arithmetic inside it: patternsize lands at block+4
                # slots for one entry and block+3 for the other, and no single base explains
                # both. So this DECLINES rather than guessing, and the parameter reads as
                # absent instead of as zero. See FORMAT-NOTES on the parameter block.
                if not (off + 4 <= len(rec.asm.data) - 4):
                    continue
                _w1 = struct.unpack_from('<I', rec.asm.data, off + 4)[0] + 52
                # NARROWED TO THE CONFIGURATION THE SPECIMEN SHOWS. `fx_table` calls this
                # word the entry's PAYLOAD, and for most entries it plausibly addresses a
                # program while the baked slots stay inline -- declining all 399 non-inline
                # reads over 12 files on the strength of two entries would be over-broad,
                # and it changed no measured output either way. What both Clouds entries
                # have is a word1 pointing BACKWARD, before the tag, where an inline slot
                # cannot be. 15 entries in 30 files are in that configuration.
                if _w1 < off + 8:
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


#: The raster-scan state slots, and what an FX-Map that initialises them EXPLICITLY
#: writes. Some records carry a program that assigns these constants before anything reads
#: them (0x18B, the addnode above the 0x99 scanner, is where they come from); others read
#: the same slots with no such program anywhere in the record and used to die on "slot N
#: read but never set".
#:
#: The constants are read off the records that DO initialise, over 20 files, counting only
#: assignments built entirely from literals:
#:
#:     slot 12   (0.0, 0.0) x710, 0.0 x96          zero, unanimously
#:     slot 14   (0.0, 0.0) x710                   zero, unanimously
#:     slot 16   0 x710, (0.0, 0.0) x92            zero, unanimously
#:     slot 17   0 x711                            zero, unanimously
#:     slot 18   (1.0, 0.0) x710, (0.0, 0.0) x92, 0 x1     NOT unanimous -- excluded
#:     slot 13   2.82 x92, 0.0 x4, (0.0, 0.0) x1           NOT unanimous -- excluded
#:
#: Only the four that agree are seeded. 18 and 13 are the reason this is a measured table
#: and not `default everything to zero`: 18's own initialisers say (1.0, 0.0) seven times
#: out of eight, so a blanket zero would have been confidently wrong on the slot that
#: holds the scan DIRECTION.
#:
#: `setdefault`, and only after `seed_slots` has run the record's own programs, so a real
#: initialiser always wins. A record that renders today cannot change: the only reads this
#: reaches are ones that previously raised.
SCAN_STATE_DEFAULTS = {12: 0.0, 14: 0.0, 16: 0.0, 17: 0.0}


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
    # ONLY WHERE THE CHAIN HAS A SCANNER, and the unconditional version was a mistake I
    # caught by reading what it produced. These slots are the 0x99 raster scan's own state
    # -- position in 14, counters in 16 and 17 -- and a record whose chain contains no
    # scanner has no such state to start. CarpetSubstance001 records 70 and 163 are the
    # specimens: their chain is a lone 0x18B, their entry reads `patternsize` straight out
    # of slot 17, and seeding it to zero made 32 patterns of size ZERO. Nothing draws, the
    # record renders solid black, and it used to REFUSE with `slot 17 read but never set`.
    # Trading a refusal for a blank image is the one trade this renderer is not allowed to
    # make: the error named the gap, and the blank hid it inside 30 flat FX-Maps.
    #
    # The evidence the defaults rest on says the same thing on a re-read. Every explicit
    # initialiser measured -- 710 writing (0, 0) to slot 14, 711 writing 0 to slot 17 --
    # belongs to a record that ALSO carries a scanner to advance them. Zero is where the
    # scan STARTS, not what the slot means in a record that never scans.
    if any(h == STEPPER or (h & 0xFF) == STEPPER2 for _o, h, _p in chain(rec)):
        for slot, value in SCAN_STATE_DEFAULTS.items():
            slots.setdefault(slot, value)
    return slots


#: `$number` is system variable 10, and `floor($number / N)` is a grid's row index with N
#: its width. Read by following the SSA names -- which temporary holds $number, which holds
#: a constant, and which divides the one by the other -- rather than by matching a fixed
#: instruction offset, so a record whose program is ordered differently still resolves.
_ASSIGN = re.compile(r'^\s*(v\d+)\s*=\s*(.+?)\s*$')
_SYSVAR10 = re.compile(r'^sysvar\(10[,)]')
_CONST = re.compile(r'^([0-9]+\.[0-9]+)$')
_DIV = re.compile(r'^\(?\s*(v\d+)\s*/\s*(v\d+)\s*\)?$')


def grid_width(rec):
    """N from the `floor($number / N)` a placement program uses for its row index, or None.

    THE EMISSION COUNT FOR A $number-GRID RECORD, which `numberadded` does not carry. For
    these records numberadded is an amount -- Chesterfield's reads only the aspect slot and
    degenerates to 1 on a square canvas -- while the layout is a grid the placement program
    hardwires. The structural side located the divisor at the first constant after the
    `$number` read in all four Chesterfield specimens, and a byte diff of two of those
    programs shows the whole grid block identical while only the size constants differ.

    Read semantically rather than at instruction 10, because the offset is verified on four
    records that share a program almost byte-for-byte and could shift elsewhere.
    """
    asm = rec.asm
    for ptr in sorted(set(rec.programs or ())):
        end = asm.program_span(ptr)
        if not end:
            continue
        try:
            src = transpile.transpile(asm.data, ptr, end, "python", "p")
        except Exception:
            continue
        if 'slots[26]' not in src:
            continue
        number_vars, consts = set(), {}
        for line in src.splitlines():
            m = _ASSIGN.match(line)
            if not m:
                continue
            name, rhs = m.group(1), m.group(2)
            if _SYSVAR10.match(rhs):
                number_vars.add(name)
                continue
            c = _CONST.match(rhs)
            if c:
                consts[name] = float(c.group(1))
                continue
            d = _DIV.match(rhs)
            if d and d.group(1) in number_vars and d.group(2) in consts:
                n = consts[d.group(2)]
                # THE UPPER BOUND SITS IN A GAP THE CORPUS LEAVES, which is what makes it a
                # guard rather than a taste. Over 80 files the divisors found are
                # 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 16, 18, 20, 24, 25, 30, 31, 32,
                # 35, 39, 42, 50, 64 -- 355 records, dense to 64 -- and then nothing at all
                # until 128, 130 and 16384, which is 6 records. A factor of two of empty
                # space separates the two populations.
                #
                # The large ones are not grids. 16384 is 128 squared, and a divisor of that
                # size is $number used at PIXEL granularity -- a coordinate normalised by
                # the canvas -- not a stamp index; emitting N^2 there would ask for 268
                # million patterns. So the bound is not a cap on how big a grid may be, it
                # is the line between two different uses of $number, and the corpus draws it
                # rather than this code choosing it.
                if n == int(n) and 1 < n <= 64:
                    return int(n)
    return None


def emissions(rec, run, gate_polarity=True, baked_pairs=True, slots=None):
    slots = {} if slots is None else slots
    nodes = chain(rec)
    table = entries(rec, baked_pairs)
    if not table:
        raise Unmodelled("no readable table entries")
    for _off, hdr, _p in nodes:
        if hdr not in ADDNODE and hdr != GATE and hdr != STEPPER \
                and (hdr & 0xFF) != STEPPER2 and (hdr & 0xFF) != PASSTHROUGH \
                and (hdr & 0xFF) != BRANCH and not _is_leaf(hdr):
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

    # IS THE SLOT FRAME SCRATCH OR STATE, for the programs an emission runs? A parameter
    # program that writes a slot is not by itself a reason to refuse batching: the
    # commonest case is a per-pattern random seed, written at the top of the program and
    # read back two lines later, whose incoming value cannot affect anything. What would
    # break batching is a slot carried BETWEEN patterns -- written by one emission and
    # read by the next before it writes it.
    #
    # AND THE ORDER MATTERS, which the first version of this check missed. On
    # CarpetSubstance001 record 365 the parameters talk to each other through the frame
    # WITHIN one emission: `opacity` writes slots 26, 28, 29 and 31, and `frameoffset`,
    # `patternsize`, `patternrotation` and `imageindex` each read one of them. Comparing
    # bare unions calls that carried state and refuses to batch -- but the write happens
    # first, in the same emission, so the value never crosses a pattern boundary. Batching
    # preserves it exactly: slot 26 holds an (m, k) array whose row j is what pattern j
    # would have seen, and the reader is row-aligned with it.
    #
    # So the walk is simulated instead: parameters in evaluation order, accumulating what
    # has been written, and a read counts as CARRIED only if the slot is one a parameter
    # writes and nothing has written it yet this emission. Chain node programs are added
    # too, since those do run between patterns when the chain is not all leaves.
    flow = getattr(run, 'flow', None)
    batchable = False
    if flow is not None:
        try:
            param_writes = set()
            for _o, _t, params in table:
                for _n, (kind, value) in in_eval_order(params):
                    if kind != 'baked' and value:
                        param_writes |= flow(value)[1]
            carried, written = set(), set()
            for _o, _t, params in table:
                for _n, (kind, value) in in_eval_order(params):
                    if kind == 'baked' or not value:
                        continue
                    r, w = flow(value)
                    carried |= (r & param_writes) - written
                    written |= w
            for _o, _h, ps in nodes:
                for value in ps.values():
                    if value:
                        carried |= flow(value)[0] & param_writes
            batchable = not carried
        except Exception:
            batchable = False

    closed = [False]          # did a gate evaluate against its polarity and stop a branch?

    def emit(number):
        for _o, _t, params in table:
            # THE TAG TRAVELS WITH THE PATTERN. The shape is selected per entry from
            # `patterntype`, and by the time `splat` runs the tag is gone -- so it is
            # attached here rather than re-derived, which would mean re-walking the
            # table and guessing which entry produced which emission.
            got = {'patterntype': fx_patterntype(_t)}
            for name, (kind, value) in in_eval_order(params):
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

    def emit_batch(numbers):
        """`emit` for a whole range of pattern indices, in one evaluation per parameter.

        WHY THIS IS THE WHOLE COST. An FX-Map parameter program is a few dozen numpy
        operations on ONE row, and numpy charges per call, not per element: profiling
        CarpetSubstance001 record 365 counted 1,341 Python calls per emitted pattern, and
        that record emits 262,144 of them. The work is negligible and the per-call
        overhead is everything, which is exactly the case batching fixes -- the same
        program over m rows costs almost what it costs over one.

        WHEN IT IS ALLOWED, and the two guards that decide. Batching evaluates every
        pattern against ONE slot frame, so it is only equivalent where the frame does not
        move between patterns:

          * every node below the addnode must be a leaf -- a 0x99 raster scan or a 0x89
            gate would advance or branch per pattern, and the caller checks this before
            calling;
          * no parameter program may WRITE a slot. That is not statically known here, so
            pattern 0 is emitted scalar first and the frame is compared by identity; if
            anything moved, the caller falls back and nothing has been batched yet.

        A program that ignores $number returns a single row, which is broadcast rather
        than indexed -- the same value the scalar path would have produced m times.
        """
        m = len(numbers)
        cols = []
        for _o, _t, params in table:
            per = {'patterntype': fx_patterntype(_t)}
            wide = {}
            for name, (kind, value) in in_eval_order(params):
                if value is None:
                    continue
                if kind != 'baked':
                    a = np.asarray(run(value, slots, numbers, flatten=False))
                    # NORMALISE TO (rows, components) AND SAY WHETHER THE ROWS ARE
                    # PATTERNS. A program that ignores $number returns one row however
                    # wide it is, and the module's 1-D convention (see `_col`: a 1-D array
                    # is N samples of one component) only holds when the length IS the
                    # batch -- a 1-D result of any other length is one value's components,
                    # which is what the scalar path's `.ravel()` hands back.
                    if a.ndim == 0:
                        a = a.reshape(1, 1)
                    elif a.ndim == 1:
                        a = a[:, None] if a.shape[0] == m else a[None, :]
                    wide[name] = a
                elif isinstance(value, np.ndarray):
                    per[name] = value
                else:
                    per[name] = np.frombuffer(struct.pack('<I', int(value)), dtype='<f4')
            cols.append((per, wide))
        for j in range(m):
            for per, wide in cols:
                got = dict(per)
                for name, a in wide.items():
                    got[name] = a[j] if a.shape[0] == m else a[0]
                out.append(got)

    #: [cell count or 0/None, scanner-already-run] for the $number-grid path above.
    _grid = [None, False]

    def walk(i, number):
        if len(out) > MAX_PATTERNS:
            raise Unmodelled("more than %d patterns" % MAX_PATTERNS)
        if i == len(nodes):
            emit(number)
            return
        _off, hdr, progs = nodes[i]
        if hdr in ADDNODE:
            prog = progs.get('numberadded')
            if prog is None:
                raise Unmodelled("addnode with no numberadded program")
            # See assume.QUESTIONS['fx.gridcount']. Where the placement program lays a
            # $number grid, the loop bound is that grid's cell count and NOT numberadded,
            # which for these records is an amount. The scanner is also held to a single run
            # across the whole batch: frameoffset sums the grid position and the scanner's,
            # so re-driving the scan per emission carries every cell off-canvas.
            if _grid[0] is None and assume.assumed('fx.gridcount') == 'divisor':
                _w = grid_width(rec)
                _grid[0] = _w * _w if _w else 0
            if _grid[0]:
                run(prog, slots, number)          # keep the initializer's slot writes
                for k in range(_grid[0]):
                    walk(i + 1, k)
                return
            if 'randomseed' in progs and progs['randomseed'] is not None:
                run(progs['randomseed'], slots, number)
            n = int(round(float(run(prog, slots, number)[0])))
            if not 0 <= n <= MAX_PATTERNS:
                raise Unmodelled("numberadded = %d" % n)
            # Everything below is a leaf, so no node between here and the table can move
            # the slot frame, and the patterns differ only in $number -- which is what
            # makes one evaluation over every index equivalent to n evaluations. See
            # `emit_batch` for the second condition and how it is decided.
            if n > BATCH_MIN and batchable and all(_is_leaf(nodes[j][1])
                                                   for j in range(i + 1, len(nodes))):
                emit_batch(np.arange(n, dtype=np.float64))
                return
            for k in range(n):
                walk(i + 1, k)
        elif hdr == STEPPER and _grid[0]:
            prog = progs.get(None)
            if prog is not None and not _grid[1]:
                run(prog, slots, number)
                _grid[1] = True
            walk(i + 1, number)
            return
        elif hdr == STEPPER and assume.assumed('fx.scanner') == 'loop':
            # See assume.QUESTIONS['fx.scanner']. The body advances a position and returns
            # its own in-bounds predicate, so it is run, then the subtree emits, then the
            # predicate decides whether to go round again -- run-then-emit, matching the
            # single-shot order exactly so the first stamp is unchanged and the loop only
            # adds the ones that were missing.
            prog = progs.get(None)
            if prog is None:
                walk(i + 1, number)
                return
            for _it in range(SCAN_LIMIT):
                v = run(prog, slots, number)
                if _SCAN_TRACE is not None and len(_SCAN_TRACE) < 8:
                    _g = lambda k: np.round(np.asarray(slots.get(k, [np.nan]),
                                                       dtype=float).ravel(), 4).tolist()
                    _SCAN_TRACE.append((_it, _g(18), _g(14), _g(0), _g(10), _g(16), _g(17),
                                        float(np.asarray(v, dtype=np.float64).ravel()[-1])))
                walk(i + 1, number)
                try:
                    ok = bool(np.asarray(v, dtype=np.float64).ravel()[-1])
                except Exception:
                    break
                if not ok:
                    break
            return
        elif hdr == STEPPER or (hdr & 0xFF) in (STEPPER2, BRANCH):
            # Run the state update, then continue to the single successor. The return
            # value is discarded: this program is a chain of `seq`-joined `set`s, and
            # what it produces is the slot frame the entry then reads, not a number.
            prog = progs.get(None)
            if prog is not None:
                run(prog, slots, number)
            walk(i + 1, number)
        elif (hdr & 0xFF) == PASSTHROUGH:
            # Continue to the successor and run NOTHING. The cell is three words -- see
            # PASSTHROUGH -- and the pointer it holds is real but its role is not
            # established, so evaluating it would be writing this record's slot frame from
            # a word whose meaning is a guess. Walking past it is the conservative half of
            # the reading: the chain's shape is measured, the pointer's use is not.
            walk(i + 1, number)
        elif _is_leaf(hdr):
            walk(i + 1, number)             # the leaf is the entry; the table emits
        else:
            prog = progs.get('switch')
            if prog is None:
                raise Unmodelled("markov2 with no switch program")
            if bool(run(prog, slots, number)[0]) == gate_polarity:
                walk(i + 1, number)
            else:
                closed[0] = True

    walk(0, 0)
    # AN EMPTY EMISSION IS A RESULT WHEN A GATE SAID SO. Four FabricSubstance005 records
    # blocked on "emitted no patterns", and each is a single 0x89 gate whose program is
    # three instructions -- `inputref(uid) == 0` -- on the manifest's `scale`, an
    # Integer1 whose declared default is 4. The gate is false because the FILE says the
    # branch is off, not because the walk failed, and refusing there reports a modelling
    # gap that does not exist.
    #
    # The polarity is not a free parameter, which is what makes this safe to act on.
    # Running the same records with gate_polarity inverted takes the four from 0 to 1
    # pattern -- but it also takes the records that currently WORK to zero: 82 goes
    # 45 -> 0, 161 goes 45 -> 0, and 91/138/140 go 2 -> 0. So True is right and the
    # gated records really do emit nothing.
    #
    # Narrow on purpose. Only a gate closing earns an empty result; an empty walk for any
    # other reason still raises. A `numberadded` of 0 would look identical here and is NOT
    # covered, because that value has been seen misread -- Chainmail record 0 reads it as
    # 257^2 -- and blanking a map on a misread count is exactly the plausible-wrong-image
    # this renderer refuses to produce.
    if not out and not closed[0]:
        raise Unmodelled("emitted no patterns and no gate closed")
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


# Smallest patternsize component that is a size rather than a misread. Named so the
# equivalence can be A/B tested in one process -- setting it to 0 restores the old
# behaviour exactly. See the guard in `splat` for the measurement behind the value.
MIN_PATTERN_SIZE = 1e-6


_RAND_CALL = re.compile(r'\brand\(')


def branchoffset_is_rand(rec):
    """Does this record's branchoffset program call `rand`?

    A STATIC EXCLUSION FOR THE CELL-SCALE GUARD, and it settles by decode what the span
    test could only guess at. Cross-classifying every fxmaps record's branchoffset program
    against `grid_width` over the distinct-file corpus, the structural side finds every
    rand-scatter branchoffset is NON-grid -- 5,218 of them, and zero grids -- so a scatter
    can be recognised before any span is computed. It matters because the span test
    misfires on exactly these -- or so an earlier census here reported, finding 63
    rand-scatters inside "the integer-span group". That census used a hand-written span
    classifier rather than `_cell_divisor` itself, and the two do not select the same set:
    `_cell_divisor` additionally requires every pattern to carry a branchoffset and the span
    to be an exact integer at least 1 on some axis. Measured against the SHIPPED guard, the
    misfire does not exist -- over 50 files it fires on 219 records, of which none calls
    rand and none is a grid.

    So this function is a census instrument, not a filter. It is kept because the result it
    produced is worth being able to reproduce: the exclusions it would apply are already
    implied by the span test, and a proxy for a guard is not the guard.
    """
    asm = rec.asm
    try:
        params = list(rec.fx_named_params())
    except Exception:
        return False
    for _off, _tag, _slot, name, kind, val in params:
        if name != 'branchoffset' or kind != 'program' or not val:
            continue
        end = asm.program_span(val)
        if not end:
            continue
        try:
            src = transpile.transpile(asm.data, val, end, "python", "p")
        except Exception:
            continue
        if _RAND_CALL.search(src):
            return True
    return False


def _cell_divisor(patterns):
    """Per-axis 1 / (number of cells), read from the branchoffset span, or None.

    A cell-unit offset walks WHOLE CELLS, so its span across the emissions is an integer
    number of them and a span of k means k + 1 cells. That is a property of the emissions
    alone -- no G, no square test, no assumption that the count factors -- which is what
    makes it usable where round(sqrt(N)) was not. See assume.QUESTIONS['fx.branchoffset']
    for the 407-of-407 census behind it.

    Factored out because the OFFSETS and the SIZES need the same number. They are the same
    grid: if the offsets step one cell at a time, a pattern meant to fill a cell is one
    cell across, so whatever divides the one divides the other. Deriving it twice invited
    them to disagree, and an earlier pair of scalings that did disagree ended up
    multiplying.
    """
    if not patterns:
        return None
    b = [np.asarray(q.get('branchoffset'), dtype=np.float64).ravel()
         for q in patterns if q.get('branchoffset') is not None]
    if len(b) != len(patterns) or not b:
        return None
    w = max(x.size for x in b)
    a = np.array([np.pad(x, (0, w - x.size)) for x in b])
    # AN INTEGER SPAN IS NOT ENOUGH -- THE OFFSETS THEMSELVES MUST BE INTEGERS.
    # cleanroom-substance-0b classified each record's branchoffset program and found the
    # span test scaling 63 records whose program calls `rand`: a scatter has no cells, so
    # dividing it by a cell count is the same category of error round(sqrt(N)) made. Their
    # 20 program-identified grids all landed in the group this DECLINES, which was right,
    # but the group it fired on had no identified grid in it at all.
    #
    # A jittered scatter can still span an integer, because the extremes are the generator's
    # bounds; what it cannot do is put every emission on a lattice point. Requiring all
    # offsets to be integers, and the distinct count on an axis to be exactly span + 1,
    # separates them completely -- over 80 files, of the integer-span records:
    #
    #                       records   all offsets integer   distinct == span+1
    #     program has rand       65                     0                    0
    #     program has none      284                   284                  284
    #
    # 284 of 284 against 0 of 65, decided by the emissions alone. That also closes the 263
    # 0b could not classify: a per-entry transpile cannot see a $number decomposition that
    # happens one node up, but a full integer lattice is visible at emission time whatever
    # node built it.
    d = []
    for k in range(min(2, a.shape[1])):
        col = a[:, k]
        sp = float(col.max() - col.min())
        ok = (sp >= 1 and abs(sp - round(sp)) < 1e-4
              and bool(np.all(np.abs(col - np.round(col)) < 1e-4))
              and len({round(float(t), 6) for t in col}) == round(sp) + 1)
        d.append(1.0 / (round(sp) + 1.0) if ok else 1.0)
    if not any(x != 1.0 for x in d):
        return None
    while len(d) < 2:
        d.append(1.0)
    return np.asarray(d, dtype=np.float32)


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
    # WHAT IS WRONG WITH THIS FUNCTION IS COVERAGE, NOT VALUE, and that is measured rather
    # than inferred. Chesterfield's metallic and height cones each bottom out at an fxmaps
    # sampling an image input, and comparing each one's output against its own input:
    #
    #     record   input lit / mean-where-lit     output lit / mean-where-lit
    #     rec34         0.403 / 0.1438                 0.025 / 0.1427
    #     rec65         0.787 / 0.4991                 0.138 / 0.4901
    #
    # The mean WHERE LIT survives to three decimals. Every pixel a pattern writes gets very
    # nearly the right value, so the sampling, the opacity and the profile amplitude are all
    # doing their job. What collapses is how many pixels get written at all -- 16x on rec34,
    # 5.7x on rec65 -- and the whole-image attenuation is exactly that coverage ratio
    # (0.0036/0.0580 = 0.062 against 0.025/0.403 = 0.062). The stamps do not tile.
    #
    # That is the same defect as the missing lattice documented at render.py's `warp` note,
    # now quantified against a reference rather than against a picture, and it is the
    # measured form of the footprint question this file's docstring calls its largest open
    # one.
    #
    # NO CURRENT ARBITRATION ARM REACHES IT. fx.patternsize and fx.branchoffset leave both
    # records BYTE-IDENTICAL under 'cell' and 'canvas' -- `_cell_divisor` declines them --
    # which is why Chesterfield's metallic MAE is 0.0465 to four decimals under all four
    # combinations. The insensitivity is the guard declining, not the divisor being
    # irrelevant, and any future candidate for this gap has to reach a population these do
    # not.
    #
    # AND THE DEFICIT IS THE EMISSION COUNT, NOT THE SIZE OR THE INDEX. Capturing what these
    # two records actually emit:
    #
    #     rec34   ONE emission   patternsize 0.2500   frameoffset (-0.375, -0.375)  imageindex 8
    #     rec65   ONE emission   patternsize 0.4146   frameoffset (-0.377, -0.376)  imageindex 8
    #
    # `imageindex` 8 is correct: of the fourteen image slots supplied, slot 8 is the only one
    # carrying content (std 0.1489 and 0.3280), and the emission selects exactly it. So the
    # not-established index-to-edge mapping this docstring warns about is not the fault here,
    # and neither is a dilution across the thirteen blank inputs -- there is one stamp, and
    # it samples the right image.
    #
    # The coverage then follows arithmetically. A stamp of side 0.25 covers 0.0625 of the
    # canvas, and the image it stamps is itself lit over 0.403 of its area, so the output is
    # lit over 0.403 x 0.0625 = 0.0252 -- against 0.025 measured. rec65: 0.787 x 0.1719 =
    # 0.135 against 0.138. Both to the third decimal.
    #
    # ONE STAMP OF SIDE 1/4 IS ONE SIXTEENTH OF A CANVAS, and sixteen is the attenuation.
    # A quadrant subdivision two levels deep produces sixteen cells of exactly this size.
    #
    # BUT THE WALK IS NOT SKIPPING A SUBDIVISION -- it emits one because the file says one.
    # Both records are the same chain, ADDNODE(0x18B) -> STEPPER(0x099) -> LEAF(0x100B) with
    # a single entry and no branchoffset field at all, and evaluating their `numberadded`
    # program under the render's own seeded slots returns exactly 1.0 for each. The addnode
    # branch then loops once, faithfully. So the emission count is a correct reading of the
    # program, and the deficit is not a missed descent.
    #
    # What the two records share is the count; what differs is the size, 0.2500 against
    # 0.4146, and the coverage deficit is exactly 1/size^2 in both -- 16.0 and 5.8. So a
    # single stamp is asked to cover the canvas and does not, which leaves two readings: the
    # size should be 1.0, or the STEPPER should be scanning it across the canvas in more
    # than one step. Nothing measurable here separates them.
    #
    # THE REFERENCE SETTLES THE SHAPE, AND IT REFUTES BOTH READINGS ABOVE. Chesterfield's
    # exported metallic is a regular grid of dots, spacing measured at exactly 256px on a
    # 2048px map -- 8 across on both axes, 41 whole blobs plus clipped edges. So:
    #
    #   * NOT a bigger stamp. rec29, the image being stamped, is a tileable unit cell with
    #     soft blobs at its four CORNERS. One stamp of side 1.0 puts those corners at the
    #     canvas corners -- a 2x2 arrangement, not 8x8. Scaling the stamp cannot produce the
    #     reference whatever value slot 29 takes.
    #   * NOT this record's numberadded either. 8x8 is 64, and the structural side reads
    #     this program as ((n-1) mod 2 + n)^2, which yields only ODD squares -- 1, 9, 25, 49.
    #     64 is unreachable from it for any slot value.
    #
    # What the picture shows is one cell stamped once into one corner where the engine
    # repeats it across the canvas at 1/8 spacing. Note the tile loop below reaches
    # `min(3, ceil(max(sx, sy)))` and steps by WHOLE CANVASES, so for a pattern of side 0.25
    # every copy but t=0 lands entirely off-canvas: the loop can wrap a pattern, but it
    # cannot repeat one at its own pitch. Whether the repetition belongs there, in the
    # stepper's per-emission position, or upstream of the record is not settled here, and
    # the two candidates that were on the table are now excluded rather than untested.
    #
    # ONE CONCRETE THREAD LEFT, and it is checkable rather than speculative. `seed_slots`
    # supplies slots 0, 4, 8, 9, 10, 12, 14, 16 and 17. The structural side reports this
    # 0x099 chain reading slots 14, 16, 17 AND 18, and writing the size into slot 29 which
    # `patternsize`'s get(29) then reads. Slot 18 is read and never seeded. Whether that
    # matters depends on what should set it, which is a question about the chain rather than
    # about splat.
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
        if t is None:
            # See assume.QUESTIONS['fx.typeless_profile']. Default unchanged.
            return assume.assumed('fx.typeless_profile', 'rect')
        return PATTERN_SHAPES.get(t, 'rect')

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
    # Kept as 2-D grids so an emission can be evaluated over its FOOTPRINT instead of
    # over the whole canvas -- see the bounding box below. `cview` is a view, so writes
    # through a slice of it land in `canvas`.
    pxg = (xx + 0.5) / W - 0.5
    pyg = (yy + 0.5) / H - 0.5
    cview = canvas.reshape(H, W, nchan)

    # `val` reads one emitted parameter as a flat float32 array. Defined once, outside
    # the loop, and taking the pattern as an argument: a closure over `p` was being
    # rebuilt for every pattern, which is a code object and a cell per emission for no
    # gain.
    def val(pat, name, default):
        v = pat.get(name)
        return np.asarray(default, dtype=np.float32) if v is None \
            else np.asarray(v, dtype=np.float32).ravel()

    # BRANCHOFFSET MAY BE IN CELL UNITS -- see assume.QUESTIONS['fx.branchoffset']. Over
    # 966 square-grid records its span / (G - 1) has median exactly 1.0000, so it spans
    # G - 1 cells rather than the canvas, and Chainmail record 0 renders as a single cell
    # under the canvas reading and as a full 257 x 257 lattice under this one.
    #
    # Opt-in, and guarded twice. Nothing happens unless a caller opened a scope, and even
    # then only when the emission count is a perfect square, because G is undefined
    # otherwise -- 30% of those 966 fall outside 10% of the cell ratio and that tail is not
    # characterised. A span statistic cannot settle it; a scored render can.
    #
    # REPRODUCED INDEPENDENTLY before adoption: 224 square-grid records from a separate
    # walk give span/(G-1) median 1.0000 with p25 AND p75 both 1.0000, 76.8% within 10%.
    # The law is not one session's artifact.
    #
    # OPT-IN FOR A MEASURED REASON, not merely from caution. An earlier version applied
    # this scaling unconditionally to every square-count record, and that is wrong:
    # `PavingStonesSubstance003` records 38/40/42/45 have G=4 and span 0.750, so
    # span/(G-1) = 0.250 -- CANVAS is right for them and 'cell' makes them worse. The
    # unconditional form also scored worse on the only ground truth available, Chesterfield
    # `normal` MAE 0.1039 -> 0.1055 and height 0.2461 -> 0.2480, on a specimen where only
    # 2 of 16 rendering fxmaps records are even affected.
    #
    # Those two scalings briefly coexisted and MULTIPLIED, dividing a square-grid record by
    # G twice. Only this one remains.
    # PATTERNSIZE MAY BE IN CELLS TOO -- see assume.QUESTIONS['fx.patternsize']. Same guard
    # and same reason as the offsets below; kept a separate key because the two are coupled
    # and scoring them apart is what demonstrates it.
    # THE SAME SPAN GUARD THE OFFSETS USE, for the same reason and off the same number.
    # This used to divide by round(sqrt(N)) on a perfect-square emission count, which is not
    # merely over-broad but INVERTED: over Bricks, 88 of 88 records it scaled were rand
    # scatters or had no $number decomposition at all, and not one was a grid, while the
    # file's five real grids emit 32 and 8 patterns and were excluded. Every arm scored
    # through that guard was therefore measuring a population the divisor was not for.
    #
    # `_cell_divisor` replaces it with the span reading, which selects on a property of the
    # emissions instead of on the count factoring. It is per axis, so a non-square grid gets
    # a different divisor on each -- the case sqrt(N) could not express at all.
    # AN 'oversize' CANDIDATE USED TO SIT HERE and has been retired, because the span guard
    # subsumes it exactly. It scaled only records whose median patternsize exceeded 1.0, to
    # stop the old sqrt(N) guard destroying records already emitting coherent sub-canvas
    # sizes -- 625 patterns at 0.052 becoming 0.002. That was a threshold on a SYMPTOM,
    # guarding against a selector that was picking the wrong records. With the span reading
    # doing the selecting, the coherent records are declined structurally and the extra
    # condition never fires: 'cell' and 'oversize' render byte-identically on all 175 Bricks
    # fxmaps records, 0 differing. A candidate that cannot differ from another is not an
    # arbitration option, so it is gone rather than left to look like one.
    # THE STATIC EXCLUSIONS WERE TRIED HERE AND ARE NOT NEEDED -- see `branchoffset_is_rand`,
    # which is kept for the census that showed it. Excluding rand-scatters and $number-grids
    # before measuring the span removes ZERO records from what `_cell_divisor` actually
    # fires on: over 50 files it scales 219 records, of which none calls rand and none is a
    # grid. The guard is already clean, and adding a transpile per record to exclude nothing
    # is cost without effect.
    size_scale = None
    if assume.assumed('fx.patternsize') == 'cell' and patterns:
        size_scale = _cell_divisor(patterns)
        if size_scale is not None:
            assume.note(getattr(rec, 'index', -1))

    # THE GUARD IS THE SPAN, NOT THE COUNT. This used to divide by round(sqrt(N)) when the
    # emission count was a perfect square, which is not merely over-broad -- it selects
    # AGAINST its own target. cleanroom-substance-0b classified every Bricks fxmaps record
    # by what its branchoffset program consumes and crossed that with what the arm touched:
    # 88 of 88 records it scaled were rand scatters or had no $number decomposition at all,
    # and NOT ONE was a grid. That file's five real grids read an integer2 input (4, 8) and
    # emit 32 and 8 patterns -- neither a perfect square -- so the sqrt test excluded
    # exactly the population a cell divisor exists for.
    #
    # A cell-unit offset walks WHOLE CELLS, so its span is an integer number of them. That
    # is a property of the emissions alone: no G, no square test, no assumption that the
    # count factors. Over 110 files:
    #
    #     records with a branchoffset span            3,390
    #       span is an exact integer                    407
    #         and (span + 1) divides the count          407   <- 407 of 407
    #         sqrt(N) would have MISSED it               41
    #       span is fractional (canvas-like)          2,983   <- the old guard scaled these
    #
    # 407 of 407 self-consistent, against a guard right about 27% of what it touched. The
    # divisor is per axis: a span of k cells means k + 1 of them.
    cell_scale = None
    if assume.assumed('fx.branchoffset') == 'cell' and patterns:
        cell_scale = _cell_divisor(patterns)
        if cell_scale is not None:
            assume.note(getattr(rec, 'index', -1))

    # AN ENTRY THAT STATES NEITHER SHAPE NOR EXTENT: see assume.QUESTIONS['fx.sizeless'].
    # The default stays 'fill' -- a full-cell rect, today's behaviour -- because that is
    # what the code has always done, not because it is established.
    _sizeless = assume.assumed('fx.sizeless', 'fill')

    # THE ROOT ENTRY -- see assume.QUESTIONS['fx.rootentry']. A typeless, sizeless pattern at
    # branchoffset exactly (0, 0) is the whole-canvas cell of the FX-Map's own tree, not a
    # draw. Tested by its own key rather than by `fx.sizeless`, which the references decide
    # the other way: this is one pattern per record with an exact signature, that one is
    # every sizeless pattern anywhere.
    _rootskip = assume.assumed('fx.rootentry') == 'skip'

    for p in patterns:
        if (_rootskip and p.get('patternsize') is None and p.get('patterntype') is None
                and p.get('branchoffset') is not None):
            _b = np.asarray(p['branchoffset'], dtype=np.float64).ravel()
            if _b.size >= 2 and not np.any(np.abs(_b[:2]) > 1e-6):
                assume.note(getattr(rec, 'index', -1))
                continue
        if p.get('patternsize') is None and p.get('patterntype') is None:
            if _sizeless == 'skip':
                continue
            if _sizeless in ('half', 'quarter'):
                p = dict(p)
                p['patternsize'] = np.full(2, 0.5 if _sizeless == 'half' else 0.25,
                                           dtype=np.float32)
        src = image_for(p)
        base = val(p, 'branchoffset', _ZERO2)
        if cell_scale is not None:
            base = base * cell_scale[:base.size]
        off = val(p, 'frameoffset', _ZERO2)
        size = val(p, 'patternsize', _ONE2)
        if size_scale is not None:
            size = size * size_scale[:size.size]
        rot = float(val(p, 'patternrotation', _ZERO1)[0])
        # MOST PATTERNS DO NOT CARRY AN OPACITY AT ALL, which is what makes this default
        # load-bearing rather than a corner. Over 195,933 emitted patterns in 20 files:
        #
        #     no opacity, so 1.0 here   163,676   83.5%
        #     in (0, 1]                  29,802   15.2%
        #     negative                    1,195    0.6%
        #     exactly zero                  975    0.5%
        #     above 1                       285    0.1%
        #
        # So a record's appearance is decided by the DEFAULTS for five patterns in six, and
        # a full-cell size at full opacity is what paints an FX-Map solid white -- the
        # `fx.sizeless` and `fx.patternsize` questions, not this one. The 0.6% negative is
        # too small to be a systemic misread of the opacity program; it clips to 0 below and
        # those patterns draw nothing, which for fur_var_001 record 63 means 3 of its 4
        # patterns vanish and the 4th, which carries no parameters at all, fills the cell.
        # That record's white is the FALLBACK drawing, not the scatter.
        col = val(p, 'opacity', _ONE1)
        if size.size < 2:
            size = np.repeat(size[:1], 2)
        if base.size < 2:
            base = np.repeat(base[:1], 2)
        if off.size < 2:
            off = np.repeat(off[:1], 2)
        sx, sy = float(size[0]), float(size[1])
        cx, cy = float(base[0] + off[0]), float(base[1] + off[1])
        # `math.isfinite` on four scalars, not `np.isfinite` on a freshly built list:
        # the numpy form allocated an array per pattern to test four numbers.
        if not (math.isfinite(sx) and math.isfinite(sy)
                and math.isfinite(cx) and math.isfinite(cy)) or sx <= 0 or sy <= 0:
            continue
        if max(sx, sy) > 64.0:
            continue          # a pattern 64 cells across is a misread, not a pattern
        if min(sx, sy) < MIN_PATTERN_SIZE:
            # ...and neither is a pattern 1e-33 cells across. The upper bound above had
            # no lower twin, so a size small enough to make dx / sx overflow float32 was
            # admitted and then neutralised downstream: the ratio came out inf, inf
            # failed the |lx| <= 0.5 test inside profile_value, and the emission drew
            # nothing. Correct output by accident, announced as RuntimeWarning: overflow
            # encountered in divide. A guard that admits a value and leaves a later test
            # to cancel it is not a guard.
            #
            # The threshold is not a round number picked to be safe -- it sits in a gap
            # the corpus itself leaves. Over 40 fxmaps-bearing files, 75,136 finite
            # patternsize components:
            #
            #     <= 1e-30            6   two distinct values, 6.259e-33 and 9.341e-33
            #     next smallest    4.07e-04, then 5.23e-03, ...
            #     max              18.6
            #
            # Twenty-nine decades of empty space between the six and everything else.
            #
            # RE-MEASURED after the FX node/entry walks were drained onto the mask-walk,
            # which changed this population substantially. Over the same 40 files, now
            # 77,358 finite components:
            #
            #     <= 0             939   negative or zero; the sx > 0 test above takes these
            #     <= 1e-30         963   so 24 more that sx > 0 lets through
            #     <= 1e-06         963   nothing at all between 1e-30 and 1e-06
            #     <= 1e-03         964   exactly one value in (1e-06, 1e-03]
            #     min             -0.25  negative sizes exist, which they did not appear to
            #     max              21.8
            #
            # The gap is still there and 1e-6 still sits inside it, with one value the
            # nearest thing to the threshold in either direction. But the numbers above
            # the line are the old enumeration's: the population is 963 rather than six,
            # the smallest positive is 3.6e-42 rather than 6.259e-33, and 939 of them are
            # non-positive rather than merely tiny. The guard does more work than it was
            # documented as doing, and the conclusion is unchanged.
            continue
        if col.size < nchan:
            col = np.repeat(col[:1], nchan)
        col = np.clip(col[:nchan], 0.0, 1.0)

        th = 2.0 * math.pi * rot
        ct, st = math.cos(th), math.sin(th)
        reach = int(min(3, math.ceil(max(sx, sy))))
        prof = profile_for(p)          # depends only on `p`; was recomputed 49 times
        # THE FOOTPRINT, NOT THE CANVAS. profile_value multiplies every profile by
        # `inside = (|lx| <= 0.5) & (|ly| <= 0.5)`, so coverage is exactly zero outside
        # the pattern's own box and a point outside it can never write to the canvas.
        # Evaluating all H*W points per emission was therefore pure waste, and at scale
        # it was the whole cost of the slow test lane: Marble.sbsasm record 450 at 64x64
        # ran 1,930,794 profile_value calls over 7,908,463,104 points -- about 39,400
        # emissions x 49 tile offsets x every one of 4,096 pixels -- and had not
        # finished after 100 seconds.
        #
        # The footprint is a rectangle of half-extents sx/2, sy/2 rotated by th, so its
        # axis-aligned bounding box has half-extents:
        hx = 0.5 * (sx * abs(ct) + sy * abs(st))
        hy = 0.5 * (sx * abs(st) + sy * abs(ct))
        # ONLY THE TILES THAT CAN REACH THE CANVAS. The canvas spans -0.5..0.5, so a copy
        # at offset t contributes only while `cx + t` is within `hx` of that span; every
        # other t produced an empty bounding box and was thrown away one line later. For a
        # pattern a single pixel across -- a carpet tuft at 1/512 -- that was eight of
        # every nine tiles, each costing four scalar floor/ceils to reject.
        #
        # The bounds are the same inequality the box test applies, solved for t, so no
        # tile that used to draw anything is skipped: it narrows the loop, it does not
        # change what any surviving tile does.
        txlo = max(-reach, math.ceil(-0.5 - cx - hx))
        txhi = min(reach, math.floor(0.5 - cx + hx))
        tylo = max(-reach, math.ceil(-0.5 - cy - hy))
        tyhi = min(reach, math.floor(0.5 - cy + hy))
        for ty in range(tylo, tyhi + 1):
            for tx in range(txlo, txhi + 1):
                ux, uy = cx + tx, cy + ty
                # px = (col + 0.5)/W - 0.5, so col = (px + 0.5)*W - 0.5. Floor/ceil the
                # ends rather than round them: a box that clips a pixel must still
                # include it, or the slice would drop coverage the full grid had.
                #
                # `math`, not `numpy`: these are four scalars per tile, and a numpy call
                # on a Python float costs about half a microsecond of dispatch to do one
                # flop. At 262,144 patterns that was most of the splat.
                c0 = max(math.floor((ux - hx + 0.5) * W - 0.5), 0)
                c1 = min(math.ceil((ux + hx + 0.5) * W - 0.5), W - 1)
                r0 = max(math.floor((uy - hy + 0.5) * H - 0.5), 0)
                r1 = min(math.ceil((uy + hy + 0.5) * H - 0.5), H - 1)
                if c0 > c1 or r0 > r1:
                    continue                 # the footprint misses the canvas entirely
                dx = pxg[r0:r1 + 1, c0:c1 + 1] - ux
                dy = pyg[r0:r1 + 1, c0:c1 + 1] - uy
                lx = (dx * ct + dy * st) / sx
                ly = (-dx * st + dy * ct) / sy
                cov = profile_value(lx, ly, prof)
                hit = cov > 0
                if not hit.any():
                    continue
                tile = cview[r0:r1 + 1, c0:c1 + 1]
                if src is None:
                    tile[hit] = np.maximum(tile[hit], col * cov[hit, None])
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
                tile[hit] = np.maximum(tile[hit],
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
