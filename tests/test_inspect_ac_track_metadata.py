"""Synthetic fixtures only: no game installation or proprietary data required."""
import io
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_ac_track_metadata import Budget, IDENTITY, InvalidMetadata, inspect_kn5


def u(x):
    return struct.pack('<I', x)


def s(x):
    b = x.encode()
    return u(len(b)) + b


def floats(xs):
    return struct.pack('<' + 'f' * len(xs), *xs)


def dummy(name, children=b'', count=0, matrix=None):
    return u(1) + s(name) + u(count) + b'\1' + floats(matrix or IDENTITY) + children


def fixture(version=5, kind=2, material=0):
    header = b'sc6969' + u(version) + (u(0) if version == 6 else b'')
    texture = u(1) + u(1) + s('synthetic') + u(1000) + b'X' * 1000
    mat = u(1) + s('mat') + s('shader') + b'\0\0' + u(0) + u(0) + u(0)
    mesh = u(kind) + s('1ROAD') + u(0) + b'\1\1\1\0'
    if kind == 3:
        mesh += u(1) + s('bone') + floats(IDENTITY)
    mesh += u(3) + b'V' * (3 * (44 if kind == 2 else 76))
    mesh += u(3) + b'I' * 6 + u(material) + u(0) + floats([0, 0])
    if kind == 2:
        mesh += floats([0, 0, 0, 1]) + b'\1'
    return header + texture + mat + dummy('root', mesh, 1)


class MetadataTests(unittest.TestCase):
    def test_versions_and_seek(self):
        for version in (5, 6):
            data = fixture(version)
            result = inspect_kn5(io.BytesIO(data))
            self.assertEqual(result['version'], version)
            self.assertEqual(result['nodes'], 2)
            self.assertEqual(result['bytes_skipped'], 1000 + 132 + 6)
            self.assertEqual(result['actual_bytes_read'] + result['bytes_skipped'], len(data))
            self.assertEqual(result['lod_distribution'], [dict(lod_in=0, lod_out=0, meshes=1)])

    def test_skinned_kind(self):
        result = inspect_kn5(io.BytesIO(fixture(kind=3)))
        self.assertEqual(result['node_kinds'], {'1': 1, '3': 1})

    def test_parent_world_transform(self):
        parent = IDENTITY.copy()
        parent[12:15] = [10, 20, 30]
        child = IDENTITY.copy()
        child[12:15] = [1, 2, 3]
        data = b'sc6969' + u(5) + u(0) + u(0)
        data += dummy('root', dummy('AC_PIT_0', matrix=child), 1, parent)
        self.assertEqual(inspect_kn5(io.BytesIO(data))['pivots'][0]['position'], [11, 22, 33])

    def test_reject_malformed(self):
        for data in (fixture()[:-1], fixture() + b'X', fixture(material=1),
                     b'sc6969' + u(7), b'sc6969' + u(5) + u(1_000_001),
                     b'sc6969' + u(5) + u(0) + u(0) + u(99) + s('x') + u(0) + b'\1'):
            with self.assertRaises(InvalidMetadata):
                inspect_kn5(io.BytesIO(data))

    def test_budget(self):
        with self.assertRaises(InvalidMetadata):
            inspect_kn5(io.BytesIO(fixture()), Budget(30))

    def test_seek_past_eof_rejected(self):
        data = b'sc6969' + u(5) + u(1) + u(1) + s('x') + u(1000)
        with self.assertRaises(InvalidMetadata):
            inspect_kn5(io.BytesIO(data))


if __name__ == '__main__':
    unittest.main()
