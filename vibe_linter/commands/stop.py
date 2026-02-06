"""vibe stop — stop the active workflow, remove all constraints."""
from __future__ import annotations

from pathlib import Path

from vibe_linter.store.state import StateManager


def cmd_stop(cwd: str):
    vibe_dir = Path(cwd) / ".vibe"
    db_path = vibe_dir / "state.db"

    if not db_path.exists():
        print("No active workflow to stop.")
        return

    mgr = StateManager(db_path)
    try:
        state = mgr.get_current_state()
        if not state:
            print("No active workflow to stop.")
            return

        if state.status == "stopped":
            print(f'Workflow "{state.flow_name}" is already stopped.')
            return

        if state.status == "done":
            print(f'Workflow "{state.flow_name}" is already completed.')
            return

        mgr.update_state(status="stopped")
        mgr.add_history(state.flow_name, state.current_step, "stop")
        print(f'Workflow "{state.flow_name}" stopped (was at: {state.current_step}).')
        print("All edit constraints removed. Run `vibe start` to resume.")
    finally:
        mgr.close()
