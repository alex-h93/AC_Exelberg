# Supplemental forest acquisition — v002 completion attempt

## Result: source membership completed; full-route forest mask BLOCKED

The three specifically authorized OSM relation/full downloads succeeded. All
member ways and their nodes are now present. **Actual full-route polygon coverage
is not complete:** strict unchanged topology validation rejects the two major
forests. Do not present this handoff as a completed scenery mask or force a target
of 5,000 trees.

The separate conservative candidate remains **65 / 5,844 anchors**, rejecting
5,779. This is not a new placement or full-route result. No geometry was repaired,
no holes removed, no fragments promoted, and no validation relaxed. No additional
requests, retries, alternate services, or automatic fallback downloads occurred.

Coordinator handoff:
`data/processed/full_scenery_v002/manifest.json`.
This is a schema `assetto-exelberg.full-scenery-inputs`, version **1**, candidate,
not a replacement for v001 or `full_track_inputs`. Its NPZ has the exact keys,
dtypes, coordinate conventions, index semantics and exclusion rules documented in
[FULL_SCENERY_INPUTS.md](FULL_SCENERY_INPUTS.md). No consumer was switched.

For a no-mask fallback, retain the unchanged upstream
`data/processed/full_track_inputs/trees.npz`; those 5,844 anchors are synthetic
candidates, **not verified forest trees**. No unfiltered array is relabelled as a
forest-masked result. Whether to use that fallback is a coordinator decision.

## Acquisition evidence

Acquired 2026-10-25 UTC from exactly these endpoints:

| URL | HTTP | Exact body bytes | SHA256 |
|---|---:|---:|---|
| https://api.openstreetmap.org/api/0.6/relation/4624/full | 200 | 1,884,341 | `d194e2ebf1296c93dc5e10ba4ee6fc8c102b51171601e1c9aaacd57aea93a0c2` |
| https://api.openstreetmap.org/api/0.6/relation/4625/full | 200 | 2,275,952 | `633b6f5bde8985ac154012564f6075cd5d02471b6f9762cda59f5668274089ab` |
| https://api.openstreetmap.org/api/0.6/relation/15456599/full | 200 | 26,474 | `14ab1bb577869a7048edc1bc514c6e39ac3c73648ff1202c086b0041cb190acf` |

**Total: 4,186,767 body bytes, three requests, zero retries.** Exact XML and
individual SHA256/URL/request/receipt-date/license sidecars are preserved under
`data/raw/full_forest/`; `operation.json` records every attempt and byte count.
© OpenStreetMap contributors, ODbL-1.0:
https://www.openstreetmap.org/copyright . Original anchor terrain remains © BEV,
CC BY 4.0; no elevation or geographic accuracy improvement is claimed.

The new downloader uses streaming single-read chunks, 20,000,000 bytes per
successful response, 60,000,000 bytes total, an 8,192-byte error-body cap, identity
encoding, a descriptive User-Agent, no redirects, a 20-second socket timeout and
a checked 60-second wall-clock deadline (one socket timeout may overrun it).
HTTP 400/timeouts are reported, never bypassed. An existing operation ledger
prevents accidental repeat acquisition, including after a partial operation.

## Missing-member and topology diagnosis

| Relation | Previously missing ways | Now missing ways | Joined outer / inner rings | Strict result |
|---|---:|---:|---:|---|
| 4624 | 205 | 0 | 2 / 231 | skipped: `overlapping or nested inner rings` |
| 4625 | 341 | 0 | 4 / 398 | skipped: `overlapping or nested outer rings` |
| 15456599 | 2 | 0 | 1 / 1 | resolved |

Every merged way also has all referenced nodes. Missing downloads are no longer
the blocker. Diagnostic examination with the existing node-ID join and projected
intersection/containment functions found, in source member order:

- Relation 4624: inner components 4 and 98 (zero-based) touch, sharing node IDs
  `313906637`, `2589434714`; the current inclusive containment test also flags
  the latter component's first vertex within the former. This is the first
  failing inner pair, not a claim that all other pairs are valid.
- Relation 4625: outer component 0 is inside outer component 2, without a boundary
  intersection. Its inner components also have touching pairs; components 2 and
  121 share five node IDs. The outer-ring rejection happens first.

These observations do not authorize repair, reinterpretation of roles, unioning
nested outers, or accepting touching holes. **Escalate topology policy and any
geometry decision to the coordinator.** No Blender geometry was created or
changed. The existing forest-member suppression rule also suppresses standalone
forest way `667558244`, whose parent is 4625; it cannot bypass the rejected parent.

## Separate merge and output contract

`data/interim/full_forest/merged.json` is a new 14,480,293-byte file. It merges the
previous `data/interim/osm/merged.json`, its four original XML sources, and the
three supplemental XML sources using the existing `merge_sources` function:
identity is `(type, id)`, newer versions win, and different content at the same
version aborts. Each individual XML source retains its original full provenance
in the new merged document's `sources` entries. The historical merged source is
also recorded separately. This combines different acquisition dates, not one
transactionally synchronized OSM snapshot.

The v002 manifest individually hash-pins the old merged input, every original and
supplemental XML, their individual provenance files, the new merged file,
operation ledger, old manifest template, both producer scripts, and unchanged
upstream anchor/route/terrain files and manifest. No source definitions are read
and executed; the new producer imports pure geometry helpers and does not invoke
the old producer's `main`. Descriptive schema-1 metadata is inherited from the
hash-pinned v001 manifest; all data-dependent fields are recomputed.

Files under `data/processed/full_scenery_v002/`:

- `forest_trees.npz`: **5,707 bytes**, 65 exact original indexed rows;
- `source_inventory.json`: **922,625 bytes**, 2,288 resolved / 2 skipped /
  1 suppressed entries; 28 resolved forest sources;
- `manifest.json`: **8,453 bytes**, same version-1 contract, explicit input records.

Forest mask count 65; exclusion intersections 0; overlapping-forest candidates 0.
Zero exclusions do not establish that the geographic source is complete.
The additional resolved relation does not add selected anchors. Strict all-route
clearance, valid terrain cells, finite values, original order and exact original
array values/dtypes are retained. Forest holes and resolved building/water
exclusions use the unchanged strict rules.

Generating-chainage coverage in 1 km bins (final bin partial):

| km | Input | Selected |
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
| 15–16 | 90 | 0 |

Only 3 / 16 generating-chainage bins have selected anchors. Full-route acceptance
is explicitly **not met**.

## Execution and checks

Executed using the current local environment, no installation:

```sh
.venv/bin/python scripts/acquire_forest_relations.py --acquire
.venv/bin/python scripts/acquire_forest_relations.py --build
.venv/bin/python -m unittest discover -s tests -v
```

**190 tests passed**, including seven new acquisition/merge/handoff tests. Fixtures
exercise exact endpoint restriction, finite timeout/UA, exact XML preservation,
provenance, refusal to reacquire, HTTP 400 body accounting, timeout, malformed XML,
streaming response/total caps, latest-version selection and conflict rejection.
Actual-data checks cover complete references, honest topology rejection, exact
subset/source attribution, exclusions, terrain/clearance invariants, inventory,
coverage accounting, schema and all v002 input/output hashes.

The existing v001 hash test also passes, including its original producer-script
hash; that script is unchanged. All eight records pinned by the original scenery
manifest were independently rechecked against their original hashes and sizes.
Original raw/merged data, route, terrain, source CSV/NPZ, and v001 outputs remain
untouched. No GUI, Blender, deployment, live game, visual inspection or runtime
validation was performed.

The downloader and builder intentionally refuse existing destinations. For
reproduction, preserve the raw ledger/XML and use the importable `build` function
with **new** `merged` and `out` paths; do not rerun acquisition or overwrite the
preserved handoff.
