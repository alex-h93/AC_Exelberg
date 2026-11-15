"""Bounded installer fixtures plus hashed full-delivery checks (no repeated KN5 parse)."""
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import imagecodecs
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install_full_track_v003 as installer
import package_full_track_v003 as builder


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'package'
        self.package.mkdir()
        self.manifest = self.root / 'manifest.json'
        self.game = self.root / 'game'
        self.tracks = self.game / 'content/tracks'
        self.tracks.mkdir(parents=True)
        self.old = self.tracks / 'exelberg_north_proto_v001'
        self.old.mkdir()
        (self.old / 'sentinel').write_bytes(b'v001 untouched')
        self.v2 = self.tracks / 'exelberg_full_v002'
        self.v2.mkdir()
        (self.v2 / 'sentinel').write_bytes(b'v002 untouched')
        (self.game / 'global.ini').write_bytes(b'global untouched')
        self.records = []
        for name in sorted(installer.ALLOWLIST):
            path = self.package / name
            path.parent.mkdir(exist_ok=True)
            data = name.encode()
            path.write_bytes(data)
            self.records.append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        self.meta = dict(schema='full_track_package_v003', track_id=installer.TRACK_ID,
                         files=self.records, file_count=len(self.records), bytes=sum(r['bytes'] for r in self.records))
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.meta))

    def run_install(self, commit=False):
        return installer.install(self.package, self.manifest, self.game, commit=commit)

    def assert_preserved(self):
        self.assertEqual((self.old / 'sentinel').read_bytes(), b'v001 untouched')
        self.assertEqual((self.v2 / 'sentinel').read_bytes(), b'v002 untouched')
        self.assertEqual((self.game / 'global.ini').read_bytes(), b'global untouched')

    def test_dry_run_no_game_writes(self):
        result = self.run_install()
        self.assertEqual(result['mode'], 'DRY_RUN')
        self.assertEqual(set(self.tracks.iterdir()), {self.old, self.v2})
        self.assert_preserved()

    def test_commit_new_folder_and_refuse_repeat(self):
        self.assertEqual(self.run_install(True)['mode'], 'INSTALL')
        target = self.tracks / installer.TRACK_ID
        for r in self.records:
            self.assertEqual((target / r['path']).read_bytes(), (self.package / r['path']).read_bytes())
        with self.assertRaises(FileExistsError):
            self.run_install(True)
        self.assert_preserved()

    def test_tamper(self):
        (self.package / 'models.ini').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            self.run_install(True)
        self.assertEqual(set(self.tracks.iterdir()), {self.old, self.v2})

    def test_extra_file(self):
        (self.package / 'unlisted').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            self.run_install()

    def test_extra_empty_directory(self):
        (self.package / 'failed_export').mkdir()
        with self.assertRaises(ValueError):
            self.run_install()

    def test_manifest_paths_and_duplicate(self):
        original = self.records[0]['path']
        for bad in ('../escape', '/absolute', 'ui/../escape', 'ui\\escape', 'ui//escape', './models.ini', self.records[1]['path']):
            with self.subTest(bad=bad):
                self.records[0]['path'] = bad
                self.save()
                with self.assertRaises(ValueError):
                    self.run_install()
        self.records[0]['path'] = original

    def test_wrong_identity(self):
        self.meta['track_id'] = 'exelberg_north_proto_v001'
        self.save()
        with self.assertRaises(ValueError):
            self.run_install()

    def test_caps_before_read(self):
        self.records[0]['bytes'] = installer.FILE_CAP + 1
        self.save()
        with self.assertRaises(ValueError):
            self.run_install()
        self.records[0]['bytes'] = installer.FILE_CAP
        self.records[1]['bytes'] = installer.FILE_CAP
        self.save()
        with self.assertRaises(ValueError):
            self.run_install()

    def test_source_file_symlink(self):
        p = self.package / 'models.ini'
        p.unlink()
        p.symlink_to(self.game / 'global.ini')
        with self.assertRaises(ValueError):
            self.run_install(True)

    def test_source_directory_symlink(self):
        (self.package / 'ui').rename(self.root / 'ui')
        (self.package / 'ui').symlink_to(self.root / 'ui', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_install(True)

    def test_source_root_symlink(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.package, target_is_directory=True)
        with self.assertRaises(ValueError):
            installer.install(alias, self.manifest, self.game)

    def test_destination_symlink(self):
        (self.tracks / installer.TRACK_ID).symlink_to(self.old, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            self.run_install(True)
        self.assert_preserved()

    def test_game_child_symlink(self):
        self.tracks.rename(self.game / 'actual_tracks')
        self.tracks.symlink_to(self.game / 'actual_tracks', target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_install(True)

    def test_destination_race_no_replace(self):
        real_rename = installer.rename_new
        def compete(fd, source, destination):
            os.mkdir(destination, dir_fd=fd)
            real_rename(fd, source, destination)
        with patch.object(installer, 'rename_new', side_effect=compete):
            with self.assertRaises(FileExistsError):
                self.run_install(True)
        self.assertEqual(list((self.tracks / installer.TRACK_ID).iterdir()), [])
        self.assertFalse(any('.stage-' in p.name for p in self.tracks.iterdir()))
        self.assert_preserved()

    def test_no_mutable_legacy_profile(self):
        import install_full_track_v002 as legacy
        profile = (legacy.TRACK_ID, legacy.PACKAGE, legacy.MANIFEST, legacy.DDS, legacy.ALLOWLIST)
        self.run_install()
        self.assertEqual(profile, (legacy.TRACK_ID, legacy.PACKAGE, legacy.MANIFEST, legacy.DDS, legacy.ALLOWLIST))
        self.assertIsInstance(installer.ALLOWLIST, frozenset)
        self.assertIsInstance(installer.DDS, tuple)

    def test_snapshot_immune_to_source_change(self):
        real_snapshot = installer.snapshot
        def change(*args):
            meta = real_snapshot(*args)
            (self.package / 'models.ini').write_bytes(b'changed after verification')
            return meta
        with patch.object(installer, 'snapshot', side_effect=change):
            self.run_install(True)
        self.assertEqual((self.tracks / installer.TRACK_ID / 'models.ini').read_bytes(), b'models.ini')


class FullDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads(installer.MANIFEST.read_text())
        cls.package = installer.PACKAGE
        cls.scene = json.loads(builder.SCENE.read_text())

    def test_complete_hashes_and_bounded_parse_evidence(self):
        meta = installer.validate_source()
        self.assertEqual(meta['file_count'], 46)
        self.assertEqual(meta['validation']['nodes'], 1344)
        self.assertEqual(meta['validation']['limits'], dict(file=256*1024*1024, nodes=4096, texture=8*1024*1024, materials=128, textures=128))
        self.assertEqual(meta['validation']['independent_parse'], 'PASS')
        for key in ('scene_manifest', 'map_source', 'preview_source', 'source_validation', 'parser', 'parser_reader', 'builder', 'installer', 'ground_audit'):
            builder.verified(meta[key])
        for r in meta['source_assets']:
            builder.verified(r)

    def test_zip_exact_inventory_and_streamed_hashes(self):
        r = self.meta['zip']
        with (builder.ROOT / r['path']).open('rb') as stream:
            self.assertEqual(installer.transfer(stream), (r['bytes'], r['sha256']))
        with zipfile.ZipFile(builder.ROOT / r['path']) as archive:
            self.assertEqual(set(archive.namelist()), {installer.TRACK_ID+'/'+n for n in installer.ALLOWLIST})
            for item in self.meta['files']:
                with archive.open(installer.TRACK_ID+'/'+item['path']) as stream:
                    self.assertEqual(installer.transfer(stream), (item['bytes'], item['sha256']))

    def test_models_surfaces_ui_ai(self):
        ini = configparser.ConfigParser()
        ini.read(self.package / 'models.ini')
        self.assertEqual(dict(ini['MODEL_0']), dict(file=installer.TRACK_ID+'.kn5', position='0,0,0', rotation='0,0,0'))
        ini.read(self.package / 'data/surfaces.ini')
        for i, key in enumerate(('ROAD', 'GRAVEL', 'GRASS', 'WALL')):
            section = ini[f'SURFACE_{i}']
            s = self.scene['surfaces'][key]
            self.assertEqual(section['key'], key)
            self.assertEqual(float(section['friction']), s['friction'])
            self.assertEqual(int(section['is_valid_track']), s['is_valid_track'])
            self.assertEqual(int(section['is_pitlane']), s['is_pitlane'])
        ui = json.loads((self.package / 'ui/ui_track.json').read_text())
        self.assertEqual(ui['name'], 'Exelberg Full v003 (collision + ortho)')
        self.assertEqual(ui['length'], '15212.525 m')
        self.assertEqual(ui['pitboxes'], '1')
        for name in ('fast_lane', 'pit_lane'):
            self.assertEqual((self.package / f'ai/{name}.ai').read_bytes(), struct.pack('<III', 3, 0, 0))
        self.assertFalse(self.meta['validation']['runtime_tested'])

    def test_map_registration_north_up_and_render_resize(self):
        with np.load(io.BytesIO(builder.verified(self.meta['map_source'])), allow_pickle=False) as audit:
            xyz = audit['designed_xyz_m']
        xz = xyz[:, [0,1]] * [1,-1]
        ini = configparser.ConfigParser()
        ini.read(self.package / 'data/map.ini')
        p = ini['PARAMETERS']
        transform = self.meta['map_transform']
        self.assertEqual(float(p['SCALE_FACTOR']), transform['scale_factor'])
        uv = builder.pixels(xz, transform)
        actual = (xz + [float(p['X_OFFSET']), float(p['Z_OFFSET'])]) / float(p['SCALE_FACTOR'])
        np.testing.assert_allclose(actual, uv)
        self.assertTrue((uv >= 0).all() and (uv < 1024).all())
        image = imagecodecs.png_decode((self.package / 'map.png').read_bytes())
        np.testing.assert_array_equal(image, builder.draw_route(xz, transform))
        # Greater geographic north means smaller PNG row; no v001 subset/axis reversal.
        self.assertLess(uv[xyz[:,1].argmax(),1], uv[xyz[:,1].argmin(),1])
        source = imagecodecs.png_decode(builder.verified(self.meta['preview_source']))
        preview = imagecodecs.png_decode((self.package / 'ui/preview.png').read_bytes())
        np.testing.assert_array_equal(preview, source[::2, ::2])
        np.testing.assert_array_equal(imagecodecs.png_decode((self.package / 'ui/outline.png').read_bytes()),
                                     builder.draw_route(xz, builder.map_transform(xz, size=512)))

    def test_design_bytes_identical_to_v002(self):
        with np.load(io.BytesIO(builder.verified(self.meta['map_source']))) as audit:
            xyz = audit['designed_xyz_m']
        old = json.loads(builder.verified(self.scene['source_proofs']['v002_manifest']))
        r = next(r for r in old['outputs'] if r['path'].endswith('/geometry_audit.npz'))
        with np.load(io.BytesIO(builder.verified(r))) as audit:
            expected = audit['designed_xyz_m']
        self.assertEqual(xyz.dtype, expected.dtype)
        self.assertEqual(xyz.tobytes(), expected.tobytes())
        self.assertEqual(hashlib.sha256(xyz.tobytes()).hexdigest(), self.meta['designed_road_sha256'])
        self.assertTrue(self.meta['map_design_identical_v002'])

    def test_explicit_assets_only(self):
        assets = self.meta['source_assets']
        self.assertEqual(len(assets), 34)
        self.assertEqual({r['path'] for r in assets},
                         {'exports/full_track_v003/' + n for n in (installer.TRACK_ID + '.kn5', *installer.DDS)})
        self.assertEqual(assets[0]['bytes'], 124593102)
        self.assertEqual(assets[0]['sha256'], '256b714965983f71d14debed9a81609ce603a31d4d24f76ad0adbf8e730c020b')
        self.assertFalse(any('failed' in n or 'debug' in n or 'extension/' in n for n in installer.ALLOWLIST))
        self.assertEqual(sum(r['bytes'] for r in assets[1:]), 27332864)
        ini = configparser.ConfigParser()
        ini.read(self.package / 'data/surfaces.ini')
        self.assertEqual(set(ini.sections()), {f'SURFACE_{i}' for i in range(4)})
        for i in range(4):
            self.assertEqual(float(ini[f'SURFACE_{i}']['DAMPING']), 0)
            self.assertEqual(float(ini[f'SURFACE_{i}']['SIN_HEIGHT']), 0)
            self.assertEqual(float(ini[f'SURFACE_{i}']['VIBRATION_GAIN']), 0)

    def test_role_counts_and_static_evidence(self):
        v = self.meta['validation']
        self.assertEqual(v['role_nodes'], dict(visual_only=914, upward_contact_skin=292, inward_open_wall=132))
        self.assertEqual(v['role_triangles']['upward_contact_skin'], 580254)
        self.assertEqual(v['role_triangles']['inward_open_wall'], 32624)
        self.assertTrue(v['top_only_ground'] and v['role_flags_verified'] and v['helpers_identical_v002'])
        self.assertEqual(len(installer.DDS), 33)
        self.assertEqual(sum('ortho' in n for n in installer.DDS), 26)
        self.assertEqual(self.meta['timing']['finish_runout_to_source_endpoint_m'], 300)
        self.assertFalse(self.meta['timing']['runtime_verified'])
        audit = json.loads(builder.verified(self.meta['ground_audit']))
        self.assertEqual(audit['overlap']['positive_pairs'], 0)
        self.assertEqual(audit['inverted'], 0)
        self.assertTrue(audit['triangles_upward'])

    def test_fresh_outputs_required(self):
        with self.assertRaises(ValueError):
            builder.build()


class ModelRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = json.loads(builder.SCENE.read_text())
        cls.data = (installer.PACKAGE / (installer.TRACK_ID + '.kn5')).read_bytes()
        cls.standalone = {n: (installer.PACKAGE / 'texture' / n).read_bytes() for n in installer.DDS}
        cls.model = builder.parse(cls.data, max_file=256*1024*1024, max_nodes=4096,
                                  max_texture=8*1024*1024, max_materials=128, max_textures=128)

    @classmethod
    def tearDownClass(cls):
        del cls.model, cls.data, cls.standalone

    def validate(self):
        with patch.object(builder, 'parse', return_value=self.model):
            return builder.validate_model(self.data, self.scene, self.standalone)

    def test_actual_model_role_contract(self):
        self.assertTrue(self.validate()['role_flags_verified'])

    def test_legacy_defaults_refuse_33_textures(self):
        with self.assertRaises(ValueError):
            builder.parse(self.data, max_file=256*1024*1024, max_nodes=4096, max_texture=8*1024*1024)

    def test_wall_flags_regression(self):
        wall = next(n for n in self.model['nodes'] if n['name'].startswith('1WALL_'))
        for key in ('renderable', 'cast_shadows', 'active', 'visible', 'transparent', 'layer'):
            old = wall[key]
            try:
                wall[key] = 1 - old
                with self.subTest(flag=key), self.assertRaisesRegex(ValueError, 'Role-specific flags'):
                    self.validate()
            finally:
                wall[key] = old

    def test_ground_must_not_gain_vertical_caps_or_inversion(self):
        ground = next(n for n in self.model['nodes'] if n['name'].startswith('1ROAD_'))
        old = ground['indices']
        try:
            ground['indices'] = old[:, ::-1]
            with self.assertRaisesRegex(ValueError, 'Non-TOP'):
                self.validate()
        finally:
            ground['indices'] = old

    def test_embedded_texture_mismatch(self):
        name = installer.DDS[0]
        old = self.standalone[name]
        try:
            self.standalone[name] = b'not the embedded DDS'
            with self.assertRaisesRegex(ValueError, 'Embedded/standalone'):
                self.validate()
        finally:
            self.standalone[name] = old

    def test_helper_transform_regression(self):
        helper = next(n for n in self.model['nodes'] if n['name'] == 'AC_PIT_0')
        old = helper['matrix']
        try:
            helper['matrix'] = np.zeros(16)
            with self.assertRaisesRegex(ValueError, 'Helper transform'):
                self.validate()
        finally:
            helper['matrix'] = old


if __name__ == '__main__':
    unittest.main()
