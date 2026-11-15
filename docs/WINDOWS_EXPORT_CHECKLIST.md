# Windows validation and optional FBX/SDK fallback

**Current status:** direct Blender → KN5 export now works and passed independent
static/source-geometry checks. **No Windows/game loading has been tested.**

## Direct-export handoff (older standalone artifact)

**Update:** a separate static-checked solo package now exists at
`build/ac_test_v001/exelberg_north_proto_v001/`. The local Steam/Proton install
can be tested first; see [local test guide](LOCAL_TEST_GUIDE.md). Deployment is
not yet performed. The standalone artifact below predates package configuration.

- Artifact: `exports/kn5_prototype_v001/northern_hairpins_kn5_v001.kn5`.
- See [export evidence](validation/KN5_STUDIO_TEST.md) and
  [independent checks](validation/KN5_INDEPENDENT_VALIDATION.md).
- Current KN5 lacks the surrounding spawn/session/surface configuration; do not
  copy the standalone file into `content/tracks` and expect a playable track.
- Resolve/configure/test `LOD_OUT=0` visibility semantics, prepare a separate
  versioned test package, and confirm the actual Windows game path before deployment.
- Game tests must check near/far visibility, scale/axes, materials and collision,
  then spawn/reset/timing as those features are added. Never overwrite other tracks.
- ksEditor is now **optional** as a fallback or diagnostic tool. The older FBX
  workflow below is retained for that purpose, not a mandatory installation.

## Optional FBX/SDK fallback checklist

## 1. Prepare safely

- Boot the separate Windows partition. Do not modify the Linux source assets.
- In Steam, locate Assetto Corsa: Library → Assetto Corsa → Properties → Installed Files → **Browse**. Record the actual game path and installed game version.
- Locate the Assetto Corsa SDK and `ksEditor` from that installation or its installed SDK/editor location. A likely candidate is `sdk/editor`, but it is not guaranteed. Record the executable path, SDK/editor version, and any launch error.
- Optionally record whether Content Manager and CSP are present and their versions. They are not prerequisites for this FBX preview.
- Do not install SDK tools, Content Manager, CSP, plugins, or other non-Python software without approval. Ask before any download over 1 GB (or unknown potentially over 1 GB).

## 2. Transfer only the test FBX

- Use an approved cross-OS transfer path that preserves original game content (for example, a read-only/shared copy method or removable storage).
- Copy `exports/northern_hairpins_v001.fbx` to a separate Windows test workspace, **not** to `content/tracks`.
- Preserve `blender/northern_hairpins_v001.blend` and the original FBX unchanged; do not overwrite either.

## 3. ksEditor FBX preview

- Open the copied FBX in ksEditor and inspect metre scale: the road should be approximately 1.5 km long.
- Check axes/orientation, normals/winding, and material mapping.
- Expect simple Blender Principled materials, not verified Kunos game shaders; assign/test SDK-compatible shaders only as a conversion experiment.
- Compare imported mesh topology with this reference:

| Mesh | Vertices | Triangles |
|---|---:|---:|
| `1ROAD` | 7,505 | 12,000 |
| `PROVISIONAL_SHOULDER_L` | 3,002 | 3,000 |
| `PROVISIONAL_SHOULDER_R` | 3,002 | 3,000 |
| `VISUAL_TERRAIN_DERIVED_LOWERED` | 106,855 | 212,400 |
| **Total** | **120,364** | **230,400** |

- `1ROAD` is a provisional visual/physics-candidate mesh name, not final collision configuration.

## 4. Stop at the validation gate

- This FBX has no spawns, pits, timing, track configuration, surfaces configuration, or validated collision/session setup. Do **not** promise that it will load in-game.
- First verify successful SDK/ksEditor KN5 conversion and record errors/screenshots.
- Only after that validation, design an installable test in a uniquely named track folder; do not overwrite or place experimental files among existing game content.

## Return before further game steps

Provide the actual game path, ksEditor availability/version or error, and screenshots of the FBX preview/conversion results.
