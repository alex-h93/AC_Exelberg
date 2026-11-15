#!/usr/bin/env python3
"""v009 smoothed road centreline + deformed ground skin (offline, .venv; needs scipy).

User (v008 review): "the roads seem to have some rough edges, which are noticable at the turns".
Cause: the OSM way was densified with STRAIGHT 2 m steps between OSM nodes (median node spacing 8 m,
p90 26 m) and v002 only applied a sigma = 2 m Gaussian, so curves were chord polygons: curvature
spikes at every OSM node and zero in between -> kinks along the road edges.
Fix: treat the OSM nodes as points on the true curve and fit a curve through them that minimises the
change of curvature (penalised least squares on a 0.5 m lattice: sum_nodes |x - node|^2 + LAM*|x'''|^2,
end nodes pinned). XY only; per-station Z (profile, grades) is kept exactly. Station count/topology kept.
Outputs data/processed/road_v009/: centerline.npz (old/new designed_xyz_m), smoothed_skin.npz (v008
terrain skin with XY displaced by v009_field and designed_xyz_m replaced), summary.json.
"""
import json
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as sl

from v009_field import Field, station_normals

ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / 'data/processed/full_track_inputs/route.npz'
SKIN8 = ROOT / 'data/processed/terrain_v008/smoothed_skin.npz'
OUT = ROOT / 'data/processed/road_v009'
LAM, H, WEAK, END_M = 100.0, 0.5, 1e-3, 25.0


def osm_nodes(raw):
    g = np.diff(raw, axis=0)
    a = np.unwrap(np.arctan2(g[:, 1], g[:, 0]))
    return np.r_[0, np.flatnonzero(np.abs(np.diff(a)) > 1e-4) + 1, len(raw) - 1]


def fit(raw):
    sr = np.r_[0, np.cumsum(np.linalg.norm(np.diff(raw, axis=0), axis=1))]
    u = np.arange(0, sr[-1] + 1e-9, H)
    u[-1] = sr[-1]
    n = len(u)

    def im(q):
        j = np.clip(np.searchsorted(u, q, side='right') - 1, 0, n - 2)
        t = (q - u[j]) / (u[j + 1] - u[j])
        r = np.arange(len(q))
        return sp.csr_matrix((np.r_[1 - t, t], (np.r_[r, r], np.r_[j, j + 1])), shape=(len(q), n))

    nodes = osm_nodes(raw)
    B, Ball = im(sr[nodes]), im(sr)
    wn = np.ones(len(nodes))
    wn[[0, -1]] = 1e6
    D3 = (sp.diags([-1., 3., -3., 1.], [0, 1, 2, 3], shape=(n - 3, n)) / H ** 3).tocsc()
    f = sl.splu((B.T @ sp.diags(wn) @ B + WEAK * (Ball.T @ Ball) + LAM * (D3.T @ D3)).tocsc())
    Y = np.column_stack([f.solve(B.T @ (wn * raw[nodes, k]) + WEAK * (Ball.T @ raw[:, k])) for k in (0, 1)])
    return Ball @ Y, nodes


def curvature_tv(P, ds=4.0):
    c = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    q = np.arange(0, c[-1], ds)
    Q = np.column_stack([np.interp(q, c, P[:, k]) for k in (0, 1)])
    g = np.diff(Q, axis=0)
    k = np.diff(np.unwrap(np.arctan2(g[:, 1], g[:, 0]))) / ds
    return float(np.abs(np.diff(k)).sum()), float(1 / np.abs(k).max())


def turn_steps(P):
    g = np.diff(P, axis=0)
    t = np.degrees(np.diff(np.unwrap(np.arctan2(g[:, 1], g[:, 0]))))
    return np.abs(np.diff(t))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = np.load(ROUTE)['local_xyz_m'][:, :2].astype(float)
    src = np.load(SKIN8)
    d = {k: src[k] for k in src.files}
    p = d['designed_xyz_m'].astype(float)
    assert len(p) == len(raw)
    P2, nodes = fit(raw)
    P = p.copy()
    P[:, :2] = P2
    # start/finish areas unchanged: blend back to the v008 line over the first/last END_M metres
    sd = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
    x = np.clip(np.minimum(sd, sd[-1] - sd) / END_M, 0, 1)
    ramp = x * x * (3 - 2 * x)
    P[:, :2] = p[:, :2] + ramp[:, None] * (P2 - p[:, :2])
    # ribbon validity: no folded quads at the +-6 m invisible-wall offset (old line folds from 6.2 m too)
    N = station_normals(P)
    for o in (-6.0, 6.0):
        e = P[:, :2] + o * N
        q0, q1 = np.diff(e, axis=0), np.diff(P[:, :2], axis=0)
        assert ((q0 * q1).sum(1) > 0).all(), f'ribbon fold at offset {o}'
    F = Field(p, P)
    v = d['vertices'].astype(np.float64)
    xy, o = F.displace(v[:, :2], return_info=True)
    tri = d['triangles']

    def area2(xy_):
        a, b, c = xy_[tri[:, 0]], xy_[tri[:, 1]], xy_[tri[:, 2]]
        return (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])

    a0, a1 = area2(v[:, :2]), area2(xy)
    flipped = int(((a0 > 0) != (a1 > 0)).sum())
    ratio = a1 / np.where(a0 == 0, 1, a0)
    vs = v.copy()
    vs[:, :2] = xy
    shift = np.linalg.norm(xy - v[:, :2], axis=1)
    # road vertices: must land exactly on the new ribbon
    road = np.unique(tri[d['roles'] == 'ROAD'])
    dev = np.linalg.norm(P[:, :2] - p[:, :2], axis=1)
    d['vertices'] = vs.astype(d['vertices'].dtype)
    d['designed_xyz_m'] = P
    d['designed_xyz_v008_m'] = p
    d['delta_road_xy_v009_m'] = (xy - v[:, :2]).astype(np.float32)
    np.savez_compressed(OUT / 'smoothed_skin.npz', **d)
    np.savez_compressed(OUT / 'centerline.npz', old_designed_xyz_m=p, new_designed_xyz_m=P, osm_nodes=nodes)
    tv0, r0 = curvature_tv(p[:, :2])
    tv1, r1 = curvature_tv(P[:, :2])
    summ = dict(lam=LAM, end_blend_m=END_M, lattice_m=H, osm_nodes=int(len(nodes)), stations=int(len(P)),
                centerline_shift_m={k: round(float(np.percentile(dev, q)), 3) for k, q in (('p50', 50), ('p90', 90), ('p99', 99), ('max', 100))},
                max_node_deviation_m=round(float(np.linalg.norm(P2[nodes] - raw[nodes], axis=1).max()), 3),
                curvature_total_variation_4m=dict(before=round(tv0, 2), after=round(tv1, 2)),
                min_radius_4m_m=dict(before=round(r0, 1), after=round(r1, 1)),
                turn_step_change_deg=dict(before_p99=round(float(np.percentile(turn_steps(p[:, :2]), 99)), 2),
                                          after_p99=round(float(np.percentile(turn_steps(P[:, :2]), 99)), 2),
                                          before_max=round(float(turn_steps(p[:, :2]).max()), 2),
                                          after_max=round(float(turn_steps(P[:, :2]).max()), 2)),
                skin=dict(vertices=int(len(v)), moved=int((shift > 1e-4).sum()), max_shift_m=round(float(shift.max()), 3),
                          flipped_triangles=flipped, min_area_ratio=round(float(ratio.min()), 3),
                          max_area_ratio=round(float(ratio.max()), 3), z_changed=False,
                          road_vertices=int(len(road)), road_max_shift_m=round(float(shift[road].max()), 3)),
                field=dict(W0_m=__import__('v009_field').W0, W1_m=__import__('v009_field').W1), note=__doc__)
    assert flipped == 0 and ratio.min() > 0.3
    (OUT / 'summary.json').write_text(json.dumps(summ, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summ.items() if k != 'note'}, indent=1))


if __name__ == '__main__':
    main()
