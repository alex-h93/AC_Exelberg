#!/usr/bin/env python3
"""v010 tree list (offline, .venv). Input: v004 trees (vegetation_v004/trees.npz), v009 road field, v010 patch + skin,
extension CHM (data/processed/extension_v010/chm_3035.tif).

  * v004 trees OUTSIDE the v010 patch area B: same trees, XY moved by the v009 road field (as the v009 build did
    per vertex), re-grounded on the v010 skin.
  * inside B: v004 trees dropped; new trees from the extension CHM with the v004 method (3x3 mean, height-adaptive
    local maxima, OSM buildings +2 px masked, trunks MIN_TRUNK_DIST..R m from the NEW centreline, shrubs only within
    60 m, 35 % thinning beyond 80 m, species/crowns as v004, seeded), grounded on the v010 skin.
Output: data/processed/extension_v010/trees_v010.npz (same fields as v004 trees.npz) + trees_v010.json
"""
import json
from pathlib import Path

import numpy as np
import shapely
import tifffile
from pyproj import Transformer
from shapely.geometry import Polygon

import full_track_v003_geometry as H
import v004_vegetation as V
from v009_field import Field

ROOT = Path(__file__).resolve().parents[1]
EXT = Path(__import__('os').environ.get('V010_EXT', ROOT / 'data/processed/extension_v010'))  # v011: reverse-track variant
SEED = 4010


def main():
    rng = np.random.default_rng(SEED)
    tr = np.load(ROOT / 'data/processed/vegetation_v004/trees.npz')
    old = {k: tr[k] for k in tr.files}
    c9 = np.load(ROOT / 'data/processed/road_v009/centerline.npz')
    F9 = Field(c9['old_designed_xyz_m'], c9['new_designed_xyz_m'])
    xy9 = F9.displace(old['xyz'][:, :2].astype(float))
    dm = np.load(EXT / 'patch_domain.npz')
    B = Polygon(dm['B_xy'])
    inB = shapely.contains_xy(B, xy9[:, 0], xy9[:, 1])
    keep = ~inB
    # new trees in B from the extension CHM
    summ = json.loads((EXT / 'surface_summary.json').read_text())
    transform = summ['transform']
    x0, y0, sx, sy = transform
    chm = tifffile.imread(EXT / 'chm_3035.tif')
    valid = chm != -9999
    chm = np.where(valid, chm, 0).astype(np.float32)
    to3035 = Transformer.from_crs(4326, 3035, always_xy=True)
    to25833 = Transformer.from_crs(3035, 25833, always_xy=True)
    buildings, needle = V.load_osm()
    bmask = V.raster_polys(buildings, transform, chm.shape, to3035, buffer_px=2)
    nmask = V.raster_polys(needle, transform, chm.shape, to3035)
    smooth = V.box_mean(chm, 1)
    peaks = np.zeros(chm.shape, bool)
    for lo, hi, r in ((1.5, 5.0, 2), (5.0, 14.0, 3), (14.0, 24.0, 4), (24.0, 80.0, 5)):
        band = (smooth >= lo) & (smooth < hi)
        peaks |= band & (smooth >= V.max_filter(smooth, r) - 1e-4)
    peaks &= valid & ~bmask
    rows, cols = np.nonzero(peaks)
    h = smooth[rows, cols]
    E, Nn = to25833.transform(x0 + (cols + 0.5) * sx, y0 - (rows + 0.5) * sy)
    xy = np.column_stack([np.asarray(E) - V.ORIGIN[0], np.asarray(Nn) - V.ORIGIN[1]])
    inside = shapely.contains_xy(B, xy[:, 0], xy[:, 1])
    xy, h, rows, cols = xy[inside], h[inside], rows[inside], cols[inside]
    P = np.load(EXT / 'route.npz')['designed_xyz_m']
    dist = V.centerline_distance(xy, P)
    ok = (dist >= V.MIN_TRUNK_DIST) & (dist <= V.MAX_DIST)
    is_shrub = h < 5.0
    ok &= ~is_shrub | (dist <= 60.0)
    xy, h, dist, rows, cols, is_shrub = xy[ok], h[ok], dist[ok], rows[ok], cols[ok], is_shrub[ok]
    thin = (dist > 80.0) & (rng.random(len(h)) < 0.35)
    xy, h, dist, rows, cols, is_shrub = xy[~thin], h[~thin], dist[~thin], rows[~thin], cols[~thin], is_shrub[~thin]
    n = len(xy)
    u = rng.random(n)
    species = np.where(is_shrub, 3, np.where(nmask[rows, cols], np.where(u < 0.8, 2, 0), np.where(u < 0.65, 0, np.where(u < 0.9, 1, 2))))
    crown = np.clip(np.where(species == 2, 0.13 * h + 0.8, 0.2 * h + 1.0), 1.0, 7.5)
    crown = np.where(species == 3, np.clip(0.45 * h + 0.6, 0.8, 2.5), crown)
    tier = np.where(dist <= 45.0, 0, 1)
    seeds = rng.integers(0, 2**31, n).astype(np.int64)
    # merge + ground on the v010 skin
    allxy = np.vstack([xy9[keep], xy])
    sk = np.load(EXT / 'skin_v010.npz')
    ground = H.GroundIndex(sk['vertices'], sk['triangles'], size=16)
    z = np.full(len(allxy), np.nan)
    for i, q in enumerate(allxy):
        try:
            z[i] = ground.sample(q)
        except Exception:
            pass
    good = np.isfinite(z)
    out = dict(xyz=np.column_stack([allxy, z])[good].astype(np.float32),
               height=np.r_[old['height'][keep], h][good].astype(np.float32),
               crown=np.r_[old['crown'][keep], crown][good].astype(np.float32),
               species=np.r_[old['species'][keep], species][good].astype(np.int8),
               tier=np.r_[old['tier'][keep], tier][good].astype(np.int8),
               dist=np.r_[old['dist'][keep], dist][good].astype(np.float32),
               seed=np.r_[old['seed'][keep], seeds][good].astype(np.int64),
               new=np.r_[np.zeros(keep.sum(), bool), np.ones(n, bool)][good])
    np.savez_compressed(EXT / 'trees_v010.npz', **out)
    info = dict(v004_trees=int(len(old['xyz'])), dropped_in_patch=int(inB.sum()), new_in_patch=int(n),
                not_on_ground=int((~good).sum()), total=int(good.sum()), new_hero=int((tier == 0).sum()),
                new_species={s: int((species == i).sum()) for i, s in enumerate(V.SPECIES)}, seed=SEED, note=__doc__)
    (EXT / 'trees_v010.json').write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps({k: v for k, v in info.items() if k != 'note'}, indent=1))


if __name__ == '__main__':
    main()
