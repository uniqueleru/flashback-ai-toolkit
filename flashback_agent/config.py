"""Per-user settings written by `setup` and `runtime prepare`: media tools, skills, chosen installation and worker."""
import json
import os
from pathlib import Path
import sys

from . import atomic_json


def home():
    """Data folder for the worker, downloads and config.json; FLASHBACK_CLIPS_HOME overrides it."""
    if os.environ.get('FLASHBACK_CLIPS_HOME'):
        return Path(os.environ['FLASHBACK_CLIPS_HOME'])
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'FlashbackClips'
    if sys.platform == 'darwin':
        return Path.home()/'Library/Application Support/FlashbackClips'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'flashback-clips'


def load():
    path = home()/'config.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise ValueError(f'{path} is not valid JSON; fix or delete it and rerun setup') from exc


def update(**values):
    data = {**load(), **values}
    home().mkdir(parents=True, exist_ok=True)
    atomic_json(home()/'config.json', data)
    return data


def apply_environment():
    """Default the game folder and media tools to what setup chose; explicit environment wins."""
    data = load()
    if data.get('instance'):
        os.environ.setdefault('FLASHBACK_GAME_DIR', data['instance'])
    current = os.environ.get('PATH', '').split(os.pathsep)
    missing = [path for path in data.get('mediaDirs', ()) if path not in current]
    if missing:
        os.environ['PATH'] = os.pathsep.join([*missing, *current])
