"""NumPy-only, offline geometry for the provisional northern hairpin scene.

No GIS transforms, measured width inference, Blender imports, or source writes.
"""
import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def smooth_samples(raw, spacing=1.0, xy_sigma=2.0, z_sigma=3.0):
    """Uniform native arclength samples, Gaussian smoothing, linear end extension.

    Return original-arclength parameters, unsmoothed samples and designed samples.
    Pin endpoints exactly; all offsets remain available to the consumer.
    """
    raw = np.asarray(raw, dtype=float)
    steps = np.linalg.norm(np.diff(raw[:, :2], axis=0), axis=1)
    require(np.isfinite(raw).all() and (steps > 1e-8).all(), "Invalid/repeated route")
    source_s = np.r_[0.0, np.cumsum(steps)]
    s = np.linspace(0, source_s[-1], int(np.ceil(source_s[-1] / spacing)) + 1)
    original = np.column_stack([np.interp(s, source_s, raw[:, k]) for k in range(3)])
    designed = original.copy()
    for k, sigma in enumerate((xy_sigma, xy_sigma, z_sigma)):
        if sigma <= 0:
            continue
        radius = int(np.ceil(3 * sigma / (s[1] - s[0])))
        t = np.arange(-radius, radius + 1) * (s[1] - s[0])
        kernel = np.exp(-0.5 * (t / sigma) ** 2)
        kernel /= kernel.sum()
        y = original[:, k]
        padded = np.r_[y[0] + np.arange(-radius, 0) * (y[1] - y[0]),
                       y, y[-1] + np.arange(1, radius + 1) * (y[-1] - y[-2])]
        designed[:, k] = np.convolve(padded, kernel, mode="valid")
        designed[[0, -1], k] = original[[0, -1], k]
    return source_s, s, original, designed


def station_normals(points):
    tangent = np.gradient(points[:, :2], axis=0)
    lengths = np.linalg.norm(tangent, axis=1)
    require((lengths > 1e-8).all(), "Undefined tangent")
    tangent /= lengths[:, None]
    return np.column_stack([-tangent[:, 1], tangent[:, 0]])


def ribbon(points, offsets):
    """Left-positive lateral offsets. Every face explicitly triangulated upward."""
    points = np.asarray(points)
    offsets = np.asarray(offsets)
    require(np.all(np.diff(offsets) > 0), "Offsets must increase")
    xyz = np.repeat(points[:, None, :], len(offsets), axis=1)
    xyz[:, :, :2] += station_normals(points)[:, None, :] * offsets[None, :, None]
    n = len(offsets)
    i = np.arange(len(points) - 1)[:, None] * n + np.arange(n - 1)
    a, b, c, d = i.ravel(), (i + n).ravel(), (i + n + 1).ravel(), (i + 1).ravel()
    faces = np.stack([np.stack([a, b, c], axis=1), np.stack([a, c, d], axis=1)], axis=1)
    return xyz.reshape(-1, 3), faces.reshape(-1, 3)


def mesh_checks(vertices, faces):
    tri = np.asarray(vertices)[np.asarray(faces)]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cross, axis=1) * 0.5
    return {"vertices": len(vertices), "triangles": len(faces),
            "degenerate_triangles": int(np.count_nonzero(area <= 1e-9)),
            "non_upward_triangles": int(np.count_nonzero(cross[:, 2] <= 1e-9)),
            "min_triangle_area_m2": float(area.min()),
            "bounds_m": [np.min(vertices, axis=0).tolist(), np.max(vertices, axis=0).tolist()]}


def valid_terrain_faces(valid, cells):
    require(valid.dtype == np.bool_ and cells.dtype == np.bool_, "Masks must be bool")
    expected = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:] & valid[1:, 1:]
    require(np.array_equal(cells, expected), "Cell mask disagrees with vertex mask")
    r, c = np.nonzero(cells)
    a = r * valid.shape[1] + c
    b, d = a + 1, a + valid.shape[1]
    return np.stack([np.stack([a, b, d + 1], axis=1),
                     np.stack([a, d + 1, d], axis=1)], axis=1).reshape(-1, 3)


def ribbon_overlap(points, half_width=3.75):
    """Strict interior SAT overlap of non-neighbour full-width segment quads.

    Touching shared boundaries are not overlap. Convexity/folds are independently
    checked by positive triangle orientation; this test assumes that check passed.
    """
    v, _ = ribbon(points, [-half_width, half_width])
    edges = v.reshape(-1, 2, 3)[:, :, :2]
    quads = np.stack([edges[:-1, 0], edges[1:, 0], edges[1:, 1], edges[:-1, 1]], axis=1)
    lo, hi = quads.min(axis=1), quads.max(axis=1)
    pairs = []
    for i, q in enumerate(quads):
        candidates = np.flatnonzero(np.all(lo < hi[i] - 1e-8, axis=1) &
                                    np.all(hi > lo[i] + 1e-8, axis=1))
        for j in candidates[candidates > i + 1]:
            other = quads[j]
            edges2 = np.concatenate([np.roll(q, -1, axis=0) - q,
                                     np.roll(other, -1, axis=0) - other])
            axes = np.column_stack([-edges2[:, 1], edges2[:, 0]])
            axes /= np.linalg.norm(axes, axis=1)[:, None]
            a, b = q @ axes.T, other @ axes.T
            if np.all(np.minimum(a.max(0), b.max(0)) - np.maximum(a.min(0), b.min(0)) > 1e-8):
                pairs.append([int(i), int(j)])
    return pairs


def lower_terrain(x, y, z, valid_cells, points, half_width=3.75, clearance=0.25):
    """Lower every corner of cells with AABB overlap with the shoulder ribbon.

    Conservative superset of true intersections guarantees no terrain triangle
    pierces any road/shoulder triangle. End caps are covered too. No raising,
    no interpolation over masks, no modification of the original terrain array.
    """
    output = z.copy()
    v, _ = ribbon(points, [-half_width, half_width])
    edge = v.reshape(-1, 2, 3)
    cells_touched = np.zeros(valid_cells.shape, dtype=bool)
    for i in range(len(points) - 1):
        quad = edge[i:i + 2].reshape(-1, 3)
        lo, hi = quad[:, :2].min(0), quad[:, :2].max(0)
        cols = np.flatnonzero((x[0, :-1] <= hi[0]) & (x[0, 1:] >= lo[0]))
        rows = np.flatnonzero((y[:-1, 0] <= hi[1]) & (y[1:, 0] >= lo[1]))
        cap = float(quad[:, 2].min() - clearance)
        for row in rows:
            for col in cols:
                if not valid_cells[row, col]:
                    continue
                cells_touched[row, col] = True
                output[row:row + 2, col:col + 2] = np.minimum(output[row:row + 2, col:col + 2], cap)
    return output, cells_touched


def terrain_clearance(x, y, z, cells, points, half_width=3.75):
    """Conservative cell-corner clearance lower bound under each segment AABB."""
    v, _ = ribbon(points, [-half_width, half_width])
    edge = v.reshape(-1, 2, 3)
    minimum = float("inf")
    for i in range(len(points) - 1):
        quad = edge[i:i + 2].reshape(-1, 3)
        lo, hi = quad[:, :2].min(0), quad[:, :2].max(0)
        cols = np.flatnonzero((x[0, :-1] <= hi[0]) & (x[0, 1:] >= lo[0]))
        rows = np.flatnonzero((y[:-1, 0] <= hi[1]) & (y[1:, 0] >= lo[1]))
        for row in rows:
            for col in cols:
                if cells[row, col]:
                    minimum = min(minimum, float(quad[:, 2].min() - z[row:row+2, col:col+2].max()))
    return minimum


def profile_stats(points):
    ds = np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1)
    grade = np.diff(points[:, 2]) / ds
    tangent = np.diff(points[:, :2], axis=0) / ds[:, None]
    turns = np.degrees(np.arccos(np.clip(np.sum(tangent[1:] * tangent[:-1], axis=1), -1, 1)))
    return {"length_xy_m": float(ds.sum()),
            "length_3d_m": float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()),
            "height_local_min_max_m": [float(points[:, 2].min()), float(points[:, 2].max())],
            "grade_min_max_percent": [float(grade.min() * 100), float(grade.max() * 100)],
            "max_grade_step_percentage_points": float(np.abs(np.diff(grade)).max() * 100),
            "max_heading_step_deg": float(turns.max())}
