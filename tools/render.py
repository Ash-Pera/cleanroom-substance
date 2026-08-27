"""Walk an Assembly's record graph in index order and evaluate what it can.

Records are processed 0..N-1 -- verified corpus-wide (353,068/353,068 edges
sampled) that every edge points to a strictly earlier record index, so a single
forward pass suffices and nothing needs a topological sort. Each edge is wired to
the already-computed source record's output via `sbsruntime.image_sampler`, with
one dict shared across every record's `cache_read`/`cache_write`. Filter types with
no implementation raise `Unsupported` by name rather than guess -- confirmed on a
real specimen that a `uniform` record's own `.programs` entry can be its SIZE
expression with no separate program for the fill colour at all, so treating
`.programs[-1]` as the colour produced a plausible-looking but wrong tiled image.

No embedded-pixel `bitmap` in the corpus co-occurs with `cache_read`/`cache_write`
while staying inside {bitmap, pixelprocessor, uniform}, so the cache wiring is
verified separately -- two sequential calls through one `use_shared_cache` dict --
rather than end to end on a real file.

`max_dim` LIES IN THE DIRECTION OF "your decode is broken", and it has now cost two
filters an afternoon each. Any filter whose effect is a RADIUS in pixels scales
that radius with the grid, so a small parameter rounds to zero and the filter
becomes an identity -- `blur` at intensity 0.84 spreads 1 pixel at 256 and none at
64, and `distance` at 0.14 goes to 0.035. The symptom is a controlled test showing
NO EFFECT AT ALL: an impulse surviving intact, energy and centroid exactly
preserved, which reads as a dead parameter rather than a sampling artifact. Verify
a radius-valued filter at its record's NATIVE resolution first. `max_dim` also
costs one real inaccuracy: capping each pixelprocessor's OWN size independently
does not preserve two DIFFERENT records' size ratio to each other, and the cache
shares a raw per-pixel array with no position-based resampling. Rendering a single
file for real output should leave it unset.

A corpus-wide sweep also found NaN in a small, consistent minority of real
pixelprocessor outputs, always traced to `sqrt(1 - dot(v, v))` -- reconstructing a
normal map's Z from its XY -- where nothing in the bytecode clamps the input to be
non-negative. Not a transpiler defect: `np.sqrt` of a negative number is the
correct IEEE-754 answer and matches the math the compiled program performs, and
there is no evidence here for what the real engine does at that input.
"""
import math
import os
import re

import numpy as np
import transpile, sbsruntime, fxrender, distance, assume, manifest, decompose
import record_layout


class Unsupported(Exception):
    #: True when this failure is only the shadow of an upstream one -- a record whose
    #: input was never produced. Set by `cascade()`; collected by `render` in `CASCADED`.
    cascade = False


#: Record indices whose output rests on a LOW-CONFIDENCE parameter read -- a value
#: taken from a slot because containment merely points at it, rather than from a
#: program that names it. Populated by `render`, cleared at the start of each call.
#:
#: The same device as `synth_missing_bitmaps` and its `synthetic` set, applied to
#: parameters instead of pixels: an output built on a guessed parameter slot is not
#: an ordinary success. Deliberately NOT folded into `synthetic`, which means
#: something narrower -- pixels this renderer invented.
#:
#: WHY IT EXISTS. Containment rates for these slots cannot be read as accuracy: the
#: rate is ceilinged by (distinctive values the source declares) / (records the
#: file compiles to), and instancing makes one source node compile to many records
#: that no declaration corresponds to. So `normal`'s slot evidence at 14.6% against
#: a 0.0% control is not "wrong five times in six" -- the control is the
#: load-bearing half. The honest response is to MARK it.
LOW_CONFIDENCE = set()



#: Records that failed ONLY because an input of theirs failed. `failures` still holds a
#: message for each; this says which of those messages are consequences. A root-cause
#: analysis wants `set(failures) - CASCADED`.
CASCADED = set()
# THE SLOT FRAME IS PER-RECORD. Every record evaluates against its own empty dict,
# and nothing carries across records. There is no `SplitFrame` and no shared floor
# any more; what follows is why, because the class that used to be here was not
# obviously wrong.
#
# The reading it encoded: an FX-Map's entry programs are dominated by `get <slot>`
# while its node programs do the `set`s, and the two sets were measured to coincide
# within a FILE rather than within a record -- 74.7% against a 52.2% control over
# all slots, and 88.1% against 0.0% for slots >= 64. So slots >= 64 were shared
# graph-wide and slots below it kept per-record: the floor was put where the control
# went to zero, which is the right instinct applied to the wrong measurement. The
# UNIT was wrong. An FX-Map is a record, not a file. Asked per record, over 61,384
# entry-program slot reads in 282 files, counting as writes only the node chain and
# the record's own programs:
#
#     same RECORD                 61,318 / 61,384    99.892%
#     OTHER record, same file      7,245 / 61,384     11.8%   <- the real control
#     other FILE                  54,930 / 61,384     89.5%   <- what 52-54% was
#
# Cross-FILE collision is 89.5% because small slot indices collide everywhere,
# which is why the file-level figure stalled at 74% and needed a floor to say
# anything. Against an 11.8% control the per-record answer is unambiguous at EVERY
# slot range, and the 0.108% that does not resolve in-record is one construct, not
# a channel between records: 22 records in 5 files, always a lone `0x18B` node.
#
# Going the other way is still wrong: making the whole frame graph-wide regressed
# 87 record outputs on `pairs2` and gained none, rooted in 9 `dirmotionblur`
# records that inherited a stale 0 and raised ZeroDivisionError.


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
    right for the ordinary case and supplies nothing for a record that has no edges.
    Those exist and are not marginal: ie_curve record 172 is an `fxmaps` with edges=[],
    13 programs, and is itself a declared output.

    The binding is the graph's image inputs in MANIFEST DECLARATION ORDER, the one
    thing the assembly cannot supply. Only records that are themselves declared outputs
    can be bound, because that is the only case where graph membership is known -- a
    graph's records cannot be recovered by closure, since the whole problem is that
    these inputs are not reachable through edges. Returns {} when nothing can be bound.

    EXPECT THIS TO RESOLVE FEW IMAGES, and not because the mapping is wrong: of 120
    graphs with image inputs, 107 have NO manifest default on ANY of them and ship no
    image either. What this buys is a correct binding where data exists and an honest
    failure where it does not -- previously indistinguishable from a missing slot.
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


def cascade(message):
    """An `Unsupported` that means "an input of mine has no output", not "I am wrong".

    THIS DISTINCTION WAS A STRING MATCH AND IT WAS WRONG. Callers separating causes
    from consequences looked for the substring "has no output yet", which fourteen
    raise sites use -- and missed the fifteenth, which says "no sampler for input 0"
    and means exactly the same thing. The cost was not theoretical: an `fxmaps` record
    in `WoodSubstance005` was reported as a root cause and named to another session as
    the blocker for that specimen, when it was three levels downstream of the real one.

    So the classification is carried on the exception rather than in its prose, and
    `render()` collects it in `CASCADED`. The message still says "has no output yet"
    everywhere, because prose that agrees with the flag is worth more than prose that
    merely does not contradict it.
    """
    exc = Unsupported(message)
    exc.cascade = True
    return exc



def graph_input_default(asm, rec):
    """A uniform image from the manifest default for rec's image input, or None.

    A `graph_input` bitmap names an image the USER supplies, and the package ships
    none: of 45 graph-input packages whose original .sbsar is in the tree, zero ship
    any image that is not an `icon*` or `thumbnail`, both referenced by an `icon=`
    attribute -- GUI decoration. So no decode recovers these; corpus-wide 215 of the
    255 affected outputs have no value declared anywhere.

    What IS recoverable is the manifest's `default`, the constant the engine
    substitutes when the input is left unconnected. `tools/manifest.py` carries why the
    assembly header cannot supply it. Returns None rather than guessing when no default
    is declared, which is why this fills 50 of 536 records and refuses the other 486.
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
        # declares, which is how the flag was established (9 of 9).
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
        # Width and height are checked against the record every time -- a stream that is not
        # this record's would have to match both by accident. The CHANNEL count is checked
        # only when the class word states one: 45 of the 54 are cls 0x808, whose channel code
        # CHANNELS has no entry for, and demanding agreement there would refuse exactly the
        # records this branch exists to recover.
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
        # (cls 0x808) reports 'pixels' with channels/depth/size all None, since the byte
        # offset is known even though the layout is not.
        raise Unsupported("bitmap has pixels but an undecoded channel code (depth is None)")
    if off + size > len(asm.data):
        # Not a decode error: the declared offset/size are consistent with the record's own
        # width/height/channels/depth, but the file this .sbsasm was extracted from does not
        # hold that many bytes there -- confirmed on a real specimen, short by exactly the
        # missing amount, i.e. genuinely truncated. Left to `np.frombuffer` this raises a
        # confusing `cannot reshape` error instead of naming the real problem.
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
    value never touches $pos, an edge sample, or anything else N-wide -- a constant
    fill, in whatever component count -- every runtime helper it passed through (`vec`
    chief among them) keeps it at its own natural width-1 row count. That is correct in
    itself, but it means a 0-d scalar or a (1, k) constant both reach here needing an
    explicit broadcast: `out.shape[-1]` on a 0-d array is an IndexError, and reshaping
    a (1, k) result straight into (H, W, k) is a size mismatch.
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
    IDENTICAL -- a comparison between them would otherwise be trivially all-false
    everywhere, which looks like a wiring bug but is two placeholders agreeing.
    """
    yy, xx = np.mgrid[0:rec.height, 0:rec.width].astype(np.float32)
    u, v = xx / max(rec.width, 1), yy / max(rec.height, 1)
    a, b, c = (seed * 37 % 97) / 97, (seed * 61 % 89) / 89, (seed * 13 % 61) / 61
    img = 0.5 + 0.5 * np.sin(2 * np.pi * (u * (2 + a) + v * (2 + b) + c))
    return img[:, :, None].astype(np.float32)


def footprint_scale(m, offset_unused, W_out, H_out, src_shape):
    """How many SOURCE TEXELS one output pixel covers, under matrix `m`.

    A step of one output pixel is (1/W_out, 0) in output-normalised space; the
    transform maps it to (m[0], m[2]) / W_out in input-normalised space, which is that
    times the source's own dimensions in texels. The footprint is the longer step.
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
    when the source is sparse. Measured on `Chesterfield` record 128, a 4x zoom-out of
    a source that is exactly 0.5 in 99.79% of its pixels: the 16 output positions land
    on 4 distinct texel phases per axis, every one on the flat part, and the output is
    constant to 0.00000000. Box-averaging the 8x8 footprint gives std 0.00293.

    Halving rather than an arbitrary box because a power-of-two chain is exact and
    needs no resampling; it stops on an odd dimension rather than padding.

    NOT ARBITRATED, AND THE ARBITER CANNOT SEE IT: every `refcompare.py` number is
    IDENTICAL with and without this function, because the 427 records it touches in
    `Chesterfield` and 30 in `RoofTiles` sit in chains that reach no scored output. The
    prediction made when it was written -- that `normal`'s std would move off 0.0179
    toward the reference's 0.0968 -- FAILED. So what is defended is the PRESENCE of
    filtering, not this kernel: the old behaviour returned an exactly constant image
    from a varying source, which is wrong whatever replaces it. Box against trilinear
    against a proper elliptical filter is open, and the choice is provisional.

    DELIBERATELY NOT MARKED in LOW_CONFIDENCE, unlike `uniform.fill`. That names a
    value the FORMAT does not record; this is a resampling decision applying to every
    minifying transform equally, and marking 427 records per file would say something
    false about which readings are in doubt.
    """
    img = src
    while scale >= 2.0 and img.shape[0] >= 2 and img.shape[1] >= 2 \
            and img.shape[0] % 2 == 0 and img.shape[1] % 2 == 0:
        img = 0.25 * (img[0::2, 0::2] + img[1::2, 0::2]
                      + img[0::2, 1::2] + img[1::2, 1::2])
        scale /= 2.0
    return img


_POS_SYSVAR = re.compile(r'sysvar\(8,')
_READS_POS = {}
_PROG_SRC = {}


def _reference_px(rec):
    """The pixel scale `intensity` is expressed in -- from the RECORD, not a constant.

    Four branches (warp, dirmotionblur, directionalwarp, blur) convert a pixel-valued
    intensity into a UV displacement by dividing by a reference width, and all four
    used a fixed 256.0 from `assume.QUESTIONS['warp.reference_px']` -- eleven candidate
    values, arbitrated by which one scored best.

    THE RECORD STATES IT. This is the principle `distance` already runs on, in
    `scale_radius`'s own words: "512.0 is a real answer on a 512-wide map, and it is
    the RECORD, not a constant here, that says how wide it is."

    WHY THE CONSTANT SURVIVED THIS LONG, which is why it needs replacing rather than
    retuning: of 1,305 warp records in the eight reference packs, 1,287 are 256x256.
    The fitted constant is right for 98.6% of them by a property of the corpus, not of
    the format, and wrong by 2x or 4x on the 16 records at 128 and the 2 at 64 -- which
    a sweep over eleven candidate constants cannot find. The arbitration channel is
    kept, so an explicit `warp.reference_px` still wins and a record stating no width
    falls back to 256.0, the same default as the exception rather than the rule.

    A SECOND STATEMENT OF THE SAME SCALE SITS IN THE CLASS WORD, and its READING IS
    REFUTED -- recorded because someone will find the pair again. The (26, 27) bit pair
    is carried by seven spatial filters and consumed by nothing; its baked value is a
    Float2, equal in both components in 5,755 of 6,480 records and an exact power of
    two in 5,770, with `value * width == 256` in 3,326 -- which looked like this
    function's divisor stated by the record. Two later tests kill it: `rec.width` is
    `1 << ((tag >> 8) & 0xF)`, a four-bit TAG FIELD nothing here confirms; and if the
    pair were a scale relative to a per-graph output size, `value * width` would be
    CONSTANT within one assembly, which it is not (up to 12 distinct products in one
    file, including 127.162 and 253.44, not powers of two at all). What survives is
    narrower: this is the quantity the withdrawn blur slot-3 fallback was reading.
    """
    forced = assume.assumed('warp.reference_px')
    if forced is not None and forced != 'record':
        return float(forced)
    w = getattr(rec, 'width', None)
    if isinstance(w, (int, float)) and w and w > 0:
        return float(w)
    return 256.0


def _prog_source(asm, ptr):
    """The transpiled source of the program at `ptr`, memoized, '' if it will not read.

    Memoized because a pixelprocessor asks for the same program once per render and the
    body-selection tie-break below asks for it again.
    """
    key = (id(asm), ptr)
    got = _PROG_SRC.get(key)
    if got is None:
        end = asm.program_span(ptr)
        try:
            got = transpile.transpile(asm.data, ptr, end, "python", "prog") if end else ''
        except Exception:
            got = ''
        _PROG_SRC[key] = got
    return got


def _reads_pos(asm, ptr):
    """Does the program at `ptr` read `$pos`?

    Answered from the transpiled source, which states each system variable it reads, and
    memoized because a pixelprocessor asks it once per program per render.
    """
    key = (id(asm), ptr)
    got = _READS_POS.get(key)
    if got is None:
        got = _READS_POS[key] = bool(_POS_SYSVAR.search(_prog_source(asm, ptr)))
    return got


_DEAD_SAMPLER = {}
_DEF_RE = re.compile(r'^\s*%(\d+)\s+[0-9A-F]{4}\s+(\S+?)\s+(.*)$')


def sampler_is_annihilated(asm, ptr, index):
    """Does every use of `sample*(..., #index)`'s result get multiplied by a constant zero?

    If so, WHAT IS BOUND TO THAT SAMPLER CANNOT CHANGE THE PROGRAM'S OUTPUT, and a
    record that would otherwise refuse for an unwired input can be evaluated with
    anything at all. That is a proof read off the record's own bytecode, not an
    assumption about what the engine substitutes for an unconnected input -- which is
    unknowable here and stays refused.

    Why it comes up: five pixelprocessors sample an index equal to their own declared
    arity, exactly one past the last wired input, which is what a source graph with a
    trailing UNCONNECTED input slot compiles to. The compiler still emits the sample;
    on three of the five it also multiplies the result by a constant 0:

        %20  samplelum.f1  %19, #3      <- index 3, arity 3
        %21  const.f1      0
        %22  mul.f1        %20, %21     <- annihilated

        UHL3D-Stylized_Sand 2194, PavingStones003 547, stylized_round_stones 736
                                                       STRICTLY ANNIHILATED
        alien_rock_coral 155, 353, 2054                LIVE -- still refuse

    The three LIVE ones use the sample as an ANGLE driving a warp, so their output
    genuinely depends on an image nothing in the file binds.

    NOTE the operand form: `samplelum`/`samplecol` have a 2- and a 3-operand encoding,
    and the SAMPLER INDEX IS THE FIRST IMMEDIATE in both. Established by the arity
    bound -- the first immediate is in range on 5,711 of 5,714 three-operand samples
    while the second is out of range 501 times and is the constant 1 in 5,696 of them.
    """
    key = (id(asm), ptr, index)
    got = _DEAD_SAMPLER.get(key)
    if got is not None:
        return got
    try:
        import disasm
        hi = asm.program_end(ptr)
        lines = disasm.text(asm.data, ptr, hi).splitlines()
    except Exception:
        _DEAD_SAMPLER[key] = False
        return False
    defs = {}
    for ln in lines:
        m = _DEF_RE.match(ln)
        if m:
            defs[int(m.group(1))] = (m.group(2), m.group(3))
    zero = {g for g, (op, ar) in defs.items()
            if op.startswith('const') and ar.strip()
            and all(t.strip() and float(t) == 0.0 for t in ar.split(','))}
    targets = set()
    for g, (op, ar) in defs.items():
        if op.startswith('sample'):
            ims = re.findall(r'#(\d+)', ar)
            if ims and int(ims[0]) == index:
                targets.add(g)
    if not targets:
        _DEAD_SAMPLER[key] = False
        return False
    uses = {}
    for g, (op, ar) in defs.items():
        for u in re.findall(r'%(\d+)', ar):
            uses.setdefault(int(u), []).append((op, ar))
    ok = True
    for t in targets:
        for op, ar in uses.get(t, ()):
            others = [int(x) for x in re.findall(r'%(\d+)', ar) if int(x) != t]
            if not op.startswith('mul') or not any(o in zero for o in others):
                ok = False
                break
        if not ok:
            break
    _DEAD_SAMPLER[key] = ok
    return ok


def eval_program(asm, start, inputs, slots, N, pos=None, W=None, H=None):
    end = asm.program_span(start)
    if end is None:
        raise Unsupported("program at %d does not resolve a span" % start)
    src = transpile.transpile(asm.data, start, end, "python", "prog")
    scope = {}
    exec(compile(src, "<prog>", "exec"), scope)
    # `$number` BELONGS TO FX-MAP EMISSION, AND THE CONTEXT IS STICKY. Nothing here
    # reads it, but `rand` does, and an FX-Map's batched emission leaves a whole COLUMN
    # of pattern indices behind it. A pixelprocessor evaluated next then draws its
    # randomness against however many patterns the last FX-Map emitted -- a broadcast
    # error, `shapes (49,2) (4096,2)`, which cost 41 records across two files.
    sbsruntime.set_context(number=0.0)
    if pos is not None or W is not None or H is not None:
        # W/H WITHOUT pos is the case that was missing, and it is not cosmetic. A parameter
        # program can read `$size` -- `transformation`'s offset routinely does, to express a
        # shift in PIXELS -- and the context is global and sticky, so a caller that passed
        # neither got whatever record was evaluated last. `set_context` ignores None.
        sbsruntime.set_context(width=W, height=H, pos=pos)
    with np.errstate(all="ignore"):
        try:
            out = scope["prog"](inputs=inputs, slots=slots)
        except sbsruntime.MissingSampler as e:
            # MUST come first: MissingSampler subclasses KeyError, so the handler below
            # swallows it and reports an unwired image edge as a missing slot. That exact
            # confusion -- `SAMPLERS` and `slots` are both small-integer-keyed dicts and raised
            # indistinguishable KeyErrors -- sent two investigations after a phantom slot frame
            # before `sbsruntime.MissingSampler` was introduced. Removing this handler
            # reintroduces the ambiguity silently.
            #
            # AN UNWIRED INPUT WHOSE VALUE IS PROVABLY DISCARDED is not a reason to refuse. If
            # every use of this sampler's result is multiplied by a constant zero, the program
            # computes the same output for ANY binding, so evaluating it with zeros is exact
            # rather than assumed -- see `sampler_is_annihilated`. Anything else still refuses.
            idx = getattr(e, 'index', None)
            if idx is not None and sampler_is_annihilated(asm, start, idx):
                # RESTORED AFTERWARDS, ALWAYS. `SAMPLERS` is module-global and nothing else clears
                # it between records, which is the leak that made this file's render depend on
                # what ran before it. A binding installed here is scoped to this one evaluation.
                _had = idx in sbsruntime.SAMPLERS
                _prev = sbsruntime.SAMPLERS.get(idx)
                sbsruntime.SAMPLERS[idx] = sbsruntime.image_sampler(
                    np.zeros((1, 1, 1), dtype=np.float32))
                try:
                    out = scope["prog"](inputs=inputs, slots=slots)
                except sbsruntime.MissingSampler as e2:
                    raise cascade("input %s has no output yet -- no sampler was installed "
                                  "for it, which is an unwired edge and NOT a missing slot"
                                  % e2) from e2
                finally:
                    if _had:
                        sbsruntime.SAMPLERS[idx] = _prev
                    else:
                        sbsruntime.SAMPLERS.pop(idx, None)
            else:
                raise cascade("input %s has no output yet -- no sampler was installed for "
                              "it, which is an unwired edge and NOT a missing slot" % e) from e
        except KeyError as e:
            # `inputs` is keyed by uid (large, from default_inputs) and always fully populated
            # from the package's own declarations; `slots` is keyed by small integers. With
            # MissingSampler split off above, a bare KeyError here means a `get` of a slot this
            # record's own programs never `set`. It did NOT mean that before that split. The
            # already-documented category from the transpiler's own execution sweep
            # (FORMAT-NOTES.md, "Executing every program, not just transpiling it"): 9,806
            # sub-programs whose slots are written by ANOTHER of the record's programs sharing
            # slot state, which this walker does not model across records. Confirmed on a real
            # specimen that the record's other .programs entries do not set it either.
            raise Unsupported("slot %s read but never set (cross-record/-program slot "
                              "sharing, not modeled here)" % e) from e
    return np.asarray(out)


# ---------------------------------------------------------------------------
# Blend modes.
#
# WHAT IS CORPUS-VERIFIED: that `blendingmode` is the low four bits of blend's slot
# 1, and that it takes values 0-11 -- a corpus-wide falsification test over 382
# specimens with 0 counterexamples outside 0-11.
#
# WHAT IS NOT: which mode each integer NAMES. That mapping is not recoverable from
# this corpus, and the reason is structural rather than a coverage gap: a `.sbs`
# compNode has no name field, only a uid and its filter's fixed connection pins;
# there are ZERO GUIComment/GUIFrame elements in any .sbs in the tree; the mode is
# serialised as a bare `constantValueInt32`; and a `.sbsar` stores only a filter's
# INPUTS as pixels, never its computed output, so no (src, dst, mode, ground-truth
# result) tuple exists anywhere to solve for -- more specimens cannot change this.
#
# So THE ORDERING BELOW IS EXTERNAL KNOWLEDGE -- Substance Designer's documented
# blend dropdown order -- held with moderate confidence, and it is the single
# assumption every mode but 0 rests on. Kept as one flat table so a contradicting
# corpus has only one thing to change. Mode 0 is the exception and is genuinely
# corroborated: verified against a controlled red/blue lerp, and "Copy" is exactly
# what that verified behaviour means. Each function takes (dst, src) and returns
# the blend BEFORE opacity; `apply_blend` mixes afterward, the structure mode 0 was
# verified under.
BLEND_MODES = {
    0:  ('copy',       lambda d, s: s),
    1:  ('add',        lambda d, s: d + s),                  # a.k.a. linear dodge
    2:  ('subtract',   lambda d, s: d - s),
    3:  ('multiply',   lambda d, s: d * s),
    # `addsub` lightens where the source is above mid-grey and darkens below it. The
    # exact pivot scaling is the least certain entry in this table -- the behaviour is
    # described consistently but never published as an equation, so this maps src=0 ->
    # dst-1, src=0.5 -> dst, src=1 -> dst+1.
    #
    # IT IS ALSO THE ONLY MODE THAT SATURATES, and that is measured. Over
    # Chesterfield's 356 blend records the fraction of output pixels clipped to 1.0 is
    # 0.03 for copy, 0.18 multiply, 0.10 switch, 0.25 overlay, 0.00 for screen,
    # subtract, max and add -- and 0.60 for ADDSUB, 18 of whose 56 records come out
    # uniformly white. Per-record it clips 26.8% high; `d + s - 0.5` clips 19.7% high
    # and `d + s - 1` clips 37.5% LOW. None of the three is clean.
    #
    # TWO ATTEMPTS TO ARBITRATE IT, BOTH FAILURES. The exported reference maps CANNOT
    # decide it: each candidate moves 3 of 11 scoreable channels, all Chesterfield's
    # `basecolor`, which moves only between rendering and NOT rendering. And "authors
    # feed a mode's NEUTRAL value to switch an input off" is REFUTED BY ITS OWN CONTROL
    # -- mode 4's flat inputs are 146 at 0.5 against 160 at 1.0, but `max`, whose
    # neutral is unambiguously 0.0, shows 160 flat operands at 0.5 and 13 at 0.0.
    #
    # The mode NUMBER is not in doubt -- see
    # test_filters.test_blendingmode_matches_the_source_that_declares_it, which pairs
    4:  ('addsub',     lambda d, s: d + 2.0 * s - 1.0),
    5:  ('max',        lambda d, s: np.maximum(d, s)),        # a.k.a. lighten
    6:  ('min',        lambda d, s: np.minimum(d, s)),        # a.k.a. darken
    # `switch` is handled specially in `apply_blend` -- it is a hard choice between
    # the two inputs driven by opacity, not a per-channel function that opacity then
    # mixes, so running it through the normal lerp would silently turn it into `copy`.
    #
    # A CONSISTENCY CHECK THIS IDENTIFICATION PASSES, and one it could easily have
    # failed: a switch is a branch selector, so its selector should be a graph-level
    # constant rather than a picture. Evaluating the opacity of all 102 mode-7 records
    # in Chesterfield gives a spatially constant value in 102 of 102, and every one is
    # exactly 0.0 or 1.0. A mode misidentified as `switch` would be reading some other
    # filter's per-pixel parameter.
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

    Opacity mixes the blended result back toward the destination, which is the
    structure the one verified mode (0) was checked under: at opacity 0 every mode is
    a no-op. `switch` is the documented exception -- a hard selection rather than a
    mix -- and takes opacity as its selector instead.

    The result is clamped to [0, 1]. Several of these functions leave that range by
    construction (`add` above 1, `subtract` below 0, `divide` arbitrarily far) and the
    format's own images are unsigned-normalised, so an unclamped result would
    propagate out-of-range values into every downstream record.
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



class _SwappedEdges(object):
    """A record view with its first two edges exchanged -- see QUESTIONS['dirwarp.edges']."""

    def __init__(self, rec):
        self._rec = rec

    @property
    def edges(self):
        e = list(self._rec.edges)
        e[0], e[1] = e[1], e[0]
        return e

    def __getattr__(self, name):
        return getattr(self._rec, name)


def cls_pair_slot(rec, low_bit):
    """Where a class-word (baked, program) parameter pair lives, from the WALK.

    The class word encodes a parameter as an ADJACENT BIT PAIR: the lower bit means
    the value is baked in place and costs its own width, the upper means it is a
    program and costs one pointer, and the two are mutually exclusive. That is the
    same two-bit code `PARAM_SPEC` documents for the w1 word, minus the state a
    scalar cannot take.

    `decompose` reports `cls_params` as (w0 bit, first slot, width), so the owner of a
    slot is read rather than computed. Returns (state, slot, width) with state 'baked'
    or 'program', or None when neither bit is set -- which is a real answer: the
    source omitted the parameter and the engine's default applies.

    ASKING THE WALK MATTERS EVEN WHERE `end - 1` WOULD DO. A pair is the last thing in
    the header only when no w1 parameter follows it, which is true for blur, sharpen
    and warp and false for directionalwarp and dirmotionblur. Computing the position
    as "the last header slot" scores 100% on the first group and 4.7% on
    directionalwarp -- the difference being entirely in the arithmetic.
    """
    d = None
    try:
        d = decompose.decompose(rec)
    except Exception:
        return None
    if not d:
        return None
    w0 = rec.words[0]
    state = ('baked' if (w0 >> low_bit) & 1 else
             'program' if (w0 >> (low_bit + 1)) & 1 else None)
    if state is None:
        return None
    want = low_bit if state == 'baked' else low_bit + 1
    for b, slot, width in d.get('cls_params', ()):
        if b == want:
            return (state, slot, width)
    return None


def walk_named_offset(asm, rec):
    """`transformation`'s offset program, taken from the slot the WALK names, or None.

    The width heuristic in the transformation branch asks which of this record's
    programs returns 2 components, which is a question about VALUES. `decompose`
    answers it structurally: the walk enumerates the record's own parameter slots, and
    a slot holding `program - 52` names that program.

    Consulting the walk matters because `Record.programs` scans EVERY word of the
    record, not just its slots, and calls anything passing `valid_program` a program.
    Past the walk's `end` a record is bytecode, so an instruction OPERAND that survives
    that test is returned as a program: on `UHL3D-Stylized_Sand_with_Rocks_01`, word 19
    of a 142-word record whose structure ends at word 5 yields "program" 65596 in 177
    records, evaluating 2-wide and colliding with the real offset, which left
    `by_width[2]` ambiguous on 88 of that file's records -- a refusal built on a
    phantom. Cross-checked against the independent width rule: over 14 corpus files,
    1,203 of 1,204 bit-26 records agree, 0 disagree, 1 where the walk names no program.
    That 88 is a DECODE measurement, not a count of renders repaired.

    THE TENSION THIS USED TO RECORD IS RESOLVED. Field 13 was not a field: bits 24 and
    27 are never set in any of 242,931 filter-2 records, so field 12 can only read 0b10
    and field 13 only 0b01 -- the halves of one code at bits (25,26).
    `Record.translation`'s two booleans and the two-bit field were the same statement
    seen through the wrong frame.
    """
    try:
        import decompose
        d = decompose.decompose(rec)
    except Exception:
        return None
    if not d:
        return None
    # NAMED BY ITS FIELD, which it could not be until the straddle was framed. The
    # offset's two-bit code sits at bits 25,26 and `decompose`'s tiling reads fields
    # on EVEN bits, so the code used to split across tiling fields 12 and 13 -- one
    # half always reading 0b10 and looking like a value, the other always 0b01 and
    # looking like a pointer. This function could only work by elimination: collect
    # every program-valued parameter slot and insist there be exactly one. That failed
    # on the 82 records whose MATRIX is a program too.
    #
    # `decompose.STRADDLED` now relabels the two halves as the single field they are,
    # so the offset can be asked for directly, exactly as `walk_named_matrix` asks for
    # field 3. Over 69,282 bit-26 records the field read returns the SAME program as
    # the elimination rule in 69,282 of 69,282, the 82 included.
    named = [t for t in d.get('param_slots', ()) if t[0] == 12 and t[1] == 2]
    if len(named) != 1:
        return None
    pos = named[0][2]
    if not (0 <= pos < len(rec.words)):
        return None
    p = rec.words[pos] + 52
    if not (asm.body_lo <= p < asm.body_hi and asm.valid_program(p)):
        return None
    try:
        v = np.asarray(eval_program(asm, p, default_inputs(asm, 1), {}, 1,
                                    W=rec.width, H=rec.height)).reshape(-1)
    except Exception:
        return None
    if v.size != 2:
        return None
    return tuple(float(x) for x in v)


def walk_named_matrix(asm, rec):
    """`transformation`'s matrix22 program, taken from the slot the WALK names, or None.

    The sibling of `walk_named_offset`, closing the same gap one parameter over. The
    transformation branch singles the matrix out with `by_width[4]` -- a question about
    VALUES. The record states it instead: `matrix22` is the w1 pair at bits 6 and 7,
    FIELD 3 under the two-bit tiling `decompose` reports, and the slot that field names
    holds the program.

    THE FIELD IS THE SELECTOR, NOT THE WIDTH, which is a real difference from
    `walk_named_offset`: that one can only ask for "the record's single program-valued
    parameter slot", because the offset's two bits STRADDLE the tiling boundary. The
    matrix's bits do not, so a record carrying both a program matrix and a program
    offset is no longer ambiguous here.

    Structurally exact: all 5,106 records with w1 bit 7 set have exactly one field-3
    entry, state 2 (program), width 1, and in 5,106 of 5,106 that slot holds a valid
    program. Cross-checked against the independent width rule (this reads costs.json;
    that evaluates bytecode): 5,105 agree, 1 where the walk answers alone, 0 disagree.
    The one apparent disagreement in a first pass was an artefact of the COMPARISON --
    Lava record 845's matrix is (1.5, nan, 1.5, 1.5) and `nan != nan`.

    So this turns refusals into answers rather than changing resolved ones -- which
    matters most where the width rule cannot help by construction, on records with two
    disagreeing 4-wide programs. Returns None whenever the walk is not decisive.
    """
    try:
        import decompose
        d = decompose.decompose(rec)
    except Exception:
        return None
    if not d:
        return None
    named = [t for t in d.get('param_slots', ()) if t[0] == 3]
    if len(named) != 1:
        return None
    pos = named[0][2]
    if not (0 <= pos < len(rec.words)):
        return None
    p = rec.words[pos] + 52
    if not (asm.body_lo <= p < asm.body_hi and asm.valid_program(p)):
        return None
    try:
        v = np.asarray(eval_program(asm, p, default_inputs(asm, 1), {}, 1,
                                    W=rec.width, H=rec.height)).reshape(-1)
    except Exception:
        return None
    if v.size != 4:
        return None
    return tuple(float(x) for x in v)


def render(asm, precomputed=None, verbose=True, max_dim=None,
           synth_missing_bitmaps=False, stop_after=None):
    """Evaluate every record 0..N-1 that a filter type here can handle.

    `precomputed` pre-seeds outputs for records the walker cannot compute itself
    (e.g. a graph-input bitmap) -- {record_index: (H, W, C) array}. Returns
    {record_index: array} for every record that ended up with an output, a
    {record_index: reason} for every one that did not, and a `synthetic` set naming
    which outputs came from `synth_missing_bitmaps` rather than the file's own data.

    `max_dim` caps the evaluation grid a `pixelprocessor` runs at, independent of the
    record's own declared size -- sampling is position-based, so a downsampled
    consumer reading a full-resolution source is not a shape mismatch, just a coarser
    look. For sweeping many files this is the difference between minutes and seconds.

    `synth_missing_bitmaps` fills a `bitmap` record with no data of its own with a
    deterministic synthetic pattern instead of raising, so a sweep can see how much
    of a graph downstream of an external input still runs -- at the cost of that
    branch's output no longer reflecting the file's own content.
    """
    outputs = dict(precomputed or {})
    synthetic = set()
    LOW_CONFIDENCE.clear()
    CASCADED.clear()
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
                    # The manifest declares what the engine substitutes when this image input is left
                    # unconnected, so this is the file's own value, not an invention. Still
                    # LOW_CONFIDENCE: that the substitution is a UNIFORM of that value is the reading,
                    # unverified against an engine render.
                    outputs[i] = graph_input_default(asm, rec)
                    LOW_CONFIDENCE.add(i)
                    # (the manifest parse is cached per assembly path; only the small uniform array is
                    # rebuilt, and only for the 50 of 536 records that have a default at all)
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
                        raise cascade("edge -> record %s has no output yet" % edge_rec)
                    src_img = outputs[edge_rec]
                    sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(src_img)
                    own_slots.add(slot_i)
                    tainted = tainted or edge_rec in synthetic
                # A pixelprocessor can also reach images by sampler index with no edge at all:
                # ie_curve record 233 has edges=[], asks for sampler 8, and is itself a declared
                # output. Same binding as the fxmaps branch -- see `sampler_bindings`. Of the four
                # genuine decode-gap records, one is each.
                #
                # TESTED AGAINST `own_slots`, NOT against SAMPLERS membership: unlike the fxmaps
                # branch this one does not clear the global, so a stale entry left by an earlier
                # record would otherwise beat a correct binding here and be invisible.
                for slot_i, src in sampler_bindings(asm, rec, outputs).items():
                    if slot_i not in own_slots:
                        sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(outputs[src])
                        LOW_CONFIDENCE.add(i)
                progs = rec.filter_programs
                if not progs:
                    raise Unsupported("no filter_programs")
                # A record can carry more than one filter program -- but not always as independent
                # parameters. A real specimen has an earlier program that `set`s slot 0 to a random
                # per-image seed, which only the LAST program's `get slot 0` then reads. So every
                # earlier program runs once, N=1, sharing one `slots` dict whose `set`s carry
                # forward; only the last is the per-pixel body and gets $pos and the full N.
                #
                # WHICH ONE IS THE BODY IS DECIDED BY `$pos`, NOT BY POSITION. A per-pixel body has
                # to know where it is; a scale, an offset or a seed does not. Over 3,021
                # pixelprocessor records in 22 files:
                #
                #     exactly one program uses $pos     2,561
                #       and it IS the last              2,411   -- taking the last was right
                #       and it is NOT the last            150   -- taking the last was wrong
                #     two of four use it                  288   -- ambiguous, left alone
                #     none uses it                        172   -- ambiguous, left alone
                #
                # The 150 are the records whose output this renderer had no business producing.
                # Travertine 301's three programs are a 2-wide (7.0, 7.0) -- log2 of its own
                # 128-wide size -- a 15-instruction $pos body, and a 7-op `vec(1 + rand(1.0), 1.0)`;
                # the last was being drawn as the picture, which is where the out-of-range 1.9217 in
                # this branch's channel guard comes from. An earlier attempt used the DECLARED
                # RESULT WIDTH and was unique in only 21 of 325 cases (29f32b4).
                #
                # WHERE $pos IS NOT UNIQUE, A TIE AMONG IDENTICAL PROGRAMS IS NOT A TIE: much of
                # the ambiguity is degenerate, the several $pos programs transpiling to the SAME
                # SOURCE. Over 437 corpus files plus the 7 reference-shipping packages, 176 such
                # records -- the last program already IS that body in 32 and is something else in
                # 144. AND THE HEADER, WHICH THIS RULE DOES NOT CONSULT, AGREES 144 OF 144: the
                # newly selected body's declared width matches `Record.colour` and the incumbent's
                # does not. Width is the CHECK here, not the criterion. ALL 144 ARE IN THE
                # REFERENCE PACKAGES, which is the point -- `corpus.paths()` is `DISTINCT.txt`,
                # which does not contain `new_opengameart/` at all, so every census asking "does
                # this rule change anything" answered 0.
                main = progs[-1]
                if len(progs) > 1:
                    lit = [p for p in progs if _reads_pos(asm, p)]
                    if len(lit) == 1:
                        main = lit[0]
                    elif len(lit) > 1 and len(
                            set(_prog_source(asm, p) for p in lit)) == 1:
                        main = lit[0]
                slots = {}          # per-record frame; see the slot-frame note above
                for p in progs:
                    if p is not main:
                        eval_program(asm, p, default_inputs(asm, 1), slots, 1)
                inputs = default_inputs(asm, N)
                out = eval_program(asm, main, inputs, slots, N, pos=pos, W=W, H=H)
                outputs[i] = to_image(out, N, H, W)
                if tainted:
                    synthetic.add(i)   # downstream of a synthetic placeholder somewhere

            elif rec.filter_name == "blend":
                # `blendingmode` is the low nibble of slot 1 -- FORMAT-NOTES.md, corpus-wide
                # falsified range test. WHICH mode each integer names comes from the BLEND_MODES
                # table above and is EXTERNAL; mode 0 is the one independently verified case.
                #
                # Edge order -- which input is laid UNDER the other -- was an unverified convention
                # for a long time and is now CORPUS-VERIFIED: edges[0] is the destination,
                # edges[1] the source. A paired `.sbs` names each blend's two connections outright,
                # so the only missing link is which compiled edge slot each became; where the two
                # inputs are fed by DIFFERENT filter types, that type pair identifies the
                # orientation without any node-to-record mapping. Restricted to unordered type
                # pairs occurring exactly ONCE on each side, over 11 file contents and 11 type
                # pairs: edges[0] == destination 14 of 14. The control matters as much -- rerunning
                # with the compiled edges deliberately swapped flips it to 0 of 14 forward. This
                # mattered more once the asymmetric modes landed: under mode 0 alone a swap was
                # mathematically invisible.
                mode = rec.slot1_flags.get("blendingmode") if rec.slot1_flags else None
                if mode is None:
                    raise Unsupported("blend record has no readable blendingmode")
                if len(rec.edges) < 2:
                    raise Unsupported("blend has fewer than 2 edges")
                for edge_rec in rec.edges:
                    if edge_rec not in outputs:
                        raise cascade("edge -> record %s has no output yet" % edge_rec)
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

                # Record.size_or_baked's own docstring: its 'program' case is the record's OUTPUT
                # SIZE expression in 91.3% of records, not a filter parameter -- confirmed the hard
                # way, evaluating it as opacity on a real 7-blend chain gave values in the hundreds
                # of thousands. `filter_programs` already excludes that size program.
                #
                # THE RECORD'S OWN NAMED PARAMETER FIRST. `opacitymult` is what a blend calls its
                # opacity and `Record.named_parameters` reads it from the slot PARAM_SPEC names, so
                # where it is baked, it is the value. It was being ignored entirely. Found on
                # ChristmasTreeOrnamentSubstance006, whose `roughness` came out constant 1.0 --
                # fully matte, for a material whose own thumbnail is a pair of glossy baubles.
                # Record 22 is `add` at opacitymult 0.05 over inputs of mean 0.27 and 0.50; what it
                # used instead was `filter_programs[-1]` = 9.0, which is log2(512), the record's own
                # width. Not a one-record fix: over 25 files and 8,693 blend records, 3,898 carry a
                # baked `opacitymult` and every one was being discarded (3,622 fell through to 1.0,
                # 276 to a program). No record has both a baked opacitymult and a float in
                # `size_or_baked`, and 3,896 of the 3,898 lie in [0, 1].
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
                        # No program at all beyond (possibly) the size expression: confirmed on a real
                        # specimen (record 322) whose only program IS the one Record.size_or_baked names,
                        # so filter_programs correctly excludes it and leaves nothing. The compiler's own
                        # convention -- proven elsewhere in this file for blend mode -- is to skip
                        # emitting code for a parameter left at its default, so this takes full (100%)
                        # opacity rather than 0%, which would make the blend a no-op and the edge
                        # pointless.
                        opacity = np.full((N, 1), 1.0, dtype=np.float32)

                if len(rec.edges) > 2:
                    if rec.edges[2] not in outputs:
                        raise cascade("mask edge -> record %s has no output yet"
                                          % rec.edges[2])
                    tainted = tainted or rec.edges[2] in synthetic
                    mask = sbsruntime.image_sampler(outputs[rec.edges[2]])(pos)
                    opacity = opacity * mask[:, :1]

                result = apply_blend(mode, dst, src, opacity)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "transformation":
                # Record.matrix is baked in only 644 of 2,635 transformation records in a real
                # specimen (24%); most of the rest compute it from a program. The largest such
                # program (record 3182, 97 instructions) is not a matrix+offset computation at all
                # -- it initializes dozens of slots with rand() calls, scale ranges and iteration
                # counts, the shape of a randomized scatter generator's parameter block. That
                # general case is out of scope.
                #
                # A slice of the "not baked" population is NOT that case: 3,103 of 3,103 sampled
                # have `rec.filter_programs` empty AND slot-1 bits 6 and 7 both clear -- the same
                # bits Record.translation reads as "no parameter block to pack against".
                # `rec.programs` being non-empty there is the SIZE-EXPRESSION program, the same
                # trap as the blend-opacity bug, so there is no matrix-computing code at all. Same
                # compiler convention as blend mode (absent = 0) and opacity (absent = 1.0), so
                # this takes identity rather than raising. `translation` had the identical bug
                # independently, checking `rec.programs` instead of `rec.filter_programs`.
                # Genuinely program-computed matrices are still out of scope -- "has 2 components"
                # was tried and found wrong (record 167, a pure Y-flip, whose 2-component program
                # computes a function of the record's own aspect ratio).
                #
                # WHICH DIRECTION THE MATRIX APPLIES: conventional raster backward mapping -- for
                # each OUTPUT position, transform it INTO an input sampling position, pivoted at
                # (0.5, 0.5) so a pure scale or flip does not shift the image off-canvas. NOW
                # VERIFIED AGAINST A REFERENCE RENDER, which it was not until ChesterfieldSofa
                # became scoreable: treating the stored matrix as the FORWARD transform and
                # sampling with its inverse costs four of the five declared outputs and collapses
                # metallic against the engine's own map from +0.2294 to +0.0250. Also internally
                # consistent on clean specimens -- record 5115's (0,-1,1,0) turns a top stripe into
                # a left stripe with no drift, and 956's (0.125,...) gives solid black on a pattern
                # whose CENTER is background, as scale < 1 should.
                #
                # WHICH PROGRAM IS WHICH, settled by the format's own bits plus one structural
                # fact. Slot 1 bit 6 or 7 says a matrix parameter exists and bit 26 says the offset
                # is program-computed; evaluating each filter program once at N=1 then separates
                # them by COMPONENT WIDTH, and the widths do not overlap -- bit 26 set gives 2
                # components in 2,007 of 2,007, bit 26 clear gives 4 (405), 2 (162) or 1 (79).
                # 100% against a control that is mostly 4-wide. This is what makes the assignment
                # safe where an earlier attempt was not: that one trusted ANY 2-component result as
                # an offset without consulting bit 26. Not verified against the source -- a
                # declared CONSTANT offset compiles to a baked one (bit 25), so containment tests
                # the wrong population and its 6 of 67 says nothing either way.
                fprogs = rec.filter_programs
                w1 = rec.words[1] if len(rec.words) > 1 else 0
                # THE HEADER SAYS WHETHER A MATRIX IS BAKED, so ask it. `Record.matrix` reads four
                # slots by a rule established at 100% over "the 66,211 records whose slot-1 bit 6
                # says the matrix is baked" -- its own words -- but it never checks that bit, so
                # where the bit is CLEAR it returns whatever those slots happen to hold. Over
                # 6,666 baked matrices here: bit 6 set, 6,628 records, 0 with a denormal
                # component; bit 6 clear, 38 records, 4 with one (10.53%). The four detectable
                # ones all read 0x0A42xxxx in the third slot -- a packed pair rather than a float.
                # Rejecting on the FLAG rather than on the values also covers the other 34, whose
                # slots may read as plausible numbers while being just as unfounded.
                #
                # It matters out of proportion to 38 records. Such a matrix is near-singular, so
                # it collapses the input to a point and renders a record whose input has spread
                # 0.15 exactly flat. In ChesterfieldSofa that flat zero feeds a pixelprocessor
                # computing v8/v12 with both terms zero -- 0/0 -- and the NaN reaches 659 of the
                # 830 records the file renders. Honouring the bit takes that file to 0 non-finite
                # records and its declared outputs from 1 spatial to 4 of 4.
                m = rec.matrix if (w1 >> 6 & 1) else None
                matrix_from_program = False
                has_matrix_param = bool((w1 >> 6 & 1) or (w1 >> 7 & 1))
                offset_is_program = bool(w1 >> 26 & 1)

                by_width = {}
                n_evaluated = 0
                n_size = 0          # identified as this record's OWN size expression
                n_failed = 0        # would not evaluate, so its width is unknown
                n_two = 0           # 2-wide, the only width an OFFSET can have
                if (m is None and has_matrix_param) or offset_is_program:
                    for p in fprogs:
                        try:
                            # At the record's DECLARED size, not the (possibly max_dim capped) grid: `$size`
                            # is what the engine would report, and an offset of `-1.0 / $size.x` means one
                            # pixel of the real output. Evaluating it at a stale 256 while the record is 16
                            # wide gets the shift wrong by 16x, in units that look plausible either way.
                            a = np.asarray(eval_program(asm, p, default_inputs(asm, 1),
                                                        {}, 1, W=rec.width,
                                                        H=rec.height)).reshape(-1)
                        except Exception:
                            n_failed += 1
                            continue
                        # A 2-wide program returning (log2 W, log2 H) of THIS RECORD'S OWN declared size
                        # is the output-size expression, not a parameter, and it is skipped before the
                        # collision test below. This is an identity, not a shape heuristic: `rec.width`
                        # and `rec.height` are read from the header with no program involved. An earlier
                        # reading guessed those (8.0, 8.0) values were "tiling or scale shaped"; they are
                        # 2**8 == 256, the record's own edge.
                        #
                        # WITH THE CONTROL, over 8,473 bit-26 records in 80 files: of the 7,586 the
                        # collision test already resolves, ZERO have an accepted offset equal to
                        # log2-size, so this cannot change an answer that currently works. Of the 887 it
                        # refuses, 825 (93%) leave exactly one candidate once the size expression is set
                        # aside; 62 stay ambiguous and still refuse.
                        if (a.size == 2 and rec.width and rec.height
                                and abs(float(a[0]) - math.log2(rec.width)) < 1e-6
                                and abs(float(a[1]) - math.log2(rec.height)) < 1e-6):
                            n_size += 1
                            continue
                        # COUNTED AFTER THE SIZE EXPRESSION IS SET ASIDE, and that placement is the whole
                        # of the second fix. `n_evaluated` is what the refusal below means by "programs
                        # remain unread", and a size expression is not unread -- it is read, identified,
                        # and not a parameter. Counting it made the record refuse for carrying a program
                        # that had just been explained.
                        n_evaluated += 1
                        if a.size == 2:
                            n_two += 1
                        # A WIDTH SEEN TWICE IS ONLY AMBIGUOUS IF THE TWO DISAGREE. The test was "seen
                        # twice -> refuse", which throws away the case where there is nothing to choose:
                        # concrete_049 records 36, 37, 38 and 50 each carry TWO 4-wide programs and both
                        # return exactly (1.0, 0.0, 0.0, 1.0). Three of the four even share one program
                        # ADDRESS with a sibling record, so the duplication is the compiler emitting the
                        # same expression twice. Two candidates that agree ARE the answer.
                        val = tuple(float(x) for x in a)
                        if a.size in by_width and by_width[a.size] != val:
                            by_width[a.size] = None
                        elif a.size not in by_width:
                            by_width[a.size] = val

                # THE WALK IS ASKED FIRST, as it already is for the offset below. `matrix22` is
                # the w1 pair at bits 6,7 -- field 3 -- and the slot that field names holds the
                # program. Agreement with the width rule is 5,105/5,105 where that rule resolves.
                # See `walk_named_matrix`. Evaluated once, here, since it runs a program.
                walk_m = (walk_named_matrix(asm, rec)
                          if (m is None and has_matrix_param) else None)
                if m is None:
                    if not has_matrix_param:
                        m = (1.0, 0.0, 0.0, 1.0)      # no matrix parameter: identity
                    elif walk_m is not None:
                        m = walk_m
                        matrix_from_program = True
                    elif by_width.get(4):
                        m = by_width[4]
                        matrix_from_program = True
                    else:
                        # THE CASE THIS DESCRIBED IS RESOLVED, and by the record rather than by an
                        # arbiter. Desert_Sand_01 record 55 was the example: five programs, two of them
                        # 4-wide and DISAGREEING -- an identity and a (0.65, 0, 0, 0.05) -- so the width
                        # rule had nothing to choose between them, and this comment concluded that
                        # "picking the later address would be a coin toss dressed as a rule".
                        #
                        # No specimen was needed. The record states which program is the matrix: w1 = 0xbf
                        # sets bit 7, so field 3 is state 2, and the walk names slot 4, which holds
                        # 0x1d54 -- the identity. What still reaches here is a record where the WALK is
                        # not decisive either. Those are genuine absences, not coin tosses.
                        raise Unsupported("matrix is a program this cannot single out "
                                          "(%d programs, widths %s)"
                                          % (len(fprogs), sorted(k for k in by_width)))
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
                tainted = rec.edges[0] in synthetic

                offset = rec.translation
                if offset is None:
                    if offset_is_program:
                        # THE WALK IS ASKED FIRST -- it names the slot, so there is nothing to single out.
                        # See `walk_named_offset`. Agreement is 1,203/1,203 where the width rule
                        # resolves, so this only turns refusals into answers.
                        offset = walk_named_offset(asm, rec)
                        if offset is None:
                            if by_width.get(2):
                                offset = by_width[2]
                            else:
                                raise Unsupported("offset is a program this cannot single out "
                                                  "(%d programs, widths %s)"
                                                  % (len(fprogs), sorted(k for k in by_width)))
                    elif fprogs and has_matrix_param and (n_failed > 0 or n_two > 0):
                        # WHICH programs remain unread -- the earlier form did not ask. It refused whenever
                        # the record had any filter program and a matrix parameter, including when the ONE
                        # program present had just been consumed as the matrix. Over 1,726 records that
                        # reach here, 1,140 (66.0%) have nothing left unread by then, and for those the
                        # message was literally false: the offset is (0, 0) by exactly the path taken when
                        # a record has no programs at all. The remaining 34% still refuse and should -- 366
                        # have a BAKED matrix plus an unaccounted program, 166 a matrix-from-program plus
                        # extras, 54 a program that will not evaluate.
                        #
                        # AND ONLY AN OFFSET-SHAPED PROGRAM COUNTS AS UNREAD. An offset is 2-wide,
                        # everywhere this file reads one. Over 12 files the records refusing here carry a
                        # 4-wide matrix + a 1-WIDE program (20), a baked matrix + a 1-wide (9), and a baked
                        # matrix + a 2-wide (4). The 29 with a 1-wide leftover are the same shared constant
                        # in every case -- wood_cedar_white's records all name address 5748, returning 1.0
                        # -- and a scalar is not a translation. A 2-wide leftover still refuses: that IS
                        # offset-shaped while bit 26 says there is no offset program.
                        raise Unsupported("no offset bit set and %d offset-shaped program(s) "
                                          "remain unread (%d would not evaluate)"
                                          % (n_two, n_failed))
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

                # Integrate over the footprint when the transform MINIFIES. One bilinear tap
                # regardless of scale is what made ten records in `Chesterfield`'s basecolor chain
                # return an exactly constant image; see `prefilter`. Magnification is untouched.
                _src = outputs[rec.edges[0]]
                _scale = footprint_scale(m, offset, W, H, np.asarray(_src).shape)
                if _scale >= 2.0:
                    _src = prefilter(np.asarray(_src, dtype=np.float64), _scale)
                result = sbsruntime.image_sampler(_src)(in_pos)
                outputs[i] = to_image(result, W * H, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "levels":
                # Where the five parameters live (levelinlow/levelinhigh/levelinmid/leveloutlow/
                # levelouthigh, each independently baked-or-program) is settled corpus-wide --
                # FORMAT-NOTES.md, "`levels` joins after all, and the front/back question
                # closes", 174,329/174,396 (99.96%) tail-placement reads, containment-verified
                # against declared Float4 sources 105/132. Not settled by that research, and not
                # re-derived here: the FORMULA. This is the standard Photoshop/Substance remap --
                # clamp-normalize to [in_low, in_high], an optional gamma pivot around in_mid,
                # then rescale to [out_low, out_high] -- taken as industry-standard known math,
                # checked only for internal self-consistency against a controlled ramp.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
                tainted = rec.edges[0] in synthetic

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)

                src = sbsruntime.image_sampler(outputs[rec.edges[0]])(pos)

                # Compiler default-omission convention (established for blend mode and opacity
                # elsewhere in this file): a parameter left at its default is absent from the
                # bytecode. Levels' identity is in 0/0.5/1, out 0/1.
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
                # See assume.QUESTIONS['levels.inversion']. Only fires where exactly ONE of the
                # pair is stated AND it sits at an inversion extreme -- the population the
                # structural side isolated.
                if assume.assumed('levels.inversion') == 'complete':
                    _named = {n for n, _k, _v in (rec.named_parameters or ())}
                    _lo_set = 'levelinlow' in _named
                    _hi_set = 'levelinhigh' in _named
                    if _lo_set and not _hi_set and abs(float(in_low) - 1.0) < 1e-6:
                        in_high = np.float32(0.0)
                        assume.note(i)
                    elif _hi_set and not _lo_set and abs(float(in_high)) < 1e-6:
                        in_low = np.float32(1.0)
                        assume.note(i)
                out_low, out_high = params['leveloutlow'], params['levelouthigh']

                span = in_high - in_low
                # A ZERO-WIDTH INPUT RANGE IS A STEP, NOT A RAMP. Where in_low equals in_high the
                # transfer has no width to interpolate across: everything below the point maps to
                # out_low and everything at or above it to out_high. Substituting a span of 1.0 to
                # dodge the division turns that step into a gentle ramp over the whole range,
                # which is a different picture.
                #
                # Auras record 400 is the specimen: it stores levelinlow AND levelinhigh both at
                # 0.5900000333786011 and nothing else. Under the ramp its contrast is std 0.1262,
                # the `distance` at record 402 collapses to exactly 0.0, and record 444 -- the
                # graph-004 basecolor -- comes out constant. Under the step it keeps its structure
                # and scores r = 0.92 / 0.85 / 0.94 against the engine's own export.
                #
                # THIS IS WHAT THE OLD GAMMA READING WAS DOING BY ACCIDENT: before b2f1d97 the mid
                # point was renormalised, giving an exponent of 0.0753 -- a near-vertical curve
                # that approximated the step. Removing that accident is what exposed this; the
                # step belongs in the span, not in the gamma. See
                # assume.QUESTIONS['levels.zerospan'], under which a zero-width range passes its
                # input through instead of thresholding it.
                degenerate = np.abs(span) < 1e-6
                span = np.where(degenerate, 1.0, span)
                _ramp = np.clip((src - in_low) / span, 0.0, 1.0)
                if assume.assumed('levels.zerospan') == 'identity':
                    _deg = np.clip(src, 0.0, 1.0)
                    if np.any(degenerate):
                        assume.note(i)
                else:
                    _deg = (src >= in_low).astype(np.float32)
                t = np.where(degenerate, _deg, _ramp)

                # See assume.QUESTIONS['levels.interclamp']. THE CLAMP TWO LINES ABOVE IS A DECODED
                # PARAMETER AND NOT A SAFETY RAIL. `levels` carries a SIXTH w1 field -- pair 5,
                # bits 10 and 11 -- that `PARAM_SPEC[15]` does not name and that costs zero words
                # in both states, so it stores no value and is therefore a flag. Adobe's published
                # documentation describes a `levels` "intermediary clamp" Boolean: whether the
                # transformed input value is clamped to [0, 1] BEFORE the output level is computed,
                # and `(src - in_low) / span` is exactly that value while `_ramp` is exactly that
                # clamp.
                #
                # THE NAME IS EXTERNAL KNOWLEDGE, held at the same confidence as the blend mode
                # dropdown order, which is why this is an arm and not a behaviour. What the file
                # says without it, over 90,728 records: the field is set on 500 across 130 files,
                # ALWAYS in state 1 -- a parameter with no word and one non-absent state is a flag
                # carried by presence; it varies with the entire rest of the record held fixed (tag
                # 0x18bb1e, single `levelouthigh` of 0.5: 6 set against 4 clear); and its input is
                # a `pixelprocessor` 42.00% of the time against a base rate of 1.91%, a 22x
                # enrichment on the ONE node whose output has no reason to lie in [0, 1]. READING
                # PRESENCE AS "NOT THE DEFAULT" is a SECOND guess stacked on the first, and it is
                # the one 'noclamp' encodes. THE ARM IS MEASURABLE ON ALMOST NONE OF ITS OWN
                # POPULATION: 492 of the 500 set only an out-parameter, so `t` is `src` and
                # clamping cannot matter. A null result here is a result.
                if (assume.assumed('levels.interclamp') == 'noclamp'
                        and len(rec.words) > 1 and (rec.words[1] >> 10) & 3):
                    t = np.where(degenerate, _deg, (src - in_low) / span)
                    assume.note(i)

                # A ZERO-WIDTH INPUT RANGE MAY BE A HALF-READ INVERSION, NOT A STEP. The step
                # reading elsewhere in this branch is right for a range that is genuinely
                # zero-width, but some are probably not: Substance inverts by setting in_low ABOVE
                # in_high, so a record storing only one of that pair reads as degenerate when the
                # other half is simply not being decoded. Over 80 files, 301 of 11,396 levels
                # records have a zero-width input range -- 176 state hi 0.0 with lo defaulted, 9
                # state lo 1.0 with hi defaulted, and 116 state both at the same value. The 116 are
                # genuinely degenerate; the 185 with ONE side stated at an extreme are the
                # suspicious population, and the two readings are not distinguishable from this
                # side, since an unread parameter and an absent one look identical. It is a live
                # cause of flat output: Bricks graph 003's dead spine dies at exactly these.
                #
                # `levelinmid` IS THE GAMMA ITSELF, NOT A POSITION INSIDE THE INPUT RANGE. This
                # used to renormalise it, `(in_mid - in_low) / span`, which is wrong for a reason
                # needing no reference render: 0.5 is the parameter's DEFAULT and means "no gamma",
                # and a default has to be neutral -- under the renormalising form it is neutral only
                # when in_low is 0. It is also the worst single discrepancy in the scored corpus:
                # ChesterfieldSofa `ambientOcclusion` (record 852, storing only levelinlow 0.5,
                # leveloutlow 1.0, levelouthigh 0.0) against a reference mean of ~0.887 gives mean
                # 0.2060 renormalised and 0.9386 with in_mid as gamma. SCOPE IS EXACTLY THE RECORDS
                # THAT WERE WRONG -- for the default input range span is 1 and the two forms are
                # byte-identical.
                mid_norm = np.clip(in_mid, 1e-4, 1 - 1e-4)
                with np.errstate(all="ignore"):
                    exponent = np.log(0.5) / np.log(mid_norm)
                    gamma_t = np.power(t, exponent)
                t = np.where(np.abs(mid_norm - 0.5) < 1e-6, t, gamma_t)

                # CLAMPED, LIKE `blend`'S RESULT AND FOR THE SAME REASON. `t` is already in
                # [0, 1], but the OUTPUT RANGE is not: fur_var_001 record 55 stores leveloutlow
                # 0.62 and levelouthigh 1.31, so a white input comes out at 1.31 -- not a colour,
                # and every consumer downstream inherits it. That record feeds
                # `ambientOcclusion`, which is why the census reported an AO output flat at 1.31.
                #
                # The value is not a misread: record 54 stores (1.0, 0.0) at the same two words
                # and inverts, which is exactly what an out-range of 1 down to 0 means. The
                # engine writes 8- and 16-bit unsigned maps, so it cannot emit 1.31 either.
                # `apply_blend`'s note says this "mirrors the clamp `levels` already applies" --
                # it did not; `t` was clamped and the result was not.
                result = np.clip(out_low + t * (out_high - out_low), 0.0, 1.0)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "uniform":
                # Where the size expression lives was already known (word[1], if
                # Record.size_or_baked is a program there) but the FILL COLOR was not -- this used
                # to raise unconditionally rather than repeat the mistake found elsewhere in this
                # file, treating .programs[-1] as the color and silently producing the size
                # expression's own (8, 8) output tiled across the image.
                #
                # Real specimens close it: the color occupies the N words immediately after the
                # size-expression slot (word[2].. when word[1] holds a program, word[1]..
                # otherwise) -- N=1 for a greyscale record, N=4 (RGBA) for a colour one.
                # Confirmed two ways corpus-wide: 3,392 of 3,428 sampled (98.9%) decode to
                # components in [0, 1] at exactly that position; and exact containment against
                # DLG-Tools__US_Flag.sbs, where four DISTINCT declared `outputcolor` Float4 values
                # each match a specific record's decoded words to 6+ significant figures.
                #
                # The 1.1% residual is a second, unidentified word shape, raised rather than
                # guessed at.
                has_prog = rec.size_or_baked is not None and rec.size_or_baked[0] == 'program'
                # AND ONE MORE POINTER WHEN CLASS BIT 7 IS SET. Seven records read a denormal
                # where a colour should be, and all seven carry TWO pointers ahead of the slot
                # rather than one: MetalSubstance009 record 9887 is `[tag][ptr][ptr][1.0][bytecode
                # ...]`, a fill of exactly 1.0 one word further on. Bit 7 marks them.
                start = (2 if has_prog else 1) + (1 if (rec.cls >> 7) & 1 else 0)
                n = 4 if rec.colour else 1
                # CLASS BIT 8 SAYS WHETHER THE FILL IS STORED AT ALL, and asking it is not optional
                # politeness -- 358 of 864 uniform records in 40 files (41%) were rendering the
                # record's own BYTECODE as their colour. The words at the colour slot are the
                # program preamble, `0x0A420001 0x70818F53`, which as float32 is 9.341e-33: a
                # denormal, inside [0, 1], waved through by a range check. The same value then
                # reaches `fxrender`, where it is the population MIN_PATTERN_SIZE was built to
                # reject -- so an FX-Map fed by one draws nothing and comes out flat black, which
                # is how CarpetSubstance001's tufts vanish. Over the same 40 files: bit 8 set -> a
                # plausible colour 512 of 512; bit 8 clear -> not a colour 351 of 352. The single
                # exception reads (1.3e-18, 0, 1, 0), also bytecode, just not small enough to trip
                # the classifier -- so the bit is right there too and it is the value test that is
                # soft.
                #
                # BIT 8 CLEAR DOES NOT MEAN "NO FILL" -- IT CAN MEAN "THE FILL IS A PROGRAM". The
                # bit-8 law is right that the SLOT does not hold a colour; it does not follow that
                # the file is silent. ColorTest record 1 is the specimen: bit 8 clear, renders
                # black, and its colour sits in the record as a second program -- `inputref.f4
                # uid=3867945481`, which the header declares as (0.5, 0.5, 0.5, 1.0). A uniform's
                # size expression is one program; a SECOND one is the colour:
                #
                #                     records   have a colour program   of those, plausible
                #     bit 8 clear       2,113            259                184  (71.0%)
                #     bit 8 set         1,940             78                  2   (2.6%)
                #
                # 71% against 2.6% is a 27x enrichment in the direction the reading predicts, and
                # the recovered values are material colours rather than noise. Narrow: only when
                # the bit is clear, only when a non-size program exists, only when it runs and
                # yields the right component count inside [0, 1]. The 1,854 bit-8-clear records
                # with no colour program fall through to the arbitrated default below.
                # THE PROGRAM FILL IS NAMED BY THE WALK, not hunted for. Everything above
                # this point is the BAKED half of an ordinary class-word pair -- w0 bit 24,
                # cls bit 8 -- and bit 25 is its program half, exactly the convention
                # `cls_pair_slot` documents and `shuffle` already uses at the same bit.
                #
                # So the two guesses stacked here are both replaceable by one read. This
                # took `rec.programs[0]` minus the size program (WHICH program?) and then
                # asked whether the value landed in [0, 1] (does it LOOK like a colour?),
                # which is a value probe of the kind this decode avoids everywhere else.
                # Over the corpus and the reference packs, on cls-bit-8-clear records:
                #
                #     bit 9 set, both agree                                440
                #     bit 9 set, the WALK finds one the heuristic MISSED   196
                #     bit 9 set, both find one and they DISAGREE            12
                #     bit 9 CLEAR, the heuristic fires anyway              161
                #     neither                                            6,614
                #
                # The 161 are false positives on records the format says carry no program
                # fill at all. The 12 are worse and they are this file's own documented
                # trap: the heuristic's pointer sits 8 bytes past the walk's and evaluates
                # to (8.0, 8.0) -- the SIZE EXPRESSION, which the comment opening this
                # branch says it exists to avoid treating as the colour. The walk's pointer
                # at the same records reads (1.0, 0.0, 0.0, 1.0), (1.0, 0.752, 0.0, 1.0),
                # (0.496, 1.0, 0.0, 1.0): red, orange, yellow-green.
                #
                # And the slot the walk names holds a VALID PROGRAM on 647 of the 648
                # records with bit 25 set, so the read is checked structurally rather than
                # by whether the number that comes out looks plausible.
                #
                # THE BAKED HALF IS LEFT ON ITS FORMULA DELIBERATELY, for now. `start` and
                # `n` above agree with the walk's slot AND width on 8,680 of 8,680 records
                # where bit 24 is set, so migrating it changes no pixel and is a separate
                # tidy-up; this branch is where the two differ.
                _fillpair = cls_pair_slot(rec, 24)
                if _fillpair is not None and _fillpair[0] == 'program' \
                        and _fillpair[1] < len(rec.words):
                    _fp = rec.words[_fillpair[1]] + 52
                    try:
                        _v = np.asarray(eval_program(asm, _fp,
                                                     default_inputs(asm, 1), {}, 1)).ravel()
                    except Exception:
                        _v = np.zeros(0, dtype=np.float32)
                    if _v.size == 1 and n > 1:
                        _v = np.repeat(_v, n)
                    if _v.size >= n and np.all(np.isfinite(_v[:n])):
                        W, H = rec.width, rec.height
                        if max_dim:
                            W, H = min(W, max_dim), min(H, max_dim)
                        N = W * H
                        outputs[i] = to_image(
                            np.tile(np.clip(_v[:n], 0.0, 1.0).astype(np.float32), (N, 1)),
                            N, H, W)
                        continue

                if not (rec.cls >> 8) & 1 or len(rec.words) < start + n:
                    # THE COLOUR IS NOT IN THE FILE. These are one-word records -- just the tag, no
                    # programs, no colour slot -- distinguishable by class, and they feed
                    # `transformation` in 329 of 334 consumer links. The value is the engine's default,
                    # and this format never records defaults, the same wall the FX-Map parameters hit.
                    #
                    # THE DEFAULT IS 0.0, AND THE ENGINE SAID SO. This used to refuse unless a caller
                    # opened an `assume` scope, which was right while nothing could arbitrate it. Two
                    # reference specimens now can, because in both the fill reaches a declared output as
                    # a pure passthrough, so the scored MAE is EXACTLY the candidate:
                    #
                    #   RoofTiles, `metallic` (record 2580), against RoofTiles_Metallic.png
                    #     fill 0.0 -> MAE 0.0000   0.25 -> 0.2500   0.5 -> 0.5000   1.0 -> 1.0000
                    #
                    #   Stylized_Sandy_Stone_Path, `output_5` (record 1), scored against all six of its
                    #   maps because that package names its outputs generically:
                    #     fill 0.0 -> exact match to SandyStoneRoad01_Metallic.png, 0.0000
                    #     fill 0.5 -> best is Normal at 0.0159      fill 1.0 -> AO at 0.0453
                    #
                    # The second is stronger: the manifest could not name that output, and matching at
                    # 0.0000 identified it as the metallic map on its own.
                    #
                    # WHAT THIS IS NOT: both scoring outputs are constant-zero maps, so this arbitrates
                    # the DEFAULT FILL and nothing about how a fill combines downstream. Still
                    # LOW_CONFIDENCE and still marked in assume.USED, because the value is inferred
                    # from behaviour rather than read from the file. Chesterfield cannot arbitrate it
                    # and was tried first: there the fill changes 6 records and 0 declared outputs, so
                    # every candidate ties, and a tie is not evidence for the incumbent.
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
                # THIS WINDOW CANNOT TELL A COLOUR FROM A PROGRAM, AND IT NEVER HAS TO. It is
                # tautological in FORM: a pointer or an inline program header read as float32 is a
                # denormal, about 1e-40, which is inside [-0.01, 1.01], so this test cannot reject
                # a program word and no size of sample would reveal that. It is unreachable in
                # FACT, because the gate above takes every such record first -- over the corpus plus
                # the reference packs, 9,512 records reach THIS read and 0 have a denormal
                # component, while 7,998 are diverted to the `uniform.fill` path. That gate is
                # STRUCTURAL, a class bit and a length, so it does not share this blind spot.
                #
                # RETRACTED, and recorded because the retraction is the useful part. This note
                # previously claimed 4,323 greyscale records "render black" from a misread inline
                # program. The 4,323 are real -- their slot at `start` does hold a program, and in
                # 3,526 it runs to the record end so no colour is stored -- but every one takes the
                # `uniform.fill` path and none reaches this line. They get the arbitrated fill,
                # marked LOW_CONFIDENCE and noted in `assume.USED`. The measurement applied this
                # file's `start` formula WITHOUT the gate that precedes it: reading a branch's guard
                # while skipping the branch's entry condition.
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
                # Parameter LOCATIONS are corpus-verified (FORMAT-NOTES.md, "directionalwarp's
                # parameters are bit-selected, like levels'", 99.92% tail-placement accuracy) and
                # warpangle's UNIT is confirmed directly from real bytecode: programs that compute
                # it end in `atan2(...) / 6.28319` -- 3,336 of 3,336 angle-shaped programs divide
                # by 2*pi, so the value is a FRACTION OF A FULL TURN.
                #
                # NOT corpus-verified: the displacement FORMULA (this filter's core math is fixed
                # in the engine) and intensity's absolute scale. This implements the standard
                # directional-warp shape -- sample a second, greyscale intensity map, centre it at
                # 0, scale by `intensity` and a fixed direction from `warpangle`, and offset the
                # main input's sampling position -- with intensity taken against a fixed 256-pixel
                # reference. That constant is NOT re-derived here and could be wrong by a constant
                # factor; real program-computed specimens (DLG-Tools__Rusted_Metal_01 records
                # 13/51/60/73/74) confirm only that SOME resolution-independent normalization is
                # real, since authors compute intensity as `min(K, K*$size.x/$size.y)`.
                #
                # Edge order is likewise a declared, unverified convention: a real paired source
                # (DLG-Tools__Camouflage.sbs) declares this node's connections as `input1` first,
                # `inputintensity` second, matching Record.edges[0]/[1] without independent proof
                # -- the same stance taken for blend's destination/source pair. Wrong here means a
                # plausible-looking but misdirected warp, not a crash.
                if len(rec.edges) < 2:
                    raise Unsupported("directionalwarp has fewer than 2 edges")
                for edge_rec in rec.edges[:2]:
                    if edge_rec not in outputs:
                        raise cascade("edge -> record %s has no output yet" % edge_rec)
                tainted = any(e in synthetic for e in rec.edges[:2])
                # See assume.QUESTIONS['dirwarp.edges'] -- the order is a declared convention
                # with no bytecode-level proof. Swapping it here keeps the experiment to one line.
                if assume.assumed('dirwarp.edges') == 'swapped':
                    rec = _SwappedEdges(rec)
                    assume.note(i)

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
                REFERENCE_PX = _reference_px(rec)
                disp = signed * intensity / REFERENCE_PX
                in_pos = pos + np.concatenate(
                    [disp * np.cos(turn) * np.ones((N, 1), dtype=np.float32),
                     disp * np.sin(turn) * np.ones((N, 1), dtype=np.float32)], axis=-1)

                result = sbsruntime.image_sampler(outputs[rec.edges[0]])(in_pos)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "gradient":
                # A gradient map: the input's luminance indexes an embedded ramp. `Record.ramp`
                # is decoded and corpus-verified (FORMAT-NOTES.md); what is added here is only
                # the lookup.
                #
                # Which component is the POSITION was not assumed. Over every ramp with 3+ stops,
                # component 0 ascends monotonically in 100% of tables in all four width classes,
                # and no other component does better than 25%.
                #
                # Only the GREYSCALE widths are implemented. The colour widths carry position
                # plus TWO components, not three:
                #
                #     (pos, value)                greyscale            603 records
                #     (pos, value, 32768)         greyscale + cls b8 2,683
                #     (pos, v1, v2)               colour                 144   refused
                #     (pos, v1, v2, 32768)        colour + cls bit 8     457   refused
                #
                # The trailing 32768 is constant in 3,175 of 3,175 reads, so the bit-8 width adds
                # a field this does not need rather than a channel.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
                table = rec.ramp
                if not table:
                    raise Unsupported("gradient record carries no readable ramp")
                # THE COLOUR RAMP'S TWO VALUES ARE ONE PACKED RGBA8888. This was refused as "2
                # value components, not 3 -- an RGB reading would be invention", which was right
                # to refuse and wrong about the shape: the entries are u16, so two of them are 32
                # bits, which is four 8-bit channels rather than two 16-bit ones.
                #
                # The signature is the alpha byte. Reading `v1 | (v2 << 16)` and unpacking
                # little-endian, over 181 colour gradient records and 22,961 stops, byte 3 is 255
                # in 99.9% (next commonest value: 0, seven times). A misread field does not put
                # 255 in the same byte 99.9% of the time. And the remaining three bytes read as
                # material colours outright -- (197, 143, 76) tan, (139, 92, 38) brown, (243,
                # 211, 167) cream, (253, 253, 253) near-white.
                #
                # Greyscale ramps are unaffected: their single value stays a u16 scaled by 65535,
                # the reading already verified against an independent lookup in test_filters.py.
                if rec.colour and isinstance(table[0][0], float) and len(table[0]) >= 4:
                    # THE FLOAT FORM NEEDS NO UNPACKING. `Record.ramp`'s five-float entries are
                    # (position, R, G, B, A) already in [0, 1]; the u16 packing below exists only
                    # because a u16 pair has to be reassembled into RGBA8888.
                    stops = np.array([e[0] for e in table], dtype=np.float32)
                    vals = np.array([list(e[1:5]) for e in table], dtype=np.float32)
                elif rec.colour:
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
                # A per-channel tone curve. `Record.curve_points` is decoded and corpus-verified:
                # six floats per knot, read there as a position pair followed by an incoming and
                # an outgoing tangent, and the first table read out was the identity.
                #
                # The handles are ABSOLUTE positions, not offsets -- a real S-curve knot reads
                # (0.464, 0.382) with handles (0.379, 0.119) and (0.549, 0.645), which brackets
                # the knot on both sides only under the absolute reading. So a segment is the
                # cubic Bezier P0=knot_i, P1=out_i, P2=in_{i+1}, P3=knot_{i+1}, and y is found by
                # inverting x(t) for t.
                #
                # NOT verified: that the engine inverts the same way. A Bezier segment is not a
                # function of x in general, and this bisects x(t) rather than solving it. Every
                # table read here has ascending x (`curve_points` checks it), where the two agree.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
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
                # `intensity` and `mblurangle`, named by containment against the permitted
                # sources (FORMAT-NOTES.md, the filter-naming section), and `mblurangle` is an
                # angle in TURNS -- the convention confirmed from bytecode for directionalwarp's
                # `warpangle`, where 3,336 of 3,336 angle-shaped programs divide by 2*pi.
                #
                # NOT verified, and shared with directionalwarp above: the absolute pixel scale
                # of `intensity`. Same fixed 256-pixel reference, same possible constant-factor
                # error. Wrong here means a blur of the wrong LENGTH along the right direction.
                # The kernel is a straight, uniformly weighted line through the sample point,
                # symmetric about it -- engine math rather than anything carried in this file.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
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
                REFERENCE_PX = _reference_px(rec)
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
                # WHERE the intensity is, derived here and corpus-checked: slot 4 + class bit 11.
                # The bit shifts the parameter block by one slot, the same growth Record.matrix
                # documents for `transformation`. Grouping warp records by class word in files whose
                # source declares a distinctive `intensity`: cls 0x02319 (bit 11 clear) -> slot 4,
                # 19 hits and 1 elsewhere; cls 0x02b19 (bit 11 set) -> slot 5, 11 hits and 1
                # elsewhere. Corpus-wide the slot decodes to a plausible intensity in 2,909 of
                # 2,936 records (99.1%). WHICH edge is which is structural: a real specimen
                # (Hard-Science-Old__CrustyLava records 125/128/129/130) has edges[1] = record 123
                # in every one while edges[0] varies -- one map warping many inputs -- and the
                # paired source names the connections `input1` and `inputgradient`.
                #
                # NOT corpus-verified: the displacement FORMULA and the absolute scale. This takes
                # the standard shape -- displace along the LOCAL GRADIENT of the gradient input,
                # which is what distinguishes `warp` from `directionalwarp`'s fixed angle --
                # against the same fixed 256-pixel reference.
                #
                # THIS BRANCH IS NOT THE SUSPECT WHEN A WARP DOES NOTHING, and the measurement
                # below cost a session that started by reading this code. On Bricks, 510 of 515
                # warp records return their source BYTE-IDENTICAL, and that is arithmetic: 345 are
                # handed a gradient input whose std is exactly 0.0, and the other 165 get gradient
                # std 0.0039 against intensity 0.06, which at W=64 displaces four thousandths of a
                # pixel. Both populations are the INPUT being flat, and the flatness descends to
                # `fxmaps` records with no image edges that render as a uniform 1.0: rec5596 emits
                # 1,024 patterns each carrying patternsize 5.0, which `splat` reads as canvas units
                # -- five times the canvas, a thousand times over, is a white rectangle. NOT a
                # 32x32 lattice: rec5596's branchoffset uses `rand`, so its positions are a
                # deterministic SCATTER and sqrt(N) = 32 was fitted to the count. The five records
                # here that ARE grids (5, 11, 20, 27, 33) say so structurally.
                #
                # AND THAT IS WHY THE LATTICE IS MISSING FROM THE OUTPUT. The output cone is a
                # ~50-stage accumulator of the form `blend(prev, warp(warp_chain, G))`: each warp
                # shifts by G and the blend lays the shifted copy down. With G identically zero
                # every warp is the identity and every blend a no-op, so the chain deposits one
                # motif where the engine deposits a grid. The fix is NOT `fx.patternsize == 'cell'`
                # -- swept against the Bricks references and refuted.
                if len(rec.edges) < 2:
                    raise Unsupported("warp has fewer than 2 edges")
                for e in rec.edges[:2]:
                    if e not in outputs:
                        raise cascade("edge -> record %s has no output yet" % e)
                # ...AND IT IS THE SAME INHERITED-BLOCK WALK hsl needed, not bit 11 alone.
                # `4 + bit11` froze one term of the mask-walk: the intensity follows the inherited
                # block `walk.py`'s `_CLS` describes, and bits 7 and 10 shift it too. The 592
                # records that set bit 10 are the proof -- at `4 + bit11` a plausible value appears
                # 88.2% of the time, at one slot later 100.0%, while for bit-10-clear records that
                # later slot is plausible only 5.8%.
                #
                # THE INTENSITY IS THE LAST HEADER SLOT, from the walk, and CONTAINMENT SETTLES IT
                # rather than a distribution. `param_slots.locate` pairs a source declaring a
                # distinctive intensity with that package's OWN binary and finds the one record
                # holding it, which is ground truth independent of every rule here: the walk scores
                # 13/13 on warp, 2/2 on blur and 2/2 on sharpen, against the old subset formula's
                # 11/13, 2/2 and 2/2. The formula it replaces missed two warp records outright and
                # was FITTED BY VALUE PROBING -- its own note recorded searching every subset of the
                # inherited bits for whichever "best lands a plausible intensity".
                #
                # AN EARLIER NOTE HERE REJECTED THE WALK, AND A CORRECTION TO IT BLAMED THE COST
                # MODEL. Both were wrong: `header_words` charges w1_present whenever its `w1`
                # argument is not None, and warp has two record shapes with only one carrying a w1
                # word, so a measurement passing `words[1]` unconditionally asked for the wrong
                # shape's header. Gated as its docstring requires -- and that gate now lives inside
                # header_words -- the two agree 26,795 of 26,795. The other half of that note stands
                # and is why this needed containment: class bit 12 is set in ZERO warp records, so
                # the gate that corroborates blur and sharpen does not exist here.
                #
                # WHERE end-1 STOPS BEING THE RIGHT QUESTION: it holds for filters with no
                # `PARAM_SPEC` entry, which carry one trailing scalar. Where several are named,
                # another parameter FOLLOWS the intensity -- `end-1` scores 7/10 on directionalwarp
                # and 0/2 on dirmotionblur, missing precisely the records where warpangle/
                # mblurangle is present, while `decompose.named_params` scores 27 of 27.
                #
                # WARP'S PAIR IS (29, 30), NOT (28, 29): the pairing is per filter, and bit 28 is
                # not in warp's cost table at all. Reading warp with blur's pair reports 0 baked
                # records and 24,815 "programs", which is warp's BAKED bit misread as a program
                # half. Asked for its own pair, warp is exact on both arms -- baked 24,815 of
                # 24,815, program 1,109 of 1,109, neither 871, pair slot == end - 1 in all 25,924.
                # THE PROGRAM ARM WAS SILENTLY RENDERING AS NO-WARP: this read `end - 1` as a float
                # unconditionally, and a pointer read as float32 is a denormal that passes the
                # guard below and gives intensity 0.
                #
                # THE NEITHER-BIT RECORDS CARRY NO INTENSITY AT ALL, and that is MEASURED. Group
                # records by class word with the intensity pair masked out and compare
                # `decompose(rec)['end']`: a neither-bit record is EXACTLY ONE WORD SHORTER than
                # its baked sibling -- warp 880 of 880, blur 140 of 140, sharpen 162 of 167 (the
                # other 5 have no baked sibling) -- and not one is the same length. So warp's 30
                # blocked outputs, blur's 20 and sharpen's 18 are NOT decode work; they need one
                # constant this format does not contain.
                _pair = cls_pair_slot(rec, 29)
                if _pair is None:
                    raise Unsupported("warp intensity: neither class bit 13 (baked) nor 14 "
                                      "(program) is set, so the source omitted it and the "
                                      "engine's default applies")
                sl = _pair[1]
                if sl >= len(rec.words):
                    raise Unsupported("warp record too short for an intensity slot")
                if _pair[0] == 'baked':
                    intensity = float(np.frombuffer(
                        np.uint32(rec.words[sl]).tobytes(), dtype=np.float32)[0])
                    if not (intensity == intensity and -1e3 < intensity < 1e3):
                        raise Unsupported("warp intensity slot %d is not a plausible float"
                                          % sl)
                else:
                    _q = rec.words[sl] + 52
                    intensity = None
                    if asm.body_lo <= _q < asm.body_hi and asm.valid_program(_q):
                        try:
                            _v = np.asarray(eval_program(asm, _q, default_inputs(asm, 1),
                                                         {}, 1, W=rec.width,
                                                         H=rec.height)).reshape(-1)
                        except Exception:
                            _v = np.zeros(0, dtype=np.float32)
                        if _v.size == 1 and np.isfinite(_v[0]):
                            intensity = float(_v[0])
                    if intensity is None:
                        raise Unsupported("warp intensity: class bit 14 names a program "
                                          "slot that does not evaluate to a scalar")
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
                REFERENCE_PX = _reference_px(rec)
                dx = (gx * W / REFERENCE_PX * intensity).reshape(N, 1)
                dy = (gy * H / REFERENCE_PX * intensity).reshape(N, 1)
                in_pos = pos + np.concatenate([dx, dy], axis=-1)

                result = sbsruntime.image_sampler(outputs[rec.edges[0]])(in_pos)
                outputs[i] = to_image(result, N, H, W)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "shuffle":
                # Slot 1 is four selector BYTES, one per output channel, in the order red, green,
                # blue, alpha. A selector 0-3 takes that channel from the first input, 4-7 takes
                # channel (s - 4) from the second. Read off a permitted paired specimen, exact on
                # all five of its records including the values the source leaves at their defaults
                # (SubstanceDesigner__color, 5 source nodes against 5 binary records):
                #
                #   source {channelgreen: 4}            -> R=0 G=4 B=0 A=0   x3
                #   source {channelblue: 4}             -> R=0 G=1 B=4 A=3
                #   source {channelblue: 4, alpha: 5}   -> R=0 G=1 B=4 A=5
                #
                # Corpus-wide 664 of 1,075 records have all four bytes <= 7, and of the 411 that do
                # not, 409 are the single-input layout whose EDGE sits in slot 1.
                if len(rec.words) < 2:
                    raise Unsupported("shuffle record too short for a selector word")
                if 1 in (rec.layout[0] or ()):
                    # THE SINGLE-INPUT LAYOUT KEEPS NO SELECTOR BYTES. Its selectors were recorded as
                    # "not established", and the earlier search missed them because they are not bytes
                    # at all: scanning every slot for a quad of bytes <= 7 finds only all-zero words,
                    # and an identity byte-quad would read 0,1,2,3.
                    #
                    # They are a ONE-HOT FLOAT4 at the block start + 1: exactly one 1.0 and three 0.0,
                    # the position of the 1.0 naming the channel. Over 120 files, 471 of 600
                    # single-input records (78.5%) are one-hot, and all 471 are `colour` False, which
                    # is what extracting ONE channel produces; the channel is distributed R 31.4%,
                    # G 33.8%, B 23.1%, A 11.7%. The multi-input layout does not do this (21 of 476).
                    # Verified end to end: fed an input whose channels are 0.1/0.2/0.3/0.4, a record
                    # whose one-hot names channel k returns exactly that channel.
                    #
                    # ASK THE PRESENCE BIT BEFORE MEASURING THE RECORD -- a record whose class bit 8 is
                    # clear stores no weight vector, so "too short for one" describes a slot that was
                    # never going to be there. It was the top blocker under this filter, 24 declared
                    # outputs across 30 files. AND THE SLOT COMES FROM THE WALK: this branch located
                    # the vector as `rec.layout`'s block start PLUS ONE, while class bit 8 is w0 bit 24
                    # and the walk already reports it as a four-word field. Over 3,332 corpus records
                    # with the bit set they agree 3,090 times and DISAGREE 242 -- 196 where the old
                    # window ran PAST THE END, and ~46 where it was in range but on the wrong words, a
                    # plausible wrong picture with no error at all.
                    _walked = decompose.decompose(rec)
                    _wslot = _wwidth = None
                    for _b, _s, _wd in ((_walked or {}).get('cls_params') or []):
                        if _b - 16 == 8:
                            _wslot, _wwidth = _s, _wd
                    if ((rec.cls >> 8) & 1):
                        if _wslot is None:
                            raise Unsupported("shuffle class bit 8 is set but the walk "
                                              "names no slot for the weight vector")
                        if _wwidth != 4:
                            raise Unsupported("shuffle weight field is %s words wide, not 4"
                                              % _wwidth)
                        if _wslot + 4 > len(rec.words):
                            raise Unsupported("shuffle single-input record too short for a "
                                              "one-hot channel selector")
                    # IT IS A WEIGHT VECTOR, NOT A ONE-HOT SELECTOR -- the one-hot form is its special
                    # case. The generalisation is forced by what the non-one-hot records hold: of the
                    # 79 this refused, the commonest are (0.30, 0.59, 0.11, 0.00) x17 -- Rec.601
                    # LUMINANCE WEIGHTS -- then (0.25, 0.25, 0.25, 0.00) x10 and (0.00, 0.80, 0.20,
                    # 0.00) x2. A field holding the luminance weights is not a malformed selector; it
                    # is a weighted sum, and `take channel k` is that sum with a one at k. The rest of
                    # the 79 are infinities and values like 2.9e20 and still refuse.
                    #
                    # CLASS BIT 8 SAYS WHETHER THE VECTOR IS THERE, and the value test is no substitute
                    # for asking. Over 307 single-input records in 60 files the bit and a
                    # plausible-looking float4 agree 302 times, and the five that disagree are the
                    # point: 4 have the bit CLEAR and store no vector, but the bytecode at that offset
                    # decodes to floats the value test accepts -- (0.0, -2.0, 3.0, -2.0) among them, an
                    # opcode word and its inline constants. The fifth has the bit SET, reads all-zero,
                    # carries an extra program pointer, and still refuses.
                    #
                    # WHICH SOURCE NODE THIS IS: the sources declare `grayscaleconversion` (100 nodes,
                    # `channelsweights`, a float4) and `shuffle` (43 nodes, integer selectors) -- two
                    # node types, one compiled filter.
                    if not (rec.cls >> 8) & 1:
                        # No parameter stored, so the value is the node's default and the default is not in
                        # the file -- the same shape as `uniform.fill` before a specimen arbitrated it.
                        #
                        # BIT 8 MEANS "THE SOURCE DECLARED ONE", confirmed from the sources rather than
                        # inferred from the absence of a slot. Counting `grayscaleconversion` nodes that
                        # declare `channelsweights` against records with bit 8 clear: stylized_rocks_magma
                        # 5 nodes, 3 declaring -> 2 bit-8-clear; hblend 10/10 -> 0; triDraw 2/2 -> 0;
                        # celtic_plate 1 node, 0 declaring -> 22; and eleven more files declaring none, all
                        # with bit-8-clear records. The first line carries it: 5 = 3 + 2 exactly. WHICH IS
                        # ALSO WHY THE SOURCES CANNOT SUPPLY THE VALUE -- they omit `channelsweights`
                        # precisely when it is the default.
                        #
                        # THE MANIFEST DOES NOT CARRY IT EITHER, checked over all 437: the .xml vocabulary
                        # is entirely interface. One manifest mentions `grayscaleconversion` and it is a
                        # trap -- `GrayscaleConvert.sbsar` is a third-party filter graph whose `method`
                        # combobox defaults to YPrPb (.29, .58, .11), one author's exposed choice compiled
                        # from a bitmap and a pixelprocessor, not the built-in node. NO REFERENCE PACKAGE
                        # ARBITRATES IT either. AND A FOURTH DIRECTION CLOSES RATHER THAN OPENS: class bit
                        # 8 is w0 bit 24 and costs FOUR words, so its program half would be w0 bit 25, and
                        # if the compiler ever emitted the weights as a PROGRAM this refusal would be a
                        # missed read. It never does -- over all 7,682 shuffle records, bit 24 set with 25
                        # clear 7,080, both clear 602, bit 25 set 0.
                        # THE ARBITER EXISTS AND IS INERT, which is worth more than either
                        # a value or another refusal, because the next person to reach for
                        # it should not spend the day I did.
                        #
                        # `RoofTiles` is a REFERENCE PACK and five of its six declared
                        # outputs -- height, AO, roughness, normal, basecolor -- are blocked
                        # here, so the exported maps can in principle score a candidate.
                        # Supplying one does unblock them: with `grayscale.weights` set and
                        # warp's absent intensity supplied too (its cone needs both), the
                        # file goes from 1 of 6 declared outputs to 6 of 6.
                        #
                        # It cannot choose between candidates. Over Rec.601 (0.3, 0.59,
                        # 0.11), Rec.709, equal thirds, equal quarters and one-hot red, the
                        # scored mean MAE against the pack's own maps is 0.1192 for four of
                        # them and 0.12039 for the fifth, and the mean correlation is 0.034
                        # -- which is no agreement at all. Sweeping warp's absent value over
                        # 0, 0.1, 0.5, 1, 2 and 10 moves neither number by one part in 1e5.
                        #
                        # And that is not a threshold argument. Rendering the file twice --
                        # once at Rec.601 with warp 0, once at one-hot red with warp 10 --
                        # gives SIX OF SIX outputs identical in mean and standard deviation
                        # to six decimals. The declared outputs do not depend on either
                        # value, so this arbiter can unblock the records and cannot rank the
                        # candidates.
                        #
                        # WHAT THAT SAYS ABOUT THE REFUSAL. It is correct in principle and
                        # it cascades: a record deep in the graph declines a parameter that
                        # provably cannot change the picture, and five outputs go with it.
                        # The refusal stays, because "any value renders the same here" is a
                        # fact about RoofTiles and not about the format. But the cost is now
                        # measured rather than assumed, and the arbiter is recorded as
                        # available-and-inert rather than as untried.
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
                            np.array(rec.words[_wslot:_wslot + 4],
                                     dtype=np.uint32).tobytes(), dtype=np.float32)
                    if not (np.all(np.isfinite(hot)) and np.all(np.abs(hot) <= 4.0)
                            and float(np.abs(hot).sum()) > 1e-6):
                        raise Unsupported("shuffle single-input weight vector is not "
                                          "plausible (%r)" % (np.round(hot, 4).tolist(),))
                    if rec.edges[0] not in outputs:
                        raise cascade("edge -> record %s has no output yet"
                                          % rec.edges[0])
                    W, H = rec.width, rec.height
                    if max_dim:
                        W, H = min(W, max_dim), min(H, max_dim)
                    N = W * H
                    src = sbsruntime.image_sampler(outputs[rec.edges[0]])(pos_grid(W, H))
                    used = [k for k, w in enumerate(hot) if abs(w) > 1e-9]
                    if used and max(used) >= src.shape[-1]:
                        # Same refusal the multi-input path makes, for the same reason: a weight on a
                        # channel the input lacks means the reading is wrong here.
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
                        raise cascade("edge -> record %s has no output yet"
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
                        # Not silently clamped to an existing channel: a selector naming a channel the
                        # input does not carry means the reading is wrong here, and a wrong image is
                        # worse than a refusal.
                        raise Unsupported("shuffle selects channel %d of an input with "
                                          "only %d" % (c, a.shape[-1]))
                    cols.append(a[:, c:c + 1])
                outputs[i] = to_image(np.concatenate(cols, axis=-1), N, H, W)
                if tainted:
                    synthetic.add(i)

            elif (rec.filter_name == "emboss"
                  and assume.assumed('emboss.probe') == 'passthrough'):
                # COUNTING PROBE ONLY -- see assume.QUESTIONS['emboss.probe']. Renders the record
                # as its first input so the number of outputs emboss gates can be measured. Not a
                # reading of emboss, and its images are not to be scored.
                if not rec.edges or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
                outputs[i] = np.asarray(outputs[rec.edges[0]])
                LOW_CONFIDENCE.add(i)
                assume.note(i)

            elif rec.filter_name == "normal":
                # A normal map from a height input. The sources declare `intensity` (61 sightings),
                # `input2alpha` (31, always 0), `format` (3) and `inversedy` (1).
                #
                # WHERE `intensity` IS -- deliberately NOT a fixed slot. An earlier attempt derived
                # "slot 4 + class bit 11", `warp`'s rule, from containment against 22 files: slot 4
                # held a declared value in 33.7% of 98 records against a 6.5% control, and bit 11
                # predicted slot 4 versus 5 in 43 of 44. Both numbers were real and the rule was
                # still wrong, because in most records those slots hold PROGRAM POINTERS, and a
                # pointer read as a float is a denormal that a naive plausibility test accepts. The
                # block starts at slot 3 in 201 of 201 records with 1 to 4 leading programs, and no
                # popcount predicts how many. A CONTROLLED TEST caught it: a height RAMP produced a
                # perfectly flat normal map. So intensity is singled out by WIDTH instead, the way
                # `transformation` singles out its matrix, refusing when that is ambiguous.
                #
                # AND IT IS NOT A CLASS-WORD PAIR EITHER, which is the obvious next idea and is
                # refuted three ways. `blur`, `sharpen`, `warp`, `shuffle` and `uniform` all keep
                # their scalar in an adjacent (baked, program) bit pair that `cls_pair_slot` reads,
                # so `normal` looks like it should too, and `decompose` does report pairs for it --
                # one of {10, 11}, one of {14, 15}, bit 16, and sometimes (26, 27). Over 1,353
                # records across the corpus and the reference packs:
                #
                #   * bit 15's slot names a program returning TWO components on 854 of 916 -- the
                #     output-size expression (w, h), not a scalar. Only 62 return one.
                #   * bit 27's slot is NOT a valid program on 1,053 of 1,065. It is not a pointer.
                #   * bit 26 is charged TWO words and its second word reads 9.34e-33, which is the
                #     `0x0A420001` program preamble as float32 -- bytecode, not a component. Its
                #     first word reads 12.0, squarely in the block's observed intensity range.
                #
                # The (26, 27) pair IS real as a COST: grouping by class word with those bits
                # masked, bit 27 adds exactly one word to the walk's `end` and bit 26 adds two,
                # against records that set neither -- cls bases 0x319 (end 6 vs 5), 0x309 (6 and 7
                # vs 5), 0x019 (6 vs 5) and 0x318 (5 vs 4). So the cost model charges the pair and
                # the CONTENT contradicts the widths it charges, which makes bit 26's width the
                # thing in question rather than this branch. Handed to costs.json's owner.
                #
                # So the width rule stays. It is not elegant and it is not a formula either -- it
                # asks each program what it returns rather than computing where one should be.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
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
                    # No program names it: look for a baked float in the parameter block. Denormals are
                    # excluded explicitly -- they are what a pointer looks like read as a float.
                    #
                    # THIS FALLBACK SURVIVED THE TEST THAT KILLED `blur`'s, and the asymmetry is the
                    # evidence. A parameter with two readings must have two agreeing distributions, and
                    # the SOURCE DECLARATIONS are a third instrument: `normal` declares p50 4.5 over
                    # -0.05..100 while its block reads p50 12 over 0.5..256, the same regime sharing the
                    # specific values 16, 3 and 0.5; `blur` declares p50 1.25 clustered 0.2..1.25 while
                    # its slot 3 is 72.5% exact powers of two through 64, a different quantity.
                    #
                    # THE SLOT IS READ, NOT SEARCHED FOR -- this was an eight-word window taking the
                    # first slot reading as a float in 1e-3..1e3, the last plausibility SEARCH in this
                    # file. The structural answer is the LAST HEADER SLOT, and for this filter it comes
                    # from `record_layout.header_words` rather than `decompose`: the two readers
                    # disagree and the walk is the one that is wrong (it runs LONGER on 1,358 of 1,358
                    # normal records). Containment picked the winner on the one permitted pairing,
                    # `SubstanceDesignerPractice` record 362 declaring 2.01 -- header_words gives slot
                    # 4, correct; the walk's end - 1 gives 6. Against the search it replaces, over
                    # 1,379 records: 961 agree, 65 have the scan landing AT/PAST the header end (so it
                    # was reading bytecode), 322 the scan misses entirely, 10 undecided, 0 impossible.
                    _sl = record_layout.header_words(
                        rec.filter_id, rec.words[0],
                        rec.words[1] if len(rec.words) > 1 else None,
                        asm.header.get('version') if isinstance(asm.header, dict) else 0)
                    if _sl is not None and 0 <= _sl - 1 < len(rec.words):
                        # THE LAST HEADER SLOT HOLDS EITHER A BAKED FLOAT OR A POINTER, and
                        # only the baked arm existed. That is the same baked/program split
                        # `cls_pair_slot` reads for blur, sharpen, warp, shuffle and uniform,
                        # and the slot here is the walk's, so the two arms are two readings
                        # of ONE named slot rather than two places to look.
                        #
                        # Asking the pointer first, because the test that separates them is
                        # structural: `valid_program` either resolves at that address or it
                        # does not. The float arm's `1e-3 < abs(f) < 1e3` cannot make the
                        # distinction -- a pointer through float32 is a denormal near 1e-40,
                        # which the window happens to exclude, so those records fell through
                        # to a refusal reading "neither a program nor a baked float" while
                        # the record was in fact naming a program.
                        #
                        # Corpus-wide, at the last header slot of a `normal` record:
                        #
                        #     a valid PROGRAM, width rule also found one     263
                        #     a valid PROGRAM, width rule found NOTHING       97
                        #     a baked float                                  989
                        #     neither                                          4
                        #
                        # The 97 are what this arm adds. They are the records that failed on
                        # ImportTest, SubGraphTest, AnimatedExample and EvilOrb, and every
                        # one of them reads a denormal at that slot -- 8.6e-41, 2.1e-41,
                        # 1.35e-38 -- which is a pointer, not an intensity.
                        _isl = _sl - 1
                        _iptr = rec.words[_isl] + 52
                        if (asm.body_lo <= _iptr < asm.body_hi
                                and asm.valid_program(_iptr)):
                            try:
                                _iv = np.asarray(eval_program(
                                    asm, _iptr, default_inputs(asm, 1), {}, 1)).reshape(-1)
                            except Exception:
                                _iv = np.zeros(0, dtype=np.float32)
                            if _iv.size >= 1 and np.isfinite(_iv[0]):
                                intensity = float(_iv[0])
                                LOW_CONFIDENCE.add(i)
                        if intensity is None:
                            f = float(np.frombuffer(np.uint32(rec.words[_isl]).tobytes(),
                                                    dtype=np.float32)[0])
                            if np.isfinite(f) and 1e-3 < abs(f) < 1e3:
                                intensity = f
                                LOW_CONFIDENCE.add(i)
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
                # NOT VERIFIED, stated as directionalwarp's is: the FORMULA and intensity's
                # absolute scale. This filter's math is engine-side. The standard
                # height-to-normal shape is used -- central-difference, scale by intensity,
                # normalise against a unit Z. `format` and `inversedy` are not decoded.
                gy, gx = np.gradient(height)
                # `inversedy` -- see assume.QUESTIONS['normal.inversedy']. ADOPTED AS THE DEFAULT.
                # It was opt-in because it moved exactly ONE channel, and one channel is not a
                # population. That measurement predates the reference-pairing fixes: Bricks now
                # renders 12,585 of 12,585 records and FIVE of its graphs produce a normal map with
                # real signal. On all five the correlation FLIPS SIGN WITH ITS MAGNITUDE INTACT to
                # three decimals (-0.585 -> +0.585, -0.475, -0.594, -0.504, -0.683), which is what
                # a handedness error looks like and what a gain or geometry error cannot.
                #
                # SURGICAL: of 112 scored channels exactly 7 move, all `normal` ch1, all improve,
                # and the other 105 are byte-identical. It is TEN RECORDS, NOT ONE, all carrying
                # word1 = 5, and not a Bricks quirk: 118 of 1,447 normal records set the bit across
                # 40 of 444 files.
                #
                # WHAT WOULD STILL REFUTE IT: only one PACKAGE with an exported normal map sets the
                # bit on the record that feeds it, so any field set in Bricks and clear elsewhere
                # fits equally. minime453__Stylized_Sandy_Stone_Path sets it on rec 175, which
                # feeds basecolor/AO/height, while its exported normal comes from rec 1452 with the
                # bit CLEAR and needs no flip -- consistent, but not a second confirmation.
                if (assume.assumed('normal.inversedy', 'word1bit2') == 'word1bit2'
                        and len(rec.words) > 1 and (rec.words[1] >> 2) & 1):
                    gy = -gy
                    LOW_CONFIDENCE.add(i)
                    assume.note(i)
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
                # An isotropic blur. The source declares exactly ONE real parameter, `intensity`
                # (64 sightings across 18 permitted files), plus a single `randomseed`.
                #
                # WHERE `intensity` IS -- and note what does NOT answer this. PARAM_POPCOUNT
                # establishes `popcount(cls & 0x2881)` as the number of leading block slots holding
                # PROGRAMS, exact over 43,883 reads, which says nothing about which slot is
                # `intensity`. Assuming the block start gives 6.6% own-file containment against a
                # 6.0% control; scanning every slot, only slot 3 exceeds its control materially
                # (14.6% against 2.9%), and counting every declared value rather than file-unique
                # ones put slot 4 at 10.9% against a 22.4% control. AND THE RATE ITSELF IS NOT
                # ACCURACY -- it is ceilinged by (distinctive values declared) / (records
                # compiled), so the 0.0% controls are the load-bearing half.
                #
                # THAT EVIDENCE IS WEAKER THAN THE ONE THAT ALREADY FOOLED ME: `normal` had 33.7%
                # against 6.5% plus a 97.7% bit correlation and was still wrong, because a pointer
                # read as float32 is a denormal that passes a plausibility test. The denormal guard
                # is applied here, but this rests on test_filters.py -- an impulse must spread
                # symmetrically, a constant must survive, the centroid must not move.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
                tainted = rec.edges[0] in synthetic
                # WHERE `intensity` ACTUALLY IS -- source-verified, and neither of the two places
                # this code looked before. It is the BAKED FLOAT IMMEDIATELY AFTER THE SIZE BLOCK,
                # which is one slot or two depending on how the size is stored: with nprog == 0 the
                # size is BAKED as (w, h) at 2,3 and the intensity is slot 4; with nprog >= 1 the
                # leading nprog slots are POINTERS from 2 and the intensity is 2+nprog. Read off
                # the slot distributions -- for nprog >= 1 those leading slots read as denormals
                # near 1e-39 (188 of 188 at slot 2 for nprog==1, 557 of 557 at slots 2 AND 3 for
                # nprog==2), the slot straight after carries ordinary small values, and the ones
                # after THAT go back to denormals and 3.2e37 junk. The pair reading is not assumed:
                # over nprog==0 records slots 2 and 3 are 99.1% and 100.0% exact powers of two, and
                # in 102 of them they equal the record's own width and height.
                #
                # THE PROGRAM WAS NEVER THE INTENSITY. This code read `filter_programs[:1]` and
                # called it that; on `flowingLava` that program evaluates to 1.0 and on
                # `PW_ConcreteWall001` to 2.0 and 0.9428, none of which either source declares --
                # because it is the SIZE expression. The evidence for the slot is exact set
                # recovery, not a rate: `flowingLava` declares 8 distinct intensities and slot 3 of
                # its nprog==1 records holds exactly those 8, one each; across every permitted
                # paired source, 39 of 54 (72.2%) against an 11.1% CONTROL. 0.0 is a legitimate
                # intensity and must pass the guard; a pointer read as float32 must not.
                #
                # THE SLOT COMES FROM THE WALK, though. NOTHING IN THE FORMAT STORES A SLOT NUMBER,
                # so a rule of the shape `base + some class bits` is a fitted patch, and two such
                # patches disagreed about this very slot -- this file's `2 + nprog` and
                # `param_slots.predicted_slot` -- on a third of blur records, with no reference
                # able to separate them, BECAUSE NEITHER IS A READ. `decompose(rec)['end']` is the
                # header boundary, equal to `record_layout.header_words` in 15,371 of 15,371 blur
                # records, so the intensity is simply end - 1. That is what class bit 12 has been
                # saying while the two formulas argued underneath it: bit-12-set records read a
                # plausible baked value at end-1 in 14,931/14,931 blur and 1,148/1,148 sharpen,
                # bit-12-clear ones read a non-value in 440/440 and 175/175, while the formulas
                # reach 14,692 and 1,120 and land on a DIFFERENT plausible float in 820 records.
                #
                # So the bit chooses BAKED vs COMPUTED at one fixed position; it does not say the
                # parameter is absent. A bit-12-clear record has an intensity and this file refuses
                # it -- 49 blur and 18 sharpen declared outputs, the largest single root cause in
                # `output_census`. Not wired because the program only reads as an intensity for
                # some: 60 evaluate 1-wide (p50 1.00) while 38 evaluate 2-wide, the shape of
                # `$outputsize`, and only 8 of those sit at the size-expression slot.
                _pair = cls_pair_slot(rec, 28)
                _islot = _pair[1] if _pair else None
                _baked = bool(_pair and _pair[0] == 'baked')
                if _baked and _islot is not None and _islot < len(rec.words):
                    v = float(np.frombuffer(np.uint32(rec.words[_islot]).tobytes(),
                                            dtype=np.float32)[0])
                    if np.isfinite(v) and (v == 0.0 or 1e-6 < abs(v) < 1e4):
                        intensity = v
                # CLASS BITS 12 AND 13 ARE THE (BAKED, PROGRAM) PAIR FOR THIS PARAMETER, which is
                # the discriminator the previous note said was missing. Both cost ONE WORD -- w0
                # bits 28 and 29 -- so each owns a slot, and they are MUTUALLY EXCLUSIVE:
                #
                #     blur      bit12 only 14,931    bit13 only  303    neither 137    both 0
                #     sharpen   bit12 only  1,148    bit13 only    8    neither 167    both 0
                #
                # The earlier reading was "bit 12 clear means the intensity is a program at
                # end - 1", which conflated bit-13 records, neither-bit records and the baked ones;
                # evaluating end - 1 across all of them gave 60 results 1-wide and 38 2-wide, and
                # the 2-wide ones looked like an unexplained residue. Restricted to records where
                # BIT 13 OWNS THE SLOT, all 60 hold a program at the slot the walk names, all
                # evaluate 1-wide, p50 1.00. The 2-wide reads were bit-13-CLEAR records.
                elif (_pair and _pair[0] == 'program'
                      and _islot is not None and _islot < len(rec.words)):
                    _p = rec.words[_islot] + 52
                    if asm.body_lo <= _p < asm.body_hi and asm.valid_program(_p):
                        try:
                            _v = np.asarray(eval_program(asm, _p, default_inputs(asm, 1),
                                                         {}, 1, W=rec.width,
                                                         H=rec.height)).reshape(-1)
                        except Exception:
                            _v = np.zeros(0, dtype=np.float32)
                        if _v.size == 1 and np.isfinite(_v[0]):
                            intensity = float(_v[0])
                # THE SLOT-3 FALLBACK IS WITHDRAWN. It rendered 881 records and was reading a
                # different field. The instrument needs no source declarations: this parameter has
                # TWO readings, one of them -- the width-1 program result -- trusted, so the two
                # distributions have to agree. Over 60 files, the program path gives n=53 at p50
                # 1.00 while slot 3 gives n=881 at p50 5.00 with 72.5% EXACT powers of two through
                # 64. That ladder is a size, a mip level or a tiling count, not an intensity: the
                # sources declare blur intensity as 1.0, 1.25 and 0.2 across 17 files with no power
                # of two above 1, and slot 3 = 64 asks for a 64-pixel radius on a 256-pixel image.
                # Containment said otherwise at 14.6% against 2.9% and was the weaker instrument.
                # The KERNEL stays verified -- impulse to a 3x3 box, max exactly 1/9, energy
                # conserved, centroid to 0.01 px. It is the radius that is unestablished.
                #
                # WHEN BIT 12 IS CLEAR, THE FIRST PROGRAM RETURNING A SCALAR IS THE CANDIDATE --
                # under `assume`, not a decode. A previous note said the programs supply nothing,
                # on a measurement that read `filter_programs[-1]` and so mixed three populations.
                # Index 1 is a SCALAR in 20 of 20 records with values matching the trusted
                # distribution, while index 0 is 2-comp in 28 of 33; index 1 reads `$outputsize` in
                # 0 of 57 records against index 0's 8 of 93. Reading by WIDTH rather than position
                # also covers the single-program records and agrees on all 40 where both apply. Not
                # source-confirmed: containment recovers 1 of 42 against a 2-of-42 control.
                if intensity is None and assume.assumed('blur.intensity') == 'program':
                    for _ptr in (rec.filter_programs or ()):
                        try:
                            _v = np.asarray(eval_program(asm, _ptr, default_inputs(asm, 1),
                                                         {}, 1, W=rec.width,
                                                         H=rec.height)).reshape(-1)
                        except Exception:
                            continue
                        if _v.size == 1 and np.isfinite(_v[0]):
                            intensity = float(_v[0])
                            LOW_CONFIDENCE.add(i)
                            assume.note(i)
                            break
                if intensity is None:
                    # THE ABSENCE IS MEASURED, not assumed -- a neither-bit blur record is one word
                    # shorter than its baked sibling in 140 of 140. See the warp branch.
                    raise Unsupported(
                        "blur intensity: %s (walk slot %s)"
                        % ("neither class bit 12 (baked) nor 13 (program) is set, so the "
                           "source omitted it and the engine's default applies"
                           if not (_pair or _baked) else
                           "class bit 13 names a program slot that does not evaluate to a "
                           "scalar" if not _baked else
                           "the walk does not resolve this record's header" if _islot is None
                           else "slot does not read as a plausible intensity",
                           _islot))

                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                src = to_image(sbsruntime.image_sampler(outputs[rec.edges[0]])(pos), N, H, W)
                # NOT VERIFIED, and shared with directionalwarp and dirmotionblur: the absolute
                # pixel scale of `intensity`. A separable box blur is used, which is what the
                # parameter means before any kernel shape is assumed; a Gaussian would differ in
                # the tails and nothing here distinguishes them.
                REFERENCE_PX = _reference_px(rec)
                radius = float(np.clip(abs(intensity), 0.0, 256.0)) / REFERENCE_PX
                rpx = int(round(radius * max(W, H)))
                if rpx < 1:
                    outputs[i] = src            # a blur of sub-pixel radius is the identity
                else:
                    k = 2 * rpx + 1
                    if assume.assumed('blur.kernel', 'box') == 'gaussian':
                        # See assume.QUESTIONS['blur.kernel']. sigma = rpx/2 puts the
                        # box's half-width at two sigma, the usual correspondence.
                        _d = np.arange(-rpx, rpx + 1, dtype=np.float64)
                        _w = np.exp(-0.5 * (_d / max(rpx / 2.0, 1e-6)) ** 2)
                        _w /= _w.sum()
                        acc = np.zeros_like(src)
                        for _j, d in enumerate(range(-rpx, rpx + 1)):
                            acc += np.roll(src, d, axis=1) * _w[_j]
                        out2 = np.zeros_like(acc)
                        for _j, d in enumerate(range(-rpx, rpx + 1)):
                            out2 += np.roll(acc, d, axis=0) * _w[_j]
                        outputs[i] = np.clip(out2, 0.0, 1.0)
                    else:
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

            elif rec.filter_name == "emboss":
                # A DIRECTIONAL RELIEF, not a runnable program: the record's programs never sample
                # an input, they only compute the built-in's scalars. Re-derived on the identical
                # RoofTiles rec1997/2001/2221 -- prog A writes slot 0 = (1/W, 1/H), the texel size,
                # and slot 2 = 0.005859375 * (W, H) * (1, -1), a texel COUNT (12 at 2048, so not UV
                # on its own); their product is a CONSTANT 0.005859375 in UV at every resolution,
                # at 45 degrees (+x, -y). Prog B returns 0.1 * 2048 / size.
                #
                # EDGES ARE [base, gradient], Input + Input Gradient. HOW THE INTENSITY ENTERS IS
                # ARBITRATED, not chosen: the resolution scaling lives in the built-in, so the
                # bytes do not say whether it amplifies the relief or compensates the sampling, and
                # the two differ by 8x here. See assume.QUESTIONS['emboss.intensity'].
                if len(rec.edges) < 2 or any(e not in outputs for e in rec.edges[:2]):
                    raise cascade("emboss edge -> record has no output yet")
                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                pos = pos_grid(W, H)
                _base = to_image(sbsruntime.image_sampler(outputs[rec.edges[0]])(pos), N, H, W)
                _gsrc = sbsruntime.image_sampler(outputs[rec.edges[1]])
                _OFF = 0.005859375
                _shift = pos + np.array([_OFF, -_OFF], dtype=np.float32)
                _g0 = to_image(_gsrc(pos), N, H, W)[:, :, :1]
                _g1 = to_image(_gsrc(_shift), N, H, W)[:, :, :1]
                _k = 0.1
                if assume.assumed('emboss.intensity') == 'program':
                    _fp = rec.filter_programs or ()
                    if _fp:
                        try:
                            _v = np.asarray(eval_program(asm, _fp[0],
                                                         default_inputs(asm, 1), {}, 1,
                                                         W=rec.width, H=rec.height)).reshape(-1)
                            if _v.size and np.isfinite(_v[0]):
                                _k = float(_v[0])
                        except Exception:
                            pass
                    assume.note(i)
                outputs[i] = np.clip(_base + _k * (_g0 - _g1), 0.0, 1.0)
                if any(e in synthetic for e in rec.edges[:2]):
                    synthetic.add(i)

            elif rec.filter_name == "sharpen":
                # WHERE ITS INTENSITY IS, read the same way `blur`'s was. `sharpen` is not in
                # PARAM_SPEC, so there is no named parameter to consult; it takes one image edge
                # and one scalar, and the slot is the LAST HEADER SLOT from the walk. The table
                # that used to sit here crowned the best of five hand-fitted formulas at 79%, which
                # was the wrong contest: none of the five is a read. `decompose(rec)['end'] - 1`
                # scores 1,323 of 1,323 against the old rule's 1,120, landing on the sharpen
                # distribution (p50 0.25, 0.0..1.2).
                #
                # THE KERNEL IS A READING, the same one `blur` documents: an unsharp mask over a
                # 3x3 box. What is decoded is WHERE the intensity is; what the engine convolves
                # with is not established. A constant image is unchanged and intensity 0 is the
                # identity, both by construction.
                if not rec.edges or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
                tainted = rec.edges[0] in synthetic
                _pair = cls_pair_slot(rec, 28)
                islot = _pair[1] if _pair else None
                # CLASS BITS 12 AND 13 ARE THE (BAKED, PROGRAM) PAIR -- see the note in `blur`,
                # which this filter shares. Bit 12 owns a baked slot, bit 13 a program slot, they
                # never co-occur (1,148 / 8 / 167 / 0 here), and whichever is set owns the last
                # header slot. ORDER MATTERS: `cls_pair_slot` returns None both when neither bit is
                # set and when the walk cannot resolve the record, and the absent case is the
                # common one, so it is asked first. THE ABSENCE IS MEASURED -- a neither-bit
                # sharpen record is one word shorter than its baked sibling in 162 of 167.
                if not ((rec.words[0] >> 28) & 1 or (rec.words[0] >> 29) & 1):
                    raise Unsupported("sharpen intensity: neither class bit 12 (baked) nor "
                                      "13 (program) is set, so the source omitted it and "
                                      "the engine's default applies")
                if islot is None:
                    raise Unsupported("sharpen intensity: the walk does not resolve this "
                                      "record's header")
                if islot >= len(rec.words):
                    raise Unsupported("sharpen intensity: slot %d past the record end"
                                      % islot)
                amount = None
                if _pair and _pair[0] == 'baked':
                    amount = float(np.frombuffer(np.uint32(rec.words[islot]).tobytes(),
                                                 dtype=np.float32)[0])
                    if not (np.isfinite(amount)
                            and (amount == 0.0 or 1e-6 < abs(amount) < 1e4)):
                        raise Unsupported("sharpen intensity slot does not read as a "
                                          "plausible value (%r)" % amount)
                elif _pair and _pair[0] == 'program':
                    _p = rec.words[islot] + 52
                    if asm.body_lo <= _p < asm.body_hi and asm.valid_program(_p):
                        try:
                            _v = np.asarray(eval_program(asm, _p, default_inputs(asm, 1),
                                                         {}, 1, W=rec.width,
                                                         H=rec.height)).reshape(-1)
                        except Exception:
                            _v = np.zeros(0, dtype=np.float32)
                        if _v.size == 1 and np.isfinite(_v[0]):
                            amount = float(_v[0])
                    if amount is None:
                        raise Unsupported("sharpen intensity: class bit 13 names a program "
                                          "slot that does not evaluate to a scalar")
                else:
                    # UNREACHABLE for the neither-bit case, refused above; this catches a pair the walk
                    # reports in a state neither arm reads.
                    #
                    # NEITHER BIT MEANS THE SOURCE OMITTED THE PARAMETER, confirmed from the SOURCE
                    # side, which is where an absence can be proved: over the permitted paired sources,
                    # 15 sharpen nodes -- 13 declaring an `intensity`, 2 declaring none -- against 45
                    # records, 42 bit 12, 0 bit 13, 3 neither, and the two sources that omit it each
                    # have exactly one neither-bit record. Structurally there is nowhere else to look:
                    # these are `end = 4` with costly class bits 16 and 27, so every header word is
                    # accounted for. 167 records, 18 declared outputs; rendering them needs the
                    # ENGINE's default, which belongs in `assume.QUESTIONS`.
                    raise Unsupported("sharpen intensity: neither class bit 12 (baked) nor "
                                      "13 (program) is set, so the source omitted it and "
                                      "the engine's default applies")
                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                N = W * H
                src = to_image(sbsruntime.image_sampler(outputs[rec.edges[0]])(pos_grid(W, H)),
                               N, H, W)
                blurred = np.zeros_like(src)
                for dy in (-1, 0, 1):
                    row = np.roll(src, dy, axis=0)
                    for dx in (-1, 0, 1):
                        blurred += np.roll(row, dx, axis=1)
                blurred /= 9.0
                outputs[i] = np.clip(src + amount * (src - blurred), 0.0, 1.0)
                if tainted:
                    synthetic.add(i)

            elif rec.filter_name == "fxmaps":
                # `fxmaps` is a pattern GENERATOR, not a filter over an input, so it is the one
                # unimplemented branch that unblocks graphs on its own: 13 of the corpus's 34
                # one-root-cause-away graphs need only this. What it produces is honest but
                # incomplete -- see tools/fxrender.py, which records that 96% of records render
                # flat because `patternsize`'s coordinate space is not established. Kept behind
                # the same `Unsupported` contract as everything else.
                W, H = rec.width, rec.height
                if max_dim:
                    W, H = min(W, max_dim), min(H, max_dim)
                # SAMPLERS IS GLOBAL AND NOTHING CLEARS IT, so an FX program that samples index 2
                # may silently read whatever image the LAST record to touch index 2 left behind --
                # a wrong image rather than a refusal, invisible to every coverage metric. 343
                # records' FX programs carry a samplelum/samplecol, and the indices they name are
                # small and edge-slot-shaped. (Read token 1 of the instruction, not token 0 --
                # token 0 is the coordinate OPERAND, and reading it gives hundreds of distinct
                # "indices" reaching 2009. See disasm.IMM.)
                #
                # So: empty SAMPLERS for the duration, install this record's own edges best-effort,
                # restore afterwards. Best-effort rather than the pixelprocessor branch's raise --
                # most FX-Maps never sample their edges, and demanding them first turns records
                # that render today into cascade failures.
                saved_samplers = dict(sbsruntime.SAMPLERS)
                sbsruntime.SAMPLERS.clear()
                try:
                    own_slots = set()
                    for slot_i, edge_rec in enumerate(rec.edges or ()):
                        if edge_rec in outputs:
                            sbsruntime.SAMPLERS[slot_i] = sbsruntime.image_sampler(
                                outputs[edge_rec])
                            own_slots.add(slot_i)
                    # A record with no edge in a slot may still reach an image through the graph's
                    # declared image inputs -- see `sampler_bindings`. Edge slots WIN where both
                    # exist: an edge is this record's own wiring, and letting the fallback overwrite
                    # it would substitute a guess for a fact.
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
                        # A GENERATOR THAT FAILED WITH AN INPUT MISSING IS A CONSEQUENCE, and the test is
                        # structural rather than a read of the message: the edges are installed
                        # best-effort above, so an absent edge plus a failed walk means downstream. String
                        # matching would have to know a second module's prose, and it was exactly that
                        # coupling that made `WoodSubstance005`'s record 194 look like the blocker.
                        if any(e2 is not None and e2 not in outputs
                               for e2 in (rec.edges or ())):
                            raise cascade("fxmaps: %s" % e) from e
                        raise Unsupported("fxmaps: %s" % e) from e
                    if not pats:
                        # The walk completed and a gate closed the branch -- see fxrender.emissions. The
                        # map's output is its background, which is what splat produces from an empty
                        # pattern list, so fall through rather than refuse. An empty walk that no gate
                        # explains still raises out of emissions() and never reaches here.
                        pass
                    # `imageindex` names an input to use AS the pattern, so hand the branch's
                    # already-computed edge images to the splatter keyed by edge SLOT.
                    # `fxrender.image_for` returns None for a slot we do not supply and draws the
                    # generated profile instead, so an unmappable index degrades to the old behaviour
                    # rather than sampling whatever image is nearest. NOT a general edge-list index:
                    # over 80 files the 133 records whose patterns all index 0 have SIX edges and the
                    # 27 using index 1 have THREE, so it addresses some unestablished subset.
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
                # A distance transform. `tools/distance.py` carries the decode: units are pixels at
                # a 256 reference (every declared constant lies in [0, 256], 11 of 19 exactly 256),
                # and the kernel is verified by controlled input -- a single lit pixel gives zero at
                # radius 15.81 and 39.96 for R = 16 and 40, exactly 0.500 at R/2.
                #
                # The PARAMETER is not established and is not guessed: `distance_param` takes a
                # width-1 program result if there is exactly one, else a non-denormal baked float
                # marked LOW CONFIDENCE, else raises.
                if len(rec.edges) < 1 or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
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
                # Radius scales with resolution: 0.14 px at 256 is 0.035 at 64 and the filter
                # becomes a no-op that reads as a dead parameter. See the module docstring.
                field = distance.distance_field(mask, distance.scale_radius(val, W))
                if assume.assumed('distance.invert', False):
                    field = 1.0 - field
                    assume.note(i)
                # THE SECOND EDGE, WHICH THIS FILTER HAS BEEN THROWING AWAY. See
                # `assume.QUESTIONS['distance.propagate']`: across 444 files every one of the
                # 1,693 two-edge `distance` records has a greyscale edge 0, and the record's own
                # colour bit equals edge 1's in all 1,693. A scalar field cannot satisfy a
                # colour header, so under 'field' the 122 colour ones refuse -- correctly. Under
                # 'nearest' the payload is edge 1's value at the closest lit mask pixel, faded
                # by the same field.
                _prop = assume.assumed('distance.propagate', 'field')
                _payload = next((e for k, e in enumerate(rec.edges)
                                 if k != mask_edge and e in outputs), None)
                if _prop == 'nearest' and _payload is not None:
                    _src_img = sbsruntime.image_sampler(outputs[_payload])(
                        pos_grid(W, H)).reshape(H, W, -1)
                    _vals = distance.propagate(
                        mask, distance.scale_radius(val, W), _src_img)
                    outputs[i] = to_image((_vals * field[:, :, None]).reshape(H * W, -1),
                                          W * H, H, W)
                    assume.note(i)
                    if _payload in synthetic:
                        synthetic.add(i)
                else:
                    outputs[i] = to_image(field.reshape(-1, 1), W * H, H, W)
                if rec.edges[mask_edge] in synthetic:
                    synthetic.add(i)

            elif rec.filter_name == "hsl":
                # THE PARAMETERS ARE STATED, and which bit names which is settled by containment
                # against a paired source. The class word is a presence mask: one float32 field per
                # set bit, at words[3..] in ASCENDING BIT ORDER -- cls bit 8 hue, 10 saturation,
                # 12 luminosity. SBRustyTreadPlate declares six hsl nodes and all six match a
                # record exactly, across the one-, two- and three-parameter shapes. The ordering is
                # the part only containment could give: the source lists `luminosity` before
                # `saturation` on several nodes and the record always stores saturation first.
                #
                # WHAT IS DECODED AND WHAT IS MODELLED, kept apart. The parameters and positions
                # are read from the file. The transform is a reading: hue as a shift in turns,
                # saturation and luminosity as offsets, each neutral at 0.5 -- checkable, since a
                # record with every parameter at 0.5 must be the identity.
                if not rec.edges or rec.edges[0] not in outputs:
                    raise cascade("edge has no output yet")
                # WHERE THE BLOCK STARTS is not a constant, and reading it as one cost every hsl
                # record whose class word omits the inherited parameter. The fields follow the
                # INHERITED block that `walk.py`'s `_CLS` describes: class bits below 8 contribute
                # their slots first. `SBRustyTreadPlate` -- the specimen that fixed the bit->name
                # mapping -- has bit 0 SET, so its parameters really do start at word 3, and the
                # fixed 3 was right for it and read as a general law. `PaymentCardSubstance001` has
                # bit 0 clear and hsl records three words long, so all six refused and took 120
                # cascaded records with them, including five of the file's six outputs.
                #
                # Over 80 files, on hsl records that set at least one parameter bit:
                #
                #     start = 2 + inherited slots   59 of 59 decode inside [0, 1]
                #                                   51 of 59 within 0.25 of neutral 0.5
                #     CONTROL, the fixed 3          40 in range, 19 records too short to have one
                #
                # A wrong offset does not land on a neutral-looking distribution.
                src = np.asarray(outputs[rec.edges[0]], dtype=np.float32)
                # ...AND THE WALK MUST COUNT EVERY COST-BEARING BIT, not just the inherited two and
                # the three named here. The cost model fits hsl at const 2 with one word per set
                # cls bit for bits 0, 7, 8, 9, 10, 11, 12 and 13 -- 74 keys, 100.000% exact -- so
                # bits 9, 11 and 13 occupy slots too, set on 258, 246 and 263 of the 747 records.
                # Advancing one slot per NAMED bit skips them. It is 16 reads of 593, and every one
                # is decisive: the sequential walk reads exactly 0.0000 in 16 of 16 where the
                # popcount walk reads ordinary parameters. Sixteen exact zeros is the wrong word
                # read sixteen times.
                #
                # THE SLOT COMES FROM THE WALK, not from a slot formula. This branch used to
                # compute it as `2 + (count of set COST_BITS below this bit)`, a `base + class
                # bits` rule reimplementing the walk's own primitive with a hardcoded bit list.
                # Nothing in the file stores a slot number, so a formula for one is a fit until
                # it agrees with the structural pass -- and over 437 files and all 747 hsl
                # records it does, exactly: walk agrees 593, disagrees 0, silent 0, so the
                # formula was never a second answer and the tuple deletes.
                #
                # THIS DUPLICATES `decompose` AND THE TWO AGREE. Kept as its own walk only because
                # it must name WHICH parameter each slot holds, which `decompose` does not report
                # for a filter with no PARAM_SPEC entry. Containment confirms both, pairing sources
                # that declare a distinctive value against their OWN binaries -- ChesterfieldSofa
                # 866 saturation 0.6500 at slot 3 and luminosity 0.6000 at slot 4, 351 saturation
                # 0.5800 at slot 3, SandyStonePath 1451 saturation 0.5250 at slot 3: 4 of 4, and
                # `decompose` independently allocates cls_slots [2, 3, 4] on record 866.
                #
                # MIND THE BIT FRAME. I published the opposite here in f55ddc8, claiming costs.json
                # charges 0.0 for bits 8-13. The cls table is keyed by WORD-0 bit index and `cls`
                # is `w0 >> 16`, so its keys 8-13 are low-half bits with nothing to do with
                # hue/saturation/luminosity -- those are w0 bits 24, 26 and 28, charged 1.0 word
                # each. Reading a table in the wrong bit frame gave a clean-looking 0-of-4.
                walked = decompose.decompose(rec)
                if walked is None:
                    raise Unsupported("hsl record has no structural decomposition")
                cls_slots = {b - 16: s for b, s, _w in (walked.get('cls_params') or [])
                             if b >= 16}
                vals = {}
                for bit, name in ((8, 'hue'), (10, 'saturation'), (12, 'luminosity')):
                    if not (rec.cls >> bit) & 1:
                        continue
                    sl = cls_slots.get(bit)
                    if sl is None:
                        raise Unsupported("hsl class bit %d set but the walk names no "
                                          "slot for it" % bit)
                    if sl >= len(rec.words):
                        raise Unsupported("hsl mask names slot %d, record has %d"
                                          % (sl, len(rec.words)))
                    f = np.frombuffer(np.array([int(rec.words[sl])],
                                               dtype=np.uint32).tobytes(),
                                      dtype='<f4')[0]
                    if not np.isfinite(f) or abs(f) > 1e3:
                        raise Unsupported("hsl %s slot is not a plausible float" % name)
                    vals[name] = float(f)
                # A PARAMETER CARRIED AS A PROGRAM IS INVISIBLE HERE -- the loop above reads only
                # baked slots named by class bits 8, 10 and 12 -- and 14 of the 41 hsl records in
                # 30 files have no baked bit and one or more filter programs. They render as the
                # identity, AND THAT IS MOSTLY CORRECT: of 43 single-component results, 39 are
                # EXACTLY 0.5, neutral under this branch's `shift = value - 0.5`. Every one is a
                # node left at its defaults, so wiring the programs in would change nothing.
                #
                # The remaining 4 return 0.0. Auras 443 and 425 show a per-channel gain error
                # (slope 0.536 / 0.321 / 0.802 at correlation 0.94), the shape a missed colour
                # adjustment leaves, so all three assignments were tried -- none is uniformly
                # better (`saturation` buys ch2 and loses ch1; `luminosity` takes ch1 correlation
                # from 0.865 to 0.296). And the structure says they have no parameter at all:
                # class 0x0219 sets NONE of the parameter bits.
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
                    # `dd` is the guarded denominator: where d is 0 the pixel is grey, `m` is False
                    # and the sector value is discarded, so the guard only keeps the arithmetic
                    # finite rather than changing any kept result.
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
                    # NOT `i` -- that is the record index this branch writes its output under, and
                    # shadowing it made `outputs[i] = ...` key the dict by an array. Loud only
                    # because the key was unhashable; a scalar would have written the wrong record.
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
                    # A GREYSCALE record has no hue or saturation to move; only the luminosity term
                    # can act, and applying the others would invent a colour the input lacks.
                    out = np.clip(a + l_sh, 0.0, 1.0)
                outputs[i] = out.reshape(src.shape)
                LOW_CONFIDENCE.add(i)
                if rec.edges[0] in synthetic:
                    synthetic.add(i)

            elif rec.filter_name == "dyngradient":
                # `gradient` with the ramp supplied as an IMAGE rather than an embedded table.
                # Handed over by a parallel session with the edge roles established and the
                # sampling formula explicitly not:
                #
                #   edge 0   size EQUALS the record's own size in 373 of 373 (100.0%)
                #   edge 1   aspect 128:1 at p10/p50/p90; 97.9% at least 8x wider than tall;
                #            SHARED, one strip feeding 4, 8 and 16 records -- a palette
                #
                # It needs no parameter located: the filter has no numerics to declare, and 288 of
                # 294 records carry no filter program at all. THE ROW CAVEAT IS CLOSED -- the
                # strips' row-to-row difference is exactly 0.000000, so any row is the same row.
                #
                # ESTABLISHED, by driving both edges through `precomputed` (see
                # test_dyngradient_is_a_ramp_lookup): an identity ramp reproduces the source, a
                # REVERSED ramp gives 1 - source, a step ramp gives exactly two values. The
                # reversed case carries it -- a renderer ignoring the ramp passes the first test
                # and fails that one. STILL A CHOICE: indexing by channel 0 rather than a luminance
                # mix, which coincides for the 292 of 294 greyscale records.
                if len(rec.edges) < 2 or any(e not in outputs for e in rec.edges[:2]):
                    raise cascade("edge has no output yet")
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

            # NON-FINITE IS NOT A RENDER. An output map is 8- or 16-bit integer and has no NaN,
            # so whatever the engine does with a zero divisor it does not emit one; an array
            # carrying NaN is silent garbage that every consumer inherits while still counting
            # as rendered. ChesterfieldSofa record 119 computes v8/v12 with both terms zero and
            # its NaN reached 659 of the 830 records that file rendered, including two declared
            # outputs, none of which reported a failure. Refusing names the root rather than
            # the 659 downstream of it.
            #
            # A RECORD'S CHANNEL COUNT IS IN ITS HEADER, AND THIS RENDERER WAS NOT HONOURING
            # IT. 74 of 16,652 rendered records in 20 files come out some other width -- 64
            # greyscale-with-2-channels (origin: pixelprocessor) and 10 colour-with-3 (a
            # 3-channel PNG) -- and the 2-wide ones are why `blend inputs disagree on channel
            # count` blocks 16 declared outputs. Of the 64, 20 have both components IDENTICAL
            # and 44 are out of range rather than two candidate greys: Travertine 2792 and
            # siblings mean 1.9217 against 1.0000, and 0.9217 is `rand(1.0)`. Record 301's body
            # is `rand(1.0)`, `+ 1.0`, `vec(that, 1.0, ncomp=2)` -- `ncomp=2` is the
            # instruction's OWN width, on a record whose header says greyscale. So
            # `filter_programs[-1]` selected a program that is not the record's image body, and
            # the right fix is in that selection; the obvious selector, matching declared width
            # to the header, is unique in only 21 of 325 cases. So: conform where there is
            # nothing to choose, refuse where there is. 3 channels for a colour record is
            # unambiguous -- RGB from a PNG with no alpha.
            if i in outputs:
                arr = np.asarray(outputs[i])
                want = 4 if rec.colour else 1
                if arr.ndim == 3 and arr.shape[-1] != want:
                    if not rec.colour:
                        spread = float(np.max(np.abs(arr - arr[..., :1]))) if arr.size else 0.0
                        if spread > 1e-9:
                            del outputs[i]
                            synthetic.discard(i)
                            LOW_CONFIDENCE.discard(i)
                            raise Unsupported(
                                "greyscale record produced %d channels that disagree by "
                                "%.4g -- the program evaluated is not this record's image "
                                "program" % (arr.shape[-1], spread))
                        outputs[i] = arr[..., :1]
                    elif arr.shape[-1] == 3:
                        outputs[i] = np.concatenate(
                            [arr, np.ones(arr.shape[:2] + (1,), dtype=arr.dtype)], axis=-1)
                    else:
                        del outputs[i]
                        synthetic.discard(i)
                        LOW_CONFIDENCE.discard(i)
                        raise Unsupported("colour record produced %d channels, not 4"
                                          % arr.shape[-1])
                    arr = np.asarray(outputs[i])
                if arr.size and not np.all(np.isfinite(arr)):
                    # MOSTLY AN ARTEFACT OF `max_dim`, NOT A PROPERTY OF THE FILE. The recurring
                    # producer is an auto-levels remap `(lum - min) / (max - min)` over a source that
                    # is constant only because the raster is too coarse. Traced on Bricks record 326:
                    # its input 325 is a max-reduction returning [0, 0, 1, 1], so the range is
                    # zero-wide, because ITS input 318 is a `distance` whose radius is 2.56 px at the
                    # format's 256 reference -- 0.64 px at max_dim 64, so the field rounds away.
                    #
                    #   max_dim  64    12 non-finite records   13,747 records rendered
                    #   max_dim 128     2 non-finite records   24,115 records rendered
                    #
                    # `output_census` runs at 64 while `refcompare.RENDER_DIM` is 128, so the blocker
                    # list has been counting at a resolution the scorer does not use. Ten of the twelve
                    # are not decode work, which also mis-poses `nonfinite.fill` for them: filling with
                    # 0.0, 0.5 or 1.0 would paint over a raster that is simply too coarse. Resolve the
                    # arm on the two survivors or not at all. UNDER AN OPEN SCOPE, write the value.
                    _fill = assume.assumed('nonfinite.fill')
                    if _fill is not None:
                        outputs[i] = np.where(np.isfinite(arr), arr,
                                              np.float32(_fill)).astype(arr.dtype)
                        LOW_CONFIDENCE.add(i)
                        assume.note(i)
                        continue
                    del outputs[i]
                    synthetic.discard(i)
                    LOW_CONFIDENCE.discard(i)
                    raise Unsupported("produced non-finite values (%.1f%% of samples)"
                                      % (100.0 * float(np.mean(~np.isfinite(arr)))))
        except Unsupported as e:
            failures[i] = str(e)
            if getattr(e, 'cascade', False):
                CASCADED.add(i)
            if verbose:
                print("rec%d (%s): SKIP - %s" % (i, rec.filter_name, e))
        except Exception as e:
            failures[i] = "%s: %s" % (type(e).__name__, e)
            if verbose:
                print("rec%d (%s): ERROR - %s: %s" % (i, rec.filter_name, type(e).__name__, e))

        if stop_after is not None and i >= stop_after:
            # A caller that wants ONE record's output does not need the rest of the file.
            # Edges point backward and evaluation is a single forward pass with no state a
            # later record could feed back, so stopping here returns exactly what a full
            # render would have put in outputs[stop_after]. This is an early stop, NOT a
            # dependency-cone prune: pruning by Record.edges would be unsafe, because the
            # manifest oracle measured that closure as a strict SUBSET of the real
            # dependencies (513 paths missed, 0 over-claimed) -- samplers reach images
            # without an edge.
            break

    # CLAMP AT THE WRITE, NOT IN THE FILTER THAT OVERSHOT. `levels` leaves [0, 1] by
    # construction where an author set leveloutlow/levelouthigh outside the unit range,
    # and a few pixelprocessor and blend finals land slightly past it. The values are
    # NOT a misdecode: corpus-wide 105 of 51,822 baked levelouthigh values fall outside
    # [0, 1], running 1.01 to 1.34 in a tight contiguous band with no garbage and no
    # NaNs -- authored data being read correctly.
    #
    # SO THE CLAMP BELONGS HERE. Of those 105 records only 3 are declared outputs; 102
    # are INTERMEDIATES, and an intermediate at 1.31 feeding a multiply or a blend is
    # headroom the engine may legitimately consume. (`apply_blend`'s docstring asserts
    # `levels` already clamps, but that assertion IS the claim under test.) All three
    # out-of-range outputs declare fmt 28, which cannot hold 1.31 whatever happened
    # upstream. VALUE outputs are skipped: their `fmt` is a tuple and they carry
    # scalars, not pixels.
    for _uid, _fmt, _gray, _rec in asm.outputs():
        if isinstance(_fmt, tuple) or _rec not in outputs:
            continue
        _arr = outputs[_rec]
        if _arr.min() < 0.0 or _arr.max() > 1.0:
            outputs[_rec] = np.clip(_arr, 0.0, 1.0)

    return outputs, failures, synthetic
