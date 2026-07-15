"""End-to-end test suite for CozmoBrain agent runtime.

Usage:
    $env:PYTHONIOENCODING='utf-8'; python test_e2e.py

Requires Ollama running with models: openbmb/minicpm5:Q4_K_M, qwen3:8b
"""
import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")


async def test_ollama():
    import urllib.request
    model = "openbmb/minicpm5:Q4_K_M"
    url = "http://localhost:11434"
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": "say hi"}], "stream": False}).encode("utf-8")
    req = urllib.request.Request(f"{url}/api/chat", data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read())
    assert d["message"]["content"].strip(), "Empty response"
    print("[PASS] Ollama reachable")


async def test_tool_registry():
    from agent.tool_registry import ToolRegistry, ToolSpec, RiskLevel
    ts = ToolSpec(name="test", description="A test tool", fn=lambda x: x, risk_level=RiskLevel.LOW, permissions={"read"}, category="test")
    r = ToolRegistry([ts])
    assert r.get("test")("ok") == "ok"
    assert r.get("test").name == "test"
    assert len(r.by_permissions({"read"})) == 1
    assert len(r.by_risk(RiskLevel.LOW)) == 1
    assert r.describe_all()
    print("[PASS] ToolRegistry")


async def test_state():
    from agent.state import AgentState, StateStore
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "test_agent_state.json")
    store = StateStore(path)
    state = AgentState()
    state.set_goal("test")
    state.record_tool("search")
    state.record_failure("timeout")
    store.save(state)
    loaded = store.load()
    assert loaded.current_goal == "test"
    assert "search" in loaded.tools_used
    assert loaded.status == "error"
    os.remove(path)
    print("[PASS] State persistence")


async def test_events():
    from agent.events import EventBus
    bus = EventBus()
    captured = []
    bus.subscribe("tool_started", lambda e: captured.append(e))
    bus.emit("tool_started", {"tool": "search"})
    assert len(captured) == 1
    assert captured[0].data["tool"] == "search"
    print("[PASS] EventBus")


async def test_reflector():
    from agent.reflector import Reflector, LessonStore, Lesson
    r = Reflector()
    res = r.after_step("search", {"q": "test"}, "[error] timeout", 5.0)
    assert not res.success
    assert res.retry_strategy is not None
    store = LessonStore()
    store.add(Lesson("search", "timeout", "Network issue", "retry", "Reduce params"))
    matches = store.search("search", "timed out")
    assert len(matches) > 0
    assert matches[0][1] > 0
    print("[PASS] Reflector + LessonStore")


async def test_agent_router():
    from agent.agent_router import AgentRouter, AgentProfile
    router = AgentRouter()
    router.register(AgentProfile(name="coder", description="Code tasks"))
    router.register(AgentProfile(name="researcher", description="Research tasks"))
    r = router._route_rule_based("write a python script")
    assert r.agent == "coder"
    r = router._route_rule_based("search for news")
    assert r.agent == "researcher"
    print("[PASS] AgentRouter")


async def test_orchestrator():
    from agent.orchestrator_model import OrchestratorModel, OrchestratorOutput

    def sa(q: str) -> str:
        """Search. Args: q: query."""
        return "ok"
    def fu(u: str) -> str:
        """Fetch. Args: u: url."""
        return "ok"

    orch = OrchestratorModel(model="openbmb/minicpm5:Q4_K_M", all_tools=[sa, fu])
    result = await orch.analyze("search for python")
    assert isinstance(result, OrchestratorOutput)
    assert len(result.tools) > 0
    assert result.query
    print(f"[PASS] Orchestrator: tools={result.tools}")


async def test_planner():
    from agent.planner import Planner
    from agent.tool_registry import ToolRegistry, ToolSpec, RiskLevel

    registry = ToolRegistry([
        ToolSpec(name="search", description="Search the web", fn=lambda q: f"Results for {q}", risk_level=RiskLevel.LOW, permissions={"network"}, category="research"),
        ToolSpec(name="fetch", description="Fetch a URL", fn=lambda u: f"Content from {u}", risk_level=RiskLevel.MEDIUM, permissions={"network"}, category="research"),
    ])
    planner = Planner(tools=registry, model="qwen3:8b", tool_registry=registry)
    plan = await planner.create_plan("search python news")
    assert plan is not None, "Planner should return a plan"
    assert len(plan.steps) > 0, "Plan should have steps"
    print(f"[PASS] Planner: {len(plan.steps)} steps")


async def test_runtime():
    from agent.runtime import CognitiveRuntime
    from agent.tool_registry import ToolRegistry, ToolSpec, RiskLevel
    from agent.events import EventBus

    registry = ToolRegistry([
        ToolSpec(name="search", description="Search the web", fn=lambda q: f"Results for {q}", risk_level=RiskLevel.LOW, permissions={"network"}, category="research"),
        ToolSpec(name="fetch", description="Fetch a URL", fn=lambda u: f"Content from {u}", risk_level=RiskLevel.MEDIUM, permissions={"network"}, category="research"),
    ])
    config = {
        "agent_state_path": "./test_agent_state.json",
        "orchestrator": {"model": "openbmb/minicpm5:Q4_K_M", "planner_model": "qwen3:8b", "ollama_url": "http://localhost:11434"},
        "max_plan_retries": 1,
    }
    bus = EventBus()
    events = []
    bus.subscribe_all(lambda e: events.append(e.type))
    runtime = CognitiveRuntime(config, tool_registry=registry, all_tools=registry.to_callables(), event_bus=bus)
    result = await runtime.run("search python news")
    assert "success" in result
    plan = result.get("plan")
    assert plan is not None, "Runtime should produce a plan"
    print(f"[PASS] Runtime: {len(plan.steps)} steps, {len(events)} events, state={runtime.state.status}")
    if os.path.exists("./test_agent_state.json"):
        os.remove("./test_agent_state.json")


async def main():
    tests = [
        ("Ollama", test_ollama),
        ("ToolRegistry", test_tool_registry),
        ("State", test_state),
        ("Events", test_events),
        ("Reflector", test_reflector),
        ("AgentRouter", test_agent_router),
        ("Orchestrator", test_orchestrator),
        ("Planner", test_planner),
        ("Runtime", test_runtime),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            print(f"  {name}...", end=" ", flush=True)
            await fn()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {e}")
            failed += 1
    total = len(tests)
    print(f"\n{'='*30}")
    print(f"{passed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
