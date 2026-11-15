"""Offline numerical checks; these tests do not pretend to execute Blender."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prototype_geometry as g


class PrototypeGeometryTests(unittest.TestCase):
    def test_straight_upward_flat_ribbon(self):
        p = np.array([[0, 0, 0], [1, 0, 1], [2, 0, 2]], float)
        v, f = g.ribbon(p, [-3, 0, 3])
        checks = g.mesh_checks(v, f)
        self.assertEqual(checks["triangles"], 8)
        self.assertEqual(checks["non_upward_triangles"], 0)
        self.assertEqual(checks["degenerate_triangles"], 0)
        self.assertTrue(np.all(v.reshape(3, 3, 3)[:, :, 2] == p[:, None, 2]))
        self.assertAlmostEqual(np.ptp(v[:3, 1]), 6)

    def test_reversed_winding_detected(self):
        v, f = g.ribbon(np.array([[0, 0, 0], [1, 0, 0]], float), [-3, 3])
        self.assertEqual(g.mesh_checks(v, f[:, ::-1])["non_upward_triangles"], 2)

    def test_degenerate_detected(self):
        result = g.mesh_checks(np.zeros((3, 3)), np.array([[0, 1, 2]]))
        self.assertEqual(result["degenerate_triangles"], 1)

    def test_masks_no_partial_cells(self):
        valid = np.ones((3, 3), dtype=bool)
        valid[0, 0] = False
        cells = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:] & valid[1:, 1:]
        f = g.valid_terrain_faces(valid, cells)
        self.assertEqual(len(f), 6)
        self.assertNotIn(0, f)
        with self.assertRaises(ValueError):
            g.valid_terrain_faces(valid, np.ones((2, 2), bool))
        x, y = np.meshgrid(np.arange(3), np.arange(3))
        self.assertEqual(g.mesh_checks(np.column_stack([x.ravel(), y.ravel(), x.ravel()*0]), f)["non_upward_triangles"], 0)

    def test_smooth_straight_identity_and_endpoints(self):
        raw = np.array([[0, 0, 0], [10, 0, 1], [20, 0, 2]], float)
        _, _, original, designed = g.smooth_samples(raw)
        np.testing.assert_allclose(original, designed, atol=1e-14)
        np.testing.assert_array_equal(designed[[0, -1]], raw[[0, -1]])

    def test_corner_offsets_auditable(self):
        raw = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 1]], float)
        _, s, original, designed = g.smooth_samples(raw)
        self.assertEqual(len(s), 21)
        self.assertGreater(np.linalg.norm(designed[10] - original[10]), 0.1)
        self.assertLess(g.profile_stats(designed)["max_heading_step_deg"], 90)

    def test_repeated_route_rejected(self):
        with self.assertRaises(ValueError):
            g.smooth_samples(np.zeros((3, 3)))

    def test_overlap_straight_none(self):
        p = np.column_stack([np.arange(10.), np.zeros((10, 2))])
        self.assertEqual(g.ribbon_overlap(p, 0.1), [])

    def test_crossing_overlap_detected(self):
        p = np.array([[-10, -10, 0], [10, 10, 0], [-10, 10, 0], [10, -10, 0]], float)
        self.assertIn([0, 2], g.ribbon_overlap(p, 0.1))

    def test_terrain_lowering_guarantees_clearance_preserves_input(self):
        x, y = np.meshgrid(np.arange(-6., 7.), np.arange(-6., 7.))
        z = x * 0 + 5
        cells = np.ones((12, 12), bool)
        p = np.array([[-3, 0, 1], [0, 0, 2], [3, 1, 3]], float)
        out, touched = g.lower_terrain(x, y, z, cells, p)
        self.assertTrue(touched.any())
        self.assertTrue(np.all(out <= z))
        self.assertTrue(np.all(z == 5))
        self.assertGreaterEqual(g.terrain_clearance(x, y, out, cells, p), 0.25 - 1e-12)
        self.assertEqual(out[0, 0], 5)

    def test_fold_is_detected(self):
        p = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
        v, f = g.ribbon(p, [-5, 5])
        self.assertGreater(g.mesh_checks(v, f)["non_upward_triangles"], 0)


if __name__ == "__main__":
    unittest.main()
