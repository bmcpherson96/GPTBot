"""Beginner project navigation over the existing recording/workflow controller.

This layer changes presentation only. It never awards readiness, calls a model
automatically, or substitutes a recording for a verified practice result.
"""
from __future__ import annotations

from datetime import datetime
import json

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QScrollArea, QListWidget, QListWidgetItem, QTabWidget,
    QProgressBar, QPlainTextEdit, QFormLayout, QLineEdit, QCheckBox, QMenu)

from . import model
from .windows import CAPTURE_VALIDATION_VERSION
from .workflow import readiness


def recording_name(demo):
    when = datetime.fromtimestamp(demo["created"]).strftime("%b %d, %I:%M:%S %p")
    purpose = "Teaching" if demo["role"] == "train" else "Practice example"
    status = {"complete": "Saved", "interrupted": "Interrupted", "recording": "Recording"}.get(demo["status"], demo["status"])
    if json.loads(demo["metadata"]).get("capture_validation") != CAPTURE_VALIDATION_VERSION:
        status = "Older capture — reference only"
    return f"{when} · {purpose} · {status}"


def readable_plan(workflow):
    """Render the actual graph, including branches/loops and inferred rules."""
    targets = workflow["targets"]
    describe = lambda key: targets.get(key, {}).get("description", key)
    numbers = {node["id"]: index+1 for index, node in enumerate(workflow["nodes"])}
    lines = ["Goal: "+workflow["goal"], "Allowed scope: "+workflow["scope"],
             "Start when: "+describe(workflow["start"]),
             "Finished when: "+describe(workflow["completion"])]
    if workflow["inputs"]:
        lines.append("Inputs: "+"; ".join(f"{name}: {detail}" for name, detail in workflow["inputs"].items()))
    lines += ["", f"Begin at step {numbers[workflow['entry']]}. Each action checks its visible result."]
    for node in workflow["nodes"]:
        kind, target = node["kind"], describe(node.get("target", ""))
        if kind == "branch":
            action = f"If {target} is visible, go to step {numbers[node['next']]}; otherwise step {numbers[node['otherwise']]}"
        elif kind == "finish":
            action = "Check completion and finish"
        elif kind == "stop":
            action = "Stop: "+node["reason"]
        else:
            action = {"click": "Click "+target, "drag": "Drag "+target+" to "+describe(node.get("to", "")),
                      "type": "Enter "+repr(node.get("text", ""))+" in "+target,
                      "key": "Press "+" + ".join(node.get("keys", []))+" at "+target,
                      "scroll": f"Scroll {node.get('dy', 0)} notches at "+target,
                      "wait": "Wait for "+target}.get(kind, kind)
            if "verify" in node:
                action += "; check "+describe(node["verify"])
            action += f"; then step {numbers[node['next']]}"
        basis = "shown in a demonstration" if node["basis"] == "demonstrated" else "inferred — check this rule"
        boundary = "; separate authorization required" if node["consequential"] else ""
        lines.append(f"{numbers[node['id']]}. {action} ({basis}{boundary}).")
    if workflow["assumptions"]:
        lines += ["", "Assumptions: "+"; ".join(workflow["assumptions"])]
    lines += ["", "Exceptions and recovery: "+workflow["exceptions"]]
    return "\n".join(lines)


class ProjectShell(QWidget):
    def __init__(self, controller, detailed_workspace):
        super().__init__()
        self.c = controller
        self.basic_answers = {}
        self._review_key = None
        self._frame_demo = None
        self.frames = []
        self._preview_end = False
        self.show_archived = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        nav = QHBoxLayout()
        self.home_button = self.c.button(nav, "Projects", self.go_home)
        self.project_button = self.c.button(nav, "Back to project", self.open_current)
        self.project_button.hide()
        self.c.state.setStyleSheet("font-size:14px;font-weight:bold;padding:10px;background:#243d55;color:white")
        self.c.state.setWordWrap(True)
        nav.addWidget(self.c.state, 1)
        self.pause_button = self.c.button(nav, "Pause", self.c.pause)
        self.resume_button = self.c.button(nav, "Resume", self.c.resume)
        self.stop_button = self.c.button(nav, "Stop", self.c.stop)
        self.stop_button.setStyleSheet("font-weight:bold;padding:8px 16px")
        settings = QPushButton("Settings")
        menu = QMenu(settings)
        self.project_actions = []
        for text, fn in (("AI connection…", self.configure_ai), ("Project details…", self.show_details),
                         ("Edit project…", self.c.edit_task), ("Archive / restore project", self.c.archive)):
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, action=fn: self.c.safe(action))
            if text != "AI connection…":
                self.project_actions.append(action)
        archived = menu.addAction("Show archived projects")
        archived.setCheckable(True)
        archived.toggled.connect(self.set_archived)
        settings.setMenu(menu)
        nav.addWidget(settings)
        layout.addLayout(nav)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self._build_home()
        self._build_project()
        self.details = self.scroll(detailed_workspace)
        self.pages.addWidget(self.details)
        self.pages.currentChanged.connect(self._navigation)
        self.pages.setCurrentWidget(self.home)
        self.refresh_home()
        self.sync_activity()
        self._navigation()

    @staticmethod
    def scroll(widget):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        return area

    @staticmethod
    def label(text="", heading=False):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        if heading:
            label.setStyleSheet("font-size:24px;font-weight:bold")
        return label

    def _build_home(self):
        self.home = QWidget()
        box = QVBoxLayout(self.home)
        box.addWidget(self.label("Your projects", True))
        box.addWidget(self.label("Start something new, or pick up where you left off."))
        self.new_button = self.c.button(box, "+ New Project", self.c.create_task)
        self.new_button.setMinimumHeight(48)
        self.primary(self.new_button)
        self.projects = QListWidget()
        self.projects.setWordWrap(True)
        self.projects.itemDoubleClicked.connect(lambda item: self.c.safe(self.open_selected))
        self.projects.itemSelectionChanged.connect(lambda: self.open_button.setEnabled(self.projects.currentItem() is not None))
        box.addWidget(self.projects, 1)
        self.empty = self.label("No projects yet. Choose New Project to begin.")
        box.addWidget(self.empty)
        self.open_button = self.c.button(box, "Open Project", self.open_selected)
        self.open_button.setMinimumHeight(42)
        self.primary(self.open_button)
        self.open_button.setEnabled(False)
        box.addWidget(self.label("Recordings stay on this computer. AI review sends selected evidence only when you approve it."))
        self.pages.addWidget(self.home)

    def _build_project(self):
        self.project = QWidget()
        box = QVBoxLayout(self.project)
        row = QHBoxLayout()
        self.name = self.label("Project", True)
        row.addWidget(self.name, 1)
        self.restore_button = self.c.button(row, "Restore Project", self.c.archive)
        box.addLayout(row)
        self.goal = self.label()
        box.addWidget(self.goal)
        row = QHBoxLayout()
        row.addWidget(self.label("Application"))
        row.addWidget(self.c.windows, 1)
        self.c.button(row, "Refresh", self.c.refresh_windows)
        box.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setFormat("Learning progress: %p% of checks passed")
        box.addWidget(self.progress)
        self.next_step = self.label()
        self.next_step.setStyleSheet("padding:8px;background:#243d55;color:white")
        box.addWidget(self.next_step)
        self.steps = QTabWidget()
        box.addWidget(self.steps, 1)

        teach = QWidget()
        t = QVBoxLayout(teach)
        t.addWidget(self.label("Show TeachDesk how you do this project."))
        # Reuse the controller's privacy switch and exact scope selector.
        self.c.keys.setText("Include text I type (only for non-sensitive text)")
        t.addWidget(self.c.keys)
        t.addWidget(self.label("Click Start Teaching, switch to your app, and wait for Recording. Demonstrate the whole task. Return here and click Stop."))
        self.teach_button = self.c.button(t, "Start Teaching", lambda: self.teach(0))
        self.teach_button.setMinimumHeight(48)
        self.primary(self.teach_button)
        self.c.button(t, "Try the Practice App", self.c.open_lab)
        t.addStretch()
        self.platform = self.label()
        t.addWidget(self.platform)
        self.steps.addTab(self.scroll(teach), "1 · Teach")

        review = QWidget()
        r = QVBoxLayout(review)
        self.recording_status = self.label("No recording yet. Start with Teach.")
        r.addWidget(self.recording_status)
        r.addWidget(self.c.demos)
        row = QHBoxLayout()
        self.begin_button = self.c.button(row, "Beginning", lambda: self.show_preview(False))
        self.end_button = self.c.button(row, "End", lambda: self.show_preview(True))
        self.recording_details_button = self.c.button(row, "Recording details…", lambda: self.show_details(1))
        r.addLayout(row)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(150)
        r.addWidget(self.preview)
        self.ai_status = self.label()
        r.addWidget(self.ai_status)
        self.connect_button = self.c.button(r, "Connect AI in Settings", self.configure_ai)
        self.learn_button = self.c.button(r, "Learn from Recording", self.c.generate)
        self.primary(self.learn_button)
        self.plan = QPlainTextEdit()
        self.plan.setReadOnly(True)
        self.plan.setMinimumHeight(180)
        r.addWidget(self.plan)
        self.questions = QFormLayout()
        r.addLayout(self.questions)
        self.reviewed = QCheckBox("I checked the plan, finishing rule, assumptions and allowed actions")
        r.addWidget(self.reviewed)
        self.save_button = self.c.button(r, "Save Review", self.save_review)
        r.addStretch()
        self.steps.addTab(self.scroll(review), "2 · Review")

        practice = QWidget()
        p = QVBoxLayout(practice)
        p.addWidget(self.label("Practice checks the plan before a normal run. Use a separate example with controls in different positions when possible."))
        self.practice_example = self.c.button(p, "1. Teach a Practice Example", lambda: self.teach(1))
        self.practice_button = self.c.button(p, "2. Test Project", lambda: self.c.run(True))
        self.run_button = self.c.button(p, "Run Project", self.run_ready)
        self.run_button.setMinimumHeight(48)
        self.primary(self.run_button)
        self.promote_button = self.c.button(p, "Use This Validated Update", self.c.promote)
        p.addWidget(self.label("100% means the checks passed for the supported scope. It is not a guarantee of success. Progress is earned from review and practice."))
        self.checklist = self.label()
        self.c.button(p, "Why this percentage?", lambda: self.checklist.setVisible(not self.checklist.isVisible()))
        self.checklist.hide()
        p.addWidget(self.checklist)
        self.performance = self.label()
        p.addWidget(self.performance)
        self.c.button(p, "History and versions…", lambda: self.show_details(3))
        p.addStretch()
        self.steps.addTab(self.scroll(practice), "3 · Practice / Run")
        self.pages.addWidget(self.project)

    @staticmethod
    def primary(button):
        button.setStyleSheet("QPushButton {background:#243d55;color:white;font-weight:bold;padding:10px;border-radius:4px;} QPushButton:disabled {background:#d9dde1;color:#666;}")

    def _navigation(self):
        self.project_button.setVisible(self.pages.currentWidget() == self.details and bool(self.c.task_id))
        self.home_button.setVisible(self.pages.currentWidget() != self.home)
        self.sync_activity()

    def go_home(self):
        self.c.idle()
        self.refresh_home()
        self.pages.setCurrentWidget(self.home)

    def open_selected(self):
        self.c.idle()
        item = self.projects.currentItem()
        if item is None:
            return
        self.c.task_id = item.data(Qt.ItemDataRole.UserRole)
        self.c.refresh_library()
        self.open_current()

    def open_current(self):
        self.c.selected_task()
        self.refresh_project()
        self.pages.setCurrentWidget(self.project)

    def show_details(self, tab=None):
        self.c.selected_task()
        if tab is not None:
            self.c.tabs.setCurrentIndex(tab)
        self.pages.setCurrentWidget(self.details)

    def set_archived(self, enabled):
        self.show_archived = enabled
        self.refresh_home()

    def configure_ai(self):
        self.c.configure_model()
        self.refresh_project()

    def teach(self, role):
        self.c.idle()
        self.c.role.setCurrentIndex(role)
        self.c.start_recording()

    def save_review(self):
        self.c.idle()
        for key, edit in self.basic_answers.items():
            self.c.answer_widgets[key].setText(edit.text())
        self.c.reviewed.setChecked(self.reviewed.isChecked())
        self.c.save_review()

    def run_ready(self):
        task = self.c.selected_task()
        if not task["active_version"]:
            raise ValueError("Review and test this project before running it")
        self.c.versions.setCurrentIndex(self.c.versions.findData(task["active_version"]))
        self.c.run(False)

    def refresh_home(self):
        old = self.projects.currentItem()
        selected = old.data(Qt.ItemDataRole.UserRole) if old else self.c.task_id
        self.projects.clear()
        for task in self.c.store.rows("SELECT * FROM tasks ORDER BY created DESC"):
            if task["archived"] and not self.show_archived:
                continue
            versions = self.c.store.rows("SELECT id FROM versions WHERE task=? ORDER BY created DESC", (task["id"],))
            vid = task["active_version"] or (versions[0]["id"] if versions else None)
            checks = readiness(self.c.store, self.c.store.version(vid)) if vid else []
            percent = round(100*sum(x["passed"] for x in checks)/len(checks)) if checks else 0
            status = "Archived" if task["archived"] else "Ready to Run" if task["active_version"] and percent == 100 else "Learning"
            item = QListWidgetItem(f"{task['name']}\n{status} · {percent}% of checks passed")
            item.setData(Qt.ItemDataRole.UserRole, task["id"])
            item.setSizeHint(QSize(200, 70))
            self.projects.addItem(item)
            if task["id"] == selected:
                self.projects.setCurrentItem(item)
        self.empty.setVisible(self.projects.count() == 0)
        self.open_button.setEnabled(self.projects.currentItem() is not None)

    def refresh_recording(self):
        ident = self.c.demos.currentData()
        rows = self.c.store.rows("SELECT * FROM demos WHERE id=?", (ident,)) if ident else []
        demo = rows[0] if rows else None
        metadata = json.loads(demo["metadata"]) if demo else {}
        frames = self.c.store.rows("SELECT * FROM frames WHERE demo=? ORDER BY t", (ident,)) if ident else []
        self.frames = [frame for frame in frames if not any(a <= frame["t"] <= b for a, b, _ in metadata.get("ignored_ranges", []))]
        if ident != self._frame_demo:
            self._preview_end = False
        self._frame_demo = ident
        self.show_preview(self._preview_end)
        self.begin_button.setEnabled(bool(self.frames))
        self.end_button.setEnabled(bool(self.frames))
        self.begin_button.setVisible(bool(self.frames))
        self.end_button.setVisible(bool(self.frames))
        self.preview.setVisible(bool(self.frames))
        self.c.demos.setVisible(bool(demo))
        self.recording_details_button.setVisible(bool(demo))
        if not demo:
            message = "No recording yet. Start with Teach."
        elif metadata.get("capture_validation") != CAPTURE_VALIDATION_VERSION:
            message = "Older recording: retained for reference, but it needs replacement before AI learning."
        elif demo and demo["status"] != "complete":
            message = "This recording is incomplete. You can inspect it, but it cannot qualify for learning or practice."
        else:
            message = "Check the beginning and end. A saved recording has not yet passed practice." if self.frames else "No included frames in this recording. Teach a fresh example."
        self.recording_status.setText(message)

    def show_preview(self, end):
        self._preview_end = end
        self.preview.clear()
        if not self.frames:
            return
        frame = self.frames[-1 if end else 0]
        image = QPixmap(str(self.c.store.root/frame["path"]))
        if image.isNull():
            self.preview.setText("The local image file is unavailable. Check Recording details.")
            return
        self.preview.setPixmap(image.scaled(650, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.preview.setToolTip(f"{'End' if end else 'Beginning'} · {frame['t']:.2f} seconds")

    def refresh_project(self):
        if not self.c.task_id:
            self.pages.setCurrentWidget(self.home)
            return
        task = self.c.selected_task()
        self.name.setText(task["name"])
        self.goal.setText(task["description"])
        self.restore_button.setVisible(bool(task["archived"]))
        issue = self.c.desktop_error if not self.c.desktop else self.c.hotkey.error
        self.platform.setText("Recording unavailable: "+issue+". Saved projects remain available." if issue else "")
        vid = self.c.versions.currentData()
        version = self.c.store.version(vid) if vid else None
        checks = readiness(self.c.store, version) if version else []
        self.progress.setValue(round(100*sum(x["passed"] for x in checks)/len(checks)) if checks else 0)
        self.checklist.setText("\n".join(("✓ " if item["passed"] else "○ ")+item["label"]+(": "+item["detail"] if item.get("detail") else "") for item in checks) or "Teach, review a plan, and pass separate practice checks to build readiness.")
        ai_ready, _ = model.availability(self.c.store)
        self._ai_ready = ai_ready
        self._archived = bool(task["archived"])
        self.ai_status.setText("AI connected. Learning uses this project's saved teaching examples, and sends sampled screenshots/actions after confirmation. Practice examples stay separate. API charges may apply." if ai_ready else "AI is not connected yet. You can teach and review recordings now; connect AI in Settings when ready to learn a plan.")
        self.connect_button.setVisible(not ai_ready)
        recorded = self.c.store.rows("SELECT * FROM demos WHERE task=? AND role='train' AND status='complete'", (task["id"],))
        demos = [d for d in recorded if json.loads(d["metadata"]).get("capture_validation") == CAPTURE_VALIDATION_VERSION]
        usable = 1 <= len(demos) <= 8
        self._has_training = usable
        self._has_version = bool(version)
        self._reviewable = bool(version and not any(q["blocking"] for q in version["workflow"]["questions"]))
        self._can_practice = bool(version and version["reviewed"] and self._reviewable and checks[0]["passed"])
        active = self.c.store.version(task["active_version"]) if task["active_version"] else None
        self._ready = bool(active and all(c["passed"] for c in readiness(self.c.store, active)))
        complete = bool(checks and all(item["passed"] for item in checks))
        self.promote_button.setVisible(bool(complete and vid != task["active_version"]))
        self.learn_button.setText("Update Plan from My Answers" if version and version["workflow"]["questions"] else "Learn Again" if version else "Learn Project")
        key = (vid, version["reviewed"], json.dumps(version["answers"], sort_keys=True)) if version else None
        if key != self._review_key or not version:
            self._review_key = key
            while self.questions.rowCount():
                self.questions.removeRow(0)
            self.basic_answers = {}
            self.plan.setPlainText(readable_plan(version["workflow"]) if version else "No plan yet. Teach a demonstration, check its recording, then use Learn from Recording when AI is connected.")
            if version:
                for question in version["workflow"]["questions"]:
                    label = self.label(question["text"]+(" (needed before practice)" if question["blocking"] else ""))
                    label.setToolTip("Demonstration reference: "+question["reference"])
                    edit = QLineEdit(version["answers"].get(question["id"], ""))
                    self.questions.addRow(label, edit)
                    self.basic_answers[question["id"]] = edit
            self.reviewed.setChecked(bool(version and version["reviewed"]))
        self.reviewed.setVisible(bool(version))
        self.save_button.setVisible(bool(version))
        self.plan.setVisible(bool(version))
        if task["archived"]:
            next_step = "This project is archived. Restore it to teach or run."
        elif self._ready:
            next_step = "The working version is ready. This updated plan still needs its own review and practice." if vid != task["active_version"] else "Ready to run within its checked scope. You can still teach more."
        elif not usable:
            next_step = "Next: keep up to eight teaching examples. Remove irrelevant ones in Details." if len(demos) > 8 else "Next: teach a fresh example. Older recordings stay as local reference." if recorded else "Next: teach a fresh example."
        elif not ai_ready and not version:
            next_step = "Recording saved. Connect AI in Settings when you are ready to learn a plan."
        elif not version:
            next_step = "Next: check your recording in Review, then learn a plan."
        elif not self._can_practice:
            next_step = "Next: review the plan and answer any important questions."
        else:
            next_step = "Next: teach a separate practice example, reset the app, then test the project."
        self.next_step.setText(next_step)
        runs = self.c.store.rows("SELECT outcome FROM runs WHERE task=?", (task["id"],))
        outcomes = [run["outcome"] for run in runs]
        self.performance.setText(f"Run history: {outcomes.count('verified')} verified completions · {outcomes.count('failed')} failures · {outcomes.count('intervened')} interventions · {sum(x != 'running' for x in outcomes)} evaluated runs")
        self.refresh_recording()
        self.sync_activity()

    def sync_activity(self):
        busy = bool(self.c.armed or self.c.worker_busy or self.c.recorder or self.c.runner or self.c.control)
        active = bool(self.c.recorder or self.c.runner)
        self.home_button.setEnabled(not busy)
        self.new_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy and self.projects.currentItem() is not None)
        event = getattr(self.c.recorder, "paused", None) or getattr(self.c.control, "paused", None)
        paused = bool(event and event.is_set())
        self.pause_button.setVisible(active and not paused)
        self.resume_button.setVisible(active and paused)
        self.stop_button.setEnabled(bool(self.c.armed or active or self.c.control))
        for action in self.project_actions:
            action.setEnabled(not busy and bool(self.c.task_id) and self.pages.currentWidget() != self.home)
        if not self.c.task_id:
            return
        archived = getattr(self, "_archived", False)
        allowed = not busy and not archived
        desktop = self.c.desktop is not None and not self.c.hotkey.error and self.c.hotkey.thread.is_alive()
        self.teach_button.setEnabled(allowed and desktop)
        self.practice_example.setEnabled(allowed and desktop and getattr(self, "_can_practice", False))
        self.practice_button.setEnabled(allowed and desktop and getattr(self, "_can_practice", False))
        self.run_button.setEnabled(allowed and desktop and getattr(self, "_ready", False))
        self.learn_button.setEnabled(allowed and getattr(self, "_ai_ready", False) and getattr(self, "_has_training", False))
        self.save_button.setEnabled(allowed)
        self.restore_button.setEnabled(not busy)
        self.promote_button.setEnabled(allowed)
