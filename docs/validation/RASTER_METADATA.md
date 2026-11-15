# Bounded BEV raster metadata inspection

## Scope and observed transfer

Ran `python3 scripts/probe_raster_metadata.py` against only the two TIFF URLs
registered in `docs/DATA_SOURCES.md`. No installation, pixel/block read, full
TIFF download, or route-data change occurred.

Evidence: `data/raw/bev_metadata/dtm.json` and `orthophoto.json`, including source
URLs, recorded UTC timestamps, response headers, exact ranges, actual body bytes,
and SHA-256 checksums for each fetched chunk. Timestamps are recorded environment
and server observations, not independently verified acquisition dates. BEV source
metadata identifies CC BY 4.0; this inspection does not add a licensing audit.

| Measurement | DTM | Orthophoto |
| --- | ---: | ---: |
| Requests | 4 | 4 |
| Actual response body bytes read | 476 | 476 |
| Object length from validated Content-Range | 7,878,665,923 | 12,921,674,133 |
| Requested ranges (inclusive) | 0–15; 200–207; 208–595; 1100–1163 | 0–15; 16–23; 24–411; 3615830–3615893 |

**Total metadata body transfer: 952 bytes**, below the 2,000,000-byte cumulative
operation cap. All eight responses were HTTP 206 with matching Content-Range and
Content-Length and no Content-Encoding. Header/TLS overhead is not included in
body-byte accounting. No further network requests were made.

## Metadata findings

Both files are **little-endian BigTIFF, tiled 512 × 512**, not huge-strip rasters.
The following describes the first image directory only.

| Property | DTM | Orthophoto |
| --- | --- | --- |
| Width × height | 50,001 × 50,001 | 375,000 × 210,000 |
| Samples | 1 × float32 (SampleFormat 3, BitsPerSample 32) | 3 × uint8 (SampleFormat 1, BitsPerSample 8 each) |
| Compression | LZW (5) | JPEG (7) |
| Photometric interpretation | BlackIsZero (1) | YCbCr (6), 2 × 2 subsampling declared |
| Planar configuration | Chunky (1) | Chunky (1) |
| Tile grid | 98 × 98 = 9,604 | 733 × 411 = 301,263 |
| Offset table declaration | 9,604 LONG8 entries, 76,832 bytes, at 3,730 | 301,263 LONG8 entries, 2,410,104 bytes, at 1,205,464 |
| Byte-count table declaration | 9,604 LONG entries, 38,416 bytes, at 80,562 | 301,263 LONG entries, 1,205,052 bytes, at 412 |
| First/next IFD offsets | 200 / 1,202 | 16 / 3,615,922 |
| ProjectedCSTypeGeoKey (3072) | EPSG:3035 | EPSG:31256 |
| ProjLinearUnitsGeoKey (3076) | metre (9001) | metre (9001) |
| GTRasterTypeGeoKey (1025) | PixelIsArea (1) | PixelIsArea (1) |

Table counts match the calculated base-image tile grids. **Table contents were
not fetched or validated**; their offsets/counts are declarations, not measured
compressed tile sizes. The DTM declares GDAL nodata `-9999`; no nodata pixels were
examined. The orthophoto's stored photometric interpretation is YCbCr despite the
RGB product filename; no JPEG decoding or color validation was performed.

The fourth request retrieved each GeoKeyDirectory (64 bytes). ModelPixelScale,
ModelTiepoint and GeoASCII tags were located but their external values were not
read. Thus no affine transform, actual resolution, raster footprint, vertical CRS,
or route alignment is established by this probe. Published resolution remains a
source-register fact, not a measurement here.

Nonzero next-IFD links exist, but their directories were **not inspected** because
the four-request budget was exhausted. They may contain overviews or other images;
overview existence, dimensions, ordering and suitability remain unknown.

## Window-read assessment and limitations

512-square tiles and correctly honored byte ranges are encouraging for future
selective window reads, unlike very tall full-width strips. This is **not COG
validation**. Neither endpoint was established to advertise COG conformance;
previously advertised byte-range support is now observed for metadata only.

Compressed tile byte counts, offset ordering, overview organization, JPEG shared
metadata requirements, client table-loading behavior and the actual corridor tile
set are unverified. In particular, the orthophoto offset table alone exceeds the
entire metadata operation cap. A future reader would need appropriately selective
table access rather than assuming it can load every table cheaply.

**Corridor transfer prediction: unknown.** No actual pixel validity, complete road
coverage, capture dates, terrain correctness or imagery suitability is claimed.
Further network work requires a separately bounded, coordinated task; do not rerun
this operation to work around its four-request limit.

## Implementation and offline checks

`scripts/probe_raster_metadata.py` uses Python's standard library only. It sets an
explicit User-Agent, requests identity encoding, uses a 20-second socket timeout,
limits each range to 65,536 bytes and each raster to four requests, and shares a
2,000,000-byte actual-body budget across both rasters. It requests only the header,
IFD count, exact IFD entries/link, and small selected external tag values; it never
fetches external tile/strip offset or byte-count arrays. It parses classic TIFF
and BigTIFF, both byte orders. Output refuses to overwrite existing evidence.

Redirects and retries are disabled. Non-206 responses (including ignored-range
HTTP 200), malformed/mismatched Content-Range, unexpected encoding and conflicting
lengths are closed without body reads. Short reads count toward the operation
budget. A network/response failure stops subsequent network requests globally.
The initial 16-byte header read accommodates BigTIFF; for classic TIFF it also
contains the eight bytes immediately following the header. No pixels were present
in the header ranges of these observed BigTIFF sources.

Check executed:

```sh
python3 -m unittest discover -s tests -p test_probe_raster_metadata.py -v
```

Result: **12 offline tests passed** (classic/BigTIFF parsing, both endiannesses,
external-table declarations without acquisition, sample values, malformed input,
range/header validation, no-read failure handling, global stop, caching/checksums,
short-read accounting, request/range/operation bounds and redirect refusal).
