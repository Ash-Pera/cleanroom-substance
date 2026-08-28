#!/usr/bin/env python3
"""Run sbsasm.Assembly over the corpus and report where the model still fails.

The point is the failure columns. A segmenter that silently guesses looks perfect;
this one is meant to make its own gaps countable.
"""
import collections, sys

import disasm
import decompose
from sbsasm import _PAYLOAD_PROGRAM_FILTERS as PAYLOAD_PROGRAM_FILTERS
from sbsasm import Assembly, FILTERS, UNNAMED, PARTIAL_EDGES

def main(paths):
    tot = collections.Counter()
    byfilter = collections.defaultdict(lambda: [0, 0, 0])   # records, no prog, unresolved edges
    unexplained = []
    failed = []
    for p in paths:
        try:
            a = Assembly(p)
        except Exception as e:
            failed.append((p, str(e)[:60])); continue
        cov = a.coverage()
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
