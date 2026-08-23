#!/usr/bin/env python3
"""Locate resource boundaries inside table-less segments.

No table describes these regions, so boundaries must be recovered from the data. Pixel
data is smooth along its own stride, so the byte lag minimising mean absolute difference
gives bytes-per-pixel; a change in that lag marks a format change, and hence a boundary.
Boundaries between same-format resources do not show as a lag change and need the
discontinuity signal instead.
"""
import struct, collections

def stride(d, lo, hi, sample=8192):
    """best byte-lag (1..4) and its score for a region."""
    n = min(hi - lo - 8, sample)
    if n < 64:
        return None, 0.0
    best, bs = None, None
    for k in (1, 2, 3, 4):
        s = sum(abs(d[lo + i] - d[lo + i + k]) for i in range(0, n, 3)) / max(n // 3, 1)
        if bs is None or s < bs:
            best, bs = k, s
    return best, bs

def kind(d, lo, hi):
    """format label for a region."""
    n = hi - lo
    if n < 256:
        return '?'
    blk = d[lo:min(hi, lo + 16384)]
    if blk.count(0) > len(blk) * 0.95:
        return 'zeros'
    k, _ = stride(d, lo, hi)
    if k == 4:
        q = len(blk) // 4
        ff = sum(1 for i in range(3, len(blk), 4) if blk[i] == 0xFF) / max(q, 1)
        fe = sum(1 for i in range(3, len(blk), 4) if blk[i] in (0x3D, 0x3E, 0x3F)) / max(q, 1)
        if ff > 0.85: return 'RGBA8'
        if fe > 0.75: return 'f32'
        return '4byte'
    return {1: 'L8', 2: '16bit', 3: 'RGB8'}.get(k, '?')

def coarse_runs(d, lo, hi, blk=4096):
    """contiguous runs of one format label at `blk` granularity."""
    runs, cur, start = [], None, lo
    off = lo
    while off + blk <= hi:
        z = kind(d, off, off + blk)
        if z != cur:
            if cur is not None:
                runs.append([start, off, cur])
            cur, start = z, off
        off += blk
    if cur is not None:
        runs.append([start, hi, cur])
    return runs

def refine(d, runs, blk=4096):
    """binary-search each boundary down to 64-byte precision."""
    for i in range(len(runs) - 1):
        a, b = runs[i], runs[i + 1]
        lo, hi = max(a[0], b[0] - blk), b[0] + blk
        while hi - lo > 64:
            mid = (lo + hi) // 2 & ~63
            if mid <= lo or mid >= hi: break
            if kind(d, mid, min(mid + 2048, b[1])) == b[2]:
                hi = mid
            else:
                lo = mid
        a[1] = runs[i + 1][0] = hi
    return runs
