"""Internet/API integrations for CozmoBrain.

Each module exposes tool functions. All tools return strings
(error messages or data) — never raise.
"""

from . import system, weather, news, reminders


def get_integration_tools(config: dict) -> list:
    """Collect all integration tool functions based on config."""
    tools = []

    try:
        tools.extend(system.get_tools())
    except Exception:
        pass

    try:
        tools.extend(weather.get_tools(config.get("integrations", {})))
    except Exception:
        pass

    try:
        tools.extend(news.get_tools(config.get("integrations", {})))
    except Exception:
        pass

    try:
        tools.extend(reminders.get_tools(config.get("integrations", {})))
    except Exception:
        pass

    return tools
