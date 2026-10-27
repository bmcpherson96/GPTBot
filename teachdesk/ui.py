from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QLockFile
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import model
from .execution import Control, Runner
from .perception import materialize
from .recording import Recorder
from .storage import Store, default_home
from .windows import EmergencyHotkey, WindowsDesktop, enable_dpi_awareness
from .workflow import readiness, validate
from . import __version__
from .windows import CAPTURE_VALIDATION_VERSION


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setWindowTitle(f"TeachDesk {__version__} · Projects")
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1100, screen.width()-40), min(780, screen.height()-40))
        self.setMinimumSize(640, 480)
        font = self.font()
        font.setPointSize(11)
        self.setFont(font)
        self.shell = None
        self.task_id = None
        self.recorder = self.runner = self.control = None
        self.armed = False
        self.arm_generation = 0
        self.worker_busy = False
        self.messages = queue.Queue()
        self.emergency = threading.Event()
        self.desktop_error = ""
        self.closing = False
        try:
            self.desktop = WindowsDesktop()
        except Exception as exc:
            self.desktop = None
            self.desktop_error = str(exc)
        self.hotkey = EmergencyHotkey(self.emergency_stop)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        self.state = QLabel("Stopped · Emergency stop: Ctrl+Alt+F8")
        self.state.setStyleSheet("font-size:18px;font-weight:bold;padding:10px;background:#243d55;color:white")
        header.addWidget(self.state, 1)
        for text, fn in (("New Project", self.create_task), ("AI connection", self.configure_model), ("Practice App", self.open_lab)):
            self.button(header, text, fn)
        layout.addLayout(header)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        split = QSplitter()
        layout.addWidget(split, 1)
        self.library = QTreeWidget()
        self.library.setHeaderLabels(["Projects", "Checks"])
        self.library.itemSelectionChanged.connect(self.choose_task)
        split.addWidget(self.library)
        right = QWidget()
        box = QVBoxLayout(right)
        split.addWidget(right)
        split.setSizes([310, 1000])
        self.title = QLabel("Open or create a project")
        self.title.setStyleSheet("font-size:20px;font-weight:bold")
        box.addWidget(self.title)
        versions = QHBoxLayout()
        versions.addWidget(QLabel("Workflow version"))
        self.versions = QComboBox()
        self.versions.currentIndexChanged.connect(self.show_version)
        versions.addWidget(self.versions, 1)
        self.button(versions, "Promote / Restore Version", self.promote)
        self.button(versions, "Edit Project", self.edit_task)
        self.button(versions, "Archive / Unarchive", self.archive)
        box.addLayout(versions)
        self.progress = QProgressBar()
        self.progress.setFormat("%p% of readiness checks · not a probability of success")
        box.addWidget(self.progress)
        self.checks = QLabel()
        self.checks.setWordWrap(True)
        box.addWidget(self.checks)
        scope = QHBoxLayout()
        scope.addWidget(QLabel("Exact target window"))
        self.windows = QComboBox()
        scope.addWidget(self.windows, 1)
        self.button(scope, "Refresh Windows", self.refresh_windows)
        box.addLayout(scope)
        controls = QHBoxLayout()
        for text, fn in (("Start Recording / Teach More", self.start_recording), ("Pause", self.pause), ("Resume after correction", self.resume), ("Stop", self.stop), ("Review", lambda: self.tabs.setCurrentIndex(0)), ("Supervised Practice", lambda: self.run(True)), ("Run", lambda: self.run(False))):
            self.button(controls, text, fn)
        box.addLayout(controls)
        options = QHBoxLayout()
        self.role = QComboBox()
        self.role.addItems(["Training demonstration", "Held-out completion example", "Held-out expected-stop example"])
        options.addWidget(self.role)
        self.keys = QCheckBox("Record ordinary typed keys (may include secrets)")
        options.addWidget(self.keys)
        self.manual_pause = QCheckBox("Pause on physical input")
        self.manual_pause.setChecked(True)
        options.addWidget(self.manual_pause)
        self.button(options, "Add explanation", self.note)
        box.addLayout(options)
        masks = QHBoxLayout()
        masks.addWidget(QLabel("Exclude regions [normalized x0,y0,x1,y1]"))
        self.masks = QLineEdit("[]")
        self.masks.setToolTip("JSON list, e.g. [[0.7,0,1,0.2]]. Masked recordings disable ordinary key capture for the whole session.")
        masks.addWidget(self.masks)
        box.addLayout(masks)
        self.tabs = QTabWidget()
        box.addWidget(self.tabs, 1)
        review = QWidget()
        r = QVBoxLayout(review)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        r.addWidget(self.summary, 1)
        self.question_form = QFormLayout()
        r.addLayout(self.question_form)
        self.answer_widgets = {}
        self.reviewed = QCheckBox("I reviewed the goal, inputs, supported branches, assumptions, completion and consequential steps")
        r.addWidget(self.reviewed)
        row = QHBoxLayout()
        self.button(row, "Generate / Regenerate with model", self.generate)
        self.button(row, "Save answers and review", self.save_review)
        r.addLayout(row)
        self.tabs.addTab(review, "Review & questions")
        timeline = QWidget()
        t = QVBoxLayout(timeline)
        self.demos = QComboBox()
        self.demos.currentIndexChanged.connect(self.show_demo)
        t.addWidget(self.demos)
        self.timeline = QTableWidget(0, 4)
        self.timeline.setHorizontalHeaderLabels(["Seconds", "Kind", "Evidence (local)", "Included"])
        self.timeline.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.timeline.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.timeline.itemSelectionChanged.connect(self.show_frame)
        t.addWidget(self.timeline, 1)
        self.frame_label = QLabel("Select an event/frame to see synchronized visual evidence")
        self.frame_label.setMinimumHeight(180)
        self.frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.addWidget(self.frame_label)
        row = QHBoxLayout()
        self.button(row, "Label mistake / irrelevant interval", self.exclude)
        self.button(row, "Delete demonstration & derived workflows", self.delete_demo)
        t.addLayout(row)
        self.tabs.addTab(timeline, "Demonstrations & timeline")
        editor = QWidget()
        e = QVBoxLayout(editor)
        e.addWidget(QLabel("Structured workflow editor. Changes save as a candidate; validation and practice are required again."))
        self.editor = QPlainTextEdit()
        e.addWidget(self.editor)
        self.button(e, "Validate and save new candidate", self.save_candidate)
        self.tabs.addTab(editor, "Workflow graph / edit")
        history = QWidget()
        h = QVBoxLayout(history)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        h.addWidget(self.history)
        self.button(h, "Delete project's run history & images", self.delete_history)
        self.button(h, "Delete entire project and its local evidence", self.delete_task)
        self.tabs.addTab(history, "Runs & evidence")
        replies = QWidget()
        reply_box = QVBoxLayout(replies)
        self.reply_history = QPlainTextEdit()
        self.reply_history.setReadOnly(True)
        reply_box.addWidget(self.reply_history)
        self.button(reply_box, "Check latest saved reply (no API request)", self.recover_model_reply)
        self.button(reply_box, "Delete saved AI replies", self.delete_model_replies)
        self.tabs.addTab(replies, "AI replies")
        self.overlay = QLabel("Stopped")
        self.overlay.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet("background:#243d55;color:white;padding:8px;font-size:14px;border:2px solid #71c7e8")
        self.overlay.move(10, 5)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        from .project_ui import ProjectShell
        workspace = self.takeCentralWidget()
        self.shell = ProjectShell(self, workspace)
        self.setCentralWidget(self.shell)
        self.refresh_windows()
        self.refresh_library()
        self.refresh_notice()
        for label in self.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setPlainText("Create a task, then record an explicitly enabled teaching session.\n\nScreen evidence and task memory are local. Model learning is unavailable until configured.\nNo recording or desktop input is active.")

    def button(self, layout, text, fn):
        button = QPushButton(text)
        button.clicked.connect(lambda checked=False: self.safe(fn))
        layout.addWidget(button)
        return button

    def safe(self, fn):
        try:
            fn()
        except Exception as exc:
            QMessageBox.warning(self, "TeachDesk", str(exc))

    def confirm(self, title, text):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(text)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        return QMessageBox.StandardButton(dialog.exec())

    def idle(self):
        if self.armed or self.worker_busy or self.runner or self.recorder:
            raise ValueError("Stop the active session or wait for model review to finish first")

    def selected_task(self):
        if not self.task_id:
            raise ValueError("Open or create a project first")
        return self.store.task(self.task_id)

    def selected_version(self):
        ident = self.versions.currentData()
        if not ident:
            raise ValueError("Generate a workflow candidate first")
        return self.store.version(ident)

    def refresh_notice(self):
        _, info = model.availability(self.store)
        platform = self.desktop_error or self.hotkey.error or "Windows input available; single monitor, unlocked standard desktop required"
        self.notice.setText(platform+". "+info+". Captures stay local unless you explicitly configure and invoke model review.")

    def refresh_windows(self):
        old = self.windows.currentData()
        self.windows.clear()
        self.windows.addItem("Choose an application…", None)
        if self.desktop:
            for win in self.desktop.windows():
                self.windows.addItem(win.title, win)
                self.windows.setItemData(self.windows.count()-1, f"{win.executable} · PID {win.pid}", Qt.ItemDataRole.ToolTipRole)
            for i in range(self.windows.count()):
                if self.windows.itemData(i) == old:
                    self.windows.setCurrentIndex(i)

    def refresh_library(self):
        selected = self.task_id
        self.library.blockSignals(True)
        self.library.clear()
        groups = {name: QTreeWidgetItem(self.library, [name]) for name in ("Learning", "Ready to Run", "Archived")}
        for task in self.store.rows("SELECT * FROM tasks ORDER BY created"):
            version_rows = self.store.rows("SELECT id FROM versions WHERE task=? ORDER BY created DESC", (task["id"],))
            active = task["active_version"]
            vid = active or (version_rows[0]["id"] if version_rows else None)
            checks = readiness(self.store, self.store.version(vid)) if vid else []
            percent = round(100*sum(c["passed"] for c in checks)/len(checks)) if checks else 0
            group = "Archived" if task["archived"] else "Ready to Run" if active and percent == 100 else "Learning"
            item = QTreeWidgetItem(groups[group], [task["name"], f"{percent}%"])
            item.setData(0, Qt.ItemDataRole.UserRole, task["id"])
            if task["id"] == selected:
                self.library.setCurrentItem(item)
        self.library.expandAll()
        self.library.blockSignals(False)
        self.load_task()
        if self.shell:
            self.shell.refresh_home()

    def choose_task(self):
        item = self.library.currentItem()
        if item and item.data(0, Qt.ItemDataRole.UserRole):
            self.task_id = item.data(0, Qt.ItemDataRole.UserRole)
            self.load_task()

    def load_task(self):
        if not self.task_id:
            if self.shell:
                self.shell.refresh_project()
            return
        task = self.selected_task()
        self.title.setText(task["name"])
        old = self.versions.currentData()
        self.versions.blockSignals(True)
        self.versions.clear()
        for v in self.store.rows("SELECT * FROM versions WHERE task=? ORDER BY created DESC", (self.task_id,)):
            self.versions.addItem(v["id"][:8]+(" · active" if v["id"] == task["active_version"] else " · candidate / prior"), v["id"])
        idx = self.versions.findData(old)
        self.versions.setCurrentIndex(max(0, idx))
        self.versions.blockSignals(False)
        self.demos.blockSignals(True)
        old_demo = self.demos.currentData()
        self.demos.clear()
        for d in self.store.rows("SELECT * FROM demos WHERE task=? ORDER BY created DESC", (self.task_id,)):
            from .project_ui import recording_name
            self.demos.addItem(recording_name(d), d["id"])
        idx = self.demos.findData(old_demo)
        self.demos.setCurrentIndex(max(0, idx))
        self.demos.blockSignals(False)
        self.show_demo()
        self.show_version()
        self.show_history()
        if self.shell:
            self.shell.refresh_project()

    def show_version(self):
        while self.question_form.rowCount():
            self.question_form.removeRow(0)
        self.answer_widgets = {}
        if not self.versions.currentData():
            local = ""
            if self.task_id:
                latest = self.store.rows("SELECT id FROM demos WHERE task=? ORDER BY created DESC LIMIT 1", (self.task_id,))
                if latest:
                    ident = latest[0]["id"]
                    events = self.store.rows("SELECT kind,count(*) AS n FROM events WHERE demo=? GROUP BY kind", (ident,))
                    frames = self.store.rows("SELECT count(*) AS n,max(t) AS duration FROM frames WHERE demo=?", (ident,))[0]
                    local = f"Latest local demonstration: {frames['n']} frames, {frames['duration'] or 0:.1f}s.\nObserved events: "+", ".join(f"{e['n']} {e['kind']}" for e in events)+".\nThese are captured facts; intent and rules have not been inferred.\n\n"
            self.summary.setPlainText(local+"Review the timeline, then configure a vision model and click Generate.\nNo learned workflow exists yet.")
            self.editor.clear()
            self.checks.setText("Blocked: no workflow candidate")
            self.progress.setValue(0)
            self.reviewed.setChecked(False)
            if self.shell:
                self.shell.refresh_project()
            return
        v = self.selected_version()
        w = v["workflow"]
        checks = readiness(self.store, v)
        self.progress.setValue(round(100*sum(c["passed"] for c in checks)/len(checks)))
        self.checks.setText("\n".join(("✓ " if c["passed"] else "□ ")+c["label"]+(": "+c["detail"] if c.get("detail") else "") for c in checks))
        nodes = "\n".join(f"• {n['id']}: {n['kind']} ({n['basis']})"+(" — AUTHORIZATION REQUIRED" if n["consequential"] else "") for n in w["nodes"])
        self.summary.setPlainText(f"Goal: {w['goal']}\nSupported scope: {w['scope']}\nInputs: {json.dumps(w['inputs'])}\nStart: {w['start']}\nCompletion: {w['completion']}\n\n{nodes}\n\nAssumptions: "+"; ".join(w["assumptions"])+"\nExceptions and recovery: "+w["exceptions"])
        self.editor.setPlainText(json.dumps(w, indent=2))
        for q in w["questions"]:
            answer = QLineEdit(v["answers"].get(q["id"], ""))
            label = QLabel(("BLOCKING: " if q["blocking"] else "")+q["text"]+"\nEvidence: "+q["reference"])
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            self.question_form.addRow(label, answer)
            self.answer_widgets[q["id"]] = answer
        self.reviewed.setChecked(bool(v["reviewed"]))
        if self.shell:
            self.shell.refresh_project()

    def create_task(self):
        self.idle()
        name, ok = QInputDialog.getText(self, "New Project", "What would you like to call this project?")
        if not ok:
            return
        goal, ok = QInputDialog.getMultiLineText(self, "New Project", "What should it do, in which app, and how will you know it is finished? Include anything it must not do.")
        if ok:
            self.task_id = self.store.create_task(name, goal)
            self.refresh_library()
            if self.shell:
                self.shell.open_current()
                self.shell.steps.setCurrentIndex(0)

    def edit_task(self):
        self.idle()
        task = self.selected_task()
        name, ok = QInputDialog.getText(self, "Edit Project", "Project name", text=task["name"])
        if not ok or not name.strip():
            return
        desc, ok = QInputDialog.getMultiLineText(self, "Edit Project", "What should it do, when is it finished, and what must it not do?", task["description"])
        if ok:
            self.store.execute("UPDATE tasks SET name=?,description=? WHERE id=?", (name, desc, self.task_id))
            # Changed intent invalidates prior review; never silently retain authorization/readiness.
            if desc != task["description"]:
                self.store.invalidate(self.task_id, "Task intent changed; repeat review and practice")
            self.refresh_library()

    def archive(self):
        self.idle()
        task = self.selected_task()
        self.store.execute("UPDATE tasks SET archived=? WHERE id=?", (not task["archived"], self.task_id))
        self.refresh_library()

    def require_windows(self):
        if not self.desktop or self.hotkey.error or not self.hotkey.thread.is_alive():
            raise ValueError(self.desktop_error or self.hotkey.error or "Emergency hotkey observer is not running")
        scope = self.windows.currentData()
        if not scope:
            raise ValueError("Open an application and select its exact window")
        if self.selected_task()["archived"]:
            raise ValueError("Unarchive this task first")
        return scope

    def arm(self, callback):
        self.arm_generation += 1
        generation = self.arm_generation
        self.armed = True
        self.state.setText("Paused · starting in 5 seconds; focus selected target · Ctrl+Alt+F8 stops")
        self.overlay.setText("Starting in 5 seconds · focus target · Ctrl+Alt+F8 STOP")
        self.overlay.adjustSize()
        self.overlay.show()
        self.showMinimized()
        def begin():
            if not self.armed or generation != self.arm_generation:
                return
            self.armed = False
            self.safe(callback)
        QTimer.singleShot(5000, begin)

    def start_recording(self):
        self.idle()
        scope = self.require_windows()
        masks = json.loads(self.masks.text())
        if not isinstance(masks, list) or len(masks) > 12 or any(not isinstance(b, list) or len(b) != 4 or any(type(x) not in (int, float) for x in b) or not (0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1) for b in masks):
            raise ValueError("Exclusions must be a JSON list of normalized rectangles")
        task, role, keys = self.task_id, "practice" if self.role.currentIndex() else "train", self.keys.isChecked()
        expected = "expected_stop" if self.role.currentIndex() == 2 else "verified"
        def begin():
            recorder = Recorder(self.store, self.desktop, scope, task, role, keys, masks, expected_outcome=expected, health=lambda: self.hotkey.thread.is_alive() and not self.hotkey.error)
            recorder.start()
            self.recorder = recorder
        self.arm(begin)

    def pause(self):
        if self.recorder:
            self.recorder.pause()
        elif self.runner:
            self.control.pause("User paused; correct current state before resuming")

    def note(self):
        if not self.recorder:
            raise ValueError("Start a teaching session first")
        self.recorder.pause()
        note, ok = QInputDialog.getMultiLineText(self, "Teaching explanation", "Goal or decision at this point (saved with timestamp; do not enter secrets). Recording remains paused until Resume.")
        if ok and note.strip():
            import time
            self.recorder.queue.put_nowait((time.perf_counter()-self.recorder.started, "explanation", {"text": note.strip()}))

    def resume(self):
        # Arming delay allows refocusing target before recheck; no input during delay.
        if self.recorder:
            self.arm(lambda: self.recorder.pause(False) if self.recorder else None)
        elif self.runner:
            scope = self.runner.scope
            def begin():
                self.desktop.check(scope, self.runner.display)
                self.control.resume()
            self.arm(begin)

    def emergency_stop(self):
        self.emergency.set()
        self.armed = False
        if self.control:
            self.control.stop()
        if self.recorder:
            self.recorder.stop(emergency=True)

    def stop(self):
        self.armed = False
        if self.control:
            self.control.stop("User stopped")
            if not self.runner:
                self.control = None
        if self.recorder:
            self.recorder.stop()
        if not self.control and not self.recorder:
            self.overlay.hide()

    def show_demo(self):
        self.frame_label.clear()
        self.timeline.setRowCount(0)
        self.timeline_entries = []
        ident = self.demos.currentData()
        if not ident:
            self.frame_label.clear()
            if self.shell:
                self.shell.refresh_recording()
            return
        demo = self.store.rows("SELECT metadata FROM demos WHERE id=?", (ident,))[0]
        ranges = json.loads(demo["metadata"]).get("ignored_ranges", [])
        events = self.store.rows("SELECT * FROM events WHERE demo=? ORDER BY seq", (ident,))
        frames = self.store.rows("SELECT * FROM frames WHERE demo=? ORDER BY t", (ident,))
        self.timeline_frames = frames
        entries = sorted([{"t": e["t"], "kind": e["kind"], "desc": e["data"]} for e in events]+[{"t": f["t"], "kind": "frame", "desc": f["id"]+" · "+f["geometry"], "frame": f} for f in frames], key=lambda e: e["t"])
        self.timeline_entries = entries
        self.timeline.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            included = not any(a <= entry["t"] <= b for a, b, _ in ranges)
            for col, value in enumerate((f"{entry['t']:.3f}", entry["kind"], entry["desc"], "yes" if included else "excluded")):
                self.timeline.setItem(row, col, QTableWidgetItem(value))
        self.timeline.resizeColumnsToContents()
        self.timeline.setColumnWidth(2, 480)
        if self.shell:
            self.shell.refresh_recording()

    def show_frame(self):
        row = self.timeline.currentRow()
        if row < 0 or not self.timeline_frames:
            return
        entry = self.timeline_entries[row]
        frame = min(self.timeline_frames, key=lambda f: abs(f["t"]-entry["t"]))
        image = QPixmap(str(self.store.root/frame["path"]))
        self.frame_label.setPixmap(image.scaled(750, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.frame_label.setToolTip(f"Frame {frame['id']}, t={frame['t']:.3f}. Full resolution local file: {self.store.root/frame['path']}")

    def exclude(self):
        self.idle()
        ident = self.demos.currentData()
        if not ident:
            raise ValueError("Select a demonstration")
        text, ok = QInputDialog.getText(self, "Exclude interval", "start seconds,end seconds,reason (e.g. 2.5,5.0,mistake)")
        if not ok:
            return
        a, b, reason = text.split(",", 2)
        a, b = float(a), float(b)
        if not 0 <= a < b or not reason.strip():
            raise ValueError("Provide an ordered interval and reason")
        metadata = json.loads(self.store.rows("SELECT metadata FROM demos WHERE id=?", (ident,))[0]["metadata"])
        metadata.setdefault("ignored_ranges", []).append([a, b, reason])
        self.store.execute("UPDATE demos SET metadata=? WHERE id=?", (json.dumps(metadata), ident))
        self.store.invalidate(self.task_id, "Evidence exclusion changed; repeat review and practice")
        self.refresh_library()

    def delete_demo(self):
        self.idle()
        ident = self.demos.currentData()
        if ident and self.confirm("Delete local evidence", "Delete this demonstration, derived workflow versions and their runs? This cannot be undone.") == QMessageBox.StandardButton.Yes:
            before = {r["id"] for r in self.store.rows("SELECT id FROM runs WHERE task=?", (self.task_id,))}
            self.store.delete_demo(ident)
            after = {r["id"] for r in self.store.rows("SELECT id FROM runs WHERE task=?", (self.task_id,))}
            import shutil
            for rid in before-after:
                shutil.rmtree(self.store.root/"runs"/rid, ignore_errors=True)
            self.refresh_library()

    def save_review(self):
        self.idle()
        v = self.selected_version()
        materialize(self.store, v)
        answers = {key: edit.text().strip() for key, edit in self.answer_widgets.items()}
        self.store.execute("UPDATE versions SET answers=?,reviewed=? WHERE id=?", (json.dumps(answers), int(self.reviewed.isChecked()), v["id"]))
        self.refresh_library()

    def save_candidate(self):
        self.idle()
        self.selected_task()
        workflow = validate(json.loads(self.editor.toPlainText()))
        ident = self.store.add_version(self.task_id, workflow)
        try:
            materialize(self.store, self.store.version(ident))
        except Exception:
            self.store.execute("DELETE FROM versions WHERE id=?", (ident,))
            import shutil
            shutil.rmtree(self.store.root/"assets"/ident, ignore_errors=True)
            raise
        self.versions.setCurrentIndex(-1)
        self.refresh_library()

    def configure_model(self):
        self.idle()
        config = model.settings(self.store)
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure an application model")
        form = QFormLayout(dialog)
        note = QLabel("The model building this software is separate from this application's runtime model.\nYour ChatGPT subscription does not provide API credit.\n\nGeneration sends up to 24 full-resolution screenshots, recorded actions, task notes and review answers.\nEstimated use: roughly 5k–40k input tokens and up to 9k output tokens/call.\nExample at $2/M input + $8/M output: about $0.08–$0.15 per call, not a quote.\nCheck your provider's current image/token pricing; multiple attempts may be needed.\nLocal compatible vision models can avoid paid API use.\n\nUse a Chat Completions endpoint supporting images and JSON mode. Set the key outside the app\nas TEACHDESK_MODEL_KEY before launching. Never paste keys into task notes or recordings.")
        note.setWordWrap(True)
        form.addRow(note)
        url = QLineEdit(config.get("base_url", "https://api.openai.com/v1"))
        name = QLineEdit(config.get("model", ""))
        consent = QCheckBox("I authorize selected demonstration screenshots/actions to be sent to this endpoint when I click Generate")
        consent.setChecked(config.get("consent", False))
        local = QCheckBox("Localhost model requires no API key")
        local.setChecked(config.get("local_no_key", False))
        structured = QCheckBox("Require structured replies (recommended for supported OpenAI models)")
        structured.setChecked(model.structured_outputs(config if config else {"base_url": url.text()}))
        form.addRow("API base URL", url)
        form.addRow("Vision model identifier", name)
        form.addRow(local)
        form.addRow(structured)
        form.addRow(consent)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            model.save_settings(self.store, {"base_url": url.text().strip(), "model": name.text().strip(), "consent": consent.isChecked(), "local_no_key": local.isChecked(), "structured_outputs": structured.isChecked()})
            self.refresh_notice()
            if self.shell:
                self.shell.refresh_project()

    def background(self, fn, message):
        self.worker_busy = True
        def work():
            try:
                result = fn()
                self.messages.put((message, result, None))
            except Exception as exc:
                self.messages.put((message, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def generate(self):
        self.idle()
        task = self.selected_task()
        ok, reason = model.availability(self.store)
        if not ok:
            raise ValueError(reason)
        demos, frames = model.prepare_evidence(self.store, task["id"])
        hostname = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(model.settings(self.store)["base_url"]).hostname
        if self.confirm("Send teaching evidence to AI?", f"Send {len(frames)} sampled screenshots from {len(demos)} current teaching examples, plus included action logs, project notes and answers, to {hostname}?\nPractice examples and incompatible older recordings are excluded. Review your recordings first. The configured provider may charge for this call.") != QMessageBox.StandardButton.Yes:
            return
        self.background(lambda: model.generate(self.store, task["id"]), "model")

    def promote(self):
        self.idle()
        self.store.promote(self.selected_task()["id"], self.selected_version()["id"])
        self.refresh_library()

    def recover_model_reply(self):
        self.idle()
        task = self.selected_task()
        self.background(lambda: model.recover(self.store, task["id"]), "model")

    def delete_model_replies(self):
        self.idle()
        task = self.selected_task()
        if self.confirm("Delete saved AI replies", "Delete locally saved AI replies for this project? Existing workflow versions stay available. This does not undo API charges.") == QMessageBox.StandardButton.Yes:
            self.store.execute("DELETE FROM model_replies WHERE task=?", (task["id"],))
            self.refresh_library()

    def run(self, practice):
        self.idle()
        scope = self.require_windows()
        v = self.selected_version()
        if not practice:
            active = self.selected_task()["active_version"]
            if active != v["id"]:
                raise ValueError("Select the active Ready version, or use supervised practice for this candidate")
        inputs = {}
        for name, desc in v["workflow"]["inputs"].items():
            value, ok = QInputDialog.getText(self, "Task input (not logged)", name+": "+desc)
            if not ok:
                return
            inputs[name] = value
        practice_demo = None
        if practice:
            demos = [d for d in self.store.evidence(self.task_id, "practice") if d["metadata"].get("capture_validation") == CAPTURE_VALIDATION_VERSION and d["id"] not in v["workflow"]["sources"]]
            if not demos:
                raise ValueError("Record a held-out practice example at a different layout first. It will not be sent to the model.")
            if len(demos) == 1:
                practice_demo = demos[0]["id"]
            else:
                from .project_ui import recording_name
                labels = [recording_name({**d, "metadata": json.dumps(d["metadata"])}) for d in demos]
                chosen, ok = QInputDialog.getItem(self, "Practice example", "Reset the app to the starting layout of a separate example, then choose it", labels, editable=False)
                if not ok:
                    return
                practice_demo = demos[labels.index(chosen)]["id"]
        authorized = []
        def preview(n):
            effect = v["workflow"]["targets"].get(n.get("target"), {}).get("description", n.get("reason", ""))
            if n["kind"] == "type":
                import re
                effect += " · text: "+re.sub(r"\$\{([^}]+)\}", lambda m: inputs[m[1]], n["text"])
            if n["kind"] == "key":
                effect += " · keys: "+"+".join(n["keys"])
            return f"{n['kind']} → "+effect
        plan = "\n".join(f"{i}. "+preview(n) for i, n in enumerate(v["workflow"]["nodes"], 1))
        practice_note = "Practice: reset the app to the starting state/layout of the selected separate example before continuing.\n" if practice else ""
        if self.confirm("Allow this project to control the app?", f"Application: {scope.title}\nGoal: {v['workflow']['goal']}\nAllowed scope: {v['workflow']['scope']}\n{practice_note}\n{plan}\n\nAllow these visible actions for this run? The default limit is 120 seconds. Stop if an effect is unclear or not authorized.") != QMessageBox.StandardButton.Yes:
            return
        for node in v["workflow"]["nodes"]:
            if node["consequential"]:
                target = node.get("target", "")
                description = v["workflow"]["targets"].get(target, {}).get("description", node.get("reason", ""))
                if self.confirm("Authorize one run", f"Authorize consequential step {node['id']}: {node['kind']} on {description}?\nThis applies only to this run, within the selected window. No denies the run.") != QMessageBox.StandardButton.Yes:
                    return
                authorized.append(node["id"])
        duration = 120
        if self.shell and self.shell.pages.currentWidget() == self.shell.details:
            duration, ok = QInputDialog.getInt(self, "Run boundary", "Maximum duration in seconds, including pauses", 120, 10, 300)
            if not ok:
                return
        control = Control()
        control.health = lambda: self.hotkey.thread.is_alive() and not self.hotkey.error
        runner = Runner(self.store, self.desktop, scope, v, control, inputs, practice_demo, authorized, duration, self.manual_pause.isChecked())
        self.control = control
        def begin():
            self.runner = runner
            self.background(runner.execute, "run")
        self.arm(begin)

    def show_history(self):
        if not self.task_id:
            return
        runs = self.store.rows("SELECT * FROM runs WHERE task=? ORDER BY created DESC", (self.task_id,))
        counts = {k: sum(r["outcome"] == k for r in runs) for k in ("verified", "failed", "intervened", "stopped", "expected_stop", "interrupted", "invalidated", "running")}
        self.history.setPlainText(f"Evaluated runs: {sum(r['outcome'] != 'running' for r in runs)} · {json.dumps(counts)}\nThese counts are separate from readiness.\n\n"+"\n\n".join(f"{r['id']} · {r['outcome']} · version {r['version'][:8]} · practice {r['practice_demo'] or 'no'}\n{r['detail']}\nLast screenshot (if captured): {self.store.root/'runs'/r['id']/'last-state.png'}" for r in runs))
        replies = self.store.rows("SELECT * FROM model_replies WHERE task=? ORDER BY created DESC", (self.task_id,))
        self.reply_history.setPlainText("Saved locally. Checking a saved reply sends no API request. These replies are untrusted task data.\n\n"+"\n\n".join(f"{reply['status']} · {json.loads(reply['metadata'])['model']}\n{reply['detail']}\nUsage: {json.dumps(json.loads(reply['metadata']).get('usage', {}))}\n{reply['content']}" for reply in replies))

    def delete_history(self):
        self.idle()
        self.selected_task()
        if self.confirm("Delete history", "Delete this task's run records and screenshots? Readiness will lose practice evidence.") == QMessageBox.StandardButton.Yes:
            import shutil
            for r in self.store.rows("SELECT id FROM runs WHERE task=?", (self.task_id,)):
                shutil.rmtree(self.store.root/"runs"/r["id"], ignore_errors=True)
            self.store.execute("DELETE FROM runs WHERE task=?", (self.task_id,))
            self.refresh_library()

    def open_lab(self):
        self.idle()
        self.windows.setCurrentIndex(0)
        child = subprocess.Popen([sys.executable, "-m", "teachdesk.lab"])
        def select(attempt=0):
            if not self.desktop or child.poll() is not None or self.armed or self.runner or self.recorder or self.windows.currentData() is not None:
                return
            self.refresh_windows()
            for i in range(self.windows.count()):
                win = self.windows.itemData(i)
                if win is not None and win.pid == child.pid:
                    self.windows.setCurrentIndex(i)
                    return
            if attempt < 30:
                QTimer.singleShot(200, lambda: self.safe(lambda: select(attempt+1)))
        QTimer.singleShot(200, lambda: self.safe(select))

    def delete_task(self):
        self.idle()
        task = self.selected_task()
        if self.confirm("Delete task", f"Permanently delete {task['name']}, all demonstrations, workflow versions, answers and run evidence? Ordinary deletion cannot be undone.") == QMessageBox.StandardButton.Yes:
            self.store.delete_task(task["id"])
            self.task_id = None
            self.versions.clear()
            self.demos.clear()
            self.title.setText("Open or create a project")
            self.history.clear()
            self.refresh_library()

    def poll(self):
        if self.emergency.is_set():
            self.emergency.clear()
            self.state.setText("Stopped · emergency requested · releasing held input")
            if self.control and not self.runner:
                self.control = None  # A cancelled countdown has no worker to clear it.
        if self.recorder and self.recorder.finished.is_set():
            error = self.recorder.error
            finished_demo = self.recorder.demo
            self.task_id = self.store.rows("SELECT task FROM demos WHERE id=?", (finished_demo,))[0]["task"]
            self.recorder = None
            self.overlay.hide()
            self.showNormal()
            self.refresh_library()
            self.demos.setCurrentIndex(self.demos.findData(finished_demo))
            self.show_demo()
            self.tabs.setCurrentIndex(1)
            for row, entry in enumerate(self.timeline_entries):
                if entry["kind"] == "frame":
                    self.timeline.selectRow(row)
                    self.timeline.scrollToTop()
                    break
            if self.shell:
                self.shell.open_current()
                self.shell.steps.setCurrentIndex(1)
            if error:
                QMessageBox.warning(self, "Recording interrupted", error)
        while not self.messages.empty():
            kind, result, error = self.messages.get_nowait()
            self.worker_busy = False
            if kind == "run":
                finished_runner = self.runner
                self.runner = self.control = None
                if finished_runner and not self.store.task(finished_runner.version["task"])["active_version"]:
                    candidate = self.store.version(finished_runner.version["id"])
                    if all(c["passed"] for c in readiness(self.store, candidate)):
                        self.store.promote(candidate["task"], candidate["id"])
                self.overlay.hide()
                self.showNormal()
            else:
                self.versions.setCurrentIndex(-1)
            self.refresh_library()
            if self.shell:
                self.shell.open_current()
                self.shell.steps.setCurrentIndex(2 if kind == "run" else 1)
            if error:
                self.state.setText("Stopped · review failed · Ctrl+Alt+F8 emergency stop")
                QMessageBox.warning(self, "Operation failed", error)
        if self.armed:
            if self.shell:
                self.shell.sync_activity()
            return
        state = "Stopped"
        if self.recorder:
            if self.recorder.paused.is_set():
                state = "Paused"
            elif self.desktop.foreground() != self.recorder.scope.hwnd:
                state = "Paused · target out of focus"
            elif self.recorder.capture_reason:
                state = "Paused · "+self.recorder.capture_reason
            else:
                state = "Recording"
        elif self.runner:
            state = "Paused" if self.control.paused.is_set() else self.runner.state
        elif self.worker_busy:
            state = "Stopped · model review in progress"
        self.state.setText(state+" · Ctrl+Alt+F8 emergency stop")
        if self.recorder or self.runner:
            self.overlay.setText(state+" · Ctrl+Alt+F8 STOP")
            self.overlay.adjustSize()
            self.overlay.show()
        else:
            self.overlay.hide()
        if self.shell:
            self.shell.sync_activity()

    def closeEvent(self, event):
        self.stop()
        # Keep Qt alive until release and recording flush complete; model network requests
        # cannot emit desktop input and are independent of emergency stopping.
        if self.recorder or self.runner:
            event.ignore()
            if not self.closing:
                self.closing = True
                def retry():
                    if self.recorder or self.runner:
                        QTimer.singleShot(100, retry)
                    else:
                        self.close()
                QTimer.singleShot(100, retry)
            return
        if self.worker_busy:
            event.ignore()
            QMessageBox.information(self, "Model request active", "Wait for the model request to finish before closing (180-second request timeout). No desktop input is active.")
            return
        self.hotkey.close()
        self.overlay.close()
        super().closeEvent(event)


def main():
    enable_dpi_awareness()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    root = default_home()
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root/"instance.lock"))
    if not lock.tryLock(0):
        QMessageBox.warning(None, "TeachDesk already running", "Close the other TeachDesk instance before opening this task store")
        sys.exit(1)
    window = MainWindow(Store(root))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
