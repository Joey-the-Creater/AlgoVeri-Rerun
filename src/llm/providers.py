"""Provider implementations for different LLM backends.

This file exposes a message-first ProviderBase and three concrete adapters:
- OpenAICompatibleProvider: uses `openai.OpenAI` client (can be pointed to Google
  GenAI by using the OpenAI-compatible base_url).
- AnthropicProvider: uses Anthropic's native Messages API for Claude models.
- GeminiProvider: prefers `google.genai` client, falls back to the OpenAI-compatible adapter.
"""
from typing import Any, Dict, List, Optional
import os
import logging
from openai import OpenAI

# Multi-round chat abstractions

class MultiTurnChat:
    """Abstract multi-turn chat session.

    Methods:
      - send_message(text, role='user') -> dict with 'text' and 'role'
      - get_history() -> list[dict] with keys ('role','content', ...)
      - close() -> optional cleanup
    """
    def send_message(self, text: str, role: str = "user", temperature: float = 1.0) -> Dict[str, Any]:
        raise NotImplementedError()

    def get_history(self) -> List[Dict[str, Any]]:
        raise NotImplementedError()
    
    def get_total_tokens(self) -> float:
        raise NotImplementedError()

    def close(self) -> None:
        return None


class ProviderBase:
    """Provider that can create multi-turn chat sessions."""
    name: str = "base"

    def __init__(self, **kwargs: Any):
        self.config = kwargs
        self.logger = logging.getLogger(self.__class__.__name__)

    def new_chat(self, *, model: str = "", system_prompt: Optional[str] = None, **kwargs: Any) -> MultiTurnChat:
        """Create a new multi-turn chat session for the provider."""
        raise NotImplementedError()

    def close(self) -> None:
        return None


# OpenAI-compatible adapter intentionally omitted / unimplemented
RESPONSES_API_MODEL_PREFIXES = (
    "gpt-5.3-codex",
    "gpt-5.5",
    "gpt-5.6",
)


def _uses_responses_api(model: str) -> bool:
    normalized = model.lower().split("/")[-1]
    return normalized.startswith(RESPONSES_API_MODEL_PREFIXES)


class OpenAIMultiTurnChat(MultiTurnChat):
    def __init__(
        self,
        client: OpenAI,
        model: str,
        system_prompt: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ):
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._use_responses_api = _uses_responses_api(model)
        normalized_model = model.lower().split("/")[-1]
        if normalized_model.startswith("gpt-5.5") and reasoning_effort == "max":
            raise ValueError("GPT-5.5 supports reasoning effort through xhigh, not max")
        self._history: List[Dict[str, str]] = []
        self._total_usage = {"input": 0, "output": 0, "reasoning": 0}

        if system_prompt:
            self._history.append({"role": "system", "content": system_prompt})

    def send_message(self, text: str, role: str = "user", temperature: float = 1.0) -> Dict[str, Any]:
        # 1. Update local state
        self._history.append({"role": role, "content": text})

        # 2. Call API. GPT-5.5, GPT-5.6, and recent Codex models use the
        # Responses API so reasoning effort is explicit and no unsupported
        # sampling parameter is sent.
        if self._use_responses_api:
            request: Dict[str, Any] = {
                "model": self._model,
                "input": [message.copy() for message in self._history],
            }
            if self._reasoning_effort:
                request["reasoning"] = {"effort": self._reasoning_effort}
            if self._max_output_tokens:
                request["max_output_tokens"] = self._max_output_tokens
            response = self._client.responses.create(**request)
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=self._history,
                temperature=temperature,
            )

        # 3. Parse response
        if self._use_responses_api:
            content = response.output_text
        else:
            message_obj = response.choices[0].message
            content = message_obj.content

        if not content:
            raise RuntimeError(f"Model {self._model} returned no text output")
        
        # 4. Update state with assistant response
        self._history.append({"role": "assistant", "content": content})
        
        # 5. Track token usage (OpenAI returns usage stats in the response)
        if response.usage:
            if self._use_responses_api:
                self._total_usage["input"] += getattr(response.usage, "input_tokens", 0)
                self._total_usage["output"] += getattr(response.usage, "output_tokens", 0)
                output_details = getattr(response.usage, "output_tokens_details", None)
                self._total_usage["reasoning"] += getattr(output_details, "reasoning_tokens", 0) if output_details else 0
            else:
                self._total_usage["input"] += response.usage.prompt_tokens
                # Note: For strict "price" calculation in benchmarks, you might want to 
                # track incremental input tokens differently, but this sums up API reports.
                self._total_usage["output"] += response.usage.completion_tokens

        return {
            "text": content,
            "role": "assistant",
            "raw": response
        }

    def get_history(self) -> List[Dict[str, Any]]:
        # Return copy to prevent external mutation
        return [msg.copy() for msg in self._history]
    
    def get_total_tokens(self) -> float:
        # Placeholder for price logic. 
        # You could implement specific pricing per model (e.g. gpt-4o vs 4o-mini)
        # For now, we return total tokens as a proxy or 0.0
        return self._total_usage.copy()


class OpenAICompatibleProvider(ProviderBase):
    name = "openai_compatible"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        configured_key = api_key or os.environ.get("OPENAI_API_KEY") or "EMPTY"
        self._api_key = configured_key.strip()  # Avoid invalid auth headers from shell/file newlines.
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        
        # Initialize client immediately
        if self._base_url:
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        else:
            self._client = OpenAI(api_key=self._api_key)

    def new_chat(self, *, model: str = "gpt-4o", system_prompt: Optional[str] = None, **kwargs: Any) -> MultiTurnChat:
        return OpenAIMultiTurnChat(
            self._client,
            model=model,
            system_prompt=system_prompt,
            reasoning_effort=self._reasoning_effort,
            max_output_tokens=self._max_output_tokens,
        )


def _anthropic_content_block(block: Any) -> Dict[str, Any]:
    """Convert an Anthropic SDK content block into replayable plain data."""
    if isinstance(block, dict):
        return block.copy()
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)

    data: Dict[str, Any] = {}
    for field in ("type", "text", "thinking", "signature", "data"):
        value = getattr(block, field, None)
        if value is not None:
            data[field] = value
    return data


class AnthropicMultiTurnChat(MultiTurnChat):
    """Stateless multi-turn replay over Anthropic's Messages API."""

    def __init__(
        self,
        client: Any,
        model: str,
        system_prompt: Optional[str] = None,
        reasoning_effort: str = "medium",
        max_output_tokens: int = 32768,
        thinking_mode: str = "adaptive",
    ):
        if reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Claude Opus 5 effort must be low, medium, high, xhigh, or max")
        if max_output_tokens <= 0:
            raise ValueError("Anthropic max_output_tokens must be positive")
        if thinking_mode not in {"adaptive", "disabled"}:
            raise ValueError("Anthropic thinking mode must be adaptive or disabled")
        if thinking_mode == "disabled" and reasoning_effort in {"xhigh", "max"}:
            raise ValueError("Claude Opus 5 cannot disable thinking at xhigh or max effort")

        self._client = client
        self._model = model
        self._system_prompt = system_prompt or ""
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._thinking_mode = thinking_mode
        self._api_history: List[Dict[str, Any]] = []
        self._display_history: List[Dict[str, str]] = []
        self._total_usage = {"input": 0, "output": 0, "reasoning": 0}

        if self._system_prompt:
            self._display_history.append({"role": "system", "content": self._system_prompt})

    def send_message(self, text: str, role: str = "user", temperature: float = 1.0) -> Dict[str, Any]:
        if role != "user":
            raise ValueError("Anthropic Messages API turns sent by this harness must use role='user'")

        user_message = {"role": "user", "content": text}
        self._api_history.append(user_message)
        self._display_history.append(user_message.copy())

        request: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_output_tokens,
            "messages": [message.copy() for message in self._api_history],
            "output_config": {"effort": self._reasoning_effort},
            "thinking": {"type": self._thinking_mode},
        }
        if self._system_prompt:
            request["system"] = self._system_prompt

        # Anthropic requires streaming for requests whose configured token budget
        # may take longer than the non-streaming HTTP timeout. Consume the stream
        # to a final Message so the rest of the harness keeps the same behavior.
        with self._client.messages.stream(**request) as stream:
            response = stream.get_final_message()
        replay_blocks = [_anthropic_content_block(block) for block in response.content]
        text_blocks = [block.get("text", "") for block in replay_blocks if block.get("type") == "text"]
        content = "\n".join(part for part in text_blocks if part)

        usage = getattr(response, "usage", None)
        if usage:
            self._total_usage["input"] += getattr(usage, "input_tokens", 0)
            self._total_usage["output"] += getattr(usage, "output_tokens", 0)
            details = getattr(usage, "output_tokens_details", None)
            self._total_usage["reasoning"] += getattr(details, "thinking_tokens", 0) if details else 0

        if not content:
            block_types = [block.get("type", "unknown") for block in replay_blocks]
            stop_reason = getattr(response, "stop_reason", None)
            request_id = getattr(response, "_request_id", None)
            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "output_tokens", None) if usage else None
            raise RuntimeError(
                f"Model {self._model} returned no text output "
                f"(stop_reason={stop_reason!r}, block_types={block_types!r}, "
                f"input_tokens={input_tokens!r}, output_tokens={output_tokens!r}, "
                f"request_id={request_id!r}). If stop_reason is 'max_tokens', "
                "increase MAX_OUTPUT_TOKENS or lower REASONING_EFFORT."
            )

        # Preserve thinking/signature blocks exactly for valid multi-turn replay,
        # while exposing a JSON-friendly visible history to result files.
        self._api_history.append({"role": "assistant", "content": replay_blocks})
        self._display_history.append({"role": "assistant", "content": content})

        return {"text": content, "role": "assistant", "raw": response}

    def get_history(self) -> List[Dict[str, Any]]:
        return [message.copy() for message in self._display_history]

    def get_total_tokens(self) -> Dict[str, int]:
        return self._total_usage.copy()


class AnthropicProvider(ProviderBase):
    name = "anthropic"

    def __init__(
        self,
        api_key: Optional[str] = None,
        reasoning_effort: str = "medium",
        max_output_tokens: int = 32768,
        thinking_mode: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        configured_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not configured_key or not configured_key.strip():
            raise RuntimeError("Set ANTHROPIC_API_KEY before using Claude models")

        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("Install the Anthropic SDK with: python -m pip install anthropic") from exc

        self._api_key = configured_key.strip()
        self._client = Anthropic(api_key=self._api_key)
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._thinking_mode = thinking_mode or os.environ.get("ANTHROPIC_THINKING", "adaptive")

    def new_chat(
        self,
        *,
        model: str = "claude-opus-5",
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> MultiTurnChat:
        return AnthropicMultiTurnChat(
            self._client,
            model=model,
            system_prompt=system_prompt,
            reasoning_effort=self._reasoning_effort,
            max_output_tokens=self._max_output_tokens,
            thinking_mode=self._thinking_mode,
        )


# Bonus: Your VLLMProvider can simply inherit from this
class VLLMProvider(OpenAICompatibleProvider):
    name = "vllm"
    
    def __init__(self, endpoint: Optional[str] = None, **kwargs: Any):
        # vLLM usually runs at http://localhost:8000/v1
        base_url = endpoint or "http://localhost:8000/v1"
        super().__init__(api_key="EMPTY", base_url=base_url, **kwargs)


# Gemini implementation (google.genai preferred)
class GeminiMultiTurnChat(MultiTurnChat):
    def __init__(self, genai_chat: Any, model_name: str = "", genai_client: Optional[Any] = None):
        self._chat = genai_chat
        self._client = genai_client
        self._model_name = model_name
        self.cached_content_token_count = 0
        self.prompt_token_count = 0
        self.thoughts_token_count = 0
        self.candidates_token_count = 0

    def send_message(self, text: str, role: str = "user", temperature: float = 1.0) -> Dict[str, Any]:
        """
        Send a message into the underlying gemini/genai chat session.
        Returns a dict: {'text': <assistant text>, 'role': 'assistant', 'raw': <raw response>}
        """
        # genai.Client.chat.send_message returns an object with .text per user's snippet
        resp = self._chat.send_message(text)
        if resp.usage_metadata.cached_content_token_count:
            self.cached_content_token_count += resp.usage_metadata.cached_content_token_count
        if resp.usage_metadata.prompt_token_count:
            self.prompt_token_count += resp.usage_metadata.prompt_token_count
        if resp.usage_metadata.thoughts_token_count:
            self.thoughts_token_count += resp.usage_metadata.thoughts_token_count
        if resp.usage_metadata.candidates_token_count:
            self.candidates_token_count += resp.usage_metadata.candidates_token_count
        text_out = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else str(resp))
        return {"text": text_out, "role": "assistant", "raw": resp}

    def get_history(self) -> List[Dict[str, Any]]:
        """Return history in normalized form: list of {'role':..., 'content':...}"""
        hist = []
        try:
            for message in self._chat.get_history():
                role = getattr(message, "role", None) or (message.get("role") if isinstance(message, dict) else None)
                # message.parts[0].text in your snippet; handle objects/dicts
                content = None
                try:
                    parts = getattr(message, "parts", None) or (message.get("parts") if isinstance(message, dict) else None)
                    if parts:
                        first = parts[0]
                        content = getattr(first, "text", None) or (first.get("text") if isinstance(first, dict) else None)
                except Exception:
                    content = None
                # fallback: try message.text
                if content is None:
                    content = getattr(message, "text", None) or (message.get("text") if isinstance(message, dict) else None)
                hist.append({"role": role or "unknown", "content": content})
        except Exception:
            # If underlying client doesn't support get_history or fails, return empty
            pass
        return hist
    
    def get_total_tokens(self):
        #return self._client.models.count_tokens(model=self._model_name, contents=self._chat.get_history()).total_tokens if self._client else 0
        return {"cached_content": self.cached_content_token_count, "prompt": self.prompt_token_count, "thoughts": self.thoughts_token_count, "candidates": self.candidates_token_count}

    def close(self) -> None:
        # genai chat objects currently do not require explicit close; keep for API parity
        return None


class GeminiProvider(ProviderBase):
    """Gemini provider using google.genai; falls back to raising error if unavailable."""
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self.logger = logging.getLogger("GeminiProvider")
        self._genai = None
        self._client = None
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GENAI_API_KEY")

        try:
            from google import genai  # type: ignore
            self._genai = genai
            try:
                if self._api_key:
                    self._client = genai.Client(api_key=self._api_key)
                else:
                    self._client = genai.Client()
            except TypeError:
                self._client = genai.Client()
        except Exception as e:
            self.logger.debug("google.genai import failed: %s", e)
            self._genai = None
            self._client = None

    def new_chat(self, *, model: str = "gemini-2.5-flash", system_prompt: Optional[str] = None, **kwargs: Any) -> MultiTurnChat:
        if self._client is None:
            raise RuntimeError("google.genai client not available; install google-genai and set GEMINI_API_KEY/GENAI_API_KEY")

        # create chat and optionally send a system prompt
        chat = self._client.chats.create(model=model)
        mtchat = GeminiMultiTurnChat(chat, model_name=model, genai_client=self._client)
        if system_prompt:
            # use send_message with role system if client doesn't support it natively,
            # we simply send the system prompt first (client may treat first message as system)
            try:
                # some genai versions support chat.send_message with role; try best-effort
                if hasattr(chat, "send_message"):
                    mtchat.send_message(system_prompt, role="system")
            except Exception:
                # ignore failures for system prompt injection
                self.logger.debug("failed to send system_prompt to gemini chat (non-fatal)")
        return mtchat

    def close(self) -> None:
        # nothing to close at provider level
        return None
