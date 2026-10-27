from __future__ import annotations

import copy
import json
import threading
import time

import pytest
from PIL import Image

from teachdesk.execution import Cancelled, Control, Paused, Runner, VisibleInput
from teachdesk.perception import UnknownState, locate, materialize
from teachdesk.storage import Store
from teachdesk.workflow import readiness, validate

from conftest import DISPLAY, SCOPE, FakeDesktop, pattern, scene


def quick_input(monkeypatch):
    monkeypatch.setattr(VisibleInput, "wait", lambda self, seconds: self.gate())


def test_persistence_and_synchronized_evidence(project):
    store, task, train, held, vid, w = project
    store.event(train, 0, .123, "button", {"down": True, "x": 40, "y": 30})
    reopened = Store(store.root)
    assert reopened.task(task)["name"] == "Fixture"
    evidence = reopened.evidence(task)
    assert evidence[0]["events"][0]["t"] == .123
    assert evidence[0]["frames"][0]["t"] == 0
    assert reopened.version(vid)["workflow"] == w
    assert reopened.evidence(task, "practice")[0]["id"] == held


def test_pattern_relocation_and_ambiguity():
    found = locate(scene(1, (270, 150)), pattern(1))
    assert (found.x, found.y) == (294, 163)
    image = scene(1, (20, 20))
    image.paste(pattern(1), (230, 100))
    with pytest.raises(UnknownState, match="ambiguous"):
        locate(image, pattern(1))
    assert locate(scene(None), pattern(1)) is None
    with pytest.raises(UnknownState, match="Low-information"):
        locate(scene(None), Image.new("RGB", (20, 20), "black"))


@pytest.mark.parametrize("mutate", [
    lambda w: w.update(entry="unknown"),
    lambda w: w["nodes"][0].update(kind="shell"),
    lambda w: w["nodes"][0].update(timeout=10000),
    lambda w: w["nodes"][0].update(duration=float("nan")),
    lambda w: w["nodes"][0].update(basis="certain"),
    lambda w: w["nodes"][0].pop("verify"),
    lambda w: w["targets"].update({"../../escape": w["targets"]["done"]}),
    lambda w: w.update(completion="button"),
    lambda w: w["nodes"].append({**w["nodes"][1], "id": "unreachable"}),
    lambda w: w.update(questions=[{"id": str(i), "text": "?", "blocking": True, "reference": "0"} for i in range(4)]),
])
def test_untrusted_workflow_rejected(project, mutate):
    w = project[-1]
    mutate(w)
    with pytest.raises(ValueError):
        validate(w)


def test_only_source_training_images_can_be_assets(project):
    store, task, train, held, vid, _ = project
    v = store.version(vid)
    materialize(store, v)
    v["workflow"]["targets"]["button"]["frame"] = store.evidence(task, "practice")[0]["frames"][0]["id"]
    with pytest.raises(ValueError, match="held-out"):
        materialize(store, v)


def test_visual_execution_changed_position_and_readiness(project, monkeypatch):
    store, task, train, held, vid, w = project
    quick_input(monkeypatch)
    assert not all(x["passed"] for x in readiness(store, store.version(vid)))
    d = FakeDesktop()
    runner = Runner(store, d, SCOPE, store.version(vid), Control(), practice_demo=held)
    assert runner.execute(use_hooks=False) == "verified"
    moves = [e["move"] for e in d.sent if "move" in e]
    assert moves[-1] == (314, 143)  # Target relocated from (20,20), plus window origin.
    assert all(x["passed"] for x in readiness(store, store.version(vid)))
    store.promote(task, vid)
    assert store.task(task)["active_version"] == vid
    d2 = FakeDesktop()
    assert Runner(store, d2, SCOPE, store.version(vid), Control()).execute(use_hooks=False) == "verified"
    run = store.rows("SELECT * FROM runs WHERE id=?", (runner.id,))[0]
    assert json.loads(run["detail"])["trace"][-1]["kind"] == "finish"
    assert (store.root/"runs"/runner.id/"last-state.png").exists()


def test_candidate_isolation_and_rollback(project, monkeypatch):
    store, task, _, held, vid, w = project
    quick_input(monkeypatch)
    Runner(store, FakeDesktop(), SCOPE, store.version(vid), Control(), practice_demo=held).execute(use_hooks=False)
    store.promote(task, vid)
    candidate = store.add_version(task, w)
    assert store.task(task)["active_version"] == vid
    with pytest.raises(ValueError, match="readiness"):
        store.promote(task, candidate)
    store.promote(task, vid)
    assert store.task(task)["active_version"] == vid


def test_clarification_answer_requires_new_graph(project, monkeypatch):
    store, task, _, held, vid, w = project
    w["questions"] = [{"id": "why", "text": "What selects the item?", "blocking": True, "reference": "0.1"}]
    new = store.add_version(task, w)
    store.execute("UPDATE versions SET reviewed=1,answers=? WHERE id=?", (json.dumps({"why": "Use Oak"}), new))
    runner = Runner(store, FakeDesktop(), SCOPE, store.version(new), Control(), practice_demo=held)
    with pytest.raises(ValueError, match="regenerate"):
        runner.preflight()
    assert not readiness(store, store.version(new))[1]["passed"]


@pytest.mark.parametrize("mode", ["movement", "typing", "held_key", "held_button"])
def test_emergency_cancels_queue_and_releases_inputs(mode):
    desktop, control = FakeDesktop(), Control()
    io = VisibleInput(desktop, SCOPE, DISPLAY, control, {"speed": 100, "hold": .2, "gap": .05})
    seen = threading.Event()
    def after(kw):
        if mode == "movement" and "move" in kw or mode == "typing" and "unicode" in kw and kw["down"] or mode == "held_key" and "key" in kw and kw["down"] or mode == "held_button" and "button" in kw and kw["down"]:
            seen.set()
    desktop.after_send = after
    errors = []
    def work():
        try:
            if mode == "movement": io.move(700, 500)
            if mode == "typing": io.type_text("A"*100)
            if mode == "held_key": io.keys(["shift", "a"], 3)
            if mode == "held_button":
                io.send(button="left", down=True)
                io.wait(3)
        except (Cancelled, Paused) as e:
            errors.append(e)
        finally:
            io.release()
    worker = threading.Thread(target=work)
    worker.start()
    assert seen.wait(2)
    start = time.perf_counter()
    control.stop()
    worker.join(1)
    assert not worker.is_alive()
    assert time.perf_counter()-start < .5
    assert not io.held
    assert errors
    before = len(desktop.sent)
    with pytest.raises(Cancelled):
        io.send(key=65, down=True)
    assert len(desktop.sent) == before


def test_manual_pause_releases_held_and_refocus_required():
    d, control = FakeDesktop(), Control()
    io = VisibleInput(d, SCOPE, DISPLAY, control, {"speed": 100, "gap": .05, "hold": .1})
    io.send(key=65, down=True)
    control.pause()
    assert not io.held
    with pytest.raises(Paused): io.send(key=66, down=True)
    d.scope_ok = False
    control.resume()
    with pytest.raises(Paused): io.gate()
    assert control.paused.is_set()


@pytest.mark.parametrize("condition", ["unexpected", "already_complete", "consequential", "wrong_app", "wrong_display", "not_reviewed"])
def test_preflight_and_unexpected_states_block_input(project, condition, monkeypatch):
    store, task, _, held, vid, w = project
    quick_input(monkeypatch)
    d = FakeDesktop()
    v = store.version(vid)
    if condition == "unexpected": d.image = scene(None)
    if condition == "already_complete": d.image = scene(2, (140, 150))
    if condition == "consequential": v["workflow"]["nodes"][0]["consequential"] = True
    if condition == "wrong_app":
        from teachdesk.windows import Window
        scope = Window(1, 2, "other.exe", "Wrong app")
    else: scope = SCOPE
    if condition == "wrong_display": d.display = lambda: {**DISPLAY, "dpi": 144}
    if condition == "not_reviewed": v["reviewed"] = 0
    # Short timeouts for a deliberately absent visual state.
    original = Runner.wait_target
    monkeypatch.setattr(Runner, "wait_target", lambda self, target, timeout=5: original(self, target, .02))
    r = Runner(store, d, scope, v, Control(), practice_demo=held)
    assert r.execute(use_hooks=False) == "failed"
    assert not d.sent


def test_failure_is_not_readiness_evidence(project):
    store, task, train, held, vid, _ = project
    store.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", ("fake", task, vid, held, "intervened", '{"coverage":[]}', time.time()))
    assert not readiness(store, store.version(vid))[3]["passed"]
    with pytest.raises(ValueError):
        Runner(store, FakeDesktop(), SCOPE, store.version(vid), Control(), practice_demo=train).preflight()


def test_delete_evidence_invalidates_derived_version_and_readiness(project):
    store, task, train, held, vid, _ = project
    store.delete_demo(train)
    assert not store.rows("SELECT * FROM versions WHERE id=?", (vid,))
    assert not (store.root/"demos"/train).exists()


def test_branch_coverage_requires_both_heldout_outcomes(project, monkeypatch):
    store, task, train, held, _, w = project
    quick_input(monkeypatch)
    optional_image = scene(1, (240, 80))
    optional_image.paste(pattern(3), (80, 170))
    extra = store.frame(train, .5, optional_image, {})
    w["targets"]["optional"] = {"frame": extra, "bbox": [80, 170, 128, 196], "description": "Optional fixture marker"}
    action = w["nodes"][0]
    other = {**action, "id": "other"}
    branch = {"id": "branch", "kind": "branch", "target": "optional", "next": "click", "otherwise": "other", "basis": "demonstrated", "evidence": train+":.5", "consequential": False}
    w["nodes"] = [branch, action, other, w["nodes"][1]]
    w["entry"] = "branch"
    candidate = store.add_version(task, w)
    store.execute("UPDATE versions SET reviewed=1 WHERE id=?", (candidate,))
    assert Runner(store, FakeDesktop(), SCOPE, store.version(candidate), Control(), practice_demo=held).execute(use_hooks=False) == "verified"
    assert not readiness(store, store.version(candidate))[-1]["passed"]
    new_held = store.create_demo(task, {"window": {"executable": SCOPE.executable}, "display": DISPLAY}, "practice")
    store.frame(new_held, 0, optional_image, {})
    store.frame(new_held, 1, scene(2, (140, 150)), {})
    store.execute("UPDATE demos SET status='complete' WHERE id=?", (new_held,))
    d = FakeDesktop()
    d.image = optional_image
    assert Runner(store, d, SCOPE, store.version(candidate), Control(), practice_demo=new_held).execute(use_hooks=False) == "verified"
    assert all(x["passed"] for x in readiness(store, store.version(candidate)))


def test_repeated_decision_loop_has_hard_stop(project, monkeypatch):
    store, task, train, held, _, w = project
    quick_input(monkeypatch)
    w["entry"] = "loop"
    w["nodes"] = [{"id": "loop", "kind": "branch", "target": "button", "next": "loop", "otherwise": "end", "basis": "inferred", "evidence": train+":0", "consequential": False}, w["nodes"][1]]
    vid = store.add_version(task, w)
    store.execute("UPDATE versions SET reviewed=1 WHERE id=?", (vid,))
    d = FakeDesktop()
    r = Runner(store, d, SCOPE, store.version(vid), Control(), practice_demo=held)
    assert r.execute(use_hooks=False) == "failed"
    assert "Repeated node limit" in store.rows("SELECT detail FROM runs WHERE id=?", (r.id,))[0]["detail"]
    assert not d.sent


def test_style_has_demonstrated_curve_separate_from_task_logic():
    from teachdesk.recording import learn_style
    events = [{"t": i*.1, "kind": "move", "data": {"x": x, "y": y}} for i, (x, y) in enumerate([(0, 0), (10, 3), (40, 12), (80, 10), (100, 0)])]
    events += [{"t": .5, "kind": "button", "data": {"down": True}}, {"t": .6, "kind": "button", "data": {"down": False, "held_seconds": .1}}]
    style = learn_style([{"events": events}])
    assert style["path_samples"] == 5
    assert max(point[2] for point in style["motion_profile"]) > 0
    assert style["motion_profile"][-1][1] == 1


def test_expected_stop_branch_is_evidence_but_not_a_completion(project, monkeypatch):
    store, task, train, held, _, w = project
    quick_input(monkeypatch)
    exception = scene(1, (240, 80))
    exception.paste(pattern(3), (80, 170))
    extra = store.frame(train, .5, exception, {})
    w["targets"]["exception"] = {"frame": extra, "bbox": [80, 170, 128, 196], "description": "Exception marker"}
    w["entry"] = "decide"
    w["nodes"] = [{"id": "decide", "kind": "branch", "target": "exception", "next": "halt", "otherwise": "click", "basis": "demonstrated", "evidence": train+":.5", "consequential": False}, *w["nodes"],
                  {"id": "halt", "kind": "stop", "reason": "Known exception: stop safely", "basis": "demonstrated", "evidence": train+":.5", "consequential": False}]
    vid = store.add_version(task, w)
    store.execute("UPDATE versions SET reviewed=1 WHERE id=?", (vid,))
    assert Runner(store, FakeDesktop(), SCOPE, store.version(vid), Control(), practice_demo=held).execute(use_hooks=False) == "verified"
    stopped = store.create_demo(task, {"window": {"executable": SCOPE.executable}, "display": DISPLAY, "expected_outcome": "expected_stop"}, "practice")
    store.frame(stopped, 0, exception, {})
    store.execute("UPDATE demos SET status='complete' WHERE id=?", (stopped,))
    d = FakeDesktop()
    d.image = exception
    r = Runner(store, d, SCOPE, store.version(vid), Control(), practice_demo=stopped)
    assert r.execute(use_hooks=False) == "expected_stop"
    assert not d.sent
    assert all(c["passed"] for c in readiness(store, store.version(vid)))
    assert store.rows("SELECT count(*) AS n FROM runs WHERE outcome='verified'")[0]["n"] == 1


def test_pause_count_is_per_episode_not_physical_event():
    control = Control()
    control.pause("User pause")
    control.pause("Another physical move")
    assert control.pause_count == 1
    control.resume()
    control.pause("Focus lost")
    assert control.pause_count == 2


def test_crash_reopen_and_changed_intent_invalidate_evidence(project):
    store, task, train, held, vid, _ = project
    store.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", ("crashed", task, vid, held, "running", "{}", time.time()))
    reopened = Store(store.root)
    row = reopened.rows("SELECT * FROM runs WHERE id='crashed'")[0]
    assert row["outcome"] == "interrupted"
    assert "closed" in json.loads(row["detail"])["reason"]
    reopened.invalidate(task, "Changed test scope")
    assert not reopened.version(vid)["reviewed"]
    assert reopened.rows("SELECT outcome FROM runs WHERE id='crashed'")[0]["outcome"] == "invalidated"


def test_delete_task_removes_local_evidence_and_versions(project):
    store, task, train, held, vid, _ = project
    materialize(store, store.version(vid))
    store.delete_task(task)
    assert not store.rows("SELECT * FROM tasks")
    assert not store.rows("SELECT * FROM versions")
    assert not store.rows("SELECT * FROM frames")
    assert not (store.root/"demos"/train).exists()
    assert not (store.root/"demos"/held).exists()
    assert not (store.root/"assets"/vid).exists()


def test_manual_input_never_qualifies_even_when_auto_pause_disabled(project, monkeypatch):
    store, task, _, held, vid, _ = project
    quick_input(monkeypatch)
    d = FakeDesktop()
    r = Runner(store, d, SCOPE, store.version(vid), Control(), practice_demo=held, pause_on_manual=False)
    d.after_send = lambda kw: r.manual("move", {"x": 1, "y": 2})
    assert r.execute(use_hooks=False) == "intervened"
    assert not r.control.paused.is_set()
    assert not readiness(store, store.version(vid))[3]["passed"]
