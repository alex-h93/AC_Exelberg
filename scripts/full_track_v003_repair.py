"""Factory-Blender constrained triangulation of v003 single ground skin.
Keep exact v002 road constraints; rebuild verges and original-cell terrain without slabs.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import json,time
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
import full_track_v003_geometry as H
import full_track_v002_geometry as G
from prototype_geometry import ribbon,require
from build_full_track_v003 import ROOT,OUT,OLD,verified,dump

def repair():
    require(not (OUT/'repaired_skin.npz').exists() and not (OUT/'repair_report.json').exists(),'Refuse existing repaired assets')
    start=time.monotonic();old=json.loads(OLD.read_text());roadv=[];roadf=[]
    for s in old['meshes']:
        if s['surface_key']!='ROAD':continue
        with np.load(verified(s['artifact'])) as a:v,f,uv=H.extract_top(a)
        roadf.extend(f+len(roadv));roadv.extend(v)
    rv=np.asarray(roadv);rf=np.asarray(roadf);xy,idx,inv=np.unique(rv[:,:2],axis=0,return_index=True,return_inverse=True);rv=rv[idx];rf=inv[rf]
    with np.load(ROOT/'data/processed/full_track_scene_v002/geometry_audit.npz') as a:
        p=a['designed_xyz_m'];tv=a['clipped_terrain_xyz_m'].astype(np.float32);tf=a['clipped_terrain_triangles'];gridz=a['derived_grid_z_m']
    terrain=np.load(ROOT/'data/processed/full_track_inputs/terrain.npz');x0=terrain['x_m'][0,0];y0=terrain['y_m'][0,0]
    # Rebuild exact cell edges, subtracting the shoulder envelope in double precision.
    # Never carry v002's almost-collinear clipped fan edges into the new triangulation.
    valid=terrain['valid_cells'];rr,cc=np.nonzero(valid);stride=valid.shape[1]+1
    aa=rr*stride+cc
    ge=np.vstack([np.c_[aa,aa+1],np.c_[aa+stride,aa+stride+1],np.c_[aa,aa+stride],np.c_[aa+1,aa+stride+1],np.c_[aa,aa+stride+1]])
    ge=np.unique(ge,axis=0);nodes=np.c_[terrain['x_m'].ravel(),terrain['y_m'].ravel()]
    endpoints=nodes[ge];mid=endpoints.mean(1);ni,nt,nd=H.local_nearest(mid,p)
    shoulder,_=ribbon(p,[-3.75,3.75]);quad=shoulder.reshape(-1,2,3)
    quad=np.stack([quad[:-1,0,:2],quad[1:,0,:2],quad[1:,1,:2],quad[:-1,1,:2]],1)
    bins={}
    for j,q in enumerate(quad):
        low=np.floor((q.min(0)-8)/32).astype(int);high=np.floor((q.max(0)+8)/32).astype(int)
        for x in range(low[0],high[0]+1):
            for y in range(low[1],high[1]+1):bins.setdefault((x,y),[]).append(j)
    coords=list(rv[:,:2]);edges=[];lookup={tuple(q):i for i,q in enumerate(coords)}
    def vertex(q):
        key=tuple(q)
        if key not in lookup:lookup[key]=len(coords);coords.append(q)
        return lookup[key]
    for k,(a,b) in enumerate(endpoints):
        intervals=[(0.,1.)];d=b-a
        if nd[k]<10:
            for j in bins.get(tuple(np.floor(mid[k]/32).astype(int)),()):
                lo,hi=0.,1.
                for qa,qb in zip(quad[j],np.roll(quad[j],-1,axis=0)):
                    e=qb-qa;z=e[0]*(a[1]-qa[1])-e[1]*(a[0]-qa[0]);s=e[0]*d[1]-e[1]*d[0]
                    if abs(s)<1e-14:
                        if z<0:lo=2;break
                    elif s>0:lo=max(lo,-z/s)
                    else:hi=min(hi,-z/s)
                if lo>=hi:continue
                intervals=[part for l,h in intervals for part in ((l,min(h,lo)),(max(l,hi),h)) if part[1]-part[0]>1e-9]
        for lo,hi in intervals:
            if (hi-lo)*8>.004:edges.append([vertex(a+lo*d),vertex(a+hi*d)])
    faces=rf.tolist()
    # Shoulder contour is a material/seam constraint, never physical vertical geometry.
    shoulder,_=ribbon(p,[-3.75,3.75]);si=len(coords);coords.extend(shoulder[:,:2]);n=len(p)
    for j in range(n-1):edges.extend([[si+2*j,si+2*(j+1)],[si+2*j+1,si+2*(j+1)+1]])
    outer,_=ribbon(p,[-6.,6.]);oi=len(coords);coords.extend(outer[:,:2])
    for j in range(n-1):edges.extend([[oi+2*j,oi+2*(j+1)],[oi+2*j+1,oi+2*(j+1)+1]])
    roadedge,_=ribbon(p,[-3.,3.]);roadlookup={tuple(q):i for i,q in enumerate(rv[:,:2])}
    for j in range(n):
        for side in (0,1):
            ri=roadlookup[tuple(roadedge[j*2+side,:2].astype(np.float32))]
            edges.extend([[ri,si+2*j+side],[si+2*j+side,oi+2*j+side]])
    for endpoint in (0,n-1):
        for side in (0,1):
            j=roadlookup[tuple(roadedge[endpoint*2+side,:2].astype(np.float32))]
            edges.append([si+2*endpoint+side,j])
    print('CDT INPUT',len(coords),len(edges),len(faces),flush=True)
    # 10mm CDT tolerance resolves almost coincident cuts; topology-safe 8mm
    # collapse/needle flips follow. Road points/triangles are restored exactly.
    cv,ce,cf,ov,oe,of=delaunay_2d_cdt([Vector(q) for q in coords],[tuple(map(int,e)) for e in edges],faces,0,.01,True)
    print('CDT OUTPUT',len(cv),len(cf),'seconds',time.monotonic()-start,flush=True)
    v=np.column_stack([np.array(cv),np.zeros(len(cv))]).astype(np.float32);f=np.array(cf,dtype=np.int32)
    roadmap={}
    for j,origin in enumerate(ov):
        road=[k for k in origin if k<len(rv)]
        if road:
            require(len(road)==1 or (rv[road]==rv[road[0]]).all(),'CDT merged distinct road vertices')
            v[j]=rv[road[0]];roadmap[road[0]]=j
    winding=np.cross(v[f[:,1],:2]-v[f[:,0],:2],v[f[:,2],:2]-v[f[:,0],:2]);f[winding<0]=f[winding<0,::-1]
    expected=np.array([[roadmap[int(i)] for i in face] for face in rf],dtype=np.int32)
    roadkeys=set(bytes(k) for k in H.triangles_key(v,expected));keys=H.triangles_key(v,f)
    isroad=np.array([bytes(k) in roadkeys for k in keys]);print('EXACT ROAD',isroad.sum(), 'expected',len(roadkeys),flush=True)
    # Original endpoint edges cross cell boundaries. CDT may subdivide two road
    # faces at these straight, coplanar endpoints; restore their exact triangles.
    # Adjacent terrain retains geometric T-junctions on the same line, not caps.
    covered={k for ids in of for k in ids};require(covered==set(range(len(rf))),'Missing constrained road area')
    roadregion=np.array([bool(ids) for ids in of]);f=np.r_[f[~roadregion],expected]
    isroad=np.r_[np.zeros((~roadregion).sum(),dtype=bool),np.ones(len(expected),dtype=bool)]
    for endpoint in (0,len(p)-1):
        a=roadedge[endpoint*2,:2].astype(np.float32).astype(float);b=roadedge[endpoint*2+1,:2].astype(np.float32).astype(float);d=b-a
        w=np.clip(((v[:,:2]-a)*d).sum(1)/(d@d),0,1);proj=a+w[:,None]*d
        close=np.linalg.norm(v[:,:2]-proj,axis=1)<.002
        notroad=np.ones(len(v),dtype=bool);notroad[list(roadmap.values())]=False
        v[close&notroad,:2]=proj[close&notroad].astype(np.float32)
    center=v[f,:2].mean(1);ii,tt,dd=H.local_nearest(center,p)
    rows=np.floor((center[:,1]-y0)/8).astype(int);cols=np.floor((center[:,0]-x0)/8).astype(int);valid=terrain['valid_cells'];inside=(rows>=0)&(cols>=0)&(rows<valid.shape[0])&(cols<valid.shape[1]);inside[inside]&=valid[rows[inside],cols[inside]]
    # Classification uses explicit road constrained faces; nonroad shoulders extend to 3.75m.
    start_t=(p[1,:2]-p[0,:2]);end_t=(p[-1,:2]-p[-2,:2])
    endoutside=((ii==0)&(tt==0)&(((center-p[0,:2])*start_t).sum(1)<-1e-5))|((ii==len(p)-2)&(tt==1)&(((center-p[-1,:2])*end_t).sum(1)>1e-5))
    av,af=ribbon(p,[-3.75,-3.,0.,3.,3.75]);ai=H.GroundIndex(av.astype(np.float32),af)
    gravel=np.zeros(len(f),dtype=bool)
    for j in np.flatnonzero((dd<4)&~isroad&~endoutside):
        try:ai.sample(center[j]);gravel[j]=True
        except ValueError:pass
    keep=inside|isroad;f=f[keep];isroad=isroad[keep];dd=dd[keep];rows=rows[keep];cols=cols[keep];gravel=gravel[keep]
    roles=np.where(isroad,'ROAD',np.where(gravel,'GRAVEL','GRASS'));cells=rows*valid.shape[1]+cols;cells[roles!='GRASS']=-1
    # DTM sample on valid source triangles for original grid / derived v002 base.
    z=G.grid_sample({k:terrain[k] for k in terrain.files},v[:,:2],gridz);v[:,2]=z
    # Original orthophoto tile edges must remain exact, even after CDT's
    # tolerance-based merging of a nearby shoulder station and grid intersection.
    orth=json.loads((ROOT/'data/processed/landscape_orthos_v003/manifest.json').read_text())
    locked=np.zeros(len(v),bool);locked[list(roadmap.values())]=True
    for axis,keys in [(0,(0,2)),(1,(1,3))]:
        lines=sorted({c['local_bounds'][k] for c in orth['chunks'] for k in keys})
        for line in lines:
            close=(abs(v[:,axis]-line)<.012)&~locked;v[close,axis]=line
    v,f,roles,cells,micro_removed=H.collapse_micro_edges(v,f,roles,cells)
    f,roles,cells,cap_cuts=H.dissolve_cap_cuts(v,f,roles,cells,p)
    f=H.flip_needles(v,f,roles,cells)
    out,ii,tt,dist,delta=H.apron(v,p)
    shouldervertices=np.unique(f[roles=='GRAVEL'])
    for j in shouldervertices:out[j,2]=ai.extrapolate(out[j,:2])
    for original,j in roadmap.items():out[j]=rv[original]
    # Natural (zero-flux) outside boundary at the containment contour: distant
    # opposing hairpin branches can have very different Z and must not pull the
    # reachable apron downhill through a 20m Dirichlet boundary.
    sixv,sixf=ribbon(p,[-6.,6.]);sixindex=H.GroundIndex(sixv.astype(np.float32),sixf)
    reachable=(roles=='ROAD')|(roles=='GRAVEL');centers=out[f,:2].mean(1)
    for j in np.flatnonzero((roles=='GRASS')&(dist[f].min(1)<6.1)):
        try:sixindex.sample(centers[j]);reachable[j]=True
        except ValueError:pass
    out=H.relax_apron(out,f[reachable],((roles=='ROAD')|(roles=='GRAVEL'))[reachable],np.zeros(len(v)))
    out=H.limit_slopes(out,f[reachable],np.unique(f[(roles=='ROAD')|(roles=='GRAVEL')]))
    q,alt,slope=H.quality(out,f);duplicate=len(f)-len(np.unique(np.sort(f,axis=1),axis=0))
    report=dict(vertices=len(out),triangles=len(f),roles={r:int((roles==r).sum()) for r in ('ROAD','GRAVEL','GRASS')},inverted=int((q<=0).sum()),min_altitude_m=float(alt.min()),needle_under_1mm=int((alt<.001).sum()),duplicate_triangles=duplicate,max_reachable_slope=float(slope[reachable&(roles!='ROAD')].max()),micro_triangles_collapsed=micro_removed,cap_cuts_dissolved=cap_cuts,elapsed_seconds=time.monotonic()-start)
    dump(OUT/'repair_report.json',report);print('REPAIR',report,flush=True)
    np.savez_compressed(OUT/'repaired_skin.npz',vertices=out,triangles=f,roles=roles,source_cell=cells,distance_to_route_m=dist,source_xyz_m=v,delta_z_m=out[:,2]-v[:,2],designed_xyz_m=p,reachable_triangles=reachable)
if __name__=='__main__':repair()
