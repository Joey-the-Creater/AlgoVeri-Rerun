#!/usr/bin/env python3
"""Export the exact LastDance prompt templates used by the Claude Code runner."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_claude_code_lean import agent_prompt, repair_prompt
from src.agent.lastdance_robust import LastDanceFeatures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="reports/prompts",
        help="Directory for the rendered prompt templates",
    )
    parser.add_argument("--profile", choices=("legacy", "robust"), default="legacy")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    features = LastDanceFeatures.profile_defaults(args.profile)
    prefix = "lastdance" if args.profile == "legacy" else "lastdance_robust"
    (output_dir / f"{prefix}_initial_prompt.txt").write_text(
        agent_prompt("<TASK_NAME>", features)
    )
    (output_dir / f"{prefix}_repair_prompt.txt").write_text(
        repair_prompt(
            "<TASK_NAME>",
            2,
            "<EXACT_INDEPENDENT_VERIFIER_FEEDBACK>",
            features,
            targeted_feedback="<SOURCE_MAPPED_REPAIR_TARGETS>",
        )
    )
    print(f"Wrote LastDance {args.profile} prompts to {output_dir}")


if __name__ == "__main__":
    main()
