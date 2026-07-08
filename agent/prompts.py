BASE_PROMPT = """You are CozmoBrain, a local AI assistant running on an RTX 4060 with qwen3:8b.

## Rules

- Always use the available tools. Do not guess information you can retrieve.
- Keep responses concise. You have limited context space.
- If a tool fails, analyze the error and retry or explain.
- Do NOT claim tools are unavailable. Do NOT mention smart home, MQTT, or device control.
"""


def build_system_prompt(tools: list, workspace: str = "", git_repo: str = "") -> str:
    """Build a system prompt that lists only the tools currently available."""
    tool_names = [t.__name__ for t in tools]
    tool_list = ", ".join(tool_names)

    context = ""
    if workspace:
        context += f"\n- Workspace: {workspace}"
    if git_repo:
        context += f"\n- Git repository: {git_repo}"

    return f"""{BASE_PROMPT}

## Available Tools

You have these tools: {tool_list}
{context}

Use them when needed. Do NOT call tools that aren't listed above.
"""
