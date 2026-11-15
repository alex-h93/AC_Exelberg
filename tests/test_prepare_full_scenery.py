"""Offline topology, exclusion and immutable consumer-contract checks."""
import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_full_scenery as p
from prepare_prototype import sha


def node(n, x, y):
    return dict(type='node', id=n, lon=x, lat=y)


def way(n, ids, **tags):
    return dict(type='way', id=n, nodes=ids, tags=tags)


def relation(n, members, **tags):
    return dict(type='relation', id=n, tags=dict(type='multipolygon', **tags),
                members=[dict(type='way', ref=ref, role=role) for ref, role in members])


def square_nodes(start, lo, hi):
    return [node(start+i, x, y) for i, (x, y) in enumerate(
        [(lo, lo), (hi, lo), (hi, hi), (lo, hi)])]


def inventory(elements):
    return p.build_inventory(elements, lambda xy: xy)


class TopologyTests(unittest.TestCase):
    def test_join_reversed_shuffled_members_multiple_outers_and_hole(self):
        elements = square_nodes(1, 0, 10)+square_nodes(5, 3, 7)+square_nodes(9, 20, 30)
        elements += [way(1, [1, 2, 3]), way(2, [1, 4, 3]),
                     way(3, [5, 6, 7]), way(4, [5, 8, 7]),
                     way(5, [9, 10, 11, 12, 9]),
                     relation(50, [(4, 'inner'), (2, 'outer'), (5, 'outer'),
                                   (3, 'inner'), (1, 'outer')], landuse='forest')]
        inv, polygons = inventory(elements)
        self.assertEqual(inv[0]['status'], 'resolved')
        self.assertEqual(inv[0]['outer_rings'], 2)
        points = np.array([[1, 1], [5, 5], [3, 5], [0, 5], [25, 25], [15, 15]])
        keep, ids, types, _ = p.select_anchors(points, polygons)
        np.testing.assert_array_equal(keep, [True, False, False, True, True, False])
        np.testing.assert_array_equal(ids[keep], 50)
        np.testing.assert_array_equal(types[keep], 2)
        _, shuffled = inventory(list(reversed(elements)))
        np.testing.assert_array_equal(p.select_anchors(points, shuffled)[0], keep)

    def test_closed_way_exclusions_use_polygons_not_bounding_boxes(self):
        elements = square_nodes(1, 0, 10)+square_nodes(5, 1, 3)+square_nodes(9, 6, 9)
        elements += [way(100, [1, 2, 3, 4, 1], natural='wood'),
                     way(101, [5, 6, 7, 5], building='yes'),
                     way(102, [9, 10, 11, 12, 9], natural='water')]
        _, polygons = inventory(elements)
        keep, _, _, counts = p.select_anchors(np.array([[2.5, 1.5], [1.1, 2.8], [7, 7], [5, 5], [6, 7]]), polygons)
        np.testing.assert_array_equal(keep, [False, True, False, True, False])
        self.assertEqual(counts['excluded_in_forest'], 3)

    def test_water_and_building_multipolygon_holes(self):
        for tags in ({'building': 'yes'}, {'landuse': 'reservoir'}):
            elements = square_nodes(1, 0, 10)+square_nodes(5, 3, 7)
            elements += [way(1, [1, 2, 3]), way(2, [1, 4, 3]), way(3, [5, 6, 7, 8, 5]),
                         relation(90, [(1, 'outer'), (2, 'outer'), (3, 'inner')], **tags),
                         way(4, [1, 2, 3, 4, 1], landuse='forest')]
            _, polygons = inventory(elements)
            np.testing.assert_array_equal(p.select_anchors(np.array([[1, 1], [5, 5]]), polygons)[0], [False, True])

    def test_overlap_attribution_is_stable_no_duplicate_points(self):
        elements = square_nodes(1, 0, 10)
        elements += [way(200, [1, 2, 3, 4, 1], natural='wood'),
                     way(100, [1, 2, 3, 4, 1], landuse='forest')]
        _, polygons = inventory(elements)
        points = np.array([[1, 1], [11, 11]])
        first = p.select_anchors(points, polygons)
        second = p.select_anchors(points, list(reversed(polygons)))
        for a, b in zip(first[:3], second[:3]):
            np.testing.assert_array_equal(a, b)
        self.assertEqual(first[1][0], 100)
        self.assertEqual(first[3]['overlapping_forest_candidates'], 1)

    def test_parent_members_suppressed_without_refilling_hole(self):
        elements = square_nodes(1, 0, 10)+square_nodes(5, 3, 7)
        elements += [way(1, [1, 2, 3, 4, 1], landuse='forest'),
                     way(2, [5, 6, 7, 8, 5], natural='wood'),
                     relation(3, [(1, 'outer'), (2, 'inner')], landuse='forest')]
        inv, polygons = inventory(elements)
        self.assertEqual([e['status'] for e in inv], ['suppressed', 'suppressed', 'resolved'])
        keep, ids, _, _ = p.select_anchors(np.array([[1, 1], [5, 5]]), polygons)
        np.testing.assert_array_equal(keep, [True, False])
        self.assertEqual(ids[0], 3)
        # Missing parent members must not promote known fragments to forest.
        elements[-1]['members'].append(dict(type='way', ref=999, role='inner'))
        inv, polygons = inventory(elements)
        self.assertEqual(inv[-1]['status'], 'skipped')
        self.assertFalse(polygons)

    def test_missing_disconnected_unsupported_and_invalid_skip(self):
        base = square_nodes(1, 0, 10)
        cases = [
            ([way(1, [1, 2, 3])], 'open'),
            ([way(1, [1, 2, 99, 4, 1])], 'missing geometry'),
            ([way(1, [1, 3, 2, 4, 1])], 'area'),
            ([way(1, [1, 2]), relation(2, [(1, 'outer')], landuse='forest')], 'disconnected'),
            ([relation(2, [(999, 'inner')], landuse='forest')], 'missing member'),
            ([dict(type='relation', id=2, tags=dict(landuse='forest', type='multipolygon'),
                   members=[dict(type='relation', ref=3, role='outer')])], 'unsupported'),
        ]
        for extra, reason in cases:
            with self.subTest(reason=reason):
                extra = copy.deepcopy(extra)
                if extra[-1]['type'] == 'way':
                    extra[-1]['tags'] = dict(landuse='forest')
                inv, polygons = inventory(base+extra)
                self.assertFalse(polygons)
                self.assertEqual(inv[-1]['status'], 'skipped')
                self.assertIn(reason, inv[-1]['reason'])
        with self.assertRaisesRegex(ValueError, 'branching'):
            p.join_rings([[1, 2], [2, 3], [2, 1], [3, 2]])

    def test_uncontained_hole_rejected(self):
        elements = square_nodes(1, 0, 10)+square_nodes(5, 20, 30)
        elements += [way(1, [1, 2, 3, 4, 1]), way(2, [5, 6, 7, 8, 5]),
                     relation(3, [(1, 'outer'), (2, 'inner')], natural='wood')]
        inv, polygons = inventory(elements)
        self.assertFalse(polygons)
        self.assertIn('uncontained', inv[-1]['reason'])


class ActualFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((p.OUT/'manifest.json').read_text())
        cls.source = dict(np.load(p.INPUT/'trees.npz', allow_pickle=False))
        cls.result = dict(np.load(p.OUT/'forest_trees.npz', allow_pickle=False))
        transform, _ = p.operation(4326, 25833)
        cls.inventory, cls.polygons = p.build_inventory(json.loads(p.OSM.read_text())['elements'],
                                                      lambda xy: p.project(transform, xy))

    def test_actual_tree_filter_is_exact_stable_subset(self):
        keep, ids, types, counts = p.select_anchors(self.source['xy_25833_m'], self.polygons)
        indices = np.flatnonzero(keep)
        self.assertEqual(len(keep), 5844)
        self.assertGreater(len(indices), 0)
        self.assertLess(len(indices), len(keep))
        np.testing.assert_array_equal(self.result['source_anchor_index'], indices)
        for key, array in self.source.items():
            self.assertEqual(self.result[key].dtype, array.dtype)
            np.testing.assert_array_equal(self.result[key], array[keep])
        np.testing.assert_array_equal(self.result['source_forest_id'], ids[keep])
        np.testing.assert_array_equal(self.result['source_forest_type'], types[keep])
        self.assertEqual(counts, self.manifest['counts'])
        for entry, polygon in self.polygons:
            if 'forest' not in entry['categories']:
                self.assertFalse(p.polygon_mask(self.result['xy_25833_m'], polygon).any())
        for ident, kind in set(zip(ids[keep], types[keep])):
            polygon = next(poly for e, poly in self.polygons
                           if e['id'] == ident and p.TYPE_CODES[e['type']] == kind)
            self.assertTrue(p.polygon_mask(self.result['xy_25833_m'][(ids[keep] == ident) & (types[keep] == kind)], polygon).all())
        again = p.select_anchors(self.source['xy_25833_m'], list(reversed(self.polygons)))
        for a, b in zip((keep, ids, types), again[:3]):
            np.testing.assert_array_equal(a, b)

    def test_full_terrain_and_route_invariants_preserved(self):
        with np.load(p.INPUT/'route.npz') as route, np.load(p.INPUT/'terrain.npz') as terrain:
            distances = p.validate_candidates(self.source, route, terrain)
            p.validate_candidates(self.result, route, terrain)
            self.assertGreater(distances.min(), 10.)
            broken = dict(self.source, valid=np.zeros(len(distances), bool))
            with self.assertRaises(ValueError):
                p.validate_candidates(broken, route, terrain)

    def test_inventory_and_all_hashes(self):
        self.assertEqual(self.inventory, json.loads((p.OUT/'source_inventory.json').read_text())['sources'])
        skipped = [e for e in self.inventory if e['status'] == 'skipped' and 'forest' in e['categories']]
        self.assertEqual({e['id'] for e in skipped}, {4624, 4625, 15456599})
        self.assertTrue(all('missing member ways' in e['reason'] for e in skipped))
        for entry in self.manifest['inputs']+[self.manifest['inventory'], self.manifest['output']]:
            path = p.ROOT/entry['path']
            self.assertEqual(path.stat().st_size, entry['bytes'])
            self.assertEqual(sha(path), entry['sha256'])
        self.assertEqual(sum(self.manifest['coverage']['selected_counts']), len(self.result['valid']))


if __name__ == '__main__':
    unittest.main()
