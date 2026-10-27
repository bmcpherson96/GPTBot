from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import asdict

from .windows import CAPTURE_VALIDATION_VERSION, InputHooks, WindowNotReady


class Recorder:
    def __init__(self, store, desktop, scope, task, role="train", capture_text=False, masks=(), limit=600, expected_outcome="verified", health=lambda: True):
        self.store, self.desktop, self.scope = store, desktop, scope
        self.display = desktop.display()
        self.health = health
        self.masks, self.limit = masks, limit
        self.capture_text = capture_text and not masks
        self.started = time.perf_counter()
        self.cancelled = threading.Event()
        self.paused = threading.Event()
        self.queue = queue.Queue(maxsize=10000)
        self.error = None
        self.capture_reason = "Waiting for first frame"
        self.finished = threading.Event()
        self.held = {}
        self.callback_lock = threading.Lock()
        self.last_move = 0
        self.bytes_written = 0
        self.demo = store.create_demo(task, {"window": asdict(scope), "display": self.display, "masks": masks, "capture_text": self.capture_text, "fps": 4, "ignored_ranges": [], "expected_outcome": expected_outcome, "capture_validation": CAPTURE_VALIDATION_VERSION}, role)
        self.hooks = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.desktop.check(self.scope, self.display)
        getattr(self.desktop, "check_idle", lambda: None)()
        self.hooks = InputHooks(self._input)
        try:
            self.hooks.start()
        except Exception:
            self.hooks.close()
            self.store.execute("UPDATE demos SET status='interrupted' WHERE id=?", (self.demo,))
            raise
        self.thread.start()

    def _input(self, kind, data):
        if self.cancelled.is_set() or self.paused.is_set():
            return
        observable = getattr(self.desktop, "can_observe_input", lambda scope: self.desktop.foreground() == scope.hwnd)
        if not observable(self.scope):
            return
        now = time.perf_counter() - self.started
        with self.callback_lock:
            if kind == "move":
                if now - self.last_move < .05:
                    return
                self.last_move = now
            if kind in {"key", "button"}:
                ident = (kind, data.get("key", data.get("button")))
                if data["down"]:
                    self.held.setdefault(ident, now)
                else:
                    data["held_seconds"] = max(0, now-self.held.pop(ident, now))
            if kind == "key" and not self.capture_text:
                safe = {"enter", "tab", "esc", "left", "right", "up", "down", "shift", "ctrl_l", "ctrl_r", "alt_l", "alt_r", "backspace"}
                if data["key"] not in safe:
                    data["key"], data["redacted"] = "<redacted>", True
            data["foreground_hwnd"] = self.scope.hwnd
            try:
                self.queue.put_nowait((now, kind, data))
            except queue.Full:
                self.error = "Input queue overflow; demonstration is incomplete"
                self.cancelled.set()

    def pause(self, paused=True):
        if paused:
            self.paused.set()
        else:
            self.desktop.check(self.scope, self.display)
            self.paused.clear()
        self.queue.put_nowait((time.perf_counter()-self.started, "pause" if paused else "resume", {}))
        self.held.clear()

    def stop(self, emergency=False):
        if emergency:
            self.error = "Emergency stop"
        self.cancelled.set()

    def _run(self):
        seq, next_frame = 0, 0
        try:
            while not self.cancelled.is_set():
                if not self.health() or not getattr(self.hooks, "healthy", True):
                    raise RuntimeError("Emergency hotkey or physical input observer stopped")
                t = time.perf_counter()-self.started
                if t >= self.limit:
                    self.error = "Recording duration limit reached"
                    break
                for _ in range(500):
                    try:
                        event = self.queue.get_nowait()
                    except queue.Empty:
                        break
                    self.store.event(self.demo, seq, *event)
                    seq += 1
                if seq > 50000:
                    raise RuntimeError("Recording event limit reached")
                if not self.paused.is_set() and not self.cancelled.is_set() and t >= next_frame:
                    try:
                        if self.desktop.foreground() != self.scope.hwnd:
                            raise WindowNotReady("Target out of focus")
                        before = time.perf_counter()-self.started
                        image, rect = self.desktop.capture(self.scope, self.display, self.masks)
                        if self.cancelled.is_set() or self.paused.is_set():
                            continue  # Discard an in-flight frame after stop/pause.
                        after = time.perf_counter()-self.started
                        fid = self.store.frame(self.demo, (before+after)/2, image, {**rect, "capture_start": before, "capture_end": after, "foreground_hwnd": self.scope.hwnd})
                        self.bytes_written += (self.store.root/"demos"/self.demo/(fid+".png")).stat().st_size
                        if self.bytes_written > 512*1024*1024:
                            raise RuntimeError("512 MiB demonstration storage limit reached")
                        if self.capture_reason:
                            self.store.event(self.demo, seq, after, "capture_resumed", {})
                            seq += 1
                        self.capture_reason = None
                    except WindowNotReady as exc:
                        reason = str(exc)
                        if reason != self.capture_reason:
                            self.store.event(self.demo, seq, time.perf_counter()-self.started, "capture_paused", {"reason": reason})
                            seq += 1
                        self.capture_reason = reason
                    next_frame = t+.25
                self.cancelled.wait(.01)
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.cancelled.set()
            try:
                if self.hooks:
                    self.hooks.close()
                while not self.queue.empty():
                    self.store.event(self.demo, seq, *self.queue.get_nowait())
                    seq += 1
                count = self.store.rows("SELECT count(*) AS n FROM frames WHERE demo=?", (self.demo,))[0]["n"]
                self.store.execute("UPDATE demos SET status=? WHERE id=?", ("interrupted" if self.error or not count else "complete", self.demo))
            except Exception as exc:
                self.error = self.error or "Recording finalization failed: "+str(exc)
                try:
                    self.store.execute("UPDATE demos SET status='interrupted' WHERE id=?", (self.demo,))
                except Exception:
                    pass  # Next startup also invalidates unfinished recordings.
            finally:
                self.finished.set()


def learn_style(demos):
    """Robust descriptive timing statistics; never jitter or fabricate mistakes."""
    import statistics
    movements, holds, gaps, paths, key_gaps, click_holds = [], [], [], [], [], []
    for demo in demos:
        last = None
        path = []
        last_key = None
        segment = []
        for e in demo["events"]:
            if e["kind"] == "move":
                point = (e["data"].get("x", 0), e["data"].get("y", 0), e["t"])
                if path and 0 < point[2]-path[-1][2] < .3:
                    import math
                    movements.append(math.dist(point[:2], path[-1][:2])/(point[2]-path[-1][2]))
                path.append(point)
                segment.append(point)
            if e["kind"] in {"button", "key"}:
                d = e["data"].get("held_seconds")
                if d is not None and .01 <= d <= 2:
                    holds.append(d)
                    if e["kind"] == "button":
                        click_holds.append(d)
                if e["data"].get("down"):
                    if last is not None and .03 < e["t"]-last < 3:
                        gaps.append(e["t"]-last)
                    last = e["t"]
                    if e["kind"] == "key":
                        if last_key is not None and .025 <= e["t"]-last_key <= 2:
                            key_gaps.append(e["t"]-last_key)
                        last_key = e["t"]
                    if e["kind"] == "button" and len(segment) >= 4:
                        import math
                        sx, sy, start = segment[0]
                        ex, ey, end = segment[-1]
                        length, elapsed = math.hypot(ex-sx, ey-sy), end-start
                        if length >= 40 and .1 <= elapsed <= 5:
                            ux, uy = (ex-sx)/length, (ey-sy)/length
                            profile = [[(t-start)/elapsed, ((x-sx)*ux+(y-sy)*uy)/length, (-(x-sx)*uy+(y-sy)*ux)/length] for x, y, t in segment]
                            if all(-.2 <= p[1] <= 1.2 and abs(p[2]) <= .4 for p in profile):
                                paths.append(profile)
                        segment = []
    median = lambda xs, fallback, lo, hi: min(hi, max(lo, statistics.median(xs) if xs else fallback))
    # Use a representative observed path, independent of all task coordinates.
    # The median-duration profile retains demonstrated acceleration, curvature and corrections.
    profile = sorted(paths, key=len)[len(paths)//2] if paths else []
    if len(profile) > 80:
        profile = [profile[round(i*(len(profile)-1)/79)] for i in range(80)]
    return {"speed": median(movements, 500, 100, 1200), "hold": median(click_holds or holds, .09, .04, .4),
            "gap": median(gaps, .15, .05, .8), "typing_gap": median(key_gaps, .12, .03, .8),
            "motion_profile": profile, "path_samples": sum(len(p) for p in paths), "timing_samples": len(gaps),
            "method": "representative normalized demonstrated path and median timing; smooth fallback if insufficient samples; no error injection"}
