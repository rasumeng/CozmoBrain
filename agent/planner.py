"""Hybrid planner: LLM generates plan, code validates and executes."""

import json
import asyncio
import urllib.request
import re
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Any, Callable

from .reflector import Reflector
from .tool_registry import ToolRegistry, ToolSpec


PLANNER_PROMPT = """You are a task planner. Given a user's goal and available tools, create a step-by-step plan.

Rules:
- Each step uses exactly one tool from the available list
- Steps can depend on prior steps via depends_on (use step IDs)
- Keep plans minimal — one step per unique tool call needed
- If the goal needs 1 tool call, return a single step
- If a tool fails, the plan should continue with remaining steps
- Consider tool risk levels. Prefer low-risk tools when possible.
- Always return valid JSON only, no extra text

Available tools: {tool_list}

Return format:
{{
  "goal": "restated goal",
  "steps": [
    {{
      "id": "step_1",
      "description": "what this step does",
      "tool": "tool_name",
      "args": {{"arg1": "value1"}},
      "depends_on": []
    }}
  ]
}}"""


class StepStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    id: str
    description: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str = ""


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_text(self) -> str:
        lines = [f"Goal: {self.goal}", ""]
        for i, s in enumerate(self.steps, 1):
            status = s.status.value
            lines.append(f"{i}. [{status}] {s.description}")
            lines.append(f"   Tool: {s.tool}({s.args})")
            if s.depends_on:
                lines.append(f"   Depends on: {', '.join(s.depends_on)}")
            if s.result is not None:
                result_preview = str(s.result)[:100]
                lines.append(f"   Result: {result_preview}")
            if s.error:
                lines.append(f"   Error: {s.error}")
            lines.append("")
        return "\n".join(lines)


class TaskQueue:
    """Manages task state machine with dependency resolution."""

    def __init__(self, steps: list[PlanStep]):
        self.steps = {s.id: s for s in steps}
        self._order = [s.id for s in steps]

    def get_ready(self) -> list[PlanStep]:
        ready = []
        for step in self.steps.values():
            if step.status != StepStatus.PENDING:
                continue
            deps = [self.steps[d] for d in step.depends_on if d in self.steps]
            if all(d.status == StepStatus.DONE for d in deps):
                step.status = StepStatus.READY
                ready.append(step)
        return ready

    def mark_running(self, step_id: str):
        if step_id in self.steps:
            self.steps[step_id].status = StepStatus.RUNNING

    def mark_done(self, step_id: str, result: Any):
        if step_id in self.steps:
            self.steps[step_id].status = StepStatus.DONE
            self.steps[step_id].result = result

    def mark_failed(self, step_id: str, error: str):
        if step_id in self.steps:
            self.steps[step_id].status = StepStatus.FAILED
            self.steps[step_id].error = error

    def all_done(self) -> bool:
        return all(
            s.status in (StepStatus.DONE, StepStatus.SKIPPED, StepStatus.FAILED)
            for s in self.steps.values()
        )

    def has_failures(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps.values())

    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps.values() if s.status == StepStatus.FAILED]


def _tool_name(t: Any) -> str:
    if isinstance(t, ToolSpec):
        return t.name
    return t.__name__


class PlanExecutor:
    """Executes plan steps with reflection-based error recovery."""

    def __init__(self, tools: list | ToolRegistry, reflector: Reflector | None = None):
        if isinstance(tools, ToolRegistry):
            self.tools = {s.name: s for s in tools.all()}
        else:
            self.tools = {_tool_name(t): t for t in tools}
        self.reflector = reflector or Reflector()

    async def execute_step(
        self, step: PlanStep, max_retries: int = 2
    ) -> tuple[bool, Any]:
        tool = self.tools.get(step.tool)
        if not tool:
            return False, f"Tool '{step.tool}' not available"

        last_error = ""
        current_args = dict(step.args)

        for attempt in range(1 + max_retries):
            try:
                self.reflector.before_step(step)

                start = __import__("time").time()
                if asyncio.iscoroutinefunction(tool):
                    result = await tool(**current_args)
                else:
                    result = tool(**current_args)
                duration = __import__("time").time() - start

                reflection = self.reflector.after_step(
                    step.tool, current_args, result, duration
                )
                if reflection.success:
                    return True, result

                last_error = reflection.suggestion
                if reflection.retry_strategy == "abort":
                    return False, last_error
                if reflection.modified_args:
                    current_args.update(reflection.modified_args)

            except Exception as e:
                last_error = str(e)
                if attempt >= max_retries:
                    return False, last_error

        return False, last_error


def _call_llm(
    prompt: str,
    system_prompt: str,
    model: str = "qwen3:8b",
    ollama_url: str = "http://localhost:11434",
    structured: bool = False,
) -> str:
    """Direct Ollama API call for planner/analysis use."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload_dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 1024,
        },
    }
    if structured:
        payload_dict["format"] = "json"
    payload = json.dumps(payload_dict).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data.get("message", {}).get("content", "").strip()
    if "<think>" in content:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


class Planner:
    """Hybrid planner: LLM generates plan, code validates + executes."""

    def __init__(
        self,
        tools: list | ToolRegistry,
        model: str = "qwen3:8b",
        ollama_url: str = "http://localhost:11434",
        max_steps: int = 10,
        tool_registry: ToolRegistry | None = None,
    ):
        self._raw_tools = tools
        self.tool_registry = tool_registry
        self.model = model
        self.ollama_url = ollama_url
        self.max_steps = max_steps
        self.executor = PlanExecutor(tools)

    def _get_tool_list(self) -> str:
        if self.tool_registry:
            return self.tool_registry.describe_all()
        if isinstance(self._raw_tools, ToolRegistry):
            return self._raw_tools.describe_all()
        return "\n".join(f"- {_tool_name(t)}: {t.__doc__ or ''}" for t in self._raw_tools)

    def _tool_names(self) -> set[str]:
        if self.tool_registry:
            return set(self.tool_registry.names())
        if isinstance(self._raw_tools, ToolRegistry):
            return set(self._raw_tools.names())
        return {_tool_name(t) for t in self._raw_tools}

    async def create_plan(self, goal: str) -> Plan | None:
        """Generate a plan from a user goal using the LLM."""
        tool_list = self._get_tool_list()
        prompt = PLANNER_PROMPT.format(tool_list=tool_list)
        user_message = f"Goal: {goal}\n\nAvailable tools:\n{tool_list}"

        response = await asyncio.to_thread(
            _call_llm,
            prompt=user_message,
            system_prompt=prompt,
            model=self.model,
            ollama_url=self.ollama_url,
            structured=True,
        )

        plan_data = self._parse_plan(response)
        if plan_data is None:
            return None

        if not self._validate_plan(plan_data):
            return None

        steps = [
            PlanStep(
                id=s.get("id", f"step_{i}"),
                description=s.get("description", ""),
                tool=s.get("tool", ""),
                args=s.get("args", {}),
                depends_on=s.get("depends_on", []),
            )
            for i, s in enumerate(plan_data.get("steps", []))
        ]

        return Plan(goal=plan_data.get("goal", goal), steps=steps)

    def _parse_plan(self, response: str) -> dict | None:
        """Extract JSON from LLM response."""
        start = response.find("{")
        end = response.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(response[start:end])
        except json.JSONDecodeError:
            return None

    def _validate_plan(self, plan_data: dict) -> bool:
        """Validate plan structure against schema."""
        if "steps" not in plan_data or not isinstance(plan_data["steps"], list):
            return False
        if len(plan_data["steps"]) == 0:
            return False
        if len(plan_data["steps"]) > self.max_steps:
            return False

        step_ids = set()
        tool_names = self._tool_names()

        for i, step in enumerate(plan_data["steps"]):
            if not isinstance(step, dict):
                return False
            step_id = step.get("id", f"step_{i}")
            if step_id in step_ids:
                return False
            step_ids.add(step_id)
            if step.get("tool") not in tool_names:
                return False
            if not isinstance(step.get("args", {}), dict):
                return False
            deps = step.get("depends_on", [])
            if not isinstance(deps, list):
                return False
            for dep in deps:
                if dep not in step_ids and dep not in deps:
                    return False

        return True

    async def execute_plan(
        self, plan: Plan, progress_callback: Callable | None = None
    ) -> Plan:
        """Execute a plan through the TaskQueue."""
        queue = TaskQueue(plan.steps)

        while not queue.all_done():
            ready = queue.get_ready()
            if not ready:
                break

            for step in ready:
                queue.mark_running(step.id)
                if progress_callback:
                    progress_callback(step)

                success, result = await self.executor.execute_step(step)
                if success:
                    queue.mark_done(step.id, result)
                else:
                    queue.mark_failed(step.id, str(result))

        plan.steps = list(queue.steps.values())
        return plan

    async def replan(
        self, goal: str, previous_plan: Plan, failed_context: str
    ) -> Plan | None:
        """Generate a new plan after a step failure."""
        context = (
            f"Previous plan failed. Goal: {goal}\n"
            f"Completed steps: {previous_plan.to_text()}\n"
            f"Failure context: {failed_context}\n"
            f"Generate a revised plan that avoids the failed approach."
        )
        return await self.create_plan(context)
