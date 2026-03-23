import json
import logging
import os
from typing import List, Dict, Any

from rich.console import Console
from rich.panel import Panel

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.prompts import SYSTEM_PROMPT, tools_to_compact_text
from agent.util import safe_parse_llm_json, validate_decision

from llm.base import LLMClient
from llm.mock_llm import MockLLM
try:
    from llm.azure_openai_llm import AzureOpenAILLM
except Exception:
    AzureOpenAILLM = None  # optional dependency

console = Console()
logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Orchestrates:
      CLI -> LLM -> MCP -> LLM -> CLI
    using MCP stdio transport and a pluggable LLM provider.
    """
    def __init__(self, server_command: List[str]):
        self.server_command = server_command
        self.max_tool_steps = int(os.getenv("MAX_TOOL_STEPS", "5"))
        self.max_history_messages = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

        provider = (os.getenv("LLM_PROVIDER") or "mock").lower().strip()
        if provider == "azure_openai":
            if AzureOpenAILLM is None:
                raise RuntimeError("AzureOpenAI selected but openai SDK not installed. pip install openai")
            self.llm: LLMClient = AzureOpenAILLM.from_env()
        else:
            self.llm = MockLLM()

    def _trim_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Keep one merged system message plus a bounded number of recent non-system messages.
        """
        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system_messages = [m for m in messages if m.get("role") != "system"]
        return system_messages + non_system_messages[-self.max_history_messages:]

    async def run_cli(self):
        # 1) start MCP server as subprocess via stdio
        cmd = self.server_command[0]
        args = self.server_command[1:]

        server_params = StdioServerParameters(command=cmd, args=args, env=None)

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 2) discover tools from MCP server
                tool_resp = await session.list_tools()
                tools = tool_resp.tools

                console.print(Panel.fit(
                    f"[bold green]Connected to MCP server[/bold green]\nTools: {', '.join([t.name for t in tools])}",
                    title="MCP"
                ))

                # 3) chat loop
                merged_system_prompt = SYSTEM_PROMPT + "\n\nAvailable tools:\n" + tools_to_compact_text(tools)
                messages: List[Dict[str, Any]] = [
                    {"role": "system", "content": merged_system_prompt}
                ]

                while True:
                    user = console.input("\n[bold cyan]You>[/bold cyan] ").strip()
                    if user.lower() in ("exit", "quit"):
                        break

                    messages.append({"role": "user", "content": user})

                    try:
                        final_text = await self._run_agent_loop(session=session, messages=messages)
                    except Exception as exc:
                        logger.exception("Agent loop failed")
                        final_text = f"Sorry, something went wrong: {exc}"

                    console.print(f"\n[bold green]Assistant>[/bold green] {final_text}")
                    messages.append({"role": "assistant", "content": final_text})
                    messages = self._trim_history(messages)

    async def _run_agent_loop(self, session: ClientSession, messages: List[Dict[str, Any]]) -> str:
        """
        Tool loop:
          - ask LLM for JSON decision
          - if tool_call: call MCP tool, append tool result, continue
          - if final: return answer
        """
        for step in range(self.max_tool_steps):
            try:
                raw = await self.llm.complete(messages)
            except Exception as exc:
                raise RuntimeError(f"LLM call failed: {exc}") from exc

            try:
                decision_obj = safe_parse_llm_json(raw)
                decision = validate_decision(decision_obj)
            except Exception as exc:
                raise RuntimeError(f"LLM response was not valid decision JSON: {exc}") from exc

            if decision.type == "final":
                return decision.content or ""

            # tool call
            tool_name = decision.name or ""
            tool_args = decision.arguments or {}

            # call MCP tool
            try:
                tool_result = await session.call_tool(tool_name, tool_args)
            except Exception as exc:
                logger.exception("Tool call failed: %s", tool_name)
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps({"error": str(exc)}, ensure_ascii=False)
                })
                continue

            # attach tool result to messages for next LLM turn
            messages.append({
                "role": "tool",
                "name": tool_name,
                "content": json.dumps(tool_result.model_dump(), ensure_ascii=False)
            })

        return f"I tried calling tools up to {self.max_tool_steps} times but couldn't finish. Please refine your request."