import os
from typing import List, Dict, Any

from llm.base import LLMClient
from agent.tracing import traceable


class AnthropicLLM(LLMClient):
    """
    Anthropic Claude provider.

    Install:  pip install anthropic

    Required env vars:
        ANTHROPIC_API_KEY  — API key from console.anthropic.com
        ANTHROPIC_MODEL    — model ID, e.g. "claude-opus-4-5" (default: claude-opus-4-5)
    """

    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    @staticmethod
    def from_env() -> "AnthropicLLM":
        import anthropic  # deferred import so missing SDK gives a clear ImportError
        api_key = os.environ["ANTHROPIC_API_KEY"]
        model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")
        client = anthropic.AsyncAnthropic(api_key=api_key)
        return AnthropicLLM(client, model)

    @traceable(run_type="llm", name="anthropic_complete")
    async def complete(self, messages: List[Dict[str, Any]]) -> str:
        # Anthropic requires the system prompt as a separate top-level parameter.
        # Tool results from our custom JSON protocol are sent as plain user messages.
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        system_text = "\n\n".join(system_parts)

        conv: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                continue
            elif role in ("user", "assistant"):
                conv.append({"role": role, "content": content})
            elif role == "tool":
                # Custom protocol: tool results fed back as user messages
                conv.append({"role": "user", "content": content})

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": conv,
            "max_tokens": 4096,
        }
        if system_text:
            kwargs["system"] = system_text

        response = await self.client.messages.create(**kwargs)
        return (response.content[0].text or "").strip()
