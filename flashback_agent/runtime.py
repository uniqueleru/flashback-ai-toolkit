"""Windows background client: isolated profile, early native guard, no shell/launcher UI.

Uses the game files a Modrinth or official launcher installation already has (see launchers.py).
Authentication stores are never read; this local offline worker supports copied singleplayer
worlds and replays.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from . import atomic_json, bridges, config, launchers, read_json
from .bridges import mod_info

VERSION = '0.4.0'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def windows():
    if os.name != 'nt':
        raise RuntimeError('Managed background launcher currently supports Windows only')


def desktop_name(handle):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    buffer = ctypes.create_unicode_buffer(256)
    needed = wintypes.DWORD()
    if not user.GetUserObjectInformationW(handle, 2, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


def input_desktop():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user.OpenInputDesktop.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    handle = user.OpenInputDesktop(0, False, 1)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return desktop_name(handle)
    finally:
        user.CloseDesktop(handle)


@contextmanager
def private_desktop():
    """A separate Win32 desktop isolates even third-party child-process windows.

    Never calls SwitchDesktop or changes the user's input desktop. Keep the
    handle through startup until the worker's UI threads have connected.
    """
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPVOID,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
    user.CreateDesktopW.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    name = 'FlashbackAgent_' + uuid.uuid4().hex
    handle = user.CreateDesktopW(name, None, None, 0, 0x01FF, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if input_desktop() == name:
            raise RuntimeError('Worker desktop unexpectedly became the input desktop')
        yield name
    finally:
        user.CloseDesktop(handle)


class BackgroundProcess:
    """CreateProcessW is required: Python's STARTUPINFO wrapper omits lpDesktop."""
    def __init__(self, arguments, *, cwd, env, output, desktop):
        import msvcrt
        class Startup(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
                        ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR),
                        *[(field, wintypes.DWORD) for field in ('dwX','dwY','dwXSize','dwYSize',
                          'dwXCountChars','dwYCountChars','dwFillAttribute','dwFlags')],
                        ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                        ('lpReserved2', ctypes.POINTER(wintypes.BYTE)),
                        ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)]
        class Extended(ctypes.Structure):
            _fields_ = [('StartupInfo', Startup), ('lpAttributeList', wintypes.LPVOID)]
        class Information(ctypes.Structure):
            _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                        ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]
        self.kernel = kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID,
            wintypes.LPVOID, wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR,
            ctypes.POINTER(Extended), ctypes.POINTER(Information)]
        kernel.CreateProcessW.restype = wintypes.BOOL
        kernel.InitializeProcThreadAttributeList.argtypes = [wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.c_size_t)]
        kernel.UpdateProcThreadAttribute.argtypes = [wintypes.LPVOID,wintypes.DWORD,ctypes.c_size_t,wintypes.LPVOID,ctypes.c_size_t,wintypes.LPVOID,wintypes.LPVOID]
        kernel.DeleteProcThreadAttributeList.argtypes = [wintypes.LPVOID]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE,wintypes.UINT]
        size = ctypes.c_size_t()
        kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        if not kernel.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            with open(os.devnull, 'rb') as null:
                handles = (wintypes.HANDLE * 2)(msvcrt.get_osfhandle(null.fileno()), msvcrt.get_osfhandle(output.fileno()))
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                try:
                    if not kernel.UpdateProcThreadAttribute(attributes, 0, 0x20002, handles, ctypes.sizeof(handles), None, None):
                        raise ctypes.WinError(ctypes.get_last_error())
                    startup = Extended()
                    startup.StartupInfo.cb = ctypes.sizeof(Extended)
                    startup.StartupInfo.lpDesktop = 'WinSta0\\' + desktop
                    startup.StartupInfo.dwFlags = 0x101  # STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
                    startup.StartupInfo.wShowWindow = 0
                    startup.StartupInfo.hStdInput = handles[0]
                    startup.StartupInfo.hStdOutput = startup.StartupInfo.hStdError = handles[1]
                    startup.lpAttributeList = ctypes.cast(attributes, wintypes.LPVOID)
                    command = ctypes.create_unicode_buffer(subprocess.list2cmdline(arguments))
                    environment = ctypes.create_unicode_buffer('\0'.join(f'{k}={v}' for k,v in sorted(env.items()))+'\0\0')
                    info = Information()
                    flags = 0x08000000 | 0x4000 | 0x400 | 0x80000
                    if not kernel.CreateProcessW(arguments[0], command, None, None, True, flags,
                            environment, str(cwd), ctypes.byref(startup), ctypes.byref(info)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    self.pid, self.handle = info.dwProcessId, info.hProcess
                    self.returncode = None
                    kernel.CloseHandle(info.hThread)
                finally:
                    for handle in handles:
                        os.set_handle_inheritable(handle, False)
        finally:
            kernel.DeleteProcThreadAttributeList(attributes)

    def poll(self):
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.returncode = None if code.value == 259 else code.value
        return self.returncode

    def terminate(self):
        if not self.kernel.TerminateProcess(self.handle, 78):
            raise ctypes.WinError(ctypes.get_last_error())

    def wait(self, timeout):
        if self.kernel.WaitForSingleObject(self.handle, int(timeout*1000)) == 258:
            raise TimeoutError('Worker did not exit')
        return self.poll()

    def __del__(self):
        if getattr(self, 'handle', None):
            self.kernel.CloseHandle(self.handle)


def process_identity(pid):
    """PID + creation time prevents treating a recycled PID as our worker."""
    windows()
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # nonexistent PID
            return None
        raise OSError(error, 'Cannot inspect managed process')
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if code.value != 259:
            return None
        stamps = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(s) for s in stamps)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def window_state(pid):
    """Observe this process only; never hide, activate or move somebody else's window."""
    windows()
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetForegroundWindow.restype = wintypes.HWND
    own, visible = [], []
    @callback
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            own.append(int(hwnd))
            if user.IsWindowVisible(hwnd):
                visible.append(int(hwnd))
        return True
    user.EnumWindows(visit, 0)
    foreground = user.GetForegroundWindow()
    owner = wintypes.DWORD()
    if foreground:
        user.GetWindowThreadProcessId(foreground, ctypes.byref(owner))
    return {'windowCount': len(own), 'visibleWindows': visible, 'foreground': owner.value == pid}


def copy_tree(source, target, *, skip_session_lock=False):
    # A clone must not retain junctions into the user's active profile.
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(directory)/name
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError(f'Cannot clone linked profile entry: {path}')
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('session.lock') if skip_session_lock else None)


@contextmanager
def closed_save(world):
    import msvcrt
    # Minecraft locks session.lock while the save is open. Hold the same byte
    # across the copy so it cannot be opened midway through the snapshot.
    with (world/'session.lock').open('r+b') as stream:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Close the source world before copying it') from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def prepare(source, instance=None, *, launcher='auto', minecraft=None, install_fabric=False, meta_dir=None,
            minecraft_dir=None, java=None, save=None, cache=None):
    """Clone a launcher installation into a new worker with the bridge build for its Minecraft version.

    Rerunning with the same source reuses a completed worker; nothing existing is overwritten.
    """
    windows()
    found = launchers.detect(source, launcher, meta_dir=meta_dir, minecraft_dir=minecraft_dir)
    source = found['gameDir']
    cache = Path(cache or config.home())
    target = Path(instance or cache/'worker').resolve()
    if target == source or source in target.parents or target in source.parents:
        raise ValueError('Worker must be separate from the source installation')
    if target.exists():
        # Retry only a completed, compatible preparation; never erase an incomplete folder.
        try:
            _, manifest = load(target)
        except (OSError, ValueError, KeyError) as exc:
            raise ValueError(f'{target} exists but is not a completed worker. Choose a new --instance; '
                             'existing files were preserved.') from exc
        if Path(manifest['sourceProfile']).resolve() != source:
            raise ValueError('That worker belongs to a different installation; use a new --instance')
        for relative, expected in manifest['artifacts'].items():
            path = (target/relative).resolve()
            if target not in path.parents or sha(path) != expected:
                raise ValueError('That worker\'s bridge or mods changed; use a new --instance')
        return manifest
    spec = launchers.resolve(found, launchers.choose_minecraft(found, minecraft), install_fabric=install_fabric,
                             java=java, cache=cache)
    build = spec['build']
    world = None
    if save:
        world = (source/'saves'/save).resolve(strict=True)
        if world.parent != (source/'saves').resolve() or not (world/'level.dat').is_file():
            raise ValueError('--save must name an existing direct child of source saves')
        with closed_save(world):
            pass
    installed = {}
    for path in (source/'mods').glob('*.jar'):
        info = mod_info(path)
        installed.setdefault(info.get('id'), []).append((path, str(info.get('version', ''))))
    replacements = {}
    for dependency in build['dependencies']:
        present = installed.get(dependency['id'], [])
        # The bridge needs Flashback's exact internals. A Fabric API or Carpet at least as new as the
        # bridge's own stays, because the user's other mods may need that newer build.
        if dependency.get('policy') == 'minimum' and any(
                bridges.version_key(version) >= bridges.version_key(dependency['version']) for _, version in present):
            continue
        replacements[dependency['id']] = bridges.fetch_dependency(dependency, cache/'downloads', [p for p, _ in present])
    folder = Path(build['folder'])
    names = {'guard': f'flashback-background-{VERSION}.jar', 'flashback-agent.jar': f'flashback-agent-{VERSION}.jar',
             'carpet-agent.jar': f'carpet-agent-{VERSION}.jar'}
    for path in (bridges.GUARD, folder/'flashback-agent.jar', folder/'carpet-agent.jar'):
        path.resolve(strict=True)
    target.mkdir(parents=True)
    for name in ('mods', 'config', 'resourcepacks', 'shaderpacks', 'datapacks'):
        if (source/name).is_dir():
            copy_tree(source/name, target/name)
    (target/'mods').mkdir(exist_ok=True)
    # Only our two bridge IDs and the pinned dependencies are replaced, in the new clone.
    for jar in (target/'mods').glob('*.jar'):
        ident = mod_info(jar).get('id')
        if ident in ('flashback_agent', 'carpet_agent') or ident in replacements:
            jar.unlink()
    for ident, path in replacements.items():
        destination = target/'mods'/f'flashback-clips-dependency-{ident}.jar'
        if destination.exists():
            raise FileExistsError(f'Dependency filename is occupied: {destination}')
        shutil.copy2(path, destination)
    state = target/'.background'
    state.mkdir()
    shutil.copy2(bridges.GUARD, state/names['guard'])
    for name in ('flashback-agent.jar', 'carpet-agent.jar'):
        shutil.copy2(folder/name, target/'mods'/names[name])
    options = (source/'options.txt').read_text(encoding='utf-8') if (source/'options.txt').exists() else ''
    overrides = {'fullscreen': 'false', 'pauseOnLostFocus': 'false', 'enableVsync': 'false',
                 'maxFps': '30', 'onboardAccessibility': 'false', 'joinedFirstServer': 'true'}
    options = '\n'.join(line for line in options.splitlines() if line.partition(':')[0] not in overrides)
    (target/'options.txt').write_text(options+'\n'+'\n'.join(f'{k}:{v}' for k,v in overrides.items())+'\n', encoding='utf-8')
    if world:
        (target/'saves').mkdir()
        with closed_save(world):
            copy_tree(world, target/'saves'/world.name, skip_session_lock=True)
    paths = [state/names['guard'], target/'mods'/names['flashback-agent.jar'], target/'mods'/names['carpet-agent.jar']]
    paths += [target/'mods'/f'flashback-clips-dependency-{ident}.jar' for ident in replacements]
    manifest = {'version': VERSION, 'instance': str(target), 'sourceProfile': str(source), 'launcher': found['launcher'],
                'minecraft': spec['minecraft'], 'fabric': spec['fabric'], 'flashback': build['flashback'],
                'java': spec['java'], 'javaMajor': spec['javaMajor'], 'classpath': spec['classpath'],
                'assets': spec['assets'], 'assetIndex': spec['assetIndex'], 'mainClass': spec['mainClass'],
                'guard': str(paths[0]), 'artifacts': {str(p.relative_to(target)): sha(p) for p in paths},
                'copiedSave': save, 'authentication': 'local-offline'}
    atomic_json(state/'instance.json', manifest)
    return manifest


def load(instance):
    root = Path(instance).resolve(strict=True)
    data = json.loads((root/'.background/instance.json').read_text(encoding='utf-8'))
    if data['version'] != VERSION or Path(data['instance']).resolve() != root:
        raise ValueError('Unsupported or moved instance; prepare a new worker')
    return root, data


@contextmanager
def control_lock(root):
    import msvcrt
    with (root/'.background/control.lock').open('a+b') as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Another start/stop operation owns this worker') from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def status(instance):
    root, data = load(instance)
    path = root/'.background/process.json'
    if not path.exists():
        return {'state': 'stopped', 'instance': str(root)}
    state = json.loads(path.read_text(encoding='utf-8'))
    identity = process_identity(state['pid'])
    running = identity is not None and identity == state['created']
    result = {**state, 'state': 'running' if running else 'stopped', 'instance': str(root)}
    if running:
        result['windows'] = window_state(state['pid'])
        result['onInputDesktop'] = input_desktop() == state.get('desktop')
        health = root/'flashback-agent/live/bridge.json'
        if health.exists():
            bridge = read_json(health)
            result['bridgeFresh'] = time.time()*1000 - bridge.get('updatedAt', 0) < 15000
    return result


def java_argfile(arguments):
    # Java @argfiles use their own quoting, not PowerShell or JSON quoting.
    if any(any(c in arg for c in '\x00\r\n') for arg in arguments):
        raise ValueError('Newlines/NUL are not allowed in launch arguments')
    return '\n'.join('"'+arg.replace('\\', '\\\\').replace('"', '\\"')+'"' for arg in arguments)+'\n'


def start(instance, *, timeout=180, memory_mb=4096, fps=30):
    windows()
    root, data = load(instance)
    if not 1024 <= memory_mb <= 16384 or not 20 <= fps <= 120 or not 1 <= timeout <= 600:
        raise ValueError('Use memory 1024..16384 MiB, fps 20..120 and timeout 1..600 seconds')
    with control_lock(root), private_desktop() as desktop:
        if status(root)['state'] == 'running':
            raise RuntimeError('Worker already running; inspect runtime status instead of starting another')
        health = root/'flashback-agent/live/bridge.json'
        if health.exists() and time.time()*1000 - read_json(health)['updatedAt'] < 15000:
            raise RuntimeError('An existing client owns this profile')
        for relative, checksum in data['artifacts'].items():
            path = (root/relative).resolve(strict=True)
            if root not in path.parents or sha(path) != checksum:
                raise RuntimeError('Background guard/bridge changed; prepare a matching instance before launching')
        for path in [data['java'], *data['classpath']]:
            Path(path).resolve(strict=True)
        launch_id = uuid.uuid4().hex
        log = root/'.background'/f'{launch_id}.log'
        native = root/'.background/natives'
        native.mkdir(exist_ok=True)
        # Newer JDKs warn about (and will block) the native and Unsafe access Minecraft uses.
        modern = [*(['--enable-native-access=ALL-UNNAMED'] if data['javaMajor'] >= 22 else []),
                  *(['--sun-misc-unsafe-memory-access=allow'] if data['javaMajor'] >= 23 else [])]
        args = [f'-Xms512M', f'-Xmx{memory_mb}M', '-XX:ActiveProcessorCount=4', *modern,
                f'-javaagent:{data["guard"]}', '-Djava.awt.headless=true',
                f'-Dflashback.agent.launchId={launch_id}', f'-Dflashback.agent.backgroundFps={fps}',
                f'-Djava.library.path={native}/java', f'-Djna.tmpdir={native}/jna',
                f'-Dorg.lwjgl.system.SharedLibraryExtractPath={native}/lwjgl', f'-Dio.netty.native.workdir={native}/netty',
                '-Dminecraft.launcher.brand=flashback-agent', f'-Dminecraft.launcher.version={VERSION}',
                '-Dessential.autoUpdate=false',
                '-cp', os.pathsep.join(data['classpath']), data['mainClass'],
                '--username', 'FlashbackAgent', '--uuid', '8c3d1a98608c3a859accf669c8978832', '--accessToken', '0',
                '--version', data['minecraft'], '--versionType', 'release', '--gameDir', str(root),
                '--assetsDir', data['assets'], '--assetIndex', data['assetIndex'], '--width', '960', '--height', '540']
        argfile = root/'.background'/f'{launch_id}.args'
        argfile.write_text(java_argfile(args), encoding='utf-8')
        env = os.environ.copy()
        for key in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS'):
            env.pop(key, None)  # inherited JVM flags cannot replace the guarded launch
        env['ALSOFT_DRIVERS'] = 'null'  # silent playback backend; offline loopback export still receives audio
        with log.open('wb') as output:
            child = BackgroundProcess([data['java'], '@'+str(argfile)], cwd=root, env=env,
                                      output=output, desktop=desktop)
        created = process_identity(child.pid)
        atomic_json(root/'.background/process.json', {'pid': child.pid, 'created': created, 'launchId': launch_id,
                    'log': str(log), 'startedAt': time.time(), 'backgroundFps': fps, 'memoryMiB': memory_mb,
                    'desktop': desktop})
        deadline = time.monotonic()+timeout
        from .tools import call_tool
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f'Background worker exited ({child.returncode}); inspect {log}')
            observation = window_state(child.pid)
            if observation['visibleWindows'] or observation['foreground']:
                # During startup there is no world/recording to lose. No unguarded fallback is allowed.
                child.terminate()
                child.wait(timeout=10)
                raise RuntimeError(f'Background isolation violation; startup stopped. Inspect {log}')
            try:
                reply = call_tool('record_status', {}, game_dir=root, timeout=1)
            except (OSError, ValueError, RuntimeError, TimeoutError):
                time.sleep(.25)
                continue
            background = reply.get('result', {}).get('background', {})
            if background.get('launchId') != launch_id:
                time.sleep(.25)
                continue
            if background.get('guard') != 'active' or background.get('visible') or background.get('focused') or background.get('fullscreen'):
                child.terminate()
                child.wait(timeout=10)
                raise RuntimeError(f'Background guard not verified; startup stopped. Inspect {log}')
            return {**status(root), 'state': 'ready', 'background': background}
        raise TimeoutError(f'Worker is still starting; no visible fallback. Inspect runtime status/log: {log}')


def stop(instance, *, timeout=60):
    root, _ = load(instance)
    with control_lock(root):
        state = status(root)
        if state['state'] == 'stopped':
            return state
        from .tools import call_tool
        reply = call_tool('runtime_shutdown', {'launchId': state['launchId']}, game_dir=root, timeout=15)
        if reply['state'] != 'completed':
            raise RuntimeError(reply.get('error', 'Worker refused shutdown'))
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            result = status(root)
            if result['state'] == 'stopped':
                return result
            time.sleep(.2)
        raise TimeoutError('Worker is still saving/stopping; inspect status. No forced kill was performed')
