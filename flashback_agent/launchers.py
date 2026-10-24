"""Turn the game files a Minecraft launcher already installed into a launch spec for the worker.

The user names the installation: a Modrinth App profile folder, or the official launcher's game
folder. Nothing in the launcher is changed. When Fabric is missing it is downloaded into the
toolkit's own data folder, and only the worker uses it.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import urllib.request
import zipfile

from . import bridges, config

KNOT = 'net.fabricmc.loader.impl.launch.knot.KnotClient'
VANILLA = 'net.minecraft.client.main.Main'
FABRIC_META = 'https://meta.fabricmc.net/v2/versions/loader'
FABRIC_LOG = re.compile(r'Loading Minecraft (\S+) with Fabric Loader (\S+)')


def allowed(rules):
    if not rules:
        return True
    result = False
    for rule in rules:
        system = rule.get('os', {})
        if system.get('name', 'windows') != 'windows':
            continue
        if system.get('arch', 'amd64') not in ('amd64', 'x86_64'):
            continue
        if 'version' in system and not re.search(system['version'], platform.version()):
            continue
        if any(value is True for value in rule.get('features', {}).values()):
            continue
        result = rule['action'] == 'allow'
    return result


def library_path(library):
    artifact = (library.get('downloads') or {}).get('artifact')
    if artifact:
        return artifact['path']
    parts = library['name'].split(':')
    if len(parts) not in (3, 4):
        raise ValueError('Unsupported Maven coordinate')
    group, name, version = parts[:3]
    suffix = '-' + parts[3] if len(parts) == 4 else ''
    return f'{group.replace(".", "/")}/{name}/{version}/{name}-{version}{suffix}.jar'


def official_runtimes(root):
    """Where the official launcher keeps the Java runtimes it downloads."""
    local = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))
    programs = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))
    return [root/'runtime', local/'Packages/Microsoft.4297127D64EC6_8wekyb3d8bbwe/LocalCache/Local/runtime',
            programs/'Minecraft Launcher/runtime']


def detect(path, launcher='auto', *, meta_dir=None, minecraft_dir=None):
    """Which launcher installed this folder, and where its versions, libraries and assets are."""
    game = Path(path).resolve(strict=True)
    if launcher in ('auto', 'modrinth'):
        meta = Path(meta_dir).resolve(strict=True) if meta_dir else game.parent.parent/'meta'
        if (meta/'versions').is_dir() and (meta_dir or game.parent.name == 'profiles'):
            return {'launcher': 'modrinth', 'gameDir': game, 'root': meta, 'javaRoots': [meta/'java_versions']}
    if launcher in ('auto', 'official'):
        root = Path(minecraft_dir).resolve(strict=True) if minecraft_dir else game
        if (root/'versions').is_dir() and (root/'libraries').is_dir():
            return {'launcher': 'official', 'gameDir': game, 'root': root, 'javaRoots': official_runtimes(root)}
    raise ValueError(f'{game} is neither a Modrinth profile folder nor an official launcher game folder. '
                     'For a custom layout pass --launcher with --meta-dir (Modrinth) or --minecraft-dir (official).')


def versions(source):
    """Installed vanilla and Fabric version JSONs: id, Minecraft version, Fabric Loader version or None."""
    result = []
    folder = source['root']/'versions'
    for entry in sorted(p for p in folder.iterdir() if p.is_dir()):
        file = entry/(entry.name + '.json')
        try:
            data = json.loads(file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        fabric = {}
        for library in data.get('libraries', ()):
            parts = library.get('name', '').split(':')
            if len(parts) >= 3 and parts[0] == 'net.fabricmc':
                fabric[parts[1]] = parts[2]
        if data.get('mainClass') == KNOT:
            minecraft = data.get('inheritsFrom') or fabric.get('intermediary')
            result.append({'id': entry.name, 'minecraft': minecraft, 'fabric': fabric.get('fabric-loader'),
                           'folder': entry, 'data': data})
        elif data.get('mainClass') == VANILLA and 'inheritsFrom' not in data:
            result.append({'id': entry.name, 'minecraft': data.get('id', entry.name), 'fabric': None,
                           'folder': entry, 'data': data})
    return result


def last_launch(source):
    """(Minecraft, Fabric Loader) from the installation's latest Fabric log, if it has one."""
    log = source['gameDir']/'logs/latest.log'
    try:
        with log.open(encoding='utf-8', errors='replace') as stream:
            for _, line in zip(range(400), stream):
                match = FABRIC_LOG.search(line)
                if match:
                    return match.group(1), match.group(2)
    except OSError:
        pass
    return None


def choose_minecraft(source, requested=None):
    if requested:
        return requested
    launched = last_launch(source)
    if launched:
        return launched[0]
    installed = sorted({v['minecraft'] for v in versions(source) if v['minecraft']}, key=bridges.version_key)
    candidates = [version for version in installed if version in bridges.builds()]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError('Could not tell which Minecraft version this installation uses. '
                     f'Installed: {", ".join(installed) or "none"}; bridge builds: {", ".join(bridges.supported()) or "none"}. '
                     'Pass --minecraft-version.')


def other_loader_mods(source):
    """Forge/NeoForge mods in the installation, which a Fabric worker cannot load."""
    found = []
    for jar in sorted((source['gameDir']/'mods').glob('*.jar')):
        try:
            with zipfile.ZipFile(jar) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile):
            continue
        if 'fabric.mod.json' not in names and names & {'META-INF/mods.toml', 'META-INF/neoforge.mods.toml'}:
            found.append(jar.name)
    return found


def _json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'uniqueleru/flashback-ai-toolkit'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_fabric(minecraft, minimum, cache):
    """Newest stable Fabric Loader profile at or above the bridge's minimum, with verified libraries."""
    loaders = [item['loader']['version'] for item in _json(f'{FABRIC_META}/{minecraft}')
               if item['loader'].get('stable') and bridges.version_key(item['loader']['version']) >= bridges.version_key(minimum)]
    if not loaders:
        raise ValueError(f'Fabric has no stable loader {minimum} or later for Minecraft {minecraft}')
    loader = max(loaders, key=bridges.version_key)
    profile = _json(f'{FABRIC_META}/{minecraft}/{loader}/profile/json')
    for library in profile['libraries']:
        if not library.get('sha512'):
            raise ValueError(f'Fabric metadata has no sha512 for {library["name"]}; refusing an unverified library')
        relative = library_path(library)
        target = cache/relative
        if not (target.is_file() and bridges.digest(target) == library['sha512']):
            bridges.download(library['url'].rstrip('/') + '/' + relative, target, library['sha512'])
        library['root'] = str(cache)
    return profile, loader


def _merge(child, parent):
    seen, libraries = set(), []
    for library in [*child.get('libraries', ()), *parent.get('libraries', ())]:
        key = ':'.join(library['name'].split(':')[:2] + library['name'].split(':')[3:])
        if key not in seen:
            seen.add(key)
            libraries.append(library)
    return {**parent, **{k: v for k, v in child.items() if k != 'libraries'}, 'libraries': libraries}


def find_java(source, data, java=None):
    if java:
        path = Path(java).resolve(strict=True)
        if path.name.lower() == 'java.exe':
            path = path.with_name('javaw.exe').resolve(strict=True)
        if path.name.lower() != 'javaw.exe':
            raise ValueError('Use javaw.exe to avoid a console window')
        return path
    major = data.get('javaVersion', {}).get('majorVersion')
    component = data.get('javaVersion', {}).get('component')
    found = []
    for root in source['javaRoots']:
        if source['launcher'] == 'modrinth' and root.is_dir():
            found += [p/'bin/javaw.exe' for p in root.iterdir()
                      if 'win_x64' in p.name and re.search(rf'(?:jre|jdk)-?{major}(?:\.|$|-)', p.name)]
        elif component:
            found.append(root/component/'windows-x64'/component/'bin/javaw.exe')
    found = sorted((p for p in found if p.is_file()), key=lambda p: bridges.version_key(p.parent.parent.name), reverse=True)
    if not found:
        raise ValueError(f'Java {major} was not found where the {source["launcher"]} launcher keeps it. '
                         f'Launch this version once in the launcher, or pass --java with a Java {major} javaw.exe.')
    return found[0].resolve()


def resolve(source, minecraft, *, install_fabric=False, java=None, cache=None):
    """Classpath, assets and Java for launching `minecraft` with Fabric from this installation."""
    build = bridges.for_version(minecraft)
    foreign = other_loader_mods(source)
    if foreign:
        raise ValueError(f'{len(foreign)} mods here are for Forge/NeoForge (e.g. {foreign[0]}), not Fabric. '
                         'Choose a Fabric installation or a vanilla one.')
    installed = versions(source)
    launched = last_launch(source)
    fabric = [v for v in installed if v['minecraft'] == minecraft and v['fabric']
              and bridges.version_key(v['fabric']) >= bridges.version_key(build['fabricLoader'])]
    vanilla = next((v for v in installed if v['minecraft'] == minecraft and not v['fabric']), None)
    if fabric:
        preferred = [v for v in fabric if launched and v['fabric'] == launched[1]]
        entry = (preferred or sorted(fabric, key=lambda v: bridges.version_key(v['fabric'])))[-1]
        loader, data = entry['fabric'], entry['data']
        jar = entry['folder']/(entry['id'] + '.jar')
        if 'inheritsFrom' in data:
            parent = next((v for v in installed if v['id'] == data['inheritsFrom']), None)
            if parent is None:
                raise ValueError(f'{entry["id"]} needs Minecraft {data["inheritsFrom"]}; launch it once in the launcher')
            data, jar = _merge(data, parent['data']), parent['folder']/(parent['id'] + '.jar')
    elif not install_fabric:
        raise ValueError(f'Fabric Loader {build["fabricLoader"]} or later for Minecraft {minecraft} is not installed in this '
                         f'{source["launcher"]} installation. Rerun with --install-fabric to download it for the worker only; '
                         'the launcher is not changed.')
    elif vanilla is None:
        raise ValueError(f'Minecraft {minecraft} game files were not found. Launch Minecraft {minecraft} once in the '
                         f'{source["launcher"]} launcher, then retry.')
    else:
        profile, loader = fetch_fabric(minecraft, build['fabricLoader'], Path(cache or config.home())/'libraries')
        data, jar = _merge(profile, vanilla['data']), vanilla['folder']/(vanilla['id'] + '.jar')
    if data.get('mainClass') != KNOT:
        raise ValueError('Expected a Fabric client runtime')
    classpath = []
    for library in data['libraries']:
        if allowed(library.get('rules')) and library.get('include_in_classpath', True):
            root = Path(library.get('root') or source['root']/'libraries')
            path = (root/library_path(library)).resolve()
            if root.resolve() not in path.parents:
                raise ValueError('Library path escapes its libraries folder')
            if not path.is_file():
                raise ValueError(f'Missing library {path}. Launch Minecraft {minecraft} once in the launcher, then retry.')
            classpath.append(str(path))
    classpath.append(str(jar.resolve(strict=True)))
    assets = (source['root']/'assets').resolve(strict=True)
    asset_index = str(data['assetIndex']['id'])
    (assets/'indexes'/(asset_index + '.json')).resolve(strict=True)
    return {'minecraft': minecraft, 'fabric': loader, 'mainClass': data['mainClass'], 'classpath': classpath,
            'assets': str(assets), 'assetIndex': asset_index, 'javaMajor': data.get('javaVersion', {}).get('majorVersion'),
            'java': str(find_java(source, data, java)), 'build': build}


def _modrinth_dirs():
    appdata = Path(os.environ.get('APPDATA', Path.home()))
    dirs = [appdata/'ModrinthApp', appdata/'com.modrinth.theseus']
    for base in list(dirs):
        try:
            # Only the app's chosen data folder is read; account tables are never queried.
            with closing(sqlite3.connect(f'file:{base/"app.db"}?mode=ro', uri=True)) as db:
                custom = db.execute('SELECT custom_dir FROM settings').fetchone()
            if custom and custom[0]:
                dirs.insert(0, Path(custom[0]))
        except (sqlite3.Error, OSError):
            pass
    return dirs


def sources():
    """Installations to offer the user. They still choose one, or give another path."""
    recorded = config.load().get('source')
    paths = [Path(recorded)] if recorded else []
    for base in _modrinth_dirs():
        if (base/'profiles').is_dir():
            paths += sorted(p for p in (base/'profiles').iterdir() if p.is_dir())
    official = Path(os.environ.get('APPDATA', Path.home()))/'.minecraft'
    if official.is_dir():
        paths.append(official)
    result = []
    for path in dict.fromkeys(paths):
        try:
            source = detect(path)
            launched = last_launch(source)
            minecraft = launched[0] if launched else None
            result.append({'launcher': source['launcher'], 'path': str(source['gameDir']), 'lastLaunched': minecraft,
                           'fabric': launched[1] if launched else None,
                           'bridge': minecraft in bridges.builds() if minecraft else None})
        except (OSError, ValueError) as exc:
            result.append({'path': str(path), 'error': str(exc)})
    return {'sources': result, 'supported': bridges.supported()}
