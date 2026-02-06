"""Tests for the PreToolUse hook (check_edit.py).

These tests verify that the prehook correctly:
1. Blocks edits when no scenario has been collected
2. Blocks edits when current step's edit_policy says block
3. Warns on edits when edit_policy says warn
4. Allows edits when edit_policy says silent or scenario exists
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from vibe_linter.engine.executor import Executor

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def vibe_dir(tmp_path: Path) -> Path:
    """Create a temporary .vibe directory with test flow."""
    vibe = tmp_path / ".vibe"
    vibe.mkdir()
    (vibe / "nodes").mkdir()

    # Create a minimal flow with step names matching node function names
    # Note: No wait steps - all steps auto-advance or require submit
    flow_yaml = """
name: Test Flow
description: Flow for testing edit constraints

steps:
  - collect_scenario

  - design:
      next:
        - go: implement

  - implement

  - Done:
      type: terminate
"""
    (vibe / "flows").mkdir()
    (vibe / "flows" / "test.yaml").write_text(flow_yaml, encoding="utf-8")

    # Create node definitions with edit policies
    node_code = '''
from vibe_linter.engine.node_loader import node

@node("auto")
def collect_scenario():
    return {
        "check": lambda data: True if data.get("scenario") else "need scenario",
        "edit_policy": {
            "default": "block",
            "patterns": [],
        },
    }

@node("auto")
def design():
    return {
        "check": lambda data: True,
        "edit_policy": {
            "default": "warn",
            "patterns": [],
        },
    }

@node("auto")
def implement():
    return {
        "check": lambda data: True,
        "edit_policy": {
            "default": "silent",
            "patterns": [],
        },
    }
'''
    (vibe / "nodes" / "test_nodes.py").write_text(node_code, encoding="utf-8")

    return vibe


def run_check_edit_hook(
    cwd: Path,
    tool_name: str,
    file_path: str,
) -> tuple[int, str, str]:
    """Run the check_edit hook as a subprocess.

    Returns (exit_code, stdout, stderr).
    """
    hook_input = json.dumps({
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    })

    result = subprocess.run(
        [sys.executable, "-m", "vibe_linter.integrations.check_edit"],
        input=hook_input,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout, result.stderr


class TestCheckEditHook:
    """Test the PreToolUse hook behavior."""

    def test_no_vibe_dir_allows_edit(self, tmp_path: Path):
        """Without .vibe directory, all edits are allowed."""
        code, _stdout, _stderr = run_check_edit_hook(
            tmp_path,
            "Write",
            str(tmp_path / "foo.py"),
        )
        assert code == 0

    def test_no_active_workflow_allows_edit(self, vibe_dir: Path):
        """Without an active workflow, all edits are allowed."""
        cwd = vibe_dir.parent
        code, _stdout, _stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )
        assert code == 0

    def test_blocks_edit_without_scenario(self, vibe_dir: Path):
        """When workflow is active but no scenario, edits are blocked."""
        cwd = vibe_dir.parent

        # Start the workflow (start takes flow_name without .yaml)
        executor = Executor(vibe_dir)
        executor.start("test")
        executor.close()

        # Try to edit - should be blocked
        code, _stdout, stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )

        assert code == 2, f"Expected exit code 2 (block), got {code}"
        assert "BLOCKED" in stderr
        assert "No scenario collected" in stderr

    def test_allows_edit_with_scenario_on_implement_step(self, vibe_dir: Path):
        """When scenario exists and step allows editing, edits are allowed."""
        cwd = vibe_dir.parent

        # Start workflow with scenario and navigate to implement step
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"bug_description": "Email login is broken"})
        executor.submit({"scenario": True})  # collect_scenario -> design
        executor.submit({})  # design -> implement
        executor.close()

        # Try to edit - should be allowed (has scenario + implement has silent policy)
        code, _stdout, stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )

        assert code == 0, f"Expected exit code 0 (allow), got {code}. stderr: {stderr}"

    def test_blocks_edit_on_block_policy_step(self, vibe_dir: Path):
        """When step has edit_policy=block, edits are blocked."""
        cwd = vibe_dir.parent

        # Start workflow with scenario, at step with block policy
        executor = Executor(vibe_dir)
        # Start with scenario but at "collect_scenario" which has block policy
        executor.start("test", initial_data={"bug_description": "Test bug"})
        executor.close()

        # Try to edit - should be blocked due to edit_policy
        code, _stdout, stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )

        # Note: The hook checks scenario first, then edit_policy
        # Since we have a scenario, it proceeds to check edit_policy
        # The "collect_scenario" step has block policy
        assert code == 2, f"Expected exit code 2 (block), got {code}. stderr: {stderr}"
        assert "BLOCKED" in stderr

    def test_warns_on_warn_policy_step(self, vibe_dir: Path):
        """When step has edit_policy=warn, warning is issued but edit allowed."""
        cwd = vibe_dir.parent

        # Start workflow at design step (warn policy)
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"bug_description": "Test bug"})
        # Submit to move past collect_scenario -> design
        executor.submit({"scenario": True})
        executor.close()

        # Try to edit - should warn but allow (design has warn policy)
        code, stdout, _stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )

        # Exit code 0 means allowed
        assert code == 0
        # stdout should have warning message
        if stdout:
            parsed = json.loads(stdout)
            assert "systemMessage" in parsed or "Warning" in stdout

    def test_allows_edit_on_silent_policy_step(self, vibe_dir: Path):
        """When step has edit_policy=silent, edits are silently allowed."""
        cwd = vibe_dir.parent

        # Start workflow and navigate to implement step
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"bug_description": "Test bug"})
        executor.submit({"scenario": True})  # collect_scenario -> design
        executor.submit({})  # design -> implement
        executor.close()

        # Try to edit - should be silently allowed (implement has silent policy)
        code, stdout, _stderr = run_check_edit_hook(
            cwd,
            "Edit",
            str(cwd / "foo.py"),
        )

        assert code == 0
        # No warning in stdout
        assert "Warning" not in stdout

    def test_stopped_workflow_allows_edit(self, vibe_dir: Path):
        """When workflow is stopped, edits are allowed."""
        cwd = vibe_dir.parent

        # Start and stop workflow
        executor = Executor(vibe_dir)
        executor.start("test")
        executor.stop()
        executor.close()

        # Try to edit - should be allowed
        code, _stdout, _stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )

        assert code == 0

    def test_done_workflow_allows_edit(self, vibe_dir: Path):
        """When workflow is done, edits are allowed."""
        cwd = vibe_dir.parent

        # Complete workflow
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"bug_description": "Test"})
        executor.submit({"scenario": True})  # collect_scenario -> design
        executor.submit({})  # design -> implement
        executor.submit({})  # implement -> Done
        executor.close()

        # Try to edit - should be allowed
        code, _stdout, _stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )

        assert code == 0

    def test_non_edit_tools_always_allowed(self, vibe_dir: Path):
        """Read and other non-edit tools are always allowed."""
        cwd = vibe_dir.parent

        # Start workflow without scenario (would normally block edits)
        executor = Executor(vibe_dir)
        executor.start("test")
        executor.close()

        # Try Read tool - should be allowed
        code, _stdout, _stderr = run_check_edit_hook(
            cwd,
            "Read",
            str(cwd / "foo.py"),
        )

        assert code == 0

    def test_scenario_in_nested_step_data(self, vibe_dir: Path):
        """Scenario key in nested step data is detected."""
        cwd = vibe_dir.parent

        # Start workflow with scenario in step data
        executor = Executor(vibe_dir)
        executor.start("test")
        # Submit with nested requirements (simulating a previous step's output)
        executor.submit({
            "requirements": ["req1", "req2"],
        })
        executor.close()

        # Try to edit - should be allowed because "requirements" is a scenario key
        code, _stdout, stderr = run_check_edit_hook(
            cwd,
            "Write",
            str(cwd / "foo.py"),
        )

        # The scenario check looks in step data too
        assert code == 0 or "BLOCKED" not in stderr


class TestScenarioDetection:
    """Test _has_scenario helper function logic."""

    def test_detects_bug_description(self, vibe_dir: Path):
        """bug_description key is recognized as scenario."""
        cwd = vibe_dir.parent
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"bug_description": "Something is broken"})
        executor.close()

        _code, _, stderr = run_check_edit_hook(cwd, "Write", str(cwd / "x.py"))
        # Should not be blocked for "No scenario"
        assert "No scenario collected" not in stderr

    def test_detects_feature_request(self, vibe_dir: Path):
        """feature_request key is recognized as scenario."""
        cwd = vibe_dir.parent
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"feature_request": "Add dark mode"})
        executor.close()

        _code, _, stderr = run_check_edit_hook(cwd, "Write", str(cwd / "x.py"))
        assert "No scenario collected" not in stderr

    def test_detects_user_story(self, vibe_dir: Path):
        """user_story key is recognized as scenario."""
        cwd = vibe_dir.parent
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"user_story": "As a user I want..."})
        executor.close()

        _code, _, stderr = run_check_edit_hook(cwd, "Write", str(cwd / "x.py"))
        assert "No scenario collected" not in stderr

    def test_empty_scenario_not_detected(self, vibe_dir: Path):
        """Empty string scenario is not recognized."""
        cwd = vibe_dir.parent
        executor = Executor(vibe_dir)
        executor.start("test", initial_data={"bug_description": ""})
        executor.close()

        code, _, stderr = run_check_edit_hook(cwd, "Write", str(cwd / "x.py"))
        # Empty string should not count as scenario
        assert code == 2
        assert "No scenario collected" in stderr
