#!/usr/bin/env python3
"""Combine a historical single-session result with one preserved-workspace repair."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def session_records(agent: dict[str, Any]) -> list[dict[str, Any]]:
    sessions = agent.get("sessions")
    if isinstance(sessions, list) and sessions:
        return [deepcopy(item) for item in sessions if isinstance(item, dict)]
    record = deepcopy(agent)
    for key in (
        "sessions",
        "compiler_passes",
        "total_sessions",
        "selected_session",
        "baseline_plus_repair",
        "initial_result_source",
        "repair_result_source",
    ):
        record.pop(key, None)
    return [record]


def numeric_sum(records: list[dict[str, Any]], key: str) -> float | int | None:
    values = [item.get(key) for item in records]
    known = [value for value in values if isinstance(value, (int, float))]
    return sum(known) if known else None


def merge_results(
    original: dict[str, Any],
    repair: dict[str, Any],
    original_path: Path,
    repair_path: Path,
) -> dict[str, Any]:
    merged = deepcopy(repair)
    original_details = original.get("details") or {}
    repair_details = merged.setdefault("details", {})
    original_agent = original_details.get("agent") or {}
    repair_agent = repair_details.get("agent") or {}
    sessions = session_records(original_agent) + session_records(repair_agent)

    aggregate = deepcopy(repair_agent)
    aggregate.update(
        {
            "sessions": sessions,
            "compiler_passes": len(sessions),
            "total_sessions": len(sessions),
            "selected_session": len(sessions),
            "num_turns": int(numeric_sum(sessions, "num_turns") or 0),
            "total_cost_usd": numeric_sum(sessions, "total_cost_usd"),
            "duration_ms": numeric_sum(sessions, "duration_ms"),
            "duration_api_ms": numeric_sum(sessions, "duration_api_ms"),
            "timed_out": any(bool(item.get("timed_out")) for item in sessions),
            "baseline_plus_repair": True,
            "initial_result_source": str(original_path.resolve()),
            "repair_result_source": str(repair_path.resolve()),
            "initial_cost_usd": original_agent.get("total_cost_usd"),
            "repair_cost_usd": repair_agent.get("total_cost_usd"),
        }
    )
    repair_details["agent"] = aggregate

    original_tokens = original_details.get("tokens") or {}
    repair_tokens = repair_details.get("tokens") or {}
    repair_details["tokens"] = {
        key: int(original_tokens.get(key) or 0) + int(repair_tokens.get(key) or 0)
        for key in ("input", "output", "reasoning")
    }
    repair_details["rounds"] = max(int(aggregate["num_turns"]) - 1, 0)

    history = [
        {
            "compiler_pass": 1,
            "verified": original.get("verified") is True,
            "verifier_response": original_details.get("verifier_response"),
            "agent": original_agent,
        }
    ]
    repair_history = repair_details.get("history") or []
    if repair_history:
        for index, item in enumerate(repair_history, start=2):
            entry = deepcopy(item)
            entry["compiler_pass"] = index
            history.append(entry)
    else:
        history.append(
            {
                "compiler_pass": 2,
                "verified": repair.get("verified") is True,
                "verifier_response": repair_details.get("verifier_response"),
                "agent": repair_agent,
            }
        )
    repair_details["history"] = history
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--repair", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = json.loads(args.original.read_text())
    repair = json.loads(args.repair.read_text())
    if not isinstance(original, dict) or not isinstance(repair, dict):
        raise ValueError("generation results must be JSON objects")
    merged = merge_results(original, repair, args.original, args.repair)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(merged, indent=2) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
