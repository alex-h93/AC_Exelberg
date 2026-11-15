#!/usr/bin/env python3
"""v011 REVERSE track: route extension in forward parametrisation (offline, .venv; data/interim/osm/merged.json).

User (2026-11-15): "Add a second track ... the same as this one, but in the other direction. The start is where this
screenshot is taken" (data/raw/Marswiese_start.png: Neuwaldegger Strasse WESTBOUND carriageway, ~12 m before the
zebra crossing, roundabout ahead) and "right after the start we take the first exit" (Exelbergstrasse, "Tulln").
Driving direction: start -> westbound carriageway (way 555726612) -> ring counter-clockwise (way 278650047) ->
first exit = Exelbergstrasse one-way exit branch (26560097, 689306072) -> Exelbergstrasse -> ... -> Koenigstetten.
The road pipeline (v010_route .. v010_patch_build) is built in FORWARD parametrisation (old start -> extension end), so
this script writes the v010 extension polyline up to the branch split (node at the north end of 689306072) followed
by the reverse-track ways traversed backwards, ending END_BEHIND_M behind the spawn point.
Output: data/processed/extension_v011r/osm_extension.json (+ symlink-free copies of the v010 rasters it needs).
"""
import json
import shutil
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data/processed/extension_v010'
OUT = ROOT / 'data/processed/extension_v011r'
OSM = ROOT / 'data/interim/osm/merged.json'
SPLIT = (5216.3, -2998.7)           # node where Exelbergstrasse splits into the one-way branches
CHAIN = [555726612, 278650047, 26560097, 689306072]  # driving order of the reverse track (each traversed in way direction)
CROSSING_E = 5361078633             # zebra on the westbound carriageway (in front of the start screenshot)
SPAWN_BEFORE_CROSSING_M = 12.0
END_BEHIND_M = 10.0                 # spawn sits 10 m from the route end (as the forward track)
COPY = ('dtm_3035.tif', 'dsm_3035.tif', 'chm_3035.tif', 'surface_summary.json', 'ortho_1m.png', 'ortho.json')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    e = json.loads((SRC / 'osm_extension.json').read_text())
    org = np.array(e['origin_25833'])
    el = json.loads(OSM.read_text())['elements']
    nodes = {x['id']: (x['lon'], x['lat']) for x in el if x['type'] == 'node'}
    ways = {x['id']: x for x in el if x['type'] == 'way'}
    T = Transformer.from_crs(4326, 25833, always_xy=True)
    loc = lambda ids: np.c_[T.transform(*np.array([nodes[i] for i in ids]).T)] - org
    fwd = np.array(e['polyline_local_m'])
    k = int(np.argmin(np.linalg.norm(fwd - SPLIT, axis=1)))
    assert np.linalg.norm(fwd[k] - SPLIT) < 0.1
    drive = []  # reverse-track driving order
    for wid in CHAIN:
        w = ways[wid]
        assert w['tags'].get('oneway') in ('yes', None) and w['tags'].get('highway') == 'secondary', wid
        xy = loc(w['nodes'])
        if drive:
            assert np.linalg.norm(drive[-1][-1] - xy[0]) < 0.01, ('chain not connected', wid)
            xy = xy[1:]
        drive.append(xy)
    drive = np.vstack(drive)[::-1]  # forward parametrisation: from the split outwards, ends at the far (east) end
    assert np.linalg.norm(drive[0] - fwd[k]) < 0.05
    # spawn: SPAWN_BEFORE_CROSSING_M before the zebra in driving direction = east of it in forward parametrisation
    cx = loc([CROSSING_E])[0]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(drive, axis=0), axis=1))]
    sc = s[int(np.argmin(np.linalg.norm(drive - cx, axis=1)))]
    s_spawn, s_end = sc + SPAWN_BEFORE_CROSSING_M, sc + SPAWN_BEFORE_CROSSING_M + END_BEHIND_M
    assert s_end < s[-1]
    cut = np.searchsorted(s, s_end)
    end = np.array([np.interp(s_end, s, drive[:, j]) for j in (0, 1)])
    spawn = np.array([np.interp(s_spawn, s, drive[:, j]) for j in (0, 1)])
    poly = np.vstack([fwd[:k + 1], drive[1:cut], end])
    # ring centre: circle fit of all roundabout ways near the ring
    pts = np.vstack([loc(w['nodes']) for w in ways.values() if w.get('tags', {}).get('junction') == 'roundabout'
                     and np.linalg.norm(loc(w['nodes']) - fwd[k], axis=1).min() < 80])
    A = np.c_[2 * pts, np.ones(len(pts))]
    sol = np.linalg.lstsq(A, (pts ** 2).sum(1), rcond=None)[0]
    centre = sol[:2]
    L = float(np.linalg.norm(np.diff(poly, axis=0), axis=1).sum())
    out = dict(polyline_local_m=poly.tolist(), length_m=L, finish_local_m=spawn.tolist(), finish_arclength_m=L - END_BEHIND_M,
               reverse_spawn_local_m=spawn.tolist(), ring_center_local_m=centre.tolist(),
               ring_radius_m=float(np.sqrt(sol[2] + centre @ centre)), origin_25833=org.tolist(),
               ways=e['ways'][:e['ways'].index(674295715) + 1] + CHAIN[::-1], reverse_driving_order=CHAIN,
               crossing_node=CROSSING_E, spawn_before_crossing_m=SPAWN_BEFORE_CROSSING_M,
               attribution='© OpenStreetMap contributors, ODbL', note=__doc__,
               finish_semantics='finish_* = the REVERSE-track spawn point (pipeline field reused); forward parametrisation')
    (OUT / 'osm_extension.json').write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
    for f in COPY:
        shutil.copy2(SRC / f, OUT / f)
    print(json.dumps({k_: v for k_, v in out.items() if k_ not in ('polyline_local_m', 'note')}, indent=1))


if __name__ == '__main__':
    main()
