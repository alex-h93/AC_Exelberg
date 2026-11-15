# Direct KN5 export alternatives — source review, not runtime acceptance

## Answer

Direct Blender-to-KN5 add-ons exist. ksEditor is therefore **one possible export
backend, not an unavoidable requirement**. The installed AC Tools 0.1.6 remains
FBX-only; a different exporter would be needed for direct KN5 output.

Initial research was read-only. **Subsequently, the user approved KN5 Studio**:
its pinned 2.6.0 revision was installed and produced a direct KN5 v5 in isolated
Blender, with independent static/source-geometry checks passing. The user's open
scene was not changed. See [export test](KN5_STUDIO_TEST.md) and
[independent validation](KN5_INDEPENDENT_VALIDATION.md). This is not game acceptance;
LOD_OUT=0 semantics and actual engine behavior remain unresolved.

## Candidates

### Assetto Corsa KN5 Studio — first isolated test candidate

- Repository: <https://github.com/FatihEsen/KN5Export>
- Reviewed commit: `f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9`.
- README explicitly claims Blender 3.6/4.x/5.0/5.2, direct KN5 v5/v6 import/export,
  Kunos material presets and internal DDS encoding; license CC0.
- Actual `kn5_format.py` and `exporter.py` implement binary writing, not a wrapper
  around ksEditor. No external converter required by the inspected export path.
- Explicit selection/collection targeting, evaluated meshes, converted normals/
  tangents and automatic uint16 mesh splitting are present in source.
- New project with no independently demonstrated game acceptance here. Identified
  risks include tangent deduplication, evaluated-mesh cleanup and car-oriented
  defaults. Untextured materials can become white DDS rather than preserving
  Principled base colours. Scene appearance must be configured explicitly.
- Source tests cover binary/DDS/presets, not our Blender export or game loading.

### Blender Assetto Corsa Tools — alternative direct writer

- Repository: <https://github.com/I-Rinka/blender-assetto-corsa-tools>
- Reviewed commit: `0c75b3d12d8bc2257a73a7f13e4bde81a33861b8`.
- Based on <https://github.com/moppius/blender-assetto-corsa-tools> and the original
  Hagnhofer exporter; GPL-3.0; README minimum Blender 3.0.
- Actual `exporter/kn5_writer.py` / `node_writer.py` write KN5 v5 directly using
  Python binary serialization. A headless `cli_export.py` is documented.
- Track materials/settings, image textures and mesh splitting are supported.
  INI/session configuration and AI remain separate work.
- Source-level risks for this project: legacy image-node properties, normal/
  tangent transform handling, parented meshes, and export of hidden reference/
  debug datablocks unless excluded using the add-on's conventions. CI inspected
  was lint/package, not a Blender/game regression suite.

`kn5conv`/common KN5-to-OBJ converters are the opposite direction and do not solve
Blender-to-KN5 export. No authoritative ksEditor command-line interface was verified.

## Test protocol (installation/export/static checks completed; game gate open)

1. Obtain permission to install the chosen non-Python Blender extension. Preserve
   its exact reviewed revision and inspect all execution paths before enabling.
2. Do not reload, overwrite or alter the user's unsaved interactive scene. Use
   a separate headless process and a separately versioned copy of the saved prototype.
3. Export an explicit allowlist of the four intended meshes; exclude original
   terrain, raw reference curves, debug labels, cameras and lights.
4. Keep car-fixing/skin-copy/automatic configuration tools disabled. Write only to
   a fresh project staging directory, never the Windows game installation.
5. Assign explicit Kunos shaders and minimal image textures; do not assume Blender
   Principled materials translate correctly.
6. Check coordinates, units, winding, UVs, material/texture references, node
   hierarchy and splitting. The 106,855-vertex visual terrain exceeds a single
   uint16-indexed node; verify every output chunk and total triangles/bounds.
7. Read/validate the binary independently where feasible, then test on Windows
   Assetto Corsa. A same-library roundtrip alone is insufficient game validation.
8. Generate surfaces/spawns/session configuration separately. A KN5 is not itself
   an installable/timing-ready track package.

Blender export can be automated via headless Python or the already-working local
bridge; no new MCP adapter is necessary for this test. Windows driving/visual/
physics validation remains necessary regardless of exporter choice.
