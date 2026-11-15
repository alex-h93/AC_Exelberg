#!/usr/bin/env python3
"""v010 route extension polyline from OpenStreetMap (offline; data/interim/osm/merged.json).

User (2026-11-15): extend the track to the roundabout at WGS84 48.2401990264944, 16.276531758839184 and finish at
its 2nd exit. Path: old route end (on Exelbergstraße way 1206002982) -> Exelbergstraße downhill (directed shortest
path on highway ways, oneway respected) -> one-way entry branch 689306071 -> roundabout ring (OSM junction=roundabout,
driven in way direction = counter-clockwise) past exit 1 (Neuwaldegger Straße towards Hütteldorf) -> exit 2
(way 9873331, Neuwaldegger Straße east) -> finish gate at the user's point projected onto the exit road ->
RUNOUT_M of the real road beyond (ends before the Alsbach bridge, way 26560067).
Output: data/processed/extension_v010/osm_extension.json (local EPSG:25833 - ORIGIN metres, polyline + facts).
"""
import heapq
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
OSM = ROOT / 'data/interim/osm/merged.json'
ROUTE = ROOT / 'data/processed/full_track_inputs/route.npz'
OUT = ROOT / 'data/processed/extension_v010'
ORIGIN = np.array([589500., 5346800.])
TARGET_WGS = (48.2401990264944, 16.276531758839184)
START_WAY, RING_ENTRY, EXIT_WAY = 1206002982, 291156235, 9873331
TAIL_WAYS = (9873331, 681269672, 555726609, 278650044)
RUNOUT_M = 100.0
DRIVABLE = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
            'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'}


def load():
    el = json.loads(OSM.read_text())['elements']
    t = Transformer.from_crs(4326, 25833, always_xy=True)
    nodes = {e['id']: np.array(t.transform(e['lon'], e['lat'])) - ORIGIN for e in el if e['type'] == 'node'}
    ways = {e['id']: e for e in el if e['type'] == 'way'}
    return nodes, ways, t


def graph(nodes, ways):
    g = {}
    for w in ways.values():
        tg = w.get('tags', {})
        if tg.get('highway') not in DRIVABLE:
            continue
        ns = [n for n in w['nodes'] if n in nodes]
        one = tg.get('oneway') == 'yes' or tg.get('junction') == 'roundabout'
        for a, b in zip(ns[:-1], ns[1:]):
            d = float(np.linalg.norm(nodes[a] - nodes[b]))
            g.setdefault(a, []).append((b, d, w['id']))
            if not one:
                g.setdefault(b, []).append((a, d, w['id']))
    return g


def dijkstra(g, src, dst):
    dist, prev, q = {src: 0.0}, {}, [(0.0, src)]
    while q:
        d, u = heapq.heappop(q)
        if u == dst:
            break
        if d > dist[u]:
            continue
        for v, w, wid in g.get(u, ()):
            if d + w < dist.get(v, np.inf):
                dist[v], prev[v] = d + w, (u, wid)
                heapq.heappush(q, (d + w, v))
    path, ways_used, u = [dst], [], dst
    while u != src:
        u, wid = prev[u]
        path.append(u)
        ways_used.append(wid)
    return path[::-1], ways_used[::-1], dist[dst]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    nodes, ways, t = load()
    g = graph(nodes, ways)
    end = np.load(ROUTE)['full_xy_25833_m'][-1] - ORIGIN
    sw = [n for n in ways[START_WAY]['nodes']]
    # old end lies inside segment k of the start way; continue in the downhill direction (towards node index 0)
    seg = [(k, np.linalg.norm(end - (nodes[a] + np.clip(np.dot(end - nodes[a], nodes[b] - nodes[a]) / np.dot(nodes[b] - nodes[a], nodes[b] - nodes[a]), 0, 1) * (nodes[b] - nodes[a]))))
           for k, (a, b) in enumerate(zip(sw[:-1], sw[1:]))]
    k = min(seg, key=lambda x: x[1])[0]
    old_dir = end - (np.load(ROUTE)['full_xy_25833_m'][-2] - ORIGIN)
    first = sw[k] if np.dot(nodes[sw[k]] - end, old_dir) > 0 else sw[k + 1]
    path, used, length = dijkstra(g, first, RING_ENTRY)
    # around the ring (way direction) until the exit way's first node
    exit_first = ways[EXIT_WAY]['nodes'][0]
    ring = []
    u = RING_ENTRY
    for _ in range(64):
        nxt = [(v, wid) for v, _, wid in g[u] if ways[wid].get('tags', {}).get('junction') == 'roundabout']
        assert len(nxt) == 1, ('ambiguous ring step', u, nxt)
        u, wid = nxt[0]
        ring.append(u)
        used.append(wid)
        if u == exit_first:
            break
    else:
        raise RuntimeError('exit not reached around the ring')
    # exits passed on the ring (ways leaving a ring node, not roundabout)
    exits = []
    for n in [RING_ENTRY] + ring:
        for v, _, wid in g.get(n, ()):
            tg = ways[wid].get('tags', {})
            if tg.get('junction') != 'roundabout':
                exits.append(dict(node=n, way=wid, name=tg.get('name'), destination=tg.get('destination')))
    assert exits[-1]['way'] == EXIT_WAY and len(exits) == 2, exits
    # beyond the ring: the explicit Neuwaldegger Straße chain (each way oriented to connect)
    tail = []
    for wid in TAIL_WAYS:
        ns = list(ways[wid]['nodes'])
        last = tail[-1] if tail else exit_first
        if ns[-1] == last:
            ns = ns[::-1]
        assert ns[0] == last, ('tail chain broken at way', wid)
        tail += ns[1:]
        used.append(wid)
    tx, ty = t.transform(TARGET_WGS[1], TARGET_WGS[0])
    target = np.array([tx, ty]) - ORIGIN
    pts = np.array([end] + [nodes[n] for n in path + ring + tail])
    pts = pts[np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 0.05]]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    s_exit = s[np.argmin(np.linalg.norm(pts - nodes[exit_first], axis=1))]
    best = None
    for j in range(len(pts) - 1):  # project the target onto the polyline AFTER the ring exit
        if s[j + 1] <= s_exit:
            continue
        a_, b_ = pts[j], pts[j + 1]
        q = np.clip(np.dot(target - a_, b_ - a_) / np.dot(b_ - a_, b_ - a_), 0, 1)
        c = a_ + q * (b_ - a_)
        dd = float(np.linalg.norm(target - c))
        if best is None or dd < best[0]:
            best = (dd, c, s[j] + q * np.linalg.norm(b_ - a_))
    dd, finish, s_fin = best
    assert dd < 15, ('target not on the exit road', dd)
    s_end = s_fin + RUNOUT_M
    assert s_end < s[-1], 'tail chain too short for the run-out'
    j = int(np.searchsorted(s, s_end))
    q = (s_end - s[j - 1]) / (s[j] - s[j - 1])
    pts = np.vstack([pts[:j], pts[j - 1] + q * (pts[j] - pts[j - 1])])
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    seg_s = [s_fin]
    out = dict(polyline_local_m=pts.tolist(), length_m=float(s[-1]), finish_local_m=finish.tolist(),
               finish_arclength_m=float(seg_s[0]), runout_m=float(s[-1] - seg_s[0]),
               target_local_m=target.tolist(), target_to_finish_m=float(np.linalg.norm(target - finish)),
               ring_nodes=[RING_ENTRY] + ring, ring_center_local_m=np.mean([nodes[n] for n in [RING_ENTRY] + ring + [ring[-1]]], 0).tolist(),
               ways=list(dict.fromkeys(used)), exits_passed=exits, ring_exit_arclength_m=float(s_exit), origin_25833=ORIGIN.tolist(), target_wgs84=TARGET_WGS,
               attribution='© OpenStreetMap contributors, ODbL', note=__doc__)
    (OUT / 'osm_extension.json').write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in out.items() if k not in ('polyline_local_m', 'note')}, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
