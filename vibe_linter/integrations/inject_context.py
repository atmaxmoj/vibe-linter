"""SessionStart hook — inject current workflow status into Claude Code."""
from __future__ import annotations

import os

from vibe_linter.engine import Executor


def inject_context():
    vibe_dir = os.path.join(os.getcwd(), ".vibe")
    executor = Executor(vibe_dir)
    try:
        st = executor.get_status()
        if st.get("status") == "stopped":
            print("[vibe-linter] Workflow is stopped. No constraints active. Run `vibe start` to resume.")
            return
        lines = [
            f'[vibe-linter] {st["summary"]}',
            f'Available actions: {", ".join(st["allowed_actions"])}',
        ]
        if st.get("node"):
            lines.append(f'Node types: {", ".join(st["node"]["types"])}')
        lines.append("")
        lines.append("Use the vibe_get_status tool for details, and vibe_submit_output to submit output.")
        print("\n".join(lines))
    except Exception:
        pass
    finally:
        executor.close()
