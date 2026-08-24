"""Transpile a .sbsasm bytecode program into readable source.

The instruction stream is three-address code: one result per instruction, value numbers
contiguous from 0, operands naming earlier results. There are no branches -- `select` is
functional and the only loop construct is a capped `while` -- so a program transpiles to
straight-line code with no control-flow reconstruction. Each value number becomes one
assignment, in order.

That makes this the one conversion in this project that is faithful today. Everywhere
else a reader must guess at parameter values the format does not state; here the program
*is* the semantics, and the only question is whether the ISA table is right.

Backends emit Python (vectorised over numpy, so a program can be run and tested), GLSL
and OSL. The Python backend is what makes the ISA falsifiable: transpile a program whose
algorithm is known, evaluate it, and compare against the closed form.
"""
import struct

import disasm
import isa

# ---------------------------------------------------------------------------
# immediates

#: Operations whose immediate is a 4-byte value per component, and which therefore
#: carry the alignment pad described in OPCODES.md: an instruction landing at 0 mod 4
#: emits two bytes of padding so the immediate stays 4-aligned. Reading the immediate
#: from the first operand byte instead of past the pad silently returns a denormal --
#: 0.00031308 reads as 9.84e-17 -- which looks like data rather than a decode error.
WIDE_IMM = {0x00, 0x02}


def immediate(op, addr, toks):
    """The immediate carried by an instruction, as a list of floats or ints.

    Three rules, not one:

    * a float or int constant carries four bytes per component;
    * a bool constant carries a single u16 and the component field is unused
      (FORMAT-NOTES.md, "The component field is unused for booleans");
    * an input reference carries one u32 uid whatever its result width -- the
      component field describes the value read, not the immediate.
    """
    _ntok, ty, comps, oid = disasm.fields(op)
    if oid not in WIDE_IMM:
        return list(toks)
    if oid == 0x00 and ty == 0:
        return [bool(toks[0])] if toks else [False]
    # One pad rule, shared with the disassembler.
    raw = disasm.immediate(addr, toks)
    want = 4 if oid == 0x02 else 4 * comps
    if len(raw) < want:
        raise Unsupported("opcode %04X at %d: %d immediate bytes, wanted %d"
                          % (op, addr, len(raw), want))
    body = raw[:want]
    # A uid is an integer however the instruction types its result.
    kind = "i" if oid == 0x02 else ("f" if ty == 1 else "i")
    code = "<%d%s" % (want // 4, kind)
    return list(struct.unpack(code, body))


def swizzle_mask(mask, ncomp):
    """A packed 2-bit component mask, as a list of source indices."""
    return [(mask >> (2 * i)) & 3 for i in range(ncomp)]


# ---------------------------------------------------------------------------
# backends

class Backend:
    """Emits one line of target source per instruction."""

    name = "abstract"
    header = ""

    def var(self, k):
        return "v%d" % k

    def const(self, values, ty):
        raise NotImplementedError

    def call(self, fn, args):
        return "%s(%s)" % (fn, ", ".join(args))

    def binop(self, symbol, a, b):
        return "(%s %s %s)" % (a, symbol, b)


class Python(Backend):
    name = "python"
    header = ("import numpy as np\n"
              "from sbsruntime import (sysvar, sample_lum, sample_col, vec, swizzle,\n"
              "                        select, rand, cartesian, lerp, sbs_mod, atan2, cvt,\n"
              "                        dot,\n"
              "                        cache_read, cache_write, clamp)\n")

    def const(self, values, ty):
        if ty == 0:
            return "np.bool_(%s)" % bool(values[0])
        if len(values) == 1:
            return repr(float(values[0]) if ty == 1 else int(values[0]))
        return "vec(%s)" % ", ".join(repr(float(v) if ty == 1 else int(v)) for v in values)


class GLSL(Backend):
    name = "glsl"

    def const(self, values, ty):
        if ty == 0:
            return "true" if values[0] else "false"
        fmt = (lambda v: "%r" % float(v)) if ty == 1 else (lambda v: "%d" % int(v))
        if len(values) == 1:
            return fmt(values[0])
        kind = {1: "vec", 2: "ivec", 0: "bvec"}[ty]
        return "%s%d(%s)" % (kind, len(values), ", ".join(fmt(v) for v in values))


class OSL(Backend):
    name = "osl"

    def const(self, values, ty):
        if ty == 0:
            return "1" if values[0] else "0"
        fmt = (lambda v: "%r" % float(v)) if ty == 1 else (lambda v: "%d" % int(v))
        if len(values) == 1:
            return fmt(values[0])
        if len(values) == 3:
            return "vector(%s)" % ", ".join(fmt(v) for v in values)
        return "{%s}" % ", ".join(fmt(v) for v in values)


BACKENDS = {b.name: b for b in (Python, GLSL, OSL)}

# ---------------------------------------------------------------------------
# the operation table
#
# ('bin', symbol)   an infix operator
# ('fn', name)      a call, arguments in order
# handled inline:   const, sysvar, inputref, get, set, seq, vec, swizzle, cvt, sample*

BINOP = {0x12: "+", 0x13: "-", 0x14: "*", 0x15: "/",
         0x1A: "and", 0x1B: "or",
         0x1D: "==", 0x1E: "!=", 0x1F: ">", 0x20: ">=", 0x21: "<", 0x22: "<="}

FUNCS = {0x16: "sbs_mod", 0x17: "-", 0x18: "dot", 0x23: "abs", 0x24: "floor",
         0x2A: "exp",
         0x25: "ceil", 0x26: "cos", 0x27: "sin", 0x28: "sqrt", 0x29: "log",
         0x2B: "exp2", 0x2C: "not", 0x2D: "atan2", 0x2E: "cartesian",
         0x35: "log2", 0x36: "pow",
         0x2F: "lerp", 0x30: "minimum", 0x31: "maximum", 0x32: "rand"}

PY_FUNCS = {"abs": "np.abs", "floor": "np.floor", "ceil": "np.ceil", "cos": "np.cos",
            "exp": "np.exp",
            "sin": "np.sin", "sqrt": "np.sqrt", "log": "np.log", "log2": "np.log2",
            "exp2": "np.exp2",
            "pow": "np.power",
            # atan2 is NOT np.arctan2: one operand of two components, not two scalars.
 "minimum": "np.minimum", "maximum": "np.maximum",
            # dot is row-wise, not np.dot, which is a matrix product.
            }

PY_LOGIC = {"and": "np.logical_and", "or": "np.logical_or"}


#: Operations whose meaning is not established. Operand shape comes from the
#: disassembler's IMM table where it names one; the rest take ordinary value numbers
#: throughout, verified at 0% "operand >= own index" over the corpus. 0x1E and 0x2A were
#: here and have since been named in OPCODES.md as `neq` and `exp`; 0x06 was here and is
#: now handled explicitly above -- its meaning is known even though evaluating it needs
#: an architecture this transpiler does not have yet.
#:
#: 0x35 and 0x36 were both here too, briefly and prematurely, before either had real
#: evidence -- see git history if the story matters. Both are proven now, by two
#: different methods:
#:
#: 0x35 = log2, a structural match: `ie_pcloud`'s source computes a graph input's
#: outputsize override as get_float3 -> swizzle2 -> log2 -> toint2, and the compiled
#: file has the identical four-instruction shape (inputref -> swizzle -> op35 -> cvt),
#: byte-identical, four times over -- once per input that declares the override. See
#: test_log2_matches_ie_pcloud_source.
#:
#: 0x36 = pow, a numeric match: `LeakingSubstance004` computes
#: ((s+0.055)/1.055) ** 2.4 -- the inverse sRGB transfer function, the same closed form
#: `Embroidery_Legacy` already proved via ln/exp2 -- using op36(x, 2.4) directly, and
#: the linear branch's 0.0773994 constant is 1/12.92 to 8 decimal places. Transpiled and
#: evaluated against the closed form: max deviation 1.19e-07, identical to the ln/exp2
#: proof. See test_pow_via_srgb_decode.
UNNAMED = set()


class Unsupported(Exception):
    pass


def transpile(data, start, end, backend="python", name="program", result=None):
    """Return target source for the program at `start`.

    `result` names the value number to return, for reading a sub-expression out of a
    larger program; the default is the program's final value.
    """
    be = BACKENDS[backend]()
    ins = list(disasm.decode(data, start, end))
    if not ins:
        raise Unsupported("empty program")
    byk = {i[0]: i for i in ins}

    def emit(k, active=None):
        """The lines one instruction emits, unindented.

        `active` names a per-lane boolean expression, or None outside a loop. See its use
        in the 0x07 branch and in `emit_range`'s while handling below.
        """
        _k, addr, op, toks = byk[k]
        _ntok, ty, ncomp, oid = disasm.fields(op)
        v = be.var(k)
        out = []

        def arg(i):
            if i >= len(toks):
                raise Unsupported("opcode %04X at %d: wanted operand %d of %d"
                                  % (op, addr, i, len(toks)))
            t = toks[i]
            if t == 0xFFFF and backend == "python":
                # The same absent-value sentinel `while`'s condition operand and
                # `Assembly.valid_program`/`program_span` already treat specially
                # (0xFFFF, not a real value number -- see program_span's docstring). Here
                # it shows up as an ordinary operand, most often one branch of a `select`
                # whose condition never actually picks it for a valid input (273 corpus
                # instances, over a third of them `vec`, not just `select`). `be.var`
                # would emit a reference to a value that was never assigned -- NameError,
                # not a wrong number -- so this emits NaN instead: inert if the branch is
                # genuinely unreachable, and loud rather than silently plausible on the
                # rare input where it is not.
                return "float('nan')"
            return be.var(t)

        if oid == 0x00:                                    # const
            rhs = be.const(immediate(op, addr, toks), ty)
        elif oid == 0x01:                                  # system variable
            rhs = be.call("sysvar", [str(toks[0]), str(ncomp)])
        elif oid == 0x02:                                  # graph input by uid
            rhs = "inputs[%d]" % (immediate(op, addr, toks)[0] & 0xFFFFFFFF)
        elif oid == 0x03:                                  # cache_read: 0x03/0x06 are a
            # per-package indexed value cache used for cross-record common-subexpression
            # elimination -- 0x06 (below) writes a value once, from a dedicated
            # pixelprocessor record that is never itself sampled as an image, and any
            # record's own program reads it back by index rather than recomputing it.
            # See FORMAT-NOTES.md, "0x03/0x06 are cross-record common-subexpression
            # elimination". The MEANING is known; a single-program transpile still
            # cannot EVALUATE it, because the value lives in a different program,
            # possibly a different record, evaluated earlier in record order. cache_read
            # raises rather than guessing -- see sbsruntime.cache_read's docstring.
            rhs = be.call("cache_read", [str(toks[0]) if toks else "0"])
        elif oid == 0x04:                                  # get variable slot
            rhs = "slots[%d]" % toks[0]
        elif oid == 0x07:                                  # set variable slot
            # Every sample runs in one shared Python `for` loop (see the while handling
            # below), so a plain assignment here would keep overwriting a lane's slot
            # after ITS OWN condition went true, using whatever the other, still-running
            # lanes' iterations compute. `active` freezes it: keep the new value only
            # where this lane is still active, otherwise keep what was already there.
            # `active` is (own, expr): `own` is the innermost loop's own mask variable,
            # the only one that can still be unset on its first iteration, checked first
            # so the ternary short-circuits before `expr` (which may combine `own` with
            # an outer loop's mask, for nested loops) ever has to evaluate `None & array`.
            if active is not None:
                own, expr = active
                out.append("slots[%d] = %s if %s is None else select(%s, %s, slots[%d])"
                            % (toks[1], arg(0), own, expr, arg(0), toks[1]))
            else:
                out.append("slots[%d] = %s" % (toks[1], arg(0)))
            rhs = arg(0)
        elif oid == 0x0C:                                  # sequence
            rhs = arg(len(toks) - 1)
        elif oid == 0x0D:                                  # construct vector, by
            # concatenation: always exactly two operands whatever the result width.
            # The instruction's own declared ncomp is authoritative -- see `vec`'s
            # docstring for why concatenation alone can overshoot it.
            args = [arg(i) for i in range(len(toks))]
            if backend == "python":
                args.append("ncomp=%d" % ncomp)
            rhs = be.call("vec", args)
        elif oid == 0x0F:                                  # build a 4-vector from four
            # scalars. Probable rather than confirmed -- 28 instances, all terminal, all
            # in `levels`, all of the shape (x, x, x, 1). See OPCODES.md.
            args = [arg(i) for i in range(len(toks))]
            if backend == "python":
                args.append("ncomp=%d" % ncomp)
            rhs = be.call("vec", args)
        elif oid == 0x10:                                  # swizzle
            mask = swizzle_mask(toks[1], ncomp)
            rhs = be.call("swizzle", [arg(0), str(mask)])
        elif oid == 0x11:                                  # type conversion
            if backend == "python":
                rhs = be.call("cvt", [arg(0), "True" if ty == 2 else "False"])
            else:
                rhs = be.call("float" if ty == 1 else "int", [arg(0)])
        elif oid == 0x09:                                  # select(cond, a, b)
            rhs = be.call("select", [arg(0), arg(1), arg(2)])
        elif oid == 0x1C:                                  # not
            rhs = be.call("np.logical_not" if backend == "python" else "not", [arg(0)])
        elif oid == 0x33:                                  # sample luminance
            rhs = be.call("sample_lum", [str(toks[1]), arg(0)])
        elif oid == 0x34:                                  # sample colour
            rhs = be.call("sample_col", [str(toks[1]), arg(0)])
        elif oid in BINOP:
            # Clamp the OPERANDS, not just the result. A corpus census found both
            # operands of all 3,248,836 `add` instructions declare the instruction's own
            # width, with zero exceptions -- so trimming each to that width can only undo
            # drift, never discard something the format put there. Clamping the result
            # alone is too late: the operation runs first, and eight failures were a
            # mismatch inside `clamp((a * b), 2)`.
            sym = BINOP[oid]

            def _w(i, n=ncomp):
                a = arg(i)
                return "clamp(%s, %d)" % (a, n) if n and n > 1 else a

            if backend == "python" and sym in PY_LOGIC:
                rhs = be.call(PY_LOGIC[sym], [_w(0), _w(1)])
            else:
                rhs = be.binop(sym, _w(0), _w(1))
        elif oid in FUNCS:
            fn = FUNCS[oid]
            if fn == "-":
                rhs = "(-%s)" % arg(0)
            else:
                if backend == "python":
                    fn = PY_FUNCS.get(fn, fn)
                rhs = be.call(fn, [arg(i) for i in range(len(toks))])
        elif oid == 0x06:                                  # cache_write: the other half
            # of 0x03's pair. Position 0 is the value (an ordinary reference); position 1
            # is the cache index (immediate). Meaning known, same evaluation limit as
            # cache_read -- see there.
            rhs = be.call("cache_write", [arg(0), str(toks[1])])
        elif oid in UNNAMED:
            # The operation is not identified, but its operand *shape* is: positions the
            # disassembler's IMM table names are immediates, the rest are value numbers.
            # Emitted as an opaque call so the program still transpiles and the gap is
            # visible in the output rather than silent.
            imm_pos = disasm.IMM.get(oid, ())
            imm_pos = range(len(toks)) if imm_pos == "all" else imm_pos
            rhs = be.call("op%02X" % oid,
                          [str(toks[i]) if i in imm_pos else arg(i)
                           for i in range(len(toks))])
        else:
            raise Unsupported("opcode %04X (id %02X, type %d) at %d"
                              % (op, oid, ty, addr))
        # Clamp to the instruction's own declared width. Without this a value can drift
        # wider than declared and the drift only surfaces later, at a `vec` or a binary
        # operation that cannot broadcast. See sbsruntime.clamp.
        if ncomp and ncomp > 1:
            rhs = "clamp(%s, %d)" % (rhs, ncomp)
        out.append("%s = %s" % (v, rhs))
        return out

    # A `while` owns the instructions between its initialiser and its body. Operand 0 is
    # the init, 1 the condition, 2 the body, and `init < cond < body < while` holds in 543
    # of 543 instances, with the body always the instruction immediately before the `while`
    # itself. So the range (init, body] is exactly the condition and the body, and it is
    # emitted INSIDE the loop rather than before it.
    #
    # Operands 3 to 5 are ignored, and that is not an assumption: every one of them names a
    # value already reachable from operands 0-2 - 543/543, 542/543 and 363/363 - so they
    # can tell the loop nothing it does not already compute. See FORMAT-NOTES.md.
    #
    # The condition is a TERMINATION test. Under the other reading the body never runs in
    # either program read in full: both compare a counter starting at 0 against a positive
    # limit, so the test is false on entry and the loop would be a no-op whose accumulator
    # is nevertheless read afterwards.
    #
    # The iteration cap is a runtime guard, not a claim about the format, and it is sized
    # from the format rather than picked: the tag encodes a dimension as `log2`, in four
    # bits, so the largest image a record can declare is 2^15 = 32,768 along an axis. A
    # loop that walks a dimension therefore needs at most that many iterations, and the
    # cap is set one power of two above it.
    #
    # It matters that it is not larger. Measured over 122 loop programs run with plausible
    # inputs, every one terminates in 1 to 3 iterations - so the cap is never approached in
    # normal use. But a loop whose condition depends on an input the caller does not supply
    # can fail to terminate, and at 1 << 24 a single such program burns 16 million
    # iterations: a corpus sweep that completed in minutes before became a ten-minute
    # timeout on six files.
    loops = {}
    for k, addr, op, toks in ins:
        if (op & 0x3F) == 0x0B:
            if len(toks) < 3:
                raise Unsupported("opcode %04X at %d: while wants 3 operands" % (op, addr))
            # Opcode 0x0B has two encodings: a 6-operand form (406 in the corpus, all
            # well-ordered) and a 5-operand form (515). In the 5-operand form operand 2 is
            # k-1 and operand 4 is 0, in 515 of 515.
            #
            # 164 of those carry 0xFFFF in operand 1 -- the absent-operand sentinel this
            # format uses everywhere else -- so their CONDITION is absent, and operands 0
            # and 2 are ordered normally around it. They were reported as "out of order",
            # which named the symptom and hid the cause.
            #
            # What bounds a condition-less loop is not established: operand 0 points at a
            # sequence node (0x0C) in 164 of 164, operand 3 is 3 in 158 of 164 but also
            # appears with the condition present so it is not cleanly a trip count, and
            # the body carries a cross-iteration dependency in 100% of loops either way,
            # which is the base rate and so discriminates nothing. Emitting a loop with no
            # break would be an unbounded loop, and emitting a single pass would assume the
            # answer, so these stay unsupported until the bound is found.
            if len(toks) >= 2 and toks[1] == 0xFFFF:
                # 164 instructions carry 0xFFFF here - the absent-operand sentinel - so
                # the loop has no termination test. Operand 3 is read as a fixed trip
                # count; it is 3 in 158 of them and nothing else in the instruction can
                # bound the loop.
                #
                # The count is NOT established, and this is adopted anyway because the
                # result does not depend on it. Running these loops at 1, 3 and 9
                # iterations, with a shared cache threaded through the whole file so the
                # control group runs too:
                #
                #     identical at 1, 3 and 9      14 of 15
                #     differs                       1  (0.5 at one pass, 0.498047 at
                #                                       both 3 and 9 - it converges)
                #
                # They are iterative refinements that settle, so any count of 3 or more
                # gives the same answer. Execution rates match the control: 15 of 16 run
                # against 21 of 22 for loops that do have a condition, each losing one
                # program to a cache read whose writer runs later.
                trip = toks[3] if len(toks) > 3 else 0
                if not (1 <= trip <= 64):
                    raise Unsupported("opcode %04X at %d: condition absent and operand 3 "
                                      "= %s is not a usable trip count" % (op, addr, trip))
                loops[toks[0] + 1] = (k, toks[0], None, toks[2], trip)
                continue
            if not (toks[0] < toks[1] < toks[2] < k):
                raise Unsupported("opcode %04X at %d: while operands out of order" % (op, addr))
            loops[toks[0] + 1] = (k, toks[0], toks[1], toks[2], None)

    lines = []

    def emit_range(lo, hi, depth, active=None):
        pad = "    " * depth
        k = lo
        while k <= hi:
            if k in loops:
                # Pop it: the loop's own range starts at this same index, so leaving the
                # entry in place makes emit_range re-enter it forever.
                kw, i0, icond, ibody, trip = loops.pop(k)
                # The loop's own value is the body's, but a loop can run ZERO times -- the
                # condition is a termination test and may hold on entry -- so the body's
                # variable need not be bound when the loop ends. Bind it first and assign
                # inside, rather than after.
                lines.append(pad + "%s = None" % be.var(kw))
                # `active_N`: this loop's own per-lane "still running" mask. Every sample
                # shares the one Python `for` below, so a lane whose condition went true
                # on iteration 3 does not stop -- the loop only exits once EVERY lane's
                # condition holds. Without a mask, the body and the condition keep
                # re-running for an already-finished lane, using whatever it computed on
                # the last shared iteration rather than its own true stopping value: not
                # a crash, a silently wrong per-lane answer, which is worse. `active_N`
                # is None on the loop's own first pass (nothing has been checked yet, so
                # nothing needs freezing); `own` below is always that bare variable, so
                # its None-check short-circuits before `expr` -- which may AND in an
                # outer loop's mask for a nested loop -- ever evaluates `None & array`.
                if icond is None:
                    lines.append(pad + "for _it%d in range(%d):" % (kw, trip))
                    emit_range(i0 + 1, ibody, depth + 1, active=active)
                    lines.append(pad + "    %s = %s" % (be.var(kw), be.var(ibody)))
                    k = kw + 1
                    continue
                own = "active_%d" % kw
                expr = own if active is None else "(%s & %s)" % (active[1], own)
                lines.append(pad + "%s = None" % own)
                lines.append(pad + "for _it%d in range(1 << 16):" % kw)
                emit_range(i0 + 1, icond, depth + 1, active=(own, expr))
                lines.append(pad + "    _stop%d = np.asarray(%s).astype(bool)"
                              % (kw, be.var(icond)))
                lines.append(pad + "    %s = ~_stop%d if %s is None else (%s & ~_stop%d)"
                              % (own, kw, own, own, kw))
                lines.append(pad + "    if not np.any(%s): break" % own)
                emit_range(icond + 1, ibody, depth + 1, active=(own, expr))
                # The carry is frozen the same way: past a lane's own stopping point, its
                # exposed final value must stay put rather than keep tracking the body.
                lines.append(pad + "    %s = %s if %s is None else select(%s, %s, %s)"
                              % (be.var(kw), be.var(ibody), own, own, be.var(ibody), be.var(kw)))
                k = kw + 1
                continue
            for ln in emit(k, active=active):
                lines.append(pad + ln)
            k += 1

    emit_range(ins[0][0], ins[-1][0], 1)
    k = ins[-1][0]
    if not lines:
        raise Unsupported("empty program")
    last = be.var(k if result is None else result)
    body = "\n".join(lines)
    return ("%s\ndef %s(inputs=None, slots=None):\n"
            "    inputs = inputs if inputs is not None else {}\n"
            "    slots = slots if slots is not None else {}\n"
            "%s\n    return %s\n" % (be.header, name, body, last))
