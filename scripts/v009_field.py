"""v009 road-smoothing displacement field (numpy only: usable from .venv AND Blender's bundled Python).

The v002..v008 road/gravel/walls/markings are ribbons on the designed centreline p with per-station
normals n_i = station_normals(p): every road vertex is p_i + o*n_i and every seam point on a quad edge is
(1-t)(p_i + o n_i) + t(p_{i+1} + o n_{i+1}). For a point x we solve these exact ribbon coordinates
(segment i, t, o) and map it to the same coordinates on the smoothed centreline P (normals N_i):
    full(x) = (1-t)(P_i + o N_i) + t(P_{i+1} + o N_{i+1})
    x' = x + w(|o|) * (full(x) - x),   w = 1 for |o| <= W0, smoothstep -> 0 at |o| = W1.
Only XY moves; Z is never changed. Same xy -> same result, so shared seam vertices stay watertight.
"""
import numpy as np

W0, W1 = 9.0, 30.0
CELL = 64.0


def station_normals(points):  # identical to prototype_geometry.station_normals
    t = np.gradient(points[:, :2], axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    return np.column_stack([-t[:, 1], t[:, 0]])


def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


class Field:
    def __init__(self, old_xy, new_xy):
        self.p = np.asarray(old_xy, float)[:, :2]
        self.P = np.asarray(new_xy, float)[:, :2]
        self.n = station_normals(self.p)
        self.N = station_normals(self.P)
        a, b = self.p[:-1], self.p[1:]
        lo = np.floor((np.minimum(a, b) - W1) / CELL).astype(int)
        hi = np.floor((np.maximum(a, b) + W1) / CELL).astype(int)
        self.buckets = {}
        for k in range(len(a)):
            for cx in range(lo[k, 0], hi[k, 0] + 1):
                for cy in range(lo[k, 1], hi[k, 1] + 1):
                    self.buckets.setdefault((cx, cy), []).append(k)

    def coords(self, x, segs):
        """Ribbon coords of points x (m,2) against candidate segments (k,) -> t, o arrays (m,k)."""
        p, n = self.p, self.n
        d0 = x[:, None, :] - p[segs][None]
        e = (p[segs + 1] - p[segs])[None]
        m = (n[segs + 1] - n[segs])[None]
        ni = n[segs][None]
        A = -_cross(e, m) + 0 * d0[..., 0]
        B = _cross(d0, m) - _cross(e, ni)
        C = _cross(d0, ni)
        disc = B * B - 4 * A * C
        sq = np.sqrt(np.maximum(disc, 0))
        q = -0.5 * (B + np.where(B >= 0, sq, -sq))  # numerically stable roots q/A and C/q
        with np.errstate(divide='ignore', invalid='ignore'):
            t1 = np.where(np.abs(A) > 1e-14, q / A, np.inf)
            t2 = np.where(np.abs(q) > 1e-14, C / q, np.inf)
        out_t = np.full(t1.shape, np.nan)
        out_o = np.full(t1.shape, np.inf)
        for t in (t1, t2):
            ok = np.isfinite(t) & (t >= -1e-6) & (t <= 1 + 1e-6) & (disc >= -1e-12)
            tc = np.clip(np.where(ok, t, 0), 0, 1)
            N = ni + tc[..., None] * m
            r = d0 - tc[..., None] * e
            o = (r * N).sum(-1) / (N * N).sum(-1)
            ok &= np.linalg.norm(r - o[..., None] * N, axis=-1) < 1e-3  # exact ribbon coordinates only
            better = ok & (np.abs(o) < np.abs(out_o))
            out_t = np.where(better, tc, out_t)
            out_o = np.where(better, o, out_o)
        return out_t, out_o

    def displace(self, xy, return_info=False):
        xy = np.asarray(xy, float)
        out = xy.copy()
        info_o = np.full(len(xy), np.inf)
        keys = np.floor(xy / CELL).astype(int)
        order = np.lexsort((keys[:, 1], keys[:, 0]))
        ks = keys[order]
        brk = np.r_[0, np.nonzero((np.diff(ks, axis=0) != 0).any(1))[0] + 1, len(ks)]
        for s0, s1 in zip(brk[:-1], brk[1:]):
            segs = self.buckets.get(tuple(ks[s0]))
            if not segs:
                continue
            segs = np.array(segs)
            idx = order[s0:s1]
            for c0 in range(0, len(idx), 4096):
                ii = idx[c0:c0 + 4096]
                x = xy[ii]
                t, o = self.coords(x, segs)
                j = np.abs(o).argmin(1)
                r = np.arange(len(ii))
                t, o, sg = t[r, j], o[r, j], segs[j]
                good = np.isfinite(o) & (np.abs(o) < W1)
                full = ((1 - t)[:, None] * (self.P[sg] + o[:, None] * self.N[sg])
                        + t[:, None] * (self.P[sg + 1] + o[:, None] * self.N[sg + 1]))
                u = np.clip((np.abs(o) - W0) / (W1 - W0), 0, 1)
                w = np.where(good, 1 - u * u * (3 - 2 * u), 0.0)
                out[ii] = x + w[:, None] * np.where(good[:, None], full - x, 0.0)
                info_o[ii] = np.where(good, o, np.inf)
        return (out, info_o) if return_info else out
