"""Configure Claude Code integration for vibe-linter.

Sets up hooks and MCP server in .claude/settings.json.
"""
from __future__ import annotations

from pathlib import Path


def setup_claude_code(target_dir: Path | None = None) -> str:
    """Configure Claude Code for vibe-linter integration.

    Args:
        target_dir: Target directory (default: current directory)

    Returns:
        Success message
    """
    target = target_dir or Path.cwd()
    vibe_dir = target / ".vibe"

    # Check if vibe-linter is initialized
    if not vibe_dir.exists():
        return "Error: .vibe/ not found. Run 'vibe init' first."

    from vibe_linter.integrations.settings import ensure_claude_settings

    ensure_claude_settings(str(target))

    return """Claude Code integration configured:
  - MCP server: vibe-linter (provides workflow tools)
  - PreToolUse hook: edit policy enforcement
  - SessionStart hook: context injection

Next steps:
  1. Run: vibe load <workflow.yaml>
  2. Run: vibe start
  3. Start Claude Code in this directory!
"""


def main(args: list[str]) -> int:
    """CLI entry point."""
    result = setup_claude_code()
    print(result)
    return 0 if not result.startswith("Error") else 1
