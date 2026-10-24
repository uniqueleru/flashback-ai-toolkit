"""Fake launcher installations and bridge builds, so tests name no real Minecraft version."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import zipfile
from unittest.mock import patch

from flashback_agent import bridges

MINECRAFT = '9.9'      # a version no real bridge build uses
LOADER = '0.30.1'


def jar(path, ident, version='fixture'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('fabric.mod.json', json.dumps({'id': ident, 'version': version}))
    return path


def sha512(path):
    return hashlib.sha512(Path(path).read_bytes()).hexdigest()


@contextmanager
def fake_bridges(root, minecraft=MINECRAFT, minimum_loader='0.30.0'):
    """A bundled bridge build for `minecraft`, whose dependencies are local fixture mods."""
    bin_dir = root/'bin'
    folder = bin_dir/minecraft
    jar(folder/'flashback-agent.jar', 'flashback_agent')
    jar(folder/'carpet-agent.jar', 'carpet_agent')
    jar(bin_dir/'flashback-background.jar', 'guard')
    dependencies = []
    for ident in ('flashback', 'fabric-api', 'carpet'):
        source = jar(root/'upstream'/f'{ident}.jar', ident)
        dependencies.append({'id': ident, 'version': '1.0', 'policy': 'exact' if ident == 'flashback' else 'minimum',
                             'file': f'{ident}.jar', 'url': source.as_uri(), 'sha512': sha512(source)})
    (folder/'bridge.json').write_text(json.dumps({'schemaVersion': 1, 'minecraft': minecraft, 'java': 21,
                                                  'fabricLoader': minimum_loader, 'flashback': '1.0',
                                                  'dependencies': dependencies}))
    with patch.object(bridges, 'BIN', bin_dir), patch.object(bridges, 'GUARD', bin_dir/'flashback-background.jar'):
        yield folder


def libraries(root, names):
    entries = []
    for name in names:
        group, artifact, version = name.split(':')
        path = root/'libraries'/group.replace('.', '/')/artifact/version/f'{artifact}-{version}.jar'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        entries.append({'name': name})
    return entries


def vanilla_json(root, minecraft=MINECRAFT, java=21):
    folder = root/'versions'/minecraft
    folder.mkdir(parents=True)
    (folder/f'{minecraft}.jar').write_bytes(b'client')
    data = {'id': minecraft, 'mainClass': 'net.minecraft.client.main.Main', 'assetIndex': {'id': '7'},
            'javaVersion': {'component': 'java-runtime-test', 'majorVersion': java},
            'libraries': libraries(root, ['com.mojang:brigadier:1.0', 'org.lwjgl:lwjgl:3.3'])}
    (folder/f'{minecraft}.json').write_text(json.dumps(data))
    (root/'assets/indexes').mkdir(parents=True, exist_ok=True)
    (root/'assets/indexes/7.json').write_text('{}')
    return data


def modrinth(root, minecraft=MINECRAFT, loader=LOADER, profile='한글 profile', launched=True, app='modrinth'):
    """A Modrinth App data folder with one Fabric profile (merged version JSON, bundled Java)."""
    meta = root/app/'meta'
    version = f'{minecraft}-{loader}'
    folder = meta/'versions'/version
    folder.mkdir(parents=True)
    (folder/f'{version}.jar').write_bytes(b'client')
    (folder/f'{version}.json').write_text(json.dumps({
        'id': version, 'mainClass': 'net.fabricmc.loader.impl.launch.knot.KnotClient', 'assetIndex': {'id': '7'},
        'javaVersion': {'component': 'java-runtime-test', 'majorVersion': 21},
        'libraries': libraries(meta, [f'net.fabricmc:fabric-loader:{loader}', f'net.fabricmc:intermediary:{minecraft}',
                                      'org.lwjgl:lwjgl:3.3'])}))
    (meta/'assets/indexes').mkdir(parents=True)
    (meta/'assets/indexes/7.json').write_text('{}')
    java = meta/'java_versions/zulu21.1-ca-jre21.0.5-win_x64/bin/javaw.exe'
    java.parent.mkdir(parents=True)
    java.touch()
    source = root/app/'profiles'/profile
    (source/'logs').mkdir(parents=True)
    (source/'options.txt').write_text('fullscreen:true\ngamma:0.7\n')
    jar(source/'mods/appearance.jar', 'appearance')
    if launched:
        (source/'logs/latest.log').write_text(f'[main/INFO]: Loading Minecraft {minecraft} with Fabric Loader {loader}\n')
    return source


def official(root, minecraft=MINECRAFT, loader=LOADER, fabric=True):
    """An official launcher folder: vanilla JSON, optional Fabric JSON inheriting from it, launcher Java."""
    game = root/'.minecraft'
    vanilla_json(game, minecraft)
    if fabric:
        folder = game/'versions'/f'fabric-loader-{loader}-{minecraft}'
        folder.mkdir(parents=True)
        (folder/f'{folder.name}.json').write_text(json.dumps({
            'id': folder.name, 'inheritsFrom': minecraft, 'mainClass': 'net.fabricmc.loader.impl.launch.knot.KnotClient',
            'libraries': libraries(game, [f'net.fabricmc:fabric-loader:{loader}', f'net.fabricmc:intermediary:{minecraft}'])}))
    java = game/'runtime/java-runtime-test/windows-x64/java-runtime-test/bin/javaw.exe'
    java.parent.mkdir(parents=True)
    java.touch()
    jar(game/'mods/appearance.jar', 'appearance')
    return game
