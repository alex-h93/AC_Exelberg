#!/usr/bin/env python3
"""Offline exact source-tile/GeoTIFF/profile validation. Never opens a URL."""
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import tifffile
from pyproj import Transformer

from extract_terrain import RAW, INTERIM, PROCESSED, NODATA, bilinear, resample_route, elevation_geometry
from terrain_ranges import digest, save_json


def main():
    ledger = json.loads((RAW / 'operation.json').read_text())
    estimate = json.loads((INTERIM / 'acquisition-estimate.json').read_text())
    coverage = json.loads((INTERIM / 'coverage.json').read_text())
    path = PROCESSED / 'terrain_corridor_3035.tif'
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        assert page.geotiff_tags['ProjectedCSTypeGeoKey'] == 3035
        assert page.geotiff_tags['GTRasterTypeGeoKey'] == 1
        assert page.nodata == NODATA
        assert page.dtype == np.float32
        grid = page.asarray()
        scale, tie = page.tags[33550].value, page.tags[33922].value
        transform = (tie[3], tie[4], scale[0], scale[1])
        assert list(transform) == coverage['transform']
    nx = (estimate['source_width']+511)//512
    indices = [b['index'] for b in estimate['blocks']]
    r0, c0 = min(i//nx for i in indices), min(i%nx for i in indices)
    exact_pixels = 0
    # Decode preserved original ranges independently and compare EVERY selected
    # source float32 sample to its exported position (not just route samples).
    with tifffile.TiffFile(io.BytesIO((INTERIM / 'source-metadata.tif').read_bytes())) as tif:
        source = tif.pages[0]
        for b in estimate['blocks']:
            i = b['index']
            entry = ledger['cache'][f'{b["offset"]}-{b["compressed_bytes"]}']
            raw = (RAW / entry['file']).read_bytes()
            assert len(raw) == b['compressed_bytes'] and digest(raw) == entry['sha256']
            tile = source.decode(raw, i)[0].reshape(512,512)
            rr, cc = (i//nx-r0)*512, (i%nx-c0)*512
            np.testing.assert_array_equal(grid[rr:rr+512,cc:cc+512],tile)
            exact_pixels += tile.size
    assert int(np.sum(grid == NODATA)) == coverage['unacquired_rectangle_pixels']
    assert np.isfinite(grid).all()
    route_bytes = (PROCESSED / 'route.geojson').read_bytes()
    assert digest(route_bytes) == estimate['route_sha256']
    coords = np.array(json.loads(route_bytes)['features'][0]['geometry']['coordinates'])[:, :2]
    xy = np.column_stack(Transformer.from_crs(4326,3035,always_xy=True).transform(coords[:,0],coords[:,1]))
    distances, points = resample_route(xy)
    recomputed = bilinear(grid,points,transform)
    rows = list(csv.DictReader((PROCESSED/'route_elevation.csv').open()))
    assert len(rows) == len(distances)
    np.testing.assert_allclose([float(r['distance_m']) for r in rows],distances,atol=.00051,rtol=0)
    np.testing.assert_allclose([float(r['terrain_height_m']) for r in rows],recomputed,atol=.000051,rtol=0)
    assert np.max(np.diff(distances)) <= 10.000001
    feature = json.loads((PROCESSED/'route_elevation.geojson').read_text())['features'][0]
    lon, lat = Transformer.from_crs(3035,4326,always_xy=True).transform(points[:,0],points[:,1])
    expected_geometry, expected_heights = elevation_geometry(lon, lat, recomputed)
    assert feature['geometry'] == expected_geometry
    assert feature['properties']['terrain_heights_m'] == expected_heights
    assert feature['properties']['height_reference'].startswith('EPSG:9274')
    assert feature['properties']['height_units'] == 'm'
    assert all(len(p) == 2 for run in feature['geometry']['coordinates'] for p in run)
    summary = dict(exact_source_pixels_compared=exact_pixels, validated_route_samples=len(rows),
                   source_route_unchanged=True, selected_pixels_bit_exact=True,
                   unacquired_pixels_remain_nodata=True, geotiff_crs=3035,
                   output_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   dtm_body_bytes=ledger['actual_bytes'],
                   aggregate_body_bytes=ledger['actual_bytes']+sum(ledger.get('external_bytes',{}).values()),
                   geojson_positions_2d=True, geojson_orthometric_heights_in_properties=True,
                   network_requests_in_validation=0)
    save_json(INTERIM / 'offline-validation.json',summary)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
