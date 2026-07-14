from datetime import datetime


BASE_PROMPT = """You are CozmoBrain, a local AI assistant running on an RTX 4060 with qwen3:8b.

## Rules

- Always use the available tools. Do not guess information you can retrieve.
- Keep responses concise. You have limited context space.
- If a tool fails, analyze the error and retry or explain.
- Do NOT claim tools are unavailable. Do NOT mention smart home, MQTT, or device control.
"""


def build_system_prompt(
    tools: list,
    workspace: str = "",
    git_repo: str = "",
    extra_context: str | None = None,
) -> str:
    """Build a system prompt that lists only the tools currently available.

    Args:
        tools: List of tool functions.
        workspace: Workspace directory path.
        git_repo: Git repository path.
        extra_context: Optional plan execution summary, memories, or other context.
    """
    tool_names = [t.__name__ for t in tools]
    tool_list = ", ".join(tool_names)

    context = ""
    if workspace:
        context += f"\n- Workspace: {workspace}"
    if git_repo:
        context += f"\n- Git repository: {git_repo}"

    today = datetime.now().strftime("%Y-%m-%d")

    extra = ""
    if extra_context:
        extra = f"\n\n{extra_context}\n"

    return f"""{BASE_PROMPT}

## Available Tools

You have these tools: {tool_list}
{context}

## Today's Date

Today is {today}. When answering time-sensitive questions (news, updates, events, releases), always:
- Cite the specific date of information you find
- Note if sources are potentially outdated
- Prefer recent search results over stale knowledge

## Memory

You have long-term memory. Relevant memories from past conversations are injected at the top of this prompt under "Relevant Memories". Use them for context.

You also have tools to search memory directly:
- `web_search` — search the internet
- `read_knowledge` — read from stored knowledge files

Use them when needed. Do NOT call tools that aren't listed above.
{extra}"""
