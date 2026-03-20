import json
from typing import Any, Dict
from pydantic import ValidationError

from agent.protocol import LLMDecision

def safe_parse_llm_json(text: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM output. LLM is instructed to output pure JSON.
    We still guard for accidental whitespace.
    """
    text = text.strip()
    return json.loads(text)

def validate_decision(obj: Dict[str, Any]) -> LLMDecision:
    """
    Validate the response structure.
    """
    try:
        return LLMDecision(**obj)
    except ValidationError as e:
        raise ValueError(f"LLM output not in required schema: {e}") from e