# Installed AC Tools 0.1.6 — read-only readiness assessment

Assessment date: 2026-10-25 (environment UTC clock).

## Verdict

**This installed extension does not replace ksEditor.** It provides Blender track-authoring helpers and a wrapper around Blender's **FBX exporter**, explicitly labelled **“Export FBX for KsEditor”**. There is **no KN5 writer, KN5 export operator, or external FBX→KN5 converter invocation** in the inspected package. Existing `.kn5` files are referenced only for naming/moving them.

For this project, retain a separately validated FBX→KN5/material-conversion stage (currently planned on Windows using ksEditor). AC Tools does not remove that blocker. This conclusion applies to the installed **0.1.6** source, not every similarly named tool or future release.

## Evidence and inspection boundary

Installed source root, abbreviated **`A/`** below:

```text
/var/home/haze/.var/app/org.blender.Blender/config/blender/5.2/extensions/blender_org/ac_tools/
```

Read completely: all nine Python source files (`__init__.py`, `auto_load.py`, `Functions.py`, `Properties.py`, `Project_Setup.py`, `Project_Export.py`, `Tools_Objects.py`, `Tools_Materials.py`, `UI_Sidebar.py`), `blender_manifest.toml`, the entire two-line `README.md`, and all five templates. The remaining non-cache file is the GPL `LICENSE`; no bundled converter executable, library, wheel, shader library, or additional usage documentation was present. No symlinks were found. Existing `__pycache__` files were not executed or treated as authoritative source.

- Manifest: `id="ac_tools"`, version `0.1.6`, minimum Blender `4.2.0`; no active maximum-version/platform restriction. Permission: `files = "Import/export FBX from/to disk, Manage track folders"`. This declaration is not proof of an FBX importer: no import operator is implemented in the inspected Python.
- `flatpak info org.blender.Blender` confirmed the installed system Flatpak, x86_64 stable, version **5.2**. No PATH `blender` executable was found. Existing project evidence of actual Blender 5.2.0 LTS execution is recorded separately in [BLENDER_READINESS.md](BLENDER_READINESS.md) and [BLENDER_PROTOTYPE.md](BLENDER_PROTOTYPE.md); those tests did **not** validate AC Tools.
- Static validation performed here: all nine Python files passed AST parsing and in-memory compilation; TOML and UI JSON parsed; all four INI templates parsed with standard-library `ConfigParser`. Operator IDs, call sites, converter-related strings, and the complete non-cache file inventory were inspected. These checks do not establish Blender API/runtime compatibility.
- **No Blender launch, add-on import/registration, exporter/converter execution, installation, download, preference change, GUI interaction, game write, or `.blend` write occurred.** Static inspection answered the export question; a throwaway Blender import was unnecessary. The only project output of this assessment is this report.

Reproducibility anchors (SHA256 of installed bytes):

| Source | SHA256 |
| --- | --- |
| `A/blender_manifest.toml` | `23bbaa17c5e3603c68d1e8c574f302ffc04b1bffd014a7d519761d74ee2fb549` |
| `A/Project_Export.py` | `b10a4c64d5ec47bde27bf2ba017f26305ae9b7b42cf3e99fe7a02d24c54cd3a7` |
| `A/Functions.py` | `325a8fc498c0851ea373eef42c17a6e25bd0583c62a9af1f9421e5848cb85cb3` |
| `A/Tools_Materials.py` | `0e49177c8f4e65ccd2e35edaf1689980a473158eb6b13a0f41fa91a9015c6d49` |

## Export and converter capabilities

### Actual export path

`A/Project_Export.py:9–67`, `PROJECT_OT_export_fbx_for_ac.execute` (`project.export_fbx_for_ac`), calls **only** `bpy.ops.export_scene.fbx(...)`. `A/UI_Sidebar.py:125–147`, `UI_ProjectExport.draw`, presents “Scene to FBX” and “Export FBX for KsEditor”.

The wrapper exports next to the saved `.blend`, **not** into `track_folder` or the project's `exports/` directory:

- Whole scene: `<blend-stem>.fbx`.
- One selected object: `<active-object-name>.fbx`.
- Multiple selected objects: `<blend-stem>_objects.fbx`.
- Selection-only defaults **off** (`A/Properties.py:23–64`, `MyProperties`). No explicit export-collection allowlist is implemented.

Explicit FBX arguments are `check_existing=False`, `global_scale=0.01`, `apply_unit_scale=True`, `apply_scale_options='FBX_SCALE_ALL'`, `object_types={'EMPTY','MESH','OTHER'}`, forward `-Z`, up `Y`, tangent space, mesh/render modifiers, triangulation, smoothing `OFF`, vertex colours `SRGB`, and the selection toggle. Other FBX options inherit Blender defaults; no material/shader conversion follows the call.

**Do not assume these scale settings are suitable for our existing scene.** Its verified Blender roundtrip used `global_scale=1` and `FBX_SCALE_UNITS`, with an explicit four-mesh selection and other controlled options ([prototype evidence](BLENDER_PROTOTYPE.md)). AC Tools' preset differs; neither preset has yet been accepted by Windows ksEditor/game tests. No conversion or scale experiment was performed here.

### Checks are narrow, not game validation

`A/Project_Export.py:72–118`, `ready_for_export` / `ac_objects_valid`, requires a direct top-level view-layer `AC_OBJECTS` collection, at least one name with each configured START/HOTLAP/PIT/TIME prefix, an even total count of timing-prefixed objects, and pit count matching `int(ui_track.json['pitboxes'])`. It checks that collection's direct objects, not just the actual selected export set.

It does **not** validate timing-pair identifiers/placement, spawn orientation, point-to-point sessions, collisions, road geometry, UVs, shader/texture assignments, export scale, or complete game packaging. Checks can be disabled. Rejected checks return `{'FINISHED'}` after an informational report, so operator completion alone would not prove an FBX was written. The initial UI template's `"pitboxes": "<number>"` cannot pass the integer check unchanged.

### KN5 and external executables

- `A/Functions.py:126–157`, `TrackFolder.get_track_file` / `rename`, constructs an expected `<track-name>.kn5` path and moves that **existing** file. It neither reads nor writes KN5 binary content.
- `subprocess as sp` is imported in `Project_Export.py`, `Project_Setup.py`, and `Tools_Materials.py`, but there are **no subprocess calls**, converter command lines, executable settings, Wine/Proton integration, or ksEditor launch path in the package.
- `A/Project_Setup.py:11` merely contains a TODO about adjusting `KsEditor.ini`; no implementation exists.

Absence of a bundled/invoked converter does not inventory whether ksEditor or some unrelated converter is installed elsewhere on the machine. No such external tool was sought or executed for this task.

## Materials, shaders, and scene helpers

**“AC Materials” means surface physics and object-name prefixes here, not ksEditor shaders.**

- `A/Tools_Materials.py:8–14`, `DEFAULT_MATERIALS`, defines `1ROAD`, `1KERB`, `1GRASS`, `1SAND`, `1WALL`. `rename_objects` (`367–380`) prepends the chosen prefix to object names; it does not assign Blender materials or Kunos shaders. `remove_prefix` (`383–396`) removes a recognised prefix and returns after the first matching object.
- `AddMaterial.execute` (`17–199`) reads and **rewrites** the located `surfaces.ini`, adding physical parameters such as friction, damping, pitlane/valid-track flags, vibration, and sine bumps. `get_surface_names`, `load_materials`, and `create_material_operator` (`288–362`) derive further naming operators from surface keys. These are not visual shader slots.
- No code configures `ksPerPixel`, shader parameters, texture slots, alpha modes, shader persistence files, or Blender→Kunos node translation. Existing Principled materials therefore still need a separately tested conversion/mapping workflow.
- `A/Tools_Objects.py:14–135` creates small triangular mesh markers for `AC_START_n`, `AC_HOTLAP_START_n`, `AC_PIT_n`, and `AC_TIME_n_L/R`. `setup_ac_object` (`161–174`) rotates them 90° about X and links them into `AC_OBJECTS`. `set_default_material` (`138–158`) makes/reuses a red Principled `AC_OBJECT` display material, not a game shader.
- `get_track_middle_point` (`177–216`) supports cursor placement when alignment is off. The alignment-on branch is unfinished and returns `None`; its UI toggle is commented out. Generic markers do not establish a working Königstetten→Marswiese timed run.
- `A/__init__.py:20–39` runs module discovery on import and registers a delayed `load_materials(context)` timer when enabled. `A/auto_load.py` imports package modules and registers classes; `A/Properties.py:67–71` adds/removes a scene pointer property. Registration is therefore not a purely passive inspection operation. No registration was performed.

## Linux readiness and track-folder safety

**Manifest availability on Linux is not end-to-end Linux compatibility.** Static defects/risks:

| Area | Source and concrete consequence |
| --- | --- |
| Open folder | `A/Project_Setup.py:46–62`, `PROJECT_OT_open_track_folder.execute`, and `A/Functions.py:69–74`, `open_folder`, call Windows-only `os.startfile` without a Linux alternative. These calls cannot work on normal Linux Python as written. |
| Stored path | `A/Functions.py:100–104`, `TrackFolder.set_path`, appends a literal backslash to a Blender-relative path. On Linux it is a filename character, not a separator; the saved property can point somewhere other than the actual newly created directory. |
| Rename path | `A/Functions.py:129–157`, `TrackFolder.rename`, also appends a literal backslash to the destination folder name. No input validation, collision preflight, backup, or transactional rollback protects the two `shutil.move` operations. |
| Existing-folder initialization | `A/Project_Setup.py:14–42,153–188`, `PROJECT_OT_init.execute` and `make_*_folder`, only guard directory creation. They **unconditionally rewrite** existing `ui/ui_track.json`, `data/surfaces.ini`, and `extension/ext_config.ini` from templates through `write_json`/`write_config` (`A/Functions.py:11–35`, mode `w`). Re-running initialization can destroy customization. |
| FBX overwrite | `PROJECT_OT_export_fbx_for_ac.execute` uses a deterministic adjacent output path with `check_existing=False`, no backup/refusal check, and no output-path dialog. An existing matching FBX is at risk. The UI asks for a saved `.blend`, but the operator itself has no equivalent guard. |
| File search / edits | `TrackFolder.get_ac_file_path` (`A/Functions.py:110–123`) recursively returns the first basename match. Multi-layout/nested tracks can therefore resolve the wrong file. “Add Material” rewrites that result, and editors open it in Blender's Scripting workspace. |
| Arbitrary track target | `track_folder` is user-selectable; no staging-only restriction or check against game/source directories exists. Rename moves the selected folder and expected existing KN5 in place. There is no demonstrated separate game-deployment or rollback mechanism. |

`project.create_file` (`A/Project_Setup.py:82–113`) uses exclusive mode `x`, so it does not overwrite an existing file, but creates an **empty** file rather than a populated template. This protection does not extend to initialization/config writes or export.

### Generated folder is a skeleton, not a playable package

Initialization creates `ui/`, empty `ai/`, `data/`, and `extension/`, with only three populated template files:

- `templates/ui_track.json`: placeholder location/length/pit count, `circuit` tag, clockwise run; not a configured point-to-point event.
- `templates/surfaces.ini`: only `PIT` and `OUT` surfaces. The default ROAD/KERB/GRASS/SAND/WALL naming buttons do not themselves populate corresponding physics definitions.
- `templates/ext_config.ini`: generic CSP include, lighting, Grass FX and Rain FX using visual material names such as `Grass`, `Asphalt`, `Kerb`, `Sand`. Nothing ensures those materials exist or match Blender/exported materials. This is not evidence of tested CSP, grass, or rain support.

`templates/map.ini` and `templates/drs_zones.ini` are bundled but not copied by initialization or otherwise used by the inspected code. No KN5, models/layout configuration, actual map/preview images, AI paths, or tested timing/session setup is produced. Renaming does not update references in models/layout/UI configuration.

## Project recommendation and remaining gates

1. Treat AC Tools as **optional authoring assistance**, not a replacement export backend. Do not run its setup/rename/export operators against current source assets or game folders.
2. Preserve the current `.blend`, FBX and coordinate evidence. Any future approved add-on trial should use separately versioned scene copies and an empty disposable staging directory; explicitly review Linux paths, selection, overwrite behaviour and scale first. A manually corrected folder property alone would not fix all Linux behaviours.
3. Inventory Windows AC/SDK/ksEditor availability and safely test a minimal FBX→KN5 conversion, metre scale/axes, shader/textures, collision naming and isolated installation. Then verify spawns and actual point-to-point timing in game. These remain **unperformed acceptance gates**, not capabilities established by this assessment.

No installations, patches, exporter tests, or workflow migrations are authorized or performed by this report.
