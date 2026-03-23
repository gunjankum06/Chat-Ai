from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel

class LLMDecision(BaseModel):
    """
    The LLM must return one of:
      - {"type":"tool_call", "name":"tool_name", "arguments":{...}}
      - {"type":"final", "content":"..."}
    """
    type: Literal["tool_call", "final"]
    name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    content: Optional[str] = None