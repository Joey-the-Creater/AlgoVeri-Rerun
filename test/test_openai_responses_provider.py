from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.llm.providers import OpenAICompatibleProvider, OpenAIMultiTurnChat, _uses_responses_api


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(
            input_tokens=10,
            output_tokens=7,
            output_tokens_details=SimpleNamespace(reasoning_tokens=3),
        )
        return SimpleNamespace(output_text="assistant output", usage=usage)


class FakeChatCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(prompt_tokens=5, completion_tokens=2)
        message = SimpleNamespace(content="chat output")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class OpenAIResponsesProviderTest(unittest.TestCase):
    def test_gpt55_uses_responses_with_reasoning_and_without_temperature(self):
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        chat = OpenAIMultiTurnChat(
            client,
            "gpt-5.5",
            reasoning_effort="medium",
            max_output_tokens=32768,
        )

        result = chat.send_message("prove this")

        self.assertEqual(result["text"], "assistant output")
        self.assertEqual(responses.calls[0]["reasoning"], {"effort": "medium"})
        self.assertEqual(responses.calls[0]["max_output_tokens"], 32768)
        self.assertNotIn("temperature", responses.calls[0])
        self.assertEqual(chat.get_total_tokens(), {"input": 10, "output": 7, "reasoning": 3})

    def test_gpt56_sol_replays_multiturn_history(self):
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        chat = OpenAIMultiTurnChat(client, "gpt-5.6-sol", reasoning_effort="high")

        chat.send_message("first")
        chat.send_message("revision")

        second_input = responses.calls[1]["input"]
        self.assertEqual([message["role"] for message in second_input], ["user", "assistant", "user"])
        self.assertEqual(second_input[-1]["content"], "revision")

    def test_gpt56_none_forwards_temperature(self):
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        chat = OpenAIMultiTurnChat(client, "gpt-5.6-sol", reasoning_effort="none")

        chat.send_message("judge this", temperature=0.0)

        self.assertEqual(responses.calls[0]["reasoning"], {"effort": "none"})
        self.assertEqual(responses.calls[0]["temperature"], 0.0)

    def test_older_models_keep_chat_completions_path(self):
        completions = FakeChatCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        chat = OpenAIMultiTurnChat(client, "gpt-5-mini")

        result = chat.send_message("hello", temperature=0.5)

        self.assertEqual(result["text"], "chat output")
        self.assertEqual(completions.calls[0]["temperature"], 0.5)

    def test_model_routing(self):
        self.assertTrue(_uses_responses_api("gpt-5.5"))
        self.assertTrue(_uses_responses_api("gpt-5.6-sol"))
        self.assertFalse(_uses_responses_api("gpt-5-mini"))

    def test_api_key_line_endings_are_stripped(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key\n"}):
            provider = OpenAICompatibleProvider()
        self.assertEqual(provider._api_key, "test-key")


if __name__ == "__main__":
    unittest.main()
