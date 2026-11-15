# Stock AC track conventions — bounded static evidence

## Scope and reproduction

Read-only inspection of the user's local Steam installation at
`/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa`.
No game launch, game/config writes, network, installation, geometry extraction,
texture decoding, or artwork copying. No claim of runtime validation here.

```sh
.venv/bin/python scripts/inspect_ac_track_metadata.py \
  --game /var/home/haze/.local/share/Steam/steamapps/common/assettocorsa
.venv/bin/python -m unittest discover -s tests -v
```

Evidence: `data/processed/ac_reference_metadata/stock_tracks.json`.
Two unique source KN5 files only: Trento-Bondone (187,445,871 bytes) and
Drift (188,195,137 bytes). Both are **v6**, parsed exactly through EOF.
Per survey: **171,671 actual bytes read including selected configs**; texture,
vertex and index payloads are skipped using unbuffered-file seeks. Three surveys
were performed during implementation (515,013 source bytes total). No complete
KN5 read/hash/copy. File inventory records paths/sizes only; AI and images were
not opened. Config values are parsed metadata, not verbatim config files.

The helper accepts v5/v6, checks magic, ranges/EOF, bounded strings/counts,
boolean fields, finite transforms/LOD values and material references. Limits:
20,000,000 actual bytes per survey, 1,000,000 total nodes per file, depth 256,
64 selected pivot records. Iterative traversal carries ancestor matrices only;
it never retains vertex/index/texture data. Kinds 1/2/3 are handled, unknown
kinds fail explicitly rather than silently assuming layout. Kind 3 follows the
existing vendored reader layout; neither sampled track contains kind 3, so its
coverage is synthetic, not a native-asset validation. v5 is likewise tested with
synthetic fixtures; this survey's native evidence is v6. Field order follows
`tools/vendor/kn5_studio/source/KN5Export-f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9/kn5_format.py`
and the project's existing independent v5 validator. This is not mesh-integrity
validation: skipped indices/vertices are intentionally not checked.

## LOD_OUT=0: actual stock evidence

| Stock KN5 | Nodes / mesh nodes | LOD_IN=0, LOD_OUT=0 meshes | Of those active + visible + renderable |
| --- | ---: | ---: | ---: |
| Trento-Bondone | 1506 / 1485 | 759 | 441 |
| Drift | 350 / 308 | 192 | 174 |

All Trento LOD_IN values are zero; finite LOD_OUT ranges are 150–1500.
Drift also has genuine distance bands: 20–70 (15 meshes), 70–180 (14),
70–200 (1), and 95–450 (6), alongside near meshes and zero/zero meshes.
Examples of zero/zero renderable stock meshes include Trento `Cylinder35`
and Drift `Object704`; Drift `06GRASS001` is also active/visible/renderable.

**Interpretation:** zero LOD_OUT is very likely the engine's no-finite-distance-
cutoff/default sentinel, not an automatically invisible zero-width interval.
This is strong evidence from shipped, known stock fixtures, not just exporter
source defaults: hundreds of renderable stock meshes use it. It does **not**
prove exact engine branch logic, infinite range, camera-dependent behavior,
or that our current export loads correctly. Do not classify v001's LOD_OUT=0
alone as a proven visibility defect. Keep runtime validation open.

**Blender handoff:** preserve v001. Make any changed export a new version;
explicit finite LOD_OUT on scenery can be a controlled test, not a purported
mandatory repair. Separate collision/renderable decisions from LOD distance.
Do not change all physics-only meshes to renderable merely to fix visibility.

## Spawn pivots, transforms and direction

Matrices are recorded as 16 float values with row-vector convention,
translation at indices 12–14, and `world = local * parent_world`.
Rows 0/1/2 are local X/Y/Z axes in world coordinates. Mesh nodes have no
independent transform in this layout and inherit their ancestor matrix.
Both tracks contain **same-named dummy (kind 1) and mesh (kind 2)** for each
sampled spawn/timing object; duplicate names here are real, not a parser error.
Use kind 1 as the pivot evidence. A blanket duplicate-name ban is inappropriate
for native-track compatibility. Do not infer that duplicate child meshes are
required for a new track; exporter/game behavior still needs testing.

Rounded stock kind-1 positions (X,Y,Z metres):

| Track | AC_PIT_0 | AC_START_0 | AC_HOTLAP_START_0 |
| --- | --- | --- | --- |
| Trento | (2184.265,73.486,-2467.689) | (2184.280,73.486,-2467.752) | (2184.253,73.486,-2467.643) |
| Drift | (-60.620,0.548,180.045) | same as pit | (2.910,0.553,141.755) |

Trento spawn axes: X≈(0.971254,0,0.238046), Y≈(0,1,0),
Z≈(-0.238046,0,0.971254). Drift: X≈(0.515038,0,0.857167),
Y≈(0,1,0), Z≈(-0.857167,0,0.515038).

**Likely vehicle forward is local -Z, with local +Y up**. Supporting independent
geometric clue: Drift hotlap → TIME_0 midpoint displacement is approximately
(26.05,0,-26.96), aligned with **-Z**, not +Z. This is a static directional
inference, not a verified spawn in-game. For the existing project conversion
`KN5(x,y,z) = Blender(x,z,-y)`, this corresponds to Blender **+Y forward,
+Z up**. Ask the Blender agent to verify the exporter actually uses that mapping
for empty transforms as well as mesh vertices; do not blindly copy Euler angles.

## Timing gates: point-to-point differs from circuit

Trento UI explicitly identifies `A2B`, `Hillclimb`, length 17619 m and four pitboxes.
It has **only AC_TIME_0_L/R** in the complete parsed node graph; no TIME_1/2.
These are high at the remote finish:

- L=(616.316,777.714,-1031.024)
- R=(604.094,777.714,-1031.015), width≈12.22 m.
- Both axes: X=(1,0,0), Y≈(0,0,-1), Z≈(0,1,0).

Thus Trento's gate local +Z is **up**, unlike the spawn's +Y. Uniformly forcing
spawn-style orientation onto every timing marker is not supported by stock data.
Endpoint locations/names appear more important than a universal gate orientation;
exact engine timing rules remain unverified. Trento's `semaphore.ini` names
AC_SEMAPHORE_YELLOW_1/2/3, GREEN_1 and RED_1. No separate timing INI was found.

Drift has TIME_0 and TIME_1 pairs, all with spawn-style +Y-up matrices:

- TIME_0 L=(35.921,0.553,127.682), R=(21.999,0.553,101.915).
- TIME_1 L=(-171.427,0.553,-124.219), R=(-129.105,0.553,-97.347).

**Handoff:** for the later A2B prototype, Trento is the relevant fixture:
start/pit/hotlap pivots near the start and TIME_0 pair spanning the finish.
Do not add a circuit's sector/start-finish convention solely by analogy to Drift.
Coordinator must choose/test the session mode and restart/timer workflow.

## Packaging and model INI

- Trento has `<track-id>.kn5`, `data/`, `ai/`, root `map.png`, and `ui/`
  with `ui_track.json`, outline and preview. **No models.ini** exists there:
  same-name KN5 discovery is a stock packaging pattern.
- Drift has the same base pattern plus `models.ini`. MODEL_0 references
  `drift.kn5` with POSITION=0,0,0 and ROTATION=0,0,0. It also declares optional-
  looking dynamic objects `11.kn5` and `12.kn5`, neither present in the track
  inventory; their resolution/necessity was not investigated. Do not copy those
  references into the new package. A minimal explicit MODEL_0 is a sensible
  test packaging choice, not proved mandatory by this inspection.
- Neither fixture has an `extension/` folder or ext_config.ini in its track tree.
  This supports a **CSP-free initial test package**; external/global CSP settings
  were intentionally not inspected, so pristine vanilla execution is not proved.
- Trento AI files are ~9.77 MB / 100.7 KB; Drift's two AI files are only **12 bytes
  each** (size-only observation; payloads not read). Stock practice/test content
  therefore does not establish a need for meaningful AI paths. Start the proposed
  solo practice package without CSP or AI as a **test hypothesis**, then verify
  loading/spawn/reset. It is not yet certified, especially for hotlap/A2B timing.
  Cameras, map/UI details and lights have not been proven optional by omission.

## Surface keys, defaults and physics

Trento actual digit-prefixed mesh tokens include CONCRETE (21), TRM-TN-A (24),
TRM-TN-B (33), TRM-TN-C (74), GRASS (82), WALL (83). Examples:
`29TRM-TN-A002`, `27TRM-TN-B003`, `52TRM-TN-C`.
Its configured surface keys/frictions are CONCRETE=0.91, TRM-TN-A=0.98,
TRM-TN-B=0.97, TRM-TN-C=0.96. All four are valid-track=1, pitlane=0,
damping=0, dirt-additive=0 and sinusoidal roughness=0. The sampled road meshes
are active/visible but renderable=0, consistent with separate physical surfaces.

Drift has ROAD (8), KERB (9), GRASS (39), WALL (8); examples `03ROAD`, `06KERB`.
Its SURFACE_0 key is **TARMAC-DRIFT**, friction=1, valid-track=1; SURFACE_1
KERB friction=0.92, valid-track=1, vibration gain=0.1/length=0.2. Both pitlane=0.
The ROAD name does not match its SURFACE_0 KEY. This is consistent with
SURFACE_0 acting as a fallback for unmatched drivable names, but does **not**
prove default precedence or engine-wide friction constants. GRASS/WALL also
lack explicit keys here; do not infer their physics solely from surface.ini.
There is no static proof that an absent surface config gives safe grip.

**Recommendation to coordinator/Blender agent:** explicitly configure `KEY=ROAD`
for the proposed `1ROAD` mesh, intended friction and valid-track flag; configure
reachable shoulder keys separately. Do not transplant Trento's friction as a
measured Exelberg value. Keep object naming, material assignment, physical flags
and rendering flags distinct. Test collision/grip and invalid-track behavior in
Windows AC before calling defaults or solo timing validated.

## Checks and remaining blockers

Offline suite: **135 tests passed**, including six new helper tests for v5/v6,
seek accounting, kind 3 layout, parent transforms, EOF/count/material errors and
read budget. No Blender execution or game runtime test was performed.
Outstanding decisions belong to the coordinator/Blender agent: versioned LOD
experiment, empty-axis export verification, spawn clearance and road geometry,
and AC session choice for a timed A2B run. No installation/download blockers.
