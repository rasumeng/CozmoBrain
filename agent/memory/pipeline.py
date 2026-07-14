"""Background memory pipeline: summarize → extract → embed → store."""

import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .embed import MemoryEmbedder
from .store import LanceMemoryStore
from .types import MemoryEntry, MemoryType


KNOWLEDGE = Path("./knowledge").resolve()
CONVERSATIONS_DIR = KNOWLEDGE / "conversations"
LEARNINGS_DIR = KNOWLEDGE / "learnings"


def _ensure_dirs():
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_path(base: Path, name: str) -> Path:
    """Safely resolve a path within base directory."""
    target = (base / name).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise PermissionError(f"Path traversal blocked: {name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_okf(path: Path, content: str, type: str, title: str, tags: list[str]):
    import yaml
    frontmatter = {
        "type": type,
        "title": title,
        "tags": tags,
        "timestamp": _now(),
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.dump(frontmatter, f, default_flow_style=False, allow_unicode=True)
        f.write("---\n\n")
        f.write(content)


class MemoryPipeline:
    """Background pipeline: processes conversation turns into persistent memory."""

    def __init__(
        self,
        store: LanceMemoryStore,
        embedder: MemoryEmbedder,
        auto_knowledge: bool = True,
    ):
        self.store = store
        self.embedder = embedder
        self.auto_knowledge = auto_knowledge
        _ensure_dirs()

    async def after_turn(
        self,
        user_input: str,
        agent_response: str,
        extra_ctx: dict[str, Any] | None = None,
    ):
        """Process a completed conversation turn. Non-blocking friendly."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._process, user_input, agent_response, extra_ctx)

    def _process(
        self,
        user_input: str,
        agent_response: str,
        extra_ctx: dict[str, Any] | None = None,
    ):
        """Synchronous processing (runs in thread pool to avoid blocking REPL)."""
        conversation = f"User: {user_input}\nAssistant: {agent_response}"
        summary = self._summarize(conversation)
        today = _today()

        # 1. Save conversation to knowledge file
        convo_path = f"conversations/{today}.md"
        tags = ["conversation"]
        if extra_ctx and extra_ctx.get("had_plan"):
            tags.append("planned")

        existing = ""
        full_path = KNOWLEDGE / convo_path
        if full_path.exists():
            existing_content = full_path.read_text(encoding="utf-8")
            existing = existing_content.split("---\n\n", 1)[-1] if "---\n\n" in existing_content else existing_content

        content = existing + f"\n\n### [{_now()}]\n{user_input}\n\n{agent_response}\n"
        _write_okf(
            _safe_path(KNOWLEDGE, convo_path),
            content.strip(),
            type="Conversation",
            title=f"Conversation {today}",
            tags=tags,
        )

        # Embed and store conversation in vector DB
        convo_entry = MemoryEntry(
            content=content.strip(),
            path=convo_path,
            memory_type=MemoryType.EPISODIC,
            tags=tags,
            summary=summary,
            importance=0.6,
            embedding=self.embedder.encode_one(conversation),
        )
        self.store.add([convo_entry])

        # 2. Extract and save facts/learnings
        if self.auto_knowledge:
            facts = self._extract_facts(user_input, agent_response)
            for fact in facts:
                learning_entry = MemoryEntry(
                    content=fact["content"],
                    path=fact["path"],
                    memory_type=MemoryType.SEMANTIC,
                    tags=fact.get("tags", ["auto-extracted"]),
                    summary=fact["content"][:120],
                    importance=0.5,
                    embedding=self.embedder.encode_one(fact["content"]),
                )
                self.store.add([learning_entry])

    def _summarize(self, conversation: str, max_chars: int = 300) -> str:
        """Simple extractive summary: first meaningful lines."""
        cleaned = re.sub(r"[#*_`\[\]]", "", conversation)
        lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
        summary = " | ".join(lines[:4])
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "..."
        return summary

    def _extract_facts(
        self, user_input: str, agent_response: str
    ) -> list[dict[str, Any]]:
        """Extract factual statements from a conversation turn.

        Uses heuristics: finds lines with substantive content
        about specific topics, technologies, concepts.
        """
        facts = []
        lines = agent_response.split("\n")

        for line in lines:
            line = line.strip()
            if not line or len(line) < 40:
                continue
            if line.startswith(("#", "- ", "* ", "1.", ">", "```")):
                continue
            if "?" in line or "!" in line:
                continue

            topics = re.findall(
                r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b", line
            )
            if topics:
                topic = topics[0].lower().replace(" ", "-")
                safe_title = re.sub(r"[^\w\s-]", "", topic[:40]).strip() or "note"
                path = f"learnings/{safe_title}.md"

                facts.append({
                    "content": line.strip(),
                    "path": path,
                    "tags": ["auto-extracted", topic[:20].lower()],
                })

        return facts[:5]
