# Local Assetto Corsa installation inventory

Read-only inventory of `/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa` (Steam app 244210). No game launch, installs, downloads, mounts, or game/config writes were performed.

- **Install:** root exists; `acs.exe` (22,890,776 bytes), `AssettoCorsa.exe` (5,364,224 bytes), and `acs_x86.exe` are present. `appmanifest_244210.acf` identifies Assetto Corsa, install directory `assettocorsa`, build ID **14923034**. Steam compatibility configuration was not conclusively read: the targeted search encountered an unrelated cache occurrence, not the app compatibility setting.
- **SDK/editor:** `sdk/editor/ksEditor.exe` is present, along with SDK editor support files and `sdk/dev` tools. The inspected editor docs directory contains only an FBX export-settings image; no relevant spawn/timing/track-configuration README was found in the checked locations.
- **Track examples:** built-in `content/tracks` includes `ks_highlands` and `ks_drag`. Highlands has multiple layouts, `models_layout_*.ini` and layout-specific `data/surfaces.ini`; drag has distance-specific layouts and surfaces files. These show packaging examples, not a complete track recipe. Sampled conventional `ui_track.json`/`models.ini` candidates were not found at the checked paths.
- **Proton/tools:** Steam common directory has `Proton - Experimental` and `Proton 10.0`. `wine` and `wine64` were not found on PATH. No conclusion about AC functionality under Proton can be drawn from this inventory.
- **CSP/launcher:** root `extension/` and `dwrite.dll` are absent. Checked Content Manager executable candidates and the checked compatdata CSP path are absent. This is limited-path evidence, not proof they exist nowhere else.

No game compatibility or runtime behavior was tested.