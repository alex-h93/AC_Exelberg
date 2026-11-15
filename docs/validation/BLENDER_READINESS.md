# Blender readiness — actual installed application check

Checked **2026-10-25, 14:29–14:31 +01:00** (host clock). Scope: installed Blender only; no track implementation, installations, downloads, persistent addon enabling, preferences/Flatpak override changes, or game-file access. Read `IMPLEMENTATION_PLAN.md`, `docs/STATUS.md`, and `docs/TOOL_INVENTORY.md` first.

## Verdict

**PASS for a first bounded Blender authoring session and basic FBX output.** Actual background Blender ran successfully, read project inputs through its existing sandbox permission, built a synthetic triangle, exported binary FBX, and saved/reloaded a temporary `.blend`. Both actual launches exited **0**; no probe checks failed.

**Not a Blender → ksEditor → KN5 → game acceptance.** No Windows, GUI, game, or VR tests occurred. An FBX header and successful export do not establish ksEditor compatibility, materials, transforms/scale, collision conventions, or game behavior. M3 remains open.

Earlier inventory/status statements that Blender was absent and no Blender execution had occurred are historical and superseded by this narrow check; those files were outside this task's write ownership.

## Installed tools and inspection commands

```sh
command -v flatpak
command -v blender
command -v timeout
flatpak info org.blender.Blender
flatpak info --show-permissions org.blender.Blender
```

Observed:

- `/usr/bin/flatpak`, `/usr/bin/timeout`; **no PATH `blender`** (not a blocker).
- Existing **system-installed** `org.blender.Blender/x86_64/stable`, metadata version `5.2`, Flathub; runtime `org.freedesktop.Platform/x86_64/25.08`.
- Application commit `f97247d9e87dca0bc28c6a01e51cd6425cf8b21c636d28514898b7315b21d521`, installed size 1.1 GB. Nothing installed or updated by this task.
- Existing filesystem permissions include `host`; no extra permission or override was needed or set. Project access was then tested inside Blender, not merely inferred from metadata.

## Reproducible actual Blender command

From the project root:

```sh
timeout --signal=TERM --kill-after=10s 120s \
  flatpak run org.blender.Blender \
  --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python "$PWD/scripts/check_blender_readiness.py" \
  > /tmp/exelberg-blender-readiness.log 2>&1
printf 'BLENDER_EXIT_CODE=%s\n' "$?"
```

This is a 120-second run limit with a further 10-second termination grace period. The final script was executed, not just syntax-checked. The first run also passed before adding the explicit JSON/NumPy mesh check and exporter module-path reporting. The log path is a disposable host log; the evidence below is retained here.

### Actual runtime output (final run)

```text
READINESS {"background": true, "binary": "/app/blender/blender", "build_branch": "blender-v5.2-release", "build_date": "2026-07-14", "build_hash": "fbe6228777e7", "build_platform": "Linux", "build_time": "01:32:04", "check": "runtime", "executable": "/app/blender/5.2/python/bin/python3.13", "python": "3.13.13 (main, Apr 25 2025, 12:39:20) [GCC 14.2.1 20250110 (Red Hat 14.2.1-11)]", "version": "5.2.0 LTS", "version_tuple": [5, 2, 0]}
READINESS {"check": "project_access", "elevation_samples": 1524, "note": "TIFF readability/header only, not raster decoding or scene import", "root": "/var/home/haze/dev/Assetto_Exelberg", "route_points": 1145, "status": "PASS", "terrain_bytes": 45790016, "terrain_header_hex": "49492a00080000001300000104000100"}
READINESS {"check": "numpy", "module": "/app/blender/5.2/python/lib/python3.13/site-packages/numpy/__init__.py", "status": "PASS", "version": "2.3.4"}
READINESS {"available": {"export_scene.fbx": true, "export_scene.gltf": true, "wm.obj_export": true, "wm.ply_export": true, "wm.stl_export": true}, "check": "export_operators_initial"}
READINESS {"available": {"export_scene.fbx": true, "export_scene.gltf": true, "wm.obj_export": true, "wm.ply_export": true, "wm.stl_export": true}, "check": "export_operators_final", "fbx_module": "/app/blender/5.2/scripts/addons_core/io_scene_fbx/__init__.py"}
READINESS {"check": "native_mesh_from_json_numpy", "status": "PASS", "triangles": 1, "vertices": 3}

FBX export starting... '/tmp/exelberg-blender-readiness-fw0l838v/triangle.fbx'
export finished in 0.0018 sec.
READINESS {"bytes": 11148, "check": "fbx_export", "file_version": 7400, "header_hex": "4b617964617261204642582042696e6172792020001a00e81c0000", "status": "PASS"}
00:01.569  blend            | Read blend: "/tmp/exelberg-blender-readiness-fw0l838v/triangle.blend"
Info: Saved as "triangle.blend"
READINESS {"bytes": 94286, "check": "blend_roundtrip", "status": "PASS"}
READINESS {"check": "temporary_cleanup", "directory_removed": true, "status": "PASS"}
READINESS {"check": "summary", "failures": [], "status": "PASS"}
Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:32:04)

Blender quit
```

Host wrapper output:

```text
BLENDER_EXIT_CODE=0
SOURCE_CHECKSUMS_UNCHANGED=PASS
```

### What these checks establish

- `bpy.app` reports **Blender 5.2.0 LTS**, build **fbe6228777e7**, not merely Flatpak's metadata label. Embedded Python is **3.13.13**, distinct from the project's host Python/`.venv`.
- Blender's bundled **NumPy 2.3.4** imported and performed a finite-array check. No packages from the project `.venv` were injected or installed into Blender.
- Sandbox read/parse succeeded for `data/processed/route.geojson` (1,145 route positions), `route_elevation.csv` (1,524 terrain-height samples), and `elevation_summary.json`. Opening the **45,790,016-byte** `terrain_corridor_3035.tif` and checking its TIFF signature succeeded. **No GeoTIFF pixel decoding or real terrain import was attempted.**
- Factory startup already registered `export_scene.fbx`; shipped implementation is `addons_core/io_scene_fbx`. No registration/enabling was necessary. The script contains an in-memory shipped-module registration fallback, but that branch was **not exercised**. It never saves preferences or installs extensions.
- A one-metre synthetic triangle passed JSON → NumPy → `Mesh.from_pydata`; actual route/terrain geometry was never constructed. FBX export returned `FINISHED`, wrote **11,148 bytes**, and had the expected `Kaydara FBX Binary` header with file version **7400**. This is a minimal file/header check, not full FBX validation.
- A **94,286-byte** temporary `.blend` saved and reopened; its mesh still had three vertices and one triangle.
- TemporaryDirectory cleanup completed and was asserted. A host `find . -type f \( -name '*.blend' -o -name '*.fbx' -o -name '*.blend1' \) -print` returned no project files. No original assets were overwritten.
- Other actually registered operators: **glTF, OBJ, PLY, STL**. Their presence was queried, not an actual alternative export test, since FBX succeeded. No extension installation is needed for this check.

Before/after host `sha256sum` comparisons matched for the four inspected project inputs:

```text
0832b0657a32ee17651fbf46f36d7acebd8bd561b2dd79c337a9750745342601  data/processed/route.geojson
a8bc09bfdbd48533ab70f982285de4018a318bb45c6825c4950501b42ef7fe76  data/processed/route_elevation.csv
15b3961237a94acb1165d25b9a9865f04b513ad5978daf11c3ae666acd21e7b3  data/processed/elevation_summary.json
cbd1c8439b794ccff0075ea8efc5a9dfbece2cbf897004e9533db39a827986ee  data/processed/terrain_corridor_3035.tif
```

## What is actually needed next

### First bounded authoring — no additional software demonstrated necessary

- Existing Blender, bundled NumPy, Python/JSON, and native mesh creation suffice for a prepared-data authoring route. **A Blender GIS addon, QGIS, GDAL CLI, and embedded-Blender package installs are not prerequisites.** Process/reproject/decode rasters outside Blender using the existing project-local `.venv`; supply simple documented local-metre vertices/faces via JSON, Python, or NumPy arrays. This probe tested only the tiny synthetic JSON path, not a complete prepared terrain handoff.
- Still required **project work**, not missing tools: document EPSG:25833/local origin, axis mapping and height convention; prepare a bounded northern prototype's inputs and explicit nodata handling. Do not use the unresolved km 9.589 terrain dip as measured driving geometry. Those tasks were not implemented here.
- Interactive viewport/GUI/GPU usability remains untested; headless success does not prove visual authoring performance.

### Windows conversion and gameplay acceptance — availability unknown

- Access to the existing Windows Assetto Corsa environment and an approved cross-OS transfer destination/method.
- Verify **Assetto Corsa SDK / ksEditor** availability and version, then test this Blender version's FBX → material/shader setup → KN5 pipeline. These are required conversion/validation capabilities, **not confirmed missing installations**; Windows was not accessible and nothing was mounted.
- Verify game version and installed **CSP / Content Manager** status on Windows. Neither is established as a missing dependency or mandatory for the basic export test; choose additional requirements only from the tested workflow.
- Actual Windows load/drive/timing/material/scale tests remain required before declaring compatibility. Quest 2 validation is later and unperformed.

No software acquisition approval is needed merely to start using this already-installed Blender. If later testing identifies a genuinely missing non-Python tool, request approval before installation; do not infer that the roadmap or this readiness result authorizes it.
