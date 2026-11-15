"""v004 visual upgrade, built in factory-headless Blender from a COPY of the v003 scene.

  flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup \
      --python-exit-code 1 --python scripts/build_full_track_v004.py

Unchanged from v003 (same objects, flags, geometry): road, gravel, ground skin,
invisible walls, markings, posts, warnings, AC helpers (spawn/timing).
Changed: VIS_FOREST removed; CHM-placed vegetation added (3D hero trees near the
road with impostor LOD, impostor trees further out); orthophoto ground materials
switched to ksPerPixelMultiMap with a tiling grass multiply-detail and mipmapped DDS.
Writes only: blender/exelberg_full_v004.blend, exports/full_track_v004/,
data/processed/full_track_scene_v004/. v003 files are opened read-only.
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
import v004_treegen as T  # noqa: E402
from full_track_v002_export import exporter_class  # noqa: E402

SRC_BLEND = ROOT / 'blender/exelberg_full_v003.blend'
BLEND = ROOT / 'blender/exelberg_full_v004.blend'
EXPORT = ROOT / 'exports/full_track_v004'
TRACK = 'exelberg_full_v004'
KN5 = EXPORT / f'{TRACK}.kn5'
OUT = ROOT / 'data/processed/full_track_scene_v004'
TEX = ROOT / 'data/processed/textures_v004'
CELL = 120.0
HERO_LOD = 180.0
FAR_LOD = 1500.0
SPECIES = T.SPECIES


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(c, msg):
    if not c:
        raise RuntimeError(msg)


def small_dds(path, rgba):
    import struct
    h = w = 4
    levels = [np.tile(np.array(rgba, np.uint8), (s, s, 1)) for s in (4, 2, 1)]
    pf = struct.pack('<8I', 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    header = b'DDS ' + struct.pack('<7I', 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x8 | 0x20000, h, w, w * 4, 0, 3) + b'\0' * 44 + pf + struct.pack('<5I', 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)
    path.write_bytes(header + b''.join(l[..., [2, 1, 0, 3]].tobytes() for l in levels))
    return path


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
    order = np.argsort(mat_idx, kind='stable')  # one contiguous run per material -> one KN5 submesh each
    tri, mat_idx = tri[order], mat_idx[order]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v.tolist(), [], tri.tolist())
    me.update()
    layer = me.uv_layers.new(name='UVMap')
    layer.data.foreach_set('uv', uv[tri.reshape(-1)].reshape(-1))
    me.polygons.foreach_set('use_smooth', np.ones(len(tri), bool))
    me.polygons.foreach_set('material_index', mat_idx.astype(np.int32))
    for m in mats:
        me.materials.append(m)
    me.normals_split_custom_set_from_vertices(n.tolist())
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ac = ob.assettoCorsa
    for k, val in flags.items():
        setattr(ac, k, val)
    ac.layer = 0
    return ob


class Batch:
    def __init__(self):
        self.v, self.n, self.uv, self.tri, self.mat = [], [], [], [], []
        self.count = 0

    def add(self, t, offset):
        self.v.append(t['v'] + offset); self.n.append(t['n']); self.uv.append(t['uv'])
        self.tri.append(t['tri'] + self.count); self.mat.append(t['mat']); self.count += len(t['v'])

    def arrays(self):
        return (np.concatenate(self.v), np.concatenate(self.n), np.concatenate(self.uv),
                np.concatenate(self.tri), np.concatenate(self.mat))


def impostor(species, height, seed, meta, rng):
    k = int(seed) % 4
    sp = SPECIES[species]
    info = meta[f'{sp}_{k}']
    s = float(height) / info['ref_height']
    w = h = info['span_m'] * s
    ang = rng.uniform(0, np.pi)
    v, n, uv, tri = [], [], [], []
    u0, u1 = k / 4 + .003, (k + 1) / 4 - .003
    v0, v1 = 1 - (species + 1) / 4 + .003, 1 - species / 4 - .003
    for q, a in enumerate((ang, ang + np.pi / 2)):
        d = np.array([np.cos(a), np.sin(a), 0]) * w / 2
        base = len(v)
        v += [-d + [0, 0, -0.25], d + [0, 0, -0.25], d + [0, 0, h - .25], -d + [0, 0, h - .25]]
        nn = np.array([-np.sin(a), np.cos(a), 0]) * .35 + [0, 0, 1]
        n += [nn] * 4
        uv += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        tri += [(base, base + 1, base + 2), (base, base + 2, base + 3), (base, base + 2, base + 1), (base, base + 3, base + 2)]
    nn = np.array(n, float); nn /= np.linalg.norm(nn, axis=1, keepdims=True)
    return dict(v=np.array(v, np.float32), n=nn.astype(np.float32), uv=np.array(uv, np.float32),
                tri=np.array(tri, np.int32), mat=np.zeros(len(tri), np.int8))


def main():
    t0 = time.monotonic()
    require(not BLEND.exists() and not KN5.exists(), 'Refuse to overwrite existing v004 outputs')
    EXPORT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    src_hash = sha(SRC_BLEND)
    addon = V2.import_addon()
    bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND), load_ui=False, use_scripts=False)
    contract = json.loads(bpy.data.texts['V003_EDITABLE_AUTHORING_CONTRACT.json'].as_string())
    allow = list(contract['export_allowlist'])
    report = dict(source_blend=dict(path=str(SRC_BLEND), sha256=src_hash), blender=bpy.app.version_string)

    # --- remove v002/v003 procedural forest
    forest = bpy.data.collections['VIS_FOREST']
    removed = [o.name for o in forest.objects]
    for o in list(forest.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(forest)
    allow = [a for a in allow if a not in set(removed)]
    for name in ('V002_bark', 'V002_canopy'):
        if name in bpy.data.materials:
            bpy.data.materials.remove(bpy.data.materials[name])
    report['removed_forest_objects'] = len(removed)

    # --- textures/materials
    tm = json.loads((TEX / 'manifest.json').read_text())
    flat = small_dds(EXPORT / 'v004_flat_nm.dds', (128, 128, 255, 255))
    maps = small_dds(EXPORT / 'v004_ground_maps.dds', (18, 24, 255, 255))
    img = {k: load_image(TEX / f'v004_{k}.dds', f'v004_{k}.dds') for k in ('foliage', 'bark', 'impostors', 'grass_detail')}
    img_flat = load_image(flat, 'v004_flat_nm.dds')
    img_maps = load_image(maps, 'v004_ground_maps.dds')
    foliage = ac_material(addon, 'V004_foliage', 'ksPerPixelAT', {'txDiffuse': (img['foliage'], 'v004_foliage.dds')},
                          dict(ksAmbient=.5, ksDiffuse=.62, ksSpecular=.02, ksSpecularEXP=8.), alpha_tested=True)
    bark = ac_material(addon, 'V004_bark', 'ksPerPixel', {'txDiffuse': (img['bark'], 'v004_bark.dds')},
                       dict(ksAmbient=.45, ksDiffuse=.65, ksSpecular=.02, ksSpecularEXP=8.))
    impm = ac_material(addon, 'V004_impostor', 'ksPerPixelAT', {'txDiffuse': (img['impostors'], 'v004_impostors.dds')},
                       dict(ksAmbient=.62, ksDiffuse=.45, ksSpecular=0., ksSpecularEXP=8.), alpha_tested=True)
    ortho_manifest = json.loads((ROOT / 'data/processed/landscape_orthos_v003/manifest.json').read_text())
    widths = {c['index']: c['width'] * 2.0 for c in ortho_manifest['chunks']}
    changed = []
    for mat in list(bpy.data.materials):
        if not mat.name.startswith('V003_ortho_'):
            continue
        k = mat.name.split('_')[-1]
        new = TEX / f'v004_ortho_{k}.dds'
        require(new.is_file(), f'missing {new}')
        oi = load_image(new, f'v004_ortho_{k}.dds')
        ac = mat.assettoCorsa
        ac.shader_name = 'ksPerPixelMultiMap'
        ac.texture_slots.clear()
        for slot, (im, fname) in {'txDiffuse': (oi, oi.name), 'txNormal': (img_flat, img_flat.name),
                                  'txMaps': (img_maps, img_maps.name), 'txDetail': (img['grass_detail'], 'v004_grass_detail.dds')}.items():
            s = ac.texture_slots.add(); s.slot_name = slot; s.image = im; s.override_filename = fname
        mult = round(widths[int(k)] / 2.5, 2)
        for key, val in dict(ksAmbient=.55, ksDiffuse=.78, ksSpecular=.03, ksSpecularEXP=12., fresnelC=0., fresnelEXP=1.,
                             fresnelMaxLevel=0., isAdditive=0., useDetail=1., detailUVMultiplier=mult).items():
            ac.set_property(key, val)
        mat.name = f'V004_ortho_{k}'
        addon.materials.sync_material_nodes(mat)
        changed.append(dict(material=mat.name, detailUVMultiplier=mult))
    report['ortho_materials'] = changed

    # --- vegetation
    veg = bpy.data.collections.new('VIS_VEGETATION')
    bpy.context.scene.collection.children.link(veg)
    tr = np.load(ROOT / 'data/processed/vegetation_v004/trees.npz')
    xyz, hgt, crown, sp, tier, seed = tr['xyz'], tr['height'], tr['crown'], tr['species'], tr['tier'], tr['seed']
    meta = tm['impostor_meta']
    rng = np.random.default_rng(4004)
    cells = {}
    for i in range(len(xyz)):
        cells.setdefault((int(xyz[i, 0] // CELL), int(xyz[i, 1] // CELL)), []).append(i)
    new_objs = []
    stats = dict(hero_trees=0, impostor_trees=0, hero_tris=0, impostor_tris=0, objects=0)
    for ci, (key, ids) in enumerate(sorted(cells.items())):
        hero, imp_near, imp_far = Batch(), Batch(), Batch()
        for i in ids:
            off = xyz[i] - np.array([0, 0, 0.2], np.float32)
            im = impostor(int(sp[i]), hgt[i], seed[i], meta, rng)
            if tier[i] == 0:
                hero.add(T.tree(int(sp[i]), float(hgt[i]), float(crown[i]), int(seed[i])), off)
                imp_near.add(im, off)
                stats['hero_trees'] += 1
            else:
                imp_far.add(im, off)
                stats['impostor_trees'] += 1
        tag = f'{key[0]:+04d}_{key[1]:+04d}'.replace('+', 'p').replace('-', 'm')
        for kind, batch, mats, flags in (
                ('H', hero, [foliage, bark], dict(visible=True, renderable=True, cast_shadows=True, transparent=False, lod_in=0.0, lod_out=HERO_LOD)),
                ('L', imp_near, [impm], dict(visible=True, renderable=True, cast_shadows=False, transparent=False, lod_in=HERO_LOD, lod_out=FAR_LOD)),
                ('F', imp_far, [impm], dict(visible=True, renderable=True, cast_shadows=False, transparent=False, lod_in=0.0, lod_out=FAR_LOD))):
            if not batch.count:
                continue
            v, n, uv, tri, mi = batch.arrays()
            ob = make_mesh_object(f'VIS_TREE_{kind}_{tag}', v, n, uv, tri, mi, mats, veg, flags)
            new_objs.append(ob.name)
            stats['hero_tris' if kind == 'H' else 'impostor_tris'] += len(tri)
            stats['objects'] += 1
        if ci % 50 == 0:
            print('VEG', ci, '/', len(cells), stats, flush=True)
    report['vegetation'] = stats
    allow += new_objs

    # --- export
    objects = [bpy.data.objects[a] for a in allow]
    require(not addon.materials.audit_texture_bindings([o for o in objects if o.type == 'MESH'], 'EMBEDDED_DDS'), 'Texture bindings')
    print('EXPORT', len(objects), 'objects', flush=True)
    exporter = exporter_class(addon)(bpy.context, str(KN5), dict(version=5, texture_mode='EMBEDDED_DDS', target_objects=objects,
                                     apply_modifiers=False, auto_detect_materials=False, auto_fix_wheels=False, selection_only=False))
    model = exporter.export()
    require(not exporter.warnings, 'Exporter warnings ' + str(exporter.warnings))
    require(model.root_node.name == TRACK, 'Wrong root ' + model.root_node.name)
    with KN5.open('xb') as f:
        model.to_stream(f)
    require(KN5.stat().st_size <= 256 * 1024 * 1024, 'KN5 over 256 MiB')
    report['kn5'] = dict(path=str(KN5), bytes=KN5.stat().st_size, sha256=sha(KN5))
    report['export_allowlist'] = allow
    report['tris_total'] = sum(len(o.data.polygons) for o in objects if o.type == 'MESH')
    t = bpy.data.texts.new('V004_AUTHORING_CONTRACT.json')
    t.write(json.dumps(report, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), check_existing=True, copy=True)
    report['blend'] = dict(path=str(BLEND), sha256=sha(BLEND))
    require(sha(SRC_BLEND) == src_hash, 'v003 blend changed!')
    report['elapsed_s'] = time.monotonic() - t0
    (OUT / 'exported.json').write_text(json.dumps({k: v for k, v in report.items() if k != 'export_allowlist'}, indent=2) + '\n')
    (OUT / 'export_allowlist.json').write_text(json.dumps(allow) + '\n')
    print('V004 PASS', json.dumps({k: report[k] for k in ('vegetation', 'kn5', 'tris_total', 'elapsed_s')}), flush=True)


main()
