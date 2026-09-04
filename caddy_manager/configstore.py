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
