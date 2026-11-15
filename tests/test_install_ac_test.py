"""Installer writes are confined to temporary fake game trees."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install_ac_test as installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.game = self.root / 'game'
        self.tracks = self.game / 'content/tracks'
        self.tracks.mkdir(parents=True)
        self.package = self.root / 'package'
        self.package.mkdir()
        self.manifest = self.root / 'manifest.json'
        self.meta = dict(schema='ac_test_package_v1', track_id=installer.TRACK_ID, files=[])
        for name in sorted(installer.ALLOWLIST):
            data = ('fixture:' + name).encode()
            p = self.package / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            self.meta['files'].append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        self.meta.update(file_count=len(self.meta['files']), bytes=sum(r['bytes'] for r in self.meta['files']))
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.meta))

    def run_install(self, commit=False, game=None):
        return installer.install(self.package, self.manifest, game or self.game, commit=commit)

    def test_dry_run_no_writes(self):
        result = self.run_install()
        self.assertEqual(result['mode'], 'DRY_RUN')
        self.assertEqual(list(self.tracks.iterdir()), [])

    def test_install_and_existing_refusal(self):
        unrelated = self.tracks / 'other'
        unrelated.write_text('preserve')
        result = self.run_install(True)
        self.assertEqual(result['mode'], 'INSTALL')
        target = self.tracks / installer.TRACK_ID
        self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}, installer.ALLOWLIST)
        with self.assertRaises(FileExistsError):
            self.run_install(True)
        self.assertEqual(unrelated.read_text(), 'preserve')
        self.assertEqual({p.name for p in self.tracks.iterdir()}, {'other', installer.TRACK_ID})

    def test_tamper(self):
        (self.package / 'models.ini').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'hash/size'):
            self.run_install(True)
        self.assertEqual(list(self.tracks.iterdir()), [])

    def test_manifest_traversal_and_absolute(self):
        for bad in ('../escape', '/tmp/escape', 'ui/../escape', 'ui\\escape', 'ui//escape'):
            with self.subTest(bad=bad):
                self.meta['files'][0]['path'] = bad
                self.save()
                with self.assertRaises(ValueError):
                    self.run_install(True)
        self.assertEqual(list(self.tracks.iterdir()), [])

    def test_allowlist_extra_missing_duplicate(self):
        for change in ('extra', 'missing', 'duplicate'):
            original = list(self.meta['files'])
            if change == 'extra':
                self.meta['files'].append(dict(path='evil.py', bytes=0, sha256='0'*64))
            elif change == 'missing':
                self.meta['files'].pop()
            else:
                self.meta['files'].append(self.meta['files'][0])
            self.save()
            with self.assertRaises(ValueError):
                self.run_install(True)
            self.meta['files'] = original

    def test_extra_source(self):
        (self.package / 'unlisted').write_text('no')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.run_install(True)

    def test_source_file_and_directory_symlinks(self):
        for path in (self.package / 'models.ini', self.package / 'ui'):
            with self.subTest(path=path):
                moved = self.root / (path.name + '.original')
                path.rename(moved)
                path.symlink_to(moved, target_is_directory=moved.is_dir())
                with self.assertRaisesRegex(ValueError, 'Symlink'):
                    self.run_install(True)
                path.unlink()
                moved.rename(path)

    def test_destination_symlink_including_dangling(self):
        target = self.tracks / installer.TRACK_ID
        target.symlink_to(self.root / 'does-not-exist')
        with self.assertRaises(FileExistsError):
            self.run_install(True)
        self.assertTrue(target.is_symlink())

    def test_tracks_and_content_symlink_refused(self):
        for path in (self.tracks, self.game / 'content'):
            with self.subTest(path=path):
                moved = self.root / (path.name + '.original')
                path.rename(moved)
                path.symlink_to(moved, target_is_directory=True)
                with self.assertRaises(OSError):
                    self.run_install(True)
                path.unlink()
                moved.rename(path)

    def test_existing_game_root_symlink_permitted(self):
        alias = self.root / 'steam-alias'
        alias.symlink_to(self.game, target_is_directory=True)
        self.assertEqual(self.run_install(game=alias)['mode'], 'DRY_RUN')

    def test_preexisting_stage_symlink_not_followed_or_removed(self):
        class FixedUUID:
            hex = 'fixed'
        stage = self.tracks / ('.' + installer.TRACK_ID + '.stage-fixed')
        victim = self.root / 'victim'
        victim.mkdir()
        stage.symlink_to(victim, target_is_directory=True)
        with patch.object(installer.uuid, 'uuid4', return_value=FixedUUID()):
            with self.assertRaises(FileExistsError):
                self.run_install(True)
        self.assertTrue(stage.is_symlink())
        self.assertEqual(list(victim.iterdir()), [])

    def test_stage_child_symlink_not_followed(self):
        original = installer.os.mkdir
        victim = self.root / 'victim'
        victim.mkdir()
        (victim / 'keep').write_text('keep')
        def inject(path, *args, **kwargs):
            if path == 'ui' and 'dir_fd' in kwargs:
                installer.os.symlink(str(victim), 'ui', dir_fd=kwargs['dir_fd'])
            return original(path, *args, **kwargs)
        with patch.object(installer.os, 'mkdir', side_effect=inject):
            with self.assertRaises(FileExistsError):
                self.run_install(True)
        self.assertEqual((victim / 'keep').read_text(), 'keep')
        self.assertEqual(list(self.tracks.iterdir()), [])

    def test_copy_failure_rolls_back_own_partial(self):
        original = installer.read_at
        calls = 0
        def fail_during_stage(fd, name):
            nonlocal calls
            calls += 1
            if calls > len(installer.ALLOWLIST) + 1:
                raise OSError('injected readback failure')
            return original(fd, name)
        unrelated = self.tracks / 'other'
        unrelated.write_text('keep')
        with patch.object(installer, 'read_at', side_effect=fail_during_stage):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.run_install(True)
        self.assertEqual(list(self.tracks.iterdir()), [unrelated])
        self.assertEqual(unrelated.read_text(), 'keep')

    def test_atomic_publish_failure_rolls_back_own_partial(self):
        with patch.object(installer, 'rename_new', side_effect=OSError('injected publish failure')):
            with self.assertRaises(OSError):
                self.run_install(True)
        self.assertEqual(list(self.tracks.iterdir()), [])

    def test_racing_destination_not_overwritten(self):
        original = installer.rename_new
        def race(fd, source, destination):
            (self.tracks / destination).mkdir()
            (self.tracks / destination / 'keep').write_text('other process')
            return original(fd, source, destination)
        with patch.object(installer, 'rename_new', side_effect=race):
            with self.assertRaises(FileExistsError):
                self.run_install(True)
        self.assertEqual((self.tracks / installer.TRACK_ID / 'keep').read_text(), 'other process')
        self.assertEqual(len(list(self.tracks.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
