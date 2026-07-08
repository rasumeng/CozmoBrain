import subprocess
import urllib.request
import urllib.parse
import re
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

import yaml


WORKSPACE = Path("./workspace").resolve()
KNOWLEDGE = Path("./knowledge").resolve()
SEARXNG_URL = "http://localhost:8080"
DOCKER_AVAILABLE = shutil.which("docker") is not None


def _docker_available() -> bool:
    """Check if Docker daemon is running."""
    if not DOCKER_AVAILABLE:
        return False
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _execute_in_docker(code: str) -> str:
    """Execute Python code in an ephemeral Docker container."""
    dockerfile = Path(__file__).parent.parent / "docker" / "sandbox.Dockerfile"
    image_name = "cozmobrain-sandbox"

    # Build image if not exists
    if not _image_exists(image_name):
        subprocess.run(
            ["docker", "build", "-t", image_name, "-f", str(dockerfile), str(dockerfile.parent)],
            capture_output=True,
            timeout=60,
        )

    # Run code in container
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "--network", "none",              # No network access
            "--memory", "256m",               # Memory limit
            "--cpus", "1",                    # CPU limit
            "--read-only",                    # Read-only filesystem
            "--tmpfs", "/tmp:size=50m",       # Writable /tmp
            image_name,
            "python", "-c", code,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    return output.strip() or "[no output]"


def _image_exists(name: str) -> bool:
    """Check if a Docker image exists."""
    result = subprocess.run(
        ["docker", "image", "inspect", name],
        capture_output=True,
    )
    return result.returncode == 0


def execute_python(code: str) -> str:
    """Execute Python code in a sandboxed environment and return stdout/stderr.

    Uses Docker if available (isolated, no network), falls back to subprocess.

    Args:
        code: The Python code to execute.
    """
    if _docker_available():
        try:
            return _execute_in_docker(code)
        except subprocess.TimeoutExpired:
            return "[error] Code execution timed out (30s limit)"
        except Exception as e:
            return f"[error] Docker execution failed: {e}"

    # Fallback: subprocess (less secure)
    try:
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(WORKSPACE),
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        return output.strip() or "[no output]"
    except subprocess.TimeoutExpired:
        return "[error] Code execution timed out (30s limit)"
    except Exception as e:
        return f"[error] {e}"


def fetch_url(url: str) -> str:
    """Fetch a URL and return clean text content.

    Args:
        url: The URL to fetch.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > 2000:
            text = text[:2000] + "\n[truncated]"

        return text
    except Exception as e:
        return f"[error] Failed to fetch URL: {e}"


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using SearXNG and return summarized results.

    Args:
        query: The search query.
        max_results: Maximum number of results to return (default 5).
    """
    try:
        params = urllib.parse.urlencode({"q": query, "format": "json"})
        url = f"{SEARXNG_URL}/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results", [])[:max_results]
        if not results:
            return "[no results found]"

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            snippet = r.get("content", "")
            link = r.get("url", "")
            lines.append(f"{i}. **{title}**\n   {snippet}\n   {link}")

        return "\n\n".join(lines)
    except Exception as e:
        return f"[error] Search failed: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file inside the workspace directory.

    Args:
        path: Relative path inside workspace (e.g. 'output.txt').
        content: The content to write.
    """
    try:
        target = (WORKSPACE / path).resolve()
        if not str(target).startswith(str(WORKSPACE)):
            return "[error] Path traversal not allowed"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"[ok] Written to {path}"
    except Exception as e:
        return f"[error] {e}"


def read_knowledge(path: str) -> str:
    """Read a file from the knowledge base.

    Args:
        path: Relative path inside knowledge base (e.g. 'learnings/python-patterns.md').
    """
    try:
        target = (KNOWLEDGE / path).resolve()
        if not str(target).startswith(str(KNOWLEDGE)):
            return "[error] Path traversal not allowed"
        if not target.exists():
            return f"[error] File not found: {path}"
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"[error] {e}"


def write_knowledge(path: str, content: str, type: str = "Reference", title: str = "", tags: list[str] | None = None) -> str:
    """Write a file to the knowledge base with OKF frontmatter.

    Args:
        path: Relative path inside knowledge base (e.g. 'learnings/new-thing.md').
        content: The markdown body content.
        type: Concept type (Conversation, Learning, Project, Reference).
        title: Human-readable title.
        tags: List of tags for categorization.
    """
    try: 
        target = (KNOWLEDGE / path).resolve()
        if not str(target).startswith(str(KNOWLEDGE)):
            return "[error] Path traversal not allowed"

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        title = title or path.replace(".md", "").replace("/", " - ").replace("-", " ").title()
        tags = tags or []

        frontmatter = {
            "type": type,
            "title": title,
            "tags": tags,
            "timestamp": now,
        }

        with open(target, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.dump(frontmatter, f, default_flow_style=False, allow_unicode=True)
            f.write("---\n\n")
            f.write(content)

        return f"[ok] Written to knowledge/{path}"
    except Exception as e:
        return f"[error] {e}"
