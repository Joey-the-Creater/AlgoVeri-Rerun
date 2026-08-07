#!/usr/bin/env python3
"""Run AlgoVeri Lean tasks with Claude Code as a tool-using coding agent."""

from __future__ import annotations

import argparse
import json
import os
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent.lean_candidate import (
    CandidateValidationError,
    has_teacher_owned_sorry,
    merge_candidate_sections,
)
from src.verifiers.lean_verifier import LeanVerifier


DEFAULT_DATA_ROOT = REPO_ROOT / "algoveri_data"


def task_directories(
    data_root: Path, task: str | None, tasks: str | None = None
) -> list[Path]:
    if task and tasks:
        raise ValueError("Use either --task or --tasks, not both")
    if tasks:
        names = tasks.replace(",", " ").split()
        if not names:
            raise ValueError("--tasks did not contain any task names")
        names = list(dict.fromkeys(names))
        paths = [data_root / name for name in names]
    elif task:
        paths = [data_root / task]
    else:
        paths = sorted(path.parent for path in data_root.glob("*/lean_spec.lean"))
    valid = [
        path
        for path in paths
        if (path / "lean_spec.lean").is_file() and (path / "lean_nl.txt").is_file()
    ]
    if len(valid) != len(paths):
        invalid = [path.name for path in paths if path not in valid]
        raise FileNotFoundError(
            "Lean benchmark task(s) not found or incomplete: " + ", ".join(invalid)
        )
    return valid


def existing_result(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, (dict, list)) else None


def is_verified(value: dict[str, Any] | list[Any]) -> bool:
    attempts = value if isinstance(value, list) else [value]
    return any(isinstance(item, dict) and item.get("verified") is True for item in attempts)


def latest_verifier_feedback(value: dict[str, Any] | list[Any] | None) -> str:
    if value is None:
        return "Previous independent verification failed."
    attempts = value if isinstance(value, list) else [value]
    for item in reversed(attempts):
        if not isinstance(item, dict):
            continue
        verifier = (item.get("details") or {}).get("verifier_response") or {}
        feedback = verifier.get("feedback")
        if feedback:
            return str(feedback)
    return "Previous independent verification failed."


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_workspace(
    workspace: Path,
    task_name: str,
    natural_language: str,
    formal_code: str,
    config_path: Path,
    preserve_solution: bool = False,
    preserve_logs: bool = False,
) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "Original.lean").write_text(formal_code)
    if not preserve_solution or not (workspace / "Solution.lean").is_file():
        (workspace / "Solution.lean").write_text(formal_code)
    (workspace / "TASK.md").write_text(
        f"# AlgoVeri task: {task_name}\n\n{natural_language.rstrip()}\n"
    )
    if not preserve_logs:
        for stale_log in ("agent_events.jsonl", "agent_stderr.log"):
            try:
                (workspace / stale_log).unlink()
            except FileNotFoundError:
                pass
    python_bin = REPO_ROOT / ".venv" / "bin" / "python"
    if not python_bin.is_file():
        python_bin = Path(sys.executable)
    checker = REPO_ROOT / "scripts" / "check_claude_code_candidate.py"
    command = " ".join(
        shlex.quote(str(part))
        for part in (
            python_bin,
            checker,
            "--original",
            workspace / "Original.lean",
            "--candidate",
            workspace / "Solution.lean",
            "--merged",
            workspace / "Merged.lean",
            "--config",
            config_path,
            "--task",
            task_name,
        )
    )
    check_path = workspace / "check.sh"
    check_path.write_text(f"#!/usr/bin/env bash\nset -uo pipefail\n{command}\n")
    check_path.chmod(0o755)

    guard = REPO_ROOT / "scripts" / "claude_code_tool_guard.py"
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": str(python_bin),
                            "args": [str(guard)],
                            "timeout": 10,
                        }
                    ],
                }
            ]
        }
    }
    (workspace / "claude_settings.json").write_text(json.dumps(settings, indent=2) + "\n")


SEMANTIC_AUDIT = """Before declaring success, perform a semantic audit against every requirement in
TASK.md. In particular, verify that all named preconditions and edge cases are
implemented, that you did not weaken the requested problem or allow an easier
variant, and that every mathematical helper/specification is genuine rather than
a placeholder such as an unjustified `:= 0` or `:= True`. For nonempty-input
problems, explicitly consider adversarial inputs such as all-negative values.
After any audit-driven edit, run ./check.sh again."""


def agent_prompt(task_name: str) -> str:
    return f"""Solve the AlgoVeri Lean 4 task {task_name} in this directory.

Start by reading TASK.md and Solution.lean. You may also inspect Original.lean,
Merged.lean, and check.sh, but edit only Solution.lean and change content only
inside these four marker pairs: auxcode, code, lemma, and proof. Preserve every
marker. Do not edit Original.lean, TASK.md, check.sh, or Merged.lean.

Implement the exact algorithm described in TASK.md and prove its stated
postcondition. Semantic correctness matters: do not substitute a different
algorithm, a specification oracle, brute-force enumeration, sorting when a
different algorithm is requested, Nat.find, Classical.choose, or decide over the
target property. Do not use sorry, admit, axioms, constants, partial, unsafe,
extern, or implemented_by in an editable section. Teacher-provided sorry outside
the four editable sections is permitted and must remain unchanged.

Your budget is limited. Produce a coherent candidate without leaving editable
`sorry` placeholders and run ./check.sh early, before extended proof polishing.
Use its Lean errors to revise Solution.lean, and repeat until it prints LEAN
VERIFIED. A prior successful check is invalid after another edit: re-run it.

{SEMANTIC_AUDIT}

Do not use network access, Git, package installation, or shell commands other
than ./check.sh and safe workspace inspection (`pwd`, `ls`, or `ls -la`). Stop
when verification succeeds and the semantic audit is complete, or when you
genuinely cannot make further progress.
"""


def repair_prompt(task_name: str, pass_number: int, feedback: str) -> str:
    return f"""Repair the existing AlgoVeri Lean 4 solution for {task_name}.
This is compiler-repair pass {pass_number}. The previous session's Solution.lean
has been preserved; improve it in place rather than restarting from the original
scaffold.

The harness independently merged the editable sections and rejected the final
candidate with this exact feedback:

--- BEGIN INDEPENDENT VERIFIER FEEDBACK ---
{feedback.strip() or 'No verifier details were returned.'}
--- END INDEPENDENT VERIFIER FEEDBACK ---

Read TASK.md and the current Solution.lean. Remove every editable prohibited
placeholder, address the reported Lean errors, and run ./check.sh early. Continue
until LEAN VERIFIED. Edit only the auxcode, code, lemma, and proof marker regions
of Solution.lean; do not edit any harness or teacher-owned file.

{SEMANTIC_AUDIT}

Do not use network access, Git, package installation, or shell commands other
than ./check.sh and safe workspace inspection (`pwd`, `ls`, or `ls -la`).
"""


def event_progress(event: dict[str, Any], state: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    event_type = event.get("type")
    if event_type == "system":
        subtype = event.get("subtype", "event")
        if subtype == "thinking_tokens":
            estimate = int(event.get("estimated_tokens") or 0)
            previous = int(state.get("thinking_reported") or 0)
            if estimate >= previous + 1000:
                state["thinking_reported"] = estimate
                messages.append(f"[agent thinking] approximately {estimate:,} tokens")
            return messages
        model = event.get("model")
        if subtype == "task_started":
            messages.append(f"[tool running] {event.get('description', 'background task')}")
        elif subtype == "task_notification":
            messages.append(
                f"[tool {event.get('status', 'updated')}] "
                f"{event.get('summary', event.get('description', 'background task'))}"
            )
        else:
            messages.append(
                f"[agent system] {subtype}" + (f" ({model})" if model else "")
            )
        return messages
    if event_type == "assistant":
        blocks = (event.get("message") or {}).get("content") or []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                value = " ".join(str(block.get("text") or "").split())
                if value:
                    messages.append(f"[agent] {value[:600]}")
            if block.get("type") == "tool_use":
                name = block.get("name", "tool")
                tool_input = block.get("input") or {}
                detail = tool_input.get("command") or tool_input.get("file_path") or ""
                messages.append(f"[agent tool] {name}: {str(detail)[:240]}")
        return messages
    if event_type == "user":
        blocks = (event.get("message") or {}).get("content") or []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            content = str(block.get("content") or "").strip()
            if block.get("is_error"):
                messages.append(f"[tool blocked/error] {' '.join(content.split())[:500]}")
            elif "LEAN VERIFIED" in content:
                messages.append("[lean check] LEAN VERIFIED")
            elif "LEAN VERIFICATION FAILED" in content:
                tail = " ".join(content.splitlines()[-4:])
                messages.append(f"[lean check] FAILED — {tail[:500]}")
        return messages
    if event_type == "result":
        subtype = event.get("subtype", "result")
        turns = event.get("num_turns", "?")
        cost = event.get("total_cost_usd")
        cost_text = f", ${cost:.4f}" if isinstance(cost, (int, float)) else ""
        messages.append(f"[agent result] {subtype}, {turns} turns{cost_text}")
    return messages


def run_claude(
    claude_bin: str,
    workspace: Path,
    model: str,
    effort: str,
    timeout_seconds: int,
    max_budget_usd: float | None,
    prompt: str,
    pass_number: int,
) -> tuple[int, bool, dict[str, Any], str]:
    command = [
        claude_bin,
        "--print",
        prompt,
        "--model",
        model,
        "--effort",
        effort,
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--no-chrome",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--settings",
        str(workspace / "claude_settings.json"),
        "--tools",
        "Read,Edit,Write,Bash",
        "--allowedTools",
        "Read",
        "Edit",
        "Write",
        "Bash(./check.sh)",
        "Bash(pwd)",
        "Bash(ls)",
        "Bash(ls *)",
        "--permission-mode",
        "dontAsk",
    ]
    if max_budget_usd is not None:
        command.extend(("--max-budget-usd", str(max_budget_usd)))

    event_path = workspace / "agent_events.jsonl"
    stderr_path = workspace / "agent_stderr.log"
    final_event: dict[str, Any] = {}
    stderr_chunks: list[str] = []
    timed_out = False
    deadline = time.monotonic() + timeout_seconds
    progress_state: dict[str, Any] = {}

    with event_path.open("a") as event_file, stderr_path.open("a") as stderr_file:
        event_file.write(
            json.dumps(
                {
                    "type": "system",
                    "subtype": "harness_pass_started",
                    "pass_number": pass_number,
                    "timestamp": utc_now(),
                }
            )
            + "\n"
        )
        event_file.flush()
        stderr_file.write(f"\n=== compiler pass {pass_number} ===\n")
        stderr_file.flush()
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert process.stdout is not None and process.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")

        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0 and process.poll() is None:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                continue
            ready = selector.select(timeout=min(max(remaining, 0.0), 1.0))
            if not ready and process.poll() is not None:
                # A final read drains both pipes after process exit.
                ready = [(key, selectors.EVENT_READ) for key in selector.get_map().values()]
            for key, _ in ready:
                line = key.fileobj.readline()
                if not line:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stderr":
                    stderr_file.write(line)
                    stderr_file.flush()
                    stderr_chunks.append(line)
                    print(f"[claude stderr] {line.rstrip()}", flush=True)
                    continue
                event_file.write(line)
                event_file.flush()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[claude stdout] {line.rstrip()}", flush=True)
                    continue
                if event.get("type") == "result":
                    final_event = event
                for progress in event_progress(event, progress_state):
                    print(progress, flush=True)

        returncode = process.wait()
    return returncode, timed_out, final_event, "".join(stderr_chunks)


def token_summary(event: dict[str, Any]) -> dict[str, int]:
    usage = event.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    input_tokens += int(usage.get("cache_creation_input_tokens") or 0)
    input_tokens += int(usage.get("cache_read_input_tokens") or 0)
    return {
        "input": input_tokens,
        "output": int(usage.get("output_tokens") or 0),
        "reasoning": 0,
    }


def parsed_verifier_response(response: dict[str, Any]) -> dict[str, Any]:
    raw = response.get("raw")
    if response.get("ok"):
        return {"verified": True, "feedback": "Verified successfully.", "raw": raw}
    if raw:
        feedback = f"Stdout:\n{raw.get('stdout', '')}\n\nStderr:\n{raw.get('stderr', '')}"
    else:
        feedback = str(response.get("reason") or "Lean verification failed")
    return {"verified": False, "feedback": feedback, "raw": raw}


def make_result(
    task_name: str,
    workspace: Path,
    original: str,
    config_path: Path,
    model: str,
    effort: str,
    cli_version: str,
    returncode: int,
    timed_out: bool,
    final_event: dict[str, Any],
    stderr: str,
    pass_number: int = 1,
    budget_usd: float | None = None,
    prompt_kind: str = "initial",
) -> dict[str, Any]:
    candidate_path = workspace / "Solution.lean"
    validation_error = ""
    merged_code = ""
    try:
        candidate = candidate_path.read_text()
        merged_code = merge_candidate_sections(original, candidate).code
        verification = LeanVerifier(config_path=str(config_path)).verify(
            source=merged_code,
            spec=task_name,
            filename=f"claude_code_{task_name}_final",
        )
    except (OSError, CandidateValidationError) as exc:
        validation_error = str(exc)
        verification = {
            "ok": False,
            "reason": f"Candidate validation failed: {exc}",
            "raw": None,
            "file": None,
        }

    parsed_verifier = parsed_verifier_response(verification)
    final_text = final_event.get("result") or ""
    if validation_error and not final_text:
        final_text = f"Candidate validation failed: {validation_error}"
    if stderr and not final_text:
        final_text = stderr[-4000:]
    turns = int(final_event.get("num_turns") or 0)
    agent_metadata = {
        "kind": "claude-code",
        "cli_version": cli_version,
        "model": model,
        "effort": effort,
        "session_id": final_event.get("session_id"),
        "subtype": final_event.get("subtype"),
        "is_error": final_event.get("is_error"),
        "total_cost_usd": final_event.get("total_cost_usd"),
        "duration_ms": final_event.get("duration_ms"),
        "duration_api_ms": final_event.get("duration_api_ms"),
        "num_turns": turns,
        "returncode": returncode,
        "timed_out": timed_out,
        "event_log": str(workspace / "agent_events.jsonl"),
        "pass_number": pass_number,
        "prompt_kind": prompt_kind,
        "budget_usd": budget_usd,
    }
    return {
        "verified": parsed_verifier["verified"],
        "details": {
            "rounds": max(turns - 1, 0),
            "llm_response": {"code": merged_code, "comment": final_text},
            "verifier_response": parsed_verifier,
            "history": [],
            "tokens": token_summary(final_event),
            "agent": agent_metadata,
        },
    }


def combine_pass_results(pass_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the final candidate result with aggregate multi-session metadata."""
    if not pass_results:
        raise ValueError("at least one pass result is required")
    final = json.loads(json.dumps(pass_results[-1]))
    details = final["details"]
    sessions = [(item.get("details") or {}).get("agent") or {} for item in pass_results]
    token_sets = [(item.get("details") or {}).get("tokens") or {} for item in pass_results]
    total_turns = sum(int(item.get("num_turns") or 0) for item in sessions)
    known_costs = [
        float(item["total_cost_usd"])
        for item in sessions
        if isinstance(item.get("total_cost_usd"), (int, float))
    ]
    known_durations = [
        int(item["duration_ms"])
        for item in sessions
        if isinstance(item.get("duration_ms"), (int, float))
    ]
    known_api_durations = [
        int(item["duration_api_ms"])
        for item in sessions
        if isinstance(item.get("duration_api_ms"), (int, float))
    ]
    aggregate_agent = details.get("agent") or {}
    aggregate_agent.update(
        {
            "compiler_passes": len(pass_results),
            "sessions": sessions,
            "num_turns": total_turns,
            "total_cost_usd": sum(known_costs) if known_costs else None,
            "duration_ms": sum(known_durations) if known_durations else None,
            "duration_api_ms": sum(known_api_durations) if known_api_durations else None,
            "timed_out": any(bool(item.get("timed_out")) for item in sessions),
        }
    )
    details["agent"] = aggregate_agent
    details["rounds"] = max(total_turns - 1, 0)
    details["tokens"] = {
        key: sum(int(item.get(key) or 0) for item in token_sets)
        for key in ("input", "output", "reasoning")
    }
    details["history"] = [
        {
            "compiler_pass": index,
            "verified": item.get("verified") is True,
            "verifier_response": (item.get("details") or {}).get("verifier_response"),
            "agent": (item.get("details") or {}).get("agent"),
        }
        for index, item in enumerate(pass_results, start=1)
    ]
    return final


def claude_version(claude_bin: str) -> str:
    try:
        process = subprocess.run(
            [claude_bin, "--version"], capture_output=True, text=True, timeout=15
        )
        return (process.stdout or process.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", help="Run one task; omit to run all Lean tasks")
    parser.add_argument(
        "--tasks", help="Run a comma- or whitespace-separated ordered list of tasks"
    )
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--result-model-name", default="claude-code-opus-5")
    parser.add_argument(
        "--effort", choices=("low", "medium", "high", "xhigh", "max"), default="medium"
    )
    parser.add_argument("--results-root", default="results/claude_code_opus5")
    parser.add_argument("--work-root", default=".agent_runs/claude_code_opus5")
    parser.add_argument("--config", default="test/config_test.yaml")
    parser.add_argument("--claude-bin", default=shutil.which("claude") or "claude")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--max-budget-usd", type=float, help="Initial Claude session budget")
    parser.add_argument(
        "--repair-budget-usd",
        type=float,
        help="Budget for each compiler-repair session; defaults to the initial budget",
    )
    parser.add_argument(
        "--compiler-repair-passes",
        type=int,
        default=1,
        help="Additional preserved-workspace sessions after final verification failures",
    )
    parser.add_argument(
        "--exclude-teacher-sorry",
        action="store_true",
        help="Run only tasks with no sorry outside the four editable sections",
    )
    parser.add_argument(
        "--reuse-workspace",
        action="store_true",
        help="Preserve an existing Solution.lean and event log for targeted reruns",
    )
    parser.add_argument("--rerun", action="store_true", help="Rerun even if a result exists")
    parser.add_argument(
        "--rerun-failed", action="store_true", help="Rerun existing non-verified results"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.rerun and args.rerun_failed:
        parser.error("--rerun and --rerun-failed are mutually exclusive")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.max_budget_usd is not None and args.max_budget_usd <= 0:
        parser.error("--max-budget-usd must be positive")
    if args.repair_budget_usd is not None and args.repair_budget_usd <= 0:
        parser.error("--repair-budget-usd must be positive")
    if args.compiler_repair_passes < 0:
        parser.error("--compiler-repair-passes cannot be negative")
    return args


def main() -> int:
    args = parse_args()
    repair_budget = (
        args.repair_budget_usd
        if args.repair_budget_usd is not None
        else args.max_budget_usd
    )
    data_root = Path(args.data_root).expanduser().resolve()
    tasks = task_directories(data_root, args.task, args.tasks)
    excluded_teacher_sorry: list[str] = []
    if args.exclude_teacher_sorry:
        clean_tasks: list[Path] = []
        for task_path in tasks:
            source = (task_path / "lean_spec.lean").read_text()
            if has_teacher_owned_sorry(source):
                excluded_teacher_sorry.append(task_path.name)
            else:
                clean_tasks.append(task_path)
        tasks = clean_tasks
        print(
            f"Excluded {len(excluded_teacher_sorry)} task(s) with teacher-owned sorry.",
            flush=True,
        )
        if excluded_teacher_sorry:
            print("Excluded: " + ", ".join(excluded_teacher_sorry), flush=True)
    if not tasks:
        print("No Lean tasks remain after filtering.", file=sys.stderr)
        return 2
    print(f"Selected {len(tasks)} Lean task(s).", flush=True)
    if args.dry_run:
        for task in tasks:
            print(task.name)
        return 0

    claude_bin = shutil.which(args.claude_bin) or args.claude_bin
    if not Path(claude_bin).is_file() and shutil.which(claude_bin) is None:
        print(f"Claude Code executable not found: {args.claude_bin}", file=sys.stderr)
        return 2

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path
    config_path = config_path.resolve()
    results_dir = Path(args.results_root).expanduser()
    if not results_dir.is_absolute():
        results_dir = REPO_ROOT / results_dir
    results_dir = results_dir / "lean"
    work_root = Path(args.work_root).expanduser()
    if not work_root.is_absolute():
        work_root = REPO_ROOT / work_root
    work_root.mkdir(parents=True, exist_ok=True)
    manifest_path = work_root / "run_manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "state": "running",
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "runner_pid": os.getpid(),
        "tasks": [task.name for task in tasks],
        "current_task": None,
        "completed_count": 0,
        "model": args.model,
        "result_model_name": args.result_model_name,
        "effort": args.effort,
        "timeout_seconds": args.timeout_seconds,
        "max_budget_usd": args.max_budget_usd,
        "repair_budget_usd": repair_budget,
        "compiler_repair_passes": args.compiler_repair_passes,
        "exclude_teacher_sorry": args.exclude_teacher_sorry,
        "excluded_teacher_sorry": excluded_teacher_sorry,
        "reuse_workspace": args.reuse_workspace,
        "results_root": str(results_dir.parent),
        "work_root": str(work_root),
    }
    write_json_atomic(manifest_path, manifest)
    version = claude_version(claude_bin)
    print(f"Claude Code: {version}", flush=True)

    failures = 0
    for index, task_dir in enumerate(tasks, start=1):
        task_name = task_dir.name
        result_path = results_dir / f"{args.result_model_name}_{task_name}_lean.json"
        current = existing_result(result_path) if result_path.exists() else None
        should_skip = current is not None and not args.rerun
        if should_skip and args.rerun_failed and not is_verified(current):
            should_skip = False
        if should_skip:
            print(f"[{index}/{len(tasks)}] [skip existing] {task_name}", flush=True)
            manifest["completed_count"] = index
            manifest["updated_at"] = utc_now()
            write_json_atomic(manifest_path, manifest)
            continue

        print(f"[{index}/{len(tasks)}] [agent start] {task_name}", flush=True)
        manifest["current_task"] = task_name
        manifest["current_index"] = index
        manifest["current_started_at"] = utc_now()
        manifest["updated_at"] = utc_now()
        write_json_atomic(manifest_path, manifest)
        original = (task_dir / "lean_spec.lean").read_text()
        natural = (task_dir / "lean_nl.txt").read_text()
        workspace = work_root / task_name
        reused_workspace = args.reuse_workspace and (workspace / "Solution.lean").is_file()
        write_workspace(
            workspace,
            task_name,
            natural,
            original,
            config_path,
            preserve_solution=reused_workspace,
            preserve_logs=reused_workspace,
        )
        if reused_workspace:
            print(f"[{task_name}] [reusing existing workspace]", flush=True)
        pass_results: list[dict[str, Any]] = []
        feedback = latest_verifier_feedback(current) if reused_workspace else ""
        total_passes = 1 + args.compiler_repair_passes
        for pass_number in range(1, total_passes + 1):
            is_repair = pass_number > 1 or reused_workspace
            budget = repair_budget if is_repair else args.max_budget_usd
            prompt = (
                repair_prompt(task_name, pass_number, feedback)
                if is_repair
                else agent_prompt(task_name)
            )
            manifest["current_compiler_pass"] = pass_number
            manifest["updated_at"] = utc_now()
            write_json_atomic(manifest_path, manifest)
            print(
                f"[{task_name}] [compiler pass {pass_number}/{total_passes}] "
                + (f"budget ${budget:g}" if budget is not None else "uncapped budget"),
                flush=True,
            )
            try:
                returncode, timed_out, final_event, stderr = run_claude(
                    claude_bin=claude_bin,
                    workspace=workspace,
                    model=args.model,
                    effort=args.effort,
                    timeout_seconds=args.timeout_seconds,
                    max_budget_usd=budget,
                    prompt=prompt,
                    pass_number=pass_number,
                )
                pass_result = make_result(
                    task_name=task_name,
                    workspace=workspace,
                    original=original,
                    config_path=config_path,
                    model=args.model,
                    effort=args.effort,
                    cli_version=version,
                    returncode=returncode,
                    timed_out=timed_out,
                    final_event=final_event,
                    stderr=stderr,
                    pass_number=pass_number,
                    budget_usd=budget,
                    prompt_kind="compiler_repair" if is_repair else "initial",
                )
            except Exception as exc:
                print(
                    f"[{task_name}] pass {pass_number} runner error: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                pass_result = {
                    "verified": False,
                    "details": {
                        "rounds": 0,
                        "llm_response": {"code": "", "comment": f"Runner error: {exc}"},
                        "verifier_response": {
                            "verified": False,
                            "feedback": f"Runner error: {exc}",
                            "raw": None,
                        },
                        "history": [],
                        "tokens": {"input": 0, "output": 0, "reasoning": 0},
                        "agent": {
                            "kind": "claude-code",
                            "cli_version": version,
                            "model": args.model,
                            "effort": args.effort,
                            "runner_error": str(exc),
                            "pass_number": pass_number,
                            "prompt_kind": "compiler_repair" if is_repair else "initial",
                            "budget_usd": budget,
                        },
                    },
                }
            pass_results.append(pass_result)
            if pass_result.get("verified") is True:
                print(f"[{task_name}] [independent verification passed]", flush=True)
                break
            verifier_response = (pass_result.get("details") or {}).get(
                "verifier_response"
            ) or {}
            feedback = verifier_response.get(
                "feedback", "Independent verification failed"
            )
            print(
                f"[{task_name}] [independent verification failed] "
                f"{str(feedback).splitlines()[0][:300]}",
                flush=True,
            )
        result = combine_pass_results(pass_results)
        write_json_atomic(result_path, result)
        status = "verified" if result.get("verified") else "failed"
        print(f"[{index}/{len(tasks)}] [saved {status}] {result_path}", flush=True)
        if not result.get("verified"):
            failures += 1
        manifest["completed_count"] = index
        manifest["current_task"] = None
        manifest["current_compiler_pass"] = None
        manifest["updated_at"] = utc_now()
        write_json_atomic(manifest_path, manifest)

    print(f"Finished {len(tasks)} selected task(s); {failures} new failure(s).", flush=True)
    manifest["state"] = "completed"
    manifest["current_task"] = None
    manifest["finished_at"] = utc_now()
    manifest["updated_at"] = utc_now()
    manifest["failures"] = failures
    write_json_atomic(manifest_path, manifest)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
