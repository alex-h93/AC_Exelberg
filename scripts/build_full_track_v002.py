#!/usr/bin/env python3
"""Full OFFLINE v002. --prepare in .venv, --build in factory-headless Blender,
--validate in .venv; --check repeats read-only checks; --finalize seals evidence.
Refuses existing blend/KN5. No network/install/game/GUI IO.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import full_track_v002_geometry as G
from export_kn5_prototype import verify_install, sha256, COMMIT
from build_ac_test_scene import station, timing_frames
from prototype_geometry import ribbon, station_normals, require
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/processed/full_track_scene_v002'
EXPORT=ROOT/'exports/full_track_v002'
BLEND=ROOT/'blender/exelberg_full_v002.blend'
TRACK='exelberg_full_v002'
KN5=EXPORT/(TRACK+'.kn5')
INPUT=ROOT/'data/processed/full_track_inputs'
FOREST=ROOT/'data/processed/full_scenery_v003'
COLLECTIONS=('PHYS_ROAD','PHYS_GRAVEL','PHYS_GRASS','PHYS_WALL','VIS_MARKINGS','VIS_FOREST','VIS_WARNINGS','AC_HELPERS')
MATERIALS=('asphalt','gravel','grass','bark','canopy','white','safety')
SPAWNS=('AC_PIT_0','AC_START_0','AC_HOTLAP_START_0')
TIMING=('AC_TIME_0_L','AC_TIME_0_R')


def record(path):
    return dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha256(path))


def dump(path,data):
    with path.open('x') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n')


def verified(rec):
    path=(ROOT/rec['path']).resolve()
    require(path.is_relative_to(ROOT) and record(path)==rec,'Input artifact changed: '+str(path))
    return path


def load_inputs():
    manifest=json.loads((INPUT/'manifest.json').read_text())
    forest=json.loads((FOREST/'manifest.json').read_text())
    require(manifest['schema']=='assetto-exelberg.full-track-inputs' and manifest['version']==1,'Input schema')
    require(manifest['coordinates']['origin_m']==[589500,5346800,300],'Origin')
    for rec in manifest['provenance']['inputs']:verified({k:rec[k] for k in ('path','bytes','sha256')})
    arrays=[]
    for key in ('route','lateral','terrain'):
        rec=manifest['outputs'][key];verified({k:rec[k] for k in ('path','bytes','sha256')})
        with np.load(ROOT/rec['path'],allow_pickle=False) as f:
            data={k:f[k] for k in f.files}
        for k,v in data.items():
            spec=rec['arrays'][k]
            require(list(v.shape)==spec['shape'] and str(v.dtype)==spec['dtype'] and np.isfinite(v).all(),'Array schema '+key+'/'+k)
        arrays.append(data)
    # The forest producer pins every source and exact NPZ; validate its whole manifest artifact graph.
    def walk(item):
        if isinstance(item,dict):
            if all(k in item for k in ('path','bytes','sha256')):verified({k:item[k] for k in ('path','bytes','sha256')})
            for value in item.values():walk(value)
        elif isinstance(item,list):
            for value in item:walk(value)
    walk(forest)
    with np.load(FOREST/'forest_trees.npz',allow_pickle=False) as f:trees={k:f[k] for k in f.files}
    r,l,t=arrays
    require(r['valid'].all() and l['valid'].all() and len(trees['valid'])==4616 and trees['valid'].all(),'Required full inputs invalid')
    require(np.isclose(r['chainage_3035_m'][-1],15226.291863325048),'Full route extent')
    from prototype_geometry import valid_terrain_faces
    valid_terrain_faces(t['valid'],t['valid_cells'])
    return r,l,t,trees


def preservation():
    """Snapshot originals + live install/preferences read-only, no GUI bridge."""
    paths=set()
    for directory in ('data/raw','data/interim','data/processed','blender','exports','tools/vendor/kn5_studio'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file() and not p.is_relative_to(OUT) and not p.is_relative_to(EXPORT) and p!=BLEND and '__pycache__' not in p.parts:paths.add(p)
    previous=json.loads((ROOT/'data/processed/ac_test_scene/manifest.json').read_text())
    paths.update(Path(p) for p in previous['source_preservation']['hashes_before'] if Path(p).is_file())
    # User-owned installed candidate; read-only file hash snapshot, not a deployment.
    installation=ROOT/'data/processed/ac_package/installation.json'
    if installation.exists():
        data=json.loads(installation.read_text())
        # Find existing game track dirs only from recorded destination paths.
        def scan(v):
            if isinstance(v,dict):
                for x in v.values():scan(x)
            elif isinstance(v,list):
                for x in v:scan(x)
            elif isinstance(v,str) and v.startswith('/'):
                p=Path(v)
                if p.is_dir() and p.name=='exelberg_north_proto_v001':paths.update(x for x in p.rglob('*') if x.is_file())
                elif p.is_file() and 'exelberg_north_proto_v001' in p.parts:paths.add(p)
        scan(data)
    paths.discard(ROOT/'scripts/validate_kn5.py') # Explicitly authorized optional parser-limit edit, not a geographic/game source.
    return {str(p):sha256(p) for p in sorted(paths)}


def sample_visible(anchors,t,v,f,cell_ids):
    """Ground anchors on the actual derived, clipped terrain triangles, not raw DTM."""
    groups={}
    for j,k in enumerate(cell_ids):groups.setdefault(int(k),[]).append(j)
    heights=[]
    for p in anchors:
        c=int(np.floor((p[0]-t['x_m'][0,0])/8));r=int(np.floor((p[1]-t['y_m'][0,0])/8))
        found=[]
        for j in groups.get(r*t['valid_cells'].shape[1]+c,()):
            tri=v[f[j]];a,b=tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2];d=p[:2]-tri[0,:2]
            det=a[0]*b[1]-a[1]*b[0]
            u=(d[0]*b[1]-d[1]*b[0])/det;w=(a[0]*d[1]-a[1]*d[0])/det
            if u>=-1e-7 and w>=-1e-7 and u+w<=1+1e-7:found.append((1-u-w)*tri[0,2]+u*tri[1,2]+w*tri[2,2])
        require(found,'Forest anchor missing visible terrain')
        heights.append(max(found))
    result=anchors.copy();result[:,2]=heights
    return result


def corrected_spawn(point,forward):
    """180 degrees relative to v001. KN5 row +Z must now follow route travel."""
    fx,fy=forward;x,y,z=point
    b=[[-fy,-fx,0,x],[fx,-fy,0,y],[0,0,1,z],[0,0,0,1]]
    k=[-fy,0,-fx,0,0,1,0,0,fx,0,-fy,0,x,z,-y,1]
    return b,k


def helpers(p,r):
    total=np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1).sum();n=station_normals(p);out=[]
    for name,distance,offset in [(x,25.,-1.5) for x in SPAWNS]+[(TIMING[0],total-300.,3.),(TIMING[1],total-300.,-3.)]:
        st=station(p,distance);i=st['index'];w=st['fraction'];point=np.array(st['point'])
        point[:2]+=offset*((1-w)*n[i]+w*n[i+1]);point[2]+=.4
        b,k=corrected_spawn(point,st['forward_xy']) if name in SPAWNS else timing_frames(point)
        out.append(dict(name=name,station=st,chainage_3035_m=float((1-w)*r['chainage_3035_m'][i]+w*r['chainage_3035_m'][i+1]),
            lateral_offset_left_m=offset,clearance_m=.4,blender_matrix_rows=b,kn5_expected=k,
            orientation='Blender -Y forward; KN5 +Z forward along travel (v001 actual user feedback yaw +180)' if name in SPAWNS else 'Observed stock Trento TIME_0 fixed axes'))
    return out


def prepare():
    require(not BLEND.exists(),'Fresh blend required')
    for directory in (OUT,EXPORT):
        require(not directory.exists() or all(x.is_dir() and x.name.startswith('failed_attempt_') for x in directory.iterdir()),'Fresh outputs required')
    install=verify_install();before=preservation()
    OUT.mkdir(exist_ok=True);(OUT/'meshes').mkdir();EXPORT.mkdir(exist_ok=True)
    dump(OUT/'source_hashes_before.json',before)
    r,l,t,trees=load_inputs();print('INPUTS VERIFIED',flush=True)
    p,design=G.design_route(r);print('ROUTE DESIGNED',design['profile'],flush=True)
    tv,tf,tz,cell_ids,seam,terrain_report=G.terrain_design(t,r,l,p)
    print('TERRAIN JOINED',len(tv),len(tf),terrain_report,flush=True)
    np.savez_compressed(OUT/'geometry_audit.npz',raw_xyz_m=r['local_xyz_m'],designed_xyz_m=p,
        chainage_3035_m=r['chainage_3035_m'],raw_grid_z_m=t['z_m'],derived_grid_z_m=tz,
        terrain_delta_m=tz-t['z_m'],terrain_valid=t['valid'],terrain_valid_cells=t['valid_cells'],
        clipped_terrain_xyz_m=tv,clipped_terrain_triangles=tf,terrain_triangle_source_cell=cell_ids,shoulder_seam=seam)
    records=[]
    def mesh(name,v,f,uv,material,collection,surface=None,lod=0,closed=False):
        require(len(f)>0 and np.isfinite(v).all() and np.isfinite(uv).all(),'Invalid mesh')
        corner_uv=uv[f].copy()
        tri=v[f];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);axis=np.argmax(abs(cross),axis=1)
        # Vertex UVs alone collapse on vertical slab sides: use explicit per-corner projections there.
        for dominant,axes in [(0,[1,2]),(1,[0,2])]:
            ids=np.flatnonzero(axis==dominant)
            corner_uv[ids]=tri[ids][:,:,axes]/3.
        path=OUT/'meshes'/(name+'.npz');np.savez_compressed(path,vertices=v.astype(np.float32),triangles=f.astype(np.int32),uv=uv.astype(np.float32),corner_uv=corner_uv.astype(np.float32))
        records.append(dict(name=name,artifact=record(path),vertices=len(v),triangles=len(f),material=material,
            collection=collection,surface_key=surface,collision=surface is not None,lod_out_m=lod,closed=closed))
    def solid_chunks(prefix,v,f,material,collection,surface,thickness,size=256):
        for j,(_,vv,ff,_) in enumerate(G.chunks(v,f,v[:,:2]/6,size)):
            vv=vv.astype(np.float32).astype(float)
            vv,ff=G.closed_slab(vv,ff,thickness);vv=vv.astype(np.float32).astype(float);G.solid_checks(vv,ff)
            mesh(prefix+f'_{j:03d}',vv,ff,vv[:,:2]/6,material,collection,surface,closed=True)
    v,f=ribbon(p,[-3.,0.,3.]);solid_chunks('1ROAD',v,f,'asphalt','PHYS_ROAD','ROAD',.3)
    # Side shoulder boundary incorporates every clipped terrain seam point (no geometric seam gap).
    roadedge,_=ribbon(p,[-3.75,3.75]);roadedge=roadedge.reshape(-1,2,3)
    for side in (-1,1):
        sideid=0 if side<0 else 1;verts=[];faces=[]
        inner=p.copy();inner[:,:2]+=station_normals(p)*side*3.
        outer=roadedge[:,sideid]
        for i in range(len(p)-1):
            eid=i+sideid*(len(p)-1);rows=seam[seam[:,1]==eid]
            ts=np.unique(np.r_[0.,rows[:,2],1.]);ts=ts[(ts>=0)&(ts<=1)]
            boundary=np.vstack([inner[i],inner[i+1],outer[i+1],outer[i]+ts[::-1,None]*(outer[i+1]-outer[i])])
            # Quantize before fan construction: multiple terrain cuts can become the same float32 point.
            boundary=boundary.astype(np.float32).astype(float)
            boundary=boundary[np.linalg.norm(boundary[:,:2]-np.roll(boundary[:,:2],1,axis=0),axis=1)>1e-5]
            cross=np.cross(boundary[1]-boundary[0],boundary[2]-boundary[1])[2]
            if cross<0:boundary=boundary[::-1]
            center=boundary.mean(0);start=len(verts);verts.extend(boundary);verts.append(center)
            for j in range(len(boundary)):faces.append([start+j,start+(j+1)%len(boundary),start+len(boundary)])
        vv=np.asarray(verts,dtype=np.float32).astype(float);ff=np.asarray(faces)
        # Weld shared float32 cross-sections before solid extrusion.
        _,idx,inv=np.unique(vv,axis=0,return_index=True,return_inverse=True);vv=vv[idx];ff=inv[ff]
        solid_chunks('1GRAVEL_'+('R' if side<0 else 'L'),vv,ff,'gravel','PHYS_GRAVEL','GRAVEL',.3)
    solid_chunks('1GRASS_TERRAIN',tv,tf,'grass','PHYS_GRASS','GRASS',1.,size=512)
    for side in (-1,1):
        vv,ff=G.wall(p,side)
        # Build physical wall in station chunks before closure to retain genuine closed shells.
        offsets=sorted([side*4.05,side*4.35]);v0,f0=ribbon(p,offsets);v0[:,2]+=1.15
        solid_chunks('1WALL_'+('R' if side<0 else 'L'),v0,f0,'safety','PHYS_WALL','WALL',1.3)
    # Closed endcaps at actual source endpoints; do not extend real alignment.
    normals=station_normals(p)
    for label,i,sign in [('START',0,1),('END',len(p)-1,-1)]:
        n=normals[i];forward=np.array([n[1],-n[0]])
        center=p[i].copy();center[:2]+=forward*sign*.15
        a=center.copy();b=center.copy();a[:2]-=n*4.35;b[:2]+=n*4.35
        q=np.array([a,b,b,a]);q[2:,:2]+=forward*sign*.3
        if np.cross(q[1]-q[0],q[2]-q[0])[2]<0:q=q[::-1]
        q[:,2]+=1.15;ff=np.array([[0,1,2],[0,2,3]])
        vv,ff=G.closed_slab(q,ff,1.3);G.solid_checks(vv,ff)
        mesh('1WALL_'+label,vv,ff,vv[:,:2]/2,'safety','PHYS_WALL','WALL',closed=True)
    # Provisional white paint: 3m dash / 9m gap, 0.12m wide; edge lines at +/-2.9m.
    markv=[];markf=[];marks=0
    def paint(points,offsets):
        nonlocal marks
        vv,ff=ribbon(points,offsets);vv[:,2]+=.012;markf.extend((ff+len(markv)).tolist());markv.extend(vv);marks+=1
    paint(p,[-2.97,-2.85]);paint(p,[2.85,2.97])
    s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
    for start in np.arange(0,s[-1],12):
        end=min(start+3,s[-1]);ss=np.r_[start,s[(s>start)&(s<end)],end]
        pp=np.column_stack([np.interp(ss,s,p[:,k]) for k in range(3)]);paint(pp,[-.06,.06])
    vv=np.array(markv);ff=np.array(markf)
    for j,(_,a,b,uv) in enumerate(G.chunks(vv,ff,vv[:,:2]/2)):
        mesh('VIS_PAINT_'+f'{j:03d}',a,b,uv,'white','VIS_MARKINGS')
    anchors=sample_visible(trees['local_xyz_m'],t,tv,tf,cell_ids)
    np.savez_compressed(OUT/'forest_grounding.npz',source_anchor_index=trees['source_anchor_index'],
        raw_xyz_m=trees['local_xyz_m'],visible_terrain_xyz_m=anchors,
        z_delta_m=anchors[:,2]-trees['local_xyz_m'][:,2])
    for (vv,ff),material in zip(G.tree_geometry(anchors),('bark','canopy')):
        # UVs in metres: bark runs vertically; canopy uses varied world-projected image texture.
        uv=np.column_stack([vv[:,0]/3.,vv[:,2]/3.]) if material=='bark' else vv[:,:2]/8.
        # Assign whole trees to one spatial cluster: never split one crown between cells.
        per_tree_faces=20 if material=='bark' else 32
        treekeys=np.floor(anchors[:,:2]/128).astype(int);keys,inv=np.unique(treekeys,axis=0,return_inverse=True)
        for j,key in enumerate(keys):
            tids=np.flatnonzero(inv==j);ids=(tids[:,None]*per_tree_faces+np.arange(per_tree_faces)).ravel()
            f0=ff[ids];used,local=np.unique(f0,return_inverse=True)
            mesh('VIS_FOREST_'+material.upper()+f'_{j:03d}',vv[used],local.reshape(-1,3),uv[used],material,'VIS_FOREST',lod=900)
    helper=helpers(p,r)
    surfaces={key:dict(objects=[m['name'] for m in records if m['surface_key']==key],friction=fric,
        is_valid_track=int(key=='ROAD'),is_pitlane=0) for key,fric in [('ROAD',1.),('GRAVEL',.7),('GRASS',.6),('WALL',.6)]}
    manifest=dict(schema='assetto-exelberg.full-track-scene',version=2,track_id=TRACK,status='PREPARED_NOT_EXPORTED',
        inputs=[record(INPUT/'manifest.json'),record(FOREST/'manifest.json')]+[record(INPUT/(x+'.npz')) for x in ('route','lateral','terrain')]+[record(FOREST/'forest_trees.npz')],
        builders=[record(Path(__file__)),record(ROOT/'scripts/full_track_v002_geometry.py')],
        coordinates=dict(origin_m=[589500,5346800,300],horizontal_epsg=25833,vertical_epsg=9274,
            blender='X east,Y north,Z up',kn5='(X,Y,Z)->(X,Z,-Y)',units='metres'),
        route=dict(chainage_3035_m=[0,float(r['chainage_3035_m'][-1])],source_native_length_m=float(r['chainage_25833_m'][-1]),
            designed_road_length_m=float(s[-1]),width_m=6,lanes=2,lane_width_m=3,crossfall=0,shoulders_each_m=.75,
            width_paint_camber_provisional=True,endpoint_extension_m=0),
        design=design,terrain=terrain_report,meshes=records,export_collections=list(COLLECTIONS),helpers=helper,surfaces=surfaces,
        forest=dict(count=len(anchors),source='full_scenery_v003 actual OSM mask over synthetic anchors; not measured trees/species',
            chunks=sum(m['collection']=='VIS_FOREST' for m in records),opaque=True,grounding_delta_m=G.stats(anchors[:,2]-trees['local_xyz_m'][:,2]),
            lod_out_m=900,cluster_grid_m=128),
        paint=dict(provisional_not_measured=True,center_dash_m=3,center_gap_m=9,width_m=.12),
        barriers=dict(temporary_not_real_road_claim=True,height_above_road_m=1.15,inner_offset_left_m=[-4.05,4.05],
            thickness_m=.3,closed_endcaps=True,normal_driving_containment_only=True,high_speed_fallproof=False),
        timing_contract=dict(fixture='stock Trento A2B TIME_0_L/R finish only',start='solo spawn at designed arclength 25m',
            road_length_m=float(s[-1]),finish_gate_arclength_m=float(s[-1]-300),timed_course_from_spawn_m=float(s[-1]-325),
            finish_runout_to_source_endpoint_m=300,endcap_inset_m=.3,runtime_verified=False,
            warnings_before_road_end_m=[300,150,60],session_workflow='UNVERIFIED; package next, do not assume closed-circuit hotlap'),
        spawn_contract=dict(station_m=25,right_lane_offset_left_m=-1.5,height_clearance_m=.4,yaw_change_from_v001_degrees=180,
            kn5_forward='+Z',blender_forward='-Y',solo_coincident_markers=True,runtime_verified=False),
        source_preservation=dict(before=record(OUT/'source_hashes_before.json'),protected_files=len(before),verified=False),
        addon=dict(commit=COMMIT,installed_dir=str(install),source_modified=False,auto_fix=False),
        runtime=dict(ac_tested=False,game_deployed=False,gui_accessed=False,preferences_saved=False),outputs=[])
    dump(OUT/'prepared.json',manifest)
    print('PREPARED',len(records),'meshes',sum(m['triangles'] for m in records),'triangles',flush=True)


def texture_pixels(name,size=256):
    seed=MATERIALS.index(name)+207;rng=np.random.default_rng(seed);y,x=np.mgrid[:size,:size]
    noise=rng.normal(0,1,(size,size));coarse=np.repeat(np.repeat(rng.normal(0,1,(16,16)),size//16,0),size//16,1)
    base={'asphalt':[.17,.18,.19],'gravel':[.44,.40,.32],'grass':[.21,.31,.12],
          'bark':[.30,.20,.12],'canopy':[.16,.32,.09],'white':[.91,.91,.84],'safety':[.92,.59,.04]}[name]
    if name=='asphalt': pattern=noise*.025+coarse*.009+(np.sin(x*.61)*np.sin(y*.73))*.006
    elif name=='gravel':pattern=noise*.065+coarse*.04
    elif name=='grass':pattern=noise*.04+coarse*.05+np.sin(x*.5+y*.15)*.018
    elif name=='bark':pattern=noise*.025+(np.sin(x*.25+np.sin(y*.035))*np.sin(x*.75))*.11
    elif name=='canopy':pattern=noise*.045+coarse*.06+np.sin(x*.3)*np.sin(y*.37)*.035
    elif name=='white':pattern=noise*.012
    else:
        a=np.zeros((size,size,4),dtype=np.float32);hazard=((x+y)//32)%2==0
        a[:,:,:3]=np.where(hazard[:,:,None],np.array(base),np.array([.07,.065,.045]));a[:,:,3]=1;return a
    a=np.empty((size,size,4),dtype=np.float32);a[:,:,:3]=np.clip(np.array(base)+pattern[:,:,None],.02,.98);a[:,:,3]=1
    return a


def import_addon():
    install=verify_install()
    spec=importlib.util.spec_from_file_location('kn5_studio',install/'__init__.py',submodule_search_locations=[str(install)])
    addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
    return addon


def source_match():
    before=json.loads((OUT/'source_hashes_before.json').read_text())
    # Older failed/prepared snapshots may include this explicitly authorized parser file.
    before.pop(str(ROOT/'scripts/validate_kn5.py'),None)
    changed=[p for p,h in before.items() if sha256(p)!=h]
    require(not changed,'Protected original changed: '+str(changed));verify_install()
    return len(before)


def build():
    import bpy
    from mathutils import Matrix,Vector
    require(bpy.app.background and not bpy.data.filepath,'Factory-headless only')
    require(not BLEND.exists() and not KN5.exists(),'Refuse existing scene/export')
    start=time.monotonic();manifest=json.loads((OUT/'prepared.json').read_text());source_match()
    # Python-side no network/game/prefs writes. Native Blender saves only fresh named outputs.
    def audit(event,args):
        if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'):raise PermissionError(event)
        if event=='open':
            p,mode,flags=args;writing=(mode and any(c in mode for c in 'wax+')) or (flags and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing and not isinstance(p,int):
                path=Path(p).resolve()
                require(path.is_relative_to(OUT) or path.is_relative_to(EXPORT),'Blocked write: '+str(path))
    sys.addaudithook(audit)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections):bpy.data.collections.remove(c)
    collections={}
    for name in (*COLLECTIONS,'PREVIEW_ONLY_EXCLUDED'):
        c=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(c);collections[name]=c
    addon=import_addon();materials={};textures=[]
    for name in MATERIALS:
        pixels=texture_pixels(name);image=bpy.data.images.new('v002_'+name,width=256,height=256,alpha=True)
        image.pixels.foreach_set(pixels.ravel());image.update()
        payload=addon.dds.image_to_bgra_dds(image);path=EXPORT/('v002_'+name+'.dds')
        with path.open('xb') as f:f.write(payload)
        image.filepath_raw=str(path);image.pack()
        mat=bpy.data.materials.new('V002_'+name);ac=mat.assettoCorsa;ac.preset_selector='NONE';ac.shader_name='ksPerPixel';ac.blend_mode='0';ac.depth_mode='0';ac.alpha_tested=False
        for key,value in dict(ksAmbient=.45,ksDiffuse=.65,ksSpecular=.12 if name=='asphalt' else .03,ksSpecularEXP=12.).items():ac.set_property(key,value)
        ac.ensure_default_slots_for_shader('ksPerPixel');ac.texture_slots[0].image=image;ac.texture_slots[0].override_filename=path.name
        addon.materials.sync_material_nodes(mat);materials[name]=mat;textures.append(record(path))
    objects=[];source_counts={};expected_paths={}
    def create(name,v,f,uv,corner_uv,material,collection,lod=0):
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update()
        layer=mesh.uv_layers.new(name='UVMap');corners=np.array([l.vertex_index for l in mesh.loops])
        layer.data.foreach_set('uv',corner_uv.astype(np.float32).ravel())
        # Smooth image-shaded surfaces; physical winding remains exactly explicit.
        mesh.polygons.foreach_set('use_smooth',np.full(len(mesh.polygons),collection not in ('PHYS_WALL','PHYS_GRAVEL','PHYS_GRASS'),dtype=bool))
        mesh.materials.append(materials[material]);obj=bpy.data.objects.new(name,mesh);collections[collection].objects.link(obj)
        ac=obj.assettoCorsa;ac.visible=ac.renderable=ac.cast_shadows=True;ac.transparent=False;ac.layer=0;ac.lod_in=0;ac.lod_out=lod
        obj['provisional_not_surveyed']=True;obj['export_role']=collection;obj['collision_intended']=name.startswith('1')
        obj['temporary_safety_geometry']=collection=='PHYS_WALL'
        objects.append(obj);source_counts[name]=len(f);return obj
    for j,m in enumerate(manifest['meshes']):
        path=verified(m['artifact'])
        with np.load(path,allow_pickle=False) as a:v,f,uv,cuv=a['vertices'],a['triangles'],a['uv'],a['corner_uv']
        create(m['name'],v,f,uv,cuv,m['material'],m['collection'],m['lod_out_m']);expected_paths[m['name']]=str(path)
        if j%100==0:print('SCENE',j,'/',len(manifest['meshes']),flush=True)
    for h in manifest['helpers']:
        obj=bpy.data.objects.new(h['name'],None);collections['AC_HELPERS'].objects.link(obj);obj.matrix_world=Matrix(h['blender_matrix_rows']);obj.empty_display_type='ARROWS';objects.append(obj)
    with np.load(OUT/'geometry_audit.npz',allow_pickle=False) as a:p=a['designed_xyz_m']
    length=manifest['route']['designed_road_length_m']
    # Actual mesh warning text, provisional safety aid; not collision, not measured road furniture.
    for distance,label in [(length-300,'BRAKE / FINISH'),(length-150,'BRAKE'),(length-60,'STOP')]:
        st=station(p,distance);pt=np.array(st['point']);fx,fy=st['forward_xy'];pt[:2]+=np.array([-fy,fx])*5.2;pt[2]+=2.
        font=bpy.data.curves.new('warning','FONT');font.body=label;font.size=1.0;font.align_x='CENTER';font.extrude=.012
        obj=bpy.data.objects.new('VIS_WARNING_'+label.replace(' / ','_')+'_'+str(int(distance)),font);collections['VIS_WARNINGS'].objects.link(obj)
        obj.location=pt;obj.rotation_euler=(math.pi/2,0,math.atan2(fy,fx)-math.pi/2)
        bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.convert(target='MESH');obj.select_set(False)
        mesh=obj.data
        import bmesh
        bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.triangulate(bm,faces=bm.faces[:]);bm.to_mesh(mesh);bm.free()
        mesh.calc_loop_triangles();vv=np.array([v.co[:] for v in mesh.vertices]);ff=np.array([t.vertices[:] for t in mesh.loop_triangles]);uv=vv[:,:2]
        layer=mesh.uv_layers.new(name='UVMap');layer.data.foreach_set('uv',uv[np.array([l.vertex_index for l in mesh.loops])].astype(np.float32).ravel())
        mesh.materials.append(materials['white']);ac=obj.assettoCorsa;ac.visible=ac.renderable=ac.cast_shadows=True;ac.transparent=False;ac.lod_out=0
        objects.append(obj);source_counts[obj.name]=len(ff)
        # Capture transformed source for independent oriented-triangle checks.
        vv=np.array([obj.matrix_world@Vector(v) for v in vv],dtype=np.float32)
        # Versioned caller workaround: bake transform to avoid upstream same-name wrapper/mesh dummies.
        mesh.transform(obj.matrix_world);obj.matrix_world=Matrix.Identity(4)
        vv=np.array([v.co[:] for v in mesh.vertices],dtype=np.float32)
        path=OUT/'meshes'/(obj.name+'.npz');np.savez_compressed(path,vertices=vv,triangles=ff.astype(np.int32),uv=uv.astype(np.float32));expected_paths[obj.name]=str(path)
        manifest['meshes'].append(dict(name=obj.name,artifact=record(path),vertices=len(vv),triangles=len(ff),material='white',collection='VIS_WARNINGS',surface_key=None,collision=False,lod_out_m=0,closed=False))
    require(not addon.materials.audit_texture_bindings([o for o in objects if o.type=='MESH'],'EMBEDDED_DDS'),'Texture binding audit')
    print('EXPORT START',len(objects),'objects',flush=True)
    from full_track_v002_export import exporter_class
    exporter=exporter_class(addon)(bpy.context,str(KN5),dict(version=5,texture_mode='EMBEDDED_DDS',target_objects=objects,
        apply_modifiers=False,auto_detect_materials=False,auto_fix_wheels=False,selection_only=False))
    model=exporter.export();require(not exporter.warnings,'Exporter warnings: '+str(exporter.warnings))
    def estimate(node):
        vertex_bytes=(44*len(node.vertices)+2*len(node.indices)) if node.node_type==2 else 64
        return 512+vertex_bytes+sum(estimate(c) for c in node.children)
    require(estimate(model.root_node)+sum(len(t.data) for t in model.textures)+65536<=256*1024*1024,'Generated KN5 256MiB budget')
    require(sum(len(t.data) for t in model.textures)<=8*1024*1024,'Total embedded texture 8MiB budget')
    with KN5.open('xb') as f:model.to_stream(f)
    print('EXPORT WRITTEN',KN5.stat().st_size,flush=True)
    manifest['authorized_parser_change']=record(ROOT/'scripts/validate_kn5.py')
    manifest['builders']=[record(Path(__file__)),record(ROOT/'scripts/full_track_v002_geometry.py'),record(ROOT/'scripts/full_track_v002_export.py')]
    manifest['export_corner_adapter']=dict(artifact=record(ROOT/'scripts/full_track_v002_export.py'),
        reason='Blender 5.2 deprecated loop normals yielded wrong fallback normals/nonorthogonal tangents in the pinned extraction path. Caller-only actual corner/geometric flat-normal adapter; vendor/install unchanged.',
        changes_geometric_triangle_multiset_or_corner_uv=False,uint16_index_buffers_rebuilt=True,
        automatic_operator_fixes=False,meshes=exporter.corner_adapter)
    manifest['attribution']='Terrain © BEV CC BY 4.0; OSM © OpenStreetMap contributors ODbL. Procedural images/tree geometry authored offline in this project.'
    manifest['textures']=textures;manifest['outputs']=[record(KN5)]+textures
    manifest['export_source_triangle_counts']=source_counts
    manifest['export_allowlist']=[o.name for o in objects]
    # Preview cameras/lights are created after the explicit export; never enter the KN5.
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    scene['README']='FULL 0–15.226km source route, two 3m lanes. Provisional offline base, NOT final realism or runtime validation. Temporary walls are safety aids, NOT observed barriers. See docs/validation/FULL_TRACK_V002.md.'
    scene['origin_ENH_m']=[589500,5346800,300]
    text=bpy.data.texts.new('FULL_TRACK_V002_AUTHORING_CONTRACT.json');text.write(json.dumps(manifest,indent=2))
    reference=bpy.data.collections.new('REFERENCE_ONLY_EXCLUDED');scene.collection.children.link(reference);reference.hide_render=True;reference.hide_viewport=True
    with np.load(OUT/'geometry_audit.npz',allow_pickle=False) as audit_data:
        for label,key in [('RAW_OSM_DTM_UNCHANGED','raw_xyz_m'),('DESIGNED_CENTERLINE','designed_xyz_m')]:
            xyz=audit_data[key];curve=bpy.data.curves.new(label,'CURVE');curve.dimensions='3D';spline=curve.splines.new('POLY');spline.points.add(len(xyz)-1)
            spline.points.foreach_set('co',np.column_stack([xyz,np.ones(len(xyz))]).ravel())
            guide=bpy.data.objects.new(label,curve);reference.objects.link(guide)
    manifest['excluded_collections']=['PREVIEW_ONLY_EXCLUDED','REFERENCE_ONLY_EXCLUDED']
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=True
    scene.render.resolution_x=1280;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    scene.world.color=(.33,.38,.48)
    world=scene.world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.48,.60,.8,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.65
    light=bpy.data.lights.new('PREVIEW_SUN','SUN');light.energy=2.5;light.angle=.15
    sun=bpy.data.objects.new('PREVIEW_SUN',light);collections['PREVIEW_ONLY_EXCLUDED'].objects.link(sun);sun.rotation_euler=(.5,-.4,-.3)
    def camera(name,position,target,ortho=None):
        data=bpy.data.cameras.new(name);obj=bpy.data.objects.new(name,data);collections['PREVIEW_ONLY_EXCLUDED'].objects.link(obj)
        obj.location=position;obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler();data.clip_end=30000;data.lens=26
        if ortho:data.type='ORTHO';data.ortho_scale=ortho
        return obj
    center=(p.min(0)+p.max(0))/2
    overview=camera('PREVIEW_OVERVIEW',center+[0,-2500,10000],center,11000)
    st=station(p,2050);pos=np.array(st['point']);f=np.array(st['forward_xy']);pos[:2]+=[f[1]*1.5,-f[0]*1.5];pos[2]+=1.25
    driver=camera('PREVIEW_DRIVER',pos,pos+np.r_[f*50,0])
    previews=[]
    for cam,name in [(overview,'overview'),(driver,'driver')]:
        scene.camera=cam;scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True);previews.append(record(OUT/(name+'.png')))
    scene.camera=driver
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND),check_existing=True,copy=True)
    # Actual isolated saved-file reload and inventory/helper/texture checks.
    bpy.ops.wm.open_mainfile(filepath=str(BLEND),load_ui=False,use_scripts=False)
    for h in manifest['helpers']:require(np.allclose(np.array(bpy.data.objects[h['name']].matrix_world),h['blender_matrix_rows'],atol=.0004,rtol=0),'Saved helper differs')
    require(all(n in bpy.data.objects for n in manifest['export_allowlist']),'Saved inventory')
    manifest['outputs'] += [record(BLEND)]+previews
    manifest['source_preservation']['verified']=True;manifest['source_preservation']['checked_after_files']=source_match()
    manifest['runtime'].update(blender=bpy.app.version_string,blender_background=True,elapsed_seconds=time.monotonic()-start,
        actual_cpu_previews=2,samples=8,resolution=[1280,800],saved_copy_reloaded=True)
    manifest['status']='EXPORTED_PENDING_INDEPENDENT_VALIDATION'
    dump(OUT/'exported.json',manifest)
    print('BLENDER BUILD PASS',time.monotonic()-start,flush=True)


def collision_join_checks(manifest):
    with np.load(OUT/'geometry_audit.npz',allow_pickle=False) as a:
        p=a['designed_xyz_m'];raw=a['raw_xyz_m'];tv=a['clipped_terrain_xyz_m'];seam=a['shoulder_seam']
    with np.load(INPUT/'route.npz',allow_pickle=False) as a:
        require(np.array_equal(raw,a['local_xyz_m']),'Audit raw route differs from source')
    edge,_=ribbon(p,[-3.75,3.75]);edge=edge.reshape(-1,2,3)
    a=np.concatenate([edge[:-1,0],edge[:-1,1],edge[0:1,0],edge[-1:,0]])
    b=np.concatenate([edge[1:,0],edge[1:,1],edge[0:1,1],edge[-1:,1]])
    ids=seam[:,1].astype(int);fraction=seam[:,2,None]
    target=(a[ids]+fraction*(b[ids]-a[ids])).astype(np.float32).astype(float)
    actual=tv[seam[:,0].astype(int)].astype(np.float32).astype(float)
    max_gap=float(np.linalg.norm(actual-target,axis=1).max())
    require(max_gap<.001,'Terrain/shoulder collision seam exceeds 1mm float32 tolerance')
    shoulder_vertices=[]
    for m in manifest['meshes']:
        if m['surface_key']=='GRAVEL':
            with np.load(verified(m['artifact']),allow_pickle=False) as a:shoulder_vertices.append(a['vertices'])
    shoulder=np.concatenate(shoulder_vertices).astype('<f4')
    keys=set(shoulder.view('V12').ravel().tolist())
    n=station_normals(p);missing=0
    for side in (-1,1):
        expected=p.copy();expected[:,:2]+=n*side*3.
        missing+=sum(k not in keys for k in expected.astype('<f4').view('V12').ravel().tolist())
    require(missing==0,'Road/shoulder endpoint collision gap')
    wallv,wallf=ribbon(p,[-4.35,4.35]);wallcheck=G.mesh_checks(wallv,wallf)
    require(wallcheck['non_upward_triangles']==wallcheck['degenerate_triangles']==0,'Folded barrier envelope')
    walloverlap=G.ribbon_overlap(p,4.35);require(not walloverlap,'Barrier envelope nonadjacent overlap')
    return dict(barrier_envelope_folds=0,barrier_envelope_nonadjacent_overlaps=walloverlap,
        road_to_shoulder_shared_station_vertices=2*len(p),missing_road_shoulder_vertices=missing,
        terrain_shoulder_points=len(seam),max_terrain_shoulder_float32_gap_m=max_gap,
        tolerance_m=.001,terrain_replaced_under_road=True,
        temporary_wall_inner_clear_width_m=8.1,road_and_shoulders_width_m=7.5,
        closed_solids='Every source spatial chunk, as exact triangle union across any uint16 parts',
        numeric_terrain_residue_area_m2=manifest['terrain']['audited_numeric_sliver_area_m2'])


def validate(persist=True):
    from validate_kn5 import parse,bounded_read,compare_corners
    import struct
    path=(OUT/'manifest.json') if not persist else OUT/('captured.json' if (OUT/'captured.json').exists() else 'exported.json')
    manifest=json.loads(path.read_text())
    for rec in manifest['outputs']:verified(rec)
    if 'documentation' in manifest:verified(manifest['documentation'])
    for rec in manifest.get('reproduction_scripts',[]):verified(rec)
    model=parse(bounded_read(KN5,max_file=256*1024*1024),max_file=256*1024*1024,max_nodes=4096,max_texture=8*1024*1024)
    nodes={n['name']:n for n in model['nodes']};groups={m['name']:[] for m in manifest['meshes']};reports=[]
    require(model['root']['name']==TRACK and np.array_equal(model['root']['matrix'],np.eye(4).ravel()),'Root')
    require(len(model['textures'])==len(model['materials'])==7,'Material/texture totals')
    require(sum(len(t['data']) for t in model['textures'])<=8*1024*1024,'Total texture payload 8MiB cap')
    texture_names={t['name'] for t in model['textures']}
    for texture in model['textures']:
        data=texture['data'];require(data[:4]==b'DDS ' and data==(EXPORT/texture['name']).read_bytes(),'Embedded DDS mismatch')
        header=struct.unpack('<31I',data[4:128]);require(header[0]==124 and header[2:4]==(256,256) and len(data)==128+256*256*4,'DDS bounded format')
        pixels=np.frombuffer(data[128:],dtype=np.uint8).reshape(-1,4)
        require(pixels[:,:3].std(0).max()>1 and (pixels[:,3]==255).all(),'Nonopaque/flat DDS')
    by_material={m['name']:m for m in model['materials']}
    for name in MATERIALS:
        m=by_material['V002_'+name];require(m['shader']=='ksPerPixel' and m['blend']==m['alpha']==m['depth']==0,'Material flags')
        require(m['bindings']==[('txDiffuse',0,'v002_'+name+'.dds')],'Explicit texture binding')
    for helper in manifest['helpers']:
        n=nodes[helper['name']];a=n['matrix'];expected=np.array(helper['kn5_expected'])
        require(n['kind']==1 and n['active']==1 and not n['children'] and n['parent']==TRACK,'Helper hierarchy')
        require(np.allclose(a,expected,atol=.0004,rtol=0),'Independent helper transform')
        if helper['name'] in SPAWNS:
            travel=np.r_[helper['station']['forward_xy'][0],0,-helper['station']['forward_xy'][1]]
            require(float(a[8:11]@travel)>.99999,'Actual exported KN5 +Z not aligned with travel')
            helper['actual_kn5_plus_z_dot_travel']=float(a[8:11]@travel)
    specs={m['name']:m for m in manifest['meshes']}
    for n in model['nodes']:
        if n['kind']==1:
            require(n['name']==TRACK or n['name'] in SPAWNS+TIMING or n['name'] in groups,'Unexpected dummy')
            require(n['active']==1,'Inactive dummy')
            if n['name'] not in SPAWNS+TIMING:
                require(np.array_equal(n['matrix'],np.eye(4).ravel()),'Nonidentity root/split wrapper')
                require(n['parent']==(None if n['name']==TRACK else TRACK),'Split wrapper hierarchy')
            continue
        source=n['name'] if n['name'] in groups else n['name'].rsplit('_SUB',1)[0]
        require(source in groups,'Unexpected mesh '+n['name']);groups[source].append(n);spec=specs[source]
        parent=source if source in nodes and nodes[source]['kind']==1 else TRACK
        require(n['parent']==parent and not n['children'],'Mesh hierarchy/transform inheritance')
        v=n['vertices'];f=n['indices'];pos=v[:,:3].astype(float);normal=v[:,3:6].astype(float);tan=v[:,8:].astype(float)
        require(len(v)<=65535 and np.isfinite(v).all(),'Bounded finite vertices')
        require(np.max(abs(np.linalg.norm(normal,axis=1)-1))<2e-5,'Unit normals')
        require(np.max(abs(np.linalg.norm(tan,axis=1)-1))<2e-5 and np.max(abs((normal*tan).sum(1)))<2e-5,'Tangent frames')
        tri=pos[f];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);norm=np.linalg.norm(cross,axis=1)
        require((norm>1e-10).all(),'Export collapsed triangle '+n['name'])
        require((cross*normal[f].mean(1)).sum(1).min()>0,'Normals oppose geometric winding '+n['name'])
        require([n[k] for k in ('active','visible','renderable','cast_shadows','transparent','layer')]==[1,1,1,1,0,0],'Mesh flags')
        require(model['materials'][n['material']]['name']=='V002_'+spec['material'],'Per-node material')
        require(bool(n['name'][0].isdigit())==spec['collision'],'Per-node collision prefix')
        if spec['collision']:require(n['name'].startswith('1'+spec['surface_key']+'_'),'Per-node surface prefix')
        require(np.allclose(n['lod_sphere'][:2],[0,spec['lod_out_m']]),'LOD')
        require(np.linalg.norm(pos-n['lod_sphere'][2:5],axis=1).max()<=n['lod_sphere'][5]+.005,'Mesh sphere')
        reports.append(dict(name=n['name'],source=source,vertices=len(v),triangles=len(f),max_index=int(f.max()),
            collision=spec['collision'],surface_key=spec['surface_key'],material=spec['material'],lod_out_m=spec['lod_out_m']))
    for name,parts in groups.items():
        require(parts,'Missing exported source '+name);spec=specs[name]
        require(sum(len(n['indices']) for n in parts)==spec['triangles'],'Triangle counts across uint16 splits')
        with np.load(verified(spec['artifact']),allow_pickle=False) as a:
            v=a['vertices'];f=a['triangles'];uv=a['corner_uv'].copy() if 'corner_uv' in a else a['uv'][f].copy()
        xyz=v[:,[0,2,1]].copy();xyz[:,2]*=-1;uv[:,:,1]=1-uv[:,:,1]
        expected=np.concatenate([xyz[f],uv],axis=2)
        actual=np.concatenate([n['vertices'][n['indices']][:,:,[0,1,2,6,7]] for n in parts])
        try:compare_corners(expected,actual)
        except ValueError as error:raise ValueError(name+': '+str(error)) from error
        if spec['collision']:G.solid_checks(v.astype(float),f)
    for key,surface in manifest['surfaces'].items():
        surface.setdefault('source_objects',surface['objects'])
        surface['objects']=[m['name'] for m in reports if m['surface_key']==key]
    source_match()
    result=dict(status='PASS_INDEPENDENT_STATIC_ONLY',nodes=len(nodes),mesh_nodes=len(reports),
        triangles=sum(x['triangles'] for x in reports),meshes=reports,texture_count=7,
        max_mesh_vertices=max(x['vertices'] for x in reports),byte_count=model['bytes_consumed'],
        exact_oriented_xyz_uv_multiset_all_splits=True,collision_solids_closed_outward=True,
        collision_joins=collision_join_checks(manifest),
        ac_runtime_tested=False,remaining=['spawn direction/settling','full drive and normal-speed barrier collisions','surface grip',
        'A2B timing/restart/session','textures/LOD/culling in AC','performance/VR'])
    if not persist:
        print('READ-ONLY RECHECK PASS',len(nodes),'nodes',result['triangles'],'triangles; all output/source hashes',flush=True)
        return result
    dump(OUT/'independent_validation.json',result)
    manifest['status']='PASS_OFFLINE_FULL_ROUTE_BASE_NOT_FINAL_REALISM';manifest['static_checks']=result
    manifest['outputs'] += [record(OUT/'independent_validation.json'),record(OUT/'geometry_audit.npz'),record(OUT/'forest_grounding.npz')]
    manifest['source_preservation']['verified']=True;manifest['source_preservation']['checked_after_files']=source_match()
    dump(OUT/'manifest.json',manifest)
    print('INDEPENDENT PASS',len(nodes),'nodes',result['triangles'],'triangles',flush=True)


def finalize():
    import re
    manifest=json.loads((OUT/'manifest.json').read_text())
    require('documentation' not in manifest,'Already finalized')
    doc=ROOT/'docs/validation/FULL_TRACK_V002.md';require(doc.is_file(),'Validation document missing')
    log=(OUT/'tests.log').read_text();match=re.search(r'Ran (\d+) tests in ([0-9.]+)s',log)
    require(match is not None and '\nOK\n' in log and 'FAILED' not in log and 'skipped=' not in log,'Full tests not all passed')
    manifest['tests']=dict(command='PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -q',
        passed=int(match[1]),seconds=float(match[2]),artifact=record(OUT/'tests.log'))
    manifest['documentation']=record(doc)
    adapter=manifest['export_corner_adapter'];adapter.pop('changes_geometry_uv_indices',None)
    adapter['changes_geometric_triangle_multiset_or_corner_uv']=False;adapter['uint16_index_buffers_rebuilt']=True
    manifest['static_checks']=validate(persist=False)
    manifest['reproduction_scripts']=[record(ROOT/'scripts'/name) for name in
        ('build_full_track_v002.py','full_track_v002_geometry.py','full_track_v002_export.py','capture_full_v002_warnings.py','validate_kn5.py')]
    manifest['timing_contract']['usable_runout_to_near_face_of_endcap_m']=299.55
    manifest['timing_contract']['finish_gate_chainage_3035_m']=manifest['helpers'][3]['chainage_3035_m']
    for name in ('prepare.log','blender_build.log','source_capture.log','validation.log','tests.log'):
        manifest['outputs'].append(record(OUT/name))
    manifest['source_preservation']['checked_after_finalization_files']=source_match()
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print('FINALIZED',manifest['tests']['passed'],'tests; raw/live/settings unchanged',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare','build','validate','check','finalize'):group.add_argument('--'+name,action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    if args.prepare:prepare()
    elif args.build:build()
    elif args.check:validate(persist=False)
    elif args.finalize:finalize()
    else:validate()

if __name__=='__main__':main()
