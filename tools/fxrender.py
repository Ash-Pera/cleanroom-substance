#!/usr/bin/env python3
"""Render an fxmaps record, built on sbsasm's own FX naming tables.

Structure and NAMES come from the repository: `Record.fx_node_params()` names the chain's
programs (`numberadded`, `switch`, `randomseed`) and `Record.fx_named_params()` names the
table's (`opacity`, `branchoffset`, `frameoffset`, `patternsize`, `patternrotation`,
`patternsuppl`, `imageindex`), both derived by source containment with controls. What is
added here is only what those tables do not cover: WHEN each program runs, and what to do
with the numbers once you have them.

    addnode   n = numberadded; walk the rest of the chain n times, $number = 0..n-1
    markov2   walk on only if `switch` is true
    table     each entry emits one pattern at the current $number

A node's program is evaluated once per VISIT, not once per record -- that is what lets a
slot the table reads carry a per-iteration value. Assumptions, none from the format:
overlaps combine with `max`; patterns tile into neighbouring cells; the gate passes on true.

WHAT THIS PRODUCES, and where it stops. `Stadsspel__Lines` record 0 renders correctly end
to end: one `0x18B` node over one entry, whose three programs give a per-iteration y step,
a size of (1.414, 0.036) -- 1.414 being the unit square's diagonal -- and 0.125 turns. Ten
bars, 45 degrees, spaced 1/10, from a file named `Lines` whose name the decode never used.
Corpus-wide it does not: over 1,521 records that emit patterns at all, 96% render FLAT, and
patternsize has median 2.82 in records that render flat against 0.50 in records that render
a picture. A pattern 2.8 unit squares wide paints everything one colour, so the coordinate
space `patternsize` is expressed in is the open question, upstream of everything else here.

NEGATIVE RESULTS, recorded so they are not re-run.

1. IT IS NOT THE SHAPE ASSUMPTION. Swapping the filled rectangle for a falloff profile
   takes "renders a picture" from 4.1% to 97.3% -- and means nothing, because a profile
   with falloff cannot produce a flat image BY CONSTRUCTION, so the metric is defeated
   rather than passed. This is why flatness alone must not score a shape hypothesis.

2. THE FRAME IS NOT 1/sqrt(n). The fraction of `patternsize / sqrt(n)` landing in [0.2, 2]
   moves 55.0% -> 60.4% while the spread widens at both ends (p10 0.374 -> 0.060).

3. THE FRAME IS NOT A PER-LEVEL POWER OF TWO ON NODE DEPTH. Over 1,034 pattern-emitting
   records the best-scoring divisor is `2^chain length`, median 0.480 against the 0.50 that
   characterises a record rendering a picture -- and it is WRONG, since Lines record 0 has
   chain length 1 and a patternsize of 1.414, so any divisor above 1 destroys the one
   record known to be correct. Note the shape of that failure: a metric improving while the
   model gets worse.

4. THE TILE LATTICE DOES NOT STEP BY patternsize. `splat` tiles at spacing 1.0, so a
   pattern of size 0.15 gets reach 1 and only its centre copy lands -- while
   ChesterfieldSofa's metallic shows the engine drawing about a 6x6 lattice from such a
   record, and 1/0.15 = 6.7. It is wrong in both directions at once: Lines record 0 goes
   from a lit fraction of 0.510 to 0.936, and ChesterfieldSofa drops from 4 declared
   outputs to 1 with metallic's correlation falling +0.2294 -> 0.0000.

   THE TEST IS THE POINT, more than the result. Every earlier entry needed a bespoke
   measurement to refute and two had to be PARKED because nothing could contradict them.
   This one died in a single run against a two-sided test -- a ground-truth record that
   must keep rendering correctly (Lines record 0) and a reference correlation that must not
   get worse (ChesterfieldSofa), the second half usable only once the matrix fix took that
   file from 659 non-finite records to 0. Anything proposed for the frame question should
   be run against both halves before it is argued about.

5. THE RECIPROCAL READING OF A BAKED patternsize IS UNDECIDABLE ON THIS CORPUS -- stronger
   than "unproven". The reading: a BAKED patternsize is stored as 1/size, and it is not
   idle: the words decode as clean float32 clustering on 5.0, 3.0, 1.5, 8.0, 2.0, 1.0 and
   4.0, whose reciprocals land median exactly 0.500 with 88.7% in [0.02, 1.5] against 41.8%
   as-is, and it explains an asymmetry no frame model did (62% of oversized records have a
   baked patternsize against 27% of correctly-sized ones). WHY IT IS NOT IMPLEMENTED: both
   records with independent ground truth take patternsize from a PROGRAM, so a rule
   touching only baked values cannot break either -- the property that makes it safe is the
   property that makes it unfalsifiable. WHAT WOULD DECIDE IT: a record whose geometry is
   OVERDETERMINED, so the footprint is forced rather than chosen, AND whose patternsize is
   baked. Record 86 is the precedent in the other currency -- six patterns at radius 0.433,
   rotations stepping exactly 1/6 turn, size 0.866 = 2 x radius. Searched: 0 candidates
   over 60 files.

WHY THIS MATTERS MORE THAN THE FILTER WORK. Perturbation over 140 files: of 112 declared
outputs that render flat, the flat SOURCE records in their closure were replaced with
varying patterns and the output re-rendered. 89 then varied, 4 stayed flat, 19 had no flat
source -- so 89 of the 93 testable, 95.7%, are flat because their sources are constant, NOT
because the filter chain destroys variation. The constant sources are `fxmaps` (367) and
`uniform` (300), and nothing else.

A POSITIVE RESULT, source-confirmed: patternsize is a plain [0,1] canvas fraction, and the
open question is a VARIABLE-RESOLUTION problem, not a coordinate-space scale. The permitted
FX-Map sources have no Quadrant node -- their whole vocabulary is addnode (596), paramset
(480), markov2 (80) -- so there is no spatial subdivision to scale a size against, and the
linear-chain model is topologically right. And in 220 of 230 patternsize programs the value
is simply READ from a cross-node variable set in a setup node, not computed at the draw
site. `ie_pcloud`'s own author comment states the chain:

    cloud_img_size = pow2(tofloat2(cloud_size))     # 2 ** cloud_size, an integer2 input
    size_out       = (1, 1) / cloud_img_size        # the reciprocal
    ... paramset patternsize = get_float2("size_out")

With the default `cloud_size = (7, 7)`, `size_out = 1/128 = 0.0078` -- a point in a point
cloud. So the median 2.82 is not a size in a mysterious space; it is what `size_out` reads
when its setup chain has not resolved to its small value by the time the paramset reads it.
This confirms negative-result 5's reciprocal reading as the format's real convention --
size is written as `1/pow2(N)` for PROGRAM sizes, the majority -- and explains the
asymmetry: the oversized records are the ones whose size variable defaulted.

WHAT TO CHECK NEXT. For a cloud record, assert the walk holds `size_out ~= 1/2**cloud_size`
in `slots` at the moment a paramset reads it. If it does not, the setup `set` program that
computes it is either not run before the read or writes a different slot than the read -- a
`seed_slots`/ordering bug -- and that, not a frame scale, is what paints the corpus flat.
The two-sided test from negative-result 4 applies.
"""
import argparse
import os
import math
import re
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assume, disasm, sbsruntime, transpile                                  # noqa: E402
from sbsasm import (Assembly, FX_NODES, FX_NODES2, fx_patterntype,                   # noqa: E402
                    fx_entry_layout, node_shape, leaf_successor,
                    pointer_cell_successor)

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
# is `0x18B`. IT DOES DISTINGUISH THEM -- emitting both and comparing pattern by pattern,
# all 25 DIFFER, the frameoffsets mirrored (0.110, -0.059) against (-0.110, +0.059). What
# washes the difference out is downstream: every pattern has `patternsize` (2.82, 2.82), so
# 25 overlapping give a near-uniform field whichever way the offsets point. The measurement
# that misled me is worth keeping: salting `rand` per record moves every near-zero
# Chesterfield channel slightly the right way, which I read as support for the collapse
# when it is equally consistent with jittering an over-covered field.
ADDNODE = frozenset({0x18B, 0x1AB, 0x20B, 0x1CB})
GATE = 0x89

#: One successor, one unnamed program, and the program is a per-iteration STATE UPDATE
#: rather than a count or a predicate. In StylizedCobblestoneStreet record 27 it reads slots
#: 14/16/17/18 and writes 12/14/16/17/18: a counter in 17 wrapping against 16, a direction
#: vector in 18 rotated a quarter turn when it wraps, and a position in 14 advanced by it.
#:
#: IT IS A RASTER SCAN, not the serpentine this comment first called it -- plotting the
#: emitted offsets in emission order shows each row laid left to right then a jump back to
#: begin the row above, where a serpentine would reverse along alternate rows and need no
#: return. Over the nine records in 260 files that exercise it with more than one pattern,
#: EVERY emission lands at a distinct offset (2304 of 2304, 450 of 450, 256 of 256) against
#: 15% of records without a 0x99, and in all nine the count divides exactly by the number of
#: distinct rows -- nine courses in every brick record (Brick02 r23 432 = 9x48, Brick03 r23
#: 450 = 9x50, PavingStones r44 2304 = 48x48). Where the distinct x count EXCEEDS the row
#: length the extra values are the running-bond offset.
#:
#: It is the pattern's position, not incidental state: the entry's `frameoffset` and
#: `opacity` programs both read slot 12, which the stepper writes as *this* iteration's
#: position. So it runs its program then continues -- run first, then emit.
STEPPER = 0x99

#: 0x9B has the SAME SHAPE as the stepper -- one unnamed program and one successor -- and
#: is walked the same way. sbsasm's FX_NODES2 gives it ((12,), (8,)) where 0x99 has
#: ((16,), (8,)). It became reachable only once 0x0B's successor slot was wired, and the
#: ten records that end their chain on one are exactly the "no readable table entries"
#: failures in the reference set (ChesterfieldSofa 79, Auras 43/250/332/370 among them).
#:
#: TREATED AS A PASS-THROUGH ON ITS SHAPE, not on a decoded meaning. What the program
#: computes is not established -- 0x99 was shown to be a raster scan by reading its slot
#: traffic, and no equivalent reading has been done here -- so this runs it for its slot
#: side effects and continues. If it turns out to gate or to iterate, this is where that
#: would go, and the records above are the specimens.
STEPPER2 = 0x9B

#: The 0x??1B family: ONE child at word 2, a program at word 4, and a CONTINUATION at
#: word 5 -- not two children, which is what test_fx's name for it still says. Both
#: readings satisfy that test, and the file separates them: if word 5 is the continuation,
#: following word 2's subtree along its own next-pointers must ARRIVE at word 5's target,
#: which over every 0x??1B node in 150 files it does in 81 of 81 against 0 of 81 for the
#: control. So a linear walk visits everything a tree walk would. (See PASSTHROUGH: that
#: test is a tautology under the other reading of the same constant.) Two further facts
#: make the flat index walk exactly right, both 81 of 81: the child at word 2 is always the
#: NEXT node in the address-ordered chain, and `progs[None]` is always word 4's program.
#: The program is not a selector -- it is ~104 instructions of `rand` and `cartesian`
#: writing slots 25/27/29/30, a state initialiser, the role STEPPER's program also plays.
BRANCH = 0x1B

#: A THREE-WORD CELL THE CHAIN SIMPLY CONTINUES PAST. RE-MEASURED over all 355 `0x1B` nodes
#: in the corpus plus the reference packs, and the width holds while one of the three
#: original claims does not:
#:
#:     word 1 is the constant 12345 (0x3039)          343 of 355   (the other 12 hold 0)
#:     word 2 addresses word 3, i.e. self + 12        355 of 355
#:     word 3 is a `0x18B` node header                343 of 343   (of the 0x3039 group)
#:
#: WORD 2 POINTS FORWARD, NOT BACKWARDS -- the 34-node sample read the direction wrong. WORD
#: 1 SAYS WHAT FOLLOWS: 0x3039 means a `0x18B` NODE, and in the 12 where it is 0 it is a
#: paramset ENTRY tag, which is what `sbsasm`'s `fx_walk` value probe on `_w1 != 0x3039` is
#: really testing for. THE CONTRADICTION WITH `sbsasm.FX_NODES2` IS RESOLVED in this file's
#: favour: it read `((8, 20), (16,))`, of which only byte 8 was this node's, since words 4
#: and 5 belong to the FOLLOWING node. AND `BRANCH` ABOVE IS THE SAME NODE KIND WITH THE
#: OPPOSITE SHAPE -- both constants are 0x1B, this measurement decides between them, and
#: BRANCH's own test cannot: "word 5 reachable from word 2's subtree, 81 of 81" is a
#: TAUTOLOGY once word 2 is known to address word 3.
PASSTHROUGH = 0x1B

#: The 0x??0B family is where a chain ENDS. Its "programs" are not its own: in record 27
#: the leaf's five programs are byte-identical to the five parameter programs of the table
#: entry it hands off to, at the same five addresses. The leaf IS the entry seen from the
#: node side, so the walk passes straight through it and the table does the emitting.
def _is_leaf(hdr):
    return (hdr & 0xFF) == 0x0B
#: The per-record emission budget. A runtime bound, not a format fact -- a record asking
#: for more is refused rather than rendered slowly.
#:
#: RAISING IT IS NOT THE LEVER IT LOOKS LIKE, measured after batched emission made a
#: million patterns arithmetically cheap. Over the same 30 corpus files at max_dim 64, a
#: cap of 40,000 renders 44 of 127 declared outputs in 74 s, 300,000 renders 44 in 117 s,
#: and 3,000,000 renders 44 in 878 s -- ZERO more outputs for twelve times the wall clock.
#: It was two when this note was first written, before `distance` learned to read its
#: parameter from the derived slot; re-measured rather than carried forward, because a
#: stale comparison is how a number turns into folklore. The blocker-table counts are
#: legitimate squares of a grid dimension, so this budget IS refusing correct work, but
#: those records mostly hit another root as soon as they emit. Splat is what costs now:
#: emission is about 3 us per pattern batched, drawing one is 50-80 us.
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
    # PER ASSEMBLY, NOT PER RECORD. `cache` holds compiled program objects, `spans` program
    # extents and `flows` slot read/write sets -- all keyed on `ptr` alone, none depending on
    # which record is asking. They were being rebuilt per record, so a program reached from
    # two records was transpiled twice: over twelve files, 3,142 transpile() calls for 1,370
    # distinct programs, with the most-shared program built fourteen times.
    _memo = getattr(asm, '_fx_runner_memo', None)
    if _memo is None:
        _memo = ({}, {}, {})
        try:
            asm._fx_runner_memo = _memo
        except AttributeError:
            pass                      # __slots__ assembly: fall back to per-record
    cache, _spans_memo, _flows_memo = _memo

    # BUILT ONCE PER RECORD, NOT ONCE PER EMISSION. The graph's declared input values do not
    # change while a record renders -- they are read straight off `asm.header` -- but this
    # dict used to be rebuilt inside `run`, which an FX-Map calls several times for every
    # pattern. CarpetSubstance001 record 365 emits 262,144 patterns, so the 22
    # `np.array(...).reshape(1, -1)` calls below were being made about six million times.
    # Safe to share: `Perm` is only ever READ by transpiled code, and its `__missing__`
    # returns a default without storing it.
    shared_inputs = Perm()
    for _t, uid, val in asm.header.get('inputs') or []:
        if val:
            shared_inputs[uid] = np.array(val, dtype=np.float32).reshape(1, -1)

    # `program_span` is memoized inside the assembly, but reaching that memo is still a
    # method call and a tuple hash per emission. Keyed by ptr alone here because
    # `asm.body_hi` is fixed for the life of the assembly.
    spans = _spans_memo

    flows = _flows_memo

    def flow(ptr):
        """(slots read before this program writes them, slots it writes).

        The batched emission below needs to know whether a slot a program writes is SCRATCH --
        written before it is ever read, so the value it arrived with cannot matter -- or STATE
        carried from the previous pattern. The distinction is visible in the transpiled source,
        which assigns and reads slots by literal index, so it is read off there rather than
        guessed from the values. Reported for the program alone: a slot that is scratch here can
        still be state for the record if ANOTHER program reads it without writing it first, which
        is why the caller unions `read_first` across every program that can run.
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
                # MUST precede the bare KeyError: MissingSampler subclasses it, so without this an
                # unwired image input is reported as a missing SLOT. render.py had exactly this bug, it
                # was fixed there, and this file -- committed one turn later -- reintroduced it. It is
                # why an A/B over the sampling records showed "no sampler 0" in every arm while 18
                # records failed with a message about slots.
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

    A NARROWED FORM OF A READING THAT WAS WITHDRAWN, and the withdrawal was right about what it
    measured. `sbsasm.fx_named_params` used to re-read a failed program pointer as an inline
    program, and 9ff1354 removed it: of the 2,717 programs that recovered, the 1,910 whose
    entry HAS A SUCCESSOR sit past the next entry's tag in 1,910 of 1,910 -- bytecode from a
    later structure -- and deciding pointer-vs-inline from whether `word - 52` lands on
    decodable bytes invented an `imageindex` that duplicated an earlier pointer 2,056 times.

    That leaves 807 unexamined, the ones with no successor, and the split is total: 14
    recovered programs lie INSIDE their own entry and all 14 are the LAST entry, while 4 lie
    beyond the next tag and all 4 have a successor. But "it is the last entry" is weak, since
    for a last entry the bound is just the record's end. So the gate is whether the recovery
    ANSWERS A QUESTION THE RECORD ASKS: does the program write a slot another parameter of the
    same entry reads before writing, and that no other program in the record writes? Of the 14,
    exactly 7 do -- and three of Auras's four declared outputs hang on slot 15 having a writer.
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


def in_eval_order(params):
    """An entry's parameters, in the order the engine evaluates them.

    PROGRAM ADDRESS ORDER, NOT TABLE ORDER, and the two disagree. Entry parameters talk to each
    other through the slot frame -- one writes a slot another reads -- so where they do, only
    one order is defined. Counting every such pair: 437 dependent pairs over 25 corpus files
    where both orders score 437/437, and 192 in the reference packages where address scores
    192/192 against table order's 182/192. 629 of 629 against 619 of 629, and the ten
    disagreements all fall the same way. Auras record 49 is the clearest: `opacity` sits first
    in the table and reads slot 15, while `patternrotation` sits second and WRITES it -- at the
    lower address -- so in table order the record dies on `slot 15 read but never set`, which
    blocks three of the four declared outputs of the smallest reference specimen. Baked
    parameters are constants and cannot participate, so they go first.
    """
    return sorted(params.items(),
                  key=lambda kv: (kv[1][0] != 'baked',
                                  kv[1][1] if isinstance(kv[1][1], int) else 0))


def entries(rec, baked_pairs=True):
    """[(offset, tag, {name: (kind, value)})] in table order.

    `baked_pairs` additionally reads each UNNAMED baked (odd) bit as the baked form of the
    parameter the next even bit names -- the reading argued for in FX-RENDER-HANDOFF.md
    section 3, and NOT what sbsasm's FX_PARAM_BITS says. It is a flag precisely so the two
    readings can be compared: with it off, an entry that bakes its patternsize falls back to
    a full-cell default and paints the whole canvas.
    """
    # THE TABLE IS THE ENTRY LIST, NOT THE PARAMETER LIST. This used to derive `order` from
    # fx_named_params(), so an entry whose tag sets no parameter bits was invisible and the
    # record reported "no readable table entries" -- 9,385 entries across 220 files, and 950
    # records that thereby had no table at all. They are not nothing: the patterntype still
    # rides in the tag's nibble 2, so a paramless entry is a pattern of a stated shape at
    # default transform. That they are real entries and not a walk running into bytecode is the
    # program-span containment control, with both of its controls in one measurement:
    #
    #     group           entries   inside a program span
    #     parameterised      5621        1        0.0%     (known good)
    #     paramless8         9385        0        0.0%
    #     other-nibble        808      112       13.9%     (known bad: node headers)
    #
    # Restricted to nibble 8 for exactly that reason. The payload-pointer test cannot be used:
    # a paramless entry has no program, so its +4 word points nowhere by construction.
    #
    # ...WITH ONE EXCEPTION. For the CHAIN FAMILY -- high 16 bits 0x0002 -- "the patterntype
    # rides in nibble 2" is empty: nibble 2 is zero and `fx_patterntype` returns None for every
    # one. They are structural, not draws -- 98.5% of 6,918 chain-family typeless entries point
    # at the entry that follows against 15.9% of 5,439 other typeless ones, a linked list
    # rather than a table of independent patterns, and emitting one full-cell fill each is what
    # paints a record white. "SKIP ENTRIES WHOSE PATTERNTYPE IS None" IS NOT EQUIVALENT, and
    # that second row is why: it would drop 5,439 entries that mostly do not chain, among them
    # 3,332 of tag 0x00420008, which `FX_ENTRY_PROGS` gives a program slot. Those are real draws.
    #
    # WITHDRAWN, A THIRD DISCRIMINATOR: "bit 6 of the tag's low byte". It looked strong -- the
    # low byte is 0x48 on essentially every named-patterntype entry and 0x08 on the bulk of
    # nibble 0, `fx_entry_layout` never reads bit 6 so the two halves are independent
    # declarations, and the chain family falls out almost exactly (4,455 of 4,456). Still
    # wrong: strictly broader than the chain family, and the 2,899 entries it would newly
    # exclude score 3.5% on the next-pointer test that established the family -- BELOW the
    # 13.8% of the bit-6-set entries they would be separated from. So bit 6 marks something
    # nearer "the patterntype nibble is meaningful" than "this entry is structural", and the
    # white-generator family is NOT explained by it. That stays open: 97 of 97 solid-white
    # fxmaps records in Kutejnikov__Bricks_and_tiles have a typeless entry and 0 have none --
    # but so do 17 of the 94 that are not white.
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
    # entirely, landing on a real draw the table otherwise never reaches.
    #
    # Containment says so rather than plausibility. `SubstanceDesigner__Clouds_3_Animated` is
    # permitted, declares exactly two `paramset` nodes carrying patterntype 8, patternsize
    # "3 2" and randomseeds 42 and 16, and its own binary's record 50 walks four chain-family
    # entries and stops. The fourth's next-pointer lands on tag 0x13520658 -- patterntype
    # nibble 6, so type 8 -- whose parameter block holds 42 and (3.0, 2.0); the second entry
    # holds 16 and (3.0, 2.0). Two of two, on three declared values each, and the randomseeds
    # tell the two apart. 20 records across 30 corpus files reach a draw entry this way.
    for _o in chain_family:
        if _o + 8 > len(rec.asm.data):
            continue
        _nxt = struct.unpack_from('<I', rec.asm.data, _o + 4)[0] + 52
        if not (rec.asm.body_lo <= _nxt < rec.asm.body_hi - 7) or _nxt in tbl:
            continue
        _t2 = struct.unpack_from('<I', rec.asm.data, _nxt)[0]
        # THE TARGET IS A HEADER WORD, AND THE ENTRIES START AFTER IT. A chain-family entry's `+4`
        # pointer does not address another entry -- it addresses word 3 of the entry ITSELF, which
        # holds a small non-tag word, and the run begins one word later:
        #
        #     [0x00020018] [ptr] [ptr] [<header word>] [0x00420008] [ptr] ...
        #                                ^ _nxt lands here   ^ the entries
        #
        # so reading at `_nxt` finds a word that is not a tag and this loop gave up one word short
        # of the table. Stepping over it: of 143 chain-family entries, 134 have an entry tag in the
        # word AFTER the header word, and a table read from there yields 6 entries in 133 of them.
        # AND THEY ARE REAL ENTRIES BY THIS FILE'S OWN TEST: `entry_layout_holds` catches a walk
        # running into bytecode -- a tag naming programs none of which resolve is not a tag --
        # separating 49,528 real entries from 3,192 junk ones at 0.0% against 82.1%, and every
        # entry recovered here passes it, 800 of 800. Six entries appearing where there were none
        # is exactly the shape a runaway produces, which is why the gate is the evidence and the
        # count is not. The header word reads 2 while the run yields 6, so it is NOT a count.
        if (_t2 & 0xF) != 8 or (_t2 >> 16) == 0x0002:
            # NARROWER THAN 4fc0303 AND NOT A REPLACEMENT FOR IT. That commit reads the payload
            # pointer the cell itself stores and walks the whole alternating list; this follows one
            # target, so where a list names several payloads that walk gets them all and this gets
            # one. It is here because measurement says it still reaches records the walk does not.
            #
            # Measured against HEAD on the same 30 files: with `fx_tree`'s pointer-cell walk alone
            # the table blocker is 22 declared outputs and 15 outputs render FLAT; stepping this one
            # word as well gives 11 and 9, and takes `flat from blend` 4 -> 0 and `flat from shuffle`
            # 1 -> 0. A flat output already counts as rendered while carrying no information, so
            # those six are the substantive part.
            _after = _nxt + 4
            if _after + 4 > len(rec.asm.data) or _after in tbl:
                continue
            _t3 = struct.unpack_from('<I', rec.asm.data, _after)[0]
            if (_t3 & 0xF) != 8 or (_t3 >> 16) == 0x0002:
                continue
            if not rec.asm.entry_layout_holds(_after, _t3):
                continue
            _nxt, _t2 = _after, _t3
        for _at, _tag, _p in rec.fx_table(_nxt):
            if _at in tbl or (_tag & 0xF) != 8 or (_tag >> 16) == 0x0002:
                continue
            tbl[_at] = (_tag, {})
            order.append(_at)

    # `_chain_embedded_entries` STOOD HERE and is gone. It reached around the walk to a chain
    # cell's payload with an `(0x09, 0x49)` allowlist, `off + 8` as a constant slot, and a
    # hardcoded 12-byte step. `fx_tree` now walks both cell kinds by the pointers they store,
    # so the table arrives here the ordinary way. Verified dead before removal: of the 233
    # records `entries()` still returns empty for, it would have added entries to 0.
    _recover_last_inline(rec, tbl, order)
    if baked_pairs:
        for off in order:
            tag = tbl[off][0]
            for bit, sl, width in baked_slots(tag):
                partner = PARTNER.get(bit)
                if partner is None:
                    continue
                # A MULTI-COMPONENT BAKED PARAMETER MUST NOT BE LEFT AS A SCALAR. `fx_named_params` used
                # to hand a baked parameter back as its single raw slot WORD, and `emit` unpacked that
                # one word into one float, which for a parameter the layout declares at width 2 silently
                # discards the second component: over 20 files, 928 entries -- 921 `patternsize`, 6
                # `frameoffset`, 1 `branchoffset` -- and the values lost are not degenerate.
                # ChesterfieldSofa record 331 stores (5.0, 1.0), a 5:1 strip, and we drew a 5x5 square.
                #
                # THE WIDTH OVERRIDE IS GONE, because the read it compensated for is fixed at the root:
                # `fx_named_params` now yields a baked parameter at its declared WIDTH. This loop is back
                # to what it is for -- pairing an UNNAMED baked bit with the parameter the next bit names.
                if partner in tbl[off][1]:
                    continue
                # THE SLOT IS INLINE ONLY WHEN THE ENTRY SAYS SO. An entry's +4 word addresses its
                # parameters; usually that is off+8 and the slots follow the tag, which is what this read
                # assumes. Where it points somewhere else the parameters are in a separate block and
                # reading inline returns whatever sits there -- for Clouds_3_Animated record 50 that is
                # (0.0, 0.0) against a source-declared patternsize of (3, 2). The block IS locatable, but
                # two specimens do not establish the slot arithmetic inside it: patternsize lands at
                # block+4 slots for one entry and block+3 for the other. So this DECLINES rather than
                # guessing, and the parameter reads as absent instead of as zero.
                if not (off + 4 <= len(rec.asm.data) - 4):
                    continue
                _w1 = struct.unpack_from('<I', rec.asm.data, off + 4)[0] + 52
                # NARROWED TO THE CONFIGURATION THE SPECIMEN SHOWS. `fx_table` calls this word the
                # entry's PAYLOAD, and for most entries it plausibly addresses a program while the baked
                # slots stay inline -- declining all 399 non-inline reads over 12 files on the strength
                # of two entries would be over-broad. What both Clouds entries have is a word1 pointing
                # BACKWARD, before the tag, where an inline slot cannot be. 15 entries in 30 files.
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
    # ONE WALK, not a second implementation. This used to re-walk FX_PARAM_BITS itself and
    # claimed the two were identical; they were not, and `sbsasm.fx_entry_walk` records the
    # measurement. Deriving from that walk means they cannot drift again.
    from sbsasm import fx_entry_walk
    return [(bit, sl, width) for bit, sl, _name, kind, width in fx_entry_walk(tag)
            if kind == 'baked']


def _partners():
    from sbsasm import FX_PARAM_BITS, FX_PROGRAM_BITS
    names = {b: n for b, n, _w in FX_PARAM_BITS}
    return {b: names.get(b + 1) for b, _n, _w in FX_PARAM_BITS
            if b not in FX_PROGRAM_BITS and (b + 1) in FX_PROGRAM_BITS}


PARTNER = _partners()


#: The raster-scan state slots, and what an FX-Map that initialises them EXPLICITLY writes.
#: Some records carry a program that assigns these constants before anything reads them
#: (0x18B, the addnode above the 0x99 scanner); others read the same slots with no such
#: program and used to die on "slot N read but never set". Read off the records that DO
#: initialise, over 20 files, counting only assignments built entirely from literals:
#:
#:     slot 12   (0.0, 0.0) x710, 0.0 x96          zero, unanimously
#:     slot 14   (0.0, 0.0) x710                   zero, unanimously
#:     slot 16   0 x710, (0.0, 0.0) x92            zero, unanimously
#:     slot 17   0 x711                            zero, unanimously
#:     slot 18   (1.0, 0.0) x710, (0.0, 0.0) x92, 0 x1     NOT unanimous -- excluded
#:     slot 13   2.82 x92, 0.0 x4, (0.0, 0.0) x1           NOT unanimous -- excluded
#:
#: Only the four that agree are seeded. 18 and 13 are why this is a measured table and not
#: `default everything to zero`: 18's initialisers say (1.0, 0.0) seven times out of eight,
#: so a blanket zero would have been confidently wrong on the slot holding the scan
#: DIRECTION. `setdefault`, and only after `seed_slots` has run the record's own programs.
SCAN_STATE_DEFAULTS = {12: 0.0, 14: 0.0, 16: 0.0, 17: 0.0}


def seed_slots(rec, run):
    """Run the record's OWN non-FX programs once, so the table can read what they set.

    The FX table reads slots the chain never writes -- 58.9% of fxmaps records died on
    `slot N read but never set` when only the chain was run. The writers are the record's
    other programs, which is what "the slot frame is per-RECORD" (99.892% against an 11.8%
    control) says: the frame's unit is the record, so every program the record names shares
    it. Evaluated once at N=1 into the dict the walk then uses. Takes rendering from 27.9%
    to 85.2% of fxmaps records -- the single largest lever in this file.
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
    # ONLY WHERE THE CHAIN HAS A SCANNER, and the unconditional version was a mistake caught
    # by reading what it produced. These slots are the 0x99 raster scan's own state, and a
    # record whose chain contains no scanner has no such state to start.
    # CarpetSubstance001 records 70 and 163 are the specimens: their chain is a lone 0x18B,
    # their entry reads `patternsize` straight out of slot 17, and seeding it to zero made
    # 32 patterns of size ZERO -- solid black, where it used to REFUSE with `slot 17 read
    # but never set`. Trading a refusal for a blank image is the one trade this renderer is
    # not allowed to make. The evidence the defaults rest on says the same on a re-read:
    # every explicit initialiser measured belongs to a record that ALSO carries a scanner to
    # advance them. Zero is where the scan STARTS, not what the slot means without one.
    if any(h == STEPPER or (h & 0xFF) == STEPPER2 for _o, h, _p in chain(rec)):
        for slot, value in SCAN_STATE_DEFAULTS.items():
            slots.setdefault(slot, value)
    return slots


#: `$number` is system variable 10, and `floor($number / N)` is a grid's row index with N
#: its width. Read by following the SSA names rather than by matching a fixed instruction
#: offset, so a record whose program is ordered differently still resolves.
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
    `$number` read in all four Chesterfield specimens. Read semantically rather than at
    instruction 10, because that offset is verified on four records that share a program
    almost byte-for-byte and could shift elsewhere.
    """
    asm = rec.asm
    # THE FX WALK NAMES THE CANDIDATES, not `Record.programs`. `programs` reaches an fxmaps
    # record's payload through a scan over the record's words that is deliberately unbounded
    # for this filter, which makes the candidate list a superset of the structure: an
    # instruction operand inside an FX program's bytecode can enter it, and this function
    # would then transpile bytecode and read a divisor out of it. It does not today, and
    # that was checked rather than assumed -- over 10 files, all 22 records that yield a
    # grid width yield it from a program `fx_walk` names.
    cands = set()
    try:
        for _item in rec.fx_walk():
            _p = _item[3] if len(_item) > 3 else None
            if _p:
                cands.add(_p)
    except Exception:
        cands = set()
    if not cands:
        cands = set(rec.programs or ())
    for ptr in sorted(cands):
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
                # THE UPPER BOUND SITS IN A GAP THE CORPUS LEAVES, which is what makes it a guard rather
                # than a taste. Over 80 files the divisors found run 2, 3, 4, 5, 6, 7, 8, 10 ... 50, 64
                # -- 355 records, dense to 64 -- and then nothing at all until 128, 130 and 16384, which
                # is 6 records. The large ones are not grids: 16384 is 128 squared, and a divisor that
                # size is $number used at PIXEL granularity, a coordinate normalised by the canvas, not
                # a stamp index; emitting N^2 there would ask for 268 million patterns. So the bound is
                # the line between two uses of $number, and the corpus draws it rather than this code.
                if n == int(n) and 1 < n <= 64:
                    return int(n)
    return None


def inline_input_refs(rec, off, limit=None):
    """The input references an FX entry stores INLINE at slot 2, as [(uid, width, value)].

    An entry of this family is `[tag][word][inline program]+` -- the programs are not
    addressed by the tag's pointer slots, they ARE the words those slots occupy, which is
    why every predicted pointer resolves to nothing. Each leading program is one or more
    `inputref` instructions (opcode 0x02, width `((op >> 6) & 3) + 1`) naming a uid the
    file's own header declares; `value` is that declaration, or None if absent.

    The walk stops at the first thing that is not such a reference, because the longer
    entries carry further content after them.

    Measured over the corpus, against both populations that matter:

        the refused handoff entries recognised    24 of 27     89%
        known-good entries (false positive)        6 of 2,351  0.26%
        bytecode inside real program spans         3 of 1,969  0.15%

    Every recognised entry leads with a WIDTH-2 reference: widths are (2, 1) on 12 and
    (2,) on 12. In `roofing_007` the pair is `0xb90ebc63` (type 8, value (8, 8) -- log2 of
    256x256) and `0xee7caa31` (type 4, value 0), the same uids in every entry of the file.

    DIAGNOSTIC ONLY, AND DELIBERATELY NOT WIRED INTO `entries()`. What each reference IS
    remains unknown: the tag's mask declares 3 or 5 program parameters against 1 or 2 inline
    references, so it does not describe these slots, and no permitted source sets the bits
    that would name them. Admitting the entry would let `emit` read parameters positionally
    out of a layout that does not match the data, which paints a plausible wrong picture --
    strictly worse than refusing. This function exists so the structure is READABLE by
    whoever closes the naming gap, and so `why_no_entries` can report what is actually
    there instead of calling it unreadable.
    """
    a = rec.asm
    decl = {u: v for _t, u, v in (a.header.get('inputs') or [])}
    lim = rec.offset if limit is None else limit
    q, out = off + 8, []
    while q + 4 <= lim and len(out) < 8:
        sp = a.program_span(q, a.body_hi)
        if not sp or sp <= q:
            break
        try:
            ins = list(disasm.decode(a.data, q, sp))
        except Exception:
            break
        if not ins:
            break
        got = []
        for _k, addr, op, toks in ins:
            if (op & 0x3F) != 0x02:
                got = None
                break
            try:
                u = disasm.uid(addr, toks)
            except Exception:
                got = None
                break
            if u not in decl:
                got = None
                break
            got.append((u, ((op >> 6) & 3) + 1, decl[u]))
        if got is None:
            break
        out.extend(got)
        q = sp
    return out


def why_no_entries(rec):
    """Why `entries()` came back empty -- the WALK, or the table read?

    "no readable table entries" named the table for every one of these, and the table read is
    not what fails in most of them. `entries()` consumes `rec.fx_table()`, the tail of
    `rec.fx_walk()`: the node chain ends by pointing AT the first entry, so a walk that stops
    at its root reaches no table at all, and reporting that as a table failure sends the reader
    to the wrong half of the structure -- it sent this one there, and the fix attempted from it
    was a table patch for a record whose table read never ran. Corpus-wide, of the records
    `entries()` returns empty for: 192 have raw entries all filtered out (a table question), 46
    reached NOTHING and 7 walked nodes without handing off (both WALK questions). Diagnosis
    only.
    """
    asm = rec.asm
    try:
        walk = list(rec.fx_walk())
    except Exception as exc:
        return "fx_walk raised %s: %s" % (type(exc).__name__, exc)
    nodes = [t for t in walk if t[0] == 'node']
    raw = [t for t in walk if t[0] == 'entry']

    if raw:
        # SAY WHICH KIND, because "entries reached, none usable" points at the table read and
        # for most of these the run never reached a table at all. The bit-7-clear families --
        # leaf, branch, pointer cell -- are not entry tags: they end in nibble 9 or B where an
        # entry ends in 8. Over the records this branch fires on, the raw run is 32 pointer
        # cells, 22 leaves and 4 chain-family links against a handful of real tags. NOT a reason
        # to stop the run on them -- that was measured and withdrawn; a pointer cell is a
        # WAYPOINT, and breaking on one cost 80 records their table.
        cells = sum(1 for _k, _o, t, _p in walk
                    if _k == 'entry' and (node_shape(t) is not None
                                          or leaf_successor(t) is not None
                                          or pointer_cell_successor(t) is not None))
        links = sum(1 for _k, _o, t, _p in walk
                    if _k == 'entry' and (t >> 16) == 0x0002)
        tags = len(raw) - cells - links
        if not tags:
            return ("walk: the run reached %d node/cell header(s) and %d chain link(s) and "
                    "no entry tag -- there is no table at the end of this chain"
                    % (cells, links))
        return ("table read: %d entry tag(s) reached, none usable (alongside %d node/cell "
                "header(s) and %d chain link(s), which are not tags)" % (tags, cells, links))

    def header_at(off):
        if off is None or not (asm.body_lo <= off < asm.body_hi - 3):
            return None
        return struct.unpack_from('<I', asm.data, off)[0]

    if not nodes:
        try:
            root = rec.fx_root
        except Exception:
            root = None
        if root is None:
            return "walk: no root slot (decompose declines this record)"
        h = header_at(root)
        if h is None:
            return "walk: root slot addresses %#x, outside the body" % root
        # "NOT IN THE VOCABULARY" WAS AN INFERENCE, AND IT WAS WRONG. This read the header and
        # concluded the walk must have refused it. For all 12 records in this branch that is
        # false: the header is `0x1b`, `FX_NODES2` has it, and the walk stops for an unrelated
        # reason -- `FX_NODES2[0x1B]`'s program tuple is EMPTY and `fx_tree` yields only from
        # inside `for sl in prog_slots`. Exactly the misattribution this function exists to
        # prevent, one level further in, so it now ASKS the derivations instead of guessing.
        known = (node_shape(h) is not None or leaf_successor(h) is not None
                 or pointer_cell_successor(h) is not None or (h & 0xFF) in FX_NODES2)
        where = ('' if rec.offset <= root < rec.end
                 else ' (and the root lies outside the record, inside the body)')
        if not known:
            return ("walk: stopped AT THE ROOT, %#x holds header %#010x -- no derivation "
                    "and no table row knows it%s" % (root, h, where))
        return ("walk: root %#x holds header %#010x, which the vocabulary DOES know -- the "
                "walk reached it and yielded no node, so nothing handed off to a table%s"
                % (root, h, where))

    last = nodes[-1][1]
    h = header_at(last)
    # SAY WHAT THE HANDOFF TARGET ACTUALLY HOLDS. It is not unreadable: for 24 of the 27
    # records in this branch it is an entry storing its programs inline as references to
    # inputs the file itself declares. See `inline_input_refs` -- what is missing is which
    # parameter each reference is, not what is there.
    _sh = node_shape(h) if h is not None else None
    if _sh:
        try:
            _t = struct.unpack_from('<I', asm.data, last + _sh[0])[0] + 52
            if asm.body_lo <= _t < asm.body_hi - 8:
                _r = inline_input_refs(rec, _t)
                if _r:
                    return ("walk: %d node(s) reaching an entry at %#x that stores %d inline "
                            "input reference(s) %s -- structure read, but the tag's mask does "
                            "not name them, so no parameter can be assigned"
                            % (len(nodes), _t, len(_r),
                               ', '.join('%#x(w=%d)=%s' % (u, w, v) for u, w, v in _r)))
        except Exception:
            pass
    return ("walk: %d node(s), then no handoff -- last node %#x holds header %#010x, "
            "whose successor reaches no table" % (len(nodes), last, h if h is not None else 0))


def emissions(rec, run, gate_polarity=True, baked_pairs=True, slots=None):
    slots = {} if slots is None else slots
    nodes = chain(rec)
    table = entries(rec, baked_pairs)
    if not table:
        # WHAT AN FX-MAP WITH NO DRAWABLE ENTRIES EMITS IS AN OPEN QUESTION, AND IT IS THE LAST
        # ONE HERE. 41,088 fxmaps records yield entries and 76 do not, and all 76 are structural
        # refusals rather than decode gaps: for the 41 that walk and never hand off, EVERY slot
        # 1..7 of the terminal node was followed and none reaches an entry passing
        # `entry_layout_holds`; the 27 ending on `0x19b` point 24 bytes BEFORE their own record.
        #
        # THEY ARE NOT INERT -- over the 28 files that contain one, 30 declared outputs are
        # BLOCKED ONLY BY these, last in cone. NOT DECIDED HERE, because nothing settles it: the
        # reference packs are disjoint from `corpus.paths()`, so the render arbiter cannot see
        # these records, and "it would make 30 more outputs appear" is the kind of argument this
        # file exists to refuse. What would settle it: one reference-pack record with an empty
        # drawable table, rendered against its own reference image.
        # THE 27 ARE DECODED. Their structure is the ordinary walk, not a mode a flag
        # switches into, and looking for the flag is what kept this closed: bit 17 separates
        # the family from working tags 0% against 70%, and predicts NOTHING -- program slots
        # resolve as pointers in 99.8% of entries whether it is set or clear.
        #
        # THE ENTRY IS `[tag][word][inline program][inline program]`, each program stating
        # its own extent, and the pair tiles to the record that follows: 12 of 27 land
        # exactly on the record start and 12 more within 2 bytes (instructions are
        # byte-granular). Not pointers to programs -- the programs are THERE, which is why
        # every predicted pointer slot resolves to nothing and `entry_layout_holds` refuses.
        #
        # BOTH PROGRAMS ARE ONE `inputref` INSTRUCTION. Opcode 0x02 in all 51, widths
        # `((op >> 6) & 3) + 1` = 2 then 1, each carrying a uid, and the same uids repeat
        # across every entry in a file. So an entry of this family holds no numeric
        # parameters at all: it REFERENCES the graph's declared inputs. That is what
        # `fx_entry_layout`'s inline note already observed from the other side -- "98% of
        # these open with `inputref`, so they are image references rather than numeric
        # parameters" -- reached here by walking rather than by a value test.
        #
        # AND THE FILE DECLARES THEM. Every uid resolves in the header input table, 51 of 51:
        # `roofing_007` reads `0xb90ebc63` (type 8, width 2, value (8, 8) -- log2 256x256)
        # and `0xee7caa31` (type 4, width 1, value 0). `default_inputs` already reads that
        # table, so these values are recoverable from the file's own declarations.
        #
        # WHAT IS STILL NOT KNOWN is WHICH parameter each reference is. The tag's mask
        # declares 3 or 5 program parameters and there are 2 inline programs, so the mask is
        # not describing these slots, and no permitted source sets the bits that would name
        # them -- `fx_entry_layout`'s note says so for exactly this population. Structure
        # decoded, naming not, and emitting a pattern needs the naming.
        #
        # So the refusal stands, and it is now a NAMED gap rather than an opaque one. What
        # would close it: one permitted source whose FX-Map entry references an exposed
        # input, pairing a uid to a parameter name.
        raise Unmodelled("no emittable entries -- %s" % why_no_entries(rec))
    for _off, hdr, _p in nodes:
        if hdr not in ADDNODE and hdr != GATE and hdr != STEPPER \
                and (hdr & 0xFF) != STEPPER2 and (hdr & 0xFF) != PASSTHROUGH \
                and (hdr & 0xFF) != BRANCH and not _is_leaf(hdr):
            # THE UNMODELLED HEADERS COME AS A FAMILY, and treating one as a passthrough
            # only moves the failure to the next. Recorded so the experiment is not re-run.
            #
            # `0x1db` is the header the census names, 22 declared outputs behind it. It is
            # in the node vocabulary -- `node_shape` gives (16, (8,)) -- and it sits at the
            # chain ROOT with a downstream chain that is entirely recognised:
            #
            #     0x1db -> 0x1a3 -> 0x1a3 -> 0x89 -> 0x89 -> 0x19b -> 0x99 -> 0x18b
            #                                GATE    GATE            STEPPER  ADDNODE
            #
            # identical in both files that carry it (flowingLava_v35 record 112, Cliff
            # record 1). All 19 of its nodes in the corpus and the reference packs have the
            # same shape: `+4` is the constant 0x00000002, `+8` a child, `+16` the
            # successor, and `chain()` attaches NO named program to it -- so it is not an
            # ADDNODE, which needs a `numberadded`.
            #
            # One child, one successor, no program reads like a passthrough, and that was
            # tested rather than assumed: skipping 0x1db here clears its 6 record failures
            # and renders NOTHING new -- 3,149 records and 2 declared outputs before and
            # after -- because the failure simply becomes `node header 0x1a3 is not
            # modelled`, the next node in the same chain. 0x1a3 has 0x1ab's shape
            # (12, (4, 8)) as 0x1db has 0x1cb's, so both are one-bit neighbours of ADDNODE
            # members and neither is one.
            #
            # So this is an unmodelled sub-family, not a missing row, and a passthrough for
            # each would be a chain of guesses producing a plausible wrong picture. Naming
            # what these kinds DO needs evidence this refusal is protecting.
            raise Unmodelled("node header %#x is not modelled" % hdr)

    out = []

    # THE RECORD'S OWN PROGRAMS SEED THE FRAME. The "slot frame is per-RECORD" finding
    # counts as writers the node chain AND the record's own programs -- 99.892% of entry
    # slot reads resolve against an 11.8% control. Running only the chain left 58.9% of
    # records failing on `slot N read but never set`, because the record's own programs are
    # where the constants live.
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
    # program that writes a slot is not by itself a reason to refuse batching -- the commonest
    # case is a per-pattern random seed whose incoming value cannot matter. What would break
    # batching is a slot carried BETWEEN patterns. AND THE ORDER MATTERS, which the first
    # version of this check missed: on CarpetSubstance001 record 365 `opacity` writes slots
    # 26, 28, 29 and 31 and four other parameters each read one, so a bare union calls that
    # carried state -- but the write happens first, in the same emission, and batching
    # preserves it exactly. So the walk is simulated instead: parameters in evaluation order,
    # and a read counts as CARRIED only if a parameter writes that slot and nothing has
    # written it yet this emission.
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
            # THE TAG TRAVELS WITH THE PATTERN. The shape is selected per entry from `patterntype`,
            # and by the time `splat` runs the tag is gone -- so it is attached here rather than
            # re-derived, which would mean re-walking the table and guessing which entry produced
            # which emission.
            got = {'patterntype': fx_patterntype(_t), '_tag': _t}
            for name, (kind, value) in in_eval_order(params):
                if value is None:
                    continue
                if kind != 'baked':
                    got[name] = run(value, slots, number)
                elif isinstance(value, np.ndarray):
                    got[name] = value          # already decoded by `baked_slots`
                else:
                    # `fx_named_params` yields a baked parameter as a TUPLE OF FLOATS, one
                    # per declared word -- see its docstring. It used to hand back the raw
                    # slot word, and width-2 parameters lost their second component.
                    got[name] = np.asarray(value, dtype=np.float32).ravel()
            out.append(got)

    def emit_batch(numbers):
        """`emit` for a whole range of pattern indices, in one evaluation per parameter.

        WHY THIS IS THE WHOLE COST. An FX-Map parameter program is a few dozen numpy operations on
        ONE row, and numpy charges per call, not per element: profiling CarpetSubstance001 record
        365 counted 1,341 Python calls per emitted pattern, and that record emits 262,144 of them.

        WHEN IT IS ALLOWED. Batching evaluates every pattern against ONE slot frame, so it is only
        equivalent where the frame does not move between patterns: every node below the addnode
        must be a leaf (a raster scan or a gate would advance or branch per pattern, and the caller
        checks this), and no parameter program may WRITE a slot -- not statically known here, so
        pattern 0 is emitted scalar first and the frame compared by identity. A program that
        ignores $number returns a single row, broadcast rather than indexed.
        """
        m = len(numbers)
        cols = []
        for _o, _t, params in table:
            per = {'patterntype': fx_patterntype(_t), '_tag': _t}
            wide = {}
            for name, (kind, value) in in_eval_order(params):
                if value is None:
                    continue
                if kind != 'baked':
                    a = np.asarray(run(value, slots, numbers, flatten=False))
                    # NORMALISE TO (rows, components) AND SAY WHETHER THE ROWS ARE PATTERNS. A program that
                    # ignores $number returns one row however wide it is, and the module's 1-D convention
                    # only holds when the length IS the batch -- a 1-D result of any other length is one
                    # value's components, which is what the scalar path's `.ravel()` hands back.
                    if a.ndim == 0:
                        a = a.reshape(1, 1)
                    elif a.ndim == 1:
                        a = a[:, None] if a.shape[0] == m else a[None, :]
                    wide[name] = a
                elif isinstance(value, np.ndarray):
                    per[name] = value
                else:
                    # THE SAME DECODE THE SCALAR PATH DOES, and this is where the two drifted. `emit` was
                    # corrected to read a baked parameter as the TUPLE OF FLOATS `fx_named_params` yields;
                    # this half never got that correction and still reinterpreted an integer word as a
                    # float. It could not work: `int(value)` on a tuple raises, so EVERY batched record
                    # carrying a baked entry parameter died here -- not merely the width-2 ones, since
                    # `int((0.5,))` raises just as `int((0.0, 0.19))` does. It surfaced as a TypeError
                    # rather than an Unmodelled, which is why it read as an exotic record instead of a bug:
                    # Chipboard 1682, whose `frameoffset` is baked (0.0, 0.19). Over 6,341 fxmaps records
                    # every baked entry value is a tuple (7,170, of which 4,967 are width 2) or an ndarray
                    # (48) -- not one is a plain integer, so the branch was unreachable except to crash.
                    per[name] = np.asarray(value, dtype=np.float32).ravel()
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
            # See assume.QUESTIONS['fx.gridcount']. Where the placement program lays a $number
            # grid, the loop bound is that grid's cell count and NOT numberadded, which for these
            # records is an amount. The scanner is also held to a single run across the whole batch:
            # frameoffset sums the grid position and the scanner's, so re-driving the scan per
            # emission carries every cell off-canvas. ADOPTED AS THE DEFAULT -- and not a coverage
            # trade, since the corpus renders exactly the same 46 outputs either way. What changes
            # is whether they are RIGHT.
            if _grid[0] is None and assume.assumed('fx.gridcount', 'divisor') == 'divisor':
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
            # Everything below is a leaf, so no node between here and the table can move the slot
            # frame, and the patterns differ only in $number. See `emit_batch` for the second
            # condition and how it is decided.
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
            # See assume.QUESTIONS['fx.scanner']. The body advances a position and returns its own
            # in-bounds predicate, so it is run, then the subtree emits, then the predicate decides
            # whether to go round again -- matching the single-shot order exactly, so the first
            # stamp is unchanged and the loop only adds the ones that were missing.
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
            # Continue to the successor and run NOTHING. The cell is three words -- see PASSTHROUGH
            # -- and the pointer it holds is real but its role is not established, so evaluating it
            # would be writing this record's slot frame from a word whose meaning is a guess.
            walk(i + 1, number)
        elif _is_leaf(hdr):
            walk(i + 1, number)             # the leaf is the entry; the table emits
        else:
            prog = progs.get('switch')
            if prog is None:
                raise Unmodelled("markov2 with no switch program")
            if assume.assumed('fx.gatescan') == 'filter':
                # A gate whose program SPIRALS a position and tests it against a rectangle may be a
                # FILTER rather than a terminator: step the spiral a bounded number of times and emit
                # only where the predicate holds. See assume.QUESTIONS['fx.gatescan'].
                _any = False
                for _it in range(64):
                    _v = run(prog, slots, number)
                    if bool(np.asarray(_v, dtype=np.float64).ravel()[0]) == gate_polarity:
                        walk(i + 1, number)
                        _any = True
                if not _any:
                    closed[0] = True
                return
            if assume.assumed('fx.gatescan') == 'loop':
                # See assume.QUESTIONS['fx.gatescan']. Run-then-emit-then-test, the same
                # order the STEPPER scanner arm uses, so the first stamp is identical to
                # the one-shot reading and the loop only adds the ones that were missing.
                _any = False
                for _it in range(SCAN_LIMIT):
                    _v = run(prog, slots, number)
                    if bool(np.asarray(_v, dtype=np.float64).ravel()[0]) != gate_polarity:
                        break
                    walk(i + 1, number)
                    _any = True
                if not _any:
                    closed[0] = True
                return
            if bool(run(prog, slots, number)[0]) == gate_polarity:
                walk(i + 1, number)
            else:
                closed[0] = True

    walk(0, 0)
    # AN EMPTY EMISSION IS A RESULT WHEN A GATE SAID SO. Four FabricSubstance005 records
    # blocked on "emitted no patterns", and each is a single 0x89 gate whose program is three
    # instructions -- `inputref(uid) == 0` -- on the manifest's `scale`, an Integer1 whose
    # declared default is 4. The gate is false because the FILE says the branch is off.
    #
    # The polarity is not a free parameter, which is what makes this safe: inverting it takes
    # the four from 0 to 1 pattern and takes the records that currently WORK to zero (82 and
    # 161 go 45 -> 0). Narrow on purpose -- only a gate closing earns an empty result. A
    # `numberadded` of 0 looks identical here and is NOT covered, because that value has been
    # seen misread (Chainmail record 0 reads it as 257^2).
    if not out and not closed[0]:
        raise Unmodelled("emitted no patterns and no gate closed")
    return out


# patterntype -> shape name, READ OFF THE MANIFEST rather than guessed. Every .xml in the
# corpus is scanned for <guicomboboxitem value= text=>, and the shape-named items form one
# contiguous, self-consistent sequence: 2 Square, 3 Disc, 4 Paraboloid, 5 Bell, 6 Gaussian,
# 7 Thorn, 8 Pyramid, 9 Brick, 10 Gradation, 11 Waves, 12 Half bell, 13 Ridged Bell,
# 14 Crescent, 15 Capsule, 16 Cone.
#
# IT PREDICTS THE TWO RECORDS WE HAVE GROUND TRUTH FOR, which makes it more than a
# plausible table. Stadsspel__Lines record 0 is nibble 0 -- the catch-all, i.e. Square --
# and renders correctly as a hard bar. sci_fi_elements_02 record 86 is nibble 8 -> 10 ->
# Gradation, and its six patterns at radius 0.433 with size 0.866 are geometrically FORCED
# to cover the canvas under any hard footprint; only a falloff resolves it, which is what a
# gradation is. Both were established before this table existed, so the evidence is not the
# pair count -- it is that 5..16 are contiguous and the table gets both right.
#
# WHAT THE NIBBLE CAN AND CANNOT SAY. `fx_patterntype` reads `(tag >> 8) & 0xF`, returning
# None for nibble 0 and `n + 2` otherwise, so its range is exactly {3..17}. KEY 2 IS
# UNREACHABLE -- the sources declare patterntype 2 ten times so the value is real, but
# nibble 0 encodes both 1 and 2. KEY 17 IS PRODUCIBLE AND MISSING -- nibble 15 yields it in
# 4 entries corpus-wide. And a THIRD of every pattern drawn takes its shape from the
# catch-all: of 372,665 FX entries, nibble 0 is 127,349 (34.17%) against paraboloid 136,151
# and pyramid 37,107. A TEST THAT LOOKED LIKE IT RESOLVED WHICH OF TYPE 1 OR 2 AND DOES
# NOT: pooling nibble-0 tags from files whose declarations are unanimous separates on bits
# 6, 7, 28 and 31, bit 31 at 100.0% vs 1.5% -- CONFOUNDED, since the groups are different
# FILES (195 tags against 336) with only 43 and 10 declarations between them, so any bit
# reflecting authoring style separates the files rather than the types.
PATTERN_SHAPES = {
    2: 'square',        # UNREACHABLE from a tag; see above. Correct pairing, lossy nibble.
    3: 'disc', 4: 'paraboloid', 5: 'bell', 6: 'gaussian', 7: 'thorn',
    8: 'pyramid', 9: 'brick', 10: 'gradation', 11: 'waves', 12: 'halfbell',
    13: 'ridgedbell', 14: 'crescent', 15: 'capsule', 16: 'cone',
    # 17 is producible (nibble 15) and its shape is unknown -- 4 entries corpus-wide.
}

# Which shapes are DETERMINED by their name and which are MODELLED. A name fixes the
# family -- gaussian is radial and falls off, square does not -- but not always the
# exact analytic form, and pretending otherwise would repeat this file's own mistake: a
# shape that cannot be flat by construction passes a flatness check without being right.
SHAPE_MODELLED = frozenset({'bell', 'thorn', 'brick', 'waves', 'halfbell',
                            'ridgedbell', 'crescent', 'capsule'})


def profile_value(lx, ly, profile):
    """Pattern coverage at local coordinates, |lx|,|ly| <= 0.5 inside the footprint.

    The shape is no longer unknown: `patterntype` is declared in the entry tag and the manifest
    names its values (see PATTERN_SHAPES), so the footprint is selected from shipped data. What
    remains a modelling choice is the exact profile for the eight names in SHAPE_MODELLED.

    WHY A GLOBAL PROFILE COULD NEVER HAVE WORKED: 1,218 records are the Square catch-all and
    need a hard fill, while roughly 670 are Paraboloid, Gradation, Gaussian or Bell and need
    falloff, so any single answer breaks one group and a corpus-wide flatness score was
    measuring the metric rather than the format. An unknown name raises rather than defaulting.
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

    A CENSUS INSTRUMENT, NOT A FILTER. Cross-classifying every fxmaps record's branchoffset
    program against `grid_width`, every rand-scatter branchoffset is NON-grid -- 5,218 of them,
    zero grids -- so a scatter can be recognised before any span is computed. An earlier census
    reported 63 rand-scatters inside "the integer-span group", but it used a hand-written span
    classifier rather than `_cell_divisor` itself, which additionally requires every pattern to
    carry a branchoffset and the span to be an exact integer. Measured against the SHIPPED
    guard the misfire does not exist -- over 50 files it fires on 219 records, none calling
    rand and none a grid. Kept because the result is worth reproducing; a proxy for a guard is
    not the guard.
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
    makes it usable where round(sqrt(N)) was not. See
    assume.QUESTIONS['fx.branchoffset'] for the 407-of-407 census behind it.

    Factored out because the OFFSETS and the SIZES need the same number. They are the same
    grid: if the offsets step one cell at a time, a pattern meant to fill a cell is one
    cell across. Deriving it twice invited them to disagree, and an earlier pair of
    scalings that did disagree ended up multiplying.
    """
    if not patterns:
        return None
    b = [np.asarray(q.get('branchoffset'), dtype=np.float64).ravel()
         for q in patterns if q.get('branchoffset') is not None]
    if len(b) != len(patterns) or not b:
        return None
    w = max(x.size for x in b)
    a = np.array([np.pad(x, (0, w - x.size)) for x in b])
    # AN INTEGER SPAN IS NOT ENOUGH -- THE OFFSETS THEMSELVES MUST BE INTEGERS. An earlier
    # classification found the span test scaling 63 records whose branchoffset program calls
    # `rand`: a scatter has no cells, so dividing it by a cell count is the same category of
    # error round(sqrt(N)) made. A jittered scatter can still span an integer, because the
    # extremes are the generator's bounds; what it cannot do is put every emission on a
    # lattice point. Requiring all offsets to be integers, and the distinct count on an axis
    # to be exactly span + 1, separates them completely -- over 80 files, 284 of 284
    # integer-span records with no rand pass both tests against 0 of 65 with rand.
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


def _combine(dst, src):
    """Fold one pattern's contribution into the canvas -- see QUESTIONS['fx.combine']."""
    mode = assume.assumed('fx.combine', 'max')
    if mode == 'add':
        return dst + src
    if mode == 'over':
        a = np.clip(np.abs(src), 0.0, 1.0)
        return dst * (1.0 - a) + src
    return np.maximum(dst, src)


def splat(rec, patterns, W=None, H=None, profile=None, images=None):
    """Draw the emitted patterns. `images` maps EDGE SLOT -> (H, W, C) array.

    When `images` is supplied and a pattern carries `imageindex`, the pattern IS that image
    sampled over its own footprint rather than a generated profile.

    HOW OFTEN IT APPLIES, and what it must not be over-read as. Over 80 files, 176 fxmaps
    records carry `imageindex`: 133 index 0 on every pattern and have SIX edges, 27 index 1
    somewhere and have THREE, and the only values anywhere are 0.0 (x54,518) and 1.0 (x27). If
    it were a direct index into the edge list, six-edge records would be expected to use more
    than index 0. They do not, so it indexes a narrower subset of edges that are pattern
    images, and that mapping is NOT established -- so `image_for` takes the index literally and
    returns None when the caller did not supply it, rather than falling back to the first
    available image and sampling the wrong input on the 27.
    """
    # WHAT IS WRONG WITH THIS FUNCTION IS COVERAGE, NOT VALUE, and that is measured. On
    # Chesterfield's metallic and height cones -- each bottoming out at an fxmaps sampling an
    # image input -- the mean WHERE LIT survives to three decimals (rec34 0.1438 -> 0.1427,
    # rec65 0.4991 -> 0.4901) while the LIT FRACTION collapses 16x and 5.7x. So the sampling,
    # the opacity and the profile amplitude all work, and the whole-image attenuation is
    # exactly that coverage ratio: the stamps do not tile. No arbitration arm reaches it --
    # both records are BYTE-IDENTICAL under fx.patternsize and fx.branchoffset, because
    # `_cell_divisor` declines them.
    #
    # THE DEFICIT IS THE EMISSION COUNT, NOT THE SIZE OR THE INDEX. Both emit ONE pattern, at
    # patternsize 0.2500 and 0.4146, both imageindex 8 -- correct, since slot 8 is the only one
    # of fourteen carrying content -- and the coverage follows arithmetically (0.403 x 0.0625 =
    # 0.0252 against 0.025 measured), the deficit being exactly 1/size^2. The walk is NOT
    # skipping a subdivision: both are ADDNODE -> STEPPER -> LEAF with a single entry whose
    # `numberadded` evaluates to exactly 1.0.
    #
    # THE REFERENCE SETTLES THE SHAPE AND REFUTES BOTH READINGS THAT WERE ON THE TABLE.
    # Chesterfield's exported metallic is a regular grid of dots at exactly 256px on a 2048px
    # map -- 8 across. NOT a bigger stamp: rec29, the image stamped, is a tileable unit cell
    # with blobs at its four CORNERS, so one stamp of side 1.0 gives a 2x2 arrangement. NOT
    # this record's numberadded: 8x8 is 64, and that program reads as ((n-1) mod 2 + n)^2,
    # which yields only ODD squares. The engine repeats one cell at 1/8 spacing while the tile
    # loop below steps by WHOLE CANVASES. ONE THREAD LEFT: this chain reads slots 14, 16, 17
    # AND 18, and `seed_slots` supplies all but 18.
    W = W or rec.width
    H = H or rec.height
    # The footprint is the largest open question here and the one the reference renders
    # could settle, so it is arbitrable. An explicit scope still wins; with none, the shape
    # comes from the entry's own patterntype -- data, not an assumption.
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

    # `val` reads one emitted parameter as a flat float32 array. Defined once, outside the
    # loop: a closure over `p` was being rebuilt for every pattern, a code object and a
    # cell per emission for no gain.
    def val(pat, name, default):
        v = pat.get(name)
        return np.asarray(default, dtype=np.float32) if v is None \
            else np.asarray(v, dtype=np.float32).ravel()

    # BRANCHOFFSET MAY BE IN CELL UNITS -- see assume.QUESTIONS['fx.branchoffset']. Over 966
    # square-grid records its span / (G - 1) has median exactly 1.0000, so it spans G - 1 cells
    # rather than the canvas, and Chainmail record 0 renders as a single cell under the canvas
    # reading and as a full 257 x 257 lattice under this one. Reproduced independently on 224
    # square-grid records from a separate walk, median 1.0000, p25 and p75 both 1.0000.
    #
    # OPT-IN FOR A MEASURED REASON. An earlier version applied the scaling unconditionally,
    # which is wrong: `PavingStonesSubstance003` records 38/40/42/45 have G=4 and span 0.750,
    # so span/(G-1) = 0.250 and CANVAS is right for them, and it scored worse on the only
    # ground truth available (Chesterfield `normal` MAE 0.1039 -> 0.1055). Two such scalings
    # briefly coexisted and MULTIPLIED. PATTERNSIZE MAY BE IN CELLS TOO, kept a separate key
    # because the two are coupled and scoring them apart is what demonstrates it; an 'oversize'
    # candidate is retired, having thresholded on a SYMPTOM and now rendering byte-identically
    # to 'cell' on all 175 Bricks records.
    size_scale = None
    if assume.assumed('fx.patternsize') == 'cell' and patterns:
        size_scale = _cell_divisor(patterns)
        if size_scale is not None:
            assume.note(getattr(rec, 'index', -1))

    # THE GUARD IS THE SPAN, NOT THE COUNT. This used to divide by round(sqrt(N)) on a
    # perfect-square emission count, which is not merely over-broad -- it selects AGAINST its
    # own target: of the Bricks records it scaled, 88 of 88 were rand scatters or had no
    # $number decomposition at all and NOT ONE was a grid, while that file's five real grids
    # emit 32 and 8 patterns, neither a perfect square.
    #
    # A cell-unit offset walks WHOLE CELLS, so its span is an integer number of them -- a
    # property of the emissions alone. Over 110 files, of 3,390 records with a branchoffset
    # span, 407 have an exact integer span and in 407 of 407 (span + 1) divides the count,
    # while sqrt(N) would have missed 41; the other 2,983 are fractional, and those are what
    # the old guard was scaling. The divisor is per axis.
    frame_scale = None
    if assume.assumed('fx.frameoffset') == 'cell' and patterns:
        frame_scale = _cell_divisor(patterns)
        if frame_scale is not None:
            assume.note(getattr(rec, 'index', -1))

    cell_scale = None
    if assume.assumed('fx.branchoffset') == 'cell' and patterns:
        cell_scale = _cell_divisor(patterns)
        if cell_scale is not None:
            assume.note(getattr(rec, 'index', -1))

    # AN ENTRY THAT STATES NEITHER SHAPE NOR EXTENT: see assume.QUESTIONS['fx.sizeless'].
    # The default stays 'fill' -- a full-cell rect, today's behaviour -- because that is
    # what the code has always done, not because it is established.
    _sizeless = assume.assumed('fx.sizeless', 'fill')

    # THE ROOT ENTRY -- see assume.QUESTIONS['fx.rootentry']. A typeless, sizeless pattern
    # at branchoffset exactly (0, 0) is the whole-canvas cell of the FX-Map's own tree, not
    # a draw. Tested by its own key rather than by `fx.sizeless`, which the references
    # decide the other way: this is one pattern per record with an exact signature.
    _rootskip = assume.assumed('fx.rootentry') == 'skip'
    # See assume.QUESTIONS['fx.markers'] -- the 0x08 entry family states a position and
    # nothing else. `_tag` travels with each pattern from `emit`.
    _markerskip = assume.assumed('fx.markers') == 'skip'

    for p in patterns:
        if _markerskip and (p.get('_tag') is not None) and (int(p['_tag']) & 0xFF) == 0x08:
            continue
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
        if frame_scale is not None:
            off = off * frame_scale[:off.size]
        size = val(p, 'patternsize', _ONE2)
        if size_scale is not None:
            size = size * size_scale[:size.size]
        rot = float(val(p, 'patternrotation', _ZERO1)[0])
        # MOST PATTERNS DO NOT CARRY AN OPACITY AT ALL, which is what makes this default
        # load-bearing rather than a corner. Over 195,933 emitted patterns in 20 files, 163,676
        # (83.5%) have none and take 1.0 here; 29,802 are in (0, 1], 1,195 negative, 975 exactly
        # zero, 285 above 1. So a record's appearance is decided by the DEFAULTS for five patterns
        # in six, and a full-cell size at full opacity is what paints an FX-Map solid white -- the
        # `fx.sizeless` and `fx.patternsize` questions, not this one.
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
            # ...and neither is a pattern 1e-33 cells across. The upper bound had no lower twin, so a
            # size small enough to make dx / sx overflow float32 was admitted and then neutralised
            # downstream: the ratio came out inf, inf failed the |lx| <= 0.5 test, and the emission
            # drew nothing -- correct output by accident, announced as a RuntimeWarning. A guard that
            # admits a value and leaves a later test to cancel it is not a guard.
            #
            # The threshold sits in a gap the corpus leaves. RE-MEASURED after the FX walks were
            # drained onto the mask-walk: over 40 files, of 77,358 finite patternsize components 939
            # are <= 0 (the sx > 0 test takes those) and 963 are <= 1e-30, with NOTHING between 1e-30
            # and 1e-06 and exactly one value in (1e-06, 1e-03]. The old enumeration counted six at
            # 6.259e-33; the population is now 963 and the smallest positive is 3.6e-42, so the guard
            # does more work than it was documented as doing.
            continue
        if col.size < nchan:
            col = np.repeat(col[:1], nchan)
        # See assume.QUESTIONS['fx.negopacity'] -- the clip makes a negative opacity inert.
        _neg = assume.assumed('fx.negopacity', 'clip')
        if _neg == 'signed':
            col = np.clip(col[:nchan], -1.0, 1.0)
        elif _neg == 'abs':
            col = np.clip(np.abs(col[:nchan]), 0.0, 1.0)
        else:
            col = np.clip(col[:nchan], 0.0, 1.0)

        th = 2.0 * math.pi * rot
        ct, st = math.cos(th), math.sin(th)
        reach = int(min(3, math.ceil(max(sx, sy))))
        prof = profile_for(p)          # depends only on `p`; was recomputed 49 times
        # THE FOOTPRINT, NOT THE CANVAS. profile_value multiplies every profile by
        # `inside = (|lx| <= 0.5) & (|ly| <= 0.5)`, so a point outside the pattern's own box
        # can never write to the canvas and evaluating all H*W points per emission was pure
        # waste. At scale it was the whole cost: Marble record 450 at 64x64 ran 1,930,794
        # profile_value calls over 7,908,463,104 points and had not finished after 100 s.
        # The footprint is a rectangle of half-extents sx/2, sy/2 rotated by th:
        hx = 0.5 * (sx * abs(ct) + sy * abs(st))
        hy = 0.5 * (sx * abs(st) + sy * abs(ct))
        # ONLY THE TILES THAT CAN REACH THE CANVAS. The canvas spans -0.5..0.5, so a copy at
        # offset t contributes only while `cx + t` is within `hx` of that span; for a pattern
        # a single pixel across that was eight of every nine tiles. The bounds are the same
        # inequality the box test applies, solved for t, so no tile that used to draw
        # anything is skipped.
        txlo = max(-reach, math.ceil(-0.5 - cx - hx))
        txhi = min(reach, math.floor(0.5 - cx + hx))
        tylo = max(-reach, math.ceil(-0.5 - cy - hy))
        tyhi = min(reach, math.floor(0.5 - cy + hy))
        for ty in range(tylo, tyhi + 1):
            for tx in range(txlo, txhi + 1):
                ux, uy = cx + tx, cy + ty
                # px = (col + 0.5)/W - 0.5, so col = (px + 0.5)*W - 0.5. Floor/ceil the ends rather
                # than round them: a box that clips a pixel must still include it. `math`, not
                # `numpy`: these are four scalars per tile, and a numpy call on a Python float costs
                # about half a microsecond of dispatch to do one flop.
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
                # A HARD FILL NEEDS NO COVERAGE ARRAY. For 'rect'/'square', profile_value returns
                # exactly inside.astype(float32), so `cov[hit]` is all 1.0 and the multiply is a
                # broadcast. Building the array is the dominant cost of the render path: over 12
                # files splat evaluates 91,461,962 points, and the typeless entries that default to
                # a hard fill are exactly the ones whose footprint covers half the canvas. Same
                # values, bit for bit.
                if prof in ('rect', 'square'):
                    hit = (np.abs(lx) <= 0.5) & (np.abs(ly) <= 0.5)
                    cov = None
                else:
                    cov = profile_value(lx, ly, prof)
                    hit = cov > 0
                if not hit.any():
                    continue
                tile = cview[r0:r1 + 1, c0:c1 + 1]
                if src is None:
                    if cov is None and hit.all():
                        # The footprint covers the whole slice, so there is no mask to apply -- boolean
                        # indexing an all-true mask copies the block out and back for nothing.
                        tile[...] = _combine(tile, col)
                    else:
                        tile[hit] = _combine(tile[hit],
                                             col if cov is None else col * cov[hit, None])
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
                tile[hit] = _combine(tile[hit],
                                     sampled[:, :nchan] * col if cov is None else
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
