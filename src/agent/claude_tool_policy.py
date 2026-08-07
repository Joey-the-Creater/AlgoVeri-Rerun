"""Deny-by-default tool policy for an isolated Claude Code Lean workspace."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any


READABLE_FILES = {
    "TASK.md",
    "Solution.lean",
    "Original.lean",
    "Merged.lean",
    "check.sh",
}


def safe_inspection_command(command: str, workspace: Path) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if parts in (["pwd"], ["ls"], ["ls", "-la"], ["ls", "-al"]):
        return True
    if len(parts) == 3 and parts[:2] in (["ls", "-la"], ["ls", "-al"]):
        return Path(parts[2]).expanduser().resolve() == workspace
    return False


def policy_denial(event: dict[str, Any]) -> str | None:
    """Return a denial reason, or ``None`` when the tool call is permitted."""

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    workspace = Path(str(event.get("cwd") or ".")).resolve()

    if tool_name == "Bash":
        command = tool_input.get("command", "").strip()
        if command == "./check.sh" or safe_inspection_command(command, workspace):
            return None
        return "Only ./check.sh, pwd, and safe listings of this workspace are permitted."

    if tool_name in {"Edit", "Write"}:
        requested = tool_input.get("file_path")
        if requested and Path(str(requested)).expanduser().resolve() == workspace / "Solution.lean":
            return None
        return "Only Solution.lean may be edited or written."

    if tool_name == "Read":
        requested = tool_input.get("file_path")
        if requested:
            path = Path(str(requested)).expanduser().resolve()
            if path.parent == workspace and path.name in READABLE_FILES:
                return None
        return "Only task, solution, merged, original, and checker files in this workspace may be read."

    return f"Tool {tool_name!r} is not permitted in this benchmark."
