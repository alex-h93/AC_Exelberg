"""Blender preview renders of v004 + v006 scenery (opens v004 blend read-only, appends roadside objects;
never saves). Preview-only node materials approximate the AC shaders.
Output: data/processed/scenery_v006/previews/<label>.png
Args after '--': label:chainage[:side_offset[:look_ahead[:yaw_deg]]] ...
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector, Euler

ROOT = Path('/var/home/haze/dev/Assetto_Exelberg')
sys.path.insert(0, str(ROOT / 'scripts'))
_SRC = (ROOT / "scripts/render_full_track_v004_previews.py").read_text().split("\ndef main")[0]
exec(compile("\n".join(l for l in _SRC.splitlines() if not l.startswith("STATIONS")), "v4prev", "exec"))
OUT5 = ROOT / 'data/processed/scenery_v006/previews'
T5 = ROOT / 'data/processed/textures_v006/previews'
SHOTS = [a for a in (sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])]


def run():
    import build_full_track_v002 as V2
    V2.import_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND), load_ui=False, use_scripts=False)
    with bpy.data.libraries.load(str(ROOT / 'blender/exelberg_v006_scenery.blend')) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith('V006_')]
    coll = bpy.data.collections.new('V006_PREVIEW'); bpy.context.scene.collection.children.link(coll)
    for o in dst.objects:
        coll.objects.link(o)
    node_mat(bpy.data.materials['V004_foliage'], TEX / 'foliage.png', alpha=True)
    node_mat(bpy.data.materials['V004_impostor'], TEX / 'impostors.png', alpha=True)
    node_mat(bpy.data.materials['V004_bark'], TEX / 'bark.png')
    for mat in bpy.data.materials:
        if mat.name.startswith('V004_ortho_'):
            k = mat.name.split('_')[-1]
            node_mat(mat, ROOT / f'data/processed/landscape_orthos_v003/chunk_{k}.png', detail=TEX / 'grass_detail.png',
                     mult=mat.assettoCorsa.get_property('detailUVMultiplier'))
    for name, png, alpha in (('V005_atlas', 'signs', True), ('V005_metal', 'signs', False), ('V005_asphalt', 'asphalt', False),
                             ('V005_gravel', 'gravel', False), ('V005_foliage', 'foliage', True), ('V005_bark', 'bark', False),
                             ('V005_facade_white', 'facade_white', False), ('V005_facade_cream', 'facade_cream', False),
                             ('V005_facade_ochre', 'facade_ochre', False), ('V005_facade_plain', 'facade_plain', False),
                             ('V005_roof_red', 'roof_red', False), ('V005_roof_dark', 'roof_dark', False)):
        name = name.replace('V005_', 'V006_')
        if name in bpy.data.materials:
            node_mat(bpy.data.materials[name], T5 / f'{png}.png', alpha=alpha)
    if 'REFERENCE_ONLY_EXCLUDED' in bpy.data.collections:
        bpy.data.collections['REFERENCE_ONLY_EXCLUDED'].hide_render = True
    p = np.load(ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz')['designed_xyz_m']
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 16; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    cam_data = bpy.data.cameras.new('V006_PREVIEW'); cam_data.lens = 22; cam_data.clip_end = 6000
    cam = bpy.data.objects.new('V006_PREVIEW', cam_data); sc.collection.objects.link(cam); sc.camera = cam
    OUT5.mkdir(parents=True, exist_ok=True)
    for shot in SHOTS:
        parts = shot.split(':'); label = parts[0]; st = float(parts[1])
        off = float(parts[2]) if len(parts) > 2 else -1.5
        ahead = float(parts[3]) if len(parts) > 3 else 40.0
        yaw = float(parts[4]) if len(parts) > 4 else 0.0
        pitch = float(parts[5]) if len(parts) > 5 else 0.0
        height = float(parts[6]) if len(parts) > 6 else 1.2
        i = int(np.searchsorted(s, st)); j = int(np.searchsorted(s, st + ahead))
        f = p[j, :2] - p[i, :2]; f /= np.linalg.norm(f); left = np.array([-f[1], f[0]])
        pos = p[i].copy(); pos[:2] += left * off; pos[2] += height
        tgt = p[min(j, len(p) - 1)].copy(); tgt[:2] += left * off; tgt[2] += 1.0 + (ahead > 200) * 30
        cam.location = Vector(pos.tolist())
        rot = (Vector(tgt.tolist()) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        rot.z += math.radians(yaw)
        rot.x += math.radians(pitch)
        cam.rotation_euler = rot
        sc.render.filepath = str(OUT5 / f'{label}.png')
        bpy.ops.render.render(write_still=True)
        print('RENDERED', label, flush=True)


run()
