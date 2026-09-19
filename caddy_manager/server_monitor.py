"""Background ping monitor driving the navbar's live status tags. One thread
loops into an in-memory dict (not config.json); requests only ever read it."""
import subprocess
import threading

from .configstore import (
    get_caddy_servers, get_caddy_server_ping_interval_seconds,
    get_caddy_server_warning_after_misses, get_caddy_server_danger_after_misses,
)

# Comfortably under MIN_CADDY_SERVER_PING_INTERVAL_SECONDS so pinging both
# servers never runs long enough to delay the next scheduled check.
PING_TIMEOUT_SECONDS = 3

# status -> tag background class, status-dot class, one-word tooltip label.
# Shared by the navbar's server-rendered tags and the JSON refresh endpoint.
STATUS_DISPLAY = {
    "online": {"bg_class": "bg-success-lt", "dot_class": "status-success", "label": "Online"},
    "warning": {"bg_class": "bg-warning-lt", "dot_class": "status-warning", "label": "Unavailable"},
    "danger": {"bg_class": "bg-danger-lt", "dot_class": "status-danger", "label": "Offline"},
    # Brief window before a server's first ping completes -- clears within moments, not a full interval.
    "pending": {"bg_class": "bg-secondary-lt", "dot_class": "status-secondary", "label": "Checking"},
}

_lock = threading.Lock()
_state = {}  # host -> {"consecutive_misses": int, "checked": bool}
_wake_event = threading.Event()
_started = False


def _ping_once(host):
    """True if `host` replies within PING_TIMEOUT_SECONDS; any failure collapses
    to False. Shells out to system `ping` rather than a raw socket, to avoid needing root."""
    if not host:
        return False
    try:
        result = subprocess.run(
            ["ping", "-c", "1", host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=PING_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def _check_all(servers):
    for server in servers:
        host = server["host"]
        success = _ping_once(host)
        with _lock:
            entry = _state.setdefault(host, {"consecutive_misses": 0, "checked": False})
            entry["checked"] = True
            entry["consecutive_misses"] = 0 if success else entry["consecutive_misses"] + 1


def _monitor_loop():
    while True:
        _check_all(get_caddy_servers())
        interval = get_caddy_server_ping_interval_seconds()
        # notify_config_changed() wakes this early so a settings save resolves within moments.
        _wake_event.wait(timeout=interval)
        _wake_event.clear()


def notify_config_changed():
    """Called after a Caddy Servers settings save so status resolves
    quickly instead of sitting stale for up to a full ping interval."""
    _wake_event.set()


def start_server_monitor():
    """Starts the background ping thread; safe to call more than once, only
    the first call does anything. Not called from create_app() -- see app.py -- to avoid leaking threads in tests."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_monitor_loop, daemon=True, name="caddy-server-monitor").start()


def get_server_statuses():
    """Current status of every configured server, for the navbar tags and the
    JSON refresh endpoint. Each entry includes its STATUS_DISPLAY metadata."""
    servers = get_caddy_servers()
    warning_after = get_caddy_server_warning_after_misses()
    danger_after = get_caddy_server_danger_after_misses()
    results = []
    with _lock:
        for server in servers:
            entry = _state.get(server["host"])
            if not entry or not entry["checked"]:
                status = "pending"
            else:
                misses = entry["consecutive_misses"]
                if misses >= danger_after:
                    status = "danger"
                elif misses >= warning_after:
                    status = "warning"
                else:
                    status = "online"
            display = STATUS_DISPLAY[status]
            results.append({
                "display_name": server["display_name"],
                "host": server["host"],
                "status": status,
                "bg_class": display["bg_class"],
                "dot_class": display["dot_class"],
                "label": display["label"],
            })
    return results
