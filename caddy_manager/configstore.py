"""Config file helpers.

A JSON file stands in for a database -- there's very little to store: the
admin credentials, the caddy.d directory, and a session secret key.
"""
import os
import json

# One level up from this package (caddy_manager/) is the project root, where
# config.json has always lived -- keeping this path unchanged means existing
# installs keep working without needing to move anything.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def is_configured():
    cfg = load_config()
    return bool(cfg and cfg.get("username") and cfg.get("password_hash") and cfg.get("caddy_dir"))


def get_caddy_dir():
    cfg = load_config()
    return cfg["caddy_dir"]
