"""Shared fixtures for vibe-linter scenario tests."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from vibe_linter.engine.executor import Executor, SubmitResult
from vibe_linter.engine.node_loader import _NODE_REGISTRY, load_nodes

if TYPE_CHECKING:
    from vibe_linter.types import NodeDefinition

FLOWS_DIR = Path(__file__).parent / ".vibe" / "flows"


class FlowHarness:
    """Test harness for driving a workflow through the executor.

    Provides a clean temp .vibe directory per test, with convenience
    methods for common multi-step patterns.  All methods delegate to
    Executor public API and return SubmitResult.
    """

    def __init__(self, flow_file: str, *, loop_data: dict | None = None):
        self.tmp = Path(tempfile.mkdtemp())
        self.vibe_dir = self.tmp / ".vibe"
        self.vibe_dir.mkdir()
        (self.vibe_dir / "flows").mkdir()
        (self.vibe_dir / "nodes").mkdir()

        src = FLOWS_DIR / flow_file
        dst = self.vibe_dir / "flows" / flow_file
        shutil.copy2(src, dst)

        self.flow_name = flow_file.removesuffix(".yaml")
        self.executor = Executor(self.vibe_dir)

        # Pre-seed loop data so iterate expressions resolve
        self._loop_data = loop_data or {}

    def start(self) -> SubmitResult:
        """Start the workflow via executor public API."""
        msg = self.executor.start(
            self.flow_name,
            initial_data=self._loop_data or None,
        )
        state = self.state
        return SubmitResult(True, msg, state.current_step if state else None)

    @property
    def state(self):
        return self.executor.state_manager.get_current_state()

    @property
    def step(self) -> str:
        return self.state.current_step

    @property
    def status(self) -> str:
        return self.state.status

    def submit(self, data: dict | None = None) -> SubmitResult:
        return self.executor.submit(data or {})

    def submit_goto(self, target: str) -> SubmitResult:
        return self.executor.submit({"_goto": target})

    def skip(self, reason: str | None = None) -> SubmitResult:
        return self.executor.skip(reason)

    def approve(self, data: dict | None = None) -> SubmitResult:
        return self.executor.approve(data)

    def reject(self, reason: str | None = None) -> SubmitResult:
        return self.executor.reject(reason)

    def goto(self, target: str) -> SubmitResult:
        return self.executor.goto(target)

    def back(self) -> SubmitResult:
        return self.executor.back()

    def retry(self) -> SubmitResult:
        return self.executor.retry()

    def stop(self) -> SubmitResult:
        return self.executor.stop()

    def resume(self) -> SubmitResult:
        return self.executor.resume()

    def reset(self):
        self.executor.state_manager.reset()

    def get_status(self) -> dict:
        return self.executor.get_status()

    def get_history(self, limit: int = 50) -> list[dict]:
        return self.executor.get_history(limit)

    def advance_to(self, target_step: str, max_steps: int = 30):
        """Submit empty data repeatedly until reaching the target step.

        For LLM-condition steps, uses _goto to choose a path.
        """
        for _ in range(max_steps):
            if self.step == target_step:
                return
            s = self.state
            if s.status == "waiting":
                self.approve()
                continue
            if s.status in ("done", "stopped"):
                break
            # Try plain submit; if stuck, it means LLM conditions
            r = self.executor.submit({})
            if not r.success or r.new_step == s.current_step:
                # LLM condition - need _goto
                break
        if self.step != target_step:
            raise RuntimeError(
                f"Could not advance to {target_step!r}, stuck at {self.step!r} ({self.status})"
            )

    def close(self):
        self.executor.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def new_executor(self) -> None:
        """Close current executor and create a fresh one from the same state.db.

        Simulates user closing a session and reopening later.
        """
        self.executor.close()
        self.executor = Executor(self.vibe_dir)

    def install_node(self, filename: str, code: str) -> None:
        """Write a node definition file into .vibe/nodes/."""
        dst = self.vibe_dir / "nodes" / filename
        dst.write_text(code, encoding="utf-8")

    def reload_nodes(self) -> None:
        """Reload all node definitions from .vibe/nodes/."""
        load_nodes(self.vibe_dir / "nodes")

    def register_node(self, step_name: str, node_def: NodeDefinition) -> None:
        """Register a node definition keyed by step name.

        The executor looks up nodes via get_node(step.name), so the registry
        key must match the step name exactly.
        """
        node_def.name = step_name
        _NODE_REGISTRY[step_name] = node_def

    def get_archived_rows(self, table_name: str) -> list[dict]:
        """Query rows from an archive table created by a node."""
        try:
            rows = self.executor.state_manager.db.execute(
                f'SELECT * FROM "{table_name}"'
            ).fetchall()
            col_info = self.executor.state_manager.db.execute(
                f'PRAGMA table_info("{table_name}")'
            ).fetchall()
            col_names = [c[1] for c in col_info]
            return [dict(zip(col_names, row, strict=False)) for row in rows]
        except Exception:
            return []

    def save_checkpoint(self, name: str) -> None:
        self.executor.state_manager.save_checkpoint(name)

    def load_checkpoint(self, name: str):
        return self.executor.state_manager.load_checkpoint(name)

    def reload_yaml(self, new_content: str):
        """Overwrite the flow YAML and clear the cached flow definition."""
        path = self.vibe_dir / "flows" / f"{self.flow_name}.yaml"
        path.write_text(new_content, encoding="utf-8")
        self.executor.flow = None  # force re-parse on next access

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@pytest.fixture
def harness_factory():
    """Factory fixture that creates FlowHarness instances and cleans up after test."""
    created: list[FlowHarness] = []

    def _make(flow_file: str, **kwargs) -> FlowHarness:
        h = FlowHarness(flow_file, **kwargs)
        created.append(h)
        return h

    yield _make

    for h in created:
        h.close()


# ─── Node code templates for tests ───

VALIDATE_NODE = """\
from vibe_linter.engine.node_loader import node

@node("validate")
def {name}():
    return {{
        "check": lambda data: {check_expr},
    }}
"""

ARCHIVE_NODE = """\
from vibe_linter.engine.node_loader import node

@node("validate", "archive")
def {name}():
    return {{
        "check": lambda data: {check_expr},
        "schema": {{"output": {schema}}},
        "archive": {{"table": "{table}"}},
    }}
"""

EVAL_NODE = """\
from vibe_linter.engine.node_loader import node

@node("eval")
def {name}():
    return {{
        "check": lambda data: {check_expr},
    }}
"""

EDIT_POLICY_NODE = """\
from vibe_linter.engine.node_loader import node

@node("validate")
def {name}():
    return {{
        "check": lambda data: True,
        "edit_policy": {{
            "default": "{default}",
            "patterns": {patterns},
        }},
    }}
"""
