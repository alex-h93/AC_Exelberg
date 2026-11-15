"""Read-only saved-v002 Blender source capture for the three warning text meshes.

Corrects only expected-source evidence from the first successful export: pre-bake
Matrix@Vector prediction differs from Mesh.transform float32 arithmetic for a few
font vertices. Capture actual saved mesh/UVs after explicit triangulation. Never
save or modify the blend/KN5, never import/execute the vendor exporter here.
Future builder performs this explicit triangulation and actual post-bake capture.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import json
import numpy as np
import bpy
import bmesh
from build_full_track_v002 import ROOT,OUT,BLEND,KN5,record,verified,dump,source_match,require
require(bpy.app.background and not bpy.data.filepath,'Factory-headless only')
manifest=json.loads((OUT/'exported.json').read_text())
for rec in manifest['outputs']:verified(rec)
before={str(p):record(p) for p in (BLEND,KN5)}
destination=OUT/'saved_source_capture';require(not destination.exists(),'Refuse existing capture');destination.mkdir()
bpy.ops.wm.open_mainfile(filepath=str(BLEND),load_ui=False,use_scripts=False)
captures=[]
for spec in manifest['meshes']:
    if spec['collection']!='VIS_WARNINGS':continue
    obj=bpy.data.objects[spec['name']];require(obj.type=='MESH','Warning mesh missing')
    require(np.allclose(np.array(obj.matrix_world),np.eye(4),atol=1e-7),'Source warning transform not baked')
    mesh=obj.data.copy()
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.triangulate(bm,faces=bm.faces[:]);bm.to_mesh(mesh);bm.free()
    mesh.calc_loop_triangles();v=np.array([x.co[:] for x in mesh.vertices],dtype=np.float32)
    f=np.array([x.vertices[:] for x in mesh.loop_triangles],dtype=np.int32)
    uv=np.array([[mesh.uv_layers.active.data[i].uv[:] for i in tri.loops] for tri in mesh.loop_triangles],dtype=np.float32)
    require(len(f)==spec['triangles'],'Saved source triangle total differs')
    old=verified(spec['artifact'])
    with np.load(old,allow_pickle=False) as a:oldv=a['vertices']
    # Mesh copy and bmesh retain vertex order for these explicit font meshes.
    require(oldv.shape==v.shape,'Unexpected font vertex inventory')
    delta=np.linalg.norm(v.astype(float)-oldv.astype(float),axis=1)
    require(delta.max()<.001,'Pre-bake font prediction differs by >=1mm')
    path=destination/(obj.name+'.npz');np.savez_compressed(path,vertices=v,triangles=f,corner_uv=uv)
    captures.append(dict(name=obj.name,old_evidence=spec['artifact'],actual_saved_evidence=record(path),
        max_prebake_prediction_error_m=float(delta.max()),changed_predicted_vertices=int(np.count_nonzero(delta)),
        triangles=len(f),blender=bpy.app.version_string))
    spec['artifact']=record(path)
for p in (BLEND,KN5):require(record(p)==before[str(p)],'Source/export unexpectedly changed')
source_match()
dump(destination/'report.json',dict(status='PASS_ACTUAL_SAVED_BLENDER_SOURCE_CAPTURE',source_blend=before[str(BLEND)],
    unchanged_kn5=before[str(KN5)],capture_script=record(Path(__file__)),meshes=captures,saved_blend=False,exporter_imported=False))
manifest['source_capture']=record(destination/'report.json')
manifest['outputs'] += [record(destination/'report.json')]
dump(OUT/'captured.json',manifest)
print('SAVED SOURCE CAPTURE PASS',len(captures),'warnings; no blend/KN5 changes',flush=True)
