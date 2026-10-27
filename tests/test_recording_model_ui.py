from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from teachdesk import model
from teachdesk.recording import Recorder, learn_style
from teachdesk.storage import Store

from conftest import FakeDesktop, SCOPE


class TestHooks:
    __test__ = False
    def __init__(self, callback): self.callback = callback
    def start(self): pass
    def close(self): pass


def test_recording_sync_redaction_pause_and_durations(tmp_path, monkeypatch):
    monkeypatch.setattr("teachdesk.recording.InputHooks", TestHooks)
    store = Store(tmp_path)
    task = store.create_task("Capture", "Capture fixture")
    recorder = Recorder(store, FakeDesktop(), SCOPE, task)
    recorder.start()
    recorder._input("key", {"key": "s", "down": True})
    time.sleep(.03)
    recorder._input("key", {"key": "s", "down": False})
    recorder._input("button", {"x": 200, "y": 200, "button": "left", "down": True})
    recorder._input("button", {"x": 200, "y": 200, "button": "left", "down": False})
    recorder.pause()
    recorder._input("key", {"key": "PRIVATE", "down": True})
    time.sleep(.03)
    recorder.stop()
    assert recorder.finished.wait(2)
    demo = store.evidence(task)[0]
    assert demo["frames"] and demo["events"]
    assert all(e["t"] >= 0 for e in demo["events"])
    assert "PRIVATE" not in json.dumps(demo)
    keys = [e for e in demo["events"] if e["kind"] == "key"]
    assert all(e["data"]["key"] == "<redacted>" for e in keys)
    assert keys[1]["data"]["held_seconds"] >= .02
    assert demo["frames"][0]["geometry"]
    assert learn_style([demo])["timing_samples"] >= 0


def test_exclusion_masks_force_key_redaction_and_emergency_not_complete(tmp_path, monkeypatch):
    monkeypatch.setattr("teachdesk.recording.InputHooks", TestHooks)
    store = Store(tmp_path)
    task = store.create_task("Private", "Capture masks")
    recorder = Recorder(store, FakeDesktop(), SCOPE, task, capture_text=True, masks=[[0, 0, .5, .5]])
    assert not recorder.capture_text
    recorder.start()
    recorder._input("key", {"key": "password", "down": True})
    recorder.stop(emergency=True)
    assert recorder.finished.wait(2)
    assert not store.evidence(task)
    assert store.rows("SELECT status FROM demos")[0]["status"] == "interrupted"


def test_masks_are_black_before_storage_or_model_encoding():
    from PIL import Image
    from teachdesk.windows import mask_image
    image = mask_image(Image.new("RGB", (100, 100), "white"), [[.2, .3, .7, .8]])
    assert image.getpixel((25, 35)) == (0, 0, 0)
    assert image.getpixel((0, 0)) == (255, 255, 255)


def test_recording_finalization_error_does_not_leave_session_hanging(tmp_path, monkeypatch):
    monkeypatch.setattr("teachdesk.recording.InputHooks", TestHooks)
    store = Store(tmp_path)
    task = store.create_task("Disk failure", "Failure fixture")
    recorder = Recorder(store, FakeDesktop(), SCOPE, task)
    recorder.queue.put_nowait((0, "key", {"key": "<redacted>", "down": True}))
    monkeypatch.setattr(store, "event", lambda *a: (_ for _ in ()).throw(RuntimeError("simulated disk write failure")))
    recorder.start()
    assert recorder.finished.wait(2)
    assert "disk write" in recorder.error
    assert not store.evidence(task)



def configure(store, monkeypatch):
    monkeypatch.setenv("TEACHDESK_MODEL_KEY", "test-transport-only-not-a-real-credential")
    model.save_settings(store, {"base_url": "https://model.example/v1", "model": "test-vision", "consent": True, "local_no_key": False})


def test_missing_model_never_substitutes_learning(project, monkeypatch):
    store, task, *_ = project
    monkeypatch.delenv("TEACHDESK_MODEL_KEY", raising=False)
    assert not model.availability(store)[0]
    with pytest.raises(ValueError, match="unavailable"):
        model.generate(store, task)


def test_model_transport_contract_and_holdout_isolation(project, monkeypatch):
    store, task, train, held, vid, w = project
    configure(store, monkeypatch)
    calls = []
    def endpoint(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert request.url == "https://model.example/v1/chat/completions"
        assert payload["response_format"] == {"type": "json_object"}
        assert held not in request.content.decode()
        assert any(c["type"] == "image_url" for c in payload["messages"][1]["content"])
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(w)}}], "usage": {"total_tokens": 123}})
    original = httpx.Client
    monkeypatch.setattr(model.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(endpoint), **kw))
    candidate = model.generate(store, task)
    assert len(calls) == 1
    assert store.version(candidate)["workflow"] == w
    assert not store.version(candidate)["reviewed"]
    assert "test-transport-only" not in (store.root/"model.json").read_text()
    assert store.task(task)["active_version"] is None


def test_model_error_does_not_log_provider_body_or_secret(project, monkeypatch):
    store, task, *_ = project
    configure(store, monkeypatch)
    original = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="private request echoed by provider"))
    monkeypatch.setattr(model.httpx, "Client", lambda **kw: original(transport=transport, **kw))
    with pytest.raises(RuntimeError) as exc:
        model.generate(store, task)
    assert "401" in str(exc.value) and "private request" not in str(exc.value)


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://user:secret@model.example/v1", "https://model.example/v1?api_key=secret", "file:///etc/passwd"])
def test_model_endpoint_validation(url):
    with pytest.raises(ValueError):
        model.validate_settings({"base_url": url, "model": "vision", "consent": True})


def test_ui_library_review_lab_and_reopen(project, monkeypatch):
    if os.name != "nt":
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from teachdesk.ui import MainWindow
    from teachdesk.lab import Lab
    class Unavailable:
        def __init__(self): raise RuntimeError("Platform desktop deliberately disabled in GUI unit test")
    monkeypatch.setattr("teachdesk.ui.WindowsDesktop", Unavailable)
    store, task, *_ = project
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store)
    window.task_id = task
    window.refresh_library()
    window.show()
    app.processEvents()
    assert window.versions.count() == 1
    assert "Fixture" in window.title.text()
    assert "Change fixture state" in window.summary.toPlainText()
    assert window.timeline.rowCount() > 0
    window.timeline.selectRow(0)
    assert not window.frame_label.pixmap().isNull()
    window.close()
    reopened = MainWindow(Store(store.root))
    reopened.task_id = task
    reopened.refresh_library()
    assert reopened.versions.count() == 1
    lab = Lab()
    lab.select()
    lab.edit.setText("oak")
    assert lab.finish.isEnabled()
    lab.complete()
    assert lab.status.text() == "COMPLETE — oak stored"
    lab.exception.setChecked(True)
    assert not lab.oak.isEnabled()
    lab.close()
    reopened.close()


@pytest.mark.parametrize("has_frame,error", [(True, None), (True, "Emergency stop"), (False, "No frames captured")])
def test_finished_recording_opens_its_own_timeline(project, monkeypatch, has_frame, error):
    import threading
    from types import SimpleNamespace
    from PIL import Image
    from PySide6.QtWidgets import QApplication, QMessageBox
    from teachdesk.ui import MainWindow

    if os.name != "nt":
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    class Unavailable:
        def __init__(self): raise RuntimeError("Desktop disabled for UI regression test")
    monkeypatch.setattr("teachdesk.ui.WindowsDesktop", Unavailable)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    store, task, old_demo, *_ = project
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store)
    try:
        window.task_id = task
        window.refresh_library()
        window.demos.setCurrentIndex(window.demos.findData(old_demo))
        window.timeline.selectRow(0)
        assert not window.frame_label.pixmap().isNull()

        finished_demo = store.create_demo(task, {"capture_validation": 3})
        store.event(finished_demo, 0, 0, "capture_resumed", {})
        if has_frame:
            store.frame(finished_demo, .1, Image.new("RGB", (80, 60), "red"), {})
        store.execute("UPDATE demos SET status=? WHERE id=?", ("interrupted" if error else "complete", finished_demo))
        finished = threading.Event()
        finished.set()
        window.recorder = SimpleNamespace(finished=finished, error=error, demo=finished_demo)
        # Even if the user browsed a different task while teaching, show the
        # recording that actually finished, rather than that task's latest one.
        window.task_id = store.create_task("Other task", "Unrelated")
        window.refresh_library()
        window.tabs.setCurrentIndex(0)
        window.poll()

        assert window.recorder is None
        assert window.task_id == task
        assert window.demos.currentData() == finished_demo
        assert window.tabs.currentIndex() == 1
        assert warnings == ([error] if error else [])
        if has_frame:
            assert window.timeline_entries[window.timeline.currentRow()]["kind"] == "frame"
            assert window.frame_label.pixmap().toImage().pixelColor(0, 0).name() == "#ff0000"
        else:
            assert window.frame_label.pixmap().isNull()
        # Routine refreshes still preserve a deliberately selected older demo.
        window.demos.setCurrentIndex(window.demos.findData(old_demo))
        window.refresh_library()
        assert window.demos.currentData() == old_demo
    finally:
        window.close()
