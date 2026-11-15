"""Alternative forest policy, strict regression and offline consumer checks."""
import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_full_scenery as strict
import prepare_full_forest_union as union
from test_prepare_full_scenery import node, way, relation, square_nodes
from prepare_prototype import sha


def scene(ranges, roles, **tags):
    elements, members = [], []
    for i, (lo, hi) in enumerate(ranges):
        start = 4*i+1
        elements += square_nodes(start, lo, hi)
        elements.append(way(i+1, [start, start+1, start+2, start+3, start], landuse='forest'))
        members.append((i+1, roles[i]))
    return elements+[relation(100, members, **(tags or dict(landuse='forest')))]


class PolicyTests(unittest.TestCase):
    def check_mask(self, elements, points, expected):
        original = copy.deepcopy(elements)
        inv, polygons = union.build_inventory(elements, lambda xy: xy)
        self.assertEqual(elements, original)
        self.assertEqual(inv[-1]['topology_policy'], union.POLICY)
        self.assertTrue(all(e['status'] == 'suppressed' for e in inv[:-1]))
        np.testing.assert_array_equal(strict.select_anchors(np.array(points), polygons)[0], expected)
        old, _ = strict.build_inventory(elements, lambda xy: xy)
        self.assertEqual(old[-1]['status'], 'skipped')
        return inv

    def test_nested_holes_and_outer_island_never_refilled(self):
        elements = scene([(0, 20), (3, 17), (6, 14), (8, 12)], ['outer', 'inner', 'inner', 'outer'])
        self.check_mask(elements, [[1, 1], [4, 4], [7, 7], [10, 10], [3, 5]], [True, False, False, False, False])

    def test_nested_holes(self):
        self.check_mask(scene([(0, 20), (3, 17), (6, 14)], ['outer', 'inner', 'inner']),
                        [[1, 1], [4, 4], [10, 10]], [True, False, False])

    def test_overlapping_outers_and_inners(self):
        self.check_mask(scene([(0, 10), (5, 15), (2, 7), (6, 9)], ['outer', 'outer', 'inner', 'inner']),
                        [[1, 1], [6, 6], [8, 8], [12, 12], [20, 20]], [True, False, False, True, False])

    def test_strict_exclusions_apply_after_relaxed_forest(self):
        elements = scene([(0, 10), (5, 15)], ['outer', 'outer'])
        elements += square_nodes(20, 1, 3)+square_nodes(24, 11, 13)
        elements += [way(200, [20, 21, 22, 23, 20], building='yes'),
                     way(201, [24, 25, 26, 27, 24], natural='water')]
        _, polygons = union.build_inventory(elements, lambda xy: xy)
        keep, _, _, counts = strict.select_anchors(np.array([[2, 2], [12, 12], [8, 8]]), polygons)
        np.testing.assert_array_equal(keep, [False, False, True])
        self.assertEqual(counts['excluded_in_forest'], 2)

    def test_touching_and_uncontained_inner(self):
        self.check_mask(scene([(0, 10), (0, 4), (20, 30)], ['outer', 'inner', 'inner']),
                        [[0, 2], [5, 5], [25, 25]], [False, True, False])

    def test_building_water_remain_strict_even_when_also_forest(self):
        for tags in ({'building': 'yes'}, {'natural': 'water'}, {'landuse': 'forest', 'building': 'yes'}):
            elements = scene([(0, 10), (5, 15)], ['outer', 'outer'], **tags)
            inv, polygons = union.build_inventory(elements, lambda xy: xy)
            if 'landuse' in tags:
                self.assertEqual(inv[-1]['strict_unresolved_categories'], ['building'])
                self.assertEqual(polygons[-1][0]['categories'], ['forest'])
            else:
                self.assertEqual(inv[-1]['status'], 'skipped')
                self.assertFalse(any(e['type'] == 'relation' for e, _ in polygons))

    def test_all_individual_validation_preserved(self):
        base = scene([(0, 10), (5, 15)], ['outer', 'outer'])
        cases = []
        e = copy.deepcopy(base); e[-1]['members'].append(dict(type='way', ref=999, role='inner')); cases.append(e)
        e = copy.deepcopy(base); e[-1]['members'][0]['role'] = 'other'; cases.append(e)
        e = copy.deepcopy(base); e[-1]['members'][0]['type'] = 'relation'; cases.append(e)
        e = copy.deepcopy(base); e[-1]['members'].append(e[-1]['members'][0].copy()); cases.append(e)
        e = copy.deepcopy(base); e[4]['nodes'] = [1, 2, 3]; cases.append(e)
        e = copy.deepcopy(base); e[4]['nodes'] = [1, 2, 99, 4, 1]; cases.append(e)
        e = copy.deepcopy(base); e[4]['nodes'] = [1, 2, 3, 2, 1]; cases.append(e)
        e = copy.deepcopy(base); e[4]['nodes'] = [1, 3, 2, 4, 1]; cases.append(e)
        e = copy.deepcopy(base); e[1]['lon'] = 0; e[1]['lat'] = 0; cases.append(e)
        # A nonzero-area self intersection (not merely the bow-tie area check).
        e = copy.deepcopy(base)
        for entry, (x, y) in zip(e[:4], [(0, 0), (10, 9), (0, 10), (8, 0)]):
            entry.update(lon=x, lat=y)
        cases.append(e)
        for elements in cases:
            with self.subTest(elements=elements):
                inv, polygons = union.build_inventory(elements, lambda xy: xy)
                self.assertEqual(inv[-1]['status'], 'skipped')
                self.assertFalse(any(e['type'] == 'relation' for e, _ in polygons))
                ways = {e['id']: e for e in elements if e['type'] == 'way'}
                nodes = {e['id']: (e['lon'], e['lat']) for e in elements if e['type'] == 'node'}
                with self.assertRaises(ValueError):
                    union.resolve_union(elements[-1], ways, nodes, lambda xy: xy)


class ConsumerTests(unittest.TestCase):
    def test_generated_contract(self):
        manifest = json.loads((union.OUT/'manifest.json').read_text())
        self.assertEqual(manifest['schema'], 'assetto-exelberg.full-scenery-inputs')
        self.assertEqual(manifest['affected_relation_ids'], [4624, 4625])
        source = dict(np.load(strict.INPUT/'trees.npz', allow_pickle=False))
        result = dict(np.load(union.OUT/'forest_trees.npz', allow_pickle=False))
        transform, _ = strict.operation(4326, 25833)
        inv, polygons = union.build_inventory(json.loads(union.MERGED.read_text())['elements'],
                                              lambda xy: strict.project(transform, xy))
        keep, ids, types, counts = strict.select_anchors(source['xy_25833_m'], polygons)
        np.testing.assert_array_equal(result['source_anchor_index'], np.flatnonzero(keep))
        for key, array in source.items():
            self.assertEqual(result[key].dtype, array.dtype)
            np.testing.assert_array_equal(result[key], array[keep])
        np.testing.assert_array_equal(result['source_forest_id'], ids[keep])
        np.testing.assert_array_equal(result['source_forest_type'], types[keep])
        self.assertEqual(counts, manifest['counts'])
        self.assertEqual(sum(manifest['coverage']['selected_counts']), int(keep.sum()))
        self.assertEqual(inv, json.loads((union.OUT/'source_inventory.json').read_text())['sources'])
        for entry, polygon in polygons:
            if set(entry['categories']) & {'building', 'water'}:
                self.assertFalse(strict.polygon_mask(result['xy_25833_m'], polygon).any())
        with np.load(strict.INPUT/'route.npz') as route, np.load(strict.INPUT/'terrain.npz') as terrain:
            distances = strict.validate_candidates(result, route, terrain)
        self.assertGreater(distances.min(), 10.)
        self.assertEqual(float(distances.min()), manifest['constraints']['minimum_all_route_clearance_m'])
        for entry in manifest['inputs']+[manifest['inventory'], manifest['output']]:
            path = strict.ROOT/entry['path']
            self.assertEqual(path.stat().st_size, entry['bytes'])
            self.assertEqual(sha(path), entry['sha256'])
        with self.assertRaises(FileExistsError):
            union.produce()


if __name__ == '__main__':
    unittest.main()
