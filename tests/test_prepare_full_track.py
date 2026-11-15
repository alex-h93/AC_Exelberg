"""Offline full-route helper and generated-handoff contract tests."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_full_track as p
from prepare_prototype import sha


class GeometryTests(unittest.TestCase):
    def test_exact_segment_distance_including_other_hairpin_arm(self):
        route = np.array([[0., 0.], [100., 0.], [100., 20.], [0., 20.]])
        points = np.array([[50., 1.], [50., 18.], [-3., 4.], [105., 10.]])
        np.testing.assert_allclose(p.nearest_segment_distance(points, route), [1., 2., 5., 5.])
        # Distance to vertices would incorrectly report ~50m for the first point.
        self.assertGreater(np.linalg.norm(route-points[0], axis=1).min(), 49.)

    def test_normals_and_lateral_sign(self):
        xy = np.array([[0., 0.], [2., 0.], [4., 0.]])
        np.testing.assert_array_equal(p.normals(xy), [[0., 1.]]*3)
        with self.assertRaises(ValueError):
            p.normals(np.zeros((3, 2)))

    def test_grid_budget_and_tile_cell_partition(self):
        with self.assertRaises(ValueError):
            p.grid_axes(np.array([[0., 0.], [20000., 20000.]]))
        shape = (260, 280)
        count = np.zeros((shape[0]-1, shape[1]-1), int)
        for r0, r1, c0, c1 in p.tiles(shape):
            self.assertLessEqual(r1-r0, 129)
            self.assertLessEqual(c1-c0, 129)
            count[r0:r1-1, c0:c1-1] += 1
        np.testing.assert_array_equal(count, 1)

    def test_strict_sampling_no_fill(self):
        grid = np.array([[1., 2., 3.], [4., -9999., 6.], [7., 8., 9.]])
        h, valid = p.strict_bilinear(grid, np.array([[.5, 2.5], [1., 2.], [10., 10.]]), (0., 3., 1., 1.))
        # Zero-weight nodata neighbors still invalidate the first sample.
        self.assertFalse(valid.any())
        np.testing.assert_array_equal(h, 0.)

    def test_tree_candidates_deterministic_and_segment_safe(self):
        route = np.array([[0., 0.], [200., 0.], [200., 25.], [0., 25.]])
        first, second = p.roadside_candidates(route), p.roadside_candidates(route)
        for a, b in zip(first, second):
            np.testing.assert_array_equal(a, b)
        self.assertTrue(np.all(first[2] > 10.))
        np.testing.assert_allclose(first[2], p.nearest_segment_distance(first[0], route))


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = json.loads((p.OUT/'manifest.json').read_text())
        cls.archives = {key: np.load(p.ROOT/value['path'], allow_pickle=False)
            for key, value in cls.m['outputs'].items()}

    @classmethod
    def tearDownClass(cls):
        for archive in cls.archives.values():
            archive.close()

    def test_hashes_schemas_finite_arrays(self):
        self.assertEqual(self.m['schema'], 'assetto-exelberg.full-track-inputs')
        self.assertEqual(self.m['version'], 1)
        for item in self.m['provenance']['inputs'] + list(self.m['outputs'].values()):
            self.assertEqual(sha(p.ROOT/item['path']), item['sha256'])
        for key, archive in self.archives.items():
            schema = self.m['outputs'][key]['arrays']
            self.assertEqual(set(archive.files), set(schema))
            for name in archive.files:
                a = archive[name]
                self.assertTrue(np.isfinite(a).all(), name)
                self.assertFalse(a.dtype.hasobject)
                self.assertEqual(list(a.shape), schema[name]['shape'])
                self.assertEqual(str(a.dtype), schema[name]['dtype'])

    def test_full_route_corners_stations_endpoints_origin(self):
        r = self.archives['route']
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            t1, _ = p.operation(4326, 3035)
            t2, _ = p.operation(3035, 25833)
            wgs = np.asarray(json.loads((p.ROOT/'data/processed/route.geojson').read_text())['features'][0]['geometry']['coordinates'])[:, :2]
            source = p.project(t1, wgs)
            expected = p.project(t2, source)
        np.testing.assert_array_equal(r['full_xy_25833_m'], expected)
        np.testing.assert_array_equal(r['xy_25833_m'][[0, -1]], expected[[0, -1]])
        for corner, station in zip(expected, r['full_chainage_25833_m']):
            index = np.searchsorted(r['chainage_25833_m'], station)
            np.testing.assert_array_equal(r['xy_25833_m'][index], corner)
        for key, fullkey in [('chainage_3035_m', 'full_chainage_3035_m'), ('chainage_25833_m', 'full_chainage_25833_m')]:
            self.assertEqual(r[key][0], 0.)
            self.assertEqual(r[key][-1], r[fullkey][-1])
            self.assertTrue(np.all(np.diff(r[key]) > 0))
        self.assertGreater(r['chainage_25833_m'][-1], 15200.)
        self.assertLessEqual(np.linalg.norm(np.diff(r['xy_25833_m'], axis=0), axis=1).max(), 2.)
        self.assertTrue(r['valid'].all())
        np.testing.assert_array_equal(self.m['coordinates']['origin_m'], p.ORIGIN)
        np.testing.assert_allclose(r['local_xyz_m']+p.ORIGIN, np.column_stack([r['xy_25833_m'], r['raw_height_9274_m']]), atol=1e-8)
        self.assertLess(max(self.m['controls']['inverse_errors_m']), .001)
        self.assertEqual(self.m['diagnostics']['suspected_profile_chainage_3035_m'], [9580., 9600.])

    def test_raw_route_lateral_terrain_tree_sampling(self):
        with tifffile.TiffFile(p.ROOT/'data/processed/terrain_corridor_3035.tif') as tif:
            page = tif.pages[0]
            grid = page.asarray()
            sx, sy, _ = page.tags[33550].value
            i, j, _, x, y, _ = page.tags[33922].value
        transform = (x-i*sx, y+j*sy, sx, sy)
        trans, _ = p.operation(3035, 25833)
        for key in ('route', 'lateral', 'trees', 'terrain'):
            archive = self.archives[key]
            if key == 'terrain':
                xy = np.column_stack([archive['x_m'].ravel(), archive['y_m'].ravel()])+p.ORIGIN[:2]
            else:
                xy = archive['xy_25833_m'].reshape(-1, 2)
            # Every route/lateral/tree sample and a spread across the terrain.
            step = 37 if key == 'terrain' else 1
            h, mask = p.strict_bilinear(grid, p.project(trans, xy[::step], inverse=True), transform)
            np.testing.assert_array_equal(archive['valid'].ravel()[::step], mask)
            np.testing.assert_allclose(archive['raw_height_9274_m'].ravel()[::step], h, atol=1e-10)

    def test_terrain_topology_lateral_reference_tree_contract(self):
        t, l, r, trees = [self.archives[k] for k in ('terrain', 'lateral', 'route', 'trees')]
        self.assertLessEqual(t['valid'].size, 1600000)
        np.testing.assert_array_equal(t['valid_cells'], p.valid_cells(t['valid']))
        np.testing.assert_array_equal(t['z_m'][~t['valid']], 0.)
        np.testing.assert_allclose(np.diff(t['x_m'], axis=1), 8.)
        np.testing.assert_allclose(np.diff(t['y_m'], axis=0), 8.)
        expected = r['xy_25833_m'][:, None, :] + p.normals(r['xy_25833_m'])[:, None, :]*l['offsets_m'][None, :, None]
        np.testing.assert_array_equal(l['xy_25833_m'], expected)
        np.testing.assert_array_equal(l['raw_height_9274_m'][~l['valid']], 0.)
        self.assertFalse(self.m['trees']['forest_mask_implemented'])
        self.assertGreater(len(trees['valid']), 3000)
        self.assertLessEqual(len(trees['valid']), 7000)
        distance = p.nearest_segment_distance(trees['xy_25833_m'], r['full_xy_25833_m'])
        self.assertTrue(np.all(distance > 10.))
        np.testing.assert_array_equal(distance, trees['nearest_route_segment_distance_m'])
        xy = trees['xy_25833_m']
        lo = np.array(self.m['terrain']['bounds_25833_m'][0])
        ci = np.floor((xy-lo)/8.).astype(int)
        self.assertTrue(t['valid_cells'][ci[:, 1], ci[:, 0]].all())


if __name__ == '__main__':
    unittest.main()
