# M0 Local Tool Inventory

Inventory date: 2026-10-25 (environment UTC clock). Read-only checks; no software installed, data downloaded, disk mounted, or game files modified.

## Authoring environment

- Fedora-based Bazzite Linux (`x86_64`, kernel `7.2.9-ogc3.1.fc44`); 12 logical CPUs, Intel Core i5-12400, approximately 62 GiB RAM.
- Python 3.14.8 available; standard-library `venv` support works. At initial inventory
  no `.venv` existed; terrain processing subsequently created it (see below).
- Python modules: Pillow is importable. NumPy, SciPy, Shapely, GeoPandas, Rasterio, pyproj, Fiona, `osgeo`/GDAL bindings, trimesh, and bpy are unavailable to this Python.
- Initial inventory found no Blender/QGIS/GDAL tools; Blender was subsequently
  installed by the user and verified as described below. QGIS/GDAL CLI remain
  unavailable but are not prerequisites for the prepared-data workflow.
- Blender is a Flatpak, not a PATH executable. Python GIS libraries, if needed,
  must be installed only in the project `.venv`.

## Storage and game environment

- Project filesystem: Btrfs `/dev/sda3`, 929G total, 363G used, 564G available.
- `/boot` is ext4 on `/dev/sda2`; EFI is vfat on `/dev/sda1`. `lsblk` showed additional 931.5G `/dev/nvme0n1` without a reported filesystem or mountpoint; not investigated or mounted. No Windows partition identified among mounted filesystems.
- Steam executable and Steam directories exist; Steam version check timed out. Proton installation, Windows Assetto Corsa, SDK/ksEditor, Content Manager, and CSP status are unknown. Do not infer absence from CLI checks.
- Windows may be on the unmounted device/partition; Windows game and private data were not read. Windows AC/version, SDK, and CSP require user-accessible Windows inventory.

## Approvals / next decisions

No non-Python installation approval is implied. If needed, request approval before installing Blender (authoring/export), QGIS or GDAL (GIS tooling), or any other non-Python tools. Larger data acquisition remains separately subject to the plan's prior approval threshold.

## Subsequent Python-only setup

Terrain processing created project `.venv` and installed binary wheels there:
NumPy, pyproj, tifffile, imagecodecs and certifi. Exact versions are pinned in
`requirements-terrain.txt`; installation evidence is under `data/interim/terrain/`.
No system/user Python libraries or non-Python tools were installed. The module
availability list above records the initial system Python, not this environment.
On 2026-11-15 the system Python had moved 3.14 → 3.15, breaking `.venv`; it was
upgraded in place (`python3 -m venv --upgrade`) and the same pinned wheels
reinstalled for 3.15; all 287 tests pass. Run the complete test suite with `.venv/bin/python`; system Pillow remains available
for the optional preview-rendering scripts.

## User-installed Blender — verified

The user installed `org.blender.Blender` (system Flatpak). Actual headless checks
confirm **Blender 5.2.0 LTS**, embedded Python **3.13.13**, bundled NumPy **2.3.4**.

- Launch: `flatpak run org.blender.Blender` (no PATH `blender` required).
- Existing sandbox permissions permit reading the project route and terrain files.
- Shipped FBX exporter successfully exported a temporary synthetic triangle;
  temporary `.blend` save/reload and cleanup also passed.
- No addons, overrides, embedded Python packages or installations were needed.
- These checks do not validate GUI/GPU performance or Windows ksEditor compatibility.
- Evidence and repeatable command: [BLENDER_READINESS.md](validation/BLENDER_READINESS.md).

No additional software is currently required to prepare the first Blender scene.
Remaining project work: metric/local-coordinate handoff, prepared prototype terrain
and road geometry. Windows SDK/ksEditor availability and FBX→KN5/game behavior are
still unknown rather than confirmed missing. Ask before any later non-Python install.

## User-installed extensions and live bridge

- **AC Tools 0.1.6** is installed and enabled. Source inspection confirms authoring
  helpers and FBX export for ksEditor, **not direct KN5 generation**. Its default
  scale/path/overwrite behavior differs from our controlled exporter; do not run
  setup/export against original project or game files without staging/review.
  See [AC_TOOLS_READINESS.md](validation/AC_TOOLS_READINESS.md).
- **Blender Lab MCP 1.0.3** is installed and enabled, listening at loopback
  `127.0.0.1:9876`. A fixed read-only query via its TCP bridge succeeded; no extra
  MCP server/adapter installation was needed. This is direct bridge access, not
  a registered Pi MCP tool. See [BLENDER_MCP_OPTIONS.md](validation/BLENDER_MCP_OPTIONS.md).
- Running Blender has the prototype loaded and reports **unsaved changes**.
  Preserve the user's live scene; do not reload/overwrite it implicitly.

## Approved direct KN5 exporter installation

After explicit user approval, installed **KN5 Studio 2.6.0** unchanged at
`extensions/user_default/kn5_studio`, pinned to
`f17bc2322adbe5a9d4b53165b44f7b8ddb9aa8e9` (CC0). Archive: 113,304 bytes.
No other software/libraries installed. Persistent GUI enabling was deferred;
separate headless factory processes registered it in memory and successfully
exported KN5 v5. Existing preferences and the unsaved GUI scene were untouched.

The direct KN5 passed independent static/source-geometry checks, but actual AC
loading/LOD/material/collision behavior is untested. See
[KN5_STUDIO_TEST.md](validation/KN5_STUDIO_TEST.md) and
[KN5_INDEPENDENT_VALIDATION.md](validation/KN5_INDEPENDENT_VALIDATION.md).
ksEditor remains an optional fallback rather than a required export backend.

## Subsequent local Assetto Corsa installation

User-supplied path `/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa`
now exists, with `acs.exe`, launcher, SDK `sdk/editor/ksEditor.exe`, and stock tracks.
Steam manifest build ID: **14923034**. Proton 10.0 and Experimental are present;
Wine is not on PATH. Targeted CSP/Content Manager candidates were absent, but no
installation is needed for our vanilla test candidate. Actual base-game/Proton
launch and compatibility settings have not been validated or modified.

See [local inventory](validation/LOCAL_AC_INSTALLATION.md). A static-checked test
package is staged; installer dry-run passed, with no game-directory changes.
Current Linux game testing can proceed once deployment/launch are explicitly
authorized; booting Windows is not required for that experiment.
