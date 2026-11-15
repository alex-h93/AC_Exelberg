#!/usr/bin/env python3
"""Independent, deliberately narrow KN5 v5 static validator (no vendor imports).

Not a general KN5 loader or game-compatibility certification. See
 docs/validation/KN5_INDEPENDENT_VALIDATION.md for reference evidence and limits.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
KN5 = ROOT / 'exports/kn5_prototype_v001/northern_hairpins_kn5_v001.kn5'
SOURCE = ROOT / 'data/processed/kn5_test/expected_geometry.npz'
REPORT = ROOT / 'data/processed/kn5_test/report.json'
OUTPUT = ROOT / 'data/processed/kn5_test/independent_validation.json'
MAX_FILE = 32 * 1024 * 1024
ROOT_NAME = 'northern_hairpins_kn5_v001'
TERRAIN = 'VISUAL_TERRAIN_DERIVED_LOWERED'
SOURCES = ('1ROAD', 'PROVISIONAL_SHOULDER_L', 'PROVISIONAL_SHOULDER_R', TERRAIN)
MESHES = SOURCES[:3] + (TERRAIN + '_SUB0', TERRAIN + '_SUB1')
COLORS = ((48, 50, 52, 255), (120, 110, 90, 255), (65, 88, 52, 255))
KINDS = ('asphalt', 'gravel', 'terrain')
REFERENCE = {
    'repository': 'gro-ove/actools',
    'url': 'https://raw.githubusercontent.com/gro-ove/actools/master/AcTools/Kn5File/Kn5Basic.cs',
    'bytes': 71427,
    'sha256': 'bb0759c1c8d9529b9b536cc38fe3486ae0b7df15e1bd5b12e0cf7660402afeab',
    'retrieved_utc_date': '2026-10-25',
    'http_operation': {'requests': 3, 'successful_body_bytes': 72676,
                       'results': ['Kn5Reader.cs: HTTP 404, body not read',
                                   'Kn5.cs: HTTP 200, 1249 bytes',
                                   'Kn5Basic.cs: HTTP 200, 71427 bytes'],
                       'read_only': True, 'source_executed': False},
    'scope': 'Independent AcTools reader field order/widths; inherited string primitive not inspected; no runtime/game proof',
}


class InvalidKN5(ValueError):
    """Malformed input or failed candidate invariant."""


def require(condition, message):
    if not condition:
        raise InvalidKN5(message)


def bounded_read(path, *, max_file=None):
    max_file = MAX_FILE if max_file is None else max_file
    require(0 < max_file <= 256 * 1024 * 1024, 'unsafe file budget')
    with Path(path).open('rb') as stream:
        require(Path(path).stat().st_size <= max_file, 'file size limit')
        data = stream.read(max_file + 1)
    require(len(data) <= max_file, 'file size limit')
    return data


class Reader:
    def __init__(self, data, *, max_file=None, max_nodes=64):
        max_file = MAX_FILE if max_file is None else max_file
        require(0 < max_file <= 256 * 1024 * 1024 and 0 < max_nodes <= 4096, 'unsafe parser budget')
        require(len(data) <= max_file, 'file size limit')
        self.data = memoryview(data)
        self.pos = 0
        self.nodes_left = max_nodes
        self.max_children = max_nodes - 1

    def take(self, size):
        require(0 <= size <= len(self.data) - self.pos, f'truncated at {self.pos}: need {size}')
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def number(self, fmt='I'):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def count(self, maximum, stride=1):
        count = self.number()
        require(count <= maximum, f'count limit at {self.pos - 4}: {count}')
        require(count * stride <= len(self.data) - self.pos, 'count exceeds remaining bytes')
        return count

    def flag(self, fmt='B'):
        value = self.number(fmt)
        require(value in (0, 1), 'invalid boolean flag')
        return value

    def string(self):
        length = self.count(4096)
        try:
            value = bytes(self.take(length)).decode('utf-8', errors='strict')
        except UnicodeDecodeError as error:
            raise InvalidKN5('invalid UTF-8') from error
        require(value and '\0' not in value, 'empty/NUL string')
        return value

    def floats(self, count):
        values = np.frombuffer(self.take(count * 4), dtype='<f4')
        require(np.isfinite(values).all(), 'nonfinite float')
        return values

    def node(self, depth=0, parent=None):
        require(depth <= 16 and self.nodes_left > 0, 'recursive node budget')
        self.nodes_left -= 1
        kind = self.number()
        require(kind in (1, 2), 'unsupported node type')
        node = dict(kind=kind, name=self.string(), parent=parent)
        children = self.count(self.max_children, 13)
        require(children <= self.nodes_left, 'child node budget')
        node['active'] = self.flag()
        if kind == 1:
            node['matrix'] = self.floats(16)
        else:
            node['cast_shadows'] = self.flag()
            node['visible'] = self.flag()
            node['transparent'] = self.flag()
            count = self.count(65535, 44)
            require(count > 0, 'empty mesh')
            node['vertex_offset'] = self.pos
            node['vertices'] = self.floats(count * 11).reshape(count, 11)
            count = self.count(3_000_000, 2)
            require(count > 0 and count % 3 == 0, 'invalid triangle index count')
            node['index_offset'] = self.pos
            node['indices'] = np.frombuffer(self.take(count * 2), dtype='<u2').reshape(-1, 3)
            require(int(node['indices'].max()) < len(node['vertices']), 'index out of range')
            node['material'] = self.number()
            node['layer'] = self.number()
            node['lod_sphere_offset'] = self.pos
            node['lod_sphere'] = self.floats(6)
            require(node['lod_sphere'][5] >= 0, 'negative sphere radius')
            node['renderable'] = self.flag()
        node['children'] = [self.node(depth + 1, node['name']) for _ in range(children)]
        return node


def parse(data, *, max_file=None, max_nodes=64, max_texture=1024 * 1024):
    require(0 < max_texture <= 8 * 1024 * 1024, 'unsafe texture budget')
    reader = Reader(data, max_file=max_file, max_nodes=max_nodes)
    require(bytes(reader.take(6)) == b'sc6969', 'bad magic')
    require(reader.number() == 5, 'only KN5 v5 supported')
    textures = []
    for _ in range(reader.count(32, 12)):
        active = reader.flag('I')
        name = reader.string()
        size = reader.count(max_texture)
        textures.append(dict(active=active, name=name, data=bytes(reader.take(size))))
    materials = []
    for _ in range(reader.count(32, 18)):
        material = dict(name=reader.string(), shader=reader.string(), blend=reader.number('B'),
                        alpha=reader.flag(), depth=reader.number())
        require(material['blend'] in (0, 1, 2) and material['depth'] in (0, 1, 2), 'unknown material enum')
        properties = {}
        for _ in range(reader.count(64, 44)):
            name = reader.string()
            require(name not in properties, 'duplicate property')
            properties[name] = reader.floats(10)
        material['properties'] = properties
        material['bindings'] = [(reader.string(), reader.number(), reader.string())
                                for _ in range(reader.count(32, 12))]
        materials.append(material)
    root = reader.node()
    require(reader.pos == len(data), 'trailing bytes')
    nodes = []

    def flatten(node):
        nodes.append(node)
        for child in node['children']:
            flatten(child)
    flatten(root)
    require(len({n['name'] for n in nodes}) == len(nodes), 'duplicate node names')
    names = [t['name'] for t in textures]
    require(len(set(names)) == len(names), 'duplicate texture names')
    require(len({m['name'] for m in materials}) == len(materials), 'duplicate materials')
    for material in materials:
        require(all(b[2] in names for b in material['bindings']), 'missing texture binding')
    for node in nodes:
        if node['kind'] == 2:
            require(node['material'] < len(materials), 'material out of range')
    return dict(textures=textures, materials=materials, root=root, nodes=nodes, bytes_consumed=reader.pos)


def validate_dds(data, rgba):
    require(len(data) == 192 and data[:4] == b'DDS ', 'DDS magic/size')
    header = struct.unpack('<31I', data[4:128])
    require(header[:7] == (124, 0x100F, 4, 4, 16, 0, 1), 'DDS dimensions/flags/pitch/mips')
    require(header[7:18] == (0,) * 11, 'DDS reserved fields')
    require(header[18:26] == (32, 0x41, 0, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000), 'DDS pixel format')
    require(header[26:] == (0x1000, 0, 0, 0, 0), 'DDS caps')
    r, g, b, a = rgba
    require(data[128:] == bytes((b, g, r, a)) * 16, 'DDS placeholder pixels')


def canonical_triangles(corners):
    """Sorted exact float32 oriented XYZ+UV triangle multiset, cyclic only.

    Choose the lexicographically smallest corner as start (candidate triangles
    are nondegenerate, hence distinct XYZ). Retain the other two in order.
    Signed zero is normalized; no tolerance/rounding hides UV or winding errors.
    """
    c = np.array(corners, dtype='<f4', copy=True)
    require(c.ndim == 3 and c.shape[1:] == (3, 5) and np.isfinite(c).all(), 'bad corner array')
    c[c == 0] = 0
    start = np.lexsort(tuple(c[:, :, k] for k in range(4, -1, -1)), axis=1)[:, 0]
    order = (start[:, None] + np.arange(3)) % 3
    rows = np.take_along_axis(c, order[:, :, None], axis=1).reshape(-1, 15).copy()
    return np.sort(rows.view(np.dtype((np.void, 60))).ravel())


def compare_corners(expected, actual):
    require(expected.shape == actual.shape, 'source triangle/corner count differs')
    require(np.array_equal(canonical_triangles(expected), canonical_triangles(actual)),
            'oriented source triangle + corner UV multiset differs')


def load_source(path):
    require(Path(path).stat().st_size <= MAX_FILE, 'NPZ file size limit')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len(entries) == 12 and sum(e.file_size for e in entries) <= 64 * 1024 * 1024,
                'NPZ expansion limit')
        require(len({e.filename for e in entries}) == 12, 'duplicate NPZ entries')
    with np.load(path, allow_pickle=False) as source:
        require(set(source.files) == {f'mesh{i}_{key}' for i in range(4)
                                    for key in ('vertices', 'triangles', 'corner_uv')}, 'NPZ keys')
        return {key: source[key] for key in source.files}


def validate_candidate(model, source, original_report):
    require(original_report['allowlist'] == list(SOURCES), 'unexpected report source allowlist')
    nodes = {n['name']: n for n in model['nodes']}
    require(set(nodes) == {ROOT_NAME, TERRAIN, *MESHES}, 'node allowlist differs: unintended/missing geometry')
    require(model['root']['name'] == ROOT_NAME, 'wrong root')
    for name, children, parent in ((ROOT_NAME, SOURCES, None),
                                   (TERRAIN, MESHES[3:], ROOT_NAME)):
        node = nodes[name]
        require(node['kind'] == 1 and node['parent'] == parent and node['active'] == 1, 'dummy hierarchy/flags')
        require([c['name'] for c in node['children']] == list(children), 'dummy child allowlist')
        require(np.array_equal(node['matrix'], np.eye(4, dtype=np.float32).ravel()), 'nonidentity dummy')
    require(len(model['textures']) == len(model['materials']) == 3, 'texture/material count')
    for i, (texture, material) in enumerate(zip(model['textures'], model['materials'])):
        filename = f'kn5_{KINDS[i]}.dds'
        require(texture['name'] == filename and texture['active'] == 1, 'texture identity/active')
        validate_dds(texture['data'], COLORS[i])
        require(material['name'] == ('KN5_Asphalt', 'KN5_Gravel', 'KN5_Terrain')[i]
                and material['shader'] == 'ksPerPixel', 'material identity/shader')
        require((material['blend'], material['alpha'], material['depth']) == (0, 0, 0), 'material flags')
        require(material['bindings'] == [('txDiffuse', 0, filename)], 'diffuse texture binding')
        properties = dict(ksAmbient=0.4, ksDiffuse=0.6, ksSpecular=0.05, ksSpecularEXP=10)
        require(set(material['properties']) == set(properties), 'shader properties')
        for key, value in properties.items():
            expected = np.zeros(10, dtype=np.float32)
            expected[0] = value
            require(np.array_equal(material['properties'][key], expected), 'shader property values')
    mesh_evidence = []
    for i, name in enumerate(MESHES):
        node = nodes[name]
        require(node['kind'] == 2 and not node['children'], 'mesh type/children')
        require(node['parent'] == (ROOT_NAME if i < 3 else TERRAIN), 'mesh parent')
        require([node[k] for k in ('active', 'cast_shadows', 'visible', 'transparent', 'renderable', 'layer')]
                == [1, 1, 1, 0, 1, 0], 'mesh flags/layer')
        require(node['material'] == (0, 1, 1, 2, 2)[i], 'mesh material')
        require(np.array_equal(node['lod_sphere'][:2], [0, 0]), 'candidate LOD changed')
        vertices = node['vertices'].astype(np.float64)
        positions, normals, tangents = vertices[:, :3], vertices[:, 3:6], vertices[:, 8:11]
        nl, tl = np.linalg.norm(normals, axis=1), np.linalg.norm(tangents, axis=1)
        dot = np.abs(np.sum(normals * tangents, axis=1))
        require(np.max(np.abs(nl - 1)) < 1e-5 and np.max(np.abs(tl - 1)) < 1e-5
                and dot.max() < 1e-5, 'normal/tangent frame quality')
        triangles = positions[node['indices']]
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        require((cross[:, 1] > 0).all(), 'degenerate/non-upward winding')
        require((np.sum(cross * normals[node['indices']].mean(axis=1), axis=1) > 0).all(), 'normal opposes winding')
        center, radius = node['lod_sphere'][2:5], float(node['lod_sphere'][5])
        distance = np.linalg.norm(positions - center, axis=1)
        require(distance.max() <= radius + 0.001, 'bounding sphere fails to enclose mesh')
        bounds = [positions.min(axis=0).tolist(), positions.max(axis=0).tolist()]
        previous = original_report['model']['meshes'][i]
        require(previous['name'] == name and np.array_equal(bounds, previous['bounds_kn5']), 'reported object bounds differ')
        require(len(positions) == previous['vertices'] and len(triangles) == previous['triangles'], 'reported mesh counts differ')
        mesh_evidence.append(dict(name=name, vertices=len(positions), triangles=len(triangles),
                                  max_index=int(node['indices'].max()), bounds=bounds,
                                  normal_length=[float(nl.min()), float(nl.max())],
                                  tangent_length=[float(tl.min()), float(tl.max())],
                                  max_abs_normal_dot_tangent=float(dot.max()),
                                  lod_in=0, lod_out=0, sphere_radius=radius,
                                  max_vertex_distance=float(distance.max())))
    comparisons = []
    for i, name in enumerate(SOURCES):
        v = source[f'mesh{i}_vertices']
        t = source[f'mesh{i}_triangles']
        uv = source[f'mesh{i}_corner_uv']
        require(v.dtype == np.float32 and v.ndim == 2 and v.shape[1] == 3 and np.isfinite(v).all(), 'source vertices')
        require(t.dtype == np.int32 and t.ndim == 2 and t.shape[1] == 3 and t.min() >= 0 and t.max() < len(v), 'source indices')
        require(uv.dtype == np.float32 and uv.shape == (*t.shape, 2) and np.isfinite(uv).all(), 'source UV')
        xyz = v[:, [0, 2, 1]].copy()
        xyz[:, 2] *= -1
        uv = uv.copy()
        uv[:, :, 1] = 1 - uv[:, :, 1]
        expected = np.concatenate((xyz[t], uv), axis=2)
        chunks = [nodes[n] for n in (MESHES[3:] if i == 3 else (name,))]
        actual = np.concatenate([n['vertices'][n['indices']][:, :, [0, 1, 2, 6, 7]] for n in chunks])
        compare_corners(expected, actual)
        bounds = [xyz.min(axis=0), xyz.max(axis=0)]
        require(np.array_equal(bounds, [actual[:, :, :3].min(axis=(0, 1)), actual[:, :, :3].max(axis=(0, 1))]), 'source union bounds')
        comparisons.append(dict(source=name, triangles=len(t), oriented_xyz_corner_uv='EXACT_FLOAT32_MULTISET_PASS'))
    return mesh_evidence, comparisons


def validate(kn5=KN5, source=SOURCE, report=REPORT):
    binary, npz_bytes, report_bytes = (bounded_read(p) for p in (kn5, source, report))
    original = json.loads(report_bytes)
    digest = lambda b: hashlib.sha256(b).hexdigest()
    require(digest(binary) == original['kn5']['sha256'], 'KN5 differs from original report')
    require(digest(npz_bytes) == original['expected_geometry_sha256'], 'NPZ differs from original report')
    model = parse(binary)
    meshes, comparisons = validate_candidate(model, load_source(source), original)
    return dict(status='PASS_INDEPENDENT_STATIC_STRUCTURE_AND_SOURCE_GEOMETRY',
                inputs={str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p):
                        {'bytes': len(b), 'sha256': digest(b)}
                        for p, b in zip(map(Path, (kn5, source, report)), (binary, npz_bytes, report_bytes))},
                reference=REFERENCE, bytes_consumed=model['bytes_consumed'], nodes=len(model['nodes']),
                textures=3, materials=3, meshes=meshes, source_comparison=comparisons,
                triangle_total=sum(m['triangles'] for m in meshes),
                warnings=['LOD_OUT=0 on all meshes: unresolved potentially visibility-sensitive default; '
                          'independent reader names the field but does not establish AC zero semantics. '
                          'No bug asserted without game validation.'],
                limits=['No Windows/ksEditor/Assetto Corsa/Blender/visual/physics/timing/VR execution.',
                        'Source NPZ is exporter-task capture, not independently reacquired Blender/geographic truth.',
                        'Independent parser and external reader layout review, not a second engine implementation.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Create NEW evidence JSON exclusively; default: stdout only')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('refusing to overwrite existing evidence')
    result = validate()
    text = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
