"""Tests for the bytecode transpiler.

Most claims in this project are distribution matches: a decode is believed because the
numbers it produces line up with something independently known. The transpiler is the
one artifact that can be tested outright -- transpile a program whose algorithm is known,
run it, and compare against the closed form. These are those tests.

Two kinds:

* **Structural** tests need no corpus and always run. They cover the immediate decoding,
  which is where two bugs have already been found.
* **Known-algorithm** tests need a specimen. The corpus is not in this repository, so
  they skip when a specimen is absent rather than failing.

Point `SBS_CORPUS` at a directory holding unpacked `.sbsar` contents:

    SBS_CORPUS=~/substance python3 test_transpile.py
    SBS_CORPUS=~/substance pytest test_transpile.py

Without it the search falls back to the repository's parent directory.

**What these tests catch, measured.** A test nobody has tried to break is not evidence.
Mutating one entry of the operation table and re-running:

    lteq -> lt          caught      exp2 -> exp     caught
    sub  -> add         caught      div  -> mul     caught
    ln   -> exp         caught      pad rule broken caught (5 of 8 fail)

    gt   -> gteq        NOT caught
    eq   -> neq         NOT caught
    min  -> max         NOT caught

The misses are honest limits rather than oversights. `gt -> gteq` is undetectable here
because sRGB is *continuous* at its threshold: both branches meet, so which side of the
comparison the boundary falls on changes the result by less than the tolerance. That
`lteq -> lt` IS caught is an accident of the encode specimen -- its threshold constant is
0.00031308, ten times the standard value, which makes the function discontinuous there.
`eq` and `min`/`max` are simply not reached: neither program contains them. Covering
those needs a third specimen with a known algorithm that uses them.
"""
import glob
import os
import struct
import sys

import disasm
import sbsasm
import transpile

# ---------------------------------------------------------------------------
# specimens

def corpus_roots():
    env = os.environ.get("SBS_CORPUS")
    if env:
        return [env]
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.dirname(here)]


def find_specimen(basename):
    """Locate one unpacked assembly by file name, or None."""
    for root in corpus_roots():
        hits = sorted(glob.glob(os.path.join(root, "**", basename), recursive=True))
        if hits:
            return hits[0]
    return None


class Skip(Exception):
    """A specimen this test needs is not present."""


def load(basename):
    path = find_specimen(basename)
    if path is None:
        raise Skip("%s not found under %s" % (basename, ", ".join(corpus_roots())))
    return sbsasm.Assembly(path)


def numpy_or_skip():
    try:
        import numpy
    except ImportError:
        raise Skip("numpy is not installed")
    return numpy


# ---------------------------------------------------------------------------
# structural: the immediate decoding

def test_pad_follows_token_count():
    """A 4-byte immediate needs an even number of u16 tokens, so an odd count above
    one is the alignment pad. One token is never padded -- those are the u16
    immediates (sysvar, get, 0x03, bool constants), which have no padded form."""
    assert disasm.pad_bytes([0]) == 0, "a single token is an immediate, not a pad"
    assert disasm.pad_bytes([0, 0]) == 0
    assert disasm.pad_bytes([0, 0, 0]) == 2
    assert disasm.pad_bytes([0, 0, 0, 0]) == 0
    assert disasm.pad_bytes([0, 0, 0, 0, 0]) == 2
    assert disasm.pad_bytes([0] * 9) == 2


def test_immediate_strips_the_pad():
    """The padded and unpadded forms of one constant must decode identically.

    Compared against the float32 round-trip, not the literal: float32 holds
    0.00031308 only to 3.25e-12, and asserting on the literal tests the storage
    format rather than the pad.
    """
    value = 0.00031308
    stored = struct.unpack("<f", struct.pack("<f", value))[0]
    packed = struct.unpack("<2H", struct.pack("<f", value))
    bare = disasm.immediate(0x1002, list(packed))                 # unpadded form
    padded = disasm.immediate(0x1000, [0] + list(packed))         # padded form
    assert struct.unpack_from("<f", bare)[0] == stored
    assert struct.unpack_from("<f", padded)[0] == stored


def test_uid_reads_past_the_pad():
    want = 3445188334
    packed = list(struct.unpack("<2H", struct.pack("<I", want)))
    assert disasm.uid(0x1002, packed) == want
    assert disasm.uid(0x1000, [0] + packed) == want


def test_swizzle_mask_is_two_bits_per_component():
    assert transpile.swizzle_mask(0, 1) == [0]
    assert transpile.swizzle_mask(1, 1) == [1]
    assert transpile.swizzle_mask(2, 1) == [2]
    assert transpile.swizzle_mask(36, 3) == [0, 1, 2]      # 0b100100, identity xyz


def test_while_carries_no_immediate():
    """0x0B was annotated as carrying an iteration cap in position 0. It does not:
    every operand is a value reference. See OPCODES.md, "0x0B is a loop"."""
    assert disasm.IMM.get(0x0B) == ()


def test_0x35_stays_unnamed_until_proven():
    """0x35 has real circumstantial support for 'log2' (unary, 99.5%+ of 3,903
    instances feed straight into ceil/floor, 73% fed by an int-to-float cvt) but no
    numeric proof -- every literal-constant trace and all 22 size-expression uses
    bottom out at a sampler or cache read with no hand-computable value. OPCODES.md
    records it as probable, not confirmed. This test is the guard against a future
    edit asserting the name here before that proof exists: it should start failing
    the day someone actually gets one, not before."""
    assert disasm.name(0x0535) == "op35"
    data = struct.pack("<6H", 2, 0x0900, 0, 0, 0x0535, 0)
    source = transpile.transpile(data, 0, len(data), "python", "_probe")
    assert "op35(v0)" in source


def test_op06_takes_a_value_then_an_index():
    """Position 0 is an ordinary value reference (0.0% impossible over the corpus),
    position 1 is an index -- the shape of `set` and `swizzle`, not of `sysvar`."""
    assert disasm.IMM.get(0x06) == (1,)


# ---------------------------------------------------------------------------
# known algorithms

#: `LGMLtools__sRGB_colorchart` implements the encode direction three times over,
#: unrolled per colour channel, at this offset. Its threshold constant is 0.00031308 --
#: ten times the standard 0.0031308, which is a property of the specimen and not a
#: decode error. Testing against the textbook value instead gives 0.0224.
SRGB_ENCODE = ("sRGB_colorchart.sbsar.sbsasm", 0x23AA8, 0.00031308)

#: `DLG-Tools__Embroidery_Legacy` implements the inverse, as a block inside a larger
#: program; value 74 is the block's output. This specimen was never used to build the
#: instruction table, so it is an out-of-sample check.
SRGB_DECODE = ("Embroidery_Legacy.sbsar.sbsasm", 0x1AFC, 74, 0.04045)

TOLERANCE = 1e-6        # float32 rounding is ~1e-7; anything larger is a real error

#: Deviations recorded by the known-algorithm tests, for the standalone report. The
#: tests themselves only assert -- returning a value from a test is a pytest error.
DEVIATIONS = {}


def program_constants(asm, start, end, lo=0.0, hi=1.0):
    """Every float constant in a program that falls inside the sampled range."""
    found = set()
    for _k, addr, op, toks in disasm.decode(asm.data, start, end):
        fields = disasm.fields(op)
        if fields["id"] != 0x00 or fields["ty"] != 1:
            continue
        for value in disasm.floats(addr, toks):
            if lo <= value <= hi:
                found.add(value)
    return found


def _run(asm, start, result=None, samples=200000, boundaries=()):
    """Transpile one program and evaluate it over a linear ramp fed to every sampler.

    Every float constant the program contains is inserted as a sample point, plus one
    ulp either side. A plain linspace never lands on a piecewise function's threshold,
    so it cannot tell `<=` from `<` -- mis-naming lteq as lt was invisible until these
    were added. Taking the points from the program's own constants rather than from a
    hardcoded list means the thresholds are exercised at exactly the values the file
    holds, whatever they are.
    """
    np = numpy_or_skip()
    import sbsruntime

    end = asm.program_span(start)
    assert end is not None, "no program at 0x%X" % start
    src = transpile.transpile(asm.data, start, end, "python", "_probe", result=result)

    ramp = np.linspace(1e-7, 1.0, samples)
    for edge in set(boundaries) | program_constants(asm, start, end):
        around = [np.nextafter(edge, -np.inf), edge, np.nextafter(edge, np.inf)]
        ramp = np.concatenate([ramp, np.array(around, dtype=ramp.dtype)])
    ramp = np.sort(ramp)
    frame = np.stack([ramp, ramp, ramp, np.ones(len(ramp))], axis=-1)
    for index in range(8):
        sbsruntime.SAMPLERS[index] = lambda pos, f=frame: f

    scope = {}
    # Sample points include 0 and the program's own constants, so log(0) and similar
    # are expected at the edges; the comparison below is what judges the result.
    with np.errstate(all="ignore"):
        exec(compile(src, "<transpiled>", "exec"), scope)
        out = np.asarray(scope["_probe"]())
    return ramp, (out[:, 0] if out.ndim > 1 else out)


def test_srgb_encode():
    """The encode direction, decoded to the file's own constants."""
    np = numpy_or_skip()
    name, start, threshold = SRGB_ENCODE
    # The program holds the threshold as float32. Comparing against the float64 literal
    # disagrees for values between the two, which boundary sampling lands on exactly.
    threshold = float(np.float32(threshold))
    asm = load(name)
    ramp, got = _run(asm, start, boundaries=(threshold,))
    with np.errstate(all="ignore"):
        want = np.where(ramp <= threshold,
                        12.92 * ramp, 1.055 * np.power(ramp, 1 / 2.4) - 0.055)
    deviation = float(np.abs(got - want).max())
    DEVIATIONS["test_srgb_encode"] = deviation
    assert deviation < TOLERANCE, "max deviation %.3g" % deviation


def test_srgb_decode():
    """The inverse, on a specimen the instruction table was not built from."""
    np = numpy_or_skip()
    name, start, result, threshold = SRGB_DECODE
    threshold = float(np.float32(threshold))
    asm = load(name)
    ramp, got = _run(asm, start, result=result, boundaries=(threshold,))
    with np.errstate(all="ignore"):
        want = np.where(ramp <= threshold,
                        ramp / 12.92, np.power((ramp + 0.055) / 1.055, 2.4))
    deviation = float(np.abs(got - want).max())
    DEVIATIONS["test_srgb_decode"] = deviation
    assert deviation < TOLERANCE, "max deviation %.3g" % deviation


# ---------------------------------------------------------------------------

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = skipped = failed = 0
    for test in tests:
        try:
            test()
        except Skip as why:
            print("  SKIP  %-34s %s" % (test.__name__, why))
            skipped += 1
        except AssertionError as why:
            print("  FAIL  %-34s %s" % (test.__name__, why))
            failed += 1
        except Exception as why:
            # A broken decode raises as often as it returns a wrong number -- report it
            # as a failure rather than letting one test abort the run.
            print("  ERROR %-34s %s: %s" % (test.__name__, type(why).__name__, why))
            failed += 1
        else:
            deviation = DEVIATIONS.get(test.__name__)
            note = "max deviation %.3g" % deviation if deviation is not None else ""
            print("  ok    %-34s %s" % (test.__name__, note))
            passed += 1
    print("\n%d passed, %d skipped, %d failed" % (passed, skipped, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
