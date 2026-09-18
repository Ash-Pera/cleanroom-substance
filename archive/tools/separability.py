#!/usr/bin/env python3
"""Which named bits are SEPARABLE from their neighbours, and which are not.

THE ERROR THIS EXISTS TO CATCH. A per-bit claim is usually argued by scoring a model with
the bit against a model without it, over a population. That argument is worthless when
another bit is set on exactly the same members: the two are one column, every score is
identical, and a tie reads as a confirmation.

THE POPULATION IS PART OF THE CLAIM, and getting that wrong is how this file came to exist.
Bits 7 and 31 were called "co-extensive 4/4 both ways", and a retraction was argued on it.
They are co-extensive over `FX_ENTRY_PROGS`' KEY SET -- 57 tags -- and NOT over the corpus,
where bit 31 is a strict subset of bit 7 and 474 entries across 11 tags separate them. The
confound was an artifact of the subset it was measured on. So this file always enumerates
from `corpus.paths()`, and a caller narrowing the population must say so.

The near-miss that prompted it: after that, bits 18/26/30 were the candidates for what
"really" decided the entry extent -- three of them, indistinguishable over the three tags
that carry bit 31. That one was caught by being asked whether it was a single bit at all,
and the answer was that the extent is not bit-decided (see `sbsasm.fx_entry_width`).

So before naming a bit, ask this file whether the corpus can tell it from its neighbours.
A bit with a perfect partner is NOT NECESSARILY WRONG -- it is UNARGUED, and the evidence
offered for it is evidence for the partner too.

    python3 archive/tools/separability.py
"""

import sys, os, collections

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools")
)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbsasm, provenance, corpus


def permitted_files(limit=None):
    """Corpus paths whose manifest declares no excluded author.

    ENUMERATION IS `corpus.paths()`, not a second listing reader. The first version of this
    walked DISTINCT.txt itself and was a duplicate of that function -- the exact hazard
    `sbsasm.fx_entry_walk`'s note describes, and it differs in the ways that matter (paths()
    deduplicates by CONTENT, so a corpus with two copies of one file weights it once here
    and twice there, which silently doubles that file's masks in a separability count).

    The provenance gate stays here and is a PREDICATE CALL: `manifest_authors` against
    `EXCLUDED_AUTHORS`, never a retyped string.
    """
    out = []
    for full in corpus.paths():
        if provenance.manifest_authors(full) & set(provenance.EXCLUDED_AUTHORS):
            continue
        out.append(full)
        if limit and len(out) >= limit:
            break
    return out


def separability(masks, bits, weights=None):
    """{bit: (n_set, [(partner, relation)])} over a multiset of mask words.

    `relation` is 'identical' when the two bits are set on exactly the same masks,
    'implies' when this bit's set is a strict subset of the partner's (so the evidence
    for this bit is also evidence for the partner, but not conversely).
    """
    weights = weights or {m: 1 for m in masks}
    sets = {b: {m for m in masks if (m >> b) & 1} for b in bits}
    out = {}
    for b in bits:
        s = sets[b]
        if not s:
            out[b] = (0, [])
            continue
        rel = []
        for o in bits:
            if o == b or not sets[o]:
                continue
            if sets[o] == s:
                rel.append((o, "identical"))
            elif s < sets[o]:
                rel.append((o, "implies"))
        out[b] = (sum(weights.get(m, 1) for m in s), rel)
    return out


def report(title, masks, bits, weights=None, names=None):
    print()
    print("=" * 76)
    print(title)
    print("  distinct masks: %d" % len(set(masks)))
    sep = separability(list(set(masks)), bits, weights)
    bad = [(b, n, r) for b, (n, r) in sorted(sep.items()) if r]
    ok = [(b, n) for b, (n, r) in sorted(sep.items()) if not r and n]
    absent = [b for b, (n, r) in sorted(sep.items()) if not n]
    for b, n, r in bad:
        ident = [o for o, k in r if k == "identical"]
        impl = [o for o, k in r if k == "implies"]
        nm = (names or {}).get(b) or ""
        print(
            "  bit %-2d %-16s n=%-7d NOT SEPARABLE%s%s"
            % (
                b,
                nm,
                n,
                "  identical to " + ",".join(str(x) for x in ident) if ident else "",
                "  implies " + ",".join(str(x) for x in impl) if impl else "",
            )
        )
    if ok:
        print(
            "  separable: "
            + ", ".join(
                "%d%s"
                % (
                    b,
                    ("(" + (names or {}).get(b, "") + ")")
                    if (names or {}).get(b)
                    else "",
                )
                for b, _n in ok
            )
        )
    if absent:
        print("  never set here: " + ", ".join(str(b) for b in absent))


def main():
    files = permitted_files()
    print("permitted compiled specimens: %d" % len(files))

    entry_tags = collections.Counter()
    w0 = collections.Counter()
    w1_by_filter = collections.defaultdict(collections.Counter)
    for f in files:
        try:
            asm = sbsasm.Assembly(f)
        except Exception:
            continue
        for rec in asm.records:
            fid = getattr(rec, "filter_id", None)
            if len(rec.words) > 0:
                w0[rec.words[0]] += 1
            if len(rec.words) > 1 and fid is not None:
                w1_by_filter[fid][rec.words[1]] += 1
            if fid != 4:
                continue
            try:
                for _o, tag, _p in rec.fx_table():
                    if (tag & 0xF) == 8:
                        entry_tags[tag] += 1
            except Exception:
                pass

    names = {b: (n or "") for b, n, _w in sbsasm.FX_PARAM_BITS}
    report(
        "FX ENTRY TAGS -- FX_PARAM_BITS, the table that produced both errors",
        list(entry_tags.elements()),
        [b for b, _n, _w in sbsasm.FX_PARAM_BITS],
        entry_tags,
        names,
    )

    report(
        "RECORD WORD 0 -- the class word, bits 16..31",
        list(w0.elements()),
        list(range(16, 32)),
        w0,
    )

    for fid, cnt in sorted(w1_by_filter.items(), key=lambda kv: -sum(kv[1].values()))[
        :6
    ]:
        report(
            "RECORD WORD 1 -- filter_id %d (%d records, %d distinct)"
            % (fid, sum(cnt.values()), len(cnt)),
            list(cnt.elements()),
            list(range(0, 32)),
            cnt,
        )


if __name__ == "__main__":
    main()
