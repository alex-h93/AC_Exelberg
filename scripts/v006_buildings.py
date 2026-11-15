#!/usr/bin/env python3
"""v006 buildings: OpenStreetMap footprints extruded to heights from the BEV laser-scan CHM (nDSM).

Footprints: OSM building ways (data/raw/osm/map_*.osm), EPSG:25833 local frame (origin 589500/5346800).
Kept when: every vertex lies on the final ground skin (v003 repaired_skin), no edge comes closer than
MIN_ROAD_D to the centreline, area >= 6 m2, not an open/unfinished structure (roof, carport, construction).
Heights: CHM pixels (1 m, EPSG:3035) inside the footprint -> eave ~ p25, ridge ~ p95; OSM height /
building:levels override; clamped to plausible ranges (trees overhanging roofs inflate the CHM).
Shapes: near-rectangular footprints (area / oriented-box area >= RECT_MIN) with a measurable ridge get a
gable roof along the long axis with 0.4 m overhang; others get walls on the true outline + a flat roof.
These are approximations from public footprints and a surface model, NOT surveyed building models.
"""
import glob
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = np.array([589500.0, 5346800.0])
MAX_D, MIN_ROAD_D, RECT_MIN, OVER = 190.0, 7.0, 0.85, 0.4
SKIP = {'roof', 'carport', 'construction', 'greenhouse'}
SMALL = {'garage', 'shed', 'hut', 'farm_auxiliary', 'service'}
FACADES = ('facade_white', 'facade_cream', 'facade_ochre')
BMATS = ('facade_white', 'facade_cream', 'facade_ochre', 'facade_plain', 'roof_red', 'roof_dark')


# ------------------------------------------------------------------ footprints
def load_footprints():
    T = Transformer.from_crs(4326, 25833, always_xy=True)
    nodes, ways = {}, {}
    for f in sorted(glob.glob(str(ROOT / 'data/raw/osm/map_*.osm'))):
        r = ET.parse(f).getroot()
        for n in r.iter('node'):
            nodes[n.get('id')] = (float(n.get('lon')), float(n.get('lat')))
        for w in r.iter('way'):
            tags = {t.get('k'): t.get('v') for t in w.findall('tag')}
            if 'building' in tags:
                ways[w.get('id')] = ([nd.get('ref') for nd in w.findall('nd')], tags)
    out = []
    for wid, (refs, tags) in sorted(ways.items()):
        if tags['building'] in SKIP or len(refs) < 4 or refs[0] != refs[-1] or any(r not in nodes for r in refs):
            continue
        ll = np.array([nodes[r] for r in refs[:-1]])
        x, y = T.transform(ll[:, 0], ll[:, 1])
        p = clean(np.c_[x, y] - ORIGIN)
        if p is None or area(p) < 6.0:
            continue
        out.append(dict(way=wid, tags=tags, poly=p, lonlat=ll))
    return out


def area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def clean(p):
    """CCW, no repeated / near-collinear vertices."""
    if area(p) < 0:
        p = p[::-1]
    for _ in range(3):
        keep = []
        n = len(p)
        for i in range(n):
            a, b, c = p[i - 1], p[i], p[(i + 1) % n]
            if np.linalg.norm(b - a) < 0.3:
                continue
            u, v = b - a, c - b
            cr = abs(u[0] * v[1] - u[1] * v[0]) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12)
            if cr < 0.02 and np.dot(u, v) > 0:
                continue
            keep.append(i)
        p = p[keep]
        if len(p) < 3:
            return None
    return p


def inside(pts, poly):
    """Vectorised even-odd point-in-polygon. pts (N,2)."""
    x, y = pts[:, 0][:, None], pts[:, 1][:, None]
    a, b = poly, np.roll(poly, -1, axis=0)
    cond = (a[:, 1] > y) != (b[:, 1] > y)
    xi = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1] + 1e-12)
    return ((cond & (x < xi)).sum(1) % 2) == 1


def obb(p):
    """Minimum-area oriented rectangle over polygon edge directions -> centre, e1 (long), e2, half L, half W."""
    best = None
    for i in range(len(p)):
        e = p[(i + 1) % len(p)] - p[i]
        e = e / (np.linalg.norm(e) + 1e-12)
        f = np.array([-e[1], e[0]])
        a, b = p @ e, p @ f
        A = (a.max() - a.min()) * (b.max() - b.min())
        if best is None or A < best[0]:
            best = (A, e, f, a, b)
    A, e, f, a, b = best
    c = e * (a.max() + a.min()) / 2 + f * (b.max() + b.min()) / 2
    hl, hw = (a.max() - a.min()) / 2, (b.max() - b.min()) / 2
    if hw > hl:
        e, f, hl, hw = f, -e, hw, hl
    return c, e, f, hl, hw, A


class Heights:
    def __init__(self):
        s = json.loads((ROOT / 'data/processed/surface_v004/summary.json').read_text())
        self.x0, self.y0, self.sx, self.sy = s['transform']
        self.chm = tifffile.imread(ROOT / 'data/processed/surface_v004/chm_400_3035.tif')
        self.T = Transformer.from_crs(4326, 3035, always_xy=True)

    def pixels(self, lonlat):
        x, y = self.T.transform(lonlat[:, 0], lonlat[:, 1])
        c, r = (np.asarray(x) - self.x0) / self.sx, (self.y0 - np.asarray(y)) / self.sy
        c0, r0 = int(math.floor(c.min())) - 1, int(math.floor(r.min())) - 1
        c1, r1 = int(math.ceil(c.max())) + 2, int(math.ceil(r.max())) + 2
        H, W = self.chm.shape
        if c0 < 0 or r0 < 0 or c1 > W or r1 > H:
            return np.empty(0)
        im = Image.new('L', (c1 - c0, r1 - r0), 0)
        ImageDraw.Draw(im).polygon(list(zip((c - c0).tolist(), (r - r0).tolist())), fill=1)
        m = np.asarray(im, bool)
        v = self.chm[r0:r1, c0:c1][m]
        return v[v != -9999].astype(float)


def h01(s, k=0):
    return int(hashlib.sha1(f'{s}:{k}'.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def num(tags, k):
    try:
        return float(str(tags.get(k, '')).replace('m', '').strip())
    except ValueError:
        return None


def measure(b, hts):
    """-> eave, ridge (m above ground), source string."""
    tags, small = b['tags'], b['tags']['building'] in SMALL or abs(area(b['poly'])) < 30
    hw = obb(b['poly'])[4]
    v = hts.pixels(b['lonlat'])
    if len(v) >= 4 and np.percentile(v, 80) > 1.5:
        eave, ridge, src = float(np.percentile(v, 25)), float(np.percentile(v, 95)), 'chm'
    else:
        eave, ridge, src = (2.6, 3.4, 'default_small') if small else (5.6, 5.6 + 0.6 * hw, 'default')
    lv, ht = num(tags, 'building:levels'), num(tags, 'height')
    if ht:
        ridge, src = ht, src + '+osm_height'
        eave = min(eave, ridge)
    if lv:
        eave, src = 3.0 * lv + 0.4, src + '+osm_levels'
    eave = float(np.clip(eave, 2.3 if small else 2.8, 4.0 if small else 13.0))
    ridge = float(np.clip(ridge, eave, eave + min(1.0 * hw, 7.0)))  # <= ~45 deg pitch; trees inflate CHM
    return eave, ridge, src


# ------------------------------------------------------------------ geometry
def ear_clip(p):
    idx = list(range(len(p)))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = p[i0], p[i1], p[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-9:
                continue
            others = [j for j in idx if j not in (i0, i1, i2)]
            if others and inside(p[others], np.array([a, b, c])).any():
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            return None
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def tri_raw(m, pts, uv, mat, normal):
    pts = np.asarray(pts, float)
    if np.dot(np.cross(pts[1] - pts[0], pts[2] - pts[0]), normal) < 0:
        pts, uv = pts[[0, 2, 1]], [uv[0], uv[2], uv[1]]
    m.raw(pts, np.tile(np.asarray(normal, float) / np.linalg.norm(normal), (3, 1)), uv, [[0, 1, 2]], mat)


def walls(m, poly, zb, zt, zg, mat):
    u = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        L = float(np.linalg.norm(b - a))
        pts = [(*a, zb), (*b, zb), (*b, zt), (*a, zt)]
        vb, vt = (zb - zg) / 6.0, (zt - zg) / 6.0
        m.quad(pts, [(u, vb), (u + L / 6, vb), (u + L / 6, vt), (u, vt)], mat)
        u += L / 6


def roof_quad(m, pts, mat, along, up_dir):
    """Double-sided roof plane; uv in 2 m tiles (u along ridge, v up the slope)."""
    pts = np.asarray(pts, float)
    uv = [((q - pts[0]) @ along / 2.0, (q - pts[0]) @ up_dir / 2.0) for q in pts]
    nrm = np.cross(pts[1] - pts[0], pts[3] - pts[0])
    if nrm[2] < 0:
        pts, uv = pts[::-1], uv[::-1]
    m.quad(pts, uv, mat)
    m.quad(pts[::-1], uv[::-1], mat)  # underside of the overhang


def building(m, b, zg, zb, eave, ridge, MI):
    p = b['poly']
    c, e1, e2, hl, hw, A = obb(p)
    rect = abs(area(p)) / A
    small = b['tags']['building'] in SMALL or abs(area(p)) < 30
    fac = MI['facade_plain'] if small else MI[FACADES[int(h01(b['way']) * 3) % 3]]
    rc = b['tags'].get('roof:colour', '').lower()
    dark = rc in ('grey', 'gray', 'black', 'darkgrey', 'anthracite', '#333333', '#555555') or (not rc and h01(b['way'], 1) < 0.3)
    roof_m = MI['roof_dark' if dark else 'roof_red']
    zE, zR = zg + eave, zg + ridge
    shape = b['tags'].get('roof:shape', '')
    gable = rect >= RECT_MIN and ridge - eave > 1.2 and hw <= 9.0 and shape in ('', 'gabled', 'hipped', 'pitched')
    if gable:
        corners = np.array([c - e1 * hl - e2 * hw, c + e1 * hl - e2 * hw, c + e1 * hl + e2 * hw, c - e1 * hl + e2 * hw])
        walls(m, corners, zb, zE, zg, fac)
        for s in (-1, 1):  # gable triangles at the short ends
            base = c + s * e1 * hl
            pa, pb = base - e2 * hw, base + e2 * hw
            top = np.r_[base, zR]
            tri_raw(m, [np.r_[pa, zE], np.r_[pb, zE], top],
                    [(0, (zE - zg) / 6), (2 * hw / 6, (zE - zg) / 6), (hw / 6, (zR - zg) / 6)], fac, np.r_[s * e1, 0])
        drop = OVER * (zR - zE) / hw
        for s in (-1, 1):
            out = np.r_[s * e2, 0.0]
            e = np.r_[e1, 0.0]
            eave_line = np.r_[c + s * e2 * (hw + OVER), zE - drop]
            ridge_line = np.r_[c, zR]
            pts = [eave_line - e * (hl + OVER), eave_line + e * (hl + OVER), ridge_line + e * (hl + OVER), ridge_line - e * (hl + OVER)]
            up_dir = (ridge_line - eave_line) / np.linalg.norm(ridge_line - eave_line)
            roof_quad(m, pts, roof_m, e, up_dir)
        kind = 'gable'
    else:
        walls(m, p, zb, zE, zg, fac)
        tris = ear_clip(p)
        if tris is None:
            return None
        cap = MI['roof_dark']
        v = np.c_[p, np.full(len(p), zE + 0.02)]
        m.raw(v, np.tile([0, 0, 1.0], (len(p), 1)), p / 2.0, np.array(tris), cap)
        kind = 'flat'
    return dict(shape=kind, rect=round(rect, 3), facade=[k for k, i in MI.items() if i == fac][0],
                roof=[k for k, i in MI.items() if i == (roof_m if gable else MI['roof_dark'])][0])


def make_avoid(fps, buffer=2.0):
    """AVOID hook for shrubs: True inside (bbox-buffered) footprints."""
    boxes = np.array([np.r_[f['poly'].min(0) - buffer, f['poly'].max(0) + buffer] for f in fps])

    def avoid(q):
        q = np.asarray(q, float)[:2]
        hit = np.nonzero((boxes[:, 0] <= q[0]) & (q[0] <= boxes[:, 2]) & (boxes[:, 1] <= q[1]) & (q[1] <= boxes[:, 3]))[0]
        return len(hit) > 0
    return avoid


def add_buildings(store, R, placements, fps, MI, bucket):
    hts = Heights()
    stats = dict(candidates=len(fps), kept=0, far=0, near_road=0, off_skin=0, failed=0)
    for b in fps:
        p = b['poly']
        dens = np.concatenate([np.linspace(p[i], p[(i + 1) % len(p)], 6) for i in range(len(p))])
        d = np.min(np.linalg.norm(R.p[None, :, :2] - dens[:, None], axis=2), axis=1)
        if d.min() > MAX_D:
            stats['far'] += 1; continue
        if d.min() < MIN_ROAD_D or inside(R.p[:, :2], p).any():
            stats['near_road'] += 1; continue
        try:
            zs = np.array([R.ground.sample(q) for q in dens])
        except (RuntimeError, ValueError):  # v010: ValueError = inside the grid but outside the skin
            stats['off_skin'] += 1; continue
        zg = float(np.median(zs))
        zb = float(zs.min()) - 0.3
        eave, ridge, src = measure(b, hts)
        s, _ = R.nearest(p.mean(0))
        info = building(bucket(store, 'BLDG', s), b, zg, zb, eave, ridge, MI)
        if info is None:
            stats['failed'] += 1; continue
        stats['kept'] += 1
        placements.append(dict(kind='building', way=b['way'], osm_type=b['tags']['building'], s=round(s, 1),
                               min_road_d=round(float(d.min()), 1), area_m2=round(abs(area(p)), 1), eave_m=round(eave, 2),
                               ridge_m=round(ridge, 2), height_source=src, **info))
    return stats
