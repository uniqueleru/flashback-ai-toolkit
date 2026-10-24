"""Verify an unguarded child inherits a non-input desktop before testing a window."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from flashback_agent.runtime import BackgroundProcess, private_desktop, desktop_name, input_desktop

if '--child' in sys.argv:
    kernel = ctypes.WinDLL('kernel32')
    user = ctypes.WinDLL('user32')
    user.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user.GetThreadDesktop.restype = wintypes.HANDLE
    own = desktop_name(user.GetThreadDesktop(kernel.GetCurrentThreadId()))
    active = input_desktop()
    assert own.startswith('FlashbackAgent_') and own != active, (own, active)
    # The private-desktop assertion happens BEFORE any window is created.
    user.CreateWindowExW.argtypes = [wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,
        ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,wintypes.LPVOID]
    user.CreateWindowExW.restype = wintypes.HWND
    user.ShowWindow.argtypes = [wintypes.HWND,ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.DestroyWindow.argtypes = [wintypes.HWND]
    window = user.CreateWindowExW(0, 'STATIC', 'Private desktop validation', 0x10CF0000, 0, 0, 200, 100, None, None, None, None)
    assert window
    user.ShowWindow(window, 5)
    user.SetForegroundWindow(window)
    time.sleep(.4)
    assert input_desktop() == active
    user.DestroyWindow(window)
    print(json.dumps({'childPid':os.getpid(), 'desktop':own, 'inputDesktop':active, 'privateWindowTest':True}), flush=True)
elif '--parent' in sys.argv:
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child'], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    print(json.dumps({'parentPid': os.getpid(), 'child': json.loads(result.stdout)}), flush=True)
else:
    from window_audit import WindowAudit
    work = root/'work/background-desktop-proof'
    work.mkdir(exist_ok=True)
    with WindowAudit() as audit, private_desktop() as desktop, (work/'probe.log').open('wb') as output:
        process = BackgroundProcess([sys.executable, str(Path(__file__).resolve()), '--parent'], cwd=root,
                                    env=os.environ.copy(), output=output, desktop=desktop)
        code = process.wait(timeout=20)
        report = json.loads((work/'probe.log').read_text(encoding='utf-8')) if code == 0 else {'error': (work/'probe.log').read_text(errors='replace')}
        report['exitCode'] = code
        report['windowEventsOnUserDesktop'] = audit.for_pid(process.pid) + audit.for_pid(report.get('child',{}).get('childPid'))
        (work/'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
        assert code == 0 and not report['windowEventsOnUserDesktop'], report
