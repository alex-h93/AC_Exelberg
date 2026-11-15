#!/usr/bin/env python3
"""Strictly offline validation against original compressed imagery source tiles."""
import io
import json

import imagecodecs
import numpy as np
import tifffile

from inspect_orthophoto import (CAP, RAW, OUT, INTERIM, URLS, RangeReader,
    OfflineOpener, metadata, georef, decode, assemble, stats, digest, save_json)


def main():
    ledger=(RAW/'operation.json').read_bytes()
    m=json.loads((OUT/'manifest.json').read_text())
    for name,path in [('route','data/processed/route.geojson'),('profile','data/processed/route_elevation.csv')]:
        from pathlib import Path
        assert digest(Path(path).read_bytes())==m[name+'_sha256'],name+' changed'
    remote=RangeReader(URLS['orthophoto'],RAW,CAP,OfflineOpener())
    tags,meta,_,_=metadata(remote)
    transform=georef(tags)
    offsets,counts=tags[324]['values'],tags[325]['values']
    blocks=sorted({idx for p in m['patches'] for idx in p['tiles']})
    with tifffile.TiffFile(io.BytesIO(meta)) as source:
        tiles={i:decode(source.pages[0],remote.read(offsets[i],counts[i]),i) for i in blocks}
    verified=0
    for p in m['patches']:
        rgb=assemble(p['window'],m['source']['width'],tiles)
        path=OUT/(p['name']+'.tif')
        assert digest(path.read_bytes())==p['sha256']
        with tifffile.TiffFile(path) as tf:
            np.testing.assert_array_equal(tf.asarray(),rgb)
            assert tf.pages[0].photometric==2
            assert georef({k:{'values':list(tf.pages[0].tags[k].value)} for k in [34735,33550,33922]})==tuple(p['transform'])
        c0,r0,_,_=p['window']
        assert tuple(p['transform'])==(transform[0]+c0*transform[2],transform[1]-r0*transform[3],*transform[2:])
        np.testing.assert_array_equal(imagecodecs.png_decode((OUT/(p['name']+'_clean.png')).read_bytes()),rgb)
        assert stats(rgb)==p['stats']
        verified+=rgb.shape[0]*rgb.shape[1]
    assert (RAW/'operation.json').read_bytes()==ledger,'offline validation changed ledger'
    result=dict(patches=len(m['patches']),verified_original_rgb_pixels=verified,
        selected_tiles=len(blocks),ledger_unchanged=True,actual_body_bytes=remote.used_bytes)
    save_json(INTERIM/'offline-validation.json',result)
    print(json.dumps(result))


if __name__=='__main__': main()
