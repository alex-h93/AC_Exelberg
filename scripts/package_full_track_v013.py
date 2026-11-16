#!/usr/bin/env python3
"""v013 package (usage: package_full_track_v013.py forward|reverse): v012 + urban-sign clearance fix at the roundabout.

Starts from the verified v012 package (hash-checked against its manifest) and changes only:
  * main KN5 renamed to <track>.kn5; root node name (same length, single occurrence) patched v012 -> v013
  * scenery KN5 replaced by exports/full_track_v013/<..>_v013_scenery.kn5 (scripts/v013_scenery.py + build_scenery_v013.py)
  * models.ini, ui/ui_track.json (name, version, description), README.txt (v013 section)
AI line, cameras, textures, map, surfaces etc. are byte-identical to v012.
Output: build/full_track_v013/<track>/, data/processed/full_track_package_v013_<mode>/manifest.json
"""
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_track_v004_kn5 import parse  # noqa: E402
from validate_kn5 import bounded_read  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else 'forward'
OLD = {'forward': 'exelberg_full_v012', 'reverse': 'exelberg_reverse_v012'}[MODE]
NEW = OLD.replace('v012', 'v013')
OLD_SC = {'forward': 'exelberg_v011_scenery', 'reverse': 'exelberg_reverse_v011_scenery'}[MODE]
NEW_SC = OLD_SC.replace('v011', 'v013')
SRC = ROOT / 'build/full_track_v012' / OLD
SRC_MAN = ROOT / f'data/processed/full_track_package_v012_{MODE}/manifest.json'
SC_KN5 = ROOT / 'exports/full_track_v013' / f'{NEW_SC}.kn5'
SC_INFO = ROOT / 'data/processed' / {'forward': 'scenery_v013', 'reverse': 'scenery_v013r'}[MODE]
PKG = ROOT / 'build/full_track_v013' / NEW
OUT = ROOT / f'data/processed/full_track_package_v013_{MODE}'
BUDGET = dict(max_file=256 * 2 ** 20, max_nodes=16384, max_texture=32 * 2 ** 20, max_materials=128, max_textures=128)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    old = json.loads(SRC_MAN.read_text())
    for f in old['package']['files']:
        assert sha(SRC / f['path']) == f['sha256'], f'v012 package differs from its manifest: {f["path"]}'
    exp = json.loads((SC_INFO / 'exported.json').read_text())
    assert exp['kn5']['sha256'] == sha(SC_KN5) and exp['root'] == NEW_SC, 'scenery KN5 does not match its export report'
    if PKG.exists():
        shutil.rmtree(PKG)
    shutil.copytree(SRC, PKG)
    (PKG / f'{OLD}.kn5').unlink()
    (PKG / f'{OLD_SC}.kn5').unlink()
    b = (SRC / f'{OLD}.kn5').read_bytes()
    key = struct.pack('<i', len(OLD)) + OLD.encode()
    assert b.count(OLD.encode()) == 1 and b.count(key) == 1, 'track name must occur exactly once (root node)'
    (PKG / f'{NEW}.kn5').write_bytes(b.replace(key, struct.pack('<i', len(NEW)) + NEW.encode()))
    shutil.copy2(SC_KN5, PKG / f'{NEW_SC}.kn5')
    for k, root in ((NEW, NEW), (NEW_SC, NEW_SC)):
        kn = parse(bounded_read(PKG / f'{k}.kn5', max_file=BUDGET['max_file']), **BUDGET)
        assert kn['nodes'][0]['name'] == root, k
    mi = (PKG / 'models.ini').read_text()
    assert f'FILE={OLD}.kn5' in mi and f'FILE={OLD_SC}.kn5' in mi
    (PKG / 'models.ini').write_text(mi.replace(f'FILE={OLD}.kn5', f'FILE={NEW}.kn5').replace(f'FILE={OLD_SC}.kn5', f'FILE={NEW_SC}.kn5'))
    ui = json.loads((PKG / 'ui/ui_track.json').read_text())
    ui['name'] = ui['name'].replace('v012', 'v013')
    ui['version'] = '0.0.13'
    ui['description'] += ' v013: roundabout signs moved off the road.'
    (PKG / 'ui/ui_track.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    moved = json.loads((SC_INFO / 'extension.json').read_text())['urban_signs_moved']
    rd = (PKG / 'README.txt').read_text().replace('v012', 'v013', 1)
    rd += (f'\nv013: main KN5 renamed to {NEW}.kn5 (geometry identical). Scenery {NEW_SC}.kn5: {len(moved)} signs at the\n'
           'Neuwaldegg roundabout / Exelbergstrasse splitter island moved out to 3.95 m from the track centreline (they stood on\n'
           'the 6 m road where it covers part of the splitter island). Everything else identical to v012. NOT runtime-tested.\n')
    (PKG / 'README.txt').write_text(rd)
    files = sorted(p for p in PKG.rglob('*') if p.is_file())
    OUT.mkdir(parents=True, exist_ok=True)
    man = dict(track=NEW, mode=MODE, from_v012=str(SRC.relative_to(ROOT)), main_kn5=dict(file=f'{NEW}.kn5', sha256=sha(PKG / f'{NEW}.kn5')),
               scenery_kn5=dict(file=f'{NEW_SC}.kn5', sha256=sha(PKG / f'{NEW_SC}.kn5')), signs_moved=moved,
               package=dict(path=str(PKG.relative_to(ROOT)), files=[dict(path=p.relative_to(PKG).as_posix(), bytes=p.stat().st_size,
                                                                         sha256=sha(p)) for p in files],
                            total_bytes=sum(p.stat().st_size for p in files)),
               status='PASS_OFFLINE_NOT_RUNTIME_TESTED')
    (OUT / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
    print(json.dumps(dict(track=NEW, signs_moved=len(moved), files=len(files), bytes=man['package']['total_bytes'])))


if __name__ == '__main__':
    main()
