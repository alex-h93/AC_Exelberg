"""v004 procedural tree meshes (numpy only; usable in .venv and in Blender).

tree(species, height, crown, seed) -> dict(v, n, uv, tri, mat) in tree-local metres
(origin at trunk base, +Z up). mat: 0 = foliage atlas, 1 = bark atlas.
UVs are Blender convention (v up). Foliage atlas: 4x4 cells, row = species
(beech, oak, conifer, shrub) from the image top; bark atlas: 4 vertical strips.
Leaf cards are double-sided by index order only (shared vertices, outward
"crown-sphere" normals so both faces light softly). Not botanical models.
"""
import math
import numpy as np

SPECIES = ('beech', 'oak', 'conifer', 'shrub')


def _rot(axis, ang):
    axis = axis / np.linalg.norm(axis)
    a = math.cos(ang / 2); b, c, d = -axis * math.sin(ang / 2)
    return np.array([[a*a+b*b-c*c-d*d, 2*(b*c+a*d), 2*(b*d-a*c)],
                     [2*(b*c-a*d), a*a+c*c-b*b-d*d, 2*(c*d+a*b)],
                     [2*(b*d+a*c), 2*(c*d-a*b), a*a+d*d-b*b-c*c]])


class _Mesh:
    def __init__(self):
        self.v, self.n, self.uv, self.tri, self.mat = [], [], [], [], []
        self.count = 0

    def add(self, v, n, uv, tri, mat):
        tri = np.asarray(tri) + self.count
        self.v.append(np.asarray(v, float)); self.n.append(np.asarray(n, float)); self.uv.append(np.asarray(uv, float))
        self.tri.append(tri); self.mat.append(np.full(len(tri), mat, np.int8)); self.count += len(v)

    def result(self):
        n = np.concatenate(self.n); n /= np.linalg.norm(n, axis=1, keepdims=True)
        return dict(v=np.concatenate(self.v).astype(np.float32), n=n.astype(np.float32),
                    uv=np.concatenate(self.uv).astype(np.float32), tri=np.concatenate(self.tri).astype(np.int32),
                    mat=np.concatenate(self.mat))


def _tube(m, p0, p1, r0, r1, sides, strip, segs=1, u_scale=1.0):
    axis = p1 - p0; L = np.linalg.norm(axis); axis = axis / L
    ref = np.array([1.0, 0, 0]) if abs(axis[0]) < .9 else np.array([0, 1.0, 0])
    a = np.cross(axis, ref); a /= np.linalg.norm(a); b = np.cross(axis, a)
    u0, u1 = strip * .25 + .01, strip * .25 + .24
    v, n, uv = [], [], []
    for s in range(segs + 1):
        t = s / segs; c = p0 + axis * L * t; r = r0 + (r1 - r0) * t
        for k in range(sides + 1):
            ang = 2 * math.pi * k / sides; d = a * math.cos(ang) + b * math.sin(ang)
            v.append(c + d * r); n.append(d); uv.append((u0 + (u1 - u0) * k / sides, L * t / (2.5 * u_scale)))
    tri = []
    for s in range(segs):
        for k in range(sides):
            i = s * (sides + 1) + k; j = i + sides + 1
            tri += [(i, i + 1, j + 1), (i, j + 1, j)]
    m.add(v, n, uv, tri, 1)


def _card(m, base, up, side, size, center, row, col, normal_bias=None):
    """Quad whose bottom-centre sits at base, extending along up; double-sided."""
    w = side * size * .5; h = up * size
    pts = np.array([base - w, base + w, base + w + h, base - w + h])
    cu0, cu1 = col / 4 + .004, (col + 1) / 4 - .004
    cv0, cv1 = 1 - (row + 1) / 4 + .004, 1 - row / 4 - .004
    uv = [(cu0, cv0), (cu1, cv0), (cu1, cv1), (cu0, cv1)]
    nrm = pts - center
    nrm[:, 2] *= 0.6
    nrm = nrm / np.linalg.norm(nrm, axis=1, keepdims=True) + np.array([0, 0, .35])
    if normal_bias is not None:
        nrm = nrm + normal_bias
    m.add(pts, nrm, uv, [(0, 1, 2), (0, 2, 3), (0, 2, 1), (0, 3, 2)], 0)


def tree(species, height, crown, seed, detail=1.0):
    rng = np.random.default_rng(int(seed))
    sp = SPECIES.index(species) if isinstance(species, str) else int(species)
    m = _Mesh(); H = float(height); R = float(crown)
    if sp == 3:  # shrub: short stems + low dome of cards
        for _ in range(2):
            top = np.array([rng.normal(0, R * .2), rng.normal(0, R * .2), H * .35])
            _tube(m, np.zeros(3), top, .05, .02, 4, 3)
        center = np.array([0, 0, H * .45])
        n = max(6, int(12 * detail))
        for i in range(n):
            d = rng.normal(size=3); d[2] = abs(d[2]) * .6 + .1; d /= np.linalg.norm(d)
            pos = center + d * np.array([R, R, H * .35]) * rng.uniform(.1, .6)
            pos[2] = max(pos[2], H * .05)
            up = d * .5 + np.array([0, 0, 1.0]); up /= np.linalg.norm(up)
            out = np.array([d[0], d[1], 0]) + rng.normal(0, .3, 3); out -= up * np.dot(out, up); out /= np.linalg.norm(out)
            side = np.cross(up, out); side /= np.linalg.norm(side)
            sz = max(H * .9, R * rng.uniform(1.0, 1.4))
            _card(m, pos - up * sz * .35, up, side, sz, center, 3, rng.integers(4))
        return m.result()
    r0 = max(.12, .011 * H + .06)
    if sp == 2:  # conifer: straight trunk, dense whorls of drooping, steeply rolled cards
        _tube(m, np.zeros(3), np.array([0, 0, H]), r0, .03, 6, 2, segs=3)
        whorls = max(5, int(13 * detail)); start = H * .22
        for w in range(whorls):
            t = w / (whorls - 1); z = start + (H - start) * t; rad = R * (1 - t) ** 0.85 + .35
            per = max(3, int(round(6 * (1 - t * .5))))
            for k in range(per):
                ang = 2 * math.pi * (k + rng.random() * .5) / per + w * 1.3
                out = np.array([math.cos(ang), math.sin(ang), -.3 + .2 * t]); out /= np.linalg.norm(out)
                side = np.cross(out, [0, 0, 1.0]); side /= np.linalg.norm(side)
                side = _rot(out, rng.choice([-1, 1]) * rng.uniform(.7, 1.3)) @ side
                base = np.array([0, 0, z]) + out * .05
                _card(m, base, out, side, max(.9, rad * 1.2), np.array([0, 0, z]), 2, rng.integers(4), normal_bias=np.array([0, 0, .4]))
        return m.result()
    # broadleaf (beech / oak): crown down to ~45 % of height so edge trees read from the road
    rz = H * (.42 if sp == 0 else .38)
    center_z = max(H - rz, H * .45)
    lean = rng.normal(0, .015 * H, 2)
    center = np.array([lean[0], lean[1], center_z])
    top = np.array([lean[0], lean[1], center_z + .25 * rz])
    _tube(m, np.zeros(3), top, r0, r0 * .5, 7, sp, segs=2)
    for k in range(4):
        ang = 2 * math.pi * (k + rng.random() * .6) / 4
        p0 = np.array([lean[0], lean[1], center_z + rng.uniform(-.35, .1) * rz])
        d = np.array([math.cos(ang), math.sin(ang), rng.uniform(.4, .9) if sp == 0 else rng.uniform(.15, .45)])
        _tube(m, p0, p0 + d / np.linalg.norm(d) * R * .45, r0 * .4, r0 * .12, 4, sp)
    n = max(10, int((36 if sp == 0 else 34) * detail))
    size = float(np.clip(.5 * R + 1.3, 1.6, 4.6))
    for i in range(n):
        d = rng.normal(size=3); d /= np.linalg.norm(d)
        pos = center + d * np.array([R, R, rz]) * rng.uniform(.35, .92)
        out = np.array([d[0], d[1], d[2] * .35]) + rng.normal(0, .25, 3); out /= np.linalg.norm(out)
        tilt = rng.uniform(.25, .8)
        up = np.array([0, 0, 1.0]) * math.cos(tilt) + np.array([d[0], d[1], 0]) * math.sin(tilt)
        up -= out * np.dot(up, out); up /= np.linalg.norm(up)
        side = np.cross(up, out); side /= np.linalg.norm(side)
        sz = size * rng.uniform(.85, 1.2)
        _card(m, pos - up * sz * .5, up, side, sz, center, sp, rng.integers(4))
    return m.result()
