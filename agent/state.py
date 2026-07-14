"""
Persistent agent state.

Tracks the current cognitive state of CozmoBrain:
- current goals
- active plans
- observations
- tool usage
- failures
- decisions
- lifecycle status

This is the foundation for autonomous runtime behavior.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any
import json
from pathlib import Path


class AgentStatus:
    IDLE = "idle"
    THINKING = "thinking"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    WAITING = "waiting"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class Observation:
    """
    Something the agent learned from the environment.
    """

    source: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "source": self.source,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AgentEvent:
    """
    Record of something that happened.
    """

    event_type: str
    description: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "event_type": self.event_type,
            "description": self.description,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AgentState:
    """
    Persistent cognitive state for CozmoBrain.
    """

    # Current mission
    current_goal: str | None = None

    # Current execution state
    status: str = AgentStatus.IDLE

    # Planning state
    active_plan: dict[str, Any] | None = None
    current_step: int = 0

    # What the agent currently believes
    observations: list[Observation] = field(default_factory=list)

    # Previous actions
    events: list[AgentEvent] = field(default_factory=list)

    # Tool history
    tools_used: list[str] = field(default_factory=list)

    # Failures encountered
    failures: list[str] = field(default_factory=list)

    # Temporary working memory
    scratchpad: dict[str, Any] = field(default_factory=dict)

    # Creation time
    created_at: datetime = field(default_factory=datetime.now)

    def set_goal(self, goal: str):
        self.current_goal = goal
        self.status = AgentStatus.THINKING

        self.add_event(
            "goal_started",
            f"New goal started: {goal}"
        )

    def clear_goal(self):
        self.current_goal = None
        self.active_plan = None
        self.current_step = 0
        self.status = AgentStatus.IDLE

    def add_observation(
        self,
        source: str,
        content: str,
    ):
        self.observations.append(
            Observation(
                source=source,
                content=content,
            )
        )

    def add_event(
        self,
        event_type: str,
        description: str,
        data: dict[str, Any] | None = None,
    ):
        self.events.append(
            AgentEvent(
                event_type=event_type,
                description=description,
                data=data or {},
            )
        )

    def record_tool(
        self,
        tool_name: str,
    ):
        self.tools_used.append(tool_name)

        self.add_event(
            "tool_used",
            tool_name,
        )

    def record_failure(
        self,
        failure: str,
    ):
        self.failures.append(failure)

        self.status = AgentStatus.ERROR

        self.add_event(
            "failure",
            failure,
        )

    def summary(self) -> dict:
        """
        Compact state summary for prompts.
        """

        return {
            "goal": self.current_goal,
            "status": self.status,
            "current_step": self.current_step,
            "tools_used": self.tools_used[-10:],
            "recent_observations": [
                x.content
                for x in self.observations[-5:]
            ],
            "recent_events": [
                x.description
                for x in self.events[-5:]
            ],
            "failures": self.failures[-5:],
        }


class StateStore:
    """
    Saves agent state between sessions.
    """

    def __init__(
        self,
        path: str = "./agent_state.json",
    ):
        self.path = Path(path)

    def save(
        self,
        state: AgentState,
    ):
        data = {
            "current_goal": state.current_goal,
            "status": state.status,
            "active_plan": state.active_plan,
            "current_step": state.current_step,
            "observations": [
                x.to_dict()
                for x in state.observations
            ],
            "events": [
                x.to_dict()
                for x in state.events
            ],
            "tools_used": state.tools_used,
            "failures": state.failures,
            "scratchpad": state.scratchpad,
            "created_at": state.created_at.isoformat(),
        }

        self.path.write_text(
            json.dumps(
                data,
                indent=2,
                default=str,
            )
        )

    def load(self) -> AgentState:

        if not self.path.exists():
            return AgentState()

        data = json.loads(
            self.path.read_text()
        )

        state = AgentState()

        state.current_goal = data.get(
            "current_goal"
        )

        state.status = data.get(
            "status",
            AgentStatus.IDLE
        )

        state.active_plan = data.get(
            "active_plan"
        )

        state.current_step = data.get(
            "current_step",
            0
        )

        state.tools_used = data.get(
            "tools_used",
            []
        )

        state.failures = data.get(
            "failures",
            []
        )

        state.scratchpad = data.get(
            "scratchpad",
            {}
        )

        return state