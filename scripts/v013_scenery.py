#!/usr/bin/env python3
"""v013 scenery (usage: v013_scenery.py forward|reverse): v011 scenery + urban-sign clearance fix.

User (v012 test): "there is a missplaced traffic sign on the road at the roundabout. When the start is at the roundabout
the sign is after turning right in the first exit."
Cause: the Neuwaldegg furniture (scripts/v011_urban.py) offsets signs from the OSM carriageway centres (OSM half width
2.25 m + 0.8 m). Our drivable road is 6 m wide (+ gravel) and on the Exelbergstrasse one-way branches it covers part of
the splitter island, so island-side signs of the neighbouring branch end up on the asphalt. Worst case (reverse track):
the entry-branch zebra sign (node 6466384849, island side) 1.31 m from the centreline at s~58 m; also keep-right,
'Tulln' board, deer warning and the exit-branch zebra sign (forward: 2.20 m) inside 3.95 m.
Fix: every urban sign whose base lies closer than CLEAR (= the 3.95 m used for on-route signs, outside the drivable gravel)
to the track centreline is pushed perpendicular to the centreline out to CLEAR, on the side it was on.
Everything else is the v011 pipeline unchanged (same seeds). Output: data/processed/scenery_v013{,r}/
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import v011_scenery as S11  # noqa: E402
import v011_urban as U11  # noqa: E402

CLEAR = 3.95
MOVED = []


def centre_offset(R, xy):
    """Signed lateral offset (left +) of xy from the route polyline (segment projection), and the left normal."""
    P = R.p[:, :2]
    a, b = P[:-1], P[1:]
    ab = b - a
    t = np.clip(np.einsum('ij,ij->i', xy - a, ab) / np.maximum(np.einsum('ij,ij->i', ab, ab), 1e-12), 0, 1)
    q = a + ab * t[:, None]
    i = int(np.argmin(np.linalg.norm(q - xy, axis=1)))
    u = ab[i] / np.linalg.norm(ab[i])
    n = np.array([-u[1], u[0]])
    return float((xy - q[i]) @ n), n, i


def patch_urban_clearance():
    orig = U11.Urban.sign

    def sign(self, xy, face2, plates, note, two_posts=False):
        xy = np.asarray(xy, float)
        off, n, _ = centre_offset(self.R, xy)
        if abs(off) < CLEAR:
            new = xy + n * (np.sign(off or 1.0) * CLEAR - off)
            MOVED.append(dict(note=note, from_xy=np.round(xy, 2).tolist(), to_xy=np.round(new, 2).tolist(),
                              offset_before_m=round(off, 2), offset_after_m=round(centre_offset(self.R, new)[0], 2)))
            xy = new
        return orig(self, xy, face2, plates, note, two_posts)
    U11.Urban.sign = sign


def main(mode):
    out = {'forward': 'scenery_v013', 'reverse': 'scenery_v013r'}[mode]
    S11.MODES[mode] = (S11.MODES[mode][0], out)
    patch_urban_clearance()
    S11.main(mode)
    p = ROOT / 'data/processed' / out / 'extension.json'
    ex = json.loads(p.read_text())
    ex.update(urban_clearance_m=CLEAR, urban_signs_moved=MOVED, note_v013=__doc__)
    p.write_text(json.dumps(ex, indent=2, default=float) + '\n')
    assert all(abs(m['offset_after_m']) >= CLEAR - 0.05 for m in MOVED), MOVED
    print(json.dumps(dict(mode=mode, moved=MOVED), indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
