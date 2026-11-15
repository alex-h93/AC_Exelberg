"""Offline station/basis/allowlist safety tests; no bpy, vendor or game execution."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build_ac_test_scene.py'
spec = importlib.util.spec_from_file_location('ac_scene_builder', SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class StationTests(unittest.TestCase):
    def setUp(self):
        self.points = np.array([[0., 0., 1.], [0., 10., 2.], [0., 40., 5.]])

    def test_station_grade_and_distances(self):
        s = builder.station(self.points, 25.)
        np.testing.assert_allclose(s['point'], [0., 25., 3.5])
        np.testing.assert_allclose(s['forward_xy'], [0., 1.])
        self.assertAlmostEqual(s['grade_percent'], 10.)
        self.assertEqual(s['distance_to_end_m'], 15.)
        self.assertEqual(s['index'], 1)
        self.assertEqual(s['fraction'], 0.5)

    def test_endpoints(self):
        for distance, point in [(0., self.points[0]), (40., self.points[-1])]:
            np.testing.assert_array_equal(builder.station(self.points, distance)['point'], point)

    def test_bad_distance(self):
        for distance in (-1., 41., np.nan, np.inf):
            with self.assertRaises(ValueError):
                builder.station(self.points, distance)

    def test_bad_route(self):
        for points in ([], [[0., 0., 0.]], [[0., 0., 0.], [0., 0., 1.]],
                       [[0., 0., 0.], [np.nan, 1., 1.]]):
            with self.assertRaises(ValueError):
                builder.station(points, 0.)

    def test_helpers_on_actual_stations(self):
        helpers = builder.helper_data(self.points, np.array([1000., 1010., 1040.]))
        self.assertEqual([h['name'] for h in helpers], list(builder.SPAWNS + builder.TIMING))
        for h in helpers:
            self.assertAlmostEqual(h['chainage_3035_m'], 1025.)
            self.assertAlmostEqual(h['provisional_vertical_clearance_m'], 0.4)
            self.assertAlmostEqual(h['blender_matrix_rows'][2][3], 3.9)
        left, right = [np.array(h['blender_matrix_rows'])[:3, 3] for h in helpers[3:]]
        np.testing.assert_allclose(left - right, [-6., 0., 0.])


class OrientationTests(unittest.TestCase):
    def test_spawn_basis_independent_change_of_basis(self):
        c = np.array([[1., 0., 0.], [0., 0., 1.], [0., -1., 0.]])
        for angle in (0., 0.3, 1.8, -2.7, np.pi):
            forward = np.array([np.sin(angle), np.cos(angle)])
            b, k = builder.spawn_frames([11., 22., 33.], forward)
            b, k = np.array(b), np.array(k).reshape(4, 4)
            np.testing.assert_allclose(b[:3, 1], [*forward, 0.], atol=1e-12)
            np.testing.assert_allclose(k[:3, :3], (c @ b[:3, :3] @ c.T).T, atol=1e-12)
            np.testing.assert_allclose(-k[2, :3], c @ b[:3, 1], atol=1e-12)
            np.testing.assert_allclose(k[1, :3], [0., 1., 0.])
            np.testing.assert_allclose(k[3, :3], [11., 33., -22.])
            self.assertAlmostEqual(np.linalg.det(b[:3, :3]), 1.)
            self.assertAlmostEqual(np.linalg.det(k[:3, :3]), 1.)

    def test_undefined_heading(self):
        for heading in ([0., 0.], [np.nan, 1.], [1., 2., 3.]):
            with self.assertRaises(ValueError):
                builder.spawn_frames([0., 0., 0.], heading)

    def test_timing_uses_observed_trento_axes(self):
        b, k = builder.timing_frames([2., 3., 4.])
        k = np.array(k).reshape(4, 4)
        np.testing.assert_array_equal(k[:3, :3], [[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])
        np.testing.assert_array_equal(k[3], [2., 4., -3., 1.])
        c = np.array([[1., 0., 0.], [0., 0., 1.], [0., -1., 0.]])
        np.testing.assert_array_equal(k[:3, :3], (c @ np.array(b)[:3, :3] @ c.T).T)


class AllowlistTests(unittest.TestCase):
    def test_exact_surface_keys(self):
        for key, config in builder.SURFACES.items():
            for name in config['objects']:
                self.assertEqual(builder.surface_key(name), key)
                self.assertTrue(name.startswith('1'))
        self.assertEqual(set(builder.NAMES.values()), {'1ROAD', '1GRAVEL_L', '1GRAVEL_R', '1GRASS_TERRAIN'})

    def test_no_unintended_collision_meshes(self):
        for name in ('DEBUG_ALIGNMENT', 'REFERENCE_ORIGINAL', '1GRASS_TERRAIN',
                     '1GRASS_TERRAIN_SUB2', '1ROAD_DEBUG', 'PROVISIONAL_SHOULDER_L', 'AC_PIT_0', '1WALL'):
            with self.assertRaises(ValueError):
                builder.surface_key(name)

    def test_versioned_paths_separate(self):
        self.assertNotEqual(builder.SOURCE, builder.COPY)
        self.assertNotEqual(builder.KN5, builder.OLD_KN5)
        self.assertEqual(builder.KN5.stem, builder.TRACK_ID)
        self.assertEqual(builder.TRACK_ID, 'exelberg_north_proto_v001')


if __name__ == '__main__':
    unittest.main()
