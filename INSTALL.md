# Installation

## Requirements

- **Assetto Corsa** (PC, Steam). Works on Windows, and on Linux through Steam Proton.
- About **550 MB** of free disk space for both tracks (~260 MB each).
- *Optional:* [Custom Shaders Patch](https://acstuff.club/patch/) (CSP) for 3D grass. The
  track also runs on the original game.
- *Optional:* [Content Manager](https://acstuff.club/app/) for easy installation.

## 1. Download

Get the track archive from the
[Releases page](https://github.com/alex-h93/AC_Exelberg/releases) or from
OverTake.gg. It contains two track folders:

```
exelberg_full_v011/      Königstetten → Neuwaldegg roundabout
exelberg_reverse_v011/   Neuwaldegg roundabout → Königstetten
```

You can install either folder or both.

## 2a. Install with Content Manager (easiest)

1. Start Content Manager.
2. Drag the downloaded archive onto the Content Manager window.
3. Click **Install** in the panel that appears. Both tracks are installed.

## 2b. Install manually

Copy both folders into the game's `content/tracks` folder, so that the `.kn5` files sit
**directly** inside each track folder:

```
assettocorsa/
└── content/
    └── tracks/
        ├── exelberg_full_v011/
        │   ├── exelberg_full_v011.kn5
        │   ├── exelberg_v011_scenery.kn5
        │   ├── models.ini
        │   ├── ai/  data/  extension/  ui/
        │   └── ...
        └── exelberg_reverse_v011/
            ├── exelberg_reverse_v011.kn5
            └── ...
```

Where the game folder usually is:

| System | Path |
| --- | --- |
| Windows | `C:\Program Files (x86)\Steam\steamapps\common\assettocorsa\content\tracks\` |
| Linux (Steam/Proton) | `~/.local/share/Steam/steamapps/common/assettocorsa/content/tracks/` |
| Linux (Flatpak Steam) | `~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/assettocorsa/content/tracks/` |

If you're not sure, right-click Assetto Corsa in Steam and choose **Manage → Browse
local files**, then open `content/tracks`.

## 3. Drive

1. In Content Manager (or the original launcher), choose **Drive → Practice**.
2. Choose the track **Exelberg Full v011** or **Exelberg Reverse v011**.
3. Pick any road car and start the session. **Solo only**: there is one pit box and no AI.
4. Each run is timed from the start gate to the finish gate. The time is shown as a lap time.
5. After the finish, brake: the road ends at an invisible wall after the run-off
   (about 100 m on the forward track, about 110 m on the reverse track).

To start a new run, use **Restart session** or teleport back to the pits.

## Updating from an older version

Each version has its own folder, for example `exelberg_full_v010`. Older versions can stay
installed next to the new ones, or you can delete their folders from `content/tracks`.

## Uninstall

Delete the folders `exelberg_full_v011` and `exelberg_reverse_v011` from `content/tracks`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| **"Track not found"** or the track is missing from the list | The folder is nested one level too deep (e.g. `tracks/exelberg_full_v011/exelberg_full_v011/`). Move it up so that the `.kn5` files are directly inside `tracks/exelberg_full_v011/`. |
| Grass looks flat or missing | 3D grass needs Custom Shaders Patch. Without it, the ground is textured but flat. |
| Low frame rate | Lower *World detail* and *Shadow resolution* in the video settings. The track has many trees and buildings. |
| No lap time after the finish | Drive through the start gate from the spawn. A run counts only when you cross both gates in the right direction. |

## Building from source

Building the tracks from source is only needed for development. See
[README.md](README.md#how-it-is-built). The pipeline needs Python 3 with the
packages in `requirements-*.txt` (in a local `.venv`), Blender, and the BEV/OSM source
data, which the acquisition scripts download from the original providers.
