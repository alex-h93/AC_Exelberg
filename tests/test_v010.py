"""Offline checks for v010 (extension to the Neuwaldegg roundabout; no Blender, no game)."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
EXT = ROOT / 'data/processed/extension_v010'
TARGET_WGS84 = (16.276531758839184, 48.2401990264944)  # user's finish point (lon, lat)


def test_osm_extension_finish_at_exit_2():
    e = json.loads((EXT / 'osm_extension.json').read_text())
    assert e['target_to_finish_m'] < 15
    assert [x['way'] for x in e['exits_passed']] == [555726620, 9873331]  # exit 1 Huetteldorf, exit 2 = finish road
    assert abs(e['length_m'] - e['finish_arclength_m'] - 100.0) < 1.0


def test_route_old_part_untouched_and_drivable():
    r = np.load(EXT / 'route.npz')
    P, ic = r['designed_xyz_m'], int(r['i_cut'])
    old = np.load(ROOT / 'data/processed/road_v009/centerline.npz')['new_designed_xyz_m']
    assert np.array_equal(P[:ic + 2], old[:ic + 2])
    j = json.loads((EXT / 'route.json').read_text())
    assert j['min_radius_extension_m'] >= 7.9 and j['max_grade_extension'] < 0.08
    assert j['max_shift_vs_fit_old_part_m'] < 0.05
    assert 700 < j['length_m'] - j['old_length_m'] < 850


def test_route_follows_ring():
    from pyproj import Transformer
    r = np.load(EXT / 'route.npz')
    P = r['designed_xyz_m']
    ring = json.loads((ROOT / 'data/processed/scenery_v010/extension.json').read_text())['roundabout']
    c, rad = np.array(ring['centre_local']), ring['ring_centreline_radius_m']
    d = np.linalg.norm(P[:, :2] - c, axis=1)
    on = d < rad + 1.0
    assert on.sum() >= 10 and np.abs(d[on] - rad).max() < 1.0  # on the ring lane, not through the island
    x, y = Transformer.from_crs(4326, 25833, always_xy=True).transform(*TARGET_WGS84)
    tgt = np.array([x - 589500, y - 5346800])
    assert np.linalg.norm(P[int(r['finish_station']), :2] - tgt) < 15


def test_patch_watertight_and_skin():
    p = json.loads((EXT / 'patch.json').read_text())
    assert p['open_edges_inside_patch'] == 0 and p['apron_max_slope'] <= 0.3 + 1e-6
    sk = np.load(EXT / 'skin_v010.npz')
    v, f = sk['vertices'].astype(float), sk['triangles']
    a = (v[f[:, 1], 0] - v[f[:, 0], 0]) * (v[f[:, 2], 1] - v[f[:, 0], 1]) - (v[f[:, 1], 1] - v[f[:, 0], 1]) * (v[f[:, 2], 0] - v[f[:, 0], 0])
    assert (a > 0).all()
    e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), 1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    assert cnt.max() <= 2


def test_trees_clear_of_road():
    t = np.load(EXT / 'trees_v010.npz')
    from v004_vegetation import centerline_distance
    P = np.load(EXT / 'route.npz')['designed_xyz_m']
    new = t['new']
    assert new.sum() > 100
    assert centerline_distance(t['xyz'][new, :2].astype(float), P).min() >= 7.0 - 1e-3


def test_package_manifest():
    m = json.loads((ROOT / 'data/processed/full_track_package_v010/manifest.json').read_text())
    mk = m['main_kn5']
    assert m['status'] == 'PASS_OFFLINE_NOT_RUNTIME_TESTED'
    assert mk['skin_triangles_matched'] > 590000 and mk['max_skin_corner_err_m'] < 3e-3
    assert mk['untouched_nodes_identical'] > 400
    assert all(2.5 < g < 3.5 for g in mk['gates_from_finish_m'].values())
    assert 95 < m['route']['runout_m'] < 110
    files = {f['path'] for f in m['package']['files']}
    assert {'exelberg_full_v010.kn5', 'exelberg_v010_scenery.kn5', 'models.ini', 'map.png', 'data/map.ini'} <= files
    assert not any('v009' in f for f in files)
    assert m['package']['total_bytes'] < 300_000_000
    assert m['scene']['vegetation']['new_in_patch'] > 100
    assert {b['label'] for b in m['scene']['boards']} == {'FINISH', 'STOP'}


class V010(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V010, _name, (lambda f: lambda self: f())(_fn))
