"""An FX-Map's chain nodes read as a TREE, behind `assume.QUESTIONS['fx.chain']`.

WHAT THE LIST WALK MISSES. `fxrender.chain` follows one successor per node -- the word
`node_shape` names -- and every other word of a node is read as nothing. Three of those
words are children the file fills:

    0x89 / 0x99   [hdr] [bit-4 word]? [program] [FALSE child] [TRUE child]
                  a two-way Switch. The program returns a bool (0x89: 11,197 of 11,197
                  corpus programs; 0x99: 238 of 238). The list walk reads the FALSE child
                  as "0" and closes the branch, which is right exactly when it IS 0:
                  26,888 of 27,093 corpus 0x89 nodes, 150 of 238 0x99.
    0x1CB         [hdr] [program] [AFTER child] [LOOP child]
                  an Iterate whose second output is connected: the loop child runs
                  `numberadded` times, the after child once when the loop is done. The
                  list walk reads the after child as "0"; it is 0 on 1,800 of 1,865.
    0x19B         [hdr] [bit-4 word] [program] [LOOP child]
                  an Iterate (0x18B under bit 4). The list walk dispatches it by its low
                  byte as `STEPPER2` -- run once, continue -- but its program returns an
                  int count, 245 of 245 corpus nodes, and the count is what the nodes
                  below it loop over.

THE SPECIMEN, Bricks record 10081, is a random-size stone tiling: a 0x1CB whose LOOP
child is a statistics pass (its leaves draw at luminosity 0 and accumulate the largest
cell size into slots 27/28) and whose AFTER child is the draw pass (leaves at luminosity
1, sized to the cell minus a gap of 0.19^2 x that maximum); inside each pass a 0x89
sends a cell wider than tall down its FALSE child (split into `ceil(w/h)` columns by a
0x19B loop) and a taller one down its TRUE child (split into rows). The list walk takes
the statistics pass only, runs its 0x19B once, and draws eight black patterns. That
record is the mask of graph 001's flood fill, so everything in the graph's layout hangs
on it. See FORMAT-NOTES.md, "Record 10253 is not the fault".

WHICH WORD IS WHICH is read off the same record: the wide/tall Switch program writes the
column count into slot 45 when it returns False and the row count into slot 46 when it
returns True, and the node its spare word addresses is the 0x19B whose program returns
slot 45. The statistics pass must precede the draw pass for the gap to be non-zero, and
the loop child is the successor the list walk already follows -- so the loop runs first
and the spare word's child after. Nothing here is from a source; a permitted `.sbs`
declaring a two-output Iterate or a Switch with both outputs wired would corroborate the
reading and none of the 100 permitted sources does.

SCOPE. The arm applies only to a record whose chain holds at least one of those three
readings AND consists entirely of families this module models (`needed`); every other
record takes the list walk unchanged, so under `fx.chain=tree` no record that rendered
before refuses. A leaf reached by the walk is an entry cell read through
`sbsasm.fx_entry_walk`; a leaf carrying Quadrant pointers (bits 16/17) is refused rather
than drawn flat, and so is a 0x1DB (two children under a shape `node_shape` states is
wrong for it) and the 0x0B / 0x1B leaf and branch families.
"""

import struct

import numpy as np

import assume
import fxrender
import sbsasm
from sbsasm import fx_patterntype

from ops import Unsupported

#: The pattern budget, the same scalar `render2.fx` refuses at.
MAX_PATTERNS = 300000
MAX_DEPTH = 64
SKEW = 52


def _word(data, off, i):
    return struct.unpack_from("<I", data, off + 4 * i)[0]


def family(hdr):
    """'switch' | 'iterate' | None for a chain-node header this module reads."""
    if hdr > 0xFFFF or not (hdr & 0x80):
        return None
    if hdr in (0x89, 0x99):
        return "switch"
    if hdr in (0x18B, 0x19B, 0x1AB, 0x1CB):
        return "iterate"
    return None


def is_entry(asm, hdr):
    """Is this word an entry-cell tag rather than a chain node?"""
    return hdr > 0xFFFF and fx_patterntype(hdr) is not None


class Node(object):
    __slots__ = ("off", "hdr", "kind", "progs", "loop", "spare")

    def __init__(self, off, hdr, kind, progs, loop, spare):
        self.off = off
        self.hdr = hdr
        self.kind = kind
        self.progs = progs
        self.loop = loop
        self.spare = spare


def read_node(asm, off):
    """The chain node at `off`, or None when it is not a modelled family."""
    d = asm.data
    if not (asm.body_lo <= off < asm.body_hi - 16):
        return None
    hdr = _word(d, off, 0)
    kind = family(hdr)
    if kind is None:
        return None
    shape = sbsasm.node_shape(hdr)
    if shape is None:
        return None
    succ, progs = shape
    ptrs = []
    for pb in progs:
        p = _word(d, off, pb // 4) + SKEW
        if not (asm.body_lo <= p < asm.body_hi) or not asm.valid_program(p):
            return None
        ptrs.append(p)
    loop = _word(d, off, succ // 4)
    spare = _word(d, off, succ // 4 - 1)
    if kind == "iterate" and not (hdr & 0x40):
        spare = 0
    return Node(off, hdr, kind, ptrs, loop, spare)


def _entry_cell(asm, off):
    """(tag, {name: (kind, value)}) for the entry cell at `off`, or None."""
    d = asm.data
    if not (asm.body_lo <= off < asm.body_hi - 8):
        return None
    tag = _word(d, off, 0)
    if not is_entry(asm, tag):
        return None
    params = {}
    for _bit, sl, name, kind, width in sbsasm.fx_entry_walk(tag):
        if kind == "structural" or name is None:
            continue
        if off + 4 * (sl + width) > asm.body_hi:
            return None
        if kind == "program":
            p = _word(d, off, sl) + SKEW
            if not (asm.body_lo <= p < asm.body_hi) or not asm.valid_program(p):
                return None
            params[name] = ("program", p)
        else:
            params[name] = (
                "baked",
                np.asarray(
                    struct.unpack_from("<%df" % width, d, off + 4 * sl), np.float32
                ),
            )
    return tag, params


def _has_quadrant_pointers(tag):
    return bool((tag >> 16) & 3)


def survey(rec):
    """({offset: Node}, {offset: (tag, params)}, refusal or None) over the whole tree."""
    asm = rec.asm
    root = rec.fx_root
    if root is None:
        return {}, {}, "no chain root"
    nodes, leaves = {}, {}
    todo = [root]
    while todo:
        off = todo.pop()
        if off in nodes or off in leaves:
            continue
        n = read_node(asm, off)
        if n is not None:
            nodes[off] = n
            for w in (n.loop, n.spare):
                if w:
                    todo.append(w + SKEW)
            continue
        cell = _entry_cell(asm, off)
        if cell is None:
            return nodes, leaves, "word at %d is neither a modelled node nor an entry" % off
        if _has_quadrant_pointers(cell[0]):
            return nodes, leaves, "leaf %#x at %d carries Quadrant pointers" % (cell[0], off)
        leaves[off] = cell
    return nodes, leaves, None


def programs(rec):
    """Every program the tree names -- node programs and leaf parameter programs."""
    nodes, leaves, _why = survey(rec)
    out = set()
    for n in nodes.values():
        out.update(n.progs)
    for _tag, params in leaves.values():
        for _name, (kind, value) in params.items():
            if kind == "program":
                out.add(value)
    return out


def seed(rec, run):
    """`fxrender.seed_slots` with the TREE's programs excluded from the seeding.

    `Record.programs` scans the record's words, so the draw pass's leaf programs and the
    other branch's node programs are in it; `seed_slots` excludes only what the list walk
    names and would run the rest once at `$number` 0 as if they were the record's own
    prologue -- writing the very slots the walk is about to compute.
    """
    slots = {}
    fx = programs(rec)
    for p in rec.programs or ():
        if p in fx:
            continue
        try:
            run(p, slots, 0)
        except Exception:
            pass
    if any(n.hdr == 0x99 for n in survey(rec)[0].values()):
        for slot, value in fxrender.SCAN_STATE_DEFAULTS.items():
            slots.setdefault(slot, value)
    return slots


def active(rec):
    """Is the tree arm in force for this record?"""
    return assume.assumed("fx.chain", "list") == "tree" and needed(rec)


def needed(rec):
    """Does this record's chain hold a reading the list walk does not, and can the tree
    walk read all of it? False sends the record down the list walk unchanged."""
    nodes, _leaves, why = survey(rec)
    if why is not None or not nodes:
        return False
    for n in nodes.values():
        if n.kind == "switch" and n.spare:
            return True
        if n.hdr == 0x1CB and n.spare:
            return True
        if n.hdr == 0x19B:
            return True
    return False


def emissions(rec, run, slots):
    """[{parameter: value}] for every pattern the tree walk emits, in emission order."""
    asm = rec.asm
    nodes, leaves, why = survey(rec)
    if why is not None:
        raise Unsupported("fxmaps: fx.chain=tree: %s" % why)
    out = []

    def emit(off, number):
        tag, params = leaves[off]
        got = {"patterntype": fx_patterntype(tag), "_tag": tag}
        for name, (kind, value) in fxrender.in_eval_order(params):
            if kind == "baked":
                got[name] = value
            else:
                got[name] = run(value, slots, number)
        out.append(got)
        if len(out) > MAX_PATTERNS:
            raise Unsupported("fxmaps: more than %d patterns" % MAX_PATTERNS)

    def walk(off, number, depth):
        if depth > MAX_DEPTH:
            raise Unsupported("fxmaps: chain tree deeper than %d" % MAX_DEPTH)
        if off in leaves:
            emit(off, number)
            return
        n = nodes[off]
        if n.kind == "switch":
            ok = bool(np.asarray(run(n.progs[0], slots, number)).ravel()[0])
            child = n.loop if ok else n.spare
            if child:
                walk(child + SKEW, number, depth + 1)
            return
        # iterate: bit 5 puts `randomseed` first, `numberadded` last
        if len(n.progs) > 1:
            run(n.progs[0], slots, number)
        raw = int(round(float(np.asarray(run(n.progs[-1], slots, number)).ravel()[0])))
        if not 0 <= raw <= MAX_PATTERNS:
            raise Unsupported("fxmaps: numberadded = %d" % raw)
        if n.loop:
            for k in range(raw):
                walk(n.loop + SKEW, k, depth + 1)
        if n.spare:
            walk(n.spare + SKEW, number, depth + 1)

    walk(rec.fx_root, 0, 0)
    if not out:
        raise Unsupported("fxmaps: fx.chain=tree emitted no patterns")
    return out
