"""Opt-in tests send VISIBLE input in a disposable Practice Lab process.

Close TeachDesk first. Run with TEACHDESK_WINDOWS_TESTS=1 on an unlocked,
single-monitor Windows desktop. Keep hands off during these checks.
These do not call a model and do not validate learned task competence.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

import pytest

from teachdesk.execution import Cancelled, Control, VisibleInput
from teachdesk.recording import Recorder
from teachdesk.storage import Store
from teachdesk.windows import EmergencyHotkey, WindowsDesktop, WindowNotReady, enable_dpi_awareness

pytestmark = pytest.mark.skipif(os.name != "nt" or os.environ.get("TEACHDESK_WINDOWS_TESTS") != "1", reason="Requires explicit opt-in and interactive Windows desktop")


@pytest.fixture
def native():
    enable_dpi_awareness()
    desktop = WindowsDesktop()
    desktop.display()  # fail early if multiple monitors
    child = subprocess.Popen([sys.executable, "-m", "teachdesk.lab", "--diagnostic-edit"])
    scope = None
    try:
        until = time.monotonic()+15
        while time.monotonic() < until:
            scope = next((w for w in desktop.windows() if w.pid == child.pid and w.title == "TeachDesk Practice Lab"), None)
            if scope:
                break
            time.sleep(.1)
        assert scope, "Practice Lab did not open"
        import ctypes as C
        from ctypes import wintypes as W
        desktop.u.SetForegroundWindow.argtypes = [W.HWND]
        desktop.u.ShowWindow.argtypes = [W.HWND, C.c_int]
        desktop.u.ShowWindow(scope.hwnd, 9)
        desktop.u.SetForegroundWindow(scope.hwnd)
        until = time.monotonic()+5
        while desktop.foreground() != scope.hwnd and time.monotonic() < until:
            time.sleep(.1)
        desktop.check(scope)
        yield desktop, scope
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_native_capture_and_own_injected_events_filtered(native, tmp_path):
    desktop, scope = native
    store = Store(tmp_path)
    task = store.create_task("Native capture diagnostic", "Platform test, not learned workflow")
    recorder = Recorder(store, desktop, scope, task)
    recorder.start()
    try:
        until = time.monotonic()+8
        while not recorder.finished.is_set() and time.monotonic() < until:
            if store.rows("SELECT count(*) AS n FROM frames WHERE demo=?", (recorder.demo,))[0]["n"] >= 2:
                break
            time.sleep(.05)
        desktop.send(key=16, down=True)
        desktop.send(key=16, down=False)
        time.sleep(.3)
    finally:
        recorder.stop()
        assert recorder.finished.wait(3)
    evidence = store.evidence(task)[0]
    assert len(evidence["frames"]) >= 2
    assert not [e for e in evidence["events"] if e["kind"] == "key"], "Injected events were echoed or physical input occurred"
    # Frame count alone allowed desktop/background captures to pass. This
    # controlled fixture has a large known background and a dark status band.
    import numpy as np
    from PIL import Image
    with Image.open(store.root/evidence["frames"][0]["path"]) as image:
        pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    light = np.max(np.abs(pixels-np.array([236, 240, 246])), axis=2) <= 2
    band = np.max(np.abs(pixels-np.array([22, 40, 63])), axis=2) <= 2
    assert light.mean() > .55 and band.mean() > .01, "Saved frame is not the expected Lab surface; inspect capture coordinates"


def test_native_hwnd_capture_keeps_lab_surface_when_another_window_covers_it(native):
    """Exercise the actual source independently of potentially delayed scope APIs.

    Product capture still requires foreground ownership. Here only the provider
    is called, with a known covering window, to prove it cannot crop that window.
    """
    from teachdesk.window_capture import capture_window
    import numpy as np
    desktop, scope = native
    rect = desktop.geometry(scope.hwnd)
    script = """
import sys
from PySide6.QtWidgets import QApplication, QWidget
app = QApplication([])
w = QWidget()
w.setWindowTitle('TeachDesk capture-source diagnostic cover')
w.setStyleSheet('background: #ff00ff;')
w.setGeometry(*map(int, sys.argv[1:]))
w.show()
w.raise_()
w.activateWindow()
app.exec()
"""
    child = subprocess.Popen([sys.executable, "-c", script, str(rect["left"]-10), str(rect["top"]-10), str(rect["width"]+20), str(rect["height"]+20)])
    try:
        until = time.monotonic()+8
        cover = None
        while time.monotonic() < until:
            cover = next((w for w in desktop.windows() if w.pid == child.pid), None)
            if cover:
                desktop.u.SetForegroundWindow(cover.hwnd)
                if desktop.foreground() == cover.hwnd:
                    break
            time.sleep(.05)
        assert cover and desktop.foreground() == cover.hwnd, "Cover window did not gain focus"
        from ctypes import wintypes as W
        center = W.POINT(rect["left"]+rect["width"]//2, rect["top"]+rect["height"]//2)
        hit = desktop.u.WindowFromPhysicalPoint(center)
        assert int(desktop.u.GetAncestor(hit, 2) or 0) == cover.hwnd
        image = capture_window(scope.hwnd, (rect["width"], rect["height"]))
        pixels = np.asarray(image, dtype=np.int16)
        light = np.max(np.abs(pixels-np.array([236, 240, 246])), axis=2) <= 2
        band = np.max(np.abs(pixels-np.array([22, 40, 63])), axis=2) <= 2
        magenta = np.max(np.abs(pixels-np.array([255, 0, 255])), axis=2) <= 2
        assert light.mean() > .55 and band.mean() > .01 and magenta.mean() < .01
    finally:
        child.terminate()
        child.wait(timeout=5)
        desktop.u.SetForegroundWindow(scope.hwnd)


def test_native_minimized_window_is_not_captured(native):
    desktop, scope = native
    try:
        desktop.u.ShowWindow(scope.hwnd, 6)
        until = time.monotonic()+2
        while not desktop.u.IsIconic(scope.hwnd) and time.monotonic() < until:
            time.sleep(.02)
        with pytest.raises(WindowNotReady):
            desktop.capture(scope)
    finally:
        desktop.u.ShowWindow(scope.hwnd, 9)


@pytest.mark.parametrize("action", ["movement", "typing", "held_key", "held_button"])
def test_native_os_emergency_hotkey_interrupts_input(native, action):
    desktop, scope = native
    control = Control()
    io = VisibleInput(desktop, scope, desktop.display(), control, {"speed": 80, "hold": .1, "gap": .1})
    hotkey = EmergencyHotkey(control.stop)
    assert not hotkey.error, hotkey.error
    errors = []
    started = threading.Event()
    def work():
        try:
            if action in {"movement", "typing"}:
                started.set()
            if action == "movement":
                r = desktop.geometry(scope.hwnd)
                io.move(r["left"]+r["width"]-50, r["top"]+r["height"]-50)
                io.wait(3)
            elif action == "typing": io.type_text("diagnostic "*100)
            elif action == "held_key":
                io.send(key=65, down=True)
                started.set()
                io.wait(4)
                io.send(key=65, down=False)
            else:
                r = desktop.geometry(scope.hwnd)
                io.move(r["left"]+40, r["top"]+350)
                io.send(button="left", down=True)
                started.set()
                io.wait(4)
        except Cancelled:
            errors.append("cancelled")
        finally:
            io.release()
    worker = threading.Thread(target=work, daemon=True)
    try:
        worker.start()
        assert started.wait(8)
        time.sleep(.25)
        # Exercise the actual registered hotkey using native input, not the callback directly.
        for key in (17, 18, 0x77): desktop.send(key=key, down=True)
        for key in (0x77, 18, 17): desktop.send(key=key, down=False)
        assert control.cancelled.wait(2), "OS hotkey was not delivered"
        worker.join(2)
        assert not worker.is_alive() and errors
        assert not io.held
        assert not desktop.u.GetAsyncKeyState(65) & 0x8000
    finally:
        control.stop()
        for key in (0x77, 18, 17, 65): desktop.send(key=key, down=False)
        worker.join(2)
        hotkey.close()
