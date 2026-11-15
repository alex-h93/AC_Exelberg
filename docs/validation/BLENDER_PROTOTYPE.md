# First real northern hairpin Blender / FBX prototype

## Result and scope

**Actual offline Blender build completed**, using user-installed Flatpak Blender
**5.2.0 LTS**, embedded Python 3.13.13 and bundled NumPy 2.3.4. No project venv
packages were injected into Blender. No acquisition, installation, preference
changes, environment/graphics overrides, source-data edits or status edits.

This is an **editable visual/export prototype only**, not playable Assetto Corsa,
not timing-ready, and not surveyed asphalt geometry. The section is **1000–2500 m
EPSG:3035 chainage**, in the agreed Königstetten → Marswiese direction. Its labels
are original profile chainages, not distances measured along the smoothed road.
The unresolved km 9.589 terrain anomaly is outside the section, not corrected.

### Deliverables

- `blender/northern_hairpins_v001.blend` — 10,127,856 bytes.
- `exports/northern_hairpins_v001.fbx` — 5,111,580 bytes; binary FBX 7400.
- `data/processed/prototype_scene/overview.png` — actual saved-scene CPU render,
  1280 × 1280.
- `data/processed/prototype_scene/hairpin_detail.png` — actual saved-scene CPU
  render, 1280 × 960.
- `data/processed/prototype_scene/report.json` — build/runtime, geometry, input
  provenance, topology, save/reload and FBX reimport results.
- `data/processed/prototype_scene/geometry_audit.npz` — original, interpolated and
  designed coordinates, every XYZ delta, station parameters and terrain edits/masks.
- `data/processed/prototype_scene/stations.csv` — 1501 designed stations, original
  interpolated XYZ, designed XYZ, all deltas, grades/steps and design parameters.
- `data/processed/prototype_scene/raw_controls.csv` — all 837 original dense
  controls, raw grades/steps and design offsets evaluated at those controls.
- `data/processed/prototype_scene/postflight.json` — output hashes, no-overwrite
  check, raw-control displacement maxima and visual-review statement.
- `data/processed/prototype_scene/build.log`, `no_overwrite_check.log`,
  `tests.log` — actual execution evidence. End-of-array grades/steps without a next segment are CSV
  `nan`, not missing road-height samples.
- `scripts/build_blender_prototype.py`, `scripts/prototype_geometry.py`,
  `tests/test_prototype_geometry.py` — new builder, NumPy-only helpers and tests.

## Commands actually executed

From project root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/build_blender_prototype.py --check-only
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python -m unittest discover -s tests -q

timeout --signal=TERM --kill-after=10s 240s flatpak run org.blender.Blender \
  --background --factory-startup --disable-autoexec --threads 8 \
  --python-exit-code 1 --python "$PWD/scripts/build_blender_prototype.py"
```

Results: numerical preflight passed; **91 offline tests passed** (80 previous plus
11 new geometry tests). The real headless build exited **0**, reporting **15.27 s**
inside the script, with both renders, .blend reload and FBX reimport successful.
Cycles used **CPU**, eight samples and denoising. Blender emitted deprecation
warnings for `Material.use_nodes` / `World.use_nodes` (future Blender 6 API), not
build failures. No GUI, Windows, game or headset execution is implied.

Afterward, running the builder without `--check-only` in project Python exited
**1** with `Refusing existing output`; asset hashes remained identical. This is
an intentional safety pass, not a Blender failure. All output paths were absent
at the first build. The script refuses an existing report directory, .blend or
FBX; it has **no force-overwrite option**. Do not rerun destructively: first choose
new versioned paths in a reviewed script, or explicitly preserve/version the
existing outputs. `--check-only` is read-only and remains safe to repeat.

## Input integrity and coordinate frame

The builder validates manifest schema/version, coordinate contract and section,
then verifies byte lengths and SHA256 of **75 provenance files** and both NPZs
**before NPZ loading**. It uses `allow_pickle=False`, exact array-name/shape/dtype
checks, finite checks, bool masks, valid-count checks, strict four-corner cell
mask equality, local-coordinate/control checks, chainage order/endpoints and
≤2 m native route spacing before creating scene geometry. Invalid terrain values
are never interpreted as elevations; only fully valid cells become faces.

Input manifest SHA256:
`563f3cf324a8dee4b62e06adcb89a5076044d97da445c91164ce5009a1b58c05`.
See [PROTOTYPE_INPUTS.md](PROTOTYPE_INPUTS.md) and
[the coordinate contract](../decisions/COORDINATES.md).

The scene retains the **full-track** origin **E=589500, N=5346800, H=300 m**:
local X east, Y north, Z up, metres, EPSG:25833 horizontal and product-documented
EPSG:9274 orthometric heights. No prototype recentering, second origin subtraction,
vertical transformation, axis swap or authoring scale. Metric scene scale is 1.
Terrain © BEV, CC BY 4.0; route © OpenStreetMap contributors, ODbL. OSM alignment,
DTM/asphalt correspondence, source dates and independent height accuracy remain
unresolved. The BEV grid is not a road-width, roughness or banking survey.

## Deliberate road design and measured changes

Road **6.0 m** wide, flat crossfall/camber **0**, shoulders **0.75 m each side**.
These are **provisional design assumptions**, not measured widths/banking or
imagery-approved geometry. Left/right refer to the travel direction. Shoulders
share road-edge coordinates and Z; they are separate candidate meshes, not a
validated safe off-road driving surface. No invented staging, junctions, spawns,
barriers, buildings or survey features were added.

Raw OSM corners have heading jumps up to **27.418°**; raw DTM grades have adjacent
steps up to **3.070 percentage points**. For a first visual road, light smoothing
was considered necessary to regularize those discontinuities, not to claim a
real asphalt profile. The builder resamples native XY arclength at ≤1 m, applies
Gaussian XY σ=2 m and Z σ=3 m (±3σ support, linear end extension), and pins both
section endpoints. It does not change raw inputs or fit imagery. Sampling labels
remain interpolated original EPSG:3035 chainages.

| Quantity | Raw | Designed |
|---|---:|---:|
| XY length | 1499.989 m | 1495.739 m |
| 3D length | 1502.084 m | 1497.831 m |
| Local Z minimum / maximum | −40.570 / +37.299 m | same |
| Orthometric H minimum / maximum | 259.430 / 337.299 m | same |
| Grade minimum / maximum | 0.277 / 9.791% | 1.405 / 8.671% |
| Maximum adjacent grade step | 3.070 pp | 0.511 pp |
| Grade steps >1 pp (reporting threshold, not acceptance standard) | 56 | 0 |
| Maximum heading step | 27.418° | 8.039° |

At the 1501 uniform stations, XY displacement maximum **0.366005 m**, RMS
**0.067589 m**, mean **0.031641 m**; absolute Z change maximum **0.028487 m**,
RMS **0.004304 m**, signed range **−0.028487 to +0.016361 m**. At the **837 original
controls**, interpolating the designed alignment back to each original parameter
finds larger maxima: **0.418597 m XY** and **0.032260 m absolute Z**. These are
parameter-correspondence offsets, not geographic accuracy estimates. Both sets
are retained to avoid understating corner changes; every offset is auditable.
Length reduction is **4.250 m**. Residual heading/grade steps are reported rather
than declared physically acceptable; steering/suspension tests are still needed.

## Meshes, topology and terrain treatment

All exported surfaces have explicit upward triangles and useful UV layers. Road
has five lateral vertices per station, UV lateral/longitudinal in 6 m repeats;
shoulders share those repeats. Terrain uses local XY / 20 m UVs. Materials are
simple Principled asphalt, gravel and green-grey terrain, with no external
textures, measured road markings or ksEditor shader claims.

| Exported mesh | Vertices | Triangles |
|---|---:|---:|
| `1ROAD` | 7505 | 12000 |
| `PROVISIONAL_SHOULDER_L` | 3002 | 3000 |
| `PROVISIONAL_SHOULDER_R` | 3002 | 3000 |
| `VISUAL_TERRAIN_DERIVED_LOWERED` | 106855 | 212400 |
| **Total** | **120364** | **230400** |

Terrain is 355 × 301 at 2 m, with 106200 fully valid cells; no partial/no-data
cells are triangulated. Road local bounds are approximately
X **−3471.948…−3109.056**, Y **2839.170…3310.474**, Z **−40.570…37.299 m**.
Detailed per-object bounds/areas/counts are in `report.json`.

Checks found **zero degenerate triangles, zero negative/downward orientations,
zero folded/nonconvex full-width quads and zero self-overlap pairs**. Quad checks
include both diagonals. Strict-interior SAT tests every non-neighbour segment
quad across the full **7.5 m** road-plus-shoulders footprint. Raw full-width quads
also had no overlap. The closest designed nodes separated by >30 m source
arclength are **19.282 m** apart; subtracting two maximum station spacings gives
a conservative **17.282 m** nonlocal segment-distance bound. This is a geometric
proximity diagnostic, not survey evidence or independent clearance approval.

**Derived terrain cut/lower strategy:** for every valid grid cell whose XY AABB
intersects any full-width segment AABB, lower all four cell corners to at most
that segment's minimum Z minus **0.25 m**. Never raise terrain. AABB selection is
a conservative superset of actual intersections; bounding every cell corner
bounds both terrain triangles below the corresponding road/shoulder triangles.
The float64 conservative clearance check returned **0.25 m**. Mesh storage/export
has sub-millimetre numeric differences, not survey precision.

This touched **3879 cells**, lowered **4242 vertices**, with maximum lowering
**3.243515 m** and mean affected lowering **0.524747 m**. It intentionally creates
an artificial cut/trench, visible as an edge/shadow in the detail render; it is
**not** a reconstructed retaining wall, drainage system or joined physical verge.
There are no skirt meshes concealing intersections. More realistic terrain joins
and safe reachable shoulders require later design/reference work.

`REFERENCE_ORIGINAL_UNTOUCHED_NONEXPORT` contains a separate **212400-triangle
original DTM**, the 837-point raw OSM/DTM curve, and 174 original OSM control
vertices. It is hidden in viewport and render: toggle the collection to inspect.
Original DTM vertex coordinates survived reload with maximum **0.000003815 m**
float32 representation error; the source NPZ is unchanged. Original alignment can
be overlaid against the editable 1501-station design curve. Preserve both.

## Scene organization, renders and roundtrips

- Road-physics **candidate**, provisional shoulders and visual terrain are in
  three separate export collections. `1ROAD` is only a minimal mesh name, **not**
  evidence of verified Assetto Corsa collision/material configuration.
- `DEBUG_ALIGNMENT_MARKERS_NONEXPORT`: editable design curve, yellow dashed
  centre guide, 100 m chainage labels, direction arrows, section start/end labels.
  Dashes are debug geometry, **not observed road markings**; section end is not
  the full-route Marswiese finish. Debug objects are excluded from FBX selection.
- `CAMERAS_LIGHTS_NONEXPORT`: orthographic `CAM_Overview`,
  `CAM_Hairpin_Detail`, and sun. Saved scene opens on the overview camera.

The .blend was saved once, then **actually reopened**. Object, mesh, collection,
bounds, topology and triangle-count summaries matched: **32 objects, 6 mesh
objects** (four exports, original terrain reference and debug dashes). All saved
mesh winding/degeneracy checks passed. Both PNGs were rendered from that reopened
scene and opened for visual inspection: hairpins/shoulders continuous at view
scale; artificial edge cut/shadow visible. No orthophoto registration, ground-level
accuracy or interactive GUI performance inspection is claimed.

FBX exports **only the four selected meshes**, binary version 7400, forward **−Z**,
up **Y**, global scale **1**, `apply_unit_scale=True`,
`apply_scale_options=FBX_SCALE_UNITS`, `bake_space_transform=False`, explicit
triangles plus `use_triangles=True`, no animation or embedded textures. This
records an interchange choice, **not** Windows/AC axis acceptance.

The FBX header was parsed and FBX was actually imported into temporary in-memory
objects in the same Blender process. All **4 mesh counts, 230400 triangles,
upward winding, nondegeneracy and restored local-world bounds** passed. Maximum
bounds difference versus float64 build geometry was **0.0005563 m**. Imported
objects were deleted; the saved .blend was **not overwritten**. This validates
Blender's roundtrip, not another importer. Asset hashes are in `postflight.json`.

## Next blocker / acceptance boundary

**Windows Assetto Corsa SDK / ksEditor access and conversion are the next pipeline
blocker.** Inventory actual versions and arrange a safe transfer without touching
existing game content. Then verify FBX axes/metre scale, normal/material mapping,
SDK shaders, visual-vs-collision separation and KN5 conversion. A separately
approved playable test also needs supported spawn/session/timing conventions,
collision/suspension/edge tests, actual Windows driving, and later VR/performance
validation. No M3 gameplay gate, timing workflow, full track or Quest 2 acceptance
has been completed by this prototype.
