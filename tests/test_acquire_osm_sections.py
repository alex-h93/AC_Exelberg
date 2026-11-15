"""Offline acquisition controls; no real HTTP requests."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import acquire_osm_sections as sections


class AcquisitionTests(unittest.TestCase):
    def test_three_successes_preserve_bytes(self):
        payloads = [f'<osm version="0.6"><bounds minlat="{n}"/></osm>'.encode() for n in range(3)]
        responses = []
        for payload in payloads:
            response = io.BytesIO(payload)
            response.code = 200
            response.headers = {}
            responses.append(response)
        with tempfile.TemporaryDirectory() as directory, patch.object(sections.urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = responses
            log = json.loads(sections.acquire_sections(Path(directory)).read_text())
            self.assertEqual(factory.return_value.open.call_count, 3)
            factory.assert_called_once_with(sections.NoRedirect)
            for call in factory.return_value.open.call_args_list:
                self.assertEqual(call.kwargs["timeout"], 25)
                self.assertTrue(call.args[0].get_header("User-agent"))
            self.assertEqual(log["total_received_bytes"], sum(map(len, payloads)))
            for attempt, payload in zip(log["attempts"], payloads):
                self.assertEqual((Path(directory) / attempt["source_file"]).read_bytes(), payload)
                manifest = json.loads((Path(directory) / f"provenance_{attempt['sha256'][:16]}.json").read_text())
                self.assertEqual(manifest["license"], "ODbL-1.0")
                self.assertEqual(manifest["url"], attempt["url"])

    def test_http400_body_counted_and_failures_not_retried(self):
        body = b"You requested too many nodes"
        error = urllib.error.HTTPError("https://api.openstreetmap.org", 400, "Bad request", {}, io.BytesIO(body))
        with tempfile.TemporaryDirectory() as directory, patch.object(sections.urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = [error, TimeoutError("fixture"), TimeoutError("fixture")]
            log = json.loads(sections.acquire_sections(Path(directory)).read_text())
            self.assertEqual(factory.return_value.open.call_count, 3)
            self.assertEqual(log["total_received_bytes"], len(body))
            self.assertEqual(log["attempts"][0]["error_body"], body.decode())
            self.assertFalse(any(a["success"] for a in log["attempts"]))
            self.assertFalse(list(Path(directory).glob("map_*.osm")))

    def test_request_limit_checked_before_network(self):
        with patch.object(sections.urllib.request, "build_opener") as factory:
            with self.assertRaises(ValueError):
                sections.acquire_sections(bboxes=sections.BBOXES + sections.BBOXES)
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
