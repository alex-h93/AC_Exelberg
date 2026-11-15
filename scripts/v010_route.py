#!/usr/bin/env python3
"""v010 extended designed centreline (offline, .venv).

Old stations 0..i_cut+1 keep their exact v009 positions and heights (i_cut = CUT_BACK_M before the old end), so the
whole existing track (road, normals, spawn) is untouched up to there. From i_cut the road follows a fresh v009-style
fit (scripts/v009_centerline.fit: curvature-smooth curve through the OSM nodes) of the old raw route + the OSM extension
(scripts/v010_osm_extension.py), blended in over BLEND_M. Heights of the new part: BEV DTM 1 m (extension mosaic)
along the raw line, Gaussian sigma 4 m (as v002), blended into the old profile over BLEND_M.
Output: data/processed/extension_v010/route.npz (designed_xyz_m, i_cut, finish/ring arclengths), route.json
"""
import json
from pathlib import Path

import numpy as np
import tifffile
from pyproj import Transformer

import v009_centerline as C9
from extract_terrain import bilinear
from v009_field import station_normals

ROOT = Path(__file__).resolve().parents[1]
EXT = Path(__import__('os').environ.get('V010_EXT', ROOT / 'data/processed/extension_v010'))  # v011: reverse-track variant
CUT_BACK_M, BLEND_M, STEP_M, Z_SIGMA = 60.0, 30.0, 2.0, 4.0


def gaussian_profile(s, z, sigma):
    u = np.arange(0, s[-1] + 1e-9, 0.5)
    zu = np.interp(u, s, z)
    n = int(np.ceil(3 * sigma / 0.5))
    t = np.arange(-n, n + 1) * 0.5
    w = np.exp(-.5 * (t / sigma) ** 2)
    w /= w.sum()
    ext = np.r_[zu[0] + np.arange(-n, 0) * (zu[1] - zu[0]), zu, zu[-1] + np.arange(1, n + 1) * (zu[-1] - zu[-2])]
    return np.interp(s, u, np.convolve(ext, w, 'valid'))


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def main():
    e = json.loads((EXT / 'osm_extension.json').read_text())
    old9 = np.load(ROOT / 'data/processed/road_v009/centerline.npz')['new_designed_xyz_m']
    raw_old = np.load(C9.ROUTE)['local_xyz_m'][:, :2].astype(float)
    E = np.array(e['polyline_local_m'])
    assert np.linalg.norm(E[0] - raw_old[-1]) < 0.02, 'extension does not start at the old raw end'
    dense = []
    for a, b in zip(E[:-1], E[1:]):
        k = max(1, int(np.ceil(np.linalg.norm(b - a) / STEP_M)))
        dense += [a + (b - a) * j / k for j in range(1, k + 1)]
    raw = np.vstack([raw_old, np.array(dense)])
    fit, nodes = C9.fit(raw)
    s_raw = np.r_[0, np.cumsum(np.linalg.norm(np.diff(raw, axis=0), axis=1))]
    N_old = len(old9)
    s_old9 = np.r_[0, np.cumsum(np.linalg.norm(np.diff(old9[:, :2], axis=0), axis=1))]
    i_cut = int(np.searchsorted(s_old9, s_old9[-1] - CUT_BACK_M))
    # positions: exact v009 up to i_cut+1, then blend into the fit
    P = np.zeros((len(raw), 3))
    P[:N_old, :2] = old9[:, :2]
    w = smoothstep((s_raw - s_raw[i_cut + 1]) / BLEND_M)
    w[:i_cut + 2] = 0.0
    base = np.vstack([old9[:, :2], fit[N_old:]])
    P[:, :2] = (1 - w)[:, None] * base + w[:, None] * fit
    # heights: DTM along the raw line, sigma 4 m, blended into the old design profile
    summ3035 = json.loads((EXT / 'surface_summary.json').read_text())
    dtm = tifffile.imread(EXT / 'dtm_3035.tif')
    origin = np.array(e['origin_25833'])
    X, Y = Transformer.from_crs(25833, 3035, always_xy=True).transform(raw[:, 0] + origin[0], raw[:, 1] + origin[1])
    lo = max(0, i_cut - 200)
    zr = bilinear(dtm, np.column_stack([X[lo:], Y[lo:]]), summ3035['transform'])
    assert np.isfinite(zr).all() and (zr > 0).all(), 'DTM gap along the extension'
    zr = zr - 300.0  # local Z = H - 300 (ORIGIN z)
    zs = gaussian_profile(s_raw[lo:] - s_raw[lo], zr, Z_SIGMA)
    z_new = np.empty(len(raw))
    z_new[:lo] = np.nan
    z_new[lo:] = zs
    z_old = np.r_[old9[:, 2], np.full(len(raw) - N_old, np.nan)]
    wz = smoothstep((s_raw - s_raw[i_cut + 1]) / BLEND_M)
    wz[:i_cut + 2] = 0.0
    P[:, 2] = np.where(wz > 0, (1 - wz) * np.nan_to_num(z_old) + wz * z_new, z_old)
    assert np.isfinite(P).all()
    assert np.array_equal(P[:i_cut + 2], old9[:i_cut + 2]), 'old stations must be untouched'
    # checks: no fold of the +-6 m wall offsets on the new part, grades
    N = station_normals(P)
    folds = {}
    for o in (-6.0, 6.0):
        ed = P[:, :2] + o * N
        bad = np.flatnonzero((np.diff(ed, axis=0) * np.diff(P[:, :2], axis=0)).sum(1) <= 0)
        folds[o] = bad[bad >= i_cut].tolist()
    assert not folds[-6.0] and not folds[6.0], ('wall-offset fold on the extension', folds)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    grade = np.diff(P[:, 2]) / np.diff(s)
    g = np.diff(P[:, :2], axis=0)
    k = np.diff(np.unwrap(np.arctan2(g[:, 1], g[:, 0]))) / ((np.diff(s)[1:] + np.diff(s)[:-1]) / 2)
    fin = np.array(e['finish_local_m'])
    i_fin = int(np.argmin(np.linalg.norm(P[:, :2] - fin, axis=1)))
    ring_c = np.array(e['ring_center_local_m'])
    near_ring = np.flatnonzero(np.linalg.norm(P[:, :2] - ring_c, axis=1) < 14)
    zdiff_join = float(np.abs(z_new[i_cut + 2:N_old] - old9[i_cut + 2:, 2]).max())
    out = dict(stations=int(len(P)), old_stations=int(N_old), i_cut=i_cut, s_cut_m=float(s[i_cut]), length_m=float(s[-1]),
               old_length_m=float(s_old9[-1]), finish_station=i_fin, finish_arclength_m=float(s[i_fin]),
               finish_offset_from_osm_m=float(np.linalg.norm(P[i_fin, :2] - fin)),
               ring_stations=[int(near_ring.min()), int(near_ring.max())],
               ring_centreline_radius_m=[float(np.linalg.norm(P[near_ring, :2] - ring_c, axis=1).min()),
                                         float(np.linalg.norm(P[near_ring, :2] - ring_c, axis=1).max())],
               min_radius_extension_m=float(1 / np.abs(k[i_cut:]).max()),
               max_grade_extension=float(np.abs(grade[i_cut:]).max()),
               max_shift_vs_fit_old_part_m=float(np.linalg.norm(P[i_cut:N_old, :2] - old9[i_cut:, :2], axis=1).max()),
               max_old_vs_new_dtm_profile_m=zdiff_join, osm_nodes=int(len(nodes)), cut_back_m=CUT_BACK_M, blend_m=BLEND_M)
    np.savez_compressed(EXT / 'route.npz', designed_xyz_m=P, raw_xy_m=raw, i_cut=i_cut, finish_station=i_fin)
    (EXT / 'route.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
