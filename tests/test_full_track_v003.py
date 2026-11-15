"""v003 contracts: no game/deployment/GUI access; existing tests retain defaults."""
import inspect
import json
from pathlib import Path
import struct
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import full_track_v003_geometry as H
import build_full_track_v003 as B
from prototype_geometry import require
from validate_kn5 import InvalidKN5,compare_corners
from full_track_v003_kn5 import parse


class GeometryV003(unittest.TestCase):
    def test_top_extraction_keeps_open_skin(self):
        import full_track_v002_geometry as G
        v=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        f=np.array([[0,1,2]]);v,f=G.closed_slab(v,f,.3)
        vv,ff,uv=H.extract_top(dict(vertices=v,triangles=f,uv=v[:,:2]))
        self.assertEqual(len(vv),3);np.testing.assert_array_equal(ff,[[0,1,2]])

    def test_single_shell_inward_winding(self):
        xy=np.array([[0.,6.],[2.,6.]])
        for side in (-1,1):
            v,f=H.wall_strip(xy*np.array([1,side]),[-1,-1],[3,3],side)
            self.assertEqual(len(f),2)
            normal=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
            self.assertTrue((normal[:,1]*(-side)>0).all())

    def test_padding_never_changes_valid_black(self):
        rgb=np.zeros((3,3,3),np.uint8);rgb[1,1]=[21,34,55];mask=np.zeros((3,3),bool);mask[1,1]=True;mask[1,2]=True
        padded=B.padding(rgb,mask)
        np.testing.assert_array_equal(padded[mask],rgb[mask]);self.assertTrue((padded[0,0]==[21,34,55]).all())

    def test_slope_projection_preserves_fixed_controls(self):
        v=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,2.]],np.float32);f=np.array([[0,1,2]])
        result=H.limit_slopes(v,f,[0,1]);self.assertLessEqual(H.quality(result,f)[2].max(),.30002)
        np.testing.assert_array_equal(result[:2],v[:2])

    def test_parser_defaults_not_relaxed(self):
        sig=inspect.signature(parse)
        self.assertEqual(sig.parameters['max_materials'].default,32);self.assertEqual(sig.parameters['max_textures'].default,32)
        for kwargs in (dict(max_materials=129),dict(max_textures=129),dict(max_textures=0)):
            with self.assertRaises(InvalidKN5):parse(b'',**kwargs)

    def test_wall_ground_bounds_include_entire_adjacent_face(self):
        v=np.array([[0.,0.,-2.],[2.,0.,4.],[0.,2.,1.]],np.float32);index=H.GroundIndex(v,np.array([[0,1,2]]))
        self.assertEqual(index.bounds([.1,.1],[.2,.2]),(-2.,4.));self.assertAlmostEqual(index.sample([.5,.5]),.25)


class ActualCandidateV003(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=json.loads((B.OUT/'manifest.json').read_text());cls.old=json.loads(B.OLD.read_text());cls.g=json.loads((B.OUT/'ground_audit.json').read_text())

    def test_extracted_counts(self):
        self.assertEqual(json.loads((B.OUT/'top_extraction.json').read_text())['counts'],dict(ROAD=32620,GRAVEL=77215,GRASS=503956))

    def test_actual_top_skin_and_overlap(self):
        self.assertEqual(self.g['status'],'PASS');self.assertEqual(self.g['overlap']['positive_pairs'],0)
        for key in ('inverted','needle_altitude_under1mm','duplicate_faces','edges_incidence_over2','two_face_edges_same_direction'):self.assertEqual(self.g[key],0,key)
        self.assertLess(self.g['max_reachable_slope'],.301)

    def test_v002_helpers_dip_and_asphalt_texture_exact(self):
        self.assertEqual(self.m['helpers'],self.old['helpers']);self.assertEqual(self.m['design'],self.old['design'])
        old=next(t for t in self.old['textures'] if t['path'].endswith('v002_asphalt.dds'))
        new=next(t['artifact'] for t in self.m['textures'] if t['material']=='asphalt')
        self.assertEqual(old['sha256'],new['sha256'])

    def test_exact_original_road_xyz_and_corner_uv(self):
        expected=[];actual=[]
        for spec in self.old['meshes']:
            if spec['surface_key']=='ROAD':
                with np.load(B.verified(spec['artifact'])) as a:v,f,uv=H.extract_top(a)
                expected.append(np.concatenate([v[f],uv],2))
        for spec in self.m['meshes']:
            if spec['surface_key']=='ROAD':
                with np.load(B.verified(spec['artifact'])) as a:actual.append(np.concatenate([a['vertices'][a['triangles']],a['corner_uv']],2))
        compare_corners(np.concatenate(expected),np.concatenate(actual))

    def test_actual_33_assets_require_explicit_opt_in(self):
        from validate_kn5 import parse as legacy_parse
        payload=B.KN5.read_bytes()
        for reader in (parse,legacy_parse):
            with self.assertRaises(InvalidKN5):reader(payload,max_file=256*1024**2,max_nodes=4096,max_texture=8*1024**2)

    def test_actual_export_role_flags_and_limits(self):
        checks=self.m['static_checks'];self.assertTrue(checks['exact_oriented_xyz_uv']);self.assertLessEqual(checks['max_mesh_vertices'],65535);self.assertLess(checks['bytes'],256*1024**2)
        self.assertEqual(set(self.m['surfaces']),{'ROAD','GRAVEL','GRASS','WALL'})
        for spec in self.m['meshes']:
            self.assertEqual(spec['flags']['renderable'],int(spec['surface_key']!='WALL'))
            self.assertNotIn('safety',spec['material']);self.assertFalse(spec['closed'])
            if spec['collection']=='VIS_POSTS':self.assertFalse(spec['collision']);self.assertFalse(spec['name'][0].isdigit())

    def test_orthos_actual_dds_colour_coordinate_controls(self):
        controls=json.loads((B.OUT/'ortho_controls.json').read_text());count=0
        for t in self.m['textures']:
            if 'source_chunk' not in t:continue
            payload=B.verified(t['artifact']).read_bytes();height,width=struct.unpack_from('<II',payload,12);pixels=np.frombuffer(payload[128:],np.uint8).reshape(height,width,4)
            for c in controls:
                if c['chunk']!=t['source_chunk']['index']:continue
                r,col=c['pixel_row_col'];np.testing.assert_array_equal(pixels[r,col,[2,1,0]],c['rgb']);self.assertEqual(c['kn5_uv'],[(col+.5)/width,(r+.5)/height]);count+=1
            self.assertTrue(t['actual_blender_material']['node_images'])
        self.assertEqual(count,182);self.assertEqual(self.m['landscape']['chunks'],26)
        self.assertEqual(self.g['orthographic_uv_min'],0);self.assertEqual(self.g['orthographic_uv_max'],1)

    def test_original_forest_xy_faces_and_chunk_identity_preserved(self):
        originals={s['name']:s for s in self.old['meshes'] if s['collection']=='VIS_FOREST'}
        current={s['name']:s for s in self.m['meshes'] if s['collection']=='VIS_FOREST'}
        self.assertEqual(set(originals),set(current))
        for name,spec in current.items():
            with np.load(B.verified(originals[name]['artifact'])) as a:oldv=a['vertices'];oldf=a['triangles']
            with np.load(B.verified(spec['artifact'])) as a:
                np.testing.assert_array_equal(a['vertices'][:,:2],oldv[:,:2]);np.testing.assert_array_equal(a['triangles'],oldf)

    def test_posts_forest_bvh_and_runtime_disclaimer(self):
        self.assertEqual(self.m['forest']['count'],4616);self.assertEqual(self.m['posts']['count'],822);self.assertEqual(self.m['posts']['skipped'],98)
        self.assertEqual(self.m['bvh_ground_validation']['missing'],0);self.assertGreater(self.m['bvh_ground_validation']['min_inward_normal_dot'],0)
        for wall in self.m['barriers']['side_strips']:
            self.assertEqual(abs(wall['offset_m']),6);self.assertGreaterEqual(wall['min_below_ground_m'],1);self.assertGreaterEqual(wall['min_above_ground_road_m'],3)
        self.assertEqual(self.m['runtime']['actual_cpu_previews'],3);self.assertFalse(self.m['runtime']['ac_tested']);self.assertFalse(self.m['runtime']['game_deployed'])

if __name__=='__main__':unittest.main()
