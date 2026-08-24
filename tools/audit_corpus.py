#!/usr/bin/env python3
"""Run sbsasm.Assembly over the corpus and report where the model still fails.

The point is the failure columns. A segmenter that silently guesses looks perfect;
this one is meant to make its own gaps countable.
"""
import collections, sys
from sbsasm import Assembly, FILTERS, UNNAMED, LAYOUTS, LAYOUT_MASK

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
            par = r.parameter
            if par is None:
                byfilter[f][1] += 1
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
                else:
                    tot['param_unread'] += 1
            elif par[0] == 'program':
                tot['param_program'] += 1
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
    print('  main parameter resolved: %d  (%.1f%%)' % (r_ - tot['no_param'],
          100 * (r_ - tot['no_param']) / max(1, r_)))
    print('    record has no parameter slot: %d  (%.2f%%)  -- correct, not a miss'
          % (tot['param_absent'], 100 * tot['param_absent'] / max(1, r_)))
    print('    genuinely unread     : %d  (%.2f%%)'
          % (tot['param_unread'], 100 * tot['param_unread'] / max(1, r_)))
    print('    as a program        : %d  (%.1f%%)' % (tot['param_program'],
          100 * tot['param_program'] / max(1, r_)))
    print('    as a baked float    : %d  (%.1f%%)' % (tot['param_float'],
          100 * tot['param_float'] / max(1, r_)))
    print('    as zero / absent    : %d  (%.1f%%)' % (tot['param_zero'],
          100 * tot['param_zero'] / max(1, r_)))
    e = tot['resolved_edges'] + tot['unresolved_edges']
    print('edge slots            : %d   resolved %.2f%%' % (e, 100 * tot['resolved_edges'] / max(1, e)))
    print('bytes                 : %d   unexplained %d  (%.3f%%)' % (
        tot['bytes'], tot['unexplained'], 100 * tot['unexplained'] / max(1, tot['bytes'])))
    print('files with any unexplained bytes: %d' % len(unexplained))
    print()
    print('per filter (records, no program, unresolved edge slots):')
    print('  %-28s %10s %10s %12s' % ('filter', 'records', 'no param', 'unres edges'))
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
