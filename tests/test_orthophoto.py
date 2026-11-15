"""Offline imagery checks: shared-table JPEG, grid windows, axes and operation safety."""
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import imagecodecs
import numpy as np
from pyproj.enums import TransformDirection
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_orthophoto import (assemble, decode, georef, metadata, overlay, stats,
                                tile_indices, transformer, window, CAP)
from terrain_ranges import RangeReader, ProbeError
from test_terrain import Response, Opener


def shared_jpeg(rgb):
    """Separate DQT/DHT into TIFF JPEGTables; leave scan data in tile segment."""
    full=imagecodecs.jpeg_encode(rgb,level=92,colorspace='RGB',outcolorspace='YCbCr',subsampling='420')
    tables=bytearray(b'\xff\xd8'); tile=bytearray(b'\xff\xd8'); pos=2
    while pos<len(full):
        marker=full[pos+1]
        if marker==0xda:
            tile.extend(full[pos:]); break
        size=struct.unpack_from('>H',full,pos+2)[0]
        segment=full[pos:pos+2+size]
        (tables if marker in (0xdb,0xc4) else tile).extend(segment)
        pos+=2+size
    tables.extend(b'\xff\xd9')
    return full,bytes(tables),bytes(tile)


class ImageryTests(unittest.TestCase):
    def test_shared_ycbcr_rgb_decode_offline(self):
        rgb=np.zeros((512,512,3),np.uint8)
        rgb[:,:256]=[220,40,20]; rgb[:,256:]=[10,70,230]
        full,tables,tile=shared_jpeg(rgb)
        expected=imagecodecs.jpeg_decode(full,outcolorspace='RGB')
        buf=io.BytesIO()
        tifffile.imwrite(buf,iter([tile]),shape=rgb.shape,dtype=np.uint8,
            tile=(512,512),photometric='ycbcr',compression='jpeg',
            subsampling=(2,2),jpegtables=tables,metadata=None)
        buf.seek(0)
        with tifffile.TiffFile(buf) as tf:
            self.assertTrue(tf.pages[0].jpegtables)
            actual=decode(tf.pages[0],tile,0)
        np.testing.assert_array_equal(actual,expected)
        self.assertLess(np.abs(actual.astype(float)-rgb).mean(),3)

    def tags(self):
        return {34735: {'values':[1,1,0,2,3072,0,1,31256,1025,0,1,1]},
            33550:{'values':[.2,.2,0]},33922:{'values':[10,20,0,102,196,0]}}

    def test_georef_area_origin_and_reject_point(self):
        tags=self.tags(); self.assertEqual(georef(tags),(100,200,.2,.2))
        tags[34735]['values'][-1]=2
        with self.assertRaises(ProbeError): georef(tags)

    def test_window_tiles_and_exact_native_crop(self):
        win=window((512,512),(0,1024,1,1),1024,1024,side=250)
        self.assertEqual(win,(387,387,637,637))
        self.assertEqual(tile_indices(win,1024),[0,1,2,3])
        y,x=np.mgrid[:1024,:1024]
        full=np.stack((x%256,y%256,(x+y)%256),axis=2).astype(np.uint8)
        tiles={r*2+c:full[r*512:(r+1)*512,c*512:(c+1)*512] for r in range(2) for c in range(2)}
        np.testing.assert_array_equal(assemble(win,1024,tiles),full[387:637,387:637])
        self.assertEqual(tile_indices((0,0,512,512),1024),[0])
        with self.assertRaises(ProbeError): window((0,0),(0,1024,1,1),1024,1024)

    def test_masks_are_heuristics_not_guaranteed_coverage(self):
        a=np.array([[[0,0,0],[5,5,5]],[[6,2,1],[255,255,255]]],np.uint8)
        s=stats(a)
        self.assertEqual(s['exact_black_fraction'],.25)
        self.assertEqual(s['near_black_le5_fraction'],.5)
        self.assertIn('not a validity mask',s['interpretation'])

    def test_axes_roundtrip_and_external_control(self):
        t,record=transformer()
        xy=t.transform(16.22,48.26,direction=TransformDirection.INVERSE)
        self.assertTrue(-20000<xy[0]<30000)
        self.assertTrue(300000<xy[1]<400000)
        np.testing.assert_allclose(t.transform(*xy),(16.22,48.26),atol=1e-7)
        self.assertFalse(record['networking'])
        self.assertIn('always_xy',record['axis_handling'])
        self.assertGreaterEqual(record['accuracy_m'],1)

    def test_overlay_pixel_axes_and_marker(self):
        a=np.zeros((50,50,3),np.uint8)
        b=overlay(a,np.array([[10,90],[20,80]]),(0,100,1,1),marker=(30,70))
        np.testing.assert_array_equal(b[15,15],[255,40,180])
        np.testing.assert_array_equal(b[30,30],[0,255,255])
        self.assertFalse(a.any())

    def test_metadata_rejects_huge_payload_before_fetch(self):
        class Fake:
            def __init__(self): self.calls=[]
            def preflight(self,*args,**kwargs): pass
            def read(self,offset,size):
                self.calls.append((offset,size))
                if offset==0: return b'II'+struct.pack('<HHHQ',43,8,0,16)
                if offset==16: return struct.pack('<Q',1)
                return bytes(size)
        remote=Fake()
        with patch('inspect_orthophoto.directory',return_value=({324:{'offset':100,'bytes':5_000_001}},0)):
            with self.assertRaisesRegex(ProbeError,'metadata exceeds'): metadata(remote)
        self.assertEqual(len(remote.calls),3)

    def test_operation_protocol_fail_closed(self):
        for headers in [{'ETag':'W/\"v1\"'},{'Content-Range':'bytes 11-14/100'}]:
            with tempfile.TemporaryDirectory() as root:
                response=Response(headers=headers)
                remote=RangeReader('https://example.test/imagery',root,CAP,Opener(response))
                with self.assertRaises(ProbeError): remote.read(10,4)
                self.assertEqual(response.read_bytes,0)

    def test_separate_persistent_cap_retry_and_ifmatch(self):
        with tempfile.TemporaryDirectory() as root:
            remote=RangeReader('https://example.test/imagery',root,CAP,Opener(Response(b'ab'),Response(),Response(headers={'Content-Range':'bytes 14-17/100'})))
            remote.preflight([(10,4),(14,4)])
            remote.read(10,4); remote.read(14,4)
            self.assertEqual(remote.used_bytes,10)
            self.assertEqual(remote.opener.calls[-1][0].get_header('If-match'),'"v1"')
            cached=RangeReader('https://example.test/imagery',root,CAP,Opener())
            before=Path(root,'operation.json').read_bytes()
            self.assertEqual(cached.read(10,4),b'abcd')
            self.assertEqual(Path(root,'operation.json').read_bytes(),before)
            with self.assertRaises(ProbeError): cached.preflight([(50,100_000_000)])


if __name__=='__main__': unittest.main()
