# Background execution

Use the worker prepared for this installation. Commands default to it once `runtime prepare` has recorded one; `FLASHBACK_GAME_DIR` or `--game-dir` overrides it. It is a separate copy of the user's Minecraft installation. Check it with `python -m flashback_agent runtime status`; start with `runtime start`. Use that same worker for recording and replay tools. The copied `carpet-agent-test` world is a disposable validation fixture, not a default location for user scenes.

## First use: the user chooses the installation

When `doctor` reports no worker, set one up with the user before any game work:

1. Run `python -m flashback_agent runtime sources`. It lists Modrinth profiles and the official launcher folder it found, each with the Minecraft and Fabric versions of its last launch and whether a bridge build exists for that version. `supported` lists the versions this toolkit can run.
2. Show the user those candidates and ask which installation to use, or for another path: a Modrinth profile folder, or the official launcher's game folder. Never choose one on the user's behalf, even when only one is listed.
3. Run `python -m flashback_agent runtime prepare --source "PATH"` with their answer. It copies mods, config and resource/shader packs into a new worker and leaves the installation unchanged. It then becomes the default worker.
   - **Fabric missing:** if it reports that Fabric is not installed there, tell the user that Fabric Loader will be downloaded for the worker only, without changing their launcher, then rerun with `--install-fabric`.
   - **Version unknown:** if it cannot tell the Minecraft version, ask the user and pass `--minecraft-version`.
   - **No bridge build:** if the version has no bridge build, report the supported versions. Do not try another version or installation unless the user picks one.
   - **Other failures:** for missing game files or Java, ask the user to launch that version once in their launcher, or pass `--java`. A Forge/NeoForge installation cannot be used; ask for a Fabric or vanilla one.

`runtime prepare` refuses to overwrite an existing folder. Rerunning with the same source reuses the completed worker. To switch installations, use a new `--instance`.

## Running without disturbing the user

Automated work must not open a game/launcher/console window or take focus while the user is using the PC. Use the managed background runtime by default. Do not fall back to the launcher UI, visible `runClient`, maximizing, foregrounding, cursor automation, or an unguarded Java launch to fix a failure. Report the concrete startup/load problem and keep the task recoverable. A user explicitly requesting a visible interactive session can change this default for that session.

The worker uses the same graphical Minecraft renderer on a private Windows desktop, with a hidden OpenGL window. The launcher never switches the user's desktop; child processes inherit the private desktop. The JVM premain guard also blocks GLFW display/focus/fullscreen/cursor acquisition before window creation. Essential's updater prompts are disabled only in this worker process. Background focus loss does not pause the game; desktop audio uses a silent OpenAL backend. MP4 audio remains an independent `--audio` choice. CPU/GPU work still consumes resources; default process priority is below normal, normal rendering is 30 FPS, and heap limit is 4 GiB. Output resolution/FPS remains the agent's task decision.

`runtime status` reports process identity and current visible-window/foreground checks. `call record_status` reports guard state, hidden/focus/fullscreen flags, launch ID, pause state and current screen class. A ready worker needs `guard=active`, `visible=false`, `focused=false`, `fullscreen=false`. After a start timeout inspect status/logs instead of launching another process. The launcher rejects duplicate starts and changed guard artifacts; it never uses a visible fallback.

Stop an owned idle worker with `runtime stop` after its jobs finish. Active recording/export/world load makes shutdown fail. Retain the recording ID, finish the recording, wait for rendering, then stop. Shutdown saves the world and does not force-kill on timeout. Do not stop another user's interactive client.

`--save NAME` on `runtime prepare` copies one closed save; otherwise no worlds are copied. `--meta-dir` (Modrinth) and `--minecraft-dir` (official launcher with a custom game folder) resolve nonstandard layouts. Never point the worker at the original active installation or copy a running world. Preserve required scene mods and appearance; a failed registry load is not permission to remove them.

The worker runs as a separate local offline observer and does not read account tokens or authenticate online servers. It uses the game files the user's launcher already downloaded. The default bot flow uses the hidden client's integrated Carpet server. Dedicated Carpet control remains available through `--server-dir`; server hosting/login is separate. Missing scene/world/authentication capabilities should be reported, not replaced with a preset demo.
