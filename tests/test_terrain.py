"""Offline terrain/range checks; no real HTTP requests."""
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from terrain_ranges import RangeReader, ProbeError, CAP
from extract_terrain import bilinear, georef, resample_route, selected_blocks, gains, elevation_geometry, OfflineOpener


class Response(io.BytesIO):
    def __init__(self, body=b'abcd', status=206, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = {'Content-Range': 'bytes 10-13/100', 'Content-Length': '4', 'ETag': '"v1"'}
        self.headers.update(headers or {})
        self.read_bytes = 0

    def read(self, size=-1):
        data = super().read(size)
        self.read_bytes += len(data)
        return data


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class RangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def reader(self, *responses, cap=CAP):
        return RangeReader('https://example.test/large.tif', self.temp.name, cap, Opener(*responses))

    def test_cache_persistent_checksum_and_headers(self):
        remote = self.reader(Response())
        self.assertEqual(remote.read(10, 4), b'abcd')
        self.assertEqual(remote.state['actual_bytes'], 4)
        req, timeout = remote.opener.calls[0]
        self.assertEqual(req.get_header('Accept-encoding'), 'identity')
        self.assertEqual(req.get_header('Range'), 'bytes=10-13')
        self.assertEqual(timeout, 30)
        reopened = self.reader()
        self.assertEqual(reopened.read(10, 4), b'abcd')
        self.assertEqual(reopened.state['actual_bytes'], 4)
        (Path(self.temp.name) / 'range-10-4.bin').write_bytes(b'xxxx')
        with self.assertRaises(ProbeError):
            reopened.read(10, 4)

    def test_200_never_reads_body(self):
        response = Response(status=200)
        remote = self.reader(response)
        with self.assertRaises(ProbeError):
            remote.read(10, 4)
        self.assertEqual(response.read_bytes, 0)
        self.assertEqual(remote.state['actual_bytes'], 0)
        self.assertEqual(len(remote.opener.calls), 1)

    def test_bad_ranges_encoding_length_missing_etag(self):
        cases = [{'Content-Range': 'bytes 11-14/100'},
                 {'Content-Range': 'bytes 10-13/*'},
                 {'Content-Range': 'bytes 10-13/13'},
                 {'Content-Length': '5'}, {'Content-Encoding': 'gzip'},
                 {'ETag': None}, {'ETag': 'W/"v1"'}]
        for headers in cases:
            with self.subTest(headers=headers), tempfile.TemporaryDirectory() as root:
                response = Response(headers=headers)
                remote = RangeReader('https://example.test', root, opener=Opener(response))
                with self.assertRaises(ProbeError):
                    remote.read(10, 4)
                self.assertEqual(response.read_bytes, 0)

    def test_identity_encoding_allowed(self):
        self.assertEqual(self.reader(Response(headers={'Content-Encoding': 'identity'})).read(10, 4), b'abcd')

    def test_etag_and_object_length_consistency(self):
        for changed in [{'ETag': '"v2"', 'Content-Range': 'bytes 14-17/100'},
                        {'Content-Range': 'bytes 14-17/101'}]:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as root:
                response = Response(headers=changed)
                remote = RangeReader('https://example.test', root, opener=Opener(Response(), response))
                remote.read(10, 4)
                with self.assertRaises(ProbeError):
                    remote.read(14, 4)
                self.assertEqual(response.read_bytes, 0)
                self.assertEqual(remote.opener.calls[1][0].get_header('If-match'), '"v1"')

    def test_partial_retry_counts_all_bytes_and_keeps_original(self):
        remote = self.reader(Response(b'ab'), Response())
        self.assertEqual(remote.read(10, 4), b'abcd')
        self.assertEqual(remote.state['actual_bytes'], 6)
        self.assertEqual((Path(self.temp.name) / 'attempt-00001.part').read_bytes(), b'ab')
        self.assertEqual(len(remote.state['attempts']), 2)

    def test_incomplete_read_partial_is_counted(self):
        class Incomplete(Response):
            def read(self, size=-1):
                if self.tell() == 0:
                    super().read(2)
                    raise http.client.IncompleteRead(b'ab', 2)
                return b''
        remote = self.reader(Incomplete(), Response())
        self.assertEqual(remote.read(10, 4), b'abcd')
        self.assertEqual(remote.state['actual_bytes'], 6)

    def test_budget_retries_and_external_count(self):
        remote = self.reader(Response(b'ab'), Response(), cap=5)
        with self.assertRaises(ProbeError):
            remote.preflight([(10, 4)])
        with self.assertRaises(ProbeError):
            remote.read(10, 4)
        self.assertEqual(remote.state['actual_bytes'], 2)
        self.assertEqual(len(remote.opener.calls), 1)
        reopened = self.reader(cap=5)
        reopened.charge_external('documentation', 2)
        self.assertEqual(reopened.used_bytes, 4)
        with self.assertRaises(ProbeError):
            reopened.read(10, 4)

    def test_bounded_retries_timeout_and_bad_offsets(self):
        remote = self.reader(TimeoutError('timed out'), TimeoutError('timed out'))
        with self.assertRaises(TimeoutError):
            remote.read(10, 4)
        self.assertEqual(len(remote.opener.calls), 2)
        for offset, size in [(-1, 2), (0, 0), (0, 8_000_001)]:
            with self.assertRaises(ProbeError):
                remote.read(offset, size)


class TerrainTests(unittest.TestCase):
    def tags(self):
        return {34735: {'values': [1,1,0,2,3072,0,1,3035,1025,0,1,1]},
                33550: {'values': [2,3,0]}, 33922: {'values': [2,4,0,104,188,0]}}

    def test_georef_tiepoint_and_pixel_centers(self):
        self.assertEqual(georef(self.tags()), (100,200,2,3))
        grid = np.array([[1,2],[3,4]], dtype=float)
        self.assertEqual(bilinear(grid, [(102,197)], (100,200,2,3))[0], 2.5)

    def test_reject_point_and_wrong_crs(self):
        for key, value in [(7, 25833), (11, 2)]:
            tags = self.tags()
            tags[34735]['values'][key] = value
            with self.assertRaises(ProbeError):
                georef(tags)

    def test_block_selection_conservative_and_edge(self):
        xy = np.array([[400,600],[600,400]])
        chosen = selected_blocks(xy, (0,1024,1,1), 1024,1024, radius=200)
        self.assertEqual(chosen, [0,1,2,3])
        self.assertEqual(selected_blocks(np.array([[100,900],[110,890]]), (0,1024,1,1),1024,1024,radius=1), [0])
        with self.assertRaises(ProbeError):
            selected_blocks(np.array([[1,1],[2,2]]), (0,1024,1,1),1024,1024)

    def test_plane_bilinear_no_extrapolation_strict_nodata(self):
        grid = np.array([[1.,2.,3.],[3.,4.,5.],[5.,6.,7.]])
        self.assertEqual(bilinear(grid, [(1,2)], (0,3,1,1))[0], 2.5)
        self.assertTrue(np.isnan(bilinear(grid, [(0,3)], (0,3,1,1))[0]))
        for invalid in [-9999, np.nan, np.inf]:
            copy = grid.copy(); copy[1,1] = invalid
            # Pixel at zero interpolation weight still makes this invalid.
            self.assertTrue(np.isnan(bilinear(copy, [(.5,2.5)], (0,3,1,1))[0]))

    def test_route_resampling_preserves_distance_and_endpoints(self):
        distances, xy = resample_route(np.array([[0,0],[3,4],[15,4]]),10)
        np.testing.assert_array_equal(distances, [0,10,17])
        np.testing.assert_allclose(xy, [[0,0],[8,4],[15,4]])
        self.assertEqual(gains([1,3,2,4]), (4,1))
        with self.assertRaises(ValueError):
            resample_route(np.array([[0,0],[0,0]]))

    def test_geojson_2d_parallel_heights_and_gaps(self):
        geometry, heights = elevation_geometry(range(9), range(10,19),
                                               [1,2,np.nan,4,np.nan,6,7,8,np.nan])
        self.assertEqual(geometry, {'type': 'MultiLineString', 'coordinates':
                                   [[[0.,10.],[1.,11.]], [[5.,15.],[6.,16.],[7.,17.]]]})
        self.assertEqual(heights, [[1.,2.],[6.,7.,8.]])
        self.assertEqual(elevation_geometry([0], [1], [np.nan])[1], [])
        self.assertEqual(elevation_geometry([0,1], [2,3], [4,5])[1], [[4.,5.]])

    def test_offline_opener_fails_closed(self):
        with self.assertRaises(ProbeError):
            OfflineOpener().open(None, 30)

    def test_library_lzw_float_predictor_roundtrip_and_geotiff(self):
        # Exercise exactly the source codec/predictor without any network.
        data = (np.arange(32*32,dtype=np.float32).reshape(32,32)/7)
        data[4,4] = -9999
        buffer = io.BytesIO()
        tifffile.imwrite(buffer,data,tile=(16,16),compression='lzw',predictor=3,
                         metadata=None,extratags=[(33550,'d',3,(1,1,0),False),
                         (33922,'d',6,(0,0,0,100,200,0),False),
                         (34735,'H',16,(1,1,0,3,1024,0,1,1,1025,0,1,1,3072,0,1,3035),False),
                         (42113,'s',0,'-9999',False)])
        buffer.seek(0)
        with tifffile.TiffFile(buffer) as tif:
            page = tif.pages[0]
            raw = buffer.getvalue()
            block, position, shape = page.decode(raw[page.dataoffsets[0]:page.dataoffsets[0]+page.databytecounts[0]],0)
            np.testing.assert_array_equal(block.reshape(16,16),data[:16,:16])
            self.assertEqual(page.geotiff_tags['ProjectedCSTypeGeoKey'],3035)
            self.assertEqual(page.nodata,-9999)


if __name__ == '__main__':
    unittest.main()
