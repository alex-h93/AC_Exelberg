# Exelberg Full v005 — in-game test checklist

Install only after explicit authorization: `.venv/bin/python scripts/install_full_track_v005.py --install`
(new folder `exelberg_full_v005`; v001–v004 untouched). Practice, solo.

1. Track loads; both models appear (road + new roadside objects). If roadside objects are missing,
   report it: MODEL_1 loading would be the suspect.
2. Spawn/direction/asphalt identical to v004.
3. Start (Königstetten): end-of-town sign, first guardrails/curve boards in the hairpins.
4. Curve boards: on the OUTSIDE of bends, arrows pointing into the bend.
5. Guardrails: car should stop at the rail line (the invisible wall), not pass visibly through it.
6. Junctions: stubs visible, red/white boom + round no-entry sign beyond the wall; no bumps when
   driving over the stub mouth (it is visual only).
7. Dopplerhütte (~2.4 km): concrete blocks left, railing right.
8. Scheiblingstein (~7.9 km): town sign + children warning, end-of-town at ~8.2 km.
9. Tower: visible above the trees around 10–12 km (it stands right of the road at ~11.6 km).
10. Shrubs at the forest edge; FPS vs v004 (+~444k triangles, mostly shrubs with 260 m LOD).
11. VR (Quest 2) when convenient: sign readability, shimmer.
