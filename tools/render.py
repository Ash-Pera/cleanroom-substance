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
import transpile, sbsruntime


class Unsupported(Exception):
    pass


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
        except KeyError as e:
            # `inputs` is keyed by uid (large, from default_inputs) and always fully
            # populated from the package's own declarations; `slots` is keyed by small
            # integers and is the only one a bare KeyError here can mean -- a `get` of a
            # slot this record's own programs never `set`. The already-documented
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
                slots = {}
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
                # A second UNVERIFIED assumption, independent of the mode question and
                # unchanged here: which edge is laid UNDER the other. The paired source
                # names the two connections "destination" and "source" (a real
                # specimen's compFilter, LGMLtools__multi_blender) -- Substance's own
                # terms for a standard alpha-over compositing pair -- but nothing here
                # confirms which of edges[0]/edges[1] is which at the bytecode level, so
                # this takes the conventional order (destination = edges[0], source =
                # edges[1], source laid over destination) without independent proof.
                # Wrong here means a plausible-looking but swapped image, not a crash --
                # and now that asymmetric modes (subtract, divide, overlay) are
                # implemented, a swap is no longer invisible the way it was under mode 0
                # alone, so this is the assumption a real corpus test should attack first.
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
                        slots = {}
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
                m = rec.matrix
                fprogs = rec.filter_programs
                if m is None:
                    if fprogs:
                        raise Unsupported("matrix is not baked (computed by a program of "
                                          "unidentified shape)")
                    m = (1.0, 0.0, 0.0, 1.0)
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                tainted = rec.edges[0] in synthetic

                offset = rec.translation
                if offset is None:
                    if fprogs:
                        raise Unsupported("translation is a program, and which of "
                                          "%d programs computes it is not identified"
                                          % len(fprogs))
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
