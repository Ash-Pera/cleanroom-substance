#!/usr/bin/env python3
"""Checks for filter 17, `text`.

    python3 -m pytest -q tools/render2/test_text.py

Three kinds, in decreasing order of how much they are worth:

  SOURCE-ARBITRATED. Three permitted paired sources declare a `text` node and their
  compiled twins are in the corpus, so the string, the position and the font size can each
  be checked against the value the package's own `.sbs` states. That is the same standard
  `sourcematch.py` sets and it is the only kind here that could name a field.

  STRUCTURAL. The resource walk -- the font payload's stated length landing exactly on an
  offset another record of the same file names as its string -- and the value block order,
  asserted as the DISCRIMINATOR rather than as the answer: the ascending reading
  `model.View` uses for every other filter is asserted to be the one that puts an
  unrenderable font size on all fourteen records that set all three fields, so if someone
  reorders `W1_TEXT` this fails with the reason.

  RENDER. That the filter produces a canvas of the right shape and puts ink where the
  record says. No pixel here is compared to ground truth, because no package containing a
  `text` record ships an exported map -- see `test_no_reference_exists`, which asserts that
  absence so that the day one arrives, this file says so instead of staying quiet.

Every test SKIPS rather than fails when its specimen is absent: the corpus is not in this
repository.
"""
import os
import re
import struct
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # see __init__.py: this package goes LAST

import corpus                                                        # noqa: E402
import sbsasm                                                        # noqa: E402
import filters as filters_mod                                        # noqa: E402
import model                                                         # noqa: E402
import text as text_mod                                              # noqa: E402
from engine import Context                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))

# THE HOOK, IF IT IS NOT ALREADY THERE. `filters.py` was owned by another worktree when
# this landed and the registration is delivered as a patch; `setdefault` means this file
# passes both before and after that patch is applied, and never installs a second copy over
# the real one.
filters_mod.FILTERS.setdefault('text', text_mod.f_text)

#: The corpus files carrying a filter-17 record, by basename. Thirteen of 437.
SPECIMENS = (
    'TimelineExample.sbsar.sbsasm', 'UnitTests.sbsar.sbsasm',
    'RuntimeExample.sbsar.sbsasm', 'Do Not Enter.sbsasm', 'One Way.sbsasm',
    'Stop_Sign.sbsasm', 'Yield.sbsasm', 'Speed Limit.sbsasm',
    'Lane Markings - Stop Ahead.sbsasm', 'RoadLinesSubstance002_COMPILED.sbsasm',
    'RoadSubstance002_COMPILED.sbsasm', 'MetalPlatesSubstance003_COMPILED.sbsasm',
    'PaymentCardSubstance001_COMPILED.sbsasm',
)

#: The permitted paired sources that declare a `text` node, and the twin each one compiles
#: to. Checked by `test_a_source_that_states_a_text_parameter_finds_it_in_the_twin`; the
#: provenance rule is applied to each one before it is read.
PAIRS = (
    ('substance-for-unity-extensions__TimelineExample.sbs', 'TimelineExample.sbsar.sbsasm'),
    ('substance-for-unity-extensions__RuntimeExample.sbs', 'RuntimeExample.sbsar.sbsasm'),
    ('substance-for-unity-extensions__UnitTests.sbs', 'UnitTests.sbsar.sbsasm'),
)

_PATHS = None


def _skip(reason):
    """A skip a RUNNER can see -- `print(); return` is a silent pass under pytest."""
    try:
        import pytest
    except ImportError:
        pass
    else:
        pytest.skip(reason)
    print('SKIP ' + reason)


def specimens():
    """{basename: path} for the corpus files that carry a filter-17 record."""
    global _PATHS
    if _PATHS is None:
        want = set(SPECIMENS)
        _PATHS = {os.path.basename(p): p for p in corpus.paths()
                  if os.path.basename(p) in want}
    return _PATHS


def _asm(name):
    p = specimens().get(name)
    return None if p is None else sbsasm.Assembly(p)


def _views(asm):
    return [model.View(asm, r) for r in asm.records if r.filter_id == 17]


def _source(name):
    """A permitted paired source, or None. The exclusion rule runs BEFORE the read."""
    for d in ('pairs2', 'pairs5', 'pairs', 'pairs3', 'pairs4', 'pairs6'):
        p = os.path.join(ROOT, d, name)
        if os.path.exists(p):
            body = open(p, encoding='utf-8', errors='replace').read()
            if '<author v="Allegorithmic"' in body:
                return None             # the rule in README.md, applied not described
            return body
    return None


# ---------------------------------------------------------------------------
# Source-arbitrated
# ---------------------------------------------------------------------------

_TEXT_NODE = re.compile(r'<compFilter><filter v="text"/><parameters>(.*?)</parameters>')


def _stated(body):
    """[{parameter: value or DYNAMIC}] for every `text` node a source declares."""
    out = []
    for block in _TEXT_NODE.findall(body):
        got = {}
        for m in re.finditer(r'<name v="([^"]+)"/><relativeTo v="\d+"/><paramValue>'
                             r'(?:<constantValue[A-Za-z0-9]+ v="([^"]*)"/>'
                             r'|(<dynamicValue>))', block):
            got[m.group(1)] = 'DYNAMIC' if m.group(3) else m.group(2)
        out.append(got)
    return out


def test_a_source_that_states_a_text_parameter_finds_it_in_the_twin():
    """The naming standard: a `.sbs` says `fontsize 0.3`, and one slot of its twin holds it.

    This is what binds the three `w1` fields to names, and each binding is one file:

      `fontsize`   TimelineExample states 0.300000012 and nothing else numeric. Its record
                   sets ONE parameter bit and its parameter block is ONE word.
      `position`   RuntimeExample states it as a `get_float2` and states `text` as a
                   `get_string`; its record sets exactly two program bits and the program
                   at the `position` slot is `inputref` on the float2 graph input the
                   manifest calls `textPosition`.
      `text`       UnitTests states two constants (`True`, `False`) and one dynamic, and
                   the two constants come back from the resource segment verbatim.
    """
    checked = 0
    for src_name, asm_name in PAIRS:
        body = _source(src_name)
        asm = _asm(asm_name)
        if body is None or asm is None:
            continue
        nodes = _stated(body)
        views = _views(asm)
        assert len(views) == len(nodes), \
            '%s: %d text nodes, %d text records' % (src_name, len(nodes), len(views))
        ctx = Context(asm)
        for want in nodes:
            # Match on the STATED value, not on order: a node and a record are paired by
            # what they agree about, which is the whole method.
            if 'fontsize' in want and want['fontsize'] != 'DYNAMIC':
                f = float(want['fontsize'])
                assert any(v.baked('fontsize') is not None
                           and abs(v.baked('fontsize') - f) < 2e-4 for v in views), \
                    '%s states fontsize %s and no record holds it' % (src_name, f)
                checked += 1
            if want.get('position') == 'DYNAMIC':
                assert any(v.program('position') is not None for v in views), \
                    '%s states position dynamic and no record points at a program' % src_name
                checked += 1
            if 'text' in want and want['text'] != 'DYNAMIC':
                got = {text_mod.text_of(ctx, v)[0] for v in views}
                assert want['text'] in got, \
                    '%s states text %r; the records hold %r' % (src_name, want['text'], got)
                checked += 1
    if not checked:
        return _skip('test_a_source_that_states_a_text_parameter_finds_it_in_the_twin: '
                     'no permitted paired source with a text node')
    # Four: TimelineExample's fontsize, RuntimeExample's dynamic position, and UnitTests'
    # two constant strings. The three sources state nothing else a compiled record can be
    # checked against -- `fontdata` has no compiled counterpart the walk reads.
    assert checked >= 4, 'only %d source statements checked' % checked
    print('ok  test_a_source_that_states_a_text_parameter_finds_it_in_the_twin (%d)'
          % checked)


def test_a_dynamic_string_names_a_graph_input_the_manifest_declares():
    """`w1` bit 1 set means slot 3 is a UID, not an offset, and the manifest knows it.

    The two arms are indistinguishable by value -- both are a 32-bit word -- so a reader
    that guessed from the number would be right about half the time and silent about the
    rest. This asserts the bit decides, in both directions.
    """
    seen_input = seen_resource = 0
    for name in SPECIMENS:
        asm = _asm(name)
        if asm is None:
            continue
        ctx = Context(asm)
        for v in _views(asm):
            s, source = text_mod.text_of(ctx, v)
            if v.words[1] & 0x2:
                assert source in ('input', 'missing'), \
                    '%s rec%d: bit 1 set but the string came from %r' \
                    % (name, v.index, source)
                if source == 'input':
                    seen_input += 1
                    assert v.words[3] in text_mod.string_inputs(asm)
            else:
                assert source == 'resource', \
                    '%s rec%d: bit 1 clear and slot 3 is not a string resource' \
                    % (name, v.index)
                seen_resource += 1
    if not (seen_input or seen_resource):
        return _skip('test_a_dynamic_string_names_a_graph_input: no specimen')
    assert seen_resource >= 20 and seen_input >= 5, \
        'only %d resource / %d input strings seen' % (seen_resource, seen_input)
    print('ok  test_a_dynamic_string_names_a_graph_input_the_manifest_declares '
          '(%d resource, %d input)' % (seen_resource, seen_input))


# ---------------------------------------------------------------------------
# Structural
# ---------------------------------------------------------------------------

def test_the_font_payload_is_an_sfnt_whose_stated_length_is_exact():
    """Slot 4 addresses `[hash][length][sfnt]`, and `length` is structural, not a guess.

    Two claims of different strengths, and the weaker one is asserted for all payloads
    because THE FIRST VERSION OF THIS TEST ASSERTED THE STRONGER ONE FOR ALL AND FAILED on
    `TimelineExample`. Six of the fourteen payloads are followed by what looks like an
    offset table rather than a string.

      all fourteen  the payload lies wholly inside the resource segment: the magic is an
                    sfnt magic and `offset + length <= body_lo`.
      eight         `offset + length` is EXACTLY the string resource A RECORD OF THAT FILE
                    NAMES -- the arbiter being slot 3 of some text record, which is an
                    independent statement of where a string starts, not this reader's
                    opinion. One word either side names nothing. That is what makes the
                    length a reading rather than a coincidence.
    """
    payloads, chained = set(), 0
    for name in SPECIMENS:
        asm = _asm(name)
        if asm is None:
            continue
        views = _views(asm)
        # THE INDEPENDENT STATEMENT OF WHERE A STRING IS: every offset a text record of
        # this file names at slot 3, taken from the records and not from a scan.
        named = {v.words[3] + 52 for v in views if not (v.words[1] & 0x2)}
        for v in views:
            got = text_mod.embedded_font(asm, v)
            assert got is not None, '%s rec%d: slot 4 is not a font payload' % (name, v.index)
            off, length, magic = got
            assert magic in (b'\x00\x01\x00\x00', b'ttcf'), \
                '%s rec%d: magic %r' % (name, v.index, magic)
            assert off + length <= asm.body_lo, \
                '%s rec%d: the payload runs past the resource segment' % (name, v.index)
            if (id(asm), off) in payloads:
                continue
            payloads.add((id(asm), off))
            end = off + length
            if end in named:
                chained += 1
                assert text_mod.read_string(asm, end) is not None
                assert (end - 4) not in named and (end + 4) not in named, \
                    '%s rec%d: a record names an offset on both sides of 0x%x, so landing ' \
                    'on one says nothing' % (name, v.index, end)
    if not payloads:
        return _skip('test_the_font_payload_is_an_sfnt: no specimen')
    assert chained >= 6, \
        'only %d of %d font payloads chain exactly to a string resource' \
        % (chained, len(payloads))
    print('ok  test_the_font_payload_is_an_sfnt_whose_stated_length_is_exact '
          '(%d payloads, %d chaining exactly)' % (len(payloads), chained))


def test_the_value_block_is_not_in_ascending_mask_order():
    """The discriminator, asserted as a discriminator.

    `W1_TEXT` lists `matrix22` first, which is NOT the ascending-mask order every other
    filter uses, and the module docstring gives the evidence. Here it is as a test that can
    fail: read the same words in ascending order and `fontsize` must come back UNRENDERABLE
    on every record that sets all three fields, because under that order the word is the
    matrix's `c` component. If it ever stops being unrenderable this ordering needs
    re-arguing.

    THE FIRST VERSION OF THIS ASSERTED `== 0.0` AND FAILED, 3 of 14. It is exactly zero on
    the eleven records whose matrix is diagonal and 0.0033 / 0.0033 / -0.627 on the three
    whose matrix is a rotation or a general one. The corrected claim is the one that was
    always true and is still decisive: none of the fourteen draws anything.
    """
    zero, nonzero, matrices = 0, 0, []
    for name in SPECIMENS:
        asm = _asm(name)
        if asm is None:
            continue
        for v in _views(asm):
            w1 = v.words[1]
            if not (w1 & 0x400 and w1 & 0x40 and w1 & 0x100):
                continue
            start = v.params['matrix22'].slot
            asc = struct.unpack('<f', struct.pack('<I', v.words[start + 2]))[0]
            if asc == 0.0:
                zero += 1
            else:
                nonzero += 1
            assert asc <= 0.01, \
                '%s rec%d: the ascending reading gives a font size of %r, which would ' \
                'draw -- the ordering argument needs re-taking' % (name, v.index, asc)
            m = v.baked('matrix22')
            fs = v.baked('fontsize')
            assert 0.0 < fs <= 4.0, \
                '%s rec%d: this order gives fontsize %r' % (name, v.index, fs)
            matrices.append(m)
    if not matrices:
        return _skip('test_the_value_block_is_not_in_ascending_mask_order: no specimen')
    assert zero >= 10 and zero + nonzero == 14, \
        'the ascending reading no longer puts an exact zero font size on the diagonal ' \
        'records (%d zero of %d) -- the ordering argument needs re-taking' \
        % (zero, zero + nonzero)
    # AND THE MATRIX IS A MATRIX. Five of the six files hold a diagonal one; `Speed Limit`
    # holds (cos, -sin, sin, cos). Both are things a WRONG placement does not produce.
    diag = sum(1 for m in matrices if m[1] == 0.0 and m[2] == 0.0)
    rot = sum(1 for m in matrices
              if m[1] != 0.0 and abs(m[0] - m[3]) < 1e-6 and abs(m[1] + m[2]) < 1e-6)
    assert diag + rot >= len(matrices) - 1, \
        'only %d of %d matrices are diagonal or a rotation' % (diag + rot, len(matrices))
    print('ok  test_the_value_block_is_not_in_ascending_mask_order '
          '(%d records, %d diagonal, %d rotation)' % (len(matrices), diag, rot))


def test_the_legend_covers_every_field_the_format_charges_for():
    """No `w1` field of filter 17 is declared, charged a word, and unnamed.

    This is the `normal` failure shape one filter over: an undeclared field sitting inside
    an end-anchored block moves every named parameter after it. `legend.json` states which
    fields cost words; `W1_TEXT` must name all of them.

    THE KEYS ARE BIT OFFSETS (SPEC 7.3), so a field's presence mask is `3 << offset`. This
    used to read `costs.json`'s field INDICES on an even grid and write `3 << (2 * j)`;
    filter 17's fields are at bits 6, 8 and 10 either way, but the frame is the one the
    rest of the model now uses.
    """
    import json
    leg = json.load(open(os.path.join(ROOT, 'tools', 'legend.json'), encoding='utf-8'))
    entry = leg.get('17')
    if entry is None:
        return _skip('test_the_legend_covers_every_field: legend.json has no filter 17')
    covered, _cls = model._covered_bits(17)
    # A cell of kind 0 costs nothing baked; every other kind costs at least one word, and a
    # program pointer or an edge slot costs one whatever the kind is.
    charged = {int(j) for j, kind in entry.get('w1', {}).items() if kind != 0}
    missing = {j for j in charged if not ((3 << j) & covered)}
    assert not missing, \
        'filter 17 charges words for w1 fields %r and no name covers them' % sorted(missing)
    print('ok  test_the_legend_covers_every_field_the_format_charges_for (%d fields)'
          % len(charged))


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def test_every_text_record_renders_at_the_records_own_shape():
    """The contract `engine` enforces: (H, W, 1) greyscale or (H, W, 4) colour, finite.

    Not a fidelity check. What it catches is the thing that would take a whole file down --
    a filter that raises, returns the wrong channel count, or emits a NaN into a blend.
    """
    shapes, inked = 0, 0
    for name in SPECIMENS:
        asm = _asm(name)
        if asm is None:
            continue
        ctx = Context(asm, cap=64)
        for v in _views(asm):
            out = np.asarray(text_mod.f_text(ctx, v))
            W, H = v.size(64)
            want = 4 if v.colour else 1
            assert out.shape == (H, W, want), \
                '%s rec%d: %r, wanted %r' % (name, v.index, out.shape, (H, W, want))
            assert np.all(np.isfinite(out)), '%s rec%d: non-finite' % (name, v.index)
            assert out.min() >= 0.0 and out.max() <= 1.0
            shapes += 1
            if out.max() > 0.5:
                inked += 1
            assert v.index in ctx.low_confidence, \
                '%s rec%d: the polarity and the face are both assumed and the record is ' \
                'not marked' % (name, v.index)
    if not shapes:
        return _skip('test_every_text_record_renders_at_the_records_own_shape: no specimen')
    # AN EMPTY STRING IS A LEGITIMATE BLANK -- `Speed Limit` record 1049 is one -- so this
    # is a floor, not an equality.
    assert inked >= shapes * 0.6, 'only %d of %d text records drew anything' % (inked, shapes)
    print('ok  test_every_text_record_renders_at_the_records_own_shape (%d, %d inked)'
          % (shapes, inked))


def test_the_ink_lands_where_the_record_says():
    """The two-line stacks, as a position check that does not need a reference render.

    `Speed Limit` holds SPEED at y = -0.22 and LIMIT at y = -0.03 on one 2048 canvas each;
    `Do Not Enter` holds DO NOT at -0.10 and ENTER at +0.23. The centroid of the ink must
    follow, and the ORDER must follow -- which is exactly what the ascending reading of the
    value block gets wrong, since under it both records of a pair sit at the same y.
    """
    cases = (('Speed Limit.sbsasm', 'SPEED', 'LIMIT'),
             ('Do Not Enter.sbsasm', 'DO NOT', 'ENTER'))
    checked = 0
    for name, upper, lower in cases:
        asm = _asm(name)
        if asm is None:
            continue
        ctx = Context(asm, cap=128)
        centroid = {}
        for v in _views(asm):
            s, _src = text_mod.text_of(ctx, v)
            if s not in (upper, lower):
                continue
            out = np.asarray(text_mod.f_text(ctx, v))[:, :, 0]
            ys, xs = np.nonzero(out > 0.5)
            assert ys.size, '%s: %r drew nothing' % (name, s)
            H, W = out.shape
            centroid.setdefault(s, []).append((ys.mean() / H - 0.5, xs.mean() / W - 0.5))
        assert set(centroid) == {upper, lower}, \
            '%s: found %r' % (name, sorted(centroid))
        up = np.mean([c[0] for c in centroid[upper]])
        dn = np.mean([c[0] for c in centroid[lower]])
        assert up < dn - 0.05, \
            '%s: %r is at y=%.3f and %r at y=%.3f -- the stack is not stacked' \
            % (name, upper, up, lower, dn)
        for s in (upper, lower):
            x = np.mean([c[1] for c in centroid[s]])
            assert abs(x) < 0.06, '%s: %r is centred at x=%.3f, not on the sign' % (name, s, x)
        checked += 1
    if not checked:
        return _skip('test_the_ink_lands_where_the_record_says: no specimen')
    print('ok  test_the_ink_lands_where_the_record_says (%d files)' % checked)


def test_the_no_font_path_still_places_the_text():
    """The dependency floor: with no font library at all, the layout survives.

    `render2` may not require PIL or freetype, so the path a machine without them takes is
    the one that has to keep working -- and "keeps working" has to mean more than "does not
    raise". The box backend must put its ink in the same place the font backend does.
    """
    asm = _asm('Do Not Enter.sbsasm')
    if asm is None:
        return _skip('test_the_no_font_path_still_places_the_text: no specimen')
    ctx = Context(asm, cap=128)
    saved = text_mod._FONT_SOURCE
    try:
        for v in _views(asm):
            text_mod._FONT_SOURCE = 'system'
            a = np.asarray(text_mod.f_text(ctx, v))[:, :, 0]
            text_mod._FONT_SOURCE = 'boxes'
            b = np.asarray(text_mod.f_text(ctx, v))[:, :, 0]
            assert b.shape == a.shape and np.all(np.isfinite(b))
            for got, which in ((a, 'font'), (b, 'boxes')):
                ys, xs = np.nonzero(got > 0.5)
                assert ys.size, 'rec%d: the %s backend drew nothing' % (v.index, which)
            ay, ax = np.nonzero(a > 0.5)
            by, bx = np.nonzero(b > 0.5)
            H, W = a.shape
            assert abs(ay.mean() - by.mean()) / H < 0.05 \
                and abs(ax.mean() - bx.mean()) / W < 0.05, \
                'rec%d: the two backends disagree about where the text is' % v.index
            # The boxes must cover MORE than the glyphs -- they are the glyphs' bounding
            # boxes -- which is the cheapest statement that they are not the same picture.
            assert (b > 0.5).sum() > (a > 0.5).sum()
    finally:
        text_mod._FONT_SOURCE = saved
    print('ok  test_the_no_font_path_still_places_the_text')


def test_no_reference_exists_for_any_text_record():
    """THE NEGATIVE THAT BOUNDS EVERY CLAIM ABOVE, asserted so it cannot go stale.

    Not one package containing a filter-17 record ships the engine's own exported maps, so
    `refcompare` has nothing to score and every fidelity statement in `text.py` rests on
    source containment, internal consistency and one 512-pixel thumbnail. The day a
    reference pack with a `text` record arrives, this fails and says to go score it.
    """
    import glob
    packs = os.path.join(ROOT, 'archive', 'specimens', 'new_opengameart')
    if not os.path.isdir(packs):
        return _skip('test_no_reference_exists_for_any_text_record: no reference packs')
    found = []
    for pack in sorted(os.listdir(packs)):
        d = os.path.join(packs, pack)
        if not glob.glob(os.path.join(d, 'reference_renders', '**', '*.png'), recursive=True):
            continue
        for f in glob.glob(os.path.join(d, '**', '*.sbsasm'), recursive=True):
            try:
                asm = sbsasm.Assembly(f)
            except Exception:
                continue
            if any(r.filter_id == 17 for r in asm.records):
                found.append(f)
    assert not found, \
        'a reference pack now contains a text record (%r) -- score it, and delete this ' \
        'test along with the "no ground truth" caveats in text.py' % found
    print('ok  test_no_reference_exists_for_any_text_record (still none)')


if __name__ == '__main__':
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_') and callable(_fn):
            _fn()
