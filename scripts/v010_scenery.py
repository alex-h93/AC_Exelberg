#!/usr/bin/env python3
"""v010 scenery: v009 scenery (posts, chevrons, roofs, signs, buildings, junction stubs, shrubs, tower) on the
v010 skin/route (extension to the Neuwaldegg roundabout), plus visual-only roundabout geometry.

  * route + ground: data/processed/extension_v010/skin_v010.npz (identical to v009 before the cut)
  * guide posts: v003 positions moved by the v009 road field and re-grounded (as v009); no new posts on the
    extension (urban section, no reference footage)
  * OSM junction stubs only before the cut (s < s_cut); around the roundabout instead one draped asphalt surface:
    the full OSM ring (fitted circle, lane 7.3-14.2 m from the centre, from the BEV orthophoto) + every drivable OSM
    way within ARM_R m of the ring centre (width as v005 WIDTH, one-way 4.5 m), minus the drivable road +-3 m;
    0.05 m above the skin, 2 m cells; central-island kerb (concrete, 0.16 m) at 7.0-7.3 m. Visual only - the
    invisible +-6 m walls still bound the drivable route.
  * buildings: CHM heights from surface_v004, falling back to the v010 extension CHM
  * shrub band density from trees_v010.npz; no shrubs on the roundabout asphalt or (inside the patch area) on any
    other drivable OSM way (Neuwaldegger Strasse is a dual carriageway east of the ring), and none from
    URBAN_BEFORE_RING_M before the ring to the end (urban kerbs/sidewalks)
Output: data/processed/scenery_v010/
"""
import json
import sys
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v005_roadside as R5  # noqa: E402
import v006_buildings as B  # noqa: E402
import v007_scenery as S7  # noqa: E402
from v009_field import Field  # noqa: E402

EXT = ROOT / 'data/processed/extension_v010'
SKIN = EXT / 'skin_v010.npz'
OSM = ROOT / 'data/interim/osm/merged.json'
ARM_R, RING_IN, RING_OUT, CELL = 45.0, 7.3, 14.2, 2.0
LIFT = 0.05
URBAN_BEFORE_RING_M = 40.0  # no roadside shrub band from here on (roundabout, kerbs/sidewalks of Neuwaldegg)


def ring_and_arms():
    e = json.loads((EXT / 'osm_extension.json').read_text())
    el = json.loads(OSM.read_text())['elements']
    nodes = {x['id']: (x['lon'], x['lat']) for x in el if x['type'] == 'node'}
    T = Transformer.from_crs(4326, 25833, always_xy=True)
    org = np.array(e['origin_25833'])
    route_ways = set(e['ways'])
    rings, arms = [], []
    for w in el:
        if w['type'] != 'way':
            continue
        t = w.get('tags', {})
        hw = t.get('highway')
        if hw not in R5.WIDTH or hw in R5.SKIP_HW or t.get('area') == 'yes':
            continue
        ll = np.array([nodes[n] for n in w['nodes'] if n in nodes])
        if len(ll) < 2:
            continue
        xy = np.c_[T.transform(ll[:, 0], ll[:, 1])] - org
        (rings if t.get('junction') == 'roundabout' else arms).append((w['id'], hw, t, xy))
    near = [r for r in rings if np.linalg.norm(r[3] - np.array(e['ring_center_local_m']), axis=1).min() < 30]
    pts = np.vstack([r[3] for r in near])
    A = np.c_[2 * pts, np.ones(len(pts))]
    sol = np.linalg.lstsq(A, (pts ** 2).sum(1), rcond=None)[0]
    c = sol[:2]
    rad = float(np.sqrt(sol[2] + c @ c))
    resid = float(np.abs(np.linalg.norm(pts - c, axis=1) - rad).max())
    assert resid < 0.5 and 9 < rad < 13, ('ring fit', rad, resid)
    zone = Point(c).buffer(ARM_R, quad_segs=32)
    polys = [Point(c).buffer(RING_OUT, quad_segs=32).difference(Point(c).buffer(RING_IN, quad_segs=32))]
    used, roads = [], []
    for wid, hw, t, xy in arms:
        if wid in route_ways:
            continue
        line = LineString(xy)
        roads.append(line.buffer(2.25 if t.get('oneway') == 'yes' else R5.WIDTH[hw] / 2))
        if not line.intersects(zone):
            continue
        half = 2.25 if t.get('oneway') == 'yes' else R5.WIDTH[hw] / 2
        polys.append(line.buffer(half, cap_style='flat').intersection(zone))
        used.append(dict(way=wid, highway=hw, name=t.get('name', ''), oneway=t.get('oneway', ''), width_m=2 * half))
    return c, rad, resid, shapely.union_all(polys), used, shapely.union_all(roads)


def drape(m, R, poly, mat=2):
    x0, y0, x1, y1 = poly.bounds
    ntri = 0
    for gx in np.arange(np.floor(x0 / CELL) * CELL, x1, CELL):
        for gy in np.arange(np.floor(y0 / CELL) * CELL, y1, CELL):
            piece = poly.intersection(shapely.box(gx, gy, gx + CELL, gy + CELL))
            if piece.is_empty or piece.area < 1e-4:
                continue
            tris = shapely.constrained_delaunay_triangles(piece)
            for tr in shapely.get_parts(tris):
                p = np.asarray(tr.exterior.coords)[:3]
                if abs(shapely.area(tr)) < 1e-5:
                    continue
                if (p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[1, 1] - p[0, 1]) * (p[2, 0] - p[0, 0]) < 0:
                    p = p[::-1]
                v = np.c_[p, [R.z(q) + LIFT for q in p]]
                nrm = np.cross(v[1] - v[0], v[2] - v[0]); nrm /= np.linalg.norm(nrm)
                m.raw(v, np.tile(nrm, (3, 1)), p / 4.0, np.array([[0, 1, 2]]), mat)
                ntri += 1
    return ntri


def kerb(m, R, c, r_in=7.0, r_out=7.3, h=0.16, n=48):
    for k in range(n):
        a0, a1 = 2 * np.pi * k / n, 2 * np.pi * (k + 1) / n
        am = (a0 + a1) / 2
        rm = (r_in + r_out) / 2
        ctr = c + rm * np.array([np.cos(am), np.sin(am)])
        radial = np.r_[np.cos(am), np.sin(am), 0.0]
        tang = np.r_[-np.sin(am), np.cos(am), 0.0]
        z = R.z(ctr)
        half_len = rm * (a1 - a0) / 2 + 0.03
        m.box(np.r_[ctr, z + h / 2 - 0.04], [radial, tang, R5.UP], [(r_out - r_in) / 2, half_len, h / 2 + 0.04], 'concrete', 0)
    return n


class Heights2(B.Heights):
    """surface_v004 CHM, else the v010 extension CHM (both BEV, EPSG:3035)."""
    def __init__(self):
        super().__init__()
        import tifffile
        s = json.loads((EXT / 'surface_summary.json').read_text())
        self.ext = (s['transform'], tifffile.imread(EXT / 'chm_3035.tif'))
        self.fallbacks = 0

    def pixels(self, lonlat):
        v = super().pixels(lonlat)
        if len(v):
            return v
        keep = self.x0, self.y0, self.sx, self.sy, self.chm
        (self.x0, self.y0, self.sx, self.sy), self.chm = self.ext
        try:
            v = super().pixels(lonlat)
        finally:
            self.x0, self.y0, self.sx, self.sy, self.chm = keep
        self.fallbacks += bool(len(v))
        return v


STATE = {}


def add_posts_v010(store, R, placements):
    pl = json.loads(S7.POSTS.read_text())['placements']
    d = np.load(ROOT / 'data/processed/road_v009/smoothed_skin.npz')
    F = Field(d['designed_xyz_v008_m'], d['designed_xyz_m'])
    xy1 = F.displace(np.array([q['ground_xyz_m'][:2] for q in pl], float))
    for q, (x, y) in zip(pl, xy1):
        s, off = q['arclength_m'], q['offset_left_m']
        pos, t, n = R.frame(s)
        S7.leitpflock(R5.bucket(store, 'POST', s), R, np.array([x, y, R.z((x, y)) - 0.02]), t, np.sign(off) * n)
    placements.append(dict(kind='guide_posts', count=len(pl), source='v003 posts.json moved by the v009 road field, re-grounded on the v010 skin'))
    # roundabout
    c, rad, resid, poly, used, _ = STATE['rbt']
    s_r, _ = R.nearest(c)
    m = R5.bucket(store, 'JUNC', s_r)
    road = LineString(R.p[STATE['ic']:, :2]).buffer(3.0, cap_style='flat')
    surf = poly.difference(road)
    ntri = drape(m, R, surf)
    nk = kerb(R5.bucket(store, 'JUNC', s_r), R, c)
    placements.append(dict(kind='roundabout', centre_local=c.round(2).tolist(), ring_centreline_radius_m=round(rad, 2), fit_resid_m=round(resid, 3),
                           lane_m=[RING_IN, RING_OUT], arm_radius_m=ARM_R, arms=used, asphalt_m2=round(surf.area, 1), triangles=ntri,
                           kerb_segments=nk, source='OSM ring + ways; widths from the BEV orthophoto / v005 WIDTH', collision=False))
    STATE['rbt_info'] = placements[-1]
    if STATE.get('hook'):  # v011: extra geometry (urban furniture) with the same store/route
        STATE['hook'](store, R, placements)
    return len(pl)


def main(out=None, prefix='V010', hook=None):
    STATE['hook'] = hook
    rt = np.load(EXT / 'route.npz')
    P = rt['designed_xyz_m']
    ic = int(rt['i_cut'])
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    STATE['ic'] = ic
    STATE['rbt'] = ring_and_arms()
    B_xy = np.load(EXT / 'patch_domain.npz')['B_xy']
    i_town = int(np.searchsorted(s, s[np.argmin(np.linalg.norm(P[:, :2] - STATE['rbt'][0], axis=1))] - URBAN_BEFORE_RING_M))
    rbt_zone = shapely.union_all([STATE['rbt'][3], STATE['rbt'][5].intersection(shapely.Polygon(B_xy)),
                                  LineString(P[i_town:, :2]).buffer(12.0)]).buffer(1.5)
    R5.SKIN = SKIN
    R5.TREES = EXT / 'trees_v010.npz'
    orig_stubs = R5.osm_stubs
    R5.osm_stubs = lambda R: [j for j in orig_stubs(R) if j['s'] < s[ic]]
    orig_avoid = B.make_avoid

    def make_avoid(fps, *a, **k):
        f = orig_avoid(fps, *a, **k)
        return lambda q: f(q) or bool(shapely.contains_xy(rbt_zone, q[0], q[1]))
    B.make_avoid = make_avoid
    hts = {}
    orig_heights = B.Heights

    def H2():
        hts['h'] = Heights2()
        return hts['h']
    B.Heights = H2
    S7.add_posts = add_posts_v010
    out = ROOT / 'data/processed/scenery_v010' if out is None else Path(out)
    S7.main(prefix=prefix, out=out)
    B.Heights = orig_heights
    info = dict(roundabout=STATE['rbt_info'], building_height_fallbacks_to_extension_chm=hts['h'].fallbacks, s_cut_m=float(s[ic]), note=__doc__)
    (out / 'extension.json').write_text(json.dumps(info, indent=2, default=float) + '\n')
    print(json.dumps({k: v for k, v in info.items() if k != 'note'}, default=float))


if __name__ == '__main__':
    main()
