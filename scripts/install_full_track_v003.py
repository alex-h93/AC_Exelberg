#!/usr/bin/env python3
"""Strict isolated v003 installer; dry-run unless --install is explicit.

Frozen v003 profile; only stateless descriptor-relative primitives are shared.
Never mutate v001/v002 installer module globals to select another track.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid

# Only stateless, descriptor-relative safety primitives are shared with v001.
from install_ac_test import DIR_FLAGS, GAME, directory_at, rename_new, require, safe_name

ROOT = Path(__file__).resolve().parents[1]
TRACK_ID = 'exelberg_full_v003'
PACKAGE = ROOT / 'build/full_track_v003' / TRACK_ID
MANIFEST = ROOT / 'data/processed/full_track_package_v003/manifest.json'
DDS = (tuple('v002_' + n + '.dds' for n in ('asphalt', 'gravel', 'bark', 'canopy', 'white'))
       + ('v003_post_black.dds', 'v003_reflector.dds')
       + tuple(f'v003_ortho_{i:03d}.dds' for i in
               (4,5,6,7,8,12,13,14,15,19,20,21,22,23,28,29,30,31,36,37,38,45,46,47,54,55)))
ALLOWLIST = frozenset({TRACK_ID + '.kn5', *(f'texture/{n}' for n in DDS),
    'models.ini', 'data/surfaces.ini', 'data/map.ini', 'data/lighting.ini',
    'ui/ui_track.json', 'ui/preview.png', 'ui/outline.png', 'map.png',
    'ai/fast_lane.ai', 'ai/pit_lane.ai', 'README.txt', 'ATTRIBUTION.txt'})
FILE_CAP = 512_000_000
TOTAL_CAP = 600_000_000


def open_file(fd, name):
    safe_name(name)
    parent = directory_at(fd, name.split('/')[:-1])
    try:
        child = os.open(name.split('/')[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(child)
        if not stat.S_ISREG(info.st_mode) or info.st_size > FILE_CAP:
            os.close(child)
            raise ValueError('Nonregular/oversized source')
        return os.fdopen(child, 'rb')
    finally:
        os.close(parent)


def transfer(source, destination=None, cap=FILE_CAP):
    digest = hashlib.sha256()
    count = 0
    while chunk := source.read(min(1024 * 1024, cap - count + 1)):
        count += len(chunk)
        require(count <= cap, 'File cap exceeded')
        digest.update(chunk)
        if destination is not None:
            destination.write(chunk)
    return count, digest.hexdigest()


def snapshot(package, manifest, spool):
    manifest = Path(manifest).absolute()
    require(manifest.resolve() == manifest, 'Unsafe manifest path')
    parent = os.open(manifest.parent, DIR_FLAGS)
    try:
        with open_file(parent, manifest.name) as stream:
            raw = stream.read(2_000_001)
        require(len(raw) <= 2_000_000, 'Oversized manifest')
        meta = json.loads(raw)
    finally:
        os.close(parent)
    require(meta['schema'] == 'full_track_package_v003' and meta['track_id'] == TRACK_ID, 'Wrong identity')
    records = meta['files']
    names = [safe_name(r['path']) for r in records]
    require(len(names) == len(set(names)) and set(names) == ALLOWLIST, 'Manifest allowlist differs')
    require(all(type(r['bytes']) is int and 0 <= r['bytes'] <= FILE_CAP for r in records), 'File cap')
    total = sum(r['bytes'] for r in records)
    require(total <= TOTAL_CAP and meta['bytes'] == total and meta['file_count'] == len(names), 'Totals/cap')
    package = Path(package).absolute()
    require(package.resolve() == package, 'Symlink source root/ancestor')
    actual = set()
    allowed_dirs = {n.split('/')[0] for n in names if '/' in n}
    for parent, dirs, files in os.walk(package, followlinks=False):
        for n in dirs + files:
            p = Path(parent) / n
            require(not p.is_symlink(), 'Symlink source')
        require(all((Path(parent) / n).relative_to(package).as_posix() in allowed_dirs for n in dirs),
                'Unexpected source directory')
        actual.update((Path(parent) / n).relative_to(package).as_posix() for n in files)
    require(actual == ALLOWLIST, 'Source inventory differs')
    fd = os.open(package, DIR_FLAGS)
    try:
        for r in records:
            with open_file(fd, r['path']) as source:
                count, digest = transfer(source, spool, cap=r['bytes'])
            require((count, digest) == (r['bytes'], r['sha256']), 'Source hash/size: ' + r['path'])
    finally:
        os.close(fd)
    spool.seek(0)
    return meta


def validate_source(package=PACKAGE, manifest=MANIFEST):
    with tempfile.TemporaryFile() as spool:
        return snapshot(package, manifest, spool)


def install(package=PACKAGE, manifest=MANIFEST, game=GAME, *, commit=False):
    with tempfile.TemporaryFile() as spool:
        meta = snapshot(package, manifest, spool)  # Immutable verified snapshot before game writes.
        game = Path(game).resolve(strict=True)  # Steam root alias allowed; children never followed.
        root = os.open(game, DIR_FLAGS)
        try:
            tracks = directory_at(root, ['content', 'tracks'])
        finally:
            os.close(root)
        stage = None
        identity = None
        try:
            try:
                os.stat(TRACK_ID, dir_fd=tracks, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError('Destination exists: ' + TRACK_ID)
            result = dict(mode='INSTALL' if commit else 'DRY_RUN',
                destination=str(game / 'content/tracks' / TRACK_ID), destination_absent=True,
                file_count=meta['file_count'], bytes=meta['bytes'])
            if not commit:
                return result
            stage = '.' + TRACK_ID + '.stage-' + uuid.uuid4().hex
            os.mkdir(stage, mode=0o700, dir_fd=tracks)
            info = os.stat(stage, dir_fd=tracks, follow_symlinks=False)
            identity = (info.st_dev, info.st_ino)
            fd = os.open(stage, DIR_FLAGS, dir_fd=tracks)
            try:
                info = os.fstat(fd)
                require(identity == (info.st_dev, info.st_ino), 'Stage substituted')
                for directory in sorted({n.split('/')[0] for n in ALLOWLIST if '/' in n}):
                    os.mkdir(directory, dir_fd=fd)
                for r in meta['files']:
                    parent = directory_at(fd, r['path'].split('/')[:-1])
                    try:
                        child = os.open(r['path'].split('/')[-1],
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
                        with os.fdopen(child, 'wb') as target:
                            remaining = r['bytes']
                            while remaining:
                                chunk = spool.read(min(1024 * 1024, remaining))
                                require(bool(chunk), 'Truncated snapshot')
                                target.write(chunk)
                                remaining -= len(chunk)
                            target.flush()
                            os.fsync(target.fileno())
                    finally:
                        os.close(parent)
                    with open_file(fd, r['path']) as source:
                        require(transfer(source) == (r['bytes'], r['sha256']), 'Stage hash differs')
                os.fsync(fd)
                info = os.stat(stage, dir_fd=tracks, follow_symlinks=False)
                require(identity == (info.st_dev, info.st_ino), 'Stage substituted')
                rename_new(tracks, stage, TRACK_ID)
                stage = None
                os.fsync(tracks)
            finally:
                os.close(fd)
            return result
        finally:
            try:
                if stage is not None:
                    info = os.stat(stage, dir_fd=tracks, follow_symlinks=False)
                    require(identity == (info.st_dev, info.st_ino), 'Stage substituted; no cleanup')
                    shutil.rmtree(stage, dir_fd=tracks)
            finally:
                os.close(tracks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.package, args.manifest, args.game, commit=args.install), indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'REFUSED: {exc}\n')


if __name__ == '__main__':
    main()
