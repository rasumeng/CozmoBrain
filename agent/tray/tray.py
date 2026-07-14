"""System tray icon for CozmoBrain background operation."""

import threading
from PIL import Image, ImageDraw


def _create_icon() -> Image.Image:
    """Generate a simple 64x64 tray icon."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Brain-like shape
    draw.ellipse([8, 12, 56, 52], fill="#00CC88")
    draw.ellipse([16, 6, 48, 28], fill="#00FF99")
    draw.rectangle([20, 28, 44, 48], fill="#009966")

    return img


class TrayApp:
    """System tray icon with menu.

    Runs in a background thread. Provides quick access to
    status, open console, and quit.
    """

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._icon = None
        self._on_quit: callable | None = None

    def on_quit(self, callback: callable):
        self._on_quit = callback

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _run(self):
        import pystray
        from pystray import MenuItem as item

        icon = pystray.Icon(
            "cozmobrain",
            _create_icon(),
            "CozmoBrain",
            menu=pystray.Menu(
                item("Open Console", self._open_console, default=True),
                item("Status", self._show_status),
                pystray.Menu.SEPARATOR,
                item("Quit", self._do_quit),
            ),
        )
        self._icon = icon
        icon.run()

    def _open_console(self):
        """Bring REPL window to foreground (best-effort)."""
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle("CozmoBrain")
            for w in windows:
                w.activate()
        except ImportError:
            pass

    def _show_status(self):
        """Show notification with status info."""
        from .notify import notify
        notify("CozmoBrain", "Running in background. Voice and memory active.")

    def _do_quit(self):
        if self._icon:
            self._icon.stop()
        if self._on_quit:
            self._on_quit()
        self._running = False
        import os
        os._exit(0)
