"""Synthetic and real offline landscape texture/coordinate/provenance checks."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import imagecodecs
import numpy as np
from pyproj import Transformer, network
import tifffile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_landscape_orthos import (CachedRanges, coalesce, target_grid,
    source_samples, OUT, INTERIM, TERRAIN, INPUT_MANIFEST)
from inspect_orthophoto import RAW, CAP, decode, metadata, georef, transformer
from extract_terrain import OfflineOpener
from probe_raster_metadata import URLS, ProbeError
from terrain_ranges import digest, save_json, MAX_RANGE


class LandscapeSyntheticTests(unittest.TestCase):
    def test_grid_north_up_mask_not_colour_and_uv(self):
        x=y=np.array([0.,4.,8.])
        valid=np.array([[True,False],[False,True]])
        xx,yy,mask,grid=target_grid(x,y,valid,[0,0,8,8])
        np.testing.assert_array_equal(xx[0],[1,3,5,7])
        np.testing.assert_array_equal(yy[:,0],[7,5,3,1])
        self.assertEqual(grid,(0,8,2,-2))
        np.testing.assert_array_equal(mask,np.array([[0,0,1,1],[0,0,1,1],[1,1,0,0],[1,1,0,0]],bool))
        np.testing.assert_allclose(yy[:,0]/8,[.875,.625,.375,.125])
        # A black source value remains valid; validity never examines colour.
        self.assertEqual(int(mask.sum()),8)
        with self.assertRaises(ProbeError): target_grid(x,y,valid,[0,0,1026,8])

    def test_source_pixel_area_edges(self):
        class Identity:
            def transform(self,x,y): return x,y
        r,c,ok=source_samples(np.array([.1,3.9,4.]),np.array([3.9,.1,2.]),Identity(),(0,4,1,1),4,4)
        np.testing.assert_array_equal(r,[0,3,2])
        np.testing.assert_array_equal(c,[0,3,4])
        np.testing.assert_array_equal(ok,[True,True,False])

    def test_coalesce_counts_gaps_and_bounds(self):
        self.assertEqual(coalesce([(20,5),(0,10),(8,4),(20,5)]),[(0,25)])
        self.assertEqual(coalesce([(0,MAX_RANGE),(MAX_RANGE,1)]),[(0,MAX_RANGE),(MAX_RANGE,1)])
        self.assertEqual(coalesce([(0,10),(100,10)],max_gap=8),[(0,10),(100,10)])
        with self.assertRaises(ProbeError): coalesce([(0,MAX_RANGE+1)])

    def test_contained_cache_hash_no_network_or_charge(self):
        with tempfile.TemporaryDirectory() as root:
            remote=CachedRanges('https://example.test/source',root,CAP,OfflineOpener())
            data=b'0123456789'
            Path(root,'range-100-10.bin').write_bytes(data)
            remote.state['cache']['100-10']=dict(file='range-100-10.bin',sha256=digest(data))
            remote.flush()
            self.assertEqual(remote.read(103,4),b'3456')
            self.assertEqual(remote.used_bytes,0)
            self.assertIsNone(remote.covering(99,4))
            with self.assertRaises(ProbeError): remote.preflight([(1000,100_000_001)])


@unittest.skipUnless((OUT/'manifest.json').exists(),'real outputs not generated')
class LandscapeRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((OUT/'manifest.json').read_text())
        cls.remote=CachedRanges(URLS['orthophoto'],RAW,CAP,OfflineOpener())
        cls.ledger_before=(RAW/'operation.json').read_bytes()
        cls.tags,cls.meta,_,_=metadata(cls.remote)
        cls.terrain=np.load(TERRAIN)
        cls.origin=json.loads(INPUT_MANIFEST.read_text())['coordinates']['origin_m']

    def test_all_png_hashes_masks_bounds_coverage_and_orientation(self):
        m=self.manifest
        self.assertEqual(m['acquisition']['terrain_sha256'],digest(TERRAIN.read_bytes()))
        terrain=self.terrain
        expected=[i for i,(r0,r1,c0,c1) in enumerate(terrain['tile_node_slices']) if terrain['valid_cells'][r0:r1-1,c0:c1-1].any()]
        self.assertEqual([c['index'] for c in m['chunks']],expected)
        for chunk in m['chunks']:
            rgb=imagecodecs.png_decode(Path(chunk['path']).read_bytes())
            mask=imagecodecs.png_decode(Path(chunk['mask_path']).read_bytes())>0
            self.assertEqual(digest(Path(chunk['path']).read_bytes()),chunk['sha256'])
            self.assertEqual(digest(Path(chunk['mask_path']).read_bytes()),chunk['mask_sha256'])
            self.assertEqual(digest(rgb.tobytes()),chunk['rgb_sha256'])
            xx,yy,expected_mask,grid=target_grid(terrain['x_m'][0],terrain['y_m'][:,0],terrain['valid_cells'],chunk['local_bounds'])
            np.testing.assert_array_equal(mask,expected_mask)
            self.assertEqual(mask.sum(),chunk['valid_texels'])
            self.assertEqual(rgb.shape,(chunk['height'],chunk['width'],3))
            self.assertLessEqual(max(rgb.shape[:2]),512)
            self.assertTrue(np.all(rgb[~mask]==0))
            self.assertEqual(list(grid),chunk['local_transform'])
            self.assertLess(yy[-1,0],yy[0,0])
            self.assertEqual(chunk['source_footprint_fraction'],1)
            self.assertEqual(grid[2],2)
            self.assertEqual(grid[3],-2)

    def test_real_coordinates_and_source_colours_independent_chain(self):
        # Independent chain through geographic WGS84, rather than repeating
        # the direct target->source operation used by the producer.
        network.set_network_enabled(False)
        geographic=Transformer.from_crs(25833,4326,always_xy=True)
        source_to_ll,_=transformer()
        from pyproj.enums import TransformDirection
        x0,y0,dx,dy=georef(self.tags)
        nx=(self.tags[256]['values'][0]+511)//512
        with tifffile.TiffFile(io.BytesIO(self.meta)) as tf:
            for chunk in self.manifest['chunks']:
                rgb=imagecodecs.png_decode(Path(chunk['path']).read_bytes())
                mask=imagecodecs.png_decode(Path(chunk['mask_path']).read_bytes())>0
                candidates=np.argwhere(mask)
                # Interior samples avoiding pixel-boundary numerical ambiguity.
                for r,c in candidates[np.linspace(0,len(candidates)-1,7,dtype=int)]:
                    west,north,sx,sy=chunk['utm_transform']
                    e,n=west+(c+.5)*sx,north+(r+.5)*sy
                    lon,lat=geographic.transform(e,n)
                    source_x,source_y=source_to_ll.transform(lon,lat,direction=TransformDirection.INVERSE)
                    col,row=int(np.floor((source_x-x0)/dx)),int(np.floor((y0-source_y)/dy))
                    idx=(row//512)*nx+col//512
                    tile=decode(tf.pages[0],self.remote.read(self.tags[324]['values'][idx],self.tags[325]['values'][idx]),idx)
                    np.testing.assert_array_equal(rgb[r,c],tile[row%512,col%512])
        self.assertEqual((RAW/'operation.json').read_bytes(),self.ledger_before)

    def test_original_budget_history_and_retry_reserve(self):
        a=self.manifest['acquisition']
        self.assertEqual(a['used_before_pixels'],7_857_327)
        self.assertEqual(a['operation_cap'],200_000_000)
        self.assertEqual(a['worst_case_operation_bytes'],a['used_before_pixels']+2*a['additional_request_bytes'])
        self.assertLess(a['worst_case_operation_bytes'],a['operation_cap'])
        self.assertEqual(a['additional_request_bytes'],a['missing_compressed_bytes']+a['coalescing_gap_bytes'])
        self.assertEqual(self.manifest['actual_response_body_bytes'],67_017_250)
        self.assertEqual(self.remote.used_bytes,67_017_250)
        self.assertEqual(a['max_retry'],1)
        self.assertTrue(all(n<=MAX_RANGE for _,n in a['ranges']))
        self.assertEqual(a['transform_accuracy_m'],1.5)


if __name__=='__main__': unittest.main()
