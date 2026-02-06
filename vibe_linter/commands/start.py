"""vibe start — start the loaded workflow, Claude Code takes over."""
from __future__ import annotations

import sys
from pathlib import Path

from vibe_linter.engine import Executor


def cmd_start(cwd: str):
    vibe_dir = Path(cwd) / ".vibe"
    meta_path = vibe_dir / ".loaded"

    if not meta_path.exists():
        print("No flow loaded yet. Run: vibe load <flow>", file=sys.stderr)
        sys.exit(1)

    flow_name = meta_path.read_text(encoding="utf-8").strip()
    executor = Executor(vibe_dir)
    try:
        # Check if resuming from stopped state
        state = executor.state_manager.get_current_state()
        if state and state.status == "stopped" and state.flow_name == flow_name:
            executor.state_manager.update_state(status="running")
            executor.state_manager.add_history(flow_name, state.current_step, "resume")
            step = executor._ensure_flow().steps.get(state.current_step)
            if step and step.config.get("wait"):
                executor.state_manager.update_state(status="waiting")
            print(f'Flow "{flow_name}" resumed at step: {state.current_step}')
        else:
            print(executor.start(flow_name))
        print()
        print("Claude Code has taken over. Start a new session to begin.")
    except Exception as e:
        print(f"Failed to start: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        executor.close()
