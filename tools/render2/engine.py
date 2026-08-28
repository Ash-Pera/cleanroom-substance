#!/usr/bin/env python3
"""The forward pass: one record at a time, in index order, each read through the walk.

Edges point strictly backwards -- verified corpus-wide over 353,068 sampled edges -- so a
single forward pass suffices and nothing needs a topological sort.

WHAT THIS RENDERER REFUSES TO DO, because the old one did it and it cost the specimen this
was rebuilt against:

  * It does not read a slot the walk did not name. `model.View` is the only place a slot
    number appears, and it comes from `decompose`.
  * It does not decide a parameter's kind by looking at the value. The class-word bit pair
    and the w1 two-bit code both state it.
  * It does not pad a record's channels to match a guess. `ops.conform` narrows identical
    channels and widens RGB to RGBA; anything else is a refusal, because a channel count
    that disagrees with the record's own colour flag means the wrong program ran. The
    three-channel bitmap this file carries used to be widened with an invented alpha, and
    a weight-vector sweep then picked the vector that read most of that invented channel.
"""
import numpy as np

import assume
import manifest
import sbsruntime

import filters
import model
from ops import Unsupported, bind, conform, run_program, sampler


class Context(object):
    """Everything a filter needs that is not its own record."""

    def __init__(self, asm, cap=None):
        self.asm = asm
        self.cap = cap
        self.outputs = {}
        self.low_confidence = set()
        self.synthetic = set()
        self._bindings = {}
        self._inputs = {}

        # THE 0x03/0x06 VALUE CACHE IS THIS CONTEXT'S, not `sbsruntime`'s module global.
        # The two opcodes are cross-record common-subexpression elimination -- a value one
        # record's program computes and another reads back by index -- so answering a
        # `cache_read` needs one dict threaded through a whole file in record order, which
        # is what `render` is. The indices are bare integers with nothing in them naming a
        # file, so a dict reachable by every caller at once cannot say WHOSE index 3 it is
        # holding: a global made a leak between two files possible, and installing and
        # restoring one only made it brief. Held here, the reader and the writer are the
        # same evaluation because they are the same closure, and two Contexts are two
        # caches whether or not they overlap.
        #
        # `_funcs` and `fx_funcs` are the programs compiled against it, and they live
        # here for that reason and not for speed: a function bound to one cache must never
        # be handed to a Context holding another. See `ops.bind`.
        self.cache = {}
        self.cache_funcs = sbsruntime.cache_functions(self.cache)
        self._funcs = {}
        self.fx_funcs = {}

    # -- inputs ------------------------------------------------------------------

    def src(self, v, k):
        """Input k's full-resolution array, or a cascade failure."""
        e = v.edge(k)
        if e is None:
            raise Unsupported('input %d is not wired' % k)
        if e not in self.outputs:
            raise _cascade(e)
        return self.outputs[e]

    def sample(self, v, k, pos):
        """Input k sampled at `pos` -- (N, C)."""
        return sampler(self.src(v, k))(pos)

    # -- programs ----------------------------------------------------------------

    def graph_inputs(self, n):
        got = self._inputs.get(n)
        if got is None:
            got = self._inputs[n] = {}
            for _t, uid, val in self.asm.header.get('inputs') or []:
                if val:
                    got[uid] = np.repeat(np.array(val, np.float32).reshape(1, -1),
                                         n, axis=0)
        return got

    def run(self, v, ptr, n, slots=None, pos=None, W=None, H=None):
        """Evaluate one of `v`'s programs. `$size` is the RECORD'S DECLARED SIZE.

        THE ONE PLACE THAT DECIDES IT, because two of the three ways to get this wrong are
        invisible. `$size` is a property of the file and `max_dim` is a sweep shortcut, so
        a parameter whose program reads `$size` must not change when the caller renders
        smaller -- that already cost 4,058 Bricks records a resolution dependence through
        `transformation`'s offset. And a call that passes NO size at all is worse than
        wrong, it is ORDER-DEPENDENT: `sbsruntime.set_context` ignores None by design, so
        the program would read whatever record ran last. That is the shape of the leak
        `cc97a7a` fixed in `blur`, and `_fill_program`, `distance`, the `emboss` probe and
        the FX slot seeding all call this without a size.

        `pos` is the RENDER GRID and is passed through, because a per-pixel program is
        evaluated at whatever grid the caller is drawing on. Size and position are
        different questions and only one of them is a property of the record.

        ONE CALLER OVERRIDES THE SIZE ON PURPOSE: a `pixelprocessor`'s own image program,
        which is the only population here that reads `$pos` (of 6,793 program-valued
        PARAMETERS across a corpus sample, zero do), so for it `$size` and `$pos` have to
        describe the same grid or a neighbour tap becomes sub-pixel and the filter
        silently turns into an identity.
        """
        fn = bind(self.asm, ptr, self.cache, self._funcs)
        return run_program(fn, self.graph_inputs(n),
                           {} if slots is None else slots, n, pos=pos,
                           W=v.width if W is None else W,
                           H=v.height if H is None else H)

    def prog_at(self, v, slot):
        """The program a slot names, or None -- `word + 52`, bounds- and validity-checked."""
        if slot is None or not (0 <= slot < len(v.words)):
            return None
        p = v.words[slot] + 52
        if not (self.asm.body_lo <= p < self.asm.body_hi):
            return None
        return p if self.asm.valid_program(p) else None

    def walk_programs(self, v, include_prog_slot=False):
        """Every program THE WALK NAMES for this record, in slot order.

        Not `Record.programs`, which scans every word of the record and calls anything
        passing `valid_program` a program: past the header a record is bytecode, so an
        instruction operand that survives that test comes back as a program. On one corpus
        file that phantom evaluated 2-wide and collided with a real offset parameter.

        The named slots are the size expression, the class-word program arms, and the w1
        fields whose two-bit code is 10.
        """
        out, seen = [], set()
        cands = []
        if v.size_slot is not None:
            cands.append(v.size_slot)
        if include_prog_slot and v.prog_slot is not None:
            cands.append(v.prog_slot)
        for p in v.params.values():
            if p.kind == 'program':
                cands.append(p.slot)
        for _f, p in v.unnamed:
            if p.kind == 'program':
                cands.append(p.slot)
        cands.extend(v.cls_slots)
        for slot in sorted(set(cands)):
            got = self.prog_at(v, slot)
            if got is not None and got not in seen:
                seen.add(got)
                out.append(got)
        return out

    # -- image inputs that arrive by sampler rather than by edge -------------------

    def sampler_bindings(self, v):
        """{sampler index: source record} for images the manifest wires, not the edges.

        An `fxmaps` or `pixelprocessor` can sample a graph image input that no edge
        reaches. The binding is the graph's image inputs in MANIFEST DECLARATION ORDER,
        and only for a record that is itself a declared output, because that is the only
        case where graph membership is known.
        """
        got = self._bindings.get(v.index)
        if got is not None:
            return got
        out = {}
        try:
            table = self.asm.outputs()
        except Exception:
            table = ()
        uid = next((u for u, _f, _c, i in table if i == v.index), None)
        if uid is not None:
            order = manifest.image_inputs_for_output(self.asm, uid) or ()
            by_uid = {}
            for r in self.asm.records:
                if r.filter_name == 'bitmap' and (r.bitmap or {}).get('kind') == 'graph_input':
                    by_uid.setdefault(r.bitmap['uid'], r.index)
            for k, iu in enumerate(order):
                s = by_uid.get(iu)
                if s is not None and s in self.outputs:
                    out[k] = s
        self._bindings[v.index] = out
        return out


def _cascade(e):
    exc = Unsupported('edge -> record %s has no output yet' % e)
    exc.cascade = True
    return exc


def render(asm, precomputed=None, verbose=False, max_dim=None, stop_after=None):
    """Evaluate every record. Returns (outputs, failures, info).

    `info` carries `low_confidence` -- records whose output rests on a value the FORMAT
    does not record -- `cascaded`, the failures that are only consequences, and `ignored`,
    records that STATE a field this renderer's legend does not name. The last is the one
    that used to be invisible: an unnamed parameter reads as its default, and a default
    renders, so `hsl` was an identity in 747 records and `sharpen` in 1,156 without either
    ever appearing in a count.
    """
    ctx = Context(asm, cap=max_dim)
    ctx.outputs.update(precomputed or {})
    failures, cascaded, ignored = {}, set(), {}

    # THE VALUE CACHE IS `ctx.cache` AND NOTHING IS INSTALLED ANYWHERE. Record order is
    # what makes a `cache_read` answerable -- writers precede readers, over 7,074 matched
    # pairs with zero exceptions -- and this loop is that order. See `Context.__init__`.
    for rec in asm.records:
        i = rec.index
        if i in ctx.outputs:
            continue
        try:
            # INSIDE the try: `View` raises `model.Shifted` when the end-anchored
            # parameter block lands on an input edge or a mask word, and that is one
            # RECORD's refusal, not the file's.
            v = model.View(asm, rec)
            if v.ignored:
                # A FIELD THE RECORD STATES AND NO NAME COVERS. Kept as its own channel,
                # not folded into `low_confidence`: that set means "a value the format does
                # not record was assumed", and 57,731 pixelprocessor records carrying an
                # unnamed class pointer would drown it. This one says the opposite -- the
                # value IS in the file and this renderer did not read it.
                ignored[i] = tuple(v.ignored)
            if not v.walked:
                raise Unsupported('the cost model does not cover this record header, so '
                                  'no slot of it can be read structurally')
            fn = filters.FILTERS.get(v.filter)
            if fn is None:
                raise Unsupported('filter %r has no implementation here' % v.filter)
            out = np.asarray(fn(ctx, v))
            want = 4 if v.colour else 1
            fixed = conform(out, want)
            if fixed is None:
                raise Unsupported('%s record produced %d channels, not %d'
                                  % ('colour' if v.colour else 'greyscale',
                                     out.shape[-1] if out.ndim == 3 else 1, want))
            if fixed.size and not np.all(np.isfinite(fixed)):
                fill = assume.assumed('nonfinite.fill')
                if fill is None:
                    raise Unsupported('produced non-finite values (%.1f%% of samples)'
                                      % (100.0 * float(np.mean(~np.isfinite(fixed)))))
                fixed = np.where(np.isfinite(fixed), fixed, np.float32(fill))
                ctx.low_confidence.add(i)
                assume.note(i)
            ctx.outputs[i] = fixed
        # `rec.filter_name`, NOT `v.filter`: building the View is inside the try now, so
        # `v` is not bound when it is the View that raised.
        except Unsupported as e:
            failures[i] = str(e)
            if getattr(e, 'cascade', False):
                cascaded.add(i)
            if verbose:
                print('rec%d (%s): SKIP - %s' % (i, rec.filter_name, e))
        except Exception as e:
            failures[i] = '%s: %s' % (type(e).__name__, e)
            if verbose:
                print('rec%d (%s): ERROR - %s: %s'
                      % (i, rec.filter_name, type(e).__name__, e))
        if stop_after is not None and i >= stop_after:
            break

    # CLAMP AT THE WRITE, NOT IN THE FILTER THAT OVERSHOT. `levels` leaves [0, 1] by
    # construction where an author set the output range outside the unit interval, and an
    # INTERMEDIATE at 1.31 feeding a multiply is headroom the engine may legitimately
    # consume. Only a declared output is clamped.
    for _uid, fmt, _grey, ri in asm.outputs():
        if isinstance(fmt, tuple) or ri not in ctx.outputs:
            continue
        a = ctx.outputs[ri]
        if a.min() < 0.0 or a.max() > 1.0:
            ctx.outputs[ri] = np.clip(a, 0.0, 1.0)

    info = {'low_confidence': ctx.low_confidence, 'cascaded': cascaded,
            'synthetic': ctx.synthetic, 'ignored': ignored}
    return ctx.outputs, failures, info
