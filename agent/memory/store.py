"""LanceDB vector store for memory persistence."""

from pathlib import Path
from typing import Any
import numpy as np

import lancedb
import pyarrow as pa

from .types import MemoryEntry


TABLE_NAME = "memories"


class LanceMemoryStore:
    """Persistent vector store using LanceDB."""

    def __init__(self, db_path: str = "./memory_store", embed_dim: int = 384):
        self.db_path = str(Path(db_path).resolve())
        self.embed_dim = embed_dim
        self._db = lancedb.connect(self.db_path)
        self._tbl = self._init_table()

    def _init_table(self):
        try:
            tbl = self._db.open_table(TABLE_NAME)
            tbl.count_rows()
            return tbl
        except Exception:
            vec_type = pa.list_(pa.float32(), self.embed_dim)
            schema = pa.schema([
                pa.field("id", pa.utf8()),
                pa.field("vector", vec_type),
                pa.field("content", pa.utf8()),
                pa.field("path", pa.utf8()),
                pa.field("memory_type", pa.utf8()),
                pa.field("tags", pa.list_(pa.utf8())),
                pa.field("timestamp", pa.utf8()),
                pa.field("summary", pa.utf8()),
                pa.field("importance", pa.float32()),
            ])
            return self._db.create_table(TABLE_NAME, schema=schema)

    def add(self, entries: list[MemoryEntry]):
        """Store memory entries."""
        if not entries:
            return

        data = []
        import uuid

        for entry in entries:
            vec = entry.embedding
            if vec is None:
                vec = np.zeros(self.embed_dim, dtype=np.float32)
            data.append({
                "id": str(uuid.uuid4()),
                "vector": np.array(vec, dtype=np.float32).tolist(),
                "content": entry.content,
                "path": entry.path,
                "memory_type": entry.memory_type.value,
                "tags": entry.tags,
                "timestamp": entry.timestamp,
                "summary": entry.summary,
                "importance": entry.importance,
            })

        self._tbl.add(data)

    def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Search for nearest neighbors by vector similarity."""
        vec = np.array(query_vector, dtype=np.float32)
        try:
            results = (
                self._tbl.search(vec)
                .limit(limit)
                .to_list()
            )
            for r in results:
                r["_score"] = r.get("_distance", 1.0)
            return results
        except Exception:
            return []

    def search_by_text(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Full-text search on content/summary columns."""
        try:
            results = (
                self._tbl.search(query, query_type="fts")
                .limit(limit)
                .to_list()
            )
            return results
        except Exception:
            return []

    def delete(self, ids: list[str]):
        """Delete entries by ID."""
        if not ids:
            return
        id_list = ", ".join(f'"{i}"' for i in ids)
        self._tbl.delete(f"id IN ({id_list})")

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get most recent memory entries."""
        try:
            return (
                self._tbl.query()
                .order_by("timestamp", asc=False)
                .limit(limit)
                .to_list()
            )
        except Exception:
            return []

    def count(self) -> int:
        try:
            return self._tbl.count_rows()
        except Exception:
            return 0
