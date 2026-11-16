#!/usr/bin/env python3
"""v014 3D verge grass (usage: v014_grass.py forward|reverse; offline, .venv). Visual only, works without CSP.

User: "nicer textures for the gras next to the road, currently is absolute flat and I want something with a bit more
texture" (plain AC, no CSP -> GrassFX in ext_config.ini is inactive). Adds alpha-tested grass clumps (2 crossed,
double-sided quads, up-facing normals for even lighting) on the verge, from the v014_grass_clumps.dds atlas.

Placement (project frame, from the same final ground skin as the main KN5: extension_v010 / extension_v011r skin_v010.npz):
  * random candidates in the band 3.4 .. 9.5 m from the designed centreline, both sides
  * kept only where the skin triangle role is GRASS at the point AND 0.25 m towards the road (no clumps on asphalt/gravel
    edges), not inside scenery junction/parking asphalt or gravel (V011_JUNC) or building footprints (V011_BLDG)
  * density 0.75 /m^2 up to 6.5 m, fading linearly to 0.15 /m^2 at 9.5 m; x0.35 under tree crowns (trees_v010.npz)
  * clump height 0.28 .. 0.62 m (tall seed-head cells 0.45 .. 0.8 m), width 0.8 x height; base 0.04 m below the ground
  * chunks of 50 m x 50 m, lod_out 75 m, no shadows
Output: data/processed/grass_v014{,r}/geometry.npz + objects.json (same layout as the scenery build input).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
MODE = sys.argv[1] if len(sys.argv) > 1 else 'forward'
EXT = ROOT / 'data/processed' / {'forward': 'extension_v010', 'reverse': 'extension_v011r'}[MODE]
SCN = ROOT / 'data/processed' / {'forward': 'scenery_v013', 'reverse': 'scenery_v013r'}[MODE]
OUT = ROOT / 'data/processed' / {'forward': 'grass_v014', 'reverse': 'grass_v014r'}[MODE]
RNG = np.random.default_rng(14140 + (MODE == 'reverse'))
D_MIN, D_FULL, D_MAX = 3.4, 6.5, 9.5
DENS_NEAR, DENS_FAR, TREE_F = 0.75, 0.15, 0.35
CHUNK, LOD_OUT = 50.0, 75.0
BIN = 6.0


class Skin:
    """Point -> (triangle role, z) on the final ground skin (binned exact point-in-triangle, vectorised per bin)."""
    def __init__(self, v, f, roles):
        self.v, self.f, self.roles = v.astype(float), f, roles
        tri = self.v[f][:, :, :2]
        lo, hi = np.floor(tri.min(1) / BIN).astype(int), np.floor(tri.max(1) / BIN).astype(int)
        self.bins = defaultdict(list)
        for j in range(len(f)):
            for x in range(lo[j, 0], hi[j, 0] + 1):
                for y in range(lo[j, 1], hi[j, 1] + 1):
                    self.bins[(x, y)].append(j)
        self.bins = {k: np.array(v) for k, v in self.bins.items()}

    def query(self, P):
        role = np.full(len(P), '', dtype='<U6')
        z = np.full(len(P), np.nan)
        key = np.floor(P / BIN).astype(int)
        order = np.lexsort((key[:, 1], key[:, 0]))
        ks = key[order]
        cut = np.flatnonzero(np.any(np.diff(ks, axis=0) != 0, axis=1)) + 1
        for grp in np.split(order, cut):
            ids = self.bins.get(tuple(key[grp[0]]))
            if ids is None:
                continue
            T = self.v[self.f[ids]]
            a, b = T[:, 1, :2] - T[:, 0, :2], T[:, 2, :2] - T[:, 0, :2]
            det = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
            ok = np.abs(det) > 1e-12
            T, a, b, det, ids = T[ok], a[ok], b[ok], det[ok], ids[ok]
            d = P[grp][:, None, :] - T[None, :, 0, :2]
            u = (d[..., 0] * b[None, :, 1] - d[..., 1] * b[None, :, 0]) / det
            w = (a[None, :, 0] * d[..., 1] - a[None, :, 1] * d[..., 0]) / det
            inside = (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9)
            hit = inside.any(1)
            j = inside.argmax(1)
            r = np.arange(len(grp))
            zz = T[j, 0, 2] + u[r, j] * (T[j, 1, 2] - T[j, 0, 2]) + w[r, j] * (T[j, 2, 2] - T[j, 0, 2])
            role[grp[hit]] = self.roles[ids[j[hit]]]
            z[grp[hit]] = zz[hit]
        return role, z


def scenery_mask():
    """2D union of scenery junction surfaces and building roofs/floors (triangles with non-zero XY area)."""
    meta = json.loads((SCN / 'objects.json').read_text())
    g = np.load(SCN / 'geometry.npz')
    polys = []
    for o in meta['objects']:
        if o['kind'] not in ('JUNC', 'BLDG'):
            continue
        v, t = g[f"{o['name']}__v"], g[f"{o['name']}__tri"]
        T = v[t][:, :, :2]
        e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
        area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
        polys += list(shapely.polygons(T[area > 0.01]))
    m = shapely.union_all(polys).buffer(0.3)
    shapely.prepare(m)
    return m


def main():
    sk = np.load(EXT / 'skin_v010.npz')
    C = sk['designed_xyz_m'][:, :2].astype(float)
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    t = np.gradient(C, axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    nrm = np.c_[-t[:, 1], t[:, 0]]
    print('skin index...', flush=True)
    skin = Skin(sk['vertices'], sk['triangles'], sk['roles'])
    mask = scenery_mask()
    tr = np.load(EXT / 'trees_v010.npz')
    ttree, crown = cKDTree(tr['xyz'][:, :2]), tr['crown']
    # candidates at the peak density, thinned by the density profile
    area = s[-1] * (D_MAX - D_MIN) * 2
    n = int(area * DENS_NEAR)
    sc = RNG.uniform(0, s[-1], n)
    side = RNG.choice([-1.0, 1.0], n)
    d = RNG.uniform(D_MIN, D_MAX, n)
    i = np.clip(np.searchsorted(s, sc) - 1, 0, len(C) - 2)
    a = ((sc - s[i]) / np.maximum(seg[i], 1e-9))[:, None]
    base = C[i] * (1 - a) + C[i + 1] * a
    N = nrm[i] * (1 - a) + nrm[i + 1] * a
    N /= np.linalg.norm(N, axis=1)[:, None]
    P = base + N * (side * d)[:, None]
    dens = np.where(d <= D_FULL, DENS_NEAR, DENS_NEAR + (DENS_FAR - DENS_NEAR) * (d - D_FULL) / (D_MAX - D_FULL))
    near = ttree.query_ball_point(P, r=6.0)
    under = np.array([any(np.linalg.norm(tr['xyz'][k, :2] - p) < crown[k] for k in ks) for p, ks in zip(P, near)])
    dens = dens * np.where(under, TREE_F, 1.0)
    keep = RNG.random(n) < dens / DENS_NEAR
    stats = dict(candidates=n, after_density=int(keep.sum()))
    P, N, side, d, under = P[keep], N[keep], side[keep], d[keep], under[keep]
    role, z = skin.query(P)
    role_in, _ = skin.query(P - N * side[:, None] * 0.25)
    ok = (role == 'GRASS') & (role_in == 'GRASS') & np.isfinite(z)
    stats.update(not_on_grass=int((~ok).sum()))
    ok &= ~shapely.contains_xy(mask, P[:, 0], P[:, 1])
    stats.update(after_scenery_mask=int(ok.sum()))
    P, z, under = P[ok], z[ok], under[ok]
    # clumps
    m = len(P)
    tall = RNG.random(m) < 0.3
    h = np.where(tall, RNG.uniform(0.45, 0.8, m), RNG.uniform(0.28, 0.62, m))
    w = 0.8 * h
    cell = RNG.integers(0, 4, m)
    yaw = RNG.uniform(0, np.pi, m)
    cross = RNG.uniform(np.radians(60), np.radians(90), m)
    chunks = defaultdict(list)
    key = np.floor(P / CHUNK).astype(int)
    for k in range(m):
        chunks[tuple(key[k])].append(k)
    geo, objs = {}, []
    UP = np.array([0.0, 0.0, 1.0])
    for ci, (kk, ids) in enumerate(sorted(chunks.items())):
        ids = np.array(ids)
        V, NN, UV, TRI = [], [], [], []
        for k in ids:
            u0, u1 = cell[k] / 4, (cell[k] + 1) / 4
            v0, v1 = (0.0, 0.5) if tall[k] else (0.5, 1.0)          # Blender UV: row 0 (short) is the TOP half
            b = np.r_[P[k], z[k] - 0.04]
            for ang in (yaw[k], yaw[k] + cross[k]):
                r = np.array([np.cos(ang), np.sin(ang), 0.0]) * w[k] / 2
                o = len(V)
                V += [b - r, b + r, b + r + UP * h[k], b - r + UP * h[k]]
                UV += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
                TRI += [(o, o + 1, o + 2), (o, o + 2, o + 3), (o, o + 2, o + 1), (o, o + 3, o + 2)]  # front + back
        V = np.array(V, np.float32)
        name = f'V014_GRASS_{ci:03d}'
        geo[f'{name}__v'] = V
        geo[f'{name}__n'] = np.tile(UP.astype(np.float32), (len(V), 1))
        geo[f'{name}__uv'] = np.array(UV, np.float32)
        geo[f'{name}__tri'] = np.array(TRI, np.int32)
        geo[f'{name}__mat'] = np.zeros(len(TRI), np.int32)
        assert len(V) < 65536
        objs.append(dict(name=name, kind='GRASS', lod_in=0, lod_out=LOD_OUT, cast_shadows=False, tris=len(TRI), verts=len(V),
                         clumps=len(ids)))
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / 'geometry.npz', **geo)
    stats.update(clumps=m, tall=int(tall.sum()), under_trees=int(under.sum()), objects=len(objs),
                 tris=int(sum(o['tris'] for o in objs)), verts=int(sum(o['verts'] for o in objs)),
                 route_m=float(s[-1]), per_100m=round(m / s[-1] * 100, 1))
    meta = dict(mode=MODE, materials=['V014_grass'], objects=objs, stats=stats, note=__doc__)
    (OUT / 'objects.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps(dict(mode=MODE, **stats)))


if __name__ == '__main__':
    main()
