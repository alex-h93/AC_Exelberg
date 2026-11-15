#!/usr/bin/env python3
"""Offline, opt-in conservative forest role union; never changes strict products."""
import json
from pathlib import Path

import numpy as np

import prepare_full_scenery as p
from acquire_forest_relations import MERGED, write_new

OUT = p.ROOT / 'data/processed/full_scenery_v003'
POLICY = 'forest-role-union-minus-all-inners-v1'
INTER_RING_ERRORS = {
    'overlapping or nested outer rings',
    'overlapping or nested inner rings',
    'uncontained or touching inner ring',
}


def resolve_union(element, ways, nodes, transform):
    """Validate structure and every ring, omitting ONLY inter-ring constraints."""
    if element['type'] != 'relation' or element.get('tags', {}).get('type') != 'multipolygon':
        raise ValueError('unsupported non-multipolygon relation')
    members = element.get('members', [])
    if not members:
        raise ValueError('missing relation members')
    if any(m['type'] != 'way' or m.get('role', '') not in ('outer', 'inner', '') for m in members):
        raise ValueError('unsupported member type or role')
    if len({m['ref'] for m in members}) != len(members):
        raise ValueError('duplicate relation member')
    missing = sorted(m['ref'] for m in members if m['ref'] not in ways)
    if missing:
        raise ValueError('missing member ways: '+','.join(map(str, missing)))
    outer_ids = p.join_rings([ways[m['ref']].get('nodes', []) for m in members if m.get('role', '') != 'inner'])
    inner_ids = p.join_rings([ways[m['ref']].get('nodes', []) for m in members if m.get('role') == 'inner'])
    if not outer_ids:
        raise ValueError('no outer ring')

    def coordinates(ids):
        missing = sorted(set(ids)-nodes.keys())
        if missing:
            raise ValueError('missing geometry nodes: '+','.join(map(str, missing)))
        xy = transform(np.asarray([nodes[n] for n in ids], dtype=float))
        p.validate_ring(xy)
        return xy

    return [coordinates(ids) for ids in outer_ids], [coordinates(ids) for ids in inner_ids]


def build_inventory(elements, transform):
    """Strict by default; only known inter-ring failures in forests are eligible.

    Revalidate structure and individual rings rather than trusting the strict
    diagnostic. Invalid building/water categories never inherit relaxed geometry.
    """
    inventory, polygons = p.build_inventory(elements, transform)
    ways = {e['id']: e for e in elements if e['type'] == 'way'}
    relations = {e['id']: e for e in elements if e['type'] == 'relation'}
    nodes = {e['id']: (e['lon'], e['lat']) for e in elements
             if e['type'] == 'node' and 'lon' in e and 'lat' in e}
    for entry in inventory:
        if (entry['type'] != 'relation' or 'forest' not in entry['categories']
                or entry['status'] != 'skipped' or entry['reason'] not in INTER_RING_ERRORS):
            continue
        polygon = resolve_union(relations[entry['id']], ways, nodes, transform)
        entry.update(status='resolved', strict_rejection=entry.pop('reason'),
                     topology_policy=POLICY, outer_rings=len(polygon[0]), inner_rings=len(polygon[1]),
                     warning='Inter-ring topology accepted only for forest; all inner rings subtract, including islands.')
        relaxed = dict(entry, categories=['forest'])
        polygons.append((relaxed, polygon))
        other = [c for c in entry['categories'] if c != 'forest']
        if other:
            entry['strict_unresolved_categories'] = other
    return inventory, polygons


def produce(merged=MERGED, out=OUT):
    if out.exists():
        raise FileExistsError('Separate output destination already exists')
    transform, log = p.operation(4326, 25833)
    inventory, polygons = build_inventory(json.loads(merged.read_text())['elements'],
                                          lambda xy: p.project(transform, xy))
    with np.load(p.INPUT/'trees.npz', allow_pickle=False) as source:
        arrays = {k: source[k] for k in source.files}
    with np.load(p.INPUT/'route.npz', allow_pickle=False) as route, np.load(p.INPUT/'terrain.npz', allow_pickle=False) as terrain:
        distances = p.validate_candidates(arrays, route, terrain)
        end = float(route['full_chainage_25833_m'][-1])
    keep, ids, types, counts = p.select_anchors(arrays['xy_25833_m'], polygons)
    index = np.flatnonzero(keep).astype(np.int64)
    out.mkdir(parents=True, exist_ok=False)
    output = p.save_arrays(out/'forest_trees.npz', **{k: v[keep] for k, v in arrays.items()},
        source_anchor_index=index, source_forest_id=ids[keep], source_forest_type=types[keep])
    inventory_path = out/'source_inventory.json'
    write_new(inventory_path, json.dumps(dict(type_codes=p.TYPE_CODES, sources=inventory), indent=2, allow_nan=False)+'\n')
    bins = np.arange(0., end+1000., 1000.)
    affected = [e['id'] for e in inventory if 'topology_policy' in e]
    manifest = dict(schema='assetto-exelberg.full-scenery-inputs', version=1,
        variant='full_scenery_v003', topology_policy=POLICY, affected_relation_ids=affected,
        coordinates=dict(horizontal_epsg=25833, vertical_epsg=9274, origin_m=p.ORIGIN.tolist()),
        transform=log, input_count=len(keep), selected_count=len(index), rejected_count=int((~keep).sum()),
        counts=counts, coverage=dict(bin_edges_25833_m=bins.tolist(),
            input_counts=np.histogram(arrays['generating_chainage_25833_m'], bins)[0].tolist(),
            selected_counts=np.histogram(arrays['generating_chainage_25833_m'][keep], bins)[0].tolist()),
        inventory_status_counts={s: sum(e['status'] == s for e in inventory)
                                 for s in ('resolved', 'skipped', 'suppressed')},
        constraints=dict(upstream_valid_anchors=True, upstream_valid_terrain_cells=True,
            minimum_all_route_clearance_m=float(distances[keep].min()) if keep.any() else None,
            unchanged_selected_source_arrays=True),
        method='Forest: union of individually valid outers minus union of ALL individually valid inners; then strict building/water exclusions. No island restoration or coordinate repair.',
        overlap_attribution='way before relation, ascending OSM ID; one output row per original selected anchor',
        inputs=[p.record(path) for path in [merged, p.INPUT/'trees.npz', p.INPUT/'route.npz',
            p.INPUT/'terrain.npz', p.INPUT/'manifest.json', Path(p.__file__), Path(__file__)]],
        inventory=p.record(inventory_path), output=output,
        attribution='© OpenStreetMap contributors, ODbL; source anchor terrain © BEV, CC BY 4.0',
        warnings=[f'Alternative inter-ring forest policy {POLICY}; affected relation IDs: {affected}.',
            'All inner unions subtract, including nested holes and outer islands inside holes; approximate real forest mask, not measured individual trees.',
            'Incomplete or individually invalid forests remain skipped; no invented, snapped, filled or reconstructed open rings.',
            'Building/water validation remains strict; unresolved exclusions remain coverage gaps in inventory.',
            'Offline only; no Blender, game, deployment or runtime validation. Strict v001/v002 and source assets unchanged.'])
    write_new(out/'manifest.json', json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    return manifest


if __name__ == '__main__':
    print(json.dumps(produce(), indent=2))
