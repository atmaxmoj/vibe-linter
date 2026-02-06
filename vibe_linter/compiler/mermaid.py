"""Generate Mermaid flowchart from a FlowDefinition."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe_linter.types import FlowDefinition

_counter = 0


def _make_id(name: str) -> str:
    global _counter
    _counter += 1
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return f"n{_counter}_{clean}"


def generate_mermaid(flow: FlowDefinition) -> str:
    global _counter
    _counter = 0

    ids: dict[str, str] = {}
    nodes: list[str] = []
    edges: list[str] = []

    # Assign IDs and create nodes
    for step in flow.steps.values():
        sid = _make_id(step.name)
        ids[step.name] = sid
        label = step.name.replace('"', "'")

        if step.config.get("auto"):
            # Assert / branch / jump → diamond
            nodes.append(f'    {sid}{{{{{label}}}}}')
        elif step.config.get("iterate"):
            # Loop → stadium
            nodes.append(f'    {sid}@{{ shape: stadium, label: "{label}" }}')
        elif step.config.get("wait"):
            # Wait → parallelogram
            nodes.append(f'    {sid}[/"{label}"/]')
        elif step.config.get("terminate"):
            # Terminate → double circle
            nodes.append(f'    {sid}(("{label}"))')
        else:
            # Task → rectangle
            nodes.append(f'    {sid}["{label}"]')

    # Create edges from transitions
    for step in flow.steps.values():
        src = ids.get(step.name)
        if not src:
            continue
        for i, t in enumerate(step.transitions):
            dst = ids.get(t.target)
            if not dst:
                continue

            if t.condition:
                # Conditional edge with label
                cond_label = t.condition[:30]
                edges.append(f'    {src} -->|"{cond_label}"| {dst}')
            elif step.config.get("auto") and i > 0:
                # Default/fail edge on auto step → dashed
                edges.append(f"    {src} -.-> {dst}")
            elif step.config.get("iterate"):
                if i == 0:
                    edges.append(f"    {src} --> {dst}")
                else:
                    edges.append(f'    {src} -.->|exit| {dst}')
            else:
                edges.append(f"    {src} --> {dst}")

    lines = ["graph TD"]
    lines.extend(nodes)
    lines.extend(edges)
    return "\n".join(lines)
