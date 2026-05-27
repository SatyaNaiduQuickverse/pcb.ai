#!/usr/bin/env python3
"""net_connectivity.py — cap-free per-net connectivity (DRC unconnected caps ~499).
Node-based union-find: pads, vias, track-endpoints (2/track, unioned), zone-per-layer.
Union on geometric touch incl track-chains (coincident endpoints) + track/via/pad-in-zone-fill.
Usage: python3 net_connectivity.py <board> <net> [net2 ...]"""
import sys, pcbnew
tomm=pcbnew.ToMM
def vec(x,y): return pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y))
def check(b, net, tol=0.18):
    pads=[]
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname()!=net: continue
            ls=set(p.GetLayerSet().CuStack()); bb=p.GetBoundingBox()
            pads.append((f.GetReference()+'.'+p.GetPadName(), ls,
                         (tomm(bb.GetLeft())-0.05,tomm(bb.GetTop())-0.05,tomm(bb.GetRight())+0.05,tomm(bb.GetBottom())+0.05),
                         ((tomm(bb.GetLeft())+tomm(bb.GetRight()))/2,(tomm(bb.GetTop())+tomm(bb.GetBottom()))/2)))
    tracks=[];vias=[]
    for t in b.GetTracks():
        if t.GetNetname()!=net: continue
        if t.GetClass()=='PCB_VIA': c=t.GetPosition(); vias.append((tomm(c.x),tomm(c.y)))
        else: s,e=t.GetStart(),t.GetEnd(); tracks.append((t.GetLayer(),(tomm(s.x),tomm(s.y)),(tomm(e.x),tomm(e.y))))
    zones=[(z.GetLayer(),z) for z in b.Zones() if z.GetNetname()==net and z.IsFilled()]
    # nodes: 0..P-1 pads ; vias ; track endpoints (2 each) ; zone nodes
    P=len(pads)
    if P<=1: return P,1,[[p[0] for p in pads]]
    nodes=[]  # list of ('pad',i)/('via',j)/('tep',k,which)/('zone',z)
    idx={}
    def nid(key):
        if key not in idx: idx[key]=len(nodes); nodes.append(key)
        return idx[key]
    for i in range(P): nid(('pad',i))
    par={}
    def find(x):
        par.setdefault(x,x)
        while par[x]!=x: par[x]=par[par[x]]; x=par[x]
        return x
    def uni(a,c): par[find(a)]=find(c)
    def hit(z,zl,x,y):
        try: return z.HitTestFilledArea(zl,vec(x,y))
        except: return False
    def in_pad(i,x,y,layer=None):
        ls,g=pads[i][1],pads[i][2]
        if layer is not None and layer not in ls: return False
        return g[0]<=x<=g[2] and g[1]<=y<=g[3]
    def near(a,bp): return abs(a[0]-bp[0])<=tol and abs(a[1]-bp[1])<=tol
    # track endpoint nodes; union the 2 ends of each track
    for k,(tl,a,bp) in enumerate(tracks):
        na=nid(('tep',k,0)); nb=nid(('tep',k,1)); uni(na,nb)
    via_n=[nid(('via',j)) for j in range(len(vias))]
    zone_n={zi:nid(('zone',zi)) for zi in range(len(zones))}
    # union track endpoints to: pads, vias, other coincident track endpoints, zones
    teps=[(k,0,tracks[k][1],tracks[k][0]) for k in range(len(tracks))]+[(k,1,tracks[k][2],tracks[k][0]) for k in range(len(tracks))]
    for (k,w,pt,tl) in teps:
        nn=nid(('tep',k,w)); x,y=pt
        for i in range(P):
            if in_pad(i,x,y,tl): uni(nn,nid(('pad',i)))
        for j,vp in enumerate(vias):
            if near(pt,vp): uni(nn,via_n[j])
        for (k2,w2,pt2,tl2) in teps:
            if (k2,w2)!=(k,w) and tl2==tl and near(pt,pt2): uni(nn,nid(('tep',k2,w2)))
        for zi,(zl,z) in enumerate(zones):
            if zl==tl and hit(z,zl,x,y): uni(nn,zone_n[zi])
    # vias to pads + zones (via spans all cu layers)
    for j,vp in enumerate(vias):
        for i in range(P):
            if in_pad(i,*vp): uni(via_n[j],nid(('pad',i)))
        for zi,(zl,z) in enumerate(zones):
            if hit(z,zl,*vp): uni(via_n[j],zone_n[zi])
    # pads in zone fill (shared layer)
    for zi,(zl,z) in enumerate(zones):
        for i in range(P):
            if zl in pads[i][1] and hit(z,zl,*pads[i][3]): uni(nid(('pad',i)),zone_n[zi])
    comps={}
    for i in range(P): comps.setdefault(find(nid(('pad',i))),[]).append(pads[i][0])
    return P,len(comps),list(comps.values())
if __name__=="__main__":
    b=pcbnew.LoadBoard(sys.argv[1])
    for net in sys.argv[2:]:
        n,c,g=check(b,net)
        print(f"{net}: {n} pads, {c} group(s) ratsnest={c-1}", "OK-CONNECTED" if c<=1 else "SPLIT")
        if c>1:
            for grp in sorted(g,key=len,reverse=True)[:6]: print("   ",grp[:6],"..." if len(grp)>6 else "")
