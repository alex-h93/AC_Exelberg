"""Build the OFFLINE provisional section in existing factory-startup Blender.

  timeout --signal=TERM --kill-after=10s 240s flatpak run org.blender.Blender \
    --background --factory-startup --disable-autoexec --threads 8 \
    --python-exit-code 1 --python "$PWD/scripts/build_blender_prototype.py"

For read-only numerical preflight with project NumPy (no Blender):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/build_blender_prototype.py --check-only

Never imports project venv packages into Blender. Never overwrites existing output
assets or report directory. No installation, preferences, acquisition or networking.
"""
import sys
sys.dont_write_bytecode = True
import csv
import hashlib
import importlib
import json
from pathlib import Path
import struct
import time

import numpy as np

# Only this project's NumPy-only geometry helper, not site-packages, is added.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prototype_geometry as geom

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data/processed/prototype/manifest.json"
OUT = ROOT / "data/processed/prototype_scene"
BLEND = ROOT / "blender/northern_hairpins_v001.blend"
FBX = ROOT / "exports/northern_hairpins_v001.fbx"


def checked_path(relative):
    path = (ROOT / relative).resolve()
    geom.require(path.is_relative_to(ROOT), "Path outside project")
    return path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_artifact(record):
    path = checked_path(record["path"])
    geom.require(path.stat().st_size == record["bytes"], f"Size mismatch: {path}")
    geom.require(sha(path) == record["sha256"], f"SHA256 mismatch: {path}")
    return path


def load_inputs():
    manifest = json.loads(MANIFEST.read_text())
    geom.require(manifest["schema"] == "assetto-exelberg.prototype-inputs" and manifest["version"] == 1,
                 "Unsupported input schema")
    coordinates = manifest["coordinates"]
    geom.require(coordinates["horizontal_epsg"] == 25833 and coordinates["vertical_epsg"] == 9274
                 and coordinates["units"] == "m" and coordinates["origin_m"] == [589500., 5346800., 300.],
                 "Coordinate contract mismatch")
    geom.require(manifest["section"]["start_m"] == 1000 and manifest["section"]["end_m"] == 2500,
                 "Unexpected section")
    # Verify all original provenance records as well as the immediate NPZ inputs.
    for record in manifest["provenance"]["inputs"]:
        verified_artifact(record)
    artifacts = {name: verified_artifact(record) for name, record in manifest["outputs"].items()}
    loaded = {}
    for name in ("route", "terrain"):
        record = manifest["outputs"][name]
        with np.load(artifacts[name], allow_pickle=False) as archive:
            geom.require(set(archive.files) == set(record["arrays"]), f"Unexpected {name} keys")
            arrays = {}
            for key, spec in record["arrays"].items():
                value = archive[key]
                geom.require(list(value.shape) == spec["shape"] and str(value.dtype) == spec["dtype"],
                             f"Schema mismatch: {name}/{key}")
                geom.require(np.isfinite(value).all(), f"Nonfinite {name}/{key}")
                arrays[key] = value.copy()
            loaded[name] = arrays
    r, t = loaded["route"], loaded["terrain"]
    geom.require(r["valid"].dtype == np.bool_ and r["valid"].all(), "Invalid raw route heights")
    geom.require(len(r["valid"]) == manifest["section"]["samples"], "Route count mismatch")
    geom.require(np.all(np.diff(r["chainage_3035_m"]) > 0) and
                 np.array_equal(r["chainage_3035_m"][[0, -1]], [1000., 2500.]), "Invalid chainages")
    geom.require(np.allclose(r["local_xyz_m"][:, :2], r["xy_25833_m"] - coordinates["origin_m"][:2],
                            rtol=0, atol=1e-8), "Local XY mapping mismatch")
    geom.require(np.allclose(r["local_xyz_m"][:, 2], r["raw_height_9274_m"] - 300,
                            rtol=0, atol=1e-10), "Local Z mapping mismatch")
    steps = np.linalg.norm(np.diff(r["local_xyz_m"][:, :2], axis=0), axis=1)
    geom.require((steps > 0).all() and steps.max() <= 2 + 1e-8, "Invalid raw sampling")
    geom.require(t["valid"].dtype == np.bool_ and t["valid_cells"].dtype == np.bool_, "Missing bool masks")
    geom.require(np.all(t["z_m"][~t["valid"]] == 0), "Invalid placeholders")
    resolution = manifest["terrain"]["resolution_m"]
    geom.require(np.allclose(np.diff(t["x_m"], axis=1), resolution) and
                 np.allclose(np.diff(t["y_m"], axis=0), resolution) and
                 np.all(np.diff(t["x_m"], axis=0) == 0) and
                 np.all(np.diff(t["y_m"], axis=1) == 0), "Terrain axes/grid mismatch")
    geom.require(np.count_nonzero(t["valid"]) == manifest["terrain"]["valid_vertices"] and
                 np.count_nonzero(t["valid_cells"]) == manifest["terrain"]["valid_cells"], "Mask count mismatch")
    geom.valid_terrain_faces(t["valid"], t["valid_cells"])
    controls = manifest["controls"]
    expected = np.column_stack([np.array(controls["working_25833_m"]) - coordinates["origin_m"][:2],
                                np.zeros(len(controls["working_25833_m"]))])
    geom.require(np.allclose(expected, controls["local_xyz_m"], rtol=0, atol=1e-8), "Control mapping failure")
    return manifest, r, t


def offset_stats(values):
    return {"max": float(values.max()), "mean": float(values.mean()),
            "rms": float(np.sqrt(np.mean(values**2))), "p95": float(np.percentile(values, 95))}


def prepare_geometry(manifest, r, t):
    raw = r["local_xyz_m"]
    source_s, s, original, designed = geom.smooth_samples(raw)
    station = np.interp(s, source_s, r["chainage_3035_m"])
    designed_s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(designed[:, :2], axis=0), axis=1))]
    meshes = {}
    for name, offsets in [("1ROAD", [-3., -1.5, 0., 1.5, 3.]),
                          ("PROVISIONAL_SHOULDER_L", [3., 3.75]),
                          ("PROVISIONAL_SHOULDER_R", [-3.75, -3.])]:
        vertices, faces = geom.ribbon(designed, offsets)
        uv = np.column_stack([np.tile(np.array(offsets) / 6, len(s)),
                              np.repeat(designed_s / 6, len(offsets))])
        meshes[name] = (vertices, faces, uv)
    overlap = geom.ribbon_overlap(designed)
    raw_overlap = geom.ribbon_overlap(raw)
    # Entire-width quads: both triangles and both diagonals must be upward.
    v, f = geom.ribbon(designed, [-3.75, 3.75])
    quad = v.reshape(-1, 2, 3)
    alt = np.stack([quad[:-1, 0], quad[1:, 0], quad[:-1, 1],
                    quad[1:, 0], quad[1:, 1], quad[:-1, 1]], axis=1).reshape(-1, 3, 3)
    alt_cross = np.cross(alt[:, 1] - alt[:, 0], alt[:, 2] - alt[:, 0])[:, 2]
    geom.require(np.all(alt_cross > 1e-9), "Folded/nonconvex ribbon quad")
    geom.require(not overlap, f"Ribbon self-overlap: {overlap[:10]}")
    lowered, touched = geom.lower_terrain(t["x_m"], t["y_m"], t["z_m"], t["valid_cells"], designed)
    clearance = geom.terrain_clearance(t["x_m"], t["y_m"], lowered, t["valid_cells"], designed)
    geom.require(clearance >= 0.25 - 1e-9, "Terrain intrusion")
    terrain_vertices = np.column_stack([t["x_m"].ravel(), t["y_m"].ravel(), lowered.ravel()])
    faces = geom.valid_terrain_faces(t["valid"], t["valid_cells"])
    terrain_uv = terrain_vertices[:, :2] / 20
    meshes["VISUAL_TERRAIN_DERIVED_LOWERED"] = (terrain_vertices, faces, terrain_uv)
    checks = {name: geom.mesh_checks(v, f) for name, (v, f, uv) in meshes.items()}
    for name, check in checks.items():
        geom.require(check["degenerate_triangles"] == 0 and check["non_upward_triangles"] == 0,
                     f"Bad geometry: {name}: {check}")
    delta = designed - original
    proximity = float("inf")
    closest = None
    for i in range(len(s)):
        distances = np.linalg.norm(designed[:, :2] - designed[i, :2], axis=1)
        distances[np.abs(s - s[i]) <= 30] = np.inf
        j = int(distances.argmin())
        if distances[j] < proximity:
            proximity = float(distances[j]); closest = [i, j]
    lowering = t["z_m"] - lowered
    report = {
        "schema": "assetto-exelberg.blender-prototype", "version": 1,
        "purpose": "Offline visual/export prototype; NOT playable, timing-ready or survey accurate",
        "input_manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha(MANIFEST)},
        "verified_provenance_files": len(manifest["provenance"]["inputs"]),
        "input_artifacts": manifest["outputs"], "coordinates": manifest["coordinates"],
        "attribution": manifest["provenance"]["attribution"],
        "section_chainage_3035_m": [1000, 2500],
        "design": {"width_m": 6, "shoulder_each_side_m": 0.75, "crossfall_percent": 0, "camber_percent": 0,
                   "measured": False, "uniform_source_spacing_max_m": float(np.diff(s).max()),
                   "stations": len(s), "xy_gaussian_sigma_m": 2, "z_gaussian_sigma_m": 3,
                   "gaussian_support_sigma": 3, "endpoints_pinned": True,
                   "reason": "Raw OSM heading jumps and DTM grade steps; light visual/profile regularization, not survey correction",
                   "xy_offset_m": offset_stats(np.linalg.norm(delta[:, :2], axis=1)),
                   "absolute_z_offset_m": offset_stats(np.abs(delta[:, 2])),
                   "signed_z_offset_min_max_m": [float(delta[:, 2].min()), float(delta[:, 2].max())]},
        "raw_profile": geom.profile_stats(raw), "designed_profile": geom.profile_stats(designed),
        "slope_step_reporting": {"threshold_percentage_points": 1.0,
                                 "raw_exceedances": int(np.count_nonzero(np.abs(np.diff(np.diff(raw[:, 2]) / np.diff(source_s))) > .01)),
                                 "designed_exceedances": int(np.count_nonzero(np.abs(np.diff(np.diff(designed[:, 2]) / np.diff(designed_s))) > .01)),
                                 "note": "All raw and designed grades/steps retained in audit files; no asphalt accuracy claim"},
        "topology": {"mesh_checks": checks, "quad_fold_count": int(np.count_nonzero(alt_cross <= 1e-9)),
                     "raw_full_width_self_overlap_pairs": raw_overlap, "designed_full_width_self_overlap_pairs": overlap,
                     "nonlocal_node_exclusion_source_m": 30, "closest_nonlocal_node_pair": closest,
                     "closest_nonlocal_node_distance_m": proximity,
                     "nonlocal_segment_distance_lower_bound_m": proximity - 2 * float(np.diff(s).max()),
                     "note": "SAT on all non-neighbour 7.5m-wide quads; node-distance bound is conservative, not measured road separation"},
        "terrain_lowering": {"strategy": "Every valid cell with AABB intersection with full shoulder ribbon: lower ALL four vertices to <= min segment Z - 0.25m; no raising. Conservative superset; original hidden unchanged.",
                             "clearance_m": 0.25, "verified_conservative_clearance_m": clearance,
                             "aabb_touched_cells": int(touched.sum()), "lowered_vertices": int(np.count_nonzero(lowering > 0)),
                             "max_lowering_m": float(lowering.max()), "mean_lowering_affected_m": float(lowering[lowering > 0].mean()),
                             "limitation": "Artificial local trench/cut, not surveyed cutting/retaining walls; no joined geological or physical verge claim"},
        "export": {"format": "binary FBX", "axis_forward": "-Z", "axis_up": "Y", "global_scale": 1,
                   "scene_units": "METRIC, scale_length=1 metre", "apply_unit_scale": True,
                   "apply_scale_options": "FBX_SCALE_UNITS", "bake_space_transform": False,
                   "triangulation": "Explicit triangles in every exported mesh, use_triangles=True",
                   "selection": list(meshes), "windows_sdk_validated": False},
        "limitations": manifest["caveats"] + ["No timing/spawn/game configuration, KN5, collision or suspension test", "Flat width/camber are invented provisional design parameters, not observations", "Windows FBX/ksEditor scale/axes/material mapping unvalidated"]}
    return meshes, source_s, s, original, designed, station, designed_s, lowered, touched, report


def save_audit(r, t, values):
    meshes, source_s, s, original, designed, station, designed_s, lowered, touched, report = values
    np.savez_compressed(OUT / "geometry_audit.npz", raw_local_xyz_m=r["local_xyz_m"],
                        raw_chainage_3035_m=r["chainage_3035_m"], source_arclength_m=source_s,
                        source_parameter_m=s, raw_interpolated_xyz_m=original, designed_xyz_m=designed,
                        delta_xyz_m=designed-original, chainage_3035_m=station,
                        designed_arclength_xy_m=designed_s, terrain_lowered_z_m=lowered,
                        terrain_delta_z_m=lowered-t["z_m"], terrain_valid=t["valid"],
                        terrain_valid_cells=t["valid_cells"], terrain_aabb_touched_cells=touched)
    def rows(path, labels, cols):
        with path.open("x", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(labels)
            writer.writerows(zip(*cols))
    grade = np.r_[np.diff(designed[:, 2]) / np.diff(designed_s) * 100, np.nan]
    steps = np.r_[np.diff(grade[:-1]), np.nan, np.nan]
    rows(OUT / "stations.csv", ["chainage_3035_m", "source_section_arclength_m", "designed_section_arclength_xy_m",
                                "raw_interp_x_m", "raw_interp_y_m", "raw_interp_z_m", "designed_x_m", "designed_y_m", "designed_z_m",
                                "delta_x_m", "delta_y_m", "delta_z_m", "grade_to_next_percent", "grade_step_to_next_pp", "width_m", "shoulder_each_m", "camber_percent"],
         [station, s, designed_s, *original.T, *designed.T, *(designed-original).T, grade, steps,
          np.full(len(s), 6.), np.full(len(s), .75), np.zeros(len(s))])
    raw = r["local_xyz_m"]
    raw_grade = np.r_[np.diff(raw[:, 2]) / np.diff(source_s) * 100, np.nan]
    design_at_raw = np.column_stack([np.interp(source_s, s, designed[:, k]) for k in range(3)])
    rows(OUT / "raw_controls.csv", ["chainage_3035_m", "source_section_arclength_m", "raw_x_m", "raw_y_m", "raw_z_m", "raw_grade_to_next_percent", "raw_grade_step_to_next_pp", "design_delta_x_m", "design_delta_y_m", "design_delta_z_m"],
         [r["chainage_3035_m"], source_s, *raw.T, raw_grade, np.r_[np.diff(raw_grade[:-1]), np.nan, np.nan], *(design_at_raw-raw).T])


def fbx_module():
    import bpy
    try:
        bpy.ops.export_scene.fbx.get_rna_type()
    except (AttributeError, RuntimeError):
        import addon_utils
        spec = importlib.machinery.PathFinder.find_spec("io_scene_fbx", addon_utils.paths())
        geom.require(spec is not None, "Bundled FBX exporter unavailable; no installation allowed")
        sys.path.insert(0, str(Path(spec.origin).parent.parent))
        importlib.import_module("io_scene_fbx").register()


def build_scene(manifest, r, t, values):
    import bpy
    from mathutils import Vector
    meshes, source_s, s, original, designed, station, designed_s, lowered, touched, report = values
    geom.require(bpy.app.background, "Run only in headless factory-startup Blender")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    scene.unit_settings.length_unit = "METERS"
    collections = {}
    for name in ["EXPORT_ROAD_PHYSICS_CANDIDATE", "EXPORT_PROVISIONAL_SHOULDERS", "EXPORT_VISUAL_TERRAIN", "REFERENCE_ORIGINAL_UNTOUCHED_NONEXPORT", "DEBUG_ALIGNMENT_MARKERS_NONEXPORT", "CAMERAS_LIGHTS_NONEXPORT"]:
        c = bpy.data.collections.new(name); scene.collection.children.link(c); collections[name] = c
    ref = collections["REFERENCE_ORIGINAL_UNTOUCHED_NONEXPORT"]
    ref.hide_render = True; ref.hide_viewport = True
    debug = collections["DEBUG_ALIGNMENT_MARKERS_NONEXPORT"]
    def material(name, color, roughness=0.85):
        m = bpy.data.materials.new(name); m.diffuse_color = (*color, 1)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*color, 1)
        bsdf.inputs["Roughness"].default_value = roughness
        return m
    roadmat = material("PROVISIONAL_Asphalt_NoMeasuredSurface", (.095, .115, .14))
    shoulder = material("PROVISIONAL_Shoulder_Gravel", (.43, .35, .24))
    terrainmat = material("DTM_Visual_GreenGrey", (.24, .32, .19))
    yellow = material("DEBUG_Direction_Centreline_NotRoadMarking", (.95, .63, .06))
    white = material("DEBUG_Chainage_Label", (.95, .94, .83))
    rawmat = material("REFERENCE_Raw_OSM_DTM", (.75, .03, .03))
    def make_mesh(name, vertices, faces, uv, collection, mat, smooth=False):
        mesh = bpy.data.meshes.new(name + "_MESH")
        mesh.from_pydata(vertices.tolist(), [], faces.tolist()); mesh.update()
        geom.require(not mesh.validate(verbose=False), f"Blender repaired unexpected invalid mesh: {name}")
        layer = mesh.uv_layers.new(name="UV_Metric_Provisional")
        loop_ids = np.empty(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_ids)
        layer.data.foreach_set("uv", np.asarray(uv[loop_ids], dtype=np.float32).ravel())
        if smooth:
            mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=bool))
        obj = bpy.data.objects.new(name, mesh); collection.objects.link(obj)
        obj.data.materials.append(mat)
        obj["provisional_not_measured"] = True
        obj["coordinate_contract"] = "X=east,Y=north,Z=up metres; origin 589500,5346800,300"
        return obj
    exported = []
    for name, (vertices, faces, uv) in meshes.items():
        if name == "1ROAD":
            c, mat = collections["EXPORT_ROAD_PHYSICS_CANDIDATE"], roadmat
        elif "SHOULDER" in name:
            c, mat = collections["EXPORT_PROVISIONAL_SHOULDERS"], shoulder
        else:
            c, mat = collections["EXPORT_VISUAL_TERRAIN"], terrainmat
        obj = make_mesh(name, vertices, faces, uv, c, mat, smooth="TERRAIN" in name)
        obj["export_role"] = "unvalidated physical road candidate" if name == "1ROAD" else "provisional shoulder candidate" if "SHOULDER" in name else "visual only; no collision declaration"
        exported.append(obj)
    raw_terrain = np.column_stack([t["x_m"].ravel(), t["y_m"].ravel(), t["z_m"].ravel()])
    reference = make_mesh("REFERENCE_ORIGINAL_DTM_UNMODIFIED", raw_terrain,
                          meshes["VISUAL_TERRAIN_DERIVED_LOWERED"][1], raw_terrain[:, :2]/20, ref, terrainmat, True)
    reference["source_sha256"] = manifest["outputs"]["terrain"]["sha256"]
    reference["provisional_not_measured"] = False
    def curve(name, xyz, collection, mat, bevel=0):
        data = bpy.data.curves.new(name, "CURVE"); data.dimensions = "3D"
        data.resolution_u = 1; data.bevel_depth = bevel; data.bevel_resolution = 0
        poly = data.splines.new("POLY"); poly.points.add(len(xyz)-1)
        poly.points.foreach_set("co", np.column_stack([xyz, np.ones(len(xyz))]).ravel())
        obj = bpy.data.objects.new(name, data); collection.objects.link(obj); data.materials.append(mat)
        return obj
    curve("REFERENCE_Raw_OSM_DTM_837_points", r["local_xyz_m"], ref, rawmat, .04)
    vertex_xyz = np.column_stack([r["section_vertex_xy_25833_m"] - np.array([589500., 5346800.]),
                                 np.interp(r["section_vertex_chainage_3035_m"], r["chainage_3035_m"], r["local_xyz_m"][:, 2])])
    curve("REFERENCE_OSM_174_control_vertices", vertex_xyz, ref, rawmat, .06)
    curve("DESIGN_Centreline_1501_editable_stations", designed, debug, yellow, 0)
    # Actual mesh centreline dashes (debug only, explicitly absent from FBX).
    dash_v, dash_f = [], []
    normals = geom.station_normals(designed)
    for i in range(0, len(s)-5, 20):
        q = designed[[i, i+4]].copy(); q[:, 2] += .045
        vv, ff = geom.ribbon(q, [-.07, .07]); dash_f.extend((ff + len(dash_v)).tolist()); dash_v.extend(vv.tolist())
    dash_v, dash_f = np.asarray(dash_v), np.asarray(dash_f)
    make_mesh("DEBUG_Centre_Dashes_NotMeasuredMarkings", dash_v, dash_f, dash_v[:, :2], debug, yellow)
    def label(name, text, point, size):
        data = bpy.data.curves.new(name, "FONT"); data.body = text; data.size = size
        data.align_x = "CENTER"; data.extrude = 0
        obj = bpy.data.objects.new(name, data); debug.objects.link(obj)
        obj.location = point; data.materials.append(white)
    for chain in range(1000, 2501, 100):
        i = int(np.abs(station-chain).argmin()); pos = designed[i].copy()
        pos[:2] += normals[i] * 10; pos[2] += 1.5
        label(f"DEBUG_Chainage_{chain}", f"{chain/1000:.1f} km", pos, 3)
    for i, text in [(0, "SECTION START 1.000 km\nTO MARSWIESE >"), (-1, "SECTION END 2.500 km\nCONTINUES TO MARSWIESE >")]:
        p = designed[i].copy(); p[:2] += normals[i] * 20; p[2] += 3
        label("DEBUG_" + ("START" if i == 0 else "END"), text, p, 4)
    # Explicit small direction arrows at both section boundaries.
    for i in (8, len(s)-12):
        p = designed[i] + [0, 0, .08]; direction = designed[i+1]-designed[i]; direction /= np.linalg.norm(direction)
        left = np.r_[normals[i], 0]
        xyz = np.array([p-direction*2+left, p+direction*2, p-direction*2-left])
        curve(f"DEBUG_Direction_Arrow_{i}", xyz, debug, yellow, .15)
    camera_collection = collections["CAMERAS_LIGHTS_NONEXPORT"]
    def camera(name, target, offset, scale):
        data = bpy.data.cameras.new(name); data.type = "ORTHO"; data.ortho_scale = scale
        data.clip_start = .1; data.clip_end = 3000
        obj = bpy.data.objects.new(name, data); camera_collection.objects.link(obj)
        obj.location = Vector(target) + Vector(offset)
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
        return obj
    target = np.array([(t["x_m"].min()+t["x_m"].max())/2, (t["y_m"].min()+t["y_m"].max())/2, 0])
    overview = camera("CAM_Overview", target, [100, -600, 1000], 900)
    detail_target = designed[np.abs(station-1717.7).argmin()]
    detail = camera("CAM_Hairpin_Detail", detail_target, [25, -65, 105], 125)
    lightdata = bpy.data.lights.new("Sun_Provisional_Daylight", "SUN"); lightdata.energy = 2.5; lightdata.angle = .15
    sun = bpy.data.objects.new(lightdata.name, lightdata); camera_collection.objects.link(sun)
    sun.rotation_euler = (.45, -.35, -.5)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.55, .65, .8, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .6
    scene.render.engine = "CYCLES"; scene.cycles.device = "CPU"; scene.cycles.samples = 8
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.camera = overview
    scene.render.resolution_x = 1280; scene.render.resolution_y = 1280
    scene["README"] = "OFFLINE VISUAL / FBX prototype, not playable AC. Open docs/validation/BLENDER_PROTOTYPE.md. Reference collection hidden: toggle to inspect original DTM and raw OSM. Debug labels/dashes are not exported. Width/camber provisional."
    scene["input_manifest_sha256"] = sha(MANIFEST)
    scene["coordinate_origin_ENH_m"] = [589500., 5346800., 300.]
    scene["section_chainage_EPSG3035_m"] = [1000., 2500.]
    text = bpy.data.texts.new("PROTOTYPE_README_AND_BUILD_REPORT.json")
    text.write(json.dumps(report, indent=2))
    fbx_module()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in exported: obj.select_set(True)
    bpy.context.view_layer.objects.active = exported[0]
    result = bpy.ops.export_scene.fbx(filepath=str(FBX), check_existing=True, use_selection=True,
                                    object_types={"MESH"}, global_scale=1, apply_unit_scale=True,
                                    apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y",
                                    bake_space_transform=False, use_mesh_modifiers=True, use_triangles=True,
                                    mesh_smooth_type="FACE", add_leaf_bones=False, bake_anim=False,
                                    path_mode="AUTO", embed_textures=False, use_custom_props=True)
    geom.require(result == {"FINISHED"}, "FBX export failed")
    with FBX.open("rb") as stream: header = stream.read(27)
    geom.require(header[:23] == b"Kaydara FBX Binary  \0\x1a\0", "Not binary FBX")
    report["export"].update({"header_hex": header.hex(), "file_version": struct.unpack("<I", header[23:27])[0],
                              "bytes": FBX.stat().st_size, "sha256": sha(FBX)})
    # Save exactly once, before render or reimport, preserving the editable scene.
    geom.require(not BLEND.exists(), "Refusing existing .blend")
    geom.require(bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), check_existing=True) == {"FINISHED"}, "Save failed")
    expected = scene_summary()
    geom.require(bpy.ops.wm.open_mainfile(filepath=str(BLEND), load_ui=False) == {"FINISHED"}, "Reload failed")
    actual = scene_summary()
    geom.require(actual == expected, "Saved .blend scene roundtrip differs")
    ref_obj = bpy.data.objects["REFERENCE_ORIGINAL_DTM_UNMODIFIED"]
    reference_xyz = np.empty(len(ref_obj.data.vertices)*3, np.float32)
    ref_obj.data.vertices.foreach_get("co", reference_xyz)
    max_ref_error = float(np.max(np.abs(reference_xyz.reshape(-1, 3)-raw_terrain)))
    geom.require(max_ref_error < .0005, "Original terrain changed beyond float32 storage")
    report["blend_reload"] = {"status": "PASS", **actual, "original_terrain_float32_max_error_m": max_ref_error,
                              "bytes": BLEND.stat().st_size, "sha256": sha(BLEND)}
    # Two real, modest CPU renders from the reloaded saved scene.
    scene = bpy.context.scene
    for name, camera_name, width, height in [("overview.png", "CAM_Overview", 1280, 1280),
                                              ("hairpin_detail.png", "CAM_Hairpin_Detail", 1280, 960)]:
        scene.camera = bpy.data.objects[camera_name]
        scene.render.resolution_x = width; scene.render.resolution_y = height
        scene.render.filepath = str(OUT/name)
        geom.require(bpy.ops.render.render(write_still=True) == {"FINISHED"}, f"Render failed: {name}")
    # Temporary in-memory FBX import: do not modify/re-save the source .blend.
    before = set(bpy.data.objects)
    geom.require(bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=False) == {"FINISHED"}, "FBX reimport failed")
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    geom.require(len(imported) == len(exported), "Reimport mesh count differs")
    import_checks = {}
    for obj in imported:
        # Import adds .001 suffixes in the still-loaded source scene.
        name = next((key for key in meshes if obj.name == key or obj.name.startswith(key + ".")), None)
        geom.require(name is not None and name not in import_checks, f"Unexpected reimport object: {obj.name}")
        coordinates = np.array([obj.matrix_world @ vertex.co for vertex in obj.data.vertices], dtype=float)
        faces = np.array([list(poly.vertices) for poly in obj.data.polygons])
        geom.require(faces.ndim == 2 and faces.shape[1] == 3, "FBX lost triangles")
        check = geom.mesh_checks(coordinates, faces)
        expected_check = report["topology"]["mesh_checks"][name]
        error = float(np.max(np.abs(np.array(check["bounds_m"])-np.array(expected_check["bounds_m"]))))
        geom.require(check["triangles"] == expected_check["triangles"] and
                     check["non_upward_triangles"] == 0 and check["degenerate_triangles"] == 0 and error < .002,
                     f"Reimport bounds/winding/count mismatch: {name}: {error}")
        import_checks[name] = {**check, "bounds_max_abs_error_m": error}
    report["fbx_reimport"] = {"status": "PASS", "checks": import_checks,
                              "note": "Blender importer only, world coordinates restored to original local Z-up frame; not ksEditor/Windows validation"}
    for obj in list(bpy.data.objects):
        if obj not in before: bpy.data.objects.remove(obj, do_unlink=True)
    report["runtime"] = {"blender": bpy.app.version_string, "python": sys.version, "numpy": np.__version__,
                         "render_engine": "Cycles CPU", "samples": 8, "render_size": [[1280,1280], [1280,960]]}
    report["renders"] = [str((OUT/name).relative_to(ROOT)) for name in ("overview.png", "hairpin_detail.png")]


def scene_summary():
    import bpy
    summary = {"objects": len(bpy.data.objects), "mesh_objects": 0, "meshes": {},
               "collections": {c.name: {"objects": len(c.objects), "hide_render": c.hide_render, "hide_viewport": c.hide_viewport} for c in bpy.data.collections}}
    for obj in bpy.data.objects:
        if obj.type != "MESH": continue
        summary["mesh_objects"] += 1
        v = np.empty(len(obj.data.vertices)*3, dtype=np.float32)
        obj.data.vertices.foreach_get("co", v)
        faces = np.array([list(p.vertices) for p in obj.data.polygons])
        geom.require(faces.ndim == 2 and faces.shape[1] == 3, f"Nontriangle saved mesh: {obj.name}")
        check = geom.mesh_checks(v.reshape(-1, 3), faces)
        geom.require(check["degenerate_triangles"] == 0 and check["non_upward_triangles"] == 0,
                     f"Saved mesh invalid: {obj.name}")
        summary["meshes"][obj.name] = check
    return summary


def main():
    start = time.monotonic()
    manifest, r, t = load_inputs()
    values = prepare_geometry(manifest, r, t)
    report = values[-1]
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    if "--check-only" in args:
        print(json.dumps(report, indent=2)); return
    for path in (OUT, BLEND, FBX):
        geom.require(not path.exists(), f"Refusing existing output (preserve/version explicitly): {path}")
    OUT.mkdir(parents=True, exist_ok=False)
    BLEND.parent.mkdir(parents=True, exist_ok=True); FBX.parent.mkdir(parents=True, exist_ok=True)
    save_audit(r, t, values)
    build_scene(manifest, r, t, values)
    report["elapsed_seconds"] = time.monotonic()-start
    report["build_script_sha256"] = sha(Path(__file__))
    report["geometry_helper_sha256"] = sha(Path(geom.__file__))
    with (OUT/"report.json").open("x") as stream:
        json.dump(report, stream, indent=2); stream.write("\n")
    print("PROTOTYPE_COMPLETE " + json.dumps({"blend": str(BLEND), "fbx": str(FBX), "report": str(OUT/"report.json"), "seconds": report["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
