#!/usr/bin/env python3
"""v014 textures (offline, .venv): road, shoulder and verge upgrade (user: "nicer textures for the gras next to the road
... something with a bit more texture" and "alternative textures for the road itself which make it look more realistic").

Sources (ambientCG, CC0; zips kept untouched in data/raw/textures_cc0{,_v014}, read directly from the zip):
  Asphalt015 (road), Gravel023 (shoulder), Grass005 (verge detail), Foliage006/008 blades + Foliage002 seed
  heads (3D grass clumps).
Outputs data/processed/textures_v014/*.dds: DXT1/DXT5 with full mip chains (each level block-compressed by Pillow;
alpha-tested atlas mips keep their coverage), previews/*.png, manifest.json.

UV conventions of the existing meshes (measured on the v013 main KN5): road/gravel/paint are world-planar at 6 m per UV
unit; orthophoto ground ~1011 m per UV unit (detail tile = 1011 m / detailUVMultiplier).
  v014_asphalt.dds      2048, 6 m tile = 4x4 Asphalt015 tiles (1.5 m each); alpha 0 (= detail at full strength)
  v014_asphalt_nm.dds   2048, same tiling, DirectX normal
  v014_asphalt_maps.dds 1024, R specular (from roughness), G gloss, B reflection 0
  v014_asphalt_macro.dds 1024, multiply detail at 0.1 x UV = 60 m tile: low-frequency wear, darker repair patches,
                         bitumen crack-seal lines (procedural)
  v014_gravel.dds / _nm  1024, 6 m tile = 4x4 Gravel023 tiles
  v014_grass_detail.dds  2048, multiply detail, 5 m tile: 2x2 Grass005, gentle periodic brightness variation
  v014_grass_nm.dds      2048, matching normal detail
  v014_flat_nm.dds, v014_maps_matte.dds  4x4 constants (flat normal; low spec, no reflection)
  v014_grass_clumps.dds  2048 alpha-tested atlas, 4 x 2 clump sprites (row 0: short blades, row 1: tall + seed heads)
"""
import hashlib
import io
import json
import struct
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/processed/textures_v014'
RNG = np.random.default_rng(14014)


# ---------------------------------------------------------------- io
def zimg(zipname, member, mode='RGB'):
    for d in ('textures_cc0', 'textures_cc0_v014'):
        p = RAW / d / zipname
        if p.exists():
            with zipfile.ZipFile(p) as z:
                return np.asarray(Image.open(io.BytesIO(z.read(member))).convert(mode)).astype(np.float32)
    raise FileNotFoundError(zipname)


def src(asset, res, kind, ext):
    mode = 'L' if kind in ('Roughness', 'Opacity', 'Displacement') else 'RGB'
    return zimg(f'{asset}_{res}.zip', f'{asset}_{res}_{kind}.{ext}', mode)


def resize(a, size):
    a = np.clip(a, 0, 255).astype(np.uint8)
    return np.asarray(Image.fromarray(a).resize((size, size), Image.LANCZOS)).astype(np.float32)


def mips(rgba, alpha_test):
    levels = [rgba.astype(np.float32)]
    cover0 = (rgba[..., 3] > 127).mean() if alpha_test else None
    while levels[-1].shape[0] > 1:
        a = levels[-1]
        al = a[..., 3:4] / 255.0 if alpha_test else np.ones_like(a[..., 3:4])
        pm = a[..., :3] * al
        s4 = lambda x: x[0::2, 0::2] + x[1::2, 0::2] + x[0::2, 1::2] + x[1::2, 1::2]
        sa = s4(al)
        rgb = np.where(sa > 1e-4, s4(pm) / np.maximum(sa, 1e-4), s4(a[..., :3]) / 4)
        b = np.concatenate([rgb, s4(a[..., 3:4]) / 4], -1)
        if alpha_test and b.shape[0] > 2:
            lo, hi = 0.5, 4.0
            for _ in range(18):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if (np.clip(b[..., 3] * mid, 0, 255) > 127).mean() < cover0 else (lo, mid)
            b[..., 3] = np.clip(b[..., 3] * hi, 0, 255)
        levels.append(b)
    return [np.clip(l + 0.5, 0, 255).astype(np.uint8) for l in levels]


def write_dds(name, rgba, fmt, alpha_test=False):
    """Block-compressed DDS (DXT1/DXT5) with a full mip chain; each level compressed by Pillow."""
    h, w = rgba.shape[:2]
    assert h == w and h & (h - 1) == 0
    body = []
    for lv in mips(rgba, alpha_test):
        im = lv if lv.shape[0] >= 4 else np.pad(lv, ((0, 4 - lv.shape[0]), (0, 4 - lv.shape[1]), (0, 0)), mode='edge')
        b = io.BytesIO()
        Image.fromarray(im, 'RGBA').save(b, 'DDS', pixel_format=fmt)
        d = b.getvalue()
        assert d[84:88] == fmt.encode(), d[84:88]
        n = max(1, lv.shape[0] // 4) ** 2 * (8 if fmt == 'DXT1' else 16)
        assert len(d) - 128 == n, (len(d), n)
        body.append(d[128:])
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000  # caps|height|width|pixelformat|mipmapcount|linearsize
    pf = struct.pack('<2I4s5I', 32, 0x4, fmt.encode(), 0, 0, 0, 0, 0)
    caps = 0x1000 | 0x8 | 0x400000
    header = b'DDS ' + struct.pack('<7I', 124, flags, h, w, len(body[0]), 0, len(body)) + b'\0' * 44 + pf + struct.pack('<5I', caps, 0, 0, 0, 0)
    assert len(header) == 128
    p = OUT / name
    p.write_bytes(header + b''.join(body))
    pv = np.clip(rgba, 0, 255).astype(np.uint8)
    Image.fromarray(pv[..., :3] if not alpha_test else pv).resize((min(w, 1024),) * 2).save(OUT / 'previews' / (p.stem + '.png'))
    return dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, size=[w, h], format=fmt, mips=len(body),
                sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def tile(a, n):
    return np.tile(a, (n, n, 1) if a.ndim == 3 else (n, n))


def rgba(rgb, a):
    return np.dstack([rgb, np.broadcast_to(a, rgb.shape[:2]) if np.ndim(a) < 2 else a]).astype(np.float32)


def periodic_noise(size, octaves, rng, base=4):
    """Tileable fBm in [0,1]: sum of random-phase Fourier components with integer frequencies (periodic on the tile)."""
    y, x = np.mgrid[0:size, 0:size] / size
    out = np.zeros((size, size))
    amp = 1.0
    for o in range(octaves):
        f = base * 2 ** o
        for _ in range(6):
            kx, ky = rng.integers(-f, f + 1, 2)
            if kx == 0 and ky == 0:
                continue
            out += amp * np.cos(2 * np.pi * (kx * x + ky * y) + rng.uniform(0, 2 * np.pi))
        amp *= 0.55
    return (out - out.min()) / (out.max() - out.min())


def nm_tile(nm_rgb, n, size):
    return tile(resize(nm_rgb, size // n), n)


# ---------------------------------------------------------------- road
def asphalt(man):
    c = src('Asphalt015', '2K-JPG', 'Color', 'jpg')
    lum = c.mean(-1, keepdims=True)
    c = lum + (c - lum) * 0.55                       # slightly desaturated
    c = c * (88.0 / c.mean())                        # medium-dark grey (sRGB mean ~88; v002 was ~35)
    col = tile(resize(c, 512), 4)
    man['asphalt'] = write_dds('v014_asphalt.dds', rgba(col, 0.0), 'DXT5')
    nm = src('Asphalt015', '2K-JPG', 'NormalDX', 'jpg')
    man['asphalt_nm'] = write_dds('v014_asphalt_nm.dds', rgba(nm_tile(nm, 4, 2048), 255.0), 'DXT1')
    r = src('Asphalt015', '2K-JPG', 'Roughness', 'jpg')
    spec = 255 * np.clip(0.35 + 0.65 * (1 - r / 255.0) ** 1.5 * 1.6, 0, 1)
    spec = tile(resize(spec, 256), 4)
    maps = np.dstack([spec, np.full_like(spec, 110.0), np.zeros_like(spec)])
    man['asphalt_maps'] = write_dds('v014_asphalt_maps.dds', rgba(maps, 255.0), 'DXT1')
    # macro multiply detail, 60 m tile at 1024 px (5.9 cm/px)
    S = 1024
    n = periodic_noise(S, 5, RNG, base=2)
    m = 0.86 + 0.14 * n                              # broad wear / bitumen variation
    yy, xx = np.mgrid[0:S, 0:S]
    for _ in range(9):                               # repair patches (rectangles 1.2-4 m, randomly oriented)
        cx, cy = RNG.uniform(0, S, 2)
        a = RNG.uniform(0, np.pi)
        hw, hh = RNG.uniform(10, 34, 2)
        dx = (xx - cx + S / 2) % S - S / 2
        dy = (yy - cy + S / 2) % S - S / 2
        u, v = dx * np.cos(a) + dy * np.sin(a), -dx * np.sin(a) + dy * np.cos(a)
        edge = np.minimum(hw - np.abs(u), hh - np.abs(v))
        m = np.where(edge > 0, m * RNG.uniform(0.82, 0.9) * (0.97 + 0.03 * n), m)
    seal = np.zeros((S, S))
    for _ in range(14):                              # bitumen crack-seal lines (meandering, ~4-6 cm)
        p = RNG.uniform(0, S, 2)
        ang = RNG.uniform(0, 2 * np.pi)
        for _ in range(int(RNG.uniform(60, 220))):
            ang += RNG.normal(0, 0.18)
            p = (p + 1.0 * np.array([np.cos(ang), np.sin(ang)])) % S
            seal[int(p[1]), int(p[0])] = 1
    seal = np.clip(ndimage.gaussian_filter(seal, 0.6, mode='wrap') * 3, 0, 1)
    m = m * (1 - 0.45 * seal)
    m = 255 * np.clip(m, 0, 1)
    man['asphalt_macro'] = write_dds('v014_asphalt_macro.dds', rgba(np.dstack([m, m, m]), 255.0), 'DXT1')
    man['asphalt_macro_mean'] = float(m.mean() / 255)


def gravel(man):
    c = src('Gravel023', '1K-PNG', 'Color', 'png')
    c = c * (118.0 / c.mean())
    man['gravel'] = write_dds('v014_gravel.dds', rgba(tile(resize(c, 256), 4), 0.0), 'DXT5')
    nm = src('Gravel023', '1K-PNG', 'NormalDX', 'png')
    man['gravel_nm'] = write_dds('v014_gravel_nm.dds', rgba(nm_tile(nm, 4, 1024), 255.0), 'DXT1')


# ---------------------------------------------------------------- ground grass
def grass(man):
    """Grass005 only (2x2 = 5 m tile; a Grass004 mix gave visible light/dark blotches) with a gentle periodic brightness
    variation; stronger contrast than v004, mild chroma; mean ~0.84 so the orthophoto is not darkened overall."""
    S = 2048
    col = tile(resize(src('Grass005', '2K-JPG', 'Color', 'jpg'), S // 2), 2)
    nm = tile(resize(src('Grass005', '2K-JPG', 'NormalDX', 'jpg'), S // 2), 2)
    lum = col.mean(-1, keepdims=True)
    chroma = col / np.maximum(lum, 1)
    det = (lum / lum.mean()) ** 1.25 * (0.75 + 0.25 * chroma)
    det = det * (0.9 + 0.1 * periodic_noise(S, 3, RNG, base=2)[..., None])
    det = 255 * np.clip(det * (0.84 / det.mean()), 0, 1)
    man['grass_detail'] = write_dds('v014_grass_detail.dds', rgba(det, 255.0), 'DXT1')
    man['grass_detail_mean'] = float(det.mean() / 255)
    v = nm / 127.5 - 1
    v[..., :2] *= 1.3
    v /= np.linalg.norm(v, axis=-1, keepdims=True)
    man['grass_nm'] = write_dds('v014_grass_nm.dds', rgba((v + 1) * 127.5, 255.0), 'DXT1')


# ---------------------------------------------------------------- 3D clump atlas
def blades(asset, rotate=0):
    col = src(asset, '1K-PNG', 'Color', 'png')
    op = src(asset, '1K-PNG', 'Opacity', 'png')
    if rotate:
        col, op = np.rot90(col, rotate), np.rot90(op, rotate)
    lab, n = ndimage.label(op > 100)
    out = []
    for sl in ndimage.find_objects(lab):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if h < 120:
            continue
        out.append((col[sl], op[sl] * (lab[sl] > 0)))
    return out


def clump(cell_w, cell_h, parts, n, rng, tint):
    canvas = np.zeros((cell_h, cell_w, 4), np.float32)
    for _ in range(n):
        c, o = parts[rng.integers(len(parts))]
        hgt = rng.uniform(0.55, 0.98) * cell_h
        sc = hgt / c.shape[0]
        im = Image.fromarray(np.dstack([c, o]).astype(np.uint8), 'RGBA')
        im = im.resize((max(2, int(c.shape[1] * sc * rng.uniform(0.35, 0.55))), max(2, int(hgt))), Image.LANCZOS)  # thin blades
        im = im.rotate(rng.normal(0, 9), resample=Image.BICUBIC, expand=True)
        if rng.random() < 0.5:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if im.size[0] > cell_w * 0.7:
            f = cell_w * 0.7 / im.size[0]
            im = im.resize((max(2, int(im.size[0] * f)), max(2, int(im.size[1] * f))), Image.LANCZOS)
        a = np.asarray(im).astype(np.float32)
        a[..., :3] *= np.array(tint) * rng.uniform(0.8, 1.1)
        x0 = int(np.clip(rng.normal(cell_w / 2, cell_w / 7) - a.shape[1] / 2, 0, cell_w - a.shape[1]))
        y0 = cell_h - a.shape[0]
        if y0 < 0:
            a = a[-y0:]; y0 = 0
        reg = canvas[y0:y0 + a.shape[0], x0:x0 + a.shape[1]]
        al = a[..., 3:4] / 255.0
        reg[..., :3] = reg[..., :3] * (1 - al) + a[..., :3] * al
        reg[..., 3:] = np.maximum(reg[..., 3:], a[..., 3:])
    return canvas


def clump_atlas(man):
    short = blades('Foliage006') + blades('Foliage008', rotate=1)
    seeds = blades('Foliage002')
    S, cw, ch = 2048, 512, 1024
    atlas = np.zeros((S, S, 4), np.float32)
    tints = [(0.95, 1.0, 0.85), (1.0, 1.0, 0.8), (1.05, 1.0, 0.75), (0.9, 1.0, 0.9)]
    for k in range(4):   # row 0 (top half of the image = v 0..0.5): short dense blades
        atlas[0:ch, k * cw:(k + 1) * cw] = clump(cw, ch, short, 60, RNG, tints[k])
    for k in range(4):   # row 1: taller mix with seed heads
        parts = short + seeds * (2 if k % 2 else 1)
        atlas[ch:, k * cw:(k + 1) * cw] = clump(cw, ch, parts, 44, RNG, tints[(k + 2) % 4])
    # transparent texels take the mean blade colour (no dark fringes in mips)
    m = atlas[..., 3] > 20
    atlas[~m, :3] = atlas[m, :3].mean(0)
    atlas[..., 3] = np.where(atlas[..., 3] > 110, 255, 0)
    man['grass_clumps'] = write_dds('v014_grass_clumps.dds', atlas, 'DXT5', alpha_test=True)
    man['grass_clumps_layout'] = dict(cols=4, rows=2, row0='short blades', row1='tall + seed heads', coverage=float(m.mean()))


def main():
    (OUT / 'previews').mkdir(parents=True, exist_ok=True)
    man = dict(sources='ambientCG CC0: Asphalt015, Gravel023, Grass005, Foliage002, Foliage006, Foliage008')
    asphalt(man)
    gravel(man)
    grass(man)
    clump_atlas(man)
    man['flat_nm'] = write_dds('v014_flat_nm.dds', rgba(np.full((4, 4, 3), [128.0, 128.0, 255.0]), 255.0), 'DXT1')
    man['maps_matte'] = write_dds('v014_maps_matte.dds', rgba(np.full((4, 4, 3), [80.0, 60.0, 0.0]), 255.0), 'DXT1')
    (OUT / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
    print(json.dumps({k: (v['bytes'] if isinstance(v, dict) and 'bytes' in v else v) for k, v in man.items()}, indent=1))


if __name__ == '__main__':
    main()
