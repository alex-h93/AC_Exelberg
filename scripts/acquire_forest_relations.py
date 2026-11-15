#!/usr/bin/env python3
"""Three bounded relation/full requests, then an opt-in separate forest handoff.

No retries, redirects, alternate endpoints, or changes to previous source files.
Run --acquire once; --build can subsequently operate entirely offline.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from route_osm import ROOT, NoRedirect, read_bounded, utc_now, load_osm, merge_sources

RELATION_IDS = (4624, 4625, 15456599)
RAW = ROOT / 'data/raw/full_forest'
MERGED = ROOT / 'data/interim/full_forest/merged.json'
OUT = ROOT / 'data/processed/full_scenery_v002'
ORIGINAL = ROOT / 'data/interim/osm/merged.json'
RESPONSE_LIMIT = 20_000_000
TOTAL_LIMIT = 60_000_000


def write_new(path, content):
    """Refuse overwrites, including operation ledgers (no accidental retries)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(content)


def acquire_relations(raw_dir=RAW):
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_path = raw_dir / 'operation.json'
    # Reserve the ledger before networking, preventing a second invocation.
    write_new(log_path, json.dumps({'status': 'started', 'requested_at_utc': utc_now()}))
    budget = [TOTAL_LIMIT]
    attempts = []
    opener = urllib.request.build_opener(NoRedirect)
    for relation_id in RELATION_IDS:
        url = f'https://api.openstreetmap.org/api/0.6/relation/{relation_id}/full'
        attempt = dict(relation_id=relation_id, url=url, requested_at_utc=utc_now(), success=False)
        attempts.append(attempt)
        before = budget[0]
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'Assetto-Exelberg-Forest/1.0 (private geographic research; Python stdlib)',
                'Accept': 'application/xml', 'Accept-Encoding': 'identity'})
            deadline = time.monotonic() + 60
            try:
                response = opener.open(request, timeout=20)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                attempt['http_status'] = response.code
                payload = read_bounded(response, budget, deadline,
                    limit=RESPONSE_LIMIT if response.code == 200 else 8192)
                if response.code != 200:
                    attempt['error_body'] = payload.decode('utf-8', errors='replace')
                    raise ValueError(f'HTTP {response.code}; no retry or fallback')
                if response.headers.get('Content-Encoding', 'identity') != 'identity':
                    raise ValueError('Unexpected content encoding')
            # Preserve exact successful HTTP bodies even if XML validation fails.
            digest = hashlib.sha256(payload).hexdigest()
            filename = f'relation_{relation_id}_{digest[:16]}.osm'
            destination = raw_dir / filename
            with destination.open('xb') as stream:
                stream.write(payload)
            provenance = dict(source_file=filename, sha256=digest, url=url,
                requested_at_utc=attempt['requested_at_utc'], received_at_utc=utc_now(),
                received_bytes=len(payload), license='ODbL-1.0',
                attribution='© OpenStreetMap contributors',
                license_url='https://www.openstreetmap.org/copyright')
            write_new(raw_dir / f'provenance_{digest[:16]}.json', json.dumps(provenance, indent=2)+'\n')
            attempt.update(source_file=filename, sha256=digest)
            document = load_osm(destination)
            if not any(e['type'] == 'relation' and e['id'] == relation_id for e in document['elements']):
                raise ValueError('Response lacks requested relation')
            attempt['success'] = True
        except (OSError, ValueError, urllib.error.URLError, ET.ParseError, KeyError) as exc:
            attempt['error'] = str(exc)
        finally:
            attempt.update(received_bytes=before-budget[0], finished_at_utc=utc_now())
            log_path.write_text(json.dumps(dict(attempts=attempts,
                total_received_bytes=TOTAL_LIMIT-budget[0], retries=0,
                limits=dict(requests=3, response_bytes=RESPONSE_LIMIT, total_bytes=TOTAL_LIMIT,
                            socket_timeout_seconds=20, deadline_seconds=60)), indent=2)+'\n')
    return log_path


def build(raw_dir=RAW, merged=MERGED, out=OUT):
    """Merge versioned originals plus successful supplements; preserve all inputs."""
    if merged.exists() or out.exists():
        raise FileExistsError('Separate merged/output destination already exists')
    ledger = json.loads((raw_dir/'operation.json').read_text())
    attempts = ledger.get('attempts', [])
    if len(attempts) != 3 or tuple(a['relation_id'] for a in attempts) != RELATION_IDS:
        raise ValueError('Incomplete acquisition ledger')
    supplements = [raw_dir/a['source_file'] for a in attempts if a['success']]
    original = json.loads(ORIGINAL.read_text())
    originals = [ROOT/s['source_file'] for s in original['sources']]
    # Include the previous merged input explicitly, and separately retain each
    # exact original XML and its provenance. Same-version differences abort.
    sources = [ORIGINAL, *originals, *supplements]
    document = merge_sources(sources)
    write_new(merged, json.dumps(document, ensure_ascii=False, indent=2)+'\n')
    provenance = [p.parent/f"provenance_{hashlib.sha256(p.read_bytes()).hexdigest()[:16]}.json"
                  for p in [*originals, *supplements]]
    produce(merged, out, [*sources, *provenance, raw_dir/'operation.json', Path(__file__)])
    return out/'manifest.json'


def produce(merged, out, source_paths):
    """Reuse strict geometry functions without executing the original producer.

    Inherit descriptive schema-1 metadata from the hash-pinned v001 handoff;
    recompute every data-dependent field from the new merged source.
    """
    import numpy as np
    import prepare_full_scenery as p

    template = p.OUT/'manifest.json'
    manifest = json.loads(template.read_text())
    transform, log = p.operation(4326, 25833)
    inventory, polygons = p.build_inventory(json.loads(merged.read_text())['elements'],
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
    manifest.update(transform=log, input_count=len(keep), selected_count=len(index),
        rejected_count=int((~keep).sum()), counts=counts,
        coverage=dict(bin_edges_25833_m=bins.tolist(),
            input_counts=np.histogram(arrays['generating_chainage_25833_m'], bins)[0].tolist(),
            selected_counts=np.histogram(arrays['generating_chainage_25833_m'][keep], bins)[0].tolist()),
        inventory_status_counts={s: sum(e['status'] == s for e in inventory)
                                 for s in ('resolved', 'skipped', 'suppressed')},
        inputs=[p.record(path) for path in [merged, *source_paths, template,
            p.INPUT/'trees.npz', p.INPUT/'route.npz', p.INPUT/'terrain.npz',
            p.INPUT/'manifest.json', Path(p.__file__)]],
        inventory=p.record(inventory_path), output=output)
    manifest['constraints']['minimum_all_route_clearance_m'] = float(distances[keep].min()) if keep.any() else None
    write_new(out/'manifest.json', json.dumps(manifest, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquire', action='store_true')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    if args.acquire:
        print(acquire_relations())
    if args.build:
        print(build())
    if not (args.acquire or args.build):
        parser.error('Choose --acquire and/or --build; default performs no writes/network')


if __name__ == '__main__':
    main()
