"""Opt-in failure/cancellation checks against a real running Minecraft bridge."""
import argparse
import json
from pathlib import Path
import time

from flashback_agent import bridge_health, cancel_job, read_status, submit_job, wait_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bridge_health(args.game_dir)
    outcomes = {}

    missing = args.output_dir / "missing-player.mp4"
    job = submit_job(args.game_dir, args.replay, "1-3", "__nonexistent_test_player__", missing)
    result = wait_job(job, timeout=180)
    assert result["state"] == "failed" and "Target" in result["error"], result
    assert not missing.exists()
    outcomes["missingTarget"] = result
    print(json.dumps({"missingTarget": "passed"}), flush=True)

    # Cancel only after actual rendering starts, exercising ExportJob cleanup.
    output = args.output_dir / "cancelled.mp4"
    job = submit_job(args.game_dir, args.replay, "1-9", args.target, output,
                     width=1920, height=1080, fps=60)
    deadline = time.monotonic() + 240
    while True:
        status = read_status(job)
        assert status["state"] not in {"completed", "failed", "cancelled"}, status
        if status["state"] == "rendering":
            cancel_job(job)
            break
        assert time.monotonic() < deadline, status
        time.sleep(.05)
    result = wait_job(job, timeout=60)
    assert result["state"] == "cancelled", result
    # Terminal result is published immediately before cleanup; allow the client
    # to finish that callback, then check that neither output nor partial remains.
    time.sleep(1)
    assert not output.exists()
    assert not list(args.output_dir.glob(f".{output.name}.{job.name}.partial.mp4"))
    outcomes["cancelDuringRender"] = result
    print(json.dumps({"cancelDuringRender": "passed"}), flush=True)
    # A cancellation must leave the game usable, not merely publish a status
    # before crashing on a pending GPU download callback.
    recovery = submit_job(args.game_dir, args.replay, "1-2", args.target,
                          args.output_dir / "after-cancel.mp4", width=640, height=360, fps=24,
                          audio=True)
    result = wait_job(recovery, timeout=90)
    assert result["state"] == "completed" and result["frames"] == 24, result
    outcomes["renderAfterCancellation"] = result
    print(json.dumps({"renderAfterCancellation": "passed"}), flush=True)
    (args.output_dir / "live-controls.json").write_text(json.dumps(outcomes, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
