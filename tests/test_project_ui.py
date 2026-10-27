"""Project-first UI interactions, over real local storage and test-only evidence."""
from __future__ import annotations

import json
import os
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog

from teachdesk.storage import Store
from teachdesk.workflow import readiness
from teachdesk.project_ui import readable_plan


@pytest.fixture
def window(project, monkeypatch):
    if os.name != "nt":
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from teachdesk.ui import MainWindow
    class Unavailable:
        def __init__(self):
            raise RuntimeError("Desktop deliberately disabled for UI tests")
    monkeypatch.setattr("teachdesk.ui.WindowsDesktop", Unavailable)
    monkeypatch.delenv("TEACHDESK_MODEL_KEY", raising=False)
    app = QApplication.instance() or QApplication([])
    result = MainWindow(project[0])
    result.resize(900, 700)
    result.show()
    app.processEvents()
    yield result
    result.armed = False
    result.worker_busy = False
    result.recorder = result.runner = result.control = None
    result.close()


def open_project(window, task):
    shell = window.shell
    for row in range(shell.projects.count()):
        if shell.projects.item(row).data(Qt.ItemDataRole.UserRole) == task:
            shell.projects.setCurrentRow(row)
            shell.open_button.click()
            return
    raise AssertionError("Project not in home list")


def test_home_is_default_and_open_reuses_saved_project_without_api(window, project, monkeypatch):
    store, task, *_ = project
    monkeypatch.setattr("teachdesk.model.generate", lambda *a: pytest.fail("Opening a project must not call AI"))
    assert window.shell.pages.currentWidget() == window.shell.home
    assert window.task_id is None
    open_project(window, task)
    assert window.shell.pages.currentWidget() == window.shell.project
    assert window.task_id == task
    assert window.shell.name.text() == store.task(task)["name"]
    assert not window.shell.learn_button.isEnabled()
    window.shell.home_button.click()
    assert window.shell.pages.currentWidget() == window.shell.home


def test_new_project_button_saves_goal_and_reopens_in_home(window, project, monkeypatch):
    store = project[0]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("My next project", True))
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **kw: ("Use my scratch app; finish on DONE. No other app is allowed.", True))
    window.shell.new_button.click()
    task = window.task_id
    assert store.task(task)["name"] == "My next project"
    assert window.shell.pages.currentWidget() == window.shell.project
    assert window.shell.steps.currentIndex() == 0
    assert window.shell.progress.value() == 0
    assert not window.shell.run_button.isEnabled()
    window.close()
    from teachdesk.ui import MainWindow
    reopened = MainWindow(Store(store.root))
    try:
        assert reopened.shell.pages.currentWidget() == reopened.shell.home
        assert any(reopened.shell.projects.item(i).data(Qt.ItemDataRole.UserRole) == task for i in range(reopened.shell.projects.count()))
        open_project(reopened, task)
        assert "scratch app" in reopened.shell.goal.text()
    finally:
        reopened.close()


def test_progress_comes_from_checks_and_unvalidated_run_stays_disabled(window, project):
    store, task, _, _, vid, _ = project
    open_project(window, task)
    checks = readiness(store, store.version(vid))
    assert window.shell.progress.value() == round(100*sum(x["passed"] for x in checks)/len(checks))
    assert window.shell.progress.value() < 100
    assert not window.shell.run_button.isEnabled()
    assert "confidence" not in window.shell.progress.format().lower()
    assert window.shell.checklist.isHidden()


def test_simple_review_saves_answers_through_existing_version_store(window, project):
    store, task, _, _, vid, workflow = project
    workflow["questions"] = [{"id": "finish", "text": "What tells you it is done?", "blocking": True, "reference": "demonstration at 1s"}]
    store.execute("UPDATE versions SET workflow=?,reviewed=0 WHERE id=?", (json.dumps(workflow), vid))
    open_project(window, task)
    window.shell.basic_answers["finish"].setText("The result marker appears")
    window.shell.reviewed.setChecked(True)
    window.shell.save_button.click()
    saved = store.version(vid)
    assert saved["answers"]["finish"] == "The result marker appears"
    assert saved["reviewed"] == 1
    assert not readiness(store, saved)[1]["passed"], "An answer alone must not rewrite the graph"
    assert not window.shell.practice_button.isEnabled()
    assert "Update Plan" in window.shell.learn_button.text()


def test_recording_previews_use_included_first_and_last_frames(window, project):
    from PIL import Image
    store, task, *_ = project
    demo = store.create_demo(task, {"capture_validation": 3, "ignored_ranges": [[0, .2, "irrelevant"]]})
    for t, color in [(0, "red"), (.5, "green"), (1, "blue")]:
        store.frame(demo, t, Image.new("RGB", (80, 60), color), {})
    store.execute("UPDATE demos SET status='complete' WHERE id=?", (demo,))
    open_project(window, task)
    window.demos.setCurrentIndex(window.demos.findData(demo))
    assert [frame["t"] for frame in window.shell.frames] == [.5, 1]
    window.shell.show_preview(False)
    assert window.shell.preview.pixmap().toImage().pixelColor(0, 0).name() == "#008000"
    window.shell.show_preview(True)
    assert window.shell.preview.pixmap().toImage().pixelColor(0, 0).name() == "#0000ff"
    window.shell.show_preview(False)
    store.execute("UPDATE demos SET metadata=? WHERE id=?", (json.dumps({"capture_validation": 3, "ignored_ranges": [[0, .8, "exclude more"]]}), demo))
    window.show_demo()
    assert window.shell.preview.pixmap().toImage().pixelColor(0, 0).name() == "#0000ff", "Exclusion edits must also replace the visible preview"


def test_archived_projects_are_hidden_until_requested_and_can_be_restored(window, project):
    store, task, *_ = project
    store.execute("UPDATE tasks SET archived=1 WHERE id=?", (task,))
    window.refresh_library()
    assert window.shell.projects.count() == 0
    window.shell.set_archived(True)
    open_project(window, task)
    assert window.shell.restore_button.isVisible()
    assert not window.shell.run_button.isEnabled()
    window.shell.restore_button.click()
    assert store.task(task)["archived"] == 0
    assert window.shell.restore_button.isHidden()


def test_teaching_buttons_assign_training_vs_heldout_roles(window, project, monkeypatch):
    open_project(window, project[1])
    roles = []
    monkeypatch.setattr(window, "start_recording", lambda: roles.append(window.role.currentIndex()))
    window.shell.teach(0)
    window.shell.teach(1)
    assert roles == [0, 1]
    assert not window.worker_busy


def test_stop_remains_available_and_cancels_start_countdown(window, project, monkeypatch):
    open_project(window, project[1])
    scheduled, actions = [], []
    monkeypatch.setattr("teachdesk.ui.QTimer.singleShot", lambda ms, fn: scheduled.append(fn))
    window.arm(lambda: actions.append("must not run"))
    window.poll()
    assert window.shell.stop_button.isEnabled()
    assert not window.shell.home_button.isEnabled()
    window.shell.stop_button.click()
    for fn in scheduled:
        fn()
    assert not window.armed and not actions
    window.poll()
    assert not window.shell.stop_button.isEnabled()


def test_emergency_during_run_countdown_restores_navigation(window, project):
    from teachdesk.execution import Control
    open_project(window, project[1])
    control = window.control = Control()
    window.armed = True
    window.emergency_stop()
    assert control.cancelled.is_set() and not window.armed
    window.poll()
    assert window.control is None
    assert window.shell.home_button.isEnabled()


def test_starting_again_does_not_revive_a_cancelled_countdown(window, project, monkeypatch):
    open_project(window, project[1])
    scheduled, actions = [], []
    monkeypatch.setattr("teachdesk.ui.QTimer.singleShot", lambda ms, fn: scheduled.append(fn))
    window.arm(lambda: actions.append("cancelled start"))
    window.stop()
    window.arm(lambda: actions.append("new start"))
    scheduled[0]()
    assert not actions and window.armed
    scheduled[1]()
    assert actions == ["new start"] and not window.armed


def test_simple_practice_keeps_authorization_and_selects_only_eligible_example(window, project, monkeypatch):
    from conftest import FakeDesktop, SCOPE
    store, task, _, held, _, _ = project
    open_project(window, task)
    old = store.create_demo(task, {"capture_validation": 2}, "practice")
    store.execute("UPDATE demos SET status='complete' WHERE id=?", (old,))
    window.desktop = FakeDesktop()
    monkeypatch.setattr(window, "require_windows", lambda: SCOPE)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **kw: pytest.fail("Only one compatible practice example; no redundant picker needed"))
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a, **kw: pytest.fail("Simple mode uses its documented default limit"))
    confirmations, queued = [], []
    def allow(title, text):
        from PySide6.QtWidgets import QMessageBox
        confirmations.append(text)
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(window, "confirm", allow)
    monkeypatch.setattr(window, "arm", lambda fn: queued.append(fn))
    window.run(True)
    assert queued and window.control
    assert len(confirmations) == 1 and "Allow these visible actions" in confirmations[0]
    # Inspect the queued runner without executing input on a user's desktop.
    runner = next(cell.cell_contents for cell in queued[0].__closure__ if hasattr(cell.cell_contents, "practice_demo"))
    assert runner.practice_demo == held
    assert 119 < runner.input.deadline-time.monotonic() <= 120


def test_details_are_optional_and_small_window_does_not_force_old_layout_size(window, project):
    open_project(window, project[1])
    window.resize(800, 640)
    QApplication.processEvents()
    assert window.width() == 800 and window.height() == 640
    assert not window.tabs.isVisible()
    window.shell.show_details(1)
    QApplication.processEvents()
    assert window.shell.pages.currentWidget() == window.shell.details
    assert window.tabs.currentIndex() == 1
    window.shell.project_button.click()
    assert window.shell.pages.currentWidget() == window.shell.project


def test_model_failure_banner_is_current_before_error_dialog(window, project, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    open_project(window, project[1])
    states = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: states.append(window.state.text()))
    window.worker_busy = True
    window.state.setText("Stopped · model review in progress")
    window.messages.put(("model", None, "Rejected plan fixture"))
    window.poll()
    assert states and "review failed" in states[0] and "in progress" not in states[0]
    assert not window.worker_busy


def test_saved_reply_button_uses_only_local_recovery(window, project, monkeypatch):
    from teachdesk import model
    store, task, _, _, vid, _ = project
    store.execute("INSERT INTO model_replies VALUES(?,?,?,?,?,?,?)", ("fixture-reply", task, "{}", json.dumps({"model": "fixture"}), "rejected", "Format fixture", time.time()))
    open_project(window, task)
    window.shell.steps.setCurrentIndex(1)
    QApplication.processEvents()
    assert window.shell.recover_button.isVisible()
    called = []
    monkeypatch.setattr(model, "generate", lambda *a: pytest.fail("Saved reply button must not request paid generation"))
    monkeypatch.setattr(model, "recover", lambda s, t: called.append(t) or vid)
    monkeypatch.setattr(window, "background", lambda fn, message: fn())
    window.shell.recover_button.click()
    assert called == [task]


def test_plan_summary_keeps_actual_branch_destinations_and_inferences(project):
    workflow = project[-1]
    workflow["nodes"][0]["basis"] = "inferred"
    text = readable_plan(workflow)
    assert "inferred — check this rule" in text
    assert "check Fixture result" in text
    assert "Finished when: Fixture result" in text
    workflow["nodes"][0].update(kind="branch", otherwise="click")
    text = readable_plan(workflow)
    assert "go to step 2; otherwise step 1" in text
