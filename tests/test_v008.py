"""Offline checks for v008 smoothed terrain (no Blender, no game)."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def test_terrain_unchanged_near_road_and_capped():
    s = json.loads((ROOT / 'data/processed/terrain_v008/summary.json').read_text())
    assert s['max_abs_change_within_D0_m'] == 0.0 and s['fixed_road_gravel_vertices_max_change_m'] == 0.0
    assert s['max_abs_dz_m'] <= s['soft_cap_m'] + 1e-6
    assert float(s['crease_deg_after']['99']) < 0.6 * float(s['crease_deg_before']['99'])


def test_smoothed_skin_same_xy_topology():
    a = np.load(ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz')
    b = np.load(ROOT / 'data/processed/terrain_v008/smoothed_skin.npz')
    assert np.array_equal(a['triangles'], b['triangles'])
    assert np.array_equal(a['vertices'][:, :2], b['vertices'][:, :2])
    n = b['vertex_normals']
    assert np.allclose(np.linalg.norm(n, axis=1), 1, atol=1e-3) and (n[:, 2] > 0).all()


def test_route_distance_exact():
    from v008_terrain import route_distance
    p = np.array([[0, 0, 0], [10, 0, 0], [20, 0, 0]], float)
    d = route_distance(np.array([[5, 3.0], [25, 0.0], [10, -7.0]]), p)
    assert np.allclose(d, [3, 5, 7])


def test_package_manifest():
    m = json.loads((ROOT / 'data/processed/full_track_package_v008/manifest.json').read_text())['main_kn5']
    assert m['road_gravel_wall_identical_to_v004'] and m['physics_nodes_checked'] > 400
    assert m['grass_moved_min_route_distance_m'] > 10.0
    assert all(14 < m['spawn_moved_m'][k] < 16 for k in ('AC_START_0', 'AC_PIT_0', 'AC_HOTLAP_START_0'))
    files = {f['path'] for f in json.loads((ROOT / 'data/processed/full_track_package_v008/manifest.json').read_text())['package']['files']}
    assert {'exelberg_full_v008.kn5', 'exelberg_v008_scenery.kn5', 'models.ini'} <= files


class V008(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V008, _name, (lambda f: lambda self: f())(_fn))
