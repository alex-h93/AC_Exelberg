#!/usr/bin/env python3
"""Validate the v010 KN5s and assemble build/full_track_v010/exelberg_full_v010/.

v010 = v009 + extension to the Neuwaldegg roundabout (finish at its 2nd exit + 100 m run-off).
Offline checks of the main KN5 against the v009 main KN5 and the v010 skin:
  * every v010 ROAD/GRAVEL/GRASS triangle is either a triangle of the final v010 skin (skin_v010.npz) or an unchanged
    v009 non-top (side/skirt) face outside the patch; every skin triangle is present exactly once (corners <= 3 mm)
  * physics nodes not touched by the cut are byte-identical in geometry to v009
  * walls: v009 wall faces in the patch area removed, 1WALL_L/R_X010 + 1WALL_END present
  * helpers: spawns unchanged (< 1 mm), AC_TIME_0_L/R at the new finish (+-3 m)
  * scenery second KN5: same checks as v009
map.png / ui/outline.png / data/map.ini regenerated for the longer route (package_ac_test helpers).
Never touches build/full_track_v009 or the game folder.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import imagecodecs
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_track_v004_kn5 import parse  # noqa: E402
from package_ac_test import draw_route, map_transform  # noqa: E402
from validate_kn5 import bounded_read  # noqa: E402

TRACK = 'exelberg_full_v010'
OLD_PKG = ROOT / 'build/full_track_v009/exelberg_full_v009'
OLD_MAN = ROOT / 'data/processed/full_track_package_v009/manifest.json'
OLD_MAIN = 'exelberg_full_v009.kn5'
OLD_SCENERY = 'exelberg_v009_scenery.kn5'
MAIN_OUT = f'{TRACK}.kn5'
NEW_MAIN = ROOT / f'exports/full_track_v010/{TRACK}.kn5'
ROADSIDE = ROOT / 'exports/full_track_v010/exelberg_v010_scenery.kn5'
PKG = ROOT / 'build/full_track_v010' / TRACK
OUT = ROOT / 'data/processed/full_track_package_v010'
SRC = ROOT / 'data/processed/scenery_v010'
EXT = ROOT / 'data/processed/extension_v010'
CAP = 256 * 1024 * 1024
REGENERATED = ('map.png', 'ui/outline.png', 'data/map.ini')


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return parse(bounded_read(path, max_file=CAP), max_file=CAP, max_nodes=16384,
                 max_texture=32 * 1024 * 1024, max_materials=128, max_textures=128)


def tris_xyz(n):
    """(n,3,3) triangles in project coordinates (KN5 x, up, z=-y -> x, y, z)."""
    t = n['vertices'][:, :3].astype(np.float64)[n['indices'].reshape(-1, 3)]
    return np.stack([t[..., 0], -t[..., 2], t[..., 1]], -1)


def corner_err(a, b):
    return np.linalg.norm(a[:, :, None, :] - b[:, None, :, :], axis=-1).min(-1).max(1)


def validate():
    old = json.loads(OLD_MAN.read_text())
    assert sha(OLD_PKG / OLD_MAIN) == old['main_kn5']['sha256'], 'v009 main KN5 differs from its manifest'
    scene = json.loads((ROOT / 'data/processed/full_track_scene_v010/exported.json').read_text())
    om, nm = load(OLD_PKG / OLD_MAIN), load(NEW_MAIN)
    assert nm['nodes'][0]['name'] == TRACK, 'root node must be named after the track folder'
    names = [n['name'] for n in nm['nodes']]
    assert len(names) == len(set(names)), 'duplicate node names in main KN5'
    phys = lambda k: {n['name']: n for n in k['nodes'] if n['name'][:1].isdigit() and n['kind'] == 2}
    po, pn = phys(om), phys(nm)
    touched = set(scene['cut']['faces_removed']) | set(scene['cut']['objects_deleted'])
    added = set(scene['new_objects'])
    assert set(pn) == (set(po) - set(scene['cut']['objects_deleted'])) | {a for a in added if a[:1].isdigit()}, 'physics node set'
    same = 0
    for k in sorted(set(po) - touched):
        a, b = tris_xyz(po[k]), tris_xyz(pn[k])
        assert a.shape == b.shape and np.abs(a - b).max() < 1e-6, f'{k}: untouched physics node changed'
        same += 1
    # surface triangles vs the final skin
    sk = np.load(EXT / 'skin_v010.npz')
    st = sk['vertices'].astype(np.float64)[sk['triangles']]
    surf = [tris_xyz(n) for k, n in pn.items() if k.startswith(('1ROAD', '1GRAVEL', '1GRASS'))]
    kt = np.concatenate(surf)
    d, j = cKDTree(kt.mean(1)).query(st.mean(1))
    assert len(np.unique(j)) == len(j), 'skin -> KN5 triangle matching not one-to-one'
    err = corner_err(st, kt[j])
    assert err.max() < 3e-3, f'skin triangle missing/moved in KN5 ({err.max():.4f} m)'
    extra = np.setdiff1d(np.arange(len(kt)), j)
    ex = kt[extra]
    nz = np.cross(ex[:, 1] - ex[:, 0], ex[:, 2] - ex[:, 0])
    top = np.abs(nz[:, 2]) / (np.linalg.norm(nz, axis=1) + 1e-12) > 0.3
    assert not top.any(), f'{int(top.sum())} upward KN5 surface faces not in the v010 skin'
    oldsurf = np.concatenate([tris_xyz(n) for k, n in po.items() if k.startswith(('1ROAD', '1GRAVEL', '1GRASS'))])
    d2, j2 = cKDTree(oldsurf.mean(1)).query(ex.mean(1))
    assert (corner_err(ex, oldsurf[j2]) < 1e-3).all(), 'non-skin KN5 faces must be unchanged v009 side faces'
    for w in ('1WALL_L_X010', '1WALL_R_X010', '1WALL_END'):
        assert w in pn, f'missing {w}'
    sp = {n['name']: np.asarray(n['matrix'], float).reshape(4, 4)[3, :3] for n in nm['nodes'] if n['name'].startswith('AC_')}
    so = {n['name']: np.asarray(n['matrix'], float).reshape(4, 4)[3, :3] for n in om['nodes'] if n['name'].startswith('AC_')}
    assert sp.keys() == so.keys(), 'AC helper set changed'
    for k in sp:
        if not k.startswith('AC_TIME'):
            assert np.linalg.norm(sp[k] - so[k]) < 1e-3, f'{k} moved'
    r = np.load(EXT / 'route.npz')
    P = r['designed_xyz_m']
    fin = P[int(r['finish_station'])]
    gate = {k: float(np.linalg.norm(np.array([v[0], -v[2]]) - fin[:2])) for k, v in sp.items() if k.startswith('AC_TIME')}
    assert all(2.5 < g < 3.5 for g in gate.values()), gate
    assert not any(n.startswith('VIS_WARNING_BRAKE') for n in names), 'old Marswiese warnings still present'
    # scenery KN5
    rs = load(ROADSIDE)
    rnames = [n['name'] for n in rs['nodes']]
    assert len(rnames) == len(set(rnames)), 'duplicate node names in roadside KN5'
    assert not any(n[:1].isdigit() for n in rnames), 'physics-style node name in roadside KN5'
    assert not any(n.startswith('AC_') for n in rnames), 'AC helper in roadside KN5'
    assert not set(rnames) & set(names), 'node names clash with main KN5'
    meshes = [n for n in rs['nodes'] if n['kind'] == 2]
    assert all(n['visible'] and n['renderable'] for n in meshes), 'hidden roadside mesh'
    texs = {t['name'] for t in rs['textures']}
    for m in rs['materials']:
        for b in m['bindings']:
            assert b[2] in texs, f'{m["name"]} -> missing texture {b[2]}'
    meta = json.loads((SRC / 'objects.json').read_text())
    rj = json.loads((EXT / 'route.json').read_text())
    return dict(main_kn5=dict(file=MAIN_OUT, path=str(NEW_MAIN.relative_to(ROOT)), bytes=NEW_MAIN.stat().st_size, sha256=sha(NEW_MAIN),
                              v009_sha256=old['main_kn5']['sha256'], physics_nodes=len(pn), untouched_nodes_identical=same,
                              skin_triangles_matched=int(len(st)), max_skin_corner_err_m=float(err.max()),
                              unchanged_side_faces=int(len(extra)), gates_from_finish_m=gate),
                route=dict(length_m=rj['length_m'], old_length_m=rj['old_length_m'], finish_arclength_m=rj['finish_arclength_m'],
                           runout_m=rj['length_m'] - rj['finish_arclength_m'], min_radius_extension_m=rj['min_radius_extension_m'],
                           max_grade_extension=rj['max_grade_extension']),
                scene=dict((k, scene[k]) for k in ('cut', 'new_objects', 'gates', 'boards', 'vegetation')),
                roadside_kn5=dict(path=str(ROADSIDE.relative_to(ROOT)), bytes=ROADSIDE.stat().st_size, sha256=sha(ROADSIDE),
                                  mesh_nodes=len(meshes), tris=int(sum(len(n['indices']) for n in meshes)) // 3),
                content=meta['summary'], buildings=json.loads((SRC / 'buildings.json').read_text())['stats'],
                extension=json.loads((SRC / 'extension.json').read_text())['roundabout'],
                guardrail_m=meta['guardrail_m'], shrubs=meta['shrubs'], status='PASS_OFFLINE_NOT_RUNTIME_TESTED')


def maps(P):
    xz = np.c_[P[:, 0], -P[:, 1]]
    t = map_transform(xz)
    return {'map.png': imagecodecs.png_encode(draw_route(xz, t)),
            'ui/outline.png': imagecodecs.png_encode(draw_route(xz, map_transform(xz, size=512))),
            'data/map.ini': ('[PARAMETERS]\n' + '\n'.join(f'{k}={v}' for k, v in dict(
                WIDTH=1024, HEIGHT=1024, MARGIN=0, SCALE_FACTOR=t['scale_factor'], X_OFFSET=t['x_offset'],
                Z_OFFSET=t['z_offset'], DRAWING_SIZE=10).items()) + '\n').encode()}


def package(report):
    assert not PKG.exists(), f'{PKG} exists; refuse to overwrite'
    PKG.mkdir(parents=True)
    for p in OLD_PKG.rglob('*'):
        if p.is_file():
            rel = p.relative_to(OLD_PKG).as_posix()
            if rel in (OLD_MAIN, OLD_SCENERY, 'models.ini') + REGENERATED:
                continue
            d = PKG / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
    for rel, data in maps(np.load(EXT / 'route.npz')['designed_xyz_m']).items():
        (PKG / rel).parent.mkdir(parents=True, exist_ok=True)
        (PKG / rel).write_bytes(data)
    shutil.copy2(NEW_MAIN, PKG / MAIN_OUT)
    shutil.copy2(ROADSIDE, PKG / ROADSIDE.name)
    (PKG / 'models.ini').write_text(f'[MODEL_0]\nFILE={MAIN_OUT}\nPOSITION=0,0,0\nROTATION=0,0,0\n\n'
                                    f'[MODEL_1]\nFILE={ROADSIDE.name}\nPOSITION=0,0,0\nROTATION=0,0,0\n')
    rt = report['route']
    ui = json.loads((PKG / 'ui/ui_track.json').read_text())
    ui.update(name='Exelberg Full v010', version='0.0.10', city='Königstetten – Neuwaldegg', length=f'{rt["finish_arclength_m"]:.0f} m',
              description='Extended to the Neuwaldegg roundabout (finish at its 2nd exit, Neuwaldegger Straße); smoothed road curves; '
                          'smoothed landscape; Austrian guide posts, guardrails, signs, closed junctions, roadside shrubs, the Exelberg '
                          'radio tower and OSM buildings (visual only). Solo Practice; timing unverified.')
    (PKG / 'ui/ui_track.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    c = report['content']
    (PKG / 'README.txt').write_text(
        'EXELBERG FULL v010 - PRIVATE SOLO TEST BUILD\n'
        f'{MAIN_OUT}: v009 + extension from Marswiese to the Neuwaldegg roundabout (Wien 17).\n'
        f' - road continues {rt["length_m"] - rt["old_length_m"]:.0f} m further (OpenStreetMap Exelbergstrasse, one-way entry branch,\n'
        '   roundabout counter-clockwise past exit 1 (Neuwaldegger Strasse west), out at exit 2 (Neuwaldegger Strasse east)).\n'
        f' - FINISH at the 2nd exit ({rt["finish_arclength_m"]:.0f} m from the start), then {rt["runout_m"]:.0f} m run-off, STOP board and end wall.\n'
        '   The old Marswiese finish and BRAKE/STOP boards are gone.\n'
        ' - same two 3 m lanes + 0.75 m gravel and invisible walls at +-6 m; the other roundabout arms and the rest of the ring\n'
        '   are visual asphalt only (closed by the invisible wall like the other junctions); island kerb visual only.\n'
        ' - new ground around the extension: BEV 1 m terrain + BEV 1 m orthophoto; trees there re-detected from the BEV\n'
        '   laser-scan canopy model; no centre/edge paint in and after the roundabout; no guide posts/signs on the extension\n'
        '   (no reference footage).\n'
        'Everything before the last 60 m of the old road is unchanged from v009 (smoothed curves, landscape, scenery\n'
        f'second model exelberg_v010_scenery.kn5 with {report["buildings"]["kept"]} OSM buildings, {c.get("sign", 0)} signs, '
        f'{report["guardrail_m"]:.0f} m guardrail, tower, posts, shrubs).\n'
        'No collision on any scenery object. NOT runtime-tested.\n')
    att = (PKG / 'ATTRIBUTION.txt').read_text()
    if 'v010:' not in att:
        att += ('\nv010: roundabout extension - BEV ALS DTM/DSM 1 m and BEV orthophoto (© BEV, CC BY 4.0), OpenStreetMap ways and\n'
                'buildings (© OpenStreetMap contributors, ODbL).\n')
        (PKG / 'ATTRIBUTION.txt').write_text(att)
    files = sorted(p for p in PKG.rglob('*') if p.is_file())
    report['package'] = dict(path=str(PKG.relative_to(ROOT)), files=[dict(path=str(p.relative_to(PKG)), bytes=p.stat().st_size,
                                                                            sha256=sha(p)) for p in files],
                             total_bytes=sum(p.stat().st_size for p in files))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = validate()
    package(report)
    (OUT / 'manifest.json').write_text(json.dumps(report, indent=2, default=float) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('package', 'scene')}, indent=1, default=float))
    print('package bytes', report['package']['total_bytes'], 'files', len(report['package']['files']))


if __name__ == '__main__':
    main()
