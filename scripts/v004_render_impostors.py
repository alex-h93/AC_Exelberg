"""Blender (factory, background): render v004 impostor sprites + a hero-tree check image.

flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup \
    --python-exit-code 1 --python scripts/v004_render_impostors.py
Writes only under data/processed/textures_v004/impostor_renders/.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v004_treegen as T  # noqa: E402

TEX = ROOT / 'data/processed/textures_v004'
OUT = TEX / 'impostor_renders'
REF = {'beech': (24.0, 6.0), 'oak': (18.0, 6.5), 'conifer': (26.0, 3.8), 'shrub': (3.0, 1.6)}


def material(name, image_path, alpha):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(image_path))
    tex.interpolation = 'Closest' if alpha else 'Linear'
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    if alpha:
        nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        if hasattr(mat, 'blend_method'):
            mat.blend_method = 'CLIP'
    bsdf.inputs['Roughness'].default_value = 0.85
    return mat


def make_object(name, t, mats, loc=(0, 0, 0), rot=0.0):
    me = bpy.data.meshes.new(name)
    v = t['v'].astype(float)
    c, s = np.cos(rot), np.sin(rot)
    v = v @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    me.from_pydata((v + np.array(loc)).tolist(), [], t['tri'].tolist())
    uv = me.uv_layers.new(name='UVMap')
    loops = t['uv'][t['tri'].reshape(-1)]
    uv.data.foreach_set('uv', loops.reshape(-1))
    me.polygons.foreach_set('material_index', t['mat'].astype(int))
    for m in mats:
        me.materials.append(m)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def setup_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 24
    sc.render.film_transparent = True
    sc.world = bpy.data.worlds.new('w') if sc.world is None else sc.world
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.55, 0.65, 0.8, 1)
    bg.inputs['Strength'].default_value = 0.9
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    sun.data.energy = 3.2
    sun.rotation_euler = (0.9, 0.2, -0.6)
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc, cam = setup_scene()
    fol = material('foliage', TEX / 'previews/foliage.png', True)
    bark = material('bark', TEX / 'previews/bark.png', False)
    meta = {}
    sc.render.resolution_x = sc.render.resolution_y = 512
    cam.data.type = 'ORTHO'
    for sp, (H, R) in REF.items():
        for k in range(4):
            for o in [o for o in bpy.data.objects if o.type == 'MESH']:
                bpy.data.objects.remove(o)
            t = T.tree(sp, H, R, 1000 + k)
            make_object('tree', t, [fol, bark])
            span = float(max(t['v'][:, 2].max(), 2 * np.abs(t['v'][:, :2]).max())) * 1.1
            cam.data.ortho_scale = span
            cam.location = (0, -60, span / 2)
            cam.rotation_euler = (np.pi / 2, 0, 0)
            sc.render.filepath = str(OUT / f'{sp}_{k}.png')
            bpy.ops.render.render(write_still=True)
            meta[f'{sp}_{k}'] = dict(species=sp, variant=k, ref_height=H, ref_crown=R, span_m=span,
                                     base='bottom edge = z0, centred x')
            print('rendered', sp, k, flush=True)
    # hero check: small grove from a driver-like viewpoint
    for o in [o for o in bpy.data.objects if o.type == 'MESH']:
        bpy.data.objects.remove(o)
    rng = np.random.default_rng(7)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    ground = bpy.context.active_object
    gm = bpy.data.materials.new('g'); gm.use_nodes = True
    gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.08, 0.12, 0.04, 1)
    ground.data.materials.append(gm)
    for i in range(70):
        x, y = rng.uniform(-60, 60), rng.uniform(8, 80)
        sp = rng.choice(['beech'] * 6 + ['oak'] * 3 + ['conifer'])
        H = rng.uniform(16, 30) if sp != 'conifer' else rng.uniform(20, 30)
        R = 0.2 * H + 1 if sp != 'conifer' else 0.13 * H + .8
        make_object(f't{i}', T.tree(sp, H, R, i), [fol, bark], loc=(x, y, 0), rot=rng.uniform(0, 6.28))
    for i in range(12):
        make_object(f's{i}', T.tree('shrub', 2.5, 1.4, 50 + i), [fol, bark], loc=(rng.uniform(-40, 40), rng.uniform(5, 10), 0))
    cam.data.type = 'PERSP'
    cam.data.lens = 24
    cam.location = (0, -12, 1.3)
    cam.rotation_euler = (np.radians(88), 0, 0)
    sc.render.film_transparent = False
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.filepath = str(OUT / 'hero_check.png')
    bpy.ops.render.render(write_still=True)
    (OUT / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')


main()
