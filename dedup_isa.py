import sys,struct,collections; sys.path.insert(0,'.')
import standalone_parse as S, isa
FILTS=set([0x00,0x02,0x04,0x06,0x08,0x0C,0x0E,0x14,0x1E,0x20,0x24,0x28,0x2A])
known=collections.defaultdict(set)
for l in open('OPCODES.md'):
    if not l.startswith('| '): continue
    c=[x.strip().strip('`') for x in l.strip().strip('|').split('|')]
    if len(c)<10 or c[0]=='type': continue
    try: known[c[0]].add(int(c[1],16))
    except ValueError: pass
TY={0:'bool',1:'float',2:'int',3:'t3'}
cnt=collections.Counter(); fl=collections.defaultdict(set)
for a in [l.strip() for l in open('DISTINCT.txt')]:
    try:
        d=open(a,'rb').read(); r=S.parse(a)
    except Exception: continue
    c,dir0=r['dir_count'],r['dir_at']
    if c<1 or dir0+4*c>len(d): continue
    seen=set()
    for e in struct.unpack_from('<%dI'%c,d,dir0):
        o=e+52
        if o+40>len(d): continue
        w=struct.unpack_from('<10I',d,o)
        if (((w[0]&0xFFFF)&0xFF)&~1) not in FILTS: continue
        for sl in range(1,10):
            p=w[sl]+52
            if p+4>len(d) or p in seen: continue
            n=struct.unpack_from('<H',d,p)[0]
            if not (1<=n<=20000): continue
            q=p+2; k=0; ops=[]
            while k<n and q+2<=len(d):
                op=struct.unpack_from('<H',d,q)[0]
                L=isa.LEN.get(op)
                if not L: break
                ops.append(op); q+=2*L; k+=1
            if k==n:
                seen.add(p)
                for op in ops: cnt[op]+=1; fl[op].add(a)
                break
tot=sum(cnt.values())
allk=set().union(*known.values())
ok=sum(v for op,v in cnt.items() if (op&0x3F) in known.get(TY.get((op>>8)&3,''),set()))
print('instructions                        : {:,}'.format(tot))
print('operation id catalogued for its type : {:.3f}%   (was 96.926% with duplicates)'.format(100.0*ok/max(tot,1)))
sel=[op for op in cnt if len(fl[op])>=20]
print('opcodes in 20+ DISTINCT specimens    : {}   (was 95)'.format(len(sel)))
bad=[op for op in sel if (op&0x3F) not in allk]
print('of those, uncatalogued operation id  : {}  {}'.format(len(bad),['0x%04X (op 0x%02X, %d files)'%(o,o&0x3F,len(fl[o])) for o in bad]))
