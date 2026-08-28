#!/usr/bin/env python3
"""Name a compiled field by the value the package's OWN SOURCE states for it.

    python3 tools/sourcematch.py                       # every pair this repository ships
    python3 tools/sourcematch.py <dir|.sbs> [--filter blend] [--all]

Four fields in `render2`'s legend were named this way, by hand, one at a time: `blend`'s
relocated `opacitymult`, `hsl`'s hue/saturation/luminosity, `normal`'s intensity, and
`distance`'s radius. The method is always the same -- a `.sbs` states `saturation 0.65` on a
node, and exactly one slot of the compiled twin holds 0.65 -- so it belongs in a tool rather
than in four scratch scripts, and its limits belong in a docstring rather than in my memory.

WHAT IT COMPARES. Source side: every `<compNode>` whose implementation is a native
`<compFilter>`, with the parameters it states and whether each is a constant or a function.
Compiled side: every location the WALK places -- a class bit or a `w1` field -- read as
float32 at the slot the walk gives it. Nothing here scans for plausible values, and nothing
reads a slot the walk did not place.

WHAT A MATCH IS WORTH. A stated value found at a location is evidence, and how much depends
entirely on the value:

  * `distinct` is the number of DIFFERENT stated values matched. One is weak -- half the
    parameters in this format default to 0.5 and a location holding 0.5 matches all of them
    at once. Two distinctive floats is the standard the four hand-derivations met.
  * `exclusive` says no other location of that filter matches as many of this parameter's
    values. Without it the reading is ambiguous, not wrong: `blend` states `opacitymult` at
    TWO locations, and both are correct -- the second is where the compiler puts the slider
    when the opacity port is connected.
  * `dynamic` compares functions to program arms: a node whose parameter is a
    `<dynamicValue>` should compile to a record whose location holds a pointer. It is the
    only signal that can name a location no constant ever reaches, and it is what named
    `hue` -- the parameter no shipped source ever states as a number.

WHAT IT CANNOT DO, and this is the binding limit rather than a caveat: it needs a `.sbs`
AND its compiled twin. This repository ships 74 sources and exactly TWO of them have one.
Between those two the covered filters are blend, levels, gradient, hsl, transformation,
uniform, normal, bitmap, directionalwarp, distance and curve; `blur`, `warp`,
`dirmotionblur`, `pixelprocessor`, `sharpen`, `shuffle` and `dyngradient` have no twin here
and this tool can say nothing about them at all. `--pairs` prints that inventory.

NOT AN ARBITER OF THE RENDER. It reports where a stated value LANDS. Whether the renderer
should read it, and what it means, is a separate question that a reference render or the
spec has to answer.
"""
import argparse
import glob
import os
import re
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import decompose                                                      # noqa: E402
import sbsasm                                                         # noqa: E402

#: `<compNode>` blocks are split on, not parsed: the file is one line of several megabytes
#: and every field this needs is a flat attribute. A real parser would be slower and would
#: not be more correct about `<constantValueFloat4 v="0.1 0.2 0.3 1"/>`.
_NODE = re.compile(r'(?=<compNode>)')
_FILTER = re.compile(r'<compFilter><filter v="([a-z0-9]+)"/>')
_UID = re.compile(r'<uid v="(\d+)"/>')
_CONN = re.compile(r'<connection><identifier v="([^"]+)"/>')
_PARAM = re.compile(r'<name v="([^"]+)"/><relativeTo v="\d+"/><paramValue>'
                    r'(?:<constantValue([A-Za-z0-9]+) v="([^"]*)"/>|(<dynamicValue>))')


#: Values so common that matching one of them names nothing. See `match`.
_ROUND = frozenset((0.0, 1.0, 0.5, -1.0, 2.0, 256.0))


def _f32(word):
    return struct.unpack('<f', struct.pack('<I', word & 0xFFFFFFFF))[0]


def _as_f32(x):
    """A source constant through float32, which is the width the assembly stores."""
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


def _as_int(x):
    """A source constant as the integer a `u32` slot would hold, or None."""
    try:
        f = float(x)
    except ValueError:
        return None
    return int(f) if f == int(f) and -2 ** 31 <= f < 2 ** 32 else None


def source_nodes(path):
    """[{filter, uid, conns, params}] for every native filter node in a `.sbs`.

    `params` maps a name to ('const', (floats...)) or ('dynamic', None). A value this
    cannot read as numbers -- a font name, an enum written as a string -- is kept as
    ('const', None) so the parameter still counts as stated.
    """
    text = open(path, encoding='utf-8', errors='replace').read()
    out = []
    for block in _NODE.split(text):
        f = _FILTER.search(block)
        if not f:
            continue
        uid = _UID.search(block)
        params = {}
        for name, kind, raw, dyn in _PARAM.findall(block):
            if dyn:
                params[name] = ('dynamic', None)
                continue
            try:
                floats = tuple(_as_f32(p) for p in raw.split())
            except ValueError:
                params[name] = ('const', None)
                continue
            # BOTH READINGS ARE KEPT. `outputsize`, `format`, `mipmapmode`, `tiling` and
            # `combinedistance` are integers, and an integer 12 in a u32 slot reads as a
            # float denormal -- so a float-only matcher cannot see any of them, which is
            # why the first version of this tool found no name for a class bit costing two
            # words on six filters. The location is compared against whichever reading its
            # words support.
            params[name] = ('const', floats,
                            tuple(_as_int(p) for p in raw.split()))
        out.append({'filter': f.group(1), 'uid': uid.group(1) if uid else None,
                    'conns': sorted(_CONN.findall(block)), 'params': params})
    return out


def record_locations(asm, filter_id):
    """[(record index, {location: value})] for one filter's records.

    Three kinds of location, because one kind was not enough:

      ('cls', bit)   a class parameter, where the walk places it.
      ('w1', field)  a `w1` parameter, where the COST MODEL places it -- the fitted half,
                     and it is empty for `normal` and short for `blend`, which is exactly
                     why the third kind exists.
      ('end', -k)    the k'th word back from the header end. The parameter block is
                     end-anchored (SPEC 13.4), so this frame is where a stated value can be
                     found without believing any width. It is the frame the four
                     hand-derivations actually used.

    A value is the tuple of float32 at the slot, or ('program', pointer) when the field's
    state says program.
    """
    out = []
    for rec in asm.records:
        if rec.filter_id != filter_id:
            continue
        try:
            d = decompose.decompose(rec)
        except Exception:
            continue
        if not d:
            continue
        here = {}
        words = rec.words

        def window(slot, n):
            """Both readings of one span: float32, and the raw words as integers."""
            span = tuple(words[slot:slot + n])
            return {'f': tuple(_f32(w) for w in span), 'i': span}

        for (bit, slot, width) in d.get('cls_params', ()):
            n = max(1, int(width))
            if 0 <= slot and slot + n <= len(words):
                here[('cls', bit)] = window(slot, n)
        for (j, state, slot, width) in d.get('param_slots', ()):
            n = max(1, int(width))
            if not (0 <= slot and slot + n <= len(words)):
                continue
            here[('w1', j)] = (('program', words[slot] + 52) if state == 2
                               else window(slot, n))
        end = d.get('end')
        floor = max([s for s in d.get('inputs', ()) if isinstance(s, int)] + [1]) + 1
        if isinstance(end, int):
            for k in range(1, 5):
                slot = end - k
                if slot < floor or slot >= len(words):
                    break
                here[('end', -k)] = window(slot, 1)
                if slot + 2 <= len(words):
                    here[('end2', -k)] = window(slot, 2)
                if slot + 4 <= len(words):
                    here[('end4', -k)] = window(slot, 4)
        out.append((rec.index, here))
    return out


def _stated(nodes, filter_name):
    """{parameter: {'consts': [tuple...], 'dynamic': n}} over one filter's source nodes."""
    stated = {}
    for node in nodes:
        if node['filter'] != filter_name:
            continue
        for name, entry in node['params'].items():
            kind, value = entry[0], entry[1]
            e = stated.setdefault(name, {'consts': [], 'ints': [], 'dynamic': 0})
            if kind == 'dynamic':
                e['dynamic'] += 1
            elif value is not None:
                e['consts'].append(value)
                ints = entry[2] if len(entry) > 2 else None
                if ints is not None and all(i is not None for i in ints):
                    e['ints'].append(tuple(ints))
    return stated


def _holds(held, floats, ints=None):
    """Does a location hold this stated constant, at its own WIDTH, under either reading?

    Width-exact on purpose. Letting a stated Float1 match any word of a wider window was
    the first version, and it reported `hsl`'s luminosity at seven locations at once --
    every window that happened to contain the word. The windows are offered at widths 1, 2
    and 4 instead, so the right width is its own location and a match names one place.

    Both readings, because this format stores integers too: `outputsize` is written `12 12`
    and a slot holding the integer 12 reads as a float denormal. A float-only matcher is
    blind to every enum and every size in the file.
    """
    if not isinstance(held, dict):
        return False
    if len(floats) == len(held['f']) and all(a == b for a, b in zip(floats, held['f'])):
        return True
    return bool(ints) and len(ints) == len(held['i']) and all(
        a is not None and a == b for a, b in zip(ints, held['i']))


def match(sbs_path, asm_path, only=None):
    """[(filter, parameter, location, row)] -- every location a stated value reaches."""
    nodes = source_nodes(sbs_path)
    asm = sbsasm.Assembly(asm_path)
    ids = {n: i for i, n in sbsasm.FILTERS.items()}
    rows = []
    for filter_name in sorted({n['filter'] for n in nodes}):
        if only and filter_name != only:
            continue
        fid = ids.get(filter_name)
        if fid is None:
            continue
        stated = _stated(nodes, filter_name)
        if not stated:
            continue
        places = record_locations(asm, fid)
        if not places:
            continue
        every = sorted({loc for _i, here in places for loc in here})
        found = {}
        for name, info in stated.items():
            for loc in every:
                hits, seen = 0, set()
                by_float = {tuple(c) for c in info['consts']}
                for _i, here in places:
                    held = here.get(loc)
                    if held is None:
                        continue
                    for k, value in enumerate(info['consts']):
                        ints = info['ints'][k] if k < len(info['ints']) else None
                        if _holds(held, value, ints):
                            hits += 1
                            seen.add(tuple(value))
                progs = sum(1 for _i, here in places
                            if isinstance(here.get(loc), tuple)
                            and here[loc][:1] == ('program',))
                del by_float
                found[(name, loc)] = {
                    'records': hits, 'distinct': len(seen),
                    'stated': len({tuple(c) for c in info['consts']}),
                    'dynamic': info['dynamic'], 'programs': progs,
                    'present': sum(1 for _i, here in places if loc in here)}
        # `exclusive` is per (parameter, location): no OTHER location of this filter
        # matched as many distinct values of the same parameter.
        for (name, loc), row in found.items():
            best = max(r['distinct'] for (n2, _l), r in found.items() if n2 == name)
            row['exclusive'] = row['distinct'] == best and best > 0 and sum(
                1 for (n2, _l), r in found.items()
                if n2 == name and r['distinct'] == best) == 1
            # A LONE MATCH ON A ROUND NUMBER IS NOT EVIDENCE. Half the parameters in this
            # format sit at 0, 1 or 0.5, so a location holding one of those matches many
            # parameters at once and names none of them. Two distinct values is the
            # standard the four hand-derivations met, and one distinctive value is worth
            # reporting below it; one round value is worth nothing.
            lone = (row['distinct'] == 1 and row['stated'] == 1
                    and all(v in _ROUND for c in stated[name]['consts'] for v in c))
            row['verdict'] = (
                'CONFIRMED' if row['distinct'] >= 2 and row['distinct'] == row['stated']
                else 'weak' if lone
                else 'supported' if row['distinct'] == row['stated'] and row['stated']
                else 'dynamic-only' if (not row['stated'] and row['dynamic']
                                        and row['programs'])
                else 'partial' if row['distinct'] else '')
            if row['verdict'] and row['verdict'] != 'weak':
                rows.append((filter_name, name, loc, row))
            elif row['verdict'] == 'weak':
                rows.append((filter_name, name, loc, row))
    return rows


#: What the tool must still find. Each row is a naming this repository already derived BY
#: HAND from these same two sources, so a run that stops reporting one has lost the method,
#: not the fact. `location` is where the value lands, `least` the fewest distinct values
#: that must match there.
EXPECTED = (
    ('ChesterfieldSofa', 'blend', 'opacitymult', ('end', -1), 11, 'CONFIRMED'),
    ('ChesterfieldSofa', 'hsl', 'saturation', ('cls', 26), 2, 'CONFIRMED'),
    ('ChesterfieldSofa', 'hsl', 'luminosity', ('cls', 28), 1, 'supported'),
    ('ChesterfieldSofa', 'transformation', 'matrix22', ('w1', 3), 2, 'CONFIRMED'),
    ('SandyStonePath', 'blend', 'opacitymult', ('end', -1), 6, 'CONFIRMED'),
    ('SandyStonePath', 'normal', 'intensity', ('end', -1), 2, 'CONFIRMED'),
    ('SandyStonePath', 'distance', 'distance', ('w1', 0), 2, 'CONFIRMED'),
    ('SandyStonePath', 'directionalwarp', 'intensity', ('w1', 0), 5, 'CONFIRMED'),
    ('SandyStonePath', 'directionalwarp', 'warpangle', ('w1', 1), 5, 'CONFIRMED'),
)


def verify(root=None):
    """[] when every EXPECTED naming is still found, else the rows that are not.

    A tool whose whole output is "here is what matched" cannot be trusted on a run that
    matches nothing -- an empty report and a broken parser look identical. This is the
    fixture that tells them apart, and every row in it was derived before the tool existed.
    """
    root = root or os.path.dirname(_HERE)
    found = {}
    for sbs, asm in pairs(os.path.join(root, 'archive', 'specimens')):
        stem = os.path.basename(sbs)[:-4]
        for filter_name, name, loc, row in match(sbs, asm):
            found[(stem, filter_name, name, loc)] = row
    bad = []
    for (stem, filter_name, name, loc, least, verdict) in EXPECTED:
        row = found.get((stem, filter_name, name, loc))
        if row is None:
            bad.append((stem, filter_name, name, loc, 'not found at all'))
        elif row['distinct'] < least:
            bad.append((stem, filter_name, name, loc,
                        'matched %d values, expected at least %d' % (row['distinct'], least)))
        elif row['verdict'] != verdict:
            bad.append((stem, filter_name, name, loc,
                        'verdict %r, expected %r' % (row['verdict'], verdict)))
    return bad


def pairs(root):
    """[(sbs, sbsasm)] -- the sources this repository ships that HAVE a compiled twin."""
    out = []
    for sbs in sorted(glob.glob(os.path.join(root, '**', '*.sbs'), recursive=True)):
        pack = os.path.dirname(sbs)
        twins = sorted(glob.glob(os.path.join(pack, '**', '*.sbsasm'), recursive=True))
        if twins:
            out.append((sbs, twins[0]))
    return out


def _print(rows, show_all=False):
    print('%-16s %-18s %-10s %8s %8s %8s %9s  %s'
          % ('filter', 'parameter', 'location', 'distinct', 'stated', 'records',
             'dyn/prog', 'verdict'))
    for filter_name, name, loc, row in sorted(
            rows, key=lambda r: (r[0], r[1], -r[3]['distinct'])):
        if not show_all and row['verdict'] in ('partial', 'weak', ''):
            continue
        print('%-16s %-18s %-10s %8d %8d %8d %4d/%-4d  %s%s'
              % (filter_name, name, '%s %s' % loc, row['distinct'], row['stated'],
                 row['records'], row['dynamic'], row['programs'], row['verdict'],
                 '' if row['exclusive'] else '  (also matches elsewhere)'))


def main(argv=None):
    root = os.path.dirname(_HERE)
    ap = argparse.ArgumentParser(prog='sourcematch')
    ap.add_argument('target', nargs='?', help='a .sbs, or a directory holding one')
    ap.add_argument('--asm', help='the compiled twin, if it is not beside the source')
    ap.add_argument('--filter', dest='only')
    ap.add_argument('--all', action='store_true', help='include partial matches')
    ap.add_argument('--pairs', action='store_true', help='list the pairs and stop')
    ap.add_argument('--verify', action='store_true',
                    help='re-derive the namings this repository already made by hand')
    a = ap.parse_args(argv)

    if a.verify:
        bad = verify(root)
        for row in bad:
            print('   LOST %s' % (row,))
        print('%d of %d hand-derived namings re-derived'
              % (len(EXPECTED) - len(bad), len(EXPECTED)))
        return 1 if bad else 0

    found = pairs(os.path.join(root, 'archive', 'specimens'))
    if a.pairs:
        every = glob.glob(os.path.join(root, 'archive', 'specimens', '**', '*.sbs'),
                          recursive=True)
        print('%d sources, %d with a compiled twin' % (len(every), len(found)))
        for sbs, asm in found:
            print('   %-46s %s' % (os.path.basename(sbs), os.path.basename(asm)))
        return 0

    if a.target:
        sbs = a.target if a.target.endswith('.sbs') else None
        if sbs is None:
            hits = glob.glob(os.path.join(a.target, '**', '*.sbs'), recursive=True)
            if not hits:
                print('no .sbs under %s' % a.target)
                return 1
            sbs = hits[0]
        asm = a.asm or next((t for s, t in found if s == sbs), None)
        if asm is None:
            hits = sorted(glob.glob(os.path.join(os.path.dirname(sbs), '**', '*.sbsasm'),
                                    recursive=True))
            asm = hits[0] if hits else None
        if asm is None:
            print('no compiled twin beside %s' % sbs)
            return 1
        found = [(sbs, asm)]

    for sbs, asm in found:
        print('== %s  ->  %s' % (os.path.basename(sbs), os.path.basename(asm)))
        _print(match(sbs, asm, only=a.only), show_all=a.all)
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
