"""Manage .claude/settings.json and CLAUDE.md for Claude Code integration."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

CLAUDE_MD_SECTION = """
## Vibe Linter

This project uses vibe-linter for workflow management. When working on tasks:

1. Check current workflow status using the `vibe_get_status` MCP tool
2. Submit work output using `vibe_submit_output` when a step is complete
3. Follow the edit policies — some files may be restricted during certain steps
4. Use `vibe_get_context` to understand the current task requirements
"""


def ensure_claude_settings(cwd: str) -> None:
    claude_dir = Path(cwd) / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    settings = {}
    if settings_path.exists():
        with contextlib.suppress(Exception):
            settings = json.loads(settings_path.read_text(encoding="utf-8"))

    changed = False

    settings.setdefault("mcpServers", {})
    if "vibe-linter" not in settings["mcpServers"]:
        settings["mcpServers"]["vibe-linter"] = {"command": "vibe", "args": ["mcp-server"]}
        changed = True

    settings.setdefault("hooks", {})
    if "PreToolUse" not in settings["hooks"]:
        settings["hooks"]["PreToolUse"] = [{
            "matcher": "Edit|MultiEdit|Write",
            "hooks": [{"type": "command", "command": "vibe check-edit"}],
        }]
        changed = True
    if "SessionStart" not in settings["hooks"]:
        settings["hooks"]["SessionStart"] = [{
            "hooks": [{"type": "command", "command": "vibe inject-context"}],
        }]
        changed = True

    if changed:
        settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        print("✓ .claude/settings.json configured")

    claude_md_path = Path(cwd) / "CLAUDE.md"
    existing = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    if "vibe-linter" not in existing:
        claude_md_path.write_text(existing + CLAUDE_MD_SECTION, encoding="utf-8")
        print("✓ CLAUDE.md updated")
