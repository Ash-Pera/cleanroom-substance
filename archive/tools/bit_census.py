#!/usr/bin/env python3
"""Every bit of every record header, per filter: which are set, which are accounted for.

    python3 archive/tools/bit_census.py                     # the whole corpus, all filters
    python3 archive/tools/bit_census.py levels blend        # named filters only
    python3 archive/tools/bit_census.py --limit 40          # first 40 files
    python3 archive/tools/bit_census.py --json out.json     # machine-readable
    python3 archive/tools/bit_census.py --check             # audit this file's own w1 rule

THE POINT IS THAT IT IS A SCRIPT. FORMAT-NOTES.md's `levels` census, and the corpus-wide
byte row before it, were both figures that lived in prose: the 92.5% byte row survived eight
days of being wrong because `git log -S` finds no script that ever computed it. A per-filter
bit table is exactly the same shape of claim -- true when taken, silently stale the moment a
cost is re-attributed or a name is added -- so it is computed here and quoted nowhere else.

WHAT "ACCOUNTED FOR" MEANS, and it is three different things that a single "unknown" column
would blur together:

    named        the name legend (`render2.model.CLS_NAMES` / `W1_PARAMS`, plus the two
                 universal class bits 16 `$outputsize` and 23 `$randomseed`) gives the bit a
                 meaning. This is the only column that says anything about SEMANTICS.
    costed       the cost model carries a coefficient for the bit and it is nonzero: the bit
                 gates a stored value, the walk places a slot for it, and no name covers it.
                 A reader is placing the right words and calling them nothing.
    free         the cost model carries a coefficient and it is zero. The bit is DECLARED to
                 the walk and gates no stored value -- class bits 19/20/21 are this. Nothing
                 is misplaced by these, whatever they mean.
    constant     `constant_bits`: set on every record the fit could see, so its cost cannot
                 be told from the intercept. NOT the same as "free"; see `derive_costs.
                 _constant_set_bits`.
    unmodelled   set in the corpus and the spec carries no coefficient at all. This is the
                 only column where a slot could be going unplaced, and it is the one to
                 read first. `derive_costs.bits_of` admits a bit as a feature only when it
                 VARIES over the fit population, and the fit population is the records with
                 an observable header boundary -- so a bit set on some records of a filter
                 and absent from its spec means the two populations differ.

PER-FILTER MODE LOGIC, WHICH IS WHY THIS IS NOT A ONE-LINER. `costs.json` runs five shapes
and a naive reader gets three of them wrong:

    cls dict + w1 dict      the plain additive spec (levels, normal, ...)
    interaction colour      `clsbits` + `pairs` + base/cross vectors, NO `cls` key at all
    interaction colour_states   same, but `cross` holds only the state columns
    mode 'arity'            w1 is an input COUNT, not a code grid (pixelprocessor)
    variants                one spec per record shape behind a guard (shuffle)

A previous attempt to separate "understood" from "merely unnamed" read `spec['pairs']`
unconditionally and got `None` for `blend`, `text` and `pixelprocessor` -- the three filters
that do not use the interaction form. The spec is selected here through
`decompose._select_spec`, per record, so variants and `min_version` guards are honoured for
free and the census describes the spec that actually answered for that record.

THE W1 PRESENCE RULE IS THE WALK'S, NOT `len(words) > 1`. `uniform` has no w1 word and its
slot 1 is an EDGE; `warp` and `shuffle` each have one shape that carries a w1 word and one
that does not. Reading `words[1]` unconditionally counts an edge's record index as a field
grid -- a starting-point script for this census did exactly that. `_w1_of` delegates to
`record_layout.two_shape_w1` and the spec's own mode, which is what `decompose` does, and
`--check` re-runs the answer against `decompose`'s reported `hdr` on every record it covers.
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tools'))

import corpus
import decompose
import record_layout
import sbsasm
from render2 import model

#: word0's low half is not a presence mask -- two of its nibbles are a size (SPEC 6.2), and
#: a fitted table that offers every bit of word0 as a feature will charge header words to
#: them. Named here so the census reports them as structure rather than as unknowns, and so
#: a nonzero cost coefficient landing on one of them shows up as the defect it is.
LOW_HALF = ([(0, 'colour flag')] + [(b, 'filter id') for b in range(1, 8)]
            + [(b, 'log2 width') for b in range(8, 12)]
            + [(b, 'log2 height') for b in range(12, 16)])
LOW_HALF_NAME = dict(LOW_HALF)

#: The two class bits every filter shares, from the manifest rather than from a fit: bit 16
#: resolves a type-4 `$outputsize` input and bit 23 a type-8 `$randomseed` (SPEC 13.4).
UNIVERSAL_CLS = {16: '$outputsize', 23: '$randomseed'}

#: Names the MODEL carries somewhere other than `render2.model`'s two legends. A census
#: that only asks `_covered_bits` reports these as unnamed and overstates the gap: `blend`'s
#: blend mode is decoded, has been for a long time, and lives in `Record.slot1_flags` as
#: `v & 0xF` -- four `w1` bits that cost no header word because the mask state IS the value.
NAMED_ELSEWHERE_W1 = {
    1: [(0x000F, 'blendingmode (Record.slot1_flags)')],
    # `sbsasm.PARAM_SPEC` names fxmaps' four fields; `render2.model.W1_PARAMS` does not.
    4: [(0x0003, 'fx_param0'), (0x0030, 'fx_param1'),
        (0x00C0, 'fx_param2'), (0x0300, 'fx_param3')],
}

#: Class bits this census NAMED and the code legend does not carry. Kept separate from
#: `render2.model.CLS_NAMES` deliberately: adding them there changes what `View.params`
#: holds and, for `uniform`, which slot `f_uniform` reads, so each is a patch that owes an
#: A/B against the reference harness. Listing them here makes the census report the gap
#: instead of either hiding it or pretending the legend already closed it.
#:
#: Every one is named by the SAME arbiter that named bits 16 and 23 -- the manifest
#: identifier of the graph input the slot's program reads with its first `inputref`:
#:
#:     26/27  $pixelsize, baked/program, in the seven filters that read a neighbourhood.
#:            The two bits are mutually exclusive on 124,388 of 124,388 records, which is
#:            the adjacent-pair law SPEC 13.4 states for warp 29/30 and blur 28/29. The
#:            program arm resolves an input literally identified `$pixelsize` (type 1,
#:            float2) on 7,000+ records and is otherwise a `sysvar..exp2` program; the
#:            baked arm is two words, equal pairs at powers of two for `blur`.
#:     6:25   `uniform`'s outputcolor PROGRAM arm, 653 records, inputs named `color`,
#:            `metallic`, `rough`, `metallic_strength`. `f_uniform` currently finds it
#:            with `_fill_program`, a value probe over every program slot.
#:     8:27   `emboss`'s `$pixelsize`, and the one entry here whose SLOT is also wrong: bit 27
#:            is set on 375 of the 375 emboss records the fit could see, so it is in
#:            `constant_bits` and its word went into the intercept, and the walk then charges
#:            that word to `w1` field 0. The program sitting there is the same
#:            `sysvar..exp2` on 358 records and an `inputref` on a graph input named
#:            `$pixelsize` on 8. See SPEC 7.4 and FORMAT-NOTES.md for the grid shift that
#:            goes with it.
PENDING_CLS = {
    6:  {25: 'outputcolor (program arm)'},
    8:  {27: '$pixelsize (program; the walk charges its word to w1 field 0)'},
    7:  {26: '$pixelsize (baked)', 27: '$pixelsize (program)'},
    10: {26: '$pixelsize (baked)', 27: '$pixelsize (program)'},
    11: {26: '$pixelsize (baked)', 27: '$pixelsize (program)'},
    12: {26: '$pixelsize (baked)', 27: '$pixelsize (program)'},
    13: {26: '$pixelsize (baked)', 27: '$pixelsize (program)'},
    18: {26: '$pixelsize (baked)', 27: '$pixelsize (program)'},
    21: {26: '$pixelsize (baked)', 27: '$pixelsize (program)'},
}


def _spec_clsbits(spec):
    """The class bits this spec carries a coefficient for, in the fit's own column order.

    Two shapes: `cls` is a dict (JSON-sorted, so recovered by sorting numerically -- the
    fit built it from an ascending bitrange, so sorted order IS the column order), and
    `clsbits` is the interaction form's explicit list.
    """
    if spec.get('cls') is not None:
        return sorted(int(k) for k in spec['cls'])
    return list(spec.get('clsbits', ()))


def _spec_fields(spec):
    """The w1 FIELD indices the spec carries costs for, and the grid shift."""
    gsh = int(spec.get('w1_shift', 0))
    if spec.get('cls') is not None:
        return sorted(int(k) for k in spec.get('w1', {})), gsh
    return list(spec.get('pairs', ())), gsh


def _cls_cost(spec, b, colour):
    """What the spec charges for class bit `b` on a record of this colour, or None.

    None is "carries no coefficient", never zero -- the distinction between `unmodelled`
    and `free` is the whole census.
    """
    if spec.get('cls') is not None:
        v = spec['cls'].get(str(b))
        return None if v is None else int(round(float(v)))
    bits = list(spec.get('clsbits', ()))
    if b not in bits:
        return None
    return decompose._feature_cost(spec, 1 + bits.index(b), float(colour), False)


def _field_cost(spec, j, state, colour):
    """What the spec charges for w1 field `j` in `state`, or None if it carries no cell."""
    if spec.get('cls') is not None:
        cell = spec.get('w1', {}).get(str(j))
        if cell is None:
            return None
        v = cell.get(str(state))
        return None if v is None else int(round(float(v)))
    pairs = list(spec.get('pairs', ()))
    if j not in pairs:
        return None
    off = 1 + len(spec.get('clsbits', ()))
    if spec.get('has_absent'):
        off += 1
    if spec.get('arity_sm') is not None:
        off += 1
    return decompose._feature_cost(spec, off + 3 * pairs.index(j) + (state - 1),
                                   float(colour), True)


def _arity_bits(spec):
    """The w1 bits an arity count occupies, as a mask, or 0.

    `arity` (the additive form, pixelprocessor) and `arity_sm` (the interaction form,
    fxmaps) are the same field written twice; `decompose` widens both when it reads them,
    and the census reports the WIDENED extent, since those are the bits a record can set.
    """
    ar = spec.get('arity')
    if ar:
        m = ar.get('mask', 0)
        return (m | (m + 1)) << ar.get('shift', 0)      # decompose widens 0xf -> 0x1f
    sm = spec.get('arity_sm')
    if sm:
        return sm[1] << sm[0]
    return 0


def _identified(spec):
    """{label: bool} from the fit's `identified` vector, or {} if it cannot be aligned.

    Rebuilds `derive_costs.fit`'s column labels in the order `row()` emits them. Where the
    rebuilt list and the stored vector disagree in length the answer is {} rather than a
    guess -- a mis-aligned identifiability flag is worse than none, because it reads as a
    statement about a bit it does not describe.
    """
    ident = spec.get('identified')
    if not ident:
        return {}
    labels = ['const'] + ['cls%d' % b for b in _spec_clsbits(spec)]
    labels += ['cls%d&cls%d' % (bx, by) for bx, by, _c in spec.get('conj', ())]
    if spec.get('has_absent') or spec.get('w1_present') is not None:
        labels.append('w1_present')
    if spec.get('arity') or spec.get('arity_sm'):
        labels.append('arity')
    fields, _gsh = _spec_fields(spec)
    for j in fields:
        labels += ['f%d.1' % j, 'f%d.2' % j, 'f%d.3' % j]
    if spec.get('interaction') == 'colour':
        labels = labels + ['colour*' + n for n in labels]
    elif spec.get('interaction') == 'colour_states':
        labels = labels + ['colour*' + n for n in labels[len(labels) - 3 * len(fields):]]
    if len(labels) != len(ident):
        return {}
    return {lab: bool(v) for lab, v in zip(labels, ident)}


def _w1_of(r, spec, ver):
    """The record's w1 word, or None when its shape carries no w1 word.

    THE WALK'S RULE, not `len(words) > 1`. `decompose._has_w1_word` delegates the two-shape
    gate to `record_layout.two_shape_w1`; the spec's mode decides the rest. `uniform` is
    mode 'absent' and its slot 1 is an image edge.
    """
    tw = decompose._has_w1_word(r.filter_id, r.words[0], ver)
    has = tw if tw is not None else (spec.get('mode') != 'absent')
    if not has or len(r.words) < 2:
        return None
    return r.words[1]


#: Class bits that gate no stored value -- so a name legend has nothing to place for them --
#: and that a MEASUREMENT nevertheless describes. Printed under the shared-bit summary so the
#: census does not present a settled bit as an open one. See SPEC 13.4.
CHARACTERISED_CLS = {
    19: 'clear IFF the class word is exactly 0x0080 -- an exact partition over 903,616 '
        'records. Still unnamed',
    20: "the output's format bit 4: 94.67% vs 0.60% over the 2,455 records an output names, "
        'and 1,185 of 1,222 within the 156 files whose own outputs disagree on it',
    21: "the output's format bit 6: 98.46% vs 0.00%",
    24: "the filter's sampling class, low bit (0 pixel-local, 3 samples elsewhere); a "
        'parameter instead in uniform, hsl, shuffle and dyngradient',
    25: "the filter's sampling class, high bit; same four exceptions",
}


class FilterCensus(object):
    """One filter's accumulated bit counts."""

    def __init__(self, fid):
        self.fid = fid
        self.records = 0
        self.uncovered = 0                     # no spec answered for the record
        self.colour = 0
        self.w0_set = collections.Counter()    # bit -> records
        self.w1_records = 0
        self.w1_set = collections.Counter()
        self.states = collections.defaultdict(collections.Counter)   # field -> state -> n
        self.cls_cost = collections.defaultdict(collections.Counter)  # bit -> cost -> n
        self.field_cost = collections.defaultdict(collections.Counter)  # (j,st) -> cost -> n
        self.spec_keys = collections.Counter()  # a short description of the spec that answered
        self.specs = {}                         # description -> spec
        self.modelled_cls = set()
        self.constant_cls = set()
        self.modelled_fields = set()
        self.arity_mask = 0
        self.gsh = 0
        self.free_mask = 0                      # w1 bits whose field costs 0 in every state
        self.free_values = collections.Counter()  # the value those bits carry

    def add(self, r, spec, ver):
        self.records += 1
        w0 = r.words[0]
        colour = w0 & 1
        self.colour += colour
        for b in range(32):
            if (w0 >> b) & 1:
                self.w0_set[b] += 1
        if spec is None:
            self.uncovered += 1
            return
        key = spec.get('_key', '')
        self.spec_keys[key] += 1
        self.specs[key] = spec
        self.modelled_cls |= set(_spec_clsbits(spec))
        self.constant_cls |= set(spec.get('constant_bits', ()))
        fields, gsh = _spec_fields(spec)
        self.modelled_fields |= set(fields)
        self.gsh = gsh
        self.arity_mask |= _arity_bits(spec)
        for b in range(16, 32):
            if (w0 >> b) & 1:
                c = _cls_cost(spec, b, colour)
                self.cls_cost[b][c] += 1
        w1 = _w1_of(r, spec, ver)
        if w1 is None:
            return
        self.w1_records += 1
        for b in range(32):
            if (w1 >> b) & 1:
                self.w1_set[b] += 1
        free = 0
        for j in fields:
            st = (w1 >> (2 * j + gsh)) & 3
            self.states[j][st] += 1
            if st:
                self.field_cost[(j, st)][_field_cost(spec, j, st, colour)] += 1
            # A field charged nothing in ANY state is `mask-valued`: it stores no word, so
            # its two bits ARE its value -- the shape of `levels` field 5, `text`'s
            # align_flag and `normal`'s two booleans. Reported as a value distribution
            # rather than as three state counts, because the state framing says nothing
            # about a field that never allocates.
            if not any(_field_cost(spec, j, s, colour) for s in (1, 2, 3)):
                free |= 3 << (2 * j + gsh)
        self.free_mask |= free
        if free:
            self.free_values[w1 & free] += 1

    # ---- classification

    def named_cls(self, pending=True):
        _w1bits, cls = model._covered_bits(self.fid)
        out = set(cls) | set(UNIVERSAL_CLS)
        if pending:
            out |= set(PENDING_CLS.get(self.fid, ()))
        return out

    def named_w1_bits(self):
        w1bits, _cls = model._covered_bits(self.fid)
        for nm, pres, _prog in sbsasm.PARAM_SPEC.get(self.fid, ()):
            w1bits |= pres
        for mask, _nm in NAMED_ELSEWHERE_W1.get(self.fid, ()):
            w1bits |= mask
        return w1bits

    def cls_status(self, b):
        """(status, cost) for a class bit that is SET somewhere in this filter."""
        costs = self.cls_cost[b]
        vals = {c for c in costs if c is not None}
        if not costs or set(costs) == {None}:
            return ('constant' if b in self.constant_cls else 'unmodelled'), None
        cost = max(vals) if vals else None
        if cost and cost > 0:
            return 'costed', cost
        return 'free', 0

    def unaccounted_cls(self):
        """Class bits set in the corpus that no NAME covers, with their status."""
        named = self.named_cls()
        out = []
        for b in sorted(self.w0_set):
            if b < 16 or b in named or not self.w0_set[b]:
                continue
            st, cost = self.cls_status(b)
            out.append((b, self.w0_set[b], st, cost))
        return out

    def unaccounted_w1(self):
        """w1 bits set in the corpus that no name covers, grouped by field where possible."""
        named = self.named_w1_bits()
        out = []
        for b in sorted(self.w1_set):
            if (named >> b) & 1 or not self.w1_set[b]:
                continue
            if (self.arity_mask >> b) & 1:
                st = 'arity'
                j = None
            else:
                j = (b - self.gsh) // 2 if b >= self.gsh else None
                if j is not None and j in self.modelled_fields:
                    cells = [c for (jj, s), cc in self.field_cost.items() if jj == j
                             for c in cc if c]
                    st = 'costed' if any(c > 0 for c in cells) else 'free'
                else:
                    st = 'unmodelled'
            out.append((b, self.w1_set[b], st, j))
        return out


def run(paths, wanted=None, check=False):
    cens = {}
    mismatch = collections.Counter()
    loud = collections.Counter()
    for p in paths:
        try:
            a = sbsasm.Assembly(p)
        except Exception:
            continue
        ver = a.header.get('version') if isinstance(a.header, dict) else 0
        for r in a.records:
            f = r.filter_id
            if wanted is not None and f not in wanted:
                continue
            if not r.words:
                continue
            c = cens.get(f)
            if c is None:
                c = cens[f] = FilterCensus(f)
            w1raw = r.words[1] if len(r.words) > 1 else None
            spec = None
            if f == 5:
                spec = None                     # vectorshape: no header cost model at all
            else:
                try:
                    spec = decompose._select_spec(f, r.words[0], w1raw,
                                                  0 if f == 4 else ver)
                except Exception:
                    spec = None
            if spec is not None and '_key' not in spec:
                g = spec.get('guard')
                spec['_key'] = ('c%d' % g['value']) if g else ''
            c.add(r, spec, ver)
            if check and spec is not None:
                try:
                    d = decompose.decompose(r)
                except Exception:
                    d = None
                if d is not None and 'hdr' in d:
                    ours = 2 if _w1_of(r, spec, ver) is not None else 1
                    if ours != d['hdr']:
                        mismatch[(f, ours, d['hdr'])] += 1
                if d is not None:
                    _loud(a, r, d, loud)
    return cens, mismatch, loud


def _loud(a, r, d, loud):
    """SPEC 6.3's two loud checks, per (filter, field), as counts.

    A slot the walk calls an EDGE must hold a backward record index; a slot it calls a
    PROGRAM must hold a decodable program at `value + 52`. Both fail loudly by
    construction, which is the point: a wrong radius renders and a wrong address does
    not. Run over the census so a state legend that is wrong for one filter shows up as a
    number rather than as a plausible float.
    """
    for s in d.get('inputs', ()):
        if s >= len(r.words):
            continue
        v = r.words[s]
        ok = (0 <= v < r.index) or v == 0xFFFFFFFF
        loud[('edge', r.filter_id, bool(ok))] += 1
    for (j, st, slot, _w) in d.get('param_slots', ()):
        if st != 2 or slot >= len(r.words):
            continue
        loud[('prog', r.filter_id, j, a.valid_program(r.words[slot] + 52))] += 1


def _bar(n, tot):
    return '%8d %6.2f%%' % (n, 100.0 * n / tot if tot else 0.0)


def report(cens, out=sys.stdout):
    names = dict(sbsasm.FILTERS)
    shared = collections.defaultdict(list)
    for f in sorted(cens, key=lambda f: -cens[f].records):
        c = cens[f]
        print('', file=out)
        print('=' * 78, file=out)
        print('%-16s filter %-3d  %d records  (%d colour)  spec %s' % (
            names.get(f, '?'), f, c.records, c.colour,
            ', '.join('%s x%d' % (k or 'plain', n) for k, n in c.spec_keys.most_common())
            or 'NONE'), file=out)
        if c.uncovered:
            print('  %d records no spec answered for' % c.uncovered, file=out)
        spec = next(iter(c.specs.values()), None)
        if spec is not None:
            ident = _identified(spec)
            print('  mode %-10s interaction %-14s w1 grid shift %d%s' % (
                spec.get('mode'), spec.get('interaction') or '-', c.gsh,
                '   arity bits 0x%x' % c.arity_mask if c.arity_mask else ''), file=out)
        else:
            ident = {}

        print('  word0 low half (SPEC 6.2 -- structure, not a presence mask)', file=out)
        for lo, hi, what in ((0, 0, 'colour flag'), (1, 7, 'filter id'),
                             (8, 11, 'log2 width'), (12, 15, 'log2 height')):
            bits = ' '.join('%d:%d' % (b, c.w0_set[b]) for b in range(lo, hi + 1)
                            if c.w0_set[b])
            charged = [b for b in range(lo, hi + 1)
                       if any(k for k in c.cls_cost.get(b, ()) if k)]
            print('    bits %-5s %-12s %s%s' % (
                '%d-%d' % (lo, hi) if hi > lo else str(lo), what,
                bits or '(never set)',
                '   *** CHARGED A SLOT: %s' % charged if charged else ''), file=out)

        print('  class word (word0 bits 16-31)', file=out)
        print('    bit  %-16s %-9s %-11s %s' % ('records', 'cost', 'status', 'name'),
              file=out)
        named = c.named_cls()
        for b in range(16, 32):
            n = c.w0_set[b]
            if not n:
                continue
            st, cost = c.cls_status(b)
            nm = UNIVERSAL_CLS.get(b) or (model.CLS_NAMES.get(f, {}).get(b, ('', ''))[0])
            if not nm and b in PENDING_CLS.get(f, {}):
                nm = PENDING_CLS[f][b] + '  [not in the code legend]'
            idflag = ident.get('cls%d' % b)
            costs = sorted(k for k in c.cls_cost[b] if k is not None)
            cs = ('/'.join(str(x) for x in costs) if costs else '-')
            if idflag is False:
                cs += ' (unident)'
            print('    %-4d %s %-9s %-11s %s' % (
                b, _bar(n, c.records), cs, st, nm or '--'), file=out)
            if b not in named:
                shared[b].append((names.get(f, f), n, st))

        if c.w1_records:
            print('  w1 (present on %d of %d records)' % (c.w1_records, c.records),
                  file=out)
            w1named = c.named_w1_bits()
            allf = sorted(set(c.states) | set(c.modelled_fields))
            for j in allf:
                bits = (2 * j + c.gsh, 2 * j + 1 + c.gsh)
                sc = c.states[j]
                if not any(s for s in sc if s):
                    continue
                nm = [nm for (mask, _sh, nm, _k) in model.W1_PARAMS.get(f, ())
                      if nm and (mask & (3 << bits[0]))]
                nm += [n2 for (mask, n2) in NAMED_ELSEWHERE_W1.get(f, ())
                       if mask & (3 << bits[0])]
                nm += [n2 for (n2, pres, _pg) in sbsasm.PARAM_SPEC.get(f, ())
                       if (pres & (3 << bits[0])) and n2 not in nm]
                costs = ' '.join('%d:%s' % (s, '/'.join(
                    str(x) for x in sorted(k for k in c.field_cost[(j, s)] if k is not None))
                    or '-') for s in (1, 2, 3) if sc[s])
                print('    field %-3d bits %2d,%-3d  %-30s cost %-14s %s' % (
                    j, bits[0], bits[1],
                    ' '.join('%s:%d' % (('baked', 'prog', 'edge')[s - 1], sc[s])
                             for s in (1, 2, 3) if sc[s]),
                    costs, '/'.join(nm) if nm else '--'), file=out)
            loose = [b for b in sorted(c.w1_set)
                     if not (c.arity_mask >> b) & 1
                     and ((b - c.gsh) // 2) not in c.modelled_fields]
            if loose:
                print('    bits in no modelled field: %s' % ' '.join(
                    '%d:%d' % (b, c.w1_set[b]) for b in loose), file=out)
            if c.arity_mask:
                ab = [b for b in sorted(c.w1_set) if (c.arity_mask >> b) & 1]
                print('    arity count bits: %s' % (' '.join(
                    '%d:%d' % (b, c.w1_set[b]) for b in ab) or '(never set)'), file=out)
            if c.free_mask:
                vals = c.free_values.most_common(6)
                print('    mask-valued fields (0 words in every state) mask 0x%x, values: %s'
                      % (c.free_mask, '  '.join('%s:%d' % (bin(v), n) for v, n in vals)),
                      file=out)

        ucls = c.unaccounted_cls()
        uw1 = c.unaccounted_w1()
        print('  UNNAMED, still set:', file=out)
        print('    class %s' % (', '.join('%d(%s,%d)' % (b, st, n)
                                          for b, n, st, _c in ucls) or 'none'), file=out)
        print('    w1    %s' % (', '.join('%d(%s)' % (b, st)
                                          for b, _n, st, _j in uw1) or 'none'), file=out)
        bad = [x for x in ucls if x[2] in ('costed', 'unmodelled')]
        bad += [x for x in uw1 if x[2] == 'unmodelled']
        if bad:
            print('    ^ of which NOT merely free/constant: %s' % bad, file=out)

    print('', file=out)
    print('=' * 78, file=out)
    print('CLASS BITS NO NAME LEGEND COVERS -- which filters set them', file=out)
    for b in sorted(shared):
        tot = sum(n for _f, n, _s in shared[b])
        sts = sorted({s for _f, _n, s in shared[b]})
        print('  bit %-3d %2d filters  %9d records  %s' % (
            b, len(shared[b]), tot, ','.join(sts)), file=out)
        print('          %s' % ' '.join('%s:%d' % (f, n) for f, n, _s
                                        in sorted(shared[b], key=lambda x: -x[1])),
              file=out)
        if b in CHARACTERISED_CLS:
            print('          -> %s' % CHARACTERISED_CLS[b], file=out)
    return shared


def to_json(cens):
    out = {}
    for f, c in cens.items():
        out[str(f)] = {
            'name': sbsasm.FILTERS.get(f), 'records': c.records, 'colour': c.colour,
            'uncovered': c.uncovered,
            'w0_set': {str(b): n for b, n in sorted(c.w0_set.items())},
            'w1_records': c.w1_records,
            'w1_set': {str(b): n for b, n in sorted(c.w1_set.items())},
            'states': {str(j): {str(s): n for s, n in sorted(v.items())}
                       for j, v in sorted(c.states.items())},
            'cls_cost': {str(b): {str(k): n for k, n in sorted(
                v.items(), key=lambda kv: (kv[0] is None, kv[0]))}
                for b, v in sorted(c.cls_cost.items())},
            'unaccounted_cls': c.unaccounted_cls(),
            'unaccounted_w1': c.unaccounted_w1(),
            'grid_shift': c.gsh, 'arity_mask': c.arity_mask,
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('filters', nargs='*', help='filter names or ids; default all')
    ap.add_argument('--limit', type=int, default=None, help='first N corpus files')
    ap.add_argument('--json', dest='json_out', default=None)
    ap.add_argument('--check', action='store_true',
                    help="audit this file's w1-presence rule against decompose's hdr")
    args = ap.parse_args(argv)

    byname = {v: k for k, v in sbsasm.FILTERS.items()}
    wanted = None
    if args.filters:
        wanted = {int(x) if x.isdigit() else byname[x] for x in args.filters}
    paths = corpus.paths()
    if args.limit:
        paths = paths[:args.limit]
    cens, mismatch, loud = run(paths, wanted, check=args.check)
    print('%d files, %d records' % (len(paths), sum(c.records for c in cens.values())))
    report(cens)
    if args.check:
        print('')
        print('w1-presence check against decompose hdr: %s' % (
            'AGREE on every covered record' if not mismatch else dict(mismatch)))
        eok = sum(n for k, n in loud.items() if k[0] == 'edge' and k[2])
        ebad = {sbsasm.FILTERS.get(k[1], k[1]): n for k, n in loud.items()
                if k[0] == 'edge' and not k[2]}
        pok = sum(n for k, n in loud.items() if k[0] == 'prog' and k[3])
        pbad = {(sbsasm.FILTERS.get(k[1], k[1]), k[2]): n for k, n in loud.items()
                if k[0] == 'prog' and not k[3]}
        print('SPEC 6.3 loud check -- edge slots holding a backward index: %d of %d%s'
              % (eok, eok + sum(ebad.values()),
                 '' if not ebad else '   FAILING: %s' % ebad))
        print('SPEC 6.3 loud check -- state-2 slots resolving a program : %d of %d%s'
              % (pok, pok + sum(pbad.values()),
                 '' if not pbad else '\n    FAILING (filter, field): %s' % pbad))
    if args.json_out:
        with open(args.json_out, 'w') as fh:
            json.dump(to_json(cens), fh, indent=1, sort_keys=True)
        print('\nwrote %s' % args.json_out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
