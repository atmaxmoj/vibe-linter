from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# ─── Flow Definition IR (parsed from YAML) ───

@dataclass
class Transition:
    target: str
    condition: str | None = None  # None = default/unconditional

@dataclass
class StepDefinition:
    name: str
    transitions: list[Transition] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    # config keys used by the engine:
    #   wait: True        → engine pauses for approval
    #   terminate: True   → engine ends flow (optional "reason")
    #   iterate: "expr"   → loop header, engine manages iteration
    #   auto: True        → engine auto-evaluates transitions (assert/branch/jump)

@dataclass
class FlowDefinition:
    name: str
    description: str = ""
    steps: dict[str, StepDefinition] = field(default_factory=dict)
    entry: str = ""

# ─── Edit Policy ───

@dataclass
class EditPolicyPattern:
    glob: str
    policy: str  # silent | warn | block

@dataclass
class EditPolicy:
    default: str = "silent"  # silent | warn | block
    patterns: list[EditPolicyPattern] = field(default_factory=list)

# ─── Node Definition (loaded from .py files) ───

@dataclass
class NodeDefinition:
    name: str = ""
    types: list[str] = field(default_factory=list)
    instructions: str = ""  # Claude reads this to know what to do
    schema: dict[str, dict[str, str]] | None = None
    check: Callable[[Any], bool | str] | None = None
    edit_policy: EditPolicy | None = None
    archive: dict[str, str] | None = None

# ─── Workflow Runtime State ───

@dataclass
class WorkflowState:
    flow_name: str
    current_step: str
    status: str = "running"  # running | waiting | paused | done
    data: dict[str, Any] = field(default_factory=dict)
    loop_state: dict[str, Any] = field(default_factory=dict)  # {loop_name: {"i": N, "n": M}}
    started_at: str = ""
