# Data-source register

**Status:** four small OSM XML extracts have been acquired (15,100,776 bytes),
merged, and used to reconstruct a provisional 15.205 km route. After an initial
952-byte TIFF metadata inspection, a bounded DTM corridor acquisition retrieved
36,429,665 body bytes including official documentation. A separate bounded
orthophoto operation acquired 7,857,327 body bytes for six small imagery references
and their metadata. No full rasters downloaded. See [route report](validation/ROUTE_REPORT.md),
[raster inspection](validation/RASTER_METADATA.md),
[elevation report](validation/ELEVATION_REPORT.md), and
[imagery report](validation/ORTHOPHOTO_REPORT.md). This register does not authorize
downloads over 1 GB.

## Project reference corridor

Approximate route: Königstetten start (WGS84 `48.3012763, 16.1591442`) →
Dopplerhütte → Scheiblingstein/Exelberg → Marswiese finish (WGS84
`48.2439815, 16.2702098`), about 15.2 km. A local reference image,
`Screenshot_google_maps.jpg`, exists. Acquired route geometry is saved in
`data/processed/route.geojson`; see `data/processed/route_preview.png` for the
schematic. General route shape has been compared visually with the screenshot;
precise alignment against orthophotos and terrain is still pending.

## Terrain: BEV ALS DTM

- **Metadata:** <https://doi.org/10.48677/17e0f9fe-86d9-43b1-aaa6-5cf9538f8cf0>
- **Release:** 2025-09-15; 1 m bare-earth grid; CC BY 4.0.
- **Metadata bbox:** west 15.77078, east 16.49814, south 48.12544, north
  48.61085.
- **Bulk TIFF:** <https://data.bev.gv.at/download/ALS/DTM/20250915/ALS_DTM_CRS3035RES50000mN2800000E4750000.tif>
- **Verified endpoint facts:** HTTP 200 HEAD; `Content-Length` 7,878,665,923
  bytes (~7.88 GB decimal); byte ranges advertised.
- **Product information:** <https://www.bev.gv.at/Services/Produkte/Digitales-Gelaendehoehenmodell/ALS-Hoehenraster.html>
  states general vertical accuracy ±0.50 m; horizontal CRS EPSG:3035; heights
  generally EPSG:9274 (EVRF2000 Austria). The 2021 series is an exception using
  EPSG:5778 (Adria).
- **Observed TIFF structure:** little-endian BigTIFF, 50,001 × 50,001 float32,
  512 × 512 LZW-compressed tiles, GeoKey EPSG:3035, declared nodata -9999.
  Metadata and selected pixel ranges were successfully served as HTTP 206.
  A conservative ±200 m corridor used 56 tiles and 36,175,660 compressed pixel
  bytes. All 14,680,064 selected pixels and 1,524 route samples are finite/non-nodata;
  raw terrain has a flagged narrow dip near route km 9.589. COG conformance and
  independent road/height accuracy remain unverified. Source-cache ledger:
  `data/raw/terrain/operation.json`.
- **Unknown:** exact source-survey dates for the route area.

## Orthophoto: BEV DOP

- **Metadata:** <https://doi.org/10.48677/1f33a105-0798-4696-92c2-df985c6f40a9>
- **Dataset:** Operat2024460, approximately 20 cm imagery, CC BY 4.0.
- **Metadata bbox:** west 15.97708, east 16.98824, south 48.09893, north
  48.47719.
- **RGB bulk TIFF:** <https://data.bev.gv.at/download/DOP/20250415/2024460_Mosaik_RGB.tif>
- **Verified endpoint facts:** HTTP 200 HEAD; `Content-Length` 12,921,674,133
  bytes (~12.92 GB decimal); byte ranges advertised.
- **Observed TIFF structure:** little-endian BigTIFF, 375,000 × 210,000,
  three uint8 samples, 512 × 512 JPEG-compressed tiles, GeoKey EPSG:31256.
  Metadata and selected pixel ranges were successfully served as HTTP 206.
  Native affine: upper-left (-26250, 371000), pixel scale (0.2, -0.2) metres,
  PixelIsArea. Imagery uses a different horizontal CRS than the terrain.
- **Acquired:** six ~250 m-square references, 9,390,006 RGB pixels, checked exactly
  against decoded original windows. Operation total 7,857,327 bytes including
  metadata and retained exploratory tiles. Outputs and provenance:
  `data/processed/orthophoto/`, `data/raw/orthophoto/operation.json`.
- **Coordinate limitation:** selected source/WGS84 operation reports 1.5 m accuracy;
  no sub-metre registration or OSM precision claim. Networking for PROJ disabled.
- **Still verify:** full-corridor pixel coverage, capture date/currentness, precise
  alignment and exact attribution wording for any eventual distribution. Sampled
  imagery broadly matches the road, but cannot establish asphalt height at the
  terrain anomaly. COG conformance and full-corridor transfer size remain unknown.
- **Newer national metadata:** <https://doi.org/10.48677/ba4b0a47-8349-44d7-86ff-2edeb7877783>
  lists imagery from 2022–2025; it does not prove newer route-area imagery.

## Surface model: BEV ALS DSM (metadata checked, no pixels acquired)

- **Bulk TIFF:** <https://data.bev.gv.at/download/ALS/DSM/20250915/ALS_DSM_CRS3035RES50000mN2800000E4750000.tif>
  (same tile name and grid as the DTM; older 20240915/20230915 releases also exist).
- **Verified (2026-11-15):** HTTP 200 HEAD, `Content-Length` 9,080,212,834 bytes,
  byte ranges served. BigTIFF 50,001 × 50,001 float32, LZW + float predictor,
  512 × 512 tiles, nodata -9999, EPSG:3035; tiepoint/size identical to the DTM.
  BEV metadata: 1 m, CC BY 4.0, general height accuracy ±0.50 m (worse at
  vegetation, building edges, glass, water).
- **Metadata operation:** 116,266 body bytes; ledger `data/raw/surface_dsm/operation.json`,
  report `data/interim/surface_dsm/estimate.json`, script `scripts/probe_surface_dsm.py`.
- **Exact corridor costs (compressed tile bytes):** ±200 m: 56 tiles / 46.4 MB;
  ±400 m: 80 tiles / 66.4 MB; ±800 m: 136 tiles / 112.0 MB. A wider radius than
  ±200 m would also need extra DTM tiles for DSM−DTM (≈+15 MB for ±400 m).
- **Purpose:** canopy-height and building-height model (DSM−DTM) for vegetation
  and building placement.
- **Acquired (user-approved ±400 m, 2026-11-15):** 80 DSM tiles, 66,482,043 body bytes
  (ledger `data/raw/surface_dsm/operation.json`, cap 200 MB) plus 24 extra DTM tiles,
  15,521,017 new bytes on the existing DTM ledger (cumulative 51,812,943 of its 500 MB cap).
  Script `scripts/acquire_surface_v004.py`; outputs `data/processed/surface_v004/`
  (`dsm_400_3035.tif`, `dtm_400_3035.tif`, `chm_400_3035.tif`, `summary.json`, `chm_preview.png`).
  CHM median 16.4 m, P90 32.0 m, 80 % of valid pixels > 3 m. Whole-tile selection,
  so coverage is a conservative superset of ±400 m, with nodata outside the tiles.

## Vector and reference candidates

| Source | Verified finding | Use / caution |
| --- | --- | --- |
| Vienna WFS | [Capabilities](https://data.wien.gv.at/daten/geo?service=WFS&request=GetCapabilities) lists `ogdwien:FMZKGEBOGD`, `HOEHENLINIEOGD`, and `HOEHENFESTPKTADRIAOGD`. | Service advertises CC BY 3.0 AT; check dataset-specific terms before use. |
| OpenStreetMap | Four bounded extracts acquired through the official map API after Overpass timeouts; source XML/checksum/URL sidecars in `data/raw/osm/`. [Copyright](https://www.openstreetmap.org/copyright). | ODbL; © OpenStreetMap contributors. Provisional road continuity checked; other feature completeness and restrictions not fully validated. |
| basemap.at | [WMTS capabilities](https://basemap.at/wmts/1.0.0/WMTSCapabilities.xml) reachable. | Layers and terms have not been audited. |
| Official NÖ portal | `atlas.noe.gv.at` | Candidate only; not product verification. |

## Full-route forest supplements and scenic placement

Three OSM relation/full supplements (relations 4624, 4625, 15456599) were acquired
in a bounded three-request operation: **4,186,767 bytes**, original XML/provenance
under `data/raw/full_forest/`. The initial extract alone lacked their members.

Complete relations 4624/4625 have overlapping/nested ring arrangements. The
separately documented v003 mask uses union of individually valid closed outer
rings minus union of all inner rings, then strict building/water exclusions.
No ring snapping, open-ring filling or source-coordinate changes. This conservative
role policy can omit forest islands; it does not claim a perfect topological
interpretation. See [policy/evidence](validation/FULL_FOREST_UNION.md).

It retains **4,616** deterministic ground-valid anchors across all route bins from
5,844 candidate points. These become low-poly broadleaf-style scenery in v002;
forest extent is data-derived, but individual trees/species/density are **not
measured**. Tree geometry and seven surface image textures are generated locally,
not extracted from Google or copied from commercial game assets.

## Full landscape imagery extension (v003)

The original orthophoto operation was extended, without resetting its 200 MB cap:
**59,159,923 new body bytes**, cumulative **67,017,250 bytes**. Existing metadata
and range cache reused; no full TIFF downloaded. Exact selection and two-attempt
reserve were estimated before acquisition.

26 valid-terrain chunk textures, north-up at **2 m/texel** (source 20 cm), are
prepared under `data/processed/landscape_orthos_v003/`. They are integrated into
v003 using explicit UV tables and checked DDS colour/coordinate controls. The
approximate 1.5 m coordinate-operation accuracy, unknown capture dates and canopy/
roof/shadow appearance remain limitations. Padding/masks do not create terrain.
These diffuse backdrops are not a road survey or replacement for 3D buildings.
See [landscape imagery evidence](validation/LANDSCAPE_ORTHOS_V003.md).

Google Street View may assist manual visual comparison of furniture/materials,
but no Google imagery/meshes/textures have been extracted into this project.
Suitable reuse rights would need verification before any such asset acquisition.

## CC0 textures (ambientCG) for v004

Twelve ambientCG assets, CC0 1.0, acquired 2026-11-15 in one bounded operation of
**266,441,504 bytes** (cap 400 MB). Original zips and sha256 values are in `data/raw/textures_cc0/`
(`operation.json`), extracted to `data/interim/textures_cc0/`. Assets: LeafSet014/016/019/024,
Bark011/012/014, Grass004/005, Ground037/038, Gravel023. No Google or commercial game assets.

## Acquisition controls

1. Keep metadata review separate from pixel acquisition. Selected DTM and
   orthophoto blocks were acquired within pre-estimated bounded operations;
   no complete BEV TIFFs downloaded. Preserve both acquisition ledgers/caches.
2. Obtain user approval **before any download over 1 GB**. Budget cumulative
   range requests per operation conservatively; do not split requests to bypass
   approval.
3. Do not action the large download links until layout, byte-range behavior,
   licensing/terms, and suitability for corridor clipping are verified. Do not
   assume the TIFFs are COGs.
4. Consider corridor clipping only after those checks. Record attribution and
   license dates from verified source material; dates are currently unknown.
5. Use Python libraries only within the project `.venv`; ask before installing
   non-Python software.
