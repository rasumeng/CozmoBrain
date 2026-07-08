import asyncio
import sys
import yaml
from rich.console import Console

from . import tools as tools_module
from .llm import create_agent
from .tools import execute_python, fetch_url, write_file, read_knowledge, write_knowledge, web_search
from .mcp_host import MCPHost
from .context import compact_messages, count_message_tokens, truncate_tool_responses
from .router import ToolRouter


console = Console()


def load_config() -> dict:
    """Load config.yaml."""
    with open("config.yaml") as f:
        return yaml.safe_load(f)


async def main():
    """Entry point — async to support MCP tools."""
    config = load_config()

    # Configure native tool settings from config
    tools_module.SEARXNG_URL = config.get("searxng_url", tools_module.SEARXNG_URL)

    # Native tools (sync)
    native_tools = [execute_python, fetch_url, write_file, read_knowledge, write_knowledge, web_search]

    # Connect MCP servers and get async tool wrappers
    mcp = MCPHost("config.yaml")
    mcp_tools = []
    try:
        await mcp.connect()
        mcp_tools = await mcp.get_tool_wrappers()
    except Exception:
        pass  # connect failure already logged; agent runs with native tools only

    # All tools: native (sync) + MCP (async) — Pydantic AI handles both
    all_tools = native_tools + mcp_tools

    # Initialize router
    router = ToolRouter(
        "rules.yaml",
        use_llm=config.get("router_llm", True),
        llm_model=config.get("router_model", "qwen2.5:1.5b"),
    )

    console.print("[bold green]CozmoBrain[/] initialized. Type 'quit' to exit.\n")

    message_history = []

    try:
        while True:
            try:
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
                # Route: select relevant tools for this query
                active_tools = router.get_tools(user_input, all_tools)

                # Create agent with filtered tools
                agent = create_agent(
                    config.get("model", "qwen3:8b"),
                    tools=active_tools,
                    max_tokens=config.get("max_tokens", 2048),
                    workspace=config.get("workspace", ""),
                    git_repo=config.get("git_repo", ""),
                )

                # Compact context before each call
                if message_history:
                    message_history = compact_messages(message_history, config)

                async with agent.run_stream(
                    user_input,
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
            except Exception as e:
                console.print(f"[red]Error:[/] {e}\n")
    finally:
        await mcp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
