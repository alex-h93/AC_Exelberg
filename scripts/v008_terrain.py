#!/usr/bin/env python3
"""v008 terrain smoothing (offline, .venv). Input: v003 final ground skin (read-only).

User (v007 review): "the terrain has some rough edges and is not smooth ... smooth the landscape a bit,
especially the elevations". Two causes found: the ground is FLAT-shaded (per-triangle normals, up to ~30 deg
jumps between neighbouring 8 m triangles) and the 8 m DTM-derived mesh has short-wavelength bumps.

  1. heights: z-only Taubin smoothing (lambda/mu, no shrinkage) of GRASS vertices, weight
     w = smoothstep((d - D0) / (D1 - D0)) by distance to the designed centreline. d <= D0 = 10 m unchanged
     (road, gravel, drivable grass inside the +-6 m invisible walls, wall bases); full effect beyond D1 = 25 m.
     Vertices used by ROAD/GRAVEL triangles and mesh-boundary vertices are always fixed. Change soft-capped
     with CAP * tanh(dz / CAP) (CAP = 2 m) so real steep landforms (cuts, embankments) are not flattened.
     Distance recomputed from the designed centreline (the skin field uses a 1e6 sentinel for far vertices).
     XY and topology unchanged (same coverage).
  2. smooth vertex normals per skin vertex (area-weighted, all skin triangles) for smooth shading.
Output: data/processed/terrain_v008/smoothed_skin.npz (same keys as repaired_skin.npz, smoothed 'vertices',
plus 'vertex_normals', 'delta_smooth_z_m'), summary.json.
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz'
OUT = ROOT / 'data/processed/terrain_v008'
D0, D1, ITER, LAM, MU, CAP = 10.0, 25.0, 30, 0.5, -0.53, 2.0


def adjacency(f, n):
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e = np.unique(np.sort(e, axis=1), axis=0)
    i = np.r_[e[:, 0], e[:, 1]]
    j = np.r_[e[:, 1], e[:, 0]]
    deg = np.bincount(i, minlength=n).astype(float)
    return i, j, deg


def lap(z, i, j, deg):
    s = np.bincount(i, weights=z[j], minlength=len(z))
    return np.where(deg > 0, s / np.maximum(deg, 1) - z, 0.0)


def vertex_normals(v, f):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    fn = np.cross(b - a, c - a)  # area-weighted
    fn[fn[:, 2] < 0] *= -1
    vn = np.zeros_like(v)
    for k in range(3):
        np.add.at(vn, f[:, k], fn)
    unused = np.linalg.norm(vn, axis=1) < 1e-12  # vertices referenced by no triangle
    vn[unused] = (0.0, 0.0, 1.0)
    vn /= np.linalg.norm(vn, axis=1)[:, None]
    return vn


def route_distance(xy, p):
    """Exact distance to the designed centreline polyline, via 50 m buckets."""
    a, b = p[:-1, :2], p[1:, :2]
    cell = 50.0
    lo = np.floor(np.minimum(a, b) / cell).astype(int) - 1
    hi = np.floor(np.maximum(a, b) / cell).astype(int) + 1
    buckets = {}
    for k in range(len(a)):
        for cx in range(lo[k, 0], hi[k, 0] + 1):
            for cy in range(lo[k, 1], hi[k, 1] + 1):
                buckets.setdefault((cx, cy), []).append(k)
    out = np.full(len(xy), np.inf)
    keys = np.floor(xy / cell).astype(int)
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    ks = keys[order]
    brk = np.r_[0, np.nonzero((np.diff(ks, axis=0) != 0).any(1))[0] + 1, len(ks)]
    for s0, s1 in zip(brk[:-1], brk[1:]):
        segs = buckets.get(tuple(ks[s0]))
        if not segs:
            continue
        segs = np.array(segs)
        q = xy[order[s0:s1]][:, None]
        A, B = a[segs][None], b[segs][None]
        t = np.clip(((q - A) * (B - A)).sum(-1) / ((B - A) ** 2).sum(-1), 0, 1)
        out[order[s0:s1]] = np.linalg.norm(q - (A + t[..., None] * (B - A)), axis=-1).min(1)
    return out  # inf = farther than ~50 m from any segment


def crease(v, f):
    """Angle between normals of edge-adjacent triangles (deg) -> roughness measure."""
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    fn = np.cross(b - a, c - a); fn /= np.linalg.norm(fn, axis=1)[:, None]
    e = np.concatenate([np.sort(f[:, [0, 1]], 1), np.sort(f[:, [1, 2]], 1), np.sort(f[:, [2, 0]], 1)])
    t = np.tile(np.arange(len(f)), 3)
    key = e[:, 0].astype(np.int64) * len(v) + e[:, 1]
    o = np.argsort(key)
    k, t = key[o], t[o]
    same = k[1:] == k[:-1]
    t0, t1 = t[:-1][same], t[1:][same]
    return np.degrees(np.arccos(np.clip((fn[t0] * fn[t1]).sum(1), -1, 1)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    src = np.load(SRC)
    d = {k: src[k] for k in src.files}
    v = d['vertices'].astype(np.float64)
    f = d['triangles']
    roles = d['roles']
    fixed = np.zeros(len(v), bool)
    fixed[np.unique(f[roles != 'GRASS'])] = True
    e = np.concatenate([np.sort(f[:, [0, 1]], 1), np.sort(f[:, [1, 2]], 1), np.sort(f[:, [2, 0]], 1)])
    u, c = np.unique(e, axis=0, return_counts=True)
    boundary = np.unique(u[c == 1])
    fixed[boundary] = True
    dist = route_distance(v[:, :2], d['designed_xyz_m'])
    x = np.clip((dist - D0) / (D1 - D0), 0, 1)
    w = x * x * (3 - 2 * x)
    w[fixed] = 0.0
    i, j, deg = adjacency(f, len(v))
    z0 = v[:, 2].copy()
    z = z0.copy()
    for _ in range(ITER):
        z += LAM * w * lap(z, i, j, deg)
        z += MU * w * lap(z, i, j, deg)
    dz = CAP * np.tanh((z - z0) / CAP)
    z = z0 + dz
    vs = v.copy(); vs[:, 2] = z
    vn = vertex_normals(vs, f)
    far = dist > D1
    d['distance_to_route_v008_m'] = np.where(np.isfinite(dist), dist, 1e6).astype(np.float32)
    c0, c1 = crease(v, f), crease(vs, f)
    d['vertices'] = vs.astype(d['vertices'].dtype)
    d['vertex_normals'] = vn.astype(np.float32)
    d['delta_smooth_z_m'] = dz.astype(np.float32)
    np.savez_compressed(OUT / 'smoothed_skin.npz', **d)
    summ = dict(source=str(SRC.relative_to(ROOT)), D0_m=D0, D1_m=D1, iterations=ITER, lam=LAM, mu=MU,
                vertices=int(len(v)), boundary_vertices_fixed=int(len(boundary)), soft_cap_m=CAP, changed_vertices=int((np.abs(dz) > 1e-4).sum()),
                max_abs_change_within_D0_m=float(np.abs(dz[dist <= D0]).max()),
                fixed_road_gravel_vertices_max_change_m=float(np.abs(dz[fixed]).max()),
                dz_percentiles_m={str(p): round(float(np.percentile(dz[far], p)), 3) for p in (0.1, 1, 50, 99, 99.9)},
                max_abs_dz_m=round(float(np.abs(dz).max()), 3),
                crease_deg_before={str(p): round(float(np.percentile(c0, p)), 2) for p in (50, 90, 99)},
                crease_deg_after={str(p): round(float(np.percentile(c1, p)), 2) for p in (50, 90, 99)},
                note=__doc__)
    (OUT / 'summary.json').write_text(json.dumps(summ, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summ.items() if k != 'note'}, indent=1))


if __name__ == '__main__':
    main()
