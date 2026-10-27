from __future__ import annotations

import copy
import json

import numpy as np
import pytest
from PIL import Image

from teachdesk.storage import Store
from teachdesk.windows import Window


DISPLAY = {"left": 0, "top": 0, "width": 800, "height": 600, "dpi": 96}
SCOPE = Window(1, 2, "C:/test/fixture.exe", "Test fixture")


def pattern(seed):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(20, 240, size=(26, 48, 3), dtype=np.uint8))


def scene(marker, position=(20, 20)):
    image = Image.new("RGB", (400, 250), "#edf0f4")
    if marker is not None:
        image.paste(pattern(marker), position)
    return image


@pytest.fixture
def project(tmp_path):
    store = Store(tmp_path)
    task = store.create_task("Fixture", "Deterministic test fixture, not a learned or model-generated task")
    meta = {"window": {"executable": SCOPE.executable}, "display": DISPLAY, "masks": [], "capture_validation": 3}
    train = store.create_demo(task, meta)
    start = store.frame(train, 0, scene(1), {})
    end = store.frame(train, 1, scene(2, (140, 150)), {})
    store.execute("UPDATE demos SET status='complete' WHERE id=?", (train,))
    held = store.create_demo(task, meta, "practice")
    store.frame(held, 0, scene(1, (240, 80)), {})
    store.frame(held, 1, scene(2, (140, 150)), {})
    store.execute("UPDATE demos SET status='complete' WHERE id=?", (held,))
    workflow = {"schema": 1, "goal": "Change fixture state", "inputs": {}, "scope": "Fixture only; one visual transition",
                "sources": [train], "start": "button", "completion": "done", "entry": "click",
                "targets": {"button": {"frame": start, "bbox": [20, 20, 68, 46], "description": "Fixture marker"},
                            "done": {"frame": end, "bbox": [140, 150, 188, 176], "description": "Fixture result"}},
                "nodes": [{"id": "click", "kind": "click", "target": "button", "verify": "done", "next": "end", "basis": "demonstrated", "evidence": train+":0.1", "consequential": False},
                          {"id": "end", "kind": "finish", "basis": "demonstrated", "evidence": train+":1", "consequential": False}],
                "questions": [], "assumptions": [], "exceptions": "Any different visual state stops the workflow"}
    vid = store.add_version(task, workflow)
    store.execute("UPDATE versions SET reviewed=1 WHERE id=?", (vid,))
    return store, task, train, held, vid, copy.deepcopy(workflow)


class FakeDesktop:
    """An explicit test double. Production UI never substitutes this for Windows."""
    def __init__(self):
        self.image = scene(1, (240, 80))
        self.sent = []
        self.cursor = (100, 100)
        self.scope_ok = True
        self.after_send = lambda kw: None

    def display(self):
        return DISPLAY.copy()

    def check(self, scope, display=None):
        if not self.scope_ok:
            raise RuntimeError("Target lost focus")
        return {"left": 50, "top": 50, "width": 400, "height": 250}

    def capture(self, scope, display=None, masks=()):
        return self.image.copy(), self.check(scope, display)

    def position(self):
        return self.cursor

    def foreground(self):
        return 1 if self.scope_ok else 9

    def send(self, **kw):
        self.sent.append(kw)
        if "move" in kw:
            self.cursor = kw["move"]
        if kw.get("button") == "left" and kw.get("down") is False and not self.image.getbbox() is None:
            if abs(self.cursor[0]-314) < 3 and abs(self.cursor[1]-143) < 3:
                self.image = scene(2, (140, 150))
        self.after_send(kw)
