"""Agent orchestrator: MiniCPM tool selection + plan generation + execution."""

from typing import Any
from dataclasses import dataclass, field

from .planner import Plan, PlanStep, PlanExecutor
from .reflector import Reflector
from .orchestrator_model import OrchestratorModel, OrchestratorOutput
from .state import AgentState, StateStore, AgentStatus


@dataclass
class OrchestratorResult:
    plan_context: str | None = None
    memories_context: str | None = None
    selected_tools: list | None = None
    reformulated_query: str | None = None
    plan_steps: int = 0
    plan_failures: int = 0
    status_messages: list[str] = field(default_factory=list)


class AgentOrchestrator:
    """Routes queries via MiniCPM, manages planning, coordinates memory."""

    def __init__(
        self,
        config: dict,
        all_tools: list,
        memory_retriever: Any | None = None,
    ):
        self.config = config
        self.all_tools = all_tools
        self.memory_retriever = memory_retriever
        self.state_store = StateStore(
            config.get(
                "agent_state_path",
                "./agent_state.json"
            )
        )

        self.state = self.state_store.load()
        self.reflector = Reflector()
        self.state_store = StateStore()
        self.state = self.state_store.load()

        orc_config = config.get("orchestrator", {})
        self.orch_model = OrchestratorModel(
            model=orc_config.get("model", "openbmb/minicpm5:fp16"),
            ollama_url=orc_config.get("ollama_url", "http://localhost:11434"),
            all_tools=all_tools,
        )

    def _resolve_tools(self, selected_names: list[str]) -> list:
        """Map MiniCPM-selected tool names to actual tool objects."""
        if not selected_names:
            return self.all_tools
        name_map = {t.__name__: t for t in self.all_tools}
        resolved = [name_map[n] for n in selected_names if n in name_map]
        return resolved if resolved else self.all_tools

    def _build_plan_from_output(self, output: OrchestratorOutput) -> Plan | None:
        """Convert MiniCPM plan to Plan object for execution."""
        if not output.plan:
            return None

        steps = []
        for i, step in enumerate(output.plan):
            desc = f"Run {step.tool}(...)"
            steps.append(PlanStep(
                id=f"step_{i+1}",
                description=desc,
                tool=step.tool,
                args=step.args,
            ))

        return Plan(goal=output.query, steps=steps)

    def _build_plan_context(self, plan: Plan) -> str:
        """Build plan execution summary for system prompt injection."""
        lines = ["## Plan Execution Summary", "", f"Goal: {plan.goal}", ""]
        for i, step in enumerate(plan.steps, 1):
            status = "✓" if step.status.value == "done" else "✗"
            lines.append(f"{status} Step {i}: {step.description}")
            lines.append(f"   Tool: {step.tool}({step.args})")
            if step.result is not None:
                result_str = str(step.result)
                if len(result_str) > 300:
                    result_str = result_str[:300] + "..."
                lines.append(f"   Result: {result_str}")
            if step.error:
                lines.append(f"   Error: {step.error}")
            lines.append("")
        lines.extend([
            "## Instructions", "",
            "Plan above already executed. Results available.",
            "Provide clear summary of what was accomplished.",
            "If steps failed, mention what went wrong.",
            "Do NOT re-execute plan steps.",
        ])
        return "\n".join(lines)

    async def process(
        self,
        user_input: str,
        message_history: list,
    ) -> OrchestratorResult:
        """Process user input via MiniCPM orchestrator.

        1. Retrieve relevant memories.
        2. MiniCPM selects tools, reformulates query, generates plan.
        3. Multi-step plans executed via PlanExecutor.
        """
        result = OrchestratorResult()

        self.state.set_goal(user_input)
        self.state.status = AgentStatus.THINKING

        # Step 1: memories
        if self.memory_retriever is not None:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                memories = await loop.run_in_executor(
                    None, self.memory_retriever.get_auto_inject, user_input
                )
                if memories:
                    result.memories_context = self.memory_retriever.format_for_prompt(memories)
            except Exception:
                pass

        # Step 2: MiniCPM orchestrator
        orc_output = await self.orch_model.analyze(
            user_input,
            memories_context=result.memories_context,
            state_context=self.state.summary(),
            planned=orc_output.plan is not None,
        )

        self.state.add_event(
            "planning",
            "Orchestrator generated plan",
            {
                "tools": orc_output.tools,
                "query": orc_output.query,
            }
        )

        result.selected_tools = self._resolve_tools(orc_output.tools)
        if orc_output.query and orc_output.query != user_input:
            result.reformulated_query = orc_output.query

        # Step 3: execute plan if multi-step
        plan = self._build_plan_from_output(orc_output)
        if plan is not None and len(plan.steps) > 1:
            result.status_messages.append(f"Executing {len(plan.steps)}-step plan...")
            result.plan_steps = len(plan.steps)


            self.state.status = AgentStatus.EXECUTING
            self.state.active_plan = { "goal": plan.goal, "steps": len(plan.steps),}
            
            executor = PlanExecutor(result.selected_tools, self.reflector)
            plan = await executor.execute_plan(plan)
            self.state.record_execution(plan)

            failed = [s for s in plan.steps if s.status.value == "failed"]
            result.plan_failures = len(failed)

            if failed:
                result.status_messages.append(
                    f"{len(failed)} step(s) had issues. "
                    "Proceeding with available results."
                )
            else:
                result.status_messages.append("Plan executed successfully.")

            result.plan_context = self._build_plan_context(plan)

            for step in plan.steps:

                if step.result:
                    self.state.add_observation(
                        source=step.tool,
                        content=str(step.result)[:500]
                    )

                self.state.record_tool(
                    step.tool
                )


            self.state.status = AgentStatus.REFLECTING

            self.state_store.save(
                self.state
            )

        return result
