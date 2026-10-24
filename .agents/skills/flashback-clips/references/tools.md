# CLI tools and boundaries

Prefix commands below with `python -m flashback_agent`. The `flashback-clips` console command is equivalent if its Scripts directory is on PATH; `mc-broll` remains a compatibility alias. The Python package has no runtime dependencies. Minecraft and its matching bridge are needed for replay queries and renders. `review`, `assemble`, and the assembly stage of `sequence` require FFmpeg and ffprobe on PATH.

| Command | Purpose |
| --- | --- |
| `capabilities` | Inspect implemented operations and control bounds without a running game. |
| `inspect REPLAY.zip` | Read metadata and duration without a running game. |
| `doctor [--game-dir WORKER]` | Check FFmpeg, bridge builds, the skill, the worker and the live bridge; `ok` is true only when every check passes. |
| `runtime sources` | List Minecraft installations found on this PC for the user to choose from; see [runtime.md](runtime.md). |
| `runtime prepare --source PATH` | Build the worker from the installation the user chose. |
| `setup` | One-time installation, normally run by the user: installs this skill and finds FFmpeg. |
| `players --replay FILE --range START-END` | Discover player names/UUIDs at one-second intervals. |
| `sample --replay FILE --range START-END --step 10` | Sample loaded recorded entities at a chosen tick interval. |
| `validate-plan PLAN.json --range START-END` | Validate and normalize an authored camera without rendering. |
| `validate-edit EDIT.json` | Preflight every replay, range and camera in an edit. |
| `preview --replay FILE --range START-END --plan PLAN.json --output NEW.mp4` | Render a plan with defaults 640×360, 24 FPS. |
| `render --replay FILE --range START-END --plan PLAN.json --output NEW.mp4` | Render a plan with defaults 1920×1080, 60 FPS. |
| `review VIDEO.mp4 --output-dir NEW_DIR --every 0.5 --max-frames 24` | Extract chronological PNGs and media metadata for inspection. |
| `sequence --edit EDIT.json --output NEW.mp4 --work-dir NEW_DIR` | Render the supplied shot order and assemble it with cuts. |
| `assemble A.mp4 B.mp4 --output NEW.mp4` | Join compatible clips in the specified order. |
| `status JOB_ID`, `wait JOB_ID --timeout 1800`, `cancel JOB_ID` | Manage one submitted job. |

Game operations accept `--game-dir PROFILE` or the `FLASHBACK_GAME_DIR` environment variable. Paths can contain spaces and Unicode. Stdout is JSON; progress goes to stderr. Errors produce nonzero exit codes. For `players`, `sample`, `preview`, and `render`, `--submit-only` returns the job ID immediately; otherwise the CLI waits. `--timeout` bounds waiting, not job execution.

## Query results

`inspect` reports `durationSeconds` and raw metadata, including `total_ticks`. Times are source replay time at 20 ticks/s. Ranges accept seconds, `MM:SS`, or `HH:MM:SS`, including 0.05-second increments. Start is inclusive and end is exclusive for video frames; queries can also sample the end boundary for interpolation.

`sample` takes `--step` from 1 to 200 ticks and an optional exact entity name/UUID with `--target`. Omitting the target includes all currently loaded recorded entities except replay-viewer players. A completed result points to `samplesFile`; read that JSON. Each sample contains `tick`, `dimension`, and `entities` with `uuid`, `name`, `type`, `player`, `position`, `yaw`, `pitch`, and `onGround`. Sampling density is a task decision. This is not an inventory of everything that ever existed on the server or a semantic event index.

## Rendering controls

Both render commands accept `--width`, `--height`, `--fps`, and `--audio`. Dimensions are even integers from 64 to 4096; FPS is 24, 30, or 60. Portrait sizes are permitted. Audio is off unless requested. A preview renders the supplied range; it does not choose a shorter excerpt. Make an appropriate range/plan yourself when needed.

The plan specifies the camera and constant source speed. Coordinates are executed without automatic subject lock, smoothing, breathing, or collision repair. Inspect the result when visibility, clearance or motion is uncertain. Each render saves `camera-plan.json` and `camera-state.json` beside its job result. The native export uses a separate editor state and leaves the replay and its saved editor state intact.

The optional legacy path is `render ... --style dynamic-follow --target NAME_OR_UUID`. Only that generator uses `--distance`, `--side`, and `--height-offset`. These options cannot modify a `--plan`. Its camera is computed from player motion; it does not interpret a creative brief. Neither it nor an authored plan guarantees collision clearance in all intermediate frames.

## Edits and recovery

An edit defines explicit shot order, replay ranges, and plan paths or inline plans. See [plans.md](plans.md). `sequence` validates all shots before submitting the first. It records job IDs and completed clips in `WORK_DIR/sequence.json`. To continue after a waiting timeout, use the same command with `--resume` and the same edit, output, profile, and work directory. Completed shots are reused. Failed/cancelled jobs are not silently retried; inspect their error before preparing a corrected run.

`assemble` requires matching dimensions, frame rate and audio layout. It re-encodes H.264 video and AAC audio when present, preserves shot order with hard cuts, checks the final frame count, and publishes to a new output file. It does not add transitions, crop, grade or mix music. Use suitable editing tools for those operations when the brief calls for them.

## Current adapter limits

Each bridge build targets one Minecraft version (listed by `capabilities`). The worker always uses the bridge's exact Flashback build, and keeps the installation's Fabric API and Carpet when they are at least the bridge's versions. The graphical renderer and required replay registries/mods remain necessary; use the [background runtime](runtime.md) to keep its window off the user's desktop. Skin, resource-pack, shader and mod appearance comes from that worker profile. For live Carpet bots and recording, read [actors.md](actors.md); those use separate tool inboxes from replay jobs.

Use one dimension per render. Split dimension changes or discontinuities into suitable ranges. Playback speed is constant per shot, 0.1× to 8×; freezes, reverse playback and variable-speed curves are not exposed. Native audio at altered speed is not a high-quality audio time-stretch service. The bridge does not expose every Flashback UI feature or contain an LLM: scene interpretation and creative planning belong to the calling agent.
