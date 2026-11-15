#!/usr/bin/env python3
"""v010 patch stage 3 (offline, .venv): heights, roles, UVs, walls, markings and the new full ground skin.

Ground (CDT of stage 2, triangles inside the ground domain only):
  target z = BEV DTM 1 m (extension mosaic), Gaussian sigma SIG_DTM m, blended towards the road height near the road
  (w = smoothstep((d - 3.75) / (BLEND_D - 3.75)), d = distance to the new centreline);
  boundary vertices shared with the remaining v009 skin / the ribbon keep their exact heights, T-junction points are
  interpolated on their skin edge, and the mismatch is spread harmonically (Laplace, Neumann at the free outer edge);
  drivable apron (< 6.5 m from the centreline) slope-limited to 30 % as in v003.
Ribbon: road +-3 m, gravel 3-3.75 m, flat cross-section at the station height (as v002/v003).
Walls: v003 wall code (+-6 m, bounds from the final skin, 1.01 m below / 3.01 m above), new 1WALL_END at the new end.
Paint: v002 rules (edge lines +-2.85..2.97 m, 3 m dash / 9 m gap centre line, same phase) up to the roundabout entry;
no paint from PAINT_STOP_M before the ring (OSM: lane_markings=no on the ring and branches).
Outputs data/processed/extension_v010/patch.npz, skin_v010.npz (full skin for scenery), patch.json.
"""
import json
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as sl
import shapely
import tifffile
from pyproj import Transformer
from shapely.geometry import LineString, Polygon

import full_track_v003_geometry as H
from extract_terrain import bilinear
from prototype_geometry import ribbon
from v009_field import station_normals

ROOT = Path(__file__).resolve().parents[1]
EXT = Path(__import__('os').environ.get('V010_EXT', ROOT / 'data/processed/extension_v010'))  # v011: reverse-track variant
SKIN9 = ROOT / 'data/processed/road_v009/smoothed_skin.npz'
SIG_DTM, BLEND_D, PAINT_STOP_M = 3.0, 12.0, 8.0


def gauss2d(a, sigma):
    r = int(3 * sigma)
    t = np.arange(-r, r + 1)
    k = np.exp(-.5 * (t / sigma) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(lambda x: np.convolve(np.pad(x, r, mode='edge'), k, 'valid'), 0, a)
    return np.apply_along_axis(lambda x: np.convolve(np.pad(x, r, mode='edge'), k, 'valid'), 1, a)


def area2(xy, f):
    a, b, c = xy[f[:, 0]], xy[f[:, 1]], xy[f[:, 2]]
    return (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])


def main():
    r = np.load(EXT / 'route.npz')
    P = r['designed_xyz_m']
    ic = int(r['i_cut'])
    N = station_normals(P)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    ext = json.loads((EXT / 'osm_extension.json').read_text())
    rj = json.loads((EXT / 'route.json').read_text())
    dm = np.load(EXT / 'patch_domain.npz')
    cd = np.load(EXT / 'patch_cdt.npz')
    sk = np.load(SKIN9)
    sv_all = sk['vertices'].astype(np.float64)
    keep = dm['keep']
    xy = cd['xy']
    F = cd['faces']
    n_in = int(cd['n_input'])
    rv = dm['ribbon_v']
    rib = Polygon(rv[dm['ribbon_outline'], :2])
    B = Polygon(dm['B_xy'])
    rem = shapely.union_all(shapely.polygons(sv_all[sk['triangles'][dm['removed']]][:, :, :2]))
    kept_poly = shapely.union_all(shapely.polygons(sv_all[sk['triangles'][dm['kept_near']]][:, :, :2]))
    dom = shapely.union_all([B, rem]).difference(rib)
    cen = xy[F].mean(1)
    inside = (shapely.contains_xy(B, cen[:, 0], cen[:, 1]) | shapely.contains_xy(rem, cen[:, 0], cen[:, 1])) & \
        ~shapely.contains_xy(rib, cen[:, 0], cen[:, 1]) & ~shapely.contains_xy(kept_poly, cen[:, 0], cen[:, 1])
    F = F[inside]
    neg = area2(xy, F) < 0
    F[neg] = F[neg][:, ::-1]
    a2 = area2(xy, F)
    n_degenerate = int((a2 <= 1e-6).sum())  # CDT faces on collinear world-edge points (zero area)
    F, a2 = F[a2 > 1e-6], a2[a2 > 1e-6]
    assert n_degenerate <= 5, n_degenerate
    assert abs(a2.sum() / 2 - dom.area) < 1e-3 * dom.area, ('ground triangulation does not cover the domain', a2.sum() / 2, dom.area)
    used, F = np.unique(F, return_inverse=True)
    F = F.reshape(-1, 3)
    kind = np.r_[dm['src_kind'], np.full(len(xy) - n_in, 4)][used]
    sid = np.r_[dm['src_id'], np.full(len(xy) - n_in, -1)][used]
    xy = xy[used]
    # --- heights: fixed = skin vertices still used by kept triangles, ribbon outline vertices, CDT points on kept edges
    zfix = np.full(len(xy), np.nan)
    kept_used = np.zeros(len(sv_all), bool)
    kept_used[sk['triangles'][keep].ravel()] = True
    m0 = (kind == 0) & kept_used[np.where(kind == 0, sid, 0)]
    zfix[m0] = sv_all[sid[m0], 2]
    m1 = kind == 1
    zfix[m1] = rv[sid[m1], 2]
    kt = sk['triangles'][dm['kept_near']]
    kedges = np.unique(np.sort(np.concatenate([kt[:, [0, 1]], kt[:, [1, 2]], kt[:, [2, 0]]]), 1), axis=0)
    segs = shapely.linestrings(sv_all[kedges][:, :, :2])
    tj = 0
    for i in np.flatnonzero(kind == 4):
        dd = shapely.distance(segs, shapely.Point(xy[i]))
        k = int(dd.argmin())
        if dd[k] < 1e-4:
            a_, b_ = sv_all[kedges[k]]
            tt = np.dot(xy[i] - a_[:2], b_[:2] - a_[:2]) / np.dot(b_[:2] - a_[:2], b_[:2] - a_[:2])
            zfix[i] = a_[2] + tt * (b_[2] - a_[2])
            tj += 1
    summ = json.loads((EXT / 'surface_summary.json').read_text())
    x0, y0, sx, sy = summ['transform']
    dtm = tifffile.imread(EXT / 'dtm_3035.tif').astype(np.float64)
    assert (dtm > -9000).all(), 'DTM mosaic has nodata'
    dtm_s = gauss2d(dtm, SIG_DTM)
    origin = np.array(ext['origin_25833'])
    X, Y = Transformer.from_crs(25833, 3035, always_xy=True).transform(xy[:, 0] + origin[0], xy[:, 1] + origin[1])
    zg = bilinear(dtm_s.astype(np.float32), np.column_stack([X, Y]), summ['transform']) - 300.0
    assert np.isfinite(zg).all()
    line = LineString(P[ic - 40:, :2])
    d = shapely.distance(shapely.points(xy), line)
    sp_ = shapely.line_locate_point(LineString(P[:, :2]), shapely.points(xy))
    zr = np.interp(sp_, s, P[:, 2])
    u = np.clip((d - 3.75) / (BLEND_D - 3.75), 0, 1)
    w = u * u * (3 - 2 * u)
    zt = (1 - w) * zr + w * zg
    fixed = np.isfinite(zfix)
    # harmonic correction of the boundary mismatch
    e = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1), axis=0)
    n = len(xy)
    Wm = sp.coo_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    L = sp.diags(np.asarray(Wm.sum(1)).ravel()) - Wm
    c = np.zeros(n)
    c[fixed] = zfix[fixed] - zt[fixed]
    free = ~fixed
    rhs = -L[free][:, fixed] @ c[fixed]
    c[free] = sl.spsolve(L[free][:, free].tocsc(), rhs)
    z = zt + c
    z[fixed] = zfix[fixed]
    v = np.column_stack([xy, z])
    apron = np.flatnonzero((d[F] < 6.5).all(1))
    v2 = H.limit_slopes(v.astype(np.float32), F[apron], np.flatnonzero(fixed | (d > 6.5)), limit=0.30)
    v[:, 2] = np.where(fixed, z, v2[:, 2].astype(float))
    # --- ribbon
    rf, rrole = dm['ribbon_f'], dm['ribbon_role']
    # --- combined new skin (remaining v009 + ribbon + ground), vertices merged by exact XY
    ft, rt = sk['triangles'][keep], sk['roles'][keep]
    u_sv, ft = np.unique(ft, return_inverse=True)  # drop unreferenced skin vertices (v003 has 83, some duplicate XY)
    ft = ft.reshape(-1, 3)
    sv = sv_all[u_sv]
    allv = np.vstack([sv, rv, v])
    allf = np.vstack([ft, rf + len(sv), F + len(sv) + len(rv)])
    allr = np.r_[rt, rrole, np.full(len(F), 'GRASS')]
    key = np.round(allv[:, :2], 4)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    zc = allv[first[inv], 2]
    shared = np.abs(allv[:, 2] - zc) > 1e-3
    assert not shared.any(), f'{shared.sum()} merged vertices disagree in height'
    allf = first[inv][allf]
    used, local = np.unique(allf, return_inverse=True)
    nv, nf = allv[used], local.reshape(-1, 3)
    # watertightness of the seam: every interior edge used exactly twice
    ee = np.sort(np.concatenate([nf[:, [0, 1]], nf[:, [1, 2]], nf[:, [2, 0]]]), 1)
    _, cnt = np.unique(ee, axis=0, return_counts=True)
    assert cnt.max() <= 2, 'non-manifold edge after merge'
    ue_, cnt_ = np.unique(ee, axis=0, return_counts=True)
    bmid = nv[ue_[cnt_ == 1]][:, :, :2].mean(1)
    inner = shapely.union_all([B, rem]).buffer(-0.5)
    open_inside = int(shapely.contains_xy(inner, bmid[:, 0], bmid[:, 1]).sum())
    if open_inside and __import__('os').environ.get('V010_DEBUG'):
        np.save(EXT / 'debug_open.npy', nv[ue_[cnt_ == 1]][shapely.contains_xy(inner, bmid[:, 0], bmid[:, 1])])
    assert open_inside == 0, f'{open_inside} open edges inside the patch (seam not watertight)'
    a_new = area2(nv[:, :2], nf)
    assert (a_new > 0).all(), f'{(a_new <= 0).sum()} folded/degenerate skin triangles'
    # --- walls (v003 code) on the final skin
    ground = H.GroundIndex(nv.astype(np.float32), nf)
    walls = {}
    for side, label in ((-1, 'R'), (1, 'L')):
        wxy = P[ic:, :2] + side * 6 * N[ic:]
        bounds = np.array([ground.bounds(a, b) for a, b in zip(wxy[:-1], wxy[1:])])
        bounds[:, 0] = np.minimum(bounds[:, 0], np.minimum(P[ic:-1, 2], P[ic + 1:, 2]))
        bounds[:, 1] = np.maximum(bounds[:, 1], np.maximum(P[ic:-1, 2], P[ic + 1:, 2]))
        lo = np.empty(len(wxy))
        hi = lo.copy()
        for i in range(len(wxy)):
            adj = bounds[max(i - 1, 0):min(i + 1, len(bounds))]
            lo[i], hi[i] = adj[:, 0].min() - 1.01, adj[:, 1].max() + 3.01
        walls[label] = H.wall_strip(wxy, lo, hi, side)
    i = len(P) - 1
    exy = np.array([P[i, :2] - 6 * N[i], P[i, :2] + 6 * N[i]])
    lo, hi = ground.bounds(*exy)
    lo, hi = min(lo, P[i, 2]) - 1.01, max(hi, P[i, 2]) + 3.01
    walls['END'] = H.wall_strip(exy, [lo, lo], [hi, hi], -1)
    # --- paint (v002 rules), from the cut to PAINT_STOP_M before the ring
    s_stop = s[rj['ring_stations'][0]] - PAINT_STOP_M
    j1 = int(np.searchsorted(s, s_stop))
    pv, pf = [], []

    def paint(points, normals, offsets):
        vv = np.repeat(points[:, None, :], len(offsets), axis=1)
        vv[:, :, :2] += normals[:, None, :] * np.asarray(offsets)[None, :, None]
        _, ff = ribbon(points, offsets)
        vv = vv.reshape(-1, 3)
        vv[:, 2] += .012
        pf.extend((ff + len(pv)).tolist())
        pv.extend(vv.tolist())
    seg = slice(ic, j1 + 1)
    paint(P[seg], N[seg], [-2.97, -2.85])
    paint(P[seg], N[seg], [2.85, 2.97])
    for start in np.arange(np.ceil(s[ic] / 12) * 12, s[j1] - 3, 12):
        end = start + 3
        ss = np.r_[start, s[(s > start) & (s < end)], end]
        pp = np.column_stack([np.interp(ss, s, P[:, k]) for k in range(3)])
        nn = np.column_stack([np.interp(ss, s, N[:, k]) for k in range(2)])
        nn /= np.linalg.norm(nn, axis=1)[:, None]
        paint(pp, nn, [-.06, .06])
    pv, pf = np.array(pv), np.array(pf)
    # --- outputs
    vn = np.zeros_like(nv)
    fnrm = np.cross(nv[nf[:, 1]] - nv[nf[:, 0]], nv[nf[:, 2]] - nv[nf[:, 0]])
    for k in range(3):
        np.add.at(vn, nf[:, k], fnrm)
    vn /= np.linalg.norm(vn, axis=1)[:, None]
    ob = json.loads((EXT / 'ortho.json').read_text())
    west, south, east, north = ob['local_bounds']
    assert (v[:, 0] >= west).all() and (v[:, 0] <= east).all() and (v[:, 1] >= south).all() and (v[:, 1] <= north).all(), 'patch outside ortho'
    guv = (v[:, :2] - [west, south]) / [east - west, north - south]
    gvn = vn[np.searchsorted(used, first[inv][len(sv) + len(rv):])]
    np.savez_compressed(EXT / 'patch.npz', ground_v=v, ground_f=F, ground_uv=guv, ground_n=gvn,
                        ribbon_v=rv, ribbon_f=rf, ribbon_role=rrole, ribbon_n=vn[np.searchsorted(used, first[inv][len(sv):len(sv) + len(rv)])],
                        wall_L_v=walls['L'][0], wall_L_f=walls['L'][1], wall_R_v=walls['R'][0], wall_R_f=walls['R'][1],
                        wall_END_v=walls['END'][0], wall_END_f=walls['END'][1], paint_v=pv, paint_f=pf,
                        removed_centroids=sv_all[sk['triangles'][dm['removed']]].mean(1), B_xy=dm['B_xy'], designed_xyz_m=P)
    d9 = {k: sk[k] for k in sk.files}
    out = dict(vertices=nv.astype(np.float32), triangles=nf.astype(np.int64), roles=allr, designed_xyz_m=P,
               vertex_normals=vn.astype(np.float32), designed_xyz_v009_m=d9['designed_xyz_m'])
    np.savez_compressed(EXT / 'skin_v010.npz', **out)
    slopes = np.linalg.norm(np.stack([(np.cross(v[F[apron, 1]] - v[F[apron, 0]], v[F[apron, 2]] - v[F[apron, 0]]))[:, k] for k in (0, 1)], 1), axis=1) / \
        np.abs(np.cross(v[F[apron, 1]] - v[F[apron, 0]], v[F[apron, 2]] - v[F[apron, 0]])[:, 2])
    info = dict(ground_vertices=int(len(v)), ground_triangles=int(len(F)), fixed_boundary_vertices=int(fixed.sum()), tjunction_points=tj, open_edges_inside_patch=open_inside, dropped_zero_area_faces=n_degenerate,
                max_boundary_correction_m=float(np.abs(c[fixed]).max()), max_dtm_vs_target_m=float(np.abs(z - zg).max()),
                apron_triangles=int(len(apron)), apron_max_slope=float(slopes.max()),
                skin=dict(vertices=int(len(nv)), triangles=int(len(nf)), roles={k: int((allr == k).sum()) for k in ('ROAD', 'GRAVEL', 'GRASS')},
                          boundary_edges=int((cnt == 1).sum())),
                walls={k: int(len(w_[1])) for k, w_ in walls.items()}, paint_triangles=int(len(pf)),
                paint_stop_arclength_m=float(s_stop), sigma_dtm_m=SIG_DTM, blend_d_m=BLEND_D, note=__doc__)
    (EXT / 'patch.json').write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps({k: v_ for k, v_ in info.items() if k != 'note'}, indent=1))


if __name__ == '__main__':
    main()
