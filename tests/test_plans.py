import json
from pathlib import Path
import tempfile
import unittest
import zipfile


class PlanTest(unittest.TestCase):
    def test_cli_allows_plan_without_target_and_requires_explicit_render_method(self):
        from flashback_agent.cli import parser
        cli = parser()
        args = cli.parse_args(['preview', '--replay', 'world.zip', '--range', '1-3', '--plan', 'camera.json', '--output', 'p.mp4'])
        self.assertIsNone(args.target)
        self.assertEqual((args.width, args.height, args.fps), (640, 360, 24))
        with self.assertRaises(SystemExit):
            cli.parse_args(['render', '--replay', 'world.zip', '--range', '1-3', '--target', 'Player', '--output', 'p.mp4'])

    def test_world_camera_can_render_without_a_player_or_follow_style(self):
        from flashback_agent import submit_job
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay = root / 'world.zip'
            with zipfile.ZipFile(replay, 'w') as archive:
                archive.writestr('metadata.json', json.dumps({'version_string': '26.2', 'total_ticks': 200}))
            plan = {'version': 1, 'camera': [
                {'tick': 20, 'position': [0, 80, -10], 'lookAt': [0, 70, 0], 'fov': 55},
                {'tick': 60, 'position': [10, 85, -10], 'lookAt': [0, 70, 0], 'roll': 8, 'fov': 45},
            ]}
            job = submit_job(root, replay, '1-3', output=root/'world.mp4', plan=plan)
            request = json.loads((job/'request.json').read_text())
            self.assertIsNone(request['target'])
            self.assertEqual(request['plan']['camera'][1]['position'], [10, 85, -10])
            self.assertEqual(request['plan']['camera'][1]['roll'], 8)
            self.assertEqual(request['plan']['camera'][0]['yaw'], 0)
            self.assertAlmostEqual(request['plan']['camera'][0]['pitch'], 45)
            # Follow-only options must never be silently ignored on an authored plan.
            with self.assertRaisesRegex(ValueError, 'Follow options'):
                submit_job(root, replay, '1-3', output=root/'other.mp4', plan=plan, distance=8)

    def test_unsupported_or_incomplete_intent_is_rejected_without_mutating_input(self):
        import copy
        from flashback_agent import validate_plan
        plan = {'version': 1, 'camera': [
            {'tick': 20, 'position': [0, 80, -10], 'lookAt': [0, 70, 0]},
            {'tick': 40, 'position': [10, 80, -10], 'lookAt': [0, 70, 0]},
        ]}
        original = copy.deepcopy(plan)
        with self.assertRaisesRegex(ValueError, 'cover'):
            validate_plan(plan, 20, 60)
        self.assertEqual(plan, original)
        plan['camera'][0]['subjectLock'] = 'Player'
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            validate_plan(plan)


if __name__ == '__main__':
    unittest.main()
