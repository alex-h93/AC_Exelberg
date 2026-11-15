# Offline full-track forest-mask handoff

## Scope and result

Run from the project root, without network, installation, Blender or game access:

```sh
.venv/bin/python scripts/prepare_full_scenery.py
.venv/bin/python -m unittest discover -s tests -v
```

This is a **separate, optional scenery input**, not a change to the
`full_track_inputs` schema, producer, route, terrain, or any existing consumer.
A consumer must explicitly choose `full_scenery/forest_trees.npz` instead of
`full_track_inputs/trees.npz`; no consumer has been switched here. Continue to
use the original full-track route/terrain/lateral arrays and their validity
contracts unchanged. No scene, mesh, game placement or visual validation is implied.

Current local result: **65 of 5,844 anchors selected**, 5,779 rejected.
Resolved sources: 27 forest polygons, 2,189 building polygons, 44 water polygons.
There are 2,260 resolved source entries, three skipped entries, and no suppressed
entries in this particular extract. Eight distinct forest ways contribute selected
anchors. No candidate overlaps multiple resolved forests; zero forest candidates
intersect resolved building/water exclusion masks. These zero counts do not prove
source completeness or the absence of real buildings/water.

**Coverage blocker:** forest relations `4624`, `4625`, `15456599` lack respectively
205, 341, and 2 member ways in the existing local extract. Each entire relation is
skipped, including its known fragments: an outer fragment or missing inner ring
must not silently become forest. This local input cannot support an honest
approximately 5,000-tree full-corridor result. No geometry is invented, no missing
members are fetched, and no target count is enforced. Full coverage requires a
coordinator decision and a separately authorized source-completion task.

Generating chainage bins in EPSG:25833 (not exact nearest-road chainage):

| km interval | input | selected |
|---|---:|---:|
| 0–1 | 351 | 52 |
| 1–2 | 330 | 12 |
| 2–3 | 383 | 0 |
| 3–4 | 400 | 0 |
| 4–5 | 400 | 0 |
| 5–6 | 400 | 0 |
| 6–7 | 400 | 0 |
| 7–8 | 400 | 0 |
| 8–9 | 393 | 0 |
| 9–10 | 397 | 0 |
| 10–11 | 398 | 0 |
| 11–12 | 400 | 0 |
| 12–13 | 379 | 0 |
| 13–14 | 333 | 0 |
| 14–15 | 390 | 1 |
| 15–16 (last partial) | 90 | 0 |

## Polygon method

Use actual `node` coordinates, `way.nodes`, `relation.members`, and tags from
`data/interim/osm/merged.json`. Forest means `landuse=forest` or `natural=wood`.
Building means a present `building` value other than `no`. Water exclusions mean
`natural` in `water,wetland,bay`, `landuse` in `reservoir,basin,salt_pond`,
`waterway` in `riverbank,dock`, or a present `water` value other than `no`.
Only actual closed polygons are used, not bounding boxes, buffers, node markers,
water centerlines, leaf-type tags, or candidate-row proximity. No independent
field mask is inferred: candidates outside resolved forest polygons are rejected.

Standalone ways must explicitly close by node ID. Multipolygon members must be
ways with `outer`, `inner`, or empty roles (empty is treated as outer). Members
are joined by matching endpoint **node IDs**, reversing whole ways when needed;
coordinate proximity never closes a gap. Multiple disconnected **closed** outer
components are supported. Open/disconnected chains, branching endpoint graphs,
missing members/nodes, duplicate members, unsupported member types/roles,
non-multipolygon relations, repeated-node/degenerate/self-intersecting rings,
intersecting/nested outer rings, uncontained/touching holes, and overlapping/nested
holes are skipped and reported rather than repaired. A missing member anywhere
invalidates the whole relation, even if some rings appear locally complete.

Forest-tagged ways belonging to forest relations are not reused as standalone
forest masks. This applies conservatively even to incomplete parents, preventing
closed inner/fragment members from bypassing missing relation topology. Other
building/water categories on such ways remain independently eligible. The local
extract has no such independently forest-tagged member ways, so suppression count
is currently zero; synthetic tests exercise this policy.

Projection is offline WGS84 (EPSG:4326, longitude/latitude) to EPSG:25833 using the
existing non-ballpark project helper. Transformer details are in the manifest.
Point-in-polygon uses even/odd ray crossing and a 0.000001 m numerical boundary
tolerance, **not geographic precision**. Union outer rings, subtract union inner
rings. Outer boundaries count as included; hole boundaries count as excluded.
Then subtract all resolved building/water masks, with the same polygon/hole
semantics. Unresolved exclusions are explicit gaps, not evidence of safety.

Select existing anchors only, preserving original order and all original array
values/dtypes. Overlapping forests yield only one output row; deterministic source
attribution sorts ways before relations, then ascending numeric OSM ID. Hole
exclusion is per forest polygon; an independently tagged overlapping forest can
provide positive coverage. No resampling, jitter, replenishment or relocation is
performed. Synthetic upstream rows can still look artificial inside real forest
bounds; these are not observed individual trees, species measurements, survey-grade
positions, or a complete forest inventory.

## Exact output schema (version 1)

All outputs are under `data/processed/full_scenery/`.
`forest_trees.npz` contains only finite, non-object NumPy arrays, loadable with
`allow_pickle=False`. `N=65` for this run. The first six arrays are exact indexed
copies of the upstream arrays:

| key | dtype | shape | meaning |
|---|---|---|---|
| `xy_25833_m` | float64 | (N,2) | absolute easting/northing, metres |
| `raw_height_9274_m` | float64 | (N,) | original raw ground height, EPSG:9274 |
| `local_xyz_m` | float64 | (N,3) | E−589500, N−5346800, H−300, metres |
| `valid` | bool | (N,) | all true; original upstream validity |
| `generating_chainage_25833_m` | float64 | (N,) | original row-generation chainage |
| `nearest_route_segment_distance_m` | float64 | (N,) | exact planar distance to all original route segments |
| `source_anchor_index` | int64 | (N,) | zero-based row in original trees.npz; strictly increasing |
| `source_forest_id` | int64 | (N,) | positive OSM forest source ID |
| `source_forest_type` | uint8 | (N,) | 1=way, 2=relation; pair with ID |

All 5,844 input anchors are checked for finite values, true validity, original local
coordinate/height consistency, distance **strictly >10 m from every original route
segment**, and valid containing full-terrain cells. Distances are recomputed and
must match stored distances within 1e-8 m absolute tolerance. Selected rows inherit
the upstream strict four-support-pixel bilinear raw-height validity without altering
or filling terrain. Source raster heights are not independently resampled by this
refinement. Selected minimum clearance: **10.863105936630513 m**.

`source_inventory.json` has `type_codes` (`way:1`, `relation:2`) and `sources`.
Each source has `type`, `id`, original `tags`, effective `categories`, `status`.
Relation entries also retain original `members` (`type/ref/role`). Resolved entries
have `outer_rings` and `inner_rings` counts. Skipped/suppressed entries have `reason`;
missing-way/node reasons enumerate absent IDs. Suppressed forest-member ways also
have `forest_parent_ids`. Ways losing only the forest category may still resolve
as exclusions. Geometry remains in the hash-pinned original OSM file rather than
being duplicated in this inventory.

`manifest.json` has:

- `schema="assetto-exelberg.full-scenery-inputs"`, `version=1`;
- `coordinates` (horizontal/vertical EPSG, local origin), `transform` operation log;
- `input_count`, `selected_count`, `rejected_count`;
- `counts`: `forest_mask_count`, `excluded_in_forest`,
  `overlapping_forest_candidates` (all refer to original candidates);
- `coverage`: `bin_edges_25833_m`, `input_counts`, `selected_counts`;
- `inventory_status_counts`: `resolved`, `skipped`, `suppressed`;
- `constraints`: `upstream_valid_anchors`, `upstream_valid_terrain_cells`,
  `minimum_all_route_clearance_m` (null for empty output),
  `unchanged_selected_source_arrays`;
- `method`, `overlap_attribution`, `attribution`, `warnings` strings/list;
- `inputs`: records of original OSM, trees, route, terrain, upstream manifest,
  and producer script; each record is `path` (project-relative), `bytes`, `sha256`;
- `inventory`: the same hash/size/path record for `source_inventory.json`;
- `output`: the same record for `forest_trees.npz`, plus `arrays` mapping each
  key to its `shape` list and NumPy `dtype` string.

The manifest hash-pins source inputs, the upstream manifest, inventory and output;
it is not self-hashed. OSM attribution: © OpenStreetMap contributors, ODbL.
Original terrain attribution: © BEV, CC BY 4.0. Vertical heights retain the original
BEV documented EVRF2000 Austria reference; no new vertical transform or independent
accuracy validation is claimed.

## Checks performed

All **183 tests pass**, including 10 new tests covering synthetic reversed member
joining, multiple outer rings, inner holes/boundaries, building/water holes,
triangle-vs-bounding-box exclusions, disconnected/missing/unsupported geometry,
parent-member suppression, overlap attribution, order determinism, actual OSM
filter membership, exact original-array selection, all-route clearance, valid
terrain cells, inventory equality, coverage accounting and input/output hashes.
No Blender, visual, game, species or field validation was performed.
