#!/usr/bin/env python3
"""Offline OSM polygon refinement of immutable full-track tree candidates."""
import json
from pathlib import Path

import numpy as np

from prepare_full_track import ORIGIN, nearest_segment_distance
from prepare_prototype import ROOT, operation, project, record, save_arrays

INPUT = ROOT / 'data/processed/full_track_inputs'
OUT = ROOT / 'data/processed/full_scenery'
OSM = ROOT / 'data/interim/osm/merged.json'
TYPE_CODES = {'way': 1, 'relation': 2}


def categories(tags):
    result = []
    if tags.get('landuse') == 'forest' or tags.get('natural') == 'wood':
        result.append('forest')
    if tags.get('building', 'no') != 'no':
        result.append('building')
    if (tags.get('natural') in ('water', 'wetland', 'bay')
            or tags.get('landuse') in ('reservoir', 'basin', 'salt_pond')
            or tags.get('waterway') in ('riverbank', 'dock')
            or tags.get('water', 'no') != 'no'):
        result.append('water')
    return result


def join_rings(parts):
    """Join whole ways by endpoint node IDs, never by coordinate proximity."""
    pending = [list(p) for p in parts]
    if any(len(p) < 2 for p in pending):
        raise ValueError('short member way')
    # Ambiguous branching must not be resolved by arbitrary member order.
    ends = {}
    for p in pending:
        if p[0] != p[-1]:
            for n in (p[0], p[-1]):
                ends[n] = ends.get(n, 0) + 1
    if any(v != 2 for v in ends.values()):
        raise ValueError('disconnected or branching member endpoints')
    rings = []
    while pending:
        ring = pending.pop(0)
        while ring[0] != ring[-1]:
            matches = [i for i, p in enumerate(pending) if ring[-1] in (p[0], p[-1])]
            if len(matches) != 1:
                raise ValueError('unresolved member chain')
            p = pending.pop(matches[0])
            if p[-1] == ring[-1]:
                p.reverse()
            ring.extend(p[1:])
        if len(ring) < 4 or len(set(ring[:-1])) != len(ring)-1:
            raise ValueError('degenerate or repeated-node ring')
        rings.append(ring)
    return rings


def ring_contains(points, ring):
    """Even/odd ray test; boundary is included (1 micrometre tolerance)."""
    points = np.asarray(points)
    inside = np.zeros(len(points), bool)
    boundary = inside.copy()
    x, y = points.T
    for a, b in zip(ring[:-1], ring[1:]):
        v = b-a
        length2 = np.dot(v, v)
        if length2 == 0:
            raise ValueError('zero-length polygon edge')
        t = np.clip(((points-a)*v).sum(axis=1)/length2, 0., 1.)
        boundary |= np.sum((points-a-t[:, None]*v)**2, axis=1) <= 1.e-12
        if b[1] != a[1]:
            inside ^= ((a[1] > y) != (b[1] > y)) & (x < a[0]+(y-a[1])*v[0]/v[1])
    return inside | boundary


def edges_intersect(a, b, c, d):
    """Vectorized inclusive segment intersection, including collinear contact."""
    def cross(u, v):
        return u[..., 0]*v[..., 1]-u[..., 1]*v[..., 0]
    ab, cd = b-a, d-c
    s1, s2 = cross(ab, c-a), cross(ab, d-a)
    s3, s4 = cross(cd, a-c), cross(cd, b-c)
    boxes = np.all(np.maximum(np.minimum(a, b), np.minimum(c, d)) <=
                   np.minimum(np.maximum(a, b), np.maximum(c, d)), axis=-1)
    return boxes & (s1*s2 <= 0) & (s3*s4 <= 0)


def validate_ring(ring):
    if not np.isfinite(ring).all() or np.any(np.all(np.diff(ring, axis=0) == 0, axis=1)):
        raise ValueError('nonfinite or zero-length ring edge')
    p = ring-ring[0]
    area = abs(np.sum(p[:-1, 0]*p[1:, 1]-p[1:, 0]*p[:-1, 1]))
    if area <= 1.e-8:
        raise ValueError('zero-area ring')
    count = len(ring)-1
    for i in range(count):
        js = np.arange(i+2, count)
        if i == 0:
            js = js[js != count-1]
        if np.any(edges_intersect(ring[i], ring[i+1], ring[js], ring[js+1])):
            raise ValueError('self-intersecting ring')


def rings_touch(a, b):
    return any(np.any(edges_intersect(x, y, b[:-1], b[1:]))
               for x, y in zip(a[:-1], a[1:]))


def resolve(element, ways, nodes, transform):
    if element['type'] == 'way':
        ids = element.get('nodes', [])
        if not ids or ids[0] != ids[-1]:
            raise ValueError('open or missing way geometry')
        outer_ids, inner_ids = join_rings([ids]), []
    else:
        if element.get('tags', {}).get('type') != 'multipolygon':
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
        outer_ids = join_rings([ways[m['ref']].get('nodes', []) for m in members if m.get('role', '') != 'inner'])
        inner_ids = join_rings([ways[m['ref']].get('nodes', []) for m in members if m.get('role') == 'inner'])
    if not outer_ids:
        raise ValueError('no outer ring')
    def coordinates(ids):
        missing = sorted(set(ids)-nodes.keys())
        if missing:
            raise ValueError('missing geometry nodes: '+','.join(map(str, missing)))
        xy = np.asarray([nodes[n] for n in ids], dtype=float)
        xy = transform(xy)
        validate_ring(xy)
        return xy
    outer = [coordinates(ids) for ids in outer_ids]
    inner = [coordinates(ids) for ids in inner_ids]
    # Reject invalid/ambiguous topology instead of attempting geometric repair.
    for i, a in enumerate(outer):
        for b in outer[i+1:]:
            if rings_touch(a, b) or ring_contains(a[:1], b)[0] or ring_contains(b[:1], a)[0]:
                raise ValueError('overlapping or nested outer rings')
    for i, hole in enumerate(inner):
        if sum(ring_contains(hole[:1], o)[0] for o in outer) != 1 or any(rings_touch(hole, o) for o in outer):
            raise ValueError('uncontained or touching inner ring')
        for other in inner[i+1:]:
            if rings_touch(hole, other) or ring_contains(hole[:1], other)[0] or ring_contains(other[:1], hole)[0]:
                raise ValueError('overlapping or nested inner rings')
    return outer, inner


def polygon_mask(points, polygon):
    outer, inner = polygon
    result = np.zeros(len(points), bool)
    for ring in outer:
        result |= ring_contains(points, ring)
    for ring in inner:
        result &= ~ring_contains(points, ring)
    return result


def build_inventory(elements, transform):
    ways = {e['id']: e for e in elements if e['type'] == 'way'}
    nodes = {e['id']: (e['lon'], e['lat']) for e in elements
             if e['type'] == 'node' and 'lon' in e and 'lat' in e}
    relevant = sorted((e for e in elements if e['type'] in TYPE_CODES and categories(e.get('tags', {}))),
                      key=lambda e: (TYPE_CODES[e['type']], e['id']))
    # Suppress member forest ways even for incomplete parents: treating an inner
    # or closed fragment as standalone forest could silently fill unknown holes.
    parents = {}
    for e in relevant:
        if e['type'] == 'relation' and 'forest' in categories(e['tags']):
            for m in e.get('members', []):
                if m['type'] == 'way':
                    parents.setdefault(m['ref'], []).append(e['id'])
    inventory, polygons = [], []
    for e in relevant:
        entry = dict(type=e['type'], id=e['id'], tags=e.get('tags', {}), categories=categories(e.get('tags', {})))
        if e['type'] == 'relation':
            entry['members'] = e.get('members', [])
        suppressed = e['type'] == 'way' and e['id'] in parents and 'forest' in entry['categories']
        if suppressed:
            entry['forest_parent_ids'] = sorted(parents[e['id']])
            entry['categories'] = [c for c in entry['categories'] if c != 'forest']
        if not entry['categories']:
            entry.update(status='suppressed', reason='forest relation member; no standalone forest mask')
        else:
            try:
                polygon = resolve(e, ways, nodes, transform)
                entry.update(status='resolved', outer_rings=len(polygon[0]), inner_rings=len(polygon[1]))
                polygons.append((entry, polygon))
            except ValueError as exc:
                entry.update(status='skipped', reason=str(exc))
        inventory.append(entry)
    return inventory, polygons


def select_anchors(points, polygons):
    source_id = np.zeros(len(points), np.int64)
    source_type = np.zeros(len(points), np.uint8)
    forest = np.zeros(len(points), bool)
    excluded = forest.copy()
    overlap = np.zeros(len(points), np.int32)
    # Deterministic overlap attribution: way before relation, then ascending ID.
    for entry, polygon in sorted(polygons, key=lambda p: (TYPE_CODES[p[0]['type']], p[0]['id'])):
        mask = polygon_mask(points, polygon)
        if 'forest' in entry['categories']:
            fresh = mask & ~forest
            source_id[fresh] = entry['id']
            source_type[fresh] = TYPE_CODES[entry['type']]
            forest |= mask
            overlap += mask
        if any(c in entry['categories'] for c in ('building', 'water')):
            excluded |= mask
    return forest & ~excluded, source_id, source_type, dict(
        forest_mask_count=int(forest.sum()), excluded_in_forest=int((forest & excluded).sum()),
        overlapping_forest_candidates=int((overlap > 1).sum()))


def validate_candidates(arrays, route, terrain):
    """Fail on broken upstream invariants; do not silently repair source arrays."""
    xy = arrays['xy_25833_m']
    if not all(np.isfinite(a).all() for a in arrays.values()) or not arrays['valid'].all():
        raise ValueError('nonfinite or invalid upstream anchors')
    distances = nearest_segment_distance(xy, route['full_xy_25833_m'])
    if np.any(distances <= 10.) or not np.allclose(distances, arrays['nearest_route_segment_distance_m'], atol=1.e-8, rtol=0):
        raise ValueError('upstream all-route clearance invariant failed')
    np.testing.assert_allclose(arrays['local_xyz_m'][:, :2], xy-ORIGIN[:2], atol=1.e-8, rtol=0)
    np.testing.assert_allclose(arrays['local_xyz_m'][:, 2], arrays['raw_height_9274_m']-ORIGIN[2], atol=1.e-8, rtol=0)
    x, y = terrain['x_m'][0]+ORIGIN[0], terrain['y_m'][:, 0]+ORIGIN[1]
    ci = np.searchsorted(x, xy[:, 0], side='right')-1
    ri = np.searchsorted(y, xy[:, 1], side='right')-1
    cells = terrain['valid_cells']
    if np.any((ci < 0) | (ri < 0) | (ci >= cells.shape[1]) | (ri >= cells.shape[0])):
        raise ValueError('anchor outside terrain cells')
    if not cells[ri, ci].all():
        raise ValueError('anchor in invalid terrain cell')
    return distances


def main():
    transform, log = operation(4326, 25833)
    elements = json.loads(OSM.read_text())['elements']
    inventory, polygons = build_inventory(elements, lambda xy: project(transform, xy))
    with np.load(INPUT/'trees.npz', allow_pickle=False) as source:
        arrays = {k: source[k] for k in source.files}
    with np.load(INPUT/'route.npz') as route, np.load(INPUT/'terrain.npz') as terrain:
        distances = validate_candidates(arrays, route, terrain)
        end = float(route['full_chainage_25833_m'][-1])
    keep, ids, types, counts = select_anchors(arrays['xy_25833_m'], polygons)
    index = np.flatnonzero(keep).astype(np.int64)
    OUT.mkdir(parents=True, exist_ok=True)
    output = save_arrays(OUT/'forest_trees.npz', **{k: v[keep] for k, v in arrays.items()},
                         source_anchor_index=index, source_forest_id=ids[keep], source_forest_type=types[keep])
    inventory_path = OUT/'source_inventory.json'
    inventory_path.write_text(json.dumps(dict(type_codes=TYPE_CODES, sources=inventory), indent=2, allow_nan=False)+'\n')
    bins = np.arange(0., end+1000., 1000.)
    coverage = dict(bin_edges_25833_m=bins.tolist(),
                    input_counts=np.histogram(arrays['generating_chainage_25833_m'], bins)[0].tolist(),
                    selected_counts=np.histogram(arrays['generating_chainage_25833_m'][keep], bins)[0].tolist())
    manifest = dict(schema='assetto-exelberg.full-scenery-inputs', version=1,
        coordinates=dict(horizontal_epsg=25833, vertical_epsg=9274, origin_m=ORIGIN.tolist()),
        transform=log, input_count=len(keep), selected_count=len(index), rejected_count=int((~keep).sum()),
        counts=counts, coverage=coverage, inventory_status_counts={s: sum(e['status'] == s for e in inventory)
            for s in ('resolved', 'skipped', 'suppressed')},
        constraints=dict(upstream_valid_anchors=True, upstream_valid_terrain_cells=True,
            minimum_all_route_clearance_m=float(distances[keep].min()) if keep.any() else None,
            unchanged_selected_source_arrays=True),
        method='OSM closed ways / complete multipolygons joined by node IDs; outer union minus inner union; building/water subtraction; boundary-inclusive outers, boundary-exclusive holes.',
        overlap_attribution='way before relation, ascending OSM ID; one output row per original selected anchor',
        inputs=[record(p) for p in (OSM, INPUT/'trees.npz', INPUT/'route.npz', INPUT/'terrain.npz', INPUT/'manifest.json', Path(__file__))],
        inventory=record(inventory_path), output=output,
        attribution='© OpenStreetMap contributors, ODbL; source anchor terrain © BEV, CC BY 4.0',
        warnings=['Incomplete/invalid relations skipped in full, including known fragments; no invented geometry or missing holes.',
            'Unresolved building/water polygons cannot exclude anchors; inventory records these coverage gaps.',
            'Synthetic candidate rows remain artificial; polygon masking is not observed individual trees, species, survey accuracy, or complete forest coverage.',
            'No changes to full_track_inputs or producer. Optional separate consumer input; no Blender/game/runtime validation.'])
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: manifest[k] for k in ('input_count', 'selected_count', 'counts', 'coverage', 'inventory_status_counts')}, indent=2))


if __name__ == '__main__':
    main()
