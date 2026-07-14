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
│
├── orchestrator_model.py
├── reflector.py
├── state.py
│
├── knowledge/
├── memory_store/
└── config.yaml
Completed Work
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

connect reflector to AgentState
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

MiniCPM router/planner.

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

connect to AgentState
use memory context automatically
support replanning
support multi-agent routing
Current Cognitive Loop

Current:

User
 |
 ▼
Orchestrator
 |
 ▼
LLM
 |
 ▼
Tools
 |
 ▼
Response
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

Create:

runtime.py

Purpose:

Own the cognition loop.

Responsibilities:

load state
accept goal
execute plan
handle failures
call reflector
save state

Expected:

Runtime.run(goal)

controls:

PLAN
EXECUTE
OBSERVE
REFLECT
UPDATE
Phase 2 — Planner Module

Create:

planner.py

Purpose:

Separate planning from orchestration.

Currently:

orchestrator_model.py

does too much.

Move toward:

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

Create:

events.py

Purpose:

Everything becomes observable.

Example:

AgentEvent(
    type="tool_started",
    data={
        "tool":"web_search"
    }
)

Events:

goal_started
plan_created
tool_started
tool_finished
reflection_completed
memory_updated
state_changed

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
EventBus
+
Persistence
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

knowledge/
memory_store/

Target:

Three-layer memory:

Memory System

├── Working Memory
│       current task
│
├── Episodic Memory
│       past experiences
│
└── Semantic Memory
        learned knowledge

Implement:

memory_manager.py

Responsibilities:

retrieve relevant memories
summarize experiences
store lessons
Phase 6 — Autonomous Runtime

Add:

scheduler.py

Purpose:

Allow limited autonomous actions.

Examples:

Allowed:

memory cleanup
indexing
checking queued tasks
maintenance

Not allowed:

uncontrolled external actions
destructive operations
hidden behavior

Autonomy should always be:

bounded
observable
interruptible
Phase 7 — Tool Intelligence

Current:

tools.py

Upgrade:

ToolRegistry

+
Permissions

+
Tool Metadata

Each tool gains:

Tool(
 name,
 description,
 risk_level,
 cost,
 required_permissions
)

Planner can reason:

"Should I use this tool?"

Phase 8 — Improved Reflection

Upgrade:

Current:

Rule based reflection

Future:

Rule Reflection
       +
LLM Reflection
       +
Memory

Example:

After failure:

Why failed?

What changed?

Should future attempts avoid this?

Store lesson?
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
✅ Reflector
✅ Structured Orchestrator
🔨 Runtime controller
🔨 Planner extraction
🔨 Event system
🔨 Memory manager
🔨 Autonomous scheduler
🔨 Tool registry upgrade
🔨 Multi-agent capabilities
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