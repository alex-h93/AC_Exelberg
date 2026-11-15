# Offline conservative forest union — v003

## Finalized optional consumer source

- Manifest: `data/processed/full_scenery_v003/manifest.json`
- **Forest input: `data/processed/full_scenery_v003/forest_trees.npz`**
- Audit: `data/processed/full_scenery_v003/source_inventory.json`
- Producer: `scripts/prepare_full_forest_union.py`
- Tests: `tests/test_prepare_full_forest_union.py`

This is a separate, coordinator-authorized alternative, not a replacement for
strict v001 (`full_scenery`) or v002 (`full_scenery_v002`). Neither their producers,
outputs nor source data were modified. Consumers must explicitly choose v003;
no Blender consumer, geometry, game content or deployment was changed.

The consumer manifest retains `schema: assetto-exelberg.full-scenery-inputs`,
`version: 1`, with additive `variant`, `topology_policy`, and
`affected_relation_ids` fields. The forest NPZ has the **same schema** as v001/v002:
all original candidate arrays retain their names, dtypes and exact selected values,
plus `source_anchor_index`, `source_forest_id`, `source_forest_type` (way=1,
relation=2). EPSG:25833 horizontal / EPSG:9274 heights and local origin are unchanged.
Manifest hashes pin the merged source, upstream inputs, producer, strict helpers,
inventory and NPZ. No target tree count was imposed.

## Source and policy

Inspected the completion producer `scripts/acquire_forest_relations.py` and its
existing `data/raw/full_forest/operation.json`: all three relation/full requests
(4624, 4625, 15456599) succeeded, totaling 4,186,767 bytes. This work used only the
already completed `data/interim/full_forest/merged.json`; no requests, acquisition
or merging were performed. Existing strict tests verify full member/node coverage.
Strict v002 rejects 4624 for overlapping/nested inners and 4625 for
overlapping/nested outers; 15456599 already passes strict validation.

The new explicit policy is `forest-role-union-minus-all-inners-v1`:

1. Run the original strict inventory/resolver, unchanged.
2. Only forest relations rejected for an enumerated **inter-ring** reason are
   eligible. Revalidate member existence, types/roles, duplicate ways, endpoint
   joining/closure, missing nodes and every individual ring. No broad exception
   handler converts individual-invalid geometry into accepted forest.
3. Use union(all valid outer rings) minus union(all valid inner rings), then the
   existing strict building/water exclusions. Permit inter-ring overlap, nesting,
   touching and inners extending outside outers (subtraction outside is inert).
   All inner boundaries subtract; outer boundaries include.
4. Do not restore outer islands inside holes, infer containment hierarchies, snap,
   invent, fill or reconstruct open rings. Existing forest-member suppression
   remains active. Stable way-before-relation/ascending-ID attribution deduplicates
   selected anchors. Building/water geometry never inherits relaxed validation,
   even on a relation also tagged forest.

Affected IDs **4624, 4625** are recorded with policy, warning and strict rejection
in the inventory and manifest. All other geometry follows strict behavior. This is
an **approximate real-forest mask over synthetic candidates**, not measured trees,
species, complete forest coverage or survey-quality geometry. OSM/BEV licensing
and attribution remain in the manifest. Any unresolved exclusions remain a coverage
limitation, not permission to invent geometry.

## Measured output

- Input candidates: **5,844**; selected **4,616**; rejected **1,228**.
- Forest-mask candidates: 4,616; building/water exclusions within that mask: 0;
  multiply attributed forest candidates: 0.
- Inventory: 2,290 resolved, 0 skipped, 1 suppressed.
- All selected terrain cells valid; all-route minimum clearance:
  **10.113638822029952 m**, strictly greater than 10 m.
- Selected arrays are exact immutable upstream subsets; no coordinates changed.
- Coverage: **16/16 chainage bins populated** (1 km, final partial bin).

| Chainage km | Input | Selected |
|---|---:|---:|
| 0–1 | 351 | 66 |
| 1–2 | 330 | 149 |
| 2–3 | 383 | 341 |
| 3–4 | 400 | 400 |
| 4–5 | 400 | 286 |
| 5–6 | 400 | 376 |
| 6–7 | 400 | 380 |
| 7–8 | 400 | 344 |
| 8–9 | 393 | 320 |
| 9–10 | 397 | 393 |
| 10–11 | 398 | 393 |
| 11–12 | 400 | 360 |
| 12–13 | 379 | 378 |
| 13–14 | 333 | 229 |
| 14–15 | 390 | 164 |
| 15–end | 90 | 37 |

## Reproduction and checks

```sh
.venv/bin/python scripts/prepare_full_forest_union.py
.venv/bin/python -m unittest discover -s tests
```

The producer is offline-only and refuses an existing output directory; preserve
the finalized outputs rather than rerunning over them. `produce(merged, out)` can
use a separate destination for comparison. No installs were needed.

Tests cover nested holes, overlapping outers/inners, island exclusion, touching,
uncontained subtraction, unchanged strict rejection, strict building/water
exclusions, individual-invalid/structural rejection, exact selected arrays,
provenance hashes, terrain validity and all-route clearance. Existing strict
v001/v002 tests also continue to run unmodified. Full suite result: **198 tests
passed** (47.122 seconds); the printed `validate_kn5` refusal is an expected
negative test. No Blender execution, visual
inspection, game launch, runtime or VR validation was performed.
