"""Caller-authored shot order; persisted job IDs make interrupted edits resumable."""
import hashlib
import json
from pathlib import Path
import uuid

from . import atomic_json, bridge_health, bridges, inspect_replay, parse_range, submit_job, wait_job
from .media import assemble
from .plans import known_fields, validate_plan


def load_edit(path):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 1_000_000:
        raise ValueError('Edit JSON exceeds 1 MB')
    edit = json.loads(path.read_text(encoding='utf-8-sig'))
    known_fields(edit, {'version', 'replay', 'render', 'shots'}, 'edit')
    if type(edit.get('version')) is not int or edit['version'] != 1:
        raise ValueError('Edit version must be 1')
    settings = edit.get('render', {})
    known_fields(settings, {'width', 'height', 'fps', 'audio'}, 'render settings')
    settings = {'width':1920, 'height':1080, 'fps':60, 'audio':False, **settings}
    if any(type(settings[k]) is not int or not 64 <= settings[k] <= 4096 or settings[k] % 2 for k in ('width','height')):
        raise ValueError('Edit dimensions must be even integers between 64 and 4096')
    if settings['fps'] not in (24,30,60) or type(settings['audio']) is not bool:
        raise ValueError('Invalid edit frame rate or audio setting')
    shots = edit.get('shots')
    if not isinstance(shots, list) or not 1 <= len(shots) <= 100:
        raise ValueError('Edit requires 1..100 ordered shots')
    normalized, minecraft = [], set()
    for shot in shots:
        known_fields(shot, {'replay', 'range', 'plan', 'name'}, 'shot')
        replay = shot.get('replay', edit.get('replay'))
        if not isinstance(replay, str):
            raise ValueError('Each shot requires a replay, directly or inherited from the edit')
        replay = (path.parent / replay).resolve(strict=True)
        metadata = inspect_replay(replay)
        start, end = parse_range(shot['range'])
        version = metadata.get('version_string')
        if version not in bridges.builds():
            raise ValueError(f'{replay.name} was recorded in Minecraft {version}; bridge builds: {", ".join(bridges.supported()) or "none"}')
        if end > metadata['total_ticks']:
            raise ValueError(f'Shot range exceeds {replay.name}')
        minecraft.add(version)
        plan = shot['plan']
        if isinstance(plan, str):
            plan = path.parent / plan
        plan = validate_plan(plan, start, end)
        normalized.append({'replay':str(replay), 'range':shot['range'], 'plan':plan, 'name':shot.get('name','')})
    if len(minecraft) > 1:
        raise ValueError('One worker renders the whole edit, so every shot must come from the same Minecraft version')
    return {'version':1, 'render':settings, 'shots':normalized}


def render_sequence(edit_path, game_dir, output, *, work_dir=None, resume=False, timeout=1800, on_progress=None):
    edit = load_edit(edit_path)  # Preflight every shot before submitting any game work.
    game_dir = Path(game_dir).resolve(strict=True)
    output = Path(output).resolve()
    if output.suffix.lower() != '.mp4':
        raise ValueError('Output must be MP4')
    fingerprint = hashlib.sha256(json.dumps(edit, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if resume and work_dir is None:
        raise ValueError('--resume requires the original --work-dir')
    directory = Path(work_dir).resolve() if work_dir else output.parent / f'{output.stem}.sequence-{uuid.uuid4().hex[:8]}'
    checkpoint = directory/'sequence.json'
    if resume:
        state = json.loads(checkpoint.read_text(encoding='utf-8'))
        if state['editSha256'] != fingerprint or state['output'] != str(output) or state['gameDir'] != str(game_dir):
            raise ValueError('Resume requires the same edit, profile and output')
        if state['state'] == 'completed':
            if not output.is_file():
                raise RuntimeError('Completed sequence output is missing')
            return state
    else:
        if output.exists():
            raise FileExistsError(output)
        directory.mkdir(parents=True, exist_ok=False)
        state = {'state':'queued', 'editSha256':fingerprint, 'gameDir':str(game_dir), 'output':str(output),
                 'manifest':str(checkpoint), 'edit':edit, 'jobs':[]}
        atomic_json(checkpoint, state)
    try:
        bridge_health(game_dir)
        for index, shot in enumerate(edit['shots']):
            clip = directory/f'shot-{index+1:03d}.mp4'
            if index < len(state['jobs']):
                job = Path(state['jobs'][index])
            else:
                job = submit_job(game_dir, shot['replay'], shot['range'], output=clip, plan=shot['plan'], **edit['render'])
                state['jobs'].append(str(job))
            state.update(state='rendering', shot=index+1, currentJob=job.name)
            atomic_json(checkpoint, state)
            if on_progress:
                on_progress({'manifest':str(checkpoint), 'shot':index+1, 'jobId':job.name})
            result = wait_job(job, timeout=timeout, on_progress=on_progress)
            if result['state'] != 'completed':
                raise RuntimeError(f'Shot {index+1}: {result.get("error",result["state"])}; manifest: {checkpoint}')
        state['state'] = 'assembling'
        atomic_json(checkpoint, state)
        result = assemble([directory/f'shot-{i+1:03d}.mp4' for i in range(len(edit['shots']))], output)
        state.update(result)
        atomic_json(checkpoint, state)
        return state
    except (KeyboardInterrupt, TimeoutError):
        state['state'] = 'waiting'  # Active job continues; resume waits on that exact ID.
        atomic_json(checkpoint, state)
        raise
    except Exception as exc:
        state.update(state='failed', error=str(exc))
        atomic_json(checkpoint, state)
        raise
