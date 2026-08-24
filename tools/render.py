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
    dtype = "<u1" if depth == 8 else "<u2"
    maxval = float((1 << depth) - 1)
    arr = np.frombuffer(asm.data[off:off + size], dtype=dtype)
    arr = arr.reshape(rec.height, rec.width, ch) if ch and ch > 1 else \
          arr.reshape(rec.height, rec.width, 1)
    return arr.astype(np.float32) / maxval


def pos_grid(W, H):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.stack([(xx.ravel() + 0.5) / W, (yy.ravel() + 0.5) / H], axis=-1)


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
        out = scope["prog"](inputs=inputs, slots=slots)
    return np.asarray(out)


def render(asm, precomputed=None, verbose=True):
    """Evaluate every record 0..N-1 that a filter type here can handle.

    `precomputed` pre-seeds outputs for records the walker cannot compute itself (e.g. a
    graph-input bitmap) -- {record_index: (H, W, C) array}. Returns {record_index: array}
    for every record that ended up with an output, and a separate {record_index: reason}
    for every one that did not.
    """
    outputs = dict(precomputed or {})
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
                else:
                    raise Unsupported("bitmap kind %r has no supplied output" % b['kind'])

            elif rec.filter_name == "pixelprocessor":
                W, H = rec.width, rec.height
                N = W * H
                pos = pos_grid(W, H)
                for slot_i, edge_rec in enumerate(rec.edges):
                    if edge_rec not in outputs:
                        raise Unsupported("edge -> record %s has no output yet" % edge_rec)
                    src_img = outputs[edge_rec]
                    sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(src_img)
                progs = rec.filter_programs
                if not progs:
                    raise Unsupported("no filter_programs")
                main = progs[-1]
                inputs = default_inputs(asm, N)
                out = eval_program(asm, main, inputs, {}, N, pos=pos, W=W, H=H)
                if out.ndim == 1:
                    out = out[:, None]
                outputs[i] = out.reshape(H, W, out.shape[-1])

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

    return outputs, failures
