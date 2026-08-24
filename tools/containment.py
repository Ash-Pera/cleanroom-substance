#!/usr/bin/env python3
"""Identify a filter id by CONTAINMENT, with the control that makes it evidence.

A source `.sbs` declares parameter values on named nodes (`levels`, `transformation`, ...).
The compiled binary stores those same values in records of one filter id. So a distinctive
value declared on a `levels` node, found again in a filter-15 record of that file's own
binary, is evidence that filter 15 is `levels` -- provided the same procedure does NOT put
every other filter's values there too. That proviso is the whole test; without it a large
filter wins by being large.

WHY THIS EXISTS. The published identification of `levels` (and `warp`, `blur`, `gradient`,
`fxmaps`) rested on exact-count matching over "instance-free" specimens, and every specimen
it names is Allegorithmic-authored -- source-excluded by the provenance rule (see
tools/provenance.py). Count-exact cannot be re-run clean: no PERMITTED instance-free
specimen in the corpus contains a `levels` node at all. Containment can, because it needs
only a permitted source that declares a distinctive value, not a whole instance-free graph.

WHAT COUNTS AS DISTINCTIVE. Round numbers -- 0, 0.5, 0.25, 1.0 -- occur in every filter and
discriminate nothing, so both the targets and the control drop them; a value qualifies only
with >= 5 decimal digits. Values a single file declares on two different source filters are
dropped as well, since they cannot separate the two.

READ THE CONTROL, NOT THE HEADLINE. `blend` scores 52% here: its declared opacities are
shallow decimals that recur across the corpus, and `blend` is the commonest filter. That is
the method failing honestly on a case it cannot resolve, and it is the reason the diagonal
is reported next to the off-diagonal rather than alone.
"""
import collections
import glob
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from provenance import paired_sources, matches, EXCLUDED_AUTHORS, FLAGGED_AUTHORS
from sbsasm import Assembly, FILTERS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NODE = re.compile(r'<compNode>((?:(?!</compNode>).)*?)</compNode>', re.S)
# `.sbs` serialises a value TWO ways -- as a direct attribute (`<x v="1"/>`) and nested
# (`<x><value v="1"/></x>`) -- a fact tools/pixelgraph.py's docstring already records. An
# earlier version of this file matched only the direct form, which made 23 of 92 permitted
# specimens (25%) contribute nothing and reported `fxmaps` as declaring zero values when
# every FX-Map parameter it declares uses the nested form. Both are matched here.
PARAM = re.compile(r'<constantValueFloat[1234](?: v="([^"]+)"/>'
                   r'|><value v="([^"]+)"/></constantValueFloat[1234]>)')
FILT = re.compile(r'<filter v="([^"]+)"/>')

DEFAULT_FILTERS = ["levels", "fxmaps", "blend", "transformation", "directionalwarp", "warp",
                   "blur", "gradient", "uniform", "curve", "hsl", "sharpen", "normal"]

MIN_DECIMALS = 5


def distinctive(v):
    if not (0.0 < abs(v) < 1000.0):
        return False
    s = "%.9g" % v
    return '.' in s and len(s.split('.')[-1]) >= MIN_DECIMALS


def f32(v):
    """Round-trip through float32, the width the binary stores."""
    return round(struct.unpack('<f', struct.pack('<f', v))[0], 6)


def declared(sbs_text, wanted):
    """{source filter name: set of distinctive declared values}"""
    out = collections.defaultdict(set)
    for body in NODE.findall(sbs_text):
        m = FILT.search(body)
        if not m or m.group(1) not in wanted:
            continue
        for direct, nested in PARAM.findall(body):
            for tok in (direct or nested).split():
                try:
                    v = float(tok)
                except ValueError:
                    continue
                if distinctive(v):
                    out[m.group(1)].add(f32(v))
    return out


def sbsasm_for(sbs_path):
    stem = os.path.basename(sbs_path)[:-4]
    hits = glob.glob(os.path.join(os.path.dirname(sbs_path), "x_" + stem,
                                  "assemblies", "content", "*", "*.sbsasm"))
    return hits[0] if hits else None


def record_floats(rec):
    """Every slot of a record read as float32, distinctive values only.

    Reads raw slots rather than `Record.named_parameters` on purpose: the point is to find
    where a value LANDS without assuming the parameter layout that is itself derived from
    these identifications.
    """
    out = set()
    for w in rec.words:
        v = struct.unpack('<f', struct.pack('<I', w & 0xFFFFFFFF))[0]
        if v == v and distinctive(v):
            out.add(round(v, 6))
    return out


def confusion(wanted=None, permitted_only=True):
    """(matrix, totals, n_files): where each source filter's declared values were found."""
    wanted = wanted or DEFAULT_FILTERS
    matrix = collections.defaultdict(collections.Counter)
    totals = collections.Counter()
    n_files = 0
    for p in paired_sources():
        if permitted_only and (matches(p, EXCLUDED_AUTHORS) or matches(p, FLAGGED_AUTHORS)):
            continue
        data = open(p, encoding='utf-8', errors='replace').read()
        decl = declared(data, wanted)
        if not decl:
            continue
        asmf = sbsasm_for(p)
        if not asmf:
            continue
        try:
            asm = Assembly(asmf)
        except Exception:
            continue
        n_files += 1
        by_fid = collections.defaultdict(set)
        for rec in asm.records:
            if rec.filter_id is None:
                continue
            by_fid[rec.filter_id] |= record_floats(rec)
        seen = collections.Counter()
        for vals in decl.values():
            for v in vals:
                seen[v] += 1
        for srcname, vals in decl.items():
            uniq = {v for v in vals if seen[v] == 1}
            totals[srcname] += len(uniq)
            for fid, bvals in by_fid.items():
                n = len(uniq & bvals)
                if n:
                    matrix[srcname][FILTERS.get(fid, "fid%d" % fid)] += n
    return matrix, totals, n_files


if __name__ == '__main__':
    matrix, totals, n_files = confusion()
    print("Containment identification, PERMITTED sources only (%d specimens)\n" % n_files)
    print("  row = filter the value was declared on in the .sbs source")
    print("  col = filter of the compiled record the value was found in\n")
    print("  %-16s %8s %7s %10s   %s" % ("declared on", "targets", "found", "on-target",
                                          "where found"))
    for src in DEFAULT_FILTERS:
        if not totals.get(src):
            continue
        row = matrix[src]
        tot = sum(row.values())
        diag = row.get(src, 0)
        cells = ", ".join("%s=%d" % (k, v) for k, v in row.most_common(4))
        print("  %-16s %8d %7d %6d %5.1f%%   %s"
              % (src, totals[src], tot, diag, (100.0 * diag / tot) if tot else 0.0, cells))
