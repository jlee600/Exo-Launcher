import threading, webbrowser
from config import Wifi, SERVER
from util.utils import write_dashboard_info
from util.ssh import periodic_sync, close_master

_active_user = None
_active_host = None
_sync_thread = None
_active_ssid = None

def set_active_ssid(ssid):
    """Record which Wi-Fi network is currently active."""
    global _active_ssid
    _active_ssid = ssid

def get_active_ssid():
    """Return the active Wi-Fi network, or None if not set."""
    return _active_ssid

def on_login(profile_name, user, host):
    """
    Called by the API server after /api/login succeeds.
    - records active user/host
    - writes dashboard info
    - starts the periodic sync thread (if not running)
    - opens the dashboard in the browser
    """
    global _active_user, _active_host, _sync_thread
    _active_user, _active_host = user, host

    ssid = _active_ssid or "Unknown"
    write_dashboard_info(user, ssid, host)

    if _sync_thread is None or not _sync_thread.is_alive():
        _sync_thread = threading.Thread(target=periodic_sync, args=(user, host, Wifi.SSID_CAREN, 4), daemon=True)
        _sync_thread.start()

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

        