#!/usr/bin/env python3
"""Fresh factory-headless AC scene; project-local only, no overwrite or install.

--check-only performs offline input/tool/no-overwrite checks without bpy.
--validate-only independently parses the NEW KN5 and verifies its manifest.
No vendor parser is used for validation; validate_kn5.validate_candidate is NOT used.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from export_kn5_prototype import verify_install, sha256, refuse_existing, ALLOWLIST, COMMIT

TRACK_ID = 'exelberg_north_proto_v001'
SOURCE = ROOT / 'blender/northern_hairpins_kn5_v001.blend'
COPY = ROOT / 'blender/northern_hairpins_ac_test_v001.blend'
OUTPUT = ROOT / 'exports/ac_test_v001'
KN5 = OUTPUT / (TRACK_ID + '.kn5')
EVIDENCE = ROOT / 'data/processed/ac_test_scene'
AUDIT = ROOT / 'data/processed/prototype_scene/geometry_audit.npz'
OLD_KN5 = ROOT / 'exports/kn5_prototype_v001/northern_hairpins_kn5_v001.kn5'
EXPECTED = ROOT / 'data/processed/kn5_test/expected_geometry.npz'
NAMES = dict(zip(ALLOWLIST, ('1ROAD', '1GRAVEL_L', '1GRAVEL_R', '1GRASS_TERRAIN')))
SPAWNS = ('AC_PIT_0', 'AC_START_0', 'AC_HOTLAP_START_0')
TIMING = ('AC_TIME_0_L', 'AC_TIME_0_R')
SURFACES = {
    'ROAD': dict(objects=['1ROAD'], friction=1.0, is_valid_track=1, is_pitlane=0,
                 width_m=6.0),
    'GRAVEL': dict(objects=['1GRAVEL_L', '1GRAVEL_R'], friction=0.7,
                   is_valid_track=0, is_pitlane=0, width_each_m=0.75),
    'GRASS': dict(objects=['1GRASS_TERRAIN_SUB0', '1GRASS_TERRAIN_SUB1'],
                  friction=0.6, is_valid_track=0, is_pitlane=0),
}
PINNED = {
    SOURCE: '09a94568007a070cd31767cbe08b93eea5471dcad4b10e424bb26f89fb1a24fc',
    AUDIT: '97c93508530f7c13dbfca2b1dd367f0062c8d2ee4d116914e0997f74e92ccaec',
    OLD_KN5: '8681e75aa707c359c3f340fd719db088b3c40aa47b2900b137c8d87b3bb7c37a',
    EXPECTED: '65c5038dbde6fa4bcc8c179d65c2027f0632278d72fd772ec0e443b56a03c430',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative(path):
    return str(Path(path).relative_to(ROOT))


def artifact(path):
    return dict(path=relative(path), bytes=path.stat().st_size, sha256=sha256(path))


def surface_key(name):
    """Exact export allowlist: no digit-prefix/fallback/substring guesswork."""
    for key, config in SURFACES.items():
        if name in config['objects']:
            return key
    raise ValueError('Unapproved physical mesh: ' + name)


def station(points, distance):
    """Interpolate designed XY arclength, not original chainage or raw route."""
    import numpy as np
    p = np.asarray(points, dtype=float)
    require(p.ndim == 2 and p.shape[1] == 3 and len(p) >= 2 and np.isfinite(p).all(),
            'Invalid station points')
    ds = np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1)
    require((ds > 1e-8).all(), 'Repeated station')
    s = np.r_[0., np.cumsum(ds)]
    require(math.isfinite(distance) and 0 <= distance <= s[-1], 'Station outside road')
    i = min(int(np.searchsorted(s, distance, side='right') - 1), len(p) - 2)
    t = float((distance - s[i]) / ds[i])
    delta = p[i + 1] - p[i]
    forward = delta[:2] / ds[i]
    return dict(index=i, fraction=t, point=(p[i] + t * delta).tolist(),
                forward_xy=forward.tolist(), grade_percent=float(delta[2] / ds[i] * 100),
                distance_from_start_m=float(distance), distance_to_end_m=float(s[-1] - distance))


def spawn_frames(point, forward_xy):
    """Independent basis construction, never exporter convert_matrix or Euler.

    Blender columns: right, +Y forward, +Z up. KN5 rows: right, up, backward.
    Translation occupies KN5 indices 12:15. C(x,y,z)=(x,z,-y).
    """
    import numpy as np
    f = np.asarray(forward_xy, dtype=float)
    require(f.shape == (2,) and np.isfinite(f).all() and np.linalg.norm(f) > 1e-8,
            'Undefined spawn heading')
    f /= np.linalg.norm(f)
    x, y, z = point
    fx, fy = f
    blender = [[fy, fx, 0., x], [-fx, fy, 0., y], [0., 0., 1., z], [0., 0., 0., 1.]]
    kn5 = [fy, 0., fx, 0., 0., 1., 0., 0., -fx, 0., fy, 0., x, z, -y, 1.]
    return blender, kn5


def timing_frames(point):
    """Observed Trento TIME_0 row axes, deliberately not the spawn basis."""
    x, y, z = point
    blender = [[1., 0., 0., x], [0., 0., 1., y], [0., -1., 0., z], [0., 0., 0., 1.]]
    kn5 = [1., 0., 0., 0., 0., 0., -1., 0., 0., 1., 0., 0., x, z, -y, 1.]
    return blender, kn5


def helper_data(points, chainages):
    import numpy as np
    from prototype_geometry import station_normals
    total = float(np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1).sum())
    normals = station_normals(points)
    records = []
    for name, distance, offset in [(n, 25., 0.) for n in SPAWNS] + [
            (TIMING[0], total - 15., 3.), (TIMING[1], total - 15., -3.)]:
        s = station(points, distance)
        i, t = s['index'], s['fraction']
        # Interpolate actual ribbon edge offsets, not a newly yawed road cross-section.
        point = np.array(s['point'])
        point[:2] += offset * ((1 - t) * normals[i] + t * normals[i + 1])
        surface_z = float(point[2])
        point[2] += 0.4
        b, k = spawn_frames(point, s['forward_xy']) if name in SPAWNS else timing_frames(point)
        records.append(dict(name=name, kind=1, station=s,
            chainage_3035_m=float((1 - t) * chainages[i] + t * chainages[i + 1]),
            lateral_offset_left_m=offset, surface_z_blender_m=surface_z,
            provisional_vertical_clearance_m=0.4, blender_matrix_rows=b,
            kn5_expected_row_axes_translation=k,
            orientation=('flat yaw; Blender +Y forward +Z up; KN5 -Z forward +Y up'
                         if name in SPAWNS else 'Trento TIME_0 observed fixed axes; endpoint semantics unverified')))
    return records


def check_inputs(new=True):
    install = verify_install()
    for path, expected in PINNED.items():
        require(sha256(path) == expected, 'Changed pinned source: ' + str(path))
    if new:
        refuse_existing([COPY])
        for directory in (OUTPUT, EVIDENCE):
            if directory.exists():
                # Explicit archive of this task's failed first attempt only; no force/reuse.
                require(not directory.is_symlink() and directory.is_dir(), 'Unsafe output directory')
                require(all(p.name == 'failed_attempt_001' and p.is_dir() and not p.is_symlink()
                            for p in directory.iterdir()), 'Refusing existing output: ' + str(directory))
    return install


def protected_hashes():
    """Read-only snapshot of source data, old exports, code and Blender settings."""
    paths = set(PINNED)
    for directory in ('blender', 'exports', 'data', 'scripts', 'tests', 'docs', 'tools/vendor/kn5_studio'):
        for path in (ROOT / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and not any(
                    path == p or path.is_relative_to(p) for p in (OUTPUT, COPY, EVIDENCE)):
                paths.add(path)
    # Existing snapshot enumerates preferences and extensions; never connect to GUI.
    previous = json.loads((ROOT / 'data/processed/kn5_test/source_hashes_before.json').read_text())
    paths.update(Path(p) for p in previous if Path(p).is_file())
    return {str(p): sha256(p) for p in sorted(paths)}


def mesh_fingerprint(obj):
    """Scene geometry, UV, corner normals, smoothing, transforms/parent; names excluded."""
    import numpy as np
    m = obj.data
    m.calc_loop_triangles()
    h = hashlib.sha256()
    def add(a):
        h.update(np.asarray(a).tobytes())
    add(np.array([v.co[:] for v in m.vertices], dtype='<f4'))
    add(np.array([t.vertices[:] for t in m.loop_triangles], dtype='<i4'))
    for layer in m.uv_layers:
        h.update(layer.name.encode())
        add(np.array([uv.uv[:] for uv in layer.data], dtype='<f4'))
    add(np.array([n.vector[:] for n in m.corner_normals], dtype='<f4'))
    add(np.array([p.use_smooth for p in m.polygons], dtype='?'))
    add(np.array(obj.matrix_world, dtype='<f4'))
    h.update(str(obj.parent.name if obj.parent else None).encode())
    return h.hexdigest()


def independent_checks(helpers):
    """New candidate-specific validation using existing independent binary parser."""
    import numpy as np
    from validate_kn5 import parse, bounded_read, load_source, compare_corners, validate_dds, COLORS
    model = parse(bounded_read(KN5))
    old = parse(bounded_read(OLD_KN5))
    nodes = {n['name']: n for n in model['nodes']}
    old_nodes = {n['name']: n for n in old['nodes']}
    meshes = SURFACES['ROAD']['objects'] + SURFACES['GRAVEL']['objects'] + SURFACES['GRASS']['objects']
    require(set(nodes) == {TRACK_ID, '1GRASS_TERRAIN', *meshes, *SPAWNS, *TIMING}, 'Node allowlist')
    require(model['root']['name'] == TRACK_ID and model['root']['parent'] is None, 'Root track ID')
    for name in (TRACK_ID, '1GRASS_TERRAIN'):
        n = nodes[name]
        require(n['kind'] == 1 and np.array_equal(n['matrix'], np.eye(4).ravel()), 'Wrapper transform')
    require(nodes['1GRASS_TERRAIN']['parent'] == TRACK_ID, 'Terrain wrapper parent')
    helper_evidence = []
    for helper in helpers:
        n = nodes[helper['name']]
        expected = np.asarray(helper['kn5_expected_row_axes_translation'])
        actual = n['matrix'].astype(float)
        require(n['kind'] == 1 and n['active'] == 1 and not n['children'] and n['parent'] == TRACK_ID,
                'Helper must be active root-child dummy only')
        require(np.allclose(actual, expected, rtol=0, atol=0.0003), 'Actual exported helper basis/translation differs')
        require(np.allclose(actual.reshape(4, 4)[:3, :3], expected.reshape(4, 4)[:3, :3], rtol=0, atol=2e-6),
                'Actual exported helper axes differ')
        helper_evidence.append(dict(name=n['name'], actual_kn5_row_axes_translation=actual.tolist(),
                                    max_abs_error=float(np.abs(actual - expected).max()), status='PASS'))
    # Materials/textures must be identical to the previous explicit three-DDS export.
    require(len(model['materials']) == len(model['textures']) == 3, 'Material/texture count')
    for i, (a, b) in enumerate(zip(model['textures'], old['textures'])):
        require(a == b, 'Texture payload/identity changed')
        require((OUTPUT / a['name']).read_bytes() == a['data'], 'Standalone DDS differs')
        validate_dds(a['data'], COLORS[i])
    for a, b in zip(model['materials'], old['materials']):
        require({k: v for k, v in a.items() if k != 'properties'} ==
                {k: v for k, v in b.items() if k != 'properties'}, 'Material changed')
        require(a['properties'].keys() == b['properties'].keys() and all(
            np.array_equal(a['properties'][k], b['properties'][k]) for k in a['properties']), 'Shader property changed')
    source = load_source(EXPECTED)
    evidence = []
    for i, (original, renamed) in enumerate(NAMES.items()):
        names = [renamed] if i < 3 else [renamed + '_SUB0', renamed + '_SUB1']
        chunks = []
        for j, name in enumerate(names):
            n = nodes[name]
            old_name = original if i < 3 else original + '_SUB' + str(j)
            o = old_nodes[old_name]
            require(n['kind'] == 2 and not n['children'] and n['parent'] ==
                    (TRACK_ID if i < 3 else '1GRASS_TERRAIN'), 'Mesh hierarchy')
            require(surface_key(name) in SURFACES, 'Explicit surface key missing')
            for field in ('active', 'cast_shadows', 'visible', 'transparent', 'renderable', 'layer', 'material'):
                require(n[field] == o[field], 'Mesh flags/material changed')
            require([n[k] for k in ('active', 'cast_shadows', 'visible', 'transparent', 'renderable', 'layer')]
                    == [1, 1, 1, 0, 1, 0], 'Physical/visible mesh flags')
            require(np.array_equal(n['lod_sphere'], o['lod_sphere']) and
                    np.array_equal(n['lod_sphere'][:2], [0., 0.]), 'LOD/bounds changed')
            # Positions, normals, UVs and indices are bit-exact. Recomputed terrain
            # tangents after source .blend reload differ by <=1.8e-7; bound separately.
            require(np.array_equal(n['vertices'][:, :8], o['vertices'][:, :8]) and
                    np.array_equal(n['indices'], o['indices']), 'Surface geometry/normal/UV/index stream changed')
            tangent_error = float(np.max(np.abs(n['vertices'][:, 8:] - o['vertices'][:, 8:])))
            require(tangent_error <= 2e-7, 'Tangent recomputation exceeds bounded float32 tolerance')
            v = n['vertices']
            require(np.max(np.abs(np.linalg.norm(v[:, 8:], axis=1) - 1)) < 1e-5 and
                    np.max(np.abs(np.sum(v[:, 3:6] * v[:, 8:], axis=1))) < 1e-5, 'Tangent frame quality')
            tri = v[n['indices']]
            cross = np.cross(tri[:, 1, :3] - tri[:, 0, :3], tri[:, 2, :3] - tri[:, 0, :3])
            require((cross[:, 1] > 0).all(), 'Non-upward triangles')
            chunks.append(tri[:, :, [0, 1, 2, 6, 7]])
            evidence.append(dict(name=name, original_name=old_name, surface_key=surface_key(name),
                vertices=len(v), triangles=len(tri), material_id=n['material'], lod_in=0, lod_out=0,
                flags={k: n[k] for k in ('active', 'visible', 'renderable', 'cast_shadows', 'transparent', 'layer')},
                bounds_kn5=[v[:, :3].min(0).tolist(), v[:, :3].max(0).tolist()],
                geometry_normal_uv_indices='EXACT_PREVIOUS_KN5_PASS',
                max_abs_tangent_recompute_error=tangent_error))
        xyz = source[f'mesh{i}_vertices'][:, [0, 2, 1]].copy()
        xyz[:, 2] *= -1
        uv = source[f'mesh{i}_corner_uv'].copy()
        uv[:, :, 1] = 1 - uv[:, :, 1]
        expected = np.concatenate((xyz[source[f'mesh{i}_triangles']], uv), axis=2)
        compare_corners(expected, np.concatenate(chunks))
    require(sum(m['triangles'] for m in evidence) == 230400, 'Triangle total')
    return dict(status='PASS_INDEPENDENT_STATIC_ONLY', bytes_consumed=model['bytes_consumed'],
                node_count=len(nodes), mesh_nodes=evidence, helpers=helper_evidence,
                source_oriented_triangle_uv_comparison='EXACT_FLOAT32_MULTISET_PASS',
                texture_count=3, material_count=3, ac_runtime_tested=False)


def run(install):
    import bpy
    import numpy as np
    from mathutils import Matrix
    require(bpy.app.background and not bpy.data.filepath, 'Requires separate factory-headless Blender')
    before = protected_hashes()
    OUTPUT.mkdir(exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    with (EVIDENCE / '.build_started').open('x') as marker:
        marker.write('Exclusive one-shot reservation; no rerun/overwrite.\n')
    writes = []
    def audit(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'}:
            raise PermissionError('Blocked side effect: ' + event)
        if event == 'open':
            path, mode, flags = args
            writing = (mode and any(c in mode for c in 'wax+')) or (flags and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not isinstance(path, int):
                path = Path(path).resolve()
                require(path.is_relative_to(OUTPUT) or path.is_relative_to(EVIDENCE), 'Blocked Python write: ' + str(path))
                writes.append(relative(path))
    # Native Blender save is not covered by Python audit; sole destination is fresh COPY.
    sys.addaudithook(audit)
    started = time.monotonic()
    spec = importlib.util.spec_from_file_location('kn5_studio', install / '__init__.py',
                                                submodule_search_locations=[str(install)])
    addon = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = addon
    spec.loader.exec_module(addon)
    addon.register()  # In-process only, no enable/save preferences.
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False, use_scripts=False)
    original_meshes = {o.name: mesh_fingerprint(o) for o in bpy.data.objects if o.type == 'MESH'}
    original_objects = set(o.name for o in bpy.data.objects)
    with np.load(AUDIT, allow_pickle=False) as data:
        points = data['designed_xyz_m']
        chainages = data['chainage_3035_m']
        require(np.allclose(data['designed_arclength_xy_m'], np.r_[0., np.cumsum(
            np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1))], atol=1e-8, rtol=0), 'Audit arclength mismatch')
    report = json.loads((ROOT / 'data/processed/prototype_scene/report.json').read_text())
    require(report['section_chainage_3035_m'] == [1000., 2500.] and report['design']['width_m'] == 6,
            'Unexpected prototype source/design')
    objects = []
    for original, renamed in NAMES.items():
        obj = bpy.data.objects[original]
        obj.data.calc_loop_triangles()
        require(obj.type == 'MESH' and not obj.parent and not obj.modifiers and
                (len(obj.data.vertices), len(obj.data.loop_triangles)) == ALLOWLIST[original][:2], 'Unexpected source mesh')
        obj.name = renamed
        # Preserve all geometry/materials; explicitly set render flags, not a fictitious physical API flag.
        ac = obj.assettoCorsa
        ac.visible = ac.renderable = ac.cast_shadows = True
        ac.transparent = False
        ac.layer = 0
        ac.lod_in = ac.lod_out = 0
        objects.append(obj)
    road = np.array([v.co[:] for v in objects[0].data.vertices], dtype=np.float32).reshape(-1, 5, 3)
    require(np.array_equal(road[:, 2], points.astype(np.float32)), 'Audit route not actual road centre')
    helpers = helper_data(points, chainages)
    collection = bpy.data.collections.new('AC_TEST_HELPERS_EXPORT')
    bpy.context.scene.collection.children.link(collection)
    for helper in helpers:
        obj = bpy.data.objects.new(helper['name'], None)
        collection.objects.link(obj)
        obj.empty_display_type = 'ARROWS'
        obj.empty_display_size = 1.0
        obj.matrix_world = Matrix(helper['blender_matrix_rows'])
        objects.append(obj)
    for name in SPAWNS:
        h = next(h for h in helpers if h['name'] == name)
        require(h['station']['distance_from_start_m'] >= 15 and h['station']['distance_from_start_m'] <= 30,
                'Spawn placement outside requested interval')
    # A conservative reference envelope is a static check, not actual car clearance.
    spawn = helpers[0]
    center = np.array(spawn['blender_matrix_rows'])[:3, 3]
    f = np.array(spawn['station']['forward_xy'])
    right = np.array([f[1], -f[0]])
    footprint = []
    for distance in (22., 28.):
        sample = station(points, distance)
        delta = np.array(sample['point']) - center
        lateral = abs(float(delta[:2] @ right))
        vertical = float(center[2] - sample['point'][2])
        require(lateral + 1. < 3. and vertical > 0.1, 'Provisional reference envelope clearance failed')
        footprint.append(dict(distance_from_start_m=distance, centerline_yaw_lateral_error_m=lateral,
                              flat_pivot_to_surface_vertical_m=vertical))
    excluded = sorted(o.name for o in bpy.context.scene.objects if o not in objects)
    # Copy explicit original DDS payloads, never decode or acquire textures.
    old = json.loads((ROOT / 'data/processed/kn5_test/report.json').read_text())
    for texture in old['textures']:
        path = OLD_KN5.parent / texture['name']
        require(sha256(path) == texture['sha256'], 'Original DDS changed')
        with (OUTPUT / texture['name']).open('xb') as f:
            f.write(path.read_bytes())
    require(not addon.materials.audit_texture_bindings(objects[:4], 'EMBEDDED_DDS'), 'Texture bindings not explicit')
    options = dict(version=5, texture_mode='EMBEDDED_DDS', target_objects=objects,
                   apply_modifiers=False, auto_detect_materials=False, auto_fix_wheels=False, selection_only=False)
    exporter = addon.exporter.KN5Exporter(bpy.context, str(KN5), options)
    model = exporter.export()
    require(not exporter.warnings, 'Exporter warnings: ' + str(exporter.warnings))
    with KN5.open('xb') as f:
        model.to_stream(f)
    static = independent_checks(helpers)
    for name, expected in original_meshes.items():
        require(mesh_fingerprint(bpy.data.objects[NAMES.get(name, name)]) == expected, 'In-memory geometry changed')
    refuse_existing([COPY])
    bpy.ops.wm.save_as_mainfile(filepath=str(COPY), check_existing=True, copy=True)
    # Actual saved-copy reload in the isolated process, never GUI or original save.
    bpy.ops.wm.open_mainfile(filepath=str(COPY), load_ui=False, use_scripts=False)
    require(set(o.name for o in bpy.data.objects) == {NAMES.get(n, n) for n in original_objects} | set(SPAWNS + TIMING),
            'Saved copy object inventory changed')
    for name, expected in original_meshes.items():
        require(mesh_fingerprint(bpy.data.objects[NAMES.get(name, name)]) == expected, 'Saved mesh fingerprint differs')
    for helper in helpers:
        actual = np.array(bpy.data.objects[helper['name']].matrix_world)
        require(np.allclose(actual, helper['blender_matrix_rows'], atol=0.0003, rtol=0), 'Saved helper matrix differs')
        helper['saved_blender_matrix_rows'] = actual.tolist()
    for objname, material in zip(NAMES.values(), ('KN5_Asphalt', 'KN5_Gravel', 'KN5_Gravel', 'KN5_Terrain')):
        require(bpy.data.objects[objname].data.materials[0].name == material, 'Saved material changed')
    require(not addon.materials.audit_texture_bindings([bpy.data.objects[n] for n in NAMES.values()], 'EMBEDDED_DDS'),
            'Saved texture binding mismatch')
    after = {p: sha256(p) for p in before}
    require(before == after, 'Protected source/settings hash changed')
    verify_install()
    manifest = dict(schema='assetto_exelberg_ac_test_scene', version=1, track_id=TRACK_ID,
        purpose='LOCAL solo practice packaging candidate; NOT installed or game-validated',
        status='PASS_OFFLINE_SCENE_EXPORT', inputs=[artifact(p) for p in PINNED],
        source_report=artifact(ROOT / 'data/processed/prototype_scene/report.json'),
        stock_conventions=artifact(ROOT / 'data/processed/ac_reference_metadata/stock_tracks.json'),
        builder=artifact(Path(__file__)),
        outputs=[artifact(COPY), artifact(KN5)] + [artifact(p) for p in sorted(OUTPUT.glob('*.dds'))],
        expected_geometry=dict(**artifact(EXPECTED), prefixes={f'mesh{i}': dict(original=o, renamed=n)
                                                       for i, (o, n) in enumerate(NAMES.items())}),
        original_to_export_object_names=NAMES, export_objects=list(NAMES.values()) + list(SPAWNS + TIMING),
        excluded_objects=excluded, source_mesh_fingerprints=original_meshes,
        coordinates=dict(horizontal_crs='EPSG:25833', vertical_crs='EPSG:9274 product-documented, not surveyed',
            local_origin_enh_m=[589500, 5346800, 300], blender_axes='X east / Y north / Z up',
            kn5_mapping='(X,Y,Z) -> (X,Z,-Y)', units='metres; scale 1', uv_mapping='(u,v) -> (u,1-v)',
            kn5_matrix_layout='row-vector axes rows 0/1/2; translation indices 12/13/14; world=local*parent_world',
            section_chainage_3035_m=[1000, 2500], full_route_endpoints_changed=False),
        helpers=helpers, surfaces=SURFACES,
        physics_handoff=dict(explicit_keys_required=['ROAD', 'GRAVEL', 'GRASS'],
            assumptions='Widths, friction, valid-track and pitlane flags are provisional, unmeasured, untested.',
            collision='Digit-prefix 1 on all reachable surface meshes including terrain chunks; no separate KN5 physical flag.',
            roughness='No measured roughness; zero sinusoidal/vibration and damping are initial packaging assumptions.',
            pitlane='AC_PIT_0 on ROAD, not separate pitlane geometry; is_pitlane=0 for all proposed keys.'),
        geometry_limitations=[
            'OSM alignment and BEV bare-earth heights are provisional, not surveyed asphalt or imagery-approved alignment.',
            'Original smoothed 6 m road, 0 camber; 0.75 m shoulders retained without geometry edits.',
            'Artificial terrain lowered >=0.25 m under ribbon, max lowering 3.243515 m; now collision-intended, NOT a joined safe verge.',
            'No staging, barriers or extended run-out added; 15 m after finish is not high-speed stopping certification.',
            'Coincident pit/start/hotlap pivots intentionally for solo only; no multiplayer or AI.'],
        timing_handoff=dict(fixture='Trento A2B/hillclimb names: AC_TIME_0_L/R only, near remote finish',
            gate_width_m=float(np.linalg.norm(np.array(helpers[3]['blender_matrix_rows'])[:3, 3] -
                                             np.array(helpers[4]['blender_matrix_rows'])[:3, 3])),
            distance_before_section_end_m=15, orientation='Observed Trento fixed axes, not spawn-style up.',
            semantics='Endpoint-pair interpretation and session/timer/restart workflow UNVERIFIED; no timing promises.'),
        spawn_handoff=dict(distance_after_section_start_m=25, clearance_m=0.4, provisional=True,
            pitch='Flat yaw, not grade-aligned. Grade recorded per interpolated segment; test car settling and nose/tail clearance.',
            footprint_check='Reference envelope only: +/-3 m longitudinal and +/-1 m lateral fits 6 m road at spawn; not a measured car.',
            reference_envelope_samples=footprint, road_before_reference_rear_m=22, road_after_finish_m=15),
        lod='Retain LOD_IN=LOD_OUT=0: stock zero/zero renderable evidence; no engine validation claimed.',
        static_checks=static, saved_copy_reload='PASS: all 6 mesh fingerprints, 37 objects, helper transforms and bindings',
        source_preservation=dict(status='PASS', protected_files=len(before), hashes_before=before, hashes_after=after,
                                 addon_unchanged=True, preferences_saved=False),
        runtime=dict(blender=bpy.app.version_string, build=bpy.app.build_hash.decode(), addon=list(addon.bl_info['version']),
                     addon_commit=COMMIT, installed_package=str(install),
                     factory_headless=True, elapsed_seconds=time.monotonic() - started,
                     python_write_audit=writes, native_blender_save_destination=relative(COPY)),
        untested=['Windows AC loading', 'spawn direction and settling', 'collision/friction/invalid track behavior',
                  'LOD/culling and shaders', 'reset to pits/restarts', 'point-to-point timing/session selection',
                  'GUI visual inspection', 'performance/VR'])
    with (EVIDENCE / 'manifest.json').open('x') as f:
        json.dump(manifest, f, indent=2, allow_nan=False)
        f.write('\n')
    print('PASS', relative(KN5), '5 helper dummies; independent matrices/geometry checks; saved copy reloaded', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check-only', action='store_true')
    group.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
    if args.validate_only:
        check_inputs(new=False)
        manifest = json.loads((EVIDENCE / 'manifest.json').read_text())
        for record in manifest['outputs']:
            p = ROOT / record['path']
            require(artifact(p) == record, 'Output hash/size differs')
        result = independent_checks(manifest['helpers'])
        print(json.dumps(result, indent=2, allow_nan=False))
        return
    install = check_inputs()
    if args.check_only:
        print('PASS pinned reviewed add-on, source hashes, fresh output paths')
    else:
        run(install)


if __name__ == '__main__':
    main()
