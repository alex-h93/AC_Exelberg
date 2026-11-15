# Landscape orthophotos v003 — prepared, not integrated

## Result

Generated **26 RGB PNG textures** for the 26 entries with valid cells in the
original 63-entry `tile_node_slices` array. Original chunk indices are retained;
empty chunks are omitted. Resolution is **2 × 2 m/texel**, north-up, maximum
512 × 512 pixels (edge dimensions also include 280 × 512 and 512 × 324).
There are 6,504,448 rectangular texture texels, **3,326,160 valid texels**,
representing 13.30464 km² of original valid terrain cells.

- `data/processed/landscape_orthos_v003/manifest.json`: indices, node slices,
  local/UTM bounds, transforms, dimensions, validity coverage, PNG/mask/RGB hashes,
  source tiles, attribution and acquisition provenance.
- `chunk_NNN.png`: ungraded source colours; `chunk_NNN_mask.png`: 255 valid,
  0 excluded. Zero RGB outside the mask is padding, **not invented ground**.
- `contact_sheet.png`: manifest chunk order, seven columns, unused slots white;
  excluded terrain magenta **only on this review sheet**.
- `data/interim/landscape_orthos_v003/acquisition-estimate.json`: complete
  pre-pixel selection, exact compressed offsets/counts and coalesced ranges.
- `source-metadata.tif`, `run.log`, `tests.log` in that interim directory retain
  metadata, actual acquisition progress and test evidence.

No road texture, geometry, Blender scene, current GUI, game package, main status,
original route or terrain array was edited. Integration is a separate task.

## Acquisition and preservation

Source: BEV Operat2024460, © BEV, CC BY 4.0:
<https://data.bev.gv.at/download/DOP/20250415/2024460_Mosaik_RGB.tif>.
License metadata: <https://doi.org/10.48677/1f33a105-0798-4696-92c2-df985c6f40a9>.
Source object: 12,921,674,133 bytes; strong ETag
`"302311995-62d819976e140"`. No full TIFF download.

The **same** `data/raw/orthophoto/operation.json` was continued, never reset or
assigned a duplicate cap. Original cached bytes remain in place. Exact metadata
and complete tile offset/count tables were loaded offline from its cache before
selecting any pixels. Metadata logical size: 3,615,921 bytes; new metadata
transfer: **zero**. First native IFD only; overviews not followed.

| Preflight / actual item | Bytes / count |
| --- | ---: |
| Existing cumulative body bytes | 7,857,327 |
| Selected native JPEG tiles | 1,435 |
| Selected compressed bytes, including cached tiles | 63,401,329 |
| New required compressed bytes | 59,159,923 |
| Coalescing gaps charged | 0 |
| New coalesced requests | 93 |
| One-retry reserve (two attempts total) | 59,159,923 |
| Worst-case existing history + all new ranges twice | 126,177,173 |
| Original operation cap | 200,000,000 |
| Actual new body bytes | 59,159,923 |
| **Actual cumulative body bytes** | **67,017,250** |

Adjacent selected ranges are merged up to 8,000,000 bytes; allowed gaps up to
65,536 bytes would be fully charged, but this selection needed no gaps. Cached
exact/contained ranges are reused with size/SHA-256 verification. Original
`RangeReader` supplies HTTP 206/Content-Range checks, strong ETag/If-Match,
identity encoding, 30-second socket timeout, maximum one retry, incremental body
charging and preservation of complete/partial raw bytes. No software installed.

## Coordinate, decoder and validity contract

Target: EPSG:25833; local X east, Y north, origin
(589500, 5346800, 300) m. Source: EPSG:31256, explicit easting/northing axis
normalization. PROJ networking remains **off**. The first available non-ballpark
operation is the reviewed inverse MGI-to-ETRS89 (1), accuracy **1.5 m**. PROJ warns
that a better grid-based operation is unavailable; no grid was downloaded and no
submetre registration claim is made. The exact pipeline is in the manifest.

TIFF source affine: upper-left (-26250, 371000), 0.2 m pixels, PixelIsArea,
375000 × 210000. Each target texel centre is transformed to source coordinates.
Nearest resampling chooses the source pixel **containing** that centre (floor of
PixelIsArea coordinates), rather than averaging or colour grading. At 2 m this
can alias fine detail; it is a diffuse backdrop, not road-detail reconstruction.
Only JPEG tiles used by valid target texel centres are selected, not a full
route bounding-box mosaic. All output texture rectangles are within the source
raster's georeferenced rectangular footprint.

`tifffile` page decoding supplies shared `JPEGTables`, subsampling and YCbCr-to-RGB
parameters through existing `imagecodecs`; output is native uint8 RGB. PNG output
is lossless and roundtrip-checked. No band swaps, contrast changes or Google/game
assets are used.

Mask validity is the original **containing terrain valid_cell**, intersected with
source rectangular coverage. It is not a semantic source nodata mask: no declared
imagery nodata was verified, and black pixels are never used to infer validity.
Thus rectangular coverage does not prove every source pixel represents ground.
Canopy, shadows and roofs remain visible imagery, not measured terrain geometry.
Capture dates and independent precise registration remain unknown. No asphalt
height, width, roughness or camber measurements are inferred.

PNG row zero is north. For Blender integration use
`u=(E-west)/(east-west)`, `v=(N-south)/(north-south)` (bottom-up v).
Manifest transforms are `[west, north, positive_pixel_width, negative_pixel_height]`
in both local and UTM coordinates. Do not apply a second vertical flip. Honour
the mask/original terrain topology; do not create ground in excluded cells.

## Verification performed

`timeout 180 .venv/bin/python -m unittest discover -s tests`:
**242 tests passed in 53.792 seconds**, including seven new landscape tests.
No Blender/game execution occurred.

Synthetic checks cover north-up centre placement, valid-cell mapping, bottom-up
UV direction, source PixelIsArea edges, coalescing/gap/range caps, contained cache
reuse without charging, and budget refusal. Existing tests cover shared-table
JPEG decoding, 206/ETag failure, short-read retry charging and persistent caps.
Real checks recompute all PNG/mask/RGB hashes, all terrain masks, valid chunk
selection, dimensions/resolution, zero padding and georeference orientation.
Seven valid samples per chunk (182 total) independently transform through WGS84,
decode their original cached source JPEGs and exactly match exported RGB colours.
Those checks made no requests and left the ledger byte-for-byte unchanged.

The contact sheet was opened and visually inspected: forest, roads, settlements
and clearings are visible, with excluded terrain explicitly magenta. This is not
an independent alignment survey or Blender material/render validation.

Reproduce planning offline:
`.venv/bin/python scripts/prepare_landscape_orthos.py`.
Rebuild from the acquired cache without HTTP:
`.venv/bin/python scripts/prepare_landscape_orthos.py --pixels --offline`.
Planning estimates reflect current cache state on rerun; the generated manifest
retains the acquisition estimate from its own build. Keep the initial run/manifest
for original preflight evidence.

**Remaining gates:** downstream Blender UV/mask integration and render review,
source-date/semantic coverage review, independent registration, and authorized
runtime testing. No acquisition budget blocker remains.
