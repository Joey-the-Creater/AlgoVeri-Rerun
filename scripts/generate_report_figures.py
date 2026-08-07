#!/usr/bin/env python3
"""Generate reproducible vector figures and plot data for the LastDance report."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


CONDITION_ORDER = [
    "gpt-5.5",
    "gpt-5.6-sol",
    "opus-5-thinking",
    "opus-5-no-thinking",
    "claude-code-opus5-enhanced",
]
SHORT_LABELS = {
    "gpt-5.5": "GPT-5.5",
    "gpt-5.6-sol": "GPT-5.6-sol",
    "opus-5-thinking": "Opus 5\nthinking",
    "opus-5-no-thinking": "Opus 5\nno thinking",
    "claude-code-opus5-enhanced": "LastDance",
}
COLORS = {
    "gpt-5.5": "#4C78A8",
    "gpt-5.6-sol": "#F58518",
    "opus-5-thinking": "#B279A2",
    "opus-5-no-thinking": "#E45756",
    "claude-code-opus5-enhanced": "#18A999",
}
STATE_COLORS = {
    "semantic_pass": "#2A9D8F",
    "compiled_fail": "#E9C46A",
    "compile_fail": "#E76F51",
    "missing": "#9CA3AF",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        default="reports/data/result_summary.json",
        help="Analysis JSON produced by analyze_rerun_results.py",
    )
    parser.add_argument("--figure-dir", default="reports/figures")
    parser.add_argument("--data-dir", default="reports/data")
    return parser.parse_args()


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "figure.dpi": 160,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.05,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def category_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for category in summary["algorithm_categories"]:
        for condition in category["conditions"]:
            scope = condition["scope"]
            passes = condition["semantic_passes"]["gpt54_t0"]
            rows.append(
                {
                    "category": category["category"],
                    "native_scope": category["native_scope"],
                    "common_scope": scope,
                    "condition": condition["condition"],
                    "outputs": condition["outputs"],
                    "compile_success": condition["compile_success"],
                    "gpt54_temp0_semantic_passes": passes,
                    "gpt54_temp0_full_mark_rate": passes / scope if scope else 0,
                }
            )
    return rows


def plot_category_breakdown(
    summary: dict[str, Any], rows: list[dict[str, Any]], output: Path
) -> None:
    categories = [item["category"] for item in summary["algorithm_categories"]]
    lookup = {(row["condition"], row["category"]): row for row in rows}
    radar_conditions = [
        "gpt-5.5",
        "gpt-5.6-sol",
        "opus-5-no-thinking",
        "claude-code-opus5-enhanced",
    ]
    rates = np.array(
        [
            [100 * lookup[(condition, category)]["gpt54_temp0_full_mark_rate"] for category in categories]
            for condition in CONDITION_ORDER
        ]
    )

    fig = plt.figure(figsize=(12.3, 4.5))
    grid = fig.add_gridspec(1, 2, width_ratios=[1.05, 1.35], wspace=0.28)
    ax_radar = fig.add_subplot(grid[0, 0], projection="polar")
    angles = np.linspace(0, 2 * math.pi, len(categories), endpoint=False)
    closed_angles = np.r_[angles, angles[0]]
    for condition in radar_conditions:
        values = np.array(
            [100 * lookup[(condition, category)]["gpt54_temp0_full_mark_rate"] for category in categories]
        )
        ax_radar.plot(
            closed_angles,
            np.r_[values, values[0]],
            color=COLORS[condition],
            linewidth=2.0 if condition == "claude-code-opus5-enhanced" else 1.4,
            marker="o",
            markersize=3,
            label=SHORT_LABELS[condition].replace("\n", " "),
        )
        if condition == "claude-code-opus5-enhanced":
            ax_radar.fill(closed_angles, np.r_[values, values[0]], color=COLORS[condition], alpha=0.10)
    ax_radar.set_theta_offset(math.pi / 2)
    ax_radar.set_theta_direction(-1)
    ax_radar.set_xticks(angles)
    ax_radar.set_xticklabels(categories)
    ax_radar.set_ylim(0, 100)
    ax_radar.set_yticks([20, 40, 60, 80, 100])
    ax_radar.set_yticklabels(["20", "40", "60", "80", "100%"], color="#666666")
    ax_radar.grid(color="#D1D5DB", linewidth=0.7)
    ax_radar.set_title("(a) Full-mark rate by AlgoVeri category", pad=17, fontweight="bold")
    ax_radar.legend(loc="lower center", bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False)

    ax_heat = fig.add_subplot(grid[0, 1])
    image = ax_heat.imshow(rates, cmap="YlGnBu", vmin=0, vmax=100, aspect="auto")
    ax_heat.set_xticks(range(len(categories)))
    ax_heat.set_xticklabels(categories, rotation=32, ha="right")
    ax_heat.set_yticks(range(len(CONDITION_ORDER)))
    ax_heat.set_yticklabels([SHORT_LABELS[item] for item in CONDITION_ORDER])
    for row_index, condition in enumerate(CONDITION_ORDER):
        for column_index, category in enumerate(categories):
            item = lookup[(condition, category)]
            value = rates[row_index, column_index]
            color = "white" if value >= 55 else "#111827"
            ax_heat.text(
                column_index,
                row_index,
                f"{item['gpt54_temp0_semantic_passes']}/{item['common_scope']}\n{value:.0f}%",
                ha="center",
                va="center",
                fontsize=7.5,
                color=color,
            )
    ax_heat.set_title("(b) Counts and rates on the common 65-task scope", pad=10, fontweight="bold")
    ax_heat.tick_params(length=0)
    for spine in ax_heat.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax_heat, fraction=0.035, pad=0.025)
    colorbar.set_label("GPT-5.4 T0 full-mark rate (%)")
    fig.savefig(output)
    plt.close(fig)


def repair_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in summary["efficiency"]:
        for point in item["common_try_curve"]:
            rows.append(
                {
                    "condition": item["condition"],
                    "try": point["try"],
                    "compiled": point["successes"],
                    "scope": summary["common_no_teacher_sorry_scope"]["count"],
                    "compile_rate": point["rate"],
                }
            )
    return rows


def plot_repair_curves(rows: list[dict[str, Any]], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    for condition in CONDITION_ORDER:
        points = [row for row in rows if row["condition"] == condition and row["try"] <= 15]
        ax.plot(
            [row["try"] for row in points],
            [100 * row["compile_rate"] for row in points],
            color=COLORS[condition],
            linewidth=2.2 if condition == "claude-code-opus5-enhanced" else 1.5,
            marker="o" if condition == "claude-code-opus5-enhanced" else None,
            markersize=3,
            label=SHORT_LABELS[condition].replace("\n", " "),
        )
    ax.set_xlim(1, 15)
    ax.set_ylim(0, 100)
    ax.set_xticks([1, 2, 3, 5, 7, 10, 12, 15])
    ax.set_xlabel("Generation attempt / observed Lean check")
    ax.set_ylabel("Cumulative compilation rate (%)")
    ax.grid(axis="y", color="#E5E7EB")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right", ncol=2, frameon=True, framealpha=0.95)
    fig.savefig(output)
    plt.close(fig)


def outcome_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for condition in summary["common_no_teacher_sorry_scope"]["conditions"]:
        scope = condition["scope"]
        output = condition["outputs"]
        compiled = condition["compile_success"]
        semantic = condition["semantic_passes"]["gpt54_t0"]
        rows.append(
            {
                "condition": condition["condition"],
                "scope": scope,
                "compiled_and_semantic_pass": semantic,
                "compiled_semantic_fail": compiled - semantic,
                "compile_fail": output - compiled,
                "missing_output": scope - output,
            }
        )
    return rows


def plot_outcomes(rows: list[dict[str, Any]], output: Path) -> None:
    lookup = {row["condition"]: row for row in rows}
    fig, ax = plt.subplots(figsize=(7.2, 3.7))
    left = np.zeros(len(CONDITION_ORDER))
    states = [
        ("compiled_and_semantic_pass", "Compiled + semantic pass", "semantic_pass"),
        ("compiled_semantic_fail", "Compiled, semantic fail", "compiled_fail"),
        ("compile_fail", "Does not compile", "compile_fail"),
        ("missing_output", "Missing output", "missing"),
    ]
    for key, label, color_key in states:
        values = np.array([lookup[item][key] for item in CONDITION_ORDER])
        ax.barh(
            range(len(CONDITION_ORDER)),
            values,
            left=left,
            color=STATE_COLORS[color_key],
            edgecolor="white",
            linewidth=0.6,
            label=label,
        )
        for index, value in enumerate(values):
            if value >= 4:
                ax.text(left[index] + value / 2, index, str(value), ha="center", va="center", fontsize=8)
        left += values
    ax.set_yticks(range(len(CONDITION_ORDER)))
    ax.set_yticklabels([SHORT_LABELS[item] for item in CONDITION_ORDER])
    ax.invert_yaxis()
    ax.set_xlim(0, 65)
    ax.set_xlabel("Tasks on common no-teacher-sorry scope (n=65)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#E5E7EB", zorder=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False)
    fig.savefig(output)
    plt.close(fig)


def rounded_box(ax: Any, x: float, y: float, width: float, height: float, text: str, color: str) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.025,rounding_size=0.08",
        linewidth=1.2,
        edgecolor=color,
        facecolor="white",
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=8.3)


def arrow(ax: Any, start: tuple[float, float], end: tuple[float, float], color: str = "#4B5563", rad: float = 0) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=11,
            linewidth=1.15,
            color=color,
            connectionstyle=f"arc3,rad={rad}",
        )
    )


def plot_pipeline(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.4, 4.2))
    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, 4.3)
    ax.axis("off")
    stages = [
        (0.15, "AlgoVeri task\nTASK.md + scaffold", "#4C78A8"),
        (2.25, "Isolated workspace\nSolution.lean only", "#4C78A8"),
        (4.35, "Claude Code + Opus 5\nsemantic self-audit", "#7B61A8"),
        (6.45, "Section merge + guard\nownership / banned terms", "#D97706"),
        (8.55, "Independent Lean check\npinned Lake + Mathlib", "#059669"),
        (10.65, "Semantic judges\nresults + dashboard", "#0F766E"),
    ]
    for x, label, color in stages:
        rounded_box(ax, x, 2.55, 1.7, 0.9, label, color)
    for left, right in zip(stages, stages[1:]):
        arrow(ax, (left[0] + 1.7, 3.0), (right[0], 3.0))

    rounded_box(ax, 3.25, 0.75, 1.75, 0.72, "Restricted ./check.sh\n(no network / Git)", "#7B61A8")
    rounded_box(ax, 5.40, 0.75, 1.65, 0.72, "Lean compiler\nexact diagnostics", "#059669")
    arrow(ax, (4.65, 2.55), (4.18, 1.47), "#7B61A8", 0.08)
    arrow(ax, (5.0, 1.11), (5.40, 1.11), "#059669")
    arrow(ax, (5.95, 1.47), (5.03, 2.55), "#E45756", 0.15)

    ax.plot([9.40, 9.40, 5.20], [2.55, 2.05, 2.05], color="#E45756", linewidth=1.15)
    arrow(ax, (5.20, 2.05), (5.20, 2.55), "#E45756")
    ax.text(
        7.25,
        1.82,
        "if independent verification fails:\npreserve workspace + exact feedback + one repair session",
        ha="center",
        va="center",
        fontsize=7.5,
        color="#9F1239",
    )

    ax.text(0.15, 3.96, "LastDance", fontsize=17, fontweight="bold", color="#111827")
    ax.text(
        2.05,
        4.00,
        "a constrained, compiler-grounded Claude Code toolchain for Lean vericoding",
        fontsize=9.5,
        color="#4B5563",
    )
    ax.text(
        0.18,
        0.18,
        "Trust boundary: the agent cannot edit teacher files or the checker; only merged marker regions are accepted, and final success is recompiled outside the agent session.",
        fontsize=8,
        color="#374151",
    )
    fig.savefig(output)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    configure_style()
    summary = json.loads(Path(args.summary).read_text())
    figure_dir = Path(args.figure_dir)
    data_dir = Path(args.data_dir)
    figure_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    categories = category_rows(summary)
    repairs = repair_rows(summary)
    outcomes = outcome_rows(summary)
    write_csv(data_dir / "category_results.csv", categories)
    write_csv(data_dir / "repair_curves.csv", repairs)
    write_csv(data_dir / "outcome_breakdown.csv", outcomes)
    plot_category_breakdown(summary, categories, figure_dir / "category_breakdown.pdf")
    plot_repair_curves(repairs, figure_dir / "repair_curves.pdf")
    plot_outcomes(outcomes, figure_dir / "outcome_breakdown.pdf")
    plot_pipeline(figure_dir / "lastdance_pipeline.pdf")
    print(f"Wrote figures to {figure_dir} and plot data to {data_dir}")


if __name__ == "__main__":
    main()
