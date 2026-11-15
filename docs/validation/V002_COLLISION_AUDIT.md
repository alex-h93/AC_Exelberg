# v002 collision audit — read-only static evidence

## Scope and verdict

User runtime observations: full v002 spawns correctly; performance and asphalt texture are satisfactory; the car can pass the visible yellow/black side barriers and sometimes launches. These are **user observations**, not runtime tests performed by this audit. Preserve the successful yaw, appearance and full two-lane route.

No Blender, GUI, game, network, installation, deployment or source modification was performed. Python ran with bytecode writing disabled; diagnostic programs were supplied on stdin, with results printed only. This document is the only authored output. No `.blend` was opened. No runtime cause is proved.

**Ranked findings:**

1. **Confirmed barrier/ground mismatch:** side walls follow road elevation, not the ground at their location. Actual terrain provides substantial under-wall gaps and locally overtops the walls. This is the strongest geometric explanation for apparent barrier pass-through; vehicle contact behavior remains untested.
2. **Confirmed internal collision faces; launch hypothesis:** independently closing spatial chunks creates opposing vertical caps ending on the driving surface. Road/verge boundaries also carry overlapping skirts. They are credible snagging/double-contact candidates, not demonstrated launch causes.
3. **Confirmed physics/render conflation:** all walls are renderable; stock comparison supports separate non-renderable physical walls. A flag-related explanation for pass-through remains unconfirmed. Current naming and inner-face winding are not missing/reversed.
4. **Confirmed abrupt endpoint obstacles and rough off-road ground:** transverse walls intersect asphalt at both endpoints; steep terrain is reachable outside the shoulders. Either is a plausible location-dependent impact hazard. No substantive terrain spike through the asphalt was found.

## Files and artifact identity

Reviewed `scripts/build_full_track_v002.py`, `full_track_v002_geometry.py`, `full_track_v002_export.py`, `prototype_geometry.py`, `validate_kn5.py`, relevant package checks, the pinned vendor node exporter/writer, the scene manifest, all 1,132 source mesh artifacts, geometry audit arrays and the actual exported KN5.

Exported, staged and installed `exelberg_full_v002.kn5` are identical:

- Size: **232,993,555 bytes**.
- SHA-256: `56230c52247bb989d80f9a1363a6fb26cbedb62e60d687e106c2068b372aaeba`.
- Installed `data/surfaces.ini` and `models.ini` also match staging.
- Independent v5 parse: 1,177 nodes, 1,152 mesh nodes, **4,988,521 exported vertices**, 1,928,784 triangles; 1,645,884 collision-intended triangles.
- Recomputed every source-artifact hash and exact float32 **oriented XYZ + corner-UV triangle multiset** against actual KN5 parts. All matched. Collision triangle areas are nonzero and geometric winding agrees with exported shading normals.

The installed path inspected read-only was `/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa/content/tracks/exelberg_full_v002/`.

## 1. Barrier geometry and actual ground intersections

Builder lines 203–207 extrude offset strips at **±4.05–4.35 m**, with top at road Z +1.15 m and bottom at road Z −0.15 m. Asphalt ends at ±3 m; thus the existing inner wall is only **1.05 m beyond asphalt**, not the requested 3 m. `G.wall()` is called but its returned geometry is unused; the subsequent ribbon/`solid_chunks()` constructs the exported wall.

Barycentric sampling of the actual float32 clipped terrain triangles at all **8,156 stations per side**, at the inner wall faces, found no missing terrain samples:

| Inner face | Ground minus road Z | Stations with ground below wall bottom | Gap >0.5 m | Maximum under-wall gap | Ground above wall top |
|---|---:|---:|---:|---:|---:|
| Right, −4.05 m | −1.531 to +1.520 m | 1,210 | 231 | 1.381 m | 42 stations |
| Left, +4.05 m | −2.117 to +2.428 m | 2,393 | 494 | 1.967 m | 26 stations |

Largest under-wall gaps occur near source chainage **2,283.95 m right** and **6,969.87 m left**. Maximum terrain above wall top is **0.370 m right** and **1.278 m left**, near source chainages 13,658.50 m and 1,408.46 m respectively. These are station samples, not measured gap lengths or car-clearance simulations. Terrain intersects/buries parts of the wall elsewhere; a visible wall is not guaranteed to span the car's local ground-contact height.

Actual inner shell winding was checked: **16,310 triangles per side**, zero outward-facing errors. Minimum horizontal geometric-normal dot intended inward direction: **0.99764 right**, **0.99377 left**. Thus simply flipping all wall normals would be wrong.

Both explicit endpoint walls cross the asphalt: start approximately **0.150–0.450 m into the route**, finish **0.150–0.450 m before the end**, vertically road −0.15 to +1.15 m. These are genuine above-road obstacles, unlike the below-surface chunk caps.

## 2. Closed chunk caps and double-contact geometry

`solid_chunks()` closes **each centroid-assigned spatial triangle batch** before export (`build_full_track_v002.py:175–207`). `closed_slab()` duplicates the top downward and adds a skirt on every batch boundary (`full_track_v002_geometry.py:270–305`). A spatial boundary can zigzag through asphalt triangles; it is not necessarily a clean transverse road section.

Counts below were derived from actual source topology, whose oriented triangles match KN5 exactly. An internal cap edge is an exact shared top edge with caps in two source chunks; each copy contributes two vertical triangles.

| Surface | Top triangles | Bottom triangles | Vertical triangles | Paired internal cap edges | Opposing cap triangles |
|---|---:|---:|---:|---:|---:|
| ROAD | 32,620 | 32,620 | 33,772 | **286** | **1,144** |
| GRAVEL | 77,215 | 77,215 | 100,010 | 261 | 1,044 |
| GRASS | 503,956 | 503,956 | 153,444 | 9,751 | 39,004 |
| WALL | 32,624 | 32,624 | 65,828 | 141 | 564 |

The road's 286 internal edges total **820.366 m** of unique XY edge length. Their cap planes meet the road top exactly and descend approximately 0.3 m: **they do not protrude above asphalt**. They nevertheless introduce unnecessary opposed collision faces where wheels/body contact the surface. This audit does not establish whether AC's contact solver actually hits those faces.

Across material boundaries, exact top-edge matching found **16,310 ROAD/GRAVEL skirt pairs**, totaling 30,425.053 m, and **14,004 GRAVEL/GRASS skirt pairs**, totaling 15,775.895 m. Road/gravel skirts overlap in the same vertical plane; gravel/terrain skirts share their top edge and overlap over the shallower extrusion depth. Differing triangulation does not eliminate the coplanar overlap.

Existing `solid_checks()` proves closure, directed edge consistency and positive signed volume, not safe vehicle contact. `collision_join_checks()` verifies station vertices, seam gaps and an envelope, but does not reject internal caps or perform full surface-intersection tests. Tests explicitly requiring every collision object to be closed institutionalize this unwanted requirement.

### Actual top-face overlap, not just endpoint matching

Clipped actual terrain triangles against actual float32 asphalt triangles in XY, then interpolated both triangle heights over the intersection polygons:

- Eight positive-area triangle pairs, all at the source start/end.
- Total overlap **0.0003783 m²**; largest pair **0.0001478 m²**.
- Terrain minus asphalt height: **−0.2513 mm to +0.0077 mm**.

This does **not** support a substantial terrain spike through the interior asphalt. Against the entire ±3.75 m shoulder envelope, triangle/quad clipping found 0.25675 m² total overlap spread over 14,570 tiny pairs, maximum 0.0004906 m² per pair. These small boundary residues still deserve shared-boundary construction, not a declaration of exact non-overlap.

## 3. Flags, naming, material keys and vertex shading

All 132 exported wall nodes retain `1WALL_*`, material `V002_safety`, and flags:

`active=1, visible=1, renderable=1, cast_shadows=1, transparent=0, layer=0`.

The actual `surfaces.ini` contains matching `KEY=ROAD/GRAVEL/GRASS/WALL`. Frictions are 1.0/0.7/0.6/0.6; only ROAD is valid track; all pitlane, damping, sinusoidal roughness and vibration values are zero. No configured procedural bump source was found. Invalid-track status is not a wall-enable setting.

Use the **digit-prefixed object surface token → surfaces.ini KEY** contract, not the shader material name. The exporter writes an ordinary material index; it does not read `surfaces.ini` or translate `V002_safety` into WALL. No separate per-mesh “physical” boolean exists in the reviewed KN5 layout. Blender custom properties such as `collision_intended` are annotations, not exported collision switches. No `ACTRIG*` node exists in this candidate; no trigger-name omission or shading-based trigger mechanism was demonstrated. Do not rename walls to triggers as a repair.

The 4.99M vertex count is the **whole exported render/corner stream**, including UV/normal/tangent splits, not 4.99M independently authored collision points. Collision-intended meshes account for 4,616,604 exported vertices. The adapter deduplicates float32 XYZ+normal+UV+tangent, splits uint16 buffers, and cycles indices `(1,2,0)` without reversing winding. Exact source comparisons show that this process did **not** remove collision caps, change triangle positions, or flip them. Smooth normals/tangents are shading data, not a collision-repair mechanism; engine contact-normal implementation was not inspected. Road-top shading normals have up components as low as 0.5135 because smoothing includes slab edges; that alone does not prove a physics defect. User reports performance/texture satisfactory, so do not rank vertex count or shading as the established cause.

### Bounded native comparison

Used `inspect_ac_track_metadata.inspect_kn5` on exactly two unique stock KN5s: Trento-Bondone and Drift. An in-memory extension aggregated WALL/ACTRIG flags and material names. **168,789 metadata bytes read total**; texture/vertex/index payloads were seek-skipped, never extracted/copied. No further native KN5s were opened.

- Drift: all **8 digit-prefixed WALL meshes** have `active=1, visible=1, renderable=0, cast_shadows=0, transparent=0`; material `wall`.
- Trento: 82 WALL meshes use material `barr` and `renderable=0` (81 inactive, one active); one active renderable WALL uses material `term`.
- Neither contains `ACTRIG*` nodes.

This supports separate physics-only wall shells and shows wall material names need not equal WALL. It does **not** prove that `renderable=1` disables collision, that inactive stock meshes should be copied, or that changing one flag will fix v002.

## Actionable v003 plan — not implemented

1. **Top-face-only physical ground:** export ROAD, GRAVEL and reachable GRASS as upward open surfaces. No underside, extrusion skirts, chunk endcaps or duplicate reverse faces. Partition the same surface triangles without reclosing chunks. Keep visual slabs/scenery separately under non-digit names. Preserve asphalt material/texture, route extent, two lanes and successful spawn yaw.
2. **Single contact skin:** construct road, verge and reachable terrain from shared final float32 boundary vertices/edges, including all terrain cut points. Retriangulate slivers/T-junctions; reject positive-area overlaps, discontinuities, collapsed/needle triangles and extreme local slopes in the reachable apron. Do not merely lower another collision layer under the road. Far scenery need not be physical.
3. **Requested containment:** independent physics-only inward-facing strips at exactly **left +6 m / right −6 m**, i.e. **3 m beyond each ±3 m asphalt edge**. Use `1WALL_L_*` / `1WALL_R_*`, active/visible=1, **renderable=0**, transparent=0, cast-shadows=0, layer=0, with explicit WALL surface key. No duplicated backfaces, roofs, bottoms, interior chunk caps or co-located visual colliders. Keep current friction values provisionally, ROAD valid-track=1 and other keys=0, pitlane=0, damping/sinusoidal roughness/vibration=0; do not add an invented INI collision toggle. Retain zero/default LOD provisionally; stock metadata does not establish a special collision LOD fix.
4. **Normals/winding:** with unit travel tangent `t=(tx,ty,0)` and left normal `n=(-ty,tx,0)`, left inward normal is **−n**, right inward normal **+n**. KN5 mapping `(x,y,z)→(x,z,−y)` gives left `(ty,0,tx)`, right `(-ty,0,-tx)`. For sequential stations, left triangles can use `(bottom_i,bottom_j,top_j)` and `(bottom_i,top_j,top_i)`; reverse for right. Assert actual geometric normals dot intended inward direction >0 after export, including every split.
5. **Ground-aware barrier height:** do not reuse road Z −0.15/+1.15 blindly. At ±6 m, actual sampled terrain differs from road by **−2.050…+2.364 m right**, **−2.609…+3.133 m left**. Although the ±6 m envelope has zero inverted triangles/nonadjacent overlaps, this buffer is **not statically safe as-is**. Design a documented provisional, smooth drivable apron and anchor shells below its final local ground, with adequate height above that ground; check triangle interiors as well as stations. A conservative candidate is ≥0.5 m below minimum adjacent contact ground and ≥2.5 m above its maximum, subject to later car tests—not a high-speed containment guarantee.
6. **Visible posts every 33 m of designed arclength**, using non-digit `VIS_*` names, no physical duplicates. Ground them on the final apron; mark them as procedural safety aids, not surveyed furniture. Remove yellow/black side-wall rendering. Do not retain sudden transverse above-asphalt endpoint walls without an explicit braking/endpoint design.
7. **Role-aware validators:** replace blanket `closed=True` and `renderable=True` assertions in builder/package/tests with top-only ground and non-renderable wall contracts. Test exact oriented exports, inward wall faces, continuous shared seams, no internal caps/duplicate contact planes, no apron/barrier burial or underpass, no positive-area ground overlaps and no above-asphalt unintended obstacle. Keeping existing top triangles alone reduces non-wall physical geometry from 1,514,808 to **613,791 triangles**, before apron redesign.
8. **Later, explicitly authorized runtime gate:** low-speed wheel/body wall tests from both lanes, cross-verge recovery, the identified gap/burial chainages, road chunk seams, endpoints, then full-route speed tests. Log car, position/speed, contact behavior and settings. No such launch/deployment/test is authorized or performed here.

**Blocker:** static geometry and stock flags cannot identify the actual AC contact/solver branch causing a particular launch or prove the flag change restores body collision. The v003 plan removes confirmed geometry hazards and creates a controlled physics configuration for subsequent authorized testing.
