#!/usr/bin/env python3
"""Run LastDance, the constrained Claude Code toolchain for AlgoVeri Lean."""

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
from dataclasses import asdict, dataclass
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
from src.agent.claude_tool_policy import policy_denial
from src.agent.lastdance_robust import (
    CheckpointManager,
    LastDanceFeatures,
    append_jsonl,
    diagnostic_fingerprint,
    provenance_record,
    sha256_text,
    structured_feedback,
    targeted_diagnostics,
    targeted_diagnostics_markdown,
)
from src.eval.prompt.lean_prompt import LEAN_INITIAL_PROMPT, LEAN_SYSTEM_PROMPT
from src.verifiers.lean_verifier import LeanVerifier


DEFAULT_DATA_ROOT = REPO_ROOT / "algoveri_data"
DEFAULT_LEANSEARCH_URL = "https://leansearch.net"


@dataclass(frozen=True)
class AgentRunControl:
    """Optional budget-loss controls used by the LastDance ablation study."""

    recover_pending_tool: bool = False
    progress_governor: bool = False
    pre_edit_timeout_seconds: int = 300
    pre_edit_thinking_tokens: int = 12000
    post_edit_check_timeout_seconds: int = 180
    planning_mode: bool = False
    diagnostic_wrapper: bool = False
    rescue_mode: bool = False


def text_sha256(path: Path) -> str | None:
    try:
        return sha256_text(path.read_text())
    except OSError:
        return None


def apply_pending_tool_call(workspace: Path, tool_call: dict[str, Any]) -> dict[str, Any]:
    """Commit one unexecuted safe Write/Edit emitted at a budget boundary."""
    name = str(tool_call.get("name") or "")
    tool_input = tool_call.get("input") or {}
    denial = policy_denial(
        {"cwd": str(workspace), "tool_name": name, "tool_input": tool_input}
    )
    record: dict[str, Any] = {
        "tool_use_id": tool_call.get("id"),
        "tool_name": name,
        "recovered": False,
        "denial": denial,
    }
    if denial or name not in {"Write", "Edit"}:
        return record
    path = Path(str(tool_input.get("file_path") or "")).expanduser().resolve()
    try:
        if name == "Write":
            replacement = str(tool_input.get("content") or "")
        else:
            source = path.read_text()
            old = str(tool_input.get("old_string") or "")
            new = str(tool_input.get("new_string") or "")
            occurrences = source.count(old) if old else 0
            if occurrences == 0:
                raise ValueError("Edit old_string was not present")
            if tool_input.get("replace_all"):
                replacement = source.replace(old, new)
            elif occurrences == 1:
                replacement = source.replace(old, new, 1)
            else:
                raise ValueError("Edit old_string was not unique")
        temporary = path.with_name(path.name + ".lastdance-pending")
        temporary.write_text(replacement)
        os.replace(temporary, path)
        record.update(
            {
                "recovered": True,
                "file": path.name,
                "characters": len(replacement),
                "sha256": sha256_text(replacement),
            }
        )
    except (OSError, ValueError) as exc:
        record["error"] = str(exc)
    return record


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


def latest_governor_stop_reason(
    value: dict[str, Any] | list[Any] | None,
) -> str | None:
    """Return the latest recorded governor stop, including aggregate sessions."""
    if value is None:
        return None
    attempts = value if isinstance(value, list) else [value]
    for item in reversed(attempts):
        if not isinstance(item, dict):
            continue
        agent = (item.get("details") or {}).get("agent") or {}
        sessions = agent.get("sessions") or [agent]
        for session in reversed(sessions):
            reason = ((session or {}).get("run_control") or {}).get(
                "governor_stop_reason"
            )
            if reason:
                return str(reason)
    return None


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lean_environment_record(config_path: Path) -> dict[str, Any]:
    """Capture pinned Lean/Mathlib evidence without invoking the compiler."""
    record: dict[str, Any] = {
        "config_path": str(config_path),
        "config_sha256": sha256_text(config_path.read_text()) if config_path.is_file() else None,
    }
    try:
        verifier = LeanVerifier(config_path=str(config_path))
        project = verifier._project_path()
        record["method"] = verifier.method
        record["project_path"] = str(project)
        for name in ("lean-toolchain", "lake-manifest.json", "lakefile.lean", "lakefile.toml"):
            path = project / name
            if path.is_file():
                content = path.read_text()
                record[name] = {
                    "sha256": sha256_text(content),
                    "content": content if name == "lean-toolchain" else None,
                }
        manifest = project / "lake-manifest.json"
        if manifest.is_file():
            value = json.loads(manifest.read_text())
            packages = value.get("packages") if isinstance(value, dict) else []
            mathlib = next(
                (item for item in packages or [] if item.get("name") == "mathlib"), None
            )
            if mathlib:
                record["mathlib"] = {
                    key: mathlib.get(key) for key in ("url", "rev", "inputRev")
                }
    except Exception as exc:
        record["snapshot_error"] = str(exc)
    return record


def leansearch_preflight(
    workspace: Path,
    root: Path | None,
    python: Path | None,
    url: str,
    num_results: int,
    timeout: int,
    rerank: bool = True,
    retrieve_k: int | None = None,
) -> tuple[bool, str]:
    adapter = REPO_ROOT / "scripts" / "lastdance_leansearch.py"
    command = [
        sys.executable,
        str(adapter),
        "--workspace",
        str(workspace),
        "--num",
        str(num_results),
        "--rerank" if rerank else "--no-rerank",
        "--timeout",
        str(timeout),
    ]
    if retrieve_k is not None:
        command.extend(("--retrieve-k", str(retrieve_k)))
    if url:
        command.extend(("--url", url))
    else:
        assert root is not None and python is not None
        command.extend(("--root", str(root), "--python", str(python)))
    command.append("commutativity of natural number addition")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if completed.returncode != 0:
        return False, (completed.stderr or completed.stdout).strip()[-4000:]
    return True, sha256_text(completed.stdout)


def write_workspace(
    workspace: Path,
    task_name: str,
    natural_language: str,
    formal_code: str,
    config_path: Path,
    preserve_solution: bool = False,
    preserve_logs: bool = False,
    features: LastDanceFeatures | None = None,
    leansearch_root: Path | None = None,
    leansearch_python: Path | None = None,
    leansearch_url: str = "",
    leansearch_results: int = 5,
    leansearch_timeout: int = 120,
    leansearch_rerank: bool = True,
    leansearch_retrieve_k: int | None = None,
    diagnostic_wrapper: bool = False,
    max_compiler_checks: int = 0,
) -> None:
    features = features or LastDanceFeatures.profile_defaults("legacy")
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
        robust_root = workspace / ".lastdance"
        if robust_root.exists():
            shutil.rmtree(robust_root)

    if features.algorithm_plan:
        plan_path = workspace / "AlgorithmPlan.md"
        if not preserve_solution or not plan_path.is_file():
            plan_path.write_text(
                "# Algorithm commitment\n\n"
                "- Named algorithm:\n"
                "- Required data structures:\n"
                "- State/loop invariants:\n"
                "- Required edge cases:\n"
                "- Expected complexity:\n"
                "- Forbidden substitutes checked:\n"
            )
    if features.lemma_plan:
        proof_path = workspace / "ProofState.md"
        if not preserve_solution or not proof_path.is_file():
            proof_path.write_text(
                "# Hierarchical proof state\n\n"
                "## Main theorem\n\n"
                "## Supporting lemmas\n\n"
                "## Current blocking goal\n\n"
                "## Failed approaches and why\n"
            )
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
    check_limit = ""
    check_count_path = workspace / ".compiler_check_count"
    if not preserve_logs:
        try:
            check_count_path.unlink()
        except FileNotFoundError:
            pass
    if max_compiler_checks:
        check_limit = f"""counter_file=.compiler_check_count
check_count=0
if [[ -f "$counter_file" ]]; then
    read -r check_count < "$counter_file"
fi
if [[ ! "$check_count" =~ ^[0-9]+$ ]]; then
    echo "Invalid compiler-check counter." >&2
    exit 2
fi
if (( check_count >= {max_compiler_checks} )); then
    echo "Compiler-check limit reached ({max_compiler_checks})." >&2
    exit 2
fi
check_count=$((check_count + 1))
printf '%s\\n' "$check_count" > "$counter_file"
echo "[compiler check $check_count/{max_compiler_checks}]"
"""
    check_path.write_text(
        f"#!/usr/bin/env bash\nset -uo pipefail\n{check_limit}{command}\n"
    )
    check_path.chmod(0o755)
    diagnose_path = workspace / "diagnose"
    if diagnostic_wrapper:
        diagnose_path.write_text(
            "#!/usr/bin/env bash\n"
            "set +e\n"
            "output=$(./check.sh 2>&1)\n"
            "status=$?\n"
            "printf '%s\\n' \"$output\" | tail -n 160\n"
            "exit \"$status\"\n"
        )
        diagnose_path.chmod(0o755)
    elif diagnose_path.exists():
        diagnose_path.unlink()

    leansearch_path = workspace / "leansearch"
    if features.leansearch:
        if not leansearch_url and (leansearch_root is None or leansearch_python is None):
            raise ValueError("LeanSearch is enabled but neither service nor local CLI was configured")
        adapter = REPO_ROOT / "scripts" / "lastdance_leansearch.py"
        backend_args: tuple[Any, ...] = (
            ("--url", leansearch_url)
            if leansearch_url
            else ("--root", leansearch_root, "--python", leansearch_python)
        )
        retrieval_args: tuple[Any, ...] = (
            ("--rerank",) if leansearch_rerank else ("--no-rerank",)
        )
        if leansearch_retrieve_k is not None:
            retrieval_args += ("--retrieve-k", leansearch_retrieve_k)
        search_command = " ".join(
            shlex.quote(str(part))
            for part in (
                python_bin,
                adapter,
                *backend_args,
                "--workspace",
                workspace,
                "--num",
                leansearch_results,
                *retrieval_args,
                "--timeout",
                leansearch_timeout,
            )
        ) + ' "$1"'
        leansearch_path.write_text(
            "#!/usr/bin/env bash\nset -uo pipefail\n"
            '[[ "$#" -eq 1 ]] || { echo "usage: ./leansearch \\\"query\\\"" >&2; exit 2; }\n'
            f"{search_command}\n"
        )
        leansearch_path.chmod(0o755)
    elif leansearch_path.exists():
        leansearch_path.unlink()

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


def feature_instructions(features: LastDanceFeatures) -> str:
    sections: list[str] = []
    if features.algorithm_plan:
        sections.append(
            "Before implementation, complete AlgorithmPlan.md. Commit to the named "
            "algorithm, its data structures, invariants, edge cases, and expected "
            "complexity. Revisit the commitment before final success."
        )
    if features.lemma_plan:
        sections.append(
            "Maintain ProofState.md as a hierarchical lemma manager: decompose the "
            "main theorem, record each supporting lemma and the current blocking "
            "goal, and record failed approaches so they are not repeated."
        )
    if features.leansearch:
        sections.append(
            "For Mathlib premise discovery, use the Frenzymath LeanSearch v2 API only through "
            "`./leansearch \"one natural-language theorem query\"`. Search for "
            "lemmas, not complete benchmark solutions; verify every retrieved "
            "declaration with ./check.sh because the hosted index may use a newer "
            "Mathlib revision. Do not guess declaration names repeatedly."
        )
    return "\n\n".join(sections)


def audit_instruction(features: LastDanceFeatures, reminder: bool = False) -> str:
    if not features.semantic_audit:
        return ""
    if reminder and not features.semantic_reminder:
        return ""
    return SEMANTIC_AUDIT


def agent_prompt(
    task_name: str,
    features: LastDanceFeatures | None = None,
    natural_language: str = "",
    formal_code: str = "",
    max_compiler_checks: int = 0,
) -> str:
    features = features or LastDanceFeatures.profile_defaults("legacy")
    if features.profile == "api":
        if not natural_language or not formal_code:
            raise ValueError("the API-equivalent prompt requires the task text and Lean scaffold")
        baseline = LEAN_SYSTEM_PROMPT + "\n\n" + LEAN_INITIAL_PROMPT.format(
            natural_language=natural_language,
            formal_code=formal_code,
        )
        limit = (
            f"The compiler wrapper permits at most {max_compiler_checks} checks."
            if max_compiler_checks
            else ""
        )
        return baseline + f"""

Claude Code transport note: the incomplete code above is also available as
Solution.lean in the current directory. Instead of returning the final Lean code
in a fenced response, edit Solution.lean in place, changing only the auxcode,
code, lemma, and proof marker regions. Use exactly ./check.sh to invoke the Lean
compiler and revise from its output. {limit} Do not create or modify any other
file. This transport note changes only how the answer and compiler feedback are
exchanged; all task and proof requirements are the baseline requirements above.
"""
    if features == LastDanceFeatures.profile_defaults("legacy"):
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
    planning = feature_instructions(features)
    early = (
        "run ./check.sh early, before extended proof polishing. Use its Lean errors"
        if features.early_check
        else "run ./check.sh to validate the completed candidate. Use its Lean errors"
    )
    editable_plans = " You may also edit AlgorithmPlan.md and ProofState.md when present."
    completion = (
        "verification succeeds and the semantic audit is complete"
        if features.semantic_audit
        else "verification succeeds"
    )
    return f"""Solve the AlgoVeri Lean 4 task {task_name} in this directory.

Start by reading TASK.md and Solution.lean. You may also inspect Original.lean,
Merged.lean, and check.sh. For Lean code, edit only Solution.lean and change
content only inside these four marker pairs: auxcode, code, lemma, and proof.
Preserve every marker. Do not edit Original.lean, TASK.md, check.sh, or
Merged.lean.{editable_plans}

{planning}

Implement the exact algorithm described in TASK.md and prove its stated
postcondition. Semantic correctness matters: do not substitute a different
algorithm, a specification oracle, brute-force enumeration, sorting when a
different algorithm is requested, Nat.find, Classical.choose, or decide over the
target property. Do not use sorry, admit, axioms, constants, partial, unsafe,
extern, or implemented_by in an editable section. Teacher-provided sorry outside
the four editable sections is permitted and must remain unchanged.

Your budget is limited. Produce a coherent candidate without leaving editable
`sorry` placeholders and {early} to revise Solution.lean, and repeat until it prints LEAN
VERIFIED. A prior successful check is invalid after another edit: re-run it.

{audit_instruction(features)}

Do not use network access, Git, package installation, or shell commands other
than ./check.sh, the guarded ./leansearch command when present, and safe workspace
inspection (`pwd`, `ls`, or `ls -la`). Stop
when {completion}, or when you
genuinely cannot make further progress.
"""


def repair_prompt(
    task_name: str,
    pass_number: int,
    feedback: str,
    features: LastDanceFeatures | None = None,
    alternate_strategy: bool = False,
    targeted_feedback: str = "",
    progress_rescue: bool = False,
) -> str:
    features = features or LastDanceFeatures.profile_defaults("legacy")
    if features == LastDanceFeatures.profile_defaults("legacy"):
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

Invoke the checker only as the exact standalone command ./check.sh. Never append
2>&1, a pipe, tail, a filter, a redirection, or another command.

{SEMANTIC_AUDIT}

Do not use network access, Git, package installation, or shell commands other
than ./check.sh and safe workspace inspection (`pwd`, `ls`, or `ls -la`).
"""
    shown_feedback = (
        structured_feedback(feedback)
        if features.feedback_mode == "structured"
        else feedback.strip() or "No verifier details were returned."
    )
    strategy = (
        "The same diagnostic fingerprint has repeated. The harness restored the "
        "best distinct checkpoint when available. Do not repeat the previous local "
        "edit; reconsider the decomposition or choose a different proof route."
        if alternate_strategy
        else ""
    )
    target_section = (
        "\n--- BEGIN SOURCE-MAPPED REPAIR TARGETS ---\n"
        + targeted_feedback.strip()
        + "\n--- END SOURCE-MAPPED REPAIR TARGETS ---\n"
        if targeted_feedback.strip()
        else ""
    )
    check_timing = "run ./check.sh early" if features.early_check else "run ./check.sh"
    rescue = (
        """
The preceding agent session was stopped because it spent its progress allowance
without making a durable edit. This is a focused rescue session, not a fresh
planning session. Reuse AlgorithmPlan.md and ProofState.md when present. Read the
current Solution.lean and diagnostics, then make a small, substantive Edit or
Write to Solution.lean as your first implementation action. Do not restart an
open-ended analysis. Compile that edit with exactly ./check.sh (or ./diagnose
when the bounded wrapper is present), then repair from the concrete Lean errors.
"""
        if progress_rescue
        else ""
    )
    return f"""Repair the existing AlgoVeri Lean 4 solution for {task_name}.
This is compiler-repair pass {pass_number}. The previous session's Solution.lean
has been preserved; improve it in place rather than restarting from the original
scaffold.

The harness independently merged the editable sections and rejected the final
candidate with this exact feedback:

--- BEGIN INDEPENDENT VERIFIER FEEDBACK ---
{shown_feedback}
--- END INDEPENDENT VERIFIER FEEDBACK ---
{target_section}
{strategy}
{rescue}

Read TASK.md and the current Solution.lean. Remove every editable prohibited
placeholder, address the reported Lean errors, and {check_timing}. Continue
until LEAN VERIFIED. Edit only the auxcode, code, lemma, and proof marker regions
of Solution.lean; planning files may also be maintained when present. Do not edit
any harness or teacher-owned file.

Invoke the checker only as the exact standalone command ./check.sh, or ./diagnose
when that bounded wrapper is present. Never append 2>&1, a pipe, tail, a filter,
a redirection, or another command.

{feature_instructions(features)}

{audit_instruction(features, reminder=True)}

Do not use network access, Git, package installation, or shell commands other
than ./check.sh, the guarded ./leansearch command when present, and safe workspace
inspection (`pwd`, `ls`, `ls -la`, or `cat` of an approved workspace file). Use
the Read tool for source files when possible. Do not inspect checker-wrapper
source merely to run it.
"""


def planning_prompt(task_name: str, hard_case_routing: bool = False) -> str:
    hard_requirements = """
Because this task was previously budget-limited, perform a proof-feasibility
gate. In AlgorithmPlan.md explicitly map every postcondition conjunct to an
invariant or lemma, and record the algorithm's representation and termination
measure. In ProofState.md list the smallest supporting lemmas, likely Mathlib
premises, and the first compiler-checkable implementation milestone.
""" if hard_case_routing else ""
    return f"""Prepare the implementation and proof plan for AlgoVeri task {task_name}.

Read TASK.md, Original.lean, Solution.lean, AlgorithmPlan.md, and ProofState.md.
Do not edit Solution.lean during this planning session. Immediately make the plan
durable by filling in the two plan files you have already read; do not spend the
session silently reasoning before the first write. Commit to the exact named
algorithm and reject semantic shortcuts or specification oracles.
{hard_requirements}
Keep the plan concise and actionable. Stop after both plan files contain enough
information for a fresh implementation session to begin coding without
re-planning. Use only approved file reads and writes; do not run shell commands.
"""


def implementation_phase_prompt(
    task_name: str,
    features: LastDanceFeatures,
    hard_case_routing: bool = False,
) -> str:
    routing = (
        "Follow the proof-feasibility mapping in the plan. Preserve the exact named "
        "algorithm even if a different implementation would be easier to prove."
        if hard_case_routing
        else "Follow the completed plan."
    )
    return agent_prompt(task_name, features) + f"""

AlgorithmPlan.md and ProofState.md were prepared in a separately budgeted phase.
Read them, then begin implementation without restarting open-ended planning.
{routing} Make a durable Solution.lean edit early and run exactly ./check.sh;
do not add pipes, redirections, or filters to the checker command.
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
                label = (
                    "tool policy correction"
                    if "PreToolUse:" in content
                    else "tool blocked/error"
                )
                messages.append(f"[{label}] {' '.join(content.split())[:500]}")
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
    allow_leansearch: bool = False,
    control: AgentRunControl | None = None,
) -> tuple[int, bool, dict[str, Any], str, dict[str, Any]]:
    control = control or AgentRunControl()
    allowed_tools = [
        "Read",
        "Edit",
        "Write",
        "Bash(./check.sh)",
        "Bash(pwd)",
        "Bash(ls)",
        "Bash(ls *)",
        "Bash(cat *)",
    ]
    if allow_leansearch:
        allowed_tools.insert(4, "Bash(./leansearch *)")
    if control.diagnostic_wrapper:
        allowed_tools.insert(4, "Bash(./diagnose)")
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
        *allowed_tools,
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
    started = time.monotonic()
    progress_at: float | None = None
    check_at: float | None = None
    governor_stop_reason: str | None = None
    max_thinking_tokens = 0
    pending_tools: dict[str, dict[str, Any]] = {}
    pending_order: list[str] = []
    completed_tools: set[str] = set()
    tracked_files = (
        ("AlgorithmPlan.md", "ProofState.md")
        if control.planning_mode
        else ("Solution.lean",)
    )
    initial_hashes = {name: text_sha256(workspace / name) for name in tracked_files}

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

        def stop_for_governor(reason: str) -> None:
            nonlocal governor_stop_reason
            if governor_stop_reason is not None or process.poll() is not None:
                return
            governor_stop_reason = reason
            print(f"[progress governor] {reason}", flush=True)
            os.killpg(process.pid, signal.SIGTERM)

        while selector.get_map():
            remaining = deadline - time.monotonic()
            now = time.monotonic()
            if control.progress_governor and governor_stop_reason is None:
                if (
                    progress_at is None
                    and now - started >= control.pre_edit_timeout_seconds
                ):
                    stop_for_governor(
                        f"no durable {'plan' if control.planning_mode else 'edit'} "
                        f"within {control.pre_edit_timeout_seconds}s"
                    )
                elif (
                    not control.planning_mode
                    and progress_at is not None
                    and check_at is None
                    and now - progress_at >= control.post_edit_check_timeout_seconds
                ):
                    stop_for_governor(
                        "no checker execution within "
                        f"{control.post_edit_check_timeout_seconds}s of the first edit"
                    )
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
                if event.get("type") == "assistant":
                    for block in (event.get("message") or {}).get("content") or []:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        tool_id = str(block.get("id") or "")
                        if tool_id:
                            pending_tools[tool_id] = block
                            pending_order.append(tool_id)
                elif event.get("type") == "user":
                    for block in (event.get("message") or {}).get("content") or []:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            continue
                        tool_id = str(block.get("tool_use_id") or "")
                        completed_tools.add(tool_id)
                        call = pending_tools.get(tool_id) or {}
                        command_text = str((call.get("input") or {}).get("command") or "")
                        if call.get("name") == "Bash" and command_text in {
                            "./check.sh",
                            "./diagnose",
                        }:
                            check_at = check_at or time.monotonic()
                        if call.get("name") in {"Write", "Edit"}:
                            for name in tracked_files:
                                current_hash = text_sha256(workspace / name)
                                if current_hash is not None and current_hash != initial_hashes[name]:
                                    progress_at = progress_at or time.monotonic()
                elif (
                    event.get("type") == "system"
                    and event.get("subtype") == "thinking_tokens"
                ):
                    max_thinking_tokens = max(
                        max_thinking_tokens, int(event.get("estimated_tokens") or 0)
                    )
                    if (
                        control.progress_governor
                        and progress_at is None
                        and max_thinking_tokens >= control.pre_edit_thinking_tokens
                    ):
                        stop_for_governor(
                            f"no durable {'plan' if control.planning_mode else 'edit'} "
                            f"before {control.pre_edit_thinking_tokens} thinking tokens"
                        )
                for progress in event_progress(event, progress_state):
                    print(progress, flush=True)

        returncode = process.wait()
        recovery_records: list[dict[str, Any]] = []
        if (
            control.recover_pending_tool
            and final_event.get("subtype") == "error_max_budget_usd"
        ):
            for tool_id in pending_order:
                if tool_id in completed_tools:
                    continue
                call = pending_tools[tool_id]
                if call.get("name") not in {"Write", "Edit"}:
                    continue
                recovered = apply_pending_tool_call(workspace, call)
                recovery_records.append(recovered)
                event_file.write(
                    json.dumps(
                        {
                            "type": "system",
                            "subtype": "harness_pending_tool_recovery",
                            "timestamp": utc_now(),
                            **recovered,
                        }
                    )
                    + "\n"
                )
                event_file.flush()
                if recovered.get("recovered"):
                    print(
                        f"[pending tool recovered] {recovered.get('file')} "
                        f"({recovered.get('characters')} characters)",
                        flush=True,
                    )
        if governor_stop_reason and not final_event:
            final_event = {
                "type": "result",
                "subtype": "error_progress_governor",
                "is_error": True,
                "result": f"Progress governor stopped the session: {governor_stop_reason}",
                "num_turns": 0,
                "usage": {},
            }
    run_metadata = {
        "control": asdict(control),
        "governor_stop_reason": governor_stop_reason,
        "max_thinking_tokens_observed": max_thinking_tokens,
        "seconds_to_first_progress": (
            round(progress_at - started, 3) if progress_at is not None else None
        ),
        "seconds_to_first_check": (
            round(check_at - started, 3) if check_at is not None else None
        ),
        "pending_tool_recovery": recovery_records,
    }
    return returncode, timed_out, final_event, "".join(stderr_chunks), run_metadata


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
    prompt: str = "",
    features: LastDanceFeatures | None = None,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    features = features or LastDanceFeatures.profile_defaults("legacy")
    candidate_path = workspace / "Solution.lean"
    validation_error = ""
    merged_code = ""
    provenance: dict[str, Any] = {}
    try:
        candidate = candidate_path.read_text()
        merged = merge_candidate_sections(original, candidate)
        merged_code = merged.code
        provenance = provenance_record(original, candidate, merged)
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
    repair_targets = targeted_diagnostics(parsed_verifier.get("feedback", ""), merged_code)
    final_text = final_event.get("result") or ""
    if validation_error and not final_text:
        final_text = f"Candidate validation failed: {validation_error}"
    if stderr and not final_text:
        final_text = stderr[-4000:]
    turns = int(final_event.get("num_turns") or 0)
    provider_subtype = final_event.get("subtype")
    governor_reason = (run_metadata or {}).get("governor_stop_reason")
    agent_metadata = {
        "kind": "claude-code",
        "cli_version": cli_version,
        "model": model,
        "effort": effort,
        "session_id": final_event.get("session_id"),
        "subtype": "error_progress_governor" if governor_reason else provider_subtype,
        "provider_subtype": provider_subtype,
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
        "prompt_sha256": sha256_text(prompt) if prompt else None,
        "budget_usd": budget_usd,
        "lastdance_profile": features.profile,
        "features": features.as_dict(),
        "run_control": run_metadata or {},
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
            "provenance": provenance,
            "targeted_diagnostics": repair_targets,
        },
    }


def combine_pass_results(
    pass_results: list[dict[str, Any]], selected_index: int | None = None
) -> dict[str, Any]:
    """Return the final candidate result with aggregate multi-session metadata."""
    if not pass_results:
        raise ValueError("at least one pass result is required")
    selected = selected_index if selected_index is not None else len(pass_results) - 1
    final = json.loads(json.dumps(pass_results[selected]))
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
            "compiler_passes": len(sessions),
            "total_sessions": len(pass_results),
            "selected_session": selected + 1,
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


def include_planning_session(
    result: dict[str, Any], planning: dict[str, Any] | None
) -> None:
    """Include a separately budgeted planning phase in aggregate accounting."""
    if not planning:
        return
    details = result["details"]
    agent = details.get("agent") or {}
    sessions = list(agent.get("sessions") or [])
    sessions.insert(0, planning)
    agent["sessions"] = sessions
    agent["total_sessions"] = len(sessions)
    cost = planning.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        agent["total_cost_usd"] = float(agent.get("total_cost_usd") or 0) + float(cost)
    duration = planning.get("duration_ms")
    if isinstance(duration, (int, float)):
        agent["duration_ms"] = int(agent.get("duration_ms") or 0) + int(duration)
    api_duration = planning.get("duration_api_ms")
    if isinstance(api_duration, (int, float)):
        agent["duration_api_ms"] = int(agent.get("duration_api_ms") or 0) + int(api_duration)
    agent["planning_session"] = planning
    details["agent"] = agent
    planning_tokens = planning.get("tokens") or {}
    for key in ("input", "output", "reasoning"):
        details["tokens"][key] = int(details["tokens"].get(key) or 0) + int(
            planning_tokens.get(key) or 0
        )


def claude_version(claude_bin: str) -> str:
    try:
        process = subprocess.run(
            [claude_bin, "--version"], capture_output=True, text=True, timeout=15
        )
        return (process.stdout or process.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def resolve_features(args: argparse.Namespace) -> LastDanceFeatures:
    defaults = LastDanceFeatures.profile_defaults(args.profile)

    def selected(name: str) -> Any:
        value = getattr(args, name)
        return getattr(defaults, name) if value is None else value

    return LastDanceFeatures(
        profile=args.profile,
        algorithm_plan=selected("algorithm_plan"),
        lemma_plan=selected("lemma_plan"),
        leansearch=selected("leansearch"),
        semantic_audit=selected("semantic_audit"),
        semantic_reminder=selected("semantic_reminder"),
        early_check=selected("early_check"),
        feedback_mode=selected("feedback_mode"),
        backtracking=selected("backtracking"),
        stagnation_threshold=selected("stagnation_threshold"),
    )


def append_harness_event(workspace: Path, subtype: str, **values: Any) -> None:
    append_jsonl(
        workspace / "agent_events.jsonl",
        {"type": "system", "subtype": subtype, "timestamp": utc_now(), **values},
    )


def runner_error_result(
    exc: Exception,
    version: str,
    model: str,
    effort: str,
    pass_number: int,
    prompt_kind: str,
    budget: float | None,
    prompt: str,
    features: LastDanceFeatures,
) -> dict[str, Any]:
    return {
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
            "provenance": {},
            "targeted_diagnostics": [],
            "agent": {
                "kind": "claude-code",
                "cli_version": version,
                "model": model,
                "effort": effort,
                "runner_error": str(exc),
                "pass_number": pass_number,
                "prompt_kind": prompt_kind,
                "prompt_sha256": sha256_text(prompt),
                "budget_usd": budget,
                "lastdance_profile": features.profile,
                "features": features.as_dict(),
            },
        },
    }


def result_feedback(result: dict[str, Any]) -> str:
    return str(
        ((result.get("details") or {}).get("verifier_response") or {}).get(
            "feedback", "Independent verification failed"
        )
    )


def result_targets(result: dict[str, Any]) -> list[dict[str, Any]]:
    value = (result.get("details") or {}).get("targeted_diagnostics") or []
    return value if isinstance(value, list) else []


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
    parser.add_argument(
        "--profile",
        choices=("api", "legacy", "robust"),
        default="legacy",
        help=(
            "api uses the direct API baseline prompt with only compiler access; "
            "legacy reproduces the original LastDance runner; robust enables all v2 measures"
        ),
    )
    for option, help_text in (
        ("algorithm-plan", "Require an explicit algorithm commitment artifact"),
        ("lemma-plan", "Maintain a hierarchical proof-state artifact"),
        ("leansearch", "Enable guarded Frenzymath LeanSearch premise retrieval"),
        ("semantic-audit", "Require a final requirement-by-requirement self-audit"),
        ("semantic-reminder", "Repeat semantic audit instructions during repairs"),
        ("early-check", "Instruct the agent to compile before extended polishing"),
        ("backtracking", "Checkpoint candidates and roll back on diagnostic stagnation"),
    ):
        parser.add_argument(
            f"--{option}",
            action=argparse.BooleanOptionalAction,
            default=None,
            help=help_text,
        )
    parser.add_argument(
        "--feedback-mode",
        choices=("exact", "structured"),
        default=None,
        help="Repair-prompt diagnostic representation (profile default when omitted)",
    )
    parser.add_argument(
        "--stagnation-threshold",
        type=int,
        default=None,
        help="Repeated diagnostic fingerprints before alternate-strategy rollback",
    )
    parser.add_argument("--max-checkpoints", type=int, default=20)
    parser.add_argument(
        "--leansearch-root",
        default=os.environ.get("LEANSEARCH_ROOT", ""),
        help="Local Frenzymath LeanSearch checkout containing search.py",
    )
    parser.add_argument(
        "--leansearch-python",
        default=os.environ.get("LEANSEARCH_PYTHON", ""),
        help="Python environment with LeanSearch dependencies (defaults to checkout .venv)",
    )
    parser.add_argument(
        "--leansearch-url",
        default=os.environ.get("LEANSEARCH_URL", ""),
        help=f"Frenzymath LeanSearch API base URL (robust default: {DEFAULT_LEANSEARCH_URL})",
    )
    parser.add_argument("--leansearch-results", type=int, default=5)
    parser.add_argument("--leansearch-timeout", type=int, default=120)
    parser.add_argument(
        "--leansearch-rerank",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use the hosted LeanSearch v2 reranker",
    )
    parser.add_argument(
        "--leansearch-retrieve-k",
        type=int,
        help="Optional first-stage retrieval width for the LeanSearch v2 API",
    )
    parser.add_argument(
        "--leansearch-preflight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run one cached search before spending model budget",
    )
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument(
        "--max-compiler-checks",
        type=int,
        default=0,
        help="Maximum ./check.sh calls in one Claude session; zero is unlimited",
    )
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
        "--recover-pending-tool",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Commit safe unexecuted Write/Edit calls emitted at a budget boundary",
    )
    parser.add_argument(
        "--progress-governor",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Stop and repair sessions that miss durable progress milestones",
    )
    parser.add_argument("--pre-edit-timeout-seconds", type=int, default=300)
    parser.add_argument("--pre-edit-thinking-tokens", type=int, default=12000)
    parser.add_argument("--post-edit-check-timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--rescue-pre-edit-timeout-seconds",
        type=int,
        default=600,
        help="Relaxed first-edit wall-time allowance after a governor stop",
    )
    parser.add_argument(
        "--rescue-pre-edit-thinking-tokens",
        type=int,
        default=30000,
        help="Relaxed first-edit thinking allowance for focused rescue sessions",
    )
    parser.add_argument(
        "--rescue-post-edit-check-timeout-seconds",
        type=int,
        default=300,
        help="Relaxed edit-to-check allowance for focused rescue sessions",
    )
    parser.add_argument(
        "--phase-separated",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run a separately budgeted planning session before implementation",
    )
    parser.add_argument("--planning-budget-usd", type=float, default=0.4)
    parser.add_argument(
        "--planning-effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="low",
    )
    parser.add_argument(
        "--hard-case-routing",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use a postcondition-to-invariant proof-feasibility planning gate",
    )
    parser.add_argument(
        "--diagnostic-wrapper",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Provide the bounded exact ./diagnose checker wrapper",
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
    if args.max_compiler_checks < 0:
        parser.error("--max-compiler-checks cannot be negative")
    if args.max_budget_usd is not None and args.max_budget_usd <= 0:
        parser.error("--max-budget-usd must be positive")
    if args.repair_budget_usd is not None and args.repair_budget_usd <= 0:
        parser.error("--repair-budget-usd must be positive")
    if args.compiler_repair_passes < 0:
        parser.error("--compiler-repair-passes cannot be negative")
    if args.planning_budget_usd <= 0:
        parser.error("--planning-budget-usd must be positive")
    if args.pre_edit_timeout_seconds <= 0:
        parser.error("--pre-edit-timeout-seconds must be positive")
    if args.pre_edit_thinking_tokens <= 0:
        parser.error("--pre-edit-thinking-tokens must be positive")
    if args.post_edit_check_timeout_seconds <= 0:
        parser.error("--post-edit-check-timeout-seconds must be positive")
    if args.rescue_pre_edit_timeout_seconds <= 0:
        parser.error("--rescue-pre-edit-timeout-seconds must be positive")
    if args.rescue_pre_edit_thinking_tokens <= 0:
        parser.error("--rescue-pre-edit-thinking-tokens must be positive")
    if args.rescue_post_edit_check_timeout_seconds <= 0:
        parser.error("--rescue-post-edit-check-timeout-seconds must be positive")
    if args.stagnation_threshold is not None and args.stagnation_threshold < 2:
        parser.error("--stagnation-threshold must be at least 2")
    if args.max_checkpoints <= 0:
        parser.error("--max-checkpoints must be positive")
    if args.leansearch_results <= 0 or args.leansearch_results > 25:
        parser.error("--leansearch-results must be between 1 and 25")
    if args.leansearch_timeout <= 0:
        parser.error("--leansearch-timeout must be positive")
    if (
        args.leansearch_retrieve_k is not None
        and args.leansearch_retrieve_k < args.leansearch_results
    ):
        parser.error("--leansearch-retrieve-k cannot be smaller than --leansearch-results")
    return args


def main() -> int:
    args = parse_args()
    features = resolve_features(args)
    if args.phase_separated and not (features.algorithm_plan and features.lemma_plan):
        print(
            "--phase-separated requires algorithm-plan and lemma-plan artifacts.",
            file=sys.stderr,
        )
        return 2
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
        print("LastDance features: " + json.dumps(features.as_dict(), sort_keys=True))
        print(
            "Budget controls: "
            + json.dumps(
                {
                    "recover_pending_tool": args.recover_pending_tool,
                    "progress_governor": args.progress_governor,
                    "pre_edit_timeout_seconds": args.pre_edit_timeout_seconds,
                    "pre_edit_thinking_tokens": args.pre_edit_thinking_tokens,
                    "post_edit_check_timeout_seconds": args.post_edit_check_timeout_seconds,
                    "rescue_pre_edit_timeout_seconds": args.rescue_pre_edit_timeout_seconds,
                    "rescue_pre_edit_thinking_tokens": args.rescue_pre_edit_thinking_tokens,
                    "rescue_post_edit_check_timeout_seconds": (
                        args.rescue_post_edit_check_timeout_seconds
                    ),
                    "phase_separated": args.phase_separated,
                    "planning_budget_usd": args.planning_budget_usd,
                    "planning_effort": args.planning_effort,
                    "hard_case_routing": args.hard_case_routing,
                    "diagnostic_wrapper": args.diagnostic_wrapper,
                },
                sort_keys=True,
            )
        )
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
    environment_record = lean_environment_record(config_path)
    leansearch_root: Path | None = None
    leansearch_python: Path | None = None
    leansearch_url = args.leansearch_url
    if features.leansearch:
        if not leansearch_url and not args.leansearch_root:
            leansearch_url = DEFAULT_LEANSEARCH_URL
        if leansearch_url and args.leansearch_root:
            print("Set only one of LEANSEARCH_URL and LEANSEARCH_ROOT.", file=sys.stderr)
            return 2
        if leansearch_url and not leansearch_url.startswith(("http://", "https://")):
            print("LEANSEARCH_URL must use http:// or https://.", file=sys.stderr)
            return 2
        if args.leansearch_root:
            leansearch_root = Path(args.leansearch_root).expanduser().resolve()
            if not (leansearch_root / "search.py").is_file():
                print(f"LeanSearch search.py not found: {leansearch_root}", file=sys.stderr)
                return 2
            if args.leansearch_python:
                leansearch_python = Path(args.leansearch_python).expanduser().resolve()
            else:
                leansearch_python = leansearch_root / ".venv" / "bin" / "python"
            if not leansearch_python.is_file():
                print(
                    f"LeanSearch Python not found: {leansearch_python}. Set LEANSEARCH_PYTHON.",
                    file=sys.stderr,
                )
                return 2
    results_dir = Path(args.results_root).expanduser()
    if not results_dir.is_absolute():
        results_dir = REPO_ROOT / results_dir
    results_dir = results_dir / "lean"
    work_root = Path(args.work_root).expanduser()
    if not work_root.is_absolute():
        work_root = REPO_ROOT / work_root
    work_root.mkdir(parents=True, exist_ok=True)
    leansearch_preflight_record: dict[str, Any] | None = None
    if features.leansearch and args.leansearch_preflight:
        preflight_workspace = work_root / ".leansearch_preflight"
        ok, detail = leansearch_preflight(
            preflight_workspace,
            leansearch_root,
            leansearch_python,
            leansearch_url,
            args.leansearch_results,
            args.leansearch_timeout,
            args.leansearch_rerank,
            args.leansearch_retrieve_k,
        )
        leansearch_preflight_record = {
            "ok": ok,
            "timestamp": utc_now(),
            "result_sha256": detail if ok else None,
            "error": None if ok else detail,
        }
        if not ok:
            print(f"LeanSearch preflight failed: {detail}", file=sys.stderr)
            return 2
        print("LeanSearch preflight passed.", flush=True)
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
        "max_compiler_checks": args.max_compiler_checks,
        "max_budget_usd": args.max_budget_usd,
        "repair_budget_usd": repair_budget,
        "compiler_repair_passes": args.compiler_repair_passes,
        "budget_controls": {
            "recover_pending_tool": args.recover_pending_tool,
            "progress_governor": args.progress_governor,
            "pre_edit_timeout_seconds": args.pre_edit_timeout_seconds,
            "pre_edit_thinking_tokens": args.pre_edit_thinking_tokens,
            "post_edit_check_timeout_seconds": args.post_edit_check_timeout_seconds,
            "rescue_pre_edit_timeout_seconds": args.rescue_pre_edit_timeout_seconds,
            "rescue_pre_edit_thinking_tokens": args.rescue_pre_edit_thinking_tokens,
            "rescue_post_edit_check_timeout_seconds": (
                args.rescue_post_edit_check_timeout_seconds
            ),
            "phase_separated": args.phase_separated,
            "planning_budget_usd": args.planning_budget_usd,
            "planning_effort": args.planning_effort,
            "hard_case_routing": args.hard_case_routing,
            "diagnostic_wrapper": args.diagnostic_wrapper,
        },
        "lastdance_profile": features.profile,
        "features": features.as_dict(),
        "leansearch_root": str(leansearch_root) if leansearch_root else None,
        "leansearch_python": str(leansearch_python) if leansearch_python else None,
        "leansearch_url": leansearch_url or None,
        "leansearch_results": args.leansearch_results if features.leansearch else None,
        "leansearch_timeout": args.leansearch_timeout if features.leansearch else None,
        "leansearch_rerank": args.leansearch_rerank if features.leansearch else None,
        "leansearch_retrieve_k": (
            args.leansearch_retrieve_k if features.leansearch else None
        ),
        "leansearch_preflight": leansearch_preflight_record,
        "exclude_teacher_sorry": args.exclude_teacher_sorry,
        "excluded_teacher_sorry": excluded_teacher_sorry,
        "reuse_workspace": args.reuse_workspace,
        "results_root": str(results_dir.parent),
        "work_root": str(work_root),
        "lean_environment": environment_record,
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
            features=features,
            leansearch_root=leansearch_root,
            leansearch_python=leansearch_python,
            leansearch_url=leansearch_url,
            leansearch_results=args.leansearch_results,
            leansearch_timeout=args.leansearch_timeout,
            leansearch_rerank=args.leansearch_rerank,
            leansearch_retrieve_k=args.leansearch_retrieve_k,
            diagnostic_wrapper=args.diagnostic_wrapper,
            max_compiler_checks=args.max_compiler_checks,
        )
        if reused_workspace:
            print(f"[{task_name}] [reusing existing workspace]", flush=True)
        ledger_path = workspace / ".lastdance" / "run_ledger.jsonl"
        config_digest = sha256_text(json.dumps(manifest, sort_keys=True, default=str))
        append_jsonl(
            ledger_path,
            {
                "event": "task_started",
                "timestamp": utc_now(),
                "task": task_name,
                "profile": features.profile,
                "features": features.as_dict(),
                "config_sha256": config_digest,
                "original_sha256": sha256_text(original),
                "natural_language_sha256": sha256_text(natural),
                "reused_workspace": reused_workspace,
                "lean_environment": environment_record,
            },
        )
        prompt_root = workspace / ".lastdance" / "prompts"
        prompt_root.mkdir(parents=True, exist_ok=True)
        planning_session: dict[str, Any] | None = None
        reusable_plans = reused_workspace and all(
            (workspace / name).is_file() and (workspace / name).stat().st_size > 250
            for name in ("AlgorithmPlan.md", "ProofState.md")
        )
        if args.phase_separated and not reusable_plans:
            prompt = planning_prompt(task_name, args.hard_case_routing)
            prompt_path = prompt_root / f"000-planning-{sha256_text(prompt)[:10]}.txt"
            prompt_path.write_text(prompt)
            append_jsonl(
                ledger_path,
                {
                    "event": "session_started",
                    "timestamp": utc_now(),
                    "pass_number": 0,
                    "prompt_kind": "proof_feasibility_planning",
                    "prompt_sha256": sha256_text(prompt),
                    "prompt_path": str(prompt_path),
                    "budget_usd": args.planning_budget_usd,
                },
            )
            print(
                f"[{task_name}] [planning phase] budget ${args.planning_budget_usd:g}",
                flush=True,
            )
            planning_control = AgentRunControl(
                recover_pending_tool=args.recover_pending_tool,
                progress_governor=args.progress_governor,
                pre_edit_timeout_seconds=args.pre_edit_timeout_seconds,
                pre_edit_thinking_tokens=args.pre_edit_thinking_tokens,
                post_edit_check_timeout_seconds=args.post_edit_check_timeout_seconds,
                planning_mode=True,
                diagnostic_wrapper=args.diagnostic_wrapper,
            )
            try:
                (
                    planning_returncode,
                    planning_timed_out,
                    planning_event,
                    planning_stderr,
                    planning_run_metadata,
                ) = run_claude(
                    claude_bin=claude_bin,
                    workspace=workspace,
                    model=args.model,
                    effort=args.planning_effort,
                    timeout_seconds=args.timeout_seconds,
                    max_budget_usd=args.planning_budget_usd,
                    prompt=prompt,
                    pass_number=0,
                    allow_leansearch=features.leansearch,
                    control=planning_control,
                )
                planning_session = {
                    "kind": "claude-code",
                    "cli_version": version,
                    "model": args.model,
                    "effort": args.planning_effort,
                    "session_id": planning_event.get("session_id"),
                    "subtype": planning_event.get("subtype"),
                    "is_error": planning_event.get("is_error"),
                    "total_cost_usd": planning_event.get("total_cost_usd"),
                    "duration_ms": planning_event.get("duration_ms"),
                    "duration_api_ms": planning_event.get("duration_api_ms"),
                    "num_turns": int(planning_event.get("num_turns") or 0),
                    "returncode": planning_returncode,
                    "timed_out": planning_timed_out,
                    "stderr": planning_stderr[-1000:],
                    "pass_number": 0,
                    "prompt_kind": "proof_feasibility_planning",
                    "prompt_sha256": sha256_text(prompt),
                    "budget_usd": args.planning_budget_usd,
                    "tokens": token_summary(planning_event),
                    "run_control": planning_run_metadata,
                }
            except Exception as exc:
                planning_session = {
                    "kind": "claude-code",
                    "model": args.model,
                    "effort": args.planning_effort,
                    "prompt_kind": "proof_feasibility_planning",
                    "runner_error": str(exc),
                    "budget_usd": args.planning_budget_usd,
                    "tokens": {"input": 0, "output": 0, "reasoning": 0},
                }
            append_jsonl(
                ledger_path,
                {
                    "event": "session_finished",
                    "timestamp": utc_now(),
                    "pass_number": 0,
                    "prompt_kind": "proof_feasibility_planning",
                    "agent": planning_session,
                    "algorithm_plan_sha256": text_sha256(workspace / "AlgorithmPlan.md"),
                    "proof_state_sha256": text_sha256(workspace / "ProofState.md"),
                },
            )
        elif args.phase_separated:
            print(f"[{task_name}] [reusing existing planning artifacts]", flush=True)
            append_jsonl(
                ledger_path,
                {
                    "event": "planning_reused",
                    "timestamp": utc_now(),
                    "algorithm_plan_sha256": text_sha256(workspace / "AlgorithmPlan.md"),
                    "proof_state_sha256": text_sha256(workspace / "ProofState.md"),
                },
            )
        checkpoints = (
            CheckpointManager(workspace, args.max_checkpoints)
            if features.backtracking
            else None
        )
        pass_results: list[dict[str, Any]] = []
        selected_index: int | None = None
        feedback = latest_verifier_feedback(current) if reused_workspace else ""
        targeted_feedback = ""
        fingerprint_counts: dict[str, int] = {}
        alternate_strategy = False
        rescue_mode = bool(reused_workspace and latest_governor_stop_reason(current))
        total_passes = 1 + args.compiler_repair_passes
        for pass_number in range(1, total_passes + 1):
            is_repair = pass_number > 1 or reused_workspace
            budget = repair_budget if is_repair else args.max_budget_usd
            prompt = (
                repair_prompt(
                    task_name,
                    pass_number,
                    feedback,
                    features,
                    alternate_strategy=alternate_strategy,
                    targeted_feedback=targeted_feedback,
                    progress_rescue=rescue_mode,
                )
                if is_repair
                else (
                    implementation_phase_prompt(
                        task_name, features, args.hard_case_routing
                    )
                    if args.phase_separated
                    else agent_prompt(
                        task_name,
                        features,
                        natural_language=natural,
                        formal_code=original,
                        max_compiler_checks=args.max_compiler_checks,
                    )
                )
            )
            if args.diagnostic_wrapper:
                prompt += (
                    "\nFor bounded compiler output, run exactly ./diagnose. "
                    "Do not add shell pipes, filters, or redirections.\n"
                )
            alternate_strategy = False
            prompt_path = prompt_root / (
                f"{pass_number:03d}-{'repair' if is_repair else 'initial'}-"
                f"{sha256_text(prompt)[:10]}.txt"
            )
            prompt_path.write_text(prompt)
            if checkpoints:
                checkpoints.save(
                    workspace / "Solution.lean", pass_number, "before", verified=None
                )
            append_jsonl(
                ledger_path,
                {
                    "event": "session_started",
                    "timestamp": utc_now(),
                    "pass_number": pass_number,
                    "prompt_kind": "compiler_repair" if is_repair else "initial",
                    "prompt_sha256": sha256_text(prompt),
                    "prompt_path": str(prompt_path),
                    "candidate_sha256": sha256_text((workspace / "Solution.lean").read_text()),
                    "budget_usd": budget,
                },
            )
            manifest["current_compiler_pass"] = pass_number
            manifest["updated_at"] = utc_now()
            write_json_atomic(manifest_path, manifest)
            print(
                f"[{task_name}] [compiler pass {pass_number}/{total_passes}] "
                + (f"budget ${budget:g}" if budget is not None else "uncapped budget")
                + (" [focused rescue]" if rescue_mode else ""),
                flush=True,
            )
            try:
                returncode, timed_out, final_event, stderr, run_metadata = run_claude(
                    claude_bin=claude_bin,
                    workspace=workspace,
                    model=args.model,
                    effort=args.effort,
                    timeout_seconds=args.timeout_seconds,
                    max_budget_usd=budget,
                    prompt=prompt,
                    pass_number=pass_number,
                    allow_leansearch=features.leansearch,
                    control=AgentRunControl(
                        recover_pending_tool=args.recover_pending_tool,
                        progress_governor=args.progress_governor,
                        pre_edit_timeout_seconds=(
                            args.rescue_pre_edit_timeout_seconds
                            if rescue_mode
                            else args.pre_edit_timeout_seconds
                        ),
                        pre_edit_thinking_tokens=(
                            args.rescue_pre_edit_thinking_tokens
                            if rescue_mode
                            else args.pre_edit_thinking_tokens
                        ),
                        post_edit_check_timeout_seconds=(
                            args.rescue_post_edit_check_timeout_seconds
                            if rescue_mode
                            else args.post_edit_check_timeout_seconds
                        ),
                        diagnostic_wrapper=args.diagnostic_wrapper,
                        rescue_mode=rescue_mode,
                    ),
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
                    prompt=prompt,
                    features=features,
                    run_metadata=run_metadata,
                )
            except Exception as exc:
                print(
                    f"[{task_name}] pass {pass_number} runner error: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                pass_result = runner_error_result(
                    exc,
                    version,
                    args.model,
                    args.effort,
                    pass_number,
                    "compiler_repair" if is_repair else "initial",
                    budget,
                    prompt,
                    features,
                )
            pass_results.append(pass_result)
            rescue_mode = rescue_mode or bool(
                (((pass_result.get("details") or {}).get("agent") or {}).get(
                    "run_control"
                ) or {}).get("governor_stop_reason")
            )
            feedback = result_feedback(pass_result)
            targeted_feedback = targeted_diagnostics_markdown(result_targets(pass_result))
            if features.feedback_mode == "structured":
                (workspace / "Diagnostics.md").write_text(
                    "# Source-mapped repair targets\n\n" + targeted_feedback + "\n"
                )
            fingerprint = diagnostic_fingerprint(feedback) if not pass_result.get("verified") else None
            checkpoint = None
            if checkpoints:
                checkpoint = checkpoints.save(
                    workspace / "Solution.lean",
                    pass_number,
                    "after",
                    verified=pass_result.get("verified") is True,
                    feedback=feedback,
                )
            append_jsonl(
                ledger_path,
                {
                    "event": "session_finished",
                    "timestamp": utc_now(),
                    "pass_number": pass_number,
                    "verified": pass_result.get("verified") is True,
                    "diagnostic_fingerprint": fingerprint,
                    "candidate_sha256": (
                        checkpoint.candidate_sha256
                        if checkpoint
                        else sha256_text((workspace / "Solution.lean").read_text())
                    ),
                    "agent": (pass_result.get("details") or {}).get("agent"),
                },
            )
            if pass_result.get("verified") is True:
                selected_index = len(pass_results) - 1
                print(f"[{task_name}] [independent verification passed]", flush=True)
                break
            print(
                f"[{task_name}] [independent verification failed] "
                f"{str(feedback).splitlines()[0][:300]}",
                flush=True,
            )
            if features.backtracking and checkpoints and fingerprint:
                fingerprint_counts[fingerprint] = fingerprint_counts.get(fingerprint, 0) + 1
                if fingerprint_counts[fingerprint] >= features.stagnation_threshold:
                    current_sha = sha256_text((workspace / "Solution.lean").read_text())
                    restored = checkpoints.restore_best(
                        workspace / "Solution.lean", exclude_sha256=current_sha
                    )
                    alternate_strategy = True
                    message = (
                        f"restored pass {restored.pass_number} checkpoint"
                        if restored
                        else "no distinct checkpoint available; forcing alternate strategy"
                    )
                    print(
                        f"[{task_name}] [stagnation {fingerprint}] {message}", flush=True
                    )
                    append_harness_event(
                        workspace,
                        "harness_backtrack",
                        pass_number=pass_number,
                        fingerprint=fingerprint,
                        action=message,
                    )
                    append_jsonl(
                        ledger_path,
                        {
                            "event": "backtrack",
                            "timestamp": utc_now(),
                            "pass_number": pass_number,
                            "diagnostic_fingerprint": fingerprint,
                            "action": message,
                        },
                    )

        if selected_index is None:
            selected_index = len(pass_results) - 1

        result = combine_pass_results(pass_results, selected_index=selected_index)
        include_planning_session(result, planning_session)
        check_count_path = workspace / ".compiler_check_count"
        try:
            compiler_checks_observed = int(check_count_path.read_text().strip())
        except (OSError, ValueError):
            compiler_checks_observed = 0
        result["details"]["agent"]["compiler_checks_observed"] = compiler_checks_observed
        result["details"]["agent"]["max_compiler_checks"] = args.max_compiler_checks
        result["details"]["lastdance_artifacts"] = {
            "ledger": str(ledger_path),
            "algorithm_plan": str(workspace / "AlgorithmPlan.md") if features.algorithm_plan else None,
            "proof_state": str(workspace / "ProofState.md") if features.lemma_plan else None,
            "leansearch_queries": (
                str(workspace / ".lastdance" / "leansearch_queries.jsonl")
                if features.leansearch
                else None
            ),
            "checkpoints": (
                str(workspace / ".lastdance" / "checkpoints" / "manifest.jsonl")
                if checkpoints
                else None
            ),
            "prompts": str(prompt_root),
        }
        append_jsonl(
            ledger_path,
            {
                "event": "task_finished",
                "timestamp": utc_now(),
                "task": task_name,
                "verified": result.get("verified") is True,
                "selected_session": selected_index + 1,
                "result_sha256": sha256_text(json.dumps(result, sort_keys=True, default=str)),
            },
        )
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
