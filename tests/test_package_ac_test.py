import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import imagecodecs
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import package_ac_test as packager
from install_ac_test import ALLOWLIST, TRACK_ID, validate_source


class PackageTests(unittest.TestCase):
    def test_north_up_transform_and_inverse(self):
        points = np.array([[-3470., -3310.], [-3110., -2840.]])
        transform = packager.map_transform(points)
        uv = packager.pixels(points, transform)
        self.assertLess(uv[0, 1], uv[1, 1])  # More negative KN5 Z is north/top.
        self.assertLess(uv[0, 0], uv[1, 0])
        restored = uv * transform['scale_factor'] - [transform['x_offset'], transform['z_offset']]
        np.testing.assert_allclose(restored, points)
        self.assertTrue((uv > 0).all() and (uv < 1023).all())

    def test_image_encoder_and_route_pixels(self):
        xz = np.array([[0., -10.], [0., 10.]])
        transform = packager.map_transform(xz, size=64)
        image = packager.draw_route(xz, transform)
        decoded = imagecodecs.png_decode(imagecodecs.png_encode(image))
        np.testing.assert_array_equal(image, decoded)
        for x, y in np.rint(packager.pixels(xz, transform)).astype(int):
            self.assertEqual(decoded[y, x, 3], 255)

    def test_build_self_contained_hashes_zip_and_refuse_rerun(self):
        # All generated test files remain in a temporary tree, never game paths.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build = root / 'build'
            evidence = root / 'evidence'
            with contextlib.redirect_stdout(io.StringIO()):
                meta = packager.build(build, evidence)
            package = build / TRACK_ID
            payload = validate_source(package, evidence / 'manifest.json')
            self.assertEqual(set(payload), ALLOWLIST)
            self.assertEqual(meta['file_count'], len(ALLOWLIST))
            with zipfile.ZipFile(build / (TRACK_ID + '.zip')) as archive:
                self.assertEqual(set(archive.namelist()), {TRACK_ID + '/' + n for n in ALLOWLIST})
                for name, data in payload.items():
                    self.assertEqual(archive.read(TRACK_ID + '/' + name), data)
            for name in ('fast_lane.ai', 'pit_lane.ai'):
                self.assertEqual(payload['ai/' + name], b'\x03\0\0\0' + b'\0'*8)
            ui = json.loads(payload['ui/ui_track.json'])
            self.assertEqual(ui['country'], 'Austria')
            self.assertEqual(ui['pitboxes'], '1')
            self.assertEqual(ui['tags'], ['A2B', 'Hillclimb', 'prototype'])
            self.assertIn('1496', ui['length'])
            for key in ('ROAD', 'GRAVEL', 'GRASS'):
                self.assertIn('KEY=' + key, payload['data/surfaces.ini'].decode())
            before = (evidence / 'manifest.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'already exists'):
                packager.build(build, evidence)
            self.assertEqual(before, (evidence / 'manifest.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
