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
from teachdesk.windows import EmergencyHotkey, WindowsDesktop, enable_dpi_awareness

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
        time.sleep(.6)
        desktop.send(key=16, down=True)
        desktop.send(key=16, down=False)
        time.sleep(.3)
    finally:
        recorder.stop()
        assert recorder.finished.wait(3)
    evidence = store.evidence(task)[0]
    assert len(evidence["frames"]) >= 2
    assert not [e for e in evidence["events"] if e["kind"] == "key"], "Injected events were echoed or physical input occurred"


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
