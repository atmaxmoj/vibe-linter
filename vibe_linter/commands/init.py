"""Initialize a vibe-linter project.

Creates .vibe/ directory and copies a workflow template.
"""
from __future__ import annotations

import shutil
from pathlib import Path

# Templates bundled with the package
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

TEMPLATES = {
    "tdd": ("tdd.yaml", "Test-Driven Development (Red-Green-Refactor)"),
    "bugfix": ("bugfix.yaml", "Quick Bugfix (reproduce, fix, verify)"),
    "feature": ("feature.yaml", "Simple Feature Development"),
}


def list_templates() -> list[tuple[str, str, str]]:
    """Return list of (key, filename, description) for available templates."""
    return [(k, v[0], v[1]) for k, v in TEMPLATES.items()]


def init_project(template: str | None = None, target_dir: Path | None = None) -> str:
    """Initialize a vibe-linter project.

    Args:
        template: Template key (tdd, bugfix, feature) or None for interactive
        target_dir: Target directory (default: current directory)

    Returns:
        Success message
    """
    target = target_dir or Path.cwd()
    vibe_dir = target / ".vibe"
    flows_dir = vibe_dir / "flows"
    nodes_dir = vibe_dir / "nodes"

    # Check if already initialized
    if vibe_dir.exists():
        return f"Already initialized: {vibe_dir} exists"

    # Interactive template selection if not specified
    if template is None:
        print("\nAvailable workflow templates:")
        templates = list_templates()
        for i, (key, _, desc) in enumerate(templates, 1):
            print(f"  {i}. {key}: {desc}")
        print()

        choice = input("Select template [1]: ").strip() or "1"
        try:
            idx = int(choice) - 1
            template = templates[idx][0] if 0 <= idx < len(templates) else "tdd"
        except ValueError:
            # Maybe they typed the key directly
            template = choice if choice in TEMPLATES else "tdd"

    # Validate template
    if template not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        return f"Unknown template: {template}. Available: {available}"

    # Create directories
    flows_dir.mkdir(parents=True, exist_ok=True)
    nodes_dir.mkdir(parents=True, exist_ok=True)

    # Copy template
    template_file = TEMPLATES_DIR / TEMPLATES[template][0]
    if not template_file.exists():
        return f"Template file not found: {template_file}"

    dest_file = flows_dir / TEMPLATES[template][0]
    shutil.copy(template_file, dest_file)

    # Create empty __init__.py for nodes
    (nodes_dir / "__init__.py").touch()

    return f"""Initialized vibe-linter project:
  {vibe_dir}/
  ├── flows/
  │   └── {TEMPLATES[template][0]}
  └── nodes/

Next steps:
  1. Run: vibe setup    # Configure Claude Code hooks
  2. Run: vibe load {TEMPLATES[template][0]}
  3. Run: vibe start
  4. Start working with Claude Code!
"""


def main(args: list[str]) -> int:
    """CLI entry point."""
    template = args[0] if args else None
    result = init_project(template)
    print(result)
    return 0
