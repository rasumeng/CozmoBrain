CozmoBrain → Hermes-Style Autonomous Agent Architecture Plan
Vision

Transform CozmoBrain from a reactive LLM wrapper into a persistent autonomous cognitive runtime.

The target architecture is inspired by Hermes-style agent systems:

User
 │
 ▼
Runtime Controller
 │
 ▼
Cognitive Loop
 ├── Observe
 ├── Reason
 ├── Plan
 ├── Execute
 ├── Reflect
 ├── Update Memory
 └── Continue

The goal is not simply "better prompting".

The goal is a runtime where CozmoBrain maintains:

persistent state
goals
plans
observations
memory
tool history
self-correction
autonomous background activity

while still remaining user-controlled and transparent.

Current Architecture (Completed Components)
Existing Core
CozmoBrain/
│
├── agent/
│   ├── llm.py
│   ├── tools.py
│   ├── context.py
│   ├── prompts.py
│   ├── state.py
│   ├── reflector.py
│   ├── planner.py
│   ├── orchestrator_model.py
│   ├── orchestrator.py
│   ├── runtime.py
│   ├── events.py
│   ├── mcp_host.py
│   ├── main.py
│   │
│   ├── memory/
│   │   ├── types.py
│   │   ├── embed.py
│   │   ├── store.py
│   │   ├── retrieval.py
│   │   └── pipeline.py
│   │
│   ├── tray/
│   │   ├── tray.py
│   │   ├── scheduler.py
│   │   └── notify.py
│   │
│   ├── voice/
│   ├── integrations/
│   └── __init__.py
│
├── knowledge/
├── memory_store/
└── config.yaml

1. Persistent Agent State

File:

state.py

Status:

✅ Implemented

Purpose:

Provides persistent cognitive state.

Tracks:

current goal
execution status
active plan
current step
observations
events
tools used
failures
scratchpad memory

Current state machine:

IDLE
 |
 THINKING
 |
 PLANNING
 |
 EXECUTING
 |
 REFLECTING
 |
 COMPLETE
 |
 IDLE

Future improvements:

add state transition validation
add event hooks
add persistence versioning
add state migrations
add checkpoint recovery

2. Reflection System

File:

reflector.py

Status:

✅ Implemented

Purpose:

Allows CozmoBrain to analyze failures.

Current capabilities:

classify tool errors
recommend recovery
modify parameters
retry failed actions
detect bad outputs

Current loop:

Tool Call
    |
    ▼
Result
    |
    ▼
Reflector
    |
    ├── success
    |
    ├── retry
    |
    ├── modify parameters
    |
    ├── change strategy
    |
    └── abort

Future improvements:

connect reflector to AgentState (partial: used by PlanExecutor)
store lessons learned
create failure memory
confidence scoring
reflection prompts through LLM

3. Context Management

File:

context.py

Status:

✅ Implemented

Current features:

token estimation
history trimming
tool response truncation
message compaction
state context builder (build_state_context)

Current purpose:

Prevent context overflow.

Future evolution:

Turn into:

ContextManager

responsible for:

short-term memory
working memory
relevant memory retrieval
conversation compression
context prioritization

4. Structured Orchestrator Model

File:

orchestrator_model.py

Status:

✅ Implemented

Current role:

MiniCPM router/planner with JSON-guaranteed output.

Responsibilities:

analyze user request
select tools
reformulate query
create plans

Current flow:

User Request

      |
      ▼

Orchestrator Model

      |
      ├── tools[]
      |
      ├── query rewrite
      |
      └── plan[]

Future improvements:

connect to AgentState (done via AgentOrchestrator)
use memory context automatically (done via AgentOrchestrator)
support replanning (done via Planner)
support multi-agent routing

5. Agent Orchestrator

File:

orchestrator.py

Status:

✅ Implemented

Purpose:

Wires MiniCPM orchestrator + planner + state + memory into a unified query pipeline.

Responsibilities:

route queries through MiniCPM for tool selection + plan generation
retrieve relevant memories before analysis
execute multi-step plans via PlanExecutor
feed plan results + memory context into LLM
track agent state through lifecycle

Flow:

User Input
    |
    ▼
Memory Retrieval
    |
    ▼
MiniCPM Orchestrator (select tools, rewrite query, generate plan)
    |
    ├── Single step → pass directly to LLM
    └── Multi-step  → PlanExecutor → results fed as context

Known issues:

StateStore initialized twice (fixed)
Undefined variable reference in analyze call (fixed)
Missing record_execution method (fixed)

6. Planner Module

File:

planner.py

Status:

✅ Implemented

Separate planning from orchestration.

Architecture:

Orchestrator
      |
      ▼
Planner
      |
      ▼
Execution Runtime

Planner responsibilities:

create plans via LLM (hybrid planner)
break goals into steps with dependency tracking
estimate complexity via tool list validation
request replanning on failure
execute plans through TaskQueue + PlanExecutor
retry with reflection-based error recovery

Includes:

Plan, PlanStep, TaskQueue, PlanExecutor — full lifecycle
TaskQueue: dependency resolution state machine
PlanExecutor: retry loop with Reflector integration

7. Memory Architecture

File:

agent/memory/ (package with 5 modules)

Status:

✅ Implemented (ahead of original plan)

Three-layer memory (in types.py):

Working Memory (via AgentState.scratchpad)
Episodic Memory (conversation history with vector embeddings)
Semantic Memory (extracted facts, learnings, knowledge)

Components:

MemoryEntry — typed dataclass (content, embedding, type, tags, importance)
MemoryType — enum (EPISODIC, SEMANTIC, PROCEDURAL)
MemoryEmbedder — sentence-transformers wrapper (384d, CPU)
LanceMemoryStore — LanceDB vector store with FTS + vector search
MemoryRetriever — hybrid search (vector + FTS) with recency/importance scoring
MemoryPipeline — background pipeline: summarize → extract → embed → store

Capabilities:

vector similarity search
full-text search fallback
scoring: vector distance × importance × recency decay
auto-inject top N memories into system prompt
background conversation → memory pipeline
auto-extract facts into knowledge base

8. Event System

File:

events.py

Status:

✅ Implemented

Purpose:

Everything becomes observable.

Example:

EventBus.emit("tool_started", {"tool": "web_search"})

Events:

goal_started, goal_completed
plan_created, plan_failed
tool_started, tool_finished, tool_failed
step_completed, step_failed
reflection_completed
memory_updated
state_changed
error, warning, info

Benefits:

TUI updates
debugging
logs
autonomous monitoring

9. Runtime Controller

File:

runtime.py

Status:

✅ Implemented

Purpose:

Own the cognition loop.

Responsibilities:

load state
accept goal
execute plan
handle failures
call reflector
save state

Interface:

CognitiveRuntime.run(goal)

Loop:

LOAD STATE → PLAN → EXECUTE → REFLECT → UPDATE STATE → SAVE

Features:

EventBus integration for observability
Fallback plan via OrchestratorModel if Planner fails
Replan on failure (up to max_retries)
Automatic state persistence

Current Cognitive Loop

Current:

User
 |
 ▼
CognitiveRuntime.run(goal)
 |
 ├── PLANNING (Planner + OrchestratorModel fallback)
 ├── EXECUTING (PlanExecutor + Reflector)
 ├── REFLECTING (Reflector on failures)
 ├── UPDATE STATE (persist)
 └── COMPLETE

Target Hermes-Style Cognitive Loop

Future:

                 ┌───────────────┐
                 │ User Request  │
                 └───────┬───────┘
                         |
                         ▼

                 ┌───────────────┐
                 │ State Manager │
                 └───────┬───────┘
                         |
                         ▼

                 ┌───────────────┐
                 │ Planner       │
                 └───────┬───────┘
                         |
                         ▼

              ┌─────────────────────┐
              │ Execution Runtime   │
              └─────────┬───────────┘
                        |
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼

     Tools          Memory          Events


        |
        ▼

 ┌─────────────────────┐
 │ Reflection System   │
 └─────────┬───────────┘
           |
           ▼

      Update State

           |
           ▼

      Continue Loop

Next Implementation Phase
Phase 1 — Runtime Controller

File:

runtime.py

Status:

✅ Implemented

Purpose:

Own the cognition loop.

Responsibilities:

load state
accept goal
execute plan
handle failures
call reflector
save state

Interface:

CognitiveRuntime.run(goal)

controls:

PLAN
EXECUTE
OBSERVE
REFLECT
UPDATE

Phase 2 — Planner Module

File:

planner.py

Status:

✅ Implemented

Purpose:

Separate planning from orchestration.

Architecture:

Orchestrator
      |
      ▼
Planner
      |
      ▼
Execution Runtime

Planner responsibilities:

create plans
break goals into steps
estimate complexity
request replanning

Phase 3 — Event System

File:

events.py

Status:

✅ Implemented

Purpose:

Everything becomes observable.

Example:

EventBus.emit("tool_started", {"tool": "web_search"})

Events:

goal_started, goal_completed
plan_created, plan_failed
tool_started, tool_finished, tool_failed
step_completed, step_failed
reflection_completed
memory_updated
state_changed
error, warning, info

Benefits:

TUI updates
debugging
logs
autonomous monitoring

Phase 4 — Upgrade State System

Current:

state.py

Upgrade:

AgentState
+
EventBus (done in events.py)
+
Persistence (done via StateStore)
+
Transitions

Add:

transition(
    old_state,
    new_state
)

Prevent:

EXECUTING
   |
   ▼
IDLE

without completion.

Phase 5 — Memory Architecture

Current:

agent/memory/ (5 modules)

Status:

✅ Implemented (ahead of original plan)

Target achieved:

Memory System

├── Working Memory (AgentState.scratchpad)
├── Episodic Memory (conversations in vector DB + knowledge files)
└── Semantic Memory (extracted facts, learnings)

Components:

types.py — MemoryEntry, MemoryType (EPISODIC, SEMANTIC, PROCEDURAL)
embed.py — MemoryEmbedder (sentence-transformers, 384d)
store.py — LanceMemoryStore (LanceDB, vector + FTS)
retrieval.py — MemoryRetriever (hybrid search, recency/importance scoring)
pipeline.py — MemoryPipeline (background summarize → extract → embed → store)

Future improvements:

memory consolidation / dedup
memory decay / forgetting curves
cross-session inference
memory graph / associations

Phase 6 — Autonomous Runtime

File:

agent/tray/scheduler.py

Status:

✅ Implemented

Purpose:

Allow limited autonomous actions.

Examples:

Allowed:

memory cleanup (via MemoryPipeline background processing)
indexing
checking queued tasks
reminder notifications

Not allowed:

uncontrolled external actions
destructive operations
hidden behavior

Autonomy should always be:

bounded
observable
interruptible

Phase 7 — Tool Intelligence

File:

tool_registry.py

Status:

✅ Implemented

What was built:

ToolSpec — dataclass wrapping each tool with name, description, fn, risk_level (LOW/MEDIUM/HIGH/CRITICAL), permissions (read/write/execute/network/filesystem), category. Callable + __name__/__doc__/__signature__ for full backward compat.

ToolRegistry — collection with lookup by name, category, risk level, permissions. Richer tool descriptions for planner/orchestrator prompts (includes signatures, risk icons, permissions).

RiskLevel — enum (LOW, MEDIUM, HIGH, CRITICAL) for tool risk classification

Permissions — string set (read, write, execute, network, filesystem, dangerous)

Backward compat: all existing code paths still work with bare function lists

Config key: tools.py exports get_native_specs() + get_native_registry()

Phase 8 — Improved Reflection

File:

reflector.py

Status:

✅ Implemented

Upgrade:

Rule Reflection
       +
LLM Reflection (configurable)
       +
Memory (LessonStore)

What was built:

LessonStore — persists failure lessons with tool, error_pattern, root_cause, suggestion, context. match() scoring for retrieval. format_for_prompt() surfaces relevant lessons to LLM.

LLM reflection — when reflection.llm_enabled=true in config, calls LLM with error + past lessons for deep root cause analysis. Auto-stores new lessons. Falls back to rule-based on failure.

Confidence scoring — LLM returns confidence 0-1, rules return hard 1.0

Config key:

reflection:
  llm_enabled: true
  llm_model: qwen3:8b
  ollama_url: http://localhost:11434

Phase 9 — Multi-Agent Routing

File:

agent_router.py

Status:

✅ Implemented

What was built:

AgentProfile — dataclass (name, description, model, allowed_categories, system_prompt_override)

AgentRouter — routes queries to agent profiles. LLM-based routing with rule-based fallback. Profiles registered: coder (execution/code tasks), researcher (research/search tasks), writer (file/knowledge tasks).

Integration — OrchestratorModel injects agent_profile + description into system prompt. CognitiveRuntime routes before planning.

Config key: agent profiles registered in main.py

Final Target Architecture
CozmoBrain Runtime

                 User
                  |
                  ▼

          Cognitive Runtime

                  |
     ┌────────────┼────────────┐
     ▼            ▼            ▼

  Planner     State       Memory

     |
     ▼

 Execution Engine

     |
 ┌───┼────┐

Tools MCP  Agents


     |
     ▼

 Reflection

     |
     ▼

 Learning / Memory Update

Long-Term Goals
Intelligence

Move from:

"answer questions"

to:

"complete objectives"

Persistence

Move from:

"conversation history"

to:

"continuous identity"

Autonomy

Move from:

"user triggers every action"

to:

"user defines goals and boundaries"

Reliability

Move from:

"LLM output"

to:

"verified execution loop"

Current Priority Order
✅ AgentState
✅ Reflector (rule + LLM + LessonStore)
✅ Structured Orchestrator (orchestrator_model.py + orchestrator.py)
✅ Planner module (planner.py)
✅ Event system (events.py + EventBus)
✅ Runtime controller (runtime.py)
✅ Memory system (agent/memory/ — 5 modules)
✅ Scheduler (agent/tray/scheduler.py)
✅ Tool registry upgrade (ToolRegistry + Permissions + Metadata)
✅ Multi-agent capabilities (AgentRouter + AgentProfile)
✅ LLM-powered reflection (Phase 8 upgrade)

All phases complete. Remaining optional polish:
- State transition validation guards
- CLI entrypoint / packaging (pyproject.toml)
- Add `reflection.llm_enabled: true` to config for LLM failure analysis

End Goal

CozmoBrain becomes a persistent autonomous cognitive framework:

A system that can:

understand goals
create plans
execute actions
observe outcomes
recover from failure
remember experiences
improve over time
operate continuously under user-defined boundaries

The final product is not a chatbot.

It is an agent runtime.
