#!/usr/bin/env python3
"""v005 roadside geometry (offline, .venv). Visual-only objects for a SECOND KN5 that sits beside the
unchanged v004 KN5 (models.ini MODEL_1). Nothing here has collision.

Inputs: route + final ground skin (v003 repaired_skin.npz), roadside inventory
(inventory_v2.csv), OSM ways (junctions), v004 trees (forest mask for the edge shrub band),
Richtfunkstation Exelberg position (OSM node 2916162012).

Lateral layout (metres from centreline; asphalt +-3, gravel 3-4, invisible wall +-6 from v003):
  guardrail rail face 5.9 (just inside the wall so cars cannot visibly drive through it),
  sign/chevron posts 6.4, concrete parapet 6.0, fences 7.0, shrub band 6.6-10, junction barriers >= 8.
Output: data/processed/roadside_v005/{geometry.npz, objects.json, placements.json}
"""
import csv
import glob
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import full_track_v003_geometry as H  # noqa: E402
import v004_treegen as TG  # noqa: E402
from v005_textures import uv_rect, SHAPE_BACK  # noqa: E402

OUT = ROOT / 'data/processed/roadside_v005'
ORIGIN = np.array([589500.0, 5346800.0])
TOWER_LONLAT = (16.2440867, 48.2488238)
CELL = 250.0
SKIN = ROOT / 'data/processed/full_track_scene_v003/repaired_skin.npz'  # v008+: smoothed skin
RAIL_D, SIGN_D, WALL_D = 5.9, 6.4, 6.0
SIGN_INNER = None  # v006+: if set, sign centre = SIGN_INNER + width/2 (inner plate edge at SIGN_INNER)
PREFIX = 'V005'
JUNC_BARRIER = True  # v006: False (user asked to remove the junction barriers + their no-entry signs)
AVOID = None  # optional callable(xy) -> True if a shrub must not be placed there (e.g. inside buildings)
TREES = ROOT / 'data/processed/vegetation_v004/trees.npz'  # v010: trees_v010.npz (shrub-band density source)
LODS = {'RAIL': (0, 700, True), 'SIGN': (0, 500, True), 'JUNC': (0, 600, False), 'SHRUB': (0, 260, True)}
MATS = ('V005_atlas', 'V005_metal', 'V005_asphalt', 'V005_gravel', 'V005_foliage', 'V005_bark')


# ------------------------------------------------------------------ mesh accumulation
class Mesh:
    def __init__(self):
        self.v, self.n, self.uv, self.tri, self.mat = [], [], [], [], []
        self.count = 0

    def quad(self, p, uv, mat, normal=None):
        """p: 4 corners CCW seen from the front; uv: 4 uv pairs."""
        p = np.asarray(p, float)
        nrm = np.cross(p[1] - p[0], p[3] - p[0]) if normal is None else np.asarray(normal, float)
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
        self.v.append(p); self.n.append(np.tile(nrm, (4, 1))); self.uv.append(np.asarray(uv, float))
        self.tri.append(np.array([[0, 1, 2], [0, 2, 3]]) + self.count); self.mat += [mat, mat]; self.count += 4

    def raw(self, v, n, uv, tri, mat):
        self.v.append(np.asarray(v, float)); self.n.append(np.asarray(n, float)); self.uv.append(np.asarray(uv, float))
        self.tri.append(np.asarray(tri) + self.count); self.mat += list(np.broadcast_to(mat, len(tri))); self.count += len(v)

    def box(self, c, ax, half, uvname, mat=0, skip_bottom=True):
        """Oriented box: c centre, ax 3x3 rows = unit axes (x, y, z), half sizes."""
        c, ax, h = np.asarray(c, float), np.asarray(ax, float), np.asarray(half, float)
        u0, v0, u1, v1 = uv_rect(uvname, 6)
        uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        for k in range(3):
            for s in (-1, 1):
                if skip_bottom and k == 2 and s == -1:
                    continue
                a, b = [(k + 1) % 3, (k + 2) % 3]
                f = c + s * ax[k] * h[k]
                ea, eb = ax[a] * h[a], ax[b] * h[b]
                corners = [f - ea - eb, f + ea - eb, f + ea + eb, f - ea + eb]
                if s < 0:
                    corners = corners[::-1]
                self.quad(corners, uv, mat, normal=s * ax[k])

    def plate(self, centre, facing, up, w, h, front, back, mat=0):
        """Double-sided sign plate; facing = unit normal of the front."""
        right = np.cross(up, facing)  # viewer's right when looking at the front
        c, e = np.asarray(centre, float), 0.012
        f = c + facing * e
        u0, v0, u1, v1 = uv_rect(front, 1)
        pts = [f - right * w / 2 - up * h / 2, f + right * w / 2 - up * h / 2, f + right * w / 2 + up * h / 2, f - right * w / 2 + up * h / 2]
        self.quad(pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], mat, normal=facing)
        b = c - facing * e
        u0, v0, u1, v1 = uv_rect(back, 1)
        pts = [b + right * w / 2 - up * h / 2, b - right * w / 2 - up * h / 2, b - right * w / 2 + up * h / 2, b + right * w / 2 + up * h / 2]
        self.quad(pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], mat, normal=-facing)

    def arrays(self):
        return (np.concatenate(self.v).astype(np.float32), np.concatenate(self.n).astype(np.float32),
                np.concatenate(self.uv).astype(np.float32), np.concatenate(self.tri).astype(np.int32),
                np.asarray(self.mat, np.int32))


# ------------------------------------------------------------------ route frame
class Route:
    def __init__(self):
        d = np.load(SKIN)
        self.p = d['designed_xyz_m'].astype(float)
        self.s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(self.p[:, :2], axis=0), axis=1))]
        self.L = float(self.s[-1])
        t = np.gradient(self.p[:, :2], axis=0)
        self.t = t / np.linalg.norm(t, axis=1)[:, None]
        hd = np.unwrap(np.arctan2(self.t[:, 1], self.t[:, 0]))
        g = np.arange(0, self.L, 2.0)
        h = np.interp(g, self.s, hd)
        k = np.gradient(h, g)
        w = 11
        self.kg, self.k = g, np.convolve(np.pad(k, w, mode='edge'), np.ones(2 * w + 1) / (2 * w + 1), 'same')[w:-w]
        print('ground index...', flush=True)
        self.ground = H.GroundIndex(d['vertices'], d['triangles'])

    def frame(self, s):
        s = float(np.clip(s, 0, self.L))
        i = min(int(np.searchsorted(self.s, s)) - 1, len(self.p) - 2); i = max(i, 0)
        a = (s - self.s[i]) / max(self.s[i + 1] - self.s[i], 1e-9)
        pos = self.p[i] * (1 - a) + self.p[i + 1] * a
        t = self.t[i] * (1 - a) + self.t[i + 1] * a; t /= np.linalg.norm(t)
        return pos, np.array([t[0], t[1], 0.0]), np.array([-t[1], t[0], 0.0])  # left normal

    def at(self, s, side, d):
        """World point at chainage s, side +1 left / -1 right, lateral d, on the ground."""
        pos, t, n = self.frame(s)
        xy = pos[:2] + side * d * n[:2]
        return np.array([xy[0], xy[1], self.z(xy)]), t, n

    def z(self, xy):
        try:
            return self.ground.sample(np.asarray(xy, float))
        except RuntimeError:
            return self.ground.extrapolate(np.asarray(xy, float))

    def curvature(self, s):
        return float(np.interp(s, self.kg, self.k))

    def nearest(self, xy):
        d = np.linalg.norm(self.p[:, :2] - np.asarray(xy)[None], axis=1)
        i = int(d.argmin())
        return float(self.s[i]), float(d[i])


UP = np.array([0.0, 0.0, 1.0])
SIDE = {'L': 1, 'R': -1}


def bucket(store, kind, s):
    return store[(kind, int(s // CELL))]


# ------------------------------------------------------------------ guardrail (Austrian W-profile)
PROFILE = [(0.00, 0.47), (0.06, 0.53), (0.01, 0.61), (0.06, 0.69), (0.00, 0.75)]  # (outward d, height)


def guardrail(store, R, s0, s1, side, placements, gaps):
    ss = np.arange(s0, s1 + 0.01, 2.0)
    if len(ss) < 3:
        return
    pts = []
    for s in ss:
        p, t, n = R.at(s, side, RAIL_D)
        pts.append((p, n * side))  # outward horizontal
    nseg = len(ss)
    ramp = 2  # samples (4 m) ramping into the ground at each end
    for j in range(nseg - 1):
        s_mid = (ss[j] + ss[j + 1]) / 2
        if any(a <= s_mid <= b for a, b in gaps):
            continue
        m = bucket(store, 'RAIL', s_mid)
        (pa, oa), (pb, ob) = pts[j], pts[j + 1]

        def drop(k):
            e = min(k, nseg - 1 - k)
            return 0.0 if e >= ramp else (ramp - e) / ramp * 0.6
        da, db = drop(j), drop(j + 1)
        prof = PROFILE + [(0.11, 0.75), (0.11, 0.47)]  # closed loop incl. flat back
        u0, v0, u1, v1 = uv_rect('metal', 8)
        for k in range(len(prof)):
            (d0, h0), (d1, h1) = prof[k], prof[(k + 1) % len(prof)]
            a0 = pa + oa * d0 + UP * (h0 - da); a1 = pa + oa * d1 + UP * (h1 - da)
            b0 = pb + ob * d0 + UP * (h0 - db); b1 = pb + ob * d1 + UP * (h1 - db)
            m.quad([a1, b1, b0, a0], [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], 1)
        # post (sigma post simplified), behind the beam
        if j % 1 == 0 and da == 0:
            c = pa + oa * 0.16 + UP * 0.33
            fwd = np.cross(UP, oa)
            m.box(c, [oa, fwd, UP], [0.05, 0.03, 0.45], 'post_grey', 1)
    placements.append(dict(kind='guardrail', side=side, s0=float(s0), s1=float(s1), lateral_m=RAIL_D))


# ------------------------------------------------------------------ signs
def post(m, base, top, w=0.07):
    c = (base + top) / 2
    m.box(c, [np.array([1., 0, 0]), np.array([0, 1., 0]), UP], [w / 2, w / 2, (top[2] - base[2]) / 2], 'post_grey', 0)


def sign(store, R, s, side, cell, w, h, bottom, placements, note='', two_posts=False, d=None):
    if d is None:
        d = SIGN_D if SIGN_INNER is None else SIGN_INNER + w / 2
    p, t, n = R.at(s, side, d)
    facing = -t  # faces traffic driving in track direction
    m = bucket(store, 'SIGN', s)
    centre = p + UP * (bottom + h / 2)
    back = SHAPE_BACK.get(cell, 'back_rect')
    m.plate(centre, facing, UP, w, h, cell, back)
    offs = [-w * 0.35, w * 0.35] if two_posts else [0.0]
    right = np.cross(UP, facing)
    for o in offs:
        base = p + right * o - facing * 0.03 + UP * -0.3
        post(m, base, base + UP * (bottom + h * 0.85 + 0.3))
    placements.append(dict(kind='sign', cell=cell, s=float(s), side=side, size_m=[w, h], bottom_m=bottom, lateral_m=float(d), note=note))


SIGN_SPEC = {  # subtype -> (cell, w, h, bottom, two_posts, note)
    'speed_50': ('speed_50', .6, .6, 1.6, False, ''), 'speed_70': ('speed_70', .6, .6, 1.6, False, ''),
    'speed_limit': ('speed_70', .6, .6, 1.6, False, 'value not known; 70 assumed'),
    'warning': ('warn_generic', .9, .8, 1.5, False, 'type not readable; generic danger sign'),
    'warning_curves': ('warn_curves', .9, .8, 1.5, False, ''),
    'priority_road': ('priority', .6, .6, 1.6, False, ''), 'no_stopping': ('no_stopping', .6, .6, 1.6, False, ''),
    'direction_board': ('direction', 1.8, .9, 1.2, True, 'text unknown; abstract lines'),
    'board': ('info_board', 1.4, .7, 1.0, True, 'content unknown'), 'billboard': ('billboard', 3.0, 1.5, 1.0, True, 'generic'),
}


def chevron_series(store, R, s_obs, side_obs, length, n_boards, red, placements):
    lo, hi = s_obs - 50, s_obs + max(length, 0) + 50
    g = (R.kg >= lo) & (R.kg <= hi)
    # boards stand on the OUTER side: side L -> right-hand bend (k < 0), side R -> left-hand bend (k > 0)
    want = {'L': -1, 'R': 1}.get(side_obs, 0)
    kk = R.k[g] * want if want else np.abs(R.k[g])
    if g.any() and kk.max() > 1 / 400:
        j = int(np.argmax(kk)); sc = float(R.kg[g][j])
    else:
        sc = s_obs + max(length, 0) / 2
    k = R.curvature(sc)
    side = SIDE.get(side_obs) if side_obs in SIDE else (-1 if k > 0 else 1)
    d = ('L' if side < 0 else 'R') if want else ('L' if k > 0 else 'R')  # arrow points into the bend (outer-side board)
    cell = f'chev_{"red" if red else "yel"}_{d}'
    spacing = 12.0
    for i in range(n_boards):
        s = sc + (i - (n_boards - 1) / 2) * spacing
        sign(store, R, s, side, cell, .6, .75, 0.9, placements, note=f'chevron series snapped to curvature peak ({s_obs:.0f}->{sc:.0f})')


# ------------------------------------------------------------------ junction stubs
SKIP_HW = {'path', 'footway', 'cycleway', 'steps', 'bridleway', 'pedestrian', 'platform', 'proposed', 'construction', 'corridor'}
WIDTH = {'primary': 6.5, 'secondary': 6.0, 'tertiary': 5.5, 'unclassified': 4.5, 'residential': 5.0, 'service': 4.0, 'track': 3.5}


def osm_stubs(R):
    T = Transformer.from_crs(4326, 25833, always_xy=True)
    nodes, ways = {}, {}
    for f in sorted(glob.glob(str(ROOT / 'data/raw/osm/map_*.osm'))):
        r = ET.parse(f).getroot()
        for n in r.iter('node'):
            nodes[n.get('id')] = (float(n.get('lon')), float(n.get('lat')))
        for w in r.iter('way'):
            tags = {t.get('k'): t.get('v') for t in w.findall('tag')}
            if 'highway' in tags:
                ways[w.get('id')] = ([nd.get('ref') for nd in w.findall('nd')], tags)
    out = []
    for wid, (refs, tags) in ways.items():
        hw = tags['highway']
        if hw in SKIP_HW or hw not in WIDTH or tags.get('area') == 'yes':
            continue
        ll = np.array([nodes[r] for r in refs if r in nodes])
        if len(ll) < 2:
            continue
        x, y = T.transform(ll[:, 0], ll[:, 1])
        xy = np.c_[x, y] - ORIGIN
        dist = np.array([R.nearest(q)[1] for q in xy])
        k = int(dist.argmin())
        if dist[k] > 6:
            continue
        for seg in (xy[k:], xy[:k + 1][::-1]):
            if len(seg) < 2:
                continue
            seglen = np.r_[0, np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))]
            if seglen[-1] < 12:
                continue
            s_j, _ = R.nearest(seg[0])
            if s_j < 60 or s_j > R.L - 60:
                continue
            q = np.array([np.interp(min(15, seglen[-1]), seglen, seg[:, 0]), np.interp(min(15, seglen[-1]), seglen, seg[:, 1])])
            pos, t, n = R.frame(s_j)
            dvec = (q - seg[0]) / (np.linalg.norm(q - seg[0]) + 1e-9)
            if abs(dvec @ t[:2]) > 0.9:  # continuation of the route itself
                continue
            if R.nearest(q)[1] < 8:  # runs along the road
                continue
            side = 1 if dvec @ n[:2] > 0 else -1
            surface = tags.get('surface', '')
            asphalt = surface in ('asphalt', 'paved', 'concrete') or (hw in ('primary', 'secondary', 'tertiary', 'residential', 'unclassified') and surface in ('', 'asphalt'))
            out.append(dict(way=wid, highway=hw, name=tags.get('name', ''), surface=surface, s=s_j, side=side,
                            width=WIDTH[hw], asphalt=bool(asphalt), poly=seg, length=float(seglen[-1])))
    out.sort(key=lambda j: j['s'])
    merged = []
    for j in out:
        if merged and abs(merged[-1]['s'] - j['s']) < 12 and merged[-1]['side'] == j['side']:
            if j['width'] > merged[-1]['width']:
                merged[-1] = j
            continue
        merged.append(j)
    return merged


def stub(store, R, j, placements):
    seg = j['poly']
    seglen = np.r_[0, np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))]
    L = min(28.0, seglen[-1])
    ts = np.arange(0, L + 0.01, 1.5)
    cx, cy = np.interp(ts, seglen, seg[:, 0]), np.interp(ts, seglen, seg[:, 1])
    c = np.c_[cx, cy]
    tang = np.gradient(c, axis=0); tang /= np.linalg.norm(tang, axis=1)[:, None]
    nor = np.c_[-tang[:, 1], tang[:, 0]]
    hw = j['width'] / 2
    left, right = c + nor * hw, c - nor * hw
    ok = np.array([min(R.nearest(a)[1], R.nearest(b)[1]) >= 3.05 for a, b in zip(left, right)])
    if not ok.any():
        return None
    i0 = int(np.argmax(ok))
    left, right, c, cdist = left[i0:], right[i0:], c[i0:], np.array([R.nearest(q)[1] for q in c[i0:]])
    if len(c) < 3:
        return None
    m = bucket(store, 'JUNC', j['s'])
    mat = 2 if j['asphalt'] else 3
    zl = np.array([R.z(q) for q in left]) + 0.06
    zr = np.array([R.z(q) for q in right]) + 0.06
    for k in range(len(c) - 1):
        a0 = np.r_[right[k], zr[k]]; a1 = np.r_[left[k], zl[k]]
        b0 = np.r_[right[k + 1], zr[k + 1]]; b1 = np.r_[left[k + 1], zl[k + 1]]
        uv = [tuple(p[:2] / 4.0) for p in (a0, b0, b1, a1)]
        m.quad([a0, b0, b1, a1], uv, mat, normal=None)
    if not JUNC_BARRIER:
        placements.append(dict(kind='junction', way=j['way'], highway=j['highway'], name=j['name'], s=float(j['s']), side=j['side'],
                               width_m=j['width'], surface='asphalt' if j['asphalt'] else 'gravel', stub_length_m=float(L),
                               barrier_xy=None, source='OSM'))
        return (float(j['s']), j['side'])
    # barrier where the centreline is >= 8 m from the road centre (beyond the 6 m invisible wall)
    kb = int(np.argmax(cdist >= 8.0)) if (cdist >= 8.0).any() else len(c) - 1
    pc = np.r_[c[kb], R.z(c[kb])]
    tb = (c[min(kb + 1, len(c) - 1)] - c[max(kb - 1, 0)]); tb /= np.linalg.norm(tb)
    across = np.r_[-tb[1], tb[0], 0.0]; along = np.r_[tb, 0.0]
    mb = bucket(store, 'SIGN', j['s'])
    span = j['width'] + 0.6
    mb.box(pc + UP * 0.95, [across, along, UP], [span / 2, 0.06, 0.08], 'barrier_stripes', 0)
    for sgn in (-1, 1):
        base = pc + across * sgn * (span / 2 + 0.05) + UP * -0.3
        mb.box(base + UP * 0.68, [across, along, UP], [0.05, 0.05, 0.68], 'red', 0)
    # Fahrverbot sign facing the main road, on the right-hand post as seen from the main road
    sp = pc + across * (span / 2 + 0.05) * -1
    facing = -along
    mb.plate(sp + UP * 1.75 + facing * 0.08, facing, UP, 0.5, 0.5, 'no_entry_round', 'back_round')
    placements.append(dict(kind='junction', way=j['way'], highway=j['highway'], name=j['name'], s=float(j['s']), side=j['side'],
                           width_m=j['width'], surface='asphalt' if j['asphalt'] else 'gravel', stub_length_m=float(L),
                           barrier_xy=pc.tolist(), source='OSM'))
    return (float(j['s']), j['side'])


def pad(store, R, s, side, length, placements, note):
    m = bucket(store, 'JUNC', s)
    ss = np.arange(s - length / 2, s + length / 2 + 0.01, 2.0)
    for a, b in zip(ss[:-1], ss[1:]):
        q = [R.at(a, side, 4.2)[0], R.at(b, side, 4.2)[0], R.at(b, side, 10.0)[0], R.at(a, side, 10.0)[0]]
        q = [x + UP * 0.06 for x in q]
        if side < 0:
            q = [q[0], q[3], q[2], q[1]]
        m.quad(q, [tuple(x[:2] / 4.0) for x in q], 3)
    placements.append(dict(kind='parking_pad', s=float(s), side=side, length_m=length, lateral_m=[4.2, 10.0], note=note, source='inventory'))


# ------------------------------------------------------------------ simple linear features
def parapet(store, R, s0, s1, side, placements):
    for s in np.arange(s0, s1, 4.0):
        p, t, n = R.at(s + 1.9, side, WALL_D + 0.25)
        m = bucket(store, 'SIGN', s)
        m.box(p + UP * 0.35, [n * side, t, UP], [0.25, 1.95, 0.45], 'concrete', 0)
    placements.append(dict(kind='concrete_parapet', s0=float(s0), s1=float(s1), side=side))


def railing(store, R, s0, s1, side, placements, uvname='post_grey', d=6.2, hgt=1.0):
    ss = np.arange(s0, s1 + .01, 2.0)
    for a, b in zip(ss[:-1], ss[1:]):
        pa, t, n = R.at(a, side, d); pb = R.at(b, side, d)[0]
        m = bucket(store, 'SIGN', a)
        m.box(pa + UP * (hgt / 2 - .15), [n * side, t, UP], [0.04, 0.04, hgt / 2 + .15], uvname, 0)
        for hh in (hgt * .5, hgt):
            mid = (pa + pb) / 2 + UP * hh
            dirv = pb - pa; ln = np.linalg.norm(dirv); dirv /= ln
            side_v = np.cross(UP, dirv); side_v /= np.linalg.norm(side_v)
            m.box(mid, [side_v, dirv, np.cross(dirv, side_v)], [0.03, ln / 2, 0.03], uvname, 0, skip_bottom=False)
    placements.append(dict(kind='railing' if uvname == 'post_grey' else 'fence', s0=float(s0), s1=float(s1), side=side))


# ------------------------------------------------------------------ tower
def lathe(m, profile, centre, segs, uvname, mat=0, cap_top=False):
    u0, v0, u1, v1 = uv_rect(uvname, 8)
    ang = np.linspace(0, 2 * np.pi, segs + 1)
    for (r0, z0), (r1, z1) in zip(profile[:-1], profile[1:]):
        for a, b in zip(ang[:-1], ang[1:]):
            p = [centre + np.array([r0 * math.cos(a), r0 * math.sin(a), z0]), centre + np.array([r0 * math.cos(b), r0 * math.sin(b), z0]),
                 centre + np.array([r1 * math.cos(b), r1 * math.sin(b), z1]), centre + np.array([r1 * math.cos(a), r1 * math.sin(a), z1])]
            if np.linalg.norm(p[0] - p[3]) < 1e-6 and np.linalg.norm(p[1] - p[2]) < 1e-6:
                continue
            m.quad(p, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], mat)
    if cap_top:
        r, z = profile[-1]
        for a, b in zip(ang[:-1], ang[1:]):
            p = [centre + np.array([0, 0, z]), centre + np.array([r * math.cos(a), r * math.sin(a), z]), centre + np.array([r * math.cos(b), r * math.sin(b), z])]
            m.raw(p, np.tile(UP, (3, 1)), [(u0, v0), (u1, v0), (u1, v1)], [[0, 1, 2]], mat)


def tower(R, placements):
    T = Transformer.from_crs(4326, 25833, always_xy=True)
    xy = np.array(T.transform(*TOWER_LONLAT)) - ORIGIN
    z = R.z(xy)
    c = np.r_[xy, z - 0.5]
    m = Mesh()
    # concrete shaft + stacked antenna platforms (approximation from reference photos; not surveyed)
    shaft = [(4.2, 0.0), (3.4, 56.0)]
    lathe(m, shaft, c, 20, 'tower')
    plats = [(56.0, 9.0, 2.6), (60.5, 8.0, 2.4), (64.8, 7.0, 2.4), (69.0, 5.5, 3.2)]
    for z0, r, hgt in plats:
        lathe(m, [(3.4, z0 - 0.01), (r, z0), (r, z0 + hgt), (3.4, z0 + hgt + 0.01)], c, 28, 'tower')
    lathe(m, [(3.4, 56.0), (3.3, 72.2)], c, 20, 'tower')
    lathe(m, [(3.3, 72.2), (2.0, 72.4), (1.8, 79.0)], c, 16, 'tower', cap_top=True)
    # red/white mast 79-109 m
    zb, band = 79.0, 30.0 / 7
    for i in range(7):
        r0 = 0.9 - 0.6 * i / 7; r1 = 0.9 - 0.6 * (i + 1) / 7
        lathe(m, [(r0, zb + i * band), (r1, zb + (i + 1) * band)], c, 6, 'red' if i % 2 == 0 else 'white', cap_top=(i == 6))
    # equipment building at the base (generic)
    ax = [np.array([1., 0, 0]), np.array([0, 1., 0]), UP]
    m.box(c + np.array([12.0, -4.0, 2.5]), ax, [9.0, 5.0, 3.0], 'plaster', 0)
    m.box(c + np.array([12.0, -4.0, 5.6]), ax, [9.2, 5.2, 0.15], 'dark', 0)
    placements.append(dict(kind='tower', name='Richtfunkstation Exelberg', xy_local=xy.tolist(), ground_z_local=float(z), height_m=109.0,
                           source='OSM node 2916162012 / Wikipedia (109 m) / BEV DSM 97 m return; shape approximated'))
    return m


# ------------------------------------------------------------------ shrub band
def shrubs(store, R, blocked, rng, placements):
    t = np.load(TREES)
    xy = t['xyz'][:, :2]
    grid = defaultdict(list)
    for i, q in enumerate(xy):
        grid[(int(q[0] // 20), int(q[1] // 20))].append(i)

    def near(q, r):
        cx, cy = int(q[0] // 20), int(q[1] // 20)
        ids = [i for dx in (-1, 0, 1, 2, -2) for dy in (-1, 0, 1, 2, -2) for i in grid.get((cx + dx, cy + dy), ())]
        if not ids:
            return 0, 1e9
        d = np.linalg.norm(xy[ids] - q, axis=1)
        return int((d < r).sum()), float(d.min())
    count = 0
    for s in np.arange(30, R.L - 30, 4.5):
        for side in (1, -1):
            if any(abs(s - bs) < 12 and bside == side for bs, bside in blocked):
                continue
            d = rng.uniform(6.6, 10.0)
            pos, tt, n = R.frame(s + rng.uniform(-1.5, 1.5))
            q = pos[:2] + side * d * n[:2]
            dense, nearest = near(q, 25.0)
            if dense < 3 or nearest < 2.0 or (AVOID is not None and AVOID(q)):
                continue
            for _ in range(1 + int(rng.random() < 0.5)):
                qq = q + rng.normal(0, 0.8, 2)
                h = rng.uniform(1.2, 2.8); cr = rng.uniform(0.9, 1.9)
                tr = TG.tree(3, h, cr, int(rng.integers(1 << 30)), detail=0.8)
                a = rng.uniform(0, 2 * np.pi); rot = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
                v = tr['v'] @ rot.T + np.r_[qq, R.z(qq) - 0.05]
                nn = tr['n'] @ rot.T
                bucket(store, 'SHRUB', s).raw(v, nn, tr['uv'], tr['tri'], np.where(tr['mat'] == 0, 4, 5))
                count += 1
    placements.append(dict(kind='shrub_band', count=count, rule='every 4.5 m per side, 6.6-10 m out, where >=3 v004 CHM trees within 25 m'))
    return count


# ------------------------------------------------------------------ main
def main(out=None, extra=None):
    """extra(store, R, placements, objects_hook) lets later versions add geometry before serialisation."""
    OUT_ = OUT if out is None else Path(out)
    OUT_.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(505)
    R = Route()
    store = defaultdict(Mesh)
    placements = []
    inv = list(csv.DictReader(open(ROOT / 'data/processed/roadside_inventory/inventory_v2.csv')))

    # junctions first (they create gaps for rails and shrubs)
    blocked = []
    for j in osm_stubs(R):
        r = stub(store, R, j, placements)
        if r:
            blocked.append(r)
    for row in inv:
        if row['type'] == 'junction' and row['subtype'] in ('parking', 'gravel_area', 'gravel'):
            s = float(row['chainage_m']); sides = [1, -1] if row['side'] == 'both' else [SIDE[row['side']]]
            for sd in sides:
                if any(abs(s - bs) < 15 and bside == sd for bs, bside in blocked):
                    continue
                pad(store, R, s + max(float(row['length_m']), 0) / 2, sd, max(16.0, float(row['length_m']) + 8), placements,
                    f"{row['id']} {row['subtype']} {row['note']}")
                blocked.append((s, sd))
    gaps_by_side = defaultdict(list)
    for bs, bside in blocked:
        gaps_by_side[bside].append((bs - 8, bs + 8))

    for row in inv:
        s, typ, sub = float(row['chainage_m']), row['type'], row['subtype']
        length = float(row['length_m'])
        sides = [1, -1] if row['side'] == 'both' else [SIDE[row['side']]]
        if typ == 'guardrail':
            L = max(length + 20.0, 40.0)
            mid = s + max(length, 0) / 2
            for sd in sides:
                guardrail(store, R, max(mid - L / 2, 5), min(mid + L / 2, R.L - 5), sd, placements, gaps_by_side[sd])
        elif typ == 'sign' and sub.startswith('chevron'):
            nb = int(row['note'].split()[0]) if row['note'][:1].isdigit() else (4 if 'series' in row['note'] or 'several' in row['note'] else 3)
            chevron_series(store, R, s, row['side'], length, nb, sub.endswith('red'), placements)
        elif typ == 'sign' and sub == 'town_sign':
            place = 'Scheiblingstein' if 'Scheibling' in row['note'] else 'Koenigstetten'
            # driving direction leaves Koenigstetten at the start, so its sign is the end-of-town board
            end = 'end' in row['note'] or place == 'Koenigstetten'
            for sd in ([-1] if row['side'] == 'both' else sides):
                sign(store, R, s, sd, f"town_{'end_' if end else ''}{place}", 1.4, .7, 1.4, placements, note=row['note'], two_posts=True)
                if 'children' in row['note']:
                    sign(store, R, s + 12, sd, 'children', .9, .8, 1.5, placements, note=row['note'])
        elif typ == 'sign' and sub in SIGN_SPEC:
            cell, w, h, b, two, note = SIGN_SPEC[sub]
            for sd in sides:
                sign(store, R, s, sd, cell, w, h, b, placements, note=(note + ' ' + row['note']).strip(), two_posts=two)
                if 'children' in row['note']:
                    sign(store, R, s - 8, sd, 'children', .9, .8, 1.5, placements, note=row['note'])
        elif typ == 'barrier' and sub == 'concrete':
            for sd in sides:
                parapet(store, R, s - 10, s + max(length, 20) + 10, sd, placements)
        elif typ == 'barrier' and sub == 'railing':
            for sd in sides:
                railing(store, R, s - 8, s + 8, sd, placements)
        elif typ == 'fence':
            for sd in sides:
                railing(store, R, s - 15, s + max(length, 0) + 15, sd, placements, uvname='wood', d=7.0, hgt=1.1)
    nshrub = shrubs(store, R, blocked, rng, placements)
    tw = tower(R, placements)
    if extra is not None:
        extra(store, R, placements)

    # ---- serialise
    arrays, objects = {}, []
    LOD = LODS
    for (kind, cell), m in sorted(store.items()):
        if not m.count:
            continue
        v, n, uv, tri, mi = m.arrays()
        name = f'{PREFIX}_{kind}_{cell:03d}'
        lo, hi, sh = LOD[kind]
        objects.append(dict(name=name, kind=kind, lod_in=lo, lod_out=hi, cast_shadows=sh, tris=int(len(tri)), verts=int(len(v))))
        for k, a in (('v', v), ('n', n), ('uv', uv), ('tri', tri), ('mat', mi)):
            arrays[f'{name}__{k}'] = a
    v, n, uv, tri, mi = tw.arrays()
    objects.append(dict(name=f'{PREFIX}_TOWER_EXELBERG', kind='TOWER', lod_in=0, lod_out=9000, cast_shadows=True, tris=int(len(tri)), verts=int(len(v))))
    for k, a in (('v', v), ('n', n), ('uv', uv), ('tri', tri), ('mat', mi)):
        arrays[f'{PREFIX}_TOWER_EXELBERG__{k}'] = a
    np.savez_compressed(OUT_ / 'geometry.npz', **arrays)
    summary = defaultdict(int)
    for p in placements:
        summary[p['kind']] += 1
    rail_m = sum(p['s1'] - p['s0'] for p in placements if p['kind'] == 'guardrail')
    meta = dict(materials=MATS, objects=objects, summary=dict(summary), guardrail_m=rail_m, shrubs=nshrub,
                total_tris=sum(o['tris'] for o in objects), max_verts=max(o['verts'] for o in objects))
    (OUT_ / 'objects.json').write_text(json.dumps(meta, indent=2) + '\n')
    (OUT_ / 'placements.json').write_text(json.dumps(placements, indent=1, default=float) + '\n')
    print(json.dumps({k: meta[k] for k in ('summary', 'guardrail_m', 'shrubs', 'total_tris', 'max_verts')}), len(objects), 'objects')


if __name__ == '__main__':
    main()
