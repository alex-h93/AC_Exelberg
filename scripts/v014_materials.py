"""v014 material/texture patch for the main and scenery KN5s (header only, see kn5_header.py; meshes byte-identical).

Shaders are vanilla Kunos shaders (no CSP needed); slot/property names copied from the user's installed Kunos tracks
(imola 'Sand-16' = ksPerPixelMultiMap_NMDetail: txDiffuse, txNormal, txMaps, txDetail, txNormalDetail).
  main  V002_asphalt  ksPerPixel -> ksPerPixelMultiMap_NMDetail: Asphalt015 (6 m tile) + normal + spec map, 60 m macro detail
  main  V002_gravel   ksPerPixel -> ksPerPixelMultiMap_NMDetail: Gravel023 (6 m tile) + normal, 60 m macro detail
  main  V004_ortho_*, V010_ortho_ext  ksPerPixelMultiMap -> ksPerPixelMultiMap_NMDetail: new grass detail (5 m tile,
        stronger contrast) + grass normal detail (detailNormalBlend 1)
  scenery V011_asphalt / V011_gravel (roundabout, junction stubs; 4 m per UV unit): same textures, macro scaled to 60 m
Unused old textures (v002_asphalt/gravel, v004_grass_detail, v007_asphalt/gravel) are dropped.
"""
from pathlib import Path

import kn5_header as K

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / 'data/processed/textures_v014'
ORDER = ('ksAmbient', 'ksDiffuse', 'ksSpecular', 'ksSpecularEXP', 'ksEmissive', 'ksAlphaRef', 'fresnelC', 'fresnelEXP',
         'fresnelMaxLevel', 'isAdditive', 'useDetail', 'detailUVMultiplier', 'shadowBiasMult', 'detailNormalBlend')
NMD = 'ksPerPixelMultiMap_NMDetail'
MACRO_M = 60.0
ROAD_TEX = ['v014_asphalt.dds', 'v014_asphalt_nm.dds', 'v014_asphalt_maps.dds', 'v014_asphalt_macro.dds', 'v014_gravel.dds',
            'v014_gravel_nm.dds', 'v014_maps_matte.dds', 'v014_flat_nm.dds']


def nmdetail(m, values, diffuse, normal, maps, detail, ndetail):
    base = dict(ksEmissive=0.0, ksAlphaRef=0.0, fresnelC=0.0, fresnelEXP=1.0, fresnelMaxLevel=0.0, isAdditive=0.0,
                useDetail=1.0, shadowBiasMult=0.0, detailNormalBlend=0.0)
    base.update(values)
    assert set(base) == set(ORDER), set(ORDER) ^ set(base)
    m.update(shader=NMD, blend=0, alpha=0, depth=0, props=[(k, K.prop(base[k])) for k in ORDER],
             bindings=[('txDiffuse', 0, diffuse), ('txNormal', 1, normal), ('txMaps', 2, maps), ('txDetail', 3, detail),
                       ('txNormalDetail', 4, ndetail)])


def road(m, m_per_uv, kind):
    if kind == 'asphalt':
        nmdetail(m, dict(ksAmbient=0.45, ksDiffuse=0.6, ksSpecular=0.3, ksSpecularEXP=25.0, detailUVMultiplier=m_per_uv / MACRO_M),
                 'v014_asphalt.dds', 'v014_asphalt_nm.dds', 'v014_asphalt_maps.dds', 'v014_asphalt_macro.dds', 'v014_flat_nm.dds')
    else:
        nmdetail(m, dict(ksAmbient=0.47, ksDiffuse=0.55, ksSpecular=0.03, ksSpecularEXP=8.0, detailUVMultiplier=m_per_uv / MACRO_M),
                 'v014_gravel.dds', 'v014_gravel_nm.dds', 'v014_maps_matte.dds', 'v014_asphalt_macro.dds', 'v014_flat_nm.dds')


def ground(m):
    p = {k: v[0] for k, v in m['props']}
    old = {b[0]: b[2] for b in m['bindings']}
    assert m['shader'] == 'ksPerPixelMultiMap' and old['txDetail'] == 'v004_grass_detail.dds', m['name']
    nmdetail(m, dict(ksAmbient=p['ksAmbient'], ksDiffuse=p['ksDiffuse'], ksSpecular=p['ksSpecular'], ksSpecularEXP=p['ksSpecularEXP'],
                     detailUVMultiplier=p['detailUVMultiplier'] / 2.0,   # 2048 px detail now covers 5 m (v004: 1024 px, 2.47 m)
                     detailNormalBlend=1.0),
             old['txDiffuse'], old['txNormal'], old['txMaps'], 'v014_grass_detail.dds', 'v014_grass_nm.dds')


def _finish(h, add):
    have = {t['name'] for t in h['textures']}
    for name in add:
        if name not in have:
            h['textures'].append(K.texture(name, (TEX / name).read_bytes()))
    used = {b[2] for m in h['materials'] for b in m['bindings']}
    dropped = [t['name'] for t in h['textures'] if t['name'] not in used]
    h['textures'] = [t for t in h['textures'] if t['name'] in used]
    missing = used - {t['name'] for t in h['textures']}
    assert not missing, missing
    return dropped


def patch_main(data):
    h = K.read(data)
    changed = []
    for m in h['materials']:
        if m['name'] == 'V002_asphalt':
            road(m, 6.0, 'asphalt'); changed.append(m['name'])
        elif m['name'] == 'V002_gravel':
            road(m, 6.0, 'gravel'); changed.append(m['name'])
        elif m['name'].startswith('V004_ortho_') or m['name'] == 'V010_ortho_ext':
            ground(m); changed.append(m['name'])
    assert {'V002_asphalt', 'V002_gravel', 'V010_ortho_ext'} <= set(changed) and len(changed) == 29, changed
    dropped = _finish(h, ROAD_TEX + ['v014_grass_detail.dds', 'v014_grass_nm.dds'])
    return K.write(h, data[h['node_offset']:]), dict(materials=changed, textures_dropped=dropped)


def patch_scenery(data):
    h = K.read(data)
    changed = []
    for m in h['materials']:
        if m['name'] in ('V011_asphalt', 'V011_gravel'):
            road(m, 4.0, 'asphalt' if m['name'].endswith('asphalt') else 'gravel'); changed.append(m['name'])
    assert len(changed) == 2, changed
    dropped = _finish(h, ROAD_TEX)
    return K.write(h, data[h['node_offset']:]), dict(materials=changed, textures_dropped=dropped)
