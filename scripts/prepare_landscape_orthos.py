#!/usr/bin/env python3
"""Prepare native-colour terrain backdrops; default offline planning, --pixels acquires.

Run from repository root. One persistent orthophoto operation, never a new cap.
"""
import argparse
from functools import lru_cache
import io
import json
import math
from pathlib import Path

import imagecodecs
import numpy as np
from pyproj import network
from pyproj.transformer import TransformerGroup
import tifffile

from extract_terrain import OfflineOpener
from inspect_orthophoto import CAP, RAW, decode, georef, metadata, png, scalar
from probe_raster_metadata import ProbeError, URLS
from terrain_ranges import MAX_RANGE, RangeReader, digest, save_json

OUT = Path('data/processed/landscape_orthos_v003')
INTERIM = Path('data/interim/landscape_orthos_v003')
TERRAIN = Path('data/processed/full_track_inputs/terrain.npz')
INPUT_MANIFEST = TERRAIN.with_name('manifest.json')


class CachedRanges(RangeReader):
    """Reuse exact or contained ranges, including previous coalesced requests."""
    @lru_cache(maxsize=4)
    def block(self, start, size):
        return super().cached(start, size)

    def covering(self, start, size):
        for key in self.state['cache']:
            a, n = map(int, key.split('-'))
            if a <= start and start + size <= a + n:
                return a, n
        return None

    def cached(self, start, size):
        bounds = self.covering(start, size)
        if bounds is None:
            return None
        a, n = bounds
        return self.block(a, n)[start-a:start-a+size]


def coalesce(ranges, max_gap=65536):
    """Merge nearby ranges, charging every gap, never exceed HTTP range cap."""
    result = []
    for start, size in sorted(set(ranges)):
        if not 0 < size <= MAX_RANGE:
            raise ProbeError('invalid tile byte count')
        if result:
            a, n = result[-1]
            end = max(a+n, start+size)
            if start <= a+n+max_gap and end-a <= MAX_RANGE:
                result[-1] = (a, end-a)
                continue
        result.append((start, size))
    return result


def target_grid(x, y, valid, bounds):
    """North-up 2 m texel centres, masked by containing original valid cell."""
    west, south, east, north = bounds
    w, h = math.ceil((east-west)/2), math.ceil((north-south)/2)
    if not 0 < max(w, h) <= 512:
        raise ProbeError('chunk exceeds 512 texture limit')
    dx, dy = (east-west)/w, (north-south)/h
    xx, yy = np.meshgrid(west+(np.arange(w)+.5)*dx, north-(np.arange(h)+.5)*dy)
    c = np.searchsorted(x, xx, side='right')-1
    r = np.searchsorted(y, yy, side='right')-1
    mask = valid[r, c]
    return xx, yy, mask, (west, north, dx, -dy)


def source_samples(xx, yy, transform, affine, width, height):
    sx, sy = transform.transform(xx, yy)
    x0, y0, dx, dy = affine
    cols = np.floor((sx-x0)/dx).astype(np.int64)
    rows = np.floor((y0-sy)/dy).astype(np.int64)
    inside = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)
    return rows, cols, inside


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pixels', action='store_true')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    INTERIM.mkdir(parents=True, exist_ok=True)
    if not (RAW/'operation.json').exists():
        raise ProbeError('existing orthophoto operation required; never create/reset')
    remote = CachedRanges(URLS['orthophoto'], RAW, cap=CAP, opener=OfflineOpener())
    # Metadata MUST already exist. Never use network to discover a selection.
    tags, meta, next_ifd, meta_bytes = metadata(remote)
    (INTERIM/'source-metadata.tif').write_bytes(meta)
    expected = {259:7, 262:6, 277:3, 284:1, 322:512, 323:512}
    if any(scalar(tags, k) != v for k, v in expected.items()) or tags[258]['values'] != [8,8,8]:
        raise ProbeError('unsupported source JPEG contract')
    affine = georef(tags)
    width, height = scalar(tags,256), scalar(tags,257)
    offsets, counts = tags[324]['values'], tags[325]['values']
    nx = math.ceil(width/512)
    if len(offsets) != nx*math.ceil(height/512) or len(offsets) != len(counts):
        raise ProbeError('invalid TIFF tile tables')
    network.set_network_enabled(False)
    group = TransformerGroup(25833, 31256, always_xy=True, allow_ballpark=False)
    transform = group.transformers[0]
    if transform.accuracy != 1.5:
        raise ProbeError('expected reviewed 1.5 m operation; review changed PROJ environment')
    origin = json.loads(INPUT_MANIFEST.read_text())['coordinates']['origin_m']
    terrain = np.load(TERRAIN)
    x, y = terrain['x_m'][0], terrain['y_m'][:,0]
    valid = terrain['valid_cells']
    chunks, selected = [], set()
    for index, (r0,r1,c0,c1) in enumerate(terrain['tile_node_slices']):
        if not valid[r0:r1-1,c0:c1-1].any():
            continue
        bounds = [float(x[c0]), float(y[r0]), float(x[c1-1]), float(y[r1-1])]
        xx, yy, mask, grid = target_grid(x,y,valid,bounds)
        rows, cols, inside = source_samples(xx+origin[0], yy+origin[1], transform, affine, width,height)
        if not inside.all():
            raise ProbeError('texture rectangle extends outside actual source footprint')
        tiles = np.unique((rows[mask]//512)*nx+cols[mask]//512).tolist()
        selected.update(tiles)
        chunks.append(dict(index=index, node_slice=[int(v) for v in (r0,r1,c0,c1)],
            local_bounds=bounds, utm_bounds=[bounds[0]+origin[0],bounds[1]+origin[1],bounds[2]+origin[0],bounds[3]+origin[1]],
            width=int(xx.shape[1]),height=int(xx.shape[0]),local_transform=list(grid),
            utm_transform=[grid[0]+origin[0],grid[1]+origin[1],grid[2],grid[3]],
            tiles=tiles,valid_texels=int(mask.sum()),valid_fraction=float(mask.mean()),
            source_footprint_fraction=float(inside.mean())))
    ranges = [(offsets[i],counts[i]) for i in sorted(selected)]
    if any(o < 0 or o+n > remote.state['total'] for o,n in ranges):
        raise ProbeError('tile outside source object')
    missing = [(o,n) for o,n in ranges if remote.covering(o,n) is None]
    requests = coalesce(missing)
    needed = sum(n for _,n in requests)
    estimate = dict(source_url=remote.state['url'],etag=remote.state['etag'],source_bytes=remote.state['total'],
        operation_cap=CAP,used_before_pixels=remote.used_bytes,metadata_logical_bytes=meta_bytes,
        metadata_additional_bytes=0,selected_tiles=len(selected),selected_compressed_bytes=sum(n for _,n in ranges),
        missing_compressed_bytes=sum(n for _,n in missing),coalescing_gap_bytes=needed-sum(n for _,n in missing),
        additional_request_bytes=needed,retry_reserve_bytes=needed,max_retry=1,
        worst_case_operation_bytes=remote.used_bytes+2*needed,request_count=len(requests),
        ranges=requests,blocks=[dict(index=i,offset=offsets[i],compressed_bytes=counts[i]) for i in sorted(selected)],
        next_ifd_not_followed=next_ifd,source_affine=list(affine),source_dimensions=[width,height],
        target_crs=25833,source_crs=31256,proj_network=False,transform_accuracy_m=transform.accuracy,
        transform_definition=transform.definition,transform_description=transform.description,
        terrain_sha256=digest(TERRAIN.read_bytes()),chunks=chunks)
    save_json(INTERIM/'acquisition-estimate.json',estimate)
    print(f'{len(chunks)} chunks; {len(selected)} tiles; {len(requests)} requests; worst case {estimate["worst_case_operation_bytes"]:,}/{CAP:,} bytes', flush=True)
    remote.preflight(requests, attempts=2)
    if not args.pixels:
        return
    if not args.offline:
        # Same ledger and cap, only now enable bounded HTTP with one retry.
        remote = CachedRanges(URLS['orthophoto'],RAW,cap=CAP)
    for number, (o,n) in enumerate(requests):
        remote.read(o,n)
        print(f'range {number+1}/{len(requests)}; ledger {remote.used_bytes:,}', flush=True)
    thumbnails = []
    with tifffile.TiffFile(io.BytesIO(meta)) as tf:
        page = tf.pages[0]
        if not page.jpegtables:
            raise ProbeError('shared JPEG tables missing')
        @lru_cache(maxsize=24)
        def tile(index):
            return decode(page,remote.read(offsets[index],counts[index]),index)
        for chunk in chunks:
            xx, yy, mask, _ = target_grid(x,y,valid,chunk['local_bounds'])
            rows, cols, inside = source_samples(xx+origin[0],yy+origin[1],transform,affine,width,height)
            rgb = np.zeros((*mask.shape,3),np.uint8)
            ids = (rows//512)*nx+cols//512
            for idx in chunk['tiles']:
                take = mask & (ids==idx)
                rgb[take] = tile(idx)[rows[take]%512,cols[take]%512]
            path = OUT/f'chunk_{chunk["index"]:03d}.png'
            mask_path = path.with_name(path.stem+'_mask.png')
            png(path,rgb)
            png(mask_path,mask.astype(np.uint8)*255)
            if not np.array_equal(imagecodecs.png_decode(path.read_bytes()),rgb):
                raise ProbeError('PNG colour roundtrip mismatch')
            chunk.update(path=str(path),sha256=digest(path.read_bytes()),rgb_sha256=digest(rgb.tobytes()),
                mask_path=str(mask_path),mask_sha256=digest(mask_path.read_bytes()))
            thumb = rgb[::4,::4].copy()
            thumb[~mask[::4,::4]] = [255,0,255]
            thumbnails.append(thumb)
    sheet = np.full((math.ceil(len(chunks)/7)*128,7*128,3),255,np.uint8)
    for i, thumb in enumerate(thumbnails):
        r,c = divmod(i,7)
        sheet[r*128:r*128+thumb.shape[0],c*128:c*128+thumb.shape[1]] = thumb
    png(OUT/'contact_sheet.png',sheet)
    manifest = dict(schema='assetto-exelberg.landscape-orthos',version=3,chunks=chunks,
        acquisition=estimate,actual_response_body_bytes=remote.used_bytes,
        attribution='© BEV, CC BY 4.0',license='https://doi.org/10.48677/1f33a105-0798-4696-92c2-df985c6f40a9',
        decoder='tifffile page.decode with shared JPEGTables, native YCbCr JPEG to uint8 RGB via imagecodecs',
        resampling='Nearest source pixel containing each transformed 2 m target texel centre; no colour grading.',
        uv='u=(E-west)/(east-west); v=(N-south)/(north-south). Blender bottom-up v; PNG row zero is north.',
        validity='Mask is containing original terrain valid_cell AND source rectangular footprint, not semantic imagery nodata. Black is NOT tested for validity. No declared source nodata verified. RGB outside mask is zero padding, never ground.',
        scope='Native ground-colour backdrop only; road textures unchanged. Roofs/canopy are imagery, not terrain geometry or asphalt/camber measurements.',
        capture_date=None,contact_sheet_order=[c['index'] for c in chunks])
    save_json(OUT/'manifest.json',manifest)
    print(f'Completed {len(chunks)} textures; ledger {remote.used_bytes:,} bytes',flush=True)


if __name__ == '__main__':
    main()
