from pathlib import Path
import yaml


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4


def truncate_tool_response(response: str, max_chars: int = 2000) -> str:
    """Truncate long tool responses to save context space."""
    if len(response) <= max_chars:
        return response
    return response[:max_chars] + "\n[truncated]"


def trim_history(messages: list, max_messages: int = 20) -> list:
    """Drop oldest messages, always keep system prompt and most recent user msg."""
    if len(messages) <= max_messages:
        return messages

    # Keep first (system) + most recent messages
    system = messages[:1]
    recent = messages[-(max_messages - 1):]
    return system + recent


def count_message_tokens(messages: list) -> int:
    """Estimate total tokens across all messages."""
    total = 0
    for msg in messages:
        # Handle both Pydantic AI objects and dicts
        content = getattr(msg, 'content', '') or ''
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            # Pydantic AI parts list
            for part in content:
                text = getattr(part, 'content', '') or str(part)
                total += estimate_tokens(text)
    return total


def truncate_tool_responses(messages: list, max_chars: int = 2000) -> list:
    """Truncate long tool return content in message history to save context."""
    for msg in messages:
        for part in getattr(msg, 'parts', []):
            if getattr(part, 'kind', None) == 'tool-return':
                content = getattr(part, 'content', '')
                if isinstance(content, str) and len(content) > max_chars:
                    part.content = content[:max_chars] + "\n[truncated]"
    return messages


def compact_messages(messages: list, config: dict) -> list:
    """Apply context management: sliding window trim."""
    max_messages = config.get("max_history", 20)
    return trim_history(messages, max_messages)