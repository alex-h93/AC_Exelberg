"""Blender preview renders of v004 (opens the saved v004 blend; never saves it).

Preview-only node materials approximate the AC shaders (ortho x grass detail,
alpha-clipped foliage). Output: data/processed/full_track_scene_v004/driver_<m>.png
"""
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path('/var/home/haze/dev/Assetto_Exelberg')
BLEND = ROOT / 'blender/exelberg_full_v004.blend'
OUT = ROOT / 'data/processed/full_track_scene_v004'
TEX = ROOT / 'data/processed/textures_v004/previews'
STATIONS = [int(a) for a in (sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['2050', '5200', '9000', '12600'])]


def node_mat(mat, image_path, alpha=False, detail=None, mult=1.0):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.9
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(image_path), check_existing=True)
    color = tex.outputs['Color']
    if detail is not None:
        uv = nt.nodes.new('ShaderNodeTexCoord')
        vm = nt.nodes.new('ShaderNodeVectorMath'); vm.operation = 'SCALE'; vm.inputs['Scale'].default_value = mult
        nt.links.new(uv.outputs['UV'], vm.inputs[0])
        dt = nt.nodes.new('ShaderNodeTexImage'); dt.image = bpy.data.images.load(str(detail), check_existing=True)
        nt.links.new(vm.outputs[0], dt.inputs[0])
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        nt.links.new(tex.outputs['Color'], mix.inputs[6]); nt.links.new(dt.outputs['Color'], mix.inputs[7])
        bright = nt.nodes.new('ShaderNodeMix'); bright.data_type = 'RGBA'; bright.blend_type = 'MULTIPLY'
        bright.inputs['Factor'].default_value = 1.0; bright.inputs[7].default_value = (1.2, 1.2, 1.2, 1)
        nt.links.new(mix.outputs[2], bright.inputs[6])
        color = bright.outputs[2]
    nt.links.new(color, bsdf.inputs['Base Color'])
    if alpha:
        nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])


def main():
    sys.path.insert(0, str(ROOT / 'scripts'))
    import build_full_track_v002 as V2
    V2.import_addon()
    bpy.ops.wm.open_mainfile(filepath=str(BLEND), load_ui=False, use_scripts=False)
    node_mat(bpy.data.materials['V004_foliage'], TEX / 'foliage.png', alpha=True)
    node_mat(bpy.data.materials['V004_impostor'], TEX / 'impostors.png', alpha=True)
    node_mat(bpy.data.materials['V004_bark'], TEX / 'bark.png')
    for mat in bpy.data.materials:
        if mat.name.startswith('V004_ortho_'):
            k = mat.name.split('_')[-1]
            mult = mat.assettoCorsa.get_property('detailUVMultiplier')
            node_mat(mat, ROOT / f'data/processed/landscape_orthos_v003/chunk_{k}.png', detail=TEX / 'grass_detail.png', mult=mult)
    for c in ('REFERENCE_ONLY_EXCLUDED',):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
    p = np.load(ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz')['designed_xyz_m']
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 16; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items] else 'Standard'
    cam_data = bpy.data.cameras.new('V004_PREVIEW'); cam_data.lens = 22; cam_data.clip_end = 5000
    cam = bpy.data.objects.new('V004_PREVIEW', cam_data); sc.collection.objects.link(cam); sc.camera = cam
    for st in STATIONS:
        i = int(np.searchsorted(s, st)); j = int(np.searchsorted(s, st + 40))
        f = p[j, :2] - p[i, :2]; f /= np.linalg.norm(f)
        pos = p[i].copy(); pos[:2] += np.array([f[1], -f[0]]) * 1.5; pos[2] += 1.2
        tgt = p[min(j, len(p) - 1)].copy(); tgt[:2] += np.array([f[1], -f[0]]) * 1.5; tgt[2] += 1.0
        cam.location = Vector(pos.tolist())
        cam.rotation_euler = (Vector(tgt.tolist()) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = str(OUT / f'driver_{st:05d}.png')
        bpy.ops.render.render(write_still=True)
        print('RENDERED', st, flush=True)


main()
