from __future__ import annotations
import os, json, re
from config import Local_Paths

PROFILES_FILE = Local_Paths.PROFILES
_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,40}$")
_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$", re.I)
_HOST_RE = re.compile(r"^[A-Za-z0-9_.:\-]+$")  # IPv4, IPv6, or hostname

def _default_store():
    return {"active": None, "profiles": {}}

def load_store():
    """Load jetson_profiles.json; return default if missing or invalid."""
    try:
        with open(PROFILES_FILE, "r") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return _default_store()
        obj.setdefault("active", None)
        obj.setdefault("profiles", {})
        if not isinstance(obj["profiles"], dict):
            obj["profiles"] = {}
        return obj
    except FileNotFoundError:
        return _default_store()
    except Exception:
        return _default_store()

def save_store(store):
    """Persist atomically to data/jetson_profiles.json"""
    os.makedirs(Local_Paths.DATA_DIR, exist_ok=True)
    tmp = PROFILES_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, PROFILES_FILE)

def validate_profile(name, user, host):
    if not name or not _NAME_RE.match(name):
        return False, "Invalid profile name"
    if not user or not _USER_RE.match(user):
        return False, "Invalid SSH user"
    if not host or not _HOST_RE.match(host):
        return False, "Invalid host/IP"
    return True, ""

def upsert_profile(name, user, host) -> None:
    """Add or update a Jetson profile (does not change active)."""
    store = load_store()
    store.setdefault("profiles", {})
    store["profiles"][name] = {"user": user, "host": host}
    save_store(store)

def set_active(name):
    """Set a profile active by name."""
    store = load_store()
    if name not in store.get("profiles", {}):
        return False, "Profile not found"
    store["active"] = name
    save_store(store)
    return True, ""

def get_active():
    """Return (active_name, user, host). Raises if none active."""
    store = load_store()
    active = store.get("active")
    prof = (store.get("profiles") or {}).get(active or "")
    if not prof:
        raise ValueError("No active profile")
    return active, prof["user"], prof["host"]

def delete_profile(name):
    """Delete a profile; deactivate if it was active."""
    store = load_store()
    if name not in store.get("profiles", {}):
        return False, "Profile not found"
    del store["profiles"][name]
    if store.get("active") == name:
        store["active"] = None
    save_store(store)
    return True, ""

def list_profiles():
    """Return the profiles dict for convenience."""
    return load_store().get("profiles", {})