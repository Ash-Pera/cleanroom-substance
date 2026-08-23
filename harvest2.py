#!/usr/bin/env python3
"""Second-stage harvest: discover repositories by NAME/TOPIC rather than code search.

Code search only indexes a narrow slice of GitHub and caps results, which is why the
first pass found 30-odd repositories. Repository search reaches much further; each hit is
then enumerated via the git-tree API for .sbs/.sbsar basename pairs.
"""
import json, os, subprocess, time

QUERIES=['substance designer','sbsar','substance graph','substance material',
 'substance designer nodes','sbs substance','substance procedural','allegorithmic',
 'substance tools','substance library','designer material','substance shader',
 'procedural texture substance','substance node','substance filter','sbsar unity',
 'substance painter designer','texture substance designer','sd nodes','substance pack']

def gh(a, t=90):
    try:
        r=subprocess.run(['gh']+a, capture_output=True, text=True, timeout=t)
        return r.stdout if r.returncode==0 else ''
    except Exception: return ''

def discover():
    repos=set()
    for q in QUERIES:
        out=gh(['search','repos',q,'--limit','100','--json','fullName'])
        if out:
            try:
                for x in json.loads(out): repos.add(x['fullName'])
            except Exception: pass
        print(f'  {q[:30]:<32} repos so far {len(repos)}', flush=True)
        time.sleep(1.5)
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
    os.makedirs('pairs5', exist_ok=True)
    repos=discover()
    print(f'\n{len(repos)} repositories to enumerate\n', flush=True)
    got=0
    for i,repo in enumerate(repos):
        t=tree(repo)
        if not t: continue
        sbs={}; sbsar={}
        for e in t:
            p=e.get('path','')
            if p.lower().endswith('.sbs'): sbs[os.path.basename(p)[:-4]]=p
            elif p.lower().endswith('.sbsar'): sbsar[os.path.basename(p)[:-6]]=p
        both=set(sbs)&set(sbsar)
        if not both: continue
        print(f'  [{i}/{len(repos)}] {repo:<44} pairs {len(both)}', flush=True)
        tag=repo.split('/')[-1].replace('.','_')
        for b in sorted(both):
            safe=f'{tag}__{b}'.replace('/','_')[:80]
            o1=f'pairs5/{safe}.sbs'; o2=f'pairs5/{safe}.sbsar'
            if os.path.exists(o1) and os.path.exists(o2): continue
            for path,out in ((sbs[b],o1),(sbsar[b],o2)):
                subprocess.run(['curl','-sL','-o',out,
                  f'https://raw.githubusercontent.com/{repo}/HEAD/{path}'],
                  capture_output=True, timeout=240)
            if all(os.path.exists(o) and os.path.getsize(o)>200 for o in (o1,o2)): got+=1
            else:
                for o in (o1,o2):
                    if os.path.exists(o): os.remove(o)
    print(f'\ndownloaded {got} new pairs')

if __name__=='__main__': main()
