# Full-length two-lane v002 — offline authoring/export validation

## Delivery and status

**A meaningful full-route base, not final realism or game acceptance.** Built offline
in the already installed Blender 5.2.0 LTS. No downloads, installs, live-GUI access,
preference saves, deployment or game launch. v001 and geographic source inputs are
unchanged. User feedback that v001 loaded, spawned backwards and allowed mountain
falls is the reason for the explicit heading reversal and temporary containment.

- Authoring scene: `blender/exelberg_full_v002.blend` — 45,226,411 bytes.
- KN5 v5: `exports/full_track_v002/exelberg_full_v002.kn5` — **232,993,555 bytes**.
- KN5 SHA256: `56230c52247bb989d80f9a1363a6fb26cbedb62e60d687e106c2068b372aaeba`.
- Packaging contract: **`data/processed/full_track_scene_v002/manifest.json`**.
  It records output paths/hashes, each source mesh and exported uint16 part,
  exact surface keys/flags, helper matrices, timing distances and runtime caveats.
- CPU previews: `data/processed/full_track_scene_v002/overview.png` and `driver.png`.
  Both are actual Cycles CPU renders, **1280×800, 8 samples**. Both were opened and
  visually reviewed: complete geographic extent; textured road/shoulders, white
  paint, opaque trees and deliberately conspicuous temporary walls at driver level.

The final factory-headless build/render/save/reload took **177.61 seconds**, under
an external **600-second timeout**. A further read-only saved-scene capture corrected
three warning-text expected-source records; it did not resave the scene or KN5.
Failed numerical/export attempts are preserved in this task's own `failed_*`
subdirectories. **Do not glob those archives into a package.** Use the manifest.

## Full route, coordinates and provisional design

Inputs are the verified route/lateral/terrain NPZs from `full_track_inputs` and the
**4,616-point `full_scenery_v003/forest_trees.npz`** actual OSM-mask selection.
Their manifests and upstream provenance hashes were checked. No synthetic unmasked
`full_track_inputs/trees.npz` distribution was used.

- Entire source interval: **0–15226.291863325048 m EPSG:3035**; native UTM source
  length **15226.670946413231 m**, Königstetten → Marswiese.
- Designed XY road length: **15212.525114314722 m**; designed 3D length:
  **15231.650464127053 m**. Smoothing shortens XY by 14.145832 m; neither source
  endpoint is moved or extended. Full source chainage remains in the audit.
- **8,156 driving stations**, native maximum step **1.999873448113 m**; two nominal
  **3 m lanes**, total **6 m**, **zero crossfall**. Shoulders: **0.75 m each**.
  OSM alignment, width, profile, paint, grip and camber are **not surveyed**.
- Origin **(589500,5346800,300) m**, EPSG:25833 horizontal / product-documented
  EPSG:9274 heights. Blender X east/Y north/Z up; KN5 **(X,Z,−Y)**, metres.
- Metric Gaussian smoothing: XY sigma 2 m, Z sigma 4 m, support 3 sigma, endpoints
  pinned. Maximum XY displacement **0.422561 m**. Smoothing-only Z delta:
  **−0.047743…+0.041264 m**, RMS **0.006689 m**; dip correction is separate.
- Designed grade range **−8.871028…+11.091770%**; maximum adjacent grade step
  **0.812685 percentage points**. **Zero road/shoulder quad folds and zero
  nonadjacent full-width road/shoulder overlaps**. No road segment was discarded.

`geometry_audit.npz` retains all raw/designed XYZ, source chainages, raw/derived
terrain, masks, exact per-node terrain deltas, clipped triangles/source-cell IDs and
shoulder seam records. Hidden raw/design editable centreline curves and embedded
contract text are included in the blend, but excluded from export.

## Explicit km 9.589 provisional profile bridge

The unresolved raw DTM dip is retained in the source. Only the designed road is
bridged over **inclusive EPSG:3035 window [9578,9602] m** using interpolation between
flanks, followed by the separately audited smoothing above. Flank local Z values:
**188.60910139814862 / 189.71635409971904 m** (add origin H=300 for product heights).

The exact native mask is **indices [5098,5099,5100,5101,5102,5103,5104,5105,5106,
5107,5108,5109]**. Round-trip numeric arrays are in `manifest.design.dip`; the table
is rounded for reading. Deltas are metres, positive upwards.

| Index | 3035 station m | Raw local Z m | Bridge-only delta m | Final delta m |
|---:|---:|---:|---:|---:|
|5098|9579.272824626|188.665894232|0.001929604|0.003651092|
|5099|9581.254881974|188.742385267|0.016881833|0.017493793|
|5100|9583.236939323|188.818416117|0.032294248|0.032475416|
|5101|9585.218996672|188.863399710|0.078753920|0.078795743|
|5102|9587.186932510|187.671357782|1.361587609|1.361595068|
|5103|9589.154868349|186.615692438|2.508044715|2.508050622|
|5104|9591.122804187|188.561625622|0.652903292|0.652951619|
|5105|9593.090740025|189.237717327|0.067603348|0.067847619|
|5106|9595.058675863|189.329332014|0.066780423|0.067681946|
|5107|9597.026611702|189.428769594|0.058134604|0.060809845|
|5108|9598.994547540|189.533640483|0.044055477|0.050681970|
|5109|9600.962483378|189.654107301|0.014380420|0.028397966|

At the minimum, source H **486.615692438 m** becomes designed H
**489.123743060 m**, a **+2.508050622 m** provisional change. This is **not a
surveyed culvert/bridge/asphalt elevation claim**. Gaussian support affects stations
outside the bridge mask too; full final deltas remain available for every station.

## Terrain joins, collision and temporary containment

Only the source **207,885 fully valid 8 m cells** are used; invalid cells/nodata
are never filled. The exact 7.5 m road-plus-shoulder footprint is clipped out of
terrain triangles and replaced by the designed surfaces, rather than lowering a
trench underneath them. Near-road terrain blends from shoulder height at 3.75 m
to **actual lateral ±8 m probes**, fading back to source grid height by 15 m.

- Source valid-cell area: **13,304,640 m²**; road-replaced area:
  **114,083.317359 m²**. All source cells are accounted for explicitly.
- **7,109 grid nodes modified**, signed deltas **−1.250752…+1.874708 m**;
  RMS across valid nodes **0.044853 m**. These are derived terrain works only.
- Float32 clipped-coordinate area delta: **+0.120728 m²**. Explicit numeric sliver
  omissions total **0.076693838 m²**, not missing road segments or silently dropped
  source cells. One bounded float32 topological repair removed **0.000001877546 m²**
  at source cell **799760**; exact coordinates/reason are in the terrain report.
  Sub-millimetre terrain residues are not a claim of globally surveyed watertightness.
- **16,312 road/shoulder station vertices shared exactly**, zero missing joins.
  **26,222 terrain/shoulder seam points**, maximum final float32 3D mismatch
  **0.000690534 m**, below the explicit **1 mm** check tolerance.
- Each source spatial collision chunk is a **closed, consistently outward-wound
  solid**, with positive volume and cancelling directed edge incidence. Exact
  exported triangle unions preserve closure across any uint16 split. Normal/UV
  splits in the vertex stream do not imply geometric cracks. The full **8.7 m
  outer barrier envelope** also has zero folds and nonadjacent overlaps.

Explicit keys and actual exported mesh counts:

| Key | Exported collision meshes | Provisional friction | Valid track / pitlane |
|---|---:|---:|---|
|ROAD|66|1.0|1 / 0|
|GRAVEL|131|0.7|0 / 0|
|GRASS|104|0.6|0 / 0|
|WALL|132|0.6|0 / 0|

All physical names begin `1<KEY>_`; terrain collides outside the road too. Paint,
forest and warning meshes are visual-only, never digit-prefixed collision objects.

**WALL is invented TEMPORARY safety geometry, not real roadside infrastructure.**
Continuous walls run along both sides of the full route, inner offsets ±4.05 m,
thickness 0.30 m, top 1.15 m above the road profile, base 0.15 m below it. They leave
the full 6 m road, both shoulders and another 0.30 m each side clear. Closed start
and finish endcaps prevent an endpoint drop. Safety stripes emphasize their status.
They are intended to contain ordinary driving departures, **not certified high-speed
containment or a fall-proof promise**. Low-speed collision tests remain required.

## Images, trees, visibility and cost

Seven own **256×256 opaque image textures** are embedded as DDS and supplied
standalone: asphalt, gravel, grass, bark, canopy, white paint and safety stripes.
All were generated offline and converted by the reviewed KN5 Studio DDS API;
no downloaded assets or flat 4-pixel v001 placeholder textures are used. Total
DDS payload **1,835,904 bytes**, below the aggregate 8 MiB budget. `ksPerPixel`
materials have explicit diffuse bindings and opaque flags.

White centre paint is **3 m dash / 9 m gap, 0.12 m wide**, with continuous white
edge lines. This is **clearly provisional, not measured existing paint**.

All **4,616 forest-mask anchors** get opaque low-poly broadleaf-style trunks and
crowns, **52 triangles/tree**, totaling **240,032 triangles**. Whole trees are
merged into **650 material/spatial meshes** on a 128 m cluster grid, finite
**LOD_OUT=900 m**. No per-tree objects/draw calls, field scattering, transparency,
wind or species/individual-tree survey claims. Roots are sampled on the **actual
visible derived triangulation**, not the raw DTM: all 4,616 are independently
rechecked. Grounding changes versus raw anchors range **−1.973284…+2.588663 m**,
RMS **0.232012 m**, recorded in `forest_grounding.npz`.

**Actual cost exceeds the ~500k–1M triangle aim:** **1,928,784 triangles**, including
**1,645,884 collision triangles**. Closed terrain undersides/skirts are the main
cost (terrain alone 1,161,356 triangles). The output contains **1,152 mesh nodes /
1,177 total nodes**, 4,988,521 exported shading/UV vertices, max **65,533 vertices
per mesh**, with exact triangle totals over uint16 splits. This is not yet a
performance-optimized or VR-approved track. File remains below the 256 MB cap.

## Spawn, finish and next packaging contract

**All three solo markers** (`AC_PIT_0`, `AC_START_0`, `AC_HOTLAP_START_0`) are at
**designed station 25 m**, **right lane (−1.5 m left-positive offset)**, **+0.4 m**
provisional pivot height. All yaw is reversed **180° relative to v001**. Blender
**−Y** now points along travel; actual exported **KN5 +Z** has dot product >0.99999
with travel for all three. This intentionally supersedes the old *static* −Z
inference using the user's *actual* backwards-spawn feedback. No new in-game
heading or settling test is claimed. Coincident markers are for solo use only.

The remote **AC_TIME_0_L/R-only Trento A2B fixture** retains its observed fixed axes.
Finish is at designed arclength **14912.525114 m**, **300 m before the source road
endpoint**, with **14887.525114 m** from the spawn to the gate. There is **299.55 m**
of usable runout to the near face of the closed endcap; no fictional road extension.
Visible **BRAKE / FINISH**, **BRAKE**, **STOP** warnings are at 300/150/60 m before
the road endpoint. These are unmeasured safety aids, not guarantees of stopping
from any speed. Manifest distinguishes full source extent, designed road length,
timed-course length, finish source chainage and runout. No circuit TIME_1/2 added.

A later Python package must use the exact manifest KN5 and surface/helper contract,
explicit KEY values, solo/A2B assumptions and existing attribution. **No installable
package or deployment is produced here.** Timer start/finish, selected session,
restart/reset-to-pits and repeated-run behavior require authorized AC tests.

## Exporter workaround and independent checks

Pinned KN5 Studio **2.6.0**, commit
`f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9`, remains unchanged in both vendor and
installed locations. No other addon copy or installed-source patch was created.
The reviewed core hierarchy/material/DDS/v5 writer is used, with all automatic
fix/detection/operator post-steps disabled and an exact object allowlist. Four
physical collections plus visual/helpers collections export; preview/reference
collections, cameras and lights do not.

`full_track_v002_export.py` is an explicit caller-only Blender 5.2 extraction
adapter: deprecated loop normals in the pinned path produced bad fallback normals
and nonorthogonal tangents. It reads actual corner normals / exact outward flat
normals and uses orthogonalized Mikk tangents; deterministic perpendicular fallbacks
are counted, not hidden. **10,246 fallback corners / 1,170,210 orthogonalized tangent
corners**, out of 5,786,352 total triangle corners. No positions, topology, UVs,
materials or flags are changed by the adapter. Physics grass/gravel/walls use flat
shading. Per-mesh adapter counts are in the manifest. Three visual warning meshes
have actual saved-scene source captures because pre-bake matrix prediction differed
by less than **0.000001 m**; the strict equality check was **not weakened**.

The independent non-vendor parser checks full EOF, indices, finite fields, unit
normals/orthogonal unit tangents, winding, bounds, DDS content, material bindings,
helper transforms, collision prefixes, surface keys, flags and exact **oriented
float32 XYZ+corner-UV triangle multisets for every source and split**. Source
collision solids and connection gaps are separately checked. `validate_kn5.py`
only gains **optional bounded limits**: defaults remain **32 MiB / 64 nodes**;
full candidate checks cap **256 MiB / 4096 nodes / 8 MiB texture payload**, without
disabling string/count/depth/index checks. Existing parser tests still pass.

**215 offline tests pass**, including every previous test and full-candidate
geometry/grounding/output-hash regressions. The `validate_kn5` refusal printed in
the suite is an expected negative test. **482 protected files**—raw/interim inputs,
previous scenes/exports, recorded installed v001 files and preference/addon files—
were SHA256 checked unchanged before/after. The optional parser edit is explicitly
authorized code, not presented as an unchanged geographic/game source.

Safe current checks:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/build_full_track_v002.py --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -q
```

Historical creation commands (fresh destinations only; **do not overwrite delivery**):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/build_full_track_v002.py --prepare
timeout --signal=TERM --kill-after=10s 600s flatpak run org.blender.Blender \
  --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 1 \
  --python "$PWD/scripts/build_full_track_v002.py" -- --build
# First independent evidence creation only; use --check for repeat validation.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/build_full_track_v002.py --validate
```

### Remaining acceptance checks

Authorized AC load, actual spawn/settling/reset, complete low-speed/full-route drive,
normal-speed barrier/shoulder/terrain collision and grip, finish/runout/braking,
A2B session/timer/restarts, in-engine textures/LOD/culling, performance and Quest 2
VR remain **unverified**. Sparse procedural forest and dominant temporary walls
are intentionally a full-length base, not final Exelberg scenery fidelity.

Terrain © BEV, CC BY 4.0; OSM © OpenStreetMap contributors, ODbL. Source accuracy,
dates, full imagery alignment and the dip's true physical explanation remain open.
