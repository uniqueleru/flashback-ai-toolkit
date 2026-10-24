from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from flashback_agent import bridges, launchers
import fixtures
from fixtures import LOADER, MINECRAFT


class LauncherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        environment = patch.dict(os.environ, {'FLASHBACK_CLIPS_HOME': str(self.root/'home'), 'APPDATA': str(self.root/'appdata'),
                                              'LOCALAPPDATA': str(self.root/'local')})
        environment.start()
        self.addCleanup(environment.stop)
        build = fixtures.fake_bridges(self.root)
        build.__enter__()
        self.addCleanup(build.__exit__, None, None, None)

    def test_modrinth_profile_uses_its_fabric_and_bundled_java(self):
        found = launchers.detect(fixtures.modrinth(self.root))
        self.assertEqual(found['launcher'], 'modrinth')
        self.assertEqual(launchers.choose_minecraft(found), MINECRAFT)  # from the profile's Fabric log
        spec = launchers.resolve(found, MINECRAFT)
        self.assertEqual((spec['fabric'], spec['javaMajor']), (LOADER, 21))
        self.assertIn('jre21', spec['java'])
        self.assertTrue(spec['classpath'][-1].endswith(f'{MINECRAFT}-{LOADER}.jar'))

    def test_official_launcher_merges_fabric_with_its_vanilla_parent(self):
        found = launchers.detect(fixtures.official(self.root))
        self.assertEqual(found['launcher'], 'official')
        spec = launchers.resolve(found, MINECRAFT)
        names = [Path(path).name for path in spec['classpath']]
        self.assertEqual(names[0], f'fabric-loader-{LOADER}.jar')  # Fabric's libraries come before vanilla's
        self.assertIn('brigadier-1.0.jar', names)
        self.assertEqual(names[-1], f'{MINECRAFT}.jar')
        self.assertEqual(spec['assetIndex'], '7')
        self.assertIn('java-runtime-test', spec['java'])

    def test_unsupported_and_undetectable_versions_are_reported(self):
        source = fixtures.modrinth(self.root, minecraft='9.8')
        found = launchers.detect(source)
        with self.assertRaisesRegex(ValueError, f'Supported versions: {MINECRAFT}'):
            launchers.resolve(found, launchers.choose_minecraft(found))
        (source/'logs/latest.log').unlink()
        with self.assertRaisesRegex(ValueError, '--minecraft-version'):
            launchers.choose_minecraft(found)
        with self.assertRaisesRegex(ValueError, 'neither a Modrinth profile'):
            launchers.detect(self.root)

    def test_missing_fabric_is_downloaded_for_the_worker_only_with_the_flag(self):
        game = fixtures.official(self.root, fabric=False)
        found = launchers.detect(game)
        with self.assertRaisesRegex(ValueError, '--install-fabric'):
            launchers.resolve(found, MINECRAFT)
        payload = b'fabric loader'
        library = {'name': f'net.fabricmc:fabric-loader:{LOADER}', 'url': 'https://maven.example/',
                   'sha512': hashlib.sha512(payload).hexdigest()}
        meta = {f'{launchers.FABRIC_META}/{MINECRAFT}': [
                    {'loader': {'version': '0.31.0', 'stable': False}}, {'loader': {'version': LOADER, 'stable': True}},
                    {'loader': {'version': '0.29.9', 'stable': True}}],
                f'{launchers.FABRIC_META}/{MINECRAFT}/{LOADER}/profile/json': {
                    'inheritsFrom': MINECRAFT, 'mainClass': launchers.KNOT, 'libraries': [library]}}

        def download(url, target, sha512, check=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            return target
        with patch.object(launchers, '_json', side_effect=lambda url: meta[url]), \
             patch.object(bridges, 'download', side_effect=download) as fetched:
            spec = launchers.resolve(found, MINECRAFT, install_fabric=True, cache=self.root/'home')
        # 0.31.0 is not stable and 0.29.9 is below the bridge's minimum 0.30.0.
        self.assertEqual(spec['fabric'], LOADER)
        self.assertEqual(fetched.call_args.args[0], f'https://maven.example/net/fabricmc/fabric-loader/{LOADER}/fabric-loader-{LOADER}.jar')
        self.assertTrue(spec['classpath'][0].startswith(str(self.root/'home'/'libraries')))
        self.assertEqual([p.name for p in (game/'versions').iterdir()], [MINECRAFT])  # the launcher is unchanged
        del library['sha512']
        with patch.object(launchers, '_json', side_effect=lambda url: meta[url]):
            with self.assertRaisesRegex(ValueError, 'unverified'):
                launchers.resolve(found, MINECRAFT, install_fabric=True, cache=self.root/'other')

    def test_forge_mods_are_refused_for_a_fabric_worker(self):
        game = fixtures.official(self.root)
        with zipfile.ZipFile(game/'mods/forge-only.jar', 'w') as archive:
            archive.writestr('META-INF/neoforge.mods.toml', '')
        with self.assertRaisesRegex(ValueError, 'Forge/NeoForge'):
            launchers.resolve(launchers.detect(game), MINECRAFT)

    def test_sources_offer_default_and_custom_modrinth_folders_and_the_official_launcher(self):
        fixtures.modrinth(self.root/'appdata', app='ModrinthApp', profile='default')
        custom = fixtures.modrinth(self.root/'drive', app='modrinth', profile='custom', minecraft='9.8')
        with closing(sqlite3.connect(self.root/'appdata/ModrinthApp/app.db')) as db, db:
            db.execute('CREATE TABLE settings (custom_dir TEXT)')
            db.execute('INSERT INTO settings VALUES (?)', (str(custom.parent.parent),))
        fixtures.official(self.root/'appdata')
        listed = {Path(item['path']).name: item for item in launchers.sources()['sources']}
        self.assertEqual(set(listed), {'default', 'custom', '.minecraft'})
        self.assertEqual((listed['default']['launcher'], listed['default']['bridge']), ('modrinth', True))
        self.assertEqual((listed['custom']['lastLaunched'], listed['custom']['bridge']), ('9.8', False))
        self.assertEqual(listed['.minecraft']['launcher'], 'official')


if __name__ == '__main__':
    unittest.main()
