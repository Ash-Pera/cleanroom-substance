#!/usr/bin/env python3
"""Structural probe for Substance .sbsasm files (the compiled graph inside a .sbsar).

Usage:
    python3 sbsasm_probe.py FILE.sbsasm [FILE2.sbsasm ...]
    python3 sbsasm_probe.py --sbsar FILE.sbsar     # extract + probe in one step

Reports only what is directly verifiable from the bytes. Fields whose meaning is
still a guess are labelled as such.
"""
import argparse
import collections
import glob
import math
import os
import struct
import subprocess
import sys
import tempfile

HEADER_FMT = "<4sIQIIIIIIIII"  # through 0x34
HEADER_SIZE = 0x38


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def probe(path):
    d = open(path, "rb").read()
    n = len(d)
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]

    print(f"\n{'=' * 70}\n{os.path.basename(path)}  size={n} (0x{n:X})\n{'=' * 70}")

    if d[:4] != b"SBAM":
        print(f"  !! not an sbsasm: magic={d[:4]!r}")
        return

    # ---- fixed header ------------------------------------------------
    print("  [header]")
    print(f"    0x00 magic        {d[:4].decode()}")
    print(f"    0x04 version      0x{u32(4):08X}")
    print(f"    0x08 uid          {d[8:16].hex()}")
    print(f"    0x10 total_size   {u32(0x10)}  (matches file: {u32(0x10) == n})")
    for off, note in (
        (0x14, "const 0x1C in all samples"),
        (0x18, "const 0"),
        (0x1C, "ptr: size-28 -> trailer"),
        (0x20, "const 0x00010002"),
        (0x24, "const 0"),
        (0x28, "const 1"),
        (0x2C, "ptr -> float parameter block"),
        (0x30, "const 2"),
        (0x34, "const 0"),
    ):
        v = u32(off)
        rel = f"  (= size-{n - v})" if 0 < v <= n else ""
        print(f"    0x{off:02X} 0x{v:08X} = {v}{rel}   [{note}]")

    # ---- body layout detection ---------------------------------------
    print("  [body]")
    first = u32(HEADER_SIZE)
    if first < n:
        offs, o = [], HEADER_SIZE
        while o + 4 <= n:
            v = u32(o)
            if (offs and v <= offs[-1]) or v >= n:
                break
            offs.append(v)
            o += 4
        implied = (first - HEADER_SIZE) // 4
        aligned = (first - HEADER_SIZE) % 4 == 0
        print(f"    layout: OFFSET TABLE at 0x{HEADER_SIZE:X}")
        print(f"    monotonic run: {len(offs)} entries (may overrun into record data)")
        print(f"    implied count if table abuts first record: {implied} "
              f"(4-byte aligned: {aligned})")
        if offs:
            gaps = [offs[i + 1] - offs[i] for i in range(len(offs) - 1)]
            print(f"    first targets: {[hex(x) for x in offs[:6]]}")
            print(f"    record spans: min={min(gaps)} median={sorted(gaps)[len(gaps)//2]} max={max(gaps)}")
    else:
        print(f"    layout: NO offset table (first u32 0x{first:X} > filesize) -- "
              f"alternate/inline-data layout")

    # ---- float parameter block ---------------------------------------
    t = u32(0x2C)
    if 0 < t < n:
        raw = d[t:t + 64]
        floats = struct.unpack_from("<%df" % (len(raw) // 4), raw)
        pretty = [f"{f:.6g}" if abs(f) < 1e8 else "?" for f in floats]
        print(f"  [param block @0x{t:X} (size-{n - t})]")
        print(f"    as f32: {pretty[:16]}")

    # ---- trailer ------------------------------------------------------
    tr = struct.unpack_from("<7I", d, n - 28)
    print(f"  [trailer, last 28 bytes]")
    print(f"    u32 x7: {[hex(x) for x in tr]}")
    print(f"    dec   : {list(tr)}")

    # ---- statistics ---------------------------------------------------
    print("  [stats]")
    print(f"    entropy whole={entropy(d):.3f}  head4k={entropy(d[:4096]):.3f}  "
          f"tail4k={entropy(d[-4096:]):.3f}   (>7.9 would imply crypt/compression)")
    bh = collections.Counter(d)
    print(f"    byte hist top5: {[(hex(b), round(c / n, 4)) for b, c in bh.most_common(5)]}")
    import re
    strs = [s for s in re.findall(rb"[ -~]{8,}", d) if not re.fullmatch(rb"[\x20-\x40]+", s)]
    print(f"    plausible ascii strings (>=8, non-punct): {len(strs)}")
    for s in strs[:5]:
        print(f"      {s[:60]!r}")


FLOAT_T = {0: 1, 1: 2, 2: 3, 3: 4}
INT_T = {4: 1, 8: 2, 9: 3, 10: 4}
# Non-numeric input types still consume table space: IMAGE is stored as a float4
# (scalar default in component 0, all zeros when the input has no default).
# STRING and FONT occupy no slot.
NONNUM_WIDTH = {5: 16, 6: 0, 7: 0}


def _pack_default(t, dv):
    import re as _re
    parts = [p for p in _re.split(r"[,\s]+", dv.strip()) if p]
    try:
        if t in FLOAT_T:
            return struct.pack("<%df" % len(parts), *[float(p) for p in parts])
        if t in INT_T:
            return struct.pack("<%di" % len(parts), *[int(float(p)) for p in parts])
    except ValueError:
        return None
    return None


def decode_default_table(sbsasm_path, xml_path, ulp_tolerance=2):
    """Locate and decode the graph-input default table.

    The table is sorted by the manifest's `uid` attribute ascending, with element
    widths given by the input `type` code (float1-4 -> N x f32, int1-4 -> N x i32).
    Values may differ from the XML decimal rendering by a small number of ULPs,
    so matching is tolerant.
    """
    import xml.etree.ElementTree as ET

    d = open(sbsasm_path, "rb").read()
    graph = ET.parse(xml_path).getroot().find("graphs/graph")
    if graph is None:
        print("  no graph in manifest")
        return
    rec = []
    for i in graph.findall("inputs/input"):
        t = int(i.get("type", 0))
        dv = i.get("default")
        rec.append({
            "ident": i.get("identifier", "?"), "uid": int(i.get("uid", "0")),
            "t": t, "dv": dv, "b": _pack_default(t, dv) if dv is not None else None,
        })
    rec.sort(key=lambda r: r["uid"])
    # every input consumes space; non-numeric ones have no comparable bytes
    ents = [(r["b"], len(r["b"])) if r["b"] is not None
            else (None, NONNUM_WIDTH.get(r["t"], 0)) for r in rec]
    total = sum(w for _, w in ents)

    # Deterministic location: the header field at 0x2C equals table_end - 52 in every
    # specimen examined, so the start follows from the manifest alone -- no searching.
    ptr = struct.unpack_from("<I", d, 0x2C)[0]
    start = ptr + 52 - total
    how = "derived from 0x2C"

    # fall back to anchoring if the derived start is implausible
    if not (0 <= start <= len(d) - total):
        best = None
        for s in range(len(ents)):
            blob = b""
            for e in range(s, len(ents)):
                b, w = ents[e]
                if b is None:
                    break
                blob += b
                o = d.find(blob)
                if o < 0:
                    break
                if best is None or (e - s + 1) > best[0]:
                    best = (e - s + 1, s, o)
        if not best:
            print("  default table: NOT FOUND")
            return
        cnt, s, o = best
        start = o - sum(ents[k][1] for k in range(s))
        how = f"anchored on {cnt}-entry run (0x2C derivation failed)"

    print(f"  [default table] start=0x{start:X} len={total} ({how})")
    pos, exact, eps, unexpl = start, 0, 0, 0
    for (b, w), r in zip(ents, rec):
        seg = d[pos:pos + w]
        pos += w
        if b is None:
            continue
        if seg == b:
            exact += 1
            continue
        n = w // 4
        fmt = "<%d" % n + ("f" if r["t"] in FLOAT_T else "i")
        try:
            got, want = struct.unpack(fmt, seg), struct.unpack(fmt, b)
        except struct.error:
            unexpl += 1
            continue
        # the manifest writes floats at 6 significant figures (%g), which cannot
        # round-trip an f32 -- the binary value is the authoritative one
        if all(abs(p - q) <= 1e-5 * max(1.0, abs(q)) for p, q in zip(got, want)):
            eps += 1
            print(f"    ROUNDED  @0x{pos - w:X} {r['ident'][:26]:<26} "
                  f"xml={want} binary={got}")
        else:
            unexpl += 1
            print(f"    MISMATCH @0x{pos - w:X} {r['ident'][:26]:<26} "
                  f"xml={want} binary={got}")
    n_cmp = exact + eps + unexpl
    print(f"    {exact}/{n_cmp} byte-exact, {eps} explained by %g rounding, "
          f"{unexpl} unexplained")


def from_sbsar(path):
    tmp = tempfile.mkdtemp(prefix="sbsar_")
    subprocess.run(["bsdtar", "-xf", path, "-C", tmp], check=True)
    found = glob.glob(os.path.join(tmp, "**", "*.sbsasm"), recursive=True)
    if not found:
        print(f"  no .sbsasm inside {path}")
    for f in found:
        probe(f)
        xml = os.path.splitext(f)[0] + ".xml"
        if os.path.exists(xml):
            decode_default_table(f, xml)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--sbsar", action="store_true",
                    help="treat inputs as .sbsar archives and extract first")
    a = ap.parse_args()
    for f in a.files:
        if a.sbsar or f.lower().endswith(".sbsar"):
            from_sbsar(f)
        else:
            probe(f)


if __name__ == "__main__":
    main()
