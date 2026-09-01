#!/usr/bin/env python3
"""Run sbsasm.Assembly over the corpus and report where the model still fails.

The point is the failure columns. A segmenter that silently guesses looks perfect;
this one is meant to make its own gaps countable.
"""
import collections, os, struct, sys

# THE MODULES THIS TOOL AUDITS ARE IN tools/, AND THIS TOOL IS NOT. The archive cut moved
# it here and nothing put the two back in touch, so `python3 archive/tools/audit_corpus.py`
# -- the invocation tools/README.md documents -- died at `import disasm` on line 1. It ran
# only under pytest, where `conftest.py` inserts this exact path, and pytest never collects
# it because it defines no test. So the tool that prints this project's headline figures
# has not been runnable as documented since the cut, which is the mechanical half of why
# the `record bytes interpreted` row went four points stale without anyone noticing.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))

import disasm
import decompose
import sbsasm
from sbsasm import _PAYLOAD_PROGRAM_FILTERS as PAYLOAD_PROGRAM_FILTERS
from sbsasm import Assembly, FILTERS, UNNAMED, PARTIAL_EDGES

# ---------------------------------------------------------------------------
# RECORD BYTES INTERPRETED -- the row README.md quotes, as code.
#
# It was never code. "92.5% of record bytes" entered FORMAT-NOTES.md in 8fa476b and the
# README in 0f21ceb, and NEITHER COMMIT TOUCHED A .py FILE: `git log -S` over the whole
# history finds no script that ever computed it. `coverage()` does not -- it reports
# whole-file byte classes, and its own docstring points AT this figure rather than
# producing it. So the one row nobody could re-run was the one that looked worst, and it
# sat four points stale for a week because re-running it was not possible. That is exactly
# the failure `corpus.py`'s docstring describes, one level up: a number recorded in prose
# does not propagate to code, and a number with no code cannot go stale loudly.
#
# THE CANVAS IS FILE-WIDE, NOT PER RECORD, and that is not a detail. The record directory
# is a sorted PARTITION and not an allocation -- `ramp`, `vector_shape` and `fx_walk` all
# say so in their own docstrings -- so a gradient's ramp table, an FX-Map's entry run and a
# vectorshape strip routinely lie inside a NEIGHBOURING record's extent. Marked per record,
# every one of those bytes is charged to a record that does not own them and credited to
# none. Measured both ways the difference is 132,370 bytes, and all of it is misattribution
# rather than decode: `transformation` and `blend`, which have no payload of their own,
# carry 660,544 bytes of other records' FX entry tables inside their extents.
#
# Three tiers, because the answer depends on what you are willing to call "interpreted"
# and the honest thing is to print the spread rather than pick one:
#
#   header      the tag, and every slot the structural walk enumerates, bounded by the
#               header end the walk states
#   +programs   the bodies of the programs `Record.programs` returns.  THIS TIER IS THE
#               README ROW: re-run against `git archive 8f973fa` -- the commit that pinned
#               92.5% into `coverage()`'s docstring -- over this same 437-file corpus it
#               gives 92.296%, so the definition below is the one that produced the row.
#   +payloads   every payload reader this repository already has: `read_ramp`,
#               `curve_points`, `vector_shape`, `bitmap`, and `fx_walk`'s nodes and entries
#               at their TRUE extent (an entry runs to the end of its own inline program,
#               which `fx_table`'s docstring states is structural -- crediting a token 8
#               bytes instead understates `fxmaps` by 1.98 MB, two thirds of the residual).
#
# What is NOT credited, deliberately: `referenced_programs()`. It is the permissive scan,
# and crediting it here would let the coverage number be raised by a scan rather than by a
# decode -- the same circularity the "0 unexplained bytes" retraction is about.
_TAG, _W1, _INP, _CLS, _PAR, _PRG, _BASE = 1, 2, 3, 4, 5, 6, 7
_PROGBODY = 8
_RAMP, _CURVE, _VEC, _FXNODE, _FXENTRY, _BMP = 9, 10, 11, 12, 13, 14
_REGION_NAMES = {_TAG: 'tag', _W1: 'w1', _INP: 'input edge', _CLS: 'class slot',
                 _PAR: 'w1 parameter', _PRG: 'size / program slot',
                 _BASE: 'header, no named slot', _PROGBODY: 'program body',
                 _RAMP: 'ramp table', _CURVE: 'curve table', _VEC: 'vector strip',
                 _FXNODE: 'fx node cell', _FXENTRY: 'fx entry', _BMP: 'bitmap pixels'}
_TIER_HDR = frozenset((_TAG, _W1, _INP, _CLS, _PAR, _PRG, _BASE))
_TIER_PROG = _TIER_HDR | frozenset((_PROGBODY,))


def _byte_canvas(a):
    """Every byte of `a`, labelled with the reader that can say what it is."""
    n = len(a.data)
    seen = bytearray(n)

    def mark(x, y, v):
        x, y = max(0, int(x)), min(n, int(y))
        if y <= x:
            return
        seg = seen[x:y]
        if seg.count(0) == y - x:                  # slice assignment, not a Python loop
            seen[x:y] = bytes((v,)) * (y - x)
            return
        for i in range(x, y):
            if not seen[i]:
                seen[i] = v

    for r in a.records:
        lo = r.offset

        def slot(s, v, w=1):
            if s is not None:
                mark(lo + 4 * s, lo + 4 * (s + w), v)

        try:
            d = decompose.decompose(r)
        except Exception:
            d = None
        slot(0, _TAG)
        if d is None:
            continue
        ins, cls = set(d.get('inputs') or ()), set(d.get('cls_slots') or ())
        if len(r.words) > 1 and 1 not in ins and 1 not in cls:
            slot(1, _W1)
        for s in ins:
            slot(s, _INP)
        for s in cls:
            slot(s, _CLS)
        for t in (d.get('param_slots') or ()):
            pos, wd = (t[2], t[3]) if len(t) >= 4 else (t[2], 1)
            slot(pos, _PAR, int(wd))
        slot(d.get('prog'), _PRG)
        # Whatever the walk's own header end covers and no slot above named. This is the
        # cost model's BASE REGION -- the words `pos = max(pos, const)` steps over -- and
        # it is 0.11% of record bytes, so naming it separately keeps it from hiding inside
        # either "understood" or "unexplained".
        if d.get('end') is not None:
            mark(lo, lo + 4 * d['end'], _BASE)
    for r in a.records:
        try:
            progs = r.programs
        except Exception:
            progs = ()
        for p in progs:
            try:
                e = a.program_end(p)
            except Exception:
                continue
            if e:
                mark(p, e, _PROGBODY)
    for r in a.records:
        f = r.filter_id
        try:
            if f == 0:
                got = r.read_ramp()
                if got:
                    form, tab = got
                    w = len(tab[0]) * (4 if 'float' in form else 2)
                    mark(r.words[3] + 52, r.words[3] + 52 + w * len(tab), _RAMP)
            elif f == 22:
                cp = r.curve_points
                if cp:
                    mark(r.words[3] + 52, r.words[3] + 52 + 4 + 24 * len(cp), _CURVE)
            elif f == 5 and len(r.words) > 1:
                off = r.words[1] + 52
                if 0 <= off <= n - 8:
                    _k, w = struct.unpack_from('<2I', a.data, off)
                    m = (w + 23) // 2
                    if m >= 12 and off + m <= n:
                        mark(off, off + m, _VEC)
            elif f == 16:
                bm = r.bitmap
                if isinstance(bm, dict) and bm.get('kind') in ('pixels', 'inline_pixels'):
                    st, sz = bm.get('offset'), bm.get('size')
                    if st is not None and sz:
                        mark(st, st + sz, _BMP)
            elif f == 4:
                ent = []
                for kind, off, hdr, prog in r.fx_walk():
                    if kind == 'node':
                        try:
                            sz = sbsasm.chain_extent(a, off)
                        except Exception:
                            sz = None
                        mark(off, off + (sz or 4), _FXNODE)
                    else:
                        ent.append((off, prog))
                    if prog:
                        try:
                            pe = a.program_end(prog)
                        except Exception:
                            pe = None
                        if pe:
                            mark(prog, pe, _PROGBODY)
                # An entry runs to the end of its own inline program, or to the next entry
                # when it names none. Second pass, because the bound is the NEXT entry.
                ent.sort()
                for i, (off, prog) in enumerate(ent):
                    hi = None
                    if prog:
                        try:
                            hi = a.program_end(prog)
                        except Exception:
                            hi = None
                    if hi is None:
                        nx = ent[i + 1][0] if i + 1 < len(ent) else None
                        hi = nx if (nx and 0 < nx - off < 4096) else off + 8
                    mark(off, hi, _FXENTRY)
        except Exception:
            pass
    return seen


def record_bytes(a, tot, byfilter_bytes):
    """Accumulate the record-byte accounting for one file."""
    seen = _byte_canvas(a)
    for r in a.records:
        lo, hi = r.offset, r.end
        if hi <= lo:
            continue
        seg = seen[lo:hi]
        tot['rb_total'] += hi - lo
        byfilter_bytes[r.filter_id]['_total'] += hi - lo
        for v in set(seg):
            c = seg.count(v)
            tot['rb_%d' % v] += c
            byfilter_bytes[r.filter_id][v] += c

def main(paths):
    tot = collections.Counter()
    byfilter = collections.defaultdict(lambda: [0, 0, 0])   # records, no prog, unresolved edges
    byfilter_bytes = collections.defaultdict(collections.Counter)
    unexplained = []
    failed = []
    for p in paths:
        try:
            a = Assembly(p)
        except Exception as e:
            failed.append((p, str(e)[:60])); continue
        cov = a.coverage()
        record_bytes(a, tot, byfilter_bytes)
        tot['files'] += 1
        tot['bytes'] += cov['total']
        tot['unexplained'] += cov['unexplained']
        tot['records'] += len(a.records)
        tot['programs'] += cov['programs_found']
        if cov['unexplained']:
            unexplained.append((cov['unexplained'] / cov['total'], p))
        for r in a.records:
            f = r.filter_id
            byfilter[f][0] += 1
            if r.known:
                tot['known_records'] += 1
            # Programs the WALK's own slots do not name.
            #
            # This was "programs off the layout table", splitting records by whether
            # layouts.json held a key for them: 23.40% of dropped-key records gained a
            # program against a 2.61% keyed control. THAT PARTITION IS DEAD. `programs()`
            # walks slots and no longer consults LAYOUTS at all -- test_tables.py records
            # the lookup as contributing nothing -- so both sides of the split now run the
            # same code, and the contrast described a mechanism that no longer exists.
            # The figure stayed in this report because a settled number invites no
            # re-reading, which is the failure `reverify.py` exists to prevent.
            #
            # The live question is whether the non-slot probes -- `classified_programs`,
            # and the tail and header-end scans inside `programs()` -- still recover
            # anything the walk misses. Corpus-wide they do: 58,237 programs over 58,084
            # records, so they are load-bearing and not a removal candidate.
            #
            # SPLIT BY WHETHER A PAYLOAD PROGRAM IS EXPECTED, because otherwise this
            # number is one filter's ordinary structure. `pixelprocessor` accounts for
            # 56,081 of those 58,237 -- exactly one per record, its pixel program, which
            # lives past the header by construction and is why sbsasm exempts it from the
            # slot bound. Reporting that as recovery states 96% of the total as though it
            # were a gap. The residual over every other filter is 2,156.
            _d = decompose.decompose(r)
            if f != 4:
                slots = set()
                if _d is not None and _d.get('end') is not None:
                    if _d.get('prog') is not None:
                        slots.add(_d['prog'])
                    for t in _d.get('param_slots', ()):
                        pos, wd = (t[2], t[3]) if len(t) >= 4 else (t[2], 1)
                        slots.update(range(pos, pos + int(wd)))
                    slots.update(_d.get('cls_slots', ()))
                named = set()
                for sx in slots:
                    if sx is None or sx >= len(r.words):
                        continue
                    q = r.words[sx] + 52
                    if a.body_lo <= q < a.body_hi and a.valid_program(q):
                        named.add(q)
                extra = [p for p in r.classified_programs() if p not in named]
                side = 'payload' if f in PAYLOAD_PROGRAM_FILTERS else 'other'
                tot[side + '_records'] += 1
                tot[side + '_recovered'] += len(extra)
                if extra:
                    tot[side + '_records_gaining'] += 1
            par = r.size_or_baked
            if par is None:
                tot['no_param'] += 1
                # Distinguish a record that HAS no parameter slot from one whose
                # parameter this model failed to read. A four-word blend is
                # [tag][flags][edge][edge] and ends before a parameter slot could exist,
                # so "no parameter" is the correct answer there. Counting those as
                # failures put the gap at 4.55% when the genuine miss is 0.55%.
                # ASKED OF THE WALK, not of layouts.json. The decoder stopped reading
                # that memo for layout, edges and prog, but this classification still
                # looked the record up in it -- so a record the table has no key for could
                # not be called "has no parameter slot" however plainly its own header
                # said so, and fell through to be counted as an unread parameter instead.
                # Over 19,631 records, 959 have no key and the walk resolves 958 of them.
                # `_d['inputs']` is the memo's edge-slot list and `_d['param_slots']` its
                # parameter list, so this is the same test on the same two facts, taken
                # from the mechanism that actually decodes the record.
                sl = r.layout[1]
                if (_d is not None and _d.get('end') is not None
                        and not _d['param_slots']
                        and len(r.words) <= max(list(_d['inputs']) + [1]) + 1):
                    tot['param_absent'] += 1
                elif sl is not None and sl >= len(r.words):
                    tot['param_absent'] += 1
                elif (r.filter_id == 0 and sl in (2, 3, 4) and r.ramp):
                    # For `gradient` the layout's parameter slot is one the RAMP uses --
                    # slot 2 is the stop count, 3 the table start, 4 its end. All 38 of
                    # these records return a ramp, and in all 38 the slot is 4, the end
                    # pointer. The field is read; it is just not a parameter. Same class
                    # as "the slot is an edge" above.
                    tot['param_is_edge'] += 1
                elif sl is None:
                    # The layout names no parameter slot at all. That is the same fact as
                    # "the block ends before one could exist", and was being counted as a
                    # miss: 117 of `gradient`'s 155 supposed misses, whose payload is the
                    # ramp and is read - 150 of the 155 return one.
                    tot['param_absent'] += 1
                # THE RECORD'S OWN EDGE SLOTS, from the walk. This asked EDGE_SLOTS,
                # a per-FILTER union of every edge slot any layouts.json key registered
                # for that filter -- so "some record of this filter has an edge here"
                # was accepted as "this record has an edge here". The walk answers it
                # per record. Over 60 specimens only 5 records reach this test at all,
                # and the union claimed 2 of them as edges that their own walk does not:
                # those are now reported unread, which is a slightly worse number and
                # the correct one.
                elif (sl is not None and sl < len(r.words)
                      and (r.words[sl] in [e for e in r.edges if e is not None]
                           or (_d is not None and sl in _d.get('inputs', ())))):
                    # The slot the layout calls the parameter is already claimed as an
                    # EDGE by this same record - it holds a backward record index that
                    # `Record.edges` resolved. That is a record with no parameter, not one
                    # whose parameter went unread. Of the 1,319 previously counted as
                    # unread, 828 have a readable slot, 774 of those hold a valid record
                    # index and 772 point backward, which is the edge signature; 303 are
                    # edges this record already lists.
                    #
                    # The other 469 are edges too, on two independent tests. Their slot is
                    # registered as an EDGE slot for the same filter under other layout
                    # keys in 469 of 469 (100.0%), and their target record is unreachable
                    # from the output table in 68.9% against 21.1% for a random backward
                    # index from the same record - a record nothing reaches is what a
                    # missing edge leaves behind. So the layout entry for those keys names
                    # an edge slot as the parameter slot.
                    tot['param_is_edge'] += 1
                else:
                    # The per-filter column counts only this branch. Counting every
                    # `None` there reported `bitmap` at 66% and `blend` at 6% where the
                    # genuine miss is 0.00%: 872 of 1,335 bitmap records are two words
                    # long, `[tag][flags]`, with no room for a parameter slot at all, and
                    # the audit's own summary already classifies those as correct.
                    byfilter[f][1] += 1
                    tot['param_unread'] += 1
            elif par[0] == 'program':
                # Not every program-valued parameter is a size expression. A size is a
                # TWO-component integer -- (log2 width, log2 height) -- and that is what
                # 90-99.5% of them return for every filter except two. `pixelprocessor`
                # returns a ONE-component integer in 99.7% and `fxmaps` in 99.3%, so for
                # those the slot holds something else entirely and calling it a size was
                # a label this audit applied, not a fact it measured.
                tot['param_program'] += 1
                last = None
                for last in disasm.decode(r.asm.data, par[1], r.asm.body_hi):
                    pass
                if True:
                    if last is not None and (((last[2] >> 6) & 3) + 1) == 2:
                        tot['param_size2'] += 1
                    else:
                        tot['param_size1'] += 1
            elif par[0] == 'float':
                tot['param_float'] += 1
            else:
                tot['param_zero'] += 1
            for e in r.edges:
                if e is None:
                    byfilter[f][2] += 1
                    tot['unresolved_edges'] += 1
                else:
                    tot['resolved_edges'] += 1
    print('files parsed          : %d   (failed %d)' % (tot['files'], len(failed)))
    print('records               : %d' % tot['records'])
    print('  filter identified   : %d  (%.1f%%)' % (tot['known_records'],
          100 * tot['known_records'] / max(1, tot['records'])))
    r_ = tot['records']
    print('  size expression or first parameter read: %d  (%.1f%%)' % (r_ - tot['no_param'],
          100 * (r_ - tot['no_param']) / max(1, r_)))
    print('    record has no parameter slot: %d  (%.2f%%)  -- correct, not a miss'
          % (tot['param_absent'], 100 * tot['param_absent'] / max(1, r_)))
    print('    slot is an edge or a ramp bound: %d  (%.2f%%)  -- read, not a parameter'
          % (tot['param_is_edge'], 100 * tot['param_is_edge'] / max(1, r_)))
    print('    genuinely unread     : %d  (%.2f%%)'
          % (tot['param_unread'], 100 * tot['param_unread'] / max(1, r_)))
    print('    the parameter is a program: %d  (%.1f%%)' % (tot['param_program'],
          100 * tot['param_program'] / max(1, r_)))
    print('      returning 2 components -- an output size : %d' % tot['param_size2'])
    print('      returning 1 component  -- a random seed : %d' % tot['param_size1'])
    print('    a baked filter parameter : %d  (%.1f%%)' % (tot['param_float'],
          100 * tot['param_float'] / max(1, r_)))
    print('    as zero / absent    : %d  (%.1f%%)' % (tot['param_zero'],
          100 * tot['param_zero'] / max(1, r_)))
    e = tot['resolved_edges'] + tot['unresolved_edges']
    print('edge slots            : %d   resolved %.2f%%' % (e, 100 * tot['resolved_edges'] / max(1, e)))
    # Programs the non-slot probes find beyond what the WALK's slots name. The
    # payload row is EXPECTED, not a gap: pixelprocessor carries its pixel program past
    # the header by construction. The `other` row is the one to read -- it is what the
    # walk does not reach on filters that have no reason to hide a program.
    pr, ot = tot['payload_records'], tot['other_records']
    print('programs beyond the walk\'s slots (fxmaps excluded):')
    print('    payload-program filters: %d records  recovered %d  (%.2f%% gain one)'
          '   -- expected, one per record'
          % (pr, tot['payload_recovered'],
             100 * tot['payload_records_gaining'] / max(1, pr)))
    print('    all other filters      : %d records  recovered %d  (%.2f%% gain one)'
          % (ot, tot['other_recovered'],
             100 * tot['other_records_gaining'] / max(1, ot)))
    print('bytes                 : %d   unexplained %d  (%.3f%%)' % (
        tot['bytes'], tot['unexplained'], 100 * tot['unexplained'] / max(1, tot['bytes'])))
    print('files with any unexplained bytes: %d' % len(unexplained))
    # THIS IS THE HEADLINE ROW, and the line above is not. `coverage()`'s unexplained
    # count is circular -- record extents are marked on enumeration and the directory
    # partitions the body -- so it reads 0.000% and means "the directory is complete".
    rbt = max(1, tot['rb_total'])
    hdr = sum(tot['rb_%d' % v] for v in _TIER_HDR)
    prg = hdr + tot['rb_%d' % _PROGBODY]
    pay = rbt - tot['rb_0']
    print('record bytes          : %d  (%.1f MB over %d records)'
          % (tot['rb_total'], tot['rb_total'] / 1e6, tot['records']))
    print('  interpreted, header slots only        : %.3f%%' % (100 * hdr / rbt))
    print('  interpreted, + program bodies         : %.3f%%   <- the README row'
          % (100 * prg / rbt))
    print('  interpreted, + every payload reader   : %.3f%%' % (100 * pay / rbt))
    print('  uninterpreted                         : %d bytes  (%.3f%%)'
          % (tot['rb_0'], 100 * tot['rb_0'] / rbt))
    for v in sorted(_REGION_NAMES):
        c = tot['rb_%d' % v]
        if c:
            print('      %-24s %12d %6.2f%%' % (_REGION_NAMES[v], c, 100 * c / rbt))
    print()
    print('  uninterpreted record bytes, by filter:')
    print('    %-24s %12s %12s %9s' % ('filter', 'record bytes', 'uninterp', 'interp'))
    for f, c in sorted(byfilter_bytes.items(), key=lambda kv: -kv[1][0])[:10]:
        t = max(1, c['_total'])
        print('    %-24s %12d %12d %8.2f%%'
              % (FILTERS.get(f) or 'fid %d *' % f, c['_total'], c[0], 100 * (t - c[0]) / t))
    print()
    print('per filter (records, no program, unresolved edge slots):')
    print('  %-28s %10s %10s %12s' % ('filter', 'records', 'unread', 'unres edges'))
    for f, (n, np_, ue) in sorted(byfilter.items(), key=lambda kv: -kv[1][0])[:22]:
        name = FILTERS.get(f) or 'fid %d *' % f
        # An unresolved-edge percentage with no explanation reads as a defect. Where the
        # model knows why a filter's slots do not all resolve, say so on the same line --
        # `PARTIAL_EDGES` held that knowledge and nothing consulted it, so the column
        # invited the reading its own note already answered.
        print('  %-28s %10d %9.0f%% %11.1f%%   %s'
              % (name, n, 100 * np_ / n, 100 * ue / n, PARTIAL_EDGES.get(f, '')))
    if unexplained:
        print('\nworst unexplained-byte files:')
        for frac, p in sorted(unexplained, reverse=True)[:6]:
            print('   %6.2f%%  %s' % (100 * frac, p.split('/')[-1]))
    if failed:
        print('\nparse failures:')
        for p, e in failed[:6]:
            print('   %-52s %s' % (p.split('/')[-1][:52], e))

if __name__ == '__main__':
    # Through `corpus.paths`. This tool read tools/DISTINCT.txt directly, which had been
    # WITHDRAWN as duplicate-laden - reverify.py's docstring says so - and moved to the
    # root list. That correction never reached here, and this is what prints the headline
    # figures, so every count below was inflated by about 20%. See tools/corpus.py.
    import corpus
    paths = corpus.paths(verbose=True)
    main(paths[:int(sys.argv[1])] if len(sys.argv) > 1 else paths)
