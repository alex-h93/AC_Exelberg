"""Offline checks for v012 (AI line + TV cameras; no game)."""
import json
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
P_ = ROOT / 'data/processed'


def man(mode):
    return json.loads((P_ / f'full_track_package_v012_{mode}/manifest.json').read_text())


def test_ai_line_reparses_and_follows_road():
    from v012_ai_cameras import read_ai, kn5
    for mode, ext in (('forward', 'extension_v010'), ('reverse', 'extension_v011r')):
        A = read_ai(P_ / f'ai_cameras_v012_{mode}/fast_lane.ai')
        P = kn5(np.load(P_ / ext / 'route.npz')['designed_xyz_m'])
        if mode == 'reverse':
            P = P[::-1]
        lift = np.array([0, 0.35, 0])  # KN5 up = y
        assert np.linalg.norm(A[0, :3] - P[0] - lift) < 0.01 and np.linalg.norm(A[-1, :3] - P[-1] - lift) < 0.01
        d = np.linalg.norm(np.diff(A[:, :3], axis=0), axis=1)
        assert 1.3 < d.min() and d.max() < 1.7 and abs(A[-1, 3] - d.sum()) < 1.0


def test_ai_extras_sane():
    for mode in ('forward', 'reverse'):
        b = (P_ / f'ai_cameras_v012_{mode}/fast_lane.ai').read_bytes()
        n = struct.unpack_from('<i', b, 4)[0]
        E = np.frombuffer(b, '<f4', count=18 * n, offset=20 + 20 * n).reshape(n, 18)
        assert E[0, 0] == 0 and 5 < np.median(E[:, 0]) < 45 and E[:, 0].max() <= 45
        assert np.all((E[:, 1] >= 0) & (E[:, 1] <= 1) & (E[:, 2] >= 0) & (E[:, 2] <= 1))
        assert np.allclose(np.linalg.norm(E[:, 13:16], axis=1), 1, atol=1e-3)


def test_packages():
    for mode, track in (('forward', 'exelberg_full_v012'), ('reverse', 'exelberg_reverse_v012')):
        m = man(mode)
        assert m['status'] == 'PASS_OFFLINE_NOT_RUNTIME_TESTED' and m['main_kn5']['root_node'] == track
        files = {f['path'] for f in m['package']['files']}
        assert {f'{track}.kn5', 'ai/fast_lane.ai', 'data/cameras.ini', 'data/cameras_1.ini', 'data/cameras_2.ini'} <= files
        assert len(files) == 18 and m['ai_check']['spawn_heading_dot'] > 0.99
        assert all(v['cameras'] > 20 for v in m['cameras'].values())
        mi = (ROOT / m['package']['path'] / 'models.ini').read_text()
        assert f'FILE={track}.kn5' in mi


class V012(unittest.TestCase):
    pass


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(V012, _name, (lambda f: lambda self: f())(_fn))
