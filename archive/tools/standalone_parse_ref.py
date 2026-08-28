#!/usr/bin/env python3
"""Extract a Substance package's graph interface from a .sbsasm alone — no manifest.

Locates the interface block by scanning for the footer's arithmetic signature, then
walks it backwards to recover input types, uids and default values.
"""
import struct, sys

FLOATT = {0: 1, 1: 2, 2: 3, 3: 4}
INTT = {4: 1, 8: 2, 9: 3, 10: 4}
TYPENAME = {0:'float1',1:'float2',2:'float3',3:'float4',4:'int1',
            5:'image',6:'string',7:'font',8:'int2',9:'int3',10:'int4'}


def image_width(ver):
    return 16 if ver >= 0x00080000 else 0


def find_footer(d):
    """The footer is (count, dir_ref, dir_ref_end, table_start-52) with an exact
    arithmetic relation that is vanishingly unlikely to occur by chance."""
    n = len(d)
    hits = []
    for off in range(0x38, n - 15, 4):
        c, r0, r1, bk = struct.unpack_from("<4I", d, off)
        if c == 0 or c > n // 4 or r1 != r0 + 4 * c or not (0 < bk < off):
            continue
        dir0 = r0 - 4 + 0x38
        if dir0 < 0 or dir0 + 4 * c > n:
            continue
        hits.append((off, c, r0, bk))
    return hits


def parse(path):
    d = open(path, "rb").read()
    if d[:4] != b"SBAM":
        raise ValueError("not an sbsasm")
    ver = struct.unpack_from("<I", d, 4)[0]
    iw = image_width(ver)
    hits = find_footer(d)
    if not hits:
        raise ValueError("no interface-block footer found")

    # A file may contain more than one candidate matching the arithmetic signature.
    # The real one is the candidate whose block resolves AND whose value table, walked
    # with the widths its descriptor types imply, lands exactly on the header.
    chosen = None
    for foot, count, dir_ref, back in hits:
        tstart = back + 52
        sol = None
        for n_in in range(1, 4000):
            dsc = foot - 8 * n_in
            if dsc <= tstart:
                break
            for n_out in range(0, 400):
                hdr = dsc - 4 * n_out - 4
                if hdr < tstart:
                    break
                if struct.unpack_from("<HH", d, hdr) == (n_out, n_in):
                    sol = (n_out, n_in, hdr, dsc)
                    break
            if sol:
                break
        if not sol:
            continue
        n_out, n_in, hdr, dsc = sol
        span = 0
        for k in range(n_in):
            t = struct.unpack_from("<I", d, dsc + 8 * k)[0]
            span += 4 * FLOATT[t] if t in FLOATT else (
                4 * INTT[t] if t in INTT else (iw if t == 5 else 0))
        if tstart + span == hdr:
            chosen = (foot, count, dir_ref, back, n_out, n_in, hdr, dsc)
            break
    if not chosen:
        raise ValueError(f"no candidate resolved (of {len(hits)})")
    foot, count, dir_ref, back, n_out, n_in, hdr, dsc = chosen
    tstart = back + 52

    inputs = [struct.unpack_from("<II", d, dsc + 8 * k) for k in range(n_in)]
    out_uids = list(struct.unpack_from("<%dI" % n_out, d, hdr + 4)) if n_out else []

    # walk the value table using the widths the descriptor types imply
    pos, vals = tstart, []
    for t, uid in inputs:
        if t in FLOATT:
            k = FLOATT[t]
            v = struct.unpack_from("<%df" % k, d, pos); w = 4 * k
        elif t in INTT:
            k = INTT[t]
            v = struct.unpack_from("<%di" % k, d, pos); w = 4 * k
        else:
            w = iw if t == 5 else 0
            v = struct.unpack_from("<4f", d, pos) if w == 16 else ()
        vals.append((t, uid, v))
        pos += w
    return dict(version=ver, dir_count=count, dir_at=dir_ref - 4 + 0x38,
                table_start=tstart, n_in=n_in, n_out=n_out,
                inputs=vals, output_uids=out_uids, table_ok=(pos == hdr))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        r = parse(p)
        print(f"{p}\n  version 0x{r['version']:08X}  inputs {r['n_in']}  outputs {r['n_out']}"
              f"  directory {r['dir_count']} entries @0x{r['dir_at']:X}  consistent={r['table_ok']}")
        for t, uid, v in r["inputs"][:8]:
            print(f"    uid={uid:<11} {TYPENAME.get(t, t):<7} {v}")
