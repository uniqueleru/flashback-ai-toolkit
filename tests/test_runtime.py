import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

from flashback_agent import launchers, runtime


class RuntimeTests(unittest.TestCase):
    def test_copy_save_refuses_live_lock_then_copies_without_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)/'world'
            world.mkdir()
            (world/'session.lock').write_bytes(b'abc')
            (world/'level.dat').write_bytes(b'fixture')
            code = 'import msvcrt,sys; f=open(sys.argv[1],"r+b"); msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1); print("locked",flush=True); input()'
            child = subprocess.Popen([sys.executable, '-c', code, str(world/'session.lock')],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'locked')
                with self.assertRaisesRegex(RuntimeError, 'Close the source world'):
                    with runtime.closed_save(world):
                        self.fail('Acquired live world lock')
            finally:
                child.communicate('\n', timeout=5)
            with runtime.closed_save(world):
                runtime.copy_tree(world, Path(tmp)/'copy', skip_session_lock=True)
            self.assertEqual((Path(tmp)/'copy/level.dat').read_bytes(), b'fixture')
            self.assertFalse((Path(tmp)/'copy/session.lock').exists())

    def test_transient_sharing_violation_retries_only_read(self):
        from flashback_agent import read_json
        with patch.object(Path, 'read_text', side_effect=[PermissionError('atomic replace'), '{"state":"ready"}']) as read:
            self.assertEqual(read_json('heartbeat.json'), {'state': 'ready'})
            self.assertEqual(read.call_count, 2)

    def test_platform_rules_and_argfile_keep_literal_paths(self):
        self.assertTrue(launchers.allowed([{'action': 'allow', 'os': {'name': 'windows'}}]))
        self.assertFalse(launchers.allowed([{'action': 'allow', 'os': {'name': 'linux'}}]))
        self.assertFalse(launchers.allowed([{'action': 'allow', 'features': {'is_demo_user': True}}]))
        self.assertFalse(launchers.allowed([{'action': 'allow'}, {'action': 'disallow', 'os': {'name': 'windows'}}]))
        self.assertEqual(launchers.library_path({'name': 'net.fabricmc:fabric-loader:0.19.3'}),
                         'net/fabricmc/fabric-loader/0.19.3/fabric-loader-0.19.3.jar')
        self.assertIn('"D:\\\\한글 경로\\\\a.jar"', runtime.java_argfile([r'D:\한글 경로\a.jar']))
        with self.assertRaises(ValueError):
            runtime.java_argfile(['x\n-javaagent:bad'])

    def test_recycled_pid_is_not_treated_as_owned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root/'.background').mkdir()
            (root/'.background/instance.json').write_text(json.dumps({'version': runtime.VERSION, 'instance': str(root)}))
            (root/'.background/process.json').write_text(json.dumps({'pid': 123, 'created': 40, 'launchId': 'old'}))
            with patch.object(runtime, 'process_identity', return_value=41), patch.object(runtime, 'window_state') as windows:
                self.assertEqual(runtime.status(root)['state'], 'stopped')
                windows.assert_not_called()

    def test_prepare_refuses_original_or_nested_profile_before_copy(self):
        import fixtures
        with tempfile.TemporaryDirectory() as tmp:
            source = fixtures.official(Path(tmp).resolve())
            for target in (source, source/'child'):
                with self.assertRaisesRegex(ValueError, 'separate'):
                    runtime.prepare(source, target)
            self.assertFalse((source/'child').exists())

    def test_stop_refuses_recording_and_never_kills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root/'.background').mkdir()
            (root/'.background/instance.json').write_text(json.dumps({'version': runtime.VERSION, 'instance': str(root)}))
            with patch.object(runtime, 'status', return_value={'state': 'running', 'launchId': 'owned'}), \
                 patch('flashback_agent.tools.call_tool', return_value={'state': 'failed', 'error': 'active recording'}) as call:
                with self.assertRaisesRegex(RuntimeError, 'active recording'):
                    runtime.stop(root)
                self.assertEqual(call.call_args.args, ('runtime_shutdown', {'launchId': 'owned'}))


if __name__ == '__main__':
    unittest.main()
