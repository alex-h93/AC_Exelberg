#!/usr/bin/env python3
"""Assemble only the full-v002 manifest assets into fresh offline outputs."""
from __future__ import annotations

import argparse
import gc
import io
import json
from pathlib import Path
import struct
import zipfile

import imagecodecs
import numpy as np

from install_full_track_v002 import ALLOWLIST, DDS, TRACK_ID, validate_source, transfer
from package_ac_test import digest, draw_route, map_transform, pixels, record, require, verified
from validate_kn5 import parse

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / 'data/processed/full_track_scene_v002/manifest.json'
BUILD = ROOT / 'build/full_track_v002'
EVIDENCE = ROOT / 'data/processed/full_track_package_v002'
README = '''EXELBERG FULL v002 (two lanes) — PRIVATE SOLO TEST BASE
Entire Königstetten -> Marswiese designed road: 15212.525 m, width 6 m,
two nominal 3 m lanes, one pitbox; zero crossfall, 0.75 m shoulders.
This UI length is full ROAD length, NOT certified timed-course length.
Finish-only Trento-style TIME_0_L/R fixture: 14912.525 m along designed road.
Spawn at 25 m, nominal spawn-to-finish 14887.525 m; runout ~300 m
(299.55 m to endcap face). Timing/session/results/restarts NOT certified.
Brake BEFORE finish; closed endcap is not a stopping-distance guarantee.
Spawn yaw reversed 180 degrees from v001 after actual backwards feedback;
KN5 +Z follows travel. New heading/settling/reset remain runtime UNTESTED.
All four physical keys ROAD/GRAVEL/GRASS/WALL explicit; terrain collision and
temporary closed walls aim to reduce ordinary departures/falls, NOT fallproof.
Walls are invented safety aids, NOT real Exelberg barriers. Start at walking pace.
Seven own opaque procedural DDS are embedded and supplied in texture/.
Preview is resized actual offline driver render; north-up maps use v002 design.
Own empty AI headers (3,0,0), same format that v001 loaded with; NOT recorded AI.
Solo Practice first, daytime dry, no opponents/traffic, no required CSP.
No v002 game load, collision, texture, performance or Quest 2 VR validation yet.
Provisional OSM alignment/width/paint/grip/camber, sparse procedural forest;
not final realism or survey accuracy. Unresolved km 9.589 DTM dip provisionally
bridged in designed road (up to +2.508 m); original geographic data unchanged.
Geometry cost 1,928,784 triangles; performance/LOD still need actual measurement.

INSTALL only after authorization: project installer defaults to dry-run;
--install exclusively creates content/tracks/exelberg_full_v002, never overwrites.
No global config/Steam/Proton changes. v001 remains independent and untouched.
ROLLBACK: close AC, confirm exact folder identity, remove ONLY the new
content/tracks/exelberg_full_v002 folder. Preserve all other tracks/config/saves.
'''
ATTRIBUTION = '''Private-use full-route base; no game artwork, vendor code or downloaded assets.
Terrain © BEV, CC BY 4.0: https://www.bev.gv.at/
https://creativecommons.org/licenses/by/4.0/
BEV 1 m DTM, product-documented EPSG:9274 heights; bounded derived terrain,
road-footprint replacement, shoulder blending, designed/smoothed road and
explicit provisional dip correction, NOT measured asphalt or surveyed accuracy.
Route and forest-area masks © OpenStreetMap contributors, ODbL 1.0:
https://www.openstreetmap.org/copyright
https://opendatacommons.org/licenses/odbl/1-0/
Projected/local route design; forest mask selects synthetic anchors, not measured trees.
Own offline procedural texture images, opaque tree geometry, road/paint/wall
geometry, CPU preview render, generated map/outline, configs and empty AI headers.
Walls are temporary fictional safety geometry; scenery/width/camber/paint/grip
remain provisional. No public-release license clearance or authenticity claim.
Full source provenance remains separately in full_track_scene_v002/manifest.json,
full_track_inputs and full_scenery_v003 manifests, and docs/DATA_SOURCES.md.
No blend, vendor, failed exports, geographic NPZ or source inputs in this ZIP.
'''


def validate_model(data, scene, standalone):
    model = parse(data, max_file=256 * 1024 * 1024, max_nodes=4096, max_texture=8 * 1024 * 1024)
    nodes = {n['name']: n for n in model['nodes']}
    require(len(nodes) == len(model['nodes']) == scene['static_checks']['nodes'], 'Node count/duplicates')
    require(nodes[TRACK_ID]['kind'] == 1 and nodes[TRACK_ID]['parent'] is None and
            np.array_equal(nodes[TRACK_ID]['matrix'], np.eye(4).ravel()), 'Root identity')
    expected = {m['name']: m for m in scene['static_checks']['meshes']}
    require({n for n, v in nodes.items() if v['kind'] == 2} == set(expected), 'Mesh inventory')
    require(set(scene['surfaces']) == {'ROAD', 'GRAVEL', 'GRASS', 'WALL'}, 'Surface keys')
    for key, surface in scene['surfaces'].items():
        for name in surface['objects']:
            require(name in expected and name.startswith('1' + key), 'Physics inventory')
    for name, item in expected.items():
        n = nodes[name]
        require(len(n['indices']) == item['triangles'] and len(n['vertices']) == item['vertices'], 'Geometry count')
        require(bool(n['renderable']) and not n['transparent'], 'Opaque render flags')
        require(bool(name[:1].isdigit()) == item['collision'], 'Collision prefix')
    for helper in scene['helpers']:
        n = nodes[helper['name']]
        require(n['kind'] == 1 and n['parent'] == TRACK_ID and
                np.allclose(n['matrix'], helper['kn5_expected'], atol=0.0003, rtol=0), 'Helper transform')
    textures = {t['name']: t['data'] for t in model['textures']}
    require(set(textures) == set(DDS) and len(model['textures']) == 7, 'Seven DDS required')
    require(sum(map(len, textures.values())) <= 8 * 1024 * 1024, 'Aggregate texture cap')
    require(textures == standalone, 'Embedded/standalone texture mismatch')
    require(len(model['materials']) == 7, 'Material count')
    for material in model['materials']:
        require(material['shader'] == 'ksPerPixel' and material['bindings'] and
                all(b[2] in textures for b in material['bindings']), 'Diffuse references')
    return dict(independent_parse='PASS', nodes=len(nodes), mesh_nodes=len(expected),
                texture_count=7, embedded_matches_standalone=True, root=TRACK_ID,
                limits=dict(file=256*1024*1024, nodes=4096, texture=8*1024*1024), runtime_tested=False)


def build(build_dir=BUILD, evidence=EVIDENCE):
    build_dir, evidence = Path(build_dir), Path(evidence)
    require(not build_dir.exists() and not build_dir.is_symlink(), 'Build exists')
    require(not evidence.exists() and not evidence.is_symlink(), 'Evidence exists')
    require(build_dir.absolute().resolve() == build_dir.absolute() and
            evidence.absolute().resolve() == evidence.absolute(), 'Output ancestor symlink')
    scene = json.loads(SCENE.read_text())
    require(scene['track_id'] == TRACK_ID and scene['status'] == 'PASS_OFFLINE_FULL_ROUTE_BASE_NOT_FINAL_REALISM', 'Scene identity')
    outputs = {r['path']: r for r in scene['outputs']}
    def source(name):
        return outputs[name]
    base = 'exports/full_track_v002/'
    kn5_record = source(base + TRACK_ID + '.kn5')
    kn5 = verified(kn5_record)
    standalone = {n: verified(source(base + n)) for n in DDS}
    validation = validate_model(kn5, scene, standalone)  # One bounded full parse, before output creation.
    gc.collect()
    audit_record = source('data/processed/full_track_scene_v002/geometry_audit.npz')
    with np.load(io.BytesIO(verified(audit_record)), allow_pickle=False) as audit:
        xyz = audit['designed_xyz_m']
    xz = xyz[:, [0, 1]] * [1, -1]
    require(len(xz) == scene['design']['samples'] and np.isfinite(xz).all(), 'Design map source')
    transform = map_transform(xz)
    files = {TRACK_ID + '.kn5': kn5, **{'texture/' + n: standalone[n] for n in DDS}}
    def text(name, value):
        files[name] = value.encode('utf-8')
    text('README.txt', README)
    text('ATTRIBUTION.txt', ATTRIBUTION)
    text('models.ini', f'[MODEL_0]\nFILE={TRACK_ID}.kn5\nPOSITION=0,0,0\nROTATION=0,0,0\n')
    surfaces = '; Own provisional physics; see README\n'
    for i, key in enumerate(('ROAD', 'GRAVEL', 'GRASS', 'WALL')):
        s = scene['surfaces'][key]
        surfaces += (f'\n[SURFACE_{i}]\nKEY={key}\nFRICTION={s["friction"]}\n'
            f'IS_VALID_TRACK={s["is_valid_track"]}\nIS_PITLANE={s["is_pitlane"]}\n'
            'DAMPING=0\nDIRT_ADDITIVE=0\nWAV_PITCH=0\nWAV=\nSIN_HEIGHT=0\nSIN_LENGTH=0\n'
            'VIBRATION_GAIN=0\nVIBRATION_LENGTH=0\nBLACK_FLAG_TIME=0\n')
    text('data/surfaces.ini', surfaces)
    text('data/map.ini', '[PARAMETERS]\n' + '\n'.join(f'{k}={v}' for k,v in dict(
        WIDTH=1024, HEIGHT=1024, MARGIN=0, SCALE_FACTOR=transform['scale_factor'],
        X_OFFSET=transform['x_offset'], Z_OFFSET=transform['z_offset'], DRAWING_SIZE=10).items()) + '\n')
    text('data/lighting.ini', '; Own provisional daylight, not calibrated\n[LIGHTING]\nSUN_PITCH_ANGLE=45\nSUN_HEADING_ANGLE=0\n')
    text('ui/ui_track.json', json.dumps(dict(name='Exelberg Full v002 (two lanes)',
        description='Full road, private solo two-lane test base; provisional geometry and safety walls.',
        tags=['Austria', 'Hillclimb', 'A2B'], country='Austria', city='Königstetten – Marswiese',
        length='15212.525 m', width='6 m (2 x 3 m lanes)', pitboxes='1',
        author='Assetto Exelberg project', version='0.0.2'), ensure_ascii=False, indent=2) + '\n')
    files['map.png'] = imagecodecs.png_encode(draw_route(xz, transform))
    files['ui/outline.png'] = imagecodecs.png_encode(draw_route(xz, map_transform(xz, size=512)))
    preview_record = source('data/processed/full_track_scene_v002/driver.png')
    image = imagecodecs.png_decode(verified(preview_record))
    # Exact 1/2 nearest-neighbour resize of own 1280x800 CPU driver render.
    require(image.shape[:2] == (800, 1280), 'Preview dimensions')
    files['ui/preview.png'] = imagecodecs.png_encode(image[::2, ::2].copy())
    for n in ('fast_lane', 'pit_lane'):
        files[f'ai/{n}.ai'] = struct.pack('<III', 3, 0, 0)
    require(set(files) == ALLOWLIST, 'Package allowlist')
    build_dir.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    package = build_dir / TRACK_ID
    package.mkdir()
    for n, data in sorted(files.items()):
        target = package / n
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    meta = dict(schema='full_track_package_v002', track_id=TRACK_ID,
        scene_manifest=record(SCENE), source_assets=[kn5_record, *(source(base+n) for n in DDS)],
        map_source=audit_record, map_source_key='designed_xyz_m', map_transform=transform,
        preview_source=preview_record, preview_resize='nearest 1280x800 -> 640x400',
        source_validation=source('data/processed/full_track_scene_v002/independent_validation.json'),
        parser=record(ROOT / 'scripts/validate_kn5.py'), builder=record(Path(__file__).resolve()),
        validation=validation, timing=scene['timing_contract'], spawn=scene['spawn_contract'],
        road=scene['route'], files=[dict(path=n, bytes=len(d), sha256=digest(d)) for n,d in sorted(files.items())],
        file_count=len(files), bytes=sum(map(len, files.values())))
    # Validate upstream independent evidence hash too; source geometry proof stays outside ZIP.
    verified(meta['source_validation'])
    zip_path = build_dir / (TRACK_ID + '.zip')
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for n in sorted(files):
            archive.write(package / n, TRACK_ID + '/' + n)
    with zipfile.ZipFile(zip_path) as archive:
        require(set(archive.namelist()) == {TRACK_ID+'/'+n for n in files}, 'ZIP allowlist')
        for r in meta['files']:
            with archive.open(TRACK_ID + '/' + r['path']) as stream:
                require(transfer(stream) == (r['bytes'], r['sha256']), 'ZIP hash/size')
    meta['zip'] = record(zip_path)
    meta['zip']['entries'] = len(files)
    manifest = evidence / 'manifest.json'
    with manifest.open('x') as stream:
        json.dump(meta, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    validate_source(package, manifest)
    print(json.dumps(dict(package=str(package), zip=meta['zip'], file_count=len(files), bytes=meta['bytes']), indent=2))
    return meta


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()


if __name__ == '__main__':
    main()
