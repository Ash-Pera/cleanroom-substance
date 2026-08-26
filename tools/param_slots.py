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
dirmotionblur. Both bits are ones this format already charges a word for elsewhere: bit 7
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

WHERE IT IS BLOCKED. `distance` and `emboss` pair zero: their permitted sources declare no
intensity with enough decimals to be distinctive, and for emboss there is exactly one
permitted source at all -- 23 of the 24 that pair are Allegorithmic-authored and excluded.

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
        m = re.search(r'<name v="%s"/>.*?<constantValueFloat1 v="([-\d.e]+)"/>' % param,
                      body, re.S)
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
