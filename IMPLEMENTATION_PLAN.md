# Assetto Exelberg — implementation plan

## 1. Agreed scope

Build a recognizable, geographically grounded Assetto Corsa road track for private use.

- **Direction:** Königstetten → Dopplerhütte → Scheiblingstein / Exelberg → Marswiese.
- **Start:** WGS84 latitude `48.3012763`, longitude `16.1591442`.
- **Finish:** WGS84 latitude `48.2439815`, longitude `16.2702098`.
- **Reference:** `Screenshot_google_maps.jpg` and the user-provided Google Maps link:
  <https://maps.app.goo.gl/ZG9JyqGHiSVBXBC57> (link directions are opposite the agreed driving direction).
- **Approximate length:** 15.2 km. The full source route is 15.226 km projected;
  v002's designed road is 15.213 km after audited smoothing, with source endpoints retained.
- **Road:** two lanes. Current nominal design is two 3 m lanes / 6 m total,
  provisional until actual widths and crossfall are checked along the route.
- **Initial gameplay:** solo driving and timed point-to-point runs; no traffic or competitive AI.
- **Initial appearance:** daylight, dry road; seasonal appearance to be agreed before scenery production.
- **Latest requested detail:** remove striped safety walls, use invisible containment
  3 m beyond each nominal asphalt edge, nominal 33 m roadside posts, and licensed
  orthophoto landscape textures. Street View is visual reference only unless rights
  for asset reuse are established.
- **Available game testing:** user now has Assetto Corsa in local Linux Steam;
  validate via the existing Proton setup first. The separate Windows installation
  remains a fallback. No runtime installation/launch is implied by this plan.
- **Authoring environment:** Bazzite Linux for geographic processing, Python, and Blender where practical.
- **Display:** single 4K monitor; reduced rendering resolution acceptable. Quest 2 VR is a planned option.
- **CSP:** plan a documented, tested Custom Shaders Patch configuration, not unverified preview-only dependencies.

Keep the full route unless a prototype demonstrates a concrete problem. No verified hard engine distance limit requires shortening it. Length alone is not an adequate performance predictor.

## 2. Permissions and operating constraints

Writing project documentation and implementation files is permitted. This document is a plan, not a request to start all implementation phases immediately.

- Install Python libraries **only inside a project-local `.venv`**, using that environment's Python/pip. No global, user-site, or system Python package installs.
- Ask the user **before installing any additional non-Python software**, including Blender, QGIS, GDAL system packages, Wine/Proton additions, Content Manager, CSP, plugins, and SDK tools. Existing tools may be inspected and used without installation.
- Ask the user **before downloading anything larger than 1 GB**. Use 1,000,000,000 bytes as a conservative threshold. Treat a multi-request acquisition as one operation; do not split downloads or byte ranges to bypass approval.
- Estimate transfer size in advance; if unknown or likely to exceed the threshold, ask first. Include purpose, size, destination, and available smaller alternatives.
- Do not overwrite existing Windows game content, source assets, or `.blend` files without checking the destination and preserving recoverable originals.
- Preserve original geographic data and provenance. Keep generated data reproducible and separate from source files.
- Metadata inspection does not imply bulk-data acquisition, installation, or in-game validation has happened.

## 3. Current evidence and limitations

Progress is tracked in [docs/STATUS.md](docs/STATUS.md). Initial inventory,
provisional route reconstruction and first bounded terrain extraction/profile are
complete; milestone acceptance gates remain open where noted. The reconstructed
OSM route is 15.205 km by spherical distance. The terrain extraction acquired
approximately 36.43 MB including metadata/documentation, and produced 1,524 valid
route samples. Six small orthophoto references were acquired in a separate
approximately 7.86 MB operation. Their road correspondence is broadly consistent,
but precise alignment and full-corridor coverage remain open. A narrow terrain dip
near km 9.589 remains unresolved; do not use it as road geometry. User-installed
Blender 5.2.0 LTS passed readiness checks and built an editable northern prototype
covering chainage 1.0–2.5 km, using documented EPSG:25833/local coordinates.
Actual terrain/road mesh creation, renders, saved .blend reload and Blender FBX
reimport passed. Subsequently, user-approved KN5 Studio 2.6.0 exported KN5 v5
directly without ksEditor; independent static/source-geometry validation passed.
The northern v001 package was installed and **the user confirmed it loads**, but
reported backwards spawn, mountain falls and insufficient materials/scenery.
The user then authorized full-route implementation: v002 now covers the entire
two-lane road with textured surfaces, joined verges, 4,616 mapped-forest trees,
reversed spawn yaw and temporary collision walls. The user tested v002: spawn,
performance and asphalt appearance are satisfactory, but barriers can be crossed
and intermittent launches occur. A static audit found ground/barrier gaps and
unwanted internal collision caps; those are plausible, not runtime-proven causes.
**v003 is now packaged but not installed/tested**: top-only ground contacts,
ground-aware invisible strips, 822 nominal-33 m posts, and 26 orthophoto textures.
Timing, scenic fidelity, collision regression, calibrated physics and VR remain
open. See `docs/validation/FULL_TRACK_V003.md` and
`docs/validation/FULL_TRACK_PACKAGE_V003.md`.

See [the data-source register](docs/DATA_SOURCES.md) for URLs, licenses, sizes, and verification status.

Verified through metadata and HTTP headers:

- BEV offers a laser-derived **1 m bare-earth DTM** tile whose published bounds encompass the route area, with CC BY 4.0 metadata and an approximately **7.88 GB** download.
- A BEV RGB orthophoto mosaic whose published bounds encompass the area is approximately **20 cm resolution**, has CC BY 4.0 metadata, and an approximately **12.92 GB** download.
- Both endpoints honor byte ranges for metadata; both inspected images use 512 × 512 tiles. This does **not** establish cloud-optimized layout or guarantee a small corridor extraction.
- Vienna's vector service lists building footprints, contours, and height benchmarks.

Selected DTM pixels, route samples, six native orthophoto windows and 26 full-terrain backdrop textures have been checked against source data/coordinates. The existing orthophoto ledger totals 67,017,250 bytes after bounded extension. Still pending: semantic imagery/source-date review, precise alignment, terrain-anomaly truth, independent height accuracy, OSM completeness, post specification/placement, point-to-point timing, collision stability and v003 performance. Terrain/imagery do not provide asphalt camber or 3D buildings. Python dependencies remain only in `.venv`.

A 1 m terrain grid does not measure asphalt roughness or camber. BEV's general stated height accuracy is ±0.50 m, not centimetre-level road survey accuracy. Do not claim survey-grade driving geometry from these sources alone.

## 4. Proposed project organization

Create these directories as their phases require; they do not all exist yet:

```text
IMPLEMENTATION_PLAN.md
AGENTS.md
docs/
  DATA_SOURCES.md
  decisions/                 # scope, tooling, coordinate and timing decisions
  validation/                # checks, test procedures, performance observations
data/
  raw/                       # unmodified licensed source data and metadata
  interim/                   # reprojected/clipped intermediate products
  processed/                 # route, road constraints, terrain and imagery for authoring
scripts/                     # repeatable processing and validation
blender/                     # source scenes and reusable authoring assets
exports/                     # intermediate FBX and candidate KN5 files
build/                       # assembled test track package
references/                  # user photographs/video and their provenance
.venv/                       # local Python environment, if needed
```

Keep large data, generated outputs, environments, credentials, and temporary exports out of version control if Git is introduced. Check free space and allow for processing copies, not just compressed download sizes. Do not duplicate national datasets unnecessarily across operating systems.

## 5. Milestones and acceptance gates

### M0 — Inventory and technical decisions

1. Inspect existing Python/GIS/Blender tools without installing anything.
2. Record Windows game location, installed Assetto Corsa version, available SDK/ksEditor, and any existing Content Manager/CSP installation when Windows is accessible.
3. Agree on a transfer method between Linux authoring and Windows testing; do not assume a shared partition is writable or safe to modify.
4. Record a baseline monitor target before performance testing. For Quest 2, choose refresh rate, render resolution, and connection method when VR testing becomes available.
5. Select compatible authoring/export versions after a minimal export test, not from assumptions about current Blender FBX behavior.

**Gate:** tool inventory and an explicit approval list for missing software. No Linux Assetto Corsa installation required initially.

### M1 — Route and acquisition manifest

1. Acquire a small, bounded OSM road extract; follow the screenshot's road and junction choices rather than accepting an arbitrary shortest route.
2. Build an ordered centerline from the Königstetten start to Marswiese finish. Check endpoint snapping, direction, junction continuity, and hairpin shape.
3. Remeasure distance; investigate disagreement with the displayed 15.2 km before proceeding.
4. Identify route intersections with terrain/imagery footprints, tile edges, no-data regions, and acquisition-date boundaries.
5. Record exact datasets, required spatial extent, metadata, license, attribution, estimated size, and acquisition method.
6. Request approval for the BEV full-file downloads if necessary. Investigate a legitimate bounded service or range-based extraction first; stop before unapproved large transfers.

**Gate:** user-reviewable route map and manifest; a viable source for terrain and imagery across the entire road, or explicit documented gaps.

### M2 — Geographic processing and quality checks

1. Preserve originals; record source identifiers and checksums for acquired files.
2. Use one metric working CRS, preferably ETRS89 / UTM zone 33N (EPSG:25833), after verifying transformations from source CRSs.
3. Retain a documented local origin near the route midpoint for Blender/game coordinates. Record axis mapping and units; verify with known control points.
4. Keep heights in one documented vertical reference. BEV documentation generally specifies EVRF2000 Austria (EPSG:9274); do not combine it directly with Adria benchmarks or ellipsoidal GPS heights without a valid transformation.
5. Clip an initial high-detail corridor approximately 100–250 m on either side of the road, adjusting for sightlines and terrain. Use lower-detail terrain out to the visible skyline rather than a uniform arbitrary radius.
6. Prepare terrain, imagery, centerline, building footprints, woodland, and water features in standard GeoTIFF/GeoPackage or other documented interchange formats.
7. Generate elevation profile, hillshade, slope checks, and coverage/continuity diagnostics. Investigate spikes rather than silently smoothing them away.
8. Manually flag bridges, culverts, retaining walls, canopy-obscured road, steep cuttings, and uncertain widths or camber.

**Gate:** consistent scale, no unexplained terrain seams, checked coverage, and an explicit accuracy/gap report. Raster validity and transforms must be tested before scene construction.

### M3 — Representative short playable prototype

The initial ~1.5 km Königstetten/Dopplerhütte prototype loaded in the user's game.
Following that milestone, the user requested full-route implementation rather
than further isolated-prototype polishing. v002 extends the workflow to the whole
two-lane road; runtime regression remains required.

1. Validate a minimal test surface through Blender → direct KN5 exporter → Assetto Corsa (local Steam/Proton now available; Windows fallback). FBX → ksEditor remains optional. Direct KN5/static package checks pass; game loading/culling/physics are still untested.
2. Construct a purpose-built road with editable alignment, longitudinal profile, width, shoulders, and crossfall. Do not use a raw DEM triangulation as the driving surface.
3. Use sufficient mesh density for bends and elevation transitions, guided by driving tests rather than a uniform extremely dense mesh.
4. Separate physical/collision surfaces from visual scenery. Make reachable shoulders safe and believable; omit collision on distant detail.
5. Add representative terrain, guardrails, trees, markings, and one or two surface materials.
6. Verify object/surface naming, transforms, normals, spawn placement, scale, and material conversion in the actual exporter.
7. Test collisions, suspension response, smooth joins, loading, shadows, and scenery cost.

**Gate:** a repeatable export procedure and a short section that drives convincingly. Fix pipeline issues before producing the entire detailed scene.

### M4 — Full-length greybox and point-to-point timing

1. Extend the checked road and simplified terrain over the full route.
2. Provide a usable start/spawn area and sufficient finish run-out without moving the agreed endpoints unnecessarily. Any fictional staging geometry must be identified and approved.
3. Implement and test a supported point-to-point timing/session setup. Verify timer start, finish detection, result display, restart, reset-to-pits, and repeated attempts.
4. Do not assume an open route behaves like a closed hotlap circuit. If default sessions are unsuitable, test an appropriate hillclimb/event workflow before choosing any additional dependency.
5. Check the route from end to end for collision gaps, grade discontinuities, invisible obstacles, object seams, and floating-point artifacts.
6. Benchmark representative forest, hairpin, and open-view sections with simple scenery.

**Gate:** the complete track is driveable; the chosen timed-run workflow is demonstrated in-game. Keep the full route unless testing identifies a justified reason to add a shorter layout.

### M5 — Scenery and surface production

Prioritize road fidelity and visible landmarks over uniform detail everywhere.

Detailed proposal (vegetation, ground, guardrails, signs, closed junctions, selected buildings): [docs/VISUAL_UPGRADE_PLAN.md](docs/VISUAL_UPGRADE_PLAN.md).

1. Reconstruct road edges, shoulders, drainage, roadside slopes, barriers, junctions, signs, and markings.
2. Use imagery for placement, not as a substitute for eye-level reference. Infer uncertain geometry conservatively and document it.
3. Recreate recognizable landmarks, buildings, clearings, and forest transitions using appropriately licensed assets.
4. Use ground-level user photographs/video to resolve road width, barrier types, camber, and missing details; conduct any survey safely and lawfully.
5. Split assets into manageable geographic sections. Use LODs, culling, sensible materials and texture sizes, and exporter-supported batching/instancing where verified.
6. Limit expensive foliage transparency, shadow casters, and collision complexity. Check tree appearance in both monitor and stereo views.
7. Add a versioned CSP configuration for selected visual features. Keep the core road and surface physics independent from optional visual effects where practical.

**Gate:** continuous, recognizable surroundings with no obvious visual gaps from the road and no unresolved high-priority reference gaps.

### M6 — Performance and VR validation

Detected hardware: i5-12400 (6 cores/12 threads), approximately 64 GB RAM, RTX 5060 Ti 16 GB plus RTX 3060 12 GB. Confirm Assetto Corsa uses the intended GPU on Windows; GPU VRAM is not combined for rendering.

1. Record resolution, graphics/CSP settings, car, weather, test locations, GPU, and software versions for every comparison.
2. Benchmark frame times, not just average FPS, during full runs. Measure CPU/GPU bottlenecks, memory use, and loading where tools permit.
3. Establish the single-monitor target first, allowing reduced resolution. Do not sacrifice road accuracy merely to improve distant visual detail.
4. Test Quest 2 on Windows with the actual connection/runtime. Choose a sustainable refresh target; at 72 Hz the display frame interval is about 13.9 ms, at 90 Hz about 11.1 ms, with headroom needed for runtime/encoding overhead.
5. Tune foliage, shadows, draw calls, scenery LODs, and texture budgets against measured bottlenecks. A lower-detail scenery option may be preferable to shortening the road.
6. Test stereo comfort, depth, signs, vegetation shimmer, cockpit-to-road scale, and frame-time spikes. Do not label VR support validated without headset testing.

**Gate:** documented stable settings for monitor use, and either a tested Quest 2 configuration or an explicit VR-not-yet-validated status. No FPS guarantee until measurements exist.

### M7 — Package and final acceptance

1. Assemble a uniquely named track folder without overwriting unrelated game content.
2. Include required KN5/models/layout configuration, surfaces, spawns, timing setup, UI metadata, preview, map, and basic cameras as appropriate.
3. Add AI paths only if required by a validated session feature; traffic and racing AI are deferred.
4. Include installation/rollback instructions, tested AC/CSP versions, known issues, and license/attribution records.
5. Test the package from a clean copy, perform a complete timed run, restart it, and verify logs and missing assets.
6. Preserve editable Blender scenes and the processing recipe separately from the playable package.

**Gate:** reproducible package, complete-route drive, working timed run, documented performance, and honest accuracy limitations.

## 6. Model routing and task boundaries

- **Coordinator — Sol high:** planning, integration, approvals, acceptance decisions, final review.
- **Blender specialist — Sol high:** geometry, Blender-specific scripting, materials, scene/export decisions.
- **Python implementer — Sol medium:** geographic-processing automation, validation, repeatable build helpers.
- **Luna / Terra — low:** source metadata, inventories, bounded research, mechanical changes, documentation.

Delegate narrow tasks with explicit file ownership and acceptance criteria. Never have multiple agents edit the same scene, road dataset, or output package concurrently. Prefer short results with paths, checks, and blockers; skip delegation when overhead exceeds the task. All agents inherit the installation and download approval rules.

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Forest canopy hides road and edges | Combine DTM, imagery, OSM, and ground-level references; manually validate alignment. |
| DTM does not describe road camber/bumps | Build a deliberate road surface; avoid claiming measured detail that is unavailable. |
| Data is old or footprint has gaps | Check route-area acquisition dates and actual valid pixels before production. |
| Coordinate/height mismatch | Record CRSs/origin; use control points; never silently mix height references. |
| Large rasters exceed download/storage budget | Obtain approval, inspect layout, clip early, use coarser distant terrain, avoid duplicate originals. |
| Linux/Windows/export incompatibility | Minimal export on Windows before detailed authoring; no need to install AC on Linux initially. |
| Point-to-point timing does not work in chosen mode | Validate session workflow during greybox; do not postpone until scenery is complete. |
| Forest detail is too costly in VR | Profile representative sections; prioritize LODs, transparency/shadows, and reduced scenery options. |
| Scope expands before road is playable | Gate scenery behind short prototype and full-route greybox acceptance. |

## 8. Deferred scope and remaining decisions

Deferred: reverse direction, traffic, racing AI, multiplayer, wet/night variants, extensive off-route exploration, and public release. Public release would require an additional complete asset/license review.

No further answer is needed to approve this plan as a roadmap. Before affected work begins, resolve:

- Which missing non-Python software may be installed?
- Are full BEV downloads approved if bounded access cannot keep the operation under 1 GB?
- Which season/road appearance should ground-level references represent?
- What monitor frame-rate target and Quest 2 connection/refresh mode should be used for acceptance testing?
- Can the user provide current roadside photographs or a safely recorded drive?

**Next executable step, after proceeding is agreed:** M0 tool inventory and M1 route/metadata verification. Do not jump directly to large downloads or detailed modeling.
