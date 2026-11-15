"""Offline checks for v009 smoothed road curves (no Blender, no game)."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
R9 = ROOT / 'data/processed/road_v009'


def test_field_maps_ribbon_exactly():
    from v009_field import Field, station_normals
    th = np.linspace(0, np.pi, 60)
    p = np.c_[50 * np.cos(th), 50 * np.sin(th)] + np.c_[np.random.default_rng(1).normal(0, .2, (60, 2))]
    P = np.c_[50 * np.cos(th), 50 * np.sin(th)]
    n, N = station_normals(p), station_normals(P)
    F = Field(p, P)
    for o in (-6.0, -3.0, 0.0, 3.0, 6.0):  # station vertices and quad-edge midpoints map onto the new ribbon
        assert np.allclose(F.displace(p[2:-2] + o * n[2:-2]), P[2:-2] + o * N[2:-2], atol=1e-6)
        mid0 = 0.5 * ((p[2:-3] + o * n[2:-3]) + (p[3:-2] + o * n[3:-2]))
        mid1 = 0.5 * ((P[2:-3] + o * N[2:-3]) + (P[3:-2] + o * N[3:-2]))
        assert np.allclose(F.displace(mid0), mid1, atol=1e-6)
    far = np.array([[0.0, 0.0], [200.0, 200.0]])  # >30 m from the line: untouched
    assert np.array_equal(F.displace(far), far)


def test_centerline_smoother_and_close():
    s = json.loads((R9 / 'summary.json').read_text())
    assert s['curvature_total_variation_4m']['after'] < 0.6 * s['curvature_total_variation_4m']['before']
    assert s['turn_step_change_deg']['after_p99'] < s['turn_step_change_deg']['before_p99']
    assert s['centerline_shift_m']['max'] < 1.2 and s['max_node_deviation_m'] < 0.3
    assert s['min_radius_4m_m']['after'] >= s['min_radius_4m_m']['before'] - 0.2
    sk = s['skin']
    assert sk['flipped_triangles'] == 0 and not sk['z_changed']


def test_skin_heights_topology_ends():
    a = np.load(ROOT / 'data/processed/terrain_v008/smoothed_skin.npz')
    b = np.load(R9 / 'smoothed_skin.npz')
    assert np.array_equal(a['triangles'], b['triangles'])
    assert np.array_equal(a['vertices'][:, 2], b['vertices'][:, 2])
    p, P = b['designed_xyz_v008_m'], b['designed_xyz_m']
    assert np.array_equal(p[:, 2], P[:, 2])  # profile unchanged
    assert np.allclose(P[:8, :2], p[:8, :2], atol=0.02) and np.allclose(P[-6:, :2], p[-6:, :2], atol=0.02)


def test_package_manifest():
    m = json.loads((ROOT / 'data/processed/full_track_package_v009/manifest.json').read_text())
    mk = m['main_kn5']
    assert mk['triangles_match_v008_moved_by_field'] and mk['physics_nodes_checked'] > 400
    assert mk['max_height_change_m'] < 1e-4 and mk['max_field_error_m'] < 3e-3
    assert all(v < 0.05 for v in mk['helpers_moved_m'].values())
    files = {f['path'] for f in m['package']['files']}
    assert {'exelberg_full_v009.kn5', 'exelberg_v009_scenery.kn5', 'models.ini'} <= files
    assert not any('v008' in f for f in files)


def test_posts_follow_road():
    pl = json.loads((ROOT / 'data/processed/scenery_v009/placements.json').read_text())
    gp = [p for p in pl if p['kind'] == 'guide_posts'][0]
    assert gp['count'] > 700 and gp['max_shift_m'] < 1.2


class V009(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V009, _name, (lambda f: lambda self: f())(_fn))
