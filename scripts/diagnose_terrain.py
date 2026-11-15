#!/usr/bin/env python3
"""Offline dense terrain investigation; never changes route, raster or 10 m profile.

Distances, tangents and normals are derived in EPSG:3035, not road design geometry.
Thresholds flag terrain for investigation, not acceptable/unacceptable road grades.
"""
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import tifffile
from pyproj import Transformer

from extract_terrain import PROCESSED, INTERIM, bilinear, resample_route
from terrain_ranges import save_json

GRADE_FLAG = 20.0
GRADE_CHANGE_FLAG = 20.0


def route_points(xy, distances):
    chain = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    return np.column_stack([np.interp(distances, chain, xy[:, n]) for n in range(2)])


def cross_section(xy, distance, grid, transform):
    length = np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()
    ends = [max(0, distance - 2), min(length, distance + 2)]
    chord = np.diff(route_points(xy, ends), axis=0)[0]
    tangent = chord / np.linalg.norm(chord)
    normal = np.array([-tangent[1], tangent[0]])
    center = route_points(xy, [distance])[0]
    offsets = np.arange(-20., 21.)
    points = center + offsets[:, None] * normal
    heights = bilinear(grid, points, transform)
    return dict(distance_m=float(distance), center_3035_m=center.tolist(),
                tangent_chord_distances_m=ends, tangent_unit_3035=tangent.tolist(),
                left_normal_unit_3035=normal.tolist(), offsets_m=offsets.tolist(),
                sample_xy_3035_m=points.tolist(),
                terrain_heights_m=[float(h) if np.isfinite(h) else None for h in heights])


def investigation_flags(distances, heights):
    grades = np.diff(heights) / np.diff(distances) * 100
    changes = np.r_[np.nan, np.diff(grades)]
    flags = (np.abs(grades) > GRADE_FLAG) | (np.abs(changes) > GRADE_CHANGE_FLAG)
    return grades, changes, flags


def grouped_intervals(distances, grades, changes, flags):
    indices = np.flatnonzero(flags)
    groups = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    result = []
    for group in groups:
        if not len(group):
            continue
        peak = group[np.argmax(np.abs(grades[group]))]
        result.append(dict(start_m=float(distances[group[0]]), end_m=float(distances[group[-1]+1]),
                           flagged_intervals=len(group), peak_interval_start_m=float(distances[peak]),
                           max_absolute_terrain_gradient_percent=float(np.max(np.abs(grades[group]))),
                           max_absolute_gradient_change_percentage_points=float(np.nanmax(np.abs(changes[group])))
                           if np.isfinite(changes[group]).any() else None))
    return sorted(result, key=lambda r: r['max_absolute_terrain_gradient_percent'], reverse=True)


def support_tiles(points, source_transform, width):
    x0, y0, sx, sy = source_transform
    tiles = set()
    nx = math.ceil(width / 512)
    for x, y in points:
        c, r = math.floor((x-x0)/sx-.5), math.floor((y0-y)/sy-.5)
        tiles.update(rr//512*nx+cc//512 for rr in (r, r+1) for cc in (c, c+1))
    return sorted(tiles)


def sections_svg(sections):
    panels = []
    for i, section in enumerate(sections):
        top = 100 + i * 210
        heights = section['terrain_heights_m']
        finite = [h for h in heights if h is not None]
        low, high = math.floor(min(finite)), math.ceil(max(finite))
        span = max(1, high-low)
        runs, run = [], []
        for offset, height in zip(section['offsets_m'], heights):
            if height is not None:
                run.append(f'{100+(offset+20)*20:.2f},{top+140-(height-low)/span*130:.2f}')
            elif run:
                runs.append(run); run = []
        if run:
            runs.append(run)
        lines = ''.join(f'<polyline points="{" ".join(p)}" fill="none" stroke="#176b39" stroke-width="2"/>' for p in runs)
        cx, cy = section['center_3035_m']
        nx, ny = section['left_normal_unit_3035']
        panels.append(f'''<text x="100" y="{top-20}">d={section['distance_m']:.1f} m; center=({cx:.3f}, {cy:.3f}); left normal=({nx:.6f}, {ny:.6f})</text>
<path d="M100 {top} V{top+140} H900 M500 {top} V{top+140}" stroke="#aaa" fill="none"/>{lines}
<text x="20" y="{top+10}">{high} m</text><text x="20" y="{top+140}">{low} m</text>
<text x="100" y="{top+165}">-20 m (right)</text><text x="465" y="{top+165}">0 (route)</text><text x="790" y="{top+165}">+20 m (left)</text>''')
    height = 130 + 210*len(sections)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}">
<rect width="1100" height="{height}" fill="white"/><g font-family="sans-serif" font-size="13" fill="#222">
<text x="40" y="25" font-size="20">BEV terrain cross-sections — investigation only, not road shape</text>
<text x="40" y="48">EPSG:3035; 1 m offsets; left normal=(-tangent_y, tangent_x); tangent from route chord d-2 to d+2 m.</text>
<text x="40" y="69">EPSG:9274 orthometric heights; independent panel height scales. No fitting, smoothing or repair.</text>
{''.join(panels)}<text x="40" y="{height-12}">© BEV CC BY 4.0; route © OpenStreetMap contributors ODbL. Terrain alone cannot identify structures or artifacts.</text>
</g></svg>'''


def main():
    route_bytes = (PROCESSED/'route.geojson').read_bytes()
    coords = np.asarray(json.loads(route_bytes)['features'][0]['geometry']['coordinates'])[:, :2]
    xy = np.column_stack(Transformer.from_crs(4326,3035,always_xy=True).transform(coords[:,0],coords[:,1]))
    with tifffile.TiffFile(PROCESSED/'terrain_corridor_3035.tif') as tif:
        page = tif.pages[0]
        assert page.geotiff_tags['ProjectedCSTypeGeoKey'] == 3035
        grid = page.asarray()
        scale, tie = page.tags[33550].value, page.tags[33922].value
        transform = (tie[3], tie[4], scale[0], scale[1])
    distances, points = resample_route(xy, 1)
    heights = bilinear(grid, points, transform)
    grades, changes, flags = investigation_flags(distances, heights)
    groups = grouped_intervals(distances, grades, changes, flags)
    with (PROCESSED/'terrain_diagnostic_1m.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['distance_3035_m', 'easting_3035_m', 'northing_3035_m', 'terrain_height_9274_m', 'valid',
                         'terrain_gradient_from_previous_percent', 'gradient_change_percentage_points', 'investigation_flag'])
        for i, (d, point, h) in enumerate(zip(distances, points, heights)):
            writer.writerow([f'{d:.3f}', *[f'{v:.3f}' for v in point], f'{h:.6f}' if np.isfinite(h) else '',
                             int(np.isfinite(h)), f'{grades[i-1]:.6f}' if i and np.isfinite(grades[i-1]) else '',
                             f'{changes[i-1]:.6f}' if i and np.isfinite(changes[i-1]) else '', int(flags[i-1]) if i else 0])
    section_distances = sorted(set([9585., 9589., 9593.] +
                                  [g['peak_interval_start_m']+.5 for g in groups[:5]]))
    sections = [cross_section(xy, d, grid, transform) for d in section_distances]
    estimate = json.loads((INTERIM/'acquisition-estimate.json').read_text())
    for section in sections:
        section['source_support_tile_indices'] = support_tiles(section['sample_xy_3035_m'], estimate['source_transform'], estimate['source_width'])
    suspect = (distances >= 9580) & (distances <= 9610)
    report = dict(horizontal_crs='EPSG:3035', height_reference='EPSG:9274 EVRF2000 Austria (documented product reference)',
                  height_units='m', route_sha256=hashlib.sha256(route_bytes).hexdigest(),
                  sampling='1 m planar route chainage plus endpoint; strict four-pixel bilinear, no smoothing',
                  interpretation='Investigation flags only, not road grades. Terrain alone cannot distinguish culvert, ground-under-road, alignment error or source artifact.',
                  thresholds=dict(absolute_terrain_gradient_percent=GRADE_FLAG, absolute_gradient_change_percentage_points=GRADE_CHANGE_FLAG),
                  samples=len(distances), invalid_samples=int((~np.isfinite(heights)).sum()),
                  distance_m=float(distances[-1]), flagged_intervals=int(flags.sum()),
                  max_absolute_terrain_gradient_percent=float(np.nanmax(np.abs(grades))),
                  grouped_intervals=groups,
                  suspect_profile=[dict(distance_m=float(d), terrain_height_m=float(h)) for d,h in zip(distances[suspect],heights[suspect])],
                  suspect_source_support_tile_indices=support_tiles(points[suspect],estimate['source_transform'],estimate['source_width']),
                  cross_section_derivation='Center: piecewise-linear provisional route at chainage. Unit tangent: normalized chord d-2 to d+2 m (clipped at endpoints). Left unit normal=(-ty,tx). Sample center+offset*normal, -20..20 m by 1 m.',
                  cross_sections=sections)
    save_json(PROCESSED/'terrain_diagnostic_1m.json', report)
    (PROCESSED/'terrain_diagnostic_cross_sections.svg').write_text(sections_svg(sections))
    print(json.dumps({k:v for k,v in report.items() if k not in ('cross_sections','suspect_profile','grouped_intervals')}, indent=2))
    print('Top investigation groups:', json.dumps(groups[:5], indent=2))


if __name__ == '__main__':
    main()
