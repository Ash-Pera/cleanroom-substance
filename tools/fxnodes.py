#!/usr/bin/env python3
"""Where an FX-Map node's programs SIT, from the header mask -- and where the mask stops.

THE FIRST VERSION OF THIS MODULE READ A ROLE OUT OF THE MASK, AND THAT WAS A FIT. It said
bit 7 with bit 4 clear is a `count` when the low nibble is B and a `gate` when it is 9, and
called that a derivation because the bits involved are the ones the walk uses. Fitting on
bits is not a walk. A walk states WHERE a field goes -- ascending bit order, each set bit
advancing the cursor by its width -- and says nothing about what the field means; reading
the same bits as a role is a classification of the header population, and it has to meet
the bar a classification meets.

It does not meet it. `separability.py`'s question, asked of the corpus's own chain headers:

    census role   headers                      cells
    count         0x18B, 0x1AB, 0x1CB          33,209 / 27 / 1,858
    gate          0x89                         27,600
    state         0x99, 0x19B                  194 / 136

    bits that separate count from gate     1 and 8      <- co-extensive, both perfect
    bits that separate count from state    4
    bits that separate gate  from state    4

So the "low nibble decides count against gate" reading is bit 1 OR bit 8 with nothing
between them -- one distinct gate header against three count headers, and two candidate
discriminators that no specimen separates. That is the confound `separability.py` exists to
catch, and `node_shape` refuses the identical inference one line up from here ("bit 1 of the
nibble happens to split these three correctly; that is a three-point fit on a two-valued
output and is not written down as a rule"). The fitted rule is withdrawn, not demoted.

WHAT THE WALK DOES STATE, and it is placement rather than meaning:

  * WHERE the programs are, and how many. `node_shape` walks the mask: the base program at
    word 1 (word 2 when bit 4 has spent one), bit 5's program one word on, the successor at
    `base + popcount(header & 0xF0)`. This module uses those positions and adds no bit rule
    of its own.

  * WHICH program is which, GIVEN their names. A walk emits fields in ascending bit order,
    so bit 5's program precedes bit 7's base program. That is the pairing `FX_NODE_PARAMS`
    states for `0x1AB` -- word 1 `randomseed`, word 2 `numberadded` -- and the corroboration
    is ONE HEADER and the four `ie_curve` source nodes behind that row, said as one header
    rather than as the 27 cells it covers.

  * THAT A BIT-7-CLEAR NODE HAS NO PROGRAM OF ITS OWN. Bit 7 is what declares the base
    program+successor structure, so a header without it declares no program, and the leaf,
    the pointer cell and the `0x??1B` branch pass straight through. This is the one ROLE
    statement here that is the mask's own, and it is not a fit: it is the absence of a
    field, corroborated by `FX_NODES2`' correction that the words a `0x??1B` appears to own
    past its three are the NEIGHBOUR's program and successor (355 of 355).

WHAT IT TAKES FROM THE CENSUS, having no way to derive it: what a bit-7-set node's program
DOES. `count`, `gate` and `state` come from `fxrender`'s header census, which is where the
evidence for them is -- source containment for `addnode` and `markov2`, the value
distribution separating `0x1CB` from `0x1AB`, the slot-traffic reading of `0x99`. A header
the census does not carry is REFUSED here, exactly as it is there. `0x1DB` was `state` under
the fitted rule and is refused again; nothing establishes what its program does, and 23
records draw the same either way only because they also carry an `0x1A3`.

SO WHAT IS THE SECOND IMPLEMENTATION FOR. It places what the first looks up. The table arm
reads `FX_NODE_PARAMS[header]`, a per-header map from BYTE OFFSET to name, and the retired
`FX_NODES` before it; the walk arm computes those offsets from the mask and pairs the names
onto them by field order. Two statements of one address, which is the discipline the rest of
this decode runs on. Over all 437 corpus files (`python3 tools/fxnodes.py`):

    fxmaps records yielding a chain                       27,184
      records whose node list differs between the arms         0
      records either arm walks and the other refuses           0
    node programs the table model names                   62,721
      the mask places identically                         62,721   100.00%
    distinct headers behind those figures                      8
      of which any name is placed on                           4

READ THE LAST TWO ROWS BEFORE THE OTHERS. 62,721 agreements are 62,721 OCCURRENCES of four
headers, and `0x18B` and `0x89` are 97% of them; the independent content is four addresses,
each confirmed across every cell that carries it. Reporting the cell count alone is how a
four-point agreement reads as overwhelming, which is the same mistake in presentation that
the withdrawn rule was in substance.

MEASURED THROUGH THE RENDERERS TOO (`python3 tools/fxnodes.py --emissions 40`): 3,086
records emit the identical pattern list under both arms, 0 differ, 102 are refused by both,
and 2 are nondeterministic -- they call `rand` in their own parameter programs and differ
under the SAME arm run twice, which is why the comparison renders every record three times.
`render2` renders the reference specimen (`Rokviz japanese fabric 8`) to 70 outputs under
both arms with a maximum absolute difference of 0.0.

THE ONE PLACE THE ARMS WOULD DRAW DIFFERENTLY, and nothing on this corpus exercises it: the
`0x??1B` family. Both renderers test `(hdr & 0xFF) in (STEPPER2, BRANCH)` before their
pass-through arm, and `BRANCH` and `PASSTHROUGH` are the same constant, so the census runs
such a node's program and its own pass-through arm is unreachable. The mask says it has no
program, so the walk arm runs nothing. A node carrying no program never enters a chain --
`fx_node_params` drops it -- so 0 of 27,184 records dispatch a bit-7-clear header at all.

WHAT THE FIT WOULD NEED, stated so the next attempt starts here rather than at the
beginning, and it is two things and not one:

  * SEPARABILITY. A chain header with bit 7 set, bit 4 clear and exactly one of bits 1 and 8
    -- a `count` at nibble 9, or a `gate` at nibble B -- would say which of the two the
    corpus has been reading. None exists here, which is why the rule could be written down
    for a day with nothing contradicting it.

  * AND THEN EVIDENCE THAT THE BIT MEANS THE ROLE, which separability does not supply. A bit
    that co-varies with a role over four headers is still a classification of four headers;
    what would make it a reading is a permitted source declaring an `addnode` or a `markov2`
    against a compiled header the current four do not cover, the way `FX_NODE_PARAMS`' own
    rows were obtained. Only eight permitted sources carry FX-Map node data at all.

Neither is a walk, and that is the point: the walk places fields. The engine's choice of
what to do with a field is not a fact about a presence mask, and a second implementation
that pretends otherwise is not a second reading of the file -- it is the same census with
its keys rewritten as arithmetic.
"""

import struct
import sys

import assume
from sbsasm import node_shape, leaf_successor, pointer_cell_successor


#: The roles a chain node can have. A renderer dispatches on these; both models return them.
#:
#:   count   loop the rest of the chain `numberadded` times, $number = 0..n-1
#:   gate    run `switch` and continue only where it holds
#:   state   run the program for its slot writes, then continue -- one successor
#:   branch  continue, running nothing (the 0x??1B cell: SPEC 8, `FX_NODES2`)
#:   leaf    continue; the leaf IS the table entry seen from the node side
#:   link    a pointer cell -- carries no program and draws nothing
#:
#: The first three are the census's to say and are taken from it. The last three are the
#: mask's own answer, and all three say the same thing -- no program of this node's own.
ROLES = ("count", "gate", "state", "branch", "leaf", "link")

#: The node's own parameter, by role -- the census's naming, keyed by what the census says
#: the node does rather than by the header word. `state`'s program is unnamed because no
#: permitted source contains a `0x99` or a `0x9B`, which is why `fx_node_params` leaves it
#: blank too.
OWN_PARAM = {"count": "numberadded", "gate": "switch", "state": None}


def mask_passthrough(header):
    """The role of a header that declares no program of its own, or None.

    Bit 7 declares the base program+successor structure. Without it a node has no program,
    and the three families that shape occurs in are exactly the ones `sbsasm`'s own mask
    predicates already claim -- so this asks them rather than restating their conditions.
    """
    if header & 0x80:
        return None
    if pointer_cell_successor(header) is not None:
        return "link"
    if leaf_successor(header) is not None:
        return "leaf"
    if (header & 0xF) == 0xB and header & 0x10:
        return "branch"
    return None


def walk_role(header):
    """The node's role under the walk model, or None where nothing establishes one.

    Derived where the mask states it -- a bit-7-clear header declares no program, so it
    passes through -- and taken from the census where the mask does not, which is every
    header that HAS a program. See the module docstring: the rule that read a role out of
    bit 4 and the low nibble was a fit on six headers with two co-extensive discriminators,
    and is withdrawn.
    """
    return mask_passthrough(header) or (census_role(header) if header & 0x80 else None)


def mask_programs(header):
    """{byte offset: parameter name or None} for the node's own programs.

    OFFSETS FROM THE MASK, NAMES FROM THE ROLE. `node_shape` places the programs; the role
    says what the node's own parameter is called; and where the mask declares two programs,
    ascending bit order puts bit 5's first. That order is the walk's, and `FX_NODE_PARAMS`
    corroborates it on the one header that has two -- `0x1AB`, word 1 holding every literal
    the source's `randomseed` graph declares and word 2 all seven of `numberadded`'s, 4 of 4
    over the `ie_curve` nodes that declare both, with the reverse failing on all four.

    A header whose ROLE is unknown gets positions and no names. Bit 5 is `randomseed` on the
    strength of one header's containment plus the pair design it shares with the entry tags;
    carrying that onto a header nobody can place at all would be the withdrawn fit again,
    one bit smaller.
    """
    shape = node_shape(header)
    if shape is None:
        return {}
    _succ, progs = shape
    role = walk_role(header)
    if role not in OWN_PARAM:
        return {p: None for p in progs}
    own = OWN_PARAM[role]
    if len(progs) == 2:
        return {progs[0]: "randomseed", progs[1]: own}
    return {progs[0]: own}


def census_role(header):
    """The role, from the whole-word constants both renderers dispatch on today.

    The classification `fxrender.emissions` and `render2.fx._walk` used to perform inline,
    lifted out so the dispatch can be written once and so the two models can be compared.
    It is deliberately bug-compatible: `BRANCH` and `PASSTHROUGH` are both `0x1B`, and both
    renderers test `(hdr & 0xFF) in (STEPPER2, BRANCH)` BEFORE their pass-through arm, so a
    `0x??1B` runs its program and the pass-through arm is unreachable. Reported as `state`
    for that reason -- this states what the code does, not what the constants' comments say
    it does.

    Imported lazily: `fxrender` imports this module, and the constants live there.
    """
    import fxrender

    if header in fxrender.ADDNODE:
        return "count"
    if header == fxrender.GATE:
        return "gate"
    if header == fxrender.STEPPER or (header & 0xFF) in (
        fxrender.STEPPER2,
        fxrender.BRANCH,
    ):
        return "state"
    if (header & 0xFF) == fxrender.PASSTHROUGH:
        return "branch"
    if fxrender._is_leaf(header):
        return "leaf"
    return None


def model():
    """Which node model is in force: 'table' (the default) or 'walk'."""
    return assume.assumed("fx.nodemodel", "table")


def role(header):
    """The node's role under the model in force, or None if that model declines it."""
    return walk_role(header) if model() == "walk" else census_role(header)


def known(header):
    """Does the model in force have a reading for this header?"""
    return role(header) is not None


def _name_at(rec, off, header, prog):
    """Which of the mask's program slots addresses `prog`, as a name -- or None.

    `fx_walk` yields a program's ADDRESS and not the slot that named it, so the slot is
    recovered by reading each candidate back, exactly as `fx_node_params` does. Subtracting
    `off` names nothing, since a program does not sit inside the node.
    """
    d, hi = rec.asm.data, rec.asm.body_hi
    for boff, name in mask_programs(header).items():
        if off + boff + 4 > hi:
            continue
        if struct.unpack_from("<I", d, off + boff)[0] + 52 == prog:
            return name
    return None


def chain(rec):
    """[(offset, header, {name: program})] in chain order -- `fxrender.chain`'s walk arm.

    Same shape and same order as the table arm, including its two conventions: a node
    carrying no program does not appear at all (that is `fx_node_params`' filter, and it is
    why no leaf or pointer cell is ever dispatched), and an unnamed program lands under the
    key None. What changes is that the name reaches the program through a byte offset the
    MASK placed, where the table arm reads the offset out of `FX_NODE_PARAMS`.
    """
    nodes, order = {}, []
    for kind, off, hdr, prog in rec.fx_walk():
        if kind != "node" or not prog:
            continue
        if off not in nodes:
            nodes[off] = (hdr, {})
            order.append(off)
        nodes[off][1][_name_at(rec, off, hdr, prog)] = prog
    return [(off, nodes[off][0], nodes[off][1]) for off in order]


# ---------------------------------------------------------------------------
# The standing comparison. Two implementations of one thing drift; this is what
# makes them disagree out loud rather than quietly.
# ---------------------------------------------------------------------------


def separability(paths):
    """Which bits separate one census role's headers from another's, over a corpus.

    THE CHECK THAT WITHDREW THIS MODULE'S FIRST READING, kept runnable because the reading
    was plausible enough to write down: `count` and `gate` are separated by bit 1 and bit 8
    equally, so "the low nibble decides" is one of two readings the corpus cannot tell
    apart. A specimen that broke the tie would show up here as a single bit.
    """
    import collections
    import fxrender
    import sbsasm

    seen = collections.Counter()
    for p in paths:
        try:
            asm = sbsasm.Assembly(p)
        except Exception:
            continue
        for rec in asm.records:
            if rec.filter_id != 4:
                continue
            try:
                for _o, hdr, _q in fxrender.chain(rec):
                    seen[hdr] += 1
            except Exception:
                continue
    groups = collections.defaultdict(list)
    for hdr in seen:
        groups[census_role(hdr)].append(hdr)
    out = {}
    names = [r for r in ("count", "gate", "state") if groups.get(r)]
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            bits = [
                k
                for k in range(32)
                if len({(h >> k) & 1 for h in groups[a]}) == 1
                and len({(h >> k) & 1 for h in groups[b]}) == 1
                and ((groups[a][0] >> k) & 1) != ((groups[b][0] >> k) & 1)
            ]
            out["%s|%s" % (a, b)] = bits
    return {
        "headers": {r: sorted("%#x" % h for h in hs) for r, hs in groups.items()},
        "cells": {"%#x" % h: n for h, n in seen.items()},
        "separating_bits": out,
    }


def compare(paths, verbose=False):
    """Run both models over `paths` and return the agreement census as a dict."""
    import collections
    import fxrender
    import sbsasm

    got = collections.Counter()
    names = collections.Counter()
    only = collections.Counter()
    # THE DENOMINATOR THAT MATTERS. 62,721 agreeing programs is 62,721 occurrences of a
    # handful of headers, and reporting only the cell count is how a six-point agreement
    # reads as overwhelming. Both are counted and `main` prints both.
    headers, headers_named = set(), set()
    for p in paths:
        try:
            asm = sbsasm.Assembly(p)
        except Exception:
            got["files_unreadable"] += 1
            continue
        got["files"] += 1
        for rec in asm.records:
            if rec.filter_id != 4:
                continue
            try:
                # THE ARM IS FORCED, not inherited. `fxrender.chain` dispatches on the
                # model in force, so calling it from inside a 'walk' scope would compare
                # the walk model against itself and report perfect agreement.
                with assume.scope(**{"fx.nodemodel": "table"}):
                    tbl = fxrender.chain(rec)
                wlk = chain(rec)
            except Exception:
                got["records_unwalkable"] += 1
                continue
            if not tbl and not wlk:
                continue
            got["records"] += 1
            if [(o, h) for o, h, _p in tbl] != [(o, h) for o, h, _p in wlk]:
                got["records_structure_differs"] += 1
                if verbose:
                    print("%s rec %d: node lists differ" % (p, rec.index))
            t_ok = all(census_role(h) is not None for _o, h, _q in tbl)
            w_ok = all(walk_role(h) is not None for _o, h, _q in wlk)
            got["records_table_walkable"] += t_ok
            got["records_walk_walkable"] += w_ok
            for (_o, h, tp), (_o2, _h2, wp) in zip(tbl, wlk):
                headers.add(h)
                if any(n is not None for n in tp):
                    headers_named.add(h)
                if census_role(h) is None and walk_role(h) is not None:
                    only["walk %#x" % h] += 1
                if walk_role(h) is None and census_role(h) is not None:
                    only["table %#x" % h] += 1
                for name, prog in tp.items():
                    if name is None:
                        continue
                    got["programs_named_by_table"] += 1
                    if wp.get(name) == prog:
                        got["programs_agreeing"] += 1
                    else:
                        names["%#x %s" % (h, name)] += 1
                for name in wp:
                    if name is not None and name not in tp:
                        got["programs_named_by_walk_only"] += 1
    out = dict(got)
    out["name_disagreements"] = dict(names)
    out["headers_one_model_only"] = dict(only)
    out["distinct_headers"] = len(headers)
    out["distinct_headers_named"] = len(headers_named)
    return out


def compare_emissions(paths, verbose=False):
    """Drive `fxrender.emissions` under both models and compare pattern for pattern.

    WITH ITS OWN CONTROL, because the naive comparison reports differences that are not
    the model's. Two records in 25 files emit different numbers under the SAME arm run
    twice -- their parameter programs call `rand` -- so every record is rendered three
    times here: table, table again, and walk. A record whose two table runs already
    disagree is counted `nondeterministic` and says nothing either way; only a record that
    reproduces itself and then differs across arms is a difference.
    """
    import collections
    import numpy as np
    import fxrender
    import sbsasm

    def sig(pats):
        return [
            tuple(
                sorted(
                    (
                        k,
                        np.asarray(v).ravel().tolist()
                        if isinstance(v, np.ndarray)
                        else v,
                    )
                    for k, v in q.items()
                )
            )
            for q in pats
        ]

    def drive(rec, asm):
        run = fxrender.make_runner(asm, rec)
        return sig(fxrender.emissions(rec, run, slots=fxrender.seed_slots(rec, run)))

    got = collections.Counter()
    for p in paths:
        try:
            asm = sbsasm.Assembly(p)
        except Exception:
            continue
        for rec in asm.records:
            if rec.filter_id != 4:
                continue
            res = {}
            for arm, key in (("table", "a"), ("table", "b"), ("walk", "w")):
                with assume.scope(**{"fx.nodemodel": arm}):
                    try:
                        res[key] = ("ok", drive(rec, asm))
                    except Exception as exc:
                        res[key] = ("refused", type(exc).__name__)
            a, b, w = res["a"], res["b"], res["w"]
            if a[0] == "refused" and w[0] == "refused":
                got["both_refuse"] += 1
            elif a[0] != w[0]:
                got["one_arm_only"] += 1
                if verbose:
                    print("%s rec %d: table %s, walk %s" % (p, rec.index, a[0], w[0]))
            elif a != b:
                got["nondeterministic"] += 1
            elif a == w:
                got["identical"] += 1
            else:
                got["DIFFER"] += 1
                if verbose:
                    print(
                        "%s rec %d: arms differ on a deterministic record"
                        % (p, rec.index)
                    )
    return dict(got)


def main(argv):
    import corpus

    if len(argv) > 1 and argv[1] == "--emissions":
        limit = int(argv[2]) if len(argv) > 2 else 25
        res = compare_emissions(corpus.paths()[:limit], verbose=True)
        for k in (
            "identical",
            "DIFFER",
            "nondeterministic",
            "one_arm_only",
            "both_refuse",
        ):
            print("%-32s %8d" % (k, res.get(k, 0)))
        return 1 if res.get("DIFFER") or res.get("one_arm_only") else 0
    if len(argv) > 1 and argv[1] == "--separability":
        limit = int(argv[2]) if len(argv) > 2 else None
        res = separability(corpus.paths()[:limit])
        for role_name, hs in sorted(res["headers"].items(), key=lambda kv: str(kv[0])):
            print("%-8s %s" % (role_name, " ".join(hs)))
        for pair, bits in sorted(res["separating_bits"].items()):
            print(
                "bits separating %-14s %s%s"
                % (pair, bits, "   <- not identified" if len(bits) > 1 else "")
            )
        return 0
    limit = int(argv[1]) if len(argv) > 1 else None
    paths = corpus.paths()[:limit]
    res = compare(paths, verbose=True)
    for k in (
        "files",
        "records",
        "records_structure_differs",
        "records_table_walkable",
        "records_walk_walkable",
        "programs_named_by_table",
        "programs_agreeing",
        "programs_named_by_walk_only",
        "distinct_headers",
        "distinct_headers_named",
    ):
        print("%-32s %8d" % (k, res.get(k, 0)))
    print("%-32s %s" % ("headers one model only", res["headers_one_model_only"]))
    print("%-32s %s" % ("name disagreements", res["name_disagreements"] or "none"))
    bad = res["programs_named_by_table"] != res["programs_agreeing"] or res.get(
        "records_structure_differs"
    )
    print("DISAGREEMENT" if bad else "the two models agree")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
