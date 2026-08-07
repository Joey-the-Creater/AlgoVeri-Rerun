from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.dashboard_state import DashboardState, line_change_counts, parse_event_log


class DashboardStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.work = self.root / "work"
        self.results = self.root / "results"
        self.task = self.work / "demo"
        self.task.mkdir(parents=True)
        (self.task / "Original.lean").write_text("def value := by\n  sorry\n")
        (self.task / "Solution.lean").write_text("def value := by\n  rfl\n")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_events(self) -> Path:
        events = [
            {
                "type": "system",
                "subtype": "harness_pass_started",
                "pass_number": 1,
                "timestamp": "2026-01-01T00:00:00Z",
            },
            {"type": "system", "subtype": "init", "model": "claude-opus-5", "session_id": "abc"},
            {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 1250},
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:01Z",
                "message": {"content": [{"type": "text", "text": "I will prove it."}]},
            },
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:02Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "Bash",
                            "input": {"command": "./check.sh"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "timestamp": "2026-01-01T00:00:03Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "content": "LEAN VERIFIED",
                            "is_error": False,
                        }
                    ]
                },
            },
        ]
        path = self.task / "agent_events.jsonl"
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        return path

    def test_parses_agent_activity(self) -> None:
        parsed = parse_event_log(self.write_events())
        self.assertEqual(parsed["thinking_tokens"], 1250)
        self.assertEqual(parsed["check_attempts"], 1)
        self.assertTrue(parsed["lean_verified"])
        self.assertTrue(
            any(
                item["title"] == "Compiler pass 1 started"
                for item in parsed["timeline"]
            )
        )
        self.assertTrue(any(item["title"] == "Claude" for item in parsed["timeline"]))
        checker = next(item for item in parsed["timeline"] if item["title"] == "Run Lean checker")
        self.assertEqual(checker["status"], "verified")

    def test_counts_added_and_removed_lines(self) -> None:
        changes = line_change_counts("one\ntwo\n", "one\nchanged\nthree\n")
        self.assertEqual(changes, {"added": 2, "removed": 1})

    def test_marks_orphaned_event_stream_interrupted(self) -> None:
        self.write_events()
        dashboard = DashboardState(self.work, self.results, tasks=["demo"])
        snapshot = dashboard.snapshot()
        self.assertEqual(snapshot["tasks"][0]["status"], "interrupted")
        self.assertEqual(snapshot["summary"]["interrupted"], 1)

    def test_saved_result_overrides_interrupted_state(self) -> None:
        self.write_events()
        result_dir = self.results / "lean"
        result_dir.mkdir(parents=True)
        result = {
            "verified": True,
            "details": {
                "llm_response": {"code": "def value := by rfl", "comment": "done"},
                "verifier_response": {"verified": True, "feedback": "Verified successfully."},
                "agent": {"num_turns": 3, "total_cost_usd": 0.25, "duration_ms": 5000},
            },
        }
        (result_dir / "claude-code-opus-5_demo_lean.json").write_text(json.dumps(result))
        dashboard = DashboardState(self.work, self.results, tasks=["demo"])
        summary = dashboard.snapshot()["tasks"][0]
        self.assertEqual(summary["status"], "verified")
        self.assertEqual(summary["cost_usd"], 0.25)
        self.assertEqual(summary["duration_seconds"], 5.0)
        self.assertEqual(summary["loc_added"], 1)
        self.assertEqual(summary["loc_removed"], 1)

    def test_catalog_scope_survives_targeted_retry_manifest(self) -> None:
        (self.work / "run_manifest.json").write_text(
            json.dumps({"state": "running", "tasks": ["retry_only"]})
        )
        dashboard = DashboardState(
            self.work,
            self.results,
            tasks=["previous_result", "retry_only"],
        )
        self.assertEqual(
            [item["name"] for item in dashboard.snapshot()["tasks"]],
            ["previous_result", "retry_only"],
        )

    def test_active_retry_overrides_previous_saved_failure_state(self) -> None:
        (self.work / "run_manifest.json").write_text(
            json.dumps(
                {
                    "state": "running",
                    "runner_pid": 123,
                    "current_task": "demo",
                    "tasks": ["demo"],
                }
            )
        )
        result_dir = self.results / "lean"
        result_dir.mkdir(parents=True)
        (result_dir / "claude-code-opus-5_demo_lean.json").write_text(
            json.dumps({"verified": False, "details": {}})
        )
        with patch("src.agent.dashboard_state.pid_is_runner", return_value=True):
            summary = DashboardState(self.work, self.results).snapshot()["tasks"][0]
        self.assertEqual(summary["status"], "active")


if __name__ == "__main__":
    unittest.main()
