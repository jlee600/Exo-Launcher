import threading, webbrowser
from config import Wifi, HTML
from util.utils import write_dashboard_info
from util.ssh import periodic_sync, close_master

_active_user = None
_active_host = None
_sync_thread = None

def on_login(profile_name: str, user: str, host: str):
    """
    Called by the API server after /api/login succeeds.
    - records active user/host
    - writes dashboard info
    - starts the periodic sync thread (if not running)
    - opens the dashboard in the browser
    """
    global _active_user, _active_host, _sync_thread
    _active_user, _active_host = user, host

    write_dashboard_info(user, Wifi.SSID_CAREN)

    if _sync_thread is None or not _sync_thread.is_alive():
        _sync_thread = threading.Thread(target=periodic_sync, args=(user, host, Wifi.SSID_CAREN, 4), daemon=True)
        _sync_thread.start()

    url = f"http://127.0.0.1:{HTML.POLL_PORT}/dashboard.html"
    try:
        webbrowser.open_new_tab(url)
    except Exception:
        pass

def get_active_connection():
    """Return (user, host) if login occurred, else (None, None)."""
    return _active_user, _active_host

def close_active_master():
    """Close control master for currently active connection (if any)."""
    if _active_user and _active_host:
        try:
            close_master(_active_user, _active_host)
        except Exception:
            pass