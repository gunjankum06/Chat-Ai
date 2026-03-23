import json
import re
from typing import List, Dict, Any
from llm.base import LLMClient

class MockLLM(LLMClient):
    """
    A deterministic mock LLM used to prove the loop works:
      - If user asks for defect details, it calls get_defect_details.
      - If user says greet <name>, it calls greet.
      - Otherwise, final.
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

        m = re.search(r"defect\s+(\d+)", user, re.IGNORECASE)
        if m:
            defect_id = m.group(1)
            return json.dumps({"type": "tool_call", "name": "get_defect_details", "arguments": {"defectId": defect_id}})

        # default: no tool
        return json.dumps({"type": "final", "content": "I can greet you or fetch mock defect details. Try: 'greet Gunjan' or 'get defect 1234 details'."})