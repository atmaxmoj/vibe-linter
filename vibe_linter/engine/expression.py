"""Template expression evaluator for {{expr}} syntax."""
from __future__ import annotations

import re
from typing import Any

TEMPLATE_RE = re.compile(r"\{\{(.+?)\}\}")


def evaluate_template(template: str, context: dict[str, Any]) -> str:
    def replacer(m: re.Match) -> str:
        val = evaluate_expression(m.group(1).strip(), context)
        return "" if val is None else str(val)
    return TEMPLATE_RE.sub(replacer, template)


def evaluate_expression(expr: str, context: dict[str, Any]) -> Any:
    expr = expr.strip()

    for op in ("===", "!==", ">=", "<=", "==", "!=", ">", "<"):
        idx = expr.find(op)
        if idx != -1:
            left = evaluate_expression(expr[:idx], context)
            right = evaluate_expression(expr[idx + len(op):], context)
            match op:
                case "===" | "==":
                    return left == right
                case "!==" | "!=":
                    return left != right
                case ">":
                    return left > right
                case "<":
                    return left < right
                case ">=":
                    return left >= right
                case "<=":
                    return left <= right

    if expr == "true":
        return True
    if expr == "false":
        return False
    if re.match(r"^-?\d+(\.\d+)?$", expr):
        return float(expr) if "." in expr else int(expr)
    if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
        return expr[1:-1]

    return _resolve_path(expr, context)


def _resolve_path(path: str, context: dict[str, Any]) -> Any:
    current: Any = context
    for part in path.split("."):
        if current is None:
            return None
        bracket = re.match(r"^(\w+)\[(\d+)\]$", part)
        if bracket:
            current = current.get(bracket.group(1)) if isinstance(current, dict) else getattr(current, bracket.group(1), None)
            if isinstance(current, list):
                current = current[int(bracket.group(2))]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    return bool(evaluate_expression(condition, context))
