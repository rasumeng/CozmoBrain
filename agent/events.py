from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


EVENT_TYPES = frozenset({
    "goal_started",
    "goal_completed",
    "plan_created",
    "plan_failed",
    "tool_started",
    "tool_finished",
    "tool_failed",
    "step_completed",
    "step_failed",
    "reflection_completed",
    "memory_updated",
    "state_changed",
    "error",
    "warning",
    "info",
})


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }


EventHandler = Callable[[Event], None]


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._max_history = 1000

    def subscribe(self, event_type: str, handler: EventHandler):
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event_type}")
        self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: EventHandler):
        for t in EVENT_TYPES:
            self.subscribe(t, handler)

    def unsubscribe(self, event_type: str, handler: EventHandler):
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event_type: str, data: dict | None = None, source: str = ""):
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event_type}")
        event = Event(type=event_type, data=data or {}, source=source)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        for handler in self._subscribers.get(event_type, []):
            handler(event)

    def recent(self, limit: int = 10) -> list[Event]:
        return self._history[-limit:]

    def clear(self):
        self._history.clear()
