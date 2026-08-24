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
    cols = []
    for p in parts:
        a = np.asarray(p)
        cols.append(a[:, None] if a.ndim == 1 else a)
    return np.concatenate(cols, axis=-1)


def swizzle(value, indices):
    a = np.asarray(value)
    if a.ndim == 1:
        a = a[:, None]
    out = a[:, indices]
    return out[:, 0] if len(indices) == 1 else out


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
