import sys,struct,collections; sys.path.insert(0,'.')
import standalone_parse as S, isa
FILTS=set([0x00,0x02,0x04,0x06,0x08,0x0C,0x0E,0x14,0x1E,0x20,0x24,0x28,0x2A])
FMT={0x01,0x02,0x03,0x05,0x07,0x08}
res=collections.Counter(); byver=collections.defaultdict(collections.Counter); rows=[]
for a in [l.strip() for l in open('DISTINCT.txt')]:
    try:
        d=open(a,'rb').read(); r=S.parse(a)
    except Exception: continue
    ver=struct.unpack_from('<I',d,4)[0]>>16
    c,dir0=r['dir_count'],r['dir_at']
    base=dir0-0x38
    if c<1 or dir0+4*c>len(d): continue
    pre=post=0; ndesc=0
    for e in struct.unpack_from('<%dI'%c,d,dir0):
        o=e+52
        if o+8>len(d): continue
        tag,off=struct.unpack_from('<II',d,o)
        b=tag.to_bytes(4,'little')
        if b[0] in (0x20,0x21) and b[2] in (0x08,0x18) and b[3] in FMT and 0<=off<=base: ndesc+=1
        if o+40>len(d): continue
        w=struct.unpack_from('<10I',d,o)
        if (((w[0]&0xFFFF)&0xFF)&~1) not in FILTS: continue
        for sl in range(1,10):
            p=w[sl]+52
            if p+4>len(d): continue
            n=struct.unpack_from('<H',d,p)[0]
            if not (1<=n<=20000): continue
            q=p+2; k=0
            while k<n and q+2<=len(d):
                op=struct.unpack_from('<H',d,q)[0]
                L=isa.LEN.get(op)
                if not L: break
                q+=2*L; k+=1
            if k==n:
                if p<dir0: pre+=1
                else: post+=1
                break
    if pre+post<5: continue
    lay='B (code before directory)' if pre>post else 'A (code interleaved with records)'
    res[lay]+=1; byver[ver][lay]+=1
    rows.append((a,lay,pre,post,ndesc,base))
print('layout across {} distinct specimens with >=5 bytecode blocks:'.format(len(rows)))
for k,v in res.most_common(): print('   {:<38}{:>5}  ({:.0f}%)'.format(k,v,100.0*v/len(rows)))
print('\nby version:')
for ver in sorted(byver):
    t=sum(byver[ver].values())
    a_=byver[ver].get('A (code interleaved with records)',0)
    b_=byver[ver].get('B (code before directory)',0)
    print('   v{:<3} n={:<5} A={:<5} B={:<5}'.format(ver,t,a_,b_))
print('\nresource descriptors present?')
for lay in res:
    g=[x for x in rows if x[1]==lay]
    wd=sum(1 for x in g if x[4]>0)
    print('   {:<38}{}/{} have descriptors'.format(lay,wd,len(g)))
print('\nlayout B specimens (first 12):')
for a,lay,pre,post,nd,base in rows:
    if lay.startswith('B'): print('   {:<40} pre={:<5} post={:<4} descs={}'.format(a.split('/')[1][2:][:38],pre,post,nd))
