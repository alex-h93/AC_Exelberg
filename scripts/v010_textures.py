#!/usr/bin/env python3
"""v010: mipmapped BGRA DDS of the extension orthophoto (data/processed/extension_v010/ortho_1m.png, BEV CC BY 4.0)
for the new ground patch material. Output: exports/full_track_v010/v010_ortho_ext.dds (+ JSON record)."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

import v004_textures as T

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'exports/full_track_v010'

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(Image.open(ROOT / 'data/processed/extension_v010/ortho_1m.png').convert('RGB'))
    rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
    rec = T.write_dds(OUT / 'v010_ortho_ext.dds', rgba)
    (OUT / 'v010_ortho_ext.json').write_text(json.dumps(rec, indent=2) + '\n')
    print(rec)
