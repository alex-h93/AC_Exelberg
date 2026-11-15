#!/usr/bin/env python3
"""v010 patch domain (offline, .venv + shapely). Stage 1 of the ground patch for the roundabout extension.

B = all points within R_WIDE of the new centreline from station i_cut on, cut by the cross-section line at i_cut
(nothing behind the cut is touched). Every v009 skin triangle overlapping B (area > 5e-3 m^2; float32 slivers on the
cut line ignored) is removed. The seam is built TOPOLOGICALLY (no polygon booleans on the skin): constraint edges for
the CDT (stage 2) are
  * every edge shared by a kept and a removed triangle (exact skin vertices -> watertight seam),
  * every outer-boundary edge of the removed triangles that lies outside B (world edge of the old skin),
  * the B arc (cut line excluded) - outer edge of the new ground,
  * the outline of the new road/gravel ribbon (offsets -3.75 -3 0 3 3.75, stations i_cut..end; full-route normals,
    vertices at i_cut snapped to the existing skin vertices).
Stage 3 keeps CDT triangles whose centroid is in (B u removed) and not in a kept triangle or the ribbon.
Output: data/processed/extension_v010/patch_domain.npz + patch_domain.json
"""
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from prototype_geometry import ribbon
from v009_field import station_normals

ROOT = Path(__file__).resolve().parents[1]
EXT = Path(__import__('os').environ.get('V010_EXT', ROOT / 'data/processed/extension_v010'))  # v011: reverse-track variant
SKIN9 = ROOT / 'data/processed/road_v009/smoothed_skin.npz'
R_WIDE = 140.0
OFFSETS = np.array([-3.75, -3.0, 0.0, 3.0, 3.75])
ROWS = (4.6, 6.0, 7.5, 10.0, 13.0)
GRID = 8.0


def main():
    r = np.load(EXT / 'route.npz')
    P = r['designed_xyz_m']
    ic = int(r['i_cut'])
    N = station_normals(P)
    sk = np.load(SKIN9)
    v = sk['vertices'].astype(np.float64)
    f = sk['triangles']
    roles = sk['roles']
    line = LineString(P[ic:, :2])
    t = np.array([N[ic, 1], -N[ic, 0]])
    assert np.dot(t, P[ic + 1, :2] - P[ic, :2]) > 0
    big = 5000.0
    half = Polygon([P[ic, :2] + N[ic] * big, P[ic, :2] + N[ic] * big + t * big,
                    P[ic, :2] - N[ic] * big + t * big, P[ic, :2] - N[ic] * big])
    B = line.buffer(R_WIDE, quad_segs=16).intersection(half)
    assert B.geom_type == 'Polygon'
    cen = v[f].mean(1)[:, :2]
    cand = np.flatnonzero(shapely.distance(shapely.points(cen), line) < R_WIDE + 20)
    ov = shapely.area(shapely.intersection(shapely.polygons(v[f[cand]][:, :, :2]), B)) > 5e-3
    removed = cand[ov]
    keep = np.ones(len(f), bool)
    keep[removed] = False
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    rg = removed[np.isin(roles[removed], ['ROAD', 'GRAVEL'])]
    proj = shapely.line_locate_point(LineString(P[:, :2]), shapely.points(cen[rg]))
    assert (proj >= s[ic] - 1e-6).all(), 'old road/gravel before the cut would be removed'
    # topology: edges -> (kept count, removed count)
    E = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), 1)
    tid = np.tile(np.arange(len(f)), 3)
    ue, inv = np.unique(E, axis=0, return_inverse=True)
    nk = np.bincount(inv, weights=keep[tid].astype(float), minlength=len(ue))
    nr = np.bincount(inv, weights=(~keep[tid]).astype(float), minlength=len(ue))
    interface = ue[(nk == 1) & (nr == 1)]
    outer_removed = ue[(nk == 0) & (nr == 1)]
    # world-edge edges inside B become interior of the new ground: only those outside B bound the patch
    om = v[outer_removed][:, :, :2].mean(1)
    outer_removed = outer_removed[~shapely.contains_xy(B.buffer(0.01), om[:, 0], om[:, 1])]
    # ribbon
    _, rf = ribbon(P[ic:], OFFSETS)
    rv = np.repeat(P[ic:, None, :], len(OFFSETS), axis=1)
    rv[:, :, :2] += N[ic:, None, :] * OFFSETS[None, :, None]
    keepv = np.unique(f[keep])
    for j in range(len(OFFSETS)):
        d = np.linalg.norm(v[keepv, :2] - rv[0, j, :2], axis=1)
        k = int(d.argmin())
        assert d[k] < 2e-3, ('cut cross-section vertex not found in the remaining skin', OFFSETS[j], d[k])
        rv[0, j] = v[keepv[k]]
    nO = len(OFFSETS)
    rv = rv.reshape(-1, 3)
    band = (np.arange(len(rf)) // 2) % (nO - 1)
    rrole = np.where((band == 0) | (band == nO - 2), 'GRAVEL', 'ROAD')
    nS = len(P) - ic
    idx = np.arange(nS * nO).reshape(nS, nO)
    outline = np.r_[idx[:, -1], idx[-1, ::-1][1:], idx[::-1, 0][1:]]  # left side, end cap (all 5), right side back
    rib = Polygon(rv[outline, :2])
    assert rib.is_valid
    # B arc without the cut line
    bxy = np.asarray(B.exterior.coords)[:-1]
    along = (bxy - P[ic, :2]) @ t
    arc_ok = along > 0.5
    # --- CDT input: points = skin vertices used by constraints + ribbon outline + arc points + Steiner points
    skin_ids = np.unique(np.r_[interface.ravel(), outer_removed.ravel()])
    pts = [v[skin_ids, :2]]
    src_kind = [np.full(len(skin_ids), 0)]  # 0 skin vertex, 1 ribbon vertex, 2 arc, 3 steiner
    src_id = [skin_ids]
    rib_ids = np.unique(outline)
    rib_map = {}
    for k in rib_ids:  # ribbon vertices at i_cut ARE skin vertices
        hit = np.flatnonzero(np.all(np.abs(v[skin_ids, :2] - rv[k, :2]) < 1e-9, axis=1))
        if len(hit):
            rib_map[int(k)] = int(hit[0])
    new_rib = np.array([k for k in rib_ids if int(k) not in rib_map])
    base = len(skin_ids)
    for j, k in enumerate(new_rib):
        rib_map[int(k)] = base + j
    pts.append(rv[new_rib, :2]); src_kind.append(np.full(len(new_rib), 1)); src_id.append(new_rib)
    base += len(new_rib)
    arc_idx = np.flatnonzero(arc_ok)
    pts.append(bxy[arc_idx]); src_kind.append(np.full(len(arc_idx), 2)); src_id.append(arc_idx)
    arc_map = {int(a): base + j for j, a in enumerate(arc_idx)}
    smap = {int(q): j for j, q in enumerate(skin_ids)}
    edges = [(smap[int(a)], smap[int(b)]) for a, b in np.r_[interface, outer_removed]]
    first_row = set(idx[0].tolist())
    edges += [(rib_map[int(a)], rib_map[int(b)]) for a, b in zip(outline, np.roll(outline, -1))
              if not (int(a) in first_row and int(b) in first_row)]
    nb = len(bxy)
    edges += [(arc_map[int(i)], arc_map[int((i + 1) % nb)]) for i in arc_idx if arc_ok[(i + 1) % nb]]
    # domain for Steiner points
    rem_union = shapely.union_all(shapely.polygons(v[f[removed]][:, :, :2]))
    dom = shapely.union_all([B, rem_union]).difference(rib)
    x0, y0, x1, y1 = dom.bounds
    gx, gy = np.meshgrid(np.arange(np.floor(x0 / GRID) * GRID, x1 + GRID, GRID), np.arange(np.floor(y0 / GRID) * GRID, y1 + GRID, GRID))
    st = [np.column_stack([gx.ravel(), gy.ravel()])]
    for o in ROWS:
        for sign in (-1, 1):
            q = np.arange(s[ic] + 1.5, s[-1], 3.0)
            xy = np.column_stack([np.interp(q, s, P[:, k]) for k in (0, 1)])
            nn = np.column_stack([np.interp(q, s, N[:, k]) for k in (0, 1)])
            nn /= np.linalg.norm(nn, axis=1)[:, None]
            st.append(xy + sign * o * nn)
    st = np.vstack(st)
    st = st[shapely.contains_xy(dom, st[:, 0], st[:, 1])]
    allp = np.vstack(pts)
    cons = shapely.multilinestrings([allp[[a, b]] for a, b in edges])
    st = st[shapely.distance(shapely.points(st), cons) > 1.2]
    kept_near = np.flatnonzero(keep & (shapely.distance(shapely.points(cen), line) < R_WIDE + 30))
    kept_poly = shapely.union_all(shapely.polygons(v[f[kept_near]][:, :, :2]))
    st = st[~shapely.contains_xy(kept_poly, st[:, 0], st[:, 1])]
    st = st[np.lexsort((st[:, 1], st[:, 0]))]
    ok = np.ones(len(st), bool)
    seen = {}
    for i, c in enumerate(map(tuple, np.floor(st / 1.5).astype(int))):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                j = seen.get((c[0] + dx, c[1] + dy))
                if j is not None and np.linalg.norm(st[i] - st[j]) < 1.5:
                    ok[i] = False
        if ok[i]:
            seen[c] = i
    st = st[ok]
    pts.append(st); src_kind.append(np.full(len(st), 3)); src_id.append(np.arange(len(st)))
    pts = np.vstack(pts)
    np.savez_compressed(EXT / 'patch_domain.npz', pts=pts, edges=np.array(edges), src_kind=np.concatenate(src_kind),
                        src_id=np.concatenate(src_id), removed=removed, keep=keep, kept_near=kept_near,
                        ribbon_v=rv, ribbon_f=rf, ribbon_role=rrole, ribbon_outline=outline, B_xy=np.asarray(B.exterior.coords))
    out = dict(i_cut=ic, R_wide_m=R_WIDE, removed_triangles=int(len(removed)),
               removed_by_role={k: int((roles[removed] == k).sum()) for k in ('ROAD', 'GRAVEL', 'GRASS')},
               interface_edges=int(len(interface)), outer_removed_edges=int(len(outer_removed)), arc_points=int(len(arc_idx)),
               ribbon_vertices=int(len(rv)), ribbon_triangles=int(len(rf)), constraint_edges=len(edges),
               steiner_points=int(len(st)), cdt_points=int(len(pts)), domain_area_m2=float(dom.area))
    (EXT / 'patch_domain.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
