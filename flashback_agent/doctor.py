"""`flashback-clips doctor`: check setup, the worker and the live bridge in one report."""
import os
from pathlib import Path
import shutil
import sys

from . import bridge_health, bridges, config, runtime


def doctor(game_dir=None):
    checks = []

    def check(name, ok, detail):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})

    data = config.load()
    check('python', sys.version_info >= (3, 11), sys.version.split()[0])
    check('platform', os.name == 'nt', 'Windows' if os.name == 'nt' else 'The background runtime currently requires Windows')
    for tool in ('ffmpeg', 'ffprobe'):
        path = shutil.which(tool)
        check(tool, path, path or f'{tool} is not on PATH; run setup or install FFmpeg')
    supported = bridges.supported()
    check('bridges', supported, f'Bridge builds for Minecraft {", ".join(supported)}' if supported else
          'No bridge builds in this installation; reinstall the package')
    if data.get('skills'):
        missing = [path for path in data['skills'] if not (Path(path)/'SKILL.md').is_file()]
        check('skill', not missing, f'Missing: {", ".join(missing)}; rerun setup' if missing else ', '.join(data['skills']))
    bridge = None
    if not game_dir:
        check('worker', False, 'No worker yet: run `runtime sources`, let the user choose an installation, '
                               'then `runtime prepare --source PATH`')
    else:
        root = Path(game_dir)
        if (root/'.background/instance.json').exists() or str(root) == data.get('instance'):
            try:
                _, manifest = runtime.load(root)
                java = Path(manifest['java'])
                check('worker', java.is_file(),
                      f'{root}: Minecraft {manifest["minecraft"]} / Fabric {manifest["fabric"]} from {manifest["sourceProfile"]}'
                      if java.is_file() else f'Java runtime is missing: {java}')
            except (OSError, ValueError, KeyError) as exc:
                check('worker', False, f'{root} is not a prepared worker ({exc}); run `runtime prepare` again')
        try:
            bridge = bridge_health(root)
            check('bridge', True, f'Minecraft {bridge["minecraft"]} / Flashback {bridge["flashback"]} bridge is live')
        except (OSError, ValueError, RuntimeError) as exc:
            check('bridge', False, f'{exc} For the background worker: flashback-clips runtime start --instance "{root}"')
    return {'ok': all(item['ok'] for item in checks), 'checks': checks, 'bridge': bridge}
