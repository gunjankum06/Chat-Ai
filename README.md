# cli-llm-mcp-agent

Project scaffold for a CLI LLM + MCP agent.
# CLI → LLM → MCP → LLM → CLI (Proof-of-Flow)

This project implements a CLI chat agent that:
1) Accepts user input in a terminal (CLI)
2) Sends it to an LLM
3) LLM decides whether to call a tool
4) CLI calls the MCP tool server over MCP (stdio)
5) Sends tool result back to LLM
6) LLM returns final answer to CLI

This is a reference implementation of an MCP host app (App+LLM) using MCP tools
via `list_tools()` and `call_tool()`.

## Quick start

### 1) Setup venv
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate