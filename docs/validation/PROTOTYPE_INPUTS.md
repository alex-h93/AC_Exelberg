# Offline northern hairpin prepared inputs — contract v1

## Build and verified result

From project root, no installation or acquisition:

```sh
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python scripts/prepare_prototype.py
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python -m unittest discover -s tests -q
```

Actual build completed without Blender, network, road shaping or meshing.
**80 offline tests passed**, including eight new tests for clipping, exact
endpoints, corner-preserving ≤2 m sampling, axis/origin inverse mapping, strict
bilinear nodata handling, fully-valid-cell topology, real-data sampling and hashes.
The existing source validator was also executed with `save_json` replaced by a
no-op (to avoid touching existing reports) and sockets blocked: **14,680,064
source pixels bit-exact**, 1,524 existing profile samples matched, source route
unchanged. No existing source or processed products were overwritten.

Outputs under `data/processed/prototype/`:

| File | Bytes | Meaning |
|---|---:|---|
| `manifest.json` | 21,578 | Versioned contract, transforms, controls, provenance, hashes |
| `route.npz` | 88,111 | Full alignment, section vertices, dense route and raw heights |
| `terrain.npz` | 797,326 | Local regular grid and explicit validity masks |

Section **1000–2500 m EPSG:3035 chainage**, Königstetten → Marswiese direction.
**837 dense points**, maximum native UTM step **1.996016571 m**; all valid raw
terrain samples. Full source OSM section corners are included without smoothing.
The unresolved **9589 m** anomaly is outside this section.

Terrain: **355 rows × 301 columns = 106,855 vertices**, **2 m** grid spacing,
section bounding box expanded by **120 m**, then snapped outward to 2 m grid.
UTM bounds: E **585910–586510 m**, N **5349520–5350228 m** (600 × 708 m).
All 106,855 vertices and 106,200 cells are valid in this build. This manageable
section-only rectangle is not the oversized full-route terrain rectangle.
Do not assume future builds have no gaps: masks are mandatory.

## Consumer entry point and manifest JSON keys

Read `manifest.json`, require `schema == "assetto-exelberg.prototype-inputs"`
and `version == 1`; reject unknown versions. Paths are relative to project root,
not the manifest directory. Verify artifact SHA256 before loading. Use
`numpy.load(path, allow_pickle=False)`; no Python packages from the project venv
need to be injected into Blender (its NumPy can load these arrays).

Top-level keys:

- `schema`, `version`, `purpose`: identity and provisional status.
- `coordinates`: horizontal/vertical EPSG, units, `origin_m` in E,N,H order,
  origin rule, exact midpoint, axes, and explicit no-vertical-transform statement.
- `section`: exact start/end, chainage convention, full route lengths in both
  projections, sample count, maximum step, raw-only flag, excluded anomaly.
- `terrain`: resolution, margin, row/column shape, counts, projected/local bounds
  (lower XY pair then upper XY pair), sampling/placeholder/topology rules.
- `precision`: storage, maximum local extent and float32 spacing at that extent.
- `transforms`: source/target EPSG, selected description/PROJ definition, accuracy,
  best-available status, always-XY, no-ballpark and network-disabled flags.
  These are horizontal transforms only; accuracy -1 would mean unknown.
- `software`: actual NumPy, pyproj and PROJ build versions.
- `controls`: three full-route locations in source/working/local coordinates,
  synthetic orthometric control height, inverse source coordinates and residuals.
- `provenance.inputs`: project-relative path, byte length and SHA256 for original
  OSM XML, original terrain range bytes/ledger, route and verified raster inputs.
  A hash of the unavailable complete remote TIFF is not claimed.
- `outputs.route` / `outputs.terrain`: path, bytes, SHA256, `arrays` dictionary
  whose entries describe exact shapes and dtypes. Manifest does not hash itself.
- `orthophoto`: existing Doppler patch and its manifest paths, EPSG:31256,
  reference-only scope. No new imagery, reprojection or full-section coverage.
- `caveats`: limitations consumers must retain.

## `route.npz` arrays

All numeric arrays float64, mask bool. Parallel rows refer to the same point.

| Key | Shape / interpretation |
|---|---|
| `full_xy_25833_m` | (F,2), whole original ordered OSM alignment, UTM E,N |
| `full_chainage_3035_m` | (F,), original profile-convention station per full vertex |
| `full_chainage_25833_m` | (F,), UTM station per full vertex; origin selection only |
| `section_vertex_chainage_3035_m` | (V,), clipped exact boundaries plus all interior OSM vertices |
| `section_vertex_xy_25833_m` | (V,2), native UTM section alignment for specialist generation |
| `chainage_3035_m` | (837,), dense sample labels in profile convention |
| `xy_25833_m` | (837,2), native UTM dense section positions |
| `xy_3035_m` | (837,2), inverse-transformed positions used for original raster sampling |
| `raw_height_9274_m` | (837,), unshaped bare-earth orthometric heights |
| `valid` | (837,), whether raw height is real terrain |
| `local_xyz_m` | (837,3), local position with raw height, not designed road |

Exact boundary positions come from EPSG:3035 route interpolation, then transform
to UTM. Densification preserves every corner in native UTM; chainage labels
interpolate parent source stations, not a new UTM distance origin. Invalid heights
and invalid local Z would be **0**, not elevations; the current producer fails if
any section sample is invalid. No optional CSV was needed.

## `terrain.npz` arrays and topology rule

`x_m`, `y_m`, `z_m` are float64 arrays of shape (355,301), already **local** metres.
Columns increase X eastward, rows increase Y northward. `valid` is bool of the
same shape; `valid_cells` is bool (354,300). Invalid Z is **0 local metres as a
finite placeholder**, never terrain at H=300. X/Y remain legitimate positions.
All values are finite, including masked-out nodes.

For a cell `(r,c)`, use it only when `valid_cells[r,c]` is true, equivalently all
four `valid[r:r+2,c:c+2]` values are true. Only then may the Blender specialist
triangulate it. Do not connect across holes, average placeholders, interpolate
nodata, or triangulate partial cells. Triangle winding, diagonal choice, road
surface, shoulder joins, camber and all mesh decisions belong to that specialist.

Grid nodes are inverse-transformed to original EPSG:3035, sampled at pixel
centers with strict four-pixel bilinear support. **Any nodata, nonfinite or
out-of-bounds support invalidates the node**, even a zero-weight neighbor.
The existing EPSG:3035 raster was verified bit-exact against the preserved raw
source ranges; no synthetic terrain fill, road smoothing or height transformation
has been introduced.

## Coordinate and accuracy caveats

Common origin **(589500, 5346800, 300) m**, not section-centered. See
[COORDINATES.md](../decisions/COORDINATES.md) for operation details, roundtrips,
axis mapping and differing spherical/3035/UTM length conventions. Do not apply
origin subtraction twice to local arrays. Whole-route arrays have no fabricated
heights and are not intended as a full-route surface.

DTM is bare earth, not a survey of asphalt crossfall, roughness or road edges.
OSM alignment remains provisional; precise imagery registration, independent
height accuracy and source capture dates remain unresolved. No anomaly correction
is implied by excluding km 9.589. No Blender execution, road geometry, exporter,
Windows, game, timing or VR acceptance is claimed. No blockers for this data
handoff; those downstream decisions/validations remain with the coordinator and
Blender specialist.
