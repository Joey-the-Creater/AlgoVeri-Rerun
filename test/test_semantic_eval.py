from __future__ import annotations

import unittest

from src.eval.semantic_eval import SemanticEval


class RecordingChat:
    def __init__(self) -> None:
        self.temperatures: list[float] = []

    def send_message(self, text: str, role: str = "user", temperature: float = 1.0):
        self.temperatures.append(temperature)
        return {
            "text": "<analysis>The implementation follows the task.</analysis>"
            "<conclusion>YES</conclusion>"
        }


class RecordingProvider:
    def __init__(self) -> None:
        self.chat = RecordingChat()

    def new_chat(self, **kwargs):
        return self.chat


class SemanticEvalTemperatureTests(unittest.TestCase):
    def test_forwards_configured_temperature_to_judge(self) -> None:
        provider = RecordingProvider()
        result = SemanticEval(provider, temperature=0.0).run_single(
            natural_language="Implement the algorithm.",
            formal_code="def answer := 1",
            model="gpt-5.4",
            filename="",
        )
        self.assertTrue(result["parsed"])
        self.assertTrue(result["verdict"])
        self.assertEqual(provider.chat.temperatures, [0.0])


if __name__ == "__main__":
    unittest.main()
