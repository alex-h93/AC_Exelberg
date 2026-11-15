#!/usr/bin/env python3
"""v010 bounded acquisition for the roundabout extension (BEV DTM, DSM, orthophoto; CC BY 4.0).

Default: plan only (prints tile counts / uncached bytes). --pixels downloads (HTTP byte ranges, one retry).
Fresh ledgers in NEW cache folders, so the hash-pinned v002/v004 ledgers stay byte-identical:
  data/raw/terrain_v010/, data/raw/surface_dsm_v010/  (cap 100 MB each)
  data/raw/orthophoto_v010/                            (cap 60 MB)
Outputs data/processed/extension_v010/:
  dtm_3035.tif, dsm_3035.tif, chm_3035.tif (+ summary.json)  whole 512 m source tiles within RADIUS of the extension
  ortho_1m.png + ortho.json                                   1 m/px, 1024 m square around the extension, local EPSG:25833
"""
import argparse
import io
import json
import math
from functools import lru_cache
from pathlib import Path

import imagecodecs
import numpy as np
import tifffile
from pyproj import Transformer, network
from pyproj.transformer import TransformerGroup

import acquire_surface_v004 as S4
from extract_terrain import URL as DTM_URL, selected_blocks
from inspect_orthophoto import decode, georef as ortho_georef, metadata as ortho_metadata, scalar
from probe_raster_metadata import URLS
from probe_surface_dsm import URL as DSM_URL
from terrain_ranges import RangeReader, save_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/extension_v010'
EXT = OUT / 'osm_extension.json'
RADIUS = 400
ORTHO_SIZE, ORTHO_RES = 1024, 1.0
CAPS = dict(dtm=100_000_000, dsm=100_000_000, ortho=60_000_000)


def ext_xy_local():
    e = json.loads(EXT.read_text())
    return np.array(e['polyline_local_m']), np.array(e['origin_25833'])


def mosaic(remote, xy3035, label, download):
    tags, meta = S4.metadata(remote)
    transform = S4.georef(tags)
    width, height = S4.scalar(tags, 256), S4.scalar(tags, 257)
    offsets, counts = tags[324]['values'], tags[325]['values']
    blocks = selected_blocks(xy3035, transform, width, height, radius=RADIUS)
    ranges = [(offsets[i], counts[i]) for i in blocks]
    needed = remote.preflight(ranges)
    print(f'{label}: {len(blocks)} tiles, uncached {needed:,} bytes, ledger {remote.used_bytes:,}', flush=True)
    if not download:
        return None
    nx = math.ceil(width / 512)
    rows, cols = [i // nx for i in blocks], [i % nx for i in blocks]
    r0, c0 = min(rows), min(cols)
    grid = np.full(((max(rows) + 1 - r0) * 512, (max(cols) + 1 - c0) * 512), S4.NODATA, np.float32)
    with tifffile.TiffFile(io.BytesIO(meta)) as tif:
        page = tif.pages[0]
        for i, (o, n) in zip(blocks, ranges):
            tile = page.decode(remote.read(o, n), i)[0].reshape(512, 512).copy()
            rr, cc = i // nx, i % nx
            grid[(rr - r0) * 512:(rr - r0 + 1) * 512, (cc - c0) * 512:(cc - c0 + 1) * 512] = tile
    x0, y0, sx, sy = transform
    return grid, (x0 + c0 * 512 * sx, y0 - r0 * 512 * sy, sx, sy), blocks, remote.used_bytes


def surfaces(download):
    xy, origin = ext_xy_local()
    x, y = Transformer.from_crs(25833, 3035, always_xy=True).transform(xy[:, 0] + origin[0], xy[:, 1] + origin[1])
    xy3035 = np.column_stack([x, y])
    dsm = mosaic(RangeReader(DSM_URL, ROOT / 'data/raw/surface_dsm_v010', cap=CAPS['dsm']), xy3035, 'DSM', download)
    dtm = mosaic(RangeReader(DTM_URL, ROOT / 'data/raw/terrain_v010', cap=CAPS['dtm']), xy3035, 'DTM', download)
    if not download:
        return
    (gs, ts, bs, bytes_s), (gt, tt, bt, bytes_t) = dsm, dtm
    assert ts == tt and bs == bt and gs.shape == gt.shape, 'DSM/DTM grids differ'
    valid = (gs != S4.NODATA) & (gt != S4.NODATA) & np.isfinite(gs) & np.isfinite(gt)
    chm = np.full_like(gs, S4.NODATA)
    chm[valid] = np.clip(gs[valid] - gt[valid], 0, None)
    hashes = {n: S4.write(OUT / f'{n}_3035.tif', g, ts) for n, g in (('dsm', gs), ('dtm', gt), ('chm', chm))}
    save_json(OUT / 'surface_summary.json', dict(radius_m=RADIUS, tiles=len(bs), transform=ts, shape=list(gs.shape),
                                                 valid_pixels=int(valid.sum()), dsm_ledger_bytes=bytes_s, dtm_ledger_bytes=bytes_t,
                                                 sha256=hashes, license='BEV ALS DSM/DTM, CC BY 4.0'))


def ortho(download):
    xy, origin = ext_xy_local()
    c = (xy.min(0) + xy.max(0)) / 2
    west, south = np.floor(c - ORTHO_SIZE / 2)
    n = int(ORTHO_SIZE / ORTHO_RES)
    xx, yy = np.meshgrid(west + (np.arange(n) + .5) * ORTHO_RES, south + ORTHO_SIZE - (np.arange(n) + .5) * ORTHO_RES)
    remote = RangeReader(URLS['orthophoto'], ROOT / 'data/raw/orthophoto_v010', cap=CAPS['ortho'])
    tags, meta, _next, _mb = ortho_metadata(remote)
    affine = ortho_georef(tags)
    width, height = scalar(tags, 256), scalar(tags, 257)
    offsets, counts = tags[324]['values'], tags[325]['values']
    nx = math.ceil(width / 512)
    network.set_network_enabled(False)
    tr = TransformerGroup(25833, 31256, always_xy=True, allow_ballpark=False).transformers[0]
    assert tr.accuracy == 1.5, 'expected the reviewed 1.5 m operation'
    sx, sy = tr.transform(xx + origin[0], yy + origin[1])
    x0, y0, dx, dy = affine
    cols = np.floor((sx - x0) / dx).astype(np.int64)
    rows = np.floor((y0 - sy) / dy).astype(np.int64)
    assert ((cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)).all(), 'outside orthophoto footprint'
    ids = (rows // 512) * nx + cols // 512
    tiles = np.unique(ids).tolist()
    needed = remote.preflight([(offsets[i], counts[i]) for i in tiles])
    print(f'ORTHO: {len(tiles)} tiles, uncached {needed:,} bytes, ledger {remote.used_bytes:,}', flush=True)
    if not download:
        return
    with tifffile.TiffFile(io.BytesIO(meta)) as tf:
        page = tf.pages[0]

        @lru_cache(maxsize=32)
        def tile(i):
            return decode(page, remote.read(offsets[i], counts[i]), i)
        rgb = np.zeros((n, n, 3), np.uint8)
        for i in tiles:
            m = ids == i
            rgb[m] = tile(i)[rows[m] % 512, cols[m] % 512]
    (OUT / 'ortho_1m.png').write_bytes(imagecodecs.png_encode(rgb))
    save_json(OUT / 'ortho.json', dict(local_bounds=[float(west), float(south), float(west + ORTHO_SIZE), float(south + ORTHO_SIZE)],
                                       resolution_m=ORTHO_RES, size_px=n, tiles=len(tiles), ledger_bytes=remote.used_bytes,
                                       resampling='nearest source pixel per 1 m texel centre; no colour grading',
                                       uv='u=(E-west)/size, v=(N-south)/size; PNG row 0 = north',
                                       attribution='© BEV, CC BY 4.0', source=URLS['orthophoto']))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pixels', action='store_true')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    surfaces(a.pixels)
    ortho(a.pixels)


if __name__ == '__main__':
    main()
