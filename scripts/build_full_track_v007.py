"""v007 main KN5, built in factory-headless Blender from a COPY of the v004 scene (v004 blend opened read-only).

  flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup \
      --python-exit-code 1 --python /abs/scripts/build_full_track_v007.py

Changes vs v004 (user's v006 in-game review):
  * spawn helpers AC_PIT_0 / AC_START_0 / AC_HOTLAP_START_0 moved from designed arclength 25 m to 10 m
    (same lane offset -1.5 m, +0.4 m clearance, same yaw convention), so the Königstetten town sign
    (~28 m) is visible ahead from the start
  * v003 guide posts (collection VIS_POSTS) not exported; Austrian posts now live in the scenery KN5
Everything else (road, gravel, grass, invisible walls, markings, warnings, timing gates, trees) is exported
from the unchanged v004 objects.
Writes only: blender/exelberg_full_v007.blend, exports/full_track_v007/exelberg_full_v007.kn5,
data/processed/full_track_scene_v007/exported.json
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
TRACK = 'exelberg_full_v007'
BLEND = ROOT / f'blender/{TRACK}.blend'
EXPORT = ROOT / 'exports/full_track_v007'
KN5 = EXPORT / f'{TRACK}.kn5'
OUT = ROOT / 'data/processed/full_track_scene_v007'
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


def main():
    t0 = time.monotonic()
    require(not BLEND.exists() and not KN5.exists(), 'Refuse to overwrite existing v007 outputs')
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
    allow = json.loads(ALLOW.read_text())
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
    print('V007 MAIN PASS', json.dumps(report), flush=True)


main()
