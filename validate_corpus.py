#!/usr/bin/env python3
"""Validate the documented .sbsasm structure against every extracted specimen.

Run from a directory containing x_* extraction dirs (also recurses into corpus/,
pairs/, pairs2/ if present). Exits non-zero if any specimen contradicts the spec.

Structure validated, per single-graph package:

    [ input value table ]
    [ u16 n_outputs ][ u16 n_inputs ]
    [ u32 output_uid * n_outputs ]
    [ (u32 type, u32 uid) * n_inputs ]        input descriptors, uid-ascending
    [ u32 count ][ u32 dir_ref ][ u32 dir_ref_end ][ u32 table_start - 52 ]

  The footer names the record directory: it lives at (dir_ref - 4) + 0x38 and holds
  `count` strictly-increasing absolute file offsets. It is NOT always at 0x38.

  * the value table holds graph inputs AND global inputs, merged and sorted by uid
  * element width comes from the manifest type code (image width is version-dependent)
  * table_end == u32_at(0x2C) + 52
  * floats may differ from the manifest by %g rounding; compare with epsilon
"""
import collections, glob, hashlib, os, re, struct, sys
import xml.etree.ElementTree as ET

FLOATT = {0: 1, 1: 2, 2: 3, 3: 4}
INTT = {4: 1, 8: 2, 9: 3, 10: 4}
PTR_SKEW = 52
EPS = 1e-5


def image_width(ver):
    """v8 and later give image inputs a 16-byte float4 slot; earlier versions none."""
    return 16 if ver >= 0x00080000 else 0


def pack(t, dv):
    parts = [p for p in re.split(r"[,\s]+", dv.strip()) if p]
    try:
        if t in FLOATT:
            return struct.pack("<%df" % len(parts), *[float(p) for p in parts])
        if t in INTT:
            return struct.pack("<%di" % len(parts), *[int(float(p)) for p in parts])
    except ValueError:
        return None
    return None


def specimens():
    seen = set()
    for pat in ("x_*", "corpus/x_*", "pairs/x_*", "pairs2/x_*", "pairs3/x_*",
                "pairs4/x_*", "pairs5/x_*", "pairs6/x_*", "tiny/x_*", "tiny2/x_*"):
        for xd in sorted(glob.glob(pat)):
            a = glob.glob(os.path.join(xd, "**", "*.sbsasm"), recursive=True)
            x = glob.glob(os.path.join(xd, "**", "*.xml"), recursive=True)
            if not (a and x):
                continue
            # deduplicate by content: the corpus contains the same material extracted
            # more than once under different names, which inflates every count
            key = hashlib.sha256(open(a[0], "rb").read()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            yield os.path.basename(xd)[2:], a[0], x[0]


def analyse(asm, xml):
    d = open(asm, "rb").read()
    n = len(d)
    root = ET.parse(xml).getroot()
    r = {"n": n, "ver": struct.unpack_from("<I", d, 4)[0],
         "ok_magic": d[:4] == b"SBAM",
         "ok_size": struct.unpack_from("<I", d, 0x10)[0] == n,
         "ok_trailer": struct.unpack_from("<I", d, 0x1C)[0] == n - 28,
         "ngraphs": len(root.findall("graphs/graph"))}
    r["layout"] = "table" if struct.unpack_from("<I", d, 0x38)[0] < n else "alt"
    graphs = root.findall("graphs/graph")
    r["multigraph"] = len(graphs) > 1
    iw = image_width(r["ver"])
    # The interface block is package-level: it aggregates the inputs and outputs of
    # EVERY graph, plus the package globals, in one uid-ascending sequence.
    entries = []
    for g in graphs:
        entries += [(int(i.get("type", 0)), int(i.get("uid", "0")), i.get("default"))
                    for i in g.findall("inputs/input")]
    entries += [(int(i.get("type", 0)), int(i.get("uid", "0")), i.get("default"))
                for i in root.findall("global/inputs/input")]
    entries.sort(key=lambda z: z[1])

    ents = []
    for t, _uid, dv in entries:
        b = pack(t, dv) if dv is not None else None
        ents.append((b, len(b), t) if b is not None else (None, iw if t == 5 else 0, t))
    total = sum(w for _, w, _ in ents)
    start = struct.unpack_from("<I", d, 0x2C)[0] + PTR_SKEW - total
    r.update(total=total, start=start)
    r["exact"] = r["eps"] = r["bad"] = r["entries"] = 0
    if not (0 <= start <= n - total - 4):
        r["bad"] = -1
        return r

    pos = start
    for b, w, t in ents:
        seg = d[pos:pos + w]
        pos += w
        if b is None:
            continue
        r["entries"] += 1
        if seg == b:
            r["exact"] += 1
            continue
        k = w // 4
        fmt = "<%d" % k + ("f" if t in FLOATT else "i")
        try:
            got, want = struct.unpack(fmt, seg), struct.unpack(fmt, b)
        except struct.error:
            r["bad"] += 1
            continue
        if all(abs(p - q) <= EPS * max(1.0, abs(q)) for p, q in zip(got, want)):
            r["eps"] += 1
        else:
            r["bad"] += 1

    outs = []
    for g in graphs:
        for o in g.findall("outputs/output"):
            try:
                outs.append(int(o.get("uid")))
            except (TypeError, ValueError):
                pass
    n_out, n_in = struct.unpack_from("<HH", d, start + total)
    r["ok_header"] = (n_out, n_in) == (len(outs), len(entries))
    r["ok_outarray"] = False
    if r["ok_header"] and outs:
        got = list(struct.unpack_from("<%dI" % len(outs), d, start + total + 4))
        r["ok_outarray"] = sorted(got) == sorted(outs)
        r["out_order"] = ("declaration" if got == outs
                          else "uid-ascending" if got == sorted(outs) else "other")

    # input descriptor array: (u32 type, u32 uid) per input, same uid-ascending order
    desc = start + total + 4 + 4 * len(outs)
    r["ok_desc"] = False
    if desc + 8 * len(entries) <= n:
        r["ok_desc"] = all(
            struct.unpack_from("<II", d, desc + 8 * k) == (t, u)
            for k, (t, u, _dv) in enumerate(entries))

    # trailing array descriptor + back-pointer to the value table
    foot = desc + 8 * len(entries)
    r["ok_footer"] = r["ok_dir"] = False
    if foot + 16 <= n:
        cnt, a0, a1, back = struct.unpack_from("<4I", d, foot)
        r["ok_footer"] = (a1 == a0 + 4 * cnt) and (back == start - 52)
        # the record directory sits at (dir_ref - 4) + 0x38, not necessarily at 0x38
        base = a0 - 4
        dir0 = base + 0x38
        r["dir_base"] = base
        r["dir_count"] = cnt
        if 0 <= dir0 and dir0 + 4 * cnt <= n and cnt >= 1:
            ents = struct.unpack_from("<%dI" % cnt, d, dir0)
            # a single-entry directory is trivially ordered
            r["ok_dir"] = (all(ents[i] < ents[i + 1] for i in range(cnt - 1))
                           and 0 < ents[0] and ents[-1] < start)
    return r


def main():
    rows, unreadable = [], []
    for k, a, x in specimens():
        try:
            rows.append((k, analyse(a, x)))
        except ET.ParseError as e:
            # some manifests carry bytes the XML parser rejects; report rather than abort
            unreadable.append((k, str(e).split(":")[0]))
    if not rows:
        print("no specimens found")
        return 1
    multi = [k for k, r in rows if r.get("multigraph")]
    fails = [(k, r) for k, r in rows
             if not r["ok_magic"] or not r["ok_size"] or not r["ok_trailer"]
             or r["bad"] or not r.get("ok_header") or not r.get("ok_outarray")]
    tot = sum(r["entries"] for _, r in rows)
    ex = sum(r["exact"] for _, r in rows)
    eps = sum(r["eps"] for _, r in rows)
    bad = sum(max(r["bad"], 0) for _, r in rows)
    print(f"specimens              : {len(rows)}   (of which multi-graph: {len(multi)})")
    print(f"value-table entries    : {tot}")
    print(f"  byte-exact           : {ex} ({100*ex//max(tot,1)}%)")
    print(f"  within %g rounding   : {eps}")
    print(f"  unexplained          : {bad}")
    print(f"(n_out, n_in) header   : {sum(1 for _, r in rows if r.get('ok_header'))}/{len(rows)}")
    print(f"output uid array       : {sum(1 for _, r in rows if r.get('ok_outarray'))}/{len(rows)}")
    print("  array order          :",
          dict(collections.Counter(r.get("out_order") for _, r in rows if r.get("ok_outarray"))))
    print(f"input descriptor array : {sum(1 for _, r in rows if r.get('ok_desc'))}/{len(rows)}")
    print(f"trailing array footer  : {sum(1 for _, r in rows if r.get('ok_footer'))}/{len(rows)}")
    print(f"record directory       : {sum(1 for _, r in rows if r.get('ok_dir'))}/{len(rows)}")
    print(f"  directory base != 0  : {sum(1 for _, r in rows if r.get('dir_base'))}/{len(rows)}"
          "   (these are NOT at 0x38)")
    if unreadable:
        print(f"manifests unparseable  : {len(unreadable)}  " +
              ", ".join(k for k, _ in unreadable[:4]))
    print("versions               :", dict(collections.Counter(hex(r["ver"]) for _, r in rows)))

    if fails:
        print(f"\nFAILURES ({len(fails)}):")
        for k, r in fails[:15]:
            print(f"   {k:<40} bad={r['bad']} header={r.get('ok_header')} "
                  f"outarray={r.get('ok_outarray')} desc={r.get('ok_desc')} "
                  f"footer={r.get('ok_footer')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
