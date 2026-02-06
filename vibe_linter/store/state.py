"""SQLite-backed workflow state persistence."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from vibe_linter.types import WorkflowState

if TYPE_CHECKING:
    from pathlib import Path

INIT_SQL = """
CREATE TABLE IF NOT EXISTS workflow_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    flow_name TEXT NOT NULL,
    current_step TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    data TEXT NOT NULL DEFAULT '{}',
    loop_state TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflow_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_name TEXT NOT NULL,
    step_path TEXT NOT NULL,
    action TEXT NOT NULL,
    data TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    flow_name TEXT NOT NULL,
    state TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class StateManager:
    def __init__(self, db_path: str | Path):
        self.db = sqlite3.connect(str(db_path))
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript(INIT_SQL)

    def has_state(self) -> bool:
        row = self.db.execute("SELECT COUNT(*) FROM workflow_state").fetchone()
        return row[0] > 0

    def init_state(self, state: WorkflowState) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO workflow_state
               (id, flow_name, current_step, status, data, loop_state, started_at)
               VALUES (1, ?, ?, ?, ?, ?, ?)""",
            (
                state.flow_name,
                state.current_step,
                state.status,
                json.dumps(state.data),
                json.dumps(state.loop_state),
                state.started_at or datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        self.db.commit()

    def get_current_state(self) -> WorkflowState | None:
        row = self.db.execute("SELECT * FROM workflow_state WHERE id = 1").fetchone()
        if not row:
            return None
        return WorkflowState(
            flow_name=row[1],
            current_step=row[2],
            status=row[3],
            data=json.loads(row[4]),
            loop_state=json.loads(row[5]),
            started_at=row[6],
        )

    def update_state(self, **kwargs) -> None:
        current = self.get_current_state()
        if not current:
            raise RuntimeError("No active workflow")
        for k, v in kwargs.items():
            setattr(current, k, v)
        self.init_state(current)

    def add_history(self, flow_name: str, step_path: str, action: str, data: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO workflow_history (flow_name, step_path, action, data) VALUES (?, ?, ?, ?)",
            (flow_name, step_path, action, data),
        )
        self.db.commit()

    def get_history(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, flow_name, step_path, action, data, timestamp "
            "FROM workflow_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "flow_name": r[1], "step_path": r[2],
             "action": r[3], "data": r[4], "timestamp": r[5]}
            for r in rows
        ]

    def save_checkpoint(self, name: str) -> None:
        state = self.get_current_state()
        if not state:
            raise RuntimeError("No active workflow")
        self.db.execute(
            "INSERT OR REPLACE INTO workflow_checkpoints (name, flow_name, state) VALUES (?, ?, ?)",
            (name, state.flow_name, json.dumps(state.__dict__)),
        )
        self.db.commit()

    def load_checkpoint(self, name: str) -> WorkflowState | None:
        row = self.db.execute(
            "SELECT state FROM workflow_checkpoints WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        return WorkflowState(**json.loads(row[0]))

    def create_table(self, table_name: str, columns: dict[str, str]) -> None:
        type_map = {"number": "REAL", "boolean": "INTEGER", "string": "TEXT", "string[]": "TEXT"}
        col_defs = ", ".join(f'"{c}" {type_map.get(t, "TEXT")}' for c, t in columns.items())
        self.db.execute(
            f'CREATE TABLE IF NOT EXISTS "{table_name}" '
            f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs}, "
            f"created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        self.db.commit()

    def insert_row(self, table_name: str, data: dict) -> None:
        keys = list(data.keys())
        placeholders = ", ".join("?" for _ in keys)
        values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in data.values()]
        self.db.execute(
            f'INSERT INTO "{table_name}" ({", ".join(keys)}) VALUES ({placeholders})', values
        )
        self.db.commit()

    def reset(self) -> None:
        self.db.execute("DELETE FROM workflow_state")
        self.db.execute("DELETE FROM workflow_history")
        self.db.commit()

    def close(self) -> None:
        self.db.close()
