#!/usr/bin/env python3
"""Check the corpus against laws its own data must satisfy, with no reference render.

WHY THIS EXISTS. The four-byte bitmap offset was found by looking at a contact sheet and
noticing four tiles were the wrong colour. Nothing in the suite could have caught it: the
wrong decode still had the right dimensions, the right channel count and real spatial
structure, and the reference set that could have scored it produces zero spatially
varying outputs, blocked behind six separate unimplemented things. The bug was visible
for as long as it took someone to look, and invisible to every number.

What made it findable was not the picture, it was that IMAGES OBEY LAWS. A tangent-space
normal map is a unit vector. An RGBA alpha is the flattest channel and sits last. Pixels
are finite. Those hold for every file in the corpus, they need nobody's ground truth, and
a decode that violates one is wrong whatever its coverage number says.

WHAT MAKES A LAW USABLE HERE. Each of these has to be able to FAIL, and has to have
something to fail against, or it is decoration:

  * `alpha_last` and `normal_rotation` are self-controlling -- the readings the law
    rejects are tested by the same measurement that accepts the right one, so a law that
    accepts everything shows up as a flat distribution rather than as a pass.
  * `packing` is here BECAUSE it cannot see a uniform shift. It was briefly mistaken for
    a refutation of the offset fix. It stays as a guard on the shape of any future
    correction, and its docstring says what it cannot do.
  * `grayscale_bit` compares two INDEPENDENT declarations -- the output table's bit and
    the channel count actually produced -- rather than a value against itself. Checking
    that a rendered image has the dimensions the record declares would be tautological,
    since the renderer reshapes to exactly those, so that is not a law and is not here.

Every law reports what it CHECKED as well as what it violated, because a law that
examined nothing must not read as a law that passed.
"""
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import imgstat                                                       # noqa: E402
from sbsasm import Assembly                                          # noqa: E402

#: A rotation must beat every other by this factor to count as decided. Ambiguous
#: bitmaps are counted separately rather than silently scored -- a photograph has no
#: preferred rotation and would otherwise add noise in whichever direction it fell.
DECISIVE = 1.5


class Law(object):
    """One checkable property, its violations, and what it looked at."""

    def __init__(self, name, note):
        self.name, self.note = name, note
        self.checked = self.violations = 0
        self.detail = collections.Counter()
        self.witnesses = []

    def see(self, ok, witness=None, **tally):
        self.checked += 1
        if not ok:
            self.violations += 1
            if witness and len(self.witnesses) < 8:
                self.witnesses.append(witness)
        self.detail.update(tally)

    def report(self):
        if not self.checked:
            return '   %-18s EXAMINED NOTHING -- not a pass' % self.name
        rate = 100.0 * self.violations / self.checked
        s = ('   %-18s %6d checked  %5d violations  %5.1f%%   %s'
             % (self.name, self.checked, self.violations, rate, self.note))
        for k, v in sorted(self.detail.items()):
            s += '\n        %-46s %6d' % (k, v)
        for w in self.witnesses:
            s += '\n        witness: %s' % (w,)
        return s


# --- laws that read the bitmaps, and need no render ----------------------------------

def _pixel_bitmaps(asm):
    for rec in asm.records:
        if rec.filter_name != 'bitmap':
            continue
        bm = getattr(rec, 'bitmap', None) or {}
        if bm.get('kind') == 'pixels' and bm.get('size') and bm.get('depth'):
            yield rec, bm


def _samples(asm, rec, bm, stride=97):
    off, size, ch, depth = bm['offset'], bm['size'], bm['channels'], bm['depth']
    if not ch or off + size > len(asm.data):
        return None
    n = rec.height * rec.width * ch
    arr = np.frombuffer(asm.data[off:off + size], dtype='<u1' if depth == 8 else '<u2')
    if arr.size < n:
        return None
    return arr[:n].reshape(-1, ch)[::stride].astype(np.float64) / float((1 << depth) - 1)


def _unit_error(x, k):
    """Mean |x^2 + y^2 + z^2 - 1| reading (x, y, z) starting at channel k."""
    ch = x.shape[1]
    a, b, c = (x[:, (0 + k) % ch], x[:, (1 + k) % ch], x[:, (2 + k) % ch])
    return float(np.abs((2 * a - 1) ** 2 + (2 * b - 1) ** 2 + c ** 2 - 1.0).mean())


def check_alpha_last(asm, laws):
    """An RGBA image's flattest channel is its alpha, and alpha is the last channel.

    Self-controlling: the index is reported for every bitmap, so a decode shifted by a
    whole number of channels shows up as a mode somewhere other than the last rather
    than as a silent pass.
    """
    law = laws['alpha_last']
    for rec, bm in _pixel_bitmaps(asm):
        if bm['channels'] != 4:
            continue
        x = _samples(asm, rec, bm)
        if x is None:
            continue
        idx = int(np.argmin(x.std(0)))
        law.see(idx == 3, **{'flattest channel at index %d' % idx: 1})


#: The unit-length test is applied ONLY to 16-bit RGBA. See check_normal_rotation.
ROTATION_LAYOUTS = frozenset({(16, 4)})


def check_normal_rotation(asm, laws):
    """Where a channel rotation is DECIDED by the unit-length law, it must be zero.

    THE UNIT-LENGTH LAW DOES NOT HOLD ON THIS CORPUS, and saying so is the point of this
    docstring. A tangent-space normal map should satisfy x^2 + y^2 + z^2 == 1 exactly;
    here the BEST rotation of a bitmap that is plainly a normal map still sits at a mean
    |L - 1| of 0.10 to 0.24. So this is not a law the data obeys, it is a RELATIVE
    discriminator: the right channel order scores better than the wrong ones, by a wide
    margin, while none of them scores well.

    Run unrestricted it produced a 79% "violation" rate that meant nothing -- 214 of 352
    bitmaps were undecided, and most of the rest are not normal maps at all but still
    cleared a purely relative bar. Broken down by layout it is legible, and only one
    layout is trustworthy:

        layout          uncorrected offset      corrected offset
        depth 16 ch 4   rotation 2 x13          rotation 0 x13     <- confirms the fix
        depth  8 ch 3   rotation 2 x7, 1 x4     rotation 1 x7, 0 x5
        depth  8 ch 4   unchanged               unchanged          <- the null control
        depth 16 ch 3   rotation 0 x4           rotation 1 x3      <- prefers uncorrected

    16-bit RGBA is the only one with a second, independent instrument agreeing with it:
    the alpha-index test, which needs no unit-length assumption and moves 13 of 16 from
    index 1 to index 3. The 3-channel layouts have no alpha to anchor them, n is 3 to 7,
    and depth-16 ch-3 points the other way. That disagreement is NOT resolved and is not
    smoothed over by averaging the layouts together, which is what the unrestricted
    version did.

    None of this is what the offset correction rests on. That rests on the eight-byte
    header -- 'SBAM' at 0 and a version word at 4, in 40 of 40 files -- which is
    structural and layout-independent. This check is a weak secondary instrument that
    corroborates it where it has an anchor.
    """
    law = laws['normal_rotation']
    for rec, bm in _pixel_bitmaps(asm):
        ch, depth = bm['channels'], bm['depth']
        if not ch or ch < 3 or (depth, ch) not in ROTATION_LAYOUTS:
            continue
        x = _samples(asm, rec, bm)
        if x is None:
            continue
        errs = [_unit_error(x, k) for k in range(ch)]
        order = sorted(range(ch), key=lambda k: errs[k])
        best, runner = order[0], order[1]
        if errs[best] <= 0 or errs[runner] < DECISIVE * errs[best]:
            law.detail['no rotation decided (not normal-map-like)'] += 1
            continue
        law.see(best == 0,
                witness=('%s rec %d wants rotation %d (err %.3f vs %.3f)'
                         % (os.path.basename(getattr(asm, 'path', '?')),
                            asm.records.index(rec), best, errs[best], errs[runner])),
                **{'decided on rotation %d' % best: 1})


def check_packing(asm, laws):
    """Consecutive images pack back to back: offset[k+1] - offset[k] == size[k].

    NOTE WHAT THIS CANNOT DO. It is invariant to a uniform shift of every offset, which
    is exactly the defect the four-byte correction fixes, and it held just as firmly
    before that fix as after. It is not evidence the offsets are right. It is a guard
    that any future correction stays a uniform shift, and it is kept precisely so the
    next reader does not mistake it for the stronger thing again.
    """
    law = laws['packing']
    spans = sorted({(bm['offset'], bm['size']) for _r, bm in _pixel_bitmaps(asm)})
    for k in range(len(spans) - 1):
        off, size = spans[k]
        if spans[k + 1][0] == off:                # two records sharing one image
            continue
        law.see(spans[k + 1][0] - off == size)


# --- laws that need the render --------------------------------------------------------

def check_outputs(asm, outs, laws):
    """Finiteness, range, and the output table's grayscale bit against what came out."""
    fin, rng, gray = laws['finite'], laws['range'], laws['grayscale_bit']
    name = os.path.basename(getattr(asm, 'path', '?'))
    for uid, _fmt, is_gray, ri in asm.outputs():
        if ri is None or ri not in outs:
            continue
        x = np.asarray(outs[ri])
        fin.see(bool(np.isfinite(x).all()), witness='%s rec %d not finite' % (name, ri))
        lo, hi = float(np.nanmin(x)), float(np.nanmax(x))
        rng.see(-0.001 <= lo and hi <= 1.001,
                witness='%s rec %d spans [%.3f, %.3f]' % (name, ri, lo, hi))
        # Two independent declarations, which is what makes this a law rather than a
        # restatement: the bit comes from the output table, the channel count from the
        # pixels the renderer produced.
        nch = 1 if x.ndim == 2 else x.shape[-1]
        gray.see(bool(is_gray) == (nch == 1),
                 witness='%s rec %d grayscale=%s but %d channels' % (name, ri, is_gray, nch),
                 **{'grayscale bit %s, %d channel(s)' % (bool(is_gray), nch): 1})


def sweep(paths, max_dim=64, do_render=True, verbose=True):
    laws = collections.OrderedDict(
        (n, Law(n, d)) for n, d in (
            ('alpha_last', 'RGBA alpha is the flattest channel and sits last'),
            ('normal_rotation', 'a decided channel rotation must be zero'),
            ('packing', 'images pack back to back (blind to a uniform shift)'),
            ('finite', 'no NaN or Inf in a produced output'),
            ('range', 'produced values lie in [0, 1]'),
            ('grayscale_bit', 'the output table\'s grayscale bit matches the channels'),
        ))
    tally = collections.Counter()
    import render as R                                   # deferred: heavy import
    for n, f in enumerate(paths):
        try:
            asm = Assembly(f)
        except Exception:
            tally['files that would not load'] += 1
            continue
        tally['files'] += 1
        for fn in (check_alpha_last, check_normal_rotation, check_packing):
            try:
                fn(asm, laws)
            except Exception as e:
                tally['bitmap law raised %s' % type(e).__name__] += 1
        if do_render:
            try:
                outs, _fl, _sy = R.render(asm, verbose=False, max_dim=max_dim,
                                          synth_missing_bitmaps=False)
            except Exception as e:
                tally['render raised %s' % type(e).__name__] += 1
                outs = None
            if outs is not None:
                check_outputs(asm, outs, laws)
                for _uid, _fmt, _g, ri in asm.outputs():
                    if ri is None:
                        continue
                    tally['declared outputs'] += 1
                    if ri in outs:
                        tally['produced'] += 1
                        tally['spatial'] += 1 if imgstat.classify(outs[ri]) == 'spatial' else 0
        if verbose and (n + 1) % 25 == 0:
            sys.stderr.write('  ... %d/%d files\n' % (n + 1, len(paths)))
            sys.stderr.flush()
    return laws, tally


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 0
    max_dim = int(argv[2]) if len(argv) > 2 else 64
    paths = corpus.paths()
    if n:
        paths = paths[:n]
    print('sweeping %d files at max_dim %d\n' % (len(paths), max_dim))
    laws, tally = sweep(paths, max_dim=max_dim)
    print('LAWS')
    for law in laws.values():
        print(law.report())
    print('\nTOTALS')
    for k, v in sorted(tally.items()):
        print('   %-40s %7d' % (k, v))
    bad = [l.name for l in laws.values() if l.checked and l.violations]
    empty = [l.name for l in laws.values() if not l.checked]
    print('\n   laws violated: %s' % (bad or 'none'))
    print('   laws that examined nothing: %s' % (empty or 'none'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
