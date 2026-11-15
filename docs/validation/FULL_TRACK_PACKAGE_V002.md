# Full track package v002 — offline validation

## Delivery

- Track folder: `build/full_track_v002/exelberg_full_v002/`
- Archive: `build/full_track_v002/exelberg_full_v002.zip`
- File/source/ZIP SHA256 and byte-count evidence:
  `data/processed/full_track_package_v002/manifest.json`
- **20 package files, 235,165,128 bytes**; ZIP **94,299,634 bytes**, 20 entries.
- ZIP SHA256: `174aae003c921789eea42508b44b823a36a04582a2a12c6771a1af50b24ce0a2`.
- KN5: **232,993,555 bytes**;
  SHA256 `56230c52247bb989d80f9a1363a6fb26cbedb62e60d687e106c2068b372aaeba`.

This is the **full 15,212.525 m designed road**, Königstetten → Marswiese,
not the v001 northern subset. Nominal two 3 m lanes, 6 m total, one pitbox.
UI name is **Exelberg Full v002 (two lanes)**, Austria / Hillclimb / A2B.
The root node, track folder, models.ini FILE and KN5 basename all match
`exelberg_full_v002`; models.ini has explicit zero position/rotation.

## Checks actually performed

`scripts/package_full_track_v002.py` read the v002 scene manifest and performed
one independent `validate_kn5.parse` before reserving fresh output roots, with
explicit **256 MiB / 4096 nodes / 8 MiB texture** bounds. Parser defaults are
unchanged. Result: **1177 nodes, 1152 meshes**, matched manifest mesh counts,
helper transforms, identity root, collision prefixes and opaque rendering.
All seven ksPerPixel texture references resolve. All seven embedded DDS payloads
match separately hash-verified standalone export files; aggregate DDS is 1,835,904
bytes. Only the explicit seven-file allowlist enters `texture/`; no failed-export
subdirectory is copied. Existing independent geometry proof is separately hashed
and referenced, not claimed to have been rerun by the packager.

ROAD / GRAVEL / GRASS / WALL keys are explicit, with manifest friction
**1.0 / 0.7 / 0.6 / 0.6** and manifest validity/pitlane settings.
The preview is the actual own CPU `driver.png` render, resized 1280×800 → 640×400.
Map and outline are generated from **`geometry_audit.npz:designed_xyz_m`**, all
8156 v002 designed stations, not v001 geometry. Tests verify map.ini registration,
full image reproduction, geographic north-up (KN5 X east, Z south), and preview
pixels. Lighting is own provisional daylight configuration.

Both AI files are own-generated little-endian `(3,0,0)` empty headers, the same
format with which v001 loaded according to user feedback. They contain no
recorded driving line and do not establish v002 runtime compatibility.

All packaged bytes and exact ZIP membership were hash/size checked. ZIP contains
only one track-ID root and the strict 20-file allowlist: no scripts, vendor,
blend, failed attempts, NPZ or geographic source inputs. Source provenance stays
outside the game package in the evidence manifest. ATTRIBUTION includes BEV
CC BY 4.0, OSM ODbL, own procedural textures/tree geometry, maps and render.

## Installer verification

`scripts/install_full_track_v002.py` defaults to **DRY_RUN**. Only explicit
`--install` permits new-folder publication. It uses v001's stateless descriptor
and atomic-no-replace rename primitives, never v001 globals or mutable profiles.
Before any game write it checks strict identity/inventory, complete hashes and
sizes, rejects symlinks and unlisted directories, and snapshots verified bytes
into a temporary file. Transfers are streamed, bounded at **512,000,000 bytes
per source file / 600,000,000 bytes total** (no full package held in RAM).
Staging uses exclusive private directories/files, descriptor-relative no-follow
opens, staged hash checks and Linux atomic no-replace publication. No overwrite
fallback is allowed. Snapshotting prevents later source mutation from changing
installed bytes. Tests simulate competing destination creation and ensure refusal
and cleanup; existing v001 and a fake global config remain unchanged.

Actual local destination dry-run passed, with `destination_absent: true`:
`/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa/content/tracks/exelberg_full_v002`.
See `data/processed/full_track_package_v002/dry_run.json`. **No game content was
written, no deployment or game launch occurred, and no global config changed.**

- New tests: **20 passed**, 1.833 s.
- All existing plus new tests: **235 passed**, 47.920 s, under 180-second timeout.
- Log: `data/processed/full_track_package_v002/tests.log`.
- The printed validate_kn5 overwrite refusal is an expected negative test.

Commands actually run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/package_full_track_v002.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/install_full_track_v002.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_full_track_package_v002.py' -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -q
```

Build roots are exclusive: rerunning the packaging command refuses an existing
v002 delivery, rather than replacing it. Normal regression checks reuse hashed
validation evidence and do not repeatedly parse the 233 MB model.

## Runtime gates and honest limitations

**v002 runtime is untested.** No Blender execution occurred during packaging.
The reversed yaw responds to v001 backwards-spawn feedback, but settling, heading,
road/shoulder/wall/terrain collisions, DDS appearance and continuous route driving
still require authorized in-game verification. Invented continuous temporary walls
are not authentic roadside barriers or high-speed/fallproof containment.

The finish-only TIME_0_L/R fixture is at **14912.525 m**, with nominal **300 m
runout**, **299.55 m to the endcap face**; nominal spawn-to-gate distance is
14887.525 m. These are not the full-road UI length, nor certified timing results.
Timer/session/restarts/reset-to-pits and stopping distances remain unverified.
Known km 9.589 DTM dip has an explicitly provisional designed correction up to
+2.508 m, not surveyed asphalt. Width, camber, paint, grip, procedural forest and
scenery fidelity remain provisional. Geometry cost is 1,928,784 triangles;
performance and Quest 2 VR are unvalidated. See
[FULL_TRACK_V002.md](FULL_TRACK_V002.md) and
[the runtime guide](../FULL_TRACK_V002_TEST_GUIDE.md).
