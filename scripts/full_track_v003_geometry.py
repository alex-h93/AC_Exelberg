"""Offline v003 top-skin/apron utilities. No geographic inputs are modified."""
import numpy as np
from prototype_geometry import require
import full_track_v002_geometry as G


def extract_top(a):
    v=a['vertices']; f=a['triangles']; n=len(v)//2
    require(len(v)%2==0 and np.array_equal(v[:n,:2],v[n:,:2]),'Not the known v002 closed_slab layout')
    ids=np.flatnonzero((f<n).all(1)); top=f[ids]
    cuv=a['corner_uv'][ids] if 'corner_uv' in a else a['uv'][top]
    return v[:n].copy(),top.copy(),cuv.copy()


def triangles_key(v,f):
    t=v[f].astype('<f4'); start=np.lexsort((t[:,:,2],t[:,:,1],t[:,:,0]),axis=1)[:,0]
    t=np.take_along_axis(t,((start[:,None]+np.arange(3))%3)[:,:,None],axis=1).copy()
    t[t==0]=0
    return t.reshape(-1,9).view('V36').ravel()


def unify(parts,epsilon=.0015):
    """Weld the contact skin once, road-first and immutable; collapse tiny cut edges.

    Float32 seam discrepancies are snapped, not covered by a second contact layer.
    Source cell grid lines are pinned so orthophoto ownership stays meaningful.
    """
    verts=[]; faces=[]; roles=[]; cells=[]; lookup={}; bins={}; fixed=[]; moved=[]
    for role,v,f,cell in parts:
        remap=[]
        for q in v:
            key=tuple(q[:2]); found=lookup.get(key)
            if found is None:
                b=tuple(np.floor(q[:2]/epsilon).astype(int)); best=epsilon; candidate=None
                if role!='ROAD':
                    for dx in (-1,0,1):
                        for dy in (-1,0,1):
                            for j in bins.get((b[0]+dx,b[1]+dy),()):
                                dist=np.linalg.norm(q[:2]-verts[j][:2])
                                if dist<best:best=dist;candidate=j
                if candidate is None:
                    found=len(verts);verts.append(q.copy());fixed.append(role=='ROAD');bins.setdefault(b,[]).append(found)
                else:found=candidate;moved.append(float(best))
                lookup[key]=found
            remap.append(found)
        ff=np.asarray(remap)[f];faces.extend(ff);roles.extend([role]*len(f));cells.extend(cell)
    v=np.asarray(verts,dtype=np.float32); f=np.asarray(faces,dtype=np.int32);roles=np.asarray(roles);cells=np.asarray(cells)
    original=len(f); keep=(f[:,0]!=f[:,1])&(f[:,1]!=f[:,2])&(f[:,2]!=f[:,0]);f,roles,cells=f[keep],roles[keep],cells[keep]
    return v,f,roles,cells,dict(weld_tolerance_m=epsilon,snapped_vertices=len(moved),max_snap_m=max(moved,default=0),collapsed_triangles=original-len(f))


def quality(v,f):
    tri=v[f].astype(float); d=np.roll(tri,-1,axis=1)-tri
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]); horizontal=cross[:,2]
    edge=np.linalg.norm(d[:,:,:2],axis=2).max(1); altitude=horizontal/edge
    slope=np.linalg.norm(cross[:,:2],axis=1)/np.maximum(horizontal,1e-30)
    return horizontal,altitude,slope


def local_nearest(xy,p,size=64.):
    """Exact candidates within40m, vectorized spatial bins; distant points untouched."""
    buckets={};a=p[:-1,:2];dd=np.diff(p[:,:2],axis=0);length=(dd*dd).sum(1)
    for i,(lo,hi) in enumerate(zip(np.minimum(a,a+dd)-40,np.maximum(a,a+dd)+40)):
        l=np.floor(lo/size).astype(int);h=np.floor(hi/size).astype(int)
        for x in range(l[0],h[0]+1):
            for y in range(l[1],h[1]+1):buckets.setdefault((x,y),[]).append(i)
    keys,inv=np.unique(np.floor(xy/size).astype(int),axis=0,return_inverse=True)
    indices=np.zeros(len(xy),dtype=int);frac=np.zeros(len(xy));dist=np.full(len(xy),1e6)
    for j,key in enumerate(keys):
        ids=buckets.get(tuple(key))
        if not ids:continue
        ids=np.asarray(ids);rows=np.flatnonzero(inv==j)
        for rr in np.array_split(rows,max(1,int(np.ceil(len(rows)/512)))):
            delta=xy[rr,None,:]-a[ids];t=np.clip((delta*dd[ids]).sum(2)/length[ids],0,1)
            d=np.linalg.norm(delta-t[:,:,None]*dd[ids],axis=2);k=d.argmin(1);indices[rr]=ids[k];frac[rr]=t[np.arange(len(rr)),k];dist[rr]=d[np.arange(len(rr)),k]
    return indices,frac,dist


def apron(v,p):
    i,t,d=local_nearest(v[:,:2],p);center=p[i]*(1-t[:,None])+p[i+1]*t[:,None]
    z=v[:,2].astype(float).copy();target=center[:,2]+.02*np.maximum(d-3.75,0)
    w=np.clip((d-20)/20,0,1);w=w*w*(3-2*w)
    v=v.copy();v[:,2]=(target*(1-w)+z*w).astype(np.float32)
    return v,i,t,d,v[:,2].astype(float)-z


def relax_apron(v,f,roadmask,dist,iterations=1200):
    """Positive-weight harmonic extension, road Dirichlet controls immutable.

    The near-road plateau is a design, not a measured change to source DTM.
    """
    v=v.copy();fixed=np.zeros(len(v),bool);fixed[np.unique(f[roadmask])]=True;fixed|=dist>=20
    # Cotangent finite-element Laplacian reproduces linear planes on irregular
    # clipped topology, unlike valence/inverse-edge averaging. Solve its SPD
    # Dirichlet system with local NumPy preconditioned conjugate gradients.
    tri=v[f,:2].astype(float);u=tri[:,1]-tri[:,0];w=tri[:,2]-tri[:,0];area=u[:,0]*w[:,1]-u[:,1]*w[:,0]
    ee=[];ww=[]
    for i,j,k in ((0,1,2),(1,2,0),(2,0,1)):
        ee.append(f[:,[i,j]]);ww.append(((tri[:,i]-tri[:,k])*(tri[:,j]-tri[:,k])).sum(1)/area)
    edges,inv=np.unique(np.sort(np.concatenate(ee),1),axis=0,return_inverse=True);weight=np.bincount(inv,weights=np.concatenate(ww))
    active=~fixed[edges].all(1);edges=edges[active];weight=weight[active];a,b=edges.T
    diag=np.bincount(a,weights=weight,minlength=len(v))+np.bincount(b,weights=weight,minlength=len(v));movable=(~fixed)&(diag>0)
    z=v[:,2].astype(float);boundary=z.copy();boundary[movable]=0
    def multiply(x):
        return diag*x-np.bincount(a,weights=weight*x[b],minlength=len(v))-np.bincount(b,weights=weight*x[a],minlength=len(v))
    rhs=-multiply(boundary);rhs[~movable]=0
    x=z.copy();x[~movable]=0;r=rhs-multiply(x);r[~movable]=0;pre=np.zeros(len(v));pre[movable]=r[movable]/diag[movable];direction=pre.copy();rz=r@pre
    for iteration in range(iterations):
        ap=multiply(direction);ap[~movable]=0;alpha=rz/(direction@ap);x+=alpha*direction;r-=alpha*ap
        if np.max(np.abs(r[movable])/diag[movable])<1e-8:break
        pre[movable]=r[movable]/diag[movable];new=r@pre;direction=pre+(new/rz)*direction;rz=new
    z[movable]=x[movable];v[:,2]=z.astype(np.float32)
    return v


def limit_slopes(v,f,fixed_vertices,limit=.30,iterations=400):
    """Project reachable triangle gradients; immutable asphalt/shoulder controls."""
    v=v.copy();z=v[:,2].astype(float);xy=v[f,:2].astype(float);a=xy[:,1]-xy[:,0];b=xy[:,2]-xy[:,0];det=a[:,0]*b[:,1]-a[:,1]*b[:,0]
    c1=np.c_[b[:,1],-b[:,0]]/det[:,None];c2=np.c_[-a[:,1],a[:,0]]/det[:,None];coeff=np.stack([-c1-c2,c1,c2],1)
    movable=np.ones(len(v),bool);movable[fixed_vertices]=False
    for _ in range(iterations):
        gradient=(coeff*z[f][:,:,None]).sum(1);norm=np.linalg.norm(gradient,axis=1);bad=np.flatnonzero(norm>limit+1e-5)
        if not len(bad):break
        derivative=(coeff[bad]*gradient[bad,None,:]/norm[bad,None,None]).sum(2);derivative*=movable[f[bad]];denom=(derivative**2).sum(1)
        require((denom>1e-20).all(),'Fixed shoulder itself exceeds slope limit')
        change=-(norm[bad]-limit)[:,None]*derivative/denom[:,None]
        ids=f[bad].ravel();sums=np.bincount(ids,weights=change.ravel(),minlength=len(v));counts=np.bincount(ids,minlength=len(v));use=counts>0;z[use]+=sums[use]/counts[use]
    v[:,2]=z.astype(np.float32);return v


def collapse_micro_edges(v,f,roles,cells,epsilon=.008):
    fixed=np.zeros(len(v),bool);fixed[np.unique(f[roles=='ROAD'])]=True;removed=0
    for _ in range(4):
        edges=np.unique(np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),1),axis=0)
        length=np.linalg.norm(v[edges[:,0],:2]-v[edges[:,1],:2],axis=1);short=edges[length<epsilon]
        remap=np.arange(len(v));count=0;adj={}
        for i,face in enumerate(f):
            for vertex in face:adj.setdefault(int(vertex),set()).add(i)
        def resolve(a):
            while remap[a]!=a:a=remap[a]
            return int(a)
        for a,b in short:
            a,b=resolve(a),resolve(b)
            if a==b or (fixed[a] and fixed[b]):continue
            if fixed[b]:a,b=b,a
            incident=adj.get(a,set())|adj.get(b,set());local=np.array([[resolve(i) for i in f[j]] for j in incident]);local[local==b]=a
            nonzero=(local[:,0]!=local[:,1])&(local[:,0]!=local[:,2])&(local[:,1]!=local[:,2]);tri=v[local[nonzero],:2].astype(float)
            d0=tri[:,1]-tri[:,0];d1=tri[:,2]-tri[:,0]
            if ((d0[:,0]*d1[:,1]-d0[:,1]*d1[:,0])<=1e-10).any():continue
            remap[b]=a;adj[a]=incident;adj[b]=set();count+=1
        if not count:break
        while not np.array_equal(remap,remap[remap]):remap=remap[remap]
        f=remap[f];keep=(f[:,0]!=f[:,1])&(f[:,0]!=f[:,2])&(f[:,1]!=f[:,2]);removed+=int((~keep).sum());f,roles,cells=f[keep],roles[keep],cells[keep]
    return v,f,roles,cells,removed


def dissolve_cap_cuts(v,f,roles,cells,p):
    """Remove one-cell terrain fan T-junctions on immutable asphalt end edges.

    A float32 interior point cannot always lie exactly on an arbitrary float32
    segment. A single unsplit shared edge is preferable to numerical overlap.
    """
    from prototype_geometry import ribbon
    edge,_=ribbon(p,[-3.,0.,3.]);edge=edge.astype(np.float32).reshape(-1,3,3)
    fixed=set(np.unique(f[roles=='ROAD']).tolist());candidates=set()
    for endpoint in (0,len(p)-1):
        for a,b in zip(edge[endpoint,:-1,:2],edge[endpoint,1:,:2]):
            d=b.astype(float)-a;t=np.clip(((v[:,:2]-a)*d).sum(1)/(d@d),0,1);dist=np.linalg.norm(v[:,:2]-a-t[:,None]*d,axis=1)
            candidates.update(i for i in np.flatnonzero((dist<.002)&(t>1e-4)&(t<1-1e-4)) if i not in fixed)
    dissolved=0
    for point in sorted(candidates):
        star=np.flatnonzero((f==point).any(1))
        if not len(star) or len(set(roles[star]))!=1 or roles[star[0]]=='ROAD' or len(set(cells[star]))!=1:continue
        ee=np.concatenate([f[star][:,[0,1]],f[star][:,[1,2]],f[star][:,[2,0]]]);_,idx,count=np.unique(np.sort(ee,1),axis=0,return_index=True,return_counts=True);boundary=ee[idx[count==1]];following={int(a):int(b) for a,b in boundary}
        if point not in following or len(following)!=len(boundary):continue
        polygon=[];j=following[point]
        while j!=point and j not in polygon:polygon.append(j);j=following[j]
        if j!=point or len(polygon)<3:continue
        triangles=[];remaining=polygon.copy()
        for _ in range(len(polygon)*2):
            if len(remaining)==3:triangles.append(remaining);break
            for k in range(len(remaining)):
                a,b,c=remaining[k-1],remaining[k],remaining[(k+1)%len(remaining)];tri=v[[a,b,c],:2].astype(float);u=tri[1]-tri[0];w=tri[2]-tri[0];det=u[0]*w[1]-u[1]*w[0]
                if det<=1e-12:continue
                other=[i for i in remaining if i not in (a,b,c)];d=v[other,:2]-tri[0]
                ss=(d[:,0]*w[1]-d[:,1]*w[0])/det;tt=(u[0]*d[:,1]-u[1]*d[:,0])/det
                if ((ss>=0)&(tt>=0)&(ss+tt<=1)).any():continue
                triangles.append([a,b,c]);remaining.pop(k);break
            else:raise ValueError('Cap polygon ear clipping failed')
        else:raise ValueError('Cap ear clipping budget')
        keep=np.ones(len(f),bool);keep[star]=False;role=roles[star[0]];cell=cells[star[0]];f=np.r_[f[keep],np.asarray(triangles)];roles=np.r_[roles[keep],np.full(len(triangles),role)];cells=np.r_[cells[keep],np.full(len(triangles),cell)];dissolved+=1
    return f,roles,cells,dissolved


def flip_needles(v,f,roles,cells,minimum=.001):
    """Retriangulate tiny collinear fans, only within one source cell/material."""
    f=f.copy()
    for _ in range(8):
        q,alt,_=quality(v,f);bad=np.flatnonzero(alt<minimum)
        if not len(bad):return f
        changes=0
        for j in bad:
            if roles[j]=='ROAD':continue
            best=None;bestquality=alt[j]
            for a,b in zip(f[j],np.roll(f[j],-1)):
                neighbors=np.flatnonzero((f==a).any(1)&(f==b).any(1));neighbors=neighbors[neighbors!=j]
                if len(neighbors)!=1:continue
                k=int(neighbors[0])
                if roles[k]!=roles[j] or cells[k]!=cells[j]:continue
                c=int(next(i for i in f[j] if i not in (a,b)));d=int(next(i for i in f[k] if i not in (a,b)))
                ff=np.array([[c,d,a],[d,c,b]]);qq,aa,_=quality(v,ff)
                if (qq<0).all():ff=ff[:,::-1];qq,aa,_=quality(v,ff)
                if qq.min()<=0 or abs(qq.sum()-q[[j,k]].sum())>1e-8 or aa.min()<=bestquality:continue
                bestquality=aa.min();best=(k,ff)
            if best is not None:k,ff=best;f[[j,k]]=ff;changes+=1
        if not changes:break
    require(quality(v,f)[1].min()>=minimum,'Unrepaired needle triangle')
    return f


def wall_strip(xy,bottom,top,side):
    v=np.empty((len(xy)*2,3),dtype=np.float32);v[0::2,:2]=xy;v[1::2,:2]=xy;v[0::2,2]=bottom;v[1::2,2]=top
    a=np.arange(len(xy)-1)*2;b=a+2
    f=np.stack([np.stack([a,b,b+1],1),np.stack([a,b+1,a+1],1)],1).reshape(-1,3)
    if side<0:f=f[:,::-1]
    return v,f


def box(center,size):
    c=np.asarray(center);s=np.asarray(size)/2
    v=np.array([c+np.array([x,y,z])*s for z in (-1,1) for y in (-1,1) for x in (-1,1)],dtype=np.float32)
    f=np.array([[0,2,3],[0,3,1],[4,5,7],[4,7,6],[0,1,5],[0,5,4],[2,6,7],[2,7,3],[0,4,6],[0,6,2],[1,3,7],[1,7,5]])
    return v,f


class GroundIndex:
    """XY bins over final float32 contact triangles; also reports conservative bounds."""
    def __init__(self,v,f,size=16):
        self.v=v;self.f=f;self.size=size;self.bins={};tri=v[f];self.lo=tri[:,:,:2].min(1);self.hi=tri[:,:,:2].max(1)
        for j,(lo,hi) in enumerate(zip(self.lo,self.hi)):
            a=np.floor(lo/size).astype(int);b=np.floor(hi/size).astype(int)
            for x in range(a[0],b[0]+1):
                for y in range(a[1],b[1]+1):self.bins.setdefault((x,y),[]).append(j)
    def candidates(self,lo,hi):
        a=np.floor(np.array(lo)/self.size).astype(int);b=np.floor(np.array(hi)/self.size).astype(int);out=set()
        for x in range(a[0],b[0]+1):
            for y in range(a[1],b[1]+1):out.update(self.bins.get((x,y),()))
        ids=np.array(sorted(out),dtype=int)
        return ids[((self.lo[ids]<=hi).all(1))&((self.hi[ids]>=lo).all(1))]
    def extrapolate(self,xy):
        xy=np.asarray(xy);ids=self.candidates(xy-.15,xy+.15);tri=self.v[self.f[ids]].astype(float)
        a=tri[:,1,:2]-tri[:,0,:2];b=tri[:,2,:2]-tri[:,0,:2];d=xy-tri[:,0,:2];det=a[:,0]*b[:,1]-a[:,1]*b[:,0]
        u=(d[:,0]*b[:,1]-d[:,1]*b[:,0])/det;w=(a[:,0]*d[:,1]-a[:,1]*d[:,0])/det
        error=np.maximum.reduce([-u,-w,u+w-1,np.zeros(len(u))]);j=int(error.argmin());require(error[j]<.5,'Extrapolation too far')
        return float(tri[j,0,2]+u[j]*(tri[j,1,2]-tri[j,0,2])+w[j]*(tri[j,2,2]-tri[j,0,2]))
    def sample(self,xy,tolerance=1e-7):
        xy=np.asarray(xy);pad=max(1e-4,tolerance*2);ids=self.candidates(xy-pad,xy+pad);tri=self.v[self.f[ids]].astype(float)
        a=tri[:,1,:2]-tri[:,0,:2];b=tri[:,2,:2]-tri[:,0,:2];d=xy-tri[:,0,:2];det=a[:,0]*b[:,1]-a[:,1]*b[:,0]
        u=(d[:,0]*b[:,1]-d[:,1]*b[:,0])/det;w=(a[:,0]*d[:,1]-a[:,1]*d[:,0])/det
        use=(u>=-tolerance)&(w>=-tolerance)&(u+w<=1+tolerance)
        require(use.any(),'Missing final contact ground at '+str(xy))
        z=tri[:,0,2]+u*(tri[:,1,2]-tri[:,0,2])+w*(tri[:,2,2]-tri[:,0,2])
        return float(z[use].max())
    def bounds(self,a,b):
        ids=self.candidates(np.minimum(a,b)-.002,np.maximum(a,b)+.002);require(len(ids)>0,'Wall without adjacent ground')
        z=self.v[self.f[ids],2];return float(z.min()),float(z.max())


def overlap_audit(v,f,roles,index,minimum_area=1e-8):
    """Exact convex XY clipping of every local contact-triangle candidate pair."""
    hits=[];total=0.;tri=v[f].astype(float)
    for j in range(len(f)):
        ids=index.candidates(index.lo[j],index.hi[j]);ids=ids[ids>j]
        # Triangles sharing an exact edge cannot overlap if both are upward and edge directions oppose.
        for k in ids:
            common=np.intersect1d(f[j],f[k])
            if len(common)==2:
                e=common;others=[int(next(x for x in f[h] if x not in e)) for h in (j,k)]
                a,b=v[e,:2].astype(float);q=v[others,:2].astype(float)
                cross=(b[0]-a[0])*(q[:,1]-a[1])-(b[1]-a[1])*(q[:,0]-a[0])
                if cross.prod()<0:continue
            poly=tri[j,:,:2]
            for a,b in zip(tri[k,:,:2],np.roll(tri[k,:,:2],-1,axis=0)):
                poly=G.clip_half(poly,a,b)
                if len(poly)<3:break
            ar=G.area(poly)
            if ar>minimum_area:
                total+=ar
                if len(hits)<30:hits.append([j,int(k),ar,str(roles[j]),str(roles[k])])
    return dict(tolerance_area_m2=minimum_area,total_overlap_m2=total,examples=hits)
