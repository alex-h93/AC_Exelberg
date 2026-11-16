#!/usr/bin/env python3
"""v012 package (usage: package_full_track_v012.py forward|reverse): v011 + AI line + TV/replay cameras.

Starts from the verified v011 package (hash-checked against its manifest) and changes only:
  * main KN5 renamed to <track>.kn5; its root node name (same length, single occurrence) patched v011 -> v012
  * ai/fast_lane.ai  <- data/processed/ai_cameras_v012_<mode>/fast_lane.ai (pit_lane.ai unchanged)
  * data/cameras.ini, cameras_1.ini, cameras_2.ini (new: TV 1 / TV 2 / TV 3)
  * models.ini (MODEL_0 file name), ui/ui_track.json (name, version, description), README.txt (v012 section)
Scenery KN5, textures, map, surfaces etc. are byte-identical to v011.
Output: build/full_track_v012/<track>/, data/processed/full_track_package_v012_<mode>/manifest.json
"""
import configparser
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_track_v004_kn5 import parse  # noqa: E402
from validate_kn5 import bounded_read  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else 'forward'
OLD = {'forward': 'exelberg_full_v011', 'reverse': 'exelberg_reverse_v011'}[MODE]
NEW = OLD.replace('v011', 'v012')
SRC = ROOT / 'build/full_track_v011' / OLD
SRC_MAN = ROOT / f'data/processed/full_track_package_v011_{MODE}/manifest.json'
GEN = ROOT / f'data/processed/ai_cameras_v012_{MODE}'
PKG = ROOT / 'build/full_track_v012' / NEW
OUT = ROOT / f'data/processed/full_track_package_v012_{MODE}'
CAMS = ('cameras.ini', 'cameras_1.ini', 'cameras_2.ini')


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def check_cameras(path, length):
    c = configparser.ConfigParser(strict=False)
    c.read(path)
    n = int(c['HEADER']['CAMERA_COUNT'])
    secs = [s for s in c.sections() if s.startswith('CAMERA_')]
    assert len(secs) == n and n > 10, path
    io = [(float(c[s]['IN_POINT']), float(c[s]['OUT_POINT'])) for s in secs]
    assert io[0][0] == 0.0 and io[-1][1] == 1.0, path
    assert all(a[1] == b[0] for a, b in zip(io, io[1:])) and all(i < o for i, o in io), f'{path}: not contiguous'
    for s in secs:
        f = np.array([float(x) for x in c[s]['FORWARD'].split(',')])
        assert abs(np.linalg.norm(f) - 1) < 1e-3 and float(c[s]['MIN_FOV']) <= float(c[s]['MAX_FOV'])
    spans = np.diff([0.0] + [o for _, o in io]) * length
    return dict(set_name=c['HEADER']['SET_NAME'], cameras=n, span_m_median=float(np.median(spans)), span_m_max=float(spans.max()))


def main():
    old = json.loads(SRC_MAN.read_text())
    for f in old['package']['files']:
        assert sha(SRC / f['path']) == f['sha256'], f'v011 package differs from its manifest: {f["path"]}'
    if PKG.exists():
        shutil.rmtree(PKG)
    shutil.copytree(SRC, PKG)
    # main KN5: rename + root node name
    (PKG / f'{OLD}.kn5').unlink()
    b = (SRC / f'{OLD}.kn5').read_bytes()
    key = struct.pack('<i', len(OLD)) + OLD.encode()
    assert b.count(OLD.encode()) == 1 and b.count(key) == 1, 'track name must occur exactly once (root node)'
    (PKG / f'{NEW}.kn5').write_bytes(b.replace(key, struct.pack('<i', len(NEW)) + NEW.encode()))
    kn = parse(bounded_read(PKG / f'{NEW}.kn5', max_file=256 * 2 ** 20), max_file=256 * 2 ** 20, max_nodes=16384,
               max_texture=32 * 2 ** 20, max_materials=128, max_textures=128)
    assert kn['nodes'][0]['name'] == NEW
    spawn = {n['name']: np.asarray(n['matrix'], float).reshape(4, 4) for n in kn['nodes'] if n['name'] == 'AC_START_0'}['AC_START_0']
    mi = (PKG / 'models.ini').read_text()
    assert f'FILE={OLD}.kn5' in mi
    (PKG / 'models.ini').write_text(mi.replace(f'FILE={OLD}.kn5', f'FILE={NEW}.kn5'))
    # AI line + cameras
    shutil.copy2(GEN / 'fast_lane.ai', PKG / 'ai/fast_lane.ai')
    rep = json.loads((GEN / 'report.json').read_text())
    ab = (PKG / 'ai/fast_lane.ai').read_bytes()
    n = struct.unpack_from('<i', ab, 4)[0]
    A = np.frombuffer(ab, '<f4', count=5 * n, offset=16).reshape(n, 5)
    sp = spawn[3, :3]
    k = int(np.argmin(np.linalg.norm(A[:, :3] - sp, axis=1)))
    head = A[min(k + 5, n - 1), :3] - A[k, :3]
    ai_check = dict(spawn_to_line_m=float(np.linalg.norm(A[k, [0, 2]] - sp[[0, 2]])), spawn_at_m=float(A[k, 3]),
                    spawn_heading_dot=float(head @ spawn[2, :3] / np.linalg.norm(head) / np.linalg.norm(spawn[2, :3])))
    assert ai_check['spawn_to_line_m'] < 2.0 and ai_check['spawn_at_m'] < 20 and ai_check['spawn_heading_dot'] > 0.99, ai_check
    cams = {}
    for c in CAMS:
        shutil.copy2(GEN / c, PKG / 'data' / c)
        cams[c] = check_cameras(PKG / 'data' / c, rep['ai']['length_m'])
    # ui + readme
    ui = json.loads((PKG / 'ui/ui_track.json').read_text())
    ui['name'] = ui['name'].replace('v011', 'v012')
    ui['version'] = '0.0.12'
    ui['description'] += (' v012: AI line and three TV camera sets for replays (F3 cycles: TV 1 broadcast, TV 2 low trackside, '
                          'TV 3 high).')
    (PKG / 'ui/ui_track.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    rd = (PKG / 'README.txt').read_text().replace('v011', 'v012', 1)
    rd += (f'\nv012: main KN5 renamed to {NEW}.kn5 (geometry identical to v011). NEW ai/fast_lane.ai generated from the road\n'
           f'centreline ({rep["ai"]["points"]} points, {rep["ai"]["length_m"]:.0f} m; drives the centreline, not a racing line) and\n'
           'three replay camera sets (data/cameras.ini, cameras_1.ini, cameras_2.ini; F3 cycles them):\n')
    for c, v in cams.items():
        rd += f' - {v["set_name"]}: {v["cameras"]} cameras, median {v["span_m_median"]:.0f} m per camera\n'
    rd += 'Camera positions were checked for line of sight against terrain, trees and buildings offline. NOT runtime-tested.\n'
    (PKG / 'README.txt').write_text(rd)
    files = sorted(p for p in PKG.rglob('*') if p.is_file())
    OUT.mkdir(parents=True, exist_ok=True)
    man = dict(track=NEW, mode=MODE, from_v011=str(SRC.relative_to(ROOT)), main_kn5=dict(file=f'{NEW}.kn5', root_node=NEW,
               sha256=sha(PKG / f'{NEW}.kn5')), ai=rep['ai'], ai_check=ai_check, cameras=cams, camera_report=rep['sets'],
               package=dict(path=str(PKG.relative_to(ROOT)), files=[dict(path=p.relative_to(PKG).as_posix(), bytes=p.stat().st_size,
                                                                         sha256=sha(p)) for p in files],
                            total_bytes=sum(p.stat().st_size for p in files)),
               status='PASS_OFFLINE_NOT_RUNTIME_TESTED')
    (OUT / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
    print(json.dumps(dict(track=NEW, ai_check=ai_check, cameras=cams, files=len(files), bytes=man['package']['total_bytes']), indent=1))


if __name__ == '__main__':
    main()
