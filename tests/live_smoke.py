"""Opt-in real Minecraft smoke test. Never counted as a passing mocked render."""
import argparse
import json
from pathlib import Path
import subprocess

from flashback_agent import bridge_health, submit_job, wait_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bridge_health(args.game_dir)
    discovery = submit_job(args.game_dir, args.replay, "00:01-00:03", operation="players")
    players = wait_job(discovery, timeout=180)
    assert players["state"] == "completed", players
    assert players["players"], players
    target = players["players"][0]["uuid"]
    job = submit_job(args.game_dir, args.replay, "00:01-00:03", target, args.output,
                     width=640, height=360, fps=30)
    result = wait_job(job, timeout=300, on_progress=lambda s: print(json.dumps(s), flush=True))
    assert result["state"] == "completed", result
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(args.output)],
                           check=True, capture_output=True, text=True)
    media = json.loads(probe.stdout)
    video = next(s for s in media["streams"] if s["codec_type"] == "video")
    assert video["width"] == 640 and video["height"] == 360, video
    assert video["codec_name"] == "h264", video
    assert abs(float(media["format"]["duration"]) - 2) < .08, media
    assert int(video["nb_frames"]) == 60, video
    print(json.dumps({"verified": True, "job": job.name, "video": video}, ensure_ascii=False))


if __name__ == "__main__":
    main()
