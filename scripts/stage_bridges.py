"""Stage the Gradle-built bridges into flashback_agent/bin/<minecraft>/ with their bridge.json.

The Minecraft target and mod versions come from gradle.properties. The exact files and sha512
hashes of Flashback, Fabric API and Carpet come from the Modrinth API, so the worker later
downloads the same builds the bridge was compiled against.
"""
import json
from pathlib import Path
import shutil
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flashback_agent.runtime import VERSION

MODRINTH = 'https://api.modrinth.com/v2'


def properties():
    result = {}
    for line in (ROOT/'gradle.properties').read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep and not key.lstrip().startswith('#'):
            result[key.strip()] = value.strip()
    return result


def modrinth(path):
    request = urllib.request.Request(MODRINTH + path, headers={'User-Agent': 'uniqueleru/flashback-ai-toolkit'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def dependency(ident, version, policy):
    """`exact`: always this build. `minimum`: a newer build already in the user's mods is kept."""
    file = next((f for f in version['files'] if f.get('primary')), version['files'][0])
    return {'id': ident, 'version': version['version_number'], 'policy': policy, 'file': file['filename'],
            'url': file['url'], 'sha512': file['hashes']['sha512']}


def main():
    props = properties()
    minecraft = props['minecraft_version']
    query = urllib.parse.urlencode({'game_versions': json.dumps([minecraft]), 'loaders': json.dumps(['fabric'])})
    fabric_api = next((v for v in modrinth(f'/project/fabric-api/version?{query}')
                       if v['version_number'] == props['fabric_api_version']), None)
    if fabric_api is None:
        raise SystemExit(f'Fabric API {props["fabric_api_version"]} is not on Modrinth for {minecraft}')
    target = ROOT/'flashback_agent/bin'/minecraft
    target.mkdir(parents=True, exist_ok=True)
    built = ROOT/'build/libs'
    for source, destination in ((built/f'flashback-agent-{VERSION}.jar', target/'flashback-agent.jar'),
                                (built/f'carpet-agent-{VERSION}.jar', target/'carpet-agent.jar'),
                                (built/f'flashback-background-{VERSION}.jar', target.parent/'flashback-background.jar')):
        if not source.is_file():
            raise SystemExit(f'Missing {source}. Run `gradlew build` first.')
        shutil.copy2(source, destination)
        print(destination)
    manifest = {'schemaVersion': 1, 'minecraft': minecraft, 'java': int(props['java_version']),
                'fabricLoader': props['loader_version'], 'flashback': props['flashback_version'],
                # The bridge's mixins target Flashback internals; Fabric API and Carpet are used through their APIs.
                'dependencies': [dependency('flashback', modrinth(f'/version/{props["flashback_modrinth"]}'), 'exact'),
                                 dependency('fabric-api', fabric_api, 'minimum'),
                                 dependency('carpet', modrinth(f'/version/{props["carpet_modrinth"]}'), 'minimum')]}
    if manifest['dependencies'][0]['version'] != props['flashback_version']:
        raise SystemExit('flashback_modrinth does not point at flashback_version')
    (target/'bridge.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(target/'bridge.json')


if __name__ == '__main__':
    main()
