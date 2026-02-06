"""Static analysis for workflow definitions — catch issues at compile time."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe_linter.types import FlowDefinition


class ValidationError:
    def __init__(self, level: str, message: str, step: str | None = None):
        self.level = level  # "error" | "warning"
        self.message = message
        self.step = step

    def __str__(self):
        prefix = f"[{self.step}] " if self.step else ""
        return f"{self.level.upper()}: {prefix}{self.message}"


def validate_flow(flow: FlowDefinition) -> list[ValidationError]:
    """Run all static checks on a flow definition."""
    errors: list[ValidationError] = []

    if not flow.steps:
        errors.append(ValidationError("error", "Flow has no steps"))
        return errors

    if not flow.entry or flow.entry not in flow.steps:
        errors.append(ValidationError("error", "Flow has no valid entry point"))
        return errors

    errors.extend(_check_targets(flow))
    errors.extend(_check_reachability(flow))
    errors.extend(_check_dead_ends(flow))
    errors.extend(_check_loops(flow))

    return errors


def format_errors(errors: list[ValidationError]) -> str:
    if not errors:
        return ""
    lines = []
    errs = [e for e in errors if e.level == "error"]
    warns = [e for e in errors if e.level == "warning"]
    if errs:
        lines.append(f"  {len(errs)} error(s):")
        for e in errs:
            lines.append(f"    ✗ {e}")
    if warns:
        lines.append(f"  {len(warns)} warning(s):")
        for e in warns:
            lines.append(f"    ⚠ {e}")
    return "\n".join(lines)


# ─── Checks ───

def _check_targets(flow: FlowDefinition) -> list[ValidationError]:
    """Every transition target must exist in the flow."""
    errors: list[ValidationError] = []
    for step in flow.steps.values():
        for t in step.transitions:
            if t.target not in flow.steps:
                errors.append(ValidationError(
                    "error", f"Transition target not found: '{t.target}'", step.name
                ))
    return errors


def _check_reachability(flow: FlowDefinition) -> list[ValidationError]:
    """All steps should be reachable from the entry point."""
    errors: list[ValidationError] = []
    reachable: set[str] = set()
    queue = [flow.entry]

    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue
        reachable.add(current)
        step = flow.steps.get(current)
        if step:
            for t in step.transitions:
                if t.target not in reachable:
                    queue.append(t.target)

    for name in set(flow.steps) - reachable:
        errors.append(ValidationError("warning", "Step is unreachable from the start", name))

    return errors


def _check_dead_ends(flow: FlowDefinition) -> list[ValidationError]:
    """Non-terminate steps with no transitions are dead ends."""
    errors: list[ValidationError] = []
    for step in flow.steps.values():
        if step.config.get("terminate"):
            continue
        if not step.transitions:
            errors.append(ValidationError("warning", "Step has no outgoing transitions (dead end)", step.name))
    return errors


def _check_loops(flow: FlowDefinition) -> list[ValidationError]:
    """Loop headers with iterate should have a body transition (at least 2: enter + exit)."""
    errors: list[ValidationError] = []
    for step in flow.steps.values():
        if step.config.get("iterate"):
            if not step.transitions:
                errors.append(ValidationError("error", "Loop has no transitions", step.name))
            elif len(step.transitions) < 2:
                errors.append(ValidationError("error", "Loop has no body steps (empty loop)", step.name))
    return errors
