"""
LLM provider registry.

Set the LLM_PROVIDER environment variable to select a provider.
Supported values (case-insensitive):

  mock          – built-in deterministic mock (no keys needed)
  azure_openai  – Azure OpenAI   (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY,
                                   AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION)
  openai        – OpenAI          (OPENAI_API_KEY, OPENAI_MODEL)
  anthropic     – Anthropic       (ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
  ollama        – Ollama local    (OLLAMA_BASE_URL, OLLAMA_MODEL)

Optional providers are registered only when their SDK is installed.
"""
from typing import Callable

from llm.base import LLMClient
from llm.mock_llm import MockLLM

# Registry: provider name -> zero-arg factory that returns an LLMClient
_REGISTRY: dict[str, Callable[[], LLMClient]] = {
    "mock": MockLLM,
}


def _register(name: str, factory: Callable[[], LLMClient]) -> None:
    _REGISTRY[name] = factory


# --- optional providers (silently skipped if SDK is missing) ---

try:
    from llm.azure_openai_llm import AzureOpenAILLM
    _register("azure_openai", AzureOpenAILLM.from_env)
except ImportError:
    pass

try:
    from llm.openai_llm import OpenAILLM
    _register("openai", OpenAILLM.from_env)
except ImportError:
    pass

try:
    from llm.anthropic_llm import AnthropicLLM
    _register("anthropic", AnthropicLLM.from_env)
except ImportError:
    pass

try:
    from llm.ollama_llm import OllamaLLM
    _register("ollama", OllamaLLM.from_env)
except ImportError:
    pass


def create_llm(provider: str) -> LLMClient:
    """
    Instantiate the LLM client for the given provider name.

    Raises:
        ValueError   – unknown provider name
        RuntimeError – missing SDK or misconfigured env vars
    """
    key = provider.lower().strip()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Available: {available}"
        )
    try:
        return _REGISTRY[key]()
    except (KeyError, ImportError) as exc:
        raise RuntimeError(
            f"Failed to initialise LLM provider '{provider}': {exc}"
        ) from exc
