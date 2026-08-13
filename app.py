import os
import json
import glob
import secrets
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Config helpers (a JSON file stands in for a database — there's very little
# to store: the admin credentials, the caddy.d directory, and a session key)
# ---------------------------------------------------------------------------

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


@app.before_request
def load_secret_key():
    cfg = load_config()
    if cfg and cfg.get("secret_key"):
        app.secret_key = cfg["secret_key"]
    else:
        # Temporary key so the setup page can still use flash()/session.
        if "_TEMP_SECRET" not in app.config:
            app.config["_TEMP_SECRET"] = secrets.token_hex(32)
        app.secret_key = app.config["_TEMP_SECRET"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_configured():
            return redirect(url_for("setup"))
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if is_configured():
        return redirect(url_for("login"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        caddy_dir = request.form.get("caddy_dir", "").strip()

        if not username or not password:
            error = "Username and password are required."
        elif password != password2:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif not caddy_dir:
            error = "Caddy conf directory is required."
        else:
            try:
                os.makedirs(caddy_dir, exist_ok=True)
            except OSError as e:
                error = f"Could not create/access that directory: {e}"

        if not error:
            cfg = {
                "secret_key": secrets.token_hex(32),
                "username": username,
                "password_hash": generate_password_hash(password),
                "caddy_dir": caddy_dir,
            }
            save_config(cfg)
            # Switch to the real secret key immediately so the flash message
            # set below actually survives the redirect to /login.
            app.secret_key = cfg["secret_key"]
            flash("Setup complete. Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("setup.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not is_configured():
        return redirect(url_for("setup"))
    error = None
    if request.method == "POST":
        cfg = load_config()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == cfg["username"] and check_password_hash(cfg["password_hash"], password):
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def get_caddy_dir():
    cfg = load_config()
    return cfg["caddy_dir"]


def safe_path(filename):
    """Resolve filename inside caddy_dir, preventing path traversal."""
    caddy_dir = os.path.abspath(get_caddy_dir())
    target = os.path.abspath(os.path.join(caddy_dir, filename))
    if target != caddy_dir and not target.startswith(caddy_dir + os.sep):
        abort(400, "Invalid filename")
    return target


def detect_type(content):
    """Best-effort detection of block type + domain, for files created
    either by this app or by hand outside of it."""
    domain = ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and "{" in stripped and not stripped.startswith("#"):
            domain = stripped.split("{")[0].strip()
            break

    if "lb_policy" in content:
        block_type = "load_balancer"
    elif "reverse_proxy" in content:
        block_type = "reverse_proxy"
    elif "redir" in content:
        block_type = "redirect"
    else:
        block_type = "custom"
    return block_type, domain


def list_blocks():
    caddy_dir = get_caddy_dir()
    if not os.path.isdir(caddy_dir):
        return []
    paths = glob.glob(os.path.join(caddy_dir, "*.conf")) + \
        glob.glob(os.path.join(caddy_dir, "*.conf.disabled"))

    blocks = []
    for path in paths:
        fname = os.path.basename(path)
        disabled = fname.endswith(".disabled")
        fdate = datetime.fromtimestamp(os.path.getmtime(path))
        try:
            with open(path, "r") as f:
                content = f.read()
        except OSError:
            content = ""
        block_type, domain = detect_type(content)
        
        blocks.append({
            "filename": fname,
            "disabled": disabled,
            "type": block_type,
            "domain": domain,
            "updated": fdate.strftime("%d/%m/%Y %I:%M%p"),
        })
    blocks.sort(key=lambda b: b["filename"].lower())
    return blocks


def slugify(value):
    value = (value or "").strip().lower()
    out = []
    for ch in value:
        if ch.isalnum() or ch == ".":
            out.append(ch)
        else:
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "block"


def unique_filename(base):
    caddy_dir = get_caddy_dir()
    candidate = f"{base}.conf"
    i = 2
    while os.path.exists(os.path.join(caddy_dir, candidate)) or \
            os.path.exists(os.path.join(caddy_dir, candidate + ".disabled")):
        candidate = f"{base}-{i}.conf"
        i += 1
    return candidate


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    caddy_dir = get_caddy_dir()
    dir_exists = os.path.isdir(caddy_dir)
    blocks = list_blocks() if dir_exists else []
    stats = {
        "total": len(blocks),
        "enabled": sum(1 for b in blocks if not b["disabled"]),
        "disabled": sum(1 for b in blocks if b["disabled"]),
    }
    return render_template(
        "home.html", stats=stats, caddy_dir=caddy_dir, dir_exists=dir_exists
    )


@app.route("/sites")
@login_required
def sites():
    caddy_dir = get_caddy_dir()
    dir_exists = os.path.isdir(caddy_dir)
    blocks = list_blocks() if dir_exists else []
    return render_template(
        "sites.html", blocks=blocks, caddy_dir=caddy_dir, dir_exists=dir_exists
    )


@app.route("/new/<block_type>", methods=["GET", "POST"])
@login_required
def new_block(block_type):
    if block_type not in ("reverse_proxy", "redirect", "custom"):
        abort(404)
    error = None

    if request.method == "POST":
        domain = request.form.get("domain", "").strip()
        filename_field = request.form.get("filename", "").strip()
        filename_base = slugify(filename_field or domain)
        content = None

        if block_type == "reverse_proxy":
            upstream = request.form.get("upstream", "").strip()
            extra = request.form.get("extra", "").strip()
            if not domain or not upstream:
                error = "Domain and upstream address are required."
            else:
                lines = [f"{domain} {{", f"    reverse_proxy {upstream}"]
                for line in extra.splitlines():
                    line = line.strip()
                    if line:
                        lines.append(f"    {line}")
                lines.append("}")
                content = "\n".join(lines) + "\n"

        elif block_type == "redirect":
            target = request.form.get("target", "").strip()
            status_code = request.form.get("status_code", "301").strip()
            if not domain or not target:
                error = "Domain and redirect target are required."
            else:
                content = f"{domain} {{\n    redir {target} {status_code}\n}}\n"

        else:  # custom
            raw = request.form.get("raw_content", "").strip()
            if not raw:
                error = "Block content is required."
            elif not filename_field and not domain:
                error = "Please provide a filename or label so the file can be named."
            else:
                content = raw + "\n"

        if not error:
            filename = unique_filename(filename_base)
            os.makedirs(get_caddy_dir(), exist_ok=True)
            with open(safe_path(filename), "w") as f:
                f.write(content)
            flash(f"Created {filename}", "success")
            return redirect(url_for("sites"))

    return render_template("new_block.html", block_type=block_type, error=error)


@app.route("/edit/<path:filename>", methods=["GET", "POST"])
@login_required
def edit_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    if request.method == "POST":
        content = request.form.get("content", "")
        with open(path, "w") as f:
            f.write(content)
        flash(f"Saved {filename}", "success")
        return redirect(url_for("sites"))

    with open(path, "r") as f:
        content = f.read()
    return render_template("edit.html", filename=filename, content=content)


@app.route("/toggle/<path:filename>", methods=["POST"])
@login_required
def toggle_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    if filename.endswith(".disabled"):
        new_name = filename[: -len(".disabled")]
    else:
        new_name = filename + ".disabled"

    os.rename(path, safe_path(new_name))
    state = "Disabled" if new_name.endswith(".disabled") else "Enabled"
    flash(f"{state} {new_name}", "success")
    return redirect(url_for("sites"))


@app.route("/delete/<path:filename>", methods=["POST"])
@login_required
def delete_block(filename):
    path = safe_path(filename)
    if os.path.isfile(path):
        os.remove(path)
        flash(f"Deleted {filename}", "success")
    return redirect(url_for("sites"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    cfg = load_config()
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_dir":
            new_dir = request.form.get("caddy_dir", "").strip()
            if not new_dir:
                error = "Directory is required."
            else:
                try:
                    os.makedirs(new_dir, exist_ok=True)
                except OSError as e:
                    error = f"Could not create/access that directory: {e}"
                if not error:
                    cfg["caddy_dir"] = new_dir
                    save_config(cfg)
                    flash("Caddy directory updated.", "success")
                    return redirect(url_for("settings"))

        elif action == "change_password":
            current = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            new_password2 = request.form.get("new_password2", "")
            if not check_password_hash(cfg["password_hash"], current):
                error = "Current password is incorrect."
            elif len(new_password) < 6:
                error = "New password must be at least 6 characters."
            elif new_password != new_password2:
                error = "New passwords do not match."
            else:
                cfg["password_hash"] = generate_password_hash(new_password)
                save_config(cfg)
                flash("Password updated.", "success")
                return redirect(url_for("settings"))

    return render_template("settings.html", cfg=cfg, error=error)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
