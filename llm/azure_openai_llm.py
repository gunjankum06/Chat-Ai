import os
from typing import List, Dict, Any
from openai import AsyncAzureOpenAI

from llm.base import LLMClient
from agent.tracing import traceable

class AzureOpenAILLM(LLMClient):
    """
    Optional provider: Azure OpenAI via openai SDK.
    Install: pip install openai
    """
    def __init__(self, client, deployment: str):
        self.client = client
        self.deployment = deployment

    @staticmethod
    def from_env():
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        api_key = os.environ["AZURE_OPENAI_API_KEY"]
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]

        client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version
        )
        return AzureOpenAILLM(client, deployment)

    @traceable(run_type="llm", name="azure_openai_complete")
    async def complete(self, messages: List[Dict[str, Any]]) -> str:
        response = await self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=0
        )
        return (response.choices[0].message.content or "").strip()