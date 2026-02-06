"""PreToolUse hook — enforce workflow constraints on file modifications.

This hook intercepts Write/Edit tool calls and checks:
1. Is there an active workflow?
2. Does state.data have a scenario (bug_description, feature_request, etc.)?
3. Does the current step's edit_policy allow this edit?

If any check fails, the hook blocks the edit and tells Claude what to do.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from vibe_linter.engine.executor import Executor
from vibe_linter.engine.policy import check_edit_policy
from vibe_linter.types import EditPolicy, EditPolicyPattern

# Keys that indicate a scenario has been collected
SCENARIO_KEYS = frozenset({
    "bug_description",
    "feature_request",
    "user_story",
    "requirements",
    "scenario",
    "task",
    "goal",
})

# Steps where code editing is typically NOT allowed (early phases)
# These are checked via edit_policy in node definitions, but we also
# provide a fallback heuristic based on step name patterns
EARLY_PHASE_PATTERNS = frozenset({
    "collect",
    "gather",
    "requirements",
    "design",
    "review",
    "scenario",
})


def _has_scenario(data: dict) -> bool:
    """Check if state.data contains any scenario description."""
    if not data:
        return False
    # Check top-level keys
    for key in SCENARIO_KEYS:
        if data.get(key):
            return True
    # Check nested step data (e.g., data["1.1 Gather requirements"]["requirements"])
    for step_data in data.values():
        if isinstance(step_data, dict):
            for key in SCENARIO_KEYS:
                if step_data.get(key):
                    return True
    return False


def _is_early_phase_step(step_name: str) -> bool:
    """Heuristic: is this step in an early phase where editing is discouraged?"""
    step_lower = step_name.lower()
    return any(pattern in step_lower for pattern in EARLY_PHASE_PATTERNS)


def check_edit():
    """Main hook entry point. Called by Claude Code before Write/Edit tools."""
    vibe_dir = Path(os.getcwd()) / ".vibe"

    # If no .vibe directory, not a vibe-managed project — allow everything
    if not vibe_dir.is_dir():
        sys.exit(0)

    # Parse hook input from Claude Code
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Only check file modification tools
    if tool_name not in ("Write", "Edit", "write", "edit"):
        sys.exit(0)

    file_path = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("filePath")
        or ""
    )
    if not file_path:
        sys.exit(0)

    executor = Executor(vibe_dir)
    try:
        status = executor.get_status()

        # No active workflow — allow (user hasn't started vibe yet)
        if status.get("status") == "not_started":
            sys.exit(0)

        # Workflow is stopped or done — allow (user explicitly paused/finished)
        if status.get("status") in ("stopped", "done"):
            sys.exit(0)

        current_step = status.get("current_step", "")
        state_data = status.get("data", {})

        # ══════════════════════════════════════════════════════════════
        # CHECK 1: Does Claude have a scenario?
        # ══════════════════════════════════════════════════════════════
        if not _has_scenario(state_data):
            _block_edit(
                file_path=file_path,
                reason="No scenario collected yet",
                guidance=(
                    "Before modifying code, you need to understand what to do.\n"
                    "Please ask the user to describe the bug or feature, then call:\n"
                    "  vibe_submit_output({\"bug_description\": \"...\", ...})\n"
                    "or\n"
                    "  vibe_submit_output({\"feature_request\": \"...\", ...})"
                ),
            )

        # ══════════════════════════════════════════════════════════════
        # CHECK 2: Does the current step allow editing?
        # ══════════════════════════════════════════════════════════════
        node_info = status.get("node")
        edit_policy = None

        if node_info and node_info.get("edit_policy"):
            # Node has explicit edit_policy — use it
            ep = node_info["edit_policy"]
            patterns = [EditPolicyPattern(**p) for p in ep.get("patterns", [])]
            edit_policy = EditPolicy(default=ep.get("default", "silent"), patterns=patterns)
        elif _is_early_phase_step(current_step):
            # No explicit policy but step looks like early phase — warn
            edit_policy = EditPolicy(default="warn", patterns=[])

        if edit_policy:
            result = check_edit_policy(file_path, edit_policy)

            if result == "block":
                _block_edit(
                    file_path=file_path,
                    reason=f'Step "{current_step}" does not allow editing this file',
                    guidance=(
                        f"The current workflow step is: {current_step}\n"
                        "This step is for planning/review, not code changes.\n"
                        "Please complete this step first by calling vibe_submit_output(),\n"
                        "then proceed to the implementation step."
                    ),
                )
            elif result == "warn":
                _warn_edit(file_path, current_step)

        # All checks passed — allow the edit
        sys.exit(0)

    except Exception as e:
        # On any error, fail open (allow the edit) to avoid blocking user
        # But log the error for debugging
        print(f"[vibe-linter] Hook error (allowing edit): {e}", file=sys.stderr)
        sys.exit(0)
    finally:
        executor.close()


def _block_edit(file_path: str, reason: str, guidance: str) -> None:
    """Block the edit and provide guidance to Claude."""
    message = f"""[vibe-linter] BLOCKED: {reason}

File: {file_path}

{guidance}

Use vibe_get_status() to check current workflow state."""

    # Print to stderr for Claude to see
    print(message, file=sys.stderr)
    # Exit with code 2 to tell Claude Code to block the tool
    sys.exit(2)


def _warn_edit(file_path: str, step_name: str) -> None:
    """Warn about the edit but allow it."""
    print(json.dumps({
        "systemMessage": (
            f'[vibe-linter] Warning: editing "{file_path}" during step "{step_name}". '
            "Please confirm this edit is necessary for the current task. "
            "If you're unsure, call vibe_get_status() to review the workflow state."
        )
    }))
    sys.exit(0)


if __name__ == "__main__":
    check_edit()
