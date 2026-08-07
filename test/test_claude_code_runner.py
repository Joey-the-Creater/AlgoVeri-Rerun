from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_claude_code_lean import (
    agent_prompt,
    combine_pass_results,
    repair_prompt,
    task_directories,
    write_workspace,
)


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
