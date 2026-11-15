# AC local solo test scene v001 — offline handoff

## Result / boundaries

**Actual factory-headless Blender export and saved-copy reload PASS.** Blender
5.2.0 LTS (`fbe6228777e7`), reviewed KN5 Studio 2.6.0 at pinned commit
`f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9`; unchanged installed/source/archive
hashes checked before and after. Successful headless process exited **0**;
script runtime **10.819 s**, no exporter warnings. No packages, acquisition,
network, installation, game writes/launch, live GUI, bridge or preference edits.
No render or visual inspection in this task. This is **not an installed or
runtime-accepted track**, and no timing support is promised.

Only the **1000–2500 m original EPSG:3035-chainage northern prototype** is used
(1495.738982 m designed XY length). Agreed full-route Königstetten/Marswiese
endpoints and scope are unchanged; this is not the complete route.

## Artifacts

- Builder: `scripts/build_ac_test_scene.py`.
- Offline helper tests: `tests/test_build_ac_test_scene.py`.
- Fresh saved scene: `blender/northern_hairpins_ac_test_v001.blend`
  (10,130,110 bytes; SHA256
  `16b199c25d50c4c9d9dd2d308575ab0b53752ffac40bf9cad0ef2202057a991e`).
- KN5 v5: `exports/ac_test_v001/exelberg_north_proto_v001.kn5`
  (8,191,169 bytes; SHA256
  `31ba7498ce7681aa4b2fed23d6ea96d368e31b5d9510dd33ff596e13a5ce9f1d`).
- Explicit standalone/embedded DDS: `exports/ac_test_v001/kn5_asphalt.dds`,
  `kn5_gravel.dds`, `kn5_terrain.dds` (192 bytes each). Original packed 4×4
  placeholders/material bindings retained; opaque `ksPerPixel`, not final art.
- Packaging contract: **`data/processed/ac_test_scene/manifest.json`**. Includes
  output/input hashes, original-to-renamed mapping, expected-geometry NPZ path/hash,
  Blender matrices, independently expected KN5 matrices, parsed actual matrices,
  grades/stations/clearances, explicit surface keys, flags and assumptions.
- Execution/check evidence under `data/processed/ac_test_scene/`:
  `blender.log`, `headless_exit.json`, `independent_validation.json`, `tests.log`,
  `no_overwrite.log`, `postflight.json`, `.build_started` one-shot reservation.

Python packager should consume **only the KN5 and the three explicit DDS files
listed in the manifest**, not recursively copy the export directory. Root dummy
and intended package track ID are **`exelberg_north_proto_v001`**. No package,
models.ini, surfaces.ini, CSP, AI, UI, cameras or game installation was created by
this task. Scene cameras/debug/reference objects remain authoring-only.

## Unchanged geometry / intended collision naming

| Configured-source object | Export name / chunks | Proposed explicit KEY | Assumed friction | Valid track |
|---|---|---|---:|---:|
| `1ROAD` | `1ROAD` | ROAD | 1.00 | 1 |
| `PROVISIONAL_SHOULDER_L` | `1GRAVEL_L` | GRAVEL | 0.70 | 0 |
| `PROVISIONAL_SHOULDER_R` | `1GRAVEL_R` | GRAVEL | 0.70 | 0 |
| `VISUAL_TERRAIN_DERIVED_LOWERED` | `1GRASS_TERRAIN_SUB0`, `_SUB1` | GRASS | 0.60 | 0 |

Four intended Blender surface meshes become **five KN5 meshes**, 230,400 triangles;
terrain's identity wrapper is `1GRASS_TERRAIN`. Both automatic chunks keep the
**1** collision-intended prefix. There is no separate physical-toggle field in
this exporter layout: naming and explicit surfaces.ini keys are the physics
handoff, not verified collision. All meshes active/visible/renderable/cast-shadows,
opaque, layer 0. No debug/reference mesh exported. The complete KN5 graph has
**12 nodes**: five meshes, two identity container dummies, five helper dummies.

Friction, 6 m road width, 0.75 m shoulders, zero camber/crossfall and valid-track
values are **provisional/unmeasured**. Explicit `KEY=GRAVEL` is required, not
inferred/default grip; likewise ROAD and GRASS. Proposed pitlane flag is 0 for
all keys: pit spawn is on the existing road, not an invented pitlane. Initial
zero roughness/vibration/damping is an assumption, not asphalt survey data.

Original scene limitations remain: smoothed OSM/BEV bare-earth-derived road,
not surveyed asphalt or imagery-approved alignment. The unchanged terrain was
artificially lowered at least 0.25 m under the ribbon, maximum 3.243515 m. Making
it collision-intended does **not** repair the trench, create joined verges or
prove shoulders/terrain transitions safe. No staging, barriers, extra pavement
or extended run-out was invented. Preserve BEV CC BY 4.0 / OSM ODbL attribution
and provenance from the prototype report when packaging.

LOD_IN=LOD_OUT=0 is deliberately retained. Hundreds of stock renderable meshes
provide zero/zero evidence; this is **not** a proven visibility defect or proof
of the new scene's engine visibility. See [stock conventions](AC_TRACK_CONVENTIONS.md).

## Coordinates / spawn and timing handoff

Metres, scale 1; EPSG:25833, full-track origin E=589500 / N=5346800 / H=300 m.
Product-documented EPSG:9274 heights, no new datum transform. Blender X east,
Y north, Z up → KN5 **(X,Z,−Y)**; UV → (u,1−v). KN5 serialized rows 0/1/2
are local axes in world coordinates, translation is indices 12–14;
`world = local * parent_world`. All helpers are direct root-child **kind-1
empties**, no duplicate helper geometry.

`AC_PIT_0`, `AC_START_0`, `AC_HOTLAP_START_0` are intentionally coincident for
**solo only**, 25 m designed XY arclength after section start, original chainage
1025.031497 m. Position:

- Blender `(-3344.782408, 3257.174627, -39.020227)`.
- KN5 `(-3344.782408, -39.020227, -3257.174627)` expected.
- Surface Z `-39.420227`; provisional clearance **+0.4 m**; grade **+4.730025%**.

Orientation is **flat yaw**, not slope-aligned: Blender +Y forward/+Z up maps to
KN5 −Z forward/+Y up. Expected KN5 axes are approximately
X=(0.867347,0,0.497704), Y=(0,1,0), Z=(−0.497704,0,0.867347).
Independent expected bases are built from route vectors, not copied exporter
Euler/conversion results. Parsed actual axes agree within **2e−6**; translations
within **0.0003 m** (observed maximum 0.000092593 m over all helpers).

A reference ±3 m longitudinal / ±1 m lateral envelope has 22 m road before its
rear and 2 m lateral margin. Flat pivot-to-surface clearance at its longitudinal
ends is approximately 0.540459 / 0.256286 m. This is a static reference envelope,
**not actual car underbody/suspension clearance**. Confirm settling, nose/tail
clearance and direction with the chosen car in Windows.

Trento-style point-to-point fixture **`AC_TIME_0_L/R` only**, at designed station
1480.738982 m, original chainage 2485.007070 m: **15 m before section end**,
6 m across actual interpolated road edges. Both use provisional +0.4 m clearance:

| Helper | Blender XYZ | KN5 XYZ expected |
|---|---|---|
| `AC_TIME_0_L` | (−3348.206871,2850.253511,36.966874) | (−3348.206871,36.966874,−2850.253511) |
| `AC_TIME_0_R` | (−3350.413786,2844.674126,36.966874) | (−3350.413786,36.966874,−2844.674126) |

Timing axes deliberately reproduce observed Trento TIME_0 axes:
X=(1,0,0), Y=(0,0,−1), Z=(0,1,0), **not spawn-style +Y-up**.
Endpoint-pair semantics/orientation significance remain uncertain. No TIME_1/2,
sectors or unsupported circuit/timer assumptions were added. **15 m run-out
fits a car but is not high-speed braking distance or safe stopping certification.**

## Validation and reproduction

Actual successful command (separate process; not the user's GUI):

```sh
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF \
 timeout --signal=TERM --kill-after=10s 240s flatpak run org.blender.Blender \
 --background --factory-startup --disable-autoexec --threads 8 \
 --python-exit-code 1 --python "$PWD/scripts/build_ac_test_scene.py" --
```

Bounded captured log: 515 bytes, 131,072-byte cap, untruncated. Explicit
`target_objects` comprises four surfaces + five helpers; modifiers, material
autodetection and wheel fixes disabled. Core exporter API avoids operator
skin/config-copy poststeps. Python audit blocks network/processes and writes
outside owned export/evidence roots; native Blender C IO is outside that audit,
with its sole save explicitly naming the fresh .blend copy. No preferences saved.

- Independent binary parser (`scripts/validate_kn5.py:parse`, **not** its old
  hardcoded `validate_candidate`) consumed exact EOF and checked new allowlists,
  hierarchy, flags, three DDS payloads/shaders, indices and upward winding.
- XYZ/normal/UV/index streams are **bit-exact against prior KN5**; original
  expected-geometry NPZ gives exact oriented XYZ/corner-UV triangle multisets.
- Recomputed terrain tangents differ by at most **1.7881393e−7**, bounded ≤2e−7;
  unit/orthogonality checks pass. Road/shoulder tangent streams remain exact.
- Actual saved-copy reload in the same isolated process checked all **six mesh
  fingerprints** (including nonexport references), 37 objects, helper transforms,
  material assignments and texture bindings. No .blend backups generated.
- **418** protected files' hashes unchanged, including original/configured scenes,
  old exports, source inputs, preferences and installed extension files.
- **146 offline tests pass**, including 11 new station/grade/interpolation,
  independent basis, Trento timing-axis and surface-allowlist tests. A printed
  argparse refusal in tests.log is an expected existing negative test.
- Post-build no-overwrite preflight exits **1 intentionally**, before asset writes.

First attempt stopped **before .blend save** on over-strict terrain tangent
bit-equality. Its KN5/DDS and failure logs are preserved separately under
`exports/ac_test_v001/failed_attempt_001/` and
`data/processed/ac_test_scene/failed_attempt_001/`. Only this named task-local
archive is accepted when preflighting otherwise unused output directories;
existing root artifacts/reservation/saved copy always block reruns. There is no
force-overwrite switch. Use reviewed new version paths for another build.

Repeatable read-only checks:

```sh
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python \
 scripts/build_ac_test_scene.py --validate-only
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python \
 -m unittest discover -s tests -q
```

## Still missing

Coordinator/Python packager must assemble and statically check local package
configuration from the manifest. Subsequent **explicitly authorized Windows AC**
test must establish loading, materials/LOD/culling, spawn direction/settling,
road/shoulder/terrain collision and grip, invalid-track behavior, reset/restart,
supported solo/A2B session and timer/result workflow. No CSP or AI path is added
or assumed necessary yet. GUI visuals, full-route driving, performance and VR
remain untested. No claim of a playable/timed milestone completion.
