"""Offline safety checks; these do not claim Blender or independent KN5 validation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export_kn5_prototype.py"
spec = importlib.util.spec_from_file_location("kn5_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def records():
    result = []
    for name, (_, triangles, material) in smoke.ALLOWLIST.items():
        chunks = 2 if name.startswith("VISUAL_TERRAIN") else 1
        for index in range(chunks):
            count = triangles // chunks
            result.append({"name": name + f"_SUB{index}" if chunks > 1 else name,
                           "source_object": name, "vertices": 65535 if chunks > 1 else 100,
                           "min_index": 0, "max_index": 99, "indices": count * 3,
                           "triangles": count, "material_name": material})
    return result


class TestKN5SmokeSafety(unittest.TestCase):
    def test_valid_split(self):
        self.assertEqual(len(smoke.validate_mesh_records(records())), 4)

    def test_reject_uint16_overflow(self):
        for field, value in (("vertices", 65536), ("max_index", 65535), ("min_index", -1)):
            data = records()
            data[-1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                smoke.validate_mesh_records(data)

    def test_reject_excluded_mesh(self):
        data = records()
        data[0]["source_object"] = "REFERENCE_ORIGINAL_DTM_UNMODIFIED"
        with self.assertRaises(ValueError):
            smoke.validate_mesh_records(data)

    def test_reject_material_mismatch(self):
        data = records()
        data[0]["material_name"] = "WhiteFallback"
        with self.assertRaises(ValueError):
            smoke.validate_mesh_records(data)

    def test_reject_triangle_loss_or_nontriangular_indices(self):
        for field in ("triangles", "indices"):
            data = records()
            data[-1][field] -= 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                smoke.validate_mesh_records(data)

    def test_reject_missing_object(self):
        with self.assertRaises(ValueError):
            smoke.validate_mesh_records(records()[1:])

    def test_require_terrain_split(self):
        data = records()[:-1]
        data[-1]["triangles"] *= 2
        data[-1]["indices"] *= 2
        with self.assertRaisesRegex(ValueError, "not split"):
            smoke.validate_mesh_records(data)

    def test_refuse_files_directories_and_dangling_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "existing"
            file.write_text("preserve")
            link = root / "dangling"
            link.symlink_to(root / "absent")
            for path in (root, file, link):
                with self.subTest(path=path), self.assertRaises(FileExistsError):
                    smoke.refuse_existing([path])
            smoke.refuse_existing([root / "new"])
            self.assertEqual(file.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
