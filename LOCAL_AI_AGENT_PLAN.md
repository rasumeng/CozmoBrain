# Local AI Agent on RTX 4060 (8GB VRAM)

## Hardware Constraints

| Spec | Value |
|------|-------|
| GPU | RTX 4060, 8GB VRAM |
| Max Model Size | 7B–9B params (Q4_K_M quant) |
| Target VRAM Usage | 6–7GB model + 1–2GB context/safety |
| Target Speed | 40–60 tokens/sec |

---

## 1. Model Selection

### Primary: Ornith-1.0-9B (Q4_K_M)

- Self-scaffolding RL model built specifically for agentic coding
- **43.1 Terminal-Bench 2.1, 69.4 SWE-Bench Verified** — crushes Qwen2.5-Coder at coding tasks
- Fits ~6GB VRAM with full GPU offload, leaves room for 262K context
- MIT license, no regional restrictions
- Available on Ollama: `ollama pull ornith:9b`

### Alternatives

- **Qwen2.5-Coder 7B** — Good general-purpose coding, weaker on agentic tasks
- **Ornith-1.0-35B MoE** — 3B active params/token, fast but needs 24GB card (future upgrade)

### Runtime

- **Ollama** with llama.cpp backend
- Enable full GPU offload: `-ngl 99`
- Quantization: Q4_K_M (balance of speed and quality)
- Model loading: ~5s cold start

---

## 2. Expandability Layer: Model Context Protocol (MCP)

MCP separates the agent from tools. Plug in pre-built servers instead of writing custom integrations.

### Architecture

- **Agent = MCP Host** (Python or TypeScript SDK)
- **Tools = MCP Servers** (run as separate processes)
- Communication via stdio or SSE transport

### Essential MCP Servers

| Server | Purpose | Notes |
|--------|---------|-------|
| Filesystem MCP | Read/write files in a directory | Replicates Claude's project awareness |
| SearXNG MCP | Web search | Self-hosted via Docker, free, privacy-focused, no API keys |
| Git MCP | Clone, commit, diff, log | Direct repo interaction |
| SQLite MCP | Database queries | Lightweight, no external DB needed |
| Postgres MCP | If needed later | For structured data workloads |

### Why SearXNG over Brave/Tavily

- No API keys required
- No usage limits
- Self-contained Docker container
- Privacy-respecting

---

## 3. Native Tools (Must Build)

These run locally and replicate Claude's core utility.

### A. Sandboxed Code Execution (Critical)

**Goal**: Agent can run Python safely without host system access.

| Component | Choice |
|-----------|--------|
| Sandbox Runtime | Docker containers or Pyodide (WebAssembly) |
| Library | `llm-sandbox` or `localsandbox` |
| Tool Signature | `execute_python(code: str) -> str` |
| Behavior | Spin up ephemeral container → run code → capture stdout/images → return result → destroy container |
| Security | No host network access, no private file access, temp package installs allowed |

**Implementation Notes**:
- Docker mode preferred for full isolation
- Pyodide fallback for lighter weight (no Docker dependency)
- Output captured as text or base64-encoded images
- Timeout on execution (e.g., 30s) to prevent runaway code

### B. Web Fetch & Scraping

**Goal**: Convert URLs to clean text/markdown for the LLM.

| Component | Choice |
|-----------|--------|
| HTTP Client | `requests` or `httpx` |
| Content Extraction | `trafilatura` or `readability-lxml` |
| Tool Signature | `fetch_url(url: str, format: str = "markdown") -> str` |
| Output | Clean markdown, stripped of ads/CSS/JS |

**Why**: Raw HTML is massive. Clean text saves context window space dramatically.

### C. Knowledge Base (OKF Format)

**Goal**: Agent maintains a structured knowledge base using Google's Open Knowledge Format (OKF v0.1).

OKF = directory of markdown files with YAML frontmatter. Each file = one concept with a required `type` field. Reserved files: `index.md` (directory listing), `log.md` (change history). Cross-links via standard markdown. No SDK needed — just files.

| Component | Choice |
|-----------|--------|
| Format | OKF v0.1 (markdown + YAML frontmatter) |
| Tool Signature | `write_file(path: str, content: str, type: str) -> str` |
| Knowledge Root | `./knowledge/` directory |
| Security | Reject any path traversal (`../`, absolute paths outside knowledge root) |
| Validation | Auto-add frontmatter with `type` field if missing |
| Obsidian | Open `./knowledge/` as Obsidian vault — native compatibility |

**Knowledge Structure**:
```
knowledge/
├── index.md                    # Root index, lists all categories
├── conversations/
│   ├── index.md
│   └── 2026-07-06.md          # Daily conversation logs
├── learnings/
│   ├── index.md
│   └── python-patterns.md     # Things the agent has learned
├── projects/
│   ├── index.md
│   └── cozmobrain.md          # Project-specific knowledge
└── reference/
    ├── index.md
    └── tools.md               # Reference material
```

**Frontmatter Format**:
```yaml
---
type: Conversation | Learning | Project | Reference
title: Human-readable title
description: One-line summary
tags: [tag1, tag2]
timestamp: 2026-07-06T14:30:00Z
---
```

### D. Artifact/File Generation

**Goal**: Agent creates files in a sandboxed workspace (separate from knowledge base).

| Component | Choice |
|-----------|--------|
| Tool Signature | `write_file(path: str, content: str) -> str` |
| Workspace | Hardcoded directory: `./workspace/` |
| Security | Reject any path traversal (`../`, absolute paths outside workspace) |
| Validation | Use `os.path.realpath()` to resolve and check prefix match |

---

## 4. Orchestrator: Agent Framework

### Primary: Pydantic AI

FastAPI-inspired agent framework. Type-safe, minimal boilerplate, built-in MCP support.

**Why Pydantic AI over custom ReAct:**
- Type-safe tool definitions with Pydantic models
- Built-in MCP server integration
- Dependency injection for sharing state across tools
- Structured output validation with auto-retry
- Model-agnostic (works with Ollama)
- Same philosophy as custom loop, but production-ready

```python
# Pydantic AI agent example
from pydantic_ai import Agent

agent = Agent(
    "ollama:ornith:9b",
    system_prompt="You are a local AI assistant with tools.",
    tools=[execute_python, fetch_url, write_knowledge],
)

result = agent.run_sync("Write a Python script to sort a list")
print(result.output)
```

### Avoid Initially

- **LangChain / LangGraph** — Heavy overhead, unnecessary abstractions
- **AutoGen / CrewAI** — Multi-agent frameworks spawn extra model instances, blow up VRAM usage
- **CrewAI** — Multi-agent overkill for single-model setup

---

## 5. Context Window Management (The Real Bottleneck)

On 8GB VRAM, context overflow kills performance. This is the hardest engineering problem.

### Rules

| Rule | Detail |
|------|--------|
| Aggressive Summarization | Every tool response (especially web search) must be summarized before re-injection |
| Truncation | Hard-truncate search results to top N characters |
| Sliding Window | Drop oldest messages when history exceeds threshold |
| Tool Response Budget | Cap each tool response at ~500 tokens max |
| Structured Output | Force JSON output to minimize token waste |

### Implementation Strategy

```
Tool Response → Summarizer (lightweight) → Truncated Summary → Inject into Context
```

- Use a separate small model or regex-based summarizer for tool outputs
- Or: truncate to first N sentences + last M sentences
- Monitor VRAM usage; trigger compaction when approaching limit

### OKF Progressive Disclosure

OKF index files (`index.md`) enable smart context loading:

```
1. Agent receives question about "Python patterns"
2. Reads knowledge/index.md → sees categories (conversations, learnings, projects, reference)
3. Reads knowledge/learnings/index.md → sees "python-patterns.md"
4. Reads knowledge/learnings/python-patterns.md → gets full content
```

This avoids loading the entire knowledge base into context. Agent only reads what it needs, guided by index files at each level.

---

## 6. System Prompt Template

```
You are a local AI assistant running on an RTX 4060.

Rules:
- Always output valid JSON for tool calls.
- Tool call format: {"tool": "tool_name", "args": {...}}
- If a tool fails, analyze the error and retry or explain the limitation.
- Never attempt to access files outside the workspace directory.
- Keep responses concise. You have limited context space.
- When fetching web content, summarize key findings, not full text.
- When writing to the knowledge base, use OKF format (YAML frontmatter with type field).
- Use knowledge index files for progressive disclosure — don't load everything at once.

Available tools: [list tools here]
```

---

## 7. Implementation Phases

### Phase 1: Foundation

- [x] Install Ollama, pull Ornith-1.0-9B Q4_K_M (`ollama pull ornith:9b`)
- [ ] Verify GPU offload working (`-ngl 99`)
- [ ] Benchmark token speed (target: 40+ tok/s)

### Phase 2: Core Agent

- [x] Set up Python project with dependencies
- [ ] Implement Pydantic AI agent with Ollama provider
- [ ] Register native tools (execute_python, fetch_url, write_knowledge)
- [ ] Create system prompt with tool schema
- [x] Set up OKF knowledge base structure
- [ ] Implement OKF read/write tools as Pydantic AI tools

### Phase 3: Tools

- [ ] Implement `execute_python` with Docker sandbox
- [ ] Implement `fetch_url` with trafilatura
- [ ] Implement `write_file` with path validation
- [ ] Implement `read_knowledge` with OKF index navigation
- [ ] Implement `write_knowledge` with auto frontmatter
- [ ] Connect SearXNG MCP for web search

### Phase 4: Integration

- [ ] Connect Filesystem MCP server
- [ ] Connect Git MCP server
- [ ] Wire all tools into orchestrator
- [ ] Implement context window management

### Phase 5: Polish

- [ ] Add error handling and retry logic
- [ ] Implement summarization for tool responses
- [ ] Add logging and debug mode
- [ ] Test end-to-end workflows

---

## 8. Project Structure

```
cozmobrain/
├── agent/
│   ├── __init__.py
│   ├── main.py              # Entry point, Pydantic AI agent
│   ├── tools.py             # Tool definitions (Pydantic models)
│   ├── knowledge.py         # OKF knowledge base tools
│   ├── context.py           # Context window management
│   └── prompts.py           # System prompts
├── docker/
│   └── sandbox.Dockerfile   # Sandbox container
├── knowledge/               # OKF knowledge base (Obsidian vault)
│   ├── index.md
│   ├── conversations/
│   │   └── index.md
│   ├── learnings/
│   │   └── index.md
│   ├── projects/
│   │   └── index.md
│   └── reference/
│       └── index.md
├── workspace/               # Agent file workspace (code output)
├── requirements.txt
└── config.yaml              # Model, tool, server config
```

---

## 9. Dependencies

```
# Core
pydantic-ai         # Agent framework (FastAPI-inspired)
ollama              # Local LLM runtime
pydantic            # Data validation

# Tools
docker              # Sandbox code execution
trafilatura         # Web content extraction
httpx               # HTTP client

# MCP (built into pydantic-ai, but explicit for servers)
mcp                 # MCP Python SDK

# Knowledge (OKF)
pyyaml              # YAML frontmatter parsing
python-frontmatter  # OKF frontmatter extraction (optional, for convenience)

# Utilities
rich                # Terminal output
```

---

## 10. Performance Targets

| Metric | Target |
|--------|--------|
| Model Load Time | < 5s (Ornith-9B cold start) |
| Tokens/sec (generation) | 40–60 |
| Max Tool Calls Before Context Full | 8–12 |
| Tool Response Truncation | 500 tokens max |
| Max History Messages | 20 (then summarize/compact) |
| Docker Sandbox Startup | < 2s |
| Docker Sandbox Teardown | < 1s |
| Context Window (Ornith) | 262K tokens |

---

## 11. Security Checklist

- [ ] Path traversal prevention on all file tools
- [ ] Docker sandbox: no host network, no volume mounts to sensitive dirs
- [ ] Web fetch: timeout on all HTTP requests
- [ ] No secrets/keys in prompts or tool responses
- [ ] Workspace directory is the only writable location
- [ ] Code execution has a hard timeout (30s)

---

## 12. Future Enhancements

- **Micro-agents** — Split into specialized models (coder, researcher, writer) with routing
- **Voice input/output** — Whisper for STT, Piper for TTS
- **Image understanding** — Add vision model (e.g., LLaVA) for multimodal
- **Obsidian sync** — Git sync between knowledge base and Obsidian vault across devices
- **OKF validation** — Auto-validate knowledge base against OKF v0.1 spec
- **Plugin system** — Dynamic MCP server loading at runtime
- **Web UI** — Gradio or Streamlit interface
- **Upgrade to Ornith-35B MoE** — When 24GB card acquired
