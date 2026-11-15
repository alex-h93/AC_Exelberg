"""Offline checks for v006 scenery (no Blender, no game)."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SRC = ROOT / 'data/processed/scenery_v006'


def placements():
    return json.loads((SRC / 'placements.json').read_text())


def cell_pixels(name):
    from v005_textures import CELLS, C
    c, r, w, h = CELLS[name]
    a = np.asarray(Image.open(ROOT / 'data/processed/textures_v006/previews/signs.png').convert('RGBA'))
    return a[r * C:(r + h) * C, c * C:(c + w) * C]


def colour_share(px, pred):
    px = px[px[..., 3] > 128][:, :3].astype(int)
    return float(np.mean([pred(*p) for p in px]))


def test_town_sign_white_field_blue_frame_black_text():
    for name in ('town_Koenigstetten', 'town_Scheiblingstein', 'town_end_Koenigstetten', 'town_end_Scheiblingstein'):
        px = cell_pixels(name)
        assert colour_share(px, lambda r, g, b: r > 220 and g > 220 and b > 220) > 0.5, name   # white field
        assert colour_share(px, lambda r, g, b: b > 120 and r < 60) > 0.05, name             # blue frame
        assert colour_share(px, lambda r, g, b: r < 60 and g < 60 and b < 60) > 0.01, name   # black text


def test_red_chevron_white_arrow_on_red():
    for d in 'LR':
        px = cell_pixels(f'chev_red_{d}')
        red = colour_share(px, lambda r, g, b: r > 170 and g < 70 and b < 70)
        white = colour_share(px, lambda r, g, b: r > 220 and g > 220 and b > 220)
        assert red > 0.5 and 0.1 < white < red, (d, red, white)


def test_signs_closer_to_road():
    for p in placements():
        if p['kind'] == 'sign':
            inner = p['lateral_m'] - p['size_m'][0] / 2
            assert abs(inner - 4.4) < 1e-6, p
            assert p['lateral_m'] - p['size_m'][0] / 2 > 4.1  # outside the v003 white posts


def test_buildings_clear_of_road_and_plausible():
    b = [p for p in placements() if p['kind'] == 'building']
    assert len(b) > 200
    for p in b:
        assert p['min_road_d'] >= 7.0
        assert 2.3 <= p['eave_m'] <= p['ridge_m'] <= 20.0 + 1e-9


def test_geometry_names_finite_and_nondegenerate():
    meta = json.loads((SRC / 'objects.json').read_text())
    g = np.load(SRC / 'geometry.npz')
    assert all(m.startswith('V006_') for m in meta['materials'])
    for o in meta['objects']:
        assert o['name'].startswith('V006_')
        v, tri, mi = g[o['name'] + '__v'], g[o['name'] + '__tri'], g[o['name'] + '__mat']
        assert np.isfinite(v).all() and tri.min() >= 0 and tri.max() < len(v) and mi.max() < len(meta['materials'])
        a = np.linalg.norm(np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]]), axis=1)
        assert (a > 1e-9).all(), o['name']
        assert o['verts'] < 65000


def test_no_junction_barriers():
    j = [p for p in placements() if p['kind'] == 'junction']
    assert j and all(p['barrier_xy'] is None for p in j)


def test_ear_clip_concave():
    from v006_buildings import ear_clip, area
    p = np.array([[0, 0], [4, 0], [4, 4], [2, 2], [0, 4]], float)  # concave CCW
    t = ear_clip(p)
    assert len(t) == 3
    assert abs(sum(abs(area(p[list(k)])) for k in t) - area(p)) < 1e-9


def test_package_manifest():
    m = json.loads((ROOT / 'data/processed/full_track_package_v006/manifest.json').read_text())
    old = json.loads((ROOT / 'data/processed/full_track_package_v004/manifest.json').read_text())
    assert m['main_kn5']['sha256'] == old['kn5']['sha256']
    files = {f['path'] for f in m['package']['files']}
    assert {'exelberg_full_v006.kn5', 'exelberg_v006_scenery.kn5', 'models.ini'} <= files
    assert not any('v005' in f for f in files)
    ini = (ROOT / 'build/full_track_v006/exelberg_full_v006/models.ini').read_text()
    assert 'FILE=exelberg_full_v006.kn5' in ini and 'FILE=exelberg_v006_scenery.kn5' in ini


class V006(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V006, _name, (lambda f: lambda self: f())(_fn))
