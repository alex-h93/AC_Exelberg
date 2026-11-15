"""v010 patch stage 2: constrained Delaunay triangulation in factory-headless Blender (mathutils, no installs).

  flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup --python-exit-code 1 \
      --python /abs/scripts/v010_patch_cdt.py
Input data/processed/extension_v010/patch_domain.npz (points + constraint edges); output patch_cdt.npz: full CDT,
faces in INPUT point ids where possible; vertices created by crossing constraints are appended (coords from CDT,
float32 precision) and listed. Inside/outside is classified in stage 3.
"""
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

ROOT = Path('/var/home/haze/dev/Assetto_Exelberg')
EXT = Path(__import__('os').environ.get('V010_EXT', ROOT / 'data/processed/extension_v010'))  # v011: reverse-track variant
d = np.load(EXT / 'patch_domain.npz')
pts, edges = d['pts'], d['edges']
c = pts.mean(0)
vo, eo, fo, ov, oe, of = delaunay_2d_cdt([Vector(q) for q in (pts - c).tolist()], [tuple(map(int, e)) for e in edges], [], 0, 1e-6, True)
vo = np.array([tuple(q) for q in vo], float) + c
n = len(pts)
remap = np.empty(len(vo), int)
extra = []
for j, o in enumerate(ov):
    ids = [k for k in o if k < n]
    assert len(set(ids)) <= 1, ('CDT merged distinct input points', ids)
    if ids:
        remap[j] = ids[0]
    else:
        remap[j] = n + len(extra)
        extra.append(vo[j])
faces = np.array([[remap[k] for k in f] for f in fo])
assert faces.shape[1] == 3
xy = np.vstack([pts, np.array(extra).reshape(-1, 2)])
np.savez_compressed(EXT / 'patch_cdt.npz', xy=xy, faces=faces, n_input=n)
print('CDT PASS', len(xy), 'verts', len(extra), 'added', len(faces), 'faces', flush=True)
