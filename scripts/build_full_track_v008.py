"""v008 main KN5 (= v007 changes + smoothed landscape), built in factory-headless Blender from a COPY of the v004 scene (v004 blend opened read-only).

  flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup \
      --python-exit-code 1 --python /abs/scripts/build_full_track_v008.py

Changes vs v004 (user's v006 + v007 reviews):
  * spawn helpers AC_PIT_0 / AC_START_0 / AC_HOTLAP_START_0 moved from designed arclength 25 m to 10 m
    (same lane offset -1.5 m, +0.4 m clearance, same yaw convention), so the Königstetten town sign
    (~28 m) is visible ahead from the start
  * v003 guide posts (collection VIS_POSTS) not exported; Austrian posts now live in the scenery KN5
  * PHYS_GRASS heights from data/processed/terrain_v008/smoothed_skin.npz (only > 10 m from the centreline;
    road, gravel, walls and drivable grass unchanged) and smooth vertex normals on PHYS_GRASS + PHYS_GRAVEL
    top faces (v003 was flat-shaded -> visible 8 m facets)
  * VIS_VEGETATION rebuilt with the v004 code/seed, each tree raised/lowered by the ground change at its base
Road, gravel geometry, invisible walls, markings, warnings and timing gates are the unchanged v004 objects.
Writes only: blender/exelberg_full_v008.blend, exports/full_track_v008/exelberg_full_v008.kn5,
data/processed/full_track_scene_v008/exported.json
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path('/var/home/haze/dev/Assetto_Exelberg')
sys.path.insert(0, str(ROOT / 'scripts'))
import build_full_track_v002 as V2  # noqa: E402
from full_track_v002_export import exporter_class  # noqa: E402
from prototype_geometry import station_normals  # noqa: E402

SRC_BLEND = ROOT / 'blender/exelberg_full_v004.blend'
ALLOW = ROOT / 'data/processed/full_track_scene_v004/export_allowlist.json'
TRACK = 'exelberg_full_v008'
BLEND = ROOT / f'blender/{TRACK}.blend'
EXPORT = ROOT / 'exports/full_track_v008'
KN5 = EXPORT / f'{TRACK}.kn5'
OUT = ROOT / 'data/processed/full_track_scene_v008'
SKIN0 = ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz'
SKIN1 = ROOT / 'data/processed/terrain_v008/smoothed_skin.npz'
_V4 = (ROOT / 'scripts/build_full_track_v004.py').read_text().split('\ndef main')[0]
V4 = {}
exec(compile(_V4, 'build_full_track_v004_helpers', 'exec'), V4)  # Batch, impostor, make_mesh_object, constants
OLD_STATION, NEW_STATION, OFFSET = 25.0, 10.0, -1.5


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def require(c, msg):
    if not c:
        raise RuntimeError(msg)


def spawn_rows(p, distance):
    n = station_normals(p)
    st = V2.station(p, distance)
    i, w = st['index'], st['fraction']
    point = np.array(st['point'])
    point[:2] += OFFSET * ((1 - w) * n[i] + w * n[i + 1])
    point[2] += .4
    return V2.corrected_spawn(point, st['forward_xy'])[0]


def smooth_ground():
    s0, s1 = np.load(SKIN0), np.load(SKIN1)
    v0, v1, vn = s0['vertices'].astype(float), s1['vertices'].astype(float), s1['vertex_normals'].astype(float)
    require(np.array_equal(v0[:, :2], v1[:, :2]), 'smoothed skin XY differs')
    used = np.zeros(len(v0), bool); used[s0['triangles'].ravel()] = True
    key = {}
    for i, (x, y) in enumerate(np.round(v0[:, :2], 2).tolist()):
        if used[i] or (x, y) not in key:  # skin has 83 unreferenced vertices; prefer triangle-used ones
            key[(x, y)] = i
    stats = dict(objects=0, vertices=0, z_changed=0, unmatched=0, max_dz=0.0, smooth_loops=0, flat_loops=0)
    for cname, move in (('PHYS_GRASS', True), ('PHYS_GRAVEL', False)):
        for ob in bpy.data.collections[cname].objects:
            me = ob.data
            mw = np.array(ob.matrix_world)
            require(np.allclose(mw, np.eye(4)), f'{ob.name}: non-identity transform')
            co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
            idx = np.array([key.get((x, y), -1) for x, y in np.round(co[:, :2], 2).tolist()])
            stats['unmatched'] += int((idx < 0).sum())
            require((idx >= 0).all(), f'{ob.name}: {(idx < 0).sum()} vertices not on the skin grid')
            if move:
                dz = v1[idx, 2] - v0[idx, 2]
                co[:, 2] += dz
                me.vertices.foreach_set('co', co.ravel())
                stats['z_changed'] += int((np.abs(dz) > 1e-4).sum())
                stats['max_dz'] = max(stats['max_dz'], float(np.abs(dz).max()))
            else:
                require(np.allclose(v1[idx, 2], v0[idx, 2]), f'{ob.name}: gravel height would change')
            me.update()
            np_ = len(me.polygons)
            pn = np.empty(np_ * 3); me.polygons.foreach_get('normal', pn); pn = pn.reshape(-1, 3)
            ls = np.empty(np_, int); me.polygons.foreach_get('loop_start', ls)
            lt = np.empty(np_, int); me.polygons.foreach_get('loop_total', lt)
            lv = np.empty(len(me.loops), int); me.loops.foreach_get('vertex_index', lv)
            lpoly = np.repeat(np.arange(np_), lt)
            top = pn[lpoly, 2] > 0.3
            ln = np.where(top[:, None], vn[idx[lv]], pn[lpoly])
            stats['smooth_loops'] += int(top.sum()); stats['flat_loops'] += int((~top).sum())
            me.polygons.foreach_set('use_smooth', np.ones(np_, bool))
            me.normals_split_custom_set(ln.tolist())
            stats['objects'] += 1; stats['vertices'] += len(co)
    return stats


def rebuild_trees(allow):
    import full_track_v003_geometry as H
    g0 = H.GroundIndex(np.load(SKIN0)['vertices'], np.load(SKIN0)['triangles'])
    g1 = H.GroundIndex(np.load(SKIN1)['vertices'], np.load(SKIN1)['triangles'])
    old = [o.name for o in bpy.data.collections['VIS_VEGETATION'].objects]
    veg = bpy.data.collections['VIS_VEGETATION']
    for o in list(veg.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    allow = [a for a in allow if a not in set(old)]
    tm = json.loads((V4['TEX'] / 'manifest.json').read_text())
    foliage, bark, impm = (bpy.data.materials[n] for n in ('V004_foliage', 'V004_bark', 'V004_impostor'))
    tr = np.load(ROOT / 'data/processed/vegetation_v004/trees.npz')
    xyz, hgt, crown, sp, tier, seed = (tr[k] for k in ('xyz', 'height', 'crown', 'species', 'tier', 'seed'))
    dzs = np.zeros(len(xyz))
    for i in range(len(xyz)):
        q = xyz[i, :2].astype(float)
        try:
            dzs[i] = g1.sample(q) - g0.sample(q)
        except RuntimeError:
            dzs[i] = 0.0
    meta = tm['impostor_meta']
    rng = np.random.default_rng(4004)
    cells = {}
    for i in range(len(xyz)):
        cells.setdefault((int(xyz[i, 0] // V4['CELL']), int(xyz[i, 1] // V4['CELL'])), []).append(i)
    T, Batch, impostor, mk = V4['T'], V4['Batch'], V4['impostor'], V4['make_mesh_object']
    new = []
    for key_, ids in sorted(cells.items()):
        hero, imp_near, imp_far = Batch(), Batch(), Batch()
        for i in ids:
            off = xyz[i] - np.array([0, 0, 0.2], np.float32) + np.array([0, 0, dzs[i]], np.float32)
            im = impostor(int(sp[i]), hgt[i], seed[i], meta, rng)
            if tier[i] == 0:
                hero.add(T.tree(int(sp[i]), float(hgt[i]), float(crown[i]), int(seed[i])), off)
                imp_near.add(im, off)
            else:
                imp_far.add(im, off)
        tag = f'{key_[0]:+04d}_{key_[1]:+04d}'.replace('+', 'p').replace('-', 'm')
        for kind, batch, mats, flags in (
                ('H', hero, [foliage, bark], dict(visible=True, renderable=True, cast_shadows=True, transparent=False, lod_in=0.0, lod_out=V4['HERO_LOD'])),
                ('L', imp_near, [impm], dict(visible=True, renderable=True, cast_shadows=False, transparent=False, lod_in=V4['HERO_LOD'], lod_out=V4['FAR_LOD'])),
                ('F', imp_far, [impm], dict(visible=True, renderable=True, cast_shadows=False, transparent=False, lod_in=0.0, lod_out=V4['FAR_LOD']))):
            if not batch.count:
                continue
            v, n, uv, tri, mi = batch.arrays()
            new.append(mk(f'VIS_TREE_{kind}_{tag}', v, n, uv, tri, mi, mats, veg, flags).name)
    require(sorted(new) == sorted(old), 'rebuilt tree object set differs from v004')
    return allow + new, dict(trees=int(len(xyz)), objects=len(new), moved=int((np.abs(dzs) > 1e-3).sum()),
                             dz_m=[round(float(dzs.min()), 3), round(float(dzs.max()), 3)])


def main():
    t0 = time.monotonic()
    require(not BLEND.exists() and not KN5.exists(), 'Refuse to overwrite existing v008 outputs')
    EXPORT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    src_hash = sha(SRC_BLEND)
    addon = V2.import_addon()
    bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND), load_ui=False, use_scripts=False)
    p = np.load(ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz')['designed_xyz_m'].astype(float)
    report = dict(source_blend=dict(path=str(SRC_BLEND), sha256=src_hash), blender=bpy.app.version_string, spawns={})
    old_rows = spawn_rows(p, OLD_STATION)
    new_rows = spawn_rows(p, NEW_STATION)
    for name in V2.SPAWNS:
        ob = bpy.data.objects[name]
        before = np.array(ob.matrix_world)
        require(np.allclose(before, old_rows, atol=0.01), f'{name}: v004 spawn does not match the 25 m formula')
        ob.matrix_world = Matrix(new_rows)
        after = np.array(ob.matrix_world)
        report['spawns'][name] = dict(before=before[:3, 3].round(3).tolist(), after=after[:3, 3].round(3).tolist(),
                                      moved_m=float(np.linalg.norm(after[:3, 3] - before[:3, 3])),
                                      rotation_unchanged_deg=float(np.degrees(np.arccos(np.clip(
                                          (np.trace(before[:3, :3].T @ after[:3, :3]) - 1) / 2, -1, 1)))))
    report['terrain'] = smooth_ground()
    allow = json.loads(ALLOW.read_text())
    allow, report['vegetation'] = rebuild_trees(allow)
    posts = {o.name for o in bpy.data.collections['VIS_POSTS'].objects}
    allow = [a for a in allow if a not in posts]
    report['removed_post_objects'] = len(posts)
    objects = [bpy.data.objects[a] for a in allow]
    require(not addon.materials.audit_texture_bindings([o for o in objects if o.type == 'MESH'], 'EMBEDDED_DDS'), 'Texture bindings')
    exporter = exporter_class(addon)(bpy.context, str(KN5), dict(version=5, texture_mode='EMBEDDED_DDS', target_objects=objects,
                                     apply_modifiers=False, auto_detect_materials=False, auto_fix_wheels=False, selection_only=False))
    model = exporter.export()
    require(not exporter.warnings, 'Exporter warnings ' + str(exporter.warnings))
    require(model.root_node.name == TRACK, 'Wrong root ' + model.root_node.name)
    with KN5.open('xb') as f:
        model.to_stream(f)
    require(KN5.stat().st_size <= 256 * 1024 * 1024, 'KN5 over 256 MiB')
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), check_existing=True, copy=True)
    require(sha(SRC_BLEND) == src_hash, 'v004 blend changed!')
    report.update(kn5=dict(path=str(KN5.relative_to(ROOT)), bytes=KN5.stat().st_size, sha256=sha(KN5)), objects=len(objects),
                  elapsed_s=round(time.monotonic() - t0, 1), runtime_tested=False)
    (OUT / 'exported.json').write_text(json.dumps(report, indent=2) + '\n')
    (OUT / 'export_allowlist.json').write_text(json.dumps(allow) + '\n')
    print('V008 MAIN PASS', json.dumps(report), flush=True)


main()
