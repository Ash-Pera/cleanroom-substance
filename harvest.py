#!/usr/bin/env python3
"""Harvest .sbs/.sbsar pairs from GitHub.

Code search is narrow and capped, so it is used only to DISCOVER repositories; each
repository is then enumerated wholesale via the git-tree API and every .sbs with a
matching .sbsar basename is downloaded. Pairs are what matter: the .sbs supplies the
node labels, the .sbsar the compiled form.
"""
import json, os, subprocess, sys, time, collections

QUERIES = ['dynamicValue extension:sbs','paramNode extension:sbs','compNode extension:sbs',
 'sbsdescription extension:sbs','graphIdentifier extension:sbs','compFilter extension:sbs',
 'cartesian extension:sbs','samplelum extension:sbs','pow2 extension:sbs','log2 extension:sbs',
 'lerp extension:sbs','atan2 extension:sbs','iswizzle1 extension:sbs','mulscalar extension:sbs',
 'passthrough extension:sbs','toint1 extension:sbs','tofloat2 extension:sbs',
 'connRef extension:sbs','paramsArrayCell extension:sbs','outputBridging extension:sbs',
 'substance extension:sbs','rootnode extension:sbs','funcData extension:sbs']

def gh(args, timeout=90):
    try:
        r=subprocess.run(['gh']+args, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode==0 else ''
    except Exception:
        return ''

def discover():
    repos=set()
    for q in QUERIES:
        out=gh(['search','code',q,'--limit','100','--json','repository'])
        if out:
            try:
                for x in json.loads(out): repos.add(x['repository']['nameWithOwner'])
            except Exception: pass
        print(f'  {q[:34]:<36} total repos so far: {len(repos)}', flush=True)
        time.sleep(2.5)
    return sorted(repos)

def tree(repo):
    for br in ('HEAD','main','master'):
        out=gh(['api',f'repos/{repo}/git/trees/{br}?recursive=1'])
        if out:
            try:
                j=json.loads(out)
                if 'tree' in j: return j['tree']
            except Exception: pass
    return []

def main():
    os.makedirs('pairs4', exist_ok=True)
    repos=discover()
    print(f'\n{len(repos)} repositories discovered\n')
    got=0; skipped=0
    for repo in repos:
        t=tree(repo)
        if not t: continue
        sbs={}; sbsar={}
        for e in t:
            p=e.get('path','')
            if p.lower().endswith('.sbs'): sbs[os.path.basename(p)[:-4]]=p
            elif p.lower().endswith('.sbsar'): sbsar[os.path.basename(p)[:-6]]=p
        both=set(sbs)&set(sbsar)
        print(f'  {repo:<44} .sbs {len(sbs):>4}  .sbsar {len(sbsar):>4}  pairs {len(both):>4}', flush=True)
        tag=repo.split('/')[-1].replace('.','_')
        for b in sorted(both):
            safe=f'{tag}__{b}'.replace('/','_')[:80]
            o1=f'pairs4/{safe}.sbs'; o2=f'pairs4/{safe}.sbsar'
            if os.path.exists(o1) and os.path.exists(o2): skipped+=1; continue
            for path,out in ((sbs[b],o1),(sbsar[b],o2)):
                r=subprocess.run(['curl','-sL','-o',out,
                    f'https://raw.githubusercontent.com/{repo}/HEAD/{path}'],
                    capture_output=True, timeout=180)
            if os.path.exists(o1) and os.path.getsize(o1)>200 and \
               os.path.exists(o2) and os.path.getsize(o2)>200:
                got+=1
            else:
                for o in (o1,o2):
                    if os.path.exists(o): os.remove(o)
    print(f'\ndownloaded {got} new pairs ({skipped} already present)')

if __name__=='__main__': main()
