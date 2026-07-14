"""MiniCPM orchestrator: lightweight model for tool selection + query reformulation + plan generation.

Uses Ollama's `format: json` (grammar-based sampling) to guarantee structured output.
Output validated against Pydantic schema before use.
"""

import json
import urllib.request
import re
import inspect
from typing import Any
from pydantic import BaseModel, Field
from dataclasses import dataclass


ORCHESTRATOR_SYSTEM_PROMPT = """You are CozmoBrain's orchestrator. Your job: analyze the user request and output structured JSON.

Available tools:
{tools}

Rules:
- Select the MINIMUM tools needed. Quality over quantity.
- Reformulate the query into a clear, specific instruction for the worker model.
- If the request needs multiple sequential steps, provide a plan array.
  Each plan step has: {{"tool": "tool_name", "args": {{...}}}}
  Steps run in order. Results flow step-to-step via context.
- If one step suffices, set plan to null.
- Use memory context if provided, but reformulate the query to be self-contained.
- Return ONLY valid JSON. No extra text, no markdown, no explanations.

Output schema:
{{
  "tools": ["tool_name_1", "tool_name_2"],
  "query": "Reformulated query for the worker model",
  "plan": null or [
    {{"tool": "tool_name", "args": {{"arg1": "value1"}}}}
  ]
}}"""


class PlanStep(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class OrchestratorOutput(BaseModel):
    tools: list[str] = Field(default_factory=list)
    query: str = ""
    plan: list[PlanStep] | None = None


def build_tool_descriptions(tools: list) -> str:
    """Serialize tool functions into descriptions for the orchestrator prompt.

    Each tool described as: name(args) — docstring
    """
    lines = []
    for t in tools:
        name = t.__name__
        sig = _format_signature(t)
        doc = (t.__doc__ or "No description").strip().split("\n")[0]
        lines.append(f"- {name}{sig} — {doc}")
    return "\n".join(lines)


def _format_signature(tool) -> str:
    """Extract function signature as (arg1: type, arg2: type = default)."""
    try:
        sig = inspect.signature(tool)
        parts = []
        for name, param in sig.parameters.items():
            annotation = ""
            if param.annotation is not inspect.Parameter.empty:
                ann = str(param.annotation)
                ann = ann.replace("<class '", "").replace("'>", "")
                ann = ann.replace("typing.", "")
                annotation = f": {ann}"
            default = ""
            if param.default is not inspect.Parameter.empty:
                default = f" = {param.default}"
            parts.append(f"{name}{annotation}{default}")
        return f"({', '.join(parts)})"
    except (ValueError, TypeError):
        return "(...)"


class OrchestratorModel:
    """MiniCPM orchestrator with JSON-guaranteed output.

    Calls Ollama with format=json (grammar-based sampling).
    Validates output against Pydantic schema.
    Falls back gracefully on failure.
    """

    def __init__(
        self,
        model: str = "openbmb/minicpm5:fp16",
        ollama_url: str = "http://localhost:11434",
        all_tools: list | None = None,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.all_tools = all_tools or []

    async def analyze(
        self,
        user_input: str,
        all_tools: list | None = None,
        memories_context: str | None = None,
    ) -> OrchestratorOutput:
        """Analyze user input and return structured output.

        Args:
            user_input: Raw user query.
            all_tools: Full tool list (overrides instance list).
            memories_context: Relevant memories for context.

        Returns:
            OrchestratorOutput with tools, query, and optional plan.
            On failure, returns fallback with all tools + original query.
        """
        tools = all_tools or self.all_tools
        tool_descriptions = build_tool_descriptions(tools)

        system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(tools=tool_descriptions)

        user_prompt = f"User query: {user_input}"
        if memories_context:
            user_prompt += f"\n\nMemory context:\n{memories_context}"

        raw = await self._call(system_prompt, user_prompt)
        if raw is None:
            return self._fallback(user_input)

        parsed = self._parse(raw)
        if parsed is None:
            return self._fallback(user_input)

        validated = self._validate(parsed, user_input)
        return validated

    async def _call(self, system: str, prompt: str) -> str | None:
        """Call Ollama with format=json for guaranteed structured output."""
        import asyncio

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": 0,
                "num_predict": 1024,
            },
            "format": "json",
            "stream": False,
        }).encode("utf-8")

        def _request():
            req = urllib.request.Request(
                f"{self.ollama_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            data = await asyncio.to_thread(_request)
            content = data.get("message", {}).get("content", "").strip()
            if not content:
                return None
            # Strip thinking tags if any
            if "<think>" in content:
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content
        except Exception:
            return None

    def _parse(self, raw: str) -> dict | None:
        """Extract JSON from model response."""
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            return None

    def _validate(self, data: dict, original_query: str) -> OrchestratorOutput:
        """Validate parsed data against schema with fallback."""
        try:
            return OrchestratorOutput(**data)
        except Exception:
            return self._fallback(original_query)

    def _fallback(self, original_query: str) -> OrchestratorOutput:
        """Safe fallback: all tools + original query."""
        return OrchestratorOutput(
            tools=[t.__name__ for t in (self.all_tools or [])],
            query=original_query,
            plan=None,
        )
