#!/usr/bin/env python3
"""v008 scenery: identical to v007 scenery (posts, chevrons, roofs, signs, buildings) but every object is placed
on the SMOOTHED ground skin (scripts/v008_terrain.py). Output: data/processed/scenery_v008/"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v005_roadside as R5  # noqa: E402
import v007_scenery as S7  # noqa: E402

if __name__ == '__main__':
    R5.SKIN = ROOT / 'data/processed/terrain_v008/smoothed_skin.npz'
    S7.main(prefix='V008', out=ROOT / 'data/processed/scenery_v008')
