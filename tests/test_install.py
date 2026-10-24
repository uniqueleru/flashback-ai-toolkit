import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from flashback_agent import bridges, install, runtime
import fixtures
from fixtures import MINECRAFT


class DependencyTests(unittest.TestCase):
    def test_corrupt_download_does_not_replace_cache_or_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            old = cache/'mod.jar'
            old.write_bytes(b'old')
            spec = {'id': 'carpet', 'file': 'mod.jar', 'url': 'https://example.invalid/mod.jar', 'sha512': '0'*128}
            with patch.object(bridges.urllib.request, 'urlopen', return_value=io.BytesIO(b'corrupted')):
                with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                    bridges.fetch_dependency(spec, cache)
            self.assertEqual(old.read_bytes(), b'old')
            self.assertEqual(list(cache.glob('*.part')), [])

    def test_matching_existing_artifact_avoids_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = fixtures.jar(root/'source.jar', 'carpet')
            spec = {'id': 'carpet', 'file': 'carpet.jar', 'url': 'https://example.invalid', 'sha512': fixtures.sha512(path)}
            with patch.object(bridges.urllib.request, 'urlopen') as network:
                self.assertEqual(bridges.fetch_dependency(spec, root/'cache', [path]), path)
                network.assert_not_called()


class WorkerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        environment = patch.dict(os.environ, {'FLASHBACK_CLIPS_HOME': str(self.root/'home')})
        environment.start()
        self.addCleanup(environment.stop)
        build = fixtures.fake_bridges(self.root)
        build.__enter__()
        self.addCleanup(build.__exit__, None, None, None)

    def test_prepare_replaces_pinned_mods_in_clone_preserves_source_and_retries(self):
        source = fixtures.modrinth(self.root)
        old = fixtures.jar(source/'mods/old-flashback.jar', 'flashback', 'old')
        old_bytes = old.read_bytes()
        worker = self.root/'worker'
        result = runtime.prepare(source, worker)
        self.assertEqual((result['sourceProfile'], result['minecraft'], result['launcher']), (str(source), MINECRAFT, 'modrinth'))
        self.assertEqual(old.read_bytes(), old_bytes)
        self.assertFalse((worker/'mods/old-flashback.jar').exists())
        self.assertTrue((worker/'mods/appearance.jar').is_file())
        self.assertEqual({runtime.mod_info(p)['id'] for p in (worker/'mods').glob('*.jar')},
                         {'appearance', 'flashback', 'fabric-api', 'carpet', 'flashback_agent', 'carpet_agent'})
        self.assertIn('fullscreen:false', (worker/'options.txt').read_text())
        with patch.object(bridges, 'fetch_dependency') as download:
            self.assertEqual(runtime.prepare(source, worker), result)
            download.assert_not_called()
        (worker/'mods'/f'carpet-agent-{runtime.VERSION}.jar').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            runtime.prepare(source, worker)

    def test_newer_fabric_api_stays_but_flashback_is_always_the_bridge_build(self):
        source = fixtures.modrinth(self.root)
        newer = fixtures.jar(source/'mods/fabric-api-newer.jar', 'fabric-api', '2.0+9.9')
        older = fixtures.jar(source/'mods/carpet-older.jar', 'carpet', '0.5')
        fixtures.jar(source/'mods/flashback-newer.jar', 'flashback', '9.0')
        worker = self.root/'worker'
        runtime.prepare(source, worker)
        mods = {p.name: runtime.mod_info(p) for p in (worker/'mods').glob('*.jar')}
        self.assertIn(newer.name, mods)                       # another mod may need this newer Fabric API
        self.assertNotIn(older.name, mods)                    # below the bridge's minimum, so replaced
        self.assertNotIn('flashback-newer.jar', mods)         # Flashback must match the bridge exactly
        self.assertEqual(sorted(m['id'] for m in mods.values()).count('fabric-api'), 1)

    def test_official_launcher_worker_uses_its_game_folder(self):
        game = fixtures.official(self.root)
        result = runtime.prepare(game, self.root/'worker')
        self.assertEqual((result['launcher'], result['fabric']), ('official', fixtures.LOADER))
        self.assertTrue((self.root/'worker/mods/appearance.jar').is_file())

    def test_incomplete_or_nested_worker_preserves_files(self):
        source = fixtures.modrinth(self.root)
        worker = self.root/'worker'
        worker.mkdir()
        (worker/'keep.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'not a completed worker'):
            runtime.prepare(source, worker)
        self.assertEqual((worker/'keep.txt').read_text(), 'keep')
        with self.assertRaisesRegex(ValueError, 'separate'):
            runtime.prepare(source, source/'child')
        self.assertFalse((source/'child').exists())


class SetupTests(unittest.TestCase):
    def test_skill_backup_and_command_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root/'skills/flashback-clips'
            target.mkdir(parents=True)
            (target/'SKILL.md').write_text('custom instructions')
            install.install_skill(target)
            backup = list((root/'skill-backups').glob('flashback-clips-*'))
            self.assertEqual(len(backup), 1)
            self.assertEqual((backup[0]/'SKILL.md').read_text(), 'custom instructions')
            text = (target/'references/runtime.md').read_text(encoding='utf-8')
            self.assertIn('flashback-clips runtime sources', text)
            self.assertNotIn('python -m flashback_agent', text)

    def test_skill_targets_follow_installed_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex, claude = root/'codex/skills/flashback-clips', root/'claude/skills/flashback-clips'
            with patch.dict(install.os.environ, {'CODEX_HOME': str(root/'codex'), 'CLAUDE_CONFIG_DIR': str(root/'claude')}):
                self.assertEqual(install.skill_dirs(), [codex, claude])
                (root/'claude').mkdir()
                self.assertEqual(install.skill_dirs(), [claude])
                self.assertEqual(install.skill_dirs('codex'), [codex])
                self.assertEqual(install.skill_dirs('both'), [codex, claude])

    def test_setup_installs_skill_and_records_media_without_touching_minecraft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.dict(install.os.environ, {'FLASHBACK_CLIPS_HOME': str(root/'home')}), \
                 patch.object(install, 'find_media_tools', return_value=[str(root/'ffmpeg')]), \
                 patch.object(runtime, 'prepare') as prepare:
                result = install.setup(skill_dir=root/'skills/flashback-clips')
                saved = install.config.load()
            prepare.assert_not_called()
            self.assertEqual(saved['mediaDirs'], [str(root/'ffmpeg')])
            self.assertNotIn('instance', saved)
            self.assertIn('runtime sources', result['next'])
            self.assertTrue((root/'skills/flashback-clips/SKILL.md').is_file())

    def test_command_defaults_to_recorded_worker_and_media_tools(self):
        with tempfile.TemporaryDirectory(prefix='한글 설치 ') as tmp:
            root = Path(tmp)
            media = root/'media tools'
            media.mkdir()
            for name in ('ffmpeg.exe', 'ffprobe.exe'):
                (media/name).touch()
            (root/'config.json').write_text(json.dumps({'instance': str(root/'작업 worker'), 'mediaDirs': [str(media)]}),
                                            encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if k != 'FLASHBACK_GAME_DIR'}
            env['FLASHBACK_CLIPS_HOME'] = str(root)
            result = subprocess.run([sys.executable, '-m', 'flashback_agent', 'doctor'], env=env,
                                    capture_output=True, encoding='utf-8', cwd=Path(__file__).resolve().parents[1])
            self.assertEqual(result.returncode, 1, result.stderr)  # no live bridge in a test
            checks = {item['name']: item for item in json.loads(result.stdout)['checks']}
            self.assertEqual(checks['ffmpeg']['detail'].lower(), str(media/'ffmpeg.exe').lower())
            self.assertIn(str(root/'작업 worker'), checks['bridge']['detail'])


if __name__ == '__main__':
    unittest.main()
