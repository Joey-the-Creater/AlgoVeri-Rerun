#!/usr/bin/env python3
"""Produce reproducible aggregate and case-level statistics for the rerun report."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent.experiment_catalog import Experiment, ExperimentCatalog
from src.agent.lean_candidate import has_teacher_owned_sorry


CONDITIONS = {
    "gpt-5.5": {
        "label": "GPT-5.5",
        "original": "gpt-5.5",
        "gpt54_t0": "gpt-5.5-temp0",
        "gpt56_t0": "gpt-5.5-judge-gpt56-temp0",
    },
    "gpt-5.6-sol": {
        "label": "GPT-5.6-sol",
        "original": "gpt-5.6-sol",
        "gpt54_t0": "gpt-5.6-sol-temp0",
        "gpt56_t0": "gpt-5.6-sol-judge-gpt56-temp0",
    },
    "opus-5-thinking": {
        "label": "Opus 5 (thinking)",
        "original": "opus-5-thinking",
        "gpt54_t0": "opus-5-thinking-temp0",
        "gpt56_t0": "opus-5-thinking-judge-gpt56-temp0",
    },
    "opus-5-no-thinking": {
        "label": "Opus 5 (no thinking)",
        "original": "opus-5-no-thinking",
        "gpt54_t0": "opus-5-no-thinking-temp0",
        "gpt56_t0": "opus-5-no-thinking-judge-gpt56-temp0",
    },
    "claude-code-opus5-enhanced": {
        "label": "Claude Code + Opus 5 (enhanced)",
        "original": "claude-code-opus5-enhanced",
        "gpt54_t0": "claude-code-opus5-enhanced-temp0",
        "gpt56_t0": "claude-code-opus5-enhanced-judge-gpt56-temp0",
    },
}

JUDGE_LABELS = {
    "original": "GPT-5.4, temperature 1",
    "gpt54_t0": "GPT-5.4, temperature 0",
    "gpt56_t0": "GPT-5.6-sol, temperature 0, reasoning none",
}


def result(experiment: Experiment, task: str) -> dict[str, Any]:
    return experiment.task_result(task)


def kappa(a: list[bool], b: list[bool]) -> float | None:
    if not a:
        return None
    observed = sum(left == right for left, right in zip(a, b, strict=True)) / len(a)
    a_yes = sum(a) / len(a)
    b_yes = sum(b) / len(b)
    expected = a_yes * b_yes + (1 - a_yes) * (1 - b_yes)
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1 - expected)


def agreement(
    condition: str,
    left_name: str,
    left: Experiment,
    right_name: str,
    right: Experiment,
) -> dict[str, Any]:
    common = sorted(set(left.task_names) & set(right.task_names))
    rows = []
    for task in common:
        left_item = result(left, task)
        right_item = result(right, task)
        if not left_item["compile_success"]:
            continue
        if not left_item["semantic_evaluated"] or not right_item["semantic_evaluated"]:
            continue
        rows.append((task, left_item["semantic_success"], right_item["semantic_success"]))
    left_values = [row[1] for row in rows]
    right_values = [row[2] for row in rows]
    disagreements = [
        {"task": task, "left": left_value, "right": right_value}
        for task, left_value, right_value in rows
        if left_value != right_value
    ]
    return {
        "condition": condition,
        "left": left_name,
        "right": right_name,
        "compiled_common": len(rows),
        "agree": sum(left_value == right_value for _, left_value, right_value in rows),
        "both_pass": sum(left_value and right_value for _, left_value, right_value in rows),
        "both_fail": sum(not left_value and not right_value for _, left_value, right_value in rows),
        "left_only_pass": sum(left_value and not right_value for _, left_value, right_value in rows),
        "right_only_pass": sum(not left_value and right_value for _, left_value, right_value in rows),
        "agreement_rate": (
            sum(left_value == right_value for _, left_value, right_value in rows) / len(rows)
            if rows
            else None
        ),
        "cohen_kappa": kappa(left_values, right_values),
        "disagreements": disagreements,
    }


def build_analysis(catalog: ExperimentCatalog) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    conditions: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    agreements: list[dict[str, Any]] = []
    no_teacher_sorry_scope = catalog.get("claude-code-opus5-enhanced")
    if no_teacher_sorry_scope is None:
        raise ValueError("Catalog is missing the enhanced Claude Code experiment")
    common_tasks = no_teacher_sorry_scope.task_names
    teacher_sorry_tasks = sorted(
        path.parent.name
        for path in (REPO_ROOT / "algoveri_data").glob("*/lean_spec.lean")
        if has_teacher_owned_sorry(path.read_text())
    )

    for condition_id, configured in CONDITIONS.items():
        experiments = {
            judge: catalog.get(configured[judge]) for judge in JUDGE_LABELS
        }
        if any(experiment is None for experiment in experiments.values()):
            raise ValueError(f"Catalog is missing an experiment for {condition_id}")
        typed = {key: value for key, value in experiments.items() if value is not None}
        original = typed["original"]
        summaries = {judge: experiment.summary() for judge, experiment in typed.items()}
        condition = {
            "id": condition_id,
            "label": configured["label"],
            "scope": len(original.task_names),
            "outputs": summaries["original"]["outputs"],
            "missing": summaries["original"]["missing"],
            "compile_success": summaries["original"]["compile_success"],
            "compile_rate": summaries["original"]["compile_rate"],
            "known_cost_usd": summaries["original"]["known_cost_usd"],
            "cost_coverage": summaries["original"]["cost_coverage"],
            "judges": {
                judge: {
                    "label": JUDGE_LABELS[judge],
                    "evaluated": summary["semantic_evaluated"],
                    "passes": summary["semantic_success"],
                    "rate_scope": summary["semantic_rate"],
                    "rate_evaluated": summary["semantic_rate_judged"],
                    "rate_compiled": (
                        summary["semantic_success"] / summaries["original"]["compile_success"]
                        if summaries["original"]["compile_success"]
                        else None
                    ),
                }
                for judge, summary in summaries.items()
            },
            "compile_failures": [],
            "missing_tasks": [],
        }
        for task in original.task_names:
            items = {judge: result(experiment, task) for judge, experiment in typed.items()}
            generation = items["original"]
            if not generation["output_present"]:
                condition["missing_tasks"].append(task)
            elif not generation["compile_success"]:
                condition["compile_failures"].append(task)
            case_rows.append(
                {
                    "condition": condition_id,
                    "model": configured["label"],
                    "task": task,
                    "in_no_teacher_sorry_scope": task in common_tasks,
                    "teacher_owned_sorry": task in teacher_sorry_tasks,
                    "output_present": generation["output_present"],
                    "compile_success": generation["compile_success"],
                    "gpt54_temp1_pass": items["original"]["semantic_success"],
                    "gpt54_temp0_pass": items["gpt54_t0"]["semantic_success"],
                    "gpt56_temp0_pass": items["gpt56_t0"]["semantic_success"],
                    "gpt54_temp1_analysis": items["original"]["semantic_analysis"],
                    "gpt54_temp0_analysis": items["gpt54_t0"]["semantic_analysis"],
                    "gpt56_temp0_analysis": items["gpt56_t0"]["semantic_analysis"],
                }
            )
        conditions.append(condition)
        agreements.extend(
            [
                agreement(condition_id, "original", typed["original"], "gpt54_t0", typed["gpt54_t0"]),
                agreement(condition_id, "gpt54_t0", typed["gpt54_t0"], "gpt56_t0", typed["gpt56_t0"]),
            ]
        )

    common_scope = []
    teacher_sorry_results = []
    efficiency = []
    for condition_id, configured in CONDITIONS.items():
        experiments = {
            judge: catalog.get(configured[judge]) for judge in JUDGE_LABELS
        }
        typed = {key: value for key, value in experiments.items() if value is not None}
        common_summaries = {
            judge: experiment.summary(common_tasks) for judge, experiment in typed.items()
        }
        common_scope.append(
            {
                "condition": condition_id,
                "label": configured["label"],
                "scope": len(common_tasks),
                "outputs": common_summaries["original"]["outputs"],
                "compile_success": common_summaries["original"]["compile_success"],
                "semantic_passes": {
                    judge: summary["semantic_success"]
                    for judge, summary in common_summaries.items()
                },
            }
        )
        teacher_items = {
            judge: [result(experiment, task) for task in teacher_sorry_tasks]
            for judge, experiment in typed.items()
        }
        teacher_sorry_results.append(
            {
                "condition": condition_id,
                "outputs": sum(item["output_present"] for item in teacher_items["original"]),
                "compile_success": sum(item["compile_success"] for item in teacher_items["original"]),
                "semantic_passes": {
                    judge: sum(item["semantic_success"] for item in items)
                    for judge, items in teacher_items.items()
                },
            }
        )
        original = typed["original"]
        task_items = [result(original, task) for task in original.task_names]
        tokens = {
            key: sum(int(item["tokens"].get(key, 0) or 0) for item in task_items)
            for key in ("input", "output", "reasoning")
        }
        durations = [
            item["duration_ms"]
            for item in task_items
            if isinstance(item.get("duration_ms"), (int, float))
        ]
        summary = original.summary()
        try_counts = {row["try"]: row["successes"] for row in summary["try_curve"]}
        efficiency.append(
            {
                "condition": condition_id,
                "tokens": tokens,
                "known_cost_usd": summary["known_cost_usd"],
                "cost_coverage": summary["cost_coverage"],
                "summed_duration_hours": sum(durations) / 3_600_000,
                "loc_added": summary["loc_added"],
                "average_loc_added": summary["average_loc_added"],
                "success_by_try": {
                    str(number): try_counts.get(number, summary["compile_success"])
                    for number in (1, 2, 3, 5, 10, 15)
                },
            }
        )

    pilot_ids = [
        "claude-code-hard10",
        "claude-code-opus5-nonthinking20",
        "claude-code-opus5-combined",
    ]
    pilot = [catalog.get(experiment_id).summary() for experiment_id in pilot_ids if catalog.get(experiment_id)]

    return {
        "schema_version": 1,
        "conditions": conditions,
        "agreements": agreements,
        "common_no_teacher_sorry_scope": {
            "count": len(common_tasks),
            "tasks": common_tasks,
            "conditions": common_scope,
        },
        "teacher_owned_sorry": {
            "count": len(teacher_sorry_tasks),
            "tasks": teacher_sorry_tasks,
            "conditions": teacher_sorry_results,
        },
        "efficiency": efficiency,
        "pilot_claude_code": pilot,
    }, case_rows


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def write_latex(path: Path, analysis: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    by_condition_task = {
        (row["condition"], row["task"]): row
        for row in rows
    }
    all_tasks = sorted({row["task"] for row in rows})
    lines = [
        "% Generated by scripts/analyze_rerun_results.py; do not edit manually.",
        r"\begin{landscape}",
        r"\footnotesize",
        r"\begin{longtable}{@{}lccccc@{}}",
        r"\caption{Complete case-level outcome matrix. A cell is \texttt{C:abc} when Lean compiles; $a$, $b$, and $c$ are semantic outcomes for GPT-5.4 at temperature 1, GPT-5.4 at temperature 0, and GPT-5.6-sol at temperature 0, respectively (\texttt{P}=pass, \texttt{F}=fail). \texttt{X} denotes a saved output that does not compile, \texttt{M} a missing output, and -- an out-of-scope case.}\label{tab:complete-matrix}\\",
        r"\toprule",
        r"Task & GPT-5.5 & GPT-5.6-sol & Opus think & Opus no-think & Claude Code \\",
        r"\midrule",
        r"\endfirsthead",
        r"\multicolumn{6}{c}{\tablename\ \thetable{} -- continued}\\",
        r"\toprule",
        r"Task & GPT-5.5 & GPT-5.6-sol & Opus think & Opus no-think & Claude Code \\",
        r"\midrule",
        r"\endhead",
        r"\midrule \multicolumn{6}{r}{Continued on next page}\\",
        r"\endfoot",
        r"\bottomrule",
        r"\endlastfoot",
    ]
    for task in all_tasks:
        cells = []
        for condition in CONDITIONS:
            row = by_condition_task.get((condition, task))
            if row is None:
                cells.append("--")
            elif not row["output_present"]:
                cells.append(r"\texttt{M}")
            elif not row["compile_success"]:
                cells.append(r"\texttt{X}")
            else:
                verdicts = "".join(
                    "P" if row[key] else "F"
                    for key in ("gpt54_temp1_pass", "gpt54_temp0_pass", "gpt56_temp0_pass")
                )
                cells.append(rf"\texttt{{C:{verdicts}}}")
        lines.append(rf"\texttt{{{latex_escape(task)}}} & " + " & ".join(cells) + r" \\")
    lines.extend([r"\end{longtable}", r"\end{landscape}", ""])

    lines.extend(
        [
            r"\begin{landscape}",
            r"\scriptsize",
            r"\begin{longtable}{@{}llrrrrp{9.2cm}@{}}",
            r"\caption{All semantic-judge disagreements on compiler-accepted outputs.}\label{tab:all-disagreements}\\",
            r"\toprule",
            r"Generation & Comparison & $n$ & Agree & $\kappa$ & Flips & Disagreement cases \\",
            r"\midrule",
            r"\endfirsthead",
            r"\multicolumn{7}{c}{\tablename\ \thetable{} -- continued}\\",
            r"\toprule",
            r"Generation & Comparison & $n$ & Agree & $\kappa$ & Flips & Disagreement cases \\",
            r"\midrule",
            r"\endhead",
            r"\midrule \multicolumn{7}{r}{Continued on next page}\\",
            r"\endfoot",
            r"\bottomrule",
            r"\endlastfoot",
        ]
    )
    label_by_id = {item["id"]: item["label"] for item in analysis["conditions"]}
    comparison_labels = {
        ("original", "gpt54_t0"): "5.4 T1 vs 5.4 T0",
        ("gpt54_t0", "gpt56_t0"): "5.4 T0 vs 5.6 T0",
    }
    for item in analysis["agreements"]:
        tasks = ", ".join(
            f"{entry['task']} ({'L' if entry['left'] else 'R'})"
            for entry in item["disagreements"]
        )
        flips = len(item["disagreements"])
        lines.append(
            f"{latex_escape(label_by_id[item['condition']])} & "
            f"{comparison_labels[(item['left'], item['right'])]} & "
            f"{item['compiled_common']} & {item['agree']} & {item['cohen_kappa']:.3f} & {flips} & "
            f"{latex_escape(tasks)} \\\\"
        )
    lines.extend([r"\end{longtable}", r"\end{landscape}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=REPO_ROOT / "config/dashboard_experiments.json")
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "algoveri_data")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--latex-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = ExperimentCatalog(REPO_ROOT, args.catalog, args.data_root)
    analysis, case_rows = build_analysis(catalog)
    if args.json_output:
        write_json(args.json_output, analysis)
    if args.csv_output:
        write_csv(args.csv_output, case_rows)
    if args.latex_output:
        write_latex(args.latex_output, analysis, case_rows)
    print(json.dumps(analysis, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
