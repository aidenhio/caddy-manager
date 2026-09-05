"""Config file helpers.

A JSON file stands in for a database -- there's very little to store: the
admin credentials, the Caddy root directory and the paths derived from
it, and a session secret key.
"""
import os
import json

# One level up from this package (caddy_manager/) is the project root, where
# config.json has always lived -- keeping this path unchanged means existing
# installs keep working without needing to move anything.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def default_paths_for_root(root_dir):
    """The conventional Caddy directory layout this app assumes under a
    given root directory:

        <root>/
        |- caddy.d/    -- conf_dir: the .conf blocks this app manages
        |- data/       -- certificate_dir: Caddy's data directory
        |               (https://caddyserver.com/docs/conventions#data-directory),
        |               where it keeps TLS certificates/keys
        |- logs/       -- log_dir
        |- Caddyfile   -- caddyfile_path: the main Caddyfile importing conf_dir

    Any of these can be overridden away from the default individually, in
    Setup's advanced options or later from Settings."""
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
        # Migrate installs from before the Caddy root directory concept:
        # the single caddy_dir they configured becomes conf_dir, and its
        # parent becomes a best-guess root_dir so the other three paths
        # have a sensible default -- correct any of them from Settings.
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


def get_caddy_log_output_dir():
    """The directory path written into a block's `output file` line when
    logging is enabled -- i.e. where Caddy itself will actually write that
    block's access log, as far as Caddy's own filesystem sees it.

    This is deliberately independent from get_log_dir(), which is where
    Caddy Manager looks to read/tail/delete/rename log files on its own
    side. The two normally point at the same directory (this defaults to
    get_log_dir(), itself root_dir/logs by default), but they can be split
    apart when Caddy and Caddy Manager don't share the same filesystem
    view of the logs volume -- for example, each running in its own
    container with that volume mounted at a different path. Overriding
    this setting only changes what gets written into newly rendered .conf
    files; it never affects where Caddy Manager itself looks for logs."""
    cfg = load_config()
    value = (cfg.get("caddy_log_output_dir") or "").strip() if cfg else ""
    return value or get_log_dir()


# Caddy's built-in default is to attempt renewal starting 30 days before
# expiry -- 37 gives it a week of retries (rate limits, a flaky ACME
# challenge, DNS propagation) before the Certificates page calls a cert
# "expiring soon", so the badge means "renewal may need attention" rather
# than just "due soon and presumably fine."
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


# The header "Quick Add" button skips the New Site Block type-picker modal,
# linking straight to main.new_block for one pre-chosen type -- configured
# separately per page (Home Dashboard vs Site Blocks) since a deployment
# might create mostly reverse proxies on one and mostly static sites on the
# other. A page's type defaults to (and can be reset to) "None", which is
# itself what turns the button off for that page -- there's no separate
# enable switch.
QUICK_ADD_BLOCK_TYPES = ("reverse_proxy", "redirect", "load_balancer", "static_site", "custom")


def get_quick_add_type_dashboard():
    cfg = load_config()
    value = cfg.get("quick_add_type_dashboard") if cfg else None
    return value if value in QUICK_ADD_BLOCK_TYPES else None


def get_quick_add_type_site_blocks():
    cfg = load_config()
    value = cfg.get("quick_add_type_site_blocks") if cfg else None
    return value if value in QUICK_ADD_BLOCK_TYPES else None


# Whether a block's Preview page shows the raw metadata sidecar alongside its
# Caddy config -- on by default, since the metadata card is how someone
# double-checks what the app has stored about a block (creation time, log
# settings, etc.) without opening the sidecar file directly.
DEFAULT_SHOW_METADATA_CARD = True


def get_show_metadata_card():
    cfg = load_config()
    value = cfg.get("show_metadata_card") if cfg else None
    if isinstance(value, bool):
        return value
    return DEFAULT_SHOW_METADATA_CARD
