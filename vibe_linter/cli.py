"""Thin CLI router — dispatches to commands and internal hooks."""
from __future__ import annotations

import os
import sys

USAGE = """\
vibe-linter — workflow system for Claude Code

Usage:
  vibe load <flow>       Compile workflow, validate, output Mermaid diagram
  vibe start             Start (or resume) loaded workflow, Claude Code takes over
  vibe stop              Stop workflow, remove all constraints on Claude Code
  vibe status            View current status (for debugging)
  vibe reset             Clear state, start fresh (redefine or switch workflows)

Internal (called automatically by hooks/MCP):
  vibe mcp-server        Start MCP Server
  vibe check-edit        Edit policy check (PreToolUse hook)
  vibe inject-context    Inject context (SessionStart hook)
"""


def main():
    args = sys.argv[1:]
    cwd = os.getcwd()
    command = args[0] if args else None

    if command == "load":
        if len(args) < 2:
            print("Usage: vibe load <flow-name>", file=sys.stderr)
            sys.exit(1)
        from vibe_linter.commands.load import cmd_load
        cmd_load(args[1], cwd)

    elif command == "start":
        from vibe_linter.commands.start import cmd_start
        cmd_start(cwd)

    elif command == "status":
        from pathlib import Path

        from vibe_linter.engine import Executor
        executor = Executor(Path(cwd) / ".vibe")
        try:
            st = executor.get_status()
            print(st["summary"])
            if st.get("last_action"):
                la = st["last_action"]
                print(f'Last action: {la["action"]} at {la["timestamp"]}')
        except Exception as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        finally:
            executor.close()

    elif command == "stop":
        from vibe_linter.commands.stop import cmd_stop
        cmd_stop(cwd)

    elif command == "reset":
        from vibe_linter.commands.reset import cmd_reset
        cmd_reset(cwd)

    elif command == "mcp-server":
        from vibe_linter.integrations.mcp_server import run_server
        run_server()

    elif command == "check-edit":
        from vibe_linter.integrations.check_edit import check_edit
        check_edit()

    elif command == "inject-context":
        from vibe_linter.integrations.inject_context import inject_context
        inject_context()

    elif command in ("help", "--help", "-h", None):
        print(USAGE)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(USAGE)
        sys.exit(1)
