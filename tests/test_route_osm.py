"""Offline standard-library tests: python3 -m unittest discover -s tests -v."""
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("route_osm", Path(__file__).resolve().parents[1] / "scripts/route_osm.py")
route = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = route
SPEC.loader.exec_module(route)


def fixture(tags=None, points=None):
    points = points or [(16.0, 48.0), (16.01, 48.0), (16.02, 48.0)]
    return {"elements": [dict(type="node", id=i + 1, lon=p[0], lat=p[1]) for i, p in enumerate(points)] +
            [dict(type="way", id=100, nodes=list(range(1, len(points) + 1)),
                  tags={"highway": "secondary", "ref": "L120", **(tags or {})})]}


class GeometryTests(unittest.TestCase):
    def test_distance_spherical_and_lon_lat_order(self):
        self.assertAlmostEqual(route.distance((0, 0), (1, 0)), 111195.08, places=1)
        self.assertLess(route.distance((16, 48), (17, 48)), 75000)
        self.assertEqual(route.distance((16, 48), (16, 48)), 0)
        self.assertTrue(math.isfinite(route.distance((0, 0), (180, 0))))

    def test_edge_snap_not_vertex(self):
        coordinate, fraction, offset = route.project_to_edge((16.005, 48.0001), (16, 48), (16.01, 48))
        self.assertAlmostEqual(fraction, 0.5)
        self.assertEqual(coordinate, (16.005, 48))
        self.assertAlmostEqual(offset, 11.12, places=1)

    def test_projection_clamps_and_degenerate(self):
        self.assertEqual(route.project_to_edge((-1, 0), (0, 0), (1, 0))[1], 0)
        self.assertEqual(route.project_to_edge((2, 0), (0, 0), (1, 0))[1], 1)
        self.assertEqual(route.project_to_edge((2, 0), (1, 0), (1, 0))[0], (1, 0))


class GraphTests(unittest.TestCase):
    def path(self, tags=None, start=(16.002, 48), finish=(16.018, 48)):
        segments = route.segments_from_osm(fixture(tags))
        graph, a, b, snaps = route.snap_endpoints(segments, start, finish)
        return route.shortest_path(graph, a, b), snaps

    def test_continuous_ordered_path_with_edge_snaps(self):
        path, snaps = self.path()
        self.assertEqual(path[0].a, (16.002, 48))
        self.assertEqual(path[-1].b, (16.018, 48))
        self.assertEqual(path[0].b, path[1].a)
        self.assertTrue(all(s["offset_m"] < 0.001 for s in snaps))
        self.assertAlmostEqual(sum(e.length for e in path), route.distance(path[0].a, path[-1].b), places=3)

    def test_same_edge_two_snaps(self):
        path, _ = self.path(start=(16.002, 48), finish=(16.008, 48))
        self.assertEqual(len(path), 1)
        self.assertAlmostEqual(path[0].length, route.distance((16.002, 48), (16.008, 48)))

    def test_same_position_snaps(self):
        path, _ = self.path(start=(16.005, 48), finish=(16.005, 48))
        self.assertEqual(path, [])

    def test_node_endpoint_snap(self):
        path, _ = self.path(start=(16.0, 48), finish=(16.02, 48))
        self.assertEqual(len(path), 2)

    def test_oneway_forward_and_blocked_reverse(self):
        self.assertTrue(self.path({"oneway": "yes"})[0])
        with self.assertRaisesRegex(ValueError, "No directed path"):
            self.path({"oneway": "yes"}, (16.018, 48), (16.002, 48))

    def test_reverse_oneway(self):
        self.assertTrue(self.path({"oneway": "-1"}, (16.018, 48), (16.002, 48))[0])
        with self.assertRaises(ValueError):
            self.path({"oneway": "-1"})

    def test_roundabout_and_car_override(self):
        self.assertEqual(route.directions({"junction": "roundabout"}), (True, False))
        self.assertEqual(route.directions({"junction": "roundabout", "oneway": "no"}), (True, True))
        self.assertEqual(route.directions({"oneway": "yes", "oneway:motorcar": "no"}), (True, True))
        self.assertEqual(route.directions({"oneway": "reversible"}), (False, False))

    def test_access_precedence_and_conservative_restrictions(self):
        self.assertFalse(route.car_access({"highway": "secondary", "access": "private"}))
        self.assertTrue(route.car_access({"highway": "secondary", "access": "no", "motorcar": "yes"}))
        self.assertFalse(route.car_access({"highway": "secondary", "motorcar": "no", "access": "yes"}))
        self.assertFalse(route.car_access({"highway": "footway"}))
        self.assertFalse(route.car_access({"highway": "secondary", "access": "destination"}))

    def test_named_corridor_only(self):
        self.assertTrue(route.corridor_way({"ref": "L 120"}))
        self.assertTrue(route.corridor_way({"name": "Neuwaldegger Straße"}))
        self.assertFalse(route.corridor_way({"ref": "L121", "name": "Other road"}))
        with self.assertRaises(ValueError):
            route.segments_from_osm(fixture({"ref": "L121"}))

    def test_missing_node_and_overpass_remark_fail(self):
        document = fixture()
        document["elements"].pop(1)
        with self.assertRaisesRegex(ValueError, "Missing geometry"):
            route.segments_from_osm(document)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            route.segments_from_osm({"remark": "runtime error", "elements": []})

    def test_snap_distance_limit(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.path(start=(17, 49))

    def test_geometric_crossing_is_not_junction(self):
        # Two crossing lines without a shared OSM node must remain disconnected.
        tags = {"highway": "secondary", "ref": "L120"}
        segments = [route.Segment((1, 0), 1, 2, (16, 48), (16.02, 48.02), tags, True, True),
                    route.Segment((2, 0), 3, 4, (16, 48.02), (16.02, 48), tags, True, True)]
        graph, a, b, _ = route.snap_endpoints(segments, (16, 48), (16.02, 48))
        with self.assertRaisesRegex(ValueError, "No directed path"):
            route.shortest_path(graph, a, b)

    def test_shortest_path_uses_distance_not_hops(self):
        a, b, c = (16, 48), (16.01, 48), (16.005, 48.1)
        edge = lambda target, x, y: route.Edge(target, x, y, 1, {})
        graph = {1: [edge(2, a, b), edge(3, a, c)], 3: [edge(2, c, b)]}
        self.assertEqual(len(route.shortest_path(graph, 1, 2)), 1)

    def test_road_grouping(self):
        path, _ = self.path({"name": "Tullner Straße"})
        groups = route.route_groups(path)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["way_ids"], [100])
        self.assertEqual(groups[0]["length_m"], sum(e.length for e in path))


class XmlTests(unittest.TestCase):
    XML = b'''<osm version="0.6"><node id="1" version="1" lon="16" lat="48"/>
      <node id="2" version="1" lon="16.01" lat="48"/>
      <way id="100" version="2"><nd ref="1"/><nd ref="2"/>
      <tag k="highway" v="secondary"/><tag k="ref" v="L120"/></way>
      <relation id="100" version="1"><member type="way" ref="100" role="from"/>
      <tag k="type" v="restriction"/></relation></osm>'''

    def test_xml_geometry_tags_and_relation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.osm"
            source.write_bytes(self.XML)
            document = route.load_osm(source)
            segments = route.segments_from_osm(document)
            self.assertEqual(len(segments), 1)
            self.assertEqual(segments[0].a, (16, 48))
            self.assertEqual(document["elements"][-1]["members"][0]["ref"], 100)
            self.assertEqual(source.read_bytes(), self.XML)

    def test_merge_dedup_versions_provenance_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = [Path(directory) / n for n in ("a.osm", "b.osm")]
            first.write_bytes(self.XML)
            second.write_bytes(self.XML)
            merged = route.merge_sources([first, second])
            self.assertEqual(len(merged["elements"]), 4)
            self.assertEqual(len(merged["sources"]), 2)
            self.assertEqual(merged["sources"][0]["sha256"], route.hashlib.sha256(self.XML).hexdigest())
            self.assertEqual(merged["license"], "ODbL-1.0")
            second.write_bytes(self.XML.replace(b'lon="16"', b'lon="16.001"'))
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                route.merge_sources([first, second])
            second.write_bytes(second.read_bytes().replace(b'id="1" version="1"', b'id="1" version="2"'))
            merged = route.merge_sources([second, first])
            node = next(e for e in merged["elements"] if e["type"] == "node" and e["id"] == 1)
            self.assertEqual(node["lon"], 16.001)

    def test_xml_root_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.osm"
            source.write_text("<html/>")
            with self.assertRaisesRegex(ValueError, "root"):
                route.load_osm(source)


class OutputTests(unittest.TestCase):
    def test_build_geojson_and_self_contained_svg_offline(self):
        # Deliberately synthetic geometry, isolated from all project outputs.
        document = fixture({"name": "Tullner Straße"}, [route.START, route.FINISH])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic.json"
            source.write_text(json.dumps(document))
            with patch.object(route, "ROOT", root), patch("builtins.print"):
                route.build(source)
            collection = json.loads((root / "data/processed/route.geojson").read_text())
            feature = collection["features"][0]
            self.assertEqual(feature["geometry"]["coordinates"][0], list(route.START))
            self.assertEqual(feature["geometry"]["coordinates"][-1], list(route.FINISH))
            self.assertTrue(all(len(p) == 2 for p in feature["geometry"]["coordinates"]))
            self.assertEqual(feature["properties"]["status"], "provisional_not_screenshot_verified")
            svg = (root / "data/processed/route.svg").read_text()
            ET.fromstring(svg)
            self.assertNotIn("<image", svg)
            report = (root / "docs/validation/ROUTE_REPORT.md").read_text()
            self.assertIn("not accepted final route", report)
            self.assertIn("No elevations sampled", report)
            self.assertIn("over 10%", report)


class TransferTests(unittest.TestCase):
    def test_stream_cap_and_cumulative_budget(self):
        body = io.BytesIO(b"x" * 100)
        budget = [50]
        with self.assertRaisesRegex(ValueError, "cap"):
            route.read_bounded(body, budget, time.monotonic() + 1, limit=20)
        self.assertEqual(body.tell(), 20)
        self.assertEqual(budget, [30])
        with self.assertRaises(ValueError):
            route.read_bounded(body, budget, time.monotonic() + 1)
        self.assertEqual(body.tell(), 50)
        self.assertEqual(budget, [0])

    def test_complete_small_body_and_deadline(self):
        budget = [100]
        self.assertEqual(route.read_bounded(io.BytesIO(b"ok"), budget, time.monotonic() + 1), b"ok")
        self.assertEqual(budget, [98])
        with self.assertRaises(TimeoutError):
            route.read_bounded(io.BytesIO(), budget, time.monotonic() - 1)

    def test_max_three_endpoint_attempts_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(route.urllib.request, "build_opener") as opener:
                opener.return_value.open.side_effect = TimeoutError("offline fixture")
                with self.assertRaisesRegex(RuntimeError, "three"):
                    route.acquire(Path(directory))
                self.assertEqual(opener.return_value.open.call_count, 3)
                calls = opener.return_value.open.call_args_list
                self.assertTrue(all(call.kwargs["timeout"] == 20 for call in calls))
                self.assertTrue(all(call.args[0].get_header("User-agent") for call in calls))
            logs = list(Path(directory).glob("failed_*.json"))
            log = json.loads(logs[0].read_text())
            self.assertEqual(len(log["attempts"]), 3)
            self.assertEqual(log["total_received_bytes"], 0)

    def test_success_preserves_exact_payload_and_checksum(self):
        payload = json.dumps(fixture()).encode()
        response = io.BytesIO(payload)
        response.code = 200
        response.headers = {}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(route.urllib.request, "build_opener") as opener:
                opener.return_value.open.return_value = response
                source, manifest = route.acquire(Path(directory))
                self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertEqual(source.read_bytes(), payload)
            provenance = json.loads(manifest.read_text())
            self.assertEqual(provenance["sha256"], route.hashlib.sha256(payload).hexdigest())
            self.assertEqual(provenance["total_received_bytes"], len(payload))
            self.assertEqual(provenance["query"], route.QUERY)
            self.assertEqual(provenance["license"], "ODbL-1.0")

    def test_redirects_disabled(self):
        self.assertIsNone(route.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org"))


if __name__ == "__main__":
    unittest.main()
