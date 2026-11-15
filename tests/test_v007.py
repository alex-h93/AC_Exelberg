"""Offline checks for v007 (no Blender, no game)."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SRC = ROOT / 'data/processed/scenery_v007'


def placements():
    return json.loads((SRC / 'placements.json').read_text())


def cell(name):
    import v007_textures  # noqa: F401
    from v005_textures import CELLS, C
    c, r, w, h = CELLS[name]
    a = np.asarray(Image.open(ROOT / 'data/processed/textures_v007/previews/signs.png').convert('RGB')).astype(int)
    return a[r * C:(r + h) * C, c * C:(c + w) * C]


def test_red_chevron_matches_svg_layout():
    for d in 'LR':
        a = cell(f'chev_red_{d}')
        white = (a.min(-1) > 220)
        red = (a[..., 0] > 180) & (a[..., 1] < 70)
        assert red.mean() + white.mean() > 0.97
        assert 0.4 < white.mean() < 0.6           # SVG chevron covers ~half the board
        C = a.shape[1]
        mid = white[C // 2]
        # apex at the board edge in the arrow direction, red notch at the opposite edge
        left, right = mid[:C // 2].mean(), mid[C // 2:].mean()
        assert (right > 0.9 and left < 0.1) if d == 'R' else (left > 0.9 and right < 0.1), (d, left, right)


def test_new_atlas_cells_do_not_overlap():
    import v007_textures  # noqa: F401
    from v005_textures import CELLS, N
    g = np.zeros((N, N), int)
    for c, r, w, h in CELLS.values():
        g[r:r + h, c:c + w] += 1
    assert g.max() == 1


def test_posts_at_v003_positions():
    old = json.loads((ROOT / 'data/processed/full_track_scene_v003/posts.json').read_text())['placements']
    gp = [p for p in placements() if p['kind'] == 'guide_posts'][0]
    assert gp['count'] == len(old) > 700


def test_houses_have_pitched_roofs():
    import v006_buildings as B
    for p in placements():
        if p['kind'] == 'building' and p['shape'] == 'flat':
            assert p['osm_type'] in B.SMALL or p['area_m2'] < 30, p


def test_geometry_finite_nondegenerate():
    meta = json.loads((SRC / 'objects.json').read_text())
    g = np.load(SRC / 'geometry.npz')
    for o in meta['objects']:
        assert o['name'].startswith('V007_')
        v, t = g[o['name'] + '__v'].astype(float), g[o['name'] + '__tri']
        assert np.isfinite(v).all() and t.max() < len(v)
        a = np.linalg.norm(np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]), axis=1)
        assert (a > 1e-9).all(), o['name']
        assert o['verts'] < 65000


def test_package_manifest():
    m = json.loads((ROOT / 'data/processed/full_track_package_v007/manifest.json').read_text())
    mk = m['main_kn5']
    assert mk['physics_nodes_identical_to_v004'] > 400
    assert all(14 < mk['spawn_moved_m'][k] < 16 for k in ('AC_START_0', 'AC_PIT_0', 'AC_HOTLAP_START_0'))
    assert mk['spawn_moved_m']['AC_TIME_0_L'] == 0 and mk['spawn_moved_m']['AC_TIME_0_R'] == 0
    files = {f['path'] for f in m['package']['files']}
    assert {'exelberg_full_v007.kn5', 'exelberg_v007_scenery.kn5', 'models.ini'} <= files
    assert not any('v006' in f or 'v005' in f for f in files)


class V007(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V007, _name, (lambda f: lambda self: f())(_fn))
