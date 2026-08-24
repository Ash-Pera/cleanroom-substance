"""Runtime for transpiled .sbsasm programs, vectorised over numpy.

A value with one component is an array of shape (N,); a k-component value is (N, k).
Everything is evaluated for N sample points at once, so a transpiled program can be run
over a grid and compared against a reference implementation.
"""
import numpy as np

#: System variable ids. Only $pos is confirmed; the rest are placeholders so a program
#: that reads one runs rather than failing, and are reported by `unresolved`.
SYSVARS = {8: "$pos"}
_unresolved = set()


def sysvar(vid, ncomp, n=1):
    if vid not in SYSVARS:
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
