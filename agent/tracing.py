"""
Optional LangSmith observability integration.

When enabled (LANGSMITH_TRACING=true), every agent turn, LLM call, and tool
call is traced to your LangSmith project for debugging, evaluation, and
monitoring.

Required env vars:
    LANGSMITH_TRACING   — "true" to enable  (default: "false")
    LANGSMITH_API_KEY   — API key from smith.langchain.com
    LANGSMITH_PROJECT   — project name       (default: "Chat-Ai")
    LANGSMITH_ENDPOINT  — API URL            (default: https://api.smith.langchain.com)

Optional env vars:
    LANGSMITH_REDACT    — "true" to redact PII/secrets from traced inputs
                          (default: "true" when tracing is enabled)

If the langsmith SDK is not installed or tracing is disabled, all helpers
become transparent no-ops — zero runtime cost.
"""

import copy
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detect whether tracing is available and enabled
# ---------------------------------------------------------------------------

_TRACING_ENABLED = False

_enabled_flag = (os.getenv("LANGSMITH_TRACING", "false")).strip().lower()
if _enabled_flag == "true":
    try:
        from langsmith import traceable as _ls_traceable  # type: ignore
        _TRACING_ENABLED = True
        logger.info("LangSmith tracing enabled (project=%s)", os.getenv("LANGSMITH_PROJECT", "Chat-Ai"))
    except ImportError:
        logger.warning(
            "LANGSMITH_TRACING=true but langsmith SDK is not installed. "
            "Run:  pip install langsmith"
        )

# Whether to redact sensitive data before sending to LangSmith.
# Defaults to true when tracing is on — opt OUT by setting LANGSMITH_REDACT=false.
_REDACT_ENABLED = (
    os.getenv("LANGSMITH_REDACT", "true").strip().lower() == "true"
    and _TRACING_ENABLED
)


def is_tracing_enabled() -> bool:
    """Return True when LangSmith tracing is active."""
    return _TRACING_ENABLED


# ---------------------------------------------------------------------------
# Redaction engine
# ---------------------------------------------------------------------------

# Secrets (aligned with guardrails.py patterns)
_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(authorization|api[_-]?key|token|pat|password|secret)\b\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9\-\._~\+/]+=*"),
    re.compile(r"(?i)\bghp_[a-z0-9]{20,}\b"),
    re.compile(r"(?i)\bsk-[a-z0-9]{20,}\b"),           # OpenAI keys
    re.compile(r"(?i)\blsv2_[a-z0-9]{20,}\b"),          # LangSmith keys
    re.compile(r"(?i)\bsk-ant-[a-z0-9\-]{20,}\b"),      # Anthropic keys
]

# PII
_PII_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # email
    re.compile(r"(?<!\d)(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),  # phone
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),               # SSN
]

_PLACEHOLDER_SECRET = "[redacted-secret]"
_PLACEHOLDER_EMAIL = "[redacted-email]"
_PLACEHOLDER_PHONE = "[redacted-phone]"
_PLACEHOLDER_SSN = "[redacted-ssn]"


def _redact_text(text: str) -> str:
    """Apply all redaction patterns to a string."""
    for p in _SECRET_PATTERNS:
        text = p.sub(_PLACEHOLDER_SECRET, text)
    text = _PII_PATTERNS[0].sub(_PLACEHOLDER_EMAIL, text)
    text = _PII_PATTERNS[1].sub(_PLACEHOLDER_PHONE, text)
    text = _PII_PATTERNS[2].sub(_PLACEHOLDER_SSN, text)
    return text


def _redact_value(value: Any) -> Any:
    """Recursively redact strings inside dicts, lists, and plain values."""
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(item) for item in value)
    return value


def _redact_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deep-copy and redact a message list, masking the system prompt body."""
    out = []
    for msg in messages:
        m = dict(msg)  # shallow copy
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            # Replace full system prompt with a safe placeholder — it contains
            # tool schemas, internal instructions, and routing details.
            m["content"] = "[system prompt redacted]"
        elif isinstance(content, str):
            m["content"] = _redact_text(content)
        out.append(m)
    return out


def _process_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Called by langsmith before serialising trace inputs.
    Returns a redacted copy — the original objects are never mutated.
    """
    if not _REDACT_ENABLED:
        return inputs

    safe = {}
    for key, val in inputs.items():
        if key == "messages":
            safe[key] = _redact_messages(val)
        elif key == "self":
            safe[key] = val  # class instance — skip, nothing sensitive
        else:
            safe[key] = _redact_value(val)
    return safe


# ---------------------------------------------------------------------------
# @traceable decorator  (no-op when tracing is off)
# ---------------------------------------------------------------------------

def traceable(
    *,
    run_type: str = "chain",
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Callable:
    """
    Decorator that wraps a function with LangSmith tracing when enabled.

    Falls back to a transparent pass-through when the SDK is missing or
    LANGSMITH_TRACING is not "true".

    When LANGSMITH_REDACT is true (the default), inputs are scrubbed of
    secrets, PII, and the full system prompt before being sent to LangSmith.

    Supports both sync and async functions.
    """
    if _TRACING_ENABLED:
        return _ls_traceable(  # type: ignore[return-value]
            run_type=run_type,
            name=name,
            metadata=metadata,
            tags=tags,
            process_inputs=_process_inputs,
        )

    # No-op path: return the original function unchanged.
    def _noop(fn: Callable) -> Callable:
        return fn
    return _noop
