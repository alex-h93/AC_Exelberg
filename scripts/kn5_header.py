"""KN5 v5 header rewrite: textures + materials only; the node section (geometry, physics names, transforms) is copied
byte-for-byte. Used by v014 to change shaders/textures without touching meshes.

read(data) -> dict(version, textures=[dict(active, name, data)], materials=[dict(name, shader, blend, alpha, depth,
                   props=[(name, 10 floats)], bindings=[(slot, unit, texture)])], node_offset)
write(header, node_bytes) -> bytes      (round trip is exact: write(read(d), d[read(d)['node_offset']:]) == d)
"""
import struct


class _R:
    def __init__(self, d):
        self.d, self.p = memoryview(d), 0

    def take(self, n):
        v = self.d[self.p:self.p + n]
        assert len(v) == n, 'truncated KN5'
        self.p += n
        return bytes(v)

    def i(self):
        return struct.unpack('<i', self.take(4))[0]

    def b(self):
        return self.take(1)[0]

    def s(self):
        n = self.i()
        assert 0 <= n < 4096
        return self.take(n).decode('utf-8')


def read(data):
    r = _R(data)
    assert r.take(6) == b'sc6969'
    version = r.i()
    assert version == 5, 'only KN5 v5'
    textures = []
    for _ in range(r.i()):
        active = r.i()
        name = r.s()
        textures.append(dict(active=active, name=name, data=r.take(r.i())))
    materials = []
    for _ in range(r.i()):
        m = dict(name=r.s(), shader=r.s(), blend=r.b(), alpha=r.b(), depth=r.i())
        m['props'] = [(r.s(), struct.unpack('<10f', r.take(40))) for _ in range(r.i())]
        m['bindings'] = [(r.s(), r.i(), r.s()) for _ in range(r.i())]
        materials.append(m)
    return dict(version=version, textures=textures, materials=materials, node_offset=r.p)


def _s(x):
    b = x.encode('utf-8')
    return struct.pack('<i', len(b)) + b


def write(h, node_bytes):
    out = [b'sc6969', struct.pack('<i', h['version']), struct.pack('<i', len(h['textures']))]
    for t in h['textures']:
        out += [struct.pack('<i', t['active']), _s(t['name']), struct.pack('<i', len(t['data'])), t['data']]
    out.append(struct.pack('<i', len(h['materials'])))
    for m in h['materials']:
        out += [_s(m['name']), _s(m['shader']), bytes([m['blend'], m['alpha']]), struct.pack('<i', m['depth']),
                struct.pack('<i', len(m['props']))]
        for n, v in m['props']:
            out += [_s(n), struct.pack('<10f', *v)]
        out.append(struct.pack('<i', len(m['bindings'])))
        for slot, unit, tex in m['bindings']:
            out += [_s(slot), struct.pack('<i', unit), _s(tex)]
    return b''.join(out) + bytes(node_bytes)


def prop(value):
    return (float(value),) + (0.0,) * 9


def texture(name, data):
    return dict(active=1, name=name, data=data)
