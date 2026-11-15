# AC solo Practice package v001 — offline validation

## Result and scope

**PASS offline packaging/static checks; NOT installed, launched, visually inspected,
or game-validated.** No network, downloads, software installation, Blender execution,
live GUI, source-scene edits, game writes or global preference changes occurred.
Temporary fake game trees were used for installer write tests only.

Track ID: **`exelberg_north_proto_v001`**. This is the northern source-chainage
1000–2500 m subset, designed XY length **1495.738982 m**, not the full 15.2 km route.
The full-route endpoints and project scope are unchanged.

## Outputs and integrity

- Folder: `build/ac_test_v001/exelberg_north_proto_v001/`
- Archive: `build/ac_test_v001/exelberg_north_proto_v001.zip`
- Manifest: `data/processed/ac_package/manifest.json`
- Builder / installer: `scripts/package_ac_test.py`, `scripts/install_ac_test.py`
- Tests: `tests/test_package_ac_test.py`, `tests/test_install_ac_test.py`

**16 package files, 8,216,815 uncompressed bytes.** ZIP: **5,358,701 bytes**, SHA256
`494c092f0e33511c16c11000b397e0f84f649b1bf7f446c05fb547babb6658b3`.
ZIP entries have exactly one top directory, the track ID; payloads were reread and
compared with the complete manifest allowlist. Manifest lists every package file's
size/SHA256, totals, ZIP hash/provenance, source manifest, four source assets,
design-station data and builder provenance. It lives outside the payload to avoid
self-hash recursion. Hashes detect corruption, not malicious replacement of both
manifest and payload; retain this trusted project manifest with the transfer.

Builder consumes only the scene manifest's exact KN5 and three DDS output entries.
It verifies their hashes, embeds no scripts/vendor/game assets, and copies DDS into
`texture/` only after checking exact equality with the KN5's embedded payloads.
No recursive export-directory copying. Original scenes and failed exports excluded.
Both build/evidence roots are exclusive reservations: reruns refuse even partial
outputs. Use reviewed new-version paths for another build, not force/overwrite.

## Package choices

- `models.ini`: only MODEL_0, exact KN5 filename, zero position and rotation.
- `data/surfaces.ini`: explicit ROAD/GRAVEL/GRASS keys and manifest frictions
  1.0/0.7/0.6, valid-track 1/0/0, pitlane 0 throughout. Zero roughness, vibration,
  damping and dirt are **provisional unmeasured physics**, not calibrated values.
- `ui/ui_track.json`: Austria, Königstetten, 1496 m, one pitbox,
  A2B/Hillclimb/prototype tags. These describe the candidate, not proven timing.
- Original schematic `ui/preview.png`, `ui/outline.png`, `map.png`, generated from
  the project's checksum-verified designed stations. Preview is **not a game
  screenshot or visual acceptance render**. Green/red mark section start/end.
- `data/lighting.ini`: simple own provisional daylight sun parameters.
- No CSP configs/dependency, cameras, opponents, recorded AI or racing workflow.
- `README.txt` and `ATTRIBUTION.txt`: safety, limitations, BEV CC BY 4.0,
  OpenStreetMap ODbL, adaptation provenance and exact-folder rollback.

### Map registration

Map bounds derive from independently parsed **KN5 road vertices**, not generic
numbers. Design stations are converted Blender XY → KN5 XZ = (X,−Y). North is
negative KN5 Z; PNG row increases with KN5 Z, so this is north-up.

`data/map.ini` and the 1024×1024 raster share:

```text
SCALE_FACTOR=0.5095840111039834 metres/pixel
X_OFFSET=3551.15478515625
Z_OFFSET=3335.47412109375
u=(KN5_X+X_OFFSET)/SCALE_FACTOR
v=(KN5_Z+Z_OFFSET)/SCALE_FACTOR
```

Square world extent is centered on road bounds, with at least 25 m edge padding;
the raster uses indices 0–1023. Padding is already included in offsets: INI
MARGIN=0. Tests verify north/east direction and inverse registration. Outline and
preview use their own 512×512 transform. Actual engine map/UI interpretation still
needs runtime confirmation.

### Empty AI hypothesis

Read-only bounded metadata confirmation of stock Drift's `ai/fast_lane.ai` and
`ai/pit_lane.ai`: both exactly 12 bytes, little-endian uint32 **(3,0,0)**.
Evidence: `data/processed/ac_package/checks.json`. Package files are newly generated
`struct.pack('<III', 3, 0, 0)` headers, **not copied stock files**. They contain no
recorded path or opponents. Matching an empty stock fixture is an **unvalidated
solo Practice compatibility hypothesis**, not proof that our track will load or
support hotlap/timing. No Trento AI or artwork was copied.

## Checks actually run

All Python commands used the project `.venv`, with bytecode writing disabled.

```sh
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python scripts/package_ac_test.py
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python scripts/build_ac_test_scene.py --validate-only
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python scripts/install_ac_test.py
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python -m unittest discover -s tests -v
```

- **164 tests PASS**, including 18 new package/installer tests.
- Independent KN5 parser: exact EOF, 12 unique nodes, five meshes, 230,400 triangles,
  uint16 vertex/index bounds, explicit surface keys/hierarchy, finite geometry,
  identity wrappers, five helper transforms, unique AC_START_0 grid and three
  `ksPerPixel` texture bindings/payloads PASS.
- Existing scene **read-only `--validate-only` PASS**: original expected oriented
  triangle/UV multisets, prior geometry streams and bounded tangent differences,
  helper axes and source-output checksums. This command does not invoke Blender.
- Actual Steam-path installer **DRY_RUN PASS**, target absent before/after:
  `/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa/content/tracks/exelberg_north_proto_v001`.
- No-overwrite package rerun intentionally exits 1 before writes.
- Installer temporary-tree tests cover installation, existing-destination refusal,
  corruption, extra/missing/duplicate allowlists, traversal, source/target/parent
  symlinks (including dangling), staging-root/child symlinks, permitted Steam-root
  alias, injected partial-copy/publish rollback and concurrent destination refusal.

Logs: `scene_validation.json`, `dry_run.json`, `tests.log`, `checks.json`,
`no_overwrite.log` under `data/processed/ac_package/`.

## Installer safety and open gates

Default is dry-run. Only explicit `--install` enables writes, and **was not run
against the actual game**. Existing Steam-root symlink is resolved; content/tracks
children, source children and staging accesses use no-follow directory/file opens.
Complete exact allowlist and hashes are validated before creating any game files.
Payload is held in memory, staged exclusively in a random private child of tracks,
verified, then atomically published with Linux `renameat2(RENAME_NOREPLACE)`.
No overwrite fallback. Unsupported atomic no-replace platforms fail closed.
Rollback on failure removes only the installer's own verified staging folder;
a pre-existing target/stage or concurrent destination is preserved.

**Runtime is the remaining blocker.** Trento TIME_0_L/R is a finish-stage fixture
only; timer start/results/restart remain unverified. Width, flat camber and grip
are assumed. Collision-intended lowered terrain retains a trench (up to 3.243515 m),
not joined safe verges. Spawn +0.4 m on a grade is not actual car clearance proof.
The 15 m finish run-out is **not braking distance**. Begin at walking speed; slow
well before the finish. No geometry fixes were attempted in packaging.
See [LOCAL_TEST_GUIDE](../LOCAL_TEST_GUIDE.md) for the user-controlled next step.
