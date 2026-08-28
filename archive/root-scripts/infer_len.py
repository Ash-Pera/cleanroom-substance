#!/usr/bin/env python3
"""Infer instruction length for an unknown opcode X.

Two independent signals, both required, to avoid the coverage-only overfitting that
previously promoted 0x0000 on 19% evidence:

  (a) operand validity - with X at value number V, every operand token of X must be a
      value number < V, and should be local (V - a small). Longer L is self-penalising
      because it claims more operands that must all check out.
  (b) continuation - the token at X + 2L must itself be a known opcode.

Sites are drawn only from breaks preceded by a clean run long enough to pin the
absolute value numbering. Specimens are split train/hold-out and the winner must hold
on both.
"""
import glob, os, struct, sys, collections
import code_region, runs
from census import LEN

MAXL = 10
LOCAL = 4096          # generous cap on how far back an operand may reference

def sites_for(paths, targets, min_run=5, cap=4000):
    """Collect (data, break_offset, value_number_at_break) per target opcode."""
    out = collections.defaultdict(list)
    for p in paths:
        try: d, spans, r = code_region.code_spans(p)
        except Exception: continue
        for lo, hi in spans:
            for st, cnt, blk in runs.runs(d, lo, hi):
                if blk in targets and cnt >= min_run and len(out[blk]) < cap:
                    ins, end = runs.instrs(d, st, cnt)
                    S = runs.base_vn(ins)
                    out[blk].append((d, end, S + cnt))
    return out

def score(sites, L):
    ok = 0
    for d, off, V in sites:
        if off + 2*L + 2 > len(d): continue
        args = struct.unpack_from('<%dH' % (L-1), d, off+2) if L > 1 else ()
        if any(a >= V or V - a > LOCAL for a in args): continue
        nxt = struct.unpack_from('<H', d, off + 2*L)[0]
        if nxt in LEN: ok += 1
    return ok / max(len(sites), 1)

def infer(sites):
    s = [(score(sites, L), L) for L in range(2, MAXL+1)]
    s.sort(reverse=True)
    return s
