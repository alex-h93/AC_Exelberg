#!/usr/bin/env python3
"""v005 roadside textures (procedural, drawn here; no third-party sign artwork).

Outputs data/processed/textures_v005/:
  v005_signs.dds    1024x1024 atlas, 8x8 cells of 128 px (layout CELLS below), alpha-tested shapes
  v005_asphalt.dds  256x256 tiling asphalt (procedural noise)
  v005_gravel.dds   512x512 tiling gravel (ambientCG Gravel023, CC0)
  v005_foliage.dds  1024 downscale of v004 foliage atlas (same UV layout)
  v005_bark.dds     512 downscale of v004 bark atlas
  manifest.json + previews/signs.png
Sign designs are simplified approximations of Austrian StVO signs, not certified reproductions.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import v004_textures as T4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/textures_v005'
TEX4 = ROOT / 'data/processed/textures_v004'
CC0 = ROOT / 'data/interim/textures_cc0'
C = 128  # cell px
N = 8

RED = (200, 30, 35, 255); WHITE = (238, 238, 232, 255); BLACK = (20, 20, 22, 255)
YEL = (250, 200, 0, 255); BLUE = (20, 70, 150, 255); GREY = (150, 152, 150, 255)

# name -> (col, row, wcells, hcells)
CELLS = {
    'chev_yel_L': (0, 0, 1, 1), 'chev_yel_R': (1, 0, 1, 1), 'chev_red_L': (2, 0, 1, 1), 'chev_red_R': (3, 0, 1, 1),
    'speed_50': (4, 0, 1, 1), 'speed_70': (5, 0, 1, 1), 'warn_curves': (6, 0, 1, 1), 'warn_generic': (7, 0, 1, 1),
    'priority': (0, 1, 1, 1), 'no_stopping': (1, 1, 1, 1), 'no_entry_round': (2, 1, 1, 1), 'children': (3, 1, 1, 1),
    'back_round': (4, 1, 1, 1), 'back_tri': (5, 1, 1, 1), 'back_diamond': (6, 1, 1, 1), 'back_rect': (7, 1, 1, 1),
    'town_Koenigstetten': (0, 2, 2, 1), 'town_Scheiblingstein': (2, 2, 2, 1),
    'town_end_Koenigstetten': (4, 2, 2, 1), 'town_end_Scheiblingstein': (6, 2, 2, 1),
    'direction': (0, 3, 2, 1), 'info_board': (2, 3, 2, 1), 'billboard': (4, 3, 2, 1), 'barrier_stripes': (6, 3, 2, 1),
    # solid material swatches (uv inside, never edges)
    'metal': (0, 4, 2, 2), 'concrete': (2, 4, 2, 2), 'tower': (4, 4, 2, 2), 'post_grey': (6, 4, 1, 1),
    'red': (7, 4, 1, 1), 'white': (6, 5, 1, 1), 'wood': (7, 5, 1, 1), 'dark': (0, 6, 1, 1), 'glass': (1, 6, 1, 1),
    'roof': (2, 6, 2, 2), 'plaster': (4, 6, 2, 2),
}
SHAPE_BACK = {'chev_yel_L': 'back_rect', 'chev_yel_R': 'back_rect', 'chev_red_L': 'back_rect', 'chev_red_R': 'back_rect',
              'speed_50': 'back_round', 'speed_70': 'back_round', 'no_stopping': 'back_round', 'no_entry_round': 'back_round',
              'warn_curves': 'back_tri', 'warn_generic': 'back_tri', 'children': 'back_tri', 'priority': 'back_diamond'}


def uv_rect(name, inset=0.0):
    """Blender UV (u0, v0, u1, v1) of a cell; inset in px."""
    c, r, w, h = CELLS[name]
    W = N * C
    x0, y0, x1, y1 = c * C + inset, r * C + inset, (c + w) * C - inset, (r + h) * C - inset
    return x0 / W, 1 - y1 / W, x1 / W, 1 - y0 / W


FONT = Path('/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf')  # SIL OFL, used only to rasterise


def font(size):
    return ImageFont.truetype(str(FONT), size) if FONT.exists() else ImageFont.load_default(size=size)


def noise(shape, rng, amp, base):
    n = rng.normal(0, amp, shape[:2])
    a = np.clip(np.asarray(base[:3], float)[None, None] + n[..., None], 0, 255)
    return np.concatenate([a, np.full(shape[:2] + (1,), 255.)], -1).astype(np.uint8)


def draw_atlas():
    W = N * C
    img = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    rng = np.random.default_rng(5)

    def box(name):
        c, r, w, h = CELLS[name]
        return c * C, r * C, (c + w) * C, (r + h) * C

    def sub(name):
        x0, y0, x1, y1 = box(name)
        return Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0)), (x0, y0)

    def put(name, im):
        img.paste(im, box(name)[:2])

    # chevrons: rectangular board with bold arrow, 4 px border margin
    for name, (bg, fg) in {'chev_yel': (YEL, BLACK), 'chev_red': (WHITE, RED)}.items():
        for d in 'LR':
            im, _ = sub(f'{name}_{d}')
            g = ImageDraw.Draw(im)
            g.rectangle([10, 2, C - 11, C - 3], fill=bg, outline=(60, 60, 60, 255), width=2)
            pts = [(84, 18), (44, 64), (84, 110), (100, 98), (70, 64), (100, 30)]
            if d == 'R':
                pts = [(C - x, y) for x, y in pts]
            g.polygon(pts, fill=fg)
            put(f'{name}_{d}', im)
    # round signs
    for name, text in (('speed_50', '50'), ('speed_70', '70')):
        im, _ = sub(name); g = ImageDraw.Draw(im)
        g.ellipse([3, 3, C - 4, C - 4], fill=RED); g.ellipse([17, 17, C - 18, C - 18], fill=WHITE)
        g.text((C / 2, C / 2 + 2), text, fill=BLACK, font=font(54), anchor='mm')
        put(name, im)
    im, _ = sub('no_stopping'); g = ImageDraw.Draw(im)
    g.ellipse([3, 3, C - 4, C - 4], fill=RED); g.ellipse([17, 17, C - 18, C - 18], fill=BLUE)
    g.line([28, 28, C - 29, C - 29], fill=RED, width=14); g.line([28, C - 29, C - 29, 28], fill=RED, width=14)
    put('no_stopping', im)
    im, _ = sub('no_entry_round'); g = ImageDraw.Draw(im)  # Fahrverbot (white disc, red ring)
    g.ellipse([3, 3, C - 4, C - 4], fill=RED); g.ellipse([17, 17, C - 18, C - 18], fill=WHITE)
    put('no_entry_round', im)
    # triangles
    tri = [(C / 2, 6), (C - 4, C - 12), (4, C - 12)]
    inner = [(C / 2, 30), (C - 26, C - 24), (26, C - 24)]
    for name in ('warn_curves', 'warn_generic', 'children'):
        im, _ = sub(name); g = ImageDraw.Draw(im)
        g.polygon(tri, fill=RED); g.polygon(inner, fill=WHITE)
        if name == 'warn_generic':
            g.rectangle([60, 52, 68, 82], fill=BLACK); g.rectangle([60, 88, 68, 96], fill=BLACK)
        elif name == 'warn_curves':
            g.line([(56, 98), (56, 84), (72, 74), (72, 62), (58, 52), (58, 44)], fill=BLACK, width=8)
            g.polygon([(50, 46), (66, 46), (58, 34)], fill=BLACK)
        else:
            g.ellipse([50, 50, 60, 60], fill=BLACK); g.rectangle([50, 62, 60, 92], fill=BLACK)
            g.ellipse([68, 58, 76, 66], fill=BLACK); g.rectangle([68, 68, 76, 92], fill=BLACK)
        put(name, im)
    im, _ = sub('priority'); g = ImageDraw.Draw(im)
    g.polygon([(C / 2, 3), (C - 4, C / 2), (C / 2, C - 4), (3, C / 2)], fill=WHITE)
    g.polygon([(C / 2, 22), (C - 23, C / 2), (C / 2, C - 23), (22, C / 2)], fill=YEL)
    put('priority', im)
    # backs (grey silhouettes)
    for name, shape in (('back_round', 'round'), ('back_tri', 'tri'), ('back_diamond', 'diamond'), ('back_rect', 'rect')):
        im, _ = sub(name); g = ImageDraw.Draw(im)
        if shape == 'round':
            g.ellipse([3, 3, C - 4, C - 4], fill=GREY)
        elif shape == 'tri':
            g.polygon(tri, fill=GREY)
        elif shape == 'diamond':
            g.polygon([(C / 2, 3), (C - 4, C / 2), (C / 2, C - 4), (3, C / 2)], fill=GREY)
        else:
            g.rectangle([10, 2, C - 11, C - 3], fill=GREY)
        put(name, im)
    # town signs (Austrian Ortstafel: blue, white border/text; end sign with red bar)
    for place, label in (('Koenigstetten', 'Königstetten'), ('Scheiblingstein', 'Scheiblingstein')):
        for end in ('', 'end_'):
            name = f'town_{end}{place}'
            im, _ = sub(name); g = ImageDraw.Draw(im); w = 2 * C
            g.rectangle([2, 8, w - 3, C - 9], fill=WHITE); g.rectangle([8, 14, w - 9, C - 15], fill=BLUE)
            g.text((w / 2, C / 2), label, fill=WHITE, font=font(30 if len(label) < 13 else 25), anchor='mm')
            if end:
                g.line([14, C - 20, w - 14, 20], fill=RED, width=10)
            put(name, im)
    # direction board: white with abstract text bars (real text unknown)
    im, _ = sub('direction'); g = ImageDraw.Draw(im); w = 2 * C
    g.rectangle([2, 6, w - 3, C - 7], fill=WHITE, outline=BLACK, width=3)
    for i, y in enumerate((26, 54, 82)):
        g.rectangle([18, y, 18 + [150, 120, 170][i], y + 12], fill=(40, 40, 40, 255))
        g.polygon([(w - 40, y - 4), (w - 20, y + 6), (w - 40, y + 16)], fill=(40, 40, 40, 255))
    put('direction', im)
    im, _ = sub('info_board'); g = ImageDraw.Draw(im)
    g.rectangle([2, 6, w - 3, C - 7], fill=(235, 235, 225, 255), outline=(90, 70, 50, 255), width=5)
    for y in (30, 50, 70, 90):
        g.rectangle([20, y, w - 20 - (y % 40), y + 8], fill=(90, 90, 90, 255))
    put('info_board', im)
    im, _ = sub('billboard'); g = ImageDraw.Draw(im)
    g.rectangle([2, 6, w - 3, C - 7], fill=YEL); g.rectangle([16, 22, 120, 60], fill=(30, 110, 50, 255))
    g.rectangle([16, 72, w - 16, 100], fill=(30, 110, 50, 255))
    put('billboard', im)
    im, _ = sub('barrier_stripes'); g = ImageDraw.Draw(im)
    g.rectangle([0, 0, w - 1, C - 1], fill=WHITE)
    for x in range(-C, w + C, 64):
        g.polygon([(x, C), (x + 32, C), (x + 32 + C, 0), (x + C, 0)], fill=RED)
    put('barrier_stripes', im)
    # swatches
    sw = {'metal': ((168, 172, 170), 9), 'concrete': ((172, 170, 162), 10), 'tower': ((205, 206, 202), 6),
          'post_grey': ((120, 122, 122), 4), 'red': ((190, 30, 35), 3), 'white': ((236, 236, 230), 3),
          'wood': ((105, 78, 52), 10), 'dark': ((45, 48, 50), 4), 'glass': ((70, 85, 95), 5),
          'roof': ((140, 60, 45), 10), 'plaster': ((222, 214, 196), 6)}
    for name, (base, amp) in sw.items():
        x0, y0, x1, y1 = box(name)
        img.paste(Image.fromarray(noise((y1 - y0, x1 - x0), rng, amp, base)), (x0, y0))
    return np.asarray(img)


def tile_noise(size, base, amp, rng, blur=1):
    a = rng.normal(0, 1, (size, size))
    f = np.fft.fft2(a); ky, kx = np.meshgrid(np.fft.fftfreq(size), np.fft.fftfreq(size), indexing='ij')
    a = np.fft.ifft2(f * np.exp(-(kx ** 2 + ky ** 2) * (size / (4 * blur)) ** 2 * 0.0) / 1).real  # tiling white noise
    a = (a - a.mean()) / a.std()
    rgb = np.clip(np.asarray(base, float)[None, None] + a[..., None] * amp, 0, 255)
    return np.concatenate([rgb, np.full((size, size, 1), 255.)], -1).astype(np.uint8)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'previews').mkdir(exist_ok=True)
    rng = np.random.default_rng(11)
    man = dict(note=__doc__, cells=CELLS, cell_px=C, files={})
    atlas = draw_atlas()
    Image.fromarray(atlas).save(OUT / 'previews/signs.png')
    man['files']['signs'] = T4.write_dds(OUT / 'v005_signs.dds', atlas, alpha_test=True)
    man['files']['asphalt'] = T4.write_dds(OUT / 'v005_asphalt.dds', tile_noise(256, (50, 52, 54), 7, rng))
    g = Image.open(CC0 / 'Gravel023_1K-PNG/Gravel023_1K-PNG_Color.png').convert('RGBA').resize((512, 512), Image.LANCZOS)
    ga = np.asarray(g).astype(float)
    ga[..., :3] *= np.array([112, 102, 82]) / ga[..., :3].reshape(-1, 3).mean(0)  # match v002/v003 gravel shoulder tint
    man['files']['gravel'] = T4.write_dds(OUT / 'v005_gravel.dds', np.clip(ga, 0, 255).astype(np.uint8))
    fol = T4.read_bgra_dds(TEX4 / 'v004_foliage.dds')
    small = Image.fromarray(fol).resize((1024, 1024), Image.LANCZOS)
    man['files']['foliage'] = T4.write_dds(OUT / 'v005_foliage.dds', np.asarray(small), alpha_test=True)
    bark = T4.read_bgra_dds(TEX4 / 'v004_bark.dds')
    man['files']['bark'] = T4.write_dds(OUT / 'v005_bark.dds', np.asarray(Image.fromarray(bark).resize((512, 512), Image.LANCZOS)))
    man['sources'] = dict(gravel='ambientCG Gravel023 (CC0 1.0)', foliage_bark='v004 atlases (ambientCG CC0) downscaled',
                          signs='procedurally drawn in this script; simplified approximations')
    (OUT / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
    print(json.dumps({k: v['bytes'] for k, v in man['files'].items()}))


if __name__ == '__main__':
    main()
