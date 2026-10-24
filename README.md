# Flashback Clips

**English** | [한국어](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/README.ko.md)

A CLI, Python library, Fabric bridge and agent skill that inspect [Flashback](https://modrinth.com/mod/flashback) replays and turn agent-authored cameras and cuts into real MP4s. **The agent decides what to shoot and how.** Player tracking is one optional legacy tool, not the default behavior.

Depending on the request, the agent reads replay and entity data, writes camera plans in arbitrary world coordinates, reviews and revises previews, then outputs a single clip or several shots. Landscapes with no subject, static compositions, moves/rotations/zooms and shots driven by entity data are all expressed with the same tools. The tools themselves contain no LLM and no automatic highlight detector.

With the Carpet bot tools and the Flashback recording tools, an agent can compose actions from what it observes, record the result, and then direct the camera separately. `python -m flashback_agent tools` lists the descriptions and JSON Schemas of all 20 tools. The CLI, Python and the optional MCP stdio server call the same tools. Their semantics and limits are in the [Carpet tools guide](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/docs/carpet-tools.md).

**It runs in the background:** on a hidden Windows desktop, with a guard that applies before any window is created. It copies the Minecraft installation you choose into a separate worker and keeps the game, child dialogs and console windows from appearing, from taking focus or the mouse, and from playing through your speakers. See the [background runtime guide](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/docs/background-runtime.md) (Korean). The agent skill uses this path by default; scenes and camera work still follow the request freely.

## Installation

You need Windows 10/11 x64 (the background runtime is Windows-only for now) and Minecraft installed through the **Modrinth App or the official Minecraft Launcher**.

```powershell
uv tool install flashback-ai-toolkit
flashback-clips setup
```

No uv yet? Run `winget install astral-sh.uv`, or double-click `install.cmd` from this repository, which installs uv and runs both commands. uv provides Python 3.11+ itself and leaves your system Python alone. `setup` installs the skill for Codex and/or Claude Code and finds FFmpeg, installing it with WinGet if needed. It does not touch Minecraft.

### First use: you choose the Minecraft installation

The first time you ask your agent for footage, it sets up a worker with you:

1. The agent runs `flashback-clips runtime sources` and shows you the Modrinth profiles and official launcher folder it found, each with the Minecraft and Fabric versions it last launched. You pick one or give another path; the agent never picks for you.
2. `flashback-clips runtime prepare --source "<path>"` copies that installation's mods, config and resource/shader packs into a separate worker at `%LOCALAPPDATA%\FlashbackClips\worker`. Your installation is not modified. Flashback is always the exact build the bridge was compiled against; Fabric API and Carpet stay as you have them when they are at least the bridge's versions. Anything missing is downloaded and hash-checked.
3. **No Fabric in that installation?** The agent tells you and reruns with `--install-fabric`. This downloads Fabric Loader for the worker only, without changing your launcher.

The Minecraft version is detected from the installation, never fixed in the toolkit. It works with every version that has a bridge build; `flashback-clips capabilities` lists them, and other versions get a clear message. The worker uses the game files your launcher already downloaded, so launch the version you want once in your launcher first. It runs as a separate local offline observer and never reads your account tokens.

`flashback-clips doctor` reports every piece as JSON. Options and troubleshooting are in the [install guide](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/docs/install.md) (Korean).

### Manual and development installs

1. Build with `gradlew.bat build`. The Minecraft target and its Flashback, Fabric API and Carpet versions come from `gradle.properties`. Then run `python scripts/stage_bridges.py`, which copies the bridges into `flashback_agent/bin/<minecraft>/` and writes their `bridge.json`.
2. Install the CLI with `uv tool install flashback-ai-toolkit`, `python -m pip install flashback-ai-toolkit`, or `python -m pip install -e .` from a source checkout. There are no Python runtime dependencies.
3. Put FFmpeg and ffprobe on PATH for joining shots and extracting review frames.
4. Without `setup`, install `.agents/skills/flashback-clips` into a skill folder your agent scans: `$CODEX_HOME/skills/flashback-clips` (default `~/.codex`) for Codex or `~/.claude/skills/flashback-clips` for Claude Code.

Use the normal launcher only when you want a visible game yourself. Replay jobs run from the title screen or inside a replay and are refused in a live world or server. Bot and recording tools run in a live world. Once installed, `flashback-clips` works from any directory; `python -m flashback_agent` is equivalent. `mc-broll` is a compatibility alias.

## Using the tools

```powershell
python -m flashback_agent capabilities
python -m flashback_agent doctor
python -m flashback_agent inspect 'D:\replays\session.zip'
python -m flashback_agent sample --replay 'D:\replays\session.zip' --range 03:00-03:05 --step 10
python -m flashback_agent validate-plan 'D:\clips\camera.json' --range 03:00-03:05
python -m flashback_agent preview --replay 'D:\replays\session.zip' --range 03:00-03:05 --plan 'D:\clips\camera.json' --output 'D:\clips\preview.mp4'
python -m flashback_agent review 'D:\clips\preview.mp4' --output-dir 'D:\clips\preview-frames' --every 0.25
python -m flashback_agent render --replay 'D:\replays\session.zip' --range 03:00-03:05 --plan 'D:\clips\camera.json' --output 'D:\clips\final.mp4'
```

Adjust paths and coordinates to your own replay. Game commands use the worker from `runtime prepare`; pass `--game-dir` to use another. Existing outputs are never overwritten. stdout is JSON and stderr is progress. `--submit-only` on game jobs returns the job ID immediately.

| Tool | Purpose |
| --- | --- |
| `inspect`, `capabilities`, `doctor` | Check metadata, tool scope and the runtime environment |
| `players`, `sample` | Find recorded players; sample entity position, orientation and dimension |
| `validate-plan`, `validate-edit` | Validate camera plans and full edit plans up front |
| `preview`, `render` | Preview or final render with an explicit camera plan |
| `sequence` | Render and join shots from multiple replays/ranges in a given order |
| `assemble`, `review` | Join output clips as cuts; extract media info and review frames |
| `status`, `wait`, `cancel` | Query, wait for or cancel jobs |

`preview` defaults to 640×360 at 24 FPS and `render` to 1920×1080 at 60 FPS. Width and height can each be any even number from 64 to 4096, at 24/30/60 FPS; vertical video works too. `--audio` includes the replay audio; the default is silent.

## Free cameras and edit plans

The `camera.json` example is a fixed world camera over source seconds 180–185. Pick the position and line of sight by inspecting the actual scene.

```json
{
  "version": 1,
  "speed": 1,
  "camera": [
    {"tick": 3600, "position": [10, 80, -10], "lookAt": [0, 70, 0], "fov": 55}
  ]
}
```

A single key is a fixed camera for the whole range. Multiple keys are placed at absolute source ticks covering the range and set position, yaw/pitch or lookAt, roll, FOV and interpolation. Speed is 0.1–8× per shot. `lookAt` is converted into each key's orientation; it is not a persistent target binding. The camera runs the plan as written and never adds tracking, shake, stabilization or collision correction on its own.

The full schemas and edit examples are in [camera/edit plans](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/.agents/skills/flashback-clips/references/plans.md); per-command behavior and limits are in the [tool reference](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/.agents/skills/flashback-clips/references/tools.md).

```powershell
python -m flashback_agent validate-edit edit.json
python -m flashback_agent sequence --edit edit.json --output montage.mp4 --work-dir render-work
# If you stopped waiting, continue with the same plan and paths.
python -m flashback_agent sequence --edit edit.json --output montage.mp4 --work-dir render-work --resume
```

`sequence` validates every input up front, renders shots in the given order and keeps job IDs in a checkpoint. It does not force source-chronological order. `assemble` re-encodes clips that share resolution, FPS and audio layout to H.264/AAC and joins them as cuts.

The same features are available from Python.

```python
from flashback_agent import bridge_health, submit_job, wait_job, validate_plan
from flashback_agent.sequence import render_sequence

bridge_health(profile)
plan = validate_plan('camera.json', 3600, 3700)
job = submit_job(profile, replay, '03:00-03:05', output='final.mp4', plan=plan, fps=30)
result = wait_job(job, timeout=1800)
if result['state'] != 'completed':
    raise RuntimeError(result.get('error', result['state']))
```

Legacy auto-tracking is chosen in the CLI only when you explicitly pass `render ... --style dynamic-follow --target PlayerName`. The existing Python `target` API remains for compatibility. Tracking target/distance options cannot be combined with an explicit camera plan.

## Agent skill

The `flashback-clips` skill (`$flashback-clips` in Codex, `/flashback-clips` in Claude Code) tells the agent to choose inspection, shooting and editing tools to fit the request. It does not impose a particular subject, shot style, movement, video purpose or fixed production procedure. It does not shrink requests down to the old tracking preset; requirements that aren't implemented are explained as concrete limitations or combined with other suitable editing tools.

The skill needs no LLM API key. The calling agent handles natural-language interpretation and scene judgment. On first use the skill has the agent ask you which Minecraft installation to use, as described above. Samples produced by the tools are not semantic analysis, and stills from `review` alone cannot prove motion quality.

## Runtime requirements and limitations

- Needs a real Minecraft client, a graphics driver, and the mods/registries the recording requires. This is not a pure headless ZIP converter.
- Its generality comes from the agent's direction and how it combines tools. Not every Flashback UI feature is exposed through the CLI. Each shot covers one dimension at a fixed forward speed. Reverse playback, freeze frames, speed curves and transitions are not built in yet.
- Entity samples are the recorded entities loaded at that moment. They do not determine camera visibility, full server state or interesting events. Unrecorded chunks and dimension changes need suitable range splits and review.
- Free cameras are not automatically corrected for clipping through geometry or occluded subjects. The agent decides what review and fixes the request needs. The simple collision handling in the legacy tracking tool does not guarantee every frame either.
- Resource packs, shaders and modded appearance follow the worker profile. Audio at changed speeds follows native replay playback; it is not a high-quality audio time-stretch.
- Original replays and saved editor state are never modified. Each job stores its own camera plan/edit state. Output is published only after the finished frames and file are checked; on failure or cancellation a partial file is never published as a completed MP4.
- Ctrl+C or a wait timeout does not cancel a job. Query, wait for or cancel it by job ID. Jobs interrupted by a bridge restart stay failed and are never re-run automatically.

The detailed file protocol is in [docs/protocol.md](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/docs/protocol.md).

## Testing

Run the automated Python and Java tests with the commands below. Some installer tests need the bridge JARs: run `python scripts/stage_bridges.py` after the Gradle build. Releases are built and published by GitHub Actions; see the [release guide](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/docs/releasing.md) (Korean). Carpet integration testing runs in a separate copied world, `run/saves/carpet-agent-test`, with `tests/live_carpet.py --work-dir NEW_DIRECTORY`. The test checks that world's name, then builds a stage and drives two bots, so never point it at a world you actually use. It verifies bot state, time limits, rejection of invalid targets and recording IDs, direct recording, replay entity queries and explicit-camera MP4 output. It also checks that the recorder's spectator mode and the actors' normal mode don't leak into each other.

```powershell
.\gradlew.bat build
python scripts/stage_bridges.py
python -m unittest discover -s tests -v
# A separate development profile. Put any extra mods the recording needs in run/mods.
.\gradlew.bat runClient
$env:PYTHONPATH = (Get-Location).Path
python tests/live_general.py --game-dir run --replay 'D:\replays\test.zip' --output 'D:\clips\general-test.mp4' --work-dir 'work\general-test-new'
```

The live integration test needs a compatible replay of at least 9 seconds that contains a player, plus ffprobe/FFmpeg. It uses that player only as a reference for finding scene coordinates and passes no target to the render request.

0.2.0 passed 11 Python and 12 Java tests. With a provided 11.15-second replay, an entity query → fixed world camera → hand-written 3-key moving camera at 2× → two-shot join ran end to end and produced a 640×360/24 FPS, 4-second/96-frame MP4. A separate CLI preview produced 1 second/24 frames with AAC audio and no target. Composition was checked on representative frames; this does not mean full motion quality was evaluated.

Live footage was validated in a separate development profile with Flashback, Fabric API and Lithostitched. Large modpacks with shaders and long replays are untested. The 0.1.0 tracking demo and validation reports are material from an older version and are not used as evidence for the general-purpose features.

## License

[MIT](https://github.com/uniqueleru/flashback-ai-toolkit/blob/main/LICENSE). Minecraft, Flashback, Carpet and Fabric are separate projects under their own licenses and are not included in this repository or the published package. This is not an official Minecraft product and is not approved by or associated with Mojang or Microsoft.
