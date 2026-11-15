#!/usr/bin/env python3
"""Fetch selected ambientCG (CC0) texture zips for v004; originals kept, sha256 ledger.
Budget: hard cap 400 MB for the whole operation (well under the 1 GB approval line)."""
import hashlib, json, sys, urllib.request, datetime
from pathlib import Path
RAW = Path('data/raw/textures_cc0')
CAP = 400_000_000
PICK = {  # assetId: attribute
    'LeafSet014': '1K-PNG', 'LeafSet016': '1K-PNG', 'LeafSet024': '1K-PNG', 'LeafSet019': '1K-PNG',
    'Bark011': '1K-PNG', 'Bark012': '1K-PNG', 'Bark014': '1K-PNG',
    'Grass005': '2K-JPG', 'Grass004': '2K-JPG', 'Ground038': '2K-JPG', 'Ground037': '2K-JPG', 'Gravel023': '1K-PNG',
}
def main():
    RAW.mkdir(parents=True, exist_ok=True)
    ledger_p = RAW / 'operation.json'
    ledger = json.loads(ledger_p.read_text()) if ledger_p.exists() else dict(source='https://ambientcg.com', license='CC0 1.0', cap=CAP, files={})
    ids = ','.join(PICK)
    req = urllib.request.Request(f'https://ambientcg.com/api/v2/full_json?id={ids}&include=downloadData&limit=50', headers={'User-Agent': 'Assetto-Exelberg/1.0'})
    meta = json.load(urllib.request.urlopen(req, timeout=60))
    plan = {}
    for a in meta['foundAssets']:
        for folder in a['downloadFolders'].values():
            for cat in folder['downloadFiletypeCategories'].values():
                for d in cat['downloads']:
                    if d['attribute'] == PICK.get(a['assetId']):
                        plan[a['assetId']] = d
    missing = set(PICK) - set(plan)
    if missing: sys.exit(f'missing {missing}')
    total = sum(d['size'] for k, d in plan.items() if k not in ledger['files'])
    used = sum(f['bytes'] for f in ledger['files'].values())
    if used + total > CAP: sys.exit('cap exceeded')
    print('planned bytes', total)
    for k, d in plan.items():
        if k in ledger['files']: continue
        out = RAW / d['fileName']
        r = urllib.request.urlopen(urllib.request.Request(d['downloadLink'], headers={'User-Agent': 'Assetto-Exelberg/1.0'}), timeout=120)
        data = r.read(d['size'] + 1)
        if len(data) != d['size']: sys.exit(f'{k}: size mismatch {len(data)} vs {d["size"]}')
        out.write_bytes(data)
        ledger['files'][k] = dict(file=out.name, url=d['downloadLink'], bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                  attribute=d['attribute'], retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        ledger_p.write_text(json.dumps(ledger, indent=2) + '\n'); print(k, len(data), flush=True)
    print('operation bytes', sum(f['bytes'] for f in ledger['files'].values()))
main()
