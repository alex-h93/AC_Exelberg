#!/usr/bin/env python3
"""One-shot, isolated KN5 Studio smoke test; no install, network, GUI or preferences.

Run with the documented factory-startup Blender command. --check-only is offline
stdlib-only. Existing versioned outputs are never reused, even after a failure.
The pinned third-party package must already be reviewed and installed unchanged.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9"
VENDOR = ROOT / "tools/vendor/kn5_studio"
EVIDENCE = ROOT / "data/processed/kn5_test"
SOURCE = ROOT / "blender/northern_hairpins_v001.blend"
COPY = ROOT / "blender/northern_hairpins_kn5_v001.blend"
OUTPUT = ROOT / "exports/kn5_prototype_v001"
KN5 = OUTPUT / "northern_hairpins_kn5_v001.kn5"
# Explicit exact names, never collection/visibility/name-prefix heuristics.
ALLOWLIST = {
    "1ROAD": (7505, 12000, "KN5_Asphalt"),
    "PROVISIONAL_SHOULDER_L": (3002, 3000, "KN5_Gravel"),
    "PROVISIONAL_SHOULDER_R": (3002, 3000, "KN5_Gravel"),
    "VISUAL_TERRAIN_DERIVED_LOWERED": (106855, 212400, "KN5_Terrain"),
}
COLORS = {
    "KN5_Asphalt": (48, 50, 52, 255),
    "KN5_Gravel": (120, 110, 90, 255),
    "KN5_Terrain": (65, 88, 52, 255),
}


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def refuse_existing(paths):
    for path in paths:
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"Refusing existing output: {path}")


def verify_install():
    review = json.loads((VENDOR / "review.json").read_text())
    provenance = json.loads((VENDOR / "provenance.json").read_text())
    if review["commit"] != COMMIT or provenance["commit"] != COMMIT:
        raise ValueError("Unexpected source commit")
    archive = VENDOR / provenance["archive"]
    if sha256(archive) != provenance["sha256"]:
        raise ValueError("Archive changed")
    install = Path(review["installed_dir"])
    source = VENDOR / "source" / f"KN5Export-{COMMIT}"
    for base in (source, install):
        actual = {}
        for path in base.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Unexpected symlink: {path}")
            if path.is_file():
                actual[str(path.relative_to(base))] = sha256(path)
        if actual != review["files_sha256"]:
            raise ValueError(f"Reviewed package changed: {base}")
    return install


def check_inputs():
    install = verify_install()
    before = json.loads((EVIDENCE / "source_hashes_before.json").read_text())
    expected = before[str(SOURCE)]["sha256"]
    if sha256(SOURCE) != expected:
        raise ValueError("Original prototype changed")
    refuse_existing([OUTPUT, COPY, EVIDENCE / "report.json",
                     EVIDENCE / "expected_geometry.npz"])
    return install


def validate_mesh_records(records):
    """Validate uint16/chunk/material/triangle invariants without third-party code."""
    groups = {name: [] for name in ALLOWLIST}
    for record in records:
        name = record["name"]
        parent = record["source_object"]
        if parent not in groups or not (name == parent or name.startswith(parent + "_SUB")):
            raise ValueError(f"Unexpected exported mesh {name}")
        nv = record["vertices"]
        if not (0 < nv <= 65535 and 0 <= record["min_index"] <= record["max_index"] < nv):
            raise ValueError(f"Unsafe indices/vertices: {name}")
        if record["indices"] != record["triangles"] * 3:
            raise ValueError(f"Non-triangle index stream: {name}")
        if record["material_name"] != ALLOWLIST[parent][2]:
            raise ValueError(f"Unexpected material: {name}")
        groups[parent].append(record)
    for name, (_, nt, _) in ALLOWLIST.items():
        if sum(r["triangles"] for r in groups[name]) != nt:
            raise ValueError(f"Triangle mismatch: {name}")
    if len(groups["VISUAL_TERRAIN_DERIVED_LOWERED"]) < 2:
        raise ValueError("Terrain was not split for uint16")
    return groups


def run(install):
    import bpy
    import numpy as np

    if not bpy.app.background:
        raise RuntimeError("Must run in a separate headless factory-startup Blender")
    if bpy.data.filepath:
        raise RuntimeError("Expected factory startup, not an already loaded file")
    sys.dont_write_bytecode = True
    OUTPUT.mkdir()  # Atomic refusal if another process created it.
    report = {
        "status": "STARTED", "commit": COMMIT, "license": "CC0-1.0",
        "blender": bpy.app.version_string, "blender_build": bpy.app.build_hash.decode(),
        "python": sys.version, "installed_package": str(install),
        "source_blend": str(SOURCE), "source_sha256": sha256(SOURCE),
        "axis": "Blender local metres (east,north,up) -> KN5 (X,Z,-Y); UV (u,1-v); scale 1",
        "allowlist": list(ALLOWLIST), "third_party_source_modified": False,
        "live_gui_or_preferences_accessed": False,
        "disabled": ["auto_fix_wheels", "auto_detect_materials", "skin_sync",
                     "physics_sync", "file_copies", "config_generation", "game_writes",
                     "auto_update", "downloads"],
        "write_audit": [], "structural_issues": [],
    }
    started = time.monotonic()

    def audit(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            raise PermissionError(f"Blocked smoke-test side effect: {event}")
        if event != "open":
            return
        path, mode, flags = args
        writing = (mode and any(c in mode for c in "wax+")) or (
            flags and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and not isinstance(path, int):
            path = Path(path).resolve()
            if not (path.is_relative_to(OUTPUT) or path.is_relative_to(EVIDENCE)):
                raise PermissionError(f"Blocked Python write: {path}")
            if len(report["write_audit"]) < 128:
                report["write_audit"].append(str(path))
    # Native Blender C file IO is not covered; its only save call names COPY below.
    sys.addaudithook(audit)
    try:
        spec = importlib.util.spec_from_file_location("kn5_studio", install / "__init__.py",
                                                    submodule_search_locations=[str(install)])
        addon = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = addon
        spec.loader.exec_module(addon)
        addon.register()  # In-process RNA registration, NOT addon_utils.enable/save prefs.
        report["addon_version"] = list(addon.bl_info["version"])
        report["registration"] = "PASS; full reviewed package, this process only"
        bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False, use_scripts=False)
        objects = [bpy.data.objects[name] for name in ALLOWLIST]
        report["excluded_objects"] = sorted(o.name for o in bpy.context.scene.objects if o not in objects)
        arrays = {}
        source_records = []
        for number, obj in enumerate(objects):
            nv, nt, material = ALLOWLIST[obj.name]
            if obj.type != "MESH" or obj.parent or obj.modifiers:
                raise ValueError(f"Expected unparented, unmodified mesh: {obj.name}")
            if any(abs(obj.matrix_world[r][c] - (r == c)) > 1e-7
                   for r in range(4) for c in range(4)):
                raise ValueError(f"Unexpected transform: {obj.name}")
            mesh = obj.data
            mesh.calc_loop_triangles()
            if (len(mesh.vertices), len(mesh.loop_triangles)) != (nv, nt) or not mesh.uv_layers.active:
                raise ValueError(f"Source mesh counts/UV mismatch: {obj.name}")
            vertices = np.empty((nv, 3), dtype=np.float32)
            mesh.vertices.foreach_get("co", vertices.ravel())
            triangles = np.array([tuple(t.vertices) for t in mesh.loop_triangles], dtype=np.int32)
            corner_uv = np.array([[tuple(mesh.uv_layers.active.data[i].uv) for i in t.loops]
                                  for t in mesh.loop_triangles], dtype=np.float32)
            if not all(np.isfinite(a).all() for a in (vertices, corner_uv)):
                raise ValueError("Nonfinite source coordinates/UV")
            lo, hi = vertices.min(axis=0), vertices.max(axis=0)
            record = {"name": obj.name, "vertices": nv, "triangles": nt,
                      "material_name": material, "npz_prefix": f"mesh{number}",
                      "bounds_blender": [lo.tolist(), hi.tolist()],
                      "bounds_kn5_expected": [[float(lo[0]), float(lo[2]), float(-hi[1])],
                                              [float(hi[0]), float(hi[2]), float(-lo[1])]],
                      "uv_layers": [u.name for u in mesh.uv_layers]}
            source_records.append(record)
            for key, array in (("vertices", vertices), ("triangles", triangles), ("corner_uv", corner_uv)):
                arrays[f"mesh{number}_{key}"] = array
        report["source_meshes"] = source_records
        np.savez_compressed(EVIDENCE / "expected_geometry.npz", **arrays)
        report["expected_geometry_sha256"] = sha256(EVIDENCE / "expected_geometry.npz")
        print("KN5_STAGE source geometry captured", flush=True)

        for name, rgba in COLORS.items():
            filename = name.lower() + ".dds"
            payload = addon.dds.create_solid_color_dds(*rgba, width=4, height=4)
            with (OUTPUT / filename).open("xb") as f:
                f.write(payload)
            image = bpy.data.images.load(str(OUTPUT / filename), check_existing=False)
            image.name = filename
            image.pack()
            mat = bpy.data.materials.new(name)
            ac = mat.assettoCorsa
            ac.preset_selector = "NONE"
            ac.shader_name = "ksPerPixel"
            ac.blend_mode = "0"
            ac.depth_mode = "0"
            ac.alpha_tested = False
            for key, value in {"ksAmbient": 0.4, "ksDiffuse": 0.6,
                               "ksSpecular": 0.05, "ksSpecularEXP": 10.0}.items():
                ac.set_property(key, value)
            ac.ensure_default_slots_for_shader("ksPerPixel")
            slot = ac.texture_slots[0]
            slot.image, slot.override_filename = image, filename
            addon.materials.sync_material_nodes(mat)
            mat.diffuse_color = tuple(v / 255 for v in rgba)
        for obj in objects:
            obj.data.materials.clear()
            obj.data.materials.append(bpy.data.materials[ALLOWLIST[obj.name][2]])
        report["texture_audit"] = addon.materials.audit_texture_bindings(objects, "EMBEDDED_DDS")
        if report["texture_audit"]:
            raise ValueError(report["texture_audit"])
        options = {"version": 5, "texture_mode": "EMBEDDED_DDS", "target_objects": objects,
                   "apply_modifiers": False, "auto_detect_materials": False,
                   "auto_fix_wheels": False, "selection_only": False}
        report["export_options"] = {k: v for k, v in options.items() if k != "target_objects"}
        # Core API deliberately bypasses the operator's default skin-copy post-step.
        exporter = addon.exporter.KN5Exporter(bpy.context, str(KN5), options)
        model = exporter.export()
        report["export_warnings"] = exporter.warnings
        print("KN5_STAGE exporter returned model", flush=True)

        def summarize(model):
            meshes, dummies = [], []
            def visit(node, parent=None):
                if node.node_type == 1:
                    dummies.append({"name": node.name, "transform": node.transform,
                                    "children": len(node.children)})
                    if node.transform != addon.exporter.identity_matrix16():
                        raise ValueError("Unexpected nonidentity output dummy")
                elif node.node_type == 2:
                    source_name = next((n for n in ALLOWLIST
                                        if node.name == n or node.name.startswith(n + "_SUB")), None)
                    p = np.array([v.position for v in node.vertices], dtype=np.float64)
                    n = np.array([v.normal for v in node.vertices], dtype=np.float64)
                    t = np.array([v.tangent for v in node.vertices], dtype=np.float64)
                    uv = np.array([v.uv for v in node.vertices], dtype=np.float64)
                    idx = np.array(node.indices, dtype=np.int64).reshape(-1, 3)
                    if not all(np.isfinite(a).all() for a in (p, n, t, uv)):
                        raise ValueError("Nonfinite exported vertex fields")
                    if not len(p) or idx.min() < 0 or idx.max() >= len(p):
                        raise ValueError("Unsafe exported indices")
                    cross = np.cross(p[idx[:, 1]] - p[idx[:, 0]], p[idx[:, 2]] - p[idx[:, 0]])
                    degenerate = int(np.count_nonzero(np.linalg.norm(cross, axis=1) < 1e-10))
                    downward = int(np.count_nonzero(cross[:, 1] <= 0))
                    meshes.append({"name": node.name, "source_object": source_name,
                        "parent": parent, "vertices": len(p), "indices": len(node.indices),
                        "triangles": len(idx), "min_index": int(idx.min()), "max_index": int(idx.max()),
                        "material_id": node.material_id, "material_name": model.materials[node.material_id].name,
                        "bounds_kn5": [p.min(axis=0).tolist(), p.max(axis=0).tolist()],
                        "uv_bounds": [uv.min(axis=0).tolist(), uv.max(axis=0).tolist()],
                        "normal_length_range": [float(x) for x in (np.linalg.norm(n, axis=1).min(), np.linalg.norm(n, axis=1).max())],
                        "tangent_length_range": [float(x) for x in (np.linalg.norm(t, axis=1).min(), np.linalg.norm(t, axis=1).max())],
                        "max_abs_normal_dot_tangent": float(np.abs((n*t).sum(axis=1)).max()),
                        "degenerate_triangles": degenerate, "non_upward_triangles": downward,
                        "cast_shadows": node.cast_shadows, "visible": node.visible,
                        "transparent": node.transparent, "renderable": node.renderable,
                        "layer": node.layer, "lod_in": node.lod_in, "lod_out": node.lod_out})
                    if degenerate or downward:
                        raise ValueError(f"Winding/degeneracy issue: {node.name}")
                else:
                    raise ValueError(f"Unexpected node type: {node.node_type}")
                for child in node.children:
                    visit(child, node.name)
            visit(model.root_node)
            groups = validate_mesh_records(meshes)
            for source in source_records:
                group = groups[source["name"]]
                bounds = [np.min([r["bounds_kn5"][0] for r in group], axis=0),
                          np.max([r["bounds_kn5"][1] for r in group], axis=0)]
                if not np.allclose(bounds, source["bounds_kn5_expected"], atol=1e-6, rtol=0):
                    raise ValueError(f"Output bounds mismatch: {source['name']}")
            return {"meshes": meshes, "dummies": dummies,
                    "triangles": sum(m["triangles"] for m in meshes)}
        report["model"] = summarize(model)
        report["materials"] = [{"id": i, "name": m.name, "shader": m.shader,
            "blend_mode": m.blend_mode, "depth_mode": m.depth_mode,
            "alpha_tested": m.alpha_tested, "properties": {p.name: p.valueA for p in m.properties},
            "texture_mappings": m.texture_mappings} for i, m in enumerate(model.materials)]
        report["textures"] = []
        for i, texture in enumerate(model.textures):
            info = addon.dds.parse_dds_header(texture.data)
            expected_name = next(name for name in COLORS if name.lower() + ".dds" == texture.name)
            expected_payload = addon.dds.create_solid_color_dds(*COLORS[expected_name], width=4, height=4)
            if texture.data != expected_payload:
                raise ValueError("Generated texture payload differs")
            report["textures"].append({"id": i, "name": texture.name, "active": texture.active,
                "bytes": len(texture.data), "sha256": hashlib.sha256(texture.data).hexdigest(),
                "width": info.width, "height": info.height, "mipmaps": info.mipmaps,
                "format": info.format_name, "rgba8": COLORS[expected_name]})
        if len(model.materials) != 3 or len(model.textures) != 3:
            raise ValueError("Unexpected material/texture count")
        with KN5.open("xb") as f:
            model.to_stream(f)
        with KN5.open("rb") as f:
            parsed = addon.kn5_format.KN5Model.from_stream(f)
            if f.tell() != KN5.stat().st_size:
                raise ValueError("Same-library reader did not consume entire file")
        report["roundtrip_model"] = summarize(parsed)
        buffer = io.BytesIO()
        parsed.to_stream(buffer)
        if buffer.getvalue() != KN5.read_bytes():
            raise ValueError("Same-library binary reserialization differs")
        report["same_library_roundtrip"] = "PASS; full EOF, mesh invariants, byte-identical reserialization; NOT independent validation"
        report["kn5"] = {"path": str(KN5), "bytes": KN5.stat().st_size,
                         "sha256": sha256(KN5), "version": parsed.version}
        # Save only a fresh material-configured copy. No geometry edits or live-file access.
        refuse_existing([COPY])
        bpy.ops.wm.save_as_mainfile(filepath=str(COPY), check_existing=True, copy=True)
        report["configured_blend"] = {"path": str(COPY), "bytes": COPY.stat().st_size, "sha256": sha256(COPY)}
        report["status"] = "PASS_EXPORT_AND_SAME_LIBRARY_ROUNDTRIP"
        print("KN5_STAGE PASS", report["kn5"], flush=True)
    except Exception as exc:
        report["status"] = "BLOCKED"
        report["exception"] = {"type": type(exc).__name__, "message": str(exc),
                               "traceback": traceback.format_exc()}
        print("KN5_STAGE BLOCKED", report["exception"]["traceback"], flush=True)
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        with (EVIDENCE / "report.json").open("x") as f:
            json.dump(report, f, indent=2, allow_nan=False)
            f.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    install = check_inputs()
    if args.check_only:
        print("PASS: pinned archive, source/install hashes, original blend and no-overwrite preflight")
        return
    run(install)


if __name__ == "__main__":
    main()
