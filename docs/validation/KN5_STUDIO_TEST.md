# KN5 Studio — approved installation and isolated export smoke test

## Actual result

**PASS for the tested headless export path, not independent/game acceptance.**
KN5 Studio **2.6.0** registered in a separate factory-startup **Blender 5.2.0 LTS**
(build `fbe6228777e7`, Python 3.13.13). Direct KN5 **v5** export completed, including
uint16 terrain splitting and embedded explicit DDS materials. The script took
**6.287 s**, process exit **0**, with **zero exporter/texture warnings**.

The same exporter library parsed the complete binary to EOF and reserialized it
byte-for-byte. This is **not an independent format validator**. No Windows,
ksEditor, Assetto Corsa, GUI, driving, physics, timing or VR test occurred.
No render/visual inspection is claimed. No source or installed third-party patch
was needed or applied.

## Acquisition, review and installation

- Repository: <https://github.com/FatihEsen/KN5Export>
- Exact commit: `f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9`.
- License: **CC0-1.0**, original `LICENSE` retained.
- Original archive: `tools/vendor/kn5_studio/f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9.zip`
  (**113,304 bytes**), SHA256
  `4881328ea759c729fe9c48945bce5f1de9ca4e4f95a535e7e69807dde5b5d5eb`.
- One HTTPS codeload request, HTTP 200; explicit **20,000,000-byte transfer cap**,
  **60 s** total / 15 s connect timeout, zero retries. No other acquisition or
  software/library/MCP installation. No operation approached 1 GB.
- All ZIP paths/modes inspected before extraction: no absolute/traversal paths,
  backslashes, colons, duplicate entries, symlinks or special files; expanded-size
  ceiling 100 MB. Actual expansion **417,417 bytes**, **23 files**.
- Original extracted tree:
  `tools/vendor/kn5_studio/source/KN5Export-f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9/`.
  All **13 top-level execution-relevant Python modules were read completely before
  import**. Registration adds classes, properties and menu callbacks; no runtime
  network client, updater, subprocess, timer or handler was found in that path.
  Developer PowerShell sync and upstream CI/tests were **not executed**.
- Copied the unchanged tree only after asserting the destination absent:
  `/home/haze/.var/app/org.blender.Blender/config/blender/5.2/extensions/user_default/kn5_studio/`
  (`/home/haze` resolves to `/var/home/haze`). Blender's actual
  `bpy.utils.user_resource('EXTENSIONS')` confirmed this extension root.
- Disk installation only: full package registration was tested in-process with
  `importlib`; **no persistent enable, repository/preferences edit or live enable**.
  Blender extension-manager/UI package validation and live enabling remain deferred.
- Provenance, safe archive inventory, review/hashes and installation receipt:
  `tools/vendor/kn5_studio/{download.log,provenance.json,archive_inventory.json,review.json,installation.json}`.

## New project outputs

| Path | Bytes / purpose |
|---|---|
| `scripts/export_kn5_prototype.py` | one-shot explicit-allowlist export, safety checks and report |
| `tests/test_export_kn5_prototype.py` | eight offline safety tests |
| `blender/northern_hairpins_kn5_v001.blend` | **10,127,639**, separate material-configured copy |
| `exports/kn5_prototype_v001/northern_hairpins_kn5_v001.kn5` | **8,190,802**, KN5 v5 |
| `exports/kn5_prototype_v001/kn5_{asphalt,gravel,terrain}.dds` | **192 each**, standalone copies of embedded DDS |
| `data/processed/kn5_test/report.json` | actual runtime, expected/source meshes, output nodes, bounds, UVs, normal/tangent diagnostics, shader/texture IDs, options and write audit |
| `data/processed/kn5_test/expected_geometry.npz` | original four meshes captured before export, independent-check handoff |
| `data/processed/kn5_test/verify_saved_copy.py` | read-only saved-copy comparison helper |
| `data/processed/kn5_test/saved_copy_reopen.{json,log}` | actual second fresh-process original/copy comparison |
| `data/processed/kn5_test/source_hashes_{before,after}.json` | **356** original project/config/extension files hashed; all unchanged |
| `data/processed/kn5_test/postflight.json` | output hashes, installed-file integrity, no `.blend1` backups |
| `data/processed/kn5_test/{blender.log,headless_exit.log,resource_probe.log,tests.log,no_overwrite.log}` | bounded actual execution evidence |

KN5 SHA256:
`8681e75aa707c359c3f340fd719db088b3c40aa47b2900b137c8d87b3bb7c37a`.
Configured `.blend` SHA256:
`09a94568007a070cd31767cbe08b93eea5471dcad4b10e424bb26f89fb1a24fc`.

## Tested commands and safety

From the project root, after the reviewed disk install:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/export_kn5_prototype.py --check-only
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python -m unittest discover -s tests -q

timeout --signal=TERM --kill-after=10s 240s flatpak run org.blender.Blender \
  --background --factory-startup --disable-autoexec --threads 8 \
  --python-exit-code 1 --python "$PWD/scripts/export_kn5_prototype.py" --

timeout --signal=TERM --kill-after=10s 240s flatpak run org.blender.Blender \
  --background --factory-startup --disable-autoexec --threads 8 \
  --python-exit-code 1 --python "$PWD/data/processed/kn5_test/verify_saved_copy.py"
```

Actual headless stdout/stderr was drained through a bounded logger retaining at
most **131,072 bytes**; export log **550 bytes**, copy-reopen log **890 bytes**,
neither truncated. Both headless processes exited **0**. Factory startup plus
`--disable-autoexec`, `load_ui=False`, `use_scripts=False` kept this isolated from
the user's running unsaved GUI. No bridge/MCP connection was made.

**99 project-local offline tests passed** (91 existing + eight new). These test
safety invariants, not independent KN5 semantics. Repeating the preflight after
success exited **1**, intentionally refusing the existing versioned directory
before importing Blender/exporter code. There is no force-overwrite switch;
choose separately reviewed new versioned paths for another export. The saved-copy
helper also refuses an existing evidence result.

The exporter uses `KN5Exporter` directly with `target_objects` set to the exact
four-name allowlist, v5, `EMBEDDED_DDS`, material autodetection **off**, wheel fixes
**off**, modifiers **off** (all four source objects have none). It bypasses the
operator's default skin-copy post-step entirely. No car auto-fix, skin/physics/
camera/light/config tool or file-copy function is called. Python audit hooks
block network/process launches and Python writes outside the two staging/evidence
directories. **Native Blender C IO is not covered by that audit**: its sole save
call explicitly names the fresh configured-copy `.blend`.

All 356 baseline files retained their byte lengths and SHA256, including original
prototype/FBX, terrain/route inputs, scripts/tests/docs, preferences and existing
extensions. Installed add-on files also remain byte-identical to the archive.
No preferences were saved; no existing assets/game files were written. Original
prototype SHA256 remains
`647f276be66a531acc812d6e5ffd986d040b979c3cf73d4ef9c92da3b4f2dec0`.

Actual saved-copy reopening verified all **32 objects**, mesh positions/topology,
UVs/smoothing, transforms and parents match the saved original. Only the four
object material assignments change. All three shader configurations and exact
packed DDS payloads persisted. Reference/debug objects remain in the authoring
copy but **not in the KN5**.

## Geometry, axes and splitting

Coordinates retain the original full-track origin E=589500, N=5346800, H=300 m;
authoring metres, X east / Y north / Z up. Export maps **(X,Y,Z) → (X,Z,−Y)**,
unit scale, UV **(u,v) → (u,1−v)**. No recentering, geometry smoothing or terrain
edit was performed in this task. Geographic/source accuracy caveats and the
artificial lowered terrain trench remain as in `BLENDER_PROTOTYPE.md`.

| Source / output mesh | Source vertices | KN5 vertices | Triangles | Material ID |
|---|---:|---:|---:|---:|
| `1ROAD` | 7,505 | 30,673 | 12,000 | 0 |
| `PROVISIONAL_SHOULDER_L` | 3,002 | 8,452 | 3,000 | 1 |
| `PROVISIONAL_SHOULDER_R` | 3,002 | 8,404 | 3,000 | 1 |
| `VISUAL_TERRAIN_DERIVED_LOWERED_SUB0` | terrain total 106,855 | **65,531** | **130,025** | 2 |
| `VISUAL_TERRAIN_DERIVED_LOWERED_SUB1` | shared source above | **41,627** | **82,375** | 2 |
| **Total** | **120,364** | **154,687** | **230,400** | |

Road/shoulder vertex expansion comes from corner normals/UV deduplication; terrain
chunks duplicate **303 boundary vertices**. Every chunk is ≤65,535 vertices;
maximum index is **65,530**, all indices in range. Triangle totals and per-source
union bounds match. No degenerate/non-upward triangles or nonfinite vertex fields
were found in the model or same-library parsed output. Normals/tangents are near
unit length; maximum absolute normal·tangent is **1.226e−7**. Complete per-chunk
bounds/UV/normal/tangent diagnostics are in `report.json`.

KN5-axis bounds (min → max), metres:

- Road: `(-3471.948486, -40.570229, -3310.474121)` →
  `(-3109.056152, 37.299305, -2839.169678)`.
- Left shoulder: `(-3465.950439, -40.570229, -3311.224121)` →
  `(-3108.306396, 37.299305, -2844.751465)`.
- Right shoulder: `(-3472.698242, -40.570229, -3304.474121)` →
  `(-3115.055420, 37.299305, -2838.472168)`.
- Terrain union: `(-3590, -89.117645, -3428)` → `(-2990, 61.899143, -2720)`.

Root dummy `northern_hairpins_kn5_v001` has four children: road, shoulders, terrain
wrapper. Terrain wrapper has the two `_SUB` mesh children. Both dummy transforms
are identity. Only these **two dummy/type-1 + five mesh/type-2 nodes** are expected;
no reference terrain, curves, debug dashes/text, cameras, lights or car dummies.
All output meshes: visible/renderable/cast-shadows true; transparent false;
layer 0; LOD in/out 0. These flags/names are **not a collision/physics acceptance**.

## Explicit materials and textures

Three new materials use the add-on's `Material.assettoCorsa` API, explicit
**`ksPerPixel`** shader (not a Principled-conversion assumption), opaque blend 0,
normal depth 0, alpha-test off. Each sets `ksAmbient=0.4`, `ksDiffuse=0.6`,
`ksSpecular=0.05`, `ksSpecularEXP=10`; slot **`txDiffuse`, slot ID 0**. Node sync
provides a corresponding Blender preview material. No name heuristics or white
fallback texture is used.

| Material ID / name | Texture ID / filename | Exact RGBA8 placeholder |
|---|---|---|
| 0 `KN5_Asphalt` | 0 `kn5_asphalt.dds` | (48,50,52,255), dark grey asphalt |
| 1 `KN5_Gravel` | 1 `kn5_gravel.dds` | (120,110,90,255), brown-grey gravel |
| 2 `KN5_Terrain` | 2 `kn5_terrain.dds` | (65,88,52,255), muted green terrain |

Each is an original generated **4×4**, uncompressed **B8G8R8A8 DDS**, one mip level,
128-byte header + 64-byte pixels, active=1. Payloads were checked byte-for-byte
against generated colors, embedded in KN5 and packed in the configured `.blend`.
These are meaningful export-test colors, **not finished measured/PBR surfaces**.

## Handoff for an independent Python check

Do not import the vendor writer/reader for an independent validation. Use the KN5,
`report.json` IDs/expected bounds, and `expected_geometry.npz` (SHA256
`65c5038dbde6fa4bcc8c179d65c2027f0632278d72fd772ec0e443b56a03c430`).
NPZ prefixes `mesh0`…`mesh3` follow the four allowlist rows in source order;
`*_vertices` are original float32 Blender XYZ, `*_triangles` int32 indices,
`*_corner_uv` float32 triangle×corner×2 UVs. Load with `allow_pickle=False`.
Compare triangle multisets after the documented axis conversion (cyclic index
rotation is allowed); totals/bounds alone cannot establish triangle equality.

Source-described binary fields for this v5 candidate, **not independently accepted
specification**:

- Little-endian. Magic **`sc6969`** (6 bytes), u32 version=5, i32 texture count=3.
  Strings: u32 UTF-8 byte length + bytes.
- Each texture: i32 active=1, name string, u32 payload size, DDS bytes.
- i32 material count=3. Each material: name/shader strings, u8 blend, u8 alpha-test,
  u32 depth; u32 property count; each property is name + **10 float32** (A, B2,
  C3, D4). Then u32 texture mapping count; each mapping slot string, u32 slot ID,
  texture filename string.
- Recursive node header: u32 type, name string, u32 child count, u8 active.
  Type 1 payload: **16 float32**, column-major matrix. Type 2 payload: three u8
  flags (cast-shadows, visible, transparent), u32 vertex count, vertices at
  **44 bytes** each (position3, normal3, UV2, tangent3 float32), u32 index count,
  uint16 indices; u32 material ID, u32 layer; float32 LOD in/out, sphere center3,
  sphere radius; u8 renderable. Children follow each payload.
- Expect exact EOF, no type 3/skinning, valid texture/material references,
  uint16-safe chunk counts, finite fields, winding, tangent/normal quality, UVs,
  source triangle equality and the explicit allowlist only.

## Remaining issues / acceptance boundary

No blocking export compatibility bug or examined structural invariant failure
occurred. Same-library checks cannot establish AC's interpretation of axes,
front-face/culling, materials, collision names, LOD flags or loadability.
Independent parsing/source-geometry comparison and actual Windows game inspection
are still required. This is not an installable track package: surfaces/session/
spawn/timing setup is absent.

Source-review risks remain outside the tested path: vertex deduplication omits
tangents, evaluated-mesh cleanup uses the original object, and the Blender KN5
importer uses legacy `Material.blend_method` and reverses winding. This smoke test
uses no modifiers, a basic diffuse shader and **binary-only** roundtrip, not that
Blender scene importer. Do not silently patch the installed third-party package;
preserve evidence and propose a reviewed/versioned patch if a later test blocks.
