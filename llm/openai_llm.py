import os
from typing import List, Dict, Any
from openai import AsyncOpenAI

from llm.base import LLMClient
from agent.tracing import traceable


class OpenAILLM(LLMClient):
    """
    Standard OpenAI provider (api.openai.com).

    Required env vars:
        OPENAI_API_KEY  — API key from platform.openai.com
        OPENAI_MODEL    — model name, e.g. "gpt-4o" (default: gpt-4o)
    """

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model

    @staticmethod
    def from_env() -> "OpenAILLM":
        api_key = os.environ["OPENAI_API_KEY"]
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        client = AsyncOpenAI(api_key=api_key)
        return OpenAILLM(client, model)

    @traceable(run_type="llm", name="openai_complete")
    async def complete(self, messages: List[Dict[str, Any]]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()
