"""Walk an Assembly's record graph in index order and evaluate what it can.

Records are processed 0..N-1 -- verified corpus-wide (353,068/353,068 edges sampled)
that every edge points to a strictly earlier record index, so a single forward pass
suffices; nothing needs a topological sort. Handles `bitmap` records with embedded
pixels and `pixelprocessor` records, wiring each edge to the already-computed source
record's output via `sbsruntime.image_sampler` and sharing one dict across every
record's `cache_read`/`cache_write` for the whole walk. `uniform` and every other
filter type raise `Unsupported` by name rather than guess -- confirmed on a real
specimen that a `uniform` record's own `.programs` entry can be its SIZE expression
with no separate program for the fill color at all, so treating `.programs[-1]` as
the color the way a `pixelprocessor`'s main program works produced a plausible-looking
but wrong tiled image (the size expression's own (log2 width, log2 height) output,
not a color). Where a uniform's color actually lives is not investigated.

No embedded-pixel `bitmap` in the corpus co-occurs with `cache_read`/`cache_write`
while staying inside {bitmap, pixelprocessor, uniform} -- every specimen combining
the two also uses a filter type with no runtime implementation here, so the cache
wiring itself is verified separately (two sequential `cache_write`/`cache_read` calls
through one `use_shared_cache` dict, exactly what this module does across records)
rather than end to end through this walker on a real file.

A `pixelprocessor` can carry more than one program (Record.programs' own docstring:
directionalwarp has an intensity and an angle, warp/blur/distance/sharpen/normal/
filter-11 the same) -- but not always as independent parameters. A real specimen has
an earlier program that `set`s slot 0 to a random per-image seed, which only the last
program's `get slot 0` then reads; running just the last program left that get on an
empty `slots` dict. Every program but the last now runs once, N=1, not per-pixel,
sharing one `slots` dict across the whole record so the earlier ones' `set`s carry
forward to the real per-pixel body.

`max_dim` sweeps fast at the cost of one real inaccuracy: capping each pixelprocessor's
OWN width/height independently does not preserve two DIFFERENT records' size ratio to
each other, and `cache_read`/`cache_write` share a raw per-pixel array across records
with no position-based resampling the way `image_sampler` gives edges -- confirmed on a
real specimen where one record's write at 16x1024 capped to 16x48 (N=768) while a later
reader's own record capped to 48x48 (N=2304), a real shape mismatch that is an artifact
of independent per-record capping, not of the cache mechanism itself. Rendering a single
file for real output should leave `max_dim` unset.

A corpus-wide sweep also found NaN in a small, consistent minority of real (not
placeholder-fed) pixelprocessor outputs, always traced to the same shape: a value built
as `sqrt(1 - dot(v, v))` (reconstructing a normal map's Z from its XY, or similar) where
nothing in the bytecode clamps the input to sqrt to be non-negative. This is not a
transpiler defect -- `np.sqrt` on a negative number is the correct IEEE-754 answer, NaN,
matching the actual math the compiled program performs -- and there is no evidence here
for what the real engine does at that same input (clamps to 0? saturates earlier in a
step this reading is missing?), so it is surfaced rather than guessed at.
"""
import numpy as np
import transpile, sbsruntime, fxrender


class Unsupported(Exception):
    pass


# THE SLOT FRAME IS PER-RECORD. Every record evaluates against its own empty dict, and
# nothing carries across records. There is no `SplitFrame` and no shared floor any more;
# what follows is why, because the class that used to be here was not obviously wrong.
#
# The reading it encoded: an FX-Map's entry programs are dominated by `get <slot>` while
# its node programs and the record's own programs do the `set`s, and the two sets were
# measured to coincide within a FILE rather than within a record --
#
#     slot range      read AND written in the same file     control: written elsewhere
#     all slots               74.7%                                 52.2%
#     slots < 64              74.1%                                 54.3%
#     slots >= 64             88.1%   (59 of 67)                     0.0%
#
# -- so slots >= 64 were shared graph-wide and slots below it kept per-record. The floor
# was put where the control went to zero, which is the right instinct applied to the wrong
# measurement: the UNIT was wrong. An FX-Map is a record, not a file. Asked per record,
# over 61,384 entry-program slot reads in 282 files, counting as writes only the node
# chain and the record's own programs:
#
#     same RECORD                 61,318 / 61,384    99.892%
#     OTHER record, same file      7,245 / 61,384     11.8%   <- the control that matters
#     other FILE                  54,930 / 61,384     89.5%   <- what 52-54% above was
#
# Cross-FILE collision is 89.5% because small slot indices collide everywhere, which is
# exactly why the file-level figure stalled at 74% and needed a floor to say anything.
# Against an 11.8% control the per-record answer is unambiguous, and it holds at EVERY
# slot range -- ~100% from 0-8 up through 64+. Slots >= 64 are 118 of 61,384 reads; their
# 0.0% cross-file control measures how rare a high slot index is, not that anything is
# shared above it. FORMAT-NOTES.md, "The slot frame is per-RECORD".
#
# The 0.108% that does not resolve in-record is one construct, not a channel between
# records: 22 records in 5 files, always a lone `0x18B` node with entry tag `0x15140848`,
# whose bare `get <slot>` pass-throughs name slots above the highest its one-node chain
# writes. That 65 of those 66 reads name a slot some OTHER record happens to write is the
# 11.8% coincidence rate, not evidence.
#
# Going the other way is still wrong, and that evidence stands: making the whole frame
# graph-wide regressed 87 record outputs on `pairs2` and gained none, rooted in 9
# `dirmotionblur` records that inherited a stale 0 and raised ZeroDivisionError. Per-record
# is the far end of that same finding rather than a reversal of it -- measured here at
# 10,625 records rendered against the floor's 10,624, no regressions.


def default_inputs(asm, N):
    out = {}
    for t, u, v in asm.header.get('inputs') or []:
        if not v:
            continue
        arr = np.array(v, dtype=np.float32).reshape(1, -1)
        out[u] = np.repeat(arr, N, axis=0)
    return out


def load_pixels_bitmap(asm, rec):
    b = rec.bitmap
    off, size, ch, depth = b['offset'], b['size'], b['channels'], b['depth']
    if depth is None:
        # Record.bitmap's own documented gap: a channel code CHANNELS does not cover
        # (cls 0x808) reports 'pixels' with channels/depth/size all None rather than
        # vanishing, since the byte offset is known even though the layout is not.
        raise Unsupported("bitmap has pixels but an undecoded channel code (depth is None)")
    if off + size > len(asm.data):
        # Not a decode error: the declared offset/size are consistent with the record's
        # own width/height/channels/depth, but the file this .sbsasm was extracted from
        # does not actually hold that many bytes there -- confirmed on a real specimen,
        # short by exactly (declared size - bytes actually present), i.e. genuinely
        # truncated, not misread. Left to `np.frombuffer` this raises a confusing
        # `cannot reshape` error instead of naming the real problem.
        raise Unsupported("bitmap wants %d bytes at %d, file has %d" %
                          (size, off, max(0, len(asm.data) - off)))
    dtype = "<u1" if depth == 8 else "<u2"
    maxval = float((1 << depth) - 1)
    arr = np.frombuffer(asm.data[off:off + size], dtype=dtype)
    arr = arr.reshape(rec.height, rec.width, ch) if ch and ch > 1 else \
          arr.reshape(rec.height, rec.width, 1)
    return arr.astype(np.float32) / maxval


def pos_grid(W, H):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.stack([(xx.ravel() + 0.5) / W, (yy.ravel() + 0.5) / H], axis=-1)


def to_image(out, N, H, W):
    """Normalize a program's raw return value to an (H, W, k) image.

    An N-sample evaluation does not guarantee an N-row result: if the program's final
    value never actually touches $pos, an edge sample, or anything else N-wide along the
    way -- a constant fill, in whatever component count -- every runtime helper it passed
    through (`vec` chief among them) keeps it at its own natural width-1 row count rather
    than manufacturing a broadcast nothing asked for. That is correct in itself (`vec`'s
    own docstring: scalars get promoted to a column, not to N rows), but it means a
    0-d scalar (`out.shape == ()`) or a (1, k) constant both reach here needing an
    explicit broadcast this walker has to do, not `out.reshape(H, W, out.shape[-1])`
    blindly -- confirmed on real specimens: `out.shape[-1]` on a 0-d array is an
    IndexError (empty shape tuple), and reshaping a (1, k) result straight into
    (H, W, out.shape[-1]) is a size mismatch (k elements, not H*W*k).
    """
    a = np.asarray(out)
    if a.ndim == 0:
        a = a.reshape(1, 1)
    elif a.ndim == 1:
        a = a[:, None]
    if a.shape[0] == 1 and N > 1:
        a = np.repeat(a, N, axis=0)
    return a.reshape(H, W, a.shape[-1])


def synthetic_bitmap(rec, seed):
    """A deterministic placeholder image for a bitmap record with no data of its own.

    Seeded per record so two missing bitmaps feeding the same pixelprocessor are not
    IDENTICAL -- a comparison between them (e.g. `easy_diz`'s own `a > b` threshold)
    would otherwise be trivially all-false everywhere, which looks like a wiring bug
    but is really just two placeholders that happen to agree with themselves.
    """
    yy, xx = np.mgrid[0:rec.height, 0:rec.width].astype(np.float32)
    u, v = xx / max(rec.width, 1), yy / max(rec.height, 1)
    a, b, c = (seed * 37 % 97) / 97, (seed * 61 % 89) / 89, (seed * 13 % 61) / 61
    img = 0.5 + 0.5 * np.sin(2 * np.pi * (u * (2 + a) + v * (2 + b) + c))
    return img[:, :, None].astype(np.float32)


def eval_program(asm, start, inputs, slots, N, pos=None, W=None, H=None):
    end = asm.program_span(start)
    if end is None:
        raise Unsupported("program at %d does not resolve a span" % start)
    src = transpile.transpile(asm.data, start, end, "python", "prog")
    scope = {}
    exec(compile(src, "<prog>", "exec"), scope)
    if pos is not None:
        sbsruntime.set_context(width=W, height=H, pos=pos)
    with np.errstate(all="ignore"):
        try:
            out = scope["prog"](inputs=inputs, slots=slots)
        except sbsruntime.MissingSampler as e:
            # MUST come first: MissingSampler subclasses KeyError, so the handler below
            # swallows it and reports an unwired image edge as a missing slot. That exact
            # confusion -- `SAMPLERS` and `slots` are both small-integer-keyed dicts and
            # raised indistinguishable KeyErrors -- sent two investigations after a
            # phantom slot frame before `sbsruntime.MissingSampler` was introduced to
            # separate them. Removing this handler reintroduces the ambiguity silently.
            raise Unsupported("no sampler for input %s (an unwired edge, NOT a missing "
                              "slot)" % e) from e
        except KeyError as e:
            # `inputs` is keyed by uid (large, from default_inputs) and always fully
            # populated from the package's own declarations; `slots` is keyed by small
            # integers. With MissingSampler split off above, a bare KeyError here means a
            # `get` of a slot this record's own programs never `set`. It did NOT mean that
            # before that split, whatever this comment used to claim. The already-documented
            # category from the transpiler's own execution sweep (FORMAT-NOTES.md,
            # "Executing every program, not just transpiling it"): 9,806 sub-programs
            # whose slots are written by ANOTHER of the record's programs sharing slot
            # state, which this walker does not model across records. Not a new bug --
            # confirmed on a real specimen that the record's other .programs entries
            # (beyond .filter_programs) do not set it either, so it is not simply a
            # missed sibling program.
            raise Unsupported("slot %s read but never set (cross-record/-program slot "
                              "sharing, not modeled here)" % e) from e
    return np.asarray(out)


# ---------------------------------------------------------------------------
# Blend modes.
#
# WHAT IS CORPUS-VERIFIED: that `blendingmode` is the low four bits of blend's slot 1,
# and that it takes values 0-11 -- FORMAT-NOTES.md, "The low four bits of blend slot 1
# are `blendingmode`", a corpus-wide falsification test over 382 specimens with 0
# counterexamples outside 0-11. Twelve values, densely used.
#
# WHAT IS NOT: which mode each integer NAMES. That mapping is not recoverable from this
# corpus and the reason is structural, not a coverage gap -- checked directly and
# recorded in the session that added this:
#   * a `.sbs` compNode has no name field, only a uid and its filter's fixed connection
#     pins ("destination"/"source"/"opacity"), never author free text;
#   * there are ZERO GUIComment/GUIFrame elements in any .sbs anywhere in the tree, so
#     no artist annotation exists to read;
#   * `.sbs` serialises the mode as a bare `constantValueInt32`, the label living in the
#     application UI, not the file;
#   * and a `.sbsar` stores only a filter's INPUTS as pixels, never its computed output,
#     so no (src, dst, mode, ground-truth result) tuple exists in any .sbsar to solve
#     for -- adding more specimens cannot change this.
#
# So THE ORDERING BELOW IS EXTERNAL KNOWLEDGE -- Substance Designer's documented blend
# dropdown order -- held with moderate, not high, confidence, and is the single
# assumption every mode but 0 rests on. It is deliberately kept as one flat table rather
# than scattered through the dispatch: if a corpus ever contradicts it, this table is the
# only thing that has to change.
#
# Mode 0 is the exception and is genuinely corroborated: it is the only mode this file
# implemented before, verified against a controlled red/blue lerp, and "Copy" is exactly
# what that verified behaviour (a straight opacity lerp of src over dst) means. The
# externally-sourced table agreeing with an independently verified fact at its one
# testable point is weak evidence for the rest, not proof.
#
# Each function takes (dst, src) already-sampled float arrays and returns the blended
# colour BEFORE opacity is applied; `apply_blend` does the opacity mix afterward, which
# is the structure mode 0 was verified under.
BLEND_MODES = {
    0:  ('copy',       lambda d, s: s),
    1:  ('add',        lambda d, s: d + s),                  # a.k.a. linear dodge
    2:  ('subtract',   lambda d, s: d - s),
    3:  ('multiply',   lambda d, s: d * s),
    # `addsub` lightens where the source is above mid-grey and darkens below it. The
    # exact pivot scaling is the least certain entry in this table -- the behaviour is
    # described consistently but the formula is not published as an equation, so this
    # takes the reading that maps src=0 -> dst-1, src=0.5 -> dst, src=1 -> dst+1.
    4:  ('addsub',     lambda d, s: d + 2.0 * s - 1.0),
    5:  ('max',        lambda d, s: np.maximum(d, s)),        # a.k.a. lighten
    6:  ('min',        lambda d, s: np.minimum(d, s)),        # a.k.a. darken
    # `switch` is handled specially in `apply_blend` -- it is a hard choice between the
    # two inputs driven by opacity, not a per-channel function that opacity then mixes,
    # so running it through the normal lerp would silently turn it into `copy`.
    7:  ('switch',     None),
    8:  ('divide',     lambda d, s: d / np.where(np.abs(s) < 1e-6, 1e-6, s)),
    9:  ('overlay',    lambda d, s: np.where(d < 0.5, 2.0 * d * s,
                                             1.0 - 2.0 * (1.0 - d) * (1.0 - s))),
    10: ('screen',     lambda d, s: 1.0 - (1.0 - d) * (1.0 - s)),
    11: ('softlight',  lambda d, s: np.where(s < 0.5,
                                             2.0 * d * s + d * d * (1.0 - 2.0 * s),
                                             2.0 * d * (1.0 - s) + np.sqrt(np.clip(d, 0, None)) * (2.0 * s - 1.0))),
}


def apply_blend(mode, dst, src, opacity):
    """Composite `src` over `dst` under `mode` at `opacity`.

    Opacity mixes the blended result back toward the destination, which is the structure
    the one verified mode (0) was checked under: at opacity 0 every mode is a no-op and
    the destination survives untouched. `switch` is the documented exception -- a hard
    selection rather than a mix -- and takes opacity as its selector instead.

    The result is clamped to [0, 1]. Several of these functions leave that range by
    construction (`add` above 1, `subtract` below 0, `divide` arbitrarily far), and the
    format's own images are unsigned-normalised, so an unclamped result would propagate
    out-of-range values into every downstream record. This mirrors the clamp `levels`
    already applies for the same reason.
    """
    entry = BLEND_MODES.get(mode)
    if entry is None:
        raise Unsupported("blend mode %r is outside the verified 0-11 range" % (mode,))
    name, fn = entry
    if name == 'switch':
        return np.where(opacity >= 0.5, src, dst)
    with np.errstate(all="ignore"):
        blended = fn(dst, src)
        return np.clip(dst * (1.0 - opacity) + blended * opacity, 0.0, 1.0)


def render(asm, precomputed=None, verbose=True, max_dim=None, synth_missing_bitmaps=False):
    """Evaluate every record 0..N-1 that a filter type here can handle.

    `precomputed` pre-seeds outputs for records the walker cannot compute itself (e.g. a
    graph-input bitmap) -- {record_index: (H, W, C) array}. Returns {record_index: array}
    for every record that ended up with an output, a {record_index: reason} for every one
    that did not, and a `synthetic` set naming which output indices came from
    `synth_missing_bitmaps` rather than the file's own data or `precomputed`.

    `max_dim` caps the evaluation grid a `pixelprocessor` runs at, independent of the
    record's own declared size -- sampling is position-based (`sbsruntime.image_sampler`
    is bilinear against normalized [0, 1] coordinates, not indexed), so a downsampled
    consumer reading a full-resolution source (or vice versa) is not a shape mismatch,
    just a coarser look. For sweeping many files' worth of records rather than producing
    a final image, this is the difference between minutes and seconds per file.

    `synth_missing_bitmaps` fills a `bitmap` record with no data of its own (a
    pass-through graph input, or any other unresolved kind) with a deterministic
    synthetic pattern instead of raising -- so a sweep can see how much of a graph
    downstream of an external input still runs, at the cost of that branch's output no
    longer reflecting the file's own content.
    """
    outputs = dict(precomputed or {})
    synthetic = set()
    failures = {}
    cache = {}
    sbsruntime.use_shared_cache(cache)

    for i, rec in enumerate(asm.records):
        if i in outputs:
            continue
        try:
            if rec.filter_name == "bitmap":
                b = rec.bitmap
                if b['kind'] == 'pixels':
                    outputs[i] = load_pixels_bitmap(asm, rec)
                elif synth_missing_bitmaps:
                    outputs[i] = synthetic_bitmap(rec, i)
                    synthetic.add(i)
                else:
                    raise Unsupported("bitmap kind %r has no supplied output" % b['kind'])

            elif rec.filter_name == "pixelprocessor":
                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                tainted = False
                for slot_i, edge_rec in enumerate(rec.edges):
                    if edge_rec not in outputs:
                        raise Unsupported("edge -> record %s has no output yet" % edge_rec)
                    src_img = outputs[edge_rec]
                    sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(src_img)
                    tainted = tainted or edge_rec in synthetic
                progs = rec.filter_programs
                if not progs:
                    raise Unsupported("no filter_programs")
                # A record can carry more than one filter program (Record.programs'
                # own docstring: directionalwarp has an intensity and an angle,
                # warp/blur/distance/sharpen/normal/filter-11 the same) -- but not
                # always as independent parameters. A real specimen has an earlier
                # program that `set`s slot 0 to a random per-image seed, which only the
                # LAST program's `get slot 0` then reads; evaluating just the last
                # program left that get on an empty slots dict, `KeyError: 0`. Every
                # earlier program runs once, N=1, not per-pixel, sharing one `slots`
                # dict whose side effects (the `set`s) carry forward; only the last
                # program is the real per-pixel body and gets $pos and the full N.
                slots = {}          # per-record frame; see the slot-frame note above
                for p in progs[:-1]:
                    eval_program(asm, p, default_inputs(asm, 1), slots, 1)
                main = progs[-1]
                inputs = default_inputs(asm, N)
                out = eval_program(asm, main, inputs, slots, N, pos=pos, W=W, H=H)
                outputs[i] = to_image(out, N, H, W)
                if tainted:
                    synthetic.add(i)   # downstream of a synthetic placeholder somewhere

            elif rec.filter_name == "blend":
                # `blendingmode` is the low nibble of slot 1 -- FORMAT-NOTES.md,
                # "blendingmode is the low four bits of blend slot 1", corpus-wide
                # falsified range test. WHICH mode each integer names comes from the
                # BLEND_MODES table above and is EXTERNAL, not corpus-derived; see that
                # table's comment for why no .sbsar can settle it. Mode 0 is the one
                # independently verified case.
                #
                # Edge order -- which input is laid UNDER the other -- was carried here as
                # an unverified convention for a long time. It is now CORPUS-VERIFIED:
                # edges[0] is the destination, edges[1] the source.
                #
                # The test (FORMAT-NOTES.md, "Blend's edge order, settled by asymmetric
                # input types"): a paired `.sbs` names each blend's two connections
                # `destination` and `source` outright, so the only missing link is which
                # compiled edge slot each became. Where a blend's two inputs are fed by
                # DIFFERENT filter types, that type pair identifies the orientation without
                # needing any node-to-record mapping. Restricted to unordered type pairs
                # occurring exactly ONCE on each side -- the count-exact discipline used
                # elsewhere in this document, which is what makes the correspondence
                # unambiguous rather than coincidental:
                #
                #     edges[0] == destination     14 of 14
                #     edges[0] == source           0 of 14
                #
                # over 11 distinct file contents and 11 distinct type pairs (levels/uniform,
                # distance/pixelprocessor, pixelprocessor/fxmaps, gradient/hsl, blend/
                # transformation, levels/sharpen and others), with the provenance gate
                # applied as its own step first. The control matters as much as the result:
                # re-running the identical test with the compiled edges deliberately swapped
                # flips it to 0 of 14 forward, so the test could have detected a reversal
                # and did not -- it is not vacuously agreeing.
                #
                # This mattered more once the asymmetric modes (subtract, divide, overlay)
                # landed: under mode 0 alone a swap was mathematically invisible, so the
                # assumption was both load-bearing and newly falsifiable.
                mode = rec.slot1_flags.get("blendingmode") if rec.slot1_flags else None
                mode = rec.slot1_flags.get("blendingmode") if rec.slot1_flags else None
                if mode is None:
                    raise Unsupported("blend record has no readable blendingmode")
                if len(rec.edges) < 2:
                    raise Unsupported("blend has fewer than 2 edges")
                for edge_rec in rec.edges:
                    if edge_rec not in outputs:
                        raise Unsupported("edge -> record %s has no output yet" % edge_rec)
                tainted = any(e in synthetic for e in rec.edges)

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)

                dst = sbsruntime.image_sampler(outputs[rec.edges[0]])(pos)
                src = sbsruntime.image_sampler(outputs[rec.edges[1]])(pos)
                c = max(dst.shape[-1], src.shape[-1])
                if dst.shape[-1] != c or src.shape[-1] != c:
                    raise Unsupported("blend inputs disagree on channel count (%d vs %d)"
                                      % (dst.shape[-1], src.shape[-1]))

                # Record.size_or_baked's own docstring: its 'program' case is the
                # record's OUTPUT SIZE expression in 91.3% of records, not a filter
                # parameter -- confirmed the hard way here, evaluating it as opacity
                # directly on a real 7-blend chain gave values in the hundreds of
                # thousands (repeated out-of-[0,1] lerp compounding across stages)
                # before this was traced back to the parameter program reading a
                # ($outputsize-shaped) (8, 8) input, not an opacity. filter_programs is
                # the property that already excludes exactly that size program (its own
                # docstring says so directly); the real opacity computation, when the
                # compiler emits one at all, is there instead.
                par = rec.size_or_baked
                if par and par[0] == "float":
                    opacity = np.full((N, 1), par[1], dtype=np.float32)
                else:
                    fprogs = rec.filter_programs
                    if fprogs:
                        for slot_i, edge_rec in enumerate(rec.edges):
                            sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(
                                outputs[edge_rec])
                        slots = {}          # per-record frame; see the slot-frame note above
                        for p in fprogs[:-1]:
                            eval_program(asm, p, default_inputs(asm, 1), slots, 1)
                        opacity = to_image(
                            eval_program(asm, fprogs[-1], default_inputs(asm, N), slots, N,
                                        pos=pos, W=W, H=H),
                            N, H, W).reshape(N, -1)[:, :1]
                    else:
                        # No program at all beyond (possibly) the size expression:
                        # confirmed on a real specimen (record 322) whose only program
                        # IS the one Record.size_or_baked names, so filter_programs
                        # correctly excludes it and leaves nothing. The compiler's own
                        # apparent convention -- proven elsewhere in this file for
                        # blend mode, which is never in the bytecode either when it is
                        # the default -- is to skip emitting code for a parameter left
                        # at its default, so absent any other information this takes
                        # full (100%) opacity as that default rather than 0%, which
                        # would make the blend a no-op and the edge pointless.
                        opacity = np.full((N, 1), 1.0, dtype=np.float32)

                if len(rec.edges) > 2:
                    if rec.edges[2] not in outputs:
                        raise Unsupported("mask edge -> record %s has no output yet"
                                          % rec.edges[2])
                    tainted = tainted or rec.edges[2] in synthetic
                    mask = sbsruntime.image_sampler(outputs[rec.edges[2]])(pos)
                    opacity = opacity * mask[:, :1]

                result = apply_blend(mode, dst, src, opacity)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "transformation":
                # Record.matrix is baked in only 644 of 2,635 transformation records in
                # a real specimen (24%); most of the rest compute it from a program. The
                # largest such program found (record 3182, 97 instructions) is not a
                # 6-float matrix+offset computation at all -- it initializes dozens of
                # slots with rand() calls and values like scale ranges and iteration
                # counts, the shape of a randomized tile/scatter generator's parameter
                # block. That general case is out of scope here.
                #
                # A slice of the "not baked" population is NOT that case, though: 3,103 of
                # 3,103 sampled (x_DLG-Tools__* and a sample of x_serverhouse__*) have
                # `rec.filter_programs` empty AND slot-1 bits 6 and 7 both clear -- the
                # same bits Record.translation's own docstring reads as "no [matrix]
                # parameter block to pack against". `rec.programs` being non-empty there
                # is the record's SIZE-EXPRESSION program (filter_programs already
                # excludes it, same trap as the blend-opacity bug elsewhere in this file)
                # -- there is no matrix-computing code at all, only a size computation.
                # Same compiler convention already established for blend mode (absent =
                # 0) and blend opacity (absent = 1.0): a parameter left at its default is
                # not emitted, so this takes identity (no scale/rotate/shear) rather than
                # raising for that specific, corpus-confirmed shape.
                #
                # `translation` had the identical bug, independently of the above: it
                # checked `rec.programs` (482 of 729 real "baked matrix, no baked
                # translation" specimens have ONLY a size-expression program there, no
                # program that could compute a translation at all) instead of
                # `rec.filter_programs`, so it was raising "translation is a program" on
                # records with no translation program whatsoever. Fixed the same way.
                #
                # Genuinely program-computed matrices/translations (filter_programs
                # non-empty) are still out of scope -- which of possibly several programs
                # computes what is not identified, and "has 2 components" was already
                # tried and found wrong as a discriminator (record 167, matrix (1,0,0,-1),
                # a pure Y-flip: the 2-component program picked this way turned out to
                # compute (0.2199, min(0.3905, 0.3905*$size.x/$size.y)), a function of the
                # record's own aspect ratio, not a translation).
                #
                # Which direction the matrix applies: the conventional raster
                # backward-mapping convention -- for each OUTPUT position, transform it
                # INTO an input sampling position, pivoted at the texture center (0.5,
                # 0.5) so a pure scale or flip does not shift the image off-canvas --
                # matching how virtually every UV-space 2D transform (CSS, SVG, shader
                # texture transforms) is conventionally applied. matrix (m0, m1, m2, m3)
                # is read as row-major [[m0, m1], [m2, m3]].
                #
                # Not verified against a ground-truth reference render -- none is
                # correlated to a specific record here -- but checked for INTERNAL
                # consistency on real, clean (no offset, no program) specimens with a
                # controlled, asymmetric test pattern: record 5115's matrix (0,-1,1,0),
                # a pure 90-degree rotation, turns a top stripe into a left stripe and a
                # left stripe into a bottom stripe with no drift or artifact. Record
                # 956's matrix (0.125,...) against a pattern whose CENTER is plain
                # background gives solid black -- a tight zoom on that center, as scale
                # less than 1 should be. Record 950's matrix (8,...), the reciprocal
                # scale, gives multiple distinct values instead of one solid color --
                # consistent with the pattern tiling/repeating, as scale greater than 1
                # should. Both directions behave as the convention predicts; neither
                # proves the format's own engine does not do the opposite.
                # Which program is which, settled by the format's own bits plus one
                # structural fact. Slot 1 bit 6 or 7 says a matrix parameter exists at all
                # and bit 26 says the offset is program-computed (Record.translation's
                # docstring derives both). Evaluating each filter program once at N=1 then
                # separates them by COMPONENT WIDTH, and the widths do not overlap:
                #
                #   bit 26 set, exactly one program    2,007 of 2,007 return 2 components
                #   bit 26 clear, exactly one program  4 components (405), 2 (162), 1 (79)
                #
                # 100% against a control that is mostly 4-wide -- a 4-vector is a matrix22,
                # a 2-vector is an offset. This is what makes the assignment safe where an
                # earlier attempt was not: that one trusted ANY 2-component result as an
                # offset without consulting bit 26, and on a real specimen (record 167,
                # matrix (1,0,0,-1), a pure Y-flip) picked up a program computing
                # (0.2199, min(0.3905, 0.3905*$size.x/$size.y)) -- an aspect-ratio
                # expression, not a translation. Bit 26 is clear on that record, so the
                # rule below never reaches it.
                #
                # Not verified against the source: a source that declares a CONSTANT offset
                # compiles to a baked one (bit 25), so a containment check against declared
                # constants tests the wrong population -- it scored 6 of 67 and that number
                # says nothing either way. The evidence here is the width split and the bits.
                m = rec.matrix
                matrix_from_program = False
                fprogs = rec.filter_programs
                w1 = rec.words[1] if len(rec.words) > 1 else 0
                has_matrix_param = bool((w1 >> 6 & 1) or (w1 >> 7 & 1))
                offset_is_program = bool(w1 >> 26 & 1)

                by_width = {}
                n_evaluated = 0
                if (m is None and has_matrix_param) or offset_is_program:
                    for p in fprogs:
                        try:
                            a = np.asarray(eval_program(asm, p, default_inputs(asm, 1),
                                                        {}, 1)).reshape(-1)
                        except Exception:
                            continue
                        n_evaluated += 1
                        # a width seen twice cannot be assigned to one parameter
                        by_width[a.size] = None if a.size in by_width else tuple(
                            float(x) for x in a)

                if m is None:
                    if not has_matrix_param:
                        m = (1.0, 0.0, 0.0, 1.0)      # no matrix parameter: identity
                    elif by_width.get(4):
                        m = by_width[4]
                        matrix_from_program = True
                    else:
                        raise Unsupported("matrix is a program this cannot single out "
                                          "(%d programs, widths %s)"
                                          % (len(fprogs), sorted(k for k in by_width)))
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                tainted = rec.edges[0] in synthetic

                offset = rec.translation
                if offset is None:
                    if offset_is_program:
                        if by_width.get(2):
                            offset = by_width[2]
                        else:
                            raise Unsupported("offset is a program this cannot single out "
                                              "(%d programs, widths %s)"
                                              % (len(fprogs), sorted(k for k in by_width)))
                    elif fprogs and has_matrix_param and (
                            n_evaluated == 0 or
                            n_evaluated - (1 if matrix_from_program else 0) > 0):
                        # WHICH programs remain unread -- the earlier form did not ask.
                        #
                        # It refused whenever the record had any filter program and a matrix
                        # parameter, including when the ONE program present had just been
                        # consumed two branches up as the matrix. Over 1,726 records that
                        # reach here, 1,140 (66.0%) have nothing left unread by then: no
                        # baked matrix, a single 4-wide program, and that program is the
                        # matrix. For those the message was literally false and the offset
                        # is (0, 0) by exactly the path taken when a record has no programs
                        # at all -- the format says there is no baked offset and bit 26 says
                        # it is not a program, so (0, 0) is its answer, not a guess.
                        #
                        # The remaining 34% still refuse and should: 366 have a BAKED matrix
                        # with a program nobody has accounted for, 166 have a
                        # matrix-from-program plus one to four extra, and 54 have a program
                        # that will not evaluate. Their unread programs are 2-wide values
                        # like (8.0, 8.0) and (0.918, 0.918), which are tiling or scale
                        # shaped rather than translation shaped, so assuming (0, 0) there
                        # would be a guess.
                        #
                        # This matters beyond the count: the refusal severs branches. Both
                        # spatially-varying fxmaps chains in `Facade01` (records 484 and 489
                        # at std 0.1998) are stranded behind it, which is how it was found.
                        raise Unsupported("no offset bit set and %d program(s) remain unread"
                                          % (len(fprogs) if n_evaluated == 0 else
                                             n_evaluated - (1 if matrix_from_program else 0)))
                    else:
                        offset = (0.0, 0.0)

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                pos = pos_grid(W, H)
                c = pos - 0.5
                in_x = m[0] * c[:, 0] + m[1] * c[:, 1] + 0.5 + offset[0]
                in_y = m[2] * c[:, 0] + m[3] * c[:, 1] + 0.5 + offset[1]
                in_pos = np.stack([in_x, in_y], axis=-1)

                result = sbsruntime.image_sampler(outputs[rec.edges[0]])(in_pos)
                outputs[i] = to_image(result, W * H, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "levels":
                # Where the five parameters live (levelinlow/levelinhigh/levelinmid/
                # leveloutlow/levelouthigh, each independently baked-or-program) is
                # settled corpus-wide -- FORMAT-NOTES.md, "`levels` joins after all, and
                # the front/back question closes", 174,329/174,396 (99.96%) tail-placement
                # reads, containment-verified against declared Float4 sources 105/132. Not
                # settled by that research, and not re-derived here: the FORMULA itself.
                # This is the standard Photoshop/Substance "Levels" remap -- clamp-normalize
                # to [in_low, in_high], an optional gamma pivot around in_mid, then rescale
                # to [out_low, out_high] -- taken as industry-standard, ubiquitous, known
                # math rather than something needing corpus mining the way the parameter
                # LOCATIONS did. Checked only for internal self-consistency (a controlled
                # ramp input, below), not against a ground-truth reference renderer.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                tainted = rec.edges[0] in synthetic

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)

                src = sbsruntime.image_sampler(outputs[rec.edges[0]])(pos)

                # Compiler default-omission convention (already established for blend
                # mode and blend opacity elsewhere in this file): a parameter left at
                # its default is simply absent from the bytecode. Levels' identity
                # transform is in_low=0, in_mid=0.5, in_high=1, out_low=0, out_high=1.
                DEFAULTS = {'levelinlow': 0.0, 'levelinmid': 0.5, 'levelinhigh': 1.0,
                           'leveloutlow': 0.0, 'levelouthigh': 1.0}
                params = dict(DEFAULTS)
                for name, kind, value in rec.named_parameters:
                    if name not in DEFAULTS:
                        continue
                    if kind == 'baked':
                        params[name] = np.float32(value)
                    else:
                        sbsruntime.SAMPLERS[0] = sbsruntime.image_sampler(outputs[rec.edges[0]])
                        params[name] = to_image(
                            eval_program(asm, value, default_inputs(asm, N), {}, N,
                                        pos=pos, W=W, H=H),
                            N, H, W).reshape(N, -1)[:, :1]

                in_low, in_mid, in_high = (params['levelinlow'], params['levelinmid'],
                                           params['levelinhigh'])
                out_low, out_high = params['leveloutlow'], params['levelouthigh']

                span = in_high - in_low
                span = np.where(np.abs(span) < 1e-6, 1.0, span)
                t = np.clip((src - in_low) / span, 0.0, 1.0)

                mid_norm = np.clip((in_mid - in_low) / span, 1e-4, 1 - 1e-4)
                with np.errstate(all="ignore"):
                    exponent = np.log(0.5) / np.log(mid_norm)
                    gamma_t = np.power(t, exponent)
                t = np.where(np.abs(mid_norm - 0.5) < 1e-6, t, gamma_t)

                result = out_low + t * (out_high - out_low)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "uniform":
                # Where the size expression lives was already known (word[1], if
                # Record.size_or_baked is a program there) but the FILL COLOR was not --
                # this used to raise unconditionally rather than repeat the mistake found
                # elsewhere in this file, treating .programs[-1] as the color and silently
                # producing the size expression's own (8, 8) output tiled across the image.
                #
                # Real specimens close it: the color occupies the N words immediately
                # after the size-expression slot (word[2].. when word[1] holds a program,
                # word[1].. directly when it does not) -- N=1 for a grayscale record
                # (Record.colour False), N=4 (RGBA) for a colour one. Confirmed two ways
                # corpus-wide: (1) 3,392 of 3,428 sampled (98.9%) decode to components in
                # [0, 1] at exactly that position; (2) exact containment against a real
                # paired source, DLG-Tools__US_Flag.sbs -- four DISTINCT declared
                # `outputcolor` constantValueFloat4 values (a dark red, a dark blue, an
                # off-white, pure white) each match a specific record's decoded words to
                # 6+ significant figures, e.g. 0.745098054 0.0431372561 0.192156866 1.
                #
                # The 1.1% residual is a second, unidentified word shape: Record.programs
                # names one program, but the word right after it is not a program either
                # (by Record.programs' own reading) and does not decode as a plausible
                # color -- not guessed at, raised instead like the format's own matrix
                # reading rejects an implausible determinant rather than trust a bad slot.
                has_prog = rec.size_or_baked is not None and rec.size_or_baked[0] == 'program'
                start = 2 if has_prog else 1
                n = 4 if rec.colour else 1
                if len(rec.words) < start + n:
                    raise Unsupported("uniform has no room for a fill color at the "
                                      "expected slot")
                color = np.array(rec.words[start:start + n], dtype=np.uint32).view(np.float32)
                if not np.all((-0.01 <= color) & (color <= 1.01) & (color == color)):
                    raise Unsupported("uniform fill color slot does not decode as a "
                                      "plausible color (%r) -- an unidentified second "
                                      "word shape" % (color.tolist(),))
                color = np.clip(color, 0.0, 1.0).astype(np.float32)

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                result = np.tile(color, (N, 1))
                outputs[i] = to_image(result, N, H, W)

            elif rec.filter_name == "directionalwarp":
                # Parameter LOCATIONS are corpus-verified (FORMAT-NOTES.md,
                # "directionalwarp's parameters are bit-selected, like levels'", 99.92%
                # tail-placement accuracy) and warpangle's UNIT is confirmed directly
                # from real bytecode, not inferred: programs that compute it end in
                # `atan2(...) / 6.28319` -- 3,336 of 3,336 angle-shaped programs divide
                # by 2*pi, i.e. the value is a FRACTION OF A FULL TURN.
                #
                # NOT corpus-verified: the displacement FORMULA itself (this filter's
                # core math is fixed in the engine, not carried in bytecode the way a
                # pixelprocessor's is) and intensity's absolute scale. This implements
                # the standard directional-warp shape -- sample a second, grayscale
                # "intensity map" input, centre it at 0 (0.5 -> no displacement), scale
                # by `intensity` and a fixed direction from `warpangle`, and offset the
                # main input's sampling position by the result -- with intensity taken
                # against a fixed 256-pixel reference scale independent of the record's
                # own resolution, matching the convention several public shader ports of
                # this Substance node use. That constant is NOT re-derived from this
                # corpus and could be wrong by a constant factor; real program-computed
                # `intensity` specimens (DLG-Tools__Rusted_Metal_01 records 13/51/60/
                # 73/74) confirm only that SOME resolution-independent normalization is
                # real -- authors compute intensity as `min(K, K*$size.x/$size.y)` for K
                # from 10 to 128, an aspect-ratio cap wrapped around a per-record
                # constant, not evidence of the divisor itself.
                #
                # Edge order (which input is warped, which supplies the intensity map)
                # is likewise the declared, unverified-at-the-bytecode-level convention:
                # a real paired source (DLG-Tools__Camouflage.sbs) declares this node's
                # connections as `input1` first, `inputintensity` second, matching
                # Record.edges[0]/[1] in that order without independent proof -- the
                # same epistemic stance already taken for blend's destination/source
                # pair. Wrong here means a plausible-looking but misdirected warp, not a
                # crash.
                if len(rec.edges) < 2:
                    raise Unsupported("directionalwarp has fewer than 2 edges")
                for edge_rec in rec.edges[:2]:
                    if edge_rec not in outputs:
                        raise Unsupported("edge -> record %s has no output yet" % edge_rec)
                tainted = any(e in synthetic for e in rec.edges[:2])

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)

                DEFAULTS = {'intensity': 0.0, 'warpangle': 0.0}
                params = dict(DEFAULTS)
                for name, kind, value in rec.named_parameters:
                    if name not in DEFAULTS:
                        continue
                    if kind == 'baked':
                        params[name] = np.float32(value)
                    else:
                        for slot_i, edge_rec in enumerate(rec.edges[:2]):
                            sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(
                                outputs[edge_rec])
                        params[name] = to_image(
                            eval_program(asm, value, default_inputs(asm, N), {}, N,
                                        pos=pos, W=W, H=H),
                            N, H, W).reshape(N, -1)[:, :1]

                intensity, angle = params['intensity'], params['warpangle']

                height = sbsruntime.image_sampler(outputs[rec.edges[1]])(pos)[:, :1]
                signed = 2.0 * height - 1.0
                turn = 2.0 * np.pi * angle
                REFERENCE_PX = 256.0
                disp = signed * intensity / REFERENCE_PX
                in_pos = pos + np.concatenate(
                    [disp * np.cos(turn) * np.ones((N, 1), dtype=np.float32),
                     disp * np.sin(turn) * np.ones((N, 1), dtype=np.float32)], axis=-1)

                result = sbsruntime.image_sampler(outputs[rec.edges[0]])(in_pos)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "gradient":
                # A gradient map: the input's luminance indexes an embedded ramp.
                # `Record.ramp` is decoded and corpus-verified (FORMAT-NOTES.md); what
                # is added here is only the lookup.
                #
                # Which component is the POSITION was not assumed. Over every ramp with
                # 3+ stops, component 0 ascends monotonically in 100% of tables in all
                # four width classes, and no other component does better than 25% -- so
                # component 0 is the stop position and the rest are values.
                #
                # Only the GREYSCALE widths are implemented. The colour widths carry
                # position plus TWO components, not three, so an RGB reading of them
                # would be invention:
                #
                #     (pos, value)                greyscale            603 records
                #     (pos, value, 32768)         greyscale + cls b8 2,683
                #     (pos, v1, v2)               colour                 144   refused
                #     (pos, v1, v2, 32768)        colour + cls bit 8     457   refused
                #
                # The trailing 32768 is constant in 3,175 of 3,175 reads, so the bit-8
                # width adds a field this does not need rather than a channel.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                table = rec.ramp
                if not table:
                    raise Unsupported("gradient record carries no readable ramp")
                if rec.colour:
                    raise Unsupported("colour ramp width carries 2 value components, "
                                      "not 3 -- an RGB reading is not established")
                if isinstance(table[0][0], float):
                    stops = np.array([e[0] for e in table], dtype=np.float32)
                    vals = np.array([e[1] for e in table], dtype=np.float32)
                else:
                    stops = np.array([e[0] for e in table], dtype=np.float32) / 65535.0
                    vals = np.array([e[1] for e in table], dtype=np.float32) / 65535.0
                tainted = rec.edges[0] in synthetic

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                src = sbsruntime.image_sampler(outputs[rec.edges[0]])(pos)
                t = np.clip(src[:, :1], 0.0, 1.0)
                result = np.interp(t.ravel(), stops, vals).astype(np.float32)
                outputs[i] = to_image(result.reshape(N, 1), N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "curve":
                # A per-channel tone curve. `Record.curve_points` is decoded and
                # corpus-verified: six floats per knot, read there as a position pair
                # followed by an incoming and an outgoing tangent, and the first table
                # read out was the identity.
                #
                # The handles are ABSOLUTE positions, not offsets -- a real S-curve knot
                # reads (0.464, 0.382) with handles (0.379, 0.119) and (0.549, 0.645),
                # which brackets the knot on both sides only under the absolute reading.
                # So a segment is the cubic Bezier P0=knot_i, P1=out_i, P2=in_{i+1},
                # P3=knot_{i+1}, and y is found by inverting x(t) for t.
                #
                # NOT verified: that the engine inverts the same way. A Bezier segment is
                # not a function of x in general, and this bisects x(t) rather than
                # solving it, so a curve with a non-monotonic x would differ. Every table
                # read here has ascending x (`curve_points` checks it), where the two
                # agree.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                knots = rec.curve_points
                if not knots or len(knots) < 2:
                    raise Unsupported("curve record carries no readable spline")
                tainted = rec.edges[0] in synthetic

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                src = sbsruntime.image_sampler(outputs[rec.edges[0]])(pos)

                # Sample the spline onto a fixed table once, then look up per pixel --
                # bisecting per pixel would be the same answer far slower.
                TAPS = 1024
                xs, ys = [], []
                for k in range(len(knots) - 1):
                    p0 = (knots[k][0], knots[k][1])
                    p1 = (knots[k][4], knots[k][5])
                    p2 = (knots[k + 1][2], knots[k + 1][3])
                    p3 = (knots[k + 1][0], knots[k + 1][1])
                    u = np.linspace(0.0, 1.0, TAPS // max(1, len(knots) - 1),
                                    dtype=np.float32)
                    b0 = (1 - u) ** 3
                    b1 = 3 * u * (1 - u) ** 2
                    b2 = 3 * u * u * (1 - u)
                    b3 = u ** 3
                    xs.append(b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0])
                    ys.append(b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1])
                cx = np.concatenate(xs)
                cy = np.concatenate(ys)
                order = np.argsort(cx)
                cx, cy = cx[order], cy[order]

                flat = np.clip(src, 0.0, 1.0)
                result = np.interp(flat.ravel(), cx, cy).astype(np.float32)
                outputs[i] = to_image(result.reshape(flat.shape), N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "dirmotionblur":
                # Parameter locations and UNITS are settled: filter 11 declares exactly
                # `intensity` and `mblurangle`, named by containment against the
                # permitted sources (FORMAT-NOTES.md, the filter-naming section), and
                # `mblurangle` is an angle in TURNS -- the same convention confirmed from
                # bytecode for directionalwarp's `warpangle`, where 3,336 of 3,336
                # angle-shaped programs divide by 2*pi.
                #
                # NOT verified, and shared with directionalwarp above: the absolute pixel
                # scale of `intensity`. This uses the same fixed 256-pixel reference and
                # inherits the same possible constant-factor error. Wrong here means a
                # blur of the wrong LENGTH along the right direction, not a wrong shape.
                #
                # The kernel is a straight, uniformly weighted line through the sample
                # point, symmetric about it -- that is what a directional motion blur is,
                # and it is engine math rather than anything carried in this file.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                tainted = rec.edges[0] in synthetic

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)

                DEFAULTS = {'intensity': 0.0, 'mblurangle': 0.0}
                params = dict(DEFAULTS)
                for name, kind, value in rec.named_parameters:
                    if name not in DEFAULTS:
                        continue
                    if kind == 'baked':
                        params[name] = np.float32(value)
                    else:
                        sbsruntime.SAMPLERS[0] = sbsruntime.image_sampler(
                            outputs[rec.edges[0]])
                        params[name] = to_image(
                            eval_program(asm, value, default_inputs(asm, N), {}, N,
                                        pos=pos, W=W, H=H),
                            N, H, W).reshape(N, -1)[:, :1]

                intensity = np.asarray(params['intensity'], dtype=np.float32)
                angle = np.asarray(params['mblurangle'], dtype=np.float32)
                REFERENCE_PX = 256.0
                length = np.clip(np.abs(intensity), 0.0, 256.0) / REFERENCE_PX * 10.0
                turn = 2.0 * np.pi * angle
                sampler = sbsruntime.image_sampler(outputs[rec.edges[0]])

                TAPS = 17
                acc = None
                for k in range(TAPS):
                    f = (k / (TAPS - 1.0)) - 0.5          # -0.5 .. +0.5, centred
                    dx = (length * f) * np.cos(turn)
                    dy = (length * f) * np.sin(turn)
                    off = np.concatenate(
                        [dx * np.ones((N, 1), dtype=np.float32),
                         dy * np.ones((N, 1), dtype=np.float32)], axis=-1)
                    v = sampler(pos + off)
                    acc = v if acc is None else acc + v
                outputs[i] = to_image(acc / float(TAPS), N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "warp":
                # WHERE the intensity is, derived here and corpus-checked: slot
                # 4 + class bit 11. The bit shifts the parameter block by one slot, the
                # same one-slot-per-class-bit growth Record.matrix documents for
                # `transformation`. Grouping warp records by class word, in files whose
                # source declares a distinctive `intensity`:
                #
                #   cls 0x02319 (bit 11 clear) -> slot 4    19 hits, 1 elsewhere
                #   cls 0x02b19 (bit 11 set)   -> slot 5    11 hits, 1 elsewhere
                #   cls 0x02309 (bit 11 clear) -> slot 4     1 hit
                #
                # Applying `4 + bit11`: 31 records hold a value the source declares, 746
                # hold a plausible undeclared one (inlined library warps, whose intensities
                # are not in the paired source at all), 6 are implausible and 0 records are
                # too short. Corpus-wide the slot decodes to a plausible intensity in
                # 2,909 of 2,936 records (99.1%).
                #
                # WHICH edge is which is structural rather than assumed: `EDGES[7]` is
                # [1, 2] and a real specimen (Hard-Science-Old__CrustyLava records
                # 125/128/129/130) has edges[1] = record 123 in every one while edges[0]
                # varies -- one map warping many inputs, which is what a shared gradient
                # input looks like and not what a per-record image input looks like. The
                # paired source names the two connections `input1` and `inputgradient`.
                #
                # NOT corpus-verified, and stated as such the same way `directionalwarp`'s
                # is: the displacement FORMULA and the absolute scale. This takes the
                # standard shape -- displace along the LOCAL GRADIENT of the gradient
                # input, which is what distinguishes `warp` from `directionalwarp`'s fixed
                # angle -- against the same fixed 256-pixel reference. The gradient is a
                # central difference in pixel space, converted to UV by the record's own
                # width and height so a warp does not change strength with resolution.
                if len(rec.edges) < 2:
                    raise Unsupported("warp has fewer than 2 edges")
                for e in rec.edges[:2]:
                    if e not in outputs:
                        raise Unsupported("edge -> record %s has no output yet" % e)
                sl = 4 + ((rec.cls >> 11) & 1)
                if sl >= len(rec.words):
                    raise Unsupported("warp record too short for an intensity slot")
                intensity = float(np.frombuffer(
                    np.uint32(rec.words[sl]).tobytes(), dtype=np.float32)[0])
                if not (intensity == intensity and -1e3 < intensity < 1e3):
                    raise Unsupported("warp intensity slot %d is not a plausible float"
                                      % sl)
                tainted = any(e in synthetic for e in rec.edges[:2])

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)

                gmap = to_image(sbsruntime.image_sampler(outputs[rec.edges[1]])(pos),
                                N, H, W)[:, :, 0]
                # np.gradient returns d/drow, d/dcol; scale each to UV by its own axis
                # length so the displacement is resolution-independent.
                gy, gx = np.gradient(gmap.astype(np.float32))
                REFERENCE_PX = 256.0
                dx = (gx * W / REFERENCE_PX * intensity).reshape(N, 1)
                dy = (gy * H / REFERENCE_PX * intensity).reshape(N, 1)
                in_pos = pos + np.concatenate([dx, dy], axis=-1)

                result = sbsruntime.image_sampler(outputs[rec.edges[0]])(in_pos)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "shuffle":
                # Slot 1 is four selector BYTES, one per output channel, in the order
                # red, green, blue, alpha. A selector 0-3 takes that channel from the
                # first input, 4-7 takes channel (s - 4) from the second.
                #
                # Read off a permitted paired specimen, exact on all five of its records
                # including the values the source leaves at their defaults
                # (SubstanceDesigner__color, 5 source nodes against 5 binary records):
                #
                #   source {channelgreen: 4}            -> R=0 G=4 B=0 A=0   x3
                #   source {channelblue: 4}             -> R=0 G=1 B=4 A=3
                #   source {channelblue: 4, alpha: 5}   -> R=0 G=1 B=4 A=5
                #
                # The undeclared channels come back as 0,1,2,3 -- identity -- which is what
                # a defaults-omitted serialisation predicts, and the declared ones land in
                # the byte their name picks. Corpus-wide the reading holds where it applies:
                # 664 of 1,075 shuffle records have all four bytes <= 7, and of the 411 that
                # do not, 409 are the single-input layout whose EDGE sits in slot 1 -- so
                # slot 1 is not a selector word there and is refused rather than misread.
                # Where those records keep their selectors is not established.
                if len(rec.words) < 2:
                    raise Unsupported("shuffle record too short for a selector word")
                if 1 in (rec.layout[0] or ()):
                    raise Unsupported("shuffle single-input layout: slot 1 is the edge, "
                                      "and where its selectors live is not established")
                w1 = rec.words[1]
                sels = [(w1 >> (8 * k)) & 0xFF for k in range(4)]
                if not all(s <= 7 for s in sels):
                    raise Unsupported("shuffle slot 1 %#010x is not a selector word" % w1)

                nout = 4 if rec.colour else 1
                sels = sels[:nout]
                need = {s // 4 for s in sels}
                for k in sorted(need):
                    if k >= len(rec.edges) or rec.edges[k] is None:
                        raise Unsupported("shuffle wants input %d, which this record "
                                          "does not have" % (k + 1))
                    if rec.edges[k] not in outputs:
                        raise Unsupported("edge -> record %s has no output yet"
                                          % rec.edges[k])
                tainted = any(rec.edges[k] in synthetic for k in need)

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                src = {k: sbsruntime.image_sampler(outputs[rec.edges[k]])(pos)
                       for k in need}

                cols = []
                for s in sels:
                    a = src[s // 4]
                    c = s % 4
                    if c >= a.shape[-1]:
                        # Not silently clamped to an existing channel: a selector naming a
                        # channel the input does not carry means the reading is wrong here,
                        # and a wrong image is worse than a refusal.
                        raise Unsupported("shuffle selects channel %d of an input with "
                                          "only %d" % (c, a.shape[-1]))
                    cols.append(a[:, c:c + 1])
                outputs[i] = to_image(np.concatenate(cols, axis=-1), N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "fxmaps":
                # `fxmaps` is a pattern GENERATOR, not a filter over an input, so it is
                # the one unimplemented branch that unblocks graphs on its own: 13 of the
                # corpus's 34 one-root-cause-away graphs need only this. What it produces
                # is honest but incomplete -- see tools/fxrender.py, which records that
                # 96% of records render flat because `patternsize`'s coordinate space is
                # not established, and that a nicer pattern shape does NOT fix that.
                #
                # Kept behind the same `Unsupported` contract as everything else: a record
                # the FX model does not cover raises rather than returning a wrong image.
                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                # SAMPLERS IS GLOBAL AND NOTHING CLEARS IT, so an FX program that
                # samples index 2 does not necessarily fail -- it may silently read
                # whatever image the LAST record to touch index 2 left behind. A wrong
                # image rather than a refusal, and invisible to every coverage metric,
                # which is the failure this project treats as worse than a crash.
                #
                # 343 records' FX programs carry a samplelum/samplecol, so this is a real
                # population, not a hypothetical. The indices they name are small and
                # edge-slot-shaped: 34 distinct values corpus-wide, 0/1/2 accounting for
                # most, one or two per record. (Read token 1 of the instruction, not token
                # 0 -- token 0 is the coordinate OPERAND, a value reference, and reading it
                # instead produces hundreds of distinct "indices" reaching 2009. See
                # disasm.IMM, which states the order.)
                #
                # So: empty SAMPLERS for the duration, install this record's own edges
                # best-effort, and restore afterwards. Best-effort rather than the
                # pixelprocessor branch's "raise if an edge has no output" -- that guard is
                # right for a FILTER, whose inputs are what it operates on, and wrong for a
                # GENERATOR: most FX-Maps never sample their edges, and demanding the edges
                # first turns records that render today into cascade failures. A program
                # that genuinely needs a missing input still fails, and MissingSampler
                # names the index it wanted.
                #
                # The save/restore is what makes this safe to add: no other branch's
                # sampler state is disturbed, so nothing outside fxmaps can regress.
                saved_samplers = dict(sbsruntime.SAMPLERS)
                sbsruntime.SAMPLERS.clear()
                try:
                    for slot_i, edge_rec in enumerate(rec.edges or ()):
                        if edge_rec in outputs:
                            sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(
                                outputs[edge_rec])
                    try:
                        runner = fxrender.make_runner(asm, rec)
                        pats = fxrender.emissions(rec, runner,
                                                  slots=fxrender.seed_slots(rec, runner))
                    except fxrender.Unmodelled as e:
                        raise Unsupported("fxmaps: %s" % e) from e
                    if not pats:
                        raise Unsupported("fxmaps: emitted no patterns")
                    outputs[i] = fxrender.splat(rec, pats, W, H)
                finally:
                    sbsruntime.SAMPLERS.clear()
                    sbsruntime.SAMPLERS.update(saved_samplers)

            else:
                raise Unsupported("filter %r not implemented" % rec.filter_name)

        except Unsupported as e:
            failures[i] = str(e)
            if verbose:
                print("rec%d (%s): SKIP - %s" % (i, rec.filter_name, e))
        except Exception as e:
            failures[i] = "%s: %s" % (type(e).__name__, e)
            if verbose:
                print("rec%d (%s): ERROR - %s: %s" % (i, rec.filter_name, type(e).__name__, e))

    return outputs, failures, synthetic
