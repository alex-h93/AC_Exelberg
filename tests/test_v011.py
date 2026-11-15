"""Offline checks for v011 (forward fixes + reverse track; no Blender, no game)."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
P_ = ROOT / 'data/processed'


def man(mode):
    return json.loads((P_ / f'full_track_package_v011_{mode}/manifest.json').read_text())


def test_reverse_route_shares_old_road_and_uses_exit_branch():
    r = np.load(P_ / 'extension_v011r/route.npz')
    f = np.load(P_ / 'extension_v010/route.npz')
    ic = int(r['i_cut'])
    assert np.array_equal(r['designed_xyz_m'][:ic + 2], f['designed_xyz_m'][:ic + 2])
    e = json.loads((P_ / 'extension_v011r/osm_extension.json').read_text())
    assert e['reverse_driving_order'] == [555726612, 278650047, 26560097, 689306072]
    j = json.loads((P_ / 'extension_v011r/route.json').read_text())
    assert j['min_radius_extension_m'] > 8 and j['max_grade_extension'] < 0.08


def test_reverse_route_on_ring_lane():
    P = np.load(P_ / 'extension_v011r/route.npz')['designed_xyz_m']
    e = json.loads((P_ / 'extension_v011r/osm_extension.json').read_text())
    d = np.linalg.norm(P[:, :2] - np.array(e['ring_center_local_m']), axis=1)
    assert d.min() > 9.5  # never across the island (island + kerb < 7.3 m)


def test_reverse_patch_watertight():
    p = json.loads((P_ / 'extension_v011r/patch.json').read_text())
    assert p['open_edges_inside_patch'] == 0 and p['apron_max_slope'] <= 0.3 + 1e-6


def test_chevron_fix_exactly_two_series():
    for d in ('scenery_v011', 'scenery_v011r'):
        fx = json.loads((P_ / d / 'extension.json').read_text())['chevron_fixes']
        assert sorted(round(x['s_obs']) for x in fx) == [1113, 2318]


def test_chevrons_on_outer_side():
    from v005_roadside import Route  # noqa: F401  (curvature as the generator)
    P = np.load(P_ / 'extension_v010/route.npz')['designed_xyz_m']
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    t = np.gradient(P[:, :2], axis=0)
    h = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    for d in ('scenery_v011', 'scenery_v011r'):
        pl = json.loads((P_ / d / 'placements.json').read_text())
        ch = [p for p in pl if p['kind'] == 'sign' and p['cell'].startswith('chev')]
        assert len(ch) == 58
        inner = [p['s'] for p in ch if (lambda k: (p['side'] == 1 and k > 0.004) or (p['side'] == -1 and k < -0.004))(
            (np.interp(p['s'] + 15, s, h) - np.interp(p['s'] - 15, s, h)) / 30)]
        assert not inner, (d, inner)
        if d == 'scenery_v011r':
            assert all(p.get('facing') == 'reverse' for p in ch)


def test_urban_furniture():
    for d in ('scenery_v011', 'scenery_v011r'):
        u = json.loads((P_ / d / 'extension.json').read_text())['urban']
        assert u['zebra_stripes'] >= 24 and u['signs'] >= 18 and u['island_shrubs'] >= 30
        cells = {c for p in json.loads((P_ / d / 'placements.json').read_text()) if p['kind'] == 'urban_sign' for c in p['cells']}
        assert {'tulln', 'ped_crossing', 'bike_crossing', 'yield', 'kurzpark_end', 'keep_right_diag', 'pass_right', 'deer'} <= cells


def test_packages():
    for mode, track in (('forward', 'exelberg_full_v011'), ('reverse', 'exelberg_reverse_v011')):
        m = man(mode)
        mk = m['main_kn5']
        assert m['status'] == 'PASS_OFFLINE_NOT_RUNTIME_TESTED' and mk['file'] == f'{track}.kn5'
        assert mk['max_skin_corner_err_m'] < 3e-3 and mk['untouched_nodes_identical'] > 400
        assert all(2.5 < g < 3.5 for g in mk['gates_from_finish_m'].values())
        files = {f['path'] for f in m['package']['files']}
        assert {f'{track}.kn5', 'models.ini', 'map.png'} <= files and len(files) == 15
        assert m['package']['total_bytes'] < 300_000_000
    rs = man('reverse')['main_kn5']['reverse_spawns']
    assert len(rs) == 3 and all(v['facing_dot_reverse'] > 0.99 for v in rs.values())


class V011(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V011, _name, (lambda f: lambda self: f())(_fn))
