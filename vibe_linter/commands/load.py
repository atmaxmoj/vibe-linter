"""vibe load <flow> — compile workflow, validate, output Mermaid diagram."""
from __future__ import annotations

import sys
from pathlib import Path

from vibe_linter.compiler import format_errors, generate_mermaid, parse_flow_yaml, validate_flow
from vibe_linter.integrations.settings import ensure_claude_settings


def cmd_load(flow_name: str, cwd: str):
    vibe_dir = Path(cwd) / ".vibe"
    flow_path = vibe_dir / "flows" / f"{flow_name}.yaml"

    if not flow_path.exists():
        print(f"Flow file not found: {flow_path}", file=sys.stderr)
        sys.exit(1)

    try:
        flow = parse_flow_yaml(flow_path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"✗ Parse error: {e}", file=sys.stderr)
        sys.exit(1)

    # Static analysis
    errors = validate_flow(flow)
    has_errors = any(e.level == "error" for e in errors)

    if has_errors:
        print(f'✗ Flow "{flow.name}" failed validation:')
        print(format_errors(errors))
        sys.exit(1)

    print(f'✓ Flow "{flow.name}" compiled ({len(flow.steps)} steps)')
    if errors:
        print(format_errors(errors))
    print()

    # Mermaid diagram
    print("```mermaid")
    print(generate_mermaid(flow))
    print("```")
    print()

    # Configure Claude Code
    ensure_claude_settings(cwd)

    # Save loaded flow name
    meta_path = vibe_dir / ".loaded"
    meta_path.write_text(flow_name, encoding="utf-8")

    print()
    print("Once the flow looks correct, run: vibe start")
