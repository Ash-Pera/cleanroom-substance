#!/usr/bin/env python3
"""Does every attribution stay inside the structure it is attributed to?

    python3 tools/walk_partition.py [n_files]

THE INVARIANT, and why it is worth more than a render comparison. The walk yields
STRUCTURES -- record headers, FX nodes, FX entries -- each with a start. Sorted by start,
a structure's extent runs to the next structure's start. Every slot a decode reads ON
BEHALF OF a structure must lie inside that structure's extent, because two structures
cannot own the same word. A read outside it is claiming a neighbour's bytes, and that is
wrong BY CONSTRUCTION rather than wrong-looking.

WHY NOT JUST RENDER IT. Because the render has too many moving parts to answer a
structural question. Over this session a single decode change was measured three times
and gave three answers: the shared working tree contributed another session's edits
(3,968 of 6,077 records "changed" by an edit that changed nothing), `sbsruntime.SAMPLERS`
is module-level and never cleared at entry so a file renders differently depending on what
rendered before it, and most specimens ship no reference maps at all -- of 27 packages with
any image beside them only 5 carry the engine's own exported maps, and none of those
exercises the mechanism under test. A criterion that depends on all of that is not a
criterion. This one depends on nothing but the walk, which is independently established:
`decompose` reproduces `_compute_layout` on 925,701 of 925,706 records, from a different
model.

WHAT A VIOLATION MEANS. Not "this looks wrong" -- "this structure named a word that
belongs to the next structure". The decode may still produce a usable number; a program
found two structures away is real bytecode and will disassemble. The claim it makes about
WHOSE program it is, is what fails. That is exactly the failure the FX leaf scan and the
record-header word scan both had, and it is visible here without rendering anything.

THIS DOES NOT PROVE A DECODE CORRECT. Staying inside your own extent is necessary, not
sufficient: a rule can read the wrong slot within the right structure and pass. It bounds
the error rather than eliminating it, and it is falsifiable on 100% of the corpus instead
of on the 5 packages a render can score.

THE EXTENT IS A PROXY, and that is the one place to be careful. A structure's end is taken
as the START OF THE NEXT STRUCTURE the walk yields, which is exact only where structures
are laid out consecutively. FX children are reached by POINTER, so a node whose child
happens to sit three words along reads as a three-word node whether or not it is one. That
is why a violation here is a CONFLICT to explain, not a verdict on its own: either the
attribution crosses a boundary, or the structure is longer than the next start suggests and
the walk has placed something inside it. Both are decode problems; they are different ones.
Where a structure states its own extent -- an FX entry ends at its inline program, whose
length that program's first word gives -- that stated end is the better bound and this
check is the weaker form of it.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus                                                        # noqa: E402
import sbsasm                                                        # noqa: E402
import decompose                                                     # noqa: E402


def _naming_slots(rec, q, prog, limit):
    """Slot indices, relative to `q`, whose word names `prog` (`word + 52 == prog`)."""
    base = (q - rec.offset) // 4
    out = []
    for k in range(0, limit):
        j = base + k
        if j >= len(rec.words):
            break
        if rec.words[j] + 52 == prog:
            out.append(k)
    return out


def fx_violations(rec):
    """[(kind, tag, slot, extent_words)] for FX attributions outside their own structure."""
    try:
        items = list(rec.fx_walk())
    except Exception:
        return []
    starts = sorted({it[1] for it in items})
    nxt = {}
    for i, s in enumerate(starts):
        nxt[s] = starts[i + 1] if i + 1 < len(starts) else rec.end
    bad = []
    for it in items:
        kind, q, tag, prog = it[0], it[1], it[2], (it[3] if len(it) > 3 else None)
        if prog is None or q not in nxt:
            continue
        extent = (nxt[q] - q) // 4              # this structure's own width, in words
        if extent <= 0:
            continue
        slots = _naming_slots(rec, q, prog, 32)
        # ONLY when the structure cannot name it from inside. A program whose pointer also
        # appears within the extent is attributed legitimately, and a second copy of the
        # same word further along is a coincidence, not a claim. Counting every matching
        # slot instead would report one violation per repeat and flag correct attributions
        # that happen to have a duplicate word downstream.
        if slots and all(k >= extent for k in slots):
            bad.append((kind, tag, min(slots), extent))
    return bad


def header_violations(rec):
    """[(slot, end)] for record-header programs named past the walk's own header end."""
    if rec.filter_id in getattr(sbsasm, '_PAYLOAD_PROGRAM_FILTERS', {4, 20}):
        return []                                # payload legitimately holds pointers
    d = decompose.decompose(rec)
    if not d or d.get('end') is None:
        return []
    end = d['end']
    bad = []
    for p in rec.programs:
        idxs = [j for j, w in enumerate(rec.words) if w + 52 == p]
        if idxs and all(j >= end for j in idxs):
            bad.append((min(idxs), end))
    return bad


def census(paths=None):
    paths = paths or corpus.paths()
    fx = collections.Counter()
    fx_tot = collections.Counter()
    hdr = collections.Counter()
    hdr_tot = collections.Counter()
    for pp in paths:
        try:
            a = sbsasm.Assembly(pp)
        except Exception:
            continue
        for r in a.records:
            name = sbsasm.FILTERS.get(r.filter_id, str(r.filter_id))
            try:
                hv = header_violations(r)
            except Exception:
                hv = []
            hdr_tot[name] += len(list(r.programs) or ())
            hdr[name] += len(hv)
            if r.filter_id != 4:
                continue
            for kind, tag, k, extent in fx_violations(r):
                fx[(kind, 'slot %d of a %d-word structure' % (k, extent))] += 1
            try:
                items = list(r.fx_walk())
            except Exception:
                items = []
            fx_tot['attributions'] += sum(
                1 for it in items if len(it) > 3 and it[3] is not None)
    return fx, fx_tot, hdr, hdr_tot


def main(argv):
    n = int(argv[0]) if argv else 80
    paths = corpus.paths()[:n]
    fx, fx_tot, hdr, hdr_tot = census(paths)
    print('walk partition check -- %d files\n' % len(paths))
    print('RECORD HEADER: programs named only by a word past the walk\'s header end')
    print('  %-20s %10s %10s' % ('filter', 'violations', 'programs'))
    any_h = False
    for f in sorted(hdr, key=lambda k: -hdr[k]):
        if hdr[f]:
            print('  %-20s %10d %10d' % (f, hdr[f], hdr_tot[f]))
            any_h = True
    if not any_h:
        print('  none')
    print()
    print('FX STRUCTURES: a program named by a slot outside its own structure')
    if not fx:
        print('  none')
    else:
        for (kind, where), c in fx.most_common(20):
            print('  %-6s %-44s %5d' % (kind, where, c))
    n_att = fx_tot.get('attributions', 0)
    print('\n  total FX violations: %d of %d attributions (%.2f%%)'
          % (sum(fx.values()), n_att, 100.0 * sum(fx.values()) / max(n_att, 1)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
