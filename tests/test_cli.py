import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
import zipfile


class TimeRangeTest(unittest.TestCase):
    def test_minutes_are_converted_to_replay_ticks(self):
        self.assertIsNotNone(importlib.util.find_spec("flashback_agent"), "CLI package is not implemented")
        from flashback_agent import parse_range
        self.assertEqual(parse_range("03:00-05:00"), (3600, 6000))

    def test_rejects_invalid_or_subtick_times(self):
        from flashback_agent import parse_range
        for value in ("05:00-03:00", "0-NaN", "0-1.001", "1:60-3:00", "0-0", "-1-3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_range(value)


class QueueTest(unittest.TestCase):
    def test_terminal_result_takes_priority_over_stale_progress(self):
        from flashback_agent import read_status
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "status.json").write_text('{"state":"sampling"}')
            (root / "result.json").write_text('{"state":"completed","frames":60}')
            self.assertEqual(read_status(root)["state"], "completed")

    def test_submits_validated_request_and_reads_terminal_failure(self):
        import flashback_agent as api
        self.assertTrue(hasattr(api, "submit_job"), "Job submission is not implemented")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay = root / "replay.zip"
            with zipfile.ZipFile(replay, "w") as archive:
                archive.writestr("metadata.json", json.dumps({"version_string": "26.2", "total_ticks": 223}))
            job = api.submit_job(root, replay, "00:01-00:03", "PlayerA", root / "clip.mp4")
            request = json.loads((job / "request.json").read_text())
            self.assertEqual((request["startTick"], request["endTick"]), (20, 60))
            self.assertEqual(request["target"], "PlayerA")
            (job / "status.json").write_text(json.dumps({"state": "failed", "error": "Target not recorded"}))
            self.assertEqual(api.wait_job(job, timeout=0.1)["error"], "Target not recorded")
            with self.assertRaises(ValueError):
                api.submit_job(root, replay, "03:00-05:00", "PlayerA", root / "other.mp4")
            (root / "clip.mp4").write_bytes(b"existing video")
            with self.assertRaises(FileExistsError):
                api.submit_job(root, replay, "0-2", "PlayerA", root / "clip.mp4")


class CliProcessTest(unittest.TestCase):
    def test_inspect_command_returns_machine_readable_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            replay = Path(directory) / "한글 replay.zip"
            with zipfile.ZipFile(replay, "w") as archive:
                archive.writestr("metadata.json", json.dumps({"version_string": "26.2", "total_ticks": 223}))
            result = subprocess.run([sys.executable, "-m", "flashback_agent", "inspect", str(replay)],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["durationSeconds"], 11.15)


if __name__ == "__main__":
    unittest.main()
