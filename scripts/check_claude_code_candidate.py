#!/usr/bin/env python3
"""Compile a Claude Code candidate after enforcing AlgoVeri edit boundaries."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent.lean_candidate import CandidateValidationError, merge_candidate_sections
from src.verifiers.lean_verifier import LeanVerifier


def verifier_feedback(result: dict) -> str:
    raw = result.get("raw") or {}
    parts = []
    if raw.get("stdout"):
        parts.append(raw["stdout"].rstrip())
    if raw.get("stderr"):
        parts.append(raw["stderr"].rstrip())
    if not parts and result.get("reason"):
        parts.append(str(result["reason"]))
    return "\n\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--merged", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()

    try:
        merged = merge_candidate_sections(
            Path(args.original).read_text(), Path(args.candidate).read_text()
        ).code
    except (OSError, CandidateValidationError) as exc:
        print(f"CANDIDATE VALIDATION FAILED: {exc}")
        return 2

    Path(args.merged).write_text(merged)
    result = LeanVerifier(config_path=args.config).verify(
        source=merged,
        spec=args.task,
        filename=f"claude_code_{args.task}",
    )
    feedback = verifier_feedback(result)
    if feedback:
        print(feedback)
    if result.get("ok"):
        print("LEAN VERIFIED")
        return 0
    print("LEAN VERIFICATION FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
