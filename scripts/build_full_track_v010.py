"""v010 main KN5 (= v009 + extension to the Neuwaldegg roundabout, finish at its 2nd exit), built in
factory-headless Blender from a COPY of the v009 scene (v009 blend opened read-only, never saved over).

  flatpak run --filesystem=$PWD org.blender.Blender -b --factory-startup \
      --python-exit-code 1 --python /abs/scripts/build_full_track_v010.py

Inputs (offline, .venv): data/processed/extension_v010/{route,patch,trees_v010}.npz (v010_route.py,
v010_patch_domain.py, v010_patch_cdt.py, v010_patch_build.py, v010_trees.py), exports/full_track_v010/v010_ortho_ext.dds.
Changes vs v009:
  * physics ROAD/GRAVEL/GRASS: every v009 skin triangle replaced by the patch (matched by centroid, <= 5 mm) and every
    non-top (side) face whose centroid lies in the patch area B is deleted; new objects 1ROAD_X010, 1GRAVEL_X010,
    1GRASS_X010 (new ortho material V010_ortho_ext, BEV orthophoto 1 m) added - watertight with the kept skin
  * invisible walls / markings: faces in B deleted, new 1WALL_L_X010 / 1WALL_R_X010 / 1WALL_END and VIS_PAINT_X010
  * old Marswiese warnings removed; FINISH and STOP boards (same text-mesh style) at the new finish / near the end
  * timing gates AC_TIME_0_L/R at the new finish station (+-3 m, +0.4 m, fixed axes as v002)
  * VIS_VEGETATION rebuilt from trees_v010.npz (v004 code; trees in B re-detected from the extension CHM)
  Spawns, everything before the cut (60 m before the old end) unchanged.
Writes only: blender/exelberg_full_v010.blend, exports/full_track_v010/exelberg_full_v010.kn5,
data/processed/full_track_scene_v010/{exported.json, export_allowlist.json}
"""
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, kdtree
from mathutils.bvhtree import BVHTree

ROOT = Path('/var/home/haze/dev/Assetto_Exelberg')
sys.path.insert(0, str(ROOT / 'scripts'))
import build_full_track_v002 as V2  # noqa: E402
from full_track_v002_export import exporter_class  # noqa: E402
from prototype_geometry import station_normals  # noqa: E402

SRC_BLEND = ROOT / 'blender/exelberg_full_v009.blend'
ALLOW = ROOT / 'data/processed/full_track_scene_v009/export_allowlist.json'
EXT = ROOT / 'data/processed/extension_v010'
TRACK = 'exelberg_full_v010'
BLEND = ROOT / f'blender/{TRACK}.blend'
EXPORT = ROOT / 'exports/full_track_v010'
KN5 = EXPORT / f'{TRACK}.kn5'
ORTHO_DDS = EXPORT / 'v010_ortho_ext.dds'
OUT = ROOT / 'data/processed/full_track_scene_v010'
_V4 = (ROOT / 'scripts/build_full_track_v004.py').read_text().split('\ndef main')[0]
V4 = {}
exec(compile(_V4, 'build_full_track_v004_helpers', 'exec'), V4)  # Batch, impostor, make_mesh_object, constants
MATCH_TOL = 5e-3
STOP_BEFORE_END_M = 25.0


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def require(c, msg):
    if not c:
        raise RuntimeError(msg)


def in_poly(pts, poly):
    """Even-odd point-in-polygon, vectorised (poly closed or open ring)."""
    poly = poly[:-1] if np.allclose(poly[0], poly[-1]) else poly
    x1, y1 = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    out = np.zeros(len(pts), bool)
    for a in range(0, len(pts), 4000):
        px, py = pts[a:a + 4000, 0:1], pts[a:a + 4000, 1:2]
        cond = (y1 > py) != (y2 > py)
        xi = x1 + (py - y1) * (x2 - x1) / np.where(y2 == y1, 1e-30, y2 - y1)
        out[a:a + 4000] = (cond & (px < xi)).sum(1) % 2 == 1
    return out


def corner_normals(me):
    n = np.empty(len(me.loops) * 3, np.float32)
    me.corner_normals.foreach_get('vector', n)
    return n.reshape(-1, 3)


def delete_faces(ob, mask):
    """Delete faces[mask] (and loose vertices) via bmesh; verifies the kept corners keep their normals and UVs."""
    me = ob.data
    lt = np.empty(len(me.polygons), int); me.polygons.foreach_get('loop_total', lt)
    require((lt == 3).all(), f'{ob.name}: non-triangle faces')
    keep_loops = np.repeat(~mask, 3)
    n0 = corner_normals(me)[keep_loops]
    uv0 = {l.name: np.array([d.uv[:] for d in l.data])[keep_loops] for l in me.uv_layers}
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.flatnonzero(mask)], context='FACES')
    bm.to_mesh(me); bm.free(); me.update()
    require(len(me.polygons) == int((~mask).sum()), f'{ob.name}: face count after delete')
    if me.has_custom_normals:  # fan-relative storage shifts at the new boundary -> re-set the captured corner normals
        me.normals_split_custom_set(n0.tolist())
    require(np.abs(corner_normals(me) - n0).max() < 2e-3, f'{ob.name}: corner normals changed by delete')
    for l in me.uv_layers:
        require(np.abs(np.array([d.uv[:] for d in l.data]) - uv0[l.name]).max() < 1e-6, f'{ob.name}: UVs changed')


def face_centers(ob):
    me = ob.data
    c = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('center', c)
    return c.reshape(-1, 3)


def copy_ac(src, dst):
    for p in src.assettoCorsa.bl_rna.properties:
        if p.identifier == 'rna_type' or p.is_readonly or p.type in ('POINTER', 'COLLECTION'):
            continue
        setattr(dst.assettoCorsa, p.identifier, getattr(src.assettoCorsa, p.identifier))
    for k in src.keys():
        if k != '_RNA_UI':
            dst[k] = src[k]
    dst.hide_render = src.hide_render


def new_object(name, ref, v, f, uv_corner, mats, mat_idx=None, normals=None, smooth=None):
    require(name not in bpy.data.objects, f'{name} exists')
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(v, float).tolist(), [], np.asarray(f, int).tolist())
    me.update()
    require(len(me.polygons) == len(f), f'{name}: from_pydata dropped faces')
    me.uv_layers.new(name='UVMap').data.foreach_set('uv', np.asarray(uv_corner, np.float32).ravel())
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set('material_index', np.asarray(mat_idx, np.int32))
    sm = ref.data.polygons[0].use_smooth if smooth is None else smooth
    me.polygons.foreach_set('use_smooth', np.full(len(f), sm, bool))
    if normals is not None:
        me.normals_split_custom_set_from_vertices(np.asarray(normals, float).tolist())
    ob = bpy.data.objects.new(name, me)
    ref.users_collection[0].objects.link(ob)
    copy_ac(ref, ob)
    ob['source_artifact'] = 'data/processed/extension_v010/patch.npz'
    return ob


def text_board(label, p, distance, mat, coll, offset=5.2):
    st = V2.station(p, distance)
    pt = np.array(st['point']); fx, fy = st['forward_xy']
    pt[:2] += np.array([-fy, fx]) * offset; pt[2] += 2.
    font = bpy.data.curves.new('warning', 'FONT'); font.body = label; font.size = 1.0; font.align_x = 'CENTER'; font.extrude = .012
    obj = bpy.data.objects.new(f'VIS_WARNING_{label}_{int(distance)}', font); coll.objects.link(obj)
    obj.location = pt; obj.rotation_euler = (math.pi / 2, 0, math.atan2(fy, fx) - math.pi / 2)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj; obj.select_set(True); bpy.ops.object.convert(target='MESH'); obj.select_set(False)
    mesh = obj.data
    bm = bmesh.new(); bm.from_mesh(mesh); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(mesh); bm.free()
    vv = np.array([v.co[:] for v in mesh.vertices])
    mesh.uv_layers.new(name='UVMap').data.foreach_set('uv', vv[np.array([l.vertex_index for l in mesh.loops])][:, :2].astype(np.float32).ravel())
    mesh.materials.append(mat)
    ac = obj.assettoCorsa; ac.visible = ac.renderable = ac.cast_shadows = True; ac.transparent = False; ac.lod_out = 0
    mesh.transform(obj.matrix_world); obj.matrix_world = Matrix.Identity(4)  # bake (as v002)
    return obj, dict(label=label, arclength_m=float(distance), position=np.round(pt, 3).tolist())


def rebuild_trees():
    veg = bpy.data.collections['VIS_VEGETATION']
    old = [o.name for o in veg.objects]
    for o in list(veg.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    tm = json.loads((V4['TEX'] / 'manifest.json').read_text())
    foliage, bark, impm = (bpy.data.materials[n] for n in ('V004_foliage', 'V004_bark', 'V004_impostor'))
    tr = np.load(EXT / 'trees_v010.npz')
    xyz, hgt, crown, sp, tier, seed = (tr[k] for k in ('xyz', 'height', 'crown', 'species', 'tier', 'seed'))
    meta = tm['impostor_meta']
    rng = np.random.default_rng(4004)
    cells = {}
    for i in range(len(xyz)):
        cells.setdefault((int(xyz[i, 0] // V4['CELL']), int(xyz[i, 1] // V4['CELL'])), []).append(i)
    T, Batch, impostor, mk = V4['T'], V4['Batch'], V4['impostor'], V4['make_mesh_object']
    new = []
    for key_, ids in sorted(cells.items()):
        hero, imp_near, imp_far = Batch(), Batch(), Batch()
        for i in ids:
            off = xyz[i] - np.array([0, 0, 0.2], np.float32)
            im = impostor(int(sp[i]), hgt[i], seed[i], meta, rng)
            if tier[i] == 0:
                hero.add(T.tree(int(sp[i]), float(hgt[i]), float(crown[i]), int(seed[i])), off)
                imp_near.add(im, off)
            else:
                imp_far.add(im, off)
        tag = f'{key_[0]:+04d}_{key_[1]:+04d}'.replace('+', 'p').replace('-', 'm')
        for kind, batch, mats, flags in (
                ('H', hero, [foliage, bark], dict(visible=True, renderable=True, cast_shadows=True, transparent=False, lod_in=0.0, lod_out=V4['HERO_LOD'])),
                ('L', imp_near, [impm], dict(visible=True, renderable=True, cast_shadows=False, transparent=False, lod_in=V4['HERO_LOD'], lod_out=V4['FAR_LOD'])),
                ('F', imp_far, [impm], dict(visible=True, renderable=True, cast_shadows=False, transparent=False, lod_in=0.0, lod_out=V4['FAR_LOD']))):
            if not batch.count:
                continue
            v, n, uv, tri, mi = batch.arrays()
            new.append(mk(f'VIS_TREE_{kind}_{tag}', v, n, uv, tri, mi, mats, veg, flags).name)
    return old, new, dict(trees=int(len(xyz)), new_in_patch=int(tr['new'].sum()), objects=len(new), old_objects=len(old))


def main():
    t0 = time.monotonic()
    require(not BLEND.exists() and not KN5.exists(), 'Refuse to overwrite existing v010 outputs')
    require(ORTHO_DDS.is_file(), 'run scripts/v010_textures.py first')
    OUT.mkdir(parents=True, exist_ok=True)
    src_hash = sha(SRC_BLEND)
    addon = V2.import_addon()
    bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND), load_ui=False, use_scripts=False)
    pa = np.load(EXT / 'patch.npz')
    rt = np.load(EXT / 'route.npz')
    rj = json.loads((EXT / 'route.json').read_text())
    P = rt['designed_xyz_m'].astype(float)
    N = station_normals(P)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    B = pa['B_xy'][:, :2].astype(float)
    bx0, by0 = B.min(0) - 1; bx1, by1 = B.max(0) + 1
    rc = pa['removed_centroids'].astype(float)
    allow = json.loads(ALLOW.read_text())
    report = dict(source_blend=dict(path=str(SRC_BLEND), sha256=src_hash), blender=bpy.app.version_string,
                  route=dict(length_m=float(s[-1]), finish_arclength_m=float(s[rt['finish_station']]), i_cut=int(rt['i_cut'])))
    spawns0 = {n: np.array(bpy.data.objects[n].matrix_world) for n in V2.SPAWNS}

    # --- 1. cut the v009 physics skin, walls and markings
    kd = kdtree.KDTree(len(rc))
    for i, c in enumerate(rc):
        kd.insert(Vector(c), i)
    kd.balance()
    hit = np.zeros(len(rc), int)
    cut = dict(faces_removed={}, objects_deleted=[])
    ortho_ref = None
    for cname in ('PHYS_ROAD', 'PHYS_GRAVEL', 'PHYS_GRASS', 'PHYS_WALL', 'VIS_MARKINGS'):
        for ob in list(bpy.data.collections[cname].objects):
            if ob.name not in allow or ob.type != 'MESH':
                continue
            require(np.allclose(np.array(ob.matrix_world), np.eye(4)), f'{ob.name}: non-identity transform')
            if ob.name == '1WALL_END':
                cut['objects_deleted'].append(ob.name); allow.remove(ob.name)
                bpy.data.objects.remove(ob, do_unlink=True)
                continue
            c = face_centers(ob)
            if not ((c[:, 0] > bx0) & (c[:, 0] < bx1) & (c[:, 1] > by0) & (c[:, 1] < by1)).any():
                continue
            mask = in_poly(c[:, :2], B)
            if cname.startswith('PHYS_') and cname != 'PHYS_WALL':
                # surfaces: top faces only by exact skin match (tiny kept skin triangles inside B stay); side faces in B go
                me = ob.data
                fn = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('normal', fn); fn = fn.reshape(-1, 3)
                mask &= np.abs(fn[:, 2]) <= 0.3
                for j, q in enumerate(c):
                    _, k, d = kd.find(Vector(q))
                    if d is not None and d < MATCH_TOL:
                        mask[j] = True; hit[k] += 1
                if mask.any() and cname == 'PHYS_GRASS' and ortho_ref is None:
                    ortho_ref = ob
            if not mask.any():
                continue
            cut['faces_removed'][ob.name] = int(mask.sum())
            if mask.all():
                cut['objects_deleted'].append(ob.name); allow.remove(ob.name)
                bpy.data.objects.remove(ob, do_unlink=True)
            else:
                delete_faces(ob, mask)
    require((hit == 1).all(), f'removed skin triangles matched {np.bincount(hit).tolist()} (need exactly once each)')
    cut['skin_triangles_matched'] = int(len(rc))
    report['cut'] = cut

    # --- 2. warnings
    warn = bpy.data.collections['VIS_WARNINGS']
    report['removed_warnings'] = [o.name for o in warn.objects]
    for o in list(warn.objects):
        allow.remove(o.name)
        bpy.data.objects.remove(o, do_unlink=True)

    # --- 3. new physics + visual objects
    mats = {k: bpy.data.materials[k] for k in ('V002_asphalt', 'V002_gravel', 'V002_white', 'V003_post_black')}
    ref = {k: bpy.data.objects[k] for k in ('1ROAD_000', '1GRAVEL_000', '1WALL_L_000', '1WALL_R_000', 'VIS_PAINT_000')}
    require(ortho_ref is not None, 'no grass object touched')
    ref['grass'] = ortho_ref
    base = ortho_ref.data.materials[0]
    ground_mat = base.copy(); ground_mat.name = 'V010_ortho_ext'
    img = bpy.data.images.load(str(ORTHO_DDS), check_existing=False); img.name = 'v010_ortho_ext.dds'; img.pack()
    ac = ground_mat.assettoCorsa
    slot = next(sl for sl in ac.texture_slots if sl.slot_name == 'txDiffuse')
    slot.image = img; slot.override_filename = 'v010_ortho_ext.dds'
    ob_json = json.loads((EXT / 'ortho.json').read_text())
    size = ob_json['local_bounds'][2] - ob_json['local_bounds'][0]
    ac.set_property('detailUVMultiplier', round(size / 2.5, 2))  # 2.5 m grass detail tile, as v004
    addon.materials.sync_material_nodes(ground_mat)
    new = []
    rv, rf, rr, rn = pa['ribbon_v'], pa['ribbon_f'], pa['ribbon_role'], pa['ribbon_n']
    for role, name, mat in (('ROAD', '1ROAD_X010', 'V002_asphalt'), ('GRAVEL', '1GRAVEL_X010', 'V002_gravel')):
        ff = rf[rr == role]
        used, loc = np.unique(ff, return_inverse=True)
        vv = rv[used]
        new.append(new_object(name, ref['1' + role + '_000'], vv, loc.reshape(-1, 3), (vv[loc, :2] / 6.0), [mats[mat]], normals=rn[used]))
    gv, gf = pa['ground_v'], pa['ground_f']
    new.append(new_object('1GRASS_X010', ref['grass'], gv, gf, pa['ground_uv'][gf.ravel()], [ground_mat], normals=pa['ground_n'], smooth=True))
    for label in ('L', 'R', 'END'):
        wv, wf = pa[f'wall_{label}_v'], pa[f'wall_{label}_f']
        new.append(new_object(f'1WALL_{label}_X010' if label != 'END' else '1WALL_END', ref['1WALL_L_000'] if label != 'R' else ref['1WALL_R_000'],
                              wv, wf, wv[wf.ravel()][:, [0, 2]], [mats['V003_post_black']]))
    pv, pf = pa['paint_v'], pa['paint_f']
    new.append(new_object('VIS_PAINT_X010', ref['VIS_PAINT_000'], pv, pf, pv[pf.ravel()][:, :2], [mats['V002_white']]))
    allow += [o.name for o in new]
    report['new_objects'] = {o.name: dict(vertices=len(o.data.vertices), triangles=len(o.data.polygons)) for o in new}

    # --- 4. finish gates + boards
    fin = float(s[rt['finish_station']])
    report['gates'] = {}
    for name, off in (('AC_TIME_0_L', 3.0), ('AC_TIME_0_R', -3.0)):
        st = V2.station(P, fin)
        i, w = st['index'], st['fraction']
        pt = np.array(st['point']); pt[:2] += off * ((1 - w) * N[i] + w * N[i + 1]); pt[2] += .4
        ob = bpy.data.objects[name]
        m = np.array(ob.matrix_world)
        report['gates'][name] = dict(before=m[:3, 3].round(3).tolist(), after=pt.round(3).tolist())
        m[:3, 3] = pt
        ob.matrix_world = Matrix(m.tolist())
    boards = []
    for label, dist in (('FINISH', fin), ('STOP', s[-1] - STOP_BEFORE_END_M)):
        ob, rec = text_board(label, P, float(dist), mats['V002_white'], warn)
        allow.append(ob.name); boards.append(rec)
    report['boards'] = boards

    # --- 5. trees
    old_t, new_t, report['vegetation'] = rebuild_trees()
    allow = [a for a in allow if a not in set(old_t)] + new_t

    # --- 6. checks: new walls stand on exported ground; spawns untouched; no allowlist gaps
    for n_, m0 in spawns0.items():
        require(np.allclose(np.array(bpy.data.objects[n_].matrix_world), m0), f'{n_} moved')
    vs, fs = [], []
    for cname in ('PHYS_ROAD', 'PHYS_GRAVEL', 'PHYS_GRASS'):
        for ob in bpy.data.collections[cname].objects:
            if ob.name not in allow:
                continue
            c = face_centers(ob)
            if not ((c[:, 0] > bx0 - 50) & (c[:, 0] < bx1 + 50) & (c[:, 1] > by0 - 50) & (c[:, 1] < by1 + 50)).any():
                continue
            me = ob.data
            v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', v)
            t = np.empty(len(me.polygons) * 3, int); me.polygons.foreach_get('vertices', t)
            fs.append(t.reshape(-1, 3) + sum(len(x) for x in vs)); vs.append(v.reshape(-1, 3))
    bvh = BVHTree.FromPolygons(np.vstack(vs).tolist(), np.vstack(fs).tolist(), all_triangles=True)
    miss = 0; samples = 0
    for label in ('L', 'R', 'END'):
        wv = pa[f'wall_{label}_v']
        for q in np.unique(np.round(wv[:, :2], 4), axis=0):
            loc, *_ = bvh.ray_cast(Vector((q[0], q[1], 2000.0)), Vector((0, 0, -1)), 5000)
            samples += 1; miss += loc is None
    require(miss == 0, f'{miss} wall foot points without ground')
    report['wall_ground_samples'] = samples
    objects = [bpy.data.objects[a] for a in allow]
    require(len(set(allow)) == len(allow), 'duplicate allowlist names')

    # --- export
    require(not addon.materials.audit_texture_bindings([o for o in objects if o.type == 'MESH'], 'EMBEDDED_DDS'), 'Texture bindings')
    exporter = exporter_class(addon)(bpy.context, str(KN5), dict(version=5, texture_mode='EMBEDDED_DDS', target_objects=objects,
                                     apply_modifiers=False, auto_detect_materials=False, auto_fix_wheels=False, selection_only=False))
    model = exporter.export()
    require(not exporter.warnings, 'Exporter warnings ' + str(exporter.warnings))
    require(model.root_node.name == TRACK, 'Wrong root ' + model.root_node.name)
    with KN5.open('xb') as f:
        model.to_stream(f)
    require(KN5.stat().st_size <= 256 * 1024 * 1024, 'KN5 over 256 MiB')
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), check_existing=True, copy=True)
    require(sha(SRC_BLEND) == src_hash, 'v009 blend changed!')
    report.update(kn5=dict(path=str(KN5.relative_to(ROOT)), bytes=KN5.stat().st_size, sha256=sha(KN5)), objects=len(objects),
                  elapsed_s=round(time.monotonic() - t0, 1), runtime_tested=False)
    (OUT / 'exported.json').write_text(json.dumps(report, indent=2) + '\n')
    (OUT / 'export_allowlist.json').write_text(json.dumps(allow) + '\n')
    print('V010 MAIN PASS', json.dumps({k: v for k, v in report.items() if k != 'cut'}), flush=True)
    print('CUT', json.dumps(report['cut']), flush=True)


main()
