# Blender MCP bridge: local assessment

Inspected the installed Blender Lab extension at `/var/home/haze/.var/app/org.blender.Blender/config/blender/5.2/extensions/lab_blender_org/mcp` (manifest v1.0.3; Blender minimum 5.1). No README or local usage documentation was present.

## Findings

- This is a **TCP bridge hosted by Blender**, not a standalone MCP stdio server. The add-on accepts null-byte-delimited JSON requests over its socket; no stdio MCP server launcher or stdio transport implementation is included in this directory. Native MCP integration would need an adapter, but project Python can communicate directly with the installed bridge without another installation.
- The only supplied launch command is for Blender background mode: `blender --background file.blend --command blender_mcp`. It runs the add-on's blocking TCP bridge, not an MCP stdio process. CLI accepts `--host` and `--port`; defaults in `mcp_to_blender_server.py` are `localhost:9876`. Background mode does not support deferred responses. The interactive add-on UI also starts the TCP bridge.
- No external Python package imports are evident in the bridge sources; it imports Blender's `bpy` and Python standard-library modules. The bridge therefore needs a compatible Blender executable with this extension available/enabled. An independent stdio wrapper's dependencies and connection protocol are unknown and would need separate research/approval; none was installed.
- Source executes Blender Python code using a weak sandbox. This is not a security boundary or a read-only service; only a reviewed, fixed metadata query was sent in the subsequent check. Keep the bridge on loopback and do not expose it externally.
- The initial listener check was empty. A coordinator check subsequently found **127.0.0.1:9876** listening in the user's already-running Blender. No server was started by the assistant.

## Actual connection check

A bounded standard-library socket client sent one fixed read-only `execute` request
(`strict_json: true`) and successfully received a null-delimited JSON response.
Evidence including exact request: `data/processed/blender_bridge/readiness.json`.
No standalone MCP adapter, Python package, or other software was installed.

The running interactive application reports Blender **5.2.0 LTS**, the project
prototype loaded, **32 scene objects**, and both AC Tools and MCP enabled. The AC
Tools FBX operator is registered. **The scene has unsaved changes**; do not reload,
replace, close, or save over it without checking with the user. The query did not
invoke operators or alter scene data/preferences.

No native Pi MCP tool was registered. Direct local bridge access through Python
is working, which suffices for project automation without installing an adapter.