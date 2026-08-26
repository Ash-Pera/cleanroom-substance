"""Runtime for transpiled .sbsasm programs, vectorised over numpy.

A value with one component is an array of shape (N,); a k-component value is (N, k).
Everything is evaluated for N sample points at once, so a transpiled program can be run
over a grid and compared against a reference implementation.
"""
import numpy as np

#: System variable ids, read off how programs use them.
#:
#:   8  $pos        the sampling coordinate: feeds samplecol/samplelum in 34,180 of its
#:                  86,627 uses and nothing else consumes it that way.
#:   1  $size       the output size in pixels. `1 / $size` -- texel size -- is the
#:                  dominant idiom at 21,369 uses, with `256 / $size` and `2048 / $size`
#:                  as resolution-relative scales. Never passed to exp2.
#:   3  $sizelog2   log2 of the size. Its dominant consumer is subtraction against a
#:                  swizzle of ITSELF (54,412 of 73,398), giving `sv.yx - sv.xy`, then
#:                  exp2 -- the aspect ratio computed in log space. It is never exp2'd
#:                  directly (0 instances); only a difference of its components is.
#:   10 $number     the pattern index inside an FX-Map, fxmaps records only. Its programs
#:                  compute `v/N - 0.5 + 1/(2N)` = `(v + 0.5)/N - 0.5`, the centre of
#:                  cell v in an N-cell grid spanning [-0.5, 0.5]; N is 32 and 128 in the
#:                  specimens read.
#:   0  $time       proved, not inferred: `time_var_test`'s paired .sbs source computes
#:                  `($time + #time) * #timescale` in a valueprocessor function graph,
#:                  and the compiled program is that expression uid for uid against the
#:                  manifest's own input names. See FORMAT-NOTES.md, "#0 is $time".
#:
#: Whether $size is the node's own output size or its input's is not established -- no
#: program read so far distinguishes them.
SYSVARS = {0: "$time", 1: "$size", 3: "$sizelog2", 8: "$pos", 10: "$number"}

#: Evaluation context. `sysvar` needs the node's resolution to answer at all (and $time
#: its clock), so a caller that has the record/timeline can supply it.
CONTEXT = {"width": 256, "height": 256, "number": 0.0, "time": 0.0, "pos": None}
_unresolved = set()


def set_context(width=None, height=None, number=None, time=None, pos=None):
    """Set the resolution, FX-Map pattern index, clock, and per-sample position.

    `pos` is an (N, 2) array, x then y, one row per sample the program will be evaluated
    at -- pixel centers by Substance's own convention, `(col + 0.5) / width`. Left at its
    default of None, `$pos` reads back as zeros, exactly as before this existed: nothing
    that does not pass `pos` explicitly changes behavior.
    """
    for key, value in (("width", width), ("height", height),
                       ("number", number), ("time", time), ("pos", pos)):
        if value is not None:
            CONTEXT[key] = value


def sysvar(vid, ncomp, n=1):
    width, height = CONTEXT["width"], CONTEXT["height"]
    if vid == 8:                                    # $pos
        pos = CONTEXT["pos"]
        if pos is not None:
            return np.asarray(pos)[:, :ncomp] if ncomp > 1 else np.asarray(pos)[:, 0]
        return np.zeros((n, ncomp)) if ncomp > 1 else np.zeros(n)
    if vid == 1:                                    # $size, in pixels
        return np.tile([float(width), float(height)][:ncomp], (n, 1)) if ncomp > 1 \
            else np.full(n, float(width))
    if vid == 3:                                    # $sizelog2
        logs = [np.log2(width), np.log2(height)][:ncomp]
        return np.tile(logs, (n, 1)) if ncomp > 1 else np.full(n, logs[0])
    if vid == 10:                                   # $number
        # $number MAY BE A VECTOR. An FX-Map's emission loop can evaluate one parameter
        # program for every pattern at once when nothing in the chain below it mutates the
        # slot frame -- see fxrender's batched emission -- and then the pattern index is
        # one value per row rather than one value. Everything downstream is already
        # row-wise, so an (m,) here broadcasts through the whole program unchanged.
        num = CONTEXT["number"]
        if isinstance(num, np.ndarray) and num.ndim:
            # ONE COMPONENT, WHATEVER `ncomp` SAYS -- the scalar branch below ignores
            # ncomp too, so `$number` has always been a single component. Returning
            # (m, ncomp) instead silently gave a two-component $number and moved every
            # frameoffset this batching was meant to leave untouched.
            #
            # AND AS A COLUMN, not the 1-D the scalar branch returns. A program mixes
            # $number with values built from graph inputs, which are (1, k) 2-D, and
            # numpy broadcasts (1, 1) against a 1-D (m,) into (1, m) -- the batch laid out
            # along the COMPONENT axis, which then reads back as pattern 0 for every
            # pattern. (m, 1) broadcasts to (m, 1), which is the row-per-pattern shape the
            # rest of this module is written in.
            return num.astype(np.float64, copy=False).reshape(-1, 1)
        return np.full(n, float(num))
    if vid == 0:                                    # $time
        return np.full(n, float(CONTEXT["time"]))
    # Named from SYSVARS, which is the catalogue this function's numeric branches are
    # written against. It had no reader at all, so the names above and the ids below
    # could drift apart with nothing to notice.
    _unresolved.add(("sysvar", vid, SYSVARS.get(vid, "unknown")))
    return np.zeros((n, ncomp)) if ncomp > 1 else np.zeros(n)


def unresolved():
    """Every system variable a program asked for that this runtime cannot answer.

    `(kind, id, name)` per entry, the name from `SYSVARS`. Worth calling after a sweep:
    a zero here and a wrong image both look like "it ran".
    """
    return sorted(_unresolved)


def _col(x):
    """As an (N, components) array, the shape every runtime helper works in.

    A 1-dimensional array is N SAMPLES of one component, `(N, 1)` - not one sample of N
    components. `np.atleast_2d` makes the opposite choice, and using it here made
    `select` read a 200,000-sample ramp as a 200,000-component value and try to repeat a
    condition to (200000, 200000). The original `swizzle` had it right with `a[:, None]`
    and the helpers added later did not.
    """
    a = np.asarray(x)
    if a.ndim == 0:
        return a.reshape(1, 1)
    if a.ndim == 1:
        return a[:, None]
    return a


def vec(*parts, ncomp=None):
    """Concatenate components into one (N, k) array.

    Scalars have to be promoted, not just 1-d arrays. The Python backend emits a
    single-valued `const` as a plain float -- `0.5`, not an array -- so `vec(0.5, x)`
    arrives with a 0-dimensional operand, which `np.concatenate` refuses. That accounted
    for 28,136 of the runtime failures in an execution sweep of the corpus.

    `ncomp` is the constructing instruction's own declared result width (0x0D/0x0F carry
    one, like every opcode). It is authoritative and concatenation alone can overshoot
    it: a corpus census found the two operands of every one of 3,248,836 `add`
    instructions declare the SAME width, with zero exceptions, so the compiler statically
    guarantees an add's inputs match -- but nothing at runtime enforced it, because this
    function used to trust concatenation's width unconditionally. Traced in
    ChewingGumSubstance001's program at offset 9354228: a scalar accumulator (slot 48,
    declared 1-wide at its `get` and at all 26 `set` sites) drifted to 4 components wide,
    and a downstream vec meant to build a declared-4-wide result concatenated a piece
    built from it into 7 columns instead, which then failed to broadcast against the
    other, correctly-4-wide branch of the `select` both were headed for. Truncating to
    the declared width here fixed it. Only truncation is implemented -- there is no
    observed case of concatenation falling SHORT of the declared width, so that case
    raises rather than guess how to pad it.
    """
    cols = []
    for p in parts:
        cols.append(_col(p))
    n = max(c.shape[0] for c in cols)
    cols = [np.repeat(c, n, axis=0) if c.shape[0] == 1 and n > 1 else c for c in cols]
    out = np.concatenate(cols, axis=-1)
    if ncomp is not None and out.shape[1] != ncomp:
        if out.shape[1] < ncomp:
            raise ValueError("vec: concatenation gave %d components, declared %d -- "
                              "no observed case to model padding on" % (out.shape[1], ncomp))
        out = out[:, :ncomp]
    return out


def swizzle(value, indices):
    """Select components by index, clamping an index past the operand's width.

    62 of 210,228 swizzles in the corpus name a component their operand does not have -
    47 are a 1-wide operand read as `(0, 1)` and 15 a 2-wide operand read as `(0, 3)`.
    They are real programs, so the engine does something with them rather than failing.

    What it does is not established, but it does not matter for any of them: the two
    candidate rules - clamp the index to the last component, or broadcast the last
    component outward - **agree on every one of the 62**. `[x]` read as `(0,1)` gives
    `[x,x]` either way, and `[x,y]` read as `(0,3)` gives `[x,y]`. Clamping is chosen
    because it is the one that needs no reshaping.
    """
    a = _col(value)
    w = a.shape[1] - 1
    idx = [i if i <= w else w for i in indices]
    # `a[:, idx]` is already (N, len(idx)) for any idx, single component included --
    # collapsing that to 1-D here (a prior version did `out[:, 0]`) broke the invariant
    # every other helper in this module relies on. `lerp` does raw `a + (b - a) * t`
    # arithmetic with no `_col()` normalization of its own, so a 1-D (N,) swizzle result
    # combined with a proper (N, 1) operand silently broadcast into an (N, N) outer
    # product instead of raising -- found tracing a `ValueError: operands could not be
    # broadcast together with shapes (4096,2) (4096,4097)` in ChewingGumSubstance001's
    # program at offset 9354228 (`v120 = swizzle(v119, [2])` feeding `lerp(1.0, v120,
    # slots[18])`). Reproduced in isolation with N=4096 and N=1000, both times giving
    # exactly (N, N+1) via a downstream `vec(v131, 1.0)` concatenating the stray (N, N)
    # array with a proper (N, 1) column. See FORMAT-NOTES.md.
    return a[:, idx]


def select(cond, a, b):
    """`c ? a : b`, with the condition broadcast to the branches' width.

    The two branches always have the SAME width - 89,080 of 89,080 selects in the corpus -
    so the result's width is theirs. The condition's is not: it is narrower in 62.4% of
    them, and its declared width is 2 in every single one, whatever the branches are:

        cond 2, branches 4     54,013        cond 2, branches 1     16,454
        cond 2, branches 2     17,030        cond 2, branches 3      1,583

    A bool's width field does not track the value it selects, so the condition is taken
    one column wide and repeated. The previous version did `c[:, None]` when `a.ndim >
    c.ndim`, which compares dimensions rather than widths and raises `IndexError` on a
    0-dimensional condition - 44 of the 66 remaining execution failures.
    """
    a, b, c = _col(a), _col(b), _col(cond)
    w = max(a.shape[1], b.shape[1])
    if a.shape[1] < w:
        a = np.repeat(a[:, :1], w, axis=1)
    if b.shape[1] < w:
        b = np.repeat(b[:, :1], w, axis=1)
    if c.shape[1] != w:
        c = np.repeat(c[:, :1], w, axis=1)
    return np.where(c, a, b)


def sbs_mod(a, b):
    return np.mod(a, b)


def lerp(a, b, t):
    return a + (b - a) * t


def dot(a, b):
    """Row-wise dot product, one value per row.

    `np.dot` is a matrix product and raises on two (N, k) operands -- 330 runtime
    failures in the corpus sweep. This ISA's `dot` pairs components within a row.
    """
    x, y = _col(a).astype(np.float32), _col(b).astype(np.float32)
    # Operands are the same width in 2,511 of 2,736 dots; the other 225 are all (2, 3).
    # Two of the three candidate rules agree there and one does not: truncating to the
    # common width and zero-padding the narrower give the same number, because a zero term
    # adds nothing, while repeating the narrower operand's first component does not. The
    # pair that agree is taken.
    w = min(x.shape[1], y.shape[1])
    return np.sum(x[:, :w] * y[:, :w], axis=-1, keepdims=True)


def cvt(x, to_int):
    """`0x11`, type conversion. A numpy cast, not Python's `float()`/`int()`.

    The transpiler emitted `float(v)` and `int(v)`, which raise
    `TypeError: only length-1 arrays can be converted to Python scalars` on every
    multi-element operand -- 27,354 runtime failures in the corpus sweep.
    """
    a = np.asarray(x)
    return a.astype(np.int32) if to_int else a.astype(np.float32)


def atan2(v):
    """The polar angle of a 2-vector, in radians.

    `0x2D` takes ONE operand and that operand has two components, in 3,013 of 3,013
    instances corpus-wide -- it is not numpy's two-argument `arctan2`, which is what it
    was transpiled to, and which raised `TypeError` on every one of them.

    Component order is y then x: recovering `directionalwarp`'s baked warp angles as
    `atan2(c[1], c[0]) / 2*pi` yields clean fractions of a turn -- 45, 90, 180, 22.5
    degrees -- and the other order does not. See FORMAT-NOTES.md.
    """
    a = _col(v).astype(np.float32)
    if a.shape[1] < 2:
        a = np.repeat(a, 2, axis=1)
    return np.arctan2(a[:, 1], a[:, 0]).reshape(-1, 1)


def cartesian(r, theta):
    """Polar to xy."""
    return vec(r * np.cos(theta), r * np.sin(theta))



def clamp(value, ncomp):
    """Truncate a value to the component width its instruction declared.

    Every instruction carries a declared result width in its size field, and a corpus
    census found the two operands of all 3,248,836 `add` instructions declare the SAME
    width with zero exceptions -- so the compiler guarantees operands match and any
    mismatch at runtime is drift this evaluator introduced, not something the format
    contains.

    `vec` already truncated its own result for exactly this reason. Doing it for every
    instruction stops drift at the point it appears rather than at the next `vec`, which
    is what left plain `+` and `*` failing to broadcast: 17 of the 22 remaining runtime
    failures were a binary operation between operands of different widths.

    Only truncation, never padding -- a value narrower than declared is a different
    problem and `vec` raises on it rather than guessing.
    """
    if ncomp is None:
        return value
    arr = np.asarray(value)
    if arr.ndim < 2 or arr.shape[-1] <= ncomp:
        return value
    return arr[..., :ncomp]

def rand(limit):
    """A random value in [0, `limit`) -- the argument is the RANGE, not a seed.

    THE ARGUMENT IS A RANGE, and the corpus says so plainly. Over 19,210 `rand` calls in
    25 files, the constants passed to it are:

        1.0 x6470   2.0 x4917   0.0 x1207   0.0625 x1012   6.28 x979   0.125 x696
        0.015625 x544   0.022 x544   360.0 x389   6.283185 x305   4.0 x216

    `6.28` and `6.283185` are a full turn in radians, and 154 of those calls feed `np.cos`
    and 154 feed `np.sin` -- a random ANGLE. `360.0` is the same thing in degrees.
    `rand(0.0)` appears 1,207 times, which under this reading is an author switching a
    jitter off and under a seed reading is a seed of zero, which means nothing. Read as
    seeds, `cos(rand(2*pi))` is one fixed number rather than a direction, and 6.28, 360
    and 0.0625 are arbitrary.

    It had been returning [0, 1) whatever it was given, which collapses every one of those
    to the same narrow band. In CarpetSubstance001 the effect is visible: the emitted
    patterns of record 377 all carry `imageindex` 8, because the program computes
    `int(rand(6.0)) + 8` to choose one of six images and `rand(6.0)` was 0.626 -- so the
    choice was never made, 262,144 times.

    AND IT VARIES WITH `$number`, which is what makes an FX-Map a scatter rather than one
    stamp repeated. A pure function of the argument gives every emitted pattern the same
    draw: the same angle out of `rand(6.28)`, the same jitter, the same image index. In
    CarpetSubstance001 that is 262,144 tufts at one position with one rotation, and the
    file renders flat -- record 0 comes out a uniform 0.9217, which is exactly the old
    `rand(1.0)`. 30 of the 84 records that introduce flatness there are FX-Maps.

    `$number` is the pattern index, already set per emission (and a whole column of them
    under batched emission, which this follows: the hash is elementwise, so m patterns get
    m draws in one evaluation). Where nothing sets it -- a `pixelprocessor`, a filter
    parameter program -- it is 0 and the result is what it always was, so this reaches the
    FX-Map case and leaves the rest alone.

    WHAT IS MODELLED AND WHAT IS READ, kept apart. That the argument is a range is read off
    the corpus. That the draw varies per pattern is a reading of what an FX-Map is for; the
    hash itself is arbitrary and nothing in the file constrains it. Two calls with the same
    argument in the same emission still collide, which the engine would not do.
    """
    x = np.asarray(limit, dtype=np.float64)
    num = CONTEXT["number"]
    if isinstance(num, np.ndarray) and num.ndim:
        n = num.astype(np.float64, copy=False).reshape(-1, 1)
    else:
        n = float(num)
    h = np.modf(np.sin(x * 12.9898 + n * 78.233) * 43758.5453)[0] % 1.0
    return x * h


#: Samplers are installed by the caller: index -> function(pos) -> value.
SAMPLERS = {}


class MissingSampler(KeyError):
    """No sampler installed for an input index a program samples.

    A distinct type because `SAMPLERS` and a program's `slots` are BOTH dicts keyed by
    small integers, so a bare `KeyError(0)` from either is indistinguishable. render.py
    read every such KeyError as "slot 0 read but never set" and reported missing image
    inputs as missing slot state -- which sent a whole investigation after a
    cross-record slot frame that did not exist. On `ie_curve` the mistake was most of
    the population: wiring the samplers took its records' own programs from 235 of 491
    evaluating to 441, and its FX entry programs from 45 of 235 to 195.
    """


def _sampler(index):
    try:
        return SAMPLERS[index]
    except KeyError:
        raise MissingSampler(
            "no sampler installed for input %r (the record's edge is unwired, which is "
            "NOT a missing slot)" % (index,)) from None


def sample_lum(index, pos):
    return _sampler(index)(pos)


def sample_col(index, pos):
    return _sampler(index)(pos)


def image_sampler(image):
    """Wrap an (H, W, C) array as a `pos -> value` function for `SAMPLERS`.

    Bilinear, wrap-tiled -- Substance textures are addressed as tileable by default, and
    a warp-style filter's computed position can legitimately land outside [0, 1] (see
    e.g. a log-polar remap's radius term). `pos` is (N, 2), x then y, pixel centers at
    (col + 0.5) / width, matching `set_context`'s own `pos` convention.
    """
    H, W = image.shape[:2]

    def sampler(pos):
        pos = np.asarray(pos)
        u = pos[:, 0] * W - 0.5
        v = pos[:, 1] * H - 0.5
        u0 = np.floor(u).astype(np.int64)
        v0 = np.floor(v).astype(np.int64)
        fu = (u - u0)[:, None]
        fv = (v - v0)[:, None]
        u0m, u1m = u0 % W, (u0 + 1) % W
        v0m, v1m = v0 % H, (v0 + 1) % H
        # Flat gathers, not 2-D fancy indexing: one index array per corner instead of a
        # pair, which numpy turns into a single take rather than a broadcast join.
        #
        # The lerp is also fused -- a + (b - a) * f rather than a * (1 - f) + b * f --
        # which is two array ops per axis instead of three. The two are equal in exact
        # arithmetic and differ by up to 2.95e-08 in float32, about one ulp. That is
        # below any threshold this repository compares renders at (the reference MAEs
        # are quoted to 1e-04), so it is bought deliberately rather than by accident.
        base = image.reshape(-1, image.shape[2]) if image.ndim == 3 else image.reshape(-1)
        r0, r1 = v0m * W, v1m * W
        a0 = base[r0 + u0m]; b0 = base[r0 + u1m]
        a1 = base[r1 + u0m]; b1 = base[r1 + u1m]
        top = a0 + (b0 - a0) * fu
        bot = a1 + (b1 - a1) * fu
        return top + (bot - top) * fv

    return sampler


_CACHE = None


def use_shared_cache(cache=None):
    """Install a dict for `cache_read`/`cache_write`, or `None` to remove it.

    Returns the previous one, so a caller can restore it. With no cache installed both
    halves raise, which is the default and the safe one for a single-program transpile.
    """
    global _CACHE
    prev, _CACHE = _CACHE, ({} if cache is None else cache)
    return prev


class NoSharedCache(NotImplementedError):
    """cache_read/cache_write need cross-record state this transpiler does not model."""


def cache_read(index):
    """The read half of the per-package value cache 0x03/0x06 implement.

    0x06 (cache_write) writes a value once, from a dedicated `pixelprocessor` record that
    is never itself sampled as an image; any record's own program reads it back by index
    instead of recomputing it -- cross-record common-subexpression elimination. See
    FORMAT-NOTES.md, "0x03/0x06 are cross-record common-subexpression elimination".

    The MEANING is established. This function still cannot answer, because a
    single-program transpile has no access to the writer -- the value was computed by a
    different program, possibly in a different record, guaranteed only to appear earlier
    in record order (verified over 7,074 matched writer/reader pairs, zero exceptions).
    Answering needs a caller that transpiles a whole file in record order and threads one
    cache dict through every program's evaluation. Raising here beats guessing zero: a
    silently wrong cached value is exactly the failure mode this project's own tests
    exist to catch.

    A caller that does thread a cache installs one with `use_shared_cache`. Reading an
    index nothing has written still raises: an unwritten index means the evaluation order
    is wrong or the writer was skipped, and both are worth hearing about.
    """
    if _CACHE is None:
        raise NoSharedCache(
            "cache index %r: needs the whole file evaluated in record order with a shared "
            "cache, not a single program" % index)
    if index not in _CACHE:
        raise NoSharedCache("cache index %r read before anything wrote it" % index)
    return _CACHE[index]


def cache_write(value, index):
    """The write half of `cache_read`. See there."""
    if _CACHE is None:
        raise NoSharedCache(
            "cache index %r: needs the whole file evaluated in record order with a shared "
            "cache, not a single program" % index)
    _CACHE[index] = value
    return value
