"""Locate and extract the embedded bitmaps in a .sbsasm.

A bitmap record in its short (8-byte) form is:

    [u16 tag][u16 class][u32 resource offset]

    tag    low byte  = 2*filter_id + is_colour, filter_id 16
           high byte = (log2 height << 4) | log2 width
    class  bits 8-9  = channel layout   1 -> L, 2 -> RGB, 3 -> RGBA
           bit  10   = 16 bits per channel when set
           low byte  = 0x08 for 8-bit, 0x18 for 16-bit (redundant with bit 10)

The pixel data lives at `resource offset` in the resource segment at the head of the file.
It is raw and uncompressed: width * height * channels * bytes_per_channel bytes, no
mipmaps, no padding between images.

Verified over the corpus: the class word determines bytes-per-pixel with no exceptions,
and no resource ever overruns the record region.
"""
import struct
import standalone_parse as S
import sbsasm

CHANNELS = {1: 1, 2: 3, 3: 4}

#: format code -> (name, channels, bytes per channel). The code is a base - 1 for L,
#: 2 for RGB, 3 for RGBA - plus 0 for 8-bit, 4 for 16-bit, or 32 for 32-bit float,
#: and the class low byte repeats the depth as 0x08 / 0x18 / 0x38. Inferred bytes per
#: pixel agrees with this table in 100% of samples for every code below.
#: Code 8 is JPEG, which carries its own geometry and a 4-byte length prefix.
FORMATS = {
    1:  ('L8',      1, 1),   2:  ('RGB8',    3, 1),   3:  ('RGBA8',   4, 1),
    5:  ('L16',     1, 2),   6:  ('RGB16',   3, 2),   7:  ('RGBA16',  4, 2),
    33: ('L32F',    1, 4),   34: ('RGB32F',  3, 4),   35: ('RGBA32F', 4, 4),
    8:  ('JPEG',    0, 0),
}
JPEG_SOI = b'\xff\xd8'


def pixel_format(cls):
    """(channels, bytes_per_channel) for a bitmap record's class word, or None.

    Returns (0, 0) for JPEG, whose size is not computable from the geometry.
    """
    f = FORMATS.get((cls >> 8) & 0xFF)
    return (f[1], f[2]) if f else None


def format_name(cls):
    f = FORMATS.get((cls >> 8) & 0xFF)
    return f[0] if f else None


def bitmaps(path):
    """Yield one dict per embedded bitmap: offset, width, height, channels, depth, size.

    THROUGH `sbsasm.Record.bitmap`, not through a second directory walk of its own. This
    module used to re-derive the record directory from the raw bytes and decide pixels vs
    graph input by RECORD LENGTH -- 8 bytes meant stored pixels, longer meant a named
    input. `Record.bitmap`'s docstring records that reading as measured and wrong: a third
    of short records name a graph input too, and the discriminator is whether slot 1 can
    be a file offset at all (>= file size -> a uid, 157 of 157; < file size -> pixels,
    306 of 306). Against this module, that cost 75 graph inputs over 60 specimens, 0
    gained.

    It also lacked the offset correction the model carries. The pixel region begins at 8,
    after an eight-byte magic-plus-version header, while every record declares an offset
    four bytes short of its data -- invisible at depth 8 with 4 channels, where four bytes
    is exactly one pixel, and a channel rotation everywhere else. Reading `b['offset']`
    takes that fix rather than repeating the bug.
    """
    asm = sbsasm.Assembly(path)
    d = asm.data
    for r in asm.records:
        if r.filter_id != 16:
            continue
        b = r.bitmap
        if not b or b['kind'] != 'pixels':
            continue
        name = format_name(r.cls)
        pos = b['offset'] + 52              # the model's offset, already +4 corrected
        row = {'record': r.index, 'offset': pos, 'width': r.width, 'height': r.height,
               'channels': b.get('channels'), 'depth': b.get('depth'), 'format': name}
        if b.get('compressed') == 'jpeg':
            # [u32 length][stream]; the model's offset points AT the stream, so the
            # length word is the four bytes in front of it.
            if pos < 4 or pos + 2 > len(d):
                continue
            size = struct.unpack_from('<I', d, pos - 4)[0]
            if size <= 0 or pos + size > len(d) or d[pos:pos + 2] != JPEG_SOI:
                continue
            row.update(format=name or 'JPEG', size=size,
                       data=memoryview(d)[pos:pos + size])
            yield row
            continue
        size = b.get('size')
        if not size or pos + size > len(d):
            continue
        row.update(size=size, data=memoryview(d)[pos:pos + size])
        yield row


if __name__ == '__main__':
    import sys
    for b in bitmaps(sys.argv[1]):
        print('record %-5d %5dx%-5d %-8s offset %-10d %d bytes'
              % (b['record'], b['width'], b['height'], b['format'],
                 b['offset'], b['size']))


def graph_inputs(path):
    """Yield the graph image inputs -- bitmap records naming a uid rather than pixels.

    Was "records in their long (>= 20 byte) form", which is the length discriminator
    `Record.bitmap` measured as wrong; see `bitmaps` above. Asking the model instead finds
    the short-form inputs this missed: 293 against 218 over 60 specimens, none lost.
    """
    asm = sbsasm.Assembly(path)
    for r in asm.records:
        if r.filter_id != 16:
            continue
        b = r.bitmap
        if not b or b['kind'] != 'graph_input':
            continue
        yield {'record': r.index, 'uid': b['uid'],
               'width': r.width, 'height': r.height, 'colour': bool(r.colour)}



def strings(path, limit=4096):
    """Yield the text strings a package embeds, in resource-segment order.

    The `text` filter's strings are stored at the head of the resource segment, before
    the images, as a run of length-prefixed UTF-32:

        [u32 character count][u32 per character] ...

    Verified over the corpus: every file whose segment begins this way contains
    `text` records, and no file without them does. The strings are the rendered
    content - "STOP", "YIELD", "ONE WAY".
    """
    d = open(path, 'rb').read()
    q, hi = 0x38, len(d)
    while q + 4 <= hi:
        n = struct.unpack_from('<I', d, q)[0]
        if not (1 <= n <= limit) or q + 4 + 4 * n > hi:
            return
        chars = struct.unpack_from('<%dI' % n, d, q + 4)
        if not all(9 <= c < 0x110000 for c in chars):
            return
        yield ''.join(chr(c) for c in chars)
        q += 4 + 4 * n
