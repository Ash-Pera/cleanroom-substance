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


def test_while_emits_a_loop_that_counts():
    """A `while` must not merely transpile -- it must run the right number of times.

    Synthetic program, so no corpus is needed. Slot 0 is a counter and slot 1 a limit:

        init       slot0 = 0
        condition  slot0 >= slot1
        body       slot0 = slot0 + 1

    which must leave slot 0 equal to the limit, for any limit. That tests the three
    things the emitter can get wrong independently: the initialiser running once rather
    than per iteration, the condition being a TERMINATION test rather than a
    continuation one, and the body being inside the loop rather than before it.
    """
    import numpy as np
    # const 0 ; set slot0 ; get slot0 ; get slot1 ; gteq ; get slot0 ; const 1 ; add ;
    # set slot0 ; while(init=1, cond=4, body=8)
    words = [
        10,
        0x0900, 0, 0,          # v0 = const 0.0
        0x0907, 0, 0,          # v1 = set slot0 = v0     <- init
        0x0504, 0,             # v2 = get slot0
        0x0504, 1,             # v3 = get slot1
        0x085D, 2, 3,          # v4 = eq(v2, v3)         <- condition
        0x0504, 0,             # v5 = get slot0
        0x0900, 0x0000, 0x3F80,  # v6 = const 1.0
        0x0912, 5, 6,          # v7 = add(v5, v6)
        0x0907, 7, 0,          # v8 = set slot0 = v7     <- body
        0x150B, 1, 4, 8, 0, 0,   # v9 = while(init, cond, body, pad, pad)
    ]
    data = struct.pack("<%dH" % len(words), *words)
    src = transpile.transpile(data, 0, len(data), "python", "_loop")
    assert "for _it" in src, "no loop emitted"
    g = {}
    exec(src, g)
    for limit in (0, 1, 5, 17):
        slots = {0: np.array([[0.0]], np.float32), 1: np.array([[float(limit)]], np.float32)}
        g["_loop"](inputs={}, slots=slots)
        got = float(np.asarray(slots[0]).ravel()[0])
        assert got == limit, "limit %d: slot0 ended at %r" % (limit, got)


def test_log2_is_named_and_transpiled():
    """The source-matched unary 0x35 operation transpiles as log2."""
    data = struct.pack("<6H", 2, 0x0900, 0, 0, 0x0535, 0)
    source = transpile.transpile(data, 0, len(data), "python", "_probe")
    assert disasm.name(0x0535) == "log2"
    assert "v1 = np.log2(v0)" in source


def test_log2_matches_ie_pcloud_source():
    """Structural proof, not a numeric one: the compiled shape must match the source
    graph node-for-node, and the same four-instruction program must recur once per
    graph input that declares the outputsize override -- a coincidence in decode
    would not repeat identically four times."""
    name, start = LOG2_SOURCE_MATCH
    asm = load(name)
    end = asm.program_span(start)
    assert end is not None, "no program at %d" % start
    rows = list(disasm.decode(asm.data, start, end))
    assert [disasm.name(op) for _k, _addr, op, _toks in rows] == [
        "inputref", "swizzle", "log2", "cvt",
    ]
    assert disasm.fields(rows[2][2])["id"] == 0x35

    refs = asm.referenced_programs()
    matches = 0
    for p_start, p_end in refs.items():
        r = list(disasm.decode(asm.data, p_start, p_end))
        if len(r) == 4 and [disasm.name(op) for _k, _a, op, _t in r] == [
            "inputref", "swizzle", "log2", "cvt",
        ]:
            matches += 1
    assert matches == 4, "expected 4 identical copies, found %d" % matches


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

#: `LeakingSubstance004` implements the same inverse transform as SRGB_DECODE, but via
#: op36(x, 2.4) directly rather than the ln/exp2 idiom -- the proof that op36 is `pow`.
#: `RoadSubstance002` and `RoadLinesSubstance002` carry byte-identical copies of this
#: program; this specimen is arbitrary among the three.
SRGB_DECODE_VIA_POW = ("LeakingSubstance004_COMPILED.sbsasm", 460092, 0.04045)

#: `ie_pcloud`'s source computes a graph input's outputsize override as
#: get_float3("#pcloud_meta") -> swizzle2 -> log2 -> toint2, a node-for-node match
#: (not a numeric one -- there is no independently known input value to check a result
#: against) to four identical compiled programs, one per graph input with this override.
#: Reachable only through the permissive whole-file scan, not any record's own slots --
#: it is a graph-input default expression, not filter logic, the same category as the
#: version-2 prologue's programs.
LOG2_SOURCE_MATCH = ("ie_pcloud.sbsasm", 6656)

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


def test_pow_via_srgb_decode():
    """0x36 = pow, proved the same way ln/exp2 was: the same inverse-sRGB closed form,
    computed here with op36(x, 2.4) instead of ln/div/exp2, on a specimen SRGB_DECODE
    never touches."""
    np = numpy_or_skip()
    name, start, threshold = SRGB_DECODE_VIA_POW
    threshold = float(np.float32(threshold))
    asm = load(name)
    ramp, got = _run(asm, start, boundaries=(threshold,))
    with np.errstate(all="ignore"):
        want = np.where(ramp <= threshold,
                        ramp / 12.92, np.power((ramp + 0.055) / 1.055, 2.4))
    deviation = float(np.abs(got - want).max())
    DEVIATIONS["test_pow_via_srgb_decode"] = deviation
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
