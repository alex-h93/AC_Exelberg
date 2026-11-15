#!/usr/bin/env python3
"""Validate the v009 KN5s and assemble build/full_track_v009/exelberg_full_v009/.

v009 = v008 + smoothed road curves (scripts/v009_centerline.py, v009_field.py, build_full_track_v009.py).
Checks vs the v008 main KN5 (offline): identical node set; every physics triangle of v008, moved by the v009
field, matches exactly one v009 triangle (corners within 3 mm; heights unchanged); road vertices therefore lie exactly on the new ribbon; spawns/gates moved < 5 cm.
Scenery exelberg_v009_scenery.kn5 via models.ini MODEL_1 (same checks as v008).
Never touches build/full_track_v008 or the game folder.
"""

import hashlib
import json
import shutil

import numpy as np
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_track_v004_kn5 import parse  # noqa: E402
from validate_kn5 import bounded_read  # noqa: E402
from v009_field import Field  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

TRACK = 'exelberg_full_v009'
OLD_PKG = ROOT / 'build/full_track_v008/exelberg_full_v008'
OLD_MAN = ROOT / 'data/processed/full_track_package_v008/manifest.json'
MAIN = 'exelberg_full_v008.kn5'  # source name in the v008 package
OLD_SCENERY = 'exelberg_v008_scenery.kn5'
MAIN_OUT = f'{TRACK}.kn5'
NEW_MAIN = ROOT / f'exports/full_track_v009/{TRACK}.kn5'  # AC reported 'TRACK NOT FOUND' without a KN5 named after the folder
ROADSIDE = ROOT / 'exports/full_track_v009/exelberg_v009_scenery.kn5'
PKG = ROOT / 'build/full_track_v009' / TRACK
OUT = ROOT / 'data/processed/full_track_package_v009'
SRC = ROOT / 'data/processed/scenery_v009'
CAP = 256 * 1024 * 1024


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return parse(bounded_read(path, max_file=CAP), max_file=CAP, max_nodes=16384,
                 max_texture=32 * 1024 * 1024, max_materials=128, max_textures=128)


def canon(n, xy_key=False):
    """Triangles as (n,3,3) positions rounded to 1 mm, rotated so the smallest vertex comes first (winding kept),
    rows sorted -> comparable regardless of vertex sharing/order."""
    P = np.round(n['vertices'][:, :3].astype(np.float64), 3)
    T = P[n['indices'].reshape(-1, 3)]
    K = T[..., [0, 2]] if xy_key else T  # KN5 axes: x, up, z (= -Blender y)
    _, ids = np.unique(K.reshape(-1, K.shape[-1]), axis=0, return_inverse=True)
    ids = ids.reshape(-1, 3)
    r = ids.argmin(1)
    T = np.stack([T[np.arange(len(T)), (r + k) % 3] for k in range(3)], 1)
    K = T[..., [0, 2]] if xy_key else T
    o = np.lexsort(K.reshape(len(K), -1).T[::-1])
    return T[o]


def validate():
    old = json.loads(OLD_MAN.read_text())
    main_sha = sha(OLD_PKG / MAIN)
    assert main_sha == old['main_kn5']['sha256'], 'v008 main KN5 differs from its manifest'
    rs = load(ROADSIDE)
    names = [n['name'] for n in rs['nodes']]
    assert len(names) == len(set(names)), 'duplicate node names in roadside KN5'
    assert not any(n[:1].isdigit() for n in names), 'physics-style node name in roadside KN5'
    assert not any(n.startswith('AC_') for n in names), 'AC helper in roadside KN5'
    old_main = load(OLD_PKG / MAIN)
    main = load(NEW_MAIN)
    assert [n['name'] for n in old_main['nodes']][1:] == [n['name'] for n in main['nodes']][1:], 'node list differs from v008'
    assert main['nodes'][0]['name'] == TRACK, 'root node must be named after the track folder'
    c = np.load(ROOT / 'data/processed/road_v009/centerline.npz')
    F = Field(c['old_designed_xyz_m'], c['new_designed_xyz_m'])
    phys = lambda k: {n['name']: n for n in k['nodes'] if n['name'][:1].isdigit()}
    po, pn = phys(old_main), phys(main)
    err, shift, dz, nv = 0.0, {}, 0.0, 0
    for nm in po:
        a, b = po[nm], pn[nm]
        ta = a['vertices'][:, :3].astype(float)[a['indices'].reshape(-1, 3)]  # (n,3,3) KN5 x, up, z=-y
        tb = b['vertices'][:, :3].astype(float)[b['indices'].reshape(-1, 3)]
        assert ta.shape == tb.shape, f'{nm}: triangle count differs'
        xy = np.c_[ta[..., 0].ravel(), -ta[..., 2].ravel()]
        ex = ta.copy()
        mv = F.displace(xy)
        ex[..., 0], ex[..., 2] = mv[:, 0].reshape(-1, 3), -mv[:, 1].reshape(-1, 3)  # v008 triangles moved by the field
        _, j = cKDTree(tb.mean(1)).query(ex.mean(1))
        assert len(np.unique(j)) == len(j), f'{nm}: triangle matching not one-to-one'
        m = tb[j]
        d = np.linalg.norm(ex[:, :, None, :] - m[:, None, :, :], axis=-1).min(-1)  # each expected corner -> matched triangle
        err = max(err, float(d.max()))
        dz = max(dz, float(np.abs(np.sort(ex[..., 1], 1) - np.sort(m[..., 1], 1)).max()))
        kind = nm.split('_')[0]
        shift[kind] = max(shift.get(kind, 0.0), float(np.linalg.norm(mv - xy, axis=1).max()))
        nv += ta.shape[0]
    assert dz < 1e-4, f'physics heights changed by {dz}'
    assert err < 3e-3, f'physics XY deviates from the v009 field by {err}'
    assert not any(n['name'].startswith('VIS_POST') for n in main['nodes']), 'old posts still in main KN5'
    sp = {n['name']: n for n in main['nodes'] if n['name'].startswith('AC_')}
    so = {n['name']: n for n in old_main['nodes'] if n['name'].startswith('AC_')}
    assert sp.keys() == so.keys(), 'AC helper set changed'
    moved = {k: float(np.linalg.norm(np.asarray(sp[k]['matrix'], float).reshape(4, 4)[3, :3] - np.asarray(so[k]['matrix'], float).reshape(4, 4)[3, :3])) for k in sp}
    assert all(v < 0.05 for v in moved.values()), moved
    clash = set(names) & {n['name'] for n in main['nodes']}
    assert not clash, f'node names clash with main KN5: {sorted(clash)[:5]}'
    meshes = [n for n in rs['nodes'] if n['kind'] == 2]
    assert all(n['visible'] and n['renderable'] for n in meshes), 'hidden roadside mesh'
    mats = {m['name'] for m in rs['materials']}
    texs = {t['name'] for t in rs['textures']}
    for m in rs['materials']:
        for b in m['bindings']:
            assert b[2] in texs, f'{m["name"]} -> missing texture {b[2]}'
    meta = json.loads((SRC / 'objects.json').read_text())
    lods = sorted({(float(n['lod_sphere'][0]), float(n['lod_sphere'][1])) for n in meshes})
    cl = json.loads((ROOT / 'data/processed/road_v009/summary.json').read_text())
    return dict(main_kn5=dict(file=MAIN_OUT, path=str(NEW_MAIN.relative_to(ROOT)), sha256=sha(NEW_MAIN), v008_sha256=main_sha,
                              physics_nodes_checked=len(po), physics_triangles_checked=nv, triangles_match_v008_moved_by_field=True,
                              max_height_change_m=dz, max_field_error_m=err, max_xy_shift_m_by_kind=shift, helpers_moved_m=moved),
                centerline=dict((k, cl[k]) for k in ('centerline_shift_m', 'curvature_total_variation_4m', 'turn_step_change_deg', 'min_radius_4m_m')),
                roadside_kn5=dict(path=str(ROADSIDE.relative_to(ROOT)), bytes=ROADSIDE.stat().st_size, sha256=sha(ROADSIDE),
                                  mesh_nodes=len(meshes), tris=int(sum(len(n['indices']) for n in meshes)),
                                  materials=sorted(mats), textures=sorted(texs), lod_ranges=lods),
                content=meta['summary'], buildings=json.loads((SRC / 'buildings.json').read_text())['stats'], guardrail_m=meta['guardrail_m'], shrubs=meta['shrubs'],
                status='PASS_OFFLINE_NOT_RUNTIME_TESTED')


def package(report):
    assert not PKG.exists(), f'{PKG} exists; refuse to overwrite'
    PKG.mkdir(parents=True)
    for p in OLD_PKG.rglob('*'):
        if p.is_file():
            if p.name in (MAIN, OLD_SCENERY, 'models.ini'):
                continue
            d = PKG / p.relative_to(OLD_PKG)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
    shutil.copy2(NEW_MAIN, PKG / MAIN_OUT)
    shutil.copy2(ROADSIDE, PKG / ROADSIDE.name)
    (PKG / 'models.ini').write_text(f'[MODEL_0]\nFILE={MAIN_OUT}\nPOSITION=0,0,0\nROTATION=0,0,0\n\n'
                                    f'[MODEL_1]\nFILE={ROADSIDE.name}\nPOSITION=0,0,0\nROTATION=0,0,0\n')
    ui = json.loads((PKG / 'ui/ui_track.json').read_text())
    ui.update(name='Exelberg Full v009', version='0.0.9',
              description='Smoothed road curves (v009); smoothed landscape; Austrian guide posts, guardrails, signs, closed junctions, '
                          'roadside shrubs, the Exelberg radio tower and OSM buildings (visual only). Solo Practice; timing unverified.')
    (PKG / 'ui/ui_track.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    prev = SRC / 'previews/marswiese_aerial.png'
    if prev.exists():
        shutil.copy2(prev, PKG / 'ui/preview.png')
    c = report['content']
    (PKG / 'README.txt').write_text(
        'EXELBERG FULL v009 - PRIVATE SOLO TEST BUILD\n'
        f'{MAIN_OUT}: v008 objects re-exported; road curves smoothed (the OSM centreline was a chord polygon):\n'
        'road, gravel, invisible walls +-6 m, markings and nearby ground/trees moved sideways by up to ~1 m\n'
        '(heights, topology and finish fixture unchanged);\n'
        'landscape smoothed (heights only > 10 m from the road, max 2 m; smooth shading), trees follow the ground;\n'
        'spawn 15 m earlier; old v003 posts removed. Visual-only second model exelberg_v009_scenery.kn5\n'
        '(models.ini MODEL_1), placed along the smoothed road:\n'
        f' - {report["guardrail_m"]:.0f} m Austrian-style W-profile guardrail ({c.get("guardrail", 0)} runs) placed from a\n'
        '   roadside inventory; set 5.9 m from the centreline so the existing 6 m invisible wall\n'
        '   is where the rail is (the real rails stand closer to the asphalt). Lengths are estimates.\n'
        f' - {c.get("sign", 0)} signs, inner plate edge 4.4 m from the centreline: yellow/black and red curve boards\n'
        '   (red: after an Austrian sample SVG, white chevron on red), speed limits, warning, priority, town signs (black on white, blue frame),\n'
        '   direction/info boards. Simplified drawings, not certified\n'
        '   sign artwork; some values/texts were unreadable and are marked assumed in placements.json.\n'
        f' - {c.get("junction", 0)} short side-road stubs from OpenStreetMap (no barriers; the invisible wall keeps\n'
        f'   cars on the route); {c.get("parking_pad", 0)} gravel parking/pull-off pads.\n'
        f' - {report["buildings"]["posts"]} Austrian guide posts (Leitpflock, after a user photo), v003 positions moved with the road.\n'
        f' - {report["shrubs"]} edge shrubs 6.6-10 m from the road in forest sections.\n'
        ' - Richtfunkstation Exelberg, 109 m (position OSM/Wikipedia/laser scan; shape approximated).\n'
        f' - {c.get("building", 0)} buildings from OpenStreetMap footprints, heights from the BEV laser-scan surface\n'
        '   model; pitched roofs (cross-gables on L-shaped houses), generic facades/roofs (approximations,\n'
        '   not surveyed models).\n'
        'No collision on any new object. NOT runtime-tested.\n')
    att = (PKG / 'ATTRIBUTION.txt').read_text()  # v008 package text already lists all sources
    assert 'v006: building footprints' in att
    files = sorted(p for p in PKG.rglob('*') if p.is_file())
    report['package'] = dict(path=str(PKG.relative_to(ROOT)), files=[dict(path=str(p.relative_to(PKG)), bytes=p.stat().st_size,
                                                                            sha256=sha(p)) for p in files],
                             total_bytes=sum(p.stat().st_size for p in files))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = validate()
    package(report)
    (OUT / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'package'}, indent=2))
    print('package bytes', report['package']['total_bytes'], 'files', len(report['package']['files']))


if __name__ == '__main__':
    main()
