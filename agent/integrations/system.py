"""System info integration. Zero dependencies beyond stdlib + pyperclip (optional)."""

import os
import platform
import shutil
from datetime import datetime
from .base import tool_fn


def _get_clipboard() -> str:
    """Read clipboard text. Requires pyperclip."""
    try:
        import pyperclip
        text = pyperclip.paste()
        return text if text else "[clipboard empty]"
    except ImportError:
        return "[error] clipboard requires: pip install pyperclip"
    except Exception as e:
        return f"[error] clipboard: {e}"


def _set_clipboard(text: str) -> str:
    """Write text to clipboard. Requires pyperclip."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return f"[ok] Copied to clipboard ({len(text)} chars)"
    except ImportError:
        return "[error] clipboard requires: pip install pyperclip"
    except Exception as e:
        return f"[error] clipboard: {e}"


def _get_system_info() -> str:
    """Get OS, CPU, memory, disk usage."""
    try:
        uname = platform.uname()
        cpu_count = os.cpu_count() or 0

        disk = shutil.disk_usage("/")
        disk_gb = disk.free / (1024**3)

        boot_time = datetime.fromtimestamp(
            psutil.boot_time()
        ).strftime("%Y-%m-%d %H:%M") if _psutil_available() else "unknown"

        lines = [
            f"OS: {uname.system} {uname.release}",
            f"Host: {uname.node}",
            f"CPU: {cpu_count} cores",
            f"Disk free: {disk_gb:.1f} GB",
        ]

        if _psutil_available():
            import psutil
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            lines.insert(3, f"RAM: {used_gb:.1f}/{total_gb:.1f} GB ({mem.percent}%)")
            lines.append(f"Boot: {boot_time}")
            lines.append(f"Processes: {len(psutil.pids())}")
        else:
            lines.append("[tip: pip install psutil for RAM/process info]")

        return "\n".join(lines)
    except Exception as e:
        return f"[error] system info: {e}"


def _psutil_available() -> bool:
    try:
        import psutil
        return True
    except ImportError:
        return False


get_system_info = tool_fn(
    "get_system_info",
    "Get system information: OS, CPU cores, RAM usage, disk space, uptime.",
    _get_system_info,
)

read_clipboard = tool_fn(
    "read_clipboard",
    "Read text from the system clipboard.",
    _get_clipboard,
)

write_clipboard = tool_fn(
    "write_clipboard",
    "Write text to the system clipboard.",
    _set_clipboard,
)


def get_tools() -> list:
    return [get_system_info, read_clipboard, write_clipboard]
