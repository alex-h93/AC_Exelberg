# Exelberg Full v004 (vegetation) — in-game test guide

v004 = v003 road/collision **byte-identical** (424 physics meshes, spawn/timing helpers
checked offline) + new visuals. Install only after explicit authorization:
`cd scripts && ../.venv/bin/python install_full_track_v004.py` (dry run) then `--install`.
It installs as a NEW folder `content/tracks/exelberg_full_v004`; v002/v003 stay.

## What to look at (solo Practice, daytime, dry)
1. **Loads at all?** KN5 is 255 MB (v003: 125 MB); note loading time.
2. **Trees** near the road (3D) and further away (flat impostors): do they look like a
   summer forest? Any black/white leaf fringes, missing leaves, trees floating or buried?
3. **LOD switch** at ~180 m: how noticeable is the 3D→impostor pop?
4. **Ground**: does the grass detail texture look right, or too dark/bright/stripy?
   (Shader semantics `ksPerPixelMultiMap` + `txDetail` are unverified; easy to tune.)
5. **With CSP**: 3D grass (GrassFX) on the ground — present? Under forest too?
6. **Performance**: FPS at start (Königstetten), mid-forest (~km 5) and a hairpin.
   Compare with v003 at the same spots. Note settings and whether shadows are on.
7. Collision is unchanged from v003; previous v003 collision checks still apply.

Report: screenshots + FPS numbers + anything odd with approximate km.
