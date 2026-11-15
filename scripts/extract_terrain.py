#!/usr/bin/env python3
"""BEV DTM corridor acquisition and provisional route terrain profile.

Default is metadata/estimate only; --pixels explicitly enables bounded extraction.
Original route and raster-probe evidence are never modified. Reruns reuse the SAME
persistent operation ledger, including failed-attempt bytes and range checksums.
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import struct

import numpy as np
from pyproj import Transformer
import tifffile

from probe_raster_metadata import header, directory, TYPES, values, ProbeError
from terrain_ranges import RangeReader, save_json

URL = 'https://data.bev.gv.at/download/ALS/DTM/20250915/ALS_DTM_CRS3035RES50000mN2800000E4750000.tif'
RAW = Path('data/raw/terrain')
INTERIM = Path('data/interim/terrain')
PROCESSED = Path('data/processed')
NODATA = -9999.0


def metadata(remote):
    """Read only the first IFD and its tag payloads (no overview/pixel reads)."""
    chunks = []
    def get(offset, size):
        data = remote.read(offset, size)
        chunks.append((offset, data))
        return data
    endian, big, first = header(get(0, 16))
    if not big:
        raise ProbeError('this acquisition expects BigTIFF')
    count = struct.unpack(endian + 'Q', get(first, 8))[0]
    if not 1 <= count <= 100:
        raise ProbeError('unsafe IFD size')
    tags, next_ifd = directory(get(first + 8, count * 20 + 8), count, endian, True)
    for tag, item in tags.items():
        if 'offset' in item:
            if item['bytes'] > 100_000:
                raise ProbeError('unsafe tag payload size')
            item['values'] = values(get(item['offset'], item['bytes']), item['type'], item['count'], endian)
    # A small local TIFF metadata image allows tifffile to perform the source
    # LZW + floating-point predictor decoding; pixel offsets are never followed.
    buf = bytearray(max(offset + len(data) for offset, data in chunks))
    for offset, data in chunks:
        buf[offset:offset + len(data)] = data
    # No local overview directories are available; remove their linked-list pointer.
    struct.pack_into(endian + 'Q', buf, first + 8 + count * 20, 0)
    return tags, bytes(buf)


def scalar(tags, tag):
    return tags[tag]['values'][0]


def georef(tags):
    keys = tags[34735]['values']
    keymap = {keys[i]: keys[i + 3] for i in range(4, len(keys), 4)}
    if keymap.get(3072) != 3035 or keymap.get(1025) != 1:
        raise ProbeError('requires EPSG:3035 PixelIsArea')
    if 34264 in tags:
        raise ProbeError('rotated transforms unsupported')
    sx, sy, _ = tags[33550]['values']
    i, j, k, x, y, z = tags[33922]['values']
    if sx <= 0 or sy <= 0 or k != 0:
        raise ProbeError('invalid scale/tiepoint')
    return x - i * sx, y + j * sy, sx, sy


def selected_blocks(xy, transform, width, height, tile=512, radius=200):
    """Conservative superset: expanded segment AABBs, then whole source tiles.

    AABB expansion includes the true Euclidean +/- radius buffer; extra corners
    and tile margins are retained. No resampling/interpolation of the terrain.
    """
    x0, y0, sx, sy = transform
    nx, ny = math.ceil(width / tile), math.ceil(height / tile)
    chosen = set()
    for a, b in zip(xy[:-1], xy[1:]):
        xmin, xmax = min(a[0], b[0]) - radius, max(a[0], b[0]) + radius
        ymin, ymax = min(a[1], b[1]) - radius, max(a[1], b[1]) + radius
        if xmin < x0 or xmax > x0 + width * sx or ymax > y0 or ymin < y0 - height * sy:
            raise ProbeError('corridor outside source raster')
        c0, c1 = math.floor((xmin - x0) / (sx * tile)), math.floor((xmax - x0) / (sx * tile))
        r0, r1 = math.floor((y0 - ymax) / (sy * tile)), math.floor((y0 - ymin) / (sy * tile))
        for r in range(max(0, r0), min(ny - 1, r1) + 1):
            for c in range(max(0, c0), min(nx - 1, c1) + 1):
                chosen.add(r * nx + c)
    return sorted(chosen)


def bilinear(grid, xy, transform, nodata=NODATA):
    """Pixel centers; all four support pixels must be valid, even at zero weight."""
    x0, y0, sx, sy = transform
    output = np.full(len(xy), np.nan)
    for n, (x, y) in enumerate(xy):
        c, r = (x - x0) / sx - .5, (y0 - y) / sy - .5
        ci, ri = math.floor(c), math.floor(r)
        if ri < 0 or ci < 0 or ri + 1 >= grid.shape[0] or ci + 1 >= grid.shape[1]:
            continue
        v = grid[ri:ri + 2, ci:ci + 2]
        if np.any(~np.isfinite(v)) or np.any(v == nodata):
            continue
        u, w = c - ci, r - ri
        output[n] = (v[0, 0] * (1-u) * (1-w) + v[0, 1] * u * (1-w)
                     + v[1, 0] * (1-u) * w + v[1, 1] * u * w)
    return output


def resample_route(xy, spacing=10):
    distances = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    if np.any(np.diff(distances) <= 0):
        raise ValueError('duplicate/zero length route segments')
    samples = np.r_[np.arange(0, distances[-1], spacing), distances[-1]]
    return samples, np.column_stack([np.interp(samples, distances, xy[:, n]) for n in range(2)])


def gains(heights):
    delta = np.diff(heights)
    return float(np.nansum(np.maximum(delta, 0))), float(-np.nansum(np.minimum(delta, 0)))


def elevation_geometry(lon, lat, heights):
    """RFC 7946 positions are 2D; orthometric heights stay in parallel properties."""
    runs, height_runs, run, height_run = [], [], [], []
    for x, y, h in zip(lon, lat, heights):
        if np.isfinite(h):
            run.append([float(x), float(y)])
            height_run.append(float(h))
        else:
            if len(run) >= 2:
                runs.append(run)
                height_runs.append(height_run)
            run, height_run = [], []
    if len(run) >= 2:
        runs.append(run)
        height_runs.append(height_run)
    return {'type': 'MultiLineString', 'coordinates': runs}, height_runs


class OfflineOpener:
    def open(self, request, timeout):
        raise ProbeError('offline mode: required range is not cached')


def write_profile(route, xy, grid, transform):
    distances, sampled = resample_route(xy)
    heights = bilinear(grid, sampled, transform)
    lon, lat = Transformer.from_crs(3035, 4326, always_xy=True).transform(sampled[:, 0], sampled[:, 1])
    valid = np.isfinite(heights)
    slopes = np.diff(heights) / np.diff(distances) * 100
    # Coarse independent 100 m samples, NOT a filtered road design profile.
    coarse_d, coarse_xy = resample_route(xy, 100)
    coarse_h = bilinear(grid, coarse_xy, transform)
    raw_up, raw_down = gains(heights)
    coarse_up, coarse_down = gains(coarse_h)
    summary = dict(distance_m=float(distances[-1]), samples=len(heights), invalid_samples=int((~valid).sum()),
                   min_m=float(np.nanmin(heights)), max_m=float(np.nanmax(heights)),
                   start_m=float(heights[0]) if valid[0] else None,
                   finish_m=float(heights[-1]) if valid[-1] else None,
                   net_m=float(heights[-1]-heights[0]) if valid[0] and valid[-1] else None,
                   raw_10m_ascent_m=raw_up, raw_10m_descent_m=raw_down,
                   coarse_100m_ascent_m=coarse_up, coarse_100m_descent_m=coarse_down,
                   coarse_invalid_samples=int((~np.isfinite(coarse_h)).sum()),
                   max_absolute_grade_percent=float(np.nanmax(np.abs(slopes))),
                   grades_over_20_percent=int(np.sum(np.abs(slopes) > 20)),
                   heights_outside_100_1000m=int(np.sum(valid & ((heights < 100) | (heights > 1000)))),
                   grade_flag_sample_indices=(np.flatnonzero(np.abs(slopes) > 20)+1).tolist(),
                   sampling='<=10 m in EPSG:3035, strict four-pixel bilinear; no vertical smoothing',
                   interpretation='Terrain along provisional OSM, not surveyed asphalt. Raw gain is noise-sensitive; 100 m gain is scale-dependent, not definitive.',
                   vertical_reference='EPSG:9274 EVRF2000 Austria per official BEV product documentation for non-2021 releases; not independently validated')
    with (PROCESSED / 'route_elevation.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['distance_m', 'longitude', 'latitude', 'easting_3035_m', 'northing_3035_m', 'terrain_height_m', 'valid', 'grade_from_previous_percent'])
        for i, d in enumerate(distances):
            writer.writerow([f'{d:.3f}', f'{lon[i]:.9f}', f'{lat[i]:.9f}', *[f'{v:.3f}' for v in sampled[i]],
                             f'{heights[i]:.4f}' if valid[i] else '', int(valid[i]),
                             f'{slopes[i-1]:.4f}' if i and np.isfinite(slopes[i-1]) else ''])
    # Do not connect nodata gaps. Heights are NOT RFC 7946 ellipsoidal Z.
    geometry, height_runs = elevation_geometry(lon, lat, heights)
    properties = dict(summary, terrain_heights_m=height_runs,
                      height_reference='EPSG:9274 EVRF2000 Austria (orthometric; documented product reference)',
                      height_units='m',
                      terrain_heights_alignment='One list per MultiLineString run, one height per 2D position; isolated valid samples omitted')
    save_json(PROCESSED / 'route_elevation.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': properties, 'geometry': geometry}]})
    save_json(PROCESSED / 'elevation_summary.json', summary)
    ymin, ymax = math.floor(np.nanmin(heights)/50)*50, math.ceil(np.nanmax(heights)/50)*50
    paths, points = [], []
    for d, h in zip(distances, heights):
        if np.isfinite(h):
            points.append(f'{70 + d/distances[-1]*1060:.2f},{350-(h-ymin)/max(1,ymax-ymin)*280:.2f}')
        elif points:
            paths.append(' '.join(points)); points=[]
    if points:
        paths.append(' '.join(points))
    lines = ''.join(f'<polyline points="{p}" fill="none" stroke="#176b39" stroke-width="2"/>' for p in paths)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="440" viewBox="0 0 1200 440">
<rect width="1200" height="440" fill="white"/><g font-family="sans-serif" fill="#222">
<text x="70" y="28" font-size="20">Provisional OSM route — sampled BEV bare-earth terrain</text>
<text x="70" y="50">Königstetten → Marswiese | strict bilinear, ≤10 m spacing | not road survey</text>
<path d="M70 70 V350 H1130" stroke="#444" fill="none"/>{lines}
<text x="8" y="80">{ymax} m</text><text x="8" y="350">{ymin} m</text>
<text x="70" y="380">0 km</text><text x="1060" y="380">{distances[-1]/1000:.3f} km</text>
<text x="70" y="410">© BEV, CC BY 4.0; route © OpenStreetMap contributors, ODbL. Height reference: EVRF2000 Austria.</text>
</g></svg>'''
    (PROCESSED / 'elevation_profile.svg').write_text(svg)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pixels', action='store_true')
    parser.add_argument('--offline', action='store_true', help='Fail on any cache miss; never open a URL')
    args = parser.parse_args()
    INTERIM.mkdir(parents=True, exist_ok=True)
    remote = RangeReader(URL, RAW, opener=OfflineOpener() if args.offline else None)
    official = RAW / 'official-product.json'
    if official.exists():
        evidence = json.loads(official.read_text())
        content = (RAW / 'official-product.html').read_bytes()
        if len(content) != evidence['bytes'] or hashlib.sha256(content).hexdigest() != evidence['sha256']:
            raise ProbeError('official-document checksum mismatch')
        remote.charge_external('official-product.html', evidence['bytes'])
    tags, metadata_bytes = metadata(remote)
    transform = georef(tags)
    expected = {258: 32, 259: 5, 277: 1, 284: 1, 317: 3, 322: 512, 323: 512, 339: 3}
    if any(scalar(tags, k) != v for k, v in expected.items()) or float(tags[42113]['values']) != NODATA:
        raise ProbeError('source encoding changed')
    width, height = scalar(tags, 256), scalar(tags, 257)
    route_bytes = (PROCESSED / 'route.geojson').read_bytes()
    route = json.loads(route_bytes)
    coords = np.array(route['features'][0]['geometry']['coordinates'])[:, :2]
    x, y = Transformer.from_crs(4326, 3035, always_xy=True).transform(coords[:, 0], coords[:, 1])
    xy = np.column_stack([x, y])
    blocks = selected_blocks(xy, transform, width, height)
    offsets, counts = tags[324]['values'], tags[325]['values']
    if len(offsets) != math.ceil(width/512)*math.ceil(height/512) or len(counts) != len(offsets):
        raise ProbeError('invalid tile tables')
    ranges = [(offsets[i], counts[i]) for i in blocks]
    if any(n <= 0 or n > 8_000_000 or o < 0 or o+n > remote.state['total'] for o, n in ranges):
        raise ProbeError('unsafe tile ranges')
    needed = remote.preflight(ranges)
    estimate = dict(url=URL, generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    source_etag=remote.state['etag'], source_bytes=remote.state['total'],
                    route_sha256=hashlib.sha256(route_bytes).hexdigest(), source_transform=transform,
                    source_width=width, source_height=height, source_nodata=NODATA,
                    corridor_radius_m=200, selection='whole tiles intersecting +/-200m expanded segment AABBs (conservative superset)',
                    blocks=[dict(index=i, offset=offsets[i], compressed_bytes=counts[i]) for i in blocks],
                    selected_compressed_bytes=sum(n for o, n in ranges),
                    metadata_bytes=sum(item['requested_bytes'] for item in remote.state['attempts']
                                       if item['offset'] not in set(offsets)),
                    operation_body_bytes_before_pixels=remote.used_bytes,
                    uncached_pixel_bytes=needed, worst_case_additional_pixel_bytes=2*needed,
                    cap_bytes=remote.state['cap'])
    estimate_path = INTERIM / 'acquisition-estimate.json'
    if not estimate_path.exists():
        save_json(estimate_path, estimate)
    else:
        previous = json.loads(estimate_path.read_text())
        for key in ('source_etag', 'route_sha256', 'blocks', 'source_transform'):
            if previous[key] != json.loads(json.dumps(estimate[key])):
                raise ProbeError('existing acquisition plan changed; coordinator review required')
    (INTERIM / 'source-metadata.tif').write_bytes(metadata_bytes)
    save_json(INTERIM / 'source-tags.json', tags)
    print(f'Metadata body bytes: {remote.state["actual_bytes"]}; tiles: {len(blocks)}; exact compressed bytes: {estimate["selected_compressed_bytes"]}; retry reserve: {2*needed}', flush=True)
    if not args.pixels:
        return
    nx = math.ceil(width/512)
    rows, cols = [i//nx for i in blocks], [i%nx for i in blocks]
    r0, c0, r1, c1 = min(rows), min(cols), max(rows)+1, max(cols)+1
    grid = np.full(((r1-r0)*512, (c1-c0)*512), NODATA, dtype=np.float32)
    coverage = []
    with tifffile.TiffFile(io.BytesIO(metadata_bytes)) as tif:
        page = tif.pages[0]
        for seq, i in enumerate(blocks):
            compressed = remote.read(offsets[i], counts[i])
            decoded, position, shape = page.decode(compressed, i)
            tile = decoded.reshape(512, 512)
            rr, cc = i//nx, i%nx
            # TIFF padding outside image bounds is never valid terrain.
            tile = tile.copy()
            if (rr+1)*512 > height:
                tile[height-rr*512:, :] = NODATA
            if (cc+1)*512 > width:
                tile[:, width-cc*512:] = NODATA
            grid[(rr-r0)*512:(rr-r0+1)*512, (cc-c0)*512:(cc-c0+1)*512] = tile
            valid = np.isfinite(tile) & (tile != NODATA)
            coverage.append(dict(index=i, valid_pixels=int(valid.sum()), nodata_or_nonfinite_pixels=int((~valid).sum()),
                                 min_m=float(tile[valid].min()) if valid.any() else None,
                                 max_m=float(tile[valid].max()) if valid.any() else None))
            if seq % 10 == 0:
                print(f'Decoded {seq+1}/{len(blocks)}; body bytes {remote.state["actual_bytes"]}', flush=True)
    x0, y0, sx, sy = transform
    clipped_transform = (x0+c0*512*sx, y0-r0*512*sy, sx, sy)
    # Explicit nodata holes between the selected tiles; never filled/interpolated.
    keys = (1,1,0,3,1024,0,1,1,1025,0,1,1,3072,0,1,3035)
    tifffile.imwrite(PROCESSED / 'terrain_corridor_3035.tif', grid, tile=(512,512), compression='deflate',
                     metadata=None, extratags=[(33550,'d',3,(sx,sy,0),False),
                     (33922,'d',6,(0,0,0,clipped_transform[0],clipped_transform[1],0),False),
                     (34735,'H',len(keys),keys,False), (42113,'s',0,'-9999',False)])
    summary = write_profile(route, xy, grid, clipped_transform)
    save_json(INTERIM / 'coverage.json', dict(tiles=coverage, grid_shape=grid.shape, transform=clipped_transform,
                  valid_selected_pixels=sum(t['valid_pixels'] for t in coverage),
                  invalid_selected_pixels=sum(t['nodata_or_nonfinite_pixels'] for t in coverage),
                  unacquired_rectangle_pixels=grid.size-len(blocks)*512*512,
                  dtm_body_bytes=remote.state['actual_bytes'], aggregate_body_bytes=remote.used_bytes, output_sha256=hashlib.sha256((PROCESSED/'terrain_corridor_3035.tif').read_bytes()).hexdigest()))
    print(json.dumps(summary, indent=2))
    print('Total operation body bytes including official document:', remote.used_bytes)


if __name__ == '__main__':
    main()
