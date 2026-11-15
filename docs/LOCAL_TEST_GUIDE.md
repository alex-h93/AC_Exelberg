# Local solo Practice test — user-controlled, not yet performed

Package: `build/ac_test_v001/exelberg_north_proto_v001/` and matching ZIP.
**Installed with explicit user approval** under the local game's
`content/tracks/exelberg_north_proto_v001`; all 16 file hashes verified.
Evidence: `data/processed/ac_package/installation.json`. No game launch/settings
changes performed. You can proceed to the baseline and Practice checks below.

[Offline evidence](validation/AC_TEST_PACKAGE.md). This is an unvalidated ~1.496 km
northern prototype, not the full route, final realism or a timing-ready event.

## 1. Establish a base-game baseline first

You can test on the **current Linux Steam/Proton installation**; there is no need
to boot Windows now. Windows remains a later primary export/runtime validation
platform, not a prerequisite for this local experiment.

Launch the unmodified base game yourself through your existing Steam setup and
confirm a stock track/car Practice session works. If it does not, stop: troubleshoot
the baseline separately rather than attributing it to this package. Do not have an
agent launch the game or change global configuration without separate permission.
No Content Manager or CSP is required by this package; if absent, do not install
additional software without asking. Do not assume a new Proton version, launch
option, prefix modification, plugin or runtime fix is necessary.

Launching/testing may update your game preferences, Steam/Proton state and logs.
Only you should choose those changes. Record the baseline Steam/Proton version,
car, weather, graphics settings and optional already-present CSP state; do not
change them globally just to try this track. No preference changes were made by
the packager or installer.

## 2. Installation record / future-transfer reference

**The local installation below has already been completed. Do not rerun it over
v001:** dry-run and install modes now intentionally refuse the existing folder.
The commands are retained as a record and for future separately approved transfers.

From the project root, this **dry-run** reads and verifies the complete package and
confirms that the exact new destination is absent. It performs no game writes:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/install_ac_test.py
```

Default game root:
`/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa`.
Use `--game /your/existing/assettocorsa` for a different existing root. The root
may be a Steam symlink; its content/tracks descendants and destination must not
be symlinks. Missing content/tracks is a refusal, not automatically created.

**Do not execute the following until you explicitly decide to install.** Close
AC first. This creates only the exact new track folder and refuses any existing
file/folder/symlink with that name:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/install_ac_test.py --install
```

The user subsequently authorized actual-game install mode; it completed and all
installed file hashes match. Earlier installer tests used fake temporary roots.
The installer did not replace existing content, edit Steam/Proton settings or
launch AC. On systems without Linux atomic no-replace
rename it refuses installation; do not substitute overwrite-capable commands.

For a later Windows transfer, retain the ZIP plus external
`data/processed/ac_package/manifest.json` and verify hashes. ZIP's sole top folder
is `exelberg_north_proto_v001`. Manual extraction is user-controlled: extract into
an isolated staging location first, verify inventory, and only move that new
folder into content/tracks when the destination is absent. Never extract over
existing content. Do not copy scripts, source scenes, vendor tools or geographic
source data into the game.

## 3. First test: one car, low speed

1. Select **Practice**, **Exelberg North Prototype v001**, **one car**, daytime,
   dry weather. No opponents, traffic, hotlap challenge or CSP dependency.
2. Let the car settle without throttle. Check orientation, height, wheels,
   nose/tail clearance and ground contact. Spawn pivots are coincident solo-only,
   +0.4 m above road and flat-yaw on a grade: actual car clearance is **untested**.
   If the car falls, clips, faces incorrectly or spawns badly, stop and report it.
3. Begin at walking speed. Verify steering, braking and continuous collision on
   the road before attempting the section. Keep to the road: collision-intended
   terrain has an artificial trench and verges are not safely joined.
4. Road width (6 m), shoulders (0.75 m each), flat/zero camber and all surface grip
   values are provisional assumptions, not measurements. There are no barriers.
5. Slow well before the remote finish. **Only 15 m run-out remains after the gate;
   this is not braking distance.** Do not arrive at speed or seek a timed result.
6. Separately check reset-to-pits, session restart and a second slow attempt.
   Observe map orientation/materials/visibility. Stop on missing surfaces or errors.

The two AI files are own-generated **empty headers, not recorded AI**. Solo
Practice loading is still a hypothesis. No opponents or racing AI are supported.
The Trento-style TIME_0 pair is a **finish-stage fixture only**, not a verified
start/finish timer. Do not claim timing readiness based on tags or a displayed timer.

If loading fails, preserve the error and available AC logs from your existing
Steam/Proton prefix without deleting/resetting the prefix. Record failure stage,
car/session/weather, screenshots if you choose, spawn behavior and reset behavior.
Do not install CM/CSP or alter global configs as an automatic workaround. Report
findings before requesting a new version. Performance and Quest 2 VR are untested.

## 4. Exact rollback

Close AC. Confirm that you installed this new track and that this is the precise
folder you intend to remove:

```text
/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa/content/tracks/exelberg_north_proto_v001
```

Remove **only that newly installed track-ID folder** (or its exact counterpart
under your explicitly chosen game root). If its identity is uncertain, stop.
Never delete content/tracks itself, another track, saves, Proton prefixes,
Steam files or global configs. No automated uninstall/delete command is provided.
User-selected gameplay preference changes are separate from folder rollback.
Keep project package, ZIP and evidence for diagnosis; do not overwrite v001 to
repair geometry or runtime problems—request a reviewed new version.
