# Chat-Ai

A reference implementation of an **MCP host application** that pairs a CLI front-end with a pluggable LLM backend and an MCP tool server. The agent follows a strict request/response loop:

```
CLI → LLM → (tool call?) → MCP Server → LLM → CLI
```

The LLM is asked to decide on every turn whether to call a tool or answer directly. It responds in a strict JSON schema (`tool_call` or `final`). The orchestrator interprets the decision, calls the MCP server when needed, and feeds the result back into the conversation until a final answer is produced.

Every message passing through the pipeline is protected by **[guardrails-ai](https://github.com/guardrails-ai/guardrails)** at three enforcement points — user input, tool-call arguments, and final output — using hub validators for length limits, prompt-injection detection, and toxic-language filtering.

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
│   - Applies guardrails at 3 points via agent/guardrails.py      │
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
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   agent/guardrails.py  (guardrails-ai)          │
│                                                                 │
│  ① check_input()      ← user turn enters context               │
│     - ValidLength     (max MAX_INPUT_LENGTH chars)              │
│     - DetectPromptInjection                                     │
│                                                                 │
│  ② check_tool_call()  ← before MCP tool is executed            │
│     - ALLOWED_TOOLS allowlist                                   │
│     - ValidLength per argument (max MAX_ARG_LENGTH chars)       │
│                                                                 │
│  ③ check_output()     ← before answer is returned to user      │
│     - ValidLength / auto-fix truncation (MAX_OUTPUT_LENGTH)     │
│     - ToxicLanguage   (optional)                                │
└─────────────────────────────────────────────────────────────────┘
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
│   ├── guardrails.py            # guardrails-ai Guard wrappers (input / tool / output)
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
| `MAX_HISTORY_MESSAGES` | `20` | Rolling window of non-system messages kept in context |
| `MAX_INPUT_LENGTH` | `2000` | Max characters accepted from the user (guardrails-ai) |
| `MAX_OUTPUT_LENGTH` | `8000` | Max characters in the assistant reply (guardrails-ai) |
| `MAX_ARG_LENGTH` | `1000` | Max characters per tool argument value (guardrails-ai) |
| `ALLOWED_TOOLS` | *(empty — all allowed)* | Comma-separated allowlist of permitted MCP tool names |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Guardrails (guardrails-ai)

The project uses the **[guardrails-ai](https://github.com/guardrails-ai/guardrails)** framework (`pip install guardrails-ai`) to enforce safety and quality policies at three points in every agent turn.

### Enforcement Points

| Point | Where | Validators used |
|---|---|---|
| **Input** | Before user message enters LLM context | `ValidLength`, `DetectPromptInjection` |
| **Tool call** | Before MCP tool is executed | `ALLOWED_TOOLS` allowlist, `ValidLength` per argument |
| **Output** | Before final answer is returned to user | `ValidLength` (auto-fix truncation), `ToxicLanguage` |

### Hub Validators

Install once with the guardrails CLI before running the agent:

```bash
guardrails hub install hub://guardrails/valid_length
guardrails hub install hub://guardrails/detect_prompt_injection
guardrails hub install hub://guardrails/toxic_language   # optional
```

> **Graceful degradation** — if a hub validator is not installed, `agent/guardrails.py` logs a warning and falls back to simple built-in checks so the agent continues to work.

### Violation Behaviour

| Violation | Result |
|---|---|
| Input too long or injection detected | Turn blocked; user sees a `Blocked:` message |
| Tool not on `ALLOWED_TOOLS` list | Tool call skipped; LLM receives an error payload and may retry |
| Tool argument too long | Same as above |
| Output too long | Auto-truncated with a `[... response truncated]` notice |
| Toxic output | Turn raises `GuardrailViolation`, user sees friendly error |

---

## Security Audit (March 2026)

This project was reviewed with a production mindset for shipping to multiple users. Findings below are ranked by severity and mapped to practical remediation.

### Findings Summary

| Severity | Finding | Impact | Affected Component |
|---|---|---|---|
| High | Tool output is re-injected into LLM without dedicated sanitization | Indirect prompt injection from external systems (e.g., ADO fields/comments) can influence model behavior | `agent/orchestrator.py` |
| High | Raw exception details are surfaced to users/model in some paths | Internal implementation details may leak and assist adversarial probing | `agent/orchestrator.py` |
| Medium-High | Guardrails may silently degrade when hub validators are missing | Security posture weakens at runtime without hard startup failure | `agent/guardrails.py` |
| Medium | Arbitrary WIQL execution in ADO tool | Broad data exfiltration/query abuse risk | `mcp_server/ado_tools_server.py` |
| Medium | Tool allowlist defaults to permissive behavior when unset | Newly added sensitive tools can become callable unintentionally | `agent/guardrails.py` |
| Low-Medium | Data minimization gap (`$expand=all`, rich fields) | Unnecessary sensitive data flows into prompt context | `mcp_server/ado_tools_server.py` |

### Production Hardening Actions

1. Add `check_tool_result()` guardrail before appending MCP output to conversation history.
2. Replace user-facing raw exception text with generic safe error messages; keep details in internal logs only.
3. Add strict mode (`SECURITY_MODE=prod`) that fails startup if required guardrail validators are unavailable.
4. Require explicit `ALLOWED_TOOLS` in production mode and fail startup if empty.
5. Restrict WIQL input with server-side policy checks (query templates/allowlist constraints).
6. Reduce ADO response surface (avoid `$expand=all`; return only required fields).
7. Add structured audit logs for guardrail blocks, tool calls, and policy denials.

### Release Gate (Recommended)

Before shipping to users, require all checks below to pass:

- Guardrails strict mode enabled and validated in startup checks.
- Tool-output sanitization path covered by automated tests.
- No raw exception text returned to end users.
- ADO tool queries constrained and regression-tested for abuse cases.
- Per-turn logging does not include PATs/secrets/PII.

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
| `__init__(server_command)` | Selects LLM provider from env; instantiates `Guardrails`; stores MCP server command |
| `run_cli()` | Spawns MCP subprocess, discovers tools, starts interactive loop; applies input + output guardrails |
| `_run_agent_loop(session, messages)` | Iterates LLM ↔ tool calls until `type=final` or step limit; applies tool-call guardrail |

### `agent/guardrails.py` — `Guardrails`

Wrapper around the **guardrails-ai** `Guard` API. Builds one `Guard` per enforcement point at init time from installed hub validators.

| Method | Validators | Behaviour on failure |
|---|---|---|
| `check_input(text)` | `ValidLength`, `DetectPromptInjection` | Raises `GuardrailViolation` |
| `check_tool_call(name, arguments)` | Allowlist + `ValidLength` per arg | Raises `GuardrailViolation` |
| `check_output(text)` | `ValidLength` (fix), `ToxicLanguage` | Truncates or raises `GuardrailViolation` |

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
| `guardrails-ai` | Input / tool-call / output safety guardrails framework |
| `openai` *(optional)* | Azure OpenAI provider |

---

## License

MIT
