#!/usr/bin/env python3
"""v006 textures: v005 sign atlas with corrections from the user's in-game review, plus building textures.

Sign corrections (same atlas layout as v005, so UVs are unchanged):
  * town signs (Ortstafel): black name on WHITE, blue frame; end sign adds the red diagonal bar
  * red chevron boards: WHITE arrow on RED background (yellow/black boards unchanged, as on the real road)
Building textures (procedural, tiling):
  v006_facade_{white,cream,ochre}.dds  512x512 = 6 m wide x 6 m tall (two storeys, windows)
  v006_facade_plain.dds                garages/huts (no windows, wood-ish plaster)
  v006_roof_{red,dark}.dds             256x256 = 2 m x 2 m tile rows
Outputs data/processed/textures_v006/ (+ copies of the unchanged v005 textures it needs).
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
OUT = ROOT / 'data/processed/textures_v006'
C = T5.C
BLUE = (20, 70, 150, 255); RED = (200, 30, 35, 255); WHITE = (240, 240, 236, 255); BLACK = (15, 15, 15, 255)


def fix_signs(atlas):
    img = Image.fromarray(atlas)

    def cellbox(name):
        c, r, w, h = T5.CELLS[name]
        return c * C, r * C, (c + w) * C, (r + h) * C

    for place, label in (('Koenigstetten', 'Königstetten'), ('Scheiblingstein', 'Scheiblingstein')):
        for end in ('', 'end_'):
            name = f'town_{end}{place}'
            x0, y0, x1, y1 = cellbox(name)
            im = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0)); g = ImageDraw.Draw(im); w = x1 - x0
            g.rectangle([2, 8, w - 3, C - 9], fill=BLUE)            # blue frame
            g.rectangle([10, 16, w - 11, C - 17], fill=WHITE)       # white field
            g.text((w / 2, C / 2), label, fill=BLACK, font=T5.font(30 if len(label) < 13 else 25), anchor='mm')
            if end:
                g.line([16, C - 22, w - 16, 22], fill=RED, width=10)
            img.paste(im, (x0, y0))
    for d in 'LR':
        name = f'chev_red_{d}'
        x0, y0, x1, y1 = cellbox(name)
        im = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0)); g = ImageDraw.Draw(im)
        g.rectangle([10, 2, C - 11, C - 3], fill=RED, outline=(90, 20, 20, 255), width=2)
        pts = [(84, 18), (44, 64), (84, 110), (100, 98), (70, 64), (100, 30)]
        if d == 'R':
            pts = [(C - x, y) for x, y in pts]
        g.polygon(pts, fill=WHITE)
        img.paste(im, (x0, y0))
    return np.asarray(img)


def plaster(size, base, rng, amp=7):
    n = rng.normal(0, 1, (size, size))
    k = np.ones(5) / 5
    n = np.apply_along_axis(lambda r: np.convolve(np.r_[r[-2:], r, r[:2]], k, 'valid'), 1, n)  # wrap-blur keeps tiling
    rgb = np.clip(np.asarray(base, float)[None, None] + n[..., None] * amp, 0, 255)
    return Image.fromarray(np.concatenate([rgb, np.full((size, size, 1), 255.)], -1).astype(np.uint8))


def facade(base, rng, windows=True):
    S = 512  # 6 m x 6 m
    im = plaster(S, base, rng)
    if windows:
        g = ImageDraw.Draw(im)
        px = S / 6.0
        for storey in (0, 1):
            y_top = S - (storey * 3.0 + 2.25) * px   # window 1.0-2.25 m above floor level
            y_bot = S - (storey * 3.0 + 1.0) * px
            for xc in (1.5, 4.5):
                x0, x1 = (xc - 0.55) * px, (xc + 0.55) * px
                g.rectangle([x0 - 4, y_top - 4, x1 + 4, y_bot + 6], fill=(235, 235, 232, 255))
                g.rectangle([x0, y_top, x1, y_bot], fill=(52, 62, 72, 255))
                g.line([(x0 + x1) / 2, y_top, (x0 + x1) / 2, y_bot], fill=(225, 225, 220, 255), width=4)
                g.line([x0, (y_top + y_bot) / 2 - 8, x1, (y_top + y_bot) / 2 - 8], fill=(225, 225, 220, 255), width=4)
        g.rectangle([0, S - 0.35 * px, S, S], fill=tuple(int(c * .7) for c in base) + (255,))  # plinth
    return np.asarray(im)


def roof(base, rng):
    S = 256  # 2 m x 2 m, tile rows every 0.25 m
    im = plaster(S, base, rng, amp=9)
    g = ImageDraw.Draw(im)
    for y in range(0, S, S // 8):
        g.line([0, y, S, y], fill=tuple(int(c * .62) for c in base) + (255,), width=3)
        off = (y // (S // 8)) % 2 * 16
        for x in range(off, S + 32, 32):
            g.line([x, y, x, y + S // 8], fill=tuple(int(c * .8) for c in base) + (255,), width=1)
    return np.asarray(im)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'previews').mkdir(exist_ok=True)
    rng = np.random.default_rng(606)
    v5 = ROOT / 'data/processed/textures_v005'
    atlas = fix_signs(np.asarray(Image.open(v5 / 'previews/signs.png').convert('RGBA')))
    Image.fromarray(atlas).save(OUT / 'previews/signs.png')
    files = {'signs': T4.write_dds(OUT / 'v006_signs.dds', atlas, alpha_test=True)}
    for k in ('asphalt', 'gravel', 'foliage', 'bark'):
        shutil.copy2(v5 / f'v005_{k}.dds', OUT / f'v006_{k}.dds')
        shutil.copy2(v5 / f'previews/{k}.png', OUT / f'previews/{k}.png')
        files[k] = dict(path=str((OUT / f'v006_{k}.dds').relative_to(ROOT)), copied_from=f'v005_{k}.dds',
                        sha256=hashlib.sha256((OUT / f'v006_{k}.dds').read_bytes()).hexdigest())
    tex = {'facade_white': facade((228, 226, 218), rng), 'facade_cream': facade((226, 212, 180), rng),
           'facade_ochre': facade((214, 186, 128), rng), 'facade_plain': facade((150, 128, 100), rng, windows=False),
           'roof_red': roof((150, 62, 44), rng), 'roof_dark': roof((70, 72, 76), rng)}
    for k, a in tex.items():
        files[k] = T4.write_dds(OUT / f'v006_{k}.dds', a)
        Image.fromarray(a).save(OUT / f'previews/{k}.png')
    (OUT / 'manifest.json').write_text(json.dumps(dict(note=__doc__, files=files), indent=2) + '\n')
    print(json.dumps({k: v.get('bytes', 'copied') for k, v in files.items()}))


if __name__ == '__main__':
    main()
