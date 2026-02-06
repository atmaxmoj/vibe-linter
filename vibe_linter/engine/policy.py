"""Edit policy checker — glob match file paths against node policies."""
from __future__ import annotations

from fnmatch import fnmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe_linter.types import EditPolicy


def check_edit_policy(file_path: str, policy: EditPolicy | None) -> str:
    """Returns 'silent', 'warn', or 'block'."""
    if not policy:
        return "silent"

    for pattern in policy.patterns:
        if fnmatch(file_path, pattern.glob):
            return pattern.policy

    return policy.default
