"""Offline NumPy-only v002 geometry. All heights/widths are provisional designs."""
import numpy as np
from prototype_geometry import require, ribbon, station_normals, mesh_checks, ribbon_overlap, profile_stats


def stats(a):
    a = np.asarray(a)
    return dict(min=float(a.min()), max=float(a.max()), rms=float(np.sqrt(np.mean(a*a))),
                p95_abs=float(np.percentile(np.abs(a), 95)))


def design_route(r):
    raw = r['local_xyz_m']; native = r['chainage_25833_m']; chain = r['chainage_3035_m']
    # Preserve the native 2m detail; add samples to short controls only through interpolation.
    s = np.unique(np.r_[native, np.arange(0, native[-1], 2.)])
    p = np.column_stack([np.interp(s, native, raw[:, k]) for k in range(3)])
    original = p.copy(); c = np.interp(s, native, chain)
    bridge = (c >= 9578.) & (c <= 9602.)
    flanks = np.interp([9578., 9602.], c, p[:, 2])
    p[bridge, 2] = np.interp(c[bridge], [9578., 9602.], flanks)
    bridged = p.copy()
    # Metric Gaussian convolution on a uniform <=1m working lattice, linear endpoint extension.
    u = np.linspace(0, s[-1], int(np.ceil(s[-1])) + 1)
    for k, sigma in enumerate((2., 2., 4.)):
        z = np.interp(u, s, p[:, k]); step = u[1] - u[0]
        n = int(np.ceil(3*sigma/step)); t = np.arange(-n, n+1)*step
        w = np.exp(-.5*(t/sigma)**2); w /= w.sum()
        ext = np.r_[z[0] + np.arange(-n, 0)*(z[1]-z[0]), z,
                    z[-1] + np.arange(1,n+1)*(z[-1]-z[-2])]
        p[:, k] = np.interp(s, u, np.convolve(ext,w,'valid'))
    p[[0,-1]] = original[[0,-1]]
    # Remove the redundant union lattice: retain exact source stations (<=2m), smooth result.
    p = np.column_stack([np.interp(native, s, p[:, k]) for k in range(3)])
    original = raw.copy(); bridged = np.column_stack([np.interp(native,s,bridged[:,k]) for k in range(3)])
    c = chain.copy(); bridge = (c >=9578.) & (c<=9602.)
    v,f = ribbon(p,[-3.75,3.75]); check = mesh_checks(v,f)
    require(check['non_upward_triangles']==0, 'Road/shoulder folds')
    edges = v.reshape(-1,2,3)
    q = np.stack([edges[:-1,0],edges[1:,0],edges[1:,1],edges[:-1,1]],axis=1)
    e0=np.roll(q[:,:,:2],-1,axis=1)-q[:,:,:2]
    e1=np.roll(q[:,:,:2],-2,axis=1)-np.roll(q[:,:,:2],-1,axis=1)
    turns=e0[:,:,0]*e1[:,:,1]-e0[:,:,1]*e1[:,:,0]
    require((turns>1e-8).all(),'Nonconvex road quads')
    overlap = ribbon_overlap(p,3.75)
    require(not overlap, 'Nonadjacent road/shoulder overlap: '+str(overlap[:10]))
    report = dict(profile=profile_stats(p), raw_profile=profile_stats(raw),
        xy_displacement_m=stats(np.linalg.norm(p[:,:2]-raw[:,:2],axis=1)),
        final_z_delta_m=stats(p[:,2]-raw[:,2]), smoothing_only_z_delta_m=stats(p[:,2]-bridged[:,2]),
        smoothing=dict(xy_sigma_m=2.,z_sigma_m=4.,radius_sigma=3,endpoint_pinned=True),
        dip=dict(window_chainage_3035_m=[9578.,9602.], flank_local_z_m=flanks.tolist(),
                 source_indices=np.flatnonzero(bridge).tolist(),
                 source_chainage_3035_m=c[bridge].tolist(), raw_local_z_m=raw[bridge,2].tolist(),
                 bridged_local_z_m=bridged[bridge,2].tolist(), final_local_z_m=p[bridge,2].tolist(),
                 bridge_delta_m=(bridged[bridge,2]-raw[bridge,2]).tolist(),
                 final_delta_m=(p[bridge,2]-raw[bridge,2]).tolist(),
                 meaning='Provisional interpolated road bridge over unresolved DTM outlier, NOT surveyed asphalt'),
        folds=0,nonadjacent_overlaps=overlap,samples=len(p),max_station_step_m=float(np.diff(native).max()))
    return p, report


def clip_half(poly,a,b,inside=True):
    """Clip convex XY polygon left (or right) of oriented line. No hidden area discard."""
    if len(poly)<3: return np.empty((0,2))
    e=b-a; d=e[0]*(poly[:,1]-a[1])-e[1]*(poly[:,0]-a[0])
    if not inside: d=-d
    out=[]
    for i in range(len(poly)):
        j=(i+1)%len(poly); x,y=poly[i],poly[j]; dx,dy=d[i],d[j]
        if dx>=-1e-10: out.append(x)
        if (dx>1e-10 and dy < -1e-10) or (dx < -1e-10 and dy>1e-10):
            out.append(x+(y-x)*dx/(dx-dy))
    if len(out)<3: return np.empty((0,2))
    out=np.asarray(out)
    keep=np.linalg.norm(out-np.roll(out,1,axis=0),axis=1)>1e-8
    return out[keep] if keep.sum()>=3 else np.empty((0,2))


def area(poly):
    if len(poly)<3:return 0.
    # Translation avoids cancellation at full-track offsets.
    x=poly-poly[0]
    return float(abs(np.sum(x[:,0]*np.roll(x[:,1],-1)-x[:,1]*np.roll(x[:,0],-1)))*.5)


def subtract(poly,quad):
    remaining=poly; pieces=[]
    for a,b in zip(quad,np.roll(quad,-1,axis=0)):
        outside=clip_half(remaining,a,b,False)
        if len(outside)>=3:pieces.append(outside)
        remaining=clip_half(remaining,a,b,True)
        if len(remaining)<3:break
    return pieces


def grid_sample(t, xy, z=None):
    """Actual triangle interpolation on the visible grid, strict valid-cell check."""
    xy=np.atleast_2d(xy); z=t['z_m'] if z is None else z
    u=(xy[:,0]-t['x_m'][0,0])/8.; v=(xy[:,1]-t['y_m'][0,0])/8.
    require(((u>=-1e-8)&(v>=-1e-8)&(u<=t['valid_cells'].shape[1]+1e-8)&(v<=t['valid_cells'].shape[0]+1e-8)).all(),'Outside terrain')
    c=np.clip(np.floor(u).astype(int),0,t['valid_cells'].shape[1]-1)
    r=np.clip(np.floor(v).astype(int),0,t['valid_cells'].shape[0]-1)
    bad=~t['valid_cells'][r,c]
    for j in np.flatnonzero(bad):
        found=False
        for rr,cc in ((r[j],c[j]-1),(r[j]-1,c[j]),(r[j]-1,c[j]-1)):
            if rr>=0 and cc>=0 and t['valid_cells'][rr,cc] and -1e-8<=u[j]-cc<=1+1e-8 and -1e-8<=v[j]-rr<=1+1e-8:
                r[j],c[j]=rr,cc;found=True;break
        require(found,'Invalid terrain anchor/cell')
    u-=c;v-=r
    return np.where(u>=v,(1-u)*z[r,c]+(u-v)*z[r,c+1]+v*z[r+1,c+1],
                    (1-v)*z[r,c]+u*z[r+1,c+1]+(v-u)*z[r+1,c])


def nearest(points, route, bucket_size=32.):
    """Exact nearest segment in expanding spatial bins, bounded local corridor."""
    a=route[:-1,:2]; d=np.diff(route[:,:2],axis=0); dd=(d*d).sum(1)
    bins={}
    for i,(lo,hi) in enumerate(zip(np.minimum(a,a+d),np.maximum(a,a+d))):
        for x in range(int(np.floor(lo[0]/bucket_size)),int(np.floor(hi[0]/bucket_size))+1):
            for y in range(int(np.floor(lo[1]/bucket_size)),int(np.floor(hi[1]/bucket_size))+1):
                bins.setdefault((x,y),[]).append(i)
    indices=[]; fractions=[]; distances=[]
    for p in np.asarray(points):
        bx,by=np.floor(p/bucket_size).astype(int); best=np.inf;bi=None;bt=None
        for radius in range(1,30):
            ids=set()
            for x in range(bx-radius,bx+radius+1):
                for y in range(by-radius,by+radius+1):ids.update(bins.get((x,y),()))
            if ids:
                ids=np.array(sorted(ids)); t=np.clip(((p-a[ids])*d[ids]).sum(1)/dd[ids],0,1)
                dist=np.linalg.norm(p-a[ids]-t[:,None]*d[ids],axis=1); j=dist.argmin()
                best=float(dist[j]);bi=int(ids[j]);bt=float(t[j])
            boundary=min(p[0]-(bx-radius)*bucket_size,(bx+radius+1)*bucket_size-p[0],
                         p[1]-(by-radius)*bucket_size,(by+radius+1)*bucket_size-p[1])
            if best<boundary:break
        require(bi is not None and best<boundary,'Nearest segment search budget')
        indices.append(bi);fractions.append(bt);distances.append(best)
    return np.array(indices),np.array(fractions),np.array(distances)


def terrain_design(t, r, lateral, p):
    """Blend original grid to actual lateral probes, then subtract the exact shoulder footprint.

    Every valid original cell is retained outside the explicitly accounted road footprint.
    Terrain beneath road is replaced, not lowered into an open trench. Source arrays untouched.
    """
    v,f=ribbon(p,[-3.75,3.75]);edge=v.reshape(-1,2,3)
    quads=np.stack([edge[:-1,0,:2],edge[1:,0,:2],edge[1:,1,:2],edge[:-1,1,:2]],axis=1)
    candidates={}
    for i,q in enumerate(quads):
        lo,hi=q.min(0),q.max(0)
        c0,c1=np.floor((np.array([lo[0],hi[0]])-t['x_m'][0,0])/8).astype(int)
        r0,r1=np.floor((np.array([lo[1],hi[1]])-t['y_m'][0,0])/8).astype(int)
        for row in range(r0,r1+1):
            for col in range(c0,c1+1):
                require(t['valid_cells'][row,col],'Road touches invalid terrain cell')
                candidates.setdefault((row,col),[]).append(i)
    # Derived near-road grid adjustment. Nodes >15m are exactly raw.
    rows,cols=np.nonzero(t['valid']);xy=np.column_stack([t['x_m'][rows,cols],t['y_m'][rows,cols]])
    # Only nodes in expanded occupied-cell bins need nearest queries.
    near=set()
    for row,col in candidates:
        for rr in range(max(0,row-2),min(t['valid'].shape[0],row+4)):
            for cc in range(max(0,col-2),min(t['valid'].shape[1],col+4)):
                if t['valid'][rr,cc]:near.add((rr,cc))
    near=np.array(sorted(near));nxy=np.column_stack([t['x_m'][near[:,0],near[:,1]],t['y_m'][near[:,0],near[:,1]]])
    ni,nt,nd=nearest(nxy,p)
    z=t['z_m'].copy(); normals=station_normals(p)
    center=p[ni]*(1-nt[:,None])+p[ni+1]*nt[:,None]
    signed=np.sum((nxy-center[:,:2])*(normals[ni]*(1-nt[:,None])+normals[ni+1]*nt[:,None]),axis=1)
    # Interpolate actual +/-8m probes; values corrected only for the designed road XY drift.
    ground8=np.where(signed>=0,(1-nt)*lateral['local_xyz_m'][ni,6,2]+nt*lateral['local_xyz_m'][ni+1,6,2],
                     (1-nt)*lateral['local_xyz_m'][ni,1,2]+nt*lateral['local_xyz_m'][ni+1,1,2])
    rawz=z[near[:,0],near[:,1]]
    w=np.clip((nd-3.75)/4.25,0,1)
    first=center[:,2]*(1-w)+ground8*w
    w2=np.clip((nd-8.)/7.,0,1);w2=w2*w2*(3-2*w2)
    target=np.where(nd<8,first,ground8*(1-w2)+rawz*w2)
    target=np.where(nd<15,target,rawz)
    z[near[:,0],near[:,1]]=target
    # Clip each valid top triangle only where it intersects actual road quads.
    vertices=[]; faces=[]; lookup={}; cell_ids=[]; removed=0.; sliver_area=0.;seam=[]
    def add_triangle(poly,row,col):
        nonlocal sliver_area
        if len(poly)<3:return
        for j in range(1,len(poly)-1):
            tri=poly[[0,j,j+1]]; ar=area(tri)
            if ar<1e-7:
                sliver_area+=ar;continue # explicitly audited sub-square-millimetre clipping residue
            ids=[]
            for q in tri:
                key=tuple(q.astype(np.float32))
                if key not in lookup:
                    lookup[key]=len(vertices);vertices.append(q)
                ids.append(lookup[key])
            actual=np.array([vertices[k] for k in ids]);single=actual.astype(np.float32).astype(float)
            d0=single[1]-single[0];d1=single[2]-single[0]
            if len(set(ids))<3 or d0[0]*d1[1]-d0[1]*d1[0]<=1e-9:
                sliver_area+=ar;continue # float32-unrepresentable numeric residues, explicitly reported
            faces.append(ids);cell_ids.append(row*t['valid_cells'].shape[1]+col)
    for row,col in zip(*np.nonzero(t['valid_cells'])):
        x=t['x_m'][row,col];y=t['y_m'][row,col]
        for tri in (np.array([[x,y],[x+8,y],[x+8,y+8]]),np.array([[x,y],[x+8,y+8],[x,y+8]])):
            pieces=[tri]
            for i in candidates.get((row,col),()):
                pieces=[part for poly in pieces for part in subtract(poly,quads[i])]
            kept=sum(area(poly) for poly in pieces)
            require(kept<=32.+1e-6,'Clipping added area')
            removed+=32.-kept
            for poly in pieces:add_triangle(poly,row,col)
    xy=np.asarray(vertices,dtype=np.float32).astype(float); faces=np.asarray(faces,dtype=np.int32)
    used,local=np.unique(faces,return_inverse=True);xy=xy[used];faces=local.reshape(-1,3)
    cell_ids=np.asarray(cell_ids,dtype=np.int64);numeric_repairs=[]
    # A quantized, vanishing sliver can share one edge with BOTH neighboring fans.
    # Refuse substantive defects; explicitly account every removed numeric residue.
    for iteration in range(16):
        edges=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
        _,inverse,counts=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
        bad=np.flatnonzero(counts>2)
        if not len(bad):break
        victims=set()
        for edge_id in bad:
            ids=np.unique(np.flatnonzero(inverse==edge_id)%len(faces))
            areas=np.array([area(xy[faces[k]]) for k in ids]);j=int(ids[areas.argmin()])
            require(areas.min()<1e-3,'Substantive terrain nonmanifold overlap')
            victims.add(j)
        for j in sorted(victims):
            lost=area(xy[faces[j]]);sliver_area+=lost
            numeric_repairs.append(dict(source_cell=int(cell_ids[j]),xy_m=xy[faces[j]].tolist(),area_m2=lost,reason='Float32 clipped sliver edge incidence >2'))
        keep=np.ones(len(faces),dtype=bool);keep[list(victims)]=False;faces=faces[keep];cell_ids=cell_ids[keep]
    else:raise ValueError('Numeric terrain repair iteration budget')
    # For clipped boundary coordinates compute exact nearest *shoulder edge*, not a centerline approximation.
    base=grid_sample(t,xy,z)
    cell_c=np.floor((xy[:,0]-t['x_m'][0,0])/8).astype(int)
    cell_r=np.floor((xy[:,1]-t['y_m'][0,0])/8).astype(int)
    need=[j for j,(rr,cc) in enumerate(zip(cell_r,cell_c)) if any((rr+dr,cc+dc) in candidates for dr,dc in ((0,0),(-1,0),(0,-1),(-1,-1)))]
    edge_a=np.concatenate([edge[:-1,0],edge[:-1,1],edge[0:1,0],edge[-1:,0]])
    edge_b=np.concatenate([edge[1:,0],edge[1:,1],edge[0:1,1],edge[-1:,1]])
    # Nearby side segments using route station plus endpoint caps.
    for j in need:
        local=set()
        for dr,dc in ((0,0),(-1,0),(0,-1),(-1,-1)):
            local.update(candidates.get((cell_r[j]+dr,cell_c[j]+dc),()))
        local=np.array(sorted(local),dtype=int)
        ids=np.unique(np.r_[local,local+len(p)-1,2*(len(p)-1),2*(len(p)-1)+1])
        a=edge_a[ids];d=edge_b[ids]-a
        t0=np.clip(((xy[j]-a[:,:2])*d[:,:2]).sum(1)/(d[:,:2]*d[:,:2]).sum(1),0,1)
        ds=np.linalg.norm(xy[j]-a[:,:2]-t0[:,None]*d[:,:2],axis=1);k=ds.argmin()
        if ds[k]<6e-4:
            base[j]=a[k,2]+t0[k]*d[k,2];seam.append([j,int(ids[k]),float(t0[k]),float(ds[k])])
    xyz=np.column_stack([xy,base])
    checks=mesh_checks(xyz,faces)
    if checks['non_upward_triangles']:
        tri=xyz[faces];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,2]
        bad=np.flatnonzero(cross<=1e-9)
        raise ValueError('Terrain clipping folds '+str(checks)+' first='+str([(int(k),float(cross[k]),tri[k].tolist()) for k in bad[:5]]))
    delta=z-t['z_m']
    report=dict(valid_source_cells=int(t['valid_cells'].sum()),valid_source_area_m2=float(t['valid_cells'].sum()*64),
        road_replaced_area_m2=removed, terrain_top_area_m2=float(sum(area(xy[f0]) for f0 in faces)),
        audited_numeric_sliver_area_m2=sliver_area,numeric_topology_repairs=numeric_repairs,source_cells_accounted=int(t['valid_cells'].sum()),
        modified_grid_nodes=int(np.count_nonzero(delta)),grid_delta_m=stats(delta[t['valid']]),
        exact_shoulder_seam_points=len(seam),max_seam_xy_error_m=max(s[3] for s in seam),
        policy='Valid cells only; exact road/shoulder footprint replaced. 3.75–8m blend to actual lateral probes; 8–15m fade to source grid. No raw changes.',
        checks=checks)
    report['float32_xy_area_delta_m2']=report['terrain_top_area_m2']+removed+sliver_area-report['valid_source_area_m2']
    require(abs(report['float32_xy_area_delta_m2'])<5.,'Terrain float32 quantization exceeds 5 square metres across 13.3 km2')
    return xyz,faces,z,np.asarray(cell_ids),np.asarray(seam),report


def closed_slab(v,f,thickness):
    """Closed solid with upward top, outward sides, downward underside."""
    v=np.asarray(v);f=np.asarray(f,dtype=np.int32).copy()
    # Spatial triangle batches can meet at a vertex but not an edge. Split each
    # disconnected incident fan so extrusion produces truly manifold closed solids.
    ee=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
    _,ei,ec=np.unique(np.sort(ee,axis=1),axis=0,return_index=True,return_counts=True)
    boundary0=ee[ei[ec==1]]
    degree=np.bincount(boundary0.ravel(),minlength=len(v));extra=[]
    for vertex in np.flatnonzero(degree>2):
        incident=np.flatnonzero((f==vertex).any(1));by_other={}
        for face in incident:
            for other in f[face][f[face]!=vertex]:by_other.setdefault(int(other),[]).append(int(face))
        todo=set(incident.tolist());first=True
        while todo:
            group={todo.pop()};stack=list(group)
            while stack:
                face=stack.pop()
                for other in f[face][f[face]!=vertex]:
                    for neighbor in by_other[int(other)]:
                        if neighbor in todo:todo.remove(neighbor);group.add(neighbor);stack.append(neighbor)
            if not first:
                new=len(v)+len(extra);extra.append(v[vertex])
                for face in group:f[face,f[face]==vertex]=new
            first=False
    if extra:v=np.r_[v,np.array(extra)]
    n=len(v)
    edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);key=np.sort(edges,axis=1)
    _,index,count=np.unique(key,axis=0,return_index=True,return_counts=True)
    require(count.max()<=2,'Nonmanifold top mesh')
    boundary=edges[index[count==1]]
    bottom=v.copy();bottom[:,2]-=thickness
    a,b=boundary.T
    sides=np.stack([np.stack([b,a,a+n],1),np.stack([b,a+n,b+n],1)],1).reshape(-1,3)
    outv=np.r_[v,bottom];outf=np.r_[f,f[:,::-1]+n,sides]
    return outv,outf


def solid_checks(v,f):
    e=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);s=np.sort(e,1)
    _,count=np.unique(s,axis=0,return_counts=True)
    tri=v[f];volume=float(np.sum(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])))/6.)
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    require((count==2).all(),'Collision solid is not closed')
    require(np.linalg.norm(cross,axis=1).min()>1e-9,'Degenerate solid triangle')
    require(volume>0,'Non-outward collision solid')
    # Directed incidence must cancel, not just undirected edge counts.
    signed=np.where(e[:,0]<e[:,1],1,-1);_,inverse=np.unique(s,axis=0,return_inverse=True)
    require((np.bincount(inverse,weights=signed)==0).all(),'Inconsistent outward winding')
    return dict(closed=True,outward=True,volume_m3=volume,triangles=len(f),vertices=len(v))


def wall(p,side):
    """Continuous 1.15m temporary safety wall, beyond 0.75m shoulder."""
    v,f=ribbon(p,sorted([side*4.05,side*4.35]));v[:,2]-=.15
    return closed_slab(v+np.array([0,0,1.3]),f,1.3)


def chunks(v,f,uv,size=256.):
    """Spatially bounded deterministic meshes; per-chunk collision closure is preserved by caller."""
    centers=v[f].mean(1);keys=np.floor(centers[:,:2]/size).astype(int)
    unique,inv=np.unique(keys,axis=0,return_inverse=True)
    for k,key in enumerate(unique):
        ids=np.flatnonzero(inv==k);ff=f[ids];used,local=np.unique(ff,return_inverse=True)
        yield tuple(key),v[used],local.reshape(-1,3),uv[used]


def tree_geometry(anchors,seed=2002):
    """Opaque 6-sided trunks and two 8-sided irregular crown rings, merged by material."""
    rng=np.random.default_rng(seed);bark_v=[];bark_f=[];leaf_v=[];leaf_f=[]
    for a in anchors:
        h=rng.uniform(9,16);radius=rng.uniform(2.8,4.7);phase=rng.uniform(0,2*np.pi)
        ang=np.arange(6)*np.pi/3+phase
        v=np.array([[*(a[:2]+r*np.array([np.cos(t),np.sin(t)])),a[2]+z]
                    for z,r in [(0,.24),(h*.58,.16)] for t in ang])
        f=[]
        for j in range(6):k=(j+1)%6;f.extend([[j,k,k+6],[j,k+6,j+6]])
        f.extend([[0,2,1],[0,3,2],[0,4,3],[0,5,4],[6,7,8],[6,8,9],[6,9,10],[6,10,11]])
        bark_f.extend((np.array(f)+len(bark_v)).tolist());bark_v.extend(v)
        ang=np.arange(8)*np.pi/4+phase;v=[a+[0,0,h*.32]]
        for z,scale in [(h*.51,1.),(h*.80,.83)]:
            for theta in ang:
                rr=radius*scale*rng.uniform(.85,1.15);v.append(a+[rr*np.cos(theta),rr*np.sin(theta),z])
        v.append(a+[.3,-.2,h]);f=[]
        for j in range(8):k=(j+1)%8;f.extend([[0,1+k,1+j],[1+j,1+k,9+k],[1+j,9+k,9+j],[9+j,9+k,17]])
        leaf_f.extend((np.array(f)+len(leaf_v)).tolist());leaf_v.extend(v)
    return [(np.asarray(bark_v),np.asarray(bark_f)),(np.asarray(leaf_v),np.asarray(leaf_f))]
