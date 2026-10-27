"""Contract tests for the HWND-bound provider; no native Windows claim."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from teachdesk.window_capture import capture_window
from teachdesk.windows import UnsupportedDesktop, WindowNotReady


def provider(monkeypatch, mode="frame", size=(8, 6), stop_error=False):
    calls = []
    pixels = np.zeros((size[1], size[0]+4, 4), dtype=np.uint8)
    pixels[:] = [19, 37, 211, 255]  # BGRA, padded rows
    class Capture:
        def __init__(self, **kwargs):
            calls.append(("create", kwargs))
            self.handlers = {}
        def event(self, fn):
            self.handlers[fn.__name__] = fn
            return fn
        def start_free_threaded(self):
            calls.append(("start",))
            if mode == "failure":
                raise RuntimeError("native initialization failed")
            if mode == "closed":
                self.handlers["on_closed"]()
            elif mode != "timeout":
                frame = SimpleNamespace(width=size[0], height=size[1], frame_buffer=pixels[:, :size[0], :])
                self.handlers["on_frame_arrived"](frame, SimpleNamespace(stop=lambda: calls.append(("stop_callback",))))
                pixels[:] = 0  # callback storage is no longer usable
            def stop():
                calls.append(("stop_session",))
                if stop_error:
                    raise RuntimeError("native stop failed")
            return SimpleNamespace(stop=stop)
    monkeypatch.setitem(sys.modules, "windows_capture", SimpleNamespace(WindowsCapture=Capture))
    return calls


def test_source_is_exact_hwnd_and_pixel_copy_outlives_native_frame(monkeypatch):
    calls = provider(monkeypatch)
    image = capture_window(123456, (8, 6))
    assert calls == [("create", {"window_hwnd": 123456, "cursor_capture": False}), ("start",), ("stop_callback",), ("stop_session",)]
    assert image.mode == "RGB" and image.size == (8, 6)
    assert image.getpixel((7, 5)) == (211, 37, 19)


@pytest.mark.parametrize("mode,message", [("timeout", "timed out"), ("closed", "closed before")])
def test_no_frame_still_closes_source(monkeypatch, mode, message):
    calls = provider(monkeypatch, mode)
    with pytest.raises(WindowNotReady, match=message):
        capture_window(123, (8, 6), timeout=.001)
    assert calls[-1] == ("stop_session",)


def test_different_surface_dimensions_are_rejected_and_session_closed(monkeypatch):
    calls = provider(monkeypatch, size=(7, 6))
    with pytest.raises(WindowNotReady, match="differs from physical bounds"):
        capture_window(123, (8, 6))
    assert calls[-2:] == [("stop_callback",), ("stop_session",)]


def test_failed_native_initialization_never_falls_back_to_a_monitor(monkeypatch):
    calls = provider(monkeypatch, "failure")
    with pytest.raises(UnsupportedDesktop, match="unsupported"):
        capture_window(123, (8, 6))
    assert len([c for c in calls if c[0] == "create"]) == 1
    assert calls[0][1]["window_hwnd"] == 123


def test_missing_provider_blocks_capture(monkeypatch):
    monkeypatch.setitem(sys.modules, "windows_capture", None)
    with pytest.raises(UnsupportedDesktop, match="updated TeachDesk launcher"):
        capture_window(123, (8, 6))


def test_no_window_handle_never_uses_library_monitor_default(monkeypatch):
    calls = provider(monkeypatch)
    with pytest.raises(UnsupportedDesktop, match="exact window handle"):
        capture_window(0, (8, 6))
    assert not calls


def test_session_shutdown_error_blocks_return_of_frame(monkeypatch):
    provider(monkeypatch, stop_error=True)
    with pytest.raises(UnsupportedDesktop, match="shut down cleanly"):
        capture_window(123, (8, 6))
