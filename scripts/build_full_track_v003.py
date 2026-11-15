#!/usr/bin/env python3
"""Fresh, offline v003: --prepare (.venv), --build (factory Blender), --validate (.venv).
No deployment, source-scene save, GUI, network, plugins or preference changes.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import argparse
import collections
import copy
import json
import math
import time
import os
import numpy as np
import build_full_track_v002 as V2
import full_track_v002_geometry as G
import full_track_v003_geometry as H
from prototype_geometry import require,station_normals
ROOT=V2.ROOT
OUT=ROOT/'data/processed/full_track_scene_v003'
EXPORT=ROOT/'exports/full_track_v003'
BLEND=ROOT/'blender/exelberg_full_v003.blend'
TRACK='exelberg_full_v003'
KN5=EXPORT/(TRACK+'.kn5')
OLD=ROOT/'data/processed/full_track_scene_v002/manifest.json'
ORTHO=ROOT/'data/processed/landscape_orthos_v003/manifest.json'
COLLECTIONS=('PHYS_ROAD','PHYS_GRAVEL','PHYS_GRASS','PHYS_WALL','VIS_MARKINGS','VIS_FOREST','VIS_WARNINGS','VIS_POSTS','AC_HELPERS')
BASE=('asphalt','gravel','bark','canopy','white')
record=V2.record
verified=V2.verified

def dump(p,d):
    with p.open('x') as f:json.dump(d,f,indent=2,allow_nan=False);f.write('\n')

def snapshot():
    paths=set()
    for directory in ('data/raw','data/interim','data/processed/full_track_inputs','data/processed/full_scenery_v003','data/processed/full_track_scene_v002','data/processed/landscape_orthos_v003','exports/full_track_v002','tools/vendor/kn5_studio'):
        paths.update(p for p in (ROOT/directory).rglob('*') if p.is_file())
    paths.add(ROOT/'blender/exelberg_full_v002.blend')
    old=json.loads((ROOT/'data/processed/full_track_scene_v002/source_hashes_before.json').read_text())
    paths.update(Path(p) for p in old if Path(p).is_file() and 'full_track_scene_v003' not in p)
    game=Path.home()/'.local/share/Steam/steamapps/common/assettocorsa/content/tracks/exelberg_full_v002'
    if game.exists():paths.update(p for p in game.rglob('*') if p.is_file())
    paths.add(ROOT/'scripts/validate_kn5.py') # Legacy sealed parser remains byte-for-byte.
    return {str(p):V2.sha256(p) for p in sorted(paths)}

def unchanged():
    before=json.loads((OUT/'source_hashes_before.json').read_text())
    bad=[p for p,h in before.items() if not Path(p).is_file() or V2.sha256(p)!=h]
    require(not bad,'Protected source changed: '+str(bad));V2.verify_install()
    return len(before)

def padding(rgb,mask):
    """Nearest Manhattan propagation into excluded texels only, never valid imagery."""
    rgb=rgb.copy();seen=mask.copy();q=collections.deque()
    # Seed only valid boundary pixels, not millions of interior pixels.
    padded=np.pad(mask,1,constant_values=False)
    boundary=mask&~(padded[:-2,1:-1]&padded[2:,1:-1]&padded[1:-1,:-2]&padded[1:-1,2:])
    q.extend(zip(*np.nonzero(boundary)))
    h,w=mask.shape
    while q:
        r,c=q.popleft()
        for rr,cc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
            if 0<=rr<h and 0<=cc<w and not seen[rr,cc]:
                rgb[rr,cc]=rgb[r,c];seen[rr,cc]=True;q.append((rr,cc))
    require(seen.all(),'Padding missing seed')
    return rgb

def mesh_record(records,name,v,f,uv,material,collection,surface=None,lod=0,corner_uv=None,**extra):
    v=np.asarray(v,dtype=np.float32);f=np.asarray(f,dtype=np.int32);uv=np.asarray(uv,dtype=np.float32)
    require(len(f)>0 and np.isfinite(v).all() and np.isfinite(uv).all(),'Invalid mesh '+name)
    cuv=uv[f] if corner_uv is None else np.asarray(corner_uv,dtype=np.float32)
    path=OUT/'meshes'/(name+'.npz');np.savez_compressed(path,vertices=v,triangles=f,uv=uv,corner_uv=cuv)
    flags=dict(active=1,visible=1,renderable=int(surface!='WALL'),cast_shadows=int(surface!='WALL'),transparent=0,layer=0)
    records.append(dict(name=name,artifact=record(path),vertices=len(v),triangles=len(f),material=material,collection=collection,
        surface_key=surface,collision=surface is not None,lod_out_m=lod,closed=False,
        role='inward_open_wall' if surface=='WALL' else 'upward_contact_skin' if surface else 'visual_only',flags=flags,**extra))

def chunk(records,prefix,v,f,material,collection,surface=None,lod=0,size=256,uv=None):
    uv=v[:,:2]/6 if uv is None else uv
    for j,(_,a,b,c) in enumerate(G.chunks(v,f,uv,size)):
        mesh_record(records,prefix+f'_{j:03d}',a,b,c,material,collection,surface,lod)

def prepare():
    require(not BLEND.exists() and not KN5.exists(),'Fresh assets only')
    OUT.mkdir(exist_ok=True);EXPORT.mkdir(exist_ok=True)
    require(not (OUT/'prepared.json').exists(),'Refuse prepared overwrite')
    (OUT/'meshes').mkdir();(OUT/'textures').mkdir()
    dump(OUT/'source_hashes_before.json',snapshot())
    old=json.loads(verified(record(OLD)).read_text());orth=json.loads(ORTHO.read_text());records=[];parts=[];counts=collections.Counter();proof=[]
    for spec in old['meshes']:
        path=verified(spec['artifact'])
        if spec['surface_key'] in ('ROAD','GRAVEL','GRASS'):
            with np.load(path,allow_pickle=False) as a:v,f,cuv=H.extract_top(a)
            key=spec['surface_key'];counts[key]+=len(f);proof.append(dict(source=spec['artifact'],top_triangles=len(f),half_vertices=len(v)))
            parts.append((key,v,f,np.full(len(f),-1,dtype=np.int64)))
        elif not spec['collision'] and spec['collection']!='VIS_FOREST':
            with np.load(path,allow_pickle=False) as a:
                v=a['vertices'];f=a['triangles'];uv=a['uv'] if 'uv' in a else np.zeros((len(v),2));cu=a['corner_uv'] if 'corner_uv' in a else uv[f]
            mesh_record(records,spec['name'],v,f,uv,spec['material'],spec['collection'],lod=spec['lod_out_m'],corner_uv=cu)
    require(dict(counts)==dict(ROAD=32620,GRAVEL=77215,GRASS=503956),'Independent extracted top counts '+str(counts))
    dump(OUT/'top_extraction.json',dict(counts=dict(counts),construction='first half vertices and faces with all indices < half; original slabs untouched',sources=proof))
    print('EXTRACTED TOPS',counts,flush=True)
    with np.load(ROOT/'data/processed/full_track_scene_v002/geometry_audit.npz') as a:
        p=a['designed_xyz_m'];raw=a['raw_xyz_m'];audit_v=a['clipped_terrain_xyz_m'].astype(np.float32);audit_f=a['clipped_terrain_triangles'];audit_cells=a['terrain_triangle_source_cell']
        np.savez_compressed(OUT/'v002_reference.npz',**{k:a[k] for k in a.files})
    # Match exact original oriented terrain triangles to their original cell IDs, never nearest texture.
    source={bytes(k):int(c) for k,c in zip(H.triangles_key(audit_v,audit_f),audit_cells)}
    for j,(role,v,f,c) in enumerate(parts):
        if role=='GRASS':c=np.array([source[bytes(k)] for k in H.triangles_key(v,f)]);parts[j]=(role,v,f,c)
    # Road-first fixed vertices, then gravel, then terrain.
    require((OUT/'repaired_skin.npz').is_file(),'Run factory Blender full_track_v003_repair.py first')
    with np.load(OUT/'repaired_skin.npz') as a:
        v=a['vertices'];f=a['triangles'];roles=a['roles'];cells=a['source_cell'];protected=a['source_xyz_m'];dist=a['distance_to_route_m'];delta=a['delta_z_m'];reachable=a['reachable_triangles']
    weld=dict(method='Blender global constrained Delaunay; original road constraints restored exactly; 8mm topology-safe micro-edge collapse + within-cell needle flip',repair_report=record(OUT/'repair_report.json'))
    q,alt,slopes=H.quality(v,f)
    duplicate=len(f)-len(np.unique(np.sort(f,axis=1),axis=0))
    diagnostics=dict(weld=weld,triangles=len(f),inverted=int((q<=0).sum()),min_altitude_m=float(alt.min()),needle_under_1mm=int((alt<.001).sum()),duplicate_triangles=duplicate,
        max_reachable_slope=float(slopes[reachable&(roles!='ROAD')].max()),apron_delta_m=G.stats(delta),changed_vertices=int(np.count_nonzero(delta)))
    dump(OUT/'ground_diagnostics.json',diagnostics)
    np.savez_compressed(OUT/'contact_skin.npz',vertices=v,triangles=f,roles=roles,source_cell=cells,distance_to_route_m=dist,source_xyz_m=protected,delta_z_m=v[:,2]-protected[:,2],designed_xyz_m=p,reachable_triangles=reachable)
    print('GROUND',diagnostics,flush=True)
    require((q>0).all() and duplicate==0,'Invalid or duplicated contact faces')
    require(slopes[reachable&(roles!='ROAD')].max()<.301,'Reachable apron slope >30.1%')
    require(alt.min()>.001,'Needle contact triangle altitude below1mm')
    # Ground shares one topology; spatial partition never extrudes or closes it.
    for role,mat in [('ROAD','asphalt'),('GRAVEL','gravel')]:
        ff=f[roles==role];chunk(records,'1'+role,v,ff,mat,'PHYS_'+role,role)
    terrain=np.load(ROOT/'data/processed/full_track_inputs/terrain.npz');ncols=terrain['valid_cells'].shape[1]
    terrain_mask=roles=='GRASS';tile=np.full(len(f),-1)
    for c in orth['chunks']:
        r0,r1,c0,c1=c['node_slice'];r=cells//ncols;col=cells%ncols
        use=terrain_mask&(r>=r0)&(r<r1-1)&(col>=c0)&(col<c1-1);require((tile[use]<0).all(),'Overlapping tile ownership');tile[use]=c['index']
        ff=f[use];require(len(ff)>0,'Missing ortho terrain')
        west,south,east,north=c['local_bounds'];uv=(v[:,:2]-[west,south])/[east-west,north-south]
        # Split by spatial cell only after original source-cell material ownership.
        chunk(records,'1GRASS_ORTHO_'+f'{c["index"]:03d}',v,ff,'ortho_'+f'{c["index"]:03d}','PHYS_GRASS','GRASS',lod=0,size=512,uv=uv)
    require((tile[terrain_mask]>=0).all(),'Unmapped terrain triangle')
    # A near-road material may avoid canopy imagery; source cell ownership remains in audit.
    # For now retain orthos throughout, without pretending canopy is asphalt imagery.
    import imagecodecs
    textures=[];controls=[]
    for name in BASE:
        rec=next(t for t in old['textures'] if Path(t['path']).name=='v002_'+name+'.dds');src=verified(rec);dest=EXPORT/src.name
        with dest.open('xb') as o:o.write(src.read_bytes())
        textures.append(dict(material=name,name='V002_'+name,artifact=record(dest),source=rec,unchanged=True))
    for name,rgb in [('post_black',[20,22,23]),('reflector',[235,235,222])]:
        png=OUT/'textures'/(name+'.png');png.write_bytes(imagecodecs.png_encode(np.tile(np.array(rgb,dtype=np.uint8),(4,4,1))))
        textures.append(dict(material=name,name='V003_'+name,png=record(png),rgb=rgb))
    for c in orth['chunks']:
        src=ROOT/c['path'];require(V2.sha256(src)==c['sha256'],'Ortho input hash');rgb=imagecodecs.png_decode(src.read_bytes());mask=imagecodecs.png_decode((ROOT/c['mask_path']).read_bytes())>0
        padded=padding(rgb,mask);require(np.array_equal(padded[mask],rgb[mask]),'Padding altered actual imagery')
        png=OUT/'textures'/('ortho_'+f'{c["index"]:03d}'+'.png');png.write_bytes(imagecodecs.png_encode(padded))
        textures.append(dict(material='ortho_'+f'{c["index"]:03d}',name='V003_ortho_'+f'{c["index"]:03d}',png=record(png),source_chunk=c,
            padding='Excluded texels nearest-Manhattan edge extension only; no terrain creation; valid RGB unchanged'))
        rows,cols=np.nonzero(mask)
        for j in np.linspace(0,len(rows)-1,7).astype(int):
            row,col=int(rows[j]),int(cols[j]);west,north,dx,dy=c['local_transform'];x=west+(col+.5)*dx;y=north+(row+.5)*dy
            controls.append(dict(chunk=c['index'],pixel_row_col=[row,col],local_EN_m=[x,y],blender_uv=[(col+.5)/c['width'],1-(row+.5)/c['height']],kn5_uv=[(col+.5)/c['width'],(row+.5)/c['height']],rgb=rgb[row,col].tolist()))
    dump(OUT/'ortho_controls.json',controls)
    # Re-ground every original tree on final contact skin; preserve dimensions/seed/count.
    ground=H.GroundIndex(v,f);treefile=ROOT/'data/processed/full_track_scene_v002/forest_grounding.npz'
    with np.load(treefile) as a:anchors=a['visible_terrain_xyz_m'].copy();original_anchors=anchors.copy()
    for a in anchors:a[2]=ground.sample(a[:2])
    np.savez_compressed(OUT/'forest_grounding.npz',v002_xyz_m=original_anchors,visible_terrain_xyz_m=anchors,z_delta_m=anchors[:,2]-original_anchors[:,2])
    for (vv,ff),mat in zip(G.tree_geometry(anchors),('bark','canopy')):
        per=20 if mat=='bark' else 32;keys,inv=np.unique(np.floor(anchors[:,:2]/128).astype(int),axis=0,return_inverse=True)
        uv=np.column_stack([vv[:,0]/3,vv[:,2]/3]) if mat=='bark' else vv[:,:2]/8
        for j in range(len(keys)):
            ids=(np.flatnonzero(inv==j)[:,None]*per+np.arange(per)).ravel();used,local=np.unique(ff[ids],return_inverse=True)
            mesh_record(records,'VIS_FOREST_'+mat.upper()+f'_{j:03d}',vv[used],local.reshape(-1,3),uv[used],mat,'VIS_FOREST',lod=900)
    # Wall lower/upper bounds use every final adjacent face's FULL bounds, not road Z alone.
    normals=station_normals(p);wallmetrics=[]
    for side,label in [(-1,'R'),(1,'L')]:
        xy=p[:,:2]+side*6*normals;low=np.empty(len(p));high=low.copy()
        bounds=np.array([ground.bounds(a,b) for a,b in zip(xy[:-1],xy[1:])])
        bounds[:,0]=np.minimum(bounds[:,0],np.minimum(p[:-1,2],p[1:,2]));bounds[:,1]=np.maximum(bounds[:,1],np.maximum(p[:-1,2],p[1:,2]))
        for i in range(len(p)):
            adjacent=bounds[max(i-1,0):min(i+1,len(bounds))];low[i]=adjacent[:,0].min()-1.01;high[i]=adjacent[:,1].max()+3.01
        vv,ff=H.wall_strip(xy,low,high,side);chunk(records,'1WALL_'+label,vv,ff,'post_black','PHYS_WALL','WALL',size=256)
        # All segment interiors are covered by conservative face bounds, plus actual ground samples.
        clearance=[]
        for i,(a,b) in enumerate(zip(xy[:-1],xy[1:])):
            for t in (0,.25,.5,.75,1):
                z=ground.sample(a*(1-t)+b*t);clearance.append([z-((1-t)*low[i]+t*low[i+1]),((1-t)*high[i]+t*high[i+1])-max(z,(1-t)*p[i,2]+t*p[i+1,2])])
        clearance=np.asarray(clearance);require(clearance[:,0].min()>=1 and clearance[:,1].min()>=3,'Wall height coverage')
        wallmetrics.append(dict(side=label,offset_m=side*6,triangles=len(ff),min_below_ground_m=float(clearance[:,0].min()),min_above_ground_road_m=float(clearance[:,1].min()),interior_samples=len(clearance),conservative_adjacent_face_bounds=True))
    for label,i,sign in [('START',0,1),('END',len(p)-1,-1)]:
        xy=np.array([p[i,:2]-6*normals[i],p[i,:2]+6*normals[i]])
        lo,hi=ground.bounds(*xy);lo=min(lo,p[i,2])-1.01;hi=max(hi,p[i,2])+3.01
        vv,ff=H.wall_strip(xy,[lo,lo],[hi,hi],sign)
        mesh_record(records,'1WALL_'+label,vv,ff,vv[:,[0,2]],'post_black','PHYS_WALL','WALL')
    posts=make_posts(records,p,ground)
    # Actual full skin BVH is independently queried in Blender during build.
    surfaces=copy.deepcopy(old['surfaces'])
    for key,s in surfaces.items():s['source_objects']=[m['name'] for m in records if m['surface_key']==key];s['objects']=s['source_objects'].copy();s.update(damping=0,sin_height=0,sin_length=0,vibration_gain=0,vibration_length=0)
    m=copy.deepcopy({k:old[k] for k in ('coordinates','route','design','helpers','paint','timing_contract','spawn_contract','attribution')})
    m.update(schema='assetto-exelberg.full-track-scene',version=3,track_id=TRACK,status='PREPARED_NOT_EXPORTED',meshes=records,textures=textures,surfaces=surfaces,export_collections=list(COLLECTIONS),
        source_v002=record(OLD),source_orthos=record(ORTHO),top_extraction=record(OUT/'top_extraction.json'),ground=diagnostics,
        apron=dict(policy='Station-conforming shoulder from existing3.75m boundary. Harmonic reachable apron through6m, gradient projected to30%; zero-flux containment boundary decouples opposing hairpin elevations. Outside barrier: provisional road-profile plateau to20m, cubic fade20–40m to derived v002 terrain; not measured.',maximum_offset_m=40),
        barriers=dict(side_strips=wallmetrics,flags=dict(active=1,visible=1,renderable=0,cast_shadows=0,transparent=0,layer=0),surface_key='WALL',end_containment='single inward shell at each source endpoint; no visible walls',high_speed_guarantee=False),
        posts=posts,forest=dict(count=len(anchors),regrounded=int(np.count_nonzero(anchors[:,2]-original_anchors[:,2])),delta_m=G.stats(anchors[:,2]-original_anchors[:,2]),source='same 4616 v002 procedural trees, exact seed/shape; not surveyed'),
        landscape=dict(chunks=26,original_source_cells=True,uv='u east, v north; exporter (u,1-v)',controls=record(OUT/'ortho_controls.json'),padding_only=True),
        source_preservation=dict(before=record(OUT/'source_hashes_before.json'),protected_files=unchanged()),
        runtime=dict(ac_tested=False,game_deployed=False,gui_accessed=False,preferences_saved=False),outputs=[])
    m['timing_contract'].update(endcap_inset_m=0,usable_runout_to_near_face_of_endcap_m=300,usable_runout_to_end_wall_m=300,explicit_braking_geometry='Unchanged final 300m asphalt, BRAKE signs at300/150m and STOP at60m; no above-ground physical obstacles until invisible endpoint shell',runtime_verified=False)
    m['spawn_contract']['runtime_verified']=False;m['spawn_contract']['source_v002_user_confirmed_correct']=True
    dump(OUT/'prepared.json',m)
    print('PREPARED',len(records),'meshes',sum(x['triangles'] for x in records),'triangles',flush=True)

def make_posts(records,p,ground):
    from pyproj import Transformer
    import xml.etree.ElementTree as ET
    # Existing OSM only. Connection nodes on non-route highway ways close to alignment.
    ways={};nodes={};transform=Transformer.from_crs(4326,25833,always_xy=True)
    for path in sorted((ROOT/'data/raw/osm').glob('map_*.osm')):
        root=ET.parse(path).getroot()
        for n in root.findall('node'):nodes[n.attrib['id']]=(float(n.attrib['lon']),float(n.attrib['lat']))
        for w in root.findall('way'):
            tags={x.attrib['k']:x.attrib['v'] for x in w.findall('tag')}
            if 'highway' in tags:ways[w.attrib['id']]=([n.attrib['ref'] for n in w.findall('nd')],tags)
    connections=[]
    for refs,tags in ways.values():
        if tags['highway'] not in ('service','residential','unclassified','tertiary','secondary','primary','track'):continue
        # End nodes represent possible driveable connections; route endpoints also conservatively skipped.
        for n in (refs[0],refs[-1]):
            if n in nodes:
                e,no=transform.transform(*nodes[n]);connections.append([e-589500,no-5346800])
    if connections:
        xy=np.unique(np.array(connections),axis=0);ii,tt,dd=H.local_nearest(xy,p);ss=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
        connection_s=ss[ii]+tt*(ss[ii+1]-ss[ii]);connection_s=connection_s[dd<9]
    else:connection_s=np.array([])
    s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))];normal=station_normals(p);placements=[];skips=[];geoms={k:[[],[]] for k in ('white','post_black','reflector')}
    for d in np.arange(33,s[-1]-20,33):
        reason='possible existing OSM driveable connection within12m' if len(connection_s) and abs(connection_s-d).min()<12 else None
        for side in (-1,1):
            if reason:skips.append(dict(arclength_m=float(d),side=side,reason=reason));continue
            i=min(int(np.searchsorted(s,d)-1),len(p)-2);t=(d-s[i])/(s[i+1]-s[i]);a=p[i]*(1-t)+p[i+1]*t;n=normal[i]*(1-t)+normal[i+1]*t;n/=np.linalg.norm(n);xy=a[:2]+side*4.1*n;z=ground.sample(xy)
            placements.append(dict(arclength_m=float(d),offset_left_m=side*4.1,ground_xyz_m=[*xy.tolist(),z],height_m=1.1))
            for mat,base,height,size in [('white',0,.72,[.12,.16,.72]),('post_black',.72,.24,[.13,.17,.24]),('white',.96,.14,[.12,.16,.14]),('reflector',.79,.09,[.145,.175,.09])]:
                vv,ff=H.box([*xy,z+base+height/2],size);vs,fs=geoms[mat];fs.extend((ff+len(vs)).tolist());vs.extend(vv)
    for mat,(v,f) in geoms.items():
        vv=np.asarray(v);ff=np.asarray(f);chunk(records,'VIS_POST_'+mat.upper(),vv,ff,mat,'VIS_POSTS',lod=700,size=256)
    dump(OUT/'posts.json',dict(placements=placements,skips=skips,osm_possible_connections_arclength_m=connection_s.tolist()))
    return dict(count=len(placements),skipped=len(skips),nominal_spacing_m=33,offset_left_m=[-4.1,4.1],max_height_m=1.1,collision=False,artifact=record(OUT/'posts.json'),
        design='Simplified Austrian-style white guidepost, black band, pale reflector; nominal not measured. Reflector colour/compliance not established; not RVS certification.',connection_heuristic='Existing OSM drivable way endpoints within9m of designed route; omit posts within12m along route, conservative both sides')

def build():
    import bpy
    from mathutils import Matrix,Vector
    from mathutils.bvhtree import BVHTree
    require(bpy.app.background and not bpy.data.filepath,'Factory headless required')
    require(not BLEND.exists() and not KN5.exists(),'Refuse existing blend/KN5')
    started=time.monotonic();m=json.loads((OUT/'prepared.json').read_text());unchanged()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections):bpy.data.collections.remove(c)
    groups={}
    for name in (*COLLECTIONS,'REFERENCE_ONLY_EXCLUDED','PREVIEW_ONLY_EXCLUDED'):
        c=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(c);groups[name]=c
    addon=V2.import_addon();materials={};texrecs=[]
    for t in m['textures']:
        name=t['material'];mat=bpy.data.materials.new(t['name']);ac=mat.assettoCorsa;ac.preset_selector='NONE';ac.shader_name='ksPerPixel';ac.blend_mode='0';ac.depth_mode='0';ac.alpha_tested=False
        if 'artifact' in t:
            path=verified(t['artifact']);image=bpy.data.images.load(str(path),check_existing=False)
        else:
            image=bpy.data.images.load(str(verified(t['png'])),check_existing=False)
            path=EXPORT/('v003_'+name+'.dds');payload=addon.dds.image_to_bgra_dds(image)
            with path.open('xb') as f:f.write(payload)
            t['artifact']=record(path)
        image.name=t['name'];image.pack()
        for key,value in dict(ksAmbient=.45,ksDiffuse=.65,ksSpecular=.12 if name=='asphalt' else .03,ksSpecularEXP=12.).items():ac.set_property(key,value)
        ac.ensure_default_slots_for_shader('ksPerPixel');ac.texture_slots[0].image=image;ac.texture_slots[0].override_filename=path.name
        addon.materials.sync_material_nodes(mat);materials[name]=mat;texrecs.append(record(path))
        t['actual_blender_material']=dict(name=mat.name,image=image.name,size=list(image.size),node_images=[n.image.name for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image],shader=ac.shader_name,slot_filename=path.name)
    objects=[]
    for j,s in enumerate(m['meshes']):
        with np.load(verified(s['artifact']),allow_pickle=False) as a:v=a['vertices'];f=a['triangles'];cuv=a['corner_uv']
        mesh=bpy.data.meshes.new(s['name']);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update();layer=mesh.uv_layers.new(name='UVMap');layer.data.foreach_set('uv',cuv.ravel())
        # Flat top-only ground avoids side-skirt normal averaging. Asphalt keeps smooth v002 convention.
        mesh.polygons.foreach_set('use_smooth',np.full(len(f),s['collection'] in ('PHYS_ROAD','VIS_MARKINGS','VIS_FOREST'),dtype=bool))
        mesh.materials.append(materials[s['material']]);obj=bpy.data.objects.new(s['name'],mesh);groups[s['collection']].objects.link(obj)
        ac=obj.assettoCorsa
        for k in ('visible','renderable','cast_shadows','transparent'):setattr(ac,k,bool(s['flags'][k]))
        ac.layer=0;ac.lod_in=0;ac.lod_out=s['lod_out_m'];obj['collision_intended']=s['collision'];obj['role']=s['role'];obj['surface_key']=s['surface_key'] or '';obj['source_artifact']=s['artifact']['path']
        if s['surface_key']=='WALL':obj.hide_render=True
        objects.append(obj)
        if j%100==0:print('SCENE',j,'/',len(m['meshes']),flush=True)
    for h in m['helpers']:
        obj=bpy.data.objects.new(h['name'],None);groups['AC_HELPERS'].objects.link(obj);obj.matrix_world=Matrix(h['blender_matrix_rows']);obj.empty_display_type='ARROWS';objects.append(obj)
    with np.load(OUT/'contact_skin.npz') as a:v=a['vertices'];f=a['triangles'];p=a['designed_xyz_m']
    bvh=BVHTree.FromPolygons(v.tolist(),f.tolist(),all_triangles=True,epsilon=0)
    bvh_count=0;min_below=1e9;min_above=1e9;inward=1
    for spec in m['meshes']:
        if spec['surface_key']!='WALL':continue
        with np.load(verified(spec['artifact'])) as a:wv=a['vertices'];wf=a['triangles']
        # Face vertices, centroids and edge midpoints: includes diagonal interiors, not only stations.
        tri=wv[wf].astype(float)
        for t in tri:
            xytests=np.vstack([t[:,:2],t[:,:2].mean(0),(t[:,:2]+np.roll(t[:,:2],1,axis=0))/2])
            for xy in xytests:
                hit=bvh.ray_cast(Vector((float(xy[0]),float(xy[1]),1000)),Vector((0,0,-1)),2000)
                require(hit[0] is not None,'BVH wall ground coverage');bvh_count+=1
        if spec['name'].startswith(('1WALL_L_','1WALL_R_')):
            centers=tri.mean(1);ni,nt,nd=G.nearest(centers[:,:2],p);n=station_normals(p);nn=n[ni]*(1-nt[:,None])+n[ni+1]*nt[:,None];side=1 if spec['name'].startswith('1WALL_L_') else -1
            cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);dot=np.sum(cross[:,:2]*(-side*nn),axis=1)/np.linalg.norm(cross,axis=1);inward=min(inward,float(dot.min()));require((dot>0).all(),'Outward side wall')
        else:
            tangent=(p[1,:2]-p[0,:2]) if spec['name']=='1WALL_START' else (p[-2,:2]-p[-1,:2]);tangent/=np.linalg.norm(tangent)
            cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);dot=(cross[:,:2]*tangent).sum(1)/np.linalg.norm(cross,axis=1)
            require((dot>0).all(),'Outward endpoint wall');inward=min(inward,float(dot.min()))
    m['bvh_ground_validation']=dict(actual_blender_bvh=True,triangle_vertex_centroid_edge_samples=bvh_count,missing=0,min_inward_normal_dot=inward,
        height_coverage='Per-segment complete adjacent-face min/max bounds plus 5 interpolated ground samples; see barriers')
    require(not addon.materials.audit_texture_bindings([o for o in objects if o.type=='MESH'],'EMBEDDED_DDS'),'Texture bindings')
    from full_track_v002_export import exporter_class
    print('EXPORT',len(objects),'objects',flush=True)
    exporter=exporter_class(addon)(bpy.context,str(KN5),dict(version=5,texture_mode='EMBEDDED_DDS',target_objects=objects,apply_modifiers=False,auto_detect_materials=False,auto_fix_wheels=False,selection_only=False))
    model=exporter.export();require(not exporter.warnings,'Exporter warnings '+str(exporter.warnings));require(model.root_node.name==TRACK,'Wrong root')
    with KN5.open('xb') as f:model.to_stream(f)
    require(KN5.stat().st_size<=256*1024*1024,'Generated file budget256MiB')
    m['export_allowlist']=[o.name for o in objects];m['export_corner_adapter']=dict(artifact=record(ROOT/'scripts/full_track_v002_export.py'),vendor_modified=False,meshes=exporter.corner_adapter)
    m['outputs']=[record(KN5)]+texrecs
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene['origin_ENH_m']=[589500,5346800,300];scene['README']='v003 offline candidate; nominal apron/posts; no runtime claim. See FULL_TRACK_V003.md.'
    text=bpy.data.texts.new('V003_EDITABLE_AUTHORING_CONTRACT.json');text.write(json.dumps(m,indent=2))
    ref=groups['REFERENCE_ONLY_EXCLUDED'];ref.hide_render=True;ref.hide_viewport=True
    with np.load(OUT/'v002_reference.npz') as a:
        for label,key in [('RAW_OSM_DTM_UNCHANGED','raw_xyz_m'),('DESIGNED_CENTERLINE_V002_UNCHANGED','designed_xyz_m')]:
            xyz=a[key];curve=bpy.data.curves.new(label,'CURVE');curve.dimensions='3D';line=curve.splines.new('POLY');line.points.add(len(xyz)-1);line.points.foreach_set('co',np.column_stack([xyz,np.ones(len(xyz))]).ravel());obj=bpy.data.objects.new(label,curve);ref.objects.link(obj)
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=True
    scene.render.resolution_x=1280;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.48,.60,.8,1);scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.65
    light=bpy.data.lights.new('PREVIEW_SUN','SUN');light.energy=2.5;light.angle=.15;obj=bpy.data.objects.new('PREVIEW_SUN',light);groups['PREVIEW_ONLY_EXCLUDED'].objects.link(obj);obj.rotation_euler=(.5,-.4,-.3)
    def camera(name,pos,target,ortho=None):
        data=bpy.data.cameras.new(name);obj=bpy.data.objects.new(name,data);groups['PREVIEW_ONLY_EXCLUDED'].objects.link(obj);obj.location=pos;obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler();data.clip_end=30000;data.lens=26
        if ortho:data.type='ORTHO';data.ortho_scale=ortho
        return obj
    center=(p.min(0)+p.max(0))/2;overview=camera('PREVIEW_OVERVIEW',center+[0,-2500,10000],center,11000)
    st=V2.station(p,2050);pos=np.array(st['point']);forward=np.array(st['forward_xy']);pos[:2]+=[forward[1]*1.5,-forward[0]*1.5];pos[2]+=1.25
    driver=camera('PREVIEW_DRIVER',pos,pos+np.r_[forward*50,0])
    postdata=json.loads((OUT/'posts.json').read_text())['placements'];post=min(postdata,key=lambda x:abs(x['arclength_m']-2050));target=np.array(post['ground_xyz_m'])+[0,0,.55];detail=camera('PREVIEW_POST_DETAIL',target+np.r_[forward*-3,1],target)
    previews=[]
    for cam,name in [(driver,'driver'),(overview,'overview'),(detail,'post_detail')]:
        scene.camera=cam;scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True);previews.append(record(OUT/(name+'.png')))
    scene.camera=driver
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND),check_existing=True,copy=True)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND),load_ui=False,use_scripts=False)
    require(all(n in bpy.data.objects for n in m['export_allowlist']),'Saved inventory')
    for h in m['helpers']:require(np.allclose(np.array(bpy.data.objects[h['name']].matrix_world),h['blender_matrix_rows'],atol=.0004,rtol=0),'Saved helper')
    m['runtime'].update(blender=bpy.app.version_string,blender_background=True,actual_cpu_previews=3,resolution=[1280,800],samples=8,saved_copy_reloaded=True,elapsed_seconds=time.monotonic()-started)
    m['outputs']+=[record(BLEND)]+previews;m['source_preservation']['checked_after_files']=unchanged();m['status']='EXPORTED_PENDING_INDEPENDENT_VALIDATION'
    dump(OUT/'exported.json',m);print('BLENDER PASS',m['runtime'],flush=True)

def validate(persist=True):
    from full_track_v003_kn5 import parse
    from validate_kn5 import bounded_read,compare_corners
    m=json.loads((OUT/'exported.json').read_text());unchanged()
    for rec in m['outputs']:verified(rec)
    model=parse(bounded_read(KN5,max_file=256*1024*1024),max_file=256*1024*1024,max_nodes=4096,max_texture=8*1024*1024,max_materials=128,max_textures=128)
    require(model['root']['name']==TRACK and np.array_equal(model['root']['matrix'],np.eye(4).ravel()),'Root')
    specs={s['name']:s for s in m['meshes']};groups={s:[] for s in specs};nodes={n['name']:n for n in model['nodes']};reports=[]
    with np.load(OUT/'contact_skin.npz') as a:route=a['designed_xyz_m']
    for h in m['helpers']:
        n=nodes[h['name']];require(n['kind']==1 and n['parent']==TRACK and n['active']==1 and np.allclose(n['matrix'],h['kn5_expected'],atol=.0004,rtol=0),'Helper changed')
    for n in model['nodes']:
        if n['kind']==1:
            require(n['name'] in [TRACK,*groups,*[h['name'] for h in m['helpers']]],'Unallowlisted dummy');continue
        source=n['name'] if n['name'] in groups else n['name'].rsplit('_SUB',1)[0];require(source in specs,'Unallowlisted mesh');s=specs[source];groups[source].append(n)
        require(all(n[k]==v for k,v in s['flags'].items()),'Flags '+n['name']);require(model['materials'][n['material']]['name']==next(t['name'] for t in m['textures'] if t['material']==s['material']),'Material')
        require(n['name'].startswith('1'+s['surface_key']+'_') if s['collision'] else not n['name'][0].isdigit(),'Collision name')
        vertices=n['vertices'];normal=vertices[:,3:6].astype(float);tan=vertices[:,8:].astype(float)
        require(len(vertices)<=65535 and np.max(abs(np.linalg.norm(normal,axis=1)-1))<2e-5,'Unit/bounded vertices')
        require(np.max(abs(np.linalg.norm(tan,axis=1)-1))<2e-5 and np.max(abs((tan*normal).sum(1)))<2e-5,'Tangent frame')
        tri=vertices[n['indices'],:3].astype(float);cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);require((np.linalg.norm(cross,axis=1)>1e-10).all(),'Collapsed export')
        require(((cross*normal[n['indices']].mean(1)).sum(1)>0).all(),'Normal/winding disagreement')
        if s['role']=='upward_contact_skin':require((cross[:,1]>0).all(),'Exported non-upward ground')
        if s['surface_key']=='WALL':
            blender_tri=tri[:,:,[0,2,1]].copy();blender_tri[:,:,1]*=-1;centers=blender_tri.mean(1)
            if source.startswith(('1WALL_L_','1WALL_R_')):
                ii,tt,dd=H.local_nearest(centers[:,:2],route);normals=station_normals(route);nn=normals[ii]*(1-tt[:,None])+normals[ii+1]*tt[:,None];side=1 if source.startswith('1WALL_L_') else -1;intended=-side*nn
            else:
                intended=route[1,:2]-route[0,:2] if source=='1WALL_START' else route[-2,:2]-route[-1,:2]
            geometric=np.cross(blender_tri[:,1]-blender_tri[:,0],blender_tri[:,2]-blender_tri[:,0]);require(((geometric[:,:2]*intended).sum(1)>0).all(),'Exported wall not inward')
        require(np.allclose(n['lod_sphere'][:2],[0,s['lod_out_m']]),'LOD')
        require(np.linalg.norm(vertices[:,:3]-n['lod_sphere'][2:5],axis=1).max()<=n['lod_sphere'][5]+.005,'Bounding sphere')
        reports.append(dict(name=n['name'],source=source,surface_key=s['surface_key'],vertices=len(vertices),triangles=len(n['indices']),flags=s['flags'],material=s['material'],lod_out_m=s['lod_out_m']))
    for name,parts in groups.items():
        require(parts,'Missing source');s=specs[name]
        with np.load(verified(s['artifact'])) as a:v=a['vertices'];f=a['triangles'];uv=a['corner_uv'].copy()
        xyz=v[:,[0,2,1]].copy();xyz[:,2]*=-1;uv[:,:,1]=1-uv[:,:,1]
        compare_corners(np.concatenate([xyz[f],uv],axis=2),np.concatenate([n['vertices'][n['indices']][:,:,[0,1,2,6,7]] for n in parts]))
    require(len(model['textures'])==len(model['materials'])==33,'Texture/material total')
    for t in m['textures']:
        path=verified(t['artifact']);actual=next(a for a in model['textures'] if a['name']==path.name);require(actual['data']==path.read_bytes(),'Embedded DDS');mat=next(a for a in model['materials'] if a['name']==t['name']);require(mat['bindings']==[('txDiffuse',0,path.name)] and mat['shader']=='ksPerPixel','Diffuse binding')
        require(mat['blend']==mat['alpha']==mat['depth']==0,'Opaque material contract')
        import struct
        payload=actual['data'];header=struct.unpack('<31I',payload[4:128]);height,width=header[2:4]
        require(payload[:4]==b'DDS ' and header[0]==124 and 0<max(height,width)<=512 and len(payload)==128+height*width*4,'Bounded BGRA DDS')
        require((np.frombuffer(payload[128:],np.uint8).reshape(-1,4)[:,3]==255).all(),'DDS alpha')
    for key,s in m['surfaces'].items():s['objects']=[r['name'] for r in reports if r['surface_key']==key]
    ground_audit=json.loads((OUT/'ground_audit.json').read_text());require(ground_audit['status']=='PASS','Ground audit blocked')
    result=dict(status='PASS_INDEPENDENT_OFFLINE_NOT_RUNTIME',inward_walls_actual_kn5=True,ground_audit=record(OUT/'ground_audit.json'),nodes=len(model['nodes']),mesh_nodes=len(reports),triangles=sum(r['triangles'] for r in reports),vertices=sum(r['vertices'] for r in reports),max_mesh_vertices=max(r['vertices'] for r in reports),bytes=KN5.stat().st_size,materials=len(model['materials']),textures=len(model['textures']),exact_oriented_xyz_uv=True,meshes=reports,ac_runtime_tested=False)
    if not persist:
        print('READ-ONLY VALIDATION PASS',{k:v for k,v in result.items() if k!='meshes'},flush=True);return result
    dump(OUT/'independent_validation.json',result);m['static_checks']=result;m['outputs'].append(record(OUT/'independent_validation.json'));m['status']=result['status'];m['source_preservation']['checked_after_validation_files']=unchanged()
    m['builders']=[record(ROOT/'scripts'/s) for s in ('build_full_track_v003.py','full_track_v003_geometry.py','full_track_v003_repair.py','full_track_v003_kn5.py','audit_full_track_v003.py','full_track_v002_export.py','validate_kn5.py')]
    dump(OUT/'manifest.json',m);print('VALIDATED',{k:v for k,v in result.items() if k!='meshes'},flush=True)

def finalize():
    """Seal explicit candidate assets/evidence, without touching existing scenes."""
    import re
    m=json.loads((OUT/'manifest.json').read_text());require('documentation' not in m,'Already finalized')
    log=(OUT/'tests.log').read_text();match=re.search(r'Ran (\d+) tests in ([0-9.]+)s',log)
    require(match and '\nOK\n' in log and 'FAILED' not in log,'Full tests must pass')
    audit=json.loads((OUT/'ground_audit.json').read_text());require(audit['status']=='PASS','Ground audit')
    old=json.loads(OLD.read_text());require(m['helpers']==old['helpers'] and m['design']==old['design'],'v002 helper/dip regression')
    m['forest'].update(source_grounding=record(ROOT/'data/processed/full_track_scene_v002/forest_grounding.npz'),source_trees=record(ROOT/'data/processed/full_scenery_v003/forest_trees.npz'),row_order_unchanged=True,shape_seed=2002)
    m['attribution']='DTM and orthophotos © BEV, CC BY4.0; OSM © OpenStreetMap contributors, ODbL. Procedural road/post/tree materials and tree/post geometry authored offline in this project. See source orthophoto manifest for exact provenance.'
    m['tests']=dict(passed=int(match[1]),seconds=float(match[2]),command='PYTHONDONTWRITEBYTECODE=1 timeout240s .venv/bin/python -m unittest discover -s tests -q',artifact=record(OUT/'tests.log'))
    m['documentation']=record(ROOT/'docs/validation/FULL_TRACK_V003.md');m['ground_audit']=audit
    m['timing_contract']['usable_runout_to_near_face_of_endcap_m']=300
    m['authoring_contract']='Embedded scene text is a prepared/pre-export snapshot; this external sealed manifest is authoritative for final evidence and runout values.'
    m['source_proofs']=dict(v002_scene=record(ROOT/'blender/exelberg_full_v002.blend'),v002_manifest=record(OLD),v002_kn5=record(ROOT/'exports/full_track_v002/exelberg_full_v002.kn5'),helpers_exact=True,design_dip_bridge_exact=True,asphalt_oriented_xyz_corner_uv_exact=True,asphalt_dds_exact=True,raw_reference=record(OUT/'v002_reference.npz'),legacy_parser_unchanged=record(ROOT/'scripts/validate_kn5.py'))
    uv_tables=[]
    for t in m['textures']:
        t['shader_properties']=dict(ksAmbient=.45,ksDiffuse=.65,ksSpecular=.12 if t['material']=='asphalt' else .03,ksSpecularEXP=12.)
        t['colour_contract']='Unchanged v002 procedural DDS' if t.get('unchanged') else 'Native ungraded source RGB; padding only' if 'source_chunk' in t else 'Procedural RGB '+str(t.get('rgb'))
        if 'source_chunk' in t:
            c=t['source_chunk'];uv_tables.append(dict(index=c['index'],source_node_slice=c['node_slice'],local_bounds=c['local_bounds'],dimensions=[c['width'],c['height']],blender_uv='u=(E-west)/(east-west),v=(N-south)/(north-south)',kn5_uv='u,1-v',texture=t['artifact'],material=t['name'],nodes=[s['name'] for s in m['meshes'] if s['material']==t['material']],source_mask=dict(path=c['mask_path'],sha256=c['mask_sha256'])))
    m['landscape']['uv_tables']=uv_tables;m['landscape']['actual_dds_coordinate_rgb_controls']=182
    proof_files=('top_extraction.json','contact_skin.npz','repaired_skin.npz','repair_report.json','v002_reference.npz','forest_grounding.npz','ground_diagnostics.json','ground_audit.json','ortho_controls.json','posts.json','prepare.log','repair.log','blender_build.log','ground_audit.log','validation.log','tests.log')
    m['outputs'] += [record(OUT/s) for s in proof_files]
    m['builders']=[record(ROOT/'scripts'/s) for s in ('build_full_track_v003.py','full_track_v003_geometry.py','full_track_v003_repair.py','full_track_v003_kn5.py','audit_full_track_v003.py','full_track_v002_export.py','validate_kn5.py')]+[record(ROOT/'tests/test_full_track_v003.py')]
    m['package_plan']=dict(ready_for_separate_offline_package=True,track_id=TRACK,kn5=record(KN5),package_artifacts=[record(KN5)],helpers=m['helpers'],surface_keys=list(m['surfaces']),explicit_allowlist_required=True,never_glob_failed_attempts=True,embedded_textures=True,install_default='DRY_RUN; deployment/game launch require separate explicit authorization',numeric_acceptance=dict(max_nodes=4096,max_materials=128,max_textures=128,max_file_bytes=256*1024*1024,max_texture_bytes=8*1024*1024,max_vertices_per_mesh=65535,min_ground_altitude_m=.001,max_xy_aspect_ratio=1000,max_reachable_slope=.301,ground_role='open upward top only',wall_role='inward open nonrenderable shell',flags_are_role_specific=True),runtime_gates=['Low-speed wheel/body contact on both walls incl audited v002 gap/burial chainages','Shoulder/apron recovery and chunk seams; no launches','Endpoint braking, settling, restart and A2B timing','Full-route drive and terrain/texture/LOD inspection','Performance and Quest2 VR'])
    m['source_preservation']['checked_after_finalization_files']=unchanged();m['status']='PASS_OFFLINE_V003_NOT_GAME_VALIDATED'
    (OUT/'manifest.json').write_text(json.dumps(m,indent=2,allow_nan=False)+'\n');print('FINALIZED',m['tests']['passed'],'tests; explicit package allowlist; no deployment',flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__);group=ap.add_mutually_exclusive_group(required=True)
    for flag in ('prepare','build','validate','check','finalize'):group.add_argument('--'+flag,action='store_true')
    args=ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.prepare:prepare()
    elif args.build:build()
    elif args.finalize:finalize()
    elif args.check:validate(persist=False)
    else:validate()
if __name__=='__main__':main()
