# Route report

## Provisional calculation — not accepted final route

Source: `data/interim/osm/merged.json`; SHA256 `75e902e51b3e47b9e6a36e605ee99a360618ea515332eed1d3299f8795cd4c35`.
License: ODbL-1.0; © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).
Direction: Königstetten → Marswiese. Spherical distance: **15.205 km**.
Difference from approximate 15.2 km: +0.005 km.

Map: `data/processed/route.svg`; geometry: `data/processed/route.geojson`.

## Endpoint edge snaps

- start: offset 2.09 m, way 33038070, edge 9, fraction 0.202510; lon/lat (16.15917230041046, 48.30127823461176).
- finish: offset 1.35 m, way 1206002982, edge 2, fraction 0.580626; lon/lat (16.270220293917088, 48.24399144368507).

Route bounds (west, south, east, north): [16.1591421, 48.2427804, 16.270220293917088, 48.30127823461176].

## Original sources

- `data/raw/osm/map_3ff58a650f69e02d.osm`; SHA256 `3ff58a650f69e02d23a99a4acf55587fad9acf12083ecc923f7f44a58d40e5b6`; ODbL-1.0. URL: https://api.openstreetmap.org/api/0.6/map?bbox=16.15,48.28,16.18,48.305; requested UTC 2026-10-25T12:26:22.610152+00:00.
- `data/raw/osm/map_54a8d88b81a99a07.osm`; SHA256 `54a8d88b81a99a075bd33707aea0f6ec65948d5589309f9ff9ef249bb39685b1`; ODbL-1.0. URL: https://api.openstreetmap.org/api/0.6/map?bbox=16.2,48.245,16.25,48.27; requested UTC 2026-10-25T12:27:55.121471+00:00.
- `data/raw/osm/map_597a5fea5611b721.osm`; SHA256 `597a5fea5611b72172d7fb7d0fd1630550a2a482f8f86a856ac3ce0796de2de4`; ODbL-1.0. URL: https://api.openstreetmap.org/api/0.6/map?bbox=16.24,48.235,16.28,48.255; requested UTC 2026-10-25T12:27:56.876344+00:00.
- `data/raw/osm/map_a35c0c19fe8fc560.osm`; SHA256 `a35c0c19fe8fc560ed643a4a4d337e8eca6e1153c3236ef2399fd5a17eea4920`; ODbL-1.0. URL: https://api.openstreetmap.org/api/0.6/map?bbox=16.17,48.26,16.21,48.29; requested UTC 2026-10-25T12:27:53.499665+00:00.

Preserved original XML total: 15,100,776 bytes. URL/timestamp/checksum/license sidecars remain in `data/raw/osm/`.
Section operation attempts and byte accounting: `data/raw/osm/sections_*.json`; earlier `failed_*.json` evidence preserved.

## Ordered road segments

| Road | Ref | Length (km) | OSM ways |
|---|---|---:|---|
| Neuwaldegger Straße | L120 | 4.208 | 33038070, 97841064, 1379268592, 1376185814, 1376185815, 33503120, 1376770861, 920990124, 699104558 |
| Tullnerstraße | L120 | 3.684 | 171860687, 920990126, 699104559, 729709007, 99455224 |
| Tullner Straße | L120 | 0.312 | 33503488, 279256943, 1028876476, 409753018, 603999578, 409753019, 116402546, 287993331 |
| (unnamed) | L120 | 5.802 | 1201737384, 1201737385, 33503490, 189980436, 189980437, 666692746, 100849539, 733249536, 131981282, 99455158, 101822120, 101822007, 163840840, 101822011, 1292475130, 292478113, 1201737382, 1201737381, 33744530 |
| Exelbergstraße |  | 1.199 | 1201737380, 1465437172, 1465437173, 162585706, 1206002982 |

## Limitations / acceptance blockers

- Calculated provisional OSM path, NOT screenshot-verified final alignment.
- Road ref/name whitelist only (observed L120 and Exelbergstraße tags, no arbitrary fallback); Dopplerhütte and Scheiblingstein/Exelberg passage and junction/hairpin choices require coordinator screenshot review.
- Turn-restriction relations, conditional/directional access, barriers and lane-level restrictions are NOT enforced. No legal driving clearance is implied.
- No elevations sampled: coordinates are two-dimensional WGS84 longitude, latitude.
- Endpoint snapping uses local planar edge projection; lengths use a spherical Earth, not survey-grade measurements.
- Terrain/imagery valid-pixel coverage and acquisition dates remain unverified; M1 gate remains open.

Ways with additional tagged details to review: [33038070, 33503120, 33503488, 33503490, 33744530, 97841064, 99455158, 99455224, 100849539, 101822011, 101822120, 116402546, 131981282, 163840840, 171860687, 189980436, 189980437, 279256943, 287993331, 292478113, 409753018, 409753019, 603999578, 666692746, 699104558, 699104559, 729709007, 733249536, 920990124, 920990126, 1028876476, 1201737381, 1201737382, 1201737384, 1201737385, 1292475130, 1376185814, 1376185815, 1376770861, 1379268592].

No Blender execution, game test, screenshot correspondence, or geographic raster validation was performed.
Rebuild merge offline: `python3 scripts/acquire_osm_sections.py` (no network without `--acquire`).
Rebuild route offline: `python3 scripts/route_osm.py --source data/interim/osm/merged.json`.
