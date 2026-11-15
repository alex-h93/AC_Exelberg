#!/usr/bin/env python3
"""v004 texture builder (.venv): CC0 ambientCG sources -> mipmapped DDS for AC.

Outputs (data/processed/textures_v004/):
  v004_foliage.dds   2048² atlas, 4x4 cells: rows beech, oak, conifer, shrub (alpha-tested)
  v004_bark.dds      1024² atlas, 4 vertical strips: beech, oak, conifer, shrub
  v004_grass_detail.dds  tiling multiply-detail for the orthophoto ground
  v004_ortho_XXX.dds     v003 ortho chunks re-encoded with alpha 0 (=full detail) + mips
  previews/*.png, manifest.json
DDS: uncompressed A8R8G8B8 with a full mip chain; alpha mips preserve coverage.
Sources: ambientCG (CC0 1.0); BEV orthophoto (CC BY 4.0) via v003 exports.
"""
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data/interim/textures_cc0'
OUT = ROOT / 'data/processed/textures_v004'
V3 = ROOT / 'exports/full_track_v003'
RNG = np.random.default_rng(4004)
CELL = 512


# ---------------------------------------------------------------- DDS
def _mips(rgba, alpha_test):
    levels = [rgba.astype(np.float32)]
    cover0 = (rgba[..., 3] > 127).mean() if alpha_test else None
    while max(levels[-1].shape[:2]) > 1:
        a = levels[-1]
        h, w = a.shape[:2]
        a = a[: h - h % 2 or 1, : w - w % 2 or 1]
        if a.shape[0] >= 2 and a.shape[1] >= 2:
            # premultiplied box filter so transparent texels don't bleed dark fringes
            al = a[..., 3:4] / 255.0
            pm = a[..., :3] * al
            sumc = pm[0::2, 0::2] + pm[1::2, 0::2] + pm[0::2, 1::2] + pm[1::2, 1::2]
            suma = al[0::2, 0::2] + al[1::2, 0::2] + al[0::2, 1::2] + al[1::2, 1::2]
            rgb = np.where(suma > 1e-4, sumc / np.maximum(suma, 1e-4), (a[0::2, 0::2, :3] + a[1::2, 1::2, :3]) / 2)
            alpha = suma / 4 * 255.0
            b = np.concatenate([rgb, alpha], -1)
        else:
            b = a.reshape(-1, 4).mean(0).reshape(1, 1, 4)
        if alpha_test and cover0 is not None and b.shape[0] > 2:
            # scale alpha so the fraction above the 0.5 threshold matches level 0
            lo, hi = 0.5, 4.0
            for _ in range(18):
                mid = (lo + hi) / 2
                if (np.clip(b[..., 3] * mid, 0, 255) > 127).mean() < cover0:
                    lo = mid
                else:
                    hi = mid
            b[..., 3] = np.clip(b[..., 3] * hi, 0, 255)
        levels.append(b)
    return [np.clip(l + 0.5, 0, 255).astype(np.uint8) for l in levels]


def write_dds(path, rgba, alpha_test=False):
    h, w = rgba.shape[:2]
    levels = _mips(rgba, alpha_test)
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x8 | 0x20000  # caps|height|width|pixelformat|pitch|mipmapcount
    pf = struct.pack('<8I', 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    caps = 0x1000 | 0x8 | 0x400000
    header = b'DDS ' + struct.pack('<7I', 124, flags, h, w, w * 4, 0, len(levels)) + b'\0' * 44 + pf + struct.pack('<5I', caps, 0, 0, 0, 0)
    assert len(header) == 128
    body = b''.join(l[..., [2, 1, 0, 3]].tobytes() for l in levels)  # BGRA
    path.write_bytes(header + body)
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, size=[w, h], mips=len(levels),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def read_bgra_dds(path):
    data = path.read_bytes()
    h, w = struct.unpack('<2I', data[12:20])
    px = np.frombuffer(data[128:128 + w * h * 4], np.uint8).reshape(h, w, 4)
    return px[..., [2, 1, 0, 3]].copy()


# ---------------------------------------------------------------- sprites
def leaf_sprites(name, max_sprites=12):
    d = SRC / f'{name}_1K-PNG'
    col = np.asarray(Image.open(d / f'{name}_1K-PNG_Color.png').convert('RGB'))
    op = np.asarray(Image.open(d / f'{name}_1K-PNG_Opacity.png').convert('L'))
    small = op[::4, ::4] > 100
    lab = np.zeros(small.shape, np.int32)
    n = 0
    boxes = []
    for sy, sx in zip(*np.nonzero(small)):
        if lab[sy, sx]:
            continue
        n += 1
        stack = [(sy, sx)]
        lab[sy, sx] = n
        ys, xs = [], []
        while stack:
            y, x = stack.pop()
            ys.append(y); xs.append(x)
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < small.shape[0] and 0 <= xx < small.shape[1] and small[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    stack.append((yy, xx))
        if len(ys) > 40:
            boxes.append((min(ys) * 4 - 4, min(xs) * 4 - 4, max(ys) * 4 + 8, max(xs) * 4 + 8))
    sprites = []
    for y0, x0, y1, x1 in sorted(boxes, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))[:max_sprites]:
        y0, x0 = max(y0, 0), max(x0, 0)
        rgba = np.dstack([col[y0:y1, x0:x1], op[y0:y1, x0:x1]])
        sprites.append(Image.fromarray(rgba, 'RGBA'))
    return sprites


def graded(sprite, target, jitter):
    a = np.asarray(sprite).astype(np.float32)
    m = a[..., 3] > 128
    mean = a[m, :3].mean(0) if m.any() else np.array([128, 128, 128.0])
    lum = a[..., :3].mean(-1, keepdims=True)
    detail = lum / max(lum[m].mean(), 1)
    rgb = np.clip(np.array(target) * jitter * (0.6 + 0.4 * detail) * (a[..., :3] / np.maximum(mean, 1)) ** 0.25, 0, 255)
    return Image.fromarray(np.dstack([rgb, a[..., 3]]).astype(np.uint8), 'RGBA')


def cluster_cell(sprites, target, n_leaves, leaf_px, conifer=False):
    img = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    twig = (78, 62, 46, 255)
    # stem + side twigs; leaves are attached along them
    pts = []
    base = np.array([CELL / 2 + RNG.normal(0, 20), CELL - 10.0])
    tip = np.array([CELL / 2 + RNG.normal(0, 50), 50.0])
    stem = [base + (tip - base) * t + np.array([math.sin(t * 3 + RNG.random()) * 18, 0]) for t in np.linspace(0, 1, 12)]
    d.line([tuple(p) for p in stem], fill=twig, width=6)
    pts += stem[3:]
    for k in range(7 if not conifer else 9):
        t = RNG.uniform(0.15, 0.9)
        start = base + (tip - base) * t
        ang = (RNG.choice([-1, 1]) * RNG.uniform(0.5, 1.2)) + (-math.pi / 2)
        length = RNG.uniform(90, 200) * (1 - 0.4 * t)
        end = start + length * np.array([math.cos(ang), math.sin(ang)])
        end = np.clip(end, 20, CELL - 20)
        d.line([tuple(start), tuple(end)], fill=twig, width=3)
        pts += [start + (end - start) * s for s in np.linspace(0.2, 1, 6)]
    pts = np.array(pts)
    for i in range(n_leaves):
        p = pts[RNG.integers(len(pts))] + RNG.normal(0, leaf_px * 0.6, 2)
        if not (leaf_px / 2 < p[0] < CELL - leaf_px / 2 and leaf_px / 2 < p[1] < CELL - leaf_px / 2):
            continue
        s = sprites[RNG.integers(len(sprites))]
        scale = leaf_px * RNG.uniform(0.75, 1.25) / max(s.size)
        s = s.resize((max(2, int(s.size[0] * scale)), max(2, int(s.size[1] * scale))), Image.LANCZOS)
        depth = np.linalg.norm((p - [CELL / 2, CELL / 2]) / (CELL / 2))
        jitter = RNG.uniform(0.78, 1.12) * (0.82 + 0.18 * min(depth, 1.0)) * np.array([RNG.uniform(.93, 1.07), 1, RNG.uniform(.9, 1.1)])
        s = graded(s, target, jitter).rotate(RNG.uniform(0, 360), expand=True, resample=Image.BICUBIC)
        img.alpha_composite(s, (int(p[0] - s.size[0] / 2), int(p[1] - s.size[1] / 2)))
    a = np.asarray(img).copy()
    a[..., 3] = np.where(a[..., 3] > 110, 255, 0)  # hard edge for alpha test
    return a


def dilate_rgb(a, iters=8):
    """Bleed opaque colour into transparent texels (avoids dark mip halos)."""
    rgb = a[..., :3].astype(np.float32)
    m = a[..., 3] > 0
    for _ in range(iters):
        acc = np.zeros_like(rgb); cnt = np.zeros(m.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sm = np.roll(m, (dy, dx), (0, 1)); sr = np.roll(rgb, (dy, dx), (0, 1))
            acc += sr * sm[..., None]; cnt += sm
        grow = ~m & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow, None]
        m = m | grow
    out = a.copy(); out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return out


def main():
    (OUT / 'previews').mkdir(parents=True, exist_ok=True)
    manifest = dict(license='ambientCG CC0 1.0 (leaves/bark/grass); BEV orthophoto CC BY 4.0', outputs={})
    # ---- foliage atlas
    species = [  # name, leaf set, target sRGB, leaves, leaf px, conifer
        ('beech', 'LeafSet014', (64, 92, 36), 520, 34, False),
        ('oak', 'LeafSet016', (60, 84, 34), 430, 40, False),
        ('conifer', 'LeafSet019', (40, 62, 36), 120, 120, True),
        ('shrub', 'LeafSet024', (70, 98, 40), 480, 34, False),
    ]
    atlas = np.zeros((4 * CELL, 4 * CELL, 4), np.uint8)
    for r, (name, src, target, n, px, con) in enumerate(species):
        sprites = leaf_sprites(src)
        for c in range(4):
            atlas[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = cluster_cell(sprites, target, n, px, con)
        print('foliage', name, len(sprites), 'sprites', flush=True)
    atlas = dilate_rgb(atlas)
    Image.fromarray(atlas).save(OUT / 'previews/foliage.png')
    manifest['outputs']['foliage'] = write_dds(OUT / 'v004_foliage.dds', atlas, alpha_test=True)
    manifest['foliage_layout'] = dict(rows=['beech', 'oak', 'conifer', 'shrub'], cols=4, cell_px=CELL)
    # ---- bark atlas
    bark = np.zeros((1024, 1024, 4), np.uint8); bark[..., 3] = 255
    for i, (src, tint) in enumerate((('Bark011', (0.58, 0.58, 0.55)), ('Bark012', (0.62, 0.58, 0.54)),
                                     ('Bark014', (0.6, 0.53, 0.48)), ('Bark011', (0.45, 0.43, 0.38)))):
        im = Image.open(SRC / f'{src}_1K-PNG/{src}_1K-PNG_Color.png').convert('RGB').resize((256, 1024), Image.LANCZOS)
        bark[:, i * 256:(i + 1) * 256, :3] = np.clip(np.asarray(im) * np.array(tint), 0, 255)
    Image.fromarray(bark).save(OUT / 'previews/bark.png')
    manifest['outputs']['bark'] = write_dds(OUT / 'v004_bark.dds', bark)
    manifest['bark_layout'] = dict(strips=['beech', 'oak', 'conifer', 'shrub'], strip_u=0.25)
    # ---- grass multiply-detail (mean ~0.82, mild chroma)
    g = np.asarray(Image.open(SRC / 'Grass005_2K-JPG/Grass005_2K-JPG_Color.jpg').convert('RGB').resize((1024, 1024), Image.LANCZOS)).astype(np.float32)
    lum = g.mean(-1, keepdims=True)
    chroma = g / np.maximum(lum, 1)
    det = (lum / lum.mean()) ** 0.8 * 0.82
    det = det * (0.7 + 0.3 * chroma)
    det = np.clip(det * 255, 0, 255)
    detail = np.dstack([det, np.full(det.shape[:2], 255.0)]).astype(np.uint8)
    Image.fromarray(detail).save(OUT / 'previews/grass_detail.png')
    manifest['outputs']['grass_detail'] = write_dds(OUT / 'v004_grass_detail.dds', detail)
    manifest['grass_detail_mean'] = float(det.mean() / 255)
    # ---- ortho chunks: alpha 0 (detail at full strength) + mips
    for p in sorted(V3.glob('v003_ortho_*.dds')):
        rgba = read_bgra_dds(p)
        rgba[..., 3] = 0
        k = p.stem.split('_')[-1]
        manifest['outputs'][f'ortho_{k}'] = write_dds(OUT / f'v004_ortho_{k}.dds', rgba)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('done', sum(v['bytes'] for v in manifest['outputs'].values()))


if __name__ == '__main__' and 'impostors' not in __import__('sys').argv:
    main()


def build_impostor_atlas():
    """4x4 atlas of Blender-rendered impostor sprites (rows: beech, oak, conifer, shrub)."""
    src = OUT / 'impostor_renders'
    meta = json.loads((src / 'meta.json').read_text())
    atlas = np.zeros((4 * CELL, 4 * CELL, 4), np.uint8)
    for r, sp in enumerate(('beech', 'oak', 'conifer', 'shrub')):
        for c in range(4):
            a = np.asarray(Image.open(src / f'{sp}_{c}.png').convert('RGBA').resize((CELL, CELL), Image.LANCZOS)).copy()
            a[..., 3] = np.where(a[..., 3] > 140, 255, 0)
            atlas[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = a
    atlas = dilate_rgb(atlas)
    Image.fromarray(atlas).save(OUT / 'previews/impostors.png')
    m = json.loads((OUT / 'manifest.json').read_text())
    m['outputs']['impostors'] = write_dds(OUT / 'v004_impostors.dds', atlas, alpha_test=True)
    m['impostor_meta'] = meta
    (OUT / 'manifest.json').write_text(json.dumps(m, indent=2) + '\n')


if __name__ == '__main__' and 'impostors' in __import__('sys').argv:
    build_impostor_atlas()
