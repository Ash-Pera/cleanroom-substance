#!/usr/bin/env python3
"""Run every arm of an `assume` question in ONE process against ONE pinned tree.

    python3 tools/sweep.py warp.reference_px --files new_opengameart
    python3 tools/sweep.py --list

WHY THIS EXISTS. Commit 4a53c57 withdrew a nine-arm sweep in full. Its arms had run as
nine sequential processes over eleven minutes, and four commits landed inside that window:
one bounding shuffle's header, one bounding `classified_programs`' scan, one changing
`refcompare` itself. The arms did not run against the same code, so no difference between
them could be attributed to the arm. It was a before/after difference wearing an A/B's
clothes. Ten sessions share this checkout and it takes roughly one commit every two
minutes, so that window is not an unlucky one -- it is the normal one.

Three hazards produce a convincing wrong number here, and this file closes all three by
construction rather than by advice.

1.  CODE DRIFT BETWEEN ARMS. The tree is materialised ONCE, from `git archive`, before any
    arm runs. Every arm then imports out of that one directory. Two arms cannot see
    different code because there is only one copy and it is read-only to the run.

2.  THE SHARED CHECKOUT. See `_child_source` -- the child process is started with a
    `sys.path` that does not contain the checkout's `tools/` at all, and it asserts on
    every module it imports that `__file__` resolves under the pinned root. A caller who
    wants to measure their uncommitted edits cannot do it by accident; they have to commit
    them, which is the honest way to make an edit measurable.

3.  `sbsruntime.SAMPLERS`. Module-level, and `render()` does not clear it at entry, so a
    file renders differently depending on what rendered before it in the same process
    (2,229 records then 2,288 on the same file). Cleared before every render here.

WHAT "ADMISSIBLE" MEANS AND WHAT IT DOES NOT. A result from this harness carries the
commit its arms shared, and the arms shared it BY CONSTRUCTION. That makes the DIFFERENCE
between two arms attributable to the arm. It says nothing about whether the reference maps
can decide the question -- `assume.py` records a knob that provably cannot reach a record
moving its channel by +0.29, and a fitted 256 that scores well only because 1,287 of 1,305
warp records in the packs are 256 wide. Same-moment removes one way to be wrong. It does
not make the packs an oracle.

DRIFT DURING THE RUN IS NOT A DEFECT HERE, which is worth stating because the withdrawn
sweep died of it. If HEAD moves while arms are running, the arms are unaffected: they read
the archive, not the checkout. The commit is recorded so the run can be reproduced, and
`moved_during_run` is reported for information, not as a verdict.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def repo_commit(repo=REPO):
    return subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'],
                                   text=True).strip()


def pin(commit='HEAD', repo=REPO, into=None):
    """Materialise `repo`'s tree at `commit` and return (root, resolved sha).

    `git archive` and not a copy of the checkout: the checkout holds ten sessions'
    in-flight edits, and the whole point is to not measure them.
    """
    sha = subprocess.check_output(['git', '-C', repo, 'rev-parse', commit],
                                  text=True).strip()
    root = into or tempfile.mkdtemp(prefix='sweep-%s-' % sha[:10])
    tar = subprocess.check_output(['git', '-C', repo, 'archive', sha])
    p = subprocess.Popen(['tar', '-x', '-C', root], stdin=subprocess.PIPE)
    p.communicate(tar)
    if p.returncode:
        raise RuntimeError('git archive %s did not extract' % sha)
    _complete_data(root, repo)
    return root, sha


#: Non-code files under tools/ that the archive cannot carry, because .gitignore
#: deliberately excludes them: `DISTINCT.txt` is the corpus LISTING, and this repository
#: does not redistribute the corpus. Pinning the code but not the data would make
#: `corpus.paths()` raise inside every arm -- which is how this was found.
def _complete_data(root, repo):
    """Copy tools/ DATA the archive lacks. Code is pinned; data is completed.

    THE ASYMMETRY IS THE WHOLE POINT and it must not be relaxed to `.py`. A `.py` copied
    from the checkout is exactly the uncommitted-edit leak this file exists to prevent, so
    the filter is on extension and the copy is reported. Data files are inputs to the
    measurement, not the thing under measurement: swapping the corpus listing changes which
    files an arm renders, and every arm still renders the same ones.
    """
    src_dir, dst_dir = os.path.join(repo, 'tools'), os.path.join(root, 'tools')
    copied = []
    if not os.path.isdir(src_dir):
        return copied
    for name in sorted(os.listdir(src_dir)):
        if name.endswith('.py') or name.startswith('.') or name == '__pycache__':
            continue
        s, d = os.path.join(src_dir, name), os.path.join(dst_dir, name)
        if os.path.isfile(s) and not os.path.exists(d):
            shutil.copy2(s, d)
            copied.append(name)
    if copied:
        print('sweep: completed pinned tree with untracked data: %s'
              % ', '.join(copied), file=sys.stderr)
    return copied


# The child. Written as source rather than imported so that the parent's own `sys.path` --
# which DOES contain the checkout -- cannot leak into it through inheritance.
_child_source = r'''
import json, os, sys, traceback
PINNED, REPO, SPEC = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
TOOLS = os.path.join(PINNED, 'tools')

# THE PREVENTION, and it is a path fact rather than a promise. The checkout's tools/ is
# never placed on the path, so `import render` has nothing to resolve to but the archive.
sys.path.insert(0, TOOLS)

import numpy as np
import assume, sbsasm, sbsruntime, render, manifest

def _under_pin(m):
    f = getattr(m, '__file__', None)
    return f is not None and os.path.realpath(f).startswith(os.path.realpath(PINNED))

# Belt as well as braces: a module reachable some other way (a stale .pth, a parent's
# PYTHONPATH, a package installed into site-packages) would defeat the path alone.
_stray = sorted(n for n, m in sys.modules.items()
                if getattr(m, '__file__', None)
                and os.path.realpath(m.__file__).startswith(os.path.realpath(REPO))
                and not _under_pin(m))
if _stray:
    print(json.dumps({'error': 'modules loaded from the shared checkout: %s' % _stray}))
    sys.exit(3)

def score_one(path, max_dim):
    """Per declared output: rendered or not, and how much it varies.

    `std` IS THE POINT, not a nicety. The failure this project ranks worst is a plausible
    wrong picture, and its commonest shape here is a flat one -- an output that renders
    to a single value and counts as a success. Reporting variation makes an arm that
    "unblocks" an output into a flat grey distinguishable from one that does not.
    """
    asm = sbsasm.Assembly(path)
    names = manifest.output_names(asm)
    sbsruntime.SAMPLERS.clear()
    produced, failures, _synth = render.render(asm, verbose=False, max_dim=max_dim)
    rows = []
    for uid, _fmt, _gray, rec in asm.outputs():
        if rec in produced:
            a = np.asarray(produced[rec], dtype=np.float64)
            rows.append({'name': names.get(uid), 'uid': uid, 'rec': rec, 'ok': True,
                         'mean': float(a.mean()), 'std': float(a.std()),
                         'shape': list(a.shape)})
        else:
            rows.append({'name': names.get(uid), 'uid': uid, 'rec': rec, 'ok': False,
                         'why': failures.get(rec, 'not rendered')})
    return {'records': len(asm.records), 'produced': len(produced),
            'failures': len(failures), 'outputs': rows}

out = {'arms': []}
for arm in SPEC['arms']:
    scopes = dict(SPEC.get('base_scope') or {})
    if arm is not None:
        scopes[SPEC['key']] = arm
    row = {'arm': arm, 'files': {}}
    try:
        with assume.scope(**scopes) as used:
            for path in SPEC['files']:
                try:
                    row['files'][path] = score_one(path, SPEC['max_dim'])
                except Exception as e:
                    row['files'][path] = {'error': '%s: %s' % (type(e).__name__, e)}
            row['assumption_records'] = len(used)
        row['active'] = {k: repr(v) for k, v in scopes.items()}
    except Exception as e:
        row['error'] = '%s: %s' % (type(e).__name__, e)
        row['traceback'] = traceback.format_exc()[-800:]
    out['arms'].append(row)
print(json.dumps(out))
'''


def run(key, files, arms=None, max_dim=64, base_scope=None, commit='HEAD', repo=REPO):
    """Every arm of `key`, in one child process, against one pinned tree.

    `arms=None` takes the candidates from the PINNED `assume.QUESTIONS`, not from the
    checkout's -- otherwise a question edited in the working tree would be swept with arms
    the pinned code cannot honour, and `assume.scope` would raise on every one of them.
    """
    root, sha = pin(commit, repo)
    if arms is None:
        arms = _pinned_arms(root, key)
    # A question this pinned tree does not know is a TYPO or a key that only exists in the
    # caller's working copy, and both used to render here as a clean run of zero arms --
    # a report with a commit on it and nothing measured, which reads like a null result
    # rather than a mistake.
    if not arms:
        raise KeyError('%r has no arms at %s; `--list` shows the %d questions it does have'
                       % (key, sha[:10], len(_pinned_questions(root))))
    spec = {'key': key, 'arms': list(arms), 'files': list(files),
            'max_dim': max_dim, 'base_scope': base_scope or {}}
    src = os.path.join(root, '_sweep_child.py')
    with open(src, 'w') as fh:
        fh.write(_child_source)
    env = dict(os.environ)
    # PYTHONPATH is inherited and the parent may well have the checkout on it.
    env.pop('PYTHONPATH', None)
    proc = subprocess.run([sys.executable, src, root, repo, json.dumps(spec)],
                          cwd=repo, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('sweep child failed (%d):\n%s' % (proc.returncode,
                                                             proc.stderr[-2000:]))
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    if 'error' in result:
        raise RuntimeError(result['error'])
    result.update({'key': key, 'commit': sha, 'pinned_root': root,
                   'max_dim': max_dim, 'base_scope': base_scope or {},
                   'shared_tree': True, 'moved_during_run': repo_commit(repo) != sha})
    return result


def _pinned_questions(root):
    src = ('import sys, json; sys.path.insert(0, %r); import assume; '
           'print(json.dumps({k: [repr(a) for a in (v or ())] '
           'for k, v in assume.QUESTIONS.items()}))' % os.path.join(root, 'tools'))
    return json.loads(subprocess.check_output([sys.executable, '-c', src], text=True))


def _pinned_arms(root, key):
    src = ('import sys, json; sys.path.insert(0, %r); import assume; '
           'print(json.dumps(list(assume.QUESTIONS.get(%r) or ())))'
           % (os.path.join(root, 'tools'), key))
    return json.loads(subprocess.check_output([sys.executable, '-c', src], text=True))


def report(result):
    lines = ['%s -- %d arms, commit %s, max_dim %s'
             % (result['key'], len(result['arms']), result['commit'][:10],
                result['max_dim'])]
    lines.append('arms shared the tree by construction (one `git archive`, one process)')
    if result['moved_during_run']:
        lines.append('NOTE: HEAD moved during the run; the arms are unaffected, they read '
                     'the archive')
    for row in result['arms']:
        lines.append('')
        lines.append('  arm %r' % (row['arm'],))
        if 'error' in row:
            lines.append('    ERROR %s' % row['error'])
            continue
        for path, r in sorted(row['files'].items()):
            if 'error' in r:
                lines.append('    %-40s ERROR %s' % (os.path.basename(path), r['error']))
                continue
            ok = [o for o in r['outputs'] if o['ok']]
            varying = [o for o in ok if o['std'] > 1e-6]
            lines.append('    %-40s %d/%d outputs, %d varying   (%d/%d records)'
                         % (os.path.basename(path), len(ok), len(r['outputs']),
                            len(varying), r['produced'], r['records']))
            for o in r['outputs']:
                lines.append('        %-14s %s' % (
                    o['name'],
                    ('mean %.4f std %.5f' % (o['mean'], o['std'])) if o['ok']
                    else 'BLOCKED: %s' % str(o['why'])[:70]))
    return '\n'.join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('key', nargs='?')
    ap.add_argument('files', nargs='*')
    ap.add_argument('--list', action='store_true', help='every question and its arms')
    ap.add_argument('--dim', type=int, default=64)
    ap.add_argument('--commit', default='HEAD')
    ap.add_argument('--json', help='write the full result here')
    args = ap.parse_args(argv)

    if args.list or not args.key:
        root, sha = pin(args.commit)
        qs = _pinned_questions(root)
        print('%d questions, %d arms, at %s'
              % (len(qs), sum(len(v) for v in qs.values()), sha[:10]))
        for k in sorted(qs):
            print('  %-28s %s' % (k, ', '.join(qs[k]) or '(continuous)'))
        return 0

    if not args.files:
        print('give at least one .sbsasm to render', file=sys.stderr)
        return 2
    result = run(args.key, args.files, max_dim=args.dim, commit=args.commit)
    print(report(result))
    if args.json:
        with open(args.json, 'w') as fh:
            json.dump(result, fh, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
