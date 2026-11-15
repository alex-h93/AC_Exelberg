#!/usr/bin/env python3
"""Validate exports/full_track_v004 KN5 against v003 and assemble build/full_track_v004/.

Checks (offline, independent KN5 reader):
  * every v003 physics node (name starting with '1') exists in v004 with identical
    flags, vertices and indices  -> collision geometry unchanged
  * all v003 AC helper nodes (spawn/timing) have identical matrices
  * vegetation nodes are non-physics (VIS_ prefix), LOD ranges as designed
  * texture/material bindings resolve; counts and sizes reported
Package: copies v003 data/ai/map files, new KN5, ui text, README, ATTRIBUTION and
extension/ext_config.ini. Never touches build/full_track_v003 or the game folder.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_track_v004_kn5 import parse  # noqa: E402
from validate_kn5 import bounded_read  # noqa: E402

TRACK = 'exelberg_full_v004'
KN5 = ROOT / f'exports/full_track_v004/{TRACK}.kn5'
OLD_KN5 = ROOT / 'exports/full_track_v003/exelberg_full_v003.kn5'
OLD_PKG = ROOT / 'build/full_track_v003/exelberg_full_v003'
PKG = ROOT / 'build/full_track_v004' / TRACK
SRC = ROOT / 'data/processed/full_track_package_v004_src'
OUT = ROOT / 'data/processed/full_track_package_v004'
CAP = 256 * 1024 * 1024


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(path):
    return parse(bounded_read(path, max_file=CAP), max_file=CAP, max_nodes=16384,
                 max_texture=32 * 1024 * 1024, max_materials=128, max_textures=128)


def validate():
    new, old = load(KN5), load(OLD_KN5)
    nn = {n['name']: n for n in new['nodes']}
    res = dict(kn5=dict(path=str(KN5.relative_to(ROOT)), bytes=KN5.stat().st_size, sha256=sha(KN5)))
    phys = [n for n in old['nodes'] if n['kind'] == 2 and n['name'].startswith('1')]
    for o in phys:
        n = nn.get(o['name'])
        assert n is not None, f'missing physics node {o["name"]}'
        for k in ('active', 'visible', 'transparent', 'cast_shadows', 'renderable', 'layer'):
            assert n[k] == o[k], f'{o["name"]} flag {k} changed'
        assert np.array_equal(n['vertices'], o['vertices']), f'{o["name"]} vertices changed'
        assert np.array_equal(n['indices'], o['indices']), f'{o["name"]} indices changed'
    helpers = [n for n in old['nodes'] if n['kind'] == 1 and n['name'].startswith('AC_')]
    for o in helpers:
        assert np.array_equal(nn[o['name']]['matrix'], o['matrix']), f'helper {o["name"]} moved'
    new_phys = [n['name'] for n in new['nodes'] if n['kind'] == 2 and n['name'].startswith('1')]
    assert sorted(new_phys) == sorted(o['name'] for o in phys), 'physics node set changed'
    veg = [n for n in new['nodes'] if n['kind'] == 2 and n['name'].startswith('VIS_TREE_')]
    lods = {}
    for n in veg:
        key = n['name'].split('_')[2]
        lods.setdefault(key, set()).add(tuple(np.round(n['lod_sphere'][:2], 1)))
    mats = {m['name']: m for m in new['materials']}
    ortho = [m for m in new['materials'] if m['name'].startswith('V004_ortho_')]
    assert len(ortho) == 26 and all(m['shader'] == 'ksPerPixelMultiMap' for m in ortho)
    meshes = [n for n in new['nodes'] if n['kind'] == 2]
    res.update(physics_nodes_identical=len(phys), helpers_identical=[h['name'] for h in helpers],
               vegetation_nodes=len(veg), vegetation_tris=int(sum(len(n['indices']) for n in veg)),
               vegetation_lod_ranges={k: sorted([float(a), float(b)] for a, b in v) for k, v in lods.items()},
               mesh_nodes=len(meshes), total_tris=int(sum(len(n['indices']) for n in meshes)),
               max_vertices_per_mesh=int(max(len(n['vertices']) for n in meshes)),
               materials=len(new['materials']), textures=len(new['textures']),
               texture_bytes=int(sum(len(t['data']) for t in new['textures'])),
               foliage_shader=mats['V004_foliage']['shader'], foliage_alpha_tested=bool(mats['V004_foliage']['alpha']),
               ortho_detail=[dict(name=m['name'], bindings=[b[0] for b in m['bindings']],
                                  detailUVMultiplier=float(m['properties'].get('detailUVMultiplier', [0])[0])) for m in ortho[:2]],
               status='PASS_OFFLINE_NOT_RUNTIME_TESTED')
    return res, [m['name'] for m in ortho]


def package(report, ortho_names):
    assert not PKG.exists(), f'{PKG} exists; refuse to overwrite'
    PKG.mkdir(parents=True)
    shutil.copy2(KN5, PKG / f'{TRACK}.kn5')
    for rel in ('data/surfaces.ini', 'data/map.ini', 'data/lighting.ini', 'ai/fast_lane.ai', 'ai/pit_lane.ai',
                'map.png', 'ui/outline.png'):
        (PKG / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OLD_PKG / rel, PKG / rel)
    (PKG / 'models.ini').write_text(f'[MODEL_0]\nFILE={TRACK}.kn5\nPOSITION=0,0,0\nROTATION=0,0,0\n')
    ui = json.loads((OLD_PKG / 'ui/ui_track.json').read_text())
    ui.update(name='Exelberg Full v004 (vegetation)', version='0.0.4',
              description='v003 road/collision unchanged; CHM-placed summer forest (3D near road, impostors further), '
                          'detail-textured ground, optional CSP GrassFX. Solo Practice; timing unverified.')
    (PKG / 'ui/ui_track.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    prev = ROOT / 'data/processed/full_track_scene_v004/driver.png'
    shutil.copy2(prev if prev.exists() else OLD_PKG / 'ui/preview.png', PKG / 'ui/preview.png')
    ext = (SRC / 'extension/ext_config.ini').read_text().replace('GRASS_MATERIALS = V004_ortho_?', 'GRASS_MATERIALS = ' + ', '.join(ortho_names))
    (PKG / 'extension').mkdir()
    (PKG / 'extension/ext_config.ini').write_text(ext)
    (PKG / 'README.txt').write_text(
        'EXELBERG FULL v004 (vegetation) - PRIVATE SOLO TEST BUILD\n'
        'Road, gravel, ground skin, invisible walls (+-6 m), posts, spawn and finish fixture are\n'
        'byte-identical to v003 (checked offline). Only visuals changed:\n'
        f' - {report["vegetation_nodes"]} vegetation meshes, {report["vegetation_tris"]:,} triangles. Trees are placed at\n'
        '   canopy-height maxima from BEV laser data (DSM-DTM), so positions/heights follow reality;\n'
        '   species are a plausible beech/oak/conifer mix, NOT surveyed. 3D trees within ~45 m of the\n'
        '   road (visible to 180 m, then impostors), impostor trees to ~195 m (visible to 1.5 km).\n'
        ' - Ground: orthophoto x tiling grass detail (ksPerPixelMultiMap, mipmapped textures).\n'
        ' - extension/ext_config.ini: optional CSP GrassFX on the ground materials (untested values).\n'
        'NOT runtime-tested: look, LOD popping, foliage shimmer, performance, VR. v003 collision\n'
        'runtime status still applies (not proven). Leaf/bark/grass textures: ambientCG CC0.\n')
    att = (OLD_PKG / 'ATTRIBUTION.txt').read_text()
    (PKG / 'ATTRIBUTION.txt').write_text(att + '\nv004: BEV ALS DSM/DTM (CC BY 4.0) canopy height for tree placement; '
                                         'ambientCG textures LeafSet014/016/019/024, Bark011/012/014, Grass005 (CC0 1.0).\n')
    files = sorted(p for p in PKG.rglob('*') if p.is_file())
    report['package'] = dict(path=str(PKG.relative_to(ROOT)), files=[dict(path=str(p.relative_to(PKG)), bytes=p.stat().st_size,
                                                                            sha256=sha(p)) for p in files],
                             total_bytes=sum(p.stat().st_size for p in files))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report, ortho = validate()
    package(report, ortho)
    (OUT / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'package'}, indent=2))
    print('package bytes', report['package']['total_bytes'], 'files', len(report['package']['files']))


if __name__ == '__main__':
    main()
