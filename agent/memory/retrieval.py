"""Memory retrieval strategies: vector + keyword hybrid search."""

from datetime import datetime, timezone
from typing import Any

from .embed import MemoryEmbedder
from .store import LanceMemoryStore
from .types import MemoryEntry


class MemoryRetriever:
    """Retrieves relevant memories for context injection.

    Strategies:
    - Primary: vector search (semantic similarity)
    - Fallback: keyword full-text search
    - Scoring: importance boost + recency decay
    """

    def __init__(
        self,
        store: LanceMemoryStore,
        embedder: MemoryEmbedder,
        max_auto_inject: int = 2,
    ):
        self.store = store
        self.embedder = embedder
        self.max_auto_inject = max_auto_inject

    def search(self, query: str, top_k: int = 5, min_score: float = 0.3) -> list[dict[str, Any]]:
        """Multi-strategy memory search. Returns scored results sorted by relevance."""
        hits: dict[str, dict[str, Any]] = {}

        # Strategy 1: vector search
        query_vec = self.embedder.encode_one(query)
        vec_results = self.store.search(query_vec, limit=top_k * 2)
        for r in vec_results:
            r["_score"] = self._compute_score(r, from_vector=True)
            hits[r.get("id", "")] = r

        # Strategy 2: full-text fallback (catch what vector misses)
        text_results = self.store.search_by_text(query, limit=top_k)
        for r in text_results:
            rid = r.get("id", "")
            if rid not in hits:
                r["_score"] = self._compute_score(r, from_vector=False)
                hits[rid] = r

        # Sort by score descending
        sorted_hits = sorted(hits.values(), key=lambda x: x["_score"], reverse=True)

        # Filter low scores
        sorted_hits = [h for h in sorted_hits if h["_score"] >= min_score]

        return sorted_hits[:top_k]

    def get_auto_inject(self, query: str) -> list[dict[str, Any]]:
        """Get top memories for automatic injection into system prompt."""
        return self.search(query, top_k=self.max_auto_inject)

    def _compute_score(self, result: dict, from_vector: bool) -> float:
        """Compute relevance score: vector distance + importance + recency."""
        base = 1.0

        if from_vector:
            distance = result.get("_distance", 0.5)
            base = 1.0 - min(distance, 1.0)
        else:
            base = 0.5

        importance = result.get("importance", 0.5)
        base = base * 0.6 + importance * 0.4

        timestamp = result.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_ago = (now - dt).total_seconds() / 86400
                decay = max(0.3, 1.0 - (days_ago / 30))
                base *= decay
            except ValueError:
                pass

        return round(base, 4)

    def format_for_prompt(self, memories: list[dict[str, Any]]) -> str:
        """Format memories for injection into system prompt."""
        if not memories:
            return ""

        lines = ["## Relevant Memories", ""]
        for i, mem in enumerate(memories, 1):
            summary = mem.get("summary", mem.get("content", "")[:100])
            path = mem.get("path", "")
            mem_type = mem.get("memory_type", "note")
            tags = mem.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            path_str = f" ({path})" if path else ""
            lines.append(f"{i}. [{mem_type}]{path_str}{tag_str}")
            lines.append(f"   {summary}")
            lines.append("")

        return "\n".join(lines)
