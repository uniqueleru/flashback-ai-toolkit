# Carpet actors and live recording (0.4.0)

The agent plans a scene; structured tools operate Carpet fake players and return world state. The agent can combine these tools for the user's scene, then independently author cameras against the recording. There is no predefined actor, scene, choreography or shot style.

## Installation and transport

- Server: a Minecraft version with a bridge build (see `capabilities`), Fabric API, official [Carpet](https://modrinth.com/mod/carpet), and the matching `carpet-agent` JAR.
- Recording client: the same Minecraft version, Flashback, Fabric API, and the matching `flashback-agent` JAR.
- Singleplayer: install both bridges and both mods in one profile. Carpet tools become available when its live integrated server starts.
- Dedicated server: only the Carpet companion is needed server-side. Run the CLI/MCP process on the server host or with access to its folder. The recorder remains a separate graphical client. Remote networking/authentication and server hosting are not configured by these tools.

For automated Windows execution, use the [isolated background runtime](background-runtime.md). It runs the client on a private desktop with a hidden window; use the worker directory as `--game-dir`. The world tools below operate within that client. Their interface does not need keyboard/mouse automation.

Install the Python wheel, then `python -m flashback_agent tools` returns tool names, descriptions and JSON Schemas. `tools --name carpet_move` narrows discovery. The same contract is callable from Python with `flashback_agent.tools.call_tool` / `submit_tool`, the CLI, or MCP.

Each bridge build names a minimum Carpet build, with file name and sha512, in its `bridge.json`. The worker keeps the installation's Carpet when it is at least that version and otherwise downloads that exact file from Modrinth. Carpet is not bundled in our JAR.

The companion refreshes a respawned bot's authoritative abilities/visibility and broadcasts its game mode: Carpet's saved-player loading can otherwise leave spectator display state on a creative bot. The Flashback bridge also corrects a snapshot game-mode serialization flag that the targeted Flashback build omits. These preserve the requested actor mode and active effects, including intentional invisibility. State tools report both server and observer visibility for inspection.

## Calls and results

```powershell
$env:FLASHBACK_GAME_DIR = 'D:\MinecraftWorkers\clips'
python -m flashback_agent tools
python -m flashback_agent call record_status
python -m flashback_agent call carpet_list
python -m flashback_agent call carpet_spawn --args-file spawn.json
python -m flashback_agent call carpet_move --args-file move.json
```

`spawn.json` supplies `name` and `position`, optionally `yaw`, `pitch`, `dimension`, `gameMode`. `move.json` supplies `name`, `forward` and/or `strafe`, and `ticks`. Values belong to the caller's scene. Spawn defaults to creative mode in the overworld; set mode/dimension explicitly when they matter. A successful spawn waits for the fake player to join; it does not replace an online name.

For a dedicated server, add `--server-dir SERVER_ROOT` or set `CARPET_SERVER_DIR`. If provided, it selects the Carpet server; `--game-dir` continues to select the recording client. Each result is `{id,state,result}` or `{id,state,error}`. Ongoing actions return after input acceptance, before their duration elapses. Inspect state or observations to verify the intended action actually happened.

Tool jobs use separate inboxes from replay jobs. Keep the returned `jobDir` from stderr or `--submit-only`, and use `tool-status JOB_DIR [--wait]` after timeout. A timeout/disconnected caller does not roll back an executed action. Requests are pinned to the running bridge session, expire before execution after 120 seconds, and are claimed once; stale requests cannot execute in a newly opened world. A server restart during a request is an ambiguous outcome, not permission to retry automatically.

## Actor controls

| Tools | Meaning |
| --- | --- |
| `carpet_list`, `carpet_state` | Authoritative players/bot state, dimension, game tick, active input durations |
| `carpet_spawn`, `carpet_remove` | Create/remove fake players |
| `carpet_move` | Forward/back/strafe input, optional sprint/sneak, bounded duration |
| `carpet_look` | Absolute yaw/pitch or look at a coordinate |
| `carpet_action` | Use, attack, jump, drop, dropStack, swapHands; once/continuous/interval/stop |
| `carpet_stop` | Stop all inputs on one bot |
| `carpet_inventory`, `carpet_hotbar` | Inspect inventory/select slot |
| `carpet_mount`, `carpet_teleport` | Mount/dismount; explicit same-dimension teleport |
| `carpet_observe` | Nearby loaded blocks and entities, not path planning |
| `carpet_command` | Explicit privileged server command for world setup or other command features |

Bot-specific tools verify Carpet's actual fake-player class. They cannot control a real player. `carpet_command` intentionally has the server console's authority and can affect people, terrain and server state; choose it only for the requested scene operations. Its numeric return value and messages must be interpreted: a transport-level completed result can still contain a command-level failure. Avoid using raw `/player` commands when structured bounded controls express the action; raw commands do not acquire duration leases.

`carpet_move` is input, not `go_to`: no automatic pathfinding, obstacle avoidance, terrain construction or semantic task execution is included. Forward/strafe are relative to the bot's view; forward +1, backward -1, left strafe +1, right -1. Each move replaces previous movement/sprint/sneak inputs. Other action channels remain active. A new action replaces only its own channel. Ongoing controls require 1..12000 server ticks; at normal speed 20 ticks = 1 second. Paused/frozen servers do not consume action ticks. Expiration stops the relevant inputs; physical inertia can persist briefly. `carpet_stop` ends all inputs immediately.

An accepted use/attack may miss, a mount may find no vehicle, and a move may hit an obstacle. Inspect the resulting world/inventory/position. Item queries return IDs/counts, not full item components. Observations do not load missing chunks. Bot motion and camera motion are separate decisions.

## Recording and world lifecycle

`record_status` reports the client observer, loaded players, pause state and ownership. `record_start` requires a live world and no active recording, and returns `recordingId`. Pass that exact ID to `record_stop` (`output` new ZIP path). Stop flushes Flashback's recorder, exports and verifies metadata/chunk presence before publishing. If export fails, the error includes recovery locations. It never calls Flashback's destructive cancel operation. It does not finish a recording started elsewhere.

Pause/resume is deliberately not exposed in this release: Flashback's native resume snapshot produced transient missing actors at the boundary during validation. Use separate recordings and edits when the request needs separate takes.

Keep the recorder within the scene's loaded chunks/entity tracking range. Server-side bot state does not prove the observer captured it. Check `record_status.visiblePlayers`, then inspect/sample the saved replay. The client must remain connected and unpaused for the intended duration. A headless bot server alone cannot produce a Flashback replay.

`world_open` opens an existing direct child of the profile's `saves` folder when no world is open. It does not create worlds or bypass upgrade/registry prompts. `world_close` explicitly saves/leaves the current world and refuses active recording/export. Use it only when leaving that world is within the task; replay rendering cannot run while still connected to a live world. The separate `runtime` CLI handles process lifecycle and background execution. Existing automatic Flashback recordings are reported but not adopted. `runtime_shutdown` requires the exact managed `launchId`, refuses ongoing work, and saves/stops only that background client; normally use `runtime stop`, which also waits for process exit.

## Optional MCP stdio

```json
{
  "command": "python",
  "args": ["-m", "flashback_agent", "mcp", "--game-dir", "D:\\MinecraftWorkers\\clips"]
}
```

This is a server-launch example, not a setting the installer adds to Codex or Claude Code. A configured MCP host discovers the same 20 tools through `tools/list` and invokes them with `tools/call`. CLI use needs no MCP registration. Stdio follows the [MCP transport contract](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports); it processes calls sequentially and does not implement in-flight cancellation. Use bounded action durations and explicit stop tools.
