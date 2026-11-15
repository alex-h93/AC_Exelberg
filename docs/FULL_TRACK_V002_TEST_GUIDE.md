# Exelberg Full v002 — authorized local AC test guide

**Installed with explicit user approval; not yet runtime-tested.** All 20 installed
file hashes match; v001's 16 files remain unchanged. Installation evidence:
`data/processed/full_track_package_v002/installation.json`. The assistant did not
launch AC or change game settings. Proceed to the first-run checks below.

## Installation record — already completed

Do not rerun installation over v002; both dry-run and install modes intentionally
refuse its existing destination. Commands below are retained for reference only.

Candidate: `build/full_track_v002/exelberg_full_v002/`.
ZIP: `build/full_track_v002/exelberg_full_v002.zip` (one track-ID root).
Evidence: `data/processed/full_track_package_v002/manifest.json`.

Safe default (already performed against the actual local AC root):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/install_full_track_v002.py
```

It must print DRY_RUN, 20 files / 235165128 bytes and destination absent. No
existing folder is ever overwritten. Only **after explicit user authorization**:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/install_full_track_v002.py --install
```

Fixed destination suffix: `content/tracks/exelberg_full_v002`. The installer
validates complete file hashes, strict inventory, caps and symlink safety,
then publishes a fresh folder atomically. Do not manually merge over a failed or
older installation. Keep manifests/logs outside the game folder.

## First run (not yet performed)

1. Record AC/Proton/CSP versions, car, session, daylight/dry weather, graphics,
   resolution and GPU. Start **solo Practice, one car, no opponents/traffic**.
   Select **Exelberg Full v002 (two lanes)**, not Exelberg North Prototype v001.
   Do not alter global Steam/Proton settings to troubleshoot without approval.
2. Capture loading/errors and missing DDS/material symptoms. Seven own opaque
   textures should show road, gravel, grass, bark, canopy, paint and safety stripes;
   compare the packaged offline driver preview without assuming identical lighting.
3. Before accelerating, check the car rests on the right lane and faces towards
   Marswiese. All three solo markers are at designed station 25 m, offset 1.5 m
   right, provisional 0.4 m pivot clearance. Yaw is reversed 180° from v001 after
   backwards-spawn feedback; the new direction is still runtime-unverified.
4. Move at walking speed. Check settling, reset-to-pits and restart repeatedly.
   Stop on reversed direction, falling, sinking, hovering or severe collision hits;
   record screenshot, car, approximate distance/location and relevant AC log.
5. Check reachable road/shoulder/terrain seams and temporary walls gently at low
   speed. Continuous walls and endpoint caps are invented test containment, not
   real barriers or a high-speed/fallproof guarantee. Do not deliberately attempt
   high-speed impacts. GRAVEL/GRASS/WALL provisional friction is 0.7/0.6/0.6;
   ROAD is 1.0. No physical calibration is claimed.
6. Complete the full road slowly, watching for gaps, invisible obstacles, culling,
   missing textures and unexpected bumps. Flag the provisional profile correction
   near source km 9.589; do not mistake it for surveyed bridge/culvert geometry.

## Finish and timing — separate acceptance gate

- Full road/UI length: **15212.525 m**, nominal **6 m / two 3 m lanes**.
- Finish-only Trento A2B `AC_TIME_0_L/R` fixture: **14912.525 m** along the road.
- Spawn-to-gate nominal distance: **14887.525 m**.
- Remaining road: **~300 m**, **299.55 m** to the near face of the closed endcap.
- BRAKE / FINISH, BRAKE and STOP aids occur 300 / 150 / 60 m before road end.

**Brake before the gate.** Runout is not guaranteed stopping distance at any speed.
Empty AI headers are loader compatibility aids, not recorded AI or race support.
Practice loading does not establish timed A2B functionality. Only after basic
load/collision checks and appropriate authorization, test an available supported
solo A2B/hillclimb workflow. Record timer start, gate detection, displayed results,
restart/reset and repeated runs. Do not call timing certified until all pass.
No TIME_1/2 circuit fixture or closed-circuit hotlap claim is provided.

## Performance, feedback and rollback

Measure load time, CPU/GPU frame times and memory through representative forest,
hairpins and open views. Model has 1,928,784 triangles; no FPS or VR guarantee.
Quest 2 validation is deferred until separately authorized and measured.
Record pass/fail per gate, approximate chainage, screenshot/log and reproduction
steps. Source geometry, widths, paint, grip, forest and temporary barriers are a
provisional base, not final Exelberg realism.

To roll back after an authorized installation: close AC, confirm identity, and
remove **only** `content/tracks/exelberg_full_v002`. Do not remove other tracks,
content/tracks itself, v001, saves, global configs or Proton prefixes. Preserve
project evidence and source assets. See
[offline package validation](validation/FULL_TRACK_PACKAGE_V002.md).
