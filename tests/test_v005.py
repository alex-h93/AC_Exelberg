"""Offline checks for v005 roadside (no Blender, no game)."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SRC = ROOT / 'data/processed/roadside_v005'


def placements():
    return json.loads((SRC / 'placements.json').read_text())


def test_atlas_cells_inside_texture():
    from v005_textures import CELLS, N, uv_rect
    for name, (c, r, w, h) in CELLS.items():
        assert 0 <= c and c + w <= N and 0 <= r and r + h <= N, name
        u0, v0, u1, v1 = uv_rect(name)
        assert 0 <= u0 < u1 <= 1 and 0 <= v0 < v1 <= 1


def test_cells_do_not_overlap():
    from v005_textures import CELLS, N
    grid = np.zeros((N, N), int)
    for c, r, w, h in CELLS.values():
        grid[r:r + h, c:c + w] += 1
    assert grid.max() == 1


def test_chevrons_on_outer_side_pointing_into_bend():
    for p in placements():
        if p['kind'] == 'sign' and p['cell'].startswith('chev'):
            # left-side board -> right-hand bend -> arrow '>' (R); right-side board -> arrow '<' (L)
            assert p['cell'].endswith('R') == (p['side'] == 1), p


def test_no_physics_names_and_geometry_finite():
    meta = json.loads((SRC / 'objects.json').read_text())
    g = np.load(SRC / 'geometry.npz')
    for o in meta['objects']:
        assert o['name'].startswith('V005_')
        v, tri = g[o['name'] + '__v'], g[o['name'] + '__tri']
        assert np.isfinite(v).all() and tri.min() >= 0 and tri.max() < len(v)
        a = np.linalg.norm(np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]]), axis=1)
        assert (a > 1e-9).all(), o['name']
        assert o['verts'] < 200000


def test_guardrails_and_barriers_beyond_drivable_zone():
    for p in placements():
        if p['kind'] == 'guardrail':
            assert p['lateral_m'] >= 5.8
        if p['kind'] == 'junction':
            assert p['stub_length_m'] > 8


def test_tower_position_and_height():
    t = [p for p in placements() if p['kind'] == 'tower'][0]
    assert t['height_m'] == 109.0
    x, y = t['xy_local']
    assert abs(x - 2855) < 20 and abs(y + 2095) < 20


def test_package_manifest_main_kn5_unchanged():
    m = json.loads((ROOT / 'data/processed/full_track_package_v005/manifest.json').read_text())
    old = json.loads((ROOT / 'data/processed/full_track_package_v004/manifest.json').read_text())
    assert m['main_kn5']['sha256'] == old['kn5']['sha256']
    files = {f['path'] for f in m['package']['files']}
    assert {'exelberg_full_v005.kn5', 'exelberg_v005_roadside.kn5', 'models.ini'} <= files
    ini = (ROOT / 'build/full_track_v005/exelberg_full_v005/models.ini').read_text()
    assert 'MODEL_1' in ini and 'exelberg_v005_roadside.kn5' in ini


import unittest  # noqa: E402


class V005(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V005, _name, (lambda f: lambda self: f())(_fn))
