"""Offline checks of diagnostic mathematics and generated evidence."""
import csv
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

import numpy as np
import tifffile
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnose_terrain import (cross_section, investigation_flags, grouped_intervals,
                              route_points, sections_svg, support_tiles)
from extract_terrain import bilinear, resample_route


class DiagnosticTests(unittest.TestCase):
    def test_normal_and_plane_sampling(self):
        # Eastbound route, left normal north. Grid plane height = northing.
        xy = np.array([[30.,50.],[70.,50.]])
        grid = np.repeat((99.5-np.arange(100))[:,None],100,axis=1)
        section = cross_section(xy,20,grid,(0,100,1,1))
        np.testing.assert_allclose(section['center_3035_m'],[50,50])
        np.testing.assert_allclose(section['tangent_unit_3035'],[1,0])
        np.testing.assert_allclose(section['left_normal_unit_3035'],[0,1])
        np.testing.assert_allclose(section['terrain_heights_m'],50+np.arange(-20,21))
        self.assertEqual(section['tangent_chord_distances_m'],[18,22])
        self.assertEqual(cross_section(xy,0,grid,(0,100,1,1))['tangent_chord_distances_m'],[0,2])

    def test_flags_groups_and_nodata(self):
        distances = np.arange(7.)
        heights = np.array([0,0,1,0,0,np.nan,0])
        grades, changes, flags = investigation_flags(distances,heights)
        self.assertEqual(flags.tolist(),[False,True,True,True,False,False])
        groups = grouped_intervals(distances,grades,changes,flags)
        self.assertEqual(len(groups),1)
        self.assertEqual((groups[0]['start_m'],groups[0]['end_m']),(1,4))
        self.assertEqual(grouped_intervals(distances,grades,changes,np.zeros(6,dtype=bool)),[])

    def test_support_tiles_includes_bilinear_boundary(self):
        self.assertEqual(support_tiles([(512,512)], (0,1024,1,1),1024),[0,1,2,3])

    def test_svg_standalone_and_gaps(self):
        grid = np.ones((100,100))
        section = cross_section(np.array([[30.,50.],[70.,50.]]),20,grid,(0,100,1,1))
        section['terrain_heights_m'][20] = None
        root = ET.fromstring(sections_svg([section]))
        self.assertEqual(len(root.findall('.//{http://www.w3.org/2000/svg}polyline')),2)
        self.assertFalse(root.findall('.//{http://www.w3.org/2000/svg}image'))

    def test_generated_dense_profile_and_sections(self):
        root = Path(__file__).resolve().parents[1]/'data/processed'
        report = json.loads((root/'terrain_diagnostic_1m.json').read_text())
        coords = np.array(json.loads((root/'route.geojson').read_text())['features'][0]['geometry']['coordinates'])[:,:2]
        xy = np.column_stack(Transformer.from_crs(4326,3035,always_xy=True).transform(coords[:,0],coords[:,1]))
        distances, points = resample_route(xy,1)
        with tifffile.TiffFile(root/'terrain_corridor_3035.tif') as tif:
            page = tif.pages[0]
            grid = page.asarray()
            scale, tie = page.tags[33550].value,page.tags[33922].value
            transform = (tie[3],tie[4],scale[0],scale[1])
        heights = bilinear(grid,points,transform)
        with (root/'terrain_diagnostic_1m.csv').open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows),len(distances))
        self.assertEqual(report['samples'],len(distances))
        np.testing.assert_allclose([float(r['distance_3035_m']) for r in rows],distances,atol=.00051,rtol=0)
        np.testing.assert_allclose([float(r['terrain_height_9274_m']) for r in rows],heights,atol=.00000051,rtol=0)
        self.assertTrue(np.isfinite(heights).all())
        self.assertLessEqual(np.diff(distances).max(),1.000001)
        grades, changes, flags = investigation_flags(distances,heights)
        self.assertEqual(report['grouped_intervals'],grouped_intervals(distances,grades,changes,flags))
        self.assertEqual([int(r['investigation_flag']) for r in rows],[0]+flags.astype(int).tolist())
        for section in report['cross_sections']:
            expected = cross_section(xy,section['distance_m'],grid,transform)
            for key,value in expected.items():
                self.assertEqual(section[key],value)
        self.assertEqual(report['suspect_source_support_tile_indices'],[7021])
        suspect = {r['distance_m']:r['terrain_height_m'] for r in report['suspect_profile']}
        self.assertAlmostEqual(suspect[9585],488.873,places=3)
        self.assertAlmostEqual(suspect[9589],486.529,places=3)
        self.assertAlmostEqual(suspect[9593],489.234,places=3)
        ET.parse(root/'terrain_diagnostic_cross_sections.svg')


if __name__ == '__main__':
    unittest.main()
