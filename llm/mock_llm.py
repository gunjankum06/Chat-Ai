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
        user = messages[-1]["content"].strip()

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