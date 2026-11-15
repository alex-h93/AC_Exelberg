#!/usr/bin/env python3
"""v011 installer (usage: install_full_track_v011.py forward|reverse [--install]); DRY-RUN unless --install is given explicitly.

Copies build/full_track_v011/exelberg_full_v010 into the game's content/tracks as a NEW
folder (refuses if it exists), verifying every file against the package manifest hashes,
staging in a hidden temp folder and renaming atomically. Never touches v001-v004 folders.
"""
import argparse
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from install_ac_test import GAME, require

ROOT = Path(__file__).resolve().parents[1]
import sys
MODE = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ('forward', 'reverse') else 'forward'
TRACK_ID = {'forward': 'exelberg_full_v011', 'reverse': 'exelberg_reverse_v011'}[MODE]
PACKAGE = ROOT / 'build/full_track_v011' / TRACK_ID
MANIFEST = ROOT / f'data/processed/full_track_package_v011_{MODE}/manifest.json'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(package=PACKAGE, manifest=MANIFEST):
    files = json.loads(Path(manifest).read_text())['package']['files']
    listed = {f['path'] for f in files}
    actual = {p.relative_to(package).as_posix() for p in Path(package).rglob('*') if p.is_file()}
    require(listed == actual, f'inventory differs: {sorted(listed ^ actual)}')
    require(not any(p.is_symlink() for p in Path(package).rglob('*')), 'symlink in package')
    for f in files:
        require(sha(Path(package) / f['path']) == f['sha256'], 'hash differs: ' + f['path'])
    return files


def install(commit=False, game=GAME):
    files = verify()
    tracks = Path(game).resolve(strict=True) / 'content/tracks'
    require(tracks.is_dir(), 'content/tracks missing')
    dest = tracks / TRACK_ID
    require(not dest.exists() and not dest.is_symlink(), f'Destination exists: {dest}')
    result = dict(mode='INSTALL' if commit else 'DRY_RUN', destination=str(dest), files=len(files),
                  bytes=sum(f['bytes'] for f in files))
    if not commit:
        return result
    stage = tracks / f'.{TRACK_ID}.stage-{uuid.uuid4().hex}'
    try:
        shutil.copytree(PACKAGE, stage, symlinks=False)
        for f in files:
            require(sha(stage / f['path']) == f['sha256'], 'staged hash differs: ' + f['path'])
        os.rename(stage, dest)
        stage = None
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', nargs='?', default='forward', choices=('forward', 'reverse'))
    ap.add_argument('--install', action='store_true')
    args = ap.parse_args()
    print(json.dumps(install(commit=args.install), indent=2))


if __name__ == '__main__':
    main()
