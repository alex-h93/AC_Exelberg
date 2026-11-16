# Installation

## Requirements

- **Assetto Corsa** (PC, Steam). Works on Windows, and on Linux through Steam Proton.
- About **720 MB** of free disk space for both tracks (~360 MB each).
- *Optional:* [Custom Shaders Patch](https://acstuff.club/patch/) (CSP) for extra grass across
  the whole landscape. The track, including its verge grass, runs on the original game.
- *Optional:* [Content Manager](https://acstuff.club/app/) for easy installation.

## 1. Download

Get the track archive from the
[Releases page](https://github.com/alex-h93/AC_Exelberg/releases) or from
OverTake.gg. It contains two track folders:

```
exelberg_full_v014/      Königstetten → Neuwaldegg roundabout
exelberg_reverse_v014/   Neuwaldegg roundabout → Königstetten
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
        ├── exelberg_full_v014/
        │   ├── exelberg_full_v014.kn5
        │   ├── exelberg_v014_scenery.kn5
        │   ├── exelberg_v014_grass.kn5
        │   ├── models.ini
        │   ├── ai/  data/  extension/  ui/
        │   └── ...
        └── exelberg_reverse_v014/
            ├── exelberg_reverse_v014.kn5
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
2. Choose the track **Exelberg Full v014** or **Exelberg Reverse v014**.
3. Pick any road car and start the session. **Solo only**: there is one pit box, so no AI
   opponents. The ideal line (driving assist) works.
4. Each run is timed from the start gate to the finish gate. The time is shown as a lap time.
5. After the finish, brake: the road ends at an invisible wall after the run-off
   (about 100 m on the forward track, about 110 m on the reverse track).

To start a new run, use **Restart session** or teleport back to the pits.

In replays, press **F3** to switch between the three TV camera sets.

## Updating from an older version

Each version has its own folder, for example `exelberg_full_v013`. Older versions can stay
installed next to the new ones, or you can delete their folders from `content/tracks`.

## Uninstall

Delete the folders `exelberg_full_v014` and `exelberg_reverse_v014` from `content/tracks`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| **"Track not found"** or the track is missing from the list | The folder is nested one level too deep (e.g. `tracks/exelberg_full_v014/exelberg_full_v014/`). Move it up so that the `.kn5` files are directly inside `tracks/exelberg_full_v014/`. |
| Grass clumps missing next to the road | Check that `exelberg_v014_grass.kn5` (or `exelberg_reverse_v014_grass.kn5`) is in the track folder. Clumps are only drawn within about 75 m of the camera. |
| First load hangs on the loading screen | Close the game and start it again. This happened once right after installing and could not be reproduced. |
| Low frame rate | Lower *World detail* and *Shadow resolution* in the video settings. The track has many trees, buildings and grass clumps. |
| No lap time after the finish | Drive through the start gate from the spawn. A run counts only when you cross both gates in the right direction. |

## Building from source

Building the tracks from source is only needed for development. See
[README.md](README.md#how-it-is-built). The pipeline needs Python 3 with the
packages in `requirements-*.txt` (in a local `.venv`), Blender, and the BEV/OSM source
data, which the acquisition scripts download from the original providers.
