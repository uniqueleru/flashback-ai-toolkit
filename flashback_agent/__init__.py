"""Flashback Agent's dependency-free public Python API."""
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import time
import uuid
import zipfile
from .plans import validate_plan, look_at

TERMINAL = {"completed", "failed", "cancelled"}


def read_json(path):
    """Retry a brief Windows sharing violation during the bridge's atomic replace.

    Only the observation is retried; tool submissions/actions are never repeated.
    """
    for attempt in range(21):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8'))
        except PermissionError:
            if attempt == 20:
                raise
            time.sleep(.025)


def atomic_json(path: Path, value: dict):
    path = Path(path)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def inspect_replay(path) -> dict:
    """Read bounded metadata without extracting the replay or its paths."""
    with zipfile.ZipFile(Path(path)) as archive:
        entry = archive.getinfo("metadata.json")
        if entry.file_size > 1024 * 1024:
            raise ValueError("Replay metadata exceeds 1 MiB")
        metadata = json.loads(archive.read(entry))
    ticks = metadata.get("total_ticks")
    if type(ticks) is not int or not 0 < ticks <= 2147483646:
        raise ValueError("Replay metadata has invalid total_ticks")
    return metadata


def submit_job(game_dir, replay, source_range, target=None, output=None, *,
               operation="render", width=1920, height=1080, fps=60,
               distance=None, side=None, height_offset=None, audio=False,
               plan=None, sample_interval_ticks=20) -> Path:
    """Submit a render, entity sample or player query to the local file inbox."""
    game_dir = Path(game_dir).resolve(strict=True)
    replay = Path(replay).resolve(strict=True)
    metadata = inspect_replay(replay)
    bridge = game_dir / "flashback-agent" / "bridge.json"
    running = read_json(bridge).get("minecraft") if bridge.is_file() else None
    if running and metadata.get("version_string") != running:
        raise ValueError(f"Replay was recorded in Minecraft {metadata.get('version_string')}; this client runs {running}")
    start, end = parse_range(source_range)
    if end > metadata["total_ticks"]:
        raise ValueError(f"Requested range exceeds replay duration ({metadata['total_ticks'] / 20:g}s)")
    if operation not in {"render", "players", "sample"}:
        raise ValueError("Unknown operation")
    if type(sample_interval_ticks) is not int or not 1 <= sample_interval_ticks <= 200:
        raise ValueError('Sample interval must be 1..200 ticks')
    if plan is not None:
        if operation != 'render' or target is not None:
            raise ValueError('Explicit camera plans do not take a follow target')
        if any(value is not None for value in (distance, side, height_offset)):
            raise ValueError('Follow options cannot modify an explicit camera plan')
        plan = validate_plan(plan, start, end)
    distance = 5.0 if distance is None else distance
    side = 2.0 if side is None else side
    height_offset = 2.5 if height_offset is None else height_offset
    if operation == "render":
        if (plan is None and (not target or not target.strip())) or output is None:
            raise ValueError("Render requires a camera plan or a legacy follow target, and an output path")
        output = Path(output).resolve()
        if output.suffix.lower() != ".mp4":
            raise ValueError("Output must have an .mp4 extension")
        if output.exists():
            raise FileExistsError(f"Output already exists: {output}")
        if any(type(n) is not int or n < 64 or n > 4096 or n % 2 for n in (width, height)):
            raise ValueError("Dimensions must be even integers between 64 and 4096")
        if fps not in (24, 30, 60):
            raise ValueError("FPS must be 24, 30 or 60")
        for name, value, low, high in (("distance", distance, 2, 16), ("side", side, -8, 8), ("height", height_offset, 0.5, 10)):
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
    job = game_dir / "flashback-agent" / "jobs" / uuid.uuid4().hex
    job.mkdir(parents=True)
    atomic_json(job / "request.json", {
        "schemaVersion": 2, "id": job.name, "operation": operation,
        "replay": str(replay), "startTick": start, "endTick": end,
        "target": target, "output": str(output) if output else None,
        "width": width, "height": height, "fps": fps,
        "distance": distance, "side": side, "heightOffset": height_offset,
        "audio": bool(audio), "plan": plan, "sampleIntervalTicks": sample_interval_ticks,
    })
    return job


def read_status(job) -> dict:
    path = Path(job) / "result.json"
    if not path.exists():
        path = Path(job) / "status.json"
    if not path.exists():
        return {"state": "queued", "id": Path(job).name}
    return read_json(path)


def wait_job(job, *, timeout=1800, poll=0.5, on_progress=None) -> dict:
    deadline = time.monotonic() + timeout
    previous = None
    while True:
        status = read_status(job)
        if status != previous and on_progress:
            on_progress(status)
        if status.get("state") in TERMINAL:
            return status
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Still {status.get('state')}; job continues. Inspect with status/wait: {Path(job).name}")
        previous = status
        time.sleep(min(poll, max(0, deadline - time.monotonic())))


def cancel_job(job):
    job = Path(job)
    if not (job / "request.json").is_file():
        raise ValueError("Unknown job")
    atomic_json(job / "cancel.json", {"cancel": True})


def bridge_health(game_dir) -> dict:
    path = Path(game_dir) / "flashback-agent" / "bridge.json"
    if not path.is_file():
        raise RuntimeError("Bridge not found. Install the bridge JAR and start this Minecraft profile.")
    health = read_json(path)
    if time.time() * 1000 - health.get("updatedAt", 0) > 15000:
        raise RuntimeError("Bridge heartbeat is stale. Start/restart this Minecraft profile.")
    if health.get('protocolVersion', 0) < 2:
        raise RuntimeError('Bridge update required: install Flashback Agent 0.2.0+ and restart Minecraft')
    return health


def parse_range(value: str) -> tuple[int, int]:
    """Parse seconds, MM:SS or HH:MM:SS into source replay ticks (20 Hz)."""
    def tick(text):
        parts = text.split(":")
        if not 1 <= len(parts) <= 3:
            raise ValueError("Time must be seconds, MM:SS or HH:MM:SS")
        try:
            nums = [Decimal(p) for p in parts]
            if any(not n.is_finite() or n < 0 for n in nums):
                raise ValueError("Time must be finite and non-negative")
            if any(n != n.to_integral_value() for n in nums[:-1]):
                raise ValueError("Only seconds may be fractional")
            if len(nums) > 1 and any(n >= 60 for n in nums[1:]):
                raise ValueError("Seconds/minutes component must be below 60")
            seconds = sum(n * 60 ** i for i, n in enumerate(reversed(nums)))
            ticks = seconds * 20
            if ticks != ticks.to_integral_value():
                raise ValueError("Times must align to 0.05-second replay ticks")
            if ticks > 2147483646:
                raise ValueError("Time exceeds the replay tick limit")
            return int(ticks)
        except InvalidOperation as exc:
            raise ValueError("Invalid time") from exc
    try:
        start, end = value.split("-")
    except ValueError as exc:
        raise ValueError("Range must be START-END, e.g. 03:00-05:00") from exc
    start, end = tick(start), tick(end)
    if end <= start:
        raise ValueError("End must be after start")
    return start, end
