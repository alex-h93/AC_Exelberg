#!/usr/bin/env python3
"""Bounded native-grid BEV imagery inspection. Default metadata only; --pixels opt-in.

Run from project root. --offline forbids HTTP and reuses the same persistent ledger.
No full raster, raster reprojection, corridor bounding-box mosaic or geometry edits.
"""
import argparse
import csv
import io
import json
import math
from pathlib import Path
import struct

import imagecodecs
import numpy as np
import pyproj
from pyproj import CRS, network
from pyproj.enums import TransformDirection
from pyproj.transformer import TransformerGroup
import tifffile

from probe_raster_metadata import header, directory, values, ProbeError, URLS
from terrain_ranges import RangeReader, save_json, digest
from extract_terrain import OfflineOpener, bilinear

RAW = Path('data/raw/orthophoto')
INTERIM = Path('data/interim/orthophoto')
OUT = Path('data/processed/orthophoto')
CAP = 200_000_000
META_CAP = 5_000_000


def metadata(remote):
    chunks = []
    def get(offset, size):
        if sum(len(b) for _, b in chunks) + size > META_CAP:
            raise ProbeError('metadata exceeds 5 MB; stop')
        remote.preflight([(offset, size)], attempts=2)
        data = remote.read(offset, size)
        chunks.append((offset, data))
        return data
    endian, big, first = header(get(0, 16))
    if not big or not 16 <= first <= META_CAP:
        raise ProbeError('unsupported source directory')
    count = struct.unpack(endian + 'Q', get(first, 8))[0]
    if not 1 <= count <= 100:
        raise ProbeError('unsafe IFD size')
    tags, next_ifd = directory(get(first + 8, count * 20 + 8), count, endian, True)
    payloads = [(t['offset'], t['bytes']) for t in tags.values() if 'offset' in t]
    if sum(n for _, n in payloads) + sum(len(b) for _, b in chunks) > META_CAP:
        raise ProbeError('metadata exceeds 5 MB; stop before payloads')
    remote.preflight(payloads, attempts=2)
    for t in tags.values():
        if 'offset' in t:
            if t['offset'] + t['bytes'] > META_CAP:
                raise ProbeError('source metadata sparse extent too large')
            t['values'] = values(get(t['offset'], t['bytes']), t['type'], t['count'], endian)
    buf = bytearray(max(o + len(b) for o, b in chunks))
    for offset, data in chunks:
        buf[offset:offset + len(data)] = data
    struct.pack_into(endian + 'Q', buf, first + 8 + count * 20, 0)
    return tags, bytes(buf), next_ifd, sum(len(b) for _, b in chunks)


def scalar(tags, key):
    return tags[key]['values'][0]


def georef(tags):
    keys = tags[34735]['values']
    keymap = {keys[i]: keys[i+3] for i in range(4, len(keys), 4) if keys[i+1] == 0}
    if keymap.get(3072) != 31256 or keymap.get(1025) != 1 or 34264 in tags:
        raise ProbeError('requires north-up EPSG:31256 PixelIsArea')
    sx, sy, _ = tags[33550]['values']
    i, j, k, x, y, _ = tags[33922]['values']
    if sx <= 0 or sy <= 0 or k != 0:
        raise ProbeError('invalid scale/tiepoint')
    return x-i*sx, y+j*sy, sx, sy


def transformer():
    network.set_network_enabled(False)
    group = TransformerGroup(31256, 4326, always_xy=True, allow_ballpark=False)
    if not group.transformers:
        raise ProbeError('no non-ballpark source transformation')
    # Deliberately use PROJ's first-ranked available operation; record alternatives.
    selected = group.transformers[0]
    def grids(operation):
        return [dict(name=g.short_name, available=g.available, url=g.url)
                for g in operation.grids]
    record = dict(proj_version=pyproj.proj_version_str, networking=False,
        source_axes=[str(a) for a in CRS(31256).axis_info],
        axis_handling='always_xy=True: source easting,northing; WGS84 longitude,latitude. TIFF x=easting,y=northing, despite EPSG native northing,easting axes.',
        best_available=group.best_available, selected=selected.description,
        accuracy_m=selected.accuracy, definition=selected.definition,
        available=[dict(description=t.description, accuracy_m=t.accuracy,
            grids=[g for o in t.operations for g in grids(o)]) for t in group.transformers],
        unavailable=[dict(name=o.name, accuracy_m=o.accuracy, grids=grids(o)) for o in group.unavailable_operations],
        caution='Operation accuracy is not measured imagery/OSM registration accuracy; no submetre alignment claim.')
    return selected, record


def window(center, transform, width, height, side=250):
    x0, y0, sx, sy = transform
    x, y = center
    c0, c1 = math.floor((x-side/2-x0)/sx), math.ceil((x+side/2-x0)/sx)
    r0, r1 = math.floor((y0-y-side/2)/sy), math.ceil((y0-y+side/2)/sy)
    if not 0 <= c0 < c1 <= width or not 0 <= r0 < r1 <= height:
        raise ProbeError('patch outside source')
    return c0, r0, c1, r1


def tile_indices(win, width, tile=512):
    c0, r0, c1, r1 = win
    nx = math.ceil(width/tile)
    return [r*nx+c for r in range(r0//tile, (r1-1)//tile+1)
            for c in range(c0//tile, (c1-1)//tile+1)]


def decode(page, data, index):
    # Tifffile supplies JPEGTables, subsampling and YCbCr->RGB parameters.
    pixels, _, _ = page.decode(data, index, jpegtables=page.jpegtables)
    result = pixels.reshape(512, 512, 3)
    if result.dtype != np.uint8:
        raise ProbeError('unexpected decoded dtype')
    return result


def assemble(win, width, tiles):
    c0, r0, c1, r1 = win
    result = np.empty((r1-r0, c1-c0, 3), np.uint8)
    nx = math.ceil(width/512)
    for idx in tile_indices(win, width):
        r, c = divmod(idx, nx)
        a, b = max(c0, c*512), max(r0, r*512)
        e, f = min(c1, (c+1)*512), min(r1, (r+1)*512)
        result[b-r0:f-r0, a-c0:e-c0] = tiles[idx][b-r*512:f-r*512, a-c*512:e-c*512]
    return result


def stats(rgb):
    black = np.all(rgb == 0, axis=2)
    dark = np.max(rgb, axis=2) <= 5
    return dict(finite_pixels=int(np.isfinite(rgb).all(axis=2).sum()),
        pixels=int(black.size), exact_black_fraction=float(black.mean()),
        near_black_le5_fraction=float(dark.mean()), min=int(rgb.min()), max=int(rgb.max()),
        mean_rgb=rgb.mean(axis=(0,1)).tolist(),
        interpretation='Black/dark are heuristics only, not a validity mask. No declared imagery nodata verified; shadow, canopy and missing imagery cannot be distinguished automatically.')


def overlay(rgb, xy, transform, marker=None):
    out = rgb.copy()
    x0,y0,sx,sy = transform
    pts = np.column_stack(((xy[:,0]-x0)/sx, (y0-xy[:,1])/sy))
    h,w = out.shape[:2]
    for a,b in zip(pts[:-1], pts[1:]):
        if max(a[0],b[0]) < 0 or min(a[0],b[0]) >= w or max(a[1],b[1]) < 0 or min(a[1],b[1]) >= h:
            continue
        n = int(np.max(np.abs(b-a)))+2
        if n > 100000:
            raise ProbeError('unsafe overlay segment')
        p = np.rint(np.linspace(a,b,n)).astype(int)
        for dy in range(-2,3):
            for dx in range(-2,3):
                x,y = p[:,0]+dx,p[:,1]+dy
                ok=(x>=0)&(x<w)&(y>=0)&(y<h)
                out[y[ok],x[ok]] = [255,40,180]
    if marker is not None:
        x,y = round((marker[0]-x0)/sx), round((y0-marker[1])/sy)
        for d in range(-20,21):
            if 0<=x+d<w and 0<=y<h: out[y,x+d]=[0,255,255]
            if 0<=x<w and 0<=y+d<h: out[y+d,x]=[0,255,255]
    return out


def png(path, rgb):
    path.write_bytes(imagecodecs.png_encode(np.ascontiguousarray(rgb)))


def hillshade(transform, shape):
    """Sample existing terrain onto imagery grid only for review, not RGB export."""
    with tifffile.TiffFile('data/processed/terrain_corridor_3035.tif') as tf:
        grid=tf.asarray()
        sx,sy,_=tf.pages[0].tags[33550].value
        _,_,_,x0,y0,_=tf.pages[0].tags[33922].value
    h,w=shape
    # 1 m review grid avoids unnecessary full-resolution terrain interpolation.
    rows,cols=np.mgrid[0:h:5,0:w:5]
    x=transform[0]+(cols+.5)*transform[2]
    y=transform[1]-(rows+.5)*transform[3]
    group=TransformerGroup(31256,3035,always_xy=True,allow_ballpark=False)
    t=group.transformers[0]
    xx,yy=t.transform(x.ravel(),y.ravel())
    z=bilinear(grid,np.column_stack((xx,yy)),(x0,y0,sx,sy)).reshape(rows.shape)
    gy,gx=np.gradient(z,5*transform[3],5*transform[2])
    shade=np.clip((.7-.5*gx+.5*gy)/np.sqrt(1+gx*gx+gy*gy),0,1)
    valid=np.isfinite(shade)
    gray=np.where(valid,shade*255,0).astype(np.uint8)
    rgb=np.repeat(gray[:,:,None],3,axis=2)
    rgb[~valid]=[255,0,0]
    full=np.repeat(np.repeat(rgb,5,axis=0),5,axis=1)[:h,:w]
    return full, dict(valid_fraction=float(valid.mean()), invalid_color='red',
        sampling='strict bilinear existing EPSG:3035 DTM at ~1 m; transformed native imagery pixel centers',
        transform=t.description, accuracy_m=t.accuracy)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pixels',action='store_true')
    p.add_argument('--offline',action='store_true')
    args=p.parse_args()
    for d in [INTERIM,OUT]: d.mkdir(parents=True,exist_ok=True)
    remote=RangeReader(URLS['orthophoto'],RAW,cap=CAP,opener=OfflineOpener() if args.offline else None)
    tags,meta,next_ifd,meta_bytes=metadata(remote)
    (INTERIM/'source-metadata.tif').write_bytes(meta)
    save_json(INTERIM/'source-tags.json',tags)
    transform=georef(tags)
    expected={259:7,262:6,277:3,284:1,322:512,323:512}
    if any(scalar(tags,k)!=v for k,v in expected.items()) or tags[258]['values'] != [8,8,8]:
        raise ProbeError('unexpected source encoding')
    width,height=scalar(tags,256),scalar(tags,257)
    offsets,counts=tags[324]['values'],tags[325]['values']
    if len(offsets)!=math.ceil(width/512)*math.ceil(height/512) or len(offsets)!=len(counts):
        raise ProbeError('invalid tile tables')
    t,tr=transformer()
    with Path('data/processed/route_elevation.csv').open() as f: profile=list(csv.DictReader(f))
    distances=np.array([float(r['distance_m']) for r in profile])
    ll=np.array([[float(r['longitude']),float(r['latitude'])] for r in profile])
    targets=[('anomaly',9589.),('start',0.),('doppler_vicinity',2460.),('scheiblingstein_vicinity',7950.),('exelberg_vicinity',11950.),('finish',float(distances[-1]))]
    patches=[]
    for name,d in targets:
        lon,lat=[float(np.interp(d,distances,ll[:,i])) for i in range(2)]
        x,y=t.transform(lon,lat,direction=TransformDirection.INVERSE)
        win=window((x,y),transform,width,height)
        patches.append(dict(name=name,chainage_m=d,center_lon_lat=[lon,lat],center_source_xy=[x,y],window=list(win),tiles=tile_indices(win,width)))
    selected=sorted({i for patch in patches for i in patch['tiles']})
    ranges=[(offsets[i],counts[i]) for i in selected]
    if any(n<=0 or n>8_000_000 or o<0 or o+n>remote.state['total'] for o,n in ranges):
        raise ProbeError('unsafe compressed tile ranges')
    total=sum(n for _,n in ranges)
    # Retain all prior selections in this SAME operation, including superseded
    # exploratory patches. Never let a revised patch selection reset its budget.
    history_path=INTERIM/'selected-block-history.json'
    prior=[]
    if history_path.exists():
        prior=json.loads(history_path.read_text())
    elif (INTERIM/'acquisition-estimate.json').exists():
        previous=json.loads((INTERIM/'acquisition-estimate.json').read_text())
        prior=previous['blocks']
        save_json(INTERIM/'initial-selection.json',previous)
    history={b['index']:b for b in prior}
    history.update({i:dict(index=i,offset=offsets[i],compressed_bytes=counts[i]) for i in selected})
    historical_compressed=sum(b['compressed_bytes'] for b in history.values())
    save_json(history_path,list(history.values()))
    estimate=dict(source_url=URLS['orthophoto'],source_bytes=remote.state['total'],etag=remote.state['etag'],
        operation_cap=CAP,metadata_logical_bytes=meta_bytes,metadata_worst_case_two_attempts=2*meta_bytes,
        source_transform=transform,width=width,height=height,source_tiles=len(offsets),next_ifd_offset=next_ifd,
        overviews='not followed; first native image only; no COG conformance claim',
        selected_tiles=len(selected),selected_compressed_bytes=total,
        retained_operation_compressed_bytes=historical_compressed,
        complete_worst_case_two_attempts_bytes=2*(meta_bytes+historical_compressed),
        used_before_pixels=remote.used_bytes,remaining_worst_case_bytes=2*sum(n for o,n in ranges if remote.cached(o,n) is None),
        transform=tr,patches=patches,blocks=[dict(index=i,offset=offsets[i],compressed_bytes=counts[i]) for i in selected])
    save_json(INTERIM/'acquisition-estimate.json',estimate)
    # A fixed selection must fit as one operation even on subsequent cache runs.
    if 2*(meta_bytes+historical_compressed)>CAP:
        raise ProbeError('fixed selection cannot fit two attempts; STOP, do not split operation')
    remote.preflight(ranges,attempts=2)
    print(f'Metadata {meta_bytes:,}; selected {len(selected)} tiles, {total:,} compressed bytes; whole-operation two-attempt total {2*(meta_bytes+historical_compressed):,}')
    if not args.pixels: return
    decoded={}
    with tifffile.TiffFile(io.BytesIO(meta)) as tf:
        page=tf.pages[0]
        if not page.jpegtables: raise ProbeError('shared JPEG tables required')
        for idx in selected:
            decoded[idx]=decode(page,remote.read(offsets[idx],counts[idx]),idx)
    route=json.loads(Path('data/processed/route.geojson').read_text())
    coords=np.array(route['features'][0]['geometry']['coordinates'])[:,:2]
    xx,yy=t.transform(coords[:,0],coords[:,1],direction=TransformDirection.INVERSE)
    xy=np.column_stack((xx,yy))
    d=9590.
    ml=[np.interp(d,distances,ll[:,i]) for i in range(2)]
    marker=t.transform(*ml,direction=TransformDirection.INVERSE)
    thumbnails=[]
    for patch in patches:
        win=patch['window']; c0,r0,c1,r1=win
        local=(transform[0]+c0*transform[2],transform[1]-r0*transform[3],*transform[2:])
        rgb=assemble(win,width,decoded)
        name=patch['name']; path=OUT/f'{name}.tif'
        extra=[(33550,'d',3,(local[2],local[3],0),False),
               (33922,'d',6,(0,0,0,local[0],local[1],0),False),
               (34735,'H',16,(1,1,0,3,1024,0,1,1,1025,0,1,1,3072,0,1,31256),False)]
        tifffile.imwrite(path,rgb,photometric='rgb',compression='deflate',metadata=None,extratags=extra,
            description='Derived native BEV Operat2024460 RGB window; Copyright BEV, CC BY 4.0. Capture date unknown. No resampling.')
        with tifffile.TiffFile(path) as exported:
            if not np.array_equal(exported.asarray(),assemble(win,width,decoded)):
                raise ProbeError('export differs from decoded original window')
            if tuple(exported.pages[0].tags[33922].value)[3:5]!=local[:2]:
                raise ProbeError('export tiepoint differs')
        patch.update(transform=local,stats=stats(rgb),sha256=digest(path.read_bytes()),
            rgb_sha256=digest(rgb.tobytes()),verified_equal_original_window=True,
            bounds=[local[0],local[1]-rgb.shape[0]*local[3],local[0]+rgb.shape[1]*local[2],local[1]])
        png(OUT/f'{name}_clean.png',rgb)
        over=overlay(rgb,xy,local,marker if name=='anomaly' else None)
        png(OUT/f'{name}_route.png',over)
        thumbnails.append(over[::4,::4])
        if name=='anomaly':
            shade,record=hillshade(local,rgb.shape[:2])
            patch['hillshade']=record
            png(OUT/'anomaly_hillshade_route.png',overlay(shade,xy,local,marker))
            png(OUT/'anomaly_imagery_hillshade_route.png',overlay((.65*rgb+.35*shade).astype(np.uint8),xy,local,marker))
    h=max(a.shape[0] for a in thumbnails); w=max(a.shape[1] for a in thumbnails)
    sheet=np.full((2*h,3*w,3),255,np.uint8)
    for i,a in enumerate(thumbnails):
        r,c=divmod(i,3); sheet[r*h:r*h+a.shape[0],c*w:c*w+a.shape[1]]=a
    png(OUT/'contact_sheet.png',sheet)
    manifest=dict(source=estimate,patches=patches,actual_response_body_bytes=remote.used_bytes,
        attribution='© BEV, CC BY 4.0; route © OpenStreetMap contributors, ODbL',
        license_reference='docs/DATA_SOURCES.md; https://doi.org/10.48677/1f33a105-0798-4696-92c2-df985c6f40a9',
        capture_date=None,source_survey_date=None,dates='URL release path and HTTP Last-Modified are not capture dates',
        route_sha256=digest(Path('data/processed/route.geojson').read_bytes()),
        profile_sha256=digest(Path('data/processed/route_elevation.csv').read_bytes()),
        contact_sheet_order=[p['name'] for p in patches],
        scope='Six independent ~250m squares, not full-route coverage; no guaranteed semantic validity mask or asphalt geometry measurement',
        versions=dict(numpy=np.__version__,tifffile=tifffile.__version__,imagecodecs=imagecodecs.__version__,pyproj=pyproj.__version__))
    save_json(OUT/'manifest.json',manifest)
    print(f'Exported six patches, exact source-window equality verified; ledger {remote.used_bytes:,} bytes')


if __name__=='__main__':
    main()
