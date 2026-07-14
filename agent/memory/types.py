"""Memory types and schemas for long-term storage."""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class MemoryType(Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass
class MemoryEntry:
    content: str
    path: str = ""
    memory_type: MemoryType = MemoryType.SEMANTIC
    tags: list[str] = field(default_factory=list)
    timestamp: str = ""
    summary: str = ""
    importance: float = 0.5
    embedding: list[float] | None = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.summary and self.content:
            first_line = self.content.strip().split("\n")[0]
            self.summary = first_line[:120]

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "path": self.path,
            "memory_type": self.memory_type.value,
            "tags": self.tags,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "importance": self.importance,
            "vector": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            content=data.get("content", ""),
            path=data.get("path", ""),
            memory_type=MemoryType(data.get("memory_type", "semantic")),
            tags=data.get("tags", []),
            timestamp=data.get("timestamp", ""),
            summary=data.get("summary", ""),
            importance=data.get("importance", 0.5),
            embedding=data.get("vector"),
        )
