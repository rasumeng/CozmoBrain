from typing import Any

from .state import AgentState, StateStore, AgentStatus
from .planner import Planner, Plan, PlanStep
from .reflector import Reflector, LessonStore, ReflectionResult
from .events import EventBus
from .orchestrator_model import OrchestratorModel
from .tool_registry import ToolRegistry
from .agent_router import AgentRouter


class CognitiveRuntime:
    def __init__(
        self,
        config: dict,
        tool_registry: ToolRegistry | None = None,
        all_tools: list | None = None,
        event_bus: EventBus | None = None,
        agent_router: AgentRouter | None = None,
    ):
        state_path = config.get("agent_state_path", "./agent_state.json")
        self.state_store = StateStore(state_path)
        self.state = self.state_store.load()
        self.event_bus = event_bus or EventBus()
        self.tool_registry = tool_registry
        self.agent_router = agent_router

        orc_config = config.get("orchestrator", {})
        reflect_config = config.get("reflection", {})

        lesson_store = LessonStore()
        llm_reflect_config = {}
        if reflect_config.get("llm_enabled", False):
            llm_reflect_config = {
                "model": reflect_config.get("llm_model", orc_config.get("model", "qwen3:8b")),
                "ollama_url": reflect_config.get("ollama_url", orc_config.get("ollama_url", "http://localhost:11434")),
            }
        self.reflector = Reflector(lesson_store=lesson_store, llm_config=llm_reflect_config)

        self.orch_model = OrchestratorModel(
            model=orc_config.get("model", "openbmb/minicpm5:fp16"),
            ollama_url=orc_config.get("ollama_url", "http://localhost:11434"),
            all_tools=all_tools or [],
            tool_registry=tool_registry,
            agent_router=agent_router,
        )
        self.planner = Planner(
            tools=tool_registry or all_tools or [],
            model=orc_config.get("planner_model", orc_config.get("model", "qwen3:8b")),
            ollama_url=orc_config.get("ollama_url", "http://localhost:11434"),
            tool_registry=tool_registry,
        )

        self.max_retries = config.get("max_plan_retries", 2)

    async def run(self, goal: str) -> dict[str, Any]:
        self.state.set_goal(goal)
        self.state.status = AgentStatus.THINKING
        self.event_bus.emit("goal_started", {"goal": goal})
        self._save()

        profile = "default"
        if self.agent_router:
            routing = await self.agent_router.route(goal)
            profile = routing.agent
            self.state.scratchpad["agent_profile"] = profile
            self.event_bus.emit("info", {"router": profile, "reason": routing.reason})

        plan = await self._plan(profile)
        if plan is None:
            self.state.status = AgentStatus.ERROR
            self._save()
            return {"success": False, "error": "Failed to create plan", "agent_profile": profile}

        result = await self._execute(plan)
        self.state.status = AgentStatus.COMPLETE
        self._save()
        self.event_bus.emit("goal_completed", {"goal": goal, "success": result.get("success")})
        result["agent_profile"] = profile
        return result

    async def _plan(self, profile: str = "default") -> Plan | None:
        self.state.status = AgentStatus.PLANNING
        self.event_bus.emit("plan_created", {"goal": self.state.current_goal, "status": "started"})

        plan = await self.planner.create_plan(self.state.current_goal)
        if plan is None:
            plan = await self._fallback_plan(profile)

        if plan:
            self.state.active_plan = {"goal": plan.goal, "steps": len(plan.steps)}
            self.event_bus.emit("plan_created", {
                "goal": plan.goal,
                "steps": len(plan.steps),
                "status": "ready",
            })
            self._save()
        return plan

    async def _fallback_plan(self, profile: str = "default") -> Plan | None:
        orc_output = await self.orch_model.analyze(
            self.state.current_goal,
            agent_profile=profile,
        )
        if orc_output.plan:
            steps = []
            for i, step in enumerate(orc_output.plan):
                steps.append(PlanStep(
                    id=f"step_{i+1}",
                    description=f"Run {step.tool}(...)",
                    tool=step.tool,
                    args=step.args,
                ))
            return Plan(goal=orc_output.query or self.state.current_goal, steps=steps)
        return None

    async def _execute(self, plan: Plan) -> dict[str, Any]:
        self.state.status = AgentStatus.EXECUTING
        self.event_bus.emit("state_changed", {"status": AgentStatus.EXECUTING})

        plan = await self.planner.execute_plan(plan)
        self.state.record_execution(plan)

        failed = [s for s in plan.steps if s.status.value == "failed"]
        for step in failed:
            self.state.record_failure(f"{step.tool}: {step.error}")

        self.state.status = AgentStatus.REFLECTING
        reflection = self._reflect(plan, failed)
        self.event_bus.emit("reflection_completed", {
            "success": len(failed) == 0,
            "failures": len(failed),
        })

        if failed and self.state.failures.count(None) < self.max_retries:
            plan = await self.planner.replan(
                self.state.current_goal, plan,
                f"Failed steps: {[s.tool for s in failed]}"
            )
            if plan:
                return await self._execute(plan)

        return {
            "success": len(failed) == 0,
            "plan": plan,
            "failures": failed,
        }

    def _reflect(self, plan: Plan, failed_steps: list) -> list[dict[str, Any]]:
        results = []
        for step in failed_steps:
            reflection = self.reflector.after_step(
                step.tool, step.args, step.error, 0
            )
            self.state.add_observation(
                source="reflector",
                content=f"Failure in {step.tool}: {reflection.suggestion}",
            )
            results.append({
                "step": step.id,
                "reflection": reflection,
            })
        return results

    def _save(self):
        self.state_store.save(self.state)

    def load_state(self):
        self.state = self.state_store.load()
