import json, struct, sys, unittest
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v004_treegen as T


class TreeGen(unittest.TestCase):
    def test_shapes_and_budget(self):
        for sp, h, r in (('beech', 25, 6), ('oak', 20, 6), ('conifer', 28, 3.5), ('shrub', 3, 1.5)):
            t = T.tree(sp, h, r, 7)
            self.assertLess(len(t['v']), 400)
            self.assertLess(len(t['tri']), 400)
            self.assertTrue(np.isfinite(t['v']).all() and np.isfinite(t['n']).all())
            self.assertTrue((t['uv'] >= 0).all())
            self.assertTrue((t['uv'][:, 0] <= 1).all())
            self.assertGreaterEqual(t['v'][:, 2].min(), -0.3)  # build sinks bases 0.2 m anyway
            self.assertLess(t['v'][:, 2].max(), h * 1.25)
            self.assertEqual(int(t['tri'].max()), len(t['v']) - 1)

    def test_deterministic(self):
        a, b = T.tree('beech', 20, 5, 3), T.tree('beech', 20, 5, 3)
        self.assertTrue(np.array_equal(a['v'], b['v']))


class Outputs(unittest.TestCase):
    def test_dds_have_mips(self):
        for name in ('foliage', 'bark', 'impostors', 'grass_detail'):
            p = ROOT / f'data/processed/textures_v004/v004_{name}.dds'
            if not p.exists():
                self.skipTest('textures not built')
            d = p.read_bytes()
            h, w, pitch, depth, mips = struct.unpack('<5I', d[12:32])
            self.assertEqual(d[:4], b'DDS ')
            self.assertEqual(mips, int(np.log2(max(h, w))) + 1)

    def test_package_manifest(self):
        p = ROOT / 'data/processed/full_track_package_v004/manifest.json'
        if not p.exists():
            self.skipTest('package not built')
        m = json.loads(p.read_text())
        self.assertEqual(m['status'], 'PASS_OFFLINE_NOT_RUNTIME_TESTED')
        self.assertEqual(m['physics_nodes_identical'], 424)
        self.assertLessEqual(m['kn5']['bytes'], 256 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
