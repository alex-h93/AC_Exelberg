"""Offline independent-parser tests; no Blender or exporter/reader imports."""
import ast
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import validate_kn5 as validator


def u32(value):
    return struct.pack('<I', value)


def text(value):
    data = value.encode()
    return u32(len(data)) + data


def dummy(name='root', children=0, active=1):
    return u32(1) + text(name) + u32(children) + bytes([active]) + struct.pack('<16f', *np.eye(4).ravel())


HEADER = b'sc6969' + u32(5) + u32(0) + u32(0)


class ParserTests(unittest.TestCase):
    def test_minimal_independently_constructed_v5(self):
        data = HEADER + dummy()
        result = validator.parse(data)
        self.assertEqual(result['bytes_consumed'], len(data))
        self.assertEqual(len(result['nodes']), 1)

    def test_every_truncation_of_small_fixture(self):
        data = HEADER + dummy()
        for end in range(len(data)):
            with self.subTest(end=end), self.assertRaises(validator.InvalidKN5):
                validator.parse(data[:end])

    def test_header_magic_version_trailing_and_negative_count(self):
        good = HEADER + dummy()
        variants = [b'x' + good[1:], good[:6] + u32(6) + good[10:], good + b'\0',
                    good[:10] + u32(0xFFFFFFFF) + good[14:]]
        for data in variants:
            with self.subTest(data=data[:18]), self.assertRaises(validator.InvalidKN5):
                validator.parse(data)

    def test_string_bounds_invalid_utf8_and_nul(self):
        for payload in (u32(4097), u32(0xFFFFFFFF), u32(0), u32(1) + b'\xff', text('a\0b')):
            with self.subTest(payload=payload), self.assertRaises(validator.InvalidKN5):
                validator.parse(HEADER + u32(1) + payload + b'\0' * 100)

    def test_invalid_flags_and_type(self):
        for data in (HEADER + dummy(active=2), HEADER + u32(3) + dummy()[4:]):
            with self.assertRaises(validator.InvalidKN5):
                validator.parse(data)

    def test_nonfinite_matrix(self):
        data = bytearray(HEADER + dummy())
        data[-4:] = struct.pack('<f', float('nan'))
        with self.assertRaisesRegex(validator.InvalidKN5, 'nonfinite'):
            validator.parse(data)

    def test_recursion_depth_budget(self):
        data = HEADER + b''.join(dummy(str(i), 1 if i < 18 else 0) for i in range(19))
        with self.assertRaisesRegex(validator.InvalidKN5, 'recursive node budget'):
            validator.parse(data)

    def test_total_node_budget(self):
        data = HEADER + dummy('root', 63)
        data += dummy('branch', 1) + dummy('leaf')
        data += b''.join(dummy(str(i)) for i in range(62))
        with self.assertRaisesRegex(validator.InvalidKN5, 'budget'):
            validator.parse(data)

    def test_duplicate_node_names(self):
        with self.assertRaisesRegex(validator.InvalidKN5, 'duplicate node'):
            validator.parse(HEADER + dummy('root', 1) + dummy('root'))

    def test_in_memory_size_cap(self):
        with mock.patch.object(validator, 'MAX_FILE', 8):
            with self.assertRaisesRegex(validator.InvalidKN5, 'file size'):
                validator.parse(HEADER)

    def test_sparse_oversized_disk_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'large.kn5'
            with path.open('wb') as stream:
                stream.truncate(validator.MAX_FILE + 1)
            with self.assertRaisesRegex(validator.InvalidKN5, 'file size'):
                validator.bounded_read(path)

    def test_no_vendor_or_blender_imports(self):
        tree = ast.parse(Path(validator.__file__).read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(n.name for n in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
        self.assertEqual(set(imports), {'argparse', 'hashlib', 'json', 'pathlib', 'struct', 'zipfile', 'numpy'})


class TriangleTests(unittest.TestCase):
    def setUp(self):
        self.corners = np.array([[[0, 0, 0, 0, 0], [1, 0, 0, 1, 0], [0, 1, 0, 0, 1]],
                                 [[1, 0, 0, 1, 0], [2, 0, 0, 2, 0], [0, 1, 0, 0, 1]]], dtype=np.float32)

    def test_cyclic_rotation_and_triangle_order_pass(self):
        validator.compare_corners(self.corners, np.roll(self.corners[::-1], 1, axis=1))

    def test_reverse_rejected(self):
        with self.assertRaisesRegex(validator.InvalidKN5, 'multiset'):
            validator.compare_corners(self.corners, self.corners[:, ::-1])

    def test_same_counts_bounds_but_changed_connectivity_rejected(self):
        changed = self.corners.copy()
        changed[0, 1], changed[1, 1] = self.corners[1, 1], self.corners[0, 1]
        with self.assertRaisesRegex(validator.InvalidKN5, 'multiset'):
            validator.compare_corners(self.corners, changed)

    def test_corner_uv_seam_change_rejected(self):
        changed = self.corners.copy()
        changed[0, 0, 3] = np.nextafter(np.float32(0), np.float32(1))
        with self.assertRaisesRegex(validator.InvalidKN5, 'multiset'):
            validator.compare_corners(self.corners, changed)

    def test_duplicate_multiplicity_rejected(self):
        with self.assertRaisesRegex(validator.InvalidKN5, 'multiset'):
            validator.compare_corners(self.corners, np.repeat(self.corners[:1], 2, axis=0))

    def test_signed_zero_equal(self):
        changed = self.corners.copy()
        changed[changed == 0] = -0.0
        validator.compare_corners(self.corners, changed)


class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = validator.bounded_read(validator.KN5)
        cls.model = validator.parse(cls.binary)
        cls.source = validator.load_source(validator.SOURCE)
        cls.report = json.loads(validator.REPORT.read_text())
        cls.road = next(n for n in cls.model['nodes'] if n['name'] == '1ROAD')

    def mutate_parse(self, offset, payload, message):
        changed = bytearray(self.binary)
        changed[offset:offset + len(payload)] = payload
        with self.assertRaisesRegex(validator.InvalidKN5, message):
            validator.parse(changed)

    def test_full_actual_artifact_and_source(self):
        result = validator.validate()
        self.assertEqual(result['triangle_total'], 230400)
        self.assertEqual(result['bytes_consumed'], 8190802)
        self.assertEqual(len(result['source_comparison']), 4)
        self.assertIn('LOD_OUT=0', result['warnings'][0])

    def test_real_truncations(self):
        for end in (6, 18, 100, 1000, self.road['vertex_offset'], self.road['index_offset'], len(self.binary) - 1):
            with self.subTest(end=end), self.assertRaises(validator.InvalidKN5):
                validator.parse(self.binary[:end])

    def test_oversized_vertex_count(self):
        self.mutate_parse(self.road['vertex_offset'] - 4, u32(65536), 'count limit')

    def test_oversized_index_count(self):
        self.mutate_parse(self.road['index_offset'] - 4, u32(0xFFFFFFFF), 'count limit')

    def test_invalid_index(self):
        self.mutate_parse(self.road['index_offset'], struct.pack('<H', 65535), 'index out of range')

    def test_texture_flag_and_payload_size(self):
        self.mutate_parse(14, u32(2), 'boolean flag')
        size_offset = 22 + len('kn5_asphalt.dds')
        self.mutate_parse(size_offset, u32(0xFFFFFFFF), 'count limit')

    def test_shader_properties_finite(self):
        start = self.binary.index(b'ksAmbient') + len('ksAmbient')
        for component in range(10):
            with self.subTest(component=component):
                self.mutate_parse(start + component * 4, struct.pack('<f', float('nan')), 'nonfinite')

    def test_all_vertex_components_finite(self):
        for component in range(11):
            with self.subTest(component=component):
                self.mutate_parse(self.road['vertex_offset'] + 4 * component, struct.pack('<f', float('inf')), 'nonfinite')

    def test_lod_sphere_fields_finite(self):
        for component in range(6):
            with self.subTest(component=component):
                self.mutate_parse(self.road['lod_sphere_offset'] + 4 * component, struct.pack('<f', float('nan')), 'nonfinite')

    def test_normal_tangent_winding_sphere_and_uv_mutations(self):
        for field in ('normal', 'tangent', 'winding', 'sphere', 'uv', 'extra_geometry', 'binding', 'visible'):
            with self.subTest(field=field):
                model = copy.deepcopy(self.model)
                road = next(n for n in model['nodes'] if n['name'] == '1ROAD')
                if field == 'normal':
                    road['vertices'][0, 3:6] = 0
                elif field == 'tangent':
                    road['vertices'][0, 8:11] = road['vertices'][0, 3:6]
                elif field == 'winding':
                    road['indices'][0] = road['indices'][0, ::-1]
                elif field == 'sphere':
                    road['lod_sphere'][5] = 1
                elif field == 'uv':
                    road['vertices'][0, 6] += 0.01
                elif field == 'extra_geometry':
                    road['name'] = 'DEBUG_UNINTENDED'
                elif field == 'binding':
                    model['materials'][0]['bindings'][0] = ('txDiffuse', 0, 'kn5_terrain.dds')
                elif field == 'visible':
                    road['visible'] = 0
                with self.assertRaises(validator.InvalidKN5):
                    validator.validate_candidate(model, self.source, self.report)

    def test_dds_header_and_meaningful_color_corruptions(self):
        texture = self.model['textures'][0]['data']
        validator.validate_dds(texture, validator.COLORS[0])
        for offset in (0, 4, 8, 12, 16, 20, 28, 76, 80, 88, 92, 108, 128, 191):
            changed = bytearray(texture)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(validator.InvalidKN5):
                validator.validate_dds(changed, validator.COLORS[0])

    def test_evidence_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'evidence.json'
            path.write_text('original')
            with mock.patch.object(sys, 'argv', ['validate_kn5', '--output', str(path)]):
                with self.assertRaises(SystemExit), mock.patch.object(validator, 'validate') as run:
                    validator.main()
                run.assert_not_called()
            self.assertEqual(path.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
