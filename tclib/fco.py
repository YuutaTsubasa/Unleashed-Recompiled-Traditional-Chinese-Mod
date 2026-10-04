import struct
class R:
    def __init__(s,d): s.d=d; s.o=0
    def u(s): v=struct.unpack_from('>i',s.d,s.o)[0]; s.o+=4; return v
    def f(s): v=struct.unpack_from('>f',s.d,s.o)[0]; s.o+=4; return v
    def s(s):
        n=s.u(); t=s.d[s.o:s.o+n].decode('latin1'); s.o+=n
        while s.o%4: s.o+=1
        return t
    def arr(s,n): v=list(struct.unpack_from('>%di'%n,s.d,s.o)); s.o+=4*n; return v
def read_fte(d):
    r=R(d); hdr=(r.u(),r.u()); texs=[]
    for i in range(r.u()): texs.append((r.s(),r.u(),r.u()))
    chars=[(r.u(),r.f(),r.f(),r.f(),r.f()) for i in range(r.u())]
    assert r.o==len(d)
    return hdr,texs,chars
def read_fco(d):
    r=R(d); hdr=(r.u(),r.u()); assert hdr[1]==0
    groups=[]
    for g in range(r.u()):
        gname=r.s(); cells=[]
        for c in range(r.u()):
            cell={'name':r.s()}
            cell['msg']=r.arr(r.u())
            assert r.u()==4
            cell['colors']=[r.arr(4) for i in range(3)]
            cell['end']=r.arr(3)
            cell['align']=r.u()
            cell['hl']=[r.arr(4) for i in range(r.u())]
            subs=[]
            for i in range(r.u()):
                a,b=r.u(),r.u(); subs.append((a,b,r.arr(r.u())))
            cell['subs']=subs
            cells.append(cell)
        groups.append((gname,cells))
    assert r.o==len(d),(r.o,len(d))
    return hdr,groups
def pstr(s):
    b=s.encode('latin1'); p=struct.pack('>i',len(b))+b
    return p+b'@'*((4-len(b)%4)%4)
def write_fco(hdr,groups):
    o=struct.pack('>ii',*hdr)+struct.pack('>i',len(groups))
    for gname,cells in groups:
        o+=pstr(gname)+struct.pack('>i',len(cells))
        for c in cells:
            o+=pstr(c['name'])+struct.pack('>i',len(c['msg']))+struct.pack('>%di'%len(c['msg']),*c['msg'])
            o+=struct.pack('>i',4)
            for col in c['colors']: o+=struct.pack('>4i',*col)
            o+=struct.pack('>3i',*c['end'])+struct.pack('>i',c['align'])
            o+=struct.pack('>i',len(c['hl']))
            for h in c['hl']: o+=struct.pack('>4i',*h)
            o+=struct.pack('>i',len(c['subs']))
            for a,b,m in c['subs']: o+=struct.pack('>3i',a,b,len(m))+struct.pack('>%di'%len(m),*m)
    return o
def write_fte(hdr,texs,chars):
    o=struct.pack('>ii',*hdr)+struct.pack('>i',len(texs))
    for n,w,h in texs: o+=pstr(n)+struct.pack('>ii',w,h)
    o+=struct.pack('>i',len(chars))
    for c in chars: o+=struct.pack('>iffff',*c)
    return o
