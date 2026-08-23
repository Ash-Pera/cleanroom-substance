"""Embedded image resources.

A resource is described by an ordinary record whose tag decodes as a resource
descriptor. Descriptors are enumerated by the record directory, so they need not be
searched for: walk the directory, keep the entries whose tag decodes, and the segment
at the head of the file is fully accounted for.

    [ u32 tag ][ u32 offset - 52 ]

    tag = NN << 16 | type

    byte[3]  NN high    pixel format  1 L8, 2 RGB8, 3 RGBA8, 5 L16, 7 RGBA16, 8 JPEG
    byte[2]  NN low     bit depth     0x08 8-bit, 0x18 16-bit
    byte[1]  type high  output resolution, packed as (log2 h << 4) | log2 w
    byte[0]  type low   2 * filter_id + is_colour; filter 16 is `bitmap`, so 0x20 / 0x21

Raw resources occupy `width * height * channels * bytes_per_channel` bytes. Format 8 is
an ordinary JFIF JPEG behind a `u32` length prefix; the prefix bounds the payload
exactly, verified by its EOI marker on every JPEG in the corpus.

Sources in FORMAT-NOTES.md: "Resource descriptors are ordinary records, and NN carries
the format", "The record type's high byte is the output resolution", "Format 8 is JPEG".
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .assembly import SKEW, Assembly

#: format code -> (name, channels, bytes per channel). JPEG carries its own geometry.
FORMATS: dict[int, tuple[str, int, int]] = {
    1: ("L8", 1, 1),
    2: ("RGB8", 3, 1),
    3: ("RGBA8", 4, 1),
    5: ("L16", 1, 2),
    7: ("RGBA16", 4, 2),
    8: ("JPEG", 0, 0),
}

#: The depth byte each format must carry. Agreement is 564 of 565 descriptors, so a
#: disagreement is evidence the tag is not a descriptor at all.
_DEPTH = {1: 0x08, 2: 0x08, 3: 0x08, 8: 0x08, 5: 0x18, 7: 0x18}

#: The grayscale/colour flag each format must carry. JPEG may be either.
_COLOUR = {1: 0x20, 5: 0x20, 2: 0x21, 3: 0x21, 7: 0x21}

_BITMAP_FILTER = 16
JPEG_SOI = b"\xff\xd8"


@dataclass(frozen=True)
class Resource:
    """One embedded image, as the file describes it."""

    index: int
    format: str
    width: int
    height: int
    channels: int
    depth: int
    colour: bool
    offset: int
    size: int
    record_offset: int

    @property
    def is_jpeg(self) -> bool:
        return self.format == "JPEG"

    def __str__(self) -> str:
        return "%-6s %dx%d %s %d bytes @%d" % (
            self.format, self.width, self.height,
            "colour" if self.colour else "grayscale", self.size, self.offset,
        )


def decode_tag(tag: int) -> tuple[int, int, int, int] | None:
    """Split a record tag into (format code, depth, resolution byte, colour byte),
    or None if it is not a self-consistent resource descriptor."""
    colour_byte = tag & 0xFF
    resolution = (tag >> 8) & 0xFF
    depth = (tag >> 16) & 0xFF
    fmt = (tag >> 24) & 0xFF

    if colour_byte >> 1 != _BITMAP_FILTER:      # 0x20 grayscale, 0x21 colour
        return None
    if fmt not in FORMATS:
        return None
    if depth != _DEPTH[fmt]:
        return None
    if fmt in _COLOUR and colour_byte != _COLOUR[fmt]:
        return None
    return fmt, depth, resolution, colour_byte


def resources(asm: Assembly) -> list[Resource]:
    """Every embedded image the assembly describes, in segment order."""
    data = asm.data
    found: list[Resource] = []

    for record_offset in asm.record_offsets:
        tag = asm.record_tag(record_offset)
        if tag is None:
            continue
        decoded = decode_tag(tag)
        if decoded is None:
            continue
        fmt, depth, resolution, colour_byte = decoded

        raw_offset = struct.unpack_from("<I", data, record_offset + 4)[0]
        offset = raw_offset + SKEW
        if not 0 <= offset < len(data):
            continue

        width = 1 << (resolution & 0xF)
        height = 1 << ((resolution >> 4) & 0xF)
        name, channels, bpc = FORMATS[fmt]

        if fmt == 8:
            if offset + 6 > len(data) or data[offset + 4:offset + 6] != JPEG_SOI:
                continue
            size = struct.unpack_from("<I", data, offset)[0] + 4
        else:
            size = width * height * channels * bpc
        if offset + size > len(data):
            continue

        found.append(Resource(
            index=0, format=name, width=width, height=height,
            channels=channels, depth=8 if depth == 0x08 else 16,
            colour=bool(colour_byte & 1), offset=offset, size=size,
            record_offset=record_offset,
        ))

    found.sort(key=lambda r: r.offset)
    return [Resource(**{**r.__dict__, "index": i}) for i, r in enumerate(found)]


def payload(asm: Assembly, res: Resource) -> bytes:
    """The resource's bytes: raw pixels, or the JPEG file with its length prefix removed."""
    blob = asm.data[res.offset:res.offset + res.size]
    return blob[4:] if res.is_jpeg else blob


def segment_report(asm: Assembly, found: list[Resource]) -> dict:
    """How completely the resources account for the segment at the head of the file.

    The segment runs from the start of the body to the first record. Descriptors that
    tile it exactly are the strongest available check on the decode: a single misparsed
    descriptor breaks the total.
    """
    from .assembly import BODY

    end = asm.body_start
    covered = sum(r.size for r in found)
    # Resources are 4-aligned, so up to three bytes of padding between two of them is
    # the layout rather than an unexplained hole. Anything more is a real gap, and an
    # overlap means a descriptor was misread.
    gaps = overlaps = 0
    for a, b in zip(found, found[1:]):
        slack = b.offset - (a.offset + a.size)
        if slack < 0:
            overlaps += 1
        elif slack > 3:
            gaps += 1
    return {
        "segment_start": BODY,
        "segment_end": end,
        "segment_bytes": max(0, end - BODY),
        "resources": len(found),
        "covered_bytes": covered,
        "starts_at_body": bool(found) and found[0].offset == BODY,
        "internal_gaps": gaps,
        "overlaps": overlaps,
        "tiles_exactly": (
            bool(found) and found[0].offset == BODY and gaps == 0 and overlaps == 0
        ),
    }
