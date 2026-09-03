#!/usr/bin/env python3
"""Do the bitmap records point at their pixels?

The pixel region is the RESOURCE SEGMENT, and SPEC 9 puts it at [0x38, resource_end).
A bitmap record names its image at `words[1] + 52` -- the format's universal pointer
skew -- so the first image's declared word of 4 lands on 0x38 exactly.

**THE `+4` READING THIS FILE USED TO PIN IS WITHDRAWN, and three of the four checks below
could not see the difference.** It said the segment sat behind an eight-byte
magic-plus-version header so that pixels began at 8, and every declared offset was four
bytes short of its data. The eight bytes are not a header in front of the pixels; they are
the first two fields of the 0x38-byte FILE header of SPEC 2, whose remaining fields --
per-file uid, total file size, the trailer pointer, the value-table end -- this module's
own `Assembly` parses. Under `+4` the first image's leading 48 bytes were those fields.

What survives is that the offset is right MOD 8: 52 == 4 (mod 8), so the alpha-channel
test below gives the identical answer under both readings, as does the packing test, as
does the magic-and-version test. A uniform 48-byte shift is invisible to all three, which
is why the fourth check exists.

  * the file header's first two words really are a magic and a version (they are -- that
    was never the disputed part, only what it implied);
  * an RGBA image's flattest channel -- its alpha -- lands at index 3, with the depth-8
    4-channel bitmaps as a null control that must answer the same either way. This pins
    the offset MOD 8 and nothing else;
  * the images pack back to back, which must STAY true, since a correction that broke the
    packing would be a different offset rather than a uniform shift. Invariant to a
    uniform shift, so it cannot choose between +4 and +52 either;
  * **THE SEGMENT'S FAR END, which is the one that discriminates.** The images tile
    [0x38, resource_end), and `resource_end` is the record directory's offset out of the
    file header -- it owes nothing to any bitmap record. `max(offset + size)` must equal
    it exactly. At +52 it does, 111 of 111; at +4 it undershoots by 48, 111 of 111.

SKIPS when the corpus is absent.
"""
import contextlib
import io
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
from sbsasm import Assembly                                          # noqa: E402

FILES = int(os.environ.get('SBS_BITMAP_FILES', '120'))
MAGIC = 0x4D414253                       # 'SBAM', little-endian


def _paths():
    try:
        return corpus.paths()[:FILES]
    except Exception:
        return []


def _pixel_bitmaps(asm):
    """Bitmaps with a raw pixel payload -- size and depth known.

    Deliberately EXCLUDES the JPEG-flagged ones, which have their own iterator. The two
    were conflated at first and the `size`/`depth` requirement here silently dropped 45
    of the 54 JPEG bitmaps, because cls 0x808's channel code has no CHANNELS entry so
    size is None. The JPEG test then reported a confident "9 of 9" while examining a
    sixth of its population -- the same failure this file's docstring warns about, one
    level down.
    """
    for rec in asm.records:
        if rec.filter_name != 'bitmap':
            continue
        bm = getattr(rec, 'bitmap', None) or {}
        if bm.get('compressed'):
            continue
        if bm.get('kind') == 'pixels' and bm.get('size') and bm.get('depth'):
            yield rec, bm


def _jpeg_bitmaps(asm):
    """Bitmaps whose class word flags a JPEG payload. No size/depth requirement."""
    for rec in asm.records:
        if rec.filter_name != 'bitmap':
            continue
        bm = getattr(rec, 'bitmap', None) or {}
        if bm.get('compressed') == 'jpeg':
            yield rec, bm


def test_the_pixel_header_is_eight_bytes():
    """'SBAM' at 0 and a version word at 4, in every file that carries pixels.

    KEPT, AND ITS CONCLUSION WITHDRAWN. These two words are real and this test still
    passes; what was wrong was reading them as an eight-byte header with pixels behind it.
    They are the first two fields of SPEC 2's 0x38-byte file header. Left in place because
    a test whose premise moved should say so where the next reader will look.
    """
    paths = _paths()
    if not paths:
        print('SKIP: no corpus')
        return
    files = bad_magic = bad_version = 0
    for f in paths:
        try:
            asm = Assembly(f)
        except Exception:
            continue
        if not any(True for _r, _b in _pixel_bitmaps(asm)) or len(asm.data) < 16:
            continue
        files += 1
        if struct.unpack_from('<I', asm.data, 0)[0] != MAGIC:
            bad_magic += 1
        # A version, not pixels: the low half is zero. The control is word 3, which is
        # pixel data under either reading -- if "low 16 bits zero" were just what this
        # data looks like, the control would show it too.
        if struct.unpack_from('<I', asm.data, 4)[0] & 0xFFFF:
            bad_version += 1
    if not files:
        print('SKIP: no file carries pixels')
        return
    print('    %d files with pixels: %d without the SBAM magic, %d without a version word'
          % (files, bad_magic, bad_version))
    assert bad_magic == 0, '%d of %d files lack the SBAM magic' % (bad_magic, files)
    assert bad_version == 0, ('%d of %d files have pixel-looking data where the version '
                              'word should be' % (bad_version, files))


def test_rgba_alpha_lands_in_the_last_channel():
    """The flattest channel of an RGBA bitmap is its alpha, and alpha is channel 3.

    Depth-8 4-channel bitmaps are the null control: four bytes is exactly one pixel
    there, so the offset correction cannot move their answer and they must score the
    same as they would uncorrected.
    """
    paths = _paths()
    if not paths:
        print('SKIP: no corpus')
        return
    hit = {8: [0, 0], 16: [0, 0]}                     # depth -> [alpha last, total]
    for f in paths:
        try:
            asm = Assembly(f)
        except Exception:
            continue
        for rec, bm in _pixel_bitmaps(asm):
            off, size, ch, depth = bm['offset'], bm['size'], bm['channels'], bm['depth']
            if ch != 4 or off + size > len(asm.data) or depth not in hit:
                continue
            n = rec.height * rec.width * ch
            arr = np.frombuffer(asm.data[off:off + size],
                                dtype='<u1' if depth == 8 else '<u2')
            if arr.size < n:
                continue
            x = arr[:n].reshape(-1, ch)[::97].astype(np.float64)
            hit[depth][1] += 1
            if int(np.argmin(x.std(0))) == ch - 1:
                hit[depth][0] += 1
    for depth in (8, 16):
        good, total = hit[depth]
        if total:
            print('    depth %2d, 4 channels: flattest channel is the last in %d of %d'
                  % (depth, good, total))
    good16, total16 = hit[16]
    if total16 < 4:
        print('SKIP: only %d depth-16 RGBA bitmaps, too few to test' % total16)
        return
    # The measured rate is 13 of 16. Requiring a majority is what distinguishes the
    # corrected offset (alpha last) from the uncorrected one (alpha at index 1, 13 of 16
    # the other way) without pretending every RGBA bitmap has a flat alpha.
    assert good16 * 2 > total16, (
        'only %d of %d depth-16 RGBA bitmaps put their flattest channel last -- the '
        'pixel offset correction has probably come undone' % (good16, total16))


def test_the_images_still_pack_back_to_back():
    """offset[k+1] - offset[k] == size[k]: the correction is a UNIFORM shift.

    This held before the correction too -- packing cannot see a uniform shift, which is
    why it was briefly mistaken for a refutation of it. It is here for the opposite
    reason: it must still hold, because a correction that broke the packing would not be
    a uniform shift and would be wrong in a way the alpha test alone would not catch.
    """
    paths = _paths()
    if not paths:
        print('SKIP: no corpus')
        return
    pairs = packed = 0
    for f in paths:
        try:
            asm = Assembly(f)
        except Exception:
            continue
        spans = sorted({(bm['offset'], bm['size']) for _r, bm in _pixel_bitmaps(asm)})
        for k in range(len(spans) - 1):
            off, size = spans[k]
            if spans[k + 1][0] == off:            # two records sharing one image
                continue
            pairs += 1
            packed += 1 if spans[k + 1][0] - off == size else 0
    if not pairs:
        print('SKIP: no consecutive image pairs')
        return
    print('    %d of %d consecutive image pairs pack exactly' % (packed, pairs))
    # NOT `packed == pairs`. That assertion passed here only because 120 files is too few
    # to reach a counterexample: over all 437 there are 21 non-packing pairs in 7 files,
    # the earliest at corpus index 173. They are real and unrelated to the offset -- gaps
    # where an image is skipped (NightSkyHDRI, pbr_render, BricksSubstance004) and, in
    # GravelSubstance002, seven OVERLAPS, where a declared size runs past the next image's
    # start and so is too large. That is a size/channel misread worth its own look and is
    # not what this test is for.
    #
    # The test was written with the tighter assertion and is corrected here rather than
    # quietly widened: an assertion that holds only because the sample cannot reach a
    # counterexample is the same failure as a law that examined nothing.
    assert packed >= 0.9 * pairs, (
        'only %d of %d consecutive pairs pack -- well below the 96%% seen corpus-wide, '
        'so the offsets are no longer a uniform shift' % (packed, pairs))


def test_jpeg_bitmaps_decode_to_what_the_record_declares():
    """Class-word bit 11 marks a JPEG payload, and it must decode to the declared shape.

    This is the strongest check in this file, because the two sides know nothing about
    each other: the width, height and channel count come from the RECORD, and the actual
    dimensions come from decoding a JPEG stream found 52 bytes past the offset. A stream
    that is not this record's image would have to match all three by accident.

    It is also the check that matters most to get wrong quietly. Untreated, these bitmaps
    do not raise -- 8 of the 9 in the corpus read their compressed bytes as raw pixels and
    feed entropy-7.7 noise downstream without complaint.

    SKIPS when the corpus is absent.
    """
    import io
    paths = _paths()
    if not paths:
        print('SKIP: no corpus')
        return
    try:
        from PIL import Image
    except ImportError:
        print('SKIP: PIL not available')
        return
    flagged = matched = lengths = 0
    bad = []
    for f in paths:
        try:
            asm = Assembly(f)
        except Exception:
            continue
        for rec, bm in _jpeg_bitmaps(asm):
            flagged += 1
            p = bm['data_offset']
            if asm.data[p:p + 3] != b'\xff\xd8\xff':
                bad.append('%s: no JPEG stream at +52' % os.path.basename(f))
                continue
            # The u32 ahead of the SOI is the stream length; check it against the actual
            # SOI..EOI extent, which is the independent half of this.
            n = struct.unpack_from('<I', asm.data, p - 4)[0]
            end = asm.data.find(b'\xff\xd9', p)
            if end > 0 and end + 2 - p == n:
                lengths += 1
            try:
                im = Image.open(io.BytesIO(asm.data[p:p + n]))
                im.load()
            except Exception as e:
                bad.append('%s: will not decode (%s)' % (os.path.basename(f), e))
                continue
            got = {'L': 1, 'RGB': 3, 'RGBA': 4}.get(im.mode)
            # Channels are checked only when the class word states them: cls 0x808 has no
            # CHANNELS entry and the JPEG is the only thing that knows.
            ok = (im.size[0], im.size[1]) == (rec.width, rec.height) \
                and (bm['channels'] is None or got == bm['channels'])
            if ok:
                matched += 1
            else:
                bad.append('%s: decodes %r/%s, record declares %r'
                           % (os.path.basename(f), im.size, im.mode, 
                              (rec.width, rec.height, bm['channels'])))
    if not flagged:
        print('SKIP: no JPEG-flagged bitmaps in this slice of the corpus')
        return
    print('    %d of %d JPEG-flagged bitmaps decode to the declared shape, '
          '%d have the length at +48' % (matched, flagged, lengths))
    assert matched == flagged, 'JPEG bitmaps that do not match their record: %r' % (bad,)


def test_the_images_tile_the_resource_segment_exactly():
    """max(offset + size) == resource_end, which is what a 48-byte shift CANNOT survive.

    THE ONLY CHECK IN THIS FILE THAT CAN TELL +52 FROM +4. The other three are invariant
    to a uniform shift or to a shift that is 0 mod 8, and 52 - 4 == 48 is both, which is
    how the `+4` reading survived here for as long as it did. `resource_end` is
    `header['dir_at']`, taken from the file header and not from any bitmap record, so a
    bitmap offset landing on it is a closure and not a restatement.

    Measured over the whole corpus, both columns exceptionless:

        max(offset + size) - resource_end     at +52     0    111 of 111
                                              at +4    -48    111 of 111

    RAW PAYLOADS ONLY. A JPEG record's `size` is the UNCOMPRESSED size, so it does not
    describe a byte extent and cannot be summed with the others.

    **WHICH FILES ARE IN THE POPULATION IS CHOSEN SHIFT-INVARIANTLY, and the first draft
    of this test got that wrong in the one way that matters.** It selected on
    `min(offset) == 0x38` and then asserted the far end -- so under the `+4` skew it is
    trying to catch, every file failed the selector, the population was empty and the test
    SKIPPED. It reported success either way, which is the `c0d7774` failure in miniature.
    The selector is now `max(offset + size) - min(offset) == resource_end - 0x38`: the
    images span exactly the segment's LENGTH, which a uniform shift cannot change. Five
    specimens fail it because they carry images no record points at -- the same gaps
    `test_the_images_still_pack_back_to_back` records -- and there the last record's image
    is not the last image, so the endpoints say nothing.

    Both endpoints are then asserted, and 48 is called out by name because it is the one
    wrong answer with a history.
    """
    paths = _paths()
    if not paths:
        print('SKIP: no corpus')
        return
    tiling = exact = shifted = 0
    bad = []
    for f in paths:
        try:
            asm = Assembly(f)
        except Exception:
            continue
        if not asm.resource_end:
            continue
        spans = [(bm['offset'], bm['size']) for _r, bm in _pixel_bitmaps(asm)]
        if not spans:
            continue
        lo = min(o for o, _s in spans)
        hi = max(o + s for o, s in spans)
        if hi - lo != asm.resource_end - 0x38:          # shift-invariant selector
            continue
        tiling += 1
        if lo == 0x38 and hi == asm.resource_end:
            exact += 1
        else:
            shifted += 1
            bad.append('%s: images at [%d, %d), segment [%d, %d)'
                       % (os.path.basename(f), lo, hi, 0x38, asm.resource_end))
    if not tiling:
        print('SKIP: no file whose images span the resource segment')
        return
    print('    %d of %d files whose images span the segment land on both of its ends'
          % (exact, tiling))
    assert shifted == 0, (
        '%d files span the right LENGTH at the wrong PLACE -- if the offset is 0x38-48=8 '
        'the bitmap pointer skew has gone back to +4: %r' % (shifted, bad[:6]))


if __name__ == '__main__':
    for fn in (test_the_pixel_header_is_eight_bytes,
               test_rgba_alpha_lands_in_the_last_channel,
               test_the_images_still_pack_back_to_back,
               test_the_images_tile_the_resource_segment_exactly,
               test_jpeg_bitmaps_decode_to_what_the_record_declares):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        out = buf.getvalue()
        sys.stdout.write(out)
        print('%-52s %s' % (fn.__name__, 'skipped' if 'SKIP' in out else 'ok'))
