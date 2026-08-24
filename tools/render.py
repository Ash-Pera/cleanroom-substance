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
                # Only mode 0 (blendingmode's low nibble of slot 1 -- FORMAT-NOTES.md,
                # "blendingmode is the low four bits of blend slot 1", corpus-wide
                # falsified range test) is implemented, and even that rests on one
                # UNVERIFIED assumption: which edge is laid UNDER the other. The paired
                # source names the two connections "destination" and "source" (a real
                # specimen's compFilter, LGMLtools__multi_blender) -- Substance's own
                # terms for a standard alpha-over compositing pair -- but nothing here
                # confirms which of edges[0]/edges[1] is which at the bytecode level, so
                # this takes the conventional order (destination = edges[0], source =
                # edges[1], source laid over destination) without independent proof.
                # Wrong here means a plausible-looking but swapped image, not a crash.
                mode = rec.params.get("blendingmode") if rec.params else None
                if mode != 0:
                    raise Unsupported("blend mode %r not implemented (only mode 0)" % mode)
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

                par = rec.parameter
                if par and par[0] == "float":
                    opacity = np.full((N, 1), par[1], dtype=np.float32)
                elif par and par[0] == "program":
                    for slot_i, edge_rec in enumerate(rec.edges):
                        sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(outputs[edge_rec])
                    opacity = to_image(
                        eval_program(asm, par[1], default_inputs(asm, N), {}, N,
                                    pos=pos, W=W, H=H),
                        N, H, W).reshape(N, -1)[:, :1]
                else:
                    raise Unsupported("blend parameter kind %r" % (par,))

                if len(rec.edges) > 2:
                    if rec.edges[2] not in outputs:
                        raise Unsupported("mask edge -> record %s has no output yet"
                                          % rec.edges[2])
                    tainted = tainted or rec.edges[2] in synthetic
                    mask = sbsruntime.image_sampler(outputs[rec.edges[2]])(pos)
                    opacity = opacity * mask[:, :1]

                result = dst * (1 - opacity) + src * opacity
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "uniform":
                # Not implemented: `.programs` for a `uniform` record can be JUST its
                # size expression (Record.parameter == ('program', p)), with no separate
                # program at all for the fill color -- confirmed on a real specimen,
                # where treating .programs[-1] as the color silently produced (8, 8)
                # (the size expression's own output) tiled across the image. Where the
                # color is actually stored for this case (a ramp? a baked slot?) is not
                # investigated, so this raises rather than guess and risk repeating that
                # exact mistake silently.
                raise Unsupported("uniform fill color storage not investigated")

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
