"""Bridge builds shipped in this package: one folder per Minecraft version under bin/.

Each folder holds the client and Carpet bridges built for that version and a bridge.json
listing the Java version, minimum Fabric Loader and the exact Flashback, Fabric API and
Carpet files the bridge was built against. scripts/stage_bridges.py writes these folders.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.request
import uuid
import zipfile

BIN = Path(__file__).resolve().parent/'bin'
# The JVM premain guard patches LWJGL only, so one build serves every Minecraft version.
GUARD = BIN/'flashback-background.jar'


def mod_info(path):
    with zipfile.ZipFile(path) as archive:
        if 'fabric.mod.json' not in archive.namelist():
            return {}
        # Fabric/Gson accepts literal line breaks in third-party descriptions.
        return json.loads(archive.read('fabric.mod.json'), strict=False)


def version_key(version):
    """Order release versions such as 0.19.5 < 0.20.1; build metadata after '+' is ignored."""
    return tuple(int(part) if part.isdecimal() else 0 for part in re.split(r'[.-]', version.partition('+')[0]))


def builds():
    """{Minecraft version: manifest} for every bundled bridge build."""
    result = {}
    for path in sorted(BIN.glob('*/bridge.json')):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['folder'] = str(path.parent)
        result[manifest['minecraft']] = manifest
    return result


def supported():
    return sorted(builds(), key=version_key)


def for_version(minecraft):
    available = builds()
    if minecraft not in available:
        listed = ', '.join(supported()) or 'none in this installation'
        raise ValueError(f'No bridge build for Minecraft {minecraft}. Supported versions: {listed}')
    return available[minecraft]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha512').hexdigest()


def download(url, target, sha512, check=None):
    """Download to `target` only if the file matches `sha512` (and passes `check`)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.' + uuid.uuid4().hex + '.part')
    print(f'Downloading {target.name}...', file=sys.stderr, flush=True)
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'uniqueleru/flashback-ai-toolkit'})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open('xb') as stream:
            shutil.copyfileobj(response, stream, length=1024*1024)
        if digest(partial) != sha512:
            raise ValueError(f'Checksum mismatch for {target.name}; download was not installed')
        if check:
            check(partial)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def fetch_dependency(dependency, cache, existing=()):
    """A verified copy of one pinned mod, reusing a matching file the user already has."""
    for path in existing:
        if digest(path) == dependency['sha512']:
            return Path(path)
    target = cache/dependency['file']
    if target.is_file() and digest(target) == dependency['sha512']:
        return target

    def same_mod(path):
        if mod_info(path).get('id') != dependency['id']:
            raise ValueError(f'Unexpected mod ID in {dependency["file"]}')
    return download(dependency['url'], target, dependency['sha512'], same_mod)
