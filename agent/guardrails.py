"""
Guardrails for the agent pipeline using the guardrails-ai framework.

Hub validators — install once with the guardrails CLI before running:
    guardrails hub install hub://guardrails/valid_length
    guardrails hub install hub://guardrails/detect_prompt_injection
    guardrails hub install hub://guardrails/toxic_language   # optional, for output

Three enforcement points:
  1. check_input()     — before user message enters the LLM context
  2. check_tool_call() — before an MCP tool is executed
  3. check_output()    — before the final answer is shown / stored

Environment variables:
    MAX_INPUT_LENGTH   max characters from the user         (default 2000)
    MAX_OUTPUT_LENGTH  max characters in assistant reply    (default 8000)
    MAX_ARG_LENGTH     max characters per tool argument     (default 1000)
    ALLOWED_TOOLS      comma-separated permitted tool names; empty = all allowed
"""

import logging
import os
import re
from typing import Any, Dict, Optional

from guardrails import Guard

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional hub validators — degrade gracefully when not installed
# ---------------------------------------------------------------------------
try:
    from guardrails.hub import ValidLength
    _HAS_VALID_LENGTH = True
except ImportError:
    _HAS_VALID_LENGTH = False
    logger.warning(
        "ValidLength not installed. "
        "Run: guardrails hub install hub://guardrails/valid_length"
    )

try:
    from guardrails.hub import DetectPromptInjection
    _HAS_PROMPT_INJECTION = True
except ImportError:
    _HAS_PROMPT_INJECTION = False
    logger.warning(
        "DetectPromptInjection not installed. "
        "Run: guardrails hub install hub://guardrails/detect_prompt_injection"
    )

try:
    from guardrails.hub import ToxicLanguage
    _HAS_TOXIC_LANGUAGE = True
except ImportError:
    _HAS_TOXIC_LANGUAGE = False


class GuardrailViolation(Exception):
    """Raised by any check_*() method when a policy is violated."""


class Guardrails:
    """
    Guardrails applied at three points using the guardrails-ai Guard API.

    Each guard is built once at construction from hub validators that happen
    to be installed.  Missing validators degrade gracefully to simple
    fallback checks so the agent still runs without the hub.
    """

    def __init__(self) -> None:
        self.security_mode = (os.getenv("SECURITY_MODE") or "dev").strip().lower()
        self.strict_mode = self.security_mode in ("prod", "production", "strict")

        self.max_input_length: int = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
        self.max_output_length: int = int(os.getenv("MAX_OUTPUT_LENGTH", "8000"))
        self.max_arg_length: int = int(os.getenv("MAX_ARG_LENGTH", "1000"))
        self.max_tool_result_length: int = int(os.getenv("MAX_TOOL_RESULT_LENGTH", "6000"))

        raw_allowed = os.getenv("ALLOWED_TOOLS", "").strip()
        self.allowed_tools: Optional[set] = (
            {t.strip() for t in raw_allowed.split(",") if t.strip()}
            if raw_allowed
            else None  # None means "all tools permitted"
        )

        # In strict mode, fail closed on missing critical validators.
        missing_validators = []
        if not _HAS_VALID_LENGTH:
            missing_validators.append("ValidLength")
        if not _HAS_PROMPT_INJECTION:
            missing_validators.append("DetectPromptInjection")

        if self.strict_mode and missing_validators:
            raise RuntimeError(
                "SECURITY_MODE is strict but required guardrails validators are missing: "
                f"{', '.join(missing_validators)}"
            )

        if self.strict_mode and self.allowed_tools is None:
            raise RuntimeError(
                "SECURITY_MODE is strict but ALLOWED_TOOLS is not configured. "
                "Set ALLOWED_TOOLS to a comma-separated explicit allowlist."
            )

        self._input_guard = self._build_input_guard()
        self._output_guard = self._build_output_guard()
        self._arg_guard = self._build_arg_guard()

        # Simple fallback patterns for tool-result sanitization.
        self._tool_injection_patterns = [
            re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
            re.compile(r"override\s+(your|all)\s+(instructions?|system|directives?)", re.IGNORECASE),
            re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
            re.compile(r"do not follow.*policy", re.IGNORECASE),
        ]
        self._secret_patterns = [
            re.compile(r"(?i)\b(authorization|api[_-]?key|token|pat|password|secret)\b\s*[:=]\s*[^\s,;]+"),
            re.compile(r"(?i)\bbearer\s+[a-z0-9\-\._~\+/]+=*"),
            re.compile(r"(?i)\bghp_[a-z0-9]{20,}\b"),
        ]

    # ------------------------------------------------------------------
    # Guard builders
    # ------------------------------------------------------------------
    def _build_input_guard(self) -> Guard:
        guard = Guard()
        if _HAS_VALID_LENGTH:
            guard = guard.use(
                ValidLength(min=1, max=self.max_input_length, on_fail="exception")
            )
        if _HAS_PROMPT_INJECTION:
            guard = guard.use(DetectPromptInjection(on_fail="exception"))
        return guard

    def _build_output_guard(self) -> Guard:
        guard = Guard()
        if _HAS_VALID_LENGTH:
            # on_fail="fix" → ValidLength truncates to max_output_length automatically
            guard = guard.use(
                ValidLength(min=0, max=self.max_output_length, on_fail="fix")
            )
        if _HAS_TOXIC_LANGUAGE:
            guard = guard.use(ToxicLanguage(on_fail="exception"))
        return guard

    def _build_arg_guard(self) -> Guard:
        guard = Guard()
        if _HAS_VALID_LENGTH:
            guard = guard.use(
                ValidLength(min=0, max=self.max_arg_length, on_fail="exception")
            )
        return guard

    # ------------------------------------------------------------------
    # 1. Input guardrail
    # ------------------------------------------------------------------
    def check_input(self, text: str) -> str:
        """
        Validate user input before it enters the LLM context.
        Returns the text if valid; raises GuardrailViolation otherwise.
        """
        if not _HAS_VALID_LENGTH and len(text) > self.max_input_length:
            raise GuardrailViolation(
                f"Input too long ({len(text):,} chars). "
                f"Maximum allowed is {self.max_input_length:,}."
            )
        try:
            outcome = self._input_guard.validate(text)
            return outcome.validated_output if outcome.validated_output is not None else text
        except GuardrailViolation:
            raise
        except Exception as exc:
            raise GuardrailViolation(str(exc)) from exc

    # ------------------------------------------------------------------
    # 2. Tool-call guardrail
    # ------------------------------------------------------------------
    def check_tool_call(self, name: str, arguments: Dict[str, Any]) -> None:
        """
        Validate a tool call before it is sent to the MCP server.
        Raises GuardrailViolation if the tool is not allowed or an argument
        fails validation.
        """
        if self.allowed_tools is not None and name not in self.allowed_tools:
            raise GuardrailViolation(
                f"Tool '{name}' is not permitted. "
                f"Allowed tools: {sorted(self.allowed_tools)}"
            )

        for key, val in arguments.items():
            str_val = val if isinstance(val, str) else str(val)

            if not _HAS_VALID_LENGTH and len(str_val) > self.max_arg_length:
                raise GuardrailViolation(
                    f"Argument '{key}' is too long "
                    f"({len(str_val):,} chars > max {self.max_arg_length:,})."
                )
            try:
                self._arg_guard.validate(str_val)
            except GuardrailViolation:
                raise
            except Exception as exc:
                raise GuardrailViolation(f"Argument '{key}' blocked: {exc}") from exc

    # ------------------------------------------------------------------
    # 3. Output guardrail
    # ------------------------------------------------------------------
    def check_output(self, text: str) -> str:
        """
        Validate / truncate the final assistant reply before it is returned.
        ValidLength with on_fail="fix" handles truncation automatically.
        """
        if not _HAS_VALID_LENGTH:
            if len(text) > self.max_output_length:
                logger.warning(
                    "Output truncated: %d → %d chars", len(text), self.max_output_length
                )
                return (
                    text[: self.max_output_length]
                    + "\n[... response truncated by output guardrail]"
                )
            return text
        try:
            outcome = self._output_guard.validate(text)
            return outcome.validated_output if outcome.validated_output is not None else text
        except GuardrailViolation:
            raise
        except Exception as exc:
            logger.warning("Output validation error: %s", exc)
            return text

    # ------------------------------------------------------------------
    # 4. Tool-result guardrail
    # ------------------------------------------------------------------
    def check_tool_result(self, text: str) -> str:
        """
        Validate and sanitize tool output before it is appended to model context.
        """
        sanitized = text

        if len(sanitized) > self.max_tool_result_length:
            logger.warning(
                "Tool result truncated: %d -> %d chars",
                len(sanitized),
                self.max_tool_result_length,
            )
            sanitized = sanitized[: self.max_tool_result_length] + "\n[tool result truncated]"

        for pattern in self._secret_patterns:
            sanitized = pattern.sub("[redacted-secret]", sanitized)

        injection_hits = [p for p in self._tool_injection_patterns if p.search(sanitized)]
        if injection_hits:
            if self.strict_mode:
                raise GuardrailViolation("Tool result blocked: potential indirect prompt injection detected.")
            logger.warning("Tool result had prompt-injection indicators; redacting suspicious content")
            for pattern in self._tool_injection_patterns:
                sanitized = pattern.sub("[redacted-injection-pattern]", sanitized)

        return sanitized
