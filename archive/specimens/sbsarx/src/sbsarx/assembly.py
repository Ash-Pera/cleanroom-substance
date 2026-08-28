"""The `.sbsasm` container: header, record directory, record tags.

Only the parts a resource reader needs are implemented here. The full description of
the format is in FORMAT-NOTES.md in the parent project; section names are cited at the
facts they establish.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"SBAM"

#: Every offset in the format is stored relative to file position 52, without exception:
#: the value-table pointer, the trailer, the record directory and the resource table.
#: ("The resource table uses the same +52 skew")
SKEW = 52

#: The body begins here; a resource segment, when present, starts at this offset.
BODY = 0x38


class NotAnAssembly(ValueError):
    pass


@dataclass(frozen=True)
class Assembly:
    """A parsed `.sbsasm` buffer."""

    data: bytes
    version: int
    uid: int
    declared_size: int
    record_offsets: tuple[int, ...]
    directory_offset: int
    table_start: int

    @property
    def size_ok(self) -> bool:
        """Header field 0x10 is the total file size — an exact match in every specimen."""
        return self.declared_size == len(self.data)

    @property
    def body_start(self) -> int:
        """Where the record body begins."""
        return min(self.record_offsets) if self.record_offsets else len(self.data)

    @property
    def segment_end(self) -> int:
        """Where a resource segment, if there is one, ends.

        The layout is header, resource segment, record directory, record body. The
        directory sits immediately ahead of the body, so it is the directory -- not the
        first record -- that bounds the segment. Taking the first record instead counts
        the directory as unexplained segment bytes, and invents a segment entirely for
        the many packages whose directory starts at the top of the body at 0x38.
        """
        return self.directory_offset

    @property
    def has_segment(self) -> bool:
        return self.segment_end > BODY

    def record_tag(self, offset: int) -> int | None:
        if offset + 8 > len(self.data):
            return None
        return struct.unpack_from("<I", self.data, offset)[0]


def _footer_ok(data: bytes, off: int) -> tuple[int, int, int] | None:
    """The footer is (count, dir_ref, dir_ref + 4*count, table_start - 52).

    The arithmetic relation between the second and third words is what identifies it;
    it is vanishingly unlikely to hold by chance.
    """
    n = len(data)
    if off < BODY or off + 16 > n or off & 3:
        return None
    count, dir_ref, dir_end, back = struct.unpack_from("<IIII", data, off)
    if count == 0 or count > n // 4:
        return None
    if dir_end != dir_ref + 4 * count:
        return None
    if not 0 < back < off:
        return None
    dir_at = dir_ref - 4 + BODY
    if dir_at < 0 or dir_at + 4 * count > n:
        return None
    return count, dir_at, back + SKEW


def parse(data: bytes) -> Assembly:
    """Parse the header and record directory of a `.sbsasm` buffer."""
    if data[:4] != MAGIC:
        raise NotAnAssembly("missing SBAM magic")
    version, uid_lo, uid_hi, declared = struct.unpack_from("<IIII", data, 4)

    # The footer is the last sixteen bytes of the file in 435 of 435 specimens. The
    # whole-file scan this used to need is answering a question the layout settles.
    found = _footer_ok(data, len(data) - 16)
    if found is None:
        found = _scan_for_footer(data)
    if found is None:
        raise NotAnAssembly("no record-directory footer found")
    count, dir_at, table_start = found

    offsets = struct.unpack_from("<%dI" % count, data, dir_at)
    return Assembly(
        data=data,
        version=version,
        uid=uid_lo | (uid_hi << 32),
        declared_size=declared,
        record_offsets=tuple(sorted(o + SKEW for o in offsets)),
        directory_offset=dir_at,
        table_start=table_start,
    )


def _scan_for_footer(data: bytes):
    """Fallback for a file that does not put its footer last. Never runs in practice."""
    for off in range(BODY, len(data) - 16, 4):
        hit = _footer_ok(data, off)
        if hit is not None:
            return hit
    return None


def load(path) -> Assembly:
    with open(path, "rb") as fh:
        return parse(fh.read())
