#!/usr/bin/env python3
"""Filter 17, `text`: the string, the font payload, and a layout that is not a rasteriser.

WHERE THE STRING IS. Not in the record's words and not in the value table: in the file's
RESOURCE SEGMENT, the region between the 0x38 header and the first record that also holds
the embedded images. A string resource is `[u32 count][u32 codepoint x count]` -- one
32-bit word per character, so an ASCII string reads as every fourth byte -- and the record
names it at a fixed slot with the format's universal `+52` skew. `Assembly.strings()`
already read the FIRST such resource; it stops at the first word that is not a plausible
count, so it recovers one string per file and there are up to six.

  slot 3, `w1` bit 1 CLEAR   `words[3] + 52` is the offset of the string resource.
  slot 3, `w1` bit 1 SET     `words[3]` is the UID OF A TYPE-6 (string) GRAPH INPUT, and
                             the string is whatever the caller passes at render time. The
                             manifest's `default=` for that uid is what the package itself
                             would show, and that is what this reads.

  Verified both ways on `RuntimeExample`: the source states `text` as a `get_string`
  function, the record sets bit 1, `words[3]` is 3557603301, and the manifest declares
  `<input uid="3557603301" identifier="text" type="6" default="Test"/>`. Its sibling
  `position` is stated as a `get_float2` in the same node, sets the OTHER program bit, and
  the program at that slot is one instruction: `inputref.f2 uid=3557602755`, which the
  manifest names `textPosition`. Two parameters, two arms, both named by the file.

WHERE THE FONT IS, which is the question that decides how much fidelity is reachable.

  slot 4 always holds `offset - 52` of a SECOND resource, and that resource is
  `[u32 hash][u32 length][sfnt]` -- a complete embedded TrueType/OpenType font. The four
  magic bytes are `00 01 00 00` (TrueType) in thirteen of the fourteen distinct payloads the
  thirteen files hold and `ttcf` (a TrueType Collection) in the fourteenth. The length word
  is structural, not a guess: `Do Not Enter` slot 4 -> 0x54, +8 +0xCF14 = 0xCF70, which is
  exactly the offset ANOTHER RECORD OF THE SAME FILE names at slot 3 as its own string, and
  eight of the fourteen land that way -- exactly, since no record names an offset one word
  either side. The other six land on what looks like an offset table rather than a string,
  so the check that holds for all fourteen is the weaker one: the payload lies wholly
  inside the resource segment.

  IT IS PER RECORD AND A FILE CAN CARRY SEVERAL. `PaymentCardSubstance001` holds two, and
  which record points at which is the corroboration that this slot is the font at all: five
  of its six records share one payload and the SIGNATURE record points at the other, which
  is the one place on the card whose glyphs are visibly a different, script face.

  So the outlines ARE embedded, and a byte-faithful `text` is reachable in principle by
  handing that payload to a rasteriser. THIS MODULE DOES NOT DO THAT, on the provenance
  rule: a font is a separately licensed work that the compiler embedded, this project's
  discipline is to touch no font shipped by the tool, and the decision is the maintainer's
  rather than this module's. `embedded_font()` returns the SPAN and the four magic bytes so
  the finding is checkable; nothing here reads a glyph, a `name` table or a metric out of
  it, and no font is written to disk or committed. If the maintainer resolves the licence
  question, `_FONT_SOURCE` is the one switch that changes.

  The compiled record does NOT name the font family anywhere the walk reads -- the family
  lives only in the payload's `name` table and in the SOURCE, whose `fontdata` parameter
  states `Arial|Regular`, `Arial Unicode MS|Regular`, `Arial|Bold` or plain `Arial` across
  the five permitted sources that declare a `text` node. So this renders with a system sans-serif if
  one is found and with boxes if not, and the divergence from the file's own glyphs is
  unmeasured because nothing in this repository can measure it: no package containing a
  `text` record ships an exported map.

WHAT THE PARAMETERS ARE, and one of them contradicts `model.View`'s general rule.

The `w1` fields are `position` (2 words), `fontsize` (1 word) and `matrix22` (4 words), and
each is named by a permitted paired source:

  bits (6, 7)   `position`   RuntimeExample states it dynamic; the record sets bit 7 and
                             the program there is `inputref.f2` on `textPosition`.
  bits (8, 9)   `fontsize`   TimelineExample states `fontsize 0.300000012` and nothing
                             else numeric; its record sets bit 8 and the ONE word of its
                             parameter block is 0x3E99999A = 0.30000001.
  bits (10, 11) `matrix22`   four words, the only 4-wide field, and the source vocabulary
                             (`fontdata`, `text`, `matrix22`, `position`, `fontsize`,
                             `colorswitch`, `background`) has exactly one Float4 that is
                             not a colour.

THE BLOCK IS LAID OUT `matrix22`, `position`, `fontsize` -- NOT in ascending mask order,
which is what every other filter does and what `model.View`'s docstring describes. The
widths are `decompose`'s and are right; only the order differs, and `W1_PARAMS` is a LIST
that `View` walks in list order, so stating it here is enough. The discriminating test, on
the fourteen corpus records that set all three fields:

  ascending order    `fontsize` is the single word between the 2-wide and the 4-wide field,
                     which under this order is the matrix's `c` component. THE FIRST VERSION
                     OF THIS PARAGRAPH SAID IT WAS EXACTLY 0.0 ON ALL FOURTEEN AND THAT WAS
                     WRONG -- `test_the_value_block_is_not_in_ascending_mask_order` caught
                     it. It is exactly 0.0 on ELEVEN, the ones whose matrix is diagonal, and
                     on the other three it is 0.0033, 0.0033 and -0.627: two invisible and
                     one NEGATIVE. Fourteen of fourteen unrenderable, which is the point;
                     "all zero" was a tidier sentence about a smaller fact. `position`
                     meanwhile reads (0.95, 0.0), (1.0, 0.0), (0.91, 0.0) and (1.0, 0.0),
                     an anchor a full canvas width off centre.
  this order         `matrix22` is (0.952, 0, 0, 1.0), (1.0, 0, 0, 0.826), (1.0, 0, 0, 0.5)
                     -- diagonal in five of the six files -- and in `Speed Limit` it is
                     (0.99999, -0.00328, 0.00328, 0.99999), which is a rotation matrix and
                     is not something a wrong placement produces. `fontsize` comes back in
                     [0.1, 0.5], the same range as the records that carry no matrix at all.

And it reads as a layout. `Speed Limit` holds SPEED at y = -0.22 and LIMIT at y = -0.03,
one line above the other; `Do Not Enter` holds DO NOT at -0.10 and ENTER at +0.23. Under
the ascending reading both pairs sit at the same y and differ in the fourth component of a
matrix.

THE ANCHOR IS THE WEAKEST READING HERE AND IT IS ONE OBSERVATION, NOT THREE. Centre-of-
block is right for 56 of the 59 corpus records -- `Stop_Sign` holds STOP at x = -0.01 on a
2048 canvas, which is centred and not left-set, and the two-line stacks all sit at x = 0.
The other three are `PaymentCardSubstance001` records 83, 99 and 168, at x = -0.49, -0.50
and -0.50: centred there is half off the canvas, which is not something an author does, and
the package's own thumbnail shows all three left-aligned at the card's left margin with the
fine print ragged right. So something distinguishes them, and the only thing the records
offer is `w1` bit 12 -- a field the cost model charges ZERO words in every state, so its
mask state is its value, the shape `normal`'s `inversedy` has. It is set on 56 of 59 and
clear on exactly those three.

  The coincidence is exact -- three of fifty-nine, and the same three -- but they are three
  records of one file authored in one sitting, so it is one observation. Inside that file
  the bit is also perfectly anti-correlated with "has a `position` field at all", which is a
  competing explanation this corpus cannot separate; across the corpus that explanation
  fails (`Stop_Sign` and `Do Not Enter` both bake a position AND set bit 12). The bit is
  declared below as `align_flag`, named for the one thing measured about it and not for a
  meaning, and `assume`'s `text.anchor` overrides it in either direction.

WHAT IS STILL A GUESS, because no package with a `text` record ships an exported map and
`refcompare` therefore has nothing to score:

  * `_EM_PER_LINE`. `fontsize` is taken as the LINE ADVANCE and the em box as 0.8 of it,
    which is a fit, not a reading: RoadLines' three-line `SLOW\n12345\n67890` at 0.33 and
    four-line `AHEAD\nSCHOOL\nCLEAR\nPARKING` at 0.23 both fill the canvas height almost
    exactly under advance == fontsize, and under em == fontsize the widest road-sign
    strings overflow the canvas by 15-23%.
  * the polarity. White glyphs on black is assumed. No corpus record sets `background` or
    `colorswitch`, so the value is in neither file, and every record this renders is marked
    LOW CONFIDENCE for that reason alone.
  * word wrap. Applied at the canvas width, because `PaymentCardSubstance001`'s fine print
    is one unbroken 236-character string in the manifest and the package's thumbnail shows
    it broken over five lines, so the engine wraps. THE WIDTH IS WRONG AND THIS IS THE
    MEASUREMENT: the engine's five lines run about 47 characters each; a canvas-width wrap
    with the substitute face fits about 100, so this renders that paragraph on THREE lines
    where the package shows five. Part of that gap is the face -- the card's own glyphs are
    visibly monospaced and so wider per character -- and part is the box, and one specimen
    cannot separate them. Nothing in the record states a box width and no other corpus
    string wraps at all.

WHAT IT DOES REPRODUCE, and this is the bar it was written to: the right string, on the
right canvas at the right channel count, at the position, scale, rotation and line
structure the record states. A downstream `blend`, `distance` or `transformation` gets a
mask of the right shape in the right place, and a human reading the render can tell SPEED
LIMIT from DO NOT ENTER. It is not glyph-exact and does not claim to be.
"""
import os
import struct

import numpy as np

import assume
import manifest
from ops import Unsupported, pos_grid, to_image


# The legend for filter 17 lives inline in `model.W1_PARAMS`, with the evidence for its
# non-ascending order. It was defined here only while `model.py` was owned by another
# worktree; keeping a second copy is exactly the drift that comment warns about.


#: Values the format does not record for this filter, in the shape `filters.DEFAULTS` uses.
#:
#: `text.fontsize` -- the node default for a record whose `w1` bit 8 is clear. THIS IS A
#: GUESS AND NOT AN ARGUMENT FROM AN ABSENCE: 0.5, 0.3 and 0.2 are all stated somewhere in
#: the corpus, so the "the default is the value nobody writes" reasoning that `uniform.fill`
#: rests on is not available here. 0.2 is the low end of the road-sign cluster and keeps a
#: defaulted record on the canvas. Six corpus records are affected.
#: `text.background` / `text.foreground` -- no corpus record sets `background` or
#: `colorswitch`, so the polarity is in neither the assembly nor the manifest.
DEFAULTS = {
    'text.fontsize': 0.2,
    'text.background': 0.0,
    'text.foreground': 1.0,
}

#: The em box as a fraction of `fontsize`, and the line advance as a multiple of it.
#: Fitted, and the fit is stated in the module docstring: `fontsize` behaves as the line
#: advance, not as the em.
_EM_PER_LINE = 0.8

#: Where the glyphs come from. 'system' finds a sans-serif on this machine; 'boxes' draws
#: the layout as filled cap-height boxes. 'embedded' would hand the record's OWN payload to
#: the rasteriser and is NOT enabled: see the module docstring's provenance note. Set
#: `SBS_TEXT_FONT` to override.
_FONT_SOURCE = os.environ.get('SBS_TEXT_FONT', 'system')

#: Candidate system faces, most-generic first. Nothing here is read unless it exists.
_FONT_CANDIDATES = (
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/TTF/DejaVuSans.ttf',
    '/usr/share/fonts/dejavu/DejaVuSans.ttf',
    'C:\\Windows\\Fonts\\arial.ttf',
)

#: Advance width in em for the box backend, and the cap height it draws. Uppercase Latin in
#: a grotesque runs 0.6-0.75 em wide; this is one number for all of them and is only ever
#: used when no font is available at all.
_BOX_ADVANCE = 0.62
_BOX_CAP = 0.70
_BOX_INK = 0.78         # the drawn fraction of the advance, so glyphs do not run together


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

def read_string(asm, offset):
    """The `[u32 count][u32 codepoint ...]` resource at `offset`, or None.

    Returns None rather than raising: a slot that does not address a string resource is a
    record this reader has misunderstood, and the caller decides what to do about it.

    THE CODEPOINT TEST IS NOT "IS IT IN RANGE", AND THE DIFFERENCE IS MEASURABLE. The first
    version accepted anything under 0x110000, and `test_the_font_payload_is_an_sfnt` caught
    what that costs: read FOUR BYTES PAST a real string resource in `Do Not Enter` and the
    permissive reader happily returns a 69-character run of control codes and surrogates
    spliced out of the next resource's offset table. A reader that decodes at every offset
    cannot be used to test whether an offset is right. Surrogates and C0 controls other than
    tab, newline and return are rejected, which is a property of TEXT rather than of this
    format and costs nothing: all 59 corpus strings pass.
    """
    d = asm.data
    if not (0 <= offset and offset + 4 <= len(d)):
        return None
    n = struct.unpack_from('<I', d, offset)[0]
    if not (0 <= n <= 65536) or offset + 4 + 4 * n > len(d):
        return None
    if n == 0:
        return ''
    chars = struct.unpack_from('<%dI' % n, d, offset + 4)
    for c in chars:
        if c >= 0x110000 or 0xD800 <= c <= 0xDFFF:
            return None
        if c < 0x20 and c not in (0x09, 0x0A, 0x0D):
            return None
    return ''.join(chr(c) for c in chars)


_STRING_INPUTS = {}


def string_inputs(asm):
    """{uid: (identifier, default)} for the manifest's TYPE-6 string graph inputs.

    `manifest.image_input_defaults` reads type 5 only, and its regex is anchored on that
    type, so this cannot route through it. Parsed the same way -- one pass over the same
    file -- and cached per assembly path.
    """
    key = getattr(asm, 'path', None)
    got = _STRING_INPUTS.get(key)
    if got is not None:
        return got
    out = {}
    xml = manifest.path_for(asm)
    if xml:
        try:
            import re
            text = open(xml, encoding='utf-8', errors='replace').read()
            for m in re.finditer(r'<input\s+uid="(\d+)"\s+identifier="([^"]*)"\s*'
                                 r'type="6"\s*default="([^"]*)"', text):
                out[int(m.group(1))] = (m.group(2), m.group(3))
        except Exception:
            out = {}
    _STRING_INPUTS[key] = out
    return out


def embedded_font(asm, v):
    """`(offset, length, magic)` of the record's embedded font payload, or None.

    THE PAYLOAD IS NOT READ BEYOND ITS FIRST FOUR BYTES. This exists so the finding -- that
    filter 17 embeds a complete sfnt rather than naming a system face -- is checkable and
    so that a maintainer who resolves the licence question has the span in hand. See the
    module docstring.

    `words[4] + 52` addresses `[u32 hash][u32 length][sfnt]`; the sfnt starts eight bytes
    in and `length` is its size.
    """
    d = asm.data
    if len(v.words) < 5:
        return None
    p = v.words[4] + 52
    if not (0 <= p and p + 12 <= len(d)):
        return None
    length = struct.unpack_from('<I', d, p + 4)[0]
    q = p + 8
    if not (12 <= length and q + length <= len(d)):
        return None
    magic = bytes(d[q:q + 4])
    if magic not in (b'\x00\x01\x00\x00', b'ttcf', b'OTTO', b'true'):
        return None
    return (q, length, magic)


def text_of(ctx, v):
    """`(string, source)` for one record. `source` is 'resource', 'input' or 'missing'.

    The discriminator is `w1` bit 1 -- the two-bit code of field 0, the `text` parameter --
    and not what the word at slot 3 looks like. Both arms hold a 32-bit number and neither
    is distinguishable from the other by value.
    """
    words = v.words
    if len(words) < 4:
        return ('', 'missing')
    w1 = words[1] if len(words) > 1 else 0
    if w1 & 0x2:
        got = string_inputs(ctx.asm).get(words[3])
        if got is None:
            return ('', 'missing')
        return (got[1], 'input')
    s = read_string(ctx.asm, words[3] + 52)
    return ('', 'missing') if s is None else (s, 'resource')


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _metrics(font):
    """`advance(ch) -> em` for the chosen backend."""
    if font is None:
        return lambda ch: (0.0 if ch == '\n' else _BOX_ADVANCE)
    unit = float(font.size)

    def advance(ch):
        try:
            return font.getlength(ch) / unit
        except Exception:
            return _BOX_ADVANCE
    return advance


def _wrap(line, advance, limit_em):
    """`line` broken on spaces so no piece exceeds `limit_em`, longest-first.

    A word longer than the limit on its own is left whole rather than split mid-word: the
    only corpus string that wraps is prose, and a hard break inside `authorized` would be
    a worse error than one over-wide line.
    """
    words = line.split(' ')
    out, cur, cur_w = [], [], 0.0
    space = advance(' ')
    for w in words:
        w_em = sum(advance(c) for c in w)
        step = w_em if not cur else space + w_em
        if cur and cur_w + step > limit_em:
            out.append(' '.join(cur))
            cur, cur_w = [w], w_em
        else:
            cur.append(w)
            cur_w += step
    out.append(' '.join(cur))
    return out


def layout(s, fontsize, advance, wrap_em=None):
    """`(lines, em)` -- the string as drawn rows, in TEXT SPACE.

    Text space has the same units as the canvas: 1.0 is the canvas height, the origin is
    the canvas centre before `position` and `matrix22` are applied, and +y is down. The
    line advance is `fontsize` and the em box is `_EM_PER_LINE` of it -- see the module
    docstring for what settled that and how firmly.
    """
    em = fontsize * _EM_PER_LINE
    rows = []
    for raw in s.split('\n'):
        if wrap_em is not None and em > 0:
            rows.extend(_wrap(raw, advance, wrap_em / em))
        else:
            rows.append(raw)
    return (rows, em)


def _affine(v, W, H, matrix, position):
    """Text-space `(x, y)` for every canvas pixel, as two `(N,)` arrays.

    `transformation`'s convention, which is the only one in this renderer: both axes are
    normalised to [0, 1], the centre is 0.5, and the matrix is row-major `(a, b, c, d)`.
    This is the INVERSE map -- canvas to text -- because the raster is sampled, so the
    matrix the record states is inverted here and a singular one is a refusal.
    """
    a, b, c, d = matrix
    det = a * d - b * c
    if not np.isfinite(det) or abs(det) < 1e-9:
        raise Unsupported('matrix22 is singular (det %.3g), so no text can be placed' % det)
    ia, ib, ic, idd = d / det, -b / det, -c / det, a / det
    grid = pos_grid(W, H)
    cx = grid[:, 0] - 0.5 - np.float32(position[0])
    cy = grid[:, 1] - 0.5 - np.float32(position[1])
    return (ia * cx + ib * cy, ic * cx + idd * cy)


# ---------------------------------------------------------------------------
# Rasterising
# ---------------------------------------------------------------------------

def _system_font(px):
    """A system sans-serif at `px`, or None. Lazily imported; never a hard dependency."""
    if _FONT_SOURCE == 'boxes':
        return None
    try:
        from PIL import ImageFont
    except Exception:
        return None
    for path in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, px)
        except Exception:
            continue
    return None


def anchor(v):
    """'centre' or 'left' -- where `position` sits relative to the text block.

    THE WEAKEST READING IN THIS MODULE; the module docstring states its whole evidence and
    `assume`'s `text.anchor` overrides it. 'flag' (the default) reads the record; 'centre'
    and 'left' force one answer for a sweep.
    """
    choice = assume.assumed('text.anchor', 'flag')
    if choice in ('centre', 'left'):
        return choice
    return 'centre' if v.has('align_flag') else 'left'


def _coverage_boxes(rows, em, advance, tx, ty, align):
    """Glyph coverage as filled cap-height rectangles -- the no-font path.

    A DOCUMENTED PLACEHOLDER, not an attempt at letters. What it preserves is everything
    the layout knows: which rows exist, how wide each is, where the block sits and how the
    matrix transformed it. A downstream `blend` gets a mask with the right footprint and a
    reader can see that the record draws two lines of six and five characters where the
    file says DO NOT / ENTER.
    """
    cov = np.zeros(tx.shape, np.float32)
    n = len(rows)
    for i, row in enumerate(rows):
        width = sum(advance(ch) for ch in row) * em
        y0 = (i - 0.5 * n) * (em / _EM_PER_LINE) + 0.5 * (em / _EM_PER_LINE - em * _BOX_CAP)
        y1 = y0 + em * _BOX_CAP
        x = -0.5 * width if align == 'centre' else 0.0
        for ch in row:
            w = advance(ch) * em
            if ch.strip():
                pad = 0.5 * w * (1.0 - _BOX_INK)
                cov[(tx >= x + pad) & (tx < x + w - pad) & (ty >= y0) & (ty < y1)] = 1.0
            x += w
    return cov


def _coverage_font(font, rows, em, advance, tx, ty, W, H, align):
    """Glyph coverage from a real face, rasterised in TEXT SPACE and sampled.

    One raster over the bounding box of the mapped canvas, so the sampling density follows
    the canvas rather than the text: a record whose matrix shrinks the text does not pay
    for a raster it cannot see, and one that magnifies it gets the resolution back.
    """
    from PIL import Image, ImageDraw

    lo_x, hi_x = float(tx.min()), float(tx.max())
    lo_y, hi_y = float(ty.min()), float(ty.max())
    if not all(np.isfinite(z) for z in (lo_x, hi_x, lo_y, hi_y)):
        raise Unsupported('the inverse text transform is not finite')
    span_x, span_y = max(hi_x - lo_x, 1e-4), max(hi_y - lo_y, 1e-4)
    # Cap the raster: a 2048 record with a matrix that magnifies 20x would otherwise ask
    # for a 40k-pixel bitmap. 4096 is four times the largest canvas this filter appears on.
    RW = int(min(4096, max(16, round(W * span_x))))
    RH = int(min(4096, max(16, round(H * span_y))))

    px = em * RH / span_y
    if px < 1.0:
        return np.zeros(tx.shape, np.float32)
    face = font.font_variant(size=int(round(max(1.0, min(px, 4096.0)))))
    img = Image.new('L', (RW, RH), 0)
    draw = ImageDraw.Draw(img)
    n = len(rows)
    advance_units = em / _EM_PER_LINE
    for i, row in enumerate(rows):
        if not row.strip():
            continue
        # The row's own centre in text space, then into raster pixels.
        cy = (i + 0.5 - 0.5 * n) * advance_units
        rx = (0.0 - lo_x) / span_x * RW
        ry = (cy - lo_y) / span_y * RH
        draw.text((rx, ry), row, fill=255, font=face,
                  anchor='mm' if align == 'centre' else 'lm')

    raster = np.asarray(img, dtype=np.float32) / 255.0
    # Bilinear sample of the raster at every canvas pixel. Outside the raster is
    # background, NOT a tile: text does not repeat.
    u = (tx - lo_x) / span_x * RW - 0.5
    w_ = (ty - lo_y) / span_y * RH - 0.5
    x0 = np.floor(u).astype(np.int64)
    y0 = np.floor(w_).astype(np.int64)
    fx = (u - x0).astype(np.float32)
    fy = (w_ - y0).astype(np.float32)
    out = np.zeros(tx.shape, np.float32)
    for dx in (0, 1):
        for dy in (0, 1):
            xi, yi = x0 + dx, y0 + dy
            ok = (xi >= 0) & (xi < RW) & (yi >= 0) & (yi < RH)
            wgt = (fx if dx else 1.0 - fx) * (fy if dy else 1.0 - fy)
            out[ok] += wgt[ok] * raster[yi[ok], xi[ok]]
    return np.clip(out, 0.0, 1.0)


# ---------------------------------------------------------------------------
# The filter
# ---------------------------------------------------------------------------

def f_text(ctx, v):
    """Filter 17. Registered into `filters.FILTERS` by the hook in `filters.py`.

    EVERY RECORD IS LOW CONFIDENCE, and not as a hedge. Two values this needs are in
    neither the assembly nor the manifest -- which of black and white is the ink, and the
    font size of a record that states none -- and the glyphs themselves are a substitute
    face rather than the payload the file carries. Marking the record says all three at
    once, in the channel `engine` already reports.
    """
    W, H = v.size(ctx.cap)
    n = 4 if v.colour else 1
    s, source = text_of(ctx, v)

    bg = np.float32(assume.assumed('text.background', DEFAULTS['text.background']))
    fg = np.float32(assume.assumed('text.foreground', DEFAULTS['text.foreground']))
    ctx.low_confidence.add(v.index)
    assume.note(v.index)

    fontsize = v.baked('fontsize')
    if fontsize is None:
        if v.has('fontsize'):
            got = np.asarray(ctx.run(v, v.program('fontsize'), 1)).ravel()
            fontsize = float(got[0]) if got.size else None
        if fontsize is None:
            fontsize = assume.assumed('text.fontsize', DEFAULTS['text.fontsize'])

    matrix = v.baked('matrix22')
    if matrix is None and v.has('matrix22'):
        got = np.asarray(ctx.run(v, v.program('matrix22'), 1)).ravel()
        matrix = tuple(float(x) for x in got[:4]) if got.size >= 4 else None
    if matrix is None:
        matrix = (1.0, 0.0, 0.0, 1.0)

    position = v.baked('position')
    if position is None and v.has('position'):
        got = np.asarray(ctx.run(v, v.program('position'), 1)).ravel()
        position = tuple(float(x) for x in got[:2]) if got.size >= 2 else None
    if position is None:
        position = (0.0, 0.0)

    canvas = np.zeros((H, W, n), np.float32) + bg
    if not s.strip() or not (fontsize and np.isfinite(fontsize) and fontsize > 0):
        # AN EMPTY TEXT LAYER IS AN ANSWER, NOT A FAILURE. `Speed Limit` record 1049 states
        # a rotation, a position and a size and points slot 3 at an empty string resource;
        # the record renders as its background and the graph downstream of it is fine.
        return canvas

    px = max(8.0, min(256.0, fontsize * _EM_PER_LINE * H))
    font = _system_font(int(round(px)))
    advance = _metrics(font)
    tx, ty = _affine(v, W, H, matrix, position)
    rows, em = layout(s, float(fontsize), advance, wrap_em=1.0)

    align = anchor(v)
    if font is None:
        cov = _coverage_boxes(rows, em, advance, tx, ty, align)
    else:
        try:
            cov = _coverage_font(font, rows, em, advance, tx, ty, W, H, align)
        except ImportError:
            cov = _coverage_boxes(rows, em, advance, tx, ty, align)

    out = bg + (fg - bg) * cov.reshape(H, W, 1)
    if n == 4:
        # RGB IS THE INK AND ALPHA IS THE COVERAGE. No corpus `text` record is a colour
        # record, so this branch is unexercised by the corpus and is written to be the
        # obvious thing rather than to be a claim about the format.
        out = np.concatenate([np.repeat(out, 3, axis=2),
                              cov.reshape(H, W, 1)], axis=2)
    return to_image(out.reshape(H * W, n), H * W, H, W)
