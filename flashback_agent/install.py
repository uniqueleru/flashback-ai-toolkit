"""`flashback-clips setup`: install the agent skill and find FFmpeg. It never touches Minecraft.

Which Minecraft installation to use is chosen later, when an agent first needs the game:
see `runtime sources` and `runtime prepare`.
"""
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from . import config, runtime

WINGET = ('--exact', '--source', 'winget', '--scope', 'user', '--silent',
          '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')


def progress(message):
    # Stdout carries the final JSON result, as in every other command.
    print(message, file=sys.stderr, flush=True)


def find_media_tools(install_missing):
    """Folders holding ffmpeg and ffprobe, installing FFmpeg with WinGet when allowed."""
    found = {name: shutil.which(name) for name in ('ffmpeg', 'ffprobe')}
    if not all(found.values()):
        winget = shutil.which('winget')
        if not (install_missing and os.name == 'nt' and winget):
            raise ValueError('FFmpeg and ffprobe are required on PATH. Install FFmpeg, then rerun setup.')
        progress('Installing FFmpeg (Gyan.FFmpeg) for the current user...')
        subprocess.run([winget, 'install', '--id', 'Gyan.FFmpeg', *WINGET], check=True, stdout=sys.stderr)
        # This process keeps its old PATH; WinGet links portable packages here.
        links = str(Path(os.environ.get('LOCALAPPDATA', Path.home()))/'Microsoft/WinGet/Links')
        found = {name: path or shutil.which(name, path=links) for name, path in found.items()}
        if not all(found.values()):
            raise ValueError('FFmpeg was installed but ffmpeg/ffprobe were not found; reopen the terminal and rerun setup')
    return list(dict.fromkeys(str(Path(path).parent) for path in found.values()))


def skill_source():
    """The skill shipped inside the wheel, or the repository copy in a source checkout."""
    package = Path(__file__).resolve().parent
    for path in (package/'skill', package.parent/'.agents/skills/flashback-clips'):
        if (path/'SKILL.md').is_file():
            return path
    raise ValueError('The flashback-clips skill files are missing from this installation')


def install_skill(target):
    source = skill_source()
    if target.exists():
        if target.is_symlink() or (hasattr(target, 'is_junction') and target.is_junction()):
            raise ValueError('Skill destination must not be a link')
        backup = target.parent.parent/'skill-backups'/('flashback-clips-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
        backup.parent.mkdir(parents=True, exist_ok=True)
        runtime.copy_tree(target, backup)
        progress(f'Previous skill backed up to {backup}')
    target.mkdir(parents=True, exist_ok=True)
    # Only replace files shipped in this skill; retain user-added files.
    for path in source.rglob('*'):
        if not path.is_file() or path.suffix not in ('.md', '.yaml'):
            continue
        dest = target/path.relative_to(source)
        if dest.is_symlink() or any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
                                    for p in dest.parents if p != target.parent):
            raise ValueError(f'Skill destination contains a link: {dest}')
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.md':
            text = path.read_text(encoding='utf-8').replace('python -m flashback_agent', 'flashback-clips')
            dest.write_text(text, encoding='utf-8')
        else:
            shutil.copy2(path, dest)


def skill_dirs(agent='auto'):
    """Skill folders for Codex and/or Claude Code; 'auto' picks the agents already set up."""
    homes = {'codex': Path(os.environ.get('CODEX_HOME', Path.home()/'.codex')),
             'claude': Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home()/'.claude'))}
    if agent in homes:
        names = [agent]
    elif agent == 'both':
        names = list(homes)
    else:
        # With neither agent set up yet, install for both so whichever is installed later finds it.
        names = [name for name, home in homes.items() if home.is_dir()] or list(homes)
    return [homes[name]/'skills/flashback-clips' for name in names]


def setup(*, agent='auto', skill_dir=None, skip_skill=False, no_dependency_install=False):
    media = find_media_tools(not no_dependency_install)
    targets = [Path(skill_dir)] if skill_dir else skill_dirs(agent)
    skills = [] if skip_skill else [path.resolve() for path in targets]
    for target in skills:
        install_skill(target)
        progress(f'Skill installed: {target}')
    config.update(version=runtime.VERSION, mediaDirs=media, skills=[str(p) for p in skills])
    return {'skills': [str(p) for p in skills], 'mediaDirs': media,
            'next': 'Ask your agent for a video. On first use it asks which Minecraft installation to use '
                    '(see `flashback-clips runtime sources`).'}
