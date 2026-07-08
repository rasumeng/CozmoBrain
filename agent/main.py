import asyncio
import yaml
from rich.console import Console

from .llm import create_agent
from .tools import execute_python, fetch_url, write_file, read_knowledge, write_knowledge, web_search
from .mcp_host import MCPHost
from .context import compact_messages, count_message_tokens
from .router import ToolRouter


console = Console()


def load_config() -> dict:
    """Load config.yaml."""
    with open("config.yaml") as f:
        return yaml.safe_load(f)


async def main():
    """Entry point — async to support MCP tools."""
    config = load_config()

    # Native tools (sync)
    native_tools = [execute_python, fetch_url, write_file, read_knowledge, write_knowledge, web_search]

    # Connect MCP servers and get async tool wrappers
    mcp = MCPHost("config.yaml")
    await mcp.connect()
    mcp_tools = await mcp.get_tool_wrappers()

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
                config.get("model", "ornith:9b"),
                tools=active_tools,
                max_tokens=config.get("max_tokens", 2048),
            )

            # Compact context before each call
            if message_history:
                message_history = compact_messages(message_history, config)

            result = await agent.run(
                user_input,
                message_history=message_history,
            )
            console.print(f"[bold green]CozmoBrain:[/] {result.output}\n")
            message_history = result.all_messages()
        except Exception as e:
            console.print(f"[red]Error:[/] {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
