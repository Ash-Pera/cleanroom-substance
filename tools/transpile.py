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
    f = disasm.fields(op)
    if f["id"] not in WIDE_IMM:
        return list(toks)
    if f["id"] == 0x00 and f["ty"] == 0:
        return [bool(toks[0])] if toks else [False]
    # One pad rule, shared with the disassembler.
    raw = disasm.immediate(addr, toks)
    want = 4 if f["id"] == 0x02 else 4 * f["comps"]
    if len(raw) < want:
        raise Unsupported("opcode %04X at %d: %d immediate bytes, wanted %d"
                          % (op, addr, len(raw), want))
    body = raw[:want]
    # A uid is an integer however the instruction types its result.
    kind = "i" if f["id"] == 0x02 else ("f" if f["ty"] == 1 else "i")
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
              "                        select, rand, cartesian, lerp, sbs_mod,\n"
              "                        cache_read, cache_write)\n")

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
         0x2F: "lerp", 0x30: "minimum", 0x31: "maximum", 0x32: "rand"}

PY_FUNCS = {"abs": "np.abs", "floor": "np.floor", "ceil": "np.ceil", "cos": "np.cos",
            "exp": "np.exp",
            "sin": "np.sin", "sqrt": "np.sqrt", "log": "np.log", "exp2": "np.exp2",
            "atan2": "np.arctan2", "minimum": "np.minimum", "maximum": "np.maximum",
            "dot": "np.dot"}

PY_LOGIC = {"and": "np.logical_and", "or": "np.logical_or"}


#: Operations whose meaning is not established. Operand shape comes from the
#: disassembler's IMM table where it names one; the rest take ordinary value numbers
#: throughout, verified at 0% "operand >= own index" over the corpus. 0x1E and 0x2A were
#: here and have since been named in OPCODES.md as `neq` and `exp`; 0x06 was here and is
#: now handled explicitly above -- its meaning is known even though evaluating it needs
#: an architecture this transpiler does not have yet.
#:
#: 0x35 was briefly here as "log2" in a concurrent edit with no numeric proof behind it --
#: every avenue tried (literal constants, the 22 size expressions that use it, all of
#: which trace back to a sampler or cache read with no way to get a hand-computable
#: value) came up empty. Circumstantial support is real (unary; 99.5%+ of 3,903 instances
#: feed straight into ceil/floor; 73% fed by an int-to-float cvt) and is recorded as such
#: in OPCODES.md, but "probably" is not the bar every other name in this table clears.
#: Emitting it as log2 would make the transpiler compute a plausible, silently unverified
#: number for 3,903 instructions -- exactly the failure mode the cache_read/cache_write
#: raise exists to avoid, just without the raise.
#:
#: 0x36 briefly named "pow" in FUNCS the same way, with no investigation behind it at all
#: that I've found -- no commit, no test, no corpus measurement, and FUNCS is checked
#: before UNNAMED in the dispatch below, so the membership here was dead code while it
#: sat in FUNCS: it would have silently emitted `pow(...)` regardless of this comment.
UNNAMED = {0x35, 0x36}


class Unsupported(Exception):
    pass


def transpile(data, start, end, backend="python", name="program", result=None):
    """Return target source for the program at `start`.

    `result` names the value number to return, for reading a sub-expression out of a
    larger program; the default is the program's final value.
    """
    be = BACKENDS[backend]()
    lines = []
    for k, addr, op, toks in disasm.decode(data, start, end):
        f = disasm.fields(op)
        oid, ty, ncomp = f["id"], f["ty"], f["comps"]
        v = be.var(k)

        def arg(i):
            if i >= len(toks):
                raise Unsupported("opcode %04X at %d: wanted operand %d of %d"
                                  % (op, addr, i, len(toks)))
            return be.var(toks[i])

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
            lines.append("    slots[%d] = %s" % (toks[1], arg(0)))
            rhs = arg(0)
        elif oid == 0x0C:                                  # sequence
            rhs = arg(len(toks) - 1)
        elif oid == 0x0D:                                  # construct vector, by
            # concatenation: always exactly two operands whatever the result width.
            rhs = be.call("vec", [arg(i) for i in range(len(toks))])
        elif oid == 0x0F:                                  # build a 4-vector from four
            # scalars. Probable rather than confirmed -- 28 instances, all terminal, all
            # in `levels`, all of the shape (x, x, x, 1). See OPCODES.md.
            rhs = be.call("vec", [arg(i) for i in range(len(toks))])
        elif oid == 0x10:                                  # swizzle
            mask = swizzle_mask(toks[1], ncomp)
            rhs = be.call("swizzle", [arg(0), str(mask)])
        elif oid == 0x11:                                  # type conversion
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
            sym = BINOP[oid]
            if backend == "python" and sym in PY_LOGIC:
                rhs = be.call(PY_LOGIC[sym], [arg(0), arg(1)])
            else:
                rhs = be.binop(sym, arg(0), arg(1))
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

        lines.append("    %s = %s" % (v, rhs))

    if not lines:
        raise Unsupported("empty program")
    last = be.var(k if result is None else result)
    body = "\n".join(lines)
    return ("%s\ndef %s(inputs=None, slots=None):\n"
            "    inputs = inputs or {}\n"
            "    slots = slots if slots is not None else {}\n"
            "%s\n    return %s\n" % (be.header, name, body, last))
