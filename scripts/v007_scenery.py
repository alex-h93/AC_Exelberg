#!/usr/bin/env python3
"""v007 scenery generator (visual only, second KN5): v006 scenery + corrections from the user's v006 review.

  * Austrian guide posts (Leitpflock, after user photo data/raw/Leitpflock-B16_4333.jpg) replace the v003
    posts, which are removed from the main KN5 (build_full_track_v007.py). Same positions as v003
    (data/processed/full_track_scene_v003/posts.json: every 33 m, +-4.1 m, OSM-connection gaps).
    White body ~0.12 x 0.10 m, black head with knob, black reflector plate with white dots on both
    traffic-facing faces, blue wildlife reflector on the outer side (as in the photo; not verified per post).
  * red chevrons redrawn from the user-supplied SVG (textures_v007).
  * pitched roofs for every house that is not tagged flat: near-rectangular footprints -> one gable;
    L/T/irregular footprints -> greedy rectangle decomposition in the oriented-box frame, one gable per
    section (cross-gables intersect like real valleys) over walls on the true outline and a flat cap at the
    eave. Where the CHM gives no ridge (<= 1.2 m rise) a ~35 deg pitch is assumed (rise 0.7 x half width).
    Garages/sheds keep flat roofs when the scan shows no ridge.
Output: data/processed/scenery_v007/
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v007_textures  # noqa: E402,F401  (registers refl_strip / refl_blue atlas cells)
import v005_roadside as R5  # noqa: E402
import v006_buildings as B  # noqa: E402
from v005_textures import uv_rect  # noqa: E402

OUT = ROOT / 'data/processed/scenery_v007'
SIGN_INNER = 4.4
POSTS = ROOT / 'data/processed/full_track_scene_v003/posts.json'


# ------------------------------------------------------------------ roofs
def rect_sections(p, c, e1, e2, min_area=6.0):
    """Greedy decomposition of the footprint into axis-aligned rectangles in the (e1, e2) frame."""
    a, b = (p - c) @ e1, (p - c) @ e2

    def grid(v):
        v = np.sort(v)
        out = [v[0]]
        for x in v[1:]:
            if x - out[-1] > 0.6:
                out.append(x)
        out[-1] = max(out[-1], v[-1])
        return np.array(out)

    xs, ys = grid(a), grid(b)
    if len(xs) < 2 or len(ys) < 2:
        return []
    cx, cy = (xs[:-1] + xs[1:]) / 2, (ys[:-1] + ys[1:]) / 2
    X, Y = np.meshgrid(cx, cy, indexing='ij')
    pts = c + X.reshape(-1, 1) * e1 + Y.reshape(-1, 1) * e2
    occ = B.inside(pts, p).reshape(X.shape)
    used = np.zeros_like(occ)
    rects = []
    while True:
        free = occ & ~used
        if not free.any():
            break
        best = None
        for i, j in zip(*np.nonzero(free)):
            i1 = i
            while i1 + 1 < free.shape[0] and free[i1 + 1, j]:
                i1 += 1
            j1 = j
            while j1 + 1 < free.shape[1] and free[i:i1 + 1, j1 + 1].all():
                j1 += 1
            area = (xs[i1 + 1] - xs[i]) * (ys[j1 + 1] - ys[j])
            if best is None or area > best[0]:
                best = (area, i, i1, j, j1)
        area, i, i1, j, j1 = best
        used[i:i1 + 1, j:j1 + 1] = True
        if area >= min_area and min(xs[i1 + 1] - xs[i], ys[j1 + 1] - ys[j]) >= 2.0:
            rects.append((xs[i], xs[i1 + 1], ys[j], ys[j1 + 1]))
    return rects


def gable(m, p, c, e1, e2, lo1, hi1, lo2, hi2, zg, zE, rise, fac, roof_m, outline_check=True):
    """One gable over rectangle [lo1,hi1]x[lo2,hi2] of frame (e1,e2); ridge along the longer side.
    Ends that are interior to the footprint are extended by the half width (cross-gable valley)."""
    L1, L2 = hi1 - lo1, hi2 - lo2
    ctr = c + e1 * (lo1 + hi1) / 2 + e2 * (lo2 + hi2) / 2
    if L1 >= L2:
        ax, sx, hl, hw = e1, e2, L1 / 2, L2 / 2
    else:
        ax, sx, hl, hw = e2, -e1, L2 / 2, L1 / 2
    rise = float(min(rise, 1.0 * hw, 7.0))
    zR = zE + rise
    ext = []
    for s in (-1, 1):
        probe = ctr + s * ax * (hl + 0.4)
        interior = outline_check and bool(B.inside(probe[None], p)[0])
        ext.append(hw if interior else B.OVER)
    for k, s in enumerate((-1, 1)):
        e_end = hl + (ext[k] if ext[k] != B.OVER else 0.0)
        base = ctr + s * ax * e_end
        pa, pb = base - sx * hw, base + sx * hw
        B.tri_raw(m, [np.r_[pa, zE], np.r_[pb, zE], np.r_[base, zR]],
                  [(0, (zE - zg) / 6), (2 * hw / 6, (zE - zg) / 6), (hw / 6, (zR - zg) / 6)], fac, np.r_[s * ax, 0])
    drop = B.OVER * rise / hw
    e = np.r_[ax, 0.0]
    for s in (-1, 1):
        eave_line = np.r_[ctr + s * sx * (hw + B.OVER), zE - drop]
        ridge_line = np.r_[ctr, zR]
        a0, a1 = -(hl + ext[0]), hl + ext[1]
        pts = [eave_line + e * a0, eave_line + e * a1, ridge_line + e * a1, ridge_line + e * a0]
        up_dir = (ridge_line - eave_line) / np.linalg.norm(ridge_line - eave_line)
        B.roof_quad(m, pts, roof_m, e, up_dir)
    return rise


def building7(m, b, zg, zb, eave, ridge, MI):
    p = b['poly']
    c, e1, e2, hl, hw, A = B.obb(p)
    rect = abs(B.area(p)) / A
    small = b['tags']['building'] in B.SMALL or abs(B.area(p)) < 30
    fac = MI['facade_plain'] if small else MI[B.FACADES[int(B.h01(b['way']) * 3) % 3]]
    rc = b['tags'].get('roof:colour', '').lower()
    dark = rc in ('grey', 'gray', 'black', 'darkgrey', 'anthracite', '#333333', '#555555') or (not rc and B.h01(b['way'], 1) < 0.3)
    roof_m = MI['roof_dark' if dark else 'roof_red']
    zE = zg + eave
    measured = ridge - eave
    flat_tag = b['tags'].get('roof:shape', '') == 'flat'
    pitched = not flat_tag and (measured > 1.2 or not small)

    def rise_for(half_w):
        return measured if measured > 1.2 else float(np.clip(0.7 * half_w, 1.5, 4.5))

    if pitched and rect >= B.RECT_MIN:
        corners = np.array([c - e1 * hl - e2 * hw, c + e1 * hl - e2 * hw, c + e1 * hl + e2 * hw, c - e1 * hl + e2 * hw])
        B.walls(m, corners, zb, zE, zg, fac)
        r = gable(m, corners, c, e1, e2, -hl, hl, -hw, hw, zg, zE, rise_for(hw), fac, roof_m, outline_check=False)
        return dict(shape='gable', rect=round(rect, 3), sections=1, rise_m=round(r, 2), facade=_n(MI, fac), roof=_n(MI, roof_m))
    B.walls(m, p, zb, zE, zg, fac)
    tris = B.ear_clip(p)
    if tris is None:
        return None
    m.raw(np.c_[p, np.full(len(p), zE + 0.02)], np.tile([0, 0, 1.0], (len(p), 1)), p / 2.0, np.array(tris), MI['roof_dark'])
    if not pitched:
        return dict(shape='flat', rect=round(rect, 3), sections=0, rise_m=0.0, facade=_n(MI, fac), roof='roof_dark')
    secs = rect_sections(p, c, e1, e2)
    rises = [gable(m, p, c, e1, e2, *s, zg, zE + 0.01, rise_for(min(s[1] - s[0], s[3] - s[2]) / 2), fac, roof_m) for s in secs]
    return dict(shape='cross_gable' if len(secs) > 1 else ('gable_section' if secs else 'flat'), rect=round(rect, 3),
                sections=len(secs), rise_m=round(max(rises), 2) if rises else 0.0, facade=_n(MI, fac),
                roof=_n(MI, roof_m) if secs else 'roof_dark')


def _n(MI, i):
    return [k for k, v in MI.items() if v == i][0]


# ------------------------------------------------------------------ posts
def leitpflock(m, R, base, t, n_out):
    """Austrian guide post. t: travel tangent, n_out: unit normal pointing away from the road."""
    t, n_out = np.r_[t[:2], 0.0], np.r_[n_out[:2], 0.0]
    ax = np.array([n_out, t, R5.UP])  # x across (away from road), y along road, z up
    body_h, head_h = 0.88, 0.17
    m.box(base + R5.UP * (body_h / 2 - 0.1), ax, [0.06, 0.05, body_h / 2 + 0.1], 'white', 0)
    m.box(base + R5.UP * (body_h + head_h / 2), ax, [0.065, 0.055, head_h / 2], 'dark', 0)
    R5.lathe(m, [(0.028, 0.0), (0.028, 0.035)], base + R5.UP * (body_h + head_h), 8, 'dark', cap_top=True)
    u0, v0, u1, v1 = uv_rect('refl_strip', 2)
    for s in (-1, 1):  # both traffic-facing faces
        f = s * t
        right = np.cross(R5.UP, f)
        cc = base + f * 0.052 + R5.UP * (body_h - 0.16)
        w, h = 0.04, 0.2
        pts = [cc - right * w / 2 - R5.UP * h / 2, cc + right * w / 2 - R5.UP * h / 2, cc + right * w / 2 + R5.UP * h / 2,
               cc - right * w / 2 + R5.UP * h / 2]
        m.quad(pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], 0, normal=f)
    # blue wildlife reflector on the outer side, faces both travel directions
    bc = base + n_out * 0.095 + R5.UP * (body_h - 0.17)
    m.box(bc, ax, [0.03, 0.035, 0.11], 'dark', 0)
    u0, v0, u1, v1 = uv_rect('refl_blue', 3)
    for s in (-1, 1):
        f = s * t
        right = np.cross(R5.UP, f)
        cc = bc + f * 0.037
        w, h = 0.055, 0.2
        pts = [cc - right * w / 2 - R5.UP * h / 2, cc + right * w / 2 - R5.UP * h / 2, cc + right * w / 2 + R5.UP * h / 2,
               cc - right * w / 2 + R5.UP * h / 2]
        m.quad(pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], 0, normal=f)


def add_posts(store, R, placements):
    pl = json.loads(POSTS.read_text())['placements']
    for q in pl:
        s, off = q['arclength_m'], q['offset_left_m']
        pos, t, n = R.frame(s)
        side = np.sign(off)
        x, y, z = q['ground_xyz_m']
        leitpflock(R5.bucket(store, 'POST', s), R, np.array([x, y, z - 0.02]), t, side * n)
    placements.append(dict(kind='guide_posts', count=len(pl), source='v003 posts.json positions', design='Austrian Leitpflock (user photo)'))
    return len(pl)


def main(prefix='V007', out=OUT):
    B.building = building7
    R5.SIGN_INNER = SIGN_INNER
    R5.PREFIX = prefix
    R5.JUNC_BARRIER = False
    R5.MATS = tuple(m.replace('V005_', f'{prefix}_') for m in R5.MATS) + tuple(f'{prefix}_{k}' for k in B.BMATS)
    R5.LODS = dict(R5.LODS, BLDG=(0, 1500, True), POST=(0, 450, False))
    MI = {k: R5.MATS.index(f'{prefix}_{k}') for k in B.BMATS}
    fps = B.load_footprints()
    R5.AVOID = B.make_avoid(fps)
    stats = {}

    def extra(store, R, placements):
        stats['posts'] = add_posts(store, R, placements)
        stats.update(B.add_buildings(store, R, placements, fps, MI, R5.bucket))

    R5.main(out=out, extra=extra)
    pl = json.loads((out / 'placements.json').read_text())
    bl = [p for p in pl if p['kind'] == 'building']
    rep = dict(stats=stats, sign_inner_m=SIGN_INNER, shapes=dict(Counter(p['shape'] for p in bl)),
               flat_by_type=dict(Counter(p['osm_type'] for p in bl if p['shape'] == 'flat')),
               height_sources=dict(Counter(p['height_source'] for p in bl)), note=__doc__)
    (out / 'buildings.json').write_text(json.dumps(rep, indent=2) + '\n')
    print(json.dumps({k: rep[k] for k in ('stats', 'shapes', 'flat_by_type')}))


if __name__ == '__main__':
    main()
