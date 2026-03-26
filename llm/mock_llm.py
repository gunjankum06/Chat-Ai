import json
import re
from typing import List, Dict, Any
from llm.base import LLMClient

class MockLLM(LLMClient):
    """
    Deterministic mock LLM for local development and testing.
    Recognises a small set of patterns and routes them to MCP tools;
    falls back to a final text answer for everything else.
    """
    async def complete(self, messages: List[Dict[str, Any]]) -> str:
        # If the last message is a tool result, return its content as the final answer.
        last = messages[-1] if messages else {}
        if last.get("role") == "tool":
            answer = last.get("content", "(no result)")
            return json.dumps({"type": "final", "content": answer})

        # Find the last user message to decide which tool to call.
        user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user = str(msg.get("content", "")).strip()
                break

        m = re.match(r"greet\s+(.+)$", user, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            return json.dumps({"type": "tool_call", "name": "greet", "arguments": {"name": name}})

        # Match "defect 123", "get 123 details", "get defect 123", etc.
        m = re.search(r"(?:defect\s+(\d+)|get\s+(?:defect\s+)?(\d+))", user, re.IGNORECASE)
        if m:
            defect_id = m.group(1) or m.group(2)
            return json.dumps({"type": "tool_call", "name": "get_defect_details", "arguments": {"defectId": defect_id}})

        # default: no tool needed
        return json.dumps({"type": "final", "content": "I'm a mock LLM. Try: 'greet <name>' or 'get defect <id>'."})