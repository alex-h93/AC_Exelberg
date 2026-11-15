#!/usr/bin/env python3
"""Strict, dry-run-by-default installer for the isolated v001 package."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]
TRACK_ID = 'exelberg_north_proto_v001'
GAME = Path('/var/home/haze/.local/share/Steam/steamapps/common/assettocorsa')
PACKAGE = ROOT / 'build/ac_test_v001' / TRACK_ID
MANIFEST = ROOT / 'data/processed/ac_package/manifest.json'
ALLOWLIST = frozenset({
    TRACK_ID + '.kn5', 'texture/kn5_asphalt.dds', 'texture/kn5_gravel.dds',
    'texture/kn5_terrain.dds', 'models.ini', 'data/surfaces.ini', 'data/map.ini',
    'data/lighting.ini', 'ui/ui_track.json', 'ui/preview.png', 'ui/outline.png',
    'map.png', 'ai/fast_lane.ai', 'ai/pit_lane.ai', 'README.txt', 'ATTRIBUTION.txt',
})
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe_name(name):
    require(isinstance(name, str) and '\\' not in name and
            not PurePosixPath(name).is_absolute() and
            all(p not in ('', '.', '..') for p in name.split('/')), 'Unsafe relative path')
    return name


def directory_at(fd, parts):
    """Open child directories without following any child symlink."""
    current = os.dup(fd)
    try:
        for part in parts:
            new = os.open(part, DIR_FLAGS, dir_fd=current)
            os.close(current)
            current = new
        return current
    except BaseException:
        os.close(current)
        raise


def read_at(fd, name):
    safe_name(name)
    parent = directory_at(fd, name.split('/')[:-1])
    try:
        f = os.open(name.split('/')[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(f, 'rb') as stream:
            import stat
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Not regular file')
            return stream.read()
    finally:
        os.close(parent)


def validate_source(package=PACKAGE, manifest=MANIFEST):
    meta = json.loads(Path(manifest).read_text())
    require(meta['track_id'] == TRACK_ID and meta['schema'] == 'ac_test_package_v1', 'Wrong package identity')
    records = meta['files']
    names = [safe_name(r['path']) for r in records]
    require(len(names) == len(set(names)) and set(names) == ALLOWLIST, 'Manifest allowlist differs')
    package = Path(package).absolute()
    # Unlike the game root, the package root and its ancestors may not be symlinks.
    require(package.resolve() == package, 'Symlink package root/ancestor')
    actual = set()
    for parent, dirs, files in os.walk(package, followlinks=False):
        for name in dirs + files:
            p = Path(parent) / name
            require(not p.is_symlink(), 'Symlink in source package')
        actual.update((Path(parent) / n).relative_to(package).as_posix() for n in files)
    require(actual == ALLOWLIST, 'Source inventory differs')
    fd = os.open(package, DIR_FLAGS)
    try:
        payload = {}
        for r in records:
            data = read_at(fd, r['path'])
            require(len(data) == r['bytes'] and hashlib.sha256(data).hexdigest() == r['sha256'],
                    'Source hash/size mismatch: ' + r['path'])
            payload[r['path']] = data
    finally:
        os.close(fd)
    require(meta['file_count'] == len(payload) and meta['bytes'] == sum(map(len, payload.values())), 'Totals mismatch')
    return payload


def rename_new(fd, source, destination):
    """Linux atomic no-replace rename; never fall back to overwrite-capable rename."""
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, 'renameat2', None)
    if function is None:
        raise OSError('Atomic no-replace rename unavailable; refusing installation')
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(fd, os.fsencode(source), fd, os.fsencode(destination), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def install(package=PACKAGE, manifest=MANIFEST, game=GAME, *, commit=False):
    payload = validate_source(package, manifest)  # Fully validate before any game write.
    game = Path(game).resolve(strict=True)  # Existing Steam root symlink is explicitly permitted.
    rootfd = os.open(game, DIR_FLAGS)
    try:
        tracksfd = directory_at(rootfd, ['content', 'tracks'])
    finally:
        os.close(rootfd)
    stage = None
    stage_identity = None
    try:
        try:
            os.stat(TRACK_ID, dir_fd=tracksfd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError('Destination exists; never overwrite: ' + TRACK_ID)
        result = dict(mode='INSTALL' if commit else 'DRY_RUN', destination=str(game / 'content/tracks' / TRACK_ID),
                      destination_absent=True, file_count=len(payload), bytes=sum(map(len, payload.values())))
        if not commit:
            return result
        # mkdir is exclusive: a pre-existing stage (including symlink) is never reused.
        candidate = '.' + TRACK_ID + '.stage-' + uuid.uuid4().hex
        os.mkdir(candidate, mode=0o700, dir_fd=tracksfd)
        stage = candidate
        info = os.stat(stage, dir_fd=tracksfd, follow_symlinks=False)
        stage_identity = (info.st_dev, info.st_ino)
        stagefd = os.open(stage, DIR_FLAGS, dir_fd=tracksfd)
        try:
            info = os.fstat(stagefd)
            require(stage_identity == (info.st_dev, info.st_ino), 'Staging root changed')
            for directory in sorted({n.split('/')[0] for n in payload if '/' in n}):
                os.mkdir(directory, dir_fd=stagefd)
            for name, data in sorted(payload.items()):
                parent = directory_at(stagefd, name.split('/')[:-1])
                try:
                    f = os.open(name.split('/')[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o644, dir_fd=parent)
                    with os.fdopen(f, 'wb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                finally:
                    os.close(parent)
                require(read_at(stagefd, name) == data, 'Staged verification failed')
            os.fsync(stagefd)
            # Detect substituted stage root before publication.
            require(os.stat(stage, dir_fd=tracksfd, follow_symlinks=False).st_ino == os.fstat(stagefd).st_ino,
                    'Staging directory changed')
            rename_new(tracksfd, stage, TRACK_ID)
            stage = None
        finally:
            os.close(stagefd)
        return result
    finally:
        try:
            if stage is not None:
                # Never remove a substituted child, even during error cleanup.
                info = os.stat(stage, dir_fd=tracksfd, follow_symlinks=False)
                require(stage_identity == (info.st_dev, info.st_ino), 'Staging replaced; refusing cleanup')
                shutil.rmtree(stage, dir_fd=tracksfd)
        finally:
            os.close(tracksfd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--install', action='store_true', help='Explicitly authorize new-folder installation')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.package, args.manifest, args.game, commit=args.install), indent=2))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'REFUSED: {exc}\n')


if __name__ == '__main__':
    main()
