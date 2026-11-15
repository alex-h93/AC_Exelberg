#!/usr/bin/env python3
"""v011 scenery (visual-only second KN5) for the FORWARD track (exelberg_full_v011) and the new REVERSE track
(exelberg_reverse_v011).  Usage: v011_scenery.py forward|reverse

Same generator as v010 (scripts/v010_scenery.py: v009 scenery on the extended skin, roundabout asphalt, kerb,
buildings, shrubs) plus:
  * chevron fix (user, v010 test: "2 corners where the chevron signs are on the wrong side of the road" before
    Dopplerhuette): when the side logged in the roadside inventory contradicts the road geometry (no bend of the
    matching direction within the search window: W011 ~1.11 km, W015 ~2.32 km) the series is snapped to the actual
    bend and stands on its OUTER side, like the inventory rows logged as 'both'
  * Neuwaldegg roundabout furniture (scripts/v011_urban.py: zebras, crossing/yield/keep-right/parking/deer signs,
    'Tulln' board, green island)
  * reverse only: chevron boards face the reverse traffic (same outer side, arrow mirrored) and town signs are
    mirrored (Koenigstetten entry board on the reverse right-hand side, Scheiblingstein entry/end swapped); other
    signs are the forward-direction signs (their backs are seen, as on the real road)
Outputs: data/processed/scenery_v011/ (forward) or scenery_v011r/ (reverse)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v005_roadside as R5  # noqa: E402
import v010_scenery as S10  # noqa: E402
from v011_urban import Urban  # noqa: E402

MODES = {'forward': ('extension_v010', 'scenery_v011'), 'reverse': ('extension_v011r', 'scenery_v011r')}
FIXED = []


def patch_chevrons():
    orig = R5.chevron_series

    def chevron_series(store, R, s_obs, side_obs, length, n_boards, red, placements):
        want = {'L': -1, 'R': 1}.get(side_obs, 0)
        if want:
            g = (R.kg >= s_obs - 50) & (R.kg <= s_obs + max(length, 0) + 50)
            if not (g.any() and (R.k[g] * want).max() > 1 / 400):
                FIXED.append(dict(s_obs=float(s_obs), logged_side=side_obs, rule='no matching bend -> outer side of the actual bend'))
                side_obs = 'both'
        return orig(store, R, s_obs, side_obs, length, n_boards, red, placements)
    R5.chevron_series = chevron_series


def patch_reverse_signs():
    """Chevrons/town signs face the reverse traffic (R5.sign is looked up at call time by R5.main)."""
    orig = R5.sign
    mirrored = []

    def sign(store, R, s, side, cell, w, h, bottom, placements, note='', two_posts=False, d=None):
        if not (cell.startswith('chev_') or cell.startswith('town_')):
            return orig(store, R, s, side, cell, w, h, bottom, placements, note, two_posts, d)
        if cell.startswith('chev_'):
            cell = cell[:-1] + ('R' if cell.endswith('L') else 'L')  # reverse travel: the bend turns the other way
        else:
            side = -side
            cell = cell.replace('town_end_', 'town_') if 'end_' in cell else cell.replace('town_', 'town_end_')
        if d is None:
            d = R5.SIGN_D if R5.SIGN_INNER is None else R5.SIGN_INNER + w / 2
        p, t, n = R.at(s, side, d)
        facing = t  # faces traffic driving AGAINST the track parametrisation
        m = R5.bucket(store, 'SIGN', s)
        centre = p + R5.UP * (bottom + h / 2)
        m.plate(centre, facing, R5.UP, w, h, cell, R5.SHAPE_BACK.get(cell, 'back_rect'))
        offs = [-w * 0.35, w * 0.35] if two_posts else [0.0]
        right = np.cross(R5.UP, facing)
        for o in offs:
            base = p + right * o - facing * 0.03 + R5.UP * -0.3
            R5.post(m, base, base + R5.UP * (bottom + h * 0.85 + 0.3))
        mirrored.append(cell)
        placements.append(dict(kind='sign', cell=cell, s=float(s), side=side, size_m=[w, h], bottom_m=bottom, lateral_m=float(d),
                               note=(note + ' [reverse-facing]').strip(), facing='reverse'))
    R5.sign = sign
    return mirrored


def main(mode):
    ext, out = MODES[mode]
    S10.EXT = ROOT / 'data/processed' / ext
    S10.SKIN = S10.EXT / 'skin_v010.npz'
    out = ROOT / 'data/processed' / out
    patch_chevrons()
    mirrored = patch_reverse_signs() if mode == 'reverse' else []
    info = {}

    def hook(store, R, placements):
        R5.MATS = tuple(R5.MATS) + ('V011_urban',)
        c = S10.STATE['rbt'][0]
        info['urban'] = Urban(store, R, placements, len(R5.MATS) - 1, c, S10.LIFT + 0.012).run(np.random.default_rng(1101))
    S10.main(out=out, prefix='V011', hook=hook)
    ex = json.loads((out / 'extension.json').read_text())
    ex.update(mode=mode, chevron_fixes=FIXED, reverse_mirrored_signs=len(mirrored), urban=info['urban'], note_v011=__doc__)
    (out / 'extension.json').write_text(json.dumps(ex, indent=2, default=float) + '\n')
    print(json.dumps(dict(mode=mode, chevron_fixes=FIXED, mirrored=len(mirrored), urban=info['urban'])))


if __name__ == '__main__':
    main(sys.argv[1])
