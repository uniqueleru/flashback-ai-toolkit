# Live scenes with Carpet

Use these tools when the requested footage needs new recorded events. Reuse a suitable replay when the request calls for it. The agent chooses the scene, participants, actions and filming approach; there is no required choreography or shot recipe.

## Discovery and invocation

`python -m flashback_agent tools` returns the live tool descriptions and JSON Schemas. Use `tools --name TOOL` to inspect one. Invoke `call TOOL --game-dir PROFILE --args-file FILE.json` (or `--args JSON`). For a dedicated Carpet server, add `--server-dir SERVER_ROOT`; the recording client still uses `--game-dir`. Environment equivalents are `FLASHBACK_GAME_DIR` and `CARPET_SERVER_DIR`. Python callers can use `flashback_agent.tools.call_tool`. Configured MCP hosts may call the same names directly.

Carpet tools require a live server with Carpet and the `carpet-agent` bridge for that Minecraft version; the worker includes both. This works with an integrated singleplayer server or a dedicated Fabric server. Recording tools require Flashback and the `flashback-agent` bridge in the [background client](runtime.md). A bot server alone does not record a Flashback ZIP. Do not substitute a different Minecraft version just to fit a demo.

## Choose actions from observed state

`carpet_list` distinguishes fake and human players. `carpet_state`, `carpet_observe` and `carpet_inventory` provide positions, nearby loaded blocks/entities and items. `carpet_spawn`, `carpet_move`, `carpet_look`, `carpet_action`, `carpet_hotbar`, `carpet_mount`, `carpet_teleport`, `carpet_stop` and `carpet_remove` operate only on fake players. Discover their exact argument schemas instead of guessing.

Movement is forward/strafe input relative to the bot's view, not navigation. There is no built-in `go_to`, obstacle avoidance, combat strategy or scene understanding. Use observations to decide actions, and report a missing capability when the task needs one. Teleporting is an explicit discontinuity, not a substitute for a requested walk. Spawn defaults to creative mode/overworld; specify them when the scene requires another choice.

Reusing a bot name can restore saved inventory/effects. Inspect its state instead of assuming a fresh actor. Server state and `record_status.visiblePlayers` report visibility; loaded does not necessarily mean visible, for example with an intentional invisibility effect.

Movement and continuous/interval actions require a duration in server ticks (20 per second at normal tick rate). They return when accepted and expire in the game even if the agent is still thinking. Inspect resulting state: accepted input does not prove a jump, hit, placement or mount succeeded. Paused servers do not advance action durations. A move replaces movement/sprint/sneak inputs but not other action channels. `carpet_stop` ends all inputs for the named bot. Stop/remove only the actors whose cleanup belongs to this task.

`carpet_command` exposes privileged server commands for requested world setup or advanced operations. Unlike bot-specific tools it can affect humans and terrain. Use it with the existing authorization and scene scope; read its numeric result and messages for command-level failure. Prefer bounded bot tools when they express the action; raw `/player` commands have no automatic duration limit. Recording is not an excuse to alter unrelated worlds or server settings.

## Record, inspect, then film

`record_status` shows observer position, visible players, paused state and existing recording. `record_start` returns a `recordingId`; use it with `record_stop`. Stop takes a new ZIP `output` path and verifies the archive before publishing. The tools will not take over an unrelated active recording. Retain the recording ID so another turn can stop it.

Recording tools currently expose start/stop, not pause/resume; the pinned native resume path showed actor visibility gaps at a snapshot boundary. Separate takes can be recorded and edited when appropriate.

The recorder must receive the relevant chunks and entities. Server observations do not establish recording coverage. Check the observer's loaded players, and inspect/sample the resulting replay before claiming the action was captured. Actor motion does not prescribe camera motion: after recording, use the normal replay/camera/edit tools to fulfill the requested visual intent.

`world_open` opens an existing save folder in an idle client; it does not create a world, launch Minecraft or bypass load prompts. `world_close` saves/leaves the current world and refuses active recording/export. Close a world only when authorized by the work; replay rendering requires leaving the live game. The tools do not change focus/pause preferences. Verify paused state if actions or recording seem stalled.

Keep returned `jobDir` values. After a waiting timeout use `tool-status JOB_DIR [--wait]`. Timeout or caller disconnect does not cancel executed inputs. Requests are tied to a server session and expire before execution; a restart can leave an uncertain action outcome. Inspect current state before retrying. The CLI and MCP share these semantics; the MCP adapter processes calls sequentially.
