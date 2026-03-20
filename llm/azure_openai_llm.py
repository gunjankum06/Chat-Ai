import os
from typing import List, Dict, Any

from llm.base import LLMClient

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
        from openai import AzureOpenAI  # type: ignore

        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        api_key = os.environ["AZURE_OPENAI_API_KEY"]
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]

        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version
        )
        return AzureOpenAILLM(client, deployment)

    async def complete(self, messages: List[Dict[str, Any]]) -> str:
        # AzureOpenAI SDK is required for this method.
        # Implement the completion logic here.
        raise NotImplementedError("The 'complete' method must be implemented.")