import os
import warnings

# Suppress HuggingFace Hub unauthenticated request warning
warnings.filterwarnings("ignore", message="You are sending unauthenticated requests")

import asyncio
import sys
import yaml
from rich.console import Console

from . import tools as tools_module
from .llm import create_agent
from .tools import execute_python, fetch_url, write_file, read_knowledge, write_knowledge, web_search, get_native_specs
from .mcp_host import MCPHost
from .context import compact_messages, count_message_tokens, truncate_tool_responses
from .orchestrator import AgentOrchestrator
from .memory import MemoryEmbedder, LanceMemoryStore, MemoryRetriever, MemoryPipeline
from .integrations import get_integration_tools
from .tool_registry import ToolRegistry, ToolSpec
from .agent_router import AgentRouter, AgentProfile


console = Console()


def load_config() -> dict:
    """Load config.yaml."""
    with open("config.yaml") as f:
        return yaml.safe_load(f)


async def main():
    """Entry point — async to support MCP tools and orchestrator."""
    config = load_config()

    # Configure native tool settings from config
    tools_module.SEARXNG_URL = config.get("searxng_url", tools_module.SEARXNG_URL)

    # Build ToolRegistry
    registry = ToolRegistry(get_native_specs())

    # Connect MCP servers and get async tool wrappers
    mcp = MCPHost("config.yaml")
    mcp_tools = []
    try:
        await mcp.connect()
        mcp_tools = await mcp.get_tool_wrappers()
    except Exception:
        pass

    # Register MCP tools as ToolSpecs (infer metadata from callables)
    for t in mcp_tools:
        registry.register(ToolSpec(
            name=t.__name__,
            description=getattr(t, "__doc__", "MCP tool") or "MCP tool",
            fn=t,
            risk_level=RiskLevel.MEDIUM,
            permissions={"network"},
            category="mcp",
        ))

    # Integration tools (system, weather, news, reminders, calendar)
    integration_tools = get_integration_tools(config)
    for t in integration_tools:
        registry.register(ToolSpec(
            name=t.__name__,
            description=getattr(t, "__doc__", "Integration tool") or "Integration tool",
            fn=t,
            risk_level=RiskLevel.LOW,
            permissions={"read"},
            category="integration",
        ))

    # All tools: as callable list (backward compat)
    all_tools = registry.to_callables()

    # Agent router with profiles
    router = AgentRouter(llm_config=config.get("router", {}))
    router.register(AgentProfile(
        name="coder",
        description="Specialist for code execution, debugging, scripting tasks",
        model=config.get("model", "qwen3:8b"),
        allowed_categories=["execution", "filesystem"],
    ))
    router.register(AgentProfile(
        name="researcher",
        description="Specialist for web search, URL fetching, information gathering",
        model=config.get("model", "qwen3:8b"),
        allowed_categories=["research"],
    ))
    router.register(AgentProfile(
        name="writer",
        description="Specialist for writing files, knowledge base entries, note-taking",
        model=config.get("model", "qwen3:8b"),
        allowed_categories=["filesystem", "knowledge"],
    ))

    # Initialize memory system
    mem_config = config.get("memory", {})
    embedder = MemoryEmbedder(mem_config.get("embedding_model", "all-MiniLM-L6-v2"))
    console.print("[dim]Loading memory model...[/]")
    _ = embedder.dim  # Pre-load embedding model at startup
    mem_store = LanceMemoryStore(
        db_path=mem_config.get("path", "./memory_store"),
        embed_dim=mem_config.get("embed_dim", 384),
    )
    mem_retriever = MemoryRetriever(
        mem_store, embedder,
        max_auto_inject=mem_config.get("max_auto_inject", 2),
    )
    mem_pipeline = MemoryPipeline(
        mem_store, embedder,
        auto_knowledge=mem_config.get("auto_summarize", True),
    )

    # Initialize orchestrator with memory + registry + router
    orchestrator = AgentOrchestrator(
        config, all_tools,
        memory_retriever=mem_retriever,
        tool_registry=registry,
        agent_router=router,
    )

    # Initialize voice (STT + TTS) if enabled
    voice_listener = None
    tts = None
    voice_config = config.get("voice", {})
    if voice_config.get("enabled", False):
        from .voice import VoiceListener, TTS
        try:
            voice_listener = VoiceListener(
                stt_model=voice_config.get("model", "tiny"),
                hotkey_name=voice_config.get("hotkey", "scroll_lock"),
            )
            voice_listener.start()
            voice_name = voice_config.get("voice") or "en-US-JennyNeural"
            tts = TTS(voice=voice_name)
            hotkey_display = voice_config.get("hotkey", "scroll_lock")
            console.print(f"[dim]Voice: [/]push-to-talk on {hotkey_display}")
        except Exception as e:
            console.print(f"[dim]Voice init failed: {e}[/]")

    # Initialize tray + scheduler
    tray_app = None
    scheduler = None
    tray_config = config.get("tray", {})
    if tray_config.get("enabled", False):
        from .tray import TrayApp, Scheduler
        from .tray.notify import notify as tray_notify
        from .integrations.reminders import check_due_reminders as _check_reminders
        try:
            scheduler = Scheduler()

            def _reminder_check():
                try:
                    due = _check_reminders()
                    if due:
                        tray_notify("CozmoBrain Reminder", due)
                except Exception:
                    pass

            scheduler.add_task(60, _reminder_check)
            scheduler.start()

            tray_app = TrayApp()
            tray_app.on_quit(lambda: None)  # Let main loop handle cleanup
            tray_app.start()
            console.print("[dim]Tray: [/]background notifications active")
        except Exception as e:
            console.print(f"[dim]Tray init failed: {e}[/]")

    console.print("[bold green]CozmoBrain[/] initialized. Type 'quit' to exit.\n")

    message_history = []

    try:
        while True:
            try:
                # Check for voice input before REPL prompt
                if voice_listener and voice_listener.has_pending():
                    user_input = voice_listener.get_pending()
                    console.print(f"\n[bold cyan]You (voice):[/] {user_input}")
                else:
                    user_input = console.input("[bold cyan]You:[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\nGoodbye!")
                break

            if user_input.lower() in ("quit", "exit"):
                console.print("Goodbye!")
                break

            if not user_input:
                continue

            try:
                # Run orchestrator: memory retrieval + optional planning
                orc_result = await orchestrator.process(user_input, message_history)
                console.print(f"[dim]Agent state: {orchestrator.state.status}[/]") # Remove later

                # Combine plan context + memories into one extra_context string
                extra_parts = []
                if orc_result.plan_context:
                    extra_parts.append(orc_result.plan_context)
                if orc_result.memories_context:
                    extra_parts.append(orc_result.memories_context)
                extra_context = "\n\n".join(extra_parts) if extra_parts else None

                # Show status messages from orchestrator
                for msg in orc_result.status_messages:
                    console.print(f"[dim]{msg}[/]")

                # Use MiniCPM-selected tools + reformulated query
                active_tools = orc_result.selected_tools or all_tools
                agent_input = orc_result.reformulated_query or user_input

                # Create agent with filtered tools and context
                agent = create_agent(
                    config.get("model", "qwen3:8b"),
                    tools=active_tools,
                    max_tokens=config.get("max_tokens", 2048),
                    workspace=config.get("workspace", ""),
                    git_repo=config.get("git_repo", ""),
                    extra_context=extra_context,
                )

                # Compact context before each call
                if message_history:
                    message_history = compact_messages(message_history, config)

                async with agent.run_stream(
                    agent_input,
                    message_history=message_history,
                ) as result:
                    console.print("[bold green]CozmoBrain:[/] [dim italic]thinking...[/]", end="")
                    first = True
                    async for chunk in result.stream_text(delta=True, debounce_by=0):
                        if first:
                            console.print("\r[bold green]CozmoBrain:[/] ", end="")
                            first = False
                        console.print(chunk, end="")
                        console.file.flush()
                    console.print("\n")
                    all_msgs = result.all_messages()
                    # Strip old system prompts — agent injects fresh one each cycle
                    all_msgs = [m for m in all_msgs if not any(
                        getattr(p, 'kind', None) == 'system-prompt' for p in getattr(m, 'parts', [])
                    )]
                    # Truncate long tool responses to save context
                    all_msgs = truncate_tool_responses(
                        all_msgs,
                        config.get("tool_response_max_chars", 2000),
                    )
                    message_history = all_msgs

                # Fire memory pipeline in background (don't block next input)
                response_text = ""
                for msg in reversed(all_msgs):
                    for part in getattr(msg, 'parts', []):
                        if getattr(part, 'kind', None) == 'text':
                            response_text = getattr(part, 'content', '') or ''
                            break
                    if response_text:
                        break

                if response_text:
                    asyncio.create_task(mem_pipeline.after_turn(
                        user_input,
                        response_text,
                        extra_ctx={"had_plan": orc_result.plan_steps > 0},
                    ))

                # Speak response via TTS if enabled
                if tts and response_text:
                    asyncio.create_task(tts.speak_and_wait(response_text))
            except Exception as e:
                console.print(f"[red]Error:[/] {e}\n")
    finally:
        await mcp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
