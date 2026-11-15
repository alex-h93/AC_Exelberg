#!/usr/bin/env python3
"""v004 vegetation placement from the BEV canopy height model (DSM - DTM).

Run from the project root with the .venv Python. Inputs are read-only:
  data/processed/surface_v004/chm_400_3035.tif (+ summary.json)
  data/processed/full_track_scene_v003/repaired_skin.npz  (final v003 ground skin)
  data/raw/osm/*.osm, data/raw/full_forest/*.osm         (buildings, leaf_type)
Output: data/processed/vegetation_v004/{trees.npz, summary.json, preview.png}

Tree positions and heights are measured (local CHM maxima); species are
assigned plausibly (OSM leaf_type where tagged, otherwise a seeded mix) and are
NOT surveyed. Shrubs come from low (1.5-5 m) canopy areas near the road.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import full_track_v003_geometry as H  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/vegetation_v004'
ORIGIN = np.array([589500.0, 5346800.0, 300.0])
SEED = 4004
MAX_DIST = 195.0      # ground skin covers ~±200 m
MIN_TRUNK_DIST = 7.0  # centerline; invisible wall at 6 m
SPECIES = ('beech', 'oak', 'conifer', 'shrub')


def box_mean(a, r):
    k = 2 * r + 1
    p = np.pad(a, r, mode='edge').astype(np.float64)
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return (s / (k * k)).astype(np.float32)


def max_filter(a, r):
    out = a.copy()
    for axis in (0, 1):
        src = out.copy()
        for s in range(1, r + 1):
            for sign in (1, -1):
                sh = np.roll(src, sign * s, axis=axis)
                np.maximum(out, sh, out=out)
    return out


def load_osm():
    nodes, ways = {}, []
    files = sorted((ROOT / 'data/raw/osm').glob('*.osm')) + sorted((ROOT / 'data/raw/full_forest').glob('*.osm'))
    for f in files:
        for el in ET.parse(f).getroot():
            if el.tag == 'node':
                nodes[el.get('id')] = (float(el.get('lon')), float(el.get('lat')))
            elif el.tag == 'way':
                tags = {t.get('k'): t.get('v') for t in el.findall('tag')}
                ways.append((el.get('id'), [n.get('ref') for n in el.findall('nd')], tags))
    uniq = {}
    for wid, refs, tags in ways:
        uniq[wid] = (refs, tags)
    buildings, needle = [], []
    for refs, tags in uniq.values():
        pts = [nodes[r] for r in refs if r in nodes]
        if len(pts) < 3 or len(pts) != len(refs):
            continue
        if 'building' in tags:
            buildings.append(pts)
        if tags.get('leaf_type') == 'needleleaved':
            needle.append(pts)
    return buildings, needle


def raster_polys(polys, transform, shape, to3035, buffer_px=0):
    x0, y0, sx, sy = transform
    img = Image.new('L', (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(img)
    for p in polys:
        lon, lat = np.array(p).T
        x, y = to3035.transform(lon, lat)
        cols = (np.asarray(x) - x0) / sx
        rows = (y0 - np.asarray(y)) / sy
        xy = list(zip(cols.tolist(), rows.tolist()))
        d.polygon(xy, fill=255, outline=255)
        if buffer_px:
            d.line(xy + [xy[0]], fill=255, width=2 * buffer_px + 1)
    return np.asarray(img) > 0


def centerline_distance(points, line, cell=20.0):
    """Approximate (≤ ~1 m) nearest distance to the designed centerline vertices."""
    grid = {}
    for i, (x, y) in enumerate(line[:, :2]):
        grid.setdefault((int(x // cell), int(y // cell)), []).append(i)
    out = np.full(len(points), np.inf)
    keys = np.floor(points / cell).astype(int)
    reach = int(np.ceil(MAX_DIST / cell)) + 1
    for k in set(map(tuple, keys)):
        sel = np.where((keys[:, 0] == k[0]) & (keys[:, 1] == k[1]))[0]
        ids = []
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                ids.extend(grid.get((k[0] + dx, k[1] + dy), ()))
        if not ids:
            continue
        lp = line[ids, :2]
        d = np.sqrt(((points[sel, None, :] - lp[None]) ** 2).sum(-1)).min(1)
        out[sel] = d
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    summary = json.loads((ROOT / 'data/processed/surface_v004/summary.json').read_text())
    transform = summary['transform']
    x0, y0, sx, sy = transform
    chm = tifffile.imread(ROOT / 'data/processed/surface_v004/chm_400_3035.tif')
    valid = chm != -9999
    chm = np.where(valid, chm, 0).astype(np.float32)
    to3035 = Transformer.from_crs(4326, 3035, always_xy=True)
    to25833 = Transformer.from_crs(3035, 25833, always_xy=True)

    print('osm…', flush=True)
    buildings, needle = load_osm()
    bmask = raster_polys(buildings, transform, chm.shape, to3035, buffer_px=2)
    nmask = raster_polys(needle, transform, chm.shape, to3035)

    print('maxima…', flush=True)
    smooth = box_mean(chm, 1)
    peaks = np.zeros(chm.shape, bool)
    for lo, hi, r in ((1.5, 5.0, 2), (5.0, 14.0, 3), (14.0, 24.0, 4), (24.0, 80.0, 5)):
        band = (smooth >= lo) & (smooth < hi)
        mf = max_filter(smooth, r)
        peaks |= band & (smooth >= mf - 1e-4)
    peaks &= valid & ~bmask
    rows, cols = np.nonzero(peaks)
    h = smooth[rows, cols]
    ex = x0 + (cols + 0.5) * sx
    ny = y0 - (rows + 0.5) * sy
    E, N = to25833.transform(ex, ny)
    xy = np.column_stack([np.asarray(E) - ORIGIN[0], np.asarray(N) - ORIGIN[1]])

    skin = np.load(ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz')
    line = skin['designed_xyz_m']
    print('distances…', len(xy), flush=True)
    dist = centerline_distance(xy, line)
    keep = (dist >= MIN_TRUNK_DIST) & (dist <= MAX_DIST)
    # shrubs only near the road where they read as forest edge / hedge
    is_shrub = h < 5.0
    keep &= ~is_shrub | (dist <= 60.0)
    xy, h, dist, rows, cols, is_shrub = xy[keep], h[keep], dist[keep], rows[keep], cols[keep], is_shrub[keep]
    # Thin dense tall-forest maxima far from the road (impostor tier) to bound counts.
    far = dist > 80.0
    thin = far & (rng.random(len(h)) < 0.35)
    xy, h, dist, rows, cols, is_shrub = xy[~thin], h[~thin], dist[~thin], rows[~thin], cols[~thin], is_shrub[~thin]

    print('grounding…', len(xy), flush=True)
    v, f = skin['vertices'], skin['triangles']
    ground = H.GroundIndex(v, f, size=16)
    z = np.full(len(xy), np.nan)
    for i, p in enumerate(xy):
        try:
            z[i] = ground.sample(p)
        except Exception:
            pass
        if i % 20000 == 0:
            print('  ', i, flush=True)
    ok = np.isfinite(z)
    xy, h, dist, rows, cols, is_shrub, z = xy[ok], h[ok], dist[ok], rows[ok], cols[ok], is_shrub[ok], z[ok]

    n = len(xy)
    needle_here = nmask[rows, cols]
    u = rng.random(n)
    species = np.where(is_shrub, 3,
               np.where(needle_here, np.where(u < 0.8, 2, 0),
               np.where(u < 0.65, 0, np.where(u < 0.9, 1, 2))))
    crown = np.clip(np.where(species == 2, 0.13 * h + 0.8, 0.2 * h + 1.0), 1.0, 7.5)
    crown = np.where(species == 3, np.clip(0.45 * h + 0.6, 0.8, 2.5), crown)
    tier = np.where(dist <= 45.0, 0, 1)  # 0 = hero 3D near road, 1 = impostor
    np.savez_compressed(OUT / 'trees.npz', xyz=np.column_stack([xy, z]).astype(np.float32),
                        height=h.astype(np.float32), crown=crown.astype(np.float32),
                        species=species.astype(np.int8), tier=tier.astype(np.int8),
                        dist=dist.astype(np.float32), seed=rng.integers(0, 2**31, n).astype(np.int64))
    counts = {s: int((species == i).sum()) for i, s in enumerate(SPECIES)}
    res = dict(trees=int(n), species=counts, hero=int((tier == 0).sum()), impostor=int((tier == 1).sum()),
               height_percentiles={p: float(np.percentile(h[~is_shrub], p)) for p in (10, 50, 90)},
               buildings_masked=len(buildings), needleleaved_polys=len(needle),
               method='CHM 1 m (DSM-DTM) 3x3 mean, height-adaptive local maxima, buildings (OSM, +2 px) masked, '
                      f'trunks {MIN_TRUNK_DIST}-{MAX_DIST} m from designed centerline, 35% thinning beyond 80 m, '
                      'shrubs (<5 m) only within 60 m; species seeded/plausible, not surveyed',
               seed=SEED)
    (OUT / 'summary.json').write_text(json.dumps(res, indent=2) + '\n')
    print(json.dumps(res, indent=2))
    # preview
    W = 1600
    lo, hi = xy.min(0), xy.max(0)
    s = W / (hi - lo).max()
    img = Image.new('RGB', (W, int((hi - lo)[1] * s) + 10), (20, 20, 20))
    d = ImageDraw.Draw(img)
    cols_rgb = [(60, 170, 60), (170, 140, 40), (40, 90, 160), (200, 200, 80)]
    for (px, py), sp in zip((xy - lo) * s, species):
        d.point((px, img.height - 5 - py), fill=cols_rgb[sp])
    for px, py in (line[:, :2] - lo) * s:
        d.point((px, img.height - 5 - py), fill=(255, 40, 40))
    img.save(OUT / 'preview.png')


if __name__ == '__main__':
    main()
