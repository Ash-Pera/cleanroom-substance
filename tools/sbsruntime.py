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
CONTEXT = {"width": 256, "height": 256, "number": 0.0, "time": 0.0}
_unresolved = set()


def set_context(width=None, height=None, number=None, time=None):
    """Set the resolution, FX-Map pattern index and clock programs evaluate at."""
    for key, value in (("width", width), ("height", height),
                       ("number", number), ("time", time)):
        if value is not None:
            CONTEXT[key] = value


def sysvar(vid, ncomp, n=1):
    width, height = CONTEXT["width"], CONTEXT["height"]
    if vid == 8:                                    # $pos
        return np.zeros((n, ncomp)) if ncomp > 1 else np.zeros(n)
    if vid == 1:                                    # $size, in pixels
        return np.tile([float(width), float(height)][:ncomp], (n, 1)) if ncomp > 1 \
            else np.full(n, float(width))
    if vid == 3:                                    # $sizelog2
        logs = [np.log2(width), np.log2(height)][:ncomp]
        return np.tile(logs, (n, 1)) if ncomp > 1 else np.full(n, logs[0])
    if vid == 10:                                   # $number
        return np.full(n, float(CONTEXT["number"]))
    if vid == 0:                                    # $time
        return np.full(n, float(CONTEXT["time"]))
    _unresolved.add(("sysvar", vid))
    return np.zeros((n, ncomp)) if ncomp > 1 else np.zeros(n)


def unresolved():
    return sorted(_unresolved)


def vec(*parts):
    """Concatenate components into one (N, k) array.

    Scalars have to be promoted, not just 1-d arrays. The Python backend emits a
    single-valued `const` as a plain float -- `0.5`, not an array -- so `vec(0.5, x)`
    arrives with a 0-dimensional operand, which `np.concatenate` refuses. That accounted
    for 28,136 of the runtime failures in an execution sweep of the corpus.
    """
    cols = []
    for p in parts:
        a = np.asarray(p, dtype=np.float32) if np.isscalar(p) else np.asarray(p)
        if a.ndim == 0:
            a = a.reshape(1, 1)
        elif a.ndim == 1:
            a = a[:, None]
        cols.append(a)
    n = max(c.shape[0] for c in cols)
    cols = [np.repeat(c, n, axis=0) if c.shape[0] == 1 and n > 1 else c for c in cols]
    return np.concatenate(cols, axis=-1)


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
    a = np.asarray(value)
    if a.ndim == 0:
        a = a.reshape(1, 1)
    elif a.ndim == 1:
        a = a[:, None]
    w = a.shape[1] - 1
    idx = [i if i <= w else w for i in indices]
    out = a[:, idx]
    return out[:, 0] if len(idx) == 1 else out


def select(cond, a, b):
    """select(c, a, b) is `c ? a : b`."""
    c = np.asarray(cond)
    a, b = np.asarray(a), np.asarray(b)
    if a.ndim > c.ndim:
        c = c[:, None]
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
    x = np.atleast_2d(np.asarray(a, dtype=np.float32))
    y = np.atleast_2d(np.asarray(b, dtype=np.float32))
    return np.sum(x * y, axis=-1, keepdims=True)


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
    a = np.atleast_2d(np.asarray(v, dtype=np.float32))
    return np.arctan2(a[:, 1], a[:, 0]).reshape(-1, 1)


def cartesian(r, theta):
    """Polar to xy."""
    return vec(r * np.cos(theta), r * np.sin(theta))


def rand(seed):
    """Deterministic hash-style noise in [0, 1)."""
    x = np.asarray(seed, dtype=np.float64)
    return np.modf(np.sin(x * 12.9898) * 43758.5453)[0] % 1.0


#: Samplers are installed by the caller: index -> function(pos) -> value.
SAMPLERS = {}


def sample_lum(index, pos):
    return SAMPLERS[index](pos)


def sample_col(index, pos):
    return SAMPLERS[index](pos)


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
