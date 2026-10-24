# Replay job protocol v2

This document describes replay inspection/rendering. The 0.3.0 live tool protocol is separate: `<server-dir>/carpet-agent` and `<game-dir>/flashback-agent/live`. See [Carpet tools](carpet-tools.md). Those inboxes execute structured bot/recording calls and explicitly include a privileged `carpet_command` tool; their authority and lifetime differ from replay jobs.

The bridge owns `<game-dir>/flashback-agent`. There is no HTTP listener, network service, or arbitrary script execution. One bridge holds `bridge.lock` for the lifetime of the client and executes one job at a time.

The Python client atomically publishes `jobs/<32 lowercase hex characters>/request.json`. The bridge exclusively creates `claimed` before reading it. Requests are immutable after submission. On startup, claimed jobs without a terminal result are failed; they are never automatically replayed. Unclaimed jobs remain queued. Schema v1 follow jobs remain accepted for compatibility; the new client emits v2 and requires a v2 heartbeat.

```json
{
  "schemaVersion": 2,
  "id": "0123456789abcdef0123456789abcdef",
  "operation": "render",
  "replay": "D:/replays/session.zip",
  "startTick": 3600,
  "endTick": 3700,
  "target": null,
  "output": "D:/clips/world.mp4",
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "audio": false,
  "plan": {
    "version": 1,
    "speed": 1,
    "camera": [
      {"tick": 3600, "position": [10, 80, -10], "yaw": 0, "pitch": 20,
       "roll": 0, "fov": 55, "interpolation": "linear"}
    ],
    "visuals": {}
  }
}
```

Operations are `render`, `players`, and `sample`. Paths are absolute. Both Python and Java validate bounds. Ranges are source replay time at 20 ticks/s, start-inclusive/end-exclusive for video frames. Queries may sample the end boundary for interpolation.

## Camera authority

`render` requires either a normalized `plan` or a legacy `target`, never both. The Python public schema also accepts `lookAt`, which it converts to yaw/pitch before queueing. The bridge accepts normalized world-space camera keys, FOV, roll, interpolation, a constant speed, and three visual flags. Single-key plans expand into a fixed camera at both range boundaries; multiple keys must cover the range. No procedural motion, tracking or collision repair is applied to explicit plans.

The public plan and edit schemas live in [the Skill reference](../.agents/skills/flashback-clips/references/plans.md). The Java adapter writes a dedicated `EditorState` and never modifies `EditorStateManager`'s saved state. The job retains `camera-plan.json` and `camera-state.json`. Explicit plans have an empty `targetUuid` in the terminal result.

Legacy follow requests use `target`, `distance`, `side`, and `heightOffset` without a plan. They sample the player every two ticks, smooth heading/position, and shorten obstructed target-to-camera rays. This generator is independent of the general plan path and is not a cinematographic optimizer.

## Queries

`players` samples recorded player names/UUIDs every 20 ticks. `sample` takes `sampleIntervalTicks` (1–200), and optionally an exact entity name/UUID as `target`. It reads loaded recorded entities and excludes replay-viewer players. Results point to `samplesFile`, a JSON containing `samples` with tick, dimension and entity records (UUID, name, type, player flag, position, yaw, pitch, onGround). Recorded accurate positions are used when available, otherwise current entity positions. This is scene data, not event classification or a complete server inventory.

All game access occurs on the Minecraft client thread after seeking and waiting for server reconstruction/client packet updates. A query/render refuses to disconnect an active live world/server.

## State and cancellation

`status.json` states are `opening`, `sampling`, `rendering`, `completed`, `failed`, `cancelled`. No status file means queued. Sampling includes tick/endTick; rendering reports frames/expectedFrames when available. `result.json` is authoritative and overrides progress. Completed renders include output, frame count, duration and camera artifact paths. Empty queries may complete and do not select an arbitrary target.

Writing `cancel.json` requests cancellation during queueing, sampling, or the native export loop's end-of-frame branch. GPU downloads and the encoder drain before the partial file is removed. Ctrl+C or a waiting timeout only stops waiting. Cancellation cannot immediately interrupt a blocked GPU driver or asynchronous world load. A complete MP4 is published only after frame-count and file checks, without replacing an existing destination.

`bridge.json` contains schemaVersion, protocolVersion, bridgeVersion, Minecraft/Flashback versions, state, jobId and `updatedAt` in Unix milliseconds. It is stale after 15 seconds and proves liveness, not progress of a GPU call.

## Ordered edits

`sequence` is Python-side orchestration over ordinary render jobs. It preflights all shots before submission and persists ordered job IDs in `WORK_DIR/sequence.json`. Resume checks the normalized edit fingerprint, profile and output; it waits on existing job IDs rather than submitting duplicates. Failed or cancelled shots are not silently retried. FFmpeg assembly joins matching video/audio layouts with hard cuts and checks frame count before publishing.

## Flashback adapter

Each bridge build is compiled against one immutable Flashback build from Modrinth, recorded in its `bridge.json`, and does not bundle Flashback in its JAR. Mixins are limited to agent-owned exports:

- An accessor reads completed frames; injections report progress and request cancellation through the native end-of-frame branch. Throwing mid-frame was found to leave a pending GPU callback accessing a released buffer in the original MVP, so cancellation follows Flashback's cleanup path.
- `calculateTicks` receives a constant-speed schedule only when the input editor state belongs to the active agent export. The schedule is `frameIndex * 20 * speed / fps`, with `ceil(durationTicks * fps / (20 * speed))` frames. This also avoids the targeted Flashback build's observed residual-rounding issue (119 instead of 60 frames in a two-second/30 FPS export). Ordinary GUI exports and user speed tracks are untouched. A version-pinned reflective adapter constructs the private `ExportJob.TickInfo`; a signature mismatch fails explicitly.

The current adapter handles one dimension and constant forward speed per shot. It does not expose every Flashback feature. Profile resources determine the rendered appearance; native altered-speed audio is not a high-quality time-stretch implementation.
