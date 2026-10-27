"""Regression checks for invalid desktop frames around window transitions.

These use fake Win32/capture boundaries on Linux; native behavior still needs
the opt-in Windows suite and inspection of a newly recorded Lab frame.
"""
from __future__ import annotations

import ctypes
import json
import sys
import threading
import types

import pytest
from PIL import Image

from teachdesk import model
from teachdesk.execution import Control, Paused, Runner
from teachdesk.recording import Recorder
from teachdesk.storage import Store
from teachdesk.windows import WindowNotReady, WindowsDesktop, UnsupportedDesktop, physical_pixels
from teachdesk.workflow import readiness
from conftest import FakeDesktop, SCOPE


PHYSICAL = ctypes.c_void_p(-4).value
RECT = {"left": 300, "top": 150, "width": 300, "height": 200}


class DpiAPI:
    def __init__(self):
        self.context = 17
        self.history = []

    def SetThreadDpiAwarenessContext(self, context):
        value = context.value if isinstance(context, ctypes.c_void_p) else context
        previous, self.context = self.context, value
        self.history.append(value)
        return previous


def desktop_capture(monkeypatch, after):
    desktop = object.__new__(WindowsDesktop)
    desktop.u = DpiAPI()
    desktop.foreground = lambda: SCOPE.hwnd  # Still reported even while minimizing.
    checks = []

    def check(scope, display=None):
        checks.append(1)
        if len(checks) == 1:
            return RECT.copy()
        if isinstance(after, Exception):
            raise after
        return after.copy()

    desktop.check = check

    class Capture:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, rect):
            assert desktop.u.context == PHYSICAL
            assert rect == RECT
            image = Image.new("RGB", (rect["width"], rect["height"]), "white")
            return types.SimpleNamespace(size=image.size, rgb=image.tobytes())

    monkeypatch.setitem(sys.modules, "mss", types.SimpleNamespace(mss=Capture))
    return desktop, checks


@pytest.mark.parametrize("after", [
    WindowNotReady("Target hidden or minimized"),
    WindowNotReady("Target lost foreground focus"),
    WindowNotReady("Target center is covered"),
    {**RECT, "left": RECT["left"]+20},
    {**RECT, "width": RECT["width"]+20},
])
def test_inflight_frame_is_discarded_even_if_foreground_handle_stays_same(monkeypatch, after):
    desktop, checks = desktop_capture(monkeypatch, after)
    with pytest.raises(WindowNotReady):
        desktop.capture(SCOPE)
    assert len(checks) == 2
    assert desktop.u.context == 17


def test_stable_capture_has_same_scope_before_and_after(monkeypatch):
    desktop, checks = desktop_capture(monkeypatch, RECT)
    image, rect = desktop.capture(SCOPE, masks=[[0, 0, .5, .5]])
    assert len(checks) == 2 and rect == RECT
    assert image.size == (300, 200) and image.getpixel((10, 10)) == (0, 0, 0)
    assert desktop.u.context == 17


def test_dpi_context_restores_after_exception():
    subject = types.SimpleNamespace(u=DpiAPI())
    @physical_pixels
    def failing(self):
        assert self.u.context == PHYSICAL
        raise ValueError("capture failed")
    with pytest.raises(ValueError, match="capture failed"):
        failing(subject)
    assert subject.u.context == 17


def test_unavailable_physical_context_blocks_capture():
    subject = types.SimpleNamespace(u=types.SimpleNamespace(SetThreadDpiAwarenessContext=lambda context: None))
    @physical_pixels
    def must_not_run(self):
        pytest.fail("Never capture in an unknown coordinate context")
    with pytest.raises(UnsupportedDesktop, match="physical-pixel"):
        must_not_run(subject)


def test_window_geometry_is_queried_in_physical_pixels():
    desktop = object.__new__(WindowsDesktop)
    desktop.u = DpiAPI()
    def window_rect(hwnd, pointer):
        rect = pointer._obj
        if desktop.u.context == PHYSICAL:
            rect.left, rect.top, rect.right, rect.bottom = 300, 150, 600, 350
        else:
            rect.left, rect.top, rect.right, rect.bottom = 200, 100, 400, 233
        return True
    desktop.u.GetWindowRect = window_rect
    assert desktop.geometry(SCOPE.hwnd) == RECT
    assert desktop.u.context == 17


@pytest.mark.parametrize("owner", [0, 99])
def test_foreground_alone_does_not_allow_covered_window_capture(owner):
    desktop = object.__new__(WindowsDesktop)
    def desktop_name(handle, index, name, size, needed):
        name.value = "Default"
        return True
    desktop.u = types.SimpleNamespace(
        IsWindow=lambda hwnd: True, IsIconic=lambda hwnd: False,
        IsWindowVisible=lambda hwnd: True, OpenInputDesktop=lambda *a: 1,
        GetUserObjectInformationW=desktop_name, CloseDesktop=lambda handle: None,
        WindowFromPhysicalPoint=lambda point: owner, GetAncestor=lambda hwnd, kind: hwnd)
    desktop.window = lambda hwnd: SCOPE
    desktop.foreground = lambda: SCOPE.hwnd
    desktop.geometry = lambda hwnd: RECT
    desktop.display = lambda: {"left": 0, "top": 0, "width": 1000, "height": 800}
    with pytest.raises(WindowNotReady, match="covered"):
        desktop.check(SCOPE)


def test_recording_retains_last_valid_frame_when_target_minimizes(tmp_path, monkeypatch):
    class Hooks:
        def __init__(self, callback): pass
        def start(self): pass
        def close(self): pass
    monkeypatch.setattr("teachdesk.recording.InputHooks", Hooks)
    rejected = threading.Event()
    class MinimizingDesktop(FakeDesktop):
        def __init__(self):
            super().__init__()
            self.calls = 0
        def capture(self, *args):
            self.calls += 1
            if self.calls > 1:
                rejected.set()
                raise WindowNotReady("Target hidden or minimized")
            return super().capture(*args)
    store = Store(tmp_path)
    task = store.create_task("Capture race", "Minimize regression")
    recorder = Recorder(store, MinimizingDesktop(), SCOPE, task)
    recorder.start()
    try:
        assert rejected.wait(3)
    finally:
        recorder.stop()
        assert recorder.finished.wait(3)
    assert recorder.error is None
    evidence = store.evidence(task)[0]
    assert len(evidence["frames"]) == 1
    assert any(e["kind"] == "capture_paused" for e in evidence["events"])
    assert evidence["metadata"]["capture_validation"] == 2


def test_execution_pauses_if_window_disappears_during_observation(project):
    store, _, _, held, vid, _ = project
    desktop = FakeDesktop()
    def unavailable(*args): raise WindowNotReady("Target minimized during capture")
    desktop.capture = unavailable
    runner = Runner(store, desktop, SCOPE, store.version(vid), Control(), practice_demo=held)
    with pytest.raises(Paused, match="minimized"):
        runner.observe()
    assert runner.control.paused.is_set()
    assert runner.last_image is None and not desktop.sent


def test_capture_resumes_after_target_becomes_visible_again(tmp_path, monkeypatch):
    class Hooks:
        def __init__(self, callback): pass
        def start(self): pass
        def close(self): pass
    monkeypatch.setattr("teachdesk.recording.InputHooks", Hooks)
    unavailable = threading.Event()
    visible_again = threading.Event()
    resumed_frame_saved = threading.Event()
    class ChangingDesktop(FakeDesktop):
        def capture(self, *args):
            if not visible_again.is_set():
                unavailable.set()
                raise WindowNotReady("Target minimized")
            return super().capture(*args)
    store = Store(tmp_path)
    task = store.create_task("Resume", "Scope transition fixture")
    original_frame = store.frame
    def saved(*args):
        result = original_frame(*args)
        resumed_frame_saved.set()
        return result
    monkeypatch.setattr(store, "frame", saved)
    recorder = Recorder(store, ChangingDesktop(), SCOPE, task)
    recorder.start()
    try:
        assert unavailable.wait(3)
        visible_again.set()
        assert resumed_frame_saved.wait(3)
    finally:
        recorder.stop()
        assert recorder.finished.wait(3)
    evidence = store.evidence(task)[0]
    assert recorder.error is None and recorder.capture_reason is None
    assert len(evidence["frames"]) == 1
    assert any(e["kind"] == "capture_resumed" for e in evidence["events"])


def test_hidden_target_input_is_ignored_even_before_foreground_handle_changes(tmp_path):
    desktop = FakeDesktop()
    desktop.can_observe_input = lambda scope: False
    store = Store(tmp_path)
    task = store.create_task("Hidden input", "Native foreground lag fixture")
    recorder = Recorder(store, desktop, SCOPE, task, capture_text=True)
    recorder._input("key", {"key": "unintended", "down": True})
    assert recorder.queue.empty()


def test_old_capture_cannot_be_sent_to_model_or_qualify_for_readiness(project, monkeypatch):
    store, task, train, held, vid, _ = project
    meta = json.loads(store.rows("SELECT metadata FROM demos WHERE id=?", (train,))[0]["metadata"])
    meta.pop("capture_validation")
    store.execute("UPDATE demos SET metadata=? WHERE id=?", (json.dumps(meta), train))
    monkeypatch.setenv("TEACHDESK_MODEL_KEY", "test-key-not-a-real-credential")
    model.save_settings(store, {"base_url": "https://model.example/v1", "model": "vision", "consent": True, "local_no_key": False})
    monkeypatch.setattr(model.httpx, "Client", lambda **kwargs: pytest.fail("Must not transmit legacy evidence"))
    with pytest.raises(ValueError, match="predates capture validation"):
        model.generate(store, task)
    assert not readiness(store, store.version(vid))[0]["passed"]
    runner = Runner(store, FakeDesktop(), SCOPE, store.version(vid), Control(), practice_demo=held)
    with pytest.raises(ValueError, match="predates capture validation"):
        runner.preflight()
