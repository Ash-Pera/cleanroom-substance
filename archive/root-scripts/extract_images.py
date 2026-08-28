#!/usr/bin/env python3
"""Extract embedded bitmaps from a .sbsasm resource segment.

The pixel format is NOT inferred - it is read from a resource table the file carries.
Just before the interface block sits one 8-byte record per embedded image:

    u32 format_tag, u32 offset_into_segment

The tag decodes as four bytes (little-endian):

    byte[3]  format   0x01=L  0x02=RGB  0x03=RGBA  0x05=L16  0x07=RGBA16
    byte[2]  depth    0x08 = 8 bits per channel, 0x18 = 16 bits per channel
    byte[1]  0xAA     constant marker - this is what makes the table findable
    byte[0]  0x20 = grayscale, 0x21 = colour

Consecutive offsets give each image's byte size; the final image runs to the end of
the segment. Across the corpus these sizes sum to the segment length exactly, in
every file where the table is present.

Pixel dimensions are not stored, but follow from size / bytes-per-pixel assuming a
square image, which holds for every case checked against rendered output.

Usage: python3 extract_images.py FILE.sbsasm [outdir]
"""
import math
import os
import struct
import sys

import standalone_parse as S

# format code -> (bytes per pixel, PIL mode, human name)
FORMATS = {
    0x01: (1, "L", "L8"),
    0x02: (3, "RGB", "RGB8"),
    0x03: (4, "RGBA", "RGBA8"),
    0x05: (2, "I;16", "L16"),
    0x07: (8, "RGBA16", "RGBA16"),
}


def valid_tag(tag):
    """A resource tag is 0xAA in byte 1, a known format in byte 3, a known depth in
    byte 2, and a grayscale/colour flag in byte 0. Requiring all four rejects float
    bit patterns, which otherwise match the 0xAA marker alone."""
    return (((tag >> 8) & 0xFF) == 0xAA
            and ((tag >> 24) & 0xFF) in FORMATS
            and ((tag >> 16) & 0xFF) in (0x08, 0x18)
            and (tag & 0xFF) in (0x20, 0x21))


def find_table(d, r, segment=None):
    """All valid (tag, offset) records between the directory and the interface block.

    Record spacing is NOT constant - it is 8 bytes in some files and 32 in others - so
    the region is scanned for valid tags rather than walked at a fixed stride. Results
    are sorted by offset and deduplicated.
    """
    out = {}
    a, hi = r["dir_at"], r["table_start"] - 8
    while a <= hi:
        tag, off = struct.unpack_from("<II", d, a)
        if valid_tag(tag) and (segment is None or 0 < off <= segment + 4):
            out.setdefault(off, tag)
        a += 4
    return [(out[o], o) for o in sorted(out)]


def describe(path):
    d = open(path, "rb").read()
    r = S.parse(path)
    base = r["dir_at"] - 0x38
    if base <= 0:
        return {"segment": 0, "images": []}
    tbl = find_table(d, r, base)
    if not tbl:
        return {"segment": base, "images": []}
    imgs = []
    for i, (tag, off) in enumerate(tbl):
        end = tbl[i + 1][1] if i + 1 < len(tbl) else base + tbl[0][1]
        size = end - off
        code = (tag >> 24) & 0xFF
        bpp, mode, name = FORMATS.get(code, (None, None, f"unknown({code:#04x})"))
        w = h = None
        if bpp and size % bpp == 0:
            px = size // bpp
            s = int(math.isqrt(px))
            if s * s == px:
                w = h = s
        imgs.append(dict(index=i, tag=tag, offset=off, size=size, code=code,
                         bpp=bpp, mode=mode, format=name, w=w, h=h,
                         gray=(tag & 0xFF) == 0x20,
                         depth=16 if ((tag >> 16) & 0xFF) == 0x18 else 8))
    return {"segment": base, "images": imgs,
            "sums": sum(i["size"] for i in imgs) == base}


def extract(path, outdir):
    from PIL import Image
    d = open(path, "rb").read()
    info = describe(path)
    if not info.get("images"):
        return info
    r = S.parse(path)
    seg = d[0x38:0x38 + info["segment"]]
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    for im in info["images"]:
        if not (im["w"] and im["mode"]):
            im["file"] = None
            continue
        raw = seg[im["offset"] - 4:im["offset"] - 4 + im["size"]]
        if len(raw) < im["size"]:
            im["file"] = None
            continue
        p = os.path.join(outdir, f"{stem}_{im['index']}_{im['w']}x{im['h']}_{im['format']}.png")
        if im["mode"] == "RGBA16":
            # PIL has no 16-bit-per-channel RGBA loader; take the high byte of each
            import numpy as _np
            a = _np.frombuffer(raw, dtype="<u2").reshape(im["h"], im["w"], 4)
            Image.fromarray((a >> 8).astype("uint8"), "RGBA").save(p)
        elif im["mode"] == "I;16":
            import numpy as _np
            a = _np.frombuffer(raw, dtype="<u2").reshape(im["h"], im["w"])
            Image.fromarray((a >> 8).astype("uint8"), "L").save(p)
        else:
            Image.frombytes(im["mode"], (im["w"], im["h"]), raw).save(p)
        im["file"] = p
    return info


if __name__ == "__main__":
    out = (extract(sys.argv[1], sys.argv[2]) if len(sys.argv) > 2
           else describe(sys.argv[1]))
    print(f"segment {out['segment']} bytes, sizes sum exactly: {out.get('sums')}")
    for im in out.get("images", []):
        dim = f"{im['w']}x{im['h']}" if im["w"] else "dims unresolved"
        print(f"  [{im['index']}] {im['format']:<8} {dim:<12} {im['size']:>9} bytes "
              f"{'gray' if im['gray'] else 'colour'} {im['depth']}-bit  {im.get('file') or ''}")
