"""Windows-only capture and visible SendInput. No target application APIs."""
from __future__ import annotations

import ctypes as C
import os
import threading
import time
from dataclasses import asdict, dataclass
from ctypes import wintypes as W


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    executable: str
    title: str


def enable_dpi_awareness():
    if os.name == "nt":
        u = C.WinDLL("user32", use_last_error=True)
        u.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
        u.SetProcessDpiAwarenessContext(C.c_void_p(-4))  # PER_MONITOR_AWARE_V2, before Qt


class UnsupportedDesktop(RuntimeError):
    pass


def mask_image(image, masks):
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    for x0, y0, x1, y1 in masks:
        draw.rectangle((int(x0*image.width), int(y0*image.height), int(x1*image.width), int(y1*image.height)), fill="black")
    return image


class WindowsDesktop:
    def __init__(self):
        if os.name != "nt":
            raise UnsupportedDesktop("Capture and control require an unlocked Windows 10/11 desktop")
        self.u = C.WinDLL("user32", use_last_error=True)
        self.k = C.WinDLL("kernel32", use_last_error=True)
        self.u.GetForegroundWindow.restype = W.HWND
        for name in ("IsWindow", "IsWindowVisible", "IsIconic"):
            getattr(self.u, name).argtypes = [W.HWND]
        self.u.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
        self.u.GetWindowTextLengthW.argtypes = [W.HWND]
        self.u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        self.k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.k.OpenProcess.restype = W.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.u.OpenInputDesktop.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.u.OpenInputDesktop.restype = W.HANDLE
        self.u.GetUserObjectInformationW.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
        self.u.CloseDesktop.argtypes = [W.HANDLE]
        ulong_ptr = C.c_size_t

        class MOUSEINPUT(C.Structure):
            _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD), ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ulong_ptr)]

        class KEYBDINPUT(C.Structure):
            _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ulong_ptr)]

        class HARDWAREINPUT(C.Structure):
            _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]

        class UNION(C.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(C.Structure):
            _anonymous_ = ("data",)
            _fields_ = [("type", W.DWORD), ("data", UNION)]

        self.INPUT, self.MI, self.KI = INPUT, MOUSEINPUT, KEYBDINPUT
        self.u.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
        self.u.SendInput.restype = W.UINT

    def foreground(self):
        return int(self.u.GetForegroundWindow() or 0)

    def window(self, hwnd):
        pid = W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        title = C.create_unicode_buffer(self.u.GetWindowTextLengthW(hwnd) + 1)
        self.u.GetWindowTextW(hwnd, title, len(title))
        h = self.k.OpenProcess(0x1000, False, pid.value)
        exe = C.create_unicode_buffer(32768)
        length = W.DWORD(len(exe))
        try:
            if not h or not self.k.QueryFullProcessImageNameW(h, 0, exe, C.byref(length)):
                raise UnsupportedDesktop("Cannot inspect target process")
            return Window(int(hwnd), pid.value, exe.value, title.value)
        finally:
            if h:
                self.k.CloseHandle(h)

    def windows(self):
        result = []
        callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

        @callback
        def visit(hwnd, _):
            if self.u.IsWindowVisible(hwnd) and self.u.GetWindowTextLengthW(hwnd):
                try:
                    win = self.window(hwnd)
                    if win.pid != os.getpid():
                        result.append(win)
                except UnsupportedDesktop:
                    pass
            return True

        self.u.EnumWindows.argtypes = [callback, W.LPARAM]
        if not self.u.EnumWindows(visit, 0):
            raise UnsupportedDesktop("Cannot enumerate desktop windows")
        return result

    def geometry(self, hwnd):
        rect = W.RECT()
        if not self.u.GetWindowRect(hwnd, C.byref(rect)):
            raise UnsupportedDesktop("Target window no longer exists")
        return {"left": rect.left, "top": rect.top, "width": rect.right-rect.left, "height": rect.bottom-rect.top}

    def display(self):
        import mss
        with mss.mss() as sct:
            if len(sct.monitors) != 2:
                raise UnsupportedDesktop("Prototype supports exactly one enabled monitor")
            return {**dict(sct.monitors[1]), "dpi": int(self.u.GetDpiForSystem())}

    def check(self, scope: Window, display=None):
        if not self.u.IsWindow(scope.hwnd) or self.u.IsIconic(scope.hwnd) or not self.u.IsWindowVisible(scope.hwnd):
            raise UnsupportedDesktop("Target closed, hidden or minimized")
        current = self.window(scope.hwnd)
        if current.pid != scope.pid or current.executable != scope.executable or current.title != scope.title:
            raise UnsupportedDesktop("Target identity changed")
        if self.foreground() != scope.hwnd:
            raise UnsupportedDesktop("Target lost foreground focus; refocus it before resuming")
        desktop = self.u.OpenInputDesktop(0, False, 1)
        if not desktop:
            raise UnsupportedDesktop("Input desktop is locked or unavailable")
        try:
            name = C.create_unicode_buffer(256)
            needed = W.DWORD()
            if not self.u.GetUserObjectInformationW(desktop, 2, name, C.sizeof(name), C.byref(needed)) or name.value.lower() != "default":
                raise UnsupportedDesktop("Secure or alternate desktop is unsupported")
        finally:
            self.u.CloseDesktop(desktop)
        monitor, rect = self.display(), self.geometry(scope.hwnd)
        if display and monitor != display:
            raise UnsupportedDesktop("Display configuration changed")
        if not (monitor["left"] <= rect["left"] and monitor["top"] <= rect["top"] and rect["left"]+rect["width"] <= monitor["left"]+monitor["width"] and rect["top"]+rect["height"] <= monitor["top"]+monitor["height"]):
            raise UnsupportedDesktop("Target must fit entirely on the single monitor")
        return rect

    def capture(self, scope, display=None, masks=()):
        from PIL import Image
        import mss
        rect = self.check(scope, display)
        with mss.mss() as sct:
            shot = sct.grab(rect)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        # normalized rectangles move with window, remain independent of DPI.
        image = mask_image(image, masks)
        if self.foreground() != scope.hwnd:
            raise UnsupportedDesktop("Foreground changed during capture; discarded frame")
        return image, rect

    def position(self):
        p = W.POINT()
        self.u.GetCursorPos(C.byref(p))
        return p.x, p.y

    def check_idle(self):
        if any(self.u.GetAsyncKeyState(key) & 0x8000 for key in range(1, 255)):
            raise UnsupportedDesktop("Release held keyboard keys and mouse buttons before starting")

    def send(self, *, move=None, button=None, down=None, key=None, unicode=None, scroll=None):
        item = self.INPUT()
        if move is not None or button is not None or scroll is not None:
            item.type = 0
            mi = self.MI()
            if move is not None:
                d = self.display()
                x, y = move
                mi.dx = round((x-d["left"]) * 65535 / max(1, d["width"]-1))
                mi.dy = round((y-d["top"]) * 65535 / max(1, d["height"]-1))
                mi.dwFlags = 0x8000 | 0x0001
            if button is not None:
                mi.dwFlags = {("left", True): 2, ("left", False): 4, ("right", True): 8, ("right", False): 16, ("middle", True): 32, ("middle", False): 64}[(button, down)]
            if scroll is not None:
                mi.dwFlags, mi.mouseData = 0x0800, int(scroll*120) & 0xFFFFFFFF
            item.mi = mi
        else:
            item.type = 1
            item.ki = self.KI(key or 0, unicode or 0, (4 if unicode is not None else 0) | (0 if down else 2), 0, 0)
        if self.u.SendInput(1, C.byref(item), C.sizeof(item)) != 1:
            raise UnsupportedDesktop("SendInput failed (possibly an elevated window or rejected simulated input)")


class EmergencyHotkey:
    """Dedicated OS hotkey thread; never waits on Qt or model requests."""
    def __init__(self, stop):
        self.stop = stop
        self.ready = threading.Event()
        self.closed = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        if not self.ready.wait(3):
            self.error = "Emergency hotkey registration timed out"

    def _run(self):
        if os.name != "nt":
            self.error = "Windows emergency hotkey unavailable on this platform"
            self.ready.set()
            return
        u = C.WinDLL("user32", use_last_error=True)
        if not u.RegisterHotKey(None, 0x741, 0x4000 | 0x2 | 0x1, 0x77):  # Ctrl+Alt+F8
            self.error = "Ctrl+Alt+F8 is already registered; close the conflicting app"
            self.ready.set()
            return
        self.ready.set()
        try:
            msg = W.MSG()
            while not self.closed.wait(.01):
                while u.PeekMessageW(C.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312:
                        self.stop()
        finally:
            u.UnregisterHotKey(None, 0x741)

    def close(self):
        self.closed.set()
        self.thread.join(2)


class InputHooks:
    """pynput hooks observe physical inputs only; do not suppress user's input."""
    def __init__(self, callback):
        from pynput import keyboard, mouse

        def mouse_filter(msg, data):
            return not (data.flags & 1)  # LLMHF_INJECTED

        def key_filter(msg, data):
            return not (data.flags & 0x10)  # LLKHF_INJECTED

        self.listeners = [
            mouse.Listener(on_move=lambda x, y: callback("move", {"x": x, "y": y}),
                           on_click=lambda x, y, b, down: callback("button", {"x": x, "y": y, "button": b.name, "down": down}),
                           on_scroll=lambda x, y, dx, dy: callback("scroll", {"x": x, "y": y, "dx": dx, "dy": dy}),
                           win32_event_filter=mouse_filter),
            keyboard.Listener(on_press=lambda k: callback("key", {"key": getattr(k, "char", None) or getattr(k, "name", str(k)), "down": True}),
                              on_release=lambda k: callback("key", {"key": getattr(k, "char", None) or getattr(k, "name", str(k)), "down": False}),
                              win32_event_filter=key_filter)]
        self.started = []

    def start(self):
        for listener in self.listeners:
            listener.start()
            self.started.append(listener)
            listener.wait()

    @property
    def healthy(self):
        return len(self.started) == len(self.listeners) and all(listener.is_alive() for listener in self.started)

    def close(self):
        for listener in self.started:
            listener.stop()
        # Never join from a hook callback.
        for listener in self.started:
            if listener is not threading.current_thread():
                listener.join(2)
