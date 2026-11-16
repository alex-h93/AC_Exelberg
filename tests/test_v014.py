"""Offline checks for v013 (roundabout sign clearance) and v014 (textures + 3D verge grass); no game."""
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
P_ = ROOT / 'data/processed'
B = ROOT / 'build'
MODES = {'forward': ('exelberg_full', 'exelberg', 'extension_v010', 'grass_v014', 'scenery_v013'),
         'reverse': ('exelberg_reverse', 'exelberg_reverse', 'extension_v011r', 'grass_v014r', 'scenery_v013r')}


def man(v, mode):
    return json.loads((P_ / f'full_track_package_{v}_{mode}/manifest.json').read_text())


def test_v013_urban_signs_clear_of_the_road():
    from v013_scenery import centre_offset
    from types import SimpleNamespace
    for mode, (_, _, ext, _, scn) in MODES.items():
        R = SimpleNamespace(p=np.load(P_ / ext / 'skin_v010.npz')['designed_xyz_m'].astype(float))
        signs = [p for p in json.loads((P_ / scn / 'placements.json').read_text()) if p['kind'] == 'urban_sign']
        assert len(signs) == 21
        for p in signs:
            assert abs(centre_offset(R, np.array(p['xy']))[0]) >= 3.95 - 0.05, (mode, p['note'])


def test_kn5_header_round_trip():
    import kn5_header as K
    d = (B / 'full_track_v013/exelberg_full_v013/exelberg_v013_scenery.kn5').read_bytes()
    h = K.read(d)
    assert K.write(h, d[h['node_offset']:]) == d


def test_v014_dds_are_block_compressed_with_mips():
    tm = json.loads((P_ / 'textures_v014/manifest.json').read_text())
    for k, v in tm.items():
        if not (isinstance(v, dict) and 'path' in v):
            continue
        b = (ROOT / v['path']).read_bytes()
        h, w, mips = struct.unpack_from('<2I', b, 12) + struct.unpack_from('<I', b, 28)
        fmt = b[84:88].decode()
        assert fmt in ('DXT1', 'DXT5') and h == w and mips == int(np.log2(w)) + 1, k
        size = sum(max(1, (w >> i) // 4) ** 2 * (8 if fmt == 'DXT1' else 16) for i in range(mips))
        assert len(b) == 128 + size, k


def test_v014_packages():
    import kn5_header as K
    for mode, (track, sc, *_rest) in MODES.items():
        m = man('v014', mode)
        pkg = ROOT / m['package']['path']
        assert len(m['package']['files']) == 19
        assert m['main_kn5']['node_section_identical'] and m['scenery_kn5']['node_section_identical']
        h = K.read((pkg / f'{track}_v014.kn5').read_bytes())
        mats = {x['name']: x for x in h['materials']}
        assert mats['V002_asphalt']['shader'] == 'ksPerPixelMultiMap_NMDetail'
        assert sum(x['shader'] == 'ksPerPixelMultiMap_NMDetail' for x in h['materials']) == 29
        names = {t['name'] for t in h['textures']}
        assert {b[2] for x in h['materials'] for b in x['bindings']} == names
        assert 'v002_asphalt.dds' not in names and 'v014_asphalt.dds' in names
        mi = (pkg / 'models.ini').read_text()
        for f in (f'{track}_v014.kn5', f'{sc}_v014_scenery.kn5', f'{sc}_v014_grass.kn5'):
            assert f'FILE={f}' in mi and (pkg / f).exists()
        # meshes untouched: node section of the main KN5 equals v013 apart from the 4-byte-aligned root name
        old = (B / f'full_track_v013/{track}_v013/{track}_v013.kn5').read_bytes()
        ho = K.read(old)
        new_nodes = (pkg / f'{track}_v014.kn5').read_bytes()[h['node_offset']:]
        assert new_nodes == old[ho['node_offset']:].replace(f'{track}_v013'.encode(), f'{track}_v014'.encode())


def test_v014_grass_is_on_grass_and_visual_only():
    from v014_grass import Skin
    from full_track_v004_kn5 import parse
    rng = np.random.default_rng(0)
    for mode, (_, sc, ext, gdir, _) in MODES.items():
        meta = json.loads((P_ / gdir / 'objects.json').read_text())
        assert 80000 < meta['stats']['clumps'] < 120000
        assert all(o['lod_out'] <= 80 and not o['cast_shadows'] for o in meta['objects'])
        g = np.load(P_ / gdir / 'geometry.npz')
        names = [o['name'] for o in meta['objects']]
        base = np.vstack([(g[f'{n}__v'][0::8] + g[f'{n}__v'][1::8]) / 2 for n in rng.choice(names, 40, replace=False)])  # clump centre
        sk = np.load(P_ / ext / 'skin_v010.npz')
        role, z = Skin(sk['vertices'], sk['triangles'], sk['roles']).query(base[:, :2].astype(float))
        assert (role == 'GRASS').all() and np.allclose(base[:, 2], z - 0.04, atol=0.01)
        kn = parse((ROOT / f'exports/full_track_v014/{sc}_v014_grass.kn5').read_bytes(), max_file=256 * 2 ** 20,
                   max_nodes=16384, max_texture=32 * 2 ** 20, max_materials=128, max_textures=128)
        assert not any(n['name'][:1].isdigit() for n in kn['nodes'])
        assert [m['shader'] for m in kn['materials']] == ['ksPerPixelAT']
