#!/usr/bin/env python3
"""Render a pack at native through `render2-lean` and keep a DOWNSAMPLED copy of every record
in one output's cone, so a picture-level fault can be bisected offline without holding the
cone at full size.

    python3 archive/tools/conestash.py <pack> <output channel> <out.npz> [--factor 4]
                                       [--inputs uid=v[,v]...] [--arms a=b,c=d]

    python3 archive/tools/conestash.py Sandy height ~/Documents/cleanroom-substance-runs/sandy01_height.npz \
        --inputs 89582107=1

WHY A HOOK AND NOT `extra_keep`. `render2-lean` can be told to keep intermediates alive, and
for a whole cone at 2048 that is ~16 MB a record -- the cone of SandyStonePath's height is
hundreds of records, which does not fit. This wraps every entry of the filter table and
keeps a block-averaged float16 copy of each result as it is produced, while the lean pass
frees the full-size array exactly as it always does. The copies are for LOOKING -- which
record a shape first appears in -- and are not a score: a 4x block mean is a coarser picture,
which is legitimate here only because the render itself ran at native (FORMAT-NOTES.md,
"the `pergraph` blocker was an artefact of `max_dim`": clamping the render changes the
picture; downsampling its result does not).

`filters` IS LOADED TWICE in this process, as `filters` and as `render2.filters` (the
same split `engine` has -- see `nativeguard.py`'s docstring), so both filter tables are
wrapped. Written after a session scratchpad holding the throwaway version of this was wiped
by a container restart.
"""
import os, sys, time, glob
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "render2"), _HERE):
    sys.path.insert(0, _p)
import assume, manifest, refcompare as rc, sbsasm  # noqa: E402
import filters as _f_top  # noqa: E402
from render2 import filters as _f_pkg  # noqa: E402


def _opt(argv, name, default=None):
    if name in argv:
        k = argv.index(name)
        return argv[k + 1]
    return default


def main(argv):
    pos = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and not argv[i - 1].startswith("--")]
    if len(pos) < 3:
        raise SystemExit(__doc__)
    pack, channel, out = pos[0], pos[1].lower(), os.path.expanduser(pos[2])
    factor = int(_opt(argv, "--factor", "4"))
    # `--quantize N`: round EVERY filter output to N bits before the next record reads it --
    # a probe for whether the engine stores intermediates at a fixed bit depth. Not a
    # reading of the format; an experiment.
    qbits = _opt(argv, "--quantize")
    qscale = float((1 << int(qbits)) - 1) if qbits else None
    inputs = {}
    for kv in (_opt(argv, "--inputs", "") or "").split(","):
        if kv:
            k, v = kv.split("=")
            inputs[int(k)] = tuple(int(float(x)) if float(x).is_integer() else float(x) for x in v.split(";"))
    arms = dict(kv.split("=", 1) for kv in (_opt(argv, "--arms", "") or "").split(",") if kv)
    for k, v in list(arms.items()):
        for c in assume.QUESTIONS.get(k, ()):
            if str(c) == v:
                arms[k] = c
    packs = rc.reference_packs(pack)
    if not packs:
        raise SystemExit("no pack matching %r" % pack)
    name, refs = sorted(packs.items())[0]
    ap = sorted(glob.glob(os.path.join(rc.PACKS, name, "**", "*.sbsasm"), recursive=True))[0]
    asm = sbsasm.Assembly(ap)
    R = asm.records
    chans = manifest.output_channels(asm)
    names = manifest.output_names(asm)
    target = [ri for uid, _f, _g, ri in asm.outputs()
              if channel in ((chans.get(uid) or "").lower(), (names.get(uid) or "").lower())]
    if not target:
        raise SystemExit("no output with channel or name %r" % channel)
    root = target[0]
    depth, todo = {root: 0}, [root]
    while todo:
        i = todo.pop(0)
        for e in R[i].edges:
            if e not in depth:
                depth[e] = depth[i] + 1
                todo.append(e)
    osz = rc.implied_outputsize(refs)
    stash = {}

    def shrink(a):
        a = np.asarray(a, np.float32)
        if a.ndim == 2:
            a = a[:, :, None]
        h, w, c = a.shape
        f = factor if (h % factor == 0 and w % factor == 0) else 1
        return a.reshape(h // f, f, w // f, f, c).mean((1, 3)).astype(np.float16)

    wrapped = []
    for mod in {id(_f_top): _f_top, id(_f_pkg): _f_pkg}.values():
        for key, fn in list(mod.FILTERS.items()):
            def w(ctx, v, _fn=fn):
                r = _fn(ctx, v)
                if qscale is not None:
                    r = np.round(np.clip(np.asarray(r, np.float32), 0.0, 1.0) * qscale) / qscale
                if v.index in depth:
                    try:
                        stash[v.index] = shrink(r)
                    except Exception:
                        pass
                return r
            mod.FILTERS[key] = w
            wrapped.append((mod, key, fn))
    t0 = time.time()
    try:
        with assume.scope(**arms):
            outs = rc._renderer("render2-lean")(asm, 1 << max(osz), None, osz, inputs=inputs or None)
    finally:
        for mod, key, fn in wrapped:
            mod.FILTERS[key] = fn
    print("%s  output %s = record %d  cone %d records  stashed %d  render %.0fs"
          % (name, channel, root, len(depth), len(stash), time.time() - t0), flush=True)
    np.savez_compressed(out, **{("r%d" % i): a for i, a in stash.items()},
                        _depth=np.array([(i, d) for i, d in depth.items()], np.int64),
                        _output=np.array([root], np.int64))
    print("wrote %s" % out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
