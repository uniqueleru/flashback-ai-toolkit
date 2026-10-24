"""Declarative camera tools. No subject or cinematographic style is assumed."""
import copy
import json
import math
from pathlib import Path

INTERPOLATIONS = {'linear', 'smooth', 'ease_in', 'ease_out', 'ease_in_out', 'hold', 'hermite'}
VISUALS = {'nametags', 'chat', 'hotbar'}


def finite(value, label, low=-30_000_000, high=30_000_000):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} must be finite and between {low} and {high}')
    return value


def vector(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f'{label} must be [x, y, z]')
    return [finite(v, label) for v in value]


def look_at(position, target):
    """Minecraft yaw/pitch in degrees; +Z is yaw zero, positive pitch looks down."""
    p, t = vector(position, 'position'), vector(target, 'lookAt')
    x, y, z = [b-a for a, b in zip(p, t)]
    if math.sqrt(x*x+y*y+z*z) < 1e-8:
        raise ValueError('lookAt cannot coincide with camera position')
    return {'yaw': math.degrees(math.atan2(-x, z)),
            'pitch': -math.degrees(math.atan2(y, math.hypot(x, z)))}


def known_fields(value, allowed, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f'Unsupported {label} fields: {sorted(unknown)}')


def validate_plan(value, start=None, end=None):
    """Normalize an explicit camera plan, rejecting unsupported intent instead of ignoring it."""
    if isinstance(value, (str, Path)):
        path = Path(value)
        if path.stat().st_size > 900_000:
            raise ValueError('Camera plan exceeds 900 KB')
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    value = copy.deepcopy(value)
    known_fields(value, {'version', 'camera', 'speed', 'visuals', 'name'}, 'plan')
    if type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Camera plan version must be 1')
    camera = value.get('camera')
    if not isinstance(camera, list) or not 1 <= len(camera) <= 10000:
        raise ValueError('Camera plan requires 1..10000 keyframes')
    prior = -1
    for key in camera:
        known_fields(key, {'tick', 'position', 'yaw', 'pitch', 'lookAt', 'roll', 'fov', 'interpolation'}, 'camera keyframe')
        tick = key.get('tick')
        if type(tick) is not int or not prior < tick <= 2147483646:
            raise ValueError('Camera ticks must be non-negative, strictly increasing integers')
        prior = tick
        key['position'] = vector(key.get('position'), 'position')
        if 'lookAt' in key:
            if 'yaw' in key or 'pitch' in key:
                raise ValueError('Specify lookAt OR yaw/pitch, not both')
            key.update(look_at(key['position'], key.pop('lookAt')))
        key['yaw'] = finite(key.get('yaw'), 'yaw', -36000, 36000)
        key['pitch'] = finite(key.get('pitch'), 'pitch', -90, 90)
        key['roll'] = finite(key.get('roll', 0), 'roll', -36000, 36000)
        key['fov'] = finite(key.get('fov', 70), 'fov', 1, 170)
        key.setdefault('interpolation', 'linear')
        if key['interpolation'] not in INTERPOLATIONS:
            raise ValueError(f'Unknown interpolation: {key["interpolation"]}')
    if len(camera) > 1 and start is not None and end is not None:
        if camera[0]['tick'] > start or camera[-1]['tick'] < end:
            raise ValueError('Camera keys must cover the entire requested source range; a single key is a fixed camera')
    value['speed'] = finite(value.get('speed', 1), 'speed', .1, 8)
    visuals = value.setdefault('visuals', {})
    known_fields(visuals, VISUALS, 'visuals')
    if any(type(v) is not bool for v in visuals.values()):
        raise ValueError('Visual options must be booleans')
    if 'name' in value and not isinstance(value['name'], str):
        raise ValueError('Plan name must be a string')
    if len(json.dumps(value, allow_nan=False).encode()) > 900_000:
        raise ValueError('Camera plan exceeds 900 KB')
    return value
