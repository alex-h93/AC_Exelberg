# Full track v003 — offline package validation

**PASS offline packaging. Not deployed, launched or game-validated.** No network, downloads, installs, Blender execution, live GUI, preference saves or game writes occurred. Installer commit tests use isolated temporary fixture game directories only. Original v001/v002, exports, status and source-proof files were not edited.

## Artifacts

| Artifact | Size / count |
| --- | --- |
| `build/full_track_v003/exelberg_full_v003/` | **152,238,504 bytes, 46 files** |
| `build/full_track_v003/exelberg_full_v003.zip` | **60,172,031 bytes, 46 entries** |
| Packaged KN5 | **124,593,102 bytes** |
| DDS backups under `texture/` | **33 files, 27,332,864 bytes** |

ZIP SHA-256: `e3d2145f8acc5052ac532660f344666527320b479f7bc8555da6b39e37fd7825`.

KN5 SHA-256: `256b714965983f71d14debed9a81609ce603a31d4d24f76ad0adbf8e730c020b`.

Integrity/provenance ledger: `data/processed/full_track_package_v003/manifest.json`. It records per-file sizes/SHA-256, exact source records, authoritative scene manifest, parser/helper/builder/installer hashes, source collision evidence, route-array digest, map registration, preview provenance, timing and spawn contracts. Verification logs remain outside the playable folder and ZIP.

## Allowlist and independent checks

The builder reads `data/processed/full_track_scene_v003/manifest.json`, not an embedded authoring snapshot. It copies exactly the explicit KN5 record plus the 33 explicit DDS output records. No recursive export copy/glob: failed attempts, debug files, `.blend`, source NPZ/geodata, scripts and source evidence are excluded. The archive has only the exact `exelberg_full_v003/` top-level folder and 46 allowlisted files, with every entry independently streamed and hashed.

`full_track_v003_kn5.parse` reuses the sealed independent Reader; bounded opt-in is explicit: 256 MiB file, 4,096 nodes, 8 MiB per texture, 128 materials/textures. Default asset-count limits remain 32; the old validator and vendor code are unchanged. Actual parse: **1,344 nodes, 1,338 mesh nodes, 935,234 triangles, 33 materials/33 textures**. All 33 embedded DDS payloads match their standalone backups byte-for-byte: 26 BEV orthos, five retained procedural asphalt/gravel/bark/canopy/white textures and two post textures. Material shader/bindings reference packaged textures.

### Role contract — never blanket-renderable

| Role | Mesh nodes | Triangles | Renderable / shadows |
| --- | ---: | ---: | --- |
| Upward TOP-only contact skin | 292 | 580,254 | 1 / 1 |
| Inward open wall shell | 132 | 32,624 | **0 / 0** |
| Non-digit visual-only scenery | 914 | 322,356 | 1 / 1 |

Every mesh is checked against role-specific flags. Walls require **active=1, visible=1, renderable=0, cast_shadows=0, transparent=0, layer=0**. Ground is upward-only in the actual exported triangle coordinates; unexpected vertical caps, reversed/underside faces or non-role collision nodes are rejected. Exact digit-prefixed collision inventory maps to exactly **KEY=ROAD/GRAVEL/GRASS/WALL**; triangle counts **32,620 / 41,481 / 506,153 / 32,624**. Frictions remain **1.0 / 0.7 / 0.6 / 0.6**, only ROAD valid, no pitlane, damping, synthetic roughness or vibration.

The upstream hashed ground audit is reverified: zero inverted/duplicate faces, >2-incidence edges or positive-area contact intersections; all 580,254 ground triangles upward. The source evidence establishes top extraction and exact oriented XYZ/corner-UV preservation, including immutable v002 asphalt. Its finite numerical tolerances and six endpoint T-junctions remain limitations, not exact watertightness or AC solver guarantees. The package does not rerun Blender geometry construction or recharacterize this as runtime collision proof. See [FULL_TRACK_V003.md](FULL_TRACK_V003.md).

## Route, UI and provenance

- UI: **Exelberg Full v003 (collision + ortho)**. Königstetten → Marswiese, full **15,212.525 m designed road**, original source chainage **0–15,226.292 m**, two provisional 3 m lanes / 6 m, one pit, solo A2B.
- All five actual helper matrices are verified against the v003 contract and the hashed v002 manifest; successful reversed yaw is preserved.
- Own north-up map/outline are generated from `designed_xyz_m` in v003's `v002_reference.npz`, cryptographically verified against the authoritative source record. Array dtype, shape and bytes are identical to v002's designed road. Tests recompute maps and registration.
- UI preview is the actual v003 offline `driver.png`, nearest-neighbour resized **1280×800 → 640×400**; pixels are tested, not substituted schematic art. No new render or visual inspection was performed during packaging.
- New own `(3,0,0)` empty AI headers retain the solo Practice format v002 already loads. No AI opponents or required CSP configuration.
- Packaged `ATTRIBUTION.txt` includes BEV CC BY 4.0, source DOI/URL, unknown local flight date, transformations/resampling, 2 m backdrop-pixel and approximate 1.5 m transform-accuracy caveats. Orthophotos are imagery, not road/terrain measurements. OSM attribution covers route and forest masks; procedural trees are not individual surveyed trees. The 822 posts use a nominal 33 m grid and heuristic connection gaps, not measured/RVS-verified furniture.

## Safety / runtime boundary

Invisible invented walls lie ±6 m from centreline, **3 m beyond nominal road edges**. Low-speed wheel/body contact from both lanes, old gap/burial sites, shoulder recovery and road chunk seams remain required. **Car flying/falling is not proven fixed.** Provisional apron slope cap 30%, terrain edits and surface physics are uncalibrated.

Finish remains at designed 14,912.525 m with **300 m physical runout**. BRAKE signs at 300/150 m and STOP at 60 m precede the invisible endpoint shell. Neither stopping adequacy nor AC timer/session/results/restart behavior is proven. Spawn, full-route collision/texture/culling, performance and Quest 2 VR require separately authorized runtime tests.

[FULL_TRACK_V003_TEST_GUIDE.md](../FULL_TRACK_V003_TEST_GUIDE.md) requires explicit deployment/launch permission and asks for the **specific car and source chainage/location** of earlier failures before launch. Preserve current preferences and v001/v002 throughout.

## Installer and executed checks

New `scripts/install_full_track_v003.py` retains v002's descriptor-relative, no-follow safety procedure with an isolated tuple/frozenset v003 profile, not runtime mutation of legacy module globals. Only stateless legacy safety primitives are shared. It defaults to dry-run, requires explicit `--install`, refuses existing destinations, validates exact source inventory/hashes, streams bounded immutable snapshots, verifies staging and atomically publishes without replacement. Maximum **512,000,000 bytes/file / 600,000,000 bytes aggregate**. Source/child symlinks and unexpected directories are refused; the configured Steam-root alias alone may resolve. No global settings are modified.

Executed:

1. `PYTHONDONTWRITEBYTECODE=1 timeout 240s .venv/bin/python scripts/package_full_track_v003.py` — PASS, fresh outputs.
2. `PYTHONDONTWRITEBYTECODE=1 timeout 240s .venv/bin/python -m unittest discover -s tests -q` — **287 tests passed in 54.582 s**, including 30 new package tests. The legacy CLI refusal text is expected from a passing refusal test. Evidence: `data/processed/full_track_package_v003/tests.log`.
3. Actual default-root **dry-run only** — PASS; destination `/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa/content/tracks/exelberg_full_v003` absent, 46 files / 152,238,504 bytes. Evidence: `default_dry_run.json` in the package evidence directory.
4. Installed **v002 read-only** full allowlist verification — all **20 files** match its package manifest's size/SHA-256. Evidence: `installed_v002_read_only.json`.
5. Read-only rehash of the existing v003 source-preservation snapshot — **2,045 protected files, zero mismatches**, including original sources, old builds/exports, installed content and recorded preferences. Evidence: `preservation_check.json`. Original snapshot unchanged.

Regression tests exercise actual KN5 parse, role/triangle counts, wall flag mutations (including the forbidden v002-style renderable/shadow flags), inverted ground, helper changes, embedded DDS mismatch, default parser refusal, cryptographic route equality, exact ZIP/file inventories, source tampering/caps/path traversal/symlinks, destination races, immutable snapshots, no-overwrite and preservation of both prior track IDs and preferences in fixtures.

**Blockers:** no offline packaging blocker. Runtime collision fix, braking adequacy, complete AC A2B timing workflow, performance regression and VR remain unknown. No deployment/launch authorization was exercised.
