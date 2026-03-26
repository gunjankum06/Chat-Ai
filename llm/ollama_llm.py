import os
from typing import List, Dict, Any
from openai import AsyncOpenAI

from llm.base import LLMClient


class OllamaLLM(LLMClient):
    """
    Ollama local model provider via its OpenAI-compatible API.

    Install Ollama: https://ollama.com  then pull a model, e.g.:
        ollama pull llama3

    Env vars:
        OLLAMA_BASE_URL  — Ollama server URL (default: http://localhost:11434/v1)
        OLLAMA_MODEL     — model name, e.g. "llama3", "mistral" (default: llama3)
    """

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model

    @staticmethod
    def from_env() -> "OllamaLLM":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        model = os.getenv("OLLAMA_MODEL", "llama3")
        # Ollama does not require authentication; the openai SDK needs a non-empty key
        client = AsyncOpenAI(base_url=base_url, api_key="ollama")
        return OllamaLLM(client, model)

    async def complete(self, messages: List[Dict[str, Any]]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()
