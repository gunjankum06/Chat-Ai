from abc import ABC, abstractmethod
from typing import List, Dict, Any

class LLMClient(ABC):
    @abstractmethod
    async def complete(self, messages: List[Dict[str, Any]]) -> str:
        """
        Return a string that MUST be valid JSON for LLMDecision.
        """
        raise NotImplementedError