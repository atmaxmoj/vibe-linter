"""Load node definitions from .py files in .vibe/nodes/."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

if TYPE_CHECKING:
    from collections.abc import Callable

_NODE_REGISTRY: dict[str, NodeDefinition] = {}


def node(*types: str):
    """Factory function for defining nodes.

    Usage in .vibe/nodes/confirm_root_cause.py::

        from vibe_linter import node

        @node("validate", "archive")
        def confirm_root_cause():
            return {
                "schema": {"output": {"root_cause": "string", "evidence": "string[]"}},
                "check": lambda output: True if output.get("evidence") else "must have log evidence",
                "archive": {"table": "root_causes"},
            }
    """
    def decorator(fn: Callable[[], dict[str, Any]]) -> NodeDefinition:
        config = fn()
        edit_policy = None
        if "edit_policy" in config:
            ep = config["edit_policy"]
            patterns = [EditPolicyPattern(**p) for p in ep.get("patterns", [])]
            edit_policy = EditPolicy(default=ep.get("default", "silent"), patterns=patterns)

        return NodeDefinition(
            name=fn.__name__,
            types=list(types),
            instructions=config.get("instructions", ""),
            schema=config.get("schema"),
            check=config.get("check"),
            edit_policy=edit_policy,
            archive=config.get("archive"),
        )
    return decorator


def load_nodes(nodes_dir: str | Path) -> dict[str, NodeDefinition]:
    _NODE_REGISTRY.clear()
    nodes_path = Path(nodes_dir)
    if not nodes_path.is_dir():
        return _NODE_REGISTRY

    for py_file in nodes_path.glob("*.py"):
        try:
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if isinstance(obj, NodeDefinition):
                    if not obj.name:
                        obj.name = py_file.stem
                    _NODE_REGISTRY[obj.name] = obj
        except Exception as e:
            print(f"Warning: failed to load node {py_file}: {e}")

    return dict(_NODE_REGISTRY)


def get_node(name: str) -> NodeDefinition | None:
    return _NODE_REGISTRY.get(name)
