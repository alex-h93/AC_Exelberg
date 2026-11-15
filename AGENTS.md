# Assetto_Exelberg agent routing

## Project rules and roadmap

Read `IMPLEMENTATION_PLAN.md` before implementation and `docs/DATA_SOURCES.md` before geographic-data acquisition.

- Python libraries must be installed only in the project-local `.venv`, never globally or into system/user Python.
- Ask the user before installing any non-Python software, plugins, game tools, or system packages.
- Ask before downloads larger than 1 GB (conservatively 1,000,000,000 bytes), including cumulative transfers within one acquisition operation. Never split requests to bypass approval. Ask first if size is unknown and potentially larger.
- Project file writes are allowed. Preserve original data and existing game/source assets; keep generated outputs separate.
- Current scope: private-use, FULL approximately 15.2 km route (not just northern prototype), Königstetten to Marswiese only, TWO-LANE road, solo driving and timed point-to-point runs. Nominal two 3 m lanes are provisional, not measured widths. v001 loaded in the user's game but spawned backwards; v002 explicitly reverses yaw. Temporary safety barriers and procedural scenic assets must not be presented as faithful surveyed surroundings. User confirmed v002 heading/performance/asphalt appearance but reported barrier pass-through and car launches; v003 is a runtime-unverified collision revision, not a proved fix. Requested invisible containment is 3 m beyond each asphalt edge (±6 m centerline), with nominal 33 m visual roadside posts. Preserve v002's successful spawn/asphalt. Ground physics should not be reclosed with internal chunk caps; use role-aware wall/ground flags and actual final-ground coverage tests. Local Steam/Proton Assetto Corsa is now installed and may be used for authorized runtime tests; Windows remains a fallback. Quest 2 VR is a planned validation target. Do not launch the game, change global Steam/Proton settings, or deploy test content without explicit authorization; the package installer defaults to dry-run.
- Treat roadmap milestones as work to perform and verify, not as completed capabilities. Do not install or acquire large datasets merely because a plan lists them.

## Routing

The main session coordinates using openai-codex/gpt-6.1-sol with high thinking.
Use the project `subagent` tool with `agentScope: "project"` for scoped work:

| Agent | Model / thinking | Tasks |
| --- | --- | --- |
| blender | gpt-6.1-sol / high | Blender modeling, geometry, materials, Blender-specific Python |
| python | gpt-6.1-sol / medium | General Python implementation, automation, tests |
| luna | gpt-6-luna / low | Discovery, summaries, simple bounded changes |
| terra | gpt-5.6-terra / low | Mechanical edits, documentation, simple checks |

Keep architecture, task assignment, integration, and final review in the coordinator.
Delegate substantive implementation rather than doing it all in the high-thinking session.
Skip delegation when its overhead would exceed the task itself.
Give each agent a narrow objective, relevant paths, acceptance criteria, and explicit write ownership.
Parallelize only independent tasks; never let agents edit the same files or Blender scene concurrently.
Request concise summaries (paths, results, blockers), not full transcripts or source dumps.
Subagents should execute their assigned work directly without further delegation.
Never claim Blender execution, tests, or visual inspection occurred unless actually performed.
