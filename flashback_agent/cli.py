"""Command line interface. Stdout is JSON; progress is written to stderr."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import zipfile

from . import (bridge_health, cancel_job, config, inspect_replay, read_status,
               submit_job, wait_job, parse_range, validate_plan)


def emit(value, file=sys.stdout):
    print(json.dumps(value, ensure_ascii=False), file=file, flush=True)


def parser():
    p = argparse.ArgumentParser(prog="flashback-clips", description="Inspect Flashback replays and render caller-authored camera plans")
    sub = p.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Read replay metadata without Minecraft")
    inspect.add_argument("replay", type=Path)
    sub.add_parser('capabilities', help='Describe available tools and boundaries as JSON')
    setup = sub.add_parser('setup', help='Install the agent skill and find FFmpeg; Minecraft is chosen later')
    setup.add_argument('--agent', choices=('auto', 'codex', 'claude', 'both'), default='auto',
                       help='Where to install the skill; auto picks the agents already set up')
    setup.add_argument('--skill-dir', type=Path, help='Exact skill folder instead of --agent')
    setup.add_argument('--skip-skill', action='store_true')
    setup.add_argument('--no-dependency-install', action='store_true', help='Fail instead of installing FFmpeg with WinGet')
    runtime = sub.add_parser('runtime', help='Choose a Minecraft installation and run an isolated Windows background client')
    runtimes = runtime.add_subparsers(dest='runtime_command', required=True)
    runtimes.add_parser('sources', help='List Minecraft installations found on this PC, for the user to choose from')
    for operation in ('prepare', 'start', 'status', 'stop'):
        command = runtimes.add_parser(operation)
        if operation == 'prepare':
            command.add_argument('--source', type=Path, required=True,
                                 help='Modrinth profile folder or official launcher game folder the user chose')
            command.add_argument('--launcher', choices=('auto', 'modrinth', 'official'), default='auto')
            command.add_argument('--minecraft-version', dest='minecraft', help='When it cannot be detected')
            command.add_argument('--install-fabric', action='store_true',
                                 help='Download Fabric Loader for the worker when the launcher has none')
            command.add_argument('--instance', type=Path, help='New worker folder; default "worker" in the data folder')
            command.add_argument('--meta-dir', type=Path, help="Modrinth's meta folder, when not next to profiles")
            command.add_argument('--minecraft-dir', type=Path, help="Official launcher folder, when the game folder is custom")
            command.add_argument('--java', type=Path)
            command.add_argument('--save', help='Optional quiescent source save to COPY into the new instance')
        else:
            command.add_argument('--instance', type=Path, default=os.getenv('FLASHBACK_GAME_DIR'),
                                 help='Worker folder; default the one runtime prepare recorded')
        if operation == 'start':
            command.add_argument('--memory-mb', type=int, default=4096)
            command.add_argument('--fps', type=int, default=30)
            command.add_argument('--timeout', type=float, default=180)
        if operation == 'stop':
            command.add_argument('--timeout', type=float, default=60)
    tool_list = sub.add_parser('tools', help='List structured Carpet/recording tools with JSON Schemas')
    tool_list.add_argument('--name', help='Show one tool schema')
    for command in ('call', 'mcp'):
        child = sub.add_parser(command, help='Invoke a structured tool' if command == 'call' else 'Serve tools via MCP stdio')
        child.add_argument('--game-dir', type=Path, default=os.getenv('FLASHBACK_GAME_DIR'))
        child.add_argument('--server-dir', type=Path, default=os.getenv('CARPET_SERVER_DIR'))
        if command == 'call':
            child.add_argument('tool')
            arguments = child.add_mutually_exclusive_group()
            arguments.add_argument('--args', default='{}', help='Tool arguments as JSON')
            arguments.add_argument('--args-file', type=Path)
            child.add_argument('--timeout', type=float, default=180)
            child.add_argument('--submit-only', action='store_true')
    tool_status = sub.add_parser('tool-status', help='Read or wait for a tool job by its returned directory')
    tool_status.add_argument('job_dir', type=Path)
    tool_status.add_argument('--wait', action='store_true')
    tool_status.add_argument('--timeout', type=float, default=180)
    validate = sub.add_parser('validate-plan', help='Check and normalize a camera JSON without running Minecraft')
    validate.add_argument('plan', type=Path)
    validate.add_argument('--range', dest='source_range')
    edit = sub.add_parser('validate-edit', help='Preflight all shot ranges, plans and relative paths')
    edit.add_argument('edit', type=Path)
    review = sub.add_parser('review', help='Inspect media metadata and extract chronological frames')
    review.add_argument('video', type=Path)
    review.add_argument('--output-dir', type=Path, required=True)
    review.add_argument('--every', type=float, default=1)
    review.add_argument('--max-frames', type=int, default=24)
    assemble = sub.add_parser('assemble', help='Join compatible rendered clips in supplied order with hard cuts')
    assemble.add_argument('clips', nargs='+', type=Path)
    assemble.add_argument('--output', required=True, type=Path)
    sequence = sub.add_parser('sequence', help='Render an explicit ordered edit and assemble its shots')
    sequence.add_argument('--edit', type=Path, required=True)
    sequence.add_argument('--game-dir', type=Path, default=os.getenv('FLASHBACK_GAME_DIR'))
    sequence.add_argument('--output', type=Path, required=True)
    sequence.add_argument('--work-dir', type=Path)
    sequence.add_argument('--resume', action='store_true')
    sequence.add_argument('--timeout', type=float, default=1800)
    for command in ("doctor", "render", "preview", "sample", "players", "status", "wait", "cancel"):
        child = sub.add_parser(command)
        child.add_argument("--game-dir", type=Path, default=os.getenv("FLASHBACK_GAME_DIR"),
                           help="Minecraft profile directory; or set FLASHBACK_GAME_DIR")
        if command in ("render", "preview", "sample", "players"):
            child.add_argument("--replay", type=Path, required=True)
            child.add_argument("--range", required=True, dest="source_range", help="Source time START-END (20 ticks/s)")
            child.add_argument("--submit-only", action="store_true")
            child.add_argument("--timeout", type=float, default=1800)
        if command == 'sample':
            child.add_argument('--target', help='Optional exact entity name/UUID; omit to query loaded recorded entities')
            child.add_argument('--step', type=int, default=20, help='Sampling interval in source ticks (1..200)')
        if command in ("render", "preview"):
            method = child.add_mutually_exclusive_group(required=True)
            method.add_argument('--plan', type=Path, help='Explicit world-space camera plan JSON')
            method.add_argument('--style', choices=('dynamic-follow',), help='Opt-in legacy player-follow generator')
            child.add_argument("--target", help="Player name/UUID, only for explicit legacy follow style")
            child.add_argument("--output", type=Path, required=True)
            child.add_argument("--width", type=int, default=640 if command == 'preview' else 1920)
            child.add_argument("--height", type=int, default=360 if command == 'preview' else 1080)
            child.add_argument("--fps", type=int, choices=(24, 30, 60), default=24 if command == 'preview' else 60)
            child.add_argument("--distance", type=float)
            child.add_argument("--side", type=float)
            child.add_argument("--height-offset", type=float)
            child.add_argument("--audio", action="store_true", help="Enable replay audio; silent output is default")
        if command in ("status", "wait", "cancel"):
            child.add_argument("job_id")
        if command == "wait":
            child.add_argument("--timeout", type=float, default=1800)
    return p


def main(argv=None):
    # Console and redirected output are stable UTF-8, including Korean paths.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        config.apply_environment()  # before parsing: setup's worker becomes the --game-dir default
    except ValueError as exc:
        emit({"error": str(exc)}, file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    try:
        if args.command == 'setup':
            from .install import setup
            kwargs = vars(args).copy()
            kwargs.pop('command')
            emit(setup(**kwargs))
            return 0
        if args.command == 'doctor':
            from .doctor import doctor
            report = doctor(args.game_dir)
            emit(report)
            return 0 if report['ok'] else 1
        if args.command == 'runtime':
            from . import launchers, runtime
            kwargs = vars(args).copy()
            kwargs.pop('command')
            operation = kwargs.pop('runtime_command')
            if operation == 'sources':
                emit(launchers.sources())
                return 0
            if operation != 'prepare' and not kwargs['instance']:
                raise ValueError('No worker yet: run `runtime sources`, let the user choose, then `runtime prepare`')
            result = getattr(runtime, operation)(**kwargs)
            if operation == 'prepare':
                # The chosen installation and its worker become the defaults for every later command.
                config.update(instance=result['instance'], source=result['sourceProfile'], minecraft=result['minecraft'])
            emit(result)
            return 0
        if args.command == 'tools':
            from .tools import TOOLS, BY_NAME
            emit(BY_NAME[args.name] if args.name else {'tools': TOOLS})
            return 0
        if args.command == 'mcp':
            from .mcp import serve
            serve(args.game_dir, args.server_dir)
            return 0
        if args.command == 'tool-status':
            result = wait_job(args.job_dir, timeout=args.timeout) if args.wait else read_status(args.job_dir)
            emit(result)
            return 1 if result['state'] in ('failed', 'cancelled') else 0
        if args.command == 'call':
            from .tools import submit_tool
            arguments = json.loads(args.args_file.read_text(encoding='utf-8-sig') if args.args_file else args.args)
            job = submit_tool(args.tool, arguments, game_dir=args.game_dir, server_dir=args.server_dir)
            emit({'id': job.name, 'jobDir': str(job), 'state': 'queued'}, file=sys.stderr)
            if args.submit_only:
                emit({'id': job.name, 'jobDir': str(job), 'state': 'queued'})
                return 0
            result = wait_job(job, timeout=args.timeout, poll=.1)
            emit(result)
            return 0 if result['state'] == 'completed' else 1
        if args.command == 'capabilities':
            from .plans import INTERPOLATIONS, VISUALS
            from . import bridges
            builds = bridges.builds()
            emit({'protocolVersion': 2, 'bridgeVersion': '0.4.0',
                  'bridges': [{'minecraft': v, 'java': builds[v]['java'], 'fabricLoader': builds[v]['fabricLoader'],
                               'flashback': builds[v]['flashback']} for v in bridges.supported()],
                  'tools': ['setup', 'runtime', 'tools', 'call', 'tool-status', 'mcp', 'inspect', 'doctor', 'sample', 'players', 'validate-plan', 'validate-edit', 'preview', 'render', 'sequence', 'assemble', 'review', 'status', 'wait', 'cancel'],
                  'backgroundRuntime': {'platform': 'Windows', 'isolatedProfile': True, 'privateDesktop': True, 'windowGuard': 'JVM premain / GLFW', 'gameFiles': 'from the Modrinth or official launcher installation the user chooses', 'authentication': 'local-offline', 'defaultFps': 30, 'desktopAudio': 'silent null backend'},
                  'liveTools': {'discovery': 'tools', 'pathfinding': False, 'recording': True, 'transport': 'local file inbox; optional MCP stdio'},
                  'camera': ['position', 'yaw', 'pitch', 'lookAt', 'roll', 'fov'],
                  'interpolations': sorted(INTERPOLATIONS), 'visuals': sorted(VISUALS),
                  'sourceTicksPerSecond': 20, 'constantSpeedRange': [.1, 8], 'fps': [24, 30, 60],
                  'subjectRequiredForPlan': False, 'automaticShotSelection': False,
                  'limits': ['Matching Minecraft client and recorded registries required',
                             'Samples include currently loaded recorded entities', 'No reverse playback or time freezes',
                             'Explicit plans are not automatically collision-adjusted', 'Transitions beyond hard cuts require external editing']})
            return 0
        if args.command == 'validate-plan':
            bounds = parse_range(args.source_range) if args.source_range else (None, None)
            emit(validate_plan(args.plan, *bounds))
            return 0
        if args.command == 'validate-edit':
            from .sequence import load_edit
            emit(load_edit(args.edit))
            return 0
        if args.command == 'review':
            from .media import review
            emit(review(args.video, args.output_dir, every=args.every, max_frames=args.max_frames))
            return 0
        if args.command == 'assemble':
            from .media import assemble
            emit(assemble(args.clips, args.output))
            return 0
        if args.command == "inspect":
            metadata = inspect_replay(args.replay)
            emit({"metadata": metadata, "durationSeconds": metadata["total_ticks"] / 20})
            return 0
        if not args.game_dir:
            raise ValueError("Specify --game-dir or FLASHBACK_GAME_DIR")
        root = args.game_dir.resolve(strict=True)
        if args.command == 'sequence':
            from .sequence import render_sequence
            emit(render_sequence(args.edit, root, args.output, work_dir=args.work_dir, resume=args.resume,
                                 timeout=args.timeout, on_progress=lambda s: emit(s, file=sys.stderr)))
            return 0
        if args.command in ("render", "preview", "sample", "players"):
            bridge_health(root)
            options = {}
            if args.command in ("render", "preview"):
                options = {key: getattr(args, key) for key in
                           ("target", "output", "width", "height", "fps", "distance", "side", "height_offset", "audio", "plan")
                           if getattr(args, key) is not None}
                if args.plan and any(getattr(args, key) is not None for key in ('target', 'distance', 'side', 'height_offset')):
                    raise ValueError('Follow options cannot modify an explicit camera plan')
            if args.command == 'sample':
                options = {'target': args.target, 'sample_interval_ticks': args.step}
            job = submit_job(root, args.replay, args.source_range, operation='render' if args.command == 'preview' else args.command, **options)
            emit({"id": job.name, "state": "queued", "jobDir": str(job)}, file=sys.stderr)
            if args.submit_only:
                emit({"id": job.name, "state": "queued", "jobDir": str(job)})
                return 0
        else:
            if not re.fullmatch(r"[0-9a-f]{32}", args.job_id):
                raise ValueError("Invalid job ID")
            job = root / "flashback-agent" / "jobs" / args.job_id
            if not (job / "request.json").is_file():
                raise ValueError("Unknown job")
            if args.command == "cancel":
                cancel_job(job)
                emit({"id": job.name, "cancelRequested": True})
                return 0
            if args.command == "status":
                emit(read_status(job))
                return 0
        status = wait_job(job, timeout=args.timeout, on_progress=lambda s: emit(s, file=sys.stderr))
        emit(status)
        return 0 if status["state"] == "completed" else 1
    except KeyboardInterrupt:
        emit({"error": "Stopped waiting; the submitted job continues. Use cancel JOB_ID to stop it."}, file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError, zipfile.BadZipFile) as exc:
        emit({"error": str(exc)}, file=sys.stderr)
        return 2
