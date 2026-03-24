# Chat-Ai High Level Design

## 1. Document Purpose

This High Level Design describes the architecture, runtime behavior, interfaces, and operational model of the Chat-Ai project.

The document is intended for:
- Developers extending the orchestrator, LLM providers, or MCP tools.
- Architects reviewing scalability, reliability, and security posture.
- Operators deploying the solution in local, enterprise, or CI environments.

## 2. System Vision

Chat-Ai is a CLI-first, tool-augmented AI assistant host that coordinates:
- User interaction in a terminal.
- Model reasoning through a pluggable LLM abstraction.
- External capability execution through MCP tool servers.

Core architecture pattern:

CLI -> Orchestrator -> LLM Decision -> MCP Tool Execution -> LLM Synthesis -> CLI Response

This pattern enables deterministic tool invocation control while preserving natural language conversation.

## 3. Scope and Non-Goals

### In Scope
- Interactive CLI chat loop.
- Tool-augmented reasoning with iterative LLM/tool loop.
- MCP stdio server integration.
- Multiple LLM providers via provider abstraction.
- Azure DevOps integration through an MCP server.

### Out of Scope
- Web UI.
- Multi-user session management.
- Persistent conversation storage.
- Distributed orchestration across machines.
- Fine-grained RBAC model inside the host process.

## 4. Architectural Drivers

### Functional Drivers
- Accept natural language user requests.
- Decide whether a request needs tool execution.
- Call one or more tools and return curated output.
- Support both mock and production-grade integrations.

### Non-Functional Drivers
- Simplicity for developer onboarding.
- Deterministic behavior boundaries.
- Resilience against malformed model outputs.
- Configuration via environment variables.
- Extensibility for additional MCP tools and LLM backends.

## 5. Context View

External actors and systems:
- User: enters prompts in CLI, receives final response.
- Azure OpenAI: optional LLM provider for production reasoning.
- Azure DevOps REST APIs: source of work item and comment data.
- MCP Server Process: child process exposing tools over stdio.

System boundary:
- The Chat-Ai host process contains CLI, orchestrator, prompting, protocol validation, and provider selection logic.
- MCP tool servers are separate processes spawned by the host.

## 6. Logical Architecture

Primary modules:

1. Entry Point
- File: main.py
- Responsibilities:
  - Parse command line arguments.
  - Load environment variables.
  - Configure logging.
  - Instantiate AgentOrchestrator.

2. Orchestration Layer
- File: agent/orchestrator.py
- Responsibilities:
  - Spawn MCP server subprocess with stdio transport.
  - Discover tools from MCP server.
  - Manage chat message history.
  - Execute tool loop with max-step safety limit.
  - Convert MCP tool result blocks to plain text for LLM consumption.

3. Prompt and Protocol Layer
- Files: agent/prompts.py, agent/protocol.py, agent/util.py
- Responsibilities:
  - Define strict JSON output contract for LLM.
  - Format available tools into prompt context.
  - Parse and validate LLM responses.

4. LLM Provider Layer
- Files: llm/base.py, llm/mock_llm.py, llm/azure_openai_llm.py
- Responsibilities:
  - Abstract completion contract via LLMClient.
  - Provide mock deterministic behavior for local testing.
  - Provide Azure OpenAI async implementation for real usage.

5. Tool Server Layer (MCP)
- Files: mcp_server/mock_tools_server.py, mcp_server/ado_tools_server.py
- Responsibilities:
  - Expose callable tools with typed inputs.
  - Bridge external systems (Azure DevOps) into MCP tool calls.

## 7. Runtime Interaction Flows

### 7.1 Startup Flow
1. User runs main.py with --server command.
2. main.py loads .env and configures logging.
3. AgentOrchestrator selects LLM provider based on LLM_PROVIDER.
4. Orchestrator starts MCP server subprocess over stdio.
5. Orchestrator initializes MCP session and fetches tool catalog.
6. Orchestrator merges system prompt and tool catalog into one system message.

### 7.2 Single-Turn Tool-Assisted Flow
1. User enters request in CLI.
2. Request appended as role=user message.
3. Orchestrator asks LLM for JSON decision.
4. LLM returns either:
   - type=final with content, or
   - type=tool_call with name + arguments.
5. If tool_call, orchestrator invokes MCP session call_tool.
6. Tool result content blocks are extracted to plain text and appended as role=tool.
7. Loop repeats until LLM returns type=final or max_tool_steps reached.
8. Final answer printed in CLI and added to conversation history.

### 7.3 Error Flow
- LLM invocation errors raise runtime failure for current turn.
- Invalid JSON or schema mismatch raises runtime failure for current turn.
- Tool call failure is transformed into role=tool error payload and loop continues.
- User receives friendly fallback message when turn-level failure occurs.

## 8. Data and Message Contracts

### 8.1 Internal Chat Message Shape
Each message is represented as a dict with key fields:
- role: system, user, assistant, or tool
- content: prompt text, tool result text, or final answer
- name: used for role=tool to identify called tool

### 8.2 LLM Decision Contract
Validated by pydantic model LLMDecision:
- type: tool_call or final
- name: optional tool name
- arguments: optional tool arguments object
- content: optional final answer text

Design principle:
- Orchestrator accepts only strict JSON from LLM and validates every turn.

### 8.3 MCP Tool Result Handling
- MCP call_tool returns structured result blocks.
- Orchestrator extracts text fragments from content blocks.
- If text blocks are absent, full JSON result is serialized and passed through.

## 9. Deployment View

### 9.1 Process Model
- Parent process: Chat-Ai host (CLI + orchestrator + LLM client).
- Child process: MCP tool server chosen at runtime by --server argument.

### 9.2 Configuration Model
Environment variables:
- LLM_PROVIDER: mock or azure_openai
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_API_KEY
- AZURE_OPENAI_API_VERSION
- AZURE_OPENAI_DEPLOYMENT
- MAX_TOOL_STEPS
- MAX_HISTORY_MESSAGES
- LOG_LEVEL
- ADO_ORG
- ADO_PROJECT
- ADO_PAT

### 9.3 Typical Deployment Modes
- Local development: mock LLM + mock MCP server.
- Enterprise integration: Azure OpenAI + ADO MCP server.
- CI validation: mock LLM + unit tests.

## 10. Security Design

### 10.1 Credential Handling
- Secrets are loaded from environment variables, not hard-coded.
- .env should be excluded from source control.

### 10.2 ADO Authentication
- ADO tool server uses PAT in Basic auth header.
- PAT should be least privilege and scoped to required APIs.

### 10.3 Data Exposure Controls
- MCP stdio channel is process-local.
- Tool results may include sensitive project metadata and should be logged carefully.
- Avoid printing secrets or raw auth headers.

### 10.4 Recommended Hardening
- Mask PII and secrets in logs.
- Add outbound host allowlist for ADO endpoints.
- Add rate limits and retry budgets around ADO calls.
- Add PAT rotation policy and secret-store integration.

## 11. Reliability and Resilience

### Existing Reliability Mechanisms
- Bounded tool loop via MAX_TOOL_STEPS.
- Bounded conversation history via MAX_HISTORY_MESSAGES.
- Per-turn exception handling in orchestrator.
- Tool call failure converted into model-visible error payload.

### Recommended Enhancements
- Retry with backoff for transient HTTP 429/5xx from ADO.
- Timeout and circuit-breaker policy for external dependencies.
- Graceful fallback if MCP subprocess crashes.
- Health checks for MCP server startup and readiness.

## 12. Scalability Considerations

Current architecture is single-user, single-session, single-process interactive CLI.

Scales well for:
- Individual developer workflows.
- Low-throughput operational use.

Not yet optimized for:
- High request concurrency.
- Multi-tenant workloads.
- Long-running session persistence across restarts.

Evolution path:
- Introduce API service wrapper around orchestrator.
- Externalize state and session persistence.
- Run MCP servers as managed services instead of local subprocesses.

## 13. Observability and Operations

### Current Observability
- Python logging configured in main.py.
- Orchestrator logs failures and exceptions.
- ADO server logs startup metadata to stderr.

### Recommended Telemetry Additions
- Correlation IDs per user turn.
- Structured logs with tool_name, latency_ms, outcome.
- Metrics:
  - llm_call_count
  - tool_call_count by tool_name
  - tool_error_rate
  - average_turn_latency
- Optional tracing across orchestrator, LLM, MCP, and ADO HTTP calls.

## 14. Testing Strategy

### Existing Tests
- tests/test_util.py for JSON parsing and decision validation.
- tests/test_mock_llm.py for mock tool-call and post-tool finalization behavior.

### Recommended Additional Tests
- Orchestrator integration tests with mocked MCP session.
- Contract tests for LLM decision schema edge cases.
- ADO tool server tests with mocked requests responses.
- Failure-path tests for timeout, HTTP 401/403, and malformed payloads.

## 15. Key Design Decisions and Rationale

1. Pluggable LLM interface
- Decision: LLMClient abstraction.
- Rationale: isolate provider-specific implementation and enable easy swaps.

2. MCP as tool boundary
- Decision: host never directly calls external systems; MCP server does.
- Rationale: clear separation of orchestration from integration logic.

3. Strict JSON protocol for model outputs
- Decision: enforce typed decision contract with pydantic validation.
- Rationale: reduce unpredictable parsing behavior.

4. Tool result normalization to text
- Decision: convert MCP content blocks to plain text before feeding back.
- Rationale: improves reliability of model follow-up reasoning and summarization.

## 16. Risks and Mitigations

Risk: LLM emits invalid JSON.
- Mitigation: strict parser/validator and turn-level failure handling.

Risk: ADO API throttling or transient failures.
- Mitigation: retries with exponential backoff and jitter.

Risk: PAT leakage in logs or config.
- Mitigation: secret masking and secured secret storage.

Risk: Long prompts exceed model context.
- Mitigation: history trimming and optional summarization of prior turns.

Risk: Tool misuse due to poor prompt grounding.
- Mitigation: explicit tool schema injection and deterministic prompt policies.

---

## 17. Guardrails Integration Design (guardrails-ai)

### 17.1 Overview and Motivation

Guardrails-ai (`guardrails-ai` Python package) is a framework that wraps LLM calls and data flows with declarative validation pipelines. Unlike hand-written `if/else` checks, it provides:

- **Validators**: reusable, composable, testable functions that assert properties on strings or structured data.
- **Guard objects**: an execution wrapper that runs validators before and/or after an LLM call, or on arbitrary data.
- **Hub validators**: a registry of community and enterprise-grade validators (toxic language, PII detection, regex patterns, JSON schema conformance, etc.) installable via `guardrails hub install`.
- **Fix-up actions**: on validation failure, guards can choose to `NOOP` (pass-through), `FILTER` (remove), `REASK` (retry the LLM with a correction prompt), or `EXCEPTION` (raise hard error).
- **ValidationOutcome**: a structured result object containing the validated output, raw output, validation errors, and whether the guard passed or failed.

In Chat-Ai, guardrails-ai will be introduced as a dedicated **Guardrails Layer** sitting between user input, LLM output, tool call arguments, tool results, and final answers. This layer is the authoritative enforcement boundary for safety, correctness, and policy compliance.

---

### 17.2 Threat Model and What Guardrails Defends Against

The following threats are in scope for the guardrails layer:

| Threat | Entry Point | Description |
|---|---|---|
| Direct prompt injection | User CLI input | User crafts input to hijack the system prompt or override agent behavior |
| Indirect prompt injection | Tool result (MCP) | External data (e.g. ADO work item title/description) contains injected instructions |
| LLM hallucination / schema violation | LLM output | LLM returns JSON that does not conform to the LLMDecision contract |
| Toxic or inappropriate input | User CLI input | User sends offensive, harmful, or policy-violating content |
| PII leakage in output | Final LLM answer | LLM references personal data from ADO work items in its visible reply |
| Unauthorized tool invocation | LLM decision | LLM fabricates a tool name not registered in the MCP session |
| Oversized payload DoS | Any layer | Extremely large strings passed into prompts or tool calls |
| Sensitive credential exposure | Tool result / logs | ADO API response containing tokens or credentials echoed to user |

---

### 17.3 Guardrails Layer Position in Architecture

The updated runtime flow with guardrails inserted:

```
User Input (CLI)
    │
    ▼
[Guard: InputGuard]          ← Step 1: validate/sanitize user text
    │
    ▼
Orchestrator → LLM.complete()
    │
    ▼
[Guard: LLMOutputGuard]      ← Step 2: validate LLM JSON structure + content
    │
    ▼
Pydantic LLMDecision validate_decision()
    │
    ▼
[Guard: ToolCallGuard]       ← Step 3: validate tool name allowlist + argument safety
    │
    ▼
MCP session.call_tool()
    │
    ▼
[Guard: ToolResultGuard]     ← Step 4: sanitize tool result before re-injecting into prompt
    │
    ▼
Orchestrator builds final_text
    │
    ▼
[Guard: OutputGuard]         ← Step 5: validate final answer for PII, toxicity, length
    │
    ▼
Console output to user
```

Each guard is a separate `Guard` instance defined in a new module `agent/guardrails.py`. Guards are constructed at orchestrator startup and reused across turns.

---

### 17.4 Guard Definitions (Per Layer)

#### Guard 1 — InputGuard

**Purpose:** Validate all raw user text before it enters the message history.

**Validators to apply:**
- `guardrails-hub: ToxicLanguage` — detect hate speech, harassment, and harmful content using an NLP classifier.
- `guardrails-hub: DetectPII` (optional) — warn or block if the user submits PII that should not be processed.
- Custom `PromptInjectionValidator` — regex + semantic pattern match for phrases like "ignore previous instructions", "you are now", "new system prompt", "disregard all" with configurable severity.
- Custom `InputLengthValidator` — enforce maximum character limit (e.g. 2000 chars) to prevent context-stuffing attacks.

**Failure action:** `EXCEPTION` — immediately surface a user-visible error, do not append to message history.

**Reask:** Not applicable for input guard (no LLM involved).

---

#### Guard 2 — LLMOutputGuard

**Purpose:** Validate the raw string returned by the LLM before it is JSON-parsed and fed to `validate_decision()`.

**Validators to apply:**
- `guardrails-hub: ValidJson` — assert the output is parseable JSON before any further processing.
- Custom `LLMDecisionSchemaValidator` — assert the parsed JSON conforms to the `LLMDecision` Pydantic schema (`type`, `name`, `arguments`, `content` fields with correct types).
- Custom `AuthorizedToolValidator` — if `type == "tool_call"`, assert `name` is in the set of tools registered in the current MCP session.
- Custom `OutputLengthValidator` — reject responses over a configurable byte limit (e.g. 10,000 chars) to guard against runaway generation.

**Failure action:** `REASK` (up to 1 retry) — if the LLM output is invalid JSON or wrong schema, append a correction instruction to messages and repeat the LLM call once. If retry also fails, `EXCEPTION`.

**Why REASK here:** The LLM may have accidentally emitted markdown fences or extra text around valid JSON. A single structured retry prompt ("Your last response was not valid JSON. Respond only with the JSON object.") typically recovers the model without losing context.

---

#### Guard 3 — ToolCallGuard

**Purpose:** Validate the tool name and arguments extracted from the LLM decision before calling `session.call_tool()`.

**Validators to apply:**
- Custom `AllowlistToolNameValidator` — hard-block any tool name not in the MCP-discovered tool catalog.
- Custom `ArgumentSizeValidator` — serialize `arguments` to JSON and assert total size is under a configurable limit (e.g. 5,000 chars).
- Custom `ArgumentInjectionValidator` — scan string values within `arguments` for prompt injection patterns (defense against the LLM trying to inject instructions through tool parameters).
- Custom `ArgTypeConformanceValidator` — assert argument values conform to the MCP tool's `inputSchema` JSON Schema definition.

**Failure action:** `EXCEPTION` — do not call the tool; inject a `role=tool` error message into history so the LLM can recover gracefully.

---

#### Guard 4 — ToolResultGuard

**Purpose:** Sanitize the raw text returned by MCP tool execution before it is appended to the conversation as a `role=tool` message.

This is the most security-critical guard because external data (ADO work item titles, descriptions, comments) re-enters the LLM prompt context here. An attacker who controls ADO content could embed injected instructions in a work item description.

**Validators to apply:**
- Custom `IndirectInjectionDetector` — scan returned text for known injection phrases and patterns. On detection, redact the suspicious segment and log a warning.
- Custom `CredentialLeakDetector` — regex scan for patterns resembling API keys, tokens (`Bearer ...`), or PAT-shaped strings. Redact on match.
- Custom `ResultSizeValidator` — truncate or reject results exceeding a configurable character limit (e.g. 8,000 chars) to prevent prompt overflow.
- `guardrails-hub: DetectPII` (optional) — detect PII in tool results, either redact or flag before the LLM sees it.

**Failure action:** `FILTER` — replace suspicious content with a safe placeholder (`[redacted by guardrail]`) rather than blocking the entire turn, allowing the LLM to continue with degraded but safe data.

---

#### Guard 5 — OutputGuard

**Purpose:** Validate the final `content` string produced by the LLM before printing it to the user.

**Validators to apply:**
- `guardrails-hub: ToxicLanguage` — the LLM should not emit toxic or harmful text in its final reply.
- `guardrails-hub: DetectPII` — if the answer references personal data extracted from ADO, optionally redact or warn before surface to the CLI user.
- Custom `OutputLengthGuard` — truncate or page final responses exceeding a display limit (e.g. 5,000 chars).
- Custom `SensitiveKeywordFilter` — block any final response that mentions internal project-sensitive keywords (configurable list loaded from environment or config file).

**Failure action:** `FILTER` on PII fields; `EXCEPTION` on toxicity detection.

---

### 17.5 New Module and File Structure

The following new files will be introduced:

```
agent/
    guardrails.py          ← Guard factory: instantiates and configures all 5 guards
    validators/
        __init__.py
        input_validators.py        ← PromptInjectionValidator, InputLengthValidator
        llm_output_validators.py   ← LLMDecisionSchemaValidator, AuthorizedToolValidator, OutputLengthValidator
        tool_call_validators.py    ← AllowlistToolNameValidator, ArgumentSizeValidator, ArgumentInjectionValidator, ArgTypeConformanceValidator
        tool_result_validators.py  ← IndirectInjectionDetector, CredentialLeakDetector, ResultSizeValidator
        output_validators.py       ← OutputLengthGuard, SensitiveKeywordFilter
```

`agent/guardrails.py` will expose a `GuardrailsManager` class that:
- Is constructed once in `AgentOrchestrator.__init__()`.
- Holds references to all 5 `Guard` instances.
- Exposes typed methods: `validate_input()`, `validate_llm_output()`, `validate_tool_call()`, `validate_tool_result()`, `validate_output()`.
- Centralizes configuration (limits, patterns, allowed tools list) from environment variables or a config file.

---

### 17.6 Integration Points in Orchestrator

The orchestrator (`agent/orchestrator.py`) integrates the guardrails manager at the following call sites:

| Orchestrator location | GuardrailsManager method called |
|---|---|
| `run_cli()` after `console.input()` | `validate_input(user_text)` |
| `_run_agent_loop()` after `llm.complete()` | `validate_llm_output(raw, allowed_tools)` |
| `_run_agent_loop()` before `session.call_tool()` | `validate_tool_call(tool_name, tool_args, allowed_tools)` |
| `_run_agent_loop()` after tool result extraction | `validate_tool_result(tool_text)` |
| `run_cli()` before `console.print(final_text)` | `validate_output(final_text)` |

All methods raise `GuardrailViolationError` (a custom exception) on hard block, or return a (possibly modified) safe string on `FILTER` action.

---

### 17.7 New Dependencies

```
guardrails-ai>=0.5          # core framework
guardrails-hub              # CLI tool to install Hub validators
```

Hub validators to install at setup time (via `guardrails hub install <validator>`):
- `guardrails/toxic_language`
- `guardrails/detect_pii`
- `guardrails/valid_json`

These are installed into the local project environment, not globally, and pinned via `requirements.txt`.

---

### 17.8 Configuration Model (New Environment Variables)

| Variable | Purpose | Default |
|---|---|---|
| `GUARDRAILS_INPUT_MAX_LENGTH` | Max chars for user input | `2000` |
| `GUARDRAILS_RESULT_MAX_LENGTH` | Max chars for tool result fed to LLM | `8000` |
| `GUARDRAILS_OUTPUT_MAX_LENGTH` | Max chars for final answer shown to user | `5000` |
| `GUARDRAILS_LLM_OUTPUT_MAX_LENGTH` | Max chars for raw LLM response | `10000` |
| `GUARDRAILS_LLM_REASK_ENABLED` | Enable single REASK retry on bad LLM JSON | `true` |
| `GUARDRAILS_TOXIC_LANGUAGE_ENABLED` | Enable toxic language checks (input + output) | `true` |
| `GUARDRAILS_PII_DETECTION_ENABLED` | Enable PII detection in tool results + output | `false` |
| `GUARDRAILS_SENSITIVE_KEYWORDS` | Comma-separated list of blocked keywords in output | `` (empty) |
| `GUARDRAILS_LOG_VIOLATIONS` | Write all violations to application log | `true` |

---

### 17.9 Guard Failure Handling and User Experience

- **Hard block (EXCEPTION):** The current turn is aborted. The user sees a clear, user-friendly message (e.g. `[Guardrail] Input blocked: potential injection pattern detected.`). The message is NOT added to conversation history.
- **Filter (FILTER):** Content is redacted and processing continues. The LLM sees redacted content. The user may see `[redacted]` in the assistant's answer if the LLM references the filtered content.
- **Reask (REASK):** Transparent to the user. A correction prompt is silently appended and the LLM is called again. Max 1 reask attempt to avoid latency loops.
- **All violations** are logged at `WARNING` level with context (which guard, which validator, the pattern or reason) for observability and audit.

---

### 17.10 Security Properties Gained

After guardrails-ai integration:

| Property | Before | After |
|---|---|---|
| Prompt injection prevention | None | InputGuard + ToolResultGuard |
| LLM output schema enforcement | Pydantic only (crash on bad data) | Guard REASK + Pydantic (graceful recovery) |
| Unauthorized tool call prevention | None | ToolCallGuard allowlist |
| Indirect injection via ADO data | None | ToolResultGuard IndirectInjectionDetector |
| Toxic content filtering | None | Hub ToxicLanguage at input + output |
| PII leakage prevention | None | Hub DetectPII at tool result + output |
| Credential redaction in tool results | None | CredentialLeakDetector |
| Audit trail of violations | None | Structured log at WARNING level |

---

### 17.11 Testing Strategy for Guardrails

New tests to be added in `tests/`:

- `tests/test_guardrails_input.py`: unit tests for each input validator; test injection patterns, length limits, and pass-through of clean input.
- `tests/test_guardrails_llm_output.py`: test valid/invalid JSON, schema-conformant and non-conformant decisions, oversized output, unauthorized tool names.
- `tests/test_guardrails_tool_call.py`: test allowlist enforcement, oversized args, and arg injection.
- `tests/test_guardrails_tool_result.py`: test injection redaction, credential pattern detection, and result truncation.
- `tests/test_guardrails_output.py`: test PII detection path, length truncation, and keyword filter.

All validators should be unit-testable in isolation since `guardrails-ai` validators are plain Python callables.

Integration tests in `tests/test_orchestrator_guardrails.py` should simulate end-to-end turn execution with both clean and adversarial inputs, verifying that `GuardrailViolationError` is raised at the correct layer and that filtered outputs are sanitized before reaching the console.

---

### 17.12 Phased Implementation Plan

| Phase | Scope | Priority |
|---|---|---|
| Phase 1 | Install guardrails-ai; implement InputGuard (injection + length) and LLMOutputGuard (valid JSON + schema) | High |
| Phase 2 | Implement ToolCallGuard (allowlist + arg size) and ToolResultGuard (indirect injection + credential redaction) | High |
| Phase 3 | Implement OutputGuard (PII + length); integrate Hub validators (ToxicLanguage, DetectPII, ValidJson) | Medium |
| Phase 4 | Add structured violation logging; wire all environment variable config; write full test suite | Medium |
| Phase 5 | Evaluate Azure Content Safety API integration at InputGuard and OutputGuard for enterprise deployment | Low |

## 17. Future Architecture Roadmap

Phase 1
- Add retries and richer ADO error mapping.
- Add orchestrator integration tests.
- Add token-aware history management.

Phase 2
- Add response post-processing policy layer.
- Add optional caching for repeated work-item fetches.
- Add structured telemetry and dashboards.

Phase 3
- Add REST API facade for multi-client access.
- Add authentication and authorization at host boundary.
- Add multi-session persistence and horizontal scalability model.

## 18. File-to-Responsibility Map

- main.py: process bootstrap, env loading, logging, CLI startup.
- agent/orchestrator.py: runtime coordinator and turn loop.
- agent/prompts.py: model instruction and tool schema formatting.
- agent/protocol.py: LLM decision schema.
- agent/util.py: parser and validation helpers.
- llm/base.py: provider interface.
- llm/mock_llm.py: deterministic test provider.
- llm/azure_openai_llm.py: Azure OpenAI async provider.
- mcp_server/mock_tools_server.py: local demonstration tools.
- mcp_server/ado_tools_server.py: Azure DevOps integration tools.

## 19. Operational Runbook Snapshot

Development run:
- LLM_PROVIDER=mock
- python main.py --server python mcp_server/mock_tools_server.py

Enterprise run:
- LLM_PROVIDER=azure_openai
- Set AZURE_OPENAI_* and ADO_* variables
- python main.py --server python mcp_server/ado_tools_server.py

Pre-release checks:
- Install dependencies from requirements.txt.
- Run unit tests.
- Validate ADO credentials and API access scope.
- Smoke test tool calls for work item retrieval and WIQL queries.

## 20. Conclusion

The project already has a strong modular foundation for tool-augmented conversational workflows. The orchestrator-plus-MCP separation is a suitable architecture for evolving from mock tools to enterprise integrations like Azure DevOps. With targeted improvements in retry policies, observability, and integration testing, this architecture can support production-grade use cases while maintaining developer simplicity.

## 21. Detailed Module Design

This section expands each module with responsibilities, key APIs, dependencies, failure modes, and extension points.

### 21.1 main.py

Purpose:
- Process bootstrap and runtime composition root.

Key functions:
- parse_args()
  - Input: CLI arguments.
  - Output: argparse namespace containing --server command tokens.
  - Responsibility: enforce that --server is present and can include command + args.
- main()
  - Input: environment and parsed CLI args.
  - Responsibility:
    - Load .env values.
    - Configure logging level from LOG_LEVEL.
    - Construct AgentOrchestrator with server command.
    - Start async chat lifecycle.

Runtime dependencies:
- dotenv for env loading.
- agent.orchestrator for the runtime coordinator.

Failure behavior:
- Ctrl+C handled gracefully in __main__ guard.
- Misconfigured args result in argparse usage error.

Extension points:
- Add startup diagnostics (connectivity checks, config validation).
- Add mode flags (batch mode, non-interactive mode, transcript mode).

### 21.2 agent/orchestrator.py

Purpose:
- Core runtime controller that bridges CLI, LLM, and MCP server interactions.

Primary responsibilities:
- Spawn MCP subprocess via stdio transport.
- Discover tools from MCP server.
- Manage conversation messages and bounded history.
- Run iterative decision loop until final answer.
- Convert MCP structured tool output to LLM-friendly plain text.

Key methods:
- __init__(server_command)
  - Reads MAX_TOOL_STEPS and MAX_HISTORY_MESSAGES.
  - Chooses LLM provider by LLM_PROVIDER.
  - Initializes provider instance (mock or Azure).
- _trim_history(messages)
  - Keeps all system messages.
  - Keeps only the N most recent non-system messages.
  - Prevents unbounded context growth.
- run_cli()
  - Opens MCP stdio client/session.
  - Calls initialize() and list_tools().
  - Builds merged system prompt with tool schemas.
  - Runs interactive user input loop.
  - Handles turn-level exceptions with user-safe error text.
- _run_agent_loop(session, messages)
  - Repeats up to MAX_TOOL_STEPS:
    - LLM complete()
    - JSON parse + pydantic validation
    - If final: return content
    - If tool_call: invoke MCP tool
    - Normalize tool result and append as role=tool
  - Returns fallback message on step exhaustion.

Important invariants:
- LLM output must parse as JSON and match LLMDecision schema.
- Every tool call result is fed back before next decision.
- Tool loop is bounded by MAX_TOOL_STEPS.

Failure behavior:
- LLM call exception -> RuntimeError and turn failure.
- Invalid LLM JSON/schema -> RuntimeError and turn failure.
- Tool call failure -> tool error message appended, loop continues.

Extension points:
- Add per-turn correlation ID.
- Add retry policies for tool calls.
- Add richer event hooks for metrics and tracing.

### 21.3 agent/prompts.py

Purpose:
- Owns model instruction contract and tool schema prompt serialization.

Key artifacts:
- SYSTEM_PROMPT
  - Constrains model to strict JSON-only responses.
  - Defines two response shapes: tool_call and final.
- tools_to_compact_text(tools)
  - Converts MCP tool metadata to compact bullet text.
  - Includes name, description, inputSchema when available.

Design notes:
- Prompt is intentionally strict to reduce parser failures.
- Tool serialization trades verbosity for compactness to manage context usage.

Extension points:
- Add domain policy blocks (e.g., allowed tool boundaries, pii handling).
- Add role-specific instruction segments for ADO use cases.

### 21.4 agent/protocol.py

Purpose:
- Defines strict schema for LLM decision objects.

Classes:
- LLMDecision(BaseModel)
  - type: Literal["tool_call", "final"]
  - name: Optional[str]
  - arguments: Optional[Dict[str, Any]]
  - content: Optional[str]

Design notes:
- Single union-style model simplifies validation path in orchestrator.
- Optional fields allow one model to represent both variants.

Extension points:
- Add discriminated submodels for stricter per-type enforcement.
- Add custom validators (e.g., require name when type=tool_call).

### 21.5 agent/util.py

Purpose:
- Utility functions for parsing and validation boundaries.

Functions:
- safe_parse_llm_json(text)
  - Trims whitespace and parses JSON.
  - Raises json errors on malformed output.
- validate_decision(obj)
  - Validates object against LLMDecision.
  - Converts pydantic ValidationError into ValueError.

Design notes:
- Keeps parser/validator concerns out of orchestration flow logic.

Extension points:
- Add tolerant JSON extraction strategy for non-compliant models.
- Add structured error categories for telemetry.

### 21.6 llm/base.py

Purpose:
- Provider abstraction contract.

Class:
- LLMClient(ABC)
  - abstract async complete(messages) -> str
  - Contract: return JSON string compatible with LLMDecision.

Design notes:
- Allows runtime provider swap without orchestrator changes.

Extension points:
- Add optional streaming interface.
- Add usage metadata return type (tokens, model id).

### 21.7 llm/mock_llm.py

Purpose:
- Deterministic local provider for development/testing.

Class:
- MockLLM(LLMClient)
  - If last message is role=tool -> returns final with tool content.
  - If user text matches greet pattern -> returns greet tool_call.
  - If user text matches defect/get details pattern -> returns get_defect_details tool_call.
  - Else returns guidance final message.

Design notes:
- Implements finite behavior to validate tool loop deterministically.

Failure behavior:
- Minimal by design; relies on deterministic regex routing.

Extension points:
- Add scenario flags for test-driven negative path simulation.

### 21.8 llm/azure_openai_llm.py

Purpose:
- Production LLM provider using async Azure OpenAI client.

Class:
- AzureOpenAILLM(LLMClient)

Methods:
- from_env()
  - Reads Azure env vars and constructs AsyncAzureOpenAI client.
- complete(messages)
  - Calls chat.completions.create() with model deployment and temperature=0.
  - Returns trimmed assistant content string.

Design notes:
- Async client prevents blocking event loop.
- Temperature zero favors predictable JSON formatting.

Failure behavior:
- Propagates SDK/network/auth exceptions to orchestrator.

Extension points:
- Add response_format JSON schema enforcement if supported.
- Add retry/backoff wrapper around SDK call.

### 21.9 mcp_server/mock_tools_server.py

Purpose:
- Local MCP demo server to validate host-tool loop without external dependencies.

Tools:
- greet(name: str) -> str
- get_defect_details(defectId: str) -> dict

Design notes:
- Must run foreground with stdio transport.
- Should avoid stdout logging.

Extension points:
- Add additional synthetic tools for experimentation.

### 21.10 mcp_server/ado_tools_server.py

Purpose:
- MCP server that integrates with Azure DevOps Work Item APIs.

Private helper functions:
- _base_url()
  - Builds org/project-scoped ADO API base URL.
- _headers()
  - Creates Basic auth header from PAT.

Tools:
- get_work_item(id: int) -> dict
  - Fetches one work item and maps relevant fields.
- list_work_items(wiql: str) -> list
  - Runs WIQL query, then batch-fetches item summary fields.
- get_work_item_comments(id: int) -> list
  - Fetches comment stream for a work item.

Design notes:
- Server logs to stderr only.
- API calls use explicit timeouts.

Failure behavior:
- requests raise_for_status propagates HTTP failures.
- Missing env vars raise KeyError on startup/usage.

Extension points:
- Add retries and rate-limit handling.
- Add batching/pagination for larger WIQL results.
- Add field projection control from caller arguments.

## 22. Detailed Class Inventory

### AgentOrchestrator

Module:
- agent/orchestrator.py

State:
- server_command: List[str]
- max_tool_steps: int
- max_history_messages: int
- llm: LLMClient

Public API:
- run_cli() -> None

Private API:
- _trim_history(messages) -> List[Dict[str, Any]]
- _run_agent_loop(session, messages) -> str

Lifecycle:
1. Constructed with server command and env-based runtime settings.
2. Opens MCP session and enters user loop.
3. Handles each turn by iterative decisioning until final content.

Threading/async model:
- Async methods; runs inside single asyncio event loop.

### LLMDecision

Module:
- agent/protocol.py

Role:
- Canonical envelope for model decision semantics.

Variant semantics:
- type=tool_call: name and arguments expected.
- type=final: content expected.

### LLMClient

Module:
- llm/base.py

Role:
- Provider interface.

Contract:
- complete() must return decision JSON text, not arbitrary prose.

### MockLLM

Module:
- llm/mock_llm.py

Role:
- Controlled behavior for local validation and unit tests.

Decision strategy:
- Regex route by latest user utterance.
- Finalize immediately after tool output present.

### AzureOpenAILLM

Module:
- llm/azure_openai_llm.py

Role:
- External model provider implementation.

External dependencies:
- openai AsyncAzureOpenAI client.
- Azure endpoint, key, deployment.

### FastMCP server instances

Modules:
- mcp_server/mock_tools_server.py
- mcp_server/ado_tools_server.py

Role:
- Host callable tool registry exposed over MCP stdio.

## 23. Configuration Reference (Detailed)

This section describes each configuration field, expected format, defaults, and operational impact.

### 23.1 Core Runtime

- LLM_PROVIDER
  - Required: No (default: mock)
  - Allowed values: mock, azure_openai
  - Impact: selects provider implementation in AgentOrchestrator.

- MAX_TOOL_STEPS
  - Required: No (default: 5)
  - Type: int > 0
  - Impact: upper bound on tool recursion loop.
  - Risk if too low: incomplete multi-step tasks.
  - Risk if too high: increased latency/cost on model/tool errors.

- MAX_HISTORY_MESSAGES
  - Required: No (default: 20)
  - Type: int > 0
  - Impact: number of non-system messages retained.
  - Risk if too low: conversation context loss.
  - Risk if too high: token pressure and latency increase.

- LOG_LEVEL
  - Required: No (default: INFO)
  - Typical values: DEBUG, INFO, WARNING, ERROR
  - Impact: verbosity for runtime diagnostics.

### 23.2 Azure OpenAI

- AZURE_OPENAI_ENDPOINT
  - Required when LLM_PROVIDER=azure_openai: Yes
  - Example: https://<resource>.openai.azure.com/
  - Impact: target inference endpoint.

- AZURE_OPENAI_API_KEY
  - Required when LLM_PROVIDER=azure_openai: Yes
  - Impact: authentication credential for model invocation.

- AZURE_OPENAI_API_VERSION
  - Required: No (default in code: 2024-12-01-preview)
  - Impact: request contract version for Azure SDK calls.

- AZURE_OPENAI_DEPLOYMENT
  - Required when LLM_PROVIDER=azure_openai: Yes
  - Example: gpt-4.1-mini
  - Impact: concrete deployed model used by chat completion call.

### 23.3 Azure DevOps MCP Server

- ADO_ORG
  - Required when using ado_tools_server.py: Yes
  - Example: contoso
  - Impact: forms API host path segment.

- ADO_PROJECT
  - Required when using ado_tools_server.py: Yes
  - Example: Platform
  - Impact: scopes work-item APIs to project.

- ADO_PAT
  - Required when using ado_tools_server.py: Yes
  - Impact: Basic auth token for ADO REST APIs.
  - Security requirement: store in secret manager for production.

### 23.4 CLI Runtime Parameter

- --server
  - Required: Yes
  - Shape: command tokens list (command + args)
  - Examples:
    - python mcp_server/mock_tools_server.py
    - python mcp_server/ado_tools_server.py
  - Impact: determines tool capability surface exposed to the LLM.

### 23.5 Configuration Validation Checklist

At startup, validate:
1. --server command is provided and executable.
2. If LLM_PROVIDER=azure_openai, all AZURE_OPENAI_* vars exist.
3. If ado_tools_server.py is selected, all ADO_* vars exist.
4. MAX_TOOL_STEPS and MAX_HISTORY_MESSAGES parse as positive integers.
5. LOG_LEVEL maps to supported Python logging level.

### 23.6 Recommended Production Config Baseline

- LLM_PROVIDER=azure_openai
- MAX_TOOL_STEPS=5 (start conservative)
- MAX_HISTORY_MESSAGES=20 to 40 depending on prompt size
- LOG_LEVEL=INFO (DEBUG only for short-lived diagnostics)
- ADO_PAT with least privilege and periodic rotation

