from __future__ import annotations

import unittest
from pathlib import Path

from scripts.merge_claude_repair_result import merge_results


def result(verified: bool, cost: float, turns: int, name: str) -> dict:
    return {
        "verified": verified,
        "details": {
            "rounds": turns - 1,
            "tokens": {"input": 10, "output": 20, "reasoning": 0},
            "verifier_response": {"verified": verified, "feedback": name},
            "agent": {
                "session_id": name,
                "num_turns": turns,
                "total_cost_usd": cost,
                "duration_ms": 100,
                "duration_api_ms": 80,
                "timed_out": False,
            },
            "history": [],
        },
    }


class MergeClaudeRepairResultTests(unittest.TestCase):
    def test_combines_initial_and_one_repair_session(self) -> None:
        merged = merge_results(
            result(False, 2.0, 5, "initial"),
            result(True, 1.5, 3, "repair"),
            Path("initial.json"),
            Path("repair.json"),
        )
        agent = merged["details"]["agent"]
        self.assertTrue(merged["verified"])
        self.assertTrue(agent["baseline_plus_repair"])
        self.assertEqual(agent["total_sessions"], 2)
        self.assertEqual(agent["total_cost_usd"], 3.5)
        self.assertEqual(agent["num_turns"], 8)
        self.assertEqual(len(merged["details"]["history"]), 2)
        self.assertEqual(
            merged["details"]["tokens"],
            {"input": 20, "output": 40, "reasoning": 0},
        )


if __name__ == "__main__":
    unittest.main()
