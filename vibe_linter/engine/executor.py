"""Core workflow executor — graph-based state machine.

Condition evaluation has three modes:
  1. Expression:   "tests_pass == true"       → engine evaluates
  2. Eval node:    "@check_coverage"           → user-defined function evaluates
  3. LLM:          "design covers all cases"   → Claude evaluates, submits _goto
"""
from __future__ import annotations

import contextlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibe_linter.compiler.parser import parse_flow_yaml
from vibe_linter.engine.expression import evaluate_condition, evaluate_expression
from vibe_linter.engine.node_loader import get_node, load_nodes
from vibe_linter.store.state import StateManager
from vibe_linter.types import FlowDefinition, StepDefinition, Transition, WorkflowState

# ─── Condition classification ───

_EXPRESSION_OPS = re.compile(r"===|!==|==|!=|>=|<=|>|<")
_SIMPLE_IDENT = re.compile(r"^[\w.]+(\[\d+\])?$")


def _classify_condition(condition: str) -> str:
    """Classify a transition condition string.

    Returns "eval_node", "expression", or "llm".
    """
    c = condition.strip()
    if c.startswith("@"):
        return "eval_node"
    if _EXPRESSION_OPS.search(c):
        return "expression"
    if _SIMPLE_IDENT.match(c):
        return "expression"
    return "llm"


def _eval_node_condition(condition: str, data: dict[str, Any]) -> bool:
    """Evaluate an @node("eval") condition."""
    node_name = condition.strip().lstrip("@")
    node_def = get_node(node_name)
    if node_def and node_def.check:
        result = node_def.check(data)
        return result is True
    return False


# ─── Result type ───

class SubmitResult:
    def __init__(self, success: bool, message: str, new_step: str | None = None):
        self.success = success
        self.message = message
        self.new_step = new_step

    def __bool__(self) -> bool:
        return self.success

    def to_dict(self) -> dict:
        return {"success": self.success, "message": self.message, "new_step": self.new_step}


# ─── Executor ───

class Executor:
    def __init__(self, vibe_dir: str | Path):
        self.vibe_dir = Path(vibe_dir)
        self.state_manager = StateManager(self.vibe_dir / "state.db")
        self.flow: FlowDefinition | None = None

    def start(self, flow_name: str, initial_data: dict[str, Any] | None = None) -> str:
        flow_path = self.vibe_dir / "flows" / f"{flow_name}.yaml"
        self.flow = parse_flow_yaml(flow_path.read_text(encoding="utf-8"))
        self._load_nodes()

        if not self.flow.steps:
            raise ValueError("Flow has no steps")

        entry = self.flow.entry
        state = WorkflowState(
            flow_name=flow_name,
            current_step=entry,
            status="running",
            data=dict(initial_data or {}),
            started_at=datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.state_manager.init_state(state)
        self.state_manager.add_history(flow_name, entry, "start")

        # Auto-advance if entry is a control-flow step
        step = self.flow.steps[entry]
        if self._should_auto_advance(step):
            result = self._auto_advance()
            return f'Flow "{self.flow.name}" started → {result.message}'

        if step.config.get("wait"):
            self.state_manager.update_state(status="waiting")

        return f'Flow "{self.flow.name}" started, current step: {entry}'

    def get_status(self) -> dict[str, Any]:
        state = self._require_state()
        flow = self._ensure_flow()
        step = flow.steps.get(state.current_step)
        node_def = get_node(state.current_step) if step else None

        allowed = ["submit", "skip"]
        if state.status == "waiting":
            allowed.extend(["approve", "reject"])
        allowed.extend(["back", "goto", "retry"])

        elapsed = _format_elapsed(state.started_at)
        history = self.state_manager.get_history(1)
        last_action = history[0] if history else None
        display_path = self._build_display_path(state)

        result: dict[str, Any] = {
            "flow_name": flow.name,
            "current_step": state.current_step,
            "display_path": display_path,
            "total_steps": len(flow.steps),
            "status": state.status,
            "elapsed": elapsed,
            "last_action": last_action,
            "allowed_actions": allowed,
            "data": state.data,
        }

        # One-line summary
        summary_parts = [f"{flow.name} > {display_path}"]
        if state.status == "waiting":
            summary_parts.append("waiting for approval")
        if elapsed:
            summary_parts.append(f"elapsed {elapsed}")
        if last_action:
            summary_parts.append(f"last: {last_action['action']}")
        result["summary"] = ", ".join(summary_parts)

        # Pending LLM decisions — transitions Claude needs to evaluate
        if step:
            decisions = _collect_llm_decisions(step.transitions)
            if decisions:
                result["pending_decisions"] = decisions
                result["decision_hint"] = (
                    "This step has conditions that require your judgment. "
                    "Evaluate the situation, then submit with {\"_goto\": \"step_name\"} "
                    "to choose a path."
                )

        if node_def:
            result["node"] = {
                "name": node_def.name,
                "types": node_def.types,
                "instructions": node_def.instructions or None,
                "edit_policy": node_def.edit_policy.__dict__ if node_def.edit_policy else None,
            }
        return result

    def submit(self, data: dict[str, Any]) -> SubmitResult:
        state = self._require_state()
        if state.status == "done":
            return SubmitResult(
                False,
                "Workflow is already completed. Use vibe_goto to jump to a step if you need to revisit.",
            )
        if state.status == "stopped":
            return SubmitResult(
                False,
                "Workflow is stopped. Run `vibe start` to resume before submitting.",
            )
        if state.status == "waiting":
            return SubmitResult(
                False,
                f'Step "{state.current_step}" is waiting for human approval. '
                "Use vibe_approve to continue or vibe_reject to reject.",
            )

        flow = self._ensure_flow()
        step = flow.steps.get(state.current_step)
        if not step:
            return SubmitResult(
                False,
                f'Step "{state.current_step}" not found in flow definition. '
                "The workflow YAML may have changed. Use vibe_goto to jump to a valid step.",
            )

        # Node validation + archival
        node_def = get_node(step.name)
        if node_def:
            if "validate" in node_def.types and node_def.check:
                check_result = node_def.check(data)
                if check_result is not True:
                    return SubmitResult(
                        False,
                        f'Output rejected by step "{step.name}": {check_result}. '
                        "Please fix the issues and resubmit.",
                    )
            if "archive" in node_def.types and node_def.archive:
                try:
                    if node_def.schema and "output" in node_def.schema:
                        self.state_manager.create_table(node_def.archive["table"], node_def.schema["output"])
                    self.state_manager.insert_row(node_def.archive["table"], data)
                except Exception as e:
                    return SubmitResult(False, f"Failed to archive output: {e}")

        # Explicit _goto — Claude chose a transition path
        goto_target = data.pop("_goto", None)

        # Store data and record
        new_data = {**state.data, step.name: data}
        self.state_manager.update_state(data=new_data)
        self.state_manager.add_history(
            state.flow_name, step.name, "submit", json.dumps(data, ensure_ascii=False)
        )

        if goto_target:
            if goto_target not in flow.steps:
                return SubmitResult(
                    False,
                    f'_goto target "{goto_target}" not found. '
                    f"Available steps: {', '.join(flow.steps)}",
                )
            return self._move_to(goto_target)

        return self._follow_transitions(step)

    def skip(self, reason: str | None = None) -> SubmitResult:
        state = self._require_state()
        flow = self._ensure_flow()
        step = flow.steps.get(state.current_step)
        if not step:
            return SubmitResult(False, f'Current step "{state.current_step}" not found in flow.')
        self.state_manager.add_history(state.flow_name, state.current_step, "skip", reason)
        self.state_manager.update_state(status="running")
        return self._follow_transitions(step)

    def retry(self) -> SubmitResult:
        state = self._require_state()
        self.state_manager.update_state(status="running")
        self.state_manager.add_history(state.flow_name, state.current_step, "retry")
        return SubmitResult(True, f'Retrying step "{state.current_step}". Please attempt it again.')

    def approve(self, data: dict[str, Any] | None = None) -> SubmitResult:
        state = self._require_state()
        if state.status != "waiting":
            return SubmitResult(
                False,
                f'Step "{state.current_step}" is not waiting for approval (status: {state.status}).',
            )
        self.state_manager.update_state(status="running")
        self.state_manager.add_history(state.flow_name, state.current_step, "approve")
        return self.submit(data or {})

    def reject(self, reason: str | None = None) -> SubmitResult:
        state = self._require_state()
        if state.status != "waiting":
            return SubmitResult(
                False,
                f'Step "{state.current_step}" is not waiting for approval (status: {state.status}).',
            )
        self.state_manager.add_history(state.flow_name, state.current_step, "reject", reason)
        return SubmitResult(True, f"Rejected: {reason or 'no reason given'}")

    def goto(self, target_name: str) -> SubmitResult:
        state = self._require_state()
        flow = self._ensure_flow()
        if target_name not in flow.steps:
            return SubmitResult(
                False,
                f'Step "{target_name}" not found. '
                f"Available steps: {', '.join(flow.steps)}",
            )
        self.state_manager.update_state(current_step=target_name, status="running")
        self.state_manager.add_history(state.flow_name, target_name, "goto")
        return SubmitResult(True, f"Jumped to: {target_name}", target_name)

    def back(self) -> SubmitResult:
        state = self._require_state()
        history = self.state_manager.get_history(20)
        for entry in history:
            if entry["step_path"] != state.current_step:
                target = entry["step_path"]
                self.state_manager.update_state(current_step=target, status="running")
                self.state_manager.add_history(state.flow_name, target, "back")
                return SubmitResult(True, f"Moved back to: {target}", target)
        return SubmitResult(False, "Cannot go back — no previous step in history.")

    def stop(self) -> SubmitResult:
        state = self._require_state()
        if state.status == "done":
            return SubmitResult(False, "Workflow already completed.")
        if state.status == "stopped":
            return SubmitResult(False, "Workflow already stopped.")
        self.state_manager.update_state(status="stopped")
        self.state_manager.add_history(state.flow_name, state.current_step, "stop")
        return SubmitResult(True, f"Workflow stopped at: {state.current_step}")

    def resume(self) -> SubmitResult:
        state = self._require_state()
        if state.status != "stopped":
            return SubmitResult(False, f"Cannot resume: status is {state.status}.")
        flow = self._ensure_flow()
        step = flow.steps.get(state.current_step)
        new_status = "waiting" if step and step.config.get("wait") else "running"
        self.state_manager.update_state(status=new_status)
        self.state_manager.add_history(state.flow_name, state.current_step, "resume")
        return SubmitResult(True, f"Resumed at: {state.current_step}", state.current_step)

    def get_history(self, limit: int = 20) -> list[dict]:
        return self.state_manager.get_history(limit)

    def get_data(self) -> dict[str, Any]:
        state = self.state_manager.get_current_state()
        return state.data if state else {}

    def close(self) -> None:
        self.state_manager.close()

    # ─── Private ───

    def _require_state(self) -> WorkflowState:
        state = self.state_manager.get_current_state()
        if not state:
            raise RuntimeError("No active workflow. Run `vibe start` first.")
        return state

    def _load_nodes(self) -> None:
        with contextlib.suppress(Exception):
            load_nodes(self.vibe_dir / "nodes")

    def _ensure_flow(self) -> FlowDefinition:
        if self.flow:
            return self.flow
        state = self._require_state()
        flow_path = self.vibe_dir / "flows" / f"{state.flow_name}.yaml"
        self.flow = parse_flow_yaml(flow_path.read_text(encoding="utf-8"))
        self._load_nodes()
        return self.flow

    def _build_display_path(self, state: WorkflowState) -> str:
        parts: list[str] = []
        for loop_name, info in state.loop_state.items():
            if isinstance(info, dict):
                parts.append(f"{loop_name}[{info['i'] + 1}/{info['n']}]")
        parts.append(state.current_step)
        return " > ".join(parts)

    def _build_context(self, state: WorkflowState) -> dict[str, Any]:
        ctx = dict(state.data)
        for k, v in state.loop_state.items():
            ctx[k] = v["i"] if isinstance(v, dict) else v
        return ctx

    def _should_auto_advance(self, step: StepDefinition) -> bool:
        """Can this step auto-advance without waiting for input?"""
        if step.config.get("iterate"):
            return True
        if not step.config.get("auto"):
            return False
        # Auto step, but only if all conditions are programmatic (no LLM)
        return all(
            t.condition is None or _classify_condition(t.condition) != "llm"
            for t in step.transitions
        )

    def _follow_transitions(self, step: StepDefinition) -> SubmitResult:
        """Evaluate transitions: programmatic first, then LLM, then default."""
        state = self._require_state()
        self._ensure_flow()
        ctx = self._build_context(state)

        # Pass 1: try programmatic conditions (expression + eval_node)
        for t in step.transitions:
            if t.condition is None:
                continue
            ctype = _classify_condition(t.condition)
            if ctype == "expression" and evaluate_condition(t.condition, ctx):
                return self._move_to(t.target)
            if ctype == "eval_node" and _eval_node_condition(t.condition, state.data):
                return self._move_to(t.target)

        # Pass 2: check for unresolved LLM conditions
        llm_decisions = _collect_llm_decisions(step.transitions)
        if llm_decisions:
            # Can't auto-resolve — present to Claude
            options = ", ".join(f'"{d["target"]}"' for d in llm_decisions)
            return SubmitResult(
                True,
                f'Step "{step.name}" has conditions that need your judgment. '
                f"Evaluate the situation and submit with "
                f'{{"_goto": <one of {options}>}} to choose a path.',
                step.name,
            )

        # Pass 3: default transition (no condition)
        for t in step.transitions:
            if t.condition is None:
                return self._move_to(t.target)

        if not step.transitions:
            self.state_manager.update_state(status="done")
            return SubmitResult(True, "Workflow completed — no more transitions from this step.")
        return SubmitResult(
            False,
            f'No matching transition from step "{step.name}". '
            "None of the conditions were met and there is no default path.",
        )

    def _move_to(self, target_name: str) -> SubmitResult:
        state = self._require_state()
        flow = self._ensure_flow()
        target = flow.steps.get(target_name)
        if not target:
            return SubmitResult(
                False,
                f'Target step "{target_name}" not found in the flow. '
                "The workflow YAML may have changed.",
            )

        # Loop header
        if "iterate" in target.config:
            return self._handle_loop(target)

        # Terminate
        if target.config.get("terminate"):
            reason = target.config.get("reason", "workflow completed")
            self.state_manager.update_state(current_step=target_name, status="done")
            self.state_manager.add_history(state.flow_name, target_name, "terminate", reason)
            return SubmitResult(True, f"Workflow completed: {reason}")

        # Regular step
        new_status = "waiting" if target.config.get("wait") else "running"
        self.state_manager.update_state(current_step=target_name, status=new_status)
        self.state_manager.add_history(state.flow_name, target_name, "transition")

        # Auto-advance if all conditions are programmatic
        if self._should_auto_advance(target):
            return self._auto_advance()

        return SubmitResult(True, f"Advanced to: {target_name}", target_name)

    def _auto_advance(self) -> SubmitResult:
        state = self._require_state()
        flow = self._ensure_flow()
        step = flow.steps.get(state.current_step)
        if not step:
            return SubmitResult(False, f'Step "{state.current_step}" not found.')
        return self._follow_transitions(step)

    def _handle_loop(self, loop_step: StepDefinition) -> SubmitResult:
        state = self._require_state()
        loop_name = loop_step.name
        info = state.loop_state.get(loop_name)

        if info is None:
            ctx = self._build_context(state)
            items = evaluate_expression(loop_step.config["iterate"], ctx)
            if not isinstance(items, list) or not items:
                if len(loop_step.transitions) > 1:
                    return self._move_to(loop_step.transitions[1].target)
                self.state_manager.update_state(status="done")
                return SubmitResult(True, f"Loop skipped (empty): {loop_name}")

            new_loop_state = {**state.loop_state, loop_name: {"i": 0, "n": len(items)}}
            self.state_manager.update_state(loop_state=new_loop_state)
            return self._move_to(loop_step.transitions[0].target)
        else:
            i = info["i"] + 1
            n = info["n"]
            if i < n:
                new_loop_state = {**state.loop_state, loop_name: {"i": i, "n": n}}
                self.state_manager.update_state(loop_state=new_loop_state)
                return self._move_to(loop_step.transitions[0].target)
            else:
                new_loop_state = {k: v for k, v in state.loop_state.items() if k != loop_name}
                self.state_manager.update_state(loop_state=new_loop_state)
                if len(loop_step.transitions) > 1:
                    return self._move_to(loop_step.transitions[1].target)
                self.state_manager.update_state(status="done")
                return SubmitResult(True, f"Loop completed: {loop_name}")


# ─── Helpers ───

def _collect_llm_decisions(transitions: list[Transition]) -> list[dict[str, str]]:
    """Extract transitions with LLM-evaluated conditions."""
    decisions: list[dict[str, str]] = []
    for t in transitions:
        if t.condition and _classify_condition(t.condition) == "llm":
            decisions.append({"target": t.target, "description": t.condition})
    return decisions


def _format_elapsed(started_at: str) -> str:
    if not started_at:
        return ""
    try:
        start = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        delta = datetime.now(tz=UTC) - start
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m"
    except ValueError:
        return ""
