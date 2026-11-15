# Exelberg Full v003 — authorized runtime test guide

**Installed with explicit user approval; not yet launched or game-validated.** All 46 installed file hashes verified; v001/v002 remain unchanged. Evidence: `data/processed/full_track_package_v003/installation.json`. No game/preferences changes or assistant launch occurred. No global Steam/Proton/CSP changes are required.

## Package and installation record

Local installation is complete. Do not rerun installation over v003: both modes
intentionally refuse its existing folder. Commands below are retained for reference.

- Folder: `build/full_track_v003/exelberg_full_v003/`
- ZIP: `build/full_track_v003/exelberg_full_v003.zip`; exact single top-level folder `exelberg_full_v003/`, 46 files.
- Integrity ledger: `data/processed/full_track_package_v003/manifest.json`.
- Dry-run only: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/install_full_track_v003.py`
- Only after deployment authorization, adding `--install` creates **only** the new `content/tracks/exelberg_full_v003` folder. Existing folders, including that ID, are refused. Do not manually merge/overwrite tracks.
- Installer streams and verifies an immutable source snapshot (512 MB/file, 600 MB aggregate ceilings), rejects source/child symlinks and unexpected files/directories, verifies staging and publishes atomically without replacement. The configured Steam-root alias may resolve; child directories are not followed.
- Rollback after closing AC: confirm identity and remove **only** `content/tracks/exelberg_full_v003`. Never remove other tracks, settings, saves or Proton prefixes.

## Ask before the first launch

Obtain explicit launch authorization and ask: **Which specific car should be tested, and at which source chainage/location did the earlier wall pass-through or car-flying event occur?** Record exact car/version/setup, AC/Proton/CSP versions (if already present), weather/session, graphics/resolution/GPU and reproduction direction/speed. Do not silently change current preferences. No opponents, traffic, AI recording, CSP installation or VR setup is implied.

## Gates, in order

1. Select **Exelberg Full v003 (collision + ortho)**, solo Practice, one car, daytime dry. New own empty AI headers `(3,0,0)` retain the Practice format v002 already loads; they are not opponent paths. No required CSP dependency.
2. At rest, verify settling, right-lane placement and correct Königstetten → Marswiese direction. All five helper transforms retain v002's successful yaw. Restart/reset-to-pits must be checked independently in v003.
3. Start at walking pace. Walls are deliberately **invisible**, ±6 m from centreline: **3 m beyond each nominal asphalt edge**, not at the visual posts. Gently test wheel/body contact from both lanes/sides; stop on pass-through, snagging, suspension impulses, launches or unstable settling. These invented aids are not surveyed barriers or high-speed containment guarantees.
4. Revisit source-chainage regression sites: **2,283.95 m right** and **6,969.87 m left** (old under-wall gaps); **13,658.50 m right** and **1,408.46 m left** (old burial/overtopping). These are EPSG:3035 source chainages, not exactly the UI designed-road odometer. Also test the user's specific event location/car. Do not infer success from static ground coverage alone.
5. Cross asphalt/shoulder/apron boundaries gently and traverse road chunk seams in both lanes. Static TOP-only ground removes old underside/skirt/internal-cap hazards, but six endpoint T-junction edges remain. Apron slope limit **30%** is provisional; substantial derived-terrain edits and uncalibrated grip/zero camber are not measured road design. **Car flying/falling is not proven fixed.**
6. Inspect both endpoints and braking before increasing speed. Full designed asphalt is **15,212.525 m**, two nominal 3 m lanes, total 6 m, one pit. Finish fixture is at designed **14,912.525 m**, leaving the same **300 m physical runout** to an invisible endpoint shell. BRAKE signs are 300/150 m before road end, STOP at 60 m. Brake before the gate; runout is not certified stopping distance.
7. Complete the full route slowly, watching orthophoto tile/road seams, missing textures, culling, trees/posts and unintended obstacles. The 26 BEV orthos are 2 m backdrop pixels, not close-road geometry. 822 posts on a nominal 33 m grid are procedural, connection exclusions heuristic, not RVS verified. Forest uses OSM masks, not surveyed individual trees.
8. Separately verify A2B timer start, finish detection, results, restart, reset-to-pits and a repeated run. Finish-only stock-style `TIME_0_L/R` fixtures and full-route UI length are **not proof of working AC timing**. Do not assume closed-circuit Hotlap or enable AI opponents.
9. Only after successful low-speed gates, seek authorization for higher-speed/full-route performance work. Record frame times at representative forest/hairpin/open locations and compare v002 under unchanged conditions. Quest 2 VR remains unvalidated and separately scoped.

For every gate, record pass/fail, specific car, source chainage or identifiable location, lane/side, speed, screenshot/log and repeatable steps. Preserve existing user evidence; do not claim collision, performance, timing or VR acceptance without actual runtime results.
