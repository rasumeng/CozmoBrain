from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
import inspect


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


STD_PERMISSIONS = frozenset({"read", "write", "execute", "network", "filesystem", "dangerous"})


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: Callable
    risk_level: RiskLevel = RiskLevel.LOW
    permissions: set[str] = field(default_factory=set)
    category: str = "general"

    def __post_init__(self):
        self.__name__ = self.name
        self.__doc__ = self.description
        self.__wrapped__ = self.fn
        self.__signature__ = self._build_signature()

    def _build_signature(self):
        try:
            sig = inspect.signature(self.fn)
            return sig
        except (ValueError, TypeError):
            return inspect.Signature()

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)

    def format_sig(self) -> str:
        parts = []
        try:
            sig = inspect.signature(self.fn)
            for pname, param in sig.parameters.items():
                annotation = ""
                if param.annotation is not inspect.Parameter.empty:
                    ann = str(param.annotation)
                    ann = ann.replace("<class '", "").replace("'>", "")
                    ann = ann.replace("typing.", "")
                    annotation = f": {ann}"
                default = ""
                if param.default is not inspect.Parameter.empty:
                    default = f" = {param.default}"
                parts.append(f"{pname}{annotation}{default}")
        except (ValueError, TypeError):
            pass
        return f"({', '.join(parts)})"

    def short_desc(self) -> str:
        risk_icon = {"low": "", "medium": "⚠️", "high": "⚠️⚠️", "critical": "🚫"}
        icon = risk_icon.get(self.risk_level.value, "")
        perms = f"[{', '.join(sorted(self.permissions))}]" if self.permissions else ""
        return f"{icon} {self.name}{self.format_sig()} — {self.description} {perms}"


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None):
        self._specs: dict[str, ToolSpec] = {}
        if specs:
            for s in specs:
                self._specs[s.name] = s

    def register(self, spec: ToolSpec):
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def names(self) -> list[str]:
        return list(self._specs.keys())

    def by_category(self, category: str) -> list[ToolSpec]:
        return [s for s in self._specs.values() if s.category == category]

    def by_risk(self, max_risk: RiskLevel) -> list[ToolSpec]:
        levels = list(RiskLevel)
        max_idx = levels.index(max_risk)
        return [s for s in self._specs.values() if levels.index(s.risk_level) <= max_idx]

    def by_permissions(self, require_all: set[str]) -> list[ToolSpec]:
        return [s for s in self._specs.values() if s.permissions and require_all.issubset(s.permissions)]

    def to_callables(self) -> list[Callable]:
        return list(self._specs.values())

    def describe_all(self) -> str:
        return "\n".join(f"- {s.short_desc()}" for s in self._specs.values())

    def __len__(self):
        return len(self._specs)

    def __contains__(self, name: str):
        return name in self._specs
