from types import SimpleNamespace
import unittest

from src.llm.providers import AnthropicMultiTurnChat


class FakeMessages:
    def __init__(self):
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        content = [
            SimpleNamespace(
                type="thinking",
                thinking="internal",
                signature="signed",
                model_dump=lambda exclude_none=True: {
                    "type": "thinking",
                    "thinking": "internal",
                    "signature": "signed",
                },
            ),
            SimpleNamespace(
                type="text",
                text="Lean answer",
                model_dump=lambda exclude_none=True: {"type": "text", "text": "Lean answer"},
            ),
        ]
        usage = SimpleNamespace(
            input_tokens=11,
            output_tokens=9,
            output_tokens_details=SimpleNamespace(thinking_tokens=4),
        )
        response = SimpleNamespace(content=content, usage=usage)
        return FakeMessageStream(response)


class FakeMessageStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def get_final_message(self):
        return self.response


class AnthropicProviderTests(unittest.TestCase):
    def test_opus_uses_native_messages_api_and_replays_thinking_blocks(self):
        messages = FakeMessages()
        client = SimpleNamespace(messages=messages)
        chat = AnthropicMultiTurnChat(
            client,
            "claude-opus-5",
            system_prompt="system guidance",
            reasoning_effort="medium",
            max_output_tokens=32768,
        )

        first = chat.send_message("first proof")
        chat.send_message("compiler feedback")

        self.assertEqual(first["text"], "Lean answer")
        self.assertEqual(messages.calls[0]["model"], "claude-opus-5")
        self.assertEqual(messages.calls[0]["system"], "system guidance")
        self.assertEqual(messages.calls[0]["output_config"], {"effort": "medium"})
        self.assertEqual(messages.calls[0]["thinking"], {"type": "adaptive"})
        self.assertEqual(messages.calls[0]["max_tokens"], 32768)
        replay = messages.calls[1]["messages"]
        self.assertEqual([turn["role"] for turn in replay], ["user", "assistant", "user"])
        self.assertEqual(replay[1]["content"][0]["signature"], "signed")
        self.assertEqual(chat.get_total_tokens(), {"input": 22, "output": 18, "reasoning": 8})
        self.assertEqual(chat.get_history()[-1], {"role": "assistant", "content": "Lean answer"})

    def test_opus_rejects_unsupported_none_effort(self):
        client = SimpleNamespace(messages=FakeMessages())
        with self.assertRaisesRegex(ValueError, "effort"):
            AnthropicMultiTurnChat(client, "claude-opus-5", reasoning_effort="none")

    def test_opus_can_disable_thinking_at_medium_effort(self):
        messages = FakeMessages()
        chat = AnthropicMultiTurnChat(
            SimpleNamespace(messages=messages),
            "claude-opus-5",
            reasoning_effort="medium",
            thinking_mode="disabled",
        )
        chat.send_message("proof")
        self.assertEqual(messages.calls[0]["thinking"], {"type": "disabled"})

    def test_opus_rejects_disabled_thinking_at_max_effort(self):
        with self.assertRaisesRegex(ValueError, "cannot disable thinking"):
            AnthropicMultiTurnChat(
                SimpleNamespace(messages=FakeMessages()),
                "claude-opus-5",
                reasoning_effort="max",
                thinking_mode="disabled",
            )

    def test_empty_text_reports_stop_reason_usage_and_block_types(self):
        thinking = SimpleNamespace(
            type="thinking",
            thinking="internal",
            signature="signed",
            model_dump=lambda exclude_none=True: {
                "type": "thinking",
                "thinking": "internal",
                "signature": "signed",
            },
        )
        usage = SimpleNamespace(
            input_tokens=123,
            output_tokens=32768,
            output_tokens_details=SimpleNamespace(thinking_tokens=32768),
        )
        response = SimpleNamespace(
            content=[thinking],
            usage=usage,
            stop_reason="max_tokens",
            _request_id="req_test",
        )
        messages = SimpleNamespace(
            stream=lambda **kwargs: FakeMessageStream(response),
        )
        chat = AnthropicMultiTurnChat(
            SimpleNamespace(messages=messages),
            "claude-opus-5",
            reasoning_effort="medium",
            max_output_tokens=32768,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "stop_reason='max_tokens'.*block_types=\\['thinking'\\].*output_tokens=32768.*req_test",
        ):
            chat.send_message("hard Lean proof")
        self.assertEqual(
            chat.get_total_tokens(),
            {"input": 123, "output": 32768, "reasoning": 32768},
        )


if __name__ == "__main__":
    unittest.main()
