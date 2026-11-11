"""Background monitor driving the sidebar's live server status: one thread pings each
server, another checks Caddy's admin API on it. Results live in memory only."""
import subprocess
import threading
import urllib.error
import urllib.request

from .configstore import (
    get_caddy_servers, get_caddy_server_ping_interval_seconds, get_caddy_server_offline_after_misses,
    get_caddy_status_interval_seconds, get_caddy_status_failed_after,
)

# Comfortably under the 10s minimum intervals, so checking both servers never
# runs long enough to delay the next scheduled check.
PING_TIMEOUT_SECONDS = 3
STATUS_TIMEOUT_SECONDS = 3

# Sidebar badge per check result, as (label, badge class). None = not checked yet.
SERVER_BADGES = {
    "online": ("Online", "bg-green-lt"),
    "offline": ("Offline", "bg-red-lt"),
    None: ("Checking", "bg-secondary-lt"),
}
CADDY_BADGES = {
    "running": ("Running", "bg-green-lt"),
    "stopped": ("Stopped", "bg-yellow-lt"),
    None: ("Checking", "bg-secondary-lt"),
}

_lock = threading.Lock()
_ping_state = {}    # host -> {"misses": int, "checked": bool}
_status_state = {}  # (host, api_port) -> {"failures": int, "checked": bool}
_wake_events = []
_started = False


def admin_api_base_url(host, api_port):
    """http://host:port for a server's admin API, bracketing a bare IPv6 address."""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{api_port}"


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


def _caddy_running(host, api_port):
    """True if GET /config/ on the server's admin API answers HTTP 200."""
    try:
        req = urllib.request.Request(f"{admin_api_base_url(host, api_port)}/config/")
        with urllib.request.urlopen(req, timeout=STATUS_TIMEOUT_SECONDS) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False


def _ping_all(servers):
    for server in servers:
        success = _ping_once(server["host"])
        with _lock:
            entry = _ping_state.setdefault(server["host"], {"misses": 0, "checked": False})
            entry["checked"] = True
            entry["misses"] = 0 if success else entry["misses"] + 1


def _status_all(servers):
    for server in servers:
        key = (server["host"], server["api_port"])
        success = _caddy_running(*key)
        with _lock:
            entry = _status_state.setdefault(key, {"failures": 0, "checked": False})
            entry["checked"] = True
            entry["failures"] = 0 if success else entry["failures"] + 1


def _loop(check, get_interval, wake_event):
    while True:
        check(get_caddy_servers())
        # notify_config_changed() wakes this early so a settings save resolves within moments.
        wake_event.wait(timeout=get_interval())
        wake_event.clear()


def notify_config_changed():
    """Called after a Caddy Servers settings save so status resolves
    quickly instead of sitting stale for up to a full interval."""
    for event in _wake_events:
        event.set()


def start_server_monitor():
    """Starts the ping and status threads; safe to call more than once, only the
    first call does anything. Not called from create_app() -- see app.py -- to avoid leaking threads in tests."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    for name, check, get_interval in (
        ("caddy-server-ping", _ping_all, get_caddy_server_ping_interval_seconds),
        ("caddy-server-status", _status_all, get_caddy_status_interval_seconds),
    ):
        event = threading.Event()
        _wake_events.append(event)
        threading.Thread(target=_loop, args=(check, get_interval, event), daemon=True, name=name).start()


def caddy_status(server):
    """"running", "stopped", or None if not checked yet -- the admin API check on its own."""
    with _lock:
        entry = _status_state.get((server["host"], server["api_port"]))
        if not entry or not entry["checked"]:
            return None
        return "stopped" if entry["failures"] >= get_caddy_status_failed_after() else "running"


def get_server_statuses():
    """Ping and Caddy status of every configured server, for the sidebar and its JSON
    refresh endpoint. The dot is red if ping is down, yellow if only Caddy is down, else green."""
    servers = get_caddy_servers()
    offline_after = get_caddy_server_offline_after_misses()
    results = []
    for server in servers:
        with _lock:
            ping = _ping_state.get(server["host"])
        if not ping or not ping["checked"]:
            server_state = None
        else:
            server_state = "offline" if ping["misses"] >= offline_after else "online"
        caddy_state = caddy_status(server)
        if server_state == "offline":
            dot_class = "status-danger"
        elif server_state is None or caddy_state is None:
            dot_class = "status-secondary"
        elif caddy_state == "stopped":
            dot_class = "status-warning"
        else:
            dot_class = "status-success"
        server_label, server_badge = SERVER_BADGES[server_state]
        caddy_label, caddy_badge = CADDY_BADGES[caddy_state]
        results.append({
            "display_name": server["display_name"],
            "host": server["host"],
            "dot_class": dot_class,
            "server_label": server_label,
            "server_badge_class": server_badge,
            "caddy_label": caddy_label,
            "caddy_badge_class": caddy_badge,
        })
    return results
