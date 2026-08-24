"""Embedded image resources.

A resource is described by an ordinary record whose tag decodes as a resource
descriptor. Descriptors are enumerated by the record directory, so they need not be
searched for: walk the directory and keep the entries whose tag decodes.

    [ u32 tag ][ u32 offset - 52 ]

    tag = NN << 16 | type

    byte[3]  NN high    pixel format, see FORMATS below
    byte[2]  NN low     bit depth     0x08 8-bit, 0x18 16-bit
    byte[1]  type high  declared resolution, packed as (log2 h << 4) | log2 w
    byte[0]  type low   2 * filter_id + is_colour; filter 16 is `bitmap`, so 0x20 / 0x21

Two things the field layout alone does not tell you, both measured against this corpus
and handled below:

*Several records may describe one image.* A resource shared by several `bitmap` nodes
gets a descriptor per node, all pointing at the same offset — 34 of them in one
specimen. Descriptors are therefore deduplicated by offset, and `references` records
how many records named each image.

*A descriptor does not always account for the gap to the next one.* Where the gap is a
whole multiple of the declared image size, the surplus holds further images that no
descriptor names. The declared geometry is still the right way to read the image that
descriptor points at -- decoding the whole span as one larger image splices several
images together, which is wrong and visible at a glance. The surplus is reported as
`slack` and counted by `segment_report` rather than guessed at.

Sources in FORMAT-NOTES.md: "Resource descriptors are ordinary records, and NN carries
the format", "The record type's high byte is the output resolution", "Format 8 is JPEG",
"The manifest's declared output size is a default, not the resource resolution".
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, replace

from .assembly import BODY, SKEW, Assembly

#: format code -> (name, channels, bytes per channel). JPEG carries its own geometry.
#: The code is `base + 4` when the channels are 16-bit, with base 1 L, 2 RGB, 3 RGBA.
#: FORMAT-NOTES.md lists every code but 6; RGB16 was found here, in GrassSubstance001,
#: and confirmed by decoding it -- a clean image, and the only reading of those bytes
#: that produces one.
FORMATS: dict[int, tuple[str, int, int]] = {
    1: ("L8", 1, 1),
    2: ("RGB8", 3, 1),
    3: ("RGBA8", 4, 1),
    5: ("L16", 1, 2),
    6: ("RGB16", 3, 2),
    7: ("RGBA16", 4, 2),
    8: ("JPEG", 0, 0),
}

#: The depth byte each format must carry. Agreement is 564 of 565 descriptors, so a
#: disagreement is evidence the tag is not a descriptor at all.
_DEPTH = {1: 0x08, 2: 0x08, 3: 0x08, 8: 0x08, 5: 0x18, 6: 0x18, 7: 0x18}

#: The grayscale/colour flag each format must carry. JPEG may be either.
_COLOUR = {1: 0x20, 5: 0x20, 2: 0x21, 3: 0x21, 6: 0x21, 7: 0x21}

_BITMAP_FILTER = 16
JPEG_SOI = b"\xff\xd8"
_SOF_MARKERS = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


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
    declared_width: int
    declared_height: int
    references: int = 1
    slack: int = 0
    geometry_known: bool = True

    @property
    def is_jpeg(self) -> bool:
        return self.format == "JPEG"

    @property
    def declared_geometry_differs(self) -> bool:
        """True when a JPEG's own SOF header disagrees with the descriptor's tag."""
        return (self.width, self.height) != (self.declared_width, self.declared_height)

    def __str__(self) -> str:
        geometry = "%dx%d" % (self.width, self.height) if self.geometry_known else "?x?"
        return "%-6s %s %s, %d bytes" % (
            self.format, geometry, "colour" if self.colour else "grayscale", self.size)


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


def jpeg_geometry(payload: bytes) -> tuple[int, int] | None:
    """Read width and height from a JPEG's own SOF header."""
    i = 2
    while i + 9 < len(payload):
        if payload[i] != 0xFF:
            return None
        marker = payload[i + 1]
        length = struct.unpack_from(">H", payload, i + 2)[0]
        if marker in _SOF_MARKERS:
            height, width = struct.unpack_from(">HH", payload, i + 5)
            return width, height
        i += 2 + length
    return None


def _candidates(asm: Assembly) -> list[tuple[int, int, int, int, int]]:
    """(offset, format code, resolution byte, colour byte, reference count)."""
    data, segment_end = asm.data, asm.segment_end
    seen: dict[int, list] = {}
    for record_offset in asm.record_offsets:
        tag = asm.record_tag(record_offset)
        if tag is None:
            continue
        decoded = decode_tag(tag)
        if decoded is None:
            continue
        fmt, _depth, resolution, colour_byte = decoded
        offset = struct.unpack_from("<I", data, record_offset + 4)[0] + SKEW
        if not BODY <= offset < segment_end:
            continue
        if offset in seen:
            seen[offset][-1] += 1
            continue
        seen[offset] = [offset, fmt, resolution, colour_byte, 1]
    return [tuple(v) for v in sorted(seen.values())]


def resources(asm: Assembly) -> list[Resource]:
    """Every embedded image the assembly describes, in segment order."""
    data, segment_end = asm.data, asm.segment_end
    found: list[Resource] = []

    candidates = _candidates(asm)
    for i, (offset, fmt, resolution, colour_byte, refs) in enumerate(candidates):
        name, channels, bpc = FORMATS[fmt]
        declared_w = 1 << (resolution & 0xF)
        declared_h = 1 << ((resolution >> 4) & 0xF)
        next_offset = candidates[i + 1][0] if i + 1 < len(candidates) else segment_end
        span = next_offset - offset
        if span <= 0:
            continue

        if fmt == 8:
            if offset + 6 > len(data) or data[offset + 4:offset + 6] != JPEG_SOI:
                continue
            size = struct.unpack_from("<I", data, offset)[0] + 4
            if size > span or offset + size > segment_end:
                continue
            geometry = jpeg_geometry(data[offset + 4:offset + size])
            width, height = geometry or (declared_w, declared_h)
            known = geometry is not None
            slack = span - size
        else:
            # The declared geometry is the stored geometry. Where the gap to the next
            # descriptor is larger, the surplus holds further images that no descriptor
            # names -- reading the span as one big image is wrong, and visibly so.
            size = declared_w * declared_h * channels * bpc
            width, height, known = declared_w, declared_h, size <= span
            if not known:
                size = span
            slack = span - size

        found.append(Resource(
            index=len(found), format=name, width=width, height=height,
            channels=channels or (3 if colour_byte & 1 else 1),
            depth=16 if fmt in (5, 6, 7) else 8, colour=bool(colour_byte & 1),
            offset=offset, size=size, declared_width=declared_w,
            declared_height=declared_h, references=refs, slack=slack,
            geometry_known=known,
        ))
    return found


def payload(asm: Assembly, res: Resource) -> bytes:
    """The resource's bytes: raw pixels, or the JPEG file with its length prefix removed."""
    blob = asm.data[res.offset:res.offset + res.size]
    return blob[4:] if res.is_jpeg else blob


def segment_report(asm: Assembly, found: list[Resource]) -> dict:
    """How completely the resources account for the segment at the head of the file.

    The segment runs from the start of the body to the first record. Resources that
    tile it exactly are the strongest available check on the decode: a single misparsed
    descriptor breaks the total.
    """
    end = asm.segment_end
    covered = sum(r.size for r in found)
    # Resources are 4-aligned, so a few bytes of padding between two of them is the
    # layout rather than an unexplained hole. More than that is a real gap, and an
    # overlap means a descriptor was misread.
    gaps = overlaps = 0
    for a, b in zip(found, found[1:]):
        slack = b.offset - (a.offset + a.size)
        if slack < 0:
            overlaps += 1
        elif slack > 3:
            gaps += 1
    tail = end - (found[-1].offset + found[-1].size) if found else 0
    undescribed = max(0, (end - BODY) - covered)
    return {
        "segment_start": BODY,
        "segment_end": end,
        "segment_bytes": max(0, end - BODY),
        "resources": len(found),
        "covered_bytes": covered,
        "starts_at_body": bool(found) and found[0].offset == BODY,
        "internal_gaps": gaps,
        "overlaps": overlaps,
        "trailing_bytes": max(0, tail),
        "undescribed_bytes": undescribed,
        "declared_geometry_differs": sum(
            1 for r in found if r.declared_geometry_differs),
        "geometry_unknown": sum(1 for r in found if not r.geometry_known),
        "tiles_exactly": (
            bool(found) and found[0].offset == BODY and gaps == 0 and overlaps == 0
        ),
    }
