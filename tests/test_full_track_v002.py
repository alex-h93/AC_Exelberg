"""Offline v002 geometry, bounded parser and (when built) full-artifact regression tests."""
import inspect
import json
from pathlib import Path
import sys
import struct
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import full_track_v002_geometry as G
import build_full_track_v002 as B
import validate_kn5 as K


class GeometryTests(unittest.TestCase):
    def test_convex_subtraction_accounts_area(self):
        square=np.array([[0.,0.],[8.,0.],[8.,8.],[0.,8.]])
        cut=np.array([[3.,-1.],[5.,-1.],[5.,9.],[3.,9.]])
        pieces=G.subtract(square,cut)
        self.assertAlmostEqual(sum(G.area(p) for p in pieces),48.)
        self.assertTrue(all(G.area(p)>0 for p in pieces))

    def test_no_intersection_unchanged(self):
        p=np.array([[0.,0.],[1.,0.],[0.,1.]])
        q=np.array([[5.,5.],[6.,5.],[6.,6.],[5.,6.]])
        self.assertAlmostEqual(sum(G.area(x) for x in G.subtract(p,q)),.5)

    def test_closed_outward_slab(self):
        v=np.array([[0.,0.,3.],[2.,0.,3.],[2.,2.,3.],[0.,2.,3.]])
        f=np.array([[0,1,2],[0,2,3]])
        vv,ff=G.closed_slab(v,f,.3);check=G.solid_checks(vv,ff)
        self.assertAlmostEqual(check['volume_m3'],1.2)
        with self.assertRaises(ValueError):G.solid_checks(vv,ff[:-1])
        with self.assertRaises(ValueError):G.solid_checks(vv,ff[:,::-1])

    def test_point_touching_chunk_fans_close_independently(self):
        v=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[-1.,0.,0.],[0.,-1.,0.]])
        f=np.array([[0,1,2],[0,3,4]])
        vv,ff=G.closed_slab(v,f,.3)
        self.assertTrue(G.solid_checks(vv,ff)['closed'])

    def test_corrected_spawn_plus_z_travel(self):
        for f in ([0,1],[1,0],[-.6,.8]):
            b,k=B.corrected_spawn([1,2,3],f)
            self.assertTrue(np.allclose(np.array(b)[:2,1],-np.array(f)))
            self.assertGreater(np.array(k)[8:11]@np.array([f[0],0,-f[1]]),.999999)
            self.assertAlmostEqual(np.linalg.det(np.array(b)[:3,:3]),1.)

    def test_visible_grid_and_invalid_masks(self):
        t=dict(x_m=np.array([[0,8],[0,8]]),y_m=np.array([[0,0],[8,8]]),
               z_m=np.array([[0,8],[8,16.]]),valid_cells=np.ones((1,1),dtype=bool))
        self.assertTrue(np.allclose(G.grid_sample(t,[[3,4],[8,8]]),[7,16]))
        t['valid_cells'][:]=False
        with self.assertRaises(ValueError):G.grid_sample(t,[[3,4]])

    def test_nearest_exact_segments_not_vertices(self):
        p=np.array([[0.,0.,0.],[100.,0.,0.],[100.,10.,0.],[0.,10.,0.]])
        i,t,d=G.nearest(np.array([[50.,2.],[55.,9.]]),p)
        self.assertTrue(np.array_equal(i,[0,2]));self.assertTrue(np.allclose(d,[2,1]))

    def test_procedural_images_are_opaque_varied_reproducible(self):
        for name in B.MATERIALS:
            a=B.texture_pixels(name)
            self.assertTrue(np.array_equal(a,B.texture_pixels(name)))
            self.assertEqual(a.shape,(256,256,4));self.assertTrue((a[:,:,3]==1).all())
            self.assertGreater(a[:,:,:3].std(0).max(),.005)

    def test_optional_node_budget_not_disabled(self):
        def dummy(name,children=0):
            text=name.encode();return struct.pack('<II',1,len(text))+text+struct.pack('<IB',children,1)+np.eye(4,dtype='<f4').tobytes()
        data=b'sc6969'+struct.pack('<III',5,0,0)+dummy('root',70)+b''.join(dummy(str(i)) for i in range(70))
        with self.assertRaises(K.InvalidKN5):K.parse(data)
        self.assertEqual(len(K.parse(data,max_nodes=128)['nodes']),71)
        with self.assertRaises(K.InvalidKN5):K.parse(data,max_nodes=70)

    def test_bounded_parser_defaults_and_hard_caps(self):
        self.assertEqual(inspect.signature(K.parse).parameters['max_nodes'].default,64)
        self.assertIsNone(inspect.signature(K.parse).parameters['max_file'].default)
        self.assertEqual(K.MAX_FILE,32*1024*1024)
        with self.assertRaises(K.InvalidKN5):K.parse(b'',max_nodes=4097)
        with self.assertRaises(K.InvalidKN5):K.parse(b'',max_file=256*1024*1024+1)
        with self.assertRaises(K.InvalidKN5):K.parse(b'',max_texture=8*1024*1024+1)


@unittest.skipUnless((B.OUT/'manifest.json').exists(),'Full candidate not built yet')
class FullArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=json.loads((B.OUT/'manifest.json').read_text())

    def test_full_extent_lanes_grade_overlap(self):
        m=self.m;self.assertEqual(m['route']['chainage_3035_m'],[0,15226.291863325048])
        self.assertEqual(m['route']['lanes'],2);self.assertEqual(m['route']['width_m'],6)
        self.assertEqual(m['route']['crossfall'],0);self.assertGreater(m['route']['designed_road_length_m'],15200)
        self.assertEqual(m['design']['nonadjacent_overlaps'],[]);self.assertEqual(m['design']['folds'],0)
        self.assertLess(m['design']['profile']['max_grade_step_percentage_points'],1.)
        self.assertLess(m['design']['profile']['grade_min_max_percent'][1],12.)

    def test_raw_dip_audited(self):
        d=self.m['design']['dip'];self.assertEqual(d['window_chainage_3035_m'],[9578.,9602.])
        self.assertGreater(max(d['bridge_delta_m']),2.)
        with np.load(B.OUT/'geometry_audit.npz',allow_pickle=False) as a:
            self.assertTrue(np.array_equal(a['raw_xyz_m'],np.load(B.INPUT/'route.npz')['local_xyz_m']))
            ids=np.array(d['source_indices']);self.assertTrue(np.allclose(a['designed_xyz_m'][ids,2],d['final_local_z_m']))

    def test_all_valid_cells_accounted_no_invented_coverage(self):
        t=self.m['terrain'];self.assertEqual(t['valid_source_cells'],207885)
        self.assertAlmostEqual(t['terrain_top_area_m2']+t['road_replaced_area_m2']+t['audited_numeric_sliver_area_m2']-t['float32_xy_area_delta_m2'],t['valid_source_area_m2'],places=5)
        self.assertLess(t['max_seam_xy_error_m'],.001);self.assertGreater(t['exact_shoulder_seam_points'],1000)

    def test_collision_visual_allowlist_and_tree_count(self):
        self.assertEqual(set(self.m['surfaces']),{'ROAD','GRAVEL','GRASS','WALL'})
        self.assertEqual(self.m['forest']['count'],4616);self.assertLess(self.m['forest']['chunks'],1000)
        for m in self.m['meshes']:
            self.assertEqual(m['collision'],m['name'].startswith('1'))
            if m['collision']:self.assertTrue(m['closed'])
            else:self.assertIsNone(m['surface_key'])
        self.assertTrue(self.m['static_checks']['collision_solids_closed_outward'])

    def test_all_trees_grounded_on_actual_derived_visible_mesh(self):
        with np.load(B.OUT/'geometry_audit.npz',allow_pickle=False) as a:
            v=a['clipped_terrain_xyz_m'].astype(np.float32).astype(float);f=a['clipped_terrain_triangles'];cells=a['terrain_triangle_source_cell']
        with np.load(B.INPUT/'terrain.npz',allow_pickle=False) as a:t={k:a[k] for k in a.files}
        with np.load(B.OUT/'forest_grounding.npz',allow_pickle=False) as a:anchors=a['visible_terrain_xyz_m']
        actual=B.sample_visible(anchors,t,v,f,cells)
        self.assertEqual(len(actual),4616)
        self.assertLess(np.max(np.abs(actual[:,2]-anchors[:,2])),.00003)
        self.assertLess(self.m['static_checks']['collision_joins']['max_terrain_shoulder_float32_gap_m'],.001)

    def test_spawn_timing_and_artifact_hashes(self):
        self.assertEqual(self.m['spawn_contract']['yaw_change_from_v001_degrees'],180)
        for h in self.m['helpers'][:3]:
            self.assertEqual(h['lateral_offset_left_m'],-1.5)
            self.assertGreater(h['actual_kn5_plus_z_dot_travel'],.99999)
        self.assertEqual(self.m['timing_contract']['finish_runout_to_source_endpoint_m'],300)
        for rec in self.m['outputs']:self.assertEqual(B.record(ROOT/rec['path']),rec)
        self.assertTrue(self.m['source_preservation']['verified'])

    def test_complete_uint16_split_totals(self):
        check=self.m['static_checks'];self.assertLessEqual(check['max_mesh_vertices'],65535)
        self.assertEqual(check['triangles'],sum(x['triangles'] for x in self.m['meshes']))
        self.assertTrue(check['exact_oriented_xyz_uv_multiset_all_splits'])
        self.assertFalse(check['ac_runtime_tested'])

if __name__=='__main__':unittest.main()
