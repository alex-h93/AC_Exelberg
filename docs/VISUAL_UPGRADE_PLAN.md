# Visual upgrade plan (post-v003)

**Status:** proposal only. Nothing in this document has been implemented or
acquired. It refines milestone M5 of `IMPLEMENTATION_PLAN.md`. All project rules
still apply: `.venv`-only Python, ask before non-Python installs and downloads
over 1 GB, no game launch or deployment without explicit authorization.

## 0. Where we are and what looks wrong

Observed in `data/processed/full_track_scene_v003/driver.png` (Blender preview,
not an in-game screenshot):

| Problem | Cause |
| --- | --- |
| Trees look like green lollipops | 4,616 identical low-poly opaque blobs with one generated texture; no leaf cards, no alpha, no variation in species, size or density |
| Forest has no depth | trees are isolated objects on bare ground; no forest edge, understory, or dense "wall" of trunks/foliage |
| Ground is smeared | 2 m/texel orthophoto viewed from 1.2 m eye height; no tiling detail, no grass |
| Verge is a flat gravel band | no mown grass strip, ditch, or edge transition |
| Empty roadside | only white posts; no guardrails, signs, junctions, buildings, lamps or bus stops |
| Flat, grey sky / light | no CSP lighting/weather configuration yet |

Biggest visual wins per unit of work, in order: **vegetation + ground**, then
**roadside furniture (guardrails/signs/posts)**, then **junctions**, then
**buildings**.

## 1. Gate before starting

The v003 collision revision is still runtime-unverified. Visual work changes
little collision geometry, except junction stubs and guardrails (sections 5 and
6). Proposal:

1. Finish the v003 low-speed collision test first.
2. Vegetation, ground, signs and buildings may proceed in parallel because they
   are visual-only.
3. Junction stubs and guardrail collision wait until v003 collision is
   understood.

## 2. Reference collection (everything else depends on this)

The data we have (OSM, BEV DTM/orthophoto) cannot reveal guardrail positions,
sign content, building facades, or forest species from road level.

- **Preferred:** the user records a daytime drive (dashcam or phone, both
  directions if possible), plus stopped-car photos at junctions and landmarks.
  Record the date and season. Drive or film safely and lawfully.
- **Street View:** only for visual comparison, per the existing project rule.
  Do not extract images, and do not bulk-digitize positions from it (Google's
  terms restrict derived data). Use it to check things, not as a data source.
- **Output:** a single **roadside inventory** file,
  `data/processed/roadside_inventory/inventory.csv`, is the placement database
  for every phase:

  `id, chainage_m, side(L/R/both), type, subtype, length_m, source(osm|video|photo|inferred), confidence, note`

  Types: `guardrail`, `sign`, `junction`, `building_landmark`, `bus_stop`,
  `lamp`, `wall`, `fence`, `hedge`, `forest_edge`, `vineyard`, `meadow`.
- A small tool (`scripts/inventory_from_video.py` or a simple Blender
  chainage marker workflow) converts "video timestamp → chainage" using the
  known route length and a few landmark sync points.

**Decided (user):** summer, full leaf. Species need only be plausible, not exact.
**Decided (user):** CSP may be used for the look (keep a tested vanilla fallback).

## 3. Vegetation

### 3.1 What the real vegetation is

The route crosses the Wienerwald flysch hills. Expect, from Königstetten to
Marswiese:

- **Königstetten slopes (start):** vineyards, orchards, meadows, hedgerows, and
  village gardens (OSM has `vineyard`, `orchard`, `meadow` and `farmland` polygons).
- **Forest sections (most of the route):** beech-dominated deciduous forest
  (*Fagus sylvatica*) with oak (sessile and pedunculate), hornbeam, ash and
  maple, plus patches of spruce, larch and pine plantations. OSM
  `leaf_type` is mostly `broadleaved`, with a few `needleleaved` areas.
  Beech forest is typically tall, straight grey trunks with a closed canopy
  and a sparse floor covered in leaf litter. Forest edges are dense with
  shrubs (hazel, hawthorn, blackthorn, elder).
- **Clearings/Exelberg/Marswiese:** meadows, sports facilities, scattered
  houses with gardens.

Species mix per area is an **inference** from regional ecology and OSM tags,
not a measurement. Correct it from the drive video.

### 3.2 Optional data upgrade: canopy height

BEV also publishes an ALS surface model (DOM/DSM). DSM minus DTM gives a canopy
and building height model, which would supply real tree heights, real forest
gaps and edges, and building heights (section 7). **Verify** the product,
license and byte-range access first, then acquire it as a bounded corridor
operation like the DTM. **Checked 2026-11-15:** exists on the DTM grid, CC BY 4.0;
±200 m = 46.4 MB, ±400 m = 66.4 MB (+~15 MB DTM). See `docs/DATA_SOURCES.md`.
Pixel acquisition still awaits approval of the radius.

### 3.3 Asset strategy (three tiers)

| Tier | Distance from road | Representation | Budget idea |
| --- | --- | --- | --- |
| Hero | 0–40 m | Real tree meshes: modeled trunk + branches, alpha-tested leaf cards, 5–8 variants per species | 1–3k tris each |
| Mid | 40–200 m | Simplified variants (crossed planes or reduced cards) plus continuous "forest wall" strips along forest edges | 50–300 tris |
| Far | 200 m+ | Orthophoto terrain plus low canopy "skirt" meshes on hill silhouettes | merged |

- **Tree generation:** Blender's free Sapling Tree Gen add-on, or hand-built
  trees, keeps licensing clean. Leaf, bark and needle textures from **CC0** sources
  (ambientCG, Poly Haven) or our own photos. No textures ripped from other games
  or Google.
- **Placement:** keep the existing deterministic forest mask, but add
  - species zoning per OSM polygon (`leaf_type`, plus canopy height if acquired),
  - Poisson-disc density that is higher at forest edges and lower in the interior,
  - random scale and rotation, with heights clamped to plausible values (beech 25–35 m),
  - a shrub band 2–8 m deep along every forest edge facing the road,
  - single trees, tree rows (OSM `natural=tree` ×507, `tree_row`) and orchards
    placed from OSM.
- **AC specifics:** use alpha-test (not alpha-blend) shaders for foliage to avoid
  sorting artefacts and VR shimmer. Use mip-mapped DDS with a coverage-preserving
  alpha. Set per-mesh `lodOut` distances in the KN5 node, but **verify KN5
  Studio exposes lodIn/lodOut** before relying on it. Only hero trees cast
  shadows. No tree collision; the invisible containment already prevents
  reaching them.
- **Batching:** merge instances per material per geographic chunk (about 250 m)
  so the draw count stays bounded. Today there are 1,338 nodes; target is similar or fewer.

### 3.4 Ground and verges

- Replace the single orthophoto material with a **multilayer** material (AC
  `ksMultilayer_fresnel_nm4` family): the orthophoto stays as the low-frequency
  colour; 3–4 tiling CC0 detail layers (grass, leaf litter, dirt, gravel) are
  selected by a mask derived from OSM land cover and the orthophoto. **Verify**
  that KN5 Studio exports the shader inputs correctly with a 1-chunk test.
- **Verge cross-section:** asphalt → 0.3–0.5 m gravel/broken edge → 1–2 m mown
  grass → shallow ditch or slope. Use the reference video to decide where ditches,
  rock cuts or retaining walls exist (OSM lists `retaining_wall` and `cliff`).
- **Grass:** CSP GrassFX on the grass/meadow materials gives real 3D grass at
  low cost. It is optional; the track must still look acceptable without CSP.
- Add leaf litter decals in the forest floor material, and a few fallen logs and
  stones near the road in forest sections.

## 4. Lighting and atmosphere (cheap, high impact)

- Versioned CSP track config (`extension/ext_config.ini`) with tuned fog and
  haze, so distant hills fade and the forest gains depth. Add material tweaks
  (asphalt specular, foliage translucency) and GrassFX settings.
- Check the result with vanilla AC too, and record CSP/Pure/Sol versions used.

## 5. Guardrails (Austrian Leitschiene)

**Yes, this is feasible.** The common Austrian rural-road type is the galvanized
steel **W-profile guardrail** (Leitschiene, EN 1317), with sigma or C-profile
posts at about 2 m (sometimes 4 m) spacing, rail top at about 0.75 m, and
spacer blocks. Ends are ramped into the ground or flared away. Rectangular
reflectors are often mounted on the rail. Confirm the exact variants, spacing
and reflector colours from photos; do not assume them.

- **Placement:** OSM has **no** `barrier=guard_rail` in our extracts, so positions
  come from the roadside inventory (video/photos). Typical locations are outer
  edges of bends on embankments, bridge/culvert approaches (including the
  km 9.58–9.60 bridge section), and steep drops.
- **Modeling:** one 4 m rail module, one post, one spacer, and two end-terminal
  variants. A script sweeps the module along the road edge offset, following
  road grade and crossfall, and snaps posts to the ground.
- **Texture:** galvanized steel (slightly mottled, with dirt near the ground),
  normal map for the W-profile, and reflectors.
- **Collision:** two-step approach.
  1. Visual-only first, with the existing ±6 m invisible strip unchanged.
  2. After v003 collision is understood: in guardrail stretches, place a
     smooth, simple, vertical physics wall at the rail line (not the rail
     mesh itself), and verify no launch at low speed. The rail mesh itself
     is never a physics surface.
- **Existing posts:** upgrade the 822 posts to the proper Austrian Leitpflock
  model (white, black band, reflectors per side, confirmed from photos). Omit
  posts where guardrails exist; in Austria, the reflectors move onto the rail there.

## 6. Junctions closed with barriers

**Yes, this is feasible.** The geometry pipeline already knows where connections are;
98 post placements were skipped near mapped connections.

1. **Enumerate:** intersect the designed centerline with all OSM highways
   (`secondary`, `tertiary`, `residential`, `service`, `unclassified`, `track`)
   and write each one to the inventory with chainage, side, angle and class.
2. **Classify:**
   - *Road junctions* (secondary/tertiary/residential/service): build an
     asphalt stub 25–60 m long that follows the side road's real alignment and
     DTM profile. Include flared corner radii, give-way/stop line markings and
     correct signs (OSM has `give_way` ×11 and `stop` ×5 nodes). Place the closure
     where it looks natural, just beyond the corner: red/white **Absperrschranke**
     barrier boards on trestles, plus an "Allgemeines Fahrverbot" sign and
     optional flashing warning lights. Behind it, the side road continues visually
     for another 30–100 m, then fades into terrain or forest so it does not
     look like a wall.
   - *Forest tracks/driveways:* a short gravel or asphalt mouth with the real
     closure type. The Wienerwald already has many forestry **Schranken** (OSM
     has `lift_gate` ×25, `gate` ×59), so those can match reality directly.
3. **Collision:** the invisible containment line currently runs continuously at ±6 m.
   Choose one option per junction:
   - **Simple (recommended first):** keep the ±6 m line across the junction mouth.
     The stub is visual only, and the car stops 3 m before the junction mouth.
     This is safe but slightly odd if the visible barrier is further back.
   - **Faithful:** open the containment at the mouth and add a containment wall
     at the visible barrier plus walls along the stub's edges. This requires
     the ground-coverage checks from v003 and a new low-speed test.
     Do it only after v003 collision is verified, and only for a few showcase junctions.
4. Add matching road markings on the main road at junctions: centre-line changes,
   give-way markings, and bus stop bays (OSM `bus_stop` ×53 across the extracts).

## 7. Buildings (selected, not all)

The OSM extracts contain roughly 2,000 building footprints, including overlap
between extracts. Only a few have `height`, `building:levels` or `roof:shape`.

1. **Visibility selection:** sample driver eye points every 10–20 m along the road.
   Ray-cast to each building centroid and its corners against DTM plus a forest
   occlusion proxy (canopy height model if acquired, otherwise forest polygons
   with an assumed height). Keep buildings that are visible for at least *N*
   samples within about 300 m. Output a ranked list for user review. Expect only
   a small fraction to qualify, mostly Königstetten at the start, roadside
   houses, Dopplerhütte, the Exelberg area, and the Marswiese area at the finish.
2. **Three tiers:**
   - **Landmarks (3–8 buildings):** hand-modeled from photos, such as the
     Dopplerhütte inn and the buildings around the start and finish. The user picks the list.
   - **Procedural (visible set):** extrude the OSM footprint. Use height from
     `height`/`building:levels`, DSM−DTM if acquired, or a default of about
     6.5 m for houses. Default to gabled roofs (Satteldach) along the long
     axis. Austrian palette: white/cream/ochre rendered walls, red-brown or
     anthracite tiles. Add window/door texture atlases with variation, and
     place sheds and garages as simple boxes.
   - **Not visible:** omit. The orthophoto already shows roofs from far away.
3. **Source options:** OSM (ODbL) for Lower Austria. The Vienna part (Marswiese)
   has Vienna OGD building data (FMZK footprints are already listed; Vienna
   also offers a building-volume model). Verify that product and its license before use.
4. **Plus street furniture** in villages: street lamps (`street_lamp` ×169),
   bus stop shelters and signs, fences, hedges and walls from OSM.

## 8. Road signs (Austrian StVO)

**Yes, this is feasible.** Austrian traffic sign designs are official works and generally
not copyright-protected. Wikimedia Commons has SVG sets for Austrian signs
(check each file's stated license and record it).

- **Content:** speed limits, curve and danger warnings, Ortstafel and Ortsende
  (OSM has `city_limit` ×14), give-way and stop signs at junctions, direction
  signs (Wegweiser), bus stops, and Fahrverbot at the closed junctions. Place
  curve chevrons and markers only where the video shows them.
- **Placement:** OSM `traffic_sign` nodes (few) plus the roadside inventory.
  Side, height (about 2.0–2.2 m to lower sign edge in towns, lower outside) and
  offset (about 1 m from edge) follow typical practice; confirm from photos.
- **Build:** one atlas texture for all sign faces (SVG → PNG → DDS), an
  alpha-tested face plane with a grey galvanized back, and a round post with a
  clamp. Generate everything with a script from the inventory.
- Signs are visual only, with no collision, and sit outside the ±6 m containment.

## 9. Performance and budgets

v003 has 935k tris and 1,338 nodes, with performance not yet measured. v002 ran
acceptably at 1.93M tris. Proposed per-version targets, to be revised after
measurement:

- At most ~2.5M tris total, with ≤ ~1M visible at once thanks to lodOut and culling.
- Draw calls per frame are bounded by chunking (about 250 m chunks, one mesh per material).
- Texture memory: hero assets up to 2K, atlased signs, 1K detail tiles.
- For VR, check foliage shimmer and the alpha-test mip bias, and measure
  frame times before claiming VR suitability.

Record a frame-time comparison against v003 at three fixed locations
(Königstetten start, forest hairpin, Exelberg open view) for every release.

## 10. Proposed sequence

| Release | Content | Collision change? |
| --- | --- | --- |
| v004 | New tree assets + species zoning + forest edges/shrubs, multilayer ground, mown verges, CSP fog/light config, improved Leitpflöcke | No |
| v005 | Guardrails (visual), road signs atlas + placements, junction stubs with barriers ("simple" collision option) | Minimal (stubs outside ±6 m) |
| v006 | Visible-building selection, procedural houses, 3–8 landmarks, village furniture | No |
| v007 | Optional: guardrail physics walls, faithful junction containment, canopy-height-driven forest | Yes, needs a low-speed runtime test |

Each release follows the existing pipeline: Blender headless build →
independent validation → KN5 Studio export → packaged as a **new** track folder
alongside older versions → user runtime test. Keep v002/v003 for comparison.

## 11. Decisions needed from the user

1. **Season** for vegetation and textures (summer recommended).
2. **References:** can you record a drive video and some photos? Without them,
   guardrails, signs and landmarks will be plausible inventions and will be
   labelled as such.
3. **Landmark list:** which buildings or places must be recognizable?
4. **CSP:** may the visual config depend on CSP (with a vanilla fallback that is
   tested but less pretty)?
5. **Optional data:** may I verify (metadata only) and then request approval for
   a bounded BEV surface-model corridor acquisition for canopy and building heights?
6. **Junction collision:** start with the "simple" option everywhere?


## Landmark: Richtfunkstation Exelberg (user request 2026-11-15)

- Position: OSM node 2916162012 "Funkanlage Exelberg" 48.248824 N, 16.244087 E; Wikipedia gives
  48.24875 N, 16.244125 E (about 8 m apart). Local track coords about (2858, -2104); 89 m from the
  centreline at chainage about 11,626 m, beside the Exelberg / Rotes Kreuz section.
- Height: 109 m total (Wikipedia). The BEV DSM shows a 97 m return 1 m from the OSM node, over ground
  at about 514 m a.s.l. (the scan likely misses the thin antenna tip). It is a reinforced-concrete
  standard tower (Telekom Austria "Typenturm").
- Look (from reference photos): light grey/white concrete shaft, several stacked
  circular antenna platforms in the upper third, and a slim red/white lattice mast on top. It is seen
  over the treeline from the forest section.
- Model: a simple lathe of shaft plus platform discs plus a mast (well under 2k triangles), always
  visible (LOD out 5 km), non-physics, VIS_ prefix. Check that the v004 trees within 40 m of the base
  are not base buildings.
- Its CHM spike was not turned into a tree (v004's tallest tree is 46.7 m), so nothing needs removing.

## v005 as built (2026-11-15)

Second KN5 (`exelberg_v005_roadside.kn5`) next to the unchanged v004 KN5; all objects visual only.
Positions from the roadside inventory (approximate chainage) plus OSM junctions; see docs/STATUS.md
for counts and known limits. Collision on guardrails is deliberately not added (v003's ±6 m wall is
the containment); a later option is narrowing the walls to real rail positions where rails exist.
