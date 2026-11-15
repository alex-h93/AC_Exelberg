#!/usr/bin/env python3
"""Offline, versioned northern prototype inputs; no road design or Blender API."""
import hashlib
import json
import math
import os
from pathlib import Path

os.environ['PROJ_NETWORK'] = 'OFF'
import numpy as np
import pyproj
from pyproj import network
from pyproj.transformer import TransformerGroup
import tifffile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/prototype'
START, END = 1000.0, 2500.0


def operation(source, target):
    network.set_network_enabled(False)
    group = TransformerGroup(source, target, always_xy=True, allow_ballpark=False)
    if not group.transformers:
        raise ValueError(f'No non-ballpark operation: {source} -> {target}')
    transform = group.transformers[0]
    info = dict(source_epsg=source, target_epsg=target, always_xy=True,
                allow_ballpark=False, networking=False, best_available=group.best_available,
                description=transform.description, definition=transform.definition,
                accuracy_m=transform.accuracy)
    return transform, info


def project(transform, xy, inverse=False):
    direction = 'INVERSE' if inverse else 'FORWARD'
    result = np.column_stack(transform.transform(xy[:, 0], xy[:, 1],
                                               direction=direction, errcheck=True))
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite projection')
    return result


def stations(xy):
    result = np.r_[0., np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    if len(xy) < 2 or not np.isfinite(xy).all() or np.any(np.diff(result) <= 0):
        raise ValueError('Route must be finite with positive-length segments')
    return result


def interpolate(xy, chainage, requested):
    return np.column_stack([np.interp(requested, chainage, xy[:, i]) for i in range(2)])


def clip_route(xy, chainage, start, end):
    if not chainage[0] <= start < end <= chainage[-1]:
        raise ValueError('Invalid section interval')
    s = np.r_[start, chainage[(chainage > start) & (chainage < end)], end]
    return s, interpolate(xy, chainage, s)


def densify(xy, chainage, spacing=2.):
    if spacing <= 0:
        raise ValueError('Spacing must be positive')
    pieces, ss = [], []
    for a, b, sa, sb in zip(xy[:-1], xy[1:], chainage[:-1], chainage[1:]):
        count = max(1, math.ceil(np.linalg.norm(b-a) / spacing))
        t = np.arange(count) / count
        pieces.append(a + t[:, None] * (b-a))
        ss.append(sa + t * (sb-sa))
    return np.r_[np.concatenate(ss), chainage[-1]], np.vstack([*pieces, xy[-1:]])


def strict_bilinear(grid, xy, transform, nodata=-9999.):
    """All four support pixels valid, including zero-weight neighbors."""
    x0, y0, sx, sy = transform
    c = (xy[:, 0]-x0)/sx - .5
    r = (y0-xy[:, 1])/sy - .5
    finite = np.isfinite(c) & np.isfinite(r)
    ci = np.floor(np.where(finite, c, -1)).astype(np.int64)
    ri = np.floor(np.where(finite, r, -1)).astype(np.int64)
    inside = finite & (ci >= 0) & (ri >= 0) & (ci+1 < grid.shape[1]) & (ri+1 < grid.shape[0])
    indices = np.flatnonzero(inside)
    cc, rr = ci[inside], ri[inside]
    v = np.column_stack([grid[rr, cc], grid[rr, cc+1], grid[rr+1, cc], grid[rr+1, cc+1]])
    valid_support = np.all(np.isfinite(v) & (v != nodata), axis=1)
    valid = np.zeros(len(xy), dtype=bool)
    valid[indices[valid_support]] = True
    u, w = c[valid]-ci[valid], r[valid]-ri[valid]
    v = v[valid_support]
    heights = np.zeros(len(xy), dtype=np.float64)
    heights[valid] = v[:, 0]*(1-u)*(1-w) + v[:, 1]*u*(1-w) + v[:, 2]*(1-u)*w + v[:, 3]*u*w
    return heights, valid


def local_positions(xy, heights, valid, origin):
    result = np.column_stack([xy-origin[:2], np.where(valid, heights-origin[2], 0.)])
    return result


def valid_cells(mask):
    return mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def record(path):
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=sha(path))


def save_arrays(path, **arrays):
    if any(a.dtype.hasobject or not np.isfinite(a).all() for a in arrays.values()):
        raise ValueError('Only finite non-object arrays permitted')
    np.savez_compressed(path, **arrays)
    return dict(record(path), arrays={k: dict(shape=list(v.shape), dtype=str(v.dtype)) for k, v in arrays.items()})


def main():
    route_path = ROOT / 'data/processed/route.geojson'
    raster_path = ROOT / 'data/processed/terrain_corridor_3035.tif'
    route = np.asarray(json.loads(route_path.read_text())['features'][0]['geometry']['coordinates'])[:, :2]
    wgs_source, log1 = operation(4326, 3035)
    source_work, log2 = operation(3035, 25833)
    source_xy = project(wgs_source, route)
    full_s = stations(source_xy)
    full_work = project(source_work, source_xy)
    full_work_s = stations(full_work)
    midpoint = interpolate(full_work, full_work_s, [full_work_s[-1]/2])[0]
    origin = np.r_[np.round(midpoint/100)*100, 300.]
    section_s, section_source = clip_route(source_xy, full_s, START, END)
    section_work = project(source_work, section_source)
    dense_s, dense_work = densify(section_work, section_s)
    dense_source = project(source_work, dense_work, inverse=True)
    # Use preserved EPSG:3035 GeoTIFF pixels, verified against cached originals
    # by validate_terrain.py; no raster reprojection, fill, or vertical processing.
    with tifffile.TiffFile(raster_path) as tif:
        page = tif.pages[0]
        keys = page.geotiff_tags
        if keys['ProjectedCSTypeGeoKey'] != 3035 or keys['GTRasterTypeGeoKey'] != 1:
            raise ValueError('Expected EPSG:3035 PixelIsArea')
        sx, sy, _ = page.tags[33550].value
        i, j, _, x, y, _ = page.tags[33922].value
        transform = (x-i*sx, y+j*sy, sx, sy)
        if float(page.tags[42113].value) != -9999.:
            raise ValueError('Unexpected nodata')
        grid = page.asarray()
    raw_h, route_valid = strict_bilinear(grid, dense_source, transform)
    if not route_valid.all():
        raise ValueError('Section contains invalid raw terrain samples')
    resolution, margin = 2., 120.
    lo = np.floor((section_work.min(axis=0)-margin)/resolution)*resolution
    hi = np.ceil((section_work.max(axis=0)+margin)/resolution)*resolution
    axes = [np.arange(lo[i], hi[i]+resolution/2, resolution) for i in range(2)]
    if len(axes[0])*len(axes[1]) >= 400000:
        raise ValueError('Section grid exceeds vertex budget; coordinator review required')
    xx, yy = np.meshgrid(*axes)
    terrain_work = np.column_stack([xx.ravel(), yy.ravel()])
    terrain_source = project(source_work, terrain_work, inverse=True)
    terrain_h, terrain_valid = strict_bilinear(grid, terrain_source, transform)
    terrain_local = local_positions(terrain_work, terrain_h, terrain_valid, origin)
    shape = xx.shape
    mask = terrain_valid.reshape(shape)
    OUT.mkdir(parents=True, exist_ok=True)
    route_output = save_arrays(OUT/'route.npz', full_xy_25833_m=full_work,
        full_chainage_3035_m=full_s, full_chainage_25833_m=full_work_s,
        section_vertex_chainage_3035_m=section_s, section_vertex_xy_25833_m=section_work,
        chainage_3035_m=dense_s, xy_25833_m=dense_work, xy_3035_m=dense_source,
        raw_height_9274_m=raw_h, valid=route_valid,
        local_xyz_m=local_positions(dense_work, raw_h, route_valid, origin))
    terrain_output = save_arrays(OUT/'terrain.npz', x_m=terrain_local[:, 0].reshape(shape),
        y_m=terrain_local[:, 1].reshape(shape), z_m=terrain_local[:, 2].reshape(shape),
        valid=mask, valid_cells=valid_cells(mask))
    controls_source = source_xy[[0, len(source_xy)//2, -1]]
    controls_work = project(source_work, controls_source)
    controls_back = project(source_work, controls_work, inverse=True)
    controls_local = local_positions(controls_work, np.full(3, 300.), np.ones(3, dtype=bool), origin)
    error = np.linalg.norm(controls_back-controls_source, axis=1)
    if error.max() > .001:
        raise ValueError('Projection roundtrip exceeds 1 mm')
    source_files = [route_path, raster_path, ROOT/'data/interim/terrain/source-tags.json',
                    ROOT/'data/interim/terrain/coverage.json', ROOT/'data/raw/terrain/operation.json']
    source_files += sorted((ROOT/'data/raw/terrain').glob('range-*.bin'))
    source_files += sorted((ROOT/'data/raw/osm').glob('map_*.osm'))
    extent = np.max(np.abs(np.vstack([full_work-origin[:2], terrain_local[:, :2]])))
    manifest = dict(schema='assetto-exelberg.prototype-inputs', version=1,
        purpose='Provisional northern hairpin authoring inputs, not a driving mesh',
        coordinates=dict(horizontal_epsg=25833, vertical_epsg=9274, units='m', origin_m=origin.tolist(),
            origin_rule='Full EPSG:25833 polyline arclength midpoint, each horizontal component rounded nearest 100 m (ties to even)',
            midpoint_25833_m=midpoint.tolist(), axes='right-handed X=easting-E0, Y=northing-N0, Z=orthometric_height-300',
            vertical_transform='none; documented BEV orthometric reference retained'),
        section=dict(start_m=START, end_m=END, convention='EPSG:3035 full route planar chainage; NOT EPSG:25833 or spherical distance',
            full_length_3035_m=float(full_s[-1]), full_length_25833_m=float(full_work_s[-1]),
            samples=len(dense_s), max_sample_step_25833_m=float(np.linalg.norm(np.diff(dense_work, axis=0), axis=1).max()),
            raw_only=True, excluded_anomaly_chainage_m=9589.),
        terrain=dict(resolution_m=resolution, margin_m=margin, shape=list(shape), vertices=xx.size,
            bounds_25833_m=[lo.tolist(), hi.tolist()], bounds_local_xy_m=[(lo-origin[:2]).tolist(), (hi-origin[:2]).tolist()],
            valid_vertices=int(mask.sum()), invalid_vertices=int((~mask).sum()), valid_cells=int(valid_cells(mask).sum()),
            sampling='inverse to EPSG:3035; strict bilinear at pixel centers, all four neighbors required',
            invalid_placeholder_m=0., topology='Only triangulate cells where valid_cells is true; never use invalid vertices as elevation'),
        precision=dict(storage='float64, bool masks; no pickle', max_abs_full_route_or_terrain_xy_m=float(extent),
            float32_spacing_at_max_extent_m=float(np.spacing(np.float32(extent)))),
        transforms=[log1, log2], software=dict(numpy=np.__version__, pyproj=pyproj.__version__, proj=pyproj.proj_version_str),
        controls=dict(source_3035_m=controls_source.tolist(), working_25833_m=controls_work.tolist(),
            local_xyz_m=controls_local.tolist(), control_height_9274_m=300., inverse_3035_m=controls_back.tolist(),
            inverse_errors_m=error.tolist()),
        provenance=dict(inputs=[record(p) for p in source_files],
            note='Raw cached ranges hashed individually; full remote TIFF not downloaded. GeoTIFF pixels previously checked against originals.',
            attribution='Terrain © BEV CC BY 4.0; route © OpenStreetMap contributors ODbL'),
        outputs=dict(route=route_output, terrain=terrain_output),
        orthophoto=dict(path='data/processed/orthophoto/doppler_vicinity.tif',
            manifest='data/processed/orthophoto/manifest.json', horizontal_epsg=31256,
            scope='Reference location only; no resampling or full-section coverage claim'),
        caveats=['OSM alignment provisional; heights are bare-earth samples, not asphalt survey.',
                 'No smoothing, road shaping, camber, widths, mesh, Blender or game validation.',
                 'Grid is a bounded section rectangle, not full-route terrain; preserve masks.'])
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(origin_m=origin.tolist(), section=manifest['section'], terrain=manifest['terrain'],
                          output_bytes={k:v['bytes'] for k,v in manifest['outputs'].items()}), indent=2))


if __name__ == '__main__':
    main()
