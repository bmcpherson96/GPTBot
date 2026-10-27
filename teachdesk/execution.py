from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path

from .perception import UnknownState, locate, materialize
from .recording import learn_style
from .storage import new_id
from .workflow import ACTIONS, readiness, validate
from .windows import CAPTURE_VALIDATION_VERSION, WindowNotReady


class Cancelled(RuntimeError):
    pass


class Paused(RuntimeError):
    pass


class RunOutcome(Exception):
    def __init__(self, outcome, detail):
        self.outcome, self.detail = outcome, detail


class Control:
    def __init__(self):
        self.cancelled, self.paused = threading.Event(), threading.Event()
        self.reason = ""
        self.pause_count = 0
        self.lock = threading.Lock()
        self.release = lambda: None
        self.health = lambda: True

    def stop(self, reason="Emergency stop"):
        self.reason = reason
        self.cancelled.set()  # visible to queued input before acquiring release lock
        self.release()

    def pause(self, reason="Manual intervention"):
        with self.lock:
            self.reason = reason
            if not self.paused.is_set():
                self.pause_count += 1
            self.paused.set()
        self.release()

    def resume(self):
        self.paused.clear()


VK = {**{chr(x): x-32 for x in range(ord("a"), ord("z")+1)}, **{str(x): 48+x for x in range(10)},
      "enter": 13, "tab": 9, "escape": 27, "space": 32, "backspace": 8, "delete": 46,
      "left": 37, "right": 39, "up": 38, "down": 40, "home": 36, "end": 35, "ctrl": 17, "alt": 18, "shift": 16}


class VisibleInput:
    def __init__(self, desktop, scope, display, control, style, max_seconds=120):
        self.desktop, self.scope, self.display, self.control, self.style = desktop, scope, display, control, style
        self.deadline = time.monotonic()+max_seconds
        self.lock = threading.RLock()
        self.held = set()
        self.geometry = None
        self.interventions = 0
        self.distance, self.moving_seconds = 0.0, 0.0
        self.release_errors = []
        self.control.release = self.release

    def gate(self):
        if self.control.cancelled.is_set():
            raise Cancelled(self.control.reason)
        if not self.control.health():
            self.control.stop("Emergency hotkey or physical input observer stopped")
            raise Cancelled(self.control.reason)
        if time.monotonic() > self.deadline:
            self.control.stop("Run duration limit reached")
            raise Cancelled(self.control.reason)
        if self.control.paused.is_set():
            raise Paused(self.control.reason)
        try:
            rect = self.desktop.check(self.scope, self.display)
            if self.geometry and rect != self.geometry:
                raise UnknownState("Window geometry changed during input")
        except Exception as exc:
            self.control.pause(str(exc))
            raise Paused(str(exc)) from exc

    def wait(self, seconds):
        until = time.monotonic()+seconds
        while True:
            self.gate()
            left = until-time.monotonic()
            if left <= 0:
                break
            self.control.cancelled.wait(min(.01, left))

    def send(self, **kwargs):
        with self.lock:
            self.gate()
            kind, value = ("button", kwargs["button"]) if "button" in kwargs else (("key", kwargs["key"]) if "key" in kwargs else (("unicode", kwargs["unicode"]) if "unicode" in kwargs else (None, None)))
            # Record intended down before SendInput: a partial/error still gets a best-effort release.
            if kind and kwargs.get("down"):
                self.held.add((kind, value))
            self.desktop.send(**kwargs)
            if kind and not kwargs.get("down"):
                self.held.discard((kind, value))

    def release(self):
        with self.lock:
            for kind, value in list(self.held):
                try:
                    self.desktop.send(**{kind: value, "down": False})
                    self.held.discard((kind, value))
                except Exception as exc:
                    self.release_errors.append(str(exc))

    def move(self, x, y):
        started = time.perf_counter()
        sx, sy = self.desktop.position()
        distance = math.hypot(x-sx, y-sy)
        duration = min(5., max(.12, distance/self.style["speed"]))
        count = max(2, math.ceil(duration*60))
        for i in range(1, count+1):
            t = i/count
            smooth = t*t*(3-2*t)
            parallel, perpendicular = smooth, 0
            profile = self.style.get("motion_profile", [])
            if len(profile) >= 4:
                after = next((j for j, point in enumerate(profile) if point[0] >= t), len(profile)-1)
                a, b = profile[max(0, after-1)], profile[after]
                ratio = min(1, max(0, (t-a[0])/max(.0001, b[0]-a[0])))
                parallel, perpendicular = a[1]+(b[1]-a[1])*ratio, a[2]+(b[2]-a[2])*ratio
            px = round(sx+(x-sx)*parallel-(y-sy)*perpendicular)
            py = round(sy+(y-sy)*parallel+(x-sx)*perpendicular)
            px = max(self.display["left"], min(self.display["left"]+self.display["width"]-1, px))
            py = max(self.display["top"], min(self.display["top"]+self.display["height"]-1, py))
            self.send(move=(px, py))
            self.wait(duration/count)
        self.distance += distance
        self.moving_seconds += time.perf_counter()-started
        self.wait(self.style["gap"])

    def click(self, double=False):
        for _ in range(2 if double else 1):
            self.send(button="left", down=True)
            self.wait(self.style["hold"])
            self.send(button="left", down=False)
            if double:
                self.wait(.08)

    def type_text(self, text):
        # UTF-16 units support non-BMP characters; no clipboard or hidden paste.
        for char in text:
            units = char.encode("utf-16-le")
            for offset in range(0, len(units), 2):
                code = int.from_bytes(units[offset:offset+2], "little")
                self.send(unicode=code, down=True)
                self.send(unicode=code, down=False)
            self.wait(self.style.get("typing_gap", self.style["gap"]))

    def keys(self, keys, duration=None):
        for key in keys:
            self.send(key=VK[key], down=True)
        self.wait(duration or self.style["hold"])
        for key in reversed(keys):
            self.send(key=VK[key], down=False)


class Runner:
    def __init__(self, store, desktop, scope, version, control, inputs=None, practice_demo=None, authorized=(), max_seconds=120, pause_on_manual=True):
        self.store, self.desktop, self.scope, self.version, self.control = store, desktop, scope, version, control
        self.w = validate(version["workflow"])
        self.inputs, self.practice_demo, self.authorized = inputs or {}, practice_demo, set(authorized)
        self.display = desktop.display()
        source_demos = [d for d in store.evidence(version["task"]) if d["id"] in self.w["sources"]]
        self.style = learn_style(source_demos)
        self.masks = source_demos[0]["metadata"].get("masks", []) if source_demos else []
        self.input = VisibleInput(desktop, scope, self.display, control, self.style, max_seconds)
        self.pause_on_manual = pause_on_manual
        self.id = None
        self.trace, self.coverage, self.last_image = [], set(), None
        self.interventions = 0
        self.variation = []
        self.last_manual = -1.0
        self.state = "Stopped"

    def preflight(self):
        if not self.version["reviewed"]:
            raise ValueError("Review supported scope and assumptions first")
        if any(q["blocking"] for q in self.w["questions"]):
            raise ValueError("Answer blocking questions and regenerate the workflow to apply their answers")
        if set(self.inputs) != set(self.w["inputs"]):
            raise ValueError("Supply exactly the declared task inputs")
        if any(not isinstance(v, str) or len(v) > 2000 for v in self.inputs.values()):
            raise ValueError("Input values must be text up to 2000 characters")
        needed = {n["id"] for n in self.w["nodes"] if n["consequential"]}
        if not needed <= self.authorized:
            raise ValueError("Authorize the listed consequential steps for this run")
        if self.practice_demo:
            practice = {d["id"]: d for d in self.store.evidence(self.version["task"], "practice")}
            if self.practice_demo not in practice or self.practice_demo in self.w["sources"]:
                raise ValueError("Practice requires a separate completed held-out demonstration")
            if practice[self.practice_demo]["metadata"].get("capture_validation") != CAPTURE_VALIDATION_VERSION:
                raise ValueError("Practice example predates capture validation v2; record it again")
            if practice[self.practice_demo]["metadata"]["window"]["executable"] != self.scope.executable:
                raise ValueError("Practice evidence belongs to a different application")
        elif self.store.task(self.version["task"])["active_version"] != self.version["id"] or not all(c["passed"] for c in readiness(self.store, self.version)):
            raise ValueError("Only a validated active version can Run; use supervised practice for candidates")
        demos = {d["id"]: d for d in self.store.evidence(self.version["task"])}
        for source in self.w["sources"]:
            if source not in demos or demos[source]["metadata"]["window"]["executable"] != self.scope.executable:
                raise ValueError("Selected window application differs from the training evidence")
            if demos[source]["metadata"].get("capture_validation") != CAPTURE_VALIDATION_VERSION:
                raise ValueError("Training evidence predates capture validation v2; record a fresh demonstration")
            source_title = demos[source]["metadata"]["window"].get("title")
            if source_title and self.scope.title != source_title:
                raise ValueError("Window title differs from the demonstrated scope; teach a separate candidate")
            if demos[source]["metadata"].get("display") != self.display:
                raise ValueError("Display geometry or scaling changed; record and validate a new candidate")
            if demos[source]["metadata"].get("masks", []) != self.masks:
                raise ValueError("Recording exclusions differ; use demonstrations with consistent exclusions")
        self.desktop.check(self.scope, self.display)
        getattr(self.desktop, "check_idle", lambda: None)()

    def manual(self, kind, data):
        if self.state == "Running" and not self.control.paused.is_set() and not self.control.cancelled.is_set():
            now = time.monotonic()
            if now-self.last_manual > .5:
                self.interventions += 1
            self.last_manual = now
            if self.pause_on_manual:
                self.control.pause("Physical mouse/keyboard input detected; correct the state before resuming")

    def observe(self):
        self.input.geometry = None
        self.input.gate()
        try:
            image, rect = self.desktop.capture(self.scope, self.display, self.masks)
        except WindowNotReady as exc:
            self.control.pause(str(exc))
            raise Paused(str(exc)) from exc
        self.input.gate()
        self.last_image = image
        self.input.geometry = rect
        return image, rect

    def see(self, target):
        image, rect = self.observe()
        return locate(image, self.targets[target]), rect

    def wait_target(self, target, timeout=5):
        until = time.monotonic()+timeout
        stable = 0
        while True:
            found, rect = self.see(target)
            stable = stable+1 if found else 0
            if stable >= 2:
                return found, rect
            if time.monotonic() >= until:
                raise UnknownState("Expected visual state missing: " + target)
            self.input.wait(.12)

    def await_resume(self):
        self.state = "Paused"
        self.input.release()
        while self.control.paused.is_set():
            if self.control.cancelled.wait(.03):
                raise Cancelled(self.control.reason)
            if time.monotonic() > self.input.deadline:
                raise Cancelled("Run duration limit reached while paused")
        self.input.geometry = None
        self.input.gate()
        self.state = "Running"

    def execute(self, use_hooks=True):
        hooks = None
        outcome, detail = "failed", ""
        self.id = new_id()
        self.store.execute("INSERT INTO runs(id,task,version,practice_demo,outcome,detail,created) VALUES(?,?,?,?,?,?,?)", (self.id, self.version["task"], self.version["id"], self.practice_demo, "running", "{}", time.time()))
        try:
            self.preflight()
            self.targets = materialize(self.store, self.version)
            self.state = "Running"
            if use_hooks:
                from .windows import InputHooks
                hooks = InputHooks(self.manual)
                hooks.start()
                previous_health = self.control.health
                self.control.health = lambda: previous_health() and hooks.healthy
            found, _ = self.see(self.w["completion"])
            if found:
                raise UnknownState("Completion already visible at start; reset the application first")
            self.wait_target(self.w["start"])
            if self.practice_demo:
                # Current start must correspond visually to the held-out example, not just a user label.
                evidence = next(d for d in self.store.evidence(self.version["task"], "practice") if d["id"] == self.practice_demo)
                from PIL import Image
                with Image.open(self.store.root/evidence["frames"][0]["path"]) as start:
                    ref = locate(start, self.targets[self.w["start"]])
                if ref is None:
                    raise UnknownState("Held-out example does not show the starting condition")
                current, rect = self.see(self.w["start"])
                if current is None or math.dist((ref.x, ref.y), (current.x, current.y)) > 12:
                    raise UnknownState("Reset to the recorded held-out starting layout before practice")
                completion_evidence = False
                for frame in evidence["frames"][-8:]:
                    self.input.gate()
                    with Image.open(self.store.root/frame["path"]) as image:
                        completion_evidence = locate(image, self.targets[self.w["completion"]]) is not None
                    if completion_evidence:
                        break
                if not completion_evidence and evidence["metadata"].get("expected_outcome", "verified") != "expected_stop":
                    raise UnknownState("Held-out demonstration does not show the expected completion")
                with Image.open(self.store.root/evidence["frames"][0]["path"]) as start:
                    for name in {n["target"] for n in self.w["nodes"] if n["kind"] in ACTIONS}:
                        match = locate(start, self.targets[name])
                        bbox = self.w["targets"][name]["bbox"]
                        center = ((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2)
                        if match and math.dist(center, (match.x, match.y)) >= 20:
                            self.variation.append(name+": visually relocated by at least 20 window pixels")
            nodes = {n["id"]: n for n in self.w["nodes"]}
            current, counts = self.w["entry"], {}
            for step in range(80):
                n = nodes[current]
                counts[current] = counts.get(current, 0)+1
                if counts[current] > 8:
                    raise UnknownState("Repeated node limit reached")
                self.trace.append({"step": current, "time": time.time(), "kind": n["kind"]})
                while True:
                    begun = False
                    try:
                        self.input.geometry = None
                        self.input.gate()
                        kind = n["kind"]
                        if kind == "finish":
                            self.wait_target(self.w["completion"])
                            if self.practice_demo and evidence["metadata"].get("expected_outcome", "verified") == "expected_stop":
                                raise UnknownState("Completed instead of the held-out example's expected stop")
                            self.interventions = max(self.interventions, self.control.pause_count)
                            outcome = "intervened" if self.interventions else "verified"
                            detail = "Visual completion verified twice; intervention runs do not qualify for readiness" if self.interventions else "Visual completion verified twice"
                            raise RunOutcome(outcome, detail)
                        if kind == "stop":
                            outcome = "expected_stop" if self.practice_demo and evidence["metadata"].get("expected_outcome") == "expected_stop" and not self.control.pause_count else "stopped"
                            detail = n["reason"]
                            raise RunOutcome(outcome, detail)
                        if kind == "branch":
                            found, _ = self.see(n["target"])
                            branch = "true" if found else "false"
                            self.coverage.add(current+":"+branch)
                            current = n["next"] if found else n["otherwise"]
                            break
                        target, rect = self.wait_target(n["target"], n.get("timeout", 5))
                        if kind in ACTIONS:
                            if locate(self.last_image, self.targets[n["verify"]]) is not None:
                                raise UnknownState("Action postcondition already visible; cannot establish this action's result")
                            begun = True
                            self.input.move(rect["left"]+target.x, rect["top"]+target.y)
                            if kind in {"click", "double_click"}:
                                self.input.click(kind == "double_click")
                            elif kind == "drag":
                                destination = locate(self.last_image, self.targets[n["to"]])
                                if destination is None:
                                    raise UnknownState("Drag destination missing")
                                self.input.send(button="left", down=True)
                                self.input.move(rect["left"]+destination.x, rect["top"]+destination.y)
                                self.input.send(button="left", down=False)
                            elif kind == "scroll":
                                self.input.send(scroll=n["dy"])
                            elif kind == "type":
                                self.input.click()
                                text = re.sub(r"\$\{([^}]+)\}", lambda m: self.inputs[m[1]], n["text"])
                                self.input.type_text(text)
                            elif kind == "key":
                                self.input.keys(n["keys"], n.get("duration"))
                            self.wait_target(n["verify"], n.get("timeout", 5))
                        current = n["next"]
                        break
                    except Paused:
                        self.await_resume()
                        if begun:
                            # Never replay partially typed text, held actions or consequential clicks.
                            self.wait_target(n["verify"], n.get("timeout", 5))
                            current = n["next"]
                            break
            raise UnknownState("Total action limit reached")
        except RunOutcome as result:
            outcome, detail = result.outcome, result.detail
        except Cancelled as exc:
            outcome, detail = "stopped", str(exc)
        except Exception as exc:
            detail = str(exc)
        finally:
            self.input.release()
            if hooks:
                hooks.close()
            self.state = "Stopped"
            evidence_path = self.store.root/"runs"/self.id
            evidence_path.mkdir(parents=True, exist_ok=True)
            if self.last_image is not None:
                self.last_image.save(evidence_path/"last-state.png")
            result = {"reason": detail, "coverage": sorted(self.coverage), "interventions": max(self.interventions, self.control.pause_count), "trace": self.trace,
                      "variation": self.variation,
                      "release_errors": self.input.release_errors,
                      "style": {"demonstrated": self.style, "executed_speed": self.input.distance/max(.001, self.input.moving_seconds), "note": "Timing resemblance only; path/acceleration fidelity is not measured"}}
            if self.input.release_errors:
                outcome = "failed"
                result["reason"] = "Input release failed; check held keys/buttons on desktop"
            self.store.execute("UPDATE runs SET outcome=?,detail=? WHERE id=?", (outcome, json.dumps(result), self.id))
        return outcome
