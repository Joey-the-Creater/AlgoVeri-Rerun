#!/usr/bin/env python3
"""Export the exact LastDance prompt templates used by the Claude Code runner."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_claude_code_lean import agent_prompt, repair_prompt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="reports/prompts",
        help="Directory for the rendered prompt templates",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lastdance_initial_prompt.txt").write_text(
        agent_prompt("<TASK_NAME>")
    )
    (output_dir / "lastdance_repair_prompt.txt").write_text(
        repair_prompt(
            "<TASK_NAME>",
            2,
            "<EXACT_INDEPENDENT_VERIFIER_FEEDBACK>",
        )
    )
    print(f"Wrote LastDance prompts to {output_dir}")


if __name__ == "__main__":
    main()
