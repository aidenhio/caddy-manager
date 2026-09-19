"""Config file helpers. A JSON file stands in for a database -- admin
credentials, the Caddy root directory and derived paths, and a session secret key."""
import os
import json

# config.json lives at the project root, one level up from this package.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def default_paths_for_root(root_dir):
    """Conventional Caddy layout under root_dir: caddy.d/ (conf_dir),
    data/ (certificate_dir), logs/ (log_dir), Caddyfile. Each is overridable from Settings."""
    root_dir = (root_dir or "").rstrip("/\\")
    return {
        "conf_dir": os.path.join(root_dir, "caddy.d"),
        "certificate_dir": os.path.join(root_dir, "data"),
        "log_dir": os.path.join(root_dir, "logs"),
        "caddyfile_path": os.path.join(root_dir, "Caddyfile"),
    }


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)

    if "conf_dir" not in cfg and "caddy_dir" in cfg:
        # Migrate pre-root-directory installs: caddy_dir -> conf_dir, its parent -> a guessed root_dir.
        conf_dir = cfg.pop("caddy_dir")
        root_dir = os.path.dirname(conf_dir.rstrip("/\\")) or conf_dir
        cfg["root_dir"] = root_dir
        cfg["conf_dir"] = conf_dir
        defaults = default_paths_for_root(root_dir)
        cfg.setdefault("certificate_dir", defaults["certificate_dir"])
        cfg.setdefault("log_dir", defaults["log_dir"])
        cfg.setdefault("caddyfile_path", defaults["caddyfile_path"])
        save_config(cfg)

    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def is_configured():
    cfg = load_config()
    return bool(cfg and cfg.get("username") and cfg.get("password_hash") and cfg.get("conf_dir"))


def get_conf_dir():
    return load_config()["conf_dir"]


def get_certificate_dir():
    return load_config().get("certificate_dir", "")


def get_log_dir():
    return load_config().get("log_dir", "")


def get_caddyfile_path():
    return load_config().get("caddyfile_path", "")


def get_caddyfile_backup_path():
    """Backup path for the Global Configuration tab's save/rollback: always
    Caddyfile.bak next to the real Caddyfile, or None if unconfigured."""
    caddyfile_path = get_caddyfile_path()
    if not caddyfile_path:
        return None
    return os.path.join(os.path.dirname(caddyfile_path), "Caddyfile.bak")


def get_caddy_log_output_dir():
    """Directory written into a block's `output file` line -- independent of
    get_log_dir() (this app's read side), for a split Caddy/app filesystem view."""
    cfg = load_config()
    value = (cfg.get("caddy_log_output_dir") or "").strip() if cfg else ""
    return value or get_log_dir()


def get_caddy_admin_api_url():
    """Caddy admin API address, used for Dashboard stats. Empty string if
    unset -- entirely optional, nothing else depends on it."""
    cfg = load_config()
    return (cfg.get("caddy_admin_api_url") or "").strip() if cfg else ""


# Caddy starts renewal 30 days out; 37 gives it a week of retries before
# this app's "expiring soon" badge means renewal may need attention.
DEFAULT_CERT_EXPIRING_SOON_DAYS = 37


def get_cert_expiring_soon_days():
    cfg = load_config()
    value = cfg.get("cert_expiring_soon_days") if cfg else None
    try:
        days = int(value)
        if days > 0:
            return days
    except (TypeError, ValueError):
        pass
    return DEFAULT_CERT_EXPIRING_SOON_DAYS


DEFAULT_LOG_TAIL_LINES = 20


def get_log_tail_lines():
    cfg = load_config()
    value = cfg.get("log_tail_lines") if cfg else None
    try:
        lines = int(value)
        if lines > 0:
            return lines
    except (TypeError, ValueError):
        pass
    return DEFAULT_LOG_TAIL_LINES


# The "Quick Add" button skips the type-picker modal for one pre-chosen type,
# set per page. "None" both is the default and turns the button off.
QUICK_ADD_BLOCK_TYPES = ("reverse_proxy", "redirect", "load_balancer", "static_site", "custom")


def get_quick_add_type_dashboard():
    cfg = load_config()
    value = cfg.get("quick_add_type_dashboard") if cfg else None
    return value if value in QUICK_ADD_BLOCK_TYPES else None


def get_quick_add_type_site_blocks():
    cfg = load_config()
    value = cfg.get("quick_add_type_site_blocks") if cfg else None
    return value if value in QUICK_ADD_BLOCK_TYPES else None


# Whether the Preview page shows the raw metadata sidecar. On by default.
DEFAULT_SHOW_METADATA_CARD = True


def get_show_metadata_card():
    cfg = load_config()
    value = cfg.get("show_metadata_card") if cfg else None
    if isinstance(value, bool):
        return value
    return DEFAULT_SHOW_METADATA_CARD


# Dashboard widgets in display order, as (config key, toggle label). All shown by default.
DASHBOARD_WIDGETS = (
    ("quick_glance_row", "Quick Glance Row"),
    ("recently_added", "Recently Added"),
    ("sites_by_type", "Site Blocks by Type"),
    ("certificate_status", "Certificate Status"),
    ("upstream_health", "Upstream Health"),
)

# Up to this many servers can be ping-monitored (see server_monitor.py),
# matching the navbar layout's design.
MAX_CADDY_SERVERS = 2

DEFAULT_CADDY_SERVER_PING_INTERVAL_SECONDS = 60
# Floor for the settings form's validation, kept here so it can't drift from the getter.
MIN_CADDY_SERVER_PING_INTERVAL_SECONDS = 10
DEFAULT_CADDY_SERVER_WARNING_AFTER_MISSES = 3
DEFAULT_CADDY_SERVER_DANGER_AFTER_MISSES = 5


def get_caddy_servers():
    """Up to MAX_CADDY_SERVERS servers to ping-monitor, each as
    {"display_name": str, "host": str}, both always non-empty."""
    cfg = load_config()
    stored = cfg.get("caddy_servers") if cfg else None
    if not isinstance(stored, list):
        return []
    servers = []
    for entry in stored[:MAX_CADDY_SERVERS]:
        if not isinstance(entry, dict):
            continue
        display_name = (entry.get("display_name") or "").strip()
        host = (entry.get("host") or "").strip()
        if display_name and host:
            servers.append({"display_name": display_name, "host": host})
    return servers


def get_caddy_server_ping_interval_seconds():
    cfg = load_config()
    value = cfg.get("caddy_server_ping_interval_seconds") if cfg else None
    try:
        seconds = int(value)
        if seconds >= MIN_CADDY_SERVER_PING_INTERVAL_SECONDS:
            return seconds
    except (TypeError, ValueError):
        pass
    return DEFAULT_CADDY_SERVER_PING_INTERVAL_SECONDS


def get_caddy_server_warning_after_misses():
    cfg = load_config()
    value = cfg.get("caddy_server_warning_after_misses") if cfg else None
    try:
        misses = int(value)
        if misses > 0:
            return misses
    except (TypeError, ValueError):
        pass
    return DEFAULT_CADDY_SERVER_WARNING_AFTER_MISSES


def get_caddy_server_danger_after_misses():
    cfg = load_config()
    value = cfg.get("caddy_server_danger_after_misses") if cfg else None
    try:
        misses = int(value)
        if misses > 0:
            return misses
    except (TypeError, ValueError):
        pass
    return DEFAULT_CADDY_SERVER_DANGER_AFTER_MISSES


def get_dashboard_widget_visibility():
    """{key: bool} for every key in DASHBOARD_WIDGETS, defaulting to
    shown (True) when unset or malformed."""
    cfg = load_config()
    stored = cfg.get("dashboard_widgets") if cfg else None
    stored = stored if isinstance(stored, dict) else {}
    return {
        key: stored[key] if isinstance(stored.get(key), bool) else True
        for key, _label in DASHBOARD_WIDGETS
    }
