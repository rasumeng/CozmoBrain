from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from .prompts import build_system_prompt


def create_agent(model: str = "qwen3:8b", tools: list | None = None, max_tokens: int = 2048,
                  workspace: str = "", git_repo: str = "") -> Agent:
    """Create a Pydantic AI agent with Ollama backend.

    Args:
        model: Ollama model name.
        tools: List of tool functions to register.
        max_tokens: Max tokens for model response.
        workspace: Workspace directory path.
        git_repo: Git repository path.
    """
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    ollama_model = OllamaModel(model_name=model, provider=provider)
    return Agent(
        ollama_model,
        system_prompt=build_system_prompt(tools or [], workspace, git_repo),
        tools=tools or [],
        model_settings={"max_tokens": max_tokens},
    )
