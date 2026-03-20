SYSTEM_PROMPT = """You are an agentic assistant running in a CLI.
You have access to MCP tools. You must decide whether to call a tool.

IMPORTANT RULES:
1) If a tool is needed, respond ONLY with JSON:
   {"type":"tool_call","name":"<tool_name>","arguments":{...}}

2) If no tool is needed, respond ONLY with JSON:
   {"type":"final","content":"<answer>"}

3) Do not include markdown fences. Do not include extra text outside JSON.
4) Use the provided tool schemas to form correct arguments.
"""

def tools_to_compact_text(tools: list) -> str:
    """
    tools is a list of MCP Tool objects. We create a compact description for the LLM.
    """
    lines = []
    for t in tools:
        lines.append(f"- name: {t.name}")
        if getattr(t, "description", None):
            lines.append(f"  description: {t.description}")
        if getattr(t, "inputSchema", None):
            lines.append(f"  inputSchema: {t.inputSchema}")
    return "\n".join(lines)