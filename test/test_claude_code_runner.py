from __future__ import annotations

import tempfile
import unittest
import json
import subprocess
import sys
from pathlib import Path

from scripts.run_claude_code_lean import (
    apply_pending_tool_call,
    agent_prompt,
    combine_pass_results,
    leansearch_preflight,
    planning_prompt,
    repair_prompt,
    task_directories,
    write_workspace,
)
from src.agent.lastdance_robust import LastDanceFeatures
from src.eval.prompt.lean_prompt import LEAN_SYSTEM_PROMPT


class ClaudeCodeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for name in ("one", "two"):
            task = self.root / name
            task.mkdir()
            (task / "lean_spec.lean").write_text("-- spec")
            (task / "lean_nl.txt").write_text("task")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_selects_ordered_comma_separated_tasks(self) -> None:
        selected = task_directories(self.root, None, "two,one,two")
        self.assertEqual([path.name for path in selected], ["two", "one"])

    def test_rejects_single_and_multiple_selection_together(self) -> None:
        with self.assertRaisesRegex(ValueError, "either --task or --tasks"):
            task_directories(self.root, "one", "two")

    def test_rejects_unknown_task_in_list(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "missing"):
            task_directories(self.root, None, "one,missing")

    def test_prompts_require_early_compilation_and_semantic_audit(self) -> None:
        initial = agent_prompt("one")
        self.assertIn("run ./check.sh early", initial)
        self.assertIn("semantic audit", initial)
        self.assertIn("placeholder", initial)
        repair = repair_prompt("one", 2, "error: unsolved goals")
        self.assertIn("Solution.lean\nhas been preserved", repair)
        self.assertIn("error: unsolved goals", repair)
        self.assertIn("compiler-repair pass 2", repair)
        self.assertIn("Never append\n2>&1, a pipe", repair)

    def test_robust_prompt_exposes_planning_and_guarded_leansearch(self) -> None:
        features = LastDanceFeatures.profile_defaults("robust")
        initial = agent_prompt("one", features)
        self.assertIn("AlgorithmPlan.md", initial)
        self.assertIn("ProofState.md", initial)
        self.assertIn("Frenzymath LeanSearch", initial)
        self.assertIn('./leansearch "one natural-language theorem query"', initial)

    def test_api_profile_reuses_baseline_prompt_without_lastdance_modules(self) -> None:
        prompt = agent_prompt(
            "one",
            LastDanceFeatures.profile_defaults("api"),
            natural_language="Sort the array.",
            formal_code="-- Lean scaffold",
            max_compiler_checks=15,
        )
        self.assertTrue(prompt.startswith(LEAN_SYSTEM_PROMPT))
        self.assertIn("Natural language description:\nSort the array.", prompt)
        self.assertIn("Incomplete code:\n-- Lean scaffold", prompt)
        self.assertIn("Claude Code transport note", prompt)
        self.assertIn("at most 15 checks", prompt)
        self.assertNotIn("Before declaring success, perform a semantic audit", prompt)
        self.assertNotIn("AlgorithmPlan.md", prompt)
        self.assertNotIn("ProofState.md", prompt)
        self.assertNotIn("LeanSearch", prompt)

    def test_hard_case_planning_maps_postconditions_before_code(self) -> None:
        prompt = planning_prompt("dijkstra", hard_case_routing=True)
        self.assertIn("proof-feasibility", prompt)
        self.assertIn("every postcondition conjunct", prompt)
        self.assertIn("Do not edit Solution.lean", prompt)
        self.assertIn("AlgorithmPlan.md, and ProofState.md", prompt)

    def test_progress_rescue_requires_an_early_durable_edit(self) -> None:
        prompt = repair_prompt(
            "dijkstra",
            2,
            "previous verification failed",
            LastDanceFeatures.profile_defaults("robust"),
            progress_rescue=True,
        )
        self.assertIn("focused rescue session", prompt)
        self.assertIn("first implementation action", prompt)
        self.assertIn("Do not restart an\nopen-ended analysis", prompt)

    def test_recovers_safe_pending_write_at_budget_boundary(self) -> None:
        workspace = self.root / "recovery"
        workspace.mkdir()
        solution = workspace / "Solution.lean"
        solution.write_text("old")
        recovered = apply_pending_tool_call(
            workspace,
            {
                "id": "tool-1",
                "name": "Write",
                "input": {"file_path": str(solution), "content": "new candidate"},
            },
        )
        self.assertTrue(recovered["recovered"])
        self.assertEqual(solution.read_text(), "new candidate")

    def test_pending_recovery_obeys_tool_policy(self) -> None:
        workspace = self.root / "recovery"
        workspace.mkdir()
        outside = self.root / "outside.lean"
        outside.write_text("safe")
        recovered = apply_pending_tool_call(
            workspace,
            {
                "id": "tool-2",
                "name": "Write",
                "input": {"file_path": str(outside), "content": "overwrite"},
            },
        )
        self.assertFalse(recovered["recovered"])
        self.assertEqual(outside.read_text(), "safe")

    def test_workspace_initialization_clears_old_event_logs(self) -> None:
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "agent_events.jsonl").write_text("old event")
        (workspace / "agent_stderr.log").write_text("old error")
        write_workspace(
            workspace,
            "one",
            "Natural language task",
            "-- Lean scaffold",
            self.root / "config.yaml",
        )
        self.assertFalse((workspace / "agent_events.jsonl").exists())
        self.assertFalse((workspace / "agent_stderr.log").exists())
        self.assertEqual((workspace / "Solution.lean").read_text(), "-- Lean scaffold")

    def test_workspace_resume_preserves_solution_and_event_logs(self) -> None:
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "Solution.lean").write_text("-- partial solution")
        (workspace / "agent_events.jsonl").write_text("old event\n")
        (workspace / "agent_stderr.log").write_text("old error\n")
        write_workspace(
            workspace,
            "one",
            "Natural language task",
            "-- Lean scaffold",
            self.root / "config.yaml",
            preserve_solution=True,
            preserve_logs=True,
        )
        self.assertEqual((workspace / "Solution.lean").read_text(), "-- partial solution")
        self.assertEqual((workspace / "agent_events.jsonl").read_text(), "old event\n")
        self.assertEqual((workspace / "agent_stderr.log").read_text(), "old error\n")

    def test_workspace_can_limit_compiler_checks(self) -> None:
        workspace = self.root / "workspace-limit"
        write_workspace(
            workspace,
            "one",
            "Natural language task",
            "-- Lean scaffold",
            self.root / "config.yaml",
            max_compiler_checks=15,
        )
        checker = (workspace / "check.sh").read_text()
        self.assertIn("Compiler-check limit reached (15).", checker)
        self.assertIn("[compiler check $check_count/15]", checker)
        self.assertFalse((workspace / ".compiler_check_count").exists())

    def test_robust_workspace_uses_cached_local_leansearch_adapter(self) -> None:
        workspace = self.root / "workspace"
        leansearch = self.root / "LeanSearch"
        leansearch.mkdir()
        (leansearch / "search.py").write_text(
            "import json, sys\n"
            "print(json.dumps([[{'query': sys.argv[-1], 'name': 'Nat.add_comm'}]]))\n"
        )
        write_workspace(
            workspace,
            "one",
            "Natural language task",
            "-- Lean scaffold",
            self.root / "config.yaml",
            features=LastDanceFeatures.profile_defaults("robust"),
            leansearch_root=leansearch,
            leansearch_python=Path(sys.executable),
        )
        completed = subprocess.run(
            [str(workspace / "leansearch"), "commutativity of natural addition"],
            cwd=workspace,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Nat.add_comm", completed.stdout)
        query_log = workspace / ".lastdance" / "leansearch_queries.jsonl"
        first = json.loads(query_log.read_text().splitlines()[0])
        self.assertEqual(first["query"], "commutativity of natural addition")
        self.assertFalse(first["cached"])

        ok, detail = leansearch_preflight(
            self.root / "preflight",
            leansearch,
            Path(sys.executable),
            "",
            5,
            10,
        )
        self.assertTrue(ok, detail)
        self.assertEqual(len(detail), 64)

    def test_combines_adaptive_pass_usage(self) -> None:
        def result(verified: bool, cost: float, turns: int, pass_number: int) -> dict:
            return {
                "verified": verified,
                "details": {
                    "rounds": turns - 1,
                    "llm_response": {"code": f"pass {pass_number}", "comment": ""},
                    "verifier_response": {"verified": verified, "feedback": "feedback"},
                    "history": [],
                    "tokens": {"input": 10, "output": 5, "reasoning": 0},
                    "agent": {
                        "pass_number": pass_number,
                        "num_turns": turns,
                        "total_cost_usd": cost,
                        "duration_ms": 100,
                        "duration_api_ms": 80,
                        "timed_out": False,
                    },
                },
            }

        combined = combine_pass_results([result(False, 2.0, 8, 1), result(True, 1.0, 4, 2)])
        details = combined["details"]
        self.assertTrue(combined["verified"])
        self.assertEqual(details["llm_response"]["code"], "pass 2")
        self.assertEqual(details["rounds"], 11)
        self.assertEqual(details["tokens"], {"input": 20, "output": 10, "reasoning": 0})
        self.assertEqual(details["agent"]["compiler_passes"], 2)
        self.assertEqual(details["agent"]["num_turns"], 12)
        self.assertEqual(details["agent"]["total_cost_usd"], 3.0)
        self.assertEqual(len(details["history"]), 2)


if __name__ == "__main__":
    unittest.main()
