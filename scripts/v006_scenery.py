#!/usr/bin/env python3
"""v006 scenery generator: v005 roadside content (corrected sign atlas, signs closer to the road)
+ OSM buildings (scripts/v006_buildings.py). Visual only, no collision.

Changes vs v005:
  * sign plates: inner edge 4.4 m from the centreline (v005: post at 6.4 m) per user's in-game review
  * names/materials prefixed V006 (separate KN5, no clash with the v005 roadside KN5)
  * shrubs avoid building footprints; new BLDG objects per 250 m cell, LOD out 1500 m
Output: data/processed/scenery_v006/{geometry.npz, objects.json, placements.json, buildings.json}
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v005_roadside as R5  # noqa: E402
import v006_buildings as B  # noqa: E402

OUT = ROOT / 'data/processed/scenery_v006'
SIGN_INNER = 4.4


def main():
    R5.SIGN_INNER = SIGN_INNER
    R5.PREFIX = 'V006'
    R5.JUNC_BARRIER = False
    R5.MATS = tuple(m.replace('V005_', 'V006_') for m in R5.MATS) + tuple(f'V006_{k}' for k in B.BMATS)
    R5.LODS = dict(R5.LODS, BLDG=(0, 1500, True))
    MI = {k: R5.MATS.index(f'V006_{k}') for k in B.BMATS}
    fps = B.load_footprints()
    R5.AVOID = B.make_avoid(fps)
    stats = {}

    def extra(store, R, placements):
        stats.update(B.add_buildings(store, R, placements, fps, MI, R5.bucket))

    R5.main(out=OUT, extra=extra)
    pl = json.loads((OUT / 'placements.json').read_text())
    bl = [p for p in pl if p['kind'] == 'building']
    from collections import Counter
    rep = dict(stats=stats, sign_inner_m=SIGN_INNER, shapes=dict(Counter(p['shape'] for p in bl)),
               height_sources=dict(Counter(p['height_source'] for p in bl)),
               roofs=dict(Counter(p['roof'] for p in bl)), facades=dict(Counter(p['facade'] for p in bl)), note=B.__doc__)
    (OUT / 'buildings.json').write_text(json.dumps(rep, indent=2) + '\n')
    print(json.dumps(stats))


if __name__ == '__main__':
    main()
