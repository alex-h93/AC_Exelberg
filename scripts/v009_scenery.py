#!/usr/bin/env python3
"""v009 scenery: identical to v008 scenery (posts, chevrons, roofs, signs, buildings, junction stubs) but placed
along the SMOOTHED road centreline and on the XY-deformed v008 ground skin (scripts/v009_centerline.py).
Station-based objects (signs, chevrons, guardrails, junction stubs) follow the new centreline automatically;
the guide posts (v003 posts.json stores absolute XY) are moved by the same v009 displacement field as the road
edge and re-grounded on the v009 skin. Output: data/processed/scenery_v009/"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v005_roadside as R5  # noqa: E402
import v007_scenery as S7  # noqa: E402
from v009_field import Field  # noqa: E402

SKIN9 = ROOT / 'data/processed/road_v009/smoothed_skin.npz'


def add_posts_v009(store, R, placements):
    pl = json.loads(S7.POSTS.read_text())['placements']
    d = np.load(SKIN9)
    F = Field(d['designed_xyz_v008_m'], d['designed_xyz_m'])
    xy0 = np.array([q['ground_xyz_m'][:2] for q in pl], float)
    xy1 = F.displace(xy0)
    for q, (x, y) in zip(pl, xy1):
        s, off = q['arclength_m'], q['offset_left_m']
        pos, t, n = R.frame(s)
        S7.leitpflock(R5.bucket(store, 'POST', s), R, np.array([x, y, R.z((x, y)) - 0.02]), t, np.sign(off) * n)
    placements.append(dict(kind='guide_posts', count=len(pl), source='v003 posts.json positions moved by the v009 road field',
                           design='Austrian Leitpflock (user photo)',
                           max_shift_m=round(float(np.linalg.norm(xy1 - xy0, axis=1).max()), 3)))
    return len(pl)


if __name__ == '__main__':
    R5.SKIN = SKIN9
    S7.add_posts = add_posts_v009
    S7.main(prefix='V009', out=ROOT / 'data/processed/scenery_v009')
