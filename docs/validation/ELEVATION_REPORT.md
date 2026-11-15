# First real terrain extraction / provisional elevation profile

## Scope and interpretation

Real BEV bare-earth DTM pixels have been extracted around the existing provisional
OSM route, Königstetten → Marswiese. This is **terrain sampled along provisional
OSM**, not exact asphalt alignment, road survey, camber, roughness, or approved
Blender/game geometry. No imagery pixels, Blender, game, Windows or VR work occurred.
M2 acceptance is not implied: alignment, local source dates, slope anomalies,
EPSG:25833 reprojection and further geographic/visual checks remain open.

Original `data/processed/route.geojson`, route scripts/tests, metadata probe evidence,
roadmap/status/register and source assets were not modified. Its SHA256 remains
`0832b0657a32ee17651fbf46f36d7acebd8bd561b2dd79c337a9750745342601`.

## Acquisition and provenance

Source: BEV `ALS_DTM_CRS3035RES50000mN2800000E4750000.tif`, release 2025-09-15.
URL: <https://data.bev.gv.at/download/ALS/DTM/20250915/ALS_DTM_CRS3035RES50000mN2800000E4750000.tif>.
Attribution: © BEV, CC BY 4.0 (registered product metadata); route © OpenStreetMap
contributors, ODbL. The release date is not a route-area laser-survey date.

- Source object: **7,878,665,923 bytes**, strong ETag
  `"1d59ae6c3-65a891eeafd00"`, matching the earlier metadata evidence.
- First inspected the first IFD, small georeferencing/GDAL tags and block
  offset/byte-count tables: **116,266 DTM metadata body bytes**.
- Route transformed explicitly from longitude/latitude EPSG:4326 to EPSG:3035
  using pyproj `always_xy=True`. Selected **56 original 512 × 512 tiles**.
- Selection: each route segment's axis-aligned bounding box expanded by 200 m,
  then all intersecting source tiles. This is a conservative superset of the true
  ±200 m Euclidean corridor, with extra segment-box corners and whole-tile margins.
- **Before any pixels**, saved `data/interim/terrain/acquisition-estimate.json`:
  exact selected compressed sum **36,175,660 bytes**; two-attempt pixel reserve
  **72,351,320 bytes**. Including metadata and the official document below, the
  worst-case planned operation was **72,605,325 bytes**, far below the hard
  **500,000,000-byte aggregate ceiling**. No splitting to evade the ceiling.
- Actual DTM transfer: **36,291,926 bytes** (metadata + compressed tiles).
- Official BEV product HTML: **137,739 bytes**, separately bounded to 300,001
  bytes and preserved with URL, headers and SHA256 in `data/raw/terrain/`.
- **Aggregate acquisition body bytes: 36,429,665** including that document.
  No retries were needed. No full raster was downloaded; no orthophoto requests.

`data/raw/terrain/operation.json` persists the same operation's cumulative bytes,
source size/ETag, every exact requested range, response headers, actual bytes and
SHA256. Original successful compressed ranges are preserved as `range-*.bin`;
failed/partial attempts, if any, are preserved rather than discarded. The ledger
also charges the official-document bytes against the same ceiling. It must not
be deleted/reset to obtain a fresh allowance. The first pre-pixel estimate is
preserved rather than overwritten on cached reruns.

`terrain_ranges.py` requires HTTP 206 and exact Content-Range/length, permits only
identity/no Content-Encoding, requires a consistent strong ETag and object size,
uses If-Match after identification, rejects redirects/HTTP 200 before body reads,
and has 30-second socket timeouts and at most two attempts per range. It charges
all returned body bytes, including partial reads/retries, verifies persistent cache
checksums and preflights worst-case retries. Single ranges are capped at 8 MB.
Protocol/object changes fail closed without retry. Use one process per operation
cache. `official-product.html` is supporting documentation, not a raster range.

## Georeferencing, decoding and coverage

The source is little-endian float32 BigTIFF, LZW with floating-point predictor 3,
PixelIsArea, EPSG:3035, one sample/pixel, declared nodata **-9999**. Decoding uses
**tifffile + imagecodecs**, not a custom LZW codec. Original source compressed
bytes remain available separately from the recompressed output.

Source upper-left outer corner: `(4749999.5, 2850000.5)`; pixel scale `(1, -1)` m.
Source pixel centers therefore lie on integer metre coordinates. No half-pixel
shift is introduced when sampling or exporting.

Output: `data/processed/terrain_corridor_3035.tif` (**45,790,016 bytes**), tiled,
Deflate float32 GeoTIFF, 9,728 columns × 6,656 rows. Outer bounds in source metres:
west `4777135.5`, east `4786863.5`, south `2811600.5`, north `2818256.5`.
Source EPSG:3035 is deliberately retained for this first extraction;
EPSG:25833 reprojection, local origin and Blender axis mapping are deferred.

- **14,680,064 selected pixels**, all finite and non-nodata.
- Selected terrain height range **178.489–516.207 m**.
- **50,069,504 unacquired pixels** in the bounding rectangle remain explicit
  -9999 nodata. The rectangular file is NOT a complete rectangular terrain survey.
- No terrain interpolation, nodata filling, resampling, horizontal reprojection
  or height modification occurred in raster export.
- Offline validation compared **every selected exported float32 pixel** exactly
  against the independently decoded preserved source tile, checked geotags and
  confirmed every unacquired rectangle pixel remains nodata.
- Output SHA256:
  `cbd1c8439b794ccff0075ea8efc5a9dfbece2cbf897004e9533db39a827986ee`.

`data/interim/terrain/source-tags.json` preserves parsed first-IFD tags;
`source-metadata.tif` is a **reconstructed metadata-only TIFF**, with the unavailable
overview link cleared for local library parsing, not an original complete TIFF.
Exact original metadata ranges remain in raw cache. `coverage.json` gives each
selected tile's validity and min/max; `offline-validation.json` records checks.
COG conformance and overview pixels were not examined.

## Elevation results

Sampling: piecewise-linear route resampled at **≤10 m EPSG:3035 planar distance**,
including both endpoints. Bilinear interpolation uses pixel centers and requires
all four support pixels finite/non-nodata, even if a support weight is zero.
Missing samples would be blank in CSV and break GeoJSON/SVG lines, never invent
heights or bridge missing coverage. Original 2D route is untouched.

| Metric | Result |
| --- | ---: |
| Projected route length | 15,226.292 m |
| Samples / invalid | 1,524 / **0** |
| Minimum / maximum terrain height | 203.911 / 500.317 m |
| Start / finish | 203.911 / 296.129 m |
| Net height change | **+92.218 m** |
| Raw ≤10 m ascent / descent | 394.075 / 301.857 m |
| Independent 100 m coarse ascent / descent | 388.381 / 296.163 m |
| Maximum absolute adjacent-sample grade | **22.717%** |
| Intervals exceeding absolute 20% grade | **1** |
| Route samples outside broad 100–1000 m plausibility screen | **0** |

The 21 m difference from the earlier 15.205 km spherical route measurement reflects
the different distance method/CRS, not a changed route. No vertical smoothing was
applied. Raw ascent/descent is noise/alignment-sensitive and **not definitive**;
the separately sampled 100 m totals illustrate scale dependence, not a recommended
road profile. Gains omit invalid adjacent intervals if data are missing (none here).
The broad height screen and grade threshold are flags, not proof of accuracy.

**Investigate before road design:** km 9.590→9.600 rises from 487.318 to 489.590 m
(+22.717%) after a preceding -13.741% interval. The flagged sample is at WGS84
longitude `16.223779086`, latitude `48.257232852`. This may reflect OSM/terrain
misalignment, a cutting/structure or real terrain; it was **not silently smoothed**
and has not been visually resolved against imagery or survey. No tile nodata gap
was found there. Further bridge/culvert/cutting/canopy and seam checks remain open.

### Offline follow-up: dense terrain investigation

A fully cached rebuild with `--pixels --offline` and a separate offline diagnostic
were executed without network access or installs. The fail-closed offline opener
rejects any cache miss. SHA256 comparisons of **74 preserved files** confirmed
that all raw terrain files (including the operation ledger), the original route,
the main 10 m CSV, summary, profile SVG and terrain GeoTIFF were byte-identical.
DTM `actual_bytes` remains **36,291,926**; aggregate including the official page
remains **36,429,665**. The main statistics above are unchanged.

`scripts/diagnose_terrain.py` samples the entire provisional route at **1 m
EPSG:3035 planar chainage**, plus the final endpoint: **15,228 samples, zero
invalid**, total **15,226.292 m**. It uses the same strict four-pixel bilinear
sampling, with no fitting, filtering, smoothing, terrain repair or road design.
Distances are not EPSG:25833 distances. Flags are investigation heuristics:
absolute adjacent terrain gradient >20%, or absolute change between successive
interval gradients >20 percentage points. They are **not road-grade limits or
measurements of asphalt grade**; absence of a flag does not validate terrain.

There are **7 flagged intervals**, forming one contiguous investigation group,
**9,586–9,593 m**. Maximum absolute 1 m terrain gradient is **112.000%**
(9,590→9,591 m); the steepest fall is **-102.065%** (9,587→9,588 m).
These reflect a narrow sampled terrain depression largely missed by 10 m spacing,
not a proposed driving surface. The diagnostic JSON records all grouped intervals
ranked by maximum absolute gradient; cross-sections include the top group's peak
midpoint at 9,590.5 m and the requested 9,585, 9,589 and 9,593 m stations.

| EPSG:3035 chainage (m) | Terrain height (m, EPSG:9274) |
| ---: | ---: |
| 9,585 | 488.873 |
| 9,586 | 488.699 |
| 9,587 | 487.870 |
| 9,588 | 486.850 |
| 9,589 | **486.529** |
| 9,590 | 487.318 |
| 9,591 | 488.438 |
| 9,592 | 489.070 |
| 9,593 | 489.234 |

The 9,589 m sample lies **2.344 m below** 9,585 m and **2.705 m below**
9,593 m. All four-pixel supports for the entire 9,580–9,610 m window,
and every plotted lateral cross-section, lie inside **one original source tile,
index 7021** (zero-based source row-major index). This is not a boundary between
acquired tiles or a nodata gap; it does not establish that the source is correct.

Cross-sections sample **-20 to +20 m by 1 m** relative to the derived centerline.
The center is piecewise-linear interpolation of the unchanged provisional route
at the stated chainage. The unit tangent is the normalized chord between route
positions at d−2 and d+2 m (clipped at route endpoints); the left normal is
`(-tangent_y, tangent_x)` in EPSG:3035. Each sample is `center + offset * normal`.
At d=9,589 m, center is `(4782716.171398, 2813230.650142)` m and left normal
is `(0.711015256, 0.703176582)`. The JSON preserves exact centers, tangent
chord chainages, tangent/normal vectors, sample coordinates, offsets and heights.
This is a diagnostic geometric construction, not measured lane edges or crossfall.

Selected lateral heights show the depression is not confined to one centerline
sample (positive offset is left in the driving direction):

| Chainage (m) | -5 m | 0 m | +5 m | +10 m |
| ---: | ---: | ---: | ---: | ---: |
| 9,585 | 488.809 | 488.873 | 487.856 | 484.950 |
| 9,589 | 486.955 | 486.529 | 486.119 | 485.491 |
| 9,593 | 488.080 | 489.234 | 488.405 | 486.465 |

These are terrain elevations, not a road cross-section survey. **Terrain alone
cannot distinguish a culvert, ground beneath a bridge/road, another real ground
feature, provisional alignment error, or a source/classification artifact.**
Independent imagery, structural evidence and/or field/survey checks are needed;
no cause is diagnosed and no road geometry decision or repair is made here.
The self-contained SVG has four labeled panels with independent elevation scales;
it was XML-parsed, not visually inspected.

### Vertical reference / accuracy

The preserved official page
<https://www.bev.gv.at/Services/Produkte/Digitales-Gelaendehoehenmodell/ALS-Hoehenraster.html>
states general height accuracy **±0.50 m**, normally **EVRF2000 Austria,
orthometric heights (EPSG:9274)**. It identifies the 2021-09-15 series as the
Adria Triest EPSG:5778 exception. This source is the **2025-09-15 series**, so
EPSG:9274 is the documented product reference; the TIFF's inspected keys do not
independently establish its vertical datum. No independent control points, datum
transformation or local survey accuracy validation occurred. Do not combine these
heights directly with Adria benchmarks or ellipsoidal GNSS. One-metre grid spacing
does not establish centimetre road accuracy or measure asphalt camber/roughness.

## Outputs and reproducibility

- `data/processed/terrain_corridor_3035.tif` — sparse-coverage terrain GeoTIFF.
- `data/processed/route_elevation.csv` — distance, WGS84, EPSG:3035, raw terrain
  heights, validity and adjacent grades.
- `data/processed/route_elevation.geojson` — RFC 7946 **2D longitude/latitude**
  MultiLineString. Orthometric heights are **not coordinate Z**: per-feature
  `terrain_heights_m` is a nested list, one list per valid multiline run and one
  height per position in that run. `height_reference` explicitly identifies
  EPSG:9274 EVRF2000 Austria and `height_units` is `m`. Invalid heights break
  runs; isolated valid points cannot form a line and are omitted from both lists
  (the CSV retains all samples). No ellipsoidal-height transformation is claimed.
- `data/processed/terrain_diagnostic_1m.csv` — separate dense profile, projected
  chainage/coordinates, orthometric height, gradients and investigation flags.
- `data/processed/terrain_diagnostic_1m.json` — thresholds, ranked grouped flags,
  9,580–9,610 m evidence and complete derived lateral section samples.
- `data/processed/terrain_diagnostic_cross_sections.svg` — standalone ±20 m
  terrain cross-sections at 9,585, 9,589, 9,590.5 and 9,593 m.
- `data/processed/elevation_profile.svg` — self-contained reviewable chart.
  PNG was not produced; no extra rendering dependency was needed.
- `data/processed/elevation_summary.json` — machine-readable statistics/flags.
- `data/raw/terrain/`, `data/interim/terrain/` — source range bytes, provenance,
  acquisition estimate, coverage, dependency/install/test and validation evidence.

```sh
# Only if dependencies are not already installed; wheels only, project-local.
.venv/bin/python -m pip install --only-binary=:all: --retries 0 -r requirements-terrain.txt
# Metadata/estimate only; the existing operation cache is reused.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/extract_terrain.py
# Guaranteed cache-only rebuild; any cache miss fails without a URL request.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/extract_terrain.py --pixels --offline
# Independent offline 1 m terrain investigation; leaves the 10 m outputs alone.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/diagnose_terrain.py
# Guaranteed offline source/output comparison and complete test suite.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/validate_terrain.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

### Dependencies and checks actually executed

Follow-up QA: **63 offline tests passed** in the existing `.venv`; no installs.
Added checks cover 2D GeoJSON/parallel heights and missing-data run alignment,
fail-closed offline access, normals and plane sampling, endpoint chord clipping,
flag grouping/nodata, bilinear support tile boundaries, standalone SVG gaps/XML,
and recomputation of all 15,228 dense samples and every lateral section.
Updated `validate_terrain.py` passed the original 14,680,064 exact-pixel comparisons
and 1,524 profile checks plus 2D positions and exact parallel orthometric heights.
The following dependency/acquisition history predates this offline follow-up.

Created `.venv` using `python3 -m venv`; no global/user/system Python libraries or
non-Python software installed. Binary-only pip dry-run/report preceded installation.
The first dry-run failed because its report directory did not exist (no packages
installed); directory creation and rerun succeeded. Wheel URL HEAD size checks
summed **55,425,905 bytes**, well under the **150 MB dependency-transfer budget**;
small package metadata added approximately 0.11 MB. Installation used zero retries
and succeeded; evidence is in `dependency-dry-run.json`, `dependency-sizes.json`
and `dependency-install.log`. No source builds or pip upgrade.

Exact installed versions (`requirements-terrain.txt`): **numpy 2.5.4, pyproj 3.8.0,
tifffile 2026.10.15, imagecodecs 2026.10.10, certifi 2026.10.23**.

**56 offline tests passed** in `.venv` (41 existing + 15 new). New tests cover
HTTP 200/range/encoding/ETag rejection, identity encoding, cache corruption,
persistent budgets including partial reads/retries/supporting documents, timeouts,
georeferencing/pixel centers, conservative tile selection, strict nodata sampling,
route resampling and library LZW/floating-predictor round-trip.
The first synthetic round-trip test needed a BytesIO rewind and then passed.

Real-data `validate_terrain.py` additionally verified all 14,680,064 source pixels,
1,524 recomputed profile samples, georeferencing/nodata and unchanged route SHA256,
without network requests. A complete cached rebuild also ran with **no additional
raster body bytes** and reproduced the same GeoTIFF checksum. No visual inspection
of the SVG or terrain, independent survey check, Blender execution or game test is
claimed. No acquisition-budget blocker remains; flagged steep interval/alignment
and later CRS/geometry choices require coordinator follow-up.
