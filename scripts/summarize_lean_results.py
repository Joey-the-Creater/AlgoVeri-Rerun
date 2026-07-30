#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def attempts(result: Any) -> Iterable[dict[str, Any]]:
    if isinstance(result, dict):
        yield result
    elif isinstance(result, list):
        yield from (item for item in result if isinstance(item, dict))


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize AlgoVeri Lean result JSON files")
    parser.add_argument("--model", required=True)
    parser.add_argument("--results-root", default="test_results_scale")
    parser.add_argument("--data-root", default="algoveri_data")
    args = parser.parse_args()

    model_name = args.model.split("/")[-1]
    result_dir = Path(args.results_root) / "lean"
    task_names = sorted(path.parent.name for path in Path(args.data_root).glob("*/lean_spec.lean"))

    compiler_passes = 0
    full_marks = 0
    semantic_files = 0
    missing: list[str] = []

    for task_name in task_names:
        path = result_dir / f"{model_name}_{task_name}_lean.json"
        if not path.exists():
            missing.append(task_name)
            continue

        result_attempts = list(attempts(json.loads(path.read_text())))
        if any(item.get("verified") is True for item in result_attempts):
            compiler_passes += 1

        has_semantic_fields = any("parsed" in item or "verdict" in item for item in result_attempts)
        if has_semantic_fields:
            semantic_files += 1
        if any(
            item.get("verified") is True
            and item.get("parsed") is True
            and item.get("verdict") is True
            for item in result_attempts
        ):
            full_marks += 1

    total = len(task_names)
    completed = total - len(missing)
    print(f"Model: {model_name}")
    print(f"Completed: {completed}/{total}")
    print(f"Compiler verified: {compiler_passes}/{total} ({100 * compiler_passes / total:.2f}%)")
    if semantic_files:
        print(f"Semantic-filtered full mark: {full_marks}/{total} ({100 * full_marks / total:.2f}%)")
        print(f"Files with semantic judgments: {semantic_files}/{total}")
    else:
        print("Semantic-filtered full mark: not available (run the semantic filter first)")
    if missing:
        print("Missing tasks: " + ", ".join(missing))


if __name__ == "__main__":
    main()

