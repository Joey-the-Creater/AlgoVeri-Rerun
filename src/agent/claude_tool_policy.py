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
    "leansearch",
    "AlgorithmPlan.md",
    "ProofState.md",
    "Diagnostics.md",
    "diagnose",
}

WRITABLE_FILES = {"Solution.lean", "AlgorithmPlan.md", "ProofState.md"}


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


def safe_cat_command(command: str, workspace: Path) -> bool:
    """Allow read-only ``cat`` of explicitly approved workspace files.

    Claude occasionally uses ``cat`` even though the Read tool is available.  Keep
    that harmless preference from wasting a turn, while rejecting options, shell
    syntax, paths outside the task directory, and unapproved files.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) < 2 or parts[0] != "cat":
        return False
    for requested in parts[1:]:
        if requested.startswith("-"):
            return False
        path = Path(requested).expanduser()
        if not path.is_absolute():
            path = workspace / path
        path = path.resolve()
        if path.parent != workspace or path.name not in READABLE_FILES:
            return False
    return True


def safe_leansearch_command(command: str, workspace: Path) -> bool:
    """Allow one bounded natural-language query through the harness wrapper."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    return (
        len(parts) == 2
        and parts[0] == "./leansearch"
        and 0 < len(parts[1]) <= 1000
        and "\n" not in parts[1]
        and (workspace / "leansearch").is_file()
    )


def policy_denial(event: dict[str, Any]) -> str | None:
    """Return a denial reason, or ``None`` when the tool call is permitted."""

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    workspace = Path(str(event.get("cwd") or ".")).resolve()

    if tool_name == "Bash":
        command = tool_input.get("command", "").strip()
        if (
            command in {"./check.sh", "./diagnose"}
            or safe_inspection_command(command, workspace)
            or safe_cat_command(command, workspace)
            or safe_leansearch_command(command, workspace)
        ):
            return None
        if command.startswith("./check.sh"):
            return (
                "Run the checker exactly as ./check.sh; do not append 2>&1, a pipe, "
                "tail, a filter, or a redirection. Use ./diagnose when that bounded "
                "wrapper is present."
            )
        return (
            "Only ./check.sh, ./diagnose when provided, one quoted ./leansearch "
            "query, pwd, safe listings, and cat of approved workspace files are "
            "permitted."
        )

    if tool_name in {"Edit", "Write"}:
        requested = tool_input.get("file_path")
        if requested:
            path = Path(str(requested)).expanduser().resolve()
            if path.parent == workspace and path.name in WRITABLE_FILES:
                if path.name == "Solution.lean" or path.is_file():
                    return None
        return "Only Solution.lean and existing LastDance plan files may be edited or written."

    if tool_name == "Read":
        requested = tool_input.get("file_path")
        if requested:
            path = Path(str(requested)).expanduser().resolve()
            if path.parent == workspace and path.name in READABLE_FILES:
                return None
        return "Only approved task, solution, plan, search, lint, and checker files may be read."

    return f"Tool {tool_name!r} is not permitted in this benchmark."
