#!/usr/bin/env python3
"""Run sbsasm.Assembly over the corpus and report where the model still fails.

The point is the failure columns. A segmenter that silently guesses looks perfect;
this one is meant to make its own gaps countable.
"""
import collections, sys

import disasm
from sbsasm import Assembly, FILTERS, UNNAMED, LAYOUTS, LAYOUT_MASK

# Which slots the layout table registers as EDGE slots, per filter, across all its keys.
# Used to recognise a layout entry that names an edge slot as its parameter slot.
EDGE_SLOTS = {}
for _k, _v in LAYOUTS.items():
    EDGE_SLOTS.setdefault(_k[0], set()).update(_v[0])

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
            # Programs the layout table does not name. A record whose key was dropped by
            # derive_layouts' MIN=20 falls through to a fallback that names one slot by
            # construction, so a second program there was invisible in every figure below.
            # The control is the same probe on known-key records, which measures what the
            # small-integer artifact contributes: it ran at 0.02% against 19.54%.
            key = (f, r.cls, r.words[1] & LAYOUT_MASK.get(f, 0)) if len(r.words) > 1 else None
            if key is not None and f != 4:
                # what the layout slots alone name, which is what `programs` used to be
                slots = list(LAYOUTS[key][1]) if key in LAYOUTS else []
                sl = r.layout[1]
                if sl is not None and sl not in slots:
                    slots.insert(0, sl)
                named = {r.words[s] + 52 for s in slots
                         if s is not None and s < len(r.words)}
                extra = [p for p in r.classified_programs() if p not in named]
                side = 'fallback' if key not in LAYOUTS else 'keyed'
                tot[side + '_records'] += 1
                tot[side + '_recovered'] += len(extra)
                if extra:
                    tot[side + '_records_gaining'] += 1
            par = r.parameter
            if par is None:
                tot['no_param'] += 1
                # Distinguish a record that HAS no parameter slot from one whose
                # parameter this model failed to read. A four-word blend is
                # [tag][flags][edge][edge] and ends before a parameter slot could exist,
                # so "no parameter" is the correct answer there. Counting those as
                # failures put the gap at 4.55% when the genuine miss is 0.55%.
                hit = LAYOUTS.get((r.filter_id, r.cls,
                                   r.words[1] & LAYOUT_MASK.get(r.filter_id, 0))
                                  if len(r.words) > 1 else None)
                sl = r.layout[1]
                if hit and not hit[1] and len(r.words) <= max(list(hit[0]) + [1]) + 1:
                    tot['param_absent'] += 1
                elif sl is not None and sl >= len(r.words):
                    tot['param_absent'] += 1
                elif sl is None:
                    # The layout names no parameter slot at all. That is the same fact as
                    # "the block ends before one could exist", and was being counted as a
                    # miss: 117 of `gradient`'s 155 supposed misses, whose payload is the
                    # ramp and is read - 150 of the 155 return one.
                    tot['param_absent'] += 1
                elif (sl is not None and sl < len(r.words)
                      and (r.words[sl] in [e for e in r.edges if e is not None]
                           or (0 <= r.words[sl] < r.index
                               and sl in EDGE_SLOTS.get(r.filter_id, ())))):
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
    print('    slot is an edge      : %d  (%.2f%%)  -- no parameter, not a miss'
          % (tot['param_is_edge'], 100 * tot['param_is_edge'] / max(1, r_)))
    print('    genuinely unread     : %d  (%.2f%%)'
          % (tot['param_unread'], 100 * tot['param_unread'] / max(1, r_)))
    print('    the parameter is a program: %d  (%.1f%%)' % (tot['param_program'],
          100 * tot['param_program'] / max(1, r_)))
    print('      returning 2 components -- an output size : %d' % tot['param_size2'])
    print('      returning 1 component  -- not a size     : %d' % tot['param_size1'])
    print('    a baked filter parameter : %d  (%.1f%%)' % (tot['param_float'],
          100 * tot['param_float'] / max(1, r_)))
    print('    as zero / absent    : %d  (%.1f%%)' % (tot['param_zero'],
          100 * tot['param_zero'] / max(1, r_)))
    e = tot['resolved_edges'] + tot['unresolved_edges']
    print('edge slots            : %d   resolved %.2f%%' % (e, 100 * tot['resolved_edges'] / max(1, e)))
    # Programs named by a slot the layout table does not list. The keyed row is the
    # CONTROL: on records whose key is known the same predicate should find almost
    # nothing, and what it does find is the small-integer artifact's contribution.
    fb, kd = tot['fallback_records'], tot['keyed_records']
    print('programs off the layout table (fxmaps excluded):')
    print('    dropped-key records : %d  recovered %d  (%.2f%% of records gain one)'
          % (fb, tot['fallback_recovered'],
             100 * tot['fallback_records_gaining'] / max(1, fb)))
    print('    CONTROL keyed records: %d  recovered %d  (%.2f%%)'
          % (kd, tot['keyed_recovered'],
             100 * tot['keyed_records_gaining'] / max(1, kd)))
    print('bytes                 : %d   unexplained %d  (%.3f%%)' % (
        tot['bytes'], tot['unexplained'], 100 * tot['unexplained'] / max(1, tot['bytes'])))
    print('files with any unexplained bytes: %d' % len(unexplained))
    print()
    print('per filter (records, no program, unresolved edge slots):')
    print('  %-28s %10s %10s %12s' % ('filter', 'records', 'unread', 'unres edges'))
    for f, (n, np_, ue) in sorted(byfilter.items(), key=lambda kv: -kv[1][0])[:22]:
        name = FILTERS.get(f) or 'fid %d *' % f
        print('  %-28s %10d %9.0f%% %11.1f%%' % (name, n, 100 * np_ / n, 100 * ue / n))
    if unexplained:
        print('\nworst unexplained-byte files:')
        for frac, p in sorted(unexplained, reverse=True)[:6]:
            print('   %6.2f%%  %s' % (100 * frac, p.split('/')[-1]))
    if failed:
        print('\nparse failures:')
        for p, e in failed[:6]:
            print('   %-52s %s' % (p.split('/')[-1][:52], e))

if __name__ == '__main__':
    paths = [l.strip() for l in open('DISTINCT.txt') if l.strip()]
    main(paths[:int(sys.argv[1])] if len(sys.argv) > 1 else paths)
