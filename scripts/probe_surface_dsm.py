#!/usr/bin/env python3
"""BEV ALS DSM (surface model) corridor estimate — metadata only, no pixel tiles.

Reads the TIFF header, first IFD and its tag payloads (incl. tile offset/count
tables) through the same persistent ledgered RangeReader as the DTM operation,
then reports exact compressed byte totals for several corridor radii.
Pixel acquisition is a separate, user-approved step (not implemented here).
"""
import datetime
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer

from extract_terrain import metadata, georef, scalar, selected_blocks
from terrain_ranges import RangeReader, save_json

URL = 'https://data.bev.gv.at/download/ALS/DSM/20250915/ALS_DSM_CRS3035RES50000mN2800000E4750000.tif'
RAW = Path('data/raw/surface_dsm')
OUT = Path('data/interim/surface_dsm')
CAP = 200_000_000  # whole operation (metadata + any later approved pixels)
RADII = (200, 400, 800)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    remote = RangeReader(URL, RAW, cap=CAP)
    tags, metadata_bytes = metadata(remote)
    transform = georef(tags)
    width, height = scalar(tags, 256), scalar(tags, 257)
    offsets, counts = tags[324]['values'], tags[325]['values']
    if len(offsets) != math.ceil(width / 512) * math.ceil(height / 512) or len(counts) != len(offsets):
        raise ValueError('invalid tile tables')
    route_bytes = Path('data/processed/route.geojson').read_bytes()
    coords = np.array(json.loads(route_bytes)['features'][0]['geometry']['coordinates'])[:, :2]
    x, y = Transformer.from_crs(4326, 3035, always_xy=True).transform(coords[:, 0], coords[:, 1])
    xy = np.column_stack([x, y])
    dtm_tags = json.loads(Path('data/interim/terrain/source-tags.json').read_text())
    encoding = {name: (scalar(tags, t) if t in tags else None) for name, t in
                dict(bits=258, compression=259, predictor=317, tile_w=322, tile_h=323, sample_format=339).items()}
    estimates = {}
    for r in RADII:
        blocks = selected_blocks(xy, transform, width, height, radius=r)
        nbytes = sum(counts[i] for i in blocks)
        estimates[str(r)] = dict(tiles=len(blocks), compressed_bytes=nbytes,
                                 worst_case_with_one_retry=2 * nbytes,
                                 max_tile_bytes=max(counts[i] for i in blocks))
    report = dict(url=URL, generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  source_bytes=remote.state['total'], source_etag=remote.state['etag'],
                  route_sha256=hashlib.sha256(route_bytes).hexdigest(),
                  width=width, height=height, transform=transform, encoding=encoding,
                  nodata=tags.get(42113, {}).get('values'),
                  same_grid_as_dtm=(dtm_tags.get('256', {}).get('values') == [width]
                                    and dtm_tags.get('33922', {}).get('values') == tags[33922]['values']),
                  metadata_body_bytes=remote.state['actual_bytes'], operation_cap=CAP,
                  corridor_estimates=estimates, pixels_acquired=False)
    (OUT / 'source-metadata.tif').write_bytes(metadata_bytes)
    save_json(OUT / 'estimate.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('transform',)}, indent=2))


if __name__ == '__main__':
    main()
