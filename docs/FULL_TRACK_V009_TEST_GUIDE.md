# Exelberg Full v009 — in-game test guide

Install only after explicit authorization: `.venv/bin/python scripts/install_full_track_v009.py --install`
(adds content/tracks/exelberg_full_v009; older versions untouched). Track name: "Exelberg Full v009".

Change vs v008 (user's v008 review: rough road edges in the turns): the OSM centreline was a chord polygon
(straight 2 m steps between OSM nodes, kinks every ~8–26 m). v009 fits a curvature-smooth centreline through
the OSM nodes (scripts/v009_centerline.py) and moves road, gravel, invisible walls, markings, nearby ground,
trees, posts and signs sideways with it (median 7 cm, p99 0.5 m, max 1.04 m). Heights, start and finish unchanged.

1. Curves (e.g. ~1.7 km, ~5.1–5.25 km S-bends, ~9.1–9.4 km sweepers, ~13.6 km hairpin): asphalt and gravel
   edges and centre/edge markings run as smooth arcs, no visible kinks. Report any remaining kink with km.
2. Road surface: no new bumps or steps (heights are unchanged; only XY moved).
3. Roadside: guide posts, curve boards, guardrails and junction stubs line up with the new road edges
   (nothing standing on the asphalt, no gaps between junction stubs and the road).
4. Ground/ortho texture next to the road follows the road (no visible seam or gap at the gravel edge).
5. Start position, Königstetten sign, finish timing as in v008.
