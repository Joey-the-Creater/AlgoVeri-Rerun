"""Read-only projection of Claude Code JSONL runs for the local dashboard."""

from __future__ import annotations

import difflib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def pid_is_runner(pid: Any) -> bool:
    try:
        numeric_pid = int(pid)
        os.kill(numeric_pid, 0)
        command = Path(f"/proc/{numeric_pid}/cmdline").read_bytes().replace(b"\0", b" ")
        return b"run_claude_code_lean.py" in command
    except (TypeError, ValueError, OSError):
        return False


def iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def short_path(value: Any) -> str:
    path = Path(str(value or ""))
    return path.name or str(value or "")


def compact(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def line_change_counts(original: str, revised: str) -> dict[str, int]:
    """Count added and removed lines using the same matching model as a text diff."""
    added = 0
    removed = 0
    matcher = difflib.SequenceMatcher(a=original.splitlines(), b=revised.splitlines())
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation in {"insert", "replace"}:
            added += new_end - new_start
        if operation in {"delete", "replace"}:
            removed += old_end - old_start
    return {"added": added, "removed": removed}


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with path.open(errors="replace") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
    except OSError:
        pass
    return events


def parse_event_log(path: Path) -> dict[str, Any]:
    events = read_events(path)
    timeline: list[dict[str, Any]] = []
    tools: dict[str, dict[str, Any]] = {}
    thinking_tokens = 0
    check_attempts = 0
    lean_failures = 0
    lean_verified = False
    first_verified_check = None
    denied_tools = 0
    model = None
    session_id = None
    final: dict[str, Any] = {}
    first_timestamp = None
    last_timestamp = None

    def add(kind: str, title: str, body: str = "", **extra: Any) -> dict[str, Any]:
        item = {"kind": kind, "title": title, "body": compact(body)}
        item.update(extra)
        timeline.append(item)
        return item

    for event in events:
        timestamp = event.get("timestamp")
        if timestamp:
            first_timestamp = first_timestamp or timestamp
            last_timestamp = timestamp
        event_type = event.get("type")
        subtype = event.get("subtype")
        if event_type == "system" and subtype == "init":
            model = event.get("model")
            session_id = event.get("session_id")
            add("system", "Claude Code session started", model or "", timestamp=timestamp)
        elif event_type == "system" and subtype == "harness_pass_started":
            pass_number = int(event.get("pass_number") or 1)
            add(
                "system",
                f"Compiler pass {pass_number} started",
                "Initial agent session"
                if pass_number == 1
                else "Preserved-workspace repair session",
                timestamp=timestamp,
            )
        elif event_type == "system" and subtype == "harness_backtrack":
            add(
                "system",
                "Stagnation recovery",
                f"Fingerprint {event.get('fingerprint', '')}: {event.get('action', '')}",
                timestamp=timestamp,
                status="failed",
            )
        elif event_type == "system" and subtype == "thinking_tokens":
            thinking_tokens = max(thinking_tokens, int(event.get("estimated_tokens") or 0))
        elif event_type == "assistant":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text" and block.get("text"):
                    add("message", "Claude", block["text"], timestamp=timestamp)
                elif block_type == "tool_use":
                    tool_name = block.get("name", "Tool")
                    tool_input = block.get("input") or {}
                    detail = tool_input.get("command") or tool_input.get("file_path") or ""
                    if tool_name == "Bash" and str(detail).strip() == "./check.sh":
                        title = "Run Lean checker"
                        check_attempts += 1
                    elif tool_name == "Bash" and str(detail).strip().startswith("./leansearch "):
                        title = "Search Mathlib with Frenzymath LeanSearch"
                    elif tool_name in {"Read", "Edit", "Write"}:
                        title = f"{tool_name} {short_path(detail)}"
                    else:
                        title = f"{tool_name}: {compact(detail, 180)}"
                    body = ""
                    if tool_name == "Edit":
                        old = compact(tool_input.get("old_string"), 500)
                        new = compact(tool_input.get("new_string"), 500)
                        body = f"Before:\n{old}\n\nAfter:\n{new}"
                    item = add(
                        "tool",
                        title,
                        body,
                        timestamp=timestamp,
                        status="running",
                        tool=tool_name,
                    )
                    if block.get("id"):
                        tools[str(block["id"])] = item
        elif event_type == "user":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_id = str(block.get("tool_use_id") or "")
                item = tools.get(tool_id)
                content = str(block.get("content") or "")
                is_error = bool(block.get("is_error"))
                if item is None:
                    item = add("tool", "Tool result", timestamp=timestamp, status="error" if is_error else "done")
                item["status"] = "error" if is_error else "done"
                item["output"] = compact(content, 4000)
                if is_error:
                    denied_tools += 1
                if "LEAN VERIFIED" in content:
                    lean_verified = True
                    if first_verified_check is None:
                        first_verified_check = check_attempts
                    item["status"] = "verified"
                if "LEAN VERIFICATION FAILED" in content:
                    lean_failures += 1
                    item["status"] = "failed"
        elif event_type == "result":
            final = event
            add(
                "result",
                f"Agent finished: {event.get('subtype', 'result')}",
                event.get("result") or "",
                timestamp=timestamp,
                status="error" if event.get("is_error") else "done",
            )

    file_timestamp = path.stat().st_mtime if path.exists() else None
    return {
        "event_count": len(events),
        "timeline": timeline[-250:],
        "thinking_tokens": thinking_tokens,
        "check_attempts": check_attempts,
        "lean_failures": lean_failures,
        "lean_verified": lean_verified,
        "first_verified_check": first_verified_check,
        "denied_tools": denied_tools,
        "model": model,
        "session_id": session_id,
        "final": final,
        "turns": final.get("num_turns"),
        "cost_usd": final.get("total_cost_usd"),
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "last_activity": iso_from_timestamp(file_timestamp) if file_timestamp else None,
    }


def result_details(path: Path) -> dict[str, Any]:
    value = load_json(path)
    attempts = value if isinstance(value, list) else [value]
    attempts = [item for item in attempts if isinstance(item, dict)]
    if not attempts:
        return {}
    chosen = next((item for item in attempts if item.get("verified") is True), attempts[-1])
    details = chosen.get("details") or {}
    agent = details.get("agent") or {}
    verifier = details.get("verifier_response") or {}
    return {
        "verified": chosen.get("verified") is True,
        "turns": agent.get("num_turns"),
        "cost_usd": agent.get("total_cost_usd"),
        "duration_ms": agent.get("duration_ms"),
        "timed_out": agent.get("timed_out"),
        "comment": (details.get("llm_response") or {}).get("comment", ""),
        "feedback": verifier.get("feedback", ""),
        "tokens": details.get("tokens") or {},
        "provenance": details.get("provenance") or {},
        "lastdance_artifacts": details.get("lastdance_artifacts") or {},
        "agent": agent,
    }


class DashboardState:
    def __init__(
        self,
        work_root: Path,
        results_root: Path,
        tasks: list[str] | None = None,
        result_model_name: str = "claude-code-opus-5",
        pid_file: Path | None = None,
    ) -> None:
        self.work_root = work_root.resolve()
        self.results_root = results_root.resolve()
        self.explicit_tasks = tasks or []
        self.result_model_name = result_model_name
        self.pid_file = pid_file.resolve() if pid_file else None
        self._event_cache: dict[str, tuple[int, int, dict[str, Any]]] = {}

    @property
    def manifest(self) -> dict[str, Any]:
        value = load_json(self.work_root / "run_manifest.json")
        return value if isinstance(value, dict) else {}

    def task_names(self) -> list[str]:
        # An experiment catalog defines the stable reporting denominator. A
        # targeted retry may replace run_manifest.json with only its subset,
        # but must not hide previously saved results from that experiment.
        if self.explicit_tasks:
            return self.explicit_tasks
        manifest_tasks = self.manifest.get("tasks")
        if isinstance(manifest_tasks, list) and manifest_tasks:
            return [str(item) for item in manifest_tasks]
        names = {path.name for path in self.work_root.iterdir() if path.is_dir()} if self.work_root.exists() else set()
        result_dir = self.results_root / "lean"
        prefix = self.result_model_name + "_"
        suffix = "_lean.json"
        if result_dir.exists():
            for path in result_dir.glob(f"{self.result_model_name}_*_lean.json"):
                if path.name.startswith(prefix) and path.name.endswith(suffix):
                    names.add(path.name[len(prefix) : -len(suffix)])
        return sorted(names)

    def runner_pid(self) -> int | None:
        pid = self.manifest.get("runner_pid")
        if pid is None and self.pid_file:
            try:
                pid = int(self.pid_file.read_text().strip())
            except (OSError, ValueError):
                return None
        try:
            return int(pid) if pid is not None else None
        except (TypeError, ValueError):
            return None

    def events_for(self, name: str) -> dict[str, Any]:
        path = self.work_root / name / "agent_events.jsonl"
        try:
            stat = path.stat()
        except OSError:
            return parse_event_log(path)
        cached = self._event_cache.get(name)
        key = (stat.st_mtime_ns, stat.st_size)
        if cached and cached[:2] == key:
            return cached[2]
        parsed = parse_event_log(path)
        self._event_cache[name] = (key[0], key[1], parsed)
        return parsed

    def result_path(self, name: str) -> Path:
        return self.results_root / "lean" / f"{self.result_model_name}_{name}_lean.json"

    def task_summary(self, name: str, runner_active: bool, current_task: str | None) -> dict[str, Any]:
        workspace = self.work_root / name
        event_path = workspace / "agent_events.jsonl"
        result = result_details(self.result_path(name))
        events = self.events_for(name) if event_path.exists() else {}
        if runner_active and current_task == name:
            status = "active"
        elif result:
            status = "verified" if result.get("verified") else "failed"
        elif event_path.exists():
            status = "active" if runner_active and current_task == name else "interrupted"
        else:
            status = "queued"

        if status in {"verified", "failed"}:
            stage = "Saved result"
        elif events.get("lean_verified"):
            stage = "Lean verified; awaiting save"
        elif events.get("check_attempts"):
            stage = "Repairing after Lean check"
        elif events.get("thinking_tokens"):
            stage = "Reasoning"
        elif event_path.exists():
            stage = "Starting agent"
        else:
            stage = "Waiting"

        duration_seconds = None
        if result.get("duration_ms") is not None:
            duration_seconds = round(float(result["duration_ms"]) / 1000, 1)
        elif event_path.exists():
            try:
                start = (workspace / "Original.lean").stat().st_mtime
                end = event_path.stat().st_mtime
                if status == "active":
                    end = datetime.now().timestamp()
                duration_seconds = max(0, round(end - start, 1))
            except OSError:
                pass

        loc_added = None
        loc_removed = None
        try:
            changes = line_change_counts(
                (workspace / "Original.lean").read_text(),
                (workspace / "Solution.lean").read_text(),
            )
            loc_added = changes["added"]
            loc_removed = changes["removed"]
        except OSError:
            pass

        return {
            "name": name,
            "status": status,
            "stage": stage,
            "duration_seconds": duration_seconds,
            "thinking_tokens": events.get("thinking_tokens", 0),
            "check_attempts": events.get("check_attempts", 0),
            "lean_failures": events.get("lean_failures", 0),
            "denied_tools": events.get("denied_tools", 0),
            "turns": result.get("turns", events.get("turns")),
            "cost_usd": result.get("cost_usd", events.get("cost_usd")),
            "last_activity": events.get("last_activity"),
            "loc_added": loc_added,
            "loc_removed": loc_removed,
        }

    def snapshot(self) -> dict[str, Any]:
        manifest = self.manifest
        pid = self.runner_pid()
        runner_active = pid_is_runner(pid)
        current_task = manifest.get("current_task")
        names = self.task_names()
        if runner_active and not current_task:
            unfinished: list[tuple[float, str]] = []
            for name in names:
                event_path = self.work_root / name / "agent_events.jsonl"
                if event_path.exists() and not self.result_path(name).exists():
                    try:
                        unfinished.append((event_path.stat().st_mtime, name))
                    except OSError:
                        pass
            if unfinished:
                current_task = max(unfinished)[1]
        summaries = [self.task_summary(name, runner_active, current_task) for name in names]
        counts = {key: 0 for key in ("queued", "active", "verified", "failed", "interrupted")}
        for item in summaries:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        costs = [item["cost_usd"] for item in summaries if isinstance(item.get("cost_usd"), (int, float))]
        run_status = "running" if runner_active else manifest.get("state", "stopped")
        if run_status == "running" and not runner_active:
            run_status = "interrupted"
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run": {
                "status": run_status,
                "runner_pid": pid,
                "current_task": current_task,
                "model": manifest.get("model"),
                "effort": manifest.get("effort"),
                "started_at": manifest.get("started_at"),
                "finished_at": manifest.get("finished_at"),
                "max_budget_usd": manifest.get("max_budget_usd"),
                "timeout_seconds": manifest.get("timeout_seconds"),
                "work_root": str(self.work_root),
                "results_root": str(self.results_root),
            },
            "summary": {"total": len(names), "known_cost_usd": sum(costs), **counts},
            "tasks": summaries,
        }

    def task_detail(self, name: str) -> dict[str, Any] | None:
        if name not in self.task_names():
            return None
        snapshot = self.snapshot()
        summary = next(item for item in snapshot["tasks"] if item["name"] == name)
        workspace = self.work_root / name
        events = self.events_for(name)
        result = result_details(self.result_path(name))
        diff = ""
        loc_added = None
        loc_removed = None
        try:
            original_text = (workspace / "Original.lean").read_text()
            solution_text = (workspace / "Solution.lean").read_text()
            original = original_text.splitlines()
            solution = solution_text.splitlines()
            diff = "\n".join(
                difflib.unified_diff(original, solution, fromfile="Original.lean", tofile="Solution.lean", lineterm="")
            )
            changes = line_change_counts(original_text, solution_text)
            loc_added = changes["added"]
            loc_removed = changes["removed"]
        except OSError:
            pass
        try:
            stderr = (workspace / "agent_stderr.log").read_text()[-6000:]
        except OSError:
            stderr = ""
        robust_artifacts: dict[str, Any] = {}
        for key, filename in (
            ("algorithm_plan", "AlgorithmPlan.md"),
            ("proof_state", "ProofState.md"),
            ("diagnostics", "Diagnostics.md"),
        ):
            try:
                robust_artifacts[key] = (workspace / filename).read_text()[-12000:]
            except OSError:
                pass
        query_path = workspace / ".lastdance" / "leansearch_queries.jsonl"
        if query_path.is_file():
            robust_artifacts["leansearch_queries"] = read_events(query_path)[-50:]
        return {
            "summary": summary,
            "timeline": events.get("timeline", []),
            "diff": diff,
            "stderr": stderr,
            "result": result,
            "session_id": events.get("session_id"),
            "model": events.get("model"),
            "event_count": events.get("event_count", 0),
            "loc_added": loc_added,
            "loc_removed": loc_removed,
            "robust_artifacts": robust_artifacts,
        }
