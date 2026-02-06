"""vibe reset — clear state, allow redefining or switching workflows."""
from __future__ import annotations

from pathlib import Path

from vibe_linter.store.state import StateManager


def cmd_reset(cwd: str):
    vibe_dir = Path(cwd) / ".vibe"
    db_path = vibe_dir / "state.db"

    if not db_path.exists():
        print("Nothing to reset — no state database found.")
        return

    mgr = StateManager(db_path)
    try:
        state = mgr.get_current_state()
        if state:
            print(f'Clearing workflow "{state.flow_name}" (was at: {state.current_step})')
        mgr.reset()
    finally:
        mgr.close()

    loaded_path = vibe_dir / ".loaded"
    if loaded_path.exists():
        loaded_path.unlink()

    print("State cleared. You can now `vibe load <flow>` to start a new workflow.")
