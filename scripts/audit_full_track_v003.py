"""Independent vectorized XY contact-intersection and source preservation audit."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import json,time
import numpy as np
import full_track_v003_geometry as H
import full_track_v002_geometry as G
from build_full_track_v003 import OUT,ROOT,OLD,verified,dump,unchanged
from prototype_geometry import require

def overlaps(v,f):
    tri=v[f,:2].astype(float);lo=tri.min(1);hi=tri.max(1);bins={};size=8.
    for j,(a,b) in enumerate(zip(np.floor(lo/size).astype(int),np.floor(hi/size).astype(int))):
        for x in range(a[0],b[0]+1):
            for y in range(a[1],b[1]+1):bins.setdefault((x,y),[]).append(j)
    suspects=[];tested=0
    for ids in bins.values():
        if len(ids)<2:continue
        ids=np.asarray(ids);i,j=np.triu_indices(len(ids),1);i,j=ids[i],ids[j]
        use=(np.minimum(hi[i],hi[j])-np.maximum(lo[i],lo[j])>1e-9).all(1);i,j=i[use],j[use]
        if not len(i):continue
        tested+=len(i);keep=np.ones(len(i),bool)
        for a,b in ((i,j),(j,i)):
            aa=tri[a];bb=tri[b]
            for k in range(3):
                edge=aa[:,(k+1)%3]-aa[:,k];d=bb-aa[:,k,None,:]
                cross=edge[:,0,None]*d[:,:,1]-edge[:,1,None]*d[:,:,0]
                keep&=cross.max(1)>1e-10
        if keep.any():suspects.extend((i[keep]*np.int64(len(f))+j[keep]).tolist())
    result=[]
    for key in np.unique(suspects):
        i,j=divmod(int(key),len(f));poly=tri[i]
        for a,b in zip(tri[j],np.roll(tri[j],-1,axis=0)):
            poly=G.clip_half(poly,a,b)
            if len(poly)<3:break
        area=G.area(poly)
        if area>1e-10:result.append(dict(triangles=[i,j],area_m2=area,xy_m=poly.tolist()))
    return dict(bbox_pairs_tested_including_bins=tested,positive_pairs=len(result),total_overlap_m2=sum(x['area_m2'] for x in result),maximum_overlap_m2=max((x['area_m2'] for x in result),default=0),examples=result[:30],area_reporting_tolerance_m2=1e-10)

def main():
    start=time.monotonic()
    with np.load(OUT/'contact_skin.npz') as a:v=a['vertices'];f=a['triangles'];roles=a['roles'];cells=a['source_cell'];reachable=a['reachable_triangles']
    q,alt,slope=H.quality(v,f);ov=overlaps(v,f)
    longest=np.linalg.norm(v[f,:2]-np.roll(v[f,:2],1,axis=1),axis=2).max(1);aspect=longest/alt
    tri=v[f].astype(float);area3d=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
    edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);keys=np.sort(edges,axis=1);_,inv,count=np.unique(keys,axis=0,return_inverse=True,return_counts=True);signed=np.where(edges[:,0]<edges[:,1],1,-1);direction=np.bincount(inv,weights=signed)
    old=json.loads(OLD.read_text());road=[]
    for s in old['meshes']:
        if s['surface_key']=='ROAD':
            with np.load(verified(s['artifact'])) as a:rv,rf,uv=H.extract_top(a)
            road.append(H.triangles_key(rv,rf))
    exactroad=np.array_equal(np.sort(np.concatenate(road)),np.sort(H.triangles_key(v,f[roles=='ROAD'])))
    m=json.loads((OUT/'prepared.json').read_text());uvmin=1;uvmax=0
    for s in m['meshes']:
        if s['material'].startswith('ortho'):
            with np.load(verified(s['artifact'])) as a:uvmin=min(uvmin,float(a['uv'].min()));uvmax=max(uvmax,float(a['uv'].max()))
    # Detect internal seams separately from the actual valid-cell outside perimeter.
    terrain=np.load(ROOT/'data/processed/full_track_inputs/terrain.npz');valid=terrain['valid_cells'];x0=terrain['x_m'][0,0];y0=terrain['y_m'][0,0]
    def valid_at(xy):
        c=int(np.floor((xy[0]-x0)/8));r=int(np.floor((xy[1]-y0)/8));return 0<=r<valid.shape[0] and 0<=c<valid.shape[1] and bool(valid[r,c])
    _,edge_ids=np.unique(keys,axis=0,return_index=True);boundary=edges[edge_ids[count==1]];index=H.GroundIndex(v,f);internal=[];missing=0
    for a,b in boundary:
        mid=(v[a,:2].astype(float)+v[b,:2])/2;d=v[b,:2].astype(float)-v[a,:2];normal=np.array([-d[1],d[0]])/np.linalg.norm(d);sides=[mid+normal*.002,mid-normal*.002]
        if not all(valid_at(xy) for xy in sides):continue
        internal.append([int(a),int(b)])
        for xy in sides:
            try:index.sample(xy)
            except ValueError:missing+=1
    report=dict(status='PASS' if ov['positive_pairs']==0 and missing==0 and alt.min()>.001 and aspect.max()<1000 else 'BLOCKED_CONTACT_GEOMETRY',triangles=len(f),vertices=len(v),roles={role:int((roles==role).sum()) for role in ('ROAD','GRAVEL','GRASS')},total_xy_area_m2=float(q.sum()/2),original_valid_cell_area_m2=int(valid.sum()*64),area_residual_m2=float(q.sum()/2-valid.sum()*64),internal_topological_endcap_tjunction_edges=internal,internal_edge_both_side_samples_missing=missing,seam_probe_offset_m=.002,triangles_upward=True,inverted=int((q<=0).sum()),min_altitude_m=float(alt.min()),max_xy_aspect_ratio=float(aspect.max()),max_reachable_xy_aspect_ratio=float(aspect[reachable].max()),min_triangle_3d_area_m2=float(area3d.min()),needle_altitude_under1mm=int((alt<.001).sum()),max_reachable_slope=float(slope[reachable].max()),
        duplicate_faces=len(f)-len(np.unique(np.sort(f,1),axis=0)),edges_incidence_over2=int((count>2).sum()),two_face_edges_same_direction=int(((count==2)&(direction!=0)).sum()),boundary_edges=int((count==1).sum()),
        exact_v002_road_xyz_oriented_multiset=exactroad,orthographic_uv_min=uvmin,orthographic_uv_max=uvmax,overlap=ov,protected_files=unchanged(),seconds=time.monotonic()-start)
    dump(OUT/'ground_audit.json',report);print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
