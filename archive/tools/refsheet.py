#!/usr/bin/env python3
"""Our render beside the engine's OWN export, as a PICTURE, one row per paired output.

    python3 archive/tools/refsheet.py <pack> [arm=value,arm=value] [--out DIR]

    python3 archive/tools/refsheet.py Chesterfield
    python3 archive/tools/refsheet.py Bricks fx.subdivide=quadrant,fx.tree.gate=twoway

WHY A PICTURE, BESIDE THE SCALARS RATHER THAN INSTEAD OF THEM. `refcompare` and
`nativeguard` answer "by how much", per channel, and there are faults they cannot name
because no scalar in the table is a function of them. Three found in one sitting, each
invisible in a corr/band/dc row and obvious at a glance: a faint ring a third of the
canvas across sweeping five channels of three Bricks graphs (the flat walk drawing one
canvas-sized pattern); SandyStonePath drawing cog-shaped rosettes on every tile, in all
six channels and both export sets, that the exports have no trace of; and RoofTiles'
shingles arriving as smooth gradient ramps where the export has dense vertical wood grain.
The first two are still unattributed. See FORMAT-NOTES.md, "The pictures at native".

EVERY PACK AT ITS OWN IMPLIED `$outputsize`, THROUGH `render2-lean`, which is the honest
reading and not a choice: `max_dim` clamps each record independently while `$size`
programs read the declared size, so a capped render is a DIFFERENT PICTURE and not a
coarser one, and at native the ordinary whole-file pass does not fit (112 GB on Bricks).
Both sides are resampled to one display grid, because a 1024 render beside a 2048 export
compares two rulers.

THE PAIRING IS `refcompare.compare_pack`'s and is not reimplemented here -- graph
directories, filename prefixes, the identifier-then-channel fallback, the 16-bit load, the
export sets. A pack whose exports were made at inputs the file does not record is drawn at
the DECLARED inputs (this takes no `nativeguard`-style override), so RoofTiles' row count
will not match its export's; that is a property of the pack, recorded in
"RoofTiles ships two export sets and neither is at the declared inputs", and not a
rendering fault to be read off this sheet.
"""
import os, sys, time
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "render2"), _HERE):
    sys.path.insert(0, _p)
import assume, refcompare as rc  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

DISP = 384
PAD, HDR = 8, 18


def arms(text):
    """`a=b,c=d` as the candidate objects `assume.QUESTIONS` declares."""
    out = dict(kv.split("=", 1) for kv in (text or "").split(",") if kv)
    for k, v in list(out.items()):
        if k not in assume.QUESTIONS:
            raise SystemExit("refsheet: %r is not an assume question" % k)
        for c in assume.QUESTIONS[k]:
            if str(c) == v:
                out[k] = c
                break
        else:
            raise SystemExit("refsheet: %r is not a candidate for %r; try %r"
                             % (v, k, assume.QUESTIONS[k]))
    return out


def _rgb(chans):
    a = np.stack(chans[:3], -1) if len(chans) >= 3 else np.repeat(chans[0][:, :, None], 3, 2)
    return np.clip(a, 0.0, 1.0)


def sheet(pack, refs, choices, out_dir):
    osz = rc.implied_outputsize(refs)
    dim = 1 << max(osz) if osz else 256
    print("=== %s  implied $outputsize %s -> %d px%s"
          % (pack, osz, dim, ("  arms %s" % choices) if choices else ""), flush=True)
    t0, rows = time.time(), {}
    with assume.scope(**choices):
        for name, chan, ours, ref in rc.compare_pack(
            pack, refs, max_dim=dim, outputsize="implied",
            renderer="render2-lean", grid=DISP, qualify_graph=True,
        ):
            if chan is None:
                print("   %-28s %s" % (name, ref), flush=True)
                continue
            o, r = rows.setdefault(name, ([], []))
            o.append(ours)
            r.append(ref)
    print("   %d outputs in %.0fs" % (len(rows), time.time() - t0), flush=True)
    if not rows:
        return None
    names = sorted(rows)
    W = PAD + 2 * (DISP + PAD)
    H = HDR + len(names) * (DISP + HDR + PAD)
    im = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(im)
    d.text((PAD, 4), "%s   ours (left)  vs  export (right)   @ %d px%s"
           % (pack, dim, ("   %s" % choices if choices else "")), (230, 230, 230))
    y = HDR
    for nm in names:
        o, r = rows[nm]
        d.text((PAD, y + 3), "%s   [%d ch]" % (nm, len(o)), (200, 200, 120))
        for k, chans in enumerate((o, r)):
            im.paste(Image.fromarray((_rgb(chans) * 255).astype(np.uint8)),
                     (PAD + k * (DISP + PAD), y + HDR))
        y += DISP + HDR + PAD
    tag = "_" + "_".join(str(v) for _k, v in sorted(choices.items())) if choices else ""
    path = os.path.join(out_dir, "sheet_%s%s.png" % (pack.split("__")[-1], tag))
    im.save(path)
    print("   wrote %s" % path, flush=True)
    return path


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "")
                for a in argv[1:] if a.startswith("--"))
    # THE SPACE-SEPARATED SPELLING TOO, which is what anyone types first. Without this
    # `--out DIR` parsed as an empty `out` and the directory fell through to `args`, so
    # the flag silently wrote to the default and said nothing.
    rest = list(argv[1:])
    while rest:
        a = rest.pop(0)
        if a.startswith("--") and "=" not in a and rest and not rest[0].startswith("--"):
            opts[a[2:]] = rest.pop(0)
            if opts[a[2:]] in args:
                args.remove(opts[a[2:]])
    if not args:
        raise SystemExit(__doc__)
    packs = rc.reference_packs(args[0])
    if not packs:
        raise SystemExit("refsheet: no pack matching %r under %s" % (args[0], rc.PACKS))
    choices = arms(args[1] if len(args) > 1 else "")
    out_dir = opts.get("out") or "/tmp"
    for pack, refs in sorted(packs.items()):
        sheet(pack, refs, choices, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
