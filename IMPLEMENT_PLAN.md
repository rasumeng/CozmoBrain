# CozmoBrain → Cozmo: Transition Plan

100% asset transfer: every CozmoBrain file, feature, and config setting
mapped to the correct location in the main [rasumeng/Cozmo](https://github.com/rasumeng/Cozmo) repo.

---

## Asset Inventory (CozmoBrain)

```
CozmoBrain/
├── agent/
│   ├── __init__.py      # Exports: create_agent, tools, MCPHost, build_system_prompt
│   ├── main.py           # REPL: config → tools → router → agent → stream → loop
│   ├── llm.py            # create_agent(): pydantic_ai.Agent factory
│   ├── tools.py          # 6 native tools + web_search with date stamp
│   ├── router.py         # ToolRouter: keyword → domain priority → LLM fallback
│   ├── mcp_host.py       # MCPHost: stdio sessions, tool wrappers, connect/disconnect
│   ├── context.py        # trim_history, truncate_tool_responses, compact_messages
│   └── prompts.py        # BASE_PROMPT + build_system_prompt() with date injection
├── config.yaml           # Model, MCP servers, context, workspace config
├── rules.yaml            # 10 routing categories with keywords/priorities
└── IMPLEMENT_PLAN.md     # ← this file

# Runtime data (migrate separately):
#   workspace/           # Created files
#   knowledge/           # Saved knowledge docs
```

---

## Target Mapping (rasumeng/Cozmo)

| CozmoBrain | → | Cozmo Repo | File Status |
|---|---|---|---|
| `agent/mcp_host.py` | → | `cozmo/core/mcp_host.py` | **NEW** |
| `agent/router.py` | → | `cozmo/core/router.py` | **NEW** |
| `agent/context.py` | → | `cozmo/core/context.py` | **NEW** |
| `agent/prompts.py` | → | `cozmo/core/prompts.py` | **NEW** |
| `agent/__init__.py` | → | `cozmo/core/__init__.py` | **EDIT** (add exports) |
| `agent/llm.py` | → | `cozmo/core/llm.py` | **EDIT** (pydantic_ai path) |
| `agent/tools.py` | → | `cozmo/tools/` | **MERGE** (scatter to existing files) |
| `agent/main.py` (REPL) | → | `cozmo/cli.py` | **EDIT** (add `cozmo mcp` subcommand) |
| `config.yaml` | → | `cozmo/config.py` | **EDIT** (merge MCP + context keys) |
| `rules.yaml` | → | `cozmo/core/router.py` | **INLINE** (data embedded in class) |
| Custom agents (in `rules.yaml`) | → | `cozmo/core/agent_registry.py` | **EDIT** (register new agents) |

### Cozmo Repo files that already exist (no Brain counterpart — keep as-is)

| File | Purpose | Keep? |
|---|---|---|
| `cozmo/core/orchestrator.py` | Heuristic + LLM classifier → model routing | Keep — Brain router sits alongside |
| `cozmo/core/agent.py` | Base agent with tool loop, `<tool>` JSON | Keep — Brain agent integrates with it |
| `cozmo/core/agent_registry.py` | Multi-agent create/list/switch | Keep — Brain agents register here |
| `cozmo/core/permissions.py` | Pattern-based tool gating | Keep — unchanged |
| `cozmo/core/code_agent.py` | Build agent for code tasks | Keep — unchanged |
| `cozmo/core/plan_agent.py` | Read-only plan agent | Keep — unchanged |
| `cozmo/memory/` | ChromaDB memory + summarization | Keep — unchanged |
| `cozmo/tools/` (existing) | Calculator, file_ops, code_ops, web_search, desktop, telegram | Keep — Brain tools merge into these |
| `cozmo/tui/` | Textual TUI with Chat/Collab/Code panels | Keep — wire to Brain events later |
| `cozmo/config.py` | TOML loader, DEFAULT_CONFIG | Keep — extend schema |
| `cozmo/cli.py` | argparse commands (run, code, tui, config) | Keep — add `mcp` subcommand |

---

## Step-by-Step Migration

### STEP 1: `cozmo/core/mcp_host.py` — NEW file


Create `cozmo/core/mcp_host.py` by copying `agent/mcp_host.py` verbatim (98 lines).

**Integration:**
- Orchestrator (`cozmo/core/orchestrator.py`) can import MCPHost and initialize it during startup
- Add `mcp_servers` to config.toml schema (see STEP 6)
- MCP tool wrappers should be injected into the tool registry via `ToolRegistry.register()`

**No dependencies on other CozmoBrain files.** Standalone.

**Imports needed in `cozmo/core/mcp_host.py`:**
- `from mcp import ClientSession, StdioServerParameters, types` → add to `pyproject.toml`/`requirements.txt`
- `from mcp.client.stdio import stdio_client` → same

**Config key for `~/.cozmo/config.toml`:**
```toml
[mcp]
servers = { filesystem = { command = "npx", args = ["-y", "@modelcontextprotocol/server-filesystem", "./workspace"] } }
```

---

### STEP 2: `cozmo/core/router.py` — NEW file

Copy `agent/router.py` (173 lines) as `cozmo/core/router.py`.

**Changes needed from Brain version:**

1. **Replace YAML loading with direct dict** — Cozmo uses TOML config, not YAML. Inline the 10 routing categories as a class constant instead of loading `rules.yaml`:

```python
class ToolRouter:
    CATEGORIES = {
        "git_status": {"domain": "git", "priority": 100, "keywords": [...], "tools": [...]},
        "git_diff": {...},
        # ... all 10 categories embedded ...
    }
```

2. **Wrap LLM fallback** around Cozmo's existing `OllamaModel` instead of raw HTTP calls. Replace the `_llm_classify` method's direct `urllib.request` to Ollama with:

```python
from .llm import OllamaModel

# In __init__:
self.classifier = OllamaModel(llm_model)

# In _llm_classify:
response = self.classifier.invoke(prompt_text)
```

**Integration:**
- Orchestrator creates `ToolRouter` alongside the existing classifier
- `ToolRouter.get_tools()` feeds filtered tool list into `Agent`'s tool registry
- Cozmo's existing `Orchestrator.run()` can call `self.router.get_tools(query, all_tools)` to restrict which tools the agent sees

---

### STEP 3: `cozmo/core/context.py` — NEW file

Copy `agent/context.py` (58 lines) as `cozmo/core/context.py`.

**No changes needed.** All functions (`trim_history`, `truncate_tool_responses`, `compact_messages`, `estimate_tokens`) are self-contained utility functions.

**Integration:**
- `MemoryManager` can call `compact_messages()` before summarization
- `Agent.run()` can call `trim_history()` before each LLM call
- `Orchestrator.run()` can call `truncate_tool_responses()` on tool outputs

---

### STEP 4: `cozmo/core/prompts.py` — NEW file

Copy `agent/prompts.py` (42 lines) as `cozmo/core/prompts.py`.

**Changes needed:**
- `build_system_prompt()` signature stays the same
- Replace `tools_module` references with Cozmo's `ToolRegistry` pattern
- The date injection logic (key improvement) stays — Cozmo agents benefit from knowing today's date

**Integration:**
- Cozmo's `Agent.__init__()` in `cozmo/core/agent.py` can call `build_system_prompt(tools, workspace, git_repo)` to generate system prompt
- Already compatible with Cozmo's per-agent system prompt override pattern

---

### STEP 5: Edit existing files

#### 5a. `cozmo/core/__init__.py`

Add exports:

```python
from .mcp_host import MCPHost
from .router import ToolRouter
from .context import trim_history, truncate_tool_responses, compact_messages
from .prompts import build_system_prompt
```

#### 5b. `cozmo/core/llm.py`

Cozmo's `OllamaModel` uses `langchain_ollama` and `langchain_core`. Keep this as-is.

**Add** a second, simpler wrapper `StatelessLLM` alongside it for structured JSON output (needed by ToolRouter and Planner):

```python
class StatelessLLM:
    """Simple generate() wrapper. No history, no memory. Used by ToolRouter + Planner."""

    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def generate(self, prompt: str, system_prompt: str | None = None, structured: bool = False) -> str:
        """One-shot generate. structured=True adds JSON constraint."""
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatOllama(model=self.model_name, base_url=self.base_url, temperature=0,
                         format="json" if structured else None)
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        return llm.invoke(messages).content
```

#### 5c. `cozmo/tools/` — merge Brain's unique tools

| Brain Tool | → | Cozmo Target | Action |
|---|---|---|---|
| `execute_python` | → | `cozmo/tools/code_ops.py` | Add `execute_python(code)` function |
| `fetch_url` | → | `cozmo/tools/web_search.py` | Add `fetch_url(url)` function |
| `web_search` (with date stamp) | → | `cozmo/tools/web_search.py` | **Replace** existing `web_search` |
| `write_file` | → | `cozmo/tools/file_ops.py` | Add `write_file(path, content)` |
| `read_knowledge` | → | `cozmo/tools/file_ops.py` | Add `read_knowledge(path)` |
| `write_knowledge` (with OKF frontmatter) | → | `cozmo/tools/file_ops.py` | Add `write_knowledge(path, content, ...)` |

**Why merge, not copy:** Cozmo already has tool decorators (`@register_tool()`), a `ToolRegistry`, and permission gates in `cozmo/tools/__init__.py`. Brain tools need the `@register_tool()` decorator to appear in Cozmo's tool list.

**Key feature to preserve:** The `write_knowledge()` function's OKF (Obsidian Knowledge Format) frontmatter with `type`, `title`, `tags`, `timestamp` fields. Cozmo has no equivalent — this adds value.

#### 5d. `cozmo/cli.py` — add `cozmo mcp` subcommand

Add a new subcommand to `cozmo/cli.py` for MCP server management:

```python
mcp_parser = sub.add_parser("mcp", help="Manage MCP server connections")
mcp_parser.add_argument("action", choices=["connect", "list", "disconnect"], nargs="?", default="connect")
mcp_parser.add_argument("--server", help="Specific server name")
```

Implementation:

```python
def run_mcp(cfg: dict, action: str, server: str | None):
    """MCP subcommand: connect/list/disconnect."""
    from .core.mcp_host import MCPHost
    import asyncio

    async def _run():
        mcp = MCPHost()
        if action == "connect":
            await mcp.connect()
            wrappers = await mcp.get_tool_wrappers()
            print(f"[mcp] Got {len(wrappers)} tool wrappers")
            # Inject into ToolRegistry
            from .tools import registry
            for w in wrappers:
                registry.register(w.__name__, w)
        elif action == "list":
            for name, _ in mcp.sessions:
                print(f"  {name}")
        elif action == "disconnect":
            await mcp.disconnect()

    asyncio.run(_run())
```

**Integration with Orchestrator:** MCP initialization should happen when Orchestrator starts. Add to `Orchestrator.__init__()`:

```python
self.mcp = MCPHost()
asyncio.create_task(self._init_mcp())
```

---

### STEP 6: Config migration — `config.yaml` → `~/.cozmo/config.toml`

| Brain Key | → | Cozmo TOML Key | Notes |
|---|---|---|---|
| `model` | → | `models.coder` (or `research`) | Brain uses qwen3:8b — map to coder or research model |
| `max_tokens` | → | (new) `models.max_tokens = 2048` | Add to `ModelConfig` |
| `router_model` | → | `models.classifier` | Cozmo already has this |
| `router_llm` | → | (new) `router.use_llm = false` | Add new `[router]` section |
| `workspace` | → | (new) `workspace.path = "./workspace"` | Add new `[workspace]` section |
| `knowledge` | → | (new) `workspace.knowledge = "./knowledge"` | |
| `git_repo` | → | (new) `workspace.git_repo = ""` | |
| `searxng_url` | → | `search.url = "http://localhost:8080"` | Add new `[search]` section |
| `mcp_servers` | → | `[mcp.servers]` (TOML table) | Add new `[mcp]` section |
| `max_history` | → | `context.max_history = 20` | Add new `[context]` section |
| `tool_response_max_chars` | → | `context.tool_response_max_chars = 2000` | |

**Cozmo config.py changes needed:**

Add new config sections to `DEFAULT_CONFIG` in `cozmo/config.py`:

```python
DEFAULT_CONFIG = {
    # ... existing keys ...
    "router": {
        "use_llm": False,
    },
    "workspace": {
        "path": "./workspace",
        "knowledge": "./knowledge",
        "git_repo": "",
    },
    "search": {
        "url": "http://localhost:8080",
    },
    "mcp": {
        "servers": {},
    },
    "context": {
        "max_history": 20,
        "tool_response_max_chars": 2000,
    },
}
```

---

### STEP 7: Dependency merge — `requirements.txt`

| Package | Needed By | In Cozmo Already? |
|---|---|---|
| `mcp` | MCPHost | **NO** — add |
| `pydantic-ai` | Brain's llm.py | **NO** (Cozmo uses langchain) |
| `pyyaml` | Brain's router.py + config | **NO** (Cozmo uses TOML) — only needed if porting router.py as-is |

**Action:** Add `mcp>=1.0` to `pyproject.toml` dependencies. `pydantic-ai` is NOT needed — Cozmo uses LangChain, and the Brain's Planner/Runtime (Phases 1-3 of future work) will use `StatelessLLM` (see STEP 5b), which wraps LangChain too.

`pyyaml` is NOT needed — the router's `rules.yaml` is inlined as a Python dict (per STEP 2).

---

## Integration Architecture (Post-Migration)

```
Cozmo CLI (cozmo run / code / tui / mcp)
         │
    Orchestrator
     ├── Heuristic pre-filter (unchanged)
     ├── LLM classifier → model router (unchanged)
     ├── NEW: ToolRouter (from Brain) → keyword/domain priority → filtered tool list
     └── MemoryManager (unchanged)
            │
         Agent (updated: uses prompts.py + context.py)
            │
      ToolRegistry (extended: MCP tools injected)
            │
     ┌──────┴──────┐
     │              │
  Native tools   MCPHost → external MCP servers
  (unchanged)    (NEW from Brain)
```

---

## Files NOT to Port

These CozmoBrain files serve the isolated prototype but have **no place** in the main repo:

| File | Reason |
|---|---|
| `agent/main.py` | REPL logic absorbed into `cozmo/cli.py`'s `code` and `mcp` subcommands |
| `agent/__init__.py` | Exports moved into `cozmo/core/__init__.py` |
| `config.yaml` | Settings merged into `~/.cozmo/config.toml` (see STEP 6) |
| `rules.yaml` | Data inlined into `ToolRouter.CATEGORIES` class constant (see STEP 2) |
| `IMPLEMENT_PLAN.md` | This file — stays in CozmoBrain archive, not ported |

---

## What Comes Next (After Port)

Once migrated, build the remaining agentic capabilities from the original plan directly inside the main Cozmo repo:

| Phase | What | Where in Cozmo |
|---|---|---|
| 1 | Event system (EventBus, AgentEvent, EventType) | `cozmo/core/events.py` |
| 2 | Planner loop (Plan → Execute → Observe → Respond) | `cozmo/core/planner.py` |
| 3 | Runtime orchestrator (state machine + lifecycle) | `cozmo/core/runtime.py` |
| 4 | Formal state machine (guards, transitions) | `cozmo/core/state.py` |
| 5 | Memory system (ChromaDB) | Already exists at `cozmo/memory/` |
| 6 | Model router | Already exists at `cozmo/core/orchestrator.py` |
| 7 | Activity feed UI (event-driven) | `cozmo/tui/widgets/activity.py` |
| 8 | Tool registry | Already exists at `cozmo/tools/` |
| 9 | Context manager (smart assembly) | `cozmo/core/context.py` — extend |
| 10 | Config validation | Already exists at `cozmo/config.py` — extend |

---

## Verification Checklist

After migration, confirm these queries work:

- [ ] `cozmo mcp connect` — MCPHost starts, tool wrappers registered
- [ ] `cozmo code "git status"` — ToolRouter filters to git tools only
- [ ] Date-aware prompts — `build_system_prompt()` stamps today's date
- [ ] Context compaction — `compact_messages()` works with Cozmo's message format
- [ ] Web search — `web_search()` returns date-stamped results
- [ ] Knowledge CRUD — `read_knowledge`/`write_knowledge` with OKF frontmatter
- [ ] No Brain files left behind — every component accounted for
