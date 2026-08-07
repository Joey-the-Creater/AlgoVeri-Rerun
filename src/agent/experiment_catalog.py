"""Multi-experiment AlgoVeri result analytics for the local dashboard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dashboard_state import DashboardState, line_change_counts, load_json, parse_event_log


def attempts(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else [value]
    return [item for item in values if isinstance(item, dict)]


def first_success_try(items: list[dict[str, Any]]) -> int | None:
    successful = []
    for item in items:
        if item.get("verified") is not True:
            continue
        rounds = (item.get("details") or {}).get("rounds")
        if isinstance(rounds, int):
            successful.append(rounds + 1)
    return min(successful) if successful else None


def first_success_pass(items: list[dict[str, Any]]) -> int | None:
    return next((index for index, item in enumerate(items, start=1) if item.get("verified") is True), None)


def first_semantic_pass(items: list[dict[str, Any]]) -> int | None:
    return next(
        (
            index
            for index, item in enumerate(items, start=1)
            if item.get("verified") is True
            and item.get("parsed") is True
            and item.get("verdict") is True
        ),
        None,
    )


@dataclass
class Experiment:
    repo_root: Path
    config: dict[str, Any]
    all_tasks: list[str]

    @property
    def id(self) -> str:
        return str(self.config["id"])

    @property
    def model(self) -> str:
        return str(self.config["model"])

    @property
    def source_configs(self) -> list[dict[str, Any]]:
        configured = self.config.get("sources")
        return configured if isinstance(configured, list) and configured else [self.config]

    def tasks_for(self, config: dict[str, Any]) -> list[str]:
        configured = config.get("tasks", "all")
        tasks = self.all_tasks if configured == "all" else [str(item) for item in configured]
        excluded = {str(item) for item in config.get("exclude_tasks", [])}
        return [task for task in tasks if task not in excluded]

    def source_for(self, task: str) -> dict[str, Any]:
        for source in self.source_configs:
            if task in self.tasks_for(source):
                return source
        return self.config

    def resolve_from(self, config: dict[str, Any], key: str) -> Path | None:
        value = config.get(key)
        if not value:
            return None
        path = Path(str(value)).expanduser()
        return path.resolve() if path.is_absolute() else (self.repo_root / path).resolve()

    def resolve(self, key: str) -> Path | None:
        return self.resolve_from(self.config, key)

    @property
    def task_names(self) -> list[str]:
        return list(
            dict.fromkeys(
                task
                for source in self.source_configs
                for task in self.tasks_for(source)
            )
        )

    @property
    def results_root(self) -> Path:
        return self.resolve("results_root") or self.repo_root / "results"

    @property
    def semantic_root(self) -> Path | None:
        return self.resolve("semantic_root")

    @property
    def work_root(self) -> Path | None:
        return self.resolve("work_root")

    def results_root_for(self, task: str) -> Path:
        return self.resolve_from(self.source_for(task), "results_root") or self.repo_root / "results"

    def semantic_root_for(self, task: str) -> Path | None:
        return self.resolve_from(self.source_for(task), "semantic_root")

    def work_root_for(self, task: str) -> Path | None:
        return self.resolve_from(self.source_for(task), "work_root")

    def result_path(self, task: str, semantic: bool = False) -> Path:
        root = self.semantic_root_for(task) if semantic else self.results_root_for(task)
        assert root is not None
        return root / "lean" / f"{self.model}_{task}_lean.json"

    def task_result(self, task: str) -> dict[str, Any]:
        generation_path = self.result_path(task)
        semantic_root = self.semantic_root_for(task)
        semantic_path = self.result_path(task, semantic=True) if semantic_root else None
        generation_value = load_json(generation_path)
        semantic_value = load_json(semantic_path) if semantic_path else None
        generation_attempts = attempts(generation_value)
        semantic_attempts = attempts(semantic_value)
        output_present = generation_value is not None
        compile_success = any(item.get("verified") is True for item in generation_attempts)
        semantic_success = any(
            item.get("verified") is True
            and item.get("parsed") is True
            and item.get("verdict") is True
            for item in semantic_attempts
        )
        semantic_evaluated = semantic_value is not None and any(
            "parsed" in item or "verdict" in item for item in semantic_attempts
        )
        success_try = first_success_try(generation_attempts)
        observed_checks = 0
        event_stats: dict[str, Any] = {}
        work_root = self.work_root_for(task)
        if work_root:
            event_path = work_root / task / "agent_events.jsonl"
            event_stats = parse_event_log(event_path)
            observed_checks = int(event_stats.get("check_attempts", 0))
            if compile_success and observed_checks:
                success_try = int(observed_checks)

        chosen = next((item for item in generation_attempts if item.get("verified") is True), None)
        chosen = chosen or (generation_attempts[-1] if generation_attempts else {})
        semantic_chosen = next(
            (item for item in semantic_attempts if item.get("verdict") is True),
            semantic_attempts[-1] if semantic_attempts else {},
        )
        details = chosen.get("details") or {}
        verifier = details.get("verifier_response") or {}
        llm_response = details.get("llm_response") or {}
        agent = details.get("agent") or {}
        code = llm_response.get("code", "")
        loc_added = None
        loc_removed = None
        if code:
            try:
                original = (self.repo_root / "algoveri_data" / task / "lean_spec.lean").read_text()
                changes = line_change_counts(original, code)
                loc_added = changes["added"]
                loc_removed = changes["removed"]
            except OSError:
                pass
        return {
            "task": task,
            "output_present": output_present,
            "attempt_count": len(generation_attempts),
            "compile_success": compile_success,
            "semantic_evaluated": semantic_evaluated,
            "semantic_success": semantic_success,
            "success_try": success_try,
            "success_pass": first_success_pass(generation_attempts),
            "semantic_pass": first_semantic_pass(semantic_attempts),
            "rounds": details.get("rounds"),
            "check_attempts": observed_checks or (
                details.get("rounds") + 1 if isinstance(details.get("rounds"), int) else 0
            ),
            "code": code,
            "comment": llm_response.get("comment", ""),
            "verifier_feedback": verifier.get("feedback", ""),
            "semantic_analysis": semantic_chosen.get("analysis", ""),
            "tokens": details.get("tokens") or {},
            "agent": agent,
            "cost_usd": agent.get("total_cost_usd"),
            "duration_ms": agent.get("duration_ms"),
            "loc_added": loc_added,
            "loc_removed": loc_removed,
            "event_stats": event_stats,
        }

    def summary(self, scope: list[str] | None = None) -> dict[str, Any]:
        task_names = scope if scope is not None else self.task_names
        results = [self.task_result(task) for task in task_names]
        total = len(task_names)
        outputs = sum(item["output_present"] for item in results)
        compile_success = sum(item["compile_success"] for item in results)
        semantic_success = sum(item["semantic_success"] for item in results)
        semantic_evaluated = sum(item["semantic_evaluated"] for item in results)
        max_tries = max(
            int(self.config.get("max_tries") or 15),
            max((item["success_try"] or 0 for item in results), default=0),
        )
        max_passes = max((item["attempt_count"] for item in results), default=1)
        try_curve = []
        for try_number in range(1, max_tries + 1):
            solved = sum(
                item["success_try"] is not None and item["success_try"] <= try_number
                for item in results
            )
            try_curve.append(
                {
                    "try": try_number,
                    "successes": solved,
                    "rate": solved / total if total else 0,
                }
            )
        pass_curve = []
        for pass_number in range(1, max_passes + 1):
            compile_solved = sum(
                item["success_pass"] is not None and item["success_pass"] <= pass_number
                for item in results
            )
            semantic_solved = sum(
                item["semantic_pass"] is not None and item["semantic_pass"] <= pass_number
                for item in results
            )
            pass_curve.append(
                {
                    "pass": pass_number,
                    "compile_successes": compile_solved,
                    "compile_rate": compile_solved / total if total else 0,
                    "semantic_successes": semantic_solved,
                    "semantic_rate": semantic_solved / total if total else 0,
                }
            )
        known_costs = [item["cost_usd"] for item in results if isinstance(item.get("cost_usd"), (int, float))]
        known_loc = [item["loc_added"] for item in results if isinstance(item.get("loc_added"), int)]
        return {
            "id": self.id,
            "label": self.config.get("label", self.id),
            "group": self.config.get("group", "Experiments"),
            "comparison_default": bool(self.config.get("comparison_default", True)),
            "condition": self.config.get("condition", ""),
            "provider": self.config.get("provider", ""),
            "model": self.model,
            "judge_model": self.config.get("judge_model"),
            "judge_temperature": self.config.get("judge_temperature"),
            "judge_reasoning_effort": self.config.get("judge_reasoning_effort"),
            "color": self.config.get("color", "#67e8b1"),
            "live": bool(self.config.get("live")),
            "total": total,
            "outputs": outputs,
            "missing": total - outputs,
            "compile_success": compile_success,
            "compile_rate": compile_success / total if total else 0,
            "semantic_evaluated": semantic_evaluated,
            "semantic_success": semantic_success,
            "semantic_rate": semantic_success / total if total else 0,
            "semantic_rate_judged": semantic_success / semantic_evaluated if semantic_evaluated else None,
            "known_cost_usd": sum(known_costs),
            "cost_coverage": len(known_costs),
            "loc_added": sum(known_loc),
            "average_loc_added": sum(known_loc) / len(known_loc) if known_loc else None,
            "loc_coverage": len(known_loc),
            "max_tries": max_tries,
            "max_passes": max_passes,
            "try_curve": try_curve,
            "pass_curve": pass_curve,
        }

    def dashboard_state(self) -> dict[str, Any]:
        if self.work_root:
            pid_file = self.resolve("runner_pid_file")
            state = DashboardState(
                work_root=self.work_root,
                results_root=self.results_root,
                tasks=self.task_names,
                result_model_name=self.model,
                pid_file=pid_file,
            ).snapshot()
            results = {task: self.task_result(task) for task in self.task_names}
            state["summary"]["semantic_success"] = sum(
                item["semantic_success"] for item in results.values()
            )
            state["summary"]["semantic_evaluated"] = sum(
                item["semantic_evaluated"] for item in results.values()
            )
            state["summary"]["compiled_no_semantic_pass"] = sum(
                item["compile_success"] and not item["semantic_success"]
                for item in results.values()
            )
            state["summary"]["compile_failed"] = sum(
                item["output_present"] and not item["compile_success"]
                for item in results.values()
            )
            state["summary"]["missing_outputs"] = sum(
                not item["output_present"] for item in results.values()
            )
            for task in state["tasks"]:
                item = results[task["name"]]
                task["semantic_evaluated"] = item["semantic_evaluated"]
                task["semantic_success"] = item["semantic_success"]
                task["loc_added"] = item["loc_added"] if item["loc_added"] is not None else task.get("loc_added")
                if not item["output_present"]:
                    task["outcome_state"] = task["status"] if task["status"] != "queued" else "missing"
                elif not item["compile_success"]:
                    task["outcome_state"] = "compile_failed"
                    task["stage"] = "Lean compilation failed"
                elif item["semantic_success"]:
                    task["outcome_state"] = "semantic_success"
                    task["stage"] = "Lean verified · semantic full mark"
                else:
                    task["outcome_state"] = "compiled_no_semantic_pass"
                    task["stage"] = (
                        "Lean verified · semantic rejected"
                        if item["semantic_evaluated"]
                        else "Lean verified · semantic check pending"
                    )
            state["run_id"] = self.id
            return state

        summary = self.summary()
        task_summaries = []
        for name in self.task_names:
            item = self.task_result(name)
            if not item["output_present"]:
                status, stage = "queued", "Missing output"
                outcome_state = "missing"
            elif not item["compile_success"]:
                status, stage = "failed", "Lean compilation failed"
                outcome_state = "compile_failed"
            elif not item["semantic_evaluated"]:
                status, stage = "verified", "Lean verified · not semantically judged"
                outcome_state = "compiled_no_semantic_pass"
            elif item["semantic_success"]:
                status, stage = "verified", "Lean verified · semantic full mark"
                outcome_state = "semantic_success"
            else:
                status, stage = "verified", "Lean verified · semantic rejected"
                outcome_state = "compiled_no_semantic_pass"
            task_summaries.append(
                {
                    "name": name,
                    "status": status,
                    "stage": stage,
                    "duration_seconds": item["duration_ms"] / 1000 if item["duration_ms"] else None,
                    "thinking_tokens": item["event_stats"].get(
                        "thinking_tokens", (item["tokens"] or {}).get("reasoning", 0)
                    ),
                    "check_attempts": item["check_attempts"],
                    "lean_failures": item["event_stats"].get("lean_failures", 0),
                    "denied_tools": item["event_stats"].get("denied_tools", 0),
                    "turns": item["event_stats"].get("turns") or (
                        item["rounds"] + 1 if isinstance(item["rounds"], int) else None
                    ),
                    "cost_usd": item["cost_usd"],
                    "last_activity": None,
                    "semantic_evaluated": item["semantic_evaluated"],
                    "semantic_success": item["semantic_success"],
                    "loc_added": item["loc_added"],
                    "outcome_state": outcome_state,
                }
            )
        return {
            "run_id": self.id,
            "generated_at": None,
            "run": {
                "status": "completed" if summary["outputs"] == summary["total"] else "incomplete",
                "runner_pid": None,
                "current_task": None,
                "model": summary["label"],
                "effort": self.config.get("condition"),
                "work_root": None,
                "results_root": str(self.results_root),
            },
            "summary": {
                "total": summary["total"],
                "known_cost_usd": summary["known_cost_usd"],
                "queued": summary["missing"],
                "active": 0,
                "verified": summary["compile_success"],
                "failed": summary["outputs"] - summary["compile_success"],
                "interrupted": 0,
                "semantic_success": summary["semantic_success"],
                "semantic_evaluated": summary["semantic_evaluated"],
                "compiled_no_semantic_pass": summary["compile_success"] - summary["semantic_success"],
                "compile_failed": summary["outputs"] - summary["compile_success"],
                "missing_outputs": summary["missing"],
            },
            "tasks": task_summaries,
        }

    def dashboard_detail(self, task: str) -> dict[str, Any] | None:
        if task not in self.task_names:
            return None
        item = self.task_result(task)
        state = self.dashboard_state()
        task_summary = next(entry for entry in state["tasks"] if entry["name"] == task)
        task_source = self.source_for(task)
        task_work_root = self.work_root_for(task)
        if task_work_root:
            pid_file = self.resolve_from(task_source, "runner_pid_file")
            detail = DashboardState(
                work_root=task_work_root,
                results_root=self.results_root_for(task),
                tasks=self.tasks_for(task_source),
                result_model_name=self.model,
                pid_file=pid_file,
            ).task_detail(task)
            if detail is not None:
                detail["summary"] = task_summary
                detail["experiment"] = item
                detail["code"] = item["code"]
                if item["compile_success"] and item["semantic_evaluated"]:
                    detail["timeline"] = [
                        *(detail.get("timeline") or []),
                        {
                            "kind": "result",
                            "title": "Semantic judge "
                            + ("accepted" if item["semantic_success"] else "rejected"),
                            "body": item["semantic_analysis"],
                            "status": "verified" if item["semantic_success"] else "failed",
                        },
                    ]
                    detail["event_count"] = int(detail.get("event_count") or 0) + 1
                return detail

        timeline = []
        if item["output_present"]:
            timeline.append({"kind": "system", "title": "Model output saved", "body": f"{item['attempt_count']} independent pass(es) recorded.", "status": "done"})
            timeline.append(
                {
                    "kind": "result",
                    "title": "Lean compilation " + ("succeeded" if item["compile_success"] else "failed"),
                    "body": item["verifier_feedback"],
                    "status": "verified" if item["compile_success"] else "failed",
                }
            )
            if item["semantic_evaluated"]:
                timeline.append(
                    {
                        "kind": "result",
                        "title": "Semantic judge " + ("accepted" if item["semantic_success"] else "rejected"),
                        "body": item["semantic_analysis"],
                        "status": "verified" if item["semantic_success"] else "failed",
                    }
                )
        return {
            "summary": task_summary,
            "timeline": timeline,
            "diff": "",
            "code": item["code"],
            "stderr": "",
            "result": {"feedback": item["verifier_feedback"]},
            "experiment": item,
            "event_count": len(timeline),
        }


class ExperimentCatalog:
    def __init__(self, repo_root: Path, catalog_path: Path, data_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        configured = load_json(catalog_path)
        if not isinstance(configured, dict) or not isinstance(configured.get("experiments"), list):
            raise ValueError(f"Invalid experiment catalog: {catalog_path}")
        all_tasks = sorted(path.parent.name for path in data_root.glob("*/lean_spec.lean"))
        self.experiments = {
            str(item["id"]): Experiment(self.repo_root, item, all_tasks)
            for item in configured["experiments"]
        }

    def list(self) -> list[dict[str, Any]]:
        return [
            experiment.summary()
            for experiment in self.experiments.values()
            if not experiment.config.get("hidden")
        ]

    def get(self, experiment_id: str) -> Experiment | None:
        return self.experiments.get(experiment_id)

    def compare(self, ids: list[str], scope_mode: str = "common") -> dict[str, Any]:
        selected = [self.experiments[item] for item in ids if item in self.experiments]
        if not selected:
            selected = [
                experiment
                for experiment in self.experiments.values()
                if not experiment.config.get("hidden")
            ]
        if scope_mode == "common":
            common = set(selected[0].task_names)
            for experiment in selected[1:]:
                common.intersection_update(experiment.task_names)
            common_tasks = sorted(common)
            summaries = [experiment.summary(common_tasks) for experiment in selected]
        else:
            common_tasks = []
            summaries = [experiment.summary() for experiment in selected]

        task_union = (
            common_tasks
            if scope_mode == "common"
            else sorted({task for experiment in selected for task in experiment.task_names})
        )
        matrix = []
        for task in task_union:
            row = {"task": task, "models": {}}
            for experiment in selected:
                if task not in experiment.task_names:
                    row["models"][experiment.id] = {
                        "state": "missing",
                        "out_of_scope": True,
                    }
                    continue
                item = experiment.task_result(task)
                if not item["output_present"]:
                    state = "missing"
                elif not item["compile_success"]:
                    state = "compile_failed"
                elif item["semantic_success"]:
                    state = "semantic_success"
                else:
                    state = "compiled_no_semantic_pass"
                row["models"][experiment.id] = {
                    "state": state,
                    "success_try": item["success_try"],
                    "semantic_evaluated": item["semantic_evaluated"],
                    "out_of_scope": False,
                    "loc_added": item["loc_added"],
                }
            matrix.append(row)
        return {
            "scope_mode": scope_mode,
            "scope_count": len(common_tasks) if scope_mode == "common" else None,
            "scope_tasks": common_tasks,
            "experiments": summaries,
            "matrix": matrix,
        }
