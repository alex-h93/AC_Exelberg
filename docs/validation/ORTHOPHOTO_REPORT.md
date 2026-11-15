# Bounded orthophoto inspection

## Scope and review outputs

Acquired **7,857,327 response-body bytes (7.857327 MB decimal)** in one persistent
200,000,000-byte operation. No full 12,921,674,133-byte TIFF, dense route bounding-box
mosaic, new dependencies, non-Python tools, Blender work or geometry changes.

Outputs: `data/processed/orthophoto/` contains six independent native RGB GeoTIFFs,
matching `_clean.png` and `_route.png` files, `contact_sheet.png`, two anomaly
hillshade review PNGs, and `manifest.json` (bounds, transforms, source windows,
tile indices, statistics, checksums, provenance and software versions).

Contact sheet order, left-to-right then top-to-bottom:

| Patch | Profile chainage (m) | Source bounds xmin, ymin, xmax, ymax (m) |
| --- | ---: | --- |
| anomaly | 9589 | -8177.6, 346430.4, -7927.4, 346680.6 |
| start | 0 | -12956.6, 351328.6, -12706.4, 351578.8 |
| doppler_vicinity | 2460 | -12806.2, 350546.8, -12556.0, 350797.0 |
| scheiblingstein_vicinity | 7950 | -9232.2, 347389.4, -8982.0, 347639.6 |
| exelberg_vicinity | 11950 | -6418.0, 345504.6, -6167.8, 345754.8 |
| finish | 15226.292 | -4723.4, 344945.6, -4473.2, 345195.8 |

Chainages follow the existing EPSG:3035 terrain profile, not the spherical 15.205 km
route measure. Centers interpolate longitude/latitude from `route_elevation.csv`.
The anomaly center is longitude **16.2236839531**, latitude **48.2573088177**.
Landmark-vicinity chainages were fixed after checking nearest profile positions to
the preserved named OSM nodes; they are representative route positions, not claims
that a patch contains every landmark structure. Exelberg peak itself is off-road.

Each patch is 1251 × 1251 pixels, **250.2 × 250.2 m** after outward native-grid
rounding. No source RGB resampling or raster reprojection. PNGs are review images;
use GeoTIFF georeferencing for GIS. North is up in the source grid. Magenta marks
the provisional OSM line; cyan marks **9590 m** on anomaly overlays. Clean PNGs
have no marks. Contact sheet is decimated for review; full-resolution PNGs remain.

## Source, georeferencing and coordinate accuracy

- BEV Operat2024460, registered source:
  <https://data.bev.gv.at/download/DOP/20250415/2024460_Mosaik_RGB.tif>.
- Metadata/license reference:
  <https://doi.org/10.48677/1f33a105-0798-4696-92c2-df985c6f40a9>;
  **© BEV, CC BY 4.0**. Route **© OpenStreetMap contributors, ODbL**.
  Outputs are identified as derived subsets/overlays, not original BEV publications.
- BigTIFF, 375000 × 210000, uint8 × 3, contiguous YCbCr, JPEG compression,
  512 × 512 tiles, shared 142-byte JPEGTables, **301263 tiles**.
- Source EPSG:31256, PixelIsArea. Upper-left corner **(-26250, 371000)**,
  pixel scales **(0.2, 0.2)**, north-up affine
  `x=-26250+0.2*column; y=371000-0.2*row`. Pixel centers add 0.5.
  Overall source bounds: **[-26250, 329000, 48750, 371000]**.
- Only the first IFD is used. Next IFD pointer 3615922 is recorded but not followed;
  no overview acquisition or COG-conformance assertion.
- PROJ networking explicitly disabled. `TransformerGroup(31256,4326,
  always_xy=True,allow_ballpark=False)` reports best_available=True; no unavailable
  operations or grid dependencies. Available operations: MGI→WGS84 (3), accuracy
  **1.5 m**, and MGI→WGS84 (8), accuracy 0.5 m, both grid-free. The reproducible
  choice is PROJ's first-ranked operation (3), a seven-parameter Helmert operation.
  Full pipeline, alternatives, PROJ version and axes are recorded in the manifest.
- EPSG:31256 formally declares northing/easting axes. `always_xy=True` explicitly
  normalizes to **easting,northing** for TIFF x/y and **longitude,latitude** for
  EPSG:4326. Route→source uses the inverse of that same selected operation.
  Offline tests check axis magnitudes, roundtrip and overlay row direction.
- **No submetre registration claim.** Transformation accuracy is not a measured
  imagery accuracy or OSM positional error, and pixel size is not accuracy.

Capture dates and local source-survey dates remain **unknown**. The URL release
path `20250415`, Operat identifier, HTTP Last-Modified (2025-02-06) and acquisition
request dates are not evidence of route-area capture date. No catalogue was fetched
and no newer-imagery claim is made. DOI/license provenance is inherited from the
existing source register; its original metadata evidence is untouched.

## Exact operation accounting and safeguards

`data/raw/orthophoto/operation.json` is the persistent, separate ledger, reusing
`scripts/terrain_ranges.py` with a **200 MB** cap. Original compressed ranges and
SHA256s remain there, including superseded exploratory tiles. Repeated runs never
reset the operation. Requests require exact HTTP 206 Content-Range, strong ETag,
identity encoding, and If-Match after initial ETag establishment. Source ETag:
`"302311995-62d819976e140"`. The first request establishes object identity; all
following requests carry If-Match. Protocol failures stop without reading bodies.
All returned body bytes, including partial retries, are charged by RangeReader.

Header/IFD/georeferencing/tile tables were obtained **before any pixels**. Logical
metadata: **3,615,921 bytes**, below the 5 MB metadata limit. Metadata transfers
were preflighted for two attempts. Exact selected tile sums were persisted before
pixel transfer; no compressed-size guess or full-object read was used.

| Selection/accounting | Tiles | Compressed pixel bytes | Metadata + pixels, two attempts |
| --- | ---: | ---: | ---: |
| Initial rough landmark selection | 70 | 3,075,462 | 13,382,766 |
| Final six patches | 67 | 2,925,899 | 13,083,640 (selection only) |
| Entire operation union, including superseded tiles | 96 | 4,241,406 | **15,714,654** |

The corrected landmark selection added **1,165,944 bytes**, not a new operation.
The entire union plus metadata fits with two attempts. Runtime preflight also adds
actual historical transfers to twice the remaining missing bytes. If the selection
or retry allowance cannot fit, acquisition stops; it is not split to bypass caps.

Actual: **107 successful 206 range requests**, no HTTP failures/partial retries;
**3,615,921 metadata + 4,241,406 pixels = 7,857,327 bytes**. No supporting-document,
catalogue, grid or dependency downloads. An initial local TIFF export rejected a
non-ASCII copyright symbol; it was fixed to ASCII and rebuilt from cache, with no
additional pixel downloads for that fix. Initial selection, retained tile history,
current estimate and execution logs are in `data/interim/orthophoto/`.

## Pixel validity, original-window verification and interpretation

`tifffile.TiffPage.decode(..., jpegtables=page.jpegtables)` supplies shared JPEG
tables, subsampling and YCbCr→RGB handling. Before source-pixel acquisition, an
offline generated 512-square YCbCr JPEG fixture separated DQT/DHT tables into
JPEGTables and verified bit-exact decode against `imagecodecs.jpeg_decode` of the
complete JPEG in RGB mode. Exported lossless RGB windows are then compared exactly
against independently reassembled decoded original source windows.

All **9,390,006 exported RGB pixels** verified exactly. Every patch contains
1,565,001 finite pixels. Exact-black and near-black (all channels ≤5) fractions
are **0.0 for all six patches**. Per-channel means, extrema, output checksums and
RGB checksums are in the manifest. Finiteness of uint8 pixels and absence of black
are **not guaranteed semantic coverage**, cloud/shadow detection, asphalt masks
or proof of an unobscured road. No unverified imagery nodata convention is imposed.
Only these six small windows were checked; full-corridor imagery coverage remains
unverified.

The contact sheet and anomaly imagery/hillshade overlay were visually inspected.
The provisional route broadly follows the visible road at this review scale;
this is not a measured alignment residual or final alignment approval. Vegetation
and shadows remain important limitations. No black region was treated as a hidden
road, and no road or terrain geometry was corrected.

Anomaly hillshade uses the existing EPSG:3035 DTM, sampled strictly bilinearly at
approximately 1 m onto source-imagery pixel centers, with invalid samples red.
Its grid-free source→3035 operation reports **1.5 m** accuracy; valid fraction
is **1.0**. Hillshade and blend are separate review PNGs, never replacements for
native RGB exports. They help relate local terrain context to the 9590 m marker
but do not resolve the narrow terrain dip's physical cause.

**Orthophotos alone cannot measure asphalt elevation, longitudinal grade, camber,
roughness or concealed structures.** The existing DTM dip remains unresolved;
seek ground-level reference/control and coordinator review before road modeling.

## Reproduction and checks

Run from project root, using existing `.venv` only:

```sh
# Offline rebuild: requires preserved ledger and original range cache.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/inspect_orthophoto.py --pixels --offline
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/validate_orthophoto.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -q
```

`inspect_orthophoto.py` defaults to metadata/estimate only; pixel acquisition needs
`--pixels`. Offline mode rejects any cache miss. Do not delete/reset its ledger.

- **72 offline unit tests passed**, including 9 new imagery tests for shared-table
  decode, georeferencing/window assembly, mask semantics, axes/overlay, metadata
  bounds, range protocol and persistent retry accounting.
- Strict offline source validator: six patches, 67 source tiles, 9,390,006 exact
  RGB pixels; TIFF affine/CRS, clean PNG equality, checksums, profile/route identity
  and statistics checked. Ledger unchanged.
- Cache-only rebuild verified **every GeoTIFF, PNG, manifest and ledger SHA256
  unchanged**. Evidence: `data/interim/orthophoto/rebuild-verification.json`.
- Existing terrain scripts/cache, route/profile, main status and source register
  were not edited. No Blender/game/VR validation occurred.

Remaining blockers: unknown capture dates, unmeasured imagery/OSM registration,
full-route imagery coverage not yet checked, and unresolved terrain-anomaly cause.
