from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

class FinalAnswer(BaseModel):
    type: Literal["final"] = "final"
    content: str

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