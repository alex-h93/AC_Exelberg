#!/usr/bin/env python3
"""v014 package (usage: package_full_track_v014.py forward|reverse): v013 + new road/shoulder/verge textures + 3D verge grass.

Starts from the verified v013 package (hash-checked against its manifest) and changes only:
  * main KN5 -> <track>.kn5, root node v013 -> v014 (same length, single occurrence); header rewritten by
    v014_materials.patch_main (asphalt, gravel, 27 ground materials -> ksPerPixelMultiMap_NMDetail + v014 textures).
    The node section (all meshes incl. 1ROAD/1GRAVEL/1GRASS physics) is asserted byte-identical to v013.
  * scenery KN5 -> <..>_v014_scenery.kn5, root renamed; V011_asphalt/V011_gravel patched (v014_materials.patch_scenery),
    node section byte-identical apart from the root name
  * NEW <..>_v014_grass.kn5 (MODEL_2): 3D verge grass (scripts/v014_grass.py + build_grass_v014.py)
  * models.ini, ui/ui_track.json, README.txt, ATTRIBUTION.txt (new ambientCG assets)
Output: build/full_track_v014/<track>/, data/processed/full_track_package_v014_<mode>/manifest.json
"""
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import kn5_header as K  # noqa: E402
import v014_materials as M  # noqa: E402
from full_track_v004_kn5 import parse  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else 'forward'
OLD = {'forward': 'exelberg_full_v013', 'reverse': 'exelberg_reverse_v013'}[MODE]
NEW = OLD.replace('v013', 'v014')
OLD_SC = {'forward': 'exelberg_v013_scenery', 'reverse': 'exelberg_reverse_v013_scenery'}[MODE]
NEW_SC = OLD_SC.replace('v013', 'v014')
GRASS = {'forward': 'exelberg_v014_grass', 'reverse': 'exelberg_reverse_v014_grass'}[MODE]
SRC = ROOT / 'build/full_track_v013' / OLD
SRC_MAN = ROOT / f'data/processed/full_track_package_v013_{MODE}/manifest.json'
GRASS_KN5 = ROOT / 'exports/full_track_v014' / f'{GRASS}.kn5'
GRASS_INFO = ROOT / 'data/processed' / {'forward': 'grass_v014', 'reverse': 'grass_v014r'}[MODE]
PKG = ROOT / 'build/full_track_v014' / NEW
OUT = ROOT / f'data/processed/full_track_package_v014_{MODE}'
BUDGET = dict(max_file=256 * 2 ** 20, max_nodes=16384, max_texture=32 * 2 ** 20, max_materials=128, max_textures=128)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def rename_root(b, old, new):
    assert len(old) == len(new)
    key = struct.pack('<i', len(old)) + old.encode()
    assert b.count(old.encode()) == 1 and b.count(key) == 1, f'{old} must occur exactly once (root node)'
    return b.replace(key, struct.pack('<i', len(new)) + new.encode())


def patched(src_bytes, old, new, patch):
    b = rename_root(src_bytes, old, new)
    out, info = patch(b)
    h0, h1 = K.read(b), K.read(out)
    assert out[h1['node_offset']:] == b[h0['node_offset']:], 'node section must stay byte-identical'
    kn = parse(out, **BUDGET)
    assert kn['nodes'][0]['name'] == new
    info.update(bytes=len(out), node_section_identical=True, textures=len(h1['textures']), materials_total=len(h1['materials']))
    return out, info


def main():
    old = json.loads(SRC_MAN.read_text())
    for f in old['package']['files']:
        assert sha(SRC / f['path']) == f['sha256'], f'v013 package differs from its manifest: {f["path"]}'
    gexp = json.loads((GRASS_INFO / 'exported.json').read_text())
    assert gexp['kn5']['sha256'] == sha(GRASS_KN5) and gexp['root'] == GRASS, 'grass KN5 does not match its export report'
    if PKG.exists():
        shutil.rmtree(PKG)
    shutil.copytree(SRC, PKG)
    for f in (f'{OLD}.kn5', f'{OLD_SC}.kn5'):
        (PKG / f).unlink()
    main_b, main_info = patched((SRC / f'{OLD}.kn5').read_bytes(), OLD, NEW, M.patch_main)
    (PKG / f'{NEW}.kn5').write_bytes(main_b)
    sc_b, sc_info = patched((SRC / f'{OLD_SC}.kn5').read_bytes(), OLD_SC, NEW_SC, M.patch_scenery)
    (PKG / f'{NEW_SC}.kn5').write_bytes(sc_b)
    shutil.copy2(GRASS_KN5, PKG / f'{GRASS}.kn5')
    gk = parse((PKG / f'{GRASS}.kn5').read_bytes(), **BUDGET)
    assert gk['nodes'][0]['name'] == GRASS and not any(n['name'][:1].isdigit() for n in gk['nodes']), 'grass must be visual only'
    mi = (PKG / 'models.ini').read_text()
    assert f'FILE={OLD}.kn5' in mi and f'FILE={OLD_SC}.kn5' in mi and '[MODEL_2]' not in mi
    mi = mi.replace(f'FILE={OLD}.kn5', f'FILE={NEW}.kn5').replace(f'FILE={OLD_SC}.kn5', f'FILE={NEW_SC}.kn5')
    mi = mi.rstrip('\n') + f'\n\n[MODEL_2]\nFILE={GRASS}.kn5\nPOSITION=0,0,0\nROTATION=0,0,0\n'
    (PKG / 'models.ini').write_text(mi)
    ui = json.loads((PKG / 'ui/ui_track.json').read_text())
    ui['name'] = ui['name'].replace('v013', 'v014')
    ui['version'] = '0.0.14'
    ui['description'] += ' v014: new asphalt, shoulder and verge textures with surface relief, 3D grass along the verges.'
    (PKG / 'ui/ui_track.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    gs = json.loads((GRASS_INFO / 'objects.json').read_text())['stats']
    rd = (PKG / 'README.txt').read_text().replace('v013', 'v014', 1)
    rd += (f'\nv014: textures and verge grass (meshes, physics, AI line and cameras identical to v013).\n'
           ' - road: ambientCG Asphalt015 with normal + specular map and a 60 m wear/patch/crack-seal detail layer;\n'
           '   shoulder: Gravel023 with normal map; ground: stronger Grass005 detail + grass normal detail.\n'
           '   Shader ksPerPixelMultiMap_NMDetail (vanilla AC, no CSP required).\n'
           f' - {GRASS}.kn5: {gs["clumps"]} alpha-tested grass clumps on the verges (3.4-9.5 m from the centreline,\n'
           f'   ~{gs["per_100m"]:.0f} per 100 m), drawn within ~75 m of the camera. Visual only, no collision.\n'
           'NOT runtime-tested.\n')
    (PKG / 'README.txt').write_text(rd)
    att = (PKG / 'ATTRIBUTION.txt').read_text()
    att += ('\nv014: ambientCG (https://ambientcg.com, CC0 1.0) Asphalt015, Gravel023, Grass005, Foliage002, Foliage006,\n'
            'Foliage008; textures tiled, recoloured and combined for this project (wear/crack-seal layer procedural).\n')
    (PKG / 'ATTRIBUTION.txt').write_text(att)
    files = sorted(p for p in PKG.rglob('*') if p.is_file())
    total = sum(p.stat().st_size for p in files)
    OUT.mkdir(parents=True, exist_ok=True)
    man = dict(track=NEW, mode=MODE, from_v013=str(SRC.relative_to(ROOT)),
               main_kn5=dict(file=f'{NEW}.kn5', sha256=sha(PKG / f'{NEW}.kn5'), **main_info),
               scenery_kn5=dict(file=f'{NEW_SC}.kn5', sha256=sha(PKG / f'{NEW_SC}.kn5'), **sc_info),
               grass_kn5=dict(file=f'{GRASS}.kn5', sha256=sha(PKG / f'{GRASS}.kn5'), kn5_objects=gexp['objects'], kn5_tris=gexp['tris'], stats=gs),
               textures=json.loads((ROOT / 'data/processed/textures_v014/manifest.json').read_text()),
               package=dict(path=str(PKG.relative_to(ROOT)), files=[dict(path=p.relative_to(PKG).as_posix(), bytes=p.stat().st_size,
                                                                         sha256=sha(p)) for p in files], total_bytes=total),
               status='PASS_OFFLINE_NOT_RUNTIME_TESTED')
    (OUT / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
    print(json.dumps(dict(track=NEW, main=main_info['bytes'], scenery=sc_info['bytes'], grass=gexp['kn5']['bytes'],
                          files=len(files), bytes=total)))


if __name__ == '__main__':
    main()
