"""Parse YAML workflow definitions into a transition graph."""
from __future__ import annotations

import yaml

from vibe_linter.types import FlowDefinition, StepDefinition, Transition

# Chinese keyword -> internal key mapping
KEYWORD_MAP = {
    "步骤": "steps",
    "名称": "name",
    "描述": "description",
    "分支": "branch",
    "如果": "if",
    "否则": "else",
    "循环": "loop",
    "遍历": "iterate",
    "等待": "wait",
    "跳转": "jump",
    "断言": "assert",
    "条件": "condition",
    "终止": "terminate",
    "目标": "target",
    "原因": "reason",
    "子步骤": "children",
    "类型": "type",
    "配置": "config",
    "失败跳转": "onFail",
    "重试": "retry",
    "次数": "count",
    "下一步": "next",
    "去": "go",
}


def _normalize_key(key: str) -> str:
    return KEYWORD_MAP.get(key, key)


def _normalize(obj):
    if isinstance(obj, dict):
        return {_normalize_key(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(item) for item in obj]
    return obj


def _infer_step_type(body: dict) -> str:
    if "type" in body:
        return body["type"]
    if "branch" in body or ("if" in body and "children" not in body and "steps" not in body):
        return "branch"
    if "loop" in body or "iterate" in body:
        return "loop"
    if "wait" in body:
        return "wait"
    if "jump" in body or ("target" in body and "condition" not in body):
        return "jump"
    if "assert" in body or "condition" in body:
        return "assert"
    if "terminate" in body:
        return "terminate"
    return "task"


def _parse_raw_step(raw) -> tuple[str, dict]:
    """Parse a single raw YAML step into (name, body_dict)."""
    if isinstance(raw, str):
        return (raw, {})

    normalized = _normalize(raw)
    if not isinstance(normalized, dict):
        return ("unnamed", {})

    if "name" in normalized:
        return (normalized["name"], normalized)

    keys = list(normalized.keys())
    if len(keys) == 1:
        name = keys[0]
        body = normalized[name]
        if body is None:
            return (name, {})
        if isinstance(body, dict):
            return (name, body)

    return ("unnamed", normalized)


# Keys consumed by the parser, not forwarded to config
_CONSUMED_KEYS = frozenset({
    "steps", "children", "name", "type", "next", "if", "else",
    "condition", "onFail", "target", "iterate", "go", "assert",
    "wait", "jump", "terminate", "branch", "reason",
})


def _process_steps(
    raw_steps: list,
    all_steps: dict[str, StepDefinition],
    next_after: str | None = None,
) -> None:
    """Flatten raw steps into all_steps dict with explicit transitions."""
    parsed = [_parse_raw_step(raw) for raw in raw_steps]

    for idx, (name, body) in enumerate(parsed):
        implicit_next = parsed[idx + 1][0] if idx + 1 < len(parsed) else next_after
        step_type = _infer_step_type(body)
        config: dict = {}
        transitions: list[Transition] = []
        has_explicit_next = "next" in body
        children_raw = body.get("steps") or body.get("children") or []

        # ── Pass 1: set config flags from step type ──
        if step_type == "wait":
            config["wait"] = True
        elif step_type == "terminate":
            config["terminate"] = True
            reason = body.get("reason", "")
            if reason:
                config["reason"] = reason

        # ── Pass 2: determine transitions ──
        # Priority: loop/branch children > explicit next > type-specific sugar > implicit next

        if step_type == "loop" and children_raw:
            iterate_expr = body.get("iterate")
            if iterate_expr:
                config["iterate"] = iterate_expr
            _process_steps(children_raw, all_steps, next_after=name)
            first_child = _parse_raw_step(children_raw[0])[0]
            transitions.append(Transition(target=first_child))
            if implicit_next:
                transitions.append(Transition(target=implicit_next))

        elif step_type == "branch" and children_raw:
            config["auto"] = True
            condition = body.get("if") or body.get("condition")
            _process_steps(children_raw, all_steps, next_after=implicit_next)
            first_child = _parse_raw_step(children_raw[0])[0]
            if condition:
                transitions.append(Transition(target=first_child, condition=condition))
            else:
                transitions.append(Transition(target=first_child))
            if implicit_next:
                transitions.append(Transition(target=implicit_next))

        elif has_explicit_next:
            _parse_explicit_transitions(body["next"], transitions)

        elif step_type == "terminate":
            pass  # no transitions

        elif step_type == "assert":
            config["auto"] = True
            condition = body.get("condition") or body.get("assert")
            fail_target = body.get("onFail") or body.get("target")
            if condition:
                if implicit_next:
                    transitions.append(Transition(target=implicit_next, condition=condition))
                if fail_target:
                    transitions.append(Transition(target=fail_target))
            elif implicit_next:
                transitions.append(Transition(target=implicit_next))

        elif step_type == "jump":
            config["auto"] = True
            target = body.get("target")
            if target:
                transitions.append(Transition(target=target))

        else:
            if implicit_next:
                transitions.append(Transition(target=implicit_next))

        # Forward remaining config
        for k, v in body.items():
            if k not in _CONSUMED_KEYS:
                config[k] = v

        all_steps[name] = StepDefinition(name=name, transitions=transitions, config=config)


def _parse_explicit_transitions(next_def, transitions: list[Transition]) -> None:
    """Parse explicit `next:` definitions into Transition objects."""
    if isinstance(next_def, str):
        transitions.append(Transition(target=next_def))
    elif isinstance(next_def, list):
        for item in next_def:
            if isinstance(item, dict):
                condition = item.get("if") or item.get("condition")
                target = item.get("go") or item.get("target")
                if target:
                    transitions.append(Transition(target=target, condition=condition))
            elif isinstance(item, str):
                transitions.append(Transition(target=item))


def parse_flow_yaml(content: str) -> FlowDefinition:
    raw = yaml.safe_load(content)
    if not isinstance(raw, dict):
        raise ValueError("Invalid YAML: expected a mapping")

    normalized = _normalize(raw)

    name = normalized.get("name", "unnamed flow")
    description = normalized.get("description", "")
    raw_steps = normalized.get("steps")

    if not isinstance(raw_steps, list):
        raise ValueError('Invalid flow: missing "steps" list')

    # Check for duplicate names before processing
    all_names = _collect_all_names(raw_steps)
    seen: dict[str, int] = {}
    for n in all_names:
        seen[n] = seen.get(n, 0) + 1
    dupes = [n for n, c in seen.items() if c > 1]
    if dupes:
        raise ValueError(f"Duplicate step names: {', '.join(dupes)}")

    steps: dict[str, StepDefinition] = {}
    _process_steps(raw_steps, steps)

    entry = next(iter(steps)) if steps else ""
    return FlowDefinition(name=name, description=description, steps=steps, entry=entry)


def _collect_all_names(raw_steps: list) -> list[str]:
    """Recursively collect all step names from raw YAML."""
    names: list[str] = []
    for raw in raw_steps:
        name, body = _parse_raw_step(raw)
        names.append(name)
        children = body.get("steps") or body.get("children") if isinstance(body, dict) else None
        if not children:
            normalized = _normalize(body) if isinstance(body, dict) else {}
            children = normalized.get("steps") or normalized.get("children")
        if isinstance(children, list):
            names.extend(_collect_all_names(children))
    return names
