# Camera and edit schemas

## Camera plan

A plan is JSON. Coordinates are Minecraft world-space coordinates and ticks are absolute source replay ticks (20 per second), not output-relative time.

```json
{
  "version": 1,
  "name": "Optional shot label",
  "speed": 1,
  "visuals": {"nametags": false, "chat": false, "hotbar": false},
  "camera": [
    {"tick": 1200, "position": [10, 80, -10], "lookAt": [0, 70, 0],
     "roll": 0, "fov": 55, "interpolation": "ease_in_out"},
    {"tick": 1400, "position": [18, 84, 4], "yaw": -90, "pitch": 20,
     "roll": 8, "fov": 70, "interpolation": "ease_in_out"}
  ]
}
```

Supply 1–10,000 camera keys in strictly increasing nonnegative integer tick order. A single key produces a static camera over the requested range. Multiple keys must cover the entire range, including the end boundary used for interpolation. Unknown fields are rejected rather than silently ignored. No entity target is required.

Each key has `position` and either `lookAt` or both `yaw` and `pitch`. `lookAt` resolves to orientation at that key, not a persistent tracking constraint; add keys where a moving look-at point or path requires them. Coincident camera/look-at points are invalid. Yaw zero faces +Z, yaw −90 faces +X, and positive pitch looks down. Angles, FOV and roll are in degrees. Optional defaults are roll 0, FOV 70, interpolation `linear`. FOV is 1–170; pitch is −90–90. Position components must be finite and within ±30,000,000.

Interpolation choices map to Flashback's native types: `linear`, `smooth`, `ease_in`, `ease_out`, `ease_in_out`, `hold`, `hermite`. Native angular interpolation may take the shorter route; use intermediate keys to express large rotations. Curved interpolation can overshoot between keys, so preview paths near geometry.

The plan is the camera authority. The bridge does not add tracking, procedural motion, stabilization or collision offsets. When deriving keys from samples, decide what information to use according to the brief. Stable vertical framing, for example, might use a world-space height or a separately filtered trajectory; other requests may intentionally retain the subject's motion.

`speed` defaults to 1 and ranges from 0.1 to 8. Source ticks and camera keys remain in source time. Frame count is `ceil((endTick-startTick)*fps/(20*speed))`; output duration is that count divided by FPS. Native audio can be enabled by the render command. Validate altered-speed audio if its timing or quality matters.

`visuals` exposes only `nametags`, `chat`, and `hotbar` booleans; omitted flags render false. Other visual settings depend on the running profile and are not accepted as arbitrary JSON fields.

Validate a file with `python -m flashback_agent validate-plan camera.json --range 01:00-01:10`. The result normalizes look-at orientations without changing supplied positions or inventing keys. The Python API is also available:

```python
from flashback_agent import look_at, validate_plan, submit_job, wait_job

orientation = look_at([10, 80, -10], [0, 70, 0])  # {"yaw": ..., "pitch": ...}
plan = validate_plan("camera.json", 1200, 1400)
job = submit_job(profile, replay, "01:00-01:10", output="clip.mp4", plan=plan, fps=30)
result = wait_job(job, timeout=1800)
```

## Ordered edit

```json
{
  "version": 1,
  "replay": "session.zip",
  "render": {"width": 1920, "height": 1080, "fps": 30, "audio": false},
  "shots": [
    {"name": "Later moment first", "range": "01:00-01:10", "plan": "camera.json"},
    {"range": "00:10-00:12", "plan": {
      "version": 1, "camera": [
        {"tick": 200, "position": [10, 80, -10], "lookAt": [0, 70, 0]}
      ]
    }}
  ]
}
```

`shots` accepts 1–100 entries in the intended output order, which need not be chronological. Each shot requires a range and a plan object or path. It can override the common `replay` with a different replay path. All relative replay/plan paths resolve against the edit file's directory. `render` settings apply to every shot and default to 1920×1080, 60 FPS, no audio. Each plan can have its own speed. `name` is an optional organizational label.

Validate with `python -m flashback_agent validate-edit edit.json`, then execute `sequence --edit edit.json --output NEW.mp4 --work-dir NEW_DIR` with the chosen profile. This format describes cuts between rendered shots; it is not a complete nonlinear-editor project schema.
