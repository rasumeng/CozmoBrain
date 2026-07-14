"""Desktop notifications via plyer."""


def notify(title: str, message: str, timeout: int = 5):
    """Show a desktop notification."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            timeout=timeout,
        )
    except Exception:
        pass
