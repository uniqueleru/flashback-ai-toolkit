"""Discoverable, structured Carpet and recording tools; no creative presets."""
import json
import math
from pathlib import Path
import time
import uuid

from . import atomic_json, wait_job, read_json


def number(low, high, integer=False):
    return {'type': 'integer' if integer else 'number', 'minimum': low, 'maximum': high}


NAME = {'type': 'string', 'pattern': r'^[A-Za-z0-9_]{1,16}$'}
VECTOR = {'type': 'array', 'items': number(-29999984, 29999984), 'minItems': 3, 'maxItems': 3}
BOOL = {'type': 'boolean'}
TEXT = {'type': 'string', 'minLength': 1}
TICKS = number(1, 12000, True)


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


def tool(name, description, properties=None, required=(), read_only=False):
    return {'name': name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': properties or {},
                            'required': list(required), 'additionalProperties': False},
            'annotations': {'readOnlyHint': read_only, 'openWorldHint': False}}


TOOLS = [
    tool('carpet_list', 'List online players, distinguishing Carpet bots from humans, with authoritative positions and server tick.', read_only=True),
    tool('carpet_state', 'Inspect one existing Carpet fake player and remaining tool-controlled action durations.', {'name': NAME}, ['name'], True),
    tool('carpet_spawn', 'Spawn a Carpet fake player at explicit coordinates. Completes when the bot joins; existing names are rejected.',
         {'name': NAME, 'position': VECTOR, 'yaw': number(-360000, 360000), 'pitch': number(-90, 90),
          'dimension': TEXT, 'gameMode': enum('creative', 'survival', 'adventure', 'spectator')}, ['name', 'position']),
    tool('carpet_move', 'Apply forward/strafe inputs for ticks, then stop movement. Forward=1, backward=-1; strafe=1 left, -1 right. No pathfinding. Other action channels continue.',
         {'name': NAME, 'forward': number(-1, 1), 'strafe': number(-1, 1), 'sprint': BOOL, 'sneak': BOOL, 'ticks': TICKS}, ['name', 'ticks']),
    tool('carpet_look', 'Set yaw/pitch OR look at a world coordinate. Minecraft yaw 0 faces +Z, -90 faces +X; positive pitch looks down.',
         {'name': NAME, 'yaw': number(-360000, 360000), 'pitch': number(-90, 90), 'at': VECTOR}, ['name']),
    tool('carpet_action', 'Use Carpet actions once, continuously or at a tick interval; stop ends just that action. Ongoing actions require ticks. Completion means input accepted, not proof of a hit, placement or jump.',
         {'name': NAME, 'action': enum('use', 'attack', 'jump', 'drop', 'dropStack', 'swapHands'),
          'mode': enum('once', 'continuous', 'interval', 'stop'), 'interval': TICKS, 'ticks': TICKS}, ['name', 'action', 'mode']),
    tool('carpet_stop', 'Stop all current movement and action inputs for one Carpet bot.', {'name': NAME}, ['name']),
    tool('carpet_remove', 'Remove one Carpet fake player from the world; never targets a human.', {'name': NAME}, ['name']),
    tool('carpet_inventory', 'Read item IDs, counts, slots and selected hotbar (1..9). Does not report every item component.', {'name': NAME}, ['name'], True),
    tool('carpet_hotbar', 'Select a bot hotbar slot (1..9).', {'name': NAME, 'slot': number(1, 9, True)}, ['name', 'slot']),
    tool('carpet_mount', 'Mount a nearby rideable entity, or dismount; inspect resulting state to confirm outcome.', {'name': NAME, 'dismount': BOOL}, ['name']),
    tool('carpet_teleport', 'Stop all bot inputs and teleport within its current dimension. This is a discontinuity, not walking.', {'name': NAME, 'position': VECTOR}, ['name', 'position']),
    tool('carpet_observe', 'Inspect loaded blocks and nearby entities around a bot, radius 1..8 (default 4). Does not load missing chunks or plan routes.', {'name': NAME, 'radius': number(1, 8, True)}, ['name'], True),
    tool('carpet_command', 'Execute one privileged Minecraft/Carpet server command for explicit world setup or advanced operations. Can affect humans and terrain; unlike bot tools it is not restricted to fake players. Returns command result and messages, including command-level failures.', {'command': {**TEXT, 'maxLength': 8192}}, ['command']),
    tool('record_status', 'Inspect live client, observer position, loaded players, paused state and recording ownership.', read_only=True),
    tool('record_start', 'Start Flashback recording in a live client. Requires no existing recording. Returns recordingId for subsequent stop; records only what this client receives. Pause/resume is not exposed.'),
    tool('record_stop', 'Finish an owned recording and publish a verified new replay ZIP; output must not exist.', {'recordingId': TEXT, 'output': TEXT}, ['recordingId', 'output']),
    tool('world_open', 'Open an existing singleplayer save folder in an idle client. Does not create a world, replace the current world or bypass load prompts.', {'save': TEXT}, ['save']),
    tool('world_close', 'Save and leave the currently open world/replay. Refuses active recording/export. This disconnects the client.'),
    tool('runtime_shutdown', 'Gracefully save and stop only a managed background client with the matching launchId. Refuses active recording/export/world load.', {'launchId': TEXT}, ['launchId']),
]
BY_NAME = {t['name']: t for t in TOOLS}


def validate(value, schema, path='arguments'):
    """Validate the small JSON Schema subset used by this contract."""
    import re
    typ = schema['type']
    good = {'object': isinstance(value, dict), 'array': isinstance(value, list),
            'number': type(value) in (int, float), 'integer': type(value) is int,
            'string': isinstance(value, str), 'boolean': type(value) is bool}[typ]
    if not good:
        raise ValueError(f'{path} must be {typ}')
    if typ == 'object':
        missing = set(schema.get('required', [])) - value.keys()
        extra = value.keys() - schema.get('properties', {}).keys()
        if missing or extra:
            raise ValueError(f'{path}: missing={sorted(missing)}, unknown={sorted(extra)}')
        for key, item in value.items():
            validate(item, schema['properties'][key], f'{path}.{key}')
    if typ == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', math.inf):
            raise ValueError(f'{path}: invalid array length')
        for i, item in enumerate(value):
            validate(item, schema['items'], f'{path}[{i}]')
    if typ in ('number', 'integer'):
        if not math.isfinite(value) or not schema.get('minimum', -math.inf) <= value <= schema.get('maximum', math.inf):
            raise ValueError(f'{path}: number out of range')
    if typ == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', math.inf):
            raise ValueError(f'{path}: invalid string length')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            raise ValueError(f'{path}: invalid format')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path}: unsupported value')


def validate_call(name, arguments):
    if name not in BY_NAME:
        raise ValueError(f'Unknown tool: {name}')
    validate(arguments, BY_NAME[name]['inputSchema'])
    a = arguments
    if name == 'carpet_move':
        if not {'forward', 'strafe'} & a.keys():
            raise ValueError('Specify forward or strafe')
        if a.get('sprint') and a.get('sneak'):
            raise ValueError('Cannot sprint and sneak together')
    if name == 'carpet_look':
        if ('at' in a) == bool({'yaw', 'pitch'} & a.keys()) or ('at' not in a and not {'yaw', 'pitch'} <= a.keys()):
            raise ValueError('Specify at OR both yaw and pitch')
    if name == 'carpet_action':
        if (a['mode'] == 'interval') != ('interval' in a):
            raise ValueError('Only interval mode requires interval')
        if (a['mode'] in ('continuous', 'interval')) != ('ticks' in a):
            raise ValueError('Only continuous/interval modes require ticks')
    if name == 'carpet_command' and ('\n' in a['command'] or '\r' in a['command'] or not a['command'].strip()):
        raise ValueError('Expected one server command')


def inbox_path(name, game_dir=None, server_dir=None):
    if name.startswith('carpet_'):
        directory = server_dir or game_dir
        sub = 'carpet-agent'
    else:
        directory = game_dir
        sub = 'flashback-agent/live'
    if not directory:
        raise ValueError('Provide game_dir (recording/integrated server) or server_dir (dedicated Carpet server)')
    return Path(directory).resolve(strict=True) / sub


def submit_tool(name, arguments, *, game_dir=None, server_dir=None, ttl=120):
    validate_call(name, arguments)
    if not math.isfinite(ttl) or not 1 <= ttl <= 3600:
        raise ValueError('ttl must be 1..3600 seconds')
    root = inbox_path(name, game_dir, server_dir)
    health_path = root / 'bridge.json'
    if not health_path.is_file():
        raise RuntimeError(f'Tool bridge not running: {root}. Carpet tools require a live world/server.')
    health = read_json(health_path)
    if health.get('state') == 'stopped' or time.time()*1000-health.get('updatedAt', 0) > 15000:
        raise RuntimeError('Tool bridge is stopped or stale; start the matching world/client')
    if health.get('protocolVersion') != 1:
        raise RuntimeError('Tool bridge protocol mismatch; update the bridge in this world/client')
    args = dict(arguments)
    if name == 'record_stop':
        output = Path(args['output']).resolve()
        if output.exists() or output.suffix.lower() != '.zip':
            raise ValueError('Use a new .zip output path')
        args['output'] = str(output)
    job = root / 'jobs' / uuid.uuid4().hex
    job.mkdir(parents=True)
    atomic_json(job/'request.json', {'schemaVersion': 1, 'id': job.name, 'tool': name,
                                    'arguments': args, 'session': health['session'],
                                    'expiresAt': int((time.time()+ttl)*1000)})
    return job


def call_tool(name, arguments, *, game_dir=None, server_dir=None, timeout=180, on_progress=None):
    job = submit_tool(name, arguments, game_dir=game_dir, server_dir=server_dir)
    try:
        result = wait_job(job, timeout=timeout, poll=.1, on_progress=on_progress)
    except TimeoutError as exc:
        raise TimeoutError(f'{exc} ; jobDir={job}') from exc
    return {**result, 'jobDir': str(job)}
