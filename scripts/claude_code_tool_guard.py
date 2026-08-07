#!/usr/bin/env python3
"""PreToolUse hook that enforces the Claude Code benchmark tool policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent.claude_tool_policy import policy_denial


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Tool policy could not parse hook input: {exc}", file=sys.stderr)
        return 2
    denial = policy_denial(event)
    if denial:
        print(denial, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

