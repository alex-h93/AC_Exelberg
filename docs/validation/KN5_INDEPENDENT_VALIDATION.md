# Direct KN5 — independent static structure and source-geometry validation

## Result (2026-10-25)

**PASS: independent static parser and source-geometry checks. Not game acceptance.**

The original 8,190,802-byte KN5 parses completely to EOF using a new bounded
little-endian parser, with **3 textures, 3 materials, 2 identity dummy nodes and
5 mesh chunks**. All **230,400 triangles** match the four captured source meshes
as **oriented XYZ + per-corner UV multisets**, exactly at float32 precision after
the documented conversions. No structural/source mismatch was found. No vendor
KN5 reader, writer, exporter, Blender module or other third-party executable code
was imported or executed.

Evidence: `data/processed/kn5_test/independent_validation.json`. The first export
report, NPZ, KN5, standalone textures and other existing assets were not modified.

| Input | SHA256 |
|---|---|
| `exports/kn5_prototype_v001/northern_hairpins_kn5_v001.kn5` | `8681e75aa707c359c3f340fd719db088b3c40aa47b2900b137c8d87b3bb7c37a` |
| `data/processed/kn5_test/expected_geometry.npz` | `65c5038dbde6fa4bcc8c179d65c2027f0632278d72fd772ec0e443b56a03c430` |
| `data/processed/kn5_test/report.json` | `aaed89ff58116244e2cf662bf741508929bc797cbb29c25e2f32dbc6f28ffdbd` |

## Independence and external layout evidence

This is **more than a vendor-described layout check**, but not every primitive
has an independently inspected specification. We inspected the unrelated
[AcTools `Kn5Basic.cs`](https://raw.githubusercontent.com/gro-ove/actools/master/AcTools/Kn5File/Kn5Basic.cs)
reader implementation in `gro-ove/actools` (the Content Manager/AcTools project).
It was retrieved as text, **not executed**, on 2026-10-25:

- HTTP 200, **71,427 bytes**, SHA256
  `bb0759c1c8d9529b9b536cc38fe3486ae0b7df15e1bd5b12e0cf7660402afeab`.
- Relevant methods: nested `Factory.Kn5Reader.ReadHeader`, `ReadTexture`,
  `ReadMaterial`, `ReadNode`, and the `FromFile_*` methods.
- These independently corroborate magic `sc6969`, v5 with no v6 extra integer,
  texture/material counts, texture active/name/length/payload order, material
  property and binding order, node header and mesh fields below.
- `ReadMaterial` reads each property as `ValueA=ReadSingle`, `ValueB=ReadVec2`,
  `ValueC=ReadVec3`, `ValueD=ReadVec4`: **10 float32**, not just one scalar.
- `ReadNode` explicitly comments **44 bytes per vertex**, then reads position3,
  normal3, UV2, tangent3; indices use `ReadUInt16`. Mesh tail reads material ID,
  layer, `LodIn`, `LodOut`, sphere center3, sphere radius and renderable flag.
- It calls inherited `ReadString`, `ReadMatrix`, vector and binary primitives.
  Their implementations were **not retrieved**. Thus UTF-8/u32 string lengths,
  endianness and matrix storage convention are not independently established by
  those helper implementations. They follow the handoff description and are
  consistent with full bounded parsing of this artifact. Identity matrices cannot
  distinguish row/column-major order. No general matrix-conversion proof claimed.
- The URL used mutable `master`; the recorded content hash identifies the actual
  inspected text, not an asserted immutable upstream commit. No assertion about
  upstream maintenance recency or verified production KN5 fixtures is made.

Exactly **3 read-only HTTP requests**, no retries or installs: attempted
`AcTools/Kn5File/Kn5Reader.cs` (404; error body not read), then `Kn5.cs` (200,
1,249 bytes; SHA256
`417580edd95f7861eb381fc13879aa57272773ecd1649634676df9a77f9570cb`),
which pointed to `Kn5Basic`, then the successful reader source above. Successful
response bodies total **72,676 bytes**, below the 2 MB acquisition allowance.
The validator and tests themselves are entirely offline. The source is referenced,
not vendored or copied into executable project code.

## Parser scope and bounds

`scripts/validate_kn5.py` is deliberately a narrow v5 validator, not a permissive
all-version importer. Little-endian fixed-width fields are read with `struct` or
NumPy's explicit `<f4`/`<u2` dtypes. Unsupported types/versions fail closed.

| Structure | Checked layout |
|---|---|
| Header | 6-byte magic, u32 version, count |
| Texture | 32-bit active, bounded string, u32 byte size, embedded bytes |
| Material | name/shader strings, byte blend/alpha flags, 32-bit depth, property count, name+10 floats per property, mappings of slot-name/32-bit slot/texture-name |
| Node | 32-bit type, name, 32-bit child count, byte active |
| Dummy | 16 finite float32 matrix entries, children |
| Mesh | 3 byte flags, count, 44-byte vertices, index count, uint16 indices, material/layer, 6 finite float32 LOD/sphere fields, byte renderable, children |

Bounds: **32 MiB file**, **4,096-byte strings**, **32 textures/materials**,
**1 MiB per embedded texture**, **64 properties**, **32 bindings**,
**64 total nodes**, **depth ≤16**, **65,535 vertices per mesh**,
**3,000,000 indices per mesh**. Every read and count×stride is checked against
remaining bytes *before* consuming its payload. High-bit/negative signed counts
are rejected through the unsigned sanity ceilings. Recursion has both depth and
shared total-node budgets; EOF must be exact. Invalid UTF-8, empty/NUL strings,
duplicate names/properties, non-boolean flags, unknown candidate enums, nonfinite
floats and dangling material/texture references fail. NPZ loading disables pickle,
requires 12 unique entries, limits compressed size to 32 MiB and uncompressed
entries to 64 MiB; array keys/shapes/dtypes/index ranges/finite values are checked.
These are task-specific resource bounds, not a security claim for arbitrary KN5
or ZIP processing.

## Candidate invariants and source comparison

The expected identity root is `northern_hairpins_kn5_v001`. Its children must be
`1ROAD`, `PROVISIONAL_SHOULDER_L`, `PROVISIONAL_SHOULDER_R` and the identity wrapper
`VISUAL_TERRAIN_DERIVED_LOWERED`. That wrapper must have exactly `_SUB0` and `_SUB1`
mesh children. Parentage, type, child order/count and leaf status are checked.
The exact seven-name allowlist excludes reference terrain, debug meshes/text,
cameras, lights, curves and car dummies; mere triangle totals cannot satisfy it.

All mesh flags must be active/cast-shadows/visible/renderable=1, transparent=0,
layer=0, with expected material IDs 0/1/1/2/2. Indices must be in range and index
counts divisible by three. All vertex fields are finite. Normal/tangent lengths
must be within 1e-5 of unity; absolute dot product must be below 1e-5. Each
triangle must have strictly positive KN5 Y cross-product and agree with the
average corner normal, excluding degeneracy and reversed/non-upward winding.
Object AABBs match the original report exactly. Bounding spheres enclose every
vertex within **1 mm**, allowing float32 center/radius rounding (terrain SUB1's
maximum distance exceeds its stored radius by approximately 0.00000572 m).

| Mesh | Vertices | Triangles | Maximum index |
|---|---:|---:|---:|
| `1ROAD` | 30,673 | 12,000 | 30,672 |
| `PROVISIONAL_SHOULDER_L` | 8,452 | 3,000 | 8,451 |
| `PROVISIONAL_SHOULDER_R` | 8,404 | 3,000 | 8,403 |
| `VISUAL_TERRAIN_DERIVED_LOWERED_SUB0` | 65,531 | 130,025 | 65,530 |
| `VISUAL_TERRAIN_DERIVED_LOWERED_SUB1` | 41,627 | 82,375 | 41,626 |

Source NPZ `mesh0`…`mesh3` follows the four source names above. The validator maps
**(X,Y,Z) → (X,Z,−Y)** and **(u,v) → (u,1−v)** with unit scale and float32 storage.
It combines XYZ and UV into five-component corner records. For each triangle it
chooses the lexicographically smallest corner as the first and preserves the
remaining cyclic order, then sorts complete 60-byte triangle records. Signed zero
is normalized; **no positional/UV tolerance or quantization** is used. Sorted
multiset equality preserves duplicate multiplicity and corner seams, permits
cyclic rotation and arbitrary triangle/chunk order, and **does not permit reversed
winding**. The terrain chunks are compared as one union against mesh3, so splits
or vertex duplication do not weaken connectivity validation. Source/output union
bounds are additionally checked. All four multisets pass: 12,000 / 3,000 / 3,000 /
212,400 triangles. This verifies the exported artifact against the saved capture;
the capture itself comes from the exporter task, not a separately reopened Blender
scene or independently reacquired geographic truth.

Three materials must be `KN5_Asphalt`, `KN5_Gravel`, `KN5_Terrain`, using
`ksPerPixel`, opaque blend/depth=0, alpha-test off and exact float32 scalar values
0.4/0.6/0.05/10 for ambient/diffuse/specular/specular exponent, with the other nine
property components zero. Each has only `txDiffuse`, slot 0, bound respectively to
`kn5_asphalt.dds`, `kn5_gravel.dds`, `kn5_terrain.dds`. All DDS headers, masks,
reserved fields, caps, dimensions, pitch and mip count are checked: 4×4
uncompressed BGRA8, one mip, 192 bytes each. Every pixel must decode to RGBA
(48,50,52,255), (120,110,90,255), or (65,88,52,255). Thus nonwhite meaningful
placeholder colors and their bindings are validated, not merely DDS filenames.
They remain test surfaces, not finished material appearance.

## LOD_OUT=0: unresolved visibility-sensitive default

Every candidate mesh stores **LOD_IN=0 and LOD_OUT=0**. The independent AcTools
`ReadNode` identifies those exact two float fields as `LodIn`/`LodOut`;
`ExportIni_Node` and `ExportIni_TrackNode` pass them through as `LOD_IN`/`LOD_OUT`.
This establishes that they are named LOD fields used in the tool's node settings,
not unknown padding. It does **not** establish whether zero means unlimited,
engine fallback, immediate cutoff or something else in Assetto Corsa. No external
renderer/engine implementation or known-good game fixture demonstrating zero's
behavior was obtained within the three-request budget. The finite sphere data
passed static checks but does not settle LOD semantics.

**Warning, not a diagnosed bug:** zero LOD-out is a potentially visibility-sensitive
default requiring Windows ksEditor/AC loading and near/far visibility checks.
Nothing was patched, and static PASS must not be interpreted as proof the meshes
will render in-game. Other naming/culling/material/physics/session semantics also
remain subject to actual engine validation.

## Executed checks and safe reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 PROJ_NETWORK=OFF .venv/bin/python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/validate_kn5.py --output data/processed/kn5_test/independent_validation.json
```

Actual results: **129 project tests passed** (99 existing + **30 new**), exit 0,
1.044 seconds for the final suite. Evidence creation exited 0. Tests include the
real artifact, every truncation of a handwritten small v5 fixture, selected real
artifact truncations, invalid headers/versions/EOF/counts/strings/UTF-8/flags,
node recursion/total budgets, sparse oversized files, oversized vertex/index/
texture payload counts, out-of-range indices, all 11 vertex components and all six
LOD/sphere fields with NaN/Inf, all ten property components with NaN, DDS/header/
pixel corruption, bad normals/tangents/winding/spheres/bindings/visibility,
unintended geometry, and a vendor-import AST allowlist. Triangle tests distinguish
cyclic rotation from reversal, preserve duplicate multiplicity and reject changed
connectivity with identical counts/bounds and changed corner UVs. The deliberate
overwrite-refusal test emits an argparse error message; it is an expected passing
negative test, not a failed validation.

The CLI defaults to stdout only. `--output` creates a new file with exclusive
`'x'` mode and refuses an existing file before validation. There is no force flag.
To recheck without altering the preserved first evidence, omit `--output`.

**Not performed:** installs, live/background Blender execution, Windows, ksEditor,
Assetto Corsa load/render/driving, physics/collision, timing/session setup,
visual inspection, performance or VR. This is not an installable track package
and does not advance those acceptance gates. Geographic and provisional geometry
limitations in [KN5_STUDIO_TEST.md](KN5_STUDIO_TEST.md) remain unchanged.
