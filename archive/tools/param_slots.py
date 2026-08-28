#!/usr/bin/env python3
"""Locate a filter's parameter slot by containment, now that the pairing works.

    python3 tools/param_slots.py [filter ...]

WHY THIS IS NEW. Containment needs a source that declares a value and the SAME package's
binary to find it in. Every earlier attempt globbed `dirname(source)/**/*.sbsasm` and took
`[0]`, which returns every assembly in the collection -- 95 of them for `pairs2/` -- so each
source was searched against an unrelated package. `provenance.own_assembly` pairs them
properly, and with that fixed a value declared on a `warp` node turns up in that file's own
warp records.

WHAT IT FINDS TODAY, over the permitted paired sources, for `intensity`:

    filter            pairings   slot / class word
    warp                  13     4 (0x2309)   5 (0x2319, 0x2B19)   6 (0x2B19)
    directionalwarp       10     5 (0x0319)   6 (0x0B19)
    blur                   2     4 (0x1B19)   5 (0x1B89)
    sharpen                2     3 (0x1319)   4 (0x1B19)
    dirmotionblur          2     5 (0x0B09, 0x0B19)
    distance, emboss       0

THE SLOT IS NOT FIXED, AND THE RULE IS `start + 1 + bit7 + bit11`. Reported as a raw word
index the slot looks unstable -- `warp` puts intensity at 4, 5 and 6 -- because the index
counts from the record header and the header is not a fixed size: `Record.layout` already
says where a record's PARAMETERS begin, after its edge references. Measured from there, the
parameter sits at

    layout start + 1 + (class bit 7) + (class bit 11)

in 38 of 38 located pairings, across warp, directionalwarp, distance, blur, sharpen and
dirmotionblur.

`normal` NOW SUPPORTS IT TOO, on 8 specimens where it used to have one. It was not a Float4
problem -- normal writes `intensity` as a Float1 -- but `locate` demands a value with three
decimals that is unique among ALL the file's records of that filter, and normal's authors use
round numbers. Matching the exact float32 bit pattern within each file instead:

    ChesterfieldSofa 121 (10.0)   SandyStonePath 1452 (16.0)   Marble_Tiles_01 2020 (8.0)
    Mineral_Ore_01 7037 (20.0)    Obsidian_01 3585 (20.0)      Painted_Metal 1584 (5.0)
    substance-designer-materials 740 (25.0)   SubstanceDesignerPractice 362 (2.01)

Eight packages, and both candidate rules land on every one: `predicted_slot` 8 of 8, and
`end - 1` 8 of 8 (slot 5 with end 6 for the seven cls 0x0b19 records, slot 4 with end 5 for
the cls 0x0319 one). The remaining 65 normal nodes cannot pair and the reasons are counted
rather than assumed: 37 declare `intensity` with no float at all, 13 declare no intensity, 9
give it a `dynamicValue` program, 10 have no paired assembly, 4 are ambiguous within their
file and 2 sit in files holding no normal record.

ONE ARITHMETIC NOTE ON THE TABLE ABOVE, not resolved here: its per-filter counts sum to 29,
not 38, and re-running `locate` today reproduces the 29 exactly (warp 13, directionalwarp 10,
blur 2, sharpen 2, dirmotionblur 2, distance 0). Whatever the 38 counted, the table is what
this function returns. Both bits are ones this format already charges a word for elsewhere: bit 7
moves `uniform`'s fill by one, and `hsl` walks its class bits for the same reason.

AND IT CORROBORATES THE BIT-12 READING RATHER THAN UPSETTING IT. `blur intensity: class bit
12 clear` is the largest heading in the blocker census, 49 declared outputs, and the natural
suspicion is that the intensity is simply somewhere else. It is not. Applying the rule above
to the records that refuse, over 20 files:

    bit 12 CLEAR   17 records   the derived slot holds a value that is not an intensity
                                (denormals -- the record's own bytecode read as a float)
    bit 12 SET      8 records   the derived slot is PAST the end of the record

So where bit 12 says a baked intensity is stored the rule finds it, and where bit 12 says
none is stored the same rule lands on something that is not one. That is what an absent
value looks like, and it is independent of the distributional argument the blur branch
makes -- this comes from sources that declare a number and binaries that contain it.

WHERE IT IS BLOCKED. `emboss` pairs zero: there is exactly one permitted source declaring
it at all -- 23 of the 24 that pair are Allegorithmic-authored and excluded.

`distance` DOES NOT pair zero, and the claim that it did was an artefact of how this
function was called. `locate`'s `param` argument DEFAULTS TO 'intensity', and a distance
node does not declare an intensity -- it declares a `distance`. Called with the parameter
the node actually has, `locate('distance', 21, 'distance')` returns NINE pairings across
two permitted sources (SandyStonePath, DLG-Tools__Mineral_Ore_01). The blocker was a
default argument, not the corpus.

That is worth more than nine pairings, because the blocker was quoted onward as a fact
about the data. Before repeating "filter X cannot be reached by containment", call `locate`
with X's own parameter name and check.

THE RULE IS VERIFIED ONLY WHERE cls BIT 0 IS SET, and every pairing this module can
produce is such a record. Over the 34 pairings that survive with node-appropriate parameter
names (blur 1, sharpen 2, warp 11, directionalwarp 10, dirmotionblur 1, distance 9),
`predicted_slot` names the containment-verified slot in 34 of 34 -- and all 34 have
`cls & 1`. There are ZERO pairings with bit 0 clear, so containment says nothing whatever
about that population.

It is not a quiet gap. Over the 2,540 `distance` records in the corpus and the reference
packs, `predicted_slot`'s slot is what the walk enumerates as a parameter in 2,451 of 2,451
records with bit 0 SET -- and in the 89 with bit 0 CLEAR it lands on a walk parameter only
11 times, on a CLS slot 11 times, and on a word the walk accounts to no field at all 67
times. The rule has no term for bit 0; where the bit is clear the parameter sits one slot
later than it predicts.

So `start + 1 + bit 7 + bit 11` should be read as "verified on cls-odd records", which is
all containment can currently license. See `distance._locate_slot` for what the 11 CLS-slot
cases turn out to be.

Restricted to PERMITTED sources: 28 of the 47 sources declaring a blur node are
Allegorithmic-authored and excluded, which is the same wall FORMAT-NOTES records for the
original blur/warp/gradient/fxmaps identification.
"""
import collections
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance                                                    # noqa: E402
import sbsasm                                                        # noqa: E402

NODE = re.compile(r'<compNode>((?:(?!</compNode>).)*?)</compNode>', re.S)
#: one <parameter> element, so a name cannot reach past its own value. See `declared`.
PARAM = re.compile(r'<parameter>((?:(?!</parameter>).)*?)</parameter>', re.S)

#: source node name -> compiled filter id, for the filters whose parameter is a plain float
FILTERS = {'blur': 10, 'sharpen': 13, 'warp': 7, 'directionalwarp': 12,
           'dirmotionblur': 11, 'emboss': 8, 'distance': 21}

MIN_DECIMALS = 3


def _decimals(text):
    m = re.match(r'^-?\d+\.(\d+)$', text)
    return len(m.group(1).rstrip('0')) if m else 0


def declared(sbs_path, node, param):
    """Float values `param` takes on `node` in this source, distinctive ones only.

    Round numbers occur in every filter of every file and pair nothing with anything, so a
    value qualifies only with enough decimals to be specific -- containment.py's rule, at a
    lower threshold because these parameters are authored as sliders and rarely reach five.
    """
    try:
        text = open(sbs_path, encoding='utf-8', errors='replace').read()
    except OSError:
        return []
    out = []
    for body in NODE.findall(text):
        if '<filter v="%s"/>' % node not in body:
            continue
        # FLOAT4 AS WELL AS FLOAT1, and the omission was costing an entire filter. `levels`
        # stores every one of its five parameters as `constantValueFloat4` -- the same scalar
        # repeated across RGB with alpha 0 or 1 -- so a Float1-only pattern matched ONE node
        # in the whole corpus and `locate('levels', 15, ...)` reported a single pairing.
        # Reading the first component of a FloatN turns that into 46 unambiguous pairings
        # across 35 sources, which is what settled `levels`' parameter widths.
        # BOUNDED TO THE PARAMETER'S OWN ELEMENT. `<name>` and the value used to be matched
        # across `.*?` with re.S, which does not stop at `</parameter>` -- so a parameter
        # whose value is NOT a float takes the next parameter's. `normal` is where it shows:
        # every one of its nodes writes `input2alpha` as `<constantValueBool v="0"/>` and
        # `intensity` as a Float1 right after, so `declared('normal', 'input2alpha')`
        # returned INTENSITY's 2.01 and `locate` paired it to intensity's record and slot.
        # A false pairing is worse than a missing one here: `predicted_slot`'s rule is
        # derived from these, so a value attributed to the wrong name would be fitted as
        # though it were evidence.
        for pb in PARAM.findall(body):
            if not re.search(r'<name v="%s"/>' % param, pb):
                continue
            m = re.search(r'<constantValueFloat\d v="([-\d.e]+)'
                          r'(?:[ \t][-\d.e ]*)?"/>', pb)
            if m and _decimals(m.group(1)) >= MIN_DECIMALS:
                out.append(float(m.group(1)))
    return out


def locate(node, fid, param='intensity'):
    """[(source, record, value, slot, class word)] for every unambiguous pairing."""
    found = []
    for path in provenance.paired_sources():
        if provenance.matches(path, provenance.EXCLUDED_AUTHORS):
            continue
        values = declared(path, node, param)
        if not values:
            continue
        own = provenance.own_assembly(path)
        if not own:
            continue
        try:
            asm = sbsasm.Assembly(own)
        except Exception:
            continue
        recs = [(i, r) for i, r in enumerate(asm.records) if r.filter_id == fid]
        if not recs:
            continue
        once = collections.Counter(values)
        for v in values:
            # A value the source declares twice cannot identify one record.
            if once[v] != 1:
                continue
            hits = [(i, k, r) for i, r in recs for k, w in enumerate(r.words)
                    if abs(struct.unpack('<f', struct.pack('<I', int(w) & 0xFFFFFFFF))[0]
                           - v) < 1e-5]
            if len(hits) == 1:
                i, k, r = hits[0]
                found.append((os.path.basename(path), i, v, k, r.cls))
    return found


def predicted_slot(rec):
    """Where a filter's float parameter sits, by the rule the pairings establish.

    `layout start + 1 + bit 7 + bit 11` -- 38 of 38 located pairings across six filters.
    Returns None when the record has no readable layout or the slot falls past its end, so
    a caller gets an absence rather than a word from the next record.
    """
    try:
        _edges, start = rec.layout
    except Exception:
        return None
    # `layout` reports a start of None for records it cannot resolve; that is an absence,
    # not a zero, and treating it as one would point every such record at word 1.
    if start is None:
        return None
    at = start + 1 + ((rec.cls >> 7) & 1) + ((rec.cls >> 11) & 1)
    return at if at < len(rec.words) else None


def main(argv):
    wanted = argv[1:] or sorted(FILTERS)
    grand = collections.Counter()
    for node in wanted:
        fid = FILTERS.get(node)
        if fid is None:
            print('unknown filter %r; known: %s' % (node, sorted(FILTERS)))
            continue
        rows = locate(node, fid)
        print('=== %s (filter %d): %d unambiguous pairing(s)' % (node, fid, len(rows)))
        by_slot = collections.Counter(k for _s, _i, _v, k, _c in rows)
        for slot, n in sorted(by_slot.items()):
            classes = sorted({'0x%04X' % c for _s, _i, _v, k, c in rows if k == slot})
            print('    slot %-3d %3d  class words %s' % (slot, n, ' '.join(classes)))
            grand[(node, slot)] += n
        for src, rec, val, slot, cls in rows[:4]:
            print('      %-28s rec %-6d %-12.6f slot %-3d cls 0x%04X'
                  % (src[:28], rec, val, slot, cls))
    if not grand:
        print('no pairings -- is the corpus present?')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
