"""v013 scenery export = build_scenery_v011.py with v013 inputs/outputs (geometry from scripts/v013_scenery.py: urban-sign clearance fix). Material/object names stay V011_*.

  flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup \
      --python-exit-code 1 --python /abs/path/scripts/build_scenery_v013.py

Starts from an empty factory scene; never opens or modifies v003/v004 blends or KN5s.
All objects are visual only (VIS-style V011_ names, no leading digit -> no physics).
Writes: exports/full_track_v013/exelberg_v013_scenery.kn5, blender/exelberg_v013_scenery.blend,
data/processed/scenery_v013/exported.json
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

ROOT = Path('/var/home/haze/dev/Assetto_Exelberg')
sys.path.insert(0, str(ROOT / 'scripts'))
import build_full_track_v002 as V2  # noqa: E402
from full_track_v002_export import exporter_class  # noqa: E402

MODE = __import__('os').environ.get('V011_MODE', 'forward')
NAME = {'forward': 'exelberg_v013_scenery', 'reverse': 'exelberg_reverse_v013_scenery'}[MODE]
EXPORT = ROOT / 'exports/full_track_v013'
KN5 = EXPORT / f'{NAME}.kn5'
BLEND = ROOT / f'blender/{NAME}.blend'
SRC = ROOT / 'data/processed' / {'forward': 'scenery_v013', 'reverse': 'scenery_v013r'}[MODE]
URBAN_DDS = ROOT / 'data/processed/textures_v011/v011_urban.dds'
TEX = ROOT / 'data/processed/textures_v007'  # + textures_v011/v011_urban.dds (urban sign atlas)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(c, msg):
    if not c:
        raise RuntimeError(msg)


def load_image(path, name):
    img = bpy.data.images.load(str(path), check_existing=False)
    img.name = name
    img.pack()
    return img


def ac_material(addon, name, shader, slots, props, alpha_tested=False):
    mat = bpy.data.materials.new(name)
    ac = mat.assettoCorsa
    ac.preset_selector = 'NONE'
    ac.shader_name = shader
    ac.blend_mode = '0'
    ac.depth_mode = '0'
    ac.alpha_tested = alpha_tested
    for k, v in props.items():
        ac.set_property(k, v)
    ac.ensure_default_slots_for_shader(shader)
    for slot_name, (img, fname) in slots.items():
        slot = next((s for s in ac.texture_slots if s.slot_name == slot_name), None) or ac.texture_slots.add()
        slot.slot_name = slot_name
        slot.image = img
        slot.override_filename = fname
    addon.materials.sync_material_nodes(mat)
    return mat


def make_mesh_object(name, v, n, uv, tri, mat_idx, mats, coll, flags):
    used = sorted(set(mat_idx.tolist()))
    remap = {m: i for i, m in enumerate(used)}
    mat_idx = np.array([remap[m] for m in mat_idx.tolist()], np.int32)
    order = np.argsort(mat_idx, kind='stable')
    tri, mat_idx = tri[order], mat_idx[order]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v.tolist(), [], tri.tolist())
    me.update()
    layer = me.uv_layers.new(name='UVMap')
    layer.data.foreach_set('uv', uv[tri.reshape(-1)].reshape(-1))
    me.polygons.foreach_set('use_smooth', np.ones(len(tri), bool))
    me.polygons.foreach_set('material_index', mat_idx)
    for m in used:
        me.materials.append(mats[m])
    me.normals_split_custom_set_from_vertices(n.tolist())
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ac = ob.assettoCorsa
    for k, val in flags.items():
        setattr(ac, k, val)
    ac.layer = 0
    return ob


def main():
    t0 = time.monotonic()
    require(not KN5.exists() and not BLEND.exists(), 'Refuse to overwrite existing v013 scenery outputs')
    EXPORT.mkdir(parents=True, exist_ok=True)
    addon = V2.import_addon()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    meta = json.loads((SRC / 'objects.json').read_text())
    geo = np.load(SRC / 'geometry.npz')
    img = {k: load_image(TEX / f'v007_{k}.dds', f'v007_{k}.dds') for k in ('signs', 'asphalt', 'gravel', 'foliage', 'bark', 'facade_white',
                                                                        'facade_cream', 'facade_ochre', 'facade_plain', 'roof_red', 'roof_dark')}
    spec = {
        'V005_atlas': ('ksPerPixelAT', 'signs', dict(ksAmbient=.5, ksDiffuse=.6, ksSpecular=.05, ksSpecularEXP=10.), True),
        'V005_metal': ('ksPerPixel', 'signs', dict(ksAmbient=.45, ksDiffuse=.55, ksSpecular=.35, ksSpecularEXP=40.), False),
        'V005_asphalt': ('ksPerPixel', 'asphalt', dict(ksAmbient=.45, ksDiffuse=.55, ksSpecular=.05, ksSpecularEXP=10.), False),
        'V005_gravel': ('ksPerPixel', 'gravel', dict(ksAmbient=.48, ksDiffuse=.55, ksSpecular=.02, ksSpecularEXP=8.), False),
        'V005_foliage': ('ksPerPixelAT', 'foliage', dict(ksAmbient=.5, ksDiffuse=.62, ksSpecular=.02, ksSpecularEXP=8.), True),
        'V005_bark': ('ksPerPixel', 'bark', dict(ksAmbient=.45, ksDiffuse=.65, ksSpecular=.02, ksSpecularEXP=8.), False),
    }
    spec = {k.replace('V005_', 'V011_'): v for k, v in spec.items()}
    for k in ('facade_white', 'facade_cream', 'facade_ochre', 'facade_plain'):
        spec[f'V011_{k}'] = ('ksPerPixel', k, dict(ksAmbient=.45, ksDiffuse=.6, ksSpecular=.03, ksSpecularEXP=8.), False)
    for k in ('roof_red', 'roof_dark'):
        spec[f'V011_{k}'] = ('ksPerPixel', k, dict(ksAmbient=.45, ksDiffuse=.6, ksSpecular=.08, ksSpecularEXP=15.), False)
    img['urban'] = load_image(URBAN_DDS, 'v011_urban.dds')
    spec['V011_urban'] = ('ksPerPixelAT', 'urban', dict(ksAmbient=.5, ksDiffuse=.6, ksSpecular=.05, ksSpecularEXP=10.), True)
    tex_file = lambda t: 'v011_urban.dds' if t == 'urban' else f'v007_{t}.dds'
    mats = [ac_material(addon, name, sh, {'txDiffuse': (img[t], tex_file(t))}, props, alpha_tested=at)
            for name, (sh, t, props, at) in ((n, spec[n]) for n in meta['materials'])]
    coll = bpy.data.collections.new('VIS_V011_SCENERY')
    bpy.context.scene.collection.children.link(coll)
    objects = []
    for o in meta['objects']:
        a = {k: geo[f"{o['name']}__{k}"] for k in ('v', 'n', 'uv', 'tri', 'mat')}
        flags = dict(visible=True, renderable=True, cast_shadows=bool(o['cast_shadows']), transparent=False,
                     lod_in=float(o['lod_in']), lod_out=float(o['lod_out']))
        objects.append(make_mesh_object(o['name'], a['v'], a['n'], a['uv'], a['tri'], a['mat'], mats, coll, flags))
    require(not addon.materials.audit_texture_bindings(objects, 'EMBEDDED_DDS'), 'Texture bindings')
    exporter = exporter_class(addon)(bpy.context, str(KN5), dict(version=5, texture_mode='EMBEDDED_DDS', target_objects=objects,
                                     apply_modifiers=False, auto_detect_materials=False, auto_fix_wheels=False, selection_only=False))
    model = exporter.export()
    require(not exporter.warnings, 'Exporter warnings ' + str(exporter.warnings))
    with KN5.open('xb') as f:
        model.to_stream(f)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), check_existing=True, copy=True)
    rep = dict(kn5=dict(path=str(KN5.relative_to(ROOT)), bytes=KN5.stat().st_size, sha256=sha(KN5)), root=model.root_node.name,
               objects=len(objects), tris=meta['total_tris'], blender=bpy.app.version_string, elapsed_s=round(time.monotonic() - t0, 1),
               runtime_tested=False)
    (SRC / 'exported.json').write_text(json.dumps(rep, indent=2) + '\n')
    print('V011 SCENERY PASS', MODE, json.dumps(rep), flush=True)


main()
