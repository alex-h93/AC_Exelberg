#!/usr/bin/env python3
"""Build a fresh, isolated offline solo-practice candidate; never deploy."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

import imagecodecs
import numpy as np

from install_ac_test import ALLOWLIST, TRACK_ID, validate_source
from validate_kn5 import parse

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / 'data/processed/ac_test_scene/manifest.json'
BUILD = ROOT / 'build/ac_test_v001'
EVIDENCE = ROOT / 'data/processed/ac_package'
DDS = ('kn5_asphalt.dds', 'kn5_gravel.dds', 'kn5_terrain.dds')
SAFETY = '''EXELBERG NORTHERN PROTOTYPE v001 — PRIVATE OFFLINE TEST CANDIDATE
Only the northern 1000–2500 m source-chainage section (~1496 m), not the full route.
Solo Practice, one car, daytime dry. No CSP required by this package.
NOT game-validated, timing-ready, surveyed, final-realism or safe-stopping certified.
AI files are own-generated empty <III (3,0,0) headers, NOT recorded AI;
no opponents. Practice compatibility remains an unvalidated hypothesis.
Trento-style AC_TIME_0_L/R is a finish-stage fixture only; timer/session/results
and reset/restart workflow are unverified. Do not treat this as a timed event.
Start at walking speed. Spawn +0.4 m clearance, settling and car nose/tail
clearance are untested; flat-yaw spawn is on a grade. Stop if placement is wrong.
6 m road width, 0.75 m shoulders, flat/zero camber and all physics are assumptions.
Collision-intended terrain has an artificial trench (up to 3.243515 m lowering),
not safely joined verges. Keep to the road. No barriers or extended staging.
Only 15 m after finish: NOT braking distance. Slow down well before the gate.
Placeholder DDS and schematic map/preview are original project-generated art.
No launch, installation, game/global configuration edits or runtime acceptance
was performed to produce this package. Performance, VR and collisions untested.

INSTALL/ROLLBACK (only after explicit user authorization):
Use the project installer, dry-run by default. It refuses existing destinations.
The only new game folder is content/tracks/exelberg_north_proto_v001.
To roll back, close AC and remove ONLY that exact newly installed folder after
confirming its identity. Never delete content/tracks, other tracks, user saves,
Steam/Proton prefixes, or global configs. Installer does not change preferences.
'''
ATTRIBUTION = '''Private-use prototype; no copyrighted game assets, vendor code or scripts included.
Terrain: © BEV (Bundesamt für Eich- und Vermessungswesen), CC BY 4.0.
https://www.bev.gv.at/  https://creativecommons.org/licenses/by/4.0/
Source: BEV 1 m bare-earth DTM, product-documented EPSG:9274 heights.
Adaptations: bounded extraction, smoothing, designed road ribbon, lowered terrain;
not a surveyed road, no measured road roughness, width or camber.
Route: © OpenStreetMap contributors, ODbL 1.0.
https://www.openstreetmap.org/copyright  https://opendatacommons.org/licenses/odbl/1-0/
Adaptations: northern subset, projected/local coordinates and smoothed design route.
Project-created geometry adaptation, placeholder textures, schematic UI art and configs.
Geographic provenance retained separately in project data/processed/ac_test_scene/
manifest.json, prototype_scene/report.json and docs/DATA_SOURCES.md.
Stock Drift AI header observation is metadata evidence only: headers were generated
with struct.pack, not copied; no stock geometry, artwork, textures or source included.
No public-release/license-clearance or final authenticity claim.
'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record(path, name=None):
    data = path.read_bytes()
    return dict(path=name or str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
                bytes=len(data), sha256=digest(data))


def verified(r):
    p = ROOT / r['path']
    require(not p.is_symlink() and p.resolve().is_relative_to(ROOT), 'Unsafe input')
    data = p.read_bytes()
    require(len(data) == r['bytes'] and digest(data) == r['sha256'], 'Input checksum: ' + str(p))
    return data


def map_transform(xz, size=1024, margin=25):
    """KN5 X east / Z south. PNG rows increase south: geographically north-up."""
    low, high = xz.min(axis=0), xz.max(axis=0)
    span = float(max(high - low) + 2 * margin)
    origin = (low + high) / 2 - span / 2
    scale = span / (size - 1)  # metres per pixel, AC SCALE_FACTOR
    return dict(width=size, height=size, scale_factor=scale,
                x_offset=float(-origin[0]), z_offset=float(-origin[1]),
                pixel_formula='u=(KN5_X+X_OFFSET)/SCALE_FACTOR; v=(KN5_Z+Z_OFFSET)/SCALE_FACTOR',
                north_up=True, margin_m=margin)


def pixels(xz, transform):
    return (xz + [transform['x_offset'], transform['z_offset']]) / transform['scale_factor']


def draw_route(xz, transform, background=(0, 0, 0, 0), color=(255, 255, 255, 255), radius=3):
    size = transform['width']
    image = np.empty((size, size, 4), np.uint8)
    image[:] = background
    uv = pixels(xz, transform)
    for a, b in zip(uv[:-1], uv[1:]):
        steps = max(2, int(np.linalg.norm(b-a) * 2) + 1)
        for point in np.linspace(a, b, steps):
            x, y = np.rint(point).astype(int)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx*dx + dy*dy <= radius*radius and 0 <= x+dx < size and 0 <= y+dy < size:
                        image[y+dy, x+dx] = color
    return image


def validate_model(data, scene):
    model = parse(data)  # Independent parser, exact EOF and bounded uint16 indices.
    require(len(model['nodes']) == len({n['name'] for n in model['nodes']}), 'Duplicate nodes/grid')
    nodes = {n['name']: n for n in model['nodes']}
    meshes = {n for s in scene['surfaces'].values() for n in s['objects']}
    helpers = {h['name'] for h in scene['helpers']}
    require(set(nodes) == meshes | helpers | {TRACK_ID, '1GRASS_TERRAIN'}, 'Node allowlist')
    require({n for n in nodes if n.startswith('AC_START_')} == {'AC_START_0'}, 'Unique solo grid')
    for name in (TRACK_ID, '1GRASS_TERRAIN'):
        require(np.array_equal(nodes[name]['matrix'], np.eye(4).ravel()), 'Nonidentity wrapper')
    for helper in scene['helpers']:
        n = nodes[helper['name']]
        require(n['kind'] == 1 and n['parent'] == TRACK_ID and not n['children'], 'Helper hierarchy')
        expected = np.array(helper['kn5_expected_row_axes_translation'])
        require(np.allclose(n['matrix'], expected, atol=0.0003, rtol=0) and
                np.allclose(n['matrix'].reshape(4, 4)[:3, :3], expected.reshape(4, 4)[:3, :3], atol=2e-6, rtol=0),
                'Helper transform')
    for key, surface in scene['surfaces'].items():
        for name in surface['objects']:
            n = nodes[name]
            require(name.startswith('1' + key) and n['kind'] == 2, 'Surface key mismatch')
            require(n['parent'] == ('1GRASS_TERRAIN' if key == 'GRASS' else TRACK_ID), 'Mesh transform hierarchy')
            require(len(n['vertices']) <= 65535 and n['indices'].dtype == np.dtype('<u2') and
                    n['indices'].max() < len(n['vertices']), 'uint16 geometry')
            require(np.isfinite(n['vertices']).all(), 'Nonfinite geometry')
            require([n[k] for k in ('active', 'cast_shadows', 'visible', 'transparent', 'renderable', 'layer')]
                    == [1, 1, 1, 0, 1, 0], 'Unexpected mesh flags')
    require(sum(len(nodes[n]['indices']) for n in meshes) == 230400, 'Triangle count')
    textures = {t['name']: t['data'] for t in model['textures']}
    require(set(textures) == set(DDS), 'Texture allowlist')
    require(len(model['materials']) == 3, 'Material count')
    for material in model['materials']:
        require(material['shader'] == 'ksPerPixel', 'Unexpected shader')
        # Parser exposes explicit slot-to-texture bindings; all must resolve.
        require(material['bindings'] and all(t[2] in textures for t in material['bindings']), 'Texture binding')
    return model, textures


def build(build_dir=BUILD, evidence=EVIDENCE):
    require(not build_dir.exists() and not build_dir.is_symlink(), 'Build already exists')
    require(not evidence.exists() and not evidence.is_symlink(), 'Evidence already exists')
    scene = json.loads(SCENE.read_text())
    require(scene['track_id'] == TRACK_ID and scene['status'] == 'PASS_OFFLINE_SCENE_EXPORT', 'Scene identity/status')
    expected = {f'exports/ac_test_v001/{TRACK_ID}.kn5', *(f'exports/ac_test_v001/{n}' for n in DDS)}
    sources = {r['path']: r for r in scene['outputs'] if r['path'] in expected}
    require(set(sources) == expected, 'Scene asset allowlist incomplete')
    asset_data = {Path(n).name: verified(r) for n, r in sources.items()}
    model, textures = validate_model(asset_data[TRACK_ID + '.kn5'], scene)
    require(all(textures[n] == asset_data[n] for n in DDS), 'Embedded/standalone DDS mismatch')
    stations = ROOT / 'data/processed/prototype_scene/stations.csv'
    station_data = stations.read_bytes()
    require(digest(station_data) == scene['source_preservation']['hashes_before'][str(stations)], 'Design stations checksum')
    rows = list(csv.DictReader(io.StringIO(station_data.decode())))
    xz = np.array([[float(r['designed_x_m']), -float(r['designed_y_m'])] for r in rows])
    road = next(n for n in model['nodes'] if n['name'] == '1ROAD')['vertices'][:, [0, 2]]
    transform = map_transform(road)
    length = float(rows[-1]['designed_section_arclength_xy_m'])
    files = {TRACK_ID + '.kn5': asset_data[TRACK_ID + '.kn5'], **{'texture/' + n: asset_data[n] for n in DDS}}
    def text(name, value):
        files[name] = value.encode('utf-8')
    text('README.txt', SAFETY)
    text('ATTRIBUTION.txt', ATTRIBUTION)
    text('models.ini', f'[MODEL_0]\nFILE={TRACK_ID}.kn5\nPOSITION=0,0,0\nROTATION=0,0,0\n')
    surfaces = '; PROVISIONAL unmeasured physics; no CSP. See README.txt\n'
    for i, (key, s) in enumerate(scene['surfaces'].items()):
        surfaces += (f'\n[SURFACE_{i}]\nKEY={key}\nFRICTION={s["friction"]}\n'
                     f'IS_VALID_TRACK={s["is_valid_track"]}\nIS_PITLANE={s["is_pitlane"]}\n'
                     'DAMPING=0\nDIRT_ADDITIVE=0\nWAV_PITCH=0\nWAV=\n'
                     'SIN_HEIGHT=0\nSIN_LENGTH=0\nVIBRATION_GAIN=0\nVIBRATION_LENGTH=0\nBLACK_FLAG_TIME=0\n')
    text('data/surfaces.ini', surfaces)
    text('data/map.ini', '[PARAMETERS]\n' + '\n'.join(f'{key}={value}' for key, value in {
        'WIDTH': transform['width'], 'HEIGHT': transform['height'], 'MARGIN': 0,
        'SCALE_FACTOR': transform['scale_factor'], 'X_OFFSET': transform['x_offset'],
        'Z_OFFSET': transform['z_offset'], 'DRAWING_SIZE': 10}.items()) + '\n')
    text('data/lighting.ini', '; Own provisional daylight parameters; not calibrated\n[LIGHTING]\nSUN_PITCH_ANGLE=45\nSUN_HEADING_ANGLE=0\n')
    text('ui/ui_track.json', json.dumps(dict(name='Exelberg North Prototype v001', description='Private northern section; unvalidated solo Practice candidate, not timing-ready or surveyed.',
        tags=['A2B', 'Hillclimb', 'prototype'], country='Austria', city='Königstetten',
        length=f'{round(length)} m', width='6 m (assumed)', pitboxes='1', author='Assetto Exelberg project', version='0.0.1'), ensure_ascii=False, indent=2) + '\n')
    files['map.png'] = imagecodecs.png_encode(draw_route(xz, transform))
    outline_transform = map_transform(road, size=512)
    files['ui/outline.png'] = imagecodecs.png_encode(draw_route(xz, outline_transform))
    preview = draw_route(xz, outline_transform, background=(30, 46, 35, 255), color=(225, 199, 110, 255), radius=3)
    # Original schematic, not a photograph or in-game render; start green, finish red.
    for point, color in [(xz[0], (60, 220, 100, 255)), (xz[-1], (240, 80, 60, 255))]:
        x, y = np.rint(pixels(point[None, :], outline_transform)[0]).astype(int)
        preview[y-5:y+6, x-5:x+6] = color
    files['ui/preview.png'] = imagecodecs.png_encode(preview)
    for name in ('fast_lane.ai', 'pit_lane.ai'):
        files['ai/' + name] = struct.pack('<III', 3, 0, 0)
    require(set(files) == ALLOWLIST, 'Package file allowlist')
    # Reserve both output roots exclusively; never reuse partial/failed output.
    build_dir.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    package = build_dir / TRACK_ID
    package.mkdir()
    for name, data in sorted(files.items()):
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    manifest = dict(schema='ac_test_package_v1', track_id=TRACK_ID,
        scene_manifest=record(SCENE), source_assets=list(sources.values()),
        map_source=record(stations), map_transform=transform, designed_length_m=length,
        files=[dict(path=n, bytes=len(d), sha256=digest(d)) for n, d in sorted(files.items())],
        file_count=len(files), bytes=sum(map(len, files.values())),
        validation=dict(independent_parse='PASS', nodes=len(model['nodes']), unique_grid='AC_START_0 only',
                        helpers_transforms_surfaces_uint16_textures='PASS', runtime_tested=False),
        ai='Own struct.pack(<III,3,0,0); empty, not recorded, no opponents; Practice unvalidated')
    zip_path = build_dir / (TRACK_ID + '.zip')
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(TRACK_ID + '/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(zip_path) as archive:
        require(set(archive.namelist()) == {TRACK_ID + '/' + n for n in files}, 'ZIP topdir allowlist')
        require(all(archive.read(TRACK_ID + '/' + n) == d for n, d in files.items()), 'ZIP payload differs')
    manifest['zip'] = dict(record(zip_path), entries=len(files), uncompressed_bytes=sum(map(len, files.values())),
                           provenance='ZIP of the exact manifest-listed package bytes, one track-ID top directory only')
    manifest['builder'] = record(Path(__file__).resolve())
    manifest_path = evidence / 'manifest.json'
    with manifest_path.open('x') as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    validate_source(package, manifest_path)
    print(json.dumps(dict(package=str(package), zip=manifest['zip'], file_count=len(files), bytes=manifest['bytes']), indent=2))
    return manifest


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()


if __name__ == '__main__':
    main()
