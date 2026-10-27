from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def new_id() -> str:
    return uuid.uuid4().hex


def default_home() -> Path:
    return Path(os.environ.get("TEACHDESK_HOME", str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TeachDesk")))


class Store:
    """Single local DB, per-operation connections, WAL, atomic version promotion."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tasks.sqlite3"
        self.lock = threading.RLock()
        with self.db() as c:
            c.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0, active_version TEXT, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS demos (
                id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                role TEXT NOT NULL, status TEXT NOT NULL, metadata TEXT NOT NULL, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS events (
                demo TEXT NOT NULL REFERENCES demos(id) ON DELETE CASCADE, seq INTEGER NOT NULL,
                t REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL, ignored INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(demo,seq));
              CREATE TABLE IF NOT EXISTS frames (
                id TEXT PRIMARY KEY, demo TEXT NOT NULL REFERENCES demos(id) ON DELETE CASCADE,
                t REAL NOT NULL, path TEXT NOT NULL, geometry TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                workflow TEXT NOT NULL, answers TEXT NOT NULL DEFAULT '{}', reviewed INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                version TEXT NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
                practice_demo TEXT REFERENCES demos(id) ON DELETE CASCADE,
                outcome TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY, task TEXT, kind TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
            ''')
            # An interrupted process never converts partial work to success.
            c.execute("UPDATE demos SET status='interrupted' WHERE status='recording'")
            c.execute("UPDATE runs SET outcome='interrupted', detail=? WHERE outcome='running'", (json.dumps({"reason": "Application closed during run"}),))

    @contextmanager
    def db(self):
        with self.lock:
            c = sqlite3.connect(self.path, timeout=15)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise
            finally:
                c.close()

    def rows(self, sql, args=()):
        with self.db() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def execute(self, sql, args=()):
        with self.db() as c:
            c.execute(sql, args)

    def create_task(self, name, description):
        if not name.strip():
            raise ValueError("A task needs a name")
        ident = new_id()
        self.execute("INSERT INTO tasks(id,name,description,created) VALUES(?,?,?,?)", (ident, name.strip(), description, time.time()))
        return ident

    def task(self, ident):
        return self.rows("SELECT * FROM tasks WHERE id=?", (ident,))[0]

    def create_demo(self, task, metadata, role="train"):
        if role not in {"train", "practice"}:
            raise ValueError("Invalid demonstration role")
        ident = new_id()
        self.execute("INSERT INTO demos VALUES(?,?,?,?,?,?)", (ident, task, role, "recording", json.dumps(metadata), time.time()))
        return ident

    def event(self, demo, seq, t, kind, data):
        self.execute("INSERT INTO events(demo,seq,t,kind,data) VALUES(?,?,?,?,?)", (demo, seq, t, kind, json.dumps(data)))

    def frame(self, demo, t, image, geometry):
        ident = new_id()
        folder = self.root / "demos" / demo
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{ident}.png"
        image.save(path)
        self.execute("INSERT INTO frames VALUES(?,?,?,?,?)", (ident, demo, t, str(path.relative_to(self.root)), json.dumps(geometry)))
        return ident

    def evidence(self, task, role="train"):
        demos = self.rows("SELECT * FROM demos WHERE task=? AND role=? AND status='complete' ORDER BY created", (task, role))
        result = []
        for demo in demos:
            demo["metadata"] = json.loads(demo["metadata"])
            demo["events"] = self.rows("SELECT * FROM events WHERE demo=? AND ignored=0 ORDER BY seq", (demo["id"],))
            for e in demo["events"]:
                e["data"] = json.loads(e["data"])
            demo["frames"] = self.rows("SELECT * FROM frames WHERE demo=? ORDER BY t", (demo["id"],))
            ranges = demo["metadata"].get("ignored_ranges", [])
            demo["frames"] = [f for f in demo["frames"] if not any(a <= f["t"] <= b for a, b, _ in ranges)]
            demo["events"] = [e for e in demo["events"] if not any(a <= e["t"] <= b for a, b, _ in ranges)]
            result.append(demo)
        return result

    def add_version(self, task, workflow):
        from .workflow import validate
        validate(workflow)
        ident = new_id()
        self.execute("INSERT INTO versions(id,task,workflow,created) VALUES(?,?,?,?)", (ident, task, json.dumps(workflow), time.time()))
        return ident

    def version(self, ident):
        v = self.rows("SELECT * FROM versions WHERE id=?", (ident,))[0]
        v["workflow"] = json.loads(v["workflow"])
        v["answers"] = json.loads(v["answers"])
        return v

    def delete_demo(self, ident):
        # Deleting evidence invalidates versions derived from it (and their readiness).
        with self.db() as c:
            demo = c.execute("SELECT task FROM demos WHERE id=?", (ident,)).fetchone()
            if not demo:
                return
            before = {r["id"] for r in c.execute("SELECT id FROM runs WHERE task=?", (demo["task"],))}
            for v in c.execute("SELECT id,workflow FROM versions WHERE task=?", (demo["task"],)).fetchall():
                if ident in json.loads(v["workflow"])["sources"]:
                    c.execute("UPDATE tasks SET active_version=NULL WHERE active_version=?", (v["id"],))
                    c.execute("DELETE FROM versions WHERE id=?", (v["id"],))
                    shutil.rmtree(self.root / "assets" / v["id"], ignore_errors=True)
            c.execute("DELETE FROM demos WHERE id=?", (ident,))
            after = {r["id"] for r in c.execute("SELECT id FROM runs WHERE task=?", (demo["task"],))}
        for rid in before-after:
            shutil.rmtree(self.root/"runs"/rid, ignore_errors=True)
        shutil.rmtree(self.root / "demos" / ident, ignore_errors=True)
        self.execute("INSERT INTO audit(task,kind,detail,created) VALUES(?,?,?,?)", (demo["task"], "delete_demo", ident, time.time()))

    def invalidate(self, task, reason):
        with self.db() as c:
            c.execute("UPDATE versions SET reviewed=0 WHERE task=?", (task,))
            for row in c.execute("SELECT * FROM runs WHERE task=?", (task,)).fetchall():
                data = json.loads(row["detail"])
                data["previous_outcome"] = row["outcome"]
                data["invalidation_reason"] = reason
                c.execute("UPDATE runs SET outcome='invalidated',detail=? WHERE id=?", (json.dumps(data), row["id"]))

    def delete_task(self, task):
        with self.db() as c:
            folders = [(base, row["id"]) for table, base in (("demos", "demos"), ("versions", "assets"), ("runs", "runs")) for row in c.execute(f"SELECT id FROM {table} WHERE task=?", (task,))]
            c.execute("DELETE FROM tasks WHERE id=?", (task,))
            c.execute("DELETE FROM audit WHERE task=?", (task,))
        for base, ident in folders:
            shutil.rmtree(self.root/base/ident, ignore_errors=True)

    def promote(self, task, version):
        from .workflow import readiness
        v = self.version(version)
        if v["task"] != task or not all(x["passed"] for x in readiness(self, v)):
            raise ValueError("Candidate must pass every readiness check before promotion")
        with self.db() as c:
            c.execute("UPDATE tasks SET active_version=? WHERE id=?", (version, task))
            c.execute("INSERT INTO audit(task,kind,detail,created) VALUES(?,?,?,?)", (task, "promote_or_restore", version, time.time()))
