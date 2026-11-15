"""Read-only project probe; run ONLY in a factory-startup background Blender.

Example (host shell, 120-second limit):
  timeout --signal=TERM --kill-after=10s 120s flatpak run org.blender.Blender \
    --background --factory-startup --disable-autoexec --python-exit-code 1 \
    --python "$PWD/scripts/check_blender_readiness.py"

No preferences are saved, packages installed, or real route geometry constructed.
Synthetic exports and .blend files live only in TemporaryDirectory and are removed.
"""

import sys

sys.dont_write_bytecode = True

import csv
import importlib
import json
from pathlib import Path
import tempfile
import traceback

import bpy


FAILURES = []


def report(name, **values):
    print("READINESS " + json.dumps({"check": name, **values}, sort_keys=True), flush=True)


def check(name, function):
    try:
        function()
    except Exception as exc:
        FAILURES.append(name)
        report(name, status="FAIL", error=f"{type(exc).__name__}: {exc}")
        traceback.print_exc()


def version():
    def text(value):
        return value.decode(errors="replace") if isinstance(value, bytes) else value

    report("runtime", version=bpy.app.version_string, version_tuple=bpy.app.version,
           build_hash=text(bpy.app.build_hash), build_date=text(bpy.app.build_date),
           build_time=text(bpy.app.build_time), build_branch=text(bpy.app.build_branch),
           build_platform=text(bpy.app.build_platform), binary=bpy.app.binary_path,
           background=bpy.app.background, python=sys.version, executable=sys.executable)
    assert bpy.app.background, "Background execution is required"


def project_access():
    root = Path(__file__).resolve().parent.parent
    route_path = root / "data/processed/route.geojson"
    route = json.loads(route_path.read_text(encoding="utf-8"))
    lines = [feature["geometry"]["coordinates"] for feature in route["features"]
             if feature["geometry"]["type"] == "LineString"]
    assert lines and len(lines[0]) > 2
    with (root / "data/processed/route_elevation.csv").open(newline="") as stream:
        samples = list(csv.DictReader(stream))
    assert samples and all(float(row["terrain_height_m"]) > 0 for row in samples)
    summary = json.loads((root / "data/processed/elevation_summary.json").read_text())
    assert len(samples) == summary["samples"]
    terrain = root / "data/processed/terrain_corridor_3035.tif"
    with terrain.open("rb") as stream:
        header = stream.read(16)
    assert header[:4] in (b"II*\0", b"MM\0*", b"II+\0", b"MM\0+")
    report("project_access", status="PASS", root=str(root),
           route_points=sum(map(len, lines)), elevation_samples=len(samples),
           terrain_bytes=terrain.stat().st_size, terrain_header_hex=header.hex(),
           note="TIFF readability/header only, not raster decoding or scene import")


def numpy_check():
    import numpy as np

    data = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    assert np.isfinite(data).all()
    report("numpy", status="PASS", version=np.__version__, module=np.__file__)


def operator_available(namespace, name):
    try:
        getattr(getattr(bpy.ops, namespace), name).get_rna_type()
        return True
    except (AttributeError, RuntimeError):
        return False


def exporters():
    operators = [("export_scene", "fbx"), ("export_scene", "gltf"),
                 ("wm", "obj_export"), ("wm", "ply_export"), ("wm", "stl_export")]
    report("export_operators_initial", available={f"{ns}.{name}": operator_available(ns, name)
                                                for ns, name in operators})
    if not operator_available("export_scene", "fbx"):
        import addon_utils

        paths = addon_utils.paths()
        spec = importlib.machinery.PathFinder.find_spec("io_scene_fbx", paths)
        report("fbx_discovery", addon_paths=paths, module_origin=spec.origin if spec else None)
        if spec is not None:
            # Register only the shipped module in this throwaway factory process.
            # No addon preference enabling, extension installation or save_userpref.
            parent = str(Path(spec.origin).parent.parent)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            importlib.import_module("io_scene_fbx").register()
            report("fbx_registration", status="PASS", method="io_scene_fbx.register() in memory")
    report("export_operators_final", available={f"{ns}.{name}": operator_available(ns, name)
                                              for ns, name in operators},
           fbx_module=getattr(sys.modules.get("io_scene_fbx"), "__file__", None))


def synthetic_roundtrip():
    # A single synthetic triangle only; never construct or save real project data.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    import numpy as np

    # Exercise a tiny JSON/NumPy -> native mesh interchange, not GIS raster import.
    intermediate = json.loads('{"vertices": [[0,0,0], [1,0,0], [0,1,0]], "faces": [[0,1,2]]}')
    vertices = np.asarray(intermediate["vertices"], dtype=np.float32)
    mesh = bpy.data.meshes.new("ReadinessTriangle")
    mesh.from_pydata(vertices.tolist(), [], intermediate["faces"])
    mesh.update()
    obj = bpy.data.objects.new("ReadinessTriangle", mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    assert len(mesh.vertices) == 3 and len(mesh.polygons) == 1
    assert len(mesh.polygons[0].vertices) == 3
    report("native_mesh_from_json_numpy", status="PASS", vertices=3, triangles=1)
    with tempfile.TemporaryDirectory(prefix="exelberg-blender-readiness-") as directory:
        tmp = Path(directory)
        try:
            assert operator_available("export_scene", "fbx"), "FBX export operator unavailable"
            output = tmp / "triangle.fbx"
            result = bpy.ops.export_scene.fbx(filepath=str(output), use_selection=True,
                                              object_types={"MESH"})
            assert result == {"FINISHED"}
            with output.open("rb") as stream:
                header = stream.read(27)
            assert output.stat().st_size > 27 and header.startswith(b"Kaydara FBX Binary  \0\x1a\0")
            report("fbx_export", status="PASS", bytes=output.stat().st_size,
                   header_hex=header.hex(), file_version=int.from_bytes(header[23:27], "little"))
        except Exception as exc:
            FAILURES.append("fbx_export")
            report("fbx_export", status="FAIL", error=f"{type(exc).__name__}: {exc}")
            # Test an actually available fallback, not an assumed installable extension.
            if operator_available("wm", "obj_export"):
                output = tmp / "triangle.obj"
                result = bpy.ops.wm.obj_export(filepath=str(output), export_selected_objects=True)
                assert result == {"FINISHED"} and output.stat().st_size > 0
                report("obj_fallback", status="PASS", bytes=output.stat().st_size)
        blend = tmp / "triangle.blend"
        assert bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False) == {"FINISHED"}
        assert blend.stat().st_size > 0
        assert bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False) == {"FINISHED"}
        loaded = bpy.data.objects.get("ReadinessTriangle")
        assert loaded is not None and len(loaded.data.vertices) == 3 and len(loaded.data.polygons) == 1
        report("blend_roundtrip", status="PASS", bytes=blend.stat().st_size)
    assert not tmp.exists()
    report("temporary_cleanup", status="PASS", directory_removed=True)


for name, function in [("runtime", version), ("project_access", project_access),
                       ("numpy", numpy_check), ("exporters", exporters),
                       ("synthetic_roundtrip", synthetic_roundtrip)]:
    check(name, function)
report("summary", status="FAIL" if FAILURES else "PASS", failures=FAILURES)
if FAILURES:
    raise RuntimeError("Readiness failures: " + ", ".join(FAILURES))
