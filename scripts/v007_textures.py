#!/usr/bin/env python3
"""v007 textures: v006 atlas + corrections from the user's v006 in-game review.

  * red chevron boards redrawn after data/raw/chevron_austria.svg (user-supplied sample): full red board,
    one large white chevron spanning the full height (apex at the board edge). Yellow/black boards unchanged.
  * new cells for the Austrian guide post (Leitpflock, after user photo data/raw/Leitpflock-B16_4333.jpg):
    refl_strip (black plate with white reflective dots) at (6,6), refl_blue (blue wildlife reflector) at (7,6).
Building/ground textures are copied unchanged from textures_v006 (renamed v007_*).
Output: data/processed/textures_v007/
"""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import v004_textures as T4
import v005_textures as T5

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/textures_v007'
C = T5.C
NEW_CELLS = {'refl_strip': (6, 6, 1, 1), 'refl_blue': (7, 6, 1, 1)}
T5.CELLS.update(NEW_CELLS)  # importers of this module get uv_rect() for the new cells
RED = (217, 38, 28, 255)    # #d9261c from the sample SVG
WHITE = (245, 245, 242, 255)


def chevron_cell(right=True):
    """SVG geometry (494.6 px square): white polygon (-5,-5) (244,-5) (494,247) (244,499) (-5,499) (244,247)."""
    S = 4 * C  # supersample
    im = Image.new('RGBA', (S, S), RED)
    k = S / 494.6
    pts = [(-5, -5), (244.5, -5), (494.3, 247.2), (244.5, 499.5), (-5, 499.5), (244.5, 247.2)]
    pts = [(x * k, y * k) for x, y in pts]
    if not right:
        pts = [(S - x, y) for x, y in pts]
    ImageDraw.Draw(im).polygon(pts, fill=WHITE)
    return np.asarray(im.resize((C, C), Image.LANCZOS))


def refl_strip():
    im = Image.new('RGBA', (C, C), (18, 18, 18, 255))
    g = ImageDraw.Draw(im)
    for y in range(8, C - 6, 9):
        for x in range(10 + (y // 9) % 2 * 4, C - 8, 9):
            g.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=(235, 235, 230, 255))
    return np.asarray(im)


def refl_blue():
    im = Image.new('RGBA', (C, C), (20, 20, 70, 255))
    g = ImageDraw.Draw(im)
    g.rectangle([8, 8, C - 9, C - 9], fill=(40, 40, 190, 255))
    for y in range(12, C - 10, 7):
        g.line([12, y, C - 13, y], fill=(70, 70, 230, 255), width=2)
    return np.asarray(im)


def put(atlas, name, cell):
    c, r, w, h = T5.CELLS[name]
    atlas[r * C:(r + h) * C, c * C:(c + w) * C] = cell


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'previews').mkdir(exist_ok=True)
    v6 = ROOT / 'data/processed/textures_v006'
    atlas = np.array(Image.open(v6 / 'previews/signs.png').convert('RGBA'))
    put(atlas, 'chev_red_R', chevron_cell(True))
    put(atlas, 'chev_red_L', chevron_cell(False))
    put(atlas, 'refl_strip', refl_strip())
    put(atlas, 'refl_blue', refl_blue())
    Image.fromarray(atlas).save(OUT / 'previews/signs.png')
    files = {'signs': T4.write_dds(OUT / 'v007_signs.dds', atlas, alpha_test=True)}
    for k in ('asphalt', 'gravel', 'foliage', 'bark', 'facade_white', 'facade_cream', 'facade_ochre', 'facade_plain',
              'roof_red', 'roof_dark'):
        shutil.copy2(v6 / f'v006_{k}.dds', OUT / f'v007_{k}.dds')
        shutil.copy2(v6 / f'previews/{k}.png', OUT / f'previews/{k}.png')
        files[k] = dict(copied_from=f'v006_{k}.dds', sha256=hashlib.sha256((OUT / f'v007_{k}.dds').read_bytes()).hexdigest())
    (OUT / 'manifest.json').write_text(json.dumps(dict(note=__doc__, new_cells=NEW_CELLS, files=files), indent=2) + '\n')
    print('ok', files['signs'])


if __name__ == '__main__':
    main()
