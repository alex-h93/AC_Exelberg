"""v009 main KN5 (= v008 + smoothed road curves), built in factory-headless Blender from a COPY of the v008 scene
(v008 blend opened read-only, never saved over).

  flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup \
      --python-exit-code 1 --python /abs/scripts/build_full_track_v009.py

Change vs v008 (user's v008 review: "the roads seem to have some rough edges, which are noticable at the turns"):
  every vertex of every exported mesh (road, gravel, grass, invisible walls, markings, warnings, trees) is moved
  in XY by the v009 road field (scripts/v009_field.py, centreline from scripts/v009_centerline.py): exact ribbon
  re-mapping within 9 m of the centreline, fading to zero at 30 m. Z, topology, UVs, materials, flags unchanged.
  Spawns recomputed at designed arclength 10 m on the new centreline (same formula as v007/v008); timing
  gates moved by the field (they sit in the unchanged finish blend zone).
Writes only: blender/exelberg_full_v009.blend, exports/full_track_v009/exelberg_full_v009.kn5,
data/processed/full_track_scene_v009/exported.json
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
from v009_field import Field  # noqa: E402

SRC_BLEND = ROOT / 'blender/exelberg_full_v008.blend'
ALLOW = ROOT / 'data/processed/full_track_scene_v008/export_allowlist.json'
CENTER = ROOT / 'data/processed/road_v009/centerline.npz'
TRACK = 'exelberg_full_v009'
BLEND = ROOT / f'blender/{TRACK}.blend'
EXPORT = ROOT / 'exports/full_track_v009'
KN5 = EXPORT / f'{TRACK}.kn5'
OUT = ROOT / 'data/processed/full_track_scene_v009'
STATION, OFFSET = 10.0, -1.5


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


def xy_area2(co, tri):
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    return (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])


def deform(F, objects):
    stats = {}
    for ob in objects:
        if ob.type != 'MESH':
            continue
        require(np.allclose(np.array(ob.matrix_world), np.eye(4)), f'{ob.name}: non-identity transform')
        me = ob.data
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
        new = co.copy()
        new[:, :2] = F.displace(co[:, :2])
        shift = np.linalg.norm(new[:, :2] - co[:, :2], axis=1)
        col = ob.users_collection[0].name
        st = stats.setdefault(col, dict(objects=0, vertices=0, moved=0, max_shift_m=0.0, flipped_top=0))
        st['objects'] += 1; st['vertices'] += len(co)
        if not (shift > 1e-5).any():
            continue
        me.calc_loop_triangles()
        tri = np.empty(len(me.loop_triangles) * 3, int); me.loop_triangles.foreach_get('vertices', tri); tri = tri.reshape(-1, 3)
        a0, a1 = xy_area2(co, tri), xy_area2(new, tri)
        top = np.abs(a0) > 1e-6  # vertical (wall/tree) faces have ~0 xy area; only planar-facing ones can flip
        flipped = int((top & (np.sign(a0) != np.sign(a1))).sum())
        st['flipped_top'] += flipped
        if col.startswith('PHYS_'):
            require(flipped == 0, f'{ob.name}: {flipped} triangles flipped')
        me.vertices.foreach_set('co', new.ravel())
        me.update()
        st['moved'] += int((shift > 1e-5).sum()); st['max_shift_m'] = max(st['max_shift_m'], float(shift.max()))
    return stats


def main():
    t0 = time.monotonic()
    require(not BLEND.exists() and not KN5.exists(), 'Refuse to overwrite existing v009 outputs')
    EXPORT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    src_hash = sha(SRC_BLEND)
    addon = V2.import_addon()
    bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND), load_ui=False, use_scripts=False)
    c = np.load(CENTER)
    p_old, p_new = c['old_designed_xyz_m'].astype(float), c['new_designed_xyz_m'].astype(float)
    F = Field(p_old, p_new)
    report = dict(source_blend=dict(path=str(SRC_BLEND), sha256=src_hash), blender=bpy.app.version_string,
                  centerline=str(CENTER.relative_to(ROOT)), spawns={}, gates={})
    old_rows, new_rows = np.array(spawn_rows(p_old, STATION)), np.array(spawn_rows(p_new, STATION))
    for name in V2.SPAWNS:
        ob = bpy.data.objects[name]
        before = np.array(ob.matrix_world)
        require(np.allclose(before, old_rows, atol=0.01), f'{name}: v008 spawn does not match the 10 m formula')
        ob.matrix_world = Matrix(new_rows.tolist())
        report['spawns'][name] = dict(moved_m=float(np.linalg.norm(new_rows[:3, 3] - before[:3, 3])))
        require(report['spawns'][name]['moved_m'] < 0.05, f'{name}: spawn moved too far')
    for name in ('AC_TIME_0_L', 'AC_TIME_0_R'):
        ob = bpy.data.objects[name]
        m = np.array(ob.matrix_world)
        xy = F.displace(m[:2, 3][None])[0]
        report['gates'][name] = dict(moved_m=float(np.linalg.norm(xy - m[:2, 3])))
        m[:2, 3] = xy
        ob.matrix_world = Matrix(m.tolist())
    allow = json.loads(ALLOW.read_text())
    objects = [bpy.data.objects[a] for a in allow]
    report['deform'] = deform(F, objects)
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
    require(sha(SRC_BLEND) == src_hash, 'v008 blend changed!')
    report.update(kn5=dict(path=str(KN5.relative_to(ROOT)), bytes=KN5.stat().st_size, sha256=sha(KN5)), objects=len(objects),
                  elapsed_s=round(time.monotonic() - t0, 1), runtime_tested=False)
    (OUT / 'exported.json').write_text(json.dumps(report, indent=2) + '\n')
    (OUT / 'export_allowlist.json').write_text(json.dumps(allow) + '\n')
    print('V009 MAIN PASS', json.dumps(report), flush=True)


main()
