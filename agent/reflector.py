from enum import Enum
from dataclasses import dataclass, field
from typing import Any
import json
import urllib.request
import re


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


LLM_REFLECT_PROMPT = """You are a failure analyst for an AI agent. Analyze the tool failure and output JSON.

Tool: {tool_name}
Arguments: {args}
Error: {error}
Similar past lessons: {lessons}

Analyze the root cause and recommend a recovery strategy.

Output JSON:
{{
  "root_cause": "brief explanation",
  "strategy": "retry" | "modify_params" | "change_tool" | "decompose" | "abort",
  "suggestion": "specific actionable advice",
  "confidence": 0.0-1.0,
  "store_lesson": true or false,
  "param_fixes": {{"param_name": "fixed_value"}} or null
}}"""


@dataclass
class Lesson:
    tool: str
    error_pattern: str
    root_cause: str
    strategy: str
    suggestion: str
    context: str = ""

    def matches(self, tool: str, error: str) -> float:
        score = 0.0
        if self.tool == tool:
            score += 0.4
        if self.error_pattern.lower() in error.lower():
            score += 0.4
        if self.context and self.context.lower() in error.lower():
            score += 0.2
        return min(score, 1.0)


class LessonStore:
    def __init__(self):
        self._lessons: list[Lesson] = []

    def add(self, lesson: Lesson):
        self._lessons.append(lesson)

    def search(self, tool: str, error: str, top_k: int = 3) -> list[tuple[Lesson, float]]:
        scored = [(l, l.matches(tool, error)) for l in self._lessons]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(l, s) for l, s in scored if s > 0][:top_k]

    def format_for_prompt(self, tool: str, error: str) -> str:
        matches = self.search(tool, error)
        if not matches:
            return "No similar past failures."
        lines = []
        for lesson, score in matches:
            lines.append(f"- [{score:.0%}] {lesson.tool}: {lesson.root_cause} → {lesson.suggestion}")
        return "\n".join(lines)

    def count(self) -> int:
        return len(self._lessons)


class Reflector:
    def __init__(self, lesson_store: LessonStore | None = None, llm_config: dict | None = None):
        self._lesson_store = lesson_store or LessonStore()
        self._llm_config = llm_config or {}
        self._llm_enabled = bool(self._llm_config.get("model"))

    def before_step(self, step) -> dict[str, Any]:
        return {}

    def after_step(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        duration: float,
    ) -> ReflectionResult:
        if isinstance(result, str) and result.startswith("[error"):
            error_type = self._classify_error(result)
            result_obj = self._try_llm_reflect(tool_name, args, result, error_type)
            if result_obj:
                return result_obj
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

    def _try_llm_reflect(
        self, tool_name: str, args: dict, error: str, error_type: ErrorType
    ) -> ReflectionResult | None:
        if not self._llm_enabled:
            return None
        try:
            lessons = self._lesson_store.format_for_prompt(tool_name, error)
            prompt = LLM_REFLECT_PROMPT.format(
                tool_name=tool_name,
                args=json.dumps(args),
                error=error,
                lessons=lessons,
            )
            raw = self._call_llm(prompt)
            if not raw:
                return None
            data = json.loads(raw)
            strategy = data.get("strategy", "retry")
            result = ReflectionResult(
                success=False,
                error_type=error_type,
                retry_strategy=RetryStrategy(strategy) if strategy in [e.value for e in RetryStrategy] else RetryStrategy.RETRY,
                suggestion=data.get("suggestion", ""),
                modified_args=data.get("param_fixes"),
                confidence=data.get("confidence", 0.5),
            )
            if data.get("store_lesson"):
                self._lesson_store.add(Lesson(
                    tool=tool_name,
                    error_pattern=error[:120],
                    root_cause=data.get("root_cause", ""),
                    strategy=strategy,
                    suggestion=data.get("suggestion", ""),
                    context=json.dumps(args),
                ))
            return result
        except Exception:
            return None

    def _call_llm(self, prompt: str) -> str | None:
        model = self._llm_config.get("model", "qwen3:8b")
        url = self._llm_config.get("ollama_url", "http://localhost:11434")
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_predict": 512},
            "format": "json",
            "stream": False,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"{url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "").strip()
            if not content:
                return None
            start = content.find("{")
            end = content.rfind("}") + 1
            if start < 0 or end <= start:
                return None
            return content[start:end]
        except Exception:
            return None

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
