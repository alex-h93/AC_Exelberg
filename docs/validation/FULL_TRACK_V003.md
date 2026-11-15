# FULL v003 — offline collision / scenery / posts candidate

**PASS offline; not deployed or game-validated.** Installed v002 and the user's GUI/preferences remain unchanged. The user's successful v002 spawn, performance and asphalt feedback is preserved as source evidence, not re-tested here. No network, download, installation, vendor patch, game launch or GUI bridge was used.

## Deliverables

- `blender/exelberg_full_v003.blend` — fresh editable scene, 28,906,188 bytes.
- `exports/full_track_v003/exelberg_full_v003.kn5` — **124,593,102 bytes**, SHA-256 `256b714965983f71d14debed9a81609ce603a31d4d24f76ad0adbf8e730c020b`.
- `data/processed/full_track_scene_v003/manifest.json` — authoritative external contract, explicit asset paths, hashes, materials, flags, four surface keys, helpers, UV tables and separate-package plan. Embedded Blender contract text is a prepared/pre-export snapshot, not the final evidence ledger.
- New builder, geometry/repair, independent-reader and audit helpers under `scripts/*v003*.py`; `tests/test_full_track_v003.py`.

All unsuccessful/intermediate assets and logs are retained under owned `failed_*` folders. **Never glob these into a package.** Package only the manifest's explicit KN5 allowlist; DDS images are embedded. No package, game folder or main-status document was changed.

## Geometry and preservation

Full source chainage **0–15,226.292 m**, designed road **15,212.525 m**, two provisional 3 m lanes. Exact v002 oriented asphalt XYZ **and corner UV** are retained; asphalt DDS is byte-identical. Paint geometry/UVs, all five helper transforms (including the successful reversed spawn yaw), raw references and the v002 DTM-dip bridge are preserved. A 2,045-file before/after hash snapshot includes v002/source assets, vendor/install checks, the legacy parser, installed content and recorded settings.

Independent first-half-vertex / all-indices-below-half extraction verified original slab TOP counts **before apron edits**:

| Role | Extracted v002 tops | Final v003 contact triangles |
|---|---:|---:|
| ROAD | 32,620 | 32,620 |
| GRAVEL | 77,215 | 41,481 |
| GRASS | 503,956 | 506,153 |

Bottoms, skirts and internal spatial caps are not exported. One shared open contact skin is partitioned without extrusion/reclosure. Blender's constrained Delaunay rebuild keeps original terrain cell boundaries/diagonals, followed by topology-safe 8 mm micro-edge collapse, within-cell needle retriangulation and one start-cap fan dissolve. Immutable asphalt triangles are restored exactly after triangulation. Terrain material ownership follows original terrain source-cell tile indices, not centroid-nearest orthophotos.

The existing 3.75 m shoulder contour controls a harmonic apron through the ±6 m containment envelope. Reachable gradients are projected to a provisional **30%** maximum; this is not surveyed verge geometry. A natural boundary prevents nearby opposing hairpin elevations from pulling the reachable apron downhill. Outside containment, a provisional profile-based extension fades back to v002 derived terrain over 20–40 m. Derived vertex Z changes span **−13.217…+12.731 m**, RMS **0.682 m**, with per-vertex XYZ/deltas retained in `contact_skin.npz`. These substantial scenic edits are explicit design, not imagery-based terrain correction. Raw inputs are untouched.

Independent contact audit:

- **580,254** upward ground triangles; zero inverted, duplicate, vertical/internal-cap or >2-incidence edges.
- **Zero positive-area contact intersections** after 1,523,373 binned bounding-box candidate tests; reporting floor 1e−10 m².
- Minimum altitude **2.856 mm**, minimum 3D area **4.319e−5 m²**; maximum XY aspect ratio **992.73**, reachable **439.67**. Numerical rejection limits are altitude <1 mm or aspect ≥1,000, not AC-engine guarantees.
- Maximum reachable gradient **0.300008** (approximately 16.7°); asphalt remains unchanged.
- Six topological endpoint T-junction edges remain on the unsplit immutable asphalt end. Both-side 2 mm probes find ground throughout; these are open-skin seams, not caps. Total XY area differs from the original 13,304,640 m² valid-cell footprint by **−0.000491 m²** of float32 endpoint residue. Exact mathematical watertightness is not claimed.

## Containment and finish

Inward, single-layer triangle strips at **left +6 m / right −6 m**: exactly 3 m beyond nominal asphalt edges, with float32 coordinate precision. No backfaces, roofs, undersides or chunk caps. Two additional inward single-shell endpoint closures provide containment.

Actual KN5 flags for every `1WALL_*` node:

`active=1, visible=1, renderable=0, cast_shadows=0, transparent=0, layer=0`.

Surface token **WALL**; no invented INI collision switch. ROAD/GRAVEL/GRASS/WALL friction remains 1.0/0.7/0.6/0.6, only ROAD valid, pitlane/damping/sinusoidal roughness/vibration zero. Ground is renderable; posts/trees/paint are non-digit visual names.

Full adjacent final-face min/max bounds conservatively enclose strip interiors, not just road Z. Five samples per segment, **81,550** total, give minimum burial **1.010 m** and clearance above ground/road **3.049 m**. Actual Blender BVH checked **228,368** wall triangle vertex/centroid/edge-interior samples without missing ground. Actual exported normals are inward, including both endpoints; minimum side inward dot **0.5494**. No renderable yellow/black wall mesh/material survives.

Finish uses the unchanged final **300 m of physical asphalt** after the existing timing gate, BRAKE signs at 300/150 m and STOP at 60 m; no visible warning stripe or above-road physical obstacle precedes the invisible endpoint wall. The former 0.45 m wall inset is gone. Braking adequacy, body contact and A2B workflow still require runtime testing; no high-speed containment guarantee is made.

## Posts, forest and landscape

**822** visual-only posts: **411 per side**, offsets ±4.1 m, grounded on actual final apron, 1.1 m nominal height, designed-arclength grid **33 m**. **98** candidate placements were skipped around possible driveable connections identified from existing OSM highway-way endpoints (within 9 m of route, ±12 m along-route exclusion, conservative both sides). Exact placements, gaps and connection controls are in `posts.json`; this heuristic cannot establish complete junction coverage.

Simple white posts, black bands and pale reflectors are nominal Austrian-style aids, **not measured furniture or RVS/legal compliance**. Reflector colour requirements remain unverified. All **4,616** original trees preserve XY, faces, chunk identities and procedural shape seed; all were sampled against final ground, **2,021** moved by >1 mm. Tree locations/species are not surveyed.

All **26 north-up 2 m orthophotos** are integrated across 159 editable terrain mesh parts and 26 UV-table entries. UVs use eastward u / northward Blender v, then **(u,1−v)** in KN5; actual bounds are [0,1]. Excluded RGB padding is edge-extended only for filtering, never terrain creation or colour correction. **182 actual DDS RGB/coordinate controls** match ungraded source PNG values exactly. Actual material node/image bindings and DDS dimensions are recorded. Canopy, roofs, shadows and the source's approximate 1.5 m transform accuracy remain limitations; close-road imagery is not asphalt survey detail.

## Execution and export evidence

Actual factory/background **Blender 5.2.0 LTS**, CPU Cycles, eight samples: final scene/export plus **driver, overview and post-detail 1280×800 renders**, saved-copy reload, **105.818 s**. All three final images were opened and visually reviewed: asphalt/paint remain recognizable, posts are visible, orthophoto landscape is present, and yellow/black walls are absent. Procedural trees and low-resolution ground are visibly provisional.

Independent actual KN5 parse and exact full oriented XYZ+corner-UV comparison passed for every created mesh:

- **1,344 nodes**, **1,338 mesh nodes**, **935,234 triangles**.
- **2,080,389 exported vertices**, maximum **49,110 per node**, uint16-safe.
- **612,878 collision-intended triangles**, including **32,624 wall triangles**.
- **33 materials / 33 textures**, **27,332,864 embedded DDS bytes**.
- 256 MiB file, 4,096-node, 128-material/texture hard ceilings; per-texture ceiling 8 MiB.

The old sealed validator remains **byte-for-byte unchanged**. A new local reader entrypoint reuses its independent Reader, with unchanged default asset-count caps of 32 and explicit bounded opt-in to 128. The original tests remain unmodified. The existing corner/normal adapter and vendor writer are unchanged; no third-party patch.

`PYTHONDONTWRITEBYTECODE=1 timeout 240s .venv/bin/python -m unittest discover -s tests -q`: **257 tests passed in 53.176 s**. The expected legacy CLI refusal message in the log belongs to a passing test, not a failed build.

## Reproduction / remaining gates

Fresh destinations only; preserve previous attempts before rerunning:

1. Factory-headless Blender: `scripts/full_track_v003_repair.py` (bounded 240 s).
2. `.venv/bin/python scripts/build_full_track_v003.py --prepare`.
3. Factory-headless Blender: `scripts/build_full_track_v003.py -- --build` (bounded 900 s).
4. `.venv/bin/python scripts/audit_full_track_v003.py`, then builder `--validate`.
5. Full tests (240 s), documentation, builder `--finalize`; `--check` is read-only.

**Ready for a separate offline package, not installed/playable acceptance.** Remaining authorized-runtime checks: wheel/body wall contact from both lanes; original v002 gap/burial chainages; verge recovery and seam launches; finish braking/end containment; spawn settling/restart/A2B timing; full-route texture/LOD/culling and performance regression; Quest 2 VR. This work does **not** establish that the user's game collision problem is fixed.
