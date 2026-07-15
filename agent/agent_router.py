from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentProfile:
    name: str
    description: str
    model: str = ""
    system_prompt_override: str = ""
    allowed_categories: list[str] = field(default_factory=lambda: ["*"])
    risk_max: str = "critical"


ROUTER_PROMPT = """You are a request router. Analyze the user query and select the best agent profile.

Profiles:
{profiles}

Rules:
- Choose the profile whose description best matches the query
- If no profile is clearly best, use "default"
- Return ONLY valid JSON, no extra text

Output:
{{"agent": "profile_name", "reason": "one-line justification"}}"""


@dataclass
class RoutingResult:
    agent: str = "default"
    reason: str = ""


class AgentRouter:
    def __init__(self, profiles: list[AgentProfile] | None = None, llm_config: dict | None = None):
        self._profiles: dict[str, AgentProfile] = {}
        self._default = AgentProfile(name="default", description="General-purpose agent")
        if profiles:
            for p in profiles:
                self._profiles[p.name] = p
        self._llm_config = llm_config or {}

    def register(self, profile: AgentProfile):
        self._profiles[profile.name] = profile

    def get(self, name: str) -> AgentProfile:
        return self._profiles.get(name, self._default)

    def all_profiles(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    async def route(self, query: str) -> RoutingResult:
        if not self._llm_config.get("enabled", True):
            return self._route_rule_based(query)

        return await self._route_llm(query)

    def _route_rule_based(self, query: str) -> RoutingResult:
        q = query.lower()
        if any(w in q for w in ["code", "python", "script", "execute", "run", "debug"]):
            return RoutingResult(agent="coder", reason="Query involves code execution")
        if any(w in q for w in ["search", "find", "look up", "research", "what is", "who is"]):
            return RoutingResult(agent="researcher", reason="Query involves research")
        if any(w in q for w in ["write", "save", "store", "create file", "note"]):
            return RoutingResult(agent="writer", reason="Query involves writing content")
        return RoutingResult(agent="default", reason="General query")

    async def _route_llm(self, query: str) -> RoutingResult:
        import json, urllib.request

        profiles_text = "\n".join(
            f"- {p.name}: {p.description}" for p in self.all_profiles()
        )
        prompt = ROUTER_PROMPT.format(profiles=profiles_text)
        model = self._llm_config.get("model", "qwen3:8b")
        url = self._llm_config.get("ollama_url", "http://localhost:11434")

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": query},
            ],
            "options": {"temperature": 0, "num_predict": 256},
            "format": "json",
            "stream": False,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                f"{url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "").strip()
            if content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(content[start:end])
                    agent_name = parsed.get("agent", "default")
                    if agent_name not in self._profiles:
                        agent_name = "default"
                    return RoutingResult(agent=agent_name, reason=parsed.get("reason", ""))
        except Exception:
            pass

        return self._route_rule_based(query)
