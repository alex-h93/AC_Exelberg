#!/usr/bin/env python3
"""Validate the v007 KN5s and assemble build/full_track_v007/exelberg_full_v007/.

v007 = v004 package files + a RE-EXPORTED main KN5 (build_full_track_v007.py: spawn moved 25 m -> 10 m,
v003 posts removed; every physics node (leading digit) must be identical to v004's) + the visual-only
exelberg_v007_scenery.kn5 (Austrian guide posts, SVG chevrons, pitched roofs) via models.ini MODEL_1.
Checks (offline):
  * v004 main KN5 sha256 equals the v004 package manifest
  * scenery KN5: no physics-style node names (leading digit), no AC_ helpers, names unique
    against the main KN5, every mesh node visible/renderable, materials/textures resolve
Never touches build/full_track_v004 or the game folder.
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

TRACK = 'exelberg_full_v007'
OLD_PKG = ROOT / 'build/full_track_v004/exelberg_full_v004'
OLD_MAN = ROOT / 'data/processed/full_track_package_v004/manifest.json'
MAIN = 'exelberg_full_v004.kn5'  # source name in the v004 package
MAIN_OUT = f'{TRACK}.kn5'
NEW_MAIN = ROOT / f'exports/full_track_v007/{TRACK}.kn5'  # AC reported 'TRACK NOT FOUND' without a KN5 named after the folder
ROADSIDE = ROOT / 'exports/full_track_v007/exelberg_v007_scenery.kn5'
PKG = ROOT / 'build/full_track_v007' / TRACK
OUT = ROOT / 'data/processed/full_track_package_v007'
SRC = ROOT / 'data/processed/scenery_v007'
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


def validate():
    old = json.loads(OLD_MAN.read_text())
    main_sha = sha(OLD_PKG / MAIN)
    assert main_sha == old['kn5']['sha256'], 'v004 main KN5 differs from its manifest'
    rs = load(ROADSIDE)
    names = [n['name'] for n in rs['nodes']]
    assert len(names) == len(set(names)), 'duplicate node names in roadside KN5'
    assert not any(n[:1].isdigit() for n in names), 'physics-style node name in roadside KN5'
    assert not any(n.startswith('AC_') for n in names), 'AC helper in roadside KN5'
    old_main = load(OLD_PKG / MAIN)
    main = load(NEW_MAIN)
    phys = lambda k: {n['name']: n for n in k['nodes'] if n['name'][:1].isdigit()}
    po, pn = phys(old_main), phys(main)
    assert po.keys() == pn.keys(), 'physics node set differs from v004'
    for nm in po:
        assert np.array_equal(po[nm]['vertices'], pn[nm]['vertices']) and np.array_equal(po[nm]['indices'], pn[nm]['indices']), nm
    assert not any(n['name'].startswith('VIS_POST') for n in main['nodes']), 'old posts still in main KN5'
    sp = {n['name']: n for n in main['nodes'] if n['name'].startswith('AC_')}
    so = {n['name']: n for n in old_main['nodes'] if n['name'].startswith('AC_')}
    assert sp.keys() == so.keys(), 'AC helper set changed'
    moved = {k: float(np.linalg.norm(np.asarray(sp[k]['matrix'], float).reshape(4, 4)[3, :3] - np.asarray(so[k]['matrix'], float).reshape(4, 4)[3, :3])) for k in sp}
    assert all(14 < moved[k] < 16 for k in ('AC_START_0', 'AC_PIT_0', 'AC_HOTLAP_START_0')), moved
    assert moved['AC_TIME_0_L'] < 1e-4 and moved['AC_TIME_0_R'] < 1e-4, moved
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
    return dict(main_kn5=dict(file=MAIN_OUT, path=str(NEW_MAIN.relative_to(ROOT)), sha256=sha(NEW_MAIN), v004_sha256=main_sha,
                              physics_nodes_identical_to_v004=len(po), spawn_moved_m=moved),
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
            if p.name == MAIN:
                continue
            d = PKG / p.relative_to(OLD_PKG)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
    shutil.copy2(NEW_MAIN, PKG / MAIN_OUT)
    shutil.copy2(ROADSIDE, PKG / ROADSIDE.name)
    (PKG / 'models.ini').write_text(f'[MODEL_0]\nFILE={MAIN_OUT}\nPOSITION=0,0,0\nROTATION=0,0,0\n\n'
                                    f'[MODEL_1]\nFILE={ROADSIDE.name}\nPOSITION=0,0,0\nROTATION=0,0,0\n')
    ui = json.loads((PKG / 'ui/ui_track.json').read_text())
    ui.update(name='Exelberg Full v007', version='0.0.7',
              description='v004 road/collision/vegetation unchanged (start 15 m earlier); Austrian guide posts, guardrails, signs, closed junctions, '
                          'roadside shrubs, the Exelberg radio tower and OSM buildings (visual only). Solo Practice; timing unverified.')
    (PKG / 'ui/ui_track.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    prev = SRC / 'previews/marswiese_aerial.png'
    if prev.exists():
        shutil.copy2(prev, PKG / 'ui/preview.png')
    c = report['content']
    (PKG / 'README.txt').write_text(
        'EXELBERG FULL v007 - PRIVATE SOLO TEST BUILD\n'
        f'{MAIN_OUT}: v004 objects re-exported, physics geometry identical (road, gravel, ground, invisible walls\n'
        '+-6 m, finish fixture, trees); spawn 15 m earlier; old v003 posts removed. Visual-only second model\n'
        'exelberg_v007_scenery.kn5 (models.ini MODEL_1), additionally Austrian guide posts every 33 m:\n'
        f' - {report["guardrail_m"]:.0f} m Austrian-style W-profile guardrail ({c.get("guardrail", 0)} runs) placed from a\n'
        '   roadside inventory; set 5.9 m from the centreline so the existing 6 m invisible wall\n'
        '   is where the rail is (the real rails stand closer to the asphalt). Lengths are estimates.\n'
        f' - {c.get("sign", 0)} signs, inner plate edge 4.4 m from the centreline: yellow/black and red curve boards\n'
        '   (red: after an Austrian sample SVG, white chevron on red), speed limits, warning, priority, town signs (black on white, blue frame),\n'
        '   direction/info boards. Simplified drawings, not certified\n'
        '   sign artwork; some values/texts were unreadable and are marked assumed in placements.json.\n'
        f' - {c.get("junction", 0)} short side-road stubs from OpenStreetMap (no barriers; the invisible wall keeps\n'
        f'   cars on the route); {c.get("parking_pad", 0)} gravel parking/pull-off pads.\n'
        f' - {report["buildings"]["posts"]} Austrian guide posts (Leitpflock, after a user photo) at the v003 positions.\n'
        f' - {report["shrubs"]} edge shrubs 6.6-10 m from the road in forest sections.\n'
        ' - Richtfunkstation Exelberg, 109 m (position OSM/Wikipedia/laser scan; shape approximated).\n'
        f' - {c.get("building", 0)} buildings from OpenStreetMap footprints, heights from the BEV laser-scan surface\n'
        '   model; pitched roofs (cross-gables on L-shaped houses), generic facades/roofs (approximations,\n'
        '   not surveyed models).\n'
        'No collision on any new object. NOT runtime-tested.\n')
    att = (PKG / 'ATTRIBUTION.txt').read_text()
    (PKG / 'ATTRIBUTION.txt').write_text(att + '\nv005/v006: junctions and tower position from OpenStreetMap (ODbL); tower height\n'
                                         'Wikipedia "Richtfunkstation Exelberg"; gravel ambientCG Gravel023 (CC0 1.0); sign\n'
                                         'graphics drawn procedurally for this project. Roadside placement approximate, placed by hand.\n'
                                         'v006: building footprints OpenStreetMap contributors (ODbL); building heights\n'
                                         'derived from BEV ALS DSM/DTM (CC BY 4.0); facade/roof textures procedural.\n')
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
