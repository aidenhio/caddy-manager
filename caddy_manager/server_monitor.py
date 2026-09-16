"""Background ping monitor for the "Caddy Servers" configured in Settings
-> Caddy Servers -- shows a live status tag for each one in the navbar
(see templates/partials/header_nav_bar.html and static/js/nav-status.js),
independent of whichever page happens to be open.

A single background thread (started once from app.py, not from
create_app() itself -- see the comment there for why) pings every
configured server on a loop, tracking a simple consecutive-misses count
per host in memory. Request handlers only ever read that in-memory
state -- nothing in a request ever blocks on a live ping, since a real
ICMP round-trip (or an unreachable host timing out) can take seconds,
far too slow for a page render or a frequent navbar-refresh poll.

State deliberately lives in a plain module-level dict guarded by a lock
rather than anywhere in configstore's config.json: ping results are
transient/observational, not configuration, and persisting them would
mean stale data survives an app restart (a server that was Offline when
the app stopped would still show Offline for up to a full ping interval
after it restarts, before the first fresh check completes) -- a
"Checking" state that resolves within moments of startup is the more
honest UI for status that's inherently only as fresh as the last check.
"""
import subprocess
import threading

from .configstore import (
    get_caddy_servers, get_caddy_server_ping_interval_seconds,
    get_caddy_server_warning_after_misses, get_caddy_server_danger_after_misses,
)

# How long a single ping is allowed to take before it's counted as a miss.
# Comfortably under configstore.MIN_CADDY_SERVER_PING_INTERVAL_SECONDS so
# pinging every configured server (there are at most two) never runs long
# enough to meaningfully delay the next scheduled check.
PING_TIMEOUT_SECONDS = 3

# status -> the Tabler tag background class, the status-dot modifier
# class, and the one-word label the tooltip uses (e.g. "Online
# (10.0.0.10)"). Shared by the navbar's initial server-rendered tags
# (via get_server_statuses(), read through the nav_caddy_servers context
# processor in __init__.py) and the live JSON refresh endpoint
# (nav_server_status() in views.py) so the two can never drift out of
# sync with each other or with static/js/nav-status.js.
STATUS_DISPLAY = {
    "online": {"bg_class": "bg-success-lt", "dot_class": "status-success", "label": "Online"},
    "warning": {"bg_class": "bg-warning-lt", "dot_class": "status-warning", "label": "Unavailable"},
    "danger": {"bg_class": "bg-danger-lt", "dot_class": "status-danger", "label": "Offline"},
    # Shown only in the brief window before a server's very first ping
    # completes -- right after it's newly configured, or right after the
    # app starts. The monitor thread checks every configured server
    # immediately on startup and again immediately whenever the Caddy
    # Servers settings are saved (see notify_config_changed()), so this
    # normally clears within a second or two, not a full ping interval.
    "pending": {"bg_class": "bg-secondary-lt", "dot_class": "status-secondary", "label": "Checking"},
}

_lock = threading.Lock()
_state = {}  # host -> {"consecutive_misses": int, "checked": bool}
_wake_event = threading.Event()
_started = False


def _ping_once(host):
    """True if `host` replied to a single ICMP echo request within
    PING_TIMEOUT_SECONDS, False otherwise -- no reply, an unresolvable
    hostname, the `ping` binary itself missing, or anything else going
    wrong all collapse to the same "treat it as a miss" outcome, rather
    than raising and taking the monitor thread down.

    Shells out to the system `ping` command (`-c 1` = a single echo
    request) instead of a raw ICMP socket, since sending/receiving raw
    ICMP packets from Python normally needs root or CAP_NET_RAW -- not
    something this app should require just to show a status tag. The
    timeout is enforced by subprocess itself (`timeout=`) rather than
    ping's own per-platform timeout flag (`-W` means seconds on Linux,
    milliseconds on macOS/BSD), so behavior doesn't depend on which
    platform this happens to run on.
    """
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
        # wait() returns early (and the flag is cleared right after) if
        # notify_config_changed() fires in the meantime, so a server just
        # added or edited in Settings resolves within moments instead of
        # waiting out whatever's left of the previous interval.
        _wake_event.wait(timeout=interval)
        _wake_event.clear()


def notify_config_changed():
    """Called after a successful Caddy Servers settings save so a newly
    added or edited server's status resolves quickly instead of sitting
    at "Checking" (or showing a stale previous host's status) for up to a
    full ping interval."""
    _wake_event.set()


def start_server_monitor():
    """Starts the background ping thread, if it isn't already running.
    Safe to call more than once -- only the first call actually starts
    anything.

    Deliberately not called from create_app() itself: every test in this
    project's suite calls create_app() directly against its own
    throwaway config, and starting a real background ping thread per
    test would leak threads across the whole suite for no benefit. See
    app.py for where this is actually invoked, and why."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_monitor_loop, daemon=True, name="caddy-server-monitor").start()


def get_server_statuses():
    """The current status of every configured Caddy server, ready for
    both the navbar's server-rendered tags (via the nav_caddy_servers
    context processor in __init__.py) and the JSON refresh endpoint
    (nav_server_status() in views.py) -- each entry: display_name, host,
    status ("online", "warning", "danger", or "pending" -- see
    STATUS_DISPLAY), and that status's display metadata (bg_class,
    dot_class, label) so neither the template nor the JS poller needs
    its own copy of the thresholds-to-status mapping."""
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
