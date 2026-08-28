#!/usr/bin/env python3
"""Correct bounds for the instruction stream.

The naive span [first directory entry, last directory entry] INCLUDES the resource
table, whose records embed instructions. Counting those as code inflates opcode
statistics and, in small files, dominates them. This module returns the code span with
the resource table excised.
"""
import struct

import extract_images as E
import standalone_parse as S


def code_spans(path):
    """Return (data, [(lo, hi), ...]) - the instruction stream, resource table removed."""
    d = open(path, "rb").read()
    r = S.parse(path)
    cnt, dir0 = r["dir_count"], r["dir_at"]
    if cnt < 1 or dir0 + 4 * cnt > len(d):   # small graphs legitimately have 1-2 records
        return d, [], r
    ents = list(struct.unpack_from("<%dI" % cnt, d, dir0))
    # The body runs from just after the directory to the value table. Directory entries
    # are NOT absolute (they carry the +52 skew), so ents[0] is not a code offset -- using
    # it as one put `lo` inside the header and, combined with the resource-table excision,
    # emptied the span for small files.
    lo, hi = dir0 + 4 * cnt, r["table_start"]
    if hi <= lo:
        return d, [], r

    base = dir0 - 0x38
    res_lo = res_hi = None
    if base > 0:
        addrs = []
        a = dir0
        while a + 8 <= r["table_start"]:
            tag, off = struct.unpack_from("<II", d, a)
            if E.valid_tag(tag) and 0 < off <= base + 4:
                addrs.append(a)
            a += 4
        if addrs:
            stride = (addrs[1] - addrs[0]) if len(addrs) > 1 else 8
            res_lo, res_hi = addrs[0], addrs[-1] + max(stride, 8)

    if res_lo is None or res_hi <= lo or res_lo >= hi:
        return d, [(lo, hi)], r
    spans = []
    if res_lo > lo:
        spans.append((lo, res_lo))
    if res_hi < hi:
        spans.append((res_hi, hi))
    return d, spans, r
