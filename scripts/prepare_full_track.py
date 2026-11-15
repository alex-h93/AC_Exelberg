#!/usr/bin/env python3
"""Offline full-route raw-data handoff. No road design, terrain fill or Blender."""
import json
import math
import os
from pathlib import Path

os.environ['PROJ_NETWORK'] = 'OFF'
import numpy as np
import tifffile

from prepare_prototype import (ROOT, operation, project, stations, interpolate,
    densify, strict_bilinear, local_positions, valid_cells, record, save_arrays)

OUT = ROOT / 'data/processed/full_track_inputs'
ORIGIN = np.array([589500., 5346800., 300.])
OFFSETS = np.array([-15., -8., -3.75, -3., 3., 3.75, 8., 15.])


def nearest_segment_distance(points, route, batch=256):
    """Exact planar distance to every original segment, including hairpins."""
    a, v = route[:-1], np.diff(route, axis=0)
    vv = np.sum(v*v, axis=1)
    if np.any(vv <= 0):
        raise ValueError('Zero length segment')
    result = np.empty(len(points))
    for start in range(0, len(points), batch):
        d = points[start:start+batch, None, :] - a
        t = np.clip(np.sum(d*v, axis=2)/vv, 0., 1.)
        result[start:start+batch] = np.sqrt(np.min(np.sum((d-t[..., None]*v)**2, axis=2), axis=1))
    return result


def normals(xy):
    """Centered raw-route tangent; positive offset is left of travel."""
    tangent = np.empty_like(xy)
    tangent[1:-1] = xy[2:]-xy[:-2]
    tangent[0], tangent[-1] = xy[1]-xy[0], xy[-1]-xy[-2]
    length = np.linalg.norm(tangent, axis=1)
    if np.any(length <= 0):
        raise ValueError('Undefined normal; alignment review required')
    return np.column_stack([-tangent[:, 1], tangent[:, 0]]) / length[:, None]


def grid_axes(route, resolution=8., margin=200., cap=1600000):
    lo = np.floor((route.min(axis=0)-margin)/resolution)*resolution
    hi = np.ceil((route.max(axis=0)+margin)/resolution)*resolution
    axes = [np.arange(lo[i], hi[i]+resolution/2, resolution) for i in range(2)]
    if math.prod(map(len, axes)) > cap:
        raise ValueError('Terrain node budget exceeded')
    return axes, lo, hi


def tiles(shape, cells=128):
    """[row start, row stop, col start, col stop], exclusive node stops.

    Adjacent tiles share one boundary node; no cells overlap.
    """
    return np.array([[r, min(r+cells+1, shape[0]), c, min(c+cells+1, shape[1])]
        for r in range(0, shape[0]-1, cells)
        for c in range(0, shape[1]-1, cells)], dtype=np.int64)


def roadside_candidates(route, seed=20260221):
    """Synthetic rows, NOT an OSM forest classification or observed trees."""
    rng = np.random.default_rng(seed)
    s = stations(route)
    base_s = np.arange(12.5, s[-1], 25.)
    center = interpolate(route, s, base_s)
    normal = normals(center)
    offsets = np.array([-145., -100., -60., -30., -12., 12., 30., 60., 100., 145.])
    xy = center[:, None, :] + normal[:, None, :] * offsets[None, :, None]
    xy += rng.uniform(-1., 1., xy.shape)
    xy = xy.reshape(-1, 2)
    distance = nearest_segment_distance(xy, route)
    keep = distance > 10.
    return xy[keep], np.repeat(base_s, len(offsets))[keep], distance[keep]


def main():
    route_path = ROOT/'data/processed/route.geojson'
    raster_path = ROOT/'data/processed/terrain_corridor_3035.tif'
    osm_path = ROOT/'data/interim/osm/merged.json'
    wgs = np.asarray(json.loads(route_path.read_text())['features'][0]['geometry']['coordinates'])[:, :2]
    t1, log1 = operation(4326, 3035)
    t2, log2 = operation(3035, 25833)
    source = project(t1, wgs)
    full = project(t2, source)
    s3035, sutm = stations(source), stations(full)
    dense_s, xy = densify(full, s3035, 2.)
    dense_utm, check_xy = densify(full, sutm, 2.)
    np.testing.assert_array_equal(xy, check_xy)
    with tifffile.TiffFile(raster_path) as tif:
        page = tif.pages[0]
        tags = page.geotiff_tags
        if tags['ProjectedCSTypeGeoKey'] != 3035 or tags['GTRasterTypeGeoKey'] != 1:
            raise ValueError('Expected EPSG:3035 PixelIsArea')
        sx, sy, _ = page.tags[33550].value
        i, j, _, x, y, _ = page.tags[33922].value
        if max(sx, sy) > 10 or float(page.tags[42113].value) != -9999.:
            raise ValueError('Unsupported source resolution/nodata')
        transform = (x-i*sx, y+j*sy, sx, sy)
        grid = page.asarray()

    def sample(work):
        return strict_bilinear(grid, project(t2, work, inverse=True), transform)

    h, valid = sample(xy)
    if not valid.all():
        raise ValueError('Full route has raw terrain coverage gaps; coordinator review required')
    lateral_xy = xy[:, None, :] + normals(xy)[:, None, :]*OFFSETS[None, :, None]
    lateral_h, lateral_valid = sample(lateral_xy.reshape(-1, 2))
    axes, lo, hi = grid_axes(full)
    xx, yy = np.meshgrid(*axes)
    shape = xx.shape
    # Bound projection/sampling temporaries to one 128-row strip.
    th = np.zeros(shape)
    tv = np.zeros(shape, dtype=bool)
    for r in range(0, shape[0], 128):
        points = np.column_stack([xx[r:r+128].ravel(), yy[r:r+128].ravel()])
        hh, vv = sample(points)
        th[r:r+128] = hh.reshape(xx[r:r+128].shape)
        tv[r:r+128] = vv.reshape(xx[r:r+128].shape)
    tree_xy, tree_s, tree_distance = roadside_candidates(full)
    tree_h, tree_valid = sample(tree_xy)
    # Require all containing terrain-cell corners valid, so anchors are not
    # placed on apparent coverage slivers that cannot be triangulated.
    cell = valid_cells(tv)
    ci = np.floor((tree_xy-lo)/8.).astype(int)
    inside = (ci[:, 0] >= 0) & (ci[:, 1] >= 0) & (ci[:, 0] < cell.shape[1]) & (ci[:, 1] < cell.shape[0])
    safe = np.zeros(len(ci), bool)
    safe[inside] = cell[ci[inside, 1], ci[inside, 0]]
    keep = tree_valid & safe
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {}
    outputs['route'] = save_arrays(OUT/'route.npz', full_xy_25833_m=full,
        full_xy_3035_m=source, full_chainage_3035_m=s3035, full_chainage_25833_m=sutm,
        chainage_3035_m=dense_s, chainage_25833_m=dense_utm, xy_25833_m=xy,
        xy_3035_m=project(t2, xy, inverse=True), raw_height_9274_m=h, valid=valid,
        local_xyz_m=local_positions(xy, h, valid, ORIGIN))
    outputs['lateral'] = save_arrays(OUT/'lateral.npz', offsets_m=OFFSETS,
        xy_25833_m=lateral_xy, raw_height_9274_m=lateral_h.reshape(lateral_xy.shape[:2]),
        valid=lateral_valid.reshape(lateral_xy.shape[:2]),
        local_xyz_m=local_positions(lateral_xy.reshape(-1, 2), lateral_h, lateral_valid, ORIGIN).reshape(-1, len(OFFSETS), 3))
    outputs['terrain'] = save_arrays(OUT/'terrain.npz', x_m=xx-ORIGIN[0], y_m=yy-ORIGIN[1],
        z_m=np.where(tv, th-ORIGIN[2], 0.), raw_height_9274_m=th, valid=tv,
        valid_cells=cell, tile_node_slices=tiles(shape))
    outputs['trees'] = save_arrays(OUT/'trees.npz', xy_25833_m=tree_xy[keep],
        raw_height_9274_m=tree_h[keep], local_xyz_m=local_positions(tree_xy[keep], tree_h[keep], np.ones(keep.sum(), bool), ORIGIN),
        valid=np.ones(keep.sum(), bool), generating_chainage_25833_m=tree_s[keep],
        nearest_route_segment_distance_m=tree_distance[keep])
    elements = json.loads(osm_path.read_text())['elements']
    forest = lambda e: e.get('tags', {}).get('landuse') == 'forest' or e.get('tags', {}).get('natural') == 'wood'
    forest_counts = {kind: sum(e['type'] == kind and forest(e) for e in elements) for kind in ('way', 'relation')}
    controls_source = source[[0, len(source)//2, -1]]
    controls_work = project(t2, controls_source)
    back = project(t2, controls_work, inverse=True)
    errors = np.linalg.norm(back-controls_source, axis=1)
    if errors.max() > .001:
        raise ValueError('Control roundtrip exceeds 1 mm')
    anomaly = (dense_s >= 9580) & (dense_s <= 9600)
    diagnostic = dict(suspected_profile_chainage_3035_m=[9580., 9600.],
        chainage_3035_m=dense_s[anomaly].tolist(), raw_height_9274_m=h[anomaly].tolist(),
        max_abs_adjacent_raw_grade=float(np.max(np.abs(np.diff(h)/np.diff(dense_utm)))),
        disposition='Raw dip retained. Blender specialist must audit any candidate correction separately; not an approved road profile.')
    sources = [route_path, raster_path, osm_path, ROOT/'data/interim/terrain/coverage.json',
        ROOT/'data/interim/terrain/source-tags.json', ROOT/'data/raw/terrain/operation.json']
    sources += sorted((ROOT/'data/raw/terrain').glob('range-*.bin'))
    manifest = dict(schema='assetto-exelberg.full-track-inputs', version=1,
        coordinates=dict(horizontal_epsg=25833, vertical_epsg=9274, origin_m=ORIGIN.tolist(),
            units='m', axes='X=E-589500, Y=N-5346800, Z=H-300; right-handed',
            vertical_transform='none; BEV documented EVRF2000 Austria orthometric heights, not independent survey'),
        route=dict(start_m=0., end_m=float(s3035[-1]), convention='EPSG:3035 chainage labels on native UTM straight-segment densification',
            full_length_3035_m=float(s3035[-1]), full_length_25833_m=float(sutm[-1]), samples=len(xy),
            max_step_25833_m=float(np.linalg.norm(np.diff(xy, axis=0), axis=1).max()),
            corners='All original OSM vertices retained exactly; no smoothing or clipping beyond original endpoints', direction='Königstetten to Marswiese'),
        terrain=dict(resolution_m=8., source_resolution_m=[sx, sy], shape=list(shape), nodes=xx.size,
            cap_nodes=1600000, bounds_25833_m=[lo.tolist(), hi.tolist()], margin_m=200.,
            valid_nodes=int(tv.sum()), valid_cells=int(cell.sum()), invalid_nodes=int((~tv).sum()),
            topology='Triangulate only valid_cells; 128x128-cell tiles share boundary nodes; no fill',
            sampling='Inverse XY to original EPSG:3035 1m raster, strict four-support-pixel bilinear, no vertical transform'),
        lateral=dict(offsets_m=OFFSETS.tolist(), normal='Centered tangent of raw densified alignment; positive left of travel',
            valid_samples=int(lateral_valid.sum()), total_samples=len(lateral_valid), purpose='Raw shoulder/verge ground references only; NOT a road cross-section'),
        trees=dict(count=int(keep.sum()), seed=20260221, generating_spacing_m=25.,
            label='SYNTHETIC ROADSIDE DISTRIBUTION, NOT MEASURED FOREST', forest_mask_implemented=False,
            osm_forest_tag_counts=forest_counts, unresolved_forest_relations=forest_counts['relation'],
            offsets_m=[-145,-100,-60,-30,-12,12,30,60,100,145], jitter_m=1.,
            constraints='Actual valid raw ground, valid containing terrain cell, exact distance >10m from ALL original route segments',
            warning='OSM tags inventoried only. Polygon topology/holes/relations NOT resolved; candidates may lie in fields/buildings/clearings. Optional authoring placeholders only.'),
        diagnostics=diagnostic, transforms=[log1, log2],
        controls=dict(source_3035_m=controls_source.tolist(), working_25833_m=controls_work.tolist(),
            local_xyz_m=local_positions(controls_work, np.full(3, 300.), np.ones(3, bool), ORIGIN).tolist(),
            synthetic_height_9274_m=300., inverse_3035_m=back.tolist(), inverse_errors_m=errors.tolist()),
        invalid_values='All arrays finite. Invalid raw height and local Z are zero placeholders; validity masks mandatory.',
        provenance=dict(inputs=[record(p) for p in sources], attribution='Terrain © BEV CC BY 4.0; OSM © OpenStreetMap contributors ODbL'),
        outputs=outputs,
        caveats=['Raw data only: no road width/camber, terrain alteration, mesh or road correction.',
            'Full two-lane road design belongs to Blender specialist; offsets are reference probes, not approved widths.',
            'User reports v001 loads but spawn backwards and falls off mountain; no runtime fix or test is implied here.',
            'No game/live GUI/source writes/network/install. No invented terrain beyond acquired valid coverage.'])
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: manifest[k] for k in ('route', 'terrain', 'trees')}, indent=2))


if __name__ == '__main__':
    main()
