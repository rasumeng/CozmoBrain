"""Self-reflection system for post-tool-call analysis and error recovery."""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class ErrorType(Enum):
    TIMEOUT = "timeout"
    AUTH = "authentication"
    NOT_FOUND = "not_found"
    PARSE = "parse_error"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    LOGIC = "logic_error"
    UNKNOWN = "unknown"


class RetryStrategy(Enum):
    RETRY = "retry"
    MODIFY_PARAMS = "modify_params"
    CHANGE_TOOL = "change_tool"
    DECOMPOSE = "decompose"
    ABORT = "abort"


@dataclass
class ReflectionResult:
    success: bool
    error_type: ErrorType = ErrorType.UNKNOWN
    retry_strategy: RetryStrategy | None = None
    suggestion: str = ""
    modified_args: dict[str, Any] | None = None
    confidence: float = 1.0


ERROR_PATTERNS: dict[str, list[str]] = {
    "timeout": ["timeout", "timed out", "timed_out"],
    "authentication": ["401", "403", "unauthorized", "forbidden", "api key", "auth"],
    "not_found": ["404", "not found", "no results", "file not found"],
    "rate_limit": ["429", "rate limit", "too many requests"],
    "parse_error": ["parse", "json decode", "unexpected token", "syntaxerror"],
    "validation": ["validation", "invalid", "required field", "type_error"],
}


class Reflector:
    """Analyzes tool results and recommends recovery strategies."""

    def before_step(self, step) -> dict[str, Any]:
        """Prepare for step execution. Returns context enhancements."""
        return {}

    def after_step(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        duration: float,
    ) -> ReflectionResult:
        """Analyze a tool result and return reflection."""
        if isinstance(result, str) and result.startswith("[error"):
            error_type = self._classify_error(result)
            strategy = self._recommend_strategy(error_type, tool_name)
            modified = None
            if strategy == RetryStrategy.MODIFY_PARAMS:
                modified = self._suggest_param_fix(error_type, tool_name, args, result)
            suggestion = self._build_suggestion(error_type, tool_name, result)
            return ReflectionResult(
                success=False,
                error_type=error_type,
                retry_strategy=strategy,
                suggestion=suggestion,
                modified_args=modified,
            )

        if not result or (
            isinstance(result, str)
            and len(result.strip()) < 15
            and "no" in result.lower()
        ):
            return ReflectionResult(
                success=False,
                error_type=ErrorType.LOGIC,
                retry_strategy=RetryStrategy.MODIFY_PARAMS,
                suggestion="Result seems empty or uninformative. Try different parameters.",
                confidence=0.5,
            )

        return ReflectionResult(success=True)

    def _classify_error(self, error_msg: str) -> ErrorType:
        error_lower = error_msg.lower()
        for error_type, patterns in ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern in error_lower:
                    return ErrorType(error_type)
        return ErrorType.UNKNOWN

    def _recommend_strategy(self, error_type: ErrorType, tool_name: str) -> RetryStrategy:
        mapping = {
            ErrorType.TIMEOUT: RetryStrategy.RETRY,
            ErrorType.AUTH: RetryStrategy.ABORT,
            ErrorType.NOT_FOUND: RetryStrategy.MODIFY_PARAMS,
            ErrorType.RATE_LIMIT: RetryStrategy.RETRY,
            ErrorType.PARSE: RetryStrategy.MODIFY_PARAMS,
            ErrorType.VALIDATION: RetryStrategy.MODIFY_PARAMS,
            ErrorType.LOGIC: RetryStrategy.DECOMPOSE,
            ErrorType.UNKNOWN: RetryStrategy.RETRY,
        }
        return mapping.get(error_type, RetryStrategy.RETRY)

    def _suggest_param_fix(
        self,
        error_type: ErrorType,
        tool_name: str,
        args: dict[str, Any],
        error: str,
    ) -> dict[str, Any] | None:
        import re

        fixes = {}
        if error_type == ErrorType.NOT_FOUND:
            for k, v in args.items():
                if isinstance(v, str):
                    words = v.split()
                    fixes[k] = " ".join(words[: max(1, len(words) // 2)])
        elif error_type == ErrorType.TIMEOUT:
            if "max_results" in args:
                fixes["max_results"] = min(args["max_results"], 3)
        elif error_type == ErrorType.VALIDATION:
            for k, v in args.items():
                if isinstance(v, str):
                    fixes[k] = re.sub(r"[^\w\s\-]", "", v)
        elif error_type == ErrorType.PARSE:
            if "max_results" in args:
                fixes["max_results"] = min(args["max_results"], 3)
        return fixes or None

    def _build_suggestion(
        self, error_type: ErrorType, tool_name: str, error: str
    ) -> str:
        suggestions = {
            ErrorType.TIMEOUT: f"Tool {tool_name} timed out. Retry with fewer params.",
            ErrorType.AUTH: f"Tool {tool_name} needs authentication. Check API keys.",
            ErrorType.NOT_FOUND: f"No results from {tool_name}. Try broader terms.",
            ErrorType.RATE_LIMIT: f"Rate limited on {tool_name}. Wait then retry.",
            ErrorType.PARSE: f"Parse error from {tool_name}. Service may have changed.",
            ErrorType.VALIDATION: f"Invalid args for {tool_name}. Check format.",
            ErrorType.LOGIC: f"Unexpected result from {tool_name}. Wrong approach?",
            ErrorType.UNKNOWN: f"Unknown error from {tool_name}. Retry different approach.",
        }
        return suggestions.get(
            error_type, f"Error using {tool_name}. Check and retry."
        )
