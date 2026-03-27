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

If the langsmith SDK is not installed or tracing is disabled, all helpers
become transparent no-ops — zero runtime cost.
"""

import functools
import logging
import os
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


def is_tracing_enabled() -> bool:
    """Return True when LangSmith tracing is active."""
    return _TRACING_ENABLED


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

    Supports both sync and async functions.
    """
    if _TRACING_ENABLED:
        return _ls_traceable(  # type: ignore[return-value]
            run_type=run_type,
            name=name,
            metadata=metadata,
            tags=tags,
        )

    # No-op path: return the original function unchanged.
    def _noop(fn: Callable) -> Callable:
        return fn
    return _noop
