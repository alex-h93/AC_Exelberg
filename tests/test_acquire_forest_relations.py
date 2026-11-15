"""Bounded HTTP fixtures and actual strict v002 handoff checks; no network."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import acquire_forest_relations as f
import prepare_full_scenery as p
from route_osm import merge_sources


def response(body, status=200):
    result = io.BytesIO(body)
    result.code, result.headers = status, {}
    return result


class AcquisitionTests(unittest.TestCase):
    def test_exact_endpoints_bytes_provenance_and_no_second_operation(self):
        payloads = [f'<osm version="0.6"><relation id="{n}" version="1"/></osm>'.encode()
                    for n in f.RELATION_IDS]
        with tempfile.TemporaryDirectory() as tmp, patch.object(f.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = [response(b) for b in payloads]
            raw = Path(tmp)
            log = json.loads(f.acquire_relations(raw).read_text())
            self.assertEqual(factory.return_value.open.call_count, 3)
            factory.assert_called_once_with(f.NoRedirect)
            self.assertEqual(log['total_received_bytes'], sum(map(len, payloads)))
            for attempt, body, call in zip(log['attempts'], payloads, factory.return_value.open.call_args_list):
                self.assertTrue(attempt['success'])
                self.assertEqual(call.args[0].full_url, attempt['url'])
                self.assertEqual(call.kwargs['timeout'], 20)
                self.assertTrue(call.args[0].get_header('User-agent'))
                self.assertEqual((raw/attempt['source_file']).read_bytes(), body)
                meta = json.loads((raw/f"provenance_{attempt['sha256'][:16]}.json").read_text())
                self.assertEqual(meta['sha256'], hashlib.sha256(body).hexdigest())
                self.assertEqual(meta['license'], 'ODbL-1.0')
                self.assertEqual(meta['url'], attempt['url'])
            with self.assertRaises(FileExistsError):
                f.acquire_relations(raw)
            self.assertEqual(factory.return_value.open.call_count, 3)

    def test_http400_timeout_invalid_xml_no_retry(self):
        error = urllib.error.HTTPError('https://api.openstreetmap.org', 400, 'Bad request', {}, io.BytesIO(b'too large'))
        with tempfile.TemporaryDirectory() as tmp, patch.object(f.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = [error, TimeoutError('fixture'), response(b'not xml')]
            log = json.loads(f.acquire_relations(Path(tmp)).read_text())
            self.assertEqual(factory.return_value.open.call_count, 3)
            self.assertEqual(log['total_received_bytes'], len(b'too largenot xml'))
            self.assertFalse(any(a['success'] for a in log['attempts']))
            self.assertEqual(log['attempts'][0]['error_body'], 'too large')
            self.assertEqual(len(list(Path(tmp).glob('*.osm'))), 1)

    def test_response_and_total_caps_streamed(self):
        for response_limit, total_limit, expected in [(10, 100, 30), (100, 15, 15)]:
            with self.subTest(response_limit=response_limit), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(f.urllib.request, 'build_opener') as factory, \
                    patch.object(f, 'RESPONSE_LIMIT', response_limit), patch.object(f, 'TOTAL_LIMIT', total_limit):
                factory.return_value.open.side_effect = [response(b'x'*200) for _ in range(3)]
                log = json.loads(f.acquire_relations(Path(tmp)).read_text())
                self.assertEqual(log['total_received_bytes'], expected)
                self.assertFalse(any(a['success'] for a in log['attempts']))
                self.assertFalse(list(Path(tmp).glob('*.osm')))

    def test_merge_latest_version_and_same_version_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.json', Path(tmp)/'b.json'
            old = dict(type='way', id=1, version=1, nodes=[1, 2])
            new = dict(old, version=2, nodes=[1, 3])
            a.write_text(json.dumps(dict(elements=[old])))
            b.write_text(json.dumps(dict(elements=[new])))
            self.assertEqual(merge_sources([a, b])['elements'], [new])
            a.write_text(json.dumps(dict(elements=[dict(old, version=2)])))
            with self.assertRaisesRegex(ValueError, 'Conflicting same-version'):
                merge_sources([a, b])


class ActualHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((f.OUT/'manifest.json').read_text())
        cls.elements = json.loads(f.MERGED.read_text())['elements']
        transform, _ = p.operation(4326, 25833)
        cls.inventory, cls.polygons = p.build_inventory(cls.elements, lambda xy: p.project(transform, xy))

    def test_complete_members_but_strict_topology_blockers(self):
        ways = {e['id'] for e in self.elements if e['type'] == 'way'}
        nodes = {e['id'] for e in self.elements if e['type'] == 'node'}
        for e in self.elements:
            if e['type'] == 'relation' and e['id'] in f.RELATION_IDS:
                self.assertTrue(all(m['ref'] in ways for m in e['members']))
            if e['type'] == 'way':
                self.assertTrue(set(e['nodes']) <= nodes)
        entries = {e['id']: e for e in self.inventory if e['type'] == 'relation'}
        self.assertEqual(entries[4624]['reason'], 'overlapping or nested inner rings')
        self.assertEqual(entries[4625]['reason'], 'overlapping or nested outer rings')
        self.assertEqual(entries[15456599]['status'], 'resolved')

    def test_actual_subset_exclusions_bins_and_validity(self):
        with np.load(p.INPUT/'trees.npz', allow_pickle=False) as src, np.load(f.OUT/'forest_trees.npz', allow_pickle=False) as result:
            keep, ids, types, counts = p.select_anchors(src['xy_25833_m'], self.polygons)
            np.testing.assert_array_equal(result['source_anchor_index'], np.flatnonzero(keep))
            for key in src.files:
                np.testing.assert_array_equal(result[key], src[key][keep])
                self.assertEqual(result[key].dtype, src[key].dtype)
            np.testing.assert_array_equal(result['source_forest_id'], ids[keep])
            np.testing.assert_array_equal(result['source_forest_type'], types[keep])
            self.assertEqual(counts, self.manifest['counts'])
            for entry, poly in self.polygons:
                if set(entry['categories']) & {'building', 'water'}:
                    self.assertFalse(p.polygon_mask(result['xy_25833_m'], poly).any())
            with np.load(p.INPUT/'route.npz') as route, np.load(p.INPUT/'terrain.npz') as terrain:
                p.validate_candidates(dict(result), route, terrain)
            self.assertEqual(sum(self.manifest['coverage']['selected_counts']), int(keep.sum()))
            self.assertEqual(int(keep.sum()), 65)  # Honest conservative fallback, not a target.

    def test_hashes_schema_inventory_and_individual_sources(self):
        self.assertEqual(self.manifest['schema'], 'assetto-exelberg.full-scenery-inputs')
        self.assertEqual(self.manifest['version'], 1)
        self.assertEqual(self.inventory, json.loads((f.OUT/'source_inventory.json').read_text())['sources'])
        entries = self.manifest['inputs']+[self.manifest['inventory'], self.manifest['output']]
        for entry in entries:
            path = f.ROOT/entry['path']
            self.assertEqual(path.stat().st_size, entry['bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])
        paths = {entry['path'] for entry in self.manifest['inputs']}
        self.assertIn(str(f.ORIGINAL.relative_to(f.ROOT)), paths)
        self.assertIn(str(f.MERGED.relative_to(f.ROOT)), paths)
        self.assertEqual(len([s for s in paths if s.endswith('.osm')]), 7)


if __name__ == '__main__':
    unittest.main()
