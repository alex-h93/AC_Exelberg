# Offline full-route raw input handoff — version 1

## Scope and build

This supersedes the **extent**, not the geometry decisions, of the 1–2.5 km
prototype handoff. It covers the entire original Königstetten → Marswiese route:
**0–15226.291863325048 m EPSG:3035**, or **15226.670946413231 m EPSG:25833**.
The requested deliverable is a full approximately 15.2 km **two-lane track**;
these files are raw authoring inputs, not a playable track or approved road mesh.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/prepare_full_track.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -q
```

Entirely offline using installed local NumPy, pyproj and tifffile. No installs,
network, game launch/deployment, GUI access, source-data changes or scene writes.
Rerunning replaces only the generated files in `data/processed/full_track_inputs/`.
The script reuses read-only geographic helpers from `scripts/prepare_prototype.py`.

## Coordinate and sample contract

Follow [COORDINATES.md](../decisions/COORDINATES.md): **origin (589500, 5346800,
300) m**, horizontal EPSG:25833; X east, Y north, Z up. No rotation/axis swap.
Local XYZ plus origin recovers E,N,H. H is BEV product-documented **EPSG:9274 /
EVRF2000 Austria orthometric height**, not independently surveyed. No vertical
transformation, GPS-height substitution or RFC7946 Z interpretation.

All **1,145 original OSM vertices**, including corners and exact endpoints, remain
unchanged. The route is densified on native UTM straight segments, maximum step
**1.999873448113 m**, yielding **8,156 points**. Both chainage arrays interpolate
original vertex chainages; EPSG:3035 labels are not native UTM distance. Do not
recompute alignment by interpolating rounded old CSV profiles.

Raw ground is sampled at these actual 2 m route positions from the original
**1 m EPSG:3035 raster**, not interpolated from an old 10 m elevation profile.
Inverse horizontal projection precedes strict bilinear sampling at pixel centers.
All four support pixels must be finite and non-nodata, even at zero weight.
No height smoothing, road shaping, cut/fill, invented coverage or datum conversion.
Every route sample and all **65,248 lateral samples** are currently valid.

**All arrays finite; invalid raw H and local Z are zero placeholders, never ground.**
Read masks before using heights. Local Z placeholder zero is not H=300 evidence.
Load NPZ with `allow_pickle=False` and verify manifest schema/version/hashes.

## Consumer files and exact keys

Directory: `data/processed/full_track_inputs/`. `manifest.json` schema is
`assetto-exelberg.full-track-inputs`, integer `version=1`. It includes transform
operation definitions/accuracy, bounds, counts, diagnostics, coordinate controls,
provenance and exact per-array dtype/shape. All numeric arrays below are
**float64**, except explicitly **bool** masks and **int64** tile slices.

Dimensions: V=1145 original vertices, N=8156 dense route samples, L=8 offsets,
R=850 terrain rows, C=1095 terrain columns, T=5844 tree anchors.

### `route.npz`

| Key | Shape | Meaning |
| --- | --- | --- |
| `full_xy_25833_m`, `full_xy_3035_m` | V×2 | Original projected OSM vertices |
| `full_chainage_3035_m`, `full_chainage_25833_m` | V | Original vertex stations |
| `chainage_3035_m`, `chainage_25833_m` | N | Dense stations from zero through exact full length |
| `xy_25833_m`, `xy_3035_m` | N×2 | Dense native alignment; inverse-projected sampling coordinates |
| `raw_height_9274_m` | N | Unmodified sampled H |
| `valid` | N bool | Raw ground validity |
| `local_xyz_m` | N×3 | Raw ground positions, not designed road profile |

### `lateral.npz`

| Key | Shape | Meaning |
| --- | --- | --- |
| `offsets_m` | L | [-15,-8,-3.75,-3,3,3.75,8,15] m |
| `xy_25833_m` | N×L×2 | Lateral probe positions |
| `raw_height_9274_m`, `valid` | N×L | Raw H and bool validity |
| `local_xyz_m` | N×L×3 | Raw probe positions |

Rows match route samples exactly. Positive offset is **left of travel**, using
centered tangents of the raw densified alignment (one-sided at endpoints).
Offsets ±3/3.75 m are reference probes, **not measured or approved road widths**.
Use ±8/15 m ground references when designing shoulders/verges; no connection mesh
or terrain modification is supplied. At corners, probes are not surveyed road
cross-sections and may reference a nearby hairpin arm.

### `terrain.npz`

| Key | Shape | Meaning |
| --- | --- | --- |
| `x_m`, `y_m`, `z_m` | R×C | Regular local X/Y and sampled local Z |
| `raw_height_9274_m` | R×C | Raw orthometric H |
| `valid` | R×C bool | Strict source coverage |
| `valid_cells` | (R−1)×(C−1) bool | All four corner nodes valid |
| `tile_node_slices` | 63×4 int64 | [row_start,row_stop,col_start,col_stop], exclusive stops |

Grid spacing **8 m**, rows increase northward, columns eastward. UTM node bounds
**[585760,5343848]–[594512,5350640] m**. Full route bbox padded 200 m; this does
**not** assert complete measured terrain throughout that rectangle. Existing
acquired ±approximately 200 m corridor tiles supply **209,912 valid nodes** out
of **930,750** (hard cap 1,600,000), and **207,885 valid cells**. Remaining nodes
are explicitly invalid. Never bridge holes or turn the bbox into filled terrain.
Only triangulate `valid_cells`; winding must face +Z. For example cell (r,c)
uses (r,c),(r,c+1),(r+1,c+1) and (r,c),(r+1,c+1),(r+1,c).

Tiles contain at most **128×128 cells / 129×129 nodes**, share one boundary node
row/column, and do not duplicate cells. Reindex locally on consumption; preserve
identical shared boundary coordinates. Projection/sampling uses bounded 128-row
strips. Raw grid is deliberately coarser than route probes and is not a driving
surface. Triangulation may not interpolate exactly through raw tree/probe H.

### `trees.npz`

| Key | Shape | Meaning |
| --- | --- | --- |
| `xy_25833_m` | T×2 | Candidate XY |
| `raw_height_9274_m` | T | Actual sampled ground H |
| `local_xyz_m` | T×3 | Candidate ground anchors |
| `valid` | T bool | All true after filtering |
| `generating_chainage_25833_m` | T | Generating row station, NOT nearest-road chainage |
| `nearest_route_segment_distance_m` | T | Exact minimum distance to every original route segment |

**SYNTHETIC ROADSIDE DISTRIBUTION, NOT MEASURED FOREST.** 25 m generating stations,
seed 20260221, rows ±12/30/60/100/145 m, ±1 m XY jitter. Only valid raw ground
inside a fully valid containing terrain cell survives. All anchors are >10 m
from **every route segment**, including other hairpin arms; this is not a
vertex-only distance filter. Result: **5,844** optional placeholders, not assets.

`merged.json` was read and hashed: 27 forest/wood-tagged ways and 3 tagged
relations inventoried. **No forest mask or polygon topology is implemented**;
all 3 forest relations remain unresolved, including potential holes/openings.
Do not present candidates as OSM forest placement: they can occupy fields,
buildings and clearings. Final scenic placement requires resolved polygons or
manual review; consumers should make these placeholders optional.

## Provenance and controls

`manifest.json.provenance.inputs` records path, byte count and **SHA256 for every
input**: route GeoJSON, preserved corridor TIFF, merged OSM, terrain coverage,
source tags, acquisition operation ledger and every cached raw range file.
`outputs` records path/bytes/SHA256 and exact array schemas for all four NPZs.
The original full remote DTM was not downloaded. Terrain attribution: © BEV,
CC BY 4.0; route/OSM © OpenStreetMap contributors, ODbL. Preserve attribution.

Three widely separated synthetic-height H=300 controls store original 3035,
25833, local XYZ, inverse 3035 and residuals. Largest roundtrip residual is
**9.313225746154785e-10 m** (build fails above 1 mm). This tests mapping, not height
or OSM survey accuracy. Start/finish local XY controls respectively:
(-3536.282460723305,3636.248904443346) and
(4804.210173644591,-2600.6904488848522) m. Controls have local Z=0 by construction,
not actual start/finish elevation. Projection-operation accuracy is not road accuracy.

## Explicit geometry/runtime handoff blockers

- **Raw dip retained at EPSG:3035 chainage 9580–9600 m.** Manifest diagnostics
  include exact dense stations/heights; approximately 486.616 m at 9589.155 m,
  versus 488.863 m at 9585.219 m and 489.238 m at 9593.091 m. Maximum adjacent
  full-route raw grade magnitude is approximately 0.988. This is a potential
  profile anomaly, not an acceptable driving-road grade. Blender specialist
  must make a separately audited candidate correction; do not alter these data.
- User runtime feedback says v001 **loads but spawns backwards and falls off the
  mountain**. No fix or additional runtime validation is implied by this handoff.
  Coordinator/Blender specialist must review forward tangent/spawn orientation,
  designed two-lane road, collision continuity and safe terrain/verge joins.
- No endpoint extension, finish run-out, road width/camber, smoothing, collision
  geometry, terrain cut/fill or game/source asset is created or approved here.

## Checks performed

Full offline suite: **173 tests passed**. Added 9 tests cover exact nearest-segment
hairpin distances, normal sign, nodata rules, grid cap, complete nonoverlapping
tile cell partition, deterministic tree candidates, generated hashes/dtypes,
all original corners/full endpoints/stations, common origin/roundtrips, actual
route/lateral/tree raw sampling and distributed terrain resampling, masks and
anchor containment. No Blender execution, visual inspection or game test.
