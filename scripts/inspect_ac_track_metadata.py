#!/usr/bin/env python3
"""Read-only, bounded KN5 v5/v6 metadata survey; never extracts asset payloads."""
import argparse
from collections import Counter
import configparser
import json
import math
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = [float(i // 4 == i % 4) for i in range(16)]
PIVOT = re.compile(r'^AC_(?:PIT_0|START_0|HOTLAP_START_0|TIME_\d+_[LR])$')


class InvalidMetadata(ValueError):
    pass


class Budget:
    def __init__(self, maximum=20_000_000):
        self.maximum = maximum
        self.used = 0

    def charge(self, size):
        if size < 0 or self.used + size > self.maximum:
            raise InvalidMetadata('actual-read byte budget exceeded')
        self.used += size


class Reader:
    def __init__(self, stream, budget):
        self.stream, self.budget = stream, budget
        here = stream.tell()
        self.size = stream.seek(0, 2)
        stream.seek(here)
        self.skipped = 0

    def check(self, size):
        if size < 0 or self.stream.tell() + size > self.size:
            raise InvalidMetadata('range exceeds EOF')

    def take(self, size):
        self.check(size)
        self.budget.charge(size)
        data = self.stream.read(size)
        if len(data) != size:
            raise InvalidMetadata('short read')
        return data

    def skip(self, size):
        self.check(size)
        self.stream.seek(size, 1)
        self.skipped += size

    def number(self, fmt='I'):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def count(self, maximum=1_000_000, stride=1):
        value = self.number()
        if value > maximum:
            raise InvalidMetadata('count limit exceeded')
        self.check(value * stride)
        return value

    def flag(self, fmt='B'):
        value = self.number(fmt)
        if value not in (0, 1):
            raise InvalidMetadata('invalid boolean')
        return value

    def string(self):
        data = self.take(self.count(4096))
        try:
            result = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise InvalidMetadata('invalid string') from exc
        if '\0' in result:
            raise InvalidMetadata('NUL string')
        return result

    def floats(self, count):
        result = list(struct.unpack('<' + 'f' * count, self.take(4 * count)))
        if not all(math.isfinite(x) for x in result):
            raise InvalidMetadata('nonfinite metadata')
        return result


def multiply(a, b):
    """Row-vector matrices: local * parent; translation in indices 12..14."""
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
            for r in range(4) for c in range(4)]


def inspect_kn5(stream, budget=None):
    budget = budget or Budget()
    before = budget.used
    r = Reader(stream, budget)
    if r.take(6) != b'sc6969':
        raise InvalidMetadata('bad KN5 magic')
    version = r.number()
    if version not in (5, 6):
        raise InvalidMetadata('only KN5 v5/v6 accepted')
    extra = r.number() if version == 6 else None
    textures = r.count(100_000, 12)
    texture_bytes = 0
    for _ in range(textures):
        r.flag('I')
        r.string()
        size = r.count(1_000_000_000)
        r.skip(size)
        texture_bytes += size
    materials = r.count(100_000, 18)
    for _ in range(materials):
        r.string(), r.string()
        blend, alpha, depth = r.number('B'), r.flag(), r.number()
        if blend > 2 or depth > 2:
            raise InvalidMetadata('material enum')
        for _ in range(r.count(1024, 44)):
            r.string()
            r.skip(40)
        for _ in range(r.count(1024, 12)):
            r.string(), r.number(), r.string()
    kinds, lods, flags, refs, surfaces = (Counter() for _ in range(5))
    pivots, samples, surface_samples = [], [], []
    zero_lod_flags = Counter()
    vertices = indices = nodes = 0
    # Iterative preorder traversal avoids recursion limits and retains only ancestors.
    stack = [(1, IDENTITY, 0)]
    while stack:
        remaining, parent, depth = stack.pop()
        if remaining > 1:
            stack.append((remaining - 1, parent, depth))
        nodes += 1
        if nodes > 1_000_000 or depth > 256:
            raise InvalidMetadata('node/depth budget')
        kind, name = r.number(), r.string()
        children, active = r.count(1_000_000, 13), r.flag()
        kinds[str(kind)] += 1
        world = parent
        if kind == 1:
            world = multiply(r.floats(16), parent)
        elif kind in (2, 3):
            cast, visible, transparent = r.flag(), r.flag(), r.flag()
            if kind == 3:
                for _ in range(r.count(100_000, 68)):
                    r.string()
                    r.skip(64)
            vc = r.count(10_000_000, 44 if kind == 2 else 76)
            r.skip(vc * (44 if kind == 2 else 76))
            ic = r.count(100_000_000, 2)
            r.skip(ic * 2)
            material, layer = r.number(), r.number()
            if material >= materials:
                raise InvalidMetadata('material reference out of range')
            lod = r.floats(2)
            renderable = None
            if kind == 2:
                sphere = r.floats(4)
                if sphere[3] < 0:
                    raise InvalidMetadata('negative sphere radius')
                renderable = r.flag()
            vertices += vc
            indices += ic
            lods[tuple(lod)] += 1
            if lod == [0.0, 0.0]:
                zero_lod_flags[(active, visible, renderable)] += 1
            flags[(active, cast, visible, transparent, renderable)] += 1
            refs[str(material)] += 1
            # Only aggregate surface tokens, not a scene/geometry inventory.
            match = re.match(r'^\d+([A-Za-z]+(?:-[A-Za-z]+)*)', name)
            if match:
                surfaces[match[1].upper()] += 1
                if surfaces[match[1].upper()] <= 2 and len(surface_samples) < 16:
                    surface_samples.append(dict(name=name, lod=lod, active=active,
                                                visible=visible, renderable=renderable))
            if len(samples) < 6:
                samples.append(dict(name=name, kind=kind, vertices=vc, indices=ic,
                                    material=material, layer=layer, lod=lod))
        else:
            raise InvalidMetadata(f'unknown node kind {kind} at {r.stream.tell()}')
        if PIVOT.fullmatch(name):
            if len(pivots) >= 64:
                raise InvalidMetadata('pivot output budget')
            pivots.append(dict(name=name, kind=kind, active=active, world_matrix=world,
                               x_axis=world[0:3], y_axis=world[4:7], z_axis=world[8:11],
                               position=world[12:15]))
        if children:
            stack.append((children, world, depth + 1))
    if stream.tell() != r.size:
        raise InvalidMetadata('trailing bytes')
    return dict(version=version, extra=extra, file_bytes=r.size,
                actual_bytes_read=budget.used - before, bytes_skipped=r.skipped,
                textures=textures, texture_payload_bytes_skipped=texture_bytes,
                materials=materials, nodes=nodes, node_kinds=dict(kinds),
                vertices_skipped=vertices, indices_skipped=indices,
                lod_distribution=[dict(lod_in=k[0], lod_out=k[1], meshes=v)
                                  for k, v in sorted(lods.items())],
                flag_distribution=[dict(active=k[0], cast_shadows=k[1], visible=k[2],
                                        transparent=k[3], renderable=k[4], meshes=v)
                                   for k, v in flags.items()],
                material_reference_counts=dict(refs), surface_tokens=dict(surfaces),
                zero_lod_flags=[dict(active=k[0], visible=k[1], renderable=k[2], meshes=v)
                                for k, v in zero_lod_flags.items()],
                mesh_samples=samples, surface_samples=surface_samples, pivots=pivots)


def inspect_track(track, budget):
    inventory = {str(p.relative_to(track)): p.stat().st_size
                 for p in sorted(track.rglob('*')) if p.is_file()}
    selected = ['ui/ui_track.json', 'models.ini', 'data/surfaces.ini',
                'data/semaphore.ini', 'data/startinglights.ini']
    configs = {}
    for relative in selected:
        path = track / relative
        if not path.exists():
            continue
        size = path.stat().st_size
        if size > 65536:
            raise InvalidMetadata('config size budget')
        budget.charge(size)
        with path.open('rb', buffering=0) as stream:
            text = stream.read(size).decode('utf-8-sig')
        if path.suffix == '.json':
            values = json.loads(text)
            configs[relative] = {k: values[k] for k in
                                 ('name', 'length', 'pitboxes', 'run', 'tags') if k in values}
        else:
            parser = configparser.ConfigParser(strict=False, interpolation=None,
                                                inline_comment_prefixes=(';', '//'))
            parser.read_string(text)
            configs[relative] = {s: dict(parser[s]) for s in parser.sections()}
    with (track / (track.name + '.kn5')).open('rb', buffering=0) as stream:
        metadata = inspect_kn5(stream, budget)
    return dict(track=track.name, inventory=inventory, configs=configs, kn5=metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/processed/ac_reference_metadata/stock_tracks.json')
    args = parser.parse_args()
    # Fixed selection: two source KN5 files, no arbitrary recursive asset reads.
    budget = Budget()
    result = dict(source_root=str(args.game), runtime_verified=False,
                  tracks=[inspect_track(args.game / 'content/tracks' / name, budget)
                          for name in ('trento-bondone', 'drift')])
    result['total_actual_bytes_read_including_configs'] = budget.used
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'{args.output}: {budget.used} bytes read; two KN5 files, no payload extraction')


if __name__ == '__main__':
    main()
