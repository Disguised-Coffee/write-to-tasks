"""Interface for sending desktop notifications to the user. This is used to notify the user of important events, such as when a task is completed or when a new task is added."""
import threading
from concurrent.futures import ThreadPoolExecutor
import asyncio

# Create a thread pool executor for running async code
_executor = ThreadPoolExecutor(max_workers=1)
_loop = None

from desktop_notifier import Button, DesktopNotifier, DEFAULT_SOUND, ReplyField, Urgency, Icon

notifier = DesktopNotifier(app_name="Write-To-Tasks")

ICON_PATH = "C:/repository/write-to-tasks/src/assets/thinking-blue.png"  # Update with the actual path to your icon


def _get_event_loop():
    """Get or create an event loop for the background thread."""
    global _loop
    if _loop is None or not _loop.is_running():
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True).start()
    return _loop

def send_notif(title: str, message: str, on_click_callback=None):
    """Send a notification synchronously."""
    async def _send():
        await notifier.send(
            title=title,
            message=message,
            sound=DEFAULT_SOUND,
            on_clicked=on_click_callback,
        )
    
    loop = _get_event_loop()
    asyncio.run_coroutine_threadsafe(_send(), loop)

def send_error_notif(title: str, message: str, on_click_callback=None):
    """Send an error notification synchronously."""
    async def _send_error():
        await notifier.send(
            title=title,
            message=message,
            icon=Icon(uri=ICON_PATH),  # Optional: URL or local path to an icon
        sound=DEFAULT_SOUND,
        urgency=Urgency.Critical,
        on_clicked=on_click_callback,
        timeout=5  # Notification will disappear after 5 seconds
    )

    loop = _get_event_loop()
    asyncio.run_coroutine_threadsafe(_send_error(), loop)