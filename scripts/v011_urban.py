#!/usr/bin/env python3
"""v011 Neuwaldegg roundabout furniture (visual only), shared by the forward and the reverse track scenery.

Placed in WORLD coordinates from OpenStreetMap (data/interim/osm/merged.json: crossing / give_way nodes, ways) and the
user's reference screenshots (data/raw/Marswiese_start.png, Marswiese_start_1st_exit.png; reference only):
  * zebra crossings at the 6 OSM crossing nodes (both Neuwaldegger Strasse carriageways, both Exelbergstrasse
    branches, both south-west branches): 0.5 m stripes / 0.5 m gaps, 3 m deep, across the carriageway; bicycle
    crossing squares beside the two Neuwaldegger Strasse zebras (screenshot 1); on the current track's road 0.015 m
    above the asphalt, on visual arms 0.012 m above the draped arm asphalt
  * pedestrian-crossing signs both sides before every zebra (+ bicycle-crossing sign at Neuwaldegger Strasse), and
    end-of-short-term-parking-zone sign + text plate at the westbound start road (screenshot 1)
  * yield signs at the 3 OSM give_way nodes (ring entries), right-hand side
  * roundabout island: dense low shrubs (green centre, screenshot 1) and a pass-right sign on a two-post frame facing
    each entry
  * Exelbergstrasse splitter island: keep-right sign + red/white marker at the ring-side tip and the 'Tulln ->' board,
    facing traffic leaving the ring (screenshot 2); deer-crossing warning + plate on the right further up
Sign geometry: Austrian sizes approximated (0.6 m squares, 0.75 m triangles); posts as v005.
"""
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

import v005_roadside as R5
import v011_textures as U
from v005_textures import uv_rect

ROOT = Path(__file__).resolve().parents[1]
OSM = ROOT / 'data/interim/osm/merged.json'
ORIGIN = np.array([589500.0, 5346800.0])
CROSSINGS = (2163188183, 5361078633, 4042119305, 6466384849, 1743287357, 5361078636)
BIKE = (2163188183, 5361078633)
KURZPARK = (5361078633,)
GIVE_WAY = (11008636112, 6466384848, 11008636113)
ENTRY_BRANCH = (689306071,)                 # Exelbergstrasse one-way into the ring
EXIT_BRANCH = (26560097, 689306072)         # Exelbergstrasse one-way out of the ring (reverse-track route)
UP = R5.UP
BACK = {'ped_crossing': 'back_rect', 'bike_crossing': 'back_rect', 'kurzpark_end': 'back_rect', 'kurzpark_text': 'back_rect',
        'plate_text': 'back_rect', 'tulln': 'back_rect', 'yield': 'back_tri', 'deer': 'back_tri',
        'keep_right_diag': 'back_round', 'pass_right': 'back_round'}


class Osm:
    def __init__(self):
        el = json.loads(OSM.read_text())['elements']
        T = Transformer.from_crs(4326, 25833, always_xy=True)
        ns = [x for x in el if x['type'] == 'node']
        xy = np.c_[T.transform([n['lon'] for n in ns], [n['lat'] for n in ns])] - ORIGIN
        self.xy = {n['id']: xy[i] for i, n in enumerate(ns)}
        self.ways = {w['id']: w for w in el if w['type'] == 'way'}

    def line(self, wid):
        return np.array([self.xy[i] for i in self.ways[wid]['nodes']])

    def carriageway(self, node):
        for w in self.ways.values():
            t = w.get('tags', {})
            if node in w['nodes'] and t.get('highway') in R5.WIDTH and t.get('junction') != 'roundabout':
                return w
        raise KeyError(node)

    def direction(self, w, node):
        i = w['nodes'].index(node)
        a, b = self.xy[w['nodes'][max(i - 1, 0)]], self.xy[w['nodes'][min(i + 1, len(w['nodes']) - 1)]]
        d = b - a
        return d / np.linalg.norm(d)


def half_width(w):
    return 2.25 if w.get('tags', {}).get('oneway') == 'yes' else R5.WIDTH[w['tags']['highway']] / 2


class Urban:
    def __init__(self, store, R, placements, mat_urban, ring_c, lift_arm):
        self.store, self.R, self.pl, self.mu, self.c, self.lift_arm = store, R, placements, mat_urban, np.asarray(ring_c), lift_arm
        self.o = Osm()
        self.s_ring, _ = R.nearest(self.c)
        self.counts = dict(zebra_stripes=0, bike_squares=0, signs=0, island_shrubs=0)

    # ---------------------------------------------------------------- helpers
    def on_route(self, xy, tol=3.5):
        return self.R.nearest(xy)[1] < tol

    def lateral(self, xy, osm_half):
        """Sign offset from a carriageway centre: OSM half width + 0.8 m, but outside the drivable gravel when the
        carriageway is the current track's road."""
        return 3.95 if self.on_route(xy) else osm_half + 0.8

    def ground(self, xy, lift):
        return self.R.z(np.asarray(xy, float)) + lift

    def flat_quad(self, m, centre, along, across, half_a, half_c, lift):
        pts = [centre - along * half_a - across * half_c, centre + along * half_a - across * half_c,
               centre + along * half_a + across * half_c, centre - along * half_a + across * half_c]
        p3 = [np.r_[p, self.ground(p, lift)] for p in pts]
        if np.cross(np.r_[along, 0], np.r_[across, 0])[2] < 0:
            p3 = p3[::-1]
        u0, v0, u1, v1 = uv_rect('white', 6)
        m.quad(p3, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], 0, normal=UP)

    def plate(self, m, centre, facing, w, h, cell):
        """Double-sided plate: front from the urban atlas, back from the v005 atlas (yield: back triangle upside down)."""
        right = np.cross(UP, facing)
        f = centre + facing * 0.012
        u0, v0, u1, v1 = U.uv2(cell)
        pts = [f - right * w / 2 - UP * h / 2, f + right * w / 2 - UP * h / 2, f + right * w / 2 + UP * h / 2, f - right * w / 2 + UP * h / 2]
        m.quad(pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], self.mu, normal=facing)
        b = centre - facing * 0.012
        u0, v0, u1, v1 = uv_rect(BACK[cell], 1)
        uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)] if cell != 'yield' else [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]
        pts = [b + right * w / 2 - UP * h / 2, b - right * w / 2 - UP * h / 2, b - right * w / 2 + UP * h / 2, b + right * w / 2 + UP * h / 2]
        m.quad(pts, uv, 0, normal=-facing)

    def sign(self, xy, face2, plates, note, two_posts=False):
        """plates: [(cell, w, h, bottom, sideways_offset)]; face2: 2D unit vector the fronts face."""
        facing = np.r_[face2, 0.0]
        base = np.r_[xy, self.R.z(np.asarray(xy, float))]
        m = R5.bucket(self.store, 'SIGN', self.R.nearest(xy)[0])
        right = np.cross(UP, facing)
        top = 0.0
        for cell, w, h, bottom, side in plates:
            self.plate(m, base + right * side + UP * (bottom + h / 2), facing, w, h, cell)
            top = max(top, bottom + h * 0.85)
        offs = [-0.32, 0.32] if two_posts else sorted({p[4] for p in plates})
        for o in offs:
            b0 = base + right * o - facing * 0.03 - UP * 0.3
            R5.post(m, b0, b0 + UP * (top + 0.3))
        self.counts['signs'] += 1
        self.pl.append(dict(kind='urban_sign', cells=[p[0] for p in plates], xy=np.round(xy, 2).tolist(),
                            facing_deg=round(float(np.degrees(np.arctan2(face2[1], face2[0]))), 1), note=note, source='OSM + user screenshot'))

    # ---------------------------------------------------------------- items
    def crossings(self):
        for node in CROSSINGS:
            w = self.o.carriageway(node)
            p, d = self.o.xy[node], self.o.direction(w, node)
            nrm = np.array([-d[1], d[0]])
            on = self.on_route(p)
            W = 6.0 if on else 2 * half_width(w)
            lift = 0.015 if on else self.lift_arm
            m = R5.bucket(self.store, 'JUNC', self.R.nearest(p)[0])
            for x in np.arange(-W / 2 + 0.35, W / 2 - 0.3, 1.0):
                self.flat_quad(m, p + nrm * x, d, nrm, 1.5, 0.25, lift)
                self.counts['zebra_stripes'] += 1
            away = 1.0 if (p - self.c) @ d > 0 else -1.0  # side of the zebra away from the ring
            if node in BIKE:
                for x in np.arange(-W / 2 + 0.4, W / 2 - 0.3, 0.9):
                    self.flat_quad(m, p + d * away * 2.4 + nrm * x, d, nrm, 0.25, 0.25, lift)
                    self.counts['bike_squares'] += 1
            # signs before the zebra for the traffic of this carriageway (one-way: way direction)
            ow = w['tags'].get('oneway') == 'yes'
            for trav in ([d] if ow else [d, -d]):
                tn = np.array([trav[1], -trav[0]])  # right of travel
                q = p - trav * 1.8
                lat = self.lateral(q, half_width(w))
                for sd, label in ((1, 'right'), (-1, 'left')):
                    plates = [('ped_crossing', .6, .6, 2.0, 0.0)]
                    if node in BIKE:
                        plates.append(('bike_crossing', .6, .6, 1.35, 0.0))
                    if node in KURZPARK:
                        plates += [('kurzpark_end', .55, .55, 2.05, -0.62 * sd), ('kurzpark_text', .55, .5, 1.5, -0.62 * sd)]
                    self.sign(q + tn * sd * lat, -trav, plates, f'zebra {node} {label}')
            self.pl.append(dict(kind='zebra', node=node, way=w['id'], width_m=W, on_track_road=bool(on), bike=node in BIKE, source='OSM highway=crossing'))

    def give_way(self):
        for node in GIVE_WAY:
            w = self.o.carriageway(node)
            p, d = self.o.xy[node], self.o.direction(w, node)
            tn = np.array([d[1], -d[0]])
            self.sign(p + tn * self.lateral(p, half_width(w)), -d, [('yield', .75, .66, 1.55, 0.0)], f'give_way {node}')

    def island(self, rng):
        r_shrub = 5.3
        m = R5.bucket(self.store, 'SHRUB', self.s_ring)
        n = 0
        for _ in range(400):
            q = self.c + rng.uniform(-r_shrub, r_shrub, 2)
            if np.linalg.norm(q - self.c) > r_shrub or n >= 46:
                continue
            h, cr = rng.uniform(0.7, 1.3), rng.uniform(0.6, 0.95)
            tr = R5.TG.tree(3, h, cr, int(rng.integers(1 << 30)), detail=0.8)
            a = rng.uniform(0, 2 * np.pi)
            rot = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
            m.raw(tr['v'] @ rot.T + np.r_[q, self.R.z(q) - 0.05], tr['n'] @ rot.T, tr['uv'], tr['tri'], np.where(tr['mat'] == 0, 4, 5))
            n += 1
        self.counts['island_shrubs'] = n
        for node in GIVE_WAY:  # pass-right sign at the island edge facing each entry
            u = self.o.xy[node] - self.c
            u /= np.linalg.norm(u)
            self.sign(self.c + u * 6.2, u, [('pass_right', .6, .6, 0.55, 0.0)], f'island pass-right towards entry {node}', two_posts=True)

    def splitter(self):
        ent = np.vstack([self.o.line(w) for w in ENTRY_BRANCH])
        ext = np.vstack([self.o.line(w)[(1 if i else 0):] for i, w in enumerate(EXIT_BRANCH)])  # ring -> NW
        dense = lambda P: np.vstack([np.linspace(a, b, max(2, int(np.linalg.norm(b - a) / 0.25))) for a, b in zip(P[:-1], P[1:])])
        E, X = dense(ent), dense(ext)
        # island centre line: midpoints entry<->exit; keep points where the gap leaves >= 1.6 m of island
        k = np.argmin(np.linalg.norm(E[:, None] - X[None], axis=2), axis=1)
        gap = np.linalg.norm(E - X[k], axis=1)
        mid = (E + X[k]) / 2
        dr = np.linalg.norm(mid - self.c, axis=1)
        ok = (gap >= 2 * 2.25 + 1.6) & (dr > 15.5)
        assert ok.any(), 'no splitter island found'
        tip = mid[ok][np.argmin(dr[ok])]
        dX = X[-1] - X[0]; dX /= np.linalg.norm(dX)   # exit travel direction (towards Exelberg)
        self.sign(tip, -dX, [('keep_right_diag', .6, .6, 1.25, 0.0)], 'splitter tip keep-right (screenshot 2)')
        # red/white marker below (v005 atlas red chevron, narrow)
        m = R5.bucket(self.store, 'SIGN', self.R.nearest(tip)[0])
        c3 = np.r_[tip, self.R.z(tip)] + UP * 0.75 - np.r_[dX, 0] * 0.03
        R5.Mesh.plate(m, c3, np.r_[-dX, 0.0], UP, 0.25, 0.5, 'chev_red_R', 'back_rect')
        far = mid[ok][np.argmin(np.abs(dr[ok] - (dr[ok].min() + 4.5)))]
        self.sign(far, -dX, [('tulln', 1.4, .35, 2.4, 0.0)], 'Tulln direction board (screenshot 2)')
        # deer warning on the right of the exit traffic, ~20 m past the zebra
        z = self.o.xy[4042119305]
        q = z + dX * 20.0
        tn = np.array([dX[1], -dX[0]])
        self.sign(q + tn * self.lateral(q, 3.0), -dX, [('deer', .75, .66, 1.75, 0.0), ('plate_text', .6, .3, 1.32, 0.0)],
                  'deer-crossing warning (screenshot 2)')
        self.pl.append(dict(kind='splitter_island', tip=np.round(tip, 2).tolist(), tulln=np.round(far, 2).tolist(),
                            min_gap_m=round(float(gap[ok].min()), 2)))

    def run(self, rng):
        self.crossings()
        self.give_way()
        self.island(rng)
        self.splitter()
        self.pl.append(dict(kind='urban_summary', **self.counts))
        return self.counts
