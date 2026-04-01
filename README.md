# Chat-Ai

A reference implementation of an **MCP host application** that pairs a CLI front-end with a pluggable LLM backend and an MCP tool server. The agent follows a strict request/response loop:

```
CLI → LLM → (tool call?) → MCP Server → LLM → CLI
```

The LLM is asked to decide on every turn whether to call a tool or answer directly. It responds in a strict JSON schema (`tool_call` or `final`). The orchestrator interprets the decision, calls the MCP server when needed, and feeds the result back into the conversation until a final answer is produced.

Every message passing through the pipeline is protected by **[guardrails-ai](https://github.com/guardrails-ai/guardrails)** at **four** enforcement points — user input, tool-call arguments, tool results, and final output — using hub validators for length limits, prompt-injection detection, and toxic-language filtering.

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
│  ③ check_tool_result() ← before tool output re-enters context  │
│     - Truncation, secret redaction, injection detection         │
│                                                                 │
│  ④ check_output()     ← before answer is returned to user      │
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
│   ├── tracing.py               # LangSmith @traceable decorator (no-op when off)
│   ├── prompts.py               # System prompt + tool-text formatter
│   ├── protocol.py              # Pydantic models: LLMDecision schema
│   └── util.py                  # JSON parsing + LLMDecision validation helpers
├── llm/
│   ├── base.py                  # Abstract LLMClient base class
│   ├── factory.py               # Provider registry and create_llm() factory
│   ├── mock_llm.py              # Deterministic mock (no API key required)
│   ├── azure_openai_llm.py      # Azure OpenAI provider
│   ├── openai_llm.py            # Standard OpenAI provider
│   ├── anthropic_llm.py         # Anthropic Claude provider
│   └── ollama_llm.py            # Ollama local model provider
└── mcp_server/
    ├── mock_tools_server.py     # FastMCP server: greet, get_defect_details
    ├── ado_tools_server.py      # FastMCP Azure DevOps server
    └── README.md
```

---

## Prerequisites

| Requirement | Version / Notes |
|---|---|
| Python | 3.10 + |
| pip | latest |
| Azure OpenAI resource | only if `LLM_PROVIDER=azure_openai` |
| OpenAI API key | only if `LLM_PROVIDER=openai` |
| Anthropic API key | only if `LLM_PROVIDER=anthropic` (`pip install anthropic`) |
| [Ollama](https://ollama.com) | only if `LLM_PROVIDER=ollama` (local, no API key needed) |

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

### Core

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `mock` | LLM backend: `mock`, `azure_openai`, `openai`, `anthropic`, `ollama` |
| `MAX_TOOL_STEPS` | `5` | Max tool-call iterations per user turn (safety guard) |
| `MAX_HISTORY_MESSAGES` | `20` | Rolling window of non-system messages kept in context |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Guardrails

| Variable | Default | Description |
|---|---|---|
| `MAX_INPUT_LENGTH` | `2000` | Max characters accepted from the user |
| `MAX_OUTPUT_LENGTH` | `8000` | Max characters in the assistant reply |
| `MAX_ARG_LENGTH` | `1000` | Max characters per tool argument value |
| `MAX_TOOL_RESULT_LENGTH` | `6000` | Max characters from MCP tool output re-injected into LLM context |
| `SECURITY_MODE` | `dev` | `dev` (best effort) or `prod`/`strict` (fail-closed startup checks) |
| `ALLOWED_TOOLS` | *(empty — all allowed)* | Comma-separated allowlist of permitted MCP tool names |

### Azure OpenAI (`LLM_PROVIDER=azure_openai`)

| Variable | Default | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI resource endpoint URL |
| `AZURE_OPENAI_API_KEY` | — | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` | API version string |
| `AZURE_OPENAI_DEPLOYMENT` | — | Deployment/model name (e.g. `gpt-4o`) |

### OpenAI (`LLM_PROVIDER=openai`)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | API key from [platform.openai.com](https://platform.openai.com) |
| `OPENAI_MODEL` | `gpt-4o` | Model name |

### Anthropic (`LLM_PROVIDER=anthropic`)

Requires `pip install anthropic`.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | API key from [console.anthropic.com](https://console.anthropic.com) |
| `ANTHROPIC_MODEL` | `claude-opus-4-5` | Model ID |

### Ollama — local models (`LLM_PROVIDER=ollama`)

Install [Ollama](https://ollama.com), pull a model (`ollama pull llama3`), then:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Local model name |

### Azure DevOps MCP Server

| Variable | Default | Description |
|---|---|---|
| `ADO_ORG` | — | Azure DevOps organisation slug |
| `ADO_PROJECT` | — | Project name |
| `ADO_PAT` | — | Personal Access Token (Work Items read scope) |
| `ADO_MAX_WIQL_LENGTH` | `1000` | Max WIQL query length accepted by ADO MCP server |
| `ADO_MAX_RESULTS` | `100` | Max work items returned from WIQL batch query (capped at 200) |
| `ADO_MAX_COMMENTS` | `50` | Max comments returned by `get_work_item_comments` |
| `ADO_MAX_COMMENT_LENGTH` | `2000` | Max length per returned comment text |
| `ADO_INCLUDE_DESCRIPTION` | `false` | Include work-item description field when true |

---

## Guardrails (guardrails-ai)

The project uses the **[guardrails-ai](https://github.com/guardrails-ai/guardrails)** framework (`pip install guardrails-ai`) to enforce safety and quality policies at four points in every agent turn.

### Enforcement Points

| Point | Where | Validators used |
|---|---|---|
| **Input** | Before user message enters LLM context | `ValidLength`, `DetectPromptInjection` |
| **Tool call** | Before MCP tool is executed | `ALLOWED_TOOLS` allowlist, `ValidLength` per argument |
| **Tool result** | Before tool output is appended back into model context | Truncation, secret redaction, indirect-injection detection |
| **Output** | Before final answer is returned to user | `ValidLength` (auto-fix truncation), `ToxicLanguage` |

### Hub Validators

Install once with the guardrails CLI before running the agent:

```bash
guardrails hub install hub://guardrails/valid_length
guardrails hub install hub://guardrails/detect_prompt_injection
guardrails hub install hub://guardrails/toxic_language   # optional
```

> **Strict production mode** — set `SECURITY_MODE=prod` to fail startup if required validators are missing and to require an explicit `ALLOWED_TOOLS` list.

### Violation Behaviour

| Violation | Result |
|---|---|
| Input too long or injection detected | Turn blocked; user sees a `Blocked:` message |
| Tool not on `ALLOWED_TOOLS` list | Tool call skipped; LLM receives an error payload and may retry |
| Tool argument too long | Same as above |
| Tool result contains secrets | Secret-like tokens are redacted before re-injection |
| Tool result appears injection-like | In `dev`: redacted; in `prod`: blocked |
| Output too long | Auto-truncated with a `[... response truncated]` notice |
| Toxic output | Turn raises `GuardrailViolation`, user sees friendly error |

---

## LangSmith Observability (Optional)

[LangSmith](https://smith.langchain.com) provides full-stack tracing for every agent turn — LLM calls, tool calls, latencies, inputs/outputs — with zero code changes beyond env vars. It does **not** require LangChain; the standalone `langsmith` SDK works with this project’s custom orchestrator directly.

### Setup

```bash
pip install langsmith
```

### Configuration

```bash
# .env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=Chat-Ai                        # optional (default: Chat-Ai)
# LANGSMITH_ENDPOINT=https://api.smith.langchain.com  # optional (override for self-hosted)
# LANGSMITH_REDACT=true                               # optional (default: true — redacts PII/secrets from traces)
```

### What gets traced

Every user turn produces a nested trace tree:

```
agent_turn  (chain)                          ← one per user message
 └── agent_loop  (chain)                      ← tool-calling loop
      ├── <provider>_complete  (llm)           ← 1st LLM API call
      ├── [tool execution]                    ← MCP tool call
      ├── <provider>_complete  (llm)           ← 2nd LLM call (with tool result)
      └── ...                                  ← repeats until "final"
```

| Span | Type | Description |
|---|---|---|
| `agent_turn` | chain | One span per user interaction (top-level) |
| `agent_loop` | chain | Inner tool-calling loop |
| `azure_openai_complete` | llm | Azure OpenAI API call |
| `openai_complete` | llm | Standard OpenAI API call |
| `anthropic_complete` | llm | Anthropic Claude API call |
| `ollama_complete` | llm | Ollama local model API call |

### How it works

The `agent/tracing.py` module provides a `@traceable` decorator that:
1. Checks `LANGSMITH_TRACING` env var at import time.
2. If `true`, imports `langsmith.traceable` and delegates to it.
3. If `false` or SDK is missing, returns the original function unchanged — **zero overhead**.
4. When `LANGSMITH_REDACT=true` (the default), a `process_inputs` callback scrubs all traced inputs before they leave the process.

Provider code never imports `langsmith` directly. All instrumentation goes through `tracing.py`, making it trivial to swap to a different tracing backend in the future.

### Data protection

By default, traced inputs are **automatically redacted** before being sent to LangSmith. The original runtime objects are never mutated.

| What is redacted | Example match | Replacement |
|---|---|---|
| System prompt | `role=system` messages | `[system prompt redacted]` |
| API keys & secrets | `sk-abc123...`, `Bearer eyJ...`, `pat=...` | `[redacted-secret]` |
| Email addresses | `user@example.com` | `[redacted-email]` |
| Phone numbers | `+1 (555) 123-4567` | `[redacted-phone]` |
| SSNs | `123-45-6789` | `[redacted-ssn]` |

Redaction runs **after** guardrails (`check_input`, `check_tool_result`) and **before** the LangSmith API call, giving two independent layers of protection:

```
guardrails.check_input()  →  guardrails.check_tool_result()  →  tracing._process_inputs()  →  LangSmith API
```

To disable redaction on a trusted self-hosted instance (e.g. for raw evaluation data):
```bash
LANGSMITH_REDACT=false
```

### Evaluation workflow

LangSmith traces enable a structured evaluation loop:

1. **Collect** — run the agent with tracing on; turns are logged automatically.
2. **Curate** — select interesting turns in the LangSmith UI and add them to a dataset.
3. **Evaluate** — write evaluator functions ("did the agent call the right tool?") and score the dataset.
4. **Compare** — after changing a prompt or model, re-evaluate the same dataset and diff scores.

### Self-hosted / air-gapped deployments

Set `LANGSMITH_ENDPOINT` to your internal LangSmith URL. All other env vars work the same. This keeps trace data within your network boundary. Consider setting `LANGSMITH_REDACT=false` on a fully trusted self-hosted instance if you need unredacted data for evaluation.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No traces appear | `LANGSMITH_TRACING` is not `true` | Set `LANGSMITH_TRACING=true` in `.env` |
| `langsmith SDK is not installed` warning | SDK missing from venv | `pip install langsmith` |
| Traces appear but are empty | Functions not decorated | Verify `@traceable` on `_handle_turn`, `_run_agent_loop`, `complete()` |
| Authentication error | Invalid API key | Verify `LANGSMITH_API_KEY` at smith.langchain.com → Settings |
| Wrong project | `LANGSMITH_PROJECT` mismatch | Set the correct project name in `.env` |
| Traces show `[redacted-*]` placeholders | `LANGSMITH_REDACT=true` (default) | Expected behaviour; set `LANGSMITH_REDACT=false` only on trusted self-hosted instances |
| Secrets visible in traces | `LANGSMITH_REDACT=false` | Set `LANGSMITH_REDACT=true` (or remove the var — defaults to true) |

---

## Security Audit (March 2026)

This project was reviewed with a production mindset for shipping to multiple users. Findings were ranked by severity and the critical controls below have been implemented.

### Implemented Hardening Controls

1. Added tool-result sanitization guard (`check_tool_result`) before output is re-injected into LLM context.
2. Added strict fail-closed production mode (`SECURITY_MODE=prod`) for validator and tool allowlist enforcement.
3. Replaced raw user-facing exception details with generic safe errors.
4. Added ADO WIQL policy validation and query-size/result-size limits.
5. Reduced default ADO data exposure by removing broad expansion and making description opt-in.

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

### `mock` (default)

Deterministic, no network calls, no API key. Ideal for local development and CI.

```bash
python main.py --server python mcp_server/mock_tools_server.py
```

Recognised patterns:
- `greet <name>` → calls the `greet` MCP tool
- `defect <id>` or `get defect <id>` → calls `get_defect_details`
- anything else → returns a help message as `final`

### `azure_openai`

Azure-hosted OpenAI models via the Azure OpenAI Service.

```bash
# .env
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

### `openai`

Standard OpenAI API (api.openai.com).

```bash
# .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o      # optional, default: gpt-4o
```

### `anthropic`

Anthropic Claude models. Requires `pip install anthropic`.

```bash
# .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-5   # optional
```

### `ollama` (local / air-gapped)

Any local model served by [Ollama](https://ollama.com) via its OpenAI-compatible endpoint. No API key or internet required after initial model download.

```bash
# 1. Install Ollama and pull a model
ollama pull llama3

# 2. .env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3             # optional, default: llama3
# OLLAMA_BASE_URL defaults to http://localhost:11434/v1
```

All providers speak the same `LLMClient.complete()` interface defined in `llm/base.py`. The LLM is instructed via `SYSTEM_PROMPT` to respond only in the strict JSON schema:

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
| `__init__(server_command)` | Calls `create_llm(LLM_PROVIDER)` from `llm/factory.py`; instantiates `Guardrails`; stores MCP server command |
| `run_cli()` | Spawns MCP subprocess, discovers tools, starts interactive loop; applies input + output guardrails |
| `_handle_turn(session, messages, user_input)` | Traced wrapper (`agent_turn` span) around the agent loop for one user turn |
| `_run_agent_loop(session, messages)` | Traced inner loop (`agent_loop` span); iterates LLM ↔ tool calls until `type=final` or step limit |

### `agent/guardrails.py` — `Guardrails`

Wrapper around the **guardrails-ai** `Guard` API. Builds one `Guard` per enforcement point at init time from installed hub validators.

| Method | Validators | Behaviour on failure |
|---|---|---|
| `check_input(text)` | `ValidLength`, `DetectPromptInjection` | Raises `GuardrailViolation` |
| `check_tool_call(name, arguments)` | Allowlist + `ValidLength` per arg | Raises `GuardrailViolation` |
| `check_tool_result(text)` | Truncation, redaction, injection detection | Returns sanitized text or raises `GuardrailViolation` |
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

### `agent/tracing.py` — LangSmith observability

Provides a `@traceable` decorator that wraps functions with LangSmith tracing when `LANGSMITH_TRACING=true` and the `langsmith` SDK is installed. Falls back to a transparent no-op otherwise (zero overhead).

| Function / attribute | Purpose |
|---|---|
| `traceable(run_type, name, metadata, tags)` | Decorator: delegates to `langsmith.traceable` when active, no-op when off |
| `is_tracing_enabled()` | Returns `True` when LangSmith tracing is active |

Applied to: `_handle_turn` (chain), `_run_agent_loop` (chain), and each provider’s `complete()` (llm). `MockLLM` is intentionally not traced.

### `llm/base.py` — `LLMClient` (ABC)

Abstract base class. All providers must implement:

```python
async def complete(self, messages: List[Dict[str, Any]]) -> str: ...
```

### `llm/factory.py` — provider registry

Maps `LLM_PROVIDER` names to provider instances. Optional providers are registered only if their SDK is importable.

| `LLM_PROVIDER` value | Provider class | SDK required |
|---|---|---|
| `mock` | `MockLLM` | none |
| `azure_openai` | `AzureOpenAILLM` | `openai` |
| `openai` | `OpenAILLM` | `openai` |
| `anthropic` | `AnthropicLLM` | `anthropic` |
| `ollama` | `OllamaLLM` | `openai` |

### `mcp_server/mock_tools_server.py`

A [FastMCP](https://github.com/jlowin/fastmcp) stdio server with two demo tools:

| Tool | Arguments | Returns |
|---|---|---|
| `greet` | `name: str` | Greeting string |
| `get_defect_details` | `defectId: str` | Dict with mock defect data |

---

## Extending the Project

**Add a new MCP tool:** Edit `mcp_server/mock_tools_server.py` and add a `@mcp.tool()` decorated function. No changes needed elsewhere — `list_tools()` discovers it automatically.

**Add a new LLM provider:**
1. Create `llm/my_provider_llm.py` implementing `LLMClient` (one method: `async complete(messages) -> str`).
2. Add a `from_env()` static method that reads credentials from env vars.
3. In `llm/factory.py`, add inside a `try/except ImportError` block:
   ```python
   from llm.my_provider_llm import MyProviderLLM
   _register("my_provider", MyProviderLLM.from_env)
   ```
4. Set `LLM_PROVIDER=my_provider` in `.env`.

**Point to a different MCP server:** Change the `--server` argument. Any MCP-compliant stdio server works.

---

## Dependencies

| Package | Purpose |
|---|---|
| `mcp` | MCP client + FastMCP server SDK |
| `python-dotenv` | Load `.env` file into environment |
| `rich` | Terminal formatting (panels, coloured prompts) |
| `pydantic` | Runtime data validation for LLM output |
| `guardrails-ai` | Input / tool-call / output safety guardrails framework |
| `openai` | Required for: `azure_openai`, `openai`, `ollama` providers |
| `anthropic` *(optional)* | Required for: `anthropic` provider (`pip install anthropic`) |
| `langsmith` *(optional)* | Required for: LangSmith tracing (`pip install langsmith`) |

---

## Known Issues

| Issue | Severity | Description | Workaround |
|---|---|---|---|
| Hub validators not bundled | Low | `ValidLength` and `DetectPromptInjection` show "not installed" warnings at startup | Run `guardrails hub install hub://guardrails/valid_length` and `guardrails hub install hub://guardrails/detect_prompt_injection` |
| Venv must be activated | Low | `ModuleNotFoundError` for `guardrails` or other packages when the virtual environment is not active | Always activate the venv before running: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (macOS/Linux) |
| Pip shebang breaks on Windows after folder rename | Low | Bare `pip` fails if the project directory was renamed after venv creation | Use `python -m pip install` instead of `pip install` |
| Interactive terminal required | Info | The agent reads from stdin; piping output through filters causes `EOFError` | Run the agent directly in a terminal without output redirection |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ValidLength not installed` warning | Hub validators missing | `guardrails hub install hub://guardrails/valid_length` |
| `DetectPromptInjection not installed` warning | Hub validators missing | `guardrails hub install hub://guardrails/detect_prompt_injection` |
| `ModuleNotFoundError: No module named 'guardrails'` | Venv not activated | Activate: `.venv\Scripts\activate` (Win) / `source .venv/bin/activate` (macOS/Linux) |
| `pip` fails with path error | Pip shebang stale after folder rename | `python -m pip install -r requirements.txt` |
| `EOFError` at `You>` prompt | stdin closed (piped output) | Run the agent in an interactive terminal |
| `SECURITY_MODE is strict but required guardrails validators are missing` | `SECURITY_MODE=prod` without hub validators | Install validators or set `SECURITY_MODE=dev` |
| No `You>` prompt after MCP connection | MCP server process crashed | Verify `--server` command and check MCP server script for errors |

---

## License

MIT
