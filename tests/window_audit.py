"""Windows event audit for integration tests; never changes desktop/input state."""
import ctypes
from ctypes import wintypes
import threading
import time


class WindowAudit:
    def __init__(self):
        self.events = []
        self.ready = threading.Event()
        self.done = threading.Event()
        self.failure = None

    def __enter__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        if not self.ready.wait(5) or self.failure:
            raise RuntimeError(f'Window audit failed: {self.failure}')
        return self

    def _run(self):
        user = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                          wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        user.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, callback_type,
                                        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        user.SetWinEventHook.restype = wintypes.HANDLE
        user.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.IsWindowVisible.argtypes = [wintypes.HWND]
        @callback_type
        def callback(hook, event, hwnd, object_id, child_id, thread, stamp):
            if hwnd and (event == 3 or (event == 0x8002 and object_id == 0)):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                self.events.append({'pid': pid.value, 'event': 'foreground' if event == 3 else 'show',
                                    'visible': bool(user.IsWindowVisible(hwnd)), 'time': time.time()})
        hooks = [user.SetWinEventHook(event, event, None, callback, 0, 0, 0) for event in (3, 0x8002)]
        if not all(hooks):
            self.failure = ctypes.get_last_error()
            self.ready.set()
            return
        self.ready.set()
        msg = wintypes.MSG()
        while not self.done.is_set():
            while user.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user.TranslateMessage(ctypes.byref(msg))
                user.DispatchMessageW(ctypes.byref(msg))
            self.done.wait(.01)
        for hook in hooks:
            user.UnhookWinEvent(hook)

    def for_pid(self, pid):
        return [event for event in self.events if event['pid'] == pid]

    def __exit__(self, *args):
        self.done.set()
        self.thread.join(timeout=5)
