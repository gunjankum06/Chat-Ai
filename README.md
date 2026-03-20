# Chat-Ai

A reference implementation of an **MCP host application** that pairs a CLI front-end with a pluggable LLM backend and an MCP tool server. The agent follows a strict request/response loop:

```
CLI → LLM → (tool call?) → MCP Server → LLM → CLI
```

The LLM is asked to decide on every turn whether to call a tool or answer directly. It responds in a strict JSON schema (`tool_call` or `final`). The orchestrator interprets the decision, calls the MCP server when needed, and feeds the result back into the conversation until a final answer is produced.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          main.py                                │
│   - Parses --server CLI argument                                │
│   - Loads .env                                                  │
│   - Instantiates AgentOrchestrator and starts the chat loop     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   agent/orchestrator.py                         │
│   - Spawns the MCP server subprocess via stdio                  │
│   - Discovers available tools via list_tools()                  │
│   - Runs the interactive CLI loop                               │
│   - Runs the inner agent loop (LLM ↔ MCP until "final")         │
└──────────┬──────────────────────────────────────┬───────────────┘
           │                                      │
           ▼                                      ▼
┌─────────────────────┐              ┌────────────────────────────┐
│   llm/              │              │   mcp_server/              │
│   base.py           │              │   mock_tools_server.py     │
│   mock_llm.py       │              │                            │
│   azure_openai_llm  │              │   Tools exposed:           │
│                     │              │   - greet(name)            │
│   LLMClient ABC     │              │   - get_defect_details(id) │
└─────────────────────┘              └────────────────────────────┘
```

---

## Project Structure

```
Chat-Ai/
├── main.py                      # Entry point
├── requirements.txt             # Runtime dependencies
├── .env.example                 # Template for environment variables
├── .gitignore
├── agent/
│   ├── orchestrator.py          # Core agent loop (CLI ↔ LLM ↔ MCP)
│   ├── prompts.py               # System prompt + tool-text formatter
│   ├── protocol.py              # Pydantic models: ToolCall, FinalAnswer, LLMDecision
│   └── util.py                  # JSON parsing + LLMDecision validation helpers
├── llm/
│   ├── base.py                  # Abstract LLMClient base class
│   ├── mock_llm.py              # Deterministic mock (no API key required)
│   └── azure_openai_llm.py      # Azure OpenAI provider (optional)
└── mcp_server/
    ├── mock_tools_server.py     # FastMCP server exposing demo tools
    └── README.md
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 + |
| pip | latest |
| Azure OpenAI resource | only if `LLM_PROVIDER=azure_openai` |

---

## Quick Start

### 1. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# then edit .env with your settings
```

### 4. Run the agent (with mock LLM — no API key needed)

```bash
python main.py --server python mcp_server/mock_tools_server.py
```

---

## Running Examples

```
You> greet Gunjan
Assistant> Hello Gunjan! This result came from an MCP tool.

You> get defect 1234 details
Assistant> {"defectId": "1234", "title": "Demo defect title", ...}

You> what is 2 + 2?
Assistant> I can greet you or fetch mock defect details. Try: 'greet Gunjan' or 'get defect 1234 details'.

You> exit
```

---

## Configuration

All configuration is via `.env` (or real environment variables). Copy `.env.example` to `.env` and edit:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `mock` | LLM backend to use. Allowed: `mock`, `azure_openai` |
| `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI resource endpoint URL |
| `AZURE_OPENAI_API_KEY` | — | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` | API version string |
| `AZURE_OPENAI_DEPLOYMENT` | — | Deployment/model name (e.g. `gpt-4.1-mini`) |
| `MAX_TOOL_STEPS` | `5` | Max tool-call iterations per user turn (safety guard) |

---

## LLM Providers

### MockLLM (`LLM_PROVIDER=mock`)

Deterministic, no network calls, no API key. Useful for local development and CI.

Recognized patterns:
- `greet <name>` → calls the `greet` MCP tool
- `defect <id>` → calls the `get_defect_details` MCP tool
- anything else → returns a help message as `final`

### AzureOpenAILLM (`LLM_PROVIDER=azure_openai`)

Requires `pip install openai` and valid Azure OpenAI credentials in `.env`.  
The LLM is instructed via `SYSTEM_PROMPT` to respond only in the strict JSON schema:

```json
// Tool call
{"type": "tool_call", "name": "<tool_name>", "arguments": {...}}

// Final answer
{"type": "final", "content": "<answer>"}
```

---

## Module Reference

### `agent/orchestrator.py` — `AgentOrchestrator`

| Method | Description |
|---|---|
| `__init__(server_command)` | Selects LLM provider from env; stores MCP server command |
| `run_cli()` | Spawns MCP subprocess, discovers tools, starts interactive loop |
| `_run_agent_loop(session, messages)` | Iterates LLM ↔ tool calls until `type=final` or step limit |

### `agent/protocol.py`

Pydantic models that enforce the LLM output contract:

- `ToolCall` — `type="tool_call"`, `name`, `arguments`
- `FinalAnswer` — `type="final"`, `content`
- `LLMDecision` — union validator used by `validate_decision()`

### `agent/prompts.py`

- `SYSTEM_PROMPT` — instructs the LLM to respond only in JSON
- `tools_to_compact_text(tools)` — formats MCP tool schemas into plain text for the LLM context

### `agent/util.py`

- `safe_parse_llm_json(text)` — strips whitespace and parses JSON
- `validate_decision(obj)` — validates parsed JSON against `LLMDecision`

### `llm/base.py` — `LLMClient` (ABC)

Abstract base class. All providers must implement:

```python
async def complete(self, messages: List[Dict[str, Any]]) -> str: ...
```

### `mcp_server/mock_tools_server.py`

A [FastMCP](https://github.com/jlowin/fastmcp) stdio server with two demo tools:

| Tool | Arguments | Returns |
|---|---|---|
| `greet` | `name: str` | Greeting string |
| `get_defect_details` | `defectId: str` | Dict with mock defect data |

---

## Extending the Project

**Add a new MCP tool:** Edit `mcp_server/mock_tools_server.py` and add a `@mcp.tool()` decorated function. No changes needed elsewhere — `list_tools()` discovers it automatically.

**Add a new LLM provider:** Create a class in `llm/` that extends `LLMClient` and implement `complete()`. Then add a branch for it in `AgentOrchestrator.__init__()` keyed to a new `LLM_PROVIDER` value.

**Point to a different MCP server:** Change the `--server` argument. Any MCP-compliant stdio server works.

---

## Dependencies

| Package | Purpose |
|---|---|
| `mcp` | MCP client + FastMCP server SDK |
| `python-dotenv` | Load `.env` file into environment |
| `rich` | Terminal formatting (panels, colored prompts) |
| `pydantic` | Runtime data validation for LLM output |
| `openai` *(optional)* | Azure OpenAI provider |

---

## License

MIT
