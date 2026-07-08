import yaml
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


class MCPHost:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.sessions: list[tuple[str, ClientSession]] = []
        self._context_managers = []

    async def connect(self):
        """Connect to all MCP servers defined in config."""
        server_configs = self.config.get("mcp_servers", {})
        for name, cfg in server_configs.items():
            try:
                params = StdioServerParameters(
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=cfg.get("env"),
                )
                ctx = stdio_client(params)
                streams = await ctx.__aenter__()
                read_stream, write_stream = streams

                session = ClientSession(read_stream, write_stream)
                await session.__aenter__()
                await session.initialize()

                self.sessions.append((name, session))
                self._context_managers.append(ctx)
                print(f"[mcp] Connected to {name}")
            except Exception as e:
                print(f"[mcp] Failed to connect to {name}: {e}")

    async def get_tool_wrappers(self) -> list[callable]:
        """Get all MCP tools as async callable wrappers, prefixed with server name."""
        wrappers = []
        for server_name, session in self.sessions:
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    prefixed_name = f"{server_name}_{tool.name}"
                    wrappers.append(self._make_wrapper(session, tool.name, prefixed_name))
            except Exception as e:
                print(f"[mcp] Failed to list tools: {e}")
        return wrappers

    def _make_wrapper(self, session: ClientSession, tool_name: str, display_name: str) -> callable:
        """Create an async callable wrapper for an MCP tool."""
        async def wrapper(**kwargs) -> str:
            try:
                result = await session.call_tool(tool_name, arguments=kwargs)
                texts = []
                for content in result.content:
                    if isinstance(content, types.TextContent):
                        texts.append(content.text)
                return "\n".join(texts) or "[no output]"
            except Exception as e:
                return f"[error] Tool call failed: {e}"
        wrapper.__name__ = display_name
        wrapper.__doc__ = f"MCP tool: {display_name}"
        return wrapper
