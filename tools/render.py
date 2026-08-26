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

`max_dim` LIES IN THE DIRECTION OF "your decode is broken", and it has now cost two
filters an afternoon each. Any filter whose effect is a RADIUS in pixels scales that
radius with the grid, so a small parameter rounds to zero and the filter becomes an
identity -- `blur` at intensity 0.84 spreads 1 pixel at 256 and none at 64, and `distance`
at 0.14 goes to 0.035. The symptom is a controlled test showing NO EFFECT AT ALL: an
impulse surviving intact, energy and centroid exactly preserved, which reads as a dead or
mislocated parameter rather than as a sampling artifact. Verify a radius-valued filter at
its record's NATIVE resolution before concluding anything about where its parameter lives.

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
import math

import numpy as np
import transpile, sbsruntime, fxrender, distance, assume, manifest


class Unsupported(Exception):
    pass


#: Record indices whose output rests on a LOW-CONFIDENCE parameter read -- a value taken
#: from a slot because containment merely points at it, rather than from a program that
#: names it. Populated by `render`, cleared at the start of each call.
#:
#: This is the same device as `synth_missing_bitmaps` and its `synthetic` set, applied to
#: parameters instead of to pixels: an output built on an invented input is not an
#: ordinary success and should not be counted as one, and neither is an output built on a
#: guessed parameter slot. It is deliberately NOT folded into `synthetic`, which means
#: something narrower -- pixels this renderer invented.
#:
#: WHY IT EXISTS. Containment rates for these slots cannot be read as accuracy, and the
#: reason is a ceilinged denominator: the rate is bounded above by (distinctive values the
#: source declares) / (records the file compiles to), and instancing makes one source node
#: compile to many records, none of which any declaration corresponds to. So `normal`'s
#: slot evidence at 14.6% against a 0.0% control is not "wrong five times in six" -- the
#: control is the load-bearing half and the headline rate is close to meaningless. The
#: honest response is neither to trust it nor to refuse: it is to MARK it, so a sweep can
#: count these separately rather than reporting them as ordinary successes.
LOW_CONFIDENCE = set()


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


def sampler_bindings(asm, rec, outputs):
    """{sampler index: source record} for a record whose images arrive by SAMPLER.

    render.py installs FX-Map samplers from `rec.edges`, keyed by edge slot, which is
    right for the ordinary case and supplies nothing at all for a record that has no
    edges. Those exist and are not marginal: ie_curve record 172 is an `fxmaps` with
    edges=[], 13 programs, and is itself a declared output -- it asks for sampler 0 and
    there is no edge to answer with.

    The binding is the graph's image inputs in MANIFEST DECLARATION ORDER, which is the
    one thing the assembly cannot supply (`manifest.image_inputs_for_output` records why
    record order will not substitute). Only records that are themselves declared outputs
    can be bound, because that is the only case where graph membership is known -- a
    graph's records cannot be recovered by closure, since the whole problem is that these
    inputs are not reachable through edges.

    Returns {} when nothing can be bound, so the caller falls back to edge slots and a
    record that genuinely cannot be resolved still fails rather than sampling whatever
    happens to be nearby.

    EXPECT THIS TO RESOLVE FEW IMAGES, and not because the mapping is wrong: of 120
    graphs with image inputs, 107 have NO manifest default on ANY of them and ship no
    image either, so the record a sampler correctly binds to has nothing to render. What
    this buys is a correct binding where data exists, and an honest failure where it does
    not -- previously indistinguishable from a missing slot.
    """
    try:
        table = asm.outputs()
    except Exception:
        return {}
    uid = next((u for u, _f, _c, i in table if i == rec.index), None)
    if uid is None:
        return {}
    order = manifest.image_inputs_for_output(asm, uid)
    if not order:
        return {}
    by_uid = {}
    for r in asm.records:
        if r.filter_name == 'bitmap' and (r.bitmap or {}).get('kind') == 'graph_input':
            by_uid.setdefault(r.bitmap['uid'], r.index)
    out = {}
    for k, input_uid in enumerate(order):
        src = by_uid.get(input_uid)
        if src is not None and src in outputs:
            out[k] = src
    return out


def graph_input_default(asm, rec):
    """A uniform image from the manifest default for rec's image input, or None.

    A `graph_input` bitmap names an image the USER supplies, and the package ships none:
    of 45 graph-input packages whose original .sbsar is in the tree, zero ship any image
    that is not an `icon*` or `thumbnail`, and both of those are referenced by an `icon=`
    attribute in the manifest -- GUI decoration. So no decode recovers these; corpus-wide
    215 of the 255 affected outputs have no value declared anywhere.

    What IS recoverable is the manifest's `default`, the constant the engine substitutes
    when the input is left unconnected -- the file's own declaration rather than an
    invention. `tools/manifest.py` carries why the assembly header cannot supply it.

    Returns None rather than guessing when no default is declared, which is why this
    fills 50 of 536 graph_input records and refuses the other 486.
    """
    uid = (rec.bitmap or {}).get('uid')
    got = manifest.image_input_defaults(asm).get(uid)
    if got is None:
        return None
    try:
        parts = [float(x) for x in got[0].replace(';', ',').split(',') if x.strip() != '']
    except ValueError:
        return None
    if not parts:
        return None
    ch = 4 if rec.colour else 1
    # A scalar default fills every channel; a vector is taken component-wise and padded
    # with its last value rather than with zero, so `1` and `1,1,1` mean the same thing.
    vals = ([parts[0]] * ch) if len(parts) == 1 else (parts + [parts[-1]] * ch)[:ch]
    return np.full((rec.height, rec.width, ch), 0.0, dtype=np.float32) + np.asarray(
        vals, dtype=np.float32)


def load_pixels_bitmap(asm, rec):
    b = rec.bitmap
    off, size, ch, depth = b['offset'], b['size'], b['channels'], b['depth']
    if b.get('compressed') == 'jpeg':
        # Class-word bit 11 marks a JPEG payload; see Record.bitmap. Untreated, these read
        # as raw pixels and produce entropy-7.7 noise -- 8 of the 9 in the corpus do not
        # even fail, they silently feed that noise downstream.
        #
        # The decode is CHECKED against the record rather than trusted: the stream must
        # decode to exactly the width, height and channel count the record independently
        # declares, which is how the flag was established (9 of 9) and is equally a
        # per-file guard against a stream that is not this record's.
        import io
        import struct as _struct
        from PIL import Image
        p = b['data_offset']
        if asm.data[p:p + 3] != b'\xff\xd8\xff':
            raise Unsupported("bitmap is flagged JPEG but has no JPEG stream at +52")
        # The length is the u32 immediately ahead of the SOI, not a scan for `ff d9`:
        # that byte pair occurs inside entropy-coded data, so scanning can truncate.
        n = _struct.unpack_from('<I', asm.data, p - 4)[0]
        try:
            im = Image.open(io.BytesIO(asm.data[p:p + n]))
            im.load()
        except Exception as e:
            raise Unsupported("bitmap's JPEG payload will not decode: %s" % e)
        got = {'L': 1, 'RGB': 3, 'RGBA': 4}.get(im.mode)
        if got is None:
            raise Unsupported("bitmap's JPEG has an unhandled mode %r" % im.mode)
        # Width and height are checked against the record every time -- a stream that is
        # not this record's image would have to match both by accident. The CHANNEL count
        # is checked only when the class word states one: 45 of the 54 are cls 0x808, whose
        # channel code CHANNELS has no entry for, and for those the JPEG is the only thing
        # that knows. Demanding agreement there would refuse exactly the records this
        # branch exists to recover.
        if (im.size[0], im.size[1]) != (rec.width, rec.height):
            raise Unsupported("bitmap's JPEG is %dx%d, record declares %dx%d"
                              % (im.size[0], im.size[1], rec.width, rec.height))
        if ch is not None and got != ch:
            raise Unsupported("bitmap's JPEG has %d channels, record declares %d"
                              % (got, ch))
        a = np.asarray(im, dtype=np.float32) / 255.0
        return a.reshape(rec.height, rec.width, got)
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


def footprint_scale(m, offset_unused, W_out, H_out, src_shape):
    """How many SOURCE TEXELS one output pixel covers, under matrix `m`.

    A step of one output pixel is (1/W_out, 0) in output-normalised space; the transform
    maps it to (m[0], m[2]) / W_out in input-normalised space, which is that times the
    source's own dimensions in texels. The footprint is the longer of the two axis steps.
    """
    Hs, Ws = src_shape[0], src_shape[1]
    dx = np.hypot(m[0] * Ws / max(W_out, 1), m[2] * Hs / max(W_out, 1))
    dy = np.hypot(m[1] * Ws / max(H_out, 1), m[3] * Hs / max(H_out, 1))
    return float(max(dx, dy))


def prefilter(src, scale):
    """Box-reduce `src` by halves until one texel covers the sampling footprint.

    MINIFICATION WITHOUT THIS IS THE BUG IT EXISTS FOR. A single bilinear tap answers
    "what is the source AT this point"; a minifying transform needs "what is the source
    AVERAGED over the area this output pixel covers", and the two differ by everything
    when the source is sparse. Measured on `Chesterfield` record 128, a 4x zoom-out of a
    source that is exactly 0.5 in 99.79% of its pixels: the 16 output positions land on 4
    distinct texel phases per axis, every one of them on the flat part, and the output is
    constant to 0.00000000. Box-averaging the 8x8 footprint that zoom-out covers gives
    std 0.00293 instead.

    Halving rather than an arbitrary box because a power-of-two chain is exact and needs
    no resampling: each level is the mean of a 2x2 block. It stops on an odd dimension
    rather than padding, which would invent edge texels -- so a 3-wide image simply does
    not reduce, and the caller gets the point sample it would have had anyway.

    NOT ARBITRATED, AND THE ARBITER CANNOT SEE IT. `tools/refcompare.py` scores renders
    against the engine's own exported maps, and every one of its numbers is IDENTICAL with
    and without this function: the change touches 427 records in `Chesterfield` and 30 in
    `RoofTiles` and ZERO declared outputs in either, because the records it affects sit in
    chains that do not reach a scored output. Coverage is unchanged too. The prediction
    made when it was written -- that `normal`'s std would move off 0.0179 toward the
    reference's 0.0968 -- FAILED; the std did not move at all.

    So what is defended here is the PRESENCE of filtering, not this kernel. The old
    behaviour returned an exactly constant image from a varying source, which is wrong
    whatever replaces it, and that part is measured rather than argued. Power-of-two box
    against trilinear against a proper elliptical filter is an open question, and no
    evidence in this repository currently distinguishes them -- so a later reader should
    treat the choice as provisional and should not cite agreement with the engine as
    support for it, because there is none either way.

    DELIBERATELY NOT MARKED in LOW_CONFIDENCE, unlike `uniform.fill` or the FX-Map
    profile. Those name a value the FORMAT does not record and a render depends on
    guessing; this is a resampling decision that applies to every minifying transform
    equally, and the records it touches are no more and no less trustworthy than they were
    when they were being point-sampled. Marking 427 records per file would say something
    false about which readings are in doubt.
    """
    img = src
    while scale >= 2.0 and img.shape[0] >= 2 and img.shape[1] >= 2 \
            and img.shape[0] % 2 == 0 and img.shape[1] % 2 == 0:
        img = 0.25 * (img[0::2, 0::2] + img[1::2, 0::2]
                      + img[0::2, 1::2] + img[1::2, 1::2])
        scale /= 2.0
    return img


def eval_program(asm, start, inputs, slots, N, pos=None, W=None, H=None):
    end = asm.program_span(start)
    if end is None:
        raise Unsupported("program at %d does not resolve a span" % start)
    src = transpile.transpile(asm.data, start, end, "python", "prog")
    scope = {}
    exec(compile(src, "<prog>", "exec"), scope)
    if pos is not None or W is not None or H is not None:
        # W/H WITHOUT pos is the case that was missing, and it is not cosmetic. A
        # parameter program can read `$size` -- `transformation`'s offset routinely does,
        # to express a shift in PIXELS -- and the context is global and sticky, so a
        # caller that passed neither got whatever record happened to be evaluated last.
        # `set_context` ignores None, so the pos-less form sets only the resolution.
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
    #
    # IT IS ALSO THE ONLY MODE THAT SATURATES, and that is measured, not suspected. Over
    # Chesterfield's 356 blend records, the fraction of output pixels clipped to 1.0,
    # by mode:
    #
    #     copy 0.03   multiply 0.18   switch 0.10   overlay 0.25   screen 0.00
    #     subtract 0.00   max 0.00   add 0.00      ADDSUB 0.60, and 18 of its 56
    #                                              records come out uniformly white
    #
    # Per-record on its own inputs it clips 26.8% of pixels high; `d + s - 0.5` clips
    # 19.7% high and `d + s - 1` clips 37.5% LOW instead. None of the three is clean.
    #
    # TWO ATTEMPTS TO ARBITRATE IT, BOTH REPORTED AS FAILURES rather than resolved:
    #
    #   The exported reference maps CANNOT decide this. Rendering every reference package
    #   under each candidate moves 3 of 11 scoreable channels, and all three are
    #   Chesterfield's `basecolor`, which moves only between rendering and NOT rendering
    #   -- no channel has a comparable MAE under two candidates that both produce it. So
    #   there is no candidate the references prefer; `d + s - 0.5` merely happens to keep
    #   an unrelated auto-levels reduction non-degenerate (see the pixelprocessor note on
    #   0/0). Adopting a formula because it unblocks a record is selecting on a side
    #   effect, and it is not done here.
    #
    #   "Authors feed a mode's NEUTRAL value to switch an input off" -- REFUTED BY ITS OWN
    #   CONTROL. Over 6,564 blend operands in the reference packages, mode 4's flat inputs
    #   are 146 at 0.5 and 160 at 1.0, which looks like it favours a 0.5-neutral reading.
    #   But `max`, whose neutral is unambiguously 0.0, shows 160 flat operands at 0.5 and
    #   13 at 0.0. Authors feed 0.5 as a generic constant regardless of mode, so the
    #   statistic does not measure neutrality and cannot be cited for mode 4 either.
    #
    # The mode NUMBER is not in doubt -- see
    # test_filters.test_blendingmode_matches_the_source_that_declares_it, which pairs
    # source nodes to compiled records by a distinctive opacity: 10 declared modes agree,
    # 0 disagree, and 2 nodes that declare no mode decode as 0, pinning `copy` as the
    # default. Only this FORMULA is open.
    4:  ('addsub',     lambda d, s: d + 2.0 * s - 1.0),
    5:  ('max',        lambda d, s: np.maximum(d, s)),        # a.k.a. lighten
    6:  ('min',        lambda d, s: np.minimum(d, s)),        # a.k.a. darken
    # `switch` is handled specially in `apply_blend` -- it is a hard choice between the
    # two inputs driven by opacity, not a per-channel function that opacity then mixes,
    # so running it through the normal lerp would silently turn it into `copy`.
    #
    # A CONSISTENCY CHECK THIS IDENTIFICATION PASSES, and one it could easily have
    # failed: a switch is a branch selector, so its selector should be a graph-level
    # constant rather than a picture. Evaluating the opacity of all 102 mode-7 records in
    # Chesterfield gives a spatially constant value in 102 of 102, and every one is
    # exactly 0.0 or 1.0. A mode misidentified as `switch` would be reading some other
    # filter's per-pixel parameter, and 102 of 102 constants is not what that looks like.
    # Not proof of the number -- the containment test cited under mode 4 does that for
    # the modes it covers, and 7 is not among them -- but it is the reading a wrong
    # identification would have had to survive.
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


def render(asm, precomputed=None, verbose=True, max_dim=None,
           synth_missing_bitmaps=False, stop_after=None):
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
    LOW_CONFIDENCE.clear()
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
                elif b['kind'] == 'graph_input' and \
                        assume.assumed('graph_input.manifest_default', True) and \
                        graph_input_default(asm, rec) is not None:
                    # The manifest declares what the engine substitutes when this image
                    # input is left unconnected, so this is the file's own value, not an
                    # invention. Still LOW_CONFIDENCE: that the substitution is a UNIFORM
                    # of that value is the reading, and it is not verified against an
                    # engine render -- the reference-render arbiter is unusable here.
                    outputs[i] = graph_input_default(asm, rec)
                    LOW_CONFIDENCE.add(i)
                    # (the manifest parse behind this is cached per assembly path; only
                    # the small uniform array is rebuilt, and only for records that have
                    # a default at all -- 50 of 536 corpus-wide)
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
                own_slots = set()
                for slot_i, edge_rec in enumerate(rec.edges):
                    if edge_rec not in outputs:
                        raise Unsupported("edge -> record %s has no output yet" % edge_rec)
                    src_img = outputs[edge_rec]
                    sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(src_img)
                    own_slots.add(slot_i)
                    tainted = tainted or edge_rec in synthetic
                # A pixelprocessor can also reach images by sampler index with no edge at
                # all: ie_curve record 233 has edges=[], asks for sampler 8, and is itself
                # a declared output. Same binding as the fxmaps branch -- see
                # `sampler_bindings`. This branch was nearly missed by scoping the fix to
                # fxmaps; of the four genuine decode-gap records, one is each.
                #
                # TESTED AGAINST `own_slots`, NOT against SAMPLERS membership: unlike the
                # fxmaps branch this one does not clear the global, so a stale entry left
                # by an earlier record would otherwise beat a correct binding here and be
                # invisible -- which is the exact hazard documented in the fxmaps branch.
                for slot_i, src in sampler_bindings(asm, rec, outputs).items():
                    if slot_i not in own_slots:
                        sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(outputs[src])
                        LOW_CONFIDENCE.add(i)
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
                # THE RECORD'S OWN NAMED PARAMETER FIRST. `opacitymult` is what a blend
                # calls its opacity, and `Record.named_parameters` reads it from the slot
                # PARAM_SPEC names -- so where it is baked, it is the value, and no
                # inference is needed. It was being ignored entirely.
                #
                # Found on ChristmasTreeOrnamentSubstance006, whose `roughness` output came
                # out constant 1.0 -- fully matte, for a material whose own thumbnail is a
                # pair of glossy baubles. Record 22 is `add` at opacitymult 0.05 over
                # inputs of mean 0.27 and 0.50, which is ~0.30. What it actually used was
                # the fall-through below: no baked float in `size_or_baked` (that slot
                # holds the size PROGRAM), so it evaluated `filter_programs[-1]` and got
                # 9.0. That is not an opacity, it is log2(512) -- the record is 512 wide
                # and the "opacity" was a size expression. `clip(d + 9*s)` saturates to 1.0
                # everywhere, which is exactly the constant that showed up.
                #
                # Not a one-record fix. Over 25 files and 8,693 blend records, 3,898 carry
                # a baked `opacitymult` and every one of them was being discarded: 3,622
                # fell through to an opacity of 1.0 and 276 to a program. No record has
                # both a baked opacitymult and a float in `size_or_baked`, so this
                # displaces nothing that path was reading. And the values look like what
                # they claim to be -- 3,896 of the 3,898 lie in [0, 1].
                par = rec.size_or_baked
                baked_opacity = next((v for nm, kind, v in (rec.named_parameters or ())
                                      if nm == 'opacitymult' and kind == 'baked'), None)
                if baked_opacity is not None:
                    opacity = np.full((N, 1), float(baked_opacity), dtype=np.float32)
                elif par and par[0] == "float":
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
                # NOW VERIFIED AGAINST A REFERENCE RENDER. This said "not verified
                # against a ground-truth reference render -- none is correlated to a
                # specific record here", which was true until ChesterfieldSofa became
                # scoreable: the matrix header-bit fix took it from 659 non-finite records
                # to 0 and from 1 spatially-varying declared output to 4 (5 with the
                # uniform fill). Treating the stored matrix as the FORWARD transform and
                # sampling with its inverse costs four of the five declared outputs and
                # collapses metallic against the engine's own map from +0.2294 to +0.0250,
                # its lattice going from 10 elements to 1. Backward mapping is right, and
                # what says so is now a correlation rather than an argument from
                # convention. Also checked for INTERNAL
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
                fprogs = rec.filter_programs
                w1 = rec.words[1] if len(rec.words) > 1 else 0
                # THE HEADER SAYS WHETHER A MATRIX IS BAKED, so ask it. `Record.matrix`
                # reads four slots by a rule established at 100% over "the 66,211 records
                # whose slot-1 bit 6 says the matrix is baked" -- its own words -- but it
                # never checks that bit, so for records where the bit is CLEAR it returns
                # whatever those slots happen to hold. Over 6,666 baked matrices here:
                #
                #     bit 6 set     6,628 records    0 with a denormal component   0.00%
                #     bit 6 clear      38 records    4 with a denormal component  10.53%
                #
                # The four detectable ones all read 0x0A42xxxx in the third slot -- a
                # constant high half with a varying low half, a packed pair rather than a
                # float -- and the docstring already notes pointers turning up where a
                # matrix should be. Rejecting on the FLAG rather than on the values also
                # covers the other 34, whose slots may read as plausible numbers while
                # being just as unfounded; a value-plausibility guard catches only the
                # ones that happen to look wrong.
                #
                # It matters out of proportion to 38 records. Such a matrix is
                # near-singular, so it collapses the input to a point and renders a record
                # whose input has spread 0.15 exactly flat. In ChesterfieldSofa that flat
                # zero feeds a pixelprocessor computing v8/v12 with both terms zero -- 0/0
                # -- and the NaN reaches 659 of the 830 records the file renders, including
                # its `height` and `normal` outputs. Honouring the bit takes that file to 0
                # non-finite records and its declared outputs from 1 spatial to 4 of 4.
                m = rec.matrix if (w1 >> 6 & 1) else None
                matrix_from_program = False
                has_matrix_param = bool((w1 >> 6 & 1) or (w1 >> 7 & 1))
                offset_is_program = bool(w1 >> 26 & 1)

                by_width = {}
                n_evaluated = 0
                if (m is None and has_matrix_param) or offset_is_program:
                    for p in fprogs:
                        try:
                            # At the record's DECLARED size, not the (possibly max_dim
                            # capped) grid: `$size` is what the engine would report, and
                            # an offset of `-1.0 / $size.x` means one pixel of the real
                            # output. Evaluating it at a stale 256 while the record is 16
                            # wide gets the shift wrong by 16x, in normalized units that
                            # look perfectly plausible either way.
                            a = np.asarray(eval_program(asm, p, default_inputs(asm, 1),
                                                        {}, 1, W=rec.width,
                                                        H=rec.height)).reshape(-1)
                        except Exception:
                            continue
                        n_evaluated += 1
                        # A 2-wide program returning (log2 W, log2 H) of THIS RECORD'S
                        # OWN declared size is the output-size expression, not a
                        # parameter, and it is skipped before the collision test below.
                        #
                        # This is an identity, not a shape heuristic: `rec.width` and
                        # `rec.height` are read from the record's header with no program
                        # involved, so "the program returns log2 of my own size" is
                        # checkable against something already known. An earlier reading
                        # of this file guessed those (8.0, 8.0) values were "tiling or
                        # scale shaped"; they are 2**8 == 256, the record's own edge.
                        #
                        # WITH THE CONTROL, over 8,473 bit-26 records in 80 files: of
                        # the 7,586 the collision test already resolves, ZERO have an
                        # accepted offset equal to log2-size, so this cannot change an
                        # answer that currently works. Of the 887 it refuses, 825 (93%)
                        # leave exactly one candidate once the size expression is set
                        # aside; 62 stay ambiguous and still refuse.
                        if (a.size == 2 and rec.width and rec.height
                                and abs(float(a[0]) - math.log2(rec.width)) < 1e-6
                                and abs(float(a[1]) - math.log2(rec.height)) < 1e-6):
                            continue
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

                # Integrate over the footprint when the transform MINIFIES. Sampling with
                # one bilinear tap regardless of scale is what made ten records in
                # `Chesterfield`'s basecolor chain return an exactly constant image; see
                # `prefilter`. Magnification is untouched -- there the footprint is under a
                # texel and a tap is the right answer.
                _src = outputs[rec.edges[0]]
                _scale = footprint_scale(m, offset, W, H, np.asarray(_src).shape)
                if _scale >= 2.0:
                    _src = prefilter(np.asarray(_src, dtype=np.float64), _scale)
                result = sbsruntime.image_sampler(_src)(in_pos)
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
                    # THE COLOUR IS NOT IN THE FILE. These are one-word records -- just
                    # the tag, no programs, no colour slot -- distinguishable by class
                    # (neither bit 0 nor bits 8/9 set), and they feed `transformation` in
                    # 329 of 334 consumer links. There is nothing here to decode wrongly;
                    # the value is the engine's default, and this format never records
                    # defaults, which is the same wall the FX-Map parameters hit.
                    #
                    # So it is a CANDIDATE question rather than a decode one, and the only
                    # thing that can answer it is an output to compare against. Under an
                    # open `assume` scope the chosen fill is used and the record is marked
                    # in both USED and LOW_CONFIDENCE; with no scope open it refuses
                    # exactly as before. 111 records in the reference set block here, and
                    # with the FX-Map empty-table default it is one of the two assumptions
                    # that make 14 of the 19 usable reference maps scoreable.
                    # THE DEFAULT IS 0.0, AND THE ENGINE SAID SO. This used to refuse
                    # unless a caller opened an `assume` scope, which was right while
                    # nothing could arbitrate it. Two reference specimens now can, because
                    # in both the fill reaches a declared output as a pure passthrough --
                    # the scored MAE is EXACTLY the candidate, so the candidates are
                    # genuinely separated rather than all washing out:
                    #
                    #   RoofTiles, `metallic` (record 2580), against RoofTiles_Metallic.png
                    #     fill 0.0 -> MAE 0.0000     fill 0.5 -> 0.5000
                    #     fill 0.25 -> 0.2500        fill 1.0 -> 1.0000
                    #
                    #   Stylized_Sandy_Stone_Path, `output_5` (record 1), scored against
                    #   all six of its maps because that package names its outputs
                    #   generically:
                    #     fill 0.0 -> exact match to SandyStoneRoad01_Metallic.png, 0.0000
                    #     fill 0.5 -> best is Normal at 0.0159      fill 1.0 -> AO at 0.0453
                    #
                    # The second is the stronger of the two: the manifest could not name
                    # that output, and matching at 0.0000 identified it as the metallic map
                    # on its own.
                    #
                    # WHAT THIS IS NOT. Both scoring outputs are constant-zero maps -- a
                    # metallic channel for a non-metal material -- so this arbitrates the
                    # DEFAULT FILL and nothing about how a fill combines downstream. It is
                    # still LOW_CONFIDENCE and still marked in assume.USED, because the
                    # value is inferred from behaviour rather than read from the file: the
                    # record stores no colour, and no reading of it will ever produce one.
                    #
                    # Chesterfield cannot arbitrate this and it was tried first: there the
                    # fill changes 6 records and 0 declared outputs, so every candidate
                    # scores identically. An A/B that ties is not evidence for the
                    # incumbent, which is why finding a specimen where it propagates was
                    # the whole task.
                    fill = assume.assumed('uniform.fill', 0.0)
                    v = np.asarray(fill, dtype=np.float32).ravel()
                    if v.size == 1:
                        v = np.repeat(v, n)
                    if v.size != n:
                        raise Unsupported("uniform.fill supplies %d components, record "
                                          "wants %d" % (v.size, n))
                    W, H = rec.width, rec.height
                    if max_dim:
                        W, H = min(W, max_dim), min(H, max_dim)
                    N = W * H
                    outputs[i] = to_image(np.tile(np.clip(v, 0.0, 1.0), (N, 1)), N, H, W)
                    LOW_CONFIDENCE.add(i)
                    assume.note(i)
                    continue
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
                # THE COLOUR RAMP'S TWO VALUES ARE ONE PACKED RGBA8888. This was
                # refused as "2 value components, not 3 -- an RGB reading would be
                # invention", which was right to refuse and wrong about the shape: the
                # entries are u16, so two of them are 32 bits, which is exactly four 8-bit
                # channels rather than two 16-bit ones.
                #
                # The signature is the alpha byte. Reading `v1 | (v2 << 16)` and unpacking
                # little-endian, over 181 colour gradient records and 22,961 stops:
                #
                #     byte 3 == 255      99.9%      (next commonest value: 0, seven times)
                #
                # A misread field does not put 255 in the same byte 99.9% of the time. And
                # the remaining three bytes read as material colours outright -- (197, 143,
                # 76) tan, (139, 92, 38) brown, (243, 211, 167) cream, (179, 85, 19)
                # orange-brown, (253, 253, 253) near-white -- which is what a gradient map
                # for sand, wood and stone should contain.
                #
                # Greyscale ramps are unaffected: their single value stays a u16 scaled by
                # 65535, which is the reading already verified against an independent
                # lookup in test_filters.py.
                if rec.colour:
                    if isinstance(table[0][0], float) or len(table[0]) < 3:
                        raise Unsupported("colour ramp is not in the u16 packed form")
                    stops = np.array([e[0] for e in table], dtype=np.float32) / 65535.0
                    packed = [(int(e[1]) | (int(e[2]) << 16)) & 0xFFFFFFFF for e in table]
                    vals = np.array([[(u >> (8 * k)) & 0xFF for k in range(4)]
                                     for u in packed], dtype=np.float32) / 255.0
                elif isinstance(table[0][0], float):
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
                if vals.ndim == 2:
                    cols = [np.interp(t.ravel(), stops, vals[:, c]).astype(np.float32)
                            for c in range(vals.shape[1])]
                    result = np.stack(cols, axis=-1)
                    outputs[i] = to_image(result, N, H, W)
                else:
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
                # ...AND IT IS THE SAME INHERITED-BLOCK WALK hsl needed, not bit 11 alone.
                # `4 + bit11` froze one term of the mask-walk: the intensity follows the
                # inherited block `walk.py`'s `_CLS` describes, and bits 7 and 10 shift it
                # too. Over the corpus the shift mask is {7, 10, 11} -- searching every
                # subset of the inherited bits {0,7,10,11,13} for the one that best lands a
                # plausible intensity picks exactly these three, and bit 0/13 gate params
                # that sit after the intensity so they never move it. The 592 records that
                # set bit 10 are the proof: at `4 + bit11` a plausible value appears 88.2%
                # of the time, at one slot later 100.0% -- while for bit-10-clear records
                # that later slot is plausible only 5.8%, so bit 10 really does carry the
                # intensity one slot on. Corpus-wide good-value rate 84.6% -> 85.2% (the
                # ceiling is program intensities, which have no baked value to read), and
                # the bit-7/10-clear majority is untouched because the popcount is then just
                # bit 11 -- the old rule, so nothing that decoded before regresses.
                sl = 4 + bin(rec.cls & ((1 << 7) | (1 << 10) | (1 << 11))).count('1')
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
                    # THE SINGLE-INPUT LAYOUT KEEPS NO SELECTOR BYTES. Its selectors were
                    # recorded as "not established", and the reason the earlier search
                    # missed them is that they are not bytes at all: scanning every slot
                    # for a quad of bytes <= 7 finds only all-zero words (324, 314, 368 and
                    # 446 records at slots 3, 4, 5, 6), and an identity byte-quad would
                    # read 0,1,2,3.
                    #
                    # They are a ONE-HOT FLOAT4 at the block start + 1: exactly one 1.0 and
                    # three 0.0, and the position of the 1.0 says which channel to take.
                    # Over 120 files, of 600 single-input shuffle records:
                    #
                    #     one-hot float4   471   78.5%      all zero  14      other  79
                    #
                    # and all 471 are `colour` False -- a greyscale output, which is what
                    # extracting ONE channel produces and is the shape of the claim. The
                    # channel it names is distributed R 31.4%, G 33.8%, B 23.1%, A 11.7%,
                    # which is the ordering channel extraction should show in material
                    # graphs and not what a misread field would give. The multi-input
                    # layout does not do this (21 of 476), so it is specific to the layout
                    # whose slot 1 is already spoken for by the edge.
                    #
                    # Verified end to end rather than by inspection: fed a four-channel
                    # input whose channels are the distinct constants 0.1/0.2/0.3/0.4, a
                    # record whose one-hot names channel k returns exactly that channel.
                    _edges, _start = rec.layout
                    if _start + 4 >= len(rec.words):
                        raise Unsupported("shuffle single-input record too short for a "
                                          "one-hot channel selector")
                    # IT IS A WEIGHT VECTOR, NOT A ONE-HOT SELECTOR -- the one-hot form
                    # is its special case. The generalisation is forced by what the
                    # non-one-hot records hold: of the 79 that this refused as "not
                    # one-hot", the commonest vector is
                    #
                    #     (0.30, 0.59, 0.11, 0.00)   x17    Rec.601 LUMINANCE WEIGHTS
                    #     (0.25, 0.25, 0.25, 0.00)   x10
                    #     (0.00, 0.80, 0.20, 0.00)   x2
                    #
                    # 0.3/0.59/0.11 is the standard RGB-to-grey conversion to two decimal
                    # places. A field that holds the luminance weights is not a selector
                    # that happens to be malformed; it is a weighted sum, and `take channel
                    # k` is that sum with a one at k. So the output is the dot product of
                    # this vector with the input's channels, which reproduces the verified
                    # one-hot behaviour exactly and additionally renders the 29 records
                    # whose weights are a real mixture.
                    #
                    # Vectors that are not plausible weights still refuse: the remainder of
                    # the 79 are infinities and values like 2.9e20, which are a slot that
                    # is not this field at all rather than an unusual mixture.
                    # CLASS BIT 8 SAYS WHETHER THE VECTOR IS THERE, and the value test
                    # below is no substitute for asking. Over 307 single-input records in
                    # 60 files the bit and a plausible-looking float4 agree 302 times
                    # (98.4%), and the five that disagree are the point:
                    #
                    #   4 records have the bit CLEAR and store no vector, but the bytecode
                    #     sitting at that offset decodes to floats the value test accepts
                    #     -- (0.0, -2.0, 3.0, -2.0) and (0.0, -3.0, 4.0, -3.0) among them.
                    #     Those are an opcode word and its inline constants, and rendering
                    #     them as weights produced a picture with no basis at all. This is
                    #     the failure this project keeps finding: a guard on the VALUE
                    #     passes whatever happens to look reasonable, while a guard on the
                    #     format's own presence bit cannot.
                    #
                    #   1 record has the bit SET and reads all-zero at this offset; it
                    #     carries an extra program pointer and its vector is one word
                    #     further on. It still refuses, because where that word is has not
                    #     been established.
                    #
                    # WHICH SOURCE NODE THIS IS. The paired sources settle why one filter
                    # id has two layouts: they declare `grayscaleconversion` (100 nodes,
                    # parameter `channelsweights`, a float4) and `shuffle` (43 nodes,
                    # parameters `channelalpha`/`channelgreen`/`channelblue`, integer
                    # selectors) -- two node types, one compiled filter. The weight-vector
                    # layout is grayscaleconversion and the selector-word layout is
                    # shuffle, which is what the two readings below already were without
                    # knowing their names.
                    if not (rec.cls >> 8) & 1:
                        # No parameter stored, so the value is the node's default and the
                        # default is not in the file -- the same shape as `uniform.fill`
                        # before a specimen arbitrated it.
                        #
                        # BIT 8 MEANS "THE SOURCE DECLARED ONE", confirmed from the sources
                        # rather than inferred from the absence of a slot. Counting
                        # `grayscaleconversion` nodes that declare `channelsweights`
                        # against compiled records with bit 8 clear, over the permitted
                        # paired sources:
                        #
                        #     stylized_rocks_magma   5 nodes, 3 declare -> 2 bit-8-clear
                        #     hblend                10 nodes, 10 declare -> 0
                        #     triDraw                2 nodes,  2 declare -> 0
                        #     RuntimeExtensions      1 node,   1 declares -> 0
                        #     celtic_plate           1 node,   0 declare -> 22
                        #     ...and eleven more files declaring none, all with bit-8-clear
                        #     records
                        #
                        # The first line is the one that carries it: 5 = 3 + 2 exactly, so
                        # the nodes that declare a value are the records that store one and
                        # the nodes that do not are the records with bit 8 clear.
                        #
                        # WHICH IS ALSO WHY THE SOURCES CANNOT SUPPLY THE VALUE. They omit
                        # `channelsweights` precisely when it is the default, so the
                        # declared values (1 0 0 0 x8, 0 1 0 0 x6, 0 0 0 1 x3, 1 1 1 1 x2
                        # ...) are the non-defaults by construction. This is the same wall
                        # the FX-Map parameters hit, reached from the other side.
                        #
                        # AND NO REFERENCE PACKAGE ARBITRATES IT, re-checked after the
                        # blend-opacity fix moved 282 records and changed what propagates.
                        # Only RoofTiles has bit-8-clear shuffles at all (5); three of them
                        # refuse earlier -- "single-input record too short for a one-hot" --
                        # one is blocked upstream, and the one that renders takes a constant
                        # input, so every candidate weight gives an identical image. Zero
                        # declared outputs move between (1,0,0,0) and (0,0,1,0) in any
                        # reference package.
                        #
                        # AND THE MANIFEST DOES NOT CARRY IT EITHER, checked over all 437
                        # rather than assumed from one. The .xml vocabulary is entirely
                        # interface -- graphs, inputs, outputs, channels, GUI widgets,
                        # presets -- and no element describes an internal node at all.
                        # `channelsweights` appears in none of them; `shuffle` in none.
                        #
                        # One manifest mentions `grayscaleconversion`, and it is a trap
                        # worth naming: `GrayscaleConvert.sbsar`, a third-party filter graph
                        # ("Gs Conversion (3 Types)") exposing a `method` combobox that
                        # defaults to 2 = YPrPb (.29, .58, .11). That corroborates the
                        # luminance reading noted above, and it is NOT this node's default:
                        # it is one author's exposed choice in their own graph, which
                        # compiles to a bitmap and a pixelprocessor and does not use the
                        # built-in node at all. Taking .29/.58/.11 from it would be
                        # inferring the engine's default from a third party's imitation.
                        #
                        # So it is asked rather than guessed, and this comment records that
                        # the asking has been tried three times from three directions.
                        w = assume.assumed('grayscale.weights')
                        if w is None:
                            raise Unsupported("shuffle stores no weight vector (class bit "
                                              "8 clear) and its default is not in the file")
                        hot = np.asarray(w, dtype=np.float32).ravel()
                        if hot.size != 4:
                            raise Unsupported("grayscale.weights must be 4 numbers, got %d"
                                              % hot.size)
                        LOW_CONFIDENCE.add(i)
                        assume.note(i)
                    else:
                        hot = np.frombuffer(
                            np.array(rec.words[_start + 1:_start + 5],
                                     dtype=np.uint32).tobytes(), dtype=np.float32)
                    if not (np.all(np.isfinite(hot)) and np.all(np.abs(hot) <= 4.0)
                            and float(np.abs(hot).sum()) > 1e-6):
                        raise Unsupported("shuffle single-input weight vector is not "
                                          "plausible (%r)" % (np.round(hot, 4).tolist(),))
                    if rec.edges[0] not in outputs:
                        raise Unsupported("edge -> record %s has no output yet"
                                          % rec.edges[0])
                    W, H = rec.width, rec.height
                    if max_dim:
                        W, H = min(W, max_dim), min(H, max_dim)
                    N = W * H
                    src = sbsruntime.image_sampler(outputs[rec.edges[0]])(pos_grid(W, H))
                    used = [k for k, w in enumerate(hot) if abs(w) > 1e-9]
                    if used and max(used) >= src.shape[-1]:
                        # Same refusal the multi-input path makes, for the same reason: a
                        # weight on a channel the input lacks means the reading is wrong
                        # here, and a plausible wrong image is the worst outcome.
                        raise Unsupported("shuffle weights channel %d of an input with "
                                          "only %d" % (max(used), src.shape[-1]))
                    w = hot[:src.shape[-1]].astype(np.float32)
                    outputs[i] = to_image((src * w).sum(axis=-1, keepdims=True), N, H, W)
                    if rec.edges[0] in synthetic:
                        synthetic.add(i)
                    continue
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

            elif rec.filter_name == "normal":
                # A normal map from a height input. The permitted sources declare this
                # filter's parameters as `intensity` (61 sightings), `input2alpha` (31,
                # always 0), `format` (3) and `inversedy` (1).
                #
                # WHERE `intensity` IS -- and this is deliberately NOT a fixed slot. An
                # earlier attempt here derived "slot 4 + class bit 11", `warp`'s rule, from
                # containment against 22 permitted files: slot 4 held a value its own file
                # declares in 33.7% of 98 records against a 6.5% control, and bit 11
                # predicted slot 4 versus 5 in 43 of 44. Both numbers were real and the
                # rule was still wrong, because the population was mixed: in most records
                # those slots hold PROGRAM POINTERS, and a pointer read as a float is a
                # denormal, which a naive "is it a plausible float" test accepts. The
                # block starts at slot 3 in 201 of 201 records and carries 1 to 4 leading
                # programs, and no popcount of the class word predicts how many (no mask
                # reaches 90%), so `warp`'s law does not transfer.
                #
                # A CONTROLLED TEST is what caught it and is the reason this reading is
                # different: driving a real record's input with a height RAMP produced a
                # perfectly flat normal map, which a correct implementation cannot do.
                #
                # So intensity is singled out the way `transformation` singles out its
                # matrix and offset -- by evaluating the record's own filter programs and
                # taking the one whose result has the right WIDTH, refusing rather than
                # guessing when that is ambiguous. A width seen twice is not assigned.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                tainted = rec.edges[0] in synthetic

                intensity = None
                by_width = {}
                for prog in rec.filter_programs:
                    try:
                        val = np.asarray(eval_program(asm, prog, default_inputs(asm, 1),
                                                      {}, 1)).reshape(-1)
                    except Exception:
                        continue
                    by_width[val.size] = None if val.size in by_width else float(val[0])
                if by_width.get(1) is not None:
                    intensity = by_width[1]
                else:
                    # No program names it: look for a baked float in the parameter block.
                    # Denormals are excluded explicitly -- they are what a program pointer
                    # looks like when read as a float, and accepting them is the exact
                    # mistake above.
                    #
                    # THIS FALLBACK SURVIVED THE TEST THAT KILLED `blur`'s, and the
                    # asymmetry is the evidence rather than a preference. A parameter with
                    # two readings must have two agreeing distributions, and the SOURCE
                    # DECLARATIONS are a third instrument independent of both:
                    #
                    #     normal   declared p50 4.5, range -0.05..100, commonest
                    #              10, 20, 0.25, 5, 3, 0.5, 16
                    #              block    p50 12, range 0.5..256, commonest
                    #              12, 8, 16, 3, 4, 0.5          <- same regime, and it
                    #              shares the specific values 16, 3 and 0.5 with them
                    #
                    #     blur     declared p50 1.25, clustered 0.2..1.25
                    #              slot 3   72.5% exact powers of two through 64
                    #                                            <- a different quantity
                    #
                    # So blur's is withdrawn and this one is kept and MARKED. It is still
                    # the weaker of `normal`'s two paths and LOW_CONFIDENCE says so on
                    # every record that uses it.
                    _edges, start = rec.layout
                    for sl in range(start, min(start + 8, len(rec.words))):
                        f = float(np.frombuffer(np.uint32(rec.words[sl]).tobytes(),
                                                dtype=np.float32)[0])
                        if np.isfinite(f) and 1e-3 < abs(f) < 1e3:
                            intensity = f
                            LOW_CONFIDENCE.add(i)
                            break
                if intensity is None:
                    raise Unsupported("normal: intensity is neither a single-width "
                                      "program nor a baked float in the block")

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                height = to_image(sbsruntime.image_sampler(outputs[rec.edges[0]])(pos),
                                  N, H, W)[:, :, 0].astype(np.float32)
                # NOT VERIFIED, stated as directionalwarp's is: the FORMULA and
                # intensity's absolute scale. This filter's math is engine-side. The
                # standard height-to-normal shape is used -- central-difference the
                # height, scale by intensity, normalise against a unit Z. `format` (0 vs
                # 3) and `inversedy` are not decoded, so a specimen using the other
                # handedness renders with its green channel inverted rather than failing.
                gy, gx = np.gradient(height)
                nx, ny = -gx * intensity, -gy * intensity
                nz = np.ones_like(nx)
                length = np.sqrt(nx * nx + ny * ny + nz * nz)
                rgb = np.stack([0.5 + 0.5 * nx / length, 0.5 + 0.5 * ny / length,
                                0.5 + 0.5 * nz / length], axis=-1)
                rgb = np.clip(rgb.reshape(N, 3), 0.0, 1.0)
                if rec.colour:
                    rgb = np.concatenate([rgb, np.ones((N, 1), dtype=np.float32)], axis=-1)
                outputs[i] = to_image(rgb, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "blur":
                # An isotropic blur. The source declares exactly ONE real parameter,
                # `intensity` (64 sightings across 18 permitted files, mostly constants),
                # plus a single `randomseed`.
                #
                # WHERE `intensity` IS -- and note what does NOT answer this. PARAM_POPCOUNT
                # establishes `popcount(cls & 0x2881)` as the number of leading block slots
                # holding PROGRAMS, exact over 43,883 slot reads. That is a verified fact
                # about the program/constant SPLIT and it says nothing about which slot is
                # `intensity`. Assuming intensity sits at the block start gives 6.6% own-file
                # containment against a 6.0% control -- no signal at all. Scanning every slot:
                #
                #     slot 2   5.4%  CONTROL  3.6%      slot 5  20.0%  CONTROL  0.0% (n=5)
                #     slot 3  14.6%  CONTROL  2.9%      slot 7   5.9%  CONTROL  0.0%
                #     slot 4   2.9%  CONTROL  0.0%      slot 8   0.0%  CONTROL  0.0%
                #
                # Those are FILE-UNIQUE declared values only. Counting every declared
                # value instead put slot 4 at 10.9% against a 22.4% control -- a value
                # several files share discriminates nothing, and it was inflating a slot
                # that is actually noise. Slot 3 survives the correction at 5x.
                #
                # AND THE RATE ITSELF IS NOT ACCURACY. It is ceilinged by (distinctive
                # values the source declares) / (records the file compiles to), and
                # instancing makes one source node compile to many records that no
                # declaration corresponds to. The 0.0% control is the load-bearing half.
                # The slot is therefore MARKED via LOW_CONFIDENCE rather than trusted.
                #
                # Slot 3 is the only one whose own-file rate exceeds its control materially,
                # at 5x. The low ABSOLUTE rate is expected and is the same effect `warp`'s
                # derivation records: most records are inlined library filters whose
                # parameters are not in the paired source at all.
                #
                # THAT EVIDENCE IS WEAKER THAN THE ONE THAT ALREADY FOOLED ME. `normal` had
                # 33.7% against 6.5% plus a 97.7% bit correlation and was still wrong,
                # because a program pointer read as float32 is a denormal that passes a naive
                # plausibility test. The denormal guard is applied here (1e-3 < |v| < 1e4),
                # but containment alone is not what this rests on -- see test_filters.py,
                # where an impulse must spread symmetrically, a constant must survive
                # unchanged, and the blurred centroid must not move.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                tainted = rec.edges[0] in synthetic
                # WHERE `intensity` ACTUALLY IS -- source-verified, and it is neither of
                # the two places this code looked before.
                #
                # It is the BAKED FLOAT IMMEDIATELY AFTER THE SIZE BLOCK, and the size
                # block is one slot or two depending on how the size is stored:
                #
                #     nprog == 0   size is BAKED as (w, h) at 2,3  -> intensity at slot 4
                #     nprog >= 1   nprog POINTER slots from 2       -> intensity at 2+nprog
                #
                # Read straight off the slot distributions. For nprog >= 1 the leading
                # `nprog` slots read as denormals near 1e-39 -- 188 of 188 at slot 2 for
                # nprog==1, 557 of 557 at slots 2 AND 3 for nprog==2 -- which is what a
                # 4-byte pointer looks like through float32. The slot straight after them
                # carries ordinary small values (0.25, 0.5, 2, 0.125), and the ones after
                # THAT go back to denormals and 3.2e37 junk.
                #
                # The pair reading is not assumed: over nprog==0 blur records slots 2 and 3
                # have near-identical distributions, 99.1% and 100.0% exact powers of two
                # with the same value histogram (16 x128, 32 x94, 64 x94 ...), and in 102
                # of them the two slots equal the record's own width and height.
                #
                # THE PROGRAM WAS NEVER THE INTENSITY. This code read
                # `filter_programs[:1]` and called it that. On `flowingLava` that program
                # evaluates to 1.0 and on `PW_ConcreteWall001` to 2.0 and 0.9428, none of
                # which either source declares -- because it is the SIZE expression. Every
                # program-bearing blur record has been rendering with its own output size
                # as a blur radius.
                #
                # The evidence is exact set recovery, not a rate. `flowingLava` declares 8
                # distinct intensities and slot 3 of its nprog==1 blur records holds
                # exactly those 8, one each (0.0, 0.06, 0.1, 0.2, 0.23, 0.71, 4.47, 4.5);
                # its other 13 such records hold library-internal values the source never
                # mentions. `rural_rock_wall` recovers 5 of 5, `EnvironmentToolkit` 2 of 2,
                # `stylized_rocks_magma` 2 of 2, `RockyPath` 12 of 18.
                #
                # Across every permitted paired source: 39 of 54 declared values recovered
                # (72.2%) against an 11.1% CONTROL that applies the same slot rule to
                # records of other filters. 4 of the 15 misses are files with no blur
                # record at all, so the rate over files that have one is 39 of 50.
                #
                # An earlier version of this stopped at nprog <= 1 and refused the rest,
                # which cost 2,811 records over 8 files -- the rule generalises and there
                # was no reason to refuse them.
                #
                # 0.0 is a legitimate intensity -- `flowingLava` declares it -- and means a
                # blur that does nothing, so it must pass the guard. What must not pass is
                # a program POINTER read as float32, which is a denormal near 1e-38.
                # WHETHER a baked intensity is present at all is stated by CLASS-WORD
                # BIT 12, not inferred from whether the word looks plausible. Found by
                # walk.py's author (a49d08a): over 6,855 blur records, bit 12 is set iff
                # the last header slot is a baked value, 6,855/6,855.
                #
                # It changes no behaviour today and is still worth stating: over 40 files
                # every one of the 34 bit-12-clear records already fails the plausibility
                # guard below, so the guard was reaching the right answer by luck. A word
                # that happened to read as a small float would have been taken as an
                # intensity; with the gate it cannot be, because the record says there
                # isn't one.
                intensity = None
                nprog = bin(rec.cls & 0x2881).count("1")
                _islot = 4 if nprog == 0 else 2 + nprog
                _baked = bool(rec.cls >> 12 & 1)
                if _baked and _islot < len(rec.words):
                    v = float(np.frombuffer(np.uint32(rec.words[_islot]).tobytes(),
                                            dtype=np.float32)[0])
                    if np.isfinite(v) and (v == 0.0 or 1e-6 < abs(v) < 1e4):
                        intensity = v
                # THE SLOT-3 FALLBACK IS WITHDRAWN. It rendered 881 records and it was
                # reading a different field. The instrument that shows this needs no
                # source declarations and no containment, and it was available the whole
                # time: this parameter has TWO readings, and one of them -- the width-1
                # program result -- is trusted. So the two distributions have to agree.
                # Restricted to records where each path actually fires, over 60 files:
                #
                #     from a program   n=53    p50 1.00   1.0 in 43 of 53
                #     from slot 3      n=881   p50 5.00   72.5% are EXACT powers of two,
                #                                         through 2, 4, 8, 16, 32 to 64
                #
                # A ladder of exact powers of two reaching 64 is a size, a mip level or a
                # tiling count. It is not an intensity: the permitted sources declare blur
                # intensity as 1.0, 1.25 and 0.2 across 17 files with no power of two above
                # 1 anywhere. And the consequence of being wrong is not subtle -- slot 3 =
                # 64 asks for a 64-pixel radius on a 256-pixel image, which erases it.
                #
                # Containment said otherwise and containment was the weaker instrument:
                # 14.6% own-file against a 2.9% control survived the shared-value artifact
                # check and still only ever established a 5x ratio on a ceilinged
                # denominator. Two independent instruments now disagree about this slot,
                # so it is refused rather than marked. 881 records stop rendering and
                # nothing is claimed about them, which is the correct price -- this
                # project's own standard is that a plausible wrong image is worse than a
                # refusal, and 881 confidently wrong blurs feeding downstream filters is
                # that failure at scale.
                #
                # The KERNEL is unaffected and stays verified: impulse to a 3x3 box, max
                # exactly 1/9, energy conserved, centroid preserved to 0.01 px. It is the
                # radius that is not established, not the blur.
                # CANDIDATE PATH, never a result. `tools/assume.py` is the shared
                # channel for "render under a named assumption so the engine's own
                # exported map can arbitrate it" -- see its docstring. This one exists to
                # settle whether withdrawing the slot-3 fallback was right: the withdrawal
                # rests on a powers-of-two ladder to 64 against a program-path median of
                # 1.0, which is strong but is still two of us reasoning rather than the
                # engine answering. Anything rendered this way is marked twice, in
                # assume.USED and in LOW_CONFIDENCE.
                # The `assume`-gated slot-3 candidate is gone. It was asking whether
                # slot 3 is the intensity for records where the size is baked; the answer
                # is no, and the reason the old scan saw a powers-of-two ladder there is
                # that slot 3 is the HEIGHT half of the baked size pair. The question it
                # existed to arbitrate has been answered from the sources instead.
                if intensity is None:
                    raise Unsupported(
                        "blur intensity: %s (nprog=%d, slot %d)"
                        % ("class bit 12 clear, so the record states there is no baked "
                           "intensity" if not _baked else
                           "slot does not read as a plausible intensity",
                           nprog, _islot))

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                src = to_image(sbsruntime.image_sampler(outputs[rec.edges[0]])(pos), N, H, W)
                # NOT VERIFIED, and shared with directionalwarp and dirmotionblur: the
                # absolute pixel scale of `intensity`. Same fixed 256-pixel reference, same
                # possible constant-factor error. A separable box blur is used, which is what
                # the parameter means before any kernel shape is assumed; a Gaussian would
                # differ in the tails and nothing here distinguishes them.
                REFERENCE_PX = 256.0
                radius = float(np.clip(abs(intensity), 0.0, 256.0)) / REFERENCE_PX
                rpx = int(round(radius * max(W, H)))
                if rpx < 1:
                    outputs[i] = src            # a blur of sub-pixel radius is the identity
                else:
                    k = 2 * rpx + 1
                    acc = np.zeros_like(src)
                    for d in range(-rpx, rpx + 1):     # separable: rows then columns
                        acc += np.roll(src, d, axis=1)
                    acc /= k
                    out2 = np.zeros_like(acc)
                    for d in range(-rpx, rpx + 1):
                        out2 += np.roll(acc, d, axis=0)
                    outputs[i] = np.clip(out2 / k, 0.0, 1.0)
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
                    own_slots = set()
                    for slot_i, edge_rec in enumerate(rec.edges or ()):
                        if edge_rec in outputs:
                            sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(
                                outputs[edge_rec])
                            own_slots.add(slot_i)
                    # A record with no edge in a slot may still reach an image through the
                    # graph's declared image inputs -- see `sampler_bindings`. Edge slots
                    # WIN where both exist: an edge is this record's own wiring, while the
                    # graph-input order is a fallback for slots the wiring does not cover,
                    # and letting the fallback overwrite real wiring would substitute a
                    # guess for a fact.
                    for slot_i, src in sampler_bindings(asm, rec, outputs).items():
                        if slot_i not in own_slots:
                            sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(
                                outputs[src])
                            LOW_CONFIDENCE.add(i)
                    try:
                        runner = fxrender.make_runner(asm, rec)
                        pats = fxrender.emissions(rec, runner,
                                                  slots=fxrender.seed_slots(rec, runner))
                    except fxrender.Unmodelled as e:
                        raise Unsupported("fxmaps: %s" % e) from e
                    if not pats:
                        # The walk completed and a gate closed the branch -- see
                        # fxrender.emissions. The map's output is its background, which is
                        # what splat produces from an empty pattern list, so fall through
                        # rather than refuse. An empty walk that no gate explains still
                        # raises out of emissions() and never reaches here.
                        pass
                    # `imageindex` names an input to use AS the pattern, so hand the
                    # branch's already-computed edge images to the splatter keyed by edge
                    # SLOT. `fxrender.image_for` takes the index literally and returns
                    # None for a slot we do not supply, in which case it draws the
                    # generated profile -- so an unmappable index degrades to the old
                    # behaviour rather than sampling whatever image is nearest, which
                    # would be a plausible picture from the wrong input.
                    #
                    # NOT a general edge-list index: over 80 files the 133 records whose
                    # patterns all index 0 have SIX edges, and the 27 using index 1 have
                    # THREE. A direct index would not produce that split, so `imageindex`
                    # addresses some subset of the edges that are pattern images, and
                    # which subset is unestablished. Passing every rendered edge under its
                    # own slot is correct for index 0 and leaves index 1 to refuse.
                    images = {slot: outputs[e]
                              for slot, e in enumerate(rec.edges or ())
                              if e is not None and e in outputs}
                    outputs[i] = fxrender.splat(rec, pats, W, H, images=images)
                    if any(e in synthetic for e in (rec.edges or ()) if e is not None):
                        synthetic.add(i)
                finally:
                    sbsruntime.SAMPLERS.clear()
                    sbsruntime.SAMPLERS.update(saved_samplers)

            elif rec.filter_name == "distance":
                # A distance transform. `tools/distance.py` carries the decode: units are
                # pixels at a 256 reference (every declared constant lies in [0, 256] and
                # 11 of 19 are exactly 256), and the kernel is verified by controlled input
                # -- a single lit pixel gives zero at radius 15.81 and 39.96 for R = 16 and
                # 40, exactly 0.500 at R/2, radial spread under 0.016.
                #
                # The PARAMETER is not established and is not guessed: `distance_param`
                # takes a width-1 program result if there is exactly one, else a
                # non-denormal baked float in the block which it marks LOW CONFIDENCE,
                # else raises. See FORMAT-NOTES on why its containment ratio cannot be read
                # as an accuracy and why the two-path control is unavailable here.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                try:
                    val, how = distance.distance_param(
                        rec, lambda p: eval_program(asm, p, default_inputs(asm, 1), {}, 1),
                        {})
                except distance.Unlocated as e:
                    raise Unsupported("distance: %s" % e) from e
                if distance.is_low_confidence(how):
                    LOW_CONFIDENCE.add(i)
                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                # Which edge is the mask is NOT established -- both questions are on the
                # blocked list. Default 0, arbitrable through the assume channel.
                mask_edge = assume.assumed('distance.mask_edge', 0)
                if mask_edge >= len(rec.edges) or rec.edges[mask_edge] not in outputs:
                    mask_edge = 0
                if assume.assumed('distance.mask_edge') is not None:
                    assume.note(i)
                src = outputs[rec.edges[mask_edge]]
                mask = sbsruntime.image_sampler(src)(pos_grid(W, H)).reshape(H, W, -1)[:, :, 0]
                # Radius scales with resolution: 0.14 px at 256 is 0.035 at 64 and the
                # filter becomes a no-op that reads as a dead parameter. See the module
                # docstring's max_dim warning.
                field = distance.distance_field(mask, distance.scale_radius(val, W))
                if assume.assumed('distance.invert', False):
                    field = 1.0 - field
                    assume.note(i)
                outputs[i] = to_image(field.reshape(-1, 1), W * H, H, W)
                if rec.edges[mask_edge] in synthetic:
                    synthetic.add(i)

            elif rec.filter_name == "hsl":
                # THE PARAMETERS ARE STATED, and which bit names which is settled by
                # containment against a paired source rather than by guessing. The class
                # word is a presence mask exactly as walk.py describes: one float32 field
                # per set bit, at words[3..] in ASCENDING BIT ORDER.
                #
                #     cls bit  8  hue          0x1019 -> 1 param
                #     cls bit 10  saturation   0x1419 -> 2 params
                #     cls bit 12  luminosity   0x1519 -> 3 params
                #
                # SBRustyTreadPlate declares six hsl nodes and all six match a record
                # exactly, 6 of 6, across the one-, two- and three-parameter shapes. The
                # ordering is the part that could only come from containment: the source
                # lists `luminosity` before `saturation` on several nodes, and the record
                # always stores saturation first -- so the layout follows the bit order,
                # not the order the author wrote.
                #
                # WHAT IS DECODED AND WHAT IS MODELLED, kept apart. The parameters and
                # their positions are read from the file. The transform applied with them
                # is a reading: hue as a shift in turns, saturation and luminosity as
                # offsets, each neutral at 0.5. Neutrality is checkable and is the reason
                # to prefer it -- a record with every parameter at 0.5 must be the
                # identity, and the corpus's values cluster tightly around 0.5.
                if not rec.edges or rec.edges[0] not in outputs:
                    raise Unsupported("edge has no output yet")
                # WHERE THE BLOCK STARTS is not a constant, and reading it as one cost
                # every hsl record whose class word omits the inherited parameter. The
                # fields follow the INHERITED block that `walk.py`'s `_CLS` describes:
                # class bits below 8 each contribute their own slots first, and only then
                # do hue/saturation/luminosity begin.
                #
                # `SBRustyTreadPlate` -- the specimen whose six nodes fixed the bit->name
                # mapping by containment -- has bit 0 SET, so its parameters really do
                # start at word 3, and the fixed 3 was right for it and read as a general
                # law. `PaymentCardSubstance001` has bit 0 clear and its hsl records are
                # three words long: [tag][edge][0.333]. There is no word 3 to read, so all
                # six of them refused, and with them 120 cascaded records including five of
                # the file's six outputs.
                #
                # Over 80 files, on hsl records that set at least one parameter bit:
                #
                #     start = 2 + inherited slots   59 of 59 decode inside [0, 1]
                #                                   51 of 59 within 0.25 of neutral 0.5
                #     CONTROL, the fixed 3          40 in range, and 19 records are too
                #                                   short for slot 3 to exist at all
                #
                # The tight clustering around 0.5 is the same neutrality check the reading
                # below rests on, so it is evidence about the position as well as the
                # values: a wrong offset does not land on a neutral-looking distribution.
                src = np.asarray(outputs[rec.edges[0]], dtype=np.float32)
                # ...AND THE WALK MUST COUNT EVERY COST-BEARING BIT, not just the
                # inherited two and the three named here. The cost model fits hsl at
                # const 2 with one word per set cls bit for bits 0, 7, 8, 9, 10, 11, 12
                # and 13 -- 74 keys, 100.000% exact -- so bits 9, 11 and 13 occupy slots
                # too, and they are common: set on 258, 246 and 263 of the 747 hsl
                # records. Advancing one slot per NAMED bit skips them, and the walk
                # comes out short whenever one sits below the parameter being read.
                #
                # It is 16 reads of 593, and every one of them is decisive:
                #
                #     sequential walk   reads exactly 0.0000 in 16 of 16
                #     popcount walk     0.53 0.49 0.61 0.80 0.76 0.42, and 1.00 x10
                #
                # Sixteen exact zeros is not a distribution of parameters, it is the
                # wrong word read sixteen times. mesh_accretions record 200 has cls
                # 0x0608 -- bits 3, 9 and 10 -- so saturation sits one past where a
                # sequential walk puts it, and 1.00 is a legitimate extreme where 0.0
                # is the padding behind it.
                COST_BITS = (0, 7, 8, 9, 10, 11, 12, 13)
                vals = {}
                for bit, name in ((8, 'hue'), (10, 'saturation'), (12, 'luminosity')):
                    if not (rec.cls >> bit) & 1:
                        continue
                    sl = 2 + sum(1 for q in COST_BITS
                                 if q < bit and (rec.cls >> q) & 1)
                    if sl >= len(rec.words):
                        raise Unsupported("hsl mask names slot %d, record has %d"
                                          % (sl, len(rec.words)))
                    f = np.frombuffer(np.array([int(rec.words[sl])],
                                               dtype=np.uint32).tobytes(),
                                      dtype='<f4')[0]
                    if not np.isfinite(f) or abs(f) > 1e3:
                        raise Unsupported("hsl %s slot is not a plausible float" % name)
                    vals[name] = float(f)
                h_sh = vals.get('hue', 0.5) - 0.5
                s_sh = vals.get('saturation', 0.5) - 0.5
                l_sh = vals.get('luminosity', 0.5) - 0.5
                a = src.reshape(src.shape[0], src.shape[1], -1).astype(np.float32)
                if a.shape[2] >= 3:
                    r0, g0, b0 = a[:, :, 0], a[:, :, 1], a[:, :, 2]
                    mx = np.maximum(np.maximum(r0, g0), b0)
                    mn = np.minimum(np.minimum(r0, g0), b0)
                    L = (mx + mn) / 2.0
                    d = mx - mn
                    S = np.where(d < 1e-9, 0.0,
                                 d / np.maximum(1e-9, 1.0 - np.abs(2.0 * L - 1.0)))
                    # `dd` is the guarded denominator: where d is 0 the pixel is grey,
                    # `m` is False and the sector value is discarded, so the guard only
                    # keeps the arithmetic finite rather than changing any kept result.
                    m = d > 1e-9
                    dd = np.maximum(1e-9, d)
                    H = np.select([m & (mx == r0), m & (mx == g0), m],
                                  [((g0 - b0) / dd) % 6.0,
                                   ((b0 - r0) / dd) + 2.0,
                                   ((r0 - g0) / dd) + 4.0], default=0.0) / 6.0
                    H = (H + h_sh) % 1.0
                    S = np.clip(S + 2.0 * s_sh, 0.0, 1.0)
                    L = np.clip(L + l_sh, 0.0, 1.0)
                    C = (1.0 - np.abs(2.0 * L - 1.0)) * S
                    Hp = H * 6.0
                    X = C * (1.0 - np.abs((Hp % 2.0) - 1.0))
                    z = np.zeros_like(C)
                    # NOT `i` -- that is the record index this branch writes its output
                    # under, and shadowing it made `outputs[i] = ...` key the dict by an
                    # array. The failure was loud, but only because the key was unhashable;
                    # a scalar sector index would have silently written the wrong record.
                    sec = np.floor(Hp).astype(np.int32) % 6
                    pick = [sec == k for k in range(6)]
                    rr = np.select(pick, [C, X, z, z, X, C])
                    gg = np.select(pick, [X, C, C, X, z, z])
                    bb = np.select(pick, [z, z, X, C, C, X])
                    mfix = L - C / 2.0
                    out = a.copy()
                    out[:, :, 0] = np.clip(rr + mfix, 0.0, 1.0)
                    out[:, :, 1] = np.clip(gg + mfix, 0.0, 1.0)
                    out[:, :, 2] = np.clip(bb + mfix, 0.0, 1.0)
                else:
                    # A GREYSCALE record has no hue or saturation to move; only the
                    # luminosity term can act, and applying the others would be inventing
                    # a colour the input does not carry.
                    out = np.clip(a + l_sh, 0.0, 1.0)
                outputs[i] = out.reshape(src.shape)
                LOW_CONFIDENCE.add(i)
                if rec.edges[0] in synthetic:
                    synthetic.add(i)

            elif rec.filter_name == "dyngradient":
                # `gradient` with the ramp supplied as an IMAGE rather than an embedded
                # table. Handed over by a parallel session with the edge roles established
                # and the sampling formula explicitly not:
                #
                #   edge 0   size EQUALS the record's own size in 373 of 373 (100.0%)
                #   edge 1   aspect ratio 128:1 at p10, p50 and p90; 97.9% at least 8x
                #            wider than tall; SHARED, one strip feeding 4, 8 and 16
                #            records in a file -- a palette, not a per-record input
                #
                # It needs no parameter located, which is why containment found zero
                # declaring files and the two-path control found zero programs: the filter
                # has no numerics to declare. 288 of 294 records carry no filter program
                # at all.
                #
                # THE ROW CAVEAT IS CLOSED. This branch was written when "a strip that is
                # a multi-row palette could take the wrong row" was an open risk. Measured
                # since: the strips' ROW-TO-ROW difference is exactly 0.000000 -- all 16
                # rows identical, varying only along x (max step 0.2516) -- so there is no
                # multi-row palette and any row is the same row. `Rock 3` records 220, 277,
                # 335 and 393 all share ramp record 219 at 2048x16, whole file rendering
                # 628 of 628.
                #
                # ESTABLISHED: the edge roles, and that the source's value indexes the
                # ramp. Driving both edges through `precomputed` -- see
                # test_dyngradient_is_a_ramp_lookup:
                #
                #     identity ramp, x-ramp source  ->  output reproduces the source
                #     REVERSED ramp                 ->  output = 1 - source
                #     step ramp                     ->  exactly two distinct values
                #
                # The reversed case is the one that carries it: a renderer ignoring the
                # ramp and passing the input through passes the first test and fails that
                # one. The step case rules out blending -- a lookup gives two levels.
                #
                # STILL A CHOICE: indexing by channel 0 rather than a luminance mix. 292 of
                # 294 of these records are greyscale so the two coincide almost everywhere,
                # and channel 0 is what the format stores rather than a mix this would be
                # inventing. The two colour records are where it could matter, untested.
                if len(rec.edges) < 2 or any(e not in outputs for e in rec.edges[:2]):
                    raise Unsupported("edge has no output yet")
                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                idx = sbsruntime.image_sampler(outputs[rec.edges[0]])(
                    pos_grid(W, H)).reshape(H, W, -1)[:, :, 0]
                strip = np.asarray(outputs[rec.edges[1]], dtype=np.float32)
                if strip.ndim == 2:
                    strip = strip[:, :, None]
                sh, sw = strip.shape[0], strip.shape[1]
                along_x = sw >= sh              # the long axis is the ramp
                n = sw if along_x else sh
                k = np.clip((np.clip(idx, 0.0, 1.0) * (n - 1)).round().astype(int), 0, n - 1)
                mid = (sh // 2) if along_x else (sw // 2)
                ramp = strip[mid, :, :] if along_x else strip[:, mid, :]
                outputs[i] = to_image(ramp[k.ravel()], W * H, H, W)
                if any(rec.edges[j] in synthetic for j in (0, 1)):
                    synthetic.add(i)

            else:
                raise Unsupported("filter %r not implemented" % rec.filter_name)

            # NON-FINITE IS NOT A RENDER. An output map is 8- or 16-bit integer and has
            # no NaN, so whatever the engine does with a zero divisor it does not emit
            # one; an array carrying NaN or inf is silent garbage, not a picture. Emitting
            # it is worse than refusing, because every consumer inherits it and still
            # counts as rendered: ChesterfieldSofa record 119 computes v8/v12 with both
            # terms zero and its NaN reached 659 of the 830 records that file rendered,
            # including two declared outputs, none of which reported a failure.
            #
            # Refusing here costs coverage and makes what remains honest -- the same
            # trade as `blur`'s withdrawn fallback. The failure names this record, so a
            # blocker census points at the cause rather than at the 659 records
            # downstream of it, which is the difference between a root and a cascade.
            if i in outputs:
                arr = np.asarray(outputs[i])
                if arr.size and not np.all(np.isfinite(arr)):
                    del outputs[i]
                    synthetic.discard(i)
                    LOW_CONFIDENCE.discard(i)
                    raise Unsupported("produced non-finite values (%.1f%% of samples)"
                                      % (100.0 * float(np.mean(~np.isfinite(arr)))))
        except Unsupported as e:
            failures[i] = str(e)
            if verbose:
                print("rec%d (%s): SKIP - %s" % (i, rec.filter_name, e))
        except Exception as e:
            failures[i] = "%s: %s" % (type(e).__name__, e)
            if verbose:
                print("rec%d (%s): ERROR - %s: %s" % (i, rec.filter_name, type(e).__name__, e))

        if stop_after is not None and i >= stop_after:
            # A caller that wants ONE record's output does not need the rest of the
            # file. Edges point backward -- a record's inputs are always at lower
            # indices -- and evaluation is a single forward pass with no state that a
            # later record could feed back, so stopping here returns exactly what a
            # full render would have put in outputs[stop_after]. This is an early
            # stop, NOT a dependency-cone prune: pruning by Record.edges would be
            # unsafe, because the manifest oracle measured that closure as a strict
            # SUBSET of the real dependencies (513 paths missed, 0 over-claimed) --
            # samplers reach images without an edge, and a cone walk would silently
            # drop them.
            break

    return outputs, failures, synthetic
