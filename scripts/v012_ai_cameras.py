#!/usr/bin/env python3
"""v012: AI line (ai/fast_lane.ai) and TV/replay camera sets (data/cameras*.ini) for the forward and reverse tracks.

Usage: v012_ai_cameras.py forward|reverse          (offline, .venv; no Blender, no game)

AI line
  Binary layout matches Kunos files on disk byte-for-byte (verified by re-parsing magione / trento-bondone /
  ks_drag fast_lane.ai to their exact sizes):
    int32 version=7, int32 n, int32 lapTime=0, int32 sampleCount=0
    n x (float32 x, y, z, float32 cumulative length, int32 index)          KN5 frame (x, up, z = -y_local)
    int32 n, n x 18 float32: speed m/s, gas, brake, obsoleteLatG, radius, sideLeft, sideRight, camber,
                             direction (-sign of xz heading change), normal xyz, distance to next, forward xyz, tag, grade
    int32 hasGrid=1, float32 max(x, 0, z) + 350, min(x, 0, z) - 350, int32 10, float32 cell 10 m,
    int32 nx = floor(dx / 10), then nx x (int32 nz, nz x (int32 10, 10 x int32 = 10 nearest points to the cell centre))
  Points every 1.5 m (3-D arclength) along the designed road centreline in DRIVING order (reverse track: reversed),
  AI_LIFT 0.35 m above the asphalt like Kunos lines (measured 0.30 m magione, 0.38 m trento-bondone).
  Speed profile: lateral 8 m/s^2, accel 3.5 m/s^2, braking 7 m/s^2, cap 45 m/s; sides = asphalt edges (3 m).
  It drives the centreline (single closed road), not a racing line.

Cameras (IN_POINT / OUT_POINT = normalised AI-line position; contiguous coverage 0 -> 1)
  Line of sight on a 2 m raster of the final ground skin + the actual placed trees (crown cylinder from ~40 % of
  the height, conifers ~20 %) + OSM buildings (heights from the scenery build). Cameras are never inside a crown or
  building and stay >= their lateral offset from every part of the road (hairpins).
  Trunks/undergrowth are not modelled individually, so a ray may cross at most FOREST_PASS (12 m) of tree-covered
  ground below the canopy top. Greedy cover in driving order:
  from the current position pick the candidate with the longest continuously visible stretch (capped per set),
  preferring cameras ahead of the car (approach shots).
  TV 1 'Broadcast'  8-18 m off the road, 2.5-4.5 m high, stretches up to 320 m, zoom 5-50 deg
  TV 2 'Trackside'  6.5-8 m off the road, 1.0-1.6 m high (low, close), up to 160 m
  TV 3 'High'       12-40 m off the road, 20-35 m high (crane/heli feel), up to 450 m
Output: data/processed/ai_cameras_v012_<mode>/{fast_lane.ai, cameras.ini, cameras_1.ini, cameras_2.ini, report.json}
"""
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
P_ = ROOT / 'data/processed'
MODES = {'forward': 'extension_v010', 'reverse': 'extension_v011r'}
SCENERY = {'forward': 'scenery_v011', 'reverse': 'scenery_v011r'}
STEP, HALF_W = 1.5, 3.0
AI_LIFT = 0.35   # m above the asphalt: Kunos lines sit 0.30 (magione) / 0.38 (trento) above the road (recorded at
                 # car height); a line ON the surface is hidden by the asphalt (v012 test: ideal line 'off most of the time')
A_LAT, A_ACC, A_BRK, V_CAP = 8.0, 3.5, 7.0, 45.0
CELL, GRID_MARGIN, GRID_K = 10.0, 350.0, 10
RES, CORRIDOR = 2.0, 130.0      # LOS raster resolution and half-width around the road
TGT_STEP, CAR_H = 5.0, 1.0      # target spacing along the road, car height above the road
FOREST_PASS = 12.0              # max metres of tree-covered ground a ray may cross below the canopy (trunks, undergrowth)
SETS = [
    dict(file='cameras.ini', name='TV 1', lat=(8, 12, 18), hgt=(2.5, 4.5), dmax=260, lmax=320, every=15, near=0.5, fov=(5, 50)),
    dict(file='cameras_1.ini', name='TV 2', lat=(6.5, 8.0), hgt=(1.0, 1.6), dmax=140, lmax=160, every=10, near=0.3, fov=(8, 60)),
    dict(file='cameras_2.ini', name='TV 3', lat=(12, 25, 40), hgt=(20, 35), dmax=350, lmax=450, every=20, near=1.0, fov=(5, 45)),
]


def kn5(p):
    """local (x, y, z) -> KN5 (x, up, -y)."""
    p = np.asarray(p, float)
    return np.stack([p[..., 0], p[..., 2], -p[..., 1]], -1)


# ------------------------------------------------------------------ AI line
def resample(P):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    n = int(s[-1] // STEP) + 1
    g = np.linspace(0, s[-1], n)
    return np.stack([np.interp(g, s, P[:, j]) for j in range(3)], -1)


def speed_profile(k, ds):
    v = np.minimum(np.sqrt(A_LAT / np.maximum(np.abs(k), 1e-6)), V_CAP)
    v[0] = 0.0
    for i in range(1, len(v)):            # acceleration limit (standing start)
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2 * A_ACC * ds[i - 1]))
    for i in range(len(v) - 2, -1, -1):   # braking limit
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * A_BRK * ds[i]))
    return v


def write_ai(path, Q):
    """Q: (n,3) KN5 points in driving order."""
    n = len(Q)
    d = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(d)]
    f = np.gradient(Q, axis=0)
    f /= np.linalg.norm(f, axis=1)[:, None]
    hd = np.unwrap(np.arctan2(f[:, 2], f[:, 0]))
    w = 9
    kraw = np.gradient(hd, cum)
    k = np.convolve(np.pad(kraw, w, mode='edge'), np.ones(2 * w + 1) / (2 * w + 1), 'same')[w:-w]
    v = speed_profile(k, d)
    dv = np.r_[np.diff(v), 0]
    gas = np.where(dv >= -1e-3, 1.0, 0.0)
    need = np.r_[np.maximum(-(v[1:] ** 2 - v[:-1] ** 2) / (2 * np.maximum(d, 1e-6)), 0), 0]
    brake = np.clip(need / A_BRK, 0, 1)
    up = np.array([0.0, 1.0, 0.0])
    nrm = up[None] - (f @ up)[:, None] * f
    nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    E = np.zeros((n, 18), np.float32)
    E[:, 0], E[:, 1], E[:, 2] = v, gas, brake
    E[:, 3] = v ** 2 * np.abs(k) / 9.81
    E[:, 4] = np.minimum(1 / np.maximum(np.abs(k), 1e-6), 999999.0)
    E[:, 5] = E[:, 6] = HALF_W
    E[:, 8] = -np.sign(k)
    E[:, 9:12] = nrm
    E[:, 12] = np.r_[d, 0]
    E[:, 13:16] = f
    E[:, 17] = f[:, 1]
    out = bytearray(struct.pack('<4i', 7, n, 0, 0))
    pts = np.zeros(n, np.dtype([('p', '<f4', 3), ('len', '<f4'), ('id', '<i4')]))
    pts['p'], pts['len'], pts['id'] = Q, cum, np.arange(n)
    out += pts.tobytes() + struct.pack('<i', n) + E.astype('<f4').tobytes()
    lo = Q.min(0) - GRID_MARGIN
    hi = Q.max(0) + GRID_MARGIN
    nx, nz = int((hi[0] - lo[0]) // CELL), int((hi[2] - lo[2]) // CELL)
    out += struct.pack('<i6fifi', 1, hi[0], 0, hi[2], lo[0], 0, lo[2], GRID_K, CELL, nx)
    T = cKDTree(Q[:, [0, 2]])
    cx = lo[0] + (np.arange(nx) + 0.5) * CELL
    cz = lo[2] + (np.arange(nz) + 0.5) * CELL
    for i in range(nx):
        _, nn = T.query(np.c_[np.full(nz, cx[i]), cz], GRID_K)
        col = np.empty((nz, GRID_K + 1), '<i4')
        col[:, 0] = GRID_K
        col[:, 1:] = nn
        out += struct.pack('<i', nz) + col.tobytes()
    path.write_bytes(bytes(out))
    return dict(points=n, length_m=float(cum[-1]), bytes=len(out), grid=[nx, nz], v_max=float(v.max()),
                v_median=float(np.median(v)), min_radius_m=float(E[:, 4].min())), cum


def read_ai(path):
    b = path.read_bytes()
    ver, n, _, _ = struct.unpack_from('<4i', b)
    A = np.frombuffer(b, '<f4', count=5 * n, offset=16).reshape(n, 5)
    o = 16 + 20 * n
    assert struct.unpack_from('<i', b, o)[0] == n
    o += 4 + 72 * n
    has, *_, kk, cs, nx = struct.unpack_from('<i6fifi', b, o)
    o += 40
    for _ in range(nx):
        nz = struct.unpack_from('<i', b, o)[0]
        o += 4 + nz * 4 * (GRID_K + 1)
    assert ver == 7 and has == 1 and o == len(b), 'fast_lane.ai does not re-parse to its exact size'
    return A


# ------------------------------------------------------------------ line of sight
class World:
    def __init__(self, ext, scenery, P):
        sk = np.load(ext / 'skin_v010.npz')
        V = sk['vertices'].astype(float)
        T = cKDTree(P[::4, :2])
        dv, _ = T.query(V[:, :2], distance_upper_bound=CORRIDOR + 60)
        Vn = V[np.isfinite(dv)]
        self.lo = P[:, :2].min(0) - CORRIDOR - 10
        hi = P[:, :2].max(0) + CORRIDOR + 10
        self.shape = tuple(((hi - self.lo) // RES).astype(int) + 1)   # (nx, ny)
        gx = self.lo[0] + np.arange(self.shape[0]) * RES
        gy = self.lo[1] + np.arange(self.shape[1]) * RES
        X, Y = np.meshgrid(gx, gy, indexing='ij')
        dc, _ = T.query(np.c_[X.ravel(), Y.ravel()], distance_upper_bound=CORRIDOR)
        mask = np.isfinite(dc)
        self.ground = np.full(X.size, np.nan, np.float32)
        self.ground[mask] = LinearNDInterpolator(Vn[:, :2], Vn[:, 2])(np.c_[X.ravel()[mask], Y.ravel()[mask]])
        self.ground = self.ground.reshape(self.shape)
        self.base = np.full(self.shape, np.inf, np.float32)
        self.top = np.full(self.shape, -np.inf, np.float32)
        tr = np.load(ext / 'trees_v010.npz')
        dt, _ = T.query(tr['xyz'][:, :2], distance_upper_bound=CORRIDOR + 10)
        keep = np.where(np.isfinite(dt))[0]
        for i in keep:
            x, y, z = tr['xyz'][i]
            h, r = float(tr['height'][i]), float(tr['crown'][i]) * 0.85
            frac = 0.2 if tr['species'][i] == 2 else 0.4
            self._block(x, y, r, z + frac * h, z + h)
        self.n_trees = int(len(keep))
        self.n_buildings = self._buildings(scenery, T)

    def _cells(self, x, y, r):
        i0, i1 = int((x - r - self.lo[0]) // RES), int((x + r - self.lo[0]) // RES) + 1
        j0, j1 = int((y - r - self.lo[1]) // RES), int((y + r - self.lo[1]) // RES) + 1
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, self.shape[0] - 1), min(j1, self.shape[1] - 1)
        if i1 < i0 or j1 < j0:
            return None
        I, J = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing='ij')
        return I, J

    def _block(self, x, y, r, z0, z1):
        c = self._cells(x, y, r)
        if c is None:
            return
        I, J = c
        m = (self.lo[0] + I * RES - x) ** 2 + (self.lo[1] + J * RES - y) ** 2 <= r * r
        I, J = I[m], J[m]
        self.base[I, J] = np.minimum(self.base[I, J], z0)
        self.top[I, J] = np.maximum(self.top[I, J], z1)

    def _buildings(self, scenery, T):
        pl = json.loads((P_ / scenery / 'placements.json').read_text())
        hgt = {str(p['way']): float(p.get('ridge_m', 6.0)) for p in pl if p['kind'] == 'building'}
        el = json.loads((ROOT / 'data/interim/osm/merged.json').read_text())['elements']
        nodes = {x['id']: (x['lon'], x['lat']) for x in el if x['type'] == 'node'}
        from pyproj import Transformer
        tf = Transformer.from_crs(4326, 25833, always_xy=True)
        org = np.array(json.loads((ROOT / 'data/processed/extension_v010/osm_extension.json').read_text())['origin_25833'])[:2]
        n = 0
        for w in el:
            if w['type'] != 'way' or str(w['id']) not in hgt or not all(i in nodes for i in w['nodes']):
                continue
            ll = np.array([nodes[i] for i in w['nodes']])
            xy = np.c_[tf.transform(ll[:, 0], ll[:, 1])] - org
            c = xy.mean(0)
            r = float(np.linalg.norm(xy - c, axis=1).max())
            cells = self._cells(c[0], c[1], r)
            if cells is None:
                continue
            I, J = cells
            pts = np.c_[(self.lo[0] + I * RES).ravel(), (self.lo[1] + J * RES).ravel()]
            m = MPath(xy).contains_points(pts, radius=RES * 0.5).reshape(I.shape)
            g = self.ground[I[m], J[m]]
            if not m.any() or np.isnan(g).all():
                continue
            gz = float(np.nanmin(g))
            self.base[I[m], J[m]] = np.minimum(self.base[I[m], J[m]], gz - 1.0)
            self.top[I[m], J[m]] = np.maximum(self.top[I[m], J[m]], gz + hgt[str(w['id'])] + 0.5)
            n += 1
        return n

    def idx(self, xy):
        ij = np.rint((xy - self.lo) / RES).astype(int)
        ok = (ij[..., 0] >= 0) & (ij[..., 1] >= 0) & (ij[..., 0] < self.shape[0]) & (ij[..., 1] < self.shape[1])
        ij = np.where(ok[..., None], ij, 0)
        return ij[..., 0], ij[..., 1], ok

    def blocked_at(self, p):
        """p (...,3): True where the point is under ground, inside foliage/buildings, or off the raster."""
        i, j, ok = self.idx(p[..., :2])
        g = self.ground[i, j]
        z = p[..., 2]
        return ~ok | np.isnan(g) | (z < g + 0.15) | ((z >= self.base[i, j]) & (z <= self.top[i, j]))

    def visible(self, cam, tgt):
        """cam (3,), tgt (m,3) -> (m,) bool line of sight (last 3 m before the car and first 0.5 m are not tested)."""
        d = tgt - cam
        L = np.linalg.norm(d, axis=1)
        ns = int(np.ceil(L.max() / 1.5)) + 1
        t = np.linspace(0, 1, ns)[None, :, None]
        pts = cam + d[:, None, :] * t
        dist = L[:, None] * t[..., 0]
        test = (dist > 0.5) & (dist < L[:, None] - 3.0)
        # trunks/undergrowth are not in the raster: below the canopy top, at most FOREST_PASS m of tree-covered ground
        i, j, _ = self.idx(pts[..., :2])
        under = (pts[..., 2] <= self.top[i, j]) & test
        return ~(self.blocked_at(pts) & test).any(1) & (under.sum(1) * (L / max(ns - 1, 1)) <= FOREST_PASS)


# ------------------------------------------------------------------ camera placement
def frame(P):
    t = np.gradient(P[:, :2], axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    return np.c_[-t[:, 1], t[:, 0]]  # left normal


def place(world, Pd, ud, cfg, route_tree):
    """Pd: driving-order centreline (local) resampled every TGT_STEP; ud: its driving chainage."""
    nL = frame(Pd)
    tgt = Pd + np.array([0, 0, CAR_H])
    L = ud[-1]
    cands = []
    for i in range(0, len(Pd), max(1, int(cfg['every'] / TGT_STEP))):
        for side in (1, -1):
            for lat in cfg['lat']:
                xy = Pd[i, :2] + side * lat * nL[i]
                dmin, _ = route_tree.query(xy)
                if dmin < lat - 0.6:
                    continue
                gi, gj, ok = world.idx(xy)
                if not ok or np.isnan(world.ground[gi, gj]):
                    continue
                for h in cfg['hgt']:
                    cam = np.array([xy[0], xy[1], world.ground[gi, gj] + h])
                    if world.blocked_at(cam[None])[0]:
                        continue
                    w = np.where(np.abs(ud - ud[i]) <= cfg['dmax'])[0]
                    w = w[np.linalg.norm(tgt[w] - cam, axis=1) <= cfg['dmax']]
                    if len(w) == 0:
                        continue
                    vis = np.zeros(len(Pd), bool)
                    vis[w] = world.visible(cam, tgt[w])
                    if vis.any():
                        cands.append(dict(cam=cam, i=i, side=side, lat=lat, h=h, vis=vis))
    chosen, cur, fallback = [], 0, 0
    nmax = int(cfg['lmax'] / TGT_STEP)
    while cur < len(Pd) - 1:
        best, bscore, brun = None, -1, 0
        for c in cands:
            v = c['vis']
            if not v[cur]:
                continue
            run = 0
            while cur + run + 1 < len(Pd) and run < nmax and (v[cur + run + 1] or (cur + run + 2 < len(Pd) and v[cur + run + 2])):
                run += 1
            ahead = (ud[c['i']] - ud[cur]) / max(run * TGT_STEP, 1.0)
            score = run * (1.0 if 0.25 <= ahead <= 1.1 else 0.75) - 0.02 * c['lat']
            if score > bscore:
                best, bscore, brun = c, score, run
        if best is None or brun == 0:   # nothing sees this stretch: closest roadside camera, short hold
            fallback += 1
            j = min(cur + 4, len(Pd) - 1)
            xy = Pd[j, :2] + 6.5 * nL[j]
            gi, gj, _ = world.idx(xy)
            gz = world.ground[gi, gj]
            cam = np.array([xy[0], xy[1], (Pd[j, 2] if np.isnan(gz) else gz) + 2.0])
            best, brun = dict(cam=cam, i=j, side=1, lat=6.5, h=2.0, vis=None), 4
        end = min(cur + max(brun, 1), len(Pd) - 1)
        seg = tgt[cur:end + 1]
        dist = np.linalg.norm(seg - best['cam'], axis=1)
        aim = seg[len(seg) // 2] - best['cam']
        chosen.append(dict(cam=best['cam'], aim=aim / np.linalg.norm(aim), u0=ud[cur] / L, u1=ud[end] / L,
                           dnear=float(dist.min()), dfar=float(dist.max()), lat=best['lat'], h=best['h']))
        cur = end
    chosen[0]['u0'], chosen[-1]['u1'] = 0.0, 1.0
    for a, b in zip(chosen, chosen[1:]):
        b['u0'] = a['u1']
    return chosen, dict(candidates=len(cands), cameras=len(chosen), fallback_holds=fallback)


def fov(d, lo, hi):
    return float(np.clip(math.degrees(2 * math.atan(9.0 / max(d, 1.0))), lo, hi))


def write_cams(path, cams, cfg):
    lines = ['[HEADER]', 'VERSION=3', f'CAMERA_COUNT={len(cams)}', f'SET_NAME={cfg["name"]}', '']
    f3 = lambda v: ' ,'.join(f'{x:.6g}' for x in v)
    for k, c in enumerate(cams):
        pos, fwd = kn5(c['cam']), kn5(c['aim'])
        right = np.cross(fwd, [0, 1, 0])
        up = np.cross(right, fwd)
        up /= np.linalg.norm(up)
        mn, mx = fov(c['dfar'], *cfg['fov']), fov(c['dnear'], *cfg['fov'])
        lines += [f'[CAMERA_{k}]', f'NAME={k + 1}', f'POSITION={f3(pos)}', f'FORWARD={f3(fwd)}', f'UP={f3(up)}',
                  f'MIN_FOV={mn:.1f}', f'MAX_FOV={max(mx, mn):.1f}', f'IN_POINT={c["u0"]:.6f}', f'OUT_POINT={c["u1"]:.6f}',
                  'SHADOW_SPLIT0=10', 'SHADOW_SPLIT1=40', 'SHADOW_SPLIT2=180', f'NEAR_PLANE={cfg["near"]}', 'FAR_PLANE=35000',
                  'MIN_EXPOSURE=0.35', 'MAX_EXPOSURE=0.55', 'DOF_FACTOR=0', 'DOF_RANGE=10000', 'DOF_FOCUS=0', 'DOF_MANUAL=0',
                  'SPLINE=', 'SPLINE_ROTATION=0', 'FOV_GAMMA=1', 'SPLINE_ANIMATION_LENGTH=15', 'IS_FIXED=0', '']
    path.write_text('\r\n'.join(lines))


def main(mode):
    ext = P_ / MODES[mode]
    out = P_ / f'ai_cameras_v012_{mode}'
    out.mkdir(parents=True, exist_ok=True)
    P = np.load(ext / 'route.npz')['designed_xyz_m'].astype(float)
    Pd = P if mode == 'forward' else P[::-1].copy()          # driving order
    Q = resample(Pd)
    ai, cum = write_ai(out / 'fast_lane.ai', kn5(Q + [0, 0, AI_LIFT]))
    A = read_ai(out / 'fast_lane.ai')
    assert np.allclose(A[:, :3], kn5(Q + [0, 0, AI_LIFT]), atol=1e-3)
    ai['lift_above_road_m'] = AI_LIFT
    # camera targets on a 5 m grid of the same (3-D) driving chainage as the AI line
    u = np.arange(0, cum[-1], TGT_STEP)
    Pt = np.stack([np.interp(u, cum, Q[:, j]) for j in range(3)], -1)
    print(f'{mode}: AI {ai["points"]} pts, {ai["length_m"]:.0f} m, {ai["bytes"] / 1e6:.1f} MB; building LOS raster...', flush=True)
    world = World(ext, SCENERY[mode], P)
    rt = cKDTree(P[:, :2])
    rep = dict(mode=mode, ai=ai, los=dict(raster_m=RES, trees=world.n_trees, buildings=world.n_buildings), sets={})
    for cfg in SETS:
        cams, st = place(world, Pt, u, cfg, rt)
        write_cams(out / cfg['file'], cams, cfg)
        spans = np.array([(c['u1'] - c['u0']) * ai['length_m'] for c in cams])
        st.update(span_m=dict(min=float(spans.min()), median=float(np.median(spans)), max=float(spans.max())),
                  lateral_m=sorted({c['lat'] for c in cams}), contiguous=bool(all(a['u1'] == b['u0'] for a, b in zip(cams, cams[1:]))))
        rep['sets'][cfg['name']] = st
        print(cfg['name'], json.dumps(st), flush=True)
    rep['note'] = __doc__
    (out / 'report.json').write_text(json.dumps(rep, indent=2) + '\n')


if __name__ == '__main__':
    main(sys.argv[1])
