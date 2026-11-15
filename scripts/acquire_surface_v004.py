#!/usr/bin/env python3
"""User-approved (2026-11-15) ±400 m corridor: BEV DSM tiles + extra DTM tiles.

Writes, without touching existing products:
  data/processed/surface_v004/dsm_400_3035.tif   surface model (first returns)
  data/processed/surface_v004/dtm_400_3035.tif   bare earth on the same grid
  data/processed/surface_v004/chm_400_3035.tif   DSM - DTM (>= 0, nodata -9999)
  data/processed/surface_v004/summary.json
DTM tiles already cached by the original operation are reused from its ledger.

PROVENANCE NOTE (2026-11-15): the run appended 24 DTM tiles (15,521,017 bytes) to
data/raw/terrain/operation.json. Because earlier manifests pin that ledger's hash, the
original ledger was restored byte-exactly afterwards and the extended ledger was kept as
data/raw/terrain/operation_v004_extended.json (the extra range-*.bin files remain in
data/raw/terrain/). To re-run offline, temporarily swap in the extended ledger.
"""
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer
import tifffile

from extract_terrain import metadata, georef, scalar, selected_blocks, URL as DTM_URL
from terrain_ranges import RangeReader, save_json
from probe_surface_dsm import URL as DSM_URL, RAW as DSM_RAW, CAP as DSM_CAP

RADIUS = 400
NODATA = -9999.0
OUT = Path('data/processed/surface_v004')


def route_xy():
    coords = np.array(json.loads(Path('data/processed/route.geojson').read_text())
                      ['features'][0]['geometry']['coordinates'])[:, :2]
    x, y = Transformer.from_crs(4326, 3035, always_xy=True).transform(coords[:, 0], coords[:, 1])
    return np.column_stack([x, y])


def mosaic(remote, xy, label):
    tags, meta = metadata(remote)
    transform = georef(tags)
    width, height = scalar(tags, 256), scalar(tags, 257)
    offsets, counts = tags[324]['values'], tags[325]['values']
    blocks = selected_blocks(xy, transform, width, height, radius=RADIUS)
    ranges = [(offsets[i], counts[i]) for i in blocks]
    needed = remote.preflight(ranges)
    print(f'{label}: {len(blocks)} tiles, uncached {needed} bytes', flush=True)
    nx = math.ceil(width / 512)
    rows, cols = [i // nx for i in blocks], [i % nx for i in blocks]
    r0, c0 = min(rows), min(cols)
    grid = np.full(((max(rows) + 1 - r0) * 512, (max(cols) + 1 - c0) * 512), NODATA, np.float32)
    with tifffile.TiffFile(io.BytesIO(meta)) as tif:
        page = tif.pages[0]
        for i, (o, n) in zip(blocks, ranges):
            tile = page.decode(remote.read(o, n), i)[0].reshape(512, 512).copy()
            rr, cc = i // nx, i % nx
            if (rr + 1) * 512 > height:
                tile[height - rr * 512:, :] = NODATA
            if (cc + 1) * 512 > width:
                tile[:, width - cc * 512:] = NODATA
            grid[(rr - r0) * 512:(rr - r0 + 1) * 512, (cc - c0) * 512:(cc - c0 + 1) * 512] = tile
    x0, y0, sx, sy = transform
    return grid, (x0 + c0 * 512 * sx, y0 - r0 * 512 * sy, sx, sy), blocks, remote.state['actual_bytes']


def write(path, grid, t):
    keys = (1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, 3035)
    tifffile.imwrite(path, grid, tile=(512, 512), compression='deflate', metadata=None,
                     extratags=[(33550, 'd', 3, (t[2], t[3], 0), False),
                                (33922, 'd', 6, (0, 0, 0, t[0], t[1], 0), False),
                                (34735, 'H', len(keys), keys, False), (42113, 's', 0, '-9999', False)])
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    xy = route_xy()
    dtm_before = json.loads(Path('data/raw/terrain/operation.json').read_text())['actual_bytes']
    dsm, tdsm, bdsm, dsm_bytes = mosaic(RangeReader(DSM_URL, DSM_RAW, cap=DSM_CAP), xy, 'DSM')
    dtm, tdtm, bdtm, dtm_bytes = mosaic(RangeReader(DTM_URL, Path('data/raw/terrain')), xy, 'DTM')
    if tdsm != tdtm or bdsm != bdtm or dsm.shape != dtm.shape:
        raise ValueError('DSM/DTM grids differ')
    valid = (dsm != NODATA) & (dtm != NODATA) & np.isfinite(dsm) & np.isfinite(dtm)
    chm = np.full_like(dsm, NODATA)
    chm[valid] = np.clip(dsm[valid] - dtm[valid], 0, None)
    hashes = {n: write(OUT / f'{n}_400_3035.tif', g, tdsm) for n, g in (('dsm', dsm), ('dtm', dtm), ('chm', chm))}
    v = chm[valid]
    summary = dict(radius_m=RADIUS, tiles=len(bdsm), transform=tdsm, shape=list(dsm.shape),
                   valid_pixels=int(valid.sum()), invalid_pixels=int((~valid).sum()),
                   chm_percentiles_m={p: float(np.percentile(v, p)) for p in (50, 75, 90, 99, 99.9)},
                   chm_fraction_over_3m=float((v > 3).mean()),
                   dsm_operation_body_bytes=dsm_bytes, dtm_new_body_bytes=dtm_bytes - dtm_before,
                   dtm_operation_body_bytes=dtm_bytes, sha256=hashes,
                   license='BEV ALS DSM/DTM, CC BY 4.0', note='CHM = DSM - DTM, negative clipped to 0; ±0.5 m nominal accuracy')
    save_json(OUT / 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
