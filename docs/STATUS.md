v014 load test: user "the track does not load - it does not leave the loading screen". log.txt: all 3 KN5s, AI and physics load
(init3D 0.58 s), log cut mid-line while loading pit crew objects (unflushed, game closed). Diagnostic split installed:
exelberg_full_v014a = v013 + grass KN5 only, exelberg_full_v014b = v013 + v014 materials/textures only (build/diag_v014). Result: user "now all version work, the 14a, 14b and the full 14 in both directions"; last log = v014 full, loaded, CLEAN EXIT. First hang not reproduced, cause unknown (one-off). Test tracks v014a/v014b removed from the game afterwards (user OK).

v014 (INSTALLED both tracks, v012 removed from the game; NOT runtime-tested) = v013 + textures + 3D verge grass. User: "nicer textures for the gras
next to the road ... absolute flat" and "alternative textures for the road ... more realistic"; user runs plain AC on
Linux (no CSP/Content Manager), so only vanilla Kunos shaders are used (slot/property names taken from imola/Trento).
- `acquire_cc0_textures_v014.py` -> data/raw/textures_cc0_v014 (ambientCG CC0, 145.6 MB, sha256 ledger): Asphalt015,
  Asphalt023S, Asphalt031, Road006 (candidates; Asphalt015 chosen), Foliage002/006/008 (grass sprites).
- `v014_textures.py` -> data/processed/textures_v014: DXT1/DXT5 DDS with full mip chains (Pillow per level).
- `kn5_header.py`: KN5 v5 texture/material header rewrite, node section copied byte-for-byte (exact round trip).
- `v014_materials.py`: V002_asphalt / V002_gravel / 27 ortho ground materials (main) and V011_asphalt / V011_gravel
  (scenery) -> ksPerPixelMultiMap_NMDetail. Road/gravel UVs are world-planar 6 m (main) / 4 m (scenery) per unit;
  asphalt 6 m tile + 60 m wear/patch/crack-seal detail; ground detail 5 m tile + grass normal detail (blend 1.0).
  Detail-alpha semantics (diffuse alpha 0 = full detail) carried over from v004, still unverified in-game.
- `v014_grass.py` + `build_grass_v014.py` -> third KN5 `<..>_v014_grass.kn5` (MODEL_2): ~95k alpha-tested clumps per
  track (2 crossed double-sided quads), 3.4-9.5 m from the centreline, only on skin role GRASS (and 0.25 m inward),
  not on scenery junction/building footprints; 50 m chunks, lod_out 75 m, no shadows; ~760k tris, 44 MB.
- `package_full_track_v014.py` (19 files, ~358 MB per track; main/scenery node sections asserted identical),
  `install_full_track_v014.py`, `tests/test_v014.py` (also covers the v013 sign clearance).
Runtime unknowns: grass/LOD performance, how bright/contrasty the new detail layers look in AC lighting.

v013 (built, NOT installed): user "missplaced traffic sign on the road at the roundabout ... after turning right in the
first exit". Cause: v011_urban offsets signs from OSM carriageway centres (half width 2.25 m + 0.8 m); our 6 m road covers
part of the Exelbergstrasse splitter island, so island-side signs stood on the asphalt (reverse: entry-zebra sign 1.31 m
from the centreline; forward: exit-zebra sign 2.20 m). Fix `scripts/v013_scenery.py`: urban signs closer than 3.95 m are
pushed perpendicular out to 3.95 m (7 per track; geometry otherwise identical to v011, same tris). `build_scenery_v013.py`,
`package_full_track_v013.py` (= v012 + new scenery KN5), `install_full_track_v013.py`. Plot:
scratchpad signs_v013.png. No CSP found in the user's game folder (GrassFX in ext_config.ini is inactive).

# Current project status

## Latest: v012 — AI line + TV/replay cameras (exelberg_full_v012, exelberg_reverse_v012), INSTALLED 2026-11-15 (user-authorized) — NOT yet game-tested

v012 test: user "the ai line was off most of the time". Cause: the line sat exactly ON the asphalt (0.00 m); Kunos lines
sit 0.30 m (magione) / 0.38 m (trento-bondone) above the road, so the ideal line drawn from it was hidden by the road
surface. Fix: AI_LIFT 0.35 m (verified 0.350 m above every sampled road triangle); packages rebuilt; corrected fast_lane.ai
installed in both v012 folders (all files match the manifests).

Game folder cleanup (user request, 2026-11-15): all older Exelberg tracks (exelberg_full_v002-v011, exelberg_north_proto_v001,
exelberg_reverse_v011) removed from content/tracks; only the two v012 tracks remain installed. Old packages stay in build/.

User (v011 review): "test was good"; asked for TV-broadcast camera angles and an AI line.
- `scripts/v012_ai_cameras.py forward|reverse`: `ai/fast_lane.ai` from the road centreline (1.5 m points, driving order,
  version-7 layout incl. the 10 m nearest-point grid; format checked by re-parsing Kunos magione/trento-bondone/ks_drag
  files to their exact sizes). Speed profile 8 m/s^2 lateral, 3.5 accel, 7 braking, 45 m/s cap; centreline, not a
  racing line. Three camera sets (data/cameras.ini TV 1 broadcast 8-18 m off / 2.5-4.5 m high; cameras_1.ini TV 2 low
  trackside 6.5 m / 1-1.6 m; cameras_2.ini TV 3 high 20-35 m), contiguous IN/OUT 0..1, chosen greedily with line of
  sight against the ground skin, placed trees (crowns + max 12 m of forest below the canopy) and OSM buildings.
  Forward: 54 / 101 / 46 cameras; reverse: 54 / 100 / 45. No fallback holds.
- `scripts/package_full_track_v012.py`: v011 package + main KN5 renamed (root node patched, same length), models.ini,
  ui, README; scenery KN5 byte-identical. 18 files, ~293 MB each. Spawn 1.58 m beside the AI line at 10.5 m, heading
  dot 0.998. `scripts/install_full_track_v012.py forward|reverse [--install]` (dry-run default). Tests: 383 OK.
- Runtime unknowns: whether AC accepts the generated grid/extras (check log.txt), camera switching points, AI driving
  quality on the centreline. Guide: docs/FULL_TRACK_V012_TEST_GUIDE.md.

## v011 — forward exelberg_full_v011 + NEW reverse track exelberg_reverse_v011, INSTALLED 2026-11-15 (user-authorized) — NOT yet game-tested

User (v010 review): "test was good". Requests: (1) second track in the other direction, start where the screenshot
data/raw/Marswiese_start.png was taken, signs/crosswalks/green island as in the screenshots, 1st exit with a "Tulln"
sign (data/raw/Marswiese_start_1st_exit.png; Street View = reference only); (2) "2 corners where the chevron signs
are on the wrong side" before Dopplerhütte.
- Chevrons: inventory rows W011 (1113 m, logged R) and W015 (2318 m, logged L) have no bend of the logged direction
  in the snap window, so v005 fell back to the logged (= inner) side. v011 wraps chevron_series: contradiction ->
  outer side of the actual bend. Exactly these two series changed; test: no chevron on an inner side.
- Reverse geometry: `v011_reverse_extension.py` (forward parametrisation: old route + Exelbergstrasse to the branch
  split, then exit branch 689306072/26560097, ring 278650047, westbound 555726612 backwards; end 10 m behind the
  spawn, 12 m before the zebra). v010 stage scripts reused via env `V010_EXT=data/processed/extension_v011r`
  (route 15,886 m, min radius 11.8 m; patch watertight; 673 CHM trees).
- `build_full_track_v011.py` (V011_MODE forward|reverse): forward = v010 geometry renamed; reverse = spawns 10 m from
  the end facing reverse, right lane (+1.5 m), gates at 110 m (travel-left/right), FINISH/STOP boards reversed.
- `v011_textures.py` urban sign atlas; `v011_urban.py` OSM-placed zebras (6), bicycle squares, 21 sign posts,
  46 island shrubs, splitter-island keep-right + marker + Tulln board, deer warning; `v011_scenery.py forward|reverse`
  (reverse: chevrons/town signs face reverse traffic); `build_scenery_v011.py` (+V011_urban material).
  Compatible edits: v010 stage scripts read V010_EXT; `v010_scenery.main(out, prefix, hook)`.
- `package_full_track_v011.py forward|reverse`: both PASS (all skin triangles in the KN5, 417 untouched nodes
  identical to v009, gates 3.0 m, reverse spawn facing dot 0.99999, lateral 1.5 m); maps regenerated.
  Packages build/full_track_v011/{exelberg_full_v011 (260,954,414 B), exelberg_reverse_v011 (260,602,341 B)}, 15 files
  each. Installer `install_full_track_v011.py forward|reverse` dry-run OK. Tests: 377 OK.
  Guide: docs/FULL_TRACK_V011_TEST_GUIDE.md.

## Previous: v010 (= v009 + extension to the Neuwaldegg roundabout) INSTALLED 2026-11-15 (user-authorized) — game-tested OK by user ("test was good")

User (v009 review): "the curves are smooth now, works." Request: extend to 48.2401990264944, 16.276531758839184 —
"the 2nd exit of the roundabout should be the finish".
- Data: bounded BEV byte-range downloads into NEW ledgers data/raw/{terrain,surface_dsm,orthophoto}_v010 (~18 MB +
  ~3.7 MB metadata; hash-pinned older ledgers untouched): DTM/DSM/CHM 9 tiles, ortho 1024 m at 1 m/px.
- `v010_osm_extension.py`: OSM path old end -> Exelbergstrasse -> one-way entry branch -> ring (counter-clockwise)
  -> exit 2 (way 9873331), finish = projection of the user point (8.8 m away), +100 m run-off (before the Alsbach bridge).
  Note: its `ring_center_local_m` is the mean of the travelled ring nodes, NOT the ring centre; the real ring
  (circle fit in v010_scenery.py) is centre (5242.92, -3018.34), centreline radius 10.79 m; route stays at 10.4-10.9 m.
- `v010_route.py`: stations up to i_cut (60 m before the old end) identical to v009; v009-style fit for the rest,
  DTM profile sigma 4 m; 15,997 m total, finish at 15,896.5 m; min radius 8.0 m, max grade 5.7 %.
- Ground patch `v010_patch_domain.py` / `v010_patch_cdt.py` (Blender CDT) / `v010_patch_build.py`: 140 m corridor,
  3,732 v009 skin triangles replaced, watertight seam (0 open edges), harmonic height blend, apron slope <= 30 %.
- `v010_trees.py`: 190 v004 trees in the patch replaced by 740 CHM-detected trees (>= 7 m from the road).
- `build_full_track_v010.py` (v009 blend copy): cut + patch objects (1ROAD/1GRAVEL/1GRASS_X010, ortho DDS from
  `v010_textures.py`), walls L/R_X010 + new 1WALL_END, paint to 8 m before the ring, old warnings removed, FINISH/STOP
  boards, AC_TIME_0_L/R at the finish +-3 m, trees rebuilt. KN5 202 MB.
- `v010_scenery.py` + `build_scenery_v010.py`: v009 scenery on the v010 skin + roundabout ring/arms asphalt (visual),
  island kerb, buildings with extension-CHM fallback (309 buildings), no shrub band in the urban section.
  Small compatible edits: `v005_roadside.TREES` (shrub density source), `v006_buildings` tolerates off-skin buildings.
- `package_full_track_v010.py`: every one of 593,618 v010 skin triangles found in the KN5 (0 mm), 417 untouched
  physics nodes identical to v009, spawns unchanged, gates 3.0 m from the finish; map.png/outline/map.ini regenerated.
  Package build/full_track_v010/exelberg_full_v010 (15 files, 255,190,581 B). Installer dry-run OK. Tests: 363 OK.
  Guide: docs/FULL_TRACK_V010_TEST_GUIDE.md.

## Previous: v009 (= v008 + smoothed road curves) INSTALLED 2026-11-15 (user-authorized) — game-tested OK by user ("the curves are smooth now, works")

User (v008 review): v008 items 1–6 OK; "the roads seem to have some rough edges, which are noticable at the
turns". Cause: OSM way densified with straight 2 m steps between nodes (median spacing 8 m, p90 26 m) and only
sigma 2 m XY smoothing in v002 -> curves were chord polygons (curvature spikes at every OSM node).
- `scripts/v009_centerline.py` (.venv, scipy): penalised least squares through the 1,145 OSM nodes on a 0.5 m
  lattice (|x - node|^2 + 100*|x'''|^2), blended back to v008 over the first/last 25 m. XY only, Z per station
  unchanged. Shift vs v008 p50 0.07 / p99 0.53 / max 1.04 m; curvature TV(4 m) 14.4 -> 8.1; min radius 6.9 -> 7.2 m.
- `scripts/v009_field.py` (numpy only, also used inside Blender): exact ribbon coordinates (segment, t, offset)
  old -> new, full within 9 m, smoothstep fade to 0 at 30 m. 0 flipped skin/physics triangles.
- `scripts/build_full_track_v009.py`: copy of the v008 blend, every exported mesh XY-deformed, spawns at 10 m on the
  new line (moved 2 mm), gates moved 4 cm. `package_full_track_v009.py` proves every v008 physics triangle moved by the
  field matches one v009 triangle (<0.3 mm), heights unchanged. Scenery `v009_scenery.py` (posts moved by the field).
- Package build/full_track_v009/exelberg_full_v009 (15 files, 245,114,627 B). Installer dry-run OK.
  Guide: docs/FULL_TRACK_V009_TEST_GUIDE.md. Tests: 351 OK.

## Older: v008 (= v007 fixes + smoothed landscape) INSTALLED 2026-11-15 (user-authorized) — game-tested OK by user (items 1–6)

User (v007): "the terrain has some rough edges and is not smooth ... smooth the landscape a bit, especially the
elevations". Causes: v003 ground was FLAT-shaded (per-triangle normals on an 8 m mesh, up to ~30 deg jumps) and
the DTM-derived mesh has short-wavelength bumps.
- `scripts/v008_terrain.py` -> data/processed/terrain_v008/smoothed_skin.npz: z-only Taubin smoothing of GRASS
  vertices, weight 0 within 10 m of the centreline, full beyond 25 m; road/gravel/boundary vertices fixed; change
  soft-capped at 2 m (tanh) so real cuts/embankments survive. Crease angle p99 25.2 -> 12.5 deg, p90 6.7 -> 3.2.
- `scripts/build_full_track_v008.py`: v007 main changes + grass heights from the smoothed skin, smooth vertex
  normals on grass/gravel top faces, trees rebuilt with the v004 code/seed and shifted by the ground change at
  their base (22,632 of 22,904 moved, within +-1.9 m). KN5 193 MB (shared vertices; was 251 MB).
- Packager proves vs v004: road/gravel/wall triangles identical; grass XY/topology identical, heights changed
  only >= 10.09 m from the centreline (drivable strip and invisible walls at +-6 m untouched); spawn moved 15 m.
- Scenery `v008_scenery.py` (= v007 content placed on the smoothed skin; `v005_roadside.SKIN`),
  `build_scenery_v008.py`; previews `render_v008_previews.py` (v008 blend) -> data/processed/scenery_v008/previews/.
- Package build/full_track_v008/exelberg_full_v008/ (15 files, 245,163,452 B); installer dry-run OK; tests 341 OK.
- v007 (built, never installed) is superseded by v008.

## v007 BUILT 2026-11-15 — offline-validated, NOT installed, NOT game-tested

User's v006 review: "it works" + four corrections, all addressed:
1. Guide posts: Austrian Leitpflock after user photo (data/raw/Leitpflock-B16_4333.jpg): white body, black head
   + knob, dotted reflector plate on both traffic faces, blue wildlife reflector on the outer side (blue reflector
   taken from the photo, not verified per post). 822 posts at the v003 positions in the scenery KN5; the v003
   posts (VIS_POSTS, 195 objects) are no longer exported in the main KN5.
2. Red chevrons redrawn from user SVG data/raw/chevron_austria.svg (full red board, one big white chevron).
   Yellow/black boards unchanged.
3. Spawn (AC_PIT_0/AC_START_0/AC_HOTLAP_START_0) moved from arclength 25 m to 10 m (15.0 m; same lane offset,
   clearance, yaw); Königstetten sign (~28 m) now ahead of the car. Timing gates unchanged.
4. Missing roofs: every non-small building gets a pitched roof; L/T shapes via rectangle decomposition with
   cross-gables; ~35 deg assumed where the CHM shows no ridge. 16 flat roofs left, all small garages/sheds.
- Main KN5 re-exported by `scripts/build_full_track_v007.py` from the v004 blend (read-only, hash checked);
  package validator proves all 424 physics nodes are vertex/index-identical to v004.
- Scenery: `v007_textures.py` -> `v007_scenery.py` -> `build_scenery_v007.py` (227 objects, 496,062 tris);
  previews `render_v007_previews.py` -> data/processed/scenery_v007/previews/.
- Package build/full_track_v007/exelberg_full_v007/ (15 files, 303,494,846 B), installer
  `install_full_track_v007.py` dry-run OK. Tests 333 OK.

## v006 (buildings + sign fixes) INSTALLED 2026-11-15 (user-authorized) — NOT yet game-tested

- User asked to remove the junction barriers: `JUNC_BARRIER = False` in v006 drops the red/white barrier and its
  no-entry sign; side-road asphalt/gravel stubs stay. The invisible walls (main KN5) still keep cars on the route.
  Rebuilt: scenery KN5 166 objects, 443,782 tris; package 302,003,734 B; tests 321 OK; installed to
  content/tracks/exelberg_full_v006 (15 files).

- User review of v005 asked for: buildings; signs closer to the road; town signs black text on white with a
  blue frame; red curve boards with a white arrow on red. (Yellow/black boards kept: they exist on the real road.)
- `scripts/v006_textures.py` -> data/processed/textures_v006/ (corrected atlas, same cell layout; facade x4,
  roof x2). `scripts/v006_buildings.py` + `scripts/v006_scenery.py` (reuses v005_roadside via SIGN_INNER /
  PREFIX / AVOID / extra hooks; v005 output still regenerates byte-identically) -> data/processed/scenery_v006/.
- Signs: inner plate edge 4.4 m from the centreline (v005: posts at 6.4 m); still outside the 4.1 m white posts
  and inside the 6 m invisible wall, so the car cannot reach them.
- Buildings: 298 OSM footprints within 190 m, >= 7 m from the centreline, all on the ground skin. Heights from
  BEV CHM pixels inside each footprint (eave p25, ridge p95, clamped; 293 CHM-based). 208 gable roofs on
  near-rectangular footprints, 90 flat; generic procedural facades/roofs. Approximations, not surveyed models.
  Shrubs avoid building footprints; v004 trees already excluded buildings. No collision. LOD out 1500 m.
- `build_scenery_v006.py` (Blender 5.3) -> exports/full_track_v006/exelberg_v006_scenery.kn5
  (45.7 MB, 180 objects, 445,550 tris). Previews: `render_v006_previews.py` -> data/processed/scenery_v006/previews/.
- `package_full_track_v006.py` -> build/full_track_v006/exelberg_full_v006/ (15 files, 302,170,906 B); main KN5
  `exelberg_full_v006.kn5` byte-identical to v004 (named after the folder, see TRACK NOT FOUND below);
  replaces the v005 roadside KN5 rather than stacking on it. Installer `install_full_track_v006.py` is
  dry-run by default (dry run OK). tests: 319 OK (`tests/test_v006.py` adds 7).

## v005 (roadside) INSTALLED 2026-11-15 — user game-tested: loads and "looks good"

- Package `build/full_track_v005/exelberg_full_v005/` (15 files, 295,159,677 B; manifest
  `data/processed/full_track_package_v005/manifest.json`). Installer `scripts/install_full_track_v005.py`
  installed to content/tracks/exelberg_full_v005 (15 files, hashes verified while staging).
- First install failed in game: log.txt 'ERROR: exelberg_full_v005 : TRACK NOT FOUND' (main KN5 kept its
  v004 filename). Fixed by naming it exelberg_full_v005.kn5 (content unchanged); reinstalled 2026-11-15.
- Main KN5 = v004 KN5 byte-identical (sha checked). New visual-only second KN5
  `exelberg_v005_roadside.kn5` (39 MB, 156 meshes, 443,980 tris) via models.ini MODEL_1 — multi-model
  loading confirmed working in game (user, 2026-11-15). Detailed checklist items (guardrail stop, FPS, VR) not yet reported.
- Content: 15 guardrail runs / 1,270 m (rail face 5.9 m = at the 6 m invisible wall, deliberately not the
  real ~4.3 m), 84 signs (chevron series snapped to the outer side of the nearest matching bend), 52 OSM
  junction stubs each closed by a red/white boom beyond the wall, 9 parking pads, Dopplerhütte concrete
  parapet/railing, 2 fences, 8,074 edge shrubs, Richtfunkstation Exelberg (109 m, approximated shape).
- Pipeline: `v005_textures.py` -> `v005_roadside.py` (.venv) -> `build_roadside_v005.py` (Blender) ->
  `package_full_track_v005.py`; previews `render_v005_previews.py` -> data/processed/roadside_v005/previews/.
- Known limits: v003 white posts still stand in front of guardrail runs; sign texts/values partly
  assumed (flagged in placements.json); guardrail lengths estimated; no building models yet (v006).
  Tests: 305 pass. Guide: docs/FULL_TRACK_V005_TEST_GUIDE.md.

## v005 roadside inventory (2026-11-15)

- User tested v004 in-game: "it looks good" (subjective; LOD/perf/VR not separately reported).
- Roadside inventory (guardrails, chevrons, speed signs, junctions, buildings, parking pads) logged by chainage
  from private reference material (not part of this repository) into
  `data/processed/roadside_inventory/inventory_v2.csv` (90 items). Positions are approximate; guardrail
  lengths are lower bounds. Landmark requested by user: Richtfunkstation Exelberg
  (see docs/VISUAL_UPGRADE_PLAN.md). Notable: real red/white boom closing a forest track at ~8.7 km;
  precast concrete parapet at Dopplerhütte.

## v004 (vegetation) INSTALLED (user-authorized 2026-11-15) — user game-tested: looks good

Installed at `content/tracks/exelberg_full_v004` (14 files, 256,259,118 B, hashes verified
while staging). v001–v003 folders untouched. Direction decision: keep Königstetten→Marswiese;
a reverse layout may be added later (user choice a). 

User decisions: summer foliage; species need only be plausible; CSP allowed; ±400 m
BEV surface model approved and acquired (see DATA_SOURCES.md).

- **Road/collision unchanged:** built from a copy of `blender/exelberg_full_v003.blend`;
  independent KN5 check: all 424 v003 physics meshes identical (flags, vertices, indices),
  AC_PIT/START/HOTLAP/TIME helpers identical.
- **Trees from real canopy heights:** 22,904 trees/shrubs at CHM (DSM−DTM) maxima within
  7–195 m of the centerline, OSM buildings masked. 7,095 3D trees ≤45 m from road
  (~190 tris each, LOD out 180 m) + impostor LOD; 15,809 impostor trees (LOD out 1.5 km).
  Species: seeded beech 65 % / oak 25 % / conifer 10 % (not surveyed). OSM had no
  needleleaved polygons in the extracts.
- **Textures:** ambientCG CC0 leaves/bark/grass; leaf-cluster atlas, bark atlas,
  Blender-rendered impostor atlas; all DDS now carry full mip chains (v003 had none).
- **Ground:** 26 ortho materials → `ksPerPixelMultiMap` with tiling grass `txDetail`
  (multiply semantics per community docs; **unverified in-game**).
- **CSP:** `extension/ext_config.ini` with GrassFX on the ortho materials (untested values).
- KN5 254,986,998 B (just under the 256 MiB pipeline cap), 2,222,158 tris, 1,774 mesh
  nodes, 34 materials, 37 textures. Package `build/full_track_v004/exelberg_full_v004/`
  14 files, 256,259,118 B. Installer dry run OK. 291 offline tests pass.
- Previews (Blender approximations, not AC): `data/processed/full_track_scene_v004/driver_*.png`.
- Environment drift found and handled: system Python 3.14→3.15 (`.venv` upgraded in place,
  pinned wheels reinstalled, Pillow 12.3.0 added via `requirements-v004.txt`); Blender
  flatpak is now 5.3.0 (v003 was built with 5.2.0).
- Provenance: the ±400 m run had extended the DTM ledger; original
  `data/raw/terrain/operation.json` restored byte-exactly (earlier manifests pin it),
  extended copy kept as `operation_v004_extended.json`.
- Known limits / next: size (trim hero density or texture sizes), forest sometimes starts
  10–15 m back from road (CHM dominants only; add edge/understory fill), ground shader
  needs in-game tuning, guardrails/signs/junctions/buildings are later releases.
  Test guide: `docs/FULL_TRACK_V004_TEST_GUIDE.md`.

## Previous: v003 is installed — not yet game-tested

Recovered after the canceled API task. No partial landscape files existed; the
original orthophoto ledger/cache was intact. Work resumed without restarting its
budget or altering installed v002.

After explicit user approval, installed **Exelberg Full v003 (collision + ortho)**
at the local game's `content/tracks/exelberg_full_v003`. All **46 files /
152,238,504 bytes** match the package hashes. Installed v001/v002 files were also
rechecked and remain unchanged. Evidence:
`data/processed/full_track_package_v003/installation.json`.
No game launch, settings change or live-Blender edit occurred.

### Changes requested by user

- Full **15.213 km designed road**, two provisional **3 m lanes**; original full
  Königstetten → Marswiese source endpoints retained.
- Asphalt geometry/UV/texture, white paint and the user-confirmed successful v002
  spawn yaw preserved exactly.
- Removed rendered yellow/black walls. New **invisible physics-only strips at
  ±6 m from centerline**, i.e. **3 m beyond each nominal asphalt edge**.
- Walls extend below actual adjacent ground and above ground/road, with inward
  faces, active/visible=1, renderable/shadows/transparent=0. This follows stock
  physical-wall evidence; actual AC body contact is **not validated**.
- Removed ground undersides, skirts and internal chunk caps. Road/gravel/terrain
  now form a top-only contact skin instead of separate closed solids.
- Reachable apron redesigned; slope cap **30%** is provisional, not a surveyed or
  safe-at-speed guarantee. Derived terrain edits range −13.217…+12.731 m, RMS
  0.682 m. These substantial local scenic edits are explicit design, not a source
  terrain correction. Raw data are preserved.
- **822 visual-only posts**, nominal **33 m** arclength grid, 411 per side. 98
  candidate placements skipped near mapped possible connections. Simple Austrian-
  style white/black posts; reflector specification and exact locations unverified.
- **26 licensed BEV orthophoto terrain textures**, 2 m/texel, north-up UVs.
  They improve land-cover context, not 3D buildings or individual-tree realism.
- Existing **4,616 low-poly forest trees** retained and regrounded; appearance is
  still provisional. No Street View imagery or commercial game assets extracted.

### Deliverables and checks

- Scene: `blender/exelberg_full_v003.blend` — 28,906,188 bytes.
- KN5: `exports/full_track_v003/exelberg_full_v003.kn5` — 124,593,102 bytes.
- Preview: `data/processed/full_track_scene_v003/driver.png`.
- Post detail: `data/processed/full_track_scene_v003/post_detail.png`.
- Package: `build/full_track_v003/exelberg_full_v003/` — **46 files, 152,238,504 bytes**.
- ZIP alongside: **60,172,031 bytes**.
- **287 offline tests passed**. Actual isolated Blender build/render/save/reload,
  independent geometry/UV/material/helper export checks, role-specific collision
  audits, package hashes, ZIP inventory and installer tests passed.
- **935,234 triangles**, 1,338 mesh nodes, 33 materials/textures, 612,878 collision-
  intended triangles. v002 had 1,928,784 triangles. v003 performance/VR unmeasured.
- Zero detected positive-area ground contact overlaps/internal vertical caps;
  six endpoint T-junction edges and sub-mm float32 residue remain documented.
  This is not proof that the car-launch problem is fixed.
- Full wall ground coverage checked geometrically, including triangle interiors.
  Source/runtime semantics still need actual low-speed tire/body testing.

Evidence: [collision audit](validation/V002_COLLISION_AUDIT.md),
[scene validation](validation/FULL_TRACK_V003.md),
[orthophoto preparation](validation/LANDSCAPE_ORTHOS_V003.md),
[package validation](validation/FULL_TRACK_PACKAGE_V003.md),
[test guide](FULL_TRACK_V003_TEST_GUIDE.md).

## Actual user feedback — keep separate from static checks

- Northern v001 loaded but spawned backwards and allowed mountain falls.
- Full v002 loads, **spawn direction is correct**, performance is fine and the
  asphalt texture is fine.
- User can drive through the side barriers and sometimes the car flies away.
  Static audit found under-wall gaps up to ~1.97 m and internal opposed caps;
  these are credible causes, **not runtime-proved explanations**.
- The user has not yet identified the car/location/contact circumstances of the
  launches. Request those if v003 still reproduces them; do not assume a car fault.
- No v003 runtime feedback yet. Preserve v002 for comparison.

## Geographic/provenance limits

- Source route: ~15.205 km spherical, 15.226 km projected; designed ~15.213 km after
  audited smoothing. Metric authoring origin **(589500,5346800,300) m**, EPSG:25833;
  local X east, Y north, Z up. Product-documented orthometric height EPSG:9274.
- BEV 1 m DTM is bare earth, general stated height accuracy ±0.50 m, not asphalt
  survey. Source dates, exact road widths, camber and paint still need reference.
- Known raw dip near source km 9.589 remains in the source. Designed-road bridge
  over 9578–9602 m retains the explicitly provisional +2.508 m correction.
- Trees are constrained by mapped forest union/hole policy, not measured individuals;
  source role/topology assumptions are documented in the forest report.
- Orthophoto operation continued **the same 200 MB ledger**: new body transfer
  **59,159,923 bytes**, cumulative **67,017,250 bytes**. No full 12.9 GB TIFF.
  Source 20 cm imagery resampled to 2 m backdrop; approximate 1.5 m horizontal
  operation accuracy, semantic image nodata/capture dates unverified.
- Orthophotos can show canopy/roof/shadow colours on the ground; they do not create
  3D trees/buildings or validate asphalt heights. Street View is reference-only
  unless suitable rights are established; no extracted textures/assets used.
- Terrain/imagery © BEV CC BY 4.0; route/forest © OpenStreetMap contributors ODbL.
  See [source register](DATA_SOURCES.md).

## Tools and operating limits

Blender 5.2.0 LTS and user-approved pinned KN5 Studio 2.6.0 are used in separate
headless processes. No installed third-party source/preferences were patched.
Python dependencies remain in `.venv`; no new software was installed this stage.
Preserve any unsaved live Blender scene. New downloads >1 GB and additional
non-Python software require user approval.

Local game:
`/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa`.
No CSP dependency or automatic Steam/Proton/global configuration fixes introduced.

## Next action

1. v003 is installed and hash-verified alongside v002. Do not rerun the installer
   over it: the existing destination intentionally refuses. Keep older versions
   for runtime comparison.
2. User tests solo Practice at low speed: spawn/reset, gentle tire/body contact
   with invisible strips on both sides, old gap locations, apron and chunk seams.
   Invisible walls are not a high-speed containment guarantee.
3. If a launch/fall persists, record **car, approximate chainage/location, speed,
   whether on asphalt/shoulder or touching a wall, and a screenshot/replay**.
4. Full-route drive, textures/culling, braking and performance regression, then
   timing/restarts as a separate gate. Finish fixture retains ~300 m runout;
   neither stopping distance nor A2B timing is certified. VR remains untested.
5. Continue realistic scenic assets and measured references after collision
   regression is understood. Ground imagery alone is not final scenery fidelity.
