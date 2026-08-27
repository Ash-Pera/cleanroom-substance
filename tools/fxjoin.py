#!/usr/bin/env python3
"""Join a `.sbs` FX-Map paramset to the compiled entry it became.

    python3 tools/fxjoin.py

WHY THIS EXISTS. Counting source declarations against compiled entries is invalid, because
they are not in correspondence: over the corpus plus the reference packs, 41,901 `fxmaps`
records yield 189,066 entries and only 42.90% yield exactly one. That missing correspondence
produced three plausible wrong answers in one sitting -- a tag-nibble reading for
`blendingmode`, a separator for `patterntype` 1-vs-2, and a 957-of-957 divisibility for
`fx.gridcount` -- each a clean number computed over a population nothing had shown was
comparable.

WHAT DOES NOT WORK, measured rather than assumed, because each is the obvious idea:

  IDENTITY DOES NOT SURVIVE THE COMPILE. Of `ie_curve`'s 43 `paramsGraphData` uids, 410
  `compNode` uids and 43 `paramsGraph` uids, ZERO appear as a 32-bit word anywhere in the
  assembly. There is no id to join on.

  CONTAINMENT CANNOT REACH FX PARAMETERS AT ALL. It is the arbiter this project trusts most
  and it is empty here: of 289 tag-named FX parameters declared across the permitted paired
  sources, 278 are `dynamicValue` -- programs -- and only 11 are constants. NONE of those 11
  has a component at 5 decimal digits, which is the threshold a value must clear to identify
  a record. There is no distinctive constant to locate.

  THE TAG SIGNATURE IS TOO COARSE. Keying on `(patterntype, {parameter: baked|program})` --
  all of it stated by the tag -- gives 2 certain joins out of 70 paramsets, 59 ambiguous.

WHAT DOES WORK: THE PROGRAMS NAME THEIR INPUTS, AND THE MANIFEST NAMES THEM BACK. A dynamic
parameter's source form references graph inputs by STRING (`get_float1` on "stroke_size"); the
compiled program references them by UID (`inputref uid=1817737885`); and the manifest carries
`<input uid="..." identifier="...">`, which is the map between them. Over `ie_pcloud`, 23 of 23
distinct uids appearing in entry programs resolve to a manifest input name.

So the join key is the SET OF INPUT NAMES each parameter references, and it is discriminating
because it is content rather than shape -- one `ie_pcloud` opacity program names fifteen
inputs.

THE MANIFEST IS ALSO THE VOCABULARY, and that is the step that makes it work. A source
parameter body also mentions local outputs (`pos_out`), package dependencies
(`pkg:///Functions/Math/merge_float4?dependency=...`) and a `#` prefix on some references.
Keeping only names the manifest declares as an input is what aligns the two sides; without it
every paramset reads as unjoinable, 54 of 54.

COVERAGE, AND IT IS NARROW. Reported here rather than in a summary because a result derived
from this join is a result derived from these paramsets:

    permitted paired sources                                   96
      with fxmaps paramsets                                     8
      with a JOINABLE paramset                                  3
    permitted fxmaps paramsets                                 70
      reaching this join (a dynamic manifest-input reference)   46
        joined to exactly one entry                              9
        joined to several entries (one paramset, many instances) 32
        no entry carries that name-set                           5

41 of 70, in 3 files of 96, and the bulk of them are in ONE file (`ie_curve`). This is an
instrument for a handful of files, not for the corpus. `main()` prints these counts so the
figure is re-measured rather than quoted from here.

WHAT IT SETTLES, AND WHAT IT DOES NOT. It does not settle `blendingmode`, which is what it was
built for. 585 joined pairs carry a declared `blendingmode`, but 579 declare 1 and only 6
declare 2, and the one tag nibble that separates them perfectly is nibble 8 -- `patterntype`
itself. The two fields are perfectly confounded across every pair this join reaches, so there
is no independent variation to read and no amount of care with the join recovers it. What is
needed is a permitted source declaring both fields varying independently, and none does.
"""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disasm                                                        # noqa: E402
import provenance                                                    # noqa: E402
from sbsasm import Assembly                                          # noqa: E402

#: The FX entry parameters a tag names. Others (`blendingmode`, `imagefiltering`, `switch`)
#: are declared by sources but have no established bit, so they cannot key a join.
TAGNAMES = frozenset({'opacity', 'branchoffset', 'frameoffset', 'patternsize',
                      'patternrotation', 'patternsuppl', 'imageindex'})

_STR = re.compile(r'<constantValueString v="([^"]+)"')
_PARAM = re.compile(r'<parameter><name v="([^"]+)"/>(.*?)(?=<parameter><name|\Z)', re.S)
_PGD = re.compile(r'<paramsGraphData>(.*?)</paramsGraphData>', re.S)
_INPUT = re.compile(r'<input uid="(\d+)" identifier="([^"]+)"')


def manifest_inputs(asm_path):
    """{uid: identifier} from the package manifest, or None if there is none."""
    xml = os.path.splitext(asm_path)[0] + '.xml'
    if not os.path.exists(xml):
        return None
    text = open(xml, encoding='utf-8', errors='replace').read()
    return {int(m.group(1)): m.group(2) for m in _INPUT.finditer(text)}


def source_paramsets(sbs_path, vocab):
    """[{parameter: frozenset(input names)}] for each paramset with a dynamic reference."""
    text = open(sbs_path, encoding='utf-8', errors='replace').read()
    out = []
    for block in _PGD.finditer(text):
        blk = block.group(1)
        if not re.search(r'<type v="paramset"', blk):
            continue
        refs = {}
        for pm in _PARAM.finditer(blk):
            name, body = pm.group(1), pm.group(2)
            if name not in TAGNAMES or '<dynamicValue>' not in body:
                continue
            names = {s.lstrip('#') for s in _STR.findall(body)}
            names &= vocab            # the manifest decides what is an input
            if names:
                refs[name] = frozenset(names)
        if refs:
            out.append(refs)
    return out


def assembly_entries(asm_path, name_of):
    """[((record index, entry offset), {parameter: frozenset(input names)})]."""
    a = Assembly(asm_path)
    vocab = set(name_of.values())
    out = []
    for r in a.records:
        if r.filter_id != 4:
            continue
        by_entry = collections.defaultdict(dict)
        tags = {}
        for off, tag, _slot, name, kind, val in r.fx_named_params():
            if kind != 'program' or name not in TAGNAMES:
                continue
            try:
                text = disasm.text(a.data, val, a.program_end(val))
            except Exception:
                continue
            names = {name_of[int(u)] for u in re.findall(r'uid=(\d+)', text)
                     if int(u) in name_of}
            names &= vocab
            if names:
                by_entry[off][name] = frozenset(names)
                tags[off] = tag
        for off, refs in by_entry.items():
            out.append(((r.index, off), refs, tags[off]))
    return out


def _key(refs):
    return frozenset(refs.items())


def join(sbs_path):
    """[(paramset refs, [(record, offset, tag), ...])] for one source, or None."""
    asm_path = provenance.own_assembly(sbs_path)
    if not asm_path:
        return None
    name_of = manifest_inputs(asm_path)
    if name_of is None:
        return None
    src = source_paramsets(sbs_path, set(name_of.values()))
    if not src:
        return None
    try:
        ent = assembly_entries(asm_path, name_of)
    except Exception:
        return None
    index = collections.defaultdict(list)
    for where, refs, tag in ent:
        index[_key(refs)].append((where[0], where[1], tag))
    return [(refs, index.get(_key(refs), [])) for refs in src]


def main():
    stat = collections.Counter()
    for p in provenance.paired_sources():
        if provenance.matches(p, provenance.EXCLUDED_AUTHORS):
            continue
        if provenance.matches(p, provenance.FLAGGED_AUTHORS):
            continue
        stat['permitted sources'] += 1
        rows = join(p)
        if rows is None:
            continue
        stat['files with a joinable paramset'] += 1
        for _refs, hits in rows:
            stat['paramsets'] += 1
            if not hits:
                stat['  no entry carries that name-set'] += 1
            elif len(hits) == 1:
                stat['  joined to exactly one entry'] += 1
            else:
                stat['  joined to several entries (instances)'] += 1
    for k, v in stat.most_common():
        print('  %-46s %d' % (k, v))
    print('\nCoverage is narrow and concentrated -- see the module docstring before deriving'
          '\nanything from it. It does not settle `blendingmode`; that field is perfectly'
          '\nconfounded with `patterntype` across every pair this join reaches.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
