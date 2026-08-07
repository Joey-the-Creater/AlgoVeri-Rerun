from __future__ import annotations

import unittest

from src.agent.claude_tool_policy import policy_denial


class ClaudeToolPolicyTests(unittest.TestCase):
    def event(self, tool: str, tool_input: dict) -> dict:
        return {"cwd": "/tmp/agent-task", "tool_name": tool, "tool_input": tool_input}

    def test_allows_exact_checker(self) -> None:
        self.assertIsNone(policy_denial(self.event("Bash", {"command": "./check.sh"})))

    def test_allows_safe_workspace_inspection(self) -> None:
        self.assertIsNone(policy_denial(self.event("Bash", {"command": "pwd"})))
        self.assertIsNone(policy_denial(self.event("Bash", {"command": "ls -la"})))
        self.assertIsNone(
            policy_denial(
                self.event("Bash", {"command": "ls -la /tmp/agent-task"})
            )
        )

    def test_rejects_pipes_and_other_shell_commands(self) -> None:
        self.assertIsNotNone(
            policy_denial(self.event("Bash", {"command": "./check.sh | tail"}))
        )
        self.assertIsNotNone(
            policy_denial(self.event("Bash", {"command": "ls -la /tmp"}))
        )
        self.assertIsNotNone(policy_denial(self.event("Bash", {"command": "git status"})))

    def test_allows_solution_edits_only(self) -> None:
        self.assertIsNone(
            policy_denial(
                self.event("Edit", {"file_path": "/tmp/agent-task/Solution.lean"})
            )
        )
        self.assertIsNotNone(
            policy_denial(self.event("Write", {"file_path": "/tmp/agent-task/check.sh"}))
        )

    def test_allows_safe_workspace_reads_only(self) -> None:
        for name in ("TASK.md", "Solution.lean", "Original.lean", "Merged.lean", "check.sh"):
            self.assertIsNone(
                policy_denial(
                    self.event("Read", {"file_path": f"/tmp/agent-task/{name}"})
                ),
                name,
            )
        self.assertIsNotNone(
            policy_denial(self.event("Read", {"file_path": "/etc/passwd"}))
        )


if __name__ == "__main__":
    unittest.main()
