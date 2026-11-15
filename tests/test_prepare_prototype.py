"""Offline unit and real prepared-contract checks; never invoke Blender."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_prototype as p
from extract_terrain import bilinear


class SamplingTests(unittest.TestCase):
    def test_clip_exact_endpoints_preserves_corners(self):
        xy = np.array([[0., 0.], [3., 0.], [3., 4.]])
        s, clipped = p.clip_route(xy, p.stations(xy), 1., 5.)
        np.testing.assert_array_equal(s, [1., 3., 5.])
        np.testing.assert_array_equal(clipped, [[1., 0.], [3., 0.], [3., 2.]])
        dense_s, dense = p.densify(clipped, s, .7)
        self.assertLessEqual(np.linalg.norm(np.diff(dense, axis=0), axis=1).max(), .7)
        np.testing.assert_array_equal(dense[[0, -1]], clipped[[0, -1]])
        self.assertTrue(np.all(np.diff(dense_s) > 0))
        self.assertTrue(np.any(np.all(dense == clipped[1], axis=1)))

    def test_invalid_intervals_and_routes(self):
        xy = np.array([[0., 0.], [2., 0.]])
        for start, end in [(-1, 1), (1, 3), (1, 1), (2, 1)]:
            with self.assertRaises(ValueError):
                p.clip_route(xy, p.stations(xy), start, end)
        with self.assertRaises(ValueError):
            p.stations(np.zeros((2, 2)))

    def test_strict_mask_and_finite_placeholders(self):
        grid = np.array([[10., 20., 30.], [30., 40., 50.], [50., 60., -9999.]])
        xy = np.array([[1., 2.], [1.5, 1.5], [0., 3.], [2., 1.], [np.nan, 1.]])
        h, valid = p.strict_bilinear(grid, xy, (0., 3., 1., 1.))
        np.testing.assert_array_equal(valid, [True, False, False, False, False])
        self.assertEqual(h[0], 25.)
        np.testing.assert_array_equal(h[~valid], 0.)
        self.assertTrue(np.isfinite(h).all())
        local = p.local_positions(np.zeros((len(h), 2)), h, valid, np.array([0., 0., 300.]))
        np.testing.assert_array_equal(local[~valid, 2], 0.)
        grid[0, 1] = np.nan
        self.assertFalse(p.strict_bilinear(grid, xy[:1], (0., 3., 1., 1.))[1][0])

    def test_only_fully_valid_cells(self):
        mask = np.ones((3, 4), dtype=bool)
        mask[0, 0] = False
        mask[2, 3] = False
        np.testing.assert_array_equal(p.valid_cells(mask), [[False, True, True], [True, True, False]])

    def test_axes_origin_and_inverse(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            t, info = p.operation(3035, 25833)
            source = np.array([[4780000., 2800000.], [4790000., 2810000.], [4785000., 2815000.]])
            work = p.project(t, source)
            np.testing.assert_allclose(p.project(t, work, inverse=True), source, atol=1e-5, rtol=0)
        self.assertFalse(info['allow_ballpark'])
        self.assertFalse(info['networking'])
        origin = np.array([589500., 5346800., 300.])
        heights = np.array([301., 302., 299.])
        local = p.local_positions(work, heights, np.ones(3, bool), origin)
        np.testing.assert_allclose(local + origin, np.column_stack([work, heights]))
        np.testing.assert_array_equal(p.local_positions(origin[None, :2], np.array([300.]), np.array([True]), origin), [[0., 0., 0.]])
        basis_xy = origin[:2] + np.array([[1., 0.], [0., 1.], [0., 0.]])
        basis = p.local_positions(basis_xy, np.array([300., 300., 301.]), np.ones(3, bool), origin)
        np.testing.assert_array_equal(basis, np.eye(3))
        self.assertGreater(np.linalg.det(basis), 0)


class PreparedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = json.loads((p.OUT/'manifest.json').read_text())
        cls.route = np.load(p.OUT/'route.npz', allow_pickle=False)
        cls.terrain = np.load(p.OUT/'terrain.npz', allow_pickle=False)

    @classmethod
    def tearDownClass(cls):
        cls.route.close()
        cls.terrain.close()

    def test_finite_and_checksums(self):
        self.assertEqual(self.m['version'], 1)
        for artifact in self.m['outputs'].values():
            path = p.ROOT/artifact['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact['sha256'])
        for archive in (self.route, self.terrain):
            for key in archive.files:
                self.assertFalse(archive[key].dtype.hasobject)
                self.assertTrue(np.isfinite(archive[key]).all(), key)
        for item in self.m['provenance']['inputs']:
            self.assertEqual(p.sha(p.ROOT/item['path']), item['sha256'])

    def test_real_endpoints_alignment_origin(self):
        wgs, _ = p.operation(4326, 3035)
        trans, _ = p.operation(3035, 25833)
        coords = np.asarray(json.loads((p.ROOT/'data/processed/route.geojson').read_text())['features'][0]['geometry']['coordinates'])[:, :2]
        xy = p.project(wgs, coords)
        station, clipped = p.clip_route(xy, p.stations(xy), 1000., 2500.)
        expected = p.project(trans, clipped)
        np.testing.assert_array_equal(self.route['section_vertex_chainage_3035_m'], station)
        np.testing.assert_allclose(self.route['section_vertex_xy_25833_m'], expected, atol=1e-8, rtol=0)
        np.testing.assert_allclose(self.route['xy_25833_m'][[0, -1]], expected[[0, -1]], atol=1e-8, rtol=0)
        self.assertTrue(np.all(self.route['chainage_3035_m'] <= 2500))
        self.assertTrue(np.all(self.route['valid']))
        self.assertLessEqual(np.linalg.norm(np.diff(self.route['xy_25833_m'], axis=0), axis=1).max(), 2.)
        full = self.route['full_xy_25833_m']
        s = p.stations(full)
        midpoint = p.interpolate(full, s, [s[-1]/2])[0]
        origin = np.asarray(self.m['coordinates']['origin_m'])
        np.testing.assert_array_equal(origin[:2], np.round(midpoint/100)*100)
        self.assertGreater(np.linalg.norm(origin[:2]-expected.mean(axis=0)), 1000.)
        np.testing.assert_allclose(self.route['local_xyz_m'] + origin,
            np.column_stack([self.route['xy_25833_m'], self.route['raw_height_9274_m']]), atol=1e-8)
        self.assertLess(max(self.m['controls']['inverse_errors_m']), .001)

    def test_real_terrain_and_raw_samples(self):
        terrain, route = self.terrain, self.route
        self.assertLess(terrain['valid'].size, 400000)
        np.testing.assert_array_equal(terrain['valid_cells'], p.valid_cells(terrain['valid']))
        np.testing.assert_array_equal(terrain['z_m'][~terrain['valid']], 0.)
        np.testing.assert_allclose(np.diff(terrain['x_m'], axis=1), 2.)
        np.testing.assert_allclose(np.diff(terrain['y_m'], axis=0), 2.)
        with tifffile.TiffFile(p.ROOT/'data/processed/terrain_corridor_3035.tif') as tif:
            page = tif.pages[0]
            grid = page.asarray()
            sx, sy, _ = page.tags[33550].value
            i, j, _, x, y, _ = page.tags[33922].value
        transform = (x-i*sx, y+j*sy, sx, sy)
        # Independent existing scalar sampler validates all route raw heights.
        reference = bilinear(grid, route['xy_3035_m'], transform)
        np.testing.assert_allclose(route['raw_height_9274_m'], reference, atol=1e-10)
        trans, _ = p.operation(3035, 25833)
        origin = np.array(self.m['coordinates']['origin_m'])
        local = np.column_stack([terrain['x_m'].ravel(), terrain['y_m'].ravel()])
        source = p.project(trans, local+origin[:2], inverse=True)
        h, mask = p.strict_bilinear(grid, source, transform)
        np.testing.assert_array_equal(mask.reshape(terrain['valid'].shape), terrain['valid'])
        np.testing.assert_allclose(terrain['z_m'].ravel()[mask]+300., h[mask], atol=1e-8)


if __name__ == '__main__':
    unittest.main()
