"""Offline tests: no network or optional packages required."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock

SPEC = importlib.util.spec_from_file_location("probe", Path(__file__).resolve().parents[1] / "scripts/probe_raster_metadata.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class ParsingTests(unittest.TestCase):
    def test_classic_both_endians(self):
        for endian, mark in (("<", b"II"), (">", b"MM")):
            self.assertEqual(p.header(mark + struct.pack(endian + "HI", 42, 8)), (endian, False, 8))
            raw = struct.pack(endian + "HHII", 256, 4, 1, 50000) + struct.pack(endian + "I", 0)
            tags, link = p.directory(raw, 1, endian, False)
            self.assertEqual(tags[256]["values"], [50000])
            self.assertEqual(link, 0)

    def test_bigtiff_both_endians_and_large_table(self):
        for endian, mark in (("<", b"II"), (">", b"MM")):
            self.assertEqual(p.header(mark + struct.pack(endian + "HHHQ", 43, 8, 0, 16)), (endian, True, 16))
            raw = struct.pack(endian + "HHQQ", 324, 16, 1000000, 9876543210) + struct.pack(endian + "Q", 4096)
            tags, link = p.directory(raw, 1, endian, True)
            self.assertEqual(tags[324]["bytes"], 8000000)
            self.assertEqual(tags[324]["offset"], 9876543210)
            self.assertNotIn("values", tags[324])
            self.assertEqual(link, 4096)

    def test_invalid_and_truncated(self):
        for raw in (b"", b"XX" + b"\0" * 14, b"II" + struct.pack("<HHHQ", 43, 4, 0, 16)):
            with self.assertRaises(p.ProbeError):
                p.header(raw)
        with self.assertRaises(p.ProbeError):
            p.directory(b"", 1, "<", False)
        with self.assertRaises(p.ProbeError):
            p.values(b"\0", 3, 1, "<")

    def test_float_and_sample_arrays(self):
        self.assertEqual(p.values(struct.pack("<d", 1.25), 12, 1, "<"), [1.25])
        self.assertEqual(p.values(struct.pack(">3H", 8, 8, 8), 3, 3, ">"), [8, 8, 8])


class RangeTests(unittest.TestCase):
    def headers(self):
        return {"Content-Range": "bytes 0-15/100", "Content-Length": "16"}

    def remote(self, status=206, headers=None, body=b"x" * 16):
        remote = p.Remote("https://example.invalid/a.tif", p.Budget())
        response = Mock(status=status, headers=self.headers() if headers is None else headers)
        response.read.return_value = body
        remote.opener = Mock()
        remote.opener.open.return_value = response
        return remote, response

    def test_range_validation(self):
        self.assertEqual(p.validate_range(206, self.headers(), 0, 16), 100)
        for headers in ({}, {"Content-Range": "bytes 1-16/100"},
                        {"Content-Range": "bytes 0-15/*"},
                        {"Content-Range": "bytes 0-15/15"},
                        dict(self.headers(), **{"Content-Encoding": "identity"}),
                        dict(self.headers(), **{"Content-Length": "100"})):
            with self.assertRaises(p.ProbeError):
                p.validate_range(206, headers, 0, 16)
        with self.assertRaises(p.ProbeError):
            p.validate_range(206, self.headers(), 0, 16, 101)

    def test_ignored_range_closed_without_body_and_stops_globally(self):
        remote, response = self.remote(status=200)
        with self.assertRaises(p.ProbeError):
            remote.read(0, 16)
        response.read.assert_not_called()
        response.close.assert_called_once()
        with self.assertRaises(p.ProbeError):
            remote.read(0, 16)
        other = p.Remote("https://example.invalid/b.tif", remote.budget)
        other.opener = Mock()
        with self.assertRaises(p.ProbeError):
            other.read(0, 16)
        other.opener.open.assert_not_called()
        self.assertEqual(remote.budget.actual_bytes, 0)

    def test_bad_headers_closed_without_read(self):
        remote, response = self.remote(headers={})
        with self.assertRaises(p.ProbeError):
            remote.read(0, 16)
        response.read.assert_not_called()
        response.close.assert_called_once()

    def test_success_cache_and_provenance(self):
        remote, response = self.remote()
        self.assertEqual(remote.read(0, 16), b"x" * 16)
        self.assertEqual(remote.read(2, 4), b"xxxx")
        self.assertEqual(remote.requests, 1)
        self.assertEqual(remote.budget.actual_bytes, 16)
        self.assertEqual(remote.chunks[0]["sha256"], p.hashlib.sha256(b"x" * 16).hexdigest())
        self.assertEqual(remote.opener.open.call_args.kwargs["timeout"], 20)

    def test_short_response_counts_bytes(self):
        remote, response = self.remote()
        response.read.side_effect = [b"abc", b""]
        with self.assertRaises(p.ProbeError):
            remote.read(0, 16)
        self.assertEqual(remote.budget.actual_bytes, 3)
        self.assertEqual(remote.chunks[0]["actual_bytes"], 3)

    def test_bounds_request_cap_and_operation_cap(self):
        remote, response = self.remote()
        for offset, size in ((-1, 16), (0, 65537), (0, 0)):
            with self.assertRaises(p.ProbeError):
                remote.read(offset, size)
        remote.total = 100
        with self.assertRaises(p.ProbeError):
            remote.read(99, 2)
        remote.requests = 4
        with self.assertRaises(p.ProbeError):
            remote.read(0, 16)
        remote.requests = 0
        remote.budget.actual_bytes = p.CAP - 15
        with self.assertRaises(p.ProbeError):
            remote.read(0, 16)
        response.read.assert_not_called()
        remote.opener.open.assert_not_called()

    def test_no_redirect(self):
        self.assertIsNone(p.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_inspect_does_not_fetch_tables(self):
        # A complete synthetic BigTIFF directory plus out-of-line huge tables.
        entries = [(256, 4, 1, 50000), (257, 4, 1, 50000), (322, 4, 1, 256),
                   (323, 4, 1, 256), (324, 16, 1000000, 100000), (325, 16, 1000000, 8100000)]
        raw = b"".join(struct.pack("<HHQQ", *entry) for entry in entries) + struct.pack("<Q", 0)
        remote = Mock(requests=3)
        remote.read.side_effect = [b"II" + struct.pack("<HHHQ", 43, 8, 0, 16), struct.pack("<Q", len(entries)), raw]
        result = p.inspect(remote)
        self.assertEqual(remote.read.call_count, 3)
        self.assertEqual(result["layout"]["expected_blocks"], 196 * 196)
        self.assertIsNone(result["transfer_prediction_bytes"])


if __name__ == "__main__":
    unittest.main()
