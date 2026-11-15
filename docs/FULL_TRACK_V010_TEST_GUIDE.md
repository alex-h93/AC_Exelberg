# Exelberg Full v010 — in-game test guide

Install only after explicit authorization: `.venv/bin/python scripts/install_full_track_v010.py --install`
(adds content/tracks/exelberg_full_v010; older versions untouched). Track name: "Exelberg Full v010".

Change vs v009 (user request: extend to 48.2401990264944, 16.276531758839184; "the 2nd exit of the roundabout
should be the finish"): the road continues ~767 m past Marswiese down Exelbergstraße (OSM), takes the one-way entry
branch into the Neuwaldegg roundabout, drives counter-clockwise past exit 1 (Neuwaldegger Straße west, towards
Hütteldorf / Camping Wienerwald) and leaves at exit 2 (Neuwaldegger Straße east). FINISH gate where the given point
lies on that exit road (~15.90 km, 9 m from the given point), then 100 m run-off, STOP board, end wall.
Everything up to 60 m before the old end is unchanged from v009.

1. Old finish area (~15.0–15.2 km): no old BRAKE/FINISH/STOP boards, no timer at the old place; road, gravel,
   markings and ground continue smoothly past the former end (no step, hole or seam at ~15.17 km).
2. Extension (~15.2–15.83 km): road surface and grade smooth (max 5.7 %, min radius 8 m); edge/centre markings
   continue until ~8 m before the roundabout; ground beside the road has no holes/spikes; trees not on the road.
3. Roundabout: road follows the ring lane (not over the island). Other arms and the rest of the ring are visual
   asphalt only — the invisible ±6 m wall closes them, like the other junctions. The island kerb is visual only.
4. Finish: timer stops at the FINISH board on the exit road (2nd exit). Please report whether timing works.
5. Run-off: ~100 m to the STOP board area and end wall — slow down after the finish (end wall stops you hard).
6. Buildings near the roundabout (Neuwaldegg) appear; heights from the laser scan.
Known approximations: lane width/markings in the city section are the nominal 2 × 3 m; no guide posts, curve
boards or signs on the extension (no reference footage); minimap regenerated for the longer route.
