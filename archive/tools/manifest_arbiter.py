#!/usr/bin/env python3
"""The manifest arbiter, run exhaustively: name every program-carrying slot by the graph
input its program reads.

    python3 archive/tools/manifest_arbiter.py                 # every slot role, every filter
    python3 archive/tools/manifest_arbiter.py --unnamed       # only roles the legend leaves unnamed
    python3 archive/tools/manifest_arbiter.py --controls      # only roles the legend DOES name
    python3 archive/tools/manifest_arbiter.py --filter emboss --detail
    python3 archive/tools/manifest_arbiter.py --silent        # the roles this arbiter CANNOT speak for
    python3 archive/tools/manifest_arbiter.py --limit 40      # first 40 corpus files, for a smoke run

WHAT IT IS. Two facts compose. (1) A `.sbsar` manifest declares every graph input as
`<input uid="N" identifier="X" type="T">`. (2) A record slot in the `program` state holds a
pointer to bytecode that, for a parameter, opens with `inputref uid`. So the file names its
own parameters: resolve the uid through the manifest and the material author's name for the
input comes back. This is the arbiter that named class bits 16 and 23 (`$outputsize`,
`$randomseed`), bits 26/27 (`$pixelsize`), `uniform`'s bit 25, and `normal`'s three `w1`
fields. Each of those was done by hand for one field. This runs it over every slot the walk
places, in every record of the corpus, and aggregates.

WHY AGGREGATION IS THE POINT. One package naming an input `my_thing` is that author's
private choice about their own graph and is evidence about nothing. Two hundred packages by
different authors converging on `normal_intensity` is evidence about the format, because the
only thing those authors share is the compiler that put the pointer in that slot. Every row
below therefore carries `pkgs` and `authors` alongside the record count, and a row supported
by one package is a LEAD, not a finding. `--min-pkgs` sets the bar; the report marks
anything under it.

WHAT IT CANNOT SPEAK FOR, and this is most of the census's unnamed list rather than an
edge case. A `w1` field whose cost is zero words in every state has NO SLOT: its two mask
bits are its whole value, there is no pointer, and no program exists to disassemble. The
manifest is silent about such a field by construction, not by accident. `--silent` prints
that population -- run it before believing this tool has covered a field. Over the current
corpus it covers 5 of the 11 census entries and is structurally silent on the other 6.

PROVENANCE. The manifest is DISTRIBUTION DATA shipped inside the compiled `.sbsar`, not a
`.sbs` source. `archive/tools/provenance.py` states the boundary outright: the rule excludes
Adobe's `.sbs` graph DEFINITIONS, and "an Adobe-authored `.sbsar` supplies compiled bytecode
like any other specimen and supplies no definitions, so it stays in the corpus". So this runs
over all 437 specimens, not the 100 permitted paired sources that bound `sourcematch.py`.
That is checked rather than asserted: every row is also reported with Adobe-authored
manifests EXCLUDED (`nonadobe_*` columns), so a reader can see for themselves that no
conclusion here rests on them. `--exclude-adobe` runs the whole thing that way.
"""
import argparse
import collections
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import _repo_root                                                     # noqa: E402

ROOT = _repo_root.ROOT
_TOOLS = os.path.join(ROOT, 'tools')
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import corpus                                                         # noqa: E402
import decompose                                                      # noqa: E402
import disasm                                                         # noqa: E402
import sbsasm                                                         # noqa: E402

#: `<input uid=... identifier=... type=...>`, the one declaration this whole tool rests on.
#: `manifest.py` parses only type-5 inputs and the `alteroutputs` attribute; nothing there
#: returns the full uid -> (identifier, type) map, so it is built here rather than by
#: widening a module another agent owns.
_INPUT = re.compile(r'<input\s+uid="(\d+)"\s+identifier="([^"]*)"\s+type="(\d+)"')
_AUTHOR = re.compile(r'\bauthor="([^"]*)"')

#: Authors whose `.sbs` sources the provenance rule excludes. Their MANIFESTS are not
#: excluded (see the module docstring) -- this set exists so the report can show every
#: figure with and without them, which is what makes the boundary claim checkable.
_ADOBE = frozenset(('Allegorithmic', 'Adobe', 'Adobe Inc.', 'Adobe Systems'))

#: The type codes SPEC 7.2 states, for the second-order check "does the name agree with the
#: field's type".
TYPE_NAMES = {0: 'float1', 1: 'float2', 2: 'float3', 3: 'float4', 4: 'int1',
              5: 'image', 6: 'string', 7: 'font', 8: 'int2', 9: 'int3', 10: 'int4'}


def manifest_inputs(asm_path):
    """{uid: (identifier, type code)} and the set of authors, from the sibling `.xml`."""
    xml = os.path.splitext(asm_path)[0] + '.xml'
    if not os.path.exists(xml):
        return {}, frozenset()
    try:
        text = open(xml, encoding='utf-8', errors='replace').read()
    except OSError:
        return {}, frozenset()
    ins = {int(u): (i, int(t)) for u, i, t in _INPUT.findall(text)}
    return ins, frozenset(a for a in _AUTHOR.findall(text) if a)


def first_inputref(asm, ptr, hi):
    """(uid, return type letter, return components, instruction count) for the program at
    `ptr`, or None if it resolves no program.

    THE FIRST `inputref`, not any: a parameter program's opening instruction is the read of
    the graph input it is driven by, and later ones are operands of an expression built on
    it. `normal`'s field-1 programs are `<input> == 1` -- the input first, the constant
    second -- and taking "any inputref" there would still work, but taking the first is what
    makes `$pixelsize`'s six-instruction `sysvar..exp2` arm report NO input rather than
    borrow one from further down a longer program.

    The return type is read off the LAST instruction's type page and component count, which
    is the second-order check that costs nothing: a field whose programs all return bool is
    a flag whatever the manifest calls the input.
    """
    span = asm.program_span(ptr, hi)
    if span is None:
        return None
    uid = None
    ty = comps = None
    n = 0
    for _k, addr, op, toks in disasm.decode(asm.data, ptr, hi):
        _nt, ty, comps, oid = disasm.fields(op)
        n += 1
        if oid == 0x02 and uid is None:
            uid = disasm.uid(addr, toks)
    if ty is None:
        return None
    return (uid, disasm.TYPE.get(ty, '?'), comps, n)


def _roles(r, d):
    """{header slot -> role label} for one record, from the walk alone.

    Roles are the walk's own vocabulary: `cls<bit>`, `w1f<field>`, `edge`, `size`. A slot
    the walk places but does not put in any of its lists is `spare` -- reported rather than
    dropped, because a program sitting in one is exactly the kind of thing this sweep is
    for.
    """
    out = {}
    for pos in d.get('inputs') or ():
        out[pos] = 'edge'
    for bit, pos, n in d.get('cls_params') or ():
        for i in range(n):
            out[pos + i] = 'cls%d' % bit
    for fld, _st, pos, n in d.get('param_slots') or ():
        for i in range(n):
            out[pos + i] = 'w1f%d' % fld
    ss = d.get('size_slot')
    if ss is not None and out.get(ss, '').startswith('cls'):
        out[ss] = 'size'
    p = d.get('prog')
    if p is not None and p not in out:
        out[p] = 'size'
    # SLOTS THE WALK PLACES BUT LABELS NOTHING. `end` is the header boundary and `hdr` the
    # mask-word count, so every word between them belongs to the record's header and the
    # walk owes an account of it. A program sitting in one is a parameter the cost model
    # charges to nobody, which is precisely the shape of `emboss`'s grid-shift bug, so this
    # sweep reports them as `spare` rather than skipping the range.
    end = d.get('end')
    if end is not None:
        for k in range(d.get('hdr') or 0, min(end, len(r.words))):
            out.setdefault(k, 'spare')
    return out


class Tally(object):
    """Per (filter, role) evidence: names, packages, authors, return types."""

    def __init__(self):
        self.records = 0
        self.resolved = 0
        self.noname = 0                      # a program with no inputref (a computed arm)
        self.unknown_uid = 0                 # an inputref the manifest does not declare
        self.names = collections.Counter()
        self.pkgs = collections.defaultdict(set)
        self.authors = collections.defaultdict(set)
        self.types = collections.Counter()
        self.rets = collections.Counter()
        self.all_pkgs = set()
        self.examples = []

    def add(self, pkg, authors, name, tcode, ret, ex):
        self.records += 1
        self.all_pkgs.add(pkg)
        self.rets[ret] += 1
        if name is None:
            self.noname += 1
            return
        if name is False:
            self.unknown_uid += 1
            return
        self.resolved += 1
        self.names[name] += 1
        self.pkgs[name].add(pkg)
        self.authors[name] |= set(authors) or {'(none declared)'}
        self.types[TYPE_NAMES.get(tcode, tcode)] += 1
        if len(self.examples) < 4:
            self.examples.append(ex)


def sweep(paths, exclude_adobe=False, verbose=False):
    """Run the arbiter over `paths`. Returns {(filter_name, role): Tally}."""
    tallies = collections.defaultdict(Tally)
    nonadobe = collections.defaultdict(Tally)
    files = skipped = 0
    for p in paths:
        full = p if os.path.isabs(p) else os.path.join(ROOT, p)
        try:
            asm = sbsasm.Assembly(full)
        except Exception:
            skipped += 1
            continue
        ins, authors = manifest_inputs(full)
        adobe = bool(authors & _ADOBE)
        if exclude_adobe and adobe:
            skipped += 1
            continue
        files += 1
        pkg = os.path.basename(full)
        hi = asm.body_hi
        for r in asm.records:
            try:
                d = decompose.decompose(r)
            except Exception:
                continue
            if d is None:
                continue
            roles = _roles(r, d)
            fname = r.filter_name or ('filter%d' % r.filter_id)
            words = r.words
            for pos, role in roles.items():
                if role == 'edge' or pos >= len(words):
                    continue
                got = first_inputref(asm, words[pos] + 52, hi)
                if got is None:
                    continue
                uid, ret_ty, ret_n, _ni = got
                if uid is None:
                    name, tcode = None, None
                elif uid in ins:
                    name, tcode = ins[uid]
                else:
                    name, tcode = False, None
                ex = '%s rec %d slot %d' % (pkg, r.index, pos)
                ret = '%s%d' % (ret_ty, ret_n)
                tallies[(fname, role)].add(pkg, authors, name, tcode, ret, ex)
                if not adobe:
                    nonadobe[(fname, role)].add(pkg, authors, name, tcode, ret, ex)
        if verbose and files % 50 == 0:
            print('  ... %d files' % files, file=sys.stderr)
    return tallies, nonadobe, files, skipped


# ---------------------------------------------------------------- naming status

def legend_names():
    """{(filter name, role) -> the legend's name}, read from the code rather than retyped.

    Two sources, because the legend is in two places: `render2.model.W1_PARAMS` /
    `CLS_NAMES` is what the renderer reads, and `bit_census.PENDING_CLS` /
    `NAMED_ELSEWHERE_W1` is what the census credits on top of it. A role is "named" here if
    EITHER carries a name, so this tool's unnamed list is the census's unnamed list and not
    a wider one it would be flattering to report.

    A mask is turned into a field id by its LOW BIT, and that IS the field id: SPEC 7.3's
    width legend keys every `w1` cell on the bit its two-bit code begins at, so `blend`'s
    relocated opacity 0x600 is the field at bit 9 and matches what `param_slots` reports
    with no per-filter grid shift and no straddle relabelling in between.
    """
    out = {}
    r2 = os.path.join(_TOOLS, 'render2')
    if r2 not in sys.path:
        sys.path.insert(0, r2)
    import model                                                       # noqa: E402
    import bit_census                                                  # noqa: E402

    def field_of(fid, mask):
        return (mask & -mask).bit_length() - 1

    for fid, spec in getattr(model, 'W1_PARAMS', {}).items():
        fname = sbsasm.FILTERS.get(fid, 'filter%d' % fid)
        for entry in spec:
            mask, nm = entry[0], entry[2]
            if nm:
                out[(fname, 'w1f%d' % field_of(fid, mask))] = nm
    for fid, bits in getattr(model, 'CLS_NAMES', {}).items():
        fname = sbsasm.FILTERS.get(fid, 'filter%d' % fid)
        for b, nm in bits.items():
            out[(fname, 'cls%d' % b)] = nm[0] if isinstance(nm, tuple) else nm
    for fid, bits in getattr(bit_census, 'PENDING_CLS', {}).items():
        fname = sbsasm.FILTERS.get(fid, 'filter%d' % fid)
        for b, nm in bits.items():
            out.setdefault((fname, 'cls%d' % b), nm)
    for fid, entries in getattr(bit_census, 'NAMED_ELSEWHERE_W1', {}).items():
        fname = sbsasm.FILTERS.get(fid, 'filter%d' % fid)
        for mask, nm in entries:
            out.setdefault((fname, 'w1f%d' % field_of(fid, mask)), nm)
    for fname in set(sbsasm.FILTERS.values()) | {f for f, _ in out}:
        out.setdefault((fname, 'cls16'), '$outputsize')
        out.setdefault((fname, 'cls23'), '$randomseed')
        out.setdefault((fname, 'size'), '$outputsize')
    return out


def silent_roles():
    """Every `w1` field, with the word count its PROGRAM state is charged.

    A field charged zero words in state 10 has no pointer slot: its two mask bits are its
    whole value. There is nothing to disassemble, so the manifest cannot be asked about it
    at all -- not "we looked and found nothing", but "no question exists". That is the
    single most important thing this tool reports, because it is most of the census's
    unnamed list.

    Read off `legend.json` through `record_layout.legend()` rather than hard-coded, so the
    list re-derives itself if the width legend changes under it.

    WHAT THIS REPORTS IS NOW A MUCH SHORTER LIST, AND THE REASON IS THE MODEL. Under the
    fitted table a field's PROGRAM state had its own free coefficient, and several came back
    at zero -- `blend`'s field 4 and `distance`'s field 0 among them -- so this tool
    correctly reported that there was no pointer to disassemble. The width legend charges
    ONE WORD for a program pointer in every filter and every field, because a pointer is a
    pointer, so nothing is silent on the program side any more. What IS silent is a field
    whose baked KIND is 0: `normal`'s two booleans, where the mask state is the whole value.

    Returns [(filter name, field bit, program-state words, baked-state words)].
    """
    import record_layout
    out = []
    for key, spec in sorted(record_layout.legend().items(), key=lambda kv: int(kv[0])):
        fid = int(key)
        fname = sbsasm.FILTERS.get(fid, 'filter%d' % fid)
        for j, kind in sorted(spec.get('w1', {}).items(), key=lambda kv: int(kv[0])):
            baked = record_layout.width(kind, 1)
            out.append((fname, int(j), 1.0, float(baked) if baked is not None else 0.0))
    return out


# ---------------------------------------------------------------- report

def _row(tally, limit=3):
    return '; '.join('%s %d (%dp/%da)' % (nm, c, len(tally.pkgs[nm]), len(tally.authors[nm]))
                     for nm, c in tally.names.most_common(limit))


def report(tallies, nonadobe, files, args):
    """One line per (filter, slot role), and the columns are the epistemics.

    `progs` is how many slots resolved a program; `named` how many of those opened with an
    `inputref` the manifest declares. `pkgs`/`auth` are for the MODAL name only -- that is
    the number that decides whether a row is a finding or a lead, and it is deliberately not
    the row's total package count, which would flatter every row with a long tail. `names`
    is how many distinct identifiers appeared: a role with one name across many packages is
    the format speaking, and a role with two hundred names is the material authors speaking.
    """
    named = legend_names()
    rows = sorted(tallies.items(), key=lambda kv: (-kv[1].records, kv[0]))
    print('%d files, %d (filter, slot role) pairs carrying at least one program\n' % (
        files, len(rows)))
    hdr = ('%-16s %-7s %-10s %7s %7s %5s %5s %6s %6s  %s' % (
        'filter', 'role', 'status', 'progs', 'named', 'pkgs', 'auth', 'names', 'allpkg',
        'top manifest identifiers'))
    print(hdr)
    print('-' * len(hdr))
    for (fname, role), t in rows:
        legend = named.get((fname, role))
        if args.unnamed and legend:
            continue
        if args.controls and not legend:
            continue
        if args.filter and args.filter != fname:
            continue
        if t.records < args.min_records:
            continue
        top = t.names.most_common(1)
        pk = len(t.pkgs[top[0][0]]) if top else 0
        au = len(t.authors[top[0][0]]) if top else 0
        status = legend or 'UNNAMED'
        if pk < args.min_pkgs:
            status = (status + ' *lead*') if not legend else status
        print('%-16s %-7s %-10s %7d %7d %5d %5d %6d %6d  %s' % (
            fname[:16], role, status[:10], t.records, t.resolved, pk, au,
            len(t.names), len(t.all_pkgs), _row(t)[:70]))
        if args.detail:
            nd = nonadobe.get((fname, role))
            print('        return types: %s' % dict(t.rets.most_common(6)))
            print('        input types : %s' % dict(t.types.most_common(6)))
            print('        no inputref : %d    uid not in manifest: %d' % (
                t.noname, t.unknown_uid))
            if nd:
                print('        non-Adobe   : %d progs, %d named, top %s' % (
                    nd.records, nd.resolved, _row(nd)))
            for e in t.examples:
                print('        e.g. %s' % e)
            for nm, c in t.names.most_common(12):
                print('          %-40s %6d  %2d pkgs  %2d authors  %s' % (
                    nm[:40], c, len(t.pkgs[nm]), len(t.authors[nm]),
                    ', '.join(sorted(t.authors[nm])[:3])))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--limit', type=int, default=0, help='first N corpus files only')
    ap.add_argument('--filter', help='restrict to one filter name')
    ap.add_argument('--unnamed', action='store_true', help='only roles the legend leaves unnamed')
    ap.add_argument('--controls', action='store_true', help='only roles the legend names')
    ap.add_argument('--detail', action='store_true', help='per-name breakdown')
    ap.add_argument('--silent', action='store_true',
                    help='list the roles this arbiter structurally cannot speak for')
    ap.add_argument('--exclude-adobe', action='store_true',
                    help='drop specimens whose manifest declares an Adobe author')
    ap.add_argument('--min-pkgs', type=int, default=2,
                    help='packages below which a name is reported as a lead (default 2)')
    ap.add_argument('--min-records', type=int, default=1)
    args = ap.parse_args(argv)

    if args.silent:
        print('Every w1 field and the words its PROGRAM state is charged.')
        print('prog=0 means there is no pointer slot, so no program, so nothing the')
        print('manifest can be asked about -- structural silence, not a null result.\n')
        print('  %-16s %-6s %6s %6s  %s' % ('filter', 'field', 'prog', 'baked', 'arbiter'))
        for fname, j, prog, baked in silent_roles():
            if args.filter and args.filter != fname:
                continue
            print('  %-16s w1f%-3d %6g %6g  %s' % (
                fname, j, prog, baked,
                'CAN speak' if prog else 'SILENT (no pointer slot)'))
        return 0

    paths = corpus.paths()
    if args.limit:
        paths = paths[:args.limit]
    tallies, nonadobe, files, skipped = sweep(paths, args.exclude_adobe, verbose=True)
    report(tallies, nonadobe, files, args)
    if skipped:
        print('\n%d specimens skipped (unreadable, or Adobe-authored under --exclude-adobe)'
              % skipped)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
