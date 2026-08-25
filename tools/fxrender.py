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
from sbsasm import Assembly, FX_NODES                                 # noqa: E402

# 0x1CB joins these on the value evidence in sbsasm's FX_NODE_PARAMS: its +4 program is
# 1.0 in 180 of 183, matching 0x18B's `numberadded` (1.0 in 69.5%) and not 0x1AB's
# `randomseed` (0.0 in 6 of 6). It iterates once and passes through.
ADDNODE = frozenset({0x18B, 0x1AB, 0x20B, 0x1CB})
GATE = 0x89
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
    tbl, order = {}, []
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
        if hdr not in ADDNODE and hdr != GATE:
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
                got = {}
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
        else:
            prog = progs.get('switch')
            if prog is None:
                raise Unmodelled("markov2 with no switch program")
            if bool(run(prog, slots, number)[0]) == gate_polarity:
                walk(i + 1, number)

    walk(0, 0)
    return out


def profile_value(lx, ly, profile):
    """Pattern coverage at local coordinates, |lx|,|ly| <= 0.5 inside the footprint.

    `patterntype` is a declared `fxmaps` parameter that neither this session nor the
    naming work has located, so the SHAPE inside the footprint is unknown. Two profiles
    are offered so the choice is visible rather than buried:

      'rect'  a solid fill -- what the size parameter means before any shape is applied.
      'disc'  a hard circle inscribed in the box, no falloff.
      'cone'  a linear radial falloff, `max(0, 1 - r)`.
      'bell'  a quadratic radial falloff, `max(0, 1 - r^2)`.

    These are four DISTINCT candidates. An earlier version implemented only 'rect' and one
    falloff and let every other name reach it, so a scoring run would have reported three
    candidates tied and that would have measured this function rather than the format. An
    unknown name now raises: a channel that accepts a value it cannot honour is the same
    failure as a guard calibrated in the wrong units, one layer up.

    This is an EXPERIMENT, not a claim. It matters because 2,348 of 2,508 flat renders
    come out solid white under 'rect': a small number of full-cell patterns tiled over
    the canvas. An FX-Map that outputs solid white is not a pattern generator, and this
    project's own note (9a4b14d) names fxmaps as *the* thing that makes spatial
    variation -- so a solid full-cell default is functionally implausible even though
    nothing in the bytes rules it out yet.
    """
    inside = (np.abs(lx) <= 0.5) & (np.abs(ly) <= 0.5)
    if profile == 'rect':
        return inside.astype(np.float32)
    r = np.sqrt((2.0 * lx) ** 2 + (2.0 * ly) ** 2)      # 0 at centre, 1 at the box edge
    if profile == 'disc':
        return ((r <= 1.0) & inside).astype(np.float32)      # hard circle, no falloff
    if profile == 'cone':
        return (np.clip(1.0 - r, 0.0, 1.0) * inside).astype(np.float32)        # linear
    if profile == 'bell':
        return (np.clip(1.0 - r * r, 0.0, 1.0) * inside).astype(np.float32)    # quadratic
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
    if profile is None:
        profile = assume.assumed('fx.profile', 'rect')

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
                cov = profile_value(lx, ly, profile)
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
